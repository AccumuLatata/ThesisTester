"""Session VWAP level computation — Stage 3 implementation.

Implements developing VWAP anchored to the RTH session open (``dVWAP_RTH``).

Output column
-------------
``dVWAP_RTH``
    Developing VWAP from the RTH session open.  Resets at each new RTH session.
    ``NaN`` on bars outside RTH (before session open and after session close).
    ``NaN`` when cumulative RTH volume is zero.

Formula
-------
    typical_price = (high + low + close) / 3
    dVWAP_RTH[t] = cumsum(typical_price * volume)[t] / cumsum(volume)[t]

    ``cumsum`` resets at each RTH session open and includes only RTH bars.
    Non-RTH bars always emit ``NaN``.

Point-in-time guarantee
-----------------------
    At bar ``t``, only RTH bars at or before ``t`` (in the same session) are
    used.  No future RTH bar can change the value at ``t``.

Disabled behavior (``enabled=False``)
--------------------------------------
    Returns an empty DataFrame immediately — no timestamp validation, no new
    columns.  This preserves the Stage 1 no-op contract.

Unsupported anchor
------------------
    Raises ``ValueError``.  Only ``"RTH"`` is supported in Stage 3.

A later extension may add ``dVWAP_ETH`` when the session model cleanly supports it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..data.sessions import tag_session
from .common import require_tz_aware_timestamp
from .session_date import trading_session_date

# Anchor options supported in Stage 3.
SUPPORTED_VWAP_ANCHORS: tuple[str, ...] = ("RTH",)

# Default anchor for the first implementation.
DEFAULT_VWAP_ANCHOR: str = "RTH"


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
        Session anchor for VWAP reset.  Currently only ``"RTH"`` is supported.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately — no timestamp validation, no new columns.

    Returns
    -------
    pd.DataFrame
        - ``enabled=False``: empty DataFrame with the same index as *df*.
        - ``enabled=True``: DataFrame with column ``dVWAP_RTH`` aligned to *df*.

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
            f"Unsupported instrument: {instrument!r}.  "
            f"Supported instruments: {sorted(INSTRUMENTS)}"
        )

    if anchor not in SUPPORTED_VWAP_ANCHORS:
        raise ValueError(
            f"Unsupported VWAP anchor: {anchor!r}.  "
            f"Supported anchors: {list(SUPPORTED_VWAP_ANCHORS)}"
        )

    # --- Sort and work on a copy so we never mutate the caller's frame ---
    work = df.sort_values("timestamp").reset_index(drop=True).copy()

    # --- Derive session membership ---
    if "session" not in work.columns:
        work = tag_session(work, instrument=instrument)

    # --- Compute RTH session date for grouping ---
    inst = INSTRUMENTS[instrument]
    exchange_tz = inst.exchange_tz
    eth_start = getattr(inst, "eth_start", "") or ""
    local_ts = work["timestamp"].dt.tz_convert(exchange_tz)
    session_date = trading_session_date(local_ts, eth_start)

    # --- Build dVWAP_RTH ---
    is_rth = work["session"].eq("RTH")
    typical = (work["high"] + work["low"] + work["close"]) / 3.0
    pv = typical * work["volume"]

    # Group by RTH session date; accumulate pv and volume cumulatively within group.
    # Non-RTH bars are excluded from the cumulative computation and receive NaN.
    dvwap = pd.Series(np.nan, index=work.index, dtype="float64")

    for _date, idx in work[is_rth].groupby(session_date[is_rth], sort=True).groups.items():
        cum_pv = pv.loc[idx].cumsum()
        cum_vol = work["volume"].loc[idx].cumsum()
        # Emit NaN when cumulative volume is zero (prevents divide-by-zero).
        dvwap.loc[idx] = cum_pv.where(cum_vol > 0).div(cum_vol.replace(0, np.nan))

    out = pd.DataFrame({"dVWAP_RTH": dvwap}, index=work.index)

    # Re-align to original df index order if df was not sorted.
    if not df.index.equals(work.index):
        # double argsort produces the inverse permutation: position i in `out`
        # (sorted order) maps back to the original row position in df.
        inverse_sort_indices = df["timestamp"].argsort().argsort()
        out = out.iloc[inverse_sort_indices.values].set_axis(df.index)

    return out
