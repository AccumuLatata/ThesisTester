from __future__ import annotations

import pandas as pd
import pytest

from thesistester.setup import (
    BASE_COLUMNS,
    available_level_columns,
    build_setup_config,
    validate_setup_config,
)


def _base_config(**overrides) -> dict:
    config = build_setup_config(
        name="OR + ON setup",
        description="test",
        instrument="ES",
        selected_levels=["ONH", "ONL", "OR_High", "OR_Low"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        direction="both",
        trigger_params={},
    )
    config.update(overrides)
    return config


def _anchor_config(**overrides) -> dict:
    config = _base_config(
        selected_levels=[],
        confluence_mode="anchor_rules",
        anchor_level="pdHigh",
        confluence_rules=[
            {"level": "VWAP_rolling_1h", "tolerance_ticks": 4.0, "required": True},
            {"level": "pdPOC", "tolerance_ticks": 6.0, "required": False},
        ],
        min_valid_confluences=1,
    )
    config.update(overrides)
    return config


def test_available_level_columns_excludes_base_columns():
    df = pd.DataFrame(columns=[*BASE_COLUMNS, "ONH", "ONL", "pdHigh"])
    assert available_level_columns(df) == ["ONH", "ONL", "pdHigh"]


def test_validate_setup_config_valid_returns_no_errors():
    config = _base_config()
    assert validate_setup_config(config) == []


def test_old_global_config_without_confluence_mode_remains_valid():
    config = _base_config()
    config.pop("confluence_mode")
    config.pop("anchor_level")
    config.pop("confluence_rules")
    config.pop("min_valid_confluences")
    assert validate_setup_config(config) == []


def test_build_setup_config_defaults_to_global_cluster():
    config = _base_config()
    assert config["confluence_mode"] == "global_cluster"
    assert config["anchor_level"] is None
    assert config["confluence_rules"] == []
    assert config["min_valid_confluences"] == 1
    assert config["trigger_timeframe"] == "base"


def test_empty_setup_name_invalid():
    config = _base_config()
    config["name"] = "   "
    errors = validate_setup_config(config)
    assert any("Setup name" in message for message in errors)


def test_empty_selected_levels_invalid():
    config = _base_config()
    config["selected_levels"] = []
    errors = validate_setup_config(config)
    assert any("Select at least one level column" in message for message in errors)


def test_negative_tolerance_invalid():
    config = _base_config()
    config["tolerance_ticks"] = -1
    errors = validate_setup_config(config)
    assert any("Tolerance ticks must be >= 0" in message for message in errors)


def test_max_confluences_less_than_min_invalid():
    config = _base_config()
    config["min_confluences"] = 4
    config["max_confluences"] = 3
    errors = validate_setup_config(config)
    assert any("Maximum confluences must be >= minimum confluences" in message for message in errors)


def test_max_confluences_over_five_invalid():
    config = _base_config()
    config["max_confluences"] = 6
    errors = validate_setup_config(config)
    assert any("Maximum confluences must be <= 5" in message for message in errors)


def test_invalid_trigger_invalid():
    config = _base_config()
    config["trigger"] = "bad_trigger"
    errors = validate_setup_config(config)
    assert any("Trigger must be one of" in message for message in errors)


def test_invalid_direction_invalid():
    config = _base_config()
    config["direction"] = "up"
    errors = validate_setup_config(config)
    assert any("Direction must be one of" in message for message in errors)


def test_old_config_without_trigger_timeframe_remains_valid():
    config = _base_config()
    config.pop("trigger_timeframe")
    assert validate_setup_config(config) == []


def test_missing_trigger_timeframe_normalizes_to_base():
    config = build_setup_config(
        name="defaults",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        direction="both",
    )
    assert config["trigger_timeframe"] == "base"


def test_3c_config_includes_expected_trigger_params():
    # arrival_tolerance_ticks is deprecated; it is accepted in input for backward
    # compat but normalized to 0.0 in the stored config.
    config = build_setup_config(
        name="3bar",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        direction="both",
        trigger_params={
            "arrival_tolerance_ticks": 1.0,  # legacy — must be ignored and stored as 0.0
            "entry_retrace_ticks": 3.0,
            "max_entry_wait_bars_after_reversal": 7,
        },
    )

    assert config["trigger_params"] == {
        "arrival_tolerance_ticks": 0.0,  # always forced to 0 regardless of input
        "entry_retrace_ticks": 3.0,
        "max_entry_wait_bars_after_reversal": 7,
    }
    assert validate_setup_config(config) == []


def test_3c_missing_params_are_defaulted():
    config = build_setup_config(
        name="3c defaults",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        direction="both",
        trigger_params={
            "arrival_tolerance_ticks": 1.0  # deprecated; always stored as 0.0
        },
    )
    assert config["trigger_params"]["arrival_tolerance_ticks"] == 0.0  # forced to 0
    assert config["trigger_params"]["entry_retrace_ticks"] == 4.0
    assert config["trigger_params"]["max_entry_wait_bars_after_reversal"] == 5
    assert config["trigger_timeframe"] == "base"
    assert validate_setup_config(config) == []


def test_3c_non_base_trigger_timeframe_is_stored():
    """3c now supports non-base trigger timeframes; '5min' must be stored as-is."""
    config = build_setup_config(
        name="3c 5min tf",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        trigger_timeframe="5min",
        direction="both",
    )
    assert config["trigger_timeframe"] == "5min"
    assert validate_setup_config(config) == []


def test_3c_base_trigger_timeframe_remains_base():
    """3c with explicit 'base' trigger_timeframe stores 'base'."""
    config = build_setup_config(
        name="3c base tf",
        description="",
        instrument="ES",
        selected_levels=["ONH"],
        tolerance_ticks=4.0,
        min_confluences=2,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="3c",
        trigger_timeframe="base",
        direction="both",
    )
    assert config["trigger_timeframe"] == "base"
    assert validate_setup_config(config) == []


def test_valid_anchor_rules_config_returns_no_errors():
    assert validate_setup_config(_anchor_config()) == []


@pytest.mark.parametrize("anchor_level", [None, ""])
def test_anchor_rules_missing_anchor_level_invalid(anchor_level):
    errors = validate_setup_config(_anchor_config(anchor_level=anchor_level))
    assert any("Anchor level" in message for message in errors)


def test_anchor_rules_empty_confluence_rules_invalid():
    errors = validate_setup_config(_anchor_config(confluence_rules=[]))
    assert any("Confluence rules" in message for message in errors)


def test_anchor_rules_negative_rule_tolerance_invalid():
    errors = validate_setup_config(
        _anchor_config(
            confluence_rules=[
                {"level": "VWAP_rolling_1h", "tolerance_ticks": -1, "required": True},
            ]
        )
    )
    assert any("tolerance_ticks must be >= 0" in message for message in errors)


def test_anchor_rules_duplicate_rule_levels_invalid():
    errors = validate_setup_config(
        _anchor_config(
            confluence_rules=[
                {"level": "pdPOC", "tolerance_ticks": 4.0, "required": True},
                {"level": "pdPOC", "tolerance_ticks": 6.0, "required": False},
            ]
        )
    )
    assert any("Duplicate confluence rule level" in message for message in errors)


def test_anchor_rules_anchor_level_cannot_be_reused_in_confluence_rules():
    errors = validate_setup_config(
        _anchor_config(
            confluence_rules=[
                {"level": "pdHigh", "tolerance_ticks": 4.0, "required": True},
            ]
        )
    )
    assert any("must not equal anchor_level" in message for message in errors)


def test_anchor_rules_min_valid_confluences_cannot_exceed_rule_count():
    errors = validate_setup_config(_anchor_config(min_valid_confluences=3))
    assert any("Minimum valid confluences must be <= number of confluence rules" in message for message in errors)


def test_invalid_confluence_mode_invalid():
    errors = validate_setup_config(_base_config(confluence_mode="unknown"))
    assert any("Confluence mode must be one of" in message for message in errors)


def test_anchor_rules_required_must_be_boolean_compatible():
    errors = validate_setup_config(
        _anchor_config(
            confluence_rules=[
                {"level": "VWAP_rolling_1h", "tolerance_ticks": 4.0, "required": "maybe"},
            ]
        )
    )
    assert any("required must be boolean-compatible" in message for message in errors)


@pytest.mark.parametrize("required_value", [True, False, 1, 0, "true", "false", "1", "0"])
def test_anchor_rules_required_accepts_boolean_compatible_values(required_value):
    errors = validate_setup_config(
        _anchor_config(
            confluence_rules=[
                {"level": "VWAP_rolling_1h", "tolerance_ticks": 4.0, "required": required_value},
                {"level": "pdPOC", "tolerance_ticks": 6.0, "required": False},
            ]
        )
    )
    assert errors == []
