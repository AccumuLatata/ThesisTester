"""TS5 named parity test (§5.1) plus stitch-on wiring gates.

CI merge gate is (a)(b)(c). ``HOOK_POINTS`` only checks symbol existence.
Stitch-absent behaviour is pinned to ``0ebc1494``.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thesistester.api import (
    compute_levels,
    run_experiment,
    validate_run_spec,
)
from thesistester.levels.apoc import COL_APOC, COL_PAPOC
from thesistester.levels.apoc_tick import (
    APeriodTickProfileTable,
    attach_apoc_identity,
    compute_apoc_tick_source_id,
)
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.rolling_poc_tick import attach_rolling_poc_identity
from thesistester.levels.tick_vap import (
    TICK_SOURCE_NONE,
    attach_tick_identity,
    compute_tick_source_id,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, compute_levels_settings_hash
from thesistester.research_identity import normalize_levels_config
from thesistester.study.execute import (
    _prepare_study_tick_stitch,
    execute_study_cell,
    run_study,
)
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)
from thesistester.study.expand import expand_study

FIXTURE_TICKS = Path(__file__).parent / "fixtures" / "apoc" / "synthetic_a_period_ticks.csv"
STITCH_DIR = Path(__file__).parent / "fixtures" / "tick_stitch"
TZ = "America/New_York"

# Pinned from this tree (bit-identical to 0ebc1494 stitch-absent compute_levels).
_PINNED_TICK_SOURCE_ID = "05994e364ac2b6152a9b2606027b0cf3c24791394f957ef1b9a748a9e831d611"
_PINNED_APOC_TICK_SOURCE_ID = "703023847a0bbcc6353af6d13e00f02c9e72eaefcafefb847da3088fbc237138"
_PINNED_SETTINGS_HASH = "a3723e23f249c4e75566def45ff454c42e634663aa49bb87a662f57dfbadd816"
_0EBC1494_COMPUTE_LEVELS_KWARGS = frozenset(
    {
        "instrument",
        "config",
        "cache_policy",
        "data_identity",
        "store_root",
        "tick_paths",
        "tick_format_profile",
        "prior_profile_table",
        "prior_profile_table_path",
        "tick_source_id",
    }
)
_ALWAYS_ON_IDENTITY_KEYS = frozenset(
    {
        "tick_source_id",
        "va_source",
        "apoc_algorithm_version",
        "apoc_allocation",
        "apoc_tick_source_id",
        "rolling_poc_algorithm_version",
        "rolling_poc_allocation",
        "rolling_poc_tick_source_id",
    }
)
_LEAN_LEVELS = {
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
    "prev30m_vwap_enabled": False,
}


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


def _write_two_session_bars_csv(path: Path) -> Path:
    _two_session_bars().to_csv(path, index=False)
    return path


def _lean_run_spec(
    *,
    bars_name: str,
    tick_name: str | None = None,
    extra_dataset: dict | None = None,
    selected_levels: list[str] | None = None,
) -> dict:
    dataset: dict = {
        "path": bars_name,
        "instrument": "ES",
        "source_timezone": TZ,
        "exchange_timezone": TZ,
    }
    if tick_name is not None:
        dataset["tick_paths"] = [tick_name]
    if extra_dataset:
        dataset.update(extra_dataset)
    return {
        "name": "ts5-parity",
        "dataset": dataset,
        "levels": dict(_LEAN_LEVELS),
        "setup": {
            "name": "ts5-parity",
            "description": "TS5 stitch-absent parity",
            "instrument": "ES",
            "selected_levels": selected_levels or ["dOpen", "RTH_Open"],
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


def _minimal_study(**dataset_extra) -> dict:
    dataset = {"path": "data/es_1m.csv", "instrument": "ES"}
    dataset.update(dataset_extra)
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": "ts5_stitch",
            "output_dir": "results/studies/ts5_stitch",
            "workers": 1,
            "confirm_above_runs": 200,
            "dataset": dataset,
            "levels": {
                "sma_lengths": [50, 200],
                "ema_lengths": [21],
                "sma_timeframes": ["1min", "5min", "30min"],
                "ema_timeframes": ["1min", "5min", "30min"],
            },
            "constants": {
                "direction": "both",
                "tolerance_ticks": 0,
                "min_confluences": 2,
                "max_confluences": 2,
                "min_valid_confluences": 1,
                "naked_only": False,
                "naked_requirement": "any",
                "trigger_params": {},
                "backtest": {
                    "stop_loss_ticks": 8,
                    "take_profit_ticks": 16,
                    "exposure_policy": "single_position",
                },
                "grid": {"enabled": False},
                "validation": {"enabled": False},
                "walk_forward": {"enabled": False},
            },
            "factors": {
                "core_level": ["ONH"],
                "partner_levels": [["SMA_50_1min"], ["EMA_21_5min"]],
                "confluence_mode": ["global_cluster", "anchor_rules"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
                "anchor_rules": {
                    "selected_levels": [],
                    "anchor_level": "${core_level}",
                    "confluence_rules": {"from_partners": "required"},
                },
            },
            "report": {
                "primary_metric": "expectancy_r",
                "secondary_metrics": ["profit_factor", "trade_count"],
                "min_trades": 30,
                "group_by": ["partner_levels", "confluence_mode"],
                "otf_baseline": {"enabled": False},
                "multiple_testing": "warn",
            },
        },
    }


def _write_tick_csv(path: Path, rows: list[tuple[str, float, float]]) -> Path:
    lines = ["Aggressor flag;Price;Volume;Time left;"]
    for stamp, price, volume in rows:
        lines.append(f";{price};{volume};{stamp};")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _plan_for(path: Path, rows: list[tuple[str, float, float]]) -> list[dict]:
    stamps = [row[0] for row in rows]
    return [
        {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "effective_first_utc": stamps[0],
            "effective_last_utc": stamps[-1],
            "file_first_utc": stamps[0],
            "file_last_utc": stamps[-1],
            "mtime": 0,
        }
    ]


def _canonical_15s(path: Path, stamps: list[str], *, volume: float = 10.0) -> Path:
    rows = []
    for stamp in stamps:
        ts = pd.Timestamp(stamp, tz="UTC")
        rows.append(
            {
                "timestamp": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": volume,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# §5.1 (a)(b)(c)
# ---------------------------------------------------------------------------


def test_stitch_absent_call_sentinels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def _boom(name: str):
        def _inner(*_args, **_kwargs):
            called.append(name)
            raise AssertionError(f"{name} must not run when stitch is absent")

        return _inner

    monkeypatch.setattr(
        "thesistester.data.tick_stitch.verify_tick_stitch_plan", _boom("verify")
    )
    monkeypatch.setattr(
        "thesistester.data.tick_stitch.iter_stitch_sessions", _boom("iter")
    )
    monkeypatch.setattr(
        "thesistester.data.tick_stitch.apply_x1_residual_fill", _boom("x1_fill")
    )
    monkeypatch.setattr(
        "thesistester.data.tick_stitch.guard_hourly_tick_holes", _boom("guard")
    )
    monkeypatch.setattr(
        "thesistester.study.execute._prepare_study_tick_stitch", _boom("parent_prepare")
    )
    monkeypatch.setattr(
        "thesistester.data.tick_stitch.build_stitch_parent_tables", _boom("parent_prepare")
    )

    captured: dict[str, object] = {}
    real = compute_levels

    def _capture(data, **kwargs):
        captured["kwargs"] = dict(kwargs)
        return real(data, **kwargs)

    monkeypatch.setattr("thesistester.api.compute_levels", _capture)
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv", tick_name=str(FIXTURE_TICKS))
    run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    passed = set(captured["kwargs"])
    assert passed == _0EBC1494_COMPUTE_LEVELS_KWARGS
    assert "apoc_tick_table" not in captured["kwargs"]
    assert "apoc_tick_source_id" not in captured["kwargs"]
    assert "apoc_tick_table_path" not in captured["kwargs"]

    params = inspect.signature(real).parameters
    assert list(params)[:11] == [
        "data",
        "instrument",
        "config",
        "cache_policy",
        "data_identity",
        "store_root",
        "tick_paths",
        "tick_format_profile",
        "prior_profile_table",
        "prior_profile_table_path",
        "tick_source_id",
    ]
    assert params["apoc_tick_table"].default is None
    assert params["apoc_tick_source_id"].default is None

    attached = attach_rolling_poc_identity(
        attach_apoc_identity(attach_tick_identity(dict(DEFAULT_LEVELS_SETTINGS))),
    )
    extra = set(attached) - set(DEFAULT_LEVELS_SETTINGS)
    assert extra == _ALWAYS_ON_IDENTITY_KEYS
    hashed = compute_levels_settings_hash(attached)
    assert isinstance(hashed, str) and len(hashed) == 64

    from tests.study.test_study_execute import _fake_executor_factory, _mini_study_yaml

    yaml_path = _mini_study_yaml(tmp_path / "study.yaml")
    (tmp_path / "bars.csv").write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-06-02 09:30:00,100,101,99,100,10\n",
        encoding="utf-8",
    )
    run_study(
        yaml_path,
        output_dir=tmp_path / "out",
        cell_executor=_fake_executor_factory(),
    )
    assert called == []
    assert LEVEL_ENGINE_VERSION == 11


def test_stitch_absent_tick_paths_va_apoc_match_0ebc1494() -> None:
    bars = _two_session_bars()
    result = compute_levels(
        bars, instrument="ES", tick_paths=[FIXTURE_TICKS], config=_LEAN_LEVELS
    )
    levels = result["levels"]
    settings = result["levels_settings"]
    apoc = [None if pd.isna(v) else round(float(v), 8) for v in levels[COL_APOC].tolist()]
    papoc = [None if pd.isna(v) else round(float(v), 8) for v in levels[COL_PAPOC].tolist()]
    assert apoc == [None, None, 100.25, 100.25, None, None, 200.25, 200.25]
    assert papoc == [None, None, None, None, 100.25, 100.25, 100.25, 100.25]
    assert [None if pd.isna(v) else float(v) for v in levels["pdPOC"].tolist()] == [
        None,
        None,
        None,
        None,
        101.0,
        101.0,
        101.0,
        101.0,
    ]
    assert settings["tick_source_id"] == _PINNED_TICK_SOURCE_ID
    assert settings["apoc_tick_source_id"] == _PINNED_APOC_TICK_SOURCE_ID
    assert compute_levels_settings_hash(settings) == _PINNED_SETTINGS_HASH
    assert settings["tick_source_id"] == compute_tick_source_id([FIXTURE_TICKS])
    assert settings["apoc_tick_source_id"] == compute_apoc_tick_source_id([FIXTURE_TICKS])
    assert LEVEL_ENGINE_VERSION == 11


def test_stitch_absent_index_has_no_data_quality_keys(tmp_path: Path) -> None:
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv", tick_name=str(FIXTURE_TICKS))
    payload = execute_study_cell((spec, str(tmp_path)))
    assert payload["status"] == "ok"
    keys = [key for key in payload["index_row"] if str(key).startswith("data_quality.")]
    assert keys == []


def test_stitch_plan_absent_does_not_change_tick_source_id_none(tmp_path: Path) -> None:
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv")
    spec["levels"]["apoc_enabled"] = False
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    assert state["levels_settings"]["tick_source_id"] == TICK_SOURCE_NONE
    assert state["levels_settings"]["apoc_tick_source_id"] == TICK_SOURCE_NONE


# ---------------------------------------------------------------------------
# Schema / run-spec / compute_levels wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("core_level", ["pdPOC", "APOC"])
def test_named_va_apoc_with_stitch_plan_no_tick_paths_validates(core_level: str) -> None:
    raw = _minimal_study(
        tick_stitch_plan="tests/fixtures/tick_stitch/plan.json",
        tick_stitch_x1_burst_included=True,
    )
    raw["study"]["factors"]["core_level"] = [core_level]
    raw["study"]["levels"]["poc_windows"] = []
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == [core_level]


def test_schema_rejects_stitch_plan_without_burst_flag() -> None:
    raw = _minimal_study(tick_stitch_plan="tests/fixtures/tick_stitch/plan.json")
    with pytest.raises(StudySpecError, match="tick_stitch_x1_burst_included"):
        validate_study_spec(normalize_study_spec(raw))


def test_validate_run_spec_accepts_new_dataset_keys_and_rejects_unknown(tmp_path: Path) -> None:
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(
        bars_name="bars.csv",
        extra_dataset={
            "tick_stitch_plan": str(STITCH_DIR / "plan.json"),
            "tick_stitch_x1_burst_included": True,
            "apoc_tick_table_path": str(tmp_path / "apoc.parquet"),
            "apoc_tick_source_id": "abc123",
        },
    )
    spec["levels"]["apoc_enabled"] = False
    assert validate_run_spec(spec) is None
    spec["dataset"]["not_a_dataset_key"] = "nope"
    with pytest.raises(ValueError, match="not_a_dataset_key"):
        validate_run_spec(spec)


def test_compute_levels_forwards_apoc_tick_source_id_without_hashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*_args, **_kwargs):
        raise AssertionError("compute_apoc_tick_source_id must not run")

    monkeypatch.setattr(
        "thesistester.levels.apoc_tick.compute_apoc_tick_source_id", _forbid
    )
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25},
        n_ticks_by_session={date(2026, 6, 2): 3},
        source_id="parent-apoc-id",
    )
    result = compute_levels(
        _two_session_bars(),
        instrument="ES",
        config=_LEAN_LEVELS,
        apoc_tick_table=table,
        apoc_tick_source_id="parent-apoc-id",
    )
    assert result["levels_settings"]["apoc_tick_source_id"] == "parent-apoc-id"


def test_stitch_absent_apoc_still_builds_from_fixture_tick_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"build": 0}
    from thesistester.levels.apoc_tick import build_a_period_tick_profile_table as real_build

    def _wrap(*args, **kwargs):
        calls["build"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr("thesistester.api.build_a_period_tick_profile_table", _wrap)
    result = compute_levels(
        _two_session_bars(),
        instrument="ES",
        tick_paths=[FIXTURE_TICKS],
        config=_LEAN_LEVELS,
    )
    assert calls["build"] == 1
    assert result["levels_settings"]["apoc_tick_source_id"] == _PINNED_APOC_TICK_SOURCE_ID


def test_stitch_present_workers_do_not_hash_or_stream_farm_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thesistester.api import apoc_tick_table_to_parquet
    from thesistester.levels.tick_vap import build_prior_profile_table_from_paths

    va = build_prior_profile_table_from_paths(
        [FIXTURE_TICKS],
        instrument="ES",
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    va_path = tmp_path / "prior.parquet"
    va.to_parquet(va_path)
    apoc = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25, date(2026, 6, 3): 200.25},
        n_ticks_by_session={date(2026, 6, 2): 3, date(2026, 6, 3): 2},
        source_id="injected-apoc",
    )
    apoc_path = tmp_path / "apoc.parquet"
    apoc_tick_table_to_parquet(apoc, apoc_path)
    _write_two_session_bars_csv(tmp_path / "bars.csv")

    def _forbid(name: str):
        def _inner(*_a, **_k):
            raise AssertionError(f"worker must not call {name}")

        return _inner

    monkeypatch.setattr(
        "thesistester.data.quantower_ticks.iter_tick_files", _forbid("iter_tick_files")
    )
    monkeypatch.setattr(
        "thesistester.api.build_a_period_tick_profile_table",
        _forbid("build_a_period_tick_profile_table"),
    )
    monkeypatch.setattr(
        "thesistester.levels.tick_vap.compute_tick_source_id",
        _forbid("compute_tick_source_id"),
    )
    spec = _lean_run_spec(
        bars_name="bars.csv",
        extra_dataset={
            "tick_stitch_plan": str(STITCH_DIR / "plan.json"),
            "tick_stitch_x1_burst_included": True,
            "prior_profile_table_path": str(va_path),
            "apoc_tick_table_path": str(apoc_path),
            "tick_source_id": "injected-va",
            "apoc_tick_source_id": "injected-apoc",
        },
    )
    spec["levels"]["poc_windows"] = []
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    assert state["levels_settings"]["tick_source_id"] == "injected-va"
    assert state["levels_settings"]["apoc_tick_source_id"] == "injected-apoc"
    assert "tick_paths" not in spec["dataset"]


def test_parent_table_uses_study_4_8_10_not_library_defaults(tmp_path: Path) -> None:
    from thesistester.data.tick_stitch import build_stitch_parent_tables

    tick_path = tmp_path / "ticks.csv"
    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    _write_tick_csv(tick_path, rows)
    plan = _plan_for(tick_path, rows)
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-15 10:00:00", tz="UTC")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        }
    )
    built = build_stitch_parent_tables(
        plan,
        tmp_path,
        bars,
        instrument="MNQ",
        tick_stitch_x1_burst_included=True,
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    frame = built.prior_profile_table.frame
    by_family = {
        str(row.family): int(row.aggregation_ticks) for row in frame.itertuples(index=False)
    }
    assert by_family["pd"] == 4
    assert by_family["pw"] == 8
    assert by_family["pm"] == 10
    assert DEFAULT_LEVELS_SETTINGS["prior_day_profile_aggregation_ticks"] == 4


def test_explicit_empty_poc_windows_skips_rolling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"rolling": 0}

    def _count(*_a, **_k):
        called["rolling"] += 1
        raise AssertionError("rolling must not run")

    monkeypatch.setattr(
        "thesistester.levels.rolling_poc_tick.compute_rolling_poc_tick_levels", _count
    )
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25},
        n_ticks_by_session={date(2026, 6, 2): 1},
        source_id="x",
    )
    config = dict(_LEAN_LEVELS)
    config["poc_windows"] = []
    compute_levels(
        _two_session_bars(),
        instrument="ES",
        config=config,
        apoc_tick_table=table,
        apoc_tick_source_id="x",
    )
    assert called["rolling"] == 0


def test_omitting_poc_windows_is_not_the_off_switch() -> None:
    config = dict(_LEAN_LEVELS)
    config.pop("poc_windows", None)
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25},
        n_ticks_by_session={date(2026, 6, 2): 1},
        source_id="x",
    )
    with pytest.raises(ValueError, match="rolling POC requires ticks"):
        compute_levels(
            _two_session_bars(),
            instrument="ES",
            config=config,
            apoc_tick_table=table,
            apoc_tick_source_id="x",
        )


def test_future_shock_later_session_does_not_change_prior_pd_or_apoc(tmp_path: Path) -> None:
    from thesistester.data.tick_stitch import build_stitch_parent_tables

    early_rows = [
        ("2026-06-02 13:30:00.000", 100.0, 4.0),
        ("2026-06-02 13:30:01.000", 101.0, 4.0),
    ]
    mid_rows = [
        ("2026-06-03 13:30:00.000", 200.0, 4.0),
        ("2026-06-03 13:30:01.000", 200.0, 4.0),
    ]
    late_rows = [
        ("2026-06-04 13:30:00.000", 9999.0, 400.0),
        ("2026-06-04 13:30:01.000", 9999.0, 400.0),
    ]
    early = _write_tick_csv(tmp_path / "early.csv", early_rows)
    mid = _write_tick_csv(tmp_path / "mid.csv", mid_rows)
    late = _write_tick_csv(tmp_path / "late.csv", late_rows)
    plan_base = _plan_for(early, early_rows) + _plan_for(mid, mid_rows)
    plan_ext = plan_base + _plan_for(late, late_rows)
    bar_stamps = [
        "2026-06-02 13:30:00",
        "2026-06-03 13:30:00",
        "2026-06-04 13:30:00",
    ]
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(s, tz="UTC") for s in bar_stamps],
            "open": [100.0, 200.0, 9999.0],
            "high": [101.0, 200.0, 9999.0],
            "low": [99.0, 200.0, 9999.0],
            "close": [100.5, 200.0, 9999.0],
            "volume": [10.0, 10.0, 10.0],
        }
    )
    base = build_stitch_parent_tables(
        plan_base,
        tmp_path,
        bars,
        instrument="ES",
        tick_stitch_x1_burst_included=True,
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    ext = build_stitch_parent_tables(
        plan_ext,
        tmp_path,
        bars,
        instrument="ES",
        tick_stitch_x1_burst_included=True,
        value_area_pct=0.70,
        prior_day_aggregation_ticks=4,
        prior_week_aggregation_ticks=8,
        prior_month_aggregation_ticks=10,
    )
    first = date(2026, 6, 2)
    base_apoc = float(base.apoc_tick_table.poc_for(first))
    ext_apoc = float(ext.apoc_tick_table.poc_for(first))
    assert pd.notna(base_apoc) and pd.notna(ext_apoc)
    assert base_apoc == ext_apoc
    base_pd = base.prior_profile_table.frame
    ext_pd = ext.prior_profile_table.frame
    base_row = base_pd.loc[base_pd["family"].astype(str).eq("pd")].iloc[0]
    ext_row = ext_pd.loc[ext_pd["family"].astype(str).eq("pd")].iloc[0]
    assert float(base_row["POC"]) == float(ext_row["POC"])
    assert float(base_row["VAH"]) == float(ext_row["VAH"])
    assert float(base_row["VAL"]) == float(ext_row["VAL"])


def test_parent_prepare_injects_ids_and_strips_tick_paths(tmp_path: Path) -> None:
    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan = {"plan": _plan_for(tick, rows)}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(plan["plan"]), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path=str(tmp_path / "bars.csv"),
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan=str(plan_path),
        tick_stitch_x1_burst_included=True,
        tick_paths=["/mnt/nas-trading/must-not-survive.csv"],
    )
    spec["study"]["levels"]["poc_windows"] = []
    expansion = expand_study(spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        spec, expansion, output_dir=tmp_path / "out", base_directory=tmp_path
    )
    run = expansion.experiment["runs"][0]
    dataset = run["dataset"]
    assert "tick_paths" not in dataset
    assert Path(dataset["prior_profile_table_path"]).is_file()
    assert Path(dataset["apoc_tick_table_path"]).is_file()
    assert dataset["tick_source_id"]
    assert dataset["apoc_tick_source_id"]
    assert dataset["tick_source_id"] != TICK_SOURCE_NONE
    assert run["_tick_stitch_data_quality"]["data_quality.x1_burst_included"] is True


def test_normalized_levels_hash_has_no_new_always_on_keys() -> None:
    settings = normalize_levels_config({"apoc_enabled": True, "poc_windows": []}, instrument="ES")
    attached = attach_rolling_poc_identity(
        attach_apoc_identity(attach_tick_identity(settings, tick_source_id=TICK_SOURCE_NONE))
    )
    assert set(attached) - set(settings) <= _ALWAYS_ON_IDENTITY_KEYS
    assert "tick_stitch_plan" not in attached
    assert "tick_stitch_x1_burst_included" not in attached
