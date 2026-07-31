from __future__ import annotations

import pandas as pd
import pytest

from thesistester.analytics.overfitting import (
    cscv_pbo,
    deflated_sharpe,
    grid_trade_sequences,
    overfitting_summary,
    probabilistic_sharpe,
    vs_random_benchmark,
)


def _trades(values: list[float], *, direction: str = "long") -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-01-05 09:30",
        periods=len(values),
        freq="1min",
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "trade_id": range(len(values)),
            "signal_id": range(len(values)),
            "direction": [direction] * len(values),
            "entry_timestamp": timestamps,
            "exit_timestamp": timestamps,
            "r_multiple": values,
            "stop_loss_ticks": [2.0] * len(values),
            "take_profit_ticks": [4.0] * len(values),
        }
    )


def _ohlcv() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-01-05 09:30",
        periods=20,
        freq="1min",
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [103.0] * len(timestamps),
            "low": [97.0] * len(timestamps),
            "close": [100.0] * len(timestamps),
            "volume": [100.0] * len(timestamps),
        }
    )


def _directional_trades(long_returns: list[float], short_returns: list[float]) -> pd.DataFrame:
    long_trades = _trades(long_returns, direction="long")
    short_trades = _trades(short_returns, direction="short")
    short_trades["trade_id"] += len(long_trades)
    short_trades["signal_id"] += len(long_trades)
    return pd.concat([long_trades, short_trades], ignore_index=True)


def test_grid_trade_sequences_preserves_directional_grid_selection_schema(monkeypatch):
    """R15 sequence summaries must support the recorded Grid Search rule."""
    directional_cells = {
        2.0: _directional_trades([2.0, 2.0], [-1.0, -1.0]),
        3.0: _directional_trades([1.0, 1.0], [1.0, 1.0]),
    }

    def fake_simulate_trades(**kwargs):
        return directional_cells[kwargs["stop_loss_ticks"]].copy()

    monkeypatch.setattr(
        "thesistester.analytics.overfitting.simulate_trades",
        fake_simulate_trades,
    )
    sequences = grid_trade_sequences(
        _ohlcv(),
        pd.DataFrame(),
        tick_size=1.0,
        point_value=1.0,
        grid=pd.DataFrame(
            {
                "stop_loss_ticks": [2.0, 3.0],
                "take_profit_ticks": [4.0, 4.0],
                "breakeven_after_r": [None, None],
                "trailing_after_r": [None, None],
                "trailing_distance_ticks": [None, None],
            }
        ),
    )

    assert {
        "long_trade_count",
        "short_trade_count",
        "long_expectancy_r",
        "short_expectancy_r",
        "min_direction_expectancy_r",
    } <= set(sequences.grid_results.columns)
    eligible = sequences.grid_results[
        (sequences.grid_results["long_trade_count"] >= 1)
        & (sequences.grid_results["short_trade_count"] >= 1)
    ]
    selected = eligible.sort_values(
        ["long_expectancy_r", "stop_loss_ticks", "take_profit_ticks"],
        ascending=[False, True, True],
        kind="mergesort",
    ).iloc[0]
    assert selected["stop_loss_ticks"] == 2.0
    assert selected["long_expectancy_r"] == pytest.approx(2.0)


def test_cscv_hand_computed_four_partition_fixture():
    cells = {
        (2.0, 4.0, None, None, None): _trades([2.0, 2.0, -2.0, -2.0]),
        (3.0, 4.0, None, None, None): _trades([1.0, 1.0, 1.0, 1.0]),
    }
    result = cscv_pbo(cells, partitions=4, min_trades=1)
    assert result["available"] is True
    assert result["n_combinations"] == 6
    assert result["pbo"] == pytest.approx(1.0 / 3.0)
    assert {round(item["logit_lambda"], 8) for item in result["split_results"]} == {
        round(-0.6931471805599453, 8),
        round(0.6931471805599453, 8),
    }


def test_cscv_is_deterministic_and_rejects_invalid_partition_count():
    cells = {
        (2.0, 4.0, None, None, None): _trades([1.0, -1.0, 1.0, -1.0]),
        (3.0, 4.0, None, None, None): _trades([0.5, 0.5, 0.5, 0.5]),
    }
    assert cscv_pbo(cells, partitions=4) == cscv_pbo(cells, partitions=4)
    with pytest.raises(ValueError, match="even"):
        cscv_pbo(cells, partitions=3)


def test_psr_and_dsr_handle_moments_and_trial_deflation():
    selected = _trades([1.0, 0.5, 1.5, 0.25, 1.2, 0.8])
    psr = probabilistic_sharpe(selected)
    assert psr["available"] is True
    assert 0.5 < psr["psr"] <= 1.0
    dsr_one = deflated_sharpe(selected, [psr["sharpe_like_r"], psr["sharpe_like_r"] - 0.01])
    dsr_many = deflated_sharpe(
        selected,
        [psr["sharpe_like_r"], psr["sharpe_like_r"] - 0.2],
        effective_trials=100,
    )
    assert dsr_one["dsr"] is not None
    assert dsr_many["dsr"] is not None
    assert dsr_many["dsr"] <= dsr_one["dsr"]
    assert probabilistic_sharpe(_trades([1.0, 1.0, 1.0]))["available"] is False


def test_vs_random_is_seed_deterministic_and_never_returns_zero_p_value():
    df = _ohlcv()
    reference = _trades([1.0, -1.0, 0.5, -0.5])
    first = vs_random_benchmark(
        df,
        reference,
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2.0,
        take_profit_ticks=4.0,
        n_replicas=25,
        random_state=7,
    )
    second = vs_random_benchmark(
        df,
        reference,
        tick_size=1.0,
        point_value=1.0,
        stop_loss_ticks=2.0,
        take_profit_ticks=4.0,
        n_replicas=25,
        random_state=7,
    )
    assert first == second
    assert first["available"] is True
    assert 0.0 < first["p_value_greater_or_equal"] <= 1.0


def test_overfitting_summary_contract_is_stable():
    selected = _trades([1.0, 0.5, -0.25, 0.75])
    cells = {
        (2.0, 4.0, None, None, None): selected,
        (3.0, 4.0, None, None, None): _trades([0.2, 0.1, 0.3, 0.2]),
    }
    grid = pd.DataFrame(
        {
            "stop_loss_ticks": [2.0, 3.0],
            "take_profit_ticks": [4.0, 4.0],
            "sharpe_like_r": [0.5, 0.2],
        }
    )
    summary = overfitting_summary(
        selected_trades=selected,
        cell_trades=cells,
        grid_results=grid,
        df=_ohlcv(),
        tick_size=1.0,
        point_value=1.0,
        pbo_partitions=4,
        vs_random_n_replicas=10,
        random_state=42,
    )
    assert summary["schema_version"] == 1
    assert set(summary) == {
        "schema_version",
        "available",
        "config",
        "pbo",
        "deflated_sharpe",
        "vs_random",
        "caveat",
    }
