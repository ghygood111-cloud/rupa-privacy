# RUPA SoftwareX reproduction

This directory defines the locked scientific reproduction layer for RUPA 0.1.0.
The reference environment is 64-bit CPython 3.9.13 on Windows with the exact
packages in `requirements-lock-py39.txt`. Normal users should install from
`pyproject.toml`; the lock file is only for reproducing the archived regression.

## Create the reference environment

From the repository or unpacked source distribution root:

```powershell
py -3.9 -m venv .venv-reproduction
.\.venv-reproduction\Scripts\python.exe -m pip install --upgrade pip
.\.venv-reproduction\Scripts\python.exe -m pip install -r reproducibility\requirements-validation-py39.txt
.\.venv-reproduction\Scripts\python.exe -m pip install .
```

Python itself is not installed by a pip requirements file. Confirm that the
interpreter reports Python 3.9 before running the locked comparison.

## Run all principal checks

```powershell
.\.venv-reproduction\Scripts\python.exe reproducibility\run_all.py
```

The command creates temporary run directories, then executes the official
synthetic example, the independent water-treatment example, the third-party
reuse fixture, manifest verification, and the fixed-seed legacy comparison. It
checks the risk, joint-penalty, utility, epsilon, noisy-table, and final-table
expectations in `expected/` and exits nonzero on any failure.

## Portable versus locked validation

The GitHub Actions configuration defines four OS/Python combinations for invariant and tolerance-based tests
on Ubuntu and Windows with Python 3.9 and 3.11. The exact arrays and SHA-256
digests are intentionally checked only in this locked Python 3.9 environment,
because different numerical-library/platform combinations can exhibit harmless
floating-point variation.

The current publication candidate has not yet been pushed, so no hosted CI pass
is asserted. Full GUI/research tests need the validation extras, not just the
earlier core-only lock. The release verification report records local results.

## NMI resource policy

RUPA uses `KBinsDiscretizer(..., subsample=None)` for NMI calibration. This
preserves deterministic behavior above 200,000 rows but uses all calibration
rows and therefore increases runtime and memory requirements. See
`docs/nmi_reproducibility.md` for the complete preprocessing contract.
