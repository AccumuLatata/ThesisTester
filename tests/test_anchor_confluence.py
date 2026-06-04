from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from thesistester.engine import detect_anchor_confluence_zones as exported_detect_anchor_confluence_zones
from thesistester.engine.anchor_confluence import ANCHOR_ZONE_COLUMNS, detect_anchor_confluence_zones


TZ = "America/New_York"
TICK = 0.25


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_anchor_confluence_engine_is_exported():
    assert callable(exported_detect_anchor_confluence_zones)


def test_empty_rules_returns_empty_schema():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 4500.0,
                "VWAP_rolling_1h": 4500.0,
            }
        ]
    )
    result = detect_anchor_confluence_zones(df, "pdHigh", [], tick_size=TICK)
    assert result.empty
    assert list(result.columns) == ANCHOR_ZONE_COLUMNS


def test_missing_anchor_column_returns_empty_schema():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "VWAP_rolling_1h": 4500.0,
            }
        ]
    )
    rules = [{"level": "VWAP_rolling_1h", "tolerance_ticks": 1, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert result.empty
    assert list(result.columns) == ANCHOR_ZONE_COLUMNS


def test_exact_match_is_valid():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 4500.0,
                "VWAP_rolling_1h": 4500.0,
            }
        ]
    )
    rules = [{"level": "VWAP_rolling_1h", "tolerance_ticks": 0, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["valid_confluence_count"] == 1
    assert row["zone_low"] == 4500.0
    assert row["zone_high"] == 4500.0
    assert row["zone_mid"] == 4500.0
    assert row["level_names"] == "pdHigh|VWAP_rolling_1h"


def test_within_tolerance_is_valid():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 4500.00,
                "VWAP_rolling_1h": 4500.75,
            }
        ]
    )
    rules = [{"level": "VWAP_rolling_1h", "tolerance_ticks": 3, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=0.25)
    assert len(result) == 1


def test_outside_tolerance_is_invalid():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 4500.00,
                "VWAP_rolling_1h": 4501.00,
            }
        ]
    )
    rules = [{"level": "VWAP_rolling_1h", "tolerance_ticks": 3, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=0.25)
    assert result.empty


def test_required_invalid_blocks_setup():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 4500.0,
                "required_bad": 4502.0,
            }
        ]
    )
    rules = [{"level": "required_bad", "tolerance_ticks": 3, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert result.empty


def test_optional_invalid_does_not_block_if_min_valid_met():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "opt_valid": 101.0,
                "opt_invalid": 110.0,
            }
        ]
    )
    rules = [
        {"level": "opt_valid", "tolerance_ticks": 4, "required": False},
        {"level": "opt_invalid", "tolerance_ticks": 4, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK, min_valid_confluences=1)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["level_names"] == "pdHigh|opt_valid"
    assert row["level_prices"] == "100.0|101.0"
    assert row["zone_low"] == 100.0
    assert row["zone_high"] == 101.0


def test_minimum_valid_count_not_met_returns_no_zone():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 101.0,
                "rule_b": 110.0,
            }
        ]
    )
    rules = [
        {"level": "rule_a", "tolerance_ticks": 4, "required": False},
        {"level": "rule_b", "tolerance_ticks": 4, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK, min_valid_confluences=2)
    assert result.empty


def test_missing_anchor_price_skips_bar():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": np.nan,
                "rule_a": 100.0,
            }
        ]
    )
    rules = [{"level": "rule_a", "tolerance_ticks": 4, "required": False}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert result.empty


def test_missing_optional_confluence_price_allows_zone_if_min_met():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_ok": 100.5,
                "rule_nan": np.nan,
            }
        ]
    )
    rules = [
        {"level": "rule_ok", "tolerance_ticks": 2, "required": False},
        {"level": "rule_nan", "tolerance_ticks": 2, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK, min_valid_confluences=1)
    assert len(result) == 1
    parsed = json.loads(result.iloc[0]["rule_results"])
    nan_rule = next(r for r in parsed if r["level"] == "rule_nan")
    assert nan_rule["reason"] == "missing_price"
    assert nan_rule["valid"] is False


def test_missing_required_confluence_price_blocks_setup():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_req": np.nan,
            }
        ]
    )
    rules = [{"level": "rule_req", "tolerance_ticks": 2, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert result.empty


def test_missing_confluence_column_required_blocks_setup():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_ok": 100.0,
            }
        ]
    )
    rules = [
        {"level": "rule_ok", "tolerance_ticks": 1, "required": False},
        {"level": "rule_missing", "tolerance_ticks": 1, "required": True},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert result.empty


def test_optional_missing_column_keeps_zone_and_records_reason():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_ok": 100.0,
            }
        ]
    )
    rules = [
        {"level": "rule_ok", "tolerance_ticks": 1, "required": False},
        {"level": "rule_missing", "tolerance_ticks": 1, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK, min_valid_confluences=1)
    assert len(result) == 1
    parsed = json.loads(result.iloc[0]["rule_results"])
    missing_rule = next(r for r in parsed if r["level"] == "rule_missing")
    assert missing_rule["reason"] == "missing_column"


def test_zone_boundaries_use_anchor_plus_valid_only():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "valid_rule": 101.0,
                "invalid_optional": 110.0,
            }
        ]
    )
    rules = [
        {"level": "valid_rule", "tolerance_ticks": 4, "required": False},
        {"level": "invalid_optional", "tolerance_ticks": 4, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["zone_low"] == 100.0
    assert row["zone_high"] == 101.0
    assert row["zone_mid"] == 100.5


def test_tick_size_must_be_positive():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 100.0,
            }
        ]
    )
    rules = [{"level": "rule_a", "tolerance_ticks": 1, "required": True}]
    with pytest.raises(ValueError, match="tick_size must be > 0"):
        detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=0)


def test_multiple_bars_processed_independently():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 100.5,
            },
            {
                "timestamp": pd.Timestamp("2026-06-02 09:31:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 105.0,
            },
            {
                "timestamp": pd.Timestamp("2026-06-02 09:32:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 99.5,
            },
        ]
    )
    rules = [{"level": "rule_a", "tolerance_ticks": 2, "required": True}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert list(result["bar_index"]) == [0, 2]


def test_rule_results_is_valid_json_with_expected_fields():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "pdHigh": 100.0,
                "rule_a": 100.5,
            }
        ]
    )
    rules = [{"level": "rule_a", "tolerance_ticks": 2, "required": "true"}]
    result = detect_anchor_confluence_zones(df, "pdHigh", rules, tick_size=TICK)
    assert len(result) == 1
    parsed = json.loads(result.iloc[0]["rule_results"])
    assert isinstance(parsed, list)
    assert parsed
    keys = set(parsed[0].keys())
    assert {"level", "distance_ticks", "tolerance_ticks", "required", "valid", "reason"}.issubset(keys)


def test_anchor_is_first_and_rule_order_is_preserved_for_valid_entries():
    df = _df(
        [
            {
                "timestamp": pd.Timestamp("2026-06-02 09:30:00", tz=TZ),
                "anchor": 100.0,
                "rule_b": 100.5,
                "rule_a": 100.25,
            }
        ]
    )
    rules = [
        {"level": "rule_b", "tolerance_ticks": 2, "required": False},
        {"level": "rule_a", "tolerance_ticks": 2, "required": False},
    ]
    result = detect_anchor_confluence_zones(df, "anchor", rules, tick_size=TICK)
    assert len(result) == 1
    assert result.iloc[0]["level_names"] == "anchor|rule_b|rule_a"
