from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.metrics import summarize_trades, summarize_trades_by_direction
from thesistester.analytics.walk_forward import run_walk_forward_sl_tp, summarize_walk_forward


def _trades(*r_multiples: float) -> pd.DataFrame:
    n = len(r_multiples)
    ts = pd.date_range("2026-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
    return pd.DataFrame(
        {
            "trade_id": list(range(n)),
            "exit_timestamp": ts,
            "r_multiple": list(r_multiples),
        }
    )


def _ohlcv(n_bars: int) -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:30:00", periods=n_bars, freq="min", tz="America/New_York")
    rows = []
    for i, t in enumerate(ts):
        o = 100.0 + (i * 0.1)
        rows.append(
            {
                "timestamp": t,
                "open": o,
                "high": o + 2.5,
                "low": o - 0.2,
                "close": o + 0.5,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


def _touch_signal(signal_id: int, bar_index: int, direction: str = "long") -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York"),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
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
    }


def test_institutional_metrics_empty_summary_is_safe():
    summary = summarize_trades(pd.DataFrame())

    for key in [
        "median_r",
        "std_r",
        "downside_std_r",
        "sharpe_like_r",
        "sortino_like_r",
        "expectancy_to_drawdown",
        "max_consecutive_wins",
        "max_consecutive_losses",
        "avg_win_r",
        "avg_loss_r",
        "win_loss_ratio",
        "largest_win_r",
        "largest_loss_r",
        "p95_r",
        "p05_r",
        "tail_ratio",
        "trade_return_skew",
        "trade_return_kurtosis",
        "ulcer_index_r",
        "recovery_factor",
        "payoff_stability",
        "outlier_dependency_ratio",
    ]:
        assert key in summary

    assert summary["trade_count"] == 0
    assert summary["max_consecutive_wins"] == 0
    assert summary["max_consecutive_losses"] == 0
    assert summary["std_r"] is None
    assert summary["sharpe_like_r"] is None
    assert summary["ulcer_index_r"] is None


def test_institutional_metrics_known_r_sequence():
    summary = summarize_trades(_trades(1.0, -0.5, 2.0, -1.0, 0.5))

    assert summary["median_r"] == pytest.approx(0.5)
    assert summary["avg_win_r"] == pytest.approx((1.0 + 2.0 + 0.5) / 3.0)
    assert summary["avg_loss_r"] == pytest.approx((-0.5 + -1.0) / 2.0)
    assert summary["largest_win_r"] == pytest.approx(2.0)
    assert summary["largest_loss_r"] == pytest.approx(-1.0)
    assert summary["max_consecutive_wins"] == 1
    assert summary["max_consecutive_losses"] == 1
    assert summary["p95_r"] == pytest.approx(1.8)
    assert summary["p05_r"] == pytest.approx(-0.9)
    assert summary["ulcer_index_r"] >= 0.0


def test_institutional_metrics_zero_variance_handling():
    summary = summarize_trades(_trades(1.0, 1.0, 1.0))

    assert summary["std_r"] == pytest.approx(0.0)
    assert summary["sharpe_like_r"] is None
    assert summary["sortino_like_r"] is None


def test_institutional_metrics_outlier_dependency_ratio():
    summary = summarize_trades(_trades(10.0, -1.0, -1.0, -1.0))

    assert summary["outlier_dependency_ratio"] is not None
    assert summary["outlier_dependency_ratio"] == pytest.approx(-3.0 / 7.0)


def test_institutional_metrics_loss_only_and_win_only_are_safe():
    loss_only = summarize_trades(_trades(-1.0, -2.0, -0.5))
    win_only = summarize_trades(_trades(1.0, 2.0, 0.5))

    assert loss_only["avg_win_r"] is None
    assert loss_only["win_loss_ratio"] is None
    assert loss_only["sortino_like_r"] is not None
    assert win_only["avg_loss_r"] is None
    assert win_only["downside_std_r"] is None
    assert win_only["sortino_like_r"] is None


def test_institutional_metrics_directional_summary_includes_advanced_keys():
    trades = pd.DataFrame(
        {
            "trade_id": [1, 2, 3, 4],
            "direction": ["long", "long", "short", "short"],
            "r_multiple": [1.0, -0.5, 2.0, -1.0],
        }
    )

    summary = summarize_trades_by_direction(trades)

    assert "sharpe_like_r" in summary["long"]
    assert "ulcer_index_r" in summary["short"]
    assert summary["long"]["max_consecutive_losses"] == 1


def test_institutional_metrics_walk_forward_includes_selected_columns():
    df = _ohlcv(12)
    signals = pd.DataFrame([_touch_signal(i, i) for i in range(10)])

    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=0.25,
        point_value=50.0,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
    )
    summary = summarize_walk_forward(results)

    for key in [
        "train_sharpe_like_r",
        "train_sortino_like_r",
        "train_ulcer_index_r",
        "test_sharpe_like_r",
        "test_sortino_like_r",
        "test_ulcer_index_r",
        "test_recovery_factor",
    ]:
        assert key in results.columns

    for key in [
        "median_test_sharpe_like_r",
        "median_test_sortino_like_r",
        "median_test_ulcer_index_r",
    ]:
        assert key in summary
