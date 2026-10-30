"""Deterministic interpretation of actual solved quantities, without fault diagnosis."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import streamlit as st

from vibra.core.models import DOF, FrameModel
from vibra.postprocessing.beam import recover_stress
from vibra.signals.analysis import SpectrumResult
from vibra.signals.models import SignalSeries
from vibra.solvers.static import StaticResult
from vibra.studies.installed import InstalledStudy


@dataclass(frozen=True)
class Interpretation:
    happened: str
    why: str
    try_next: str


def beam_interpretation(model: FrameModel, result: StaticResult) -> Interpretation:
    tip = float(result.displacement[-1, 1]) * 1000
    translation = float(np.linalg.norm(result.displacement[-1, :2])) * 1000
    stress = recover_stress(model, result.displacement)
    moment = max(float(np.max(abs(f[[2, 5]]))) for f in result.element_end_forces.values())
    if np.max(abs(result.displacement)) == 0:
        return Interpretation(
            "The solved support has zero displacement and zero stress.",
            "This model has no effective applied load.",
            "Apply a downward load, then compare the tip movement and root stress.",
        )
    critical = stress.critical_absolute
    at_fixed = any(
        abs(node.x - critical.global_x_m) < 1e-10
        and abs(node.y - critical.global_y_m) < 1e-10
        and any(c.node == node.id for c in model.constraints)
        for node in model.nodes
    )
    location = " A critical section is at the fixed support." if at_fixed else ""
    why = (
        f"The solved peak bending moment is {moment:.4g} N m. Normal stress combines "
        "axial force per area with bending. A tip force has a larger lever arm toward "
        "the fixed end; movement and stress can therefore be critical at different places."
    )
    if moment < 1e-9:
        why = (
            f"The solved peak bending moment is {moment:.4g} N m, effectively zero here. "
            "The normal stress is carried by axial tension/compression per section area, "
            "rather than bending from a transverse load."
        )
    return Interpretation(
        f"The free-end translation magnitude is {translation:.4g} mm "
        f"(Y={tip:.4g} mm; negative Y is downward). The largest "
        f"section normal stress magnitude is "
        f"{abs(stress.critical_absolute.normal_stress_Pa) / 1e6:.4g} MPa.{location}",
        why,
        "For this straight tip-loaded support, try a thicker beam or a larger load "
        "with other inputs fixed. Compare movement and stress; these results do not "
        "establish strength or fatigue safety.",
    )


def motor_interpretation(study: InstalledStudy) -> Interpretation:
    rigid, isolated = study.cases[1:]
    a = 100 * rigid.summary["operating_root_force_ratio"]
    b = 100 * isolated.summary["operating_root_force_ratio"]
    comparison = "lower" if b < a else "higher" if b > a else "equal"
    movement = isolated.summary["static_interface_displacement_m"] * 1000
    return Interpretation(
        f"At {study.config.operating_hz:g} Hz, the isolated assembly root-force "
        f"amplitude is {b:.4g}% of the applied force, versus {a:.4g}% with a rigid "
        f"motor attachment: {comparison} at this frequency. The prescribed static load "
        f"moves the motor interface {movement:.4g} mm.",
        f"Motor inertia and spring motion change the force path. The isolated "
        f"assembly’s lowest natural frequency is "
        f"{isolated.summary['first_natural_hz']:.4g} Hz. A different excitation "
        f"frequency can change which attachment transmits less force.",
        "Try softer mounts or another excitation frequency. Lower stiffness adds "
        "static movement and can improve isolation in some bands, while amplification "
        "can grow near resonances. Check both movement and transmitted force.",
    )


def signal_interpretation(series: SignalSeries, result: SpectrumResult) -> Interpretation:
    dominant = result.dominant_frequency_hz
    frequency = (
        "No nonzero dominant bin was resolved."
        if dominant is None
        else f"The strongest resolved nonzero frequency bin is {dominant:.5g} Hz."
    )
    return Interpretation(
        f"{frequency} Overall RMS vibration is {result.raw_metrics.rms:.5g} "
        f"{series.unit}. Source: {series.provenance.label}.",
        f"The spectrum groups repeating motion by frequency. This "
        f"{result.sampling.dft_duration_s:.4g} s record has "
        f"{result.sampling.frequency_resolution_hz:.4g} Hz bin spacing; the "
        f"{result.config.window} window affects peak width and leakage. A frequency "
        f"peak alone does not identify a mechanical fault.",
        "Try two closer frequencies in the simulated example, or compare a longer "
        "measured record in Advanced mode. Finite record length and windowing can "
        "make nearby components hard to distinguish.",
    )


def render_interpretation(value: Interpretation) -> None:
    st.subheader("What did we learn?")
    with st.container(border=True):
        st.markdown("**What happened?** " + value.happened)
        st.markdown("**Why?** " + value.why)
        st.markdown("**Try next** " + value.try_next)


def advanced_interpretation(experience: str, analysis: str) -> Interpretation | None:
    """Describe only the active submitted analysis; never reinterpret a stale other page."""
    saved: Any
    if experience == "Automotive Motor Mount":
        if st.session_state.get("motor_investigation") == "Bare rail A/B (0.5 reference)":
            from vibra.io.nvh_report import design_conclusion

            study = st.session_state.get("nvh_study")
            if study is not None:
                return Interpretation(
                    design_conclusion(study),
                    "Section stiffness and distributed mass both change natural "
                    "frequencies and force-driven response.",
                    "Change one input at a time; compare the operating-frequency "
                    "response, not static stiffness alone.",
                )
        installed = st.session_state.get("installed_study")
        return None if installed is None else motor_interpretation(installed)
    if analysis == "Signal Diagnostics":
        if not st.session_state.get("signal_result_visible", False):
            return None
        saved = st.session_state.get("signal_solved")
        return None if saved is None else signal_interpretation(saved["series"], saved["result"])
    if analysis == "Harmonic response":
        saved = st.session_state.get("harmonic_solved")
        if saved is None:
            return None
        h = saved["result"]
        column = 0
        index = int(np.argmax(h.response_amplitude[:, column]))
        dof = h.response_dofs[column]
        unit = "rad" if dof.dof == DOF.RZ else "m"
        return Interpretation(
            f"{dof.label} has a largest sampled peak amplitude "
            f"{h.response_amplitude[index, column]:.5g} {unit} at "
            f"{h.frequencies_hz[index]:.5g} Hz.",
            "Mass, stiffness and damping determine the complex response; sampled "
            "maxima are not exact resonance poles.",
            "Refine frequency spacing around an interior peak and compare response "
            "locations. A boundary maximum may not be a resonance.",
        )
    if analysis == "Transient response":
        saved = st.session_state.get("transient_solved")
        if saved is None:
            return None
        t = saved["result"]
        column = 0
        index = int(np.argmax(abs(t.response_displacement[:, column])))
        unit = "rad" if t.response_dofs[column].dof == DOF.RZ else "m"
        return Interpretation(
            f"{t.response_dofs[column].label} reaches a sampled |response| of "
            f"{abs(t.response_displacement[index, column]):.5g} {unit} at "
            f"{t.time[index]:.5g} s.",
            "The applied history and initial state set the motion; viscous damping "
            "removes energy when motion exists. Continued forcing need not produce "
            "decay.",
            "Halve the time step and compare histories. Change one excitation or "
            "damping parameter at a time.",
        )
    saved = st.session_state.get("solved")
    if saved is None or saved["analysis"] != analysis:
        return None
    result = saved["result"]
    if analysis == "Static cantilever":
        return beam_interpretation(saved["model"], result)
    if analysis == "Cantilever modes":
        return Interpretation(
            f"The lowest computed natural rate is {result.frequencies_hz[0]:.5g} Hz "
            f"({result.families[0]}).",
            "These undamped shapes describe how the structure can vibrate. Display "
            "amplitude is arbitrary, not operating movement.",
            "Change thickness while holding material and length fixed; inspect how "
            "mass and stiffness together shift the frequencies.",
        )
    if analysis == "SDOF vibration":
        return Interpretation(
            f"The one-mass reference reaches |displacement| "
            f"{np.max(abs(result.displacement)):.5g} m.",
            "The assumed mass, spring, damping and force determine this reference "
            "motion; it is not a FEM vehicle or appliance model.",
            "Change damping with the load case fixed. Compare free decay separately "
            "from continuously forced motion.",
        )
    return None
