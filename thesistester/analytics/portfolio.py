"""R21 additive multi-setup portfolio analytics over completed trade frames."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .metrics import equity_curve, summarize_trades

_EXPOSURE_POLICIES = {"allow_all", "single_position", "single_direction", "single_setup"}
_REQUIRED_COLUMNS = {
    "trade_id",
    "entry_bar_index",
    "exit_bar_index",
    "entry_timestamp",
    "exit_timestamp",
    "direction",
    "r_multiple",
}


def _empty_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "setup_id",
            "source_trade_id",
            "trade_id",
            "entry_bar_index",
            "exit_bar_index",
            "entry_timestamp",
            "exit_timestamp",
            "direction",
            "r_multiple",
        ]
    )


def tag_setup_trades(setup_trades: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Copy and deterministically tag completed trades from independent setups."""
    frames: list[pd.DataFrame] = []
    for setup_id in sorted(setup_trades):
        if not str(setup_id).strip():
            raise ValueError("Portfolio setup IDs must be non-empty.")
        trades = setup_trades[setup_id]
        if trades is None or trades.empty:
            continue
        missing = sorted(_REQUIRED_COLUMNS - set(trades.columns))
        if missing:
            raise ValueError(
                f"Portfolio setup {setup_id!r} is missing columns: {', '.join(missing)}"
            )
        frame = trades.copy(deep=True)
        frame["setup_id"] = str(setup_id)
        frame["source_trade_id"] = frame["trade_id"]
        frame["trade_id"] = [
            f"{setup_id}:{trade_id}" for trade_id in frame["source_trade_id"].astype(str)
        ]
        for column in ("entry_bar_index", "exit_bar_index"):
            numeric = pd.to_numeric(frame[column], errors="coerce")
            if numeric.isna().any() or (numeric < 0).any() or (numeric % 1 != 0).any():
                raise ValueError(f"Portfolio setup {setup_id!r} has invalid {column}.")
            frame[column] = numeric.astype(int)
        if (frame["exit_bar_index"] < frame["entry_bar_index"]).any():
            raise ValueError(f"Portfolio setup {setup_id!r} exits before entry.")
        for column in ("entry_timestamp", "exit_timestamp"):
            timestamps = pd.to_datetime(frame[column], errors="coerce", format="mixed", utc=True)
            if timestamps.isna().any():
                raise ValueError(f"Portfolio setup {setup_id!r} has invalid {column}.")
            frame[column] = timestamps
        frames.append(frame)
    if not frames:
        return _empty_candidates()
    return pd.concat(frames, ignore_index=True, sort=False)


def _validate_bar_index_bounds(candidates: pd.DataFrame, bar_count: int | None) -> None:
    if bar_count is None:
        return
    if int(bar_count) < 1:
        raise ValueError("bar_count must be >= 1 when provided.")
    if (candidates["entry_bar_index"] >= int(bar_count)).any() or (
        candidates["exit_bar_index"] >= int(bar_count)
    ).any():
        raise ValueError("Portfolio trades do not share the supplied parent bar-index range.")


def apply_portfolio_exposure(
    candidates: pd.DataFrame,
    *,
    exposure_policy: str = "allow_all",
    cooldown_bars_after_exit: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply R4-equivalent admission semantics to tagged completed trades."""
    if exposure_policy not in _EXPOSURE_POLICIES:
        raise ValueError(f"Unsupported portfolio exposure policy: {exposure_policy}")
    if int(cooldown_bars_after_exit) < 0:
        raise ValueError("cooldown_bars_after_exit must be >= 0")
    if candidates.empty:
        return candidates.copy(deep=True), pd.DataFrame(
            columns=[*candidates.columns, "skip_reason", "blocking_trade_id"]
        )
    ordered = candidates.sort_values(
        ["entry_bar_index", "setup_id", "source_trade_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    cooldown = int(cooldown_bars_after_exit)
    for row in ordered.to_dict(orient="records"):
        if exposure_policy == "allow_all":
            relevant: list[dict[str, Any]] = []
        elif exposure_policy == "single_position":
            relevant = accepted
        elif exposure_policy == "single_direction":
            relevant = [prior for prior in accepted if prior["direction"] == row["direction"]]
        else:
            relevant = [prior for prior in accepted if prior["setup_id"] == row["setup_id"]]
        blockers = [
            prior
            for prior in relevant
            if int(row["entry_bar_index"]) <= int(prior["exit_bar_index"]) + cooldown
        ]
        if not blockers:
            accepted.append(row)
            continue
        blocker = sorted(
            blockers,
            key=lambda prior: (-int(prior["exit_bar_index"]), str(prior["trade_id"])),
        )[0]
        reason = (
            "cooldown_active"
            if int(row["entry_bar_index"]) > int(blocker["exit_bar_index"])
            else f"overlapping_{exposure_policy.removeprefix('single_')}"
        )
        skipped.append(
            {
                **row,
                "skip_reason": reason,
                "blocking_trade_id": blocker["trade_id"],
                "blocking_exit_bar_index": blocker["exit_bar_index"],
            }
        )
    return pd.DataFrame(accepted, columns=ordered.columns), pd.DataFrame(skipped)


def _aligned_return_paths(candidates: pd.DataFrame, setup_ids: list[str]) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=setup_ids)
    work = candidates.copy()
    work["exit_timestamp"] = pd.to_datetime(work["exit_timestamp"], errors="coerce", format="mixed")
    work["r_multiple"] = pd.to_numeric(work["r_multiple"], errors="coerce")
    work = work.dropna(subset=["exit_timestamp", "r_multiple"])
    if work.empty:
        return pd.DataFrame(columns=setup_ids)
    paths = work.pivot_table(
        index="exit_timestamp",
        columns="setup_id",
        values="r_multiple",
        aggfunc="sum",
        fill_value=0.0,
    ).reindex(columns=setup_ids, fill_value=0.0)
    return paths.sort_index()


def setup_correlation_matrices(
    candidates: pd.DataFrame, setup_ids: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return aligned incremental-return and drawdown correlation matrices."""
    paths = _aligned_return_paths(candidates, setup_ids)
    if len(paths) < 2 or len(setup_ids) < 2:
        empty = pd.DataFrame(index=setup_ids, columns=setup_ids, dtype=float)
        return empty, empty.copy()
    returns = paths.corr()
    drawdowns = paths.cumsum().cummax().clip(lower=0.0) - paths.cumsum()
    drawdown_correlation = drawdowns.corr()
    returns.index.name = returns.columns.name = None
    drawdown_correlation.index.name = drawdown_correlation.columns.name = None
    return returns, drawdown_correlation


def portfolio_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    """Build combined R and currency equity curves from admitted trades."""
    curve = equity_curve(trades)
    if curve.empty:
        return curve.assign(cum_pnl_currency=pd.Series(dtype=float))
    work = trades.copy()
    work["exit_timestamp"] = pd.to_datetime(work["exit_timestamp"], errors="coerce", format="mixed")
    currency = (
        pd.to_numeric(work["pnl_currency"], errors="coerce").fillna(0.0)
        if "pnl_currency" in work
        else pd.Series(0.0, index=work.index)
    )
    currency_by_exit = (
        pd.DataFrame({"exit_timestamp": work["exit_timestamp"], "pnl_currency": currency})
        .groupby("exit_timestamp", as_index=False)["pnl_currency"]
        .sum()
    )
    curve = curve.merge(currency_by_exit, on="exit_timestamp", how="left")
    curve["pnl_currency"] = curve["pnl_currency"].fillna(0.0)
    curve["cum_pnl_currency"] = curve["pnl_currency"].cumsum()
    return curve


def portfolio_summary(
    setup_trades: Mapping[str, pd.DataFrame],
    *,
    instrument: str,
    exposure_policy: str = "allow_all",
    cooldown_bars_after_exit: int = 0,
    bar_count: int | None = None,
) -> dict[str, Any]:
    """Build the schema-versioned R21 portfolio artifact from independent runs."""
    if len(setup_trades) < 2:
        raise ValueError("Portfolio analysis requires at least two setup trade frames.")
    candidates = tag_setup_trades(setup_trades)
    _validate_bar_index_bounds(candidates, bar_count)
    admitted, skipped = apply_portfolio_exposure(
        candidates,
        exposure_policy=exposure_policy,
        cooldown_bars_after_exit=cooldown_bars_after_exit,
    )
    setup_ids = sorted(str(key) for key in setup_trades)
    metrics = summarize_trades(admitted)
    curve = portfolio_equity_curve(admitted)
    returns_corr, drawdown_corr = setup_correlation_matrices(candidates, setup_ids)
    contribution_rows: list[dict[str, Any]] = []
    for setup_id in setup_ids:
        without = admitted.loc[admitted["setup_id"] != setup_id].copy()
        without_metrics = summarize_trades(without)
        contribution_rows.append(
            {
                "setup_id": setup_id,
                "admitted_trade_count": int((admitted["setup_id"] == setup_id).sum()),
                "total_r_contribution": (
                    None
                    if metrics["total_r"] is None or without_metrics["total_r"] is None
                    else float(metrics["total_r"] - without_metrics["total_r"])
                ),
                "max_drawdown_r_contribution": (
                    None
                    if metrics["max_drawdown_r"] is None
                    or without_metrics["max_drawdown_r"] is None
                    else float(metrics["max_drawdown_r"] - without_metrics["max_drawdown_r"])
                ),
            }
        )
    return {
        "schema_version": 1,
        "available": not admitted.empty,
        "config": {
            "instrument": str(instrument),
            "setup_ids": setup_ids,
            "exposure_policy": exposure_policy,
            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
            "bar_count": None if bar_count is None else int(bar_count),
        },
        "admission": {
            "candidate_trade_count": int(len(candidates)),
            "admitted_trade_count": int(len(admitted)),
            "skipped_trade_count": int(len(skipped)),
            "skip_reasons": skipped.get("skip_reason", pd.Series(dtype=str))
            .value_counts()
            .to_dict(),
        },
        "portfolio_metrics": metrics,
        "per_setup_metrics": {
            setup_id: summarize_trades(admitted.loc[admitted["setup_id"] == setup_id])
            for setup_id in setup_ids
        },
        "marginal_contribution": contribution_rows,
        "correlation": {
            "returns": returns_corr.to_dict(),
            "drawdowns": drawdown_corr.to_dict(),
        },
        "caveat": (
            "Diagnostic only. This is a post-hoc merge of independent completed trades, "
            "not a continuous capital, margin, liquidity, or fill simulation."
        ),
        "portfolio_trades": admitted,
        "portfolio_skipped_trades": skipped,
        "portfolio_equity_curve": curve,
        "portfolio_correlation": returns_corr,
        "portfolio_drawdown_correlation": drawdown_corr,
        "portfolio_marginal_contribution": pd.DataFrame(contribution_rows),
    }
