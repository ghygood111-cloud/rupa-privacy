"""Distribution metadata checks; no scientific calculations are changed."""
from pathlib import Path

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
