"""Report structural and allocation effects separately, including adverse metrics."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def main():
    folder = HERE / "hybrid_results"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["status"] == "PASS" and not manifest["failures"]
    raw = pd.read_csv(folder / "raw_metrics.csv")
    out = HERE / "hybrid_analysis"
    out.mkdir(exist_ok=False)
    cases = ["hazardous_waste", "water_treatment", "uci_concrete"]
    strategies = ["uniform_row_projection", "hybrid_uniform", "hybrid_workload"]
    colors = ["#69727C", "#487EAC", "#13806E"]
    main_metrics = ["normalized_squared_error", "median_relative_error_percent", "mean_relative_error_percent",
                    "row_mae_range", "median_standard_deviation_ratio", "maximum_row_equality_residual"]
    means = raw.groupby(["case", "strategy"])[main_metrics].mean()
    means.to_csv(out / "case_mean_metrics.csv")
    ranges, paired = [], []
    rng = np.random.default_rng(20261022)
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.7), layout="constrained")
    for column, case in enumerate(cases):
        frame = raw[raw.case == case]
        for position, (strategy, color) in enumerate(zip(strategies, colors)):
            data = frame[frame.strategy == strategy]
            values = data.median_relative_error_percent.to_numpy()
            low, mid, high = np.quantile(values, [.1, .5, .9])
            ranges.append(dict(case=case, strategy=strategy, median=mid, p10=low, p90=high, randomization_runs=len(values),
                               distinct_datasets=data.dataset.nunique()))
            axes[0, column].errorbar(position, mid, yerr=[[mid-low], [high-mid]], color=color, marker="o", capsize=3)
            dataset_means = data.groupby("dataset").median_relative_error_percent.mean()
            axes[0, column].scatter(position + np.linspace(-.1, .1, len(dataset_means)), dataset_means, color=color, s=11, alpha=.5)
        axes[0, column].set_yscale("log")
        axes[0, column].set_xticks([0, 1, 2], ["Row only", "Hybrid\nuniform", "Hybrid\ntask"], fontsize=8)
        axes[0, column].set_title(case.replace("_", " "), fontsize=10)
        axes[0, column].set_ylabel("Final-table median-field total error (%)", fontsize=8)
        base = frame[frame.strategy == "hybrid_uniform"]
        task = frame[frame.strategy == "hybrid_workload"]
        datasets = sorted(base.dataset.unique())
        for metric in main_metrics[:3]:
            u = base.pivot(index="dataset", columns="seed", values=metric).loc[datasets].to_numpy()
            t = task.pivot(index="dataset", columns="seed", values=metric).loc[datasets].to_numpy()
            d, s = u.shape
            selected_datasets = rng.integers(0, d, size=(5000, d))
            selected_seeds = rng.integers(0, s, size=(5000, d, s))
            sampled_u = u[selected_datasets[:, :, None], selected_seeds].mean(axis=(1, 2))
            sampled_t = t[selected_datasets[:, :, None], selected_seeds].mean(axis=(1, 2))
            differences = sampled_t - sampled_u
            reductions = 100 * (1 - sampled_t / sampled_u)
            lo, hi = np.quantile(differences, [.025, .975])
            rlo, rhi = np.quantile(reductions, [.025, .975])
            ratios = t.mean(axis=1) / u.mean(axis=1)
            paired.append(dict(case=case, metric=metric, datasets=d, seeds_per_dataset=s,
                difference_mean=float(t.mean()-u.mean()), ci95_lower=lo, ci95_upper=hi,
                percent_reduction=100*(1-t.mean()/u.mean()), reduction_ci95_lower=rlo, reduction_ci95_upper=rhi,
                dataset_ratio_median=float(np.median(ratios)), dataset_ratio_min=float(ratios.min()), dataset_ratio_max=float(ratios.max()),
                interpretation="Descriptive paired hierarchical bootstrap over these datasets and their seeds; not broad population or deployment inference"))
            if metric == "normalized_squared_error":
                for index, dataset in enumerate(datasets):
                    seed_indices = rng.integers(0, s, size=(5000, s))
                    bootstrap_ratio = t[index][seed_indices].mean(axis=1) / u[index][seed_indices].mean(axis=1)
                    a, b = np.quantile(bootstrap_ratio, [.025, .975])
                    ratio = ratios[index]
                    axes[1, column].errorbar(index+1, ratio, yerr=[[max(0, ratio-a)], [max(0, b-ratio)]],
                                             color=colors[2], marker="o", markersize=4, capsize=2)
        axes[1, column].axhline(1, color=colors[0], linestyle="--", linewidth=1)
        axes[1, column].set_ylim(0, 1.2)
        axes[1, column].set_xlabel("Public disjoint block" if case == "uci_concrete" else "New calibration/release pair", fontsize=8)
        axes[1, column].set_ylabel("Mean squared loss ratio\nHybrid task / hybrid uniform", fontsize=8)
        for row in range(2):
            ax = axes[row, column]
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
            ax.text(-.18, 1.04, "abcdef"[row*3+column], transform=ax.transAxes, weight="bold")
    fig.savefig(out / "hybrid_equal_budget_validation.png", dpi=300)
    fig.savefig(out / "hybrid_equal_budget_validation.pdf")
    plt.close(fig)
    pd.DataFrame(ranges).to_csv(out / "randomization_ranges.csv", index=False)
    pd.DataFrame(paired).to_csv(out / "paired_hierarchical_summary.csv", index=False)
    public_paths = sorted((folder / "public_runs").glob("*.csv"))
    public_checks = []
    for file in public_paths:
        data = pd.read_csv(file)
        metadata = json.loads(file.with_suffix(".json").read_text())
        assert not any(name in data.columns for name in ("confidential_cost_index", "operating_cost_index", "compressive_strength_mpa"))
        assert np.isclose(metadata["row_epsilon"] + metadata["total_query_epsilon"] + metadata["category_epsilon"], 5)
        public_checks.append({"run_id": metadata["run_id"], "rows": len(data), "columns": data.columns.tolist(), "budget_sum": 5})
    report = {"hybrid_runs": len(raw), "datasets": raw.dataset.nunique(), "representative_public_runs_checked": len(public_checks),
        "primary": "Calibration-normalized column-total squared loss; distinct from median-field absolute relative error",
        "case_means": means.reset_index().to_dict("records"), "paired": paired,
        "maximum_hybrid_public_equality_residual": float(raw[raw.strategy.str.startswith("hybrid")].maximum_row_equality_residual.max()),
        "adverse_result": "Hybrid task has larger median-field absolute relative total error than hybrid uniform in every domain; original row variances are not preserved",
        "scope": "Research-only exploratory revision; external blocks reused after the earlier statistics stage; GUI/EXE/production unchanged"}
    (out / "analysis_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"runs": len(raw), "datasets": raw.dataset.nunique(), "public_checks": len(public_checks),
                      "maximum_hybrid_public_equality_residual": report["maximum_hybrid_public_equality_residual"]}, indent=2))


if __name__ == "__main__":
    main()
