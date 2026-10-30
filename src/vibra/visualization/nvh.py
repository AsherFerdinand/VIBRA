"""Comparison figures from the actual study outputs; no numerical solver duplication."""

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vibra.studies.nvh import NVHStudy

COLORS = ("#007f88", "#d18437")


def geometry_plot(study: NVHStudy) -> Any:
    figure = make_subplots(
        rows=1, cols=2, subplot_titles=("In-plane neutral axes", "Rectangular sections")
    )
    for index, item in enumerate((study.baseline, study.modified)):
        d = item.design
        style = {"color": COLORS[index], "dash": "solid" if index == 0 else "dash"}
        figure.add_trace(
            go.Scatter(
                x=[n.x for n in item.model.nodes],
                y=[n.y for n in item.model.nodes],
                mode="lines+markers",
                name=d.name,
                line=style,
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=[-d.width / 2, d.width / 2, d.width / 2, -d.width / 2, -d.width / 2],
                y=[-d.height / 2, -d.height / 2, d.height / 2, d.height / 2, -d.height / 2],
                mode="lines",
                name=d.name + " section",
                line=style,
            ),
            row=1,
            col=2,
        )
        figure.add_trace(
            go.Scatter(
                x=[d.length * study.config.excitation_fraction],
                y=[0],
                mode="markers",
                marker={"symbol": "diamond", "size": 12, "color": COLORS[index]},
                name=d.name + " force station",
            ),
            row=1,
            col=1,
        )
    figure.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers+text",
            text=["Fixed root"],
            textposition="top right",
            marker={"symbol": "square", "size": 14, "color": "#142c3e"},
            name="ux=uy=rz=0",
        ),
        row=1,
        col=1,
    )
    figure.update_xaxes(title_text="Rail x [m]", row=1, col=1)
    figure.update_yaxes(title_text="Rail y [m]", row=1, col=1)
    figure.update_xaxes(title_text="Out-of-plane width [m]", row=1, col=2)
    figure.update_yaxes(title_text="In-plane depth [m]", row=1, col=2)
    figure.update_layout(
        template="plotly_white", title="Equivalent bare support rails (not a solid bracket)"
    )
    return figure


def comparison_figures(study: NVHStudy) -> dict[str, Any]:
    figures: dict[str, Any] = {
        key: go.Figure()
        for key in (
            "static",
            "harmonic_amplitude",
            "harmonic_phase",
            "displacement",
            "velocity",
            "acceleration",
            "energy",
            "reactions",
            "fft_displacement",
            "psd_displacement",
            "fft_acceleration",
            "psd_acceleration",
        )
    }
    titles = {
        "static": ("Static nodal displacement", "Rail x [m]", "Transverse displacement [mm]"),
        "harmonic_amplitude": (
            "Harmonic response at selected monitor",
            "Excitation frequency [Hz]",
            "Peak amplitude [mm]",
        ),
        "harmonic_phase": ("Harmonic phase", "Excitation frequency [Hz]", "Phase [deg]"),
        "displacement": ("Pulse response at selected monitor", "Time [s]", "Displacement [mm]"),
        "velocity": ("Pulse velocity", "Time [s]", "Velocity [m/s]"),
        "acceleration": ("Pulse acceleration", "Time [s]", "Acceleration [m/s²]"),
        "energy": ("Mechanical energy and cumulative dissipation", "Time [s]", "Energy [J]"),
        "reactions": (
            "Dynamic root transverse reaction (perturbation)",
            "Time [s]",
            "Reaction [N]",
        ),
    }
    for index, item in enumerate((study.baseline, study.modified)):
        color = COLORS[index]

        def trace(
            x: Any,
            y: Any,
            label: str | None = None,
            dash: str = "solid",
            color: str = color,
            name: str = item.design.name,
        ) -> Any:
            return go.Scatter(x=x, y=y, name=label or name, line={"color": color, "dash": dash})

        figures["static"].add_trace(
            trace([n.x for n in item.model.nodes], item.static.displacement[:, 1] * 1000)
        )
        node = int(len(item.model.elements) * study.config.monitor_fraction)
        column = next(i for i, r in enumerate(item.harmonic.response_dofs) if r.node == node)
        h = item.harmonic
        figures["harmonic_amplitude"].add_trace(
            trace(h.frequencies_hz, h.response_amplitude[:, column] * 1000)
        )
        figures["harmonic_phase"].add_trace(
            trace(h.frequencies_hz, np.rad2deg(h.phase_radians[:, column]))
        )
        for name in ("harmonic_amplitude", "harmonic_phase"):
            figures[name].add_vline(
                x=item.summary.first_natural_hz, line_dash="dot", line_color=color
            )
        result = item.transient
        for key, values, scale in (
            ("displacement", result.displacement, 1000.0),
            ("velocity", result.velocity, 1.0),
            ("acceleration", result.acceleration, 1.0),
        ):
            figures[key].add_trace(trace(result.time, values[:, 3 * node + 1] * scale))
        figures["energy"].add_trace(
            trace(
                result.time, result.kinetic_energy + result.strain_energy, item.design.name + " E"
            )
        )
        figures["energy"].add_trace(
            trace(result.time, result.damping_dissipation, item.design.name + " D", "dash")
        )
        figures["reactions"].add_trace(
            trace(result.time, result.reactions[:, result.constrained_indices.index(1)])
        )
        for quantity, signal in item.signals.items():
            spectrum = signal.spectrum
            for key, values, label in (
                ("fft", spectrum.peak_amplitude, "Peak-equivalent amplitude"),
                ("psd", spectrum.psd, "PSD"),
            ):
                figure = figures[f"{key}_{quantity}"]
                figure.add_trace(trace(spectrum.frequencies_hz, values))
                figure.add_vline(x=item.summary.first_natural_hz, line_dash="dot", line_color=color)
                unit = signal.series.unit if key == "fft" else f"({signal.series.unit})²/Hz"
                figure.update_layout(
                    title=f"Post-pulse {quantity} {label}",
                    xaxis_title="Frequency [Hz]",
                    yaxis_title=unit,
                )
                figure.update_xaxes(range=[0, min(400, spectrum.sampling.nyquist_hz)])
                figure.update_yaxes(type="log")
    for name in ("harmonic_amplitude", "harmonic_phase"):
        figures[name].add_vline(
            x=study.config.operating_frequency_hz,
            line_dash="dash",
            annotation_text=f"Operating order: {study.config.operating_frequency_hz:g} Hz",
        )
    for key, figure in figures.items():
        figure.update_layout(template="plotly_white")
        if key in titles:
            title, x, y = titles[key]
            figure.update_layout(title=title, xaxis_title=x, yaxis_title=y)
    return figures
