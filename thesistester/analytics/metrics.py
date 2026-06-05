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

    # Max drawdown on cumulative R curve.
    # clip(lower=0.0) anchors the running peak at 0R so that a strategy that
    # starts with a loss correctly reports a drawdown from the initial zero
    # equity point rather than from the first (negative) cumulative value.
    cum_r = r.cumsum()
    running_max = cum_r.cummax().clip(lower=0.0)
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


def summarize_by_group(trades: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Compute a minimal grouped trade outcome summary."""
    requested_group_cols = list(group_cols or [])
    trade_columns = trades.columns if trades is not None else []
    available_group_cols = [col for col in requested_group_cols if col in trade_columns]
    metric_cols = [
        "trade_count",
        "win_rate",
        "expectancy_r",
        "avg_r",
        "total_pnl",
        "avg_pnl",
        "avg_bars_held",
    ]
    empty = pd.DataFrame(columns=available_group_cols + metric_cols)
    if trades is None or trades.empty:
        return empty

    pnl_col = "pnl_currency" if "pnl_currency" in trades.columns else None
    has_r = "r_multiple" in trades.columns
    has_bars_held = "bars_held" in trades.columns

    if available_group_cols:
        grouped_iter = trades.groupby(available_group_cols, sort=True, observed=True)
    else:
        grouped_iter = [((), trades)]
    rows: list[dict] = []
    for keys, group in grouped_iter:
        row: dict = {}
        if available_group_cols:
            if len(available_group_cols) == 1:
                row[available_group_cols[0]] = keys
            else:
                for col, val in zip(available_group_cols, keys):
                    row[col] = val

        row["trade_count"] = int(len(group))
        if has_r:
            r = group["r_multiple"].dropna()
            n = len(r)
            wins = r[r > 0]
            losses = r[r < 0]
            row["win_rate"] = float(len(wins) / n) if n > 0 else None
            row["avg_r"] = float(r.mean()) if n > 0 else None
            avg_win_r = float(wins.mean()) if len(wins) > 0 else None
            avg_loss_r = float(losses.mean()) if len(losses) > 0 else None
            if n == 0:
                row["expectancy_r"] = None
            elif avg_win_r is not None and avg_loss_r is not None:
                row["expectancy_r"] = row["win_rate"] * avg_win_r + (1.0 - row["win_rate"]) * avg_loss_r
            else:
                # For all-win or all-loss groups, avg_r already equals expectancy.
                row["expectancy_r"] = row["avg_r"]
        else:
            row["win_rate"] = None
            row["expectancy_r"] = None
            row["avg_r"] = None

        row["total_pnl"] = float(group[pnl_col].sum()) if pnl_col else None
        row["avg_pnl"] = float(group[pnl_col].mean()) if pnl_col else None
        row["avg_bars_held"] = float(group["bars_held"].mean()) if has_bars_held else None
        rows.append(row)

    if not rows:
        return empty

    out = pd.DataFrame(rows)
    ordered_cols = available_group_cols + metric_cols
    present_cols = [c for c in ordered_cols if c in out.columns]
    out = out[present_cols]
    return out.sort_values(available_group_cols).reset_index(drop=True) if available_group_cols else out.reset_index(drop=True)


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

    # clip(lower=0.0) anchors the running peak at 0R (initial equity) so that
    # a strategy starting with a loss correctly reports drawdown from zero.
    running_max = t["cum_r"].cummax().clip(lower=0.0)
    t["drawdown_r"] = running_max - t["cum_r"]

    return t[cols]
