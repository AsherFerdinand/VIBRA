"""Independent stress signs, interpolation, contours and actual animation states."""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError

from vibra.core.assembly import assemble
from vibra.core.errors import EngineeringError
from vibra.core.models import FrameModel, Section
from vibra.postprocessing.beam import recover_stress, sample_beam
from vibra.solvers.static import solve_static
from vibra.studies.installed import InstalledConfig, installed_model
from vibra.verification.stress_benchmarks import stress_case, verification_report
from vibra.visualization.viewport import (
    CONTOURS,
    contour_data,
    engineering_viewport,
    state_animation,
)


def test_independent_stress_benchmarks() -> None:
    report = verification_report()
    assert report["all_passed"], report
    assert not report["experimental_validation"]


@pytest.mark.parametrize("angle", (0, 37, 90, 180))
def test_internal_force_conventions_and_rotated_coordinates(angle: int) -> None:
    model = stress_case(angle)
    result = solve_static(model)
    recovered = recover_stress(model, result.displacement)
    for item in recovered.sections:
        forces = result.element_end_forces[item.field.element_id]
        x = item.field.local_x_m
        assert_allclose(item.field.axial_force_N, -forces[0], rtol=1e-10)
        assert_allclose(item.field.shear_force_N, forces[1], rtol=1e-8, atol=1e-8)
        assert_allclose(
            item.field.bending_moment_Nm, -forces[2] + forces[1] * x, rtol=1e-8, atol=1e-8
        )
    assert_allclose(
        [recovered.maximum_normal_Pa, recovered.minimum_normal_Pa], [125e6, -25e6], rtol=1e-9
    )
    assert_allclose(
        [recovered.critical_absolute.global_x_m, recovered.critical_absolute.global_y_m],
        0,
        atol=1e-12,
    )


def test_hermite_reproduces_analytic_cubic_and_derivatives() -> None:
    model = stress_case(axial=0, transverse=0)
    # Prescribe an arbitrary polynomial in local coordinates, not a solver reference.
    q = np.zeros((len(model.nodes), 3))
    for i, node in enumerate(model.nodes):
        x = node.x
        q[i] = [
            0.002 * x,
            0.001 + 0.002 * x - 0.003 * x * x + 0.004 * x**3,
            0.002 - 0.006 * x + 0.012 * x * x,
        ]
    for field in sample_beam(model, q):
        sample_x = field.position_m[:, 0]
        assert_allclose(field.displacement_m[:, 0], 0.002 * sample_x, atol=1e-14)
        assert_allclose(
            field.displacement_m[:, 1],
            0.001 + 0.002 * sample_x - 0.003 * sample_x * sample_x + 0.004 * sample_x**3,
            atol=1e-14,
        )
        assert_allclose(
            field.rotation_rad, 0.002 - 0.006 * sample_x + 0.012 * sample_x * sample_x, atol=1e-14
        )
        assert_allclose(
            field.bending_moment_Nm,
            model.elements[0].material.young_modulus
            * model.elements[0].section.second_moment
            * (-0.006 + 0.024 * sample_x),
            rtol=1e-12,
            atol=1e-10,
        )
    # Any infinitesimal rigid motion has zero elastic section stress.
    q = np.array([[0.1 - 0.03 * node.y, -0.2 + 0.03 * node.x, 0.03] for node in model.nodes])
    stress = recover_stress(model, q)
    assert abs(stress.maximum_normal_Pa) < 1e-3
    assert abs(stress.minimum_normal_Pa) < 1e-3


def test_contours_units_and_distinct_critical_locations() -> None:
    model = stress_case(axial=0)
    q = solve_static(model).displacement
    stress = recover_stress(model, q)
    assert stress.critical_absolute.element_id == 0
    displacement = contour_data(model, q, "Displacement magnitude")
    flat = np.concatenate([item.values_SI for item in displacement])
    assert np.argmax(flat) == len(flat) - 1
    assert displacement[0].unit == "mm" and displacement[0].display_factor == 1000
    for field in CONTOURS:
        data = contour_data(model, q, field)
        assert len(data) == 8
        figure = engineering_viewport(model, q, 10, field)
        figure2 = engineering_viewport(model, q, 100, field)
        assert figure.layout.meta["physical_min_SI"] == figure2.layout.meta["physical_min_SI"]
        assert figure.layout.meta["physical_max_SI"] == figure2.layout.meta["physical_max_SI"]
        assert figure.layout.coloraxis.colorbar.title.text.endswith(
            "[N m]" if field == "Bending moment" else "[MPa]" if "stress" in field else "[mm]"
        )
        if field != "Displacement magnitude":
            assert figure.layout.coloraxis.cmid == 0
            assert figure.layout.coloraxis.cmin == -figure.layout.coloraxis.cmax
    data = contour_data(model, q, "Combined normal stress", "bottom")
    assert_allclose(data[0].values_SI, -stress.sections[0].combined_top_Pa, rtol=1e-12)
    figure = engineering_viewport(model, q, 20, "Combined normal stress")
    trace = next(trace for trace in figure.data if trace.name == "Beam 0")
    assert_allclose(trace.marker.color, stress.sections[0].combined_top_Pa * 1e-6)
    assert_allclose(np.asarray(trace.customdata)[:, 3], trace.marker.color)
    assert_allclose(
        np.column_stack((trace.x, trace.y)),
        stress.sections[0].field.position_m + 20 * stress.sections[0].field.displacement_m,
    )


def test_modal_and_transient_animation_correspondence() -> None:
    model = stress_case(axial=0)
    q = solve_static(model).displacement.reshape(-1)
    states = np.array([q, q * 0.5, q * 0])
    times = np.array([0.0, 0.1, 0.2])
    response = states[:, -2].copy()
    forces = np.zeros_like(states)
    forces[:, -2] = [-100, -50, 0]
    figure = state_animation(
        model,
        states,
        ("t=0", "t=.1", "t=.2"),
        10,
        times=times,
        response=response,
        force_states=forces,
    )
    assert len(figure.frames) == 3
    rotation = state_animation(
        model, states, ("a", "b", "c"), 10, times=times, response=response, response_unit="rad"
    )
    assert rotation.layout.yaxis2.title.text == "Response [rad]"
    for i, frame in enumerate(figure.frames):
        trace = next(trace for trace in frame.data if trace.name == "Beam 0")
        field = sample_beam(model, states[i])[0]
        assert_allclose(
            np.column_stack((trace.x, trace.y)), field.position_m + 10 * field.displacement_m
        )
        assert_allclose(frame.data[-1].x, [times[i]])
        assert_allclose(frame.data[-1].y, [response[i]])
    assert any(
        "−" in str(a.text) or "-100" in str(a.text) for a in figure.frames[0].layout.annotations
    )
    assert not any(a.visible is not False for a in figure.frames[-1].layout.annotations)
    modal = state_animation(model, states, ("mode 1", "mode .5", "mode 0"), 10, modal=True)
    first = next(trace for trace in modal.frames[0].data if trace.name == "Beam 7")
    second = next(trace for trace in modal.frames[1].data if trace.name == "Beam 7")
    assert_allclose(second.marker.color, 0.5 * np.array(first.marker.color), atol=1e-14)
    assert "relative" in modal.layout.coloraxis.colorbar.title.text
    with pytest.raises(ValueError):
        engineering_viewport(model, q, 1, "Combined normal stress", modal=True)


def test_actual_installed_body_and_mount_geometry() -> None:
    model, node = installed_model(InstalledConfig(), "isolated")
    result = solve_static(model)
    figure = engineering_viewport(
        model,
        result.displacement,
        5,
        "Combined normal stress",
        mount_forces_N=result.mount_forces_N,
    )
    # Only true beam fields receive the contour color axis.
    assert (
        len(
            [
                trace
                for trace in figure.data
                if getattr(trace.marker, "coloraxis", None) == "coloraxis"
            ]
        )
        == 8
    )
    assert any(trace.name == "Rigid motor inertia glyph" for trace in figure.data)
    assert any((trace.name or "").startswith("Mount ") for trace in figure.data)
    a = assemble(model)
    offset = {n: 3 * i for i, n in enumerate(a.node_ids)}
    q = result.displacement.reshape(-1)
    for mount in model.mounts:
        trace = next(
            trace for trace in figure.data if (trace.name or "").startswith(f"Mount {mount.id} ")
        )
        u, v, theta = q[offset[node] : offset[node] + 3]
        expected = np.array(
            [
                model.nodes[-1].x + mount.offset_a[0] + 5 * (u - mount.offset_a[1] * theta),
                model.nodes[-1].y + mount.offset_a[1] + 5 * (v + mount.offset_a[0] * theta),
            ]
        )
        assert_allclose([trace.x[0], trace.y[0]], expected)


def test_missing_fiber_invalid_states_and_sampling() -> None:
    model = stress_case()
    unknown = Section(area=0.0004, second_moment=0.02 * 0.02**3 / 12)
    model = FrameModel(
        **(
            model.model_dump()
            | {
                "elements": tuple(
                    element.model_copy(update={"section": unknown}) for element in model.elements
                )
            }
        )
    )
    q = solve_static(model).displacement
    with pytest.raises(EngineeringError):
        recover_stress(model, q)
    for bad in (np.zeros(2), np.full(q.shape, np.nan), q.astype(complex)):
        with pytest.raises(EngineeringError):
            sample_beam(model, bad)
    for count in (1, 102, True):
        with pytest.raises(EngineeringError):
            sample_beam(model, q, count)
    with pytest.raises((ValidationError, EngineeringError)):
        Section(area=1, second_moment=1, extreme_fiber_distance=-1)
    with pytest.raises(ValueError):
        state_animation(model, np.zeros((61, q.size)), tuple("x" for _ in range(61)), 1)
