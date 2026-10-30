"""Small-displacement, linear elastic statics: K_ff u_f = F_f."""

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy import linalg

from vibra.core.assembly import assemble, constrained_system
from vibra.core.element import Matrix
from vibra.core.errors import SolverError
from vibra.core.models import AnalysisConfig, FrameModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StaticResult:
    node_ids: tuple[int, ...]
    displacement: Matrix  # [ux(m), uy(m), rz(rad)] for each node
    reactions: Matrix  # [Fx(N), Fy(N), Mz(N m)], zero on free DOFs
    element_end_forces: dict[int, Matrix]  # local [N1,V1,M1,N2,V2,M2]
    relative_residual: float
    mount_forces_N: dict[int, float] = field(default_factory=dict)


def solve_static(model: FrameModel, config: AnalysisConfig | None = None) -> StaticResult:
    assembly = assemble(model)
    stiffness, _, scale = constrained_system(assembly, config or AnalysisConfig())
    scaled = scale[:, None] * stiffness * scale[None, :]
    force = assembly.force[assembly.free]
    try:
        reduced = scale * linalg.solve(scaled, scale * force, assume_a="pos")
    except linalg.LinAlgError as exc:
        raise SolverError("Static factorization failed.") from exc
    displacement = np.zeros_like(assembly.force)
    displacement[assembly.free] = reduced
    residual = assembly.stiffness @ displacement - assembly.force
    denominator = np.linalg.norm(stiffness, ord=np.inf) * np.linalg.norm(reduced, ord=np.inf)
    relative = float(np.linalg.norm(residual[assembly.free], ord=np.inf) / max(denominator, 1.0))
    if not np.all(np.isfinite(displacement)) or relative > 1e-9:
        raise SolverError("Static solution failed the equilibrium residual check.")
    reactions = np.zeros_like(residual)
    reactions[assembly.fixed] = residual[assembly.fixed]
    end_forces = {
        entry.element.id: entry.matrices.stiffness
        @ entry.matrices.transform
        @ displacement[entry.dofs]
        for entry in assembly.elements
    }
    logger.info("Static solve: %d nodes, residual %.3e", len(assembly.node_ids), relative)
    return StaticResult(
        assembly.node_ids,
        displacement.reshape(-1, 3),
        reactions.reshape(-1, 3),
        end_forces,
        relative,
        {
            entry.mount.id: float(entry.mount.stiffness * (entry.extension @ displacement))
            for entry in assembly.mounts
        },
    )
