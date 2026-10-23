"""Non-disclosing table profiles for data-import interfaces."""

from dataclasses import asdict, dataclass

import pandas as pd

from .data import load_table


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    inferred_kind: str
    missing_values: int
    unique_values: int


@dataclass
class TableProfile:
    file_name: str
    rows: int
    columns: int
    duplicate_rows: int
    column_profiles: list
    issues: list
    preview: list

    def to_dict(self):
        values = asdict(self)
        return values


def profile_table(path, include_preview=False, preview_rows=5):
    frame = load_table(path)
    columns = []
    issues = []
    for name in frame.columns:
        series = frame[name]
        if pd.api.types.is_numeric_dtype(series):
            kind = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(series):
            kind = "datetime"
        else:
            kind = "categorical/text"
        missing = int(series.isna().sum())
        if missing:
            issues.append("{0}: {1} missing values".format(name, missing))
        columns.append(
            ColumnProfile(
                name=str(name),
                dtype=str(series.dtype),
                inferred_kind=kind,
                missing_values=missing,
                unique_values=int(series.nunique(dropna=True)),
            )
        )
    duplicate_rows = int(frame.duplicated().sum())
    if duplicate_rows:
        issues.append("{0} duplicate rows".format(duplicate_rows))
    preview = (
        frame.head(min(max(int(preview_rows), 0), 10)).to_dict(orient="records")
        if include_preview
        else []
    )
    return TableProfile(
        file_name=__import__("pathlib").Path(path).name,
        rows=int(len(frame)),
        columns=int(len(frame.columns)),
        duplicate_rows=duplicate_rows,
        column_profiles=columns,
        issues=issues,
        preview=preview,
    )
