from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics import best_grid_result, run_sl_tp_grid
from thesistester.analytics.walk_forward import run_walk_forward_sl_tp, summarize_walk_forward
from thesistester.analytics.metrics import summarize_trades
from thesistester.engine.backtest import simulate_trades
from thesistester.reporting import build_research_artifact


TZ = "America/New_York"
TICK = 0.25
POINT = 50.0


def _ohlcv(n_bars: int) -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:30:00", periods=n_bars, freq="min", tz=TZ)
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
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
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


def _signal_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_walk_forward_basic_fold_generation():
    df = _ohlcv(12)
    signals = _signal_df(*[_touch_signal(i, i) for i in range(10)])
    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
    )
    assert len(results) == 4
    assert results["train_start_bar"].tolist() == [0, 2, 4, 6]
    assert results["train_end_bar"].tolist() == [3, 5, 7, 9]
    assert results["test_start_bar"].tolist() == [4, 6, 8, 10]
    assert results["test_end_bar"].tolist() == [5, 7, 9, 11]


def test_walk_forward_remaps_entry_indices_for_slice():
    df = _ohlcv(9)
    signals = pd.DataFrame(
        [
            _touch_signal(1, 1),
            {
                **_touch_signal(2, 5),
                "trigger": "3c",
                "status": "filled",
                "entry_bar_index": 6,
                "retrace_entry_price": 100.0,
            },
        ]
    )
    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=3,
    )
    row = results.iloc[0]
    assert row["status"] == "ok"
    assert row["test_trade_count"] == 1


def test_walk_forward_train_selection_has_no_test_leakage():
    df = _ohlcv(10)
    df.loc[7:, "high"] = 200.0  # Future shock in test bars
    signals = _signal_df(_touch_signal(1, 0), _touch_signal(2, 2), _touch_signal(3, 7))

    wf = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4, 8],
        take_profit_ticks_values=[8, 16],
        train_bars=6,
        test_bars=2,
        step_bars=2,
    )
    first = wf.iloc[0]

    train_df = df.iloc[0:6].reset_index(drop=True)
    train_signals = signals[(signals["bar_index"] >= 0) & (signals["bar_index"] < 6)].copy()
    train_grid = run_sl_tp_grid(
        df=train_df,
        signals=train_signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4, 8],
        take_profit_ticks_values=[8, 16],
    )
    best = best_grid_result(train_grid, metric="expectancy_r", min_trades=1)
    assert best is not None
    assert first["selected_stop_loss_ticks"] == best["stop_loss_ticks"]
    assert first["selected_take_profit_ticks"] == best["take_profit_ticks"]


def test_walk_forward_test_metrics_use_selected_train_config():
    df = _ohlcv(10)
    signals = _signal_df(_touch_signal(1, 1), _touch_signal(2, 4), _touch_signal(3, 5))
    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4, 8],
        take_profit_ticks_values=[8, 16],
        train_bars=4,
        test_bars=3,
        step_bars=3,
    )
    row = results.iloc[0]
    assert row["status"] == "ok"

    test_df = df.iloc[4:7].reset_index(drop=True)
    test_signals = signals[(signals["bar_index"] >= 4) & (signals["bar_index"] < 7)].copy()
    test_signals["bar_index"] = test_signals["bar_index"] - 4
    trades = simulate_trades(
        df=test_df,
        signals=test_signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks=float(row["selected_stop_loss_ticks"]),
        take_profit_ticks=float(row["selected_take_profit_ticks"]),
    )
    summary = summarize_trades(trades)
    assert row["test_trade_count"] == summary["trade_count"]
    assert row["test_expectancy_r"] == pytest.approx(summary["expectancy_r"])


def test_walk_forward_no_train_candidate_status():
    df = _ohlcv(9)
    signals = _signal_df(_touch_signal(1, 1), _touch_signal(2, 5))
    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=3,
        min_train_trades=999,
    )
    row = results.iloc[0]
    assert row["status"] == "no_train_candidate"
    assert pd.isna(row["test_expectancy_r"])


def test_summarize_walk_forward_empty_no_valid_ok():
    empty = summarize_walk_forward(pd.DataFrame())
    assert empty["status"] == "empty"

    invalid_results = pd.DataFrame(
        [
            {"status": "no_train_candidate", "test_expectancy_r": None},
            {"status": "no_train_candidate", "test_expectancy_r": None},
        ]
    )
    no_valid = summarize_walk_forward(invalid_results)
    assert no_valid["status"] == "no_valid_folds"

    valid_results = pd.DataFrame(
        [
            {
                "status": "ok",
                "train_expectancy_r": 1.0,
                "test_expectancy_r": 0.5,
                "degradation_expectancy_r": -0.5,
                "test_total_r": 1.0,
                "test_trade_count": 2,
                "is_oos_profitable": True,
            },
            {
                "status": "ok",
                "train_expectancy_r": 0.5,
                "test_expectancy_r": -0.5,
                "degradation_expectancy_r": -1.0,
                "test_total_r": -1.0,
                "test_trade_count": 2,
                "is_oos_profitable": False,
            },
        ]
    )
    ok = summarize_walk_forward(valid_results)
    assert ok["status"] == "ok"
    assert ok["fold_count"] == 2
    assert ok["valid_fold_count"] == 2
    assert ok["aggregate_test_trade_count"] == 4


def test_walk_forward_execution_costs_pass_through():
    df = _ohlcv(12)
    signals = _signal_df(*[_touch_signal(i, i) for i in [1, 2, 5, 6, 9]])
    zero_cost = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
    )
    with_cost = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        commission_per_side=1.0,
        slippage_ticks=1.0,
    )
    assert summarize_walk_forward(with_cost)["aggregate_test_total_r"] < summarize_walk_forward(zero_cost)[
        "aggregate_test_total_r"
    ]


def test_walk_forward_exposure_policy_pass_through():
    df = _ohlcv(10)
    signals = _signal_df(
        _touch_signal(1, 1),
        _touch_signal(2, 4),
        _touch_signal(3, 4),
        _touch_signal(4, 7),
    )
    allow_all = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[100],
        take_profit_ticks_values=[100],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        max_holding_bars=1,
        exposure_policy="allow_all",
    )
    single_position = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[100],
        take_profit_ticks_values=[100],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        max_holding_bars=1,
        exposure_policy="single_position",
    )
    assert summarize_walk_forward(single_position)["aggregate_test_trade_count"] <= summarize_walk_forward(allow_all)[
        "aggregate_test_trade_count"
    ]


def test_research_artifact_includes_walk_forward_outputs():
    walk_forward_results = pd.DataFrame(
        [
            {
                "fold_id": 0,
                "status": "ok",
                "test_expectancy_r": 0.25,
            }
        ]
    )
    state = {
        "walk_forward_results": walk_forward_results,
        "walk_forward_summary": {"status": "ok", "fold_count": 1},
        "walk_forward_config": {"train_bars": 100, "test_bars": 50},
    }
    artifact = build_research_artifact(state)
    assert artifact["results"]["walk_forward_summary"]["fold_count"] == 1
    assert artifact["configuration"]["walk_forward_config"]["train_bars"] == 100
    assert len(artifact["tables"]["walk_forward_results"]) == 1
