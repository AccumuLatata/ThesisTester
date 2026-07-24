"""Pure OTF signal eligibility filter (PR 3).

This module evaluates already-generated candidate signals against the shared
OTF engine and returns accepted and rejected signals separately.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .otf import OTF_CANONICAL_TIMEFRAMES, calculate_otf_state

_TIMEFRAME_ALIASES: dict[str, str] = {
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
}

_VALID_DIRECTIONS = frozenset({"long", "short"})


def apply_otf_filter(
    source_df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    enabled: bool = False,
    timeframes: Sequence[str] = (),
    alignment_mode: str = "all",
    minimum_consecutive_bars: int = 3,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    session_reset: str = "session",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply OTF eligibility filtering to candidate signals.

    Returns a tuple of ``(accepted_signals, rejected_signals)``.
    """
    _validate_config(
        enabled=enabled,
        timeframes=timeframes,
        alignment_mode=alignment_mode,
        minimum_consecutive_bars=minimum_consecutive_bars,
        session_reset=session_reset,
    )
    normalized_timeframes = _normalize_timeframes(timeframes)

    signal_copy = signals.copy(deep=True)

    if not enabled:
        accepted = signal_copy.copy(deep=True)
        accepted["otf_filter_enabled"] = False
        accepted["otf_filter_passed"] = True
        accepted["otf_filter_reason"] = None
        rejected = accepted.iloc[0:0].copy()
        return accepted, rejected

    _validate_signal_directions(signal_copy)
    decision_timestamps = select_signal_decision_timestamp(
        signal_copy,
        session_timezone=session_timezone,
    )

    evaluated = signal_copy.copy(deep=True)
    evaluated["otf_signal_decision_timestamp"] = decision_timestamps
    evaluated["_otf_row_order"] = range(len(evaluated))

    for timeframe in normalized_timeframes:
        state, sequence_length, reference_timestamp = _align_otf_state(
            source_df,
            evaluated,
            timeframe=timeframe,
            minimum_consecutive_bars=minimum_consecutive_bars,
            session_timezone=session_timezone,
            eth_start=eth_start,
            session_reset=session_reset,
        )
        evaluated[f"otf_{timeframe}_state"] = state
        evaluated[f"otf_{timeframe}_sequence_length"] = sequence_length
        evaluated[f"otf_{timeframe}_reference_timestamp"] = reference_timestamp

    passed_flags: list[bool] = []
    reasons: list[str | None] = []
    for _, row in evaluated.iterrows():
        passed, reason = _evaluate_signal_eligibility(row, normalized_timeframes)
        passed_flags.append(passed)
        reasons.append(reason)

    evaluated["otf_filter_enabled"] = True
    evaluated["otf_filter_passed"] = passed_flags
    evaluated["otf_filter_reason"] = reasons

    evaluated = evaluated.sort_values("_otf_row_order", kind="stable")
    evaluated = evaluated.drop(columns=["_otf_row_order"]).reset_index(drop=True)

    accepted = evaluated[evaluated["otf_filter_passed"]].copy()
    rejected = evaluated[~evaluated["otf_filter_passed"]].copy()
    return accepted, rejected


def select_signal_decision_timestamp(
    signals: pd.DataFrame,
    *,
    session_timezone: str | None = None,
) -> pd.Series:
    """Select and validate the signal decision timestamp.

    Decision timestamp rule:
    - use ``trigger_timestamp`` when present and non-null
    - otherwise fall back to ``timestamp``
    """
    if "timestamp" not in signals.columns:
        raise ValueError("signals must contain a 'timestamp' column")

    if "trigger_timestamp" in signals.columns:
        candidate_ts = signals["trigger_timestamp"].where(
            signals["trigger_timestamp"].notna(),
            signals["timestamp"],
        )
    else:
        candidate_ts = signals["timestamp"]

    if candidate_ts.isna().any():
        missing_indexes = list(candidate_ts[candidate_ts.isna()].index)
        raise ValueError(
            "Signal decision timestamp is missing for row index(es): "
            f"{missing_indexes}"
        )

    try:
        parsed = pd.to_datetime(candidate_ts, errors="raise")
    except Exception as exc:  # pragma: no cover - pandas error surface
        raise ValueError(f"Signal decision timestamp is invalid: {exc}") from exc

    if not hasattr(parsed.dtype, "tz") or parsed.dtype.tz is None:
        if session_timezone is None:
            raise ValueError(
                "Signal decision timestamps are timezone-naive and session_timezone "
                "was not supplied."
            )
        parsed = parsed.dt.tz_localize(session_timezone)
    elif session_timezone is not None:
        parsed = parsed.dt.tz_convert(session_timezone)

    return parsed


def _validate_config(
    *,
    enabled: bool,
    timeframes: Sequence[str],
    alignment_mode: str,
    minimum_consecutive_bars: int,
    session_reset: str,
) -> None:
    if not isinstance(enabled, bool):
        raise ValueError(f"enabled must be a bool, got {enabled!r}")

    if alignment_mode != "all":
        raise ValueError("alignment_mode must be 'all' in OTF v1")

    if isinstance(minimum_consecutive_bars, bool) or not isinstance(minimum_consecutive_bars, int):
        raise ValueError(
            "minimum_consecutive_bars must be an integer >= 1"
        )
    if minimum_consecutive_bars < 1:
        raise ValueError("minimum_consecutive_bars must be >= 1")

    if session_reset != "session":
        raise ValueError("session_reset must be 'session' in OTF v1")

    if enabled and len(timeframes) == 0:
        raise ValueError("enabled=True requires at least one selected timeframe")


def _normalize_timeframes(timeframes: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    supported = OTF_CANONICAL_TIMEFRAMES | frozenset(_TIMEFRAME_ALIASES)

    for timeframe in timeframes:
        if timeframe not in supported:
            raise ValueError(
                f"Unsupported OTF timeframe: {timeframe!r}. "
                f"Supported values: {sorted(OTF_CANONICAL_TIMEFRAMES)} "
                "plus aliases ['5min', '15min', '30min']."
            )
        canonical = _TIMEFRAME_ALIASES.get(timeframe, timeframe)
        if canonical in seen:
            raise ValueError(
                f"Duplicate OTF timeframe after normalization: {canonical!r}"
            )
        seen.add(canonical)
        normalized.append(canonical)

    return normalized


def _validate_signal_directions(signals: pd.DataFrame) -> None:
    if "direction" not in signals.columns:
        raise ValueError("signals must contain a 'direction' column")

    invalid = signals[~signals["direction"].isin(_VALID_DIRECTIONS)]
    if not invalid.empty:
        bad_values = sorted({str(v) for v in invalid["direction"].tolist()})
        raise ValueError(
            f"signals.direction must contain only 'long'/'short'; got {bad_values}"
        )


def _align_otf_state(
    source_df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    timeframe: str,
    minimum_consecutive_bars: int,
    session_timezone: str | None,
    eth_start: str | None,
    session_reset: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    otf_df = calculate_otf_state(
        source_df,
        timeframe,
        minimum_consecutive_bars=minimum_consecutive_bars,
        session_timezone=session_timezone,
        eth_start=eth_start,
        session_reset=session_reset,
    )

    if signals.empty:
        empty_state = pd.Series(dtype="object")
        empty_seq = pd.Series(dtype="int64")
        empty_ref = pd.Series(dtype="datetime64[ns]")
        return empty_state, empty_seq, empty_ref

    if otf_df.empty:
        unknown_states = pd.Series(["unknown"] * len(signals), index=signals.index)
        zero_lengths = pd.Series([0] * len(signals), index=signals.index)
        nat_refs = pd.Series([pd.NaT] * len(signals), index=signals.index)
        return unknown_states, zero_lengths, nat_refs

    left = signals[["_otf_row_order", "otf_signal_decision_timestamp"]].copy()
    left["_otf_decision_timestamp_utc"] = left["otf_signal_decision_timestamp"].dt.tz_convert("UTC")

    right = otf_df[["availability_timestamp", "otf_state", "otf_sequence_length"]].copy()
    right["_otf_availability_timestamp_utc"] = right["availability_timestamp"].dt.tz_convert("UTC")

    aligned = pd.merge_asof(
        left.sort_values("_otf_decision_timestamp_utc", kind="stable"),
        right[[
            "_otf_availability_timestamp_utc",
            "availability_timestamp",
            "otf_state",
            "otf_sequence_length",
        ]].sort_values("_otf_availability_timestamp_utc", kind="stable"),
        left_on="_otf_decision_timestamp_utc",
        right_on="_otf_availability_timestamp_utc",
        direction="backward",
        allow_exact_matches=True,
    ).sort_values("_otf_row_order", kind="stable")

    state = aligned["otf_state"].fillna("unknown")
    sequence = aligned["otf_sequence_length"].fillna(0).astype(int)
    reference = aligned["availability_timestamp"]

    state.index = signals.index
    sequence.index = signals.index
    reference.index = signals.index
    return state, sequence, reference


def _evaluate_signal_eligibility(
    signal_row: pd.Series,
    timeframes: Sequence[str],
) -> tuple[bool, str | None]:
    direction = signal_row["direction"]
    required_state = "up" if direction == "long" else "down"

    for timeframe in timeframes:
        state = str(signal_row[f"otf_{timeframe}_state"])
        if state == required_state:
            continue

        if state == "unknown":
            return (
                False,
                f"{timeframe} OTF state is unknown; insufficient completed OTF history for {direction}",
            )

        return (
            False,
            f"{timeframe} OTF state is {state}; all selected timeframes must be {required_state} for {direction}",
        )

    return True, None
