"""Unit-labeled full-bin spectral figures and unresampled time histories."""

from typing import Any

import plotly.graph_objects as go

from vibra.signals.analysis import SpectrumResult
from vibra.signals.models import SignalSeries


def signal_time_plot(series: SignalSeries, result: SpectrumResult) -> Any:
    figure = go.Figure()
    figure.add_trace(go.Scattergl(x=series.time, y=series.values, name="Original record"))
    figure.add_trace(
        go.Scattergl(x=series.time, y=result.processed_values, name="Processed record")
    )
    figure.update_layout(
        template="plotly_white",
        title="Time-domain vibration signal",
        xaxis_title="Time [s]",
        yaxis_title=f"Signal [{series.unit}]",
    )
    return figure


def spectrum_plots(
    result: SpectrumResult,
    natural_frequencies_hz: tuple[float, ...] = (),
    lower_hz: float = 0,
    upper_hz: float | None = None,
    logarithmic: bool = False,
) -> tuple[Any, Any]:
    upper = result.sampling.nyquist_hz if upper_hz is None else upper_hz
    selected = (result.frequencies_hz >= lower_hz) & (result.frequencies_hz <= upper)
    figures = []
    for values, title, unit in (
        (result.peak_amplitude, "One-sided peak-equivalent amplitude", result.unit),
        (result.psd, "One-sided modified periodogram PSD", f"({result.unit})²/Hz"),
    ):
        figure = go.Figure(
            go.Scattergl(x=result.frequencies_hz[selected], y=values[selected], name=title)
        )
        peaks = [p for p in result.peaks if lower_hz <= p.frequency_hz <= upper]
        if peaks:
            figure.add_trace(
                go.Scatter(
                    x=[p.frequency_hz for p in peaks],
                    y=[float(values[p.bin_index]) for p in peaks],
                    mode="markers",
                    marker={"symbol": "diamond", "size": 9},
                    name="Sampled spectral peaks",
                )
            )
        visible = [
            f
            for f in natural_frequencies_hz
            if lower_hz <= f <= min(upper, result.sampling.nyquist_hz)
        ]
        for index, natural in enumerate(visible):
            figure.add_vline(
                x=natural,
                line_dash="dot",
                line_color="#8b959f",
                annotation_text="FEM natural reference" if index == 0 else None,
            )
        figure.update_layout(
            template="plotly_white", title=title, xaxis_title="Frequency [Hz]", yaxis_title=unit
        )
        if logarithmic:
            figure.update_yaxes(type="log")
        figures.append(figure)
    return figures[0], figures[1]
