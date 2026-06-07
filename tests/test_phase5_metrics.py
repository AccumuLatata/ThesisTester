"""Phase 5 metrics tests: summarize_trades and equity_curve."""
from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.metrics import (
    equity_curve,
    summarize_by_group,
    summarize_trades,
    summarize_trades_by_direction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trades(*r_multiples: float) -> pd.DataFrame:
    """Build a minimal trades DataFrame with given r_multiples."""
    n = len(r_multiples)
    ts = pd.date_range("2026-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
    return pd.DataFrame({
        "trade_id": list(range(n)),
        "exit_timestamp": ts,
        "r_multiple": list(r_multiples),
    })


# ---------------------------------------------------------------------------
# summarize_trades tests
# ---------------------------------------------------------------------------


def test_empty_trades_summary_is_safe():
    """Empty or None trades should return a safe dict without raising."""
    result = summarize_trades(pd.DataFrame())
    assert result["trade_count"] == 0
    assert result["win_rate"] is None
    assert result["total_r"] is None


def test_none_trades_summary_is_safe():
    result = summarize_trades(None)
    assert result["trade_count"] == 0


def test_win_rate():
    """Win rate = fraction of trades with r_multiple > 0."""
    t = _trades(1.0, -1.0, 1.0, 1.0)   # 3 wins out of 4
    s = summarize_trades(t)
    assert s["trade_count"] == 4
    assert s["win_rate"] == pytest.approx(0.75)
    assert s["loss_rate"] == pytest.approx(0.25)


def test_avg_r():
    t = _trades(2.0, -1.0, 3.0, -1.0)   # avg = (2-1+3-1)/4 = 0.75
    s = summarize_trades(t)
    assert s["avg_r"] == pytest.approx(0.75)


def test_total_r():
    t = _trades(1.0, 2.0, -1.0)   # total = 2.0
    s = summarize_trades(t)
    assert s["total_r"] == pytest.approx(2.0)


def test_profit_factor():
    """Profit factor = gross wins / |gross losses|."""
    t = _trades(3.0, -1.0)   # gross win 3.0, gross loss 1.0 → pf = 3.0
    s = summarize_trades(t)
    assert s["profit_factor"] == pytest.approx(3.0)


def test_profit_factor_no_losses():
    """All winning trades → profit factor = inf."""
    t = _trades(1.0, 2.0)
    s = summarize_trades(t)
    assert s["profit_factor"] == float("inf")


def test_profit_factor_no_wins():
    """All losing trades → profit factor = 0."""
    t = _trades(-1.0, -2.0)
    s = summarize_trades(t)
    assert s["profit_factor"] == 0.0


def test_best_worst_r():
    t = _trades(5.0, -2.0, 1.0)
    s = summarize_trades(t)
    assert s["best_trade_r"] == pytest.approx(5.0)
    assert s["worst_trade_r"] == pytest.approx(-2.0)


def test_expectancy():
    """expectancy_r = win_rate * avg_win_r + loss_rate * avg_loss_r."""
    t = _trades(2.0, -1.0)   # 50% win, avg_win=2, avg_loss=-1 → 0.5*2 + 0.5*(-1) = 0.5
    s = summarize_trades(t)
    assert s["expectancy_r"] == pytest.approx(0.5)


def test_summarize_trades_by_direction_mixed_long_short():
    t = pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4],
            "direction": ["long", "long", "short", "short"],
            "r_multiple": [1.0, -0.5, 2.0, -1.0],
        }
    )
    out = summarize_trades_by_direction(t)
    assert out["long"]["trade_count"] == 2
    assert out["short"]["trade_count"] == 2
    assert out["long"]["total_r"] == pytest.approx(0.5)
    assert out["short"]["total_r"] == pytest.approx(1.0)


def test_summarize_trades_by_direction_only_long():
    t = pd.DataFrame(
        {"trade_id": [1, 2], "direction": ["long", "long"], "r_multiple": [1.0, -1.0]}
    )
    out = summarize_trades_by_direction(t)
    assert out["long"]["trade_count"] == 2
    assert out["short"]["trade_count"] == 0
    assert out["short"]["profit_factor"] is None


def test_summarize_trades_by_direction_only_short():
    t = pd.DataFrame(
        {"trade_id": [1, 2], "direction": ["short", "short"], "r_multiple": [1.0, -1.0]}
    )
    out = summarize_trades_by_direction(t)
    assert out["short"]["trade_count"] == 2
    assert out["long"]["trade_count"] == 0
    assert out["long"]["profit_factor"] is None


def test_summarize_trades_by_direction_empty():
    out = summarize_trades_by_direction(pd.DataFrame())
    assert out["long"]["trade_count"] == 0
    assert out["short"]["trade_count"] == 0
    assert out["long"]["win_rate"] is None
    assert out["short"]["win_rate"] is None


def test_summarize_trades_by_direction_missing_r_multiple_is_safe():
    t = pd.DataFrame(
        {
            "trade_id": [1, 2],
            "direction": ["long", "short"],
        }
    )
    out = summarize_trades_by_direction(t)
    assert out["long"]["trade_count"] == 0
    assert out["short"]["trade_count"] == 0
    assert out["long"]["profit_factor"] is None
    assert out["short"]["profit_factor"] is None


def test_summarize_trades_by_direction_infinite_profit_factor_case():
    t = pd.DataFrame(
        {
            "trade_id": [1, 2, 3],
            "direction": ["long", "long", "short"],
            "r_multiple": [1.0, 2.0, -1.0],
        }
    )
    out = summarize_trades_by_direction(t)
    assert out["long"]["profit_factor"] == float("inf")
    assert out["short"]["profit_factor"] == 0.0


def test_grouped_summary_empty_is_safe():
    grouped = summarize_by_group(pd.DataFrame(), ["trigger_variant", "level_source_mode", "direction"])
    assert grouped.empty


def test_grouped_summary_ignores_missing_columns():
    t = _trades(1.0, -1.0)
    t["direction"] = ["long", "short"]
    grouped = summarize_by_group(t, ["trigger_variant", "level_source_mode", "direction"])
    assert list(grouped.columns)[0] == "direction"
    assert len(grouped) == 2


def test_grouped_summary_returns_one_row_per_group_combo():
    t = pd.DataFrame(
        {
            "r_multiple": [1.0, -1.0, 2.0, -0.5],
            "pnl_currency": [50.0, -50.0, 100.0, -25.0],
            "bars_held": [3, 4, 2, 5],
            "trigger_variant": ["3c_long", "3c_long", "3c_short", "3c_short"],
            "level_source_mode": ["global_cluster", "global_cluster", "user_anchor", "user_anchor"],
            "direction": ["long", "long", "short", "short"],
        }
    )
    grouped = summarize_by_group(t, ["trigger_variant", "level_source_mode", "direction"])
    assert len(grouped) == 2
    assert set(grouped["trigger_variant"]) == {"3c_long", "3c_short"}


# ---------------------------------------------------------------------------
# equity_curve tests
# ---------------------------------------------------------------------------


def test_equity_curve_empty():
    """Empty trades → empty equity curve with correct columns."""
    curve = equity_curve(pd.DataFrame())
    assert curve.empty
    assert set(["trade_id", "exit_timestamp", "r_multiple", "cum_r", "drawdown_r"]).issubset(curve.columns)


def test_equity_curve_cumulative_r():
    """Cumulative R should be a running sum of r_multiple."""
    t = _trades(1.0, 2.0, -1.0)
    curve = equity_curve(t)
    assert list(curve["cum_r"]) == pytest.approx([1.0, 3.0, 2.0])


def test_equity_curve_drawdown():
    """Drawdown = running_max - cum_r."""
    t = _trades(1.0, 2.0, -1.0)   # cum=[1,3,2], peak=[1,3,3], dd=[0,0,1]
    curve = equity_curve(t)
    assert list(curve["drawdown_r"]) == pytest.approx([0.0, 0.0, 1.0])


def test_equity_curve_always_non_negative_drawdown():
    """Drawdown values must always be >= 0."""
    t = _trades(1.0, -0.5, 2.0, -1.5, 0.5)
    curve = equity_curve(t)
    assert (curve["drawdown_r"] >= 0).all()


def test_equity_curve_drawdown_from_initial_zero():
    """A single losing trade must show drawdown from 0R initial equity."""
    t = _trades(-1.0)
    curve = equity_curve(t)
    assert list(curve["cum_r"]) == pytest.approx([-1.0])
    assert list(curve["drawdown_r"]) == pytest.approx([1.0])


def test_summary_max_drawdown_from_initial_zero():
    """summarize_trades max_drawdown_r must be 1.0 for a single -1R trade."""
    t = _trades(-1.0)
    s = summarize_trades(t)
    assert s["max_drawdown_r"] == pytest.approx(1.0)


def test_equity_curve_drawdown_after_positive_peak():
    """Drawdown after gains and then a loss is measured from the peak."""
    t = _trades(1.0, 2.0, -1.0)
    curve = equity_curve(t)
    assert list(curve["cum_r"]) == pytest.approx([1.0, 3.0, 2.0])
    assert list(curve["drawdown_r"]) == pytest.approx([0.0, 0.0, 1.0])
