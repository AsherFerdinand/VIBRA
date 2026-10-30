"""Real computed automotive support-rail comparison and convergence figures/reports."""

import json
import os
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/vibra-cache")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from vibra.io.nvh_report import ASSUMPTIONS, study_markdown  # noqa: E402
from vibra.studies.nvh import run_nvh_study  # noqa: E402


def main() -> None:
    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "vibra-nvh-0.5"})
    study = run_nvh_study()
    colors = ("#007f88", "#d18437")
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for color, item in zip(colors, (study.baseline, study.modified), strict=True):
        name = item.design.name
        axes[0, 0].plot(
            [n.x for n in item.model.nodes],
            item.static.displacement[:, 1] * 1000,
            "o-",
            color=color,
            label=name,
        )
        node = int(len(item.model.elements) * study.config.monitor_fraction)
        column = next(i for i, r in enumerate(item.harmonic.response_dofs) if r.node == node)
        axes[0, 1].plot(
            item.harmonic.frequencies_hz,
            item.harmonic.response_amplitude[:, column] * 1000,
            color=color,
            label=name,
        )
        axes[0, 1].axvline(item.summary.first_natural_hz, color=color, linestyle=":")
        axes[1, 0].plot(
            item.transient.time,
            item.transient.displacement[:, 3 * node + 1] * 1000,
            color=color,
            label=name,
        )
        spectrum = item.signals["acceleration"].spectrum
        visible = spectrum.frequencies_hz <= 160
        axes[1, 1].semilogy(
            spectrum.frequencies_hz[visible], spectrum.psd[visible], color=color, label=name
        )
        axes[1, 1].axvline(item.summary.first_natural_hz, color=color, linestyle=":")
    axes[0, 0].set(
        xlabel="Rail x [m]",
        ylabel="Static nodal displacement [mm]",
        title="200 N downward tip force",
    )
    axes[0, 1].axvline(
        study.config.operating_frequency_hz,
        color="gray",
        linestyle="--",
        label="Operating order: 60 Hz",
    )
    axes[0, 1].set(
        xlabel="Excitation frequency [Hz]",
        ylabel="Harmonic peak amplitude [mm]",
        title="Assumed 2 N peak periodic force",
    )
    axes[1, 0].set(
        xlabel="Time [s]",
        ylabel="Dynamic perturbation [mm]",
        title="20 N, 10 ms half-sine disturbance",
    )
    axes[1, 1].set(
        xlabel="Frequency [Hz]",
        ylabel="Acceleration PSD [(m/s²)²/Hz]",
        title="Post-pulse Hann PSD; dotted modal references",
    )
    for axis in axes.flat:
        axis.legend()
        axis.grid(alpha=0.2)
    figure.suptitle("Equivalent motor-interface rails · bare rail mass only · illustrative forces")
    figure.savefig(output / "nvh-comparison.svg", metadata={"Date": None})
    figure.savefig(output / "nvh-comparison.png", dpi=160)
    plt.close(figure)
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for i, convergence in enumerate(study.convergence):
        for j, (kind, rows) in enumerate((("time", convergence.time), ("mesh", convergence.mesh))):
            axis = axes[i, j]
            for field, label in (
                ("relative_difference_from_finest", "Displacement"),
                ("relative_velocity_difference_from_finest", "Velocity"),
                ("relative_acceleration_difference_from_finest", "Acceleration"),
            ):
                nonzero = [r for r in rows if getattr(r, field) > 0]
                x = [r.time_step_s * 1e6 if kind == "time" else r.elements for r in nonzero]
                axis.loglog(x, [getattr(r, field) for r in nonzero], "o-", label=label)
            axis.set(
                xlabel="Step [μs]" if kind == "time" else "Elements",
                ylabel="Peak-normalized history difference",
                title=convergence.design_name + " · " + kind,
            )
            axis.legend()
            axis.grid(alpha=0.2)
    figure.suptitle(
        "Computed fine references; exact-solution errors are not claimed (zero rows omitted)"
    )
    figure.savefig(output / "nvh-convergence.svg", metadata={"Date": None})
    figure.savefig(output / "nvh-convergence.png", dpi=160)
    plt.close(figure)
    for name in ("nvh-comparison", "nvh-convergence"):
        path = output / f"{name}.svg"
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    (output / "nvh-study.md").write_text(study_markdown(study))
    summary = {
        "config": study.config.model_dump(mode="json"),
        "assumptions": ASSUMPTIONS,
        "baseline": asdict(study.baseline.summary),
        "modified": asdict(study.modified.summary),
        "convergence": [asdict(c) for c in study.convergence],
        "verification": study.verification_checks,
        "experimental_validation": False,
        "ansys_correlation": False,
    }
    (output / "nvh-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print("Generated real study figures, Markdown and compact JSON summary:", output)


if __name__ == "__main__":
    main()
