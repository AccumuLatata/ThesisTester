"""Indicator/dynamic level computations."""
from __future__ import annotations

import pandas as pd

from ..data.loader import infer_base_interval
from ..data.resample import resample_ohlcv
from .common import normalized_window_label, require_tz_aware_timestamp


DEFAULT_SMA_LENGTHS: tuple[int, ...] = (20, 50, 200)
DEFAULT_EMA_LENGTHS: tuple[int, ...] = (20, 50, 200)
DEFAULT_VWAP_WINDOWS: tuple[str, ...] = ("15min", "30min", "1h", "4h")
SUPPORTED_INDICATOR_TIMEFRAMES: tuple[str, ...] = ("1min", "5min", "30min")


def _normalize_indicator_timeframes(
    timeframes: list[str] | tuple[str, ...] | None,
    *,
    indicator_name: str,
) -> tuple[str, ...] | None:
    if timeframes is None:
        return None

    normalized = tuple(str(timeframe) for timeframe in timeframes)
    invalid = sorted({timeframe for timeframe in normalized if timeframe not in SUPPORTED_INDICATOR_TIMEFRAMES})
    if invalid:
        raise ValueError(
            f"Unsupported {indicator_name} timeframe(s): {', '.join(invalid)}. "
            f"Choose from {', '.join(SUPPORTED_INDICATOR_TIMEFRAMES)}."
        )
    return normalized


def _resolve_indicator_source(
    out: pd.DataFrame,
    *,
    timeframe: str,
    indicator_name: str,
    base_interval: pd.Timedelta | None,
) -> tuple[pd.DataFrame, bool]:
    target_interval = pd.to_timedelta(timeframe)
    if base_interval is not None and base_interval > target_interval:
        base_label = f"{int(base_interval.total_seconds() // 60)}min"
        valid_choices = [
            option
            for option in SUPPORTED_INDICATOR_TIMEFRAMES
            if pd.to_timedelta(option) >= base_interval
        ]
        choice_hint = "/".join(valid_choices) if valid_choices else base_label
        raise ValueError(
            f"Cannot compute {timeframe} {indicator_name} from {base_label} source data. "
            f"Load {timeframe} data or choose {choice_hint}."
        )

    source_df = resample_ohlcv(out, timeframe)
    uses_higher_timeframe = base_interval is not None and target_interval > base_interval
    return source_df, uses_higher_timeframe


def _append_timeframe_levels(
    *,
    out: pd.DataFrame,
    levels: pd.DataFrame,
    lengths: tuple[int, ...],
    timeframes: tuple[str, ...],
    indicator_prefix: str,
    base_interval: pd.Timedelta | None,
) -> None:
    base_timestamps = out[["timestamp"]].sort_values("timestamp")
    is_sma = indicator_prefix == "SMA"

    for timeframe in timeframes:
        source_df, uses_higher_timeframe = _resolve_indicator_source(
            out,
            timeframe=timeframe,
            indicator_name=indicator_prefix,
            base_interval=base_interval,
        )
        source_df = source_df.sort_values("timestamp").reset_index(drop=True)
        source_close = pd.to_numeric(source_df["close"], errors="coerce")

        timeframe_levels = pd.DataFrame({"timestamp": source_df["timestamp"]})
        for length in lengths:
            col = f"{indicator_prefix}_{int(length)}_{timeframe}"
            if is_sma:
                timeframe_levels[col] = source_close.rolling(window=int(length), min_periods=int(length)).mean()
            else:
                timeframe_levels[col] = source_close.ewm(
                    span=int(length),
                    adjust=False,
                    min_periods=int(length),
                ).mean()

        if uses_higher_timeframe:
            timeframe_levels["align_timestamp"] = timeframe_levels["timestamp"] + pd.to_timedelta(timeframe)
        else:
            timeframe_levels["align_timestamp"] = timeframe_levels["timestamp"]

        merged = pd.merge_asof(
            base_timestamps,
            timeframe_levels.sort_values("align_timestamp"),
            left_on="timestamp",
            right_on="align_timestamp",
            direction="backward",
        )
        timeframe_cols = [col for col in timeframe_levels.columns if col.startswith(f"{indicator_prefix}_")]
        for col in timeframe_cols:
            levels[col] = merged[col].to_numpy()


def compute_indicator_levels(
    df: pd.DataFrame,
    sma_lengths: list[int] | tuple[int, ...] | None = None,
    ema_lengths: list[int] | tuple[int, ...] | None = None,
    sma_timeframes: list[str] | tuple[str, ...] | None = None,
    ema_timeframes: list[str] | tuple[str, ...] | None = None,
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
    sma_timeframes = _normalize_indicator_timeframes(sma_timeframes, indicator_name="SMA")
    ema_timeframes = _normalize_indicator_timeframes(ema_timeframes, indicator_name="EMA")
    vwap_windows = DEFAULT_VWAP_WINDOWS if vwap_windows is None else tuple(vwap_windows)
    base_interval = infer_base_interval(out["timestamp"])

    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")
    typical_price = (pd.to_numeric(out["high"], errors="coerce") + pd.to_numeric(out["low"], errors="coerce") + close) / 3.0

    if sma_timeframes is None:
        for length in sma_lengths:
            levels[f"SMA_{int(length)}"] = close.rolling(window=int(length), min_periods=int(length)).mean()
    else:
        _append_timeframe_levels(
            out=out,
            levels=levels,
            lengths=sma_lengths,
            timeframes=sma_timeframes,
            indicator_prefix="SMA",
            base_interval=base_interval,
        )

    if ema_timeframes is None:
        for length in ema_lengths:
            levels[f"EMA_{int(length)}"] = close.ewm(span=int(length), adjust=False, min_periods=int(length)).mean()
    else:
        _append_timeframe_levels(
            out=out,
            levels=levels,
            lengths=ema_lengths,
            timeframes=ema_timeframes,
            indicator_prefix="EMA",
            base_interval=base_interval,
        )

    ts_indexed = out.set_index("timestamp")
    pv = (typical_price * volume).set_axis(ts_indexed.index)
    vol = volume.set_axis(ts_indexed.index)
    for window in vwap_windows:
        label = normalized_window_label(window)
        rolling_pv = pv.rolling(window=window).sum()
        rolling_vol = vol.rolling(window=window).sum()
        levels[f"VWAP_rolling_{label}"] = (rolling_pv / rolling_vol.replace(0.0, float("nan"))).to_numpy()

    return out.join(levels)
