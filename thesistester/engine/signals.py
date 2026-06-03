"""Candidate signal generation from confluence zones and trigger logic."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


VALID_TRIGGERS = frozenset({"touch", "reject", "break", "reclaim", "confirm_3bar"})
VALID_DIRECTIONS = frozenset({"long", "short", "both"})

_DEFAULT_3BAR_PARAMS: dict = {
    "arrival_tolerance_ticks": 0,
    "retrace_entry_ticks": 4,
    "allow_equal_close": False,
}

_SIGNAL_COLUMNS: list[str] = [
    "signal_id",
    "timestamp",
    "bar_index",
    "trigger",
    "direction",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "entry_reference_price",
    "entry_model",
    "status",
    "naked_level_count",
    "naked_requirement",
    "notes",
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


def _make_signal(
    *,
    signal_id: int,
    ts: object,
    bar_idx: int,
    trigger: str,
    direction: str,
    zone: pd.Series,
    entry_ref: float,
    entry_model: str,
    status: str,
    naked_count: int,
    naked_req: str,
    notes: str = "",
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": ts,
        "bar_index": bar_idx,
        "trigger": trigger,
        "direction": direction,
        "zone_low": zone["zone_low"],
        "zone_high": zone["zone_high"],
        "zone_mid": zone["zone_mid"],
        "level_count": zone["level_count"],
        "level_names": zone["level_names"],
        "entry_reference_price": entry_ref,
        "entry_model": entry_model,
        "status": status,
        "naked_level_count": naked_count,
        "naked_requirement": naked_req,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Per-trigger helpers
# ---------------------------------------------------------------------------


def _check_touch(
    df: pd.DataFrame,
    zone: pd.Series,
    bar_idx: int,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[bar_idx]
    if bar["low"] <= zone["zone_high"] and bar["high"] >= zone["zone_low"]:
        return _make_signal(
            signal_id=signal_id,
            ts=bar["timestamp"],
            bar_idx=bar_idx,
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
    bar_idx: int,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[bar_idx]
    touch = bar["low"] <= zone["zone_high"] and bar["high"] >= zone["zone_low"]
    if not touch:
        return None
    if direction == "long" and bar["close"] > zone["zone_high"]:
        pass
    elif direction == "short" and bar["close"] < zone["zone_low"]:
        pass
    else:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["timestamp"],
        bar_idx=bar_idx,
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
    bar_idx: int,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    if bar_idx == 0:
        return None
    bar = df.iloc[bar_idx]
    prev = df.iloc[bar_idx - 1]
    if direction == "long":
        ok = float(prev["close"]) <= zone["zone_high"] and float(bar["close"]) > zone["zone_high"]
    else:
        ok = float(prev["close"]) >= zone["zone_low"] and float(bar["close"]) < zone["zone_low"]
    if not ok:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["timestamp"],
        bar_idx=bar_idx,
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
    bar_idx: int,
    direction: str,
    signal_id: int,
    naked_count: int,
    naked_req: str,
) -> dict | None:
    bar = df.iloc[bar_idx]
    if direction == "long":
        ok = float(bar["low"]) < zone["zone_low"] and float(bar["close"]) > zone["zone_high"]
    else:
        ok = float(bar["high"]) > zone["zone_high"] and float(bar["close"]) < zone["zone_low"]
    if not ok:
        return None
    return _make_signal(
        signal_id=signal_id,
        ts=bar["timestamp"],
        bar_idx=bar_idx,
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

    arrival_tol = float(params.get("arrival_tolerance_ticks", 0)) * tick_size
    retrace_ticks = float(params.get("retrace_entry_ticks", 4)) * tick_size
    allow_equal = bool(params.get("allow_equal_close", False))

    bar1 = df.iloc[bar1_idx]
    bar2 = df.iloc[bar2_idx]
    bar3 = df.iloc[bar3_idx]

    # Bar 1 — arrival condition (same for long and short)
    arrival_ok = (
        float(bar1["low"]) <= zone["zone_high"] + arrival_tol
        and float(bar1["high"]) >= zone["zone_low"] - arrival_tol
    )
    if not arrival_ok:
        return []

    directions = ["long", "short"] if direction == "both" else [direction]
    results: list[dict] = []
    sid = signal_id_start

    for d in directions:
        # Bar 2 — reversal
        if d == "long":
            rev_ok = (float(bar2["close"]) >= float(bar1["close"])) if allow_equal else (float(bar2["close"]) > float(bar1["close"]))
        else:
            rev_ok = (float(bar2["close"]) <= float(bar1["close"])) if allow_equal else (float(bar2["close"]) < float(bar1["close"]))

        if not rev_ok:
            continue

        # Bar 3 — retracement and limit fill
        if d == "long":
            entry_price = float(bar3["open"]) - retrace_ticks
            filled = float(bar3["low"]) <= entry_price
        else:
            entry_price = float(bar3["open"]) + retrace_ticks
            filled = float(bar3["high"]) >= entry_price

        status = "filled" if filled else "void"
        entry_model = "bar3_limit_fill" if filled else "bar3_limit_void"
        entry_ref = entry_price if filled else float(bar3["close"])

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
                notes=f"bar1={bar1_idx},bar2={bar2_idx},bar3={bar3_idx}",
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
        One of ``touch``, ``reject``, ``break``, ``reclaim``, ``confirm_3bar``.
    direction:
        ``long``, ``short``, or ``both``.
    tick_size:
        Instrument tick size.
    trigger_params:
        Optional dict of trigger-specific parameters.  For ``confirm_3bar``
        the supported keys are ``arrival_tolerance_ticks`` (default 0),
        ``retrace_entry_ticks`` (default 4), and ``allow_equal_close``
        (default ``False``).
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
    - For simple triggers (touch / reject / break / reclaim) the signal
      timestamp and bar_index correspond to the trigger bar.
    - For ``confirm_3bar`` the timestamp and bar_index correspond to bar 3
      (the retracement bar), because that is when the entry condition is
      evaluated.
    - ``confirm_3bar`` emits a row with ``status="void"`` when bar 3 does
      not fill the limit entry, to preserve the setup for later research.
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"trigger must be one of {sorted(VALID_TRIGGERS)}, got {trigger!r}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(VALID_DIRECTIONS)}, got {direction!r}")
    if naked_only and naked_flags is None:
        raise ValueError("naked_flags must be provided when naked_only=True")
    if zones is None or zones.empty:
        return _empty_signals_df()

    params = {**_DEFAULT_3BAR_PARAMS, **(trigger_params or {})}
    naked_req = naked_requirement.lower()
    if naked_req not in {"any", "all"}:
        naked_req = "any"

    df_reset = df.reset_index(drop=True)
    directions = ["long", "short"] if direction == "both" else [direction]

    signals: list[dict] = []
    signal_id = 0

    for _, zone in zones.iterrows():
        bar_idx = int(zone["bar_index"])
        if bar_idx >= len(df_reset):
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

        if trigger == "confirm_3bar":
            new_sigs = _check_confirm_3bar(
                df_reset, zone, bar_idx, direction,
                signal_id_start=signal_id,
                naked_count=ncount,
                naked_req=naked_req,
                tick_size=tick_size,
                params=params,
            )
            signals.extend(new_sigs)
            signal_id += len(new_sigs)
        else:
            for d in directions:
                if trigger == "touch":
                    sig = _check_touch(df_reset, zone, bar_idx, d, signal_id, ncount, naked_req)
                elif trigger == "reject":
                    sig = _check_reject(df_reset, zone, bar_idx, d, signal_id, ncount, naked_req)
                elif trigger == "break":
                    sig = _check_break(df_reset, zone, bar_idx, d, signal_id, ncount, naked_req)
                elif trigger == "reclaim":
                    sig = _check_reclaim(df_reset, zone, bar_idx, d, signal_id, ncount, naked_req)
                else:
                    sig = None

                if sig is not None:
                    signals.append(sig)
                    signal_id += 1

    if not signals:
        return _empty_signals_df()
    return pd.DataFrame(signals)
