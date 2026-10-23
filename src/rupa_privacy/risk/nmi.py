"""Single-attribute NMI risk with an optional pairwise NMI diagnostic."""

from itertools import combinations
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import normalized_mutual_info_score
from sklearn.preprocessing import KBinsDiscretizer, LabelEncoder

from ..models import DataSchema, JointRiskRecord, RiskResult


def _quantile_discretizer(n_bins):
    # The supported scikit-learn <1.7 contract has no quantile_method argument.
    # Using all rows avoids the randomized >200,000-row default subsample.
    return KBinsDiscretizer(
        n_bins=int(n_bins),
        encode="ordinal",
        strategy="quantile",
        subsample=None,
        random_state=0,
    )


def _collapse_severity(requested_bins, effective_bins):
    if effective_bins >= requested_bins:
        return "none"
    if effective_bins <= 1:
        return "degenerate"
    if effective_bins < requested_bins / 2.0:
        return "severe"
    return "mild"


def _bin_diagnostic(requested_bins, configured_bins, effective_bins, unique_values, messages):
    severity = _collapse_severity(requested_bins, effective_bins)
    warning = None
    if severity != "none":
        warning = (
            "Requested {0} quantile bins but fitted {1} effective bins "
            "from {2} unique values ({3} collapse)."
        ).format(requested_bins, effective_bins, unique_values, severity)
    return {
        "requested_bins": int(requested_bins),
        "configured_bins": int(configured_bins),
        "effective_bins": int(effective_bins),
        "unique_values": int(unique_values),
        "collapse_severity": severity,
        "warning": warning,
        "sklearn_warnings": list(messages),
        "subsample": None,
        "random_state": 0,
    }


def discretize_1d(values, n_bins=10, return_diagnostics=False):
    values = np.asarray(values, dtype=float).reshape(-1, 1)
    requested_bins = int(n_bins)
    unique = len(np.unique(values))
    if unique < 2:
        labels = np.zeros(len(values), dtype=int)
        diagnostic = _bin_diagnostic(requested_bins, 1, 1, unique, [])
        return (labels, diagnostic) if return_diagnostics else labels
    bins = min(requested_bins, unique)
    discretizer = _quantile_discretizer(bins)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        labels = discretizer.fit_transform(values).astype(int).ravel()
    diagnostic = _bin_diagnostic(
        requested_bins,
        bins,
        int(discretizer.n_bins_[0]),
        unique,
        [str(item.message) for item in caught],
    )
    return (labels, diagnostic) if return_diagnostics else labels


def _joint_labels(first, second, n_bins, return_diagnostics=False):
    values = np.column_stack([np.asarray(first, dtype=float), np.asarray(second, dtype=float)])
    requested_bins = int(n_bins)
    discretizer = _quantile_discretizer(requested_bins)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        labels = discretizer.fit_transform(values).astype(int)
    joint_labels = labels[:, 0] * requested_bins + labels[:, 1]
    effective = [int(value) for value in discretizer.n_bins_]
    unique = [int(len(np.unique(values[:, index]))) for index in range(2)]
    severities = [
        _collapse_severity(requested_bins, effective_bins)
        for effective_bins in effective
    ]
    diagnostic = {
        "requested_bins": requested_bins,
        "effective_bins": effective,
        "effective_joint_labels": int(len(np.unique(joint_labels))),
        "unique_values": unique,
        "collapse_severity": severities,
        "warning": (
            "Requested {0} bins per joint dimension but fitted {1}.".format(
                requested_bins, effective
            )
            if any(item != "none" for item in severities)
            else None
        ),
        "sklearn_warnings": [str(item.message) for item in caught],
        "subsample": None,
        "random_state": 0,
    }
    return (joint_labels, diagnostic) if return_diagnostics else joint_labels


def compute_risk(
    calibration_data: pd.DataFrame,
    schema: DataSchema,
    nmi_bins=10,
    joint_bins=5,
    joint_nmi_diagnostic=True,
):
    target_labels, target_diagnostic = discretize_1d(
        calibration_data[schema.sensitive_target].to_numpy(dtype=float),
        nmi_bins,
        return_diagnostics=True,
    )
    bin_diagnostics = {"target:" + schema.sensitive_target: target_diagnostic}
    single_scores = {}
    for name in schema.released_columns:
        if name in schema.categorical_columns:
            feature_labels = LabelEncoder().fit_transform(calibration_data[name].to_numpy())
        else:
            feature_labels, diagnostic = discretize_1d(
                calibration_data[name].to_numpy(dtype=float),
                nmi_bins,
                return_diagnostics=True,
            )
            bin_diagnostics["feature:" + name] = diagnostic
        single_scores[name] = float(
            normalized_mutual_info_score(
                feature_labels, target_labels, average_method="arithmetic"
            )
        )

    penalty = {name: 0.0 for name in schema.released_columns}
    records = []
    pairs = combinations(schema.numeric_columns, 2) if joint_nmi_diagnostic else ()
    for first, second in pairs:
        labels, diagnostic = _joint_labels(
            calibration_data[first].to_numpy(dtype=float),
            calibration_data[second].to_numpy(dtype=float),
            joint_bins,
            return_diagnostics=True,
        )
        bin_diagnostics["joint:{0}|{1}".format(first, second)] = diagnostic
        joint_nmi = float(
            normalized_mutual_info_score(
                labels, target_labels, average_method="arithmetic"
            )
        )
        max_single = max(single_scores[first], single_scores[second])
        excess = max(0.0, joint_nmi - max_single)
        penalty[first] += 0.5 * excess
        penalty[second] += 0.5 * excess
        records.append(
            JointRiskRecord(first, second, joint_nmi, max_single, excess)
        )

    for name in schema.numeric_columns:
        penalty[name] = min(penalty[name], 0.5 * max(single_scores[name], 1e-6))
    augmented = {name: 0.0 for name in schema.released_columns}
    for name in schema.numeric_columns:
        augmented[name] = float(np.clip(single_scores[name] + penalty[name], 0.0, 1.0))
    bin_warnings = [
        "{0}: {1}".format(name, diagnostic["warning"])
        for name, diagnostic in bin_diagnostics.items()
        if diagnostic.get("warning")
    ]
    return RiskResult(
        single_scores,
        records,
        penalty,
        augmented,
        bin_diagnostics=bin_diagnostics,
        bin_warnings=bin_warnings,
    )
