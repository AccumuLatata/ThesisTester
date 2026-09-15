"""QI-02-03 / E-1: UI / API / Study share one tick-family refuse class."""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from tests.study.test_study_schema import _minimal_study
from tests.test_levels_page_helpers import _product_tick_family_refuse_message
from tests.test_ui_copy_guards import _USER_GUIDE_H2_SOFT_BUDGET, _md_h2_body
from thesistester.api import compute_levels
from thesistester.levels.apoc_candidates import TYPICAL_MVP_V1
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.tick_requirements import (
    APOC_REQUIRES_TICKS,
    ROLLING_POC_REQUIRES_TICKS,
    product_tick_family_message,
    product_tick_family_preflight,
)
from thesistester.study.schema import StudySpecError, normalize_study_spec, validate_study_spec

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


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


def test_product_tick_family_preflight_typical_source_is_not_an_escape():
    """AP/RP: typical is not a product escape from refuse-without-ticks."""
    msg = product_tick_family_preflight(
        {
            **DEFAULT_LEVELS_SETTINGS,
            "poc_windows": [],
            "apoc_enabled": True,
            "apoc_profile_source": TYPICAL_MVP_V1,
        }
    )
    assert msg == product_tick_family_message(apoc=True, rolling=False)
    assert APOC_REQUIRES_TICKS in msg
    assert "typical" not in msg.lower()


def test_ui_api_study_share_tick_family_substring():
    """Composer-parity: UI helper / compute_levels / validate_study_spec."""
    ui_msg = _product_tick_family_refuse_message(DEFAULT_LEVELS_SETTINGS)
    assert ui_msg == product_tick_family_preflight(DEFAULT_LEVELS_SETTINGS)
    assert APOC_REQUIRES_TICKS in ui_msg
    assert ROLLING_POC_REQUIRES_TICKS in ui_msg
    assert "typical" not in ui_msg.lower()

    with pytest.raises(ValueError) as api_exc:
        compute_levels(_bars(), instrument="ES", config={})
    assert str(api_exc.value) == ui_msg

    apoc_raw = _minimal_study()
    apoc_raw["study"]["factors"]["core_level"] = ["APOC"]
    with pytest.raises(StudySpecError) as apoc_exc:
        validate_study_spec(normalize_study_spec(apoc_raw))
    assert APOC_REQUIRES_TICKS in str(apoc_exc.value)

    rolling_raw = _minimal_study()
    rolling_raw["study"]["levels"]["poc_windows"] = ["30min"]
    rolling_raw["study"]["factors"]["core_level"] = ["POC_rolling_30min"]
    with pytest.raises(StudySpecError) as rolling_exc:
        validate_study_spec(normalize_study_spec(rolling_raw))
    assert ROLLING_POC_REQUIRES_TICKS in str(rolling_exc.value)


def test_user_guide_levels_h2_names_first_visit_tick_family_refuse():
    """USER_GUIDE Levels H2 locks first-visit refuse copy under the soft budget."""
    body = _md_h2_body((REPO_ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8"), "Levels")
    assert APOC_REQUIRES_TICKS in body
    assert ROLLING_POC_REQUIRES_TICKS in body
    assert "api.compute_levels" in body
    assert "typical" in body.lower()
    assert len(body) <= _USER_GUIDE_H2_SOFT_BUDGET, (
        f"Levels H2 exceeds USER_GUIDE soft budget: {len(body)}"
    )
