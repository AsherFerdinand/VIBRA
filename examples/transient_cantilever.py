"""Cantilever half-sine tip pulse and subsequent damped vibration decay."""

from pathlib import Path

import numpy as np

from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.mesh import cantilever
from vibra.dynamics.forcing import PulseForce
from vibra.io.transient_report import transient_report
from vibra.solvers.transient import TimeGrid, TransientConfig, solve_transient
from vibra.verification.benchmarks import steel_case
from vibra.visualization.transient import energy_history, response_history, transient_animation


def main() -> None:
    output = Path("artifacts/transient-cantilever")
    output.mkdir(parents=True, exist_ok=True)
    g, material, rectangle = steel_case()
    model = cantilever(g, material, rectangle.section(), 16, tip_force=0)
    config = TransientConfig(
        grid=TimeGrid(duration=1, time_step=0.0005),
        damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
        loads=(PulseForce(node=16, amplitude=1, end_time=0.04),),
        responses=(ResponseDOF(node=16), ResponseDOF(node=8)),
    )
    result = solve_transient(model, config)
    (output / "report.json").write_text(transient_report(model, config, result) + "\n")
    response_history(result).write_html(output / "response.html", include_plotlyjs=True)
    energy_history(result).write_html(output / "energy.html", include_plotlyjs=True)
    transient_animation(model, result, scale=100, max_frames=60).write_html(
        output / "deformation.html", include_plotlyjs=True
    )
    pulse_end_index = 80
    energy = result.kinetic_energy + result.strain_energy
    print(f"Maximum absolute tip displacement: {np.max(np.abs(result.displacement[:, -2])):.9g} m")
    print(f"E(final)/E(pulse end): {energy[-1] / energy[pulse_end_index]:.9g}")
    print(f"Relative energy-balance error: {result.relative_energy_error:.3e}")
    print(f"Reports, response, energy and actual FEM animation: {output}")


if __name__ == "__main__":
    main()
