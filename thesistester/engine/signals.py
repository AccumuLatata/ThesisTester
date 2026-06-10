"""Candidate signal generation from confluence zones and trigger logic."""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from thesistester.setup import VALID_TRIGGER_TIMEFRAMES, normalize_trigger_timeframe

from .candidate_level import CandidateLevel, from_anchor_zones, from_global_cluster_zones, with_metadata
from .signals_3c import detect_3c_setups, detect_3c_setups_with_trigger_timeframe


VALID_TRIGGERS = frozenset({"touch", "reject", "break", "reclaim", "3c"})
VALID_DIRECTIONS = frozenset({"long", "short", "both"})

_DEFAULT_3BAR_PARAMS: dict = {
    "arrival_tolerance_ticks": 0,
    "activation_retrace_ticks": 4,
    "entry_offset_ticks": 0,
    "allow_equal_close": False,
}

_DEFAULT_3C_PARAMS: dict = {
    "arrival_tolerance_ticks": 0.0,
    "entry_retrace_ticks": 4.0,
    "max_entry_wait_bars_after_reversal": 5,
}

_SIGNAL_COLUMNS: list[str] = [
    "signal_id",
    "timestamp",
    "bar_index",
    "trigger_bar_index",
    "trigger_timeframe",
    "trigger_timestamp",
    "trigger",
    "direction",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "tested_level_name",
    "tested_level_price",
    "arrival_bar_index",
    "reversal_bar_index",
    "confirmation_bar_index",
    "reversal_type",
    "is_sfp_reversal",
    "activation_price",
    "entry_price",
    "activation_retrace_ticks",
    "entry_offset_ticks",
    "entry_reference_price",
    "entry_model",
    "status",
    "trigger_variant",
    "is_muted",
    "is_sfp",
    "inside_candle_count",
    "level_source_mode",
    "level_source_label",
    "zone_id",
    "level_id",
    "arrival_level_price",
    "entry_bar_index",
    "entry_trigger_price",
    "retrace_entry_price",
    "retrace_ticks_required",
    "source_labels",
    "source_count",
    "zone_ids",
    "level_ids",
    "level_test_state_at_arrival",
    "was_naked_before_arrival",
    "naked_level_count",
    "naked_requirement",
    "notes",
    "trigger_arrival_bar_index",
    "trigger_reversal_bar_index",
]


def _empty_signals_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_SIGNAL_COLUMNS)


def _naked_count(zone_level_names: str, bar_idx: int, naked_flags: pd.DataFrame) -> int:
    """Count how many levels in the zone are naked at *bar_idx*."""
    count = 0
    for name in zone_level_names.split("|"):
        col = name + "_naked"
        if col in naked_flags.columns and bar_idx < len(naked_flags):
            if naked_flags[col].iloc[bar_idx]:
                count += 1
    return count


def _safe_signal_float(value: object) -> float | None:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if pd.isna(result) or not math.isfinite(result):
        return None
    return result


def _safe_signal_index(value: object, size: int) -> int | None:
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


def _make_signal(
    *,
    signal_id: int,
    ts: object,
    bar_idx: int,
    trigger_bar_index: int | None = None,
    trigger_timeframe: str = "base",
    trigger_timestamp: object | None = None,
    trigger: str,
    direction: str,
    zone: pd.Series,
    entry_ref: float,
    entry_model: str,
    status: str,
    naked_count: int,
    naked_req: str,
    notes: str = "",
    tested_level_name: str | None = None,
    tested_level_price: float | None = None,
    arrival_bar_index: int | None = None,
    reversal_bar_index: int | None = None,
    confirmation_bar_index: int | None = None,
    reversal_type: str | None = None,
    is_sfp_reversal: bool | None = None,
    activation_price: float | None = None,
    entry_price: float | None = None,
    activation_retrace_ticks: float | None = None,
    entry_offset_ticks: float | None = None,
    trigger_variant: str | None = None,
    is_muted: bool | None = None,
    is_sfp: bool | None = None,
    inside_candle_count: int | None = None,
    level_source_mode: str | None = None,
    level_source_label: str | None = None,
    zone_id: str | None = None,
    level_id: str | None = None,
    arrival_level_price: float | None = None,
    entry_bar_index: int | None = None,
    entry_trigger_price: float | None = None,
    retrace_entry_price: float | None = None,
    retrace_ticks_required: float | None = None,
    source_labels: str | None = None,
    source_count: int | None = None,
    zone_ids: str | None = None,
    level_ids: str | None = None,
    level_test_state_at_arrival: str | None = None,
    was_naked_before_arrival: bool | None = None,
    trigger_arrival_bar_index: int | None = None,
    trigger_reversal_bar_index: int | None = None,
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": ts,
        "bar_index": bar_idx,
        "trigger_bar_index": trigger_bar_index,
        "trigger_timeframe": trigger_timeframe,
        "trigger_timestamp": trigger_timestamp if trigger_timestamp is not None else ts,
        "trigger": trigger,
        "direction": direction,
        "zone_low": zone["zone_low"],
        "zone_high": zone["zone_high"],
        "zone_mid": zone["zone_mid"],
        "level_count": zone["level_count"],
        "level_names": zone["level_names"],
        "tested_level_name": tested_level_name,
        "tested_level_price": tested_level_price,
        "arrival_bar_index": arrival_bar_index,
        "reversal_bar_index": reversal_bar_index,
        "confirmation_bar_index": confirmation_bar_index,
        "reversal_type": reversal_type,
        "is_sfp_reversal": is_sfp_reversal,
        "activation_price": activation_price,
        "entry_price": entry_price,
        "activation_retrace_ticks": activation_retrace_ticks,
        "entry_offset_ticks": entry_offset_ticks,
        "entry_reference_price": entry_ref,
        "entry_model": entry_model,
        "status": status,
        "trigger_variant": trigger_variant,
        "is_muted": is_muted,
        "is_sfp": is_sfp,
        "inside_candle_count": inside_candle_count,
        "level_source_mode": level_source_mode,
        "level_source_label": level_source_label,
        "zone_id": zone_id,
        "level_id": level_id,
        "arrival_level_price": arrival_level_price,
        "entry_bar_index": entry_bar_index,
        "entry_trigger_price": entry_trigger_price,
        "retrace_entry_price": retrace_entry_price,
        "retrace_ticks_required": retrace_ticks_required,
        "source_labels": source_labels,
        "source_count": source_count,
        "zone_ids": zone_ids,
        "level_ids": level_ids,
        "level_test_state_at_arrival": level_test_state_at_arrival,
        "was_naked_before_arrival": was_naked_before_arrival,
        "naked_level_count": naked_count,
        "naked_requirement": naked_req,
        "notes": notes,
        "trigger_arrival_bar_index": trigger_arrival_bar_index,
        "trigger_reversal_bar_index": trigger_reversal_bar_index,
    }


# ---------------------------------------------------------------------------
# Per-trigger helpers
# ---------------------------------------------------------------------------


def _normalize_confirm_3bar_params(trigger_params: dict | None) -> dict:
    params = trigger_params or {}
    activation_retrace_ticks = params.get(
        "activation_retrace_ticks",
        params.get("retrace_entry_ticks", _DEFAULT_3BAR_PARAMS["activation_retrace_ticks"]),
    )
    return {
        "arrival_tolerance_ticks": params.get(
            "arrival_tolerance_ticks",
            _DEFAULT_3BAR_PARAMS["arrival_tolerance_ticks"],
        ),
        "activation_retrace_ticks": activation_retrace_ticks,
        "entry_offset_ticks": params.get(
            "entry_offset_ticks",
            _DEFAULT_3BAR_PARAMS["entry_offset_ticks"],
        ),
        "allow_equal_close": params.get(
            "allow_equal_close",
            _DEFAULT_3BAR_PARAMS["allow_equal_close"],
        ),
    }


def _normalize_3c_params(trigger_params: dict | None) -> dict:
    params = trigger_params or {}
    return {
        # arrival_tolerance_ticks may appear in legacy configs, but its value is
        # intentionally ignored and normalized to 0.0.
        "arrival_tolerance_ticks": 0.0,
        "entry_retrace_ticks": float(
            params.get("entry_retrace_ticks", _DEFAULT_3C_PARAMS["entry_retrace_ticks"])
        ),
        "max_entry_wait_bars_after_reversal": int(
            params.get(
                "max_entry_wait_bars_after_reversal",
                _DEFAULT_3C_PARAMS["max_entry_wait_bars_after_reversal"],
            )
        ),
        "_source_mode": str(params.get("_source_mode", "global_cluster")),
    }


def _parse_zone_levels(zone: pd.Series) -> list[tuple[str, float]]:
    names_raw = zone.get("level_names", "")
    prices_raw = zone.get("level_prices", "")
    names = str(names_raw).split("|") if pd.notna(names_raw) else []
    prices = str(prices_raw).split("|") if pd.notna(prices_raw) else []

    pairs: list[tuple[str, float]] = []
    for name, price_raw in zip(names, prices):
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(price):
            continue
        pairs.append((str(name).strip(), price))
    return pairs


def _find_tested_level_for_arrival(
    *,
    df: pd.DataFrame,
    zone: pd.Series,
    bar1_idx: int,
    direction: str,
    tick_size: float,
    arrival_tolerance_ticks: float,
) -> tuple[str, float] | None:
    levels = _parse_zone_levels(zone)
    if not levels:
        return None

    bar1 = df.iloc[bar1_idx]
    bar1_open = float(bar1["open"])
    bar1_low = float(bar1["low"])
    bar1_high = float(bar1["high"])
    bar1_close = float(bar1["close"])
    # arrival_tolerance_ticks is deprecated; effective tolerance is always 0.
    # The parameter is kept in the signature for backward-compatible callers.
    tol = 0.0
    previous_close = float(df.iloc[bar1_idx - 1]["close"]) if bar1_idx > 0 else None

    candidates: list[tuple[str, float]] = []
    for level_name, level_price in levels:
        if direction == "long":
            level_hit = bar1_low <= level_price + tol
            close_reclaimed = bar1_close > level_price
            approach_from_above = (
                bar1_open > level_price
                or (previous_close is not None and previous_close > level_price)
            )
            qualifies = level_hit and close_reclaimed and approach_from_above
        else:
            level_hit = bar1_high >= level_price - tol
            close_reclaimed = bar1_close < level_price
            approach_from_below = (
                bar1_open < level_price
                or (previous_close is not None and previous_close < level_price)
            )
            qualifies = level_hit and close_reclaimed and approach_from_below

        if qualifies:
            candidates.append((level_name, level_price))

    if not candidates:
        return None
    if direction == "long":
        return max(candidates, key=lambda item: item[1])
    return min(candidates, key=lambda item: item[1])


def _prepare_trigger_dataframe(df: pd.DataFrame, trigger_timeframe: str) -> pd.DataFrame:
    """Build trigger bars with explicit mapping back to canonical/base bars."""
    df_reset = df.reset_index(drop=True).copy()
    if df_reset.empty:
        return df_reset

    normalized_trigger_timeframe = normalize_trigger_timeframe(trigger_timeframe)
    level_columns = [
        column
        for column in df_reset.columns
        if column not in {"timestamp", "open", "high", "low", "close", "volume"}
    ]
    df_reset["__base_index"] = df_reset.index.astype(int)

    if normalized_trigger_timeframe == "base":
        trigger_df = df_reset.copy()
        trigger_df["trigger_bar_index"] = trigger_df.index.astype(int)
        trigger_df["trigger_timeframe"] = normalized_trigger_timeframe
        trigger_df["trigger_bar_start_timestamp"] = trigger_df["timestamp"]
        trigger_df["trigger_bar_end_timestamp"] = trigger_df["timestamp"]
        trigger_df["base_end_timestamp"] = trigger_df["timestamp"]
        trigger_df["base_start_bar_index"] = trigger_df["__base_index"]
        trigger_df["base_end_bar_index"] = trigger_df["__base_index"]
        return trigger_df.drop(columns=["__base_index"])

    timeframe_delta = pd.to_timedelta(normalized_trigger_timeframe)
    grouped = df_reset.copy()
    try:
        timestamps = grouped["timestamp"]
        if not pd.api.types.is_datetime64_any_dtype(timestamps):
            timestamps = pd.to_datetime(timestamps, errors="raise")
            grouped["timestamp"] = timestamps
        if timestamps.dt.tz is not None:
            original_tz = timestamps.dt.tz
            floored = timestamps.dt.tz_convert("UTC").dt.floor(normalized_trigger_timeframe)
            grouped["trigger_bar_start_timestamp"] = floored.dt.tz_convert(original_tz)
        else:
            grouped["trigger_bar_start_timestamp"] = timestamps.dt.floor(normalized_trigger_timeframe)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Unable to prepare trigger timeframe '{normalized_trigger_timeframe}' "
            "from timestamp data. Check for invalid, ambiguous, or timezone-incompatible timestamps."
        ) from exc
    grouped["trigger_bar_end_timestamp"] = grouped["trigger_bar_start_timestamp"] + timeframe_delta
    grouped["base_end_timestamp"] = grouped["timestamp"]

    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "__base_index": "last",
        "timestamp": "last",
        "base_end_timestamp": "last",
    }
    for column in level_columns:
        aggregations[column] = "last"

    trigger_df = (
        grouped.groupby(
            ["trigger_bar_start_timestamp", "trigger_bar_end_timestamp"],
            sort=True,
            observed=False,
            as_index=False,
        )
        .agg(aggregations)
        .rename(columns={"__base_index": "base_end_bar_index"})
    )
    base_start_indices = (
        grouped.groupby(
            ["trigger_bar_start_timestamp", "trigger_bar_end_timestamp"],
            sort=True,
            observed=False,
        )["__base_index"]
        .min()
        .reset_index(name="base_start_bar_index")
    )
    trigger_df = trigger_df.merge(
        base_start_indices,
        on=["trigger_bar_start_timestamp", "trigger_bar_end_timestamp"],
        how="left",
    )
    trigger_df["base_end_bar_index"] = trigger_df["base_end_bar_index"].astype(int)
    trigger_df["base_start_bar_index"] = trigger_df["base_start_bar_index"].astype(int)
    trigger_df["trigger_bar_index"] = trigger_df.index.astype(int)
    trigger_df["trigger_timeframe"] = normalized_trigger_timeframe
    return trigger_df


def _project_zones_to_trigger_df(
    zones: pd.DataFrame,
    trigger_df: pd.DataFrame,
) -> pd.DataFrame:
    """Map base-indexed zones to their containing trigger bar.

    For each zone row whose ``bar_index`` falls within the trigger bar's
    ``[base_start_bar_index, base_end_bar_index]`` range, produce a new row
    with ``bar_index = trigger_bar_index`` and ``timestamp = trigger_bar_end_timestamp``.

    A ``base_end_bar_index`` column is preserved in the output so that callers
    can correctly look up naked flags using the canonical/base arrival index.

    Zones with no matching trigger bar are silently dropped (they are outside
    the trigger-timeframe window).
    """
    if zones is None or zones.empty or trigger_df is None or trigger_df.empty:
        return pd.DataFrame(columns=list(zones.columns) if zones is not None and not zones.empty else [])

    tdf = trigger_df.reset_index(drop=True)

    # Build a lookup: base bar index -> trigger bar row (for each base bar in any trigger bar)
    # This handles zones whose bar_index may not be exactly the base_end_bar_index.
    trigger_by_any_base: dict[int, pd.Series] = {}
    for _, trow in tdf.iterrows():
        start = int(trow["base_start_bar_index"])
        end = int(trow["base_end_bar_index"])
        for b_idx in range(start, end + 1):
            if b_idx not in trigger_by_any_base:
                trigger_by_any_base[b_idx] = trow

    projected_rows: list[dict] = []
    for _, zone_row in zones.reset_index(drop=True).iterrows():
        base_idx = int(zone_row["bar_index"])
        trow = trigger_by_any_base.get(base_idx)
        if trow is None:
            continue
        projected = dict(zone_row)
        projected["bar_index"] = int(trow["trigger_bar_index"])
        projected["timestamp"] = trow["trigger_bar_end_timestamp"]
        projected["base_end_bar_index"] = int(trow["base_end_bar_index"])
        projected_rows.append(projected)

    if not projected_rows:
        return pd.DataFrame(columns=list(zones.columns))

    return pd.DataFrame(projected_rows).reset_index(drop=True)


def _check_touch(
    df: pd.DataFrame,
    zone: pd.Series,
    trigger_bar_idx: int,
    base_bar_idx: int,
    trigger_timeframe: str,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[trigger_bar_idx]
    if bar["low"] <= zone["zone_high"] and bar["high"] >= zone["zone_low"]:
        return _make_signal(
            signal_id=signal_id,
            ts=bar["base_end_timestamp"],
            bar_idx=base_bar_idx,
            trigger_bar_index=trigger_bar_idx,
            trigger_timeframe=trigger_timeframe,
            trigger_timestamp=bar["trigger_bar_end_timestamp"],
            trigger="touch",
            direction=direction,
            zone=zone,
            entry_ref=float(bar["close"]),
            entry_model="candidate_next_bar_open",
            status="candidate",
            naked_count=naked_count,
            naked_req=naked_req,
        )
    return None


def _check_reject(
    df: pd.DataFrame,
    zone: pd.Series,
    trigger_bar_idx: int,
    base_bar_idx: int,
    trigger_timeframe: str,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[trigger_bar_idx]
    touch = bar["low"] <= zone["zone_high"] and bar["high"] >= zone["zone_low"]
    if not touch:
        return None
    if direction == "long" and bar["close"] <= zone["zone_high"]:
        return None
    if direction == "short" and bar["close"] >= zone["zone_low"]:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["base_end_timestamp"],
        bar_idx=base_bar_idx,
        trigger_bar_index=trigger_bar_idx,
        trigger_timeframe=trigger_timeframe,
        trigger_timestamp=bar["trigger_bar_end_timestamp"],
        trigger="reject",
        direction=direction,
        zone=zone,
        entry_ref=float(bar["close"]),
        entry_model="candidate_next_bar_open",
        status="candidate",
        naked_count=naked_count,
        naked_req=naked_req,
    )


def _check_break(
    df: pd.DataFrame,
    zone: pd.Series,
    trigger_bar_idx: int,
    base_bar_idx: int,
    trigger_timeframe: str,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    if trigger_bar_idx == 0:
        return None
    bar = df.iloc[trigger_bar_idx]
    prev = df.iloc[trigger_bar_idx - 1]
    if direction == "long":
        ok = float(prev["close"]) <= zone["zone_high"] and float(bar["close"]) > zone["zone_high"]
    else:
        ok = float(prev["close"]) >= zone["zone_low"] and float(bar["close"]) < zone["zone_low"]
    if not ok:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["base_end_timestamp"],
        bar_idx=base_bar_idx,
        trigger_bar_index=trigger_bar_idx,
        trigger_timeframe=trigger_timeframe,
        trigger_timestamp=bar["trigger_bar_end_timestamp"],
        trigger="break",
        direction=direction,
        zone=zone,
        entry_ref=float(bar["close"]),
        entry_model="candidate_next_bar_open",
        status="candidate",
        naked_count=naked_count,
        naked_req=naked_req,
    )


def _check_reclaim(
    df: pd.DataFrame,
    zone: pd.Series,
    trigger_bar_idx: int,
    base_bar_idx: int,
    trigger_timeframe: str,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[trigger_bar_idx]
    if direction == "long":
        ok = float(bar["low"]) < zone["zone_low"] and float(bar["close"]) > zone["zone_high"]
    else:
        ok = float(bar["high"]) > zone["zone_high"] and float(bar["close"]) < zone["zone_low"]
    if not ok:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["base_end_timestamp"],
        bar_idx=base_bar_idx,
        trigger_bar_index=trigger_bar_idx,
        trigger_timeframe=trigger_timeframe,
        trigger_timestamp=bar["trigger_bar_end_timestamp"],
        trigger="reclaim",
        direction=direction,
        zone=zone,
        entry_ref=float(bar["close"]),
        entry_model="candidate_next_bar_open",
        status="candidate",
        naked_count=naked_count,
        naked_req=naked_req,
    )


def _check_confirm_3bar(
    df: pd.DataFrame,
    zone: pd.Series,
    bar1_idx: int,
    direction: str,
    signal_id_start: int,
    naked_count: int,
    naked_req: str,
    tick_size: float,
    params: dict,
) -> list[dict]:
    """Evaluate the confirm_3bar trigger starting from *bar1_idx*.

    Returns a list of zero or more signal dicts (one per qualifying
    direction).  The signal timestamp/bar_index corresponds to bar 3.
    """
    n = len(df)
    bar2_idx = bar1_idx + 1
    bar3_idx = bar1_idx + 2
    if bar3_idx >= n:
        return []

    arrival_tolerance_ticks = float(params.get("arrival_tolerance_ticks", 0))
    activation_retrace_ticks = float(
        params.get("activation_retrace_ticks", params.get("retrace_entry_ticks", 4))
    )
    entry_offset_ticks = float(params.get("entry_offset_ticks", 0))
    allow_equal = bool(params.get("allow_equal_close", False))
    activation_retrace = activation_retrace_ticks * tick_size
    entry_offset = entry_offset_ticks * tick_size

    bar1 = df.iloc[bar1_idx]
    bar2 = df.iloc[bar2_idx]
    bar3 = df.iloc[bar3_idx]

    directions = ["long", "short"] if direction == "both" else [direction]
    results: list[dict] = []
    sid = signal_id_start

    for d in directions:
        tested_level = _find_tested_level_for_arrival(
            df=df,
            zone=zone,
            bar1_idx=bar1_idx,
            direction=d,
            tick_size=tick_size,
            arrival_tolerance_ticks=arrival_tolerance_ticks,
        )
        if tested_level is None:
            continue
        tested_level_name, tested_level_price = tested_level

        # Bar 2 — reversal
        b2_close = float(bar2["close"])
        b1_close = float(bar1["close"])
        if d == "long":
            rev_ok = (b2_close >= b1_close) if allow_equal else (b2_close > b1_close)
            is_sfp_reversal = float(bar2["low"]) < float(bar1["low"]) and rev_ok
        else:
            rev_ok = (b2_close <= b1_close) if allow_equal else (b2_close < b1_close)
            is_sfp_reversal = float(bar2["high"]) > float(bar1["high"]) and rev_ok

        if not rev_ok:
            continue

        reversal_type = "sfp_reversal" if is_sfp_reversal else "standard_reversal"

        # Bar 3 — activation + stop-limit-style entry
        if d == "long":
            activation_price = float(bar3["open"]) - activation_retrace
            entry_price = float(bar3["open"]) + entry_offset
            activation_hit = float(bar3["low"]) <= activation_price
            entry_hit = float(bar3["high"]) >= entry_price
        else:
            activation_price = float(bar3["open"]) + activation_retrace
            entry_price = float(bar3["open"]) - entry_offset
            activation_hit = float(bar3["high"]) >= activation_price
            entry_hit = float(bar3["low"]) <= entry_price

        filled = activation_hit and entry_hit
        status = "filled" if filled else "void"
        entry_model = "bar3_stop_limit_fill" if filled else "bar3_stop_limit_void"
        entry_ref = entry_price
        notes_parts = [f"bar1={bar1_idx}", f"bar2={bar2_idx}", f"bar3={bar3_idx}"]
        if filled:
            notes_parts.append("bar3_sequence_assumed_from_ohlc")

        results.append(
            _make_signal(
                signal_id=sid,
                ts=bar3["timestamp"],
                bar_idx=bar3_idx,
                trigger="confirm_3bar",
                direction=d,
                zone=zone,
                entry_ref=entry_ref,
                entry_model=entry_model,
                status=status,
                naked_count=naked_count,
                naked_req=naked_req,
                notes=",".join(notes_parts),
                tested_level_name=tested_level_name,
                tested_level_price=tested_level_price,
                arrival_bar_index=bar1_idx,
                reversal_bar_index=bar2_idx,
                confirmation_bar_index=bar3_idx,
                reversal_type=reversal_type,
                is_sfp_reversal=is_sfp_reversal,
                activation_price=activation_price,
                entry_price=entry_price,
                activation_retrace_ticks=activation_retrace_ticks,
                entry_offset_ticks=entry_offset_ticks,
            )
        )
        sid += 1

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_signals(
    df: pd.DataFrame,
    zones: pd.DataFrame,
    trigger: str,
    direction: str,
    tick_size: float,
    trigger_timeframe: str = "base",
    trigger_params: dict | None = None,
    naked_only: bool = False,
    naked_flags: pd.DataFrame | None = None,
    naked_requirement: str = "any",
) -> pd.DataFrame:
    """Generate candidate entry signals from confluence zones.

    Parameters
    ----------
    df:
        Canonical OHLCV DataFrame (same row order used when building *zones*).
        Will be reset-index internally.
    zones:
        Output of :func:`~thesistester.engine.confluence.detect_confluence_zones`.
    trigger:
        One of ``touch``, ``reject``, ``break``, ``reclaim``, ``3c``.
    direction:
        ``long``, ``short``, or ``both``.
    tick_size:
        Instrument tick size.
    trigger_params:
        Optional dict of trigger-specific parameters.
    trigger_timeframe:
        Trigger evaluation timeframe for simple triggers.
    naked_only:
        When ``True`` only zones where at least one level (or all levels,
        depending on *naked_requirement*) is naked are processed.
    naked_flags:
        Output of :func:`~thesistester.engine.naked.flag_naked_levels`.
        Required when *naked_only* is ``True``; raises ``ValueError`` if
        missing.
    naked_requirement:
        ``"any"`` (default) — at least one level in the zone must be naked.
        ``"all"`` — every level in the zone must be naked.

    Returns
    -------
    pd.DataFrame
        One row per candidate signal with columns defined in
        :data:`_SIGNAL_COLUMNS`.  Returns an empty DataFrame with the
        correct schema when no signals are generated.

    Notes
    -----
    - Signals are **candidates only** in Phase 4; trade simulation (SL/TP,
      fills, P&L) is deferred to Phase 5.
    - For simple triggers (touch / reject / break / reclaim), ``timestamp``
      stays aligned to the canonical/base bar referenced by ``bar_index``.
      ``trigger_timestamp`` stores trigger-candle completion time.
    - For ``3c`` one resolved setup row is emitted (``filled``/``void``).
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"trigger must be one of {sorted(VALID_TRIGGERS)}, got {trigger!r}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(VALID_DIRECTIONS)}, got {direction!r}")
    if naked_only and naked_flags is None:
        raise ValueError("naked_flags must be provided when naked_only=True")
    if zones is None or zones.empty:
        return _empty_signals_df()

    params = _normalize_3c_params(trigger_params) if trigger == "3c" else {}
    requested_trigger_timeframe = normalize_trigger_timeframe(trigger_timeframe)
    if requested_trigger_timeframe not in VALID_TRIGGER_TIMEFRAMES:
        raise ValueError(
            f"trigger_timeframe must be one of {sorted(VALID_TRIGGER_TIMEFRAMES)}, got {trigger_timeframe!r}"
        )
    effective_trigger_timeframe = requested_trigger_timeframe
    naked_req = naked_requirement.lower()
    if naked_req not in {"any", "all"}:
        naked_req = "any"

    df_reset = df.reset_index(drop=True)
    trigger_df = _prepare_trigger_dataframe(df_reset, effective_trigger_timeframe)
    trigger_rows_by_base_end: dict[int, pd.Series] = {
        int(row["base_end_bar_index"]): row
        for _, row in trigger_df.iterrows()
    }
    signals: list[dict] = []
    signal_id = 0
    filtered_zones: list[tuple[pd.Series, int]] = []

    for _, zone in zones.iterrows():
        bar_idx = int(zone["bar_index"])
        if bar_idx >= len(df_reset):
            continue
        if trigger != "3c" and bar_idx not in trigger_rows_by_base_end:
            continue

        # Naked filter
        if naked_only:
            ncount = _naked_count(str(zone["level_names"]), bar_idx, naked_flags)
            n_levels = int(zone["level_count"])
            if naked_req == "all" and ncount < n_levels:
                continue
            if naked_req == "any" and ncount == 0:
                continue
        else:
            ncount = (
                _naked_count(str(zone["level_names"]), bar_idx, naked_flags)
                if naked_flags is not None
                else 0
            )
        filtered_zones.append((zone, ncount))

    if trigger == "3c":
        zones_for_candidates = pd.DataFrame([zone for zone, _ in filtered_zones])
        source_mode = str(params.get("_source_mode", "global_cluster"))

        if effective_trigger_timeframe == "base":
            # ── Existing base 3c path (unchanged) ────────────────────────────
            if source_mode == "anchor_rules":
                candidates = from_anchor_zones(zones_for_candidates, direction)
            else:
                candidates = from_global_cluster_zones(zones_for_candidates, direction)

            if naked_flags is not None:
                enriched: list[CandidateLevel] = []
                for candidate in candidates:
                    state = None
                    is_naked = None
                    if candidate.level_id:
                        naked_col = candidate.level_id + "_naked"
                        if naked_col in naked_flags.columns and 0 <= int(candidate.bar_index) < len(naked_flags):
                            is_naked = bool(naked_flags[naked_col].iloc[int(candidate.bar_index)])
                            state = "naked" if is_naked else "tested"
                    enriched.append(
                        with_metadata(
                            candidate,
                            was_naked_before_arrival=is_naked,
                            level_test_state_at_arrival=state,
                        )
                    )
                candidates = enriched

            setup_rows = detect_3c_setups(
                df=df_reset,
                candidates=candidates,
                tick_size=tick_size,
                trigger_params=params,
            )
            zone_by_id = {candidate.zone_id: candidate for candidate in candidates if candidate.zone_id}
            for setup in setup_rows:
                zone = None
                zone_id = setup.get("zone_id")
                arrival_naked_idx = (
                    _safe_signal_index(setup.get("arrival_bar_index"), len(naked_flags))
                    if naked_flags is not None
                    else None
                )
                if zone_id in zone_by_id:
                    candidate = zone_by_id[zone_id]
                    zone = pd.Series(
                        {
                            "zone_low": candidate.zone_low,
                            "zone_high": candidate.zone_high,
                            "zone_mid": (
                                (candidate.zone_low + candidate.zone_high) / 2.0
                                if candidate.zone_low is not None and candidate.zone_high is not None
                                else None
                            ),
                            "level_count": candidate.metadata.get("level_count", 1),
                            "level_names": "|".join(setup.get("level_ids", []))
                            if setup.get("level_ids")
                            else (candidate.level_id or candidate.source_label or ""),
                        }
                    )
                    ncount = (
                        _naked_count(str(zone["level_names"]), arrival_naked_idx, naked_flags)
                        if naked_flags is not None and arrival_naked_idx is not None
                        else 0
                    )
                else:
                    zone = pd.Series(
                        {
                            "zone_low": np.nan,
                            "zone_high": np.nan,
                            "zone_mid": np.nan,
                            "level_count": 0,
                            "level_names": "",
                        }
                    )
                    ncount = 0

                filled = str(setup["status"]) == "filled"
                is_sfp = bool(setup["is_sfp"])
                source_labels = "|".join(setup.get("source_labels", [])) if setup.get("source_labels") else None
                zone_ids = "|".join(setup.get("zone_ids", [])) if setup.get("zone_ids") else None
                level_ids = "|".join(setup.get("level_ids", [])) if setup.get("level_ids") else None
                tested_level_name = setup.get("level_id") or setup.get("level_source_label")
                tested_level_price = setup.get("arrival_level_price")
                entry_trigger_raw = setup.get("entry_trigger_price", setup.get("retrace_entry_price"))
                if entry_trigger_raw is None:
                    entry_trigger_raw = setup.get("arrival_level_price")
                entry_trigger_price = _safe_signal_float(entry_trigger_raw)
                if entry_trigger_price is None:
                    continue
                retrace_entry_price = entry_trigger_price if filled else None
                entry_bar_index = setup.get("entry_bar_index")
                bar_index_base = _safe_signal_index(setup.get("bar_index"), len(df_reset))
                arrival_idx_base = _safe_signal_index(setup.get("arrival_bar_index"), len(df_reset))
                reversal_idx_base = _safe_signal_index(setup.get("reversal_bar_index"), len(df_reset))
                entry_idx_base = (
                    _safe_signal_index(entry_bar_index, len(df_reset))
                    if entry_bar_index is not None
                    else None
                )
                arrival_level_price = _safe_signal_float(setup.get("arrival_level_price"))
                if (
                    bar_index_base is None
                    or arrival_idx_base is None
                    or reversal_idx_base is None
                    or (entry_bar_index is not None and entry_idx_base is None)
                    or arrival_level_price is None
                ):
                    continue
                signals.append(
                    _make_signal(
                        signal_id=signal_id,
                        ts=setup["timestamp"],
                        bar_idx=bar_index_base,
                        trigger_bar_index=reversal_idx_base,
                        trigger_timeframe=effective_trigger_timeframe,
                        trigger_timestamp=df_reset["timestamp"].iloc[reversal_idx_base],
                        trigger="3c",
                        direction=str(setup["direction"]),
                        zone=zone,
                        entry_ref=entry_trigger_price,
                        entry_model="3c_retrace_market" if filled else "3c_retrace_void",
                        status=str(setup["status"]),
                        naked_count=ncount,
                        naked_req=naked_req,
                        tested_level_name=tested_level_name,
                        tested_level_price=tested_level_price,
                        arrival_bar_index=arrival_idx_base,
                        reversal_bar_index=reversal_idx_base,
                        confirmation_bar_index=entry_idx_base,
                        reversal_type="sfp_reversal" if is_sfp else "standard_reversal",
                        is_sfp_reversal=is_sfp,
                        activation_price=entry_trigger_price if filled else None,
                        entry_price=entry_trigger_price if filled else None,
                        activation_retrace_ticks=float(setup["entry_retrace_ticks"]),
                        trigger_variant=str(setup["trigger_variant"]),
                        is_muted=bool(setup["is_muted"]),
                        is_sfp=is_sfp,
                        inside_candle_count=int(setup["inside_candle_count"]),
                        level_source_mode=str(setup["level_source_mode"]),
                        level_source_label=setup.get("level_source_label"),
                        zone_id=setup.get("zone_id"),
                        level_id=setup.get("level_id"),
                        arrival_level_price=arrival_level_price,
                        entry_bar_index=entry_idx_base,
                        entry_trigger_price=entry_trigger_price,
                        retrace_entry_price=retrace_entry_price,
                        retrace_ticks_required=float(setup["entry_retrace_ticks"]),
                        source_labels=source_labels,
                        source_count=int(setup.get("source_count", 1)),
                        zone_ids=zone_ids,
                        level_ids=level_ids,
                        level_test_state_at_arrival=setup.get("level_test_state_at_arrival"),
                        was_naked_before_arrival=setup.get("was_naked_before_arrival"),
                        # Base 3c: trigger indices match base indices
                        trigger_arrival_bar_index=arrival_idx_base,
                        trigger_reversal_bar_index=reversal_idx_base,
                    )
                )
                signal_id += 1

        else:
            # ── New non-base 3c path ──────────────────────────────────────────
            trigger_df_3c = _prepare_trigger_dataframe(df_reset, effective_trigger_timeframe)
            projected_zones = _project_zones_to_trigger_df(zones_for_candidates, trigger_df_3c)
            trigger_timeframe_delta = pd.to_timedelta(effective_trigger_timeframe)

            if source_mode == "anchor_rules":
                candidates = from_anchor_zones(projected_zones, direction)
            else:
                candidates = from_global_cluster_zones(projected_zones, direction)

            # For non-base 3c, naked metadata must use the base arrival index
            # (base_end_bar_index of the trigger arrival bar), not the trigger index.
            # We store base_end_bar_index from the projected zone in candidate metadata
            # so that detect_3c_setups_with_trigger_timeframe can use it.
            if naked_flags is not None:
                # Build a lookup: trigger_bar_index -> base_end_bar_index
                trigger_base_end_map: dict[int, int] = {
                    int(row["trigger_bar_index"]): int(row["base_end_bar_index"])
                    for _, row in trigger_df_3c.iterrows()
                }
                enriched_nb: list[CandidateLevel] = []
                for candidate in candidates:
                    state = None
                    is_naked = None
                    if candidate.level_id:
                        naked_col = candidate.level_id + "_naked"
                        # Use base arrival index for naked lookup
                        base_arr_idx = trigger_base_end_map.get(int(candidate.bar_index))
                        if (
                            base_arr_idx is not None
                            and naked_col in naked_flags.columns
                            and 0 <= base_arr_idx < len(naked_flags)
                        ):
                            is_naked = bool(naked_flags[naked_col].iloc[base_arr_idx])
                            state = "naked" if is_naked else "tested"
                    enriched_nb.append(
                        with_metadata(
                            candidate,
                            was_naked_before_arrival=is_naked,
                            level_test_state_at_arrival=state,
                        )
                    )
                candidates = enriched_nb

            setup_rows = detect_3c_setups_with_trigger_timeframe(
                trigger_df=trigger_df_3c,
                base_df=df_reset,
                candidates=candidates,
                tick_size=tick_size,
                trigger_params=params,
                trigger_timeframe_delta=trigger_timeframe_delta,
            )

            # Build zone lookup from candidates
            zone_by_id_nb = {candidate.zone_id: candidate for candidate in candidates if candidate.zone_id}
            for setup in setup_rows:
                zone_id = setup.get("zone_id")
                arrival_naked_idx = (
                    _safe_signal_index(setup.get("arrival_bar_index"), len(naked_flags))
                    if naked_flags is not None
                    else None
                )
                if zone_id in zone_by_id_nb:
                    candidate = zone_by_id_nb[zone_id]
                    zone = pd.Series(
                        {
                            "zone_low": candidate.zone_low,
                            "zone_high": candidate.zone_high,
                            "zone_mid": (
                                (candidate.zone_low + candidate.zone_high) / 2.0
                                if candidate.zone_low is not None and candidate.zone_high is not None
                                else None
                            ),
                            "level_count": candidate.metadata.get("level_count", 1),
                            "level_names": "|".join(setup.get("level_ids", []))
                            if setup.get("level_ids")
                            else (candidate.level_id or candidate.source_label or ""),
                        }
                    )
                    # Naked count uses base arrival index
                    ncount = (
                        _naked_count(str(zone["level_names"]), arrival_naked_idx, naked_flags)
                        if naked_flags is not None and arrival_naked_idx is not None
                        else 0
                    )
                else:
                    zone = pd.Series(
                        {
                            "zone_low": np.nan,
                            "zone_high": np.nan,
                            "zone_mid": np.nan,
                            "level_count": 0,
                            "level_names": "",
                        }
                    )
                    ncount = 0

                filled = str(setup["status"]) == "filled"
                is_sfp = bool(setup["is_sfp"])
                source_labels = "|".join(setup.get("source_labels", [])) if setup.get("source_labels") else None
                zone_ids = "|".join(setup.get("zone_ids", [])) if setup.get("zone_ids") else None
                level_ids = "|".join(setup.get("level_ids", [])) if setup.get("level_ids") else None
                tested_level_name = setup.get("level_id") or setup.get("level_source_label")
                tested_level_price = setup.get("arrival_level_price")
                entry_trigger_raw = setup.get("entry_trigger_price", setup.get("retrace_entry_price"))
                if entry_trigger_raw is None:
                    entry_trigger_raw = setup.get("arrival_level_price")
                entry_trigger_price = _safe_signal_float(entry_trigger_raw)
                if entry_trigger_price is None:
                    continue
                retrace_entry_price = entry_trigger_price if filled else None
                entry_bar_index = setup.get("entry_bar_index")
                trigger_reversal_bar_index = setup.get("trigger_reversal_bar_index")
                trigger_arrival_bar_index = setup.get("trigger_arrival_bar_index")
                # trigger_bar_index equals trigger_reversal_bar_index for 3c
                trigger_bar_index_3c = _safe_signal_index(trigger_reversal_bar_index, len(trigger_df_3c))
                bar_index_base = _safe_signal_index(setup.get("bar_index"), len(df_reset))
                arrival_idx_base = _safe_signal_index(setup.get("arrival_bar_index"), len(df_reset))
                reversal_idx_base = _safe_signal_index(setup.get("reversal_bar_index"), len(df_reset))
                entry_idx_base = (
                    _safe_signal_index(entry_bar_index, len(df_reset))
                    if entry_bar_index is not None
                    else None
                )
                trigger_arrival_idx = (
                    _safe_signal_index(trigger_arrival_bar_index, len(trigger_df_3c))
                    if trigger_arrival_bar_index is not None
                    else None
                )
                arrival_level_price = _safe_signal_float(setup.get("arrival_level_price"))
                if (
                    trigger_bar_index_3c is None
                    or bar_index_base is None
                    or arrival_idx_base is None
                    or reversal_idx_base is None
                    or (entry_bar_index is not None and entry_idx_base is None)
                    or arrival_level_price is None
                ):
                    continue
                signals.append(
                    _make_signal(
                        signal_id=signal_id,
                        ts=setup["timestamp"],
                        bar_idx=bar_index_base,
                        trigger_bar_index=trigger_bar_index_3c,
                        trigger_timeframe=effective_trigger_timeframe,
                        trigger_timestamp=setup.get("trigger_timestamp"),
                        trigger="3c",
                        direction=str(setup["direction"]),
                        zone=zone,
                        entry_ref=entry_trigger_price,
                        entry_model="3c_retrace_market" if filled else "3c_retrace_void",
                        status=str(setup["status"]),
                        naked_count=ncount,
                        naked_req=naked_req,
                        tested_level_name=tested_level_name,
                        tested_level_price=tested_level_price,
                        arrival_bar_index=arrival_idx_base,
                        reversal_bar_index=reversal_idx_base,
                        confirmation_bar_index=entry_idx_base,
                        reversal_type="sfp_reversal" if is_sfp else "standard_reversal",
                        is_sfp_reversal=is_sfp,
                        activation_price=entry_trigger_price if filled else None,
                        entry_price=entry_trigger_price if filled else None,
                        activation_retrace_ticks=float(setup["entry_retrace_ticks"]),
                        trigger_variant=str(setup["trigger_variant"]),
                        is_muted=bool(setup["is_muted"]),
                        is_sfp=is_sfp,
                        inside_candle_count=int(setup["inside_candle_count"]),
                        level_source_mode=str(setup["level_source_mode"]),
                        level_source_label=setup.get("level_source_label"),
                        zone_id=setup.get("zone_id"),
                        level_id=setup.get("level_id"),
                        arrival_level_price=arrival_level_price,
                        entry_bar_index=entry_idx_base,
                        entry_trigger_price=entry_trigger_price,
                        retrace_entry_price=retrace_entry_price,
                        retrace_ticks_required=float(setup["entry_retrace_ticks"]),
                        source_labels=source_labels,
                        source_count=int(setup.get("source_count", 1)),
                        zone_ids=zone_ids,
                        level_ids=level_ids,
                        level_test_state_at_arrival=setup.get("level_test_state_at_arrival"),
                        was_naked_before_arrival=setup.get("was_naked_before_arrival"),
                        trigger_arrival_bar_index=trigger_arrival_idx,
                        trigger_reversal_bar_index=trigger_bar_index_3c,
                    )
                )
                signal_id += 1
    else:
        directions = ["long", "short"] if direction == "both" else [direction]
        for zone, ncount in filtered_zones:
            bar_idx = int(zone["bar_index"])
            trigger_row = trigger_rows_by_base_end.get(bar_idx)
            if trigger_row is None:
                continue
            trigger_bar_idx = int(trigger_row["trigger_bar_index"])
            base_bar_idx = int(trigger_row["base_end_bar_index"])
            for d in directions:
                if trigger == "touch":
                    sig = _check_touch(
                        trigger_df,
                        zone,
                        trigger_bar_idx,
                        base_bar_idx,
                        effective_trigger_timeframe,
                        d,
                        signal_id,
                        ncount,
                        naked_req,
                    )
                elif trigger == "reject":
                    sig = _check_reject(
                        trigger_df,
                        zone,
                        trigger_bar_idx,
                        base_bar_idx,
                        effective_trigger_timeframe,
                        d,
                        signal_id,
                        ncount,
                        naked_req,
                    )
                elif trigger == "break":
                    sig = _check_break(
                        trigger_df,
                        zone,
                        trigger_bar_idx,
                        base_bar_idx,
                        effective_trigger_timeframe,
                        d,
                        signal_id,
                        ncount,
                        naked_req,
                    )
                elif trigger == "reclaim":
                    sig = _check_reclaim(
                        trigger_df,
                        zone,
                        trigger_bar_idx,
                        base_bar_idx,
                        effective_trigger_timeframe,
                        d,
                        signal_id,
                        ncount,
                        naked_req,
                    )
                else:
                    sig = None

                if sig is not None:
                    signals.append(sig)
                    signal_id += 1

    if not signals:
        return _empty_signals_df()
    return pd.DataFrame(signals)
