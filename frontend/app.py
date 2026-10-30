"""Launch the three-experience VIBRA engineering workbench."""

import logging

import streamlit as st

from vibra.workbench.beam import workspace as beam_workspace
from vibra.workbench.harmonic import workspace as harmonic_workspace
from vibra.workbench.nvh import workspace as motor_workspace
from vibra.workbench.signals import workspace as signal_workspace
from vibra.workbench.transient import workspace as transient_workspace

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
st.set_page_config(page_title="VIBRA | Engineering Workbench", page_icon="◫", layout="wide")
st.html("<style>[data-testid=stMainBlockContainer]{padding-top:2rem;} </style>")
st.title("VIBRA")
st.caption("STRUCTURAL DYNAMICS & FEM WORKBENCH · 0.7 · SI UNITS")
experience = st.sidebar.selectbox(
    "Engineering experience", ("Cantilever Beam", "Automotive Motor Mount", "Vibration Diagnostics")
)
st.sidebar.caption("Model → Loads → Solve → Visualize → Interpret")
if experience == "Cantilever Beam":
    analysis = st.sidebar.selectbox(
        "Analysis",
        (
            "Static cantilever",
            "Cantilever modes",
            "Harmonic response",
            "Transient response",
        ),
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
    tool = st.sidebar.radio("Diagnostic tool", ("Signal Diagnostics", "SDOF vibration"))
    if tool == "SDOF vibration":
        beam_workspace(tool)
    else:
        signal_workspace()
