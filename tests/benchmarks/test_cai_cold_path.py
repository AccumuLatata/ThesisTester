"""Smoke tests for CAI-0 cold-path characterization harness."""

from __future__ import annotations

import pytest

from tests.fixtures.assistant_parity import write_parity_bars, parity_run_spec
from tests.fixtures.cai_baseline import cai_levels_config, cai_run_spec
from thesistester.api import _named_level_tokens_from_setup, run_experiment
from thesistester.levels.tick_requirements import disable_unneeded_tick_families
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

from .cai_cold_path import measure_cai_cold_path

pytestmark = pytest.mark.benchmark

_EXPECTED_STAGES = [
    "load_dataset",
    "compute_levels",
    "generate_signals",
    "run_backtest",
    "build_research_bundle",
    "run_experiment_end_to_end",
]


def test_cai_small_cold_path_harness_is_complete_and_nonnegative():
    report = measure_cai_cold_path(kind="small", repeats=1)
    assert report["fixture"] == "small"
    assert report["bar_count"] == 60
    assert list(report["levels_config"]["poc_windows"]) == []
    assert [stage["stage"] for stage in report["stages"]] == _EXPECTED_STAGES
    assert all(stage["median_ms"] >= 0 for stage in report["stages"])
    assert all(stage["p95_ms"] >= stage["median_ms"] for stage in report["stages"])
    assert report["signal_count"] >= 0
    assert report["trade_count"] >= 0


def test_cai_realistic_levels_config_is_tick_gated():
    assert cai_levels_config(kind="realistic")["poc_windows"] == []


def test_cai_realistic_tick_gate_clears_unused_poc_windows():
    """QI-14-01: unused poc_windows are cleared from named setup tokens."""
    spec = cai_run_spec(dataset_path="unused.csv", kind="realistic")
    named_tokens = _named_level_tokens_from_setup(spec["setup"])
    assert "POC_rolling_30min" not in named_tokens
    stale = dict(spec["levels"])
    stale["poc_windows"] = ["30min"]
    assert disable_unneeded_tick_families(stale, named_tokens)["poc_windows"] == []


def test_cai_realistic_cold_path_harness_is_complete_and_nonnegative():
    """QI-14-01 / B-18: --fixture realistic emits six tick-gated stage rows."""
    report = measure_cai_cold_path(kind="realistic", repeats=1)
    assert report["fixture"] == "realistic"
    assert report["bar_count"] == 780
    assert list(report["levels_config"]["poc_windows"]) == []
    assert [stage["stage"] for stage in report["stages"]] == _EXPECTED_STAGES
    assert all(stage["median_ms"] >= 0 for stage in report["stages"])
    assert all(stage["p95_ms"] >= stage["median_ms"] for stage in report["stages"])
    assert all(list(stage["poc_windows"]) == [] for stage in report["stages"])
    assert report["signal_count"] >= 0
    assert report["trade_count"] >= 0


def test_existing_assistant_parity_fixture_remains_green(tmp_path):
    """CAI-0 must not disturb the established API/CLI/assistant parity fixture."""
    write_parity_bars(tmp_path / "bars.csv")
    spec = parity_run_spec(dataset_path="bars.csv")
    first = run_experiment(spec, base_directory=tmp_path)
    second = run_experiment(spec, base_directory=tmp_path)
    assert canonical_bundle_hash(build_research_bundle(first)) == canonical_bundle_hash(
        build_research_bundle(second)
    )
