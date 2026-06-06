"""Session bootstrap helpers for persisted local dataset state."""
from __future__ import annotations

import streamlit as st

from thesistester.persistence import (
    clear_active_dataset_id,
    clear_active_levels_hash,
    get_active_dataset_id,
    load_dataset,
)

ACTIVE_SAVED_DATASET_KEY = "_active_saved_dataset_id"
BOOTSTRAP_MESSAGE_KEY = "_data_bootstrap_message"


def bootstrap_active_saved_dataset() -> bool:
    """Rehydrate the active saved dataset into session state when missing."""
    if "data" in st.session_state:
        return False

    active_dataset_id = get_active_dataset_id()
    if active_dataset_id is None:
        return False

    try:
        loaded_df, loaded_meta = load_dataset(active_dataset_id)
    except (FileNotFoundError, ValueError, OSError):
        clear_active_dataset_id()
        clear_active_levels_hash(active_dataset_id)
        st.session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        return False

    st.session_state["data"] = loaded_df
    st.session_state["resampled_data"] = {}
    st.session_state["instrument"] = loaded_meta.get("instrument")
    st.session_state["base_interval"] = loaded_meta.get("base_interval")
    st.session_state["source_timezone"] = loaded_meta.get("source_timezone")
    st.session_state["exchange_timezone"] = loaded_meta.get("exchange_timezone")
    st.session_state["dataset_id"] = loaded_meta["dataset_id"]
    st.session_state[ACTIVE_SAVED_DATASET_KEY] = loaded_meta["dataset_id"]
    st.session_state[BOOTSTRAP_MESSAGE_KEY] = (
        f"Restored saved dataset '{loaded_meta.get('name', loaded_meta['dataset_id'])}'."
    )
    return True
