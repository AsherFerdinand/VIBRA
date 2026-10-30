"""Independent cantilever/axial stress equations and rotated-coordinate checks."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import FrameModel, Material, NodalLoad, Node, Rectangle
from vibra.postprocessing.beam import recover_stress
from vibra.solvers.static import solve_static


def stress_case(
    angle_degrees: float = 0, axial: float = 20000, transverse: float = -100
) -> FrameModel:
    model = cantilever(
        BeamGeometry(length=1),
        Material(young_modulus=210e9, density=7850),
        Rectangle(width=0.02, height=0.02).section(),
        8,
        tip_force=0,
    )
    angle = np.deg2rad(angle_degrees)
    c, s = float(np.cos(angle)), float(np.sin(angle))
    return FrameModel(
        **(
            model.model_dump()
            | dict(
                nodes=tuple(Node(id=node.id, x=c * node.x, y=s * node.x) for node in model.nodes),
                loads=(
                    NodalLoad(node=8, fx=c * axial - s * transverse, fy=s * axial + c * transverse),
                ),
            )
        )
    )


def verification_report() -> dict[str, Any]:
    checks = []
    for angle in (0.0, 37.0, 90.0, 180.0):
        model = stress_case(angle)
        result = solve_static(model)
        stress = recover_stress(model, result.displacement)
        area = 0.02 * 0.02
        inertia = 0.02 * 0.02**3 / 12
        c = 0.01
        reference_scale = 125e6
        errors: list[float] = []
        for i, item in enumerate(stress.sections):
            x = i / 8 + item.field.local_x_m
            n = np.full_like(x, 20000.0)
            v = np.full_like(x, 100.0)
            moment = -100 * (1 - x)
            errors.extend(
                (
                    float(np.max(abs(item.axial_Pa - n / area))) / reference_scale,
                    float(np.max(abs(item.combined_top_Pa - (n / area - moment * c / inertia))))
                    / reference_scale,
                    float(np.max(abs(item.combined_bottom_Pa - (n / area + moment * c / inertia))))
                    / reference_scale,
                    float(np.max(abs(item.field.shear_force_N - v))) / 100,
                )
            )
        maximum = max(errors)
        checks.append(
            dict(
                name=f"combined_cantilever_rotated_{angle:g}_deg",
                relative_error=maximum,
                tolerance=1e-8,
                passed=maximum < 1e-8,
                maximum_tension_Pa=stress.maximum_normal_Pa,
                maximum_compression_Pa=stress.minimum_normal_Pa,
                critical_global_x_m=stress.critical_absolute.global_x_m,
                critical_global_y_m=stress.critical_absolute.global_y_m,
            )
        )
    for axial, transverse, name, exact in (
        (0.0, -100.0, "pure_bending", 75e6),
        (20000.0, 0.0, "pure_axial", 50e6),
    ):
        model = stress_case(axial=axial, transverse=transverse)
        stress = recover_stress(model, solve_static(model).displacement)
        error = abs(stress.maximum_normal_Pa / exact - 1)
        checks.append(dict(name=name, relative_error=error, tolerance=1e-8, passed=error < 1e-8))
    return dict(
        analysis="Elastic beam section stress verification",
        definition="sigma_xx=N/A-M*y/I; tension positive; prismatic symmetric +/-c fibers",
        experimental_validation=False,
        solid_or_contact_stress=False,
        checks=checks,
        all_passed=all(row["passed"] for row in checks),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/stress-verification.json"))
    args = parser.parse_args()
    report = verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
