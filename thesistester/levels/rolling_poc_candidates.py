"""Sampled-stamp rolling-POC comparison harness (RP1).

Comparison-only. Production ``_rolling_poc`` / ``compute_profile_levels`` are
not imported and are not called. Histogram builders are reused from
:mod:`thesistester.levels.apoc_candidates`. Window membership is independent
of the A-period row selector.

Window lock
-----------
* Members: 1m bar opens in ``(now - W, now]`` (same half-open as
  ``_rolling_poc``). Not clipped to RTH.
* Prints: theoretical ``[now - W + bar_interval, now + bar_interval)``.
  Default ``bar_interval`` is ``1min``, so a 30m window at 10:00 NY is
  ``[09:31, 10:01)``. This is **not** ``min/max(members)``: dropping an
  interior 1m row skips that member; the print interval is unchanged.

Candidates
----------
1m typical / uniform-range / TPO use member bars. Scorecard bar-range is
**1m** (declared in result metadata). 15s typical is a **label**: the
harness calls ``compute_bar_candidate_profile(..., candidate="typical_mvp_v1")``
on 15s rows in the print window and stores the result as
``typical_mvp_15s_v1``. That label is not added to ``BAR_CANDIDATES``.

``APOCProfileInputError`` from a builder is caught and stamped ``NaN`` for
that candidate. The tick helper itself is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Mapping

import pandas as pd

from .apoc_candidates import (
    BAR_CANDIDATES,
    TICK_LAST_VOLUME_V1,
    TYPICAL_MVP_V1,
    APOCProfileCandidateResult,
    APOCProfileInputError,
    compute_bar_candidate_profile,
    compute_tick_last_volume_profile,
)
from .common import require_tz_aware_timestamp

TYPICAL_MVP_15S_V1: Final[str] = "typical_mvp_15s_v1"
BAR_RANGE_INPUT_1M: Final[str] = "1m"


@dataclass(frozen=True)
class RollingPOCComparison:
    """Auditable sampled-stamp comparison. Not a production level row."""

    now: pd.Timestamp
    window: pd.Timedelta
    members: pd.DataFrame
    print_start: pd.Timestamp
    print_end: pd.Timestamp
    bar_range_input: Literal["1m"]
    candidates: Mapping[str, APOCProfileCandidateResult]


def select_rolling_member_bars(
    bars: pd.DataFrame,
    now: pd.Timestamp,
    window: str | pd.Timedelta,
) -> pd.DataFrame:
    """Return 1m (or other) bars whose opens fall in ``(now - W, now]``.

    Membership matches ``_rolling_poc``: ``timestamp > now - W`` and
    ``timestamp <= now``. Sparse observed rows are kept; missing minutes are
    not imputed. Session tags are ignored (not RTH-clipped).
    """
    require_tz_aware_timestamp(bars)
    now_ts = _require_aware_now(now)
    window_td = pd.to_timedelta(window)
    if window_td <= pd.Timedelta(0):
        raise ValueError("window must be a positive Timedelta.")

    work = bars.copy()
    timestamps = pd.to_datetime(work["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("rolling member bars contain unparseable timestamps.")
    start = now_ts - window_td
    selected = work.loc[(timestamps > start) & (timestamps <= now_ts)].copy()
    selected["timestamp"] = timestamps.loc[selected.index]
    return selected.sort_values("timestamp").reset_index(drop=True)


def rolling_print_window(
    now: pd.Timestamp,
    window: str | pd.Timedelta,
    bar_interval: str = "1min",
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the theoretical print interval ``[now-W+interval, now+interval)``.

    Independent of observed member opens. A missing interior 1m row does not
    shrink this interval.
    """
    now_ts = _require_aware_now(now)
    window_td = pd.to_timedelta(window)
    interval_td = pd.to_timedelta(bar_interval)
    if window_td <= pd.Timedelta(0):
        raise ValueError("window must be a positive Timedelta.")
    if interval_td <= pd.Timedelta(0):
        raise ValueError("bar_interval must be a positive Timedelta.")
    return now_ts - window_td + interval_td, now_ts + interval_td


def compare_rolling_poc_candidates(
    bars_1m: pd.DataFrame,
    *,
    now: pd.Timestamp,
    window: str | pd.Timedelta = "30min",
    tick_size: float,
    bars_15s: pd.DataFrame | None = None,
    ticks: pd.DataFrame | None = None,
    bar_interval: str = "1min",
) -> RollingPOCComparison:
    """Compute rolling-POC candidate POCs at one stamp.

    Does not call production profile or A-period helpers. Bar-range metadata
    is always ``1m`` (scorecard column). Optional 15s / tick frames are
    filtered to the theoretical print window.
    """
    members = select_rolling_member_bars(bars_1m, now, window)
    print_start, print_end = rolling_print_window(now, window, bar_interval=bar_interval)
    now_ts = _require_aware_now(now)
    window_td = pd.to_timedelta(window)

    candidates: dict[str, APOCProfileCandidateResult] = {}
    for token in BAR_CANDIDATES:
        candidates[token] = _safe_bar_profile(members, candidate=token, tick_size=tick_size)

    if bars_15s is not None:
        try:
            selected_15s = _rows_in_print_window(bars_15s, print_start, print_end)
            candidates[TYPICAL_MVP_15S_V1] = _safe_bar_profile(
                selected_15s, candidate=TYPICAL_MVP_V1, tick_size=tick_size
            )
        except APOCProfileInputError:
            candidates[TYPICAL_MVP_15S_V1] = _empty_result(TYPICAL_MVP_V1)

    if ticks is not None:
        try:
            selected_ticks = _rows_in_print_window(ticks, print_start, print_end)
            candidates[TICK_LAST_VOLUME_V1] = _safe_tick_profile(
                selected_ticks, tick_size=tick_size
            )
        except APOCProfileInputError:
            candidates[TICK_LAST_VOLUME_V1] = _empty_result(TICK_LAST_VOLUME_V1)

    return RollingPOCComparison(
        now=now_ts,
        window=window_td,
        members=members,
        print_start=print_start,
        print_end=print_end,
        bar_range_input="1m",
        candidates=candidates,
    )


def _require_aware_now(now: pd.Timestamp) -> pd.Timestamp:
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        raise ValueError("now must be timezone-aware.")
    return now_ts


def _rows_in_print_window(
    rows: pd.DataFrame,
    print_start: pd.Timestamp,
    print_end: pd.Timestamp,
) -> pd.DataFrame:
    if "timestamp" not in rows.columns:
        raise APOCProfileInputError("Print-window rows require a 'timestamp' column.")
    work = rows.copy()
    timestamps = pd.to_datetime(work["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise APOCProfileInputError("Print-window rows contain unparseable timestamps.")
    if timestamps.dt.tz is None:
        raise APOCProfileInputError("Print-window rows require timezone-aware timestamps.")
    selected = work.loc[(timestamps >= print_start) & (timestamps < print_end)].copy()
    selected["timestamp"] = timestamps.loc[selected.index]
    return selected.sort_values("timestamp").reset_index(drop=True)


def _empty_result(candidate: str) -> APOCProfileCandidateResult:
    return APOCProfileCandidateResult(
        candidate=candidate,  # type: ignore[arg-type]
        poc=float("nan"),
        histogram=pd.Series(dtype="float64", name="allocation"),
        source_rows=0,
        source_volume=0.0,
        allocated_volume=0.0,
    )


def _safe_bar_profile(
    bars: pd.DataFrame,
    *,
    candidate: str,
    tick_size: float,
) -> APOCProfileCandidateResult:
    try:
        return compute_bar_candidate_profile(bars, candidate=candidate, tick_size=tick_size)
    except APOCProfileInputError:
        return _empty_result(candidate)


def _safe_tick_profile(ticks: pd.DataFrame, *, tick_size: float) -> APOCProfileCandidateResult:
    try:
        return compute_tick_last_volume_profile(ticks, tick_size=tick_size)
    except APOCProfileInputError:
        return _empty_result(TICK_LAST_VOLUME_V1)
