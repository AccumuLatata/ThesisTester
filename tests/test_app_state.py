import types

import pandas as pd

from thesistester import app_state


def _stub_streamlit_state(monkeypatch, state: dict):
    monkeypatch.setattr(
        app_state,
        "st",
        types.SimpleNamespace(session_state=state),
    )


def test_bootstrap_does_not_override_existing_data(monkeypatch):
    session_state = {"data": "already-loaded"}
    _stub_streamlit_state(monkeypatch, session_state)

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-123")
    monkeypatch.setattr(
        app_state,
        "load_dataset",
        lambda dataset_id: (_ for _ in ()).throw(
            AssertionError("load_dataset should not be called")
        ),
    )

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is False
    assert session_state["data"] == "already-loaded"


def test_bootstrap_restores_valid_saved_dataset(monkeypatch):
    df = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
    meta = {
        "name": "Saved sample",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state: dict = {}
    _stub_streamlit_state(monkeypatch, session_state)

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(app_state, "load_dataset", lambda dataset_id: (df, meta))

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is True
    assert session_state["data"] is df
    assert session_state["resampled_data"] == {}
    assert session_state["instrument"] == "ES"
    assert session_state["base_interval"] == "1min"
    assert session_state["source_timezone"] == "America/New_York"
    assert session_state["exchange_timezone"] == "America/New_York"
    assert session_state["dataset_id"] == "dataset-abc"
    assert session_state[app_state.ACTIVE_SAVED_DATASET_KEY] == "dataset-abc"


def test_bootstrap_restores_capture_profile_and_raw_sidecar(monkeypatch):
    df = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
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
    _stub_streamlit_state(monkeypatch, session_state)

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(app_state, "load_dataset", lambda dataset_id: (df, meta))
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: raw)

    restored = app_state.bootstrap_active_saved_dataset()

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
    _stub_streamlit_state(monkeypatch, session_state)
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: None)

    app_state.restore_saved_dataset_provenance(
        "dataset-abc",
        {"format_profile": "canonical", "raw_interval": None},
    )

    assert session_state["format_profile"] == "canonical"
    assert "raw_data" not in session_state
    assert "raw_interval" not in session_state


def test_restore_saved_dataset_provenance_keeps_canonical_state_when_raw_is_corrupt(monkeypatch):
    session_state: dict = {}
    _stub_streamlit_state(monkeypatch, session_state)
    monkeypatch.setattr(
        app_state,
        "load_raw_dataset",
        lambda dataset_id: (_ for _ in ()).throw(ValueError("invalid parquet")),
    )

    app_state.restore_saved_dataset_provenance(
        "dataset-abc",
        {"format_profile": "tick_capture", "raw_interval": "0 days 00:00:01"},
    )

    assert session_state["format_profile"] == "tick_capture"
    assert "raw_data" not in session_state
    assert "raw_capture_warning" in session_state


def test_bootstrap_restores_subtimeframe_sidecar_and_ingestion_provenance(monkeypatch):
    df = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
    sub = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
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
    _stub_streamlit_state(monkeypatch, session_state)

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-derived")
    monkeypatch.setattr(app_state, "load_dataset", lambda dataset_id: (df, meta))
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(app_state, "load_subtimeframe_dataset", lambda dataset_id: sub)

    restored = app_state.bootstrap_active_saved_dataset()

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
    _stub_streamlit_state(monkeypatch, session_state)
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(app_state, "load_subtimeframe_dataset", lambda dataset_id: None)

    app_state.restore_saved_dataset_provenance(
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
    _stub_streamlit_state(monkeypatch, session_state)
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(app_state, "load_subtimeframe_dataset", lambda dataset_id: None)

    app_state.restore_saved_dataset_provenance(
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
    _stub_streamlit_state(monkeypatch, session_state)
    monkeypatch.setattr(app_state, "load_raw_dataset", lambda dataset_id: None)
    monkeypatch.setattr(
        app_state,
        "load_subtimeframe_dataset",
        lambda dataset_id: (_ for _ in ()).throw(ValueError("corrupt parquet")),
    )

    app_state.restore_saved_dataset_provenance(
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
    _stub_streamlit_state(monkeypatch, session_state)

    cleared: dict[str, object] = {"dataset": 0, "levels_dataset_id": None}

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "stale-dataset")

    def _raise_stale(_dataset_id: str):
        raise FileNotFoundError("missing dataset")

    monkeypatch.setattr(app_state, "load_dataset", _raise_stale)
    monkeypatch.setattr(
        app_state, "clear_active_dataset_id", lambda: cleared.__setitem__("dataset", 1)
    )
    monkeypatch.setattr(
        app_state,
        "clear_active_levels_hash",
        lambda dataset_id: cleared.__setitem__("levels_dataset_id", dataset_id),
    )

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is False
    assert cleared["dataset"] == 1
    assert cleared["levels_dataset_id"] == "stale-dataset"


def test_bootstrap_clears_malformed_saved_dataset_metadata(monkeypatch):
    df = pd.DataFrame(
        {"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}
    )
    malformed_meta = {
        "name": "Saved sample",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state: dict = {}
    _stub_streamlit_state(monkeypatch, session_state)

    cleared: dict[str, object] = {"dataset": 0, "levels_dataset_id": None}
    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-abc")
    monkeypatch.setattr(app_state, "load_dataset", lambda dataset_id: (df, malformed_meta))
    monkeypatch.setattr(
        app_state, "clear_active_dataset_id", lambda: cleared.__setitem__("dataset", 1)
    )
    monkeypatch.setattr(
        app_state,
        "clear_active_levels_hash",
        lambda dataset_id: cleared.__setitem__("levels_dataset_id", dataset_id),
    )

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is False
    assert "data" not in session_state
    assert cleared["dataset"] == 1
    assert cleared["levels_dataset_id"] == "dataset-abc"
