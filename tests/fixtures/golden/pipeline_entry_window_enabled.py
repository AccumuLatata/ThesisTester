"""Enabled entry_window golden pipeline — isolated from the legacy family."""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.engine.backtest import simulate_trades

from .generate_entry_window_enabled import (
    ENTRY_WINDOW,
    TIMEZONE,
    generate_entry_window_enabled_dataset,
    generate_entry_window_enabled_signals,
)

BACKTEST_CONFIG: dict[str, Any] = {
    "tick_size": 0.25,
    "point_value": 20.0,
    "stop_loss_ticks": 8.0,
    "take_profit_ticks": 16.0,
    "max_holding_bars": 5,
    "allow_same_bar_exit": True,
    "commission_per_side": 0.0,
    "slippage_ticks": 0.0,
    "flat_by_session_close": False,
    "session_close_time": None,
    "session_timezone": TIMEZONE,
    "no_new_entries_after": None,
    "exposure_policy": "allow_all",
    "cooldown_bars_after_exit": 0,
}


def run_entry_window_enabled_pipeline(
    data: pd.DataFrame | None = None,
    *,
    signals: pd.DataFrame | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Simulate with entry_window enabled (or disabled for isolation checks)."""
    source = generate_entry_window_enabled_dataset() if data is None else data
    candidates = generate_entry_window_enabled_signals(source) if signals is None else signals
    window = ENTRY_WINDOW if enabled else None
    result = simulate_trades(
        source,
        candidates,
        entry_window=window,
        return_result=True,
        **BACKTEST_CONFIG,
    )
    skipped = result.skipped_signals
    window_skips = (
        skipped[skipped["skip_reason"] == "outside_entry_window"]
        if not skipped.empty and "skip_reason" in skipped.columns
        else skipped.iloc[0:0]
    )
    projection = {
        "entry_window": window,
        "session_timezone": TIMEZONE,
        "candidate_signal_count": int(len(candidates)),
        "accepted_trade_count": int(len(result.trades)),
        "outside_entry_window_skip_count": int(len(window_skips)),
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()]
        if not result.trades.empty
        else [],
        "outside_entry_window_signal_ids": [int(v) for v in window_skips["signal_id"].tolist()]
        if not window_skips.empty
        else [],
    }
    return {
        "data": source,
        "signals": candidates,
        "trades": result.trades,
        "skipped_signals": skipped,
        "projection": projection,
    }
