"""Transient beam workspace, separate from numerical integration and prior workflows."""

import csv
import io
from typing import Literal

import numpy as np
import streamlit as st
from pydantic import ValidationError

from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.errors import EngineeringError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import DOF, FrameModel, Material, NodalLoad, Rectangle
from vibra.dynamics.forcing import (
    HarmonicForce,
    PulseForce,
    SampledForce,
    StepForce,
    TransientForce,
)
from vibra.io.transient_report import transient_report
from vibra.solvers.static import solve_static
from vibra.solvers.transient import InitialValue, TimeGrid, TransientConfig, solve_transient
from vibra.visualization.transient import (
    energy_history,
    response_history,
)
from vibra.visualization.viewport import engineering_viewport, state_animation
from vibra.workbench.presentation import plot
from vibra.workbench.viewport import model_preview, nodal_loads


def _initial_profile(
    model: FrameModel, tip_x: float, tip_v: float
) -> tuple[tuple[InitialValue, ...], tuple[InitialValue, ...]]:
    if tip_x == 0 and tip_v == 0:
        return (), ()
    tip = max(node.id for node in model.nodes)
    unit_model = FrameModel(**(model.model_dump() | {"loads": (NodalLoad(node=tip, fy=1),)}))
    unit = solve_static(unit_model)
    profile = unit.displacement / unit.displacement[-1, 1]

    def values(amplitude: float) -> tuple[InitialValue, ...]:
        return tuple(
            InitialValue(node=node, dof=DOF(j), value=float(profile[i, j] * amplitude))
            for i, node in enumerate(unit.node_ids)
            for j in range(3)
        )

    return values(tip_x), values(tip_v)


def workspace() -> None:
    st.subheader("FEM Transient Response")
    st.caption("M ü + C u̇ + K u = F(t) · Newmark β_N = 1/4, γ_N = 1/2 · SI units")
    kind = st.sidebar.selectbox("Transient damping", ("rayleigh", "undamped", "mass", "stiffness"))
    excitation = st.sidebar.selectbox("Time excitation", ("pulse", "step", "harmonic", "sampled"))
    with st.sidebar.form("transient_inputs"):
        st.subheader("Beam model")
        length = st.number_input("Length [m]", min_value=0.1, max_value=20.0, value=1.0)
        width = st.number_input("Section width [m]", min_value=0.001, value=0.02, format="%.4f")
        height = st.number_input(
            "Section bending depth [m]", min_value=0.001, value=0.02, format="%.4f"
        )
        young = st.number_input("Young's modulus [GPa]", min_value=0.001, value=210.0)
        density = st.number_input("Density [kg/m³]", min_value=0.001, value=7850.0)
        count = st.slider("Beam elements", 2, 32, 12)
        st.caption("Fixed node 0 (ux = uy = rz = 0), free tip; node IDs run from root to tip.")
        st.subheader("Time grid")
        duration = st.number_input(
            "Duration [s]", min_value=0.001, max_value=20.0, value=0.5, format="%.6f"
        )
        step = st.number_input("Time step [s]", min_value=0.000001, value=0.001, format="%.6f")
        st.caption(
            "Duration must be an integer multiple of dt. "
            "Force onset/end times must align with the grid."
        )
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
        st.subheader("Nodal excitation")
        node = st.number_input("Excitation node", min_value=0, max_value=count, value=count)
        dof = st.selectbox("Excitation DOF", ("UY", "UX", "RZ"))
        amplitude = 0.0
        onset, end, frequency, phase = 0.0, 0.04, 15.0, 0.0
        shape, sampled_text = "half_sine", ""
        if excitation != "sampled":
            amplitude = st.number_input("Signed force [N] / moment [N m]", value=1.0)
            onset = st.number_input("Force onset [s]", min_value=0.0, value=0.0, format="%.6f")
        if excitation == "pulse":
            end = st.number_input("Pulse end [s]", min_value=0.000001, value=0.04, format="%.6f")
            shape = st.selectbox("Pulse shape", ("half_sine", "rectangular"))
        if excitation == "harmonic":
            frequency = st.number_input("Excitation frequency [Hz]", min_value=0.0, value=15.0)
            phase = st.number_input("Load cosine phase [deg]", value=0.0)
        if excitation == "sampled":
            sampled_text = st.text_area(
                "Sampled force: time [s], force [N or N m]",
                value=f"0,0\n0.02,1\n0.04,0\n{duration:g},0",
            )
            st.caption(
                "Two columns, no header; start at 0, strictly increasing times, cover duration. "
                "Linear interpolation, no extrapolation."
            )
        st.subheader("Initial state")
        tip_x = st.number_input("Initial transverse tip displacement [m]", value=0.0, format="%.6f")
        tip_v = st.number_input("Initial transverse tip velocity [m/s]", value=0.0, format="%.6f")
        st.caption(
            "Nonzero tip values initialize the whole beam with the static cantilever profile, "
            "including rotations."
        )
        nodes = st.multiselect("Response nodes", range(count + 1), default=[count])
        dofs = st.multiselect("Response DOFs", ("UY", "UX", "RZ"), default=["UY"])
        run = st.form_submit_button("Run transient analysis", type="primary", width="stretch")
    if run:
        try:
            geometry, rectangle = BeamGeometry(length=length), Rectangle(width=width, height=height)
            material = Material(young_modulus=young * 1e9, density=density)
            model = cantilever(geometry, material, rectangle.section(), count, tip_force=0)
            common = {"node": node, "dof": DOF[dof], "amplitude": amplitude, "start_time": onset}
            load: TransientForce
            if excitation == "step":
                load = StepForce.model_validate(common)
            elif excitation == "harmonic":
                load = HarmonicForce.model_validate(
                    common | {"frequency_hz": frequency, "phase_degrees": phase}
                )
            elif excitation == "pulse":
                load = PulseForce.model_validate(common | {"end_time": end, "shape": shape})
            else:
                pairs = list(csv.reader(io.StringIO(sampled_text)))
                pairs = [row for row in pairs if row]
                if any(len(row) != 2 for row in pairs):
                    raise ValueError("Sampled history requires exactly two columns: time, force.")
                load = SampledForce(
                    node=node,
                    dof=DOF[dof],
                    times=tuple(float(row[0]) for row in pairs),
                    values=tuple(float(row[1]) for row in pairs),
                )
            initial_u, initial_v = _initial_profile(model, tip_x, tip_v)
            config = TransientConfig(
                grid=TimeGrid(duration=duration, time_step=step),
                damping=Damping.model_validate({"kind": kind, "alpha": alpha, "beta": beta}),
                loads=(load,),
                responses=tuple(ResponseDOF(node=n, dof=DOF[d]) for n in nodes for d in dofs),
                initial_displacement=initial_u,
                initial_velocity=initial_v,
            )
            with st.spinner("Integrating the FEM dynamics…"):
                result = solve_transient(model, config)
            st.session_state["transient_solved"] = {
                "model": model,
                "config": config,
                "result": result,
                "geometry": geometry,
                "rectangle": rectangle,
            }
        except (EngineeringError, ValidationError, ValueError, csv.Error) as exc:
            st.session_state.pop("transient_solved", None)
            st.error(str(exc))
    saved = st.session_state.get("transient_solved")
    if saved is None:
        preview = cantilever(
            BeamGeometry(length=length),
            Material(young_modulus=young * 1e9, density=density),
            Rectangle(width=width, height=height).section(),
            count,
            tip_force=0,
        )
        model_preview(preview, loads=(), monitors=tuple(nodes), key="transient")
        st.info("Configure the model, time grid, forcing, initial state and responses, then run.")
        return
    result, config, model = saved["result"], saved["config"], saved["model"]
    st.caption(
        f"Last submitted model: {len(model.elements)} elements · fixed root · "
        f"{len(result.time) - 1} steps · dt = {config.grid.time_step:g} s · "
        f"{config.damping.kind} damping. Submit again after edits."
    )
    if saved["geometry"].length / saved["rectangle"].height < 10:
        st.warning(
            "L/h < 10: shear deformation may be significant; Euler–Bernoulli theory omits it."
        )
    for warning in result.numerical_warnings:
        st.warning(warning)
    st.subheader("Physical beam deformation")
    index = st.slider("Time sample", 0, len(result.time) - 1, 0)
    column = st.selectbox(
        "Inspect response",
        range(len(result.response_dofs)),
        format_func=lambda i: result.response_dofs[i].label,
    )
    peak_translation = float(
        np.max(
            np.linalg.norm(result.displacement.reshape(len(result.time), -1, 3)[:, :, :2], axis=2)
        )
    )
    default_scale = (
        min(1000.0, 0.15 * saved["geometry"].length / peak_translation) if peak_translation else 1.0
    )
    scale = st.number_input(
        "Displacement visualization scale [×]", min_value=0.0, value=default_scale
    )
    a, b, c = st.columns(3)
    a.metric("Time [s]", f"{result.time[index]:.6g}")
    unit: Literal["rad", "m"] = "rad" if result.response_dofs[column].dof == DOF.RZ else "m"
    b.metric(f"Physical response [{unit}]", f"{result.response_displacement[index, column]:.6g}")
    c.metric("Relative energy balance error", f"{result.relative_energy_error:.3e}")
    plot(
        engineering_viewport(
            model,
            result.displacement[index],
            scale,
            loads=nodal_loads(model, result.force_right[index]),
            monitors=tuple(sorted({r.node for r in config.responses})),
            title=f"Transient snapshot · t={result.time[index]:.6g} s",
        ),
        width="stretch",
    )
    history = response_history(result)
    history.add_vline(x=float(result.time[index]), line_dash="dash", line_color="#ba4b37")
    plot(history, width="stretch")
    plot(energy_history(result), width="stretch")
    if peak_translation / saved["geometry"].length > 0.05:
        st.warning(
            "Displacement exceeds 5% of beam length; small-displacement theory may be unsuitable."
        )
    if st.checkbox("Animate deformation (up to 60 actual frames)"):
        st.caption(
            "Illustrative playback speed; frame titles show actual timestamps and magnification."
        )
        indices = np.unique(
            np.linspace(0, len(result.time) - 1, min(40, len(result.time)), dtype=int)
        )
        plot(
            state_animation(
                model,
                result.displacement[indices],
                tuple(f"t={result.time[i]:.6g} s" for i in indices),
                scale,
                times=result.time[indices],
                response=result.response_displacement[indices, column],
                response_unit=unit,
                force_states=result.force_right[indices],
            ),
            width="stretch",
        )
    with st.expander("Energy, support reactions and solver diagnostics"):
        st.write(f"Maximum full-grid backward error: {result.backward_errors.max():.3e}")
        st.write(
            f"Mass/effective reciprocal conditions: {result.mass_reciprocal_condition:.3e} / "
            f"{result.effective_reciprocal_condition:.3e}"
        )
        st.dataframe(
            {
                "Support node": [result.node_ids[dof // 3] for dof in result.constrained_indices],
                "DOF": [DOF(dof % 3).name for dof in result.constrained_indices],
                "Reaction": result.reactions[index],
                "Unit": ["N m" if dof % 3 == 2 else "N" for dof in result.constrained_indices],
            },
            hide_index=True,
        )
        st.caption("Right-hand reactions include consistent-mass and damping coupling.")
        st.caption(
            "D/W use interval-consistent quadratures; E − E₀ + D − W is a discrete balance. "
            "Small residual does not establish time-step or mesh accuracy."
        )
    try:
        st.download_button(
            "Export transient engineering report (JSON)",
            transient_report(model, config, result),
            file_name="vibra-transient-report.json",
            mime="application/json",
        )
    except ValueError as exc:
        st.error(str(exc))
    st.caption("Linear small-displacement beam · no experimental validation or ANSYS correlation")
