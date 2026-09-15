"""QI-02-03 / E-1: UI / API / Study share one tick-family refuse class."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pandas as pd
import pytest

from thesistester.api import compute_levels
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.tick_requirements import (
    APOC_REQUIRES_TICKS,
    ROLLING_POC_REQUIRES_TICKS,
    product_tick_family_message,
    product_tick_family_preflight,
)
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)


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


def _load_page_refuse_helper():
    stub = _make_streamlit_stub()
    previous = sys.modules.get("streamlit")
    sys.modules["streamlit"] = stub
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "2_Levels.py"
    spec = importlib.util.spec_from_file_location("levels_page_e1", page_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except SystemExit:
            pass
    finally:
        if previous is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous
    return mod._product_tick_family_refuse_message


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.DatetimeIndex(
                ["2024-01-02 14:30:00", "2024-01-02 14:31:00"],
                tz="America/New_York",
            ),
            "open": [100.0, 100.25],
            "high": [100.5, 100.5],
            "low": [99.75, 100.0],
            "close": [100.25, 100.25],
            "volume": [10, 10],
        }
    )


def _minimal_study(*, core_level: str, poc_windows: list[str] | None = None) -> dict:
    levels = {
        "sma_lengths": [50, 200],
        "ema_lengths": [21],
        "sma_timeframes": ["1min", "5min", "30min"],
        "ema_timeframes": ["1min", "5min", "30min"],
    }
    if poc_windows is not None:
        levels["poc_windows"] = poc_windows
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": "tick_family_parity",
            "dataset": {"path": "data/es_1m.csv", "instrument": "ES"},
            "levels": levels,
            "constants": {
                "direction": "both",
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "min_valid_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": {},
                "backtest": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "exposure_policy": "single_position",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": [core_level],
                "partner_levels": [["SMA_50_1min"]],
                "confluence_mode": ["global_cluster"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                }
            },
            "report": {
                "primary_metric": "expectancy_r",
                "secondary_metrics": ["profit_factor", "trade_count"],
                "min_trades": 30,
                "group_by": ["partner_levels"],
                "otf_baseline": {"enabled": False},
                "multiple_testing": "warn",
            },
            "stage": {
                "mode": "filter",
                "include": {"trigger": ["touch"], "trigger_timeframe": ["base"]},
            },
        },
    }


def test_product_tick_family_preflight_one_message_class_no_typical():
    both = product_tick_family_preflight(DEFAULT_LEVELS_SETTINGS)
    expected = product_tick_family_message(apoc=True, rolling=True)
    assert both == expected
    assert APOC_REQUIRES_TICKS in both
    assert ROLLING_POC_REQUIRES_TICKS in both
    assert "typical" not in both.lower()

    apoc_only = product_tick_family_preflight(
        {**DEFAULT_LEVELS_SETTINGS, "poc_windows": [], "apoc_enabled": True}
    )
    assert apoc_only == product_tick_family_message(apoc=True, rolling=False)
    assert ROLLING_POC_REQUIRES_TICKS not in apoc_only

    rolling_only = product_tick_family_preflight(
        {**DEFAULT_LEVELS_SETTINGS, "poc_windows": ["30min"], "apoc_enabled": False}
    )
    assert rolling_only == product_tick_family_message(apoc=False, rolling=True)
    assert APOC_REQUIRES_TICKS not in rolling_only

    off = product_tick_family_preflight(
        {**DEFAULT_LEVELS_SETTINGS, "poc_windows": [], "apoc_enabled": False}
    )
    assert off == ""
    with_ticks = product_tick_family_preflight(
        DEFAULT_LEVELS_SETTINGS, tick_paths=["data/es_ticks.csv"]
    )
    assert with_ticks == ""


def test_ui_api_study_share_tick_family_substring():
    """Composer-parity: UI helper / compute_levels / validate_study_spec."""
    ui_refuse = _load_page_refuse_helper()
    ui_msg = ui_refuse(DEFAULT_LEVELS_SETTINGS)
    assert ui_msg == product_tick_family_preflight(DEFAULT_LEVELS_SETTINGS)
    assert APOC_REQUIRES_TICKS in ui_msg
    assert ROLLING_POC_REQUIRES_TICKS in ui_msg
    assert "typical" not in ui_msg.lower()

    with pytest.raises(ValueError) as api_exc:
        compute_levels(_bars(), instrument="ES", config={})
    assert str(api_exc.value) == ui_msg

    with pytest.raises(StudySpecError) as apoc_exc:
        validate_study_spec(normalize_study_spec(_minimal_study(core_level="APOC")))
    assert APOC_REQUIRES_TICKS in str(apoc_exc.value)

    with pytest.raises(StudySpecError) as rolling_exc:
        validate_study_spec(
            normalize_study_spec(
                _minimal_study(core_level="POC_rolling_30min", poc_windows=["30min"])
            )
        )
    assert ROLLING_POC_REQUIRES_TICKS in str(rolling_exc.value)
