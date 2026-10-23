# RUPA Reviewer Tasks

Version 0.1.0 | Windows Debug evaluation | Not a formal release

Do not inspect source code or developer documentation before your first attempt.
Record PASS / FAIL / NOT TESTED and an explanation for each task. There are no
pre-filled reviewer scores. The supplied evidence is a developer-executed reference,
not an independent review. Record your own run_id and keep your screenshots separately.

The actual home button is **Load official synthetic example**, referred to below
as **Load Official Example**. Loading does not auto-navigate. Use the left workflow
navigation; expand its arrow if it is collapsed. Data and Configuration are optional
inspection pages for the default case; Validation must pass before Run.

## Task 1 — First impression

- Can I identify RUPA's purpose within 30 seconds?
- Do I know the first action to take?
- Does the page look like research software rather than an unfinished demo?
- Is there a control I expected to click that is only decorative?

Result: ____ | Time: ____ | Notes: ____

## Task 2 — Load example

Click **Load Official Example**. Check Data / Configuration become Ready.
Optionally visit **02 Data** and **03 Configuration** without changing settings.
Explain Calibration dataset, Release dataset and Configuration in your own words.

Result: ____ | Explanation: ____ | Unexpected behavior: ____

## Task 3 — Validation

Open **04 Validation**, click **Run validation**.
Is the button easy to find? Is **VALIDATION PASSED** clear? Are the checks
understandable? Is any information too technical?

Result: ____ | Screenshot: validation.png | Notes: ____

## Task 4 — Run

Open **05 Run**, click **Run RUPA**.
Do I understand reproducibility mode and total epsilon? Is completion clear?
Do I know how to enter Analysis? Record the actual run_id.

Result: ____ | Run ID: ____ | Screenshot: run_complete.png | Notes: ____

## Task 5 — Risk

Open **06 Analysis → Risk**.
Can I see that attributes have different calibration risks? Is the chart readable?
Does the page mistakenly suggest NMI is a formal DP privacy guarantee?
Correct interpretation: NMI is a calibration association diagnostic, not an attack
success probability and not the DP guarantee.

Result: ____ | Screenshot: risk.png | Explanation / confusion: ____

## Task 6 — Utility

Inspect entropy weight, regulatory prior and final utility weight.
Can I explain these as allocation priorities rather than model prediction accuracy?

Result: ____ | Screenshot: utility.png | Explanation / confusion: ____

## Task 7 — Privacy Allocation

Inspect **Epsilon Allocation**. Are different field budgets understandable?
Are total, numerical and categorical budgets clear? The default total is 5,
with numerical 4.6 and categorical 0.4. Larger epsilon is a weaker privacy bound,
not automatically a better result.

Result: ____ | Screenshot: allocation.png | Notes: ____

## Task 8 — Constraint Residuals (priority task)

Inspect DP perturbation, Full projection, Interpolation and Final clipping.
Locate the **Violation rate** column (violation_rate in the JSON).
Are all four stages visible? Is any column or chart clipped? Is horizontal scrolling
or an expanded table necessary? Does the page imply perfect final feasibility?

Correct statement: **Supported public equality residuals are reduced, but exact
final feasibility is not guaranteed.** In the bundled official example, final
violation_rate is 1.0 despite much smaller residuals. Full projection is an
intermediate stage, not the final exported dataset.

Result: ____ | Final violation rate: ____ | Screenshot: residuals.png
Risk of misunderstanding / wording to improve: ____

## Task 9 — Released Data

Inspect **Released Data**. Check 1000 rows and the configured released fields plus
the public roster ID. Sensitive target values, raw-only columns and original private
rows must not be displayed in this tab. A public ID is intentionally retained.
This does not mean every categorical value must change or no numerical value can
coincide with an input. Sensitive-target field names may occur in schema metadata;
that is not disclosure of sensitive-target values.

Result: ____ | Screenshot: released_data.png | Notes: ____

## Task 10 — Audit

Inspect run_id, version, execution mode, manifest verification and artifacts.
Does this look like a traceable software run rather than just a result table?
The GUI is reproducibility-only; this audit is not production-ledger authorization.

Result: ____ | Screenshot: audit.png | Notes: ____

## Task 11 — Export

Click every existing download button; no fixed browser save directory is required.
There is no need to use commands. Record the filename, whether download triggered
and what you believe the file contains. Analysis also has two download controls.

| Location / button | Download triggered YES / NO | Filename | Meaning understood? |
|---|---|---|---|
| Analysis → Released Data → Download released CSV | | release_data.csv | |
| Analysis → Constraint Residuals → Download residual plot data | | run_id_constraint_stages.csv | |
| Export → Download released dataset | | release_data.csv | |
| Export → Download public run package | | run_id_public.zip | |
| Export → Download config.yaml | | config.yaml | |

Result: ____ | Screenshot: export.png | Notes: ____

## Finish

Complete REVIEW_FEEDBACK.md. Report any failure even if a later retry succeeds.
Do not upload confidential data. Do not bypass Windows security warnings.
Download location is controlled by the browser's own settings.
