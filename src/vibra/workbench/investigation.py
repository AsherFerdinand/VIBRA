"""Depth-only engineering challenge. Solver work occurs only on explicit submission."""

import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.io.reports import engineering_report
from vibra.studies.beginner import ShelfInputs, shelf_model
from vibra.studies.investigation import (
    ChallengeInputs,
    calculate_design,
    challenge_explanation,
    compare_designs,
    comparison_rows,
    feasible_depth_interval_mm,
)
from vibra.visualization.investigation import comparison_viewport
from vibra.visualization.viewport import Contour
from vibra.workbench.interpretation import Interpretation, render_interpretation
from vibra.workbench.presentation import comparison_table, plot
from vibra.workbench.viewport import model_preview


def _start() -> None:
    st.session_state["challenge_depth"] = 20.0


def workspace() -> None:
    st.subheader("Design a Stronger Support")
    st.write(
        "This wall-mounted support bends too much. Reduce its maximum downward "
        "movement by at least **40%**, adding no more than **20% beam mass**. "
        "Change depth only; keep the 1 m length, 20 mm width, steel-like material "
        "and 100 N downward tip force."
    )
    with st.sidebar.form("challenge_inputs", border=False):
        st.subheader("Design B · beam depth")
        depth = st.number_input(
            "Challenge depth [mm]",
            min_value=20.0,
            max_value=28.0,
            step=0.1,
            value=20.0,
            format="%.3f",
            key="challenge_depth",
            help="Only depth changes. Inputs are pending until you evaluate the design.",
        )
        start = st.form_submit_button("Start design challenge", on_click=_start)
        run = st.form_submit_button("Evaluate design", type="primary")
        st.caption(
            "A remains the saved 20 mm baseline. The challenge does not change material or load."
        )
    if start or run:
        try:
            # Retain the calculated A; no global cache or shared mutable result arrays.
            baseline = st.session_state.get("challenge_baseline")
            if baseline is None:
                baseline = calculate_design()
                st.session_state["challenge_baseline"] = baseline
            candidate = (
                baseline if depth == 20 else calculate_design(ChallengeInputs(depth_mm=depth))
            )
            st.session_state["challenge_comparison"] = compare_designs(baseline, candidate)
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("challenge_comparison", None)
            st.error(str(exc))
    comparison = st.session_state.get("challenge_comparison")
    if comparison is None:
        model_preview(shelf_model(ShelfInputs()), monitors=(12,), key="challenge_baseline")
        st.info(
            "Start the challenge to calculate and inspect design A, "
            "then change depth and evaluate B."
        )
        return
    st.caption(
        f"Submitted B: {comparison.candidate.shelf.inputs.thickness_mm:g} mm depth. "
        "Changing a control does not alter the submitted design until Evaluate design."
    )
    controls = st.columns((1.5, 1, 1))
    kind = controls[0].radio(
        "Compare field",
        ("Movement", "Stress", "Bending moment"),
        horizontal=True,
    )
    field: Contour = (
        "Displacement magnitude"
        if kind == "Movement"
        else "Bending moment"
        if kind == "Bending moment"
        else "Combined normal stress"
    )
    overlay = controls[1].checkbox("Show undeformed designs", value=True)
    scale = controls[2].number_input(
        "Comparison magnification [×]",
        min_value=0.0,
        max_value=1000.0,
        value=12.6,
    )
    plot(
        comparison_viewport(comparison, scale, field, overlay),
        width="stretch",
        key="challenge_viewport",
    )
    st.caption(
        "Common physical axes, color limits and drawing scale for A and B. Hover reports "
        "unmagnified displacement, both section fibers, N, V and M. Circle: sampled "
        "translation maximum; cross: recovered critical stress section. Top is local +y."
    )
    a, b, c, d = st.columns(4)
    a.metric("A downward movement [mm]", f"{comparison.baseline.max_downward_m * 1e3:.5g}")
    b.metric("B downward movement [mm]", f"{comparison.candidate.max_downward_m * 1e3:.5g}")
    c.metric("Movement reduction [%]", f"{comparison.displacement_reduction_percent:.3f}")
    d.metric("Mass increase [%]", f"{comparison.mass_increase_percent:.3f}")
    status = st.success if comparison.passed else st.info
    status(
        f"Movement ≥40% reduction: {'PASS' if comparison.displacement_pass else 'NOT MET'} · "
        f"Mass ≤20% increase: {'PASS' if comparison.mass_pass else 'NOT MET'} · "
        "These are movement/mass requirements, not a structural safety assessment."
    )
    comparison_table(comparison_rows(comparison))
    render_interpretation(Interpretation(*challenge_explanation(comparison)))
    with st.expander("Engineering basis, feasibility & export"):
        low, high = feasible_depth_interval_mm()
        st.write(
            f"For the ideal rectangular tip-loaded beam, displacement ∝ h⁻³ and mass ∝ h. "
            f"The analytical feasible interval is {low:.6f}–{high:.6f} mm. The table and "
            "requirement status use actual FEM solves. A 1e-7 percentage-point tolerance "
            "covers roundoff at inclusive boundaries. No material strength criterion is evaluated."
        )
        st.download_button(
            "Export design investigation (JSON)",
            engineering_report(
                "Depth-only support challenge",
                dict(
                    baseline=comparison.baseline.shelf.inputs,
                    candidate=comparison.candidate.shelf.inputs,
                    targets=dict(minimum_reduction_percent=40, maximum_mass_increase_percent=20),
                ),
                dict(
                    comparison=comparison,
                    table=comparison_rows(comparison),
                    assumptions=(
                        "Linear planar beam, fixed root; no safety or experimental validation"
                    ),
                ),
            ),
            file_name="vibra-design-investigation.json",
            mime="application/json",
        )
