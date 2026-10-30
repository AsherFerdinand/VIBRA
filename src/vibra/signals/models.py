"""Validated uniformly sampled SI signals; no dependency on FEM solvers."""

from typing import Literal, Self

import numpy as np
from pydantic import Field, JsonValue, model_validator

from vibra.core.errors import EngineeringError
from vibra.core.models import EngineeringModel

MAX_SAMPLES = 131072
SAMPLING_RTOL = 1e-6
SignalUnit = Literal["m", "m/s", "m/s^2", "rad", "rad/s", "rad/s^2"]


class SignalError(EngineeringError):
    """Invalid signal, sampling, or numerically unrepresentable spectral data."""


class Provenance(EngineeringModel):
    kind: Literal["synthetic", "csv", "fem"] = "synthetic"
    label: str = Field(default="User-defined signal", min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class SignalSeries(EngineeringModel):
    time: tuple[float, ...] = Field(min_length=4, max_length=MAX_SAMPLES)
    values: tuple[float, ...] = Field(min_length=4, max_length=MAX_SAMPLES)
    unit: SignalUnit
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def uniform_sampling(self) -> Self:
        if len(self.time) != len(self.values):
            raise SignalError("Time and signal lengths must match.")
        time, values = np.asarray(self.time), np.asarray(self.values)
        if not np.all(np.isfinite(time)) or not np.all(np.isfinite(values)):
            raise SignalError(
                "Signal and timestamps must be finite; missing values are unsupported."
            )
        differences = np.diff(time)
        if np.any(differences <= 0):
            raise SignalError("Timestamps must strictly increase; duplicates are unsupported.")
        interval = (time[-1] - time[0]) / (len(time) - 1)
        if not np.isfinite(interval) or not interval > 0 or not np.isfinite(1 / interval):
            raise SignalError("Sampling interval/rate is outside double-precision range.")
        expected = time[0] + np.arange(len(time)) * interval
        if (
            not np.allclose(differences, interval, rtol=SAMPLING_RTOL, atol=0)
            or np.max(np.abs(time - expected)) > SAMPLING_RTOL * interval
        ):
            raise SignalError("Nonuniform sampling detected; no resampling is performed.")
        return self


class FrequencyBand(EngineeringModel):
    lower_hz: float = Field(ge=0)
    upper_hz: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.upper_hz <= self.lower_hz:
            raise SignalError("Band upper frequency must exceed lower frequency.")
        return self


class SpectrumConfig(EngineeringModel):
    window: Literal["rectangular", "hann", "hamming"] = "hann"
    detrend: Literal["none", "mean", "linear"] = "mean"
    band: FrequencyBand | None = None
    max_peaks: int = Field(default=8, ge=1, le=32)
