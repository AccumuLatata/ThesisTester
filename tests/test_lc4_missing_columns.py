"""LC4 probes: API global-cluster missing-column fail-closed.

P1–P3 lock ``api.generate_signals``. P4 locks the confluence library skip
contract. See ``docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md`` §7.4.
"""

from __future__ import annotations

import pandas as pd
import pytest

from thesistester.api import generate_signals
from thesistester.engine.confluence import detect_confluence_zones
from thesistester.setup import build_setup_config

_MISSING = "Pivot_1min_High"
_UNAVAILABLE = "unavailable level columns"
_ZONE_COLUMNS = [
    "timestamp",
    "bar_index",
    "zone_low",
    "zone_high",
    "zone_mid",
    "level_count",
    "level_names",
    "level_prices",
]


def _cluster(**overrides) -> dict:
    config = build_setup_config(
        name="LC4 probe",
        description="test",
        instrument="ES",
        selected_levels=["ONH"],
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


def _levels_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:30", periods=3, freq="1min"),
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.5, 100.5, 100.5],
            "volume": [1000, 1000, 1000],
            "ONH": [100.5, 100.5, 100.5],
        }
    )


def test_lc4_p1_global_cluster_missing_column_raises():
    """LC4-P1: missing global-cluster names fail closed; they are not silent drops."""
    config = _cluster(selected_levels=["ONH", _MISSING], min_confluences=2)
    with pytest.raises(ValueError, match=_UNAVAILABLE) as exc_info:
        generate_signals(_levels_frame(), config)
    message = str(exc_info.value)
    assert _MISSING in message
    assert "confluence_zones" not in message


def test_lc4_p2_onh_only_min2_returns_empty_confluence_zones():
    """LC4-P2: ONH-only global-cluster with min_confluences=2 stays empty zones."""
    result = generate_signals(_levels_frame(), _cluster(selected_levels=["ONH"]))
    assert "confluence_zones" in result
    assert "zones" not in result
    zones = result["confluence_zones"]
    assert zones.empty
    assert list(zones.columns) == _ZONE_COLUMNS


def test_lc4_p3_anchor_rules_missing_column_same_wording():
    """LC4-P3: anchor-rules missing columns keep the same ValueError family."""
    config = _cluster(
        selected_levels=[],
        confluence_mode="anchor_rules",
        anchor_level="ONH",
        confluence_rules=[
            {"level": _MISSING, "tolerance_ticks": 4.0, "required": True},
        ],
        min_valid_confluences=1,
    )
    with pytest.raises(ValueError, match=_UNAVAILABLE) as exc_info:
        generate_signals(_levels_frame(), config)
    assert _MISSING in str(exc_info.value)


def test_lc4_p4_library_missing_columns_still_empty_schema():
    """LC4-P4: detect_confluence_zones still skips missing names (empty schema)."""
    result = detect_confluence_zones(
        _levels_frame(),
        level_columns=["missingA", "missingB"],
        tick_size=0.25,
        tolerance_ticks=4,
    )
    assert result.empty
    assert list(result.columns) == _ZONE_COLUMNS
