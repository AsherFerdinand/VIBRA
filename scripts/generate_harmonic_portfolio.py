"""Generate authentic FEM/continuum harmonic figures and verification metadata."""

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/vibra-cache")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from vibra.core.mesh import cantilever  # noqa: E402
from vibra.solvers.harmonic import (  # noqa: E402
    Damping,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.verification.benchmarks import steel_case  # noqa: E402
from vibra.verification.harmonic_analytical import continuum_cantilever_compliance  # noqa: E402
from vibra.verification.harmonic_benchmarks import harmonic_verification_report  # noqa: E402


def main() -> None:
    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "vibra-harmonic-0.2"})
    g, m, r = steel_case()
    model = cantilever(g, m, r.section(), 16, tip_force=0)
    frequencies = FrequencySweep(start_hz=0, stop_hz=60, points=1001).frequencies()
    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, layout="constrained")
    for damping in (Damping(), Damping(kind="rayleigh", alpha=2, beta=2e-5)):
        config = HarmonicConfig(
            frequencies_hz=frequencies,
            damping=damping,
            loads=(HarmonicLoad(node=16, amplitude=1),),
            responses=(ResponseDOF(node=16),),
        )
        result = solve_harmonic(model, config)
        axes[0].semilogy(
            frequencies, result.response_amplitude[:, 0] * 1000, label=f"FEM: {damping.kind}"
        )
        axes[1].plot(
            frequencies, np.rad2deg(result.phase_radians[:, 0]), label=f"FEM: {damping.kind}"
        )
        if damping.kind == "rayleigh":
            continuum = continuum_cantilever_compliance(
                g, m, r.section(), frequencies, damping.alpha, damping.beta
            )
            sampled = np.arange(0, len(frequencies), 25)
            axes[0].semilogy(
                np.asarray(frequencies)[sampled],
                np.abs(continuum[sampled]) * 1000,
                ".",
                color="black",
                label="Continuum: Rayleigh",
            )
            axes[1].plot(
                np.asarray(frequencies)[sampled],
                np.rad2deg(np.angle(continuum[sampled])),
                ".",
                color="black",
                label="Continuum: Rayleigh",
            )
            for axis in axes:
                axis.axvline(
                    result.natural_frequencies_hz[0],
                    color="#8b959f",
                    linestyle=":",
                    label="First undamped natural",
                )
    axes[0].set(
        ylabel="Tip amplitude [mm]",
        title="Steel cantilever · 1 N peak transverse tip force · 16 elements",
    )
    axes[1].set(xlabel="Excitation frequency [Hz]", ylabel="Phase [deg]", yticks=[-180, -90, 0])
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(loc="upper right")
    figure.suptitle(
        "Finite frequency samples: undamped resonance is unbounded at the pole", fontsize=10
    )
    figure.savefig(output / "harmonic-response.svg", metadata={"Date": None})
    figure.savefig(output / "harmonic-response.png", dpi=160)
    plt.close(figure)
    svg = output / "harmonic-response.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    (output / "harmonic-verification.json").write_text(
        json.dumps(harmonic_verification_report(), indent=2, allow_nan=False) + "\n"
    )
    print(f"Generated FEM/continuum harmonic plots and verification report: {output}")


if __name__ == "__main__":
    main()
