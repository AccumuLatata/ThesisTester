"""Validation and session-state injection helpers for execution-settings defaults.

These helpers sanitize raw values loaded from the persistence layer before they
are injected into ``st.session_state``.  Invalid or stale values are silently
dropped so that each widget falls back to its built-in default.

No Streamlit import is required here — callers pass ``session_state`` explicitly,
which keeps this module testable without a running Streamlit server.
"""
from __future__ import annotations

import re
from datetime import time as _time
from typing import Any

from thesistester.config import TIMEZONE_OPTIONS

# ── Constant option sets (must stay in sync with the page widgets) ────────────

EXPOSURE_POLICY_OPTIONS: tuple[str, ...] = (
    "allow_all",
    "single_position",
    "single_direction",
    "single_setup",
)

RANKING_METRIC_OPTIONS: tuple[str, ...] = (
    "expectancy_r",
    "total_r",
    "profit_factor",
    "win_rate",
)

DIRECTIONAL_METRIC_OPTIONS: tuple[str, ...] = (
    "expectancy_r",
    "total_r",
    "profit_factor",
    "win_rate",
    "long_expectancy_r",
    "short_expectancy_r",
    "long_profit_factor",
    "short_profit_factor",
    "min_direction_expectancy_r",
    "min_direction_profit_factor",
)

_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


# ── Primitive validators ──────────────────────────────────────────────────────

def _valid_float(value: Any, *, lo: float, hi: float) -> float | None:
    """Return value converted to float if it is within [lo, hi] and not a bool, else None."""
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v < lo or v > hi:
        return None
    return v


def _valid_int(value: Any, *, lo: int, hi: int) -> int | None:
    """Return value converted to int if it is within [lo, hi] and not a bool, else None."""
    if isinstance(value, bool):
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v < lo or v > hi:
        return None
    return v


def _valid_bool(value: Any) -> bool | None:
    """Return a bool only if value is already a real Python bool."""
    if isinstance(value, bool):
        return value
    return None


def _valid_time_str(value: Any) -> str | None:
    """Return value if it is a zero-padded HH:MM or HH:MM:SS with valid ranges
    (HH: 00-23, MM: 00-59, SS: 00-59), else None."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if _TIME_RE.fullmatch(stripped) is None:
        return None
    try:
        _time.fromisoformat(stripped)
    except ValueError:
        return None
    return stripped


def _valid_optional_time_str(value: Any) -> str | None:
    """Return empty string if value is empty/None, a valid strict time string, or None (invalid)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return ""
    if _TIME_RE.fullmatch(stripped) is None:
        return None
    try:
        _time.fromisoformat(stripped)
    except ValueError:
        return None
    return stripped


def _valid_timezone(value: Any) -> str | None:
    """Return value if it is a known timezone option, else None."""
    if not isinstance(value, str):
        return None
    return value if value in TIMEZONE_OPTIONS else None


def _valid_exposure_policy(value: Any) -> str | None:
    """Return value if it is a valid exposure policy, else None."""
    if not isinstance(value, str):
        return None
    return value if value in EXPOSURE_POLICY_OPTIONS else None


def _valid_ranking_metric(value: Any) -> str | None:
    """Return value if it is a valid aggregate ranking metric, else None."""
    if not isinstance(value, str):
        return None
    return value if value in RANKING_METRIC_OPTIONS else None


def _valid_directional_metric(value: Any) -> str | None:
    """Return value if it is a valid directional ranking metric, else None."""
    if not isinstance(value, str):
        return None
    return value if value in DIRECTIONAL_METRIC_OPTIONS else None


# ── Backtest sanitisation ─────────────────────────────────────────────────────

#: Maps session-state key → (validator_fn, raw_defaults_key)
_BACKTEST_FIELD_SPECS: tuple[tuple[str, str, Any], ...] = (
    # (session_key, defaults_key, validator_fn)
    ("backtest_sl_ticks",              "sl_ticks",              lambda v: _valid_float(v, lo=1.0, hi=500.0)),
    ("backtest_tp_ticks",              "tp_ticks",              lambda v: _valid_float(v, lo=1.0, hi=1000.0)),
    ("backtest_commission_per_side",   "commission_per_side",   lambda v: _valid_float(v, lo=0.0, hi=1000.0)),
    ("backtest_slippage_ticks",        "slippage_ticks",        lambda v: _valid_float(v, lo=0.0, hi=100.0)),
    ("backtest_use_max_bars",          "use_max_bars",          _valid_bool),
    ("backtest_max_bars",              "max_bars",              lambda v: _valid_int(v, lo=1, hi=500)),
    ("backtest_allow_same_bar",        "allow_same_bar",        _valid_bool),
    ("backtest_flat_by_session_close", "flat_by_session_close", _valid_bool),
    ("backtest_session_close_time",    "session_close_time",    _valid_time_str),
    ("backtest_session_timezone",      "session_timezone",      _valid_timezone),
    ("backtest_no_new_entries_after",  "no_new_entries_after",  _valid_optional_time_str),
    ("backtest_exposure_policy",       "exposure_policy",       _valid_exposure_policy),
    ("backtest_cooldown_bars",         "cooldown_bars_after_exit", lambda v: _valid_int(v, lo=0, hi=10_000)),
)


def sanitize_backtest_defaults(raw: dict) -> dict[str, Any]:
    """Return a dict of ``{session_state_key: validated_value}`` from raw saved defaults.

    Fields that fail validation are omitted so widgets fall back to their built-in defaults.
    The ``defaults_schema_version`` key is excluded from the output.
    """
    out: dict[str, Any] = {}
    for session_key, raw_key, validator in _BACKTEST_FIELD_SPECS:
        if raw_key not in raw:
            continue
        validated = validator(raw[raw_key])
        if validated is not None:
            out[session_key] = validated
    return out


def collect_backtest_defaults(session_state: Any) -> dict:
    """Collect current backtest widget values from ``session_state`` for persistence."""
    out: dict[str, Any] = {}
    for session_key, raw_key, _ in _BACKTEST_FIELD_SPECS:
        if session_key in session_state:
            out[raw_key] = session_state[session_key]
    return out


def apply_backtest_defaults(session_state: Any, raw: dict) -> None:
    """Inject sanitized backtest defaults into ``session_state``.

    Only injects a key if it is *not* already present, so user-entered values
    for the current session are never overwritten.
    """
    sanitized = sanitize_backtest_defaults(raw)
    for key, value in sanitized.items():
        if key not in session_state:
            session_state[key] = value


def reset_backtest_session_keys(session_state: Any) -> None:
    """Remove Backtest *widget* keys from ``session_state``.

    Only removes the known execution-settings widget keys so that unrelated
    result keys (e.g. ``backtest_execution_costs``, ``backtest_session_exit_policy``)
    are preserved for downstream pages.
    Call ``st.rerun()`` immediately after this to apply built-in defaults.
    """
    widget_keys = {session_key for session_key, _, _ in _BACKTEST_FIELD_SPECS}
    for k in widget_keys:
        session_state.pop(k, None)
    # Remove the "applied" sentinel so defaults are re-evaluated on next render
    session_state.pop("_backtest_defaults_applied", None)


# ── Grid Search sanitisation ──────────────────────────────────────────────────

_GRID_FIELD_SPECS: tuple[tuple[str, str, Any], ...] = (
    ("grid_sl_start",                  "sl_start",               lambda v: _valid_float(v, lo=1.0, hi=500.0)),
    ("grid_sl_stop",                   "sl_stop",                lambda v: _valid_float(v, lo=1.0, hi=500.0)),
    ("grid_sl_step",                   "sl_step",                lambda v: _valid_float(v, lo=1.0, hi=100.0)),
    ("grid_tp_start",                  "tp_start",               lambda v: _valid_float(v, lo=1.0, hi=1000.0)),
    ("grid_tp_stop",                   "tp_stop",                lambda v: _valid_float(v, lo=1.0, hi=1000.0)),
    ("grid_tp_step",                   "tp_step",                lambda v: _valid_float(v, lo=1.0, hi=200.0)),
    ("grid_commission_per_side",       "commission_per_side",    lambda v: _valid_float(v, lo=0.0, hi=1000.0)),
    ("grid_slippage_ticks",            "slippage_ticks",         lambda v: _valid_float(v, lo=0.0, hi=100.0)),
    ("grid_use_max_bars",              "use_max_bars",           _valid_bool),
    ("grid_max_bars",                  "max_bars",               lambda v: _valid_int(v, lo=1, hi=500)),
    ("grid_allow_same_bar",            "allow_same_bar",         _valid_bool),
    ("grid_flat_by_session_close",     "flat_by_session_close",  _valid_bool),
    ("grid_session_close_time",        "session_close_time",     _valid_time_str),
    ("grid_session_timezone",          "session_timezone",       _valid_timezone),
    ("grid_no_new_entries_after",      "no_new_entries_after",   _valid_optional_time_str),
    ("grid_exposure_policy_widget",    "exposure_policy",        _valid_exposure_policy),
    ("grid_cooldown_bars",             "cooldown_bars_after_exit", lambda v: _valid_int(v, lo=0, hi=10_000)),
    ("grid_ranking_metric_widget",     "ranking_metric",         _valid_ranking_metric),
    ("grid_min_trades_widget",         "min_trades",             lambda v: _valid_int(v, lo=1, hi=1000)),
    ("grid_enable_directional",        "enable_directional",     _valid_bool),
    ("grid_directional_metric",        "directional_metric",     _valid_directional_metric),
    ("grid_min_long_trades_widget",    "min_long_trades",        lambda v: _valid_int(v, lo=1, hi=1000)),
    ("grid_min_short_trades_widget",   "min_short_trades",       lambda v: _valid_int(v, lo=1, hi=1000)),
)


def sanitize_grid_defaults(raw: dict) -> dict[str, Any]:
    """Return a dict of ``{session_state_key: validated_value}`` from raw saved grid defaults.

    Fields that fail validation are omitted so widgets fall back to their built-in defaults.
    """
    out: dict[str, Any] = {}
    for session_key, raw_key, validator in _GRID_FIELD_SPECS:
        if raw_key not in raw:
            continue
        validated = validator(raw[raw_key])
        if validated is not None:
            out[session_key] = validated
    return out


def collect_grid_defaults(session_state: Any) -> dict:
    """Collect current grid widget values from ``session_state`` for persistence."""
    out: dict[str, Any] = {}
    for session_key, raw_key, _ in _GRID_FIELD_SPECS:
        if session_key in session_state:
            out[raw_key] = session_state[session_key]
    return out


def apply_grid_defaults(session_state: Any, raw: dict) -> None:
    """Inject sanitized grid defaults into ``session_state``.

    Only injects a key if it is *not* already present.
    """
    sanitized = sanitize_grid_defaults(raw)
    for key, value in sanitized.items():
        if key not in session_state:
            session_state[key] = value


def reset_grid_session_keys(session_state: Any) -> None:
    """Remove Grid Search *widget* keys from ``session_state``.

    Only removes the known execution-settings widget keys so that unrelated
    result keys (e.g. ``grid_results``, ``grid_execution_costs``) are preserved
    for downstream pages.
    Call ``st.rerun()`` immediately after this to apply built-in defaults.
    """
    widget_keys = {session_key for session_key, _, _ in _GRID_FIELD_SPECS}
    for k in widget_keys:
        session_state.pop(k, None)
    session_state.pop("_grid_defaults_applied", None)
