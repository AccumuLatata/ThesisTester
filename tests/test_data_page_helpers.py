from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd
import pytest


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
        "expander",
        "download_button",
        "write",
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


def test_subtimeframe_upload_signature_includes_explicit_profile():
    data_page = _import_data_page_module({})

    class UploadedFile:
        def getvalue(self):
            return b"same-content"

    upload = UploadedFile()
    assert data_page._upload_signature(
        upload, format_profile="canonical"
    ) != data_page._upload_signature(upload, format_profile="quantower_history_exporter")


def test_primary_duplicate_report_is_diagnostic_only_when_validation_detects_duplicates():
    data_page = _import_data_page_module({})
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-05 09:30:00+00:00", "2026-01-05 09:30:00+00:00"]),
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 99.0],
            "close": [100.5, 100.5],
            "volume": [10, 12],
        }
    )
    duplicate_report = data_page.validate_ohlcv(frame)

    report = data_page._primary_duplicate_report(frame, duplicate_report)

    assert report is not None
    assert report["volume_conflict"].tolist() == [True, True]
    assert (
        data_page._primary_duplicate_report(
            frame.drop(index=1), data_page.validate_ohlcv(frame.drop(index=1))
        )
        is None
    )


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


def test_load_subtimeframe_upload_returns_duplicate_diagnostic(tmp_path):
    data_page = _import_data_page_module({})
    parent, subtimeframe = _parent_and_subtimeframe_frames()
    path = tmp_path / "duplicate_subtimeframe.csv"
    pd.concat([subtimeframe, subtimeframe.iloc[[0]]], ignore_index=True).to_csv(path, index=False)

    with pytest.raises(data_page.SubtimeframeDuplicateTimestampError) as exc_info:
        data_page._load_subtimeframe_upload(
            path,
            parent_df=parent,
            instrument="ES",
            source_timezone="America/New_York",
            exchange_timezone="America/New_York",
            format_profile="canonical",
        )

    report = exc_info.value.report
    assert len(report) == 2
    assert report["exact_duplicate_group"].tolist() == [True, True]


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


def test_failed_subtimeframe_upload_clears_stale_loaded_data(monkeypatch):
    session_state = {
        "subtimeframe_data": "stale-data",
        "subtimeframe_interval": "15s",
        "subtimeframe_fallback_parent_bars": [{"bar_index": 1}],
        "_subtimeframe_upload_signature": "old-upload",
        "_subtimeframe_diagnostic_data": "diagnostic-lower",
        "trades": "stale-trades",
        "grid_results": "stale-grid",
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._clear_loaded_subtimeframe_after_failed_upload()

    for key in (
        "subtimeframe_data",
        "subtimeframe_interval",
        "subtimeframe_fallback_parent_bars",
        "_subtimeframe_upload_signature",
        "_subtimeframe_diagnostic_data",
        "trades",
        "grid_results",
    ):
        assert key not in session_state


def test_prepare_15s_primary_dataset_installs_atomic_parent_and_source(tmp_path, monkeypatch):
    from thesistester.engine.intrabar import prepare_subtimeframe_context

    data_page = _import_data_page_module({})
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])
    vendor = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "vendor"
        / "quantower_history_exporter_15s.csv"
    )

    prepared = data_page._prepare_15s_primary_dataset(
        vendor,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
    )

    assert prepared.base_interval == "1min"
    assert prepared.subtimeframe_interval == "15s"
    assert len(prepared.parent_df) == 2
    assert len(prepared.source_df) == 8
    assert prepared.dropped_buckets.empty
    assert prepared.provenance["ingestion_mode"] == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    prepare_subtimeframe_context(
        prepared.parent_df,
        prepared.source_df,
        tick_size=0.25,
    )

    # Mimic Upload-CSV: radio already bound to 15s-primary before install.
    # Streamlit raises if that widget key is rewritten on the same run.
    class _WidgetBoundSessionState(dict):
        def __setitem__(self, key, value):  # noqa: ANN001
            if key == "data_ingestion_mode_selector" and key in self:
                raise RuntimeError(
                    "st.session_state.data_ingestion_mode_selector cannot be "
                    "modified after the widget with key "
                    "data_ingestion_mode_selector is instantiated."
                )
            super().__setitem__(key, value)

    bound_state = _WidgetBoundSessionState(
        {
            "data_ingestion_mode_selector": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        }
    )
    sys.modules["streamlit"].session_state = bound_state
    data_page = _import_data_page_module(bound_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])
    monkeypatch.setattr(data_page, "ensure_display_timezone", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)

    data_page._install_15s_primary_dataset(
        prepared,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        resampled_data={},
    )

    assert bound_state["base_interval"] == "1min"
    assert bound_state["subtimeframe_interval"] == "15s"
    assert bound_state["subtimeframe_format_profile"] == "quantower_history_exporter"
    assert len(bound_state["data"]) == 2
    assert len(bound_state["subtimeframe_data"]) == 8
    assert bound_state[data_page.INGESTION_PROVENANCE_KEY]["derivation_policy"]
    assert data_page._is_15s_primary_session(bound_state)
    assert (
        bound_state["data_ingestion_mode_selector"]
        == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    )
    assert bound_state[data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY] is True


def test_prepare_15s_primary_dataset_drops_partial_minutes(tmp_path):
    data_page = _import_data_page_module({})
    path = tmp_path / "partial_quantower_15s.csv"
    path.write_text(
        "Time left;Time right;Open;High;Low;Close;Volume;\n"
        "2026-06-02 09:30:00.000;2026-06-02 09:30:14.999;100;101;99;100;2;\n"
        "2026-06-02 09:30:15.000;2026-06-02 09:30:29.999;100;103;100;102;3;\n"
        "2026-06-02 09:30:30.000;2026-06-02 09:30:44.999;102;104;101;103;2;\n"
        # Missing 09:30:45 — incomplete first minute.
        "2026-06-02 09:31:00.000;2026-06-02 09:31:14.999;102;103;101;102;3;\n"
        "2026-06-02 09:31:15.000;2026-06-02 09:31:29.999;102;105;102;104;4;\n"
        "2026-06-02 09:31:30.000;2026-06-02 09:31:44.999;104;106;103;105;2;\n"
        "2026-06-02 09:31:45.000;2026-06-02 09:31:59.999;105;105;101;105;3;\n"
        "2026-06-02 09:32:00.000;2026-06-02 09:32:14.999;105;106;104;105;1;\n"
        "2026-06-02 09:32:15.000;2026-06-02 09:32:29.999;105;107;105;106;1;\n"
        "2026-06-02 09:32:30.000;2026-06-02 09:32:44.999;106;108;105;107;1;\n"
        "2026-06-02 09:32:45.000;2026-06-02 09:32:59.999;107;107;106;107;1;\n"
    )

    prepared = data_page._prepare_15s_primary_dataset(
        path,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
    )

    assert [ts.isoformat() for ts in prepared.parent_df["timestamp"]] == [
        "2026-06-02T09:31:00-04:00",
        "2026-06-02T09:32:00-04:00",
    ]
    assert list(prepared.dropped_buckets["reason"]) == ["incomplete_coverage"]
    assert prepared.provenance["dropped_parent_bucket_count"] == 1
    assert "09:30" not in ",".join(prepared.parent_df["timestamp"].astype(str))

    with pytest.raises(ValueError, match="supports only these explicit"):
        data_page._prepare_15s_primary_dataset(
            path,
            instrument="ES",
            source_timezone="America/New_York",
            exchange_timezone="America/New_York",
            format_profile="canonical",
        )


def test_clear_dataset_dependent_state_clears_15s_primary_keys(monkeypatch):
    session_state = {
        "levels": "x",
        "subtimeframe_data": "lower",
        "subtimeframe_interval": "15s",
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
        "derived_parent_diagnostics": "diag",
        "trades": "stale",
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._clear_dataset_dependent_state()

    for key in (
        "levels",
        "subtimeframe_data",
        "subtimeframe_interval",
        "subtimeframe_format_profile",
        "ingestion_provenance",
        "derived_parent_diagnostics",
        "trades",
    ):
        assert key not in session_state


def test_on_ingestion_mode_change_clears_15s_primary_session(monkeypatch):
    session_state = {
        "data_source_selector": "Upload CSV",
        "data_format_profile_selector": "quantower_history_exporter",
        "data_instrument_selector": "ES",
        "data_ingestion_mode_selector": "primary",
        "data": "keep-primary-frame",
        "dataset_id": "same-id",
        "levels": "x",
        "subtimeframe_data": "lower",
        "subtimeframe_interval": "15s",
        "subtimeframe_format_profile": "quantower_history_exporter",
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
        "derived_parent_diagnostics": "diag",
        "trades": "stale",
        "_primary_csv_uploader_nonce": 3,
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._on_ingestion_mode_change()

    assert session_state["data"] == "keep-primary-frame"
    assert session_state["dataset_id"] == "same-id"
    assert not data_page._is_15s_primary_session(session_state)
    for key in (
        "levels",
        "subtimeframe_data",
        "subtimeframe_interval",
        "subtimeframe_format_profile",
        "ingestion_provenance",
        "derived_parent_diagnostics",
        "trades",
    ):
        assert key not in session_state
    assert "data_source_timezone_selector" in session_state
    # Stale uploader widget value must be invalidated so a Quantower 15s CSV
    # cannot be re-ingested on the legacy one-minute primary path.
    assert session_state[data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY] == 4


def test_invalidate_primary_csv_uploader_bumps_nonce(monkeypatch):
    session_state = {}
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._invalidate_primary_csv_uploader()
    assert session_state[data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY] == 1
    data_page._invalidate_primary_csv_uploader()
    assert session_state[data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY] == 2


def test_leave_15s_primary_session_if_active_clears_when_latched(monkeypatch):
    session_state = {
        "data": "parent",
        "dataset_id": "unchanged-id",
        "subtimeframe_data": "lower",
        "subtimeframe_interval": "15s",
        "ingestion_provenance": {"ingestion_mode": "15s_primary_derive_1m"},
        "derived_parent_diagnostics": "diag",
        "trades": "stale",
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._leave_15s_primary_session_if_active()

    assert session_state["data"] == "parent"
    assert session_state["dataset_id"] == "unchanged-id"
    assert not data_page._is_15s_primary_session(session_state)
    assert "ingestion_provenance" not in session_state
    assert "subtimeframe_data" not in session_state
    assert "derived_parent_diagnostics" not in session_state
    assert "trades" not in session_state

    # Idempotent when not in a 15s-primary session (legacy lower upload stays).
    session_state["subtimeframe_data"] = "legacy-lower"
    session_state["trades"] = "keep"
    data_page._leave_15s_primary_session_if_active()
    assert session_state["subtimeframe_data"] == "legacy-lower"
    assert session_state["trades"] == "keep"


def test_hide_legacy_subtimeframe_uploader_follows_mode_not_only_provenance():
    """Dual-upload must hide when the radio says 15s-primary, even without provenance.

    Repro: switch to derive-from-15s (clears provenance) while stale one-minute
    ``data`` remains — the mode selector and uploader visibility must agree.
    """
    data_page = _import_data_page_module({})

    # Selected mode alone is enough (stale 1m data, no active 15s session).
    assert data_page._hide_legacy_subtimeframe_uploader(
        data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M, session_state={}
    )
    assert data_page._hide_legacy_subtimeframe_uploader(
        data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        session_state={"data": "stale-one-minute"},
    )

    # Legacy primary keeps dual-upload unless a latched 15s-primary session.
    assert not data_page._hide_legacy_subtimeframe_uploader(
        data_page.INGESTION_MODE_PRIMARY, session_state={}
    )
    assert data_page._hide_legacy_subtimeframe_uploader(
        data_page.INGESTION_MODE_PRIMARY,
        session_state={
            "ingestion_provenance": {
                "ingestion_mode": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
            }
        },
    )


def test_data_page_exposes_15s_primary_mode_labels():
    data_page = _import_data_page_module({})
    page_text = pathlib.Path(data_page.__file__).read_text(encoding="utf-8")

    assert (
        data_page.INGESTION_MODE_LABELS[data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M]
        == "Recommended: 15-second primary — derive one-minute canonical"
    )
    assert (
        data_page.INGESTION_MODE_LABELS[data_page.INGESTION_MODE_PRIMARY]
        == "Legacy: one-minute primary (advanced)"
    )
    assert list(data_page.INGESTION_MODE_LABELS) == [
        data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        data_page.INGESTION_MODE_PRIMARY,
    ]
    assert data_page.DEFAULT_UPLOAD_INGESTION_MODE == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert data_page.LEGACY_SUBTIMEFRAME_EXPANDER_TITLE == "Legacy dual-upload (optional)"
    assert "DEFAULT_UPLOAD_INGESTION_MODE" in page_text
    assert "Legacy dual-upload (optional)" in page_text
    assert "Sample data remains the legacy one-minute fixture path." in page_text
    assert "quantower_history_exporter" in data_page.DERIVE_15S_SUPPORTED_PROFILES
    assert data_page.INGESTION_MODE_PRIMARY == "primary"
    assert "on_change=_on_ingestion_mode_change" in page_text
    assert "_leave_15s_primary_session_if_active()" in page_text
    assert "_invalidate_primary_csv_uploader()" in page_text
    assert 'key=f"primary_csv_upload_{primary_uploader_nonce}"' in page_text
    assert "_hide_legacy_subtimeframe_uploader(ingestion_mode)" in page_text


def test_align_upload_ingestion_mode_with_legacy_and_empty_sessions(monkeypatch):
    """Upload-CSV align: recommend 15s when empty; primary after Sample/legacy."""
    data_page = _import_data_page_module({})
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    # Empty session keeps the recommended Upload-CSV default.
    empty: dict = {}
    assert (
        data_page._align_upload_ingestion_mode_with_session(empty)
        == data_page.DEFAULT_UPLOAD_INGESTION_MODE
    )
    assert empty["data_ingestion_mode_selector"] == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    assert empty[data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY] is False

    # Legacy one-minute session (e.g. after Sample) realigns off the default.
    legacy = {
        "data": "one-minute-frame",
        "data_ingestion_mode_selector": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY: False,
    }
    assert (
        data_page._align_upload_ingestion_mode_with_session(legacy)
        == data_page.INGESTION_MODE_PRIMARY
    )
    assert legacy["data_ingestion_mode_selector"] == data_page.INGESTION_MODE_PRIMARY
    assert not data_page._hide_legacy_subtimeframe_uploader(
        legacy["data_ingestion_mode_selector"], session_state=legacy
    )

    # Explicit user choice of 15s-primary is preserved even with stale 1m data.
    explicit = {
        "data": "stale-one-minute",
        "data_ingestion_mode_selector": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY: True,
    }
    assert (
        data_page._align_upload_ingestion_mode_with_session(explicit)
        == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    )
    assert data_page._hide_legacy_subtimeframe_uploader(
        explicit["data_ingestion_mode_selector"], session_state=explicit
    )

    # Sample render must not write the Upload selector (Source defaults to Sample).
    page_text = pathlib.Path(data_page.__file__).read_text(encoding="utf-8")
    assert "Do not write data_ingestion_mode_selector here" in page_text
    with pytest.raises(ValueError, match="Unsupported ingestion mode"):
        data_page._sync_upload_ingestion_mode_selector("bogus", session_state={})


def test_sync_upload_ingestion_mode_selector_skips_redundant_widget_write(monkeypatch):
    """Post-radio CSV install must not rewrite a bound equal selector key."""
    data_page = _import_data_page_module({})
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    class _WidgetBoundSessionState(dict):
        def __setitem__(self, key, value):  # noqa: ANN001
            if key == "data_ingestion_mode_selector" and key in self:
                raise RuntimeError(
                    "cannot be modified after the widget with key "
                    "data_ingestion_mode_selector is instantiated."
                )
            super().__setitem__(key, value)

    bound = _WidgetBoundSessionState(
        {
            "data_ingestion_mode_selector": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        }
    )
    data_page._sync_upload_ingestion_mode_selector(
        data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
        session_state=bound,
        explicit=True,
    )
    assert (
        bound["data_ingestion_mode_selector"]
        == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    )
    assert bound[data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY] is True

    # Pre-widget / differing value still writes the selector key.
    mutable: dict = {
        "data_ingestion_mode_selector": data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    }
    data_page._sync_upload_ingestion_mode_selector(
        data_page.INGESTION_MODE_PRIMARY,
        session_state=mutable,
        explicit=False,
    )
    assert mutable["data_ingestion_mode_selector"] == data_page.INGESTION_MODE_PRIMARY
    assert mutable[data_page.UPLOAD_INGESTION_MODE_EXPLICIT_KEY] is False


def test_upload_csv_default_ingestion_mode_is_15s_primary_not_api_default():
    """Streamlit Upload-CSV recommends 15s-primary; API absent mode stays primary."""
    data_page = _import_data_page_module({})
    from thesistester.api import validate_run_spec

    assert data_page.DEFAULT_UPLOAD_INGESTION_MODE == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    # Headless RunSpec without ingestion_mode remains the legacy primary contract.
    validate_run_spec(
        {
            "name": "legacy_default",
            "dataset": {
                "path": "bars.csv",
                "instrument": "ES",
                "source_timezone": "America/New_York",
            },
            "levels": {
                "sma_lengths": [2],
                "ema_lengths": [2],
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["1min"],
                "vwap_windows": [],
                "poc_windows": [],
            },
            "setup": {
                "name": "legacy_default",
                "description": "API default remains primary",
                "instrument": "ES",
                "selected_levels": ["dOpen", "RTH_Open"],
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger": "touch",
                "trigger_timeframe": "base",
                "direction": "both",
                "confluence_mode": "global_cluster",
                "anchor_level": None,
                "confluence_rules": [],
                "min_valid_confluences": 1,
                "trigger_params": {},
                "otf_filter": None,
            },
            "backtest": {
                "stop_loss_ticks": 2,
                "take_profit_ticks": 3,
                "exposure_policy": "single_position",
            },
            "grid": {"enabled": False},
            "validation": {"enabled": False},
        }
    )
