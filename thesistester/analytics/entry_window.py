"""Post-hoc Focus helpers for entry windows (SW1) + re-exports (C1).

Admission/normalize/contains live in :mod:`thesistester.entry_window_policy`
so the engine can import them without circular imports through analytics.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics.metrics import (
    equity_curve,
    summarize_trades,
    summarize_trades_by_direction,
)
from thesistester.analytics.time_analysis import add_time_buckets
from thesistester.entry_window_policy import (
    RTH_SEGMENT_LABELS,
    RTH_SEGMENTS,
    disabled_entry_window,
    entry_window_contains,
    entry_window_from_bucket,
    format_entry_window_label,
    normalize_entry_window,
    rth_segment_for_minute,
)

FOCUS_HONESTY_BANNER = (
    "Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run."
)
FOCUS_EQUITY_CAVEAT = "Equity/drawdown rebuilt from the filtered trade subset only (subset replay)."


def filter_trades_by_entry_window(
    trades: pd.DataFrame | None,
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    timestamp_col: str = "entry_timestamp",
    bucket_tz: str | None = None,
) -> pd.DataFrame:
    """Return trades whose entry timestamp falls inside *entry_window*."""
    if trades is None:
        return pd.DataFrame()

    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    if trades.empty or not window["enabled"]:
        return trades.copy()

    if timestamp_col not in trades.columns:
        raise ValueError(f"trades missing required column {timestamp_col!r}.")

    working = trades
    if window["mode"] == "rth_segments":
        if "entry_rth_segment" not in working.columns:
            working = add_time_buckets(
                working,
                timestamp_col=timestamp_col,
                exchange_tz=exchange_tz,
                bucket_tz=bucket_tz or exchange_tz,
                session_tz=exchange_tz,
            )
        mask = working["entry_rth_segment"].isin(window["rth_segments"])
        return working.loc[mask].copy()

    # clock_range — reuse shared membership predicate (C2–C5).
    mask = working[timestamp_col].map(
        lambda ts: entry_window_contains(ts, window, exchange_tz=exchange_tz)
    )
    return working.loc[mask.astype(bool)].copy()


def focus_provenance(
    entry_window: dict[str, Any] | None,
    *,
    trade_count_before: int,
    trade_count_after: int,
    min_trades: int = 10,
    exchange_tz: str = "America/New_York",
) -> dict[str, Any]:
    """Build Focus metadata for banners / export (includes sample_warning)."""
    window = normalize_entry_window(entry_window, exchange_tz=exchange_tz)
    after = int(trade_count_after)
    return {
        "mode": "focus",
        "entry_window": window,
        "trade_count_before": int(trade_count_before),
        "trade_count_after": after,
        "sample_warning": bool(window["enabled"] and after < int(min_trades)),
        "min_trades": int(min_trades),
        "honesty_banner": FOCUS_HONESTY_BANNER,
        "equity_caveat": FOCUS_EQUITY_CAVEAT,
        "subset_replay_equity": True,
    }


def summarize_focused_trades(
    trades: pd.DataFrame | None,
    entry_window: dict[str, Any] | None,
    *,
    exchange_tz: str = "America/New_York",
    timestamp_col: str = "entry_timestamp",
    bucket_tz: str | None = None,
    min_trades: int = 10,
    include_direction: bool = True,
) -> dict[str, Any]:
    """Filter trades and compute full summary + equity for Focus (SW1)."""
    before = 0 if trades is None else int(len(trades))
    focused = filter_trades_by_entry_window(
        trades,
        entry_window,
        exchange_tz=exchange_tz,
        timestamp_col=timestamp_col,
        bucket_tz=bucket_tz,
    )
    summary = summarize_trades(focused)
    curve = equity_curve(focused)
    provenance = focus_provenance(
        entry_window,
        trade_count_before=before,
        trade_count_after=int(len(focused)),
        min_trades=min_trades,
        exchange_tz=exchange_tz,
    )
    result: dict[str, Any] = {
        "focused_trades": focused,
        "focused_trade_summary": summary,
        "focused_equity_curve": curve,
        "focus_provenance": provenance,
        "focus_entry_window": normalize_entry_window(entry_window, exchange_tz=exchange_tz),
    }
    if include_direction:
        result["focused_direction_summary"] = summarize_trades_by_direction(focused)
    return result


__all__ = [
    "FOCUS_EQUITY_CAVEAT",
    "FOCUS_HONESTY_BANNER",
    "RTH_SEGMENT_LABELS",
    "RTH_SEGMENTS",
    "disabled_entry_window",
    "entry_window_contains",
    "entry_window_from_bucket",
    "filter_trades_by_entry_window",
    "focus_provenance",
    "format_entry_window_label",
    "normalize_entry_window",
    "rth_segment_for_minute",
    "summarize_focused_trades",
]
