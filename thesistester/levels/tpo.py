"""TPO / Single-Print and APOC level computation — Stage 4 implementation.

Stage 4 implements the scalar Single Print contract.  APOC / pAPOC remain
stubs until Stage 5.

Output columns (Single Prints — Stage 4):
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

Single Print definition (Stage 4):
    A price bin (sized by instrument tick_size) is a Single Print when it is
    covered by exactly one completed 30-minute RTH bracket within the session.
    Bins touched by zero or more-than-one brackets are excluded.

    Developing Single Prints (``d`` prefix):
        - Computed from completed 30-minute RTH brackets in the current session.
        - The current incomplete bracket is never included.
        - Values update causally as new brackets complete.
        - Non-RTH bars emit NaN.

    Prior-session Single Prints (``p`` prefix):
        - The previous completed RTH session's frozen Single Print set.
        - Mapped forward once at the start of the next session.
        - NaN if the prior session had no Single Prints.
        - Non-RTH bars emit NaN.

Point-in-time guarantee:
    For every row at timestamp T, only completed 30-minute brackets whose end
    time is ≤ T were used.  Appending future bars cannot alter Single Print
    values at prior timestamps.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, FrozenSet, List, Set, Tuple

import numpy as np
import pandas as pd

from ..config import INSTRUMENTS
from ..data.sessions import tag_session
from .common import require_tz_aware_timestamp
from .session_date import trading_session_date

# TPO bracket width for Single Prints.
TPO_BRACKET_MINUTES: int = 30

# Output column names.
COL_D_ABOVE = "dSinglePrint_30m_NearestAbove"
COL_D_BELOW = "dSinglePrint_30m_NearestBelow"
COL_P_ABOVE = "pSinglePrint_30m_NearestAbove"
COL_P_BELOW = "pSinglePrint_30m_NearestBelow"

SINGLE_PRINT_COLUMNS: Tuple[str, ...] = (
    COL_D_ABOVE,
    COL_D_BELOW,
    COL_P_ABOVE,
    COL_P_BELOW,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _round_to_tick(price: float, tick_size: float) -> int:
    """Return price expressed as an integer number of ticks (deterministic)."""
    # Use round() with a scale factor to avoid floating-point drift.
    return round(price / tick_size)


def _bins_in_bracket(low: float, high: float, tick_size: float) -> FrozenSet[int]:
    """Return the set of tick-bin integers covered by [low, high]."""
    lo_tick = _round_to_tick(low, tick_size)
    hi_tick = _round_to_tick(high, tick_size)
    return frozenset(range(lo_tick, hi_tick + 1))


def _single_print_prices(bracket_bins: List[FrozenSet[int]], tick_size: float) -> List[float]:
    """Return sorted list of price-bin prices touched by exactly one bracket."""
    touch_count: Dict[int, int] = defaultdict(int)
    for bins in bracket_bins:
        for b in bins:
            touch_count[b] += 1
    sp_bins = sorted(k for k, v in touch_count.items() if v == 1)
    return [b * tick_size for b in sp_bins]


def _nearest_above(prices: List[float], close: float) -> float:
    """Closest Single Print price strictly above *close*, or NaN."""
    candidates = [p for p in prices if p > close]
    return float(min(candidates)) if candidates else float("nan")


def _nearest_below(prices: List[float], close: float) -> float:
    """Closest Single Print price strictly below *close*, or NaN."""
    candidates = [p for p in prices if p < close]
    return float(max(candidates)) if candidates else float("nan")


def _compute_single_prints(
    work: pd.DataFrame,
    instrument: str,
) -> pd.DataFrame:
    """Core Single Print computation, operating on a sorted working copy.

    Parameters
    ----------
    work:
        Sorted OHLCV DataFrame with tz-aware ``timestamp``, ``session``
        (``"RTH"``/``"ETH"``), and ``_session_date`` columns added by the caller.
    instrument:
        Instrument key from INSTRUMENTS.

    Returns
    -------
    pd.DataFrame
        Four Single Print columns with the same RangeIndex as *work*.
    """
    inst = INSTRUMENTS[instrument]
    tick_size = inst.tick_size
    bracket_minutes = TPO_BRACKET_MINUTES

    n = len(work)
    d_above = np.full(n, np.nan)
    d_below = np.full(n, np.nan)
    p_above = np.full(n, np.nan)
    p_below = np.full(n, np.nan)

    # --- Resample RTH bars into 30-minute brackets per session date ---
    # We need to identify, for each base-bar row, which 30-minute brackets have
    # *completed* by the time that row's timestamp is reached.
    #
    # Strategy:
    #   1. For each session date, collect all RTH bars in timestamp order.
    #   2. Assign each RTH bar to its 30-minute bucket (floor of minutes since
    #      RTH open, divided by 30).
    #   3. A bucket is "completed" once the first bar of the *next* bucket (or the
    #      first non-RTH bar after RTH close) appears.  We implement this as:
    #      a bracket ending at bucket_end_time <= current bar timestamp.
    #   4. At each base-bar row, the set of completed brackets determines the
    #      developing Single Prints.
    #
    # For prior-session: once a session is fully complete (all its RTH bars have been
    # seen), its Single Print set is frozen and mapped forward into the next session.

    exchange_tz = inst.exchange_tz
    rth_start_time = pd.to_datetime(inst.rth_start).time()

    # --- Build per-session bracket information ---
    # For each session_date, collect (bracket_end_timestamp, bins) pairs in order.
    # bracket_end_timestamp = RTH_open + (bucket_idx + 1) * 30min
    # This is the *exclusive* end (the first bar of the next bucket confirms the bracket).

    # Group RTH bars by session date.
    is_rth = work["session"].eq("RTH")
    rth_work = work[is_rth].copy()

    # Compute RTH open time for each session date:
    # RTH open = session_date + rth_start_time in exchange_tz.
    unique_sessions = sorted(rth_work["_session_date"].unique()) if len(rth_work) > 0 else []

    # Per session: list of (bracket_end_ts, bins_frozenset) in ascending order.
    # bracket_end_ts is the timestamp at which the bracket *becomes available*:
    # i.e. rth_open + (bucket_idx+1) * 30min.
    session_brackets: Dict[object, List[Tuple[pd.Timestamp, FrozenSet[int]]]] = {}  # date -> list of (end_ts, bins)

    for sess_date in unique_sessions:
        rth_open_ts = pd.Timestamp(
            year=sess_date.year,
            month=sess_date.month,
            day=sess_date.day,
            hour=rth_start_time.hour,
            minute=rth_start_time.minute,
            tz=exchange_tz,
        )
        sess_rth = rth_work[rth_work["_session_date"] == sess_date].sort_values("timestamp")

        # Assign each bar to a bucket index.
        elapsed_minutes = (
            sess_rth["timestamp"].dt.tz_convert(exchange_tz) - rth_open_ts
        ).dt.total_seconds() / 60.0

        bucket_idx = (elapsed_minutes // bracket_minutes).astype(int)

        # Group by bucket, accumulate bins.
        bucket_bins: Dict[int, Set[int]] = {}
        for bidx, (_, row) in zip(bucket_idx.values, sess_rth.iterrows()):
            bins = _bins_in_bracket(row["low"], row["high"], tick_size)
            if bidx not in bucket_bins:
                bucket_bins[bidx] = set()
            bucket_bins[bidx].update(bins)

        # Build ordered list of (end_ts, bins_frozenset) for completed brackets.
        brackets = []
        for bidx in sorted(bucket_bins.keys()):
            end_ts = rth_open_ts + pd.Timedelta(minutes=(bidx + 1) * bracket_minutes)
            brackets.append((end_ts, frozenset(bucket_bins[bidx])))

        session_brackets[sess_date] = brackets

    # --- Compute prior-session SP set per session ---
    # For session S, the prior-session SP set is the SP set of the session just before S.
    sorted_session_dates = sorted(session_brackets.keys())
    prior_sp_prices: Dict[object, List[float]] = {}  # date -> list of SP prices (from prior session)
    for i, sess_date in enumerate(sorted_session_dates):
        if i == 0:
            prior_sp_prices[sess_date] = []
        else:
            prev_date = sorted_session_dates[i - 1]
            prev_brackets = session_brackets[prev_date]
            prev_bins = [b for (_end, b) in prev_brackets]
            prior_sp_prices[sess_date] = _single_print_prices(prev_bins, tick_size)

    # --- Fill output arrays row by row using sorted work index ---
    # Iterate rows in timestamp order and use only brackets completed by row timestamp.
    closes = work["close"].values
    sessions_col = work["session"].values
    session_dates_col = work["_session_date"].values

    for i in range(n):
        sess_date = session_dates_col[i]
        row_ts = work["timestamp"].iloc[i]
        row_close = closes[i]
        is_row_rth = sessions_col[i] == "RTH"

        # --- Developing Single Prints ---
        if is_row_rth:
            brackets = session_brackets.get(sess_date, [])
            # Collect brackets whose end_ts <= row_ts (completed by this bar).
            completed_bins = [bins for (end_ts, bins) in brackets if end_ts <= row_ts]
            if completed_bins:
                sp_prices = _single_print_prices(completed_bins, tick_size)
                d_above[i] = _nearest_above(sp_prices, row_close)
                d_below[i] = _nearest_below(sp_prices, row_close)
            # else: NaN (no completed bracket yet)
        # non-RTH: remain NaN

        # --- Prior-session Single Prints ---
        if is_row_rth:
            ps_prices = prior_sp_prices.get(sess_date, [])
            if ps_prices:
                p_above[i] = _nearest_above(ps_prices, row_close)
                p_below[i] = _nearest_below(ps_prices, row_close)
            # else: NaN (prior session had no SP or no prior session)
        # non-RTH: remain NaN

    return pd.DataFrame(
        {
            COL_D_ABOVE: d_above,
            COL_D_BELOW: d_below,
            COL_P_ABOVE: p_above,
            COL_P_BELOW: p_below,
        },
        index=work.index,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_tpo_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    *,
    single_prints_enabled: bool = False,
    apoc_enabled: bool = False,
) -> pd.DataFrame:
    """Return TPO-based level columns.

    Parameters
    ----------
    df:
        OHLCV DataFrame with a tz-aware ``timestamp`` column.  An optional
        ``session`` column (values ``"RTH"``/``"ETH"``) can be pre-attached;
        when it is absent, RTH membership is derived from ``instrument`` config
        and the timestamp timezone.
    instrument:
        Instrument key recognised by ``thesistester.config.INSTRUMENTS``
        (e.g. ``"ES"``).  Used for tick-size binning.
    single_prints_enabled:
        When ``True``, compute the four Single Print scalar columns.
        Defaults to ``False``.
    apoc_enabled:
        When ``True``, would compute APOC / pAPOC columns.
        Not yet implemented (Stage 5); always raises ``NotImplementedError``.

    Returns
    -------
    pd.DataFrame
        - Both gates ``False``: empty DataFrame with the same index as *df*.
          True no-op — no timestamp validation, no new columns.
        - ``single_prints_enabled=True``, ``apoc_enabled=False``:
          DataFrame with columns
          ``dSinglePrint_30m_NearestAbove``, ``dSinglePrint_30m_NearestBelow``,
          ``pSinglePrint_30m_NearestAbove``, ``pSinglePrint_30m_NearestBelow``
          aligned to the **internally sorted** timestamp timeline
          (``sort_values("timestamp").reset_index(drop=True)``).

    Raises
    ------
    NotImplementedError
        If ``apoc_enabled=True`` (Stage 5, not yet implemented).
    ValueError
        If ``single_prints_enabled=True`` and:
        - ``df["timestamp"]`` is timezone-naive,
        - ``instrument`` is not in ``INSTRUMENTS``.
    """
    if not single_prints_enabled and not apoc_enabled:
        return pd.DataFrame(index=df.index)

    require_tz_aware_timestamp(df)

    if apoc_enabled:
        raise NotImplementedError(
            "APOC / pAPOC computation is not yet implemented (Stage 5).  "
            "Set apoc_enabled=False until Stage 5 is merged."
        )

    # single_prints_enabled=True from here onward.
    if instrument not in INSTRUMENTS:
        raise ValueError(
            f"Unsupported instrument: {instrument!r}.  "
            f"Supported instruments: {sorted(INSTRUMENTS)}"
        )

    # Sort and copy — never mutate the caller's frame.
    work = df.sort_values("timestamp").reset_index(drop=True).copy()

    # Derive session membership.
    if "session" not in work.columns:
        work = tag_session(work, instrument=instrument)

    # Attach trading-session date for grouping.
    inst = INSTRUMENTS[instrument]
    exchange_tz = inst.exchange_tz
    eth_start = getattr(inst, "eth_start", "") or ""
    local_ts = work["timestamp"].dt.tz_convert(exchange_tz)
    work["_session_date"] = trading_session_date(local_ts, eth_start)

    result = _compute_single_prints(work, instrument)

    return result
