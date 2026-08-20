from __future__ import annotations

import pandas as pd
import pytest

from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.setup import (
    BASE_COLUMNS,
    DEFAULT_OTF_FILTER_CONFIG,
    SUGGESTED_DEFAULT_LEVELS,
    available_level_columns,
    build_setup_config,
    default_selected_levels,
    get_effective_entry_window_config,
    get_effective_otf_filter_config,
    normalize_otf_filter_config,
    validate_otf_filter_config,
    validate_setup_config,
)
from thesistester.study.schema import closed_level_token_set


def _base_config(**overrides) -> dict:
    otf_filter = overrides.pop("otf_filter", None)
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
        otf_filter=otf_filter,
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


def test_lc3_suggested_defaults_implied_by_default_closed_set():
    assert set(SUGGESTED_DEFAULT_LEVELS) <= closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
    assert "VWAP_rolling_30min" in SUGGESTED_DEFAULT_LEVELS
    assert "VWAP_rolling_1h" not in SUGGESTED_DEFAULT_LEVELS
    assert "pdVAH" not in SUGGESTED_DEFAULT_LEVELS


def test_lc3_default_selected_levels_use_product_vwap_window():
    columns = [
        "ONH",
        "ONL",
        "AsiaHigh",
        "AsiaLow",
        "LondonHigh",
        "LondonLow",
        "OR_High",
        "OR_Low",
        "RTH_Open",
        "pRTH_High",
        "pRTH_Low",
        "pdHigh",
        "pdLow",
        "pdPOC",
        "VWAP_rolling_30min",
        "VWAP_rolling_4h",
        "VWAP_rolling_1h",
    ]
    selected = default_selected_levels(columns)
    assert "VWAP_rolling_30min" in selected
    assert "VWAP_rolling_1h" not in selected


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
    assert any(
        "Maximum confluences must be >= minimum confluences" in message for message in errors
    )


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


def test_anchor_rules_empty_rules_min_valid_zero_valid():
    assert validate_setup_config(_anchor_config(confluence_rules=[], min_valid_confluences=0)) == []


def test_anchor_rules_empty_rules_omitted_min_valid_invalid():
    config = _anchor_config(confluence_rules=[])
    config.pop("min_valid_confluences")
    errors = validate_setup_config(config)
    assert any("Confluence rules" in message for message in errors)


def test_anchor_rules_empty_rules_bool_false_min_valid_invalid():
    errors = validate_setup_config(_anchor_config(confluence_rules=[], min_valid_confluences=False))
    assert any("Minimum valid confluences must be an integer" in message for message in errors)


def test_anchor_rules_min_valid_negative_invalid():
    errors = validate_setup_config(_anchor_config(min_valid_confluences=-1))
    assert any("Minimum valid confluences must be >= 0" in message for message in errors)


def test_anchor_rules_non_empty_min_valid_zero_valid():
    assert validate_setup_config(_anchor_config(min_valid_confluences=0)) == []


def test_global_cluster_min_confluences_zero_still_invalid():
    errors = validate_setup_config(_base_config(min_confluences=0))
    assert any("Minimum confluences must be >= 1" in message for message in errors)


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
    assert any(
        "Minimum valid confluences must be <= number of confluence rules" in message
        for message in errors
    )


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


def test_otf_missing_block_resolves_to_disabled_defaults():
    config = _base_config()
    config.pop("otf_filter", None)
    assert get_effective_otf_filter_config(config) == DEFAULT_OTF_FILTER_CONFIG


def test_entry_window_missing_block_resolves_to_disabled_defaults():
    config = _base_config()
    config.pop("entry_window", None)
    effective = get_effective_entry_window_config(config)
    assert effective["enabled"] is False
    assert effective["timezone"] == "America/New_York"


def test_build_setup_config_includes_disabled_entry_window():
    config = _base_config()
    assert config["entry_window"]["enabled"] is False


def test_otf_none_resolves_to_disabled_defaults():
    assert normalize_otf_filter_config(None) == DEFAULT_OTF_FILTER_CONFIG


def test_otf_explicit_disabled_normalizes_to_canonical_defaults():
    normalized = normalize_otf_filter_config(
        {
            "enabled": False,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 9,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert normalized == DEFAULT_OTF_FILTER_CONFIG


def test_otf_enabled_single_timeframe_normalizes():
    normalized = normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert normalized["enabled"] is True
    assert normalized["timeframes"] == ["5m"]


def test_otf_enabled_multi_timeframe_preserves_order():
    normalized = normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["30m", "5m", "15m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 4,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert normalized["timeframes"] == ["30m", "5m", "15m"]


def test_otf_aliases_normalize_to_canonical_labels():
    normalized = normalize_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["5min", "15min", "30min"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert normalized["timeframes"] == ["5m", "15m", "30m"]


def test_otf_duplicate_alias_and_canonical_values_reject():
    errors = validate_otf_filter_config(
        {
            "enabled": True,
            "timeframes": ["5m", "5min"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 3,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert any("Duplicate timeframe" in message for message in errors)


def test_otf_enabled_without_timeframe_rejects():
    errors = validate_otf_filter_config({"enabled": True, "timeframes": []})
    assert any("Select at least one OTF timeframe" in message for message in errors)


def test_otf_invalid_enabled_type_rejects():
    errors = validate_otf_filter_config({"enabled": "yes"})
    assert any("enabled must be a boolean" in message for message in errors)


def test_otf_invalid_alignment_mode_rejects():
    errors = validate_otf_filter_config(
        {"enabled": True, "timeframes": ["5m"], "alignment_mode": "any"}
    )
    assert any("alignment_mode must be 'all'" in message for message in errors)


def test_otf_invalid_threshold_and_bool_reject():
    errors_bool = validate_otf_filter_config({"minimum_consecutive_bars": True})
    errors_zero = validate_otf_filter_config({"minimum_consecutive_bars": 0})
    assert any("minimum_consecutive_bars must be an integer" in message for message in errors_bool)
    assert any("minimum_consecutive_bars must be >= 1" in message for message in errors_zero)


def test_otf_directional_false_rejects():
    errors = validate_otf_filter_config({"directional": False})
    assert any("directional must be True" in message for message in errors)


def test_otf_use_completed_bars_only_false_rejects():
    errors = validate_otf_filter_config({"use_completed_bars_only": False})
    assert any("use_completed_bars_only must be True" in message for message in errors)


def test_otf_invalid_session_reset_rejects():
    errors = validate_otf_filter_config({"session_reset": "carry"})
    assert any("session_reset must be 'session'" in message for message in errors)


def test_otf_input_dictionary_is_not_mutated():
    payload = {
        "enabled": True,
        "timeframes": ["15min", "5m"],
        "alignment_mode": "all",
        "minimum_consecutive_bars": 3,
        "directional": True,
        "use_completed_bars_only": True,
        "session_reset": "session",
    }
    snapshot = dict(payload)
    snapshot["timeframes"] = list(payload["timeframes"])
    normalize_otf_filter_config(payload)
    assert payload == snapshot


def test_build_setup_config_includes_disabled_otf_defaults():
    config = _base_config()
    assert config["otf_filter"] == DEFAULT_OTF_FILTER_CONFIG


def test_build_setup_config_embeds_enabled_otf_canonically():
    config = _base_config(
        otf_filter={
            "enabled": True,
            "timeframes": ["30min", "5m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 5,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert config["otf_filter"]["timeframes"] == ["30m", "5m"]


def test_validate_setup_config_accepts_absent_legacy_otf_block():
    config = _base_config()
    config.pop("otf_filter", None)
    assert validate_setup_config(config) == []


def test_validate_setup_config_reports_invalid_otf_config():
    config = _base_config()
    config["otf_filter"] = {"enabled": True, "timeframes": []}
    errors = validate_setup_config(config)
    assert any("OTF filter" in message for message in errors)


def test_effective_otf_helper_preserves_enabled_values():
    config = _base_config(
        otf_filter={
            "enabled": True,
            "timeframes": ["15m"],
            "alignment_mode": "all",
            "minimum_consecutive_bars": 6,
            "directional": True,
            "use_completed_bars_only": True,
            "session_reset": "session",
        }
    )
    assert get_effective_otf_filter_config(config)["minimum_consecutive_bars"] == 6
