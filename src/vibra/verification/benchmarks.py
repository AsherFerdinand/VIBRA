"""Reproducible steel beam convergence and SDOF verification report."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import AnalysisConfig, Material, Rectangle
from vibra.dynamics.sdof import SDOFConfig, solve_sdof
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.analytical import (
    cantilever_bending_hz,
    cantilever_tip,
    underdamped_free,
)


def steel_case() -> tuple[BeamGeometry, Material, Rectangle]:
    return (
        BeamGeometry(length=1.0),
        Material(name="Illustrative steel", young_modulus=210e9, density=7850),
        Rectangle(width=0.02, height=0.02),
    )


def convergence_study(
    geometry: BeamGeometry | None = None,
    material: Material | None = None,
    rectangle: Rectangle | None = None,
) -> list[dict[str, Any]]:
    defaults = steel_case()
    geometry = geometry or defaults[0]
    material = material or defaults[1]
    rectangle = rectangle or defaults[2]
    section = rectangle.section()
    exact = cantilever_bending_hz(geometry, material, section)
    rows = []
    for count in (2, 4, 8, 16, 32):
        model = cantilever(geometry, material, section, count)
        modal = solve_modal(model, AnalysisConfig(modes=min(10, 3 * count)))
        bending = modal.frequencies_hz[np.array(modal.families) == "bending"][:3]
        static = solve_static(model)
        displacement, rotation = cantilever_tip(geometry, material, section, -100)
        rows.append(
            {
                "elements": count,
                "bending_hz": bending.tolist(),
                "relative_frequency_errors": (np.abs(bending - exact) / exact).tolist(),
                "tip_displacement_m": float(static.displacement[-1, 1]),
                "tip_rotation_rad": float(static.displacement[-1, 2]),
                "relative_tip_error": abs(static.displacement[-1, 1] / displacement - 1),
                "relative_rotation_error": abs(static.displacement[-1, 2] / rotation - 1),
                "reaction_y_N": float(static.reactions[0, 1]),
                "reaction_moment_Nm": float(static.reactions[0, 2]),
            }
        )
    return rows


def verification_report() -> dict[str, Any]:
    geometry, material, rectangle = steel_case()
    rows = convergence_study()
    sdof_checks = []
    for damping in (0.0, 0.8):
        config = SDOFConfig(mass=2, stiffness=200, damping=damping, initial_velocity=0.03)
        result = solve_sdof(config)
        exact = underdamped_free(config, result.time)
        error = float(np.max(np.abs(result.displacement - exact)))
        energy_error = float(np.max(np.abs(result.energy / result.energy[0] - 1)))
        max_increase = float(np.max(np.diff(result.energy)))
        passed = error < 1e-9 and (energy_error < 1e-8 if damping == 0 else max_increase < 1e-10)
        sdof_checks.append(
            {
                "damping_Ns_per_m": damping,
                "max_displacement_error_m": error,
                "max_relative_energy_change": energy_error,
                "max_energy_increment_J": max_increase,
                "passed": passed,
            }
        )
    frequency_errors = np.array([row["relative_frequency_errors"] for row in rows])
    checks = {
        "static_tip_and_rotation": all(
            row["relative_tip_error"] < 1e-7 and row["relative_rotation_error"] < 1e-7
            for row in rows
        ),
        "reaction_equilibrium": all(
            abs(row["reaction_y_N"] - 100) < 1e-5 and abs(row["reaction_moment_Nm"] - 100) < 1e-5
            for row in rows
        ),
        "modal_32_element_error_below_0_01_percent": bool(np.max(frequency_errors[-1]) < 1e-4),
        "modal_monotonic_convergence": bool(np.all(np.diff(frequency_errors, axis=0) < 0)),
        "sdof_analytical_and_energy": all(check["passed"] for check in sdof_checks),
    }
    return {
        "schema_version": "1.0",
        "kind": "analytical numerical verification",
        "experimental_validation": False,
        "inputs": {
            "geometry": geometry.model_dump(),
            "material": material.model_dump(),
            "rectangle": rectangle.model_dump(),
            "tip_force_N": -100,
        },
        "analytical_bending_hz": cantilever_bending_hz(
            geometry, material, rectangle.section()
        ).tolist(),
        "convergence": rows,
        "sdof": sdof_checks,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification.json"))
    args = parser.parse_args()
    report = verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "checks": report["checks"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
