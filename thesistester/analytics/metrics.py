"""Phase 5 analytics — trade summary metrics and equity curve.

All calculations operate on the trade DataFrame produced by
:func:`~thesistester.engine.backtest.simulate_trades`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_trades(trades: pd.DataFrame) -> dict:
    """Compute performance metrics for a completed trade set.

    Parameters
    ----------
    trades:
        Output of :func:`~thesistester.engine.backtest.simulate_trades`.
        May be empty.

    Returns
    -------
    dict
        Performance metrics.  All values are ``None`` / 0 / 0.0 when
        *trades* is empty so callers can always display something.
    """
    empty: dict = {
        "trade_count": 0,
        "win_rate": None,
        "loss_rate": None,
        "avg_r": None,
        "median_r": None,
        "total_r": None,
        "profit_factor": None,
        "avg_win_r": None,
        "avg_loss_r": None,
        "max_drawdown_r": None,
        "expectancy_r": None,
        "best_trade_r": None,
        "worst_trade_r": None,
    }

    if trades is None or trades.empty:
        return empty

    r = trades["r_multiple"].dropna()
    n = len(r)
    if n == 0:
        return empty

    wins = r[r > 0]
    losses = r[r < 0]

    win_rate = len(wins) / n
    loss_rate = len(losses) / n
    avg_r = float(r.mean())
    median_r = float(r.median())
    total_r = float(r.sum())

    gross_win = float(wins.sum()) if len(wins) > 0 else 0.0
    gross_loss = float(losses.sum()) if len(losses) > 0 else 0.0
    if gross_loss < 0:
        profit_factor = gross_win / abs(gross_loss)
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    avg_win_r = float(wins.mean()) if len(wins) > 0 else None
    avg_loss_r = float(losses.mean()) if len(losses) > 0 else None

    # Expectancy: win_rate * avg_win_r + loss_rate * avg_loss_r
    if avg_win_r is not None and avg_loss_r is not None:
        expectancy_r = win_rate * avg_win_r + loss_rate * avg_loss_r
    else:
        expectancy_r = avg_r

    # Max drawdown on cumulative R curve
    cum_r = r.cumsum().values
    running_max = np.maximum.accumulate(cum_r)
    drawdowns = running_max - cum_r
    max_drawdown_r = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0

    return {
        "trade_count": n,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "avg_r": avg_r,
        "median_r": median_r,
        "total_r": total_r,
        "profit_factor": profit_factor,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "max_drawdown_r": max_drawdown_r,
        "expectancy_r": expectancy_r,
        "best_trade_r": float(r.max()),
        "worst_trade_r": float(r.min()),
    }


def equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    """Build a cumulative-R equity curve from a trade set.

    Parameters
    ----------
    trades:
        Output of :func:`~thesistester.engine.backtest.simulate_trades`.

    Returns
    -------
    pd.DataFrame
        Columns: ``trade_id``, ``exit_timestamp``, ``r_multiple``,
        ``cum_r``, ``drawdown_r``.
        Returns an empty DataFrame with those columns when *trades* is empty.
    """
    cols = ["trade_id", "exit_timestamp", "r_multiple", "cum_r", "drawdown_r"]
    if trades is None or trades.empty:
        return pd.DataFrame(columns=cols)

    t = trades[["trade_id", "exit_timestamp", "r_multiple"]].copy()
    t = t.sort_values("exit_timestamp").reset_index(drop=True)

    t["cum_r"] = t["r_multiple"].cumsum()

    running_max = t["cum_r"].cummax()
    t["drawdown_r"] = running_max - t["cum_r"]

    return t[cols]
