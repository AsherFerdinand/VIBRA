"""Depth-only support investigation, composing the verified static/modal solvers.

No strength criterion is evaluated. Percentages compare calculated designs, not
continuum formula predictions. The analytical feasibility check is independent.
"""

from dataclasses import dataclass

import numpy as np
from pydantic import Field

from vibra.core.models import AnalysisConfig, EngineeringModel
from vibra.postprocessing.beam import sample_beam
from vibra.solvers.modal import ModalResult, solve_modal
from vibra.studies.beginner import ShelfExample, ShelfInputs, run_shelf
from vibra.studies.installed import InstalledStudy


class ChallengeInputs(EngineeringModel):
    depth_mm: float = Field(default=20, ge=20, le=28)


@dataclass(frozen=True)
class CalculatedDesign:
    shelf: ShelfExample
    modal: ModalResult
    mass_kg: float
    max_displacement_m: float
    max_downward_m: float
    max_bending_stress_Pa: float

    @property
    def first_frequency_hz(self) -> float:
        return float(self.modal.frequencies_hz[0])


@dataclass(frozen=True)
class DesignComparison:
    baseline: CalculatedDesign
    candidate: CalculatedDesign
    displacement_reduction_percent: float
    mass_increase_percent: float
    displacement_pass: bool
    mass_pass: bool

    @property
    def passed(self) -> bool:
        return self.displacement_pass and self.mass_pass


def feasible_depth_interval_mm() -> tuple[float, float]:
    """For fixed E,L,b,F: delta~h^-3 and mass~h; 40% less delta, <=20% more mass."""
    return 20 / 0.6 ** (1 / 3), 20 * 1.2


def calculate_design(inputs: ChallengeInputs | None = None) -> CalculatedDesign:
    inputs = inputs or ChallengeInputs()
    shelf = run_shelf(ShelfInputs(thickness_mm=inputs.depth_mm))
    modal = solve_modal(shelf.model, AnalysisConfig(modes=1))
    nodes = {node.id: node for node in shelf.model.nodes}
    mass = sum(
        element.material.density
        * element.section.area
        * np.hypot(
            nodes[element.nodes[1]].x - nodes[element.nodes[0]].x,
            nodes[element.nodes[1]].y - nodes[element.nodes[0]].y,
        )
        for element in shelf.model.elements
    )
    fields = sample_beam(shelf.model, shelf.result.displacement)
    return CalculatedDesign(
        shelf,
        modal,
        float(mass),
        max(float(np.linalg.norm(field.displacement_m, axis=1).max()) for field in fields),
        max(0.0, max(float(-field.displacement_m[:, 1].min()) for field in fields)),
        max(float(abs(section.bending_top_Pa).max()) for section in shelf.stress.sections),
    )


def compare_designs(baseline: CalculatedDesign, candidate: CalculatedDesign) -> DesignComparison:
    """Evaluate the fixed challenge; reject comparisons that change another input.

    A tolerance of 1e-7 percentage points only accommodates floating-point roundoff
    at inclusive boundaries. It is not a design allowance or uncertainty estimate.
    """
    if baseline.shelf.inputs != ShelfInputs():
        raise ValueError("Challenge A must be the fixed 20 mm, 1 m, 100 N baseline.")
    b = candidate.shelf.inputs
    ChallengeInputs(depth_mm=b.thickness_mm)
    if b.length_m != 1 or b.load_N != 100:
        raise ValueError("Change depth only; retain length, material, width and force.")
    reduction = 100 * (1 - candidate.max_downward_m / baseline.max_downward_m)
    increase = 100 * (candidate.mass_kg / baseline.mass_kg - 1)
    return DesignComparison(
        baseline, candidate, reduction, increase, reduction >= 40 - 1e-7, increase <= 20 + 1e-7
    )


def comparison_rows(comparison: DesignComparison) -> list[dict[str, str | float]]:
    a, b = comparison.baseline, comparison.candidate
    quantities = (
        ("Length [m]", a.shelf.inputs.length_m, b.shelf.inputs.length_m),
        ("Width [mm]", 20.0, 20.0),
        ("Depth [mm]", a.shelf.inputs.thickness_mm, b.shelf.inputs.thickness_mm),
        ("Mass [kg]", a.mass_kg, b.mass_kg),
        ("Max translation (sampled) [mm]", a.max_displacement_m * 1e3, b.max_displacement_m * 1e3),
        ("Max downward movement [mm]", a.max_downward_m * 1e3, b.max_downward_m * 1e3),
        (
            "Max |section normal stress| [MPa]",
            abs(a.shelf.stress.critical_absolute.normal_stress_Pa) / 1e6,
            abs(b.shelf.stress.critical_absolute.normal_stress_Pa) / 1e6,
        ),
        (
            "Max |bending stress| [MPa]",
            a.max_bending_stress_Pa / 1e6,
            b.max_bending_stress_Pa / 1e6,
        ),
        ("First natural frequency [Hz]", a.first_frequency_hz, b.first_frequency_hz),
    )
    return [
        {
            "Quantity": label,
            "A · saved baseline": av,
            "B · submitted design": bv,
            "Change B/A [%]": 100 * (bv / av - 1),
        }
        for label, av, bv in quantities
    ]


def challenge_explanation(comparison: DesignComparison) -> tuple[str, str, str]:
    b = comparison.candidate
    stress_reduction = 100 * (
        1 - b.max_bending_stress_Pa / comparison.baseline.max_bending_stress_Pa
    )
    status = (
        "Both requirements are met" if comparison.passed else "Both requirements are not yet met"
    )
    return (
        f"Design B reduces downward movement by {comparison.displacement_reduction_percent:.3f}% "
        f"and changes beam mass by {comparison.mass_increase_percent:+.3f}%. "
        f"{status} in this linear beam model.",
        "For this fixed rectangular beam, I=b·h³/12 while mass=ρ·b·h·L. Depth therefore "
        "changes bending stiffness faster than mass. Bending stress scales with h⁻², "
        f"not h⁻³: the calculated peak bending stress reduction is {stress_reduction:.3f}%.",
        "Try a depth near the two requirement boundaries. Lower displacement alone is "
        "not an overall optimum. These movement/mass targets do not check strength, "
        "buckling, fatigue, connections or real-world safety.",
    )


def motor_comparison_rows(study: InstalledStudy) -> list[dict[str, str | float]]:
    """Compare amplitudes at the actual solved operating-frequency sample.

    Relative harmonic motion is the magnitude of the *complex difference*, not
    the difference of magnitudes. Bare/rigid sites have zero reference-node gap.
    """
    rows: list[dict[str, str | float]] = []
    for case in study.cases:
        op = int(np.argmin(abs(case.harmonic.frequencies_hz - study.config.operating_hz)))
        u = case.harmonic.displacement[op]
        relative = u[3 * case.force_node + 1] - u[3 * study.config.elements + 1]
        rows.append(
            {
                "Configuration": case.topology,
                "First natural [Hz]": float(case.modal.frequencies_hz[0]),
                "Static interface |Y| [mm]": case.summary["static_interface_displacement_m"] * 1e3,
                "Harmonic interface amplitude [mm]": abs(u[3 * case.force_node + 1]) * 1e3,
                "Motor–rail relative Y amplitude [mm]": abs(relative) * 1e3,
                "Interface phase [deg]": float(np.rad2deg(np.angle(u[3 * case.force_node + 1]))),
                "Root force / input [%]": 100 * case.summary["operating_root_force_ratio"],
            }
        )
    return rows
