"""Phase 4 engine tests: confluence detection, naked levels, signal generation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from thesistester.engine.confluence import detect_confluence_zones
from thesistester.engine.naked import flag_naked_levels
from thesistester.engine.signals import generate_signals


TZ = "America/New_York"
TICK = 0.25  # ES/NQ tick size
ZONE_COLUMNS = [
    "timestamp",
    "bar_index",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "level_prices",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bar(ts, o, h, l, c, vol=100.0) -> dict:
    return {"timestamp": pd.Timestamp(ts, tz=TZ), "open": o, "high": h, "low": l, "close": c, "volume": vol}


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _df_with_level(level_prices: list[float | None], bar_highs: list[float], bar_lows: list[float]) -> pd.DataFrame:
    """Build a minimal OHLCV + one level column for naked tests."""
    n = len(level_prices)
    ts = pd.date_range("2026-06-02 09:30", periods=n, freq="1min", tz=TZ)
    levels = [p if p is not None else np.nan for p in level_prices]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": bar_highs,
            "high": bar_highs,
            "low": bar_lows,
            "close": bar_highs,
            "volume": [100.0] * n,
            "level_A": levels,
        }
    )


def _zone_df(bar_idx: int, low: float, high: float, level_names: str = "A|B") -> pd.DataFrame:
    """Minimal zone row for signal tests."""
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(f"2026-06-02 09:3{bar_idx}:00", tz=TZ),
                "bar_index": bar_idx,
                "zone_low": low,
                "zone_high": high,
                "zone_mid": (low + high) / 2.0,
                "level_count": 2,
                "level_names": level_names,
                "level_prices": f"{low}|{high}",
            }
        ]
    )


def _simple_bars(n: int = 10, base: float = 100.0) -> pd.DataFrame:
    """Flat-trend OHLCV bars for trigger tests."""
    ts = pd.date_range("2026-06-02 09:30", periods=n, freq="1min", tz=TZ)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": [base] * n,
            "high": [base + 1.0] * n,
            "low": [base - 1.0] * n,
            "close": [base] * n,
            "volume": [100.0] * n,
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# Confluence tests
# ──────────────────────────────────────────────────────────────────────────────


class TestConfluenceDetection:
    def _df_levels(self, **kwargs) -> pd.DataFrame:
        """Single-bar DataFrame with arbitrary level columns."""
        row = {
            "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100.0,
            **kwargs,
        }
        return pd.DataFrame([row])

    def test_empty_level_list_returns_empty(self):
        df = self._df_levels(levelA=100.0, levelB=100.25)
        result = detect_confluence_zones(df, level_columns=[], tick_size=TICK, tolerance_ticks=4)
        assert result.empty
        assert list(result.columns) == ZONE_COLUMNS

    def test_missing_selected_columns_returns_empty_with_schema(self):
        df = self._df_levels(levelA=100.0, levelB=100.25)
        result = detect_confluence_zones(
            df,
            level_columns=["missingA", "missingB"],
            tick_size=TICK,
            tolerance_ticks=4,
        )
        assert result.empty
        assert list(result.columns) == ZONE_COLUMNS

    def test_two_levels_within_tolerance_form_zone(self):
        # 100.0 and 100.25 — one tick apart
        df = self._df_levels(levelA=100.0, levelB=100.25)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB"], tick_size=TICK, tolerance_ticks=2
        )
        assert len(result) == 1
        assert result.iloc[0]["zone_low"] == 100.0
        assert result.iloc[0]["zone_high"] == 100.25
        assert result.iloc[0]["level_count"] == 2

    def test_levels_outside_tolerance_form_no_zone(self):
        # 100.0 and 101.0 — 4 ticks apart; tolerance is 2 ticks
        df = self._df_levels(levelA=100.0, levelB=101.0)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB"], tick_size=TICK, tolerance_ticks=2
        )
        assert result.empty

    def test_min_confluences_filters_small_groups(self):
        # Two levels within tolerance but min_confluences=3 → no zone
        df = self._df_levels(levelA=100.0, levelB=100.25)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB"], tick_size=TICK,
            tolerance_ticks=4, min_confluences=3
        )
        assert result.empty

    def test_min_confluences_satisfied_emits_zone(self):
        df = self._df_levels(levelA=100.0, levelB=100.25, levelC=100.50)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB", "levelC"],
            tick_size=TICK, tolerance_ticks=4, min_confluences=3,
        )
        assert len(result) == 1
        assert result.iloc[0]["level_count"] == 3

    def test_levels_within_tolerance_emit_sorted_zone_metadata(self):
        df = self._df_levels(L1=4500.00, L2=4500.50, L3=4501.00)
        result = detect_confluence_zones(
            df,
            level_columns=["L1", "L2", "L3"],
            tick_size=TICK,
            tolerance_ticks=4,
            min_confluences=2,
            max_confluences=5,
        )
        assert len(result) == 1
        row = result.iloc[0]
        assert row["zone_low"] == pytest.approx(4500.00)
        assert row["zone_high"] == pytest.approx(4501.00)
        assert row["zone_mid"] == pytest.approx(4500.50)
        assert row["level_count"] == 3
        assert row["level_names"] == "L1|L2|L3"
        assert row["level_prices"] == "4500.0|4500.5|4501.0"

    def test_nan_levels_are_ignored(self):
        # levelB is NaN — only levelA and levelC are valid, but they're far apart
        df = self._df_levels(levelA=100.0, levelB=np.nan, levelC=102.0)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB", "levelC"],
            tick_size=TICK, tolerance_ticks=2, min_confluences=2,
        )
        assert result.empty

    def test_nan_ignored_two_valid_close_levels(self):
        df = self._df_levels(levelA=100.0, levelB=np.nan, levelC=100.25)
        result = detect_confluence_zones(
            df, level_columns=["levelA", "levelB", "levelC"],
            tick_size=TICK, tolerance_ticks=2, min_confluences=2,
        )
        assert len(result) == 1
        assert result.iloc[0]["level_count"] == 2

    def test_duplicate_prices_count_as_independent_levels(self):
        df = self._df_levels(L1=4500.00, L2=4500.00)
        result = detect_confluence_zones(
            df,
            level_columns=["L1", "L2"],
            tick_size=TICK,
            tolerance_ticks=0,
            min_confluences=2,
            max_confluences=5,
        )
        assert len(result) == 1
        row = result.iloc[0]
        assert row["level_count"] == 2
        assert row["level_names"] == "L1|L2"
        assert row["level_prices"] == "4500.0|4500.0"

    def test_max_confluences_caps_at_5(self):
        # 6 levels all at same price
        kwargs = {f"level{i}": 100.0 for i in range(6)}
        df = self._df_levels(**kwargs)
        level_cols = list(kwargs.keys())
        result = detect_confluence_zones(
            df, level_columns=level_cols, tick_size=TICK,
            tolerance_ticks=0, min_confluences=2, max_confluences=5,
        )
        assert not result.empty
        assert result.iloc[0]["level_count"] <= 5

    def test_max_confluences_truncates_to_first_five_sorted_levels(self):
        df = self._df_levels(
            L1=4500.00,
            L2=4500.25,
            L3=4500.50,
            L4=4500.75,
            L5=4501.00,
            L6=4501.25,
        )
        result = detect_confluence_zones(
            df,
            level_columns=["L1", "L2", "L3", "L4", "L5", "L6"],
            tick_size=TICK,
            tolerance_ticks=10,
            min_confluences=2,
            max_confluences=5,
        )
        assert len(result) == 1
        row = result.iloc[0]
        assert row["level_count"] == 5
        assert row["level_names"] == "L1|L2|L3|L4|L5"
        assert row["level_prices"] == "4500.0|4500.25|4500.5|4500.75|4501.0"
        assert "L6" not in row["level_names"]

    def test_max_confluences_is_hard_capped_at_five_even_when_larger_requested(self):
        kwargs = {f"level{i}": 100.0 + (i * TICK) for i in range(6)}
        df = self._df_levels(**kwargs)
        result = detect_confluence_zones(
            df,
            level_columns=list(kwargs.keys()),
            tick_size=TICK,
            tolerance_ticks=10,
            min_confluences=2,
            max_confluences=10,
        )
        assert len(result) == 1
        assert result.iloc[0]["level_count"] == 5

    def test_non_overlapping_clusters_emitted_separately(self):
        # Levels at 100.0 and 100.25 form one cluster, 102.0 and 102.25 form another
        df = self._df_levels(lA=100.0, lB=100.25, lC=102.0, lD=102.25)
        result = detect_confluence_zones(
            df, level_columns=["lA", "lB", "lC", "lD"],
            tick_size=TICK, tolerance_ticks=2, min_confluences=2,
        )
        assert len(result) == 2

    def test_greedy_overlapping_cluster_emits_first_window_only(self):
        df = self._df_levels(L1=100.00, L2=100.50, L3=101.00, L4=101.50)
        result = detect_confluence_zones(
            df,
            level_columns=["L1", "L2", "L3", "L4"],
            tick_size=TICK,
            tolerance_ticks=4,
            min_confluences=2,
            max_confluences=5,
        )
        assert len(result) == 1
        assert result.iloc[0]["level_names"] == "L1|L2|L3"

    def test_bar_index_aligned_to_row_position(self):
        rows = [
            {"timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100.0, "lA": np.nan, "lB": np.nan},
            {"timestamp": pd.Timestamp("2026-06-02 09:31:00", tz=TZ), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100.0, "lA": 100.0, "lB": 100.25},
        ]
        df = pd.DataFrame(rows)
        result = detect_confluence_zones(
            df, level_columns=["lA", "lB"], tick_size=TICK, tolerance_ticks=2
        )
        assert len(result) == 1
        assert result.iloc[0]["bar_index"] == 1

    def test_multiple_bars_are_processed_independently(self):
        timestamps = pd.to_datetime(
            ["2024-01-01 09:30", "2024-01-01 09:31", "2024-01-01 09:32"]
        ).tz_localize(TZ)
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0, 100.0, 100.0],
                "high": [101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 99.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [100.0, 100.0, 100.0],
                "L1": [4500.00, 4500.00, 4501.00],
                "L2": [4500.50, 4501.25, np.nan],
                "L3": [np.nan, np.nan, 4501.25],
            }
        )
        result = detect_confluence_zones(
            df,
            level_columns=["L1", "L2", "L3"],
            tick_size=TICK,
            tolerance_ticks=4,
            min_confluences=2,
            max_confluences=5,
        )
        assert list(result["bar_index"]) == [0, 2]
        assert list(result["timestamp"]) == [timestamps[0], timestamps[2]]


# ──────────────────────────────────────────────────────────────────────────────
# Naked-level tests
# ──────────────────────────────────────────────────────────────────────────────


class TestNakedLevels:
    def test_level_naked_when_first_appears(self):
        df = _df_with_level([100.0], bar_highs=[101.0], bar_lows=[99.0])
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        assert result["level_A_naked"].iloc[0]

    def test_level_remains_naked_until_touched(self):
        # 4 bars: level at 100 on bar0, bars 1-2 trade above (99-101 is just outside the
        # actual level by nothing), bar 3 still hasn't touched
        # Make bars stay away: lows > 100, highs < 100 → can't touch
        # Actually level=100, bar range must include 100 for a touch
        # Use bars with low=101 (above the level) so they never touch 100
        df = _df_with_level(
            [100.0, 100.0, 100.0, 100.0],
            bar_highs=[99.5, 99.5, 99.5, 99.5],
            bar_lows=[99.0, 99.0, 99.0, 99.0],
        )
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        # Bar 0: formation — naked
        assert result["level_A_naked"].iloc[0] == True  # noqa: E712
        # Bars 1-3: range is [99.0, 99.5], doesn't include 100 → still naked
        assert result["level_A_naked"].iloc[1] == True  # noqa: E712
        assert result["level_A_naked"].iloc[3] == True  # noqa: E712

    def test_level_not_naked_after_touch(self):
        # Bar 0: level=100, range [99, 101] → formation (naked)
        # Bar 1: level=100, range [99, 101] → touches level → not naked
        df = _df_with_level(
            [100.0, 100.0],
            bar_highs=[101.0, 101.0],
            bar_lows=[99.0, 99.0],
        )
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        assert result["level_A_naked"].iloc[0] == True   # noqa: E712  # formation bar → naked
        assert result["level_A_naked"].iloc[1] == False  # noqa: E712  # touched at bar 1

    def test_formation_bar_not_immediately_tested(self):
        # Bar 0 is the formation bar and the bar range includes the level —
        # BUT the formation bar should NOT be marked tested (naked stays True on bar 0)
        df = _df_with_level(
            [100.0],
            bar_highs=[101.0],
            bar_lows=[99.0],
        )
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        # Even though bar 0 range covers 100.0, formation bars are never marked tested
        assert result["level_A_naked"].iloc[0] == True  # noqa: E712

    def test_nan_level_resets_naked_state(self):
        # Bar 0: level=100 → naked
        # Bar 1: level=NaN → resets
        # Bar 2: level=100 again → new formation → naked
        df = _df_with_level(
            [100.0, None, 100.0],
            bar_highs=[101.0, 101.0, 101.0],
            bar_lows=[99.0, 99.0, 99.0],
        )
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        assert result["level_A_naked"].iloc[0] == True   # noqa: E712
        assert result["level_A_naked"].iloc[1] == False  # noqa: E712  # NaN → not naked
        assert result["level_A_naked"].iloc[2] == True   # noqa: E712  # re-formed

    def test_level_change_triggers_new_formation(self):
        # Bar 0: level=100 → naked
        # Bar 1: level=101 (changed) → new formation → naked
        # Bar 2: level=101 (same) + bar touches it → not naked
        df = _df_with_level(
            [100.0, 101.0, 101.0],
            bar_highs=[99.5, 99.5, 102.0],
            bar_lows=[99.0, 99.0, 100.5],
        )
        result = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK)
        assert result["level_A_naked"].iloc[0] == True   # noqa: E712
        assert result["level_A_naked"].iloc[1] == True   # noqa: E712  # new formation
        assert result["level_A_naked"].iloc[2] == False  # noqa: E712  # touched at bar 2

    def test_touch_tolerance_extends_test_range(self):
        # Level=100.0, bar has high=100.10, low=99.90 — doesn't reach 100.0 exactly
        # With tolerance=1 tick (0.25), touch zone is [99.75, 100.25] → covered
        df = _df_with_level(
            [100.0, 100.0],
            bar_highs=[100.1, 100.1],
            bar_lows=[99.9, 99.9],
        )
        result_no_tol = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK, touch_tolerance_ticks=0)
        result_with_tol = flag_naked_levels(df, level_columns=["level_A"], tick_size=TICK, touch_tolerance_ticks=1)
        # Without tolerance: bar1 range [99.9, 100.1] includes 100.0 exactly → touched
        assert result_no_tol["level_A_naked"].iloc[1] == False  # noqa: E712
        # With tolerance: definitely touched
        assert result_with_tol["level_A_naked"].iloc[1] == False  # noqa: E712


# ──────────────────────────────────────────────────────────────────────────────
# Signal generation tests
# ──────────────────────────────────────────────────────────────────────────────


def _df_bars(rows: list[dict]) -> pd.DataFrame:
    ts = pd.date_range("2026-06-02 09:30", periods=len(rows), freq="1min", tz=TZ)
    for i, r in enumerate(rows):
        r["timestamp"] = ts[i]
        r.setdefault("volume", 100.0)
    return pd.DataFrame(rows)


class TestTouchSignal:
    def test_touch_fires_when_bar_intersects_zone(self):
        # Zone: [100.0, 100.5]; bar range [99.8, 100.3] — intersects
        df = _df_bars([{"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.1}])
        zones = _zone_df(0, low=100.0, high=100.5)
        sigs = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert len(sigs) == 1
        assert sigs.iloc[0]["trigger"] == "touch"
        assert sigs.iloc[0]["direction"] == "long"
        assert sigs.iloc[0]["status"] == "candidate"

    def test_touch_does_not_fire_when_bar_misses_zone(self):
        # Zone: [100.5, 101.0]; bar range [99.0, 100.2] — below zone
        df = _df_bars([{"open": 99.5, "high": 100.2, "low": 99.0, "close": 99.5}])
        zones = _zone_df(0, low=100.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert sigs.empty

    def test_touch_direction_both_emits_two_signals(self):
        df = _df_bars([{"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}])
        zones = _zone_df(0, low=100.0, high=100.25)
        sigs = generate_signals(df, zones, trigger="touch", direction="both", tick_size=TICK)
        assert len(sigs) == 2
        assert set(sigs["direction"].tolist()) == {"long", "short"}


class TestRejectSignal:
    def test_reject_long_fires_when_touch_and_close_above_zone(self):
        # Zone: [100.0, 100.5]; bar touches (low=99.9) and closes above (close=100.6)
        df = _df_bars([{"open": 100.0, "high": 100.8, "low": 99.9, "close": 100.6}])
        zones = _zone_df(0, low=100.0, high=100.5)
        sigs = generate_signals(df, zones, trigger="reject", direction="long", tick_size=TICK)
        assert len(sigs) == 1
        assert sigs.iloc[0]["direction"] == "long"

    def test_reject_long_does_not_fire_when_close_inside_zone(self):
        # Close inside zone: no reject
        df = _df_bars([{"open": 100.0, "high": 100.4, "low": 99.9, "close": 100.2}])
        zones = _zone_df(0, low=100.0, high=100.5)
        sigs = generate_signals(df, zones, trigger="reject", direction="long", tick_size=TICK)
        assert sigs.empty

    def test_reject_short_fires_when_touch_and_close_below_zone(self):
        # Zone: [100.0, 100.5]; bar touches (high=100.6) and closes below (close=99.8)
        df = _df_bars([{"open": 100.2, "high": 100.6, "low": 99.7, "close": 99.8}])
        zones = _zone_df(0, low=100.0, high=100.5)
        sigs = generate_signals(df, zones, trigger="reject", direction="short", tick_size=TICK)
        assert len(sigs) == 1
        assert sigs.iloc[0]["direction"] == "short"

    def test_reject_short_does_not_fire_when_close_inside_zone(self):
        df = _df_bars([{"open": 100.2, "high": 100.6, "low": 99.7, "close": 100.1}])
        zones = _zone_df(0, low=100.0, high=100.5)
        sigs = generate_signals(df, zones, trigger="reject", direction="short", tick_size=TICK)
        assert sigs.empty


class TestBreakSignal:
    def test_break_long_uses_previous_close(self):
        # Bar 0 close = 100.0 (at zone_high = 100.0)
        # Bar 1 close = 100.5 (above zone_high) → long break
        # Zone at bar 1
        df = _df_bars([
            {"open": 99.5, "high": 100.5, "low": 99.0, "close": 100.0},
            {"open": 100.1, "high": 100.8, "low": 100.0, "close": 100.5},
        ])
        zones = _zone_df(1, low=99.75, high=100.0)
        sigs = generate_signals(df, zones, trigger="break", direction="long", tick_size=TICK)
        assert len(sigs) == 1
        assert sigs.iloc[0]["direction"] == "long"

    def test_break_long_does_not_fire_if_prev_close_already_above_zone(self):
        # Previous close = 101.0, already above zone_high=100.0 → no break
        df = _df_bars([
            {"open": 101.0, "high": 101.5, "low": 100.5, "close": 101.0},
            {"open": 101.0, "high": 101.5, "low": 100.8, "close": 101.2},
        ])
        zones = _zone_df(1, low=99.75, high=100.0)
        sigs = generate_signals(df, zones, trigger="break", direction="long", tick_size=TICK)
        assert sigs.empty

    def test_break_short_uses_previous_close(self):
        # Bar 0 close = 100.5 (at zone_low = 100.5)
        # Bar 1 close = 99.8 (below zone_low) → short break
        df = _df_bars([
            {"open": 100.5, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.3, "high": 100.5, "low": 99.5, "close": 99.8},
        ])
        zones = _zone_df(1, low=100.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="break", direction="short", tick_size=TICK)
        assert len(sigs) == 1
        assert sigs.iloc[0]["direction"] == "short"

    def test_break_no_signal_on_first_bar(self):
        # No previous bar available at bar_index=0
        df = _df_bars([{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}])
        zones = _zone_df(0, low=99.75, high=100.0)
        sigs = generate_signals(df, zones, trigger="break", direction="long", tick_size=TICK)
        assert sigs.empty


class TestReclaimSignal:
    def test_reclaim_long_bar_low_below_zone_low_close_above_zone_high(self):
        # Long reclaim: bar_low < zone_low AND close > zone_high
        df = _df_bars([{"open": 100.0, "high": 101.5, "low": 99.4, "close": 101.2}])
        zones = _zone_df(0, low=99.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="reclaim", direction="long", tick_size=TICK)
        assert len(sigs) == 1

    def test_reclaim_long_does_not_fire_without_both_conditions(self):
        # bar_low above zone_low → condition not met
        df = _df_bars([{"open": 100.0, "high": 101.5, "low": 99.6, "close": 101.2}])
        zones = _zone_df(0, low=99.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="reclaim", direction="long", tick_size=TICK)
        assert sigs.empty

    def test_reclaim_short_bar_high_above_zone_high_close_below_zone_low(self):
        df = _df_bars([{"open": 100.0, "high": 101.5, "low": 98.5, "close": 98.9}])
        zones = _zone_df(0, low=99.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="reclaim", direction="short", tick_size=TICK)
        assert len(sigs) == 1

    def test_reclaim_short_does_not_fire_without_both_conditions(self):
        # close above zone_low → no reclaim
        df = _df_bars([{"open": 100.0, "high": 101.5, "low": 98.5, "close": 99.6}])
        zones = _zone_df(0, low=99.5, high=101.0)
        sigs = generate_signals(df, zones, trigger="reclaim", direction="short", tick_size=TICK)
        assert sigs.empty


class TestConfirm3Bar:
    def _three_bar_df(self, b1, b2, b3) -> pd.DataFrame:
        return _df_bars([b1, b2, b3])

    def _zone_with_levels(self, *, prices: list[float], names: list[str] | None = None, bar_idx: int = 0) -> pd.DataFrame:
        level_names = names or [f"L{i + 1}" for i in range(len(prices))]
        return pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp(f"2026-06-02 09:3{bar_idx}:00", tz=TZ),
                    "bar_index": bar_idx,
                    "zone_low": min(prices),
                    "zone_high": max(prices),
                    "zone_mid": (min(prices) + max(prices)) / 2.0,
                    "level_count": len(prices),
                    "level_names": "|".join(level_names),
                    "level_prices": "|".join(str(price) for price in prices),
                }
            ]
        )

    def test_long_arrival_hits_actual_level_and_selects_highest_touched(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 100.00, "close": 100.50}
        b2 = {"open": 100.60, "high": 101.00, "low": 100.20, "close": 100.80}
        b3 = {"open": 101.00, "high": 101.40, "low": 99.90, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00, 100.25], names=["level_A", "level_B"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"arrival_tolerance_ticks": 0, "activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert len(sigs) == 1
        sig = sigs.iloc[0]
        assert sig["tested_level_price"] == pytest.approx(100.25)
        assert sig["tested_level_name"] == "level_B"

    def test_long_arrival_cannot_front_run_level_without_tolerance(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 100.10, "close": 100.50}
        b2 = {"open": 100.60, "high": 101.00, "low": 100.20, "close": 100.80}
        b3 = {"open": 101.00, "high": 101.40, "low": 99.90, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"arrival_tolerance_ticks": 0, "activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert sigs.empty

    def test_long_arrival_fails_when_close_is_below_tested_level(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 99.75, "close": 99.90}
        b2 = {"open": 100.00, "high": 100.20, "low": 99.80, "close": 100.10}
        b3 = {"open": 100.20, "high": 100.40, "low": 99.70, "close": 100.00}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"arrival_tolerance_ticks": 0, "activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert sigs.empty

    def test_short_arrival_hits_actual_level_and_selects_lowest_touched(self):
        b1 = {"open": 99.00, "high": 100.30, "low": 98.80, "close": 99.80}
        b2 = {"open": 99.90, "high": 100.00, "low": 99.00, "close": 99.40}
        b3 = {"open": 99.00, "high": 100.20, "low": 98.70, "close": 98.90}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00, 100.25], names=["level_A", "level_B"]),
            trigger="confirm_3bar",
            direction="short",
            tick_size=TICK,
            trigger_params={"arrival_tolerance_ticks": 0, "activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert len(sigs) == 1
        sig = sigs.iloc[0]
        assert sig["tested_level_price"] == pytest.approx(100.00)
        assert sig["tested_level_name"] == "level_A"

    def test_short_arrival_fails_when_close_is_above_tested_level(self):
        b1 = {"open": 99.00, "high": 100.40, "low": 98.80, "close": 100.10}
        b2 = {"open": 100.00, "high": 100.20, "low": 99.40, "close": 99.60}
        b3 = {"open": 99.20, "high": 100.10, "low": 98.70, "close": 99.00}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="short",
            tick_size=TICK,
            trigger_params={"arrival_tolerance_ticks": 0, "activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert sigs.empty

    def test_long_standard_reversal_marking(self):
        b1 = {"open": 101.00, "high": 101.10, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.40, "high": 100.90, "low": 99.90, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.30, "low": 99.90, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert len(sigs) == 1
        assert sigs.iloc[0]["reversal_type"] == "standard_reversal"
        assert sigs.iloc[0]["is_sfp_reversal"] == False  # noqa: E712

    def test_long_sfp_reversal_marking(self):
        b1 = {"open": 101.00, "high": 101.10, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.20, "high": 100.90, "low": 99.70, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.30, "low": 99.90, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert len(sigs) == 1
        assert sigs.iloc[0]["reversal_type"] == "sfp_reversal"
        assert sigs.iloc[0]["is_sfp_reversal"] == True  # noqa: E712

    def test_short_sfp_reversal_marking(self):
        b1 = {"open": 99.00, "high": 100.10, "low": 98.80, "close": 99.80}
        b2 = {"open": 99.90, "high": 100.30, "low": 99.10, "close": 99.30}
        b3 = {"open": 99.00, "high": 100.20, "low": 98.70, "close": 98.90}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="short",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert len(sigs) == 1
        assert sigs.iloc[0]["reversal_type"] == "sfp_reversal"
        assert sigs.iloc[0]["is_sfp_reversal"] == True  # noqa: E712

    def test_long_bar3_activation_and_entry_filled(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.40, "high": 100.90, "low": 99.90, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.30, "low": 100.00, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        sig = sigs.iloc[0]
        assert sig["activation_price"] == pytest.approx(100.00)
        assert sig["entry_price"] == pytest.approx(101.25)
        assert sig["status"] == "filled"
        assert sig["entry_reference_price"] == pytest.approx(101.25)
        assert sig["entry_model"] == "bar3_stop_limit_fill"

    def test_long_bar3_activation_hit_but_entry_not_hit_is_void(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.40, "high": 100.90, "low": 99.90, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.20, "low": 100.00, "close": 100.80}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        sig = sigs.iloc[0]
        assert sig["status"] == "void"
        assert sig["entry_model"] == "bar3_stop_limit_void"
        assert sig["entry_reference_price"] == pytest.approx(sig["entry_price"])

    def test_long_bar3_entry_hit_but_activation_not_hit_is_void(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.40, "high": 100.90, "low": 99.90, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.30, "low": 100.10, "close": 101.20}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        assert sigs.iloc[0]["status"] == "void"

    def test_short_bar3_activation_and_entry_filled(self):
        b1 = {"open": 99.00, "high": 100.10, "low": 98.80, "close": 99.80}
        b2 = {"open": 99.70, "high": 99.90, "low": 99.00, "close": 99.30}
        b3 = {"open": 99.00, "high": 100.00, "low": 98.70, "close": 98.80}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="short",
            tick_size=TICK,
            trigger_params={"activation_retrace_ticks": 4, "entry_offset_ticks": 1},
        )
        sig = sigs.iloc[0]
        assert sig["activation_price"] == pytest.approx(100.00)
        assert sig["entry_price"] == pytest.approx(98.75)
        assert sig["status"] == "filled"
        assert sig["entry_reference_price"] == pytest.approx(98.75)

    def test_legacy_retrace_entry_ticks_maps_to_activation_retrace_ticks(self):
        b1 = {"open": 101.00, "high": 101.20, "low": 99.90, "close": 100.30}
        b2 = {"open": 100.40, "high": 100.90, "low": 99.90, "close": 100.70}
        b3 = {"open": 101.00, "high": 101.30, "low": 100.00, "close": 101.10}
        sigs = generate_signals(
            self._three_bar_df(b1, b2, b3),
            self._zone_with_levels(prices=[100.00], names=["level_A"]),
            trigger="confirm_3bar",
            direction="long",
            tick_size=TICK,
            trigger_params={"retrace_entry_ticks": 4, "entry_offset_ticks": 0},
        )
        assert len(sigs) == 1
        assert sigs.iloc[0]["activation_retrace_ticks"] == pytest.approx(4.0)


class TestNakedFilter:
    def test_naked_only_filters_zones_with_no_naked_levels(self):
        # Build a df with a level that has been touched (not naked at bar 1)
        ts = pd.date_range("2026-06-02 09:30", periods=3, freq="1min", tz=TZ)
        df = pd.DataFrame({
            "timestamp": ts,
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [100.0] * 3,
            "lA": [100.0, 100.0, 100.0],
            "lB": [100.25, 100.25, 100.25],
        })
        # Flag naked: both levels formed at bar 0; bar 1 touches them → not naked at bar 1
        naked_flags = flag_naked_levels(df, level_columns=["lA", "lB"], tick_size=TICK)

        # Zone at bar 1
        zones = _zone_df(1, low=100.0, high=100.25, level_names="lA|lB")

        sigs_all = generate_signals(
            df, zones, trigger="touch", direction="long", tick_size=TICK,
            naked_only=False,
        )
        sigs_naked_only = generate_signals(
            df, zones, trigger="touch", direction="long", tick_size=TICK,
            naked_only=True, naked_flags=naked_flags, naked_requirement="any",
        )
        # Without filter: signal emitted
        assert not sigs_all.empty
        # With naked_only=True and levels are not naked at bar 1: no signal
        assert sigs_naked_only.empty

    def test_naked_only_requires_naked_flags(self):
        df = _simple_bars(3)
        zones = _zone_df(0, 100.0, 100.5)
        with pytest.raises(ValueError, match="naked_flags"):
            generate_signals(df, zones, trigger="touch", direction="long",
                             tick_size=TICK, naked_only=True, naked_flags=None)


class TestEdgeCases:
    def test_empty_zones_returns_empty_signals(self):
        from thesistester.engine.confluence import _empty_zones_df
        df = _simple_bars(5)
        sigs = generate_signals(df, _empty_zones_df(), trigger="touch", direction="long", tick_size=TICK)
        assert sigs.empty

    def test_invalid_trigger_raises(self):
        df = _simple_bars(5)
        zones = _zone_df(0, 100.0, 100.5)
        with pytest.raises(ValueError, match="trigger"):
            generate_signals(df, zones, trigger="unknown", direction="long", tick_size=TICK)

    def test_invalid_direction_raises(self):
        df = _simple_bars(5)
        zones = _zone_df(0, 100.0, 100.5)
        with pytest.raises(ValueError, match="direction"):
            generate_signals(df, zones, trigger="touch", direction="diagonal", tick_size=TICK)

    def test_confirm_3bar_not_enough_bars(self):
        # Only 2 bars — bar 3 would be out of range
        df = _simple_bars(2)
        zones = _zone_df(0, 100.0 - 1.5, 100.0 + 1.5)  # zone covers default bar range
        sigs = generate_signals(df, zones, trigger="confirm_3bar", direction="long", tick_size=TICK)
        assert sigs.empty
