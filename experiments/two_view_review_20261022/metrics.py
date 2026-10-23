"""Offline evaluation, never a public-artifact writer or privacy mechanism."""
import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance


def _mean(values):
    defined = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.mean(defined)) if defined else None


def _relative(error, reference):
    return float(abs(error) / abs(reference)) if abs(reference) > 1e-12 else None


def aggregate_metrics(totals, original, prepared):
    totals = np.asarray(totals, dtype=float)
    truth = original.sum(axis=0)
    relative = [_relative(x - y, y) for x, y in zip(totals, truth)]
    defined = [v for v in relative if v is not None]
    residual = prepared["matrix"] @ totals - prepared["rhs"]
    return {
        "normalized_total_squared_error": float(np.mean(((totals - prepared["truth"]) / prepared["scale"]) ** 2)),
        "mean_total_relative_error_percent": 100 * _mean(defined) if defined else None,
        "median_total_relative_error_percent": float(100 * np.median(defined)) if defined else None,
        "maximum_total_relative_error_percent": float(100 * np.max(defined)) if defined else None,
        "undefined_total_relative_fields": len(relative) - len(defined),
        "maximum_aggregate_equality_residual": float(np.max(abs(residual))) if residual.size else None,
    }


def evaluate_rows(values, original, prepared, constraints):
    values, original = np.asarray(values, float), np.asarray(original, float)
    if values.shape != original.shape or not np.isfinite(values).all():
        raise ValueError("Finite aligned row matrices required for offline evaluation")
    width = prepared["delta"]
    actual_sd, released_sd = original.std(axis=0), values.std(axis=0)
    actual_mean, released_mean = original.mean(axis=0), values.mean(axis=0)
    fields = []
    quantiles = np.array([.1, .25, .5, .75, .9])
    for j, name in enumerate(prepared["names"]):
        error = values[:, j] - original[:, j]
        row = {
            "field": name,
            "mean_relative_error_percent": None if _relative(released_mean[j] - actual_mean[j], actual_mean[j]) is None else 100 * _relative(released_mean[j] - actual_mean[j], actual_mean[j]),
            "standard_deviation_relative_error_percent": None if _relative(released_sd[j] - actual_sd[j], actual_sd[j]) is None else 100 * _relative(released_sd[j] - actual_sd[j], actual_sd[j]),
            "standard_deviation_ratio": float(released_sd[j] / actual_sd[j]) if actual_sd[j] > width[j] * 1e-12 else None,
            "constant_output": bool(released_sd[j] <= width[j] * 1e-12),
            "wasserstein_range": float(wasserstein_distance(original[:, j], values[:, j]) / width[j]),
            "ks_statistic": float(ks_2samp(original[:, j], values[:, j], method="asymp").statistic),
            "row_mae_range": float(np.mean(abs(error)) / width[j]),
            "row_rmse_range": float(np.sqrt(np.mean(error ** 2)) / width[j]),
        }
        for q, a, b in zip(quantiles, np.quantile(original[:, j], quantiles), np.quantile(values[:, j], quantiles)):
            row["quantile_{0:02d}_error_range".format(int(q * 100))] = float(abs(a - b) / width[j])
        fields.append(row)
    correlations = []
    for j in range(len(width)):
        for k in range(j + 1, len(width)):
            truth_defined = actual_sd[j] > width[j] * 1e-12 and actual_sd[k] > width[k] * 1e-12
            output_defined = released_sd[j] > width[j] * 1e-12 and released_sd[k] > width[k] * 1e-12
            a = float(np.corrcoef(original[:, j], original[:, k])[0, 1]) if truth_defined else None
            b = float(np.corrcoef(values[:, j], values[:, k])[0, 1]) if output_defined else None
            correlations.append({"field_a": prepared["names"][j], "field_b": prepared["names"][k],
                "reference_correlation": a, "released_correlation": b,
                "absolute_error": abs(a - b) if a is not None and b is not None else None,
                "reference_defined": truth_defined, "output_defined": output_defined})
    result = aggregate_metrics(values.sum(axis=0), original, prepared)
    for name in ["mean_relative_error_percent", "standard_deviation_relative_error_percent", "standard_deviation_ratio", "wasserstein_range", "ks_statistic", "row_mae_range"]:
        result[name] = _mean([row[name] for row in fields])
    result["row_rmse_range"] = float(np.sqrt(np.mean(((values - original) / width) ** 2)))
    result["quantile_mean_error_range"] = _mean([row[key] for row in fields for key in row if key.startswith("quantile_")])
    result["constant_output_fields"] = sum(row["constant_output"] for row in fields)
    result["undefined_standard_deviation_fields"] = sum(row["standard_deviation_ratio"] is None for row in fields)
    result["correlation_mae_defined_pairs"] = _mean([row["absolute_error"] for row in correlations])
    result["correlation_pairs"] = len(correlations)
    result["reference_undefined_correlation_pairs"] = sum(not row["reference_defined"] for row in correlations)
    result["output_undefined_correlation_pairs"] = sum(not row["output_defined"] for row in correlations)
    residual = values @ prepared["matrix"].T - prepared["rhs"] / prepared["rows"]
    if residual.size:
        scale = abs(prepared["matrix"]) @ width
        result["row_equality_nrms_public_range"] = float(np.sqrt(np.mean((residual / scale) ** 2)))
        result["violating_row_fraction"] = float(np.mean(np.any(abs(residual) > np.array([c.tolerance for c in constraints]), axis=1)))
    else:
        result["row_equality_nrms_public_range"] = None
        result["violating_row_fraction"] = None
    return result, fields, correlations
