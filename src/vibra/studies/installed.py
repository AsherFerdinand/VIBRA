"""Installed motor study using exact planar rigid kinematics and relative isolators."""

from dataclasses import dataclass
from typing import Literal, Self

import numpy as np
from pydantic import Field, model_validator

from vibra.core.assembly import assemble
from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError
from vibra.core.models import (
    AnalysisConfig,
    EngineeringModel,
    FrameModel,
    LinearMount,
    NodalLoad,
    NodalMass,
    Node,
)
from vibra.dynamics.forcing import PulseForce
from vibra.solvers.harmonic import (
    ComplexMatrix,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    HarmonicResult,
    solve_harmonic,
)
from vibra.solvers.modal import ModalResult, solve_modal
from vibra.solvers.static import StaticResult, solve_static
from vibra.solvers.transient import TimeGrid, TransientConfig, TransientResult, solve_transient
from vibra.studies.nvh import SupportDesign, support_model

Topology = Literal["bare", "rigid", "isolated"]


class InstalledConfig(EngineeringModel):
    rail: SupportDesign = Field(default_factory=SupportDesign)
    elements: Literal[4, 8, 16] = 8
    motor_mass_kg: float = Field(default=12, gt=0)
    motor_inertia_kg_m2: float = Field(default=0.08, gt=0)
    motor_height_m: float = Field(default=0.08, ge=0)
    mount_span_m: float = Field(default=0.12, gt=0)
    stiffness_x_N_per_m: float = Field(default=200000, gt=0)
    stiffness_y_N_per_m: float = Field(default=80000, gt=0)
    damping_x_Ns_per_m: float = Field(default=30, ge=0)
    damping_y_Ns_per_m: float = Field(default=60, ge=0)
    stiffness_beta_s: float = Field(default=8e-5, gt=0)
    static_force_N: float = -200
    harmonic_force_N: float = Field(default=2, gt=0)
    operating_hz: float = Field(default=60, gt=0)
    sweep: FrequencySweep = Field(default_factory=lambda: FrequencySweep(stop_hz=120, points=601))
    pulse_force_N: float = -20
    pulse_width_s: float = Field(default=0.01, gt=0)
    grid: TimeGrid = Field(default_factory=lambda: TimeGrid(duration=0.8, time_step=0.0002))

    @model_validator(mode="after")
    def practical(self) -> Self:
        if (
            self.sweep.points > 1001
            or not self.sweep.start_hz <= self.operating_hz <= self.sweep.stop_hz
        ):
            raise InvalidModelError("Include operating frequency; at most 1001 sweep points.")
        if self.grid.duration / self.grid.time_step > 6250:
            raise InvalidModelError("Installed study supports at most 6250 base intervals.")
        if not 10 * self.grid.time_step <= self.pulse_width_s < self.grid.duration / 2:
            raise InvalidModelError("Pulse needs >=10 intervals and must end before half the run.")
        if (
            abs(
                self.pulse_width_s / self.grid.time_step
                - round(self.pulse_width_s / self.grid.time_step)
            )
            > 1e-8
        ):
            raise InvalidModelError("Pulse end must align with time grid.")
        if self.static_force_N == 0 or self.pulse_force_N == 0:
            raise InvalidModelError("Study needs nonzero static and pulse forces.")
        return self

    @property
    def damping(self) -> Damping:
        return Damping(kind="stiffness", beta=self.stiffness_beta_s)


def installed_model(config: InstalledConfig, topology: Topology) -> tuple[FrameModel, int]:
    rail = support_model(config.rail, config.elements, config.static_force_N)
    tip = config.elements
    if topology == "bare":
        return rail, tip
    if topology == "rigid":
        return FrameModel(
            **(
                rail.model_dump()
                | {
                    "nodal_masses": (
                        NodalMass(
                            node=tip,
                            mass=config.motor_mass_kg,
                            inertia_z=config.motor_inertia_kg_m2,
                            offset=(0, config.motor_height_m),
                        ),
                    )
                }
            )
        ), tip
    if topology != "isolated":
        raise InvalidModelError("Unknown installed topology.")
    motor = tip + 1
    mounts = []
    # Both mount points share a massless rigid crossarm on the rail tip.
    for site, x in enumerate((-config.mount_span_m / 2, config.mount_span_m / 2)):
        for direction, angle, k, c in (
            (0, 0, config.stiffness_x_N_per_m, config.damping_x_Ns_per_m),
            (1, 90, config.stiffness_y_N_per_m, config.damping_y_Ns_per_m),
        ):
            mounts.append(
                LinearMount(
                    id=2 * site + direction,
                    node_a=motor,
                    node_b=tip,
                    angle_degrees=angle,
                    stiffness=k / 2,
                    damping=c / 2,
                    offset_a=(x, -config.motor_height_m),
                    offset_b=(x, 0),
                )
            )
    model = FrameModel(
        **(
            rail.model_dump()
            | dict(
                nodes=(*rail.nodes, Node(id=motor, x=config.rail.length, y=config.motor_height_m)),
                loads=(NodalLoad(node=motor, fy=config.static_force_N),),
                nodal_masses=(
                    NodalMass(
                        node=motor, mass=config.motor_mass_kg, inertia_z=config.motor_inertia_kg_m2
                    ),
                ),
                mounts=tuple(mounts),
            )
        )
    )
    return model, motor


@dataclass(frozen=True)
class InstalledCase:
    topology: Topology
    model: FrameModel
    force_node: int
    static: StaticResult
    modal: ModalResult
    harmonic_config: HarmonicConfig
    harmonic: HarmonicResult
    transient_config: TransientConfig
    transient: TransientResult
    harmonic_root_force_N: ComplexMatrix  # complex force on assembly at fixed root, global Y
    harmonic_transmitted_force_N: ComplexMatrix  # force on rail, Y; same excitation reference
    transient_transmitted_force_N: Matrix
    summary: dict[str, float]


@dataclass(frozen=True)
class InstalledStudy:
    config: InstalledConfig
    cases: tuple[InstalledCase, ...]
    sensitivities: tuple[dict[str, float | str], ...]
    convergence: tuple[dict[str, float | str], ...]
    checks: dict[str, bool]


def _harmonic(
    config: InstalledConfig, model: FrameModel, node: int
) -> tuple[HarmonicConfig, HarmonicResult]:
    frequencies = tuple(sorted(set((*config.sweep.frequencies(), config.operating_hz))))
    settings = HarmonicConfig(
        frequencies_hz=frequencies,
        damping=config.damping,
        loads=(HarmonicLoad(node=node, amplitude=config.harmonic_force_N),),
        responses=tuple(ResponseDOF(node=n) for n in sorted({node, config.elements})),
    )
    return settings, solve_harmonic(model, settings)


def _transient(
    config: InstalledConfig, model: FrameModel, node: int, divisor: int = 1
) -> tuple[TransientConfig, TransientResult]:
    settings = TransientConfig(
        grid=TimeGrid(duration=config.grid.duration, time_step=config.grid.time_step / divisor),
        damping=config.damping,
        loads=(
            PulseForce(node=node, amplitude=config.pulse_force_N, end_time=config.pulse_width_s),
        ),
        responses=tuple(ResponseDOF(node=n) for n in sorted({node, config.elements})),
    )
    return settings, solve_transient(model, settings)


def investigate(config: InstalledConfig, topology: Topology) -> InstalledCase:
    model, node = installed_model(config, topology)
    static = solve_static(model)
    modal = solve_modal(model, AnalysisConfig(modes=6))
    hc, h = _harmonic(config, model, node)
    tc, t = _transient(config, model, node)
    a = assemble(model)
    u = h.displacement
    omega = 2 * np.pi * h.frequencies_hz
    c = config.stiffness_beta_s * a.stiffness + a.mount_damping
    root = (
        u @ a.stiffness.T
        + 1j * omega[:, None] * (u @ c.T)
        - omega[:, None] ** 2 * (u @ a.mass.T)
        - h.force_phasor
    )[:, 1]
    transmitted = np.full(len(omega), complex(config.harmonic_force_N))
    transient_transmitted = t.force_right[:, 3 * node + 1].copy()
    if topology == "isolated":
        transmitted = np.zeros(len(omega), dtype=complex)
        transient_transmitted = np.zeros(len(t.time))
        for entry in a.mounts:
            if entry.mount.angle_degrees == 90:
                # Includes beta*K mount viscosity as well as the explicit dashpot.
                effective_c = entry.mount.damping + config.stiffness_beta_s * entry.mount.stiffness
                transmitted += (entry.mount.stiffness + 1j * omega * effective_c) * (
                    u @ entry.extension
                )
                transient_transmitted += entry.mount.stiffness * (
                    t.displacement @ entry.extension
                ) + effective_c * (t.velocity @ entry.extension)
    elif topology == "rigid":
        # COM vertical translation equals reference UY for the chosen purely Y offset.
        transmitted += config.motor_mass_kg * omega**2 * u[:, 3 * node + 1]
        transient_transmitted -= config.motor_mass_kg * t.acceleration[:, 3 * node + 1]
    op = int(np.argmin(abs(h.frequencies_hz - config.operating_hz)))
    summary = {
        "structural_mass_kg": config.rail.structural_mass,
        "additional_motor_mass_kg": 0.0 if topology == "bare" else config.motor_mass_kg,
        "static_interface_displacement_m": abs(float(static.displacement[node, 1])),
        "static_rail_tip_displacement_m": abs(float(static.displacement[config.elements, 1])),
        "first_natural_hz": float(modal.frequencies_hz[0]),
        "operating_interface_amplitude_m": float(abs(u[op, 3 * node + 1])),
        "operating_rail_amplitude_m": float(abs(u[op, 3 * config.elements + 1])),
        "operating_root_force_ratio": float(abs(root[op]) / config.harmonic_force_N),
        "operating_rail_transmitted_force_ratio": float(
            abs(transmitted[op]) / config.harmonic_force_N
        ),
        "pulse_peak_interface_displacement_m": float(abs(t.displacement[:, 3 * node + 1]).max()),
        "pulse_peak_interface_velocity_m_per_s": float(abs(t.velocity[:, 3 * node + 1]).max()),
        "pulse_peak_interface_acceleration_m_per_s2": float(
            abs(t.acceleration[:, 3 * node + 1]).max()
        ),
        "pulse_peak_root_force_N": float(abs(t.reactions[:, 1]).max()),
        "relative_energy_balance_error": t.relative_energy_error,
        "static_root_balance_N": abs(float(static.reactions[0, 1]) + config.static_force_N),
    }
    return InstalledCase(
        topology,
        model,
        node,
        static,
        modal,
        hc,
        h,
        tc,
        t,
        root,
        transmitted,
        transient_transmitted,
        summary,
    )


def run_installed_study(config: InstalledConfig | None = None) -> InstalledStudy:
    config = config or InstalledConfig()
    kinds: tuple[Topology, ...] = ("bare", "rigid", "isolated")
    cases = tuple(investigate(config, kind) for kind in kinds)
    sensitivities = []
    for parameter in (
        "motor_mass_kg",
        "motor_inertia_kg_m2",
        "stiffness_y_N_per_m",
        "damping_y_Ns_per_m",
    ):
        for factor in (0.5, 1.0, 2.0):
            changed = InstalledConfig(
                **(config.model_dump() | {parameter: getattr(config, parameter) * factor})
            )
            model, node = installed_model(changed, "isolated")
            _, h = _harmonic(changed, model, node)
            op = int(np.argmin(abs(h.frequencies_hz - config.operating_hz)))
            sensitivities.append(
                dict(
                    parameter=parameter,
                    factor=factor,
                    value=getattr(changed, parameter),
                    first_hz=float(h.natural_frequencies_hz[0]),
                    operating_rail_amplitude_m=float(
                        abs(h.displacement[op, 3 * config.elements + 1])
                    ),
                )
            )
    for factor in (0.9, 1.1):
        rail = SupportDesign(**(config.rail.model_dump() | {"height": config.rail.height * factor}))
        changed = InstalledConfig(**(config.model_dump() | {"rail": rail}))
        model, node = installed_model(changed, "isolated")
        _, h = _harmonic(changed, model, node)
        op = int(np.argmin(abs(h.frequencies_hz - config.operating_hz)))
        sensitivities.append(
            dict(
                parameter="rail_depth_m",
                factor=factor,
                value=rail.height,
                first_hz=float(h.natural_frequencies_hz[0]),
                operating_rail_amplitude_m=float(abs(h.displacement[op, 3 * config.elements + 1])),
            )
        )
    convergence: list[dict[str, float | str]] = []
    isolated = cases[2]
    coarse = isolated.transient.displacement[:, 3 * isolated.force_node + 1]
    _, fine = _transient(config, isolated.model, isolated.force_node, 2)
    time_diff = float(
        np.max(abs(coarse - fine.displacement[::2, 3 * isolated.force_node + 1]))
        / np.max(abs(fine.displacement[::2, 3 * isolated.force_node + 1]))
    )
    fine_config = InstalledConfig(**(config.model_dump() | {"elements": 16}))
    fine_model, fine_node = installed_model(fine_config, "isolated")
    _, fine_mesh = _transient(fine_config, fine_model, fine_node)
    mesh_diff = float(
        np.max(abs(coarse - fine_mesh.displacement[:, 3 * fine_node + 1]))
        / np.max(abs(fine_mesh.displacement[:, 3 * fine_node + 1]))
    )
    convergence.extend(
        (
            dict(
                kind="time dt vs dt/2, selected mesh",
                relative_monitored_displacement_difference=time_diff,
            ),
            dict(
                kind="selected mesh vs 16 elements, base dt",
                relative_monitored_displacement_difference=mesh_diff,
            ),
        )
    )
    checks = dict(
        static_equilibrium=all(case.summary["static_root_balance_N"] < 1e-6 for case in cases),
        energy_balance=all(case.transient.relative_energy_error < 1e-8 for case in cases),
        time_difference_below_one_percent=time_diff < 0.01,
        mesh_difference_below_one_percent=mesh_diff < 0.01,
    )
    return InstalledStudy(config, cases, tuple(sensitivities), tuple(convergence), checks)
