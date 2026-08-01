from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    class _StopCalled(SystemExit):
        pass

    def _stop():
        raise _StopCalled()

    for name in (
        "title",
        "warning",
        "error",
        "success",
        "info",
        "caption",
        "divider",
        "subheader",
        "rerun",
    ):
        setattr(st, name, _noop)
    st.stop = _stop  # type: ignore[assignment]
    st.session_state = {}  # type: ignore[assignment]
    return st


def _import_levels_helpers():
    stub = _make_streamlit_stub()
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = stub

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "5_Levels.py"
    spec = importlib.util.spec_from_file_location("levels_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]

    try:
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except SystemExit:
            pass
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit

    return (
        stub,
        mod._normalize_levels_settings,
        mod._sync_levels_widget_state,
        mod._calculate_levels_transaction,
        mod._LEVELS_CALCULATION_STATUS_KEY,
        mod._SMA_TIMEFRAMES_KEY,
        mod._EMA_TIMEFRAMES_KEY,
        mod._PRIOR_DAY_AGG_TICKS_KEY,
        mod._PRIOR_WEEK_AGG_TICKS_KEY,
        mod._PRIOR_MONTH_AGG_TICKS_KEY,
    )


(
    _st_stub,
    _normalize_levels_settings,
    _sync_levels_widget_state,
    _calculate_levels_transaction,
    _LEVELS_CALCULATION_STATUS_KEY,
    _SMA_TIMEFRAMES_KEY,
    _EMA_TIMEFRAMES_KEY,
    _PRIOR_DAY_AGG_TICKS_KEY,
    _PRIOR_WEEK_AGG_TICKS_KEY,
    _PRIOR_MONTH_AGG_TICKS_KEY,
) = _import_levels_helpers()


def test_normalize_levels_settings_sorts_indicator_timeframes():
    normalized = _normalize_levels_settings(
        {
            "sma_timeframes": ["30min", "1min"],
            "ema_timeframes": ("5min", "1min"),
            "vwap_windows": ["1h", "15min"],
            "poc_windows": ["4h", "30min"],
        }
    )

    assert normalized["sma_timeframes"] == ["1min", "30min"]
    assert normalized["ema_timeframes"] == ["1min", "5min"]
    assert normalized["vwap_windows"] == ["15min", "1h"]
    assert normalized["poc_windows"] == ["30min", "4h"]
    assert normalized["prior_day_profile_aggregation_ticks"] == 1
    assert normalized["prior_week_profile_aggregation_ticks"] == 1
    assert normalized["prior_month_profile_aggregation_ticks"] == 1


def test_sync_levels_widget_state_restores_indicator_timeframe_selections():
    _st_stub.session_state.clear()
    _sync_levels_widget_state(
        {
            "sma_timeframes": ["30min", "5min", "1min", "unsupported"],
            "ema_timeframes": ["5min", "unsupported"],
        }
    )

    assert _st_stub.session_state[_SMA_TIMEFRAMES_KEY] == ["1min", "5min", "30min"]
    assert _st_stub.session_state[_EMA_TIMEFRAMES_KEY] == ["5min"]
    assert "unsupported" not in _st_stub.session_state[_SMA_TIMEFRAMES_KEY]
    assert "unsupported" not in _st_stub.session_state[_EMA_TIMEFRAMES_KEY]


def test_sync_levels_widget_state_restores_prior_profile_aggregation_ticks():
    _st_stub.session_state.clear()
    _sync_levels_widget_state(
        {
            "prior_day_profile_aggregation_ticks": 4,
            "prior_week_profile_aggregation_ticks": 10,
        }
    )

    assert _st_stub.session_state[_PRIOR_DAY_AGG_TICKS_KEY] == 4
    assert _st_stub.session_state[_PRIOR_WEEK_AGG_TICKS_KEY] == 10
    assert _st_stub.session_state[_PRIOR_MONTH_AGG_TICKS_KEY] == 1


def test_calculation_transaction_installs_complete_results_and_diagnostics():
    state: dict = {}
    calculated_levels = pd.DataFrame({"level": [1.0, 2.0]})
    calculated_session_levels = pd.DataFrame({"session_level": [1.0, 2.0]})

    succeeded = _calculate_levels_transaction(
        calculate=lambda: (calculated_levels, calculated_session_levels),
        session_state=state,
        current_settings={"opening_range_minutes": 30},
        current_data_fingerprint={"rows": 42},
        dataset_id="dataset-1",
        settings_hash="abc123",
        input_rows=42,
    )

    assert succeeded is True
    assert state["levels"] is calculated_levels
    assert state["session_levels"] is calculated_session_levels
    assert state["levels_settings"] == {"opening_range_minutes": 30}
    assert state["levels_data_fingerprint"] == {"rows": 42}
    status = state[_LEVELS_CALCULATION_STATUS_KEY]
    assert status["state"] == "succeeded"
    assert status["dataset_id"] == "dataset-1"
    assert status["settings_hash"] == "abc123"
    assert status["input_rows"] == 42


def test_calculation_transaction_preserves_prior_results_on_failure():
    prior_levels = object()
    prior_session_levels = object()
    state = {
        "levels": prior_levels,
        "session_levels": prior_session_levels,
        "levels_settings": {"opening_range_minutes": 15},
        "levels_data_fingerprint": {"rows": 10},
    }

    def _raise_memory_error():
        raise MemoryError("allocation failed")

    succeeded = _calculate_levels_transaction(
        calculate=_raise_memory_error,
        session_state=state,
        current_settings={"opening_range_minutes": 30},
        current_data_fingerprint={"rows": 42},
        dataset_id="dataset-1",
        settings_hash="abc123",
        input_rows=42,
    )

    assert succeeded is False
    assert state["levels"] is prior_levels
    assert state["session_levels"] is prior_session_levels
    assert state["levels_settings"] == {"opening_range_minutes": 15}
    assert state["levels_data_fingerprint"] == {"rows": 10}
    status = state[_LEVELS_CALCULATION_STATUS_KEY]
    assert status["state"] == "failed"
    assert status["error_type"] == "MemoryError"
    assert status["error_message"] == "allocation failed"
    assert "MemoryError: allocation failed" in status["traceback"]
