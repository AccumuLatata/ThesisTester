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

On-grid minutes are aggregated with a vectorized ``groupby`` (QR E-9 /
QI-14-06) under the locked ``observed_aligned_15s_to_1m_v2`` policy. Sparse
and misaligned diagnostics keep the same coverage-table contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any

import numpy as np
import pandas as pd

from thesistester.config import REQUIRED_COLUMNS
from thesistester.data.loader import format_interval, source_duplicate_resolution_provenance

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
_ON_GRID_OFFSETS = (
    pd.Timedelta(0),
    pd.Timedelta(seconds=15),
    pd.Timedelta(seconds=30),
    pd.Timedelta(seconds=45),
)
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
    source_duplicate_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build JSON-safe ingestion provenance for a derivation result."""
    payload: dict[str, Any] = {
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
    if source_duplicate_audit:
        payload.update(source_duplicate_resolution_provenance(source_duplicate_audit))
    return payload


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
    on_grid = (timestamps - buckets).isin(_ON_GRID_OFFSETS)
    work = source_frame.assign(_bucket=buckets)
    bucket_n = work.groupby("_bucket", sort=True).size()
    bucket_n_on = on_grid.groupby(work["_bucket"], sort=True).sum()
    aligned = (bucket_n <= _EXPECTED_SUB_BARS) & (
        bucket_n_on.reindex(bucket_n.index).fillna(0) == bucket_n
    )
    dropped_index = bucket_n.index[~aligned]

    if not bool(aligned.any()):
        raise ValueError(
            "observed aligned derivation retained no parent bars; "
            f"dropped {int(len(dropped_index))} misaligned minute buckets"
        )

    aligned_rows = work.loc[work["_bucket"].map(aligned)]
    # Positional open/close (skipna=False) matches the locked iloc[0]/iloc[-1]
    # loop. Default GroupBy.first/last skip NaN and would emit the next finite
    # print if validation were ever reordered.
    grouped = aligned_rows.groupby("_bucket", sort=True)
    parent_agg = pd.DataFrame(
        {
            "open": grouped["open"].first(skipna=False),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(skipna=False),
            "volume": grouped["volume"].sum(skipna=False),
        }
    )
    for column in ("open", "high", "low", "close", "volume"):
        parent_agg[column] = parent_agg[column].astype("float64")
    _validate_aligned_source_ohlcv(aligned_rows)

    parent_data = parent_agg.reset_index().rename(columns={"_bucket": "timestamp"})
    parent_data = parent_data.loc[:, list(REQUIRED_COLUMNS)]
    parent_data["timestamp"] = _timestamps_matching_source_dtype(
        parent_data["timestamp"], source_frame["timestamp"].dtype
    )

    # Diagnostics stay on the sparse/misaligned buckets only (not the on-grid hot path).
    sparse_index = bucket_n.index[aligned & (bucket_n != _EXPECTED_SUB_BARS)]
    dropped_rows = [
        _coverage_bucket_row_from_work(work, bucket_ts, "timestamp_misalignment")
        for bucket_ts in dropped_index
    ]
    sparse_rows = [
        _coverage_bucket_row_from_work(work, bucket_ts, "incomplete_coverage")
        for bucket_ts in sparse_index
    ]
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
    """Floor to exchange-local minutes while preserving DST fold.

    Equivalent to ``Timestamp.replace(second=0, microsecond=0, nanosecond=0)``.
    Subtracting intra-minute offsets keeps the timezone fold (unlike ``floor("min")``).
    Stay in the source datetime unit: a nanosecond timedelta would promote
    pandas 3 ``datetime64[us, tz]`` buckets to ``ns`` and make parent identity
    depend on ``_timestamps_matching_source_dtype`` recovery.
    """
    intra = pd.to_timedelta(timestamps.dt.second, unit="s") + pd.to_timedelta(
        timestamps.dt.microsecond, unit="us"
    )
    nanoseconds = timestamps.dt.nanosecond
    if bool((nanoseconds != 0).any()):
        intra = intra + pd.to_timedelta(nanoseconds, unit="ns")
    return timestamps - intra


def _validate_aligned_source_ohlcv(aligned_rows: pd.DataFrame) -> None:
    """Vectorized OHLCV check; first failing bucket keeps the locked error text."""
    values = aligned_rows.loc[:, ("open", "high", "low", "close", "volume")]
    finite_ok = bool(values.notna().all().all()) and bool(
        np.isfinite(values.to_numpy(dtype="float64")).all()
    )
    volume_ok = bool((aligned_rows["volume"] >= 0).all())
    invalid_range = (aligned_rows["high"] < aligned_rows[["open", "close"]].max(axis=1)) | (
        aligned_rows["low"] > aligned_rows[["open", "close"]].min(axis=1)
    )
    invalid_range |= aligned_rows["high"] < aligned_rows["low"]
    if finite_ok and volume_ok and not bool(invalid_range.any()):
        return
    for bucket_ts, group in aligned_rows.groupby("_bucket", sort=True):
        _validate_group_ohlcv(group, pd.Timestamp(bucket_ts))
    raise ValueError(
        "source OHLC/volume failed vectorized validation without a per-minute match"
    )


def _coverage_bucket_row_from_work(
    work: pd.DataFrame,
    bucket_ts: pd.Timestamp,
    reason: str,
) -> dict[str, Any]:
    """Sparse/misaligned diagnostic row; timestamps stay in source order."""
    observed = list(work.loc[work["_bucket"] == bucket_ts, "timestamp"])
    return _coverage_bucket_row(
        timestamp=pd.Timestamp(bucket_ts),
        reason=reason,
        observed=observed,
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
