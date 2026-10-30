"""Shared validated viscous damping and nodal response coordinates."""

from typing import Literal, Self

from pydantic import Field, model_validator

from vibra.core.errors import InvalidModelError
from vibra.core.models import DOF, EngineeringModel


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


class ResponseDOF(EngineeringModel):
    node: int = Field(ge=0)
    dof: DOF = DOF.UY

    @property
    def label(self) -> str:
        return f"Node {self.node} {self.dof.name} [{'rad' if self.dof == DOF.RZ else 'm'}]"
