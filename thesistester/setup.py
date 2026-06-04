"""Setup configuration helpers for Setup Builder and Signals pages."""
from __future__ import annotations

from typing import Any

import pandas as pd


BASE_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "session",
    "settlement",
}

VALID_TRIGGERS = frozenset({"touch", "reject", "break", "reclaim", "confirm_3bar"})
VALID_DIRECTIONS = frozenset({"long", "short", "both"})

SUGGESTED_DEFAULT_LEVELS = [
    "ONH",
    "ONL",
    "OR_High",
    "OR_Low",
    "RTH_Open",
    "pdHigh",
    "pdLow",
    "pdPOC",
    "VWAP_rolling_1h",
]

DEFAULT_CONFIRM_3BAR_PARAMS: dict[str, Any] = {
    "arrival_tolerance_ticks": 0.0,
    "activation_retrace_ticks": 4.0,
    "entry_offset_ticks": 0.0,
    "allow_equal_close": False,
}


def _normalize_confirm_3bar_params(params: dict[str, Any] | None) -> dict[str, Any]:
    trigger_params = params or {}
    activation_retrace_ticks = trigger_params.get(
        "activation_retrace_ticks",
        trigger_params.get("retrace_entry_ticks", DEFAULT_CONFIRM_3BAR_PARAMS["activation_retrace_ticks"]),
    )
    return {
        "arrival_tolerance_ticks": float(
            trigger_params.get("arrival_tolerance_ticks", DEFAULT_CONFIRM_3BAR_PARAMS["arrival_tolerance_ticks"])
        ),
        "activation_retrace_ticks": float(activation_retrace_ticks),
        "entry_offset_ticks": float(
            trigger_params.get("entry_offset_ticks", DEFAULT_CONFIRM_3BAR_PARAMS["entry_offset_ticks"])
        ),
        "allow_equal_close": bool(
            trigger_params.get("allow_equal_close", DEFAULT_CONFIRM_3BAR_PARAMS["allow_equal_close"])
        ),
    }


def available_level_columns(df: pd.DataFrame) -> list[str]:
    """Return setup-eligible level columns from *df*."""
    return [column for column in df.columns if column not in BASE_COLUMNS]


def default_selected_levels(level_columns: list[str]) -> list[str]:
    """Choose sensible default level columns."""
    preferred = [column for column in SUGGESTED_DEFAULT_LEVELS if column in level_columns]
    if preferred:
        return preferred
    return level_columns[:4]


def build_setup_config(
    *,
    name: str,
    description: str,
    instrument: str,
    selected_levels: list[str],
    tolerance_ticks: float,
    min_confluences: int,
    max_confluences: int,
    naked_only: bool,
    naked_requirement: str,
    trigger: str,
    direction: str,
    trigger_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized setup configuration dictionary."""
    normalized_params = {}
    if trigger == "confirm_3bar":
        normalized_params = _normalize_confirm_3bar_params(trigger_params)

    return {
        "name": name.strip(),
        "description": description.strip(),
        "instrument": instrument,
        "selected_levels": list(selected_levels),
        "tolerance_ticks": float(tolerance_ticks),
        "min_confluences": int(min_confluences),
        "max_confluences": int(max_confluences),
        "naked_only": bool(naked_only),
        "naked_requirement": str(naked_requirement).lower(),
        "trigger": str(trigger),
        "direction": str(direction),
        "trigger_params": normalized_params,
    }


def validate_setup_config(config: dict[str, Any]) -> list[str]:
    """Validate setup config and return a list of user-facing error messages."""
    errors: list[str] = []

    name = str(config.get("name", "")).strip()
    if not name:
        errors.append("Setup name must not be empty.")

    selected_levels = config.get("selected_levels", [])
    if not isinstance(selected_levels, list) or not selected_levels:
        errors.append("Select at least one level column.")

    try:
        tolerance_ticks = float(config.get("tolerance_ticks", 0.0))
        if tolerance_ticks < 0:
            errors.append("Tolerance ticks must be >= 0.")
    except (TypeError, ValueError):
        errors.append("Tolerance ticks must be a number.")

    try:
        min_conf = int(config.get("min_confluences", 0))
        if min_conf < 1:
            errors.append("Minimum confluences must be >= 1.")
    except (TypeError, ValueError):
        min_conf = 1
        errors.append("Minimum confluences must be an integer.")

    try:
        max_conf = int(config.get("max_confluences", 0))
    except (TypeError, ValueError):
        max_conf = 0
        errors.append("Maximum confluences must be an integer.")
    else:
        if max_conf < min_conf:
            errors.append("Maximum confluences must be >= minimum confluences.")
        if max_conf > 5:
            errors.append("Maximum confluences must be <= 5.")

    naked_requirement = str(config.get("naked_requirement", "any")).lower()
    if naked_requirement not in {"any", "all"}:
        errors.append("Naked requirement must be 'any' or 'all'.")

    trigger = str(config.get("trigger", ""))
    if trigger not in VALID_TRIGGERS:
        errors.append(f"Trigger must be one of {sorted(VALID_TRIGGERS)}.")

    direction = str(config.get("direction", ""))
    if direction not in VALID_DIRECTIONS:
        errors.append(f"Direction must be one of {sorted(VALID_DIRECTIONS)}.")

    if trigger == "confirm_3bar":
        trigger_params = config.get("trigger_params", {}) or {}
        if not isinstance(trigger_params, dict):
            errors.append("trigger_params must be a dictionary for confirm_3bar.")
        else:
            activation_retrace_ticks = trigger_params.get(
                "activation_retrace_ticks",
                trigger_params.get("retrace_entry_ticks", 0.0),
            )
            numeric_fields = {
                "arrival_tolerance_ticks": trigger_params.get("arrival_tolerance_ticks", 0.0),
                "activation_retrace_ticks": activation_retrace_ticks,
                "entry_offset_ticks": trigger_params.get("entry_offset_ticks", 0.0),
            }
            for key, raw_value in numeric_fields.items():
                try:
                    value = float(raw_value)
                    if value < 0:
                        errors.append(f"{key} must be >= 0.")
                except (TypeError, ValueError):
                    errors.append(f"{key} must be a number.")
            if "allow_equal_close" not in trigger_params:
                errors.append("allow_equal_close must be provided for confirm_3bar.")
            else:
                allow_equal_raw = trigger_params.get("allow_equal_close")
                bool_compatible = isinstance(allow_equal_raw, (bool, int))
                if not bool_compatible and isinstance(allow_equal_raw, str):
                    bool_compatible = allow_equal_raw.strip().lower() in {"true", "false", "1", "0"}
                if not bool_compatible:
                    errors.append("allow_equal_close must be boolean-compatible.")

    return errors
