"""Reproduce actual combined-stress contours and an actual first-mode animation."""

from pathlib import Path

import numpy as np

from vibra.core.models import AnalysisConfig
from vibra.io.reports import engineering_report
from vibra.postprocessing.beam import recover_stress
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.stress_benchmarks import stress_case
from vibra.visualization.viewport import engineering_viewport, state_animation


def main() -> None:
    output = Path("artifacts/stress-viewport")
    output.mkdir(parents=True, exist_ok=True)
    model = stress_case(axial=20000, transverse=-100)
    static = solve_static(model)
    stress = recover_stress(model, static.displacement)
    (output / "stress.json").write_text(
        engineering_report("Beam section normal stress", model, stress)
    )
    engineering_viewport(
        model, static.displacement, 12.6, "Combined normal stress", monitors=(8,)
    ).write_html(output / "combined-stress.html", include_plotlyjs="cdn")
    modal = solve_modal(model, AnalysisConfig(modes=1))
    mode = modal.modes[:, 0]
    scale = 0.1 / float(np.linalg.norm(mode.reshape(-1, 3)[:, :2], axis=1).max())
    phases = np.linspace(0, 2 * np.pi, 25)
    states = np.cos(phases[:, None]) * mode[None, :]
    state_animation(
        model,
        states,
        tuple(
            f"Mode 1 · {modal.frequencies_hz[0]:.5g} Hz · phase {np.rad2deg(p):.0f}°"
            for p in phases
        ),
        scale,
        modal=True,
    ).write_html(output / "mode-animation.html", include_plotlyjs="cdn")
    print(
        f"Section stress range [{stress.minimum_normal_Pa / 1e6:.6g}, "
        f"{stress.maximum_normal_Pa / 1e6:.6g}] MPa; files: {output}"
    )


if __name__ == "__main__":
    main()
