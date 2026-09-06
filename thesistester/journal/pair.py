"""Pair ``FillRecord`` rows into ``JournalTrade`` (TJ3).

``spread_id`` groups that net to zero with one open side pair via qty-aware
FIFO inside the group. Everything else falls to qty-aware FIFO per
``(instrument, contract, session_date)`` and is flagged ``fifo_fallback``.
Does not reconcile AMP, join bars, or call ``simulate_trades``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from thesistester.journal.schema import (
    DEFAULT_JOURNAL_RISK_TICKS,
    ENTRY_KIND_IMPORTED,
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
        if _nets_flat_one_open_side(ordered):
            trades.extend(
                _fifo_pair(
                    ordered,
                    pair_method=PAIR_METHOD_SPREAD,
                    group_key=spread_id,
                    intent=_intent_from_fills(ordered),
                    journal_risk_ticks=journal_risk_ticks,
                )
            )
        else:
            fallback.extend(ordered)

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
        kind = str(getattr(row, "entry_kind"))
        if kind != ENTRY_KIND_IMPORTED and not include_manual:
            continue
        qty = getattr(row, "qty")
        if qty is None or (isinstance(qty, float) and pd.isna(qty)):
            continue
        qty_int = int(qty)
        if qty_int <= 0:
            raise JournalIngestError(f"fill {getattr(row, 'fill_id')!r} qty must be a positive int")
        instrument = str(getattr(row, "instrument"))
        if instrument not in JOURNAL_POINT_VALUE:
            raise JournalIngestError(f"unknown journal instrument {instrument!r}")
        tags = getattr(row, "tags")
        if tags is None or (isinstance(tags, float) and pd.isna(tags)):
            tag_tuple: tuple[str, ...] = ()
        else:
            tag_tuple = tuple(tags)
        ts = pd.Timestamp(getattr(row, "timestamp"))
        if ts.tzinfo is None:
            raise JournalIngestError(f"fill {getattr(row, 'fill_id')!r} timestamp must be tz-aware")
        session = getattr(row, "session_date")
        if not isinstance(session, date):
            session = date.fromisoformat(str(session))
        group = getattr(row, "source_group_id")
        if group is None or (isinstance(group, float) and pd.isna(group)) or str(group) == "":
            group = None
        else:
            group = str(group)
        out.append(
            _Fill(
                fill_id=str(getattr(row, "fill_id")),
                source_group_id=group,
                instrument=instrument,
                contract_month=_optional_str(getattr(row, "contract_month")),
                contract_year=_optional_int(getattr(row, "contract_year")),
                side=str(getattr(row, "side")),
                qty=qty_int,
                price=float(getattr(row, "price")),
                timestamp=ts.tz_convert("UTC"),
                session_date=session,
                tags=tag_tuple,
                notes_text=""
                if getattr(row, "notes_text") is None
                else str(getattr(row, "notes_text")),
                declared_stop=_optional_float(getattr(row, "declared_stop")),
                declared_target=_optional_float(getattr(row, "declared_target")),
            )
        )
    return out


def _optional_str(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


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


def _fallback_key(fill: _Fill) -> tuple[str, str | None, int | None, date]:
    return (fill.instrument, fill.contract_month, fill.contract_year, fill.session_date)


def _fifo_group_key(key: tuple[str, str | None, int | None, date]) -> str:
    instrument, month, year, session = key
    month_part = month if month is not None else "-"
    year_part = str(year) if year is not None else "-"
    return f"fifo:{instrument}:{month_part}:{year_part}:{session.isoformat()}"


def _fifo_pair(
    fills: Sequence[_Fill],
    *,
    pair_method: str,
    group_key: str,
    intent: _Intent | None,
    journal_risk_ticks: int,
) -> list[JournalTrade]:
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
    for lot in opens:
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
    risk = journal_risk_ticks * tick_value * qty
    r_multiple = gross_currency / risk
    r_declared = None
    if intent.declared_stop is not None:
        distance = abs(entry.price - intent.declared_stop)
        if distance > 0:
            r_declared = gross_currency / (distance * point_value * qty)
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
        net_pnl_currency=gross_currency,
        r_multiple=r_multiple,
        r_multiple_declared=r_declared,
        journal_risk_ticks=journal_risk_ticks,
        fee_ticks=None,
        net_ticks=gross_currency / tick_value,
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
