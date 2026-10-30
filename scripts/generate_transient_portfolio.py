"""Regenerate transient engineering figures and the independent verification report."""

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/vibra-cache")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from vibra.core.dynamic_models import Damping, ResponseDOF  # noqa: E402
from vibra.core.mesh import cantilever  # noqa: E402
from vibra.dynamics.forcing import PulseForce  # noqa: E402
from vibra.solvers.transient import TimeGrid, TransientConfig, solve_transient  # noqa: E402
from vibra.verification.benchmarks import steel_case  # noqa: E402
from vibra.verification.transient_benchmarks import transient_verification_report  # noqa: E402


def main() -> None:
    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "vibra-transient-0.3"})
    g, material, rectangle = steel_case()
    model = cantilever(g, material, rectangle.section(), 16, tip_force=0)
    case = TransientConfig(
        grid=TimeGrid(duration=1, time_step=0.0005),
        damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
        loads=(PulseForce(node=16, amplitude=1, end_time=0.04),),
        responses=(ResponseDOF(node=16),),
    )
    result = solve_transient(model, case)
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    axes[0, 0].plot(result.time, result.force_right[:, -2], color="#d18437")
    axes[0, 0].set(
        xlabel="Time [s]", ylabel="Tip force [N]", title="1 N half-sine pulse, duration 40 ms"
    )
    axes[0, 1].plot(result.time, result.displacement[:, -2] * 1000, color="#007f88")
    axes[0, 1].set(
        xlabel="Time [s]", ylabel="Physical tip displacement [mm]", title="Damped vibration decay"
    )
    energy = result.kinetic_energy + result.strain_energy
    for values, name in (
        (energy, "Mechanical E"),
        (result.damping_dissipation, "Dissipated D"),
        (result.external_work, "Work W"),
    ):
        axes[1, 0].plot(result.time, values, label=name)
    axes[1, 0].set(
        xlabel="Time [s]", ylabel="Energy [J]", title="Algorithm-consistent work/dissipation"
    )
    axes[1, 0].legend()
    axes[1, 1].plot(result.time, result.energy_balance_residual, color="#142c3e")
    axes[1, 1].set(
        xlabel="Time [s]",
        ylabel="E − E₀ + D − W [J]",
        title=f"Relative energy balance: {result.relative_energy_error:.2e}",
    )
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.suptitle("Steel cantilever · 16 elements · Δt = 0.5 ms · α = 2 s⁻¹, β = 20 μs")
    figure.savefig(output / "transient-response.svg", metadata={"Date": None})
    figure.savefig(output / "transient-response.png", dpi=160)
    plt.close(figure)
    svg = output / "transient-response.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    (output / "transient-verification.json").write_text(
        json.dumps(transient_verification_report(), indent=2, allow_nan=False) + "\n"
    )
    print(f"Generated actual transient FEM figures and analytical verification: {output}")


if __name__ == "__main__":
    main()
