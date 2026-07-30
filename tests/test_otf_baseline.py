"""OTF baseline regression tests — OTF absent / disabled.

These tests record deterministic expected values for the existing
signal-generation and backtest pipeline **without any OTF filtering**.

Purpose
-------
Provide a reproducible baseline that will catch any unintended change to
signal counts, trade outcomes, or key metrics when OTF infrastructure is
later introduced in subsequent PRs.

Design rules
------------
- No OTF filtering code is imported or executed in this module.
- All scenarios use the signal-generation and backtest code as-is today.
- Assertions are precise (exact counts, exact prices, exact R-multiples)
  rather than range or snapshot comparisons.

Verification commands
---------------------

    python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q
    python3 -m pytest tests/ -q

Related files
-------------
- tests/fixtures/otf_fixtures.py  — OTF OHLCV fixtures
- tests/test_otf_contract.py      — OTF contract vector tests
- docs/otf-filter.md              — OTF v1 behavioral contract
- docs/otf-filter-roadmap.md      — implementation roadmap
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.engine.backtest import simulate_trades
from thesistester.engine.signals import generate_signals


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_phase5_backtest.py conventions)
# ---------------------------------------------------------------------------


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _zone(bar_idx: int, ts: str, low: float, high: float, names: str = "A|B") -> dict:
    """Minimal zone row matching the expected confluence-zone schema."""
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "bar_index": bar_idx,
        "zone_low": low,
        "zone_high": high,
        "zone_mid": round((low + high) / 2.0, 6),
        "level_count": len(names.split("|")),
        "level_names": names,
        "level_prices": "|".join(str(round((low + high) / 2.0, 4)) for _ in names.split("|")),
    }


def _signal(
    bar_index: int,
    trigger: str = "touch",
    direction: str = "long",
    status: str = "candidate",
    entry_ref: float = 100.0,
    zone_low: float = 99.75,
    zone_high: float = 100.25,
    signal_id: int = 0,
    **extra,
) -> pd.DataFrame:
    """Minimal pre-built signal row (bypasses generate_signals)."""
    row = {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-05 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": trigger,
        "direction": direction,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_mid": (zone_low + zone_high) / 2.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": entry_ref,
        "entry_model": "candidate_next_bar_open",
        "status": status,
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }
    row.update(extra)
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Baseline 1 — Signal generation: touch trigger, long direction
#
# This test verifies that generate_signals() produces exactly one touch signal
# when a single bar's range overlaps the zone.  It confirms the current
# behavior without any OTF filter applied.
# ---------------------------------------------------------------------------


class TestBaselineSignalGenerationTouch:
    """Signal-generation baseline: touch trigger, no OTF filter.

    Signal generation checks the bar AT the zone's bar_index for a touch.
    The zone is placed at bar 1 (where the touch occurs); bar 0 is an anchor
    bar whose prices are well outside the zone.
    """

    def _setup(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (df, zones) for a single long touch scenario."""
        df = _df(
            _bar("2026-01-05 09:30", 102.0, 103.0, 101.5, 102.5),  # bar 0: no zone here
            _bar(
                "2026-01-05 09:31", 101.5, 101.8, 100.0, 100.5
            ),  # bar 1: zone here, low=100.0 ≤ 100.25
            _bar("2026-01-05 09:32", 100.8, 103.5, 100.5, 103.0),  # bar 2: entry bar, wide TP
            _bar("2026-01-05 09:33", 103.0, 103.5, 102.5, 103.2),  # bar 3: no zone touch
        )
        zones = pd.DataFrame(
            [
                _zone(1, "2026-01-05 09:31", low=99.75, high=100.25),
            ]
        )
        return df, zones

    def test_one_signal_is_generated(self) -> None:
        """Exactly one touch signal is generated for bar 1 where zone is placed.

        Touch fires when bar_low <= zone_high AND bar_high >= zone_low.
        Bar 1: L=100.0 <= zone_high=100.25 AND H=101.8 >= zone_low=99.75 → touch.
        """
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert len(signals) == 1, f"Expected 1 signal, got {len(signals)}"

    def test_signal_direction_is_long(self) -> None:
        """Generated signal must be long."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["direction"] == "long"

    def test_signal_trigger_is_touch(self) -> None:
        """Generated signal trigger must be 'touch'."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["trigger"] == "touch"

    def test_signal_bar_index(self) -> None:
        """Signal bar_index must be 1 (the bar where the zone is placed and touch occurs)."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["bar_index"] == 1

    def test_signal_entry_model(self) -> None:
        """Touch signals use candidate_next_bar_open entry model."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["entry_model"] == "candidate_next_bar_open"

    def test_signal_status_is_candidate(self) -> None:
        """Touch signal status must be 'candidate'."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["status"] == "candidate"

    def test_signal_zone_bounds_preserved(self) -> None:
        """Signal must carry zone_low and zone_high from the source zone."""
        df, zones = self._setup()
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.iloc[0]["zone_low"] == pytest.approx(99.75)
        assert signals.iloc[0]["zone_high"] == pytest.approx(100.25)

    def test_no_signal_when_zone_not_touched(self) -> None:
        """When no bar's range overlaps the zone, no signal is generated.

        Zone at bar 0 (bar_index=0).  Bar 0 has L=101.5 which is above zone_high=100.25,
        so the touch condition (bar_low <= zone_high) is not satisfied.
        """
        df = _df(
            _bar(
                "2026-01-05 09:30", 102.0, 103.0, 101.5, 102.5
            ),  # bar 0: zone here, L=101.5 > 100.25
            _bar("2026-01-05 09:31", 102.0, 103.5, 101.5, 103.0),  # bar 1: no zone
            _bar("2026-01-05 09:32", 103.0, 104.0, 102.5, 103.8),  # bar 2: no zone
        )
        zones = pd.DataFrame([_zone(0, "2026-01-05 09:30", low=99.75, high=100.25)])
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.empty, f"Expected no signals when zone is never touched, got {len(signals)}"

    def test_empty_zones_produces_no_signals(self) -> None:
        """Empty zones input produces an empty signal DataFrame."""
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5),
            _bar("2026-01-05 09:31", 100.5, 102.0, 100.0, 101.5),
        )
        zones = pd.DataFrame(
            columns=[
                "timestamp",
                "bar_index",
                "zone_low",
                "zone_high",
                "zone_mid",
                "level_count",
                "level_names",
                "level_prices",
            ]
        )
        signals = generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)
        assert signals.empty


# ---------------------------------------------------------------------------
# Baseline 2 — Backtest: long touch signal, take-profit exit
#
# Pre-built signal at bar 0 → entry at bar 1 open → TP hit in bar 1.
# ---------------------------------------------------------------------------


class TestBaselineBacktestLongTakeProfit:
    """Backtest baseline: long touch → TP exit, no OTF filter."""

    def _data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 100.5, 99.5, 100.0),  # bar 0: signal bar
            _bar("2026-01-05 09:31", 100.0, 104.0, 99.8, 103.0),  # bar 1: entry + TP
        )
        # SL=4 ticks below entry (100.0 - 1.0 = 99.0), TP=8 ticks above (100.0 + 2.0 = 102.0)
        # bar 1: entry=100.0, SL=99.0, TP=102.0
        # bar 1: L=99.8 > SL=99.0, H=104.0 >= TP=102.0 → TP hit
        sigs = _signal(bar_index=0, direction="long", entry_ref=100.0)
        return df, sigs

    def test_one_trade_produced(self) -> None:
        """Exactly one trade is produced from one long signal."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert len(trades) == 1

    def test_trade_direction_is_long(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["direction"] == "long"

    def test_trade_entry_price(self) -> None:
        """Entry price must be the open of bar 1 (100.0)."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["entry_price"] == pytest.approx(100.0)

    def test_trade_exit_reason_is_take_profit(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["exit_reason"] == "TP"

    def test_trade_r_multiple(self) -> None:
        """R-multiple must be 2.0 (8 ticks profit / 4 ticks risk)."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["r_multiple"] == pytest.approx(2.0)

    def test_trade_pnl_points(self) -> None:
        """Gross P&L must be 2.0 points (8 ticks * 0.25)."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["pnl_points"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Baseline 3 — Backtest: short touch signal, stop-loss exit
# ---------------------------------------------------------------------------


class TestBaselineBacktestShortStopLoss:
    """Backtest baseline: short touch → SL exit, no OTF filter."""

    def _data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 100.5, 99.5, 100.0),  # bar 0: signal bar
            _bar("2026-01-05 09:31", 100.0, 101.5, 99.0, 101.0),  # bar 1: entry + SL hit
        )
        # Entry at bar 1 open = 100.0
        # SL = 100.0 + 4*0.25 = 101.0 (4 ticks above)
        # TP = 100.0 - 8*0.25 = 98.0 (8 ticks below)
        # bar 1: H=101.5 >= SL=101.0 → SL hit (pessimistic: SL wins if both same bar)
        # bar 1: L=99.0 > TP=98.0 → TP not hit
        # Result: SL exit
        sigs = _signal(bar_index=0, direction="short", entry_ref=100.0)
        return df, sigs

    def test_one_trade_produced(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert len(trades) == 1

    def test_trade_direction_is_short(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["direction"] == "short"

    def test_trade_exit_reason_is_stop_loss(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["exit_reason"] == "SL"

    def test_trade_r_multiple(self) -> None:
        """R-multiple must be -1.0 (stop hit = 1R loss)."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert trades.iloc[0]["r_multiple"] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Baseline 4 — Backtest: empty signals produce empty trades
# ---------------------------------------------------------------------------


class TestBaselineEmptyInputs:
    """Verify empty-input invariants with no OTF filter present."""

    def test_empty_signals_produce_empty_trades(self) -> None:
        df = _df(_bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5))
        trades = simulate_trades(
            df,
            pd.DataFrame(),
            TICK,
            POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )
        assert trades.empty

    def test_simulate_trades_return_type_is_dataframe_by_default(self) -> None:
        """Default return is a DataFrame (not a tuple)."""
        df = _df(_bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5))
        result = simulate_trades(
            df,
            pd.DataFrame(),
            TICK,
            POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
        )
        assert isinstance(result, pd.DataFrame)

    def test_simulate_trades_returns_tuple_when_requested(self) -> None:
        """return_skipped_signals=True returns a (trades, skipped) tuple."""
        df = _df(_bar("2026-01-05 09:30", 100.0, 101.0, 99.0, 100.5))
        result = simulate_trades(
            df,
            pd.DataFrame(),
            TICK,
            POINT_VALUE,
            stop_loss_ticks=4,
            take_profit_ticks=8,
            return_skipped_signals=True,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Baseline 5 — Signal-generation: short direction
# ---------------------------------------------------------------------------


class TestBaselineSignalGenerationShort:
    """Verify short-direction touch signal generation without OTF filter.

    The zone is placed at bar 1.  Signal generation checks the bar AT the zone's
    bar_index for a touch.  Bar 1 has H=100.1 >= zone_low=99.75, so the touch
    condition fires.
    """

    def test_short_touch_signal_generated(self) -> None:
        """A short touch signal fires when bar's range overlaps the zone.

        Zone at bar 1 (bar_index=1), zone_low=99.75, zone_high=100.25.
        Bar 1: H=100.1 >= zone_low=99.75 AND L=97.5 <= zone_high=100.25 → touch.
        """
        df = _df(
            _bar("2026-01-05 09:30", 98.0, 98.5, 97.5, 98.0),  # bar 0: no zone
            _bar(
                "2026-01-05 09:31", 98.5, 100.1, 97.5, 99.0
            ),  # bar 1: zone here, high touches zone
            _bar("2026-01-05 09:32", 99.0, 99.5, 96.0, 96.5),  # bar 2: no zone touch
        )
        zones = pd.DataFrame([_zone(1, "2026-01-05 09:31", low=99.75, high=100.25)])
        signals = generate_signals(df, zones, trigger="touch", direction="short", tick_size=TICK)
        assert len(signals) == 1
        assert signals.iloc[0]["direction"] == "short"

    def test_short_signal_bar_index(self) -> None:
        df = _df(
            _bar("2026-01-05 09:30", 98.0, 98.5, 97.5, 98.0),
            _bar("2026-01-05 09:31", 98.5, 100.1, 97.5, 99.0),
            _bar("2026-01-05 09:32", 99.0, 99.5, 96.0, 96.5),
        )
        zones = pd.DataFrame([_zone(1, "2026-01-05 09:31", low=99.75, high=100.25)])
        signals = generate_signals(df, zones, trigger="touch", direction="short", tick_size=TICK)
        assert signals.iloc[0]["bar_index"] == 1


# ---------------------------------------------------------------------------
# Baseline 6 — Backtest: two signals, two trades, mixed outcomes
#
# This test provides a concise end-to-end baseline for the combined
# signal → trade pipeline.  Both signals are pre-built to avoid confounding
# with signal-generation behavior.
# ---------------------------------------------------------------------------


class TestBaselineTwoTrades:
    """Two-trade backtest baseline: one TP, one SL, no OTF filter."""

    def _data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 100.5, 99.5, 100.0),  # bar 0: signal bars
            _bar("2026-01-05 09:31", 100.0, 103.0, 99.8, 102.5),  # bar 1: trade 0 entry — TP
            _bar("2026-01-05 09:32", 100.0, 100.5, 99.5, 100.0),  # bar 2: signal bar (short)
            _bar("2026-01-05 09:33", 100.0, 101.5, 99.0, 101.0),  # bar 3: trade 1 entry — SL
        )
        # Signal 0: long at bar 0, entry bar 1, TP at 102.0 (8 ticks above 100.0)
        # Signal 1: short at bar 2, entry bar 3, SL at 101.0 (4 ticks above 100.0)
        sigs = pd.concat(
            [
                _signal(bar_index=0, signal_id=0, direction="long", entry_ref=100.0),
                _signal(bar_index=2, signal_id=1, direction="short", entry_ref=100.0),
            ],
            ignore_index=True,
        )
        return df, sigs

    def test_two_trades_produced(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        assert len(trades) == 2

    def test_first_trade_is_long_tp(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        t0 = trades[trades["direction"] == "long"].iloc[0]
        assert t0["exit_reason"] == "TP"
        assert t0["r_multiple"] == pytest.approx(2.0)

    def test_second_trade_is_short_sl(self) -> None:
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        t1 = trades[trades["direction"] == "short"].iloc[0]
        assert t1["exit_reason"] == "SL"
        assert t1["r_multiple"] == pytest.approx(-1.0)

    def test_total_r_is_one(self) -> None:
        """Total R = 2.0 (TP) + (-1.0) (SL) = 1.0."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        total_r = trades["r_multiple"].sum()
        assert total_r == pytest.approx(1.0)

    def test_trade_count_unaffected_without_otf(self) -> None:
        """Without OTF filter, all candidate signals become trades.
        This assertion must remain true after future OTF integration when
        OTF is disabled (the default state)."""
        df, sigs = self._data()
        trades = simulate_trades(
            df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8
        )
        # All 2 candidate signals → 2 trades (no OTF rejection)
        assert len(trades) == len(sigs)


# ---------------------------------------------------------------------------
# Baseline 7 — Signal schema stability
#
# Verify that the signal DataFrame schema returned by generate_signals()
# contains the columns relied on by downstream code, so that future PRs
# cannot silently drop them.
# ---------------------------------------------------------------------------


class TestBaselineSignalSchema:
    """Verify the signal DataFrame schema is stable (OTF-absent baseline)."""

    _REQUIRED_SIGNAL_COLUMNS = [
        "signal_id",
        "timestamp",
        "bar_index",
        "trigger",
        "direction",
        "zone_low",
        "zone_high",
        "zone_mid",
        "level_count",
        "level_names",
        "entry_reference_price",
        "entry_model",
        "status",
        "naked_level_count",
        "naked_requirement",
        "notes",
    ]

    def _make_signal_df(self) -> pd.DataFrame:
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 100.5, 99.5, 100.0),
            _bar("2026-01-05 09:31", 100.0, 100.25, 99.75, 100.0),  # bar 1: zone here, touches zone
            _bar("2026-01-05 09:32", 100.0, 100.5, 99.5, 100.0),
        )
        zones = pd.DataFrame([_zone(1, "2026-01-05 09:31", low=99.75, high=100.25)])
        return generate_signals(df, zones, trigger="touch", direction="long", tick_size=TICK)

    def test_required_columns_present(self) -> None:
        """All required signal columns must be present in the output."""
        signals = self._make_signal_df()
        missing = set(self._REQUIRED_SIGNAL_COLUMNS) - set(signals.columns)
        assert not missing, f"Signal DataFrame is missing columns: {missing}"

    def test_no_otf_columns_present(self) -> None:
        """OTF columns must NOT be present in signal output before OTF is implemented.
        If this test fails in a future PR, it indicates OTF columns were added.
        Update this test to assert the new OTF column values rather than removing it."""
        signals = self._make_signal_df()
        otf_columns = [c for c in signals.columns if c.startswith("otf_")]
        assert len(otf_columns) == 0, (
            f"OTF columns found in signal output before OTF is implemented: {otf_columns}. "
            "Update this test if OTF columns are intentionally added."
        )


# ---------------------------------------------------------------------------
# Baseline 8 — Trade schema stability
# ---------------------------------------------------------------------------


class TestBaselineTradeSchema:
    """Verify the trade DataFrame schema is stable (OTF-absent baseline)."""

    _REQUIRED_TRADE_COLUMNS = [
        "trade_id",
        "signal_id",
        "trigger",
        "direction",
        "entry_timestamp",
        "entry_bar_index",
        "entry_price",
        "exit_timestamp",
        "exit_bar_index",
        "exit_price",
        "exit_reason",
        "stop_price",
        "target_price",
        "stop_loss_ticks",
        "take_profit_ticks",
        "r_multiple",
        "pnl_points",
        "bars_held",
        "zone_low",
        "zone_high",
    ]

    def _make_trades(self) -> pd.DataFrame:
        df = _df(
            _bar("2026-01-05 09:30", 100.0, 100.5, 99.5, 100.0),
            _bar("2026-01-05 09:31", 100.0, 104.0, 99.8, 103.0),
        )
        sigs = _signal(bar_index=0, direction="long", entry_ref=100.0)
        return simulate_trades(df, sigs, TICK, POINT_VALUE, stop_loss_ticks=4, take_profit_ticks=8)

    def test_required_columns_present(self) -> None:
        """All required trade columns must be present in the output."""
        trades = self._make_trades()
        missing = set(self._REQUIRED_TRADE_COLUMNS) - set(trades.columns)
        assert not missing, f"Trade DataFrame is missing columns: {missing}"
