# RUPA Python API and release boundary

## Supported in-memory workflow

`RUPAPipeline`, `RUPAResult`, configuration/model classes and the version are the
small supported Python surface. This example uses existing calculations only.

```python
from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config, load_table

schema, privacy, constraints, prior, adjacency, accounting = load_pipeline_config(
    "examples/official/config.yaml"
)
calibration = load_table("examples/official/calibration.csv")
release = load_table("examples/official/release.csv")
pipeline = RUPAPipeline(schema, privacy, constraints, prior, adjacency, accounting)
pipeline.fit(calibration)
result = pipeline.transform(release)
print(result.release_data.shape)
```

`fit` estimates calibration risk, utility and budgets, then freezes parameters.
`transform` applies perturbation and public-constraint post-processing.
`fit_transform(calibration, release)` is the convenience entry point. Public
bounds/categories are configured, not inferred from private release values.

This example is synthetic and reproducibility-only. The production CLI performs
ledger authorization/reservation; do not bypass it by adapting this example.

## Result is not a public serialization format

`RUPAResult` also carries internal row-level intermediate states and raw-dependent
utility diagnostics. Never serialize the whole object for sharing. The official
public writer is used by CLI/GUI; prefer the CLI for durable public packaging and
production governance.

```powershell
rupa-privacy run --calibration examples/official/calibration.csv --release examples/official/release.csv --config examples/official/config.yaml --output runs --run-id api_reference_release
rupa-privacy inspect-run runs/api_reference_release --sensitive-target production
```

`rupa_privacy.io.validate_public_run(directory, sensitive_target=...)` checks the
existing artifact hash, run identity and release-column safety contract. It does
not prove data accuracy or independently certify the mechanism.

## Published outputs

| Artifact | Meaning | Not evidence of |
|---|---|---|
| `release_data.csv` | Protected fields and fixed public roster ID | Original records |
| `risk_scores.csv` | Publishable calibration association/bin diagnostics | Attack success probability |
| `utility_weights.csv` | Publishable allocation priorities | Measured final accuracy |
| `epsilon_allocation.csv` | Publishable field budgets/public sensitivities | Universally optimal allocation |
| `privacy_metrics.json` | Existing accounting/numeric diagnostics | A new privacy theorem |
| `physical_metrics.json` | Validation and four-stage residuals | Exact final feasibility |
| `utility_metrics.json` | Public withholding notice | Released raw-dependent evaluation |
| `attack_metrics.json` | Explicit current audit state | An automatic attack benchmark |
| `manifest.json` | Identity and integrity of listed files | Encryption or digital signature |

Private-calibration fitted details may be withheld by the writer. GUI is
reproducibility-only, not a production release console.
