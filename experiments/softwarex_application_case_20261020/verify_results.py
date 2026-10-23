"""Check complete new evidence and distinguish reproducibility from adoption."""
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    first = json.loads((HERE / "results" / "manifest.json").read_text(encoding="utf-8"))
    final = json.loads((HERE / "results_final" / "manifest.json").read_text(encoding="utf-8"))
    assert final["successful_runs"] == 180 and not final["failures"]
    assert first["protocol_sha256"] == final["protocol_sha256"] == sha(HERE / "protocol.json")
    for relative, expected in final["source_scripts_sha256"].items():
        assert sha(ROOT / relative) == expected
    current = {p.relative_to(ROOT).as_posix(): sha(p)
               for p in (ROOT / "src" / "rupa_privacy").rglob("*.py")}
    assert current == final["core_before"] == final["core_after"] == first["core_before"]
    first_digests = {r["run_id"]: r["release_sha256"] for r in first["runs"]}
    for record in final["runs"]:
        run_id = record["run_id"]
        run = HERE / "results_final" / "runs" / run_id
        assert record["release_sha256"] == first_digests[run_id] == sha(run / "release_data.csv")
        assert record["manifest_sha256"] == sha(run / "manifest.json")
        assert record["inspection"]["release_rows"] == 92066
        assert record["inspection"]["run_id"] == run_id
    initial_metrics = pd.read_csv(HERE / "results" / "raw_run_metrics.csv")
    final_metrics = pd.read_csv(HERE / "results_final" / "raw_run_metrics.csv")
    columns = [c for c in final_metrics if not c.endswith("seconds")]
    pd.testing.assert_frame_equal(initial_metrics[columns], final_metrics[columns])
    assert len(final_metrics.groupby(["strategy", "epsilon"])) == 6
    assert final_metrics.groupby(["strategy", "epsilon"]).size().eq(30).all()
    clean = json.loads((HERE / "clean_room" / "verification.json").read_text(encoding="utf-8"))
    assert clean["status"] == "PASS" and clean["reference_release_digest_equal"]
    assert all(value == 0 for value in clean["differences"].values())
    assert "Overall: PASS" in (HERE / "reproducibility.txt").read_text(encoding="utf-8")
    suites = ET.parse(HERE / "pytest_final.xml")
    assert len(list(suites.iter("testcase"))) == 265
    assert not list(suites.iter("failure")) and not list(suites.iter("error"))
    sdist = HERE / "sdist" / "rupa_privacy-0.1.0.tar.gz"
    with tarfile.open(sdist) as archive:
        members = archive.getnames()
    assert not any("_source_cache" in name or name.endswith("registration_source.csv") for name in members)
    for file in ["calibration.csv", "release.csv", "config_reproducibility.yaml", "provenance.json", "analysis.py"]:
        assert any(name.endswith("examples/ontario_registration/" + file) for name in members)
    report = {
        "status": "PASS", "primary_matrix_runs": 180,
        "independent_execution_replay_runs": 180,
        "statistical_note": "The replay repeats the same 30 seeds, not 60 independent draws.",
        "all_180_release_digests_identical_on_replay": True,
        "all_scientific_aggregate_values_identical_on_replay": True,
        "core_python_files_unchanged": len(current), "pytest": "265 passed, 11 existing warnings",
        "legacy_reproducibility": "Overall PASS", "clean_installed_wheel_cli": "PASS",
        "clean_risk_joint_utility_epsilon_max_difference": 0.0,
        "sdist_sha256": sha(sdist), "source_cache_excluded_from_sdist": True,
        "attributed_derived_example_in_sdist": True,
        "primary_tolerance_pass": final["primary_acceptance_pass"],
        "secondary_tolerance_pass": final["secondary_acceptance_pass"],
        "independent_human_adoption": "NOT EVALUATED",
        "confidential_production_deployment": "NOT EVALUATED",
        "numerical_utility_and_physical_repair": "NOT EVALUATED BY THIS CATEGORICAL CASE",
    }
    (HERE / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
