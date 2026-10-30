"""Execute real Streamlit widgets and all three solver paths without a browser."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


def navigate(app: AppTest, analysis: str) -> None:
    """Retain all existing solver/UI assertions through the new experience grouping."""
    experience = (
        "Automotive Motor Mount"
        if analysis == "Automotive NVH Study"
        else "Vibration Diagnostics"
        if analysis in ("Signal Diagnostics", "SDOF vibration")
        else "Cantilever Beam"
    )
    app.sidebar.selectbox[0].select(experience).run()
    if experience == "Cantilever Beam":
        next(widget for widget in app.selectbox if widget.label == "Analysis").select(
            analysis
        ).run()
    elif experience == "Vibration Diagnostics":
        next(widget for widget in app.radio if widget.label == "Diagnostic tool").set_value(
            analysis
        ).run()
    elif experience == "Automotive Motor Mount":
        next(widget for widget in app.radio if widget.label == "Investigation").set_value(
            "Bare rail A/B (0.5 reference)"
        ).run()


@pytest.mark.parametrize("analysis", ["Static cantilever", "Cantilever modes", "SDOF vibration"])
def test_workbench_workflows(analysis: str) -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    navigate(app, analysis)
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
    navigate(app, "Harmonic response")
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
    navigate(app, "Harmonic response")
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
    navigate(app, "Harmonic response")
    next(widget for widget in app.selectbox if widget.label == "Damping model").select(kind).run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["harmonic_solved"]["config"].damping.kind == kind
    if kind == "undamped":
        assert app.warning


@pytest.mark.parametrize("excitation", ["pulse", "step", "harmonic", "sampled"])
def test_transient_workspace_excitation_and_time_slider(excitation: str) -> None:
    import numpy as np

    app = AppTest.from_file(str(APP), default_timeout=30).run()
    navigate(app, "Transient response")
    next(widget for widget in app.selectbox if widget.label == "Time excitation").select(
        excitation
    ).run()
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert "transient_solved" in app.session_state
    saved = app.session_state["transient_solved"]
    assert saved["config"].loads[0].kind == excitation
    assert saved["result"].relative_energy_error < 1e-6
    before = saved["result"].displacement.copy()
    next(widget for widget in app.slider if widget.label == "Time sample").set_value(25).run()
    assert not app.exception
    np.testing.assert_allclose(app.session_state["transient_solved"]["result"].displacement, before)
    assert app.metric[0].value == "0.025"
    if excitation == "pulse":
        app.checkbox[0].set_value(True).run()
        assert not app.exception
        assert not app.error


def test_transient_workspace_initial_profile_and_invalid_grid() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    navigate(app, "Transient response")
    next(
        widget for widget in app.number_input if widget.label == "Signed force [N] / moment [N m]"
    ).set_value(0.0)
    next(
        widget
        for widget in app.number_input
        if widget.label == "Initial transverse tip displacement [m]"
    ).set_value(0.001)
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["transient_solved"]["result"].displacement[0, -2] == 0.001
    next(widget for widget in app.number_input if widget.label == "Time step [s]").set_value(0.003)
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert app.error
    assert "transient_solved" not in app.session_state


def test_signal_workspace_fem_integration_and_spectrum_controls() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    navigate(app, "Signal Diagnostics")
    next(
        widget for widget in app.button if widget.label == "Generate cantilever pulse simulation"
    ).click().run()
    assert not app.exception
    next(widget for widget in app.button if widget.label == "Analyze signal").click().run()
    assert not app.exception
    assert not app.error
    saved = app.session_state["signal_solved"]
    assert saved["series"].provenance.kind == "fem"
    assert saved["result"].dominant_frequency_hz > 0
    next(widget for widget in app.radio if widget.label == "Primary spectrum").set_value(
        "PSD"
    ).run()
    assert not app.exception
    next(widget for widget in app.selectbox if widget.label == "Signal quantity").select(
        "acceleration"
    ).run()
    next(widget for widget in app.button if widget.label == "Analyze signal").click().run()
    assert not app.exception
    assert app.session_state["signal_solved"]["series"].unit == "m/s^2"


def test_signal_workspace_csv_and_invalid_sampling() -> None:
    import numpy as np

    app = AppTest.from_file(str(APP), default_timeout=30).run()
    navigate(app, "Signal Diagnostics")
    next(widget for widget in app.radio if widget.label == "Signal source").set_value(
        "CSV import"
    ).run()
    text = "time,signal\n" + "\n".join(
        f"{i / 1024},{np.cos(2 * np.pi * 100 * i / 1024)}" for i in range(1024)
    )
    app.text_area[0].set_value(text).run()
    next(widget for widget in app.button if widget.label == "Analyze signal").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["signal_solved"]["result"].dominant_frequency_hz == 100
    app.text_area[0].set_value("time,signal\n0,1\n.1,2\n.2,3\n.4,4").run()
    assert not app.exception
    assert app.error
    assert "signal_solved" not in app.session_state


def test_automotive_nvh_workspace_runs_real_study_and_exports() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    navigate(app, "Automotive NVH Study")
    next(widget for widget in app.button if widget.label == "Run engineering study").click().run()
    assert not app.exception
    assert not app.error
    study = app.session_state["nvh_study"]
    assert all(study.verification_checks.values())
    assert (
        study.modified.summary.operating_amplitude_m > study.baseline.summary.operating_amplitude_m
    )
    next(widget for widget in app.selectbox if widget.label == "Mode design").select(
        "Modified B"
    ).run()
    assert not app.exception
    assert (
        app.session_state["nvh_study"].modified.summary.first_natural_hz
        == study.modified.summary.first_natural_hz
    )
    next(widget for widget in app.number_input if widget.label == "Base time step [s]").set_value(
        0.0003
    )
    next(widget for widget in app.button if widget.label == "Run engineering study").click().run()
    assert not app.exception
    assert app.error
    assert "nvh_study" not in app.session_state


def test_installed_motor_workspace_executes_and_interacts() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    navigate(app, "Automotive NVH Study")
    next(widget for widget in app.radio if widget.label == "Investigation").set_value(
        "Installed motor A/B/C"
    ).run()
    next(
        widget for widget in app.button if widget.label == "Run installed motor study"
    ).click().run()
    assert not app.exception
    assert not app.error
    study = app.session_state["installed_study"]
    assert all(study.checks.values())
    assert study.cases[2].model.mounts[0].node_b == 8
    next(widget for widget in app.selectbox if widget.label == "Installed topology").select(
        "isolated"
    ).run()
    next(widget for widget in app.slider if widget.label == "Installed mode number").set_value(
        2
    ).run()
    next(
        widget for widget in app.slider if widget.label == "Installed deformation time [s]"
    ).set_value(0.1).run()
    assert not app.exception
    next(
        widget for widget in app.number_input if widget.label == "Installed time step [s]"
    ).set_value(0.0003)
    next(
        widget for widget in app.button if widget.label == "Run installed motor study"
    ).click().run()
    assert not app.exception
    assert app.error
    assert "installed_study" not in app.session_state


def test_three_experiences_and_static_stress_interpretation() -> None:
    import numpy as np

    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert app.sidebar.selectbox[0].options == [
        "Cantilever Beam",
        "Automotive Motor Mount",
        "Vibration Diagnostics",
    ]
    next(widget for widget in app.number_input if widget.label == "Tip axial force [N]").set_value(
        20000.0
    )
    app.sidebar.button[0].click().run()
    assert not app.exception and not app.error
    before = app.session_state["solved"]["result"].displacement.copy()
    next(widget for widget in app.selectbox if widget.label == "Contour field").select(
        "Combined normal stress"
    ).run()
    next(widget for widget in app.selectbox if widget.label == "Section fiber").select(
        "bottom"
    ).run()
    assert not app.exception
    assert any("125 MPa" in item.value for item in app.info)
    np.testing.assert_allclose(app.session_state["solved"]["result"].displacement, before, atol=0)
    next(widget for widget in app.checkbox if widget.label == "Show deformation").set_value(
        False
    ).run()
    assert not app.exception


def test_mode_and_harmonic_animation_controls_use_saved_results() -> None:
    import numpy as np

    app = AppTest.from_file(str(APP), default_timeout=60).run()
    navigate(app, "Cantilever modes")
    app.sidebar.button[0].click().run()
    before = app.session_state["solved"]["result"].modes.copy()
    next(widget for widget in app.checkbox if widget.label == "Animate mode shape").set_value(
        True
    ).run()
    assert not app.exception
    np.testing.assert_allclose(app.session_state["solved"]["result"].modes, before, atol=0)
    navigate(app, "Harmonic response")
    app.sidebar.button[0].click().run()
    before_h = app.session_state["harmonic_solved"]["result"].displacement.copy()
    next(widget for widget in app.checkbox if widget.label == "Animate harmonic cycle").set_value(
        True
    ).run()
    assert not app.exception
    np.testing.assert_allclose(
        app.session_state["harmonic_solved"]["result"].displacement, before_h, atol=0
    )
