"""Model-corresponding 2D engineering viewport and bounded actual-state animations."""

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import plotly.graph_objects as go

from vibra.core.assembly import assemble
from vibra.core.element import Matrix
from vibra.core.models import DOF, FrameModel, NodalLoad
from vibra.postprocessing.beam import BeamField, recover_stress, sample_beam

Contour = Literal[
    "Displacement magnitude",
    "Vertical displacement",
    "Axial stress",
    "Bending stress",
    "Combined normal stress",
    "Bending moment",
]
CONTOURS: tuple[Contour, ...] = (
    "Displacement magnitude",
    "Vertical displacement",
    "Axial stress",
    "Bending stress",
    "Combined normal stress",
    "Bending moment",
)


@dataclass(frozen=True)
class ContourField:
    beam: BeamField
    values_SI: Matrix
    unit: str
    display_factor: float


def contour_data(
    model: FrameModel,
    state: Matrix,
    field: Contour,
    fiber: Literal["top", "bottom"] = "top",
    samples: int = 21,
) -> tuple[ContourField, ...]:
    if fiber not in ("top", "bottom") or field not in CONTOURS:
        raise ValueError("Unknown field/fiber.")
    beams = sample_beam(model, state, samples)
    stresses = (
        {item.field.element_id: item for item in recover_stress(model, state, samples).sections}
        if field in ("Axial stress", "Bending stress", "Combined normal stress")
        else {}
    )
    output = []
    for beam in beams:
        if field == "Displacement magnitude":
            values = np.linalg.norm(beam.displacement_m, axis=1)
        elif field == "Vertical displacement":
            values = beam.displacement_m[:, 1]
        elif field == "Bending moment":
            values = beam.bending_moment_Nm
        else:
            stress = stresses[beam.element_id]
            values = (
                stress.axial_Pa
                if field == "Axial stress"
                else (stress.bending_top_Pa if fiber == "top" else stress.bending_bottom_Pa)
                if field == "Bending stress"
                else (stress.combined_top_Pa if fiber == "top" else stress.combined_bottom_Pa)
            )
        unit, factor = (
            ("N m", 1.0)
            if field == "Bending moment"
            else ("MPa", 1e-6)
            if "stress" in field
            else ("mm", 1000.0)
        )
        output.append(ContourField(beam, values, unit, factor))
    return tuple(output)


def engineering_viewport(
    model: FrameModel,
    state: Matrix,
    scale: float = 1.0,
    field: Contour = "Displacement magnitude",
    fiber: Literal["top", "bottom"] = "top",
    overlay: bool = True,
    deformed: bool = True,
    loads: tuple[NodalLoad, ...] | None = None,
    monitors: tuple[int, ...] = (),
    title: str = "Engineering viewport",
    modal: bool = False,
    mount_forces_N: dict[int, float] | None = None,
    modal_reference: float | None = None,
) -> Any:
    """Contour only beam axes; motor glyph is radius of gyration, never a stress field.

    Hover/color values always use unscaled physics. Scale affects coordinates only.
    Modal colors are arbitrary eigenvector values, not operating displacement.
    """
    if not np.isfinite(scale) or scale < 0:
        raise ValueError("Use a finite nonnegative display scale.")
    if modal and field not in ("Displacement magnitude", "Vertical displacement"):
        raise ValueError("Modal display offers relative displacement only, not operating stress.")
    data = contour_data(model, state, field, fiber)
    reference = (
        modal_reference
        if modal_reference is not None
        else float(np.max(np.linalg.norm(np.asarray(state).reshape(-1, 3)[:, :2], axis=1)))
    )
    reference = reference or 1.0
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError("Modal reference must be finite and positive.")
    factor = 1 / reference if modal else (data[0].display_factor if data else 1000.0)
    assembly = assemble(model)
    q = np.asarray(state).reshape(-1)
    nodes = {node.id: node for node in model.nodes}
    offsets = {node: 3 * i for i, node in enumerate(assembly.node_ids)}
    figure = go.Figure()
    values = np.concatenate([item.values_SI * factor for item in data]) if data else np.zeros(1)
    unit = "relative" if modal else data[0].unit if data else "mm"
    signed = field != "Displacement magnitude"
    bound = max(float(np.max(abs(values))), 1e-30)
    display_scale = scale if deformed else 0.0

    def point(node: int, offset: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        x, y = offset
        u, v, theta = q[offsets[node] : offsets[node] + 3]
        return (
            nodes[node].x + x + display_scale * (u - y * theta),
            nodes[node].y + y + display_scale * (v + x * theta),
        )

    motion_unit = "relative" if modal else "m"
    # Keep each element's one-sided fields separate, including at shared nodes.
    # Models without explicit fiber geometry still support displacement viewing.
    stress_result = (
        recover_stress(model, state)
        if not modal and all(e.section.extreme_fiber_distance is not None for e in model.elements)
        else None
    )
    stresses = {s.field.element_id: s for s in stress_result.sections} if stress_result else {}
    for item in data:
        beam = item.beam
        xy = beam.position_m + display_scale * beam.displacement_m
        if overlay:
            figure.add_trace(
                go.Scatter(
                    x=beam.position_m[:, 0],
                    y=beam.position_m[:, 1],
                    mode="lines",
                    line=dict(color="#8d9ca9", dash="dot", width=2),
                    name="Undeformed",
                    legendgroup="base",
                    showlegend=item is data[0],
                    hoverinfo="skip",
                )
            )
        custom = np.column_stack(
            (
                beam.local_x_m,
                beam.displacement_m[:, 0] / reference if modal else beam.displacement_m[:, 0],
                beam.displacement_m[:, 1] / reference if modal else beam.displacement_m[:, 1],
                item.values_SI * factor,
            )
        )
        extra_hover = ""
        if not modal:
            section = stresses.get(beam.element_id)
            extra = [beam.axial_force_N, beam.shear_force_N, beam.bending_moment_Nm]
            if section is not None:
                extra.extend((section.combined_top_Pa / 1e6, section.combined_bottom_Pa / 1e6))
            custom = np.column_stack((custom, *extra))
            extra_hover = (
                "<br>N=%{customdata[4]:.5g} N (tension +)"
                "<br>V=%{customdata[5]:.5g} N (dM/dx)"
                "<br>M=%{customdata[6]:.5g} N m"
            )
            if section is not None:
                extra_hover += (
                    "<br>σ top=%{customdata[7]:.5g} MPa<br>σ bottom=%{customdata[8]:.5g} MPa"
                )
        figure.add_trace(
            go.Scatter(
                x=xy[:, 0],
                y=xy[:, 1],
                mode="lines+markers",
                line=dict(color="#b9cbd3", width=3),
                marker=dict(size=6, color=item.values_SI * factor, coloraxis="coloraxis"),
                customdata=custom,
                name=f"Beam {beam.element_id}",
                showlegend=False,
                hovertemplate=(
                    f"Element {beam.element_id}<br>Local x=%{{customdata[0]:.5g}} "
                    f"m<br>UX=%{{customdata[1]:.5g}} "
                    f"{motion_unit}<br>UY=%{{customdata[2]:.5g}} "
                    f"{motion_unit}<br>{field}=%{{customdata[3]:.5g}} "
                    f"{unit}{extra_hover}<extra></extra>"
                ),
            )
        )
    if data:
        flat = int(np.argmax(abs(values)))
        index = 0
        for item in data:
            if flat < index + len(item.values_SI):
                station = flat - index
                xy = (
                    item.beam.position_m[station]
                    + display_scale * item.beam.displacement_m[station]
                )
                figure.add_trace(
                    go.Scatter(
                        x=[xy[0]],
                        y=[xy[1]],
                        mode="markers",
                        marker=dict(
                            symbol="diamond-open", size=17, color="#e06a2a", line=dict(width=2)
                        ),
                        name="Critical |field| (sampled)",
                        hovertemplate=(
                            f"Element {item.beam.element_id}, "
                            f"x={item.beam.local_x_m[station]:.5g} "
                            f"m<br>{values[flat]:.6g} {unit}<extra></extra>"
                        ),
                    )
                )
                break
            index += len(item.values_SI)
        # Distinct physical observations: a stress hotspot need not move most.
        peak_beam, peak_station = max(
            ((item.beam, i) for item in data for i in range(len(item.values_SI))),
            key=lambda pair: float(np.linalg.norm(pair[0].displacement_m[pair[1]])),
        )
        xy = (
            peak_beam.position_m[peak_station]
            + display_scale * peak_beam.displacement_m[peak_station]
        )
        peak_value = np.linalg.norm(peak_beam.displacement_m[peak_station])
        if modal:
            peak_value /= reference
        figure.add_trace(
            go.Scatter(
                x=[xy[0]],
                y=[xy[1]],
                mode="markers",
                marker=dict(symbol="circle-open", size=16, color="#147d75", line=dict(width=2)),
                name="Max translation (sampled)",
                hovertemplate=(
                    f"Element {peak_beam.element_id}, "
                    f"local x={peak_beam.local_x_m[peak_station]:.5g} m"
                    f"<br>|u|={peak_value:.6g} "
                    f"{motion_unit}<extra></extra>"
                ),
            )
        )
    if stress_result:
        critical = stress_result.critical_absolute
        beam = next(item.beam for item in data if item.beam.element_id == critical.element_id)
        station = int(np.argmin(abs(beam.local_x_m - critical.local_x_m)))
        xy = beam.position_m[station] + display_scale * beam.displacement_m[station]
        figure.add_trace(
            go.Scatter(
                x=[xy[0]],
                y=[xy[1]],
                mode="markers",
                marker=dict(symbol="x", size=12, color="#e06a2a", line=dict(width=2)),
                name="Critical section stress (±fiber)",
                hovertemplate=(
                    f"Element {critical.element_id}, local x={critical.local_x_m:.5g} m"
                    f"<br>fiber y={critical.fiber_y_m:.5g} m"
                    f"<br>σ={critical.normal_stress_Pa / 1e6:.6g} MPa"
                    "<br>Axis marker; section result, not solid stress<extra></extra>"
                ),
            )
        )
    fixed: dict[int, set[DOF]] = {}
    for constraint in model.constraints:
        fixed.setdefault(constraint.node, set()).add(constraint.dof)
    for node, dofs in fixed.items():
        x, y = nodes[node].x, nodes[node].y
        figure.add_trace(
            go.Scatter(
                x=[x],
                y=[y],
                mode="markers",
                marker=dict(
                    symbol="square" if len(dofs) == 3 else "triangle-up", size=18, color="#1f3e50"
                ),
                name="Fixed support" if len(dofs) == 3 else "Zero DOF support",
                text=[", ".join(dof.name for dof in sorted(dofs))],
                hovertemplate="Node " + str(node) + "<br>%{text}=0<extra></extra>",
            )
        )
    for node in monitors:
        if node not in nodes:
            raise ValueError("Measurement node not in model.")
        marker_point = point(node)
        figure.add_trace(
            go.Scatter(
                x=[marker_point[0]],
                y=[marker_point[1]],
                mode="markers",
                marker=dict(symbol="circle-open", size=17, color="#147d75", line=dict(width=2)),
                name=f"Measurement node {node}",
                hovertemplate=(
                    f"Node {node}<br>UX={q[offsets[node]]:.5g} "
                    f"m<br>UY={q[offsets[node] + 1]:.5g} m<extra></extra>"
                ),
            )
        )
    # Spring endpoints and arms follow the same rigid offset kinematics as assembly.
    for mount in model.mounts:
        a = point(mount.node_a, mount.offset_a)
        b = (
            point(mount.node_b, mount.offset_b)
            if mount.node_b is not None
            else (
                nodes[mount.node_a].x + mount.offset_a[0],
                nodes[mount.node_a].y + mount.offset_a[1],
            )
        )
        for owner, attachment in ((mount.node_a, a), (mount.node_b, b)):
            if owner is not None:
                center = point(owner)
                figure.add_trace(
                    go.Scatter(
                        x=[center[0], attachment[0]],
                        y=[center[1], attachment[1]],
                        mode="lines",
                        line=dict(color="#718895", dash="dash"),
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
        force = (
            ""
            if mount_forces_N is None
            else f"<br>Computed scalar force={mount_forces_N[mount.id]:.5g} N"
        )
        if mount_forces_N is not None and abs(mount_forces_N[mount.id]) > 1e-10 * max(
            max(abs(v) for v in mount_forces_N.values()), 1e-30
        ):
            value = mount_forces_N[mount.id]
            angle = np.deg2rad(mount.angle_degrees)
            sign = 1 if value > 0 else -1
            figure.add_annotation(
                x=b[0],
                y=b[1],
                ax=-35 * np.cos(angle) * sign,
                ay=35 * np.sin(angle) * sign,
                axref="pixel",
                ayref="pixel",
                showarrow=True,
                arrowhead=3,
                arrowcolor="#bd7139",
                text=f"Mount {mount.id}: {value:.4g} N",
                font=dict(color="#9b5b2a", size=10),
            )
        figure.add_trace(
            go.Scatter(
                x=[a[0], b[0]],
                y=[a[1], b[1]],
                mode="lines+markers",
                line=dict(color="#bd7139", width=3),
                marker=dict(symbol="hourglass-open", size=15, color="#bd7139"),
                name=f"Mount {mount.id}" + (" → ground" if mount.node_b is None else " → rail"),
                hovertemplate=(
                    f"k={mount.stiffness:.5g} N/m; c={mount.damping:.5g} N "
                    f"s/m{force}<br>Symbolic spring/dashpot; reference sites may coincide"
                    "<extra></extra>"
                ),
            )
        )
    for body in model.nodal_masses:
        center = point(body.node, body.offset)
        ref = point(body.node)
        radius = np.sqrt(body.inertia_z / body.mass) if body.mass else 0.0
        angle = np.linspace(0, 2 * np.pi, 41)
        if overlay:
            reference_center = (
                nodes[body.node].x + body.offset[0],
                nodes[body.node].y + body.offset[1],
            )
            figure.add_trace(
                go.Scatter(
                    x=reference_center[0] + radius * np.cos(angle),
                    y=reference_center[1] + radius * np.sin(angle),
                    mode="lines",
                    line=dict(color="#8d9ca9", dash="dot", width=1),
                    name="Undeformed motor inertia glyph",
                    hoverinfo="skip",
                )
            )
        figure.add_trace(
            go.Scatter(
                x=center[0] + radius * np.cos(angle),
                y=center[1] + radius * np.sin(angle),
                mode="lines",
                fill="toself",
                fillcolor="rgba(68,100,123,.08)",
                line=dict(color="#44647b", width=2),
                name="Rigid motor inertia glyph",
                hovertemplate=(
                    f"m={body.mass:g} kg; Jz(COM)={body.inertia_z:g} kg m²<br>Radius "
                    f"of gyration={radius:.5g} m; not CAD outline<extra></extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[ref[0], center[0]],
                y=[ref[1], center[1]],
                mode="lines+markers",
                line=dict(color="#44647b", dash="dash"),
                marker=dict(symbol="cross", size=12),
                name="Motor COM / rigid attachment",
                hovertemplate=f"COM offset={body.offset} m<extra></extra>",
            )
        )
        spoke = point(body.node, (body.offset[0] + radius, body.offset[1]))
        figure.add_trace(
            go.Scatter(
                x=[center[0], spoke[0]],
                y=[center[1], spoke[1]],
                mode="lines",
                line=dict(color="#44647b", width=2),
                showlegend=False,
                hovertemplate=(
                    "Rigid-body orientation (magnified infinitesimal rotation)<extra></extra>"
                ),
            )
        )
    for load in model.loads if loads is None else loads:
        x, y = point(load.node)
        magnitude = float(np.hypot(load.fx, load.fy))
        if magnitude:
            figure.add_annotation(
                x=x,
                y=y,
                ax=-55 * load.fx / magnitude,
                ay=55 * load.fy / magnitude,
                axref="pixel",
                ayref="pixel",
                text=f"F=({load.fx:.4g}, {load.fy:.4g}) N",
                showarrow=True,
                arrowhead=3,
                arrowsize=1.2,
                arrowwidth=2,
                arrowcolor="#ba4b37",
                font=dict(color="#9b3e2e"),
            )
        else:
            figure.add_annotation(x=x, y=y, text="", visible=False, showarrow=False)
        if load.mz:
            figure.add_annotation(
                x=x,
                y=y,
                text=f"{'↺' if load.mz > 0 else '↻'} Mz={load.mz:.4g} N m",
                showarrow=False,
                yshift=30,
            )
        else:
            figure.add_annotation(x=x, y=y, text="", visible=False, showarrow=False)
    subtitle = "Arbitrary modal amplitude" if modal else f"Physical deformation ×{scale:g}"
    figure.update_layout(
        template="plotly_white",
        height=560,
        title=dict(
            text=(
                f"{title}<br><sup>{subtitle} · "
                f"{'deformed' if deformed else 'undeformed axes'} · sampled min "
                f"{values.min():.5g}, max {values.max():.5g} {unit}</sup>"
            ),
            font=dict(size=18),
        ),
        xaxis_title="Global X [m]",
        yaxis_title="Global Y [m]",
        coloraxis=dict(
            colorscale="RdBu_r" if signed else "Viridis",
            cmin=-bound if signed else 0,
            cmax=bound,
            cmid=0 if signed else None,
            colorbar=dict(title=f"{field}<br>[{unit}]"),
        ),
        legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
        margin=dict(l=30, r=70, t=85, b=65),
        hovermode="closest",
    )
    figure.update_yaxes(scaleanchor="x", scaleratio=1)
    figure.update_layout(
        meta=dict(
            field=field,
            fiber=fiber,
            display_scale=scale,
            physical_min_SI=None if modal else float(values.min() / factor),
            physical_max_SI=None if modal else float(values.max() / factor),
            modal_arbitrary=modal,
        )
    )
    return figure


def state_animation(
    model: FrameModel,
    states: Matrix,
    labels: tuple[str, ...],
    scale: float,
    *,
    loads: tuple[NodalLoad, ...] = (),
    monitors: tuple[int, ...] = (),
    modal: bool = False,
    times: Matrix | None = None,
    response: Matrix | None = None,
    response_unit: Literal["m", "rad"] = "m",
    force_states: Matrix | None = None,
) -> Any:
    """At most 60 real states; synchronized physical response cursor when supplied.

    Playback timing is illustrative. Modal/phasor cycles are user display phases.
    """
    if states.ndim != 2 or not 2 <= len(states) <= 60 or len(labels) != len(states):
        raise ValueError("Animation requires 2–60 full states with matching labels.")
    if (times is None) != (response is None) or (times is not None and len(times) != len(states)):
        raise ValueError("Animation cursor needs one physical time and response per state.")
    if response_unit not in ("m", "rad"):
        raise ValueError("Response unit must be m or rad.")
    if (
        times is not None
        and response is not None
        and (
            times.ndim != 1
            or response.ndim != 1
            or len(response) != len(states)
            or not np.all(np.isfinite(times))
            or not np.all(np.isfinite(response))
            or np.any(np.diff(times) <= 0)
        )
    ):
        raise ValueError("Cursor histories must be finite, matching and strictly chronological.")
    if force_states is not None and force_states.shape != states.shape:
        raise ValueError("Force states must match full displacement state shape.")
    ids = assemble(model).node_ids
    reference = (
        float(np.max(np.linalg.norm(states.reshape(len(states), -1, 3)[:, :, :2], axis=2))) or 1.0
    )

    def frame_loads(i: int) -> tuple[NodalLoad, ...]:
        if force_states is None:
            return loads
        return tuple(
            NodalLoad(
                node=node,
                fx=float(force_states[i, 3 * j]),
                fy=float(force_states[i, 3 * j + 1]),
                mz=float(force_states[i, 3 * j + 2]),
            )
            for j, node in enumerate(ids)
        )

    snapshots = [
        engineering_viewport(
            model,
            state,
            scale,
            loads=frame_loads(i),
            monitors=monitors,
            title=label,
            modal=modal,
            modal_reference=reference,
        )
        for i, (state, label) in enumerate(zip(states, labels, strict=True))
    ]
    figure = snapshots[0]
    # A fixed color range and geometry range avoid flickering/rescaling across frames.
    bound = max(float(snapshot.layout.coloraxis.cmax) for snapshot in snapshots)
    figure.update_coloraxes(cmin=0, cmax=bound)
    xs: list[float] = []
    ys: list[float] = []
    for snapshot in snapshots:
        for trace in snapshot.data:
            xs.extend(float(v) for v in trace.x if v is not None)
            ys.extend(float(v) for v in trace.y if v is not None)
    extent = max(float(np.ptp(xs)), float(np.ptp(ys)), 0.1)
    pad = 0.08 * extent
    figure.update_xaxes(
        range=[min(xs) - pad, max(xs) + pad], domain=[0, 0.68] if times is not None else [0, 1]
    )
    figure.update_yaxes(range=[min(ys) - pad, max(ys) + pad])
    if times is not None and response is not None:
        if len(response) != len(states):
            raise ValueError("Cursor response length mismatch.")
        figure.add_trace(
            go.Scatter(
                x=times,
                y=response,
                name="Sampled physical response",
                xaxis="x2",
                yaxis="y2",
                line=dict(color="#147d75"),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[times[0]],
                y=[response[0]],
                name="Current time",
                xaxis="x2",
                yaxis="y2",
                marker=dict(color="#ba4b37", size=11),
                mode="markers",
            )
        )
        figure.update_layout(
            xaxis2=dict(domain=[0.78, 1], title="Time [s]"),
            yaxis2=dict(anchor="x2", title=f"Response [{response_unit}]"),
        )
    frames = []
    for i, snapshot in enumerate(snapshots):
        traces = list(snapshot.data)
        if times is not None and response is not None:
            traces.extend(
                [
                    figure.data[-2],
                    go.Scatter(
                        x=[times[i]],
                        y=[response[i]],
                        xaxis="x2",
                        yaxis="y2",
                        mode="markers",
                        marker=dict(color="#ba4b37", size=11),
                    ),
                ]
            )
        frames.append(
            go.Frame(
                data=traces,
                name=str(i),
                layout=go.Layout(
                    title=snapshot.layout.title, annotations=snapshot.layout.annotations
                ),
            )
        )
    figure.frames = frames
    figure.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                buttons=[
                    dict(
                        label="▶ Play",
                        method="animate",
                        args=[
                            None,
                            dict(
                                frame=dict(duration=80, redraw=True),
                                transition=dict(duration=0),
                                fromcurrent=True,
                            ),
                        ],
                    ),
                    dict(
                        label="❚❚ Pause",
                        method="animate",
                        args=[
                            [None],
                            dict(
                                mode="immediate",
                                frame=dict(duration=0, redraw=False),
                                transition=dict(duration=0),
                            ),
                        ],
                    ),
                ],
            )
        ],
        sliders=[
            dict(
                active=0,
                steps=[
                    dict(
                        label=label.split("·")[-1].strip(),
                        method="animate",
                        args=[
                            [str(i)],
                            dict(
                                mode="immediate",
                                frame=dict(duration=0, redraw=True),
                                transition=dict(duration=0),
                            ),
                        ],
                    )
                    for i, label in enumerate(labels)
                ],
            )
        ],
    )
    return figure
