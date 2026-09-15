from __future__ import annotations

import ast
import hashlib
import importlib.util
import pathlib
import sys
import types

import pandas as pd
import pytest

from thesistester.reporting import build_otf_filter_metadata


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
        "text_area",
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


def test_prepare_15s_primary_dataset_retains_sparse_minutes(tmp_path):
    data_page = _import_data_page_module({})
    path = tmp_path / "partial_quantower_15s.csv"
    path.write_text(
        "Time left;Time right;Open;High;Low;Close;Volume;\n"
        "2026-06-02 09:30:00.000;2026-06-02 09:30:14.999;100;101;99;100;2;\n"
        "2026-06-02 09:30:15.000;2026-06-02 09:30:29.999;100;103;100;102;3;\n"
        "2026-06-02 09:30:30.000;2026-06-02 09:30:44.999;102;104;101;103;2;\n"
        # Missing 09:30:45 — sparse first minute (Rithmic/Quantower trade-only).
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
        "2026-06-02T09:30:00-04:00",
        "2026-06-02T09:31:00-04:00",
        "2026-06-02T09:32:00-04:00",
    ]
    assert prepared.dropped_buckets.empty
    assert list(prepared.sparse_buckets["reason"]) == ["incomplete_coverage"]
    assert prepared.provenance["sparse_parent_bucket_count"] == 1
    assert prepared.provenance["dropped_parent_bucket_count"] == 0
    assert "09:30" in ",".join(prepared.parent_df["timestamp"].astype(str))

    with pytest.raises(ValueError, match="supports only these explicit"):
        data_page._prepare_15s_primary_dataset(
            path,
            instrument="ES",
            source_timezone="America/New_York",
            exchange_timezone="America/New_York",
            format_profile="canonical",
        )


def test_prepare_15s_primary_dataset_resolves_ohlc_identical_source_duplicates(tmp_path):
    data_page = _import_data_page_module({})
    vendor = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "vendor"
        / "quantower_history_exporter_15s.csv"
    )
    path = tmp_path / "quantower_15s_dup.csv"
    rows = vendor.read_text(encoding="utf-8").splitlines()
    rows.append("2026-06-02 09:30:00.000;2026-06-02 09:30:14.999;100;101;100;99;100;100;99;0;100;")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    prepared = data_page._prepare_15s_primary_dataset(
        path,
        instrument="ES",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        format_profile="quantower_history_exporter",
    )

    assert len(prepared.source_df) == 8
    assert len(prepared.parent_df) == 2
    assert float(prepared.parent_df["volume"].iloc[0]) == 10.0
    assert prepared.provenance["source_duplicate_groups_resolved"] == 1
    assert prepared.provenance["source_duplicate_rows_discarded"] == 1
    source_codes = {issue.code for issue in prepared.source_report.issues}
    assert "duplicate_timestamps" not in source_codes
    assert "non_monotonic_before_sort" in source_codes


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


def test_tick_attach_does_not_replace_primary_data():
    parent, _ = _parent_and_subtimeframe_frames()
    session_state = {"data": parent, "dataset_id": "keep-id"}
    data_page = _import_data_page_module(session_state)
    data_page._install_tick_paths(
        session_state,
        ["data/es_ticks.csv"],
        row_count=4,
        session_count=1,
        signature="data/es_ticks.csv",
    )
    assert session_state["data"] is parent
    assert session_state["dataset_id"] == "keep-id"
    assert session_state[data_page.TICK_PATHS_KEY] == ["data/es_ticks.csv"]
    assert session_state[data_page.TICK_ROW_COUNT_KEY] == 4
    assert session_state[data_page.TICK_SESSION_COUNT_KEY] == 1


def test_clear_dataset_dependent_state_clears_tick_paths(monkeypatch):
    parent, _ = _parent_and_subtimeframe_frames()
    session_state = {
        "data": parent,
        "dataset_id": "keep-id",
        "tick_paths": ["data/es_ticks.csv"],
        "tick_row_count": 4,
        "tick_session_count": 1,
        "tick_attach_warnings": ["stale"],
        "_tick_upload_signature": "sig",
        "levels": "x",
    }
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._clear_dataset_dependent_state()

    assert session_state["data"] is parent
    assert session_state["dataset_id"] == "keep-id"
    for key in (
        data_page.TICK_PATHS_KEY,
        data_page.TICK_ROW_COUNT_KEY,
        data_page.TICK_SESSION_COUNT_KEY,
        data_page.TICK_UPLOAD_SIGNATURE_KEY,
        data_page.TICK_WARNINGS_KEY,
        "levels",
    ):
        assert key not in session_state


# AH4 leftover set + Focus/OTF overlays that re-arm after a later Backtest/Report.
# A-7 residuals (otf_validation_* / skipped_signals / direction_collision_diagnostic)
# stay apply-clear only.
_QI1001_AH4_LEFTOVER_KEYS = (
    "focused_trades",
    "focused_equity_curve",
    "otf_filter_summary",
    "otf_filter_result",
    "backtest_otf_filter",
    "grid_otf_filter",
    "otf_rejected_signals",
    "otf_candidate_signals",
    "otf_accepted_signals",
    "signal_settings",
    "signal_settings_hash",
    "setup_config",
)
_QI1001_FOCUS_OVERLAY_KEYS = (
    "focus_entry_window",
    "focused_trade_summary",
    "focus_provenance",
    "focused_direction_summary",
)
_QI1001_DATASET_CLEAR_LEFTOVERS = (
    *_QI1001_AH4_LEFTOVER_KEYS,
    *_QI1001_FOCUS_OVERLAY_KEYS,
    "_setup_builder_editor_config",
    "display_timezone",
)
_QI1001_A7_APPLY_ONLY_KEYS = (
    "otf_validation_matrix",
    "otf_validation_config",
    "otf_validation_summary",
    "skipped_signals",
    "direction_collision_diagnostic",
)
_DATA_PAGE_SOURCE = pathlib.Path("pages/1_Data.py").read_text(encoding="utf-8")
_DATA_PAGE_HELPER_SOURCES = "\n".join(
    pathlib.Path(path).read_text(encoding="utf-8")
    for path in (
        "pages/1_Data.py",
        "thesistester/data_workspace_page_helpers.py",
        "thesistester/data_tick_page_helpers.py",
        "thesistester/data_subtimeframe_page_helpers.py",
        "thesistester/data_display_page_helpers.py",
        "thesistester/data_page_constants.py",
    )
)


def _qi1001_leftover_session(*, data, dataset_id: str) -> dict:
    """Seed leftovers that would arm Focus / Report OTF after a later Backtest."""
    return {
        "data": data,
        "dataset_id": dataset_id,
        "focused_trades": pd.DataFrame({"trade_id": [99]}),
        "focused_equity_curve": pd.DataFrame({"cum_r": [9.9]}),
        "focus_entry_window": {"enabled": True, "mode": "clock_range"},
        "focused_trade_summary": {"trade_count": 12, "expectancy_r": 9.9},
        "focus_provenance": {"trade_count_after": 12, "trade_count_before": 99},
        "focused_direction_summary": {"long": 1},
        "otf_filter_summary": {"leftover": True, "otf_rejected_signal_count": 12},
        "otf_filter_result": object(),
        "backtest_otf_filter": {
            "otf_filter_enabled": True,
            "otf_rejected_signal_count": 12,
            "otf_accepted_signal_count": 0,
            "candidate_signal_count": 12,
        },
        "grid_otf_filter": {"otf_filter_enabled": True, "otf_rejected_signal_count": 4},
        "otf_rejected_signals": pd.DataFrame({"signal_id": [1]}),
        "otf_candidate_signals": pd.DataFrame({"signal_id": [1]}),
        "otf_accepted_signals": pd.DataFrame({"signal_id": [1]}),
        "signal_settings": {"leftover": True},
        "signal_settings_hash": "leftover-hash",
        "setup_config": {"name": "matching setup", "dataset_id": "dataset-new"},
        "_setup_builder_editor_config": {"name": "draft setup", "dataset_id": "dataset-new"},
        "display_timezone": "UTC",
    }


def _focus_overlay_would_arm(session_state: dict) -> bool:
    """Backtest/Time arm Focus on window+summary, not focused_trades alone."""
    window = session_state.get("focus_entry_window")
    summary = session_state.get("focused_trade_summary")
    return isinstance(window, dict) and bool(window.get("enabled")) and isinstance(summary, dict)


def _module_function_def(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing module-level def {name}")


def _iter_direct_body(fn: ast.FunctionDef):
    """Walk ``fn`` body excluding nested function/class defs (A-1/A-6 class)."""
    stack = list(reversed(fn.body))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _clear_dataset_iterates_registry(source: str) -> None:
    """D-1: dataset-switch must iterate ``DATASET_CLEAR_KEYS`` and pop each key."""
    fn = _module_function_def(source, "_clear_dataset_dependent_state")
    for node in fn.body:
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.iter, ast.Name) or node.iter.id != "DATASET_CLEAR_KEYS":
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "pop"
            ):
                return
        raise AssertionError("_clear_dataset_dependent_state For DATASET_CLEAR_KEYS must pop")
    raise AssertionError("_clear_dataset_dependent_state must iterate DATASET_CLEAR_KEYS")


def _dataset_clear_source_literals() -> set[str]:
    """String literals on ``_DATASET_CLEAR_SOURCE`` (comment needles fail-closed)."""
    tree = ast.parse(pathlib.Path("thesistester/research_keys.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "_DATASET_CLEAR_SOURCE":
            continue
        if not isinstance(node.value, ast.Tuple):
            raise AssertionError("_DATASET_CLEAR_SOURCE must be a tuple of string literals")
        return {
            elt.value
            for elt in node.value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
    raise AssertionError("missing _DATASET_CLEAR_SOURCE")


def _assert_clear_list_literals(source: str) -> None:
    """AST-bind leftover keys to the D-1 registry. Comment needles fail-closed."""
    _clear_dataset_iterates_registry(source)
    from thesistester.research_keys import DATASET_CLEAR_KEYS, RESEARCH_KEY_BY_NAME

    literals = _dataset_clear_source_literals()
    missing = [key for key in _QI1001_DATASET_CLEAR_LEFTOVERS if key not in literals]
    assert missing == [], f"_DATASET_CLEAR_SOURCE missing literals {missing}"
    leaked = [key for key in _QI1001_A7_APPLY_ONLY_KEYS if key in literals]
    assert leaked == [], f"A-7 residuals must stay apply-clear only, leaked {leaked}"
    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.dataset_clear, f"{key} must be dataset_clear"
        assert key in DATASET_CLEAR_KEYS
    for key in _QI1001_A7_APPLY_ONLY_KEYS:
        spec = RESEARCH_KEY_BY_NAME[key]
        assert spec.apply_clear and spec.sticky and not spec.dataset_clear, key


def _is_reset_display_timezone_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "reset_display_timezone":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "reset_display_timezone"


def _reset_binds_exchange_timezone_arg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "exchange_timezone":
            continue
        val = kw.value
        if isinstance(val, ast.Name) and val.id == "exchange_timezone":
            return True
        if (
            isinstance(val, ast.Call)
            and isinstance(val.func, ast.Attribute)
            and val.func.attr == "get"
            and val.args
            and isinstance(val.args[0], ast.Constant)
            and val.args[0].value == "exchange_timezone"
        ):
            return True
    return False


def _assert_set_active_resets_display_timezone(source: str) -> None:
    """Switch path must call ``reset_display_timezone`` (ensure-only fails closed)."""
    fn = _module_function_def(source, "_set_active_dataset_state")
    for node in _iter_direct_body(fn):
        if _is_reset_display_timezone_call(node) and _reset_binds_exchange_timezone_arg(node):
            return
    raise AssertionError(
        "_set_active_dataset_state must call reset_display_timezone("
        "exchange_timezone=exchange_timezone) on dataset switch"
    )


def test_clear_dataset_dependent_state_clears_ah4_leftover_set(monkeypatch):
    """QI-10-01 / A-8: dataset-switch leftover set must pop; data/dataset_id stay."""
    kept_data = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    session_state = _qi1001_leftover_session(data=kept_data, dataset_id="keep-id")
    session_state["setup_config"] = {"name": "old setup", "dataset_id": "keep-id"}
    assert _focus_overlay_would_arm(session_state)
    assert build_otf_filter_metadata(session_state)["available"] is True
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "st", sys.modules["streamlit"])

    data_page._clear_dataset_dependent_state()

    assert session_state["data"] is kept_data
    assert session_state["dataset_id"] == "keep-id"
    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        assert key not in session_state, f"{key} leftover survived dataset-dependent clear"
    assert not _focus_overlay_would_arm(session_state)
    assert build_otf_filter_metadata(session_state)["available"] is False


def test_set_active_dataset_state_clears_ah4_leftover_set(monkeypatch):
    """QI-10-01 / A-8: load/switch dataset leaves no AH4 leftover; display TZ rebinds."""
    previous = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    session_state = _qi1001_leftover_session(data=previous, dataset_id="dataset-old")
    # Matching new dataset_id would survive the mismatch-only pop; A-8 must still clear.
    assert session_state["setup_config"]["dataset_id"] == "dataset-new"
    assert _focus_overlay_would_arm(session_state)
    assert build_otf_filter_metadata(session_state)["available"] is True
    data_page = _import_data_page_module(session_state)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)

    replacement = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-01 09:30:00", periods=2, freq="1min", tz="America/New_York"
            ),
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [5, 6],
        }
    )
    data_page._set_active_dataset_state(
        replacement,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="Europe/Berlin",
        resampled_data={},
        saved_dataset_id="dataset-new",
    )

    assert session_state["data"] is replacement
    assert session_state["dataset_id"] == "dataset-new"
    assert session_state["exchange_timezone"] == "Europe/Berlin"
    assert session_state["display_timezone"] == "Europe/Berlin"
    for key in _QI1001_DATASET_CLEAR_LEFTOVERS:
        if key == "display_timezone":
            continue
        assert key not in session_state, f"{key} leftover survived dataset switch"
    assert not _focus_overlay_would_arm(session_state)
    assert build_otf_filter_metadata(session_state)["available"] is False


def test_qi1001_clear_list_and_switch_reset_are_ast_bound():
    """QI-10-01 / A-8: comment / ensure-only needles must not bind clear or switch reset."""
    _assert_clear_list_literals(_DATA_PAGE_SOURCE)
    _assert_set_active_resets_display_timezone(_DATA_PAGE_SOURCE)


def test_qi1001_clear_list_guard_ignores_comment_needles():
    fake = (
        "def _clear_dataset_dependent_state():\n"
        "    # focused_trades otf_filter_summary signal_settings setup_config\n"
        "    # focus_entry_window backtest_otf_filter display_timezone\n"
        '    for key in ["levels", "trades"]:\n'
        "        pass\n"
    )
    try:
        _assert_clear_list_literals(fake)
    except AssertionError as exc:
        assert "DATASET_CLEAR_KEYS" in str(exc)
    else:
        raise AssertionError("comment leftover keys must not satisfy the dataset-clear probe")


def test_qi1001_switch_reset_guard_rejects_ensure_only_and_nested_def():
    header = (
        "def _set_active_dataset_state(df, *, exchange_timezone=None):\n"
        "    previous_dataset_id = 'old'\n"
        "    dataset_id = 'new'\n"
    )
    ensure_only = header + (
        "    from thesistester.timezone_display import ensure_display_timezone\n"
        "    ensure_display_timezone(st.session_state, exchange_timezone=exchange_timezone)\n"
    )
    try:
        _assert_set_active_resets_display_timezone(ensure_only)
    except AssertionError as exc:
        assert "reset_display_timezone" in str(exc)
    else:
        raise AssertionError("ensure_display_timezone must not satisfy the switch reset probe")

    nested = header + (
        "    def helper():\n"
        "        reset_display_timezone(st.session_state, exchange_timezone=exchange_timezone)\n"
        "    ensure_display_timezone(st.session_state, exchange_timezone=exchange_timezone)\n"
    )
    try:
        _assert_set_active_resets_display_timezone(nested)
    except AssertionError as exc:
        assert "reset_display_timezone" in str(exc)
    else:
        raise AssertionError("nested unused reset_display_timezone must not satisfy the probe")


def test_validate_attached_tick_paths_uses_quantower_ticks(tmp_path):
    fixture = pathlib.Path(__file__).parent / "fixtures" / "ticks" / "rth_open_stub.csv"
    dest = tmp_path / "es_ticks.csv"
    dest.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    data_page = _import_data_page_module({})
    sessions, rows, warnings = data_page._validate_attached_tick_paths(
        [str(dest)],
        instrument="MNQ",
    )
    assert sessions == 1
    assert rows >= 1
    assert warnings == []
    payload = dest.read_bytes()
    persisted = data_page._persist_tick_uploads(
        [_Uploaded(dest.name, payload)],
        tmp_path / "uploads",
    )
    digest = hashlib.sha256(payload).hexdigest()[:12]
    assert persisted == [str((tmp_path / "uploads" / f"{digest}_{dest.name}").resolve())]


def test_persist_tick_uploads_keeps_same_basename_distinct(tmp_path):
    data_page = _import_data_page_module({})
    first = data_page._persist_tick_uploads(
        [_Uploaded("same.csv", b"jan-ticks")],
        tmp_path,
    )
    second = data_page._persist_tick_uploads(
        [_Uploaded("same.csv", b"feb-ticks")],
        tmp_path,
    )
    assert len(first) == 1 and len(second) == 1
    assert first[0] != second[0]
    assert pathlib.Path(first[0]).read_bytes() == b"jan-ticks"
    assert pathlib.Path(second[0]).read_bytes() == b"feb-ticks"


def test_dedupe_attached_tick_paths_drops_identical_content(tmp_path):
    data_page = _import_data_page_module({})
    left = tmp_path / "a.csv"
    right = tmp_path / "b.csv"
    left.write_bytes(b"same-bytes")
    right.write_bytes(b"same-bytes")
    unique, warnings = data_page._dedupe_attached_tick_paths([str(left), str(right)])
    assert unique == [str(left.resolve())]
    assert any("exact-duplicate" in item for item in warnings)


def test_resolve_existing_tick_path_checks_store_root(tmp_path, monkeypatch):
    data_page = _import_data_page_module({})
    dest = tmp_path / "nested" / "ticks.csv"
    dest.parent.mkdir()
    dest.write_text("Aggressor flag;Price;Volume;Time left;\n", encoding="utf-8")
    import thesistester.data_tick_page_helpers as tick_helpers

    monkeypatch.setattr(tick_helpers, "get_store_root", lambda: tmp_path)
    assert data_page._resolve_existing_tick_path("nested/ticks.csv") == dest.resolve()
    assert data_page._resolve_existing_tick_path("missing/ticks.csv") is None


def test_classify_typed_tick_path_rejects_outside_trusted_roots(tmp_path, monkeypatch):
    data_page = _import_data_page_module({})
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("Aggressor flag;Price;Volume;Time left;\n", encoding="utf-8")
    import thesistester.data_tick_page_helpers as tick_helpers

    monkeypatch.setattr(tick_helpers, "get_store_root", lambda: store)
    status, found = data_page._classify_typed_tick_path(str(outside))
    assert status == "outside"
    assert found is None
    assert data_page._resolve_existing_tick_path(str(outside)) is None
    escaped = store / ".." / "outside.csv"
    status, found = data_page._classify_typed_tick_path(str(escaped))
    assert status == "outside"
    assert found is None


def test_install_tick_paths_persists_warnings_across_clear():
    data_page = _import_data_page_module({})
    session_state: dict = {}
    data_page._install_tick_paths(
        session_state,
        ["data/es_ticks.csv"],
        row_count=4,
        session_count=1,
        signature="sig",
        warnings=["Filename window does not cover row timestamps: x.csv"],
    )
    assert session_state[data_page.TICK_WARNINGS_KEY] == [
        "Filename window does not cover row timestamps: x.csv"
    ]
    data_page._clear_tick_session_state(session_state)
    assert data_page.TICK_WARNINGS_KEY not in session_state
    assert data_page.TICK_PATHS_KEY not in session_state


class _Uploaded:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


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
    helper_text = _DATA_PAGE_HELPER_SOURCES
    assert "Sample data remains the legacy one-minute fixture path." in helper_text
    assert "quantower_history_exporter" in data_page.DERIVE_15S_SUPPORTED_PROFILES
    from thesistester.data import loader as loader_mod

    assert data_page.DERIVE_15S_SUPPORTED_PROFILES is loader_mod.DERIVE_15S_SUPPORTED_PROFILES
    assert data_page.SUBTIMEFRAME_FORMAT_PROFILES is loader_mod.SUBTIMEFRAME_FORMAT_PROFILES
    assert data_page.INGESTION_MODE_PRIMARY == "primary"
    assert "on_change=page._on_ingestion_mode_change" in helper_text
    assert "_leave_15s_primary_session_if_active()" in page_text
    assert "_invalidate_primary_csv_uploader()" in page_text
    assert 'key=f"primary_csv_upload_{primary_uploader_nonce}"' in helper_text
    assert "_hide_legacy_subtimeframe_uploader(ingestion_mode)" in helper_text
    assert "_render_tick_attach(" in helper_text
    assert helper_text.index("page._render_tick_attach(") > helper_text.index(
        "page._hide_legacy_subtimeframe_uploader(ingestion_mode)"
    )
    assert "Quantower tick-last (optional; VA / APOC / rolling POC)" in helper_text
    assert "Named VA / APOC / rolling POC refuse without ticks" in helper_text
    assert "APOC remains" not in helper_text
    assert "all-NaN without" not in helper_text
    assert "rolling POC remain 1m typical" not in helper_text
    assert "{digest}_{name}" in helper_text or 'f"{digest}_{name}"' in helper_text
    assert "TICK_WARNINGS_KEY" in page_text
    assert "Data-page attach does not feed classic Calculate" in helper_text
    assert "_classify_typed_tick_path(" in helper_text
    assert "outside the trusted local roots (cwd and store)" in helper_text
    from thesistester.data_subtimeframe_page_helpers import (
        _apply_new_subtimeframe_upload,
        _render_subtimeframe_compatibility_report,
        _render_subtimeframe_duplicate_report,
        _render_subtimeframe_loaded_state,
        render_subtimeframe_upload,
    )
    from thesistester.data_tick_page_helpers import (
        _handle_tick_attach_submit,
        _render_tick_attached_status,
        render_tick_attach,
    )
    from thesistester.data_workspace_page_helpers import (
        _bind_source_ingest_controls,
        _render_data_flash_messages,
        _render_loaded_dataset_actions,
        _render_saved_datasets,
        _render_source_apply_or_session,
        render_data_workspace,
    )

    assert callable(render_subtimeframe_upload)
    assert callable(_render_subtimeframe_duplicate_report)
    assert callable(_render_subtimeframe_compatibility_report)
    assert callable(_apply_new_subtimeframe_upload)
    assert callable(_render_subtimeframe_loaded_state)
    assert callable(render_tick_attach)
    assert callable(_handle_tick_attach_submit)
    assert callable(_render_tick_attached_status)
    assert callable(render_data_workspace)
    assert callable(_render_data_flash_messages)
    assert callable(_render_saved_datasets)
    assert callable(_bind_source_ingest_controls)
    assert callable(_render_source_apply_or_session)
    assert callable(_render_loaded_dataset_actions)


_WORKSPACE_ORCHESTRATOR_PANELS = frozenset(
    {
        "_render_data_flash_messages",
        "_render_saved_datasets",
        "_bind_source_ingest_controls",
        "_render_source_apply_or_session",
        "_render_loaded_dataset_actions",
        "_consume_data_page_source_invalidation",
        "bootstrap_active_saved_dataset",
    }
)
_WORKSPACE_PANEL_LITERALS = (
    "Local saved datasets",
    "Save dataset locally",
    "Ingestion mode",
)


def _call_names(fn: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def assert_workspace_orchestrator_split(source: str) -> None:
    """Orchestrator must call the panels and must not inline their chrome."""
    fn = _module_function_def(source, "render_data_workspace")
    missing = _WORKSPACE_ORCHESTRATOR_PANELS - _call_names(fn)
    if missing:
        raise AssertionError(f"workspace orchestrator missing panel calls {missing}")
    body = ast.get_source_segment(source, fn) or ""
    leaked = [needle for needle in _WORKSPACE_PANEL_LITERALS if needle in body]
    if leaked:
        raise AssertionError(f"render_data_workspace re-fused panel literals {leaked}")


def test_data_workspace_orchestrator_stays_split():
    """QI-01-01: do not re-fuse the upload/save tree into one F-grade function."""
    helper = pathlib.Path("thesistester/data_workspace_page_helpers.py").read_text(encoding="utf-8")
    assert_workspace_orchestrator_split(helper)


def test_data_workspace_orchestrator_guard_rejects_fused_tree():
    """Inline saved-dataset chrome must not bind as a split orchestrator."""
    fused = (
        "def render_data_workspace(st, *, page):\n"
        "    page._consume_data_page_source_invalidation()\n"
        "    bootstrap_active_saved_dataset()\n"
        "    _render_data_flash_messages(st)\n"
        "    _render_saved_datasets(st, page=page)\n"
        "    _bind_source_ingest_controls(st, page=page)\n"
        "    _render_source_apply_or_session(st, page=page)\n"
        "    _render_loaded_dataset_actions(st, page=page)\n"
        '    st.subheader("Local saved datasets")\n'
    )
    try:
        assert_workspace_orchestrator_split(fused)
    except AssertionError:
        pass
    else:
        raise AssertionError("fused Local saved datasets must invert the split probe")


def test_data_page_constants_match_page_assignments():
    """Helper keys must stay identical to pages/1_Data.py (session-key fork)."""
    page_tree = ast.parse(_DATA_PAGE_SOURCE)
    const_src = pathlib.Path("thesistester/data_page_constants.py").read_text(encoding="utf-8")
    const_tree = ast.parse(const_src)

    def _literal_assigns(tree: ast.AST) -> dict[str, object]:
        out: dict[str, object] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            try:
                out[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
        return out

    page_vals = _literal_assigns(page_tree)
    const_vals = _literal_assigns(const_tree)
    shared = sorted(set(page_vals) & set(const_vals))
    assert shared, "data_page_constants and 1_Data.py must share key literals"
    drifted = {
        name: (page_vals[name], const_vals[name])
        for name in shared
        if page_vals[name] != const_vals[name]
    }
    assert drifted == {}, f"page vs data_page_constants drift {drifted}"
    assert "FATAL_OHLCV_CODES" in shared


def test_data_workspace_binds_via_globals_proxy():
    """Helper tests exec the page without sys.modules; a modules lookup KeyErrors."""
    assert "class _DataPageModule" in _DATA_PAGE_SOURCE
    assert "page=_DataPageModule()" in _DATA_PAGE_SOURCE
    assert "sys.modules[__name__]" not in _DATA_PAGE_SOURCE


def test_bind_loader_profile_allow_list_falls_back_when_missing_or_mistyped():
    data_page = _import_data_page_module({})
    fallback = frozenset({"quantower_history_exporter"})

    class _StaleLoader:
        pass

    class _MistypedLoader:
        DERIVE_15S_SUPPORTED_PROFILES = "not-an-allow-list"

    assert (
        data_page._bind_loader_profile_allow_list(
            _StaleLoader(), "DERIVE_15S_SUPPORTED_PROFILES", fallback
        )
        is fallback
    )
    assert (
        data_page._bind_loader_profile_allow_list(
            _MistypedLoader(), "DERIVE_15S_SUPPORTED_PROFILES", fallback
        )
        is fallback
    )


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
    assert "Do not write data_ingestion_mode_selector here" in _DATA_PAGE_HELPER_SOURCES
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
    assert bound["data_ingestion_mode_selector"] == data_page.INGESTION_MODE_15S_PRIMARY_DERIVE_1M
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


def test_should_apply_source_dataset_sample_only_when_session_empty():
    data_page = _import_data_page_module({})

    assert data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data=False,
    )
    assert not data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data=True,
    )
    assert data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data=True,
        explicit_sample_load=True,
    )


def test_should_apply_source_dataset_upload_when_file_present():
    data_page = _import_data_page_module({})

    assert data_page._should_apply_source_dataset(
        file_present=True,
        source="Upload CSV",
        has_session_data=True,
    )
    assert not data_page._should_apply_source_dataset(
        file_present=False,
        source="Upload CSV",
        has_session_data=True,
    )
    assert not data_page._should_apply_source_dataset(
        file_present=False,
        source="Sample data",
        has_session_data=False,
    )


def test_should_apply_source_dataset_keeps_bundle_import_on_sample_navigation():
    """Reproduce: import bundle (session has data+levels) then open Data.

    Source defaults to Sample. Auto-applying sample would change dataset_id
    and clear levels. Navigation must keep the imported session.
    """
    data_page = _import_data_page_module(
        {
            "data": pd.DataFrame({"timestamp": [1]}),
            "levels": pd.DataFrame({"level": [1.0]}),
            "dataset_id": "bundle-dataset",
        }
    )

    assert not data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data=True,
    )


def test_bundle_import_then_data_navigation_keeps_levels(monkeypatch):
    """Full reported loop: import bundle, open Data with Source=Sample.

    Imported bars and levels must remain. Explicitly installing a different
    dataset still clears dependents (upload / Load sample data).
    """
    from thesistester.research_bundle import (
        DATA_PAGE_INVALIDATE_SOURCE_KEY,
        apply_research_bundle_to_session,
        build_research_bundle,
        load_research_bundle,
    )

    imported_data = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-06-01 09:30:00", periods=2, freq="1min", tz="America/New_York"
            ),
            "open": [1.0, 2.0],
            "high": [2.0, 3.0],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [10, 20],
        }
    )
    bundle_bytes = build_research_bundle(
        {
            "data": imported_data,
            "dataset_id": "bundle-dataset",
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": "America/New_York",
            "exchange_timezone": "America/New_York",
            "levels": pd.DataFrame({"level": [1.0]}),
            "session_levels": pd.DataFrame({"session": ["RTH"]}),
            "levels_settings": {"or_minutes": 5},
        }
    )
    session_state: dict = {}
    apply_research_bundle_to_session(load_research_bundle(bundle_bytes), session_state)
    assert session_state[DATA_PAGE_INVALIDATE_SOURCE_KEY] is True

    # Importing the page executes its body, including source invalidation.
    data_page = _import_data_page_module(session_state)
    assert DATA_PAGE_INVALIDATE_SOURCE_KEY not in session_state
    assert session_state.get(data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY, 0) >= 1
    assert session_state.get(data_page.SUBTIMEFRAME_UPLOADER_NONCE_KEY, 0) >= 1
    assert not data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data="data" in session_state,
    )
    assert "levels" in session_state
    assert session_state["dataset_id"] == "bundle-dataset"

    monkeypatch.setattr(data_page, "ensure_display_timezone", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)
    replacement = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-01 09:30:00", periods=2, freq="1min", tz="America/New_York"
            ),
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [5, 6],
        }
    )
    data_page._set_active_dataset_state(
        replacement,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        resampled_data={},
        saved_dataset_id=None,
    )
    assert "levels" not in session_state
    assert session_state["dataset_id"] != "bundle-dataset"


def test_consume_data_page_source_invalidation_increments_uploader_nonce():
    data_page = _import_data_page_module({})
    session_state = {
        data_page.DATA_PAGE_INVALIDATE_SOURCE_KEY: True,
        data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY: 2,
        data_page.SUBTIMEFRAME_UPLOADER_NONCE_KEY: 4,
        data_page.TICK_UPLOADER_NONCE_KEY: 1,
        data_page.TICK_PATHS_KEY: ["data/es_ticks.csv"],
        data_page.TICK_WARNINGS_KEY: ["stale warning"],
        data_page.SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY: "canonical:stale",
        data_page.SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY: "canonical:stale",
        data_page.SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY: "canonical:stale",
    }

    assert data_page._consume_data_page_source_invalidation(session_state) is True
    assert data_page.DATA_PAGE_INVALIDATE_SOURCE_KEY not in session_state
    assert session_state[data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY] == 3
    assert session_state[data_page.SUBTIMEFRAME_UPLOADER_NONCE_KEY] == 5
    assert session_state[data_page.TICK_UPLOADER_NONCE_KEY] == 2
    assert data_page.TICK_PATHS_KEY not in session_state
    assert data_page.TICK_WARNINGS_KEY not in session_state
    assert data_page.SUBTIMEFRAME_UPLOAD_SIGNATURE_KEY not in session_state
    assert data_page.SUBTIMEFRAME_DUPLICATE_SIGNATURE_KEY not in session_state
    assert data_page.SUBTIMEFRAME_COMPATIBILITY_SIGNATURE_KEY not in session_state
    assert data_page._consume_data_page_source_invalidation(session_state) is False
    assert session_state[data_page.PRIMARY_CSV_UPLOADER_NONCE_KEY] == 3
    assert session_state[data_page.SUBTIMEFRAME_UPLOADER_NONCE_KEY] == 5
    assert session_state[data_page.TICK_UPLOADER_NONCE_KEY] == 2


def test_session_has_primary_data_requires_dataframe():
    data_page = _import_data_page_module({})
    assert data_page._session_has_primary_data({}) is False
    assert data_page._session_has_primary_data({"data": None}) is False
    assert data_page._session_has_primary_data({"data": pd.DataFrame({"timestamp": [1]})}) is True


def test_ah4_dataset_less_bundle_blocks_data_page_auto_fill(monkeypatch):
    """Dataset-less import must not bootstrap A or auto-apply sample on Data."""
    from thesistester.research_bundle import (
        BUNDLE_IMPORT_OMITTED_DATA_KEY,
        apply_research_bundle_to_session,
        build_research_bundle,
        load_research_bundle,
    )

    session_state: dict = {BUNDLE_IMPORT_OMITTED_DATA_KEY: True}
    apply_research_bundle_to_session(
        load_research_bundle(
            build_research_bundle(
                {
                    "trades": pd.DataFrame({"trade_id": [1], "r_multiple": [0.5]}),
                    "equity_curve": pd.DataFrame({"trade_id": [1], "cum_r": [0.5]}),
                    "trade_summary": {"trade_count": 1},
                }
            )
        ),
        session_state,
    )
    assert session_state[BUNDLE_IMPORT_OMITTED_DATA_KEY] is True
    assert "data" not in session_state

    data_page = _import_data_page_module(session_state)
    assert data_page._preserve_dataset_less_bundle(session_state) is True
    assert not data_page._should_apply_source_dataset(
        file_present=True,
        source="Sample data",
        has_session_data=data_page._session_has_primary_data(session_state)
        or data_page._preserve_dataset_less_bundle(session_state),
    )
    assert data_page._should_apply_source_dataset(
        file_present=True,
        source="Upload CSV",
        has_session_data=data_page._session_has_primary_data(session_state)
        or data_page._preserve_dataset_less_bundle(session_state),
    )

    monkeypatch.setattr(data_page, "ensure_display_timezone", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "set_active_dataset_id", lambda *a, **k: None)
    monkeypatch.setattr(data_page, "clear_active_dataset_id", lambda *a, **k: None)
    loaded = pd.DataFrame({"timestamp": [1], "open": [1], "high": [1], "low": [1], "close": [1]})
    data_page._set_active_dataset_state(
        loaded,
        instrument="ES",
        base_interval="1min",
        source_timezone="America/New_York",
        exchange_timezone="America/New_York",
        resampled_data={},
        saved_dataset_id=None,
    )
    assert BUNDLE_IMPORT_OMITTED_DATA_KEY not in session_state
    assert data_page._preserve_dataset_less_bundle(session_state) is False


def test_tv4_honesty_docs_lock_suggested_pdpoc_and_readme_object():
    """TV4 Help copy: tick VAP is the live object; suggested pdPOC is column-gated."""
    root = pathlib.Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    user_guide = (root / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    assumptions = (root / "docs" / "ASSUMPTIONS_AND_LIMITATIONS.md").read_text(encoding="utf-8")
    study_runner = (root / "docs" / "STUDY_RUNNER.md").read_text(encoding="utf-8")
    assert "tick-bucketed ES/NQ volume bins" not in readme
    assert "tick Last×Volume VAP" in readme
    assert "absent** otherwise, not 1m typical" in readme
    assert "Suggested Setup defaults include `pdPOC` only when that column exists" in user_guide
    assert "Suggested `pdPOC` appears" in assumptions
    assert "only when the column exists" in assumptions
    assert "Suggested `pdPOC` appears only when the column" in study_runner
    assert "under cwd or the local store (same as Studies launch)" in user_guide


_H10_DUPLICATE_PRIMARY_CSV = (
    "timestamp,open,high,low,close,volume\n"
    "2026-06-02 09:30:00,100,101,99,100.5,10\n"
    "2026-06-02 09:30:00,100,101,99,100.5,11\n"
    "2026-06-02 09:31:00,100.5,102,100,101.5,20\n"
)
_H10_FATAL_GATE_NAMES = frozenset(
    {
        "FATAL_OHLCV_CODES",
        "_fatal_validation_messages",
        "fatal_codes",
        "fatal_messages",
        "parent_fatal",
    }
)


def _call_func_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _tree_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _literal_str_set(node: ast.AST) -> set[str] | None:
    if isinstance(node, ast.Call) and _call_func_name(node) == "frozenset" and node.args:
        node = node.args[0]
    if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return None
    values = [elt.value for elt in node.elts if isinstance(elt, ast.Constant)]
    if len(values) != len(node.elts) or not all(isinstance(v, str) for v in values):
        return None
    return set(values)


def _assign_target_names(node: ast.Assign) -> set[str]:
    return {t.id for t in node.targets if isinstance(t, ast.Name)}


def _is_15s_primary_mode_if(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    ids = {expr.id for expr in (test.left, test.comparators[0]) if isinstance(expr, ast.Name)}
    return "ingestion_mode" in ids and "INGESTION_MODE_15S_PRIMARY_DERIVE_1M" in ids


def _legacy_primary_else_body(source: str) -> list[ast.stmt]:
    """Else-body of the Upload-CSV 15s-vs-legacy fork that tags ``raw_df``."""
    tree = ast.parse(source)
    matches: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not _is_15s_primary_mode_if(node) or not node.orelse:
            continue
        wrapper = ast.Module(body=node.orelse, type_ignores=[])
        if any(
            isinstance(child, ast.Call) and _call_func_name(child) == "tag_session"
            for child in ast.walk(wrapper)
        ):
            matches.append(node.orelse)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one legacy-primary else with tag_session, found {len(matches)}"
        )
    return matches[0]


def _has_tag_session_raw_df(body: list[ast.stmt]) -> bool:
    wrapper = ast.Module(body=body, type_ignores=[])
    for child in ast.walk(wrapper):
        if not isinstance(child, ast.Call) or _call_func_name(child) != "tag_session":
            continue
        if child.args and isinstance(child.args[0], ast.Name) and child.args[0].id == "raw_df":
            return True
    return False


def _body_calls(body: list[ast.stmt], name: str) -> bool:
    wrapper = ast.Module(body=body, type_ignores=[])
    return any(
        isinstance(child, ast.Call) and _call_func_name(child) == name
        for child in ast.walk(wrapper)
    )


def assert_h10_legacy_primary_installs_without_fatal_abort(source: str) -> None:
    """Legacy primary validates then ``tag_session(raw_df)`` with no fatal raise."""
    body = _legacy_primary_else_body(source)
    if not _body_calls(body, "validate_ohlcv"):
        raise AssertionError("legacy primary else must call validate_ohlcv")
    if not _has_tag_session_raw_df(body):
        raise AssertionError("legacy primary else must tag_session(raw_df, ...)")
    if not _body_calls(body, "_set_active_dataset_state"):
        raise AssertionError("legacy primary else must _set_active_dataset_state")
    wrapper = ast.Module(body=body, type_ignores=[])
    for child in ast.walk(wrapper):
        if not isinstance(child, ast.If):
            continue
        if not (_tree_names(child.test) & _H10_FATAL_GATE_NAMES):
            continue
        if any(isinstance(inner, ast.Raise) for inner in ast.walk(child)):
            raise AssertionError(
                "legacy primary else must not raise on FATAL_OHLCV_CODES / "
                "_fatal_validation_messages (H10 UI-installs side)"
            )


def assert_h10_15s_parent_fail_closed(source: str) -> None:
    """15s-primary parent stays abort-on-fatal (do not invert with H10)."""
    fn = _module_function_def(source, "_prepare_15s_primary_dataset")
    assigned_from_helper = False
    raises_on_parent_fatal = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and "parent_fatal" in _assign_target_names(node):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and _call_func_name(value) == "_fatal_validation_messages"
                and value.args
                and isinstance(value.args[0], ast.Name)
                and value.args[0].id == "parent_report"
            ):
                assigned_from_helper = True
        if isinstance(node, ast.If) and "parent_fatal" in _tree_names(node.test):
            if any(isinstance(inner, ast.Raise) for inner in ast.walk(node)):
                raises_on_parent_fatal = True
    if not assigned_from_helper or not raises_on_parent_fatal:
        raise AssertionError(
            "_prepare_15s_primary_dataset must raise when "
            "_fatal_validation_messages(parent_report) is non-empty"
        )


def _page_fatal_ohlcv_codes(source: str) -> set[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if "FATAL_OHLCV_CODES" not in _assign_target_names(node):
            continue
        codes = _literal_str_set(node.value)
        if codes:
            return codes
    raise AssertionError("pages/1_Data.py must assign FATAL_OHLCV_CODES to a string set")


def _api_load_dataset_fatal_codes(source: str) -> set[str]:
    fn = _module_function_def(source, "load_dataset")
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        if "fatal_codes" not in _assign_target_names(node):
            continue
        codes = _literal_str_set(node.value)
        if codes:
            return codes
    raise AssertionError("api.load_dataset must assign fatal_codes = {...}")


def test_h10_legacy_primary_installs_fatal_ohlcv_api_rejects(tmp_path):
    """QI-01-03 / B-2: lock H10 — UI helper installs; api.load_dataset rejects."""
    from thesistester.api import load_dataset
    from thesistester.data.loader import load_ohlcv, validate_ohlcv
    from thesistester.data.sessions import tag_session

    path = tmp_path / "dup_primary.csv"
    path.write_text(_H10_DUPLICATE_PRIMARY_CSV, encoding="utf-8")
    raw = load_ohlcv(path, source_tz="America/New_York", target_tz="America/New_York")
    report = validate_ohlcv(raw)
    data_page = _import_data_page_module({})
    assert data_page.FATAL_OHLCV_CODES == _page_fatal_ohlcv_codes(_DATA_PAGE_SOURCE)
    fatals = [issue.code for issue in report.issues if issue.code in data_page.FATAL_OHLCV_CODES]
    assert "duplicate_timestamps" in fatals
    installed = tag_session(raw, "ES")
    assert len(installed) == 3
    with pytest.raises(ValueError, match=r"Dataset validation failed: 1 duplicate timestamps"):
        load_dataset(path, instrument="ES", source_timezone="America/New_York")

    api_source = pathlib.Path("thesistester/api.py").read_text(encoding="utf-8")
    assert _page_fatal_ohlcv_codes(_DATA_PAGE_SOURCE) == _api_load_dataset_fatal_codes(api_source)
    assert_h10_legacy_primary_installs_without_fatal_abort(_DATA_PAGE_SOURCE)
    assert_h10_15s_parent_fail_closed(_DATA_PAGE_SOURCE)


def test_h10_wiring_guard_rejects_inverted_legacy_fatal_abort():
    """Comment / unused needle / added fatal raise must not false-green H10."""
    inverted = (
        "if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:\n"
        "    prepared = _prepare_15s_primary_dataset(file)\n"
        "else:\n"
        "    raw_df, captured_raw = load_ohlcv(file, return_raw=True)\n"
        "    report = validate_ohlcv(raw_df)\n"
        "    fatal_messages = _fatal_validation_messages(report)\n"
        "    if fatal_messages:\n"
        "        raise ValueError('Dataset validation failed')\n"
        "    df = tag_session(raw_df, inst)\n"
        "    _set_active_dataset_state(df)\n"
    )
    try:
        assert_h10_legacy_primary_installs_without_fatal_abort(inverted)
    except AssertionError:
        pass
    else:
        raise AssertionError("legacy fatal abort before tag_session must invert H10")

    comment_only = (
        "if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:\n"
        "    prepared = _prepare_15s_primary_dataset(file)\n"
        "else:\n"
        "    raw_df, captured_raw = load_ohlcv(file, return_raw=True)\n"
        "    report = validate_ohlcv(raw_df)\n"
        "    # _fatal_validation_messages(report); tag_session(raw_df, inst)\n"
        "    df = tag_session(raw_df, inst)\n"
        "    _set_active_dataset_state(df)\n"
    )
    assert_h10_legacy_primary_installs_without_fatal_abort(comment_only)

    skipped_tag = (
        "if ingestion_mode == INGESTION_MODE_15S_PRIMARY_DERIVE_1M:\n"
        "    prepared = _prepare_15s_primary_dataset(file)\n"
        "else:\n"
        "    report = validate_ohlcv(raw_df)\n"
        "    df = tag_session(filtered_df, inst)\n"
        "    _set_active_dataset_state(df)\n"
    )
    try:
        assert_h10_legacy_primary_installs_without_fatal_abort(skipped_tag)
    except AssertionError:
        pass
    else:
        raise AssertionError("tag_session(filtered_df) must not bind H10 raw_df install")


def test_h10_wiring_guard_rejects_inverted_15s_parent_fail_closed():
    """15s parent fail-closed is AST-bound (comment / unused helper fail-closed)."""
    comment_only = (
        "def _prepare_15s_primary_dataset(uploaded_file):\n"
        "    parent_report = validate_ohlcv(derived.parent_data)\n"
        "    # parent_fatal = _fatal_validation_messages(parent_report)\n"
        "    parent_df = tag_session(derived.parent_data, instrument)\n"
    )
    try:
        assert_h10_15s_parent_fail_closed(comment_only)
    except AssertionError:
        pass
    else:
        raise AssertionError("comment-only _fatal_validation_messages must not bind 15s abort")

    unused_helper = (
        "def _prepare_15s_primary_dataset(uploaded_file):\n"
        "    parent_report = validate_ohlcv(derived.parent_data)\n"
        "    parent_fatal = _fatal_validation_messages(parent_report)\n"
        "    parent_df = tag_session(derived.parent_data, instrument)\n"
    )
    try:
        assert_h10_15s_parent_fail_closed(unused_helper)
    except AssertionError:
        pass
    else:
        raise AssertionError("unused parent_fatal must not bind 15s fail-closed")
