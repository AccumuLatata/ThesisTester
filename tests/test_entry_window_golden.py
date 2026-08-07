"""Enabled entry_window golden / drift gate (SW2).

Isolated from the legacy golden-master family. Legacy artifacts must remain
unchanged; this module only verifies the additive ``entry_window_enabled_*``
family.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tests.fixtures.golden.canonical import canonicalize_trades
from tests.fixtures.golden.generate_entry_window_enabled import (
    generate_entry_window_enabled_dataset,
    generate_entry_window_enabled_signals,
)
from tests.fixtures.golden.pipeline_entry_window_enabled import (
    run_entry_window_enabled_pipeline,
)
from tests.fixtures.golden.record_entry_window_enabled_golden import (
    DATASET_PATH,
    MANIFEST_PATH,
    PROJECTION_PATH,
    SKIPPED_CSV_PATH,
    TRADES_CSV_PATH,
    _skip_projection,
)
from thesistester.analytics.entry_window import filter_trades_by_entry_window

from tests.fixtures.golden.generate_entry_window_enabled import ENTRY_WINDOW

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


def test_entry_window_enabled_artifacts_are_complete():
    manifest = _load_manifest()
    assert manifest["family"] == "entry_window_enabled"
    assert manifest["fixture_version"] == 1
    for path in (
        DATASET_PATH,
        TRADES_CSV_PATH,
        SKIPPED_CSV_PATH,
        PROJECTION_PATH,
        MANIFEST_PATH,
    ):
        assert path.is_file(), f"Missing enabled entry_window golden artifact: {path.name}"


def test_entry_window_enabled_generator_rebuilds_recorded_dataset():
    recorded = pd.read_parquet(DATASET_PATH)
    generated = generate_entry_window_enabled_dataset()
    pd.testing.assert_frame_equal(recorded, generated, check_dtype=False, check_exact=True)


def test_entry_window_enabled_reproduces_trades_and_skips():
    result = run_entry_window_enabled_pipeline()
    projection = _load_projection()

    assert list(result["trades"]["signal_id"]) == projection["accepted_signal_ids"]
    window_skips = result["skipped_signals"][
        result["skipped_signals"]["skip_reason"] == "outside_entry_window"
    ]
    assert list(window_skips["signal_id"]) == projection["outside_entry_window_signal_ids"]

    produced_trades = canonicalize_trades(result["trades"]).to_csv(
        index=False, float_format="%.17g"
    )
    assert produced_trades == TRADES_CSV_PATH.read_text(encoding="utf-8")

    produced_skips = _skip_projection(window_skips).to_csv(index=False, float_format="%.17g")
    assert produced_skips == SKIPPED_CSV_PATH.read_text(encoding="utf-8")


def test_entry_window_enabled_c7_focus_equals_admit():
    result_all = run_entry_window_enabled_pipeline(enabled=False)
    result_admit = run_entry_window_enabled_pipeline(enabled=True)
    focused = filter_trades_by_entry_window(
        result_all["trades"],
        ENTRY_WINDOW,
        exchange_tz="America/New_York",
        timestamp_col="entry_timestamp",
    )
    assert set(result_admit["trades"]["signal_id"]) == set(focused["signal_id"])


def test_entry_window_enabled_signal_bar_index_matches_timestamp():
    data = generate_entry_window_enabled_dataset()
    signals = generate_entry_window_enabled_signals(data)
    for row in signals.itertuples(index=False):
        bar_ts = pd.Timestamp(data["timestamp"].iloc[int(row.bar_index)])
        assert bar_ts == pd.Timestamp(row.timestamp)


def test_entry_window_family_does_not_rewrite_legacy_artifacts():
    """Enabled family recorder isolation: legacy files remain present."""
    for name in LEGACY_ARTIFACTS:
        path = FIXTURE_DIR / name
        assert path.is_file(), f"Legacy golden artifact missing: {name}"
    # Enabled family artifact names must not collide with legacy names.
    assert DATASET_PATH.name.startswith("entry_window_enabled_")
    assert TRADES_CSV_PATH.name.startswith("entry_window_enabled_")
