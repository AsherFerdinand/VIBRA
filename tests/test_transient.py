"""Independent transient mechanics, event handling, energy and validation checks."""

import json

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError
from scipy.integrate import solve_ivp

from vibra.core.assembly import assemble
from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.errors import EngineeringError, SolverError, UnstableModelError
from vibra.core.mesh import cantilever
from vibra.core.models import DOF, FrameModel
from vibra.dynamics.forcing import HarmonicForce, PulseForce, SampledForce, StepForce, force_limits
from vibra.io.transient_report import transient_report
from vibra.solvers.static import solve_static
from vibra.solvers.transient import InitialValue, TimeGrid, TransientConfig, solve_transient
from vibra.verification.benchmarks import steel_case
from vibra.verification.harmonic_benchmarks import guided_beam
from vibra.verification.transient_analytical import forced_cosine_sdof, free_sdof, half_sine_sdof
from vibra.verification.transient_benchmarks import transient_verification_report


def scalar_config() -> TransientConfig:
    return TransientConfig(
        grid=TimeGrid(duration=0.2, time_step=0.00005),
        responses=(ResponseDOF(node=1),),
        initial_displacement=(InitialValue(node=1, value=0.001),),
        initial_velocity=(InitialValue(node=1, value=0.01),),
    )


@pytest.mark.parametrize("alpha", [0, 4, 20])
def test_free_vibration_initial_acceleration_and_energy(alpha: float) -> None:
    model, mass, stiffness = guided_beam()
    config = TransientConfig(
        **(scalar_config().model_dump() | {"damping": Damping(kind="mass", alpha=alpha)})
    )
    result = solve_transient(model, config)
    exact_x, exact_v, exact_a = free_sdof(result.time, mass, stiffness, alpha * mass, 0.001, 0.01)
    assert_allclose(result.displacement[:, 4], exact_x, atol=4e-7)
    assert_allclose(result.velocity[:, 4], exact_v, atol=7e-5)
    assert_allclose(result.acceleration[:, 4], exact_a, atol=0.012)
    assert_allclose(result.acceleration[0, 4], -alpha * 0.01 - stiffness / mass * 0.001, rtol=1e-13)
    energy = result.kinetic_energy + result.strain_energy
    assert result.relative_energy_error < 1e-10
    if alpha == 0:
        assert_allclose(energy / energy[0], 1, atol=1e-10)
        assert_allclose(result.damping_dissipation, 0, atol=0)
    else:
        assert np.all(np.diff(energy) <= 1e-12)
        assert np.all(np.diff(result.damping_dissipation) >= 0)
        assert_allclose(energy + result.damping_dissipation, energy[0], atol=1e-11)


def test_harmonic_forced_transient_and_energy() -> None:
    model, mass, stiffness = guided_beam()
    config = TransientConfig(
        grid=TimeGrid(duration=0.2, time_step=0.00005),
        damping=Damping(kind="mass", alpha=8),
        loads=(HarmonicForce(node=1, amplitude=1, frequency_hz=15),),
        responses=(ResponseDOF(node=1),),
    )
    result = solve_transient(model, config)
    exact, _, _ = forced_cosine_sdof(result.time, mass, stiffness, 8 * mass, 1, 2 * np.pi * 15)
    assert_allclose(result.displacement[:, 4], exact, atol=1e-8)
    assert_allclose(result.acceleration[0, 4], 1 / mass, rtol=1e-13)
    assert result.relative_energy_error < 1e-10
    assert result.external_work[-1] > 0


@pytest.mark.parametrize("rectangular", [False, True])
def test_delayed_force_jumps_do_not_act_before_event(rectangular: bool) -> None:
    model, mass, stiffness = guided_beam()
    load = (
        PulseForce(node=1, amplitude=1, start_time=0.01, end_time=0.03, shape="rectangular")
        if rectangular
        else StepForce(node=1, start_time=0.01)
    )
    result = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.1, time_step=0.00005),
            loads=(load,),
            responses=(ResponseDOF(node=1),),
        ),
    )
    wn = np.sqrt(stiffness / mass)
    exact = np.where(result.time >= 0.01, (1 - np.cos(wn * (result.time - 0.01))) / stiffness, 0)
    if rectangular:
        exact -= np.where(
            result.time >= 0.03, (1 - np.cos(wn * (result.time - 0.03))) / stiffness, 0
        )
    assert_allclose(result.displacement[:, 4], exact, atol=1e-8)
    assert_allclose(result.displacement[:201], 0, atol=0)
    assert_allclose(result.velocity[:201], 0, atol=0)
    assert result.force_right[200, 4] == 1
    assert result.force_left[200, 4] == 0
    assert_allclose(result.acceleration[200, 4], 1 / mass, rtol=1e-13)
    assert_allclose(
        mass * result.acceleration[:, 4] + stiffness * result.displacement[:, 4],
        result.force_right[:, 4],
        atol=1e-12,
    )
    assert result.relative_energy_error < 1e-10


def test_half_sine_pulse_against_closed_form() -> None:
    model, mass, stiffness = guided_beam()
    config = TransientConfig(
        grid=TimeGrid(duration=0.2, time_step=0.000025),
        loads=(PulseForce(node=1, amplitude=-2, end_time=0.04),),
        responses=(ResponseDOF(node=1),),
    )
    result = solve_transient(model, config)
    exact = half_sine_sdof(result.time, mass, stiffness, -2, 0.04)
    assert_allclose(result.displacement[:, 4], exact, atol=1e-8)
    assert_allclose(result.force_right[1600:, 4], 0, atol=0)
    assert_allclose(result.external_work[1600:], result.external_work[1600], atol=0)


def test_sampled_force_linear_interpolation_against_independent_ivp() -> None:
    model, mass, stiffness = guided_beam()
    load = SampledForce(node=1, times=(0, 0.0130375, 0.04, 0.1), values=(0, 1, 0, 0))
    case = TransientConfig(
        grid=TimeGrid(duration=0.1, time_step=0.00005),
        loads=(load,),
        responses=(ResponseDOF(node=1),),
    )
    result = solve_transient(model, case)
    assert_allclose(
        result.force_right[:, 4], np.interp(result.time, load.times, load.values), atol=0
    )
    assert_allclose(result.force_left, result.force_right, atol=0)
    assert any("knots" in warning for warning in result.numerical_warnings)

    def rhs(time: float, state: np.ndarray[tuple[int, ...], np.dtype[np.float64]]) -> list[float]:
        return [
            float(state[1]),
            float((np.interp(time, load.times, load.values) - stiffness * state[0]) / mass),
        ]

    reference = solve_ivp(
        rhs,
        (0, 0.1),
        [0, 0],
        t_eval=result.time,
        method="DOP853",
        rtol=1e-11,
        atol=1e-13,
        max_step=0.000025,
    )
    assert reference.success
    assert_allclose(result.displacement[:, 4], reference.y[0], atol=5e-9)


def test_static_equilibrium_general_beam_and_dynamic_support_inertia() -> None:
    g, material, rectangle = steel_case()
    frame = cantilever(g, material, rectangle.section(), 4, tip_force=1)
    static = solve_static(frame)
    initial = tuple(
        InitialValue(node=node, dof=DOF(j), value=float(static.displacement[i, j]))
        for i, node in enumerate(static.node_ids)
        for j in range(3)
    )
    case = TransientConfig(
        grid=TimeGrid(duration=0.1, time_step=0.0005),
        loads=(StepForce(node=4),),
        responses=(ResponseDOF(node=4),),
        initial_displacement=initial,
    )
    result = solve_transient(frame, case)
    assert_allclose(
        result.displacement,
        np.broadcast_to(static.displacement.reshape(-1), result.displacement.shape),
        atol=1e-12,
    )
    assert_allclose(
        result.reactions, np.broadcast_to(static.reactions[0], result.reactions.shape), atol=1e-7
    )
    model, mass, _ = guided_beam()
    transient = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.01, time_step=0.00005),
            loads=(StepForce(node=1),),
            responses=(ResponseDOF(node=1),),
        ),
    )
    # At t=0 the root shear includes consistent-mass coupling: M_root,tip / M_tip,tip = 54/156.
    root_y_column = transient.constrained_indices.index(1)
    assert_allclose(transient.reactions[0, root_y_column], 54 / 156, rtol=1e-13)
    assert_allclose(transient.acceleration[0, 4], 1 / mass, rtol=1e-13)


def test_constraints_multiple_dofs_and_full_dynamic_equilibrium() -> None:
    g, material, rectangle = steel_case()
    model = cantilever(g, material, rectangle.section(), 4, tip_force=0)
    case = TransientConfig(
        grid=TimeGrid(duration=0.1, time_step=0.0005),
        damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
        loads=(PulseForce(node=4, end_time=0.04), StepForce(node=3, dof=DOF.RZ, amplitude=0.1)),
        responses=(ResponseDOF(node=2), ResponseDOF(node=4), ResponseDOF(node=4, dof=DOF.RZ)),
    )
    result = solve_transient(model, case)
    assembly = assemble(model)
    c = case.damping.alpha * assembly.mass + case.damping.beta * assembly.stiffness
    balance = (
        result.acceleration @ assembly.mass
        + result.velocity @ c
        + result.displacement @ assembly.stiffness
        - result.force_right
    )
    assert_allclose(balance[:, assembly.free], 0, atol=1e-7)
    assert_allclose(balance[:, assembly.fixed], result.reactions, rtol=1e-12, atol=1e-12)
    for history in (result.displacement, result.velocity, result.acceleration):
        assert_allclose(history[:, assembly.fixed], 0, atol=0)
    assert result.response_displacement.shape == (201, 3)
    assert_allclose(result.response_displacement[:, 1], result.displacement[:, 13])
    assert result.relative_energy_error < 1e-8


def test_zero_force_and_load_on_supported_dof() -> None:
    model, _, _ = guided_beam()
    for loads in ((), (StepForce(node=0, amplitude=2),)):
        result = solve_transient(
            model, TransientConfig(loads=loads, responses=(ResponseDOF(node=1),))
        )
        for history in (
            result.displacement,
            result.velocity,
            result.acceleration,
            result.kinetic_energy,
            result.strain_energy,
            result.external_work,
            result.damping_dissipation,
        ):
            assert_allclose(history, 0, atol=0)
        assert result.relative_energy_error == 0
        if loads:
            assert_allclose(result.reactions[:, result.constrained_indices.index(1)], -2, atol=0)


def test_numerical_report_time_and_mesh_convergence() -> None:
    report = transient_verification_report()
    assert report["passed"]
    assert not report["experimental_validation"]
    assert not report["ansys_correlation"]


@pytest.mark.parametrize(
    "grid",
    [
        {"duration": -1},
        {"time_step": 0},
        {"duration": 0.1, "time_step": 0.03},
        {"duration": 1, "time_step": 1e-8},
        {"duration": float("inf")},
    ],
)
def test_invalid_time_grid(grid: dict[str, float]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        TimeGrid.model_validate(grid)


@pytest.mark.parametrize(
    "data",
    [
        {"times": (0, 0.1), "values": (0,)},
        {"times": (0, 0), "values": (0, 1)},
        {"times": (0.01, 0.1), "values": (0, 1)},
        {"times": (0, 0.1), "values": (0, float("nan"))},
    ],
)
def test_invalid_sampled_input(data: dict[str, tuple[float, ...]]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        SampledForce.model_validate({"node": 1} | data)


def test_invalid_nodes_initial_constraints_and_events() -> None:
    model, _, _ = guided_beam()
    changes: list[dict[str, object]] = [
        {"loads": (StepForce(node=99),)},
        {"responses": (ResponseDOF(node=99),)},
        {"initial_displacement": (InitialValue(node=99, value=1),)},
        {"initial_displacement": (InitialValue(node=0, value=1),)},
        {"initial_velocity": (InitialValue(node=0, value=1),)},
    ]
    for change in changes:
        case = TransientConfig(**(scalar_config().model_dump() | change))
        with pytest.raises(EngineeringError):
            solve_transient(model, case)
    invalid_changes: list[dict[str, object]] = [
        {"loads": (StepForce(node=1, start_time=0.010025),)},
        {"loads": (PulseForce(node=1, end_time=0.013375),)},
        {"loads": (SampledForce(node=1, times=(0, 0.1), values=(0, 1)),)},
        {"initial_velocity": (InitialValue(node=1, value=1), InitialValue(node=1, value=2))},
        {"responses": (ResponseDOF(node=1),) * 2},
    ]
    for change in invalid_changes:
        with pytest.raises((ValidationError, EngineeringError)):
            TransientConfig(**(scalar_config().model_dump() | change))
    with pytest.raises((ValidationError, EngineeringError)):
        PulseForce(node=1, start_time=1, end_time=0.5)
    with pytest.raises(UnstableModelError):
        solve_transient(FrameModel(**(model.model_dump() | {"constraints": ()})), scalar_config())


def test_report_decimates_only_output_and_retains_original_force_samples() -> None:
    model, _, _ = guided_beam()
    case = TransientConfig(
        **(
            scalar_config().model_dump()
            | {
                "loads": (SampledForce(node=1, times=(0, 0.05, 0.2), values=(0, 1, 0)),),
            }
        )
    )
    result = solve_transient(model, case)
    report = json.loads(transient_report(model, case, result, max_samples=41))
    values = report["results"]
    assert values["output_sampling"]["exported_samples"] == 41
    assert values["output_sampling"]["integration_samples"] == 4001
    assert values["time_s"][0] == 0 and values["time_s"][-1] == 0.2
    assert report["inputs"]["transient"]["loads"][0]["times"] == [0, 0.05, 0.2]
    assert (
        values["numerical_verification"]["relative_energy_balance_error_full_grid"]
        == result.relative_energy_error
    )
    assert values["numerical_verification"]["experimental_validation"] is False
    assert len(values["support_reactions"]["force_N_or_Nm"]) == 41
    for invalid in (0, 1, 5002, True):
        with pytest.raises(ValueError):
            transient_report(model, case, result, max_samples=invalid)


def test_force_limit_conventions_and_numerical_resolution_warnings() -> None:
    grid = TimeGrid(duration=0.02, time_step=0.001)
    pulse = PulseForce(node=1, amplitude=2, start_time=0.002, end_time=0.004, shape="rectangular")
    right, left = force_limits(pulse, grid.times())
    assert_allclose(right[1:6], [0, 2, 2, 0, 0])
    assert_allclose(left[1:6], [0, 0, 2, 2, 0])
    model, _, _ = guided_beam()
    result = solve_transient(
        model, TransientConfig(grid=grid, loads=(pulse,), responses=(ResponseDOF(node=1),))
    )
    assert any("Pulse" in warning for warning in result.numerical_warnings)


def test_invalid_mass_and_resource_limits_are_not_silently_regularized() -> None:
    from vibra.solvers.transient import _factor

    for matrix in (np.zeros((2, 2)), np.array([[1.0, 1.0], [1.0, 1.0]])):
        with pytest.raises(SolverError):
            _factor(matrix, 1e-12, "test")
    with pytest.raises(SolverError, match="conditioned"):
        _factor(np.array([[1.0, 1 - 1e-14], [1 - 1e-14, 1.0]]), 1e-12, "test")
    g, material, rectangle = steel_case()
    large = cantilever(g, material, rectangle.section(), 16, tip_force=0)
    with pytest.raises(EngineeringError, match="time×DOF"):
        solve_transient(
            large,
            TransientConfig(
                grid=TimeGrid(duration=1, time_step=0.00002), responses=(ResponseDOF(node=16),)
            ),
        )


def test_physical_deformation_and_animation_use_solved_states() -> None:
    from vibra.visualization.transient import (
        energy_history,
        response_history,
        transient_animation,
        transient_shape,
    )

    g, m, r = steel_case()
    model = cantilever(g, m, r.section(), 2, tip_force=0)
    result = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.02, time_step=0.001),
            loads=(StepForce(node=2),),
            responses=(ResponseDOF(node=2),),
        ),
    )
    figure = transient_shape(model, result, 10, scale=3)
    assert_allclose(figure.data[3].y[-1], result.displacement[10, -2] * 3, atol=1e-13)
    animation = transient_animation(model, result, scale=3, max_frames=3)
    assert len(animation.frames) == 3
    assert_allclose(animation.frames[1].data[-1].y[-1], result.displacement[10, -2] * 3, atol=1e-13)
    assert len(response_history(result).data) == 3
    assert len(energy_history(result).data) == 6


@pytest.mark.parametrize(
    "load",
    [
        PulseForce(node=1, end_time=0.01),
        HarmonicForce(node=1, frequency_hz=100),
        SampledForce(node=1, times=(0, 0.001, 0.002, 0.1), values=(0, 1, 0, 0)),
    ],
)
def test_unrepresented_nonzero_forcing_is_rejected(
    load: StepForce | HarmonicForce | PulseForce | SampledForce,
) -> None:
    model, _, _ = guided_beam()
    case = TransientConfig(
        grid=TimeGrid(duration=0.1, time_step=0.01), loads=(load,), responses=(ResponseDOF(node=1),)
    )
    with pytest.raises(EngineeringError):
        solve_transient(model, case)
