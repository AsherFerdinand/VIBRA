"""Fair A/B comparison from actual states, with shared axes, colors and magnification."""

from typing import Any

import numpy as np
from plotly.subplots import make_subplots

from vibra.core.assembly import assemble
from vibra.core.models import NodalLoad
from vibra.studies.installed import InstalledStudy, Topology
from vibra.studies.investigation import DesignComparison
from vibra.visualization.viewport import Contour, engineering_viewport


def comparison_viewport(
    comparison: DesignComparison,
    scale: float = 12.6,
    field: Contour = "Combined normal stress",
    overlay: bool = True,
) -> Any:
    designs = (comparison.baseline, comparison.candidate)
    figures = [
        engineering_viewport(
            design.shelf.model,
            design.shelf.result.displacement,
            scale,
            field,
            overlay=overlay,
            title="",
        )
        for design in designs
    ]
    figure = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.09,
        subplot_titles=(
            f"A · saved baseline · {designs[0].shelf.inputs.thickness_mm:g} mm",
            f"B · submitted design · {designs[1].shelf.inputs.thickness_mm:g} mm",
        ),
    )
    for column, source in enumerate(figures, start=1):
        for trace in source.data:
            trace.showlegend = bool(trace.showlegend is not False and column == 1)
            figure.add_trace(trace, row=1, col=column)
        for annotation in source.layout.annotations:
            copied = annotation.to_plotly_json()
            copied.update(xref="x" if column == 1 else "x2", yref="y" if column == 1 else "y2")
            figure.add_annotation(copied)
    # Limits include all plotted geometries, not just the nodal displacement maxima.
    xs = np.concatenate(
        [np.asarray(trace.x, dtype=float) for source in figures for trace in source.data]
    )
    ys = np.concatenate(
        [np.asarray(trace.y, dtype=float) for source in figures for trace in source.data]
    )
    length = max(float(np.ptp(xs)), 1e-6)
    padding = 0.12 * length
    xr = [float(xs.min() - padding), float(xs.max() + padding)]
    yr = [float(ys.min() - padding), float(ys.max() + padding)]
    for column in (1, 2):
        figure.update_xaxes(range=xr, title_text="Global X [m]", row=1, col=column)
        figure.update_yaxes(
            range=yr,
            scaleanchor="x" if column == 1 else "x2",
            scaleratio=1,
            title_text="Global Y [m]" if column == 1 else None,
            row=1,
            col=column,
        )
    coloraxis = figures[0].layout.coloraxis.to_plotly_json()
    coloraxis["cmin"] = min(source.layout.coloraxis.cmin for source in figures)
    coloraxis["cmax"] = max(source.layout.coloraxis.cmax for source in figures)
    figure.update_layout(
        height=550,
        template="plotly_white",
        coloraxis=coloraxis,
        title=dict(
            text=f"Compare calculated supports · common magnification ×{scale:g}", font_size=18
        ),
        legend=dict(orientation="h", y=-0.22, font_size=10),
        margin=dict(l=35, r=75, t=95, b=100),
        meta=dict(common_scale=scale, common_x_range=xr, common_y_range=yr, field=field),
    )
    return figure


def motor_snapshot(
    study: InstalledStudy,
    topology: Topology,
    harmonic: bool = False,
    phase_degrees: float = 0,
    scale: float = 5,
    overlay: bool = True,
) -> Any:
    """Real static state or Re(U exp(j theta)); no amplitude-only deformation."""
    case = next(case for case in study.cases if case.topology == topology)
    if not np.isfinite(phase_degrees):
        raise ValueError("Use a finite harmonic phase.")
    mount_forces = case.static.mount_forces_N
    loads = case.model.loads
    q = case.static.displacement
    title = f"{topology.title()} · static prescribed load"
    if harmonic:
        index = int(np.argmin(abs(case.harmonic.frequencies_hz - study.config.operating_hz)))
        omega = 2 * np.pi * case.harmonic.frequencies_hz[index]
        rotated = case.harmonic.displacement[index] * np.exp(1j * np.deg2rad(phase_degrees))
        q = rotated.real
        velocity = (1j * omega * rotated).real
        assembly = assemble(case.model)
        force = np.real(case.harmonic.force_phasor * np.exp(1j * np.deg2rad(phase_degrees)))
        loads = tuple(
            NodalLoad(
                node=node,
                fx=float(force[3 * i]),
                fy=float(force[3 * i + 1]),
                mz=float(force[3 * i + 2]),
            )
            for i, node in enumerate(assembly.node_ids)
        )
        mount_forces = {
            entry.mount.id: float(
                entry.mount.stiffness * (entry.extension @ q)
                + (entry.mount.damping + study.config.stiffness_beta_s * entry.mount.stiffness)
                * (entry.extension @ velocity)
            )
            for entry in assembly.mounts
        }
        title = (
            f"{topology.title()} · {case.harmonic.frequencies_hz[index]:g} Hz excitation"
            f" · reference phase {phase_degrees:g}°"
        )
    return engineering_viewport(
        case.model,
        q,
        scale,
        "Displacement magnitude",
        overlay=overlay,
        loads=loads,
        monitors=tuple(sorted({case.force_node, study.config.elements})),
        mount_forces_N=mount_forces,
        title=title,
    )
