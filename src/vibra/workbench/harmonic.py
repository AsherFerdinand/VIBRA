"""Harmonic controls and result inspection, isolated from existing workspaces."""

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import DOF, Material, Rectangle
from vibra.io.harmonic_report import harmonic_report
from vibra.solvers.harmonic import (
    Damping,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.visualization.harmonic import response_figures
from vibra.visualization.viewport import engineering_viewport
from vibra.workbench.viewport import cycle_view, model_preview, nodal_loads


def workspace() -> None:
    st.subheader("FEM Harmonic Response")
    st.caption("Steady-state peak phasors · (K + jωC − ω²M)U = F · fixed-root cantilever")
    kind = st.sidebar.selectbox("Damping model", ("rayleigh", "undamped", "mass", "stiffness"))
    with st.sidebar.form("harmonic_inputs"):
        st.subheader("Geometry & material")
        length = st.number_input("Length [m]", min_value=0.1, max_value=20.0, value=1.0)
        width = st.number_input("Section width [m]", min_value=0.001, value=0.02, format="%.4f")
        height = st.number_input(
            "Section bending depth [m]", min_value=0.001, value=0.02, format="%.4f"
        )
        young = st.number_input("Young's modulus [GPa]", min_value=0.001, value=210.0)
        density = st.number_input("Density [kg/m³]", min_value=0.001, value=7850.0)
        count = st.slider("Beam elements", 2, 32, 12)
        st.caption("Fixed root at node 0: ux = uy = rz = 0; nodes run from root to tip.")
        st.subheader("Excitation")
        load_node = st.number_input("Excitation node", min_value=0, max_value=count, value=count)
        load_dof = st.selectbox("Excitation DOF", ("UY", "UX", "RZ"))
        force = st.number_input("Peak force [N] / moment [N m]", min_value=0.0, value=1.0)
        load_phase = st.number_input("Load phase [deg]", value=0.0)
        st.caption("F(t) = amplitude × cos(2πft + load phase); amplitude is peak, not RMS.")
        st.subheader("Frequency sweep")
        start = st.number_input("Start frequency [Hz]", min_value=0.0, value=0.0)
        stop = st.number_input(
            "Stop frequency [Hz]", min_value=0.001, max_value=10000.0, value=60.0
        )
        points = st.slider("Frequency samples", 11, 1001, 401, step=10)
        st.subheader("Viscous damping")
        alpha = (
            st.number_input("α [1/s]", min_value=0.0, value=2.0)
            if kind in ("mass", "rayleigh")
            else 0.0
        )
        beta = (
            st.number_input("β [s]", min_value=0.0, value=0.00002, format="%.7f")
            if kind in ("stiffness", "rayleigh")
            else 0.0
        )
        st.caption("C = αM + βK. Coefficients are assumptions; modal ζ = α/(2ωn) + βωn/2.")
        st.subheader("Response locations")
        response_nodes = st.multiselect("Response nodes", range(count + 1), default=[count])
        response_dofs = st.multiselect("Response DOFs", ("UY", "UX", "RZ"), default=["UY"])
        run = st.form_submit_button("Run harmonic analysis", type="primary", width="stretch")
    if run:
        try:
            geometry = BeamGeometry(length=length)
            rectangle = Rectangle(width=width, height=height)
            material = Material(young_modulus=young * 1e9, density=density)
            model = cantilever(geometry, material, rectangle.section(), count, tip_force=0)
            sweep = FrequencySweep(start_hz=start, stop_hz=stop, points=points)
            case = HarmonicConfig(
                frequencies_hz=sweep.frequencies(),
                damping=Damping.model_validate({"kind": kind, "alpha": alpha, "beta": beta}),
                loads=(
                    HarmonicLoad(
                        node=load_node, dof=DOF[load_dof], amplitude=force, phase_degrees=load_phase
                    ),
                ),
                responses=tuple(
                    ResponseDOF(node=node, dof=DOF[dof])
                    for node in response_nodes
                    for dof in response_dofs
                ),
            )
            with st.spinner("Solving complex FEM frequency sweep…"):
                result = solve_harmonic(model, case)
            st.session_state["harmonic_solved"] = {
                "model": model,
                "config": case,
                "result": result,
                "geometry": geometry,
                "material": material,
                "rectangle": rectangle,
                "sweep": sweep,
            }
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("harmonic_solved", None)
            st.error(str(exc))
    saved = st.session_state.get("harmonic_solved")
    if saved is None:
        preview = cantilever(
            BeamGeometry(length=length),
            Material(young_modulus=young * 1e9, density=density),
            Rectangle(width=width, height=height).section(),
            count,
            tip_force=0,
        )
        load_vector = np.zeros(3 * (count + 1))
        load_vector[3 * load_node + int(DOF[load_dof])] = force
        model_preview(
            preview,
            loads=nodal_loads(preview, load_vector),
            monitors=tuple(response_nodes),
            key="harmonic",
        )
        st.info(
            "Define the beam, excitation, sweep, damping and response DOFs, then run the analysis."
        )
        return
    result = saved["result"]
    model, case = saved["model"], saved["config"]
    geometry, rectangle, material = saved["geometry"], saved["rectangle"], saved["material"]
    st.caption(
        f"Last submitted model: L = {geometry.length:g} m · section {rectangle.width:g} × "
        f"{rectangle.height:g} m · E = {material.young_modulus / 1e9:g} GPa · "
        f"ρ = {material.density:g} kg/m³ · {len(model.elements)} elements · fixed root. "
        "Submit again after editing inputs."
    )
    st.write(
        f"Damping: **{case.damping.kind}**, α = {case.damping.alpha:g} 1/s, "
        f"β = {case.damping.beta:g} s. Solver: direct complex LU with exact support elimination."
    )
    if geometry.length / rectangle.height < 10:
        st.warning(
            "L/h < 10: shear deformation may be significant; Euler–Bernoulli theory omits it."
        )
    if case.damping.alpha == 0 and case.damping.beta == 0:
        st.warning(
            "Undamped response is unbounded at an excited natural frequency. "
            "A sampled curve can miss the pole."
        )
    st.subheader("Complex-response deformation")
    response_column = st.selectbox(
        "Inspect response",
        range(len(result.response_dofs)),
        format_func=lambda i: result.response_dofs[i].label,
    )
    default_index = int(np.argmax(result.response_amplitude[:, response_column]))
    index = st.slider("Frequency sample", 0, len(result.frequencies_hz) - 1, default_index)
    time_phase = st.slider("Cycle phase θ [deg]", -180, 180, 0)
    magnitude = float(
        np.max(np.linalg.norm(result.displacement[index].reshape(-1, 3)[:, :2], axis=1))
    )
    default_scale = min(1000.0, 0.15 * geometry.length / magnitude) if magnitude else 1.0
    scale = st.number_input(
        "Displacement visualization scale [×]", min_value=0.0, value=default_scale
    )
    a, b, c = st.columns(3)
    a.metric("Excitation frequency [Hz]", f"{result.frequencies_hz[index]:.6g}")
    unit = "rad" if result.response_dofs[response_column].dof == DOF.RZ else "m"
    b.metric(
        f"Response amplitude [{unit}]", f"{result.response_amplitude[index, response_column]:.6g}"
    )
    c.metric(
        "Response phase [deg]",
        f"{np.rad2deg(result.phase_radians[index, response_column]):.5g}"
        if result.phase_defined[index, response_column]
        else "Undefined",
    )
    st.caption(
        "Actual phasor snapshot Re(U exp(jθ)), "
        "Hermite interpolated and magnified by the scale shown."
    )
    state = np.real(result.displacement[index] * np.exp(1j * np.deg2rad(time_phase)))
    applied = np.real(result.force_phasor * np.exp(1j * np.deg2rad(time_phase)))
    st.plotly_chart(
        engineering_viewport(
            model,
            state,
            scale,
            loads=nodal_loads(model, applied),
            monitors=tuple(sorted({r.node for r in case.responses})),
            title=f"Harmonic snapshot · {result.frequencies_hz[index]:.5g} Hz · θ={time_phase}°",
        ),
        width="stretch",
    )
    cycle_view(
        model,
        result.displacement[index],
        scale,
        label=f"{result.frequencies_hz[index]:.5g} Hz",
        key="harmonic",
        force=result.force_phasor,
    )
    amplitude_plot, phase_plot = response_figures(result)
    st.plotly_chart(amplitude_plot, width="stretch")
    st.plotly_chart(phase_plot, width="stretch")
    st.caption(
        "Diamonds: sampled interior maxima. Dotted lines: undamped natural frequencies. "
        "Phase is wrapped and omitted at zero/negligible response. "
        "Refine the sweep to resolve narrow peaks."
    )
    if result.peaks:
        st.dataframe(
            [
                {
                    "Response": peak.response.label,
                    "Sample frequency [Hz]": peak.frequency_hz,
                    "Peak amplitude [m or rad]": peak.amplitude,
                    "Phase [deg]": None
                    if peak.phase_radians is None
                    else np.rad2deg(peak.phase_radians),
                }
                for peak in result.peaks
            ],
            hide_index=True,
        )
    else:
        st.info("No interior resonance peaks resolved in this sweep.")

    if magnitude / geometry.length > 0.05:
        st.warning(
            "Complex displacement norm exceeds 5% of length; "
            "small-displacement theory may be unsuitable."
        )
    with st.expander("Natural frequencies and numerical diagnostics"):
        st.dataframe(
            {
                "Natural frequency [Hz]": result.natural_frequencies_hz,
                "Modal damping ratio ζ": result.modal_damping_ratios,
            },
            hide_index=True,
        )
        st.write(f"Minimum adjusted reciprocal condition: {result.reciprocal_condition.min():.3e}")
        st.write(f"Maximum backward error: {result.backward_errors.max():.3e}")
        st.caption(
            "Algebraic checks do not establish mesh accuracy or physical validity. "
            "No experimental validation or ANSYS correlation."
        )
    st.download_button(
        "Export harmonic engineering report (JSON)",
        harmonic_report(model, case, result),
        file_name="vibra-harmonic-report.json",
        mime="application/json",
    )
    st.caption("Linear slender beam · proportional viscous damping · steady state only · SI units")
