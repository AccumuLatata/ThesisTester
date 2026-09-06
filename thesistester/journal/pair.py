"""Pair ``FillRecord`` rows into ``JournalTrade`` (TJ3).

``spread_id`` groups that net to zero with one open side pair via qty-aware
FIFO inside the group. A group that does not qualify is FIFO-matched
**inside the group** first (``fifo_fallback``); only residual lots, and
fills without ``spread_id``, join qty-aware FIFO per
``(instrument, contract, session_date)``. Does not reconcile AMP, join
bars, or call ``simulate_trades``.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from thesistester.journal.schema import (
    DEFAULT_JOURNAL_RISK_TICKS,
    ENTRY_KIND_IMPORTED,
    ENTRY_KIND_MANUAL,
    FILL_RECORD_COLUMNS,
    JOURNAL_POINT_VALUE,
    JOURNAL_TICK_SIZE,
    JOURNAL_TRADE_COLUMNS,
    PAIR_METHOD_FIFO,
    PAIR_METHOD_SPREAD,
    STATUS_CLOSED,
    STATUS_OPEN,
    JournalIngestError,
    JournalTrade,
)

_SIDES = frozenset({"buy", "sell"})
_ENTRY_KINDS = frozenset({ENTRY_KIND_IMPORTED, ENTRY_KIND_MANUAL})


@dataclass(frozen=True)
class _Fill:
    fill_id: str
    source_group_id: str | None
    instrument: str
    contract_month: str | None
    contract_year: int | None
    side: str
    qty: int
    price: float
    timestamp: pd.Timestamp
    session_date: date
    tags: tuple[str, ...]
    notes_text: str
    declared_stop: float | None
    declared_target: float | None


@dataclass
class _OpenLot:
    fill: _Fill
    remaining: int


@dataclass(frozen=True)
class _Intent:
    tags: tuple[str, ...]
    notes_text: str
    declared_stop: float | None
    declared_target: float | None


def pair_journal_trades(
    fills: pd.DataFrame,
    *,
    include_manual: bool = False,
    journal_risk_ticks: int = DEFAULT_JOURNAL_RISK_TICKS,
) -> pd.DataFrame:
    """Pair imported fills into ``JournalTrade`` rows.

    ``include_manual`` and ``journal_risk_ticks`` are keyword-only. Manual
    rows and ``qty is None`` rows are excluded unless ``include_manual=True``
    (zero-qty manuals still cannot pair).
    """
    _validate_risk_ticks(journal_risk_ticks)
    if not isinstance(include_manual, bool):
        raise JournalIngestError("include_manual must be a bool")
    rows = _fills_from_frame(fills, include_manual=include_manual)
    grouped: dict[str, list[_Fill]] = defaultdict(list)
    fallback: list[_Fill] = []
    for fill in rows:
        if fill.source_group_id is None:
            fallback.append(fill)
            continue
        grouped[fill.source_group_id].append(fill)

    trades: list[JournalTrade] = []
    for spread_id, members in grouped.items():
        ordered = _sorted_fills(members)
        _assert_homogeneous_group(ordered, spread_id)
        intent = _intent_from_fills(ordered)
        if _nets_flat_one_open_side(ordered):
            closed, leftovers = _fifo_match(
                ordered,
                pair_method=PAIR_METHOD_SPREAD,
                group_key=spread_id,
                intent=intent,
                journal_risk_ticks=journal_risk_ticks,
            )
            trades.extend(closed)
            # Net-flat + one open side should consume every lot. Emit any
            # residual as open under the same spread key rather than mixing
            # it into the session book (defensive; the predicate forbids it).
            trades.extend(
                _open_trade(
                    lot=lot,
                    lot_seq=len(closed) + index,
                    pair_method=PAIR_METHOD_SPREAD,
                    group_key=spread_id,
                    intent=intent,
                    journal_risk_ticks=journal_risk_ticks,
                )
                for index, lot in enumerate(leftovers)
            )
        else:
            closed, leftovers = _fifo_match(
                ordered,
                pair_method=PAIR_METHOD_FIFO,
                group_key=spread_id,
                intent=intent,
                journal_risk_ticks=journal_risk_ticks,
            )
            trades.extend(closed)
            fallback.extend(_fill_from_lot(lot, intent=intent) for lot in leftovers)

    buckets: dict[tuple[str, str | None, int | None, date], list[_Fill]] = defaultdict(list)
    for fill in fallback:
        buckets[_fallback_key(fill)].append(fill)
    for key, members in buckets.items():
        ordered = _sorted_fills(members)
        trades.extend(
            _fifo_pair(
                ordered,
                pair_method=PAIR_METHOD_FIFO,
                group_key=_fifo_group_key(key),
                intent=None,
                journal_risk_ticks=journal_risk_ticks,
            )
        )

    trades.sort(key=lambda trade: (trade.entry_timestamp, trade.trade_id))
    return _trades_to_frame(trades)


def _validate_risk_ticks(value: object) -> None:
    if type(value) is not int or isinstance(value, bool) or value <= 0:
        raise JournalIngestError(f"journal_risk_ticks must be a positive int (got {value!r})")


def _fills_from_frame(frame: pd.DataFrame, *, include_manual: bool) -> list[_Fill]:
    if not isinstance(frame, pd.DataFrame):
        raise JournalIngestError("pair_journal_trades expects a FillRecord DataFrame")
    missing = [name for name in FILL_RECORD_COLUMNS if name not in frame.columns]
    if missing:
        raise JournalIngestError("fills frame missing columns: " + ", ".join(missing))
    out: list[_Fill] = []
    for row in frame.itertuples(index=False):
        fill_id = str(getattr(row, "fill_id"))
        kind = str(getattr(row, "entry_kind"))
        if kind not in _ENTRY_KINDS:
            raise JournalIngestError(
                f"fill {fill_id!r} entry_kind must be imported or manual (got {kind!r})"
            )
        if kind != ENTRY_KIND_IMPORTED and not include_manual:
            continue
        qty = getattr(row, "qty")
        if qty is None or (isinstance(qty, float) and pd.isna(qty)):
            continue
        qty_int = _require_positive_int(qty, fill_id=fill_id, field="qty")
        instrument = str(getattr(row, "instrument"))
        if instrument not in JOURNAL_POINT_VALUE:
            raise JournalIngestError(f"unknown journal instrument {instrument!r}")
        side = str(getattr(row, "side"))
        if side not in _SIDES:
            raise JournalIngestError(f"fill {fill_id!r} side must be buy or sell (got {side!r})")
        price = _require_positive_finite(getattr(row, "price"), fill_id=fill_id, field="price")
        tag_tuple = _coerce_tags(getattr(row, "tags"), fill_id=fill_id)
        ts = pd.Timestamp(getattr(row, "timestamp"))
        if ts.tzinfo is None:
            raise JournalIngestError(f"fill {fill_id!r} timestamp must be tz-aware")
        session = _coerce_session_date(getattr(row, "session_date"), fill_id=fill_id)
        group = getattr(row, "source_group_id")
        if group is None or (isinstance(group, float) and pd.isna(group)) or str(group) == "":
            group = None
        else:
            group = str(group)
        out.append(
            _Fill(
                fill_id=fill_id,
                source_group_id=group,
                instrument=instrument,
                contract_month=_optional_str(getattr(row, "contract_month")),
                contract_year=_optional_int(getattr(row, "contract_year")),
                side=side,
                qty=qty_int,
                price=price,
                timestamp=ts.tz_convert("UTC"),
                session_date=session,
                tags=tag_tuple,
                notes_text=_optional_str(getattr(row, "notes_text")) or "",
                declared_stop=_optional_float(getattr(row, "declared_stop"), fill_id=fill_id),
                declared_target=_optional_float(getattr(row, "declared_target"), fill_id=fill_id),
            )
        )
    return out


def _optional_str(value: object) -> str | None:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)
    if text in {"", "nan", "NaN", "<NA>", "None"}:
        return None
    return text


def _optional_int(value: object) -> int | None:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        raise JournalIngestError(f"contract_year must be an int (got {value!r})")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    raise JournalIngestError(f"contract_year must be an int (got {value!r})")


def _optional_float(value: object, *, fill_id: str | None = None) -> float | None:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return None
    number = float(value)
    if not math.isfinite(number):
        where = f"fill {fill_id!r} " if fill_id is not None else ""
        raise JournalIngestError(f"{where}optional numeric must be finite (got {value!r})")
    return number


def _require_positive_int(value: object, *, fill_id: str, field: str) -> int:
    if isinstance(value, bool):
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    if isinstance(value, int):
        qty = int(value)
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        qty = int(value)
    else:
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    if qty <= 0:
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    return qty


def _require_positive_finite(value: object, *, fill_id: str, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(
            f"fill {fill_id!r} {field} must be a finite positive number (got {value!r})"
        ) from exc
    if not math.isfinite(number) or number <= 0.0:
        raise JournalIngestError(
            f"fill {fill_id!r} {field} must be a finite positive number (got {value!r})"
        )
    return number


def _coerce_tags(value: object, *, fill_id: str) -> tuple[str, ...]:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return ()
    if isinstance(value, (str, bytes)):
        raise JournalIngestError(
            f"fill {fill_id!r} tags must be a sequence of tokens (got {value!r})"
        )
    return tuple(str(tag) for tag in value)


def _coerce_session_date(value: object, *, fill_id: str) -> date:
    """Calendar date only. ``datetime`` / ``Timestamp`` are instances of ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise JournalIngestError(
            f"fill {fill_id!r} session_date must be a calendar date (got {value!r})"
        ) from exc
    if pd.isna(parsed):
        raise JournalIngestError(f"fill {fill_id!r} session_date must be a calendar date")
    return parsed.date()


def _sorted_fills(fills: Sequence[_Fill]) -> list[_Fill]:
    return sorted(fills, key=lambda fill: (fill.timestamp, fill.fill_id))


def _nets_flat_one_open_side(fills: Sequence[_Fill]) -> bool:
    """True when signed qty nets to 0 and the book never opens the other side."""
    if not fills:
        return False
    net = 0
    open_side: str | None = None
    buy_qty = 0
    sell_qty = 0
    for fill in fills:
        if fill.side == "buy":
            buy_qty += fill.qty
            net += fill.qty
        elif fill.side == "sell":
            sell_qty += fill.qty
            net -= fill.qty
        else:
            raise JournalIngestError(f"fill {fill.fill_id!r} side must be buy or sell")
        if net == 0:
            continue
        side = "buy" if net > 0 else "sell"
        if open_side is None:
            open_side = side
        elif side != open_side:
            return False
    return buy_qty == sell_qty and buy_qty > 0


def _intent_from_fills(fills: Sequence[_Fill]) -> _Intent:
    tags: list[str] = []
    seen: set[str] = set()
    notes = ""
    stop = None
    target = None
    for fill in fills:
        for tag in fill.tags:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
        if not notes and fill.notes_text:
            notes = fill.notes_text
        if stop is None and fill.declared_stop is not None:
            stop = fill.declared_stop
        if target is None and fill.declared_target is not None:
            target = fill.declared_target
    return _Intent(tags=tuple(tags), notes_text=notes, declared_stop=stop, declared_target=target)


def _assert_homogeneous_group(fills: Sequence[_Fill], spread_id: str) -> None:
    instruments = {fill.instrument for fill in fills}
    months = {fill.contract_month for fill in fills}
    years = {fill.contract_year for fill in fills}
    if len(instruments) > 1 or len(months) > 1 or len(years) > 1:
        raise JournalIngestError(
            f"spread_id {spread_id!r} mixes instrument/contract "
            f"(instruments={sorted(instruments)}, months={sorted(str(m) for m in months)}, "
            f"years={sorted(str(y) for y in years)})"
        )


def _fill_from_lot(lot: _OpenLot, *, intent: _Intent) -> _Fill:
    fill = lot.fill
    return _Fill(
        fill_id=fill.fill_id,
        source_group_id=fill.source_group_id,
        instrument=fill.instrument,
        contract_month=fill.contract_month,
        contract_year=fill.contract_year,
        side=fill.side,
        qty=lot.remaining,
        price=fill.price,
        timestamp=fill.timestamp,
        session_date=fill.session_date,
        tags=intent.tags,
        notes_text=intent.notes_text,
        declared_stop=intent.declared_stop,
        declared_target=intent.declared_target,
    )


def _fallback_key(fill: _Fill) -> tuple[str, str | None, int | None, date]:
    return (fill.instrument, fill.contract_month, fill.contract_year, fill.session_date)


def _fifo_group_key(key: tuple[str, str | None, int | None, date]) -> str:
    instrument, month, year, session = key
    month_part = month if month is not None else "-"
    year_part = str(year) if year is not None else "-"
    return f"fifo:{instrument}:{month_part}:{year_part}:{session.isoformat()}"


def _fifo_match(
    fills: Sequence[_Fill],
    *,
    pair_method: str,
    group_key: str,
    intent: _Intent | None,
    journal_risk_ticks: int,
) -> tuple[list[JournalTrade], list[_OpenLot]]:
    opens: deque[_OpenLot] = deque()
    trades: list[JournalTrade] = []
    lot_seq = 0
    for fill in fills:
        remaining = fill.qty
        while remaining > 0:
            if not opens or opens[0].fill.side == fill.side:
                opens.append(_OpenLot(fill=fill, remaining=remaining))
                remaining = 0
                break
            lot = opens[0]
            take = min(lot.remaining, remaining)
            trade_intent = intent if intent is not None else _intent_from_fills((lot.fill, fill))
            trades.append(
                _closed_trade(
                    entry=lot.fill,
                    exit_fill=fill,
                    qty=take,
                    lot_seq=lot_seq,
                    pair_method=pair_method,
                    group_key=group_key,
                    intent=trade_intent,
                    journal_risk_ticks=journal_risk_ticks,
                )
            )
            lot_seq += 1
            lot.remaining -= take
            remaining -= take
            if lot.remaining == 0:
                opens.popleft()
    return trades, list(opens)


def _fifo_pair(
    fills: Sequence[_Fill],
    *,
    pair_method: str,
    group_key: str,
    intent: _Intent | None,
    journal_risk_ticks: int,
) -> list[JournalTrade]:
    trades, leftovers = _fifo_match(
        fills,
        pair_method=pair_method,
        group_key=group_key,
        intent=intent,
        journal_risk_ticks=journal_risk_ticks,
    )
    lot_seq = len(trades)
    for lot in leftovers:
        leftover_intent = intent if intent is not None else _intent_from_fills((lot.fill,))
        trades.append(
            _open_trade(
                lot=lot,
                lot_seq=lot_seq,
                pair_method=pair_method,
                group_key=group_key,
                intent=leftover_intent,
                journal_risk_ticks=journal_risk_ticks,
            )
        )
        lot_seq += 1
    return trades


def _closed_trade(
    *,
    entry: _Fill,
    exit_fill: _Fill,
    qty: int,
    lot_seq: int,
    pair_method: str,
    group_key: str,
    intent: _Intent,
    journal_risk_ticks: int,
) -> JournalTrade:
    direction: str = "long" if entry.side == "buy" else "short"
    if direction == "long":
        points = exit_fill.price - entry.price
    else:
        points = entry.price - exit_fill.price
    point_value = JOURNAL_POINT_VALUE[entry.instrument]
    tick_value = JOURNAL_TICK_SIZE * point_value
    gross_currency = points * point_value * qty
    # Costs stay null until TJ4; net equals gross so r / net_ticks stay defined.
    net_currency = gross_currency
    risk = journal_risk_ticks * tick_value * qty
    r_multiple = net_currency / risk
    r_declared = None
    if intent.declared_stop is not None:
        distance = abs(entry.price - intent.declared_stop)
        if distance > 0:
            r_declared = net_currency / (distance * point_value * qty)
    hold = (exit_fill.timestamp - entry.timestamp).total_seconds()
    return JournalTrade(
        trade_id=f"jt:{group_key}:{lot_seq}",
        source_group_id=entry.source_group_id,
        pair_method=pair_method,  # type: ignore[arg-type]
        lot_seq=lot_seq,
        direction=direction,  # type: ignore[arg-type]
        instrument=entry.instrument,
        contract_month=entry.contract_month,
        contract_year=entry.contract_year,
        session_date=entry.session_date,
        qty=qty,
        entry_timestamp=entry.timestamp,
        exit_timestamp=exit_fill.timestamp,
        entry_price=entry.price,
        exit_price=exit_fill.price,
        entry_fill_id=entry.fill_id,
        exit_fill_id=exit_fill.fill_id,
        gross_pnl_points=points,
        gross_pnl_currency=gross_currency,
        commission_cost=None,
        slippage_cost=None,
        day_fee_allocation=None,
        net_pnl_currency=net_currency,
        r_multiple=r_multiple,
        r_multiple_declared=r_declared,
        journal_risk_ticks=journal_risk_ticks,
        fee_ticks=None,
        net_ticks=net_currency / tick_value,
        hold_seconds=hold,
        bars_held=None,
        mae_points=None,
        mfe_points=None,
        stop_price=intent.declared_stop,
        target_price=intent.declared_target,
        tags=intent.tags,
        notes_text=intent.notes_text,
        status=STATUS_CLOSED,
        signal_id=None,
        trigger=None,
    )


def _open_trade(
    *,
    lot: _OpenLot,
    lot_seq: int,
    pair_method: str,
    group_key: str,
    intent: _Intent,
    journal_risk_ticks: int,
) -> JournalTrade:
    entry = lot.fill
    direction: str = "long" if entry.side == "buy" else "short"
    return JournalTrade(
        trade_id=f"jt:{group_key}:{lot_seq}",
        source_group_id=entry.source_group_id,
        pair_method=pair_method,  # type: ignore[arg-type]
        lot_seq=lot_seq,
        direction=direction,  # type: ignore[arg-type]
        instrument=entry.instrument,
        contract_month=entry.contract_month,
        contract_year=entry.contract_year,
        session_date=entry.session_date,
        qty=lot.remaining,
        entry_timestamp=entry.timestamp,
        exit_timestamp=None,
        entry_price=entry.price,
        exit_price=None,
        entry_fill_id=entry.fill_id,
        exit_fill_id=None,
        gross_pnl_points=None,
        gross_pnl_currency=None,
        commission_cost=None,
        slippage_cost=None,
        day_fee_allocation=None,
        net_pnl_currency=None,
        r_multiple=None,
        r_multiple_declared=None,
        journal_risk_ticks=journal_risk_ticks,
        fee_ticks=None,
        net_ticks=None,
        hold_seconds=None,
        bars_held=None,
        mae_points=None,
        mfe_points=None,
        stop_price=intent.declared_stop,
        target_price=intent.declared_target,
        tags=intent.tags,
        notes_text=intent.notes_text,
        status=STATUS_OPEN,
        signal_id=None,
        trigger=None,
    )


def _trades_to_frame(trades: Iterable[JournalTrade]) -> pd.DataFrame:
    items = list(trades)
    empty = {column: pd.Series(dtype="object") for column in JOURNAL_TRADE_COLUMNS}
    empty["entry_timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
    empty["exit_timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
    if not items:
        return pd.DataFrame(empty, columns=list(JOURNAL_TRADE_COLUMNS))
    frame = pd.DataFrame(index=range(len(items)))
    for column in JOURNAL_TRADE_COLUMNS:
        if column in {"entry_timestamp", "exit_timestamp"}:
            continue
        frame[column] = pd.Series([getattr(item, column) for item in items], dtype="object")
    frame["entry_timestamp"] = pd.Series(
        [item.entry_timestamp for item in items], dtype="datetime64[ns, UTC]"
    )
    frame["exit_timestamp"] = pd.Series(
        [item.exit_timestamp if item.exit_timestamp is not None else pd.NaT for item in items],
        dtype="datetime64[ns, UTC]",
    )
    return frame.loc[:, list(JOURNAL_TRADE_COLUMNS)]
