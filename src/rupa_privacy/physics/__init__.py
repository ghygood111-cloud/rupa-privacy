"""Public physical-constraint post-processing."""

from .projection import apply_physical_projection, build_constraint_system
from .validation import (
    ConstraintValidationResult,
    require_valid_physical_constraints,
    validate_physical_constraints,
)

__all__ = [
    "ConstraintValidationResult",
    "apply_physical_projection",
    "build_constraint_system",
    "require_valid_physical_constraints",
    "validate_physical_constraints",
]
