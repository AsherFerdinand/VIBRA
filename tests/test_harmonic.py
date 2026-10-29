"""Independent receptance/phase benchmarks and physical/algebraic failure cases."""

import json

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError

from vibra.core.assembly import assemble
from vibra.core.errors import EngineeringError, SolverError, UnstableModelError
from vibra.core.mesh import cantilever
from vibra.core.models import DOF, FrameModel
from vibra.io.harmonic_report import harmonic_report
from vibra.solvers.harmonic import (
    Damping,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.solvers.modal import solve_modal
from vibra.verification.benchmarks import steel_case
from vibra.verification.harmonic_analytical import sdof_receptance
from vibra.verification.harmonic_benchmarks import guided_beam, harmonic_verification_report


def beam(count: int = 8) -> FrameModel:
    g, m, r = steel_case()
    return cantilever(g, m, r.section(), count, tip_force=0)


def config(model: FrameModel, damping: Damping | None = None) -> HarmonicConfig:
    tip = max(node.id for node in model.nodes)
    return HarmonicConfig(
        frequencies_hz=(0, 8, 16, 18, 25),
        damping=damping or Damping(kind="rayleigh", alpha=2, beta=2e-5),
        loads=(HarmonicLoad(node=tip, amplitude=1),),
        responses=(ResponseDOF(node=tip), ResponseDOF(node=tip, dof=DOF.RZ)),
    )


@pytest.mark.parametrize(
    "damping",
    [
        Damping(),
        Damping(kind="mass", alpha=2),
        Damping(kind="stiffness", beta=2e-5),
        Damping(kind="rayleigh", alpha=2, beta=2e-5),
    ],
)
@pytest.mark.parametrize("load_phase", [0, 43, -110])
def test_sdof_receptance_amplitude_and_phase(damping: Damping, load_phase: float) -> None:
    model, mass, stiffness = guided_beam()
    wn = np.sqrt(stiffness / mass)
    # Undamped samples avoid the singular natural frequency; damped includes it.
    ratios = (0, 0.3, 0.9, 1.1, 2) if damping.kind == "undamped" else (0, 0.5, 1, 1.5, 2)
    frequencies = tuple(float(wn / (2 * np.pi) * ratio) for ratio in ratios)
    case = HarmonicConfig(
        frequencies_hz=frequencies,
        damping=damping,
        loads=(HarmonicLoad(node=1, amplitude=3, phase_degrees=load_phase),),
        responses=(ResponseDOF(node=1),),
    )
    result = solve_harmonic(model, case)
    exact = (
        3
        * np.exp(1j * np.deg2rad(load_phase))
        * sdof_receptance(
            mass, stiffness, damping.alpha * mass + damping.beta * stiffness, frequencies
        )
    )
    assert_allclose(result.displacement[:, 4], exact, rtol=1e-11, atol=1e-15)
    assert_allclose(result.response_amplitude[:, 0], np.abs(exact), rtol=1e-11)
    assert_allclose(np.exp(1j * result.phase_radians[:, 0]), exact / np.abs(exact), atol=1e-11)
    if damping.kind != "undamped":
        assert_allclose(
            np.angle(result.displacement[2, 4] / np.exp(1j * np.deg2rad(load_phase))),
            -np.pi / 2,
            atol=1e-10,
        )


def test_matrix_equation_and_modal_superposition() -> None:
    model = beam()
    case = config(model)
    result = solve_harmonic(model, case)
    assembly = assemble(model)
    k, m = assembly.stiffness, assembly.mass
    c = case.damping.alpha * m + case.damping.beta * k
    for index, frequency in enumerate(case.frequencies_hz):
        omega = 2 * np.pi * frequency
        residual = (k - omega**2 * m + 1j * omega * c) @ result.displacement[
            index
        ] - result.force_phasor
        assert_allclose(residual[assembly.free], 0, atol=1e-8)
    assert_allclose(result.displacement[:, assembly.fixed], 0, atol=0)
    # Full modal sum is an independent algorithmic check of the direct LU solve.
    from vibra.core.models import AnalysisConfig

    modes = solve_modal(model, AnalysisConfig(modes=len(assembly.free)))
    generalized_force = modes.modes.T @ result.force_phasor
    for index, frequency in enumerate(case.frequencies_hz):
        omega = 2 * np.pi * frequency
        denominator = (
            modes.eigenvalues
            - omega**2
            + 1j * omega * (case.damping.alpha + case.damping.beta * modes.eigenvalues)
        )
        reconstructed = modes.modes @ (generalized_force / denominator)
        assert_allclose(result.displacement[index], reconstructed, rtol=3e-7, atol=1e-10)
    assert np.max(result.backward_errors) < 1e-12
    assert np.all(result.reciprocal_condition > case.condition_tolerance)


def test_independent_continuum_convergence_static_and_resonance() -> None:
    report = harmonic_verification_report()
    assert report["passed"]
    assert not report["experimental_validation"]
    assert not report["ansys_correlation"]


@pytest.mark.parametrize("zero_case", ["empty", "zero", "support"])
def test_zero_response_has_undefined_phase_and_no_resonance(zero_case: str) -> None:
    model = beam()
    loads = {
        "empty": (),
        "zero": (HarmonicLoad(node=8, amplitude=0),),
        "support": (HarmonicLoad(node=0, amplitude=1),),
    }[zero_case]
    case = HarmonicConfig(**(config(model).model_dump() | {"loads": loads}))
    result = solve_harmonic(model, case)
    assert_allclose(result.displacement, 0, atol=0)
    assert not np.any(result.phase_defined)
    assert result.peaks == result.sampled_maxima == ()
    report = json.loads(harmonic_report(model, case, result))
    assert report["results"]["harmonic"]["peaks"] == []


def test_load_superposition_reciprocity_and_selected_support() -> None:
    model = beam()
    base = config(model)
    loads = (HarmonicLoad(node=8, amplitude=0.5), HarmonicLoad(node=8, amplitude=0.5))
    doubled = solve_harmonic(model, HarmonicConfig(**(base.model_dump() | {"loads": loads})))
    original = solve_harmonic(model, base)
    assert_allclose(doubled.displacement, original.displacement, rtol=1e-12)
    support_case = HarmonicConfig(**(base.model_dump() | {"responses": (ResponseDOF(node=0),)}))
    support = solve_harmonic(model, support_case)
    assert_allclose(support.response_amplitude, 0, atol=0)
    assert not np.any(support.phase_defined)
    direct = solve_harmonic(
        model,
        HarmonicConfig(
            **(
                base.model_dump()
                | {
                    "loads": (HarmonicLoad(node=8, amplitude=1),),
                    "responses": (ResponseDOF(node=4),),
                }
            )
        ),
    )
    reciprocal = solve_harmonic(
        model,
        HarmonicConfig(
            **(
                base.model_dump()
                | {
                    "loads": (HarmonicLoad(node=4, amplitude=1),),
                    "responses": (ResponseDOF(node=8),),
                }
            )
        ),
    )
    assert_allclose(direct.displacement[:, 13], reciprocal.displacement[:, 25], rtol=1e-10)


def test_exact_and_near_undamped_resonance_rejected_even_for_scalar() -> None:
    model, mass, stiffness = guided_beam()
    natural = float(np.sqrt(stiffness / mass) / (2 * np.pi))
    for ratio in (1.0, 1 + 1e-14):
        for force in (0, 1):
            case = HarmonicConfig(
                frequencies_hz=(natural * ratio,),
                loads=(HarmonicLoad(node=1, amplitude=force),),
                responses=(ResponseDOF(node=1),),
            )
            with pytest.raises(SolverError, match="dynamic stiffness.*Hz"):
                solve_harmonic(model, case)


def test_multidof_resonance_and_overflow_rejected() -> None:
    model = beam(2)
    natural = float(solve_modal(model).frequencies_hz[0])
    case = HarmonicConfig(
        **(
            config(model).model_dump()
            | {
                "damping": Damping(),
                "frequencies_hz": (natural,),
            }
        )
    )
    with pytest.raises(SolverError, match="dynamic stiffness"):
        solve_harmonic(model, case)
    overflow = HarmonicConfig(**(case.model_dump() | {"frequencies_hz": (1e200,)}))
    with pytest.raises(SolverError, match="overflow"):
        solve_harmonic(model, overflow)


def test_unconstrained_and_unknown_nodes_rejected() -> None:
    model = beam()
    with pytest.raises(UnstableModelError):
        solve_harmonic(FrameModel(**(model.model_dump() | {"constraints": ()})), config(model))
    for field, value in [
        ("loads", (HarmonicLoad(node=99, amplitude=1),)),
        ("responses", (ResponseDOF(node=99),)),
    ]:
        case = HarmonicConfig(**(config(model).model_dump() | {field: value}))
        with pytest.raises(EngineeringError, match="unknown node"):
            solve_harmonic(model, case)


@pytest.mark.parametrize(
    "frequencies", [(), (-1,), (2, 1), (1, 1), (float("nan"),), (float("inf"),)]
)
def test_invalid_frequency_sequences(frequencies: tuple[float, ...]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        HarmonicConfig(frequencies_hz=frequencies, responses=(ResponseDOF(node=1),))


@pytest.mark.parametrize(
    "data",
    [
        {"alpha": -1},
        {"beta": -1},
        {"kind": "undamped", "alpha": 1},
        {"kind": "mass", "beta": 1},
        {"kind": "stiffness", "alpha": 1},
        {"kind": "rayleigh", "beta": float("nan")},
        {"kind": "unknown"},
    ],
)
def test_invalid_damping(data: dict[str, object]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        Damping.model_validate(data)


def test_input_guards_and_sweep_endpoints() -> None:
    for data in [{"stop_hz": 0}, {"start_hz": 10, "stop_hz": 5}, {"points": 1}]:
        with pytest.raises((ValidationError, EngineeringError)):
            FrequencySweep.model_validate(data)
    sweep = FrequencySweep(start_hz=1, stop_hz=3, points=3)
    assert sweep.frequencies() == (1, 2, 3)
    with pytest.raises(ValidationError):
        HarmonicLoad(node=1, amplitude=-1)
    with pytest.raises(ValidationError):
        HarmonicLoad(node=1, amplitude=1, phase_degrees=float("inf"))
    with pytest.raises((ValidationError, EngineeringError)):
        HarmonicConfig(frequencies_hz=(0,), responses=(ResponseDOF(node=1),) * 2)


def test_json_preserves_complex_arrays_inputs_peaks_and_metadata() -> None:
    model = beam()
    case = config(model)
    result = solve_harmonic(model, case)
    report = json.loads(harmonic_report(model, case, result))
    arrays = report["results"]["harmonic"]["displacement"]
    restored = np.array(arrays["real"]) + 1j * np.array(arrays["imag"])
    assert_allclose(restored, result.displacement, atol=0)
    assert report["inputs"]["harmonic"]["damping"]["kind"] == "rayleigh"
    assert report["results"]["numerical_verification"]["experimental_validation"] is False
    assert report["results"]["assumptions_and_limitations"]
    assert len(report["results"]["harmonic"]["natural_frequencies_hz"]) == 24
    assert result.peaks[0].frequency_hz == 16
    assert not result.peaks[0].at_sweep_boundary


def test_deformation_is_real_complex_snapshot_not_amplitude() -> None:
    from vibra.visualization.harmonic import harmonic_shape, response_figures

    model = beam(2)
    result = solve_harmonic(model, config(model))
    index, scale = 2, 3.0
    figure = harmonic_shape(model, result, index, 90, scale)
    # For θ=90°, Re(U exp(jθ)) = −Im(U). Last deformed member trace ends at tip.
    last_deformed = figure.data[3]
    assert_allclose(last_deformed.y[-1], -result.displacement[index, -2].imag * scale, atol=1e-12)
    assert_allclose(
        last_deformed.x[-1], 1 - result.displacement[index, -3].imag * scale, atol=1e-12
    )
    amplitude, phase = response_figures(result)
    assert len(amplitude.data) >= 2
    assert len(phase.data) == len(result.response_dofs)
    with pytest.raises(ValueError):
        harmonic_shape(model, result, 99, 0, 1)


def test_boundary_maximum_is_not_reported_as_interior_resonance() -> None:
    model = beam()
    base = config(model)
    case = HarmonicConfig(**(base.model_dump() | {"frequencies_hz": (1, 2, 3)}))
    result = solve_harmonic(model, case)
    assert result.peaks == ()
    assert all(peak.at_sweep_boundary for peak in result.sampled_maxima)
    assert all(peak.frequency_hz == 3 for peak in result.sampled_maxima)


def test_oriented_beam_phased_forces_transform_consistently() -> None:
    from vibra.core.mesh import BeamGeometry

    g, m, r = steel_case()
    angle = np.deg2rad(37)
    horizontal = cantilever(g, m, r.section(), 4, tip_force=0)
    rotated = cantilever(
        BeamGeometry(length=g.length, angle_degrees=37), m, r.section(), 4, tip_force=0
    )
    base = config(horizontal)
    rotated_case = HarmonicConfig(
        **(
            base.model_dump()
            | {
                "loads": (
                    HarmonicLoad(
                        node=4, dof=DOF.UX, amplitude=float(np.sin(angle)), phase_degrees=180
                    ),
                    HarmonicLoad(
                        node=4, dof=DOF.UY, amplitude=float(np.cos(angle)), phase_degrees=0
                    ),
                ),
            }
        )
    )
    normal = solve_harmonic(horizontal, base)
    turned = solve_harmonic(rotated, rotated_case)
    assert_allclose(
        turned.displacement[:, -3], -np.sin(angle) * normal.displacement[:, -2], rtol=1e-9
    )
    assert_allclose(
        turned.displacement[:, -2], np.cos(angle) * normal.displacement[:, -2], rtol=1e-9
    )
    assert_allclose(turned.displacement[:, -1], normal.displacement[:, -1], rtol=1e-9)
    moment_case = HarmonicConfig(
        **(
            base.model_dump()
            | {
                "loads": (HarmonicLoad(node=4, dof=DOF.RZ, amplitude=1, phase_degrees=720),),
            }
        )
    )
    moment = solve_harmonic(horizontal, moment_case)
    # Maxwell–Betti reciprocity: tip displacement/moment = tip rotation/transverse force.
    assert_allclose(moment.displacement[:, -2], normal.displacement[:, -1], rtol=1e-10)
