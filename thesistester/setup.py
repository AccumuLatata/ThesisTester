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

VALID_TRIGGERS = frozenset({"touch", "reject", "break", "reclaim", "3c"})
VALID_DIRECTIONS = frozenset({"long", "short", "both"})
VALID_CONFLUENCE_MODES = frozenset({"global_cluster", "anchor_rules"})

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

DEFAULT_3C_PARAMS: dict[str, Any] = {
    # arrival_tolerance_ticks is deprecated and no longer user-configurable.
    # Kept here only for backward-compatible parsing of old saved configs.
    "arrival_tolerance_ticks": 0.0,
    "entry_retrace_ticks": 4.0,
    "max_entry_wait_bars_after_reversal": 5,
}


def _normalize_3c_params(params: dict[str, Any] | None) -> dict[str, Any]:
    trigger_params = params or {}
    return {
        # arrival_tolerance_ticks is loaded from config for backward compat but
        # always ignored/forced to 0 in execution.
        "arrival_tolerance_ticks": 0.0,
        "entry_retrace_ticks": float(
            trigger_params.get("entry_retrace_ticks", DEFAULT_3C_PARAMS["entry_retrace_ticks"])
        ),
        "max_entry_wait_bars_after_reversal": int(
            trigger_params.get(
                "max_entry_wait_bars_after_reversal",
                DEFAULT_3C_PARAMS["max_entry_wait_bars_after_reversal"],
            )
        ),
    }


def _is_boolean_compatible(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if value in {0, 1}:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "false", "1", "0"}
    return False


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
    confluence_mode: str = "global_cluster",
    anchor_level: str | None = None,
    confluence_rules: list[dict[str, Any]] | None = None,
    min_valid_confluences: int = 1,
    trigger_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized setup configuration dictionary."""
    normalized_params = {}
    if trigger == "3c":
        normalized_params = _normalize_3c_params(trigger_params)

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
        "confluence_mode": str(confluence_mode or "global_cluster"),
        "anchor_level": anchor_level,
        "confluence_rules": list(confluence_rules or []),
        "min_valid_confluences": int(min_valid_confluences),
        "trigger_params": normalized_params,
    }


def validate_setup_config(config: dict[str, Any]) -> list[str]:
    """Validate setup config and return a list of user-facing error messages."""
    errors: list[str] = []

    name = str(config.get("name", "")).strip()
    if not name:
        errors.append("Setup name must not be empty.")

    confluence_mode = str(config.get("confluence_mode") or "global_cluster")
    if confluence_mode not in VALID_CONFLUENCE_MODES:
        errors.append(f"Confluence mode must be one of {sorted(VALID_CONFLUENCE_MODES)}.")

    naked_requirement = str(config.get("naked_requirement", "any")).lower()
    if naked_requirement not in {"any", "all"}:
        errors.append("Naked requirement must be 'any' or 'all'.")

    trigger = str(config.get("trigger", ""))
    if trigger not in VALID_TRIGGERS:
        errors.append(f"Trigger must be one of {sorted(VALID_TRIGGERS)}.")

    direction = str(config.get("direction", ""))
    if direction not in VALID_DIRECTIONS:
        errors.append(f"Direction must be one of {sorted(VALID_DIRECTIONS)}.")

    if confluence_mode == "global_cluster":
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
    elif confluence_mode == "anchor_rules":
        raw_anchor_level = config.get("anchor_level")
        anchor_level = raw_anchor_level.strip() if isinstance(raw_anchor_level, str) else ""
        if not anchor_level:
            errors.append("Anchor level must be a non-empty string.")

        confluence_rules = config.get("confluence_rules", [])
        if not isinstance(confluence_rules, list) or not confluence_rules:
            errors.append("Confluence rules must be a non-empty list.")
            confluence_rules = []

        try:
            min_valid_confluences = int(config.get("min_valid_confluences", 0))
            if min_valid_confluences < 1:
                errors.append("Minimum valid confluences must be >= 1.")
                min_valid_confluences = None
        except (TypeError, ValueError):
            min_valid_confluences = None
            errors.append("Minimum valid confluences must be an integer.")

        if min_valid_confluences is not None and min_valid_confluences > len(confluence_rules):
            errors.append("Minimum valid confluences must be <= number of confluence rules.")

        seen_levels: set[str] = set()
        for index, rule in enumerate(confluence_rules, start=1):
            if not isinstance(rule, dict):
                errors.append(f"Confluence rule {index} must be a dictionary.")
                continue

            rule_level = str(rule.get("level", "")).strip()
            if not rule_level:
                errors.append(f"Confluence rule {index} level must be a non-empty string.")
            else:
                if rule_level == anchor_level:
                    errors.append(f"Confluence rule {index} level must not equal anchor_level.")
                if rule_level in seen_levels:
                    errors.append(f"Duplicate confluence rule level '{rule_level}' is not allowed.")
                seen_levels.add(rule_level)

            try:
                rule_tolerance = float(rule.get("tolerance_ticks", 0.0))
                if rule_tolerance < 0:
                    errors.append(f"Confluence rule {index} tolerance_ticks must be >= 0.")
            except (TypeError, ValueError):
                errors.append(f"Confluence rule {index} tolerance_ticks must be a number.")

            if not _is_boolean_compatible(rule.get("required")):
                errors.append(f"Confluence rule {index} required must be boolean-compatible.")

    if trigger == "3c":
        trigger_params = config.get("trigger_params", {}) or {}
        if not isinstance(trigger_params, dict):
            errors.append("trigger_params must be a dictionary for 3c.")
        else:
            # arrival_tolerance_ticks is deprecated; no longer validated as an active parameter.
            numeric_fields = {
                "entry_retrace_ticks": trigger_params.get("entry_retrace_ticks", 0.0),
                "max_entry_wait_bars_after_reversal": trigger_params.get("max_entry_wait_bars_after_reversal", 0),
            }
            for key, raw_value in numeric_fields.items():
                try:
                    value = float(raw_value) if key != "max_entry_wait_bars_after_reversal" else int(raw_value)
                    if value < 0:
                        errors.append(f"{key} must be >= 0.")
                except (TypeError, ValueError):
                    errors.append(f"{key} must be a number.")

    return errors
