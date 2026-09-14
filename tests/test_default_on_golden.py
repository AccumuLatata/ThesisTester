"""B-3 / QI-11-02: additive default-on branch goldens.

Gates flatten-on, 3c filled/void ``sl_first``, BE/trail, and
``same_bar_opposite_direction="legacy"``. Legacy artifacts are never rewritten.
AH1 / AH5 unit probes stay the live probes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from tests.fixtures.golden.canonical import canonicalize_trades
from tests.fixtures.golden.generate_default_on import (
    generate_be_dataset,
    generate_flatten_on_dataset,
    generate_opposite_direction_legacy_dataset,
    generate_three_c_sl_first_dataset,
    generate_trail_dataset,
)
from tests.fixtures.golden.pipeline_default_on import (
    run_be_pipeline,
    run_flatten_on_pipeline,
    run_opposite_direction_legacy_pipeline,
    run_three_c_sl_first_pipeline,
    run_trail_pipeline,
)
from tests.fixtures.golden.record_default_on_golden import _skip_projection
from tests.test_journal_triggers import REPO, _regression_base_ref

pytestmark = pytest.mark.golden

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden"
LEGACY_ARTIFACTS = (
    "dataset_nq_1m_small.parquet",
    "trades_legacy.parquet",
    "trades_legacy.csv",
    "legacy_bundle_hash.txt",
    "fixture_manifest.json",
)
DEFAULT_ON_FAMILIES = (
    "flatten_on",
    "three_c_sl_first",
    "be_trail_be",
    "be_trail_trail",
    "opposite_direction_legacy",
)
# 4 existing families + 4 B-3 branches = 8/8 default-on paths.
GATED_DEFAULT_ON_PATHS = (
    "sl_first_same_bar_both_hit",
    "allow_all",
    "flatten_on",
    "three_c_filled_void_sl_first",
    "be_trail",
    "opposite_direction_legacy",
    "entry_window_enabled",
    "otf_enabled",
)


def _load_json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _assert_trades_match(produced: pd.DataFrame, csv_name: str) -> None:
    expected = (FIXTURE_DIR / csv_name).read_text(encoding="utf-8")
    assert canonicalize_trades(produced).to_csv(index=False, float_format="%.17g") == expected


def test_default_on_eight_paths_are_gated() -> None:
    """Exit gate: 8/8 default-on paths have a golden family."""
    tests_dir = Path(__file__).parent
    assert len(GATED_DEFAULT_ON_PATHS) == 8
    assert (tests_dir / "test_golden_master.py").is_file()
    assert (tests_dir / "test_entry_window_golden.py").is_file()
    assert (tests_dir / "test_otf_golden.py").is_file()
    assert (FIXTURE_DIR / "trades_legacy.csv").is_file()
    assert (FIXTURE_DIR / "entry_window_enabled_trades.csv").is_file()
    assert (FIXTURE_DIR / "otf_enabled_trades.csv").is_file()
    for family in DEFAULT_ON_FAMILIES:
        assert (FIXTURE_DIR / f"{family}_trades.csv").is_file()
        assert (FIXTURE_DIR / f"{family}_projection.json").is_file()
        assert (FIXTURE_DIR / f"{family}_manifest.json").is_file()


def test_default_on_families_do_not_rewrite_legacy_artifacts() -> None:
    base = _regression_base_ref()
    legacy_paths = [f"tests/fixtures/golden/{name}" for name in LEGACY_ARTIFACTS]
    for name in LEGACY_ARTIFACTS:
        assert (FIXTURE_DIR / name).is_file(), f"Legacy golden artifact missing: {name}"
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", base, "--", *legacy_paths],
        cwd=REPO,
        text=True,
    )
    assert diff.strip() == "", f"Legacy golden artifacts rewritten vs {base}:\n{diff}"
    for family in DEFAULT_ON_FAMILIES:
        assert family != "trades_legacy"
        assert not family.startswith("dataset_nq")


def test_ah1_and_ah5_remain_probes() -> None:
    """B-3 must not convert AH1 / AH5 unit probes into goldens."""
    tests_dir = Path(__file__).parent
    ah1 = (tests_dir / "test_ah1_session_flatten.py").read_text(encoding="utf-8")
    ah5 = (tests_dir / "test_ah5_sl_first_3c_entry.py").read_text(encoding="utf-8")
    assert "def test_ah1_p1_mon_eth_does_not_inherit_tuesday_flatten_clock" in ah1
    assert "def test_ah5_p1_three_c_entry_parent_does_not_sl_on_pre_retrace_low" in ah5


def test_flatten_on_reproduces_session_close_and_empty_cap() -> None:
    recorded = pd.read_parquet(FIXTURE_DIR / "flatten_on_dataset.parquet")
    pd.testing.assert_frame_equal(
        recorded, generate_flatten_on_dataset(), check_dtype=False, check_exact=True
    )
    result = run_flatten_on_pipeline()
    projection = _load_json("flatten_on_projection.json")
    assert result["projection"] == projection
    assert projection["exit_reasons"] == ["SESSION_CLOSE"]
    assert projection["skip_reasons"] == ["empty_session_close_cap"]
    assert projection["skip_signal_ids"] == [1]
    assert projection["accepted_signal_ids"] == [2]
    assert int(result["trades"].iloc[0]["exit_bar_index"]) == 5
    _assert_trades_match(result["trades"], "flatten_on_trades.csv")
    produced_skips = _skip_projection(result["skipped_signals"]).to_csv(
        index=False, float_format="%.17g"
    )
    assert produced_skips == (FIXTURE_DIR / "flatten_on_skipped.csv").read_text(encoding="utf-8")
    assert _load_json("flatten_on_manifest.json")["family"] == "flatten_on"


def test_three_c_sl_first_filled_eod_void_does_not_fill() -> None:
    recorded = pd.read_parquet(FIXTURE_DIR / "three_c_sl_first_dataset.parquet")
    pd.testing.assert_frame_equal(
        recorded,
        generate_three_c_sl_first_dataset(),
        check_dtype=False,
        check_exact=True,
    )
    result = run_three_c_sl_first_pipeline()
    projection = _load_json("three_c_sl_first_projection.json")
    assert result["projection"] == projection
    assert projection["exit_reasons"] == ["EOD"]
    assert projection["void_signal_ids"] == [2]
    assert projection["accepted_signal_ids"] == [1]
    assert projection["skip_signal_ids"] == []
    assert projection["skip_reasons"] == []
    assert projection["theoretical_exit_prices"] == [101.0]
    assert "SL" not in projection["exit_reasons"]
    skipped = result["skipped_signals"]
    assert skipped is None or skipped.empty, "3c void must not emit a skip row"
    _assert_trades_match(result["trades"], "three_c_sl_first_trades.csv")


def test_be_trail_reproduces_be_and_trail_exits() -> None:
    pd.testing.assert_frame_equal(
        pd.read_parquet(FIXTURE_DIR / "be_trail_be_dataset.parquet"),
        generate_be_dataset(),
        check_dtype=False,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(FIXTURE_DIR / "be_trail_trail_dataset.parquet"),
        generate_trail_dataset(),
        check_dtype=False,
        check_exact=True,
    )
    be = run_be_pipeline()
    trail = run_trail_pipeline()
    assert be["projection"] == _load_json("be_trail_be_projection.json")
    assert trail["projection"] == _load_json("be_trail_trail_projection.json")
    assert be["projection"]["exit_reasons"] == ["BE"]
    assert trail["projection"]["exit_reasons"] == ["TRAIL"]
    _assert_trades_match(be["trades"], "be_trail_be_trades.csv")
    _assert_trades_match(trail["trades"], "be_trail_trail_trades.csv")


def test_opposite_direction_legacy_matches_omitted_default() -> None:
    recorded = pd.read_parquet(FIXTURE_DIR / "opposite_direction_legacy_dataset.parquet")
    pd.testing.assert_frame_equal(
        recorded,
        generate_opposite_direction_legacy_dataset(),
        check_dtype=False,
        check_exact=True,
    )
    explicit = run_opposite_direction_legacy_pipeline()
    omitted = run_opposite_direction_legacy_pipeline(same_bar_opposite_direction=None)
    projection = _load_json("opposite_direction_legacy_projection.json")
    assert explicit["projection"] == projection
    assert explicit["projection"]["policy"] == "legacy"
    assert omitted["projection"]["policy"] == "legacy"
    assert explicit["projection"]["candidate_pairs"] == 3
    assert explicit["diagnostic"] == omitted["diagnostic"]
    pd.testing.assert_frame_equal(
        canonicalize_trades(explicit["trades"]),
        canonicalize_trades(omitted["trades"]),
        check_dtype=False,
        check_exact=True,
    )
    for payload in (explicit, omitted):
        skipped = payload["skipped_signals"]
        assert skipped is None or skipped.empty
    _assert_trades_match(explicit["trades"], "opposite_direction_legacy_trades.csv")
    _assert_trades_match(omitted["trades"], "opposite_direction_legacy_trades.csv")
    produced_skips = _skip_projection(explicit["skipped_signals"]).to_csv(
        index=False, float_format="%.17g"
    )
    assert produced_skips == (FIXTURE_DIR / "opposite_direction_legacy_skipped.csv").read_text(
        encoding="utf-8"
    )
