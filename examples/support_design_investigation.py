"""Reproduce the support challenge with actual FEM and modal solves."""

from pathlib import Path

from vibra.io.reports import engineering_report
from vibra.studies.investigation import (
    ChallengeInputs,
    calculate_design,
    challenge_explanation,
    compare_designs,
    comparison_rows,
)
from vibra.visualization.investigation import comparison_viewport
from vibra.visualization.theme import themed_figure


def main() -> None:
    comparison = compare_designs(calculate_design(), calculate_design(ChallengeInputs(depth_mm=24)))
    if not comparison.passed:
        raise RuntimeError("The independently feasible 24 mm design did not meet both targets.")
    output = Path("artifacts/support-investigation")
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(
        engineering_report(
            "Depth-only support challenge",
            dict(
                baseline=comparison.baseline.shelf.inputs,
                candidate=comparison.candidate.shelf.inputs,
            ),
            dict(
                comparison=comparison,
                table=comparison_rows(comparison),
                interpretation=challenge_explanation(comparison),
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    figure = comparison_viewport(comparison)
    for theme in ("Light", "Dark"):
        themed_figure(figure, theme).write_html(
            output / f"comparison-{theme.lower()}.html",
            include_plotlyjs=True,
        )
    for line in challenge_explanation(comparison):
        print(line)
    print(
        f"A: {comparison.baseline.max_downward_m * 1000:.9f} mm, "
        f"{comparison.baseline.mass_kg:.6f} kg; "
        f"B: {comparison.candidate.max_downward_m * 1000:.9f} mm, "
        f"{comparison.candidate.mass_kg:.6f} kg, "
        f"{comparison.candidate.max_bending_stress_Pa / 1e6:.9f} MPa"
    )


if __name__ == "__main__":
    main()
