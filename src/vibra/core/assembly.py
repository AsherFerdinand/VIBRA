"""Dense assembly with a stable node-id/UX/UY/RZ ordering and exact elimination."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import linalg

from vibra.core.element import ElementMatrices, Matrix, beam_matrices
from vibra.core.errors import UnstableModelError
from vibra.core.models import AnalysisConfig, BeamElement, FrameModel


@dataclass(frozen=True)
class AssembledElement:
    element: BeamElement
    dofs: NDArray[np.int64]
    matrices: ElementMatrices


@dataclass(frozen=True)
class Assembly:
    node_ids: tuple[int, ...]
    stiffness: Matrix
    mass: Matrix
    force: Matrix
    free: NDArray[np.int64]
    fixed: NDArray[np.int64]
    elements: tuple[AssembledElement, ...]


def assemble(model: FrameModel) -> Assembly:
    node_ids = tuple(sorted(node.id for node in model.nodes))
    offsets = {node: 3 * index for index, node in enumerate(node_ids)}
    nodes = {node.id: node for node in model.nodes}
    size = 3 * len(node_ids)
    stiffness, mass, force = np.zeros((size, size)), np.zeros((size, size)), np.zeros(size)
    assembled = []
    for element in sorted(model.elements, key=lambda e: e.id):
        a, b = element.nodes
        dofs = np.array([offsets[node] + j for node in (a, b) for j in range(3)], dtype=np.int64)
        matrices = beam_matrices(element, nodes[a], nodes[b])
        stiffness[np.ix_(dofs, dofs)] += matrices.global_stiffness
        mass[np.ix_(dofs, dofs)] += matrices.global_mass
        assembled.append(AssembledElement(element, dofs, matrices))
    for load in model.loads:
        offset = offsets[load.node]
        force[offset : offset + 3] += [load.fx, load.fy, load.mz]
    fixed = np.array(
        sorted(offsets[c.node] + int(c.dof) for c in model.constraints), dtype=np.int64
    )
    free = np.setdiff1d(np.arange(size, dtype=np.int64), fixed)
    return Assembly(node_ids, stiffness, mass, force, free, fixed, tuple(assembled))


def constrained_system(assembly: Assembly, config: AnalysisConfig) -> tuple[Matrix, Matrix, Matrix]:
    """Equilibrate stiffness before stability checks to avoid mixed-unit thresholds.

    Return physical reduced K, M and diagonal scale D with K_scaled = D K D.
    No penalty constraints, stiffness shifts, or mass regularization are used.
    """
    if len(assembly.free) == 0:
        raise UnstableModelError("No free degrees of freedom remain.")
    free = np.ix_(assembly.free, assembly.free)
    stiffness = assembly.stiffness[free]
    mass = assembly.mass[free]
    diagonal = np.diag(stiffness)
    if np.any(diagonal <= 0):
        raise UnstableModelError("Zero stiffness at a free degree of freedom.")
    scale = 1 / np.sqrt(diagonal)
    scaled = scale[:, None] * stiffness * scale[None, :]
    eigenvalues = linalg.eigvalsh(scaled)
    if eigenvalues[0] <= config.stability_tolerance * eigenvalues[-1]:
        raise UnstableModelError(
            "Insufficient constraints, rigid-body modes, or numerically ill-conditioned stiffness. "
            "Check supports, units, and extreme mesh/section ratios."
        )
    return stiffness, mass, scale
