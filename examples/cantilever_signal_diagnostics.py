"""Pulse FEM → full sampled tip histories → FFT/PSD → independent modal references."""

import json
from pathlib import Path

from vibra.io.signal_report import signal_report
from vibra.signals.analysis import analyze_signal
from vibra.signals.fem import (
    Quantity,
    compare_modal_peaks,
    extract_transient_signal,
    natural_references,
)
from vibra.signals.models import SpectrumConfig
from vibra.verification.signal_demo import cantilever_signal_case
from vibra.visualization.signals import signal_time_plot, spectrum_plots


def main() -> None:
    output = Path("artifacts/cantilever-signal-diagnostics")
    output.mkdir(parents=True, exist_ok=True)
    model, config, transient = cantilever_signal_case()
    naturals = natural_references(model)
    quantities: tuple[Quantity, ...] = ("displacement", "acceleration")
    summary = []
    for quantity in quantities:
        series = extract_transient_signal(
            model, config, transient, node=16, quantity=quantity, start_index=200
        )
        result = analyze_signal(series, SpectrumConfig(window="hann", detrend="mean"))
        (output / f"{quantity}-report.json").write_text(
            signal_report(series, result, naturals) + "\n"
        )
        signal_time_plot(series, result).write_html(
            output / f"{quantity}-time.html", include_plotlyjs=True
        )
        amplitude, psd = spectrum_plots(result, naturals, upper_hz=350, logarithmic=True)
        amplitude.write_html(output / f"{quantity}-amplitude.html", include_plotlyjs=True)
        psd.write_html(output / f"{quantity}-psd.html", include_plotlyjs=True)
        assert result.dominant_frequency_hz is not None
        error = abs(result.dominant_frequency_hz - naturals[0])
        if error > result.sampling.frequency_resolution_hz:
            raise RuntimeError(
                "Demonstration dominant bin is not within one bin of its first modal reference."
            )
        summary.append(
            {
                "quantity": quantity,
                "unit": series.unit,
                "sampling": result.sampling.__dict__,
                "dominant_frequency_hz": result.dominant_frequency_hz,
                "first_natural_reference_hz": naturals[0],
                "difference_hz": error,
                "reference_only": True,
                "comparison": [c.__dict__ for c in compare_modal_peaks(result, naturals)],
            }
        )
        print(
            f"{quantity}: fs={result.sampling.sampling_frequency_hz:g} Hz, "
            f"df={result.sampling.frequency_resolution_hz:.7g} Hz, "
            f"dominant={result.dominant_frequency_hz:.7g} Hz, "
            f"first natural={naturals[0]:.7g} Hz"
        )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Actual simulation reports and spectral plots: {output}")


if __name__ == "__main__":
    main()
