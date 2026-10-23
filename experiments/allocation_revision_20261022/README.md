# Allocation revision reproduction

This author-authorized source revision adds an optional balanced numerical
policy while retaining `legacy_rupa` as the default. It is not a rebuilt Windows
EXE or a new licensed public release. Read
`docs/balanced_allocation_design_20261022.md` for its exact surrogate definition.

The accepted `results/` directory records 1620 completed final states, zero
failures and unchanged source hashes during the experiment. All cases are
synthetic. Settings were frozen before evaluating the new policy, but known
legacy failures motivated the design, so the evaluation is exploratory.

From the repository root, with Python 3.9 and locked dependencies installed:

```powershell
python -m pip install -r reproducibility/requirements-validation-py39.txt
python -m pytest --junitxml=experiments/allocation_revision_20261022/pytest_rerun.xml
python experiments/allocation_revision_20261022/run.py --output experiments/allocation_revision_20261022/results_rerun --pytest-xml experiments/allocation_revision_20261022/pytest_rerun.xml
python reproducibility/run_all.py
```

Use an unused output directory. Do not overwrite the accepted evidence. The full
matrix can take several minutes. `raw_metrics.csv`, `summary.csv`,
`paired_differences.csv`, `field_budgets.csv` and `manifest.json` retain all cells;
representative first-seed public runs and their configurations accompany them.
The paper values are generated with `prepare_manuscript.py` from accepted CSVs.
Its external-control/sample-size inputs remain in
`experiments/review_revision_20261021/numeric_v2` and `sample_v2`.
