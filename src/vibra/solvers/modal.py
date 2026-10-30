"""Undamped modes: K φ = λ M φ; physical modes satisfy φᵀ M φ = 1."""

import logging
from dataclasses import dataclass

import numpy as np
from scipy import linalg

from vibra.core.assembly import assemble, constrained_system
from vibra.core.element import Matrix
from vibra.core.errors import SolverError
from vibra.core.models import AnalysisConfig, FrameModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModalResult:
    node_ids: tuple[int, ...]
    eigenvalues: Matrix
    angular_frequencies: Matrix
    frequencies_hz: Matrix
    modes: Matrix  # columns are full global mass-normalized mode vectors
    axial_energy_fraction: Matrix
    families: tuple[str, ...]
    relative_residuals: Matrix


def solve_modal(model: FrameModel, config: AnalysisConfig | None = None) -> ModalResult:
    config = config or AnalysisConfig()
    assembly = assemble(model)
    stiffness, mass, scale = constrained_system(assembly, config)
    if config.modes > len(assembly.free):
        raise SolverError(
            f"Requested {config.modes} modes, but only {len(assembly.free)} free DOFs."
        )
    ks = scale[:, None] * stiffness * scale[None, :]
    ms = scale[:, None] * mass * scale[None, :]
    try:
        eigenvalues, vectors = linalg.eigh(ks, ms, subset_by_index=(0, config.modes - 1))
    except linalg.LinAlgError as exc:
        raise SolverError(
            "Generalized eigensolve failed; check stiffness and mass definiteness."
        ) from exc
    if np.any(eigenvalues <= 0) or not np.all(np.isfinite(eigenvalues)):
        raise SolverError("Nonpositive or invalid eigenvalues; no frequency clipping is applied.")
    modes = np.zeros((len(assembly.force), config.modes))
    modes[assembly.free, :] = scale[:, None] * vectors
    # Reproducible display sign only; physical eigenvector sign is arbitrary.
    for column in range(config.modes):
        pivot = int(np.argmax(np.abs(modes[:, column])))
        if modes[pivot, column] < 0:
            modes[:, column] *= -1
    axial_energy = np.zeros(config.modes)
    for entry in assembly.elements:
        local = entry.matrices.transform @ modes[entry.dofs, :]
        delta = local[3] - local[0]
        axial_energy += entry.matrices.stiffness[0, 0] * delta**2
    total_energy = np.sum(modes * (assembly.stiffness @ modes), axis=0)
    mount_energy = np.zeros(config.modes)
    for mount in assembly.mounts:
        mount_energy += mount.mount.stiffness * (mount.extension @ modes) ** 2
    fraction = axial_energy / total_energy
    families = tuple("axial" if f > 0.9 else "bending" if f < 0.1 else "coupled" for f in fraction)
    families = tuple(
        "mount/coupled" if mount_energy[j] / total_energy[j] > 0.1 else family
        for j, family in enumerate(families)
    )
    residuals = []
    for j, eigenvalue in enumerate(eigenvalues):
        vector = modes[assembly.free, j]
        kv, mv = stiffness @ vector, eigenvalue * (mass @ vector)
        residuals.append(float(np.linalg.norm(kv - mv) / (np.linalg.norm(kv) + np.linalg.norm(mv))))
    residual_array = np.array(residuals)
    if np.any(residual_array > 1e-6):
        raise SolverError("Modal eigenpair residual exceeds 1e-6.")
    logger.info("Modal solve: %d modes, max residual %.3e", config.modes, max(residuals))
    angular = np.sqrt(eigenvalues)
    return ModalResult(
        assembly.node_ids,
        eigenvalues,
        angular,
        angular / (2 * np.pi),
        modes,
        fraction,
        families,
        residual_array,
    )
