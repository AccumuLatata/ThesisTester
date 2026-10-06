"""TS3 15s clip + hourly hole guard — plan §5 TS3 / §4.4."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from thesistester.data import loader as loader_mod
from thesistester.data.tick_stitch import (
    TickStitchError,
    clip_ticks_to_15s_bars,
    guard_hourly_tick_holes,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION
from thesistester.study import execute as execute_mod


def _utc(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz="UTC")


def _ticks(*stamps: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [_utc(stamp) for stamp in stamps],
            "price": [100.0] * len(stamps),
            "volume": [1.0] * len(stamps),
        }
    )


def _bars(start: str, end: str, *, volume: float = 1.0) -> pd.DataFrame:
    stamps = pd.date_range(_utc(start), _utc(end), freq="15s")
    return pd.DataFrame({"timestamp": stamps, "volume": [volume] * len(stamps)})


def _dense_ticks(start: str, end: str, *, freq: str = "4s") -> pd.DataFrame:
    stamps = pd.date_range(_utc(start), _utc(end), freq=freq)
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "price": [100.0] * len(stamps),
            "volume": [1.0] * len(stamps),
        }
    )


def test_halt_one_lot_print_at_2200_is_clipped_away():
    ticks = _ticks("2026-03-17 21:59:45.010", "2026-03-17 22:00:00.050")
    bars = pd.DataFrame({"timestamp": [_utc("2026-03-17 21:59:45")], "volume": [10.0]})
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert clipped["timestamp"].tolist() == [_utc("2026-03-17 21:59:45.010")]
    guard_hourly_tick_holes(clipped, bars)


def test_cut_short_hour_fails():
    ticks = _ticks("2026-03-17 14:00:00", "2026-03-17 14:51:52")
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clipped, bars)


def test_head_of_hour_hole_fails():
    """First whole volume bar of the hour has no tick (Accumu option A)."""
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = _dense_ticks("2026-03-17 14:00:15", "2026-03-17 14:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_mid_hour_gap_spanning_volume_bars_fails():
    ticks = _ticks("2026-03-17 14:10:00", "2026-03-17 14:10:30")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_sparse_7s_gaps_with_a_tick_in_every_volume_bar_pass():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = _dense_ticks("2026-03-17 14:00:00", "2026-03-17 14:59:59", freq="7s")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert not clipped.empty
    guard_hourly_tick_holes(clipped, bars)


def test_volume_bar_with_no_tick_fails_mid_hour():
    ticks = _ticks("2026-03-17 14:10:00.100", "2026-03-17 14:10:30.050")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_filled_x1_style_1800_hour_one_print_per_bar_at_7_5s_passes():
    bars = _bars("2025-11-07 18:00:00", "2025-11-07 18:59:45")
    ticks = pd.DataFrame(
        {
            "timestamp": bars["timestamp"] + pd.Timedelta(milliseconds=7500),
            "price": [100.0] * len(bars),
            "volume": [1.0] * len(bars),
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert len(clipped) == len(bars)
    guard_hourly_tick_holes(clipped, bars)


def test_filled_hour_plus_7_5s_only_passes_whole_guard():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:59:45")
    ticks = pd.DataFrame(
        {
            "timestamp": bars["timestamp"] + pd.Timedelta(milliseconds=7500),
            "price": [100.0] * len(bars),
            "volume": [1.0] * len(bars),
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_1128_allowlisted_hole_does_not_fail():
    bars = _bars("2025-11-28 08:00:00", "2025-11-28 08:59:45")
    guard_hourly_tick_holes(pd.DataFrame(columns=["timestamp", "price", "volume"]), bars)


def test_hour_with_ticks_but_no_15s_does_not_fail_after_clip():
    ticks = _ticks("2026-03-17 21:00:00.050")
    bars = pd.DataFrame({"timestamp": [_utc("2026-03-17 20:59:45")], "volume": [8.0]})
    bars["volume"] = 8.0
    # Cover the 20:59 bar so the adjacent hour is valid; 21:00 print is clipped.
    ticks = pd.concat(
        [_ticks("2026-03-17 20:59:45.010"), ticks],
        ignore_index=True,
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    assert clipped["timestamp"].dt.hour.tolist() == [20]
    guard_hourly_tick_holes(clipped, bars)


def test_unfilled_x1_hour_fails():
    bars = _bars("2025-11-07 18:00:00", "2025-11-07 18:59:45")
    with pytest.raises(TickStitchError, match="no stitched\\+clipped ticks"):
        guard_hourly_tick_holes(pd.DataFrame(columns=["timestamp", "price", "volume"]), bars)


def test_empty_in_both_weekend_hour_does_not_fail():
    guard_hourly_tick_holes(
        pd.DataFrame(columns=["timestamp", "price", "volume"]),
        pd.DataFrame(columns=["timestamp", "volume"]),
    )


def test_1128_cut_short_after_1330_still_fails():
    """Allowlist (1) is [02:00, 13:30), not the whole 13:00 hour."""
    ticks = _dense_ticks("2025-11-28 13:30:00", "2025-11-28 13:40:00")
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clipped, bars)


def test_1128_healthy_resume_after_1330_passes():
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    ticks = _dense_ticks("2025-11-28 13:30:00", "2025-11-28 13:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_1128_head_of_hour_after_1330_still_fails():
    bars = _bars("2025-11-28 13:30:00", "2025-11-28 13:59:45")
    ticks = _dense_ticks("2025-11-28 13:30:15", "2025-11-28 13:59:59")
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_allowlist_excuses_empty_bars_not_whole_hole():
    """Accumu option A: hole [18:00:54.037, 18:01:37.500) is not contained in
    [18:00:45, 18:01:30), but its whole empty 15s bars are."""
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:37.500")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
    )


def test_1128_whole_empty_bar_after_1330_still_fails():
    """11-28 allowlist stays [02:00, 13:30): empty bar [13:30:00, 13:30:15) is not excused."""
    ticks = _ticks("2025-11-28 13:29:50.100", "2025-11-28 13:30:20.050")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-28 13:29:45"),
                _utc("2025-11-28 13:30:00"),
                _utc("2025-11-28 13:30:15"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)


def test_bar_inside_only_if_half_open_span_fully_in_interval():
    """[t, t+15s) ⊆ interval. Straddle start/end fail; exact edges pass."""
    ticks = _ticks("2025-11-07 18:00:10.000", "2025-11-07 18:00:35.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:00"),
                _utc("2025-11-07 18:00:15"),
                _utc("2025-11-07 18:00:30"),
            ],
            "volume": [4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    # Sole empty whole bar is [18:00:15, 18:00:30). Interval starts at 18:00:20 → straddle.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:20"), _utc("2025-11-07 18:00:30"))],
        )
    # Interval ends at 18:00:20 → bar extends past the end.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:20"))],
        )
    # Exact [18:00:15, 18:00:30) is fully inside.
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:30"))],
    )


def test_partly_allowed_empty_bars_in_one_hole_fail():
    """Same hole: [18:01:00, 18:01:15) inside X1 window, [18:01:30, 18:01:45) not."""
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:50.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
                _utc("2025-11-07 18:01:45"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
        )


def test_several_allowed_intervals_excuse_only_when_every_empty_bar_fits():
    ticks = _ticks("2025-11-07 18:00:10.000", "2025-11-07 18:01:40.000")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:00"),
                _utc("2025-11-07 18:00:15"),
                _utc("2025-11-07 18:00:30"),
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0] * 7,
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    # Gap at [18:00:45, 18:01:00) is not in either interval.
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[
                (_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:45")),
                (_utc("2025-11-07 18:01:00"), _utc("2025-11-07 18:01:30")),
            ],
        )
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[
            (_utc("2025-11-07 18:00:15"), _utc("2025-11-07 18:00:45")),
            (_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30")),
        ],
    )


def test_head_of_hour_and_session_start_use_per_bar_allowlist():
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:02:00"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    ticks = _ticks(
        "2025-11-07 18:01:30.100",
        "2025-11-07 18:01:45.100",
        "2025-11-07 18:02:00.100",
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(clipped, bars)
    with pytest.raises(TickStitchError, match="head-of-hour"):
        guard_hourly_tick_holes(
            clipped,
            bars,
            allowed_intervals=[(_utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:01:00"))],
        )
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:01:30"))],
    )


def test_zero_volume_bar_in_gap_is_not_a_whole_empty_volume_bar():
    """TS3: a mid-hour gap with no volume>0 bar still passes (empty volume-bar set)."""
    ticks = _ticks("2026-03-17 14:10:00", "2026-03-17 14:10:30")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2026-03-17 14:10:00"),
                _utc("2026-03-17 14:10:15"),
                _utc("2026-03-17 14:10:30"),
            ],
            "volume": [4.0, 0.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    guard_hourly_tick_holes(clipped, bars)


def test_tz_aware_chicago_interval_and_naive_utc_match():
    ticks = _ticks("2025-11-07 18:00:54.037", "2025-11-07 18:01:37.500")
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    chicago = (
        pd.Timestamp("2025-11-07 12:00:45", tz="America/Chicago"),
        pd.Timestamp("2025-11-07 12:01:30", tz="America/Chicago"),
    )
    guard_hourly_tick_holes(clipped, bars, allowed_intervals=[chicago])
    naive = (
        pd.Timestamp("2025-11-07 18:00:45"),
        pd.Timestamp("2025-11-07 18:01:30"),
    )
    guard_hourly_tick_holes(clipped, bars, allowed_intervals=[naive])


def test_exact_15s_tick_boundary_empty_bar_is_the_open_right_span():
    """Tick at 18:01:00 is the left edge of that bar; [18:01:15, 18:01:30) is empty."""
    ticks = _ticks(
        "2025-11-07 18:00:50.000",
        "2025-11-07 18:01:00.000",
        "2025-11-07 18:01:30.000",
    )
    bars = pd.DataFrame(
        {
            "timestamp": [
                _utc("2025-11-07 18:00:45"),
                _utc("2025-11-07 18:01:00"),
                _utc("2025-11-07 18:01:15"),
                _utc("2025-11-07 18:01:30"),
            ],
            "volume": [4.0, 4.0, 4.0, 4.0],
        }
    )
    clipped = clip_ticks_to_15s_bars(ticks, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)
    guard_hourly_tick_holes(
        clipped,
        bars,
        allowed_intervals=[(_utc("2025-11-07 18:00:45"), _utc("2025-11-07 18:01:30"))],
    )


def test_1128_cut_short_last_bar_at_1330_fails_last_bar_before_passes():
    """Whole empty bar [13:30:00, 13:30:15) is after the 11-28 end; 13:29:45 is not."""
    ticks = _ticks("2025-11-28 13:20:00.000")
    inside = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-28 13:20:00"), _utc("2025-11-28 13:29:45"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    guard_hourly_tick_holes(clip_ticks_to_15s_bars(ticks, inside["timestamp"]), inside)
    past = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                _utc("2025-11-28 13:20:00"), _utc("2025-11-28 13:30:00"), freq="15s"
            ),
            "volume": 1.0,
        }
    )
    with pytest.raises(TickStitchError, match="cut short"):
        guard_hourly_tick_holes(clip_ticks_to_15s_bars(ticks, past["timestamp"]), past)


def test_caller_inter_file_weekend_is_honored_and_not_invented():
    """§5 TS3 allowlist (4): caller supplies stitch-meta weekends; none are baked in."""
    bars = _bars("2026-03-21 10:00:00", "2026-03-21 10:59:45")
    empty = pd.DataFrame(columns=["timestamp", "price", "volume"])
    with pytest.raises(TickStitchError, match="no stitched\\+clipped ticks"):
        guard_hourly_tick_holes(empty, bars)
    guard_hourly_tick_holes(
        empty,
        bars,
        allowed_intervals=[(_utc("2026-03-21 10:00:00"), _utc("2026-03-21 11:00:00"))],
    )


def test_inverted_allowed_interval_fails_closed():
    bars = _bars("2026-03-17 14:00:00", "2026-03-17 14:00:00")
    ticks = _ticks("2026-03-17 14:00:00")
    with pytest.raises(TickStitchError, match="inverted"):
        guard_hourly_tick_holes(
            ticks,
            bars,
            allowed_intervals=[(_utc("2026-03-21 11:00:00"), _utc("2026-03-21 10:00:00"))],
        )


def test_clip_and_guard_are_not_wired_into_execute_or_streamer():
    assert LEVEL_ENGINE_VERSION == 11
    assert "clip_ticks_to_15s_bars" not in inspect.getsource(execute_mod)
    assert "guard_hourly_tick_holes" not in inspect.getsource(execute_mod)
    assert "clip_ticks_to_15s_bars" not in inspect.getsource(loader_mod)
    from thesistester.data import tick_stitch as stitch_mod

    stream_src = inspect.getsource(stitch_mod.iter_stitch_sessions)
    assert "clip_ticks_to_15s_bars" not in stream_src
    assert "guard_hourly_tick_holes" not in stream_src
    assert "2025-11-07" not in "".join(
        f"{start.isoformat()}{end.isoformat()}" for start, end in stitch_mod._ALLOWLIST_UTC
    )
