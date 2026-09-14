"""Post-trade journal ingest (TJ series + JS1 zones + JS2 triggers).

Additive package. Does not call ``simulate_trades`` or ``compute_all_levels``.
TJ1 ships the TradesViz executions loader. TJ2 adds the AMP statement parser.
TJ3 pairs fills into ``JournalTrade``. TJ4 reconciles AMP per instrument-day.
TJ5 joins trades to the 15s / derived-1m clock (ticks when present).
TJ6 attributes every entry bar and verifies level-class tags.
TJ7 replays entries under fixed brackets, a direction-shuffle null, and declared rules.
TJ8 matches a named cell and builds a forward ledger.
TJ9 builds the Q1–Q8 report and page 17 (read-only).
JS1 attributes engine confluence zones on the previous completed 1m bar.
JS2 infers engine trigger labels on that 1m bar and a 15s_proxy.

C-9 (QI-08-02): schema is eager; JS/TJ helpers lazy-export so
``import thesistester.journal`` does not load ``engine.backtest`` or bind
``simulate_trades``. Submodule attribute access stays lazy. Call-ban
unchanged.
"""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Any

from thesistester.journal.schema import (
    AMP_KNOWN_FEE_NAMES,
    AMP_STANDARD_FEE_NAMES,
    DEFAULT_JOURNAL_RISK_TICKS,
    DEFAULT_LEVEL_TOLERANCE_TICKS,
    DEFAULT_TAG_TOLERANCE_TICKS,
    DEFAULT_ZONE_MAX_CONFLUENCES,
    DEFAULT_ZONE_MIN_CONFLUENCES,
    DEFAULT_ZONE_TOLERANCE_TICKS,
    FILL_RECORD_COLUMNS,
    JOURNAL_TRADE_COLUMNS,
    RECON_RECONCILED,
    REPORT_HONESTY,
    REPORT_MIN_N,
    TRIGGERS_HONESTY,
    TRADESVIZ_EXECUTIONS_PROFILE,
    ZONES_HONESTY,
    AmpFill,
    AmpStatement,
    DayReconcile,
    FillRecord,
    JournalIngestError,
    JournalTrade,
)

__all__ = [
    "AMP_KNOWN_FEE_NAMES",
    "AMP_STANDARD_FEE_NAMES",
    "DEFAULT_JOURNAL_RISK_TICKS",
    "DEFAULT_LEVEL_TOLERANCE_TICKS",
    "DEFAULT_TAG_TOLERANCE_TICKS",
    "DEFAULT_ZONE_MAX_CONFLUENCES",
    "DEFAULT_ZONE_MIN_CONFLUENCES",
    "DEFAULT_ZONE_TOLERANCE_TICKS",
    "REPORT_HONESTY",
    "REPORT_MIN_N",
    "TRIGGERS_HONESTY",
    "ZONES_HONESTY",
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
    "attribute_journal_zones",
    "canonical_zone_params_hash",
    "load_zone_params",
    "previous_completed_1m_open",
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
    "infer_journal_triggers",
    "trigger_files",
    "write_trigger_artifacts",
    "write_zone_artifacts",
    "zone_files",
]

_LAZY_ATTR_TO_MODULE: dict[str, str] = {
    name: module
    for module, names in {
        ".amp_statement": (
            "extract_amp_pdf_text",
            "load_amp_statement",
            "parse_amp_statement_text",
        ),
        ".counterfactual": (
            "counterfactual_files",
            "direction_shuffle_null",
            "replay_journal_brackets",
            "write_counterfactual_artifacts",
        ),
        ".join": ("join_journal_bars",),
        ".ledger": ("build_forward_ledger", "load_live_declarations"),
        ".levels": (
            "attribute_files",
            "attribute_journal_trades",
            "write_attribution_artifacts",
        ),
        ".match": (
            "NamedCell",
            "load_named_cell",
            "match_files",
            "match_journal_to_cell",
            "write_match_artifacts",
        ),
        ".pair": ("pair_journal_trades",),
        ".reconcile": (
            "quantize_price",
            "reconcile_files",
            "reconcile_journal",
            "write_reconcile_artifacts",
        ),
        ".report": (
            "JournalArtifacts",
            "JournalReport",
            "build_journal_report",
            "journal_store_dir",
            "load_journal_artifacts",
            "report_files",
            "report_from_artifacts",
            "write_report_artifacts",
        ),
        ".rules": (
            "JournalRule",
            "apply_journal_rules",
            "load_journal_rules",
            "parse_journal_rule",
        ),
        ".tags": (
            "TagMapping",
            "load_tag_map",
            "mapped_engine_tokens",
            "resolve_tag",
        ),
        ".tradesviz": ("load_tradesviz_executions",),
        ".triggers": (
            "infer_journal_triggers",
            "trigger_files",
            "write_trigger_artifacts",
        ),
        ".zones": (
            "attribute_journal_zones",
            "canonical_zone_params_hash",
            "load_zone_params",
            "previous_completed_1m_open",
            "write_zone_artifacts",
            "zone_files",
        ),
    }.items()
    for name in names
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_ATTR_TO_MODULE.get(name)
    if module_name is not None:
        value = getattr(import_module(module_name, __name__), name)
        globals()[name] = value
        return value
    # PEP 562: fall back to real submodules so ``journal.triggers`` stays
    # valid. Guard the name so getattr(journal, "..engine") cannot walk up.
    if name.isidentifier():
        spec = find_spec(f"{__name__}.{name}")
        if spec is not None:
            value = import_module(f"{__name__}.{name}")
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
