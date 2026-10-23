# SoftwareX statement of need

Differential privacy libraries already provide mature building blocks. IBM
diffprivlib supplies standard mechanisms and accounting utilities. OpenDP supplies
tools for constructing and validating formal DP computations. trasgoDP addresses
row-level tabular release under a local differential privacy model. RUPA does not
replace these projects and does not present Laplace perturbation or generalized
randomized response as new mechanisms.

The software need addressed here is narrower: a researcher preparing a
fixed-roster, row-preserving industrial microdata release must coordinate public
schema declarations, independent calibration, field-level budget decisions,
mixed numerical/categorical perturbation, public linear-balance equations,
residual diagnostics, cumulative release accounting, and public/internal artifact
separation. Implementing those decisions independently across scripts makes the
privacy unit, metadata provenance, and release boundary difficult to audit.

RUPA packages that workflow into a typed Python API, YAML/JSON configuration, and
CLI with fail-closed validation. Its distinguishing value is the integration of
field-level risk/utility-aware budget management with public linear-constraint
post-processing and release governance for the stated scope. It is not a claim
that RUPA's base mechanisms are stronger than those in diffprivlib or OpenDP.

P1 validation provides bounded evidence for this need. The same unchanged core
ran two different semi-synthetic industrial schemas through configuration alone;
the formal diffprivlib baseline and the trasgoDP near-neighbor were actually run;
and categorical, scalability, constraint, and attack-audit paths recorded both
successes and failures. Full RUPA did not show a clear dominant advantage over
the strongest uniform-plus-projection comparator, so the SoftwareX rationale is
workflow reuse, explicit governance, diagnostics, and reproducibility rather than
algorithmic superiority.

Relevant project sources:

- diffprivlib: https://github.com/IBM/differential-privacy-library
- OpenDP: https://github.com/opendp/opendp
- trasgoDP: https://github.com/IFCA-Advanced-Computing/trasgoDP
- local comparison scope: `experiments/p1/official_baselines/BASELINE_SCOPE.md`
