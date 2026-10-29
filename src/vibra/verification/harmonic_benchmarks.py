"""Independent harmonic verification report, executable in CI and installed wheels."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from vibra.core.mesh import cantilever
from vibra.core.models import DOF, Constraint, FrameModel
from vibra.solvers.harmonic import (
    Damping,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.solvers.static import solve_static
from vibra.verification.analytical import cantilever_bending_hz
from vibra.verification.benchmarks import steel_case
from vibra.verification.harmonic_analytical import (
    continuum_cantilever_compliance,
    sdof_receptance,
)


def guided_beam() -> tuple[FrameModel, float, float]:
    """One free transverse DOF: known m=156ρAL/420, k=12EI/L³."""
    geometry, material, rectangle = steel_case()
    model = cantilever(geometry, material, rectangle.section(), 1, tip_force=0)
    constraints = (
        *model.constraints,
        Constraint(node=1, dof=DOF.UX),
        Constraint(node=1, dof=DOF.RZ),
    )
    constrained = FrameModel(**(model.model_dump() | {"constraints": constraints}))
    stiffness = 12 * material.young_modulus * rectangle.section().second_moment / geometry.length**3
    mass = 156 * material.density * rectangle.section().area * geometry.length / 420
    return constrained, mass, stiffness


def harmonic_verification_report() -> dict[str, Any]:
    guided, mass, stiffness = guided_beam()
    natural = float(np.sqrt(stiffness / mass) / (2 * np.pi))
    frequencies = tuple(natural * factor for factor in (0, 0.5, 1, 1.5, 2))
    damping = Damping(kind="rayleigh", alpha=2, beta=2e-5)
    scalar_config = HarmonicConfig(
        frequencies_hz=frequencies,
        damping=damping,
        loads=(HarmonicLoad(node=1, amplitude=1, phase_degrees=23),),
        responses=(ResponseDOF(node=1),),
    )
    scalar = solve_harmonic(guided, scalar_config)
    reference = sdof_receptance(
        mass, stiffness, damping.alpha * mass + damping.beta * stiffness, frequencies
    ) * np.exp(1j * np.deg2rad(23))
    scalar_error = float(np.max(np.abs(scalar.displacement[:, 4] / reference - 1)))
    phase_error = float(np.max(np.abs(np.angle(scalar.displacement[:, 4] / reference))))

    geometry, material, rectangle = steel_case()
    analytical_frequency = float(cantilever_bending_hz(geometry, material, rectangle.section())[0])
    off_peak_frequencies = tuple(
        analytical_frequency * ratio for ratio in (0.1, 0.7, 0.95, 1.05, 1.5)
    )
    continuum = continuum_cantilever_compliance(
        geometry, material, rectangle.section(), off_peak_frequencies, damping.alpha, damping.beta
    )
    rows = []
    for count in (2, 4, 8, 16, 32):
        model = cantilever(geometry, material, rectangle.section(), count, tip_force=1)
        config = HarmonicConfig(
            frequencies_hz=off_peak_frequencies,
            damping=damping,
            loads=(HarmonicLoad(node=count, amplitude=1),),
            responses=(ResponseDOF(node=count),),
        )
        result = solve_harmonic(model, config)
        tip = result.displacement[:, -2]
        rows.append(
            {
                "elements": count,
                "max_relative_complex_compliance_error": float(np.max(np.abs(tip / continuum - 1))),
                "max_phase_error_radians": float(np.max(np.abs(np.angle(tip / continuum)))),
                "first_natural_hz": float(result.natural_frequencies_hz[0]),
                "max_backward_error": float(result.backward_errors.max()),
            }
        )
    model = cantilever(geometry, material, rectangle.section(), 16, tip_force=1)
    static = solve_static(model)
    low_config = HarmonicConfig(
        frequencies_hz=(0, analytical_frequency * 1e-3),
        damping=damping,
        loads=(HarmonicLoad(node=16, amplitude=1),),
        responses=(ResponseDOF(node=16),),
    )
    low = solve_harmonic(model, low_config)
    static_error = float(abs(low.displacement[0, -2] / static.displacement[-1, 1] - 1))
    low_error = float(abs(low.displacement[1, -2] / static.displacement[-1, 1] - 1))
    grid = tuple(
        float(f) for f in np.linspace(0.9 * analytical_frequency, 1.1 * analytical_frequency, 401)
    )
    resonant = solve_harmonic(
        model,
        HarmonicConfig(
            frequencies_hz=grid,
            damping=damping,
            loads=(HarmonicLoad(node=16, amplitude=1),),
            responses=(ResponseDOF(node=16),),
        ),
    )
    peak = resonant.sampled_maxima[0]
    peak_error = abs(peak.frequency_hz / analytical_frequency - 1)
    # At the same undamped natural frequency, increasing alpha lowers response.
    damping_amplitudes = []
    for alpha in (0.5, 2, 8):
        response = solve_harmonic(
            model,
            HarmonicConfig(
                frequencies_hz=(float(resonant.natural_frequencies_hz[0]),),
                damping=Damping(kind="mass", alpha=alpha),
                loads=(HarmonicLoad(node=16, amplitude=1),),
                responses=(ResponseDOF(node=16),),
            ),
        )
        damping_amplitudes.append(float(response.response_amplitude[0, 0]))
    checks = {
        "sdof_complex_receptance": scalar_error < 1e-10,
        "sdof_phase": phase_error < 1e-10,
        "zero_frequency_matches_static": static_error < 1e-8,
        "low_frequency_static_limit": low_error < 1e-4,
        "continuum_mesh_convergence": all(
            a["max_relative_complex_compliance_error"] > b["max_relative_complex_compliance_error"]
            for a, b in zip(rows[:-1], rows[1:], strict=True)
        ),
        "continuum_32_elements_below_1e_minus_5": rows[-1]["max_relative_complex_compliance_error"]
        < 1e-5,
        "first_sampled_peak_within_0_1_percent": peak_error < 1e-3,
        "damping_reduces_response_at_natural_frequency": bool(
            np.all(np.diff(damping_amplitudes) < 0)
        ),
    }
    return {
        "schema_version": "1.0",
        "kind": "Independent analytical harmonic verification",
        "experimental_validation": False,
        "ansys_correlation": False,
        "inputs": {
            "geometry": geometry.model_dump(),
            "material": material.model_dump(),
            "rectangle": rectangle.model_dump(),
            "damping": damping.model_dump(),
            "off_peak_frequencies_hz": off_peak_frequencies,
            "unit_tip_force_N": 1,
        },
        "sdof_max_relative_complex_error": scalar_error,
        "sdof_max_phase_error_rad": phase_error,
        "zero_frequency_relative_static_error": static_error,
        "low_frequency_relative_static_error": low_error,
        "analytical_first_bending_hz": analytical_frequency,
        "sampled_peak_hz": peak.frequency_hz,
        "sampled_peak_relative_frequency_error": peak_error,
        "damping_alpha_values_per_s": [0.5, 2, 8],
        "damping_tip_amplitudes_m": damping_amplitudes,
        "mesh_convergence": rows,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/harmonic-verification.json"))
    args = parser.parse_args()
    report = harmonic_verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "checks": report["checks"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
