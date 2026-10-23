# Task-aware statistics and joint-view reconstruction

This is an experimental algorithm revision, not the existing GUI/production path.
It retains the old row-release default and old reference outputs. Do not use it
to publish confidential inputs: the runner explicitly refuses production mode,
confidential release data and private calibration.

## What changed

`src/rupa_privacy/allocation/workload.py` allocates epsilon for the actual variance
of a declared linear statistical workload. The full option retains a calibrated
risk-surrogate cap and field budget bounds. `physics/reconstruction.py` accepts
only protected rows, protected totals and public metadata. It reconstructs bounded
rows with the protected column totals and supported public equalities. Both views
must be privatized, and their epsilon costs must be added; this is not a free
query or a stronger privacy guarantee.

The pure-statistics experiment changes the output object to totals/means. The
separate hybrid experiment keeps a row table and divides numerical epsilon 50/50
between row and total views. Both report all metrics, including variance collapse
and metrics on which uniform allocation is better. Neither claims recovery of
individual source rows or preserved arbitrary correlations.

## Reproduction

Use Python 3.9 with the supplied optional dependencies:

The retained original experiment used diffprivlib 0.6.6 in a research-only
dependency directory. Its metadata requires NumPy 2. To preserve the accepted
NumPy 1.26.4 environment, the updated install recipe uses 0.6.5. The complete
Laplace module is byte-identical (SHA-256
`8400b599cb94484618d6ebc00143ad420001b201731b3d25b2951f9af4aed84d`);
50 retained hybrid tables were compared against the new API, with maximum
absolute numeric difference below 1e-10. The historical manifests are retained,
not relabelled as new 0.6.5 runs. Installed-environment versions must still be
recorded for any rerun.

```powershell
python -m pip install -r experiments/task_statistics_20261022/requirements.txt
python -m pip install --no-deps -e .
python -m pytest --junitxml=experiments/task_statistics_20261022/pytest_rerun.xml
python -m experiments.task_statistics_20261022.run --output experiments/task_statistics_20261022/results_rerun --pytest-xml experiments/task_statistics_20261022/pytest_rerun.xml
python -m experiments.task_statistics_20261022.run_hybrid --output experiments/task_statistics_20261022/hybrid_rerun --pytest-xml experiments/task_statistics_20261022/pytest_rerun.xml
```

The attributed, prepared UCI public data are in `external/`. `prepare_external.py`
is needed only to repeat the upstream download into an absent `external/` folder;
it intentionally refuses to overwrite the retained source. Data are I-Cheng Yeh,
Concrete Compressive Strength, UCI DOI 10.24432/C5PK67, CC BY 4.0. The protected
benchmark unit is one published measurement, not a company or all measurements
from one recipe. Exact recipes are nevertheless kept together in partitioning.
The means of kg/m3 ingredients are recipe statistics, not regional waste tonnage.

The first protocol was frozen before new numeric outcomes. The hybrid protocol
was frozen after the statistics evaluation, before hybrid results. It is an
exploratory follow-up and does not relabel reused public blocks as newly unseen
data. Twenty generated calibration/release pairs are not external deployment;
the separate concrete dataset is one public external source, not broad adoption.

`fig6_reanalysis/` reuses the original 1620-state study only to add P10/P90 ranges
and paired-seed intervals. It is not new data or independent generalization.
The frozen earlier study and existing Word/EXE/ZIP remain unchanged. New figures
and a response explaining which claims are supported are provided separately.

## Results and manuscript alignment

- Detailed Chinese report: `../../docs/task_aware_algorithm_revision_20261022.md`.
- Matched draft paragraphs and captions: `PAPER_EVIDENCE_CN.md`.
- Row-table analysis: `hybrid_analysis/analysis_report.json` and
  `hybrid_analysis/paired_hierarchical_summary.csv`.
- Equal-budget row-table plot: `hybrid_analysis/hybrid_equal_budget_validation.png`.
- Earlier Figure 6 with uncertainty: `fig6_reanalysis/figure6_with_uncertainty.png`.

The task allocator improves the declared squared loss relative to uniform within
the same hybrid method, but worsens median field-total relative error. The much
larger change from the old row-only method comes from the protected total view
and reconstruction, not allocation alone. Original variances remain distorted.
