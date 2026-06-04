from __future__ import annotations

import pandas as pd

from thesistester.setup import (
    BASE_COLUMNS,
    available_level_columns,
    build_setup_config,
    validate_setup_config,
)


def _base_config() -> dict:
    return build_setup_config(
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


def test_available_level_columns_excludes_base_columns():
    df = pd.DataFrame(columns=[*BASE_COLUMNS, "ONH", "ONL", "pdHigh"])
    assert available_level_columns(df) == ["ONH", "ONL", "pdHigh"]


def test_validate_setup_config_valid_returns_no_errors():
    config = _base_config()
    assert validate_setup_config(config) == []


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


def test_confirm_3bar_config_includes_expected_trigger_params():
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
        trigger="confirm_3bar",
        direction="both",
        trigger_params={
            "arrival_tolerance_ticks": 1.0,
            "retrace_entry_ticks": 3.0,
            "allow_equal_close": True,
        },
    )

    assert config["trigger_params"] == {
        "arrival_tolerance_ticks": 1.0,
        "retrace_entry_ticks": 3.0,
        "allow_equal_close": True,
    }
    assert validate_setup_config(config) == []
