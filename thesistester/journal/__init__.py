"""Post-trade journal ingest (TJ series).

Additive package. Does not call ``simulate_trades`` or ``compute_all_levels``.
TJ1 ships the TradesViz executions loader. TJ2 adds the AMP statement parser.
"""

from __future__ import annotations

from thesistester.journal.amp_statement import (
    extract_amp_pdf_text,
    load_amp_statement,
    parse_amp_statement_text,
)
from thesistester.journal.schema import (
    AMP_KNOWN_FEE_NAMES,
    AMP_STANDARD_FEE_NAMES,
    FILL_RECORD_COLUMNS,
    AmpFill,
    AmpStatement,
    JournalIngestError,
    TRADESVIZ_EXECUTIONS_PROFILE,
    FillRecord,
)
from thesistester.journal.tradesviz import load_tradesviz_executions

__all__ = [
    "AMP_KNOWN_FEE_NAMES",
    "AMP_STANDARD_FEE_NAMES",
    "FILL_RECORD_COLUMNS",
    "AmpFill",
    "AmpStatement",
    "JournalIngestError",
    "TRADESVIZ_EXECUTIONS_PROFILE",
    "FillRecord",
    "extract_amp_pdf_text",
    "load_amp_statement",
    "load_tradesviz_executions",
    "parse_amp_statement_text",
]
