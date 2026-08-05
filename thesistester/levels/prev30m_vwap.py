"""Previous 30-minute VWAP level computation (``prev30mVWAP``).

Output columns
--------------
``prev30mVWAP``
    Frozen end-of-bracket typical-price VWAP of the prior completed session-open
    30-minute bracket.  Available on ETH and RTH bars inside the TTL window.
    Seeded into the next trading session from the prior session's last freeze.

``prev30mVWAP_hit_m1`` / ``prev30mVWAP_hit_m5``
    Diagnostic flags (not setup-selectable levels): whether ``prev30mVWAP`` was
    range-touched in the first 1 / 5 minutes of the current 30m bracket.
    Finalized only after each window completes; in-window rows stay ``NaN``.

Bracket clock
-------------
    Minutes since session open (``eth_start``), floored into 30-minute buckets.
    Not RTH-open anchored.  ETH and RTH bars both contribute and emit.

Completion
----------
    1. Clock: first bar with ``timestamp >= bracket_end``.
    2. Session-boundary: true session transition (next bar has a new
       ``trading_session_date``) finalizes still-open brackets with volume.
    Mid-session dataframe truncation must **not** finalize open brackets.

Disabled behavior (``enabled=False``)
--------------------------------------
    Returns an empty DataFrame immediately — no timestamp validation, no new
    columns.
"""

from __future__ import annotations

import datetime
import numbers
from typing import Any

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..data.loader import infer_base_interval
from ..data.sessions import tag_session
from .common import require_tz_aware_timestamp
from .session_date import trading_session_date

BRACKET_MINUTES: int = 30
COL_PREV30M_VWAP = "prev30mVWAP"
COL_HIT_M1 = "prev30mVWAP_hit_m1"
COL_HIT_M5 = "prev30mVWAP_hit_m5"
PREV30M_VWAP_COLUMNS = (COL_PREV30M_VWAP, COL_HIT_M1, COL_HIT_M5)
HIT_WINDOW_M1 = pd.Timedelta(minutes=1)
HIT_WINDOW_M5 = pd.Timedelta(minutes=5)


def _window_resolvable(base: pd.Timedelta | None, window: pd.Timedelta) -> bool:
    """Return True when *window* is an integer multiple of *base*."""
    if base is None or base <= pd.Timedelta(0):
        return False
    return window % base == pd.Timedelta(0)


def session_bracket_keys(
    timestamps: pd.Series,
    instrument: str = "ES",
) -> pd.DataFrame:
    """Return ``session_date`` / ``bracket_idx`` for session-open 30m brackets.

    Used by Phase 2 analytics to join finalized ``hit_m*`` flags without
    mutating the level engine.  Rows that cannot be keyed (NaT or before
    session open) emit ``NaN`` ``bracket_idx``.
    """
    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  Supported instruments: {sorted(INSTRUMENTS)}"
        )
    inst = INSTRUMENTS[instrument]
    eth_start_raw = getattr(inst, "eth_start", "") or ""
    if not str(eth_start_raw).strip():
        raise ValueError(
            f"Instrument {instrument!r} has no eth_start; session bracket keys require it."
        )
    eth_time = _parse_eth_start(str(eth_start_raw))
    exchange_tz = inst.exchange_tz

    ts = pd.to_datetime(timestamps, errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        raise ValueError("timestamps must be timezone-aware")
    local_ts = ts.dt.tz_convert(exchange_tz)
    session_dates = trading_session_date(local_ts, str(eth_start_raw))

    opens = {
        sess: _session_open_ts(sess, eth_time, exchange_tz)
        for sess in pd.unique(session_dates.dropna())
    }
    open_ts = session_dates.map(opens)
    delta = local_ts - open_ts
    minutes = (delta / pd.Timedelta(minutes=1)).to_numpy(dtype="float64")
    bracket = np.full(len(timestamps), np.nan, dtype="float64")
    valid = np.isfinite(minutes) & (minutes >= 0)
    bracket[valid] = np.floor(minutes[valid] / BRACKET_MINUTES)

    return pd.DataFrame(
        {
            "session_date": session_dates.to_numpy(),
            "bracket_idx": bracket,
        },
        index=timestamps.index,
    )


def _parse_eth_start(eth_start: str) -> datetime.time:
    return pd.to_datetime(str(eth_start).strip()).time()


def _session_open_ts(
    session_date: datetime.date,
    eth_time: datetime.time,
    exchange_tz: str,
) -> pd.Timestamp:
    """Return exchange-local open for trading session date *session_date*."""
    prev_day = session_date - datetime.timedelta(days=1)
    return pd.Timestamp(
        year=prev_day.year,
        month=prev_day.month,
        day=prev_day.day,
        hour=eth_time.hour,
        minute=eth_time.minute,
        second=eth_time.second,
        microsecond=eth_time.microsecond,
        tz=exchange_tz,
    )


def _complete_bracket(
    state: dict[str, Any],
    bracket_idx: int,
    *,
    active: dict[str, Any],
) -> None:
    """Mark bracket complete; update active freeze when volume > 0."""
    st = state[bracket_idx]
    if st["done"]:
        return
    st["done"] = True
    vol = float(st["vol"])
    if vol > 0.0:
        vwap = float(st["pv"]) / vol
        active["value"] = vwap
        active["formed"] = int(bracket_idx)
        active["last_freeze"] = vwap


def _finalize_due_brackets(
    state: dict[int, dict[str, Any]],
    current_ts: pd.Timestamp,
    *,
    active: dict[str, Any],
) -> None:
    """Clock-complete every unfinished bracket whose end is at or before *current_ts*."""
    for bidx in sorted(state):
        st = state[bidx]
        if not st["done"] and st["end"] <= current_ts:
            _complete_bracket(state, bidx, active=active)


def _finalize_session_open_brackets(
    state: dict[int, dict[str, Any]],
    *,
    active: dict[str, Any],
) -> None:
    """Session-transition finalize: complete still-open brackets with volume."""
    for bidx in sorted(state):
        st = state[bidx]
        if st["done"]:
            continue
        if float(st["vol"]) > 0.0:
            _complete_bracket(state, bidx, active=active)
        else:
            st["done"] = True


def _emit_level(
    *,
    active: dict[str, Any],
    bracket_idx: int,
    validity_periods: int,
) -> float:
    value = active["value"]
    formed = active["formed"]
    if value is None or formed is None:
        return np.nan
    # Active for brackets formed+1 .. formed+N (seed uses formed=-1 → brackets 0..N-1).
    if formed < bracket_idx <= formed + validity_periods:
        return float(value)
    return np.nan


def _compute_hit_columns(
    work: pd.DataFrame,
    *,
    local_ts: pd.Series,
    session_dates: pd.Series,
    eth_time: datetime.time,
    exchange_tz: str,
    out_vwap: np.ndarray,
    hit_m1_ok: bool,
    hit_m5_ok: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Second pass: PIT-safe early-window hit diagnostics."""
    n = len(work)
    out_m1 = np.full(n, np.nan, dtype="float64")
    out_m5 = np.full(n, np.nan, dtype="float64")
    if n == 0:
        return out_m1, out_m5

    highs = work["high"].to_numpy(dtype="float64", copy=False)
    lows = work["low"].to_numpy(dtype="float64", copy=False)

    # Group row indices by (session_date, bracket_idx).
    groups: dict[tuple[datetime.date, int], list[int]] = {}
    session_opens: dict[datetime.date, pd.Timestamp] = {}
    for i in range(n):
        sess = session_dates.iloc[i]
        if sess not in session_opens:
            session_opens[sess] = _session_open_ts(sess, eth_time, exchange_tz)
        sess_open = session_opens[sess]
        minutes = int(np.floor((local_ts.iloc[i] - sess_open) / pd.Timedelta(minutes=1)))
        if minutes < 0:
            continue
        bidx = minutes // BRACKET_MINUTES
        groups.setdefault((sess, bidx), []).append(i)

    for (sess, bidx), indices in groups.items():
        level = out_vwap[indices[0]]
        if not np.isfinite(level):
            continue
        sess_open = session_opens[sess]
        b_start = sess_open + pd.Timedelta(minutes=bidx * BRACKET_MINUTES)
        m1_end = b_start + HIT_WINDOW_M1
        m5_end = b_start + HIT_WINDOW_M5

        m1_touch = False
        m5_touch = False
        for i in indices:
            ts = local_ts.iloc[i]
            touched = bool(lows[i] <= level <= highs[i])
            if b_start <= ts < m1_end and touched:
                m1_touch = True
            if b_start <= ts < m5_end and touched:
                m5_touch = True

        if hit_m1_ok:
            for i in indices:
                if local_ts.iloc[i] >= m1_end:
                    out_m1[i] = 1.0 if m1_touch else 0.0
        if hit_m5_ok:
            for i in indices:
                if local_ts.iloc[i] >= m5_end:
                    out_m5[i] = 1.0 if m5_touch else 0.0

    return out_m1, out_m5


def compute_prev30m_vwap_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    *,
    enabled: bool = False,
    validity_periods: int = 1,
) -> pd.DataFrame:
    """Return ``prev30mVWAP`` and early-window hit diagnostics aligned to *df*.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column.  Optional
        ``session`` column is used when present; otherwise derived via
        ``tag_session``.
    instrument:
        Instrument key in ``INSTRUMENTS``.
    enabled:
        Master gate.  ``False`` returns an empty DataFrame immediately.
    validity_periods:
        Number of subsequent 30m periods the frozen level remains valid (≥ 1).
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)

    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  Supported instruments: {sorted(INSTRUMENTS)}"
        )

    # Accept Integral (e.g. numpy.int64 from JSON/numpy pipelines) to match
    # api._validate_number_fields; reject bool (Integral subclass).
    if isinstance(validity_periods, bool) or not isinstance(validity_periods, numbers.Integral):
        raise ValueError("validity_periods must be an integer >= 1")
    validity_periods = int(validity_periods)
    if validity_periods < 1:
        raise ValueError("validity_periods must be an integer >= 1")

    inst = INSTRUMENTS[instrument]
    eth_start_raw = getattr(inst, "eth_start", "") or ""
    if not str(eth_start_raw).strip():
        raise ValueError(
            f"Instrument {instrument!r} has no eth_start; prev30mVWAP requires a "
            "session-open (ETH) clock and fails closed when eth_start is missing."
        )
    eth_time = _parse_eth_start(str(eth_start_raw))
    exchange_tz = inst.exchange_tz

    work = df.sort_values("timestamp").reset_index(drop=True).copy()
    if "session" not in work.columns:
        work = tag_session(work, instrument=instrument)

    local_ts = work["timestamp"].dt.tz_convert(exchange_tz)
    if local_ts.isna().any():
        raise ValueError(
            "prev30mVWAP requires non-NaT timestamps after exchange-timezone conversion."
        )
    session_dates = trading_session_date(local_ts, str(eth_start_raw))

    base_interval = infer_base_interval(work["timestamp"])
    hit_m1_ok = _window_resolvable(base_interval, HIT_WINDOW_M1)
    hit_m5_ok = _window_resolvable(base_interval, HIT_WINDOW_M5)

    n = len(work)
    out_vwap = np.full(n, np.nan, dtype="float64")
    if n == 0:
        return pd.DataFrame(
            {
                COL_PREV30M_VWAP: out_vwap,
                COL_HIT_M1: out_vwap.copy(),
                COL_HIT_M5: out_vwap.copy(),
            },
            index=work.index,
        )

    typical = (work["high"] + work["low"] + work["close"]) / 3.0
    volumes = work["volume"].astype("float64")
    pv = typical * volumes

    active: dict[str, Any] = {"value": None, "formed": None, "last_freeze": None}
    bracket_state: dict[int, dict[str, Any]] = {}
    session_opens: dict[datetime.date, pd.Timestamp] = {}
    prev_session: datetime.date | None = None

    for i in range(n):
        sess = session_dates.iloc[i]
        ts = local_ts.iloc[i]

        if prev_session is not None and sess != prev_session:
            _finalize_session_open_brackets(bracket_state, active=active)
            seed = active["last_freeze"]
            bracket_state = {}
            if seed is not None:
                active = {"value": float(seed), "formed": -1, "last_freeze": None}
            else:
                active = {"value": None, "formed": None, "last_freeze": None}

        if sess not in session_opens:
            session_opens[sess] = _session_open_ts(sess, eth_time, exchange_tz)
        sess_open = session_opens[sess]

        minutes = int(np.floor((ts - sess_open) / pd.Timedelta(minutes=1)))
        if minutes < 0:
            out_vwap[i] = np.nan
            prev_session = sess
            continue

        bidx = minutes // BRACKET_MINUTES
        b_start = sess_open + pd.Timedelta(minutes=bidx * BRACKET_MINUTES)
        b_end = b_start + pd.Timedelta(minutes=BRACKET_MINUTES)

        _finalize_due_brackets(bracket_state, ts, active=active)

        if bidx not in bracket_state:
            bracket_state[bidx] = {
                "pv": 0.0,
                "vol": 0.0,
                "start": b_start,
                "end": b_end,
                "done": False,
            }
        st = bracket_state[bidx]
        if not st["done"]:
            st["pv"] += float(pv.iloc[i])
            st["vol"] += float(volumes.iloc[i])

        out_vwap[i] = _emit_level(
            active=active,
            bracket_idx=bidx,
            validity_periods=validity_periods,
        )
        prev_session = sess

    # Do not finalize open brackets at dataframe end (mid-session truncation / PIT).

    out_m1, out_m5 = _compute_hit_columns(
        work,
        local_ts=local_ts,
        session_dates=session_dates,
        eth_time=eth_time,
        exchange_tz=exchange_tz,
        out_vwap=out_vwap,
        hit_m1_ok=hit_m1_ok,
        hit_m5_ok=hit_m5_ok,
    )

    return pd.DataFrame(
        {
            COL_PREV30M_VWAP: out_vwap,
            COL_HIT_M1: out_m1,
            COL_HIT_M5: out_m5,
        },
        index=work.index,
    )
