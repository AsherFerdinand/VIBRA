"""Independent SDOF receptance and exact uniform-continuum beam tip compliance."""

import numpy as np

from vibra.core.mesh import BeamGeometry
from vibra.core.models import Material, Section
from vibra.solvers.harmonic import ComplexMatrix


def sdof_receptance(
    mass: float, stiffness: float, damping: float, frequencies_hz: tuple[float, ...]
) -> ComplexMatrix:
    """Unit-force cosine response: H = 1/(k−mω²+jcω)."""
    omega = 2 * np.pi * np.asarray(frequencies_hz)
    return np.asarray(1 / (stiffness - mass * omega**2 + 1j * damping * omega), dtype=np.complex128)


def continuum_cantilever_compliance(
    geometry: BeamGeometry,
    material: Material,
    section: Section,
    frequencies_hz: tuple[float, ...],
    alpha: float = 0,
    beta: float = 0,
) -> ComplexMatrix:
    """Uniform beam, transverse tip force, fixed-free boundary conditions.

    EI* = EI(1+jωβ); q⁴ = ρA(ω²−jωα)/EI*.
    H = (cosh(z)sin(z)−sinh(z)cos(z))/(EI* q³(1+cosh(z)cos(z))).
    No FEM matrices, modal sums or discrete solver outputs enter this solution.
    Intended for the first few bending modes; large hyperbolic arguments overflow.
    """
    ei = material.young_modulus * section.second_moment
    output = []
    for frequency in frequencies_hz:
        omega = 2 * np.pi * frequency
        effective_ei = ei * (1 + 1j * omega * beta)
        if omega == 0:
            output.append(complex(geometry.length**3 / (3 * ei)))
            continue
        q = (
            complex(
                material.density * section.area * (omega**2 - 1j * omega * alpha) / effective_ei
            )
            ** 0.25
        )
        z = q * geometry.length
        numerator = np.cosh(z) * np.sin(z) - np.sinh(z) * np.cos(z)
        denominator = effective_ei * q**3 * (1 + np.cosh(z) * np.cos(z))
        output.append(complex(numerator / denominator))
    return np.asarray(output, dtype=np.complex128)
