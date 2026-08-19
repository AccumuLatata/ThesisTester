"""Session VWAP level computation.

Implements developing session VWAPs:

``dVWAP_RTH``
    Developing VWAP from the RTH session open.  Resets at each new RTH session.
    ``NaN`` on bars outside RTH (before session open and after session close).
    ``NaN`` when cumulative RTH volume is zero.

``dVWAP``
    Developing VWAP over the entire CME trading session
    (``eth_start`` → next ``eth_start``, via ``trading_session_date``).
    ETH and RTH bars both contribute and both emit values.
    Resets at each CME session open.  ``NaN`` when cumulative session volume
    is zero.  When the instrument has no ``eth_start``, session grouping falls
    back to calendar date (same helper as other session-date levels).

``wVWAP``
    Developing VWAP of the current CME trading week.  Week keys are
    ``trading_session_date`` → ``W-SUN`` — the same construction as ``wOpen``
    in ``sessions.py`` / ``profile.py``.  ETH and RTH bars both contribute
    and both emit values.  Resets at each new trading week.  ``NaN`` when
    cumulative week volume is zero.

``mVWAP``
    Developing VWAP of the current CME trading month.  Month keys are
    ``trading_session_date`` → ``M`` — the same construction as ``mOpen``.
    ETH and RTH bars both contribute and both emit values.  Resets at each
    new trading month.  ``NaN`` when cumulative month volume is zero.

Formula
-------
    typical_price = (high + low + close) / 3
    VWAP[t] = cumsum(typical_price * volume)[t] / cumsum(volume)[t]

    For ``dVWAP_RTH``, ``cumsum`` resets at each RTH session open and includes
    only RTH bars.  Non-RTH bars always emit ``NaN``.

    For ``dVWAP``, ``cumsum`` resets at each CME trading-session date and
    includes every bar in that session.

    For ``wVWAP`` / ``mVWAP``, ``cumsum`` resets at each trading week / month
    and includes every bar in that period.

Point-in-time guarantee
-----------------------
    At bar ``t``, only bars at or before ``t`` in the same session / week /
    month group are used.  No future bar can change the value at ``t``.

Disabled behavior (``enabled=False``)
--------------------------------------
    Returns an empty DataFrame immediately — no timestamp validation, no new
    columns.  This preserves the Stage 1 no-op contract.

Unsupported anchor
------------------
    Raises ``ValueError``.  Only ``"RTH"`` is supported for the RTH column
    gate; ``dVWAP``, ``wVWAP``, and ``mVWAP`` (full CME session / week /
    month) are always emitted alongside ``dVWAP_RTH`` when enabled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..data.sessions import tag_session
from .common import require_tz_aware_timestamp
from .session_date import trading_session_date

# Anchor options supported for the RTH VWAP column gate.
SUPPORTED_VWAP_ANCHORS: tuple[str, ...] = ("RTH",)

# Default anchor for the RTH column.
DEFAULT_VWAP_ANCHOR: str = "RTH"

COL_DVWAP_RTH = "dVWAP_RTH"
COL_DVWAP = "dVWAP"
COL_WVWAP = "wVWAP"
COL_MVWAP = "mVWAP"
SESSION_VWAP_COLUMNS: tuple[str, ...] = (COL_DVWAP_RTH, COL_DVWAP, COL_WVWAP, COL_MVWAP)


def compute_session_vwap_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    anchor: str = DEFAULT_VWAP_ANCHOR,
    *,
    enabled: bool = False,
) -> pd.DataFrame:
    """Return developing-VWAP level columns aligned to *df*'s index.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column.  An optional
        ``session`` column (values ``"RTH"`` / ``"ETH"``) can be pre-attached;
        when it is absent, RTH membership is derived from ``instrument`` config
        and the timestamp timezone.
    instrument:
        Instrument key recognised by ``thesistester.config.INSTRUMENTS``
        (e.g. ``"ES"``).
    anchor:
        Session anchor for the RTH VWAP column.  Currently only ``"RTH"`` is
        supported.  Full-session ``dVWAP``, ``wVWAP``, and ``mVWAP`` do not
        use this parameter; they are always CME-session / week / month
        anchored when emitted.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately — no timestamp validation, no new columns.  When ``True``,
        emits ``dVWAP_RTH``, ``dVWAP``, ``wVWAP``, and ``mVWAP``.

    Returns
    -------
    pd.DataFrame
        - ``enabled=False``: empty DataFrame with the same index as *df*.
          Returns immediately without processing.
        - ``enabled=True``: DataFrame with columns ``dVWAP_RTH``, ``dVWAP``,
          ``wVWAP``, and ``mVWAP`` aligned to the **internally sorted**
          timestamp timeline (``sort_values("timestamp").reset_index(drop=True)``).
          The returned index is a fresh ``RangeIndex`` matching the sorted row
          order.  When joining to other level DataFrames produced by
          ``compute_all_levels``, alignment is guaranteed because all level
          functions operate on the same sorted timeline.

    Raises
    ------
    ValueError
        If ``enabled=True`` and:
        - ``df["timestamp"]`` is timezone-naive,
        - ``instrument`` is not in ``INSTRUMENTS``,
        - ``anchor`` is not in ``SUPPORTED_VWAP_ANCHORS``.
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    # --- Validation (only when enabled) ---
    require_tz_aware_timestamp(df)

    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  Supported instruments: {sorted(INSTRUMENTS)}"
        )

    if anchor not in SUPPORTED_VWAP_ANCHORS:
        raise ValueError(
            f"Unsupported VWAP anchor: {anchor!r}.  "
            f"Supported anchors: {list(SUPPORTED_VWAP_ANCHORS)}"
        )

    # --- Sort and work on a copy so we never mutate the caller's frame ---
    work = df.sort_values("timestamp").reset_index(drop=True).copy()

    # --- Derive session membership (needed for dVWAP_RTH) ---
    if "session" not in work.columns:
        work = tag_session(work, instrument=instrument)

    # --- Compute CME trading session date for grouping ---
    inst = INSTRUMENTS[instrument]
    exchange_tz = inst.exchange_tz
    eth_start = getattr(inst, "eth_start", "") or ""
    local_ts = work["timestamp"].dt.tz_convert(exchange_tz)
    session_date = trading_session_date(local_ts, eth_start)
    # Period keys identical to sessions.py / profile.py (wOpen / mOpen).
    session_date_ts = pd.to_datetime(session_date)
    week_key = session_date_ts.dt.to_period("W-SUN")
    month_key = session_date_ts.dt.to_period("M")

    typical = (work["high"] + work["low"] + work["close"]) / 3.0
    pv = typical * work["volume"]
    volume = work["volume"]

    # --- Build dVWAP_RTH (RTH bars only; unchanged semantics) ---
    is_rth = work["session"].eq("RTH")
    dvwap_rth = pd.Series(np.nan, index=work.index, dtype="float64")

    for _date, idx in work[is_rth].groupby(session_date[is_rth], sort=True).groups.items():
        cum_pv = pv.loc[idx].cumsum()
        cum_vol = volume.loc[idx].cumsum()
        # Emit NaN when cumulative volume is zero (prevents divide-by-zero).
        dvwap_rth.loc[idx] = cum_pv.where(cum_vol > 0).div(cum_vol.replace(0, np.nan))

    # --- Build dVWAP (full CME session: ETH + RTH) ---
    dvwap = pd.Series(np.nan, index=work.index, dtype="float64")

    for _date, idx in work.groupby(session_date, sort=True).groups.items():
        cum_pv = pv.loc[idx].cumsum()
        cum_vol = volume.loc[idx].cumsum()
        dvwap.loc[idx] = cum_pv.where(cum_vol > 0).div(cum_vol.replace(0, np.nan))

    # --- Build wVWAP (current trading week: ETH + RTH) ---
    wvwap = pd.Series(np.nan, index=work.index, dtype="float64")

    for _week, idx in work.groupby(week_key, sort=True).groups.items():
        cum_pv = pv.loc[idx].cumsum()
        cum_vol = volume.loc[idx].cumsum()
        wvwap.loc[idx] = cum_pv.where(cum_vol > 0).div(cum_vol.replace(0, np.nan))

    # --- Build mVWAP (current trading month: ETH + RTH) ---
    mvwap = pd.Series(np.nan, index=work.index, dtype="float64")

    for _month, idx in work.groupby(month_key, sort=True).groups.items():
        cum_pv = pv.loc[idx].cumsum()
        cum_vol = volume.loc[idx].cumsum()
        mvwap.loc[idx] = cum_pv.where(cum_vol > 0).div(cum_vol.replace(0, np.nan))

    return pd.DataFrame(
        {COL_DVWAP_RTH: dvwap_rth, COL_DVWAP: dvwap, COL_WVWAP: wvwap, COL_MVWAP: mvwap},
        index=work.index,
    )
