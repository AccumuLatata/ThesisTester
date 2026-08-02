"""Fixed research fixture for assistant/API/CLI canonical-hash parity.

The dataset matches the established CLI 14-bar ES minute fixture. The RunSpec
adds only the explicit cost/session fields required by the canonical assistant
compiler so confirmed assistant runs remain API-valid without silent defaults.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

PARITY_RUN_NAME = "assistant_parity"
PARITY_INSTRUMENT = "ES"
PARITY_SOURCE_TIMEZONE = "America/New_York"


def write_parity_bars(path: str | Path) -> Path:
    """Write the fixed 14-bar ES minute CSV used by CLI parity tests."""
    output = Path(path)
    timestamps = pd.date_range("2026-06-01 09:30", periods=14, freq="1min")
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [100.5] * len(timestamps),
            "low": [99.5] * len(timestamps),
            "close": [100.25 if i % 2 == 0 else 99.75 for i in range(len(timestamps))],
            "volume": [100 + i for i in range(len(timestamps))],
        }
    ).to_csv(output, index=False)
    return output


def parity_run_spec(
    *,
    dataset_path: str,
    name: str = PARITY_RUN_NAME,
) -> dict[str, Any]:
    """Return one complete, deterministic RunSpec for parity comparisons."""
    return {
        "name": name,
        "dataset": {
            "path": dataset_path,
            "instrument": PARITY_INSTRUMENT,
            "source_timezone": PARITY_SOURCE_TIMEZONE,
        },
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
            "vwap_windows": [],
            "poc_windows": [],
        },
        "setup": {
            "name": name,
            "description": "Assistant/API/CLI parity fixture",
            "instrument": PARITY_INSTRUMENT,
            "selected_levels": ["dOpen", "RTH_Open"],
            "tolerance_ticks": 0,
            "min_confluences": 2,
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
            "stop_loss_ticks": 2,
            "take_profit_ticks": 3,
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
            "flat_by_session_close": False,
            "session_close_time": None,
            "session_timezone": None,
            "no_new_entries_after": None,
        },
        "grid": {
            "stop_loss_ticks_values": [2, 3],
            "take_profit_ticks_values": [3],
            "ranking_metric": "expectancy_r",
            "min_trades": 1,
        },
        "validation": {
            "n_bootstrap": 50,
            "n_permutations": 50,
            "random_state": 11,
            "monte_carlo": {
                "enabled": True,
                "n_simulations": 20,
                "random_state": 11,
            },
        },
    }


def parity_cli_experiment(*, relative_dataset: str = "bars.csv") -> dict[str, Any]:
    """Return a version-1 CLI experiment mapping for the fixed parity fixture."""
    return {
        "schema_version": 1,
        "runs": [parity_run_spec(dataset_path=relative_dataset, name=PARITY_RUN_NAME)],
    }


def absolute_parity_run_spec(root: Path, *, name: str = PARITY_RUN_NAME) -> dict[str, Any]:
    """Return a path-contained assistant RunSpec rooted at ``root``."""
    return parity_run_spec(dataset_path=str((root / "bars.csv").resolve()), name=name)


def clone_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy so tests never mutate the shared fixture object."""
    return deepcopy(spec)
