"""Independent continuum/lumped analytical benchmarks."""

import numpy as np
from scipy.optimize import brentq

from vibra.core.element import Matrix
from vibra.core.mesh import BeamGeometry
from vibra.core.models import Material, Section
from vibra.dynamics.sdof import SDOFConfig


def cantilever_tip(
    geometry: BeamGeometry, material: Material, section: Section, force: float
) -> tuple[float, float]:
    ei = material.young_modulus * section.second_moment
    return force * geometry.length**3 / (3 * ei), force * geometry.length**2 / (2 * ei)


def cantilever_bending_hz(
    geometry: BeamGeometry, material: Material, section: Section, modes: int = 3
) -> Matrix:
    """Solve cos(β) + sech(β) = 0; stable form of cosh(β)cos(β) = -1."""
    if modes < 1 or modes > 10:
        raise ValueError("Analytical benchmark supports 1–10 bending roots.")
    roots = np.array(
        [
            brentq(lambda b: np.cos(b) + 1 / np.cosh(b), (n - 1) * np.pi, n * np.pi)
            for n in range(1, modes + 1)
        ]
    )
    factor = np.sqrt(
        material.young_modulus
        * section.second_moment
        / (material.density * section.area * geometry.length**4)
    )
    return np.asarray(roots**2 * factor / (2 * np.pi), dtype=np.float64)


def underdamped_free(config: SDOFConfig, time: Matrix) -> Matrix:
    if config.force_amplitude != 0 or config.damping_ratio >= 1:
        raise ValueError("Benchmark requires free, underdamped vibration.")
    wn, zeta = config.angular_frequency, config.damping_ratio
    wd = wn * np.sqrt(1 - zeta**2)
    return np.asarray(
        np.exp(-zeta * wn * time)
        * (
            config.initial_displacement * np.cos(wd * time)
            + (config.initial_velocity + zeta * wn * config.initial_displacement)
            / wd
            * np.sin(wd * time)
        ),
        dtype=np.float64,
    )
