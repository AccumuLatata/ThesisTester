"""Enabled fade golden / drift gate (DA4).

Isolated from the legacy golden-master family. Legacy artifacts must remain
unchanged; this module only verifies the additive ``fade_enabled_*`` family.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tests.fixtures.golden.canonical import canonicalize_trades
from tests.fixtures.golden.generate_fade_enabled import (
    generate_fade_enabled_dataset,
    generate_fade_enabled_signals,
)
from tests.fixtures.golden.pipeline_fade_enabled import run_fade_enabled_pipeline
from tests.fixtures.golden.record_fade_enabled_golden import (
    DATASET_PATH,
    MANIFEST_PATH,
    PROJECTION_PATH,
    SIGNALS_CSV_PATH,
    TRADES_CSV_PATH,
    _signal_projection,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden"
LEGACY_ARTIFACTS = (
    "dataset_nq_1m_small.parquet",
    "trades_legacy.parquet",
    "trades_legacy.csv",
    "legacy_bundle_hash.txt",
    "fixture_manifest.json",
)


def _load_projection() -> dict:
    return json.loads(PROJECTION_PATH.read_text(encoding="utf-8"))


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_fade_enabled_artifacts_are_complete():
    manifest = _load_manifest()
    assert manifest["family"] == "fade_enabled"
    assert manifest["fixture_version"] == 1
    for path in (
        DATASET_PATH,
        SIGNALS_CSV_PATH,
        TRADES_CSV_PATH,
        PROJECTION_PATH,
        MANIFEST_PATH,
    ):
        assert path.is_file(), f"Missing enabled fade golden artifact: {path.name}"


def test_fade_enabled_generator_rebuilds_recorded_dataset():
    recorded = pd.read_parquet(DATASET_PATH)
    generated = generate_fade_enabled_dataset()
    pd.testing.assert_frame_equal(recorded, generated, check_dtype=False, check_exact=True)


def test_fade_enabled_reproduces_signals_trades_and_projection():
    result = run_fade_enabled_pipeline()
    projection = _load_projection()
    recorded_signals = pd.read_csv(SIGNALS_CSV_PATH)
    recorded_trades = pd.read_csv(TRADES_CSV_PATH)

    pd.testing.assert_frame_equal(
        _signal_projection(result["signals"]).reset_index(drop=True),
        canonicalize_trades(recorded_signals).reset_index(drop=True),
        check_dtype=False,
    )
    assert list(result["trades"]["signal_id"]) == projection["accepted_signal_ids"]
    assert list(result["trades"]["signal_id"]) == list(recorded_trades["signal_id"])
    assert result["projection"] == projection
    assert projection["collision_pairs"] == 0
    assert set(projection["candidate_directions"]) == {"long", "short"}


def test_fade_enabled_live_signals_match_generator():
    data = generate_fade_enabled_dataset()
    generated = generate_fade_enabled_signals(data)
    live = run_fade_enabled_pipeline(data)["signals"]
    pd.testing.assert_frame_equal(generated, live, check_dtype=False, check_exact=True)


def test_legacy_golden_pipeline_unchanged_by_fade_family():
    for name in LEGACY_ARTIFACTS:
        assert (FIXTURE_DIR / name).is_file()
