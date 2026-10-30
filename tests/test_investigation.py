"""Independent challenge mechanics, fair comparisons and actual UI investigations."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from vibra.studies.investigation import (
    ChallengeInputs,
    calculate_design,
    challenge_explanation,
    compare_designs,
    comparison_rows,
    feasible_depth_interval_mm,
    motor_comparison_rows,
)
from vibra.visualization.investigation import comparison_viewport, motor_snapshot
from vibra.visualization.theme import PALETTES, themed_figure
from vibra.visualization.viewport import engineering_viewport

APP = Path(__file__).resolve().parents[1] / "frontend/app.py"


@pytest.mark.parametrize(
    "depth,passes",
    [
        (20, (False, True)),
        (23.7, (False, True)),
        (23.8, (True, True)),
        (24, (True, True)),
        (24.01, (True, False)),
        (28, (True, False)),
    ],
)
def test_challenge_against_independent_rectangular_beam(
    depth: float, passes: tuple[bool, bool]
) -> None:
    a = calculate_design()
    b = calculate_design(ChallengeInputs(depth_mm=depth))
    h = depth / 1000
    # Independent continuum equations, not ratios of the same FEM implementation.
    inertia = 0.02 * h**3 / 12
    exact_tip = 100 / (3 * 210e9 * inertia)
    exact_stress = 100 * h / 2 / inertia
    assert_allclose(b.max_downward_m, exact_tip, rtol=2e-8)
    assert_allclose(b.max_bending_stress_Pa, exact_stress, rtol=2e-8)
    assert_allclose(b.mass_kg, 7850 * 0.02 * h, rtol=1e-14)
    result = compare_designs(a, b)
    assert_allclose(result.displacement_reduction_percent, 100 * (1 - (20 / depth) ** 3), atol=1e-7)
    assert_allclose(result.mass_increase_percent, 100 * (depth / 20 - 1), atol=1e-12)
    assert (result.displacement_pass, result.mass_pass) == passes
    assert result.passed == all(passes)
    # Continuous cantilever first bending frequency, beta_1=1.875104068711961.
    exact_frequency = (
        1.875104068711961**2 / (2 * np.pi) * np.sqrt(210e9 * inertia / (7850 * 0.02 * h))
    )
    assert_allclose(b.first_frequency_hz, exact_frequency, rtol=2e-6)
    rows = comparison_rows(result)
    assert (
        next(row for row in rows if row["Quantity"] == "Mass [kg]")["B · submitted design"]
        == b.mass_kg
    )
    story = challenge_explanation(result)
    assert f"{result.displacement_reduction_percent:.3f}%" in story[0]
    assert "h⁻²" in story[1] and "safety" in story[2]


def test_feasibility_boundaries_and_invalid_depths() -> None:
    low, high = feasible_depth_interval_mm()
    assert low == pytest.approx(23.71262202993375)
    assert high == 24
    a = calculate_design()
    for depth in (low, high):
        assert compare_designs(a, calculate_design(ChallengeInputs(depth_mm=depth))).passed
    for bad in (0, 19.9, 28.1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            ChallengeInputs(depth_mm=bad)
    with pytest.raises(ValueError, match="fixed 20 mm"):
        compare_designs(calculate_design(ChallengeInputs(depth_mm=24)), a)


@pytest.mark.parametrize(
    "field", ("Displacement magnitude", "Combined normal stress", "Bending moment")
)
def test_common_axes_scales_colors_and_physical_hover(field: Any) -> None:
    comparison = compare_designs(calculate_design(), calculate_design(ChallengeInputs(depth_mm=24)))
    before = comparison.candidate.shelf.result.displacement.copy()
    figure = comparison_viewport(comparison, scale=10, field=field)
    assert figure.layout.xaxis.range == figure.layout.xaxis2.range
    assert figure.layout.yaxis.range == figure.layout.yaxis2.range
    assert figure.layout.yaxis.scaleanchor == "x" and figure.layout.yaxis2.scaleanchor == "x2"
    a, b = [trace for trace in figure.data if trace.name == "Beam 0"]
    for design, trace in ((comparison.baseline, a), (comparison.candidate, b)):
        recovered = design.shelf.stress.sections[0]
        values = np.asarray(trace.customdata)
        assert_allclose(values[:, 1:3], recovered.field.displacement_m)
        assert_allclose(values[:, 4], recovered.field.axial_force_N)
        assert_allclose(values[:, 5], recovered.field.shear_force_N)
        assert_allclose(values[:, 6], recovered.field.bending_moment_Nm)
        assert_allclose(values[:, 7], recovered.combined_top_Pa / 1e6)
        assert_allclose(values[:, 8], recovered.combined_bottom_Pa / 1e6)
        assert_allclose(values[:, 3], trace.marker.color)
        assert "σ top" in trace.hovertemplate and "V=" in trace.hovertemplate
    assert any(trace.name == "Critical section stress (±fiber)" for trace in figure.data)
    assert any(trace.name == "Max translation (sampled)" for trace in figure.data)
    for theme in ("Light", "Dark"):
        styled = themed_figure(figure, theme)
        assert styled.layout.font.color == PALETTES[theme].text
        assert styled.layout.coloraxis.cmax == figure.layout.coloraxis.cmax
        assert styled.layout.xaxis2.range == figure.layout.xaxis2.range
        assert_allclose(
            np.asarray(styled.data[1].customdata), np.asarray(figure.data[1].customdata)
        )
    changed = comparison_viewport(comparison, scale=30, field=field, overlay=False)
    trace = next(trace for trace in changed.data if trace.name == "Beam 0")
    assert_allclose(trace.customdata, a.customdata)
    assert changed.layout.coloraxis.cmax == figure.layout.coloraxis.cmax
    assert not any(trace.name == "Undeformed" for trace in changed.data)
    assert_allclose(comparison.candidate.shelf.result.displacement, before, atol=0, rtol=0)


def _click(app: AppTest, label: str) -> None:
    next(widget for widget in app.button if widget.label == label).click().run()


def test_challenge_submission_pending_edits_and_view_only_controls() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    next(widget for widget in app.radio if widget.label == "Support investigation").set_value(
        "Design a Stronger Support"
    ).run()
    _click(app, "Start design challenge")
    assert not app.exception and not app.error
    saved_a = app.session_state["challenge_baseline"]
    initial = app.session_state["challenge_comparison"]
    assert not initial.passed
    # A browser form keeps edits local until submit; do not simulate an input rerun.
    next(widget for widget in app.number_input if widget.label == "Challenge depth [mm]").set_value(
        24.0
    )
    assert app.session_state["challenge_comparison"] is initial
    _click(app, "Evaluate design")
    saved = app.session_state["challenge_comparison"]
    assert saved.passed and saved.baseline is saved_a
    assert not app.exception and not app.error
    before = saved.candidate.shelf.result.displacement.copy()
    # Fail immediately if presentation changes unexpectedly call either solver.
    with (
        patch(
            "vibra.studies.investigation.run_shelf", side_effect=AssertionError("unexpected solve")
        ),
        patch(
            "vibra.studies.investigation.solve_modal",
            side_effect=AssertionError("unexpected solve"),
        ),
    ):
        next(
            widget for widget in app.number_input if widget.label == "Comparison magnification [×]"
        ).set_value(20).run()
        next(
            widget for widget in app.checkbox if widget.label == "Show undeformed designs"
        ).uncheck().run()
        next(widget for widget in app.radio if widget.label == "Compare field").set_value(
            "Stress"
        ).run()
        next(widget for widget in app.selectbox if widget.label == "Theme").select("Dark").run()
    assert app.session_state["challenge_comparison"] is saved
    assert_allclose(saved.candidate.shelf.result.displacement, before, atol=0, rtol=0)
    assert not app.exception
    _click(app, "Start design challenge")
    assert app.session_state["challenge_baseline"] is saved_a
    assert app.session_state["challenge_comparison"].candidate is saved_a


def test_motor_snapshot_uses_full_complex_state_and_relative_motion() -> None:
    from vibra.studies.beginner import run_motor

    study = run_motor()
    rows = motor_comparison_rows(study)
    isolated = study.cases[2]
    op = int(np.argmin(abs(isolated.harmonic.frequencies_hz - study.config.operating_hz)))
    u = isolated.harmonic.displacement[op]
    expected_relative = (
        abs(u[3 * isolated.force_node + 1] - u[3 * study.config.elements + 1]) * 1000
    )
    assert rows[2]["Motor–rail relative Y amplitude [mm]"] == pytest.approx(expected_relative)
    before = isolated.harmonic.displacement.copy()
    for phase in (0, 90, 210):
        figure = motor_snapshot(study, "isolated", True, phase, 200)
        expected = engineering_viewport(
            isolated.model, np.real(u * np.exp(1j * np.deg2rad(phase))), 200
        )
        actual_beam = next(trace for trace in figure.data if trace.name == "Beam 0")
        expected_beam = next(trace for trace in expected.data if trace.name == "Beam 0")
        assert_allclose(actual_beam.customdata, expected_beam.customdata)
        assert_allclose(actual_beam.y, expected_beam.y)
    assert_allclose(isolated.harmonic.displacement, before, atol=0, rtol=0)


def test_diagnostic_display_zoom_preserves_full_record() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    app.sidebar.selectbox[0].select("Vibration Diagnostics").run()
    _click(app, "Analyze Example")
    saved = app.session_state["beginner_washer_result"]
    before = saved.spectrum.fft_complex.copy()
    next(widget for widget in app.slider if widget.label == "Visible time span [s]").set_value(
        0.5
    ).run()
    assert not app.exception
    assert app.session_state["beginner_washer_result"] is saved
    assert len(saved.series.values) == 2048
    assert_allclose(saved.spectrum.fft_complex, before, atol=0, rtol=0)


def test_hover_preserves_nodal_force_and_moment_jumps() -> None:
    from vibra.core.models import FrameModel, NodalLoad
    from vibra.solvers.static import solve_static
    from vibra.studies.beginner import ShelfInputs, shelf_model

    base = shelf_model(ShelfInputs())
    model = FrameModel(
        **(
            base.model_dump()
            | {
                "loads": (NodalLoad(node=6, fy=-40, mz=10), NodalLoad(node=12, fy=-100)),
            }
        )
    )
    result = solve_static(model)
    figure = engineering_viewport(model, result.displacement, 10)
    left = np.asarray(next(t for t in figure.data if t.name == "Beam 5").customdata)[-1]
    right = np.asarray(next(t for t in figure.data if t.name == "Beam 6").customdata)[0]
    assert_allclose(abs(left[5] - right[5]), 40, atol=1e-6)
    assert_allclose(abs(left[6] - right[6]), 10, atol=1e-6)
    # Same physical node displacement, different one-sided section force/stress.
    assert_allclose(left[1:3], right[1:3], atol=1e-12)
    assert abs(left[7] - right[7]) > 1


def test_motor_view_controls_reuse_submitted_result() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    app.sidebar.selectbox[0].select("Automotive Motor Mount").run()
    _click(app, "Run motor example")
    study = app.session_state["beginner_motor_result"]
    before = study.cases[2].harmonic.displacement.copy()
    with patch(
        "vibra.workbench.beginner.run_motor", side_effect=AssertionError("unexpected solve")
    ):
        next(w for w in app.selectbox if w.label == "Motor configuration").select("rigid").run()
        next(w for w in app.radio if w.label == "Inspect response").set_value(
            "Harmonic excitation"
        ).run()
        next(w for w in app.slider if w.label == "Motor excitation phase [deg]").set_value(90).run()
        next(w for w in app.number_input if w.label == "Motor magnification [×]").set_value(
            2000
        ).run()
        next(w for w in app.selectbox if w.label == "Theme").select("Dark").run()
    assert not app.exception and not app.error
    assert app.session_state["beginner_motor_result"] is study
    assert_allclose(study.cases[2].harmonic.displacement, before, atol=0, rtol=0)
