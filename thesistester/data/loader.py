"""CSV ingestion + validation for intraday OHLCV data."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import REQUIRED_COLUMNS


class DataValidationError(Exception):
    """Raised when input data cannot be parsed into the OHLCV contract."""


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation issue found in an OHLCV dataset."""

    code: str
    message: str
    count: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Structured output of data validation checks."""

    issues: list[ValidationIssue]
    inferred_interval: pd.Timedelta | None

    @property
    def is_clean(self) -> bool:
        return not self.issues

    def messages(self) -> list[str]:
        return [issue.message for issue in self.issues]


SUPPORTED_INTERVALS = ["1min", "5min", "15min", "30min", "1h", "4h", "1D"]


def infer_base_interval(timestamps: pd.Series) -> pd.Timedelta | None:
    """Infer the most common positive interval from a timestamp series."""
    if len(timestamps) < 2:
        return None

    ts = pd.Series(pd.to_datetime(timestamps, errors="coerce")).dropna().sort_values()
    if len(ts) < 2:
        return None

    diffs = ts.diff().dropna()
    diffs = diffs[diffs > pd.Timedelta(0)]
    if diffs.empty:
        return None

    counts = diffs.value_counts()
    return counts.sort_values(ascending=False).index[0]


def format_interval(interval: pd.Timedelta | None) -> str:
    """Format a timedelta into a compact bar string (e.g. 1min, 4h)."""
    if interval is None:
        return "unknown"

    total_seconds = int(interval.total_seconds())
    if total_seconds % 86400 == 0:
        days = total_seconds // 86400
        return f"{days}D"
    if total_seconds % 3600 == 0:
        hours = total_seconds // 3600
        return f"{hours}h"
    if total_seconds % 60 == 0:
        minutes = total_seconds // 60
        return f"{minutes}min"
    return str(interval)


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

    was_monotonic = df["timestamp"].is_monotonic_increasing
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(tz)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    out = df[REQUIRED_COLUMNS]
    out.attrs["was_monotonic_before_sort"] = was_monotonic
    return out


def validate_ohlcv(df: pd.DataFrame) -> ValidationReport:
    """Validate OHLCV data and return a structured report."""
    issues: list[ValidationIssue] = []

    dupes = int(df["timestamp"].duplicated().sum())
    if dupes:
        issues.append(
            ValidationIssue(
                code="duplicate_timestamps",
                message=f"{dupes} duplicate timestamps",
                count=dupes,
            )
        )

    if not bool(df.attrs.get("was_monotonic_before_sort", True)):
        issues.append(
            ValidationIssue(
                code="non_monotonic_before_sort",
                message="timestamps were not monotonic increasing before sorting",
            )
        )

    missing_ohlcv = int(df[["open", "high", "low", "close", "volume"]].isna().sum().sum())
    if missing_ohlcv:
        issues.append(
            ValidationIssue(
                code="missing_values",
                message=f"{missing_ohlcv} missing OHLCV values",
                count=missing_ohlcv,
            )
        )

    bad_hl = int((df["high"] < df["low"]).sum())
    if bad_hl:
        issues.append(
            ValidationIssue(
                code="high_below_low",
                message=f"{bad_hl} bars with high < low",
                count=bad_hl,
            )
        )

    oc_high = df[["open", "close"]].max(axis=1)
    oc_low = df[["open", "close"]].min(axis=1)
    bad_range = int(((df["high"] < oc_high) | (df["low"] > oc_low)).sum())
    if bad_range:
        issues.append(
            ValidationIssue(
                code="open_close_outside_range",
                message=f"{bad_range} bars where open/close fall outside high/low",
                count=bad_range,
            )
        )

    negative_volume = int((df["volume"] < 0).sum())
    if negative_volume:
        issues.append(
            ValidationIssue(
                code="negative_volume",
                message=f"{negative_volume} bars with negative volume",
                count=negative_volume,
            )
        )

    inferred_interval = infer_base_interval(df["timestamp"])
    if inferred_interval is not None:
        diffs = df["timestamp"].sort_values().diff().dropna()
        gap_threshold = inferred_interval * 3
        large_gaps = int((diffs > gap_threshold).sum())
        if large_gaps:
            issues.append(
                ValidationIssue(
                    code="significant_gaps",
                    message=(
                        f"{large_gaps} significant time gaps (> {format_interval(gap_threshold)}) "
                        f"from inferred interval {format_interval(inferred_interval)}"
                    ),
                    count=large_gaps,
                )
            )

    return ValidationReport(issues=issues, inferred_interval=inferred_interval)
