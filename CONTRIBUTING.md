# Contributing to RUPA

This is research software under BSD-3-Clause; see LICENSE. The owner approved
the initial public clean-source snapshot on 2026-10-23.
Do not submit confidential records, production ledgers, credentials or private
subject IDs. Dependency and public-data licenses remain separate.

Describe the affected supported workflow, expected behavior, minimal synthetic
reproduction and test evidence. Keep changes scoped; separate interface/docs from
changes to scientific definitions. Follow `docs/software_scope_and_non_goals.md`.

In the clean Python 3.9 reference environment:

```powershell
python -m pip install -r reproducibility/requirements-validation-py39.txt
python -m pip install -e ".[test,research]"
python -m pytest
python reproducibility/run_all.py
```

Install the optional demo extra separately for interface work. Preserve production
randomness, fixed-roster governance, cumulative budget exhaustion and the
public/internal boundary. Numeric changes require author review and regression
evidence; never update expected digests merely to make a failing test pass.

For UI changes, exercise both examples, validation, run, analysis and export. New
plots must identify run IDs, versions and evidence limits. A developer-run fixture
is not external reuse. No public support email has been supplied; follow
SECURITY.md and use sanitized synthetic errors only.
