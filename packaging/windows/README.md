# RUPA Windows onedir distribution

This is a local reproducibility-only interface. The frozen executable embeds
Python, RUPA, pinned scientific dependencies, Streamlit static resources, Altair,
and Matplotlib's Agg backend/fonts. It is not a production release console.

## Build (developer only)

CPython 3.9.13 x64 on Windows is required for the locked reproduction contract.
Double-click `build_exe.bat` for the debug build, or run:

```powershell
packaging/windows/build_exe.bat -Mode Debug
packaging/windows/build_exe.bat -Mode Release
```

The release build requires recorded acceptance of the exact debug EXE under
`artifacts/windows_packaging_20261009/debug_gui_acceptance.json`. Do not mark it
PASS without actually using the debug GUI through validation, run, analysis and
export. `-SkipInstall` is for an already verified build environment only.

The builder clears only its own resolved `build/windows-debug`,
`build/windows-release`, `dist/RUPA-debug`, or `dist/RUPA` directory. Other builds,
wheel/source archives and repository content are preserved. PyInstaller is a
build dependency only. No onefile spec or build is provided.

Compiler `packaging==24.2` satisfies PyInstaller's >=22 requirement; the reference
test environment's packaging 21.3 remains unchanged. The scientific versions
remain NumPy 1.26.4, pandas 1.4.4, SciPy 1.13.1 and scikit-learn 1.6.1. Actual
resolved versions and build logs are saved separately.

## Runtime paths and behavior

`demo/resource_paths.py` is the sole frozen/source path adapter. Bundled files are
resolved inside `_internal`; generated data goes to `%LOCALAPPDATA%/RUPA/`:

- `runs/`: approved public run artifacts;
- `logs/startup.log`: technical startup errors and health checks;
- `logs/last_startup.json`: actual loopback URL and PID;
- `workspace/` and `cache/`: writable working/cache directories.

The launcher chooses 8501, then another available port; it binds 127.0.0.1 only.
Usage telemetry and file watchers are disabled. CORS/XSRF protections are not
disabled. An explicit health check precedes default-browser opening. Startup
failure shows a Windows message box with the log location. Browser closure does
not stop the server process; use Windows Task Manager to end RUPA when finished.

The existing GUI's hidden-input defaults, sensitive-target suppression,
production rejection, manifest-based reads and whitelist ZIP exporter remain
unchanged. The compiler bundles all three maintained GUI examples byte-for-byte.

## Developer verification

```powershell
dist/RUPA-debug/RUPA-debug.exe --packaging-self-test artifacts/windows_packaging_20261009/debug_check.json
dist/RUPA/RUPA.exe --packaging-self-test artifacts/windows_packaging_20261009/release_check.json
```

This path accepts only the bundled synthetic official case and writes aggregate
scores/digests plus an approved public run. It does not export noisy/raw rows.
Noisy-state digest is checked inside the frozen process, since the normal GUI
correctly does not export that state. The normal GUI release is compared separately.
The diagnostic also renders a tiny nonsensitive Matplotlib resource probe.

GUI acceptance may use a human browser check plus automated saved-file verification:

```powershell
python packaging/windows/verify_downloads.py --run PUBLIC_RUN_DIRECTORY --downloads DOWNLOAD_DIRECTORY --output DOWNLOAD_REPORT.json
```

This checks actual saved files only, including byte-identical released CSV, the
same run's four residual stages/violation rates, and ZIP membership/bytes against
the public manifest. It never creates files merely to count a download as passed.
A copied old fixed-seed CSV is not accepted as evidence of a new GUI download.
Missing downloads or absent human visual confirmation do not become PASS.

After final release GUI acceptance, `package_evaluation.ps1` creates only the
teacher directory and `RUPA_Windows_0.1.0_Evaluation.zip`. It refuses to bypass the
acceptance gate or silently overwrite an earlier evaluation archive.

A relocated folder with PATH/PYTHONPATH removed is a dependency-isolation check,
not proof of a Python-free Windows machine. Record clean-machine verification as
NOT YET PERFORMED unless Sandbox/VM/a separate clean computer was really tested.

The EXE is unsigned. Current source is BSD-3-Clause under owner authorization;
older EXE bundles have not been rebuilt or re-licensed by this source change. Do not infer
public-release authorization from the existence of a compiled local teaching
package. Streamlit bootstrap integration is tied to the pinned version 1.50.0.

References: [PyInstaller runtime paths](https://pyinstaller.org/en/stable/runtime-information.html),
[hook utilities](https://pyinstaller.org/en/stable/hooks.html),
[Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml).
