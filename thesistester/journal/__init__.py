"""Post-trade journal ingest (TJ series).

Additive package. Does not call ``simulate_trades`` or ``compute_all_levels``.
TJ1 ships the TradesViz executions loader. TJ2 adds the AMP statement parser.
TJ3 pairs fills into ``JournalTrade``. TJ4 reconciles AMP per instrument-day.
TJ5 joins trades to the 15s / derived-1m clock (ticks when present).
TJ6 attributes every entry bar and verifies level-class tags.
"""

from __future__ import annotations

from thesistester.journal.amp_statement import (
    extract_amp_pdf_text,
    load_amp_statement,
    parse_amp_statement_text,
)
from thesistester.journal.join import join_journal_bars
from thesistester.journal.levels import (
    attribute_files,
    attribute_journal_trades,
    write_attribution_artifacts,
)
from thesistester.journal.pair import pair_journal_trades
from thesistester.journal.reconcile import (
    quantize_price,
    reconcile_files,
    reconcile_journal,
    write_reconcile_artifacts,
)
from thesistester.journal.schema import (
    AMP_KNOWN_FEE_NAMES,
    AMP_STANDARD_FEE_NAMES,
    DEFAULT_JOURNAL_RISK_TICKS,
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    FILL_RECORD_COLUMNS,
    JOURNAL_TRADE_COLUMNS,
    RECON_RECONCILED,
    AmpFill,
    AmpStatement,
    DayReconcile,
    JournalIngestError,
    JournalTrade,
    TRADESVIZ_EXECUTIONS_PROFILE,
    FillRecord,
)
from thesistester.journal.tags import TagMapping, load_tag_map, mapped_engine_tokens, resolve_tag
from thesistester.journal.tradesviz import load_tradesviz_executions

__all__ = [
    "AMP_KNOWN_FEE_NAMES",
    "AMP_STANDARD_FEE_NAMES",
    "DEFAULT_JOURNAL_RISK_TICKS",
    "DEFAULT_LEVEL_TOLERANCE_TICKS",
    "DEFAULT_TAG_TOLERANCE_TICKS",
    "FILL_RECORD_COLUMNS",
    "JOURNAL_TRADE_COLUMNS",
    "RECON_RECONCILED",
    "AmpFill",
    "AmpStatement",
    "DayReconcile",
    "JournalIngestError",
    "JournalTrade",
    "TRADESVIZ_EXECUTIONS_PROFILE",
    "FillRecord",
    "TagMapping",
    "attribute_files",
    "attribute_journal_trades",
    "extract_amp_pdf_text",
    "load_amp_statement",
    "join_journal_bars",
    "load_tag_map",
    "load_tradesviz_executions",
    "mapped_engine_tokens",
    "pair_journal_trades",
    "parse_amp_statement_text",
    "quantize_price",
    "reconcile_files",
    "reconcile_journal",
    "resolve_tag",
    "write_attribution_artifacts",
    "write_reconcile_artifacts",
]
