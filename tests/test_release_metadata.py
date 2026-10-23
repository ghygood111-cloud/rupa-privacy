"""Distribution metadata checks; no scientific calculations are changed."""
from pathlib import Path
import json
import runpy

import pytest
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_distribution_declares_authorized_license_files():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["license"] == "BSD-3-Clause"
    assert metadata["project"]["authors"] == [{"name": "高涵"}]
    assert set(metadata["project"]["license-files"]) == {"LICENSE", "THIRD_PARTY_NOTICES.md"}
    for name in metadata["project"]["license-files"]:
        assert (ROOT / name).is_file()


def test_full_validation_dependencies_include_research_and_gui():
    requirements = (ROOT / "reproducibility/requirements-validation-py39.txt").read_text(encoding="utf-8")
    assert "diffprivlib==0.6.5" in requirements
    assert "streamlit==1.50.0" in requirements
    assert "matplotlib==3.9.4" in requirements
    assert "pytest-cov==4.1.0" in requirements


@pytest.mark.parametrize("filename", ["pipeline.py", "risk/nmi.py", "mechanisms/numerical.py"])
def test_paper_provenance_rejects_scientific_file_overrides(filename):
    verify = runpy.run_path(str(ROOT / "reproducibility/verify_paper_snapshot.py"))
    manifest = {"core_sha256": {}, "release_metadata": {"overrides": {"src/rupa_privacy/" + filename: "not-permitted"}}}
    with pytest.raises(ValueError, match="Only version.py"):
        verify["release_hashes"](manifest)


def test_release_version_matches_installed_package_and_citation():
    from rupa_privacy import __version__

    expected = json.loads((ROOT / "reproducibility/expected/release_metadata.json").read_text(encoding="utf-8"))
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert expected["version"] == citation["version"] == __version__
