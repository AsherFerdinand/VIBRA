"""Elastic Euler–Bernoulli fields from actual nodal states in local coordinates."""

from dataclasses import dataclass

import numpy as np

from vibra.core.assembly import AssembledElement, assemble
from vibra.core.element import Matrix
from vibra.core.errors import InvalidModelError
from vibra.core.models import FrameModel, Node


@dataclass(frozen=True)
class BeamField:
    element_id: int
    local_x_m: Matrix
    position_m: Matrix  # [station, global X/Y] on the undeformed axis
    displacement_m: Matrix  # [station, global UX/UY], never display-scaled
    rotation_rad: Matrix
    axial_force_N: Matrix  # tension positive; N=-N1=N2 for elastic end forces
    shear_force_N: Matrix  # V=dM/dx=V1, in the local axis convention
    bending_moment_Nm: Matrix  # M=EI*v''=-M1+V1*x


def interpolate_element(
    entry: AssembledElement, start: Node, end: Node, displacement: Matrix, samples: int = 21
) -> BeamField:
    """Linear axial / cubic Hermite transverse interpolation and exact derivatives.

    Forces are elastic section resultants, not inertial/damping/support reactions.
    No distributed element loads or section rotary/shear deformation are included.
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or not 2 <= samples <= 101:
        raise InvalidModelError("Use 2–101 interpolation stations per element.")
    local = entry.matrices.transform @ displacement.reshape(-1)[entry.dofs]
    u1, v1, t1, u2, v2, t2 = local
    xi = np.linspace(0, 1, samples)
    length = entry.matrices.length
    axial = (1 - xi) * u1 + xi * u2
    transverse = (
        (1 - 3 * xi**2 + 2 * xi**3) * v1
        + length * (xi - 2 * xi**2 + xi**3) * t1
        + (3 * xi**2 - 2 * xi**3) * v2
        + length * (-(xi**2) + xi**3) * t2
    )
    rotation = (
        (-6 * xi + 6 * xi**2) * v1 / length
        + (1 - 4 * xi + 3 * xi**2) * t1
        + (6 * xi - 6 * xi**2) * v2 / length
        + (-2 * xi + 3 * xi**2) * t2
    )
    curvature = (
        (-6 + 12 * xi) * v1
        + length * (-4 + 6 * xi) * t1
        + (6 - 12 * xi) * v2
        + length * (-2 + 6 * xi) * t2
    ) / length**2
    derivative = (12 * v1 + 6 * length * t1 - 12 * v2 + 6 * length * t2) / length**3
    e = entry.element.material.young_modulus
    section = entry.element.section
    base = np.array([start.x, start.y])[None, :] + xi[:, None] * np.array(
        [end.x - start.x, end.y - start.y]
    )
    delta = np.column_stack((axial, transverse)) @ entry.matrices.transform[:2, :2]
    return BeamField(
        entry.element.id,
        length * xi,
        base,
        delta,
        rotation,
        np.full(samples, e * section.area * (u2 - u1) / length),
        np.full(samples, e * section.second_moment * derivative),
        e * section.second_moment * curvature,
    )


def sample_beam(
    model: FrameModel, displacement: Matrix, samples: int = 21
) -> tuple[BeamField, ...]:
    state = np.asarray(displacement)
    if (
        np.iscomplexobj(state)
        or state.size != 3 * len(model.nodes)
        or not np.all(np.isfinite(state))
    ):
        raise InvalidModelError("Field recovery requires a finite real full nodal state in SI.")
    assembly = assemble(model)
    nodes = {node.id: node for node in model.nodes}
    fields = tuple(
        interpolate_element(
            entry, nodes[entry.element.nodes[0]], nodes[entry.element.nodes[1]], state, samples
        )
        for entry in assembly.elements
    )
    if any(
        not np.all(np.isfinite(value))
        for field in fields
        for value in (
            field.displacement_m,
            field.rotation_rad,
            field.axial_force_N,
            field.shear_force_N,
            field.bending_moment_Nm,
        )
    ):
        raise InvalidModelError("Beam field recovery overflowed; check SI magnitudes.")
    return fields


@dataclass(frozen=True)
class SectionStress:
    field: BeamField
    extreme_fiber_distance_m: float
    axial_Pa: Matrix
    bending_top_Pa: Matrix
    bending_bottom_Pa: Matrix
    combined_top_Pa: Matrix
    combined_bottom_Pa: Matrix


@dataclass(frozen=True)
class CriticalStress:
    element_id: int
    local_x_m: float
    global_x_m: float
    global_y_m: float  # axis coordinate; fiber is specified separately
    fiber_y_m: float
    normal_stress_Pa: float


@dataclass(frozen=True)
class StressResult:
    sections: tuple[SectionStress, ...]
    minimum_normal_Pa: float
    maximum_normal_Pa: float
    critical_absolute: CriticalStress
    convention: str = (
        "Local x from node 1 to 2; y local transverse; tension positive; sigma=N/A-M*y/I"
    )
    units: str = "m, N, N m, Pa; beam section normal stress, not solid/contact/von Mises stress"


def recover_stress(model: FrameModel, displacement: Matrix, samples: int = 21) -> StressResult:
    """Prismatic section extrema at explicit symmetric +/-c fibers.

    c is geometric input, not inferred from A and I. No yield/fatigue assessment.
    N is constant and M linear within each elastic unloaded FEM element; extrema
    at its end sections are included exactly. Displacement extrema remain sampled.
    """
    fields = sample_beam(model, displacement, samples)
    if not fields:
        raise InvalidModelError("Stress recovery needs at least one beam element.")
    elements = {element.id: element for element in model.elements}
    sections = []
    critical = None
    minimum = float("inf")
    maximum = -float("inf")
    for field in fields:
        section = elements[field.element_id].section
        c = section.extreme_fiber_distance
        if c is None:
            raise InvalidModelError(
                "Supply section.extreme_fiber_distance [m] for stress recovery."
            )
        axial = field.axial_force_N / section.area
        top = -field.bending_moment_Nm * c / section.second_moment
        result = SectionStress(field, c, axial, top, -top, axial + top, axial - top)
        if not all(
            np.all(np.isfinite(values))
            for values in (
                result.axial_Pa,
                result.bending_top_Pa,
                result.combined_top_Pa,
                result.combined_bottom_Pa,
            )
        ):
            raise InvalidModelError(
                "Stress recovery overflowed; check section dimensions and SI values."
            )
        sections.append(result)
        for values, fiber in ((result.combined_top_Pa, c), (result.combined_bottom_Pa, -c)):
            minimum = min(minimum, float(values.min()))
            maximum = max(maximum, float(values.max()))
            index = int(np.argmax(abs(values)))
            value = float(values[index])
            if critical is None or abs(value) > abs(critical.normal_stress_Pa):
                critical = CriticalStress(
                    field.element_id,
                    float(field.local_x_m[index]),
                    float(field.position_m[index, 0]),
                    float(field.position_m[index, 1]),
                    fiber,
                    value,
                )
    if critical is None or not np.isfinite(minimum) or not np.isfinite(maximum):
        raise InvalidModelError("Invalid recovered stress; check section dimensions and SI values.")
    return StressResult(tuple(sections), minimum, maximum, critical)
