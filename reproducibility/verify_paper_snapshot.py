"""Check source and installed-core identity against the paper snapshot."""
import hashlib
import json
from pathlib import Path

import rupa_privacy


def release_hashes(manifest):
    expected = dict(manifest["core_sha256"])
    overrides = manifest.get("release_metadata", {}).get("overrides", {})
    if not set(overrides).issubset({"src/rupa_privacy/version.py"}):
        raise ValueError("Only version.py may differ as declared release metadata")
    expected.update(overrides)
    return expected


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "reproducibility/expected/paper_core_sha256.json").read_text(encoding="utf-8"))
    paper = manifest["core_sha256"]
    expected = release_hashes(manifest)
    installed_root = Path(rupa_privacy.__file__).resolve().parent
    source = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((root / "src/rupa_privacy").rglob("*.py"))}
    installed = {"src/rupa_privacy/" + p.relative_to(installed_root).as_posix():
                 hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(installed_root.rglob("*.py"))}
    scientific = {key for key in paper if key != "src/rupa_privacy/version.py"}
    scientific_match = all(source.get(key) == installed.get(key) == paper[key] for key in scientific)
    result = {"core_files": len(expected), "source_matches_paper": source == paper,
              "installed_core_matches_paper": installed == paper,
              "source_matches_declared_release": source == expected,
              "installed_core_matches_declared_release": installed == expected,
              "non_version_core_files": len(scientific),
              "scientific_files_match_paper": scientific_match,
              "declared_metadata_only_difference": manifest.get("release_metadata", {}),
              "note": "Byte identity is provenance, not a privacy or security proof."}
    print(json.dumps(result, indent=2))
    return 0 if source == installed == expected and scientific_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
