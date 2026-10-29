"""Straight beam geometry and uniform mesh generation."""

from pydantic import Field

from vibra.core.models import (
    DOF,
    BeamElement,
    Constraint,
    EngineeringModel,
    FrameModel,
    Material,
    NodalLoad,
    Node,
    Section,
)


class BeamGeometry(EngineeringModel):
    length: float = Field(gt=0)
    angle_degrees: float = 0.0


def cantilever(
    geometry: BeamGeometry,
    material: Material,
    section: Section,
    elements: int = 12,
    tip_force: float = -100.0,
) -> FrameModel:
    """Fix node zero; apply a transverse local-y tip force (N)."""
    import math

    if isinstance(elements, bool) or not isinstance(elements, int) or elements < 1:
        raise ValueError("Element count must be a positive integer.")
    angle = math.radians(geometry.angle_degrees)
    c, s = math.cos(angle), math.sin(angle)
    return FrameModel(
        nodes=tuple(
            Node(id=i, x=geometry.length * i / elements * c, y=geometry.length * i / elements * s)
            for i in range(elements + 1)
        ),
        elements=tuple(
            BeamElement(id=i, nodes=(i, i + 1), material=material, section=section)
            for i in range(elements)
        ),
        constraints=tuple(Constraint(node=0, dof=dof) for dof in DOF),
        loads=(NodalLoad(node=elements, fx=-s * tip_force, fy=c * tip_force),),
    )
