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
    # Desk preference 4/8/10. Day=1 was a TV3 Quantower row-size trial, not
    # a QT day lock (4-tick still misses session-20 POC by a zone). Week /
    # month stay 8/10. Kwargs remain prior_*_aggregation_ticks.
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
    "prev30m_vwap_enabled": True,
    "prev30m_vwap_validity_periods": 1,
}

# First-class but omitted from product DEFAULT_LEVELS_SETTINGS.
# APOC and rolling POC: omitted key is tick Last×Volume via
# attach_apoc_identity / attach_rolling_poc_identity (not typical).
# Production value for either key is tick_last_volume_v1 only.
OPTIONAL_LEVELS_SETTINGS: frozenset[str] = frozenset(
    {"apoc_profile_source", "rolling_poc_profile_source"}
)

# Unordered list fields: order is not semantically meaningful for identity.
# Shared by ``normalize_levels_config`` and the Levels page snapshot path
# (QI-02-04 / D-6). Not a third default table — these are the list-valued
# keys already in ``DEFAULT_LEVELS_SETTINGS``.
LEVELS_SORT_KEYS = (
    "sma_lengths",
    "ema_lengths",
    "sma_timeframes",
    "ema_timeframes",
    "vwap_windows",
    "poc_windows",
    "pivot_timeframes",
)


def canonicalize_levels_list_fields(settings: dict[str, Any]) -> dict[str, Any]:
    """Sort the same unordered list keys as ``normalize_levels_config``.

    Mutates ``settings`` in place and returns it. List and tuple values are
    replaced with a new sorted list. Other types are left unchanged so the
    page/snapshot path can keep extra or malformed keys without raising.
    """
    for key in LEVELS_SORT_KEYS:
        value = settings.get(key)
        if isinstance(value, list):
            settings[key] = sorted(value)
        elif isinstance(value, tuple):
            settings[key] = sorted(list(value))
    return settings
