from __future__ import annotations

import pandas as pd

from thesistester.data.rolls import (
    compute_roll_gaps,
    detect_contract_column,
    validate_roll_metadata,
)


def _segmented_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 09:30:00",
                    "2026-01-01 09:31:00",
                    "2026-01-01 09:32:00",
                    "2026-01-01 09:33:00",
                ],
                utc=True,
            ),
            "open": [100.0, 101.0, 110.0, 111.0],
            "high": [101.0, 102.0, 111.0, 112.0],
            "low": [99.0, 100.0, 109.0, 110.0],
            "close": [100.5, 101.5, 110.5, 111.5],
            "contract": ["ESH2026", "ESH2026", "ESM2026", "ESM2026"],
        }
    )


def test_detect_contract_column_prefers_contract_over_symbol():
    df = pd.DataFrame({"symbol": ["ES"], "contract": ["ESH2026"]})
    assert detect_contract_column(df) == "contract"


def test_detect_contract_column_returns_none_when_missing():
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    assert detect_contract_column(df) is None


def test_single_contract_valid_with_one_contract():
    df = _segmented_df().iloc[:2].copy()
    result = validate_roll_metadata(df, roll_method="single_contract", contract_column="contract")
    assert result["valid"] is True
    assert result["contract_count"] == 1


def test_single_contract_invalid_with_multiple_contracts():
    result = validate_roll_metadata(_segmented_df(), roll_method="single_contract", contract_column="contract")
    assert result["valid"] is False
    assert result["contract_count"] == 2


def test_single_contract_valid_without_contract_column_warns():
    df = _segmented_df().drop(columns=["contract"])
    result = validate_roll_metadata(df, roll_method="single_contract")
    assert result["valid"] is True
    assert any("No contract column found" in warning for warning in result["warnings"])


def test_external_continuous_warns_on_unknown_adjustments_and_roll_rule():
    result = validate_roll_metadata(
        _segmented_df().iloc[:2],
        roll_method="external_continuous",
        contract_column="contract",
        adjustment_method="unknown",
        roll_rule="unknown",
    )
    assert result["valid"] is True
    assert any("adjustment_method is unknown" in warning for warning in result["warnings"])
    assert any("roll_rule is unknown" in warning for warning in result["warnings"])


def test_external_continuous_warns_with_multiple_explicit_contracts():
    result = validate_roll_metadata(
        _segmented_df(),
        roll_method="external_continuous",
        contract_column="contract",
    )
    assert result["valid"] is True
    assert any("Multiple explicit contracts" in warning for warning in result["warnings"])


def test_segmented_contracts_invalid_without_contract_column():
    df = _segmented_df().drop(columns=["contract"])
    result = validate_roll_metadata(df, roll_method="segmented_contracts", contract_column="contract")
    assert result["valid"] is False


def test_segmented_contracts_invalid_with_fewer_than_two_contracts():
    df = _segmented_df().iloc[:2].copy()
    result = validate_roll_metadata(df, roll_method="segmented_contracts", contract_column="contract")
    assert result["valid"] is False


def test_segmented_contracts_valid_with_two_contracts_and_gaps():
    result = validate_roll_metadata(_segmented_df(), roll_method="segmented_contracts", contract_column="contract")
    assert result["valid"] is True
    assert result["contract_count"] == 2
    assert result["roll_gap_count"] == 1
    assert len(result["roll_gaps"]) == 1


def test_roll_gap_ticks_computed_when_tick_size_provided():
    gaps = compute_roll_gaps(_segmented_df(), contract_column="contract", tick_size=0.25)
    assert len(gaps) == 1
    assert gaps[0]["price_gap"] == 8.5
    assert gaps[0]["price_gap_ticks"] == 34.0


def test_validate_roll_metadata_does_not_mutate_input_dataframe():
    df = _segmented_df().sample(frac=1, random_state=42).reset_index(drop=True)
    before = df.copy(deep=True)
    validate_roll_metadata(df, roll_method="segmented_contracts", contract_column="contract")
    pd.testing.assert_frame_equal(df, before)
