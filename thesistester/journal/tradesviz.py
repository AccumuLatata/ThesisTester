"""TradesViz executions CSV → ``FillRecord`` frame (TJ1).

Explicit profile ``tradesviz_executions`` only — no autodetect. Does not pair
fills, reconcile AMP, join bars, or call ``simulate_trades``.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
from html import unescape
from pathlib import Path
import re

import pandas as pd

from thesistester.journal.schema import (
    CME_MONTH_CODES,
    ENTRY_KIND_IMPORTED,
    ENTRY_KIND_MANUAL,
    FILL_RECORD_COLUMNS,
    FLAG_MANUAL_NO_QTY,
    JOURNAL_ETH_START,
    JOURNAL_EXCHANGE_TZ,
    JournalIngestError,
    SOURCE_TRADESVIZ,
    TRADESVIZ_EXECUTIONS_PROFILE,
    FillRecord,
)
from thesistester.levels.session_date import trading_session_date

# Locked column set from the desk TradesViz executions export (plan §0.2 / §3.1).
_REQUIRED_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "side",
    "currency",
    "underlying",
    "asset_type",
    "price",
    "quantity",
    "commission",
    "fees",
    "stop_loss",
    "profit_target",
    "tags",
    "notes",
    "spread_id",
)

_KNOWN_ROOTS: frozenset[str] = frozenset({"MNQ", "MES"})
_SIDES: frozenset[str] = frozenset({"buy", "sell"})
_NA_TOKENS: frozenset[str] = frozenset({"", "n/a", "na", "none", "null"})

_CONTRACT_RE = re.compile(r"^(?P<root>MNQ|MES)(?P<month>[FGHJKMNQUVXZ])(?P<yy>\d{2})$")
_IMG_RE = re.compile(r"<img\b[^>]*>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def load_tradesviz_executions(
    path: str | Path,
    *,
    profile: str,
) -> pd.DataFrame:
    """Load a TradesViz *executions* CSV into a ``FillRecord`` frame.

    ``profile`` is required and must be ``tradesviz_executions``. ``commission``
    and ``fees`` are read so a missing column fails closed, then discarded.
    """
    if profile != TRADESVIZ_EXECUTIONS_PROFILE:
        raise JournalIngestError(
            f"unsupported journal profile {profile!r}; "
            f"expected {TRADESVIZ_EXECUTIONS_PROFILE!r} (no autodetect)"
        )

    csv_path = Path(path)
    if not csv_path.is_file():
        raise JournalIngestError(f"TradesViz executions file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise JournalIngestError("TradesViz executions CSV has no header")
        header = tuple(name.strip() for name in reader.fieldnames)
        _require_columns(header)
        raw_rows = list(reader)

    records = [_row_to_record(index, row) for index, row in enumerate(raw_rows)]
    if not records:
        return _empty_frame()

    timestamps = pd.Series([record.timestamp for record in records], dtype="datetime64[ns, UTC]")
    local_ts = timestamps.dt.tz_convert(JOURNAL_EXCHANGE_TZ)
    session_dates = trading_session_date(local_ts, JOURNAL_ETH_START)

    filled: list[FillRecord] = []
    for record, session in zip(records, session_dates, strict=True):
        filled.append(
            FillRecord(
                fill_id=record.fill_id,
                source=record.source,
                source_group_id=record.source_group_id,
                instrument=record.instrument,
                contract_month=record.contract_month,
                contract_year=record.contract_year,
                side=record.side,
                qty=record.qty,
                price=record.price,
                timestamp=record.timestamp,
                session_date=session,
                entry_kind=record.entry_kind,
                tags=record.tags,
                notes_text=record.notes_text,
                declared_stop=record.declared_stop,
                declared_target=record.declared_target,
                flags=record.flags,
            )
        )
    object_columns = (
        "fill_id",
        "source",
        "source_group_id",
        "instrument",
        "contract_month",
        "contract_year",
        "side",
        "qty",
        "price",
        "session_date",
        "entry_kind",
        "tags",
        "notes_text",
        "declared_stop",
        "declared_target",
        "flags",
    )
    frame = pd.DataFrame(index=range(len(filled)))
    for column in object_columns:
        frame[column] = pd.Series([getattr(item, column) for item in filled], dtype="object")
    frame["timestamp"] = pd.Series([item.timestamp for item in filled], dtype="datetime64[ns, UTC]")
    return frame.loc[:, list(FILL_RECORD_COLUMNS)]


def _require_columns(header: tuple[str, ...]) -> None:
    present = set(header)
    missing = [name for name in _REQUIRED_COLUMNS if name not in present]
    if missing:
        raise JournalIngestError(
            "TradesViz executions CSV missing required columns: " + ", ".join(missing)
        )


def _empty_frame() -> pd.DataFrame:
    empty = {column: pd.Series(dtype="object") for column in FILL_RECORD_COLUMNS}
    empty["timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
    return pd.DataFrame(empty, columns=list(FILL_RECORD_COLUMNS))


def _row_to_record(index: int, row: Mapping[str, str | None]) -> FillRecord:
    raw_date = _cell(row, "date")
    timestamp = _parse_timestamp(raw_date, index=index)
    symbol = _cell(row, "symbol")
    instrument, contract_month, contract_year = _parse_symbol(symbol, index=index)
    side = _parse_side(_cell(row, "side"), index=index)
    asset_type = _cell(row, "asset_type").lower()
    entry_kind = ENTRY_KIND_IMPORTED if asset_type == "future" else ENTRY_KIND_MANUAL
    qty, flags = _parse_qty(_cell(row, "quantity"), entry_kind=entry_kind, index=index)
    price = _parse_price(_cell(row, "price"), index=index)
    # Read to fail-closed if absent; never persist (plan §3.1).
    _cell(row, "commission")
    _cell(row, "fees")
    _cell(row, "currency")
    _cell(row, "underlying")
    declared_stop = _parse_optional_float(_cell(row, "stop_loss"))
    declared_target = _parse_optional_float(_cell(row, "profit_target"))
    tags = _parse_tags(_cell(row, "tags"))
    notes_text = strip_notes_html(_cell(row, "notes"))
    source_group_id = _optional_text(_cell(row, "spread_id"))
    fill_id = _fill_id(
        index,
        source_group_id=source_group_id,
        timestamp=timestamp,
        side=side,
        price=price,
        qty=qty,
    )
    # session_date is filled after the Series-shaped trading_session_date call.
    return FillRecord(
        fill_id=fill_id,
        source=SOURCE_TRADESVIZ,
        source_group_id=source_group_id,
        instrument=instrument,
        contract_month=contract_month,
        contract_year=contract_year,
        side=side,
        qty=qty,
        price=price,
        timestamp=timestamp,
        session_date=timestamp.date(),
        entry_kind=entry_kind,
        tags=tags,
        notes_text=notes_text,
        declared_stop=declared_stop,
        declared_target=declared_target,
        flags=flags,
    )


def _fill_id(
    index: int,
    *,
    source_group_id: str | None,
    timestamp: pd.Timestamp,
    side: str,
    price: float,
    qty: int | None,
) -> str:
    group = source_group_id if source_group_id is not None else "-"
    qty_part = "-" if qty is None else str(qty)
    ts = timestamp.tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")
    return f"tv:{index:06d}:{group}:{ts}:{side}:{price}:{qty_part}"


def _cell(row: Mapping[str, str | None], name: str) -> str:
    if name not in row:
        raise JournalIngestError(f"missing column {name!r}")
    value = row[name]
    return "" if value is None else str(value)


def _parse_timestamp(raw: str, *, index: int) -> pd.Timestamp:
    text = raw.strip()
    if not text:
        raise JournalIngestError(f"row {index}: empty date")
    try:
        ts = pd.Timestamp(text)
    except (ValueError, TypeError) as exc:
        raise JournalIngestError(f"row {index}: unparseable date {raw!r}") from exc
    if ts.tzinfo is None:
        raise JournalIngestError(
            f"row {index}: date must carry an explicit UTC offset (got naive {raw!r})"
        )
    return ts.tz_convert("UTC")


def _parse_symbol(raw: str, *, index: int) -> tuple[str, str | None, int | None]:
    symbol = raw.strip().upper()
    if symbol in _KNOWN_ROOTS:
        return symbol, None, None
    match = _CONTRACT_RE.fullmatch(symbol)
    if match is None:
        raise JournalIngestError(f"row {index}: unknown symbol {raw!r}")
    root = match.group("root")
    month = CME_MONTH_CODES[match.group("month")]
    year = 2000 + int(match.group("yy"))
    return root, month, year


def _parse_side(raw: str, *, index: int) -> str:
    side = raw.strip().lower()
    if side not in _SIDES:
        raise JournalIngestError(f"row {index}: side must be buy or sell (got {raw!r})")
    return side


def _parse_qty(raw: str, *, entry_kind: str, index: int) -> tuple[int | None, tuple[str, ...]]:
    text = raw.strip()
    if not text:
        raise JournalIngestError(f"row {index}: empty quantity")
    try:
        value = float(text)
    except ValueError as exc:
        raise JournalIngestError(f"row {index}: unparseable quantity {raw!r}") from exc
    if value == 0.0:
        if entry_kind != ENTRY_KIND_MANUAL:
            raise JournalIngestError(
                f"row {index}: imported fill quantity must be a positive integer"
            )
        return None, (FLAG_MANUAL_NO_QTY,)
    if value < 0 or not value.is_integer():
        raise JournalIngestError(f"row {index}: quantity must be a positive integer (got {raw!r})")
    return int(value), ()


def _parse_price(raw: str, *, index: int) -> float:
    text = raw.strip()
    if not text:
        raise JournalIngestError(f"row {index}: empty price")
    try:
        return float(text)
    except ValueError as exc:
        raise JournalIngestError(f"row {index}: unparseable price {raw!r}") from exc


def _parse_optional_float(raw: str) -> float | None:
    text = raw.strip()
    if text.lower() in _NA_TOKENS:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise JournalIngestError(f"unparseable optional numeric {raw!r}") from exc


def _parse_tags(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _optional_text(raw: str) -> str | None:
    text = raw.strip()
    return text if text else None


def strip_notes_html(raw: str) -> str:
    """Strip HTML to text; each ``<img>`` becomes the literal token ``[image]``."""
    if not raw:
        return ""
    text = _IMG_RE.sub("[image]", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = unescape(text)
    return " ".join(text.split())
