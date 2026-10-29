"""Generate actual steel cantilever results and standalone interactive plots."""

from pathlib import Path

import numpy as np

from vibra.core.mesh import cantilever
from vibra.core.models import AnalysisConfig
from vibra.io.reports import engineering_report
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.benchmarks import convergence_study, steel_case
from vibra.visualization.plots import beam_shape, bending_moment, convergence_plot


def main() -> None:
    output = Path("artifacts/steel-cantilever")
    output.mkdir(parents=True, exist_ok=True)
    geometry, material, rectangle = steel_case()
    model = cantilever(geometry, material, rectangle.section(), elements=16)
    static = solve_static(model)
    modal = solve_modal(model, AnalysisConfig(modes=8))
    convergence = convergence_study()
    (output / "report.json").write_text(
        engineering_report(
            "Steel cantilever",
            model,
            {"static": static, "modal": modal, "convergence": convergence},
        )
        + "\n"
    )
    beam_shape(model, static.displacement, scale=10).write_html(
        output / "static.html", include_plotlyjs=True
    )
    bending_moment(model, static).write_html(output / "moment.html", include_plotlyjs=True)
    convergence_plot(convergence).write_html(output / "convergence.html", include_plotlyjs=True)
    for j in range(3):
        shape = modal.modes[:, j].reshape(-1, 3)
        scale = 0.1 / float(np.max(np.linalg.norm(shape[:, :2], axis=1)))
        beam_shape(model, shape, scale, modal=True).write_html(
            output / f"mode-{j + 1}.html", include_plotlyjs=True
        )
    print(f"Tip displacement: {static.displacement[-1, 1]:.10g} m")
    print(f"Tip rotation: {static.displacement[-1, 2]:.10g} rad")
    print(f"Frequencies [Hz]: {modal.frequencies_hz}")
    print(f"Reports and interactive plots: {output}")


if __name__ == "__main__":
    main()
