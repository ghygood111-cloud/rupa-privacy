"""Check source and installed-core identity against the paper snapshot."""
import hashlib
import json
from pathlib import Path

import rupa_privacy


def main():
    root = Path(__file__).resolve().parents[1]
    expected = json.loads((root / "reproducibility/expected/paper_core_sha256.json").read_text(encoding="utf-8"))["core_sha256"]
    installed_root = Path(rupa_privacy.__file__).resolve().parent
    source = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((root / "src/rupa_privacy").rglob("*.py"))}
    installed = {"src/rupa_privacy/" + p.relative_to(installed_root).as_posix():
                 hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(installed_root.rglob("*.py"))}
    result = {"core_files": len(expected), "source_matches_paper": source == expected,
              "installed_core_matches_paper": installed == expected,
              "note": "Byte identity is provenance, not a privacy or security proof."}
    print(json.dumps(result, indent=2))
    return 0 if source == installed == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
