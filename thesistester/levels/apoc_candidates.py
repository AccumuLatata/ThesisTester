"""Pure candidate profiles for investigating Quantower A-period POC.

This module is intentionally not imported by :mod:`thesistester.levels.apoc`.
It supports AP1 evidence collection only and cannot change production APOC or
pAPOC output.  Candidates use a fixed lowest-price POC tie rule so their
histograms are deterministic; Quantower's tie behavior remains an empirical
question for the desk oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal, Mapping

import numpy as np
import pandas as pd

TYPICAL_MVP_V1: Final[str] = "typical_mvp_v1"
BAR_RANGE_UNIFORM_VOLUME_V1: Final[str] = "bar_range_uniform_volume_v1"
BAR_RANGE_TPO_V1: Final[str] = "bar_range_tpo_v1"
TICK_LAST_VOLUME_V1: Final[str] = "tick_last_volume_v1"
BAR_CANDIDATES: Final[tuple[str, ...]] = (
    TYPICAL_MVP_V1,
    BAR_RANGE_UNIFORM_VOLUME_V1,
    BAR_RANGE_TPO_V1,
)

APOCProfileCandidate = Literal[
    "typical_mvp_v1",
    "bar_range_uniform_volume_v1",
    "bar_range_tpo_v1",
    "tick_last_volume_v1",
]


class APOCProfileInputError(ValueError):
    """Raised when an AP1 candidate input violates the locked source contract."""


@dataclass(frozen=True)
class APOCProfileCandidateResult:
    """Auditable result of one candidate allocation.

    ``histogram`` has one row per inclusive tick bin and its index is the
    tick-grid price. ``source_volume`` is the valid input-bar/tick volume.
    ``allocated_volume`` equals source volume for volume candidates and equals
    the total TPO count for ``bar_range_tpo_v1``.
    """

    candidate: APOCProfileCandidate
    poc: float
    histogram: pd.Series
    source_rows: int
    source_volume: float
    allocated_volume: float


def select_a_period_rows(
    rows: pd.DataFrame,
    *,
    session_date: date | str | pd.Timestamp,
    exchange_tz: str,
    rth_start: str = "09:30",
    period_minutes: int = 30,
) -> pd.DataFrame:
    """Return rows in the half-open A-period in exchange time.

    The input ``timestamp`` column must be timezone-aware.  This helper makes
    no assumption about bar cadence: sparse trade-only bar sources remain
    eligible evidence, with their observed rows retained.
    """
    if "timestamp" not in rows.columns:
        raise APOCProfileInputError("A-period rows require a 'timestamp' column.")
    if period_minutes <= 0:
        raise APOCProfileInputError("period_minutes must be positive.")

    timestamps = pd.to_datetime(rows["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise APOCProfileInputError("A-period rows contain unparseable timestamps.")
    if timestamps.dt.tz is None:
        raise APOCProfileInputError("A-period rows require timezone-aware timestamps.")

    local = timestamps.dt.tz_convert(exchange_tz)
    session_day = pd.Timestamp(session_date).date()
    start_time = pd.to_datetime(rth_start).time()
    start = pd.Timestamp(
        year=session_day.year,
        month=session_day.month,
        day=session_day.day,
        hour=start_time.hour,
        minute=start_time.minute,
        second=start_time.second,
        tz=exchange_tz,
    )
    end = start + pd.Timedelta(minutes=period_minutes)
    selected = rows.loc[(local >= start) & (local < end)].copy()
    selected["timestamp"] = timestamps.loc[selected.index]
    return selected.sort_values("timestamp").reset_index(drop=True)


def compare_apoc_candidates(
    a_period_bars: pd.DataFrame,
    *,
    tick_size: float,
    a_period_ticks: pd.DataFrame | None = None,
) -> Mapping[str, APOCProfileCandidateResult]:
    """Compute all applicable AP1 candidates without production-level wiring."""
    results: dict[str, APOCProfileCandidateResult] = {
        candidate: compute_bar_candidate_profile(
            a_period_bars,
            candidate=candidate,
            tick_size=tick_size,
        )
        for candidate in BAR_CANDIDATES
    }
    if a_period_ticks is not None:
        results[TICK_LAST_VOLUME_V1] = compute_tick_last_volume_profile(
            a_period_ticks,
            tick_size=tick_size,
        )
    return results


def compute_bar_candidate_profile(
    a_period_bars: pd.DataFrame,
    *,
    candidate: APOCProfileCandidate,
    tick_size: float,
) -> APOCProfileCandidateResult:
    """Compute one bar-based candidate from already selected A-period bars."""
    _validate_tick_size(tick_size)
    if candidate not in BAR_CANDIDATES:
        raise APOCProfileInputError(f"Unsupported bar candidate: {candidate!r}.")
    bars = _validated_bars(a_period_bars, tick_size=tick_size)
    if bars.empty:
        return _empty_result(candidate)

    if candidate == TYPICAL_MVP_V1:
        prices = (bars["high"] + bars["low"] + bars["close"]) / 3.0
        volumes = bars["volume"]
        histogram = _histogram(prices, volumes, tick_size=tick_size)
        source_volume = float(volumes.sum())
    else:
        parts: list[pd.Series] = []
        for row in bars.itertuples(index=False):
            prices = _inclusive_tick_range(row.low, row.high, tick_size=tick_size)
            if candidate == BAR_RANGE_UNIFORM_VOLUME_V1:
                allocation = pd.Series(float(row.volume) / len(prices), index=prices)
            else:
                allocation = pd.Series(1.0, index=prices)
            parts.append(allocation)
        histogram = _merge_histogram_parts(parts)
        source_volume = float(bars["volume"].sum())

    return _result(
        candidate,
        histogram,
        source_rows=len(bars),
        source_volume=source_volume,
    )


def compute_tick_last_volume_profile(
    a_period_ticks: pd.DataFrame,
    *,
    tick_size: float,
) -> APOCProfileCandidateResult:
    """Compute the Tick–Tick–Last price × volume candidate for selected ticks."""
    _validate_tick_size(tick_size)
    required = ("price", "volume")
    missing = [column for column in required if column not in a_period_ticks.columns]
    if missing:
        raise APOCProfileInputError(f"Tick candidate requires columns: {missing}.")
    ticks = a_period_ticks.loc[:, list(required)].copy()
    for column in required:
        ticks[column] = pd.to_numeric(ticks[column], errors="coerce")
    if ticks.isna().any().any():
        raise APOCProfileInputError("Tick candidate contains missing or non-numeric price/volume.")
    if (ticks["volume"] <= 0).any():
        raise APOCProfileInputError("Tick candidate requires strictly positive volume.")
    _require_tick_grid(ticks["price"], tick_size=tick_size, field="tick price")
    histogram = _histogram(ticks["price"], ticks["volume"], tick_size=tick_size)
    return _result(
        TICK_LAST_VOLUME_V1,
        histogram,
        source_rows=len(ticks),
        source_volume=float(ticks["volume"].sum()),
    )


def _validated_bars(a_period_bars: pd.DataFrame, *, tick_size: float) -> pd.DataFrame:
    required = ("high", "low", "close", "volume")
    missing = [column for column in required if column not in a_period_bars.columns]
    if missing:
        raise APOCProfileInputError(f"Bar candidate requires columns: {missing}.")
    bars = a_period_bars.loc[:, list(required)].copy()
    for column in required:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.isna().any().any():
        raise APOCProfileInputError("Bar candidate contains missing or non-numeric OHLCV values.")
    if (bars["volume"] < 0).any():
        raise APOCProfileInputError("Bar candidate volume cannot be negative.")
    if (bars["high"] < bars["low"]).any():
        raise APOCProfileInputError("Bar candidate contains high below low.")
    if ((bars["close"] < bars["low"]) | (bars["close"] > bars["high"])).any():
        raise APOCProfileInputError("Bar candidate close must be inside high/low.")
    _require_tick_grid(bars["high"], tick_size=tick_size, field="bar high")
    _require_tick_grid(bars["low"], tick_size=tick_size, field="bar low")
    return bars.loc[bars["volume"] > 0].reset_index(drop=True)


def _result(
    candidate: APOCProfileCandidate,
    histogram: pd.Series,
    *,
    source_rows: int,
    source_volume: float,
) -> APOCProfileCandidateResult:
    if histogram.empty:
        return _empty_result(candidate)
    # ``histogram`` is already on the candidate's tick grid and sorted by
    # price. np.argmax therefore makes the tie rule explicit: lowest bin wins.
    poc = float(histogram.index[int(np.argmax(histogram.to_numpy(dtype="float64")))])
    allocated = float(histogram.sum())
    return APOCProfileCandidateResult(
        candidate=candidate,
        poc=float(poc),
        histogram=histogram,
        source_rows=source_rows,
        source_volume=source_volume,
        allocated_volume=allocated,
    )


def _empty_result(candidate: APOCProfileCandidate) -> APOCProfileCandidateResult:
    return APOCProfileCandidateResult(
        candidate=candidate,
        poc=float("nan"),
        histogram=pd.Series(dtype="float64", name="allocation"),
        source_rows=0,
        source_volume=0.0,
        allocated_volume=0.0,
    )


def _histogram(prices: pd.Series, volumes: pd.Series, *, tick_size: float) -> pd.Series:
    bins = np.round(prices.to_numpy(dtype="float64") / tick_size) * tick_size
    frame = pd.DataFrame({"bin": bins.round(10), "allocation": volumes.to_numpy(dtype="float64")})
    return frame.groupby("bin", sort=True)["allocation"].sum().astype("float64")


def _inclusive_tick_range(low: float, high: float, *, tick_size: float) -> np.ndarray:
    low_tick = int(round(low / tick_size))
    high_tick = int(round(high / tick_size))
    return (np.arange(low_tick, high_tick + 1, dtype="float64") * tick_size).round(10)


def _merge_histogram_parts(parts: list[pd.Series]) -> pd.Series:
    if not parts:
        return pd.Series(dtype="float64", name="allocation")
    histogram = pd.concat(parts).groupby(level=0, sort=True).sum().astype("float64")
    histogram.index.name = "bin"
    histogram.name = "allocation"
    return histogram


def _validate_tick_size(tick_size: float) -> None:
    if not isinstance(tick_size, (int, float, np.floating)) or not np.isfinite(tick_size):
        raise APOCProfileInputError("tick_size must be a finite positive number.")
    if tick_size <= 0:
        raise APOCProfileInputError("tick_size must be a finite positive number.")


def _require_tick_grid(values: pd.Series, *, tick_size: float, field: str) -> None:
    ticks = values.to_numpy(dtype="float64") / tick_size
    if not np.isclose(ticks, np.round(ticks), rtol=0.0, atol=1e-8).all():
        raise APOCProfileInputError(f"{field} must lie on the {tick_size:g} tick grid.")
