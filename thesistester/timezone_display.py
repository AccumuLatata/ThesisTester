"""Helpers for display/export timezone handling."""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import pandas as pd

from .config import TIMEZONE_OPTIONS

DISPLAY_TIMEZONE_KEY = "display_timezone"


def ensure_display_timezone(
    session_state: MutableMapping[str, Any],
    *,
    exchange_timezone: str | None,
) -> str:
    """Ensure session state has a valid display/export timezone."""
    current = session_state.get(DISPLAY_TIMEZONE_KEY)
    if current in TIMEZONE_OPTIONS:
        return str(current)

    fallback = exchange_timezone if exchange_timezone in TIMEZONE_OPTIONS else TIMEZONE_OPTIONS[0]
    session_state[DISPLAY_TIMEZONE_KEY] = fallback
    return fallback


def timezone_contract(session_state: MutableMapping[str, Any]) -> dict[str, str | None]:
    """Return source/canonical/display timezone contract from session state."""
    source_timezone = session_state.get("source_timezone")
    canonical_timezone = session_state.get("exchange_timezone")
    display_timezone = ensure_display_timezone(
        session_state,
        exchange_timezone=canonical_timezone,
    )
    return {
        "source_timezone": source_timezone,
        "canonical_engine_timezone": canonical_timezone,
        "display_export_timezone": display_timezone,
    }


def timezone_contract_caption(session_state: MutableMapping[str, Any]) -> str:
    """Return human-readable timezone contract caption."""
    contract = timezone_contract(session_state)
    return (
        f"Source: {contract['source_timezone'] or '—'} · "
        f"Engine: {contract['canonical_engine_timezone'] or '—'} · "
        f"Display/export: {contract['display_export_timezone'] or '—'}"
    )


def timestamp_columns(df: pd.DataFrame) -> list[str]:
    """Return likely timestamp columns for display/export conversion."""
    return [c for c in df.columns if c == "timestamp" or c.endswith("_timestamp")]


def convert_dataframe_timestamps_for_display(
    df: pd.DataFrame | None,
    *,
    display_timezone: str,
    canonical_timezone: str,
) -> tuple[pd.DataFrame | None, list[str]]:
    """Convert timestamp-like columns on a copy for display/export use."""
    if df is None:
        return None, []
    if df.empty:
        return df.copy(deep=True), []

    out = df.copy(deep=True)
    warnings: list[str] = []
    for col in timestamp_columns(out):
        series = out[col]
        if not pd.api.types.is_datetime64_any_dtype(series):
            continue
        if series.dt.tz is None:
            warnings.append(
                f"Column '{col}' was timezone-naive during export conversion; "
                f"localized to canonical timezone {canonical_timezone} before converting."
            )
            localized = series.dt.tz_localize(canonical_timezone)
            out[col] = localized.dt.tz_convert(display_timezone)
        else:
            out[col] = series.dt.tz_convert(display_timezone)

    return out, warnings
