"""Journal typed records (TJ1 ``FillRecord``, TJ2 ``AmpStatement``, TJ3 ``JournalTrade``).

Later TJ milestones add recon artifacts here. This module does not pair
fills, call ``simulate_trades``, or compute AMP fees.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from typing import Final, Literal, Mapping

import pandas as pd

TRADESVIZ_EXECUTIONS_PROFILE: Final[str] = "tradesviz_executions"
JOURNAL_ETH_START: Final[str] = "18:00"
JOURNAL_EXCHANGE_TZ: Final[str] = "America/New_York"

# CME month codes (locked TJ1 symbol table). Values are the three-letter month.
CME_MONTH_CODES: Final[dict[str, str]] = {
    "F": "JAN",
    "G": "FEB",
    "H": "MAR",
    "J": "APR",
    "K": "MAY",
    "M": "JUN",
    "N": "JUL",
    "Q": "AUG",
    "U": "SEP",
    "V": "OCT",
    "X": "NOV",
    "Z": "DEC",
}

SOURCE_TRADESVIZ: Final[str] = "tradesviz"
ENTRY_KIND_IMPORTED: Final[str] = "imported"
ENTRY_KIND_MANUAL: Final[str] = "manual"
FLAG_MANUAL_NO_QTY: Final[str] = "manual_no_qty"
PAIR_METHOD_SPREAD: Final[str] = "spread_id"
PAIR_METHOD_FIFO: Final[str] = "fifo_fallback"
STATUS_CLOSED: Final[str] = "closed"
STATUS_OPEN: Final[str] = "open"
DEFAULT_JOURNAL_RISK_TICKS: Final[int] = 10
JOURNAL_TICK_SIZE: Final[float] = 0.25
JOURNAL_POINT_VALUE: Final[dict[str, float]] = {"MNQ": 2.0, "MES": 5.0}


class JournalIngestError(ValueError):
    """Raised when a journal source file cannot be ingested (fail-closed)."""


@dataclass(frozen=True)
class FillRecord:
    """One TradesViz execution row after TJ1 normalization.

    ``commission`` / ``fees`` are intentionally absent — they are read from the
    CSV and discarded (TradesViz is not the cost source; AMP is, TJ2).
    """

    fill_id: str
    source: Literal["tradesviz"]
    source_group_id: str | None
    instrument: str
    contract_month: str | None
    contract_year: int | None
    side: Literal["buy", "sell"]
    qty: int | None
    price: float
    timestamp: pd.Timestamp
    session_date: date
    entry_kind: Literal["imported", "manual"]
    tags: tuple[str, ...]
    notes_text: str
    declared_stop: float | None
    declared_target: float | None
    flags: tuple[str, ...]


FILL_RECORD_COLUMNS: Final[tuple[str, ...]] = tuple(f.name for f in fields(FillRecord))

# Locked AMP fee names (plan §3.2). Values are title-case as stored.
AMP_STANDARD_FEE_NAMES: Final[tuple[str, ...]] = (
    "Exchange",
    "NFA",
    "Clearing Client",
    "Rithmic TRF",
    "Commission",
)
AMP_EXTRA_FEE_NAMES: Final[tuple[str, ...]] = ("Liquidation Fee",)
AMP_KNOWN_FEE_NAMES: Final[frozenset[str]] = frozenset(AMP_STANDARD_FEE_NAMES + AMP_EXTRA_FEE_NAMES)


@dataclass(frozen=True)
class AmpFill:
    """One AMP confirmation or P&S row. Not a journal trade."""

    fcm_number: str
    session_date: date
    market: str
    instrument: str
    contract_month: str
    contract_year: int
    side: Literal["buy", "sell"]
    qty: int
    price: float


@dataclass(frozen=True)
class AmpStatement:
    """One AMP Daily Statement after TJ2 parse.

    ``fills`` come from Trades Confirmations only. ``ps_pairs`` / ``ps_usd``
    are the Purchase & Sale section (recon only). ``per_side_schedule`` is
    the five standard fee lines divided by confirmation sides; ``Liquidation
    Fee`` stays in ``day_fees_extra``.
    """

    session_date: date
    fills: tuple[AmpFill, ...]
    ps_pairs: tuple[AmpFill, ...]
    ps_usd: float
    average_long: float
    average_short: float
    fee_lines: tuple[tuple[str, float], ...]
    per_side_schedule: tuple[tuple[str, float], ...]
    day_fees_extra: float
    currency: str = "USD"

    def fee_map(self) -> Mapping[str, float]:
        return dict(self.fee_lines)

    def per_side_map(self) -> Mapping[str, float]:
        return dict(self.per_side_schedule)


@dataclass(frozen=True)
class JournalTrade:
    """One paired journal round-trip (or leftover open lot) after TJ3.

    ``commission_cost`` / ``day_fee_allocation`` stay null until TJ4. AMP P&S
    is not a pairing source. ``r_multiple`` uses ``journal_risk_ticks``
    (default 10) × tick × point value × **qty**; ``r_multiple_declared`` is
    emitted only when ``declared_stop`` is present.
    """

    trade_id: str
    source_group_id: str | None
    pair_method: Literal["spread_id", "fifo_fallback"]
    lot_seq: int
    direction: Literal["long", "short"]
    instrument: str
    contract_month: str | None
    contract_year: int | None
    session_date: date
    qty: int
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp | None
    entry_price: float
    exit_price: float | None
    entry_fill_id: str
    exit_fill_id: str | None
    gross_pnl_points: float | None
    gross_pnl_currency: float | None
    commission_cost: float | None
    slippage_cost: float | None
    day_fee_allocation: float | None
    net_pnl_currency: float | None
    r_multiple: float | None
    r_multiple_declared: float | None
    journal_risk_ticks: int
    fee_ticks: float | None
    net_ticks: float | None
    hold_seconds: float | None
    bars_held: int | None
    mae_points: float | None
    mfe_points: float | None
    stop_price: float | None
    target_price: float | None
    tags: tuple[str, ...]
    notes_text: str
    status: Literal["closed", "open"]
    signal_id: str | None
    trigger: str | None


JOURNAL_TRADE_COLUMNS: Final[tuple[str, ...]] = tuple(f.name for f in fields(JournalTrade))
