"""Session bootstrap helpers for persisted local dataset state."""

from __future__ import annotations

import streamlit as st

from thesistester.persistence import (
    clear_active_dataset_id,
    clear_active_levels_hash,
    get_active_dataset_id,
    load_dataset,
    load_raw_dataset,
)
from thesistester.timezone_display import ensure_display_timezone

ACTIVE_SAVED_DATASET_KEY = "_active_saved_dataset_id"
BOOTSTRAP_MESSAGE_KEY = "_data_bootstrap_message"


def restore_saved_dataset_provenance(
    dataset_id: str, metadata: dict[str, object]
) -> None:
    """Restore saved ingestion provenance and its optional raw capture sidecar."""
    st.session_state["format_profile"] = metadata.get("format_profile", "canonical")
    raw_interval = metadata.get("raw_interval")
    if raw_interval is None:
        st.session_state.pop("raw_interval", None)
    else:
        st.session_state["raw_interval"] = raw_interval

    raw_data = load_raw_dataset(dataset_id)
    if raw_data is None:
        st.session_state.pop("raw_data", None)
    else:
        st.session_state["raw_data"] = raw_data


def bootstrap_active_saved_dataset() -> bool:
    """Rehydrate the active saved dataset into session state when missing."""
    if "data" in st.session_state:
        return False

    active_dataset_id = get_active_dataset_id()
    if active_dataset_id is None:
        return False

    dataset_id = active_dataset_id

    try:
        loaded_df, loaded_meta = load_dataset(active_dataset_id)
    except (FileNotFoundError, ValueError, OSError):
        clear_active_dataset_id()
        clear_active_levels_hash(dataset_id)
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        return False

    required_meta_keys = ("instrument", "base_interval", "source_timezone", "exchange_timezone")
    if not isinstance(loaded_meta, dict) or any(
        key not in loaded_meta for key in required_meta_keys
    ):
        clear_active_dataset_id()
        clear_active_levels_hash(dataset_id)
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        return False

    st.session_state["data"] = loaded_df
    st.session_state["resampled_data"] = {}
    st.session_state["instrument"] = loaded_meta.get("instrument")
    st.session_state["base_interval"] = loaded_meta.get("base_interval")
    st.session_state["source_timezone"] = loaded_meta.get("source_timezone")
    st.session_state["exchange_timezone"] = loaded_meta.get("exchange_timezone")
    restore_saved_dataset_provenance(dataset_id, loaded_meta)
    ensure_display_timezone(
        st.session_state,
        exchange_timezone=loaded_meta.get("exchange_timezone"),
    )
    st.session_state["dataset_id"] = dataset_id
    st.session_state[ACTIVE_SAVED_DATASET_KEY] = dataset_id
    st.session_state[BOOTSTRAP_MESSAGE_KEY] = (
        f"Restored saved dataset '{loaded_meta.get('name') or 'Unnamed dataset'}'."
    )
    return True
