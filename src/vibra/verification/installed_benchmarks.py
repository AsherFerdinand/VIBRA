"""Independent inertia, spring, continuum tip-mass and viscous response references."""

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import brentq

from vibra.core.assembly import assemble
from vibra.core.dynamic_models import ResponseDOF
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import (
    DOF,
    AnalysisConfig,
    Constraint,
    FrameModel,
    LinearMount,
    Material,
    NodalLoad,
    NodalMass,
    Node,
    Rectangle,
)
from vibra.dynamics.forcing import HarmonicForce
from vibra.solvers.harmonic import HarmonicConfig, HarmonicLoad, solve_harmonic
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.solvers.transient import InitialValue, TimeGrid, TransientConfig, solve_transient
from vibra.verification.transient_analytical import forced_cosine_sdof, free_sdof


def oscillator(damping: float = 0, stiffness: float = 800) -> FrameModel:
    return FrameModel(
        nodes=(Node(id=0, x=0, y=0),),
        nodal_masses=(NodalMass(node=0, mass=2, inertia_z=0.15),),
        mounts=(LinearMount(id=0, node_a=0, stiffness=stiffness, damping=damping),),
        constraints=(Constraint(node=0, dof=DOF.UX), Constraint(node=0, dof=DOF.RZ)),
        loads=(NodalLoad(node=0, fy=10),),
    )


def verification_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    def add(name: str, error: float, tolerance: float) -> None:
        rows.append(
            dict(
                name=name,
                error=float(error),
                tolerance=tolerance,
                passed=bool(np.isfinite(error) and error < tolerance),
            )
        )

    model = oscillator(3)
    add(
        "mass_spring_frequency_relative",
        abs(solve_modal(model, AnalysisConfig(modes=1)).frequencies_hz[0] / (20 / (2 * np.pi)) - 1),
        1e-12,
    )
    add(
        "static_spring_displacement_relative",
        abs(solve_static(model).displacement[0, 1] / (10 / 800) - 1),
        1e-12,
    )
    harmonic = solve_harmonic(
        model,
        HarmonicConfig(
            frequencies_hz=(1, 3, 10),
            loads=(HarmonicLoad(node=0, amplitude=10),),
            responses=(ResponseDOF(node=0),),
        ),
    )
    omega = 2 * np.pi * harmonic.frequencies_hz
    exact = 10 / (800 - 2 * omega**2 + 1j * 3 * omega)
    add(
        "mount_damped_complex_harmonic_relative",
        np.max(np.abs(harmonic.displacement[:, 1] - exact)) / np.max(np.abs(exact)),
        1e-12,
    )
    for damping in (0.0, 3.0):
        model = oscillator(damping)
        result = solve_transient(
            model,
            TransientConfig(
                grid=TimeGrid(duration=1, time_step=0.0005),
                responses=(ResponseDOF(node=0),),
                initial_displacement=(InitialValue(node=0, value=0.01),),
            ),
        )
        exact_x, _, _ = free_sdof(result.time, 2, 800, damping, 0.01, 0)
        add(
            f"free_decay_c{damping}_relative",
            np.max(np.abs(result.response_displacement[:, 0] - exact_x)) / 0.01,
            2e-4,
        )
        add(f"discrete_energy_c{damping}_relative", result.relative_energy_error, 1e-9)
        energy = result.kinetic_energy + result.strain_energy
        if damping:
            add("damped_energy_increase_J", max(0, float(np.max(np.diff(energy)))), 1e-12)
        else:
            add("conservative_energy_relative", np.max(np.abs(energy / energy[0] - 1)), 1e-9)
    model = oscillator(3)
    forced = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=1, time_step=0.0005),
            responses=(ResponseDOF(node=0),),
            loads=(HarmonicForce(node=0, amplitude=10, frequency_hz=4),),
        ),
    )
    exact_x, _, _ = forced_cosine_sdof(forced.time, 2, 800, 3, 10, 8 * np.pi)
    add(
        "mount_damped_forced_transient_relative",
        np.max(np.abs(forced.response_displacement[:, 0] - exact_x)) / np.max(np.abs(exact_x)),
        3e-4,
    )
    # Independent rigid-body kinetic-energy identity, including offset cross terms.
    body = NodalMass(node=0, mass=4, inertia_z=0.7, offset=(0.3, -0.2))
    rigid = FrameModel(nodes=(Node(id=0, x=0, y=0),), nodal_masses=(body,))
    matrix = assemble(rigid).mass
    q = np.array([0.2, -0.1, 0.8])
    vx, vy, w = q
    exact_energy = 0.5 * 4 * ((vx + 0.2 * w) ** 2 + (vy + 0.3 * w) ** 2) + 0.5 * 0.7 * w * w
    add(
        "offset_inertia_kinetic_energy_relative",
        abs(0.5 * q @ matrix @ q / exact_energy - 1),
        1e-12,
    )
    add("offset_mass_symmetry", np.max(np.abs(matrix - matrix.T)), 1e-14)
    # Pure rotational oscillator: two vertical springs at +/-a, ktheta=2*k*a².
    a = 0.2
    k = 1000
    inertia = 0.4
    rotation = FrameModel(
        nodes=(Node(id=0, x=0, y=0),),
        nodal_masses=(NodalMass(node=0, mass=2, inertia_z=inertia),),
        mounts=tuple(
            LinearMount(id=i, node_a=0, stiffness=k, offset_a=(x, 0)) for i, x in enumerate((-a, a))
        ),
        constraints=(Constraint(node=0, dof=DOF.UX), Constraint(node=0, dof=DOF.UY)),
    )
    add(
        "rotational_inertia_frequency_relative",
        abs(
            solve_modal(rotation, AnalysisConfig(modes=1)).angular_frequencies[0]
            / np.sqrt(2 * k * a * a / inertia)
            - 1
        ),
        1e-12,
    )
    # Coupled reference translation/rotation: analytic roots of the 2x2 determinant.
    m, j, y, kx, kr = 3.0, 0.2, 0.25, 900.0, 120.0
    coupled = FrameModel(
        nodes=(Node(id=0, x=0, y=0),),
        nodal_masses=(NodalMass(node=0, mass=m, inertia_z=j, offset=(0, y)),),
        mounts=(
            LinearMount(id=0, node_a=0, angle_degrees=0, stiffness=kx),
            LinearMount(id=1, node_a=0, stiffness=kr / 2, offset_a=(1, 0)),
            LinearMount(id=2, node_a=0, stiffness=kr / 2, offset_a=(-1, 0)),
        ),
        constraints=(Constraint(node=0, dof=DOF.UY),),
    )
    b = kx * (j + m * y * y) + kr * m
    exact_roots = np.array(
        [
            (b - np.sqrt(b * b - 4 * m * j * kx * kr)) / (2 * m * j),
            (b + np.sqrt(b * b - 4 * m * j * kx * kr)) / (2 * m * j),
        ]
    )
    actual = solve_modal(coupled, AnalysisConfig(modes=2)).eigenvalues
    add("coupled_inertia_eigenvalues_relative", np.max(abs(actual / exact_roots - 1)), 1e-12)
    coupled_assembly = assemble(coupled)
    add(
        "stiffness_symmetry",
        np.max(abs(coupled_assembly.stiffness - coupled_assembly.stiffness.T)),
        1e-14,
    )
    add(
        "mount_damping_symmetry",
        np.max(abs(coupled_assembly.mount_damping - coupled_assembly.mount_damping.T)),
        1e-14,
    )
    add(
        "coupled_mass_positive_definite",
        float(np.linalg.eigvalsh(coupled_assembly.mass).min() <= 0),
        0.5,
    )
    add(
        "mount_stiffness_semidefinite",
        float(np.linalg.eigvalsh(coupled_assembly.stiffness).min() < -1e-12),
        0.5,
    )
    # Continuum characteristic equation for cantilever with point tip mass (no J).
    geometry = BeamGeometry(length=1)
    material = Material(young_modulus=210e9, density=7850)
    section = Rectangle(width=0.02, height=0.02).section()
    tip_mass = 2.0
    mu = tip_mass / (material.density * section.area * geometry.length)
    root = brentq(
        lambda b: (
            1 + np.cos(b) * np.cosh(b) + mu * b * (np.cos(b) * np.sinh(b) - np.sin(b) * np.cosh(b))
        ),
        0.1,
        1.8752,
    )
    exact_f = (
        root**2
        / (2 * np.pi)
        * np.sqrt(
            material.young_modulus
            * section.second_moment
            / (material.density * section.area * geometry.length**4)
        )
    )
    for count in (4, 8, 16):
        beam = cantilever(geometry, material, section, count)
        beam = FrameModel(
            **(beam.model_dump() | {"nodal_masses": (NodalMass(node=count, mass=tip_mass),)})
        )
        add(
            f"continuum_tip_mass_{count}_elements_relative",
            abs(solve_modal(beam, AnalysisConfig(modes=1)).frequencies_hz[0] / exact_f - 1),
            1e-5,
        )
    return dict(
        analysis="Installed inertia and mount analytical verification",
        experimental_validation=False,
        ansys_correlation=False,
        checks=rows,
        all_passed=all(row["passed"] for row in rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/installed-verification.json")
    )
    args = parser.parse_args()
    report = verification_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
