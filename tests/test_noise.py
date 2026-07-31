from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.noise import (
    assert_valid_ohlc,
    noise_summary,
    perturb_ohlc,
    trade_persistence_rate,
)


def _ohlcv() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 09:30", periods=12, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.0] * len(timestamps),
            "volume": [100.0] * len(timestamps),
        }
    )


def _trades(signal_ids: list[int]) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 10:00", periods=len(signal_ids), freq="1min")
    return pd.DataFrame(
        {
            "signal_id": signal_ids,
            "direction": ["long"] * len(signal_ids),
            "entry_timestamp": timestamps,
            "exit_timestamp": timestamps,
            "r_multiple": [1.0 if index % 2 else -0.5 for index in range(len(signal_ids))],
        }
    )


@pytest.mark.parametrize("basis", ["atr", "range"])
def test_perturbations_preserve_ohlc_invariants_and_do_not_mutate_source(basis):
    source = _ohlcv()
    original = source.copy(deep=True)
    for seed in range(25):
        replica = perturb_ohlc(
            source,
            noise_fraction=0.10,
            scale_basis=basis,
            random_state=seed,
        )
        assert_valid_ohlc(replica)
    pd.testing.assert_frame_equal(source, original)


def test_noise_summary_is_seeded_and_has_a_stable_export_contract():
    source = _ohlcv()
    baseline = _trades([0, 1, 2])

    def runner(replica: pd.DataFrame) -> pd.DataFrame:
        return _trades([0, 1]) if float(replica["close"].iloc[0]) < 100.0 else _trades([0, 1, 2])

    first = noise_summary(
        source,
        baseline,
        replica_runner=runner,
        n_replicas=20,
        noise_fraction=0.10,
        random_state=7,
        include_rows=True,
    )
    second = noise_summary(
        source,
        baseline,
        replica_runner=runner,
        n_replicas=20,
        noise_fraction=0.10,
        random_state=7,
        include_rows=True,
    )
    assert first == second
    assert set(first) == {
        "schema_version",
        "available",
        "config",
        "baseline",
        "replicas",
        "caveat",
    }
    assert first["available"] is True
    assert first["replicas"]["n_completed"] == 20
    assert len(first["replicas"]["rows"]) == 20


def test_fragile_single_bar_trigger_has_visibly_degraded_persistence():
    source = _ohlcv()
    baseline = _trades([0])

    def fragile_runner(replica: pd.DataFrame) -> pd.DataFrame:
        # The exact baseline close is on the trigger cliff. Symmetric perturbation
        # removes the sole entry whenever the first synthetic close falls below it.
        return _trades([0]) if float(replica["close"].iloc[0]) >= 100.0 else _trades([])

    summary = noise_summary(
        source,
        baseline,
        replica_runner=fragile_runner,
        n_replicas=100,
        noise_fraction=0.10,
        random_state=42,
    )
    assert summary["replicas"]["trade_persistence_rate"]["p25"] < 0.9


def test_persistence_prefers_signal_id_and_empty_baseline_is_safe():
    baseline = _trades([1, 2])
    replica = _trades([2, 3])
    assert trade_persistence_rate(baseline, replica) == pytest.approx(0.5)
    summary = noise_summary(
        _ohlcv(),
        _trades([]),
        replica_runner=lambda _: _trades([]),
        n_replicas=1,
        random_state=1,
    )
    assert summary["available"] is False
