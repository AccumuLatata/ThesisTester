"""CSV ingestion + validation for intraday OHLCV data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import io
from typing import Literal

import pandas as pd

from ..config import REQUIRED_COLUMNS

# Flag gaps larger than 3x the inferred base interval as significant missing-bar regions.
GAP_THRESHOLD_MULTIPLIER = 3
DST_TRANSITION_CONTEXT_WINDOW = 3
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
DATABENTO_FIXED_POINT_SCALE = 1_000_000_000
DATABENTO_FIXED_POINT_THRESHOLD = 10_000_000
COLUMN_ALIASES = {
    "date time": "timestamp",
    "datetime": "timestamp",
    "time left": "timestamp",
    "volume(from bar)": "volume",
    "volume (from bar)": "volume",
}
FORMAT_PROFILES = (
    "canonical",
    "ninjatrader",
    "sierra_intraday",
    "quantower_history_exporter",
    "databento_trades",
    "tick_capture",
    "second_capture",
)
FormatProfile = Literal[
    "canonical",
    "ninjatrader",
    "sierra_intraday",
    "quantower_history_exporter",
    "databento_trades",
    "tick_capture",
    "second_capture",
]


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
    if total_seconds > 0:
        return f"{total_seconds}s"
    return str(interval)


def parse_interval(label: str | pd.Timedelta | None) -> pd.Timedelta | None:
    """Parse compact labels from :func:`format_interval` back to ``Timedelta``."""
    if label is None:
        return None
    if isinstance(label, pd.Timedelta):
        return label
    text = str(label).strip()
    if not text or text == "unknown":
        return None
    if text.endswith("min"):
        return pd.Timedelta(minutes=int(text[:-3]))
    if text.endswith("h"):
        return pd.Timedelta(hours=int(text[:-1]))
    if text.endswith("D"):
        return pd.Timedelta(days=int(text[:-1]))
    if text.endswith("s"):
        return pd.Timedelta(seconds=int(text[:-1]))
    raise ValueError(f"unrecognized interval label: {label!r}")


def _normalize_profile_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    columns = [normalize_column_name(column) for column in out.columns]
    out.columns = [COLUMN_ALIASES.get(column, column) for column in columns]
    return out


def _profile_timestamp(values: pd.Series, *, source_tz: str, target_tz: str) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if parsed.isna().any():
        raise DataValidationError("Unparseable values in profile timestamp column.")
    if parsed.dt.tz is None:
        try:
            parsed = parsed.dt.tz_localize(source_tz)
        except Exception as exc:
            text = str(exc).lower()
            class_name = exc.__class__.__name__.lower()
            if "nonexistent" in class_name or "nonexistent" in text:
                raise DataValidationError(
                    f"Nonexistent local timestamps detected for source timezone {source_tz}. "
                    "Review timestamps around spring-forward DST transition and retry."
                ) from exc
            if "ambiguous" in class_name or "ambiguous" in text:
                raise DataValidationError(
                    f"Ambiguous local timestamps detected for source timezone {source_tz}. "
                    "Review timestamps around fall-back DST transition and retry."
                ) from exc
            raise
    return parsed.dt.tz_convert(target_tz)


def _aggregate_capture_rows(rows: pd.DataFrame) -> pd.DataFrame:
    work = rows.sort_values("timestamp", kind="mergesort").copy()
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce")
    if work[["price", "volume"]].isna().any().any():
        raise DataValidationError("Capture rows must have numeric price and volume.")
    work["_bucket"] = work["timestamp"].dt.floor("1min")
    return (
        work.groupby("_bucket", sort=True)
        .agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
        .rename(columns={"_bucket": "timestamp"})
    )


def _read_explicit_profile(
    file,
    *,
    format_profile: FormatProfile,
    source_tz: str,
    target_tz: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a non-canonical vendor profile into canonical bars plus raw rows."""
    if format_profile == "ninjatrader":
        raw = pd.read_csv(file, sep=";", header=None)
        if raw.shape[1] == 6:
            raw.columns = ["timestamp", "open", "high", "low", "close", "volume"]
            raw["timestamp"] = _profile_timestamp(
                raw["timestamp"], source_tz=source_tz, target_tz=target_tz
            )
            return raw, raw.copy()
        if raw.shape[1] in {3, 5}:
            raw = raw.iloc[:, [0, 1, raw.shape[1] - 1]].copy()
            raw.columns = ["timestamp", "price", "volume"]
            raw["timestamp"] = _profile_timestamp(
                raw["timestamp"], source_tz=source_tz, target_tz=target_tz
            )
            return _aggregate_capture_rows(raw), raw
        raise DataValidationError(
            "NinjaTrader profile expects 6 bar fields or 3/5 capture fields separated by ';'."
        )

    if format_profile == "quantower_history_exporter":
        raw = _normalize_profile_columns(pd.read_csv(file, sep=";"))
        raw = raw.dropna(axis=1, how="all")
        missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
        if missing:
            raise DataValidationError(
                "Quantower History Exporter profile is missing required columns: "
                f"{missing}. Detected columns after normalization: {list(raw.columns)}"
            )
        raw["timestamp"] = _profile_timestamp(
            raw["timestamp"], source_tz=source_tz, target_tz=target_tz
        )
        return raw, raw.copy()

    raw = _normalize_profile_columns(pd.read_csv(file))
    if format_profile == "sierra_intraday":
        if "date" in raw.columns and "time" in raw.columns:
            raw["timestamp"] = (
                raw["date"].astype("string").str.strip()
                + " "
                + raw["time"].astype("string").str.strip()
            )
        if "last" in raw.columns and "close" not in raw.columns:
            raw["close"] = raw["last"]
        missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
        if missing:
            raise DataValidationError(
                f"Sierra Intraday profile is missing required columns: {missing}. "
                f"Detected columns after normalization: {list(raw.columns)}"
            )
        raw["timestamp"] = _profile_timestamp(
            raw["timestamp"], source_tz=source_tz, target_tz=target_tz
        )
        return raw, raw.copy()

    if format_profile == "databento_trades":
        if "action" in raw.columns:
            raw = raw[raw["action"].astype("string").str.upper().eq("T")].copy()
        if not {"ts_event", "price", "size"} <= set(raw.columns):
            raise DataValidationError(
                "Databento trades profile requires ts_event, price, and size columns."
            )
        raw["timestamp"] = pd.to_datetime(raw["ts_event"], unit="ns", utc=True, errors="coerce")
        if raw["timestamp"].isna().any():
            raise DataValidationError("Databento trades profile has unparseable ts_event values.")
        raw["timestamp"] = raw["timestamp"].dt.tz_convert(target_tz)
        # Keep all available price fields in decimal units for raw-sidecar provenance.
        for column in ("price", "bid_price", "ask_price"):
            if column in raw:
                values = pd.to_numeric(raw[column], errors="coerce")
                raw[column] = values.where(
                    values.abs() < DATABENTO_FIXED_POINT_THRESHOLD,
                    values / DATABENTO_FIXED_POINT_SCALE,
                )
        raw["volume"] = raw["size"]
        return _aggregate_capture_rows(raw), raw

    if format_profile in {"tick_capture", "second_capture"}:
        if not {"timestamp", "price", "volume"} <= set(raw.columns):
            raise DataValidationError(
                f"{format_profile} profile requires timestamp, price, and volume columns."
            )
        raw["timestamp"] = _profile_timestamp(
            raw["timestamp"], source_tz=source_tz, target_tz=target_tz
        )
        return _aggregate_capture_rows(raw), raw
    raise DataValidationError(f"Unsupported format profile: {format_profile!r}.")


def load_ohlcv(
    file,
    tz: str = "America/New_York",
    source_tz: str | None = None,
    target_tz: str | None = None,
    format_profile: FormatProfile = "canonical",
    return_raw: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """Load an OHLCV CSV into the canonical, tz-aware, sorted contract.

    `file` may be a path or a file-like object (e.g. Streamlit upload).
    Timezone-naive timestamps are localized to `source_tz` (or the canonical target);
    aware ones are converted using their embedded timezone.
    """
    target = target_tz or tz
    if format_profile not in FORMAT_PROFILES:
        raise DataValidationError(
            f"Unsupported format profile: {format_profile!r}. Choose one of {list(FORMAT_PROFILES)}."
        )
    source = source_tz or ("UTC" if format_profile == "ninjatrader" else target)
    if format_profile != "canonical":
        bars, raw = _read_explicit_profile(
            file,
            format_profile=format_profile,
            source_tz=source,
            target_tz=target,
        )
        canonical_input = bars[REQUIRED_COLUMNS].copy()
        # Explicit profiles already emit tz-aware timestamps. Normalize them to
        # one UTC representation before the canonical CSV re-entry so a dataset
        # crossing DST does not serialize mixed -04:00/-05:00 offsets.
        canonical_input["timestamp"] = pd.to_datetime(
            canonical_input["timestamp"], utc=True
        ).astype(str)
        canonical = load_ohlcv(
            io.StringIO(canonical_input.to_csv(index=False)),
            source_tz=target,
            target_tz=target,
        )
        canonical.attrs["format_profile"] = format_profile
        return (canonical, raw.reset_index(drop=True)) if return_raw else canonical

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
        r"^\d{1,2}\.\d{1,2}\.\d{2,4}\s\d{1,2}:\d{2}:\d{2}$", na=False
    )
    parsed_timestamps = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    if dot_date_mask.any():
        dot_date_values = df.loc[dot_date_mask, "timestamp"]
        parsed_timestamps.loc[dot_date_mask] = pd.to_datetime(
            dot_date_values,
            errors="coerce",
            dayfirst=True,
            format="mixed",
        )
    df["timestamp"] = parsed_timestamps
    if df["timestamp"].isna().any():
        raise DataValidationError("Unparseable values in 'timestamp' column.")

    was_monotonic = df["timestamp"].is_monotonic_increasing
    if df["timestamp"].dt.tz is None:
        try:
            df["timestamp"] = df["timestamp"].dt.tz_localize(source).dt.tz_convert(target)
        except Exception as exc:
            text = str(exc).lower()
            class_name = exc.__class__.__name__.lower()
            if "nonexistent" in class_name or "nonexistent" in text:
                raise DataValidationError(
                    f"Nonexistent local timestamps detected for source timezone {source}. "
                    "Review timestamps around spring-forward DST transition and retry."
                ) from exc
            if "ambiguous" in class_name or "ambiguous" in text:
                raise DataValidationError(
                    f"Ambiguous local timestamps detected for source timezone {source}. "
                    "Review timestamps around fall-back DST transition and retry."
                ) from exc
            raise
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(target)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    out = df[REQUIRED_COLUMNS]
    out.attrs["was_monotonic_before_sort"] = was_monotonic
    out.attrs["format_profile"] = "canonical"
    return (out, df.reset_index(drop=True)) if return_raw else out


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

        offset_change = (
            df["timestamp"]
            .map(lambda ts: ts.utcoffset().total_seconds() if pd.notna(ts) else None)
            .diff()
        )
        offset_change = offset_change.fillna(0)
        if (offset_change != 0).any():
            transition_idx = offset_change[offset_change != 0].index
            dst_gap_count = 0
            for idx in transition_idx:
                start = max(1, idx - DST_TRANSITION_CONTEXT_WINDOW)
                end = min(len(df) - 1, idx + DST_TRANSITION_CONTEXT_WINDOW)
                around = df["timestamp"].iloc[start : end + 1].diff().dropna()
                dst_gap_count += int((around > gap_threshold).sum())
            if dst_gap_count:
                issues.append(
                    ValidationIssue(
                        code="dst_transition_gaps",
                        message=(
                            f"{dst_gap_count} large gaps detected around DST transition boundaries "
                            f"(> {format_interval(gap_threshold)})."
                        ),
                        count=dst_gap_count,
                    )
                )

    return ValidationReport(issues=issues, inferred_interval=inferred_interval)


def duplicate_timestamp_report(df: pd.DataFrame) -> pd.DataFrame:
    """Return duplicate bars and classify duplicate groups as exact or conflicting."""
    columns = [
        "timestamp",
        "duplicate_group_size",
        "duplicate_row_number",
        "exact_duplicate_group",
        "ohlc_identical_group",
        "volume_conflict",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    duplicate_rows = df.loc[df["timestamp"].duplicated(keep=False)].copy()
    if duplicate_rows.empty:
        return pd.DataFrame(columns=columns)

    ohlcv = ["open", "high", "low", "close", "volume"]
    ohlc = ["open", "high", "low", "close"]
    duplicate_rows["duplicate_group_size"] = duplicate_rows.groupby("timestamp")[
        "timestamp"
    ].transform("size")
    duplicate_rows["duplicate_row_number"] = duplicate_rows.groupby("timestamp").cumcount() + 1
    exact_groups = duplicate_rows.groupby("timestamp")[ohlcv].apply(
        lambda group: group.drop_duplicates().shape[0] == 1
    )
    ohlc_identical_groups = duplicate_rows.groupby("timestamp")[ohlc].apply(
        lambda group: group.drop_duplicates().shape[0] == 1
    )
    duplicate_rows["exact_duplicate_group"] = duplicate_rows["timestamp"].map(exact_groups)
    duplicate_rows["ohlc_identical_group"] = duplicate_rows["timestamp"].map(ohlc_identical_groups)
    duplicate_rows["volume_conflict"] = (
        duplicate_rows["ohlc_identical_group"] & ~duplicate_rows["exact_duplicate_group"]
    )
    return (
        duplicate_rows[columns]
        .sort_values(["timestamp", "duplicate_row_number"], kind="mergesort")
        .reset_index(drop=True)
    )


def resolve_ohlc_identical_duplicates(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Resolve lower-only duplicate bars when every duplicate group shares OHLC."""
    report = duplicate_timestamp_report(df)
    if report.empty:
        return df.copy(), []
    if not bool(report["ohlc_identical_group"].all()):
        raise DataValidationError(
            "Cannot resolve duplicate timestamps with conflicting OHLC values."
        )

    duplicate_timestamps = set(report["timestamp"])
    retained_parts: list[pd.DataFrame] = [df.loc[~df["timestamp"].isin(duplicate_timestamps)]]
    audit: list[dict[str, object]] = []
    for timestamp, group in df.loc[df["timestamp"].isin(duplicate_timestamps)].groupby(
        "timestamp", sort=True
    ):
        selected = group.sort_values("volume", kind="mergesort").iloc[[0]]
        retained_parts.append(selected)
        audit.append(
            {
                "timestamp": str(timestamp),
                "policy": "ohlc_identical_keep_lowest_volume",
                "duplicate_group_size": int(len(group)),
                "retained_volume": float(selected["volume"].iloc[0]),
                "discarded_volumes": [
                    float(value) for value in group.drop(selected.index)["volume"].tolist()
                ],
            }
        )
    resolved = (
        pd.concat(retained_parts, ignore_index=True)
        .sort_values("timestamp", kind="mergesort")
        .reset_index(drop=True)
    )
    return resolved, audit


def primary_duplicate_volume_comparison(
    primary: pd.DataFrame,
    lower: pd.DataFrame,
) -> pd.DataFrame:
    """Compare duplicated primary volumes to complete lower-bar volume sums."""
    columns = [
        "timestamp",
        "primary_duplicate_group_size",
        "primary_candidate_volumes",
        "lower_aggregate_volume",
        "matching_primary_row_numbers",
        "comparison_status",
    ]
    primary_report = duplicate_timestamp_report(primary)
    if primary_report.empty:
        return pd.DataFrame(columns=columns)

    parent_interval = infer_base_interval(primary["timestamp"])
    lower_interval = infer_base_interval(lower["timestamp"])
    if parent_interval is None or lower_interval is None or lower_interval >= parent_interval:
        raise DataValidationError(
            "Primary/lower volume comparison requires a strictly finer inferred lower interval."
        )
    ratio = parent_interval / lower_interval
    expected_count = int(ratio)
    if ratio != expected_count:
        raise DataValidationError(
            "Primary/lower volume comparison requires an exact interval multiple."
        )

    lower_sorted = lower.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    lower_utc = pd.to_datetime(lower_sorted["timestamp"], utc=True)
    results: list[dict[str, object]] = []
    for timestamp, group in primary.loc[primary["timestamp"].duplicated(keep=False)].groupby(
        "timestamp", sort=True
    ):
        candidate_volumes = [float(value) for value in group["volume"].tolist()]
        row: dict[str, object] = {
            "timestamp": str(timestamp),
            "primary_duplicate_group_size": int(len(group)),
            "primary_candidate_volumes": ",".join(str(value) for value in candidate_volumes),
            "lower_aggregate_volume": None,
            "matching_primary_row_numbers": "",
            "comparison_status": "",
        }
        if group[["open", "high", "low", "close"]].drop_duplicates().shape[0] != 1:
            row["comparison_status"] = "primary_ohlc_conflict"
            results.append(row)
            continue

        start = pd.Timestamp(timestamp).tz_convert("UTC")
        end = start + parent_interval
        start_index = lower_utc.searchsorted(start, side="left")
        end_index = lower_utc.searchsorted(end, side="left")
        lower_group = lower_sorted.iloc[start_index:end_index]
        expected_timestamps = [start + offset * lower_interval for offset in range(expected_count)]
        if (
            len(lower_group) != expected_count
            or pd.to_datetime(lower_group["timestamp"], utc=True).tolist() != expected_timestamps
        ):
            row["comparison_status"] = "lower_group_unavailable"
            results.append(row)
            continue

        lower_volume = float(lower_group["volume"].sum(min_count=1))
        matching_rows = [
            index + 1
            for index, volume in enumerate(candidate_volumes)
            if abs(volume - lower_volume) <= max(1e-9, abs(lower_volume) * 1e-9)
        ]
        row["lower_aggregate_volume"] = lower_volume
        row["matching_primary_row_numbers"] = ",".join(str(index) for index in matching_rows)
        row["comparison_status"] = (
            "matched_one"
            if len(matching_rows) == 1
            else "matched_multiple"
            if len(matching_rows) > 1
            else "no_primary_volume_match"
        )
        results.append(row)
    return pd.DataFrame(results, columns=columns)
