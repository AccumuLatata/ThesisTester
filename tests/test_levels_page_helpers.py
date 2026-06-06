from __future__ import annotations

import importlib.util
import pathlib
import sys
import types


def _make_streamlit_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")

    def _noop(*args, **kwargs):
        return None

    class _StopCalled(SystemExit):
        pass

    def _stop():
        raise _StopCalled()

    for name in ("title", "warning", "error", "success", "info", "caption", "divider", "subheader", "rerun"):
        setattr(st, name, _noop)
    st.stop = _stop  # type: ignore[assignment]
    st.session_state = {}  # type: ignore[assignment]
    return st


def _import_levels_helpers():
    stub = _make_streamlit_stub()
    sys.modules["streamlit"] = stub

    page_path = pathlib.Path(__file__).parent.parent / "pages" / "5_Levels.py"
    spec = importlib.util.spec_from_file_location("levels_page", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]

    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except SystemExit:
        pass

    return (
        stub,
        mod._normalize_levels_settings,
        mod._sync_levels_widget_state,
        mod._SMA_TIMEFRAMES_KEY,
        mod._EMA_TIMEFRAMES_KEY,
    )


(
    _st_stub,
    _normalize_levels_settings,
    _sync_levels_widget_state,
    _SMA_TIMEFRAMES_KEY,
    _EMA_TIMEFRAMES_KEY,
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
