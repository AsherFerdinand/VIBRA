"""Independent amplitude, window, PSD, sampling and engineering-unit checks."""

import json

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError
from scipy.signal import periodogram

from vibra.io.signal_csv import import_signal_csv
from vibra.io.signal_report import signal_report
from vibra.signals.analysis import analyze_signal
from vibra.signals.models import FrequencyBand, SignalError, SignalSeries, SpectrumConfig
from vibra.verification.signal_benchmarks import signal_verification_report


def series(
    values: np.ndarray[tuple[int, ...], np.dtype[np.float64]], fs: float = 1024
) -> SignalSeries:
    return SignalSeries(
        time=tuple(float(n / fs) for n in range(len(values))), values=tuple(values), unit="m/s^2"
    )


@pytest.mark.parametrize("window", ["rectangular", "hann", "hamming"])
def test_coherent_tone_peak_rms_power_and_sampling(window: str) -> None:
    n = np.arange(1024)
    source = series(2.5 * np.cos(2 * np.pi * 100 * n / 1024 + 0.37))
    result = analyze_signal(
        source, SpectrumConfig.model_validate({"window": window, "detrend": "none"})
    )
    assert_allclose(result.peak_amplitude[100], 2.5, atol=1e-12)
    assert_allclose(result.rms_amplitude[100], 2.5 / np.sqrt(2), atol=1e-12)
    assert_allclose(result.power_spectrum[100], 2.5**2 / 2, atol=1e-12)
    assert_allclose(np.angle(result.fft_complex[100]), 0.37, atol=1e-12)
    assert_allclose(result.psd * result.enbw_hz, result.power_spectrum, atol=1e-12)
    assert result.dominant_frequency_hz == 100
    assert result.sampling.frequency_resolution_hz == 1
    assert result.sampling.sampling_frequency_hz == 1024
    assert result.sampling.sample_span_s == 1023 / 1024
    assert result.sampling.dft_duration_s == 1
    assert result.sampling.nyquist_hz == 512


@pytest.mark.parametrize("count", [1023, 1024])
@pytest.mark.parametrize("window", ["rectangular", "hann", "hamming"])
def test_psd_parseval_against_independent_window_equations(count: int, window: str) -> None:
    raw = np.random.default_rng(19).normal(0, 1, count) + 0.1 * np.arange(count)
    result = analyze_signal(
        series(raw), SpectrumConfig.model_validate({"window": window, "detrend": "mean"})
    )
    n = np.arange(count)
    weights = (
        np.ones(count)
        if window == "rectangular"
        else (
            0.5 - 0.5 * np.cos(2 * np.pi * n / count)
            if window == "hann"
            else 0.54 - 0.46 * np.cos(2 * np.pi * n / count)
        )
    )
    reference = float(np.sum((raw - np.mean(raw)) ** 2 * weights**2) / np.sum(weights**2))
    assert_allclose(result.integrated_psd_mean_square, reference, rtol=1e-12)
    frequencies, psd = periodogram(
        raw - np.mean(raw), fs=1024, window=weights, detrend=False, scaling="density"
    )
    assert_allclose(result.frequencies_hz, frequencies)
    assert_allclose(result.psd, psd, rtol=1e-11, atol=1e-14)


def test_dc_nyquist_and_odd_last_bin() -> None:
    n = np.arange(1024)
    for values, bin_index, amplitude in [(np.full(1024, 3.0), 0, 3), (2 * (-1.0) ** n, 512, 2)]:
        result = analyze_signal(
            series(values), SpectrumConfig(window="rectangular", detrend="none")
        )
        assert_allclose(result.peak_amplitude[bin_index], amplitude, atol=1e-13)
        assert_allclose(result.rms_amplitude[bin_index], amplitude, atol=1e-13)
        assert_allclose(result.integrated_psd_mean_square, amplitude**2, atol=1e-12)
    n = np.arange(1023)
    odd = analyze_signal(
        series(2 * np.cos(2 * np.pi * 511 * n / 1023)),
        SpectrumConfig(window="rectangular", detrend="none"),
    )
    assert_allclose(odd.peak_amplitude[-1], 2, atol=1e-11)
    assert_allclose(odd.rms_amplitude[-1], np.sqrt(2), atol=1e-11)
    assert odd.frequencies_hz[-1] < odd.sampling.nyquist_hz


def test_metrics_mixed_tones_band_rms_and_dc_removal() -> None:
    n = np.arange(1024)
    raw = 3 + 2 * np.cos(2 * np.pi * 64 * n / 1024) + 0.5 * np.cos(2 * np.pi * 200 * n / 1024)
    config = SpectrumConfig(
        window="rectangular", detrend="mean", band=FrequencyBand(lower_hz=60, upper_hz=70)
    )
    result = analyze_signal(series(raw), config)
    assert_allclose(result.raw_metrics.mean, 3, atol=1e-13)
    assert_allclose(result.raw_metrics.rms, np.sqrt(9 + 2 + 0.125), atol=1e-12)
    assert_allclose(result.raw_metrics.standard_deviation, np.sqrt(2.125), atol=1e-12)
    assert_allclose(result.processed_metrics.rms, np.sqrt(2.125), atol=1e-12)
    assert result.band_limited_rms is not None
    assert_allclose(result.band_limited_rms, np.sqrt(2), atol=1e-12)
    assert_allclose(result.raw_metrics.peak_absolute, 5.5, atol=1e-12)
    assert result.raw_metrics.crest_factor is not None
    assert_allclose(result.raw_metrics.crest_factor, 5.5 / np.sqrt(11.125), atol=1e-12)
    assert result.peaks[0].frequency_hz == 64
    assert result.peaks[1].frequency_hz == 200
    assert result.peak_amplitude[0] < 1e-12


def test_linear_detrending_and_zero_undefined_crest() -> None:
    n = np.arange(1024, dtype=float)
    result = analyze_signal(series(3 + 0.1 * n), SpectrumConfig(detrend="linear"))
    assert_allclose(result.processed_values, 0, atol=1e-12)
    assert result.dominant_frequency_hz is None
    zero = analyze_signal(series(np.zeros(1024)))
    assert zero.processed_metrics.crest_factor is None
    assert zero.dominant_frequency_hz is None and zero.peaks == ()
    assert_allclose(zero.psd, 0, atol=0)
    constant = analyze_signal(series(np.full(1024, 2.0)), SpectrumConfig(detrend="none"))
    assert constant.dominant_frequency_hz is None
    impulse = np.zeros(1024)
    impulse[0] = 1
    masked = analyze_signal(series(impulse), SpectrumConfig(detrend="none", window="hann"))
    assert masked.integrated_psd_mean_square == 0
    assert any("masks" in note for note in masked.numerical_warnings)


def test_noise_leakage_and_analytical_report() -> None:
    report = signal_verification_report()
    assert report["passed"]
    assert not report["experimental_validation"]
    assert report["off_bin_results"][1]["largest_sampled_amplitude"] < 0.86


@pytest.mark.parametrize(
    "data",
    [
        b"time,signal\n0,1\n.1,\n.2,2\n.3,3",
        b"time,signal\n0,1\n.1,nan\n.2,2\n.3,3",
        b"time,signal\n0,1\n.1,inf\n.2,2\n.3,3",
        b"time,signal\n0,1\n.1,2\n.1,3\n.3,4",
        b"time,signal\n0,1\n.1,2\n.21,3\n.3,4",
        b"time,signal\n0,1\n.1,2\n.2,3\n",
        b"time,time\n0,1",
        b"time,signal\n0,bad",
        b"time,signal\n0,1,2",
        b"\xff\xfe",
    ],
)
def test_invalid_csv(data: bytes) -> None:
    with pytest.raises((SignalError, ValidationError)):
        import_signal_csv(data, unit="m")


def test_csv_units_columns_roundtrip_and_limits() -> None:
    raw = b"elapsed,value,other\n1,1,0\n1.1,-1,0\n1.2,1,0\n1.3,-1,0\n"
    source = import_signal_csv(raw, unit="m/s", time_column="elapsed", signal_column="value")
    assert source.unit == "m/s"
    assert source.provenance.kind == "csv"
    assert_allclose(analyze_signal(source).sampling.sampling_frequency_hz, 10)
    with pytest.raises(SignalError):
        import_signal_csv(b"x" * (10 * 1024 * 1024 + 1), unit="m")
    with pytest.raises(SignalError):
        import_signal_csv(raw, unit="m", time_column="absent")


@pytest.mark.parametrize(
    "values,time",
    [
        ((1, 2, 3), (0, 1, 2)),
        ((1, 2, 3, 4), (0, 1, 2, 2)),
        ((1, 2, 3, 4), (0, 1, 2, 3.01)),
        ((1, 2, 3, 4), (3, 2, 1, 0)),
        ((1, 2, float("nan"), 4), (0, 1, 2, 3)),
    ],
)
def test_invalid_sampling(values: tuple[float, ...], time: tuple[float, ...]) -> None:
    with pytest.raises((SignalError, ValidationError)):
        SignalSeries(time=time, values=values, unit="m")


def test_band_validation_and_complete_json() -> None:
    source = series(np.cos(2 * np.pi * 100 * np.arange(1024) / 1024))
    result = analyze_signal(source)
    report = json.loads(signal_report(source, result))
    assert report["inputs"]["signal"]["unit"] == "m/s^2"
    assert report["results"]["units"]["psd"] == "(m/s^2)^2/Hz"
    assert report["results"]["verification_metadata"]["resampling"] == "none"
    assert report["results"]["modal_frequency_comparisons"] == []
    assert_allclose(report["results"]["spectrum"]["peak_amplitude"], result.peak_amplitude)
    with pytest.raises(SignalError):
        analyze_signal(source, SpectrumConfig(band=FrequencyBand(lower_hz=10, upper_hz=600)))


def test_cumulative_sampling_drift_is_rejected() -> None:
    dt = np.r_[np.full(64, 1 + 0.4e-6), np.full(63, 1 - 0.4e-6)]
    time = np.r_[0, np.cumsum(dt)]
    with pytest.raises((SignalError, ValidationError), match="Nonuniform"):
        SignalSeries(time=tuple(time), values=tuple(np.zeros(128)), unit="m")


def test_fem_extraction_units_provenance_and_modal_comparisons() -> None:
    from vibra.core.models import DOF
    from vibra.signals.fem import compare_modal_peaks, extract_transient_signal, natural_references
    from vibra.verification.signal_demo import cantilever_signal_case

    model, config, transient = cantilever_signal_case()
    source = extract_transient_signal(
        model, config, transient, 16, quantity="acceleration", start_index=200
    )
    result = analyze_signal(source)
    assert source.unit == "m/s^2"
    assert source.provenance.kind == "fem"
    assert source.provenance.details["resampling"] == "none"
    assert len(source.values) == len(transient.time) - 200
    assert_allclose(source.values, transient.acceleration[200:, -2], atol=0)
    modal = natural_references(model)
    assert result.dominant_frequency_hz is not None
    assert abs(result.dominant_frequency_hz - modal[0]) < result.sampling.frequency_resolution_hz
    assert compare_modal_peaks(result, modal)[0].reference_only
    rotation = extract_transient_signal(
        model, config, transient, 16, dof=DOF.RZ, quantity="velocity"
    )
    assert rotation.unit == "rad/s"
    report = json.loads(signal_report(source, result, modal))
    assert report["results"]["modal_frequency_comparisons"]
    with pytest.raises(SignalError):
        extract_transient_signal(model, config, transient, 99)
    with pytest.raises(SignalError):
        extract_transient_signal(model, config, transient, 16, start_index=6000)


@pytest.mark.parametrize("window", ["rectangular", "hann", "hamming"])
def test_dominant_nyquist_uses_power_not_endpoint_biased_peak_amplitude(window: str) -> None:
    source = series(np.asarray(2 * (-1.0) ** np.arange(1024), dtype=np.float64))
    result = analyze_signal(
        source, SpectrumConfig.model_validate({"window": window, "detrend": "none"})
    )
    assert result.dominant_frequency_hz == 512
    assert_allclose(result.raw_metrics.rms, 2, atol=1e-12)
    assert_allclose(result.raw_metrics.peak_to_peak, 4, atol=1e-12)
    assert result.raw_metrics.crest_factor == 1
    assert result.peaks[0].frequency_hz == 512
    assert result.peaks[0].at_frequency_boundary
    assert_allclose(result.peak_amplitude[-1], 2, atol=1e-12)
    assert_allclose(result.rms_amplitude[-1], 2, atol=1e-12)


def test_report_rejects_same_size_different_source() -> None:
    source = series(np.cos(2 * np.pi * 100 * np.arange(1024) / 1024))
    result = analyze_signal(source)
    other = series(np.cos(2 * np.pi * 200 * np.arange(1024) / 1024))
    with pytest.raises(ValueError, match="match"):
        signal_report(other, result)
