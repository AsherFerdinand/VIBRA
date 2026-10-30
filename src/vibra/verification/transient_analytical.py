"""Independent continuous-time SDOF solutions and continuum cantilever pulse response."""

import numpy as np
from scipy.optimize import brentq

from vibra.core.element import Matrix
from vibra.core.mesh import BeamGeometry
from vibra.core.models import Material, Section


def free_sdof(
    time: Matrix, mass: float, stiffness: float, damping: float, x0: float, v0: float
) -> tuple[Matrix, Matrix, Matrix]:
    """Underdamped/undamped exact response; benchmarks do not use Newmark."""
    decay = damping / (2 * mass)
    wn_squared = stiffness / mass
    if decay**2 >= wn_squared:
        raise ValueError("Reference requires underdamping.")
    wd = np.sqrt(wn_squared - decay**2)
    b = (v0 + decay * x0) / wd
    x = np.exp(-decay * time) * (x0 * np.cos(wd * time) + b * np.sin(wd * time))
    v = np.exp(-decay * time) * (
        (-decay * x0 + b * wd) * np.cos(wd * time) + (-decay * b - x0 * wd) * np.sin(wd * time)
    )
    a = -(damping * v + stiffness * x) / mass
    return (
        np.asarray(x, dtype=np.float64),
        np.asarray(v, dtype=np.float64),
        np.asarray(a, dtype=np.float64),
    )


def forced_cosine_sdof(
    time: Matrix, mass: float, stiffness: float, damping: float, amplitude: float, omega: float
) -> tuple[Matrix, Matrix, Matrix]:
    phasor = amplitude / complex(stiffness - mass * omega**2, damping * omega)
    particular = phasor * np.exp(1j * omega * time)
    xh, vh, ah = free_sdof(
        time, mass, stiffness, damping, -phasor.real, -(1j * omega * phasor).real
    )
    return (
        np.asarray(particular.real + xh, dtype=np.float64),
        np.asarray((1j * omega * particular).real + vh, dtype=np.float64),
        np.asarray((-(omega**2) * particular).real + ah, dtype=np.float64),
    )


def half_sine_sdof(
    time: Matrix, mass: float, stiffness: float, amplitude: float, width: float
) -> Matrix:
    """Exact undamped zero-initial-state response to F sin(πt/width), then zero."""
    wn, omega = np.sqrt(stiffness / mass), np.pi / width
    if np.isclose(wn, omega, rtol=1e-8):
        raise ValueError("This reference uses distinct pulse and natural frequencies.")
    factor = amplitude / (mass * (wn**2 - omega**2))
    during = factor * (np.sin(omega * time) - omega / wn * np.sin(wn * time))
    end_x = factor * (np.sin(omega * width) - omega / wn * np.sin(wn * width))
    end_v = factor * omega * (np.cos(omega * width) - np.cos(wn * width))
    after = end_x * np.cos(wn * (time - width)) + end_v / wn * np.sin(wn * (time - width))
    return np.asarray(np.where(time <= width, during, after), dtype=np.float64)


def continuum_pulse_tip(
    time: Matrix,
    geometry: BeamGeometry,
    material: Material,
    section: Section,
    width: float = 0.04,
    modes: int = 128,
) -> Matrix:
    """Continuous uniform beam modal series, not a discrete FEM eigenproblem.

    For exact cantilever eigenfunctions normalized to unit tip translation,
    every modal mass is rho*A*L/4. Roots solve cos(beta)+sech(beta)=0 using an
    overflow-safe sech. Compare 96/128 modes to estimate truncation separately.
    """
    if not 1 <= modes <= 256:
        raise ValueError("Continuum pulse benchmark supports 1–256 bending modes.")
    total_mass = material.density * section.area * geometry.length
    factor = np.sqrt(
        material.young_modulus
        * section.second_moment
        / (material.density * section.area * geometry.length**4)
    )
    tip = np.zeros_like(time)
    for mode in range(1, modes + 1):
        beta = brentq(
            lambda b: np.cos(b) + 2 * np.exp(-b) / (1 + np.exp(-2 * b)),
            (mode - 1) * np.pi,
            mode * np.pi,
        )
        wn = beta**2 * factor
        tip += half_sine_sdof(time, total_mass / 4, wn**2 * total_mass / 4, 1, width)
    return tip
