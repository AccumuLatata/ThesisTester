import pytest

from thesistester.assistant.comparison import Comparison


def test_comparison_records_exact_run_and_bundle_identity():
    comparison = Comparison.create(
        thesis_id="th_" + "a" * 32,
        left_run_id="run_" + "b" * 32,
        right_run_id="run_" + "c" * 32,
        left_bundle_hash="d" * 64,
        right_bundle_hash="e" * 64,
        evidence={"metrics": {}},
    )
    assert comparison.to_dict()["schema_version"] == 1

    with pytest.raises(ValueError, match="distinct"):
        Comparison.create(
            thesis_id="th",
            left_run_id="same",
            right_run_id="same",
            left_bundle_hash="a",
            right_bundle_hash="b",
            evidence={},
        )
