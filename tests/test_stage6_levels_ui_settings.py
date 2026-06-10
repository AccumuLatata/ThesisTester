"""Stage 6 — UI and Persistence: tests for _normalize_levels_settings,
_sync_levels_widget_state, and compute_all_levels wiring."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd
import pytest

from thesistester.levels import compute_all_levels


# ---------------------------------------------------------------------------
# Import helpers from pages/5_Levels.py without running the Streamlit app
# ---------------------------------------------------------------------------


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    class _StopCalled(SystemExit):
        pass

    def _stop():
        raise _StopCalled()

    for name in ("title", "warning", "error", "success", "info", "caption", "divider",
                 "subheader", "rerun", "selectbox", "text_input", "multiselect",
                 "slider", "number_input", "checkbox", "button", "columns",
                 "spinner", "dataframe", "plotly_chart", "expander"):
        setattr(st, name, _noop)

    class _FakeExpander:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    st.expander = lambda *a, **kw: _FakeExpander()  # type: ignore[assignment]
    st.stop = _stop  # type: ignore[assignment]
    st.session_state = {}  # type: ignore[assignment]
    return st


def _import_levels_helpers():
    stub = _make_streamlit_stub()
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = stub

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "5_Levels.py"
    spec = importlib.util.spec_from_file_location("levels_page_stage6", page_path)
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

    return stub, mod


_st_stub, _mod = _import_levels_helpers()
_normalize = _mod._normalize_levels_settings
_sync = _mod._sync_levels_widget_state

_PIVOTS_ENABLED_KEY = _mod._PIVOTS_ENABLED_KEY
_PIVOT_TIMEFRAMES_KEY = _mod._PIVOT_TIMEFRAMES_KEY
_PIVOT_LEFT_KEY = _mod._PIVOT_LEFT_KEY
_PIVOT_RIGHT_KEY = _mod._PIVOT_RIGHT_KEY
_SESSION_VWAP_ENABLED_KEY = _mod._SESSION_VWAP_ENABLED_KEY
_SINGLE_PRINTS_ENABLED_KEY = _mod._SINGLE_PRINTS_ENABLED_KEY
_APOC_ENABLED_KEY = _mod._APOC_ENABLED_KEY
_PIVOT_TIMEFRAME_OPTIONS = _mod._PIVOT_TIMEFRAME_OPTIONS


# ---------------------------------------------------------------------------
# Helpers for compute_all_levels tests
# ---------------------------------------------------------------------------


def _make_tz_df(n: int = 10) -> pd.DataFrame:
    """Minimal tz-aware 1min OHLCV DataFrame for compute_all_levels testing."""
    start = pd.Timestamp("2024-01-02 09:30:00", tz="America/New_York")
    timestamps = pd.date_range(start, periods=n, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 4500.0,
            "high": 4501.0,
            "low": 4499.0,
            "close": 4500.0,
            "volume": 100.0,
        }
    )


# ===========================================================================
# Settings normalization tests
# ===========================================================================


class TestNormalizeStage6Defaults:
    """Old settings without Stage 6 keys normalize to all new defaults disabled."""

    def test_old_settings_get_pivots_disabled(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["pivots_enabled"] is False

    def test_old_settings_get_pivot_timeframes_all_supported(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["pivot_timeframes"] == ["1min", "30min", "4h", "5min"]

    def test_old_settings_get_pivot_left_2(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["pivot_left"] == 2

    def test_old_settings_get_pivot_right_2(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["pivot_right"] == 2

    def test_old_settings_get_session_vwap_disabled(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["session_vwap_enabled"] is False

    def test_old_settings_get_session_vwap_anchor_rth(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["session_vwap_anchor"] == "RTH"

    def test_old_settings_get_single_prints_disabled(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["single_prints_enabled"] is False

    def test_old_settings_get_apoc_disabled(self):
        result = _normalize({"opening_range_minutes": 30})
        assert result["apoc_enabled"] is False

    def test_none_input_returns_none(self):
        assert _normalize(None) is None

    def test_non_dict_returns_none(self):
        assert _normalize("bad") is None  # type: ignore[arg-type]

    def test_empty_dict_gets_all_defaults(self):
        result = _normalize({})
        assert result is not None
        assert result["pivots_enabled"] is False
        assert result["session_vwap_enabled"] is False
        assert result["single_prints_enabled"] is False
        assert result["apoc_enabled"] is False
        assert result["pivot_left"] == 2
        assert result["pivot_right"] == 2


class TestNormalizeSorting:
    """List settings are sorted deterministically."""

    def test_pivot_timeframes_sorted(self):
        result = _normalize({"pivot_timeframes": ["4h", "1min", "5min", "30min"]})
        assert result["pivot_timeframes"] == ["1min", "30min", "4h", "5min"]

    def test_pivot_timeframes_tuple_sorted(self):
        result = _normalize({"pivot_timeframes": ("4h", "30min")})
        assert result["pivot_timeframes"] == ["30min", "4h"]

    def test_sma_timeframes_sorted(self):
        result = _normalize({"sma_timeframes": ["30min", "1min"]})
        assert result["sma_timeframes"] == ["1min", "30min"]

    def test_ema_timeframes_sorted(self):
        result = _normalize({"ema_timeframes": ("5min", "1min")})
        assert result["ema_timeframes"] == ["1min", "5min"]

    def test_vwap_windows_sorted(self):
        result = _normalize({"vwap_windows": ["1h", "15min"]})
        assert result["vwap_windows"] == ["15min", "1h"]

    def test_poc_windows_sorted(self):
        result = _normalize({"poc_windows": ["4h", "30min"]})
        assert result["poc_windows"] == ["30min", "4h"]

    def test_same_settings_different_list_order_normalize_equal(self):
        a = _normalize({"pivot_timeframes": ["1min", "5min", "30min", "4h"]})
        b = _normalize({"pivot_timeframes": ["4h", "30min", "5min", "1min"]})
        assert a == b

    def test_old_settings_without_new_keys_do_not_crash(self):
        result = _normalize(
            {
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["5min"],
                "vwap_windows": ["30min"],
                "poc_windows": ["1h"],
            }
        )
        assert result is not None
        assert result["pivots_enabled"] is False

    def test_explicit_values_not_overwritten_by_defaults(self):
        result = _normalize(
            {
                "pivots_enabled": True,
                "pivot_left": 3,
                "pivot_right": 5,
                "session_vwap_enabled": True,
                "single_prints_enabled": True,
                "apoc_enabled": True,
            }
        )
        assert result["pivots_enabled"] is True
        assert result["pivot_left"] == 3
        assert result["pivot_right"] == 5
        assert result["session_vwap_enabled"] is True
        assert result["single_prints_enabled"] is True
        assert result["apoc_enabled"] is True


# ===========================================================================
# Widget sync tests
# ===========================================================================


class TestSyncStage6WidgetState:
    """_sync_levels_widget_state restores new Stage 6 controls."""

    def setup_method(self):
        _st_stub.session_state.clear()

    def test_syncs_pivots_enabled_true(self):
        _sync({"pivots_enabled": True})
        assert _st_stub.session_state[_PIVOTS_ENABLED_KEY] is True

    def test_syncs_pivots_enabled_false(self):
        _sync({"pivots_enabled": False})
        assert _st_stub.session_state[_PIVOTS_ENABLED_KEY] is False

    def test_syncs_pivot_timeframes_filters_to_supported(self):
        _sync({"pivot_timeframes": ["1min", "5min", "unsupported"]})
        assert _st_stub.session_state[_PIVOT_TIMEFRAMES_KEY] == ["1min", "5min"]

    def test_syncs_pivot_timeframes_missing_key_defaults_all(self):
        _sync({})
        assert _st_stub.session_state[_PIVOT_TIMEFRAMES_KEY] == list(_PIVOT_TIMEFRAME_OPTIONS)

    def test_syncs_pivot_left(self):
        _sync({"pivot_left": 3})
        assert _st_stub.session_state[_PIVOT_LEFT_KEY] == 3

    def test_syncs_pivot_right(self):
        _sync({"pivot_right": 5})
        assert _st_stub.session_state[_PIVOT_RIGHT_KEY] == 5

    def test_syncs_session_vwap_enabled_true(self):
        _sync({"session_vwap_enabled": True})
        assert _st_stub.session_state[_SESSION_VWAP_ENABLED_KEY] is True

    def test_syncs_session_vwap_enabled_false(self):
        _sync({"session_vwap_enabled": False})
        assert _st_stub.session_state[_SESSION_VWAP_ENABLED_KEY] is False

    def test_syncs_single_prints_enabled_true(self):
        _sync({"single_prints_enabled": True})
        assert _st_stub.session_state[_SINGLE_PRINTS_ENABLED_KEY] is True

    def test_syncs_single_prints_enabled_false(self):
        _sync({"single_prints_enabled": False})
        assert _st_stub.session_state[_SINGLE_PRINTS_ENABLED_KEY] is False

    def test_syncs_apoc_enabled_true(self):
        _sync({"apoc_enabled": True})
        assert _st_stub.session_state[_APOC_ENABLED_KEY] is True

    def test_syncs_apoc_enabled_false(self):
        _sync({"apoc_enabled": False})
        assert _st_stub.session_state[_APOC_ENABLED_KEY] is False

    def test_old_snapshot_missing_keys_defaults_to_disabled(self):
        """Old saved snapshot without Stage 6 keys must load without error."""
        _sync({"opening_range_minutes": 30, "value_area_pct": 0.70})
        assert _st_stub.session_state[_PIVOTS_ENABLED_KEY] is False
        assert _st_stub.session_state[_SESSION_VWAP_ENABLED_KEY] is False
        assert _st_stub.session_state[_SINGLE_PRINTS_ENABLED_KEY] is False
        assert _st_stub.session_state[_APOC_ENABLED_KEY] is False

    def test_pivot_left_not_synced_if_zero(self):
        """pivot_left must be >= 1 to be accepted."""
        _st_stub.session_state[_PIVOT_LEFT_KEY] = 2
        _sync({"pivot_left": 0})
        assert _st_stub.session_state[_PIVOT_LEFT_KEY] == 2


# ===========================================================================
# compute_all_levels wiring tests
# ===========================================================================


class TestComputeAllLevelsWiring:
    """All new UI gates disabled → no new columns; enabling each gate → only that family."""

    def test_all_gates_disabled_no_pivot_columns(self):
        df = _make_tz_df()
        result = compute_all_levels(df)
        assert not any(col.startswith("Pivot_") for col in result.columns)

    def test_all_gates_disabled_no_dvwap_column(self):
        df = _make_tz_df()
        result = compute_all_levels(df)
        assert "dVWAP_RTH" not in result.columns

    def test_all_gates_disabled_no_single_print_columns(self):
        df = _make_tz_df()
        result = compute_all_levels(df)
        assert not any("SinglePrint" in col for col in result.columns)

    def test_all_gates_disabled_no_apoc_columns(self):
        df = _make_tz_df()
        result = compute_all_levels(df)
        assert "APOC" not in result.columns
        assert "pAPOC" not in result.columns

    def test_enabling_pivots_adds_pivot_columns(self):
        df = _make_tz_df(200)
        result = compute_all_levels(df, pivots_enabled=True, pivot_timeframes=["1min"])
        assert any(col.startswith("Pivot_") for col in result.columns)
        assert "dVWAP_RTH" not in result.columns
        assert not any("SinglePrint" in col for col in result.columns)
        assert "APOC" not in result.columns

    def test_enabling_dvwap_adds_dvwap_column(self):
        df = _make_tz_df(200)
        result = compute_all_levels(
            df, session_vwap_enabled=True, session_vwap_anchor="RTH"
        )
        assert "dVWAP_RTH" in result.columns
        assert not any(col.startswith("Pivot_") for col in result.columns)
        assert not any("SinglePrint" in col for col in result.columns)
        assert "APOC" not in result.columns

    def test_enabling_single_prints_adds_sp_columns(self):
        df = _make_tz_df(200)
        result = compute_all_levels(df, single_prints_enabled=True)
        assert "dSinglePrint_30m_NearestAbove" in result.columns
        assert "dSinglePrint_30m_NearestBelow" in result.columns
        assert "pSinglePrint_30m_NearestAbove" in result.columns
        assert "pSinglePrint_30m_NearestBelow" in result.columns
        assert "APOC" not in result.columns
        assert not any(col.startswith("Pivot_") for col in result.columns)

    def test_enabling_apoc_adds_apoc_columns(self):
        df = _make_tz_df(200)
        result = compute_all_levels(df, apoc_enabled=True)
        assert "APOC" in result.columns
        assert "pAPOC" in result.columns
        assert not any("SinglePrint" in col for col in result.columns)
        assert not any(col.startswith("Pivot_") for col in result.columns)

    def test_apoc_not_routed_through_tpo(self):
        """APOC and Single Prints must be independent; enabling both works."""
        df = _make_tz_df(200)
        result = compute_all_levels(
            df, single_prints_enabled=True, apoc_enabled=True
        )
        assert "APOC" in result.columns
        assert "pAPOC" in result.columns
        assert "dSinglePrint_30m_NearestAbove" in result.columns

    def test_all_four_families_enabled_together(self):
        df = _make_tz_df(200)
        result = compute_all_levels(
            df,
            pivots_enabled=True,
            pivot_timeframes=["1min"],
            session_vwap_enabled=True,
            single_prints_enabled=True,
            apoc_enabled=True,
        )
        assert any(col.startswith("Pivot_") for col in result.columns)
        assert "dVWAP_RTH" in result.columns
        assert "dSinglePrint_30m_NearestAbove" in result.columns
        assert "APOC" in result.columns

    def test_existing_baseline_columns_unchanged_when_gates_disabled(self):
        df = _make_tz_df(200)
        result_default = compute_all_levels(df)
        result_explicit_off = compute_all_levels(
            df,
            pivots_enabled=False,
            session_vwap_enabled=False,
            single_prints_enabled=False,
            apoc_enabled=False,
        )
        assert set(result_default.columns) == set(result_explicit_off.columns)
