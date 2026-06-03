"""Shared helpers for level modules."""
from __future__ import annotations

import pandas as pd


def require_tz_aware_timestamp(df: pd.DataFrame) -> None:
    if "timestamp" not in df.columns:
        raise ValueError("Input must include a 'timestamp' column.")
    if df["timestamp"].dt.tz is None:
        raise ValueError("Input 'timestamp' must be timezone-aware.")


def normalized_window_label(window: str | pd.Timedelta) -> str:
    if isinstance(window, str):
        return window.strip().lower().replace(" ", "")
    td = pd.to_timedelta(window)
    if td % pd.Timedelta(hours=1) == pd.Timedelta(0):
        return f"{int(td / pd.Timedelta(hours=1))}h"
    return f"{int(td / pd.Timedelta(minutes=1))}min"
