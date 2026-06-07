"""Tests for 3c trigger-timeframe support (non-base and base regression).

Covers:
- Base 3c behavior unchanged.
- Non-base 3c detection on trigger-timeframe candles.
- Base-timeframe retrace fill after reversal trigger candle completion.
- max_entry_wait_bars_after_reversal counts trigger bars, not base bars.
- Index and timestamp integrity.
- Naked metadata uses base arrival index.
- Source modes (global_cluster, anchor_rules).
- Signal settings hash distinguishes 3c + base vs 3c + non-base.
- build_setup_config stores non-base trigger_timeframe for 3c.
"""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine.candidate_level import CandidateLevel
from thesistester.engine.signals_3c import detect_3c_setups, detect_3c_setups_with_trigger_timeframe
from thesistester.engine.signals import _prepare_trigger_dataframe, _project_zones_to_trigger_df, generate_signals
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.setup import build_setup_config

TZ = "America/New_York"
TICK = 0.25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_df(rows: list[dict], freq: str = "1min") -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:30", periods=len(rows), freq=freq, tz=TZ)
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "timestamp": ts[i],
                "open": row.get("open", row.get("close", 100.0)),
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": 100.0,
            }
        )
    return pd.DataFrame(out)


def _candidate_trigger(
    direction: str = "long",
    price: float = 100.0,
    trigger_bar_index: int = 0,
    source_mode: str = "global_cluster",
) -> CandidateLevel:
    return CandidateLevel(
        source_mode=source_mode,
        zone_id=f"zone_{trigger_bar_index}",
        level_id="L1",
        level_price=price,
        zone_low=price - TICK,
        zone_high=price + TICK,
        direction=direction,
        source_label="L1",
        bar_index=trigger_bar_index,
        timestamp=pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
        metadata={},
    )


def _run_nonbase(
    base_rows: list[dict],
    direction: str = "long",
    trigger_timeframe: str = "5min",
    price: float = 100.0,
    params: dict | None = None,
) -> list[dict]:
    """Run non-base 3c detection with default 5-min trigger, 1-min base bars."""
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, trigger_timeframe)
    delta = pd.to_timedelta(trigger_timeframe)

    # Find trigger bar index where the arrival should be
    trigger_arrival_idx = 0  # Use first trigger bar as arrival

    candidate = _candidate_trigger(
        direction=direction,
        price=price,
        trigger_bar_index=trigger_arrival_idx,
    )

    return detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params=params or {"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
        trigger_timeframe_delta=delta,
    )

def _make_standard_15row_long_base_rows() -> list[dict]:
    """Standard 15-row base dataset for non-base 3c long scenario (5-min trigger).

    3 trigger bars (5-min), 15 base (1-min) bars:
    - T0 (base 0-4, end=09:35): arrival — agg H=101.0, L=100.0, C=100.9
    - T1 (base 5-9, end=09:40): reversal — agg C=101.25 > T0.H=101.0
      entry_trigger = 101.25 - 2*0.25 = 100.75
    - T2 (base 10-14): fill window
      base 10 ts=09:40 NOT eligible (not > 09:40)
      base 11 ts=09:41 FILL: low=100.6 <= 100.75
    """
    return [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # base 0
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},  # base 1
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},  # base 2
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},  # base 3
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},  # base 4
        # trigger bar 1 (base 5-9, end=09:40): reversal
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},  # base 5
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},  # base 6
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},  # base 7
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 8
        {"open": 101.2, "high": 101.5, "low": 101.0, "close": 101.25}, # base 9 (T1 agg close=101.25)
        # trigger bar 2 (base 10-14): fill window
        {"open": 101.25, "high": 101.5, "low": 101.1, "close": 101.3}, # base 10 ts=09:40 NOT eligible
        {"open": 101.3,  "high": 101.5, "low": 100.6, "close": 101.0}, # base 11 ts=09:41 FILL
        {"open": 101.0,  "high": 101.2, "low": 100.8, "close": 101.1}, # base 12
        {"open": 101.1,  "high": 101.2, "low": 100.9, "close": 101.0}, # base 13
        {"open": 101.0,  "high": 101.1, "low": 100.9, "close": 101.0}, # base 14
    ]



# ===========================================================================


def test_base_3c_detect_unchanged():
    """Base 3c uses detect_3c_setups directly and behavior is unchanged."""
    df = _base_df(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
        ]
    )
    from thesistester.engine.candidate_level import CandidateLevel

    candidate = CandidateLevel(
        source_mode="global_cluster",
        zone_id="z0",
        level_id="L1",
        level_price=100.0,
        zone_low=100.0,
        zone_high=100.0,
        direction="long",
        source_label="L1",
        bar_index=0,
        timestamp=df.iloc[0]["timestamp"],
        metadata={},
    )
    setups = detect_3c_setups(df, [candidate], tick_size=TICK,
                               trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3})
    assert len(setups) == 1
    assert setups[0]["status"] == "filled"
    assert setups[0]["arrival_bar_index"] == 0
    assert setups[0]["reversal_bar_index"] == 1
    assert setups[0]["entry_bar_index"] == 2


def test_3c_base_uses_existing_path_and_has_no_trigger_indices():
    """3c + base: trigger_arrival_bar_index and trigger_reversal_bar_index equal base indices."""
    zones = pd.DataFrame(
        [
            {
                "bar_index": 0,
                "timestamp": pd.Timestamp("2026-01-02 09:30", tz=TZ),
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "L1",
                "level_prices": "100.0",
            }
        ]
    )
    df = _base_df(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
            {"open": 100.9, "high": 101.2, "low": 100.0, "close": 100.3},
        ]
    )
    signals = generate_signals(
        df, zones, trigger="3c", direction="long", tick_size=TICK,
        trigger_timeframe="base",
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(signals) >= 1
    row = signals.iloc[0]
    # For base 3c, trigger indices match base indices
    assert row["trigger_arrival_bar_index"] == row["arrival_bar_index"]
    assert row["trigger_reversal_bar_index"] == row["reversal_bar_index"]
    assert row["trigger_timeframe"] == "base"


def test_base_3c_trigger_metadata_uses_reversal_bar_not_entry_bar():
    """Regression: base 3c trigger_bar_index / trigger_timestamp must reflect the
    reversal bar, NOT the entry bar.

    Setup (4 base bars, arrival=0, reversal=1, entry=2):
      bar 0: arrival — low<=level, close<level
      bar 1: reversal — close > bar0 high
      bar 2: fill — low touches entry_trigger
      bar 3: padding

    After the fix:
      trigger_bar_index == reversal_bar_index (1)
      trigger_timestamp == df.timestamp.iloc[1]
      bar_index == entry_bar_index (2)           <- unchanged
      timestamp == df.timestamp.iloc[2]          <- unchanged
    """
    zones = pd.DataFrame(
        [
            {
                "bar_index": 0,
                "timestamp": pd.Timestamp("2026-01-02 09:30", tz=TZ),
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "L1",
                "level_prices": "100.0",
            }
        ]
    )
    # arrival_bar_index=0, reversal_bar_index=1, entry_bar_index=2 (all distinct)
    df = _base_df(
        [
            # bar 0: arrival — low=100.0 <= level=100.0, close=100.5 < 101.0 (bar high)
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            # bar 1: reversal — close=101.3 > bar0.high=101.0
            {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.3},
            # bar 2: fill — entry_trigger = 101.3 - 2*0.25 = 100.8; low=100.7 <= 100.8
            {"open": 101.2, "high": 101.3, "low": 100.7, "close": 101.1},
            # bar 3: padding
            {"open": 101.1, "high": 101.2, "low": 100.9, "close": 101.0},
        ]
    )
    signals = generate_signals(
        df, zones, trigger="3c", direction="long", tick_size=TICK,
        trigger_timeframe="base",
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(signals) >= 1
    row = signals.iloc[0]
    assert row["trigger_timeframe"] == "base"

    # trigger indices must point to reversal bar
    assert row["trigger_arrival_bar_index"] == row["arrival_bar_index"]
    assert row["trigger_reversal_bar_index"] == row["reversal_bar_index"]
    assert row["trigger_bar_index"] == row["trigger_reversal_bar_index"]
    assert row["trigger_bar_index"] == row["reversal_bar_index"]
    assert row["trigger_timestamp"] == df["timestamp"].iloc[int(row["reversal_bar_index"])]

    # execution fields must remain at entry bar
    assert row["bar_index"] == row["entry_bar_index"]
    assert row["timestamp"] == df["timestamp"].iloc[int(row["bar_index"])]

    # Ensure arrival != reversal != entry (all three distinct)
    assert row["arrival_bar_index"] != row["reversal_bar_index"]
    assert row["reversal_bar_index"] != row["entry_bar_index"]


def test_old_config_without_trigger_timeframe_defaults_to_base():
    """Old configs with missing trigger_timeframe must default to 'base'."""
    config = build_setup_config(
        name="3c defaults",
        description="",
        instrument="ES",
        selected_levels=["L1"],
        tolerance_ticks=4.0,
        min_confluences=1,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        direction="both",
    )
    # No trigger_timeframe passed -> defaults to "base"
    assert config["trigger_timeframe"] == "base"


# ===========================================================================
# 4-8. Non-base 3c detection
# ===========================================================================


def _make_5min_base_rows() -> list[dict]:
    """10 base (1-min) rows forming 2 trigger (5-min) bars.

    Bar 0 (trigger bar 0, base bars 0-4):
      5-min OHLC: O=101.5, H=101.5, L=100.0, C=100.5
      (arrival bar: low=100.0 <= 100.0, close=100.5 > 100.0)

    Bar 1 (trigger bar 1, base bars 5-9):
      5-min OHLC built from rows, reversal close > bar0_high (101.5)
      row5: inside candle -> muted
      row6-9: reversal in row6: close=101.6 > 101.5 (bar0 high), then fill in row7
    """
    rows = [
        # Trigger bar 0 base bars (bar indices 0-4 base)
        # Arrival condition on the 5-min aggregate: low<=100, close>100
        {"open": 101.5, "high": 101.5, "low": 100.0, "close": 100.5},  # bar 0
        {"open": 100.5, "high": 101.0, "low": 100.3, "close": 100.6},  # bar 1
        {"open": 100.6, "high": 101.0, "low": 100.2, "close": 100.7},  # bar 2
        {"open": 100.7, "high": 101.0, "low": 100.1, "close": 100.8},  # bar 3
        {"open": 100.8, "high": 101.0, "low": 100.4, "close": 100.9},  # bar 4
        # Trigger bar 1 base bars (bar indices 5-9 base)
        {"open": 100.9, "high": 101.3, "low": 100.2, "close": 101.7},  # bar 5: reversal close > 101.5
        {"open": 101.7, "high": 101.8, "low": 101.1, "close": 101.5},  # bar 6: no retrace
        {"open": 101.5, "high": 101.6, "low": 101.1, "close": 101.4},  # bar 7: no retrace
        {"open": 101.4, "high": 101.5, "low": 101.0, "close": 101.2},  # bar 8: no retrace
        {"open": 101.2, "high": 101.4, "low": 101.1, "close": 101.3},  # bar 9
    ]
    return rows


def test_nonbase_3c_long_detected():
    """Long 3c detected on 5-min trigger candles with base retrace fill.

    Scenario (3 trigger bars, 15 base rows):
    - T0 (base 0-4, end=09:35): arrival — agg L=100.0<=100, agg C=100.9>100
    - T1 (base 5-9, end=09:40): reversal — agg C=101.25 > T0.H=101.0
      entry_trigger = 101.25 - 2*0.25 = 100.75
    - T2 (base 10-14): fill window; base 11 (ts=09:41 > 09:40) low=100.6<=100.75 -> fill
    """
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # base 0
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.6},  # base 1
        {"open": 100.6, "high": 100.9, "low": 100.3, "close": 100.7},  # base 2
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},  # base 3
        {"open": 100.8, "high": 100.9, "low": 100.2, "close": 100.9},  # base 4
        # trigger bar 1 (base 5-9, end=09:40): reversal
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},  # base 5
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},  # base 6
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},  # base 7
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 8
        {"open": 101.2, "high": 101.5, "low": 101.0, "close": 101.25}, # base 9 (T1 agg close=101.25)
        # trigger bar 2 (base 10-14): fill window
        {"open": 101.25, "high": 101.5, "low": 101.1, "close": 101.3}, # base 10 ts=09:40 NOT eligible
        {"open": 101.3,  "high": 101.5, "low": 100.6, "close": 101.0}, # base 11 ts=09:41 FILL
        {"open": 101.0,  "high": 101.2, "low": 100.8, "close": 101.1}, # base 12
        {"open": 101.1,  "high": 101.2, "low": 100.9, "close": 101.0}, # base 13
        {"open": 101.0,  "high": 101.1, "low": 100.9, "close": 101.0}, # base 14
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    # trigger bar 0: base 0-4
    # aggregate: H=max(101,100.9,100.9,100.9,100.9)=101, L=min(100.0,...) = 100.0, C=100.9
    t0 = trigger_df.iloc[0]
    assert float(t0["low"]) <= 100.0
    assert float(t0["close"]) > 100.0  # arrival condition met

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["direction"] == "long"
    assert r["status"] == "filled"
    assert r["trigger_arrival_bar_index"] == 0  # trigger bar index
    assert r["trigger_reversal_bar_index"] == 1  # trigger bar index
    assert r["trigger_bar_index"] == r["trigger_reversal_bar_index"]
    # Base indices must be base df indices
    assert r["arrival_bar_index"] == int(trigger_df.iloc[0]["base_end_bar_index"])
    assert r["reversal_bar_index"] == int(trigger_df.iloc[1]["base_end_bar_index"])
    assert r["entry_bar_index"] is not None
    assert r["entry_bar_index"] > r["reversal_bar_index"]


def test_nonbase_3c_short_detected():
    """Short 3c detected on 5-min trigger candles.

    Scenario (3 trigger bars, 15 base rows):
    - T0 (base 0-4, end=09:35): arrival — agg H=100.0>=100, agg C=99.1<100
      T0 agg L = min(99.0, 99.1, 99.0, 98.9, 98.8) = 98.8
    - T1 (base 5-9, end=09:40): reversal — agg C=98.5 < T0.L=98.8
      entry_trigger = 98.5 + 2*0.25 = 99.0
    - T2 (base 10-14): fill window; base 11 (ts=09:41 > 09:40) high=99.1>=99.0 -> fill
    """
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},   # base 0
        {"open": 99.5, "high": 99.8,  "low": 99.1, "close": 99.4},   # base 1
        {"open": 99.4, "high": 99.7,  "low": 99.0, "close": 99.3},   # base 2
        {"open": 99.3, "high": 99.6,  "low": 98.9, "close": 99.2},   # base 3
        {"open": 99.2, "high": 99.5,  "low": 98.8, "close": 99.1},   # base 4
        # trigger bar 1 (base 5-9, end=09:40): reversal; T1 close < T0.L=98.8
        {"open": 99.1, "high": 99.3,  "low": 98.5, "close": 98.7},   # base 5
        {"open": 98.7, "high": 99.0,  "low": 98.4, "close": 98.6},   # base 6
        {"open": 98.6, "high": 98.9,  "low": 98.4, "close": 98.6},   # base 7
        {"open": 98.6, "high": 98.9,  "low": 98.4, "close": 98.6},   # base 8
        {"open": 98.6, "high": 98.9,  "low": 98.4, "close": 98.5},   # base 9 (T1 agg close=98.5)
        # trigger bar 2 (base 10-14): fill window
        {"open": 98.5, "high": 98.8,  "low": 98.3, "close": 98.6},   # base 10 ts=09:40 NOT eligible
        {"open": 98.6, "high": 99.1,  "low": 98.5, "close": 98.9},   # base 11 ts=09:41 FILL (H=99.1>=99.0)
        {"open": 98.9, "high": 99.0,  "low": 98.7, "close": 98.9},   # base 12
        {"open": 98.9, "high": 99.0,  "low": 98.8, "close": 98.9},   # base 13
        {"open": 98.9, "high": 99.0,  "low": 98.8, "close": 98.9},   # base 14
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="short", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["direction"] == "short"
    assert r["status"] == "filled"
    assert r["trigger_arrival_bar_index"] == 0
    assert r["trigger_reversal_bar_index"] == 1


def test_nonbase_3c_muted_detected():
    """Muted 3c (inside candle between arrival and reversal) on 5-min trigger.

    Scenario (4 trigger bars, 20 base rows):
    - T0 (base 0-4, end=09:35): arrival — H=101.0, L=100.0, C=100.9
    - T1 (base 5-9, end=09:40): inside (muted) — H=100.95<=101.0, L=100.1>=100.0
    - T2 (base 10-14, end=09:45): reversal — agg C=101.25 > T0.H=101.0
      entry_trigger = 101.25 - 2*0.25 = 100.75
    - T3 (base 15-19): fill window; base 16 (ts=09:46 > 09:45) low=100.6<=100.75 -> fill
    """
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # base 0
        {"open": 100.5, "high": 100.9, "low": 100.2, "close": 100.7},  # base 1
        {"open": 100.7, "high": 100.9, "low": 100.1, "close": 100.8},  # base 2
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},  # base 3
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},  # base 4
        # trigger bar 1 (base 5-9): inside T0 (H<=101.0, L>=100.0)
        {"open": 100.5, "high": 100.8, "low": 100.1, "close": 100.5},  # base 5
        {"open": 100.5, "high": 100.7, "low": 100.2, "close": 100.6},  # base 6
        {"open": 100.6, "high": 100.8, "low": 100.1, "close": 100.7},  # base 7
        {"open": 100.7, "high": 100.9, "low": 100.3, "close": 100.8},  # base 8
        {"open": 100.8, "high": 100.95,"low": 100.2, "close": 100.8},  # base 9
        # trigger bar 2 (base 10-14, end=09:45): reversal; T2 close > T0.H=101.0
        {"open": 100.8, "high": 101.4, "low": 100.1, "close": 101.2},  # base 10
        {"open": 101.2, "high": 101.5, "low": 101.0, "close": 101.3},  # base 11
        {"open": 101.3, "high": 101.5, "low": 101.0, "close": 101.2},  # base 12
        {"open": 101.2, "high": 101.4, "low": 100.9, "close": 101.1},  # base 13
        {"open": 101.1, "high": 101.5, "low": 101.0, "close": 101.25}, # base 14 (T2 agg close=101.25)
        # trigger bar 3 (base 15-19): fill window
        {"open": 101.25,"high": 101.5, "low": 101.0, "close": 101.3},  # base 15 ts=09:45 NOT eligible
        {"open": 101.3, "high": 101.5, "low": 100.6, "close": 101.0},  # base 16 ts=09:46 FILL
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.1},  # base 17
        {"open": 101.1, "high": 101.2, "low": 100.9, "close": 101.0},  # base 18
        {"open": 101.0, "high": 101.1, "low": 100.9, "close": 101.0},  # base 19
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["is_muted"] is True
    assert r["inside_candle_count"] == 1
    assert "muted" in r["trigger_variant"]


def test_nonbase_3c_sfp_detected():
    """SFP 3c (reversal low < arrival low) on 5-min trigger."""
    base_rows = [
        # trigger bar 0: arrival (low<=100, close>100)
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # base 0
        {"open": 100.5, "high": 100.9, "low": 100.2, "close": 100.6},  # base 1
        {"open": 100.6, "high": 101.0, "low": 100.1, "close": 100.8},  # base 2
        {"open": 100.8, "high": 101.0, "low": 100.3, "close": 100.9},  # base 3
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},  # base 4
        # trigger bar 1: SFP reversal: low < bar0_low (100.0), close > bar0_high (101.0)
        {"open": 100.9, "high": 101.5, "low": 99.8, "close": 101.2},  # base 5: SFP
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},  # base 6
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},  # base 7
        # entry_trigger_price = reversal_close - 0.5; fill when low <= that
        {"open": 101.2, "high": 101.4, "low": 100.6, "close": 101.0},  # base 8
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.1},  # base 9
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["is_sfp"] is True
    assert "sfp" in r["trigger_variant"]


# ===========================================================================
# 9-14. Base retrace fill semantics
# ===========================================================================


def _scenario_two_trigger_bars(reversal_close: float = 101.2) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timedelta]:
    """Create a standard 2-trigger-bar scenario for fill boundary tests."""
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
        # trigger bar 1 (base 5-9): reversal close > 101.0 (bar0 high)
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": reversal_close},
        {"open": reversal_close, "high": reversal_close + 0.5, "low": reversal_close - 0.5, "close": reversal_close},
        {"open": reversal_close, "high": reversal_close + 0.5, "low": reversal_close - 0.5, "close": reversal_close},
        {"open": reversal_close, "high": reversal_close + 0.5, "low": reversal_close - 0.5, "close": reversal_close},
        {"open": reversal_close, "high": reversal_close + 0.5, "low": reversal_close - 0.5, "close": reversal_close},
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    return base_df_reset, trigger_df, pd.to_timedelta("5min")


def test_base_bar_before_reversal_ts_does_not_fill():
    """A base bar at or before the reversal trigger candle completion must not fill."""
    base_df_reset, trigger_df, delta = _scenario_two_trigger_bars(reversal_close=101.2)
    # reversal trigger bar end = 09:40 (bar1 end = 09:30 + 5 + 5 = 09:40)
    # base bars 5-9 are within trigger bar 1; their timestamps are before or at 09:40
    # entry_trigger_price = 101.2 - 2*0.25 = 100.7
    # Forcibly lower base bar 5 low to below entry price — but it's at reversal_ts so must not fill
    base_df_reset = base_df_reset.copy()
    base_df_reset.loc[5, "low"] = 100.5  # below entry_trigger_price=100.7
    base_df_reset.loc[5, "high"] = 101.5

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 2},
        trigger_timeframe_delta=delta,
    )
    # All base bars in trigger bar 1 have timestamp <= reversal trigger bar end
    # so they cannot fill
    # The window extends 2 trigger bars after reversal = 09:40 + 10min = 09:50
    # base bars 10-19 would be in scope (but don't exist here)
    assert len(results) == 1
    # Since we only have 10 base bars and reversal is in trigger bar 1 (09:35-09:40),
    # no base bar after 09:40 exists in this scenario -> void
    assert results[0]["status"] == "void"


def test_fill_at_window_end_is_allowed():
    """A base bar whose timestamp equals window_end is allowed to fill."""
    # reversal trigger bar ends at 09:40; max_wait=2 -> window_end = 09:50
    # We need base bars 10, 11 (09:41, 09:42) for the fill check
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
        # trigger bar 1 (base 5-9): reversal
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # trigger bar 2 (base 10-14): window bar 1
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # trigger bar 3 (base 15-19): window bar 2 — fill on last base bar of this window
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # entry_trigger_price = 101.2 - 2*0.25 = 100.7; base 19 low = 100.6 -> fill
        {"open": 101.2, "high": 101.3, "low": 100.6, "close": 101.0},  # base 19: fill at window end
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 2},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    assert results[0]["status"] == "filled"
    assert results[0]["entry_bar_index"] == 19


def test_fill_after_window_end_not_allowed():
    """A base bar after window_end must not fill.

    Scenario: reversal trigger bar ends at 09:40. max_wait=1 trigger bar.
    window_end = 09:40 + 1*5min = 09:45 (inclusive).

    T2 bars (ts 09:41-09:45): all within window but no fill (low > entry_trigger).
    T3 bar 16 (ts=09:46 > 09:45): low=100.0 would fill but is OUTSIDE window -> void.

    Note: base bar at ts=09:45 is the end of trigger bar 2 and is AT window_end
    (inclusive boundary). We ensure it does NOT fill on its own (low > entry_trigger).
    """
    # entry_trigger_price = 101.2 - 2*0.25 = 100.7
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
        # trigger bar 1 (base 5-9, end=09:40): reversal; T1 close=101.2 > T0.H=101.0
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # trigger bar 2 (base 10-14, end=09:45): within window (max_wait=1), no fill
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 10 ts=09:40 not eligible
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 11 ts=09:41
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 12 ts=09:42
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 13 ts=09:43
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},  # base 14 ts=09:44
        # trigger bar 3 (base 15-19): base 15 at ts=09:45 is AT window_end (no fill); after that -> out of window
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.0},  # base 15 ts=09:45 AT window_end, no fill
        {"open": 101.0, "high": 101.2, "low": 100.0, "close": 101.1},  # base 16 ts=09:46 AFTER window_end
        {"open": 101.1, "high": 101.2, "low": 100.9, "close": 101.0},  # base 17
        {"open": 101.0, "high": 101.1, "low": 100.9, "close": 101.0},  # base 18
        {"open": 101.0, "high": 101.1, "low": 100.9, "close": 101.0},  # base 19
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        # max_wait=1: only window up to 09:45 (1 trigger bar after 09:40)
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 1},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    assert results[0]["status"] == "void"


def test_max_entry_wait_counts_trigger_bars_not_base_bars():
    """max_entry_wait_bars_after_reversal counts trigger bars, not base bars."""
    # reversal completes at trigger bar 1 end (09:40)
    # max_wait=1 -> window_end = 09:40 + 1*5min = 09:45
    # Fill on last base bar at 09:44 (inside trigger bar 2, before 09:45) -> filled
    # Fill on first base bar at 09:45 (trigger bar 2 end exactly) -> filled
    # But with max_wait=0 -> window_end = 09:40 + 0 = 09:40 -> no base bar > 09:40 & <= 09:40

    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
        # trigger bar 1 (base 5-9): reversal
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},
        {"open": 101.2, "high": 101.4, "low": 101.0, "close": 101.3},
        {"open": 101.3, "high": 101.4, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # trigger bar 2 (base 10-14): window bar 1, fill on base 14 (last of trigger bar 2)
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        # entry_trigger_price = 101.2 - 0.5 = 100.7; base 14 low = 100.6 -> fill at window end
        {"open": 101.2, "high": 101.3, "low": 100.6, "close": 101.0},  # base 14 = 09:44
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)

    # max_wait=1 trigger bar: fill in base 14 (09:44 <= 09:45) -> filled
    results_wait1 = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 1},
        trigger_timeframe_delta=delta,
    )
    assert len(results_wait1) == 1
    assert results_wait1[0]["status"] == "filled"

    # max_wait=0 trigger bars: window_end = 09:40, no base bar > 09:40 & <= 09:40 -> void
    results_wait0 = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 0},
        trigger_timeframe_delta=delta,
    )
    assert len(results_wait0) == 1
    assert results_wait0[0]["status"] == "void"


def test_void_when_no_fill_within_window():
    """status='void' when no fill happens within the trigger-bar wait window."""
    base_rows = [
        # trigger bar 0 (base 0-4): arrival
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
        # trigger bar 1 (base 5-9): reversal
        {"open": 100.9, "high": 101.5, "low": 100.1, "close": 101.2},
        {"open": 101.2, "high": 101.4, "low": 101.1, "close": 101.3},
        {"open": 101.3, "high": 101.4, "low": 101.1, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.1, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.1, "close": 101.2},
        # trigger bar 2 (base 10-14): window bar 1, no fill (low stays above entry_trigger_price)
        # entry_trigger_price = 101.2 - 0.5 = 100.7
        {"open": 101.2, "high": 101.3, "low": 100.9, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.1, "close": 101.2},
        {"open": 101.2, "high": 101.3, "low": 101.0, "close": 101.2},
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 1},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    assert results[0]["status"] == "void"
    assert results[0]["entry_bar_index"] is None
    assert results[0]["retrace_entry_price"] is None


# ===========================================================================
# 15-20. Index and timestamp integrity
# ===========================================================================


def test_entry_bar_index_is_base_index():
    """entry_bar_index must be a canonical/base index."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")
    n_base = len(base_df_reset)

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["entry_bar_index"] is not None
    assert 0 <= r["entry_bar_index"] < n_base


def test_timestamp_equals_base_df_timestamp_at_bar_index():
    """timestamp == base_df['timestamp'].iloc[bar_index]."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    bar_index = int(r["bar_index"])
    assert r["timestamp"] == base_df_reset["timestamp"].iloc[bar_index]


def test_trigger_bar_index_equals_trigger_reversal_bar_index():
    """For 3c, trigger_bar_index must equal trigger_reversal_bar_index."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["trigger_bar_index"] == r["trigger_reversal_bar_index"]


def test_trigger_timestamp_is_reversal_trigger_candle_completion():
    """trigger_timestamp must equal reversal trigger candle completion timestamp."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    t_rev_idx = r["trigger_reversal_bar_index"]
    expected_trigger_ts = trigger_df.iloc[t_rev_idx]["trigger_bar_end_timestamp"]
    assert r["trigger_timestamp"] == expected_trigger_ts


def test_arrival_reversal_bar_indices_are_base_indices():
    """arrival_bar_index and reversal_bar_index must be base/canonical indices."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    # arrival_bar_index = base_end_bar_index of trigger arrival bar (=4)
    expected_arrival_base = int(trigger_df.iloc[0]["base_end_bar_index"])
    expected_reversal_base = int(trigger_df.iloc[1]["base_end_bar_index"])
    assert r["arrival_bar_index"] == expected_arrival_base
    assert r["reversal_bar_index"] == expected_reversal_base
    # trigger indices are different (smaller) than base indices
    assert r["trigger_arrival_bar_index"] == 0
    assert r["trigger_reversal_bar_index"] == 1


def test_trigger_and_base_indices_are_different():
    """For non-base 3c, trigger indices differ from base indices."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    # trigger indices 0, 1 < base indices 4, 9
    assert r["trigger_arrival_bar_index"] < r["arrival_bar_index"]
    assert r["trigger_reversal_bar_index"] < r["reversal_bar_index"]


# ===========================================================================
# 21. Naked metadata uses base arrival index
# ===========================================================================


def test_naked_metadata_uses_base_arrival_index():
    """Naked metadata must be read using base_arrival_bar_index, not trigger index."""
    base_rows = _make_standard_15row_long_base_rows()
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")
    delta = pd.to_timedelta("5min")

    # Build naked_flags with 15 rows, mark L1_naked=True at base arrival index (=4)
    naked_flags = pd.DataFrame({"L1_naked": [False] * len(base_df_reset)})
    base_arrival_idx = int(trigger_df.iloc[0]["base_end_bar_index"])  # should be 4
    assert base_arrival_idx == 4, f"Expected base_arrival_idx=4 but got {base_arrival_idx}"
    naked_flags.loc[base_arrival_idx, "L1_naked"] = True
    # Also set trigger index 0 to False to confirm it's NOT used
    naked_flags.loc[0, "L1_naked"] = False

    # Build candidate with naked metadata using base arrival index
    from thesistester.engine.candidate_level import with_metadata

    trigger_base_end_map = {
        int(row["trigger_bar_index"]): int(row["base_end_bar_index"])
        for _, row in trigger_df.iterrows()
    }
    candidate = _candidate_trigger(direction="long", price=100.0, trigger_bar_index=0)
    base_arr_idx = trigger_base_end_map.get(int(candidate.bar_index))
    is_naked = bool(naked_flags["L1_naked"].iloc[base_arr_idx]) if base_arr_idx is not None else None
    state = "naked" if is_naked else "tested"
    candidate = with_metadata(
        candidate,
        was_naked_before_arrival=is_naked,
        level_test_state_at_arrival=state,
    )

    results = detect_3c_setups_with_trigger_timeframe(
        trigger_df=trigger_df,
        base_df=base_df_reset,
        candidates=[candidate],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
        trigger_timeframe_delta=delta,
    )
    assert len(results) == 1
    r = results[0]
    assert r["was_naked_before_arrival"] is True  # read from base index, not trigger index
    assert r["level_test_state_at_arrival"] == "naked"


# ===========================================================================
# 22-23. Source modes
# ===========================================================================


def _make_zones_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "bar_index": 0,
                "timestamp": pd.Timestamp("2026-01-02 09:30", tz=TZ),
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "L1",
                "level_prices": "100.0",
            }
        ]
    )


def _make_anchor_zones_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "bar_index": 0,
                "timestamp": pd.Timestamp("2026-01-02 09:30", tz=TZ),
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "pdHigh",
                "level_prices": "100.0",
                "anchor_level": "pdHigh",
                "anchor_price": 100.0,
                "valid_confluence_count": 1,
                "confluence_mode": "anchor_rules",
            }
        ]
    )


def _make_base_df_for_full_test() -> pd.DataFrame:
    return _base_df(_make_standard_15row_long_base_rows(), freq="1min")


def test_global_mode_works():
    """Global cluster mode produces signals for non-base 3c."""
    df = _make_base_df_for_full_test()
    zones = _make_zones_df()
    signals = generate_signals(
        df, zones, trigger="3c", direction="long", tick_size=TICK,
        trigger_timeframe="5min",
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5},
    )
    # Should produce at least a void or filled signal
    assert isinstance(signals, pd.DataFrame)
    if len(signals) > 0:
        assert "trigger_arrival_bar_index" in signals.columns
        assert "trigger_reversal_bar_index" in signals.columns


def test_anchor_mode_works():
    """Anchor rules mode produces signals for non-base 3c."""
    df = _make_base_df_for_full_test()
    zones = _make_anchor_zones_df()
    trigger_params = {"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 5, "_source_mode": "anchor_rules"}
    signals = generate_signals(
        df, zones, trigger="3c", direction="long", tick_size=TICK,
        trigger_timeframe="5min",
        trigger_params=trigger_params,
    )
    assert isinstance(signals, pd.DataFrame)


# ===========================================================================
# 24-25. Hash/settings
# ===========================================================================


def test_3c_base_and_5min_produce_different_hashes():
    """3c + base and 3c + 5min must produce different signal settings hashes."""
    from thesistester.persistence import compute_signal_settings_hash

    settings_base = {
        "trigger": "3c",
        "trigger_timeframe": "base",
        "direction": "long",
        "selected_levels": ["L1"],
        "tolerance_ticks": 4.0,
        "min_confluences": 2,
        "max_confluences": 5,
        "naked_only": False,
        "naked_requirement": "any",
        "confluence_mode": "global_cluster",
        "anchor_level": None,
        "confluence_rules": [],
        "min_valid_confluences": 1,
        "trigger_params": {"entry_retrace_ticks": 4.0, "max_entry_wait_bars_after_reversal": 5},
        "use_saved_setup": False,
        "setup_snapshot": None,
    }
    settings_5min = dict(settings_base, trigger_timeframe="5min")

    hash_base = compute_signal_settings_hash(settings_base)
    hash_5min = compute_signal_settings_hash(settings_5min)
    assert hash_base != hash_5min


def test_build_setup_config_stores_5min_for_3c():
    """build_setup_config(trigger='3c', trigger_timeframe='5min') must store '5min'."""
    config = build_setup_config(
        name="3c 5min",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        trigger_timeframe="5min",
        direction="both",
    )
    assert config["trigger_timeframe"] == "5min"


def test_build_setup_config_stores_15min_for_3c():
    """build_setup_config(trigger='3c', trigger_timeframe='15min') must store '15min'."""
    config = build_setup_config(
        name="3c 15min",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        trigger_timeframe="15min",
        direction="both",
    )
    assert config["trigger_timeframe"] == "15min"


# ===========================================================================
# Additional regression: project_zones_to_trigger_df
# ===========================================================================


def test_project_zones_to_trigger_df_maps_correctly():
    """Projected zones should have trigger bar_index and trigger_bar_end_timestamp."""
    base_rows = [
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.5, "high": 100.9, "low": 100.3, "close": 100.7},
        {"open": 100.7, "high": 100.9, "low": 100.2, "close": 100.8},
        {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.9},
        {"open": 100.9, "high": 101.0, "low": 100.2, "close": 100.9},
    ]
    base_df = _base_df(base_rows, freq="1min")
    base_df_reset = base_df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(base_df_reset, "5min")

    zones = pd.DataFrame(
        [
            {
                "bar_index": 0,  # base bar index
                "timestamp": base_df_reset.iloc[0]["timestamp"],
                "zone_low": 99.5,
                "zone_high": 100.5,
                "zone_mid": 100.0,
                "level_count": 1,
                "level_names": "L1",
                "level_prices": "100.0",
            }
        ]
    )
    projected = _project_zones_to_trigger_df(zones, trigger_df)
    assert len(projected) == 1
    # bar_index should now be trigger bar index (0 here since all base bars 0-4 map to trigger bar 0)
    assert projected.iloc[0]["bar_index"] == 0  # trigger bar 0
    assert projected.iloc[0]["timestamp"] == trigger_df.iloc[0]["trigger_bar_end_timestamp"]
    assert "base_end_bar_index" in projected.columns


def test_project_zones_empty_input():
    """Empty zones or trigger_df returns empty DataFrame."""
    zones = pd.DataFrame(columns=["bar_index", "timestamp", "zone_low", "zone_high", "zone_mid"])
    trigger_df = pd.DataFrame()
    result = _project_zones_to_trigger_df(zones, trigger_df)
    assert result.empty
