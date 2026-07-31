"""Typed, Streamlit-free facade for the ThesisTester research pipeline.

The functions in this module only compose existing level, signal, engine, and
analytics functions. They intentionally contain no alternative trading logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, TypedDict

import pandas as pd

from thesistester.analytics import (
    best_grid_result,
    equity_curve,
    excursion_summary,
    monte_carlo_summary,
    run_sl_tp_grid,
    summarize_trades,
    validation_summary,
)
from thesistester.config import INSTRUMENTS
from thesistester.data.loader import format_interval, load_ohlcv, validate_ohlcv
from thesistester.data.sessions import tag_session
from thesistester.engine import (
    apply_configured_otf_filter,
    detect_anchor_confluence_zones,
    detect_confluence_zones,
    flag_naked_levels,
    generate_signals as _generate_signals,
    simulate_trades,
)
from thesistester.levels.all import compute_all_levels
from thesistester.levels.sessions import compute_session_levels
from thesistester.persistence.local_store import (
    compute_dataset_id,
    compute_signal_settings_hash,
)
from thesistester.setup import build_setup_config, validate_setup_config


class LevelsResult(TypedDict):
    """Plain-data handoff from level computation."""

    levels: pd.DataFrame
    session_levels: pd.DataFrame
    levels_settings: dict[str, Any]


class SignalsResult(TypedDict):
    """Plain-data handoff from signal generation."""

    signals: pd.DataFrame
    confluence_zones: pd.DataFrame
    naked_flags: pd.DataFrame
    signal_settings: dict[str, Any]
    signal_settings_hash: str


class BacktestResult(TypedDict):
    """Plain-data handoff from one fixed-SL/TP backtest."""

    trades: pd.DataFrame
    trade_summary: dict[str, Any]
    equity_curve: pd.DataFrame
    skipped_signals: pd.DataFrame
    accepted_signals: pd.DataFrame
    rejected_signals: pd.DataFrame
    otf_filter_summary: dict[str, Any]


class GridResult(TypedDict):
    """Plain-data handoff from an SL/TP grid."""

    grid_results: pd.DataFrame
    best_grid_result: dict[str, Any] | None
    accepted_signals: pd.DataFrame
    rejected_signals: pd.DataFrame
    otf_filter_summary: dict[str, Any]


class ValidationResult(TypedDict, total=False):
    """Plain-data handoff from the configured validation battery."""

    validation_summary: dict[str, Any]
    excursion_summary: dict[str, Any]
    excursion_config: dict[str, Any]
    excursion_grouped_summary: pd.DataFrame
    excursion_calibration_grid: pd.DataFrame
    excursion_quadrant_summary: pd.DataFrame
    monte_carlo_summary: dict[str, Any]
    monte_carlo_config: dict[str, Any]


_LEVEL_DEFAULTS: dict[str, Any] = {
    "opening_range_minutes": 30,
    "sma_lengths": [20, 50, 200],
    "ema_lengths": [20, 50, 200],
    "sma_timeframes": ["1min"],
    "ema_timeframes": ["1min"],
    "vwap_windows": ["1h", "4h", "1D"],
    "poc_windows": ["1h", "4h", "1D"],
    "value_area_pct": 0.70,
    "prior_day_profile_aggregation_ticks": 1,
    "prior_week_profile_aggregation_ticks": 1,
    "prior_month_profile_aggregation_ticks": 1,
    "pivots_enabled": False,
    "pivot_timeframes": ["1min", "5min", "30min", "4h"],
    "pivot_left": 2,
    "pivot_right": 2,
    "session_vwap_enabled": False,
    "session_vwap_anchor": "RTH",
    "single_prints_enabled": False,
    "apoc_enabled": False,
}
_LEVEL_ARGUMENT_MAP = {
    "prior_day_profile_aggregation_ticks": "prior_day_aggregation_ticks",
    "prior_week_profile_aggregation_ticks": "prior_week_aggregation_ticks",
    "prior_month_profile_aggregation_ticks": "prior_month_aggregation_ticks",
}
_BACKTEST_DEFAULTS: dict[str, Any] = {
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
_GRID_DEFAULTS: dict[str, Any] = {
    "stop_loss_ticks_values": [4.0, 8.0, 12.0],
    "take_profit_ticks_values": [8.0, 16.0, 24.0],
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
    "ranking_metric": "expectancy_r",
    "min_trades": 1,
}
_VALIDATION_DEFAULTS: dict[str, Any] = {
    "n_bootstrap": 2000,
    "n_permutations": 5000,
    "confidence": 0.95,
    "random_state": 42,
    "min_trades_soft": 30,
    "min_trades_hard": 100,
    "selected_grid_metric": "expectancy_r",
}


def _instrument(instrument: str):
    try:
        return INSTRUMENTS[instrument]
    except KeyError as exc:
        raise ValueError(f"Unsupported instrument: {instrument!r}") from exc


def _merge_known(
    defaults: Mapping[str, Any],
    config: Mapping[str, Any] | None,
    *,
    section: str,
) -> dict[str, Any]:
    raw = dict(config or {})
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"Unknown {section} configuration keys: {unknown}")
    return {**defaults, **raw}


def load_dataset(
    path: str | Path,
    *,
    instrument: str = "ES",
    source_timezone: str | None = None,
    exchange_timezone: str | None = None,
) -> pd.DataFrame:
    """Load, validate, and session-tag one canonical CSV dataset."""
    inst = _instrument(instrument)
    target_timezone = exchange_timezone or inst.exchange_tz
    data = load_ohlcv(
        Path(path),
        source_tz=source_timezone or target_timezone,
        target_tz=target_timezone,
    )
    report = validate_ohlcv(data)
    fatal_codes = {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
    fatal_messages = [issue.message for issue in report.issues if issue.code in fatal_codes]
    if fatal_messages:
        raise ValueError("Dataset validation failed: " + "; ".join(fatal_messages))
    return tag_session(data, instrument)


def compute_levels(
    data: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
) -> LevelsResult:
    """Compute UI-equivalent levels without reading or writing session state."""
    _instrument(instrument)
    settings = _merge_known(_LEVEL_DEFAULTS, config, section="levels")
    settings["instrument"] = instrument
    for key in (
        "sma_lengths",
        "ema_lengths",
        "sma_timeframes",
        "ema_timeframes",
        "vwap_windows",
        "poc_windows",
        "pivot_timeframes",
    ):
        settings[key] = sorted(list(settings[key]))

    kwargs = {
        _LEVEL_ARGUMENT_MAP.get(key, key): value
        for key, value in settings.items()
        if key != "instrument"
    }
    levels = compute_all_levels(data, instrument=instrument, **kwargs)
    session_levels = compute_session_levels(
        data,
        instrument=instrument,
        opening_range_minutes=int(settings["opening_range_minutes"]),
    )
    return {
        "levels": levels,
        "session_levels": session_levels,
        "levels_settings": settings,
    }


def build_setup(config: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate a setup using the same library contract as the UI."""
    try:
        setup = build_setup_config(**dict(config))
    except TypeError as exc:
        raise ValueError(f"Invalid setup configuration: {exc}") from exc
    errors = validate_setup_config(setup)
    if errors:
        raise ValueError("Invalid setup configuration: " + "; ".join(errors))
    return setup


def generate_signals(
    levels: pd.DataFrame,
    setup: Mapping[str, Any],
    *,
    instrument: str | None = None,
) -> SignalsResult:
    """Generate zones, naked flags, and candidate signals from one setup."""
    setup_config = dict(setup)
    errors = validate_setup_config(setup_config)
    if errors:
        raise ValueError("Invalid setup configuration: " + "; ".join(errors))
    instrument_name = instrument or str(setup_config.get("instrument", "ES"))
    inst = _instrument(instrument_name)
    mode = str(setup_config.get("confluence_mode", "global_cluster"))
    selected_levels = list(setup_config.get("selected_levels", []))

    if mode == "global_cluster":
        zones = detect_confluence_zones(
            levels,
            level_columns=selected_levels,
            tick_size=inst.tick_size,
            tolerance_ticks=float(setup_config["tolerance_ticks"]),
            min_confluences=int(setup_config["min_confluences"]),
            max_confluences=int(setup_config["max_confluences"]),
        )
        naked_level_columns = selected_levels
    elif mode == "anchor_rules":
        anchor_level = str(setup_config.get("anchor_level") or "")
        rules = list(setup_config.get("confluence_rules", []))
        referenced = [anchor_level, *(str(rule.get("level", "")) for rule in rules)]
        missing = sorted({column for column in referenced if column not in levels.columns})
        if missing:
            raise ValueError(f"Setup references unavailable level columns: {missing}")
        zones = detect_anchor_confluence_zones(
            levels,
            anchor_level=anchor_level,
            confluence_rules=rules,
            tick_size=inst.tick_size,
            min_valid_confluences=int(setup_config.get("min_valid_confluences", 1)),
        )
        naked_level_columns = list(dict.fromkeys(referenced))
    else:
        raise ValueError(f"Unsupported confluence mode: {mode!r}")

    naked_flags = flag_naked_levels(
        levels,
        level_columns=naked_level_columns,
        tick_size=inst.tick_size,
        touch_tolerance_ticks=0,
    )
    trigger_params = dict(setup_config.get("trigger_params") or {})
    if setup_config["trigger"] == "3c":
        trigger_params["_source_mode"] = mode
    signals = _generate_signals(
        levels,
        zones=zones,
        trigger=str(setup_config["trigger"]),
        direction=str(setup_config["direction"]),
        tick_size=inst.tick_size,
        trigger_timeframe=str(setup_config.get("trigger_timeframe", "base")),
        trigger_params=trigger_params,
        naked_only=bool(setup_config.get("naked_only", False)),
        naked_flags=naked_flags if setup_config.get("naked_only", False) else None,
        naked_requirement=str(setup_config.get("naked_requirement", "any")),
    )
    signals = signals.copy()
    signals["setup_name"] = setup_config.get("name", "Untitled setup")
    signal_settings = {
        "confluence_mode": mode,
        "selected_levels": selected_levels,
        "anchor_level": setup_config.get("anchor_level"),
        "confluence_rules": list(setup_config.get("confluence_rules", [])),
        "min_valid_confluences": int(setup_config.get("min_valid_confluences", 1)),
        "tolerance_ticks": float(setup_config.get("tolerance_ticks", 0.0)),
        "min_confluences": int(setup_config.get("min_confluences", 1)),
        "max_confluences": int(setup_config.get("max_confluences", 5)),
        "naked_only": bool(setup_config.get("naked_only", False)),
        "naked_requirement": str(setup_config.get("naked_requirement", "any")),
        "trigger": str(setup_config["trigger"]),
        "trigger_timeframe": str(setup_config.get("trigger_timeframe", "base")),
        "direction": str(setup_config["direction"]),
        "trigger_params": dict(setup_config.get("trigger_params") or {}),
        "use_saved_setup": True,
        "setup_snapshot": setup_config,
        "otf_filter": setup_config.get("otf_filter"),
    }
    return {
        "signals": signals,
        "confluence_zones": zones,
        "naked_flags": naked_flags,
        "signal_settings": signal_settings,
        "signal_settings_hash": compute_signal_settings_hash(signal_settings),
    }


def run_backtest(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any] | None = None,
    signal_settings: Mapping[str, Any] | None = None,
) -> BacktestResult:
    """Run the UI backtest composition, including the shared OTF pre-filter."""
    inst = _instrument(instrument)
    settings = _merge_known(_BACKTEST_DEFAULTS, config, section="backtest")
    session_timezone = settings["session_timezone"] or inst.exchange_tz
    otf = apply_configured_otf_filter(
        source_df=data,
        candidate_signals=signals,
        setup_config=dict(setup_config or {}),
        session_timezone=inst.exchange_tz,
        eth_start=inst.eth_start,
        signal_settings=dict(signal_settings or {}),
        last_signal_setup=dict(setup_config or {}),
    )
    trades, skipped = simulate_trades(
        df=data,
        signals=otf.accepted_signals,
        tick_size=inst.tick_size,
        point_value=inst.point_value,
        stop_loss_ticks=settings["stop_loss_ticks"],
        take_profit_ticks=settings["take_profit_ticks"],
        max_holding_bars=settings["max_holding_bars"],
        allow_same_bar_exit=bool(settings["allow_same_bar_exit"]),
        commission_per_side=float(settings["commission_per_side"]),
        slippage_ticks=float(settings["slippage_ticks"]),
        flat_by_session_close=bool(settings["flat_by_session_close"]),
        session_close_time=settings["session_close_time"],
        session_timezone=session_timezone if settings["flat_by_session_close"] else None,
        no_new_entries_after=settings["no_new_entries_after"],
        exposure_policy=str(settings["exposure_policy"]),
        cooldown_bars_after_exit=int(settings["cooldown_bars_after_exit"]),
        return_skipped_signals=True,
    )
    return {
        "trades": trades,
        "trade_summary": summarize_trades(trades),
        "equity_curve": equity_curve(trades),
        "skipped_signals": skipped,
        "accepted_signals": otf.accepted_signals,
        "rejected_signals": otf.rejected_signals,
        "otf_filter_summary": otf.to_summary_dict(),
    }


def run_grid(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str = "ES",
    config: Mapping[str, Any] | None = None,
    setup_config: Mapping[str, Any] | None = None,
    signal_settings: Mapping[str, Any] | None = None,
) -> GridResult:
    """Run the UI grid composition, including one shared OTF pre-filter."""
    inst = _instrument(instrument)
    settings = _merge_known(_GRID_DEFAULTS, config, section="grid")
    session_timezone = settings["session_timezone"] or inst.exchange_tz
    otf = apply_configured_otf_filter(
        source_df=data,
        candidate_signals=signals,
        setup_config=dict(setup_config or {}),
        session_timezone=inst.exchange_tz,
        eth_start=inst.eth_start,
        signal_settings=dict(signal_settings or {}),
        last_signal_setup=dict(setup_config or {}),
    )
    grid = run_sl_tp_grid(
        df=data,
        signals=otf.accepted_signals,
        tick_size=inst.tick_size,
        point_value=inst.point_value,
        stop_loss_ticks_values=list(settings["stop_loss_ticks_values"]),
        take_profit_ticks_values=list(settings["take_profit_ticks_values"]),
        max_holding_bars=settings["max_holding_bars"],
        allow_same_bar_exit=bool(settings["allow_same_bar_exit"]),
        commission_per_side=float(settings["commission_per_side"]),
        slippage_ticks=float(settings["slippage_ticks"]),
        flat_by_session_close=bool(settings["flat_by_session_close"]),
        session_close_time=settings["session_close_time"],
        session_timezone=session_timezone if settings["flat_by_session_close"] else None,
        no_new_entries_after=settings["no_new_entries_after"],
        exposure_policy=str(settings["exposure_policy"]),
        cooldown_bars_after_exit=int(settings["cooldown_bars_after_exit"]),
    )
    best = best_grid_result(
        grid,
        metric=str(settings["ranking_metric"]),
        min_trades=int(settings["min_trades"]),
    )
    return {
        "grid_results": grid,
        "best_grid_result": None if best is None else best.to_dict(),
        "accepted_signals": otf.accepted_signals,
        "rejected_signals": otf.rejected_signals,
        "otf_filter_summary": otf.to_summary_dict(),
    }


def run_validation(
    trades: pd.DataFrame,
    *,
    grid: pd.DataFrame | None = None,
    tick_size: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Run deterministic validation plus optional R10/R11 diagnostics."""
    raw = dict(config or {})
    excursion_config = raw.pop("excursion", None)
    monte_carlo_config = raw.pop("monte_carlo", None)
    settings = _merge_known(_VALIDATION_DEFAULTS, raw, section="validation")
    result: ValidationResult = {
        "validation_summary": validation_summary(trades, grid=grid, **settings)
    }

    if isinstance(excursion_config, Mapping) and excursion_config.get("enabled", True):
        if tick_size is None:
            raise ValueError("tick_size is required when excursion validation is enabled")
        excursion_settings = {
            key: value for key, value in excursion_config.items() if key != "enabled"
        }
        excursion = excursion_summary(trades, tick_size, **excursion_settings)
        result.update(
            {
                "excursion_summary": excursion,
                "excursion_config": excursion["config"],
                "excursion_grouped_summary": pd.DataFrame(excursion["grouped"]),
                "excursion_calibration_grid": pd.DataFrame(excursion["calibration_grid"]),
                "excursion_quadrant_summary": pd.DataFrame(excursion["quadrants"]),
            }
        )

    if isinstance(monte_carlo_config, Mapping) and monte_carlo_config.get("enabled", True):
        monte_carlo_settings = {
            key: value for key, value in monte_carlo_config.items() if key != "enabled"
        }
        monte_carlo = monte_carlo_summary(trades, **monte_carlo_settings)
        result.update(
            {
                "monte_carlo_summary": monte_carlo,
                "monte_carlo_config": monte_carlo["config"],
            }
        )
    return result


def run_experiment(
    spec: Mapping[str, Any],
    *,
    base_directory: str | Path = ".",
) -> dict[str, Any]:
    """Execute one version-1 experiment and return a bundle-ready plain dict."""
    run = dict(spec)
    dataset_config = dict(run.get("dataset") or {})
    if "path" not in dataset_config:
        raise ValueError("Experiment dataset.path is required")
    instrument = str(dataset_config.get("instrument", "ES"))
    inst = _instrument(instrument)
    dataset_path = Path(dataset_config["path"])
    if not dataset_path.is_absolute():
        dataset_path = Path(base_directory) / dataset_path
    source_timezone = dataset_config.get("source_timezone") or inst.exchange_tz
    exchange_timezone = dataset_config.get("exchange_timezone") or inst.exchange_tz
    data = load_dataset(
        dataset_path,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    validation_report = validate_ohlcv(data)
    base_interval = format_interval(validation_report.inferred_interval)
    dataset_id = compute_dataset_id(
        data,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )

    level_result = compute_levels(data, instrument=instrument, config=run.get("levels"))
    setup = build_setup(dict(run.get("setup") or {}))
    signal_result = generate_signals(level_result["levels"], setup, instrument=instrument)
    backtest_config = dict(run.get("backtest") or {})
    backtest_result = run_backtest(
        level_result["levels"],
        signal_result["signals"],
        instrument=instrument,
        config=backtest_config,
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
    )

    state: dict[str, Any] = {
        "data": data,
        "dataset_id": dataset_id,
        "instrument": instrument,
        "base_interval": base_interval,
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        **level_result,
        "levels_data_fingerprint": {
            "instrument": instrument,
            "rows": len(data),
            "timestamp_min": str(data["timestamp"].min()) if not data.empty else None,
            "timestamp_max": str(data["timestamp"].max()) if not data.empty else None,
            "columns": sorted(data.columns),
            "base_interval": base_interval,
            "source_timezone": source_timezone,
            "exchange_timezone": exchange_timezone,
        },
        "setup_config": setup,
        **signal_result,
        "last_signal_setup": setup,
        "signal_context": {
            "setup_name": setup["name"],
            "confluence_mode": setup["confluence_mode"],
            "setup_caption": None,
        },
        "trades": backtest_result["trades"],
        "trade_summary": backtest_result["trade_summary"],
        "equity_curve": backtest_result["equity_curve"],
        "backtest_otf_filter": backtest_result["otf_filter_summary"],
        "backtest_execution_costs": {
            "commission_per_side": float(backtest_config.get("commission_per_side", 0.0)),
            "slippage_ticks": float(backtest_config.get("slippage_ticks", 0.0)),
        },
    }

    grid_config = run.get("grid")
    if isinstance(grid_config, Mapping) and grid_config.get("enabled", True):
        grid_settings = {key: value for key, value in grid_config.items() if key != "enabled"}
        grid_result = run_grid(
            level_result["levels"],
            signal_result["signals"],
            instrument=instrument,
            config=grid_settings,
            setup_config=setup,
            signal_settings=signal_result["signal_settings"],
        )
        state.update(
            {
                "grid_results": grid_result["grid_results"],
                "best_grid_result": grid_result["best_grid_result"],
                "grid_otf_filter": grid_result["otf_filter_summary"],
            }
        )

    validation_config = run.get("validation")
    if isinstance(validation_config, Mapping) and validation_config.get("enabled", True):
        validation_settings = {
            key: value for key, value in validation_config.items() if key != "enabled"
        }
        state.update(
            run_validation(
                backtest_result["trades"],
                grid=state.get("grid_results"),
                tick_size=inst.tick_size,
                config=validation_settings,
            )
        )
    return state
