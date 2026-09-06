"""Journal typed records (TJ1: ``FillRecord`` only).

Later TJ milestones add ``JournalTrade`` / recon artifacts here. This module
does not pair fills, compute P&L, or call the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from typing import Final, Literal

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
