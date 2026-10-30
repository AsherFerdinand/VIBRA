"""Automotive NVH investigation controls and engineering interpretation."""

from dataclasses import asdict

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.io.nvh_report import ASSUMPTIONS, design_conclusion, study_json, study_markdown
from vibra.signals.fem import Quantity
from vibra.solvers.harmonic import FrequencySweep
from vibra.solvers.transient import TimeGrid
from vibra.studies.nvh import NVHConfig, SupportDesign, run_nvh_study
from vibra.visualization.nvh import comparison_figures, geometry_plot
from vibra.visualization.plots import beam_shape, bending_moment
from vibra.workbench.installed import workspace as installed_workspace


def workspace() -> None:
    st.subheader("Automotive NVH Study")
    investigation = st.radio(
        "Investigation", ("Bare rail A/B (0.5 reference)", "Installed motor A/B/C"), horizontal=True
    )
    if investigation == "Installed motor A/B/C":
        installed_workspace()
        return
    st.caption(
        "Equivalent motor-interface support rail · prescribed forces · bare rail inertia only"
    )
    st.info(
        "This equivalent rail is not a production bracket, installed motor model, "
        "strength assessment or acoustic prediction."
    )
    with st.sidebar.form("nvh_study_inputs"):
        parameters = {}
        for key, name, height in (("A", "Baseline A", 0.012), ("B", "Modified B", 0.015)):
            st.subheader(name)
            parameters[key] = dict(
                name=name,
                length=st.number_input(
                    f"{key}: length [m]", min_value=0.15, max_value=1.0, value=0.45
                ),
                width=st.number_input(
                    f"{key}: width [m]", min_value=0.005, max_value=0.06, value=0.025, format="%.4f"
                ),
                height=st.number_input(
                    f"{key}: bending depth [m]",
                    min_value=0.003,
                    max_value=0.03,
                    value=height,
                    format="%.4f",
                ),
                young_modulus=st.number_input(
                    f"{key}: E [GPa]", min_value=1.0, max_value=300.0, value=210.0
                )
                * 1e9,
                density=st.number_input(
                    f"{key}: density [kg/m³]", min_value=500.0, max_value=15000.0, value=7850.0
                ),
            )
        st.subheader("Common load cases")
        count = st.selectbox("Elements per design", (8, 4, 16))
        static = st.number_input("Static tip force [N]", value=-200.0)
        harmonic = st.number_input("Harmonic peak force [N]", min_value=0.001, value=2.0)
        order = st.number_input("Assumed excitation order", min_value=0.1, value=2.0)
        rpm = st.number_input("Operating rotation speed [rpm]", min_value=0.0, value=1800.0)
        stop = st.number_input("Sweep stop frequency [Hz]", min_value=1.0, value=160.0)
        excitation = st.selectbox("Dynamic force station x/L", (1.0, 0.5, 0.25))
        monitor = st.selectbox("Monitor station x/L", (1.0, 0.5, 0.25))
        alpha = st.number_input("Rayleigh α [1/s]", min_value=0.0, value=4.0)
        beta = st.number_input("Rayleigh β [s]", min_value=0.0, value=0.00008, format="%.7f")
        pulse = st.number_input("Half-sine pulse force [N]", value=-20.0)
        width = st.number_input("Pulse width [s]", min_value=0.0001, value=0.01, format="%.6f")
        duration = st.number_input(
            "Transient duration [s]", min_value=0.1, value=0.4, format="%.6f"
        )
        step = st.number_input("Base time step [s]", min_value=0.00001, value=0.0001, format="%.6f")
        st.caption(
            "Runs 4/8/16-element and dt/dt÷2/dt÷4 checks for both designs. "
            "Forces and damping are illustrative assumptions."
        )
        run = st.form_submit_button("Run engineering study", type="primary", width="stretch")
    if run:
        try:
            config = NVHConfig.model_validate(
                {
                    "baseline": SupportDesign.model_validate(parameters["A"]),
                    "modified": SupportDesign.model_validate(parameters["B"]),
                    "elements": count,
                    "static_force_N": static,
                    "harmonic_force_N": harmonic,
                    "excitation_order": order,
                    "operating_rpm": rpm,
                    "sweep": FrequencySweep(stop_hz=stop, points=401),
                    "excitation_fraction": excitation,
                    "monitor_fraction": monitor,
                    "damping": {"kind": "rayleigh", "alpha": alpha, "beta": beta},
                    "pulse_force_N": pulse,
                    "pulse_width_s": width,
                    "grid": TimeGrid(duration=duration, time_step=step),
                }
            )
            with st.spinner(
                "Running verified solvers, parameter studies and numerical convergence…"
            ):
                computed = run_nvh_study(config)
            st.session_state["nvh_study"] = computed
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("nvh_study", None)
            st.error(str(exc))
    study = st.session_state.get("nvh_study")
    if study is None:
        st.write("Run the baseline/modified investigation or edit its assumptions in the sidebar.")
        return
    st.caption("Results use the last submitted complete study inputs. Submit again after edits.")
    st.write(design_conclusion(study))
    if not all(study.verification_checks.values()):
        st.warning(
            "Some study checks failed; inspect convergence and limitations before interpretation."
        )
    figures = comparison_figures(study)
    tabs = st.tabs(
        ["Model & static", "Modes & harmonic", "Transient", "Signals", "Convergence & report"]
    )
    with tabs[0]:
        st.plotly_chart(geometry_plot(study), width="stretch")
        st.caption(
            "Neutral axes overlap for equal lengths; section depth is the default change. "
            "Root is fixed; static load is at the free tip."
        )
        st.plotly_chart(figures["static"], width="stretch")
        metrics = (
            ("Rail mass [kg]", "mass_kg", 1.0),
            ("Maximum static displacement [mm]", "maximum_static_translation_m", 1000.0),
            ("First natural frequency [Hz]", "first_natural_hz", 1.0),
            ("Operating harmonic amplitude [mm]", "operating_amplitude_m", 1000.0),
            ("Pulse peak displacement [mm]", "transient_peak_displacement_m", 1000.0),
            ("Post-pulse acceleration RMS [m/s²]", "acceleration_signal_rms_m_per_s2", 1.0),
        )
        st.dataframe(
            [
                {
                    "Quantity": label,
                    "Baseline A": getattr(study.baseline.summary, field) * scale,
                    "Modified B": getattr(study.modified.summary, field) * scale,
                }
                for label, field, scale in metrics
            ],
            hide_index=True,
        )
        with st.expander("Detailed numerical summaries"):
            st.dataframe(
                [
                    {"Design": item.design.name, **asdict(item.summary)}
                    for item in (study.baseline, study.modified)
                ],
                hide_index=True,
            )
        design_choice = st.selectbox("Inspect static design", ("Baseline A", "Modified B"))
        item = study.baseline if design_choice == "Baseline A" else study.modified
        st.plotly_chart(beam_shape(item.model, item.static.displacement, 5), width="stretch")
        st.plotly_chart(bending_moment(item.model, item.static), width="stretch")
        st.caption(
            "Deformation shown ×5. Moments/end forces are not strength or fatigue assessment."
        )
    with tabs[1]:
        st.write(
            f"Operating order = {study.config.excitation_order:g} × "
            f"{study.config.operating_rpm:g}/60 = {study.config.operating_frequency_hz:g} Hz; "
            "this is not rotation frequency alone."
        )
        st.plotly_chart(figures["harmonic_amplitude"], width="stretch")
        st.plotly_chart(figures["harmonic_phase"], width="stretch")
        st.caption(
            "Dotted lines: first natural references. Maxima are sampled; "
            "force magnitude is assumed constant over frequency."
        )
        st.dataframe(
            [
                {"Design": name, **asdict(row)}
                for name, rows in study.sensitivities.items()
                for row in rows
            ],
            hide_index=True,
        )
        selected = st.selectbox("Mode design", ("Baseline A", "Modified B"))
        item = study.baseline if selected == "Baseline A" else study.modified
        st.dataframe(
            {
                "Mode": range(1, len(item.modal.frequencies_hz) + 1),
                "Frequency [Hz]": item.modal.frequencies_hz,
                "Family": item.modal.families,
            },
            hide_index=True,
        )
        mode = st.selectbox(
            "Mode shape",
            range(len(item.modal.frequencies_hz)),
            format_func=lambda i: f"Mode {i + 1}",
        )
        shape = item.modal.modes[:, mode].reshape(-1, 3)
        scale = 0.05 * item.design.length / float(np.max(np.linalg.norm(shape[:, :2], axis=1)))
        st.plotly_chart(beam_shape(item.model, shape, scale, modal=True), width="stretch")
        st.caption(
            f"Mass-normalized eigenvector ×{scale:.5g}, arbitrary display amplitude. "
            "Bending: global Y/RZ; axial: global X. No out-of-plane modes."
        )
        st.dataframe([asdict(row) for row in study.parameter_variations], hide_index=True)
        st.caption(
            "Length, width, depth, E and density vary one at a time by ±10%. "
            "Analytical scaling ratios are included."
        )
    with tabs[2]:
        st.caption(
            "Dynamic signals/reactions perturb static equilibrium. "
            "Static and dynamic responses superpose linearly; no prestress stiffness."
        )
        for key in ("displacement", "velocity", "acceleration", "energy", "reactions"):
            st.plotly_chart(figures[key], width="stretch")
        st.caption(
            "D is cumulative algorithm-consistent dissipation. "
            "JSON retains work, balance and dynamic reactions for each design."
        )
    with tabs[3]:
        quantities: tuple[Quantity, ...] = ("displacement", "acceleration")
        quantity = st.selectbox("Signal quantity", quantities)
        st.plotly_chart(figures[f"fft_{quantity}"], width="stretch")
        st.plotly_chart(figures[f"psd_{quantity}"], width="stretch")
        for item in (study.baseline, study.modified):
            signal = item.signals[quantity].spectrum
            st.write(
                f"{item.design.name}: fs={signal.sampling.sampling_frequency_hz:g} Hz, "
                f"df={signal.sampling.frequency_resolution_hz:.5g} Hz; mean removed, Hann; "
                f"RMS={signal.processed_metrics.rms:.6g} {signal.unit}."
            )
        st.caption(
            "Natural markers are references. Duration, damping and leakage affect peaks. "
            "No experimental modal identification is performed."
        )
    with tabs[4]:
        st.dataframe(
            [
                {"Design": conv.design_name, "Study": kind, **asdict(row)}
                for conv in study.convergence
                for kind, rows in (("time", conv.time), ("mesh", conv.mesh))
                for row in rows
            ],
            hide_index=True,
        )
        st.caption(
            "Differences use common times and a computed fine reference. "
            "Final zero is by definition, not exact transient truth."
        )
        st.json(study.verification_checks)
        for assumption in ASSUMPTIONS:
            st.write(assumption)
        for item in (study.baseline, study.modified):
            for note in item.transient.numerical_warnings:
                st.write(item.design.name + ": " + note)
        try:
            st.download_button(
                "Export engineering JSON",
                study_json(study),
                file_name="vibra-nvh-study.json",
                mime="application/json",
            )
            st.download_button(
                "Export engineering Markdown",
                study_markdown(study),
                file_name="vibra-nvh-study.md",
                mime="text/markdown",
            )
        except ValueError as exc:
            st.error(str(exc))
