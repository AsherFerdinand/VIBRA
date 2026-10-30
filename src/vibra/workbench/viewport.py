"""Shared view controls and result-specific engineering interpretation."""

from typing import Literal

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from vibra.core.assembly import assemble
from vibra.core.element import Matrix
from vibra.core.models import FrameModel, NodalLoad
from vibra.io.reports import engineering_report
from vibra.postprocessing.beam import recover_stress, sample_beam
from vibra.solvers.harmonic import ComplexMatrix
from vibra.solvers.static import StaticResult
from vibra.visualization.viewport import CONTOURS, Contour, engineering_viewport, state_animation
from vibra.workbench.presentation import plot


def nodal_loads(model: FrameModel, vector: Matrix) -> tuple[NodalLoad, ...]:
    ids = assemble(model).node_ids
    return tuple(
        NodalLoad(
            node=node,
            fx=float(vector[3 * i]),
            fy=float(vector[3 * i + 1]),
            mz=float(vector[3 * i + 2]),
        )
        for i, node in enumerate(ids)
    )


def recovered_mount_forces(
    model: FrameModel, q: Matrix, v: Matrix, beta: float
) -> dict[int, float]:
    """Recover explicit mount plus beta*k viscosity from the existing assembled maps."""
    a = assemble(model)
    return {
        entry.mount.id: float(
            entry.mount.stiffness * (entry.extension @ q.reshape(-1))
            + (entry.mount.damping + beta * entry.mount.stiffness)
            * (entry.extension @ v.reshape(-1))
        )
        for entry in a.mounts
    }


def model_preview(
    model: FrameModel,
    *,
    loads: tuple[NodalLoad, ...] | None = None,
    monitors: tuple[int, ...] = (),
    key: str = "model",
) -> None:
    figure = engineering_viewport(
        model,
        np.zeros(3 * len(model.nodes)),
        loads=loads,
        monitors=monitors,
        title="Model preview · not solved",
    )
    figure.data = tuple(
        trace
        for trace in figure.data
        if trace.name
        not in (
            "Critical |field| (sampled)",
            "Max translation (sampled)",
            "Critical section stress (±fiber)",
        )
    )
    for trace in figure.data:
        if getattr(trace.marker, "coloraxis", None):
            trace.marker.coloraxis = None
            trace.marker.color = "#147d75"
            trace.hovertemplate = (
                f"{trace.name}<br>Local x=%{{customdata[0]:.5g}} m"
                "<br>Geometry preview; response not solved<extra></extra>"
            )
    figure.update_layout(coloraxis_showscale=False, title_text="Model preview · not solved")
    plot(
        figure,
        width="stretch",
        key=key + "_preview",
    )
    st.caption(
        "Model → Loads → Solve: support squares fix the labeled DOFs; arrows show the "
        "submitted force direction. Solve to inspect physical response and beam "
        "stress."
    )


def static_view(
    model: FrameModel,
    result: StaticResult,
    scale: float,
    *,
    key: str = "static",
    monitors: tuple[int, ...] = (),
) -> None:
    st.subheader("Visualize · section response")
    a, b, c = st.columns((2, 1, 1))
    field: Contour = a.selectbox("Contour field", CONTOURS, key=key + "_field")
    fibers: tuple[Literal["top", "bottom"], ...] = ("top", "bottom")
    fiber = b.selectbox(
        "Section fiber",
        fibers,
        key=key + "_fiber",
        help="Top is local +y; bottom is local −y. Applies to bending/combined stress.",
    )
    overlay = c.checkbox("Undeformed overlay", value=True, key=key + "_overlay")
    deformed = c.checkbox("Show deformation", value=True, key=key + "_deformed")
    figure = engineering_viewport(
        model,
        result.displacement,
        scale,
        field,
        fiber,
        overlay,
        deformed,
        monitors=monitors,
        title="Static beam response",
        mount_forces_N=result.mount_forces_N,
    )
    plot(figure, width="stretch", key=key + "_viewport")
    stress = recover_stress(model, result.displacement)
    critical = stress.critical_absolute
    fields = sample_beam(model, result.displacement)
    displacement = max(
        (
            float(np.linalg.norm(field.displacement_m[index])),
            field.element_id,
            float(field.local_x_m[index]),
        )
        for field in fields
        for index in range(len(field.local_x_m))
    )
    st.info(
        f"Interpret · maximum sampled beam displacement {displacement[0] * 1e3:.5g} mm "
        f"at element {displacement[1]}, local x={displacement[2]:.5g} m. "
        f"Maximum absolute section normal stress is {abs(critical.normal_stress_Pa) / 1e6:.5g} MPa "
        f"at element {critical.element_id}, local x={critical.local_x_m:.5g} m, "
        f"local fiber y={critical.fiber_y_m:.5g} m. These critical locations can differ."
    )
    peak_moment = max(float(np.max(abs(item.bending_moment_Nm))) for item in fields)
    y_min = min(float(item.displacement_m[:, 1].min()) for item in fields)
    y_max = max(float(item.displacement_m[:, 1].max()) for item in fields)
    st.write(
        f"Direction · global UY spans {y_min * 1e3:.5g} to {y_max * 1e3:.5g} mm; "
        "negative Y is downward. "
        f"Peak |bending moment| is {peak_moment:.5g} N m. "
        "Bending stress follows moment and fiber distance, not displacement."
    )
    st.caption(
        "Stress is σxx=N/A−M·y/I, tension positive; section extrema use both ±c "
        "fibers. Colors and hover values are physical; magnification changes "
        "coordinates only. Beam theory does not resolve 3D/contact stresses or "
        "establish yield/fatigue safety. Motor and spring glyphs have no stress "
        "contour."
    )
    with st.expander("Axial force · shear force · bending moment"):
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=False,
            subplot_titles=("Axial tension N", "Shear V=dM/dx", "Bending M=EI v″"),
        )
        for field_data in fields:
            for row, values in enumerate(
                (field_data.axial_force_N, field_data.shear_force_N, field_data.bending_moment_Nm),
                start=1,
            ):
                fig.add_trace(
                    go.Scatter(
                        x=field_data.local_x_m,
                        y=values,
                        name=f"Element {field_data.element_id}",
                        legendgroup=str(field_data.element_id),
                        showlegend=row == 1,
                    ),
                    row=row,
                    col=1,
                )
        for row, unit in enumerate(("N", "N", "N m"), start=1):
            fig.update_yaxes(title_text=unit, row=row, col=1)
            fig.update_xaxes(title_text="Local element x [m]", row=row, col=1)
        fig.update_layout(template="plotly_white", height=650)
        plot(fig, width="stretch")
    st.download_button(
        "Export beam section stress (JSON)",
        engineering_report("Elastic beam section recovery", model, stress),
        file_name="vibra-section-stress.json",
        mime="application/json",
        key=key + "_stress_export",
    )


def cycle_view(
    model: FrameModel,
    phasor: Matrix | ComplexMatrix,
    scale: float,
    *,
    label: str,
    key: str,
    modal: bool = False,
    force: Matrix | None = None,
) -> None:
    if st.checkbox(
        "Animate mode shape" if modal else "Animate harmonic cycle", key=key + "_animate"
    ):
        phases = np.linspace(0, 2 * np.pi, 25)
        states = np.real(np.exp(1j * phases[:, None]) * phasor.reshape(1, -1))
        forces = (
            None if force is None else np.real(np.exp(1j * phases[:, None]) * force.reshape(1, -1))
        )
        plot(
            state_animation(
                model,
                states,
                tuple(f"{label} · phase {np.rad2deg(p):.0f}°" for p in phases),
                scale,
                modal=modal,
                force_states=forces,
            ),
            width="stretch",
            key=key + "_animation",
        )
        st.caption(
            "Play/Pause and phase slider use actual FEM eigenvector/complex states. "
            "Playback speed is illustrative. Modal amplitude is arbitrary; "
            "forced-response amplitude is physical before magnification."
        )
