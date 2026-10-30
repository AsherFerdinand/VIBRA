"""Actual displacement/velocity/acceleration, energy and FEM deformation histories."""

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.colors import DEFAULT_PLOTLY_COLORS
from plotly.subplots import make_subplots

from vibra.core.models import DOF, FrameModel
from vibra.solvers.transient import TransientResult
from vibra.visualization.plots import beam_shape


def response_history(result: TransientResult) -> Any:
    indices = np.unique(
        np.linspace(0, len(result.time) - 1, min(2001, len(result.time)), dtype=int)
    )
    figure = make_subplots(rows=3, cols=1, shared_xaxes=True, specs=[[{"secondary_y": True}]] * 3)
    histories = (
        result.response_displacement,
        result.response_velocity,
        result.response_acceleration,
    )
    for column, response in enumerate(result.response_dofs):
        for row, values in enumerate(histories, start=1):
            figure.add_trace(
                go.Scatter(
                    x=result.time[indices],
                    y=values[indices, column],
                    name=response.label,
                    legendgroup=str(column),
                    showlegend=row == 1,
                    line={"color": DEFAULT_PLOTLY_COLORS[column % len(DEFAULT_PLOTLY_COLORS)]},
                ),
                row=row,
                col=1,
                secondary_y=response.dof == DOF.RZ,
            )
    for row, unit in enumerate(("", "/s", "/s²"), start=1):
        figure.update_yaxes(title_text=f"Translation [m{unit}]", row=row, col=1, secondary_y=False)
        figure.update_yaxes(title_text=f"Rotation [rad{unit}]", row=row, col=1, secondary_y=True)
    figure.update_xaxes(title_text="Time [s]", row=3, col=1)
    figure.update_layout(template="plotly_white", title="Transient response histories", height=720)
    return figure


def energy_history(result: TransientResult) -> Any:
    indices = np.unique(
        np.linspace(0, len(result.time) - 1, min(2001, len(result.time)), dtype=int)
    )
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Mechanical energy", "Cumulative work, dissipation and balance"),
    )
    for values, label in (
        (result.kinetic_energy, "Kinetic"),
        (result.strain_energy, "Elastic strain"),
        (result.kinetic_energy + result.strain_energy, "Mechanical total"),
    ):
        figure.add_trace(
            go.Scatter(x=result.time[indices], y=values[indices], name=label), row=1, col=1
        )
    for values, label in (
        (result.damping_dissipation, "Damping dissipation"),
        (result.external_work, "External work"),
        (result.energy_balance_residual, "E − E₀ + D − W"),
    ):
        figure.add_trace(
            go.Scatter(x=result.time[indices], y=values[indices], name=label), row=2, col=1
        )
    figure.update_yaxes(title_text="Energy [J]")
    figure.update_xaxes(title_text="Time [s]", row=2, col=1)
    figure.update_layout(template="plotly_white", height=650)
    return figure


def transient_shape(model: FrameModel, result: TransientResult, index: int, scale: float) -> Any:
    if not 0 <= index < len(result.time) or not np.isfinite(scale) or scale < 0:
        raise ValueError("Select a valid time index and a finite nonnegative display scale.")
    figure = beam_shape(model, result.displacement[index], scale)
    figure.update_layout(
        title=f"t = {result.time[index]:.6g} s · physical displacement magnified ×{scale:.4g}"
    )
    return figure


def transient_animation(
    model: FrameModel, result: TransientResult, scale: float, max_frames: int = 60
) -> Any:
    """Bounded frames from actual solved timestamps; playback is illustrative."""
    if not 2 <= max_frames <= 80:
        raise ValueError("Animation supports 2–80 frames.")
    indices = np.unique(
        np.linspace(0, len(result.time) - 1, min(max_frames, len(result.time)), dtype=int)
    )
    figure = transient_shape(model, result, 0, scale)
    trace_ids = [2 * i + 1 for i in range(len(model.elements))]
    frames = []
    xs: list[float] = []
    ys: list[float] = []
    for index in indices:
        snapshot = transient_shape(model, result, int(index), scale)
        data = [snapshot.data[i] for i in trace_ids]
        frames.append(
            go.Frame(data=data, traces=trace_ids, name=str(index), layout=snapshot.layout)
        )
        xs.extend(float(x) for trace in data for x in trace.x)
        ys.extend(float(y) for trace in data for y in trace.y)
    length = max(np.ptp([node.x for node in model.nodes]), np.ptp([node.y for node in model.nodes]))
    padding = 0.05 * float(length)
    figure.update_xaxes(range=[min(xs) - padding, max(xs) + padding])
    figure.update_yaxes(range=[min(ys) - padding, max(ys) + padding])
    # Frame layouts update only titles; axes must remain fixed over the whole motion.
    for frame in frames:
        frame.layout = go.Layout(title=frame.layout.title)
    figure.frames = frames
    figure.update_layout(
        updatemenus=[
            {
                "type": "buttons",
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": 60, "redraw": True},
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {"mode": "immediate", "frame": {"duration": 0, "redraw": False}},
                        ],
                    },
                ],
            }
        ]
    )
    return figure
