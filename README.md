# RUPA Privacy

Reproducible research software for task-aware and auditable privacy-preserving
tabular data release. RUPA connects an explicit input contract, independent
calibration, field budgets, established DP mechanisms, public linear-constraint
processing and controlled output files through one Python core.

**Version:** 0.1.0. **Code license:** [BSD-3-Clause](LICENSE).
Repository: [ghygood111-cloud/rupa-privacy](https://github.com/ghygood111-cloud/rupa-privacy).
See [version 0.1.0](https://github.com/ghygood111-cloud/rupa-privacy/releases/tag/v0.1.0)
for installation artifacts and the release verification record. The software is
not an independent privacy-security certification. No archival DOI is assigned.

## Scope and release tasks

| Path | Output and interface | Status |
| --- | --- | --- |
| B: default rows | Protected numerical/categorical rows; Python API, CLI, local Streamlit GUI | Controlled public writer; production authorization through CLI ledger only |
| A: direct totals | DP numerical column totals; research primitives and offline drivers | Confirmed public/synthetic inputs only; no production-ledger entry point |
| C: both views | Protected rows and totals without reconstruction | Evaluation ablation, not an additional production feature |
| D: reconstruction | Row-shaped representation of protected totals and rows; research API/GUI | Exploratory; not a general substitute for original microdata |

Direct aggregate release is appropriate when the task only needs aggregates.
Reconstruction does not improve totals already available in the protected total
view, and can seriously distort variance and correlation. Compare outputs for a
specific task rather than ranking different release objects by one metric.

RUPA provides NMI association diagnostics, complement-entropy/declared-prior
weights, legacy/uniform/optional bounded balanced numerical allocation, Laplace
and generalized randomized response (GRR), public linear-equality processing,
configuration validation, cumulative budget management and hashed manifests.
These are integrated research workflows, not new Laplace/GRR mechanisms.
Association and allocation surrogates are not attack probabilities or universal
accuracy guarantees. The categorical `W/(R+c)` allocation is a heuristic;
uniform categorical allocation remains available.

## Privacy assumptions

- A trusted curator already holds the table. This is not a decentralized LDP
  collection service.
- The roster is fixed and public, with exactly one row per privacy unit.
  Adjacency replaces one unit's declared attributes; it does not hide membership.
- Numerical bounds, complete categorical domains and public linear equalities
  must be declared in advance, not learned from confidential release values.
- Calibration parameters, field selection, tasks and budgets must be fixed
  independently of protected release attributes. Subject separation alone does
  not prove statistical independence. Private calibration subjects do not
  automatically receive DP protection.
- Ideal Laplace/GRR field guarantees compose sequentially. For the research
  two-view workflow, row, total-query and categorical budgets all count:
  `epsilon_all = epsilon_row + epsilon_total + epsilon_categorical`.
  No row-count multiplier or parallel composition across a unit's fields is used.
- Processing only protected views and fixed public metadata is post-processing.
  Raw-dependent evaluation and internal states are not free public diagnostics.
- Repeated confidential releases require cumulative accounting, even with new
  run IDs. The numeric-only RDP conversion is a diagnostic, not a strict mixed
  Laplace/GRR RDP theorem.
- Mathematical mechanisms, finite-precision sampling, validation signals,
  runtime side channels and full system security are different assurance levels.
  Local tests and file hashes do not independently certify the whole system.

Unsupported: unknown/private rosters, add/remove adjacency, repeated rows per
unit, arbitrary free text or multi-valued sets, continuous trajectories,
nonlinear/general inequality constraints, private-domain inference and exact
final physical feasibility. Interpolation and final clipping can reintroduce
linear residuals. See [scope](docs/software_scope_and_non_goals.md).

## Installation

Supported Python range: **3.9-3.11**. The scientific reference environment is
64-bit CPython 3.9.13 on Windows. Exact digests are tied to its locked numerical
dependencies; supported platforms are not a promise of identical binary hashes.

Download the versioned source archive from the release page, or check out the
versioned source before installing:

```powershell
git clone --branch v0.1.0 https://github.com/ghygood111-cloud/rupa-privacy.git
cd rupa-privacy
```

From that checkout or an extracted source archive:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\rupa-privacy.exe --help
```

Optional GUI, research mechanisms, tests and plots:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[demo,research,test]" "matplotlib>=3.5,<3.10"
```

On Linux/macOS use `.venv/bin/python` and `.venv/bin/rupa-privacy` instead. An
internet connection or approved package mirror/cache is required to obtain
dependencies. The core wheel contains the Python package; use a source checkout
or source archive for repository-level GUI, tests and experiments.

## Quick start

After activating the environment, or using the executable path above:

```powershell
rupa-privacy reproduce-example --output runs --run-id example
rupa-privacy inspect-run runs/example --sensitive-target production
```

The official example is synthetic. The final protected table is
`runs/example/release_data.csv`. The run manifest binds approved files to the
same run ID and SHA-256 checksums. Reuse a new run ID for subsequent executions.

For custom data:

```powershell
rupa-privacy validate --calibration CALIBRATION.csv --release RELEASE.csv --config CONFIG.yaml
rupa-privacy run --calibration CALIBRATION.csv --release RELEASE.csv --config CONFIG.yaml --output runs --run-id RUN_ID
rupa-privacy inspect-run runs/RUN_ID --sensitive-target TARGET
```

Both CSVs need nonmissing unique public unit IDs and the released fields. The
calibration CSV additionally needs the calibration target; that target is never
a released field. Schemas and domains are explicit YAML/JSON configuration.

## Python API

```python
from rupa_privacy import RUPAPipeline
from rupa_privacy.io import load_pipeline_config, load_table

settings = load_pipeline_config("examples/official/config.yaml")
calibration = load_table("examples/official/calibration.csv")
release = load_table("examples/official/release.csv")
pipeline = RUPAPipeline(*settings)
pipeline.fit(calibration)
result = pipeline.transform(release)
print(result.release_data.shape)
```

`fit_transform(calibration, release)` connects the two stages. `RUPAResult` also
contains internal row states and original-dependent evaluation: **do not serialize
the entire object for sharing**. Use the approved CLI writer/inspection path.
See [API reference](docs/api_reference.md) and
[privacy conditions](docs/privacy_model.md).

## Local interface

```powershell
python -m streamlit run demo/app.py --server.address 127.0.0.1
```

Load Official Example, open Validation, validate, then run. Successful validation
enters Run; a successful run enters Analysis. Review the tabs and choose
Continue to Export. Failed steps do not advance. The sidebar remains available.
The GUI calls the same core and approved public writers; it is reproducibility-
only. Its **08 Research** page requires the `research` extra and confirmed public
or synthetic inputs. It does not authorize confidential production releases.
Browser downloads follow the browser's normal save settings.

## Modes and budget ledger

**Reproducibility:** fixed seeds on synthetic or explicitly confirmed public
data. For teaching, comparison and repeatability, not confidential release.

**Production:** operating-system-backed randomness; no fixed seed; confidential
release configuration; fixed public roster; persistent ledger and matching CLI
reservation. Production mode is an execution control, not a declaration of
deployment certification. Do not adapt research endpoints to bypass it.

```powershell
rupa-privacy ledger show --ledger PATH
rupa-privacy ledger check --ledger PATH --dataset-id ID --maximum-cumulative-epsilon 10 --additional-epsilon 5
rupa-privacy ledger verify --ledger PATH
```

The default CLI reserves cumulative epsilon atomically before perturbation,
writes/hashes the result and commits after the artifact exists. Failed attempts
and reservations remain governed by the ledger contract. Protect the ledger and
the true history of releases; creating a new ledger does not erase real spend.

## Public outputs and interpretation

| Artifact | Meaning |
| --- | --- |
| `release_data.csv` | Final protected declared fields and public roster ID |
| `privacy_metrics.json` | Basic budget composition and supported diagnostics |
| `physical_metrics.json` | Constraint validation; noisy/projected/interpolated/final residuals |
| `governance_metrics.json` | Fixed-roster and release-contract record |
| `run_config.json`, `manifest.json` | Approved configuration, run identity and file hashes |

Publishable calibration diagnostics can also include risk, utility and field
budgets. Private-calibration fitted details are withheld. Raw tables, sensitive
targets, row intermediates, raw-dependent errors and internal ID checks are not
included in normal public artifacts. There is no automatic attack-model audit
in the default CLI. Low constraint residual is not a proof of statistical utility.

## Examples and paper reproduction

| Example | Status and purpose |
| --- | --- |
| `examples/official` | Fully synthetic default/GUI example |
| `examples/hazardous_waste` | Synthetic enterprise-period mixed-field workflow |
| `examples/water_treatment` | Independent generated plant-day schema and three linear balances |
| `examples/third_party_reuse` | Small synthetic configuration-only reuse fixture; not third-party user adoption |
| `examples/ontario_registration` | Attributed public-data derivatives for a two-binary-field coverage task |

For the exact scientific environment, create Python 3.9 and install:

```powershell
python -m pip install -r reproducibility/requirements-validation-py39.txt
python -m pip install .
python -m pytest
python reproducibility/run_all.py
python scripts/compare_legacy_package.py --output runs/legacy_comparison.csv
```

[Paper reproduction](docs/paper_reproduction.md) provides the four-path commands,
input provenance and comparison rules. Its 25 inputs and 30 paired seeds form
750 bundles and 10,500 shared output states, not 10,500 independent experiments.
Ten generated pairs per synthetic scenario and five blocks from one UCI source
are exploratory reuse, not independent cross-domain validation.

The core-file hash inventory identifies the exact paper snapshot; old historical
test totals are not claims about a fresh installation. The current release report
records actual tests, commands and failures. Author-local verification is not
independent third-party replication. No confidential real industrial dataset or
external deployment is claimed.

## Documentation

- [Documentation index](docs/index.md)
- [API and output boundary](docs/api_reference.md)
- [Privacy model](docs/privacy_model.md)
- [Paper reproduction](docs/paper_reproduction.md)
- [NMI preprocessing](docs/nmi_reproducibility.md)
- [Balanced allocation](docs/balanced_allocation_design_20261022.md)
- [Own-data workflow](docs/how_to_use_rupa_end_to_end.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License and citation

Copyright 2026 高涵（中国矿业大学）. Source code is BSD-3-Clause; see
[LICENSE](LICENSE). Public data and dependencies retain their own licenses and
attributions in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Machine-readable software citation is in [CITATION.cff](CITATION.cff). Cite the
versioned release and record its Git commit for reproducibility. No ORCID,
email, paper DOI or archival DOI is invented. Questions and synthetic bug
reproducers may be submitted through the repository's Issues page; never attach
confidential data or credentials.
