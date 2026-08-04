"""Smoke tests for CAI-10 warm-path characterization harness."""

from __future__ import annotations

from .cai_warm_path import measure_cai_warm_path


def test_cai_small_warm_path_harness_is_complete_and_hash_safe():
    report = measure_cai_warm_path(kind="small", repeats=1)
    assert report["fixture"] == "small"
    assert report["canonical_bundle_hash_equal"] is True
    assert report["cold_end_to_end"]["median_ms"] >= 0
    assert report["warm_end_to_end"]["median_ms"] >= 0
    assert isinstance(report["signal_cache_recommendation"], str)
    assert report["signal_cache_recommendation"]
    assert "Informational only" in report["notes"][0]
