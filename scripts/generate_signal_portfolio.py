"""Actual FEM signal plots, leakage illustration and independent verification outputs."""

import json
import os
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/vibra-cache")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from vibra.signals.analysis import analyze_signal  # noqa: E402
from vibra.signals.fem import Quantity, extract_transient_signal, natural_references  # noqa: E402
from vibra.signals.models import SignalSeries, SpectrumConfig  # noqa: E402
from vibra.verification.signal_benchmarks import signal_verification_report  # noqa: E402
from vibra.verification.signal_demo import cantilever_signal_case  # noqa: E402


def main() -> None:
    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "vibra-signals-0.4"})
    model, config, transient = cantilever_signal_case()
    references = natural_references(model)
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    quantities: tuple[Quantity, ...] = ("displacement", "acceleration")
    rows = []
    for row, quantity in enumerate(quantities):
        source = extract_transient_signal(
            model, config, transient, 16, quantity=quantity, start_index=200
        )
        result = analyze_signal(source)
        factor, unit = (1000.0, "mm") if quantity == "displacement" else (1.0, "m/s²")
        axes[row, 0].plot(source.time, result.processed_values * factor, color="#007f88")
        axes[row, 0].set(
            xlabel="Time [s]",
            ylabel=f"{quantity.title()} [{unit}]",
            title="Post-pulse processed FEM record",
        )
        selected = result.frequencies_hz <= 350
        values = result.peak_amplitude * factor if row == 0 else result.psd
        axes[row, 1].semilogy(result.frequencies_hz[selected], values[selected], color="#142c3e")
        for index, frequency in enumerate(references[:3]):
            axes[row, 1].axvline(
                frequency,
                linestyle=":",
                color="#d18437",
                label="Independent modal references" if index == 0 else None,
            )
        axes[row, 1].set(
            xlabel="Frequency [Hz]",
            ylabel="Peak-equivalent amplitude [mm]" if row == 0 else "PSD [(m/s²)²/Hz]",
            title=f"Hann spectrum · Δf = {result.sampling.frequency_resolution_hz:.4g} Hz",
        )
        axes[row, 1].legend()
        rows.append(
            {
                "quantity": quantity,
                "unit": source.unit,
                "sampling": asdict(result.sampling),
                "dominant_frequency_hz": result.dominant_frequency_hz,
                "independent_natural_references_hz": references,
                "damping": config.damping.model_dump(),
                "transient_energy_error": transient.relative_energy_error,
                "window": result.config.window,
                "detrend": result.config.detrend,
                "modal_identification_claimed": False,
            }
        )
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.suptitle(
        "Actual cantilever pulse response · 2 kHz sampling · "
        "spectral peaks are not modal identification"
    )
    figure.savefig(output / "signal-diagnostics.svg", metadata={"Date": None})
    figure.savefig(output / "signal-diagnostics.png", dpi=160)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(9, 4), layout="constrained")
    time = np.arange(4096) / 4096
    off_bin = SignalSeries(
        time=tuple(time), values=tuple(np.cos(2 * np.pi * 100.5 * time)), unit="m"
    )
    for window in ("rectangular", "hann", "hamming"):
        spectrum = analyze_signal(
            off_bin, SpectrumConfig.model_validate({"window": window, "detrend": "none"})
        )
        selected = (spectrum.frequencies_hz >= 85) & (spectrum.frequencies_hz <= 116)
        axis.semilogy(
            spectrum.frequencies_hz[selected], spectrum.peak_amplitude[selected], "o-", label=window
        )
    axis.axvline(100.5, linestyle=":", color="gray", label="True tone: 100.5 Hz, 1 m peak")
    axis.set(
        xlabel="Frequency [Hz]",
        ylabel="Coherent-gain-corrected sampled amplitude [m]",
        title="Off-bin leakage and scalloping; no window restores a unit bin peak",
    )
    axis.legend()
    figure.savefig(output / "signal-leakage.svg", metadata={"Date": None})
    figure.savefig(output / "signal-leakage.png", dpi=160)
    plt.close(figure)
    for name in ("signal-diagnostics", "signal-leakage"):
        svg = output / f"{name}.svg"
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    (output / "signal-verification.json").write_text(
        json.dumps(signal_verification_report(), indent=2, allow_nan=False) + "\n"
    )
    (output / "signal-demo.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    print(f"Generated actual FEM spectra, leakage figures and verification outputs: {output}")


if __name__ == "__main__":
    main()
