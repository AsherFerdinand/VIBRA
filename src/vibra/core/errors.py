"""Errors indicating invalid engineering problems rather than UI failures."""


class EngineeringError(ValueError):
    """Base error for a physically or numerically invalid analysis."""


class InvalidModelError(EngineeringError):
    """Invalid geometry, topology, or unsupported model definition."""


class UnstableModelError(EngineeringError):
    """Constraints leave rigid-body modes or a numerically unresolved mechanism."""


class SolverError(EngineeringError):
    """Numerical solution failed its physical or algebraic checks."""
