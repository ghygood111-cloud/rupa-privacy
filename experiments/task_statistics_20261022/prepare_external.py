"""Prepare the attributed public UCI benchmark without selecting favourable rows."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request

import pandas as pd

HERE = Path(__file__).resolve().parent
MAPPING = {
    "Cement": ("cement_kg_m3", [0, 1000]),
    "Blast Furnace Slag": ("slag_kg_m3", [0, 1000]),
    "Fly Ash": ("fly_ash_kg_m3", [0, 1000]),
    "Water": ("water_kg_m3", [0, 500]),
    "Superplasticizer": ("superplasticizer_kg_m3", [0, 100]),
    "Coarse Aggregate": ("coarse_aggregate_kg_m3", [0, 2000]),
    "Fine Aggregate": ("fine_aggregate_kg_m3", [0, 2000]),
    "Age": ("age_days", [1, 365]),
}


def main():
    out = HERE / "external"
    out.mkdir(exist_ok=False)
    url = "https://archive.ics.uci.edu/static/public/165/data.csv"
    raw = urllib.request.urlopen(url, timeout=90).read()
    (out / "source.csv").write_bytes(raw)
    frame = pd.read_csv(io.BytesIO(raw))
    assert frame.shape == (1030, 9) and set(MAPPING).issubset(frame.columns)
    assert not frame.isna().any().any()
    protocol = json.loads((HERE / "protocol.json").read_text())
    salt = protocol["public_external_dataset"]["split_salt"]
    recipes = frame[list(MAPPING)].apply(lambda row: ",".join(format(x, ".17g") for x in row), axis=1)
    hashes = recipes.map(lambda value: int(hashlib.sha256((salt + value).encode()).hexdigest(), 16))
    blocks = hashes.map(lambda value: value % 5)
    calibration = hashes.map(lambda value: (value // 5) % 5 < 2)
    renamed = frame.rename(columns={name: values[0] for name, values in MAPPING.items()})
    renamed = renamed.rename(columns={"Concrete compressive strength": "compressive_strength_mpa"})
    renamed.insert(0, "specimen_id", ["UCI-{0:06d}".format(i) for i in range(len(frame))])
    sizes = []
    for block in range(5):
        cal_mask, rel_mask = (blocks == block) & calibration, (blocks == block) & ~calibration
        assert not set(recipes[cal_mask]).intersection(recipes[rel_mask])
        assert min(cal_mask.sum(), rel_mask.sum()) > 10
        folder = out / ("block_" + str(block))
        folder.mkdir()
        renamed.loc[cal_mask].to_csv(folder / "calibration.csv", index=False)
        renamed.loc[rel_mask].drop(columns=["compressive_strength_mpa"]).to_csv(folder / "release.csv", index=False)
        sizes.append({"block": block, "calibration": int(cal_mask.sum()), "release": int(rel_mask.sum())})
    schema = {"fields": [values[0] for values in MAPPING.values()],
              "public_bounds": {values[0]: values[1] for values in MAPPING.values()},
              "bounds_source": "Analyst-declared broad benchmark assumptions frozen before numeric evaluation; age interval also documented by UCI. Not regulatory limits or bounds inferred from private release data.",
              "units": "Ingredient kg per cubic metre, age days; protected task is mean recipe parameters, not total material tonnage or company records.",
              "constraints": [], "target": "compressive_strength_mpa"}
    (out / "schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    provenance = {"name": "Concrete Compressive Strength", "creator": "I-Cheng Yeh", "doi": "10.24432/C5PK67",
        "source_url": url, "repository_url": "https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength",
        "license": "CC BY 4.0", "source_sha256": hashlib.sha256(raw).hexdigest(), "rows": 1030,
        "blocks": sizes, "preparation": "No rows dropped. Recipe groups are disjoint across blocks and calibration/release. Published measurement row is the evaluation unit; not enterprise or recipe-level privacy.",
        "privacy_status": "Already public benchmark; not confidential industrial deployment"}
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
