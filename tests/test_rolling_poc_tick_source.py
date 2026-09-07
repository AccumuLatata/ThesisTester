"""RP2 — default rolling POC is tick Last×Volume (desk amendment)."""

from __future__ import annotations

import inspect
import math
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import compute_levels, run_experiment
from thesistester.levels import PRIOR_PROFILE_LEVEL_NAMES, compute_all_levels, compute_profile_levels
from thesistester.levels.apoc import COL_APOC
from thesistester.levels.apoc_tick import (
    APeriodTickProfileTable,
    compute_apoc_tick_source_id,
    empty_a_period_tick_profile_table,
)
from thesistester.levels.rolling_poc_candidates import (
    TICK_LAST_VOLUME_V1,
    compare_rolling_poc_candidates,
)
from thesistester.levels.rolling_poc_tick import (
    ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1,
    attach_rolling_poc_identity,
    compute_rolling_poc_from_ticks,
    compute_rolling_poc_tick_source_id,
    resolve_rolling_poc_profile_source,
)
from thesistester.levels.tick_vap import (
    TICK_SOURCE_NONE,
    build_prior_profile_table_from_paths,
    compute_tick_source_id,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION
from thesistester.research_identity import normalize_levels_config

TZ = "America/New_York"
SESSION = "2026-06-02"
TICK_SIZE = 0.25
WINDOW = "30min"


def _ts(hour: int, minute: int, second: int = 0) -> pd.Timestamp:
    return pd.Timestamp(f"{SESSION} {hour:02d}:{minute:02d}:{second:02d}", tz=TZ)


def _ohlc(price: float, volume: float) -> dict[str, float]:
    return {
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
    }


def _competing_hour_bars() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, ts in enumerate(pd.date_range(_ts(9, 30), _ts(10, 29), freq="1min")):
        price = 100.00 + i * TICK_SIZE
        volume = 1.0
        if ts == _ts(9, 45):
            volume = 100.0
        if ts == _ts(10, 0):
            price = 200.00
            volume = 200.0
        rows.append({"timestamp": ts, **_ohlc(price, volume), "session": "RTH"})
    return pd.DataFrame(rows)


def _window_ticks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [_ts(9, 30, 30), _ts(9, 31), _ts(9, 45), _ts(10, 0, 30), _ts(10, 1)],
            "price": [99.00, 100.25, 103.75, 200.00, 201.00],
            "volume": [9.0, 1.0, 4.0, 2.0, 8.0],
        }
    )


def _write_tick_csv(path: Path, rows: list[tuple[str, float, float]]) -> Path:
    lines = ["Aggressor flag;Price;Volume;Time left;"]
    for stamp, price, volume in rows:
        lines.append(f";{price};{volume};{stamp};")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _window_tick_rows_utc() -> list[tuple[str, float, float]]:
    # 2026-06-02 America/New_York is UTC-4.
    return [
        ("2026-06-02 13:30:30", 99.00, 9.0),
        ("2026-06-02 13:31:00", 100.25, 1.0),
        ("2026-06-02 13:45:00", 103.75, 4.0),
        ("2026-06-02 14:00:30", 200.00, 2.0),
        ("2026-06-02 14:01:00", 201.00, 8.0),
    ]


def _lean_spec(*, bars_name: str, tick_name: str, table_path: str | None = None) -> dict:
    dataset = {
        "path": bars_name,
        "instrument": "ES",
        "source_timezone": TZ,
        "tick_paths": [tick_name],
    }
    if table_path is not None:
        dataset["prior_profile_table_path"] = table_path
    return {
        "name": "rp2-tick-wiring",
        "dataset": dataset,
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["30min"],
            "ema_timeframes": ["30min"],
            "vwap_windows": [],
            "poc_windows": ["30min"],
            "pivots_enabled": False,
            "session_vwap_enabled": False,
            "single_prints_enabled": False,
            "apoc_enabled": False,
            "prev30m_vwap_enabled": False,
        },
        "setup": {
            "name": "rp2-tick-wiring",
            "description": "RP2 tick-source wiring",
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


def test_omitted_and_explicit_tick_are_the_only_production_source():
    assert resolve_rolling_poc_profile_source(None) == TICK_LAST_VOLUME_V1
    assert resolve_rolling_poc_profile_source("") == TICK_LAST_VOLUME_V1
    assert (
        resolve_rolling_poc_profile_source(TICK_LAST_VOLUME_V1)
        == ROLLING_POC_PROFILE_SOURCE_TICK_LAST_VOLUME_V1
    )
    with pytest.raises(ValueError, match="Unsupported rolling_poc_profile_source"):
        resolve_rolling_poc_profile_source("typical_mvp_v1")
    with pytest.raises(ValueError, match="Unsupported rolling_poc_profile_source"):
        compute_profile_levels(
            _competing_hour_bars(),
            instrument="ES",
            rolling_windows=["30min"],
            rolling_poc_profile_source="typical_mvp_v1",
        )
    assert LEVEL_ENGINE_VERSION == 11


def test_no_ticks_emits_all_nan_and_does_not_use_typical():
    bars = _competing_hour_bars()
    out = compute_profile_levels(bars, instrument="ES", rolling_windows=["30min"])
    assert out["POC_rolling_30min"].isna().all()
    from thesistester.levels.profile import _rolling_poc

    work = bars.sort_values("timestamp").reset_index(drop=True)
    typical = _rolling_poc(
        work,
        (work["high"] + work["low"] + work["close"]) / 3.0,
        work["volume"],
        tick_size=TICK_SIZE,
        window="30min",
        value_area_pct=0.70,
    )
    assert typical.iloc[work.index[work["timestamp"] == _ts(10, 0)][0]] == pytest.approx(200.00)
    assert not out["POC_rolling_30min"].equals(typical)


def test_sampled_stamps_match_rp1_harness_tick_poc():
    bars = _competing_hour_bars()
    ticks = _window_ticks()
    engine, _stats = compute_rolling_poc_from_ticks(
        bars.sort_values("timestamp").reset_index(drop=True),
        ticks,
        windows=["30min"],
        tick_size=TICK_SIZE,
    )
    for stamp in (_ts(9, 59), _ts(10, 0)):
        harness = compare_rolling_poc_candidates(
            bars, now=stamp, window=WINDOW, tick_size=TICK_SIZE, ticks=ticks
        )
        row = engine.loc[bars.sort_values("timestamp").reset_index(drop=True)["timestamp"] == stamp]
        assert float(row["POC_rolling_30min"].iloc[0]) == pytest.approx(
            harness.candidates[TICK_LAST_VOLUME_V1].poc
        )
    assert engine.loc[
        bars.sort_values("timestamp").reset_index(drop=True)["timestamp"] == _ts(10, 0),
        "POC_rolling_30min",
    ].iloc[0] == pytest.approx(103.75)


def test_off_grid_tick_in_window_is_nan_not_snap():
    bars = _competing_hour_bars()
    ticks = _window_ticks()
    ticks.loc[ticks["timestamp"] == _ts(9, 45), "price"] = 103.70
    engine, _stats = compute_rolling_poc_from_ticks(
        bars.sort_values("timestamp").reset_index(drop=True),
        ticks,
        windows=["30min"],
        tick_size=TICK_SIZE,
    )
    aligned = bars.sort_values("timestamp").reset_index(drop=True)
    assert math.isnan(
        float(engine.loc[aligned["timestamp"] == _ts(10, 0), "POC_rolling_30min"].iloc[0])
    )


def test_missing_tick_file_is_all_nan_without_exception(tmp_path):
    bars = _competing_hour_bars()
    out = compute_profile_levels(
        bars,
        instrument="ES",
        rolling_windows=["30min", "1h"],
        tick_paths=[tmp_path / "missing.csv"],
    )
    assert out["POC_rolling_30min"].isna().all()
    assert out["POC_rolling_1h"].isna().all()


def test_prior_tables_do_not_substitute_for_rolling_ticks(tmp_path):
    bars = _competing_hour_bars()
    tick_path = _write_tick_csv(tmp_path / "ticks.csv", _window_tick_rows_utc())
    table = build_prior_profile_table_from_paths([tick_path], instrument="ES")
    without = compute_profile_levels(
        bars,
        instrument="ES",
        rolling_windows=["30min"],
        prior_profile_table=table,
    )
    assert without["POC_rolling_30min"].isna().all()
    for name in PRIOR_PROFILE_LEVEL_NAMES:
        assert name in without.columns
    apoc_table = empty_a_period_tick_profile_table()
    assert isinstance(apoc_table, APeriodTickProfileTable)
    still_nan = compute_profile_levels(bars, instrument="ES", rolling_windows=["30min"])
    assert still_nan["POC_rolling_30min"].isna().all()


def test_future_shock_prefix_stable_with_future_bars_and_ticks():
    bars = _competing_hour_bars()
    ticks = _window_ticks()
    aligned = bars.sort_values("timestamp").reset_index(drop=True)
    prefix_n = len(aligned)
    base, _ = compute_rolling_poc_from_ticks(
        aligned, ticks, windows=["30min"], tick_size=TICK_SIZE
    )
    future_bars = pd.concat(
        [
            aligned,
            pd.DataFrame(
                [{"timestamp": _ts(11, 0), **_ohlc(300.0, 50.0), "session": "RTH"}]
            ),
        ],
        ignore_index=True,
    )
    future_ticks = pd.concat(
        [
            ticks,
            pd.DataFrame({"timestamp": [_ts(11, 0, 15)], "price": [300.0], "volume": [80.0]}),
        ],
        ignore_index=True,
    )
    extended, _ = compute_rolling_poc_from_ticks(
        future_bars, future_ticks, windows=["30min"], tick_size=TICK_SIZE
    )
    pd.testing.assert_series_equal(
        base["POC_rolling_30min"],
        extended["POC_rolling_30min"].iloc[:prefix_n],
        check_names=False,
    )


def test_two_pointer_visits_each_tick_at_most_once():
    bars = _competing_hour_bars().sort_values("timestamp").reset_index(drop=True)
    ticks = _window_ticks()
    _levels, stats = compute_rolling_poc_from_ticks(
        bars, ticks, windows=["30min", "1h"], tick_size=TICK_SIZE
    )
    for label, window_stats in stats.items():
        assert window_stats["adds"] <= window_stats["n_ticks"]
        assert window_stats["removes"] <= window_stats["n_ticks"]
        assert window_stats["n_bars"] == len(bars)
        assert label in {"30min", "1h"}


def test_identity_ids_differ_from_va_and_apoc(tmp_path):
    path = _write_tick_csv(tmp_path / "ticks.csv", _window_tick_rows_utc())
    va_id = compute_tick_source_id([path])
    apoc_id = compute_apoc_tick_source_id([path])
    rolling_id = compute_rolling_poc_tick_source_id([path], poc_windows=["30min"])
    assert va_id != TICK_SOURCE_NONE
    assert rolling_id != TICK_SOURCE_NONE
    assert rolling_id != va_id
    assert rolling_id != apoc_id
    implicit = attach_rolling_poc_identity(normalize_levels_config({}, instrument="ES"))
    assert implicit["rolling_poc_algorithm_version"] == TICK_LAST_VOLUME_V1
    assert implicit["rolling_poc_allocation"] == "last_times_volume"
    assert "rolling_poc_tick_source_id" in implicit


def test_unrelated_families_isolated_from_rolling_tick_cutover(tmp_path):
    bars = _competing_hour_bars()
    tick_path = _write_tick_csv(tmp_path / "ticks.csv", _window_tick_rows_utc())
    without = compute_all_levels(
        bars,
        instrument="ES",
        poc_windows=["30min"],
        apoc_enabled=True,
        session_vwap_enabled=True,
    )
    with_ticks = compute_all_levels(
        bars,
        instrument="ES",
        poc_windows=["30min"],
        apoc_enabled=True,
        session_vwap_enabled=True,
        tick_paths=[tick_path],
    )
    assert without["POC_rolling_30min"].isna().all()
    assert with_ticks["POC_rolling_30min"].notna().any()
    pd.testing.assert_series_equal(without["dOpen"], with_ticks["dOpen"])
    pd.testing.assert_series_equal(without[COL_APOC], with_ticks[COL_APOC])
    pd.testing.assert_series_equal(without["dVWAP"], with_ticks["dVWAP"])


def test_run_experiment_forwards_tick_paths_when_va_parquet_present(tmp_path):
    bars = _competing_hour_bars().drop(columns=["session"])
    bars_path = tmp_path / "bars.csv"
    export = bars.copy()
    export["timestamp"] = export["timestamp"].dt.tz_convert(TZ).dt.tz_localize(None)
    export.to_csv(bars_path, index=False)
    tick_path = _write_tick_csv(tmp_path / "ticks.csv", _window_tick_rows_utc())
    table = build_prior_profile_table_from_paths([tick_path], instrument="ES")
    table_path = tmp_path / "prior_va.parquet"
    table.to_parquet(table_path)
    spec = _lean_spec(
        bars_name="bars.csv",
        tick_name=str(tick_path),
        table_path=str(table_path),
    )
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    rolling = state["levels"]["POC_rolling_30min"]
    assert rolling.notna().any()
    settings = state["levels_settings"]
    assert settings["rolling_poc_tick_source_id"] != TICK_SOURCE_NONE
    assert settings["rolling_poc_tick_source_id"] != settings["tick_source_id"]
    assert settings["rolling_poc_tick_source_id"] != compute_apoc_tick_source_id([tick_path])


def test_study_schema_accepts_tick_token_and_rejects_typical():
    implicit = normalize_levels_config({}, instrument="ES")
    assert "rolling_poc_profile_source" not in implicit
    explicit = normalize_levels_config(
        {"rolling_poc_profile_source": TICK_LAST_VOLUME_V1}, instrument="ES"
    )
    assert explicit["rolling_poc_profile_source"] == TICK_LAST_VOLUME_V1


def test_rolling_poc_body_untouched_and_not_called_from_tick_module():
    from thesistester.levels import profile as profile_mod
    from thesistester.levels import rolling_poc_tick as tick_mod

    src = inspect.getsource(profile_mod._rolling_poc)
    assert "in_window = (timestamps > start) & (timestamps <= now)" in src
    impl = inspect.getsource(tick_mod.compute_rolling_poc_from_ticks)
    loader = inspect.getsource(tick_mod.compute_rolling_poc_tick_levels)
    assert "compute_tick_last_volume_profile" not in impl
    assert "compute_tick_last_volume_profile" not in loader
    assert "select_a_period_rows" not in impl
    assert "select_a_period_rows" not in loader
    assert "PriorProfileTable" not in loader
    assert LEVEL_ENGINE_VERSION == 11


def test_compute_levels_default_is_tick_identity_not_typical():
    bars = _competing_hour_bars()
    result = compute_levels(bars, instrument="ES", config={"poc_windows": ["30min"]})
    settings = result["levels_settings"]
    assert settings["rolling_poc_algorithm_version"] == TICK_LAST_VOLUME_V1
    assert settings["rolling_poc_tick_source_id"] == TICK_SOURCE_NONE
    assert result["levels"]["POC_rolling_30min"].isna().all()
    assert "apoc_profile_source" not in settings
