"""Single-process public API for fitting and applying the RUPA mechanism."""

from copy import deepcopy

from .allocation import allocate_privacy_budget
from .evaluation import evaluate_release_utility
from .exceptions import NotFittedError
from .exceptions import PrivacySafetyError
from .governance import dataframe_version_hash, privacy_unit_tokens
from .mechanisms import perturb_release_data
from .models import FittedRUPAState, RUPAResult
from .physics import apply_physical_projection
from .risk import compute_risk
from .utility import compute_utility_weights
from .validation import (
    validate_calibration_data,
    validate_configuration,
    validate_release_data,
)


class RUPAPipeline:
    """Fit risk/utility allocation once, then protect one or more release tables."""

    def __init__(
        self,
        schema,
        privacy_config,
        physical_constraints,
        regulatory_prior,
        adjacency_config,
        privacy_accounting,
    ):
        self.schema = deepcopy(schema)
        self.privacy_config = deepcopy(privacy_config)
        self.physical_constraints = deepcopy(list(physical_constraints))
        self.regulatory_prior = deepcopy(dict(regulatory_prior))
        self.adjacency_config = deepcopy(adjacency_config)
        self.privacy_accounting = deepcopy(privacy_accounting)
        self.constraint_validation_ = validate_configuration(
            self.schema,
            self.privacy_config,
            self.physical_constraints,
            self.regulatory_prior,
            self.adjacency_config,
            self.privacy_accounting,
        )
        self.fitted_state_ = None

    def fit(self, calibration_data):
        """Estimate risk, utility, and fixed release parameters from calibration data."""
        validate_calibration_data(
            calibration_data, self.schema, self.adjacency_config
        )
        risk = compute_risk(
            calibration_data,
            self.schema,
            nmi_bins=self.privacy_config.nmi_bins,
            joint_bins=self.privacy_config.joint_bins,
            joint_nmi_diagnostic=self.privacy_config.joint_nmi_diagnostic,
        )
        utility = compute_utility_weights(
            calibration_data,
            self.schema,
            self.regulatory_prior,
            alpha=self.privacy_config.utility_alpha,
        )
        allocation = allocate_privacy_budget(
            self.schema, self.privacy_config, risk, utility
        )
        warnings = self._calibration_warnings()
        warnings.extend(risk.bin_warnings)
        self.fitted_state_ = FittedRUPAState(
            risk_result=risk,
            utility_result=utility,
            allocation_result=allocation,
            calibration_columns=tuple(calibration_data.columns),
            calibration_rows=int(len(calibration_data)),
            calibration_unit_tokens=privacy_unit_tokens(
                calibration_data, self.adjacency_config.privacy_unit_id
            ),
            warnings=warnings,
        )
        return self

    def transform(self, release_data, seed=None, production_authorization=None):
        """Protect release data using only fitted values and declared public metadata."""
        if self.fitted_state_ is None:
            raise NotFittedError("Call fit(calibration_data) before transform(release_data)")
        validate_release_data(release_data, self.schema, self.adjacency_config)
        if self.privacy_config.randomness_mode == "production":
            if production_authorization is None:
                raise PrivacySafetyError(
                    "Production transform requires an active privacy-ledger reservation"
                )
            expected_hash = dataframe_version_hash(
                release_data,
                [self.adjacency_config.privacy_unit_id] + self.schema.released_columns,
            )
            if (
                getattr(production_authorization, "dataset_id", None)
                != self.privacy_accounting.dataset_id
                or getattr(production_authorization, "dataset_version_hash", None)
                != expected_hash
                or getattr(production_authorization, "status", None) != "pending"
            ):
                raise PrivacySafetyError(
                    "Production authorization does not match the release dataset"
                )
        calibration_tokens = set(self.fitted_state_.calibration_unit_tokens)
        release_tokens = set(
            privacy_unit_tokens(release_data, self.adjacency_config.privacy_unit_id)
        )
        overlap_count = len(calibration_tokens & release_tokens)
        if self.privacy_config.calibration_mode == "disjoint_private" and overlap_count:
            raise PrivacySafetyError(
                "disjoint_private calibration overlaps release privacy units"
            )
        original_release = release_data.loc[:, self.schema.released_columns].copy()
        noisy = perturb_release_data(
            original_release,
            self.schema,
            self.privacy_config,
            self.fitted_state_.allocation_result,
            seed=seed,
        )
        projected, repaired, final_release, physical_audit = apply_physical_projection(
            original_release,
            noisy,
            self.schema,
            self.physical_constraints,
            self.fitted_state_.allocation_result,
            self.privacy_config.repair_alpha,
        )
        utility_audit = evaluate_release_utility(
            original_release, final_release, self.schema
        )
        public_release = final_release.copy()
        public_release.insert(
            0,
            self.adjacency_config.privacy_unit_id,
            release_data[self.adjacency_config.privacy_unit_id].to_numpy(copy=True),
        )
        if public_release[self.adjacency_config.privacy_unit_id].tolist() != release_data[
            self.adjacency_config.privacy_unit_id
        ].tolist():
            raise PrivacySafetyError("The public roster was not preserved in output order")
        allocation = self.fitted_state_.allocation_result
        privacy_audit = {
            "basic_composition_epsilon": allocation.basic_composition_epsilon,
            "epsilon_total_configured": self.privacy_config.epsilon_total,
            "numerical_laplace_rdp_diagnostic": {
                "epsilon": allocation.numerical_rdp_diagnostic_epsilon,
                "delta": self.privacy_config.delta,
                "order": allocation.numerical_rdp_order,
                "scope": "numerical Laplace mechanisms only",
            },
            "mixed_laplace_randomized_response_rdp_bound_established": False,
            "formal_scope": (
                "Single fixed-roster, row-preserving replacement release with public bounds, "
                "public category domains, release-independent fitted parameters, valid "
                "randomness, and cross-run accounting."
            ),
            "formal_claim": (
                "Basic sequential composition is the accounting rule for one authorized "
                "release. No strict mixed-mechanism RDP claim is made."
            ),
        }
        return RUPAResult(
            risk_result=self.fitted_state_.risk_result,
            utility_result=self.fitted_state_.utility_result,
            allocation_result=allocation,
            noisy_data=noisy,
            projected_data=projected,
            repaired_data=repaired,
            release_data=public_release,
            privacy_audit=privacy_audit,
            utility_audit=utility_audit,
            physical_audit=physical_audit,
            attack_audit={
                "status": "not_run",
                "reason": "Attack evaluation requires an explicit internal-audit workflow.",
            },
            governance_audit={
                "adjacency": self.adjacency_config.type,
                "privacy_unit_id": self.adjacency_config.privacy_unit_id,
                "roster_is_public": True,
                "one_row_per_unit": True,
                "roster_preserved": True,
                "calibration_mode": self.privacy_config.calibration_mode,
                "calibration_unit_count": len(calibration_tokens),
                "release_unit_count": len(release_tokens),
                "calibration_release_disjoint_check": (
                    "PASS"
                    if self.privacy_config.calibration_mode == "disjoint_private"
                    else "NOT_APPLICABLE"
                ),
                "overlap_count_internal": overlap_count,
                "protection_scope": (
                    "The mechanism protects release subjects under fixed-roster replacement "
                    "adjacency; it does not automatically protect private calibration subjects."
                ),
            },
            diagnostics={
                "release_rows": int(len(release_data)),
                "calibration_rows": self.fitted_state_.calibration_rows,
                "warnings": list(self.fitted_state_.warnings),
                **(
                    {
                        "seed": self.privacy_config.random_seed
                        if seed is None
                        else int(seed)
                    }
                    if self.privacy_config.randomness_mode == "reproducibility"
                    else {}
                ),
            },
            metadata={
                "software": "RUPA configurable differential privacy release toolkit",
                "calibration_mode": self.privacy_config.calibration_mode,
                "randomness_mode": self.privacy_config.randomness_mode,
                "adjacency": self.adjacency_config.type,
                "release_type": "fixed-roster, row-preserving microdata release",
                "sensitive_target_released": self.schema.sensitive_target
                in public_release.columns,
                "released_columns": list(public_release.columns),
                "local_processing_only": True,
                "release_notice": (
                    "Reproducibility mode - not for confidential data release"
                    if self.privacy_config.randomness_mode == "reproducibility"
                    else "Production mode - OS-backed randomness is non-replayable and no internal random state is exported"
                ),
            },
        )

    def fit_transform(
        self,
        calibration_data,
        release_data,
        seed=None,
        production_authorization=None,
    ):
        """Fit on calibration data and protect release data in one call."""
        if self.privacy_config.calibration_mode == "disjoint_private":
            validate_calibration_data(
                calibration_data, self.schema, self.adjacency_config
            )
            validate_release_data(
                release_data, self.schema, self.adjacency_config
            )
            calibration_tokens = set(
                privacy_unit_tokens(
                    calibration_data, self.adjacency_config.privacy_unit_id
                )
            )
            release_tokens = set(
                privacy_unit_tokens(
                    release_data, self.adjacency_config.privacy_unit_id
                )
            )
            if calibration_tokens & release_tokens:
                raise PrivacySafetyError(
                    "disjoint_private calibration overlaps release privacy units"
                )
        return self.fit(calibration_data).transform(
            release_data,
            seed=seed,
            production_authorization=production_authorization,
        )

    def _calibration_warnings(self):
        mode = self.privacy_config.calibration_mode
        if mode == "disjoint_private":
            warnings = [
                "Disjoint private calibration requires calibration subjects to be "
                "disjoint from release subjects. Private calibration subjects are "
                "outside the release-subject guarantee, and derived risk, utility, "
                "and allocation parameters remain internal."
            ]
        elif mode == "public":
            warnings = ["Calibration inputs are treated as explicitly public metadata."]
        else:
            warnings = [
                "Calibration inputs are declared synthetic and separate from release records."
            ]
        warnings.append(
            "Joint-NMI is retained as an optional diagnostic. Current validation does "
            "not demonstrate a material downstream advantage."
        )
        if self.privacy_config.categorical_budget_strategy == "heuristic_risk_utility":
            warnings.append(
                "Categorical epsilon uses heuristic risk-utility categorical budget "
                "allocation; no optimality claim is made."
            )
        return warnings
