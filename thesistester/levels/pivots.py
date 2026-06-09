"""Confirmed multi-timeframe pivot levels."""
from __future__ import annotations

import pandas as pd

from ..data.loader import format_interval, infer_base_interval
from ..data.resample import resample_ohlcv
from .common import require_tz_aware_timestamp

SUPPORTED_PIVOT_TIMEFRAMES: tuple[str, ...] = ("1min", "5min", "30min", "4h")
_PIVOT_COLUMN_LABELS: dict[str, str] = {
    "1min": "1m",
    "5min": "5m",
    "30min": "30m",
    "4h": "4h",
}

DEFAULT_PIVOT_LEFT: int = 2
DEFAULT_PIVOT_RIGHT: int = 2


def _normalize_pivot_timeframes(
    timeframes: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if timeframes is None:
        return SUPPORTED_PIVOT_TIMEFRAMES

    normalized = tuple(str(timeframe) for timeframe in timeframes)
    invalid = sorted({timeframe for timeframe in normalized if timeframe not in SUPPORTED_PIVOT_TIMEFRAMES})
    if invalid:
        raise ValueError(
            f"Unsupported pivot timeframe(s): {', '.join(invalid)}. "
            f"Choose from {', '.join(SUPPORTED_PIVOT_TIMEFRAMES)}."
        )
    return normalized


def _validate_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


def _resolve_pivot_source(
    out: pd.DataFrame,
    *,
    timeframe: str,
    base_interval: pd.Timedelta | None,
) -> pd.DataFrame:
    target_interval = pd.to_timedelta(timeframe)
    if base_interval is not None and base_interval > target_interval:
        base_label = format_interval(base_interval)
        valid_choices = [
            option
            for option in SUPPORTED_PIVOT_TIMEFRAMES
            if pd.to_timedelta(option) >= base_interval
        ]
        hint = f"Load {timeframe} data." if not valid_choices else f"Load {timeframe} data or choose {', '.join(valid_choices)}."
        raise ValueError(
            f"Cannot compute {timeframe} pivots from {base_label} source data. "
            f"{hint}"
        )

    if base_interval is not None and target_interval == base_interval:
        return out.copy()
    return resample_ohlcv(out, timeframe)


def _detect_pivot_mask(series: pd.Series, *, left: int, right: int, comparator) -> pd.Series:
    mask = series.notna()
    for offset in range(1, left + 1):
        mask &= comparator(series, series.shift(offset))
    for offset in range(1, right + 1):
        mask &= comparator(series, series.shift(-offset))
    return mask


def _latest_confirmed_pivot_series(
    source_df: pd.DataFrame,
    *,
    price_col: str,
    left: int,
    right: int,
    timeframe: str,
    base_timestamps: pd.DataFrame,
) -> pd.Series:
    prices = pd.to_numeric(source_df[price_col], errors="coerce")
    comparator = (lambda cur, other: cur > other) if price_col == "high" else (lambda cur, other: cur < other)
    pivot_mask = _detect_pivot_mask(prices, left=left, right=right, comparator=comparator)

    events = source_df.loc[pivot_mask, ["timestamp"]].copy()
    events["pivot_value"] = prices.loc[pivot_mask].to_numpy()
    events["align_timestamp"] = events["timestamp"] + (right + 1) * pd.to_timedelta(timeframe)
    events = (
        events.sort_values(["align_timestamp", "timestamp"])
        .drop_duplicates(subset=["align_timestamp"], keep="last")
        [["align_timestamp", "pivot_value"]]
    )
    if events.empty:
        return pd.Series(index=base_timestamps.index, dtype="float64")

    merged = pd.merge_asof(
        base_timestamps,
        events,
        left_on="timestamp",
        right_on="align_timestamp",
        direction="backward",
    )
    return merged["pivot_value"]


def compute_pivot_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    pivot_timeframes: list[str] | tuple[str, ...] | None = None,
    pivot_left: int = DEFAULT_PIVOT_LEFT,
    pivot_right: int = DEFAULT_PIVOT_RIGHT,
    *,
    enabled: bool = False,
) -> pd.DataFrame:
    """Return latest confirmed pivot levels aligned to *df*'s sorted timeline.

    Parameters
    ----------
    df:
        Canonical OHLCV DataFrame with a tz-aware ``timestamp`` column.  The
        function internally sorts rows by ``timestamp`` and resets the index,
        so the original index is **not** preserved in the output.
    instrument:
        Instrument key (e.g. ``"ES"``). Reserved for future pivot extensions.
    pivot_timeframes:
        Timeframes for which to compute pivots. Supported values:
        ``"1min"``, ``"5min"``, ``"30min"``, ``"4h"``.  ``None`` means all
        supported timeframes.
    pivot_left:
        Number of left-side candles required for fractal confirmation.
    pivot_right:
        Number of right-side candles required for fractal confirmation.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately so that no new columns are added by ``compute_all_levels``.

    Returns
    -------
    pd.DataFrame
        Empty DataFrame when ``enabled=False``. Otherwise returns scalar pivot
        columns aligned to *df*'s sorted timeline.
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)
    _validate_positive_int("pivot_left", pivot_left)
    _validate_positive_int("pivot_right", pivot_right)
    pivot_timeframes = _normalize_pivot_timeframes(pivot_timeframes)

    out = df.sort_values("timestamp").reset_index(drop=True).copy()
    base_timestamps = out[["timestamp"]].sort_values("timestamp")
    base_interval = infer_base_interval(out["timestamp"])
    levels = pd.DataFrame(index=out.index)

    for timeframe in pivot_timeframes:
        source_df = _resolve_pivot_source(out, timeframe=timeframe, base_interval=base_interval)
        source_df = source_df.sort_values("timestamp").reset_index(drop=True)
        label = _PIVOT_COLUMN_LABELS[timeframe]

        levels[f"Pivot_{label}_High"] = _latest_confirmed_pivot_series(
            source_df,
            price_col="high",
            left=pivot_left,
            right=pivot_right,
            timeframe=timeframe,
            base_timestamps=base_timestamps,
        ).to_numpy()
        levels[f"Pivot_{label}_Low"] = _latest_confirmed_pivot_series(
            source_df,
            price_col="low",
            left=pivot_left,
            right=pivot_right,
            timeframe=timeframe,
            base_timestamps=base_timestamps,
        ).to_numpy()

    return levels
