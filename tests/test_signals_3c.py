from __future__ import annotations

import pandas as pd

from thesistester.engine.candidate_level import CandidateLevel
from thesistester.engine.signals_3c import detect_3c_setups


TZ = "America/New_York"
TICK = 0.25


def _df(rows: list[dict]) -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:30", periods=len(rows), freq="1min", tz=TZ)
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "timestamp": ts[i],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": 100.0,
            }
        )
    return pd.DataFrame(out)


def _candidate(
    direction: str = "long",
    price: float = 100.0,
    source_mode: str = "global_cluster",
    bar_index: int = 0,
) -> CandidateLevel:
    return CandidateLevel(
        source_mode=source_mode,
        zone_id="zone_0",
        level_id="L1",
        level_price=price,
        zone_low=price,
        zone_high=price,
        direction=direction,
        source_label="L1",
        bar_index=bar_index,
        timestamp=pd.Timestamp("2026-01-02 09:30:00", tz=TZ) + pd.Timedelta(minutes=bar_index),
        metadata={},
    )


def _run(rows: list[dict], direction: str = "long") -> dict:
    setups = detect_3c_setups(
        _df(rows),
        [_candidate(direction=direction)],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 1
    return setups[0]


def test_variants_long_short_muted_sfp():
    long_core = _run(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
        ],
        direction="long",
    )
    assert long_core["trigger_variant"] == "3c_long"

    long_muted = _run(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 100.9, "low": 100.1, "close": 100.4},
            {"open": 100.4, "high": 101.3, "low": 100.2, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
        ],
        direction="long",
    )
    assert long_muted["trigger_variant"] == "3c_long_muted"

    long_sfp = _run(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.4, "high": 101.3, "low": 99.8, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
        ],
        direction="long",
    )
    assert long_sfp["trigger_variant"] == "3c_sfp_long"

    long_sfp_muted = _run(
        [
            {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 100.9, "low": 100.1, "close": 100.4},
            {"open": 100.4, "high": 101.3, "low": 99.8, "close": 101.1},
            {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
        ],
        direction="long",
    )
    assert long_sfp_muted["trigger_variant"] == "3c_sfp_long_muted"

    short_core = _run(
        [
            {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},
            {"open": 99.4, "high": 99.8, "low": 98.7, "close": 98.9},
            {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
        ],
        direction="short",
    )
    assert short_core["trigger_variant"] == "3c_short"

    short_muted = _run(
        [
            {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},
            {"open": 99.5, "high": 99.9, "low": 99.1, "close": 99.4},
            {"open": 99.4, "high": 99.8, "low": 98.7, "close": 98.9},
            {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
        ],
        direction="short",
    )
    assert short_muted["trigger_variant"] == "3c_short_muted"

    short_sfp = _run(
        [
            {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},
            {"open": 99.6, "high": 100.2, "low": 98.7, "close": 98.9},
            {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
        ],
        direction="short",
    )
    assert short_sfp["trigger_variant"] == "3c_sfp_short"

    short_sfp_muted = _run(
        [
            {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},
            {"open": 99.5, "high": 99.9, "low": 99.1, "close": 99.4},
            {"open": 99.6, "high": 100.2, "low": 98.7, "close": 98.9},
            {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
        ],
        direction="short",
    )
    assert short_sfp_muted["trigger_variant"] == "3c_sfp_short_muted"


def test_invalid_cases_and_void_and_dedupe():
    # Arrival touches but does not close through.
    bad_arrival = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 99.9},
                {"open": 100.0, "high": 101.2, "low": 99.8, "close": 101.1},
                {"open": 101.0, "high": 101.2, "low": 100.4, "close": 100.8},
            ]
        ),
        [_candidate(direction="long")],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert bad_arrival == []

    # Reversal fails strict close through arrival high.
    bad_reversal = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 100.95},
                {"open": 101.0, "high": 101.2, "low": 100.5, "close": 100.9},
            ]
        ),
        [_candidate(direction="long")],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert bad_reversal == []

    # Valid reversal but no retrace in watch window -> void.
    void_setup = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
                {"open": 101.1, "high": 101.4, "low": 100.8, "close": 101.2},
                {"open": 101.2, "high": 101.5, "low": 100.7, "close": 101.3},
            ]
        ),
        [_candidate(direction="long")],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 2},
    )
    assert len(void_setup) == 1
    assert void_setup[0]["status"] == "void"
    assert void_setup[0]["entry_trigger_price"] == 100.6
    assert void_setup[0]["entry_bar_index"] is None
    assert void_setup[0]["retrace_entry_price"] is None

    # Dedup same effective setup while keeping source metadata count.
    dups = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
                {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
            ]
        ),
        [
            _candidate(direction="long"),
            _candidate(direction="long"),
        ],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(dups) == 1
    assert dups[0]["source_count"] >= 1


def test_no_lookahead_pragmatic():
    # Without retracement bar present yet, no setup should be emitted as filled.
    setups = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
            ]
        ),
        [_candidate(direction="long")],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 1},
    )
    assert len(setups) == 1
    assert setups[0]["status"] == "void"


def test_overlapping_same_level_direction_source_mode_is_suppressed():
    rows = [
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # bar 0 arrival candidate
        {"open": 100.8, "high": 101.3, "low": 100.4, "close": 101.1},  # bar 1 reversal for first setup
        {"open": 101.0, "high": 101.2, "low": 100.7, "close": 100.9},  # bar 2 still in watch window
        {"open": 100.9, "high": 101.5, "low": 100.8, "close": 101.3},  # bar 3 could reverse second arrival
        {"open": 101.4, "high": 101.6, "low": 100.9, "close": 101.5},  # bar 4
        {"open": 101.6, "high": 101.8, "low": 101.0, "close": 101.7},  # bar 5
    ]
    setups = detect_3c_setups(
        _df(rows),
        [
            _candidate(direction="long", source_mode="global_cluster", bar_index=0),
            _candidate(direction="long", source_mode="global_cluster", bar_index=2),
        ],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 1
    assert setups[0]["arrival_bar_index"] == 0


def test_overlapping_arrival_suppressed_when_invalidated_before_reversal():
    rows = [
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # bar 0 arrival
        {"open": 100.4, "high": 100.8, "low": 100.1, "close": 100.3},  # bar 1 inside + possible overlapping arrival
        {"open": 100.4, "high": 101.2, "low": 100.2, "close": 100.9},  # bar 2 invalidates bar 0; could reverse bar 1
        {"open": 100.9, "high": 101.0, "low": 100.3, "close": 100.6},  # bar 3 would fill bar 1 if not suppressed
    ]
    setups = detect_3c_setups(
        _df(rows),
        [
            _candidate(direction="long", source_mode="global_cluster", bar_index=0),
            _candidate(direction="long", source_mode="global_cluster", bar_index=1),
        ],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert setups == []


def test_same_level_different_source_modes_are_not_suppressed():
    rows = [
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},
        {"open": 100.8, "high": 101.3, "low": 100.4, "close": 101.1},
        {"open": 101.0, "high": 101.2, "low": 100.7, "close": 100.9},
    ]
    setups = detect_3c_setups(
        _df(rows),
        [
            _candidate(direction="long", source_mode="global_cluster", bar_index=0),
            _candidate(direction="long", source_mode="user_anchor", bar_index=0),
        ],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 2
    assert {s["level_source_mode"] for s in setups} == {"global_cluster", "user_anchor"}


def test_same_level_different_directions_are_independent():
    rows = [
        {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # long arrival
        {"open": 100.8, "high": 101.3, "low": 100.4, "close": 101.1},  # long reversal
        {"open": 101.0, "high": 101.2, "low": 100.5, "close": 100.9},  # long fill
        {"open": 99.6, "high": 100.0, "low": 99.0, "close": 99.5},     # short arrival
        {"open": 99.4, "high": 99.7, "low": 98.6, "close": 98.8},      # short reversal
        {"open": 98.9, "high": 99.4, "low": 98.7, "close": 99.1},      # short fill
    ]
    setups = detect_3c_setups(
        _df(rows),
        [
            _candidate(direction="long", source_mode="global_cluster", bar_index=0),
            _candidate(direction="short", source_mode="global_cluster", bar_index=3),
        ],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 2
    assert {s["direction"] for s in setups} == {"long", "short"}


# ---------------------------------------------------------------------------
# Arrival-tolerance deprecation regression tests
# ---------------------------------------------------------------------------

def test_arrival_near_miss_does_not_qualify():
    """A candle that comes close but does not actually touch the key level must not
    qualify as an arrival candle (no tolerance is allowed)."""
    # Level is 100.0; arrival candle low is 100.25 — does not touch the level.
    setups = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.25, "close": 100.5},  # near miss
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
                {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
            ]
        ),
        [_candidate(direction="long", price=100.0)],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert setups == [], "near-miss candle must not qualify as arrival"


def test_arrival_exact_touch_qualifies():
    """A candle whose low exactly equals the key level must qualify as a valid arrival."""
    setups = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.0, "close": 100.5},  # exact touch
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
                {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
            ]
        ),
        [_candidate(direction="long", price=100.0)],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 1, "exact-touch candle must qualify as arrival"
    assert setups[0]["status"] == "filled"


def test_legacy_config_with_nonzero_arrival_tolerance_is_ignored():
    """A config with arrival_tolerance_ticks=2.0 must produce the same detection
    result as one with arrival_tolerance_ticks=0.  The nonzero value must not allow
    a near-miss candle to qualify."""
    legacy_params = {
        "arrival_tolerance_ticks": 2.0,  # nonzero — must be ignored
        "entry_retrace_ticks": 2,
        "max_entry_wait_bars_after_reversal": 3,
    }
    setups = detect_3c_setups(
        _df(
            [
                {"open": 101.0, "high": 101.0, "low": 100.25, "close": 100.5},
                {"open": 100.6, "high": 101.3, "low": 100.2, "close": 101.1},
                {"open": 101.0, "high": 101.1, "low": 100.5, "close": 100.9},
            ]
        ),
        [_candidate(direction="long", price=100.0)],
        tick_size=TICK,
        trigger_params=legacy_params,
    )
    assert setups == [], "nonzero arrival_tolerance_ticks in legacy config must be ignored"


def test_arrival_tolerance_param_forced_to_zero_in_normalize():
    """_normalize_3c_params must always return arrival_tolerance_ticks=0.0 regardless
    of what was passed in."""
    from thesistester.engine.signals_3c import _normalize_3c_params

    result = _normalize_3c_params({"arrival_tolerance_ticks": 5.0, "entry_retrace_ticks": 4.0})
    assert result["arrival_tolerance_ticks"] == 0.0


def test_short_arrival_near_miss_does_not_qualify():
    """Short direction: candle high that does not reach the key level must not qualify."""
    setups = detect_3c_setups(
        _df(
            [
                {"open": 99.0, "high": 99.75, "low": 99.0, "close": 99.5},  # near miss
                {"open": 99.4, "high": 99.8, "low": 98.7, "close": 98.9},
                {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
            ]
        ),
        [_candidate(direction="short", price=100.0)],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert setups == [], "short near-miss candle must not qualify as arrival"


def test_short_arrival_exact_touch_qualifies():
    """Short direction: candle high exactly at key level must qualify."""
    setups = detect_3c_setups(
        _df(
            [
                {"open": 99.0, "high": 100.0, "low": 99.0, "close": 99.5},  # exact touch
                {"open": 99.4, "high": 99.8, "low": 98.7, "close": 98.9},
                {"open": 99.0, "high": 99.5, "low": 98.8, "close": 99.1},
            ]
        ),
        [_candidate(direction="short", price=100.0)],
        tick_size=TICK,
        trigger_params={"entry_retrace_ticks": 2, "max_entry_wait_bars_after_reversal": 3},
    )
    assert len(setups) == 1, "exact-touch short candle must qualify as arrival"
    assert setups[0]["status"] == "filled"
