"""Standalone anchor-based confluence detection engine."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd


ANCHOR_ZONE_COLUMNS = [
    "timestamp",
    "bar_index",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "level_prices",
    "confluence_mode",
    "anchor_level",
    "anchor_price",
    "valid_confluence_count",
    "required_valid",
    "rule_results",
]


def _empty_anchor_zones_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ANCHOR_ZONE_COLUMNS)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1"}
    return bool(value)


def _safe_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(num):
        return None
    return num


def detect_anchor_confluence_zones(
    df: pd.DataFrame,
    anchor_level: str,
    confluence_rules: list[dict],
    tick_size: float,
    min_valid_confluences: int = 1,
) -> pd.DataFrame:
    """Detect per-bar confluence zones around a single anchor level."""
    if tick_size <= 0:
        raise ValueError("tick_size must be > 0")

    if not isinstance(confluence_rules, list) or not confluence_rules:
        return _empty_anchor_zones_df()

    if not isinstance(anchor_level, str) or not anchor_level.strip() or anchor_level not in df.columns:
        return _empty_anchor_zones_df()

    min_valid = max(int(min_valid_confluences), 1)
    tick = float(tick_size)

    df_reset = df.reset_index(drop=True)
    zones: list[dict[str, Any]] = []

    for bar_idx in range(len(df_reset)):
        row = df_reset.iloc[bar_idx]
        anchor_price = _safe_float(row.get(anchor_level))
        if anchor_price is None:
            continue

        rule_results: list[dict[str, Any]] = []
        valid_level_names: list[str] = []
        valid_level_prices: list[float] = []
        required_valid = True

        for raw_rule in confluence_rules:
            rule = raw_rule if isinstance(raw_rule, dict) else {}
            level = str(rule.get("level", ""))

            tolerance_raw = rule.get("tolerance_ticks", 0.0)
            try:
                tolerance_ticks = float(tolerance_raw)
            except (TypeError, ValueError):
                tolerance_ticks = 0.0

            required = _coerce_bool(rule.get("required", False))

            if level not in df_reset.columns:
                result = {
                    "level": level,
                    "price": None,
                    "tolerance_ticks": tolerance_ticks,
                    "distance_ticks": None,
                    "required": required,
                    "valid": False,
                    "reason": "missing_column",
                }
                if required:
                    required_valid = False
                rule_results.append(result)
                continue

            confluence_price = _safe_float(row.get(level))
            if confluence_price is None:
                result = {
                    "level": level,
                    "price": None,
                    "tolerance_ticks": tolerance_ticks,
                    "distance_ticks": None,
                    "required": required,
                    "valid": False,
                    "reason": "missing_price",
                }
                if required:
                    required_valid = False
                rule_results.append(result)
                continue

            distance_ticks = abs(confluence_price - anchor_price) / tick
            valid = distance_ticks <= tolerance_ticks + 1e-9
            reason = "within_tolerance" if valid else "outside_tolerance"

            result = {
                "level": level,
                "price": confluence_price,
                "tolerance_ticks": tolerance_ticks,
                "distance_ticks": distance_ticks,
                "required": required,
                "valid": valid,
                "reason": reason,
            }
            if required and not valid:
                required_valid = False

            if valid:
                valid_level_names.append(level)
                valid_level_prices.append(confluence_price)

            rule_results.append(result)

        valid_count = len(valid_level_prices)
        if not required_valid or valid_count < min_valid:
            continue

        included_names = [anchor_level, *valid_level_names]
        included_prices = [anchor_price, *valid_level_prices]

        zone_low = min(included_prices)
        zone_high = max(included_prices)

        zones.append(
            {
                "timestamp": row.get("timestamp", pd.NaT),
                "bar_index": bar_idx,
                "zone_low": zone_low,
                "zone_high": zone_high,
                "zone_mid": (zone_low + zone_high) / 2.0,
                "level_count": len(included_prices),
                "level_names": "|".join(included_names),
                "level_prices": "|".join(str(price) for price in included_prices),
                "confluence_mode": "anchor_rules",
                "anchor_level": anchor_level,
                "anchor_price": anchor_price,
                "valid_confluence_count": valid_count,
                "required_valid": required_valid,
                "rule_results": json.dumps(rule_results),
            }
        )

    if not zones:
        return _empty_anchor_zones_df()
    return pd.DataFrame(zones, columns=ANCHOR_ZONE_COLUMNS)
