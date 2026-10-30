"""Immutable input models. All lengths, forces, times, and material data use SI."""

from enum import IntEnum
from math import cos, radians, sin
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


class NodalMass(EngineeringModel):
    """Rigid planar body: mass at COM, Jz about COM, offset from reference [m]."""

    node: int = Field(ge=0)
    mass: float = Field(ge=0, description="kg; adds equal X/Y translational mass")
    inertia_z: float = Field(default=0, ge=0, description="kg m² about COM")
    offset: tuple[float, float] = (0.0, 0.0)

    @model_validator(mode="after")
    def admissible(self) -> Self:
        if self.mass == self.inertia_z == 0:
            raise InvalidModelError("A nodal inertia contribution must be nonzero.")
        if self.mass == 0 and self.offset != (0.0, 0.0):
            raise InvalidModelError("An offset needs nonzero translational mass.")
        return self


class LinearMount(EngineeringModel):
    """Directional spring/dashpot at rigid offset points; node_b=None means ground.

    Direction is global counterclockwise degrees from X. Positive extension is
    direction dot (point_a displacement - point_b displacement). Ground is fixed.
    Offsets are in global axes; small-rotation rigid kinematics are exact to first order.
    """

    id: int = Field(ge=0)
    node_a: int = Field(ge=0)
    node_b: int | None = Field(default=None, ge=0)
    angle_degrees: float = 90.0
    stiffness: float = Field(default=0, ge=0, description="N/m")
    damping: float = Field(default=0, ge=0, description="N s/m")
    offset_a: tuple[float, float] = (0.0, 0.0)
    offset_b: tuple[float, float] = (0.0, 0.0)

    @model_validator(mode="after")
    def attachments(self) -> Self:
        if self.node_a == self.node_b:
            raise InvalidModelError("Mount endpoints must use different reference nodes.")
        if self.node_b is None and self.offset_b != (0.0, 0.0):
            raise InvalidModelError("Ground has no moving reference or offset_b.")
        return self


class AnalysisConfig(EngineeringModel):
    modes: int = Field(default=6, ge=1)
    # Dimensionless eigenvalue threshold after diagonal stiffness equilibration.
    stability_tolerance: float = Field(default=1e-12, gt=0, lt=1e-4)


class FrameModel(EngineeringModel):
    nodes: tuple[Node, ...] = Field(min_length=1)
    elements: tuple[BeamElement, ...] = ()
    nodal_masses: tuple[NodalMass, ...] = ()
    mounts: tuple[LinearMount, ...] = ()
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
        mount_ids = [mount.id for mount in self.mounts]
        if len(set(mount_ids)) != len(mount_ids):
            raise InvalidModelError("Duplicate mount identifiers.")
        if any(body.node not in by_id for body in self.nodal_masses):
            raise InvalidModelError("Nodal mass references an unknown node.")
        for mount in self.mounts:
            if mount.node_a not in by_id or (
                mount.node_b is not None and mount.node_b not in by_id
            ):
                raise InvalidModelError("Mount references an unknown node.")
            if mount.node_b is not None:
                node_a, node_b = by_id[mount.node_a], by_id[mount.node_b]
                dx = node_a.x + mount.offset_a[0] - node_b.x - mount.offset_b[0]
                dy = node_a.y + mount.offset_a[1] - node_b.y - mount.offset_b[1]
                angle = radians(mount.angle_degrees % 360)
                if abs(-sin(angle) * dx + cos(angle) * dy) > 1e-10 * max(1, abs(dx), abs(dy)):
                    raise InvalidModelError(
                        "Relative directional mount points must coincide or align with its axis; "
                        "otherwise infinitesimal rigid rotation would strain the connector."
                    )
                neighbors[mount.node_a].add(mount.node_b)
                neighbors[mount.node_b].add(mount.node_a)
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
