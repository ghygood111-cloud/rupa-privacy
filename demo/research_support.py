"""Research-mode execution and narrowly allowlisted demonstration exports."""
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile

import pandas as pd

from rupa_privacy.io.run import create_run_id
from rupa_privacy.research import run_two_view_research, require_research_inputs
from demo_support import objects_from_config, validate_demo

PUBLIC_FILES = {"release_data.csv", "epsilon_allocation.csv", "diagnostics.json",
                "run_config.json", "metadata.json", "NOTICE.txt"}


def execute_research(config, calibration, release, output_root, strategy="hybrid_workload", progress=None):
    settings = objects_from_config(config)
    require_research_inputs(settings[1])
    validate_demo(config, calibration, release)
    start = time.perf_counter()
    result = run_two_view_research(calibration, release, settings, strategy=strategy, progress=progress)
    run_id = "research_" + create_run_id("reproducibility", settings[1].random_seed)
    folder = Path(output_root) / run_id
    folder.mkdir(parents=True, exist_ok=False)
    result["release_data"].to_csv(folder / "release_data.csv", index=False)
    result["allocation"].assign(run_id=run_id).to_csv(folder / "epsilon_allocation.csv", index=False)
    schema, privacy, _, _, adjacency, _ = settings
    metadata = {"run_id": run_id, "workflow": "two_view_research", "strategy": strategy,
        "mode": "reproducibility", "production_authorized": False, "rows": len(release),
        "columns": [adjacency.privacy_unit_id] + schema.released_columns,
        "excluded_target": schema.sensitive_target, "runtime_seconds": time.perf_counter() - start,
        "warning": "Research-only public/synthetic inputs. Not a production release or ledger authorization."}
    for name, value in (("diagnostics.json", {**result["diagnostics"], "allocation": result["allocation_diagnostics"]}),
                        ("run_config.json", {"schema": schema.to_dict(), "privacy": privacy.to_dict(), "strategy": strategy}),
                        ("metadata.json", metadata)):
        (folder / name).write_text(json.dumps({**value, "run_id": run_id}, indent=2, allow_nan=False), encoding="utf-8")
    (folder / "NOTICE.txt").write_text(
        "RUPA experimental two-view demonstration. Public/synthetic reproducibility only.\n"
        "Both views consume privacy budget. No confidential production authorization.\n"
        "Accurate totals do not imply original-row recovery or variance preservation.\n", encoding="utf-8")
    manifest = {"run_id": run_id, "workflow": "two_view_research", "artifacts": [
        {"name": name, "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()}
        for name in sorted(PUBLIC_FILES)]}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return load_research_run(folder)


def load_research_run(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["artifacts"]
    if len(entries) != len(PUBLIC_FILES) or {item["name"] for item in entries} != PUBLIC_FILES:
        raise ValueError("Unexpected research public artifact set")
    for item in entries:
        path = folder / item["name"]
        if path.is_symlink() or path.resolve().parent != folder or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Research artifact integrity check failed")
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((folder / "diagnostics.json").read_text(encoding="utf-8"))
    config = json.loads((folder / "run_config.json").read_text(encoding="utf-8"))
    data = pd.read_csv(folder / "release_data.csv")
    allocation = pd.read_csv(folder / "epsilon_allocation.csv")
    run_id = manifest["run_id"]
    if (any(item["run_id"] != run_id for item in (metadata, diagnostics, config))
            or set(allocation.run_id) != {run_id} or len(data) != metadata["rows"]
            or data.columns.tolist() != metadata["columns"] or metadata["excluded_target"] in data):
        raise ValueError("Research output identity or column check failed")
    return {"folder": folder, "run_id": run_id, "metadata": metadata,
            "diagnostics": diagnostics, "data": data, "allocation": allocation, "manifest": manifest}


def research_archive(folder):
    run = load_research_run(folder)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(PUBLIC_FILES | {"manifest.json"}):
            archive.write(run["folder"] / name, arcname=run["run_id"] + "/" + name)
    return buffer.getvalue()
