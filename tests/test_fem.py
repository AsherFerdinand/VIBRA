"""Independent mechanics benchmarks, algebraic invariants and invalid topology tests."""

import math

import numpy as np
import pytest
from numpy.testing import assert_allclose
from pydantic import ValidationError
from scipy import linalg

from vibra.core.assembly import assemble, constrained_system
from vibra.core.element import beam_matrices
from vibra.core.errors import InvalidModelError, SolverError, UnstableModelError
from vibra.core.mesh import BeamGeometry, cantilever
from vibra.core.models import (
    DOF,
    AnalysisConfig,
    BeamElement,
    Constraint,
    FrameModel,
    Material,
    NodalLoad,
    Node,
    Rectangle,
    Section,
)
from vibra.solvers.modal import solve_modal
from vibra.solvers.static import solve_static
from vibra.verification.analytical import cantilever_bending_hz, cantilever_tip
from vibra.verification.benchmarks import convergence_study, steel_case, verification_report


def beam(count: int = 8, angle: float = 0) -> FrameModel:
    geometry, material, rectangle = steel_case()
    return cantilever(
        BeamGeometry(length=geometry.length, angle_degrees=angle),
        material,
        rectangle.section(),
        count,
    )


def test_element_invariants_and_rigid_body_kinetic_energy() -> None:
    model = beam(1)
    matrices = beam_matrices(model.elements[0], model.nodes[0], model.nodes[1])
    k, m = matrices.stiffness, matrices.mass
    assert_allclose(k, k.T, atol=1e-12)
    assert_allclose(m, m.T, atol=1e-12)
    assert np.min(linalg.eigvalsh(m)) > 0
    length = matrices.length
    mass = model.elements[0].material.density * model.elements[0].section.area * length
    rigid_modes = [
        np.array([1, 0, 0, 1, 0, 0]),
        np.array([0, 1, 0, 0, 1, 0]),
        np.array([0, 0, 1, 0, length, 1]),
    ]
    for motion in rigid_modes:
        assert_allclose(k @ motion, 0, atol=1e-8)
    assert_allclose(rigid_modes[0] @ m @ rigid_modes[0], mass, rtol=1e-13)
    assert_allclose(rigid_modes[1] @ m @ rigid_modes[1], mass, rtol=1e-13)
    # ∫ρA x² dx about the first node, no cross-sectional rotary inertia in EB theory.
    assert_allclose(rigid_modes[2] @ m @ rigid_modes[2], mass * length**2 / 3, rtol=1e-13)
    diagonal = np.sqrt(np.diag(k))
    eigenvalues = linalg.eigvalsh(k / diagonal[:, None] / diagonal[None, :])
    assert np.sum(np.abs(eigenvalues) < 1e-12) == 3
    assert np.sum(eigenvalues > 1e-12) == 3


def test_constant_strain_energy_patch() -> None:
    model = beam(1)
    entry = assemble(model).elements[0]
    length = entry.matrices.length
    e = model.elements[0].material.young_modulus
    a, i = model.elements[0].section.area, model.elements[0].section.second_moment
    strain, curvature = 0.001, 0.002
    displacement = np.array(
        [0, 0, 0, strain * length, curvature * length**2 / 2, curvature * length]
    )
    energy = 0.5 * displacement @ entry.matrices.stiffness @ displacement
    exact = 0.5 * (e * a * strain**2 + e * i * curvature**2) * length
    assert_allclose(energy, exact, rtol=1e-12)


@pytest.mark.parametrize("count", [1, 2, 4, 16, 32])
@pytest.mark.parametrize("angle", [0, 37, 90])
def test_static_analytical_rotation_and_equilibrium(count: int, angle: float) -> None:
    model = beam(count, angle)
    geometry, material, rectangle = steel_case()
    expected_tip, expected_rotation = cantilever_tip(geometry, material, rectangle.section(), -100)
    result = solve_static(model)
    rad = math.radians(angle)
    transverse = np.array([-math.sin(rad), math.cos(rad)])
    assert_allclose(result.displacement[-1, :2], transverse * expected_tip, rtol=2e-7, atol=1e-10)
    assert_allclose(result.displacement[-1, 2], expected_rotation, rtol=2e-7)
    assert_allclose(result.reactions[0, :2], transverse * 100, atol=1e-5)
    assert_allclose(result.reactions[0, 2], 100, atol=1e-5)
    assert_allclose(result.displacement[0], 0, atol=0)
    # Global force and moment balance includes r × F at every node.
    node_by_id = {node.id: node for node in model.nodes}
    moment = float(np.sum(result.reactions[:, 2]))
    total_force = np.sum(result.reactions[:, :2], axis=0)
    for index, node_id in enumerate(result.node_ids):
        node = node_by_id[node_id]
        moment += node.x * result.reactions[index, 1] - node.y * result.reactions[index, 0]
    for load in model.loads:
        total_force += [load.fx, load.fy]
        node = node_by_id[load.node]
        moment += load.mz + node.x * load.fy - node.y * load.fx
    assert_allclose(total_force, 0, atol=1e-5)
    assert abs(moment) < 1e-5
    assert result.relative_residual < 1e-10


def test_axial_load_and_pure_end_moment() -> None:
    model = beam(4)
    geometry, material, rectangle = steel_case()
    section = rectangle.section()
    for load in [NodalLoad(node=4, fx=1000), NodalLoad(node=4, mz=10)]:
        loaded = FrameModel(**(model.model_dump() | {"loads": (load,)}))
        result = solve_static(loaded)
        if load.fx:
            assert_allclose(
                result.displacement[-1, 0],
                1000 * geometry.length / (material.young_modulus * section.area),
            )
            assert_allclose(result.displacement[-1, 1:], 0, atol=1e-12)
        else:
            assert_allclose(
                result.displacement[-1, 1],
                10 * geometry.length**2 / (2 * material.young_modulus * section.second_moment),
            )
            assert_allclose(
                result.displacement[-1, 2],
                10 * geometry.length / (material.young_modulus * section.second_moment),
            )


def test_modal_orthogonality_families_and_axial_benchmark() -> None:
    model = beam(32)
    result = solve_modal(model, AnalysisConfig(modes=10))
    assembly = assemble(model)
    assert np.all(np.diff(result.frequencies_hz) > 0)
    assert_allclose(result.modes.T @ assembly.mass @ result.modes, np.eye(10), atol=1e-9)
    # Normalize by modal stiffness: compare a dimensionless identity rather
    # than applying an absolute tolerance to mixed frequency scales.
    modal_k = result.modes.T @ assembly.stiffness @ result.modes
    omega = result.angular_frequencies
    assert_allclose(modal_k / omega[:, None] / omega[None, :], np.eye(10), atol=1e-7)
    assert_allclose(result.modes[assembly.fixed], 0, atol=0)
    assert np.max(result.relative_residuals) < 1e-6
    geometry, material, rectangle = steel_case()
    bending = result.frequencies_hz[np.array(result.families) == "bending"][:3]
    exact = cantilever_bending_hz(geometry, material, rectangle.section())
    assert_allclose(bending, exact, rtol=1e-4)
    axial = result.frequencies_hz[np.array(result.families) == "axial"]
    assert len(axial) > 0
    assert_allclose(
        axial[0],
        math.sqrt(material.young_modulus / material.density) / (4 * geometry.length),
        rtol=2e-4,
    )
    rotated = solve_modal(beam(16, 31), AnalysisConfig(modes=6))
    horizontal = solve_modal(beam(16), AnalysisConfig(modes=6))
    assert_allclose(rotated.frequencies_hz, horizontal.frequencies_hz, rtol=1e-7)


def test_convergence_and_machine_report() -> None:
    rows = convergence_study()
    errors = np.array([row["relative_frequency_errors"] for row in rows])
    assert np.all(np.diff(errors, axis=0) < 0)
    assert np.max(errors[-1]) < 1e-4
    report = verification_report()
    assert report["passed"] is True
    assert report["experimental_validation"] is False


def test_reduced_matrices_positive_definite_and_ordering() -> None:
    model = beam(4)
    assembly = assemble(model)
    k, m, _ = constrained_system(assembly, AnalysisConfig())
    linalg.cholesky(k)
    linalg.cholesky(m)
    reordered = FrameModel(
        **(
            model.model_dump()
            | {"nodes": tuple(reversed(model.nodes)), "elements": tuple(reversed(model.elements))}
        )
    )
    assert_allclose(assemble(reordered).stiffness, assembly.stiffness, atol=0)
    assert_allclose(solve_static(reordered).displacement, solve_static(model).displacement)


@pytest.mark.parametrize(
    "constraints",
    [
        (),
        (Constraint(node=0, dof=DOF.UX),),
        (Constraint(node=0, dof=DOF.UX), Constraint(node=0, dof=DOF.UY)),
    ],
)
def test_underconstrained_rejected(constraints: tuple[Constraint, ...]) -> None:
    model = beam(2)
    invalid = FrameModel(**(model.model_dump() | {"constraints": constraints}))
    with pytest.raises(UnstableModelError):
        solve_static(invalid)
    with pytest.raises(UnstableModelError):
        solve_modal(invalid)


def test_fully_constrained_and_mode_count_rejected() -> None:
    model = beam(1)
    fixed = tuple(Constraint(node=node.id, dof=dof) for node in model.nodes for dof in DOF)
    with pytest.raises(UnstableModelError):
        solve_static(FrameModel(**(model.model_dump() | {"constraints": fixed})))
    with pytest.raises(SolverError):
        solve_modal(model, AnalysisConfig(modes=4))


@pytest.mark.parametrize(
    "change",
    [
        {"nodes": (Node(id=0, x=0, y=0), Node(id=0, x=1, y=0))},
        {"nodes": (Node(id=0, x=0, y=0), Node(id=1, x=0, y=0))},
        {"nodes": (Node(id=0, x=0, y=0), Node(id=2, x=1, y=0))},
        {"nodes": (Node(id=0, x=0, y=0), Node(id=1, x=1, y=0), Node(id=2, x=2, y=0))},
        {"constraints": (Constraint(node=9, dof=DOF.UX),)},
        {"constraints": (Constraint(node=0, dof=DOF.UX), Constraint(node=0, dof=DOF.UX))},
        {"loads": (NodalLoad(node=9, fy=1),)},
    ],
)
def test_invalid_topology(change: dict[str, object]) -> None:
    model = beam(1)
    with pytest.raises((ValidationError, InvalidModelError)):
        FrameModel(**(model.model_dump() | change))


def test_duplicate_and_disconnected_elements_rejected() -> None:
    model = beam(1)
    first = model.elements[0]
    for second in [first, BeamElement(**(first.model_dump() | {"id": 2, "nodes": (1, 0)}))]:
        with pytest.raises((ValidationError, InvalidModelError)):
            FrameModel(**(model.model_dump() | {"elements": (first, second)}))
    disconnected = BeamElement(**(first.model_dump() | {"id": 2, "nodes": (2, 3)}))
    with pytest.raises((ValidationError, InvalidModelError)):
        FrameModel(
            nodes=(*model.nodes, Node(id=2, x=2, y=0), Node(id=3, x=3, y=0)),
            elements=(first, disconnected),
        )


@pytest.mark.parametrize("value", [-1, 0, float("nan"), float("inf")])
def test_invalid_physical_properties(value: float) -> None:
    with pytest.raises(ValidationError):
        Material(young_modulus=value, density=7850)
    with pytest.raises(ValidationError):
        Material(young_modulus=210e9, density=value)
    with pytest.raises(ValidationError):
        Rectangle(width=value, height=0.01)
    with pytest.raises(ValidationError):
        Section(area=1, second_moment=value)


def test_unsupported_constraints_and_connectivity() -> None:
    with pytest.raises((ValidationError, InvalidModelError)):
        Constraint(node=0, dof=DOF.UX, value=0.01)
    with pytest.raises(ValidationError):
        Constraint.model_validate({"node": 0, "dof": 9})
    model = beam(1)
    with pytest.raises(ValidationError):
        BeamElement.model_validate(model.elements[0].model_dump() | {"nodes": (0, 1, 2)})


def test_right_angle_frame_against_castigliano() -> None:
    # Vertical force F on an L-frame: horizontal leg bends, vertical leg extends.
    _, material, rectangle = steel_case()
    section = rectangle.section()
    length, force = 0.7, -100.0
    nodes = (
        Node(id=10, x=0, y=0),
        Node(id=20, x=length, y=0),
        Node(id=30, x=length, y=length),
    )
    model = FrameModel(
        nodes=nodes,
        elements=(
            BeamElement(id=5, nodes=(10, 20), material=material, section=section),
            BeamElement(id=6, nodes=(20, 30), material=material, section=section),
        ),
        constraints=tuple(Constraint(node=10, dof=dof) for dof in DOF),
        loads=(NodalLoad(node=30, fy=force),),
    )
    result = solve_static(model)
    ei, ea = material.young_modulus * section.second_moment, material.young_modulus * section.area
    assert_allclose(result.displacement[-1, 0], -force * length**3 / (2 * ei), rtol=1e-10)
    assert_allclose(
        result.displacement[-1, 1], force * length**3 / (3 * ei) + force * length / ea, rtol=1e-10
    )
    assert_allclose(result.displacement[-1, 2], force * length**2 / (2 * ei), rtol=1e-10)
    assert_allclose(result.reactions[0], [0, -force, -force * length], atol=1e-7)


def test_load_superposition_and_json_model_roundtrip() -> None:
    model = beam(4)
    half = NodalLoad(node=4, fy=-50)
    doubled = FrameModel.model_validate_json(
        FrameModel(**(model.model_dump() | {"loads": (half, half)})).model_dump_json()
    )
    assert_allclose(
        solve_static(doubled).displacement, solve_static(model).displacement, rtol=1e-12
    )
