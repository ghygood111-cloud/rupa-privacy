# Official synthetic example snapshot

These three files are byte-for-byte copies of the existing deterministic official
demo inputs, previously stored in `demo_walkthrough_20260810/inputs`. No data was
regenerated or modified when making the example portable. This directory is
included in the source distribution; the GUI no longer requires an archived
walkthrough directory.

The data is fully synthetic, not an industrial field study. The schema, public
bounds, public categories, declared regulatory priorities and public equalities
are specified by `config.yaml`. Calibration and release use disjoint public IDs.
The configuration uses reproducibility mode with seed 123; do not use it for
confidential production releases.

From the repository/source-distribution root:

```powershell
rupa-privacy validate --calibration examples/official/calibration.csv --release examples/official/release.csv --config examples/official/config.yaml
rupa-privacy run --calibration examples/official/calibration.csv --release examples/official/release.csv --config examples/official/config.yaml --output runs --run-id official_snapshot
rupa-privacy inspect-run runs/official_snapshot --sensitive-target production
```

Use a new run ID for each run. The final public table is
`runs/official_snapshot/release_data.csv`, not either input CSV. Public outputs
exclude the sensitive target and raw/calibration records.
