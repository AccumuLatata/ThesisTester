"""Enabled-OTF golden pipeline — isolated from the legacy golden pipeline."""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.engine.backtest import simulate_trades
from thesistester.engine.otf_integration import apply_configured_otf_filter
from thesistester.setup import normalize_otf_filter_config

from .generate_otf_enabled import (
    ETH_START,
    INSTRUMENT,
    TIMEZONE,
    generate_otf_enabled_dataset,
    generate_otf_enabled_signals,
    otf_enabled_setup_config,
)

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


def run_otf_enabled_pipeline(
    data: pd.DataFrame | None = None,
    *,
    signals: pd.DataFrame | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Apply configured OTF then simulate trades on accepted signals.

    When ``enabled=False``, uses the same candidates with OTF disabled so the
    disabled path can be compared against the legacy golden pipeline isolation
    guarantee (this pipeline still does not mutate legacy artifacts).
    """
    source = generate_otf_enabled_dataset() if data is None else data
    candidates = generate_otf_enabled_signals(source) if signals is None else signals
    setup = otf_enabled_setup_config()
    if not enabled:
        setup = {
            **setup,
            "otf_filter": normalize_otf_filter_config(None),
        }

    otf = apply_configured_otf_filter(
        source_df=source,
        candidate_signals=candidates,
        setup_config=setup,
        signal_settings={"otf_filter": setup["otf_filter"]},
        session_timezone=TIMEZONE,
        eth_start=ETH_START,
    )
    trades = simulate_trades(source, otf.accepted_signals, **BACKTEST_CONFIG)
    summary = otf.to_summary_dict()
    projection = {
        "otf_filter_config": summary["otf_filter_config"],
        "otf_algorithm_version": summary["otf_algorithm_version"],
        "otf_config_hash": summary["otf_config_hash"],
        "session_timezone": summary["session_timezone"],
        "eth_start": summary["eth_start"],
        "candidate_signal_count": summary["candidate_signal_count"],
        "otf_accepted_signal_count": summary["otf_accepted_signal_count"],
        "otf_rejected_signal_count": summary["otf_rejected_signal_count"],
        "rejection_rate": summary["rejection_rate"],
        "accepted_signal_ids": [int(value) for value in otf.accepted_signals["signal_id"].tolist()],
        "rejected_signal_ids": [int(value) for value in otf.rejected_signals["signal_id"].tolist()],
        "rejection_reasons": {
            str(int(row.signal_id)): row.otf_filter_reason
            for row in otf.rejected_signals.itertuples(index=False)
        },
        "trade_count": int(len(trades)),
        "instrument": INSTRUMENT,
    }
    return {
        "data": source,
        "candidate_signals": otf.candidate_signals,
        "accepted_signals": otf.accepted_signals,
        "rejected_signals": otf.rejected_signals,
        "trades": trades,
        "otf_summary": summary,
        "projection": projection,
    }
