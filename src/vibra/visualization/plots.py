"""Plotly geometry, Hermite deformations, internal moments and convergence."""

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vibra.core.assembly import assemble
from vibra.core.element import Matrix
from vibra.core.models import FrameModel
from vibra.dynamics.sdof import SDOFResult
from vibra.postprocessing.beam import sample_beam
from vibra.solvers.static import StaticResult


def _style(figure: Any, title: str, x: str, y: str) -> Any:
    figure.update_layout(
        title=title,
        template="plotly_white",
        xaxis_title=x,
        yaxis_title=y,
        font={"family": "Arial", "color": "#142c3e"},
        margin={"l": 50, "r": 25, "t": 65, "b": 50},
        legend={"orientation": "h", "y": -0.25},
    )
    return figure


def beam_shape(model: FrameModel, displacement: Matrix, scale: float, modal: bool = False) -> Any:
    assembly = assemble(model)
    nodes = {node.id: node for node in model.nodes}
    coordinates = np.array([[nodes[n].x, nodes[n].y] for n in assembly.node_ids])
    figure = go.Figure()
    for index, field in enumerate(sample_beam(model, displacement)):
        base = field.position_m.T
        shape = base + scale * field.displacement_m.T
        figure.add_trace(
            go.Scatter(
                x=base[0],
                y=base[1],
                mode="lines",
                line={"color": "#acb9c4", "dash": "dot"},
                name="Undeformed mesh",
                legendgroup="base",
                showlegend=index == 0,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=shape[0],
                y=shape[1],
                mode="lines",
                line={"color": "#007f88", "width": 3},
                name="Mode shape" if modal else "Deformed beam",
                legendgroup="shape",
                showlegend=index == 0,
            )
        )
    figure.add_trace(
        go.Scatter(
            x=coordinates[:, 0],
            y=coordinates[:, 1],
            mode="markers",
            name="Nodes",
            marker={"size": 5, "color": "#142c3e"},
        )
    )
    figure.update_yaxes(scaleanchor="x", scaleratio=1)
    label = (
        "Normalized mode, arbitrary amplitude" if modal else f"Displacement magnified ×{scale:.3g}"
    )
    return _style(figure, label, "Global x [m]", "Global y [m]")


def bending_moment(model: FrameModel, result: StaticResult) -> Any:
    figure = go.Figure()
    distance = 0.0
    # Intended for the generated straight chain. General frames retain per-element local forces.
    for index, entry in enumerate(assemble(model).elements):
        length = entry.matrices.length
        force = result.element_end_forces[entry.element.id]
        figure.add_trace(
            go.Scatter(
                x=[distance, distance + length],
                y=[-force[2], -force[2] + force[1] * length],
                mode="lines",
                fill="tozeroy",
                line={"color": "#d18437"},
                name="Bending moment",
                showlegend=index == 0,
            )
        )
        distance += length
    return _style(
        figure, "Internal bending moment (local sign convention)", "Beam coordinate [m]", "M [N m]"
    )


def convergence_plot(rows: list[dict[str, Any]]) -> Any:
    figure = go.Figure()
    for mode in range(3):
        figure.add_trace(
            go.Scatter(
                x=[row["elements"] for row in rows],
                y=[100 * row["relative_frequency_errors"][mode] for row in rows],
                mode="lines+markers",
                name=f"Bending mode {mode + 1}",
            )
        )
    figure.update_xaxes(type="log", dtick=0.30103)
    figure.update_yaxes(type="log")
    return _style(figure, "Cantilever frequency convergence", "Elements", "Relative error [%]")


def sdof_response(result: SDOFResult) -> Any:
    figure = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08)
    for row, (values, label) in enumerate(
        [
            (result.displacement, "x [m]"),
            (result.velocity, "v [m/s]"),
            (result.acceleration, "a [m/s²]"),
        ],
        start=1,
    ):
        figure.add_trace(go.Scatter(x=result.time, y=values, name=label), row=row, col=1)
        figure.update_yaxes(title_text=label, row=row, col=1)
    figure.update_layout(template="plotly_white", title="SDOF time response", height=650)
    figure.update_xaxes(title_text="Time [s]", row=3, col=1)
    return figure
