"""Dense assembly with a stable node-id/UX/UY/RZ ordering and exact elimination."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import linalg

from vibra.core.element import ElementMatrices, Matrix, beam_matrices
from vibra.core.errors import UnstableModelError
from vibra.core.models import AnalysisConfig, BeamElement, FrameModel, LinearMount


@dataclass(frozen=True)
class AssembledElement:
    element: BeamElement
    dofs: NDArray[np.int64]
    matrices: ElementMatrices


@dataclass(frozen=True)
class AssembledMount:
    mount: LinearMount
    extension: Matrix  # full global row B; extension = B @ u


@dataclass(frozen=True)
class Assembly:
    node_ids: tuple[int, ...]
    stiffness: Matrix
    mass: Matrix
    force: Matrix
    free: NDArray[np.int64]
    fixed: NDArray[np.int64]
    elements: tuple[AssembledElement, ...]
    mount_damping: Matrix
    mounts: tuple[AssembledMount, ...]


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
    for body in model.nodal_masses:
        x, y = body.offset
        m = body.mass
        local = np.array(
            [[m, 0, -m * y], [0, m, m * x], [-m * y, m * x, body.inertia_z + m * (x * x + y * y)]]
        )
        offset = offsets[body.node]
        mass[offset : offset + 3, offset : offset + 3] += local
    mount_damping = np.zeros((size, size))
    mounts = []
    for mount in sorted(model.mounts, key=lambda item: item.id):
        angle = np.deg2rad(mount.angle_degrees % 360)
        nx, ny = np.cos(angle), np.sin(angle)
        # Canonical axis directions have exact zeros, avoiding artificial tiny couplings.
        nx, ny = (0.0 if abs(nx) < 1e-15 else nx), (0.0 if abs(ny) < 1e-15 else ny)
        row = np.zeros(size)
        for node, point, sign in (
            (mount.node_a, mount.offset_a, 1),
            (mount.node_b, mount.offset_b, -1),
        ):
            if node is not None:
                x, y = point
                offset = offsets[node]
                row[offset : offset + 3] += sign * np.array([nx, ny, -nx * y + ny * x])
        outer = np.outer(row, row)
        stiffness += mount.stiffness * outer
        mount_damping += mount.damping * outer
        mounts.append(AssembledMount(mount, row))
    if not all(np.all(np.isfinite(matrix)) for matrix in (stiffness, mass, mount_damping)):
        raise UnstableModelError("Assembled matrices overflowed; check SI magnitudes.")
    for load in model.loads:
        offset = offsets[load.node]
        force[offset : offset + 3] += [load.fx, load.fy, load.mz]
    fixed = np.array(
        sorted(offsets[c.node] + int(c.dof) for c in model.constraints), dtype=np.int64
    )
    free = np.setdiff1d(np.arange(size, dtype=np.int64), fixed)
    return Assembly(
        node_ids,
        stiffness,
        mass,
        force,
        free,
        fixed,
        tuple(assembled),
        mount_damping,
        tuple(mounts),
    )


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
