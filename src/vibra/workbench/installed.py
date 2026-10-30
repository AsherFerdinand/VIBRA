"""Optional installed-system investigation within Automotive NVH Study."""

from typing import Literal

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.io.installed_report import (
    ASSUMPTIONS,
    installed_conclusion,
    installed_json,
    installed_markdown,
)
from vibra.solvers.transient import TimeGrid
from vibra.studies.installed import InstalledConfig, installed_model, run_installed_study
from vibra.studies.nvh import SupportDesign
from vibra.visualization.installed import installed_figures
from vibra.visualization.viewport import engineering_viewport, state_animation
from vibra.workbench.presentation import plot
from vibra.workbench.viewport import (
    cycle_view,
    model_preview,
    nodal_loads,
    recovered_mount_forces,
    static_view,
)


def workspace() -> None:
    st.caption(
        "A: bare rail · B: rigid motor attachment · C: separate motor on two relative mount pairs"
    )
    with st.sidebar.form("installed_inputs"):
        st.subheader("Common rail")
        length = st.number_input("Installed rail length [m]", min_value=0.15, value=0.45)
        depth = st.number_input(
            "Installed rail depth [m]", min_value=0.003, value=0.012, format="%.4f"
        )
        width = st.number_input(
            "Installed rail width [m]", min_value=0.005, value=0.025, format="%.4f"
        )
        meshes: tuple[Literal[4, 8, 16], ...] = (8, 4, 16)
        elements = st.selectbox("Installed rail elements", meshes)
        st.subheader("One additional rigid motor body")
        mass = st.number_input("Motor mass [kg]", min_value=0.01, value=12.0)
        inertia = st.number_input(
            "Motor Jz about COM [kg m²]", min_value=0.0001, value=0.08, format="%.5f"
        )
        height = st.number_input("COM height above rail tip [m]", min_value=0.0, value=0.08)
        span = st.number_input("Mount pair span [m]", min_value=0.001, value=0.12)
        st.subheader("Total properties across two mount sites")
        kx = st.number_input("Total mount Kx [N/m]", min_value=1.0, value=200000.0)
        ky = st.number_input("Total mount Ky [N/m]", min_value=1.0, value=80000.0)
        cx = st.number_input("Total mount Cx [N s/m]", min_value=0.0, value=30.0)
        cy = st.number_input("Total mount Cy [N s/m]", min_value=0.0, value=60.0)
        beta = st.number_input(
            "Common stiffness β [s]", min_value=0.0000001, value=0.00008, format="%.7f"
        )
        operating = st.number_input(
            "Installed operating assumption [Hz]", min_value=0.01, max_value=120.0, value=60.0
        )
        duration = st.number_input("Installed duration [s]", min_value=0.04, value=0.8)
        step = st.number_input(
            "Installed time step [s]", min_value=0.00001, value=0.0002, format="%.6f"
        )
        st.caption(
            "Same prescribed static −200 N, peak harmonic 2 N, half-sine −20 N / "
            "10 ms. Not measured motor loads. β acts on all stiffness, including "
            "mounts."
        )
        run = st.form_submit_button("Run installed motor study", type="primary")
    if run:
        try:
            config = InstalledConfig(
                rail=SupportDesign(length=length, height=depth, width=width),
                elements=elements,
                motor_mass_kg=mass,
                motor_inertia_kg_m2=inertia,
                motor_height_m=height,
                mount_span_m=span,
                stiffness_x_N_per_m=kx,
                stiffness_y_N_per_m=ky,
                damping_x_Ns_per_m=cx,
                damping_y_Ns_per_m=cy,
                stiffness_beta_s=beta,
                operating_hz=operating,
                grid=TimeGrid(duration=duration, time_step=step),
            )
            with st.spinner(
                "Solving installed assembly, sensitivities and displacement convergence…"
            ):
                st.session_state["installed_study"] = run_installed_study(config)
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("installed_study", None)
            st.error(str(exc))
    study = st.session_state.get("installed_study")
    if study is None:
        try:
            preview_config = InstalledConfig(
                rail=SupportDesign(length=length, height=depth, width=width),
                elements=elements,
                motor_mass_kg=mass,
                motor_inertia_kg_m2=inertia,
                motor_height_m=height,
                mount_span_m=span,
                stiffness_x_N_per_m=kx,
                stiffness_y_N_per_m=ky,
                damping_x_Ns_per_m=cx,
                damping_y_Ns_per_m=cy,
                stiffness_beta_s=beta,
            )
            preview, node = installed_model(preview_config, "isolated")
            model_preview(preview, monitors=(node, preview_config.elements), key="installed")
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.error(str(exc))
        st.write("Run the installed investigation with illustrative motor and isolator properties.")
        return
    st.caption(
        "Results use last submitted inputs. Motor mass is additional to the distributed rail mass."
    )
    st.write(installed_conclusion(study))
    if not all(study.checks.values()):
        st.warning("Numerical study checks failed; inspect convergence before interpretation.")
    selected = st.selectbox(
        "Installed topology", tuple(case.topology for case in study.cases), index=2
    )
    inspected = next(case for case in study.cases if case.topology == selected)
    scale_static = st.number_input("Installed static magnification [×]", min_value=0.0, value=5.0)
    body = inspected.model.nodal_masses[0] if inspected.model.nodal_masses else None
    vector = inspected.static.displacement
    physical_y = (
        (
            vector[inspected.static.node_ids.index(body.node), 1]
            + body.offset[0] * vector[inspected.static.node_ids.index(body.node), 2]
        )
        if body
        else vector[-1, 1]
    )
    st.caption(
        f"Physical motor/interface Y = {physical_y * 1e3:.5g} mm; "
        f"rail tip Y = {vector[study.config.elements, 1] * 1e3:.5g} mm. "
        "Beam contours exclude motor and springs."
    )
    static_view(
        inspected.model,
        inspected.static,
        scale_static,
        key="installed_static",
        monitors=(inspected.force_node,),
    )
    st.caption(
        "Motor outline is an inertia glyph of radius sqrt(Jz/m), not CAD geometry; "
        "arms are massless rigid kinematics. Only beam members receive stress "
        "contours."
    )
    with st.expander("Engineering comparison table"):
        st.dataframe(
            [{"Topology": case.topology, **case.summary} for case in study.cases], hide_index=True
        )
    figures = installed_figures(study)
    tabs = st.tabs(
        ("Topology & modes", "Harmonic & transmission", "Transient", "Report & convergence")
    )
    with tabs[0]:
        case = inspected
        st.dataframe(
            [
                {
                    "topology": case.topology,
                    "mode": i + 1,
                    "Hz": float(f),
                    "family": case.modal.families[i],
                }
                for case in study.cases
                for i, f in enumerate(case.modal.frequencies_hz)
            ],
            hide_index=True,
        )
        mode = st.slider("Installed mode number", 1, 6, 1)
        pivot = float(np.max(abs(case.modal.modes[:, mode - 1])))
        plot(
            engineering_viewport(
                case.model,
                case.modal.modes[:, mode - 1],
                0.05 / pivot,
                loads=(),
                modal=True,
                title=(
                    f"{case.topology} · mode {mode} · "
                    f"{case.modal.frequencies_hz[mode - 1]:.5g} Hz · "
                    f"{case.modal.families[mode - 1]}"
                ),
            ),
            width="stretch",
        )
        cycle_view(
            case.model,
            case.modal.modes[:, mode - 1],
            0.05 / pivot,
            label=f"{case.topology} · mode {mode} · {case.modal.frequencies_hz[mode - 1]:.5g} Hz",
            key="installed_mode",
            modal=True,
        )
        st.caption(
            "Modes exclude damping; display amplitude is arbitrary, not an operating displacement."
        )
    with tabs[1]:
        case = inspected
        sample = st.slider(
            "Installed frequency sample",
            0,
            len(case.harmonic.frequencies_hz) - 1,
            int(np.argmin(abs(case.harmonic.frequencies_hz - study.config.operating_hz))),
        )
        h = case.harmonic
        amplitude = float(abs(h.displacement[sample, 3 * case.force_node + 1]))
        st.write(
            f"Excitation {h.frequencies_hz[sample]:.5g} Hz · motor/interface UY peak "
            f"{amplitude:.5g} m · phase "
            f"{np.angle(h.displacement[sample, 3 * case.force_node + 1], deg=True):.4g}°"
        )
        hs = st.number_input("Installed harmonic magnification [×]", min_value=0.0, value=1000.0)
        plot(
            engineering_viewport(
                case.model,
                np.real(h.displacement[sample]),
                hs,
                loads=nodal_loads(case.model, np.real(h.force_phasor)),
                title=f"{case.topology} · harmonic snapshot at phase 0°",
                mount_forces_N=recovered_mount_forces(
                    case.model,
                    np.real(h.displacement[sample]),
                    np.real(1j * 2 * np.pi * h.frequencies_hz[sample] * h.displacement[sample]),
                    study.config.stiffness_beta_s,
                ),
            ),
            width="stretch",
        )
        cycle_view(
            case.model,
            h.displacement[sample],
            hs,
            label=f"{case.topology} · {h.frequencies_hz[sample]:.5g} Hz",
            key="installed_harmonic",
            force=h.force_phasor,
        )
        for key in (
            "harmonic_motor",
            "harmonic_rail",
            "phase",
            "root_transmission",
            "mount_transmission",
        ):
            plot(figures[key], width="stretch")
        st.caption(
            "Peak cosine force; roots and rail transmitted forces include "
            "different inertia paths. Force ratios are not base-motion "
            "transmissibility. Finite sweeps can miss resonances."
        )
        st.dataframe(study.sensitivities, hide_index=True)
    with tabs[2]:
        selected_t = st.slider(
            "Installed deformation time [s]",
            0.0,
            study.config.grid.duration,
            0.0,
            step=study.config.grid.time_step,
        )
        case = inspected
        index = int(round(selected_t / study.config.grid.time_step))
        plot(
            engineering_viewport(
                case.model,
                case.transient.displacement[index],
                20,
                loads=nodal_loads(case.model, case.transient.force_right[index]),
                title=f"{case.topology} · t={case.transient.time[index]:.6g} s",
                mount_forces_N=recovered_mount_forces(
                    case.model,
                    case.transient.displacement[index],
                    case.transient.velocity[index],
                    study.config.stiffness_beta_s,
                ),
            ),
            width="stretch",
        )
        st.caption("Actual installed FEM/rigid-body solution; physical displacement magnified ×20.")
        figures["displacement"].add_vline(x=float(case.transient.time[index]), line_dash="dash")
        for key in ("displacement", "root_reaction", "transmitted", "energy", "dissipation"):
            plot(figures[key], width="stretch")
        with st.expander("Velocity and acceleration histories"):
            plot(figures["velocity"], width="stretch")
            plot(figures["acceleration"], width="stretch")
        if st.checkbox("Animate installed transient"):
            t = case.transient
            indices = np.unique(np.linspace(0, len(t.time) - 1, min(30, len(t.time)), dtype=int))
            plot(
                state_animation(
                    case.model,
                    t.displacement[indices],
                    tuple(f"{case.topology} · t={t.time[i]:.6g} s" for i in indices),
                    20,
                    times=t.time[indices],
                    response=t.displacement[indices, 3 * case.force_node + 1],
                    force_states=t.force_right[indices],
                ),
                width="stretch",
            )
    with tabs[3]:
        st.json(study.checks)
        st.dataframe(study.convergence, hide_index=True)
        for text in ASSUMPTIONS:
            st.write(text)
        for case in study.cases:
            for note in case.transient.numerical_warnings:
                st.write(case.topology + ": " + note)
        try:
            st.download_button(
                "Export installed JSON",
                installed_json(study),
                file_name="vibra-installed-study.json",
                mime="application/json",
            )
            st.download_button(
                "Export installed Markdown",
                installed_markdown(study),
                file_name="vibra-installed-study.md",
                mime="text/markdown",
            )
        except ValueError as exc:
            st.error(str(exc))
