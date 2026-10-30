"""Measure executed reconstruction/viewport/animation costs; no performance simulation."""

import json
import platform
import resource
import statistics
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from vibra.core.models import AnalysisConfig
from vibra.postprocessing.beam import recover_stress
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.stress_benchmarks import stress_case
from vibra.visualization.viewport import engineering_viewport, state_animation


def main() -> None:
    model = stress_case()
    q = solve_static(model).displacement
    mode = solve_modal(model, AnalysisConfig(modes=1)).modes[:, 0]
    states = np.cos(np.linspace(0, 2 * np.pi, 25)[:, None]) * mode[None, :]
    records = {}
    for name, operation in (
        ("stress_recovery", lambda: recover_stress(model, q)),
        ("static_viewport", lambda: engineering_viewport(model, q, 12.6, "Combined normal stress")),
        (
            "25_frame_modal_animation",
            lambda: state_animation(
                model, states, tuple(str(i) for i in range(25)), 0.1, modal=True
            ),
        ),
    ):
        function: Callable[[], Any] = operation
        times = []
        value = None
        for _ in range(3):
            start = perf_counter()
            value = function()
            times.append(perf_counter() - start)
        assert value is not None
        records[name] = dict(
            median_wall_s=statistics.median(times),
            repetitions=3,
            figure_json_bytes=len(value.to_json().encode()) if name != "stress_recovery" else None,
        )
    report = dict(
        python=platform.python_version(),
        system=platform.system(),
        model=dict(beam_elements=8, stations_per_element=21, animation_frames=25),
        operations=records,
        process_peak_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        scope=(
            "Measured on this cloud CPU; not a laptop/browser benchmark or timing guarantee. "
            "Animations capped at 60 states, optional generation; no GPU required."
        ),
    )
    Path("docs/results/viewport-performance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
