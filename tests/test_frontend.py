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
