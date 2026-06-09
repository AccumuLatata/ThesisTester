"""Session VWAP level computation stubs — Stage 1 plumbing only.

Full developing-VWAP logic (cumulative session VWAP from RTH open, per-session reset,
zero-volume-safe) will be implemented in Stage 3.  Until then every public function in
this module returns an empty DataFrame so that ``compute_all_levels`` can wire these
calls behind settings gates without any behaviour change.

Planned output columns (Stage 3):
    dVWAP_RTH

Formula:
    dVWAP_RTH[t] = cumsum(typical_price * volume) / cumsum(volume)
    where typical_price = (high + low + close) / 3
    cumsum resets at each RTH session open.
    NaN before the RTH open of that session day.

A later extension may add dVWAP_ETH when the session model cleanly supports it.
"""
from __future__ import annotations

import pandas as pd

from .common import require_tz_aware_timestamp

# Anchor options that will be supported in Stage 3.
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
        OHLCV DataFrame with a tz-aware ``timestamp`` column and a ``session``
        column (added by :func:`~thesistester.data.sessions.tag_session`).
    instrument:
        Instrument key (e.g. ``"ES"``).  Used for session calendar configuration
        in Stage 3.
    anchor:
        Session anchor for VWAP reset.  Currently only ``"RTH"`` is planned.
    enabled:
        Master gate.  When ``False`` (the default), returns an empty DataFrame
        immediately so that no new columns are added by ``compute_all_levels``.

    Returns
    -------
    pd.DataFrame
        Empty DataFrame when ``enabled=False`` (Stage 1 no-op).
        Will return ``dVWAP_RTH`` (and optionally ``dVWAP_ETH``) in Stage 3.
    """
    if not enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)

    # Stage 3 implementation will go here.
    raise NotImplementedError(  # pragma: no cover
        "Session VWAP level computation is not yet implemented.  "
        "Set enabled=False (the default) until Stage 3 is merged."
    )
