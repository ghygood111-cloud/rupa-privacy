# SoftwareX contribution positioning

## Frozen software position

RUPA is a configurable differential privacy release toolkit for fixed-roster,
row-preserving industrial microdata, with field-level risk/utility-aware budget
management and physical-constraint-aware post-processing.

The SoftwareX narrative is limited to the following four primary contributions.

## 1. Configurable industrial privacy-release workflow

RUPA joins schema validation, calibration, field-level budget assignment,
standard numerical and categorical perturbation, optional public-constraint
post-processing, audit generation, and release packaging behind one configuration
and CLI. The contribution is workflow integration for the supported release model,
not a new Laplace or randomized-response mechanism.

Evidence: `src/rupa_privacy/pipeline.py`, `src/rupa_privacy/cli.py`,
`configs/example.yaml`, and both example directories.

## 2. Field-level heterogeneous privacy-budget management

The workflow combines a calibration-derived risk score, a regulatory/entropy
utility weight, public sensitivity, and a configured total epsilon to assign
field-level budgets. The design is interpretable and supports ablations and a
uniform comparator. The categorical `W/(R+c)` path is explicitly heuristic. No
absolute performance or optimality claim is made.

Evidence: `src/rupa_privacy/allocation`, P1 official-baseline outputs, and P1
categorical stress outputs.

## 3. Physical-constraint-aware post-processing and diagnostics

Users may supply public linear equalities. The core package validates dimensions,
finite values, rank, conditioning, redundancy, conflicts, and public-bound
feasibility before release. Accepted systems use weighted deterministic
post-processing and report residuals for each state. Interpolation and clipping
can leave a residual, so the supported claim is residual reduction and transparent
diagnostics, not exact physical consistency.

Evidence: `src/rupa_privacy/physics`, `tests/test_constraint_validation.py`, and
P1 constraint-robustness outputs.

## 4. Release governance and reproducibility

RUPA separates reproducibility and production randomness modes, requires public
bounds and domains, enforces fixed-roster replace-one adjacency, checks disjoint
private calibration subjects, accounts for basic sequential composition across
runs, fails closed on unsafe states, separates public and internal artifacts, and
writes one manifest per run. Reproducible examples and regression checks bind the
software behavior to the reported experiments.

Evidence: P0 tests and reports, `src/rupa_privacy/ledger.py`,
`src/rupa_privacy/io/run.py`, and `scripts/compare_legacy_package.py`.

## Excluded from the contribution list

Joint-NMI is retained as an optional diagnostic. Current validation does not demonstrate a material downstream advantage.

Standard Laplace perturbation, generalized randomized response, and basic
sequential composition are established building blocks and are not presented as
new contributions.
