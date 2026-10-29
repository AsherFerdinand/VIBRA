"""Execute real Streamlit widgets and all three solver paths without a browser."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


@pytest.mark.parametrize("analysis", ["Static cantilever", "Cantilever modes", "SDOF vibration"])
def test_workbench_workflows(analysis: str) -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    app.sidebar.selectbox[0].select(analysis).run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert "solved" in app.session_state
    assert app.session_state["solved"]["analysis"] == analysis
    if analysis == "Cantilever modes":
        next(widget for widget in app.selectbox if widget.label == "Display mode").select(1).run()
        assert not app.exception
        assert app.session_state["solved"]["result"].frequencies_hz[0] > 0
    else:
        assert len(app.metric) == 3


def test_harmonic_workspace_multiple_responses_and_zero_load() -> None:
    import numpy as np

    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.sidebar.selectbox[0].select("Harmonic response").run()
    assert not app.exception
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert "harmonic_solved" in app.session_state
    before = app.session_state["harmonic_solved"]["result"].displacement.copy()
    next(widget for widget in app.slider if widget.label == "Cycle phase θ [deg]").set_value(
        90
    ).run()
    assert not app.exception
    np.testing.assert_allclose(app.session_state["harmonic_solved"]["result"].displacement, before)
    next(widget for widget in app.multiselect if widget.label == "Response nodes").set_value(
        [6, 12]
    )
    next(widget for widget in app.multiselect if widget.label == "Response DOFs").set_value(
        ["UY", "RZ"]
    )
    next(widget for widget in app.number_input if widget.label == "Excitation node").set_value(6)
    next(widget for widget in app.number_input if widget.label == "Load phase [deg]").set_value(
        35.0
    )
    app.sidebar.button[0].click().run()
    assert not app.exception
    saved = app.session_state["harmonic_solved"]
    assert len(saved["result"].response_dofs) == 4
    assert saved["config"].loads[0].node == 6
    assert saved["config"].loads[0].phase_degrees == 35
    next(
        widget for widget in app.number_input if widget.label == "Peak force [N] / moment [N m]"
    ).set_value(0.0)
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert not np.any(app.session_state["harmonic_solved"]["result"].phase_defined)
    assert app.metric[2].value == "Undefined"


def test_harmonic_workspace_invalid_sweep_clears_old_results() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.sidebar.selectbox[0].select("Harmonic response").run()
    app.sidebar.button[0].click().run()
    assert "harmonic_solved" in app.session_state
    next(widget for widget in app.number_input if widget.label == "Start frequency [Hz]").set_value(
        100.0
    )
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert app.error
    assert "harmonic_solved" not in app.session_state


@pytest.mark.parametrize("kind", ["undamped", "mass", "stiffness"])
def test_harmonic_workspace_damping_models(kind: str) -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.sidebar.selectbox[0].select("Harmonic response").run()
    next(widget for widget in app.selectbox if widget.label == "Damping model").select(kind).run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["harmonic_solved"]["config"].damping.kind == kind
    if kind == "undamped":
        assert app.warning
