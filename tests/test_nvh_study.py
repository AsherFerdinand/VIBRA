"""Engineering orchestration, analytical scaling, integrity and repeatability."""

import json
from dataclasses import asdict

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError

from vibra.core.assembly import assemble
from vibra.core.errors import EngineeringError
from vibra.io.nvh_report import study_json, study_markdown
from vibra.solvers.harmonic import solve_harmonic
from vibra.solvers.static import solve_static
from vibra.studies.nvh import NVHConfig, NVHStudy, SupportDesign, run_nvh_study, support_model


@pytest.fixture(scope="module")
def study() -> NVHStudy:
    return run_nvh_study()


def test_support_construction_and_structural_mass(study: NVHStudy) -> None:
    for item in (study.baseline, study.modified):
        model = item.model
        assert len(model.elements) == 8
        assert_allclose([model.nodes[0].x, model.nodes[-1].x], [0, item.design.length], atol=1e-15)
        assert len(model.constraints) == 3
        assert model.loads[0].node == 8 and model.loads[0].fy == -200
        assembly = assemble(model)
        translation = np.zeros(3 * len(model.nodes))
        translation[::3] = 1
        assert_allclose(
            translation @ assembly.mass @ translation, item.design.structural_mass, rtol=1e-12
        )
        assert_allclose(item.summary.support_reactions_N_Nm, [0, 200, 90], atol=1e-6)
        assert_allclose(item.summary.equilibrium_residual_N_Nm, 0, atol=1e-6)
        assert item.summary.maximum_axial_end_force_N == 0
        assert_allclose(item.summary.maximum_end_moment_Nm, 90, atol=1e-6)


def test_controlled_design_and_parameter_scaling(study: NVHStudy) -> None:
    a, b = study.baseline.summary, study.modified.summary
    assert_allclose(b.mass_kg / a.mass_kg, 1.25, rtol=1e-12)
    assert_allclose(
        b.maximum_static_translation_m / a.maximum_static_translation_m, 1 / 1.25**3, rtol=1e-8
    )
    assert_allclose(b.first_natural_hz / a.first_natural_hz, 1.25, rtol=1e-7)
    assert len(study.parameter_variations) == 10
    for row in study.parameter_variations:
        assert_allclose(row.first_frequency_ratio, row.expected_frequency_ratio, rtol=1e-6)
        assert_allclose(row.static_tip_ratio, row.expected_static_ratio, rtol=1e-7)
    width = [row for row in study.parameter_variations if row.parameter == "width"]
    assert_allclose([r.first_frequency_ratio for r in width], 1, rtol=1e-7)
    assert_allclose([r.mass_ratio for r in width], [0.9, 1.1], rtol=1e-12)


def test_actual_solver_orchestration_and_tradeoff(study: NVHStudy) -> None:
    a, b = study.baseline, study.modified
    direct = solve_static(a.model)
    assert_allclose(a.static.displacement, direct.displacement, rtol=1e-12)
    h = solve_harmonic(a.model, a.harmonic_config)
    assert_allclose(h.displacement, a.harmonic.displacement, rtol=1e-12)
    assert study.config.operating_frequency_hz == 60
    assert study.config.operating_rpm / 60 == 30
    assert b.summary.operating_amplitude_m > 3 * a.summary.operating_amplitude_m
    assert b.summary.maximum_static_translation_m < a.summary.maximum_static_translation_m
    assert b.summary.sampled_harmonic_peak_m < a.summary.sampled_harmonic_peak_m
    for rows in study.sensitivities.values():
        assert (
            rows[0].sampled_peak_amplitude_m
            > rows[1].sampled_peak_amplitude_m
            > rows[2].sampled_peak_amplitude_m
        )
        assert_allclose(
            rows[5].first_natural_hz / rows[1].first_natural_hz, np.sqrt(0.9), rtol=1e-7
        )
        assert_allclose(
            rows[6].first_natural_hz / rows[1].first_natural_hz, np.sqrt(1.1), rtol=1e-7
        )
        # Interchanging excitation and observation preserves reciprocal displacement transfer.
        assert_allclose(rows[3].operating_amplitude_m, rows[4].operating_amplitude_m, rtol=1e-9)


def test_transient_signals_energy_and_convergence(study: NVHStudy) -> None:
    assert all(study.verification_checks.values())
    for item in (study.baseline, study.modified):
        result = item.transient
        assert_allclose(result.displacement[0], 0, atol=0)
        assert result.relative_energy_error < 1e-8
        energy = result.kinetic_energy + result.strain_energy
        pulse_end = 100
        assert np.max(np.diff(energy[pulse_end:])) < 1e-12
        assert_allclose(result.external_work[pulse_end:], result.external_work[pulse_end], atol=0)
        assert item.summary.final_to_pulse_end_energy_ratio < 0.02
        assert item.summary.maximum_dynamic_support_force_N > 0
        for quantity, signal in item.signals.items():
            source = result.displacement if quantity == "displacement" else result.acceleration
            indices = np.searchsorted(result.time, signal.series.time)
            assert_allclose(signal.series.values, source[indices, -2], atol=0)
            assert signal.series.provenance.kind == "fem"
            assert signal.spectrum.dominant_frequency_hz is not None
            assert (
                abs(signal.spectrum.dominant_frequency_hz - item.modal.frequencies_hz[0])
                <= signal.spectrum.sampling.frequency_resolution_hz
            )
    for conv in study.convergence:
        assert (
            conv.time[0].relative_difference_from_finest
            > conv.time[1].relative_difference_from_finest
            > 0
        )
        assert (
            conv.mesh[0].relative_difference_from_finest
            > conv.mesh[1].relative_difference_from_finest
            > 0
        )
        assert conv.time[-1].relative_difference_from_finest == 0
        assert conv.mesh[-1].relative_difference_from_finest == 0
        assert conv.time[0].relative_acceleration_difference_from_finest < 0.05


def test_json_markdown_integrity_and_reproducibility(study: NVHStudy) -> None:
    report = json.loads(study_json(study))
    assert report["inputs"]["modified"]["height"] == 0.015
    assert report["results"]["all_study_checks_passed"] is True
    assert not any(report["results"]["claim_scope"].values())
    assert report["results"]["load_definitions"]["order_excitation_frequency_hz"] == 60
    assert report["results"]["baseline"]["summary"]["mass_kg"] == study.baseline.summary.mass_kg
    assert (
        report["results"]["baseline"]["signals"]["acceleration"]["results"][
            "verification_metadata"
        ]["experimental_validation"]
        is False
    )
    assert len(study_json(study).encode()) < 25_000_000
    markdown = study_markdown(study)
    assert "not a production bracket" in markdown
    assert "48.80%" in markdown
    assert "universally superior" in markdown
    assert "Relative a diff" in markdown
    repeated = run_nvh_study()
    assert repeated.config == study.config
    for key, value in asdict(study.baseline.summary).items():
        other = asdict(repeated.baseline.summary)[key]
        assert_allclose(other, value, rtol=1e-11, atol=1e-13)
    assert_allclose(
        repeated.modified.transient.displacement,
        study.modified.transient.displacement,
        rtol=1e-11,
        atol=1e-13,
    )


@pytest.mark.parametrize(
    "data",
    [
        {"length": 0},
        {"density": -1},
        {"height": 0},
        {"young_modulus": float("nan")},
        {"length": 0.1, "height": 0.02},
    ],
)
def test_invalid_designs(data: dict[str, float]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        SupportDesign.model_validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {"elements": 6},
        {"excitation_fraction": 0.3},
        {"monitor_fraction": 0},
        {"static_force_N": 0},
        {"pulse_force_N": 0},
        {"harmonic_force_N": -1},
        {"operating_rpm": 10000},
        {"damping": {"kind": "undamped"}},
        {"grid": {"duration": 1, "time_step": 0.0001}},
        {"pulse_width_s": 0.01005},
        {"pulse_width_s": 0.1999},
    ],
)
def test_invalid_study_inputs(data: dict[str, object]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        NVHConfig.model_validate(data)


def test_station_validation() -> None:
    with pytest.raises(EngineeringError):
        support_model(SupportDesign(), 6, -200)
