"""Real FEM pulse-response case shared by reproducible examples and the workbench."""

from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.mesh import cantilever
from vibra.core.models import FrameModel
from vibra.dynamics.forcing import PulseForce
from vibra.solvers.transient import TimeGrid, TransientConfig, TransientResult, solve_transient
from vibra.verification.benchmarks import steel_case


def cantilever_signal_case() -> tuple[FrameModel, TransientConfig, TransientResult]:
    g, material, rectangle = steel_case()
    model = cantilever(g, material, rectangle.section(), 16, tip_force=0)
    config = TransientConfig(
        grid=TimeGrid(duration=3, time_step=0.0005),
        damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
        loads=(PulseForce(node=16, amplitude=1, end_time=0.04),),
        responses=(ResponseDOF(node=16),),
    )
    return model, config, solve_transient(model, config)
