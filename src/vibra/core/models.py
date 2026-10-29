"""Immutable input models. All lengths, forces, times, and material data use SI."""

from enum import IntEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vibra.core.errors import InvalidModelError


class EngineeringModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Material(EngineeringModel):
    name: str = Field(default="Steel", min_length=1)
    young_modulus: float = Field(gt=0, description="Pa")
    density: float = Field(gt=0, description="kg/m³")


class Section(EngineeringModel):
    area: float = Field(gt=0, description="m²")
    second_moment: float = Field(gt=0, description="m⁴ about the out-of-plane z axis")


class Rectangle(EngineeringModel):
    width: float = Field(gt=0, description="m, out-of-plane width")
    height: float = Field(gt=0, description="m, in-plane bending depth")

    def section(self) -> Section:
        return Section(
            area=self.width * self.height, second_moment=self.width * self.height**3 / 12
        )


class Node(EngineeringModel):
    id: int = Field(ge=0)
    x: float
    y: float


class BeamElement(EngineeringModel):
    id: int = Field(ge=0)
    nodes: tuple[int, int]
    material: Material
    section: Section


class DOF(IntEnum):
    UX = 0
    UY = 1
    RZ = 2


class Constraint(EngineeringModel):
    node: int = Field(ge=0)
    dof: DOF
    value: float = 0.0

    @model_validator(mode="after")
    def zero_only(self) -> Self:
        if self.value != 0:
            raise InvalidModelError("Only prescribed-zero displacement constraints are supported.")
        return self


class NodalLoad(EngineeringModel):
    node: int = Field(ge=0)
    fx: float = 0.0
    fy: float = 0.0
    mz: float = 0.0


class AnalysisConfig(EngineeringModel):
    modes: int = Field(default=6, ge=1)
    # Dimensionless eigenvalue threshold after diagonal stiffness equilibration.
    stability_tolerance: float = Field(default=1e-12, gt=0, lt=1e-4)


class FrameModel(EngineeringModel):
    nodes: tuple[Node, ...] = Field(min_length=2)
    elements: tuple[BeamElement, ...] = Field(min_length=1)
    constraints: tuple[Constraint, ...] = ()
    loads: tuple[NodalLoad, ...] = ()

    @model_validator(mode="after")
    def topology(self) -> Self:
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise InvalidModelError("Duplicate node identifiers.")
        element_ids = [element.id for element in self.elements]
        if len(set(element_ids)) != len(element_ids):
            raise InvalidModelError("Duplicate element identifiers.")
        by_id = {node.id: node for node in self.nodes}
        edges: set[tuple[int, int]] = set()
        neighbors: dict[int, set[int]] = {node: set() for node in ids}
        for element in self.elements:
            a, b = element.nodes
            if a not in by_id or b not in by_id:
                raise InvalidModelError(f"Element {element.id} references an unknown node.")
            if a == b or (by_id[a].x == by_id[b].x and by_id[a].y == by_id[b].y):
                raise InvalidModelError(f"Element {element.id} has zero length.")
            edge = (min(a, b), max(a, b))
            if edge in edges:
                raise InvalidModelError("Duplicate element connectivity, including reversed pairs.")
            edges.add(edge)
            neighbors[a].add(b)
            neighbors[b].add(a)
        visited: set[int] = set()
        pending = [ids[0]]
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(neighbors[node] - visited)
        if visited != set(ids):
            raise InvalidModelError("Disconnected mesh or unused nodes.")
        prescribed = [(c.node, c.dof) for c in self.constraints]
        if len(set(prescribed)) != len(prescribed):
            raise InvalidModelError("Duplicate constraints.")
        if any(c.node not in by_id for c in self.constraints):
            raise InvalidModelError("Constraint references an unknown node.")
        if any(load.node not in by_id for load in self.loads):
            raise InvalidModelError("Load references an unknown node.")
        return self
