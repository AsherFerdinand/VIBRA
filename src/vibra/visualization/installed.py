"""Actual installed-system results and explicit massless-arm/mount topology."""

from typing import Any

import numpy as np
import plotly.graph_objects as go

from vibra.studies.installed import InstalledCase, InstalledStudy
from vibra.visualization.plots import beam_shape


def installed_shape(
    case: InstalledCase, displacement: Any, scale: float, modal: bool = False
) -> Any:
    figure = beam_shape(case.model, displacement, scale, modal=modal)
    q = np.asarray(displacement).reshape(-1)
    nodes = {node.id: node for node in case.model.nodes}
    offsets = {node: 3 * i for i, node in enumerate(sorted(nodes))}

    def point(node: int, x: float, y: float) -> tuple[float, float]:
        u, v, theta = q[offsets[node] : offsets[node] + 3]
        return nodes[node].x + x + scale * (u - y * theta), nodes[node].y + y + scale * (
            v + x * theta
        )

    for mount in case.model.mounts:
        assert mount.node_b is not None
        a = point(mount.node_a, *mount.offset_a)
        b = point(mount.node_b, *mount.offset_b)
        for node, attachment in ((mount.node_a, a), (mount.node_b, b)):
            center = point(node, 0, 0)
            figure.add_trace(
                go.Scatter(
                    x=[center[0], attachment[0]],
                    y=[center[1], attachment[1]],
                    mode="lines",
                    line=dict(color="#777", dash="dot"),
                    showlegend=False,
                )
            )
        figure.add_trace(
            go.Scatter(
                x=[a[0], b[0]],
                y=[a[1], b[1]],
                mode="lines+markers",
                name=f"Mount {mount.id} (X/Y pair)",
                showlegend=mount.id < 2,
            )
        )
    for body in case.model.nodal_masses:
        center = point(body.node, *body.offset)
        ref = point(body.node, 0, 0)
        figure.add_trace(
            go.Scatter(
                x=[ref[0], center[0]],
                y=[ref[1], center[1]],
                mode="lines+markers",
                marker=dict(size=10),
                name="Rigid motor COM; arm is massless",
            )
        )
    return figure


def installed_figures(study: InstalledStudy) -> dict[str, Any]:
    figures = {}
    definitions = (
        ("harmonic_motor", "Frequency [Hz]", "Motor/interface peak amplitude [m]"),
        ("harmonic_rail", "Frequency [Hz]", "Rail tip peak amplitude [m]"),
        ("phase", "Frequency [Hz]", "Motor/interface phase [deg]"),
        ("root_transmission", "Frequency [Hz]", "Root |Fy| / applied peak |F|"),
        ("mount_transmission", "Frequency [Hz]", "Rail transmitted |Fy| / applied peak |F|"),
        ("displacement", "Time [s]", "Motor/interface displacement [m]"),
        ("velocity", "Time [s]", "Motor/interface velocity [m/s]"),
        ("acceleration", "Time [s]", "Motor/interface acceleration [m/s²]"),
        ("root_reaction", "Time [s]", "Dynamic root Fy [N]"),
        ("transmitted", "Time [s]", "Force transmitted to rail [N]"),
        ("energy", "Time [s]", "Mechanical energy [J]"),
        ("dissipation", "Time [s]", "Cumulative viscous dissipation [J]"),
    )
    for key, xlabel, ylabel in definitions:
        figure = go.Figure()
        for case in study.cases:
            h, t = case.harmonic, case.transient
            node = case.force_node
            harmonic = key in (
                "harmonic_motor",
                "harmonic_rail",
                "phase",
                "root_transmission",
                "mount_transmission",
            )
            x = h.frequencies_hz if harmonic else t.time
            values = {
                "harmonic_motor": abs(h.displacement[:, 3 * node + 1]),
                "harmonic_rail": abs(h.displacement[:, 3 * study.config.elements + 1]),
                "phase": np.angle(h.displacement[:, 3 * node + 1], deg=True),
                "root_transmission": abs(case.harmonic_root_force_N)
                / study.config.harmonic_force_N,
                "mount_transmission": abs(case.harmonic_transmitted_force_N)
                / study.config.harmonic_force_N,
                "displacement": t.displacement[:, 3 * node + 1],
                "velocity": t.velocity[:, 3 * node + 1],
                "acceleration": t.acceleration[:, 3 * node + 1],
                "root_reaction": t.reactions[:, 1],
                "transmitted": case.transient_transmitted_force_N,
                "energy": t.kinetic_energy + t.strain_energy,
                "dissipation": t.damping_dissipation,
            }
            figure.add_trace(go.Scatter(x=x, y=values[key], name=case.topology))
        figure.update_layout(
            template="plotly_white",
            title=key.replace("_", " ").title(),
            xaxis_title=xlabel,
            yaxis_title=ylabel,
        )
        if key in ("harmonic_motor", "harmonic_rail", "root_transmission", "mount_transmission"):
            figure.update_yaxes(type="log")
            figure.add_vline(
                x=study.config.operating_hz,
                line_dash="dash",
                annotation_text="Operating assumption",
            )
        figures[key] = figure
    return figures
