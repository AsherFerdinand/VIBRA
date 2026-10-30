"""Reproduce all three teaching examples with real numerical reports and explanations."""

from dataclasses import asdict
from pathlib import Path

from vibra.io.installed_report import installed_json
from vibra.io.reports import engineering_report
from vibra.io.signal_report import signal_report
from vibra.studies.beginner import run_motor, run_shelf, run_washer
from vibra.workbench.interpretation import (
    beam_interpretation,
    motor_interpretation,
    signal_interpretation,
)


def main() -> None:
    output = Path("artifacts/beginner-workflows")
    output.mkdir(parents=True, exist_ok=True)
    shelf, motor, washer = run_shelf(), run_motor(), run_washer()
    (output / "shelf.json").write_text(
        engineering_report(
            "Shelf support teaching example",
            shelf.inputs,
            dict(model=shelf.model, static=shelf.result, section_stress=shelf.stress),
        )
    )
    (output / "motor.json").write_text(installed_json(motor))
    (output / "simulated-washer.json").write_text(signal_report(washer.series, washer.spectrum))
    conclusions = dict(
        shelf=asdict(beam_interpretation(shelf.model, shelf.result)),
        motor=asdict(motor_interpretation(motor)),
        simulated_washer=asdict(signal_interpretation(washer.series, washer.spectrum)),
    )
    (output / "interpretation.json").write_text(
        engineering_report(
            "Deterministic example explanations", dict(simulated_not_measured=True), conclusions
        )
    )
    for name, conclusion in conclusions.items():
        print(name + ": " + conclusion["happened"])


if __name__ == "__main__":
    main()
