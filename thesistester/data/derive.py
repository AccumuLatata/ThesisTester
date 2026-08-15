"""Parent derivation from finer OHLCV source bars.

PR1 foundation for the 15-second-primary research contract, updated for
industry-standard Quantower/Rithmic History Exporter semantics: absent 15s
slots mean no prints (sparse/trade-only export), not corrupt data.

A one-minute parent is emitted for every exchange-local minute that contains
one or more on-grid 15-second opens (``:00``, ``:15``, ``:30``, ``:45``).
Minutes with off-grid timestamps are dropped with a diagnostic table.
Sparse (incomplete) minutes are retained in the canonical parent and reported
separately so R12 can use observed replay where complete and conservative
SL-first fallback where sparse.

This remains stricter than ``resample_ohlcv`` for misaligned timestamps, but
matches vendor aggregation for trade-only 15s exports.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

import pandas as pd

from thesistester.config import REQUIRED_COLUMNS
from thesistester.data.loader import format_interval, infer_base_interval

# Historical policy: required exactly four aligned sub-bars and dropped sparse
# minutes. Retained as a constant so old provenance/bindings remain readable.
DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1 = "complete_aligned_15s_to_1m_v1"
# Current policy: retain sparse on-grid minutes; drop only misaligned buckets.
DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2 = "observed_aligned_15s_to_1m_v2"
DERIVATION_POLICY_DEFAULT = DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2
INGESTION_MODE_15S_PRIMARY_DERIVE_1M = "15s_primary_derive_1m"
SUPPORTED_PARENT_INTERVAL = "1min"
_SOURCE_INTERVAL = pd.Timedelta(seconds=15)
_PARENT_INTERVAL = pd.Timedelta(minutes=1)
_EXPECTED_SUB_BARS = 4
_VALID_SECONDS = frozenset({0, 15, 30, 45})
_DROPPED_COLUMNS = (
    "timestamp",
    "reason",
    "expected_sub_bars",
    "observed_sub_bars",
    "observed_timestamps",
)
_SPARSE_COLUMNS = _DROPPED_COLUMNS


@dataclass(frozen=True)
class DerivedParentResult:
    """Typed result of observed-coverage parent derivation."""

    parent_data: pd.DataFrame
    source_data: pd.DataFrame
    source_interval: pd.Timedelta
    parent_interval: pd.Timedelta
    dropped_buckets: pd.DataFrame
    sparse_buckets: pd.DataFrame
    derivation_policy: str


def is_15s_history_exporter_source(timestamps: pd.Series) -> bool:
    """True when History Exporter Time-left stamps are a 15-second source.

    Native one-minute HE files open only on ``:00``. A 15-second export uses
    on-grid ``:00/:15/:30/:45`` opens (sparse trade-only files may omit slots).
    Any ``:15/:30/:45`` open, or a modal gap of exactly 15 seconds, selects the
    Data-page derive-1m path. All-``:00`` sparse 15s (one print per minute)
    is indistinguishable from vendor 1m and stays on the primary path; those
    parent bars already match observed-aligned derivation.
    """
    ts = pd.to_datetime(timestamps, errors="coerce").dropna()
    if ts.empty:
        return False
    seconds = ts.dt.second
    microseconds = ts.dt.microsecond
    nanoseconds = ts.dt.nanosecond if hasattr(ts.dt, "nanosecond") else 0
    fine_grid = seconds.isin({15, 30, 45}) & (microseconds == 0) & (nanoseconds == 0)
    if bool(fine_grid.any()):
        return True
    return infer_base_interval(ts) == _SOURCE_INTERVAL


def hash_source_frame(source: pd.DataFrame) -> str:
    """Return a stable SHA-256 for a normalized OHLCV source frame."""
    frame = _normalize_source_frame(source)
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64")
    hasher = hashlib.sha256()
    hasher.update(repr(list(frame.columns)).encode("utf-8"))
    dtype_repr = repr({column: str(dtype) for column, dtype in frame.dtypes.items()})
    hasher.update(dtype_repr.encode("utf-8"))
    hasher.update(row_hashes.tobytes())
    return hasher.hexdigest()


def build_derivation_provenance(
    result: DerivedParentResult,
    *,
    format_profile: str,
    source_content_hash: str | None = None,
) -> dict[str, Any]:
    """Build JSON-safe ingestion provenance for a derivation result."""
    return {
        "ingestion_mode": INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        "source_interval": format_interval(result.source_interval),
        "derived_parent_interval": format_interval(result.parent_interval),
        "derivation_policy": result.derivation_policy,
        "source_format_profile": str(format_profile),
        "source_content_hash": (
            source_content_hash
            if source_content_hash is not None
            else hash_source_frame(result.source_data)
        ),
        "dropped_parent_bucket_count": int(len(result.dropped_buckets)),
        "sparse_parent_bucket_count": int(len(result.sparse_buckets)),
    }


def derive_complete_parent_ohlcv(
    source: pd.DataFrame,
    *,
    parent_interval: str = SUPPORTED_PARENT_INTERVAL,
) -> DerivedParentResult:
    """Derive parent OHLCV bars from an aligned 15-second source frame.

    Only ``parent_interval="1min"`` is supported. The source cadence must be
    exactly 15 seconds. A parent minute is emitted when the source contains one
    or more on-grid opens among ``:00``, ``:15``, ``:30``, and ``:45``. Sparse
    minutes (fewer than four sub-bars) are retained; off-grid timestamps make
    the minute misaligned and dropped.
    """
    if parent_interval != SUPPORTED_PARENT_INTERVAL:
        raise ValueError(
            "observed aligned derivation currently supports only "
            f"parent_interval={SUPPORTED_PARENT_INTERVAL!r}, got {parent_interval!r}"
        )

    source_frame = _normalize_source_frame(source)
    _validate_source_frame(source_frame)
    _validate_15s_cadence(source_frame["timestamp"])

    timestamps = source_frame["timestamp"]
    # Preserve timezone fold so fall-back ambiguous minutes stay distinct.
    buckets = _floor_to_local_minute(timestamps)
    parent_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    sparse_rows: list[dict[str, Any]] = []

    for bucket_start, group in source_frame.groupby(buckets, sort=True):
        bucket_ts = pd.Timestamp(bucket_start)
        group = group.sort_values("timestamp").reset_index(drop=True)
        observed = list(group["timestamp"])
        if not _group_is_on_grid(observed, bucket_ts):
            dropped_rows.append(
                _coverage_bucket_row(
                    timestamp=bucket_ts,
                    reason="timestamp_misalignment",
                    observed=observed,
                )
            )
            continue
        _validate_group_ohlcv(group, bucket_ts)
        parent_rows.append(
            {
                "timestamp": bucket_ts,
                "open": float(group["open"].iloc[0]),
                "high": float(group["high"].max()),
                "low": float(group["low"].min()),
                "close": float(group["close"].iloc[-1]),
                "volume": float(group["volume"].sum()),
            }
        )
        if len(group) != _EXPECTED_SUB_BARS:
            sparse_rows.append(
                _coverage_bucket_row(
                    timestamp=bucket_ts,
                    reason="incomplete_coverage",
                    observed=observed,
                )
            )

    if not parent_rows:
        raise ValueError(
            "observed aligned derivation retained no parent bars; "
            f"dropped {len(dropped_rows)} misaligned minute buckets"
        )

    parent_data = pd.DataFrame(parent_rows, columns=list(REQUIRED_COLUMNS))
    parent_data["timestamp"] = _timestamps_matching_source_dtype(
        parent_data["timestamp"], source_frame["timestamp"].dtype
    )
    dropped_buckets = pd.DataFrame(dropped_rows, columns=list(_DROPPED_COLUMNS))
    sparse_buckets = pd.DataFrame(sparse_rows, columns=list(_SPARSE_COLUMNS))
    if not dropped_buckets.empty:
        dropped_buckets["timestamp"] = _timestamps_matching_source_dtype(
            dropped_buckets["timestamp"], source_frame["timestamp"].dtype
        )
    if not sparse_buckets.empty:
        sparse_buckets["timestamp"] = _timestamps_matching_source_dtype(
            sparse_buckets["timestamp"], source_frame["timestamp"].dtype
        )

    return DerivedParentResult(
        parent_data=parent_data.reset_index(drop=True),
        source_data=source_frame.reset_index(drop=True),
        source_interval=_SOURCE_INTERVAL,
        parent_interval=_PARENT_INTERVAL,
        dropped_buckets=dropped_buckets.reset_index(drop=True),
        sparse_buckets=sparse_buckets.reset_index(drop=True),
        derivation_policy=DERIVATION_POLICY_DEFAULT,
    )


def _timestamps_matching_source_dtype(values: pd.Series, source_dtype: Any) -> pd.Series:
    """Parse timestamps while preserving the source/loader datetime unit.

    ``pd.to_datetime`` on reconstructed Timestamp rows may default to a different
    resolution than the loader frame (pandas 2 ``ns`` vs pandas 3 ``us``). Derived
    parents must keep the source unit or CSV lineage round-trips diverge in
    ``DataIdentity.data_content_hash`` (dtype is part of the hash).
    """
    parsed = pd.to_datetime(values, errors="coerce")
    if getattr(source_dtype, "tz", None) is not None or str(source_dtype).startswith("datetime64"):
        try:
            return parsed.astype(source_dtype)
        except (TypeError, ValueError):
            pass
    unit = getattr(source_dtype, "unit", None)
    if unit is not None and hasattr(parsed.dt, "as_unit"):
        return parsed.dt.as_unit(unit)
    return parsed


def _normalize_source_frame(source: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(source, pd.DataFrame):
        raise TypeError("source must be a pandas DataFrame")
    missing = [column for column in REQUIRED_COLUMNS if column not in source.columns]
    if missing:
        raise ValueError(f"source data missing required columns: {missing}")
    frame = source.loc[:, list(REQUIRED_COLUMNS)].copy()
    source_dtype = frame["timestamp"].dtype
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    # Keep loader unit when present (datetime64[ns|us, tz] depending on pandas).
    if getattr(source_dtype, "tz", None) is not None or getattr(source_dtype, "unit", None):
        try:
            frame["timestamp"] = frame["timestamp"].astype(source_dtype)
        except (TypeError, ValueError):
            pass
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.reset_index(drop=True)


def _validate_source_frame(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise ValueError("source data is empty")
    if frame["timestamp"].isna().any():
        raise ValueError("source data contains invalid timestamps")
    if frame["timestamp"].dt.tz is None:
        raise ValueError("source timestamps must be timezone-aware")
    if frame["timestamp"].duplicated().any():
        raise ValueError("source data contains duplicate timestamps")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("source data timestamps must be sorted")


def _validate_15s_cadence(timestamps: pd.Series) -> None:
    """Require on-grid 15-second opens with gaps that are exact 15s multiples.

    Off-grid timestamps are not fatal here; they make their parent minute
    misaligned and are reported in ``dropped_buckets``. Sparse trade-only
    Quantower/Rithmic exports may omit empty slots, so consecutive on-grid
    gaps of 30s/45s/60s+ are valid — only non-multiples of 15s fail closed.
    """
    on_grid_mask = (
        (timestamps.dt.microsecond == 0)
        & (timestamps.dt.nanosecond == 0)
        & timestamps.dt.second.isin(_VALID_SECONDS)
    )
    on_grid = timestamps.loc[on_grid_mask]
    if len(on_grid) < 2:
        raise ValueError("observed aligned 15s→1m derivation requires on-grid 15-second timestamps")
    positive = on_grid.diff().dropna()
    positive = positive[positive > pd.Timedelta(0)]
    if positive.empty:
        raise ValueError("observed aligned 15s→1m derivation requires observable on-grid steps")
    remainder = positive.mod(_SOURCE_INTERVAL)
    if (remainder != pd.Timedelta(0)).any():
        raise ValueError("source cadence must be an exact multiple of 15 seconds")


def _floor_to_local_minute(timestamps: pd.Series) -> pd.Series:
    """Floor to exchange-local minutes while preserving DST fold."""
    return timestamps.map(
        lambda value: pd.Timestamp(value).replace(second=0, microsecond=0, nanosecond=0)
    )


def _add_source_offset(bucket_ts: pd.Timestamp, offset: int) -> pd.Timestamp:
    """Return an expected sub-bar open that preserves the parent minute fold."""
    return pd.Timestamp(bucket_ts) + (offset * _SOURCE_INTERVAL)


def _group_is_on_grid(observed: list[pd.Timestamp], bucket_ts: pd.Timestamp) -> bool:
    """True when every observed stamp is a unique expected 15s open for ``bucket_ts``."""
    if not observed:
        return False
    expected = {_add_source_offset(bucket_ts, offset) for offset in range(_EXPECTED_SUB_BARS)}
    if len(observed) > _EXPECTED_SUB_BARS:
        return False
    seen: set[pd.Timestamp] = set()
    for stamp in observed:
        ts = pd.Timestamp(stamp)
        if ts not in expected or ts in seen:
            return False
        if ts.microsecond != 0 or getattr(ts, "nanosecond", 0) != 0:
            return False
        seen.add(ts)
    return True


def _validate_group_ohlcv(group: pd.DataFrame, bucket_ts: pd.Timestamp) -> None:
    for column in ("open", "high", "low", "close", "volume"):
        values = group[column]
        if values.isna().any() or not values.map(lambda value: math.isfinite(float(value))).all():
            raise ValueError(
                f"source OHLC/volume contains non-finite values for parent minute {bucket_ts}"
            )
        if column == "volume" and (values < 0).any():
            raise ValueError(f"source volume is negative for parent minute {bucket_ts}")
    invalid_range = (group["high"] < group[["open", "close"]].max(axis=1)) | (
        group["low"] > group[["open", "close"]].min(axis=1)
    )
    invalid_range |= group["high"] < group["low"]
    if bool(invalid_range.any()):
        raise ValueError(f"source OHLC invariants are invalid for parent minute {bucket_ts}")


def _coverage_bucket_row(
    *,
    timestamp: pd.Timestamp,
    reason: str,
    observed: list[pd.Timestamp],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "reason": reason,
        "expected_sub_bars": _EXPECTED_SUB_BARS,
        "observed_sub_bars": len(observed),
        "observed_timestamps": ",".join(ts.isoformat() for ts in observed),
    }


# Backward-compatible private alias used by older tests/docs snippets.
_dropped_bucket_row = _coverage_bucket_row
