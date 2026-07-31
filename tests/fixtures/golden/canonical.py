"""Cross-pandas canonicalization helpers for golden trade comparisons."""

from __future__ import annotations

import pandas as pd


def canonicalize_trades(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort trades and normalize datetimes to stable UTC microsecond strings."""
    out = frame.copy()
    sort_columns = [column for column in ("entry_bar_index", "signal_id") if column in out]
    if sort_columns:
        out = out.sort_values(sort_columns, kind="mergesort")
    out = out.reset_index(drop=True)
    for column in out.columns:
        if isinstance(out[column].dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_dtype(
            out[column].dtype
        ):
            timestamps = pd.to_datetime(out[column], errors="coerce", utc=True)
            out[column] = timestamps.map(
                lambda value: None if pd.isna(value) else value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            )
    return out


def dtype_family(series: pd.Series) -> str:
    """Map pandas-version-specific dtypes to a stable semantic family."""
    dtype = series.dtype
    if isinstance(dtype, pd.DatetimeTZDtype):
        return "datetime-with-tz"
    if pd.api.types.is_datetime64_dtype(dtype):
        return "datetime-naive"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_string_dtype(dtype) or dtype == object:
        non_null = series.dropna()
        if non_null.empty or non_null.map(lambda value: isinstance(value, str)).all():
            return "string"
    return "other"


def dtype_families(frame: pd.DataFrame) -> dict[str, str]:
    """Return stable dtype families keyed by column."""
    return {column: dtype_family(frame[column]) for column in frame.columns}
