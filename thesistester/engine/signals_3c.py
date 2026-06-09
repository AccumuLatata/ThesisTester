"""Strict 3c detector over normalized candidate levels.

The detector emits one resolved row per setup:
- status="filled" when post-reversal retracement is touched
- status="void" when retracement is not touched within watch window

Two public entry-points exist:

* ``detect_3c_setups`` — base/current-timeframe detector (unchanged).
  Always use this when ``trigger_timeframe == "base"``.

* ``detect_3c_setups_with_trigger_timeframe`` — non-base detector.
  Arrival, inside/muted, SFP, and reversal are evaluated on a resampled
  trigger DataFrame.  Retrace fill is evaluated on canonical/base bars.
"""
from __future__ import annotations

from typing import Any

import math
import pandas as pd

from .candidate_level import CandidateLevel


_DEFAULT_3C_PARAMS: dict[str, float | int] = {
    # arrival_tolerance_ticks is deprecated and no longer user-configurable.
    # It is kept in defaults only for backward-compatible config parsing.
    "arrival_tolerance_ticks": 0.0,
    "entry_retrace_ticks": 4.0,
    "max_entry_wait_bars_after_reversal": 5,
}


def _normalize_3c_params(params: dict | None) -> dict[str, float | int]:
    p = params or {}
    return {
        # arrival_tolerance_ticks may appear in legacy configs, but its value is
        # intentionally ignored and normalized to 0.0 (strict level touch only).
        "arrival_tolerance_ticks": 0.0,
        "entry_retrace_ticks": float(p.get("entry_retrace_ticks", _DEFAULT_3C_PARAMS["entry_retrace_ticks"])),
        "max_entry_wait_bars_after_reversal": int(
            p.get("max_entry_wait_bars_after_reversal", _DEFAULT_3C_PARAMS["max_entry_wait_bars_after_reversal"])
        ),
    }


def _variant(direction: str, is_muted: bool, is_sfp: bool) -> str:
    if direction == "long":
        if is_sfp and is_muted:
            return "3c_sfp_long_muted"
        if is_sfp:
            return "3c_sfp_long"
        if is_muted:
            return "3c_long_muted"
        return "3c_long"
    if is_sfp and is_muted:
        return "3c_sfp_short_muted"
    if is_sfp:
        return "3c_sfp_short"
    if is_muted:
        return "3c_short_muted"
    return "3c_short"


def _rounded_price(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return float(price)
    ticks = round(float(price) / float(tick_size))
    return float(ticks * float(tick_size))


def _valid_bar_index(value: object, size: int) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    if f != math.floor(f):
        return None
    idx = int(f)
    if idx < 0 or idx >= size:
        return None
    return idx


def detect_3c_setups(
    df: pd.DataFrame,
    candidates: list[CandidateLevel],
    tick_size: float,
    trigger_params: dict | None = None,
) -> list[dict[str, Any]]:
    if df is None or df.empty or not candidates:
        return []

    params = _normalize_3c_params(trigger_params)
    tick_size_f = float(tick_size)
    arrival_tol = float(params["arrival_tolerance_ticks"]) * tick_size_f
    retrace_dist = float(params["entry_retrace_ticks"]) * tick_size_f
    max_wait = max(int(params["max_entry_wait_bars_after_reversal"]), 0)

    df_reset = df.reset_index(drop=True)
    n = len(df_reset)
    raw: list[dict[str, Any]] = []
    active_until_by_key: dict[tuple[float, str, str], int] = {}
    active_arrival_by_key: dict[tuple[float, str, str], int] = {}

    ordered_candidates = sorted(
        candidates,
        key=lambda c: (int(c.bar_index), str(c.source_mode), _rounded_price(float(c.level_price), tick_size_f)),
    )

    for candidate in ordered_candidates:
        directions = ["long", "short"] if candidate.direction == "both" else [candidate.direction]
        bar1_idx = int(candidate.bar_index)
        if bar1_idx < 0 or bar1_idx >= n:
            continue

        bar1 = df_reset.iloc[bar1_idx]
        bar1_low = float(bar1["low"])
        bar1_high = float(bar1["high"])
        bar1_close = float(bar1["close"])
        level_price = float(candidate.level_price)

        for direction in directions:
            effective_key = (
                _rounded_price(level_price, tick_size_f),
                direction,
                str(candidate.source_mode),
            )
            active_until = active_until_by_key.get(effective_key)
            active_arrival = active_arrival_by_key.get(effective_key)
            if active_until is not None and bar1_idx <= active_until and bar1_idx != active_arrival:
                continue

            if direction == "long":
                arrival_ok = bar1_low <= level_price + arrival_tol and bar1_close > level_price
            else:
                arrival_ok = float(bar1["high"]) >= level_price - arrival_tol and bar1_close < level_price
            if not arrival_ok:
                continue

            inside_count = 0
            reversal_idx: int | None = None
            reversal_close: float | None = None
            invalidated_at: int | None = None
            is_sfp = False

            for idx in range(bar1_idx + 1, n):
                bar = df_reset.iloc[idx]
                high = float(bar["high"])
                low = float(bar["low"])
                close = float(bar["close"])
                is_inside = high <= bar1_high and low >= bar1_low
                if is_inside:
                    inside_count += 1
                    continue

                if direction == "long":
                    rev_ok = close > bar1_high
                    sfp = low < bar1_low and rev_ok
                else:
                    rev_ok = close < bar1_low
                    sfp = high > bar1_high and rev_ok

                if rev_ok:
                    reversal_idx = idx
                    reversal_close = close
                    is_sfp = sfp
                else:
                    invalidated_at = idx
                break

            if reversal_idx is None or reversal_close is None:
                if invalidated_at is not None:
                    existing_active_until = active_until_by_key.get(effective_key)
                    if existing_active_until is None or invalidated_at >= int(existing_active_until):
                        active_until_by_key[effective_key] = int(invalidated_at)
                        active_arrival_by_key[effective_key] = bar1_idx
                continue

            if direction == "long":
                entry_trigger_price = reversal_close - retrace_dist
            else:
                entry_trigger_price = reversal_close + retrace_dist

            entry_idx: int | None = None
            watch_end = min(n - 1, reversal_idx + max_wait)
            for idx in range(reversal_idx + 1, watch_end + 1):
                bar = df_reset.iloc[idx]
                if direction == "long":
                    hit = float(bar["low"]) <= entry_trigger_price
                else:
                    hit = float(bar["high"]) >= entry_trigger_price
                if hit:
                    entry_idx = idx
                    break

            status = "filled" if entry_idx is not None else "void"
            resolved_through_bar = int(entry_idx) if entry_idx is not None else int(watch_end)
            is_muted = inside_count > 0
            raw.append(
                {
                    "timestamp": df_reset.iloc[entry_idx]["timestamp"] if entry_idx is not None else df_reset.iloc[reversal_idx]["timestamp"],
                    "bar_index": entry_idx if entry_idx is not None else reversal_idx,
                    "direction": direction,
                    "trigger_variant": _variant(direction, is_muted, is_sfp),
                    "is_muted": is_muted,
                    "is_sfp": is_sfp,
                    "inside_candle_count": inside_count,
                    "arrival_bar_index": bar1_idx,
                    "reversal_bar_index": reversal_idx,
                    "entry_bar_index": entry_idx,
                    "entry_trigger_price": entry_trigger_price,
                    "retrace_entry_price": entry_trigger_price if entry_idx is not None else None,
                    "status": status,
                    "arrival_level_price": level_price,
                    "level_source_mode": candidate.source_mode,
                    "level_source_label": candidate.source_label,
                    "zone_id": candidate.zone_id,
                    "level_id": candidate.level_id,
                    "entry_retrace_ticks": float(params["entry_retrace_ticks"]),
                    "source_labels": [candidate.source_label] if candidate.source_label else [],
                    "zone_ids": [candidate.zone_id] if candidate.zone_id else [],
                    "level_ids": [candidate.level_id] if candidate.level_id else [],
                    "source_count": 1,
                    "level_test_state_at_arrival": candidate.metadata.get("level_test_state_at_arrival"),
                    "was_naked_before_arrival": candidate.metadata.get("was_naked_before_arrival"),
                }
            )
            existing_active_until = active_until_by_key.get(effective_key)
            if existing_active_until is None or resolved_through_bar >= int(existing_active_until):
                active_until_by_key[effective_key] = resolved_through_bar
                active_arrival_by_key[effective_key] = bar1_idx

    # Deduplicate by effective setup key while preserving merged metadata.
    merged: dict[tuple[float, str, int, str], dict[str, Any]] = {}
    for row in raw:
        key = (
            _rounded_price(float(row["arrival_level_price"]), float(tick_size)),
            str(row["direction"]),
            int(row["arrival_bar_index"]),
            str(row["level_source_mode"]),
        )
        if key not in merged:
            merged[key] = row
            continue
        prev = merged[key]

        # Keep filled over void.
        if prev["status"] == "void" and row["status"] == "filled":
            keep, other = row, prev
        elif prev["status"] == "filled" and row["status"] == "void":
            keep, other = prev, row
        else:
            keep, other = prev, row

        labels = set(keep.get("source_labels", [])) | set(other.get("source_labels", []))
        zone_ids = set(keep.get("zone_ids", [])) | set(other.get("zone_ids", []))
        level_ids = set(keep.get("level_ids", [])) | set(other.get("level_ids", []))
        keep["source_labels"] = sorted(v for v in labels if v)
        keep["zone_ids"] = sorted(v for v in zone_ids if v)
        keep["level_ids"] = sorted(v for v in level_ids if v)
        keep["source_count"] = len(keep["level_ids"]) if keep["level_ids"] else max(int(keep.get("source_count", 1)), 1)
        merged[key] = keep

    out = list(merged.values())
    out.sort(key=lambda row: (int(row["arrival_bar_index"]), int(row["reversal_bar_index"]), row["direction"]))
    return out


# ---------------------------------------------------------------------------
# Non-base 3c detector
# ---------------------------------------------------------------------------


def detect_3c_setups_with_trigger_timeframe(
    *,
    trigger_df: pd.DataFrame,
    base_df: pd.DataFrame,
    candidates: list[CandidateLevel],
    tick_size: float,
    trigger_params: dict | None,
    trigger_timeframe_delta: pd.Timedelta,
) -> list[dict[str, Any]]:
    """Detect 3c setups using a non-base trigger timeframe.

    Arrival, inside/muted candles, SFP tagging, and reversal confirmation are
    evaluated on *trigger_df*.  Retrace entry fill is evaluated on canonical/base
    bars (*base_df*) after the reversal trigger candle is complete.

    Parameters
    ----------
    trigger_df:
        Resampled trigger-timeframe DataFrame produced by
        ``_prepare_trigger_dataframe``.  Must contain the standard mapping
        columns: ``trigger_bar_index``, ``trigger_bar_end_timestamp``,
        ``base_end_bar_index``, ``base_start_bar_index``.
    base_df:
        Canonical/base OHLCV DataFrame (reset-index).
    candidates:
        Candidate levels whose ``bar_index`` is a *trigger* bar index.
    tick_size:
        Instrument tick size.
    trigger_params:
        Optional trigger parameter dict (same schema as for ``detect_3c_setups``).
    trigger_timeframe_delta:
        ``pd.Timedelta`` for the selected trigger timeframe (e.g.
        ``pd.Timedelta('5min')`` for ``trigger_timeframe="5min"``).

    Returns
    -------
    list[dict]
        One resolved row per setup (``status="filled"`` or ``status="void"``).
        Output schema is compatible with ``detect_3c_setups`` and additionally
        includes:

        * ``trigger_arrival_bar_index`` — trigger df index of the arrival candle
        * ``trigger_reversal_bar_index`` — trigger df index of the reversal candle
        * ``trigger_bar_index`` — equals ``trigger_reversal_bar_index``
        * ``trigger_timestamp`` — reversal trigger candle completion timestamp

        Index semantics (invariants):

        * ``arrival_bar_index``, ``reversal_bar_index``, ``entry_bar_index``,
          ``bar_index`` are all canonical/base indices.
        * ``trigger_arrival_bar_index``, ``trigger_reversal_bar_index``,
          ``trigger_bar_index`` are trigger-df indices.
        * ``timestamp == base_df["timestamp"].iloc[bar_index]`` (when bar_index
          is valid).
    """
    if trigger_df is None or trigger_df.empty or base_df is None or base_df.empty or not candidates:
        return []

    params = _normalize_3c_params(trigger_params)
    tick_size_f = float(tick_size)
    arrival_tol = float(params["arrival_tolerance_ticks"]) * tick_size_f  # always 0.0
    retrace_dist = float(params["entry_retrace_ticks"]) * tick_size_f
    max_wait = max(int(params["max_entry_wait_bars_after_reversal"]), 0)

    trigger_df_reset = trigger_df.reset_index(drop=True)
    base_df_reset = base_df.reset_index(drop=True)
    n_trigger = len(trigger_df_reset)
    n_base = len(base_df_reset)

    raw: list[dict[str, Any]] = []
    active_until_by_key: dict[tuple[float, str, str], int] = {}
    active_arrival_by_key: dict[tuple[float, str, str], int] = {}

    ordered_candidates = sorted(
        candidates,
        key=lambda c: (int(c.bar_index), str(c.source_mode), _rounded_price(float(c.level_price), tick_size_f)),
    )

    for candidate in ordered_candidates:
        directions = ["long", "short"] if candidate.direction == "both" else [candidate.direction]
        t_arr_idx = int(candidate.bar_index)  # trigger df index of arrival candle
        if t_arr_idx < 0 or t_arr_idx >= n_trigger:
            continue

        t_arr_row = trigger_df_reset.iloc[t_arr_idx]
        t_arr_low = float(t_arr_row["low"])
        t_arr_high = float(t_arr_row["high"])
        t_arr_close = float(t_arr_row["close"])
        level_price = float(candidate.level_price)

        # Base index at arrival trigger candle end (used for naked metadata and
        # as the emitted arrival_bar_index).
        base_arrival_idx = _valid_bar_index(t_arr_row.get("base_end_bar_index"), n_base)
        if base_arrival_idx is None:
            continue

        for direction in directions:
            effective_key = (
                _rounded_price(level_price, tick_size_f),
                direction,
                str(candidate.source_mode),
            )
            active_until = active_until_by_key.get(effective_key)
            active_arrival = active_arrival_by_key.get(effective_key)
            if active_until is not None and t_arr_idx <= active_until and t_arr_idx != active_arrival:
                continue

            if direction == "long":
                arrival_ok = t_arr_low <= level_price + arrival_tol and t_arr_close > level_price
            else:
                arrival_ok = t_arr_high >= level_price - arrival_tol and t_arr_close < level_price
            if not arrival_ok:
                continue

            inside_count = 0
            t_rev_idx: int | None = None
            reversal_close: float | None = None
            invalidated_at: int | None = None
            is_sfp = False

            for idx in range(t_arr_idx + 1, n_trigger):
                bar = trigger_df_reset.iloc[idx]
                high = float(bar["high"])
                low = float(bar["low"])
                close = float(bar["close"])
                is_inside = high <= t_arr_high and low >= t_arr_low
                if is_inside:
                    inside_count += 1
                    continue

                if direction == "long":
                    rev_ok = close > t_arr_high
                    sfp = low < t_arr_low and rev_ok
                else:
                    rev_ok = close < t_arr_low
                    sfp = high > t_arr_high and rev_ok

                if rev_ok:
                    t_rev_idx = idx
                    reversal_close = close
                    is_sfp = sfp
                else:
                    invalidated_at = idx
                break

            if t_rev_idx is None or reversal_close is None:
                if invalidated_at is not None:
                    existing_active_until = active_until_by_key.get(effective_key)
                    if existing_active_until is None or invalidated_at >= int(existing_active_until):
                        active_until_by_key[effective_key] = int(invalidated_at)
                        active_arrival_by_key[effective_key] = t_arr_idx
                continue

            # Reversal trigger candle end timestamp — used as base-scan boundary.
            t_rev_row = trigger_df_reset.iloc[t_rev_idx]
            reversal_trigger_ts = t_rev_row["trigger_bar_end_timestamp"]
            base_reversal_idx = _valid_bar_index(t_rev_row.get("base_end_bar_index"), n_base)
            if base_reversal_idx is None:
                continue

            if direction == "long":
                entry_trigger_price = reversal_close - retrace_dist
            else:
                entry_trigger_price = reversal_close + retrace_dist

            # Window end: reversal_trigger_ts + max_wait * trigger_timeframe_delta
            window_end_ts = reversal_trigger_ts + max_wait * trigger_timeframe_delta

            # Scan base bars for retrace fill.
            # Eligible: base.timestamp > reversal_trigger_ts AND <= window_end_ts
            entry_idx_base: int | None = None

            for b_idx in range(base_reversal_idx + 1, n_base):
                b_ts = base_df_reset.iloc[b_idx]["timestamp"]
                if b_ts <= reversal_trigger_ts:
                    continue
                if b_ts > window_end_ts:
                    break
                bar = base_df_reset.iloc[b_idx]
                if direction == "long":
                    hit = float(bar["low"]) <= entry_trigger_price
                else:
                    hit = float(bar["high"]) >= entry_trigger_price
                if hit:
                    entry_idx_base = b_idx
                    break

            status = "filled" if entry_idx_base is not None else "void"
            resolved_through_trigger = t_rev_idx + max_wait  # trigger bar count

            # bar_index and timestamp: base-indexed
            if entry_idx_base is not None:
                bar_index_base = entry_idx_base
                ts_base = base_df_reset.iloc[entry_idx_base]["timestamp"]
            else:
                bar_index_base = base_reversal_idx
                ts_base = base_df_reset.iloc[base_reversal_idx]["timestamp"]

            is_muted = inside_count > 0
            raw.append(
                {
                    "timestamp": ts_base,
                    "bar_index": bar_index_base,
                    "direction": direction,
                    "trigger_variant": _variant(direction, is_muted, is_sfp),
                    "is_muted": is_muted,
                    "is_sfp": is_sfp,
                    "inside_candle_count": inside_count,
                    # Base indices
                    "arrival_bar_index": base_arrival_idx,
                    "reversal_bar_index": base_reversal_idx,
                    "entry_bar_index": entry_idx_base,
                    "entry_trigger_price": entry_trigger_price,
                    "retrace_entry_price": entry_trigger_price if entry_idx_base is not None else None,
                    "status": status,
                    "arrival_level_price": level_price,
                    "level_source_mode": candidate.source_mode,
                    "level_source_label": candidate.source_label,
                    "zone_id": candidate.zone_id,
                    "level_id": candidate.level_id,
                    "entry_retrace_ticks": float(params["entry_retrace_ticks"]),
                    "source_labels": [candidate.source_label] if candidate.source_label else [],
                    "zone_ids": [candidate.zone_id] if candidate.zone_id else [],
                    "level_ids": [candidate.level_id] if candidate.level_id else [],
                    "level_test_state_at_arrival": candidate.metadata.get("level_test_state_at_arrival"),
                    "was_naked_before_arrival": candidate.metadata.get("was_naked_before_arrival"),
                    # Trigger-index metadata
                    "trigger_arrival_bar_index": t_arr_idx,
                    "trigger_reversal_bar_index": t_rev_idx,
                    "trigger_bar_index": t_rev_idx,
                    "trigger_timestamp": reversal_trigger_ts,
                }
            )
            existing_active_until = active_until_by_key.get(effective_key)
            if existing_active_until is None or resolved_through_trigger >= int(existing_active_until):
                active_until_by_key[effective_key] = resolved_through_trigger
                active_arrival_by_key[effective_key] = t_arr_idx

    # Deduplicate by effective setup key (same logic as detect_3c_setups).
    merged: dict[tuple[float, str, int, str], dict[str, Any]] = {}
    for row in raw:
        key = (
            _rounded_price(float(row["arrival_level_price"]), float(tick_size)),
            str(row["direction"]),
            int(row["arrival_bar_index"]),
            str(row["level_source_mode"]),
        )
        if key not in merged:
            merged[key] = row
            continue
        prev = merged[key]

        if prev["status"] == "void" and row["status"] == "filled":
            keep, other = row, prev
        elif prev["status"] == "filled" and row["status"] == "void":
            keep, other = prev, row
        else:
            keep, other = prev, row

        labels = set(keep.get("source_labels", [])) | set(other.get("source_labels", []))
        zone_ids = set(keep.get("zone_ids", [])) | set(other.get("zone_ids", []))
        level_ids = set(keep.get("level_ids", [])) | set(other.get("level_ids", []))
        keep["source_labels"] = sorted(v for v in labels if v)
        keep["zone_ids"] = sorted(v for v in zone_ids if v)
        keep["level_ids"] = sorted(v for v in level_ids if v)
        keep["source_count"] = len(keep["level_ids"]) if keep["level_ids"] else max(int(keep.get("source_count", 1)), 1)
        merged[key] = keep

    out = list(merged.values())
    out.sort(key=lambda row: (int(row["arrival_bar_index"]), int(row["reversal_bar_index"]), row["direction"]))
    return out
