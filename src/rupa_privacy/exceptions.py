"""Domain-specific exceptions with messages safe for CLI and GUI display."""


class RUPAError(Exception):
    """Base exception for the configured RUPA release workflow."""


class ConfigurationError(RUPAError):
    """Raised when public schema or privacy configuration is invalid."""


class ConstraintValidationError(ConfigurationError):
    """Raised when public linear equalities cannot be projected safely."""

    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


class DataValidationError(RUPAError):
    """Raised when an input table violates its declared schema."""


class NotFittedError(RUPAError):
    """Raised when transform is called before fit."""


class PrivacySafetyError(RUPAError):
    """Raised when an operation would violate a release-safety rule."""


class BudgetOptimizationError(RUPAError):
    """Raised when no privacy-budget candidate satisfies every constraint."""

    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class LedgerError(RUPAError):
    """Raised when persistent privacy accounting cannot proceed safely."""


class OperationCancelled(RUPAError):
    """Raised when a user safely cancels a product workflow."""
