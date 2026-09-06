"""Own-entry counterfactuals (TJ7): bracket replay, direction-shuffle, rules.

Walks already-loaded 15s bars / Last prints. Does not call ``simulate_trades``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from numbers import Integral, Real
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import yaml

from thesistester.journal.rules import JournalRule, apply_journal_rules, load_journal_rules
from thesistester.journal.schema import (
    CF_EXIT_SESSION_END,
    CF_EXIT_SL,
    CF_EXIT_TIME_STOP,
    CF_EXIT_TP,
    CF_EXIT_UNRESOLVED,
    CF_HONESTY,
    COUNTERFACTUAL_OUTPUT_COLUMNS,
    DEFAULT_CF_BRACKETS,
    DEFAULT_CF_K,
    DEFAULT_CF_SEED,
    ENTRY_EDGE_MIN_N,
    JOIN_BAR_SECONDS,
    JOIN_RESOLUTION_15S,
    JOIN_RESOLUTION_TICK,
    JOIN_RESOLUTIONS,
    JOURNAL_ETH_START,
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_POINT_VALUE,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    RECON_RECONCILED,
    JournalIngestError,
)

_BAR_DELTA = pd.Timedelta(seconds=JOIN_BAR_SECONDS)
_VALID_15S = frozenset({0, 15, 30, 45})
_OHLC = ("open", "high", "low", "close")


def replay_journal_brackets(
    trades: pd.DataFrame,
    *,
    bars: pd.DataFrame,
    ticks: pd.DataFrame | None = None,
    brackets: Sequence[tuple[int, int, int | None]] = DEFAULT_CF_BRACKETS,
    resolution: str = JOIN_RESOLUTION_15S,
    allow_unreconciled: bool = False,
    tick_size: float = JOURNAL_TICK_SIZE,
) -> pd.DataFrame:
    """Replay each trade under declared ``(sl_ticks, tp_ticks, max_hold)`` brackets.

    ``bars``, ``ticks``, ``brackets``, ``resolution``, ``allow_unreconciled``,
    and ``tick_size`` are keyword-only. 15s walks start at the next 15s open.
    Same-bar both-hit on later bars is SL-first. Tick walks use Last prints
    with ``ts > entry_timestamp``.
    """
    if resolution not in JOIN_RESOLUTIONS:
        raise JournalIngestError(
            f"resolution must be one of {sorted(JOIN_RESOLUTIONS)} (got {resolution!r})"
        )
    parsed = _parse_brackets(brackets)
    tick = _as_positive_tick(tick_size)
    work = _coerce_trades(trades)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    if work.empty:
        return pd.DataFrame(columns=list(COUNTERFACTUAL_OUTPUT_COLUMNS))
    bars_15s = _normalize_bars(bars)
    tick_frame = _normalize_ticks(ticks) if resolution == JOIN_RESOLUTION_TICK else None
    rows: list[dict[str, object]] = []
    for raw in work.to_dict(orient="records"):
        for sl_ticks, tp_ticks, max_hold in parsed:
            rows.append(
                _replay_one(
                    raw,
                    bars=bars_15s,
                    ticks=tick_frame,
                    sl_ticks=sl_ticks,
                    tp_ticks=tp_ticks,
                    max_hold=max_hold,
                    resolution=resolution,
                    tick=tick,
                )
            )
    return _cf_frame(rows)


def direction_shuffle_null(
    trades: pd.DataFrame,
    *,
    seed: int = DEFAULT_CF_SEED,
    k: int = DEFAULT_CF_K,
    allow_unreconciled: bool = False,
    tick_size: float = JOURNAL_TICK_SIZE,
) -> dict[str, object]:
    """Permute per-session direction labels; report realized Σgross percentile.

    ``seed``, ``k``, ``allow_unreconciled``, and ``tick_size`` are keyword-only.
    The only RNG in TJ7. Shuffle preserves each ``session_date`` long/short
    count. Does not resample 50/50.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise JournalIngestError(f"seed must be an int (got {seed!r})")
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise JournalIngestError(f"k must be a positive int (got {k!r})")
    tick = _as_positive_tick(tick_size)
    work = _coerce_trades(trades)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    if "exit_price" not in work.columns:
        raise JournalIngestError("direction shuffle requires exit_price")
    records = [row for row in work.to_dict(orient="records") if _has_exit(row)]
    if not records:
        return {
            "seed": seed,
            "k": k,
            "n": 0,
            "realized_gross_ticks": 0.0,
            "direction_null_pct": float("nan"),
        }
    realized = sum(_gross_ticks(row, direction=str(row["direction"]), tick=tick) for row in records)
    groups = _group_indices(records)
    rng = np.random.RandomState(seed)
    nulls = np.empty(k, dtype=float)
    for draw in range(k):
        assigned = _shuffle_directions(records, groups, rng)
        nulls[draw] = sum(
            _gross_ticks(row, direction=assigned[index], tick=tick)
            for index, row in enumerate(records)
        )
    less = float(np.sum(nulls < realized))
    equal = float(np.sum(nulls == realized))
    pct = 100.0 * (less + 0.5 * equal) / k if k else float("nan")
    return {
        "seed": seed,
        "k": k,
        "n": len(records),
        "realized_gross_ticks": float(realized),
        "direction_null_pct": float(pct),
    }


def summarize_bracket_replay(frame: pd.DataFrame, trades: pd.DataFrame) -> dict[str, object]:
    """Per-bracket exit-rule delta and per-resolution entry-edge flag."""
    net_by_id = {}
    if "trade_id" in trades.columns and "net_ticks" in trades.columns:
        for raw in trades.to_dict(orient="records"):
            net = _optional_float(raw.get("net_ticks"))
            if net is not None:
                net_by_id[str(raw["trade_id"])] = net
    by_bracket: dict[str, dict[str, object]] = {}
    trades_by_resolution: dict[str, set[str]] = {}
    resolved_by_resolution: dict[str, set[str]] = {}
    if frame.empty:
        return {
            "brackets": {},
            "entry_edge_flag": {},
            "caption": "three brackets were looked at (not a single pre-registered test)",
        }
    for raw in frame.to_dict(orient="records"):
        cf_id = str(raw["cf_id"])
        resolution = str(raw["resolution"])
        trade_id = str(raw["trade_id"])
        cf_net = _optional_float(raw.get("cf_net_ticks"))
        key = f"{cf_id}@{resolution}"
        bucket = by_bracket.setdefault(
            key,
            {
                "cf_id": cf_id,
                "sl_ticks": raw["sl_ticks"],
                "tp_ticks": raw["tp_ticks"],
                "max_hold_seconds": raw["max_hold_seconds"],
                "resolution": resolution,
                "n": 0,
                "n_resolved": 0,
                "sum_cf_net_ticks": 0.0,
                "sum_paired_cf_net_ticks": 0.0,
                "sum_net_ticks": 0.0,
                "paired": 0,
            },
        )
        bucket["n"] = int(bucket["n"]) + 1
        trades_by_resolution.setdefault(resolution, set()).add(trade_id)
        if cf_net is None:
            continue
        bucket["n_resolved"] = int(bucket["n_resolved"]) + 1
        bucket["sum_cf_net_ticks"] = float(bucket["sum_cf_net_ticks"]) + cf_net
        resolved_by_resolution.setdefault(resolution, set()).add(trade_id)
        realized = net_by_id.get(trade_id)
        if realized is None:
            continue
        # Same-entry pair only: open / unresolved rows do not move the delta.
        bucket["sum_paired_cf_net_ticks"] = float(bucket["sum_paired_cf_net_ticks"]) + cf_net
        bucket["sum_net_ticks"] = float(bucket["sum_net_ticks"]) + realized
        bucket["paired"] = int(bucket["paired"]) + 1
    for bucket in by_bracket.values():
        n_resolved = int(bucket["n_resolved"])
        bucket["exit_rule_delta"] = float(bucket["sum_paired_cf_net_ticks"]) - float(
            bucket["sum_net_ticks"]
        )
        bucket["mean_cf_net_ticks"] = (
            (float(bucket["sum_cf_net_ticks"]) / n_resolved) if n_resolved else None
        )
    flags: dict[str, object] = {}
    for resolution, trade_ids in trades_by_resolution.items():
        means = [
            float(bucket["mean_cf_net_ticks"])
            for bucket in by_bracket.values()
            if bucket["resolution"] == resolution
            and bucket["mean_cf_net_ticks"] is not None
            and int(bucket["n_resolved"]) >= ENTRY_EDGE_MIN_N
        ]
        best = max(means) if means else None
        flags[resolution] = {
            "n": len(trade_ids),
            "n_resolved": len(resolved_by_resolution.get(resolution, set())),
            "best_mean_cf_net_ticks": best,
            "entry_edge_flag": bool(best is not None and best > 0),
        }
    n_brackets = len({str(bucket["cf_id"]) for bucket in by_bracket.values()})
    if n_brackets == 3:
        caption = "three brackets were looked at (not a single pre-registered test)"
    else:
        caption = f"{n_brackets} brackets were looked at (not a single pre-registered test)"
    return {
        "brackets": by_bracket,
        "entry_edge_flag": flags,
        "caption": caption,
    }


def write_counterfactual_artifacts(
    output_dir: str | Path,
    frame: pd.DataFrame,
    *,
    seed: int,
    k: int,
    resolution: str,
    null: Mapping[str, object],
    brackets_summary: Mapping[str, object],
    rules_summary: Sequence[Mapping[str, object]] = (),
) -> dict[str, Path]:
    """Write ``journal_counterfactuals.parquet`` + ``counterfactual.json``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / "journal_counterfactuals.parquet"
    json_path = out / "counterfactual.json"
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "resolution": resolution,
        "seed": int(seed),
        "k": int(k),
        "honesty": CF_HONESTY,
        "null": dict(null),
        "brackets": brackets_summary,
        "rules": [dict(row) for row in rules_summary],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    frame.to_parquet(parquet_path, index=False)
    return {
        "journal_counterfactuals.parquet": parquet_path,
        "counterfactual.json": json_path,
    }


def counterfactual_files(
    *,
    trades: str | Path,
    bars: str | Path,
    output_dir: str | Path,
    ticks: str | Path | None = None,
    brackets: str | Path | Sequence[object] | None = None,
    rules: str | Path | None = None,
    resolution: str = JOIN_RESOLUTION_15S,
    seed: int = DEFAULT_CF_SEED,
    k: int = DEFAULT_CF_K,
    allow_unreconciled: bool = False,
) -> dict[str, Path]:
    """Load artifacts, run TJ7, and write journal/v1 outputs."""
    trade_frame = _load_table(trades, name="trades")
    bar_frame = _load_table(bars, name="bars")
    tick_frame = _load_table(ticks, name="ticks") if ticks is not None else None
    parsed_brackets = _load_brackets(brackets)
    replayed = replay_journal_brackets(
        trade_frame,
        bars=bar_frame,
        ticks=tick_frame,
        brackets=parsed_brackets,
        resolution=resolution,
        allow_unreconciled=allow_unreconciled,
    )
    null = direction_shuffle_null(
        trade_frame, seed=seed, k=k, allow_unreconciled=allow_unreconciled
    )
    summary = summarize_bracket_replay(replayed, trade_frame)
    rule_rows: tuple[dict[str, object], ...] = ()
    if rules is not None:
        loaded = load_journal_rules(rules)
        hard_stops = _hard_stop_map(
            trade_frame,
            bars=bar_frame,
            ticks=tick_frame if resolution == JOIN_RESOLUTION_TICK else None,
            rules=loaded,
            resolution=resolution,
            allow_unreconciled=allow_unreconciled,
        )
        rule_rows = apply_journal_rules(
            trade_frame,
            loaded,
            hard_stop_exits=hard_stops,
            allow_unreconciled=allow_unreconciled,
        )
    return write_counterfactual_artifacts(
        output_dir,
        replayed,
        seed=seed,
        k=k,
        resolution=resolution,
        null=null,
        brackets_summary=summary,
        rules_summary=rule_rows,
    )


def sl_hit_for_trade(
    raw: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    ticks: pd.DataFrame | None,
    sl_ticks: float,
    resolution: str,
    tick: float = JOURNAL_TICK_SIZE,
) -> tuple[float, pd.Timestamp] | None:
    """SL-only walk used by ``hard_stop_ticks``. ``None`` when SL never hits."""
    sl = _as_positive_number(sl_ticks, "sl_ticks")
    result = _replay_one(
        raw,
        bars=bars,
        ticks=ticks,
        sl_ticks=sl,
        tp_ticks=10**9,
        max_hold=None,
        resolution=resolution,
        tick=tick,
    )
    if result["cf_exit_reason"] != CF_EXIT_SL:
        return None
    price = result["cf_exit_price"]
    if price is None:
        return None
    return float(price), pd.Timestamp(result["cf_exit_ts"])


def _hard_stop_map(
    trades: pd.DataFrame,
    *,
    bars: pd.DataFrame,
    ticks: pd.DataFrame | None,
    rules: Sequence[JournalRule],
    resolution: str,
    allow_unreconciled: bool,
) -> dict[tuple[str, float], tuple[float, pd.Timestamp]]:
    stops = {rule.hard_stop_ticks for rule in rules if rule.hard_stop_ticks is not None}
    if not stops:
        return {}
    work = _coerce_trades(trades)
    _assert_reconciled(work, allow_unreconciled=allow_unreconciled)
    bars_15s = _normalize_bars(bars)
    tick_frame = _normalize_ticks(ticks) if ticks is not None else None
    found: dict[tuple[str, float], tuple[float, pd.Timestamp]] = {}
    for raw in work.to_dict(orient="records"):
        for sl_ticks in stops:
            hit = sl_hit_for_trade(
                raw, bars=bars_15s, ticks=tick_frame, sl_ticks=sl_ticks, resolution=resolution
            )
            if hit is not None:
                found[(str(raw["trade_id"]), float(sl_ticks))] = hit
    return found


def _replay_one(
    raw: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    ticks: pd.DataFrame | None,
    sl_ticks: int | float,
    tp_ticks: int | float,
    max_hold: int | None,
    resolution: str,
    tick: float,
) -> dict[str, object]:
    entry_ts = _as_utc(raw["entry_timestamp"])
    entry_price = float(raw["entry_price"])
    direction = _as_direction(raw["direction"])
    sl_price, tp_price = _bracket_prices(direction, entry_price, sl_ticks, tp_ticks, tick)
    session_end = _session_end_utc(raw["session_date"])
    hold_deadline = entry_ts + pd.Timedelta(seconds=max_hold) if max_hold is not None else None
    if resolution == JOIN_RESOLUTION_TICK:
        reason, exit_price, exit_ts = _walk_ticks(
            ticks if ticks is not None else pd.DataFrame(),
            entry_ts=entry_ts,
            direction=direction,
            sl_price=sl_price,
            tp_price=tp_price,
            session_end=session_end,
            hold_deadline=hold_deadline,
        )
    else:
        reason, exit_price, exit_ts = _walk_15s(
            bars,
            entry_ts=entry_ts,
            direction=direction,
            sl_price=sl_price,
            tp_price=tp_price,
            session_end=session_end,
            hold_deadline=hold_deadline,
        )
    qty = int(raw["qty"])
    instrument = _as_instrument(raw["instrument"])
    point_value = JOURNAL_POINT_VALUE[instrument]
    tick_value = tick * point_value
    if exit_price is None:
        gross = None
        net = None
    else:
        points = _signed_points(direction, entry_price, exit_price)
        gross = points * qty / tick
        net = gross - _cost_ticks(raw, tick_value)
    return {
        "trade_id": str(raw["trade_id"]),
        "cf_id": _cf_id(sl_ticks, tp_ticks, max_hold),
        "resolution": resolution,
        "sl_ticks": sl_ticks,
        "tp_ticks": tp_ticks,
        "max_hold_seconds": max_hold,
        "cf_exit_price": exit_price,
        "cf_exit_reason": reason,
        "cf_exit_ts": exit_ts,
        "cf_gross_ticks": gross,
        "cf_net_ticks": net,
    }


def _walk_15s(
    bars: pd.DataFrame,
    *,
    entry_ts: pd.Timestamp,
    direction: str,
    sl_price: float,
    tp_price: float,
    session_end: pd.Timestamp,
    hold_deadline: pd.Timestamp | None,
) -> tuple[str, float | None, pd.Timestamp | None]:
    start = _next_15s_open(entry_ts)
    if hold_deadline is not None and start >= hold_deadline:
        return CF_EXIT_TIME_STOP, None, hold_deadline
    if start >= session_end:
        return CF_EXIT_SESSION_END, None, session_end
    walkable = bars.loc[(bars["timestamp"] >= start) & (bars["timestamp"] < session_end)]
    last_close: float | None = None
    last_ts: pd.Timestamp | None = None
    for raw in walkable.to_dict(orient="records"):
        open_ts = raw["timestamp"]
        if hold_deadline is not None and open_ts >= hold_deadline:
            if last_close is not None:
                return CF_EXIT_TIME_STOP, last_close, last_ts
            return CF_EXIT_TIME_STOP, None, hold_deadline
        sl_hit, tp_hit = _bar_hits(direction, raw, sl_price, tp_price)
        if sl_hit and tp_hit:
            return CF_EXIT_SL, sl_price, open_ts
        if sl_hit:
            return CF_EXIT_SL, sl_price, open_ts
        if tp_hit:
            return CF_EXIT_TP, tp_price, open_ts
        last_close = float(raw["close"])
        last_ts = open_ts + _BAR_DELTA
    if last_close is not None:
        data_end = walkable["timestamp"].iloc[-1] + _BAR_DELTA
        if _reached_this_session_end(data_end, session_end):
            return CF_EXIT_SESSION_END, last_close, session_end
        return CF_EXIT_UNRESOLVED, None, None
    return CF_EXIT_UNRESOLVED, None, None


def _walk_ticks(
    ticks: pd.DataFrame,
    *,
    entry_ts: pd.Timestamp,
    direction: str,
    sl_price: float,
    tp_price: float,
    session_end: pd.Timestamp,
    hold_deadline: pd.Timestamp | None,
) -> tuple[str, float | None, pd.Timestamp | None]:
    if ticks.empty:
        return CF_EXIT_UNRESOLVED, None, None
    later = ticks.loc[(ticks["timestamp"] > entry_ts) & (ticks["timestamp"] < session_end)]
    last_price: float | None = None
    last_ts: pd.Timestamp | None = None
    for raw in later.to_dict(orient="records"):
        ts = raw["timestamp"]
        if hold_deadline is not None and ts >= hold_deadline:
            if last_price is not None:
                return CF_EXIT_TIME_STOP, last_price, last_ts
            return CF_EXIT_TIME_STOP, None, hold_deadline
        price = float(raw["price"])
        sl_hit, tp_hit = _tick_hits(direction, price, sl_price, tp_price)
        if sl_hit and tp_hit:
            return CF_EXIT_SL, sl_price, ts
        if sl_hit:
            return CF_EXIT_SL, sl_price, ts
        if tp_hit:
            return CF_EXIT_TP, tp_price, ts
        last_price = price
        last_ts = ts
    if last_price is not None and last_ts is not None:
        if _reached_this_session_end(last_ts + pd.Timedelta(seconds=1), session_end):
            return CF_EXIT_SESSION_END, last_price, session_end
        return CF_EXIT_UNRESOLVED, None, None
    return CF_EXIT_UNRESOLVED, None, None


def _bar_hits(
    direction: str, bar: Mapping[str, object], sl_price: float, tp_price: float
) -> tuple[bool, bool]:
    low = float(bar["low"])
    high = float(bar["high"])
    if direction == "long":
        return low <= sl_price, high >= tp_price
    return high >= sl_price, low <= tp_price


def _tick_hits(direction: str, price: float, sl_price: float, tp_price: float) -> tuple[bool, bool]:
    if direction == "long":
        return price <= sl_price, price >= tp_price
    return price >= sl_price, price <= tp_price


def _bracket_prices(
    direction: str, entry: float, sl_ticks: int | float, tp_ticks: int | float, tick: float
) -> tuple[float, float]:
    sl_off = sl_ticks * tick
    tp_off = tp_ticks * tick
    if direction == "long":
        return entry - sl_off, entry + tp_off
    return entry + sl_off, entry - tp_off


def _next_15s_open(entry_ts: pd.Timestamp) -> pd.Timestamp:
    floored = entry_ts.floor("s")
    second = int(floored.second)
    bucket = (second // JOIN_BAR_SECONDS) * JOIN_BAR_SECONDS
    open_ts = floored.replace(second=bucket, microsecond=0)
    return open_ts + _BAR_DELTA


def _reached_this_session_end(clock: pd.Timestamp, session_end: pd.Timestamp) -> bool:
    """True only when this session's clock reached CME 18:00, not a later day."""
    return clock >= session_end


def _session_end_utc(session: date) -> pd.Timestamp:
    hour, minute = (int(part) for part in JOURNAL_ETH_START.split(":"))
    local = pd.Timestamp(datetime.combine(session, time(hour, minute)), tz=JOURNAL_EXCHANGE_TZ)
    return local.tz_convert("UTC")


def _parse_brackets(
    brackets: Sequence[tuple[int, int, int | None] | Sequence[object]],
) -> tuple[tuple[int, int, int | None], ...]:
    if isinstance(brackets, (str, bytes)) or not isinstance(brackets, Sequence) or not brackets:
        raise JournalIngestError("brackets must be a non-empty sequence of (sl, tp, max_hold)")
    parsed: list[tuple[int, int, int | None]] = []
    for item in brackets:
        if isinstance(item, Mapping):
            sl_raw, tp_raw, hold_raw = (
                item.get("sl_ticks"),
                item.get("tp_ticks"),
                item.get("max_hold_seconds"),
            )
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            if len(item) == 2:
                sl_raw, tp_raw, hold_raw = item[0], item[1], None
            elif len(item) == 3:
                sl_raw, tp_raw, hold_raw = item[0], item[1], item[2]
            else:
                raise JournalIngestError(
                    "each bracket must be (sl_ticks, tp_ticks[, max_hold_seconds])"
                )
        else:
            raise JournalIngestError("each bracket must be a sequence or mapping")
        sl_ticks = _as_positive_int(sl_raw, "sl_ticks")
        tp_ticks = _as_positive_int(tp_raw, "tp_ticks")
        hold = None if hold_raw in (None, "") else _as_positive_int(hold_raw, "max_hold_seconds")
        parsed.append((sl_ticks, tp_ticks, hold))
    return tuple(parsed)


def _load_brackets(
    value: str | Path | Sequence[object] | None,
) -> tuple[tuple[int, int, int | None], ...]:
    if value is None:
        return DEFAULT_CF_BRACKETS
    if isinstance(value, (str, Path)):
        path = Path(value)
        if not path.is_file():
            raise JournalIngestError(f"brackets file not found: {path}")
        text = path.read_text(encoding="utf-8")
        payload = (
            yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
        )
        if isinstance(payload, Mapping):
            payload = payload.get("brackets", payload)
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise JournalIngestError("brackets file must contain a list")
        return _parse_brackets(payload)
    return _parse_brackets(value)


def _cf_id(sl_ticks: int | float, tp_ticks: int | float, max_hold: int | None) -> str:
    if max_hold is None:
        return f"bracket:{sl_ticks}/{tp_ticks}"
    return f"bracket:{sl_ticks}/{tp_ticks}/{max_hold}"


def _coerce_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    needed = {
        "trade_id",
        "entry_timestamp",
        "entry_price",
        "direction",
        "qty",
        "session_date",
        "instrument",
    }
    missing = sorted(needed.difference(trades.columns))
    if missing:
        raise JournalIngestError("trades frame missing columns: " + ", ".join(missing))
    work = trades.copy()
    work["trade_id"] = work["trade_id"].map(str)
    if work["trade_id"].duplicated().any():
        raise JournalIngestError("trades frame has duplicate trade_id")
    work["entry_timestamp"] = [_as_utc(value) for value in work["entry_timestamp"]]
    work["entry_price"] = pd.to_numeric(work["entry_price"], errors="coerce")
    if (
        work["entry_price"].isna().any()
        or not work["entry_price"].map(math.isfinite).all()
        or not (work["entry_price"] > 0).all()
    ):
        raise JournalIngestError("trades frame has non-finite or non-positive entry_price")
    if "recon_status" in work.columns:
        work["recon_status"] = work["recon_status"].map(_as_optional_str)
    work["session_date"] = work["session_date"].map(_as_date)
    work["direction"] = work["direction"].map(_as_direction)
    work["instrument"] = work["instrument"].map(_as_instrument)
    work["qty"] = [
        _require_positive_int(value, field="qty", trade_id=str(tid))
        for value, tid in zip(work["qty"], work["trade_id"], strict=True)
    ]
    return work


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal counterfactual refuses days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal counterfactual refuses days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars is None or not isinstance(bars, pd.DataFrame):
        raise JournalIngestError("bars must be a DataFrame")
    needed = {"timestamp", *_OHLC}
    missing = sorted(needed.difference(bars.columns))
    if missing:
        raise JournalIngestError("bars missing columns: " + ", ".join(missing))
    if bars.empty:
        raise JournalIngestError("bars has no rows")
    work = bars.loc[:, ["timestamp", *_OHLC]].copy()
    work["timestamp"] = [_as_utc(value) for value in work["timestamp"]]
    work["timestamp"] = pd.Series(pd.to_datetime(work["timestamp"], utc=True))
    if (work["timestamp"].dt.second % JOIN_BAR_SECONDS != 0).any() or (
        work["timestamp"].dt.microsecond != 0
    ).any():
        raise JournalIngestError("bars timestamps must be 15s bar opens (:00/:15/:30/:45)")
    if not work["timestamp"].dt.second.isin(_VALID_15S).all():
        raise JournalIngestError("bars timestamps must be 15s bar opens (:00/:15/:30/:45)")
    for column in _OHLC:
        work[column] = pd.to_numeric(work[column], errors="coerce")
        if work[column].isna().any() or not work[column].map(math.isfinite).all():
            raise JournalIngestError(f"bars has non-finite {column}")
    if (work["high"] < work["low"]).any():
        raise JournalIngestError("bars has high < low")
    work = work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if work["timestamp"].duplicated().any():
        raise JournalIngestError("bars has duplicate opens")
    return work


def _normalize_ticks(ticks: pd.DataFrame | None) -> pd.DataFrame:
    if ticks is None or not isinstance(ticks, pd.DataFrame) or ticks.empty:
        raise JournalIngestError("resolution='tick' requires a non-empty ticks frame")
    if "timestamp" not in ticks.columns or "price" not in ticks.columns:
        raise JournalIngestError("ticks frame requires timestamp and price")
    work = ticks.loc[:, ["timestamp", "price"]].copy()
    work["timestamp"] = pd.Series(
        pd.to_datetime([_as_utc(value) for value in work["timestamp"]], utc=True)
    )
    work["price"] = pd.to_numeric(work["price"], errors="coerce")
    if work["price"].isna().any() or not work["price"].map(math.isfinite).all():
        raise JournalIngestError("ticks frame has non-finite price")
    return work.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _group_indices(records: Sequence[Mapping[str, object]]) -> list[list[int]]:
    grouped: dict[date, list[int]] = {}
    for index, row in enumerate(records):
        grouped.setdefault(row["session_date"], []).append(index)
    return list(grouped.values())


def _shuffle_directions(
    records: Sequence[Mapping[str, object]],
    groups: Sequence[Sequence[int]],
    rng: np.random.RandomState,
) -> list[str]:
    assigned = [str(row["direction"]) for row in records]
    for indices in groups:
        labels = np.array([assigned[i] for i in indices], dtype=object)
        shuffled = rng.permutation(labels)
        for offset, index in enumerate(indices):
            assigned[index] = str(shuffled[offset])
    return assigned


def _gross_ticks(row: Mapping[str, object], *, direction: str, tick: float) -> float:
    exit_price = float(row["exit_price"])
    entry = float(row["entry_price"])
    qty = int(row["qty"])
    return _signed_points(direction, entry, exit_price) * qty / tick


def _has_exit(row: Mapping[str, object]) -> bool:
    price = row.get("exit_price")
    if price is None:
        return False
    try:
        return math.isfinite(float(price))
    except (TypeError, ValueError):
        return False


def _signed_points(direction: str, entry: float, exit_price: float) -> float:
    if direction == "long":
        return exit_price - entry
    if direction == "short":
        return entry - exit_price
    raise JournalIngestError(f"invalid direction {direction!r}")


def _cost_ticks(raw: Mapping[str, object], tick_value: float) -> float:
    fee = _optional_float(raw.get("fee_ticks"))
    extra = _optional_float(raw.get("day_fee_allocation"))
    if fee is not None:
        return fee + ((extra / tick_value) if extra is not None else 0.0)
    commission = _optional_float(raw.get("commission_cost"))
    total = 0.0
    if commission is not None:
        total += commission / tick_value
    if extra is not None:
        total += extra / tick_value
    return total


def _cf_frame(rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(COUNTERFACTUAL_OUTPUT_COLUMNS))
    keep = [column for column in COUNTERFACTUAL_OUTPUT_COLUMNS if column in rows[0]]
    extra = [column for column in ("cf_exit_ts",) if column in rows[0]]
    out = pd.DataFrame(index=range(len(rows)))
    object_cols = {
        "cf_exit_price",
        "cf_gross_ticks",
        "cf_net_ticks",
        "cf_exit_ts",
        "max_hold_seconds",
    }
    for column in keep + extra:
        values = [row.get(column) for row in rows]
        if column in object_cols:
            out[column] = pd.Series(values, dtype="object")
        else:
            out[column] = pd.Series(values)
    return out


def _as_utc(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise JournalIngestError("timestamp is missing")
    if stamp.tzinfo is None:
        raise JournalIngestError(f"naive timestamp is not allowed ({stamp!r})")
    return stamp.tz_convert("UTC")


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return date.fromisoformat(str(value)[:10])


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


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


def _as_direction(value: object) -> str:
    text = str(value)
    if text not in {"long", "short"}:
        raise JournalIngestError(f"invalid direction {text!r}")
    return text


def _as_instrument(value: object) -> str:
    text = str(value)
    if text not in JOURNAL_POINT_VALUE:
        raise JournalIngestError(f"unknown instrument {text!r}")
    return text


def _require_positive_int(value: object, *, field: str, trade_id: str) -> int:
    if isinstance(value, bool):
        raise JournalIngestError(
            f"trade {trade_id!r} {field} must be a positive int (got {value!r})"
        )
    if isinstance(value, Integral):
        qty = int(value)
    elif isinstance(value, Real) and math.isfinite(float(value)) and float(value).is_integer():
        qty = int(value)
    else:
        raise JournalIngestError(
            f"trade {trade_id!r} {field} must be a positive int (got {value!r})"
        )
    if qty <= 0:
        raise JournalIngestError(
            f"trade {trade_id!r} {field} must be a positive int (got {value!r})"
        )
    return qty


def _as_positive_tick(value: object) -> float:
    return _as_positive_number(value, "tick_size")


def _as_positive_number(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    if isinstance(value, Integral):
        number = float(value)
    elif isinstance(value, Real) and math.isfinite(float(value)):
        number = float(value)
    else:
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    if number <= 0:
        raise JournalIngestError(f"{name} must be a positive number (got {value!r})")
    return number


def _as_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise JournalIngestError(f"{name} must be a positive int (got {value!r})")
    if isinstance(value, Integral):
        number = int(value)
    elif isinstance(value, Real) and math.isfinite(float(value)) and float(value).is_integer():
        number = int(value)
    else:
        raise JournalIngestError(f"{name} must be a positive int (got {value!r})")
    if number <= 0:
        raise JournalIngestError(f"{name} must be a positive int (got {value!r})")
    return number


def _load_table(path: str | Path, *, name: str) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise JournalIngestError(f"{name} file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(source)
    if suffix == ".csv":
        return pd.read_csv(source)
    raise JournalIngestError(f"{name} must be .parquet or .csv")


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal counterfactual must not write into results/studies/")
    return resolved
