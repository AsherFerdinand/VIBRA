"""Compare harmonic response at and away from the natural frequency."""

from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from vibra.dynamics.sdof import SDOFConfig, solve_sdof
from vibra.io.reports import engineering_report


def main() -> None:
    output = Path("artifacts/sdof")
    output.mkdir(parents=True, exist_ok=True)
    natural_hz = np.sqrt(200 / 2) / (2 * np.pi)
    figure = go.Figure()
    for ratio in (0.5, 1.0, 2.0):
        config = SDOFConfig(
            mass=2,
            stiffness=200,
            damping=2,
            initial_displacement=0,
            force_amplitude=1,
            excitation_hz=float(ratio * natural_hz),
            duration=20,
            samples=4001,
        )
        result = solve_sdof(config)
        figure.add_trace(
            go.Scatter(
                x=result.time,
                y=result.displacement,
                name=f"Excitation / natural frequency = {ratio:g}",
            )
        )
        (output / f"ratio-{ratio:g}.json").write_text(
            engineering_report("Harmonic SDOF", config, result) + "\n"
        )
    figure.update_layout(
        template="plotly_white",
        title="Damped SDOF resonance (actual integrated responses)",
        xaxis_title="Time [s]",
        yaxis_title="Displacement [m]",
    )
    figure.write_html(output / "resonance.html", include_plotlyjs=True)
    print(f"Natural frequency: {natural_hz:.8g} Hz; reports and plot: {output}")


if __name__ == "__main__":
    main()
