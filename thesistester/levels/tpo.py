"""TPO / Single-Print and APOC level computation stubs — Stage 1 plumbing only.

Full TPO logic (30-minute bracket binning, scalar nearest-above/below single-print
levels, APOC, pAPOC) will be implemented in Stages 4 and 5.  Until then every public
function in this module returns an empty DataFrame so that ``compute_all_levels`` can
wire these calls behind settings gates without any behaviour change.

Planned output columns:

Single Prints (Stage 4 — scalar contract, no dynamic columns):
    dSinglePrint_30m_NearestAbove   — developing (current session, completed brackets)
    dSinglePrint_30m_NearestBelow
    pSinglePrint_30m_NearestAbove   — prior session frozen
    pSinglePrint_30m_NearestBelow

APOC / pAPOC (Stage 5):
    APOC    — POC of the first completed RTH 30-minute bracket
    pAPOC   — prior session's APOC

Important architectural note:
    Single Prints are naturally multi-price structures; the current level engine
    uses scalar timeline columns.  To stay compatible the first implementation
    exposes only NearestAbove / NearestBelow summaries.  No dynamic SP_1, SP_2, …
    columns will be generated.
"""
from __future__ import annotations

import pandas as pd

from .common import require_tz_aware_timestamp

# TPO bracket width for Single Prints.
TPO_BRACKET_MINUTES: int = 30


def compute_tpo_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    *,
    single_prints_enabled: bool = False,
    apoc_enabled: bool = False,
) -> pd.DataFrame:
    """Return TPO-based level columns aligned to *df*'s index.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column and a ``session``
        column (added by :func:`~thesistester.data.sessions.tag_session`).
    instrument:
        Instrument key (e.g. ``"ES"``).  Used for tick-size binning in Stages 4-5.
    single_prints_enabled:
        When ``True``, compute Single Print scalar columns.  Defaults to ``False``.
        Not yet implemented (Stage 4).
    apoc_enabled:
        When ``True``, compute APOC / pAPOC columns.  Defaults to ``False``.
        Not yet implemented (Stage 5).

    Returns
    -------
    pd.DataFrame
        Empty DataFrame when both gates are ``False`` (Stage 1 no-op).
        Will return Single Print and/or APOC columns aligned to *df*'s index
        in Stages 4 and 5.
    """
    if not single_prints_enabled and not apoc_enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)

    # Stage 4 / Stage 5 implementations will go here.
    raise NotImplementedError(  # pragma: no cover
        "TPO level computation is not yet implemented.  "
        "Set single_prints_enabled=False and apoc_enabled=False (the defaults) "
        "until Stages 4-5 are merged."
    )
