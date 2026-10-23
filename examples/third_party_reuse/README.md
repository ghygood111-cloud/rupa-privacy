# Third-party reuse exercise

This small synthetic package tests whether a new user can install and run RUPA
without modifying Python source. It contains an independent calibration table, a
release table with a separate public roster, two categorical fields, public
bounds/domains, and one public water-balance equality.

From the repository root, create a clean environment and run only installed CLI
commands:

```powershell
python -m venv .venv-reuse
.\.venv-reuse\Scripts\python.exe -m pip install --upgrade "pip>=23" "setuptools>=68" "wheel>=0.41"
.\.venv-reuse\Scripts\python.exe -m pip install .
.\.venv-reuse\Scripts\rupa-privacy.exe validate --calibration examples/third_party_reuse/calibration.csv --release examples/third_party_reuse/release.csv --config examples/third_party_reuse/config.yaml
.\.venv-reuse\Scripts\rupa-privacy.exe run --calibration examples/third_party_reuse/calibration.csv --release examples/third_party_reuse/release.csv --config examples/third_party_reuse/config.yaml --output examples/third_party_reuse/runs --run-id reuse_demo
.\.venv-reuse\Scripts\rupa-privacy.exe inspect-run examples/third_party_reuse/runs/reuse_demo --sensitive-target energy_cost_index
```

Expected command-level behavior:

- `validate` reports constraint `PASS`, rank `1/1`, and a finite condition number;
- `run` creates a single `reuse_demo` directory;
- `inspect-run` reports a valid public run;
- `release_data.csv` contains `unit_id` and the six declared release fields;
- neither the sensitive target nor calibration/raw records appear in the public run.

The example uses `categorical_budget_strategy: uniform` as a conservative baseline
and disables the optional joint-NMI diagnostic. The final constraint residual can
be nonzero because `repair_alpha` is below one and public-bound clipping follows
projection.

For an actual independent evaluation, follow
`docs/third_party_reuse_protocol.md` and record failures without editing
`src/rupa_privacy`.
