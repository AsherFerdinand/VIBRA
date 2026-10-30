"""Reproducible teaching examples orchestrating existing solvers and signal analysis."""

from dataclasses import dataclass

import numpy as np
from pydantic import Field

from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import EngineeringModel, FrameModel, Material, Rectangle
from vibra.postprocessing.beam import StressResult, recover_stress
from vibra.signals.analysis import SpectrumResult, analyze_signal
from vibra.signals.models import Provenance, SignalSeries, SpectrumConfig
from vibra.solvers.static import StaticResult, solve_static
from vibra.studies.installed import InstalledConfig, InstalledStudy, run_installed_study


class ShelfInputs(EngineeringModel):
    length_m: float = Field(default=1, ge=0.3, le=1.5)
    thickness_mm: float = Field(default=20, ge=8, le=40)
    load_N: float = Field(default=100, ge=0, le=300)


@dataclass(frozen=True)
class ShelfExample:
    inputs: ShelfInputs
    model: FrameModel
    result: StaticResult
    stress: StressResult


def shelf_model(inputs: ShelfInputs) -> FrameModel:
    return cantilever(
        BeamGeometry(length=inputs.length_m),
        Material(young_modulus=210e9, density=7850),
        Rectangle(width=0.02, height=inputs.thickness_mm / 1000).section(),
        12,
        tip_force=-inputs.load_N,
    )


def run_shelf(inputs: ShelfInputs | None = None) -> ShelfExample:
    inputs = inputs or ShelfInputs()
    model = shelf_model(inputs)
    result = solve_static(model)
    return ShelfExample(inputs, model, result, recover_stress(model, result.displacement))


class MotorInputs(EngineeringModel):
    mass_kg: float = Field(default=12, ge=2, le=30)
    mount_stiffness_N_per_m: float = Field(default=80000, ge=20000, le=320000)
    excitation_hz: float = Field(default=60, ge=1, le=100)


def motor_config(inputs: MotorInputs) -> InstalledConfig:
    return InstalledConfig(
        motor_mass_kg=inputs.mass_kg,
        stiffness_y_N_per_m=inputs.mount_stiffness_N_per_m,
        operating_hz=inputs.excitation_hz,
    )


def run_motor(inputs: MotorInputs | None = None) -> InstalledStudy:
    return run_installed_study(motor_config(inputs or MotorInputs()))


class WasherInputs(EngineeringModel):
    spin_hz: float = Field(default=12, ge=5, le=30)
    second_hz: float = Field(default=24, ge=5, le=60)


@dataclass(frozen=True)
class WasherExample:
    inputs: WasherInputs
    series: SignalSeries
    spectrum: SpectrumResult


def washer_signal(inputs: WasherInputs | None = None) -> SignalSeries:
    """Illustrative stationary spin segment, not measured data or a fault model.

    512 samples/s for 4 s (2048 samples, endpoint excluded). Components have peak
    accelerations 0.6 and 0.15 m/s² plus seeded Gaussian noise with sigma=0.02 m/s².
    The second component equals the second order only at the default 12/24 Hz.
    """
    inputs = inputs or WasherInputs()
    time = np.arange(2048, dtype=np.float64) / 512
    values = (
        0.6 * np.sin(2 * np.pi * inputs.spin_hz * time)
        + 0.15 * np.sin(2 * np.pi * inputs.second_hz * time + 0.4)
        + 0.02 * np.random.default_rng(8).normal(size=len(time))
    )
    return SignalSeries(
        time=tuple(float(v) for v in time),
        values=tuple(float(v) for v in values),
        unit="m/s^2",
        provenance=Provenance(
            kind="synthetic",
            label="Simulated washing-machine steady spin segment",
            details=dict(
                spin_hz=inputs.spin_hz,
                second_component_hz=inputs.second_hz,
                peak_components_m_per_s2=[0.6, 0.15],
                noise_sigma_m_per_s2=0.02,
                noise_seed=8,
                sampling_hz=512,
                dft_duration_s=4,
                measured=False,
                fault_model=False,
            ),
        ),
    )


def run_washer(inputs: WasherInputs | None = None) -> WasherExample:
    inputs = inputs or WasherInputs()
    series = washer_signal(inputs)
    return WasherExample(inputs, series, analyze_signal(series, SpectrumConfig()))
