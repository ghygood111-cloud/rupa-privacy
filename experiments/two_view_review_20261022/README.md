# Four-path reviewer follow-up

This is an exploratory, numerical-channel-only evaluation of the existing API.
It does not change the scientific package or authorize confidential releases.
The protocol was fixed before these outcomes but reuses already examined input
sources. The five concrete blocks are one external source, not five domains.

## Reproduce

Use the supported Python environment and the project's locked numerical
dependencies, with the `research` extra (official diffprivlib 0.6.5). From the
repository root, with unused result destinations:

```powershell
python -m pytest -q --junitxml=experiments/two_view_review_20261022/pytest_rerun.xml
python -m experiments.two_view_review_20261022.run --output experiments/two_view_review_20261022/results_rerun --pytest-xml experiments/two_view_review_20261022/pytest_rerun.xml
python -m experiments.two_view_review_20261022.analyze --results experiments/two_view_review_20261022/results_rerun --output experiments/two_view_review_20261022/analysis_rerun
```

The runner requires a fresh full passing test gate and refuses to overwrite a
result directory. It uses the unchanged synthetic generators and attributed UCI
input blocks, never historical metric output. Both protocol JSONs and all core
Python files are hashed. No `.npz` inputs are used.

## Output objects and findings

- A: totals only, epsilon five; raw and feasible targets, no row metrics.
- B: rows only, epsilon five; clipped-noise and default-repair states.
- C: row view plus total view, epsilon 2.5 each; evaluated separately.
- D: reconstruction of C's same draws, no additional source query.

Uniform and task-directed totals are retained. All 25 inputs and 30 seeds are
included: 750 paired bundles, 10,500 output evaluation states, zero failures.
Shared stages are not independent experiments. The primary loss is explicitly
calibration-normalized; relative totals, means, standard deviations, quantiles,
Wasserstein, KS, correlations, row errors and constraint checks are retained.
Missing/undefined metrics are not zero-filled. Offline truth-dependent metrics
are evaluation material, not approved public research-package content.

Direct feasible aggregates beat reconstructed rows on total squared loss at
equal combined budget. Task-directed D/A loss ratios are 3.887, 4.000 and 3.778.
C's feasible target and D's sums agree to a maximum public-range-normalized
difference of 4.881e-15. Reconstruction adds a constrained row representation,
not more accurate totals. Distribution and correlation distortions rule out
generic original-microdata replacement claims. See `analysis/case_means.csv`,
`analysis/case_summary.csv`, `analysis/dataset_means.csv` and `analysis/report.json`.

The current paper has a separate privacy proof and artifact-dependency
inventory. Ideal random-channel composition is distinguished from fixed-seed
research, unsupported confidential inputs and operational timing side channels.

## Tests and regression

`pytest_before.xml` and `pytest_after.xml`: 418 passed, 23 existing warnings.
`legacy_comparison.csv`: all four array differences zero, noisy/final digests
unchanged. The standard reproduction script also passes official, water,
third-party reuse, manifest, legacy and release-hash checks.
