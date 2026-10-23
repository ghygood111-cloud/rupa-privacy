# Software scope and non-goals

## Supported contract

| Area | Supported behavior |
|---|---|
| Data object | Tabular microdata with numerical and categorical fields |
| Roster | Fixed, explicitly public roster |
| Privacy unit | Exactly one row per configured public unit ID |
| Adjacency | `fixed_roster_replace_one` |
| Public metadata | Numeric bounds, complete category domains, schema, regulatory priors, and optional constraints |
| Calibration | Synthetic, confirmed public, or subject-disjoint private calibration |
| Constraints | Public linear equalities over released numerical fields |
| Accounting | Pure epsilon-DP basic sequential composition for one mixed-mechanism release and cumulative ledger accounting |
| Execution | Single-machine Python API and CLI |

## Not supported

The current software does not support:

- add/remove adjacency;
- a private or unknown roster;
- multiple rows per privacy unit;
- streaming or continually observed releases;
- nonlinear constraints or inequalities;
- constraints learned from private release records;
- automatic inference of bounds or category domains from private data;
- arbitrary query workloads;
- general synthetic-data generation;
- distributed execution;
- a formal privacy guarantee for private calibration subjects;
- guaranteed exact feasibility after interpolation and clipping;
- certification against a law, policy, or regulatory standard.

## Failure policy

Unsupported adjacency, metadata, calibration, category, and constraint cases are
rejected with an error. The package does not guess missing public metadata, infer
private domains, silently discard constraints, or replace a rejected constraint
system with a pseudoinverse solution.

For `disjoint_private` calibration, the formal release guarantee concerns release
subjects under the configured adjacency. The calibration cohort must be disjoint,
its derived parameters remain internal, and the package does not claim that those
calibration subjects receive the same DP guarantee.
