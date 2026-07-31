"""Deterministic synthetic workloads for R22 timing measurements."""

from __future__ import annotations

import numpy as np
import pandas as pd


def benchmark_ohlcv(*, bars: int) -> pd.DataFrame:
    """Build a deterministic 1-minute parent-bar frame with no bracket hits."""
    timestamps = pd.date_range("2026-01-05 09:30", periods=bars, freq="1min", tz="America/New_York")
    close = 100.0 + np.arange(bars, dtype=float) * 0.001
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": np.full(bars, 100.0),
        }
    )


def benchmark_signals(*, bars: int, signal_count: int) -> pd.DataFrame:
    """Build deterministic next-open signals whose holds are capped by callers."""
    indices = np.linspace(0, max(0, bars - 2), num=signal_count, dtype=int)
    return pd.DataFrame(
        {
            "signal_id": np.arange(signal_count, dtype=int),
            "bar_index": indices,
            "trigger": ["touch"] * signal_count,
            "direction": np.where(np.arange(signal_count) % 2 == 0, "long", "short"),
        }
    )
