"""Prismatic Euler–Bernoulli 2D frame element: [u1,v1,θ1,u2,v2,θ2]."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vibra.core.errors import InvalidModelError
from vibra.core.models import BeamElement, Node

Matrix = NDArray[np.float64]


@dataclass(frozen=True)
class ElementMatrices:
    length: float
    transform: Matrix  # d_local = transform @ d_global
    stiffness: Matrix
    mass: Matrix

    @property
    def global_stiffness(self) -> Matrix:
        return self.transform.T @ self.stiffness @ self.transform

    @property
    def global_mass(self) -> Matrix:
        return self.transform.T @ self.mass @ self.transform


def beam_matrices(element: BeamElement, start: Node, end: Node) -> ElementMatrices:
    dx, dy = end.x - start.x, end.y - start.y
    length = float(np.hypot(dx, dy))
    if not np.isfinite(length) or length <= 0:
        raise InvalidModelError("Beam length must be finite and positive.")
    c, s = dx / length, dy / length
    rotation = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]], dtype=float)
    transform = np.zeros((6, 6))
    transform[:3, :3] = transform[3:, 3:] = rotation
    e, a, i = element.material.young_modulus, element.section.area, element.section.second_moment
    axial = e * a / length
    bending = e * i / length**3
    stiffness = np.zeros((6, 6))
    stiffness[np.ix_([0, 3], [0, 3])] = axial * np.array([[1, -1], [-1, 1]])
    bend_ids = [1, 2, 4, 5]
    stiffness[np.ix_(bend_ids, bend_ids)] = bending * np.array(
        [
            [12, 6 * length, -12, 6 * length],
            [6 * length, 4 * length**2, -6 * length, 2 * length**2],
            [-12, -6 * length, 12, -6 * length],
            [6 * length, 2 * length**2, -6 * length, 4 * length**2],
        ]
    )
    total_mass = element.material.density * a * length
    mass = np.zeros((6, 6))
    mass[np.ix_([0, 3], [0, 3])] = total_mass / 6 * np.array([[2, 1], [1, 2]])
    mass[np.ix_(bend_ids, bend_ids)] = (
        total_mass
        / 420
        * np.array(
            [
                [156, 22 * length, 54, -13 * length],
                [22 * length, 4 * length**2, 13 * length, -3 * length**2],
                [54, 13 * length, 156, -22 * length],
                [-13 * length, -3 * length**2, -22 * length, 4 * length**2],
            ]
        )
    )
    if not np.all(np.isfinite(stiffness)) or not np.all(np.isfinite(mass)):
        raise InvalidModelError("Element matrices overflowed; check SI units and geometry.")
    return ElementMatrices(length, transform, stiffness, mass)
