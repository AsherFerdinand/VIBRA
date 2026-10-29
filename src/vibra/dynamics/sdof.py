"""Linear SDOF mass-spring-damper integration in SI units."""

from dataclasses import dataclass

import numpy as np
from pydantic import Field
from scipy.integrate import solve_ivp

from vibra.core.element import Matrix
from vibra.core.errors import SolverError
from vibra.core.models import EngineeringModel


class SDOFConfig(EngineeringModel):
    mass: float = Field(gt=0, default=1.0)
    stiffness: float = Field(gt=0, default=100.0)
    damping: float = Field(ge=0, default=0.0)
    initial_displacement: float = 0.01
    initial_velocity: float = 0.0
    force_amplitude: float = 0.0
    excitation_hz: float = Field(ge=0, default=1.0)
    duration: float = Field(gt=0, default=5.0)
    samples: int = Field(ge=2, le=100000, default=1001)

    @property
    def angular_frequency(self) -> float:
        return float(np.sqrt(self.stiffness / self.mass))

    @property
    def damping_ratio(self) -> float:
        return float(self.damping / (2 * np.sqrt(self.stiffness * self.mass)))

    @property
    def damped_angular_frequency(self) -> float | None:
        """Overdamped/critical motion has no oscillatory damped frequency."""
        if self.damping_ratio >= 1:
            return None
        return float(self.angular_frequency * np.sqrt(1 - self.damping_ratio**2))


@dataclass(frozen=True)
class SDOFResult:
    time: Matrix
    displacement: Matrix
    velocity: Matrix
    acceleration: Matrix
    energy: Matrix  # kinetic plus elastic potential; excludes external work


def solve_sdof(config: SDOFConfig) -> SDOFResult:
    def rhs(time: float, state: Matrix) -> Matrix:
        force = config.force_amplitude * np.sin(2 * np.pi * config.excitation_hz * time)
        return np.array(
            [
                state[1],
                (force - config.damping * state[1] - config.stiffness * state[0]) / config.mass,
            ]
        )

    times = np.linspace(0, config.duration, config.samples)
    # Resolve the fastest structural/excitation period, regardless of output spacing.
    fastest = max(config.angular_frequency, 2 * np.pi * config.excitation_hz)
    solution = solve_ivp(
        rhs,
        (0, config.duration),
        [config.initial_displacement, config.initial_velocity],
        t_eval=times,
        method="DOP853",
        rtol=1e-10,
        atol=1e-12,
        max_step=2 * np.pi / fastest / 30,
    )
    if not solution.success or not np.all(np.isfinite(solution.y)):
        raise SolverError(f"SDOF integration failed: {solution.message}")
    displacement, velocity = solution.y
    force = config.force_amplitude * np.sin(2 * np.pi * config.excitation_hz * times)
    acceleration = (
        force - config.damping * velocity - config.stiffness * displacement
    ) / config.mass
    energy = 0.5 * config.mass * velocity**2 + 0.5 * config.stiffness * displacement**2
    return SDOFResult(times, displacement, velocity, acceleration, energy)
