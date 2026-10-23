"""Synthetic-only packaging diagnostics; never export row-level intermediates."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from demo_support import execute_demo, load_example, load_public_run
from resource_paths import resource_path, user_data_root


def frame_digest(frame, schema):
    """Match scripts/compare_legacy_package.py's eight-decimal table digest."""
    digest = hashlib.sha256()
    for name in schema.released_columns:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        if name in schema.numeric_columns:
            digest.update(np.round(frame[name].to_numpy(dtype=float), 8).astype("<f8").tobytes())
        else:
            digest.update(json.dumps(frame[name].astype(str).tolist(), ensure_ascii=True,
                                     separators=(",", ":")).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def run_check(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Packaging check output already exists")
    example = load_example("official")
    privacy = example["config"]["privacy"]
    if privacy["calibration_mode"] != "synthetic" or privacy["release_data_mode"] != "synthetic":
        raise ValueError("Packaging check accepts the bundled synthetic example only")
    run = execute_demo(example["config"], example["calibration"], example["release"],
                       output_root=user_data_root() / "runs")
    public = load_public_run(run.run_directory)
    result = run.result
    audit = {
        "risk": result.risk_result.single_scores,
        "joint_penalty": result.risk_result.joint_penalty,
        "utility": result.utility_result.utility_weights,
        "epsilon": result.allocation_result.epsilon,
        "noisy_release_digest": frame_digest(result.noisy_data, run.schema),
        "final_release_digest": frame_digest(result.release_data, run.schema),
        "input_sha256": {
            name: hashlib.sha256(resource_path("examples/official/" + name).read_bytes()).hexdigest()
            for name in ("calibration.csv", "release.csv", "config.yaml")
        },
        "versions": {name: importlib.metadata.version(name) for name in
                     ("rupa-privacy", "numpy", "pandas", "scipy", "scikit-learn", "streamlit", "matplotlib")},
        "run_id": run.run_id,
        "run_directory": str(run.run_directory),
        "inspection": public["inspection"],
        "raw_intermediates_exported": False,
    }
    # Exercise mpl-data, fonts and the bundled non-GUI backend, not a new UI plot.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(3, 2))
    axes.plot([0, 1], [0, 1])
    axes.set_title("RUPA packaging resource check")
    cache = user_data_root() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    figure.savefig(cache / "matplotlib_resource_check.png")
    plt.close(figure)
    audit["matplotlib_resource_check"] = "PASS"
    import pyarrow as pa
    probe = pa.table({"resource_check": [1, 2]})
    assert probe.num_rows == 2
    audit["pyarrow_resource_check"] = "PASS"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")
    print("Synthetic packaging check PASS: " + str(destination))
    return audit
