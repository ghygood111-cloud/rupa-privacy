"""Summarize every predeclared output state, including adverse metrics."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PAPER = HERE.parents[1] / "manuscript/softwarex_application_case_20261020"
CASES = ["hazardous_waste", "water_treatment", "uci_concrete"]
TITLES = ["Hazardous waste (10 pairs)", "Water treatment (10 pairs)", "Concrete (5 blocks, one source)"]
COLORS = ["#526778", "#4279a5", "#20866f", "#a87535", "#8b5893"]


def select(frame, path, stage, strategy):
    return frame[(frame.path == path) & (frame.stage == stage) & (frame.strategy == strategy)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path, default=HERE / "analysis")
    args = parser.parse_args()
    results = args.results.resolve()
    manifest = json.loads((results / "manifest.json").read_text())
    if manifest["status"] != "PASS":
        raise ValueError("Complete successful study required")
    out = args.output.resolve()
    out.mkdir(exist_ok=True)
    data = pd.read_csv(results / "raw_metrics.csv")
    keys = ["case", "path", "strategy", "stage", "output_kind"]
    metrics = [n for n in data.select_dtypes(include=["number"]).columns if n != "seed"]
    data.groupby(keys)[metrics].agg(["count", "mean", "median", lambda x: x.quantile(.1), lambda x: x.quantile(.9)]).to_csv(out / "case_summary.csv")
    data.groupby(["dataset"] + keys)[metrics].mean().to_csv(out / "dataset_means.csv")
    means = data.groupby(keys)[metrics].mean().reset_index()
    means.to_csv(out / "case_means.csv", index=False)
    report = {"completed_seed_bundles": manifest["completed_seed_bundles"], "evaluated_states": len(data),
        "independent_external_sources": 1, "exploratory": True, "comparisons": []}
    rng = np.random.default_rng(202610223)
    for case in CASES:
        frame = data[data.case == case]
        for strategy in ("uniform_statistics", "workload_rupa"):
            a = select(frame, "A", "feasible_totals", strategy).sort_values(["dataset", "seed"])
            c = select(frame, "C", "feasible_totals", strategy).sort_values(["dataset", "seed"])
            d = select(frame, "D", "reconstructed", strategy).sort_values(["dataset", "seed"])
            assert a.dataset.tolist() == c.dataset.tolist() == d.dataset.tolist()
            assert a.seed.tolist() == c.seed.tolist() == d.seed.tolist()
            x = a.normalized_total_squared_error.to_numpy().reshape(-1, 30)
            y = d.normalized_total_squared_error.to_numpy().reshape(-1, 30)
            bootstrap = []
            for _ in range(3000):
                datasets = rng.integers(0, len(x), len(x))
                seeds = rng.integers(0, 30, (len(x), 30))
                bootstrap.append(y[datasets[:, None], seeds].mean() / x[datasets[:, None], seeds].mean())
            report["comparisons"].append({"case": case, "strategy": strategy,
                "D_over_A_mean_loss_ratio": float(y.mean() / x.mean()),
                "descriptive_paired_hierarchical_ci95": np.quantile(bootstrap, [.025, .975]).tolist(),
                "C_D_maximum_loss_difference": float(np.max(abs(c.normalized_total_squared_error.to_numpy() - d.normalized_total_squared_error.to_numpy()))),
                "D_correlation_undefined_fraction": float(d.output_undefined_correlation_pairs.sum() / d.correlation_pairs.sum()),
                "D_mean_constant_output_fields": float(d.constant_output_fields.mean())})
    diagnostics = json.loads((results / "reconstruction_diagnostics.json").read_text())
    report["maximum_normalized_target_mismatch"] = max(r["maximum_normalized_target_mismatch"] for r in diagnostics)
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    aggregate_specs = [("B", "default_repair", "uniform_rows", "B\nRows"),
        ("A", "feasible_totals", "uniform_statistics", "A\nUniform"),
        ("A", "feasible_totals", "workload_rupa", "A\nTask"),
        ("C", "feasible_totals", "uniform_statistics", "C/D\nUniform"),
        ("C", "feasible_totals", "workload_rupa", "C/D\nTask")]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.0), layout="constrained")
    for index, (case, title) in enumerate(zip(CASES, TITLES)):
        ax = axes[index]
        for j, (path, stage, strategy, label) in enumerate(aggregate_specs):
            f = select(data[data.case == case], path, stage, strategy)
            values = f.normalized_total_squared_error
            lo, med, hi = np.quantile(values, [.1, .5, .9])
            ax.vlines(j, lo, hi, color=COLORS[j], linewidth=2)
            ax.scatter([j], [med], color=COLORS[j], s=40, zorder=3)
            by_dataset = f.groupby("dataset").normalized_total_squared_error.mean()
            ax.scatter(np.full(len(by_dataset), j) + np.linspace(-.12, .12, len(by_dataset)), by_dataset,
                facecolors="none", edgecolors=COLORS[j], s=15, linewidth=.7)
        ax.set_yscale("log")
        ax.set_xticks(range(5), [s[3] for s in aggregate_specs], fontsize=6.5)
        ax.set_title(title, fontsize=7)
        ax.set_ylabel("Normalized squared total error", fontsize=7)
        ax.tick_params(axis="y", labelsize=7)
        ax.text(-.13, 1.04, "abc"[index], transform=ax.transAxes, weight="bold", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
    fig.savefig(out / "four_path_totals.png", dpi=300)
    fig.savefig(out / "four_path_totals.pdf")
    plt.close(fig)
    row_specs = [("B", "default_repair", "uniform_rows", "B repaired"),
        ("C", "clipped_noisy", "uniform_statistics", "C row"),
        ("D", "reconstructed", "uniform_statistics", "D uniform"),
        ("D", "reconstructed", "workload_rupa", "D task")]
    fig, axes = plt.subplots(3, 3, figsize=(7.2, 6.8), layout="constrained")
    rows = [("standard_deviation_relative_error_percent", "Mean field SD relative error (%)"),
        ("wasserstein_range", "Mean Wasserstein / public range"),
        ("correlation_mae_defined_pairs", "Pearson error (defined pairs only)")]
    for column, (case, title) in enumerate(zip(CASES, TITLES)):
        for row, (metric, ylabel) in enumerate(rows):
            ax = axes[row, column]
            for j, (path, stage, strategy, label) in enumerate(row_specs):
                f = select(data[data.case == case], path, stage, strategy)
                values = f[metric].dropna()
                if len(values):
                    lo, med, hi = np.quantile(values, [.1, .5, .9])
                    ax.vlines(j, lo, hi, color=COLORS[j], linewidth=2)
                    ax.scatter([j], [med], color=COLORS[j], s=30)
                if row == 2:
                    missing = f.output_undefined_correlation_pairs.sum() / f.correlation_pairs.sum()
                    ax.text(j, .98, "{0:.0f}% NA".format(100 * missing), transform=ax.get_xaxis_transform(),
                        ha="center", va="top", fontsize=7)
            ax.set_xticks(range(4), [s[3] for s in row_specs], fontsize=6)
            ax.set_ylabel(ylabel, fontsize=7)
            ax.tick_params(axis="y", labelsize=7)
            if row == 0:
                ax.set_title(title, fontsize=7)
            if row == 2:
                ax.set_ylim(0, 1.1)
            ax.text(-.15, 1.02, "abcdefghi"[row * 3 + column], transform=ax.transAxes, weight="bold", fontsize=9)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
    fig.savefig(out / "row_fidelity.png", dpi=300)
    fig.savefig(out / "row_fidelity.pdf")
    plt.close(fig)
    workflow(out)
    print(json.dumps(report, indent=2))


def workflow(out):
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    ax.set(xlim=(0, 11), ylim=(0, 4.1))
    ax.axis("off")
    def box(x, y, w, h, text, color="#edf2f5"):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=color, edgecolor="#63717b", linewidth=.9))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=7)
    def arrow(a, b):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, linewidth=1, color="#526778"))
    ax.text(.15, 3.83, "Two-view research   |   confirmed public or synthetic inputs only", fontsize=9, weight="bold")
    box(.15, 1.4, 2, 1.2, "Public contract\nIndependent\ncalibration\nFixed allocation")
    box(2.9, 2.35, 2.2, .85, "Protected rows\nNumerical budget\nGRR budget")
    box(2.9, .85, 2.2, .85, "Protected totals\nTotal-query budget", "#e9f4ef")
    box(5.9, 1.4, 2.3, 1.2, "DP-only reconstruction\nFeasible means\nNullspace mapping\nBounded contraction")
    box(8.9, 1.4, 1.95, 1.2, "Research outputs\nReconstructed rows\nDiagnostics")
    arrow((2.15, 2.2), (2.9, 2.78))
    arrow((2.15, 1.8), (2.9, 1.28))
    arrow((5.1, 2.78), (5.9, 2.2))
    arrow((5.1, 1.28), (5.9, 1.8))
    arrow((8.2, 2), (8.9, 2))
    ax.text(5.45, 3.35, r"$\epsilon_{row}+\epsilon_{total}+\epsilon_{cat}=\epsilon_{all}$", fontsize=10, ha="center")
    ax.plot([.15, 10.85], [.55, .55], color="#bbc4c9", linewidth=.8)
    ax.text(.15, .22, "Default production CLI + ledger remain separate; no confidential-release authorization here.", fontsize=7)
    fig.savefig(out / "two_view_workflow.png", dpi=300, bbox_inches="tight")
    fig.savefig(out / "two_view_workflow.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
