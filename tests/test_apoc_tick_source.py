"""AP2 — versioned ``tick_last_volume_v1`` APOC source.

Covers source identity, fail-to-NaN, A-period tick filtering, pAPOC
propagation, PIT, unrelated-family isolation, and the reference fixture
gate. Bar-range proxies are not production sources.
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from thesistester.levels import compute_all_levels, compute_apoc_levels
from thesistester.levels.apoc import COL_APOC, COL_PAPOC
from thesistester.levels.apoc_candidates import (
    TICK_LAST_VOLUME_V1,
    TYPICAL_MVP_V1,
    compute_tick_last_volume_profile,
    select_a_period_rows,
)
from thesistester.levels.apoc_tick import (
    APOC_ALLOCATION_LAST_TIMES_VOLUME,
    APOC_A_PERIOD_POLICY_ID,
    APeriodTickProfileTable,
    attach_apoc_identity,
    build_a_period_tick_profile_table,
    compute_apoc_tick_source_id,
)
from thesistester.levels.tick_vap import (
    TICK_SOURCE_NONE,
    build_prior_profile_table_from_paths,
    compute_tick_source_id,
)
from thesistester.api import compute_levels, run_experiment
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, compute_levels_settings_hash
from thesistester.research_identity import DataIdentity, LevelsIdentity, normalize_levels_config
from thesistester.levels.tpo import SINGLE_PRINT_COLUMNS

TZ = "America/New_York"
FIXTURE_TICKS = Path(__file__).parent / "fixtures" / "apoc" / "synthetic_a_period_ticks.csv"
FIXTURE_EXPECTED = Path(__file__).parent / "fixtures" / "apoc" / "synthetic_a_period_expected.csv"
ORACLE_TICKS_ENV = "THESISTESTER_APOC_QT_TICKS"
ORACLE_EXPECTED_ENV = "THESISTESTER_APOC_QT_TICK_EXPECTED"


def _rth_bar(ts: pd.Timestamp, high: float, low: float, close: float, volume: float = 10.0) -> dict:
    return {
        "timestamp": ts,
        "open": (high + low) / 2.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session": "RTH",
    }


def _rth_ts(session_date: str, h: int, m: int) -> pd.Timestamp:
    return pd.Timestamp(f"{session_date} {h:02d}:{m:02d}:00", tz=TZ)


def _two_session_bars() -> pd.DataFrame:
    rows = [
        _rth_bar(_rth_ts("2026-06-02", 9, 30), 100.50, 99.50, 100.00, 100),
        _rth_bar(_rth_ts("2026-06-02", 9, 45), 101.00, 100.50, 100.75, 200),
        _rth_bar(_rth_ts("2026-06-02", 10, 0), 101.00, 100.00, 100.50, 50),
        _rth_bar(_rth_ts("2026-06-02", 10, 30), 101.25, 100.75, 101.00, 40),
        _rth_bar(_rth_ts("2026-06-03", 9, 30), 105.00, 104.00, 104.50, 50),
        _rth_bar(_rth_ts("2026-06-03", 9, 45), 106.00, 105.00, 105.50, 80),
        _rth_bar(_rth_ts("2026-06-03", 10, 0), 106.00, 105.00, 105.50, 30),
        _rth_bar(_rth_ts("2026-06-03", 10, 30), 106.50, 106.00, 106.25, 30),
    ]
    return pd.DataFrame(rows)


def _write_tick_csv(path: Path, rows: list[tuple[str, float, float]]) -> Path:
    lines = ["Aggressor flag;Price;Volume;Time left;"]
    for stamp, price, volume in rows:
        lines.append(f";{price};{volume};{stamp};")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _load_expected(path: Path) -> dict[date, float]:
    frame = pd.read_csv(path)
    out: dict[date, float] = {}
    for row in frame.itertuples(index=False):
        out[pd.Timestamp(row.session_date).date()] = float(row.apoc)
    return out


def _assert_session_poc(
    result: pd.DataFrame,
    bars: pd.DataFrame,
    session: date,
    expected: float,
) -> None:
    aligned = bars.sort_values("timestamp").reset_index(drop=True)
    local = aligned["timestamp"].dt.tz_convert(TZ)
    after_a = (local.dt.date == session) & (local.dt.strftime("%H:%M") >= "10:00")
    values = result.loc[after_a.to_numpy(), COL_APOC]
    assert not values.empty
    assert values.notna().all()
    assert values.iloc[0] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# Source contract
# ---------------------------------------------------------------------------


def test_library_default_source_matches_explicit_tick():
    df = _two_session_bars()
    implicit = compute_apoc_levels(
        df, instrument="ES", enabled=True, tick_paths=[FIXTURE_TICKS]
    )
    explicit = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    pd.testing.assert_frame_equal(implicit, explicit)
    _assert_session_poc(implicit, df, date(2026, 6, 2), 100.25)


def test_library_default_without_ticks_refuses():
    df = _two_session_bars()
    with pytest.raises(ValueError, match="APOC requires ticks"):
        compute_apoc_levels(df, instrument="ES", enabled=True)
    explicit_typical = compute_apoc_levels(
        df, instrument="ES", enabled=True, apoc_profile_source=TYPICAL_MVP_V1
    )
    assert COL_APOC in explicit_typical.columns


def test_apoc_profile_source_is_keyword_only():
    df = _two_session_bars()
    with pytest.raises(TypeError):
        compute_apoc_levels(df, "ES", True, TYPICAL_MVP_V1)  # type: ignore[misc]


def test_disabled_ignores_tick_source_and_missing_paths():
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2026-06-02 09:30:00"])})
    out = compute_apoc_levels(
        df,
        instrument="UNSUPPORTED",
        enabled=False,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=["/no/such/ticks.csv"],
    )
    assert out.empty
    assert list(out.columns) == []


def test_unknown_source_raises_when_enabled():
    df = _two_session_bars()
    with pytest.raises(ValueError, match="Unsupported apoc_profile_source"):
        compute_apoc_levels(
            df, instrument="ES", enabled=True, apoc_profile_source="bar_range_uniform_volume_v1"
        )


def test_level_engine_version_unchanged_for_opt_in_source():
    assert LEVEL_ENGINE_VERSION == 11


# ---------------------------------------------------------------------------
# Tick table / AP1 math reuse
# ---------------------------------------------------------------------------


def test_tick_source_matches_ap1_histogram_on_synthetic_fixture():
    table = build_a_period_tick_profile_table([FIXTURE_TICKS], instrument="ES")
    ticks = pd.read_csv(FIXTURE_TICKS, sep=";")
    ticks = ticks.rename(columns={"Price": "price", "Volume": "volume", "Time left": "timestamp"})
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True)
    selected = select_a_period_rows(
        ticks, session_date=date(2026, 6, 2), exchange_tz=TZ, rth_start="09:30"
    )
    candidate = compute_tick_last_volume_profile(selected, tick_size=0.25)
    assert table.poc_for(date(2026, 6, 2)) == pytest.approx(candidate.poc)
    assert table.poc_for(date(2026, 6, 2)) == pytest.approx(100.25)
    assert table.poc_for(date(2026, 6, 3)) == pytest.approx(200.25)


def test_a_period_filter_excludes_eth_and_post_window_prints():
    table = build_a_period_tick_profile_table([FIXTURE_TICKS], instrument="ES")
    assert table.n_ticks_by_session[date(2026, 6, 2)] == 3
    assert table.n_ticks_by_session[date(2026, 6, 3)] == 2


def test_tick_source_emits_apoc_and_papoc_from_a_period_table():
    df = _two_session_bars()
    result = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    typical = compute_apoc_levels(df, instrument="ES", enabled=True)
    _assert_session_poc(result, df, date(2026, 6, 2), 100.25)
    _assert_session_poc(result, df, date(2026, 6, 3), 200.25)

    s2 = df.sort_values("timestamp").reset_index(drop=True)
    s2_mask = s2["timestamp"].dt.tz_convert(TZ).dt.date == date(2026, 6, 3)
    assert result.loc[s2_mask.to_numpy(), COL_PAPOC].iloc[0] == pytest.approx(100.25)

    s1_after = (s2["timestamp"].dt.tz_convert(TZ).dt.date == date(2026, 6, 2)) & (
        s2["timestamp"].dt.tz_convert(TZ).dt.strftime("%H:%M") >= "10:00"
    )
    assert result.loc[s1_after.to_numpy(), COL_APOC].iloc[0] != pytest.approx(
        typical.loc[s1_after.to_numpy(), COL_APOC].iloc[0]
    )


def test_missing_tick_paths_emit_nan_without_typical_fallback():
    df = _two_session_bars()
    typical = compute_apoc_levels(df, instrument="ES", enabled=True)
    missing = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=None,
    )
    assert missing[COL_APOC].isna().all()
    assert missing[COL_PAPOC].isna().all()
    assert typical[COL_APOC].notna().any()


def test_malformed_tick_file_emits_nan(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("not;a;tick;file\n", encoding="utf-8")
    df = _two_session_bars()
    result = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[bad],
    )
    assert result[COL_APOC].isna().all()
    assert result[COL_PAPOC].isna().all()


def test_off_grid_tick_last_fails_closed_to_nan(tmp_path):
    path = _write_tick_csv(
        tmp_path / "offgrid.csv",
        [("2026-06-02 13:30:00.000", 100.10, 4.0)],
    )
    df = _two_session_bars()
    result = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[path],
    )
    s1_after = df.sort_values("timestamp").reset_index(drop=True)
    after = (s1_after["timestamp"].dt.tz_convert(TZ).dt.date == date(2026, 6, 2)) & (
        s1_after["timestamp"].dt.tz_convert(TZ).dt.strftime("%H:%M") >= "10:00"
    )
    assert result.loc[after.to_numpy(), COL_APOC].isna().all()


def test_prior_profile_table_is_not_an_apoc_substitute():
    df = _two_session_bars()
    va_table = build_prior_profile_table_from_paths([FIXTURE_TICKS], instrument="ES")
    tick = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    without_va = compute_all_levels(
        df,
        instrument="ES",
        apoc_enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    with_va = compute_all_levels(
        df,
        instrument="ES",
        apoc_enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
        prior_profile_table=va_table,
    )
    pd.testing.assert_series_equal(
        without_va[COL_APOC].reset_index(drop=True),
        with_va[COL_APOC].reset_index(drop=True),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        tick[COL_APOC].reset_index(drop=True),
        with_va[COL_APOC].reset_index(drop=True),
        check_names=False,
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_settings_identity_includes_source_algorithm_allocation_and_tick_id():
    implicit = attach_apoc_identity(normalize_levels_config({}, instrument="ES"))
    typical = attach_apoc_identity(
        normalize_levels_config({"apoc_profile_source": TYPICAL_MVP_V1}, instrument="ES")
    )
    tick = attach_apoc_identity(
        normalize_levels_config({"apoc_profile_source": TICK_LAST_VOLUME_V1}, instrument="ES"),
        tick_paths=[FIXTURE_TICKS],
    )
    assert "apoc_profile_source" not in implicit
    assert implicit["apoc_algorithm_version"] == TICK_LAST_VOLUME_V1
    assert implicit["apoc_allocation"] == APOC_ALLOCATION_LAST_TIMES_VOLUME
    assert implicit["apoc_tick_source_id"] == TICK_SOURCE_NONE
    assert typical["apoc_profile_source"] == TYPICAL_MVP_V1
    assert typical["apoc_algorithm_version"] == TYPICAL_MVP_V1
    assert typical["apoc_allocation"] == "typical_hlc3_full_volume"
    assert typical["apoc_tick_source_id"] == TICK_SOURCE_NONE
    assert tick["apoc_algorithm_version"] == TICK_LAST_VOLUME_V1
    assert tick["apoc_allocation"] == APOC_ALLOCATION_LAST_TIMES_VOLUME
    assert tick["apoc_tick_source_id"] != TICK_SOURCE_NONE
    assert tick["apoc_tick_source_id"] != compute_tick_source_id([FIXTURE_TICKS])
    assert APOC_A_PERIOD_POLICY_ID
    assert compute_levels_settings_hash(implicit) != compute_levels_settings_hash(typical)
    assert compute_levels_settings_hash(typical) != compute_levels_settings_hash(tick)
    pre_cutover = normalize_levels_config({}, instrument="ES")
    assert "apoc_algorithm_version" not in pre_cutover
    assert compute_levels_settings_hash(pre_cutover) != compute_levels_settings_hash(implicit)


def test_apoc_tick_source_id_is_not_va_table_id():
    va_id = compute_tick_source_id([FIXTURE_TICKS])
    apoc_id = compute_apoc_tick_source_id([FIXTURE_TICKS])
    assert va_id != TICK_SOURCE_NONE
    assert apoc_id != va_id
    assert apoc_id != TICK_SOURCE_NONE


# ---------------------------------------------------------------------------
# PIT + isolation
# ---------------------------------------------------------------------------


def test_tick_source_future_shock_does_not_change_prior_apoc():
    df = _two_session_bars()
    base = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    extra = pd.DataFrame([_rth_bar(_rth_ts("2026-06-04", 9, 30), 300.0, 200.0, 250.0, 9999)])
    extended_bars = pd.concat([df, extra], ignore_index=True)
    extended = compute_apoc_levels(
        extended_bars,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        tick_paths=[FIXTURE_TICKS],
    )
    orig_len = len(df)
    for i in range(orig_len):
        for col in (COL_APOC, COL_PAPOC):
            orig = base[col].iloc[i]
            new = extended[col].iloc[i]
            if math.isnan(orig):
                assert math.isnan(new)
            else:
                assert orig == pytest.approx(new, abs=1e-9)


def test_tick_source_does_not_change_unrelated_level_families():
    df = _two_session_bars()
    va_table = build_prior_profile_table_from_paths([FIXTURE_TICKS], instrument="ES")
    kwargs = dict(
        instrument="ES",
        sma_lengths=[3],
        ema_lengths=[3],
        vwap_windows=["15min"],
        poc_windows=["30min"],
        session_vwap_enabled=True,
        single_prints_enabled=True,
        prev30m_vwap_enabled=True,
        prior_profile_table=va_table,
        apoc_enabled=True,
        tick_paths=[FIXTURE_TICKS],
    )
    typical = compute_all_levels(df, apoc_profile_source=TYPICAL_MVP_V1, **kwargs)
    tick = compute_all_levels(df, apoc_profile_source=TICK_LAST_VOLUME_V1, **kwargs)
    shared = [
        col for col in typical.columns if col in tick.columns and col not in {COL_APOC, COL_PAPOC}
    ]
    assert "APOC" in typical.columns
    assert any(col.startswith("pd") for col in typical.columns)
    for col in shared:
        pd.testing.assert_series_equal(
            typical[col].reset_index(drop=True),
            tick[col].reset_index(drop=True),
            check_names=False,
            obj=f"Column {col!r} changed when APOC source switched",
        )
    for col in SINGLE_PRINT_COLUMNS:
        if col in typical.columns:
            pd.testing.assert_series_equal(
                typical[col].reset_index(drop=True),
                tick[col].reset_index(drop=True),
                check_names=False,
            )


# ---------------------------------------------------------------------------
# Reference fixture gate
# ---------------------------------------------------------------------------


def _assert_tick_oracle(tick_paths: list[Path], expected_path: Path, *, instrument: str) -> None:
    expected = _load_expected(expected_path)
    assert expected, "oracle expected table is empty"
    table = build_a_period_tick_profile_table(tick_paths, instrument=instrument)
    for session, poc in expected.items():
        got = table.poc_for(session)
        assert math.isfinite(got), f"{session}: tick source produced NaN"
        error_ticks = (got - poc) / 0.25
        assert abs(error_ticks) <= 0.0 + 1e-9, (
            f"{session}: POC={got:.2f} expected={poc:.2f} error_ticks={error_ticks:.2f}"
        )


def test_reference_fixture_gate_synthetic_ticks_are_exact():
    _assert_tick_oracle([FIXTURE_TICKS], FIXTURE_EXPECTED, instrument="ES")


@pytest.mark.skipif(
    not os.environ.get(ORACLE_TICKS_ENV) or not os.environ.get(ORACLE_EXPECTED_ENV),
    reason=(
        f"Set {ORACLE_TICKS_ENV} and {ORACLE_EXPECTED_ENV} for the desk "
        "Quantower Tick–Tick–Last A-period oracle (not committed)."
    ),
)
def test_optional_desk_tick_oracle_is_exact():
    """Env-gated Levels2test scorecard. Proprietary CSVs stay outside git."""
    ticks = Path(os.environ[ORACLE_TICKS_ENV])
    paths = sorted(ticks.glob("*.csv")) if ticks.is_dir() else [ticks]
    _assert_tick_oracle(paths, Path(os.environ[ORACLE_EXPECTED_ENV]), instrument="MNQ")


def test_prebuilt_table_is_used_when_provided():
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 123.25, date(2026, 6, 3): 124.50},
        n_ticks_by_session={date(2026, 6, 2): 1, date(2026, 6, 3): 1},
        source_id="synthetic",
    )
    df = _two_session_bars()
    result = compute_apoc_levels(
        df,
        instrument="ES",
        enabled=True,
        apoc_profile_source=TICK_LAST_VOLUME_V1,
        apoc_tick_table=table,
        tick_paths=None,
    )
    _assert_session_poc(result, df, date(2026, 6, 2), 123.25)
    _assert_session_poc(result, df, date(2026, 6, 3), 124.50)


def test_poc_for_accepts_datetime_without_missing_the_date_key():
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25},
        n_ticks_by_session={date(2026, 6, 2): 3},
        source_id="synthetic",
    )
    assert table.poc_for(datetime(2026, 6, 2, 10, 0, 0)) == pytest.approx(100.25)


def test_apoc_tick_source_id_treats_bare_path_as_one_file():
    listed = compute_apoc_tick_source_id([FIXTURE_TICKS])
    bare = compute_apoc_tick_source_id(FIXTURE_TICKS)
    as_str = compute_apoc_tick_source_id(str(FIXTURE_TICKS))
    assert listed == bare == as_str
    assert listed != TICK_SOURCE_NONE


def _write_two_session_bars_csv(path: Path) -> None:
    frame = _two_session_bars().drop(columns=["session"])
    frame["timestamp"] = frame["timestamp"].dt.tz_convert(TZ).dt.tz_localize(None)
    frame.to_csv(path, index=False)


def _lean_tick_apoc_spec(*, bars_name: str, tick_name: str, table_path: str | None = None) -> dict:
    dataset = {
        "path": bars_name,
        "instrument": "ES",
        "source_timezone": TZ,
        "tick_paths": [tick_name],
    }
    if table_path is not None:
        dataset["prior_profile_table_path"] = table_path
    return {
        "name": "apoc-tick-wiring",
        "dataset": dataset,
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["30min"],
            "ema_timeframes": ["30min"],
            "vwap_windows": [],
            "poc_windows": [],
            "pivots_enabled": False,
            "session_vwap_enabled": False,
            "single_prints_enabled": False,
            "apoc_enabled": True,
            "apoc_profile_source": TICK_LAST_VOLUME_V1,
            "prev30m_vwap_enabled": False,
        },
        "setup": {
            "name": "apoc-tick-wiring",
            "description": "AP2 tick-source wiring",
            "instrument": "ES",
            "selected_levels": ["dOpen", "RTH_Open"],
            "tolerance_ticks": 0,
            "min_confluences": 2,
            "max_confluences": 2,
            "naked_only": False,
            "naked_requirement": "any",
            "trigger": "touch",
            "trigger_timeframe": "base",
            "direction": "both",
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": {},
            "otf_filter": None,
        },
        "backtest": {
            "stop_loss_ticks": 2,
            "take_profit_ticks": 3,
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
            "exposure_policy": "single_position",
            "intrabar_model": "sl_first",
        },
    }


def test_compute_levels_tick_source_uses_tick_paths():
    df = _two_session_bars()
    result = compute_levels(
        df,
        instrument="ES",
        config={
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["30min"],
            "ema_timeframes": ["30min"],
            "vwap_windows": [],
            "poc_windows": [],
            "pivots_enabled": False,
            "session_vwap_enabled": False,
            "single_prints_enabled": False,
            "apoc_enabled": True,
            "apoc_profile_source": TICK_LAST_VOLUME_V1,
            "prev30m_vwap_enabled": False,
        },
        tick_paths=[FIXTURE_TICKS],
    )
    _assert_session_poc(result["levels"], df, date(2026, 6, 2), 100.25)
    assert result["levels_settings"]["apoc_tick_source_id"] != TICK_SOURCE_NONE
    assert result["levels_settings"]["apoc_tick_source_id"] == compute_apoc_tick_source_id(
        [FIXTURE_TICKS]
    )


def test_run_experiment_forwards_tick_paths_to_apoc_source(tmp_path):
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_tick_apoc_spec(bars_name="bars.csv", tick_name=str(FIXTURE_TICKS))
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_session_poc(state["levels"], state["data"], date(2026, 6, 2), 100.25)
    _assert_session_poc(state["levels"], state["data"], date(2026, 6, 3), 200.25)
    assert state["levels_settings"]["apoc_tick_source_id"] == compute_apoc_tick_source_id(
        [FIXTURE_TICKS]
    )


def test_run_experiment_keeps_tick_paths_when_prior_va_table_is_present(tmp_path):
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    va_table = build_prior_profile_table_from_paths([FIXTURE_TICKS], instrument="ES")
    table_path = tmp_path / "prior_va.parquet"
    va_table.to_parquet(table_path)
    spec = _lean_tick_apoc_spec(
        bars_name="bars.csv",
        tick_name=str(FIXTURE_TICKS),
        table_path=str(table_path),
    )
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_session_poc(state["levels"], state["data"], date(2026, 6, 2), 100.25)
    assert state["levels_settings"]["apoc_tick_source_id"] != TICK_SOURCE_NONE
    assert state["levels_settings"]["tick_source_id"] != TICK_SOURCE_NONE
    assert (
        state["levels_settings"]["apoc_tick_source_id"]
        != state["levels_settings"]["tick_source_id"]
    )


def test_run_spec_identity_matches_compute_levels_tick_source_hash():
    df = _two_session_bars()
    config = {
        "apoc_profile_source": TICK_LAST_VOLUME_V1,
        "poc_windows": [],
        "sma_lengths": [2],
        "ema_lengths": [2],
        "sma_timeframes": ["30min"],
        "ema_timeframes": ["30min"],
        "vwap_windows": [],
        "pivots_enabled": False,
        "session_vwap_enabled": False,
        "single_prints_enabled": False,
        "prev30m_vwap_enabled": False,
    }
    computed = compute_levels(
        df,
        instrument="ES",
        config=config,
        tick_paths=[FIXTURE_TICKS],
    )
    identity = DataIdentity.from_loaded_data(
        df,
        instrument="ES",
        base_interval="1min",
        source_timezone=TZ,
        exchange_timezone=TZ,
    )
    spec_identity = LevelsIdentity.from_run_spec(
        identity,
        {
            "levels": config,
            "dataset": {"tick_paths": [str(FIXTURE_TICKS)]},
        },
    )
    assert spec_identity.levels_settings_hash == compute_levels_settings_hash(
        computed["levels_settings"]
    )


def test_page_state_identity_includes_tick_paths_for_tick_source():
    df = _two_session_bars()
    page = LevelsIdentity.from_page_state(
        {
            "data": df,
            "instrument": "ES",
            "base_interval": "1min",
            "source_timezone": TZ,
            "exchange_timezone": TZ,
            "tick_paths": [str(FIXTURE_TICKS)],
            "levels_settings": {"apoc_profile_source": TICK_LAST_VOLUME_V1},
        }
    )
    api = LevelsIdentity.from_config(
        DataIdentity.from_loaded_data(
            df,
            instrument="ES",
            base_interval="1min",
            source_timezone=TZ,
            exchange_timezone=TZ,
        ),
        {"apoc_profile_source": TICK_LAST_VOLUME_V1},
        tick_paths=[FIXTURE_TICKS],
    )
    assert page.levels_settings_hash == api.levels_settings_hash
    assert page.levels_settings is not None
    assert page.levels_settings["apoc_tick_source_id"] != TICK_SOURCE_NONE


def test_compute_levels_default_apoc_without_ticks_refuses():
    df = _two_session_bars()
    with pytest.raises(ValueError, match="APOC requires ticks"):
        compute_levels(
            df,
            instrument="ES",
            config={"poc_windows": [], "apoc_enabled": True},
        )


def test_run_experiment_named_apoc_without_ticks_refuses(tmp_path):
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_tick_apoc_spec(bars_name="bars.csv", tick_name="unused.csv")
    spec["dataset"].pop("tick_paths")
    spec["setup"]["selected_levels"] = ["APOC", "dOpen"]
    with pytest.raises(ValueError, match="APOC requires ticks"):
        run_experiment(spec, base_directory=tmp_path, cache_policy="off")


def test_run_experiment_15s_only_onh_still_runs(tmp_path):
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_tick_apoc_spec(bars_name="bars.csv", tick_name="unused.csv")
    spec["dataset"].pop("tick_paths")
    spec["levels"]["apoc_enabled"] = True
    spec["setup"]["selected_levels"] = ["dOpen", "RTH_Open"]
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    assert "APOC" not in state["levels"].columns
    assert "POC_rolling_30min" not in state["levels"].columns
    assert "dOpen" in state["levels"].columns
