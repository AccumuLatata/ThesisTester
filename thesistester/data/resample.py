"""OHLCV resampling helpers for supported ThesisTester timeframes."""
from __future__ import annotations

import pandas as pd

from .loader import infer_base_interval

SUPPORTED_TIMEFRAMES = ("1min", "5min", "15min", "30min", "1h", "4h", "1D")
_FREQ_MAP = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "1h",
    "4h": "4h",
    "1D": "1D",
}


def _parse_timeframe(value: str) -> pd.Timedelta:
    return pd.to_timedelta(value)


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample tz-aware OHLCV bars using financial aggregation rules."""
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    base_interval = infer_base_interval(df["timestamp"])
    target_interval = _parse_timeframe(timeframe)

    # Do not upsample: return original data when target frame is <= base frame.
    if base_interval is not None and target_interval <= base_interval:
        return df.copy()

    indexed = df.set_index("timestamp")
    resampled = indexed.resample(_FREQ_MAP[timeframe]).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": lambda s: s.sum(min_count=1),
        }
    )

    resampled = resampled.dropna(how="all").reset_index()
    return resampled

