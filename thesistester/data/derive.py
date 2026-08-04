"""Complete-coverage parent derivation from finer OHLCV source bars.

PR1 foundation for the 15-second-primary research contract: emit a one-minute
parent only when exactly four exchange-local, timestamp-aligned 15-second bars
exist. Incomplete or misaligned minutes are dropped with a diagnostic table.
This is intentionally stricter than ``resample_ohlcv``, which retains partial
buckets for preview use.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

import pandas as pd

from thesistester.config import REQUIRED_COLUMNS
from thesistester.data.loader import format_interval

DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1 = "complete_aligned_15s_to_1m_v1"
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


@dataclass(frozen=True)
class DerivedParentResult:
    """Typed result of complete-coverage parent derivation."""

    parent_data: pd.DataFrame
    source_data: pd.DataFrame
    source_interval: pd.Timedelta
    parent_interval: pd.Timedelta
    dropped_buckets: pd.DataFrame
    derivation_policy: str


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
    }


def derive_complete_parent_ohlcv(
    source: pd.DataFrame,
    *,
    parent_interval: str = SUPPORTED_PARENT_INTERVAL,
) -> DerivedParentResult:
    """Derive complete parent OHLCV bars from a finer aligned source frame.

    Only ``parent_interval="1min"`` is supported in v1, and the source cadence
    must be exactly 15 seconds. A parent minute is emitted only when the source
    contains exactly the opens ``:00``, ``:15``, ``:30``, and ``:45``.
    """
    if parent_interval != SUPPORTED_PARENT_INTERVAL:
        raise ValueError(
            "complete aligned derivation currently supports only "
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

    for bucket_start, group in source_frame.groupby(buckets, sort=True):
        bucket_ts = pd.Timestamp(bucket_start)
        group = group.sort_values("timestamp").reset_index(drop=True)
        expected = [_add_source_offset(bucket_ts, offset) for offset in range(_EXPECTED_SUB_BARS)]
        observed = list(group["timestamp"])
        if len(group) != _EXPECTED_SUB_BARS:
            dropped_rows.append(
                _dropped_bucket_row(
                    timestamp=bucket_ts,
                    reason="incomplete_coverage",
                    observed=observed,
                )
            )
            continue
        if observed != expected:
            dropped_rows.append(
                _dropped_bucket_row(
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

    if not parent_rows:
        raise ValueError(
            "complete aligned derivation retained no parent bars; "
            f"dropped {len(dropped_rows)} incomplete or misaligned minute buckets"
        )

    parent_data = pd.DataFrame(parent_rows, columns=list(REQUIRED_COLUMNS))
    parent_data["timestamp"] = _timestamps_matching_source_dtype(
        parent_data["timestamp"], source_frame["timestamp"].dtype
    )
    dropped_buckets = pd.DataFrame(dropped_rows, columns=list(_DROPPED_COLUMNS))
    if not dropped_buckets.empty:
        dropped_buckets["timestamp"] = _timestamps_matching_source_dtype(
            dropped_buckets["timestamp"], source_frame["timestamp"].dtype
        )

    return DerivedParentResult(
        parent_data=parent_data.reset_index(drop=True),
        source_data=source_frame.reset_index(drop=True),
        source_interval=_SOURCE_INTERVAL,
        parent_interval=_PARENT_INTERVAL,
        dropped_buckets=dropped_buckets.reset_index(drop=True),
        derivation_policy=DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1,
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
    """Require observable 15-second cadence from on-grid adjacent pairs.

    Off-grid timestamps are not fatal here; they make their parent minute
    incomplete or misaligned and are reported in ``dropped_buckets``.
    """
    on_grid_mask = (
        (timestamps.dt.microsecond == 0)
        & (timestamps.dt.nanosecond == 0)
        & timestamps.dt.second.isin(_VALID_SECONDS)
    )
    on_grid = timestamps.loc[on_grid_mask]
    if len(on_grid) < 2:
        raise ValueError("complete aligned 15s→1m derivation requires on-grid 15-second timestamps")
    positive = on_grid.diff().dropna()
    positive = positive[positive > pd.Timedelta(0)]
    intra_minute = positive[positive < _PARENT_INTERVAL]
    if intra_minute.empty:
        raise ValueError("complete aligned 15s→1m derivation requires observable 15-second steps")
    remainder = intra_minute.mod(_SOURCE_INTERVAL)
    if (remainder != pd.Timedelta(0)).any():
        raise ValueError("source cadence must be an exact multiple of 15 seconds")
    if intra_minute.min() != _SOURCE_INTERVAL:
        raise ValueError(
            "complete aligned 15s→1m derivation requires a 15-second source interval, "
            f"got {format_interval(intra_minute.min())}"
        )


def _floor_to_local_minute(timestamps: pd.Series) -> pd.Series:
    """Floor to exchange-local minutes while preserving DST fold."""
    return timestamps.map(
        lambda value: pd.Timestamp(value).replace(second=0, microsecond=0, nanosecond=0)
    )


def _add_source_offset(bucket_ts: pd.Timestamp, offset: int) -> pd.Timestamp:
    """Return an expected sub-bar open that preserves the parent minute fold."""
    return pd.Timestamp(bucket_ts) + (offset * _SOURCE_INTERVAL)


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


def _dropped_bucket_row(
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
