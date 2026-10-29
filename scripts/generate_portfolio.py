"""Generate compact, shareable figures from the real solvers (dev dependencies)."""

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/vibra-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/vibra-cache")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import NullLocator, ScalarFormatter  # noqa: E402

from vibra.core.mesh import cantilever  # noqa: E402
from vibra.dynamics.sdof import SDOFConfig, solve_sdof  # noqa: E402
from vibra.solvers.static import solve_static  # noqa: E402
from vibra.verification.benchmarks import (  # noqa: E402
    convergence_study,
    steel_case,
    verification_report,
)


def main() -> None:
    import json

    output = Path("docs/results")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 10,
            "svg.hashsalt": "vibra-0.1",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    rows = convergence_study()
    figure, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for mode in range(3):
        axes[0].loglog(
            [row["elements"] for row in rows],
            [100 * row["relative_frequency_errors"][mode] for row in rows],
            "o-",
            label=f"Bending mode {mode + 1}",
        )
    axes[0].set(
        xlabel="Beam elements", ylabel="Frequency error [%]", title="Steel cantilever convergence"
    )
    axes[0].set_xticks([2, 4, 8, 16, 32])
    axes[0].xaxis.set_major_formatter(ScalarFormatter())
    axes[0].xaxis.set_minor_locator(NullLocator())
    axes[0].legend()
    axes[0].grid(alpha=0.2)
    geometry, material, rectangle = steel_case()
    model = cantilever(geometry, material, rectangle.section(), 16)
    static = solve_static(model)
    x = np.array([node.x for node in model.nodes])
    exact = (
        -100
        * x**2
        * (3 * geometry.length - x)
        / (6 * material.young_modulus * rectangle.section().second_moment)
    )
    axes[1].plot(x, exact * 1000, color="#142c3e", label="Analytical")
    axes[1].plot(x, static.displacement[:, 1] * 1000, "o", color="#007f88", label="FEM nodes")
    axes[1].set(
        xlabel="Beam coordinate [m]",
        ylabel="Physical displacement [mm]",
        title="100 N downward tip load",
    )
    axes[1].legend()
    figure.savefig(output / "beam-verification.svg", metadata={"Date": None})
    figure.savefig(output / "beam-verification.png", dpi=160)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(9, 4), layout="constrained")
    for damping in (0.0, 0.8, 4.0):
        config = SDOFConfig(mass=2, stiffness=200, damping=damping)
        response = solve_sdof(config)
        axis.plot(response.time, response.displacement * 1000, label=f"c = {damping:g} N s/m")
    axis.set(
        xlabel="Time [s]",
        ylabel="Displacement [mm]",
        title="Free SDOF vibration: m = 2 kg, k = 200 N/m",
    )
    axis.legend()
    figure.savefig(output / "sdof-free.svg", metadata={"Date": None})
    figure.savefig(output / "sdof-free.png", dpi=160)
    plt.close(figure)
    (output / "verification.json").write_text(
        json.dumps(verification_report(), indent=2, allow_nan=False) + "\n"
    )
    for svg in output.glob("*.svg"):
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    print(f"Generated solver figures and analytical verification report: {output}")


if __name__ == "__main__":
    main()
