"""Pure OTF signal eligibility filter (PR 3).

This module evaluates already-generated candidate signals against the shared
OTF engine and returns accepted and rejected signals separately.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .otf import normalize_otf_timeframe, calculate_otf_state

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

    When ``enabled=False`` the function returns immediately after validating
    only the ``enabled`` parameter itself.  All timeframe, signal, timestamp,
    and source-data validation is skipped.

    When ``enabled=True`` and ``signals`` is empty the function validates
    configuration and timeframe inputs, then returns stable empty
    accepted/rejected DataFrames without inspecting source OHLCV data or
    calling the OTF engine.
    """
    # ------------------------------------------------------------------
    # 1. Validate `enabled` type only — this is the sole check for the
    #    disabled path.
    # ------------------------------------------------------------------
    if not isinstance(enabled, bool):
        raise ValueError(f"enabled must be a bool, got {enabled!r}")

    # ------------------------------------------------------------------
    # 2. Disabled short-circuit: true no-op for legacy compatibility.
    #    No timeframe/signal/timestamp/source inspection.
    # ------------------------------------------------------------------
    if not enabled:
        signal_copy = signals.copy(deep=True)
        accepted = signal_copy.copy()
        accepted["otf_filter_enabled"] = False
        accepted["otf_filter_passed"] = True
        accepted["otf_filter_reason"] = None
        rejected = accepted.iloc[0:0].copy()
        return accepted, rejected

    # ------------------------------------------------------------------
    # 3. Validate remaining configuration (enabled=True only).
    # ------------------------------------------------------------------
    _validate_enabled_config(
        alignment_mode=alignment_mode,
        minimum_consecutive_bars=minimum_consecutive_bars,
        session_reset=session_reset,
        timeframes=timeframes,
    )
    normalized_timeframes = _normalize_timeframes(timeframes)

    signal_copy = signals.copy(deep=True)

    # ------------------------------------------------------------------
    # 4. Empty-signals short-circuit: return stable empty schemas without
    #    touching source OHLCV data or the OTF engine.
    # ------------------------------------------------------------------
    if signal_copy.empty:
        return _build_empty_enabled_outputs(signal_copy, normalized_timeframes)

    # ------------------------------------------------------------------
    # 5. Validate signal content and evaluate eligibility.
    # ------------------------------------------------------------------
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


def _validate_enabled_config(
    *,
    alignment_mode: str,
    minimum_consecutive_bars: int,
    session_reset: str,
    timeframes: Sequence[str],
) -> None:
    """Validate configuration parameters that apply only when enabled=True."""
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

    if len(timeframes) == 0:
        raise ValueError("enabled=True requires at least one selected timeframe")


def _normalize_timeframes(timeframes: Sequence[str]) -> list[str]:
    """Normalize timeframe inputs to canonical labels, detecting duplicates."""
    normalized: list[str] = []
    seen: set[str] = set()

    for timeframe in timeframes:
        canonical = normalize_otf_timeframe(timeframe)  # raises ValueError for unsupported
        if canonical in seen:
            raise ValueError(
                f"Duplicate OTF timeframe after normalization: {canonical!r}"
            )
        seen.add(canonical)
        normalized.append(canonical)

    return normalized


def _build_empty_enabled_outputs(
    signal_copy: pd.DataFrame,
    normalized_timeframes: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return stable empty accepted/rejected DataFrames with correct schema.

    Both outputs have identical column sets: all original signal columns plus
    OTF metadata columns for the selected timeframes only.
    """
    result = signal_copy.copy()
    result["otf_signal_decision_timestamp"] = pd.Series(
        dtype="datetime64[ns]", index=result.index
    )
    for tf in normalized_timeframes:
        result[f"otf_{tf}_state"] = pd.Series(dtype="object", index=result.index)
        result[f"otf_{tf}_sequence_length"] = pd.Series(dtype="int64", index=result.index)
        result[f"otf_{tf}_reference_timestamp"] = pd.Series(
            dtype="datetime64[ns]", index=result.index
        )
    result["otf_filter_enabled"] = pd.Series(dtype="bool", index=result.index)
    result["otf_filter_passed"] = pd.Series(dtype="bool", index=result.index)
    result["otf_filter_reason"] = pd.Series(dtype="object", index=result.index)
    accepted = result.copy()
    rejected = result.copy()
    return accepted, rejected


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
