import pytest

from thesistester.assistant.comparison import COMPARISON_SCHEMA_VERSION, Comparison


def test_comparison_records_exact_run_and_bundle_identity():
    comparison = Comparison.create(
        thesis_id="th_" + "a" * 32,
        left_run_id="run_" + "b" * 32,
        right_run_id="run_" + "c" * 32,
        left_bundle_hash="d" * 64,
        right_bundle_hash="e" * 64,
        evidence={
            "schema_version": 1,
            "metrics": {},
            "conclusions": ["Runs share dataset fingerprint and instrument."],
            "next_experiments": ["Re-run with costs."],
        },
    )
    payload = comparison.to_dict()
    assert payload["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert payload["created_at"]
    assert payload["conclusions"] == ["Runs share dataset fingerprint and instrument."]
    restored = Comparison.from_dict(payload)
    assert restored.to_dict() == payload

    with pytest.raises(ValueError, match="distinct"):
        Comparison.create(
            thesis_id="th",
            left_run_id="same",
            right_run_id="same",
            left_bundle_hash="a",
            right_bundle_hash="b",
            evidence={},
        )


def test_comparison_from_dict_migrates_v1_records():
    legacy = {
        "schema_version": 1,
        "kind": "assistant_comparison",
        "comparison_id": "cmp_" + "a" * 32,
        "thesis_id": "th_" + "b" * 32,
        "left_run_id": "run_" + "c" * 32,
        "right_run_id": "run_" + "d" * 32,
        "left_bundle_hash": "e" * 64,
        "right_bundle_hash": "f" * 64,
        "evidence": {
            "metrics": {"expectancy_r": {"left": 0.1, "right": 0.2}},
            "conclusions": ["legacy conclusion"],
        },
    }
    restored = Comparison.from_dict(legacy)
    assert restored.conclusions == ("legacy conclusion",)
    assert restored.created_at == "1970-01-01T00:00:00Z"
    assert restored.to_dict()["schema_version"] == COMPARISON_SCHEMA_VERSION
