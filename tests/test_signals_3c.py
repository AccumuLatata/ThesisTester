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


def _candidate(direction: str = "long", price: float = 100.0, source_mode: str = "global_cluster") -> CandidateLevel:
    return CandidateLevel(
        source_mode=source_mode,
        zone_id="zone_0",
        level_id="L1",
        level_price=price,
        zone_low=price,
        zone_high=price,
        direction=direction,
        source_label="L1",
        bar_index=0,
        timestamp=pd.Timestamp("2026-01-02 09:30:00", tz=TZ),
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
    assert void_setup[0]["entry_bar_index"] is None

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
