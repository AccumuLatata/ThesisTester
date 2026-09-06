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
    keyword-only. Costs are applied only on ``reconciled`` days.
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
    imported = _imported_fills(fills, include_manual=include_manual)
    amp_by_key = _index_statements(statements)
    journal_by_key = _index_journal_fills(imported)
    keys = sorted(set(journal_by_key) | set(amp_by_key))
    days = [
        _reconcile_day(
            key,
            journal_fills=journal_by_key.get(key, ()),
            statement=amp_by_key.get(key),
            trades=trades,
            pnl_tolerance=float(pnl_tolerance),
        )
        for key in keys
    ]
    return _apply_costs(trades, days, amp_by_key), tuple(days)


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


def _imported_fills(fills: pd.DataFrame, *, include_manual: bool) -> pd.DataFrame:
    if "entry_kind" not in fills.columns:
        raise JournalIngestError("fills frame missing entry_kind")
    if include_manual:
        return fills
    return fills.loc[fills["entry_kind"] == ENTRY_KIND_IMPORTED].copy()


def _index_statements(
    statements: Sequence[AmpStatement],
) -> dict[tuple[date, str], AmpStatement]:
    grouped: dict[tuple[date, str], list[AmpStatement]] = defaultdict(list)
    for stmt in statements:
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
        qty = raw.get("qty")
        if qty is None or (isinstance(qty, float) and pd.isna(qty)):
            continue
        session = _as_date(raw["session_date"])
        instrument = str(raw["instrument"])
        groups[(session, instrument)].append(raw)
    return {key: tuple(rows) for key, rows in groups.items()}


def _as_date(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    return date.fromisoformat(str(value))


def _fill_key(price: float, side: str, qty: int) -> tuple[float, str, int]:
    return (quantize_price(float(price)), str(side), int(qty))


def _journal_multiset(rows: Sequence[Mapping[str, object]]) -> Counter[tuple[float, str, int]]:
    return Counter(
        _fill_key(float(row["price"]), str(row["side"]), int(row["qty"])) for row in rows
    )


def _amp_multiset(fills: Sequence) -> Counter[tuple[float, str, int]]:
    return Counter(_fill_key(fill.price, fill.side, fill.qty) for fill in fills)


def _closed_gross(trades: pd.DataFrame, key: tuple[date, str]) -> float | None:
    if trades.empty:
        return None
    mask = (
        trades["session_date"].map(_as_date).eq(key[0])
        & trades["instrument"].eq(key[1])
        & trades["status"].eq(STATUS_CLOSED)
    )
    subset = trades.loc[mask]
    if subset.empty:
        return None
    return float(subset["gross_pnl_currency"].sum())


def _reconcile_day(
    key: tuple[date, str],
    *,
    journal_fills: Sequence[Mapping[str, object]],
    statement: AmpStatement | None,
    trades: pd.DataFrame,
    pnl_tolerance: float,
) -> DayReconcile:
    session, instrument = key
    journal_n = len(journal_fills)
    amp_n = 0 if statement is None else len(statement.fills)
    journal_gross = _closed_gross(trades, key)
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
    if abs(fee_total - expected_fees) > pnl_tolerance:
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
    if journal_gross is None or abs(journal_gross - statement.ps_usd) > pnl_tolerance:
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
) -> pd.DataFrame:
    status_by_key = {(day.session_date, day.instrument): day.status for day in days}
    if trades.empty:
        out = trades.copy()
        out["recon_status"] = pd.Series(dtype="object")
        return out
    records = trades.to_dict(orient="records")
    n_by_key: dict[tuple[date, str], int] = Counter(
        (_as_date(row["session_date"]), str(row["instrument"])) for row in records
    )
    rows: list[dict[str, object]] = []
    for raw in records:
        key = (_as_date(raw["session_date"]), str(raw["instrument"]))
        status = status_by_key.get(key)
        updated = dict(raw)
        updated["recon_status"] = status
        if status == RECON_RECONCILED:
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


def _cost_row(
    row: dict[str, object],
    *,
    per_side: float,
    day_fee_allocation: float,
) -> dict[str, object]:
    qty = int(row["qty"])
    instrument = str(row["instrument"])
    point_value = JOURNAL_POINT_VALUE[instrument]
    tick_value = JOURNAL_TICK_SIZE * point_value
    status = str(row["status"])
    commission = per_side * 2 * qty if status == STATUS_CLOSED else None
    gross = row["gross_pnl_currency"]
    row["commission_cost"] = commission
    row["day_fee_allocation"] = day_fee_allocation
    if commission is None or gross is None or (isinstance(gross, float) and pd.isna(gross)):
        return row
    net = float(gross) - commission - day_fee_allocation
    risk = int(row["journal_risk_ticks"]) * tick_value * qty
    row["net_pnl_currency"] = net
    row["fee_ticks"] = commission / tick_value
    row["net_ticks"] = net / tick_value
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
