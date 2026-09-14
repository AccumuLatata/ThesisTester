"""C-8 / QI-06-05: Streamlit-free saved-dataset store + one-function adapter."""

from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path

import pandas as pd

from thesistester.persistence import saved_dataset_state as store

LIBRARY_ROOT = Path("thesistester")


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )


def test_store_import_does_not_load_streamlit(monkeypatch):
    monkeypatch.delitem(sys.modules, "thesistester.persistence.saved_dataset_state", raising=False)
    monkeypatch.delitem(sys.modules, "thesistester.app_state", raising=False)
    blocked = types.ModuleType("streamlit")

    def _blocked_getattr(_name: str):
        raise AssertionError("saved_dataset_state must not touch Streamlit")

    blocked.__getattr__ = _blocked_getattr  # type: ignore[method-assign]
    monkeypatch.setitem(sys.modules, "streamlit", blocked)
    reloaded = importlib.import_module("thesistester.persistence.saved_dataset_state")
    assert reloaded.ACTIVE_SAVED_DATASET_KEY == store.ACTIVE_SAVED_DATASET_KEY
    adapter = importlib.import_module("thesistester.app_state")
    assert adapter.bootstrap_active_saved_dataset.__module__ == "thesistester.app_state"
    # Drop the adapter bound to this ephemeral store copy. monkeypatch will
    # restore the canonical store module; a leftover adapter would close over
    # the detached copy and ignore later `store.*` patches.
    sys.modules.pop("thesistester.app_state", None)


def test_bootstrap_does_not_override_existing_data(monkeypatch):
    session_state = {"data": "already-loaded"}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-123")
    monkeypatch.setattr(
        store,
        "load_dataset",
        lambda dataset_id: (_ for _ in ()).throw(
            AssertionError("load_dataset should not be called")
        ),
    )

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is False
    assert session_state["data"] == "already-loaded"


def test_bootstrap_restores_valid_saved_dataset(monkeypatch):
    df = _sample_frame()
    meta = {
        "name": "Saved sample",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state: dict = {}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(store, "load_dataset", lambda dataset_id: (df, meta))

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is True
    assert session_state["data"] is df
    assert session_state["resampled_data"] == {}
    assert session_state["instrument"] == "ES"
    assert session_state["base_interval"] == "1min"
    assert session_state["source_timezone"] == "America/New_York"
    assert session_state["exchange_timezone"] == "America/New_York"
    assert session_state["dataset_id"] == "dataset-abc"
    assert session_state[store.ACTIVE_SAVED_DATASET_KEY] == "dataset-abc"


def test_bootstrap_restores_capture_profile_and_raw_sidecar(monkeypatch):
    df = _sample_frame()
    raw = pd.DataFrame({"timestamp": [1], "price": [1.0], "volume": [1.0]})
    meta = {
        "name": "Saved tick capture",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "format_profile": "tick_capture",
        "raw_interval": "0 days 00:00:01",
    }
    session_state: dict = {}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(store, "load_dataset", lambda dataset_id: (df, meta))
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: raw)

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is True
    assert session_state["format_profile"] == "tick_capture"
    assert session_state["raw_data"] is raw
    assert session_state["raw_interval"] == "0 days 00:00:01"


def test_restore_saved_dataset_provenance_clears_absent_raw_sidecar(monkeypatch):
    session_state = {
        "format_profile": "tick_capture",
        "raw_data": pd.DataFrame({"timestamp": [1]}),
        "raw_interval": "0 days 00:00:01",
    }
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: None)

    store.restore_saved_dataset_provenance(
        session_state,
        "dataset-abc",
        {"format_profile": "canonical", "raw_interval": None},
    )

    assert session_state["format_profile"] == "canonical"
    assert "raw_data" not in session_state
    assert "raw_interval" not in session_state


def test_restore_saved_dataset_provenance_keeps_canonical_state_when_raw_is_corrupt(
    monkeypatch,
):
    session_state: dict = {}
    monkeypatch.setattr(
        store,
        "load_raw_dataset",
        lambda dataset_id: (_ for _ in ()).throw(ValueError("invalid parquet")),
    )

    store.restore_saved_dataset_provenance(
        session_state,
        "dataset-abc",
        {"format_profile": "tick_capture", "raw_interval": "0 days 00:00:01"},
    )

    assert session_state["format_profile"] == "tick_capture"
    assert "raw_data" not in session_state
    assert "raw_capture_warning" in session_state


def test_bootstrap_restores_subtimeframe_sidecar_and_ingestion_provenance(monkeypatch):
    df = _sample_frame()
    sub = _sample_frame()
    provenance = {
        "ingestion_mode": "15s_primary_derive_1m",
        "derivation_policy": "complete_aligned_15s_to_1m_v1",
        "dropped_parent_bucket_count": 0,
    }
    meta = {
        "name": "Derived sample",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
        "format_profile": "quantower_history_exporter",
        "has_subtimeframe": True,
        "subtimeframe_interval": "15s",
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": provenance,
    }
    session_state: dict = {}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-derived")
    monkeypatch.setattr(store, "load_dataset", lambda dataset_id: (df, meta))
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(store, "load_subtimeframe_dataset", lambda dataset_id: sub)

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is True
    assert session_state["subtimeframe_data"] is sub
    assert session_state["subtimeframe_interval"] == "15s"
    assert session_state["subtimeframe_format_profile"] == "quantower_history_exporter"
    assert session_state["ingestion_provenance"] == provenance
    assert session_state["subtimeframe_fallback_parent_bars"] == []


def test_restore_saved_dataset_provenance_clears_absent_subtimeframe_sidecar(monkeypatch):
    session_state = {
        "subtimeframe_data": pd.DataFrame({"timestamp": [1]}),
        "subtimeframe_interval": "15s",
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
        "subtimeframe_fallback_parent_bars": [],
    }
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(store, "load_subtimeframe_dataset", lambda dataset_id: None)

    store.restore_saved_dataset_provenance(
        session_state,
        "dataset-abc",
        {"format_profile": "canonical"},
    )

    assert "subtimeframe_data" not in session_state
    assert "subtimeframe_interval" not in session_state
    assert "subtimeframe_format_profile" not in session_state
    assert "ingestion_provenance" not in session_state
    assert "subtimeframe_fallback_parent_bars" not in session_state


def test_restore_does_not_latch_derive_provenance_without_subtimeframe(monkeypatch):
    """Broken/partial restores must not hide dual-upload via orphan provenance."""
    session_state: dict = {}
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(store, "load_subtimeframe_dataset", lambda dataset_id: None)

    store.restore_saved_dataset_provenance(
        session_state,
        "dataset-abc",
        {
            "format_profile": "quantower_history_exporter",
            "has_subtimeframe": False,
            "ingestion_provenance": {
                "ingestion_mode": "15s_primary_derive_1m",
                "derivation_policy": "complete_aligned_15s_to_1m_v1",
            },
        },
    )

    assert "subtimeframe_data" not in session_state
    assert "ingestion_provenance" not in session_state


def test_restore_clears_provenance_when_subtimeframe_sidecar_unreadable(monkeypatch):
    session_state = {
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
    }
    monkeypatch.setattr(store, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(
        store,
        "load_subtimeframe_dataset",
        lambda dataset_id: (_ for _ in ()).throw(ValueError("corrupt parquet")),
    )

    store.restore_saved_dataset_provenance(
        session_state,
        "dataset-abc",
        {
            "format_profile": "quantower_history_exporter",
            "has_subtimeframe": True,
            "subtimeframe_interval": "15s",
            "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
        },
    )

    assert "subtimeframe_data" not in session_state
    assert "ingestion_provenance" not in session_state
    assert "subtimeframe_restore_warning" in session_state


def test_bootstrap_clears_stale_saved_dataset_pointer(monkeypatch):
    session_state: dict = {}
    cleared: dict[str, object] = {"dataset": 0, "levels_dataset_id": None}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "stale-dataset")

    def _raise_stale(_dataset_id: str):
        raise FileNotFoundError("missing dataset")

    monkeypatch.setattr(store, "load_dataset", _raise_stale)
    monkeypatch.setattr(store, "clear_active_dataset_id", lambda: cleared.__setitem__("dataset", 1))
    monkeypatch.setattr(
        store,
        "clear_active_levels_hash",
        lambda dataset_id: cleared.__setitem__("levels_dataset_id", dataset_id),
    )

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is False
    assert cleared["dataset"] == 1
    assert cleared["levels_dataset_id"] == "stale-dataset"


def test_bootstrap_clears_malformed_saved_dataset_metadata(monkeypatch):
    df = _sample_frame()
    malformed_meta = {
        "name": "Saved sample",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state: dict = {}
    cleared: dict[str, object] = {"dataset": 0, "levels_dataset_id": None}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(store, "load_dataset", lambda dataset_id: (df, malformed_meta))
    monkeypatch.setattr(store, "clear_active_dataset_id", lambda: cleared.__setitem__("dataset", 1))
    monkeypatch.setattr(
        store,
        "clear_active_levels_hash",
        lambda dataset_id: cleared.__setitem__("levels_dataset_id", dataset_id),
    )

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is False
    assert "data" not in session_state
    assert cleared["dataset"] == 1
    assert cleared["levels_dataset_id"] == "dataset-abc"


def test_ah4_skip_flag_does_not_change_store_bootstrap(monkeypatch):
    """AH4 skip stays page-local; store bootstrap is unchanged globally."""
    df = _sample_frame()
    meta = {
        "name": "Saved sample",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state = {"bundle_import_omitted_data": True}
    monkeypatch.setattr(store, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(store, "load_dataset", lambda dataset_id: (df, meta))

    restored = store.bootstrap_active_saved_dataset(session_state)

    assert restored is True
    assert session_state["data"] is df


def test_adapter_is_one_function_and_does_not_export_restore():
    from thesistester import app_state

    assert app_state.__all__ == (
        "ACTIVE_SAVED_DATASET_KEY",
        "BOOTSTRAP_MESSAGE_KEY",
        "bootstrap_active_saved_dataset",
    )
    assert not hasattr(app_state, "restore_saved_dataset_provenance")


def test_adapter_delegates_to_store(monkeypatch):
    from thesistester import app_state

    importlib.reload(app_state)
    session_state = {"data": "already-loaded"}
    stub = types.ModuleType("streamlit")
    stub.session_state = session_state
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    monkeypatch.setattr(
        store,
        "load_dataset",
        lambda dataset_id: (_ for _ in ()).throw(
            AssertionError("adapter must not load when data is present")
        ),
    )

    assert app_state.bootstrap_active_saved_dataset() is False
    assert session_state["data"] == "already-loaded"


def test_adapter_passes_streamlit_session_state_to_store(monkeypatch):
    from thesistester import app_state

    session_state = {"probe": True}
    captured: dict[str, object] = {}

    def _capture(state):
        captured["session_state"] = state
        return True

    stub = types.ModuleType("streamlit")
    stub.session_state = session_state
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    monkeypatch.setattr(app_state, "bootstrap_saved_dataset", _capture)

    assert app_state.bootstrap_active_saved_dataset() is True
    assert captured["session_state"] is session_state


def _module_level_streamlit_imports(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    hits: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            hits.extend(
                alias.name
                for alias in node.names
                if alias.name == "streamlit" or alias.name.startswith("streamlit.")
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "streamlit" or module.startswith("streamlit."):
                hits.append(module)
    return tuple(hits)


def test_library_has_no_eager_streamlit_importers():
    """C-8 gate: eager Streamlit importers in thesistester/ = 0."""
    offenders: list[str] = []
    for path in sorted(LIBRARY_ROOT.rglob("*.py")):
        hits = _module_level_streamlit_imports(path.read_text(encoding="utf-8"))
        if hits:
            offenders.append(f"{path.as_posix()}: {', '.join(hits)}")
    assert offenders == []
