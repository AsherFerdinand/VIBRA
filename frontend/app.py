"""Launch: streamlit run frontend/app.py (after installing the package)."""

import logging
from typing import Any

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import AnalysisConfig, Material, Rectangle
from vibra.dynamics.sdof import SDOFConfig, solve_sdof
from vibra.io.reports import engineering_report
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.analytical import cantilever_bending_hz, cantilever_tip
from vibra.verification.benchmarks import convergence_study
from vibra.visualization.plots import (
    beam_shape,
    bending_moment,
    convergence_plot,
    sdof_response,
)
from vibra.workbench.harmonic import workspace as harmonic_workspace

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title="VIBRA | Engineering Workbench", page_icon="◫", layout="wide")
st.title("VIBRA")
st.caption("STRUCTURAL DYNAMICS & FEM WORKBENCH · 0.2 · SI UNITS")
analysis = st.sidebar.selectbox(
    "Analysis", ["Static cantilever", "Cantilever modes", "SDOF vibration", "Harmonic response"]
)
st.sidebar.caption("Model → Mesh & supports → Solve → Inspect → Export")

if analysis == "Harmonic response":
    harmonic_workspace()
    st.stop()

with st.sidebar.form("model_inputs"):
    if analysis != "SDOF vibration":
        st.subheader("Geometry & material")
        length = st.number_input("Length [m]", min_value=0.1, max_value=20.0, value=1.0)
        width = st.number_input("Section width [m]", min_value=0.001, value=0.02, format="%.4f")
        height = st.number_input(
            "Section bending depth [m]", min_value=0.001, value=0.02, format="%.4f"
        )
        young_gpa = st.number_input("Young's modulus [GPa]", min_value=0.001, value=210.0)
        density = st.number_input("Density [kg/m³]", min_value=0.001, value=7850.0)
        count = st.slider("Beam elements", min_value=2, max_value=64, value=12)
        st.subheader("Boundary conditions")
        st.write("Fixed root: ux = uy = rz = 0; free tip.")
        tip_force = st.number_input("Tip transverse force [N]", value=-100.0)
        modes_count = st.slider("Modes requested", 1, min(12, 3 * count), 6)
        st.caption("Modal analysis ignores the load and computes undamped, unprestressed modes.")
    else:
        st.subheader("Mass · spring · damper")
        mass = st.number_input("Mass [kg]", min_value=0.1, max_value=1000.0, value=2.0)
        stiffness = st.number_input(
            "Stiffness [N/m]", min_value=1.0, max_value=100000.0, value=200.0
        )
        damping = st.number_input("Damping [N s/m]", min_value=0.0, max_value=1000.0, value=0.8)
        x0 = st.number_input("Initial displacement [m]", value=0.01, format="%.4f")
        v0 = st.number_input("Initial velocity [m/s]", value=0.0)
        amplitude = st.number_input("Sinusoidal force amplitude [N]", value=0.0)
        excitation = st.number_input(
            "Excitation frequency [Hz]", min_value=0.0, max_value=100.0, value=1.0
        )
        duration = st.number_input("Duration [s]", min_value=0.1, max_value=30.0, value=5.0)
        st.caption("F(t) = F₀ sin(2πft). Free vibration when F₀ = 0.")
    run = st.form_submit_button("Run analysis", type="primary", width="stretch")

if run:
    try:
        with st.spinner("Solving engineering model…"):
            if analysis == "SDOF vibration":
                config = SDOFConfig(
                    mass=mass,
                    stiffness=stiffness,
                    damping=damping,
                    initial_displacement=x0,
                    initial_velocity=v0,
                    force_amplitude=amplitude,
                    excitation_hz=excitation,
                    duration=duration,
                )
                saved: dict[str, Any] = {
                    "analysis": analysis,
                    "inputs": config,
                    "result": solve_sdof(config),
                }
            else:
                geometry = BeamGeometry(length=length)
                material = Material(young_modulus=young_gpa * 1e9, density=density)
                rectangle = Rectangle(width=width, height=height)
                model = cantilever(geometry, material, rectangle.section(), count, tip_force)
                options = AnalysisConfig(modes=modes_count)
                result = (
                    solve_static(model)
                    if analysis == "Static cantilever"
                    else solve_modal(model, options)
                )
                saved = {
                    "analysis": analysis,
                    "inputs": {"model": model, "config": options},
                    "result": result,
                    "geometry": geometry,
                    "material": material,
                    "rectangle": rectangle,
                    "model": model,
                }
                if analysis == "Cantilever modes":
                    saved["convergence"] = convergence_study(geometry, material, rectangle)
            st.session_state["solved"] = saved
    except (EngineeringError, ValidationError, ValueError) as exc:
        st.session_state.pop("solved", None)
        st.error(str(exc))

saved_result = st.session_state.get("solved")
if saved_result is None or saved_result["analysis"] != analysis:
    st.info("Define the model in the parameter panel, then run the analysis.")
    st.markdown(
        "**Available workflows**\n\n"
        "- Static beam: nodal displacement, support equilibrium and internal end forces.\n"
        "- Cantilever modes: consistent-mass eigenproblem and analytical mesh convergence.\n"
        "- SDOF: free or harmonic response with displacement, velocity and acceleration."
    )
else:
    result = saved_result["result"]
    st.subheader(analysis)
    st.caption(
        "Results use the last submitted inputs. Submit again after editing the parameter panel."
    )
    if analysis == "SDOF vibration":
        config = saved_result["inputs"]
        a, b, c = st.columns(3)
        a.metric("Natural frequency [Hz]", f"{config.angular_frequency / (2 * np.pi):.5g}")
        b.metric("Damping ratio ζ", f"{config.damping_ratio:.5g}")
        wd = config.damped_angular_frequency
        c.metric(
            "Damped frequency [Hz]", "Nonoscillatory" if wd is None else f"{wd / (2 * np.pi):.5g}"
        )
        st.caption("Solver: SciPy DOP853 · mẍ + cẋ + kx = F(t) · independent lumped model")
        st.plotly_chart(sdof_response(result), width="stretch")
    else:
        model = saved_result["model"]
        geometry, material, rectangle = (
            saved_result["geometry"],
            saved_result["material"],
            saved_result["rectangle"],
        )
        section = rectangle.section()
        st.caption(
            f"{geometry.length:g} m beam · {rectangle.width:g} × {rectangle.height:g} m section · "
            f"E = {material.young_modulus / 1e9:g} GPa · ρ = {material.density:g} kg/m³ · "
            f"{len(model.elements)} elements · fixed root · Euler–Bernoulli 2D frame"
        )
        if geometry.length / rectangle.height < 10:
            st.warning(
                "L/h < 10: shear deformation may be significant; use a shear-flexible model."
            )
        if analysis == "Static cantilever":
            force = model.loads[0].fy
            exact_displacement, exact_rotation = cantilever_tip(geometry, material, section, force)
            a, b, c = st.columns(3)
            a.metric("Tip displacement [m]", f"{result.displacement[-1, 1]:.6g}")
            b.metric("Tip rotation [rad]", f"{result.displacement[-1, 2]:.6g}")
            c.metric("Root moment [N m]", f"{result.reactions[0, 2]:.6g}")
            st.caption("Solver: equilibrated symmetric positive-definite solve of Kff uf = Ff")
            if np.max(np.abs(result.displacement[:, :2])) / geometry.length > 0.05:
                st.warning(
                    "Displacement exceeds 5% of length; "
                    "small-displacement theory may be unsuitable."
                )
            magnitude = float(np.max(np.abs(result.displacement[:, :2])))
            suggested_scale = min(1000.0, 0.15 * geometry.length / magnitude) if magnitude else 1.0
            scale = st.number_input(
                "Displacement visualization scale [×]", min_value=0.0, value=suggested_scale
            )
            st.plotly_chart(beam_shape(model, result.displacement, scale), width="stretch")
            st.plotly_chart(bending_moment(model, result), width="stretch")
            st.dataframe(
                {
                    "Quantity": ["Tip displacement [m]", "Tip rotation [rad]"],
                    "FEM": [float(result.displacement[-1, 1]), float(result.displacement[-1, 2])],
                    "Analytical": [exact_displacement, exact_rotation],
                },
                hide_index=True,
            )
            st.dataframe(
                {
                    "Node": result.node_ids,
                    "ux [m]": result.displacement[:, 0],
                    "uy [m]": result.displacement[:, 1],
                    "rz [rad]": result.displacement[:, 2],
                    "Reaction Fx [N]": result.reactions[:, 0],
                    "Reaction Fy [N]": result.reactions[:, 1],
                    "Reaction Mz [N m]": result.reactions[:, 2],
                },
                hide_index=True,
            )
            with st.expander("Local element end forces"):
                st.dataframe(
                    [
                        {
                            "Element": eid,
                            **dict(
                                zip(
                                    [
                                        "N1 [N]",
                                        "V1 [N]",
                                        "M1 [N m]",
                                        "N2 [N]",
                                        "V2 [N]",
                                        "M2 [N m]",
                                    ],
                                    values.tolist(),
                                    strict=True,
                                )
                            ),
                        }
                        for eid, values in result.element_end_forces.items()
                    ],
                    hide_index=True,
                )
        else:
            st.caption("Solver: SciPy symmetric generalized eigensolve · Kφ = ω²Mφ · φᵀMφ = 1")
            st.dataframe(
                {
                    "Mode": list(range(1, len(result.frequencies_hz) + 1)),
                    "Frequency [Hz]": result.frequencies_hz,
                    "Angular frequency [rad/s]": result.angular_frequencies,
                    "Family": result.families,
                    "Axial energy fraction": result.axial_energy_fraction,
                },
                hide_index=True,
            )
            selected = st.selectbox(
                "Display mode",
                range(len(result.frequencies_hz)),
                format_func=lambda i: f"Mode {i + 1}",
            )
            shape = result.modes[:, selected].reshape(-1, 3).copy()
            max_translation = float(np.max(np.linalg.norm(shape[:, :2], axis=1)))
            amplitude_fraction = st.slider("Mode display amplitude / beam length", 0.01, 0.3, 0.1)
            factor = amplitude_fraction * geometry.length / max_translation
            st.caption(
                f"Arbitrary eigenvector amplitude; plotted coordinates use φ × {factor:.5g}. "
                "This is a visualization scale, not a physical vibration displacement."
            )
            st.plotly_chart(beam_shape(model, shape, factor, modal=True), width="stretch")
            st.plotly_chart(convergence_plot(saved_result["convergence"]), width="stretch")
            st.write(
                "Analytical first three bending frequencies [Hz]:",
                cantilever_bending_hz(geometry, material, section),
            )
    with st.expander("Submitted model and analysis settings"):
        st.json(
            engineering_report(analysis, saved_result["inputs"], {"note": "See report for results"})
        )
    report_data: Any = result
    if analysis == "Cantilever modes":
        report_data = {"modal": result, "convergence": saved_result["convergence"]}
    st.download_button(
        "Export engineering report (JSON)",
        engineering_report(analysis, saved_result["inputs"], report_data),
        file_name="vibra-report.json",
        mime="application/json",
    )
st.divider()
st.caption(
    "Educational engineering software · linear, slender beams · "
    "no shear deformation, rotary inertia, "
    "geometric nonlinearity or experimental validation · "
    "independently developed; not affiliated with ANSYS"
)
