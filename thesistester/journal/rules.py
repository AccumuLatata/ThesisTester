"""Declared journal discipline rules (TJ7). Data, never searched.

``declared_on`` is required. Evaluation is time-ordered and emits
``in_sample`` / ``forward`` separately — never a blended number.
Does not call ``simulate_trades``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from numbers import Integral, Real
from pathlib import Path
import json
import math

import pandas as pd
import yaml

from thesistester.journal.schema import (
    JOURNAL_EXCHANGE_TZ,
    JOURNAL_POINT_VALUE,
    JOURNAL_TICK_SIZE,
    RECON_RECONCILED,
    RULE_FILTER_KEYS,
    RULE_SPLIT_FORWARD,
    RULE_SPLIT_IN_SAMPLE,
    JournalIngestError,
)

_ALLOWED_KEYS = frozenset({"name", "declared_on"}) | RULE_FILTER_KEYS


@dataclass(frozen=True)
class JournalRule:
    """One pre-registered discipline rule."""

    name: str
    declared_on: date
    trade_window_ny: tuple[time, time] | None = None
    max_trades_per_day: int | None = None
    cooldown_seconds_after_loss: float | None = None
    stop_after_k_consecutive_losses: int | None = None
    daily_loss_stop_ticks: float | None = None
    hard_stop_ticks: float | None = None


def load_journal_rules(
    path: str | Path | Mapping[str, object] | Sequence[object],
) -> tuple[JournalRule, ...]:
    """Load rules from YAML/JSON path or an in-memory mapping/list."""
    if isinstance(path, Mapping):
        payload: object = dict(path)
    elif isinstance(path, (str, Path)):
        payload = _load_payload(Path(path))
    elif isinstance(path, Sequence) and not isinstance(path, (str, bytes)):
        payload = {"rules": list(path)}
    else:
        raise JournalIngestError("rules must be a path, mapping, or sequence")
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, Mapping)):
        rows = list(payload)
    elif isinstance(payload, Mapping):
        raw = payload.get("rules", payload)
        if isinstance(raw, Mapping):
            rows = [raw]
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            rows = list(raw)
        else:
            raise JournalIngestError("rules payload must be a list or mapping")
    else:
        raise JournalIngestError("rules payload must be a list or mapping")
    return tuple(parse_journal_rule(row) for row in rows)


def parse_journal_rule(raw: Mapping[str, object]) -> JournalRule:
    """Parse one rule. ``declared_on`` is required (``ValueError`` if missing)."""
    if not isinstance(raw, Mapping):
        raise JournalIngestError("each rule must be a mapping")
    unknown = sorted(set(raw) - _ALLOWED_KEYS)
    if unknown:
        raise JournalIngestError("unknown journal rule keys: " + ", ".join(unknown))
    name = str(raw.get("name") or "").strip()
    if not name:
        raise JournalIngestError("journal rule name is required")
    if "declared_on" not in raw or raw.get("declared_on") in (None, ""):
        raise ValueError("journal rule declared_on is required")
    declared = _as_date(raw["declared_on"])
    window = _as_window(raw.get("trade_window_ny"))
    return JournalRule(
        name=name,
        declared_on=declared,
        trade_window_ny=window,
        max_trades_per_day=_as_optional_positive_int(
            raw.get("max_trades_per_day"), "max_trades_per_day"
        ),
        cooldown_seconds_after_loss=_as_optional_nonneg(
            raw.get("cooldown_seconds_after_loss"), "cooldown_seconds_after_loss"
        ),
        stop_after_k_consecutive_losses=_as_optional_positive_int(
            raw.get("stop_after_k_consecutive_losses"), "stop_after_k_consecutive_losses"
        ),
        daily_loss_stop_ticks=_as_optional_nonneg(
            raw.get("daily_loss_stop_ticks"), "daily_loss_stop_ticks"
        ),
        hard_stop_ticks=_as_optional_positive_number(raw.get("hard_stop_ticks"), "hard_stop_ticks"),
    )


def apply_journal_rules(
    trades: pd.DataFrame,
    rules: Sequence[JournalRule],
    *,
    hard_stop_exits: Mapping[tuple[str, float], tuple[float, pd.Timestamp]] | None = None,
    allow_unreconciled: bool = False,
) -> tuple[dict[str, object], ...]:
    """Evaluate each rule in time order. Returns per-rule × split summaries.

    ``hard_stop_exits`` maps ``(trade_id, hard_stop_ticks)`` to
    ``(exit_price, exit_ts)`` from the TJ7 SL walk. Missing ``declared_on`` is
    rejected at parse time, not here. ``allow_unreconciled`` is keyword-only.
    """
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise JournalIngestError("rules must be a sequence of JournalRule")
    if trades is None or not isinstance(trades, pd.DataFrame):
        raise JournalIngestError("trades must be a DataFrame")
    _assert_reconciled(trades, allow_unreconciled=allow_unreconciled)
    ordered = _ordered_trades(trades)
    summaries: list[dict[str, object]] = []
    for rule in rules:
        if not isinstance(rule, JournalRule):
            raise JournalIngestError(f"rules must contain JournalRule (got {type(rule).__name__})")
        summaries.extend(_apply_one(ordered, rule, hard_stop_exits=hard_stop_exits or {}))
    return tuple(summaries)


def _apply_one(
    trades: list[dict[str, object]],
    rule: JournalRule,
    *,
    hard_stop_exits: Mapping[tuple[str, float], tuple[float, pd.Timestamp]],
) -> list[dict[str, object]]:
    buckets: dict[str, dict[str, float]] = {
        RULE_SPLIT_IN_SAMPLE: _empty_bucket(),
        RULE_SPLIT_FORWARD: _empty_bucket(),
    }
    day_count: dict[date, int] = {}
    day_streak: dict[date, int] = {}
    day_net: dict[date, float] = {}
    halted: set[date] = set()
    last_loss_exit: pd.Timestamp | None = None
    for raw in trades:
        split = _split(raw["session_date"], rule.declared_on)
        baseline = _net_ticks(raw)
        buckets[split]["n_total"] += 1
        if baseline is not None:
            buckets[split]["baseline_net_ticks"] += baseline
        session = raw["session_date"]
        if session in halted:
            buckets[split]["trades_removed"] += 1
            continue
        if rule.trade_window_ny is not None and not _in_window(
            raw["entry_timestamp"], rule.trade_window_ny
        ):
            buckets[split]["trades_removed"] += 1
            continue
        if (
            rule.cooldown_seconds_after_loss is not None
            and last_loss_exit is not None
            and raw["entry_timestamp"]
            < last_loss_exit + pd.Timedelta(seconds=rule.cooldown_seconds_after_loss)
        ):
            buckets[split]["trades_removed"] += 1
            continue
        if (
            rule.max_trades_per_day is not None
            and day_count.get(session, 0) >= rule.max_trades_per_day
        ):
            buckets[split]["trades_removed"] += 1
            continue

        net = baseline
        exit_used = raw.get("exit_timestamp") or raw["entry_timestamp"]
        if rule.hard_stop_ticks is not None:
            net, stopped_at = _apply_hard_stop(raw, rule.hard_stop_ticks, hard_stop_exits, baseline)
            if stopped_at is not None:
                exit_used = stopped_at
        if net is not None:
            buckets[split]["rule_net_ticks"] += net
        buckets[split]["n_kept"] += 1
        day_count[session] = day_count.get(session, 0) + 1
        if net is not None:
            day_net[session] = day_net.get(session, 0.0) + net
            if net < 0:
                day_streak[session] = day_streak.get(session, 0) + 1
                last_loss_exit = exit_used
            elif net > 0:
                day_streak[session] = 0
            if rule.daily_loss_stop_ticks is not None and day_net[session] <= -float(
                rule.daily_loss_stop_ticks
            ):
                halted.add(session)
            if (
                rule.stop_after_k_consecutive_losses is not None
                and day_streak.get(session, 0) >= rule.stop_after_k_consecutive_losses
            ):
                halted.add(session)
        else:
            day_streak[session] = day_streak.get(session, 0)
    return [_summary_row(rule, split, bucket) for split, bucket in buckets.items()]


def _apply_hard_stop(
    raw: Mapping[str, object],
    hard_stop_ticks: float,
    hard_stop_exits: Mapping[tuple[str, float], tuple[float, pd.Timestamp]],
    baseline: float | None,
) -> tuple[float | None, pd.Timestamp | None]:
    key = (str(raw["trade_id"]), float(hard_stop_ticks))
    hit = hard_stop_exits.get(key)
    original_exit = raw.get("exit_timestamp")
    if isinstance(original_exit, pd.Timestamp):
        original_exit = (
            original_exit.tz_convert("UTC") if original_exit.tzinfo is not None else original_exit
        )
    if hit is None:
        return baseline, original_exit
    sl_price, sl_ts = hit
    sl_ts = pd.Timestamp(sl_ts)
    if sl_ts.tzinfo is not None:
        sl_ts = sl_ts.tz_convert("UTC")
    if original_exit is not None and sl_ts >= pd.Timestamp(original_exit):
        return baseline, original_exit
    qty = int(raw["qty"])
    instrument = str(raw["instrument"])
    if instrument not in JOURNAL_POINT_VALUE:
        raise JournalIngestError(f"unknown instrument {instrument!r}")
    point_value = JOURNAL_POINT_VALUE[instrument]
    tick_value = JOURNAL_TICK_SIZE * point_value
    points = _signed_points(str(raw["direction"]), float(raw["entry_price"]), sl_price)
    gross_ticks = points * qty / JOURNAL_TICK_SIZE
    cost = _cost_ticks(raw, tick_value)
    return gross_ticks - cost, sl_ts


def _empty_bucket() -> dict[str, float]:
    return {
        "n_total": 0.0,
        "n_kept": 0.0,
        "trades_removed": 0.0,
        "rule_net_ticks": 0.0,
        "baseline_net_ticks": 0.0,
    }


def _summary_row(rule: JournalRule, split: str, bucket: Mapping[str, float]) -> dict[str, object]:
    return {
        "name": rule.name,
        "declared_on": rule.declared_on.isoformat(),
        "split": split,
        "n_kept": int(bucket["n_kept"]),
        "n_total": int(bucket["n_total"]),
        "trades_removed": int(bucket["trades_removed"]),
        "rule_net_ticks": float(bucket["rule_net_ticks"]),
        "baseline_net_ticks": float(bucket["baseline_net_ticks"]),
        "rule_delta_ticks": float(bucket["rule_net_ticks"] - bucket["baseline_net_ticks"]),
    }


def _assert_reconciled(trades: pd.DataFrame, *, allow_unreconciled: bool) -> None:
    if allow_unreconciled:
        return
    if "recon_status" not in trades.columns:
        raise JournalIngestError(
            "journal rules refuse days that are not reconciled "
            "(pass allow_unreconciled=True to override)"
        )
    if trades.empty:
        return
    bad = [status for status in trades["recon_status"] if status != RECON_RECONCILED]
    if bad:
        raise JournalIngestError(
            "journal rules refuse days that are not reconciled "
            f"(got {sorted({str(item) for item in bad})}; "
            "pass allow_unreconciled=True to override)"
        )


def _ordered_trades(trades: pd.DataFrame) -> list[dict[str, object]]:
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
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in trades.to_dict(orient="records"):
        trade_id = str(raw["trade_id"])
        if trade_id in seen:
            raise JournalIngestError("trades frame has duplicate trade_id")
        seen.add(trade_id)
        entry = pd.Timestamp(raw["entry_timestamp"])
        if entry.tzinfo is None:
            raise JournalIngestError("naive timestamp is not allowed")
        session = raw["session_date"]
        if isinstance(session, str):
            session = date.fromisoformat(session)
        elif isinstance(session, pd.Timestamp):
            session = session.date()
        elif isinstance(session, datetime):
            session = session.date()
        exit_ts = raw.get("exit_timestamp")
        if exit_ts is not None and not pd.isna(exit_ts):
            exit_ts = pd.Timestamp(exit_ts)
            if pd.isna(exit_ts):
                exit_ts = None
            elif exit_ts.tzinfo is None:
                raise JournalIngestError("naive timestamp is not allowed")
            else:
                exit_ts = exit_ts.tz_convert("UTC")
        else:
            exit_ts = None
        direction = str(raw["direction"])
        if direction not in {"long", "short"}:
            raise JournalIngestError(f"invalid direction {direction!r}")
        instrument = str(raw["instrument"])
        if instrument not in JOURNAL_POINT_VALUE:
            raise JournalIngestError(f"unknown instrument {instrument!r}")
        price = float(raw["entry_price"])
        if not math.isfinite(price) or price <= 0:
            raise JournalIngestError("trades frame has non-finite or non-positive entry_price")
        rows.append(
            {
                "trade_id": trade_id,
                "entry_timestamp": entry.tz_convert("UTC"),
                "exit_timestamp": exit_ts,
                "entry_price": price,
                "exit_price": raw.get("exit_price"),
                "direction": direction,
                "qty": _require_positive_int(raw["qty"], field="qty", trade_id=trade_id),
                "instrument": instrument,
                "session_date": session,
                "net_ticks": raw.get("net_ticks"),
                "commission_cost": raw.get("commission_cost"),
                "day_fee_allocation": raw.get("day_fee_allocation"),
                "fee_ticks": raw.get("fee_ticks"),
            }
        )
    rows.sort(key=lambda item: (item["entry_timestamp"], item["trade_id"]))
    return rows


def _split(session: date, declared_on: date) -> str:
    if session < declared_on:
        return RULE_SPLIT_IN_SAMPLE
    return RULE_SPLIT_FORWARD


def _in_window(entry_ts: pd.Timestamp, window: tuple[time, time]) -> bool:
    local = entry_ts.tz_convert(JOURNAL_EXCHANGE_TZ)
    clock = local.timetz().replace(tzinfo=None)
    start, end = window
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end


def _net_ticks(raw: Mapping[str, object]) -> float | None:
    value = raw.get("net_ticks")
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(f"net_ticks must be finite (got {value!r})") from exc
    if math.isnan(number):
        return None
    if not math.isfinite(number):
        raise JournalIngestError(f"net_ticks must be finite (got {value!r})")
    return number


def _cost_ticks(raw: Mapping[str, object], tick_value: float) -> float:
    fee = raw.get("fee_ticks")
    if fee is not None:
        try:
            if not pd.isna(fee):
                extra = raw.get("day_fee_allocation")
                extra_ticks = 0.0
                if extra is not None and not (isinstance(extra, float) and pd.isna(extra)):
                    extra_ticks = float(extra) / tick_value
                return float(fee) + extra_ticks
        except (TypeError, ValueError):
            pass
    commission = raw.get("commission_cost")
    allocation = raw.get("day_fee_allocation")
    total = 0.0
    for item in (commission, allocation):
        if item is None:
            continue
        try:
            if pd.isna(item):
                continue
        except (TypeError, ValueError):
            pass
        total += float(item) / tick_value
    return total


def _signed_points(direction: str, entry: float, exit_price: float) -> float:
    if direction == "long":
        return exit_price - entry
    if direction == "short":
        return entry - exit_price
    raise JournalIngestError(f"invalid direction {direction!r}")


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    if isinstance(value, pd.Timestamp):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise JournalIngestError(f"invalid declared_on {value!r}") from exc


def _as_window(value: object) -> tuple[time, time] | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if "-" not in text:
        raise JournalIngestError(f"trade_window_ny must be HH:MM-HH:MM (got {value!r})")
    left, right = text.split("-", 1)
    return _as_hhmm(left), _as_hhmm(right)


def _as_hhmm(text: str) -> time:
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise JournalIngestError(f"invalid HH:MM {text!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
        return time(hour, minute)
    except ValueError as exc:
        raise JournalIngestError(f"invalid HH:MM {text!r}") from exc


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


def _as_optional_positive_int(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
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


def _as_optional_nonneg(value: object, name: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise JournalIngestError(f"{name} must be a non-negative number (got {value!r})")
    if isinstance(value, Integral):
        number = float(value)
    elif isinstance(value, Real) and math.isfinite(float(value)):
        number = float(value)
    else:
        raise JournalIngestError(f"{name} must be a non-negative number (got {value!r})")
    if number < 0:
        raise JournalIngestError(f"{name} must be a non-negative number (got {value!r})")
    return number


def _as_optional_positive_number(value: object, name: str) -> float | None:
    if value is None or value == "":
        return None
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


def _load_payload(path: Path) -> object:
    if not path.is_file():
        raise JournalIngestError(f"rules file not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    if suffix == ".json":
        return json.loads(text)
    raise JournalIngestError("rules file must be .yaml, .yml, or .json")
