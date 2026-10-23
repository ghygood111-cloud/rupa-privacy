# Onedir only. Set RUPA_BUILD_DEBUG=1 for the initial console build.
import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files, collect_delvewheel_libs_directory, collect_submodules, copy_metadata,
)

WINDOWS = Path(SPECPATH).resolve()
ROOT = WINDOWS.parents[1]
DEBUG = os.environ.get("RUPA_BUILD_DEBUG") == "1"
NAME = os.environ.get("RUPA_BUILD_NAME") or ("RUPA-debug" if DEBUG else "RUPA")

datas = collect_data_files("streamlit") + collect_data_files("matplotlib")
binaries = []
# PyArrow 21's Windows wheel has a vendored MSVC DLL in sibling pyarrow.libs.
datas, binaries = collect_delvewheel_libs_directory("pyarrow", datas=datas, binaries=binaries)
datas += copy_metadata("streamlit", recursive=True)
for distribution in ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "diffprivlib"):
    datas += copy_metadata(distribution)
# Keep package version metadata, but omit installation-machine direct_url.json.
for source, destination in copy_metadata("rupa-privacy"):
    for filename in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt"):
        item = Path(source) / filename
        if item.exists():
            datas.append((str(item), destination))
for name in ("app.py", "demo_support.py", "result_presentation.py", "resource_paths.py",
             "hazardous_waste_requirements.py", "research_support.py", "research_page.py"):
    datas.append((str(ROOT / "demo" / name), "demo"))
datas.append((str(ROOT / "demo/assets/hazardous_waste_requirements.json"), "demo/assets"))
for domain, config in (("official", "config.yaml"),
                       ("water_treatment", "config_reproducibility.yaml"),
                       ("hazardous_waste", "config_reproducibility.yaml")):
    for name in ("calibration.csv", "release.csv", config):
        datas.append((str(ROOT / "examples" / domain / name), "examples/" + domain))

hiddenimports = collect_submodules("rupa_privacy")
hiddenimports += collect_submodules("diffprivlib")
hiddenimports += collect_submodules("streamlit", filter=lambda name: ".testing" not in name)
hiddenimports += ["demo_support", "result_presentation", "resource_paths", "frozen_check",
                  "hazardous_waste_requirements", "research_support", "research_page",
                  "matplotlib.backends.backend_agg"]

a = Analysis(
    [str(WINDOWS / "rupa_launcher.py")],
    pathex=[str(ROOT / "demo"), str(WINDOWS)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    excludes=["tkinter", "PySide6", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=NAME,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=DEBUG, disable_windowed_traceback=True,
    version=str(WINDOWS / "version_info.txt"), icon="NONE",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
