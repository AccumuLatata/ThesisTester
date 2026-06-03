"""CSV ingestion + validation for intraday OHLCV data."""
from __future__ import annotations

import pandas as pd

from ..config import REQUIRED_COLUMNS


class DataValidationError(Exception):
    """Raised when input data cannot be parsed into the OHLCV contract."""


def load_ohlcv(file, tz: str = "America/New_York") -> pd.DataFrame:
    """Load an OHLCV CSV into the canonical, tz-aware, sorted contract.

    `file` may be a path or a file-like object (e.g. Streamlit upload).
    Timezone-naive timestamps are localized to `tz`; aware ones are converted.
    """
    df = pd.read_csv(file)
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(f"Missing required columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].isna().any():
        raise DataValidationError("Unparseable values in 'timestamp' column.")

    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(tz)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df[REQUIRED_COLUMNS]


def validate_ohlcv(df: pd.DataFrame) -> list[str]:
    """Return a list of human-readable data-quality issues (empty == clean)."""
    issues: list[str] = []

    dupes = int(df["timestamp"].duplicated().sum())
    if dupes:
        issues.append(f"{dupes} duplicate timestamps")

    if not df["timestamp"].is_monotonic_increasing:
        issues.append("timestamps are not monotonic increasing")

    if df[["open", "high", "low", "close", "volume"]].isna().any().any():
        issues.append("NaN values present in OHLCV columns")

    bad_hl = int((df["high"] < df["low"]).sum())
    if bad_hl:
        issues.append(f"{bad_hl} bars with high < low")

    oc_high = df[["open", "close"]].max(axis=1)
    oc_low = df[["open", "close"]].min(axis=1)
    bad_range = int(((df["high"] < oc_high) | (df["low"] > oc_low)).sum())
    if bad_range:
        issues.append(f"{bad_range} bars where open/close fall outside high/low")

    if (df["volume"] < 0).any():
        issues.append("negative volume present")

    return issues
