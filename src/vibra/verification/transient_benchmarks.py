"""Reproducible Newmark, continuous-time SDOF, continuum FEM and energy checks."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.mesh import cantilever
from vibra.dynamics.forcing import HarmonicForce, PulseForce, StepForce
from vibra.solvers.transient import InitialValue, TimeGrid, TransientConfig, solve_transient
from vibra.verification.benchmarks import steel_case
from vibra.verification.harmonic_benchmarks import guided_beam
from vibra.verification.transient_analytical import (
    continuum_pulse_tip,
    forced_cosine_sdof,
    free_sdof,
)


def transient_verification_report() -> dict[str, Any]:
    model, mass, stiffness = guided_beam()
    rows = []
    for step in (0.001, 0.0005, 0.00025, 0.000125, 0.0000625):
        config = TransientConfig(
            grid=TimeGrid(duration=0.2, time_step=step),
            responses=(ResponseDOF(node=1),),
            initial_displacement=(InitialValue(node=1, value=0.001),),
            initial_velocity=(InitialValue(node=1, value=0.01),),
        )
        result = solve_transient(model, config)
        exact, _, _ = free_sdof(result.time, mass, stiffness, 0, 0.001, 0.01)
        rows.append(
            {
                "time_step_s": step,
                "relative_max_displacement_error": float(
                    np.max(np.abs(result.displacement[:, 4] - exact)) / np.max(np.abs(exact))
                ),
                "relative_energy_balance_error": result.relative_energy_error,
                "max_backward_error": float(result.backward_errors.max()),
            }
        )
    forced_config = TransientConfig(
        grid=TimeGrid(duration=0.2, time_step=0.0001),
        damping=Damping(kind="mass", alpha=8),
        loads=(HarmonicForce(node=1, amplitude=1, frequency_hz=15),),
        responses=(ResponseDOF(node=1),),
    )
    forced = solve_transient(model, forced_config)
    forced_exact, _, _ = forced_cosine_sdof(
        forced.time, mass, stiffness, 8 * mass, 1, 2 * np.pi * 15
    )
    forced_error = float(
        np.max(np.abs(forced.displacement[:, 4] - forced_exact)) / np.max(np.abs(forced_exact))
    )
    damped_config = TransientConfig(
        **(
            forced_config.model_dump()
            | {
                "loads": (),
                "initial_displacement": (InitialValue(node=1, value=0.001),),
            }
        )
    )
    damped = solve_transient(model, damped_config)
    damped_exact, _, _ = free_sdof(damped.time, mass, stiffness, 8 * mass, 0.001, 0)
    damped_error = float(np.max(np.abs(damped.displacement[:, 4] - damped_exact)) / 0.001)

    g, material, rectangle = steel_case()
    grid = TimeGrid(duration=0.12, time_step=0.00001)
    reference = continuum_pulse_tip(grid.times(), g, material, rectangle.section())
    shorter_reference = continuum_pulse_tip(
        grid.times(), g, material, rectangle.section(), modes=96
    )
    reference_scale = float(np.max(np.abs(reference)))
    truncation = float(np.max(np.abs(reference - shorter_reference)) / reference_scale)
    meshes = []
    for count in (2, 4, 8):
        frame = cantilever(g, material, rectangle.section(), count, tip_force=0)
        result = solve_transient(
            frame,
            TransientConfig(
                grid=grid,
                loads=(PulseForce(node=count, end_time=0.04),),
                responses=(ResponseDOF(node=count),),
            ),
        )
        meshes.append(
            {
                "elements": count,
                "relative_max_tip_error": float(
                    np.max(np.abs(result.displacement[:, -2] - reference)) / reference_scale
                ),
                "relative_energy_balance_error": result.relative_energy_error,
            }
        )
    equilibrium = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.2, time_step=0.0005),
            loads=(StepForce(node=1, amplitude=1),),
            responses=(ResponseDOF(node=1),),
            initial_displacement=(InitialValue(node=1, value=1 / stiffness),),
        ),
    )
    equilibrium_error = float(np.max(np.abs(equilibrium.displacement[:, 4] * stiffness - 1)))
    zero = solve_transient(model, TransientConfig(responses=(ResponseDOF(node=1),)))
    checks = {
        "static_equilibrium": equilibrium_error < 1e-10,
        "zero_force_response": bool(
            np.all(zero.displacement == 0)
            and np.all(zero.velocity == 0)
            and np.all(zero.acceleration == 0)
        ),
        "constraint_consistency": bool(
            np.all(forced.displacement[:, forced.constrained_indices] == 0)
        ),
        "undamped_free_response": rows[-1]["relative_max_displacement_error"] < 0.0005,
        "second_order_time_convergence": all(
            3.5 < a["relative_max_displacement_error"] / b["relative_max_displacement_error"] < 4.5
            for a, b in zip(rows[:-1], rows[1:], strict=True)
        ),
        "undamped_energy_conservation": all(
            row["relative_energy_balance_error"] < 1e-9 for row in rows
        ),
        "damped_analytical_decay": damped_error < 0.001,
        "damped_energy_balance": damped.relative_energy_error < 1e-9,
        "damped_energy_monotonic": bool(
            np.max(np.diff(damped.kinetic_energy + damped.strain_energy)) < 1e-12
        ),
        "forced_sdof_transient": forced_error < 0.001,
        "forced_energy_balance": forced.relative_energy_error < 1e-9,
        "continuum_series_truncation": truncation < 1e-7,
        "fem_mesh_convergence": all(
            a["relative_max_tip_error"] > b["relative_max_tip_error"]
            for a, b in zip(meshes[:-1], meshes[1:], strict=True)
        ),
        "eight_element_continuum_error": meshes[-1]["relative_max_tip_error"] < 0.002,
    }
    return {
        "schema_version": "1.0",
        "method": "Newmark beta=1/4 gamma=1/2",
        "verification_kind": "Independent analytical numerical verification",
        "experimental_validation": False,
        "ansys_correlation": False,
        "sdof_inputs": {"mass_kg": mass, "stiffness_N_per_m": stiffness},
        "static_equilibrium_relative_error": equilibrium_error,
        "time_convergence": rows,
        "damped_relative_max_displacement_error": damped_error,
        "forced_relative_max_displacement_error": forced_error,
        "damped_relative_energy_error": damped.relative_energy_error,
        "forced_relative_energy_error": forced.relative_energy_error,
        "continuum_inputs": {
            "geometry": g.model_dump(),
            "material": material.model_dump(),
            "section": rectangle.section().model_dump(),
            "grid": grid.model_dump(),
            "unit_tip_half_sine_pulse_width_s": 0.04,
            "continuum_modes": 128,
        },
        "continuum_96_to_128_modes_relative_difference": truncation,
        "mesh_convergence": meshes,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/transient-verification.json")
    )
    args = parser.parse_args()
    report = transient_verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "checks": report["checks"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
