"""Phase 6 grid search tests.

All tests use a small synthetic OHLCV + signals dataset so they run fast
and produce deterministic results.
"""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.grid import best_grid_result, run_sl_tp_grid


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


# ---------------------------------------------------------------------------
# Helpers (mirror Phase 5 test helpers)
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


def _signal(
    bar_index: int = 0,
    trigger: str = "touch",
    direction: str = "long",
    status: str = "candidate",
    entry_ref: float = 100.0,
    zone_low: float = 99.5,
    zone_high: float = 100.5,
    signal_id: int = 0,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
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
    }])


# Minimal synthetic dataset: signal bar at index 0, entry at index 1 where TP is hit.
# entry_open = 100.0, SL=4 ticks → sl_pts=1.0, TP=8 ticks → tp_pts=2.0
# next bar high = 102.5 > 102.0 (TP), low = 99.8 (does not touch 99.0 SL) → TP hit → R = +2.0

_OHLCV = _df(
    _bar("2026-01-02 09:30", 100.0, 100.5, 99.5, 100.0),
    _bar("2026-01-02 09:31", 100.0, 102.5, 99.8, 102.0),
)
_SIGNALS = _signal(bar_index=0, trigger="touch", direction="long")

SL_VALUES = [4, 8]
TP_VALUES = [8, 16, 24]


# ---------------------------------------------------------------------------
# 1. Grid row count
# ---------------------------------------------------------------------------


def test_grid_row_count():
    """2 SL values × 3 TP values → 6 rows."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=SL_VALUES,
        take_profit_ticks_values=TP_VALUES,
    )
    assert len(grid) == 6


# ---------------------------------------------------------------------------
# 2. Required output columns present
# ---------------------------------------------------------------------------


_REQUIRED_COLS = [
    "stop_loss_ticks",
    "take_profit_ticks",
    "trade_count",
    "win_rate",
    "loss_rate",
    "avg_r",
    "expectancy_r",
    "median_r",
    "total_r",
    "profit_factor",
    "avg_win_r",
    "avg_loss_r",
    "max_drawdown_r",
    "best_trade_r",
    "worst_trade_r",
]


def test_grid_output_columns():
    """All required columns must be present."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=SL_VALUES,
        take_profit_ticks_values=TP_VALUES,
    )
    for col in _REQUIRED_COLS:
        assert col in grid.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# 3. Sorted deterministic output
# ---------------------------------------------------------------------------


def test_grid_sorted_output():
    """Output must be sorted by stop_loss_ticks then take_profit_ticks."""
    # Pass values in reverse order to verify sorting is applied.
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=list(reversed(SL_VALUES)),
        take_profit_ticks_values=list(reversed(TP_VALUES)),
    )
    sl_col = grid["stop_loss_ticks"].tolist()
    assert sl_col == sorted(sl_col), "Rows not sorted by stop_loss_ticks"
    for sl in set(sl_col):
        tp_col = grid.loc[grid["stop_loss_ticks"] == sl, "take_profit_ticks"].tolist()
        assert tp_col == sorted(tp_col), (
            f"TP values not sorted for SL={sl}"
        )


# ---------------------------------------------------------------------------
# 4–7. Validation errors
# ---------------------------------------------------------------------------


def test_empty_sl_raises():
    """Empty stop_loss_ticks_values must raise ValueError."""
    with pytest.raises(ValueError, match="stop_loss_ticks"):
        run_sl_tp_grid(_OHLCV, _SIGNALS, TICK, POINT_VALUE,
                       stop_loss_ticks_values=[],
                       take_profit_ticks_values=TP_VALUES)


def test_empty_tp_raises():
    """Empty take_profit_ticks_values must raise ValueError."""
    with pytest.raises(ValueError, match="take_profit_ticks"):
        run_sl_tp_grid(_OHLCV, _SIGNALS, TICK, POINT_VALUE,
                       stop_loss_ticks_values=SL_VALUES,
                       take_profit_ticks_values=[])


def test_nonpositive_sl_raises():
    """SL value of 0 must raise ValueError."""
    with pytest.raises(ValueError):
        run_sl_tp_grid(_OHLCV, _SIGNALS, TICK, POINT_VALUE,
                       stop_loss_ticks_values=[0, 4],
                       take_profit_ticks_values=TP_VALUES)


def test_nonpositive_tp_raises():
    """TP value ≤ 0 must raise ValueError."""
    with pytest.raises(ValueError):
        run_sl_tp_grid(_OHLCV, _SIGNALS, TICK, POINT_VALUE,
                       stop_loss_ticks_values=SL_VALUES,
                       take_profit_ticks_values=[-1, 8])


# ---------------------------------------------------------------------------
# 8. best_grid_result returns highest expectancy_r row
# ---------------------------------------------------------------------------


def test_best_grid_result_returns_highest():
    """best_grid_result should return the row with the highest expectancy_r."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=SL_VALUES,
        take_profit_ticks_values=TP_VALUES,
    )
    best = best_grid_result(grid, metric="expectancy_r")
    assert best is not None
    assert best["expectancy_r"] == grid["expectancy_r"].max()


# ---------------------------------------------------------------------------
# 9. best_grid_result respects min_trades
# ---------------------------------------------------------------------------


def test_best_grid_result_respects_min_trades():
    """Rows with trade_count < min_trades must be excluded."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    # Our synthetic data produces exactly 1 trade per cell.
    # min_trades=2 should exclude all rows.
    result = best_grid_result(grid, metric="expectancy_r", min_trades=2)
    assert result is None


# ---------------------------------------------------------------------------
# 10. best_grid_result returns None for empty / all-filtered grid
# ---------------------------------------------------------------------------


def test_best_grid_result_none_on_empty():
    """best_grid_result must return None when grid is empty."""
    assert best_grid_result(pd.DataFrame(), metric="expectancy_r") is None


def test_best_grid_result_none_when_all_filtered():
    """best_grid_result returns None when all rows are filtered out."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    # Force trade_count to 0 for all rows so filter removes everything.
    grid["trade_count"] = 0
    result = best_grid_result(grid, metric="expectancy_r", min_trades=1)
    assert result is None


# ---------------------------------------------------------------------------
# 11. Uses existing backtest engine — known R values
# ---------------------------------------------------------------------------


def test_grid_uses_backtest_engine_known_r():
    """Verify a grid cell produces the expected R via the Phase 5 engine.

    Setup:
      - entry_open = 100.0 (next-bar open after signal at bar 0)
      - SL = 4 ticks → 1.0 pt → stop at 99.0
      - TP = 8 ticks → 2.0 pt → target at 102.0
      - Bar 1: high=102.5 > 102.0 (TP), low=99.8 (does not reach 99.0 SL)
        → TP hit → R = +2.0
    """
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    assert len(grid) == 1
    row = grid.iloc[0]
    assert row["trade_count"] == 1
    assert row["total_r"] == pytest.approx(2.0)
    assert row["avg_r"] == pytest.approx(2.0)
    assert row["win_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Phase 2: Directional grid columns
# ---------------------------------------------------------------------------

_DIRECTIONAL_COLS = [
    "long_trade_count",
    "long_profit_factor",
    "long_expectancy_r",
    "short_trade_count",
    "short_profit_factor",
    "short_expectancy_r",
    "min_direction_trade_count",
    "min_direction_profit_factor",
    "min_direction_expectancy_r",
]


def test_directional_columns_exist():
    """All Phase 2 directional columns must be present in grid output."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=SL_VALUES,
        take_profit_ticks_values=TP_VALUES,
    )
    for col in _DIRECTIONAL_COLS:
        assert col in grid.columns, f"Missing directional column: {col}"


def test_long_only_grid_is_safe():
    """Long-only signal set must produce safe directional metrics.

    Existing synthetic data uses a long-only signal.
    Expected:
    - long_trade_count == 1
    - short_trade_count == 0
    - short_profit_factor is NaN (no short trades)
    - min_direction_profit_factor is NaN (one side missing)
    """
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    row = grid.iloc[0]
    assert row["trade_count"] == 1
    assert row["long_trade_count"] == 1
    assert row["short_trade_count"] == 0
    assert pd.isna(row["short_profit_factor"])
    assert pd.isna(row["min_direction_profit_factor"])
    assert pd.isna(row["min_direction_expectancy_r"])


def _make_mixed_dataset():
    """Build a minimal OHLCV + signals dataset with one long and one short signal.

    Long signal (bar 0):
      - entry bar 1 open = 100.0, long
      - SL=4 ticks → 1.0 pt → stop at 99.0
      - TP=8 ticks → 2.0 pt → target at 102.0
      - Bar 1: high=102.5 > 102.0 → TP hit → R = +2.0

    Short signal (bar 2):
      - entry bar 3 open = 200.0, short
      - SL=4 ticks → 1.0 pt → stop at 201.0
      - TP=8 ticks → 2.0 pt → target at 198.0
      - Bar 3: low=197.5 < 198.0 → TP hit → R = +2.0
    """
    TZ = "America/New_York"
    ohlcv = pd.DataFrame([
        {"timestamp": pd.Timestamp("2026-01-02 09:30", tz=TZ),
         "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100.0},
        {"timestamp": pd.Timestamp("2026-01-02 09:31", tz=TZ),
         "open": 100.0, "high": 102.5, "low": 99.8, "close": 102.0, "volume": 100.0},
        {"timestamp": pd.Timestamp("2026-01-02 09:32", tz=TZ),
         "open": 200.0, "high": 200.5, "low": 199.5, "close": 200.0, "volume": 100.0},
        {"timestamp": pd.Timestamp("2026-01-02 09:33", tz=TZ),
         "open": 200.0, "high": 200.5, "low": 197.5, "close": 198.0, "volume": 100.0},
    ])
    signals = pd.DataFrame([
        {
            "signal_id": 0,
            "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
            "bar_index": 0,
            "trigger": "touch",
            "direction": "long",
            "zone_low": 99.5,
            "zone_high": 100.5,
            "zone_mid": 100.0,
            "level_count": 2,
            "level_names": "A|B",
            "entry_reference_price": 100.0,
            "entry_model": "candidate_next_bar_open",
            "status": "candidate",
            "naked_level_count": 0,
            "naked_requirement": "any",
            "notes": "",
        },
        {
            "signal_id": 1,
            "timestamp": pd.Timestamp("2026-01-02 09:32:00", tz=TZ),
            "bar_index": 2,
            "trigger": "touch",
            "direction": "short",
            "zone_low": 199.5,
            "zone_high": 200.5,
            "zone_mid": 200.0,
            "level_count": 2,
            "level_names": "C|D",
            "entry_reference_price": 200.0,
            "entry_model": "candidate_next_bar_open",
            "status": "candidate",
            "naked_level_count": 0,
            "naked_requirement": "any",
            "notes": "",
        },
    ])
    return ohlcv, signals


def test_mixed_directional_grid():
    """Grid with long + short signals must compute both directional sides."""
    ohlcv, signals = _make_mixed_dataset()
    grid = run_sl_tp_grid(
        ohlcv, signals, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    row = grid.iloc[0]
    assert row["long_trade_count"] >= 1
    assert row["short_trade_count"] >= 1
    assert row["long_profit_factor"] is not None
    assert row["short_profit_factor"] is not None
    assert row["min_direction_profit_factor"] is not None
    assert row["min_direction_expectancy_r"] is not None
    assert row["min_direction_trade_count"] >= 1


def test_best_grid_result_unchanged_with_new_columns():
    """best_grid_result by expectancy_r still works after adding directional columns."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=SL_VALUES,
        take_profit_ticks_values=TP_VALUES,
    )
    best = best_grid_result(grid, metric="expectancy_r")
    assert best is not None
    assert best["expectancy_r"] == grid["expectancy_r"].max()


def test_best_grid_result_by_directional_metric():
    """best_grid_result ranks by the highest directional metric value."""
    ohlcv, signals = _make_mixed_dataset()
    grid = run_sl_tp_grid(
        ohlcv, signals, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4, 8],
        take_profit_ticks_values=[8, 16],
    )
    valid = grid.dropna(subset=["long_expectancy_r"])
    best = best_grid_result(grid, metric="long_expectancy_r")
    assert best is not None
    assert best["long_expectancy_r"] == valid["long_expectancy_r"].max()


def test_best_grid_result_missing_metric_returns_none():
    """best_grid_result returns None when metric column does not exist."""
    grid = run_sl_tp_grid(
        _OHLCV, _SIGNALS, TICK, POINT_VALUE,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
    )
    result = best_grid_result(grid, metric="does_not_exist")
    assert result is None
