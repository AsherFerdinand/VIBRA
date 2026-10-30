"""Independent physical identities and all-solver attachment integration."""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError

from vibra.core.assembly import assemble
from vibra.core.attachments import mount_forces
from vibra.core.dynamic_models import ResponseDOF
from vibra.core.errors import EngineeringError
from vibra.core.models import (
    DOF,
    AnalysisConfig,
    Constraint,
    FrameModel,
    LinearMount,
    NodalMass,
    Node,
)
from vibra.solvers.harmonic import HarmonicConfig, HarmonicLoad, solve_harmonic
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.solvers.transient import InitialValue, TimeGrid, TransientConfig, solve_transient
from vibra.studies.installed import (
    InstalledConfig,
    InstalledStudy,
    installed_model,
    run_installed_study,
)
from vibra.verification.installed_benchmarks import oscillator, verification_report


def test_analytical_verification() -> None:
    report = verification_report()
    assert report["all_passed"], report
    assert not report["experimental_validation"]


def test_offset_inertia_and_admissibility() -> None:
    mass = 5.0
    inertia = 0.4
    x = 0.2
    y = 0.3
    model = FrameModel(
        nodes=(Node(id=8, x=1, y=2),),
        nodal_masses=(NodalMass(node=8, mass=mass, inertia_z=inertia, offset=(x, y)),),
    )
    m = assemble(model).mass
    assert_allclose(
        m,
        [
            [mass, 0, -mass * y],
            [0, mass, mass * x],
            [-mass * y, mass * x, inertia + mass * (x * x + y * y)],
        ],
    )
    assert np.linalg.eigvalsh(m).min() > 0
    for seed in range(4):
        v = np.random.default_rng(seed).normal(size=3)
        expected = (
            0.5 * mass * ((v[0] - y * v[2]) ** 2 + (v[1] + x * v[2]) ** 2)
            + 0.5 * inertia * v[2] ** 2
        )
        assert_allclose(0.5 * v @ m @ v, expected, rtol=1e-14)
    point = FrameModel(
        nodes=model.nodes, nodal_masses=(NodalMass(node=8, mass=mass, offset=(x, y)),)
    )
    assert np.linalg.eigvalsh(assemble(point).mass).min() > -1e-14


def test_rotated_relative_spring_rigid_motion_and_ground_recovery() -> None:
    # Two reference nodes with the same physical attachment point at (1,1).
    mount = LinearMount(
        id=0,
        node_a=3,
        node_b=7,
        angle_degrees=30,
        stiffness=500,
        damping=8,
        offset_a=(1, 1),
        offset_b=(0, 1),
    )
    model = FrameModel(nodes=(Node(id=3, x=0, y=0), Node(id=7, x=1, y=0)), mounts=(mount,))
    a = assemble(model)
    for matrix in (a.stiffness, a.mount_damping):
        assert_allclose(matrix, matrix.T, atol=0)
        assert np.linalg.eigvalsh(matrix).min() > -1e-12
    rigid = np.array([0.2, 0.3, 0.4, 0.2, 0.7, 0.4])
    assert_allclose(a.mounts[0].extension @ rigid, 0, atol=1e-15)
    q = np.arange(6, dtype=np.float64) * 0.01
    n = np.array([np.cos(np.pi / 6), np.sin(np.pi / 6)])
    point_a = q[:2] + q[2] * np.array([-1, 1])
    point_b = q[3:5] + q[5] * np.array([-1, 0])
    delta = n @ (point_a - point_b)
    assert_allclose(0.5 * q @ a.stiffness @ q, 0.5 * 500 * delta**2)
    assert_allclose(mount_forces(a, q, q), [float((500 + 8) * delta)])
    ground = oscillator(3)
    result = solve_static(ground)
    a = assemble(ground)
    force = mount_forces(a, result.displacement.reshape(-1), np.zeros(3))
    assert_allclose(force, [10])
    assert_allclose(result.reactions, 0)
    # A grounded spring carries support force outside fixed-DOF reactions.
    assert_allclose(-force[0] + ground.loads[0].fy, 0)


def test_coupled_translation_rotation_independent_eigenvalues() -> None:
    m, j, y, k, kr = 3.0, 0.2, 0.25, 900.0, 120.0
    model = FrameModel(
        nodes=(Node(id=0, x=0, y=0),),
        nodal_masses=(NodalMass(node=0, mass=m, inertia_z=j, offset=(0, y)),),
        mounts=(
            LinearMount(id=0, node_a=0, angle_degrees=0, stiffness=k),
            LinearMount(id=1, node_a=0, stiffness=kr / 2, offset_a=(1, 0)),
            LinearMount(id=2, node_a=0, stiffness=kr / 2, offset_a=(-1, 0)),
        ),
        constraints=(Constraint(node=0, dof=DOF.UY),),
    )
    # det(K-lambda*M)=m*j*lambda²-[k*(j+m*y²)+kr*m]*lambda+k*kr.
    b = k * (j + m * y * y) + kr * m
    roots = np.array(
        [
            (b - np.sqrt(b * b - 4 * m * j * k * kr)) / (2 * m * j),
            (b + np.sqrt(b * b - 4 * m * j * k * kr)) / (2 * m * j),
        ]
    )
    result = solve_modal(model, AnalysisConfig(modes=2))
    assert_allclose(result.eigenvalues, roots, rtol=1e-12)
    matrix = assemble(model).mass
    assert_allclose(result.modes.T @ matrix @ result.modes, np.eye(2), atol=1e-13)


def test_nonproportional_damping_and_constraints() -> None:
    # A two-mass relative isolator with one grounded spring; damping only in isolator.
    model = FrameModel(
        nodes=(Node(id=0, x=0, y=0), Node(id=1, x=0, y=0)),
        nodal_masses=(NodalMass(node=0, mass=2), NodalMass(node=1, mass=3)),
        mounts=(
            LinearMount(id=0, node_a=0, stiffness=1000),
            LinearMount(id=1, node_a=1, node_b=0, stiffness=600, damping=7),
        ),
        constraints=tuple(Constraint(node=n, dof=d) for n in (0, 1) for d in (DOF.UX, DOF.RZ)),
    )
    a = assemble(model)
    f = np.array([0, 10.0])
    indices = [1, 4]
    h = solve_harmonic(
        model,
        HarmonicConfig(
            frequencies_hz=(2.0,),
            loads=(HarmonicLoad(node=1, amplitude=10),),
            responses=(ResponseDOF(node=0), ResponseDOF(node=1)),
        ),
    )
    omega = 4 * np.pi
    exact = np.linalg.solve(
        np.array([[1600, -600], [-600, 600]])
        - omega**2 * np.diag([2, 3])
        + 1j * omega * 7 * np.array([[1, -1], [-1, 1]]),
        f,
    )
    assert_allclose(h.displacement[0, indices], exact, rtol=1e-12)
    modes = solve_modal(model, AnalysisConfig(modes=2))
    modal_c = modes.modes.T @ a.mount_damping @ modes.modes
    assert abs(modal_c[0, 1]) > 0.01
    assert_allclose(
        h.modal_damping_ratios, np.diag(modal_c) / (2 * modes.angular_frequencies), rtol=1e-12
    )
    t = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.5, time_step=0.0005),
            responses=(ResponseDOF(node=1),),
            initial_displacement=(InitialValue(node=1, value=0.01),),
        ),
    )
    assert_allclose(t.displacement[:, a.fixed], 0, atol=0)
    assert_allclose(t.velocity[:, a.fixed], 0, atol=0)
    assert_allclose(t.acceleration[:, a.fixed], 0, atol=0)
    assert t.relative_energy_error < 1e-10
    assert t.damping_dissipation[-1] > 0
    assert np.max(np.diff(t.kinetic_energy + t.strain_energy)) < 1e-12
    # Zero-force state and assembled dynamic residual at free DOFs.
    residual = (
        t.acceleration @ a.mass.T + t.velocity @ a.mount_damping.T + t.displacement @ a.stiffness.T
    )
    assert_allclose(residual[:, a.free], 0, atol=1e-9)
    zero = solve_transient(
        model,
        TransientConfig(
            grid=TimeGrid(duration=0.01, time_step=0.001), responses=(ResponseDOF(node=1),)
        ),
    )
    assert_allclose(zero.displacement, 0, atol=0)


def test_zero_and_rigid_mount_limits() -> None:
    # Ground spring in parallel with an already stable rail; zero is exactly the base model.
    config = InstalledConfig()
    base, tip = installed_model(config, "bare")
    zero = FrameModel(**(base.model_dump() | {"mounts": (LinearMount(id=0, node_a=tip),)}))
    assert_allclose(assemble(zero).stiffness, assemble(base).stiffness, atol=0)
    for stiffness in (1e3, 1e6, 1e9):
        model = FrameModel(
            **(
                base.model_dump()
                | {"mounts": (LinearMount(id=0, node_a=tip, stiffness=stiffness),)}
            )
        )
        # Exact tip compliance of beam and grounded spring in parallel.
        beam_k = (
            3
            * config.rail.young_modulus
            * base.elements[0].section.second_moment
            / config.rail.length**3
        )
        assert_allclose(
            solve_static(model).displacement[-1, 1],
            config.static_force_N / (beam_k + stiffness),
            rtol=1e-9,
        )
    # Free disconnected inertia is explicitly rejected by solvers, no stiffness shift.
    with pytest.raises(EngineeringError):
        solve_modal(oscillator(stiffness=0), AnalysisConfig(modes=1))
    values = []
    rigid, _ = installed_model(config, "rigid")
    reference = solve_modal(rigid, AnalysisConfig(modes=1)).frequencies_hz[0]
    for multiplier in (1, 100, 10000):
        changed = InstalledConfig(
            **(
                config.model_dump()
                | dict(
                    stiffness_x_N_per_m=config.stiffness_x_N_per_m * multiplier,
                    stiffness_y_N_per_m=config.stiffness_y_N_per_m * multiplier,
                )
            )
        )
        model, _ = installed_model(changed, "isolated")
        values.append(
            abs(solve_modal(model, AnalysisConfig(modes=1)).frequencies_hz[0] / reference - 1)
        )
    assert values[2] < values[1] < values[0]
    assert values[-1] < 2e-5


@pytest.fixture(scope="module")
def installed() -> InstalledStudy:
    return run_installed_study()


def test_study_topology_mass_consistency_and_transmission(installed: InstalledStudy) -> None:
    assert all(installed.checks.values())
    for case in installed.cases:
        a = assemble(case.model)
        translation = np.zeros(len(a.force))
        translation[::3] = 1
        expected = installed.config.rail.structural_mass + (
            0 if case.topology == "bare" else installed.config.motor_mass_kg
        )
        assert_allclose(translation @ a.mass @ translation, expected, rtol=1e-13)
        assert case.summary["static_root_balance_N"] < 1e-6
        assert case.transient.relative_energy_error < 1e-8
    bare, rigid, isolated = installed.cases
    assert rigid.modal.frequencies_hz[0] < bare.modal.frequencies_hz[0]
    assert (
        isolated.summary["static_interface_displacement_m"]
        > rigid.summary["static_interface_displacement_m"]
    )
    assert all(m.node_b == installed.config.elements for m in isolated.model.mounts)
    # Motor force balance: applied force minus vertical inertia = rail transmission.
    h = isolated.harmonic
    omega = 2 * np.pi * h.frequencies_hz
    expected_harmonic = (
        installed.config.harmonic_force_N
        + installed.config.motor_mass_kg * omega**2 * h.displacement[:, 3 * isolated.force_node + 1]
    )
    assert_allclose(isolated.harmonic_transmitted_force_N, expected_harmonic, rtol=1e-8, atol=1e-9)
    t = isolated.transient
    expected_t = (
        t.force_right[:, 3 * isolated.force_node + 1]
        - installed.config.motor_mass_kg * t.acceleration[:, 3 * isolated.force_node + 1]
    )
    assert_allclose(isolated.transient_transmitted_force_N, expected_t, rtol=1e-8, atol=1e-8)


@pytest.mark.parametrize(
    "data",
    [
        {"mass": -1},
        {"mass": 0},
        {"mass": 1, "inertia_z": -1},
        {"mass": float("nan")},
        {"mass": 1, "offset": (float("inf"), 0)},
        {"mass": 0, "inertia_z": 1, "offset": (1, 0)},
    ],
)
def test_invalid_inertia(data: dict[str, object]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        NodalMass.model_validate({"node": 0} | data)


@pytest.mark.parametrize(
    "data",
    [
        {"stiffness": -1},
        {"damping": -1},
        {"angle_degrees": float("nan")},
        {"node_b": 0},
        {"offset_b": (1, 0)},
    ],
)
def test_invalid_mount(data: dict[str, object]) -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        LinearMount.model_validate({"id": 0, "node_a": 0} | data)


def test_unknown_attachments() -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        FrameModel(nodes=(Node(id=0, x=0, y=0),), nodal_masses=(NodalMass(node=1, mass=1),))
    with pytest.raises((ValidationError, EngineeringError)):
        FrameModel(nodes=(Node(id=0, x=0, y=0),), mounts=(LinearMount(id=0, node_a=0, node_b=2),))


def test_report_integrity_and_repeatability(installed: InstalledStudy) -> None:
    import json

    from vibra.io.installed_report import installed_json, installed_markdown
    from vibra.studies.installed import investigate

    repeated = investigate(installed.config, "isolated")
    assert_allclose(
        repeated.harmonic.displacement,
        installed.cases[2].harmonic.displacement,
        rtol=1e-11,
        atol=1e-14,
    )
    assert_allclose(
        repeated.transient.displacement,
        installed.cases[2].transient.displacement,
        rtol=1e-11,
        atol=1e-14,
    )
    text = installed_json(installed)
    report = json.loads(text)
    assert len(text.encode()) < 25_000_000
    assert report["inputs"]["motor_mass_kg"] == 12
    cases = report["results"]["cases"]
    assert len(cases["isolated"]["model"]["nodal_masses"]) == 1
    assert len(cases["isolated"]["model"]["mounts"]) == 4
    assert cases["rigid"]["model"]["nodal_masses"][0]["offset"] == [0, 0.08]
    for case in cases.values():
        assert len(case["transient"]["results"]["time_s"]) <= 501
        assert not case["harmonic"]["results"]["numerical_verification"]["experimental_validation"]
    assert "universally optimal" in installed_markdown(installed)
    assert all(report["results"]["checks"].values())


def test_mount_damped_time_step_convergence() -> None:
    from vibra.verification.transient_analytical import free_sdof

    errors = []
    for step in (0.002, 0.001, 0.0005):
        t = solve_transient(
            oscillator(3),
            TransientConfig(
                grid=TimeGrid(duration=1, time_step=step),
                responses=(ResponseDOF(node=0),),
                initial_displacement=(InitialValue(node=0, value=0.01),),
            ),
        )
        exact, _, _ = free_sdof(t.time, 2, 800, 3, 0.01, 0)
        errors.append(float(np.max(abs(t.displacement[:, 1] - exact))))
    assert errors[0] / errors[1] > 3.9
    assert errors[1] / errors[2] > 3.9


def test_nonobjective_attachment_geometry_rejected() -> None:
    with pytest.raises((ValidationError, EngineeringError)):
        FrameModel(
            nodes=(Node(id=0, x=0, y=0), Node(id=1, x=1, y=0)),
            mounts=(LinearMount(id=0, node_a=0, node_b=1, angle_degrees=90, stiffness=1),),
        )
