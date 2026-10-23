import subprocess
import sys
from pathlib import Path


def test_active_publication_surfaces_contain_no_unconditional_overclaims():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "scan_unsupported_claims.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_authorized_source_license_and_citation_are_consistent():
    root = Path(__file__).resolve().parents[1]
    import yaml
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    assert "BSD 3-Clause License" in license_text
    assert "高涵" in license_text
    assert citation["license"] == "BSD-3-Clause"
    assert citation["authors"][0]["family-names"] == "高"
    assert citation["authors"][0]["given-names"] == "涵"
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "BSD-3-Clause" in readme
