"""Enabled fade golden pipeline — isolated from legacy / OTF / entry-window families."""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.engine.backtest import simulate_trades

from .generate_fade_enabled import (
    TICK_SIZE,
    TIMEZONE,
    generate_fade_enabled_dataset,
    generate_fade_enabled_signals,
)

BACKTEST_CONFIG: dict[str, Any] = {
    "tick_size": TICK_SIZE,
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
    "exposure_policy": "single_position",
    "cooldown_bars_after_exit": 0,
}


def run_fade_enabled_pipeline(
    data: pd.DataFrame | None = None,
    *,
    signals: pd.DataFrame | None = None,
) -> dict[str, Any]:
    source = generate_fade_enabled_dataset() if data is None else data
    candidates = generate_fade_enabled_signals(source) if signals is None else signals
    result = simulate_trades(
        source,
        candidates,
        return_result=True,
        **BACKTEST_CONFIG,
    )
    projection = {
        "trigger": "fade",
        "direction": "both",
        "exposure_policy": BACKTEST_CONFIG["exposure_policy"],
        "candidate_signal_count": int(len(candidates)),
        "accepted_trade_count": int(len(result.trades)),
        "accepted_signal_ids": (
            [int(v) for v in result.trades["signal_id"].tolist()] if not result.trades.empty else []
        ),
        "candidate_directions": (
            [str(v) for v in candidates["direction"].tolist()] if not candidates.empty else []
        ),
        "candidate_approach_sides": (
            [str(v) for v in candidates["approach_side"].tolist()]
            if not candidates.empty and "approach_side" in candidates.columns
            else []
        ),
        "collision_pairs": int(result.direction_collision_diagnostic["candidate_pairs"]),
    }
    return {
        "data": source,
        "signals": candidates,
        "trades": result.trades,
        "skipped_signals": result.skipped_signals,
        "direction_collision_diagnostic": result.direction_collision_diagnostic,
        "projection": projection,
    }
