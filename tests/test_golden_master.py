from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from tests.fixtures.golden.canonical import canonicalize_trades, dtype_families
from tests.fixtures.golden.generate import generate_dataset
from tests.fixtures.golden.pipeline import run_legacy_pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden"


def _manifest() -> dict:
    return json.loads((FIXTURE_DIR / "fixture_manifest.json").read_text(encoding="utf-8"))


def _bundle_hash_record() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (FIXTURE_DIR / "legacy_bundle_hash.txt").read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", maxsplit=1)
        values[key] = value
    return values


def test_golden_manifest_and_artifacts_are_complete():
    manifest = _manifest()
    assert manifest["fixture_version"] == 1
    assert manifest["generator"]["instrument"] == "NQ"
    assert manifest["artifacts"]["trade_count"] > 0
    for filename in (
        "dataset_nq_1m_small.parquet",
        "trades_legacy.parquet",
        "trades_legacy.csv",
        "legacy_bundle_hash.txt",
    ):
        assert (FIXTURE_DIR / filename).is_file()


def test_generator_exactly_rebuilds_recorded_dataset():
    recorded = pd.read_parquet(FIXTURE_DIR / "dataset_nq_1m_small.parquet")
    generated = generate_dataset()
    pd.testing.assert_frame_equal(recorded, generated, check_dtype=False, check_exact=True)


def test_legacy_pipeline_exactly_matches_recorded_trades():
    data = pd.read_parquet(FIXTURE_DIR / "dataset_nq_1m_small.parquet")
    recorded = pd.read_parquet(FIXTURE_DIR / "trades_legacy.parquet")
    produced = run_legacy_pipeline(data)["trades"]
    manifest = _manifest()

    assert list(recorded.columns) == manifest["artifacts"]["trade_columns"]
    assert list(produced.columns) == manifest["artifacts"]["trade_columns"]
    pd.testing.assert_frame_equal(
        canonicalize_trades(recorded),
        canonicalize_trades(produced),
        check_dtype=False,
        check_exact=True,
    )
    assert dtype_families(recorded) == manifest["artifacts"]["trade_dtype_families"]
    assert dtype_families(produced) == manifest["artifacts"]["trade_dtype_families"]


def test_readable_csv_is_current_projection_of_recorded_trades():
    recorded = pd.read_parquet(FIXTURE_DIR / "trades_legacy.parquet")
    expected = canonicalize_trades(recorded).to_csv(index=False, float_format="%.17g")
    assert (FIXTURE_DIR / "trades_legacy.csv").read_text(encoding="utf-8") == expected


def test_fixture_exercises_legacy_both_hit_sl_first_rule():
    data = pd.read_parquet(FIXTURE_DIR / "dataset_nq_1m_small.parquet")
    trades = run_legacy_pipeline(data)["trades"]
    both_hit = trades[
        (
            (trades["direction"] == "long")
            & (trades["mae_points"] >= 2)
            & (trades["mfe_points"] >= 4)
        )
        | (
            (trades["direction"] == "short")
            & (trades["mae_points"] >= 2)
            & (trades["mfe_points"] >= 4)
        )
    ]
    assert len(both_hit) == 6
    assert set(both_hit["exit_reason"]) == {"SL"}


def test_canonical_bundle_hash_matches_recorded_pandas_major():
    record = _bundle_hash_record()
    current_major = int(pd.__version__.split(".", maxsplit=1)[0])
    recorded_major = int(record["pandas_major"])
    if current_major != recorded_major:
        pytest.skip(
            f"bundle hash is pandas-major-scoped: recorded={recorded_major}, current={current_major}"
        )
    data = pd.read_parquet(FIXTURE_DIR / "dataset_nq_1m_small.parquet")
    assert run_legacy_pipeline(data)["bundle_hash"] == record["sha256"]


def test_bundle_projection_ignores_manifest_and_zip_timestamps():
    state: dict = {}
    first = build_research_bundle(state)
    second = build_research_bundle(state)
    assert first != second
    assert canonical_bundle_hash(first) == canonical_bundle_hash(second)
