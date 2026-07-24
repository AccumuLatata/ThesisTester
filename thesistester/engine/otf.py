"""Pure OTF (One Timeframing) calculation engine — ThesisTester PR 2.

This module implements the v1 OTF state machine exactly as specified in
``docs/otf-filter.md``.  It is a deterministic, regression-safe, look-ahead-safe
calculation engine with no integration into signals, UI, persistence, backtests,
grid-search, walk-forward analysis, or reporting.

Public API
----------

.. code-block:: python

    from thesistester.engine.otf import calculate_otf_state

    result = calculate_otf_state(
        df,
        timeframe="15m",
        minimum_consecutive_bars=3,
        session_timezone="America/New_York",
        eth_start="18:00",
        session_reset="session",
    )

Parameters
----------
df : pd.DataFrame
    Source OHLCV bars with columns ``timestamp``, ``open``, ``high``, ``low``,
    ``close``, ``volume``.  The ``timestamp`` column must either be timezone-aware
    or timezone-naive with ``session_timezone`` supplied so the engine can
    localise it.  The rows must be in strictly ascending timestamp order with no
    duplicates.  The caller's DataFrame is never mutated.
timeframe : str
    Target OTF higher timeframe.  Canonical public values are ``"5m"``,
    ``"15m"``, and ``"30m"``.  Backward-compatible aliases ``"5min"``,
    ``"15min"``, and ``"30min"`` are also accepted and normalized internally
    before calling ``resample_ohlcv()``.  The source bar interval must be
    strictly finer than this timeframe and must exactly divide it.
minimum_consecutive_bars : int
    Number of consecutive qualifying bar comparisons required to establish a
    directional state.  Must be >= 1.  Default 3.
session_timezone : str or None
    IANA timezone string used to localise the resampled HTF bar timestamps for
    session-boundary detection.  If ``None`` and the input timestamps are
    timezone-aware, their existing timezone is used unchanged.
eth_start : str or None
    Exchange-session start time in ``"HH:MM"`` format (e.g. ``"18:00"`` for ES/NQ
    futures).  When set, a bar whose exchange-local time is at or after this value
    belongs to the **next** calendar day's trading session.  When ``None``, session
    boundaries fall at calendar-day midnight.
session_reset : str
    Must be ``"session"`` for v1.  OTF state resets at each trading-session
    boundary; cross-session carry is not supported.

Returns
-------
pd.DataFrame
    One row per completed HTF bar with the following columns:

    ``bar_start_timestamp``
        Pandas left-label of the resampled bucket (timezone-aware).
    ``bar_close_timestamp``
        ``bar_start_timestamp + timeframe_duration`` — when the bar closed and
        its OHLCV values became final.
    ``availability_timestamp``
        Equal to ``bar_close_timestamp``.  A signal at time T may use this bar
        only when ``availability_timestamp <= T``.
    ``open``, ``high``, ``low``, ``close``, ``volume``
        Aggregated OHLCV of the completed HTF bar.
    ``trading_session_date``
        Calendar date (``datetime.date``) of the trading session this bar belongs
        to, as produced by ``trading_session_date()``.
    ``otf_state``
        One of ``"up"``, ``"down"``, ``"neutral"``, ``"unknown"``.
    ``otf_sequence_length``
        Current directional run length.  When ``otf_state`` is ``"up"`` this is
        ``up_run``; when ``"down"`` this is ``down_run``; for ``"neutral"`` and
        ``"unknown"`` this is 0.  The value is deterministic and documents the
        run that drives the active directional state.
    ``up_run``
        Raw consecutive higher-low counter for this bar.
    ``down_run``
        Raw consecutive lower-high counter for this bar.
    ``otf_reference_timestamp``
        ``bar_close_timestamp`` of the most recent *previous* completed HTF bar
        within the current trading session that was used as the comparison anchor
        (i.e. ``prev_bar``).  ``pd.NaT`` for the first bar of a session.

Partial first session-bucket policy
------------------------------------
When a trading session's first available source bar falls in the **middle** of an
HTF bucket (i.e. the bucket's ``bar_start_timestamp`` precedes the earliest source
bar in that session), the resulting aggregated bar is incomplete.  Including it in
OTF comparisons would bias the high/low values.

Decision (conservative, research-safe): **discard** any HTF bar whose
``bar_start_timestamp`` is strictly earlier than the first source bar's timestamp
within that trading session.

This is the most conservative policy because it avoids using OHLCV values that
do not represent a full bucket period.  A full bucket starting on a session
boundary or after the first source bar is always retained.

Completed-source coverage policy
--------------------------------
ThesisTester source rows are start-labelled bars.  For an inferred source
interval ``Δ``, each row covers the half-open window
``[source_bar_start_timestamp, source_bar_start_timestamp + Δ)`` and becomes
available at ``source_bar_close_timestamp = source_bar_start_timestamp + Δ``.

An HTF bucket is retained only when:

1. ``bar_close_timestamp <= latest_source_availability_timestamp``.
2. The first expected source bar is present.
3. The final expected source bar is present.
4. The source timestamps within the bucket are continuous at the inferred
   interval.
5. The bucket contains exactly ``target_duration / source_interval`` source bars.

No next-bucket sentinel row is required.  For example, 1-minute source rows
labelled 09:00, 09:01, 09:02, 09:03, 09:04 fully complete the 5-minute HTF
bucket labelled 09:00 and closing at 09:05.

Look-ahead and drift safety
----------------------------
The engine guarantees that:

1. Only bars with ``bar_close_timestamp <= evaluation_timestamp`` are usable;
   in-progress bars are never included in the OTF computation for earlier bars.
2. Appending source bars after timestamp ``T`` cannot change any OTF output
   whose ``availability_timestamp <= T``.
3. Future highs, lows, and closes do not alter historical states.
4. Session resets do not leak counters from prior sessions.

These properties follow from the fact that ``resample_ohlcv()`` is called once on
the full source slice, and the state machine iterates forward through completed bars
in strict timestamp order.

Contract reference
------------------
``docs/otf-filter.md`` — OTF v1 Behavioral Contract, §3, §6.
Contract version: v1
"""
from __future__ import annotations

import datetime
from typing import Final

import pandas as pd

from thesistester.data.loader import infer_base_interval
from thesistester.data.resample import resample_ohlcv
from thesistester.levels.session_date import trading_session_date

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical public OTF higher-timeframe labels for this engine (v1).
OTF_CANONICAL_TIMEFRAMES: Final[frozenset[str]] = frozenset({"5m", "15m", "30m"})

#: Backward-compatible aliases accepted for existing callers.
_TIMEFRAME_ALIASES: Final[dict[str, str]] = {
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
}

#: All accepted public OTF timeframe inputs, including aliases.
OTF_SUPPORTED_TIMEFRAMES: Final[frozenset[str]] = (
    OTF_CANONICAL_TIMEFRAMES | frozenset(_TIMEFRAME_ALIASES)
)

#: Internal resampler labels for the canonical public timeframes.
_TIMEFRAME_NORMALIZATION: Final[dict[str, str]] = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
}

#: Required source OHLCV columns.
_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"timestamp", "open", "high", "low", "close", "volume"}
)

#: Valid OTF states (v1 contract §2).
_VALID_STATES: Final[frozenset[str]] = frozenset({"up", "down", "neutral", "unknown"})

#: Timeframe durations for supported resampler labels.
_TIMEFRAME_DURATION: Final[dict[str, pd.Timedelta]] = {
    "5min":  pd.Timedelta("5min"),
    "15min": pd.Timedelta("15min"),
    "30min": pd.Timedelta("30min"),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_otf_state(
    df: pd.DataFrame,
    timeframe: str,
    *,
    minimum_consecutive_bars: int = 3,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    session_reset: str = "session",
) -> pd.DataFrame:
    """Calculate the v1 OTF state for every completed higher-timeframe bar.

    See module docstring for full parameter and return-value documentation.
    """
    # ------------------------------------------------------------------
    # 1. Validate inputs
    # ------------------------------------------------------------------
    _validate_inputs(df, timeframe, minimum_consecutive_bars, session_reset)
    normalized_timeframe = _normalize_timeframe(timeframe)

    if df.empty:
        return _empty_result()

    # ------------------------------------------------------------------
    # 2. Defensive copy — never mutate the caller's DataFrame
    # ------------------------------------------------------------------
    source = df.copy()

    # ------------------------------------------------------------------
    # 3. Ensure timestamps are timezone-aware; apply session_timezone if given
    # ------------------------------------------------------------------
    source = _ensure_timezone_aware(source, session_timezone)

    # ------------------------------------------------------------------
    # 4. Validate timestamp monotonicity and uniqueness
    # ------------------------------------------------------------------
    _validate_timestamps(source)

    # ------------------------------------------------------------------
    # 5. Validate and normalize source OHLCV values
    # ------------------------------------------------------------------
    source = _coerce_and_validate_source_ohlcv(source)

    # ------------------------------------------------------------------
    # 6. Infer and validate the source interval used for completion checks
    # ------------------------------------------------------------------
    source_interval = _infer_validated_source_interval(source, normalized_timeframe)

    # ------------------------------------------------------------------
    # 7. Resample source bars to the target higher timeframe
    # ------------------------------------------------------------------
    duration = _TIMEFRAME_DURATION[normalized_timeframe]
    htf = resample_ohlcv(source, normalized_timeframe).copy()
    htf = htf.rename(columns={"timestamp": "bar_start_timestamp"})
    htf["bar_close_timestamp"] = htf["bar_start_timestamp"] + duration
    htf["availability_timestamp"] = htf["bar_close_timestamp"]

    # ------------------------------------------------------------------
    # 8. Assign trading-session dates (used for session-boundary detection)
    # ------------------------------------------------------------------
    htf["trading_session_date"] = trading_session_date(
        htf["bar_start_timestamp"], eth_start
    )

    # ------------------------------------------------------------------
    # 9. Keep only HTF bars backed by complete source-bar coverage.
    #
    # Source timestamps are source-bar *start* labels.  A source bar becomes
    # available at source_bar_close_timestamp = source_bar_start_timestamp +
    # source_interval.  An HTF bar is complete only when:
    #   * bar_close_timestamp <= latest_source_availability_timestamp
    #   * every expected source bar in that bucket is present and continuous
    # ------------------------------------------------------------------
    htf = _filter_complete_htf_buckets(
        htf,
        source,
        normalized_timeframe,
        source_interval,
    )

    # ------------------------------------------------------------------
    # 10. Apply the conservative partial first session-bucket policy.
    #
    # This runs after the general completeness filter so both rules share the
    # same definition of source-bar coverage.  The session-specific guard is
    # kept explicitly because the contract treats first-session partial buckets
    # as a notable policy decision.
    # ------------------------------------------------------------------
    htf = _discard_partial_first_buckets(htf, source, eth_start)

    if htf.empty:
        return _empty_result()

    htf = htf.reset_index(drop=True)

    # ------------------------------------------------------------------
    # 11. Run the OTF state machine over the completed HTF bars
    # ------------------------------------------------------------------
    htf = _run_state_machine(htf, minimum_consecutive_bars)

    # ------------------------------------------------------------------
    # 12. Return the final result with canonical column ordering
    # ------------------------------------------------------------------
    return _reorder_columns(htf)


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _validate_inputs(
    df: pd.DataFrame,
    timeframe: str,
    minimum_consecutive_bars: int,
    session_reset: str,
) -> None:
    """Raise ValueError for any invalid input parameter."""
    # Required columns
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Input DataFrame is missing required columns: {sorted(missing)}"
        )

    # Timeframe support
    if timeframe not in OTF_SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported OTF timeframe: {timeframe!r}. "
            f"Canonical values: {sorted(OTF_CANONICAL_TIMEFRAMES)}. "
            "Backward-compatible aliases: ['5min', '15min', '30min']."
        )

    # minimum_consecutive_bars
    if not isinstance(minimum_consecutive_bars, int) or minimum_consecutive_bars < 1:
        raise ValueError(
            f"minimum_consecutive_bars must be an integer >= 1, "
            f"got {minimum_consecutive_bars!r}"
        )

    # session_reset — only "session" is supported in v1
    if session_reset != "session":
        raise ValueError(
            f"session_reset={session_reset!r} is not supported in OTF v1. "
            "Only 'session' is accepted."
        )


def _ensure_timezone_aware(
    df: pd.DataFrame, session_timezone: str | None
) -> pd.DataFrame:
    """Return a copy of df with timezone-aware timestamps.

    If session_timezone is supplied, localise naive timestamps to that zone
    or convert already-aware timestamps to that zone.
    If session_timezone is None and timestamps are naive, raise ValueError.
    """
    ts = df["timestamp"]
    if not hasattr(ts.dtype, "tz") or ts.dtype.tz is None:
        # Naive timestamps
        if session_timezone is None:
            raise ValueError(
                "Input timestamps are timezone-naive and session_timezone was not "
                "supplied. Either pass timezone-aware timestamps or provide "
                "session_timezone to localise them."
            )
        df = df.copy()
        df["timestamp"] = ts.dt.tz_localize(session_timezone)
    elif session_timezone is not None:
        # Already-aware timestamps: convert to requested timezone
        df = df.copy()
        df["timestamp"] = ts.dt.tz_convert(session_timezone)
    return df


def _normalize_timeframe(timeframe: str) -> str:
    """Normalize a canonical or alias timeframe to the resampler label."""
    canonical_timeframe = _TIMEFRAME_ALIASES.get(timeframe, timeframe)
    return _TIMEFRAME_NORMALIZATION[canonical_timeframe]


def _coerce_and_validate_source_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce source OHLCV values to numeric and validate price/volume rules."""
    df = df.copy()
    ohlcv = ["open", "high", "low", "close", "volume"]
    for column in ohlcv:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("Input contains missing or non-numeric OHLC values.")
    if df["volume"].isna().any():
        raise ValueError("Input contains missing or non-numeric volume values.")
    if (df["high"] < df["low"]).any():
        raise ValueError("Input contains bars with high < low.")

    open_close_max = df[["open", "close"]].max(axis=1)
    open_close_min = df[["open", "close"]].min(axis=1)
    within_range = (df["high"] >= open_close_max) & (df["low"] <= open_close_min)
    if not within_range.all():
        raise ValueError("Input contains bars where open/close fall outside high/low.")
    if (df["volume"] < 0).any():
        raise ValueError("Input contains bars with negative volume.")

    return df


def _validate_timestamps(df: pd.DataFrame) -> None:
    """Raise ValueError if timestamps are invalid, non-monotonic, or duplicated."""
    ts = df["timestamp"]

    # Check for NaT
    if ts.isna().any():
        raise ValueError("Input contains NaT (invalid) timestamps.")

    # Check monotonic strictly increasing (no duplicates, no reversals)
    diffs = ts.diff().iloc[1:]
    if (diffs <= pd.Timedelta(0)).any():
        raise ValueError(
            "Input timestamps must be strictly monotonically increasing with no "
            "duplicate timestamps."
        )


def _infer_validated_source_interval(
    df: pd.DataFrame,
    timeframe: str,
) -> pd.Timedelta:
    """Infer and validate the source interval used for completion checks."""
    base_interval = infer_base_interval(df["timestamp"])
    if base_interval is None:
        raise ValueError(
            "Could not infer a trustworthy source bar interval from the input timestamps. "
            "At least two source bars are required."
        )

    diffs = df["timestamp"].diff().dropna()
    diff_ns = diffs.to_numpy(dtype="timedelta64[ns]").astype("int64")
    if (diff_ns % base_interval.value != 0).any():
        raise ValueError(
            "Input timestamps do not align to a trustworthy inferred source interval; "
            "irregular timestamp gaps prevent safe HTF completion checks."
        )

    target_duration = _TIMEFRAME_DURATION[timeframe]
    if base_interval >= target_duration:
        raise ValueError(
            f"Source bar interval ({base_interval}) must be strictly finer than "
            f"the target OTF timeframe ({timeframe} = {target_duration}). "
            "The OTF engine cannot resample from an equal or coarser source."
        )
    if target_duration.value % base_interval.value != 0:
        raise ValueError(
            f"Target OTF timeframe ({timeframe} = {target_duration}) "
            f"must be exactly divisible by the inferred source bar interval ({base_interval})."
        )
    return base_interval


def _filter_complete_htf_buckets(
    htf: pd.DataFrame,
    source: pd.DataFrame,
    timeframe: str,
    source_interval: pd.Timedelta,
) -> pd.DataFrame:
    """Keep only HTF buckets backed by complete source-bar coverage."""
    if htf.empty or source.empty:
        return htf

    target_duration = _TIMEFRAME_DURATION[timeframe]
    expected_count = target_duration.value // source_interval.value
    indexed = source.set_index("timestamp")
    grouped_rows: list[dict[str, object]] = []
    # Use the actual resampler bucket labels for source-row assignment so DST
    # repeated wall-clock times remain distinct by absolute instant / UTC offset.
    for bar_start_timestamp, positions in indexed.resample(timeframe).indices.items():
        if len(positions) == 0:
            continue

        bucket_source_starts = indexed.index.take(positions)
        bucket_source_closes = bucket_source_starts + source_interval
        continuation_count = int(
            (bucket_source_starts[1:] - bucket_source_starts[:-1] == source_interval).sum()
        )
        expected_bar_close_timestamp = bar_start_timestamp + target_duration

        grouped_rows.append(
            {
                "bar_start_timestamp": bar_start_timestamp,
                "source_bar_count": len(bucket_source_starts),
                "first_source_bar_start_timestamp": bucket_source_starts.min(),
                "last_source_bar_start_timestamp": bucket_source_starts.max(),
                "last_source_bar_close_timestamp": bucket_source_closes.max(),
                "continuation_count": continuation_count,
                "expected_bar_close_timestamp": expected_bar_close_timestamp,
                "is_complete_bucket": (
                    len(bucket_source_starts) == expected_count
                    and bucket_source_starts.min() == bar_start_timestamp
                    and bucket_source_closes.max() == expected_bar_close_timestamp
                    and continuation_count == expected_count - 1
                ),
            }
        )

    grouped = pd.DataFrame(grouped_rows)
    latest_source_availability_timestamp = source["timestamp"].max() + source_interval

    filtered = htf.merge(
        grouped[
            [
                "bar_start_timestamp",
                "is_complete_bucket",
            ]
        ],
        on="bar_start_timestamp",
        how="left",
    )
    filtered = filtered[
        (
            filtered["bar_close_timestamp"].le(latest_source_availability_timestamp)
            & filtered["is_complete_bucket"].fillna(False)
        )
    ].copy()
    return filtered.drop(columns=["is_complete_bucket"])


# ---------------------------------------------------------------------------
# Partial first session-bucket discard
# ---------------------------------------------------------------------------


def _discard_partial_first_buckets(
    htf: pd.DataFrame,
    source: pd.DataFrame,
    eth_start: str | None,
) -> pd.DataFrame:
    """Discard HTF bars whose bucket started before the first source bar in their session.

    Policy (conservative, research-safe): a resampled HTF bar is *partial* when
    its ``bar_start_timestamp`` is strictly earlier than the earliest source bar
    whose trading-session date equals this HTF bar's trading-session date.  Such
    bars are incomplete and must not be used for OTF comparisons.

    A bar that starts at or after the first source bar in its session is *complete*
    and is retained.
    """
    if htf.empty or source.empty:
        return htf

    # Compute trading_session_date for each source bar
    source_sessions = trading_session_date(source["timestamp"], eth_start)
    # First source bar timestamp per session (keep as Series with tz-aware timestamps)
    tmp = (
        pd.DataFrame({"trading_session_date": source_sessions, "first_source_ts": source["timestamp"]})
        .groupby("trading_session_date", sort=False, as_index=False)["first_source_ts"]
        .min()
    )
    filtered = htf.merge(tmp, on="trading_session_date", how="left")
    mask = filtered["first_source_ts"].isna() | (
        filtered["bar_start_timestamp"].astype("int64")
        >= filtered["first_source_ts"].astype("int64")
    )
    return filtered.loc[mask, htf.columns].copy()


# ---------------------------------------------------------------------------
# OTF state machine
# ---------------------------------------------------------------------------


def _run_state_machine(htf: pd.DataFrame, minimum_consecutive_bars: int) -> pd.DataFrame:
    """Apply the v1 OTF state machine to the ordered HTF bar DataFrame in-place.

    Adds columns: ``otf_state``, ``otf_sequence_length``, ``up_run``,
    ``down_run``, ``otf_reference_timestamp``.

    The machine resets at every trading-session boundary (§3.10).
    """
    n = len(htf)
    states: list[str] = ["unknown"] * n
    up_runs: list[int] = [0] * n
    down_runs: list[int] = [0] * n
    seq_lengths: list[int] = [0] * n
    ref_timestamps: list[pd.Timestamp | pd.NaT] = [pd.NaT] * n

    up_run = 0
    down_run = 0
    prev_high: float | None = None
    prev_low: float | None = None
    prev_close_ts: pd.Timestamp | None = None
    current_session: object = None

    bars_high = htf["high"].to_numpy()
    bars_low = htf["low"].to_numpy()
    bars_session = htf["trading_session_date"].to_numpy()
    bars_close_ts = htf["bar_close_timestamp"].to_numpy()

    for i in range(n):
        sess = bars_session[i]

        # Detect session boundary — reset state on new session
        if sess != current_session:
            up_run = 0
            down_run = 0
            prev_high = None
            prev_low = None
            prev_close_ts = None
            current_session = sess

        if prev_high is None or prev_low is None:
            # First completed bar in this session — no comparison possible
            state = "unknown"
            up_runs[i] = 0
            down_runs[i] = 0
        else:
            # Update up_run (§3.2)
            if bars_low[i] > prev_low:
                up_run += 1
            else:
                up_run = 0  # equal or lower low resets

            # Update down_run (§3.3)
            if bars_high[i] < prev_high:
                down_run += 1
            else:
                down_run = 0  # equal or higher high resets

            # Determine state (§3.4)
            up_threshold = up_run >= minimum_consecutive_bars
            down_threshold = down_run >= minimum_consecutive_bars

            if up_threshold and not down_threshold:
                state = "up"
            elif down_threshold and not up_threshold:
                state = "down"
            else:
                state = "neutral"

            up_runs[i] = up_run
            down_runs[i] = down_run

        states[i] = state

        # otf_sequence_length: directional run for active state, else 0
        if state == "up":
            seq_lengths[i] = up_run
        elif state == "down":
            seq_lengths[i] = down_run
        else:
            seq_lengths[i] = 0

        # otf_reference_timestamp: bar_close_timestamp of the previous bar in this session
        ref_timestamps[i] = prev_close_ts if prev_close_ts is not None else pd.NaT

        # Advance "previous bar" for next iteration
        prev_high = float(bars_high[i])
        prev_low = float(bars_low[i])
        prev_close_ts = pd.Timestamp(bars_close_ts[i])

    htf = htf.copy()
    htf["otf_state"] = states
    htf["otf_sequence_length"] = seq_lengths
    htf["up_run"] = up_runs
    htf["down_run"] = down_runs
    htf["otf_reference_timestamp"] = ref_timestamps

    return htf


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


_OUTPUT_COLUMNS: Final[list[str]] = [
    "bar_start_timestamp",
    "bar_close_timestamp",
    "availability_timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_session_date",
    "otf_state",
    "otf_sequence_length",
    "up_run",
    "down_run",
    "otf_reference_timestamp",
]


def _reorder_columns(htf: pd.DataFrame) -> pd.DataFrame:
    """Return the DataFrame with canonical column ordering."""
    present = [c for c in _OUTPUT_COLUMNS if c in htf.columns]
    extra = [c for c in htf.columns if c not in _OUTPUT_COLUMNS]
    return htf[present + extra].reset_index(drop=True)


def _empty_result() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical output schema."""
    return pd.DataFrame(columns=_OUTPUT_COLUMNS)
