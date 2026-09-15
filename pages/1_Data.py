"""Phase 1 — Data ingest UI.

QR D-5 / QI-01-01: upload/save tree and D-grade attach renderers live in
``*_page_helpers``. H10 admission (legacy ``tag_session(raw_df)`` vs 15s
parent abort-on-fatal) stays on this page. Session keys unchanged.
"""

from pathlib import Path
import sys
from dataclasses import dataclass

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from thesistester.classic_nav import render_classic_nav_prefill_caption
from thesistester.config import INSTRUMENTS
from thesistester.data.derive import (
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    build_derivation_provenance,
    derive_complete_parent_ohlcv,
    hash_source_frame,
)
from thesistester.data import loader as _data_loader
from thesistester.data.loader import (
    DataValidationError,
    FORMAT_PROFILE_LABELS,
    ValidationReport,
    format_interval,
    infer_base_interval,
    load_ohlcv,
    prepare_15s_source_for_derivation,
    validate_ohlcv,
)
from thesistester.data.resample import SUPPORTED_TIMEFRAMES, resample_ohlcv
from thesistester.data.sessions import tag_session
from thesistester.engine.intrabar import prepare_subtimeframe_conservative_context
from thesistester.app_state import ACTIVE_SAVED_DATASET_KEY
from thesistester.research_bundle import (
    BUNDLE_IMPORT_OMITTED_DATA_KEY,
    DATA_PAGE_INVALIDATE_SOURCE_KEY,
    should_skip_dataset_bootstrap,
)
from thesistester.research_keys import DATASET_CLEAR_KEYS
from thesistester.persistence import (
    clear_active_dataset_id,
    compute_dataset_id,
    set_active_dataset_id,
)
from thesistester.timezone_display import (
    ensure_display_timezone,
    reset_display_timezone,
)
from thesistester.data_page_constants import (
    SubtimeframeCompatibilityError,
    SubtimeframeDuplicateTimestampError,
)
from thesistester.data_display_page_helpers import (
    render_15s_source_duplicate_caption,
    render_dataset_summary,
    render_derived_parent_diagnostics,
    render_roll_assumptions,
)
from thesistester import data_display_page_helpers as display_helpers
from thesistester import data_subtimeframe_page_helpers as subtf_helpers
from thesistester import data_tick_page_helpers as tick_helpers
from thesistester.data_subtimeframe_page_helpers import render_subtimeframe_upload
from thesistester.data_tick_page_helpers import render_tick_attach
from thesistester.data_workspace_page_helpers import render_data_workspace

# Re-export typed errors so `_import_data_page_module` tests keep page names.
_PAGE_TYPED_ERRORS = (
    DataValidationError,
    SubtimeframeCompatibilityError,
    SubtimeframeDuplicateTimestampError,
)

FLASH_MESSAGE_KEY = "_data_local_store_message"
PENDING_INSTRUMENT_SELECTOR_KEY = "_pending_data_instrument_selector"
PENDING_SOURCE_TZ_SELECTOR_KEY = "_pending_data_source_timezone_selector"
RAW_CAPTURE_PROFILES = frozenset(
    {"ninjatrader", "databento_trades", "tick_capture", "second_capture"}
)
INGESTION_MODE_PRIMARY = "primary"
# Presentation order: recommended 15s-primary first; legacy one-minute second.
# API/CLI defaults remain absent→primary; this widget default is Upload-CSV only.
DEFAULT_UPLOAD_INGESTION_MODE = INGESTION_MODE_15S_PRIMARY_DERIVE_1M
INGESTION_MODE_LABELS = {
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M: (
        "Recommended: 15-second primary — derive one-minute canonical"
    ),
    INGESTION_MODE_PRIMARY: "Legacy: one-minute primary (advanced)",
}


def _bind_loader_profile_allow_list(loader_module, name, fallback):
    """R17 type-checked getattr; stale or mistyped loader names keep the page up."""
    value = getattr(loader_module, name, None)
    if isinstance(value, (tuple, list, set, frozenset)) and value:
        return value
    return fallback


# R17 getattr fallback: stale loader.py without the C-2 names keeps the page up.
DERIVE_15S_SUPPORTED_PROFILES = _bind_loader_profile_allow_list(
    _data_loader,
    "DERIVE_15S_SUPPORTED_PROFILES",
    frozenset({"quantower_history_exporter"}),
)
LEGACY_SUBTIMEFRAME_EXPANDER_TITLE = "Legacy dual-upload (optional)"
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
SUBTIMEFRAME_FORMAT_PROFILES = _bind_loader_profile_allow_list(
    _data_loader,
    "SUBTIMEFRAME_FORMAT_PROFILES",
    ("canonical", "quantower_history_exporter"),
)
FATAL_OHLCV_CODES = frozenset(
    {
        "duplicate_timestamps",
        "missing_values",
        "high_below_low",
        "open_close_outside_range",
        "negative_volume",
    }
)


@dataclass(frozen=True)
class Prepared15sPrimaryDataset:
    """Atomic parent/source package for the 15-second-primary Data-page mode."""

    parent_df: pd.DataFrame
    source_df: pd.DataFrame
    source_report: ValidationReport
    parent_report: ValidationReport
    base_interval: str
    subtimeframe_interval: str
    format_profile: str
    provenance: dict
    dropped_buckets: pd.DataFrame
    sparse_buckets: pd.DataFrame
    upload_signature: str


def _default_source_timezone(format_profile: str, exchange_timezone: str) -> str:
    """Return the profile's default timezone for timezone-naive timestamps."""
    return "UTC" if format_profile == "ninjatrader" else exchange_timezone


def _reset_source_timezone_for_import() -> None:
    """Apply the selected source/profile default for timezone-naive timestamps."""
    source = st.session_state["data_source_selector"]
    profile = st.session_state.get("data_format_profile_selector", "canonical")
    exchange_timezone = INSTRUMENTS[st.session_state["data_instrument_selector"]].exchange_tz
    st.session_state["data_source_timezone_selector"] = (
        "America/New_York"
        if source == "Sample data"
        else _default_source_timezone(profile, exchange_timezone)
    )


def _is_15s_primary_session(session_state=None) -> bool:
    """Return True when the active session was built from 15s-primary derivation."""
    state = st.session_state if session_state is None else session_state
    provenance = state.get(INGESTION_PROVENANCE_KEY)
    return (
        isinstance(provenance, dict)
        and provenance.get("ingestion_mode") == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    )


def _sync_upload_ingestion_mode_selector(
    mode: str,
    session_state=None,
    *,
    explicit: bool | None = None,
) -> None:
    """Keep Upload-CSV radio aligned with the active session ingestion path.

    Sample data and restored legacy datasets force one-minute primary locally
    without touching ``data_ingestion_mode_selector``. After PR4's recommended
    15s default, returning to Upload CSV would otherwise keep the radio on
    15s-primary and hide Legacy dual-upload even when the session has no
    derivation provenance.

    Do **not** call this from the Sample-data render branch on every rerun —
    Source defaults to Sample and would clobber the Upload-CSV recommended
    default before the user ever opens Upload CSV.

    Streamlit forbids mutating a widget-bound session key after the radio is
    instantiated on the same run. CSV install paths call this *after*
    ``st.radio(..., key="data_ingestion_mode_selector")``; skip the selector
    write when the value already matches and only refresh the explicit flag.
    """
    if mode not in INGESTION_MODE_LABELS:
        raise ValueError(f"Unsupported ingestion mode for selector sync: {mode!r}")
    state = st.session_state if session_state is None else session_state
    # No-op the widget key when unchanged — required for post-radio install
    # (15s-primary / legacy primary CSV) which already selected ``mode``.
    if state.get("data_ingestion_mode_selector") != mode:
        state["data_ingestion_mode_selector"] = mode
    if explicit is not None:
        state[UPLOAD_INGESTION_MODE_EXPLICIT_KEY] = bool(explicit)


def _align_upload_ingestion_mode_with_session(session_state=None) -> str:
    """Initialize/realign Upload-CSV radio for the active session.

    - Empty / 15s-primary sessions keep the recommended 15s default.
    - Legacy one-minute sessions (Sample, saved, or prior primary upload)
      realign to primary so dual-upload is reachable — unless the user
      explicitly chose an Upload ingestion mode.
    """
    state = st.session_state if session_state is None else session_state
    has_legacy_session = "data" in state and not _is_15s_primary_session(state)
    explicit = bool(state.get(UPLOAD_INGESTION_MODE_EXPLICIT_KEY))
    if "data_ingestion_mode_selector" not in state:
        mode = INGESTION_MODE_PRIMARY if has_legacy_session else DEFAULT_UPLOAD_INGESTION_MODE
        _sync_upload_ingestion_mode_selector(mode, session_state=state, explicit=False)
        return mode
    current = state.get("data_ingestion_mode_selector")
    if has_legacy_session and not explicit and current == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        _sync_upload_ingestion_mode_selector(
            INGESTION_MODE_PRIMARY, session_state=state, explicit=False
        )
        return INGESTION_MODE_PRIMARY
    if current not in INGESTION_MODE_LABELS:
        mode = INGESTION_MODE_PRIMARY if has_legacy_session else DEFAULT_UPLOAD_INGESTION_MODE
        _sync_upload_ingestion_mode_selector(mode, session_state=state, explicit=False)
        return mode
    return str(current)


def _hide_legacy_subtimeframe_uploader(ingestion_mode: str, session_state=None) -> bool:
    """Hide dual-upload lower path when 15s-primary is selected or active.

    Visibility must follow the ingestion-mode radio, not only
    ``ingestion_provenance``. After a mode switch (or with stale one-minute
    ``data`` and no new CSV), provenance is cleared while the selector still
    says derive-from-15s — the legacy uploader must stay hidden in that case.
    """
    if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        return True
    return _is_15s_primary_session(session_state)


def _leave_15s_primary_session_if_active() -> None:
    """Drop 15s-primary artifacts when leaving that ingestion session.

    ``_set_active_dataset_state`` only clears dependent keys when
    ``compute_dataset_id`` changes. Primary uploads that keep the same
    derived parent identity would otherwise leave ``ingestion_provenance``
    and attached 15-second source latched, so ``_is_15s_primary_session()``
    stays true while the selector shows one-minute primary.
    """
    if _is_15s_primary_session():
        _clear_dataset_dependent_state()


def _invalidate_primary_csv_uploader() -> None:
    """Force Streamlit to drop the current primary CSV upload widget value.

    Mode switches must not re-ingest a file chosen under a different ingestion
    mode. A Quantower 15-second export left in the uploader after leaving
    ``15s_primary_derive_1m`` would otherwise hit the legacy primary path and
    replace derived one-minute ``data`` with raw 15-second bars.
    """
    st.session_state[PRIMARY_CSV_UPLOADER_NONCE_KEY] = (
        int(st.session_state.get(PRIMARY_CSV_UPLOADER_NONCE_KEY, 0)) + 1
    )


def _session_has_primary_data(session_state=None) -> bool:
    """True when the session holds a primary OHLCV frame (bundle/upload/saved)."""
    state = st.session_state if session_state is None else session_state
    return isinstance(state.get("data"), pd.DataFrame)


def _preserve_dataset_less_bundle(session_state=None) -> bool:
    """True after a dataset-less import: do not auto-fill ``data``.

    Saved-dataset bootstrap and Sample auto-load both treat missing ``data``
    as an empty session. After AH4 that is also the honest dataset-less
    restore shape (trades B, no bars). Auto-fill would mix A (or sample)
    beside those trades until the user explicitly loads or uploads.
    """
    state = st.session_state if session_state is None else session_state
    return should_skip_dataset_bootstrap(state)


def _consume_data_page_source_invalidation(session_state=None) -> bool:
    """Drop leftover CSV widget state after a research-bundle import.

    Must run before ``st.file_uploader`` widgets are instantiated so a prior
    Upload CSV or lower-timeframe file cannot replace the restored session.
    A leftover lower CSV would re-apply on signature mismatch and clear
    execution dependents (trades / signals / grid).
    """
    state = st.session_state if session_state is None else session_state
    if not state.pop(DATA_PAGE_INVALIDATE_SOURCE_KEY, False):
        return False
    state[PRIMARY_CSV_UPLOADER_NONCE_KEY] = int(state.get(PRIMARY_CSV_UPLOADER_NONCE_KEY, 0)) + 1
    state[SUBTIMEFRAME_UPLOADER_NONCE_KEY] = int(state.get(SUBTIMEFRAME_UPLOADER_NONCE_KEY, 0)) + 1
    state[TICK_UPLOADER_NONCE_KEY] = int(state.get(TICK_UPLOADER_NONCE_KEY, 0)) + 1
    # Signatures are Data-page widget keys, not bundle-managed. A stale hash
    # from the pre-import upload would skip an explicit re-upload of the same
    # file after restore (session would keep the imported lower frame).
    for key in (
        SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY,
        SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY,
        SUBTIMEFRAME_DUPLICATE_REPORT_KEY,
        SUBTIMEFRAME_DUPLICATE_SOURCE_KEY,
        SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY,
        SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY,
        TICK_PATHS_KEY,
        TICK_UPLOAD_SIGNATURE_KEY,
        TICK_ROW_COUNT_KEY,
        TICK_SESSION_COUNT_KEY,
        TICK_WARNINGS_KEY,
    ):
        state.pop(key, None)
    return True


def _should_apply_source_dataset(
    *,
    file_present: bool,
    source: str,
    has_session_data: bool,
    explicit_sample_load: bool = False,
) -> bool:
    """Return True when the Data page should ingest the selected source file.

    Sample data is a first-visit convenience for empty sessions. It must not
    replace in-session data (research-bundle import, prior upload, or saved
    dataset) merely because Source still defaults to Sample on navigation.
    Upload CSV still applies whenever a file is present — that is an explicit
    new-data action and resets dependents via ``dataset_id`` change.
    Sample applies when the session is empty or the user clicks Load sample data.
    """
    if not file_present:
        return False
    if source == "Upload CSV":
        return True
    if source != "Sample data":
        return False
    if explicit_sample_load:
        return True
    return not has_session_data


def _on_ingestion_mode_change() -> None:
    """Reset import defaults and clear mode-bound dataset dependent state."""
    st.session_state[UPLOAD_INGESTION_MODE_EXPLICIT_KEY] = True
    _reset_source_timezone_for_import()
    # Mode switches must not leave stale provenance, attached 15s source,
    # diagnostics, or execution results (plan §4.2 / PR2 acceptance).
    _clear_dataset_dependent_state()
    # Drop the in-widget CSV so the next run cannot re-parse it under the
    # newly selected mode (legacy primary vs 15s-derive).
    _invalidate_primary_csv_uploader()


def _fatal_validation_messages(report: ValidationReport) -> list[str]:
    return [issue.message for issue in report.issues if issue.code in FATAL_OHLCV_CODES]


def _prepare_15s_primary_dataset(
    uploaded_file,
    *,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
    format_profile: str,
) -> Prepared15sPrimaryDataset:
    """Parse, derive, tag, and R12-validate a 15-second-primary upload."""
    if format_profile not in DERIVE_15S_SUPPORTED_PROFILES:
        supported = ", ".join(sorted(DERIVE_15S_SUPPORTED_PROFILES))
        raise ValueError(
            "15-second primary derivation currently supports only these explicit "
            f"format profiles: {supported}. Selected {format_profile!r}."
        )
    raw_df = load_ohlcv(
        uploaded_file,
        source_tz=source_timezone,
        target_tz=exchange_timezone,
        format_profile=format_profile,
    )
    raw_df, source_duplicate_audit = prepare_15s_source_for_derivation(raw_df)
    source_report = validate_ohlcv(raw_df)

    derived = derive_complete_parent_ohlcv(raw_df)
    parent_report = validate_ohlcv(derived.parent_data)
    parent_fatal = _fatal_validation_messages(parent_report)
    if parent_fatal:
        raise ValueError("Derived one-minute validation failed: " + "; ".join(parent_fatal))

    parent_df = tag_session(derived.parent_data, instrument)
    source_df = tag_session(derived.source_data, instrument)
    try:
        # Quantower/Rithmic trade-only 15s exports omit empty slots. Complete
        # minutes still reconcile under the strict R12 contract; sparse minutes
        # are retained for research and use conservative SL-first fallback.
        prepare_subtimeframe_conservative_context(
            parent_df,
            source_df,
            tick_size=INSTRUMENTS[instrument].tick_size,
            parent_interval=derived.parent_interval,
            sub_interval=derived.source_interval,
        )
    except ValueError as exc:
        raise ValueError(
            f"Derived one-minute bars failed the R12 reconciliation postcondition: {exc}"
        ) from exc

    provenance = build_derivation_provenance(
        derived,
        format_profile=format_profile,
        source_duplicate_audit=source_duplicate_audit,
    )
    upload_signature = (
        f"{INGESTION_MODE_15S_PRIMARY_DERIVE_1M}:{format_profile}:"
        f"{hash_source_frame(derived.source_data)}"
    )
    return Prepared15sPrimaryDataset(
        parent_df=parent_df,
        source_df=source_df,
        source_report=source_report,
        parent_report=parent_report,
        base_interval="1min",
        subtimeframe_interval=format_interval(derived.source_interval),
        format_profile=format_profile,
        provenance=provenance,
        dropped_buckets=derived.dropped_buckets.copy(),
        sparse_buckets=derived.sparse_buckets.copy(),
        upload_signature=upload_signature,
    )


def _install_15s_primary_dataset(
    prepared: Prepared15sPrimaryDataset,
    *,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
    resampled_data: dict | None,
) -> None:
    """Install derived parent + retained 15s source into session state."""
    _set_active_dataset_state(
        prepared.parent_df,
        instrument=instrument,
        base_interval=prepared.base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        resampled_data=resampled_data or {},
        saved_dataset_id=None,
    )
    st.session_state["format_profile"] = prepared.format_profile
    st.session_state["subtimeframe_data"] = prepared.source_df
    st.session_state["subtimeframe_interval"] = prepared.subtimeframe_interval
    st.session_state["subtimeframe_format_profile"] = prepared.format_profile
    st.session_state[INGESTION_PROVENANCE_KEY] = dict(prepared.provenance)
    st.session_state[DERIVED_PARENT_DIAGNOSTICS_KEY] = {
        "dropped_buckets": prepared.dropped_buckets,
        "sparse_buckets": prepared.sparse_buckets,
    }
    st.session_state[SUBTIMEFRAME_FALLBACK_BARS_KEY] = []
    st.session_state[SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY] = prepared.upload_signature
    st.session_state.pop("raw_data", None)
    st.session_state.pop("raw_interval", None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_REPORT_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_SOURCE_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DUPLICATE_RESOLUTION_KEY, None)
    st.session_state.pop(SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY, None)
    _sync_upload_ingestion_mode_selector(INGESTION_MODE_15S_PRIMARY_DERIVE_1M, explicit=True)


@st.cache_data(show_spinner=False)
def cached_resample_and_tag(raw_df, instrument: str, timeframe: str):
    """Cache and return session-tagged resampled OHLCV data for preview."""
    out = resample_ohlcv(raw_df, timeframe)
    return tag_session(out, instrument)


def _default_dataset_name(df, instrument: str) -> str:
    if df is None or df.empty or "timestamp" not in df.columns:
        return f"{instrument} dataset"
    start = df["timestamp"].min()
    end = df["timestamp"].max()
    return f"{instrument} {start.date()} to {end.date()}"


def _saved_dataset_label(meta: dict) -> str:
    rows = f"{int(meta.get('rows', 0)):,} rows"
    date_range = "unknown range"
    if meta.get("timestamp_min") and meta.get("timestamp_max"):
        start = meta["timestamp_min"][:10]
        end = meta["timestamp_max"][:10]
        date_range = f"{start} → {end}"
    saved_at = meta.get("created_at", "")[:10] or "unknown date"
    return f"{meta.get('name', meta['dataset_id'])} · {meta.get('instrument', '—')} · {rows} · {date_range} · saved {saved_at}"


def _clear_dataset_dependent_state() -> None:
    """Pop dataset-dependent session keys (D-1 / QI-10-03 generated list).

    AH4 leftover + Focus/OTF overlays are ``dataset_clear`` on the research-key
    registry. A-7 residuals stay apply-clear / sticky (not in this list).
    """
    for key in DATASET_CLEAR_KEYS:
        st.session_state.pop(key, None)


def _set_active_dataset_state(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    resampled_data: dict | None,
    saved_dataset_id: str | None,
):
    dataset_id = saved_dataset_id or compute_dataset_id(
        df,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    previous_dataset_id = st.session_state.get("dataset_id")
    if previous_dataset_id is not None and previous_dataset_id != dataset_id:
        _clear_dataset_dependent_state()
        active_setup = st.session_state.get("setup_config")
        setup_dataset_id = (
            active_setup.get("dataset_id") if isinstance(active_setup, dict) else None
        )
        if (
            isinstance(setup_dataset_id, str)
            and setup_dataset_id
            and setup_dataset_id != dataset_id
        ):
            st.session_state.pop("setup_config", None)
            st.session_state.pop("_setup_builder_editor_config", None)
    st.session_state["data"] = df
    st.session_state.pop(BUNDLE_IMPORT_OMITTED_DATA_KEY, None)
    st.session_state["resampled_data"] = resampled_data or {}
    st.session_state["instrument"] = instrument
    st.session_state["base_interval"] = base_interval
    st.session_state["source_timezone"] = source_timezone
    st.session_state["exchange_timezone"] = exchange_timezone
    # ensure_display_timezone does not overwrite a valid leftover TZ. Switch
    # must reset; same-dataset / first load keeps a user-chosen display TZ.
    if previous_dataset_id is not None and previous_dataset_id != dataset_id:
        reset_display_timezone(
            st.session_state,
            exchange_timezone=exchange_timezone,
        )
    else:
        ensure_display_timezone(
            st.session_state,
            exchange_timezone=exchange_timezone,
        )
    st.session_state["dataset_id"] = dataset_id
    if saved_dataset_id is None:
        clear_active_dataset_id()
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
    else:
        set_active_dataset_id(saved_dataset_id)
        st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_dataset_id


def _render_derived_parent_diagnostics(
    dropped_buckets: pd.DataFrame,
    sparse_buckets: pd.DataFrame | None = None,
) -> None:
    """Show sparse/dropped minute diagnostics for 15-second-primary uploads."""
    render_derived_parent_diagnostics(st, dropped_buckets, sparse_buckets)


def _render_15s_source_duplicate_caption(provenance) -> None:
    """Show resolved 15s source-duplicate audit when provenance recorded one."""
    render_15s_source_duplicate_caption(st, provenance)


def _normalize_tick_path_list(raw) -> list[str]:
    return tick_helpers._normalize_tick_path_list(raw)


def _tick_upload_dir():
    return tick_helpers._tick_upload_dir()


def _sha256_file(path):
    return tick_helpers._sha256_file(path)


def _tick_trusted_roots():
    return tick_helpers._tick_trusted_roots()


def _is_within_tick_trusted_roots(path):
    return tick_helpers._is_within_tick_trusted_roots(path)


def _classify_typed_tick_path(raw: str):
    return tick_helpers._classify_typed_tick_path(raw)


def _resolve_existing_tick_path(raw: str):
    return tick_helpers._resolve_existing_tick_path(raw)


def _dedupe_attached_tick_paths(paths: list[str]):
    return tick_helpers._dedupe_attached_tick_paths(paths)


def _persist_tick_uploads(files, dest_dir):
    return tick_helpers._persist_tick_uploads(files, dest_dir)


def _validate_attached_tick_paths(paths, *, instrument: str, source_tz: str = "UTC"):
    return tick_helpers._validate_attached_tick_paths(
        paths, instrument=instrument, source_tz=source_tz
    )


def _install_tick_paths(
    session_state,
    paths,
    *,
    row_count=None,
    session_count=None,
    signature=None,
    warnings=None,
):
    return tick_helpers._install_tick_paths(
        session_state,
        paths,
        row_count=row_count,
        session_count=session_count,
        signature=signature,
        warnings=warnings,
    )


def _clear_tick_session_state(session_state=None) -> None:
    tick_helpers._clear_tick_session_state(st, session_state)


def _render_tick_attach(*, instrument: str) -> None:
    render_tick_attach(st, instrument=instrument)


def _clear_execution_dependent_state() -> None:
    subtf_helpers._clear_execution_dependent_state(st)


def _load_subtimeframe_upload(
    uploaded_file,
    *,
    parent_df: pd.DataFrame,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
    format_profile: str,
):
    return subtf_helpers._load_subtimeframe_upload(
        uploaded_file,
        parent_df=parent_df,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )


def _set_subtimeframe_state(
    subtimeframe_df: pd.DataFrame,
    *,
    interval: str,
    upload_signature: str,
    fallback_bars: list[dict[str, object]],
) -> None:
    subtf_helpers._set_subtimeframe_state(
        st,
        subtimeframe_df,
        interval=interval,
        upload_signature=upload_signature,
        fallback_bars=fallback_bars,
    )


def _clear_subtimeframe_state() -> None:
    subtf_helpers._clear_subtimeframe_state(st)


def _clear_loaded_subtimeframe_after_failed_upload() -> None:
    subtf_helpers._clear_loaded_subtimeframe_after_failed_upload(st)


def _upload_signature(uploaded_file, *, format_profile: str) -> str:
    return subtf_helpers._upload_signature(uploaded_file, format_profile=format_profile)


def _render_subtimeframe_upload(
    parent_df: pd.DataFrame,
    *,
    instrument: str,
    source_timezone: str | None,
    exchange_timezone: str,
) -> None:
    render_subtimeframe_upload(
        st,
        parent_df,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        profile_options=dict(FORMAT_PROFILE_LABELS),
        format_profiles=SUBTIMEFRAME_FORMAT_PROFILES,
    )


def _render_dataset_summary(
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    report=None,
    resampled_data: dict | None = None,
    saved_dataset_loaded: bool = False,
):
    render_dataset_summary(
        st,
        df,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        report=report,
        resampled_data=resampled_data,
        saved_dataset_loaded=saved_dataset_loaded,
    )


def _primary_duplicate_report(df: pd.DataFrame, report):
    return display_helpers._primary_duplicate_report(df, report)


def _render_roll_assumptions(df, *, instrument: str) -> None:
    render_roll_assumptions(st, df, instrument=instrument)


def _apply_source_dataset(
    file,
    *,
    ingestion_mode: str,
    inst: str,
    source_tz: str | None,
    exchange_timezone: str,
    format_profile: str,
) -> None:
    """Install Upload-CSV / Sample into session. H10 admission is the else fork."""
    selected_timeframes = st.multiselect(
        "Preview resampled timeframes",
        options=list(SUPPORTED_TIMEFRAMES),
        default=["5min", "15min"],
    )
    if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        prepared = _prepare_15s_primary_dataset(
            file,
            instrument=inst,
            source_timezone=source_tz,
            exchange_timezone=exchange_timezone,
            format_profile=format_profile,
        )
        resampled_data = {}
        for timeframe in selected_timeframes:
            out = cached_resample_and_tag(prepared.parent_df, inst, timeframe)
            resampled_data[timeframe] = out
        _install_15s_primary_dataset(
            prepared,
            instrument=inst,
            source_timezone=source_tz,
            exchange_timezone=exchange_timezone,
            resampled_data=resampled_data,
        )
        st.success(
            f"Derived {len(prepared.parent_df):,} one-minute bars from "
            f"{len(prepared.source_df):,} 15-second source bars."
        )
        st.caption(
            "Canonical research data is the derived one-minute frame. "
            "The retained 15-second bars are attached for R12 replay."
        )
        _render_15s_source_duplicate_caption(prepared.provenance)
        _render_derived_parent_diagnostics(
            prepared.dropped_buckets,
            prepared.sparse_buckets,
        )
        _render_dataset_summary(
            prepared.parent_df,
            instrument=inst,
            base_interval=prepared.base_interval,
            source_timezone=source_tz,
            exchange_timezone=exchange_timezone,
            report=prepared.parent_report,
            resampled_data=resampled_data,
        )
    else:
        # Leaving 15s-primary must drop provenance/subtimeframe even when
        # the new primary shares the prior derived parent dataset_id.
        _leave_15s_primary_session_if_active()
        raw_df, captured_raw = load_ohlcv(
            file,
            source_tz=source_tz,
            target_tz=exchange_timezone,
            format_profile=format_profile,
            return_raw=True,
        )
        report = validate_ohlcv(raw_df)
        base_interval = format_interval(report.inferred_interval)
        df = tag_session(raw_df, inst)

        resampled_data = {}
        for timeframe in selected_timeframes:
            out = cached_resample_and_tag(raw_df, inst, timeframe)
            resampled_data[timeframe] = out
        _set_active_dataset_state(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=exchange_timezone,
            resampled_data=resampled_data,
            saved_dataset_id=None,
        )
        st.session_state["format_profile"] = format_profile
        _sync_upload_ingestion_mode_selector(INGESTION_MODE_PRIMARY, explicit=False)
        if format_profile in RAW_CAPTURE_PROFILES:
            st.session_state["raw_data"] = captured_raw
            st.session_state["raw_interval"] = format_interval(
                infer_base_interval(captured_raw["timestamp"])
            )
            st.caption(
                f"Captured {len(captured_raw):,} raw rows; the engine uses the resampled 1-minute bars."
            )
        else:
            st.session_state.pop("raw_data", None)
            st.session_state.pop("raw_interval", None)
        _render_dataset_summary(
            df,
            instrument=inst,
            base_interval=base_interval,
            source_timezone=source_tz,
            exchange_timezone=exchange_timezone,
            report=report,
            resampled_data=resampled_data,
        )


st.title("\U0001f4e5 Data")
st.caption(
    "Load and validate OHLCV data for the active instrument. "
    "Upload a one-minute primary CSV, or use the explicit 15-second-primary mode "
    "to derive one-minute canonical bars and attach the 15-second source for R12 replay. "
    "Legacy dual-upload lower-timeframe attachment remains available for one-minute primaries. "
    "Optional Quantower Tick–Tick–Last files sit beside that 15s clock for prior VA only: "
    "no ticks → no `pdVA*` columns."
)
st.caption(
    "`MessageSizeError` is Streamlit's frontend websocket cap "
    "(`server.maxMessageSize`, repo default 400 MB), not host RAM. "
    "Upload cap (`maxUploadSize` 350 MB) is separate."
)
render_classic_nav_prefill_caption(target_page="pages/1_Data.py")


class _DataPageModule:
    """Resolve page names without requiring ``sys.modules[__name__]``.

    Helper tests ``exec_module`` the page without inserting it into
    ``sys.modules``; a globals proxy still sees monkeypatched names.
    """

    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


render_data_workspace(st, page=_DataPageModule())
