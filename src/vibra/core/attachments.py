"""Recover scalar spring/dashpot forces from the same assembled kinematic maps."""

import numpy as np

from vibra.core.assembly import Assembly
from vibra.core.element import Matrix


def mount_forces(assembly: Assembly, displacement: Matrix, velocity: Matrix) -> Matrix:
    """Last dimension is full global DOF; output last dimension is sorted mount id.

    Positive force resists positive extension B u. Force on endpoint A is -n*f,
    endpoint B is +n*f. Moments about reference nodes follow each rigid offset.
    Ground mount support force on the model is -n*f. Fixed-DOF solver reactions
    are separate; summing both is necessary for complete grounded equilibrium.
    """
    if displacement.shape != velocity.shape or displacement.shape[-1] != len(assembly.force):
        raise ValueError("Mount recovery requires matching full global u and v arrays.")
    return (
        np.stack(
            [
                entry.mount.stiffness * (displacement @ entry.extension)
                + entry.mount.damping * (velocity @ entry.extension)
                for entry in assembly.mounts
            ],
            axis=-1,
        )
        if assembly.mounts
        else np.zeros((*displacement.shape[:-1], 0))
    )
