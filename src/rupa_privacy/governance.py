"""Privacy-unit identity and release-version helpers."""

import hashlib
import json

import numpy as np
import pandas as pd


def canonical_unit_token(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        normalized = {"type": "bool", "value": value}
    elif isinstance(value, int):
        normalized = {"type": "integer", "value": value}
    elif isinstance(value, float):
        normalized = {"type": "float", "value": repr(value)}
    else:
        normalized = {"type": "string", "value": str(value)}
    return json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def privacy_unit_tokens(data, privacy_unit_id):
    return tuple(canonical_unit_token(value) for value in data[privacy_unit_id].tolist())


def dataframe_version_hash(data, columns):
    """Hash ordered values, dtypes, and columns without exporting record content."""
    frame = data.loc[:, list(columns)]
    digest = hashlib.sha256()
    descriptor = {
        "columns": list(frame.columns),
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "rows": int(len(frame)),
    }
    digest.update(json.dumps(descriptor, sort_keys=True).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes())
    return digest.hexdigest()


def release_schema_hash(schema, adjacency):
    payload = {
        "schema": schema.to_dict(),
        "adjacency": adjacency.to_dict(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
