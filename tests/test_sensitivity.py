from __future__ import annotations

import pandas as pd

from thesistester.analytics.sensitivity import sensitivity_summary


def _ohlcv() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 09:30", periods=8, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [102.0] * len(timestamps),
            "low": [98.0] * len(timestamps),
            "close": [100.0] * len(timestamps),
            "volume": [100.0] * len(timestamps),
        }
    )


def _trades(expectancy: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": [1, 2],
            "signal_id": [1, 2],
            "direction": ["long", "long"],
            "entry_timestamp": pd.date_range(
                "2026-01-05 09:30", periods=2, freq="1min", tz="America/New_York"
            ),
            "exit_timestamp": pd.date_range(
                "2026-01-05 09:31", periods=2, freq="1min", tz="America/New_York"
            ),
            "r_multiple": [expectancy, expectancy],
        }
    )


def _profile(monkeypatch, expectancies: dict[float, float]):
    def fake_simulate_trades(**kwargs):
        return _trades(expectancies[kwargs["stop_loss_ticks"]])

    monkeypatch.setattr("thesistester.analytics.sensitivity.simulate_trades", fake_simulate_trades)
    return sensitivity_summary(
        _ohlcv(),
        pd.DataFrame(),
        tick_size=1.0,
        point_value=1.0,
        selected_cell={
            "stop_loss_ticks": 10.0,
            "take_profit_ticks": 20.0,
            "breakeven_after_r": None,
            "trailing_after_r": None,
            "trailing_distance_ticks": None,
        },
        perturbation_fraction=0.2,
        n_steps_per_side=2,
        parameters=["stop_loss_ticks"],
    )


def test_sensitivity_flags_cliff_edge_and_is_deterministic(monkeypatch):
    expectancies = {8.0: -1.0, 9.0: -1.0, 10.0: 1.0, 11.0: -1.0, 12.0: -1.0}
    first = _profile(monkeypatch, expectancies)
    second = _profile(monkeypatch, expectancies)

    assert first == second
    assert first["schema_version"] == 1
    assert first["parameters"][0]["fragile"] is True
    assert first["fragile_parameter_count"] == 1
    assert [row["parameter_value"] for row in first["parameters"][0]["curve"]] == [
        8.0,
        9.0,
        10.0,
        11.0,
        12.0,
    ]


def test_sensitivity_does_not_flag_plateau(monkeypatch):
    summary = _profile(monkeypatch, {8.0: 0.5, 9.0: 0.5, 10.0: 0.5, 11.0: 0.5, 12.0: 0.5})

    assert summary["parameters"][0]["fragile"] is False
    assert summary["baseline"]["expectancy_r"] == 0.5
