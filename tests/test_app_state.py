import types

import pandas as pd

from thesistester import app_state


def _stub_streamlit_state(state: dict):
    app_state.st = types.SimpleNamespace(session_state=state)  # type: ignore[assignment]


def test_bootstrap_does_not_override_existing_data(monkeypatch):
    session_state = {"data": "already-loaded"}
    _stub_streamlit_state(session_state)

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "dataset-123")
    monkeypatch.setattr(
        app_state,
        "load_dataset",
        lambda dataset_id: (_ for _ in ()).throw(AssertionError("load_dataset should not be called")),
    )

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is False
    assert session_state["data"] == "already-loaded"


def test_bootstrap_restores_valid_saved_dataset(monkeypatch):
    df = pd.DataFrame({"timestamp": [1], "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})
    meta = {
        "dataset_id": "dataset-abc",
        "name": "Saved sample",
        "instrument": "ES",
        "base_interval": "1min",
        "source_timezone": "America/New_York",
        "exchange_timezone": "America/New_York",
    }
    session_state: dict = {}
    _stub_streamlit_state(session_state)

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


def test_bootstrap_clears_stale_saved_dataset_pointer(monkeypatch):
    session_state: dict = {}
    _stub_streamlit_state(session_state)

    cleared: dict[str, object] = {"dataset": 0, "levels_dataset_id": None}

    monkeypatch.setattr(app_state, "get_active_dataset_id", lambda: "stale-dataset")

    def _raise_stale(_dataset_id: str):
        raise FileNotFoundError("missing dataset")

    monkeypatch.setattr(app_state, "load_dataset", _raise_stale)
    monkeypatch.setattr(app_state, "clear_active_dataset_id", lambda: cleared.__setitem__("dataset", 1))
    monkeypatch.setattr(
        app_state,
        "clear_active_levels_hash",
        lambda dataset_id: cleared.__setitem__("levels_dataset_id", dataset_id),
    )

    restored = app_state.bootstrap_active_saved_dataset()

    assert restored is False
    assert cleared["dataset"] == 1
    assert cleared["levels_dataset_id"] == "stale-dataset"
