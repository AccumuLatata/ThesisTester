"""Strict 3c detector over normalized candidate levels.

The detector emits one resolved row per setup:
- status="filled" when post-reversal retracement is touched
- status="void" when retracement is not touched within watch window
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .candidate_level import CandidateLevel


_DEFAULT_3C_PARAMS: dict[str, float | int] = {
    "arrival_tolerance_ticks": 0.0,
    "entry_retrace_ticks": 4.0,
    "max_entry_wait_bars_after_reversal": 5,
}


def _normalize_3c_params(params: dict | None) -> dict[str, float | int]:
    p = params or {}
    return {
        "arrival_tolerance_ticks": float(p.get("arrival_tolerance_ticks", _DEFAULT_3C_PARAMS["arrival_tolerance_ticks"])),
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


def detect_3c_setups(
    df: pd.DataFrame,
    candidates: list[CandidateLevel],
    tick_size: float,
    trigger_params: dict | None = None,
) -> list[dict[str, Any]]:
    if df is None or df.empty or not candidates:
        return []

    params = _normalize_3c_params(trigger_params)
    arrival_tol = float(params["arrival_tolerance_ticks"]) * float(tick_size)
    retrace_dist = float(params["entry_retrace_ticks"]) * float(tick_size)
    max_wait = max(int(params["max_entry_wait_bars_after_reversal"]), 0)

    df_reset = df.reset_index(drop=True)
    n = len(df_reset)
    raw: list[dict[str, Any]] = []

    for candidate in candidates:
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
            if direction == "long":
                arrival_ok = bar1_low <= level_price + arrival_tol and bar1_close > level_price
            else:
                arrival_ok = float(bar1["high"]) >= level_price - arrival_tol and bar1_close < level_price
            if not arrival_ok:
                continue

            inside_count = 0
            reversal_idx: int | None = None
            reversal_close: float | None = None
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
                break

            if reversal_idx is None or reversal_close is None:
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
