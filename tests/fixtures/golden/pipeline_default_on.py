"""B-3 default-on branch pipelines — isolated from the legacy family."""

from __future__ import annotations

from typing import Any

import pandas as pd

from thesistester.engine.backtest import simulate_trades

from .generate_default_on import (
    TIMEZONE,
    generate_be_dataset,
    generate_be_trail_signal,
    generate_flatten_on_dataset,
    generate_flatten_on_signals,
    generate_opposite_direction_legacy_dataset,
    generate_opposite_direction_legacy_signals,
    generate_three_c_sl_first_dataset,
    generate_three_c_sl_first_signals,
    generate_trail_dataset,
    generate_trail_signal,
)

_BASE = {
    "tick_size": 0.25,
    "point_value": 20.0,
    "stop_loss_ticks": 8.0,
    "take_profit_ticks": 16.0,
    "allow_same_bar_exit": True,
    "commission_per_side": 0.0,
    "slippage_ticks": 0.0,
    "exposure_policy": "allow_all",
    "cooldown_bars_after_exit": 0,
}

FLATTEN_ON_CONFIG: dict[str, Any] = {
    **_BASE,
    "tick_size": 0.25,
    "point_value": 50.0,
    "stop_loss_ticks": 100,
    "take_profit_ticks": 100,
    "flat_by_session_close": True,
    "session_close_time": "16:00",
    "session_timezone": TIMEZONE,
}

THREE_C_SL_FIRST_CONFIG: dict[str, Any] = {
    **_BASE,
    "tick_size": 1.0,
    "point_value": 1.0,
    "stop_loss_ticks": 2,
    "take_profit_ticks": 4,
    "intrabar_model": "sl_first",
}

BE_CONFIG: dict[str, Any] = {
    **_BASE,
    "tick_size": 1.0,
    "point_value": 1.0,
    "stop_loss_ticks": 2,
    "take_profit_ticks": 4,
    "breakeven_after_r": 1.0,
}

TRAIL_CONFIG: dict[str, Any] = {
    **_BASE,
    "tick_size": 1.0,
    "point_value": 1.0,
    "stop_loss_ticks": 2,
    "take_profit_ticks": 4,
    "trailing_after_r": 1.0,
    "trailing_distance_ticks": 2,
}

OPPOSITE_DIRECTION_LEGACY_CONFIG: dict[str, Any] = {
    **_BASE,
    "tick_size": 0.25,
    "point_value": 50.0,
    "stop_loss_ticks": 8,
    "take_profit_ticks": 8,
    "same_bar_opposite_direction": "legacy",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value


def run_flatten_on_pipeline() -> dict[str, Any]:
    data = generate_flatten_on_dataset()
    signals = generate_flatten_on_signals()
    result = simulate_trades(data, signals, return_result=True, **FLATTEN_ON_CONFIG)
    skipped = result.skipped_signals
    projection = {
        "family": "flatten_on",
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()],
        "exit_reasons": [str(v) for v in result.trades["exit_reason"].tolist()],
        "skip_reasons": [str(v) for v in skipped["skip_reason"].tolist()]
        if skipped is not None and not skipped.empty
        else [],
        "skip_signal_ids": [int(v) for v in skipped["signal_id"].tolist()]
        if skipped is not None and not skipped.empty
        else [],
        "flat_by_session_close": True,
        "session_close_time": "16:00",
    }
    return {
        "data": data,
        "signals": signals,
        "trades": result.trades,
        "skipped_signals": skipped,
        "projection": projection,
    }


def run_three_c_sl_first_pipeline() -> dict[str, Any]:
    data = generate_three_c_sl_first_dataset()
    signals = generate_three_c_sl_first_signals()
    result = simulate_trades(data, signals, return_result=True, **THREE_C_SL_FIRST_CONFIG)
    filled = signals[signals["status"] == "filled"]
    void = signals[signals["status"] == "void"]
    skipped = result.skipped_signals
    projection = {
        "family": "three_c_sl_first",
        "intrabar_model": "sl_first",
        "filled_signal_ids": [int(v) for v in filled["signal_id"].tolist()],
        "void_signal_ids": [int(v) for v in void["signal_id"].tolist()],
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()],
        "exit_reasons": [str(v) for v in result.trades["exit_reason"].tolist()],
        "theoretical_exit_prices": [
            float(v) for v in result.trades["theoretical_exit_price"].tolist()
        ],
        # 3c-void-no-skip (§5.3 item 22): void is silent — no skip row.
        "skip_signal_ids": [int(v) for v in skipped["signal_id"].tolist()]
        if skipped is not None and not skipped.empty
        else [],
        "skip_reasons": [str(v) for v in skipped["skip_reason"].tolist()]
        if skipped is not None and not skipped.empty
        else [],
    }
    return {
        "data": data,
        "signals": signals,
        "trades": result.trades,
        "skipped_signals": result.skipped_signals,
        "projection": projection,
    }


def run_be_pipeline() -> dict[str, Any]:
    data = generate_be_dataset()
    signals = generate_be_trail_signal()
    result = simulate_trades(data, signals, return_result=True, **BE_CONFIG)
    projection = {
        "family": "be_trail",
        "scenario": "breakeven",
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()],
        "exit_reasons": [str(v) for v in result.trades["exit_reason"].tolist()],
        "be_exit_count": int(result.exit_management_diagnostic["be_exit_count"]),
    }
    return {
        "data": data,
        "signals": signals,
        "trades": result.trades,
        "projection": projection,
        "diagnostic": _json_safe(result.exit_management_diagnostic),
    }


def run_trail_pipeline() -> dict[str, Any]:
    data = generate_trail_dataset()
    signals = generate_trail_signal()
    result = simulate_trades(data, signals, return_result=True, **TRAIL_CONFIG)
    projection = {
        "family": "be_trail",
        "scenario": "trail",
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()],
        "exit_reasons": [str(v) for v in result.trades["exit_reason"].tolist()],
        "trail_exit_count": int(result.exit_management_diagnostic["trail_exit_count"]),
    }
    return {
        "data": data,
        "signals": signals,
        "trades": result.trades,
        "projection": projection,
        "diagnostic": _json_safe(result.exit_management_diagnostic),
    }


def run_opposite_direction_legacy_pipeline(
    *,
    same_bar_opposite_direction: str | None = "legacy",
) -> dict[str, Any]:
    data = generate_opposite_direction_legacy_dataset()
    signals = generate_opposite_direction_legacy_signals()
    kwargs = dict(OPPOSITE_DIRECTION_LEGACY_CONFIG)
    if same_bar_opposite_direction is None:
        kwargs.pop("same_bar_opposite_direction")
    else:
        kwargs["same_bar_opposite_direction"] = same_bar_opposite_direction
    result = simulate_trades(data, signals, return_result=True, **kwargs)
    diagnostic = _json_safe(result.direction_collision_diagnostic)
    projection = {
        "family": "opposite_direction_legacy",
        "same_bar_opposite_direction": kwargs.get("same_bar_opposite_direction", "omitted"),
        "accepted_signal_ids": [int(v) for v in result.trades["signal_id"].tolist()],
        "directions": [str(v) for v in result.trades["direction"].tolist()],
        "candidate_pairs": int(diagnostic.get("candidate_pairs", 0)),
        "policy": diagnostic.get("policy"),
    }
    return {
        "data": data,
        "signals": signals,
        "trades": result.trades,
        "skipped_signals": result.skipped_signals,
        "projection": projection,
        "diagnostic": diagnostic,
    }
