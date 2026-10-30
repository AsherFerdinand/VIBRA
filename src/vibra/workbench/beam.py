"""Launch: streamlit run frontend/app.py (after installing the package)."""

from typing import Any

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import AnalysisConfig, FrameModel, Material, NodalLoad, Rectangle
from vibra.dynamics.sdof import SDOFConfig, solve_sdof
from vibra.io.reports import engineering_report
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.analytical import cantilever_bending_hz, cantilever_tip
from vibra.verification.benchmarks import convergence_study
from vibra.visualization.plots import (
    convergence_plot,
    sdof_response,
)
from vibra.visualization.viewport import engineering_viewport
from vibra.workbench.presentation import plot
from vibra.workbench.viewport import cycle_view, model_preview, static_view


def workspace(analysis: str) -> None:
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
            st.subheader("Loads" if analysis == "Static cantilever" else "Natural modes")
            tip_axial = (
                st.number_input("Tip axial force [N]", value=0.0)
                if analysis == "Static cantilever"
                else 0.0
            )
            tip_force = (
                st.number_input("Tip transverse force [N]", value=-100.0)
                if analysis == "Static cantilever"
                else 0.0
            )
            modes_count = (
                st.slider("Modes requested", 1, min(12, 3 * count), 6)
                if analysis == "Cantilever modes"
                else 6
            )
            if analysis == "Cantilever modes":
                st.caption(
                    "Loads and prestress are excluded; modal display amplitude is arbitrary."
                )
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
                    model = FrameModel(
                        **(
                            model.model_dump()
                            | {"loads": (NodalLoad(node=count, fx=tip_axial, fy=tip_force),)}
                        )
                    )
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
        if analysis != "SDOF vibration":
            preview = cantilever(
                BeamGeometry(length=length),
                Material(young_modulus=young_gpa * 1e9, density=density),
                Rectangle(width=width, height=height).section(),
                count,
                tip_force,
            )
            preview = FrameModel(
                **(
                    preview.model_dump()
                    | {"loads": (NodalLoad(node=count, fx=tip_axial, fy=tip_force),)}
                )
            )
            model_preview(
                preview,
                loads=() if analysis == "Cantilever modes" else None,
                monitors=(count,),
                key="beam",
            )
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
                "Damped frequency [Hz]",
                "Nonoscillatory" if wd is None else f"{wd / (2 * np.pi):.5g}",
            )
            st.caption("Solver: SciPy DOP853 · mẍ + cẋ + kx = F(t) · independent lumped model")
            plot(sdof_response(result), width="stretch")
        else:
            model = saved_result["model"]
            geometry, material, rectangle = (
                saved_result["geometry"],
                saved_result["material"],
                saved_result["rectangle"],
            )
            section = rectangle.section()
            st.caption(
                f"{geometry.length:g} m beam · "
                f"{rectangle.width:g} × {rectangle.height:g} m section · "
                f"E = {material.young_modulus / 1e9:g} GPa · ρ = {material.density:g} kg/m³ · "
                f"{len(model.elements)} elements · fixed root · Euler–Bernoulli 2D frame"
            )
            if geometry.length / rectangle.height < 10:
                st.warning(
                    "L/h < 10: shear deformation may be significant; use a shear-flexible model."
                )
            if analysis == "Static cantilever":
                force = model.loads[0].fy
                exact_displacement, exact_rotation = cantilever_tip(
                    geometry, material, section, force
                )
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
                suggested_scale = (
                    min(1000.0, 0.15 * geometry.length / magnitude) if magnitude else 1.0
                )
                scale = st.number_input(
                    "Displacement visualization scale [×]", min_value=0.0, value=suggested_scale
                )
                static_view(
                    model, result, scale, key="beam_static", monitors=(len(model.nodes) - 1,)
                )
                st.dataframe(
                    {
                        "Quantity": ["Tip displacement [m]", "Tip rotation [rad]"],
                        "FEM": [
                            float(result.displacement[-1, 1]),
                            float(result.displacement[-1, 2]),
                        ],
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
                amplitude_fraction = st.slider(
                    "Mode display amplitude / beam length", 0.01, 0.3, 0.1
                )
                factor = amplitude_fraction * geometry.length / max_translation
                st.caption(
                    f"Arbitrary eigenvector amplitude; plotted coordinates use φ × {factor:.5g}. "
                    "This is a visualization scale, not a physical vibration displacement."
                )
                plot(
                    engineering_viewport(
                        model,
                        shape,
                        factor,
                        loads=(),
                        modal=True,
                        title=(
                            f"Mode {selected + 1} · {result.frequencies_hz[selected]:.5g} Hz · "
                            f"{result.families[selected]}"
                        ),
                    ),
                    width="stretch",
                )
                cycle_view(
                    model,
                    result.modes[:, selected],
                    factor,
                    label=(
                        f"Mode {selected + 1} · {result.frequencies_hz[selected]:.5g} Hz · "
                        f"{result.families[selected]}"
                    ),
                    key="beam_mode",
                    modal=True,
                )
                plot(convergence_plot(saved_result["convergence"]), width="stretch")
                st.write(
                    "Analytical first three bending frequencies [Hz]:",
                    cantilever_bending_hz(geometry, material, section),
                )
        with st.expander("Submitted model and analysis settings"):
            st.json(
                engineering_report(
                    analysis, saved_result["inputs"], {"note": "See report for results"}
                )
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
        "no shear deformation or section rotary inertia, "
        "geometric nonlinearity or experimental validation · "
        "independently developed; not affiliated with ANSYS"
    )
