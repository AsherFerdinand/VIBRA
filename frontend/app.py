"""Guided teaching examples and the complete advanced engineering workbench."""

import logging

import streamlit as st

from vibra.visualization.theme import THEMES
from vibra.workbench.beam import workspace as beam_workspace
from vibra.workbench.beginner import workspace as beginner_workspace
from vibra.workbench.harmonic import workspace as harmonic_workspace
from vibra.workbench.interpretation import advanced_interpretation, render_interpretation
from vibra.workbench.nvh import workspace as motor_workspace
from vibra.workbench.presentation import interface_theme
from vibra.workbench.scenarios import scenario_panel
from vibra.workbench.signals import workspace as signal_workspace
from vibra.workbench.transient import workspace as transient_workspace

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title="VIBRA | Engineering Workbench", page_icon="◫", layout="wide")
experience = st.sidebar.selectbox(
    "Engineering experience", ("Cantilever Beam", "Automotive Motor Mount", "Vibration Diagnostics")
)
level = st.sidebar.radio(
    "Experience level",
    ("Beginner", "Advanced"),
    key="experience_level",
    help=(
        "Beginner runs guided examples with essential controls. Advanced retains all "
        "solver, import, verification and export options."
    ),
)
theme = st.sidebar.selectbox(
    "Theme",
    THEMES,
    key="theme_choice",
    help="Changes presentation only; submitted numerical results stay unchanged.",
)
interface_theme(theme)
st.title("VIBRA")
st.caption("INTERACTIVE ENGINEERING INVESTIGATION · 0.9")
st.sidebar.caption("Model → Loads → Solve → Visualize → Interpret")
scenario_panel(experience)
if level == "Beginner":
    beginner_workspace(experience)
else:
    analysis = "Automotive NVH Study"
    if experience == "Cantilever Beam":
        analysis = st.sidebar.selectbox(
            "Analysis",
            ("Static cantilever", "Cantilever modes", "Harmonic response", "Transient response"),
        )
        if analysis == "Harmonic response":
            harmonic_workspace()
        elif analysis == "Transient response":
            transient_workspace()
        else:
            beam_workspace(analysis)
    elif experience == "Automotive Motor Mount":
        motor_workspace()
    else:
        analysis = st.sidebar.radio("Diagnostic tool", ("Signal Diagnostics", "SDOF vibration"))
        if analysis == "SDOF vibration":
            beam_workspace(analysis)
        else:
            signal_workspace()
    interpretation = advanced_interpretation(experience, analysis)
    if interpretation is not None:
        render_interpretation(interpretation)
