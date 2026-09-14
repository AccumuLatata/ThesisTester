"""Streamlit-free saved-dataset session restore (C-8 / QI-06-05).

Bootstrap writes a mapping (classic ``session_state``). The Streamlit bind
lives in ``thesistester.app_state.bootstrap_active_saved_dataset``.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from thesistester.persistence.local_store import (
    clear_active_dataset_id,
    clear_active_levels_hash,
    get_active_dataset_id,
    load_dataset,
    load_raw_dataset,
    load_subtimeframe_dataset,
)
from thesistester.timezone_display import ensure_display_timezone

ACTIVE_SAVED_DATASET_KEY = "_active_saved_dataset_id"
BOOTSTRAP_MESSAGE_KEY = "_data_bootstrap_message"

_REQUIRED_META_KEYS = ("instrument", "base_interval", "source_timezone", "exchange_timezone")


def restore_saved_dataset_provenance(
    session_state: MutableMapping[str, Any],
    dataset_id: str,
    metadata: Mapping[str, object],
) -> None:
    """Restore saved ingestion provenance and optional sidecars."""
    session_state["format_profile"] = metadata.get("format_profile", "canonical")
    raw_interval = metadata.get("raw_interval")
    if raw_interval is None:
        session_state.pop("raw_interval", None)
    else:
        session_state["raw_interval"] = raw_interval

    try:
        raw_data = load_raw_dataset(dataset_id)
    except (OSError, ValueError):
        raw_data = None
        session_state["raw_capture_warning"] = (
            "Saved raw capture sidecar could not be read; canonical bars remain available."
        )
    else:
        session_state.pop("raw_capture_warning", None)
    if raw_data is None:
        session_state.pop("raw_data", None)
    else:
        session_state["raw_data"] = raw_data

    try:
        subtimeframe_data = load_subtimeframe_dataset(dataset_id)
    except (OSError, ValueError):
        subtimeframe_data = None
        session_state["subtimeframe_restore_warning"] = (
            "Saved subtimeframe sidecar could not be read; canonical bars remain available."
        )
    else:
        session_state.pop("subtimeframe_restore_warning", None)

    if subtimeframe_data is None:
        session_state.pop("subtimeframe_data", None)
        session_state.pop("subtimeframe_interval", None)
        session_state.pop("subtimeframe_format_profile", None)
        session_state.pop("subtimeframe_fallback_parent_bars", None)
    else:
        session_state["subtimeframe_data"] = subtimeframe_data
        interval = metadata.get("subtimeframe_interval")
        if interval is None:
            session_state.pop("subtimeframe_interval", None)
        else:
            session_state["subtimeframe_interval"] = interval
        profile = metadata.get("subtimeframe_format_profile")
        if profile is None:
            session_state.pop("subtimeframe_format_profile", None)
        else:
            session_state["subtimeframe_format_profile"] = profile
        session_state["subtimeframe_fallback_parent_bars"] = []

    # Derive-mode provenance must not latch without a usable lower frame —
    # otherwise the UI hides dual-upload while strict R12 has no source bars.
    provenance = metadata.get("ingestion_provenance")
    if isinstance(provenance, dict) and subtimeframe_data is not None:
        session_state["ingestion_provenance"] = dict(provenance)
    else:
        session_state.pop("ingestion_provenance", None)


def bootstrap_active_saved_dataset(session_state: MutableMapping[str, Any]) -> bool:
    """Rehydrate the active saved dataset into ``session_state`` when missing.

    AH4 skip-flag stays page-local (``should_skip_dataset_bootstrap``). This
    helper does not read ``bundle_import_omitted_data``.
    """
    if "data" in session_state:
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
        session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        return False

    if not isinstance(loaded_meta, dict) or any(
        key not in loaded_meta for key in _REQUIRED_META_KEYS
    ):
        clear_active_dataset_id()
        clear_active_levels_hash(dataset_id)
        session_state.pop(ACTIVE_SAVED_DATASET_KEY, None)
        return False

    session_state["data"] = loaded_df
    session_state["resampled_data"] = {}
    session_state["instrument"] = loaded_meta.get("instrument")
    session_state["base_interval"] = loaded_meta.get("base_interval")
    session_state["source_timezone"] = loaded_meta.get("source_timezone")
    session_state["exchange_timezone"] = loaded_meta.get("exchange_timezone")
    restore_saved_dataset_provenance(session_state, dataset_id, loaded_meta)
    ensure_display_timezone(
        session_state,
        exchange_timezone=loaded_meta.get("exchange_timezone"),
    )
    session_state["dataset_id"] = dataset_id
    session_state[ACTIVE_SAVED_DATASET_KEY] = dataset_id
    session_state[BOOTSTRAP_MESSAGE_KEY] = (
        f"Restored saved dataset '{loaded_meta.get('name') or 'Unnamed dataset'}'."
    )
    return True
