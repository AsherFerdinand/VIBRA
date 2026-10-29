"""Direct steady-state FEM response with exact zero-constraint elimination."""

import logging
import warnings
from dataclasses import dataclass
from typing import Literal, Self

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator
from scipy import linalg
from scipy.linalg.lapack import zgecon
from scipy.signal import find_peaks

from vibra.core.assembly import assemble, constrained_system
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError, SolverError
from vibra.core.models import DOF, AnalysisConfig, EngineeringModel, FrameModel

ComplexMatrix = NDArray[np.complex128]
logger = logging.getLogger(__name__)


class Damping(EngineeringModel):
    kind: Literal["undamped", "mass", "stiffness", "rayleigh"] = "undamped"
    alpha: float = Field(default=0.0, ge=0, description="Mass coefficient [1/s]")
    beta: float = Field(default=0.0, ge=0, description="Stiffness coefficient [s]")

    @model_validator(mode="after")
    def active_coefficients(self) -> Self:
        if self.kind in ("undamped", "stiffness") and self.alpha != 0:
            raise InvalidModelError(f"{self.kind} damping requires alpha = 0.")
        if self.kind in ("undamped", "mass") and self.beta != 0:
            raise InvalidModelError(f"{self.kind} damping requires beta = 0.")
        return self


class FrequencySweep(EngineeringModel):
    start_hz: float = Field(default=0, ge=0)
    stop_hz: float = Field(default=60, gt=0)
    points: int = Field(default=401, ge=2, le=10001)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.stop_hz <= self.start_hz:
            raise InvalidModelError("Sweep stop frequency must exceed start frequency.")
        return self

    def frequencies(self) -> tuple[float, ...]:
        return tuple(float(f) for f in np.linspace(self.start_hz, self.stop_hz, self.points))


class ResponseDOF(EngineeringModel):
    node: int = Field(ge=0)
    dof: DOF = DOF.UY

    @property
    def label(self) -> str:
        return f"Node {self.node} {self.dof.name} [{'rad' if self.dof == DOF.RZ else 'm'}]"


class HarmonicLoad(ResponseDOF):
    amplitude: float = Field(ge=0, description="Peak force [N] or moment [N m], not RMS")
    phase_degrees: float = 0.0


class HarmonicConfig(EngineeringModel):
    frequencies_hz: tuple[float, ...] = Field(min_length=1, max_length=10001)
    damping: Damping = Field(default_factory=Damping)
    loads: tuple[HarmonicLoad, ...] = ()
    responses: tuple[ResponseDOF, ...] = Field(min_length=1)
    condition_tolerance: float = Field(default=1e-12, ge=1e-15, lt=1e-3)
    residual_tolerance: float = Field(default=1e-9, gt=0, lt=1e-3)
    stability_tolerance: float = Field(default=1e-12, gt=0, lt=1e-4)

    @model_validator(mode="after")
    def valid_sweep(self) -> Self:
        frequencies = np.asarray(self.frequencies_hz)
        if not np.all(np.isfinite(frequencies)) or np.any(frequencies < 0):
            raise InvalidModelError("Frequencies must be finite and nonnegative [Hz].")
        if np.any(np.diff(frequencies) <= 0):
            raise InvalidModelError("Frequencies must be strictly increasing without duplicates.")
        if len(set(self.responses)) != len(self.responses):
            raise InvalidModelError("Duplicate response DOFs.")
        return self


@dataclass(frozen=True)
class SampledPeak:
    response: ResponseDOF
    index: int
    frequency_hz: float
    amplitude: float
    phase_radians: float | None
    at_sweep_boundary: bool


@dataclass(frozen=True)
class HarmonicResult:
    node_ids: tuple[int, ...]
    frequencies_hz: Matrix
    displacement: ComplexMatrix  # [frequency, full global DOF], constrained entries exactly zero
    force_phasor: ComplexMatrix  # full global peak load, shared by the sweep
    response_dofs: tuple[ResponseDOF, ...]
    response_indices: tuple[int, ...]
    response_amplitude: Matrix  # [frequency, selected response]
    phase_radians: Matrix  # zero placeholder where phase_defined is False
    phase_defined: NDArray[np.bool_]
    natural_frequencies_hz: Matrix  # all undamped free-DOF natural frequencies
    modal_damping_ratios: Matrix
    reciprocal_condition: Matrix  # equilibrated inverse-norm estimate, cancellation adjusted
    backward_errors: Matrix
    peaks: tuple[SampledPeak, ...]  # strictly interior sampled local maxima
    sampled_maxima: tuple[SampledPeak, ...]  # largest sample per nonzero response


def solve_harmonic(model: FrameModel, config: HarmonicConfig) -> HarmonicResult:
    """Solve (K + jωC − ω²M)U = F for peak, cosine-reference phasors.

    Only config.loads participates; FrameModel.loads belongs to static analysis.
    Duplicate harmonic loads superpose coherently. Constrained loads are allowed
    (carried by supports); response at a constrained DOF is identically zero.
    An unsafe frequency aborts the whole sweep with its frequency in the error.
    """
    assembly = assemble(model)
    stiffness, mass, scale = constrained_system(
        assembly, AnalysisConfig(stability_tolerance=config.stability_tolerance)
    )
    offsets = {node: 3 * index for index, node in enumerate(assembly.node_ids)}
    for dof in (*config.loads, *config.responses):
        if dof.node not in offsets:
            raise InvalidModelError(f"Harmonic DOF references unknown node {dof.node}.")
    force = np.zeros(len(assembly.force), dtype=np.complex128)
    for load in config.loads:
        force[offsets[load.node] + int(load.dof)] += load.amplitude * np.exp(
            1j * np.deg2rad(load.phase_degrees % 360)
        )
    ks = scale[:, None] * stiffness * scale[None, :]
    ms = scale[:, None] * mass * scale[None, :]
    cs = config.damping.alpha * ms + config.damping.beta * ks
    if not np.all(np.isfinite(cs)) or not np.all(np.isfinite(force)):
        raise SolverError("Damping or superposed forces overflowed; check SI inputs.")
    try:
        eigenvalues = linalg.eigvalsh(ks, ms)
    except linalg.LinAlgError as exc:
        raise SolverError("Harmonic mass/stiffness eigensolve failed; check definiteness.") from exc
    if np.any(eigenvalues <= 0) or not np.all(np.isfinite(eigenvalues)):
        raise SolverError("Invalid natural frequencies in harmonic model.")
    natural_omega = np.sqrt(eigenvalues)
    natural_hz = natural_omega / (2 * np.pi)
    damping_ratios = (
        config.damping.alpha / (2 * natural_omega) + config.damping.beta * natural_omega / 2
    )
    if not np.all(np.isfinite(damping_ratios)):
        raise SolverError("Modal damping ratios overflowed; check coefficients.")
    frequencies = np.asarray(config.frequencies_hz, dtype=np.float64)
    displacement = np.zeros((len(frequencies), len(force)), dtype=np.complex128)
    reciprocal_conditions, errors = np.zeros(len(frequencies)), np.zeros(len(frequencies))
    rhs = scale * force[assembly.free]
    if not np.all(np.isfinite(rhs)):
        raise SolverError("Scaled harmonic force overflowed; check SI inputs.")
    for index, frequency in enumerate(frequencies):
        omega = 2 * np.pi * frequency
        with np.errstate(over="ignore", invalid="ignore"):
            dynamic = np.asarray(ks - omega**2 * ms + 1j * omega * cs, dtype=np.complex128)
            reference = float(
                linalg.norm(ks, 1) + omega**2 * linalg.norm(ms, 1) + omega * linalg.norm(cs, 1)
            )
        if not np.all(np.isfinite(dynamic)) or not np.isfinite(reference):
            raise SolverError(f"Dynamic stiffness overflow at {frequency:.12g} Hz.")
        norm = float(linalg.norm(dynamic, 1))
        if not np.isfinite(norm) or norm == 0:
            raise SolverError(f"Singular dynamic stiffness at {frequency:.12g} Hz.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", linalg.LinAlgWarning)
                lu, pivots = linalg.lu_factor(dynamic)
            rcond, info = zgecon(lu, norm)
            # A scalar near resonance has raw cond=1 despite destructive K−ω²M
            # cancellation. Compare dynamic norm with its uncancelled terms too.
            effective_rcond = float(rcond * norm / reference)
            if (
                info != 0
                or not np.isfinite(effective_rcond)
                or effective_rcond <= config.condition_tolerance
            ):
                raise SolverError(
                    f"Poorly conditioned dynamic stiffness at {frequency:.12g} Hz "
                    f"(adjusted reciprocal condition {effective_rcond:.3e}). "
                    "Check damping, resonance, units, and mesh; no regularization was applied."
                )
            reduced = linalg.lu_solve((lu, pivots), rhs)
        except (linalg.LinAlgError, linalg.LinAlgWarning) as exc:
            raise SolverError(f"Singular dynamic stiffness at {frequency:.12g} Hz.") from exc
        residual = dynamic @ reduced - rhs
        denominator = norm * float(linalg.norm(reduced, 1)) + float(linalg.norm(rhs, 1))
        error = float(linalg.norm(residual, 1)) / denominator if denominator else 0.0
        if (
            not np.all(np.isfinite(reduced))
            or not np.isfinite(error)
            or error > config.residual_tolerance
        ):
            raise SolverError(f"Invalid harmonic solution/residual at {frequency:.12g} Hz.")
        displacement[index, assembly.free] = scale * reduced
        reciprocal_conditions[index], errors[index] = effective_rcond, error
    if not np.all(np.isfinite(displacement)):
        raise SolverError("Physical harmonic displacement overflowed after equilibration.")
    response_indices = tuple(offsets[r.node] + int(r.dof) for r in config.responses)
    response = displacement[:, response_indices]
    amplitude = np.abs(response)
    if not np.all(np.isfinite(amplitude)):
        raise SolverError("Harmonic amplitude overflowed; check SI inputs.")
    phase_defined = amplitude > np.max(amplitude, axis=0, keepdims=True) * 1e-12
    phase = np.where(phase_defined, np.angle(response), 0.0)
    peaks: list[SampledPeak] = []
    maxima: list[SampledPeak] = []

    def peak(sample: int, column: int) -> SampledPeak:
        return SampledPeak(
            config.responses[column],
            sample,
            float(frequencies[sample]),
            float(amplitude[sample, column]),
            float(phase[sample, column]) if phase_defined[sample, column] else None,
            sample in (0, len(frequencies) - 1),
        )

    for column in range(len(config.responses)):
        peaks.extend(peak(int(sample), column) for sample in find_peaks(amplitude[:, column])[0])
        if np.max(amplitude[:, column]) > 0:
            maxima.append(peak(int(np.argmax(amplitude[:, column])), column))
    logger.info("Harmonic sweep: %d points, max backward error %.3e", len(frequencies), max(errors))
    return HarmonicResult(
        assembly.node_ids,
        frequencies,
        displacement,
        force,
        config.responses,
        response_indices,
        amplitude,
        phase,
        phase_defined,
        natural_hz,
        damping_ratios,
        reciprocal_conditions,
        errors,
        tuple(peaks),
        tuple(maxima),
    )
