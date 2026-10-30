"""Guided workflows, provenance, hidden expert settings and presentation invariance."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.testing import assert_allclose
from streamlit.testing.v1 import AppTest

from vibra.core.models import AnalysisConfig
from vibra.solvers.modal import solve_modal
from vibra.studies.beginner import ShelfInputs, run_shelf, run_washer, washer_signal
from vibra.visualization.theme import PALETTES, themed_figure
from vibra.visualization.viewport import engineering_viewport, state_animation
from vibra.workbench.interpretation import beam_interpretation, signal_interpretation

APP = Path(__file__).resolve().parents[1] / "frontend/app.py"
CASES = (
    ("Cantilever Beam", "Run shelf example", "beginner_shelf_result", "shelf on the wall"),
    ("Automotive Motor Mount", "Run motor example", "beginner_motor_result", "electric motor"),
    ("Vibration Diagnostics", "Analyze Example", "beginner_washer_result", "washing machine"),
)


def click(app: AppTest, label: str) -> None:
    next(widget for widget in app.button if widget.label == label).click().run()


def chart_layouts(app: AppTest) -> list[dict[str, Any]]:
    return [json.loads(chart.proto.spec)["layout"] for chart in app.get("plotly_chart")]


@pytest.mark.parametrize("experience,button,key,scenario", CASES)
def test_one_click_beginner_scenarios_and_theme_invariance(
    experience: str, button: str, key: str, scenario: str
) -> None:
    app = AppTest.from_file(str(APP), default_timeout=90).run()
    app.sidebar.selectbox[0].select(experience).run()
    assert not app.exception and not app.error
    assert (
        next(widget for widget in app.radio if widget.label == "Experience level").value
        == "Beginner"
    )
    assert any(scenario in expander.label.lower() for expander in app.expander)
    labels = [widget.label for widget in app.number_input] + [
        widget.label for widget in app.selectbox
    ]
    for hidden in (
        "Beam elements",
        "Young's modulus [GPa]",
        "Analysis",
        "Time step [s]",
        "Window",
        "Detrending",
        "RMS band lower [Hz]",
    ):
        assert hidden not in labels
    click(app, button)
    assert not app.exception and not app.error
    assert any(item.value == "What did we learn?" for item in app.subheader)
    assert any("**What happened?**" in item.value for item in app.markdown)
    assert any("**Why?**" in item.value for item in app.markdown)
    assert any("**Try next**" in item.value for item in app.markdown)
    saved = app.session_state[key]
    before = (
        saved.result.displacement.copy()
        if key == "beginner_shelf_result"
        else saved.cases[2].harmonic.displacement.copy()
        if key == "beginner_motor_result"
        else saved.spectrum.fft_complex.copy()
    )
    next(widget for widget in app.selectbox if widget.label == "Theme").select("Dark").run()
    assert not app.exception and not app.error
    assert app.session_state[key] is saved
    assert all(
        layout["paper_bgcolor"] == PALETTES["Dark"].background for layout in chart_layouts(app)
    )
    after = (
        saved.result.displacement
        if key == "beginner_shelf_result"
        else saved.cases[2].harmonic.displacement
        if key == "beginner_motor_result"
        else saved.spectrum.fft_complex
    )
    assert_allclose(before, after, atol=0, rtol=0)
    next(widget for widget in app.selectbox if widget.label == "Theme").select("Light").run()
    assert not app.exception
    assert all(layout["font"]["color"] == PALETTES["Light"].text for layout in chart_layouts(app))


def test_shelf_guided_changes_and_default_reset() -> None:
    app = AppTest.from_file(str(APP), default_timeout=40).run()
    click(app, "Run shelf example")
    initial = app.session_state["beginner_shelf_result"]
    click(app, "Try 25% thicker")
    thicker = app.session_state["beginner_shelf_result"]
    assert thicker.inputs.thickness_mm == 25
    assert_allclose(
        thicker.result.displacement[-1, 1] / initial.result.displacement[-1, 1],
        1 / 1.25**3,
        rtol=1e-9,
    )
    click(app, "Try double load")
    heavy = app.session_state["beginner_shelf_result"]
    assert_allclose(
        heavy.result.displacement, 2 * thicker.result.displacement, rtol=1e-10, atol=1e-12
    )
    click(app, "Run shelf example")
    assert app.session_state["beginner_shelf_result"].inputs == ShelfInputs()
    assert not app.exception


def test_diagnostic_provenance_defaults_and_advanced_handoff() -> None:
    app = AppTest.from_file(str(APP), default_timeout=50).run()
    app.sidebar.selectbox[0].select("Vibration Diagnostics").run()
    click(app, "Analyze Example")
    example = app.session_state["beginner_washer_result"]
    assert example.series.provenance.kind == "synthetic"
    assert example.series.provenance.details["measured"] is False
    assert example.spectrum.config.window == "hann" and example.spectrum.config.detrend == "mean"
    assert example.spectrum.dominant_frequency_hz == 12
    assert_allclose(example.spectrum.sampling.frequency_resolution_hz, 0.25)
    assert any("not a measured" in item.value for item in app.info)
    click(app, "Try nearby components")
    assert app.session_state["beginner_washer_result"].inputs.second_hz == 12.5
    example = app.session_state["beginner_washer_result"]
    next(widget for widget in app.radio if widget.label == "Experience level").set_value(
        "Advanced"
    ).run()
    assert any(widget.label == "Window" for widget in app.selectbox)
    assert any(widget.label == "Detrending" for widget in app.selectbox)
    click(app, "Analyze signal")
    assert not app.exception and not app.error
    assert app.session_state["signal_solved"]["series"] == example.series
    assert_allclose(
        app.session_state["signal_solved"]["result"].fft_complex,
        example.spectrum.fft_complex,
        atol=0,
        rtol=0,
    )


def test_theme_preserves_geometry_values_phases_and_animation_states() -> None:
    shelf = run_shelf()
    figure = engineering_viewport(
        shelf.model, shelf.result.displacement, 12.6, "Combined normal stress"
    )
    original = figure.to_json()
    mode = solve_modal(shelf.model, AnalysisConfig(modes=1)).modes[:, 0]
    states = np.cos(np.linspace(0, 2 * np.pi, 5)[:, None]) * mode[None, :]
    animation = state_animation(
        shelf.model, states, tuple(str(i) for i in range(5)), 0.1, modal=True
    )
    for theme in ("Light", "Dark"):
        styled = themed_figure(figure, theme)
        assert styled.layout.coloraxis.cmin == figure.layout.coloraxis.cmin
        assert styled.layout.coloraxis.cmax == figure.layout.coloraxis.cmax
        assert styled.layout.coloraxis.cmid == figure.layout.coloraxis.cmid == 0
        for before, after in zip(figure.data, styled.data, strict=True):
            assert_allclose(before.x, after.x)
            assert_allclose(before.y, after.y)
            if before.customdata is not None:
                assert_allclose(before.customdata, after.customdata)
            if getattr(before.marker, "coloraxis", None):
                assert_allclose(before.marker.color, after.marker.color)
        for before, after in zip(figure.layout.annotations, styled.layout.annotations, strict=True):
            assert (before.x, before.y, before.ax, before.ay, before.text) == (
                after.x,
                after.y,
                after.ax,
                after.ay,
                after.text,
            )
        animated = themed_figure(animation, theme)
        assert animated.layout.updatemenus[0].font.color == PALETTES[theme].text
        for before, after in zip(animation.frames, animated.frames, strict=True):
            assert before.layout.title.text == after.layout.title.text
            for a, b in zip(before.data, after.data, strict=True):
                assert_allclose(a.x, b.x)
                assert_allclose(a.y, b.y)
    assert figure.to_json() == original


def test_text_contrast_and_deterministic_teaching_record() -> None:
    def luminance(color: str) -> float:
        rgb = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    for palette in PALETTES.values():
        for foreground in (palette.text, palette.muted):
            values = sorted((luminance(foreground), luminance(palette.background)))
            assert (values[1] + 0.05) / (values[0] + 0.05) >= 4.5
    assert washer_signal() == washer_signal()
    example = run_washer()
    interpretation = signal_interpretation(example.series, example.spectrum)
    assert "12 Hz" in interpretation.happened
    assert "does not identify" in interpretation.why
    assert "simulated" in example.series.provenance.label.lower()
    zero = run_shelf(ShelfInputs(load_N=0))
    assert "zero displacement" in beam_interpretation(zero.model, zero.result).happened


def test_pure_axial_interpretation_does_not_invent_bending() -> None:
    from vibra.solvers.static import solve_static
    from vibra.verification.stress_benchmarks import stress_case

    model = stress_case(axial=20000, transverse=0)
    description = beam_interpretation(model, solve_static(model))
    assert "50 MPa" in description.happened
    assert "axial tension/compression" in description.why
    assert "lever arm" not in description.why
