"""A-Period POC (APOC / pAPOC) level computation — Stage 5 implementation.

APOC and pAPOC are **profile / POC levels**, not Single Print levels.  They are
implemented here, in a dedicated module, and not in ``tpo.py``.

Output columns
--------------
``APOC``
    POC of the first completed RTH 30-minute bracket (the A-period).
    ``NaN`` before the A-period is complete (i.e. before RTH open + 30 min).
    ``NaN`` on non-RTH bars.

``pAPOC``
    Prior completed RTH session's APOC.  Frozen at the start of the new RTH
    session and remains constant throughout that session.
    ``NaN`` on non-RTH bars and when the prior session had no valid APOC.

Conceptual definitions
----------------------
    APOC  = POC of the first completed RTH 30-minute bracket after NY/RTH open.
    pAPOC = prior completed RTH session's APOC (frozen, carried forward).

Profile approximation (consistent with ``profile.py``)
-------------------------------------------------------
    typical_price = (high + low + close) / 3
    Full bar volume is allocated to the tick bin containing ``typical_price``.
    POC is the tick bin with the highest total volume (lowest bin wins ties,
    because bins are sorted ascending and ``np.argmax`` returns the first max).

    This matches the existing ``_compute_profile`` / ``_bucket_prices`` helpers
    in ``profile.py``.  Do not change those helpers; use them directly.

A-period bars
-------------
    Only RTH bars with timestamps in ``[RTH_open, RTH_open + 30 min)`` are
    included.  ETH bars never contribute.

APOC availability
-----------------
    APOC is emitted starting from the bar whose timestamp is
    ``>= RTH_open + 30 min`` (the first bar at or after A-period completion).
    Earlier RTH bars and all non-RTH bars emit ``NaN``.

pAPOC availability
------------------
    pAPOC is available from the first RTH bar of each session.  It is constant
    throughout that session.  If the prior session produced no valid APOC,
    ``NaN`` is emitted.

Point-in-time guarantee
-----------------------
    For every row at timestamp T, only RTH A-period bars from the current
    session (when computing APOC) or the prior completed session (when computing
    pAPOC) were used — and only bars at or before the A-period completion
    timestamp.  Appending future bars cannot alter APOC or pAPOC at prior
    timestamps.

Disabled behavior (``enabled=False``)
--------------------------------------
    Returns an empty DataFrame immediately — no timestamp validation, no new
    columns.  This preserves the Stage 1 no-op contract.
"""
from __future__ import annotations

import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..data.sessions import tag_session
from .common import require_tz_aware_timestamp
from .profile import _compute_profile
from .session_date import trading_session_date

# A-period bracket width (minutes from RTH open).
A_PERIOD_MINUTES: int = 30

# Output column names.
COL_APOC = "APOC"
COL_PAPOC = "pAPOC"
APOC_COLUMNS = (COL_APOC, COL_PAPOC)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_a_period_poc(a_bars: pd.DataFrame, tick_size: float) -> float:
    """Return the POC of the given A-period bars using the profile.py approximation.

    Parameters
    ----------
    a_bars:
        RTH bars within the A-period window, with ``high``, ``low``, ``close``,
        and ``volume`` columns.
    tick_size:
        Instrument tick size for price binning.

    Returns
    -------
    float
        POC price, or ``NaN`` when ``a_bars`` is empty or all volumes are zero.
    """
    if a_bars.empty:
        return float("nan")

    typical = (
        pd.to_numeric(a_bars["high"], errors="coerce")
        + pd.to_numeric(a_bars["low"], errors="coerce")
        + pd.to_numeric(a_bars["close"], errors="coerce")
    ) / 3.0
    volumes = pd.to_numeric(a_bars["volume"], errors="coerce")

    # _compute_profile returns (vah, val, poc); we only need poc.
    _, _, poc = _compute_profile(
        typical.values,
        volumes.values,
        tick_size=tick_size,
        value_area_pct=0.70,
    )
    return poc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_apoc_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    *,
    enabled: bool = False,
) -> pd.DataFrame:
    """Return A-Period POC level columns aligned to a sorted timestamp timeline.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column.  An optional
        ``session`` column (values ``"RTH"`` / ``"ETH"``) may be pre-attached;
        when it is absent, RTH membership is derived from ``instrument`` config.
    instrument:
        Instrument key recognised by ``thesistester.config.INSTRUMENTS``
        (e.g. ``"ES"``).  Used for tick-size binning.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately — no timestamp validation, no new columns.

    Returns
    -------
    pd.DataFrame
        - ``enabled=False``: empty DataFrame with the same index as *df*.
          Returns immediately without any processing.
        - ``enabled=True``: DataFrame with columns ``APOC`` and ``pAPOC``
          aligned to the **internally sorted** timestamp timeline
          (``sort_values("timestamp").reset_index(drop=True)``).  The returned
          index is a fresh ``RangeIndex`` matching the sorted row order.  When
          joining to other level DataFrames produced by ``compute_all_levels``,
          alignment is guaranteed because all level functions operate on the
          same sorted timeline.

    Raises
    ------
    ValueError
        If ``enabled=True`` and:
        - ``df["timestamp"]`` is timezone-naive,
        - ``instrument`` is not in ``INSTRUMENTS``.
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    # --- Validation (only when enabled) ---
    require_tz_aware_timestamp(df)

    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  "
            f"Supported instruments: {sorted(INSTRUMENTS)}"
        )

    inst = INSTRUMENTS[instrument]
    exchange_tz = inst.exchange_tz
    eth_start = getattr(inst, "eth_start", "") or ""
    rth_start_time = pd.to_datetime(inst.rth_start).time()

    # --- Sort and work on a copy so we never mutate the caller's frame ---
    work = df.sort_values("timestamp").reset_index(drop=True).copy()

    # --- Derive session membership ---
    if "session" not in work.columns:
        work = tag_session(work, instrument=instrument)

    # --- Attach trading-session date for grouping ---
    local_ts = work["timestamp"].dt.tz_convert(exchange_tz)
    work["_session_date"] = trading_session_date(local_ts, eth_start)

    is_rth = work["session"].eq("RTH")
    rth_work = work[is_rth]

    unique_sessions: List[datetime.date] = (
        sorted(rth_work["_session_date"].unique()) if len(rth_work) > 0 else []
    )

    # --- Per session: compute A-period POC and availability timestamp ---
    session_apoc: Dict[datetime.date, float] = {}
    session_apoc_avail_ts: Dict[datetime.date, pd.Timestamp] = {}

    for sess_date in unique_sessions:
        rth_open_ts = pd.Timestamp(
            year=sess_date.year,
            month=sess_date.month,
            day=sess_date.day,
            hour=rth_start_time.hour,
            minute=rth_start_time.minute,
            tz=exchange_tz,
        )
        a_period_end = rth_open_ts + pd.Timedelta(minutes=A_PERIOD_MINUTES)

        # A-period bars: RTH_open <= timestamp < RTH_open + 30min
        sess_rth = rth_work[rth_work["_session_date"] == sess_date]
        a_bars = sess_rth[
            (sess_rth["timestamp"] >= rth_open_ts)
            & (sess_rth["timestamp"] < a_period_end)
        ]

        session_apoc[sess_date] = _compute_a_period_poc(a_bars, inst.tick_size)
        session_apoc_avail_ts[sess_date] = a_period_end

    # --- Prior-session APOC per session ---
    sorted_sessions = sorted(session_apoc.keys())
    prior_apoc: Dict[datetime.date, float] = {
        sd: (session_apoc[sorted_sessions[i - 1]] if i > 0 else float("nan"))
        for i, sd in enumerate(sorted_sessions)
    }

    # --- Fill output arrays row by row ---
    n = len(work)
    apoc_arr = np.full(n, np.nan)
    papoc_arr = np.full(n, np.nan)

    sessions_col = work["session"].values
    session_dates_col = work["_session_date"].values
    timestamps = work["timestamp"]

    for i in range(n):
        if sessions_col[i] != "RTH":
            continue

        sess_date = session_dates_col[i]
        row_ts = timestamps.iloc[i]

        # APOC: emit only after A-period completion.
        avail_ts = session_apoc_avail_ts.get(sess_date)
        if avail_ts is not None and row_ts >= avail_ts:
            apoc_arr[i] = session_apoc[sess_date]

        # pAPOC: emit from the first RTH bar of the session (frozen).
        papoc_arr[i] = prior_apoc.get(sess_date, float("nan"))

    return pd.DataFrame(
        {COL_APOC: apoc_arr, COL_PAPOC: papoc_arr},
        index=work.index,
    )
