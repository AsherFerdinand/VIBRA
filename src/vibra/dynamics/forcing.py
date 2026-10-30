"""Nodal histories with explicit right/left force limits at aligned force jumps."""

from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from vibra.core.dynamic_models import ResponseDOF
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError


class StepForce(ResponseDOF):
    kind: Literal["step"] = "step"
    amplitude: float = 1.0  # signed N or N m
    start_time: float = Field(default=0, ge=0)


class HarmonicForce(ResponseDOF):
    kind: Literal["harmonic"] = "harmonic"
    amplitude: float = 1.0
    start_time: float = Field(default=0, ge=0)
    frequency_hz: float = Field(default=1, ge=0)
    phase_degrees: float = 0.0


class PulseForce(ResponseDOF):
    kind: Literal["pulse"] = "pulse"
    amplitude: float = 1.0
    start_time: float = Field(default=0, ge=0)
    end_time: float = Field(gt=0)
    shape: Literal["rectangular", "half_sine"] = "half_sine"

    @model_validator(mode="after")
    def positive_width(self) -> Self:
        if self.end_time <= self.start_time:
            raise InvalidModelError("Pulse end must exceed its start time.")
        return self


class SampledForce(ResponseDOF):
    kind: Literal["sampled"] = "sampled"
    times: tuple[float, ...] = Field(min_length=2, max_length=10001)
    values: tuple[float, ...] = Field(min_length=2, max_length=10001)

    @model_validator(mode="after")
    def valid_history(self) -> Self:
        if len(self.times) != len(self.values):
            raise InvalidModelError("Sampled force times and values must have equal lengths.")
        if self.times[0] != 0 or np.any(np.diff(self.times) <= 0):
            raise InvalidModelError("Sample times must start at zero and strictly increase.")
        return self


TransientForce = Annotated[
    StepForce | HarmonicForce | PulseForce | SampledForce, Field(discriminator="kind")
]


def force_limits(load: TransientForce, time: Matrix) -> tuple[Matrix, Matrix]:
    """Return right- and left-limit nodal force samples on a validated uniform grid.

    Newmark uses right force at interval start and left force at interval end.
    At a discontinuity u,v stay continuous; acceleration is reset from equilibrium.
    Sampled inputs are continuous piecewise-linear interpolants covering [0,T].
    """
    if isinstance(load, SampledForce):
        if time[-1] > load.times[-1]:
            raise InvalidModelError("Sampled force history must cover the full simulation.")
        interpolated = np.interp(time, load.times, load.values)
        return interpolated, interpolated.copy()
    step = float(time[1] - time[0])
    indices = np.arange(len(time))

    def event_index(event: float) -> int:
        return int(round(event / step)) if event <= time[-1] else len(time)

    start = event_index(load.start_time)
    if isinstance(load, StepForce):
        return (
            np.asarray(load.amplitude * (indices >= start), dtype=np.float64),
            np.asarray(load.amplitude * (indices > start), dtype=np.float64),
        )
    if isinstance(load, HarmonicForce):
        with np.errstate(over="ignore", invalid="ignore"):
            values = load.amplitude * np.cos(
                2 * np.pi * load.frequency_hz * (time - load.start_time)
                + np.deg2rad(load.phase_degrees % 360)
            )
        return np.where(indices >= start, values, 0), np.where(indices > start, values, 0)
    end = event_index(load.end_time)
    if load.shape == "rectangular":
        return (
            np.asarray(load.amplitude * ((indices >= start) & (indices < end)), dtype=np.float64),
            np.asarray(load.amplitude * ((indices > start) & (indices <= end)), dtype=np.float64),
        )
    values = load.amplitude * np.sin(
        np.pi * (time - load.start_time) / (load.end_time - load.start_time)
    )
    values = np.where((indices > start) & (indices < end), values, 0)
    return values, values.copy()
