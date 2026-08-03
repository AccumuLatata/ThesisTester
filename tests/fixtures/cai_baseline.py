"""Fixed fixtures for CAI-0 classic/assistant cold-path characterization.

Two fixture sizes exist:

- ``small`` — exhaustive CI smoke fixture. Cheap levels config, no rolling POC.
- ``realistic`` — informational benchmark fixture. Two RTH sessions with one
  rolling POC window so level cost is representative of product research use.

Neither fixture is a CI wall-time gate. Correctness continues to use the
existing API/CLI/assistant parity fixture in ``assistant_parity.py``.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

CAI_INSTRUMENT = "ES"
CAI_SOURCE_TIMEZONE = "America/New_York"
CAI_FIXTURE_KIND = Literal["small", "realistic"]

# One RTH session of 1-minute bars (09:30–15:59 inclusive).
_RTH_BARS_PER_SESSION = 390


def _session_timestamps(start: str, bars: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=bars, freq="1min", tz=CAI_SOURCE_TIMEZONE)


def write_cai_bars(
    path: str | Path,
    *,
    kind: CAI_FIXTURE_KIND,
) -> Path:
    """Write deterministic 1-minute OHLCV for the selected CAI fixture size."""
    output = Path(path)
    if kind == "small":
        # One hour of RTH is enough to exercise load → levels → signals → backtest
        # without making CI smoke expensive.
        timestamps = _session_timestamps("2026-06-02 09:30", 60)
    else:
        day_one = _session_timestamps("2026-06-02 09:30", _RTH_BARS_PER_SESSION)
        day_two = _session_timestamps("2026-06-03 09:30", _RTH_BARS_PER_SESSION)
        timestamps = day_one.append(day_two)

    bars = len(timestamps)
    close = 5200.0 + np.arange(bars, dtype=float) * 0.01
    # Mild oscillation so confluence/touch paths are non-degenerate.
    wave = np.sin(np.arange(bars, dtype=float) / 7.0) * 0.5
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close + wave,
            "high": close + wave + 0.75,
            "low": close + wave - 0.75,
            "close": close + wave * 0.5,
            "volume": 100 + (np.arange(bars) % 17),
        }
    )
    frame.to_csv(output, index=False)
    return output


def cai_levels_config(*, kind: CAI_FIXTURE_KIND) -> dict[str, Any]:
    """Return an explicit levels config for the selected fixture size."""
    if kind == "small":
        # sma/ema length lists must be non-empty for validate_run_spec; rolling
        # POC and multi-TF work stay disabled so CI smoke remains cheap.
        return {
            "opening_range_minutes": 15,
            "sma_lengths": [5, 10],
            "ema_lengths": [5],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
            "vwap_windows": [],
            "poc_windows": [],
            "value_area_pct": 0.70,
            "prior_day_profile_aggregation_ticks": 4,
            "prior_week_profile_aggregation_ticks": 8,
            "prior_month_profile_aggregation_ticks": 10,
            "pivots_enabled": False,
            "pivot_timeframes": [],
            "pivot_left": 2,
            "pivot_right": 2,
            "session_vwap_enabled": True,
            "session_vwap_anchor": "RTH",
            "single_prints_enabled": False,
            "apoc_enabled": False,
        }
    return {
        "opening_range_minutes": 15,
        "sma_lengths": [20, 50],
        "ema_lengths": [9],
        "sma_timeframes": ["1min", "5min"],
        "ema_timeframes": ["1min"],
        "vwap_windows": ["30min"],
        "poc_windows": ["30min"],
        "value_area_pct": 0.70,
        "prior_day_profile_aggregation_ticks": 4,
        "prior_week_profile_aggregation_ticks": 8,
        "prior_month_profile_aggregation_ticks": 10,
        "pivots_enabled": False,
        "pivot_timeframes": [],
        "pivot_left": 2,
        "pivot_right": 2,
        "session_vwap_enabled": True,
        "session_vwap_anchor": "RTH",
        "single_prints_enabled": False,
        "apoc_enabled": False,
    }


def cai_run_spec(
    *,
    dataset_path: str,
    kind: CAI_FIXTURE_KIND,
    name: str | None = None,
) -> dict[str, Any]:
    """Return one complete RunSpec for CAI cold-path characterization."""
    run_name = name or f"cai_{kind}_baseline"
    selected_levels = (
        ["dVWAP_RTH", "SMA_5_1min"] if kind == "small" else ["dVWAP_RTH", "SMA_20_1min"]
    )
    return {
        "name": run_name,
        "dataset": {
            "path": dataset_path,
            "instrument": CAI_INSTRUMENT,
            "source_timezone": CAI_SOURCE_TIMEZONE,
            "exchange_timezone": CAI_SOURCE_TIMEZONE,
            "format_profile": "canonical",
        },
        "levels": cai_levels_config(kind=kind),
        "setup": {
            "name": run_name,
            "description": f"CAI-0 {kind} cold-path fixture",
            "instrument": CAI_INSTRUMENT,
            "selected_levels": selected_levels,
            "tolerance_ticks": 4.0,
            "min_confluences": 1,
            "max_confluences": 2,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "direction": "both",
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": {},
            "otf_filter": None,
        },
        "backtest": {
            "stop_loss_ticks": 8,
            "take_profit_ticks": 16,
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": False,
            "session_close_time": None,
            "session_timezone": CAI_SOURCE_TIMEZONE,
            "no_new_entries_after": None,
            "max_holding_bars": 30,
            "allow_same_bar_exit": True,
            "cooldown_bars_after_exit": 0,
        },
    }


def clone_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy so callers never mutate a shared fixture object."""
    return deepcopy(spec)
