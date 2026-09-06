"""Daily journal ↔ AMP reconciliation (TJ4).

Per ``(session_date, instrument)``: imported-fill multiset, counts, P&S $,
and fee-line total. Costs land on ``reconciled`` days only. Does not join
bars or call ``simulate_trades``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date
from numbers import Integral, Real
from pathlib import Path
import json
import math

import pandas as pd

from thesistester.journal.amp_statement import load_amp_statement, parse_amp_statement_text
from thesistester.journal.pair import pair_journal_trades
from thesistester.journal.schema import (
    DEFAULT_JOURNAL_RISK_TICKS,
    ENTRY_KIND_IMPORTED,
    JOURNAL_PNL_TOLERANCE_USD,
    JOURNAL_POINT_VALUE,
    JOURNAL_STORE_SCHEMA,
    JOURNAL_TICK_SIZE,
    JOURNAL_TRADE_COLUMNS,
    RECON_AMP_MISSING,
    RECON_JOURNAL_MISSING,
    RECON_MULTISET_MISMATCH,
    RECON_PNL_MISMATCH,
    RECON_RECONCILED,
    STATUS_CLOSED,
    TRADESVIZ_EXECUTIONS_PROFILE,
    AmpStatement,
    DayReconcile,
    JournalIngestError,
)
from thesistester.journal.tradesviz import load_tradesviz_executions


def quantize_price(price: float, *, tick_size: float = JOURNAL_TICK_SIZE) -> float:
    """Quantize a fill price to ``tick_size`` (plan §3.0 / §3.4)."""
    if not math.isfinite(price):
        raise JournalIngestError(f"cannot quantize non-finite price {price!r}")
    return round(round(price / tick_size) * tick_size, 10)


def reconcile_journal(
    fills: pd.DataFrame,
    statements: Sequence[AmpStatement],
    *,
    include_manual: bool = False,
    journal_risk_ticks: int = DEFAULT_JOURNAL_RISK_TICKS,
    pnl_tolerance: float = JOURNAL_PNL_TOLERANCE_USD,
) -> tuple[pd.DataFrame, tuple[DayReconcile, ...]]:
    """Pair fills, reconcile each instrument-day, and apply AMP costs.

    ``include_manual``, ``journal_risk_ticks``, and ``pnl_tolerance`` are
    keyword-only. ``include_manual`` is pairing-only; the AMP fill multiset
    and journal gross stay imported-only (plan §3.4). Costs apply only to
    closed imported trades on ``reconciled`` days.
    """
    if not isinstance(include_manual, bool):
        raise JournalIngestError("include_manual must be a bool")
    if (
        isinstance(pnl_tolerance, bool)
        or not isinstance(pnl_tolerance, (int, float))
        or pnl_tolerance < 0
    ):
        raise JournalIngestError(
            f"pnl_tolerance must be a non-negative number (got {pnl_tolerance!r})"
        )
    trades = pair_journal_trades(
        fills,
        include_manual=include_manual,
        journal_risk_ticks=journal_risk_ticks,
    )
    # Plan §3.4: recon fill multiset and journal gross are imported fills only.
    # include_manual is pairing-only and must not leak manuals into AMP recon.
    imported = _imported_fills(fills)
    imported_ids = _imported_fill_ids(imported)
    amp_by_key = _index_statements(statements)
    journal_by_key = _index_journal_fills(imported)
    keys = sorted(set(journal_by_key) | set(amp_by_key))
    days = [
        _reconcile_day(
            key,
            journal_fills=journal_by_key.get(key, ()),
            statement=amp_by_key.get(key),
            trades=trades,
            imported_ids=imported_ids,
            pnl_tolerance=float(pnl_tolerance),
        )
        for key in keys
    ]
    return _apply_costs(trades, days, amp_by_key, imported_ids=imported_ids), tuple(days)


def write_reconcile_artifacts(
    output_dir: str | Path,
    trades: pd.DataFrame,
    days: Sequence[DayReconcile],
) -> dict[str, Path]:
    """Write ``reconcile.json`` + ``journal_trades.parquet``. Not under ``results/studies/``."""
    out = _assert_output_dir(Path(output_dir))
    out.mkdir(parents=True, exist_ok=True)
    recon_path = out / "reconcile.json"
    trades_path = out / "journal_trades.parquet"
    payload = {
        "schema_version": JOURNAL_STORE_SCHEMA,
        "days": [_day_to_json(day) for day in days],
    }
    recon_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _trades_for_parquet(trades).to_parquet(trades_path, index=False)
    return {"reconcile.json": recon_path, "journal_trades.parquet": trades_path}


def load_amp_statement_file(path: str | Path) -> AmpStatement:
    """Load an AMP Daily Statement from a PDF or redacted text extract."""
    stmt_path = Path(path)
    if not stmt_path.is_file():
        raise JournalIngestError(f"AMP statement not found: {stmt_path}")
    if stmt_path.suffix.lower() == ".pdf":
        return load_amp_statement(stmt_path)
    return parse_amp_statement_text(stmt_path.read_text(encoding="utf-8"))


def reconcile_files(
    *,
    executions: str | Path,
    statements: Sequence[str | Path],
    output_dir: str | Path,
    include_manual: bool = False,
    journal_risk_ticks: int = DEFAULT_JOURNAL_RISK_TICKS,
) -> dict[str, Path]:
    """Load sources, reconcile, and write artifacts. All arguments keyword-only."""
    fills = load_tradesviz_executions(executions, profile=TRADESVIZ_EXECUTIONS_PROFILE)
    parsed = tuple(load_amp_statement_file(path) for path in statements)
    trades, days = reconcile_journal(
        fills,
        parsed,
        include_manual=include_manual,
        journal_risk_ticks=journal_risk_ticks,
    )
    return write_reconcile_artifacts(output_dir, trades, days)


def _imported_fills(fills: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(fills, pd.DataFrame):
        raise JournalIngestError("reconcile_journal expects a FillRecord DataFrame")
    if "entry_kind" not in fills.columns:
        raise JournalIngestError("fills frame missing entry_kind")
    return fills.loc[fills["entry_kind"] == ENTRY_KIND_IMPORTED].copy()


def _imported_fill_ids(fills: pd.DataFrame) -> frozenset[str]:
    if fills.empty:
        return frozenset()
    if "fill_id" not in fills.columns:
        raise JournalIngestError("fills frame missing fill_id")
    return frozenset(str(fill_id) for fill_id in fills["fill_id"])


def _index_statements(
    statements: Sequence[AmpStatement],
) -> dict[tuple[date, str], AmpStatement]:
    if isinstance(statements, (str, bytes)) or not isinstance(statements, Sequence):
        raise JournalIngestError("statements must be a sequence of AmpStatement")
    grouped: dict[tuple[date, str], list[AmpStatement]] = defaultdict(list)
    for stmt in statements:
        if not isinstance(stmt, AmpStatement):
            raise JournalIngestError(
                f"statements must contain AmpStatement values (got {type(stmt).__name__})"
            )
        instruments = {fill.instrument for fill in stmt.fills}
        if not instruments:
            raise JournalIngestError("AMP statement has no confirmation fills")
        if len(instruments) != 1:
            raise JournalIngestError(
                "AMP statement mixes instruments "
                + ", ".join(sorted(instruments))
                + f" on {stmt.session_date}"
            )
        grouped[(stmt.session_date, next(iter(instruments)))].append(stmt)
    by_key: dict[tuple[date, str], AmpStatement] = {}
    for key, group in grouped.items():
        if len(group) != 1:
            raise JournalIngestError(f"multiple AMP statements for {key[1]} on {key[0]}")
        by_key[key] = group[0]
    return by_key


def _index_journal_fills(
    fills: pd.DataFrame,
) -> dict[tuple[date, str], tuple[dict[str, object], ...]]:
    groups: dict[tuple[date, str], list[dict[str, object]]] = defaultdict(list)
    for raw in fills.to_dict(orient="records"):
        fill_id = str(raw.get("fill_id", ""))
        _require_positive_int(raw.get("qty"), fill_id=fill_id, field="qty")
        session = _as_date(raw["session_date"])
        instrument = str(raw["instrument"])
        if instrument not in JOURNAL_POINT_VALUE:
            raise JournalIngestError(f"unknown journal instrument {instrument!r}")
        groups[(session, instrument)].append(raw)
    return {key: tuple(rows) for key, rows in groups.items()}


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise JournalIngestError(f"invalid session_date {value!r}")
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise JournalIngestError(f"invalid session_date {value!r}") from exc
    if pd.isna(ts):
        raise JournalIngestError(f"invalid session_date {value!r}")
    return ts.date()


def _require_positive_int(value: object, *, fill_id: str, field: str) -> int:
    if isinstance(value, bool):
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    if isinstance(value, Integral):
        qty = int(value)
    elif isinstance(value, Real) and math.isfinite(float(value)) and float(value).is_integer():
        qty = int(value)
    else:
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    if qty <= 0:
        raise JournalIngestError(f"fill {fill_id!r} {field} must be a positive int (got {value!r})")
    return qty


def _fill_key(price: float, side: str, qty: object, *, fill_id: str = "") -> tuple[float, str, int]:
    side_text = str(side)
    if side_text not in {"buy", "sell"}:
        raise JournalIngestError(f"fill {fill_id!r} side must be buy or sell (got {side!r})")
    return (quantize_price(float(price)), side_text, _require_positive_int(qty, fill_id=fill_id, field="qty"))


def _journal_multiset(rows: Sequence[Mapping[str, object]]) -> Counter[tuple[float, str, int]]:
    return Counter(
        _fill_key(
            float(row["price"]),
            str(row["side"]),
            row["qty"],
            fill_id=str(row.get("fill_id", "")),
        )
        for row in rows
    )


def _amp_multiset(fills: Sequence) -> Counter[tuple[float, str, int]]:
    return Counter(_fill_key(fill.price, fill.side, fill.qty) for fill in fills)


def _closed_gross(
    trades: pd.DataFrame,
    key: tuple[date, str],
    *,
    imported_ids: frozenset[str],
) -> float | None:
    if trades.empty:
        return None
    mask = (
        trades["session_date"].map(_as_date).eq(key[0])
        & trades["instrument"].eq(key[1])
        & trades["status"].eq(STATUS_CLOSED)
        & trades["entry_fill_id"].map(lambda value: str(value) in imported_ids)
    )
    subset = trades.loc[mask]
    if subset.empty:
        return None
    total = float(subset["gross_pnl_currency"].sum())
    if not math.isfinite(total):
        return None
    return total


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _reconcile_day(
    key: tuple[date, str],
    *,
    journal_fills: Sequence[Mapping[str, object]],
    statement: AmpStatement | None,
    trades: pd.DataFrame,
    imported_ids: frozenset[str],
    pnl_tolerance: float,
) -> DayReconcile:
    session, instrument = key
    journal_n = len(journal_fills)
    amp_n = 0 if statement is None else len(statement.fills)
    journal_gross = _closed_gross(trades, key, imported_ids=imported_ids)
    if statement is None:
        return DayReconcile(
            session_date=session,
            instrument=instrument,
            status=RECON_AMP_MISSING,
            journal_fill_count=journal_n,
            amp_fill_count=0,
            journal_gross_usd=journal_gross,
            amp_ps_usd=None,
            fee_total_usd=None,
            day_fees_extra=None,
            note="no AMP statement for this instrument-day",
        )
    fee_total = sum(statement.fee_map().values())
    n_sides = sum(fill.qty for fill in statement.fills)
    expected_fees = sum(statement.per_side_map().values()) * n_sides + statement.day_fees_extra
    if (
        not math.isfinite(fee_total)
        or not math.isfinite(expected_fees)
        or abs(fee_total - expected_fees) > pnl_tolerance
    ):
        raise JournalIngestError(
            f"AMP fee total {fee_total} != schedule×sides+extra {expected_fees} "
            f"on {session} {instrument}"
        )
    if journal_n == 0:
        return DayReconcile(
            session_date=session,
            instrument=instrument,
            status=RECON_JOURNAL_MISSING,
            journal_fill_count=0,
            amp_fill_count=amp_n,
            journal_gross_usd=None,
            amp_ps_usd=statement.ps_usd,
            fee_total_usd=fee_total,
            day_fees_extra=statement.day_fees_extra,
            note="no imported journal fills for this instrument-day",
        )
    if journal_n != amp_n or _journal_multiset(journal_fills) != _amp_multiset(statement.fills):
        return DayReconcile(
            session_date=session,
            instrument=instrument,
            status=RECON_MULTISET_MISMATCH,
            journal_fill_count=journal_n,
            amp_fill_count=amp_n,
            journal_gross_usd=journal_gross,
            amp_ps_usd=statement.ps_usd,
            fee_total_usd=fee_total,
            day_fees_extra=statement.day_fees_extra,
            note="imported fill multiset (price, side, qty) != AMP confirmations",
        )
    ps_usd = _finite_or_none(float(statement.ps_usd))
    if (
        journal_gross is None
        or ps_usd is None
        or abs(journal_gross - ps_usd) > pnl_tolerance
    ):
        return DayReconcile(
            session_date=session,
            instrument=instrument,
            status=RECON_PNL_MISMATCH,
            journal_fill_count=journal_n,
            amp_fill_count=amp_n,
            journal_gross_usd=journal_gross,
            amp_ps_usd=statement.ps_usd,
            fee_total_usd=fee_total,
            day_fees_extra=statement.day_fees_extra,
            note="journal gross $ vs AMP P&S $ exceeds 1 cent",
        )
    return DayReconcile(
        session_date=session,
        instrument=instrument,
        status=RECON_RECONCILED,
        journal_fill_count=journal_n,
        amp_fill_count=amp_n,
        journal_gross_usd=journal_gross,
        amp_ps_usd=statement.ps_usd,
        fee_total_usd=fee_total,
        day_fees_extra=statement.day_fees_extra,
        note="",
    )


def _apply_costs(
    trades: pd.DataFrame,
    days: Sequence[DayReconcile],
    amp_by_key: Mapping[tuple[date, str], AmpStatement],
    *,
    imported_ids: frozenset[str],
) -> pd.DataFrame:
    status_by_key = {(day.session_date, day.instrument): day.status for day in days}
    if trades.empty:
        out = trades.copy()
        out["recon_status"] = pd.Series(dtype="object")
        return out
    records = trades.to_dict(orient="records")
    # Day extras are realized costs. Split them across closed imported trades
    # so leftover opens / manuals cannot dilute Σ net vs AMP fees.
    n_by_key: dict[tuple[date, str], int] = Counter(
        (_as_date(row["session_date"]), str(row["instrument"]))
        for row in records
        if str(row["status"]) == STATUS_CLOSED and str(row["entry_fill_id"]) in imported_ids
    )
    rows: list[dict[str, object]] = []
    for raw in records:
        key = (_as_date(raw["session_date"]), str(raw["instrument"]))
        status = status_by_key.get(key)
        updated = _normalize_trade_record(raw)
        updated["recon_status"] = status
        imported_closed = (
            str(updated["entry_fill_id"]) in imported_ids
            and str(updated["status"]) == STATUS_CLOSED
        )
        if status == RECON_RECONCILED and imported_closed:
            stmt = amp_by_key[key]
            per_side = sum(stmt.per_side_map().values())
            n_day = n_by_key[key]
            allocation = (stmt.day_fees_extra / n_day) if n_day else 0.0
            updated = _cost_row(updated, per_side=per_side, day_fee_allocation=allocation)
        rows.append(updated)
    frame = pd.DataFrame(rows)
    frame["entry_timestamp"] = pd.Series(frame["entry_timestamp"], dtype="datetime64[ns, UTC]")
    frame["exit_timestamp"] = pd.Series(frame["exit_timestamp"], dtype="datetime64[ns, UTC]")
    return frame.loc[:, list(JOURNAL_TRADE_COLUMNS) + ["recon_status"]]


def _normalize_trade_record(raw: Mapping[str, object]) -> dict[str, object]:
    """Keep JournalTrade object contracts after DataFrame round-trip."""
    updated = dict(raw)
    updated["session_date"] = _as_date(raw["session_date"])
    tags = raw.get("tags")
    if tags is None or (isinstance(tags, float) and pd.isna(tags)):
        updated["tags"] = ()
    else:
        updated["tags"] = tuple(tags)
    return updated


def _cost_row(
    row: dict[str, object],
    *,
    per_side: float,
    day_fee_allocation: float,
) -> dict[str, object]:
    qty = _require_positive_int(row["qty"], fill_id=str(row.get("trade_id", "")), field="qty")
    instrument = str(row["instrument"])
    if instrument not in JOURNAL_POINT_VALUE:
        raise JournalIngestError(f"unknown journal instrument {instrument!r}")
    point_value = JOURNAL_POINT_VALUE[instrument]
    tick_value = JOURNAL_TICK_SIZE * point_value
    status = str(row["status"])
    commission = per_side * 2 * qty if status == STATUS_CLOSED else None
    gross = row["gross_pnl_currency"]
    row["commission_cost"] = commission
    row["day_fee_allocation"] = day_fee_allocation if commission is not None else None
    if commission is None or gross is None or (isinstance(gross, float) and pd.isna(gross)):
        return row
    gross_f = float(gross)
    if not math.isfinite(gross_f) or not math.isfinite(commission) or not math.isfinite(day_fee_allocation):
        return row
    net = gross_f - commission - day_fee_allocation
    risk = int(row["journal_risk_ticks"]) * tick_value * qty
    row["net_pnl_currency"] = net
    row["fee_ticks"] = commission / tick_value
    row["net_ticks"] = net / tick_value
    if risk > 0:
        row["r_multiple"] = net / risk
    stop = row.get("stop_price")
    if stop is not None and not (isinstance(stop, float) and pd.isna(stop)):
        distance = abs(float(row["entry_price"]) - float(stop))
        if distance > 0:
            row["r_multiple_declared"] = net / (distance * point_value * qty)
    return row


def _day_to_json(day: DayReconcile) -> dict[str, object]:
    payload = asdict(day)
    payload["session_date"] = day.session_date.isoformat()
    return payload


def _trades_for_parquet(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    if "tags" in frame.columns:
        frame["tags"] = frame["tags"].map(lambda tags: list(tags) if tags is not None else [])
    if "session_date" in frame.columns:
        frame["session_date"] = frame["session_date"].map(lambda value: _as_date(value).isoformat())
    return frame


def _assert_output_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    for index, part in enumerate(parts[:-1]):
        if part == "results" and parts[index + 1] == "studies":
            raise JournalIngestError("journal reconcile must not write into results/studies/")
    return resolved
