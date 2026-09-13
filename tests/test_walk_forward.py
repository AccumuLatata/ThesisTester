from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics import best_grid_result, run_sl_tp_grid
from thesistester.analytics import walk_forward as walk_forward_mod
from thesistester.analytics.walk_forward import (
    WalkForwardResult,
    _actionable_index_column,
    _filter_fold_signals_with_otf,
    _otf_source_for_fold,
    normalize_otf_history_policy,
    run_walk_forward_sl_tp,
    run_wfa_matrix,
    summarize_walk_forward,
)
from thesistester.analytics.metrics import summarize_trades
from thesistester.engine.backtest import simulate_trades
from thesistester.reporting import build_research_artifact
from thesistester.setup import normalize_otf_filter_config


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


def _session_ohlcv(
    session_count: int,
    *,
    short_session_index: int | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for session_index in range(session_count):
        periods = 2 if session_index == short_session_index else 4
        timestamps = pd.date_range(
            pd.Timestamp("2026-01-05 09:30", tz=TZ) + pd.offsets.BusinessDay(session_index),
            periods=periods,
            freq="1min",
        )
        base = 100.0 + session_index
        for timestamp in timestamps:
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": base,
                    "high": base + 2.5,
                    "low": base - 0.5,
                    "close": base + 1.0,
                    "volume": 100.0,
                }
            )
    return pd.DataFrame(rows)


def _session_signals(df: pd.DataFrame) -> pd.DataFrame:
    local_dates = df["timestamp"].dt.date
    rows = []
    for signal_id, (_, indices) in enumerate(df.groupby(local_dates).groups.items(), start=1):
        first = int(min(indices))
        if first + 1 < len(df):
            rows.append(_touch_signal(signal_id, first))
    return pd.DataFrame(rows)


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
    assert set(results["intrabar_model"]) == {"sl_first"}


def test_session_folds_are_atomic_with_holiday_shortened_session():
    df = _session_ohlcv(6, short_session_index=3)
    results = run_walk_forward_sl_tp(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=1,
        test_bars=1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=1,
        step_sessions=1,
    )
    assert len(results) == 4
    assert set(results["fold_mode"]) == {"sessions"}
    assert set(results["train_session_count"]) == {2}
    assert set(results["test_session_count"]) == {1}
    session_dates = df["timestamp"].dt.date.astype(str)
    for row in results.itertuples():
        test_dates = set(session_dates.iloc[row.test_start_bar : row.test_end_bar + 1])
        assert test_dates == {row.test_start_session_date}
    shortened_date = str(df["timestamp"].dt.date.unique()[3])
    shortened_rows = results[results["test_start_session_date"] == shortened_date]
    assert not shortened_rows.empty
    row = shortened_rows.iloc[0]
    assert row["test_end_bar"] - row["test_start_bar"] + 1 == 2


def test_anchored_session_folds_grow_training_window_from_origin():
    df = _session_ohlcv(6)
    results = run_walk_forward_sl_tp(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=1,
        test_bars=1,
        fold_mode="sessions",
        window_mode="anchored",
        train_sessions=2,
        test_sessions=1,
        step_sessions=1,
    )
    assert results["train_start_bar"].tolist() == [0, 0, 0, 0]
    assert results["train_session_count"].tolist() == [2, 3, 4, 5]


def test_default_bar_mode_matches_explicit_legacy_mode():
    df = _ohlcv(12)
    signals = _signal_df(*[_touch_signal(i, i) for i in range(10)])
    kwargs = dict(
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
    default = run_walk_forward_sl_tp(**kwargs)
    explicit = run_walk_forward_sl_tp(
        **kwargs,
        fold_mode="bars",
        window_mode="rolling",
    )
    pd.testing.assert_frame_equal(default, explicit)


def test_walk_forward_propagates_fixed_intrabar_model_to_train_and_oos():
    df = _ohlcv(8)
    signals = _signal_df(*[_touch_signal(i, i) for i in range(6)])
    results = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        intrabar_model="path_open_proximity",
    )
    assert not results.empty
    assert set(results["intrabar_model"]) == {"path_open_proximity"}


def test_detailed_session_result_stitches_non_overlapping_oos_equity():
    df = _session_ohlcv(6)
    detailed = run_walk_forward_sl_tp(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=1,
        test_bars=1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=1,
        step_sessions=1,
        return_result=True,
    )
    assert isinstance(detailed, WalkForwardResult)
    assert detailed.schema_version == 2
    assert detailed.summary["stitched_oos_status"] == "ok"
    assert detailed.summary["stitched_oos_trade_count"] == len(detailed.oos_trades)
    assert len(detailed.stitched_equity) == len(detailed.oos_trades)
    if not detailed.oos_trades.empty:
        assert detailed.summary["stitched_oos_total_r"] == pytest.approx(
            detailed.oos_trades["r_multiple"].sum()
        )


def test_overlapping_oos_windows_require_explicit_ownership_policy():
    df = _session_ohlcv(8)
    common = dict(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=1,
        test_bars=1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=2,
        step_sessions=1,
        return_result=True,
    )
    rejected = run_walk_forward_sl_tp(**common, overlap_policy="reject")
    omitted = run_walk_forward_sl_tp(**common)
    assert omitted.config["overlap_policy"] == "reject"
    assert rejected.summary["stitched_oos_status"] == "overlapping_oos_windows"
    assert omitted.summary["stitched_oos_status"] == "overlapping_oos_windows"
    assert rejected.stitched_equity.empty
    assert rejected.summary["stitched_oos_trade_count"] == 0
    assert not rejected.oos_trades.empty
    assert "test_start_session_date" in rejected.oos_trades.columns
    assert not rejected.oos_trades["trade_id"].duplicated().any()
    assert (
        "OOS windows overlap; stitched equity is unavailable under overlap_policy='reject'."
        in rejected.warnings
    )
    # S5 identity: reject withholds the stitch; the fold-sum is still computed.
    assert rejected.summary["aggregate_test_total_r"] is not None
    assert rejected.summary["stitched_oos_total_r"] is None
    first = run_walk_forward_sl_tp(**common, overlap_policy="first")
    last = run_walk_forward_sl_tp(**common, overlap_policy="last")
    assert first.summary["stitched_oos_status"] == "ok"
    assert last.summary["stitched_oos_status"] == "ok"
    assert first.summary["stitched_oos_trade_count"] > 0
    assert last.summary["stitched_oos_trade_count"] > 0
    assert first.summary["stitched_oos_trade_count"] == len(first.oos_trades)
    first_sorted = first.oos_trades.sort_values(
        ["exit_timestamp", "entry_timestamp", "signal_id", "fold_id"],
        kind="mergesort",
    )
    assert list(first.oos_trades["signal_id"]) == list(first_sorted["signal_id"])
    assert not first.oos_trades.duplicated(["global_entry_bar_index", "signal_id"]).any()
    assert not first.oos_trades["trade_id"].duplicated().any()
    # overlap_policy does not change the fold-sum (reject ≠ first stitch).
    assert first.summary["aggregate_test_total_r"] == rejected.summary["aggregate_test_total_r"]
    assert last.summary["aggregate_test_total_r"] == rejected.summary["aggregate_test_total_r"]


def test_session_future_shock_does_not_change_existing_folds():
    original = _session_ohlcv(6)
    future = _session_ohlcv(8)
    original_results = run_walk_forward_sl_tp(
        original,
        _session_signals(original),
        TICK,
        POINT,
        [4],
        [8],
        1,
        1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=1,
    )
    future_results = run_walk_forward_sl_tp(
        future,
        _session_signals(future),
        TICK,
        POINT,
        [4],
        [8],
        1,
        1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=1,
    )
    pd.testing.assert_frame_equal(
        original_results,
        future_results.iloc[: len(original_results)].reset_index(drop=True),
    )


def test_wfa_matrix_is_deterministic_and_tidy():
    df = _session_ohlcv(8)
    kwargs = dict(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_session_values=[3, 2, 2],
        test_session_values=[2, 1],
    )
    first = run_wfa_matrix(**kwargs)
    second = run_wfa_matrix(**kwargs)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 4
    assert first[["train_sessions", "test_sessions"]].values.tolist() == [
        [2, 1],
        [2, 2],
        [3, 1],
        [3, 2],
    ]
    with pytest.raises(ValueError, match="matrix_metric"):
        run_wfa_matrix(**kwargs, matrix_metric="not_a_metric")


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
    assert row["test_sharpe_like_r"] == pytest.approx(summary["sharpe_like_r"])
    assert row["test_ulcer_index_r"] == pytest.approx(summary["ulcer_index_r"])
    assert row["test_recovery_factor"] == pytest.approx(summary["recovery_factor"])


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
    assert ok["median_test_sharpe_like_r"] is None
    assert ok["median_test_sortino_like_r"] is None
    assert ok["median_test_ulcer_index_r"] is None


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
    assert (
        summarize_walk_forward(with_cost)["aggregate_test_total_r"]
        < summarize_walk_forward(zero_cost)["aggregate_test_total_r"]
    )


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
    assert (
        summarize_walk_forward(single_position)["aggregate_test_trade_count"]
        <= summarize_walk_forward(allow_all)["aggregate_test_trade_count"]
    )


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


# ---------------------------------------------------------------------------
# B-4 / QI-11-04 — own-file assertion depth (mutation survivors)
# ---------------------------------------------------------------------------


def test_retention_ratio_is_test_over_positive_train_expectancy():
    """``train_expectancy > 1e-12`` computes retention; non-positive train does not."""
    df = _ohlcv(12)
    signals = _signal_df(*[_touch_signal(i, i) for i in range(10)])
    profitable = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        return_result=True,
    )
    ok_rows = profitable.folds[profitable.folds["ratio_status"] == "ok"]
    assert not ok_rows.empty
    for row in ok_rows.itertuples():
        assert float(row.train_expectancy_r) > 1e-12
        expected = float(row.test_expectancy_r) / float(row.train_expectancy_r)
        assert row.retention_ratio_expectancy == pytest.approx(expected)
        assert row.degradation_pct_expectancy == pytest.approx(expected - 1.0)
    assert profitable.summary["median_retention_ratio_expectancy"] == pytest.approx(
        float(ok_rows["retention_ratio_expectancy"].median())
    )

    expensive = run_walk_forward_sl_tp(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        commission_per_side=10_000.0,
    )
    scored = expensive.dropna(subset=["train_expectancy_r", "test_expectancy_r"])
    assert not scored.empty
    assert (scored["train_expectancy_r"] <= 1e-12).all()
    assert (scored["ratio_status"] == "nonpositive_or_undefined_is").all()
    assert scored["retention_ratio_expectancy"].isna().all()


def test_otf_history_policy_fold_local_is_omitted_default():
    """Own-file lock: omitted ``otf_history_policy`` ≡ explicit ``fold_local``."""
    assert normalize_otf_history_policy(None) == "fold_local"
    assert normalize_otf_history_policy("fold_local") == "fold_local"
    assert normalize_otf_history_policy("causal_prefix") == "causal_prefix"
    with pytest.raises(ValueError, match="causal_prefix"):
        normalize_otf_history_policy("any")

    start = pd.Timestamp("2026-01-05 22:00:00", tz=TZ)
    rows = []
    price = 100.0
    for i in range(80):
        ts = start + pd.Timedelta(minutes=i)
        rows.append(
            {
                "timestamp": ts,
                "open": price + 0.2,
                "high": price + 1.0,
                "low": price,
                "close": price + 0.6,
                "volume": 100.0,
            }
        )
        price += 0.05
    ohlcv = pd.DataFrame(rows)
    signals = _signal_df(
        {
            **_touch_signal(1, 40),
            "timestamp": pd.Timestamp("2026-01-05 22:40:00", tz=TZ),
        }
    )
    otf = normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    common = dict(
        df=ohlcv,
        signals=signals,
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=20,
        test_bars=20,
        step_bars=20,
        otf_config=otf,
        session_timezone=TZ,
        eth_start="18:00",
        return_result=True,
    )
    implicit = run_walk_forward_sl_tp(**common)
    explicit = run_walk_forward_sl_tp(**common, otf_history_policy="fold_local")
    assert implicit.config["otf_history_policy"] == "fold_local"
    assert explicit.config["otf_history_policy"] == "fold_local"
    pd.testing.assert_frame_equal(implicit.folds, explicit.folds)


def test_otf_history_policy_causal_prefix_uses_prefix_bars():
    """``fold_local`` is fold-slice only; ``causal_prefix`` is prefix ∪ fold."""
    start = pd.Timestamp("2026-01-05 22:00:00", tz=TZ)
    rows = []
    price = 100.0
    for i in range(90):
        ts = start + pd.Timedelta(minutes=i)
        rows.append(
            {
                "timestamp": ts,
                "open": price + 0.2,
                "high": price + 1.0,
                "low": price,
                "close": price + 0.6,
                "volume": 100.0,
            }
        )
        price += 0.05
    ohlcv = pd.DataFrame(rows)
    fold_start, fold_end = 40, 60
    fold_signals = _signal_df(
        {
            **_touch_signal(7, 0),
            "timestamp": pd.Timestamp("2026-01-05 22:40:00", tz=TZ),
        }
    )
    otf = normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    local_source = _otf_source_for_fold(
        ohlcv,
        fold_start=fold_start,
        fold_end_exclusive=fold_end,
        otf_history_policy="fold_local",
    )
    prefix_source = _otf_source_for_fold(
        ohlcv,
        fold_start=fold_start,
        fold_end_exclusive=fold_end,
        otf_history_policy="causal_prefix",
    )
    assert len(local_source) == fold_end - fold_start
    assert len(prefix_source) == fold_end
    assert len(prefix_source) > len(local_source)
    assert prefix_source["timestamp"].iloc[-1] == local_source["timestamp"].iloc[-1]
    assert prefix_source["timestamp"].iloc[0] < local_source["timestamp"].iloc[0]

    local_accepted, local_rejected, _ = _filter_fold_signals_with_otf(
        source_df=local_source,
        fold_signals=fold_signals,
        otf_config=otf,
        session_timezone=TZ,
        eth_start="18:00",
    )
    prefix_accepted, prefix_rejected, _ = _filter_fold_signals_with_otf(
        source_df=prefix_source,
        fold_signals=fold_signals,
        otf_config=otf,
        session_timezone=TZ,
        eth_start="18:00",
    )
    assert local_accepted.empty
    assert local_rejected == 1
    assert len(prefix_accepted) == 1
    assert prefix_rejected == 0
    assert int(prefix_accepted.iloc[0]["signal_id"]) == 7


def test_session_fold_uses_executable_entry_ownership(monkeypatch):
    """``fold_mode==sessions`` passes executable next-bar ownership into the slice."""
    touch = _signal_df(_touch_signal(1, 2))
    session_idx = _actionable_index_column(touch, executable_entry_ownership=True)
    bar_idx = _actionable_index_column(touch, executable_entry_ownership=False)
    assert int(session_idx.iloc[0]) == 3
    assert int(bar_idx.iloc[0]) == 2

    seen: list[bool] = []
    real = walk_forward_mod._slice_signals

    def _capture(*args, **kwargs):
        seen.append(bool(kwargs.get("executable_entry_ownership")))
        return real(*args, **kwargs)

    monkeypatch.setattr(walk_forward_mod, "_slice_signals", _capture)
    df = _session_ohlcv(6)
    run_walk_forward_sl_tp(
        df=df,
        signals=_session_signals(df),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=1,
        test_bars=1,
        fold_mode="sessions",
        train_sessions=2,
        test_sessions=1,
        step_sessions=1,
    )
    assert seen
    assert all(seen)
    seen.clear()
    bar_df = _ohlcv(12)
    run_walk_forward_sl_tp(
        df=bar_df,
        signals=_signal_df(*[_touch_signal(i, i) for i in range(10)]),
        tick_size=TICK,
        point_value=POINT,
        stop_loss_ticks_values=[4],
        take_profit_ticks_values=[8],
        train_bars=4,
        test_bars=2,
        step_bars=2,
        fold_mode="bars",
    )
    assert seen
    assert not any(seen)
