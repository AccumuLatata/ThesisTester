"""Post-trade journal ingest (TJ series).

Additive package. Does not call ``simulate_trades`` or ``compute_all_levels``.
TJ1 ships the TradesViz executions loader. TJ2 adds the AMP statement parser.
TJ3 pairs fills into ``JournalTrade``. TJ4 reconciles AMP per instrument-day.
TJ5 joins trades to the 15s / derived-1m clock (ticks when present).
TJ6 attributes every entry bar and verifies level-class tags.
TJ7 replays entries under fixed brackets, a direction-shuffle null, and declared rules.
TJ8 matches a named cell and builds a forward ledger.
TJ9 builds the Q1–Q8 report and page 17 (read-only).
"""

from __future__ import annotations

from thesistester.journal.amp_statement import (
    extract_amp_pdf_text,
    load_amp_statement,
    parse_amp_statement_text,
)
from thesistester.journal.counterfactual import (
    counterfactual_files,
    direction_shuffle_null,
    replay_journal_brackets,
    write_counterfactual_artifacts,
)
from thesistester.journal.join import join_journal_bars
from thesistester.journal.ledger import build_forward_ledger, load_live_declarations
from thesistester.journal.levels import (
    attribute_files,
    attribute_journal_trades,
    write_attribution_artifacts,
)
from thesistester.journal.match import (
    NamedCell,
    load_named_cell,
    match_files,
    match_journal_to_cell,
    write_match_artifacts,
)
from thesistester.journal.pair import pair_journal_trades
from thesistester.journal.reconcile import (
    quantize_price,
    reconcile_files,
    reconcile_journal,
    write_reconcile_artifacts,
)
from thesistester.journal.report import (
    JournalArtifacts,
    JournalReport,
    build_journal_report,
    journal_store_dir,
    load_journal_artifacts,
    report_files,
    report_from_artifacts,
    write_report_artifacts,
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
    REPORT_HONESTY,
    REPORT_MIN_N,
    TRADESVIZ_EXECUTIONS_PROFILE,
    AmpFill,
    AmpStatement,
    DayReconcile,
    FillRecord,
    JournalIngestError,
    JournalTrade,
)
from thesistester.journal.rules import (
    JournalRule,
    apply_journal_rules,
    load_journal_rules,
    parse_journal_rule,
)
from thesistester.journal.tags import TagMapping, load_tag_map, mapped_engine_tokens, resolve_tag
from thesistester.journal.tradesviz import load_tradesviz_executions

__all__ = [
    "AMP_KNOWN_FEE_NAMES",
    "AMP_STANDARD_FEE_NAMES",
    "DEFAULT_JOURNAL_RISK_TICKS",
    "DEFAULT_LEVEL_TOLERANCE_TICKS",
    "DEFAULT_TAG_TOLERANCE_TICKS",
    "REPORT_HONESTY",
    "REPORT_MIN_N",
    "FILL_RECORD_COLUMNS",
    "JOURNAL_TRADE_COLUMNS",
    "RECON_RECONCILED",
    "AmpFill",
    "AmpStatement",
    "DayReconcile",
    "JournalArtifacts",
    "JournalIngestError",
    "JournalReport",
    "JournalRule",
    "JournalTrade",
    "TRADESVIZ_EXECUTIONS_PROFILE",
    "FillRecord",
    "TagMapping",
    "apply_journal_rules",
    "NamedCell",
    "attribute_files",
    "attribute_journal_trades",
    "build_forward_ledger",
    "build_journal_report",
    "journal_store_dir",
    "load_journal_artifacts",
    "report_files",
    "report_from_artifacts",
    "write_report_artifacts",
    "counterfactual_files",
    "direction_shuffle_null",
    "extract_amp_pdf_text",
    "load_amp_statement",
    "join_journal_bars",
    "load_journal_rules",
    "load_live_declarations",
    "load_named_cell",
    "load_tag_map",
    "load_tradesviz_executions",
    "mapped_engine_tokens",
    "match_files",
    "match_journal_to_cell",
    "pair_journal_trades",
    "parse_amp_statement_text",
    "parse_journal_rule",
    "quantize_price",
    "reconcile_files",
    "reconcile_journal",
    "replay_journal_brackets",
    "resolve_tag",
    "write_attribution_artifacts",
    "write_counterfactual_artifacts",
    "write_match_artifacts",
    "write_reconcile_artifacts",
]
