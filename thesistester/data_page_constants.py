"""Data-page session/widget keys and shared literals (QR D-5 / QI-01-01).

Streamlit-free. Values match ``pages/1_Data.py`` assignments (H10 codes stay
assigned on the page so AST locks still bind there).
"""

from __future__ import annotations

import pandas as pd

FLASH_MESSAGE_KEY = "_data_local_store_message"
PENDING_INSTRUMENT_SELECTOR_KEY = "_pending_data_instrument_selector"
PENDING_SOURCE_TZ_SELECTOR_KEY = "_pending_data_source_timezone_selector"
UPLOAD_INGESTION_MODE_EXPLICIT_KEY = "_upload_ingestion_mode_explicit"
INGESTION_PROVENANCE_KEY = "ingestion_provenance"
DERIVED_PARENT_DIAGNOSTICS_KEY = "derived_parent_diagnostics"
SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY = "_subtimeframe_upload_signature"
SUBTIMEFRAME_UPLOADER_NONCE_KEY = "_subtimeframe_uploader_nonce"
PRIMARY_CSV_UPLOADER_NONCE_KEY = "_primary_csv_uploader_nonce"
TICK_PATHS_KEY = "tick_paths"
TICK_UPLOADER_NONCE_KEY = "_tick_uploader_nonce"
TICK_UPLOAD_SIGNATURE_KEY = "_tick_upload_signature"
TICK_ROW_COUNT_KEY = "tick_row_count"
TICK_SESSION_COUNT_KEY = "tick_session_count"
TICK_WARNINGS_KEY = "tick_attach_warnings"
TICK_PATHS_TEXT_KEY = "_tick_paths_text"
LOAD_SAMPLE_REQUESTED_KEY = "_load_sample_data_requested"
SUBTIMEFRAME_FALLBACK_BARS_KEY = "subtimeframe_fallback_parent_bars"
SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY = "_subtimeframe_compatibility_report"
SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY = "_subtimeframe_compatibility_signature"
SUBTIMEFRAME_DUPLICATE_REPORT_KEY = "_subtimeframe_duplicate_report"
SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY = "_subtimeframe_duplicate_signature"
SUBTIMEFRAME_DUPLICATE_SOURCE_KEY = "_subtimeframe_duplicate_source"
SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY = "subtimeframe_duplicate_resolution"
SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY = "_subtimeframe_diagnostic_data"
LEGACY_SUBTIMEFRAME_EXPANDER_TITLE = "Legacy dual-upload (optional)"
FATAL_OHLCV_CODES = frozenset(
    {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
)


class SubtimeframeCompatibilityError(ValueError):
    """Lower CSV cannot be replayed; retain its read-only diagnostic report."""

    def __init__(self, message: str, report: pd.DataFrame) -> None:
        super().__init__(message)
        self.report = report


class SubtimeframeDuplicateTimestampError(ValueError):
    """Lower CSV contains duplicate bar-open timestamps."""

    def __init__(self, message: str, report: pd.DataFrame, source: pd.DataFrame) -> None:
        super().__init__(message)
        self.report = report
        self.source = source
