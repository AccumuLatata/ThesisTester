"""SW1 tests: entry_window Focus helpers (no engine / no re-sim)."""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.entry_window import (
    FOCUS_EQUITY_CAVEAT,
    FOCUS_HONESTY_BANNER,
    entry_window_contains,
    entry_window_from_bucket,
    filter_trades_by_entry_window,
    normalize_entry_window,
    summarize_focused_trades,
)
from thesistester.analytics.time_analysis import (
    RTH_SEGMENT_LABELS,
    RTH_SEGMENTS,
    add_time_buckets,
    rth_segment_for_minute,
)


def _make_trades(timestamps_ny: list[str], r_multiples: list[float]) -> pd.DataFrame:
    ts = pd.to_datetime(timestamps_ny).tz_localize("America/New_York")
    return pd.DataFrame(
        {
            "trade_id": list(range(len(r_multiples))),
            "signal_id": list(range(100, 100 + len(r_multiples))),
            "entry_timestamp": ts,
            "exit_timestamp": ts + pd.Timedelta(minutes=5),
            "r_multiple": r_multiples,
            "direction": ["long" if r >= 0 else "short" for r in r_multiples],
        }
    )


def test_public_rth_vocabulary_matches_private_bounds():
    assert RTH_SEGMENT_LABELS == tuple(label for _, _, label in RTH_SEGMENTS)
    assert "rth_open_30m" in RTH_SEGMENT_LABELS
    assert rth_segment_for_minute(570) == "rth_open_30m"
    assert rth_segment_for_minute(599) == "rth_open_30m"
    assert rth_segment_for_minute(600) == "rth_morning"


def test_normalize_disabled_is_legacy():
    assert normalize_entry_window(None)["enabled"] is False
    assert normalize_entry_window({"enabled": False})["enabled"] is False


def test_normalize_rth_segments_or_and_rejects_empty():
    window = normalize_entry_window(
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m", "rth_power_hour", "rth_open_30m"],
        }
    )
    assert window["rth_segments"] == ["rth_open_30m", "rth_power_hour"]
    with pytest.raises(ValueError, match="non-empty"):
        normalize_entry_window({"enabled": True, "mode": "rth_segments", "rth_segments": []})


def test_normalize_clock_range_no_wrap():
    with pytest.raises(ValueError, match="no overnight wrap"):
        normalize_entry_window(
            {
                "enabled": True,
                "mode": "clock_range",
                "start_time": "15:00",
                "end_time": "10:00",
            }
        )


def test_normalize_rejects_invalid_timezone():
    with pytest.raises(ValueError, match="Invalid entry_window.timezone"):
        normalize_entry_window(
            {
                "enabled": True,
                "mode": "clock_range",
                "start_time": "09:00",
                "end_time": "10:00",
                "timezone": "Not/AZone",
            }
        )


def test_entry_window_from_bucket_mappings():
    seg = entry_window_from_bucket("entry_rth_segment", "rth_open_30m")
    assert seg["mode"] == "rth_segments"
    assert seg["timezone"] == "America/New_York"

    hour = entry_window_from_bucket("entry_hour_bucket", "09:00", bucket_tz="America/Chicago")
    assert hour["mode"] == "clock_range"
    assert hour["start_time"] == "09:00"
    assert hour["end_time"] == "10:00"
    assert hour["timezone"] == "America/Chicago"

    half = entry_window_from_bucket("entry_30min_bucket", "09:30")
    assert half["start_time"] == "09:30"
    assert half["end_time"] == "10:00"


def test_clock_range_naive_timestamp_localizes_as_exchange_tz():
    """C5: naive 09:45 is NY wall clock, not Chicago, when bucket TZ differs."""
    window = entry_window_from_bucket(
        "entry_hour_bucket",
        "09:00",
        exchange_tz="America/New_York",
        bucket_tz="America/Chicago",
    )
    naive = pd.Timestamp("2026-06-02 09:45:00")
    aware_ny = pd.Timestamp("2026-06-02 09:45:00", tz="America/New_York")
    # 09:45 NY == 08:45 Chicago → outside [09:00, 10:00) Chicago.
    assert entry_window_contains(naive, window, exchange_tz="America/New_York") is False
    assert entry_window_contains(aware_ny, window, exchange_tz="America/New_York") is False
    # 10:15 NY == 09:15 Chicago → inside.
    assert (
        entry_window_contains(
            pd.Timestamp("2026-06-02 10:15:00"),
            window,
            exchange_tz="America/New_York",
        )
        is True
    )


def test_c2_focus_membership_uses_entry_not_exit_timestamps():
    """C2: Focus/Admit classify by entry-bar time — exit-basis must not redefine membership."""
    ts_entry = pd.to_datetime(["2026-06-02 09:45"]).tz_localize("America/New_York")
    # Exit lands in rth_morning while entry is rth_open_30m.
    trades = pd.DataFrame(
        {
            "trade_id": [0],
            "signal_id": [100],
            "entry_timestamp": ts_entry,
            "exit_timestamp": ts_entry + pd.Timedelta(minutes=40),
            "r_multiple": [1.0],
            "direction": ["long"],
        }
    )
    window = {
        "enabled": True,
        "mode": "rth_segments",
        "rth_segments": ["rth_open_30m"],
    }
    by_entry = filter_trades_by_entry_window(trades, window, timestamp_col="entry_timestamp")
    by_exit = filter_trades_by_entry_window(trades, window, timestamp_col="exit_timestamp")
    assert list(by_entry["trade_id"]) == [0]
    assert by_exit.empty


def test_c2_focus_bucket_values_ignore_exit_chart_partition():
    """Focus options must list entry-time buckets, not exit-grouped chart rows."""
    from thesistester.analytics.entry_window import entry_focus_bucket_values
    from thesistester.analytics.time_analysis import add_time_buckets, summarize_by_group

    tz = "America/New_York"
    trades = pd.DataFrame(
        {
            "trade_id": [0, 1],
            "signal_id": [1, 2],
            "entry_timestamp": pd.to_datetime(["2026-06-02 09:45", "2026-06-02 10:15"]).tz_localize(
                tz
            ),
            "exit_timestamp": pd.to_datetime(["2026-06-02 10:15", "2026-06-02 10:45"]).tz_localize(
                tz
            ),
            "r_multiple": [1.0, 2.0],
            "direction": ["long", "long"],
        }
    )
    exit_grouped = summarize_by_group(
        add_time_buckets(trades, timestamp_col="exit_timestamp", exchange_tz=tz),
        "entry_rth_segment",
        min_trades=1,
    )
    # Exit chart shows only morning (both exits), hiding the open-30m entry bucket.
    assert list(exit_grouped["entry_rth_segment"]) == ["rth_morning"]
    focus_values = entry_focus_bucket_values(trades, "entry_rth_segment", exchange_tz=tz)
    assert set(focus_values) == {"rth_open_30m", "rth_morning"}


def test_filter_rth_open_30m_and_multi_segment_or():
    trades = _make_trades(
        [
            "2026-06-02 09:45",  # open
            "2026-06-02 10:15",  # morning
            "2026-06-02 15:30",  # power hour
        ],
        [1.0, -1.0, 0.5],
    )
    open_only = filter_trades_by_entry_window(
        trades,
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
    )
    assert list(open_only["trade_id"]) == [0]

    union = filter_trades_by_entry_window(
        trades,
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m", "rth_power_hour"],
        },
    )
    assert list(union["trade_id"]) == [0, 2]


def test_filter_clock_range_half_open():
    trades = _make_trades(
        ["2026-06-02 09:30", "2026-06-02 09:59", "2026-06-02 10:00"],
        [1.0, 1.0, -1.0],
    )
    filtered = filter_trades_by_entry_window(
        trades,
        {
            "enabled": True,
            "mode": "clock_range",
            "start_time": "09:30",
            "end_time": "10:00",
            "timezone": "America/New_York",
        },
    )
    assert list(filtered["trade_id"]) == [0, 1]


def test_rth_segments_ignore_display_tz_for_membership():
    # 13:45 UTC = 09:45 America/New_York → rth_open_30m
    trades = pd.DataFrame(
        {
            "trade_id": [0],
            "entry_timestamp": [pd.Timestamp("2026-06-02 13:45:00", tz="UTC")],
            "exit_timestamp": [pd.Timestamp("2026-06-02 13:50:00", tz="UTC")],
            "r_multiple": [1.0],
        }
    )
    filtered = filter_trades_by_entry_window(
        trades,
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
            "timezone": "UTC",  # must not force segment evaluation in UTC (C5)
        },
        exchange_tz="America/New_York",
    )
    assert len(filtered) == 1
    assert entry_window_contains(
        trades.loc[0, "entry_timestamp"],
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
        exchange_tz="America/New_York",
    )


def test_summarize_focused_trades_provenance_and_c8():
    trades = _make_trades(
        [
            "2026-06-02 09:45",
            "2026-06-02 10:15",
            "2026-06-02 10:45",
        ],
        [1.9, -1.1, -1.0],
    )
    result = summarize_focused_trades(
        trades,
        entry_window_from_bucket("entry_rth_segment", "rth_open_30m"),
        min_trades=10,
    )
    assert result["focused_trade_summary"]["trade_count"] == 1
    assert result["focused_trade_summary"]["total_r"] == pytest.approx(1.9)
    assert list(result["focused_equity_curve"]["cum_r"]) == pytest.approx([1.9])
    prov = result["focus_provenance"]
    assert prov["sample_warning"] is True
    assert prov["subset_replay_equity"] is True
    assert prov["honesty_banner"] == FOCUS_HONESTY_BANNER
    assert prov["equity_caveat"] == FOCUS_EQUITY_CAVEAT
    assert prov["trade_count_before"] == 3
    assert prov["trade_count_after"] == 1


def test_disabled_window_returns_all_trades():
    trades = _make_trades(["2026-06-02 09:45", "2026-06-02 10:15"], [1.0, -1.0])
    filtered = filter_trades_by_entry_window(trades, None)
    assert len(filtered) == 2


def test_empty_trades_safe():
    empty = pd.DataFrame(columns=["trade_id", "entry_timestamp", "exit_timestamp", "r_multiple"])
    result = summarize_focused_trades(
        empty,
        {
            "enabled": True,
            "mode": "rth_segments",
            "rth_segments": ["rth_open_30m"],
        },
    )
    assert result["focused_trade_summary"]["trade_count"] == 0
    assert result["focused_equity_curve"].empty


def test_add_time_buckets_still_assigns_open_segment():
    trades = _make_trades(["2026-06-02 09:30"], [1.0])
    bucketed = add_time_buckets(trades)
    assert bucketed.loc[0, "entry_rth_segment"] == "rth_open_30m"
