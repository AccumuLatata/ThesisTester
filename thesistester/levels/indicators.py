"""Indicator/dynamic level computations."""
from __future__ import annotations

import pandas as pd

from .common import normalized_window_label, require_tz_aware_timestamp


DEFAULT_SMA_LENGTHS: tuple[int, ...] = (20, 50, 200)
DEFAULT_EMA_LENGTHS: tuple[int, ...] = (20, 50, 200)
DEFAULT_VWAP_WINDOWS: tuple[str, ...] = ("15min", "30min", "1h", "4h")


def compute_indicator_levels(
    df: pd.DataFrame,
    sma_lengths: list[int] | tuple[int, ...] | None = None,
    ema_lengths: list[int] | tuple[int, ...] | None = None,
    vwap_windows: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Compute SMA/EMA and rolling VWAP levels aligned to each timestamp.

    Notes
    -----
    Rolling VWAP uses a bar-level approximation:
    ``rolling_sum(price * volume) / rolling_sum(volume)``, where ``price`` is the
    typical price `(high + low + close) / 3`.
    """
    require_tz_aware_timestamp(df)

    out = df.sort_values("timestamp").reset_index(drop=True).copy()
    levels = pd.DataFrame(index=out.index)

    sma_lengths = DEFAULT_SMA_LENGTHS if sma_lengths is None else tuple(sma_lengths)
    ema_lengths = DEFAULT_EMA_LENGTHS if ema_lengths is None else tuple(ema_lengths)
    vwap_windows = DEFAULT_VWAP_WINDOWS if vwap_windows is None else tuple(vwap_windows)

    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")
    typical_price = (pd.to_numeric(out["high"], errors="coerce") + pd.to_numeric(out["low"], errors="coerce") + close) / 3.0

    for length in sma_lengths:
        levels[f"SMA_{int(length)}"] = close.rolling(window=int(length), min_periods=int(length)).mean()

    for length in ema_lengths:
        levels[f"EMA_{int(length)}"] = close.ewm(span=int(length), adjust=False, min_periods=int(length)).mean()

    ts_indexed = out.set_index("timestamp")
    pv = (typical_price * volume).set_axis(ts_indexed.index)
    vol = volume.set_axis(ts_indexed.index)
    for window in vwap_windows:
        label = normalized_window_label(window)
        rolling_pv = pv.rolling(window=window).sum()
        rolling_vol = vol.rolling(window=window).sum()
        levels[f"VWAP_rolling_{label}"] = (rolling_pv / rolling_vol.replace(0.0, float("nan"))).to_numpy()

    return out.join(levels)
