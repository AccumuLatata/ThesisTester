"""Frozen legacy pipeline used by the golden recorder and verification tests."""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.analytics.metrics import equity_curve, summarize_trades
from thesistester.engine.backtest import simulate_trades
from thesistester.persistence.local_store import compute_dataset_id
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

from .generate import INSTRUMENT, TIMEZONE, generate_signals

BASE_INTERVAL = "1min"
BACKTEST_CONFIG: dict[str, Any] = {
    "tick_size": 0.25,
    "point_value": 20.0,
    "stop_loss_ticks": 8.0,
    "take_profit_ticks": 16.0,
    "max_holding_bars": None,
    "allow_same_bar_exit": True,
    "commission_per_side": 0.0,
    "slippage_ticks": 0.0,
    "flat_by_session_close": False,
    "session_close_time": None,
    "session_timezone": None,
    "no_new_entries_after": None,
    "exposure_policy": "allow_all",
    "cooldown_bars_after_exit": 0,
}


def run_legacy_pipeline(data: pd.DataFrame) -> dict[str, Any]:
    """Run current legacy defaults and return all recorded logical artifacts."""
    signals = generate_signals()
    trades = simulate_trades(data, signals, **BACKTEST_CONFIG)
    summary = summarize_trades(trades)
    curve = equity_curve(trades)
    dataset_id = compute_dataset_id(
        data,
        instrument=INSTRUMENT,
        base_interval=BASE_INTERVAL,
        source_timezone=TIMEZONE,
        exchange_timezone=TIMEZONE,
    )
    state = {
        "data": data,
        "dataset_id": dataset_id,
        "instrument": INSTRUMENT,
        "base_interval": BASE_INTERVAL,
        "source_timezone": TIMEZONE,
        "exchange_timezone": TIMEZONE,
        "trades": trades,
        "trade_summary": summary,
        "equity_curve": curve,
    }
    bundle = build_research_bundle(state)
    return {
        "signals": signals,
        "trades": trades,
        "trade_summary": summary,
        "equity_curve": curve,
        "bundle": bundle,
        "bundle_hash": canonical_bundle_hash(bundle),
        "dataset_id": dataset_id,
    }
