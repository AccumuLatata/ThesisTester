"""Walk-forward / out-of-sample diagnostics for SL/TP selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..data.loader import infer_base_interval
from ..levels.session_date import trading_session_date
from .grid import best_grid_result, run_sl_tp_grid
from .metrics import equity_curve, summarize_trades
from ..engine.backtest import simulate_trades
from ..setup import normalize_otf_filter_config


# Patterns that identify "insufficient fold-local OTF history" errors raised
# by the pure OTF engine when a fold slice is too short to infer a source
# interval or accumulate completed HTF bars.  Only these patterns are caught
# and converted to "all-rejected as unknown"; all other ValueError instances
# are re-raised so that programming errors and unexpected failures are not
# silently swallowed.
_EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS: tuple[str, ...] = (
    "Could not infer a trustworthy source bar interval",
    "At least two source bars are required",
    "Input timestamps do not align to a trustworthy inferred source interval",
    "must be strictly finer than",
    "must be exactly divisible by the inferred source bar interval",
)

#: Allowed WFO OTF history policies (hardening PR 4).
OTF_HISTORY_POLICIES: frozenset[str] = frozenset({"fold_local", "causal_prefix"})
DEFAULT_OTF_HISTORY_POLICY: str = "fold_local"


def normalize_otf_history_policy(value: Any = None) -> str:
    """Return a canonical OTF history policy.

    Missing / ``None`` resolves to ``fold_local``. Unsupported values raise
    ``ValueError`` and are never silently coerced.
    """
    if value is None:
        return DEFAULT_OTF_HISTORY_POLICY
    if not isinstance(value, str):
        raise ValueError(
            f"otf_history_policy must be 'fold_local' or 'causal_prefix', got {value!r}."
        )
    policy = value.strip()
    if policy not in OTF_HISTORY_POLICIES:
        raise ValueError(
            f"otf_history_policy must be 'fold_local' or 'causal_prefix', got {value!r}."
        )
    return policy


def resolve_otf_session_timezone(
    session_timezone: str | None,
    exchange_timezone: str | None = None,
) -> str | None:
    """Return the timezone fold-level OTF filtering actually uses.

    Session-exit policy may omit ``session_timezone``. Fold OTF then falls back
    to ``exchange_timezone`` so filter execution and recorded OTF metadata stay
    aligned (Streamlit Validation WFO summaries, research exports).
    """
    if isinstance(session_timezone, str) and session_timezone.strip():
        return session_timezone
    if isinstance(exchange_timezone, str) and exchange_timezone.strip():
        return exchange_timezone
    return None


def _otf_source_for_fold(
    df: pd.DataFrame,
    *,
    fold_start: int,
    fold_end_exclusive: int,
    otf_history_policy: str,
) -> pd.DataFrame:
    """Select the OHLCV source used for OTF state in one fold.

    ``fold_local`` uses only the fold slice. ``causal_prefix`` uses
    ``prefix ∪ fold-local`` bars (``df.iloc[:fold_end_exclusive]``), where
    prefix bars are strictly before ``fold_start``. Future bars after the fold
    end are never included.
    """
    if otf_history_policy == "fold_local":
        return df.iloc[fold_start:fold_end_exclusive].reset_index(drop=True)
    if otf_history_policy == "causal_prefix":
        return df.iloc[:fold_end_exclusive].reset_index(drop=True)
    raise ValueError(
        f"otf_history_policy must be 'fold_local' or 'causal_prefix', got {otf_history_policy!r}."
    )


def _filter_fold_signals_with_otf(
    source_df: pd.DataFrame,
    fold_signals: pd.DataFrame,
    otf_config: dict[str, Any],
    session_timezone: str | None,
    eth_start: str | None = None,
) -> tuple[pd.DataFrame, int, int]:
    """Apply OTF filter to a fold's signals using the provided OHLCV source.

    ``source_df`` may be fold-local only or prefix∪fold-local under
    ``causal_prefix``. Only fold-local *signals* are scored; prefix bars are
    market-state input for OTF establishment.

    If the source slice has insufficient history for OTF evaluation (e.g.,
    too few bars to complete an OTF state), all candidate signals are
    treated as OTF ``unknown`` and therefore rejected.  This prevents
    crashes on short folds without leaking future OTF state.

    Only expected ``ValueError`` cases from OTF completion/interval
    insufficiency are caught.  Invalid config ``ValueError`` propagates.

    Parameters
    ----------
    source_df:
        OHLCV used for OTF state (fold-local or causal-prefix slice).
    fold_signals:
        Fold-local candidate signals (already sliced and reset-indexed).
    otf_config:
        Canonical enabled OTF filter config.  Must have ``enabled=True``.
    session_timezone:
        Exchange timezone label for session alignment.

    Returns
    -------
    tuple of (accepted_signals, rejected_count, candidate_count)
        ``accepted_signals`` — signals that passed the OTF filter.
        ``rejected_count``   — count of signals rejected (or all rejected
                               on insufficient history).
        ``candidate_count``  — count of original fold candidates.
    """
    from ..engine.otf_filter import apply_otf_filter as _apply_otf

    candidate_count = int(len(fold_signals))

    _otf_kwargs: dict[str, Any] = {
        "enabled": True,
        "timeframes": list(otf_config.get("timeframes", [])),
        "alignment_mode": str(otf_config.get("alignment_mode", "all")),
        "minimum_consecutive_bars": int(otf_config.get("minimum_consecutive_bars", 3)),
        "session_timezone": session_timezone,
        "eth_start": eth_start,
        "session_reset": str(otf_config.get("session_reset", "session")),
    }

    try:
        accepted, rejected = _apply_otf(source_df, fold_signals, **_otf_kwargs)
        return accepted, int(len(rejected)), candidate_count
    except ValueError as exc:
        msg = str(exc)
        if any(pattern in msg for pattern in _EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS):
            # Insufficient OTF history — reject all as unknown.
            # Return an empty accepted DataFrame preserving the schema.
            empty_accepted = fold_signals.iloc[0:0].copy()
            return empty_accepted, candidate_count, candidate_count
        # Unexpected ValueError (programming error, data integrity issue, etc.)
        # — re-raise so it is not silently swallowed.
        raise


_RESULT_COLUMNS = [
    "fold_id",
    "train_start_bar",
    "train_end_bar",
    "test_start_bar",
    "test_end_bar",
    "status",
    "selected_stop_loss_ticks",
    "selected_take_profit_ticks",
    "selected_metric_name",
    "selected_train_metric_value",
    "train_trade_count",
    "train_expectancy_r",
    "train_total_r",
    "train_profit_factor",
    "train_win_rate",
    "train_sharpe_like_r",
    "train_sortino_like_r",
    "train_ulcer_index_r",
    "test_trade_count",
    "test_expectancy_r",
    "test_total_r",
    "test_profit_factor",
    "test_win_rate",
    "test_max_drawdown_r",
    "test_sharpe_like_r",
    "test_sortino_like_r",
    "test_ulcer_index_r",
    "test_recovery_factor",
    "degradation_expectancy_r",
    "is_oos_profitable",
    "ranking_metric",
    "min_train_trades",
    "train_bars",
    "test_bars",
    "step_bars",
    "exposure_policy",
    "cooldown_bars_after_exit",
    "commission_per_side",
    "slippage_ticks",
    "flat_by_session_close",
    "session_close_time",
    "session_timezone",
    "no_new_entries_after",
    "intrabar_model",
    "breakeven_after_r",
    "trailing_after_r",
    "trailing_distance_ticks",
    # OTF metadata columns — present only when OTF is enabled
    "otf_filter_enabled",
    "otf_history_policy",
    "train_otf_candidate_count",
    "train_otf_accepted_count",
    "train_otf_rejected_count",
    "test_otf_candidate_count",
    "test_otf_accepted_count",
    "test_otf_rejected_count",
    "fold_mode",
    "window_mode",
    "train_start_session_date",
    "train_end_session_date",
    "test_start_session_date",
    "test_end_session_date",
    "train_session_count",
    "test_session_count",
    "retention_ratio_expectancy",
    "degradation_pct_expectancy",
    "ratio_status",
]


@dataclass(frozen=True)
class FoldBoundary:
    """Half-open train/test bar boundaries with optional session metadata."""

    fold_id: int
    train_start: int
    train_end_exclusive: int
    test_start: int
    test_end_exclusive: int
    train_start_session: str | None = None
    train_end_session: str | None = None
    test_start_session: str | None = None
    test_end_session: str | None = None
    train_session_count: int | None = None
    test_session_count: int | None = None


@dataclass(frozen=True)
class WalkForwardResult:
    """Detailed R14 walk-forward output."""

    schema_version: int
    config: dict[str, Any]
    folds: pd.DataFrame
    oos_trades: pd.DataFrame
    stitched_equity: pd.DataFrame
    summary: dict[str, Any]
    warnings: tuple[str, ...]


def _validate_timeline(df: pd.DataFrame) -> None:
    timestamps = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError("df['timestamp'] contains invalid timestamps.")
    if timestamps.duplicated().any():
        raise ValueError("df['timestamp'] contains duplicate timestamps.")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("df['timestamp'] must be monotonic increasing.")


def _bar_fold_boundaries(
    *,
    n_bars: int,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    window_mode: str,
) -> list[FoldBoundary]:
    folds: list[FoldBoundary] = []
    test_start = int(train_bars)
    fold_id = 0
    while test_start + int(test_bars) <= n_bars:
        train_start = 0 if window_mode == "anchored" else test_start - int(train_bars)
        folds.append(
            FoldBoundary(
                fold_id=fold_id,
                train_start=train_start,
                train_end_exclusive=test_start,
                test_start=test_start,
                test_end_exclusive=test_start + int(test_bars),
            )
        )
        test_start += int(step_bars)
        fold_id += 1
    return folds


def _session_fold_boundaries(
    df: pd.DataFrame,
    *,
    train_sessions: int,
    test_sessions: int,
    step_sessions: int,
    window_mode: str,
    exchange_timezone: str,
    eth_start: str,
) -> tuple[list[FoldBoundary], pd.Series]:
    timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(exchange_timezone)
    else:
        timestamps = timestamps.dt.tz_convert(exchange_timezone)
    session_ids = trading_session_date(timestamps, eth_start).astype(str)
    ordered_sessions = list(dict.fromkeys(session_ids.tolist()))
    session_ranges: dict[str, tuple[int, int]] = {}
    for session_id in ordered_sessions:
        indices = session_ids.index[session_ids.eq(session_id)]
        start = int(indices[0])
        end = int(indices[-1]) + 1
        if list(indices) != list(range(start, end)):
            raise ValueError(f"Session {session_id} is not contiguous in df.")
        session_ranges[session_id] = (start, end)

    folds: list[FoldBoundary] = []
    test_start_session = int(train_sessions)
    fold_id = 0
    while test_start_session + int(test_sessions) <= len(ordered_sessions):
        train_start_session = (
            0 if window_mode == "anchored" else test_start_session - int(train_sessions)
        )
        train_ids = ordered_sessions[train_start_session:test_start_session]
        test_ids = ordered_sessions[test_start_session : test_start_session + int(test_sessions)]
        folds.append(
            FoldBoundary(
                fold_id=fold_id,
                train_start=session_ranges[train_ids[0]][0],
                train_end_exclusive=session_ranges[train_ids[-1]][1],
                test_start=session_ranges[test_ids[0]][0],
                test_end_exclusive=session_ranges[test_ids[-1]][1],
                train_start_session=train_ids[0],
                train_end_session=train_ids[-1],
                test_start_session=test_ids[0],
                test_end_session=test_ids[-1],
                train_session_count=len(train_ids),
                test_session_count=len(test_ids),
            )
        )
        test_start_session += int(step_sessions)
        fold_id += 1
    return folds, session_ids


def _slice_subtimeframe_data(
    subtimeframe_data: pd.DataFrame | None,
    fold_df: pd.DataFrame,
) -> pd.DataFrame | None:
    if subtimeframe_data is None:
        return None
    parent_interval = infer_base_interval(fold_df["timestamp"])
    if parent_interval is None or fold_df.empty:
        return subtimeframe_data.iloc[0:0].copy()
    parent_timestamps = pd.to_datetime(fold_df["timestamp"], utc=True)
    sub_timestamps = pd.to_datetime(subtimeframe_data["timestamp"], utc=True)
    start = parent_timestamps.iloc[0]
    end = parent_timestamps.iloc[-1] + parent_interval
    return subtimeframe_data.loc[(sub_timestamps >= start) & (sub_timestamps < end)].copy()


def _actionable_index_column(
    signals: pd.DataFrame,
    *,
    executable_entry_ownership: bool = False,
) -> pd.Series:
    has_entry = "entry_bar_index" in signals.columns
    if has_entry:
        entry = pd.to_numeric(signals["entry_bar_index"], errors="coerce")
        if entry.notna().any():
            fallback = pd.to_numeric(signals["bar_index"], errors="coerce")
            if executable_entry_ownership:
                trigger = signals.get(
                    "trigger", pd.Series(index=signals.index, dtype=object)
                ).astype(str)
                simple_entry = fallback + 1
                fallback = fallback.where(trigger.eq("confirm_3bar"), simple_entry)
            return entry.where(entry.notna(), fallback)
    bar_index = pd.to_numeric(signals["bar_index"], errors="coerce")
    if not executable_entry_ownership:
        return bar_index
    trigger = signals.get("trigger", pd.Series(index=signals.index, dtype=object)).astype(str)
    return bar_index.where(trigger.eq("confirm_3bar"), bar_index + 1)


def _slice_signals(
    signals: pd.DataFrame,
    start_bar: int,
    end_bar_exclusive: int,
    n_slice_bars: int,
    executable_entry_ownership: bool = False,
) -> pd.DataFrame:
    if signals is None:
        return pd.DataFrame()
    if signals.empty:
        return signals.iloc[0:0].copy()

    actionable = _actionable_index_column(
        signals,
        executable_entry_ownership=executable_entry_ownership,
    )
    mask = actionable.ge(start_bar) & actionable.lt(end_bar_exclusive)
    sliced = signals.loc[mask].copy()
    if sliced.empty:
        return sliced

    sliced["bar_index"] = pd.to_numeric(sliced["bar_index"], errors="coerce") - start_bar
    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        sliced["entry_bar_index"] = entry - start_bar

    if executable_entry_ownership:
        local_actionable = actionable.loc[sliced.index] - start_bar
        valid = local_actionable.ge(0) & local_actionable.lt(n_slice_bars)
    else:
        valid = sliced["bar_index"].notna()
        valid &= sliced["bar_index"].ge(0) & sliced["bar_index"].lt(n_slice_bars)

    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        trigger = sliced.get("trigger", pd.Series(index=sliced.index, dtype=object)).astype(str)
        requires_entry = trigger.eq("3c")
        entry_valid = entry.ge(0) & entry.lt(n_slice_bars)
        valid &= (~requires_entry) | entry_valid

    sliced = sliced.loc[valid].copy()
    if sliced.empty:
        return sliced

    sliced["bar_index"] = sliced["bar_index"].astype(int)
    if "entry_bar_index" in sliced.columns:
        entry = pd.to_numeric(sliced["entry_bar_index"], errors="coerce")
        has_entry = entry.notna()
        sliced.loc[has_entry, "entry_bar_index"] = entry.loc[has_entry].astype(int)

    return sliced.reset_index(drop=True)


def run_walk_forward_sl_tp(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks_values: list[int | float],
    take_profit_ticks_values: list[int | float],
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    ranking_metric: str = "expectancy_r",
    min_train_trades: int = 1,
    max_holding_bars: int | None = None,
    allow_same_bar_exit: bool = True,
    commission_per_side: float = 0.0,
    slippage_ticks: float = 0.0,
    flat_by_session_close: bool = False,
    session_close_time: str | None = None,
    session_timezone: str | None = None,
    no_new_entries_after: str | None = None,
    exposure_policy: str = "allow_all",
    cooldown_bars_after_exit: int = 0,
    otf_config: dict[str, Any] | None = None,
    *,
    otf_history_policy: str | None = None,
    intrabar_model: str = "sl_first",
    subtimeframe_data: pd.DataFrame | None = None,
    parent_interval: pd.Timedelta | str | None = None,
    sub_interval: pd.Timedelta | str | None = None,
    breakeven_after_r_values: list[float | None] | None = None,
    trailing_after_r_values: list[float | None] | None = None,
    trailing_distance_ticks_values: list[float | None] | None = None,
    max_grid_cells: int = 500,
    fold_mode: str = "bars",
    window_mode: str = "rolling",
    train_sessions: int | None = None,
    test_sessions: int | None = None,
    step_sessions: int | None = None,
    exchange_timezone: str = "America/New_York",
    eth_start: str = "18:00",
    overlap_policy: str = "reject",
    return_result: bool = False,
) -> pd.DataFrame | WalkForwardResult:
    """Run deterministic bar-window walk-forward diagnostics for SL/TP selection.

    When *otf_config* is provided and ``otf_config["enabled"]`` is ``True``,
    OTF filtering is applied per fold. History policy:

    - ``fold_local`` (default): train/test signals are filtered against only
      their respective OHLCV slices.
    - ``causal_prefix``: each fold uses prefix∪fold-local OHLCV
      (``df.iloc[:fold_end]``) so prior completed HTF history can establish
      OTF state, while only fold-local signals are scored.

    Future bars after a fold end never influence that fold. OTF configuration
    is fixed across all folds; this function does not optimize OTF parameters.

    Parameters
    ----------
    otf_config:
        Optional canonical OTF filter config dict (as returned by
        ``normalize_otf_filter_config`` or ``get_effective_otf_filter_config``).
        When ``None`` or ``{"enabled": False, ...}``, OTF filtering is
        disabled and legacy behavior is preserved exactly.
    otf_history_policy:
        ``fold_local`` or ``causal_prefix``. Missing / ``None`` defaults to
        ``fold_local``. Unsupported values raise ``ValueError``.
    """
    if fold_mode not in {"bars", "sessions"}:
        raise ValueError("fold_mode must be 'bars' or 'sessions'.")
    if window_mode not in {"rolling", "anchored"}:
        raise ValueError("window_mode must be 'rolling' or 'anchored'.")
    if overlap_policy not in {"reject", "first", "last"}:
        raise ValueError("overlap_policy must be 'reject', 'first', or 'last'.")
    otf_history_policy_normalized = normalize_otf_history_policy(otf_history_policy)
    _validate_timeline(df)

    if fold_mode == "bars":
        if train_bars <= 0:
            raise ValueError("train_bars must be > 0.")
        if test_bars <= 0:
            raise ValueError("test_bars must be > 0.")
        step = test_bars if step_bars is None else int(step_bars)
        if step <= 0:
            raise ValueError("step_bars must be > 0.")
        boundaries = _bar_fold_boundaries(
            n_bars=len(df),
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step,
            window_mode=window_mode,
        )
        effective_step_sessions = None
    else:
        if train_sessions is None or train_sessions <= 0:
            raise ValueError("train_sessions must be > 0 in session mode.")
        if test_sessions is None or test_sessions <= 0:
            raise ValueError("test_sessions must be > 0 in session mode.")
        effective_step_sessions = (
            int(test_sessions) if step_sessions is None else int(step_sessions)
        )
        if effective_step_sessions <= 0:
            raise ValueError("step_sessions must be > 0.")
        boundaries, _session_ids = _session_fold_boundaries(
            df,
            train_sessions=int(train_sessions),
            test_sessions=int(test_sessions),
            step_sessions=effective_step_sessions,
            window_mode=window_mode,
            exchange_timezone=exchange_timezone,
            eth_start=eth_start,
        )
        step = test_bars if step_bars is None else int(step_bars)

    # Validate and normalize OTF config before fold processing.
    # normalize_otf_filter_config raises ValueError for explicit invalid config
    # (e.g. enabled=True with no timeframes, unsupported timeframe).  This
    # ensures invalid config is caught once, up front, rather than being
    # silently converted into "all-rejected" fold results.
    otf_normalized_config: dict[str, Any] | None = None
    if isinstance(otf_config, dict):
        otf_normalized_config = normalize_otf_filter_config(otf_config)
    _otf_enabled = otf_normalized_config is not None and bool(
        otf_normalized_config.get("enabled", False)
    )
    # OTF session alignment may fall back to exchange_timezone when session-exit
    # policy omits a timezone; session-exit simulation keeps session_timezone as-is.
    otf_session_timezone = resolve_otf_session_timezone(session_timezone, exchange_timezone)

    fold_rows: list[dict[str, Any]] = []
    oos_trade_frames: list[pd.DataFrame] = []

    for boundary in boundaries:
        fold_id = boundary.fold_id
        train_start = boundary.train_start
        train_end_exclusive = boundary.train_end_exclusive
        test_start = boundary.test_start
        test_end_exclusive = boundary.test_end_exclusive
        train_df = df.iloc[train_start:train_end_exclusive].reset_index(drop=True)
        test_df = df.iloc[test_start:test_end_exclusive].reset_index(drop=True)
        train_subtimeframe = _slice_subtimeframe_data(subtimeframe_data, train_df)
        test_subtimeframe = _slice_subtimeframe_data(subtimeframe_data, test_df)
        train_signals = _slice_signals(
            signals=signals,
            start_bar=train_start,
            end_bar_exclusive=train_end_exclusive,
            n_slice_bars=len(train_df),
            executable_entry_ownership=fold_mode == "sessions",
        )
        test_signals = _slice_signals(
            signals=signals,
            start_bar=test_start,
            end_bar_exclusive=test_end_exclusive,
            n_slice_bars=len(test_df),
            executable_entry_ownership=fold_mode == "sessions",
        )

        # OTF fold-local filtering: apply to train and test independently
        # using only their respective OHLCV slices to prevent future leakage.
        train_otf_candidate = int(len(train_signals))
        train_otf_accepted = train_otf_candidate
        train_otf_rejected = 0
        test_otf_candidate = int(len(test_signals))
        test_otf_accepted = test_otf_candidate
        test_otf_rejected = 0

        if _otf_enabled and otf_normalized_config is not None:
            train_otf_source = _otf_source_for_fold(
                df,
                fold_start=train_start,
                fold_end_exclusive=train_end_exclusive,
                otf_history_policy=otf_history_policy_normalized,
            )
            test_otf_source = _otf_source_for_fold(
                df,
                fold_start=test_start,
                fold_end_exclusive=test_end_exclusive,
                otf_history_policy=otf_history_policy_normalized,
            )
            # Apply OTF to train/test fold signals using the selected history policy.
            train_signals, train_otf_rejected, train_otf_candidate = _filter_fold_signals_with_otf(
                source_df=train_otf_source,
                fold_signals=train_signals,
                otf_config=otf_normalized_config,
                session_timezone=otf_session_timezone,
                eth_start=eth_start,
            )
            train_otf_accepted = int(len(train_signals))

            test_signals, test_otf_rejected, test_otf_candidate = _filter_fold_signals_with_otf(
                source_df=test_otf_source,
                fold_signals=test_signals,
                otf_config=otf_normalized_config,
                session_timezone=otf_session_timezone,
                eth_start=eth_start,
            )
            test_otf_accepted = int(len(test_signals))

        train_grid = run_sl_tp_grid(
            df=train_df,
            signals=train_signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks_values=stop_loss_ticks_values,
            take_profit_ticks_values=take_profit_ticks_values,
            max_holding_bars=max_holding_bars,
            allow_same_bar_exit=allow_same_bar_exit,
            commission_per_side=commission_per_side,
            slippage_ticks=slippage_ticks,
            flat_by_session_close=flat_by_session_close,
            session_close_time=session_close_time,
            session_timezone=session_timezone,
            no_new_entries_after=no_new_entries_after,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
            intrabar_model=intrabar_model,
            subtimeframe_data=train_subtimeframe,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            breakeven_after_r_values=breakeven_after_r_values,
            trailing_after_r_values=trailing_after_r_values,
            trailing_distance_ticks_values=trailing_distance_ticks_values,
            max_grid_cells=max_grid_cells,
        )
        best_train = best_grid_result(
            train_grid,
            metric=ranking_metric,
            min_trades=min_train_trades,
        )

        row: dict[str, Any] = {
            "fold_id": int(fold_id),
            "train_start_bar": int(train_start),
            "train_end_bar": int(train_end_exclusive - 1),
            "test_start_bar": int(test_start),
            "test_end_bar": int(test_end_exclusive - 1),
            "status": "ok",
            "selected_stop_loss_ticks": None,
            "selected_take_profit_ticks": None,
            "selected_metric_name": ranking_metric,
            "selected_train_metric_value": None,
            "train_trade_count": None,
            "train_expectancy_r": None,
            "train_total_r": None,
            "train_profit_factor": None,
            "train_win_rate": None,
            "train_sharpe_like_r": None,
            "train_sortino_like_r": None,
            "train_ulcer_index_r": None,
            "test_trade_count": None,
            "test_expectancy_r": None,
            "test_total_r": None,
            "test_profit_factor": None,
            "test_win_rate": None,
            "test_max_drawdown_r": None,
            "test_sharpe_like_r": None,
            "test_sortino_like_r": None,
            "test_ulcer_index_r": None,
            "test_recovery_factor": None,
            "degradation_expectancy_r": None,
            "is_oos_profitable": None,
            "ranking_metric": ranking_metric,
            "min_train_trades": int(min_train_trades),
            "train_bars": int(train_bars),
            "test_bars": int(test_bars),
            "step_bars": int(step),
            "exposure_policy": exposure_policy,
            "cooldown_bars_after_exit": int(cooldown_bars_after_exit),
            "commission_per_side": float(commission_per_side),
            "slippage_ticks": float(slippage_ticks),
            "flat_by_session_close": bool(flat_by_session_close),
            "session_close_time": session_close_time,
            "session_timezone": session_timezone,
            "no_new_entries_after": no_new_entries_after,
            "intrabar_model": intrabar_model,
            "breakeven_after_r": None,
            "trailing_after_r": None,
            "trailing_distance_ticks": None,
            # OTF fold metadata
            "otf_filter_enabled": _otf_enabled,
            "otf_history_policy": otf_history_policy_normalized,
            "train_otf_candidate_count": train_otf_candidate,
            "train_otf_accepted_count": train_otf_accepted,
            "train_otf_rejected_count": train_otf_rejected,
            "test_otf_candidate_count": test_otf_candidate,
            "test_otf_accepted_count": test_otf_accepted,
            "test_otf_rejected_count": test_otf_rejected,
            "fold_mode": fold_mode,
            "window_mode": window_mode,
            "train_start_session_date": boundary.train_start_session,
            "train_end_session_date": boundary.train_end_session,
            "test_start_session_date": boundary.test_start_session,
            "test_end_session_date": boundary.test_end_session,
            "train_session_count": boundary.train_session_count,
            "test_session_count": boundary.test_session_count,
            "retention_ratio_expectancy": None,
            "degradation_pct_expectancy": None,
            "ratio_status": "unavailable",
        }

        if best_train is None:
            row["status"] = "no_train_candidate"
            fold_rows.append(row)
            continue

        row["selected_stop_loss_ticks"] = best_train.get("stop_loss_ticks")
        row["selected_take_profit_ticks"] = best_train.get("take_profit_ticks")
        row["breakeven_after_r"] = best_train.get("breakeven_after_r")
        row["trailing_after_r"] = best_train.get("trailing_after_r")
        row["trailing_distance_ticks"] = best_train.get("trailing_distance_ticks")
        row["selected_train_metric_value"] = best_train.get(ranking_metric)
        row["train_trade_count"] = best_train.get("trade_count")
        row["train_expectancy_r"] = best_train.get("expectancy_r")
        row["train_total_r"] = best_train.get("total_r")
        row["train_profit_factor"] = best_train.get("profit_factor")
        row["train_win_rate"] = best_train.get("win_rate")
        row["train_sharpe_like_r"] = best_train.get("sharpe_like_r")
        row["train_sortino_like_r"] = best_train.get("sortino_like_r")
        row["train_ulcer_index_r"] = best_train.get("ulcer_index_r")

        test_trades = simulate_trades(
            df=test_df,
            signals=test_signals,
            tick_size=tick_size,
            point_value=point_value,
            stop_loss_ticks=float(best_train["stop_loss_ticks"]),
            take_profit_ticks=float(best_train["take_profit_ticks"]),
            max_holding_bars=max_holding_bars,
            allow_same_bar_exit=allow_same_bar_exit,
            commission_per_side=commission_per_side,
            slippage_ticks=slippage_ticks,
            flat_by_session_close=flat_by_session_close,
            session_close_time=session_close_time,
            session_timezone=session_timezone,
            no_new_entries_after=no_new_entries_after,
            exposure_policy=exposure_policy,
            cooldown_bars_after_exit=cooldown_bars_after_exit,
            intrabar_model=intrabar_model,
            subtimeframe_data=test_subtimeframe,
            parent_interval=parent_interval,
            sub_interval=sub_interval,
            breakeven_after_r=(
                None
                if pd.isna(best_train.get("breakeven_after_r"))
                else float(best_train.get("breakeven_after_r"))
            ),
            trailing_after_r=(
                None
                if pd.isna(best_train.get("trailing_after_r"))
                else float(best_train.get("trailing_after_r"))
            ),
            trailing_distance_ticks=(
                None
                if pd.isna(best_train.get("trailing_distance_ticks"))
                else float(best_train.get("trailing_distance_ticks"))
            ),
        )
        test_summary = summarize_trades(test_trades)
        if test_trades is not None and not test_trades.empty:
            fold_trades = test_trades.copy()
            fold_trades["fold_id"] = int(fold_id)
            fold_trades["global_entry_bar_index"] = (
                pd.to_numeric(fold_trades["entry_bar_index"], errors="coerce") + test_start
            )
            fold_trades["global_exit_bar_index"] = (
                pd.to_numeric(fold_trades["exit_bar_index"], errors="coerce") + test_start
            )
            fold_trades["test_start_bar"] = test_start
            fold_trades["test_end_bar"] = test_end_exclusive - 1
            if fold_mode == "sessions":
                fold_trades["test_start_session_date"] = boundary.test_start_session
                fold_trades["test_end_session_date"] = boundary.test_end_session
            oos_trade_frames.append(fold_trades)
        row["test_trade_count"] = test_summary.get("trade_count")
        row["test_expectancy_r"] = test_summary.get("expectancy_r")
        row["test_total_r"] = test_summary.get("total_r")
        row["test_profit_factor"] = test_summary.get("profit_factor")
        row["test_win_rate"] = test_summary.get("win_rate")
        row["test_max_drawdown_r"] = test_summary.get("max_drawdown_r")
        row["test_sharpe_like_r"] = test_summary.get("sharpe_like_r")
        row["test_sortino_like_r"] = test_summary.get("sortino_like_r")
        row["test_ulcer_index_r"] = test_summary.get("ulcer_index_r")
        row["test_recovery_factor"] = test_summary.get("recovery_factor")

        if row["train_expectancy_r"] is not None and row["test_expectancy_r"] is not None:
            train_expectancy = float(row["train_expectancy_r"])
            test_expectancy = float(row["test_expectancy_r"])
            row["degradation_expectancy_r"] = test_expectancy - train_expectancy
            if train_expectancy > 1e-12:
                retention = test_expectancy / train_expectancy
                row["retention_ratio_expectancy"] = retention
                row["degradation_pct_expectancy"] = retention - 1.0
                row["ratio_status"] = "ok"
            else:
                row["ratio_status"] = "nonpositive_or_undefined_is"
            row["is_oos_profitable"] = bool(float(row["test_expectancy_r"]) > 0.0)

        fold_rows.append(row)

    results = pd.DataFrame(fold_rows)
    if results.empty:
        results = pd.DataFrame(columns=_RESULT_COLUMNS)
    else:
        results = results.reindex(columns=_RESULT_COLUMNS)
    if not return_result:
        return results

    raw_oos = pd.concat(oos_trade_frames, ignore_index=True) if oos_trade_frames else pd.DataFrame()
    warnings: list[str] = []
    overlap_exists = False
    if len(boundaries) > 1:
        overlap_exists = any(
            current.test_start < previous.test_end_exclusive
            for previous, current in zip(boundaries, boundaries[1:])
        )
    stitched_trades = raw_oos.copy()
    stitched_status = "ok"
    if overlap_exists and overlap_policy == "reject":
        stitched_trades = raw_oos.iloc[0:0].copy()
        returned_oos_trades = raw_oos.copy()
        stitched_status = "overlapping_oos_windows"
        warnings.append(
            "OOS windows overlap; stitched equity is unavailable under overlap_policy='reject'."
        )
    elif overlap_exists and not raw_oos.empty:
        ascending = overlap_policy == "first"
        stitched_trades = (
            raw_oos.sort_values(
                ["global_entry_bar_index", "signal_id", "fold_id"],
                ascending=[True, True, ascending],
                kind="mergesort",
            )
            .drop_duplicates(
                subset=["global_entry_bar_index", "signal_id"],
                keep="first",
            )
            .reset_index(drop=True)
        )
        warnings.append(
            f"Overlapping OOS windows were deduplicated with overlap_policy={overlap_policy!r}."
        )
        returned_oos_trades = stitched_trades.copy()
    else:
        returned_oos_trades = stitched_trades.copy()
    if not stitched_trades.empty:
        stitched_trades = stitched_trades.sort_values(
            ["exit_timestamp", "entry_timestamp", "signal_id", "fold_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        stitched_trades["trade_id"] = range(len(stitched_trades))
        stitched_equity = equity_curve(stitched_trades)
        if not (overlap_exists and overlap_policy == "reject"):
            returned_oos_trades = stitched_trades.copy()
    else:
        stitched_equity = equity_curve(pd.DataFrame())
    if not returned_oos_trades.empty:
        returned_oos_trades = returned_oos_trades.reset_index(drop=True)
        returned_oos_trades["trade_id"] = range(len(returned_oos_trades))
    summary = summarize_walk_forward(results)
    summary.update(
        {
            "schema_version": 2,
            "stitched_oos_status": stitched_status,
            "stitched_oos_trade_count": int(len(stitched_trades)),
            "stitched_oos_total_r": (
                float(pd.to_numeric(stitched_trades["r_multiple"], errors="coerce").sum())
                if not stitched_trades.empty
                else None
            ),
            "median_retention_ratio_expectancy": (
                float(
                    pd.to_numeric(results["retention_ratio_expectancy"], errors="coerce").median()
                )
                if not results.empty
                and pd.to_numeric(results["retention_ratio_expectancy"], errors="coerce")
                .notna()
                .any()
                else None
            ),
        }
    )
    summary = dict(summary)
    summary["otf_history_policy"] = otf_history_policy_normalized
    summary["otf_filter_enabled"] = _otf_enabled
    return WalkForwardResult(
        schema_version=2,
        config={
            "fold_mode": fold_mode,
            "window_mode": window_mode,
            "train_bars": train_bars,
            "test_bars": test_bars,
            "step_bars": step,
            "train_sessions": train_sessions,
            "test_sessions": test_sessions,
            "step_sessions": effective_step_sessions,
            "exchange_timezone": exchange_timezone,
            "eth_start": eth_start,
            "overlap_policy": overlap_policy,
            "otf_history_policy": otf_history_policy_normalized,
            "otf_filter_enabled": _otf_enabled,
        },
        folds=results,
        oos_trades=returned_oos_trades,
        stitched_equity=stitched_equity,
        summary=summary,
        warnings=tuple(warnings),
    )


def summarize_walk_forward(results: pd.DataFrame) -> dict:
    """Return a compact JSON-safe summary for walk-forward fold results."""

    def _median_or_none(series: pd.Series) -> float | None:
        value = pd.to_numeric(series, errors="coerce").median()
        if pd.isna(value):
            return None
        return float(value)

    empty_summary = {
        "fold_count": 0,
        "valid_fold_count": 0,
        "oos_profitable_fold_count": 0,
        "oos_profitable_fold_rate": None,
        "median_train_expectancy_r": None,
        "median_test_expectancy_r": None,
        "median_degradation_expectancy_r": None,
        "median_test_sharpe_like_r": None,
        "median_test_sortino_like_r": None,
        "median_test_ulcer_index_r": None,
        "aggregate_test_total_r": None,
        "aggregate_test_trade_count": 0,
        "status": "empty",
    }
    if results is None or results.empty:
        return empty_summary

    fold_count = int(len(results))
    valid = results.loc[
        (results["status"] == "ok")
        & pd.to_numeric(results["test_expectancy_r"], errors="coerce").notna()
    ].copy()
    valid_fold_count = int(len(valid))
    if valid_fold_count == 0:
        return {
            **empty_summary,
            "fold_count": fold_count,
            "status": "no_valid_folds",
        }

    oos_profitable_fold_count = int(valid["is_oos_profitable"].fillna(False).astype(bool).sum())
    aggregate_test_total_r = pd.to_numeric(valid["test_total_r"], errors="coerce").sum()
    if pd.isna(aggregate_test_total_r):
        aggregate_test_total_r = None
    else:
        aggregate_test_total_r = float(aggregate_test_total_r)
    aggregate_test_trade_count = int(
        pd.to_numeric(valid["test_trade_count"], errors="coerce").fillna(0).sum()
    )
    return {
        "fold_count": fold_count,
        "valid_fold_count": valid_fold_count,
        "oos_profitable_fold_count": oos_profitable_fold_count,
        "oos_profitable_fold_rate": float(oos_profitable_fold_count / valid_fold_count),
        "median_train_expectancy_r": _median_or_none(valid["train_expectancy_r"]),
        "median_test_expectancy_r": _median_or_none(valid["test_expectancy_r"]),
        "median_degradation_expectancy_r": _median_or_none(valid["degradation_expectancy_r"]),
        "median_test_sharpe_like_r": _median_or_none(
            valid.get("test_sharpe_like_r", pd.Series(dtype=float))
        ),
        "median_test_sortino_like_r": _median_or_none(
            valid.get("test_sortino_like_r", pd.Series(dtype=float))
        ),
        "median_test_ulcer_index_r": _median_or_none(
            valid.get("test_ulcer_index_r", pd.Series(dtype=float))
        ),
        "aggregate_test_total_r": aggregate_test_total_r,
        "aggregate_test_trade_count": aggregate_test_trade_count,
        "status": "ok",
    }


def run_wfa_matrix(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    tick_size: float,
    point_value: float,
    stop_loss_ticks_values: list[int | float],
    take_profit_ticks_values: list[int | float],
    *,
    train_session_values: list[int],
    test_session_values: list[int],
    matrix_metric: str = "median_test_expectancy_r",
    max_matrix_cells: int = 25,
    window_mode: str = "rolling",
    exchange_timezone: str = "America/New_York",
    eth_start: str = "18:00",
    **walk_forward_kwargs: Any,
) -> pd.DataFrame:
    """Run a deterministic session-count WFA robustness matrix."""
    valid_metrics = {
        "median_test_expectancy_r",
        "median_retention_ratio_expectancy",
        "stitched_oos_total_r",
        "oos_profitable_fold_rate",
    }
    if matrix_metric not in valid_metrics:
        raise ValueError(f"matrix_metric must be one of {sorted(valid_metrics)}.")
    train_values = sorted(set(int(value) for value in train_session_values))
    test_values = sorted(set(int(value) for value in test_session_values))
    if not train_values or any(value <= 0 for value in train_values):
        raise ValueError("train_session_values must contain positive integers.")
    if not test_values or any(value <= 0 for value in test_values):
        raise ValueError("test_session_values must contain positive integers.")
    cell_count = len(train_values) * len(test_values)
    if cell_count > int(max_matrix_cells):
        raise ValueError(
            f"WFA matrix would run {cell_count} cells, exceeding "
            f"max_matrix_cells={max_matrix_cells}."
        )
    rows: list[dict[str, Any]] = []
    for train_sessions in train_values:
        for test_sessions in test_values:
            detailed = run_walk_forward_sl_tp(
                df=df,
                signals=signals,
                tick_size=tick_size,
                point_value=point_value,
                stop_loss_ticks_values=stop_loss_ticks_values,
                take_profit_ticks_values=take_profit_ticks_values,
                train_bars=1,
                test_bars=1,
                fold_mode="sessions",
                window_mode=window_mode,
                train_sessions=train_sessions,
                test_sessions=test_sessions,
                step_sessions=test_sessions,
                exchange_timezone=exchange_timezone,
                eth_start=eth_start,
                return_result=True,
                **walk_forward_kwargs,
            )
            summary = detailed.summary
            metric_value = summary.get(matrix_metric)
            rows.append(
                {
                    "train_sessions": train_sessions,
                    "test_sessions": test_sessions,
                    "fold_count": summary.get("fold_count", 0),
                    "valid_fold_count": summary.get("valid_fold_count", 0),
                    "median_test_expectancy_r": summary.get("median_test_expectancy_r"),
                    "median_retention_ratio_expectancy": summary.get(
                        "median_retention_ratio_expectancy"
                    ),
                    "stitched_oos_trade_count": summary.get("stitched_oos_trade_count", 0),
                    "stitched_oos_total_r": summary.get("stitched_oos_total_r"),
                    "matrix_metric": matrix_metric,
                    "matrix_value": metric_value,
                    "status": summary.get("status", "empty"),
                }
            )
    return (
        pd.DataFrame(rows).sort_values(["train_sessions", "test_sessions"]).reset_index(drop=True)
    )
