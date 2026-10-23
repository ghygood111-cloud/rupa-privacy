"""Reject unconditional overclaims in active RUPA publication surfaces."""

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PATHS = (
    ROOT / "README.md",
    ROOT / "pyproject.toml",
    ROOT / "src" / "rupa_privacy",
    ROOT / "examples",
    ROOT / "docs" / "softwarex_contribution_positioning.md",
    ROOT / "docs" / "software_scope_and_non_goals.md",
    ROOT / "docs" / "softwarex_statement_of_need.md",
    ROOT / "docs" / "softwarex_manuscript_outline.md",
    ROOT / "docs" / "third_party_reuse_protocol.md",
)
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml"}
PATTERNS = {
    "general platform claim": re.compile(
        r"\bgeneral[- ]purpose (?:differential privacy|DP) (?:platform|system|toolkit)\b",
        re.IGNORECASE,
    ),
    "deployment readiness claim": re.compile(r"\bproduction[- ]ready\b", re.IGNORECASE),
    "exact consistency claim": re.compile(
        r"\bphysically consistent (?:data|dataset|release|output)\b", re.IGNORECASE
    ),
    "optimal allocation claim": re.compile(
        r"\boptimal privacy (?:budget )?allocation\b", re.IGNORECASE
    ),
    "superiority claim": re.compile(
        r"\b(?:superior privacy protection|state[- ]of[- ]the[- ]art|outperforms existing DP tools)\b",
        re.IGNORECASE,
    ),
    "compliance claim": re.compile(
        r"\b(?:regulatory compliant|industrial deployment validated)\b",
        re.IGNORECASE,
    ),
}
NEGATION_MARKERS = (
    " not ",
    " no ",
    "does not",
    "do not",
    "cannot",
    "unsupported",
    "excluded",
    "without claiming",
)


def _files(path):
    if path.is_file():
        return [path]
    return [item for item in path.rglob("*") if item.suffix.lower() in TEXT_SUFFIXES]


def scan():
    findings = []
    for active_path in ACTIVE_PATHS:
        for path in _files(active_path):
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                normalized = " " + line.lower() + " "
                for label, pattern in PATTERNS.items():
                    if pattern.search(line) and not any(
                        marker in normalized for marker in NEGATION_MARKERS
                    ):
                        findings.append(
                            {
                                "file": str(path.relative_to(ROOT)),
                                "line": line_number,
                                "rule": label,
                                "text": line.strip(),
                            }
                        )
    return findings


def main():
    findings = scan()
    if findings:
        for item in findings:
            print(
                "{file}:{line}: {rule}: {text}".format(**item),
                file=sys.stderr,
            )
        return 1
    print("Unsupported-claim scan PASS: no unconditional prohibited claims found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
