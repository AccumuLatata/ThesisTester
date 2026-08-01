"""Canonical default configuration for the Levels page and headless API.

These defaults are intentionally distinct from the keyword defaults on
``compute_all_levels``.  The latter preserve its low-level, additive API
contract; this module defines the product configuration shown to users.
"""

from __future__ import annotations

from typing import Any


DEFAULT_LEVELS_SETTINGS: dict[str, Any] = {
    "opening_range_minutes": 15,
    "sma_lengths": [50, 200],
    "ema_lengths": [9, 21],
    "sma_timeframes": ["1min", "5min", "30min"],
    "ema_timeframes": ["1min", "5min", "30min"],
    "vwap_windows": ["30min", "4h"],
    "poc_windows": ["30min"],
    "value_area_pct": 0.70,
    "prior_day_profile_aggregation_ticks": 4,
    "prior_week_profile_aggregation_ticks": 8,
    "prior_month_profile_aggregation_ticks": 10,
    "pivots_enabled": True,
    "pivot_timeframes": ["1min", "5min", "30min", "4h"],
    "pivot_left": 2,
    "pivot_right": 2,
    "session_vwap_enabled": True,
    "session_vwap_anchor": "RTH",
    "single_prints_enabled": True,
    "apoc_enabled": True,
}
