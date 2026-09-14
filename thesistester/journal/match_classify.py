"""TJ8 classify → match-table helpers (C-25 / QI-08-04).

Pairing and class tokens are unchanged (``executed_cell`` / ``near_level`` /
``product_mismatch`` / ``discretionary_only`` / ``systematic_unfilled``).
``load_named_cell`` and hash verify stay on ``match.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from thesistester.journal.schema import (
    DEFAULT_JOURNAL_RISK_TICKS,
    MATCH_DISCRETIONARY_ONLY,
    MATCH_EXECUTED_CELL,
    MATCH_NEAR_LEVEL,
    MATCH_OUTPUT_COLUMNS,
    MATCH_PRODUCT_MISMATCH,
    MATCH_RISK_TOLERANCE_RATIO,
    MATCH_SIDE_JOURNAL,
    MATCH_SIDE_SYSTEMATIC,
    MATCH_SYSTEMATIC_UNFILLED,
    MISMATCH_HOLD,
    MISMATCH_RISK,
    MISMATCH_TRIGGER,
)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _journal_risk_ticks(raw: Mapping[str, object]) -> float:
    risk = _optional_float(raw.get("journal_risk_ticks"))
    if risk is None:
        return float(DEFAULT_JOURNAL_RISK_TICKS)
    return risk


def _product_failing(
    journal_row: Mapping[str, object],
    sys_row: Mapping[str, object],
    *,
    stop_loss_ticks: float,
    bar_seconds: float,
) -> list[str]:
    failing: list[str] = []
    hold = _optional_float(journal_row.get("hold_seconds"))
    bars = _optional_float(sys_row.get("bars_held"))
    if hold is None or bars is None or bars <= 0:
        failing.append(MISMATCH_HOLD)
    else:
        lo = max(0.0, (bars - 1.0) * bar_seconds)
        hi = bars * bar_seconds
        if not (lo <= hold <= hi):
            failing.append(MISMATCH_HOLD)
    risk = _optional_float(journal_row.get("journal_risk_ticks"))
    if risk is None:
        risk = float(DEFAULT_JOURNAL_RISK_TICKS)
    sl = _optional_float(sys_row.get("stop_loss_ticks")) or stop_loss_ticks
    lo_r = sl * (1.0 - MATCH_RISK_TOLERANCE_RATIO)
    hi_r = sl * (1.0 + MATCH_RISK_TOLERANCE_RATIO)
    if not (lo_r <= risk <= hi_r):
        failing.append(MISMATCH_RISK)
    journal_trigger = _as_optional_str(journal_row.get("trigger"))
    sys_trigger = _as_optional_str(sys_row.get("trigger"))
    if journal_trigger is not None and sys_trigger is not None and journal_trigger != sys_trigger:
        failing.append(MISMATCH_TRIGGER)
    return failing


def _price_distance_ticks(price: float, sys_row: Mapping[str, object], tick: float) -> float:
    distances: list[float] = []
    for key in ("theoretical_entry_price", "entry_price", "zone_mid"):
        value = _optional_float(sys_row.get(key))
        if value is not None:
            distances.append(abs(price - value) / tick)
    low = _optional_float(sys_row.get("zone_low"))
    high = _optional_float(sys_row.get("zone_high"))
    if low is not None and high is not None:
        if low <= price <= high:
            distances.append(0.0)
        else:
            distances.append(min(abs(price - low), abs(price - high)) / tick)
    return min(distances) if distances else math.inf


def _nearest_level(
    journal_row: Mapping[str, object],
    systematic: list[dict[str, object]],
    signals: list[dict[str, object]],
    *,
    match_ticks: float,
    tick: float,
) -> tuple[str | None, float, float, object] | None:
    """Same-session price neighbor. Cross-session zones are not ``near_level``."""
    session = journal_row["session_date"]
    direction = str(journal_row["direction"])
    price = float(journal_row["entry_price"])
    entry = journal_row["entry_timestamp"]
    best: tuple[float, float, str | None, object] | None = None
    for raw in systematic + signals:
        if str(raw.get("direction") or "") != direction:
            continue
        if raw.get("session_date") != session:
            continue
        delta_t = _price_distance_ticks(price, raw, tick)
        if delta_t > match_ticks:
            continue
        raw_entry = raw.get("entry_timestamp")
        if not isinstance(raw_entry, pd.Timestamp):
            continue
        delta_s = abs((entry - raw_entry).total_seconds())
        counterpart = _as_optional_str(raw.get("trade_id")) or _as_optional_str(
            raw.get("signal_id")
        )
        candidate = (delta_t, delta_s, counterpart, raw.get("bars_held"))
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None
    return best[2], best[1], best[0], best[3]


def _journal_match_row(
    raw: Mapping[str, object],
    *,
    cell_id: str,
    match_class: str,
    dimension: str | None,
    counterpart_id: str | None,
    delta_s: float | None,
    delta_t: float | None,
    sl: float,
    bars_held: object,
) -> dict[str, object]:
    return {
        "side": MATCH_SIDE_JOURNAL,
        "trade_id": str(raw["trade_id"]),
        "signal_id": None,
        "session_date": raw["session_date"],
        "match_class": match_class,
        "product_mismatch_dimension": dimension,
        "cell_id": cell_id,
        "counterpart_id": counterpart_id,
        "delta_entry_seconds": delta_s,
        "delta_entry_ticks": delta_t,
        "instrument": str(raw["instrument"]),
        "direction": str(raw["direction"]),
        "net_ticks": _optional_float(raw.get("net_ticks")),
        "hold_seconds": _optional_float(raw.get("hold_seconds")),
        "journal_risk_ticks": _journal_risk_ticks(raw),
        "cell_stop_loss_ticks": sl,
        "cell_bars_held": _optional_float(bars_held),
    }


def _systematic_unfilled_row(
    raw: Mapping[str, object], *, cell_id: str, sl: float
) -> dict[str, object]:
    trade_id = raw.get("trade_id") or raw.get("signal_id") or "systematic"
    return {
        "side": MATCH_SIDE_SYSTEMATIC,
        "trade_id": str(trade_id),
        "signal_id": _as_optional_str(raw.get("signal_id")),
        "session_date": raw["session_date"],
        "match_class": MATCH_SYSTEMATIC_UNFILLED,
        "product_mismatch_dimension": None,
        "cell_id": cell_id,
        "counterpart_id": None,
        "delta_entry_seconds": None,
        "delta_entry_ticks": None,
        "instrument": str(raw.get("instrument") or ""),
        "direction": str(raw.get("direction") or ""),
        "net_ticks": None,
        "hold_seconds": None,
        "journal_risk_ticks": None,
        "cell_stop_loss_ticks": sl,
        "cell_bars_held": _optional_float(raw.get("bars_held")),
    }


def _match_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(MATCH_OUTPUT_COLUMNS))
    frame = pd.DataFrame(rows)
    keep = [column for column in MATCH_OUTPUT_COLUMNS if column in frame.columns]
    out = frame.loc[:, keep]
    for column in (
        "product_mismatch_dimension",
        "counterpart_id",
        "delta_entry_seconds",
        "delta_entry_ticks",
        "net_ticks",
        "hold_seconds",
        "journal_risk_ticks",
        "cell_bars_held",
        "signal_id",
    ):
        if column in out.columns:
            out[column] = pd.Series([row.get(column) for row in rows], dtype="object")
    return out


def _classify(
    journal: pd.DataFrame,
    systematic: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    cell_id: str,
    instrument: str,
    stop_loss_ticks: float,
    bar_seconds: float,
    window: float,
    match_ticks: float,
    tick: float,
) -> list[dict[str, object]]:
    journal_rows = journal.to_dict(orient="records")
    sys_rows = systematic.to_dict(orient="records")
    candidates: list[tuple[float, float, int, int]] = []
    for j_idx, journal_row in enumerate(journal_rows):
        if str(journal_row["instrument"]) != instrument:
            continue
        for s_idx, sys_row in enumerate(sys_rows):
            if str(sys_row["direction"]) != str(journal_row["direction"]):
                continue
            delta_s = abs(
                (journal_row["entry_timestamp"] - sys_row["entry_timestamp"]).total_seconds()
            )
            if delta_s > window:
                continue
            delta_t = _price_distance_ticks(float(journal_row["entry_price"]), sys_row, tick)
            if delta_t > match_ticks:
                continue
            candidates.append((delta_s, delta_t, j_idx, s_idx))
    candidates.sort()
    used_j: set[int] = set()
    used_s: set[int] = set()
    pairs: list[tuple[int, int, float, float]] = []
    for delta_s, delta_t, j_idx, s_idx in candidates:
        if j_idx in used_j or s_idx in used_s:
            continue
        used_j.add(j_idx)
        used_s.add(s_idx)
        pairs.append((j_idx, s_idx, delta_s, delta_t))

    paired_signal_ids: set[str] = set()
    paired_sys_ids: set[str] = set()
    rows: list[dict[str, object]] = []
    for j_idx, s_idx, delta_s, delta_t in pairs:
        journal_row = journal_rows[j_idx]
        sys_row = sys_rows[s_idx]
        failing = _product_failing(
            journal_row,
            sys_row,
            stop_loss_ticks=stop_loss_ticks,
            bar_seconds=bar_seconds,
        )
        if failing:
            klass = MATCH_PRODUCT_MISMATCH
            dimension = ",".join(failing)
        else:
            klass = MATCH_EXECUTED_CELL
            dimension = None
        sid = _as_optional_str(sys_row.get("signal_id"))
        if sid is not None:
            paired_signal_ids.add(sid)
        paired_sys_ids.add(str(sys_row["trade_id"]))
        rows.append(
            _journal_match_row(
                journal_row,
                cell_id=cell_id,
                match_class=klass,
                dimension=dimension,
                counterpart_id=str(sys_row["trade_id"]),
                delta_s=delta_s,
                delta_t=delta_t,
                sl=stop_loss_ticks,
                bars_held=sys_row.get("bars_held"),
            )
        )

    signal_rows = signals.to_dict(orient="records") if not signals.empty else []
    for j_idx, journal_row in enumerate(journal_rows):
        if j_idx in used_j:
            continue
        nearest = (
            _nearest_level(
                journal_row,
                sys_rows,
                signal_rows,
                match_ticks=match_ticks,
                tick=tick,
            )
            if str(journal_row["instrument"]) == instrument
            else None
        )
        if nearest is not None:
            counterpart_id, near_s, near_t, bars_held = nearest
            klass = MATCH_NEAR_LEVEL
        else:
            counterpart_id = None
            near_s = None
            near_t = None
            bars_held = None
            klass = MATCH_DISCRETIONARY_ONLY
        rows.append(
            _journal_match_row(
                journal_row,
                cell_id=cell_id,
                match_class=klass,
                dimension=None,
                counterpart_id=counterpart_id,
                delta_s=near_s,
                delta_t=near_t,
                sl=stop_loss_ticks,
                bars_held=bars_held,
            )
        )

    if signal_rows:
        for raw in signal_rows:
            sid = _as_optional_str(raw.get("signal_id"))
            if sid is not None and sid in paired_signal_ids:
                continue
            rows.append(_systematic_unfilled_row(raw, cell_id=cell_id, sl=stop_loss_ticks))
    else:
        for raw in sys_rows:
            if str(raw["trade_id"]) in paired_sys_ids:
                continue
            rows.append(_systematic_unfilled_row(raw, cell_id=cell_id, sl=stop_loss_ticks))
    return rows
