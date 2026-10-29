"""Actual FEM frequency-response and instantaneous phasor deformation plots."""

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from vibra.core.models import DOF, FrameModel
from vibra.solvers.harmonic import HarmonicResult
from vibra.visualization.plots import beam_shape


def response_figures(result: HarmonicResult) -> tuple[Any, Any]:
    amplitude = make_subplots(specs=[[{"secondary_y": True}]])
    phase = go.Figure()
    for column, response in enumerate(result.response_dofs):
        rotational = response.dof == DOF.RZ
        amplitude.add_trace(
            go.Scatter(
                x=result.frequencies_hz,
                y=result.response_amplitude[:, column],
                name=response.label,
                mode="lines",
            ),
            secondary_y=rotational,
        )
        phase.add_trace(
            go.Scatter(
                x=result.frequencies_hz,
                y=[
                    float(np.rad2deg(value)) if valid else None
                    for value, valid in zip(
                        result.phase_radians[:, column],
                        result.phase_defined[:, column],
                        strict=True,
                    )
                ],
                name=response.label,
                mode="lines",
                connectgaps=False,
            )
        )
        peaks = [peak for peak in result.peaks if peak.response == response]
        if peaks:
            amplitude.add_trace(
                go.Scatter(
                    x=[peak.frequency_hz for peak in peaks],
                    y=[peak.amplitude for peak in peaks],
                    mode="markers",
                    marker={"symbol": "diamond", "size": 8},
                    name=f"Sampled peaks: {response.label}",
                ),
                secondary_y=rotational,
            )
    for figure, title in ((amplitude, "Peak displacement amplitude"), (phase, "Response phase")):
        visible = result.natural_frequencies_hz[
            (result.natural_frequencies_hz >= result.frequencies_hz[0])
            & (result.natural_frequencies_hz <= result.frequencies_hz[-1])
        ]
        for index, natural in enumerate(visible):
            figure.add_vline(
                x=float(natural),
                line_dash="dot",
                line_color="#8b959f",
                annotation_text="Undamped natural" if index == 0 else None,
            )
        figure.update_layout(
            template="plotly_white",
            title=title,
            xaxis_title="Excitation frequency [Hz]",
            legend={"orientation": "h", "y": -0.25},
            margin={"t": 60, "b": 80},
        )
    amplitude.update_yaxes(title_text="Translation amplitude [m]", secondary_y=False)
    amplitude.update_yaxes(title_text="Rotation amplitude [rad]", secondary_y=True)
    phase.update_yaxes(
        title_text="Phase relative to global cosine reference [deg]", range=[-185, 185]
    )
    return amplitude, phase


def harmonic_shape(
    model: FrameModel,
    result: HarmonicResult,
    frequency_index: int,
    time_phase_degrees: float,
    scale: float,
) -> Any:
    """Interpolate Re(U exp(jθ)); never use |U| as a signed deformation."""
    if not 0 <= frequency_index < len(result.frequencies_hz):
        raise ValueError("Frequency sample index is outside the solved sweep.")
    if not np.isfinite(scale) or scale < 0 or not np.isfinite(time_phase_degrees):
        raise ValueError("Display scale must be nonnegative and display phase finite.")
    snapshot = np.real(
        result.displacement[frequency_index] * np.exp(1j * np.deg2rad(time_phase_degrees % 360))
    )
    figure = beam_shape(model, snapshot, scale)
    figure.update_layout(
        title=(
            f"{result.frequencies_hz[frequency_index]:.6g} Hz · Re(U exp(jθ)), "
            f"θ = {time_phase_degrees:g}° · displacement ×{scale:.4g}"
        )
    )
    return figure
