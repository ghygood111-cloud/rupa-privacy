# Reviewer-requested validation

This is an offline research evaluation, not a new DP mechanism or a production
release command. It refuses confidential inputs and private calibration. All task
errors use synthetic or already public references. No original rows or sensitive
target values are exported by the evaluator.

The protocol is frozen in `protocol.json` before execution. Numerical ablations
hold category budgets uniform across all methods to isolate numerical allocation.
They do not introduce a numeric-strategy option into the core API or CLI.
The diffprivlib adapter is an official Laplace mechanism plus RUPA GRR and optional
RUPA postprocessing; it is not a complete competing release platform.

Run from the repository root with the locked scientific environment:

```powershell
python -m pip install --no-deps --target experiments/review_revision_20261021/tools diffprivlib==0.6.6
python -m pytest -q --junitxml=experiments/review_revision_20261021/pytest_numeric.xml
python -m experiments.review_revision_20261021.run --section numeric --output experiments/review_revision_20261021/numeric --pytest-xml experiments/review_revision_20261021/pytest_numeric.xml
python -m pytest -q --junitxml=experiments/review_revision_20261021/pytest_sample.xml
python -m experiments.review_revision_20261021.run --section sample --output experiments/review_revision_20261021/sample --pytest-xml experiments/review_revision_20261021/pytest_sample.xml
```

Each output directory must be unused. Results retain all seeds, failures, stage
metrics, software versions, input/core hashes and a per-draw digest. Sample-size
subsets are nested and selected by a public-key hash before evaluating errors.
Public artifacts are written only through the existing RUPA writer. Reference-
dependent metrics belong to the separate `evaluation` directory, not public runs.
Reusing 30 seeds to compare processing states does not constitute 60 independent
replicates, and seeded demonstrations do not authorize confidential repeated release.
