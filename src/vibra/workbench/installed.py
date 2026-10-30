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
from vibra.studies.installed import InstalledConfig, run_installed_study
from vibra.studies.nvh import SupportDesign
from vibra.visualization.installed import installed_figures, installed_shape


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
        st.write("Run the installed investigation with illustrative motor and isolator properties.")
        return
    st.caption(
        "Results use last submitted inputs. Motor mass is additional to the distributed rail mass."
    )
    st.write(installed_conclusion(study))
    if not all(study.checks.values()):
        st.warning("Numerical study checks failed; inspect convergence before interpretation.")
    st.dataframe(
        [{"Topology": case.topology, **case.summary} for case in study.cases], hide_index=True
    )
    figures = installed_figures(study)
    tabs = st.tabs(
        ("Topology & modes", "Harmonic & transmission", "Transient", "Report & convergence")
    )
    with tabs[0]:
        selected = st.selectbox("Installed topology", tuple(case.topology for case in study.cases))
        case = next(case for case in study.cases if case.topology == selected)
        st.plotly_chart(
            installed_shape(case, np.zeros(3 * len(case.model.nodes)), 1), width="stretch"
        )
        st.caption(
            "Dotted links are massless rigid arms. Motor-to-rail mount points "
            "coincide undeformed; they are not ground springs. Root is fixed. "
            "Model is a planar idealization."
        )
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
        st.plotly_chart(
            installed_shape(case, case.modal.modes[:, mode - 1], 0.05 / pivot, modal=True),
            width="stretch",
        )
        st.caption(
            "Mode is mass normalized; displayed maximum generalized component is "
            "scaled to 0.05. Mixed m/rad components make display magnitude "
            "arbitrary. Modal frequencies exclude damping."
        )
        st.plotly_chart(installed_shape(case, case.static.displacement, 5), width="stretch")
        st.caption("Static deformation ×5. No strength/fatigue or geometric stiffening assessment.")
    with tabs[1]:
        for key in (
            "harmonic_motor",
            "harmonic_rail",
            "phase",
            "root_transmission",
            "mount_transmission",
        ):
            st.plotly_chart(figures[key], width="stretch")
        st.caption(
            "Peak cosine force; roots and rail transmitted forces include "
            "different inertia paths. Force ratios are not base-motion "
            "transmissibility. Finite sweeps can miss resonances."
        )
        st.dataframe(study.sensitivities, hide_index=True)
    with tabs[2]:
        for key in ("displacement", "root_reaction", "transmitted", "energy", "dissipation"):
            st.plotly_chart(figures[key], width="stretch")
        with st.expander("Velocity and acceleration histories"):
            st.plotly_chart(figures["velocity"], width="stretch")
            st.plotly_chart(figures["acceleration"], width="stretch")
        selected_t = st.slider(
            "Installed deformation time [s]",
            0.0,
            study.config.grid.duration,
            0.0,
            step=study.config.grid.time_step,
        )
        case = study.cases[2]
        index = int(round(selected_t / study.config.grid.time_step))
        st.plotly_chart(
            installed_shape(case, case.transient.displacement[index], 20), width="stretch"
        )
        st.caption(
            "Actual isolated FEM/rigid-body solution at selected time; physical "
            "displacement magnified ×20."
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
