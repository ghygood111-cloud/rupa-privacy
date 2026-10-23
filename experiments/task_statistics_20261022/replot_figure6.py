"""Add honest within-table randomization uncertainty to the original Figure 6."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.review_revision_20261021.analysis import bootstrap_mean_difference

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    source = ROOT / "experiments/allocation_revision_20261022/results/raw_metrics.csv"
    raw = pd.read_csv(source)
    raw = raw[raw.repair_alpha == .98]
    out = HERE / "fig6_reanalysis"
    out.mkdir(exist_ok=False)
    cases = ["hazardous_waste", "water_treatment", "hazardous_waste_holdout"]
    colors = {"legacy_rupa": "#B57637", "uniform": "#65717C", "balanced_rupa": "#137E72"}
    metric = "median_field_total_error_percent"
    statistics, paired = [], []
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.7), layout="constrained")
    for index, case in enumerate(cases):
        frame = raw[raw.case == case]
        for strategy, color in colors.items():
            curve = []
            for epsilon in [1, 5, 20]:
                values = frame[(frame.strategy == strategy) & (frame.epsilon == epsilon)][metric].to_numpy()
                assert len(values) == 30
                median = float(np.median(values))
                low, high = np.quantile(values, [.1, .9])
                statistics.append(dict(case=case, strategy=strategy, epsilon=epsilon, median=median, p10=low, p90=high, runs=30))
                curve.append((median, low, high))
            points = np.asarray(curve)
            axes[0, index].plot([1, 5, 20], points[:, 0], color=color, marker="o", markersize=4, label=strategy)
            axes[0, index].fill_between([1, 5, 20], points[:, 1], points[:, 2], color=color, alpha=.13)
        axes[0, index].set_title(case.replace("_", " "), fontsize=9)
        axes[0, index].set_xlabel("Total epsilon")
        axes[0, index].set_ylabel("Median-field total error (%)", fontsize=8)
        for position, epsilon in enumerate([1, 5, 20]):
            a = frame[(frame.strategy == "balanced_rupa") & (frame.epsilon == epsilon)].sort_values("seed")
            b = frame[(frame.strategy == "uniform") & (frame.epsilon == epsilon)].sort_values("seed")
            assert a.seed.tolist() == b.seed.tolist()
            info = bootstrap_mean_difference(a[metric], b[metric])
            paired.append(dict(case=case, epsilon=epsilon, **info))
            delta = a[metric].to_numpy() - b[metric].to_numpy()
            axes[1, index].scatter(position + np.linspace(-.1, .1, 30), delta, color=colors["balanced_rupa"], alpha=.3, s=10)
            axes[1, index].errorbar(position, info["mean_difference"],
                yerr=[[info["mean_difference"] - info["ci95_lower"]], [info["ci95_upper"] - info["mean_difference"]]],
                color="black", marker="o", markersize=4, capsize=3)
        axes[1, index].axhline(0, color=colors["uniform"], linestyle="--", linewidth=1)
        axes[1, index].set_xticks([0, 1, 2], ["1", "5", "20"])
        axes[1, index].set_xlabel("Total epsilon")
        axes[1, index].set_ylabel("Balanced minus uniform (pp)", fontsize=8)
        for row in range(2):
            ax = axes[row, index]
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
            ax.text(-.18, 1.04, "abcdef"[row * 3 + index], transform=ax.transAxes, weight="bold")
    axes[0, 0].legend(frameon=False, fontsize=7)
    fig.savefig(out / "figure6_with_uncertainty.png", dpi=300)
    fig.savefig(out / "figure6_with_uncertainty.pdf")
    plt.close(fig)
    pd.DataFrame(statistics).to_csv(out / "seed_ranges.csv", index=False)
    pd.DataFrame(paired).to_csv(out / "paired_differences.csv", index=False)
    (out / "manifest.json").write_text(json.dumps({"source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "scope": "Reanalysis of the original fixed calibration datasets; not new independent data or generalization evidence",
        "bands": "Observed P10/P90 across 30 seeds, not confidence intervals",
        "lower_panels": "All paired seed differences; point/whisker is a descriptive paired-bootstrap mean and 95% interval"}, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
