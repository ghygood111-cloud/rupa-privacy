# Privacy model and limits

The supported default release assumes a trusted curator, a fixed public roster,
one row per public unit and replace-one adjacency. A neighbouring table replaces
one unit's declared attributes. Membership, unknown rosters and repeated events
per individual are not covered.

Public bounds `[L_j,U_j]` give numerical replacement sensitivity
`Delta_j=U_j-L_j`. Changing one row changes one coordinate of a whole-column
query, and a column sum by at most the same range. Ideal independent Laplace
noise uses scale `Delta_j/epsilon_j`. GRR uses the declared complete domain and
retention probability `exp(epsilon)/(exp(epsilon)+K-1)` for `K>=2`.

Schema, field selection, calibration parameters, workload, public constraints and
budgets must remain fixed across neighbouring release tables. Calibration must
not depend on protected release values. Disjoint subject IDs are a necessary
check in relevant modes, not a proof of independence or private-calibration DP.
Private calibration needs a separate privacy mechanism/accounting treatment if
its subjects must be protected; RUPA does not supply that guarantee by omission.

Each unit's fields and views compose sequentially. The ideal basic bound is
the sum of enabled row, total-query and categorical field budgets. It is not
parallel composition across a unit's fields, and is not multiplied by row count.
The numeric Laplace RDP conversion is diagnostic only for mixed mechanisms.

Projection, interpolation, clipping, reconstruction and residuals cost no extra
budget only when they depend exclusively on protected views and fixed public
information. Original-dependent error, sensitive targets, internal states and
private adaptive tuning are not automatically safe outputs.

Confidential repeated releases must accumulate spend. The supported production
CLI maintains a persistent ledger and uses OS-backed randomness. Reproducibility
mode and research interfaces require synthetic or confirmed public release
inputs, have fixed seeds and do not authorize confidential releases.

The ideal probability argument does not certify finite-precision sampling,
validation success/failure signals, timing, operational metadata, surrounding
infrastructure or legal compliance. These require independent review. Manifests
provide file integrity and provenance, not encryption, digital signatures or
privacy certification.
