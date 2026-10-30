"""Correctly normalized real FFT, modified periodogram and vibration metrics."""

import hashlib
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from vibra.core.element import Matrix
from vibra.signals.models import SAMPLING_RTOL, SignalError, SignalSeries, SpectrumConfig


@dataclass(frozen=True)
class SamplingMetadata:
    samples: int
    sample_interval_s: float
    sampling_frequency_hz: float
    sample_span_s: float  # (N−1) dt
    dft_duration_s: float  # N dt, not the first-to-last sample span
    nyquist_hz: float
    frequency_resolution_hz: float
    uniformity_relative_tolerance: float = SAMPLING_RTOL


@dataclass(frozen=True)
class TimeMetrics:
    mean: float
    standard_deviation: float  # population, ddof=0
    rms: float
    peak_absolute: float
    peak_to_peak: float
    crest_factor: float | None  # undefined for identically zero signals


@dataclass(frozen=True)
class SpectralPeak:
    bin_index: int
    frequency_hz: float
    peak_amplitude: float
    psd: float
    at_frequency_boundary: bool


@dataclass(frozen=True)
class SpectrumResult:
    sampling: SamplingMetadata
    unit: str
    config: SpectrumConfig
    processed_values: Matrix
    frequencies_hz: Matrix
    fft_complex: NDArray[np.complex128]  # unnormalized rFFT of processed*window
    peak_amplitude: Matrix
    rms_amplitude: Matrix
    power_spectrum: Matrix  # coherent-gain power, equals rms_amplitude²
    psd: Matrix  # modified periodogram, signal-unit²/Hz
    coherent_gain: float
    window_power_gain: float
    enbw_bins: float
    enbw_hz: float
    raw_metrics: TimeMetrics
    processed_metrics: TimeMetrics
    window_weighted_mean_square: float
    integrated_psd_mean_square: float
    band_limited_rms: float | None
    dominant_frequency_hz: float | None  # largest resolved non-DC PSD bin
    peaks: tuple[SpectralPeak, ...]  # interior maxima plus a resolved high-frequency edge
    numerical_warnings: tuple[str, ...]
    source_fingerprint: str


def signal_fingerprint(series: SignalSeries) -> str:
    """Bind a result to its exact supplied data, units and provenance."""
    return hashlib.sha256(series.model_dump_json().encode()).hexdigest()


def sampling_metadata(series: SignalSeries) -> SamplingMetadata:
    count = len(series.time)
    span = series.time[-1] - series.time[0]
    interval = span / (count - 1)
    rate = 1 / interval
    if any(not np.isfinite(v) or v <= 0 for v in (count * interval, rate / 2, rate / count)):
        raise SignalError("Sampling metadata is outside double-precision range.")
    return SamplingMetadata(count, interval, rate, span, count * interval, rate / 2, rate / count)


def time_metrics(values: Matrix) -> TimeMetrics:
    # Scale before squaring to avoid avoidable overflow during RMS calculations.
    peak = float(np.max(np.abs(values)))
    rms = peak * float(np.sqrt(np.mean((values / peak) ** 2))) if peak else 0.0
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=0))
    ptp = float(np.ptp(values))
    if not all(np.isfinite(v) for v in (rms, mean, std, ptp)):
        raise SignalError("Time-domain metrics overflowed; check signal magnitudes/SI units.")
    return TimeMetrics(mean, std, rms, peak, ptp, peak / rms if rms else None)


def analyze_signal(series: SignalSeries, config: SpectrumConfig | None = None) -> SpectrumResult:
    config = config or SpectrumConfig()
    metadata = sampling_metadata(series)
    if config.band is not None and config.band.upper_hz > metadata.nyquist_hz:
        raise SignalError("Band limit exceeds Nyquist frequency.")
    raw = np.asarray(series.values, dtype=np.float64)
    raw_metrics = time_metrics(raw)
    if config.detrend == "mean":
        processed = raw - np.mean(raw)
    elif config.detrend == "linear":
        processed = np.asarray(signal.detrend(raw, type="linear"), dtype=np.float64)
    else:
        processed = raw.copy()
    processed_metrics = time_metrics(processed)
    window_name = "boxcar" if config.window == "rectangular" else config.window
    window = np.asarray(
        signal.get_window(window_name, metadata.samples, fftbins=True), dtype=np.float64
    )
    window_sum, window_square_sum = float(np.sum(window)), float(window @ window)
    coherent_gain = window_sum / metadata.samples
    power_gain = window_square_sum / metadata.samples
    enbw_hz = metadata.sampling_frequency_hz * window_square_sum / window_sum**2
    enbw_bins = enbw_hz / metadata.frequency_resolution_hz
    transform = np.asarray(np.fft.rfft(processed * window), dtype=np.complex128)
    frequencies = np.fft.rfftfreq(metadata.samples, metadata.sample_interval_s)
    weights = np.full(len(transform), 2.0)
    weights[0] = 1
    if metadata.samples % 2 == 0:
        weights[-1] = 1  # Nyquist is self-conjugate, like DC
    magnitude = np.abs(transform)
    peak_amplitude = weights * magnitude / window_sum
    rms_amplitude = np.sqrt(weights) * magnitude / window_sum
    power = weights * magnitude**2 / window_sum**2
    psd = weights * magnitude**2 / (metadata.sampling_frequency_hz * window_square_sum)
    weighted_ms = float(np.sum((processed * window) ** 2) / window_square_sum)
    integrated = float(np.sum(psd) * metadata.frequency_resolution_hz)
    if not all(
        np.all(np.isfinite(v)) for v in (transform, peak_amplitude, rms_amplitude, power, psd)
    ):
        raise SignalError("Spectral quantities overflowed; check SI magnitudes.")
    if np.any(processed * window != 0) and weighted_ms == 0:
        raise SignalError("Signal energy underflows double precision; change the input scale.")
    if not np.isfinite(weighted_ms) or not np.isfinite(integrated):
        raise SignalError("Spectral mean-square calculation is nonfinite.")
    if abs(integrated - weighted_ms) > 1e-11 * max(integrated, weighted_ms):
        raise SignalError("FFT/PSD Parseval consistency failed.")
    notes = [
        "Bin peaks are sampled spectral estimates, not measured modal identification.",
        "Coherent-gain correction does not remove off-bin scalloping or spectral leakage.",
    ]
    if config.window != "rectangular":
        notes.append(
            "Integrated PSD equals window-weighted mean square, not generally unwindowed RMS²."
        )
    if np.any(processed != 0) and not np.any(processed * window):
        notes.append("The window masks all nonzero samples; consider a rectangular window.")
    if config.detrend == "none" and config.window != "rectangular":
        notes.append("A retained mean leaks into low-frequency bins through the taper.")
    band_rms = None
    if config.band is not None:
        selected = (frequencies >= config.band.lower_hz) & (frequencies <= config.band.upper_hz)
        band_rms = float(np.sqrt(np.sum(psd[selected]) * metadata.frequency_resolution_hz))
        if not np.any(selected):
            notes.append("No FFT bin centers lie in the requested RMS band.")
    # Relative amplitude floor plus an original-record roundoff floor: no fixed SI cutoff.
    floor = max(
        float(np.max(peak_amplitude)) * 1e-12, raw_metrics.peak_absolute * 64 * np.finfo(float).eps
    )
    dominant_index = int(np.argmax(psd[1:])) + 1
    dominant = (
        float(frequencies[dominant_index]) if peak_amplitude[dominant_index] > floor else None
    )
    candidates = [int(i) for i in signal.find_peaks(psd)[0] if i > 0 and peak_amplitude[i] > floor]
    if peak_amplitude[-1] > floor and psd[-1] > psd[-2]:
        candidates.append(len(frequencies) - 1)
    if processed_metrics.standard_deviation <= raw_metrics.peak_absolute * 64 * np.finfo(float).eps:
        dominant, candidates = None, []
    candidates.sort(key=lambda i: float(psd[i]), reverse=True)
    peaks = tuple(
        SpectralPeak(
            i,
            float(frequencies[i]),
            float(peak_amplitude[i]),
            float(psd[i]),
            i == len(frequencies) - 1,
        )
        for i in candidates[: config.max_peaks]
    )
    return SpectrumResult(
        metadata,
        series.unit,
        config,
        processed,
        frequencies,
        transform,
        peak_amplitude,
        rms_amplitude,
        power,
        psd,
        coherent_gain,
        power_gain,
        enbw_bins,
        enbw_hz,
        raw_metrics,
        processed_metrics,
        weighted_ms,
        integrated,
        band_rms,
        dominant,
        peaks,
        tuple(notes),
        signal_fingerprint(series),
    )
