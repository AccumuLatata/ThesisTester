"""TS4 X1 15s residual fill + synthetic impact — plan §5 TS4 / §6."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from thesistester.data import loader as loader_mod
from thesistester.data.tick_stitch import (
    TickStitchError,
    apply_x1_residual_fill,
    clip_ticks_to_15s_bars,
    guard_hourly_tick_holes,
    x1_burst_guard_allowed_intervals,
)
from thesistester.levels.apoc_candidates import (
    VOLUME_CONSERVATION_ATOL,
    select_a_period_rows,
)
from thesistester.levels.profile import _bucket_prices
from thesistester.levels.tick_x1_fill import (
    IMPACT_VARIANTS,
    PD_LOOKAHEAD_DATE,
    VARIANT_FILL_WITH_BURST,
    VARIANT_FILL_WITHOUT_BURST,
    VARIANT_TICKS_ONLY,
    X1_BURST_END,
    X1_BURST_EXCLUDED,
    X1_BURST_INTERVAL,
    X1_BURST_START,
    X1_FILL_OFFSET,
    X1_TRADE_DATE,
    X1_WINDOW_END,
    X1_WINDOW_START,
    X1FillError,
    build_synthetic_impact_report,
    fill_x1_15s_residual,
    reject_x1_synthetics,
    run_farm_impact_report,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION
from thesistester.study import execute as execute_mod

TICK_SIZE = 0.25
ISLAND_CONTRACTS = 11_505
ISLAND_TICK_COUNT = 10_000
BURST_BAR_180045 = 100_000.0
BURST_BAR_OTHER = 90_000.0
PLAIN_BAR_VOLUME = 12.0
ISLAND_PRICE = 20_000.00
FILL_PRICE = 20_025.00
APOC_PRICE = 19_900.00


def _utc(stamp: str) -> pd.Timestamp:
    return pd.Timestamp(stamp, tz="UTC")


def _tick_frame(stamps: list[pd.Timestamp], price: float, volume: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "price": [price] * len(stamps),
            "volume": [volume] * len(stamps),
        }
    )


def _bar_row(ts: pd.Timestamp, *, high: float, low: float, close: float, volume: float) -> dict:
    return {
        "timestamp": ts,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _shaped_11_07_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shared empty 16:49–17:58, 10k-tick island, burst bars, 59 min empty."""
    apoc = _tick_frame(
        [_utc("2025-11-07 14:30:00.100"), _utc("2025-11-07 14:40:00.100")],
        APOC_PRICE,
        25.0,
    )
    pre_gap = _tick_frame([_utc("2025-11-07 16:48:00.100")], FILL_PRICE, 3.0)
    head = _tick_frame(
        [_utc("2025-11-07 17:58:00.010"), _utc("2025-11-07 17:58:14.000")],
        FILL_PRICE,
        2.0,
    )
    island_stamps = pd.date_range(
        _utc("2025-11-07 18:00:53.022"),
        _utc("2025-11-07 18:00:54.037"),
        periods=ISLAND_TICK_COUNT,
    )
    island_vol = np.ones(ISLAND_TICK_COUNT, dtype="float64")
    island_vol[-1] += ISLAND_CONTRACTS - ISLAND_TICK_COUNT
    island = pd.DataFrame(
        {
            "timestamp": island_stamps,
            "price": [ISLAND_PRICE] * ISLAND_TICK_COUNT,
            "volume": island_vol,
        }
    )
    resume = _tick_frame([_utc("2025-11-07 19:00:00.100")], FILL_PRICE, 4.0)
    ticks = pd.concat([apoc, pre_gap, head, island, resume], ignore_index=True)

    x1_left = pd.date_range(_utc("2025-11-07 17:58:00"), _utc("2025-11-07 18:59:45"), freq="15s")
    rows = []
    for ts in x1_left:
        if ts == _utc("2025-11-07 18:00:45"):
            rows.append(
                _bar_row(
                    ts,
                    high=ISLAND_PRICE + 10,
                    low=ISLAND_PRICE - 10,
                    close=ISLAND_PRICE,
                    volume=BURST_BAR_180045,
                )
            )
        elif _utc("2025-11-07 18:00:45") < ts < _utc("2025-11-07 18:01:30"):
            rows.append(
                _bar_row(
                    ts,
                    high=ISLAND_PRICE + 10,
                    low=ISLAND_PRICE - 10,
                    close=ISLAND_PRICE,
                    volume=BURST_BAR_OTHER,
                )
            )
        else:
            rows.append(
                _bar_row(
                    ts,
                    high=FILL_PRICE,
                    low=FILL_PRICE,
                    close=FILL_PRICE,
                    volume=PLAIN_BAR_VOLUME,
                )
            )
    rows.append(
        _bar_row(
            _utc("2025-11-07 14:30:00"),
            high=APOC_PRICE,
            low=APOC_PRICE,
            close=APOC_PRICE,
            volume=25.0,
        )
    )
    rows.append(
        _bar_row(
            _utc("2025-11-07 14:40:00"),
            high=APOC_PRICE,
            low=APOC_PRICE,
            close=APOC_PRICE,
            volume=25.0,
        )
    )
    rows.append(
        _bar_row(
            _utc("2025-11-07 16:48:00"),
            high=FILL_PRICE,
            low=FILL_PRICE,
            close=FILL_PRICE,
            volume=3.0,
        )
    )
    rows.append(
        _bar_row(
            _utc("2025-11-07 19:00:00"),
            high=FILL_PRICE,
            low=FILL_PRICE,
            close=FILL_PRICE,
            volume=8.0,
        )
    )
    rows.append(
        _bar_row(
            _utc("2025-11-10 15:05:00"),
            high=20_100.00,
            low=20_100.00,
            close=20_100.00,
            volume=7.0,
        )
    )
    bars = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return ticks, bars


def _extra(filled: pd.DataFrame, ticks: pd.DataFrame) -> pd.DataFrame:
    left = pd.to_datetime(filled["timestamp"], utc=True)
    right = pd.to_datetime(ticks["timestamp"], utc=True)
    return filled.loc[~left.isin(set(right))].copy()


def _fill(
    ticks: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    burst: bool,
    session_date: date = X1_TRADE_DATE,
) -> tuple[pd.DataFrame, object]:
    return fill_x1_15s_residual(
        ticks,
        bars,
        tick_stitch_x1_burst_included=burst,
        session_date=session_date,
        tick_size=TICK_SIZE,
    )


def test_burst_flag_has_no_silent_default():
    params = inspect.signature(fill_x1_15s_residual).parameters
    assert params["tick_stitch_x1_burst_included"].default is inspect.Parameter.empty
    hook = inspect.signature(apply_x1_residual_fill).parameters
    assert hook["tick_stitch_x1_burst_included"].default is inspect.Parameter.empty
    ticks, bars = _shaped_11_07_fixture()
    with pytest.raises(TypeError, match="tick_stitch_x1_burst_included"):
        fill_x1_15s_residual(ticks, bars, session_date=X1_TRADE_DATE, tick_size=TICK_SIZE)
    with pytest.raises(TypeError, match="explicit bool"):
        fill_x1_15s_residual(
            ticks,
            bars,
            tick_stitch_x1_burst_included=1,  # type: ignore[arg-type]
            session_date=X1_TRADE_DATE,
            tick_size=TICK_SIZE,
        )


def test_fill_timestamps_lie_only_inside_locked_window():
    ticks, bars = _shaped_11_07_fixture()
    filled, _quality = _fill(ticks, bars, burst=True)
    extra = _extra(filled, ticks)
    assert not extra.empty
    assert extra["timestamp"].min() >= X1_WINDOW_START
    assert extra["timestamp"].max() < X1_WINDOW_END
    assert not extra["timestamp"].eq(_utc("2025-11-07 17:58:07.500")).any()
    assert not extra["timestamp"].eq(_utc("2025-11-07 19:00:07.500")).any()
    assert (extra["timestamp"] == extra["timestamp"].dt.floor("15s") + X1_FILL_OFFSET).all()


def test_190000_bar_left_edge_in_window_but_placement_outside_is_unfilled():
    """Bar 19:00:00 is in [17:58:14.581, 19:00:00.009); +7.5s is not."""
    left = _utc("2025-11-07 19:00:00")
    placed = left + X1_FILL_OFFSET
    assert X1_WINDOW_START <= left < X1_WINDOW_END
    assert not (X1_WINDOW_START <= placed < X1_WINDOW_END)
    ticks, bars = _shaped_11_07_fixture()
    filled, _quality = _fill(ticks, bars, burst=True)
    extra = _extra(filled, ticks)
    assert extra["timestamp"].min() >= X1_WINDOW_START
    assert extra["timestamp"].max() < X1_WINDOW_END
    assert not extra["timestamp"].eq(placed).any()
    assert extra["timestamp"].eq(_utc("2025-11-07 18:59:52.500")).sum() == 1


def test_175800_bar_is_not_filled_and_shared_gap_is_not_filled():
    ticks, bars = _shaped_11_07_fixture()
    filled, quality = _fill(ticks, bars, burst=False)
    extra = _extra(filled, ticks)
    gap = extra.loc[
        (extra["timestamp"] >= _utc("2025-11-07 16:49:00"))
        & (extra["timestamp"] < _utc("2025-11-07 17:58:00"))
    ]
    assert gap.empty
    assert not extra["timestamp"].eq(_utc("2025-11-07 17:58:07.500")).any()
    assert quality.shared_gap_1649_1758 is True
    assert quality.x1_15s_residual_fill is True


def test_residual_is_max_zero_15s_minus_tick_and_island_does_not_double_count():
    ticks, bars = _shaped_11_07_fixture()
    filled, quality = _fill(ticks, bars, burst=True)
    extra = _extra(filled, ticks)
    island_synthetic = extra.loc[extra["timestamp"] == _utc("2025-11-07 18:00:52.500")]
    assert len(island_synthetic) == 1
    expected = BURST_BAR_180045 - ISLAND_CONTRACTS
    assert island_synthetic["volume"].iloc[0] == pytest.approx(
        expected, abs=VOLUME_CONSERVATION_ATOL
    )
    assert island_synthetic["volume"].iloc[0] != pytest.approx(BURST_BAR_180045)
    tick_vol = (
        ticks.assign(floor=ticks["timestamp"].dt.floor("15s")).groupby("floor")["volume"].sum()
    )
    x1_bars = bars.loc[
        (bars["timestamp"] >= X1_WINDOW_START)
        & (bars["timestamp"] < X1_WINDOW_END)
        & ((bars["timestamp"] + X1_FILL_OFFSET) < X1_WINDOW_END)
    ]
    expected_sum = 0.0
    for row in x1_bars.itertuples(index=False):
        residual = max(0.0, float(row.volume) - float(tick_vol.get(row.timestamp, 0.0)))
        expected_sum += residual
    assert extra["volume"].sum() == pytest.approx(expected_sum, abs=VOLUME_CONSERVATION_ATOL)
    assert quality.residual_volume == pytest.approx(expected_sum, abs=VOLUME_CONSERVATION_ATOL)
    typical = pd.Series([(ISLAND_PRICE + 10 + ISLAND_PRICE - 10 + ISLAND_PRICE) / 3.0])
    assert island_synthetic["price"].iloc[0] == pytest.approx(
        float(_bucket_prices(typical, TICK_SIZE).iloc[0])
    )


def test_burst_off_leaves_burst_bars_at_residual_zero():
    ticks, bars = _shaped_11_07_fixture()
    filled, quality = _fill(ticks, bars, burst=False)
    extra = _extra(filled, ticks)
    burst_left = pd.date_range(X1_BURST_START, X1_BURST_END - pd.Timedelta(seconds=15), freq="15s")
    for left in burst_left:
        assert extra["timestamp"].eq(left + X1_FILL_OFFSET).sum() == 0
    assert extra["timestamp"].eq(_utc("2025-11-07 18:02:07.500")).sum() == 1
    assert quality.x1_burst_included is False
    assert quality.x1_burst == X1_BURST_EXCLUDED
    assert quality.guard_allowed_intervals() == (X1_BURST_INTERVAL,)


def test_burst_on_tags_x1_burst_synthetics():
    ticks, bars = _shaped_11_07_fixture()
    filled, quality = _fill(ticks, bars, burst=True)
    extra = _extra(filled, ticks)
    assert extra["timestamp"].eq(_utc("2025-11-07 18:00:52.500")).sum() == 1
    assert extra["timestamp"].eq(_utc("2025-11-07 18:01:07.500")).sum() == 1
    assert extra["timestamp"].eq(_utc("2025-11-07 18:01:22.500")).sum() == 1
    assert quality.x1_burst_included is True
    assert quality.x1_burst is True
    assert quality.burst_synthetic_volume == pytest.approx(
        (BURST_BAR_180045 - ISLAND_CONTRACTS) + BURST_BAR_OTHER + BURST_BAR_OTHER,
        abs=VOLUME_CONSERVATION_ATOL,
    )


def test_synthetics_never_appear_in_select_a_period_rows():
    ticks, bars = _shaped_11_07_fixture()
    filled, _quality = _fill(ticks, bars, burst=True)
    selected = select_a_period_rows(
        filled,
        session_date=X1_TRADE_DATE,
        exchange_tz="America/New_York",
    )
    assert not selected.empty
    assert selected["timestamp"].max() < _utc("2025-11-07 15:00:00")
    assert selected["timestamp"].min() >= _utc("2025-11-07 14:30:00")
    extra = _extra(filled, ticks)
    assert extra["timestamp"].isin(selected["timestamp"]).sum() == 0
    rejected = reject_x1_synthetics(filled)
    assert (
        rejected["timestamp"].ge(X1_WINDOW_START).mul(rejected["timestamp"].lt(X1_WINDOW_END)).sum()
        == 0
    )


def test_quality_flag_true_only_for_2025_11_07():
    ticks, bars = _shaped_11_07_fixture()
    _filled, quality = _fill(ticks, bars, burst=True)
    assert quality.as_data_quality() == {
        "data_quality.x1_15s_residual_fill": True,
        "data_quality.x1_burst_included": True,
        "data_quality.shared_gap_1649_1758": True,
    }
    other, other_q = _fill(ticks, bars, burst=False, session_date=date(2025, 11, 10))
    assert _extra(other, ticks).empty
    assert other_q.x1_15s_residual_fill is False
    assert other_q.shared_gap_1649_1758 is False
    assert other_q.x1_burst_included is False
    assert other_q.n_synthetics == 0


def test_filled_x1_1800_hour_passes_ts3_guard_option_a():
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    filled, _quality = _fill(ticks, bars, burst=True)
    clipped = clip_ticks_to_15s_bars(filled, hour_bars["timestamp"])
    guard_hourly_tick_holes(clipped, hour_bars)


def test_unfilled_x1_hour_still_fails_guard():
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    clipped = clip_ticks_to_15s_bars(ticks, hour_bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped, hour_bars)


def test_fill_without_burst_does_not_bypass_guard_on_burst_volume_bars():
    """Burst-off without the Accumu option A interval still fails TS3 containment."""
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    filled, quality = _fill(ticks, bars, burst=False)
    assert quality.x1_burst == X1_BURST_EXCLUDED
    clipped = clip_ticks_to_15s_bars(filled, hour_bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, hour_bars)


def test_x1_burst_interval_is_exact_half_open_window():
    assert X1_BURST_INTERVAL == (
        _utc("2025-11-07 18:00:45"),
        _utc("2025-11-07 18:01:30"),
    )
    assert X1_BURST_INTERVAL == (X1_BURST_START, X1_BURST_END)
    assert x1_burst_guard_allowed_intervals(True) == ()
    assert x1_burst_guard_allowed_intervals(False) == (X1_BURST_INTERVAL,)
    assert x1_burst_guard_allowed_intervals(False, session_date=X1_TRADE_DATE) == (
        X1_BURST_INTERVAL,
    )
    assert x1_burst_guard_allowed_intervals(False, session_date=date(2025, 11, 10)) == ()


def _compact_burst_off_guard_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Burst-off hour whose tick-to-tick hole is contained in X1_BURST_INTERVAL."""
    compact_left = pd.date_range(
        _utc("2025-11-07 18:00:00"), _utc("2025-11-07 18:01:45"), freq="15s"
    )
    bars = pd.DataFrame(
        [
            _bar_row(
                ts,
                high=FILL_PRICE if ts < X1_BURST_START else ISLAND_PRICE + 10,
                low=FILL_PRICE if ts < X1_BURST_START else ISLAND_PRICE - 10,
                close=FILL_PRICE if ts < X1_BURST_START else ISLAND_PRICE,
                volume=PLAIN_BAR_VOLUME if ts < X1_BURST_START or ts >= X1_BURST_END else 90_000.0,
            )
            for ts in compact_left
        ]
    )
    ticks = pd.concat(
        [
            _tick_frame([_utc("2025-11-07 18:00:00.100")], FILL_PRICE, 2.0),
            _tick_frame([_utc("2025-11-07 18:00:45.050")], ISLAND_PRICE, 2.0),
            _tick_frame([_utc("2025-11-07 18:01:30.000")], FILL_PRICE, 1.0),
        ],
        ignore_index=True,
    )
    return ticks, bars


def test_burst_off_passes_hourly_guard_only_via_exact_burst_interval():
    """Accumu option A: burst-off allowlists exactly [18:00:45, 18:01:30)."""
    ticks, bars = _compact_burst_off_guard_frames()
    filled, quality = _fill(ticks, bars, burst=False)
    assert quality.x1_burst == X1_BURST_EXCLUDED
    assert quality.x1_burst_included is False
    clipped = clip_ticks_to_15s_bars(filled, bars["timestamp"])
    with pytest.raises(TickStitchError, match="mid-hour"):
        guard_hourly_tick_holes(clipped, bars)
    allowed = quality.guard_allowed_intervals()
    assert allowed == (X1_BURST_INTERVAL,)
    guard_hourly_tick_holes(clipped, bars, allowed_intervals=allowed)


def test_burst_off_hole_outside_burst_interval_still_fails():
    ticks, bars = _compact_burst_off_guard_frames()
    filled, quality = _fill(ticks, bars, burst=False)
    assert quality.x1_burst == X1_BURST_EXCLUDED
    outside = pd.DataFrame(
        [
            _bar_row(
                _utc("2025-11-07 18:10:00"),
                high=FILL_PRICE,
                low=FILL_PRICE,
                close=FILL_PRICE,
                volume=PLAIN_BAR_VOLUME,
            )
        ]
    )
    guard_bars = pd.concat([bars, outside], ignore_index=True)
    clipped = clip_ticks_to_15s_bars(filled, guard_bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(
            clipped,
            guard_bars,
            allowed_intervals=quality.guard_allowed_intervals(),
        )


def test_shaped_1107_burst_off_exact_interval_does_not_contain_plus_75s_hole():
    """11-07 hole is [18:00:54.037, 18:01:37.5); guard rule is unchanged."""
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    filled, quality = _fill(ticks, bars, burst=False)
    assert quality.x1_burst == X1_BURST_EXCLUDED
    clipped = clip_ticks_to_15s_bars(filled, hour_bars["timestamp"])
    with pytest.raises(TickStitchError, match="18:01:37.500"):
        guard_hourly_tick_holes(
            clipped,
            hour_bars,
            allowed_intervals=quality.guard_allowed_intervals(),
        )


def test_burst_on_still_passes_guard_with_no_interval():
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    filled, quality = _fill(ticks, bars, burst=True)
    assert quality.x1_burst is True
    assert quality.guard_allowed_intervals() == ()
    clipped = clip_ticks_to_15s_bars(filled, hour_bars["timestamp"])
    guard_hourly_tick_holes(clipped, hour_bars)


def test_ci_impact_emits_three_triples_and_identical_apoc():
    ticks, bars = _shaped_11_07_fixture()
    later = _tick_frame([_utc("2025-11-10 15:05:00.100")], 20_100.00, 7.0)
    report = build_synthetic_impact_report(
        {X1_TRADE_DATE: ticks, PD_LOOKAHEAD_DATE: later},
        bars,
        instrument="MNQ",
    )
    assert tuple(report["variants"]) == IMPACT_VARIANTS
    assert VARIANT_TICKS_ONLY in report["variants"]
    assert VARIANT_FILL_WITHOUT_BURST in report["variants"]
    assert VARIANT_FILL_WITH_BURST in report["variants"]
    assert report["apoc_identical"] is True
    apocs = [report["variants"][name]["apoc_2025-11-07"] for name in IMPACT_VARIANTS]
    assert apocs[0] == apocs[1] == apocs[2]
    assert apocs[0] == pytest.approx(APOC_PRICE)
    for name in IMPACT_VARIANTS:
        row = report["variants"][name]
        for key in (
            "session_2025-11-07",
            "pd_2025-11-10",
            "pw_w_sun_containing_2025-11-07",
            "pm_2025-11",
            "pm_prior_month_2025-12",
        ):
            assert set(row[key]) >= {"VAH", "VAL", "POC"}
            for field in ("VAH", "VAL", "POC"):
                assert np.isfinite(row[key][field])
        assert row["pw_w_sun_containing_2025-11-07"]["period_key"] == "2025-11-03/2025-11-09"
    assert "q9" in report
    assert "no product default" in report["q9"]
    assert "deltas" in report
    for name in IMPACT_VARIANTS:
        row = report["variants"][name]
        assert row["pd_2025-11-10"] == row["session_2025-11-07"]
        assert row["pm_prior_month_2025-12"] == row["pm_2025-11"]


def test_apply_hook_matches_fill_and_is_not_execute_wired():
    ticks, bars = _shaped_11_07_fixture()
    direct, quality = _fill(ticks, bars, burst=True)
    hooked, hooked_q = apply_x1_residual_fill(
        ticks,
        bars,
        tick_stitch_x1_burst_included=True,
        session_date=X1_TRADE_DATE,
        tick_size=TICK_SIZE,
    )
    pd.testing.assert_frame_equal(direct, hooked)
    assert hooked_q.x1_burst_included is quality.x1_burst_included
    assert LEVEL_ENGINE_VERSION == 11
    assert "fill_x1_15s_residual" not in inspect.getsource(execute_mod)
    assert "tick_x1_fill" not in inspect.getsource(execute_mod)
    assert "apply_x1_residual_fill" not in inspect.getsource(execute_mod)
    assert "x1_burst_guard_allowed_intervals" not in inspect.getsource(execute_mod)
    assert "tick_x1_fill" not in inspect.getsource(loader_mod)
    import thesistester.levels.tick_x1_fill as fill_mod

    assert "_bucket_prices" in inspect.getsource(fill_mod._residual_synthetics)


def test_farm_impact_cli_on_synthetic_fixture(tmp_path: Path):
    ticks, bars = _shaped_11_07_fixture()
    later = _tick_frame([_utc("2025-11-10 15:05:00.100")], 20_100.00, 7.0)
    ticks = pd.concat([ticks, later], ignore_index=True)
    tick_name = "MNQ Tick - Tick - Last, 11_7_2025 100000 AM-11_10_2025 100000 AM.csv"
    tick_path = tmp_path / tick_name
    with tick_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("Aggressor flag;Price;Volume;Time left;\n")
        for row in ticks.itertuples(index=False):
            stamp = (
                pd.Timestamp(row.timestamp).tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )
            handle.write(f";{row.price};{row.volume};{stamp};\n")
    bars_path = tmp_path / "bars.csv"
    with bars_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("Time left;Open;High;Low;Close;Volume\n")
        for row in bars.itertuples(index=False):
            stamp = pd.Timestamp(row.timestamp).tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")
            handle.write(f"{stamp};{row.close};{row.high};{row.low};{row.close};{row.volume}\n")
    first = pd.Timestamp(ticks["timestamp"].min()).tz_convert("UTC")
    last = pd.Timestamp(ticks["timestamp"].max()).tz_convert("UTC")
    plan = [
        {
            "filename": tick_name,
            "size_bytes": tick_path.stat().st_size,
            "effective_first_utc": first.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "effective_last_utc": last.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "file_first_utc": first.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "file_last_utc": last.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
    ]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesistester.levels.tick_x1_fill",
            "farm-impact",
            str(plan_path),
            str(tmp_path),
            str(bars_path),
            "--instrument",
            "MNQ",
            "--format-profile",
            "quantower_history_exporter",
            "--source-tz",
            "UTC",
            "--target-tz",
            "UTC",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == os.EX_OK, completed.stderr
    report = json.loads(completed.stdout)
    assert set(report["variants"]) == set(IMPACT_VARIANTS)
    assert report["apoc_identical"] is True
    for name in IMPACT_VARIANTS:
        row = report["variants"][name]
        assert "session_2025-11-07" in row
        assert "pd_2025-11-10" in row
        assert "pw_w_sun_containing_2025-11-07" in row
        assert "pm_2025-11" in row
        assert "pm_prior_month_2025-12" in row
        for key in (
            "session_2025-11-07",
            "pd_2025-11-10",
            "pw_w_sun_containing_2025-11-07",
            "pm_2025-11",
            "pm_prior_month_2025-12",
        ):
            for field in ("VAH", "VAL", "POC"):
                assert np.isfinite(row[key][field])
        assert row["pd_2025-11-10"] == row["session_2025-11-07"]
        assert row["pm_prior_month_2025-12"] == row["pm_2025-11"]


def test_farm_impact_does_not_call_hourly_guard_and_still_emits_all_variants():
    """Ticks-only / burst-off fail TS3 option A; farm-impact must not abort."""
    import thesistester.levels.tick_x1_fill as fill_mod

    assert "guard_hourly_tick_holes(" not in inspect.getsource(fill_mod.run_farm_impact_report)
    assert "guard_hourly_tick_holes(" not in inspect.getsource(fill_mod.main)
    ticks, bars = _shaped_11_07_fixture()
    hour_bars = bars.loc[bars["timestamp"].dt.floor("h") == _utc("2025-11-07 18:00:00")]
    clipped = clip_ticks_to_15s_bars(ticks, hour_bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped, hour_bars)
    filled_off, _quality = _fill(ticks, bars, burst=False)
    clipped_off = clip_ticks_to_15s_bars(filled_off, hour_bars["timestamp"])
    with pytest.raises(TickStitchError):
        guard_hourly_tick_holes(clipped_off, hour_bars)
    later = _tick_frame([_utc("2025-11-10 15:05:00.100")], 20_100.00, 7.0)
    report = build_synthetic_impact_report(
        {X1_TRADE_DATE: ticks, PD_LOOKAHEAD_DATE: later},
        bars,
        instrument="MNQ",
    )
    assert tuple(report["variants"]) == IMPACT_VARIANTS
    assert report["apoc_identical"] is True


def test_farm_impact_refuses_nas_trading_without_reading_it():
    with pytest.raises(X1FillError, match="nas-trading"):
        run_farm_impact_report(
            "/mnt/nas-trading/plan.json",
            "/tmp/tick-root",
            "/tmp/bars.csv",
        )
    with pytest.raises(X1FillError, match="nas-trading"):
        run_farm_impact_report(
            "/tmp/plan.json",
            "/mnt/nas-trading/ticks",
            "/tmp/bars.csv",
        )
    with pytest.raises(X1FillError, match="nas-trading"):
        run_farm_impact_report(
            "/tmp/plan.json",
            "/tmp/tick-root",
            "/mnt/nas-trading/bars.csv",
        )
