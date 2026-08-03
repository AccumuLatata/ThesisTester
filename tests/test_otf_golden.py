"""Enabled-OTF golden / drift gate (hardening PR 3).

Isolated from the legacy golden-master family. Legacy artifacts must remain
byte-identical; this module only verifies the additive ``otf_enabled_*`` family.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from thesistester.engine.otf_integration import apply_configured_otf_filter
from tests.fixtures.golden.canonical import canonicalize_trades
from tests.fixtures.golden.generate_otf_enabled import (
    ETH_START,
    TIMEZONE,
    generate_otf_enabled_dataset,
    generate_otf_enabled_signals,
    otf_enabled_setup_config,
)
from tests.fixtures.golden.pipeline import run_legacy_pipeline
from tests.fixtures.golden.pipeline_otf_enabled import run_otf_enabled_pipeline
from tests.fixtures.golden.generate import generate_dataset
from tests.fixtures.golden.record_otf_enabled_golden import (
    ACCEPTED_CSV_PATH,
    DATASET_PATH,
    MANIFEST_PATH,
    PROJECTION_PATH,
    REJECTED_CSV_PATH,
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


def test_otf_enabled_artifacts_are_complete():
    manifest = _load_manifest()
    assert manifest["family"] == "otf_enabled"
    assert manifest["fixture_version"] == 1
    for path in (
        DATASET_PATH,
        ACCEPTED_CSV_PATH,
        REJECTED_CSV_PATH,
        TRADES_CSV_PATH,
        PROJECTION_PATH,
        MANIFEST_PATH,
    ):
        assert path.is_file(), f"Missing enabled-OTF golden artifact: {path.name}"


def test_otf_enabled_generator_rebuilds_recorded_dataset():
    recorded = pd.read_parquet(DATASET_PATH)
    generated = generate_otf_enabled_dataset()
    pd.testing.assert_frame_equal(recorded, generated, check_dtype=False, check_exact=True)


def test_otf_enabled_signal_bar_index_matches_timestamp():
    """bar_index must point at the decision timestamp bar for next-bar entry."""
    data = generate_otf_enabled_dataset()
    signals = generate_otf_enabled_signals(data)
    for row in signals.itertuples(index=False):
        bar_ts = pd.Timestamp(data["timestamp"].iloc[int(row.bar_index)])
        assert bar_ts == pd.Timestamp(row.timestamp)


def test_otf_enabled_trades_enter_on_bar_after_decision_timestamp():
    result = run_otf_enabled_pipeline()
    accepted = result["accepted_signals"].set_index("signal_id")
    data = result["data"]
    for trade in result["trades"].itertuples(index=False):
        decision_bar = int(accepted.loc[int(trade.signal_id), "bar_index"])
        decision_ts = pd.Timestamp(accepted.loc[int(trade.signal_id), "timestamp"])
        assert pd.Timestamp(data["timestamp"].iloc[decision_bar]) == decision_ts
        assert int(trade.entry_bar_index) == decision_bar + 1
        assert pd.Timestamp(trade.entry_timestamp) == pd.Timestamp(
            data["timestamp"].iloc[decision_bar + 1]
        )


def test_enabled_fixture_reproduces_accepted_and_rejected_populations():
    result = run_otf_enabled_pipeline()
    projection = _load_projection()

    assert list(result["accepted_signals"]["signal_id"]) == projection["accepted_signal_ids"]
    assert list(result["rejected_signals"]["signal_id"]) == projection["rejected_signal_ids"]

    produced_accepted = _signal_projection(result["accepted_signals"]).to_csv(
        index=False, float_format="%.17g"
    )
    produced_rejected = _signal_projection(result["rejected_signals"]).to_csv(
        index=False, float_format="%.17g"
    )
    assert produced_accepted == ACCEPTED_CSV_PATH.read_text(encoding="utf-8")
    assert produced_rejected == REJECTED_CSV_PATH.read_text(encoding="utf-8")

    produced_reasons = {
        str(int(row.signal_id)): row.otf_filter_reason
        for row in result["rejected_signals"].itertuples(index=False)
    }
    assert produced_reasons == projection["rejection_reasons"]


def test_enabled_fixture_reproduces_trade_projection():
    result = run_otf_enabled_pipeline()
    projection = _load_projection()
    assert int(len(result["trades"])) == projection["trade_count"]
    assert projection["trade_count"] >= 1

    # Compare the stable text projection (same strategy as legacy trades_legacy.csv).
    expected = TRADES_CSV_PATH.read_text(encoding="utf-8")
    produced = canonicalize_trades(result["trades"]).to_csv(index=False, float_format="%.17g")
    assert produced == expected


def test_enabled_projection_identity_fields_are_stable():
    result = run_otf_enabled_pipeline()
    projection = _load_projection()
    produced = result["projection"]
    for key in (
        "otf_algorithm_version",
        "otf_config_hash",
        "otf_filter_config",
        "session_timezone",
        "eth_start",
        "candidate_signal_count",
        "otf_accepted_signal_count",
        "otf_rejected_signal_count",
        "rejection_rate",
        "accepted_signal_ids",
        "rejected_signal_ids",
        "rejection_reasons",
        "trade_count",
    ):
        assert produced[key] == projection[key]


def test_appending_future_bars_does_not_change_historical_enabled_otf_decisions():
    base = generate_otf_enabled_dataset()
    signals = generate_otf_enabled_signals()
    # Only evaluate signals that decide before the appended future window.
    historical = signals[
        signals["timestamp"] <= pd.Timestamp("2026-01-06 01:00:00", tz=TIMEZONE)
    ].copy()
    baseline = apply_configured_otf_filter(
        source_df=base,
        candidate_signals=historical,
        setup_config=otf_enabled_setup_config(),
        signal_settings={"otf_filter": otf_enabled_setup_config()["otf_filter"]},
        session_timezone=TIMEZONE,
        eth_start=ETH_START,
    )

    future_start = base["timestamp"].max() + pd.Timedelta(minutes=1)
    future = pd.date_range(future_start, periods=60, freq="1min", tz=TIMEZONE)
    future_rows = []
    price = float(base["close"].iloc[-1]) + 50.0
    for ts in future:
        future_rows.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 20.0,
                "low": price - 20.0,
                "close": price + 5.0,
                "volume": 9999.0,
            }
        )
        price += 1.0
    extended = pd.concat([base, pd.DataFrame(future_rows)], ignore_index=True)
    # Preserve session tags used by the generator path.
    from thesistester.data.sessions import tag_session
    from tests.fixtures.golden.generate_otf_enabled import INSTRUMENT

    extended = tag_session(extended.drop(columns=["session"], errors="ignore"), INSTRUMENT)

    shocked = apply_configured_otf_filter(
        source_df=extended,
        candidate_signals=historical,
        setup_config=otf_enabled_setup_config(),
        signal_settings={"otf_filter": otf_enabled_setup_config()["otf_filter"]},
        session_timezone=TIMEZONE,
        eth_start=ETH_START,
    )

    pd.testing.assert_series_equal(
        baseline.accepted_signals["signal_id"].reset_index(drop=True),
        shocked.accepted_signals["signal_id"].reset_index(drop=True),
    )
    pd.testing.assert_series_equal(
        baseline.rejected_signals["signal_id"].reset_index(drop=True),
        shocked.rejected_signals["signal_id"].reset_index(drop=True),
    )
    pd.testing.assert_series_equal(
        baseline.rejected_signals["otf_filter_reason"].reset_index(drop=True),
        shocked.rejected_signals["otf_filter_reason"].reset_index(drop=True),
    )


def test_extreme_future_highs_lows_do_not_change_historical_enabled_otf_decisions():
    base = generate_otf_enabled_dataset()
    signals = generate_otf_enabled_signals()
    historical = signals[
        signals["timestamp"] <= pd.Timestamp("2026-01-06 01:00:00", tz=TIMEZONE)
    ].copy()
    baseline = apply_configured_otf_filter(
        source_df=base,
        candidate_signals=historical,
        setup_config=otf_enabled_setup_config(),
        signal_settings={"otf_filter": otf_enabled_setup_config()["otf_filter"]},
        session_timezone=TIMEZONE,
        eth_start=ETH_START,
    )

    shocked_data = base.copy()
    # Append a single extreme future bar far after all historical decisions.
    last_ts = shocked_data["timestamp"].max() + pd.Timedelta(hours=2)
    shocked_data = pd.concat(
        [
            shocked_data,
            pd.DataFrame(
                [
                    {
                        "timestamp": last_ts,
                        "open": 1.0,
                        "high": 1_000_000.0,
                        "low": -1_000_000.0,
                        "close": 1.0,
                        "volume": 1.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    from thesistester.data.sessions import tag_session
    from tests.fixtures.golden.generate_otf_enabled import INSTRUMENT

    shocked_data = tag_session(shocked_data.drop(columns=["session"], errors="ignore"), INSTRUMENT)

    shocked = apply_configured_otf_filter(
        source_df=shocked_data,
        candidate_signals=historical,
        setup_config=otf_enabled_setup_config(),
        signal_settings={"otf_filter": otf_enabled_setup_config()["otf_filter"]},
        session_timezone=TIMEZONE,
        eth_start=ETH_START,
    )
    assert list(baseline.accepted_signals["signal_id"]) == list(
        shocked.accepted_signals["signal_id"]
    )
    assert list(baseline.rejected_signals["signal_id"]) == list(
        shocked.rejected_signals["signal_id"]
    )


def test_disabled_otf_on_enabled_fixture_is_pass_through():
    enabled = run_otf_enabled_pipeline(enabled=True)
    disabled = run_otf_enabled_pipeline(enabled=False)
    assert disabled["otf_summary"]["otf_filter_enabled"] is False
    assert len(disabled["accepted_signals"]) == len(generate_otf_enabled_signals())
    assert disabled["rejected_signals"].empty
    # Disabled path must not match the enabled admissions (fixture is non-trivial).
    assert list(enabled["accepted_signals"]["signal_id"]) != list(
        disabled["accepted_signals"]["signal_id"]
    )


def test_legacy_golden_pipeline_unchanged_by_enabled_otf_family():
    """Equivalent disabled legacy pipeline still matches recorded legacy trades."""
    data = generate_dataset()
    recorded = pd.read_parquet(FIXTURE_DIR / "trades_legacy.parquet")
    produced = run_legacy_pipeline(data)["trades"]
    pd.testing.assert_frame_equal(
        canonicalize_trades(recorded),
        canonicalize_trades(produced),
        check_dtype=False,
        check_exact=True,
    )


@pytest.mark.parametrize("filename", LEGACY_ARTIFACTS)
def test_legacy_golden_files_are_present_and_untouched_by_otf_family(filename: str):
    path = FIXTURE_DIR / filename
    assert path.is_file()
    # Enabled-OTF filenames must not collide with legacy names.
    assert not filename.startswith("otf_enabled_")
