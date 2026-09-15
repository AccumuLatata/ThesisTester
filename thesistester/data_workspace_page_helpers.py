"""Data-page upload / save workspace (QR D-5 / QI-01-01).

Streamlit-free: callers pass ``st``. H10 admission stays on ``pages/1_Data.py``
as ``_apply_source_dataset`` (legacy ``tag_session(raw_df)``; 15s parent
abort-on-fatal). Session keys unchanged.
"""

from __future__ import annotations

import pandas as pd

from thesistester.app_state import (
    ACTIVE_SAVED_DATASET_KEY,
    BOOTSTRAP_MESSAGE_KEY,
    bootstrap_active_saved_dataset,
)
from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.data.loader import DataValidationError, FORMAT_PROFILE_LABELS
from thesistester.persistence import (
    delete_dataset,
    display_store_path,
    get_store_root,
    list_datasets,
    load_dataset,
    save_dataset,
    set_active_dataset_id,
)
from thesistester.persistence.local_store import get_configured_store_dir
from thesistester.persistence.saved_dataset_state import restore_saved_dataset_provenance
from thesistester.data_page_constants import (
    DERIVED_PARENT_DIAGNOSTICS_KEY,
    FLASH_MESSAGE_KEY,
    LOAD_SAMPLE_REQUESTED_KEY,
    PENDING_INSTRUMENT_SELECTOR_KEY,
    PENDING_SOURCE_TZ_SELECTOR_KEY,
    PRIMARY_CSV_UPLOADER_NONCE_KEY,
)


def render_data_workspace(st, *, page) -> None:
    """Saved-dataset / source / apply / session / attach / save tree."""
    if not page._preserve_dataset_less_bundle():
        bootstrap_active_saved_dataset()
    page._consume_data_page_source_invalidation()

    flash_message = st.session_state.pop(FLASH_MESSAGE_KEY, None)
    if flash_message:
        st.success(flash_message)
    bootstrap_message = st.session_state.pop(BOOTSTRAP_MESSAGE_KEY, None)
    if bootstrap_message:
        st.success(bootstrap_message)
    raw_capture_warning = st.session_state.pop("raw_capture_warning", None)
    if raw_capture_warning:
        st.warning(raw_capture_warning)

    st.subheader("Local saved datasets")
    st.caption(f"Local store: `{display_store_path(get_store_root())}`")
    if get_configured_store_dir() is None:
        st.warning(
            "THESISTESTER_STORE_DIR is not set. Saved datasets are stored in a local repo folder "
            "and may not persist across environments. Set it via a repo-root `.env` "
            "(see `.env.example`) or `scripts/set_store_dir.ps1` on Windows."
        )
    saved_datasets = list_datasets()
    saved_dataset_options = {item["dataset_id"]: item for item in saved_datasets}

    if saved_datasets:
        selected_saved_dataset_id = st.selectbox(
            "Saved datasets",
            options=list(saved_dataset_options),
            format_func=lambda dataset_id: page._saved_dataset_label(
                saved_dataset_options[dataset_id]
            ),
        )
        selected_saved_dataset = saved_dataset_options[selected_saved_dataset_id]

        action_cols = st.columns(3)
        if action_cols[0].button("Load saved dataset", width="stretch"):
            loaded_df, loaded_meta = load_dataset(selected_saved_dataset_id)
            page._set_active_dataset_state(
                loaded_df,
                instrument=loaded_meta["instrument"],
                base_interval=loaded_meta.get("base_interval"),
                source_timezone=loaded_meta.get("source_timezone"),
                exchange_timezone=loaded_meta.get("exchange_timezone"),
                resampled_data={},
                saved_dataset_id=loaded_meta["dataset_id"],
            )
            restore_saved_dataset_provenance(
                st.session_state,
                loaded_meta["dataset_id"],
                loaded_meta,
            )
            # Align Upload-CSV radio with restored provenance so dual-upload /
            # 15s-primary hide rules match the loaded session.
            if page._is_15s_primary_session():
                page._sync_upload_ingestion_mode_selector(
                    page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M, explicit=True
                )
            else:
                page._sync_upload_ingestion_mode_selector(
                    page.INGESTION_MODE_PRIMARY, explicit=False
                )
            st.session_state[FLASH_MESSAGE_KEY] = (
                f"Loaded saved dataset '{loaded_meta['name']}' ({loaded_meta['dataset_id'][:12]}...)."
            )
            st.session_state[PENDING_INSTRUMENT_SELECTOR_KEY] = loaded_meta["instrument"]
            if loaded_meta.get("source_timezone") is not None:
                st.session_state[PENDING_SOURCE_TZ_SELECTOR_KEY] = loaded_meta["source_timezone"]
            st.rerun()

        if action_cols[1].button("Delete saved dataset", width="stretch"):
            delete_dataset(selected_saved_dataset_id)
            if st.session_state.get(ACTIVE_SAVED_DATASET_KEY) == selected_saved_dataset_id:
                st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
            st.session_state[FLASH_MESSAGE_KEY] = (
                f"Deleted saved dataset '{selected_saved_dataset.get('name', selected_saved_dataset_id)}'."
            )
            st.rerun()

        if action_cols[2].button("Refresh saved datasets", width="stretch"):
            st.rerun()
    else:
        st.caption(f"No saved datasets found in `{display_store_path(get_store_root())}`.")
        if st.button("Refresh saved datasets"):
            st.rerun()

    st.divider()

    available_instruments = list(INSTRUMENTS.keys())
    if PENDING_INSTRUMENT_SELECTOR_KEY in st.session_state:
        st.session_state["data_instrument_selector"] = st.session_state.pop(
            PENDING_INSTRUMENT_SELECTOR_KEY
        )
    if "data_instrument_selector" not in st.session_state:
        st.session_state["data_instrument_selector"] = st.session_state.get(
            "instrument",
            available_instruments[0],
        )
    inst = st.selectbox("Instrument", available_instruments, key="data_instrument_selector")
    meta = INSTRUMENTS[inst]
    st.caption(
        f"{meta.name} · tick size {meta.tick_size} · point value ${meta.point_value:,.0f} "
        f"· session tz {meta.exchange_tz} ({meta.rth_start}–{meta.rth_end} RTH)"
    )

    source = st.radio(
        "Source",
        ["Sample data", "Upload CSV"],
        horizontal=True,
        key="data_source_selector",
        on_change=page._reset_source_timezone_for_import,
    )
    if source == "Upload CSV":
        # Realign only on the Upload-CSV path (never from Sample reruns).
        page._align_upload_ingestion_mode_with_session()
        ingestion_mode = st.radio(
            "Ingestion mode",
            options=list(page.INGESTION_MODE_LABELS),
            format_func=page.INGESTION_MODE_LABELS.get,
            horizontal=True,
            key="data_ingestion_mode_selector",
            help=(
                "Recommended for Quantower 15-second exports: derive complete "
                "one-minute bars and retain the 15-second source for R12. "
                "Legacy one-minute primary keeps dual-upload available."
            ),
            on_change=page._on_ingestion_mode_change,
        )
        st.caption(
            "Locked composer fork: legacy one-minute primary still installs the "
            "frame when validation reports fatal OHLCV codes (Loaded, then warning). "
            "`api.load_dataset` rejects those same codes. 15s-primary parent stays "
            "fail-closed."
        )
    else:
        # Sample data remains the legacy one-minute fixture path.
        # Do not write data_ingestion_mode_selector here — Source defaults to
        # Sample and would clobber the Upload-CSV recommended default.
        ingestion_mode = page.INGESTION_MODE_PRIMARY

    all_profile_options = dict(FORMAT_PROFILE_LABELS)
    if ingestion_mode == page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M:
        profile_options = {
            key: label
            for key, label in all_profile_options.items()
            if key in page.DERIVE_15S_SUPPORTED_PROFILES
        }
        if st.session_state.get("data_format_profile_selector") not in profile_options:
            st.session_state["data_format_profile_selector"] = next(iter(profile_options))
    else:
        profile_options = all_profile_options
    format_profile = (
        st.selectbox(
            "CSV format profile",
            options=list(profile_options),
            format_func=profile_options.get,
            help="Explicit selection only; ThesisTester never auto-detects vendor formats.",
            key="data_format_profile_selector",
            on_change=page._reset_source_timezone_for_import,
        )
        if source == "Upload CSV"
        else "canonical"
    )
    default_source_tz = (
        "America/New_York"
        if source == "Sample data"
        else page._default_source_timezone(format_profile, meta.exchange_tz)
    )
    if PENDING_SOURCE_TZ_SELECTOR_KEY in st.session_state:
        st.session_state["data_source_timezone_selector"] = st.session_state.pop(
            PENDING_SOURCE_TZ_SELECTOR_KEY
        )
    if "data_source_timezone_selector" not in st.session_state:
        st.session_state["data_source_timezone_selector"] = default_source_tz
    source_tz = st.selectbox(
        "Source timestamp timezone",
        TIMEZONE_OPTIONS,
        index=TIMEZONE_OPTIONS.index(st.session_state["data_source_timezone_selector"]),
        key="data_source_timezone_selector",
        help=(
            "Use this for timezone-naive CSV timestamps. Timezone-aware timestamps are "
            "converted from their embedded timezone automatically."
        ),
    )

    file = None
    if source == "Upload CSV":
        primary_uploader_nonce = int(st.session_state.get(PRIMARY_CSV_UPLOADER_NONCE_KEY, 0))
        file = st.file_uploader(
            "CSV file for the selected explicit profile",
            type=["csv", "txt"],
            key=f"primary_csv_upload_{primary_uploader_nonce}",
        )
    else:
        sample = page.REPO_ROOT / "sample_data" / "ES_sample_1m.csv"
        file = sample if sample.exists() else None
        if file is None:
            st.error("Sample data not found.")

    explicit_sample_load = bool(st.session_state.pop(LOAD_SAMPLE_REQUESTED_KEY, False))
    use_source_dataset = page._should_apply_source_dataset(
        file_present=file is not None,
        source=source,
        has_session_data=page._session_has_primary_data() or page._preserve_dataset_less_bundle(),
        explicit_sample_load=explicit_sample_load,
    )

    if use_source_dataset:
        try:
            page._apply_source_dataset(
                file,
                ingestion_mode=ingestion_mode,
                inst=inst,
                source_tz=source_tz,
                exchange_timezone=meta.exchange_tz,
                format_profile=format_profile,
            )
        except (DataValidationError, ValueError) as exc:
            st.error(str(exc))
    elif page._preserve_dataset_less_bundle():
        st.info(
            "Imported research bundle omitted dataset bars. Sample data and the "
            "active saved dataset are not applied automatically. Load a saved "
            "dataset or upload a CSV if you want bars beside the imported trades."
        )
        if source == "Sample data" and st.button("Load sample data"):
            st.session_state[LOAD_SAMPLE_REQUESTED_KEY] = True
            st.rerun()
    elif page._session_has_primary_data():
        if source == "Sample data":
            st.info(
                "Session already has data. The sample file is not applied automatically "
                "when you open this page. Load sample data only if you want to replace "
                "the current dataset (this resets levels and downstream results when "
                "the dataset identity changes)."
            )
            if st.button("Load sample data"):
                st.session_state[LOAD_SAMPLE_REQUESTED_KEY] = True
                st.rerun()
        page._render_dataset_summary(
            st.session_state["data"],
            instrument=st.session_state.get("instrument", inst),
            base_interval=st.session_state.get("base_interval"),
            source_timezone=st.session_state.get("source_timezone"),
            exchange_timezone=st.session_state.get("exchange_timezone"),
            resampled_data=st.session_state.get("resampled_data"),
            saved_dataset_loaded=ACTIVE_SAVED_DATASET_KEY in st.session_state,
        )
        if page._is_15s_primary_session():
            page._render_15s_source_duplicate_caption(st.session_state.get("ingestion_provenance"))
            diagnostics = st.session_state.get(DERIVED_PARENT_DIAGNOSTICS_KEY)
            if isinstance(diagnostics, dict):
                dropped = diagnostics.get("dropped_buckets")
                sparse = diagnostics.get("sparse_buckets")
                if isinstance(dropped, pd.DataFrame) or isinstance(sparse, pd.DataFrame):
                    page._render_derived_parent_diagnostics(
                        dropped if isinstance(dropped, pd.DataFrame) else pd.DataFrame(),
                        sparse if isinstance(sparse, pd.DataFrame) else pd.DataFrame(),
                    )
            elif isinstance(diagnostics, pd.DataFrame):
                # Legacy session shape: diagnostics held only dropped/incomplete rows.
                page._render_derived_parent_diagnostics(diagnostics)

    current_df = st.session_state.get("data")
    if current_df is not None:
        st.divider()
        if page._hide_legacy_subtimeframe_uploader(ingestion_mode):
            if page._is_15s_primary_session():
                interval = st.session_state.get("subtimeframe_interval", "15s")
                source_rows = st.session_state.get("subtimeframe_data")
                source_count = len(source_rows) if isinstance(source_rows, pd.DataFrame) else 0
                st.info(
                    f"15-second source attached from primary upload: {source_count:,} bars at "
                    f"{interval}. Separate lower-timeframe upload is hidden in this mode."
                )
            else:
                # Mode selected but no active 15s-primary provenance yet (e.g. stale
                # one-minute data after a mode switch, before a new 15s CSV upload).
                st.info(
                    "Separate lower-timeframe upload is hidden in 15-second primary mode. "
                    "Upload a 15-second CSV above to derive one-minute bars and attach "
                    "the 15-second source for R12."
                )
        else:
            page._render_subtimeframe_upload(
                current_df,
                instrument=st.session_state.get("instrument", inst),
                source_timezone=st.session_state.get("source_timezone"),
                exchange_timezone=st.session_state.get("exchange_timezone", meta.exchange_tz),
            )
        page._render_tick_attach(instrument=st.session_state.get("instrument", inst))
        st.divider()
        page._render_roll_assumptions(
            current_df,
            instrument=st.session_state.get("instrument", inst),
        )
        st.divider()
        current_instrument = st.session_state.get("instrument", inst)
        default_name = page._default_dataset_name(current_df, current_instrument)
        dataset_name = st.text_input("Local dataset name", value=default_name)
        if st.button("Save dataset locally"):
            saved_meta = save_dataset(
                current_df,
                name=dataset_name.strip() or default_name,
                instrument=current_instrument,
                base_interval=st.session_state.get("base_interval"),
                source_timezone=st.session_state.get("source_timezone"),
                exchange_timezone=st.session_state.get("exchange_timezone"),
                raw_data=st.session_state.get("raw_data"),
                format_profile=st.session_state.get("format_profile", "canonical"),
                raw_interval=st.session_state.get("raw_interval"),
                subtimeframe_data=st.session_state.get("subtimeframe_data"),
                subtimeframe_interval=st.session_state.get("subtimeframe_interval"),
                subtimeframe_format_profile=st.session_state.get("subtimeframe_format_profile"),
                ingestion_provenance=st.session_state.get("ingestion_provenance"),
            )
            st.session_state["dataset_id"] = saved_meta["dataset_id"]
            set_active_dataset_id(saved_meta["dataset_id"])
            st.session_state[ACTIVE_SAVED_DATASET_KEY] = saved_meta["dataset_id"]
            st.session_state[FLASH_MESSAGE_KEY] = (
                f"Saved dataset '{saved_meta['name']}' locally ({saved_meta['dataset_id'][:12]}...)."
            )
            st.rerun()
