"""Newmark average acceleration (β=1/4, γ=1/2) with jump-aware force accounting."""

import logging
from dataclasses import dataclass
from typing import Self

import numpy as np
from pydantic import Field, model_validator
from scipy import linalg
from scipy.linalg.lapack import dpocon

from vibra.core.assembly import assemble, constrained_system
from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError, SolverError
from vibra.core.models import AnalysisConfig, EngineeringModel, FrameModel
from vibra.dynamics.forcing import (
    HarmonicForce,
    PulseForce,
    SampledForce,
    TransientForce,
    force_limits,
)

logger = logging.getLogger(__name__)
MAX_STATE_VALUES = 2_000_000
MAX_GLOBAL_DOFS = 600


class TimeGrid(EngineeringModel):
    duration: float = Field(default=0.5, gt=0)
    time_step: float = Field(default=0.001, gt=0)

    @model_validator(mode="after")
    def uniform_grid(self) -> Self:
        count = self.duration / self.time_step
        if not np.isfinite(count) or not 1 <= count <= 50000:
            raise InvalidModelError("Require 1–50000 time intervals; adjust duration/time step.")
        if abs(count - round(count)) > 1e-9:
            raise InvalidModelError("Duration must be an integer multiple of the time step.")
        return self

    def times(self) -> Matrix:
        return np.linspace(0, self.duration, int(round(self.duration / self.time_step)) + 1)


class InitialValue(ResponseDOF):
    value: float  # m/rad for displacement; m/s or rad/s for velocity


class TransientConfig(EngineeringModel):
    grid: TimeGrid = Field(default_factory=TimeGrid)
    damping: Damping = Field(default_factory=Damping)
    loads: tuple[TransientForce, ...] = Field(default=(), max_length=32)
    responses: tuple[ResponseDOF, ...] = Field(min_length=1, max_length=256)
    initial_displacement: tuple[InitialValue, ...] = ()
    initial_velocity: tuple[InitialValue, ...] = ()
    condition_tolerance: float = Field(default=1e-12, ge=1e-15, lt=1e-3)
    residual_tolerance: float = Field(default=1e-9, gt=0, lt=1e-3)
    energy_tolerance: float = Field(default=1e-6, gt=0, lt=1e-2)
    stability_tolerance: float = Field(default=1e-12, gt=0, lt=1e-4)

    @model_validator(mode="after")
    def validate_dofs_and_events(self) -> Self:
        if len(set(self.responses)) != len(self.responses):
            raise InvalidModelError("Duplicate transient response DOFs.")
        for values in (self.initial_displacement, self.initial_velocity):
            keys = [(value.node, value.dof) for value in values]
            if len(set(keys)) != len(keys):
                raise InvalidModelError("Duplicate initial-condition DOFs.")
        sample_count = 0
        for load in self.loads:
            if isinstance(load, SampledForce):
                sample_count += len(load.times)
                if load.times[-1] < self.grid.duration:
                    raise InvalidModelError("Sampled force history must cover [0, duration].")
                continue
            events = (
                (load.start_time, load.end_time)
                if isinstance(load, PulseForce)
                else (load.start_time,)
            )
            for event in events:
                if event <= self.grid.duration:
                    index = event / self.grid.time_step
                    if abs(index - round(index)) > 1e-8:
                        raise InvalidModelError(
                            "Force onset/pulse end must align with the time grid."
                        )
        if sample_count > 50000:
            raise InvalidModelError("At most 50000 sampled-force input pairs per analysis.")
        return self


@dataclass(frozen=True)
class TransientResult:
    node_ids: tuple[int, ...]
    time: Matrix
    displacement: Matrix  # [time, full global DOF], m/rad
    velocity: Matrix
    acceleration: Matrix  # right-hand acceleration at force jumps
    force_right: Matrix
    force_left: Matrix
    constrained_indices: tuple[int, ...]
    reactions: Matrix  # [time, constrained DOF], same index order as constrained_indices
    response_dofs: tuple[ResponseDOF, ...]
    response_indices: tuple[int, ...]
    kinetic_energy: Matrix
    strain_energy: Matrix
    damping_dissipation: Matrix  # cumulative midpoint-velocity quadrature, J
    external_work: Matrix  # cumulative interval-average-force work, J
    energy_balance_residual: Matrix  # E(t) − E(0) + D(t) − W(t), J
    relative_energy_error: float
    backward_errors: Matrix
    mass_reciprocal_condition: float
    effective_reciprocal_condition: float
    natural_frequencies_hz: Matrix
    numerical_warnings: tuple[str, ...]

    @property
    def response_displacement(self) -> Matrix:
        return self.displacement[:, self.response_indices]

    @property
    def response_velocity(self) -> Matrix:
        return self.velocity[:, self.response_indices]

    @property
    def response_acceleration(self) -> Matrix:
        return self.acceleration[:, self.response_indices]


@dataclass(frozen=True)
class _Factor:
    scaling: Matrix
    factor: tuple[Matrix, bool]
    reciprocal_condition: float

    def solve(self, rhs: Matrix) -> Matrix:
        if not np.all(np.isfinite(rhs)):
            raise SolverError("Nonfinite Newmark right-hand side; check inputs and units.")
        return self.scaling * linalg.cho_solve(self.factor, self.scaling * rhs)


def _factor(matrix: Matrix, tolerance: float, name: str) -> _Factor:
    if not np.all(np.isfinite(matrix)) or np.any(np.diag(matrix) <= 0):
        raise SolverError(f"Invalid {name} matrix.")
    scaling = 1 / np.sqrt(np.diag(matrix))
    normalized = scaling[:, None] * matrix * scaling[None, :]
    if not np.all(np.isfinite(normalized)):
        raise SolverError(f"Nonfinite equilibrated {name} matrix.")
    try:
        factor = linalg.cho_factor(normalized, lower=True)
        reciprocal, info = dpocon(factor[0], float(linalg.norm(normalized, 1)), uplo="L")
    except linalg.LinAlgError as exc:
        raise SolverError(f"Singular/non-positive-definite {name} matrix.") from exc
    if info != 0 or not np.isfinite(reciprocal) or reciprocal <= tolerance:
        raise SolverError(
            f"Poorly conditioned {name} matrix (reciprocal condition {reciprocal:.3e})."
        )
    return _Factor(scaling, (factor[0], True), float(reciprocal))


def solve_transient(model: FrameModel, config: TransientConfig) -> TransientResult:
    """Reuse FEM K,M and C=αM+βK; no penalties, mass lumping or algorithmic damping.

    FrameModel.loads is static-only. At aligned finite force jumps, u and v remain
    continuous and acceleration is reset through M Δa = ΔF before the next step.
    """
    time = config.grid.times()
    size = 3 * len(model.nodes)
    if size > MAX_GLOBAL_DOFS:
        raise InvalidModelError("Transient dense solver supports at most 600 global DOFs.")
    if size * len(time) > MAX_STATE_VALUES:
        raise InvalidModelError(
            "Run exceeds 2000000 time×DOF values; reduce duration/mesh or increase dt."
        )
    assembly = assemble(model)
    k, m, scale = constrained_system(
        assembly, AnalysisConfig(stability_tolerance=config.stability_tolerance)
    )
    ks, ms = scale[:, None] * k * scale[None, :], scale[:, None] * m * scale[None, :]
    cs = config.damping.alpha * ms + config.damping.beta * ks
    offsets = {node: 3 * i for i, node in enumerate(assembly.node_ids)}
    for value in (
        *config.loads,
        *config.responses,
        *config.initial_displacement,
        *config.initial_velocity,
    ):
        if value.node not in offsets:
            raise InvalidModelError(f"Transient DOF references unknown node {value.node}.")
    force_right, force_left = np.zeros((len(time), size)), np.zeros((len(time), size))
    notes = []
    for load in config.loads:
        right, left = force_limits(load, time)
        if isinstance(load, HarmonicForce) and load.amplitude != 0 and load.start_time < time[-1]:
            if load.frequency_hz * config.grid.time_step >= 0.5:
                raise InvalidModelError(
                    "Harmonic forcing must be below the time-grid Nyquist frequency."
                )
        if isinstance(load, PulseForce) and load.shape == "half_sine":
            if load.amplitude != 0 and load.start_time < time[-1] and not np.any(right):
                raise InvalidModelError("Half-sine pulse has no nonzero grid samples; refine dt.")
        if isinstance(load, SampledForce) and not np.any(right):
            if any(
                t <= time[-1] and value != 0
                for t, value in zip(load.times, load.values, strict=True)
            ):
                raise InvalidModelError(
                    "Sampled force is completely missed by the grid; refine dt."
                )
        index = offsets[load.node] + int(load.dof)
        force_right[:, index] += right
        force_left[:, index] += left
        if isinstance(load, SampledForce):
            knots = np.asarray(load.times) / config.grid.time_step
            if np.any(np.abs(knots - np.round(knots)) > 1e-8):
                notes.append(
                    "Sampled-force knots are off the integration grid; check time-step convergence."
                )
        if (
            isinstance(load, PulseForce)
            and (load.end_time - load.start_time) / config.grid.time_step < 10
        ):
            notes.append(
                "Pulse has fewer than 10 time intervals; refine the force/time resolution."
            )
        if isinstance(load, HarmonicForce) and load.frequency_hz * config.grid.time_step > 0.05:
            notes.append("Harmonic excitation has fewer than 20 steps per cycle.")
    if not np.all(np.isfinite(force_right)) or not np.all(np.isfinite(force_left)):
        raise SolverError("Nonfinite/superposed force history; check input magnitudes.")
    rhs_right = force_right[:, assembly.free] * scale
    rhs_left = force_left[:, assembly.free] * scale
    initial_u, initial_v = np.zeros(size), np.zeros(size)
    fixed = set(assembly.fixed.tolist())
    for values, target in (
        (config.initial_displacement, initial_u),
        (config.initial_velocity, initial_v),
    ):
        for value in values:
            index = offsets[value.node] + int(value.dof)
            if index in fixed and value.value != 0:
                raise InvalidModelError(
                    "Initial displacement/velocity at a constrained DOF must be zero."
                )
            target[index] = value.value
    h = float(time[1] - time[0])
    if not np.isfinite(h * h) or h * h == 0:
        raise SolverError("Time step is outside the supported double-precision range.")
    mass_factor = _factor(ms, config.condition_tolerance, "mass")
    effective = ms + 0.5 * h * cs + 0.25 * h**2 * ks
    step_factor = _factor(effective, config.condition_tolerance, "effective Newmark")
    try:
        eigenvalues = linalg.eigvalsh(ks, ms)
    except linalg.LinAlgError as exc:
        raise SolverError("Transient mass/stiffness eigensolve failed.") from exc
    if np.any(eigenvalues <= 0) or not np.all(np.isfinite(eigenvalues)):
        raise SolverError("Invalid natural frequencies in transient model.")
    natural = np.sqrt(eigenvalues) / (2 * np.pi)
    if h * natural[0] > 0.05:
        notes.append(
            "First natural mode has fewer than 20 steps per cycle; temporal accuracy is poor."
        )
    if h * natural[-1] > 0.05:
        notes.append(
            "Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest."
        )
    u = np.zeros((len(time), len(assembly.free)))
    v, a = np.zeros_like(u), np.zeros_like(u)
    u[0], v[0] = initial_u[assembly.free] / scale, initial_v[assembly.free] / scale
    a[0] = mass_factor.solve(rhs_right[0] - cs @ v[0] - ks @ u[0])
    for i in range(len(time) - 1):
        predicted_u = u[i] + h * v[i] + 0.25 * h**2 * a[i]
        predicted_v = v[i] + 0.5 * h * a[i]
        left_a = step_factor.solve(rhs_left[i + 1] - cs @ predicted_v - ks @ predicted_u)
        u[i + 1] = predicted_u + 0.25 * h**2 * left_a
        v[i + 1] = predicted_v + 0.5 * h * left_a
        jump = rhs_right[i + 1] - rhs_left[i + 1]
        a[i + 1] = left_a + mass_factor.solve(jump) if np.any(jump) else left_a
    if not all(np.all(np.isfinite(array)) for array in (u, v, a)):
        raise SolverError("Nonfinite transient state; no invalid history is returned.")
    residual = a @ ms + v @ cs + u @ ks - rhs_right
    denominator = sum(
        float(linalg.norm(matrix, np.inf)) * np.max(np.abs(state), axis=1)
        for matrix, state in ((ms, a), (cs, v), (ks, u))
    ) + np.max(np.abs(rhs_right), axis=1)
    errors = np.divide(
        np.max(np.abs(residual), axis=1),
        denominator,
        out=np.zeros(len(time)),
        where=denominator > 0,
    )
    if (
        not np.all(np.isfinite(denominator))
        or not np.all(np.isfinite(errors))
        or np.max(errors) > config.residual_tolerance
    ):
        raise SolverError("Transient equilibrium backward error exceeds tolerance.")
    kinetic = 0.5 * np.sum(v * (v @ ms), axis=1)
    strain = 0.5 * np.sum(u * (u @ ks), axis=1)
    midpoint_v = 0.5 * (v[:-1] + v[1:])
    dissipated_steps = h * np.sum(midpoint_v * (midpoint_v @ cs), axis=1)
    work_steps = np.sum(0.5 * (rhs_right[:-1] + rhs_left[1:]) * np.diff(u, axis=0), axis=1)
    dissipation, work = np.r_[0, np.cumsum(dissipated_steps)], np.r_[0, np.cumsum(work_steps)]
    energy_residual = kinetic + strain - kinetic[0] - strain[0] + dissipation - work
    reference = float(max(np.max(kinetic + strain), np.max(dissipation), np.max(np.abs(work))))
    relative = float(np.max(np.abs(energy_residual)) / reference) if reference else 0.0
    if (
        not all(
            np.all(np.isfinite(array))
            for array in (kinetic, strain, dissipation, work, energy_residual)
        )
        or np.any(kinetic < 0)
        or np.any(strain < 0)
        or np.any(dissipated_steps < 0)
        or not np.isfinite(relative)
        or relative > config.energy_tolerance
    ):
        raise SolverError(
            "Transient energy accounting failed; check conditioning and time resolution."
        )
    displacement, velocity, acceleration = (
        np.zeros((len(time), size)),
        np.zeros((len(time), size)),
        np.zeros((len(time), size)),
    )
    displacement[:, assembly.free], velocity[:, assembly.free], acceleration[:, assembly.free] = (
        u * scale,
        v * scale,
        a * scale,
    )
    c_full = config.damping.alpha * assembly.mass + config.damping.beta * assembly.stiffness
    reactions = (
        acceleration @ assembly.mass[:, assembly.fixed]
        + velocity @ c_full[:, assembly.fixed]
        + displacement @ assembly.stiffness[:, assembly.fixed]
        - force_right[:, assembly.fixed]
    )
    if not all(
        np.all(np.isfinite(array)) for array in (displacement, velocity, acceleration, reactions)
    ):
        raise SolverError("Physical transient state/reaction overflowed.")
    indices = tuple(offsets[r.node] + int(r.dof) for r in config.responses)
    logger.info("Newmark solve: %d steps, energy error %.3e", len(time) - 1, relative)
    return TransientResult(
        assembly.node_ids,
        time,
        displacement,
        velocity,
        acceleration,
        force_right,
        force_left,
        tuple(int(i) for i in assembly.fixed),
        reactions,
        config.responses,
        indices,
        kinetic,
        strain,
        dissipation,
        work,
        energy_residual,
        relative,
        errors,
        mass_factor.reciprocal_condition,
        step_factor.reciprocal_condition,
        natural,
        tuple(dict.fromkeys(notes)),
    )
