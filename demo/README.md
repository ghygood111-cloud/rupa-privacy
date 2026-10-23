# RUPA Local Demo / Tutorial UI

This folder contains a local Streamlit demonstration for the locally validated RUPA
research software. It calls the existing `rupa_privacy` API and writes public
artifacts with the existing package exporter. No privacy mechanism is
implemented in the interface.

## Start

Double-click `start_demo.bat`, or run:

```powershell
python -m pip install ".[demo,research]"
streamlit run demo/app.py
```

The batch launcher creates and uses the repository-local `.venv-demo`
environment. It does not use `PYTHONPATH`, an old F-drive copy, or a globally
installed `rupa-privacy` package.

Open `http://localhost:8501` if the browser does not open automatically.

## Demonstration scope

The updated **08 Research** page runs the optional two-view method on the loaded
synthetic/confirmed-public inputs. Select task-directed or uniform total-view
allocation and click **Run two-view research**. The numerical budget is split
equally between rows and totals; category epsilon is unchanged. Results and
downloads appear on that page, not in the reference workflow's Analysis page.
The research package has its own explicit allowlist and run manifest. Production
and private calibration/release inputs are rejected. Accurate totals do not imply
preserved variance or individual records. The original pages 01--07 remain the
reference workflow and do not silently switch algorithms.

- Use **Load official synthetic example** for the maintained synthetic walkthrough.
- Use **Load water-treatment example** for the independent semi-synthetic domain.
- Use **Load hazardous-waste synthetic example** for an illustrative
  enterprise-year schema with 18 protected fields and explicitly excluded
  identifier/contact metadata. It does not contain information-centre records.
- Uploaded data stays on this computer. The Demo does not infer public bounds
  or public category domains from uploaded release records.
- The Run page accepts reproducibility mode only. Confidential production
  releases remain restricted to the ledger-controlled CLI workflow.
- Final public artifacts are written under `demo/runs/<run_id>/`.
- Result pages read only manifest-authorized public artifacts. Source release
  records are hidden by default and internal audit directories are never
  included in GUI downloads.

This is research software and a local tutorial interface. It is not a
production GUI, a regulatory-compliance product, or a guarantee of exact
physical consistency.

## Research result presentation

Analysis > Constraint Residuals includes the actual ordered NRMS measurements
from the verified public run: DP perturbation, full projection, interpolation,
and final clipping. Download residual plot data produces aggregate CSV values
with the same run ID, not row-level intermediates. Missing values are not zeros.

Risk charts show calibration association; utility weights are allocation
priorities, not observed release accuracy. These single-run figures cannot prove
privacy, universal budget optimality or multi-seed performance superiority.

The distributed official inputs are under `examples/official`, so the extracted
source distribution can load the same example without a historical directory.
See `docs/reviewer_walkthrough.md` for installation and three-domain CLI checks.

## Hazardous-waste business requirements (no observations)

Overview > 查看危废字段需求 opens Data > 危废业务需求（无实际数据）.
The source workbook supplies 31 named fields in four business groups, not an
observational dataset. The read-only catalog is bundled in
`demo/assets/hazardous_waste_requirements.json`; it does not require access to
the author's desktop or an Excel installation. No workbook-format examples
are treated as observations or as complete public category domains.

The page provides a filterable field dictionary, proposed English column
names, mechanism/encoding guidance, source interfaces and preparation checklist.
Both CSV downloads are requirements documents, not release data or runnable
configurations. Opening or downloading them never changes the loaded inputs,
validation status, privacy budgets or run outputs. No interface connector,
free-text mechanism, trajectory support or new physical constraint is added.

The existing hazardous-waste synthetic example remains a separate illustration,
not evidence of performance on these requested business fields. Existing EXE/ZIP
deliveries do not update themselves; the resource declarations in `RUPA.spec`
apply when a new Windows build is explicitly requested.
