"""DA4 — fade / continuation approach-side triggers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.fixtures.assistant_parity import parity_run_spec, write_parity_bars
from thesistester.api import run_experiment
from thesistester.engine.backtest import simulate_trades
from thesistester.engine.signals import (
    _SIGNAL_COLUMNS,
    VALID_TRIGGERS,
    generate_signals,
)
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.setup import VALID_TRIGGERS as SETUP_VALID_TRIGGERS


TZ = "America/New_York"
TICK = 0.25
POINT_VALUE = 50.0
# Pre-DA4 capture of tests.fixtures.assistant_parity touch run_experiment bundle.
_PRE_DA4_TOUCH_BUNDLE_HASH = "50f9d271d70c8fbc297a0cc3e9992bc096b997e9fd66d858fe101e2520a27807"


def _bar(ts: str, o: float, h: float, l: float, c: float, vol: float = 100.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


def _zone(bar_index: int, ts: str, *, low: float = 100.0, high: float = 101.0) -> dict:
    return {
        "timestamp": pd.Timestamp(ts, tz=TZ),
        "bar_index": bar_index,
        "zone_low": low,
        "zone_high": high,
        "zone_mid": (low + high) / 2.0,
        "level_count": 2,
        "level_names": "A|B",
        "level_prices": f"{low}|{high}",
    }


def _frame(bars: list[dict], zones: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(bars), pd.DataFrame(zones)


def _generate(df: pd.DataFrame, zones: pd.DataFrame, trigger: str, **kwargs) -> pd.DataFrame:
    return generate_signals(
        df,
        zones,
        trigger=trigger,
        direction=kwargs.pop("direction", "both"),
        tick_size=TICK,
        **kwargs,
    )


def test_setup_and_engine_trigger_sets_stay_in_lockstep():
    assert SETUP_VALID_TRIGGERS == VALID_TRIGGERS
    assert {"fade", "continuation"} <= VALID_TRIGGERS


def test_approach_from_above_fade_long_continuation_short():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 102.0, 102.5, 101.5, 102.0),
            _bar("2026-01-02 09:31", 101.5, 102.0, 100.2, 100.8),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    fade = _generate(df, zones, "fade")
    cont = _generate(df, zones, "continuation")
    assert list(fade["direction"]) == ["long"]
    assert list(fade["approach_side"]) == ["above"]
    assert list(fade["trigger"]) == ["fade"]
    assert list(cont["direction"]) == ["short"]
    assert list(cont["approach_side"]) == ["above"]
    assert list(cont["trigger"]) == ["continuation"]
    assert fade.loc[0, "entry_model"] == "candidate_next_bar_open"
    assert fade.loc[0, "entry_reference_price"] == pytest.approx(100.8)


def test_approach_from_below_fade_short_continuation_long():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 99.0, 99.5, 98.5, 99.0),
            _bar("2026-01-02 09:31", 99.2, 100.8, 98.8, 100.4),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    fade = _generate(df, zones, "fade")
    cont = _generate(df, zones, "continuation")
    assert list(fade["direction"]) == ["short"]
    assert list(fade["approach_side"]) == ["below"]
    assert list(cont["direction"]) == ["long"]
    assert list(cont["approach_side"]) == ["below"]


def test_prev_close_inside_zone_emits_nothing():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 100.4, 100.6, 100.2, 100.5),
            _bar("2026-01-02 09:31", 100.5, 101.2, 99.8, 100.6),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    assert _generate(df, zones, "fade").empty
    assert _generate(df, zones, "continuation").empty


def test_first_bar_emits_nothing():
    df, zones = _frame(
        [_bar("2026-01-02 09:30", 102.0, 102.5, 100.2, 100.8)],
        [_zone(0, "2026-01-02 09:30")],
    )
    assert _generate(df, zones, "fade").empty
    assert _generate(df, zones, "continuation").empty


def test_direction_long_filters_out_short_fade():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 99.0, 99.5, 98.5, 99.0),
            _bar("2026-01-02 09:31", 99.2, 100.8, 98.8, 100.4),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    both = _generate(df, zones, "fade", direction="both")
    long_only = _generate(df, zones, "fade", direction="long")
    assert list(both["direction"]) == ["short"]
    assert long_only.empty


def test_both_never_emits_two_directions_for_one_zone():
    rng = np.random.default_rng(42)
    ts0 = pd.Timestamp("2026-01-02 09:30", tz=TZ)
    price = 100.5
    rows = []
    for i in range(400):
        price = price + float(rng.normal(0.0, 0.35)) + 0.08 * (100.5 - price)
        high = price + 0.6
        low = price - 0.6
        rows.append(
            {
                "timestamp": ts0 + pd.Timedelta(minutes=i),
                "open": price,
                "high": high,
                "low": low,
                "close": price + float(rng.normal(0.0, 0.1)),
                "volume": 100.0,
            }
        )
    df = pd.DataFrame(rows)
    zones = pd.DataFrame([_zone(i, str(df.loc[i, "timestamp"])) for i in range(len(df))])
    fade = _generate(df, zones, "fade")
    if fade.empty:
        pytest.skip("OU draw produced no fade touches")
    assert int(fade.groupby("bar_index")["direction"].nunique().max()) == 1


def test_two_zones_can_emit_opposite_directions_on_one_bar():
    df, _ = _frame(
        [
            _bar("2026-01-02 09:30", 102.5, 103.0, 102.0, 102.5),
            _bar("2026-01-02 09:31", 102.0, 106.0, 98.0, 102.0),
        ],
        [],
    )
    zones = pd.DataFrame(
        [
            _zone(1, "2026-01-02 09:31", low=99.0, high=100.0),
            _zone(1, "2026-01-02 09:31", low=104.0, high=105.0),
        ]
    )
    fade = _generate(df, zones, "fade")
    assert set(fade["direction"]) == {"long", "short"}
    assert fade["bar_index"].nunique() == 1
    assert len(fade) == 2


def test_require_close_confirmation_fade_and_continuation():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 102.0, 102.5, 101.5, 102.0),
            _bar("2026-01-02 09:31", 101.5, 102.0, 100.2, 100.8),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    params = {"require_close_confirmation": True}
    fade_off = _generate(df, zones, "fade")
    fade_on = _generate(df, zones, "fade", trigger_params=params)
    cont_off = _generate(df, zones, "continuation")
    cont_on = _generate(df, zones, "continuation", trigger_params=params)
    assert list(fade_off["direction"]) == ["long"]
    assert fade_on.empty
    assert list(cont_off["direction"]) == ["short"]
    assert cont_on.empty

    confirmed, confirmed_zones = _frame(
        [
            _bar("2026-01-02 09:30", 102.0, 102.5, 101.5, 102.0),
            _bar("2026-01-02 09:31", 101.5, 102.2, 100.2, 101.4),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    fade_conf = _generate(confirmed, confirmed_zones, "fade", trigger_params=params)
    assert list(fade_conf["direction"]) == ["long"]

    through, through_zones = _frame(
        [
            _bar("2026-01-02 09:30", 102.0, 102.5, 101.5, 102.0),
            _bar("2026-01-02 09:31", 101.5, 102.0, 99.2, 99.6),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    cont_conf = _generate(through, through_zones, "continuation", trigger_params=params)
    assert list(cont_conf["direction"]) == ["short"]


def test_single_zone_fade_has_zero_collision_pairs():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 102.0, 102.5, 101.5, 102.0),
            _bar("2026-01-02 09:31", 101.5, 102.0, 100.2, 100.8),
            _bar("2026-01-02 09:32", 100.8, 101.0, 100.0, 100.5),
            _bar("2026-01-02 09:33", 99.0, 99.4, 98.6, 99.0),
            _bar("2026-01-02 09:34", 99.2, 100.8, 98.8, 100.4),
            _bar("2026-01-02 09:35", 100.4, 100.8, 100.0, 100.2),
        ],
        [
            _zone(1, "2026-01-02 09:31"),
            _zone(4, "2026-01-02 09:34"),
        ],
    )
    signals = _generate(df, zones, "fade")
    result = simulate_trades(
        df,
        signals,
        tick_size=TICK,
        point_value=POINT_VALUE,
        stop_loss_ticks=8,
        take_profit_ticks=8,
        exposure_policy="single_position",
        return_result=True,
    )
    assert result.direction_collision_diagnostic["candidate_pairs"] == 0
    assert set(signals["direction"]) == {"long", "short"}


def test_touch_column_set_equals_pre_da4_signal_columns():
    df, zones = _frame(
        [
            _bar("2026-01-02 09:30", 100.0, 101.0, 99.0, 100.0),
            _bar("2026-01-02 09:31", 100.0, 101.0, 99.0, 100.0),
        ],
        [_zone(1, "2026-01-02 09:31")],
    )
    touch = _generate(df, zones, "touch")
    assert list(touch.columns) == _SIGNAL_COLUMNS
    assert "approach_side" not in touch.columns
    empty = generate_signals(
        df,
        pd.DataFrame(columns=zones.columns),
        trigger="touch",
        direction="both",
        tick_size=TICK,
    )
    assert list(empty.columns) == _SIGNAL_COLUMNS
    assert "approach_side" not in empty.columns
    fade = _generate(df, zones, "fade")
    if not fade.empty:
        assert "approach_side" in fade.columns


def test_touch_run_experiment_bundle_hash_matches_pre_da4_capture():
    with tempfile.TemporaryDirectory() as tmp:
        bars = write_parity_bars(Path(tmp) / "bars.csv")
        state = run_experiment(parity_run_spec(dataset_path=str(bars)), base_directory=Path(tmp))
        assert "approach_side" not in state["signals"].columns
        digest = canonical_bundle_hash(build_research_bundle(state))
        assert digest == _PRE_DA4_TOUCH_BUNDLE_HASH
