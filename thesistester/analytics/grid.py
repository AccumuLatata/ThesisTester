"""Phase 6 analytics — SL/TP grid search over the Phase 5 backtest engine.

Sweeps stop-loss × take-profit combinations and returns one summary row
per grid cell.  All trade simulation is delegated to
:func:`~thesistester.engine.backtest.simulate_trades` and
:func:`~thesistester.analytics.metrics.summarize_trades` so that Phase 5
assumptions are preserved exactly.

Phase 2 extends each grid row with directional (long/short) metrics and
balanced weaker-side summary columns computed from the same simulated trades.
"""
from __future__ import annotations

import pandas as pd

from thesistester.analytics.metrics import summarize_trades, summarize_trades_by_direction
from thesistester.engine.backtest import simulate_trades


# ---------------------------------------------------------------------------
# Private helpers for directional grid metrics
# ---------------------------------------------------------------------------


def _prefix_summary(summary: dict, prefix: str) -> dict:
    """Return a copy of *summary* with every key prefixed by *prefix*."""
    return {f"{prefix}{k}": v for k, v in summary.items()}


def _min_valid(a: float | None, b: float | None) -> float | None:
    """Return the minimum of two values, or ``None`` if either is ``None``."""
    if a is None or b is None:
        return None
    return min(a, b)


def _directional_grid_metrics(trades: pd.DataFrame) -> dict:
    """Compute directional and balanced metrics for a single grid cell.

    Parameters
    ----------
    trades:
        Trade table for one (SL, TP) cell from ``simulate_trades``.

    Returns
    -------
    dict
        Long columns (``long_*``), short columns (``short_*``), and balanced
        columns (``min_direction_*``).
    """
    direction_summary = summarize_trades_by_direction(trades)
    long_s = direction_summary["long"]
    short_s = direction_summary["short"]

    long_cols = _prefix_summary(
        {
            "trade_count": long_s["trade_count"],
            "win_rate": long_s["win_rate"],
            "avg_r": long_s["avg_r"],
            "expectancy_r": long_s["expectancy_r"],
            "total_r": long_s["total_r"],
            "profit_factor": long_s["profit_factor"],
            "max_drawdown_r": long_s["max_drawdown_r"],
        },
        "long_",
    )
    short_cols = _prefix_summary(
        {
            "trade_count": short_s["trade_count"],
            "win_rate": short_s["win_rate"],
            "avg_r": short_s["avg_r"],
            "expectancy_r": short_s["expectancy_r"],
            "total_r": short_s["total_r"],
            "profit_factor": short_s["profit_factor"],
            "max_drawdown_r": short_s["max_drawdown_r"],
        },
        "short_",
    )

    # Balanced / weaker-side metrics.
    # min_direction_trade_count is always numeric (0 if one side has no trades),
    # while weaker-side PF/expectancy use None when either side has no trades.
    long_pf = long_s["profit_factor"] if long_s["trade_count"] > 0 else None
    short_pf = short_s["profit_factor"] if short_s["trade_count"] > 0 else None
    long_exp = long_s["expectancy_r"] if long_s["trade_count"] > 0 else None
    short_exp = short_s["expectancy_r"] if short_s["trade_count"] > 0 else None

    balanced_cols: dict = {
        "min_direction_trade_count": min(long_s["trade_count"], short_s["trade_count"]),
        "min_direction_profit_factor": _min_valid(long_pf, short_pf),
        "min_direction_expectancy_r": _min_valid(long_exp, short_exp),
    }

    return {**long_cols, **short_cols, **balanced_cols}


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
        ``tp_sl_ratio``, ``risk_points``, ``target_points``, and
        directional columns (``long_*``, ``short_*``,
        ``min_direction_*``).

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
            directional = _directional_grid_metrics(trades)
            row: dict = {
                "stop_loss_ticks": sl,
                "take_profit_ticks": tp,
                **summary,
                "tp_sl_ratio": tp / sl,
                "risk_points": sl * tick_size,
                "target_points": tp * tick_size,
                **directional,
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
