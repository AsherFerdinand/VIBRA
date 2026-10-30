"""Reproduce installed motor study reports and interactive figures."""

import argparse
from pathlib import Path

from vibra.io.installed_report import installed_conclusion, installed_json, installed_markdown
from vibra.studies.installed import run_installed_study
from vibra.visualization.installed import installed_figures, installed_shape


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/installed-motor-study"))
    args = parser.parse_args()
    study = run_installed_study()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "study.json").write_text(installed_json(study))
    (args.output_dir / "study.md").write_text(installed_markdown(study))
    for name, figure in installed_figures(study).items():
        figure.write_html(args.output_dir / (name + ".html"), include_plotlyjs="cdn")
    for case in study.cases:
        installed_shape(case, case.modal.modes[:, 0], 0.01, modal=True).write_html(
            args.output_dir / (case.topology + "-first-mode.html"), include_plotlyjs="cdn"
        )
    print(installed_conclusion(study))
    print(study.checks)
    if not all(study.checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
