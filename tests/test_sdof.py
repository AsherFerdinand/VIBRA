"""Analytical response, energy, critical/overdamping and harmonic steady-state checks."""

import json

import numpy as np
import pytest
from numpy.testing import assert_allclose

from vibra.dynamics.sdof import SDOFConfig, solve_sdof
from vibra.io.reports import engineering_report
from vibra.verification.analytical import underdamped_free


@pytest.mark.parametrize("damping", [0.0, 0.8, 10.0])
def test_free_response_and_energy(damping: float) -> None:
    config = SDOFConfig(mass=2, stiffness=200, damping=damping, initial_velocity=0.03)
    result = solve_sdof(config)
    assert_allclose(
        result.displacement, underdamped_free(config, result.time), atol=1e-9, rtol=1e-8
    )
    assert_allclose(result.displacement[0], config.initial_displacement, atol=1e-15)
    assert_allclose(result.velocity[0], config.initial_velocity, atol=1e-15)
    if damping == 0:
        assert_allclose(result.energy / result.energy[0], 1, atol=1e-8)
    else:
        assert np.max(np.diff(result.energy)) < 1e-10
        assert result.energy[-1] < result.energy[0]


@pytest.mark.parametrize("damping", [40.0, 50.0])
def test_critical_and_overdamped_free_response(damping: float) -> None:
    config = SDOFConfig(mass=2, stiffness=200, damping=damping)
    result = solve_sdof(config)
    time = result.time
    if damping == 40:
        exact = config.initial_displacement * (1 + 10 * time) * np.exp(-10 * time)
    else:
        r1, r2 = (
            (-damping + np.sqrt(damping**2 - 4 * 2 * 200)) / 4,
            (-damping - np.sqrt(damping**2 - 4 * 2 * 200)) / 4,
        )
        exact = (
            config.initial_displacement
            * (-r2 * np.exp(r1 * time) + r1 * np.exp(r2 * time))
            / (r1 - r2)
        )
    assert config.damped_angular_frequency is None
    assert_allclose(result.displacement, exact, atol=1e-10)


def test_harmonic_solution_including_transient() -> None:
    # Exact particular sinusoid plus homogeneous transient enforcing zero initial state.
    config = SDOFConfig(
        mass=2,
        stiffness=200,
        damping=2,
        force_amplitude=1,
        excitation_hz=1.3,
        initial_displacement=0,
        duration=15,
        samples=3001,
    )
    result = solve_sdof(config)
    omega = 2 * np.pi * config.excitation_hz
    amplitude = config.force_amplitude / np.hypot(
        config.stiffness - config.mass * omega**2, config.damping * omega
    )
    phase = np.arctan2(config.damping * omega, config.stiffness - config.mass * omega**2)
    particular = amplitude * np.sin(omega * result.time - phase)
    homogeneous = SDOFConfig(
        mass=config.mass,
        stiffness=config.stiffness,
        damping=config.damping,
        initial_displacement=amplitude * np.sin(phase),
        initial_velocity=-amplitude * omega * np.cos(phase),
    )
    exact = particular + underdamped_free(homogeneous, result.time)
    assert_allclose(result.displacement, exact, atol=1e-9)
    assert_allclose(
        config.mass * result.acceleration
        + config.damping * result.velocity
        + config.stiffness * result.displacement,
        config.force_amplitude * np.sin(omega * result.time),
        atol=1e-12,
    )


def test_report_roundtrip() -> None:
    config = SDOFConfig()
    result = solve_sdof(config)
    report = json.loads(engineering_report("SDOF", config, result))
    assert report["inputs"]["mass"] == config.mass
    assert_allclose(report["results"]["displacement"], result.displacement)
    assert "not experimental" in report["validation_status"]
