"""Journal typed records (TJ1–TJ6).

Does not call ``simulate_trades`` or ``compute_all_levels``.
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
JOURNAL_PNL_TOLERANCE_USD: Final[float] = 0.01
JOURNAL_STORE_SCHEMA: Final[str] = "journal/v1"
RECON_RECONCILED: Final[str] = "reconciled"
RECON_JOURNAL_MISSING: Final[str] = "journal_missing"
RECON_AMP_MISSING: Final[str] = "amp_missing"
RECON_MULTISET_MISMATCH: Final[str] = "multiset_mismatch"
RECON_PNL_MISMATCH: Final[str] = "pnl_mismatch"
RECON_STATUSES: Final[frozenset[str]] = frozenset(
    {
        RECON_RECONCILED,
        RECON_JOURNAL_MISSING,
        RECON_AMP_MISSING,
        RECON_MULTISET_MISMATCH,
        RECON_PNL_MISMATCH,
    }
)
JOIN_RESOLUTION_15S: Final[str] = "15s"
JOIN_RESOLUTION_TICK: Final[str] = "tick"
JOIN_RESOLUTIONS: Final[frozenset[str]] = frozenset({JOIN_RESOLUTION_15S, JOIN_RESOLUTION_TICK})
FLAG_MISSING_BAR: Final[str] = "missing_bar"
FLAG_PRICE_OUTSIDE_BAR: Final[str] = "price_outside_bar"
FLAG_EXCURSION_UNAVAILABLE: Final[str] = "excursion_unavailable"
FLAG_ROLL_MISMATCH: Final[str] = "roll_mismatch"
JOIN_FLAGS: Final[frozenset[str]] = frozenset(
    {
        FLAG_MISSING_BAR,
        FLAG_PRICE_OUTSIDE_BAR,
        FLAG_EXCURSION_UNAVAILABLE,
        FLAG_ROLL_MISMATCH,
    }
)
JOIN_BAR_SECONDS: Final[int] = 15
JOIN_PARENT_MINUTES: Final[int] = 1
JOIN_OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "resolution",
    "entry_bar_open",
    "exit_bar_open",
    "parent_1m_ts",
    "join_flags",
)

# --- tag classes / attribution (TJ6) ---
TAG_CLASS_LEVEL: Final[str] = "level"
TAG_CLASS_CONTEXT: Final[str] = "context"
TAG_CLASS_CONFIRM: Final[str] = "confirm"
TAG_CLASS_UNMAPPED: Final[str] = "unmapped"
TAG_CLASSES: Final[frozenset[str]] = frozenset(
    {TAG_CLASS_LEVEL, TAG_CLASS_CONTEXT, TAG_CLASS_CONFIRM, TAG_CLASS_UNMAPPED}
)
LEVEL_CONTEXT_AT_LEVEL: Final[str] = "at_level"
LEVEL_CONTEXT_BETWEEN: Final[str] = "between_levels"
LEVEL_CONTEXT_NO_FRAME: Final[str] = "no_frame"
LEVEL_CONTEXTS: Final[frozenset[str]] = frozenset(
    {LEVEL_CONTEXT_AT_LEVEL, LEVEL_CONTEXT_BETWEEN, LEVEL_CONTEXT_NO_FRAME}
)
TAG_ALIGN_ALL: Final[str] = "all_aligned"
TAG_ALIGN_PARTIAL: Final[str] = "partial"
TAG_ALIGN_NONE: Final[str] = "none_aligned"
TAG_ALIGN_UNVERIFIABLE: Final[str] = "unverifiable"
TAG_ALIGNMENTS: Final[frozenset[str]] = frozenset(
    {TAG_ALIGN_ALL, TAG_ALIGN_PARTIAL, TAG_ALIGN_NONE, TAG_ALIGN_UNVERIFIABLE}
)
DEFAULT_LEVEL_TOLERANCE_TICKS: Final[float] = 10.0
DEFAULT_TAG_TOLERANCE_TICKS: Final[float] = 10.0
ATTRIBUTION_OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "levels_within_tolerance",
    "nearest_level_token",
    "nearest_level_distance_ticks",
    "level_context",
    "tag_alignment",
    "intent_mismatch",
    "unmapped_tags",
    "tag_verifications",
)


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

    ``commission_cost`` / ``day_fee_allocation`` are filled by TJ4 on
    ``reconciled`` days. AMP P&S is not a pairing source. ``r_multiple`` uses
    ``journal_risk_ticks`` (default 10) × tick × point value × **qty**;
    ``r_multiple_declared`` is emitted only when ``declared_stop`` is present.
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


@dataclass(frozen=True)
class DayReconcile:
    """One ``(session_date, instrument)`` recon row (TJ4)."""

    session_date: date
    instrument: str
    status: Literal[
        "reconciled",
        "journal_missing",
        "amp_missing",
        "multiset_mismatch",
        "pnl_mismatch",
    ]
    journal_fill_count: int
    amp_fill_count: int
    journal_gross_usd: float | None
    amp_ps_usd: float | None
    fee_total_usd: float | None
    day_fees_extra: float | None
    note: str = ""


DAY_RECONCILE_COLUMNS: Final[tuple[str, ...]] = tuple(f.name for f in fields(DayReconcile))
