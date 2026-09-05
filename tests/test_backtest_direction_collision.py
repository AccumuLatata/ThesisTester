"""DA1 — same-bar opposite-direction collision diagnostic."""

from __future__ import annotations

from dataclasses import fields

import pandas as pd

from thesistester.engine.backtest import SimulationResult, simulate_trades
from thesistester.research_bundle import (
    _BACKTEST_META_KEYS,
    build_research_bundle,
    canonical_bundle_hash,
)


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _signal(
    bar_index: int,
    *,
    direction: str,
    signal_id: int,
    entry_ref: float = 100.0,
) -> dict:
    return {
        "signal_id": signal_id,
        "timestamp": pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
        "bar_index": bar_index,
        "trigger": "touch",
        "direction": direction,
        "zone_low": 99.5,
        "zone_high": 100.5,
        "zone_mid": 100.0,
        "level_count": 2,
        "level_names": "A|B",
        "entry_reference_price": entry_ref,
        "entry_model": "candidate_next_bar_open",
        "status": "candidate",
        "naked_level_count": 0,
        "naked_requirement": "any",
        "notes": "",
    }


def _three_touch_pairs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Three isolated touch bars, each with a long then a short candidate."""
    df = pd.DataFrame(
        [
            _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:31", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:32", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:35", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:36", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:37", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:40", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:41", 100.0, 115.0, 85.0, 100.0),
            _bar("2026-01-02 09:42", 100.0, 101.0, 99.0, 100.0),
        ]
    )
    signals = pd.DataFrame(
        [
            _signal(0, direction="long", signal_id=0),
            _signal(0, direction="short", signal_id=1),
            _signal(3, direction="long", signal_id=2),
            _signal(3, direction="short", signal_id=3),
            _signal(6, direction="long", signal_id=4),
            _signal(6, direction="short", signal_id=5),
        ]
    )
    return df, signals


def _simulate(policy: str, **kwargs) -> SimulationResult:
    df, signals = _three_touch_pairs()
    result = simulate_trades(
        df,
        signals,
        tick_size=TICK,
        point_value=POINT_VALUE,
        stop_loss_ticks=8,
        take_profit_ticks=8,
        exposure_policy=policy,
        return_result=True,
        **kwargs,
    )
    assert isinstance(result, SimulationResult)
    return result


def test_single_position_resolves_three_pairs_long_only():
    result = _simulate("single_position")
    diagnostic = result.direction_collision_diagnostic
    assert diagnostic["policy"] == "legacy"
    assert diagnostic["candidate_pairs"] == 3
    assert diagnostic["resolved_long"] == 3
    assert diagnostic["resolved_short"] == 0
    assert diagnostic["resolved_none"] == 0
    assert diagnostic["accepted_trade_share_from_pairs"] == 1.0
    assert list(result.trades["direction"]) == ["long", "long", "long"]


def test_single_direction_accepts_both_sides_of_each_pair():
    result = _simulate("single_direction")
    diagnostic = result.direction_collision_diagnostic
    assert diagnostic["candidate_pairs"] == 3
    assert diagnostic["resolved_long"] == 3
    assert diagnostic["resolved_short"] == 3
    assert diagnostic["resolved_none"] == 0
    assert diagnostic["accepted_trade_share_from_pairs"] == 1.0
    assert set(result.trades["direction"]) == {"long", "short"}
    assert len(result.trades) == 6


def test_allow_all_matches_single_direction_pair_counts():
    result = _simulate("allow_all")
    diagnostic = result.direction_collision_diagnostic
    assert diagnostic["candidate_pairs"] == 3
    assert diagnostic["resolved_long"] == 3
    assert diagnostic["resolved_short"] == 3
    assert diagnostic["resolved_none"] == 0
    assert diagnostic["accepted_trade_share_from_pairs"] == 1.0
    assert len(result.trades) == 6


def test_legacy_return_shapes_do_not_expose_diagnostic():
    df, signals = _three_touch_pairs()
    kwargs = dict(
        df=df,
        signals=signals,
        tick_size=TICK,
        point_value=POINT_VALUE,
        stop_loss_ticks=8,
        take_profit_ticks=8,
        exposure_policy="single_position",
    )
    trades = simulate_trades(**kwargs)
    assert isinstance(trades, pd.DataFrame)
    assert not hasattr(trades, "direction_collision_diagnostic")

    trades_tuple, skipped = simulate_trades(**kwargs, return_skipped_signals=True)
    assert isinstance(trades_tuple, pd.DataFrame)
    assert isinstance(skipped, pd.DataFrame)
    assert not hasattr(trades_tuple, "direction_collision_diagnostic")

    detailed = simulate_trades(**kwargs, return_result=True)
    assert isinstance(detailed, SimulationResult)
    assert "candidate_pairs" in detailed.direction_collision_diagnostic


def test_empty_signals_return_zero_diagnostic():
    df, _ = _three_touch_pairs()
    empty = pd.DataFrame(columns=["signal_id", "bar_index", "trigger", "direction", "status"])
    result = simulate_trades(
        df,
        empty,
        tick_size=TICK,
        point_value=POINT_VALUE,
        stop_loss_ticks=8,
        take_profit_ticks=8,
        return_result=True,
    )
    assert result.direction_collision_diagnostic == {
        "policy": "legacy",
        "candidate_pairs": 0,
        "resolved_long": 0,
        "resolved_short": 0,
        "resolved_none": 0,
        "accepted_trade_share_from_pairs": 0.0,
    }


def test_simulation_result_four_field_positional_construction_still_works():
    names = [item.name for item in fields(SimulationResult)]
    assert names[:4] == [
        "trades",
        "skipped_signals",
        "intrabar_diagnostic",
        "exit_management_diagnostic",
    ]
    empty_trades = pd.DataFrame()
    constructed = SimulationResult(empty_trades, empty_trades, {}, {})
    assert constructed.direction_collision_diagnostic == {}


def test_direction_collision_is_not_a_hashed_bundle_meta_key():
    assert "direction_collision_diagnostic" not in _BACKTEST_META_KEYS
    assert "backtest_direction_collision_diagnostic" not in _BACKTEST_META_KEYS

    trades = pd.DataFrame(
        [
            {
                "trade_id": 1,
                "signal_id": 0,
                "direction": "long",
                "r_multiple": 1.0,
                "exit_timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ),
                "pnl_currency": 50.0,
            }
        ]
    )
    equity = pd.DataFrame(
        [{"exit_timestamp": pd.Timestamp("2026-01-02 09:31:00", tz=TZ), "equity_r": 1.0}]
    )
    base_state = {
        "dataset_id": "ds",
        "instrument": "ES",
        "trades": trades,
        "equity_curve": equity,
        "trade_summary": {"trade_count": 1, "expectancy_r": 1.0},
        "backtest_intrabar_diagnostic": {"same_bar_both_hit_count": 0},
        "backtest_exit_management_diagnostic": {"be_exit_count": 0},
    }
    baseline = build_research_bundle(base_state)
    with_collision = build_research_bundle(
        {
            **base_state,
            "direction_collision_diagnostic": {
                "policy": "legacy",
                "candidate_pairs": 3,
                "resolved_long": 3,
                "resolved_short": 0,
                "resolved_none": 0,
                "accepted_trade_share_from_pairs": 1.0,
            },
        }
    )
    assert canonical_bundle_hash(baseline) == canonical_bundle_hash(with_collision)
