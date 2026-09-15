"""Tests for observed-coverage 15s→1m parent derivation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from thesistester.config import REQUIRED_COLUMNS
from thesistester.data.derive import (
    DERIVATION_POLICY_DEFAULT,
    DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    DerivedParentResult,
    _EXPECTED_SUB_BARS,
    _PARENT_INTERVAL,
    _SOURCE_INTERVAL,
    _DROPPED_COLUMNS,
    _SPARSE_COLUMNS,
    _coverage_bucket_row,
    _floor_to_local_minute,
    _group_is_on_grid,
    _normalize_source_frame,
    _timestamps_matching_source_dtype,
    _validate_15s_cadence,
    _validate_group_ohlcv,
    _validate_source_frame,
    build_derivation_provenance,
    derive_complete_parent_ohlcv,
    hash_source_frame,
)
from thesistester.persistence.local_store import hash_dataframe
from thesistester.data.loader import load_ohlcv
from thesistester.data.resample import resample_ohlcv
from thesistester.engine.intrabar import (
    prepare_subtimeframe_conservative_context,
    prepare_subtimeframe_context,
)

VENDOR_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vendor"
# hash_dataframe includes timestamp unit (pandas 2 ns / pandas 3 us).
VENDOR_DERIVED_1M_PARENT_HASH_BY_UNIT = {
    "us": "2b6d2414b8cbd60e3de08892748bfdf2d82b738ad6c25e4bcc383d5b78f72033",
    "ns": "773d0fc033e678824933331b814e7a4ed19c17caf8f845af9ce22e6390ca159d",
}


def vendor_derived_1m_parent_hash_lock(frame: pd.DataFrame) -> str:
    """Return the locked vendor 15s→1m parent hash for this pandas datetime unit."""
    unit = getattr(frame["timestamp"].dtype, "unit", "ns")
    try:
        return VENDOR_DERIVED_1M_PARENT_HASH_BY_UNIT[unit]
    except KeyError as exc:
        raise AssertionError(
            f"unrecorded vendor parent hash for timestamp unit {unit!r}"
        ) from exc


def _complete_minute(
    minute: str,
    *,
    open_price: float = 100.0,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    start = pd.Timestamp(minute).tz_localize("America/New_York")
    stamps = [start + pd.Timedelta(seconds=offset) for offset in (0, 15, 30, 45)]
    opens = [open_price, open_price + 1, open_price + 2, open_price + 3]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": opens,
            "high": [value + 2 for value in opens],
            "low": [value - 1 for value in opens],
            "close": [value + 1 for value in opens],
            "volume": volumes if volumes is not None else [2.0, 3.0, 2.0, 3.0],
        }
    )


def test_four_aligned_15s_bars_produce_exact_one_minute_ohlcv():
    source = _complete_minute("2026-06-02 09:30:00", open_price=100.0)
    result = derive_complete_parent_ohlcv(source)

    assert len(result.parent_data) == 1
    parent = result.parent_data.iloc[0]
    assert parent["timestamp"].isoformat() == "2026-06-02T09:30:00-04:00"
    assert parent["open"] == 100.0
    assert parent["high"] == 105.0
    assert parent["low"] == 99.0
    assert parent["close"] == 104.0
    assert parent["volume"] == 10.0
    assert result.dropped_buckets.empty
    assert result.sparse_buckets.empty
    assert result.derivation_policy == DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2
    assert result.source_interval == pd.Timedelta(seconds=15)
    assert result.parent_interval == pd.Timedelta(minutes=1)
    pd.testing.assert_frame_equal(result.source_data, source.reset_index(drop=True))


@pytest.mark.parametrize("drop_offset", [0, 15, 30, 45])
def test_missing_any_sub_bar_retains_sparse_parent(drop_offset):
    source = _complete_minute("2026-06-02 09:30:00")
    source = source.loc[source["timestamp"].dt.second != drop_offset].reset_index(drop=True)

    result = derive_complete_parent_ohlcv(source)
    assert len(result.parent_data) == 1
    assert result.dropped_buckets.empty
    assert list(result.sparse_buckets["reason"]) == ["incomplete_coverage"]
    assert int(result.sparse_buckets["observed_sub_bars"].iloc[0]) == 3
    assert float(result.parent_data["volume"].iloc[0]) == float(source["volume"].sum())
    assert float(result.parent_data["open"].iloc[0]) == float(source["open"].iloc[0])
    assert float(result.parent_data["close"].iloc[0]) == float(source["close"].iloc[-1])


def test_offset_timestamps_are_misaligned_and_dropped():
    source = _complete_minute("2026-06-02 09:30:00")
    source.loc[3, "timestamp"] = source.loc[3, "timestamp"] + pd.Timedelta(seconds=5)
    complete = _complete_minute("2026-06-02 09:31:00", open_price=110.0)
    result = derive_complete_parent_ohlcv(pd.concat([source, complete], ignore_index=True))

    assert len(result.parent_data) == 1
    assert list(result.dropped_buckets["reason"]) == ["timestamp_misalignment"]
    assert int(result.dropped_buckets["observed_sub_bars"].iloc[0]) == 4
    assert result.sparse_buckets.empty


def test_duplicate_timestamps_fail_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    source.loc[1, "timestamp"] = source.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        derive_complete_parent_ohlcv(source)


def test_on_grid_30s_gaps_retain_sparse_parents():
    """Trade-only exports may only print :00/:30; that is valid sparse 15s grid."""
    timestamps = pd.date_range("2026-06-02 09:30:00", periods=4, freq="30s", tz="America/New_York")
    source = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1, 1, 1, 1],
        }
    )
    result = derive_complete_parent_ohlcv(source)
    assert len(result.parent_data) == 2
    assert result.dropped_buckets.empty
    assert list(result.sparse_buckets["observed_sub_bars"]) == [2, 2]
    ctx = prepare_subtimeframe_conservative_context(
        result.parent_data,
        result.source_data,
        tick_size=0.25,
        parent_interval=result.parent_interval,
        sub_interval=result.source_interval,
    )
    assert ctx.sub_interval == pd.Timedelta(seconds=15)
    assert ctx.groups == {}
    assert len(ctx.fallback_reasons) == 2


def test_invalid_source_cadence_fail_closed():
    """Off-grid-only stamps cannot establish a 15-second open grid."""
    timestamps = pd.date_range("2026-06-02 09:30:05", periods=4, freq="10s", tz="America/New_York")
    source = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1, 1, 1, 1],
        }
    )
    with pytest.raises(ValueError, match="on-grid 15-second timestamps"):
        derive_complete_parent_ohlcv(source)


def test_one_print_per_minute_passes_declared_interval_r12_postcondition():
    """Gap-mode inference sees 1min; declared 15s interval must still prepare R12."""
    stamps = [
        pd.Timestamp(f"2026-06-02 09:{minute}:00", tz="America/New_York")
        for minute in range(30, 40)
    ]
    source = pd.DataFrame(
        {
            "timestamp": stamps,
            "open": list(range(100, 110)),
            "high": list(range(101, 111)),
            "low": list(range(99, 109)),
            "close": [value + 0.5 for value in range(100, 110)],
            "volume": [1] * 10,
        }
    )
    result = derive_complete_parent_ohlcv(source)
    assert len(result.parent_data) == 10
    assert len(result.sparse_buckets) == 10
    with pytest.raises(ValueError, match="strictly finer"):
        prepare_subtimeframe_conservative_context(
            result.parent_data, result.source_data, tick_size=0.25
        )
    ctx = prepare_subtimeframe_conservative_context(
        result.parent_data,
        result.source_data,
        tick_size=0.25,
        parent_interval=result.parent_interval,
        sub_interval=result.source_interval,
    )
    assert ctx.sub_interval == pd.Timedelta(seconds=15)
    assert ctx.groups == {}
    assert len(ctx.fallback_reasons) == 10


def test_middle_gap_retains_sparse_and_complete_adjacent_minutes():
    first = _complete_minute("2026-06-02 09:30:00", open_price=100.0)
    gap_partial = _complete_minute("2026-06-02 09:31:00", open_price=110.0).iloc[:2]
    third = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    source = pd.concat([first, gap_partial, third], ignore_index=True)

    result = derive_complete_parent_ohlcv(source)

    assert [ts.isoformat() for ts in result.parent_data["timestamp"]] == [
        "2026-06-02T09:30:00-04:00",
        "2026-06-02T09:31:00-04:00",
        "2026-06-02T09:32:00-04:00",
    ]
    assert result.dropped_buckets.empty
    assert list(result.sparse_buckets["timestamp"].map(lambda ts: ts.isoformat())) == [
        "2026-06-02T09:31:00-04:00"
    ]
    assert list(result.sparse_buckets["reason"]) == ["incomplete_coverage"]


def test_naive_resample_and_derive_both_retain_partial_bucket():
    complete = _complete_minute("2026-06-02 09:30:00")
    partial = _complete_minute("2026-06-02 09:31:00").iloc[:2]
    source = pd.concat([complete, partial], ignore_index=True)

    resampled = resample_ohlcv(source, "1min")
    assert len(resampled) == 2

    result = derive_complete_parent_ohlcv(source)
    assert len(result.parent_data) == 2
    assert result.parent_data["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"
    assert result.parent_data["timestamp"].iloc[1].isoformat() == "2026-06-02T09:31:00-04:00"
    assert list(result.sparse_buckets["reason"]) == ["incomplete_coverage"]


def test_rithmic_trade_only_sparse_minutes_aggregate_like_vendor_ohlcv():
    """Quiet ETH minutes often have 1–2 prints; those must stay in canonical 1m."""
    start = pd.Timestamp("2026-06-02 02:15:00", tz="America/New_York")
    stamps = [
        start,  # :00 only in first minute
        start + pd.Timedelta(minutes=1, seconds=15),
        start + pd.Timedelta(minutes=1, seconds=45),
        start + pd.Timedelta(minutes=2),
        start + pd.Timedelta(minutes=2, seconds=15),
        start + pd.Timedelta(minutes=2, seconds=30),
        start + pd.Timedelta(minutes=2, seconds=45),
    ]
    source = pd.DataFrame(
        {
            "timestamp": stamps,
            "open": [100, 101, 102, 103, 104, 105, 106],
            "high": [101, 102, 103, 104, 105, 106, 107],
            "low": [99, 100, 101, 102, 103, 104, 105],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
            "volume": [1, 2, 3, 4, 5, 6, 7],
        }
    )
    result = derive_complete_parent_ohlcv(source)

    assert len(result.parent_data) == 3
    assert result.dropped_buckets.empty
    assert int(result.sparse_buckets["observed_sub_bars"].iloc[0]) == 1
    assert int(result.sparse_buckets["observed_sub_bars"].iloc[1]) == 2
    assert len(result.sparse_buckets) == 2
    first = result.parent_data.iloc[0]
    assert first["open"] == 100.0
    assert first["close"] == 100.5
    assert first["volume"] == 1.0
    second = result.parent_data.iloc[1]
    assert second["open"] == 101.0
    assert second["high"] == 103.0
    assert second["low"] == 100.0
    assert second["close"] == 102.5
    assert second["volume"] == 5.0

    ctx = prepare_subtimeframe_conservative_context(
        result.parent_data,
        result.source_data,
        tick_size=0.25,
        parent_interval=result.parent_interval,
        sub_interval=result.source_interval,
    )
    assert len(ctx.groups) == 1  # only the complete third minute
    assert len(ctx.fallback_reasons) == 2
    assert ctx.sub_interval == pd.Timedelta(seconds=15)


def test_exchange_local_bucketing_across_dst_spring_forward():
    pre = _complete_minute("2026-03-08 01:59:00", open_price=100.0)
    # 02:00-02:59 does not exist on spring-forward day in America/New_York.
    post = _complete_minute("2026-03-08 03:00:00", open_price=110.0)
    source = pd.concat([pre, post], ignore_index=True)

    result = derive_complete_parent_ohlcv(source)

    assert [ts.isoformat() for ts in result.parent_data["timestamp"]] == [
        "2026-03-08T01:59:00-05:00",
        "2026-03-08T03:00:00-04:00",
    ]
    assert result.dropped_buckets.empty
    assert result.sparse_buckets.empty


def test_exchange_local_bucketing_across_dst_fall_back():
    before = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-11-01 05:59:00+00:00",
                    "2026-11-01 05:59:15+00:00",
                    "2026-11-01 05:59:30+00:00",
                    "2026-11-01 05:59:45+00:00",
                ],
                utc=True,
            ).tz_convert("America/New_York"),
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1, 1, 1, 1],
        }
    )
    after = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-11-01 06:00:00+00:00",
                    "2026-11-01 06:00:15+00:00",
                    "2026-11-01 06:00:30+00:00",
                    "2026-11-01 06:00:45+00:00",
                ],
                utc=True,
            ).tz_convert("America/New_York"),
            "open": [110, 111, 112, 113],
            "high": [111, 112, 113, 114],
            "low": [109, 110, 111, 112],
            "close": [110.5, 111.5, 112.5, 113.5],
            "volume": [2, 2, 2, 2],
        }
    )
    result = derive_complete_parent_ohlcv(pd.concat([before, after], ignore_index=True))

    assert [ts.isoformat() for ts in result.parent_data["timestamp"]] == [
        "2026-11-01T01:59:00-04:00",
        "2026-11-01T01:00:00-05:00",
    ]


def test_quantower_vendor_15s_derives_and_reconciles_with_r12():
    source = load_ohlcv(
        VENDOR_FIXTURES / "quantower_history_exporter_15s.csv",
        format_profile="quantower_history_exporter",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    vendor_parent = load_ohlcv(
        VENDOR_FIXTURES / "quantower_history_exporter_1m.csv",
        format_profile="quantower_history_exporter",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    result = derive_complete_parent_ohlcv(source)

    pd.testing.assert_frame_equal(
        result.parent_data.reset_index(drop=True),
        vendor_parent.reset_index(drop=True),
        check_dtype=False,
    )
    prepare_subtimeframe_context(result.parent_data, result.source_data, tick_size=0.25)
    # Parent timestamps must keep the loader unit so CSV lineage round-trips
    # match DataIdentity hashes (dtype is part of the content hash). The unit
    # itself varies by pandas major (2.x → ns, 3.x → us).
    assert str(result.parent_data["timestamp"].dtype) == str(source["timestamp"].dtype)
    assert getattr(result.parent_data["timestamp"].dtype, "unit", None) == getattr(
        source["timestamp"].dtype, "unit", None
    )
    assert hash_dataframe(result.parent_data) == vendor_derived_1m_parent_hash_lock(
        result.parent_data
    )


def test_future_shock_append_does_not_change_prior_parents_or_diagnostics():
    first = _complete_minute("2026-06-02 09:30:00", open_price=100.0)
    incomplete = _complete_minute("2026-06-02 09:31:00", open_price=110.0).iloc[:2]
    baseline_source = pd.concat([first, incomplete], ignore_index=True)
    baseline = derive_complete_parent_ohlcv(baseline_source)

    future = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    shocked = derive_complete_parent_ohlcv(pd.concat([baseline_source, future], ignore_index=True))

    pd.testing.assert_frame_equal(
        shocked.parent_data.iloc[:2].reset_index(drop=True),
        baseline.parent_data.reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        shocked.sparse_buckets.reset_index(drop=True),
        baseline.sparse_buckets.reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        shocked.dropped_buckets.reset_index(drop=True),
        baseline.dropped_buckets.reset_index(drop=True),
    )
    assert len(shocked.parent_data) == 3


def test_provenance_builder_is_deterministic():
    source = _complete_minute("2026-06-02 09:30:00")
    result = derive_complete_parent_ohlcv(source)
    first = build_derivation_provenance(result, format_profile="quantower_history_exporter")
    second = build_derivation_provenance(result, format_profile="quantower_history_exporter")

    assert first == second
    assert first["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert first["source_interval"] == "15s"
    assert first["derived_parent_interval"] == "1min"
    assert first["derivation_policy"] == DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2
    assert first["source_format_profile"] == "quantower_history_exporter"
    assert first["dropped_parent_bucket_count"] == 0
    assert first["sparse_parent_bucket_count"] == 0
    assert first["source_content_hash"] == hash_source_frame(result.source_data)


def test_provenance_counts_sparse_and_dropped_separately():
    sparse = _complete_minute("2026-06-02 09:30:00").iloc[:2]
    misaligned = _complete_minute("2026-06-02 09:31:00")
    misaligned.loc[3, "timestamp"] = misaligned.loc[3, "timestamp"] + pd.Timedelta(seconds=5)
    complete = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    result = derive_complete_parent_ohlcv(
        pd.concat([sparse, misaligned, complete], ignore_index=True)
    )
    provenance = build_derivation_provenance(result, format_profile="quantower_history_exporter")

    assert provenance["sparse_parent_bucket_count"] == 1
    assert provenance["dropped_parent_bucket_count"] == 1
    assert "source_duplicate_resolution" not in provenance
    assert len(result.parent_data) == 2


def test_provenance_includes_source_duplicate_audit_when_provided():
    source = _complete_minute("2026-06-02 09:30:00")
    result = derive_complete_parent_ohlcv(source)
    audit = [
        {
            "timestamp": "2026-06-02 09:30:00-04:00",
            "policy": "ohlc_identical_keep_lowest_volume",
            "duplicate_group_size": 2,
            "retained_volume": 2.0,
            "discarded_volumes": [9.0],
        }
    ]
    provenance = build_derivation_provenance(
        result,
        format_profile="quantower_history_exporter",
        source_duplicate_audit=audit,
    )
    assert provenance["source_duplicate_resolution"] == "ohlc_identical_keep_lowest_volume"
    assert provenance["source_duplicate_groups_resolved"] == 1
    assert provenance["source_duplicate_rows_discarded"] == 1
    assert provenance["source_duplicate_audit"] == audit


def test_timezone_naive_source_fails_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    source["timestamp"] = source["timestamp"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        derive_complete_parent_ohlcv(source)


def test_unsupported_parent_interval_fails_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    with pytest.raises(ValueError, match="parent_interval"):
        derive_complete_parent_ohlcv(source, parent_interval="5min")


def _loop_reference_derive(source: pd.DataFrame) -> DerivedParentResult:
    """Pre-E-9 Python groupby (QI-14-06). Hash-locks the vectorized on-grid path."""
    source_frame = _normalize_source_frame(source)
    _validate_source_frame(source_frame)
    _validate_15s_cadence(source_frame["timestamp"])
    buckets = source_frame["timestamp"].map(
        lambda value: pd.Timestamp(value).replace(second=0, microsecond=0, nanosecond=0)
    )
    parent_rows = []
    dropped_rows = []
    sparse_rows = []
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


def test_floor_to_local_minute_matches_replace_across_dst_fall_back():
    timestamps = pd.to_datetime(
        [
            "2026-11-01 05:59:00+00:00",
            "2026-11-01 05:59:15+00:00",
            "2026-11-01 05:59:45+00:00",
            "2026-11-01 06:00:00+00:00",
            "2026-11-01 06:00:15+00:00",
        ],
        utc=True,
    ).tz_convert("America/New_York")
    expected = timestamps.map(
        lambda value: pd.Timestamp(value).replace(second=0, microsecond=0, nanosecond=0)
    )
    series = pd.Series(timestamps)
    floored = _floor_to_local_minute(series)
    assert [ts.isoformat() for ts in floored] == [ts.isoformat() for ts in expected]
    assert str(floored.dtype) == str(series.dtype)


def _dst_both_0130_hours() -> pd.DataFrame:
    """Both fall-back 01:30 hours (fold 0 EDT and fold 1 EST)."""
    first = pd.to_datetime(
        [
            "2026-11-01 05:30:00+00:00",
            "2026-11-01 05:30:15+00:00",
            "2026-11-01 05:30:30+00:00",
            "2026-11-01 05:30:45+00:00",
        ],
        utc=True,
    ).tz_convert("America/New_York")
    second = pd.to_datetime(
        [
            "2026-11-01 06:30:00+00:00",
            "2026-11-01 06:30:15+00:00",
            "2026-11-01 06:30:30+00:00",
            "2026-11-01 06:30:45+00:00",
        ],
        utc=True,
    ).tz_convert("America/New_York")
    stamps = list(first) + list(second)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "open": list(range(100, 108)),
            "high": list(range(101, 109)),
            "low": list(range(99, 107)),
            "close": [value + 0.5 for value in range(100, 108)],
            "volume": [1.0] * 8,
        }
    )


def _mixed_sparse_misaligned_complete() -> pd.DataFrame:
    sparse = _complete_minute("2026-06-02 09:30:00").iloc[:2]
    misaligned = _complete_minute("2026-06-02 09:31:00")
    misaligned.loc[3, "timestamp"] = misaligned.loc[3, "timestamp"] + pd.Timedelta(seconds=5)
    complete = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    return pd.concat([sparse, misaligned, complete], ignore_index=True)


def test_vectorized_derive_is_hash_identical_to_loop_reference():
    """QI-14-06 / QR E-9: on-grid vectorization must not change parent or diagnostics."""
    vendor = load_ohlcv(
        VENDOR_FIXTURES / "quantower_history_exporter_15s.csv",
        format_profile="quantower_history_exporter",
        source_tz="America/New_York",
        target_tz="America/New_York",
    )
    mixed = _mixed_sparse_misaligned_complete()
    dst_fold = _dst_both_0130_hours()

    for source in (vendor, mixed, dst_fold):
        result = derive_complete_parent_ohlcv(source)
        reference = _loop_reference_derive(source)
        assert hash_dataframe(result.parent_data) == hash_dataframe(reference.parent_data)
        assert hash_dataframe(result.dropped_buckets) == hash_dataframe(reference.dropped_buckets)
        assert hash_dataframe(result.sparse_buckets) == hash_dataframe(reference.sparse_buckets)
        assert hash_dataframe(result.source_data) == hash_dataframe(reference.source_data)
        assert build_derivation_provenance(
            result, format_profile="quantower_history_exporter"
        ) == build_derivation_provenance(reference, format_profile="quantower_history_exporter")
        assert result.derivation_policy == DERIVATION_POLICY_OBSERVED_ALIGNED_15S_TO_1M_V2

    assert hash_dataframe(derive_complete_parent_ohlcv(vendor).parent_data) == (
        vendor_derived_1m_parent_hash_lock(vendor)
    )
    mixed_result = derive_complete_parent_ohlcv(mixed)
    assert len(mixed_result.parent_data) == 2
    assert list(mixed_result.dropped_buckets["reason"]) == ["timestamp_misalignment"]
    assert list(mixed_result.sparse_buckets["reason"]) == ["incomplete_coverage"]
    dst_result = derive_complete_parent_ohlcv(dst_fold)
    assert [ts.isoformat() for ts in dst_result.parent_data["timestamp"]] == [
        "2026-11-01T01:30:00-04:00",
        "2026-11-01T01:30:00-05:00",
    ]


def test_invalid_ohlcv_names_first_failing_parent_minute():
    bad = _complete_minute("2026-06-02 09:30:00")
    bad.loc[0, "high"] = 50.0
    good = _complete_minute("2026-06-02 09:31:00", open_price=110.0)
    source = pd.concat([bad, good], ignore_index=True)
    with pytest.raises(ValueError, match="parent minute 2026-06-02 09:30:00-04:00"):
        derive_complete_parent_ohlcv(source)


def test_nan_first_open_fail_closed_does_not_skip_to_next_print():
    """GroupBy.first skipna=True would take 101; locked path must refuse the minute."""
    source = _complete_minute("2026-06-02 09:30:00")
    source.loc[0, "open"] = float("nan")
    source = pd.concat(
        [source, _complete_minute("2026-06-02 09:31:00", open_price=110.0)],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="non-finite values for parent minute 2026-06-02 09:30:00"):
        derive_complete_parent_ohlcv(source)
