"""Executed cloud CPU costs for the 0.9 investigation; not a laptop benchmark."""

import json
import platform
import resource
import statistics
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from vibra.studies.investigation import ChallengeInputs, calculate_design, compare_designs
from vibra.visualization.investigation import comparison_viewport
from vibra.visualization.theme import themed_figure


def main() -> None:
    comparison = compare_designs(calculate_design(), calculate_design(ChallengeInputs(depth_mm=24)))
    figure = comparison_viewport(comparison)
    records = {}
    for name, operation in (
        ("candidate_static_modal_recovery", lambda: calculate_design(ChallengeInputs(depth_mm=24))),
        ("two_design_viewport", lambda: comparison_viewport(comparison)),
        ("dark_presentation_copy", lambda: themed_figure(figure, "Dark")),
    ):
        function: Callable[[], Any] = operation
        times = []
        for _ in range(3):
            start = perf_counter()
            function()
            times.append(perf_counter() - start)
        records[name] = dict(median_wall_s=statistics.median(times), repetitions=3, samples_s=times)
    report = dict(
        python=platform.python_version(),
        system=platform.system(),
        model=dict(designs=2, elements_per_design=12, stations_per_element=21),
        operations=records,
        comparison_json_bytes=len(figure.to_json().encode()),
        process_peak_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        scope=(
            "Executed cloud CPU only; excludes browser/Streamlit memory; not a laptop guarantee."
        ),
    )
    output = Path("docs/results/investigation-performance.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
