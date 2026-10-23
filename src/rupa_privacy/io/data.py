"""Read supported tabular data formats without inferring private metadata."""

from pathlib import Path

import pandas as pd

from ..exceptions import DataValidationError


def load_table(path, sheet_name=0):
    """Load CSV, XLSX/XLS, or optionally Parquet into a DataFrame."""
    source = Path(path)
    if not source.is_file():
        raise DataValidationError("Input data file does not exist: " + str(source))
    suffix = source.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(source)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(source, sheet_name=sheet_name)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(source)
    except ImportError as exc:
        if suffix in {".parquet", ".pq"}:
            raise DataValidationError(
                "Parquet support requires an optional engine; install rupa-privacy[parquet]"
            ) from exc
        raise DataValidationError("A required spreadsheet reader is not installed") from exc
    except (OSError, ValueError) as exc:
        raise DataValidationError("Could not read input data file: " + str(source)) from exc
    raise DataValidationError(
        "Unsupported data format {0}; use CSV, XLSX, XLS, or Parquet".format(suffix or "<none>")
    )
