"""Tests for complete-coverage 15s→1m parent derivation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from thesistester.data.derive import (
    DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1,
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    build_derivation_provenance,
    derive_complete_parent_ohlcv,
    hash_source_frame,
)
from thesistester.data.loader import load_ohlcv
from thesistester.data.resample import resample_ohlcv
from thesistester.engine.intrabar import prepare_subtimeframe_context

VENDOR_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vendor"


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
    assert result.derivation_policy == DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1
    assert result.source_interval == pd.Timedelta(seconds=15)
    assert result.parent_interval == pd.Timedelta(minutes=1)
    pd.testing.assert_frame_equal(result.source_data, source.reset_index(drop=True))


@pytest.mark.parametrize("drop_offset", [0, 15, 30, 45])
def test_missing_any_sub_bar_drops_parent_with_incomplete_coverage(drop_offset):
    source = _complete_minute("2026-06-02 09:30:00")
    source = source.loc[source["timestamp"].dt.second != drop_offset].reset_index(drop=True)

    with pytest.raises(ValueError, match="retained no parent bars"):
        derive_complete_parent_ohlcv(source)

    # Recover diagnostics by temporarily completing a second minute.
    complete = _complete_minute("2026-06-02 09:31:00", open_price=110.0)
    mixed = pd.concat([source, complete], ignore_index=True)
    result = derive_complete_parent_ohlcv(mixed)
    assert len(result.parent_data) == 1
    assert result.parent_data["timestamp"].iloc[0].isoformat() == "2026-06-02T09:31:00-04:00"
    assert list(result.dropped_buckets["reason"]) == ["incomplete_coverage"]
    assert int(result.dropped_buckets["observed_sub_bars"].iloc[0]) == 3


def test_offset_timestamps_are_misaligned_and_dropped():
    source = _complete_minute("2026-06-02 09:30:00")
    source.loc[3, "timestamp"] = source.loc[3, "timestamp"] + pd.Timedelta(seconds=5)
    complete = _complete_minute("2026-06-02 09:31:00", open_price=110.0)
    result = derive_complete_parent_ohlcv(pd.concat([source, complete], ignore_index=True))

    assert len(result.parent_data) == 1
    assert list(result.dropped_buckets["reason"]) == ["timestamp_misalignment"]
    assert int(result.dropped_buckets["observed_sub_bars"].iloc[0]) == 4


def test_duplicate_timestamps_fail_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    source.loc[1, "timestamp"] = source.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        derive_complete_parent_ohlcv(source)


def test_invalid_source_cadence_fail_closed():
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
    with pytest.raises(ValueError, match="15-second source interval"):
        derive_complete_parent_ohlcv(source)


def test_middle_gap_retains_only_complete_adjacent_minutes():
    first = _complete_minute("2026-06-02 09:30:00", open_price=100.0)
    gap_partial = _complete_minute("2026-06-02 09:31:00", open_price=110.0).iloc[:2]
    third = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    source = pd.concat([first, gap_partial, third], ignore_index=True)

    result = derive_complete_parent_ohlcv(source)

    assert [ts.isoformat() for ts in result.parent_data["timestamp"]] == [
        "2026-06-02T09:30:00-04:00",
        "2026-06-02T09:32:00-04:00",
    ]
    assert list(result.dropped_buckets["timestamp"].map(lambda ts: ts.isoformat())) == [
        "2026-06-02T09:31:00-04:00"
    ]
    assert list(result.dropped_buckets["reason"]) == ["incomplete_coverage"]


def test_naive_resample_keeps_partial_bucket_but_derive_drops_it():
    complete = _complete_minute("2026-06-02 09:30:00")
    partial = _complete_minute("2026-06-02 09:31:00").iloc[:2]
    source = pd.concat([complete, partial], ignore_index=True)

    resampled = resample_ohlcv(source, "1min")
    assert len(resampled) == 2

    result = derive_complete_parent_ohlcv(source)
    assert len(result.parent_data) == 1
    assert result.parent_data["timestamp"].iloc[0].isoformat() == "2026-06-02T09:30:00-04:00"


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
    # match DataIdentity hashes (dtype is part of the content hash).
    assert str(result.parent_data["timestamp"].dtype) == str(source["timestamp"].dtype)
    assert getattr(result.parent_data["timestamp"].dtype, "unit", None) == "us"


def test_future_shock_append_does_not_change_prior_parents_or_diagnostics():
    first = _complete_minute("2026-06-02 09:30:00", open_price=100.0)
    incomplete = _complete_minute("2026-06-02 09:31:00", open_price=110.0).iloc[:2]
    baseline_source = pd.concat([first, incomplete], ignore_index=True)
    baseline = derive_complete_parent_ohlcv(baseline_source)

    future = _complete_minute("2026-06-02 09:32:00", open_price=120.0)
    shocked = derive_complete_parent_ohlcv(pd.concat([baseline_source, future], ignore_index=True))

    pd.testing.assert_frame_equal(
        shocked.parent_data.iloc[[0]].reset_index(drop=True),
        baseline.parent_data.reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        shocked.dropped_buckets.reset_index(drop=True),
        baseline.dropped_buckets.reset_index(drop=True),
    )
    assert len(shocked.parent_data) == 2


def test_provenance_builder_is_deterministic():
    source = _complete_minute("2026-06-02 09:30:00")
    result = derive_complete_parent_ohlcv(source)
    first = build_derivation_provenance(result, format_profile="quantower_history_exporter")
    second = build_derivation_provenance(result, format_profile="quantower_history_exporter")

    assert first == second
    assert first["ingestion_mode"] == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert first["source_interval"] == "15s"
    assert first["derived_parent_interval"] == "1min"
    assert first["derivation_policy"] == DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1
    assert first["source_format_profile"] == "quantower_history_exporter"
    assert first["dropped_parent_bucket_count"] == 0
    assert first["source_content_hash"] == hash_source_frame(result.source_data)


def test_timezone_naive_source_fails_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    source["timestamp"] = source["timestamp"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        derive_complete_parent_ohlcv(source)


def test_unsupported_parent_interval_fails_closed():
    source = _complete_minute("2026-06-02 09:30:00")
    with pytest.raises(ValueError, match="parent_interval"):
        derive_complete_parent_ohlcv(source, parent_interval="5min")
