"""Read-only content verification of completed reviewer delivery archives."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_archive(zip_path, expected):
    with zipfile.ZipFile(zip_path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename.replace("\\", "/") for item in files]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("Archive file set differs from approved directory")
        for item, name in zip(files, names):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive member")
            if hashlib.sha256(archive.read(item)).hexdigest() != digest(expected[name]):
                raise ValueError("Archive content differs: " + name)
    return {"status": "PASS", "file_count": len(expected),
            "sha256": digest(zip_path), "bytes": zip_path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--test-zip", type=Path, required=True)
    parser.add_argument("--evidence-zip", type=Path, required=True)
    args = parser.parse_args()
    directory = args.package.resolve()
    full = {directory.name + "/" + path.relative_to(directory).as_posix(): path
            for path in directory.rglob("*") if path.is_file()}
    evidence = directory / "reviewer_evidence"
    public = {path.relative_to(directory).as_posix(): path
              for path in evidence.rglob("*") if path.is_file()}
    for name in ("START_HERE.html", "REVIEW_TASKS.md", "REVIEW_FEEDBACK.md",
                 "SCREEN_RECORDING_SCRIPT.md", "NOTICE.txt"):
        public[name] = directory / name
    for name in public:
        parts = PurePosixPath(name).parts
        if any(part in {"src", "tests", ".git", ".internal_audit", "manuscript"} for part in parts):
            raise ValueError("Forbidden evidence member")
        if any(part.startswith("original_clipped_internal") for part in parts):
            raise ValueError("Private original evidence member")
    result = {"test_archive": check_archive(args.test_zip, full),
              "evidence_archive": check_archive(args.evidence_zip, public),
              "binary_bundle": "Existing debug resources byte-identical; no formal release built",
              "evidence_source_or_private_directories": "ABSENT"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
