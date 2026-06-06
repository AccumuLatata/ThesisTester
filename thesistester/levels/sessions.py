"""Session/structural level engine for canonical OHLCV data."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from .session_date import trading_session_date


def _require_tz_aware_timestamp(df: pd.DataFrame) -> None:
    if "timestamp" not in df.columns:
        raise ValueError("Input must include a 'timestamp' column.")
    if df["timestamp"].dt.tz is None:
        raise ValueError("Input 'timestamp' must be timezone-aware.")


def _period_levels(
    df: pd.DataFrame,
    key: pd.Series,
    open_name: str,
    high_name: str,
    low_name: str,
    eq_name: str,
) -> pd.DataFrame:
    grouped = df.groupby(key, sort=True).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"))
    prev = grouped.shift(1)
    return pd.DataFrame(
        {
            open_name: key.map(prev["open"]),
            high_name: key.map(prev["high"]),
            low_name: key.map(prev["low"]),
            eq_name: key.map((prev["high"] + prev["low"]) / 2.0),
        },
        index=df.index,
    )


def _current_opens(df: pd.DataFrame, session_date: pd.Series, week_key: pd.Series, month_key: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dOpen": df.groupby(session_date, sort=False)["open"].transform("first"),
            "wOpen": df.groupby(week_key, sort=False)["open"].transform("first"),
            "mOpen": df.groupby(month_key, sort=False)["open"].transform("first"),
        },
        index=df.index,
    )


def _rth_open(df: pd.DataFrame, session_date: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    if "session" not in df.columns:
        return out

    rth = df["session"].eq("RTH")
    if not rth.any():
        return out

    first_open = df.loc[rth].groupby(session_date[rth], sort=True)["open"].first()
    first_rth_ts = df.loc[rth].groupby(session_date[rth], sort=True)["timestamp"].first()
    available = df["timestamp"] >= session_date.map(first_rth_ts)
    return session_date.map(first_open).where(available).astype("float64")


def _overnight_high_low(
    df: pd.DataFrame,
    session_date: pd.Series,
    local_ts: pd.Series,
    eth_start: str,
    rth_start: pd.Timestamp,
    rth_end: pd.Timestamp,
) -> pd.DataFrame:
    out = pd.DataFrame({"ONH": pd.Series(np.nan, index=df.index, dtype="float64"), "ONL": pd.Series(np.nan, index=df.index, dtype="float64")})
    if "session" not in df.columns:
        return out

    t = local_ts.dt.time
    mask_eth = df["session"].eq("ETH")
    overnight_start_time = pd.to_datetime(eth_start).time() if eth_start else rth_end.time()
    is_overnight = mask_eth & ((t >= overnight_start_time) | (t < rth_start.time()))
    if not is_overnight.any():
        return out

    overnight_key = pd.Series(session_date.values, index=df.index)
    if not eth_start:
        overnight_key = overnight_key.where(~(mask_eth & (t >= overnight_start_time)), overnight_key + timedelta(days=1))

    overnight = df.loc[is_overnight].groupby(overnight_key[is_overnight], sort=True).agg(ONH=("high", "max"), ONL=("low", "min"))
    onh = session_date.map(overnight["ONH"])
    onl = session_date.map(overnight["ONL"])

    rth = df["session"].eq("RTH")
    if not rth.any():
        return out

    first_rth_ts = df.loc[rth].groupby(session_date[rth], sort=True)["timestamp"].first()
    available = df["timestamp"] >= session_date.map(first_rth_ts)

    out["ONH"] = onh.where(available).astype("float64")
    out["ONL"] = onl.where(available).astype("float64")
    return out


def _opening_range(
    df: pd.DataFrame,
    session_date: pd.Series,
    local_ts: pd.Series,
    rth_start: pd.Timestamp,
    opening_range_minutes: int,
) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "OR_High": pd.Series(np.nan, index=df.index, dtype="float64"),
            "OR_Low": pd.Series(np.nan, index=df.index, dtype="float64"),
        }
    )
    if "session" not in df.columns:
        return out

    if opening_range_minutes not in {5, 15, 30}:
        raise ValueError("opening_range_minutes must be one of: 5, 15, 30")

    rth = df["session"].eq("RTH")
    minute_of_day = local_ts.dt.hour * 60 + local_ts.dt.minute
    start_minute = rth_start.hour * 60 + rth_start.minute
    end_minute = start_minute + opening_range_minutes

    in_or_window = rth & (minute_of_day >= start_minute) & (minute_of_day < end_minute)
    if not in_or_window.any():
        return out

    or_levels = df.loc[in_or_window].groupby(session_date[in_or_window], sort=True).agg(OR_High=("high", "max"), OR_Low=("low", "min"))

    first_rth_ts = df.loc[rth].groupby(session_date[rth], sort=True)["timestamp"].first()
    available_after = session_date.map(first_rth_ts) + pd.to_timedelta(opening_range_minutes, unit="minute")
    available_mask = df["timestamp"] >= available_after

    out["OR_High"] = session_date.map(or_levels["OR_High"]).where(available_mask).astype("float64")
    out["OR_Low"] = session_date.map(or_levels["OR_Low"]).where(available_mask).astype("float64")
    return out


def _prev_settlement(df: pd.DataFrame, session_date: pd.Series) -> pd.Series:
    if "settlement" in df.columns:
        settlements = pd.to_numeric(df["settlement"], errors="coerce")
        daily_settlement = settlements.groupby(session_date, sort=True).last()
    else:
        daily_settlement = df.groupby(session_date, sort=True)["close"].last()

    return session_date.map(daily_settlement.shift(1)).astype("float64")


def compute_session_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    opening_range_minutes: int = 30,
) -> pd.DataFrame:
    """Compute session/structural levels aligned to each bar timestamp.

    Notes
    -----
    - Input must be canonical OHLCV with a timezone-aware ``timestamp`` column.
    - ``session`` is optional; when absent, session-dependent levels return NaN.
    - ``prevSettlement`` uses prior-day settlement when a ``settlement`` column exists;
      otherwise it conservatively falls back to prior-day final close.
    """
    _require_tz_aware_timestamp(df)
    if instrument not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {instrument}")

    inst = INSTRUMENTS[instrument]
    out = df.sort_values("timestamp").reset_index(drop=True).copy()
    local_ts = out["timestamp"].dt.tz_convert(inst.exchange_tz)
    session_date = trading_session_date(local_ts, inst.eth_start)
    session_date_ts = pd.to_datetime(session_date)
    week_key = session_date_ts.dt.to_period("W-SUN")
    month_key = session_date_ts.dt.to_period("M")

    levels = _current_opens(out, session_date, week_key, month_key)
    levels = levels.join(
        _period_levels(
            out,
            session_date,
            open_name="pdOpen",
            high_name="pdHigh",
            low_name="pdLow",
            eq_name="pdEQ",
        )
    )
    levels = levels.join(
        _period_levels(
            out,
            week_key,
            open_name="pwOpen",
            high_name="pwHigh",
            low_name="pwLow",
            eq_name="pwEQ",
        )
    )
    levels = levels.join(
        _period_levels(
            out,
            month_key,
            open_name="pmOpen",
            high_name="pmHigh",
            low_name="pmLow",
            eq_name="pmEQ",
        )
    )

    rth_start = pd.to_datetime(inst.rth_start)
    rth_end = pd.to_datetime(inst.rth_end)

    levels["RTH_Open"] = _rth_open(out, session_date)
    levels = levels.join(_overnight_high_low(out, session_date, local_ts, inst.eth_start, rth_start, rth_end))
    levels = levels.join(_opening_range(out, session_date, local_ts, rth_start, opening_range_minutes))
    levels["prevSettlement"] = _prev_settlement(out, session_date)

    ordered = [
        "ONH",
        "ONL",
        "OR_High",
        "OR_Low",
        "RTH_Open",
        "prevSettlement",
        "dOpen",
        "wOpen",
        "mOpen",
        "pdOpen",
        "pwOpen",
        "pmOpen",
        "pdHigh",
        "pdLow",
        "pwHigh",
        "pwLow",
        "pmHigh",
        "pmLow",
        "pdEQ",
        "pwEQ",
        "pmEQ",
    ]
    for col in ordered:
        if col not in levels.columns:
            levels[col] = pd.Series(np.nan, index=levels.index, dtype="float64")

    return out.join(levels[ordered])
