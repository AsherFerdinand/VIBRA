"""Analytical FFT/PSD/window/diagnostic checks, independent of FEM."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from vibra.signals.analysis import analyze_signal
from vibra.signals.models import SignalSeries, SpectrumConfig


def signal_verification_report() -> dict[str, Any]:
    count, fs, amplitude = 4096, 4096.0, 2.5
    time = np.arange(count) / fs
    values = amplitude * np.cos(2 * np.pi * 100 * time)
    rows: list[dict[str, Any]] = []
    for window, cg, enbw in (
        ("rectangular", 1.0, 1.0),
        ("hann", 0.5, 1.5),
        ("hamming", 0.54, 1 + 0.46**2 / (2 * 0.54**2)),
    ):
        config = SpectrumConfig.model_validate({"window": window, "detrend": "none"})
        result = analyze_signal(
            SignalSeries(time=tuple(time), values=tuple(values), unit="m"), config
        )
        rows.append(
            {
                "window": window,
                "peak_amplitude_error": abs(float(result.peak_amplitude[100]) - amplitude),
                "rms_error": abs(result.raw_metrics.rms - amplitude / np.sqrt(2)),
                "coherent_gain_error": abs(result.coherent_gain - cg),
                "enbw_bins_error": abs(result.enbw_bins - enbw),
                "integrated_psd_error": abs(result.integrated_psd_mean_square - amplitude**2 / 2),
            }
        )
    off_bin = np.cos(2 * np.pi * 100.5 * time)
    leakage: list[dict[str, Any]] = []
    for window in ("rectangular", "hann"):
        result = analyze_signal(
            SignalSeries(time=tuple(time), values=tuple(off_bin), unit="m"),
            SpectrumConfig.model_validate({"window": window, "detrend": "none"}),
        )
        outside = np.abs(result.frequencies_hz - 100.5) > 4
        leakage.append(
            {
                "window": window,
                "largest_sampled_amplitude": float(result.peak_amplitude.max()),
                "power_fraction_outside_4_hz": float(result.psd[outside].sum() / result.psd.sum()),
            }
        )
    random = np.random.default_rng(2404)
    noise_time = np.arange(32768) / 4096
    noise = random.normal(0, 0.3, len(noise_time))
    noisy = analyze_signal(SignalSeries(time=tuple(noise_time), values=tuple(noise), unit="m/s^2"))
    rectangular = analyze_signal(
        SignalSeries(time=tuple(noise_time), values=tuple(noise), unit="m/s^2"),
        SpectrumConfig(window="rectangular"),
    )
    parseval_error = abs(
        rectangular.integrated_psd_mean_square - rectangular.processed_metrics.rms**2
    )
    n = np.arange(count)
    mixed_values = (
        3 + 2 * np.cos(2 * np.pi * 64 * n / count) + 0.5 * np.cos(2 * np.pi * 200 * n / count)
    )
    mixed = analyze_signal(
        SignalSeries(time=tuple(time), values=tuple(mixed_values), unit="m"),
        SpectrumConfig(window="rectangular", detrend="none"),
    )
    nyquist = analyze_signal(
        SignalSeries(time=tuple(time), values=tuple(2 * (-1.0) ** n), unit="m"),
        SpectrumConfig(window="rectangular", detrend="none"),
    )
    checks = {
        "coherent_peak_rms_window_normalization": all(
            row["peak_amplitude_error"] < 1e-11 and row["rms_error"] < 1e-12 for row in rows
        ),
        "coherent_gain_and_enbw": all(
            row["coherent_gain_error"] < 1e-13 and row["enbw_bins_error"] < 1e-13 for row in rows
        ),
        "coherent_psd_integral": all(row["integrated_psd_error"] < 1e-11 for row in rows),
        "rectangular_parseval_noise": parseval_error < 1e-12,
        "noise_rms_statistical_tolerance": abs(noisy.raw_metrics.rms / 0.3 - 1) < 0.03,
        "noise_psd_statistical_tolerance": abs(noisy.integrated_psd_mean_square / 0.09 - 1) < 0.04,
        "off_bin_window_reduces_distant_leakage": leakage[1]["power_fraction_outside_4_hz"]
        < leakage[0]["power_fraction_outside_4_hz"] / 100,
        "off_bin_scalloping_is_not_hidden": 0.63 < leakage[0]["largest_sampled_amplitude"] < 0.65
        and 0.84 < leakage[1]["largest_sampled_amplitude"] < 0.86,
        "mixed_tones_and_dc": bool(
            abs(mixed.peak_amplitude[0] - 3) < 1e-12
            and abs(mixed.peak_amplitude[64] - 2) < 1e-12
            and abs(mixed.peak_amplitude[200] - 0.5) < 1e-12
        ),
        "nyquist_peak_equals_rms": bool(
            abs(nyquist.peak_amplitude[-1] - 2) < 1e-12
            and abs(nyquist.rms_amplitude[-1] - 2) < 1e-12
            and abs(nyquist.integrated_psd_mean_square - 4) < 1e-12
        ),
    }
    return {
        "schema_version": "1.0",
        "kind": "Analytical signal-processing numerical verification",
        "experimental_validation": False,
        "ansys_correlation": False,
        "inputs": {
            "samples": count,
            "fs_hz": fs,
            "coherent_tone_hz": 100,
            "peak_amplitude": amplitude,
            "noise_seed": 2404,
        },
        "coherent_window_results": rows,
        "off_bin_results": leakage,
        "rectangular_noise_parseval_absolute_error": parseval_error,
        "noise_rms": noisy.raw_metrics.rms,
        "noise_integrated_psd": noisy.integrated_psd_mean_square,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/signal-verification.json"))
    args = parser.parse_args()
    report = signal_verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "checks": report["checks"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
