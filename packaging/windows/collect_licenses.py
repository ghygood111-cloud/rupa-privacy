"""Collect installed component license texts without bundling the environment."""

import argparse
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    target = args.destination.resolve()
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name.lower() in {"rupa-privacy", "pytest", "atomicwrites", "iniconfig", "pluggy", "pefile", "pywin32-ctypes"}:
            continue
        copied = []
        for item in distribution.files or []:
            if item.name.lower().startswith(("license", "licence", "copying", "copyright", "notice")):
                source = Path(distribution.locate_file(item))
                if not source.is_file() or source.stat().st_size > 2_000_000:
                    continue
                folder = target / (name + "-" + distribution.version)
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / (str(len(copied) + 1) + "_" + source.name)
                shutil.copyfile(source, dest)
                copied.append(dest.relative_to(target).as_posix())
        records.append({"component": name, "version": distribution.version, "license_files": copied})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, target / "Python_LICENSE.txt")
    (target / "index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("Available component licenses collected: " + str(target))


if __name__ == "__main__":
    main()
