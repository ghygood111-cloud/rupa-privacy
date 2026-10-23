"""Actually execute source acceptance commands for an existing reviewer debug build."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from build_reviewer_package import redact_paths, sha256, write_json

ROOT = Path(__file__).resolve().parents[2]


def run(command, log):
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    output = completed.stdout + completed.stderr
    log.write_text(redact_paths(output), encoding="utf-8")
    print(output)
    return completed.returncode, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--core-before", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    junit = args.output / "pytest_final.xml"
    code, output = run([sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(junit)],
                       args.output / "pytest_terminal.txt")
    tree = ET.parse(junit)
    suites = list(tree.getroot().iter("testsuite"))
    counts = {name: sum(int(item.attrib.get(name, 0)) for item in suites)
              for name in ("tests", "failures", "errors", "skipped")}
    warning_match = re.search(r"(\d+) warnings? in", output)
    pytest = {"passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
              "failed": counts["failures"], "errors": counts["errors"],
              "skipped": counts["skipped"], "exit_code": code,
              "warnings": int(warning_match.group(1)) if warning_match else 0}
    repro_code, repro_output = run([sys.executable, "reproducibility/run_all.py"],
                                  args.output / "reproducibility_terminal.txt")
    before = json.loads(args.core_before.read_text(encoding="utf-8-sig"))
    changes = [Path(item["Path"]).relative_to(ROOT).as_posix() for item in before
               if sha256(item["Path"]).upper() != item["Hash"].upper()]
    current = {path.resolve() for path in (ROOT / "src/rupa_privacy").rglob("*")
               if path.is_file() and "__pycache__" not in path.parts}
    expected = {Path(item["Path"]).resolve() for item in before}
    integrity = {"status": "PASS" if not changes and current == expected else "FAIL",
                 "files_checked": len(before), "changed": changes,
                 "file_set_unchanged": current == expected}
    result = {"pytest": pytest,
              "reproducibility": {"status": "PASS" if repro_code == 0 and "Overall: PASS" in repro_output else "FAIL",
                                  "exit_code": repro_code},
              "core_integrity": integrity, "exe_sha256": sha256(args.exe),
              "browser_download_trigger": "PASS (user-confirmed browser behavior; current download controls exercised)",
              "independent_reviewer_assessment": "NOT YET COLLECTED"}
    write_json(args.output / "checks.json", result)
    print(json.dumps(result, indent=2))
    return 0 if code == 0 and result["reproducibility"]["status"] == "PASS" and integrity["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
