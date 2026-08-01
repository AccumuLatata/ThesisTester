from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd


def _parent_and_subtimeframe_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for minute in pd.date_range(
        "2024-01-02 09:30:00",
        periods=2,
        freq="1min",
        tz="America/New_York",
    ):
        rows.extend(
            [
                (minute, 100.0, 101.0, 100.0, 100.5),
                (minute + pd.Timedelta(seconds=15), 100.5, 100.75, 99.5, 100.0),
                (minute + pd.Timedelta(seconds=30), 100.0, 100.25, 99.75, 100.25),
                (minute + pd.Timedelta(seconds=45), 100.25, 100.5, 100.0, 100.4),
            ]
        )
    subtimeframe = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close"],
    ).assign(volume=25)
    parent = (
        subtimeframe.assign(parent_timestamp=subtimeframe["timestamp"].dt.floor("1min"))
        .groupby("parent_timestamp", sort=True)
        .agg(
            timestamp=("timestamp", "first"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index(drop=True)
    )
    return parent, subtimeframe


def _make_streamlit_stub(session_state: dict) -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    def _cache_data(*args, **kwargs):
        def _decorator(fn):
            return fn

        return _decorator

    for name in (
        "title",
        "caption",
        "subheader",
        "warning",
        "success",
        "error",
        "info",
        "markdown",
        "stop",
        "rerun",
        "selectbox",
        "button",
        "radio",
        "multiselect",
        "file_uploader",
        "dataframe",
        "metric",
        "text_input",
        "columns",
        "divider",
    ):
        setattr(st, name, _noop)
    st.cache_data = _cache_data  # type: ignore[assignment]
    st.session_state = session_state  # type: ignore[assignment]
    return st


def _import_data_page_module(session_state: dict):
    stub = _make_streamlit_stub(session_state)
    sys.modules["streamlit"] = stub
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "1_Data.py"
    spec = importlib.util.spec_from_file_location("data_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        pass
    return mod


def test_set_active_dataset_state_clears_mismatched_active_setup(monkeypatch):
    session_state = {
        "dataset_id": "dataset-old",
        "setup_config": {"name": "old setup", "dataset_id": "dataset-old"},
        "_setup_builder_editor_config": {"name": "draft setup", "dataset_id": "dataset-old"},
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "_clear_dataset_dependent_state", lambda: None)
    monkeypatch.setattr(data_page, "ensure_display_timezone", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)

    df = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    data_page._set_active_dataset_state(
        df,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        resampled_data={},
        saved_dataset_id="dataset-new",
    )

    assert "setup_config" not in session_state
    assert "_setup_builder_editor_config" not in session_state


def test_ninjatrader_is_a_raw_capture_profile():
    data_page = _import_data_page_module({})

    assert "ninjatrader" in data_page.RAW_CAPTURE_PROFILES


def test_ninjatrader_default_source_timezone_is_utc():
    data_page = _import_data_page_module({})

    assert data_page._default_source_timezone("ninjatrader", "America/New_York") == "UTC"
    assert data_page._default_source_timezone("canonical", "America/New_York") == "America/New_York"


def test_load_subtimeframe_upload_accepts_reconciling_canonical_bars(tmp_path):
    data_page = _import_data_page_module({})
    parent, subtimeframe = _parent_and_subtimeframe_frames()
    path = tmp_path / "subtimeframe.csv"
    subtimeframe.to_csv(path, index=False)

    loaded, interval, fallback_bars = data_page._load_subtimeframe_upload(
        path,
        parent_df=parent,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    )

    assert interval == "15s"
    assert len(loaded) == len(subtimeframe)
    assert fallback_bars == []


def test_load_subtimeframe_upload_accepts_incomplete_bars_for_conservative_model(tmp_path):
    data_page = _import_data_page_module({})
    parent, subtimeframe = _parent_and_subtimeframe_frames()
    path = tmp_path / "subtimeframe.csv"
    subtimeframe.drop(index=1).to_csv(path, index=False)

    _, interval, fallback_bars = data_page._load_subtimeframe_upload(
        path,
        parent_df=parent,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="canonical",
    )

    assert interval == "15s"
    assert fallback_bars == [
        {
            "bar_index": 0,
            "timestamp": "2024-01-02 09:30:00-05:00",
            "reason": "incomplete coverage: expected 4, observed 3",
        }
    ]


def test_load_subtimeframe_upload_rejects_parent_ohlc_mismatch(tmp_path):
    data_page = _import_data_page_module({})
    parent, subtimeframe = _parent_and_subtimeframe_frames()
    subtimeframe.loc[0, "high"] = 102.0
    path = tmp_path / "subtimeframe.csv"
    subtimeframe.to_csv(path, index=False)

    try:
        data_page._load_subtimeframe_upload(
            path,
            parent_df=parent,
            instrument="ES",
            source_timezone="America/New_York",
            exchange_timezone="America/New_York",
            format_profile="canonical",
        )
    except ValueError as exc:
        assert "does not reconcile" in str(exc)
    else:
        raise AssertionError("Expected non-reconciling lower bars to be rejected.")


def test_remove_subtimeframe_resets_uploader_for_same_file_reupload(monkeypatch):
    session_state = {
        "data": "main-data",
        "levels": "levels",
        "signals": "signals",
        "trades": "stale-trades",
        "grid_results": "stale-grid",
        "_subtimeframe_uploader_nonce": 4,
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])
    subtimeframe = pd.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": []})

    data_page._set_subtimeframe_state(
        subtimeframe,
        interval="15s",
        upload_signature="signature",
        fallback_bars=[],
    )

    assert session_state["subtimeframe_data"] is subtimeframe
    assert session_state["subtimeframe_interval"] == "15s"
    assert "trades" not in session_state
    assert "grid_results" not in session_state
    assert session_state["data"] == "main-data"
    assert session_state["levels"] == "levels"
    assert session_state["signals"] == "signals"

    data_page._clear_subtimeframe_state()

    assert "subtimeframe_data" not in session_state
    assert "subtimeframe_interval" not in session_state
    assert session_state[data_page.SUBTIMEFRAME_UPLOADER_NONCE_KEY] == 5

    data_page._set_subtimeframe_state(
        subtimeframe,
        interval="15s",
        upload_signature="signature",
        fallback_bars=[],
    )

    assert session_state["subtimeframe_data"] is subtimeframe
