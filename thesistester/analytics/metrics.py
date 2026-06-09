"""Phase 5 analytics — trade summary metrics and equity curve.

All calculations operate on the trade DataFrame produced by
:func:`~thesistester.engine.backtest.simulate_trades`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _drawdown_series(r: pd.Series) -> pd.Series:
    """Return drawdown magnitudes from the cumulative-R equity curve."""
    cum_r = r.cumsum()
    running_max = cum_r.cummax().clip(lower=0.0)
    return running_max - cum_r


def _sample_std(series: pd.Series) -> float | None:
    """Return sample std dev or None when unavailable."""
    if len(series) < 2:
        return None
    value = series.std(ddof=1)
    return None if pd.isna(value) else float(value)


def _float_or_none(value: float | int | np.floating | None) -> float | None:
    """Return a plain float unless the value is missing/NaN."""
    if value is None or pd.isna(value):
        return None
    return float(value)


def _max_consecutive_mask(mask: pd.Series) -> int:
    """Return longest consecutive True streak in a boolean mask."""
    max_run = 0
    current = 0
    for is_match in mask.astype(bool).tolist():
        if is_match:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _empty_trade_summary() -> dict:
    return {
        "trade_count": 0,
        "win_rate": None,
        "loss_rate": None,
        "avg_r": None,
        "median_r": None,
        "std_r": None,
        "downside_std_r": None,
        "sharpe_like_r": None,
        "sortino_like_r": None,
        "total_r": None,
        "profit_factor": None,
        "expectancy_to_drawdown": None,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "avg_win_r": None,
        "avg_loss_r": None,
        "win_loss_ratio": None,
        "largest_win_r": None,
        "largest_loss_r": None,
        "p95_r": None,
        "p05_r": None,
        "tail_ratio": None,
        "trade_return_skew": None,
        "trade_return_kurtosis": None,
        "ulcer_index_r": None,
        "recovery_factor": None,
        "payoff_stability": None,
        "outlier_dependency_ratio": None,
        "max_drawdown_r": None,
        "expectancy_r": None,
        "best_trade_r": None,
        "worst_trade_r": None,
    }


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
    empty: dict = _empty_trade_summary()

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
    std_r = _sample_std(r)
    downside_std_r = _sample_std(losses)
    total_r = float(r.sum())
    p95_r = _float_or_none(r.quantile(0.95))
    p05_r = _float_or_none(r.quantile(0.05))
    skew_r = _float_or_none(r.skew()) if n >= 3 else None
    kurtosis_r = _float_or_none(r.kurt()) if n >= 4 else None

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
    drawdowns = _drawdown_series(r)
    max_drawdown_r = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0
    ulcer_index_r = (
        float(np.sqrt(np.mean(np.square(drawdowns.to_numpy(dtype=float)))))
        if len(drawdowns) > 0
        else 0.0
    )

    sharpe_like_r = (
        avg_r / std_r
        if std_r is not None and not np.isclose(std_r, 0.0)
        else None
    )
    sortino_like_r = (
        avg_r / downside_std_r
        if downside_std_r is not None and not np.isclose(downside_std_r, 0.0)
        else None
    )
    expectancy_to_drawdown = (
        total_r / max_drawdown_r
        if max_drawdown_r is not None and not np.isclose(max_drawdown_r, 0.0)
        else None
    )
    recovery_factor = expectancy_to_drawdown
    win_loss_ratio = (
        abs(avg_win_r / avg_loss_r)
        if avg_win_r is not None
        and avg_loss_r is not None
        and not np.isclose(avg_loss_r, 0.0)
        else None
    )
    tail_ratio = (
        abs(p95_r / p05_r)
        if p95_r is not None
        and p05_r is not None
        and not np.isclose(p05_r, 0.0)
        else None
    )
    mean_absolute_r = _float_or_none(r.abs().mean())
    payoff_stability = (
        median_r / mean_absolute_r
        if mean_absolute_r is not None and not np.isclose(mean_absolute_r, 0.0)
        else None
    )
    outlier_dependency_ratio = None
    if n >= 2 and not np.isclose(total_r, 0.0):
        largest_abs_idx = r.abs().sort_values(ascending=False).index[0]
        total_r_without_largest_abs = float(r.drop(index=largest_abs_idx).sum())
        outlier_dependency_ratio = total_r_without_largest_abs / total_r

    return {
        "trade_count": n,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "avg_r": avg_r,
        "median_r": median_r,
        "std_r": std_r,
        "downside_std_r": downside_std_r,
        "sharpe_like_r": sharpe_like_r,
        "sortino_like_r": sortino_like_r,
        "total_r": total_r,
        "profit_factor": profit_factor,
        "expectancy_to_drawdown": expectancy_to_drawdown,
        "max_consecutive_wins": _max_consecutive_mask(r > 0),
        "max_consecutive_losses": _max_consecutive_mask(r < 0),
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "win_loss_ratio": win_loss_ratio,
        "largest_win_r": float(r.max()),
        "largest_loss_r": float(r.min()),
        "p95_r": p95_r,
        "p05_r": p05_r,
        "tail_ratio": tail_ratio,
        "trade_return_skew": skew_r,
        "trade_return_kurtosis": kurtosis_r,
        "ulcer_index_r": ulcer_index_r,
        "recovery_factor": recovery_factor,
        "payoff_stability": payoff_stability,
        "outlier_dependency_ratio": outlier_dependency_ratio,
        "max_drawdown_r": max_drawdown_r,
        "expectancy_r": expectancy_r,
        "best_trade_r": float(r.max()),
        "worst_trade_r": float(r.min()),
    }


def summarize_trades_by_direction(trades: pd.DataFrame) -> dict[str, dict]:
    """Compute long/short trade summaries with stable output keys.

    Parameters
    ----------
    trades:
        Trade table that may contain ``direction`` and ``r_multiple`` columns.
        May be empty or ``None``.

    Returns
    -------
    dict[str, dict]
        Mapping with fixed ``"long"`` and ``"short"`` keys. Each value is the
        output of :func:`summarize_trades` for that directional subset. Missing
        or empty sides return the same safe empty-summary structure.
    """
    output: dict[str, dict] = {
        "long": _empty_trade_summary(),
        "short": _empty_trade_summary(),
    }

    if (
        trades is None
        or trades.empty
        or "direction" not in trades.columns
        or "r_multiple" not in trades.columns
    ):
        return output

    direction_series = trades["direction"].astype(str).str.lower()
    for direction in ("long", "short"):
        subset = trades[direction_series == direction]
        output[direction] = summarize_trades(subset)
    return output


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
            win_rate = float(len(wins) / n) if n > 0 else None
            loss_rate = float(len(losses) / n) if n > 0 else None
            row["win_rate"] = win_rate
            row["avg_r"] = float(r.mean()) if n > 0 else None
            avg_win_r = float(wins.mean()) if len(wins) > 0 else None
            avg_loss_r = float(losses.mean()) if len(losses) > 0 else None
            if n == 0:
                row["expectancy_r"] = None
            elif avg_win_r is not None and avg_loss_r is not None:
                row["expectancy_r"] = win_rate * avg_win_r + loss_rate * avg_loss_r
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

    t["drawdown_r"] = _drawdown_series(t["r_multiple"])

    return t[cols]
