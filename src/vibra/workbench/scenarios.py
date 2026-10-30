"""Compact reference scenarios: actual model sketches, plus a labeled sensor schematic."""

from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from vibra.studies.beginner import (
    MotorInputs,
    ShelfInputs,
    motor_config,
    shelf_model,
    washer_signal,
)
from vibra.studies.installed import installed_model
from vibra.visualization.viewport import engineering_viewport
from vibra.workbench.presentation import plot

SCENARIOS = {
    "Cantilever Beam": (
        "A shelf on the wall",
        "A load pulls a shelf support downward while the wall holds one end still.",
        "How much does the support bend, and where is the beam section stress largest?",
        "Change the support length, beam thickness or downward load.",
        "See movement and beam stress separately; the tip and the stress hotspot can differ.",
    ),
    "Automotive Motor Mount": (
        "An electric motor on a support",
        "An idealized motor shakes a rail attached to a rigid vehicle-side support.",
        "How do motor inertia and flexible mounts change motion and transmitted force?",
        "Change motor mass, mount stiffness or the assumed vibration frequency.",
        "Compare rigid and isolated attachment at a chosen frequency; lower stiffness "
        "is not always better.",
    ),
    "Vibration Diagnostics": (
        "A washing machine during spin",
        "Imagine a sensor recording shaking while a washing machine spins at steady speed.",
        "Which repeating rates are visible, and how large is the recorded vibration overall?",
        "Compare two frequencies in a clearly simulated acceleration recording.",
        "Read the time trace, strongest frequency bin and RMS level without diagnosing a fault.",
    ),
}


def scenario_figure(experience: str) -> Any:
    if experience in ("Cantilever Beam", "Automotive Motor Mount"):
        if experience == "Cantilever Beam":
            model = shelf_model(ShelfInputs())
        else:
            model, _ = installed_model(motor_config(MotorInputs()), "isolated")
        figure = engineering_viewport(
            model,
            np.zeros(3 * len(model.nodes)),
            scale=1,
            overlay=False,
            title="Reference model sketch · not solved",
        )
        figure.update_layout(
            height=235,
            showlegend=False,
            title=dict(text="Reference model sketch · not solved", font=dict(size=13)),
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=30, b=10),
        )
        for trace in figure.data:
            if getattr(trace.marker, "coloraxis", None):
                trace.marker.coloraxis = None
                trace.marker.color = "#147d75"
                trace.marker.size = 5
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
        for annotation in figure.layout.annotations:
            annotation.font.size = 10
        return figure
    series = washer_signal()
    figure = make_subplots(rows=1, cols=2, column_widths=[0.32, 0.68])
    angle = np.linspace(0, 2 * np.pi, 60)
    figure.add_trace(
        go.Scatter(
            x=[0, 1, 1, 0, 0], y=[0, 0, 1.2, 1.2, 0], mode="lines", name="Illustrative appliance"
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=0.5 + 0.32 * np.cos(angle),
            y=0.55 + 0.32 * np.sin(angle),
            mode="lines",
            name="Spin drum (schematic)",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=[0.9],
            y=[1.05],
            mode="markers+text",
            text=["sensor"],
            textposition="top left",
            marker=dict(size=9),
            name="Illustrative sensor",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=series.time[:256],
            y=series.values[:256],
            mode="lines",
            name="Actual synthetic samples",
        ),
        row=1,
        col=2,
    )
    figure.update_xaxes(visible=False, row=1, col=1)
    figure.update_yaxes(visible=False, row=1, col=1)
    figure.update_xaxes(title_text="Time [s]", row=1, col=2)
    figure.update_yaxes(title_text="m/s²", row=1, col=2)
    figure.update_layout(
        height=235,
        showlegend=False,
        title=dict(text="Sensor → simulated vibration record", font=dict(size=13)),
        margin=dict(l=10, r=10, t=30, b=15),
    )
    return figure


def scenario_panel(experience: str) -> None:
    title, physical, question, change, reveal = SCENARIOS[experience]
    with st.expander("Start here · " + title, expanded=True):
        words, sketch = st.columns([1.2, 1])
        with words:
            st.markdown("**What is happening?** " + physical)
            st.markdown("**Our question** " + question)
            st.markdown("**You can change** " + change)
            st.markdown("**You will learn** " + reveal)
        with sketch:
            plot(scenario_figure(experience), width="stretch", key="scenario_sketch")
        caption = {
            "Cantilever Beam": (
                "Reference beam equivalent of a shelf support; your submitted result "
                "appears below. This is not a complete shelf or fastener model."
            ),
            "Automotive Motor Mount": (
                "Reference rail, motor and relative mounts. The motor circle is an "
                "inertia glyph, not CAD. Your submitted assembly appears below."
            ),
            "Vibration Diagnostics": (
                "Sensor location is schematic; the trace uses actual synthetic "
                "samples. This is not measured data or an appliance FEM model."
            ),
        }
        st.caption(caption[experience])
