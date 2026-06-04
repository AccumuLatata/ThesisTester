"""CSV ingestion + validation for intraday OHLCV data."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from ..config import REQUIRED_COLUMNS
# Flag gaps larger than 3x the inferred base interval as significant missing-bar regions.
GAP_THRESHOLD_MULTIPLIER = 3
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
COLUMN_ALIASES = {
    "date time": "timestamp",
    "datetime": "timestamp",
    "volume(from bar)": "volume",
    "volume (from bar)": "volume",
}


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


def normalize_column_name(column: object) -> str:
    """Normalize a CSV header value before alias resolution."""
    name = str(column).replace("\ufeff", "").replace("\xa0", " ")
    name = " ".join(name.strip().lower().split())
    name = name.replace(" (", "(").replace("( ", "(").replace(" )", ")")
    return name


def infer_base_interval(timestamps: pd.Series) -> pd.Timedelta | None:
    """Infer the base bar interval as the most frequent positive timestamp gap.

    Irregular outlier gaps are ignored by taking the mode of positive diffs only.
    Returns None when fewer than two valid timestamps are available.
    """
    if len(timestamps) < 2:
        return None

    ts = pd.to_datetime(timestamps, errors="coerce").dropna().sort_values()
    if len(ts) < 2:
        return None

    diffs = ts.diff().dropna()
    diffs = diffs[diffs > pd.Timedelta(0)]
    if diffs.empty:
        return None

    counts = diffs.value_counts()
    return counts.idxmax()


def format_interval(interval: pd.Timedelta | None) -> str:
    """Format an interval into a compact bar label, or 'unknown' for None."""
    if interval is None:
        return "unknown"

    total_seconds = int(interval.total_seconds())
    if total_seconds % SECONDS_PER_DAY == 0:
        days = total_seconds // SECONDS_PER_DAY
        return f"{days}D"
    if total_seconds % SECONDS_PER_HOUR == 0:
        hours = total_seconds // SECONDS_PER_HOUR
        return f"{hours}h"
    if total_seconds % SECONDS_PER_MINUTE == 0:
        minutes = total_seconds // SECONDS_PER_MINUTE
        return f"{minutes}min"
    return str(interval)


def load_ohlcv(
    file,
    tz: str = "America/New_York",
    source_tz: str | None = None,
    target_tz: str | None = None,
) -> pd.DataFrame:
    """Load an OHLCV CSV into the canonical, tz-aware, sorted contract.

    `file` may be a path or a file-like object (e.g. Streamlit upload).
    Timezone-naive timestamps are localized to `source_tz` (or the canonical target);
    aware ones are converted using their embedded timezone.
    """
    target = target_tz or tz
    source = source_tz or target

    df = pd.read_csv(file)
    raw_columns = [normalize_column_name(c) for c in df.columns]
    normalized_columns = [COLUMN_ALIASES.get(col, col) for col in raw_columns]

    duplicate_columns = sorted(
        [col for col, count in Counter(normalized_columns).items() if count > 1]
    )
    if duplicate_columns:
        raise DataValidationError(
            f"Duplicate columns after alias normalization: {duplicate_columns}"
        )

    df.columns = normalized_columns

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(
            f"Missing required columns: {missing}. "
            f"Detected columns after normalization: {list(df.columns)}"
        )

    timestamp_strings = df["timestamp"].astype("string").str.strip()
    dot_date_mask = timestamp_strings.str.match(
        r"^\d{1,2}\.\d{1,2}\.\d{2}\s+\d{1,2}:\d{2}:\d{2}$", na=False
    )
    parsed_timestamps = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    if dot_date_mask.any():
        parsed_timestamps.loc[dot_date_mask] = pd.to_datetime(
            df.loc[dot_date_mask, "timestamp"],
            errors="coerce",
            dayfirst=True,
            format="%d.%m.%y %H:%M:%S",
        )
    df["timestamp"] = parsed_timestamps
    if df["timestamp"].isna().any():
        raise DataValidationError("Unparseable values in 'timestamp' column.")

    was_monotonic = df["timestamp"].is_monotonic_increasing
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(source).dt.tz_convert(target)
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(target)

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

    was_monotonic_before_sort = df.attrs.get("was_monotonic_before_sort")
    if was_monotonic_before_sort is None:
        was_monotonic_before_sort = df["timestamp"].is_monotonic_increasing
    if not bool(was_monotonic_before_sort):
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
        diffs = df["timestamp"].diff().dropna()
        gap_threshold = inferred_interval * GAP_THRESHOLD_MULTIPLIER
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
