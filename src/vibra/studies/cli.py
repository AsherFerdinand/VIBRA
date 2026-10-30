"""Generate an executable automotive support-rail engineering investigation."""

import argparse
from pathlib import Path

import numpy as np

from vibra.io.nvh_report import design_conclusion, study_json, study_markdown
from vibra.studies.nvh import run_nvh_study
from vibra.visualization.nvh import comparison_figures, geometry_plot
from vibra.visualization.plots import beam_shape


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/automotive-nvh-study"))
    args = parser.parse_args()
    output: Path = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    study = run_nvh_study()
    (output / "study.json").write_text(study_json(study) + "\n")
    (output / "study.md").write_text(study_markdown(study))
    geometry_plot(study).write_html(output / "geometry.html", include_plotlyjs=True)
    for name, figure in comparison_figures(study).items():
        figure.write_html(output / f"{name}.html", include_plotlyjs=True)
    for name, item in (("baseline", study.baseline), ("modified", study.modified)):
        shape = item.modal.modes[:, 0].reshape(-1, 3)
        scale = 0.05 * item.design.length / float(np.max(np.linalg.norm(shape[:, :2], axis=1)))
        beam_shape(item.model, shape, scale, modal=True).write_html(
            output / f"{name}-mode-1.html", include_plotlyjs=True
        )
    print(design_conclusion(study))
    print("Study checks:", study.verification_checks)
    print("JSON, Markdown and actual engineering figures:", output)
    if not all(study.verification_checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
