"""One-function Streamlit adapter for saved-dataset bootstrap (C-8 / QI-06-05).

Store logic is Streamlit-free in
``thesistester.persistence.saved_dataset_state``. This module binds
``st.session_state`` lazily so importing ``app_state`` does not load Streamlit.
``restore_saved_dataset_provenance`` is store-only (mapping in; no Streamlit
bind) — do not re-export it here. AH4 skip-flag stays page-local
(``should_skip_dataset_bootstrap``).
"""

from __future__ import annotations

from thesistester.persistence.saved_dataset_state import (
    ACTIVE_SAVED_DATASET_KEY,
    BOOTSTRAP_MESSAGE_KEY,
    bootstrap_active_saved_dataset as bootstrap_saved_dataset,
)

__all__ = (
    "ACTIVE_SAVED_DATASET_KEY",
    "BOOTSTRAP_MESSAGE_KEY",
    "bootstrap_active_saved_dataset",
)


def bootstrap_active_saved_dataset() -> bool:
    """Rehydrate the active saved dataset into Streamlit session state when missing."""
    import streamlit as st

    return bootstrap_saved_dataset(st.session_state)
