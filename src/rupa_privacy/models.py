"""Typed configuration, governance state, and result objects for RUPA."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .exceptions import ConfigurationError

CALIBRATION_MODES = {"public", "synthetic", "disjoint_private"}
RANDOMNESS_MODES = {"reproducibility", "production"}
RELEASE_DATA_MODES = {"synthetic", "public_demonstration", "confidential"}
ADJACENCY_TYPES = {"fixed_roster_replace_one"}
CATEGORICAL_BUDGET_STRATEGIES = {"heuristic_risk_utility", "uniform"}
NUMERIC_BUDGET_STRATEGIES = {"legacy_rupa", "balanced_rupa", "uniform"}


def _configuration_list(name, values):
    if isinstance(values, (str, bytes)) or isinstance(values, Mapping):
        raise ConfigurationError(name + " must be a list")
    try:
        return list(values)
    except TypeError as exc:
        raise ConfigurationError(name + " must be a list") from exc


def _column_list(name, values):
    result = _configuration_list(name, values)
    if any(not isinstance(value, str) for value in result):
        raise ConfigurationError(name + " must contain only field names")
    return result


@dataclass
class DataSchema:
    """Public declaration of protected, released and excluded fields."""

    sensitive_target: str
    numeric_columns: List[str]
    categorical_columns: List[str]
    excluded_columns: List[str] = field(default_factory=list)
    released_columns: List[str] = field(default_factory=list)
    public_bounds: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    public_categories: Dict[str, List[Any]] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.sensitive_target, str):
            raise ConfigurationError("sensitive_target must be a string")
        self.numeric_columns = _column_list("numeric_columns", self.numeric_columns)
        self.categorical_columns = _column_list(
            "categorical_columns", self.categorical_columns
        )
        self.excluded_columns = _column_list(
            "excluded_columns", self.excluded_columns
        )
        if not self.released_columns:
            self.released_columns = self.numeric_columns + self.categorical_columns
        else:
            self.released_columns = _column_list(
                "released_columns", self.released_columns
            )
        if not isinstance(self.public_bounds, Mapping):
            raise ConfigurationError("public_bounds must be a mapping")
        parsed_bounds = {}
        for name, bounds in self.public_bounds.items():
            if isinstance(bounds, (str, bytes)) or isinstance(bounds, Mapping):
                raise ConfigurationError(
                    "public_bounds[{0}] must contain exactly two numbers".format(name)
                )
            try:
                bounds = list(bounds)
            except TypeError as exc:
                raise ConfigurationError(
                    "public_bounds[{0}] must contain exactly two numbers".format(name)
                ) from exc
            if len(bounds) != 2:
                raise ConfigurationError(
                    "public_bounds[{0}] must contain exactly two numbers".format(name)
                )
            try:
                parsed_bounds[str(name)] = (float(bounds[0]), float(bounds[1]))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ConfigurationError(
                    "public_bounds[{0}] must contain numeric values".format(name)
                ) from exc
        self.public_bounds = parsed_bounds

        if not isinstance(self.public_categories, Mapping):
            raise ConfigurationError("public_categories must be a mapping")
        parsed_categories = {}
        for name, values in self.public_categories.items():
            if isinstance(values, (str, bytes)) or isinstance(values, Mapping):
                raise ConfigurationError(
                    "public_categories[{0}] must be a list".format(name)
                )
            try:
                parsed_categories[str(name)] = list(values)
            except TypeError as exc:
                raise ConfigurationError(
                    "public_categories[{0}] must be a list".format(name)
                ) from exc
        self.public_categories = parsed_categories

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]):
        return cls(**dict(values))

    def to_dict(self):
        return asdict(self)


@dataclass
class PrivacyConfig:
    """Privacy, allocation, randomness, and data-governance settings.

    ``categorical_budget_strategy="heuristic_risk_utility"`` uses
    ``W / (R + c)`` with ``categorical_risk_smoothing`` as ``c``. The default
    ``c=0.05`` prevents unstable division near zero risk; it is a heuristic
    tradeoff, not an optimality result. High-cardinality or rare-category fields
    can still be strongly distorted. ``uniform`` is the more conservative
    baseline when no application-specific allocation evidence is available.
    """

    epsilon_total: float = 5.0
    epsilon_numeric: float = 4.6
    epsilon_categorical: float = 0.4
    delta: float = 1e-5
    utility_alpha: float = 0.6
    repair_alpha: float = 0.98
    randomness_mode: str = "reproducibility"
    random_seed: Optional[int] = 123
    calibration_mode: str = "synthetic"
    calibration_source: str = "Built-in synthetic generator"
    calibration_public_confirmed: bool = False
    release_data_mode: str = "synthetic"
    release_source: str = "Built-in synthetic generator"
    release_public_confirmed: bool = False
    categorical_mode: str = "randomized_response"
    categorical_budget_strategy: str = "heuristic_risk_utility"
    categorical_risk_smoothing: float = 0.05
    nmi_bins: int = 10
    joint_bins: int = 5
    joint_nmi_diagnostic: bool = True
    knee_grid_points: int = 21
    numeric_budget_strategy: str = "legacy_rupa"
    numeric_risk_smoothing: float = 0.05
    numeric_stability_weight: float = 0.1
    numeric_min_uniform_fraction: float = 0.5
    numeric_max_uniform_multiple: float = 2.0

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]):
        return cls(**dict(values))

    def to_dict(self):
        return asdict(self)

    def to_public_dict(self):
        values = self.to_dict()
        if self.randomness_mode == "production":
            values.pop("random_seed", None)
        return values


@dataclass
class AdjacencyConfig:
    """The fixed-roster replacement adjacency supported by this release."""

    type: str
    privacy_unit_id: str
    roster_is_public: bool
    one_row_per_unit: bool

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]):
        return cls(**dict(values))

    def to_dict(self):
        return asdict(self)


@dataclass
class PrivacyAccountingConfig:
    """Persistent cross-run accounting requirements for one dataset."""

    dataset_id: str
    maximum_cumulative_epsilon: float
    ledger_path: str

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]):
        return cls(**dict(values))

    def to_dict(self):
        return asdict(self)


@dataclass
class PhysicalConstraint:
    """A declared-public linear equality over released numerical fields."""

    name: str
    coefficients: Dict[str, float]
    rhs: float = 0.0
    tolerance: float = 0.01
    type: str = "equality"
    provenance: str = "public"

    def __post_init__(self):
        if not isinstance(self.coefficients, Mapping):
            raise ConfigurationError(
                "constraint coefficients must be a mapping of field names to numeric values"
            )
        try:
            self.coefficients = {
                str(name): float(value) for name, value in self.coefficients.items()
            }
            self.rhs = float(self.rhs)
            self.tolerance = float(self.tolerance)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConfigurationError(
                "constraint coefficients, rhs, and tolerance must be numeric"
            ) from exc

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]):
        return cls(**dict(values))

    def to_dict(self):
        return asdict(self)


@dataclass
class ConstraintValidationResult:
    """Diagnostics for a public linear-equality constraint system."""

    matrix_rows: int
    matrix_columns: int
    rank: int
    expected_rank: int
    augmented_rank: int
    condition_number: float
    zero_rows: List[int]
    zero_columns: List[str]
    redundant_rows: List[int]
    conflicting_rows: List[Dict[str, Any]]
    feasibility_status: str
    warnings: List[str]
    errors: List[str]
    decision: str

    def to_dict(self):
        return asdict(self)


@dataclass
class JointRiskRecord:
    first: str
    second: str
    joint_nmi: float
    max_single_nmi: float
    excess: float


@dataclass
class RiskResult:
    single_scores: Dict[str, float]
    joint_records: List[JointRiskRecord]
    joint_penalty: Dict[str, float]
    augmented_risk: Dict[str, float]
    bin_diagnostics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    bin_warnings: List[str] = field(default_factory=list)


@dataclass
class UtilityResult:
    prior_weights: Dict[str, float]
    entropy_weights: Dict[str, float]
    utility_weights: Dict[str, float]
    alpha: float


@dataclass
class AllocationResult:
    epsilon: Dict[str, float]
    sensitivities: Dict[str, float]
    numeric_budget: float
    categorical_budget: float
    basic_composition_epsilon: float
    numerical_rdp_diagnostic_epsilon: float
    numerical_rdp_order: float
    mixed_rdp_strict_bound_established: bool
    optimizer_details: Dict[str, Any]


@dataclass
class FittedRUPAState:
    risk_result: RiskResult
    utility_result: UtilityResult
    allocation_result: AllocationResult
    calibration_columns: Tuple[str, ...]
    calibration_rows: int
    calibration_unit_tokens: Tuple[str, ...]
    warnings: List[str]


@dataclass
class RUPAResult:
    """All release states and aggregate audits from one transform call."""

    risk_result: RiskResult
    utility_result: UtilityResult
    allocation_result: AllocationResult
    noisy_data: pd.DataFrame
    projected_data: pd.DataFrame
    repaired_data: pd.DataFrame
    release_data: pd.DataFrame
    privacy_audit: Dict[str, Any]
    utility_audit: Dict[str, Any]
    physical_audit: Dict[str, Any]
    attack_audit: Dict[str, Any]
    governance_audit: Dict[str, Any]
    diagnostics: Dict[str, Any]
    metadata: Dict[str, Any]
