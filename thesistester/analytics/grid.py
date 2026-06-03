"""Phase 6 analytics — SL/TP grid search over the Phase 5 backtest engine.

Sweeps stop-loss × take-profit combinations and returns one summary row
per grid cell.  All trade simulation is delegated to
:func:`~thesistester.engine.backtest.simulate_trades` and
:func:`~thesistester.analytics.metrics.summarize_trades` so that Phase 5
assumptions are preserved exactly.
"""
from __future__ import annotations

import pandas as pd

from thesistester.analytics.metrics import summarize_trades
from thesistester.engine.backtest import simulate_trades


def run_sl_tp_grid(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks_values: list[int | float],
    take_profit_ticks_values: list[int | float],
    max_holding_bars: int | None = None,
    allow_same_bar_exit: bool = True,
) -> pd.DataFrame:
    """Run a stop-loss × take-profit grid search.

    For every ``(stop_loss_ticks, take_profit_ticks)`` pair the function calls
    :func:`simulate_trades` and :func:`summarize_trades` and collects the
    results into a single tidy DataFrame (one row per cell).

    Parameters
    ----------
    df:
        Canonical OHLCV DataFrame passed through to ``simulate_trades``.
    signals:
        Phase 4 signal DataFrame passed through to ``simulate_trades``.
    tick_size:
        Instrument tick size (e.g. 0.25 for ES/NQ).
    point_value:
        Dollar value per point.
    stop_loss_ticks_values:
        Non-empty list of positive SL values (ticks) to sweep.
        Duplicates are dropped; values are sorted for deterministic output.
    take_profit_ticks_values:
        Non-empty list of positive TP values (ticks) to sweep.
        Duplicates are dropped; values are sorted for deterministic output.
    max_holding_bars:
        Passed through to ``simulate_trades``.
    allow_same_bar_exit:
        Passed through to ``simulate_trades``.

    Returns
    -------
    pd.DataFrame
        One row per (SL, TP) combination sorted by
        ``stop_loss_ticks``, then ``take_profit_ticks``.
        Columns: ``stop_loss_ticks``, ``take_profit_ticks``, plus all
        metrics returned by :func:`summarize_trades`, plus
        ``tp_sl_ratio``, ``risk_points``, ``target_points``.

    Raises
    ------
    ValueError
        If either list is empty, or if any SL/TP value is ≤ 0.
    """
    if not stop_loss_ticks_values:
        raise ValueError("stop_loss_ticks_values must not be empty.")
    if not take_profit_ticks_values:
        raise ValueError("take_profit_ticks_values must not be empty.")

    sl_values = sorted(set(stop_loss_ticks_values))
    tp_values = sorted(set(take_profit_ticks_values))

    for sl in sl_values:
        if sl <= 0:
            raise ValueError(
                f"All stop_loss_ticks values must be > 0; got {sl!r}."
            )
    for tp in tp_values:
        if tp <= 0:
            raise ValueError(
                f"All take_profit_ticks values must be > 0; got {tp!r}."
            )

    rows: list[dict] = []
    for sl in sl_values:
        for tp in tp_values:
            trades = simulate_trades(
                df=df,
                signals=signals,
                tick_size=tick_size,
                point_value=point_value,
                stop_loss_ticks=sl,
                take_profit_ticks=tp,
                max_holding_bars=max_holding_bars,
                allow_same_bar_exit=allow_same_bar_exit,
            )
            summary = summarize_trades(trades)
            row: dict = {
                "stop_loss_ticks": sl,
                "take_profit_ticks": tp,
                **summary,
                "tp_sl_ratio": tp / sl,
                "risk_points": sl * tick_size,
                "target_points": tp * tick_size,
            }
            rows.append(row)

    return pd.DataFrame(rows).sort_values(
        ["stop_loss_ticks", "take_profit_ticks"]
    ).reset_index(drop=True)


def best_grid_result(
    grid: pd.DataFrame,
    metric: str = "expectancy_r",
    min_trades: int = 1,
) -> pd.Series | None:
    """Return the grid row with the highest value of *metric*.

    Parameters
    ----------
    grid:
        Output of :func:`run_sl_tp_grid`.
    metric:
        Column name to rank by.  Defaults to ``"expectancy_r"``.
    min_trades:
        Minimum ``trade_count`` required for a row to be considered.

    Returns
    -------
    pd.Series or None
        The row with the highest ``metric`` value, or ``None`` if no
        valid rows exist (empty grid, all filtered by ``min_trades``,
        or all metric values are NaN).
    """
    if grid is None or grid.empty:
        return None

    filtered = grid[grid["trade_count"] >= min_trades].copy()
    if filtered.empty:
        return None

    if metric not in filtered.columns:
        return None

    filtered = filtered.dropna(subset=[metric])
    if filtered.empty:
        return None

    idx = filtered[metric].idxmax()
    return filtered.loc[idx]
