"""Illustrative EV motor-interface support rail study; no production component claim."""

from dataclasses import dataclass
from typing import Literal, Self

import numpy as np
from pydantic import Field, model_validator

from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import AnalysisConfig, EngineeringModel, FrameModel, Material, Rectangle
from vibra.dynamics.forcing import PulseForce
from vibra.signals.analysis import SpectrumResult, analyze_signal
from vibra.signals.fem import Quantity, extract_transient_signal
from vibra.signals.models import SignalSeries, SpectrumConfig
from vibra.solvers.harmonic import (
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    HarmonicResult,
    solve_harmonic,
)
from vibra.solvers.modal import ModalResult, solve_modal
from vibra.solvers.static import StaticResult, solve_static
from vibra.solvers.transient import TimeGrid, TransientConfig, TransientResult, solve_transient
from vibra.verification.analytical import cantilever_bending_hz, cantilever_tip

Location = float


class SupportDesign(EngineeringModel):
    name: str = Field(default="Baseline A", min_length=1)
    length: float = Field(default=0.45, gt=0)
    width: float = Field(default=0.025, gt=0)
    height: float = Field(default=0.012, gt=0)
    young_modulus: float = Field(default=210e9, gt=0)
    density: float = Field(default=7850, gt=0)

    @model_validator(mode="after")
    def slender_scope(self) -> Self:
        if self.length / self.height < 10:
            raise InvalidModelError("Equivalent support rails require L/h >= 10.")
        return self

    @property
    def structural_mass(self) -> float:
        return self.density * self.width * self.height * self.length


def modified_design() -> SupportDesign:
    return SupportDesign(name="Deeper section B", height=0.015)


class NVHConfig(EngineeringModel):
    baseline: SupportDesign = Field(default_factory=SupportDesign)
    modified: SupportDesign = Field(default_factory=modified_design)
    elements: Literal[4, 8, 16] = 8
    static_force_N: float = -200.0
    harmonic_force_N: float = Field(default=2, gt=0)
    excitation_fraction: Location = 1.0
    monitor_fraction: Location = 1.0
    excitation_order: float = Field(default=2, gt=0)
    operating_rpm: float = Field(default=1800, ge=0)
    sweep: FrequencySweep = Field(default_factory=lambda: FrequencySweep(stop_hz=160, points=401))
    damping: Damping = Field(default_factory=lambda: Damping(kind="rayleigh", alpha=4, beta=8e-5))
    pulse_force_N: float = -20.0
    pulse_width_s: float = Field(default=0.01, gt=0)
    grid: TimeGrid = Field(default_factory=lambda: TimeGrid(duration=0.4, time_step=0.0001))

    @property
    def operating_frequency_hz(self) -> float:
        return self.excitation_order * self.operating_rpm / 60

    @model_validator(mode="after")
    def practical_study(self) -> Self:
        if self.excitation_fraction not in (0.25, 0.5, 1.0) or self.monitor_fraction not in (
            0.25,
            0.5,
            1.0,
        ):
            raise InvalidModelError("Locations must be x/L = 0.25, 0.5 or 1.0.")
        if self.baseline.length / self.baseline.height < 12:
            raise InvalidModelError(
                "Baseline needs L/h >=12 to retain slenderness in ±10% studies."
            )
        if self.static_force_N == 0 or self.pulse_force_N == 0:
            raise InvalidModelError("This investigation requires nonzero static and pulse loads.")
        if (
            self.sweep.points > 1001
            or not self.sweep.start_hz <= self.operating_frequency_hz <= self.sweep.stop_hz
        ):
            raise InvalidModelError("Use <=1001 sweep points and include the operating frequency.")
        if self.damping.alpha == self.damping.beta == 0:
            raise InvalidModelError(
                "Study requires nonzero damping; undamped poles are not finite responses."
            )
        steps = self.grid.duration / self.grid.time_step
        if steps > 6250 or self.grid.duration < 0.1:
            raise InvalidModelError(
                "Study requires duration >=0.1 s and <=6250 base time intervals."
            )
        if not 10 * self.grid.time_step <= self.pulse_width_s < self.grid.duration / 2:
            raise InvalidModelError(
                "Pulse needs >=10 base intervals and must end before half the record."
            )
        ratio = self.pulse_width_s / self.grid.time_step
        if abs(ratio - round(ratio)) > 1e-8:
            raise InvalidModelError("Pulse end must align with the base time grid.")
        if round(steps) - 2 * round(ratio) + 1 < 4:
            raise InvalidModelError(
                "Need at least four post-pulse signal samples after twice the pulse width."
            )
        return self


def support_model(design: SupportDesign, elements: int, static_force_N: float) -> FrameModel:
    if elements not in (4, 8, 16):
        raise InvalidModelError(
            "Study meshes are 4, 8 or 16 elements, preserving station locations."
        )
    return cantilever(
        BeamGeometry(length=design.length),
        Material(
            name="Illustrative support metal",
            young_modulus=design.young_modulus,
            density=design.density,
        ),
        Rectangle(width=design.width, height=design.height).section(),
        elements,
        static_force_N,
    )


def harmonic_case(
    config: NVHConfig,
    model: FrameModel,
    damping: Damping | None = None,
    excitation: Location | None = None,
) -> HarmonicConfig:
    count = len(model.elements)
    location = config.excitation_fraction if excitation is None else excitation
    if location not in (0.25, 0.5, 1.0):
        raise InvalidModelError("Excitation station must be 0.25, 0.5 or 1.0.")
    frequencies = tuple(sorted(set((*config.sweep.frequencies(), config.operating_frequency_hz))))
    monitors = sorted({count // 2, count, int(count * config.monitor_fraction)})
    return HarmonicConfig(
        frequencies_hz=frequencies,
        damping=damping or config.damping,
        loads=(HarmonicLoad(node=int(count * location), amplitude=config.harmonic_force_N),),
        responses=tuple(ResponseDOF(node=node) for node in monitors),
    )


def transient_case(
    config: NVHConfig, model: FrameModel, step: float | None = None
) -> TransientConfig:
    count = len(model.elements)
    monitors = sorted({count // 2, count, int(count * config.monitor_fraction)})
    return TransientConfig(
        grid=TimeGrid(duration=config.grid.duration, time_step=step or config.grid.time_step),
        damping=config.damping,
        loads=(
            PulseForce(
                node=int(count * config.excitation_fraction),
                amplitude=config.pulse_force_N,
                end_time=config.pulse_width_s,
            ),
        ),
        responses=tuple(ResponseDOF(node=node) for node in monitors),
    )


@dataclass(frozen=True)
class StudySignal:
    series: SignalSeries
    spectrum: SpectrumResult


@dataclass(frozen=True)
class DesignSummary:
    mass_kg: float
    maximum_static_translation_m: float
    support_reactions_N_Nm: tuple[float, float, float]
    maximum_end_moment_Nm: float
    maximum_axial_end_force_N: float
    equilibrium_residual_N_Nm: tuple[float, float, float]
    first_natural_hz: float
    operating_amplitude_m: float
    operating_phase_degrees: float | None
    sampled_harmonic_peak_m: float
    sampled_peak_hz: float
    transient_peak_displacement_m: float
    transient_peak_velocity_m_per_s: float
    transient_peak_acceleration_m_per_s2: float
    displacement_signal_rms_m: float
    acceleration_signal_rms_m_per_s2: float
    dominant_displacement_hz: float | None
    dominant_acceleration_hz: float | None
    final_to_pulse_end_energy_ratio: float
    relative_energy_balance_error: float
    maximum_dynamic_support_force_N: float
    static_tip_relative_analytical_error: float
    first_frequency_relative_analytical_error: float


@dataclass(frozen=True)
class DesignInvestigation:
    design: SupportDesign
    model: FrameModel
    static: StaticResult
    modal: ModalResult
    harmonic_config: HarmonicConfig
    harmonic: HarmonicResult
    transient_config: TransientConfig
    transient: TransientResult
    signals: dict[Quantity, StudySignal]
    summary: DesignSummary


@dataclass(frozen=True)
class ParameterVariation:
    parameter: str
    multiplier: float
    first_frequency_hz: float
    first_frequency_ratio: float
    static_tip_m: float
    static_tip_ratio: float
    mass_ratio: float
    expected_frequency_ratio: float
    expected_static_ratio: float


@dataclass(frozen=True)
class Sensitivity:
    damping_multiplier: float
    excitation_fraction: float
    monitor_fraction: float
    operating_amplitude_m: float
    sampled_peak_amplitude_m: float
    sampled_peak_hz: float
    young_modulus_factor: float
    first_natural_hz: float


@dataclass(frozen=True)
class ConvergencePoint:
    elements: int
    time_step_s: float
    peak_monitored_displacement_m: float
    peak_monitored_acceleration_m_per_s2: float
    relative_velocity_difference_from_finest: float
    relative_acceleration_difference_from_finest: float
    relative_difference_from_finest: float
    relative_energy_balance_error: float
    maximum_backward_error: float


@dataclass(frozen=True)
class StudyConvergence:
    design_name: str
    time: tuple[ConvergencePoint, ...]
    mesh: tuple[ConvergencePoint, ...]


@dataclass(frozen=True)
class NVHStudy:
    config: NVHConfig
    baseline: DesignInvestigation
    modified: DesignInvestigation
    parameter_variations: tuple[ParameterVariation, ...]
    sensitivities: dict[str, tuple[Sensitivity, ...]]
    convergence: tuple[StudyConvergence, ...]
    verification_checks: dict[str, bool]


def _equilibrium(model: FrameModel, static: StaticResult) -> tuple[float, float, float]:
    total = np.sum(static.reactions, axis=0)
    nodes = {node.id: node for node in model.nodes}
    for index, node_id in enumerate(static.node_ids):
        node = nodes[node_id]
        total[2] += node.x * static.reactions[index, 1] - node.y * static.reactions[index, 0]
    for load in model.loads:
        node = nodes[load.node]
        total += [load.fx, load.fy, load.mz + node.x * load.fy - node.y * load.fx]
    return float(total[0]), float(total[1]), float(total[2])


def investigate_design(design: SupportDesign, config: NVHConfig) -> DesignInvestigation:
    model = support_model(design, config.elements, config.static_force_N)
    static = solve_static(model)
    modal = solve_modal(model, AnalysisConfig(modes=min(6, 3 * config.elements)))
    harmonic_config = harmonic_case(config, model)
    harmonic = solve_harmonic(model, harmonic_config)
    transient_config = transient_case(config, model)
    transient = solve_transient(model, transient_config)
    monitor = int(config.elements * config.monitor_fraction)
    signals: dict[Quantity, StudySignal] = {}
    # Observe ringdown after an additional pulse-width settling interval.
    start = int(np.searchsorted(transient.time, 2 * config.pulse_width_s, side="left"))
    quantities: tuple[Quantity, ...] = ("displacement", "acceleration")
    for quantity in quantities:
        series = extract_transient_signal(
            model, transient_config, transient, node=monitor, quantity=quantity, start_index=start
        )
        signals[quantity] = StudySignal(series, analyze_signal(series, SpectrumConfig()))
    column = harmonic.response_dofs.index(ResponseDOF(node=monitor))
    operating = int(np.argmin(np.abs(harmonic.frequencies_hz - config.operating_frequency_hz)))
    peak_index = int(np.argmax(harmonic.response_amplitude[:, column]))
    pulse_end = int(round(config.pulse_width_s / config.grid.time_step))
    energy = transient.kinetic_energy + transient.strain_energy
    total_at_pulse_end = float(energy[pulse_end])
    geometry = BeamGeometry(length=design.length)
    material, section = model.elements[0].material, model.elements[0].section
    exact_tip, _ = cantilever_tip(geometry, material, section, config.static_force_N)
    exact_frequency = float(cantilever_bending_hz(geometry, material, section, 1)[0])
    summary = DesignSummary(
        design.structural_mass,
        float(np.max(np.linalg.norm(static.displacement[:, :2], axis=1))),
        (
            float(static.reactions[0, 0]),
            float(static.reactions[0, 1]),
            float(static.reactions[0, 2]),
        ),
        max(float(np.max(np.abs(q[[2, 5]]))) for q in static.element_end_forces.values()),
        max(float(np.max(np.abs(q[[0, 3]]))) for q in static.element_end_forces.values()),
        _equilibrium(model, static),
        float(modal.frequencies_hz[0]),
        float(harmonic.response_amplitude[operating, column]),
        float(np.rad2deg(harmonic.phase_radians[operating, column]))
        if harmonic.phase_defined[operating, column]
        else None,
        float(harmonic.response_amplitude[peak_index, column]),
        float(harmonic.frequencies_hz[peak_index]),
        float(np.max(np.abs(transient.displacement[:, 3 * monitor + 1]))),
        float(np.max(np.abs(transient.velocity[:, 3 * monitor + 1]))),
        float(np.max(np.abs(transient.acceleration[:, 3 * monitor + 1]))),
        signals["displacement"].spectrum.processed_metrics.rms,
        signals["acceleration"].spectrum.processed_metrics.rms,
        signals["displacement"].spectrum.dominant_frequency_hz,
        signals["acceleration"].spectrum.dominant_frequency_hz,
        float(energy[-1] / total_at_pulse_end) if total_at_pulse_end else 0,
        transient.relative_energy_error,
        float(np.max(np.abs(transient.reactions[:, :2]))),
        abs(float(static.displacement[-1, 1]) / exact_tip - 1),
        abs(float(modal.frequencies_hz[0]) / exact_frequency - 1),
    )
    return DesignInvestigation(
        design,
        model,
        static,
        modal,
        harmonic_config,
        harmonic,
        transient_config,
        transient,
        signals,
        summary,
    )


def controlled_variations(
    design: SupportDesign, config: NVHConfig, reference: DesignSummary
) -> tuple[ParameterVariation, ...]:
    rows = []
    for parameter in ("length", "width", "height", "young_modulus", "density"):
        for multiplier in (0.9, 1.1):
            changed = SupportDesign(
                **(design.model_dump() | {parameter: getattr(design, parameter) * multiplier})
            )
            model = support_model(changed, config.elements, config.static_force_N)
            static = solve_static(model)
            modal = solve_modal(model, AnalysisConfig(modes=1))
            frequency = float(modal.frequencies_hz[0])
            expected_frequency = {
                "length": multiplier**-2,
                "width": 1.0,
                "height": multiplier,
                "young_modulus": multiplier**0.5,
                "density": multiplier**-0.5,
            }[parameter]
            expected_static = {
                "length": multiplier**3,
                "width": 1 / multiplier,
                "height": multiplier**-3,
                "young_modulus": 1 / multiplier,
                "density": 1.0,
            }[parameter]
            rows.append(
                ParameterVariation(
                    parameter,
                    multiplier,
                    frequency,
                    frequency / reference.first_natural_hz,
                    float(static.displacement[-1, 1]),
                    abs(float(static.displacement[-1, 1])) / reference.maximum_static_translation_m,
                    changed.structural_mass / design.structural_mass,
                    expected_frequency,
                    expected_static,
                )
            )
    return tuple(rows)


def harmonic_sensitivities(
    investigation: DesignInvestigation, config: NVHConfig
) -> tuple[Sensitivity, ...]:
    rows = []
    # Vary coefficients together, holding geometry/loads/observation fixed.
    cases: list[tuple[float, Location, Location, float]] = [
        (0.5, config.excitation_fraction, config.monitor_fraction, 1.0),
        (1.0, config.excitation_fraction, config.monitor_fraction, 1.0),
        (2.0, config.excitation_fraction, config.monitor_fraction, 1.0),
        (1.0, 0.5, 1.0, 1.0),
        (1.0, 1.0, 0.5, 1.0),
        (1.0, config.excitation_fraction, config.monitor_fraction, 0.9),
        (1.0, config.excitation_fraction, config.monitor_fraction, 1.1),
    ]
    for multiplier, excitation, monitor, e_factor in cases:
        model = investigation.model
        if e_factor != 1:
            design = SupportDesign(
                **(
                    investigation.design.model_dump()
                    | {
                        "young_modulus": investigation.design.young_modulus * e_factor,
                    }
                )
            )
            model = support_model(design, config.elements, config.static_force_N)
        damping = Damping(
            kind="rayleigh",
            alpha=config.damping.alpha * multiplier,
            beta=config.damping.beta * multiplier,
        )
        case = harmonic_case(config, model, damping, excitation)
        result = solve_harmonic(model, case)
        node = int(len(investigation.model.elements) * monitor)
        column = result.response_dofs.index(ResponseDOF(node=node))
        operating = int(np.argmin(np.abs(result.frequencies_hz - config.operating_frequency_hz)))
        maximum = int(np.argmax(result.response_amplitude[:, column]))
        rows.append(
            Sensitivity(
                multiplier,
                excitation,
                monitor,
                float(result.response_amplitude[operating, column]),
                float(result.response_amplitude[maximum, column]),
                float(result.frequencies_hz[maximum]),
                e_factor,
                float(result.natural_frequencies_hz[0]),
            )
        )
    return tuple(rows)


def convergence_study(investigation: DesignInvestigation, config: NVHConfig) -> StudyConvergence:
    """Compare common physical timestamps; finest differences are not exact errors.

    Fine-mesh/time runs are reduced immediately to common-grid monitored histories and
    diagnostics, avoiding retention of large global convergence histories.
    """
    cache: dict[tuple[int, int], tuple[Matrix, Matrix, Matrix, float, float, float, float]] = {}
    for elements, divisor in sorted(
        {(config.elements, 1), (config.elements, 2), (config.elements, 4), (4, 4), (8, 4), (16, 4)}
    ):
        if elements == config.elements and divisor == 1:
            result = investigation.transient
        else:
            model = support_model(investigation.design, elements, config.static_force_N)
            result = solve_transient(
                model, transient_case(config, model, config.grid.time_step / divisor)
            )
        index = 3 * int(elements * config.monitor_fraction) + 1
        cache[(elements, divisor)] = (
            result.displacement[::divisor, index].copy(),
            result.velocity[::divisor, index].copy(),
            result.acceleration[::divisor, index].copy(),
            float(np.max(np.abs(result.displacement[:, index]))),
            float(np.max(np.abs(result.acceleration[:, index]))),
            result.relative_energy_error,
            float(result.backward_errors.max()),
        )

    def row(elements: int, divisor: int, reference_key: tuple[int, int]) -> ConvergencePoint:
        values, velocities, accelerations, peak, peak_a, energy_error, backward = cache[
            (elements, divisor)
        ]
        reference, reference_v, reference_a, *_ = cache[reference_key]

        def difference(history: Matrix, reference: Matrix) -> float:
            scale = float(np.max(np.abs(reference)))
            return float(np.max(np.abs(history - reference)) / scale) if scale else 0.0

        return ConvergencePoint(
            elements,
            config.grid.time_step / divisor,
            peak,
            peak_a,
            difference(velocities, reference_v),
            difference(accelerations, reference_a),
            difference(values, reference),
            energy_error,
            backward,
        )

    time = tuple(row(config.elements, divisor, (config.elements, 4)) for divisor in (1, 2, 4))
    mesh = tuple(row(elements, 4, (16, 4)) for elements in (4, 8, 16))
    return StudyConvergence(investigation.design.name, time, mesh)


def run_nvh_study(config: NVHConfig | None = None) -> NVHStudy:
    config = config or NVHConfig()
    baseline, modified = (
        investigate_design(config.baseline, config),
        investigate_design(config.modified, config),
    )
    parameters = controlled_variations(config.baseline, config, baseline.summary)
    convergence = (convergence_study(baseline, config), convergence_study(modified, config))
    checks = {
        "static_force_moment_equilibrium": all(
            max(abs(v) for v in item.summary.equilibrium_residual_N_Nm) < 1e-5
            for item in (baseline, modified)
        ),
        "static_analytical_cantilever": all(
            item.summary.static_tip_relative_analytical_error < 1e-7
            for item in (baseline, modified)
        ),
        "first_modal_analytical_cantilever": all(
            item.summary.first_frequency_relative_analytical_error < 1e-3
            for item in (baseline, modified)
        ),
        "controlled_frequency_scaling": all(
            abs(row.first_frequency_ratio / row.expected_frequency_ratio - 1) < 1e-6
            for row in parameters
        ),
        "controlled_static_scaling": all(
            abs(row.static_tip_ratio / row.expected_static_ratio - 1) < 1e-7 for row in parameters
        ),
        "transient_energy_balance": all(
            item.summary.relative_energy_balance_error < 1e-8 for item in (baseline, modified)
        ),
        "base_step_monitored_displacement_difference_below_one_percent": all(
            c.time[0].relative_difference_from_finest < 0.01 for c in convergence
        ),
        "selected_mesh_monitored_displacement_difference_below_one_percent": all(
            next(p for p in c.mesh if p.elements == config.elements).relative_difference_from_finest
            < 0.01
            for c in convergence
        ),
    }
    checks["base_step_acceleration_difference_below_five_percent"] = all(
        c.time[0].relative_acceleration_difference_from_finest < 0.05 for c in convergence
    )
    checks["selected_mesh_acceleration_difference_below_one_percent"] = all(
        next(
            p for p in c.mesh if p.elements == config.elements
        ).relative_acceleration_difference_from_finest
        < 0.01
        for c in convergence
    )
    sensitivities = {
        "baseline": harmonic_sensitivities(baseline, config),
        "modified": harmonic_sensitivities(modified, config),
    }
    return NVHStudy(config, baseline, modified, parameters, sensitivities, convergence, checks)
