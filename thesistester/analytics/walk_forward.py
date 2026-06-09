"""Walk-forward / out-of-sample diagnostics for SL/TP selection."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .grid import best_grid_result, run_sl_tp_grid
from .metrics import summarize_trades
from ..engine.backtest import simulate_trades


_RESULT_COLUMNS = [
    "fold_id",
    "train_start_bar",
    "train_end_bar",
    "test_start_bar",
    "test_end_bar",
    "status",
    "selected_stop_loss_ticks",
    "selected_take_profit_ticks",
    "selected_metric_name",
    "selected_train_metric_value",
    "train_trade_count",
    "train_expectancy_r",
    "train_total_r",
    "train_profit_factor",
    "train_win_rate",
    "test_trade_count",
    "test_expectancy_r",
    "test_total_r",
    "test_profit_factor",
    "test_win_rate",
    "test_max_drawdown_r",
    "degradation_expectancy_r",
    "is_oos_profitable",
    "ranking_metric",
    "min_train_trades",
    "train_bars",
    "test_bars",
    "step_bars",
    "exposure_policy",
    "cooldown_bars_after_exit",
    "commission_per_side",
    "slippage_ticks",
    "flat_by_session_close",
    "session_close_time",
    "session_timezone",
    "no_new_entries_after",
]


def _actionable_index_column(signals: pd.DataFrame) -> pd.Series:
    has_entry = "entry_bar_index" in signals.columns
    if has_entry:
        entry = pd.to_numeric(signals["entry_bar_index"], errors="coerce")
        if entry.notna().any():
            fallback = pd.to_numeric(signals["bar_index"], errors="coerce")
            return entry.where(entry.notna(), fallback)
    return pd.to_numeric(signals["bar_index"], errors="coerce")


def _slice_signals(
    signals: pd.DataFrame,
    start_bar: int,
    end_bar_exclusive: int,
    n_slice_bars: int,
) -> pd.DataFrame:
    if signals is None:
        return pd.DataFrame()
    if signals.empty:
        return signals.iloc[0:0].copy()

    actionable = _actionable_index_column(signals)
    mask = actionable.ge(start_bar) & actionable.lt(end_bar_exclusive)
    sliced = signals.loc[mask].copy()
    if sliced.empty:
        return sliced

    sliced["bar_index"] = pd.to_numeric(sliced["bar_index"], errors="coerce") - start_bar
    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        sliced["entry_bar_index"] = entry - start_bar

    valid = sliced["bar_index"].notna()
    valid &= sliced["bar_index"].ge(0) & sliced["bar_index"].lt(n_slice_bars)

    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        trigger = sliced.get("trigger", pd.Series(index=sliced.index, dtype=object)).astype(str)
        requires_entry = trigger.eq("3c")
        entry_valid = entry.ge(0) & entry.lt(n_slice_bars)
        valid &= (~requires_entry) | entry_valid

    sliced = sliced.loc[valid].copy()
    if sliced.empty:
        return sliced

    sliced["bar_index"] = sliced["bar_index"].astype(int)
    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        has_entry = entry.notna()
        sliced.loc[has_entry, "entry_bar_index"] = entry.loc[has_entry].astype(int)

    return sliced.reset_index(drop=True)


def run_walk_forward_sl_tp(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks_values: list[int | float],
    take_profit_ticks_values: list[int | float],
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    ranking_metric: str = "expectancy_r",
    min_train_trades: int = 1,
    max_holding_bars: int | None = None,
    allow_same_bar_exit: bool = True,
    commission_per_side: float = 0.0,
    slippage_ticks: float = 0.0,
    flat_by_session_close: bool = False,
    session_close_time: str | None = None,
    session_timezone: str | None = None,
    no_new_entries_after: str | None = None,
    exposure_policy: str = "allow_all",
    cooldown_bars_after_exit: int = 0,
) -> pd.DataFrame:
    """Run deterministic bar-window walk-forward diagnostics for SL/TP selection."""
    if train_bars <= 0:
        raise ValueError("train_bars must be > 0.")
    if test_bars <= 0:
        raise ValueError("test_bars must be > 0.")

    step = test_bars if step_bars is None else int(step_bars)
    if step <= 0:
        raise ValueError("step_bars must be > 0.")

    n_bars = int(len(df))
    fold_rows: list[dict[str, Any]] = []
    fold_id = 0
    train_start = 0

    while True:
        train_end_exclusive = train_start + int(train_bars)
        test_start = train_end_exclusive
        test_end_exclusive = test_start + int(test_bars)
        if test_end_exclusive > n_bars:
            break

        train_df = df.iloc[train_start:train_end_exclusive].reset_index(drop=True)
        test_df = df.iloc[test_start:test_end_exclusive].reset_index(drop=True)
        train_signals = _slice_signals(
            signals=signals,
            start_bar=train_start,
            end_bar_exclusive=train_end_exclusive,
            n_slice_bars=len(train_df),
        )
        test_signals = _slice_signals(
            signals=signals,
            start_bar=test_start,
            end_bar_exclusive=test_end_exclusive,
            n_slice_bars=len(test_df),
        )

        train_grid = run_sl_tp_grid(
            df=train_df,
            signals=train_signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks_values=stop_loss_ticks_values,
            take_profit_ticks_values=take_profit_ticks_values,
            max_holding_bars=max_holding_bars,
            allow_same_bar_exit=allow_same_bar_exit,
            commission_per_side=commission_per_side,
            slippage_ticks=slippage_ticks,
            flat_by_session_close=flat_by_session_close,
            session_close_time=session_close_time,
            session_timezone=session_timezone,
            no_new_entries_after=no_new_entries_after,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
        )
        best_train = best_grid_result(
            train_grid,
            metric=ranking_metric,
            min_trades=min_train_trades,
        )

        row: dict[str, Any] = {
            "fold_id": int(fold_id),
            "train_start_bar": int(train_start),
            "train_end_bar": int(train_end_exclusive - 1),
            "test_start_bar": int(test_start),
            "test_end_bar": int(test_end_exclusive - 1),
            "status": "ok",
            "selected_stop_loss_ticks": None,
            "selected_take_profit_ticks": None,
            "selected_metric_name": ranking_metric,
            "selected_train_metric_value": None,
            "train_trade_count": None,
            "train_expectancy_r": None,
            "train_total_r": None,
            "train_profit_factor": None,
            "train_win_rate": None,
            "test_trade_count": None,
            "test_expectancy_r": None,
            "test_total_r": None,
            "test_profit_factor": None,
            "test_win_rate": None,
            "test_max_drawdown_r": None,
            "degradation_expectancy_r": None,
            "is_oos_profitable": None,
            "ranking_metric": ranking_metric,
            "min_train_trades": int(min_train_trades),
            "train_bars": int(train_bars),
            "test_bars": int(test_bars),
            "step_bars": int(step),
            "exposure_policy": exposure_policy,
            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
            "commission_per_side": float(commission_per_side),
            "slippage_ticks": float(slippage_ticks),
            "flat_by_session_close": bool(flat_by_session_close),
            "session_close_time": session_close_time,
            "session_timezone": session_timezone,
            "no_new_entries_after": no_new_entries_after,
        }

        if best_train is None:
            row["status"] = "no_train_candidate"
            fold_rows.append(row)
            fold_id += 1
            train_start += step
            continue

        row["selected_stop_loss_ticks"] = best_train.get("stop_loss_ticks")
        row["selected_take_profit_ticks"] = best_train.get("take_profit_ticks")
        row["selected_train_metric_value"] = best_train.get(ranking_metric)
        row["train_trade_count"] = best_train.get("trade_count")
        row["train_expectancy_r"] = best_train.get("expectancy_r")
        row["train_total_r"] = best_train.get("total_r")
        row["train_profit_factor"] = best_train.get("profit_factor")
        row["train_win_rate"] = best_train.get("win_rate")

        test_trades = simulate_trades(
            df=test_df,
            signals=test_signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=float(best_train["stop_loss_ticks"]),
            take_profit_ticks=float(best_train["take_profit_ticks"]),
            max_holding_bars=max_holding_bars,
            allow_same_bar_exit=allow_same_bar_exit,
            commission_per_side=commission_per_side,
            slippage_ticks=slippage_ticks,
            flat_by_session_close=flat_by_session_close,
            session_close_time=session_close_time,
            session_timezone=session_timezone,
            no_new_entries_after=no_new_entries_after,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
        )
        test_summary = summarize_trades(test_trades)
        row["test_trade_count"] = test_summary.get("trade_count")
        row["test_expectancy_r"] = test_summary.get("expectancy_r")
        row["test_total_r"] = test_summary.get("total_r")
        row["test_profit_factor"] = test_summary.get("profit_factor")
        row["test_win_rate"] = test_summary.get("win_rate")
        row["test_max_drawdown_r"] = test_summary.get("max_drawdown_r")

        if row["train_expectancy_r"] is not None and row["test_expectancy_r"] is not None:
            row["degradation_expectancy_r"] = (
                float(row["test_expectancy_r"]) - float(row["train_expectancy_r"])
            )
            row["is_oos_profitable"] = bool(float(row["test_expectancy_r"]) > 0.0)

        fold_rows.append(row)
        fold_id += 1
        train_start += step

    results = pd.DataFrame(fold_rows)
    if results.empty:
        return pd.DataFrame(columns=_RESULT_COLUMNS)
    return results.reindex(columns=_RESULT_COLUMNS)


def summarize_walk_forward(results: pd.DataFrame) -> dict:
    """Return a compact JSON-safe summary for walk-forward fold results."""
    def _median_or_none(series: pd.Series) -> float | None:
        value = pd.to_numeric(series, errors="coerce").median()
        if pd.isna(value):
            return None
        return float(value)

    empty_summary = {
        "fold_count": 0,
        "valid_fold_count": 0,
        "oos_profitable_fold_count": 0,
        "oos_profitable_fold_rate": None,
        "median_train_expectancy_r": None,
        "median_test_expectancy_r": None,
        "median_degradation_expectancy_r": None,
        "aggregate_test_total_r": None,
        "aggregate_test_trade_count": 0,
        "status": "empty",
    }
    if results is None or results.empty:
        return empty_summary

    fold_count = int(len(results))
    valid = results.loc[
        (results["status"] == "ok")
        & pd.to_numeric(results["test_expectancy_r"], errors="coerce").notna()
    ].copy()
    valid_fold_count = int(len(valid))
    if valid_fold_count == 0:
        return {
            **empty_summary,
            "fold_count": fold_count,
            "status": "no_valid_folds",
        }

    oos_profitable_fold_count = int(valid["is_oos_profitable"].fillna(False).astype(bool).sum())
    aggregate_test_total_r = pd.to_numeric(valid["test_total_r"], errors="coerce").sum()
    if pd.isna(aggregate_test_total_r):
        aggregate_test_total_r = None
    else:
        aggregate_test_total_r = float(aggregate_test_total_r)
    aggregate_test_trade_count = int(
        pd.to_numeric(valid["test_trade_count"], errors="coerce").fillna(0).sum()
    )
    return {
        "fold_count": fold_count,
        "valid_fold_count": valid_fold_count,
        "oos_profitable_fold_count": oos_profitable_fold_count,
        "oos_profitable_fold_rate": float(oos_profitable_fold_count / valid_fold_count),
        "median_train_expectancy_r": _median_or_none(valid["train_expectancy_r"]),
        "median_test_expectancy_r": _median_or_none(valid["test_expectancy_r"]),
        "median_degradation_expectancy_r": _median_or_none(valid["degradation_expectancy_r"]),
        "aggregate_test_total_r": aggregate_test_total_r,
        "aggregate_test_trade_count": aggregate_test_trade_count,
        "status": "ok",
    }
