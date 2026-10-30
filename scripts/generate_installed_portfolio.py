"""Generate authentic installed-system figures and compact checked engineering reports."""

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-mpl")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from vibra.io.installed_report import ASSUMPTIONS, installed_conclusion, installed_markdown
from vibra.studies.installed import InstalledConfig, investigate, run_installed_study
from vibra.verification.installed_benchmarks import verification_report


def main() -> None:
    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"svg.hashsalt": "vibra-installed-0.6", "font.size": 10})
    study = run_installed_study()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    colors = ("#127a8a", "#de8b26", "#9b458e")
    for i, (case, color) in enumerate(zip(study.cases, colors, strict=True)):
        h, t = case.harmonic, case.transient
        axes[0, 0].bar(i, case.modal.frequencies_hz[0], color=color, label=case.topology)
        axes[0, 1].semilogy(
            h.frequencies_hz,
            abs(h.displacement[:, 3 * study.config.elements + 1]) * 1e3,
            color=color,
            label=case.topology,
        )
        axes[1, 0].semilogy(
            h.frequencies_hz,
            abs(case.harmonic_root_force_N) / study.config.harmonic_force_N,
            color=color,
            label=case.topology,
        )
        axes[1, 1].plot(
            t.time,
            t.displacement[:, 3 * case.force_node + 1] * 1e3,
            color=color,
            label=case.topology,
        )
    axes[0, 0].set_xticks(range(3), ["Bare", "Rigid motor", "Isolated motor"])
    axes[0, 0].set_ylabel("First undamped natural frequency [Hz]")
    axes[0, 1].set(xlabel="Frequency [Hz]", ylabel="Rail tip peak displacement [mm]")
    axes[1, 0].set(xlabel="Frequency [Hz]", ylabel="Root force amplitude / applied force amplitude")
    axes[1, 1].set(xlabel="Time [s]", ylabel="Interface / motor COM displacement [mm]")
    for ax in axes.flat:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for ax in (axes[0, 1], axes[1, 0]):
        ax.axvline(study.config.operating_hz, color="gray", ls="--", alpha=0.7)
    fig.suptitle(
        "VIBRA 0.6 · idealized installed motor comparison\n"
        "12 kg motor, Jz=0.08 kg m² · prescribed forces · no experimental validation"
    )
    save(fig, output / "installed-comparison")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for parameter, ax in zip(("stiffness_y_N_per_m", "damping_y_Ns_per_m"), axes, strict=True):
        for factor in (0.5, 1.0, 2.0):
            config = InstalledConfig(
                **(
                    study.config.model_dump()
                    | {parameter: getattr(study.config, parameter) * factor}
                )
            )
            case = investigate(config, "isolated")
            h = case.harmonic
            ax.semilogy(
                h.frequencies_hz,
                abs(case.harmonic_transmitted_force_N) / config.harmonic_force_N,
                label=f"{factor:g} × base",
            )
        ax.axhline(1, color="gray", ls="--")
        ax.set(
            xlabel="Frequency [Hz]",
            ylabel="Force transmitted to rail / applied motor force",
            title=(
                "Total vertical mount stiffness"
                if parameter == "stiffness_y_N_per_m"
                else "Total vertical mount damping"
            ),
        )
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Relative isolator parameter sensitivity · other inputs fixed\n"
        "Resonance amplification and high-frequency isolation are different objectives"
    )
    save(fig, output / "installed-sensitivity")
    report = verification_report()
    (output / "installed-verification.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    (output / "installed-study.md").write_text(installed_markdown(study))
    summary = dict(
        inputs=study.config.model_dump(),
        assumptions=ASSUMPTIONS,
        cases={case.topology: case.summary for case in study.cases},
        convergence=study.convergence,
        checks=study.checks,
        conclusion=installed_conclusion(study),
    )
    (output / "installed-summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    if not all(study.checks.values()) or not report["all_passed"]:
        raise SystemExit(1)
    print(installed_conclusion(study))


def save(fig: Figure, path: Path) -> None:
    fig.savefig(path.with_suffix(".png"), dpi=170)
    fig.savefig(path.with_suffix(".svg"), metadata={"Date": None})
    plt.close(fig)
    svg = path.with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")


if __name__ == "__main__":
    main()
