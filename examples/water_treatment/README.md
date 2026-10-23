# Semi-synthetic water-treatment example

This directory demonstrates that the unchanged `rupa_privacy` core can operate on a
second industrial schema by changing only data and configuration. The scenario is
inspired by the openly licensed UCI Water Treatment Plant dataset
(https://archive.ics.uci.edu/dataset/106/water+treatment+plant, CC BY 4.0), but all
rows here are independently generated from the equations in `generate_data.py`.

Generate or regenerate the inputs:

```powershell
python examples/water_treatment/generate_data.py
```

Validate the reproducibility configuration:

```powershell
rupa-privacy validate --calibration examples/water_treatment/calibration.csv --release examples/water_treatment/release.csv --config examples/water_treatment/config_reproducibility.yaml
```

Run the fixed-seed demonstration:

```powershell
rupa-privacy run --calibration examples/water_treatment/calibration.csv --release examples/water_treatment/release.csv --config examples/water_treatment/config_reproducibility.yaml --output experiments/p1/second_domain/runs --run-id water-treatment-repro-20260804
```

`config_production_template.yaml` is a template only. Before a production run, the
author must replace the dataset ID, confirm disjoint confidential rosters, use the
persistent ledger, and authorize the release. Production randomness has no fixed seed.

See `SCHEMA.md`, `CONSTRAINTS.md`, and `EXPECTED_OUTPUT.md` for scope and expected
artifacts.

