"""Bounded complete spectral reports; no spectral-bin decimation or hidden resampling."""

from vibra.io.reports import engineering_report
from vibra.signals.analysis import SpectrumResult, signal_fingerprint
from vibra.signals.fem import compare_modal_peaks
from vibra.signals.models import SignalSeries

MAX_SIGNAL_REPORT_BYTES = 25_000_000


def signal_report(
    series: SignalSeries, result: SpectrumResult, natural_frequencies_hz: tuple[float, ...] = ()
) -> str:
    if (
        len(series.values) != result.sampling.samples
        or series.unit != result.unit
        or signal_fingerprint(series) != result.source_fingerprint
    ):
        raise ValueError("Signal report inputs do not match result metadata.")
    report = engineering_report(
        "Vibration signal diagnostics",
        {"signal": series, "fft_configuration": result.config},
        {
            "spectrum": result,
            "natural_reference_frequencies_hz": natural_frequencies_hz,
            "modal_frequency_comparisons": compare_modal_peaks(result, natural_frequencies_hz),
            "normalization": {
                "fft": "Unnormalized real FFT of processed signal times periodic window, NFFT=N",
                "peak_amplitude": "q*abs(FFT)/sum(window)",
                "rms_amplitude": "sqrt(q)*abs(FFT)/sum(window)",
                "power_spectrum": "q*abs(FFT)^2/sum(window)^2 = RMS_bin^2 = PSD*ENBW_Hz",
                "psd": "q*abs(FFT)^2/(fs*sum(window^2))",
                "one_sided_weights": "q=2 for conjugate-paired bins; q=1 for DC/even-N Nyquist",
                "integrated_psd": "sum(PSD)*df = sum(processed^2*window^2)/sum(window^2)",
                "detrend": result.config.detrend,
                "window": result.config.window,
            },
            "units": {
                "time": "s",
                "frequency": "Hz",
                "amplitude": series.unit,
                "power": f"({series.unit})^2",
                "psd": f"({series.unit})^2/Hz",
            },
            "verification_metadata": {
                "independent_benchmarks": "vibra-verify-signals; analytical numerical verification",
                "experimental_validation": False,
                "measured_modal_identification": False,
                "ansys_correlation": False,
                "resampling": "none",
            },
            "limitations": [
                "Uniform real-valued scalar SI signals only; no resampling or alias recovery",
                "Single-record modified periodogram; no Welch averaging/confidence intervals",
                "Resolution fs/N; sample span (N-1)/fs differs from DFT duration N/fs",
                "Coherent gain is exact for isolated coherent tones away from endpoint overlap",
                "Off-bin leakage yields approximate sampled amplitudes and peak locations",
                "Integrated tapered PSD is window-weighted mean square, not generally raw RMS^2",
                "Summing coherent-gain bin powers overcounts taper leakage; use integrated PSD",
                "Band RMS includes whole bin centers in the inclusive requested band",
                "Peak/reference proximity does not establish resonance, modal identity or health",
                "FEM acceleration can expose unresolved modes; check time/mesh/record convergence",
                "Complete samples and bins retained; bounded to 131072 samples and 25 MB JSON",
            ],
        },
    )
    if len(report.encode()) > MAX_SIGNAL_REPORT_BYTES:
        raise ValueError(
            "Signal report exceeds 25 MB; explicitly shorten the record or provenance."
        )
    return report
