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
    _named_level_tokens_from_setup,
    apoc_tick_table_to_parquet,
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
from thesistester.levels.catalog import named_apoc_tokens
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.rolling_poc_tick import attach_rolling_poc_identity
from thesistester.levels.tick_requirements import disable_unneeded_tick_families
from thesistester.levels.tick_vap import (
    TICK_SOURCE_NONE,
    attach_tick_identity,
    compute_tick_source_id,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, compute_levels_settings_hash
from thesistester.research_identity import normalize_levels_config
from thesistester.study.execute import (
    STUDY_INDEX_KEYS,
    _STITCH_DATA_QUALITY_KEY,
    _coerce_data_quality_flag,
    _finalize_study_index,
    _index_row_from_existing_bundle,
    _load_existing_index_rows,
    _prepare_study_tick_stitch,
    _stitch_quality_by_run_name,
    _write_results_index,
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

    monkeypatch.setattr("thesistester.data.tick_stitch.verify_tick_stitch_plan", _boom("verify"))
    monkeypatch.setattr("thesistester.data.tick_stitch.iter_stitch_sessions", _boom("iter"))
    monkeypatch.setattr("thesistester.data.tick_stitch.apply_x1_residual_fill", _boom("x1_fill"))
    monkeypatch.setattr("thesistester.data.tick_stitch.guard_hourly_tick_holes", _boom("guard"))
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
        "timestamp,open,high,low,close,volume\n2026-06-02 09:30:00,100,101,99,100,10\n",
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
    result = compute_levels(bars, instrument="ES", tick_paths=[FIXTURE_TICKS], config=_LEAN_LEVELS)
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


def test_named_va_prior_profile_table_without_ticks_or_stitch_still_refuses() -> None:
    """Stitch-absent schema named-VA gate stays tick_paths-only (0ebc1494)."""
    raw = _minimal_study(prior_profile_table_path="results/prior.parquet")
    raw["study"]["factors"]["core_level"] = ["pdPOC"]
    with pytest.raises(StudySpecError, match="VA requires ticks"):
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

    monkeypatch.setattr("thesistester.levels.apoc_tick.compute_apoc_tick_source_id", _forbid)
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


def test_parent_prepare_does_not_persist_quality_on_experiment_yaml(tmp_path: Path) -> None:
    """Private task key must not enter experiment.yaml (_RUN_KEYS closed)."""
    import yaml

    from thesistester.study.execute import (
        _STITCH_DATA_QUALITY_KEY,
        _detach_stitch_quality,
        _reattach_stitch_quality,
    )
    from thesistester.study.expand import write_expansion_artifacts

    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(_plan_for(tick, rows)), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path=str(tmp_path / "bars.csv"),
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan=str(plan_path),
        tick_stitch_x1_burst_included=True,
    )
    spec["study"]["levels"]["poc_windows"] = []
    expansion = expand_study(spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        spec, expansion, output_dir=tmp_path / "out", base_directory=tmp_path
    )
    assert expansion.experiment["runs"][0][_STITCH_DATA_QUALITY_KEY]
    held = _detach_stitch_quality(expansion)
    try:
        write_expansion_artifacts(
            tmp_path / "out",
            normalized_spec=spec,
            expansion=expansion,
            source_spec_parent=tmp_path,
        )
    finally:
        _reattach_stitch_quality(expansion, held)
    experiment = yaml.safe_load((tmp_path / "out" / "experiment.yaml").read_text(encoding="utf-8"))
    for run in experiment["runs"]:
        assert _STITCH_DATA_QUALITY_KEY not in run
        validate_run_spec(run)
    assert _STITCH_DATA_QUALITY_KEY in expansion.experiment["runs"][0]


def test_apoc_parquet_roundtrip_accepts_timestamp_session_date(tmp_path: Path) -> None:
    from thesistester.api import apoc_tick_table_from_parquet, apoc_tick_table_to_parquet

    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25},
        n_ticks_by_session={date(2026, 6, 2): 3},
        source_id="roundtrip",
    )
    path = tmp_path / "apoc.parquet"
    apoc_tick_table_to_parquet(table, path)
    loaded = apoc_tick_table_from_parquet(path)
    assert loaded.poc_for(date(2026, 6, 2)) == 100.25
    assert loaded.source_id == "roundtrip"
    widened = pd.DataFrame(
        {
            "session_date": [pd.Timestamp("2026-06-02", tz="UTC")],
            "poc": [100.25],
            "n_ticks": [3],
            "source_id": ["roundtrip"],
        }
    )
    wide_path = tmp_path / "apoc_ts.parquet"
    widened.to_parquet(wide_path, index=False)
    loaded_wide = apoc_tick_table_from_parquet(wide_path)
    assert loaded_wide.poc_for(date(2026, 6, 2)) == 100.25


def test_normalized_levels_hash_has_no_new_always_on_keys() -> None:
    settings = normalize_levels_config({"apoc_enabled": True, "poc_windows": []}, instrument="ES")
    attached = attach_rolling_poc_identity(
        attach_apoc_identity(attach_tick_identity(settings, tick_source_id=TICK_SOURCE_NONE))
    )
    assert set(attached) - set(settings) <= _ALWAYS_ON_IDENTITY_KEYS
    assert "tick_stitch_plan" not in attached
    assert "tick_stitch_x1_burst_included" not in attached


_STITCH_QUALITY_COLUMNS = (
    "data_quality.shared_gap_1649_1758",
    "data_quality.x1_15s_residual_fill",
    "data_quality.x1_burst_included",
)


def _csv_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() == "true"


def _stitch_off_index_row(name: str) -> dict:
    from thesistester.study.execute import _failed_index_row

    row = _failed_index_row(name)
    row["status"] = "ok"
    row["bundle_path"] = f"{name}.research.zip"
    return row


def _stitch_quality_flags(
    *,
    residual: bool = False,
    burst: bool = False,
    shared_gap: bool = True,
) -> dict[str, bool]:
    return {
        "data_quality.x1_15s_residual_fill": residual,
        "data_quality.x1_burst_included": burst,
        "data_quality.shared_gap_1649_1758": shared_gap,
    }


def _assert_quality_csv_fields(path: Path) -> None:
    frame = pd.read_csv(path)
    for column in _STITCH_QUALITY_COLUMNS:
        assert column in frame.columns
        for value in frame[column].tolist():
            if pd.isna(value):
                continue
            if isinstance(value, str):
                assert value.strip().lower() in {"true", "false"}
            else:
                assert type(value) is bool
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        assert not line.lower().endswith(",nan")
        assert ",nan," not in line.lower()
        assert ",none," not in line.lower()


def _write_stitch_on_study_yaml(tmp_path: Path) -> Path:
    import yaml

    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(_plan_for(tick, rows)), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path="bars.csv",
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan="plan.json",
        tick_stitch_x1_burst_included=False,
    )
    spec["study"]["levels"]["poc_windows"] = []
    yaml_path = tmp_path / "study.yaml"
    yaml_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return yaml_path


def test_write_results_index_stitch_off_header_and_bytes_unchanged(tmp_path: Path) -> None:
    """Stitch-off ``results_index.csv`` stays STUDY_INDEX_KEYS-only (0ebc1494)."""
    names = ["cell_a", "cell_b"]
    rows = {name: _stitch_off_index_row(name) for name in names}
    path = _write_results_index(tmp_path, rows, names)
    expected_frame = pd.DataFrame([dict(rows[name]) for name in names])
    for key in STUDY_INDEX_KEYS:
        if key not in expected_frame.columns:
            expected_frame[key] = None
    expected_frame = expected_frame.loc[:, list(STUDY_INDEX_KEYS)]
    expected = tmp_path / "expected.csv"
    expected_frame.to_csv(expected, index=False)
    assert path.read_bytes() == expected.read_bytes()
    header = pd.read_csv(path).columns.tolist()
    assert header == list(STUDY_INDEX_KEYS)
    assert not any(column.startswith("data_quality.") for column in header)


def test_write_results_index_stitch_on_sorted_quality_empty_missing(
    tmp_path: Path,
) -> None:
    names = ["with_quality", "without_quality"]
    quality = {
        "data_quality.x1_15s_residual_fill": True,
        "data_quality.x1_burst_included": False,
        "data_quality.shared_gap_1649_1758": True,
    }
    rows = {
        "with_quality": {**_stitch_off_index_row("with_quality"), **quality},
        "without_quality": _stitch_off_index_row("without_quality"),
    }
    path = _write_results_index(tmp_path, rows, names)
    frame = pd.read_csv(path)
    assert list(frame.columns)[: len(STUDY_INDEX_KEYS)] == list(STUDY_INDEX_KEYS)
    assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    present = frame.loc[frame["run_name"] == "with_quality"].iloc[0]
    assert _csv_truthy(present["data_quality.x1_15s_residual_fill"]) is True
    assert _csv_truthy(present["data_quality.x1_burst_included"]) is False
    assert _csv_truthy(present["data_quality.shared_gap_1649_1758"]) is True
    missing = frame.loc[frame["run_name"] == "without_quality"].iloc[0]
    for column in _STITCH_QUALITY_COLUMNS:
        assert pd.isna(missing[column])
    raw = path.read_text(encoding="utf-8")
    _assert_quality_csv_fields(path)
    without_line = [line for line in raw.splitlines() if line.startswith("without_quality,")][0]
    assert without_line.endswith(",,,")


def test_stitch_on_results_index_has_data_quality_burst_false(tmp_path: Path) -> None:
    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(_plan_for(tick, rows)), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path=str(tmp_path / "bars.csv"),
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan=str(plan_path),
        tick_stitch_x1_burst_included=False,
    )
    spec["study"]["levels"]["poc_windows"] = []
    expansion = expand_study(spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        spec, expansion, output_dir=tmp_path / "out", base_directory=tmp_path
    )
    run = expansion.experiment["runs"][0]
    quality = run[_STITCH_DATA_QUALITY_KEY]
    assert quality["data_quality.x1_burst_included"] is False
    payload = execute_study_cell((run, str(tmp_path)))
    assert payload["status"] == "ok"
    for key, value in quality.items():
        assert payload["index_row"][key] is value
    name = str(run["name"])
    path = _write_results_index(tmp_path / "out", {name: payload["index_row"]}, [name])
    frame = pd.read_csv(path)
    assert list(frame.columns)[: len(STUDY_INDEX_KEYS)] == list(STUDY_INDEX_KEYS)
    assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    row = frame.iloc[0]
    assert _csv_truthy(row["data_quality.x1_burst_included"]) is False
    assert _csv_truthy(row["data_quality.x1_15s_residual_fill"]) is bool(
        quality["data_quality.x1_15s_residual_fill"]
    )
    assert _csv_truthy(row["data_quality.shared_gap_1649_1758"]) is bool(
        quality["data_quality.shared_gap_1649_1758"]
    )


def test_soft_resume_rereads_index_with_data_quality_columns(tmp_path: Path) -> None:
    from tests.study.test_study_execute import _fake_executor_factory, _mini_study_yaml

    quality = {
        "data_quality.x1_15s_residual_fill": False,
        "data_quality.x1_burst_included": False,
        "data_quality.shared_gap_1649_1758": True,
    }

    def _quality_executor(task):
        payload = _fake_executor_factory()(task)
        if payload["status"] == "ok":
            payload["index_row"] = {**payload["index_row"], **quality}
        return payload

    yaml_path = _mini_study_yaml(tmp_path / "study.yaml")
    (tmp_path / "bars.csv").write_text(
        "timestamp,open,high,low,close,volume\n2026-06-02 09:30:00,100,101,99,100,10\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    first = run_study(yaml_path, output_dir=out, cell_executor=_quality_executor)
    assert first["executed"] == 4
    index_path = out / "results_index.csv"
    first_frame = pd.read_csv(index_path)
    assert list(first_frame.columns)[: len(STUDY_INDEX_KEYS)] == list(STUDY_INDEX_KEYS)
    assert list(first_frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    loaded = _load_existing_index_rows(out)
    assert set(loaded) == set(first_frame["run_name"])
    for row in loaded.values():
        assert _csv_truthy(row["data_quality.x1_burst_included"]) is False
        assert _csv_truthy(row["data_quality.shared_gap_1649_1758"]) is True

    second = run_study(yaml_path, output_dir=out, cell_executor=_quality_executor)
    assert second["executed"] == 0
    second_frame = pd.read_csv(index_path)
    assert list(second_frame.columns) == list(first_frame.columns)
    for column in _STITCH_QUALITY_COLUMNS:
        assert [_csv_truthy(value) for value in second_frame[column].tolist()] == [
            _csv_truthy(value) for value in first_frame[column].tolist()
        ]


def test_rehydrate_preserves_data_quality_from_prior_row(tmp_path: Path) -> None:
    from tests.study.test_study_execute import _fake_bundle_bytes

    name = "cell_quality"
    bundle_name = f"{name}.research.zip"
    (tmp_path / bundle_name).write_bytes(_fake_bundle_bytes(name))
    prior = {
        "run_name": name,
        "dataset_id": "ds-test",
        "instrument": "ES",
        "data_quality.x1_15s_residual_fill": False,
        "data_quality.x1_burst_included": False,
        "data_quality.shared_gap_1649_1758": True,
    }
    row = _index_row_from_existing_bundle(
        name,
        output_dir=tmp_path,
        bundle_rel=bundle_name,
        prior_row=prior,
    )
    assert row["data_quality.x1_burst_included"] is False
    assert row["data_quality.x1_15s_residual_fill"] is False
    assert row["data_quality.shared_gap_1649_1758"] is True


def test_rebuild_direction_index_keeps_data_quality_columns(tmp_path: Path) -> None:
    from thesistester.study.execute import rebuild_direction_index
    from tests.study.test_study_execute import _trades_df, _zip_with_trades

    study_dir = tmp_path / "study_out"
    study_dir.mkdir()
    trades = _trades_df(directions=["long", "short"], r_values=[1.0, -0.2])
    (study_dir / "a.research.zip").write_bytes(_zip_with_trades(trades))
    row = {
        **_stitch_off_index_row("a"),
        "bundle_path": "a.research.zip",
        "trade_count": 2,
        "data_quality.x1_15s_residual_fill": False,
        "data_quality.x1_burst_included": False,
        "data_quality.shared_gap_1649_1758": True,
    }
    _write_results_index(study_dir, {"a": row}, ["a"])
    rebuilt = pd.read_csv(rebuild_direction_index(study_dir))
    assert list(rebuilt.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert _csv_truthy(rebuilt.iloc[0]["data_quality.x1_burst_included"]) is False
    assert _csv_truthy(rebuilt.iloc[0]["data_quality.shared_gap_1649_1758"]) is True


def test_coerce_data_quality_flag_bools_empty_and_pandas_traps() -> None:
    assert _coerce_data_quality_flag(True) is True
    assert _coerce_data_quality_flag(False) is False
    assert _coerce_data_quality_flag(None) is None
    assert _coerce_data_quality_flag(float("nan")) is None
    assert _coerce_data_quality_flag(pd.NA) is None
    assert _coerce_data_quality_flag("False") is False
    assert _coerce_data_quality_flag("true") is True
    assert _coerce_data_quality_flag(0) is False
    assert _coerce_data_quality_flag(1) is True
    assert _coerce_data_quality_flag(0.0) is False
    assert _coerce_data_quality_flag(1.0) is True
    assert _coerce_data_quality_flag(2) is None


def test_write_results_index_mixed_roundtrip_keeps_bools_and_empty(tmp_path: Path) -> None:
    names = [f"cell_{index:02d}" for index in range(12)]
    quality = _stitch_quality_flags(residual=True, burst=False, shared_gap=True)
    rows = {}
    for index, name in enumerate(names):
        row = _stitch_off_index_row(name)
        if index % 3 == 0:
            row.update(quality)
        rows[name] = row
    shuffled = {name: rows[name] for name in reversed(names)}
    path = _write_results_index(tmp_path, shuffled, names)
    frame = pd.read_csv(path)
    assert list(frame["run_name"]) == names
    assert list(frame.columns)[: len(STUDY_INDEX_KEYS)] == list(STUDY_INDEX_KEYS)
    assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    for index, name in enumerate(names):
        row = frame.loc[frame["run_name"] == name].iloc[0]
        if index % 3 == 0:
            assert _csv_truthy(row["data_quality.x1_burst_included"]) is False
            assert _csv_truthy(row["data_quality.x1_15s_residual_fill"]) is True
            assert _csv_truthy(row["data_quality.shared_gap_1649_1758"]) is True
        else:
            for column in _STITCH_QUALITY_COLUMNS:
                assert pd.isna(row[column])
    first_bytes = path.read_bytes()
    _assert_quality_csv_fields(path)
    loaded = _load_existing_index_rows(tmp_path)
    assert list(loaded) == names or set(loaded) == set(names)
    for index, name in enumerate(names):
        if index % 3 == 0:
            assert loaded[name]["data_quality.x1_burst_included"] is False
        else:
            assert loaded[name]["data_quality.x1_burst_included"] is None
    rewritten = _write_results_index(tmp_path, loaded, names)
    assert rewritten.read_bytes() == first_bytes


def test_finalize_overlays_stitch_quality_on_old_index(tmp_path: Path) -> None:
    from thesistester.study.ledger import empty_ledger, mark_cell

    name = "cell_old"
    row = {
        **_stitch_off_index_row(name),
        "trade_count": 3,
        "expectancy_r": 0.1,
        "profit_factor": 1.2,
        "win_rate": 0.5,
    }
    ledger = empty_ledger(study_identity_hash="hash", run_names=[name])
    ledger = mark_cell(
        ledger,
        name,
        status="ok",
        error=None,
        bundle_path=f"{name}.research.zip",
        finished=True,
    )
    quality = {name: _stitch_quality_flags(residual=False, burst=False, shared_gap=True)}
    path = _finalize_study_index(
        tmp_path,
        ledger,
        [name],
        {name: row},
        quality_by_name=quality,
    )
    frame = pd.read_csv(path)
    assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert _csv_truthy(frame.iloc[0]["data_quality.x1_burst_included"]) is False
    assert _csv_truthy(frame.iloc[0]["data_quality.shared_gap_1649_1758"]) is True
    _assert_quality_csv_fields(path)


def test_rehydrate_without_prior_row_then_finalize_restores_quality(tmp_path: Path) -> None:
    from tests.study.test_study_execute import _fake_bundle_bytes
    from thesistester.study.ledger import empty_ledger, mark_cell

    name = "cell_missing_index"
    bundle_name = f"{name}.research.zip"
    (tmp_path / bundle_name).write_bytes(_fake_bundle_bytes(name))
    row = _index_row_from_existing_bundle(
        name,
        output_dir=tmp_path,
        bundle_rel=bundle_name,
    )
    assert not any(_is_quality_key(key) for key in row)
    ledger = empty_ledger(study_identity_hash="hash", run_names=[name])
    ledger = mark_cell(
        ledger,
        name,
        status="ok",
        error=None,
        bundle_path=bundle_name,
        finished=True,
    )
    path = _finalize_study_index(
        tmp_path,
        ledger,
        [name],
        {name: row},
        quality_by_name={name: _stitch_quality_flags(burst=False)},
    )
    frame = pd.read_csv(path)
    assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert _csv_truthy(frame.iloc[0]["data_quality.x1_burst_included"]) is False


def _is_quality_key(key: object) -> bool:
    return isinstance(key, str) and key.startswith("data_quality.")


def test_soft_resume_old_stitch_on_index_restores_data_quality(tmp_path: Path) -> None:
    from tests.study.test_study_execute import _fake_executor_factory

    yaml_path = _write_stitch_on_study_yaml(tmp_path)
    out = tmp_path / "out"
    first = run_study(yaml_path, output_dir=out, cell_executor=_fake_executor_factory())
    assert first["executed"] > 0
    index_path = out / "results_index.csv"
    first_frame = pd.read_csv(index_path)
    assert list(first_frame.columns)[: len(STUDY_INDEX_KEYS)] == list(STUDY_INDEX_KEYS)
    assert list(first_frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert all(
        _csv_truthy(value) is False for value in first_frame["data_quality.x1_burst_included"]
    )
    first_frame.loc[:, list(STUDY_INDEX_KEYS)].to_csv(index_path, index=False)
    assert not any(column.startswith("data_quality.") for column in pd.read_csv(index_path).columns)

    second = run_study(yaml_path, output_dir=out, cell_executor=_fake_executor_factory())
    assert second["executed"] == 0
    restored = pd.read_csv(index_path)
    assert list(restored.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert all(_csv_truthy(value) is False for value in restored["data_quality.x1_burst_included"])
    _assert_quality_csv_fields(index_path)


def test_readers_tolerate_data_quality_columns(tmp_path: Path) -> None:
    from thesistester.study.observatory_join import _read_results_index
    from thesistester.study.report import _load_results_index as report_load
    from thesistester.study.rollup import _load_results_index as rollup_load

    names = ["alpha", "beta"]
    quality = _stitch_quality_flags(residual=True, burst=False, shared_gap=True)
    rows = {
        "alpha": {**_stitch_off_index_row("alpha"), **quality},
        "beta": _stitch_off_index_row("beta"),
    }
    _write_results_index(tmp_path, rows, names)
    report = report_load(tmp_path)
    rollup = rollup_load(tmp_path)
    observatory = _read_results_index(tmp_path / "results_index.csv")
    for frame in (report, rollup, observatory):
        assert "run_name" in frame.columns
        assert list(frame.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
        assert set(frame["run_name"]) == set(names)


def test_stitch_quality_by_run_name_reads_expansion_flags(tmp_path: Path) -> None:
    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(_plan_for(tick, rows)), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path=str(tmp_path / "bars.csv"),
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan=str(plan_path),
        tick_stitch_x1_burst_included=False,
    )
    spec["study"]["levels"]["poc_windows"] = []
    expansion = expand_study(spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        spec, expansion, output_dir=tmp_path / "out", base_directory=tmp_path
    )
    by_name = _stitch_quality_by_run_name(expansion)
    assert by_name
    for flags in by_name.values():
        assert flags["data_quality.x1_burst_included"] is False
        assert set(flags) == set(_STITCH_QUALITY_COLUMNS)


def test_run_experiment_passes_named_tokens_not_setup_mapping() -> None:
    """Regression: the TS5 call passed the setup mapping and hid named APOC."""
    source = inspect.getsource(run_experiment)
    assert "disable_unneeded_tick_families(" in source
    assert "_named_level_tokens_from_setup(setup)" in source
    assert 'disable_unneeded_tick_families(run.get("levels"), setup)' not in source


def test_disable_unneeded_tick_families_old_setup_mapping_call_fails() -> None:
    setup = {
        "selected_levels": ["APOC"],
        "anchor_level": None,
        "confluence_rules": [],
    }
    with pytest.raises(TypeError, match="named level tokens"):
        disable_unneeded_tick_families({"apoc_enabled": True}, setup)
    tokens = _named_level_tokens_from_setup(setup)
    assert tokens == ["APOC"]
    kept = disable_unneeded_tick_families({"apoc_enabled": True, "poc_windows": ["30min"]}, tokens)
    assert kept["apoc_enabled"] is True
    assert kept["poc_windows"] == []
    partner = _named_level_tokens_from_setup(
        {"selected_levels": ["ONH"], "anchor_level": None, "confluence_rules": [{"level": "pAPOC"}]}
    )
    assert partner == ["ONH", "pAPOC"]
    assert disable_unneeded_tick_families({"apoc_enabled": True}, partner)["apoc_enabled"] is True
    unnamed = _named_level_tokens_from_setup(
        {"selected_levels": ["dOpen", "RTH_Open"], "anchor_level": None, "confluence_rules": []}
    )
    off = disable_unneeded_tick_families({"apoc_enabled": True, "poc_windows": ["30min"]}, unnamed)
    assert off["apoc_enabled"] is False
    assert off["poc_windows"] == []
    # Farm w0/w7 expand to empty selected_levels + anchor. Iterating the
    # mapping (TS5) never sees APOC / pAPOC, so disable forced the family off.
    farm_w0 = {"selected_levels": [], "anchor_level": "APOC", "confluence_rules": []}
    assert named_apoc_tokens(farm_w0) == []
    assert _named_level_tokens_from_setup(farm_w0) == ["APOC"]
    farm_w7 = {
        "selected_levels": [],
        "anchor_level": "APOC",
        "confluence_rules": [{"level": "SMA_50_1min"}],
    }
    assert _named_level_tokens_from_setup(farm_w7) == ["APOC", "SMA_50_1min"]
    partner_only = {
        "selected_levels": [],
        "anchor_level": "dOpen",
        "confluence_rules": [{"level": "pAPOC"}],
    }
    assert _named_level_tokens_from_setup(partner_only) == ["dOpen", "pAPOC"]
    papoc_anchor = {"selected_levels": [], "anchor_level": "pAPOC", "confluence_rules": []}
    assert _named_level_tokens_from_setup(papoc_anchor) == ["pAPOC"]
    assert named_apoc_tokens(_named_level_tokens_from_setup(papoc_anchor)) == ["pAPOC"]


def _injected_apoc_child_spec(
    tmp_path: Path, *, selected_levels: list[str] | None = None
) -> tuple[dict, dict[date, float]]:
    table = APeriodTickProfileTable(
        poc_by_session={date(2026, 6, 2): 100.25, date(2026, 6, 3): 200.25},
        n_ticks_by_session={date(2026, 6, 2): 3, date(2026, 6, 3): 2},
        source_id="injected-apoc",
    )
    apoc_path = tmp_path / "apoc.parquet"
    apoc_tick_table_to_parquet(table, apoc_path)
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(
        bars_name="bars.csv",
        selected_levels=selected_levels or ["dOpen", "RTH_Open"],
        extra_dataset={
            "apoc_tick_table_path": str(apoc_path),
            "apoc_tick_source_id": "injected-apoc",
        },
    )
    spec["levels"]["poc_windows"] = []
    spec["setup"]["min_confluences"] = 1
    spec["setup"]["max_confluences"] = max(1, len(selected_levels or ["dOpen"]))
    return spec, {date(2026, 6, 2): 100.25, date(2026, 6, 3): 200.25}


def _apply_anchor_setup(spec: dict, *, anchor: str, partners: list[str] | None = None) -> dict:
    """Farm w0/w7 shape: anchor_rules, empty selected_levels, optional partners."""
    partners = partners or []
    spec["setup"]["confluence_mode"] = "anchor_rules"
    spec["setup"]["selected_levels"] = []
    spec["setup"]["anchor_level"] = anchor
    spec["setup"]["confluence_rules"] = [
        {"level": token, "tolerance_ticks": 0.0, "required": True} for token in partners
    ]
    spec["setup"]["min_valid_confluences"] = 0 if not partners else 1
    spec["setup"]["min_confluences"] = 1
    spec["setup"]["max_confluences"] = 1
    return spec


def _series_or_none(frame: pd.DataFrame, column: str) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), 8) for v in frame[column].tolist()]


def _assert_injected_apoc_matches_parent(state: dict, *, expect_papoc: bool = False) -> None:
    levels = state["levels"]
    assert COL_APOC in levels.columns
    # Same bars + same table POCs as §5.1 (b) stitch-absent pin.
    assert _series_or_none(levels, COL_APOC) == [
        None,
        None,
        100.25,
        100.25,
        None,
        None,
        200.25,
        200.25,
    ]
    if expect_papoc:
        assert COL_PAPOC in levels.columns
        assert _series_or_none(levels, COL_PAPOC) == [
            None,
            None,
            None,
            None,
            100.25,
            100.25,
            100.25,
            100.25,
        ]


@pytest.mark.parametrize(
    "selected_levels",
    [["APOC"], ["APOC", "dOpen"], ["dOpen", "pAPOC"]],
)
def test_stitch_on_named_apoc_child_path_keeps_parent_table(
    tmp_path: Path, selected_levels: list[str]
) -> None:
    spec, _expected = _injected_apoc_child_spec(tmp_path, selected_levels=selected_levels)
    assert "tick_paths" not in spec["dataset"]
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_injected_apoc_matches_parent(state, expect_papoc="pAPOC" in selected_levels)


@pytest.mark.parametrize("anchor", ["APOC", "pAPOC"])
def test_stitch_on_farm_one_anchor_apoc_child_keeps_parent_table(
    tmp_path: Path, anchor: str
) -> None:
    """progB_w0_apoc: anchor_rules, selected_levels=[], core APOC/pAPOC, empty partners.

    Old disable(setup) hid the family; generate_signals then raised
    ``Setup references unavailable level columns: ['APOC']`` (farm pilot).
    """
    spec, _expected = _injected_apoc_child_spec(tmp_path)
    _apply_anchor_setup(spec, anchor=anchor)
    assert spec["setup"]["selected_levels"] == []
    assert "tick_paths" not in spec["dataset"]
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_injected_apoc_matches_parent(state, expect_papoc=True)


def test_stitch_on_farm_w7_apoc_anchor_with_partner_keeps_parent_table(tmp_path: Path) -> None:
    """progB_w7 shape: APOC anchor + non-APOC confluence partner."""
    spec, _expected = _injected_apoc_child_spec(tmp_path)
    _apply_anchor_setup(spec, anchor="APOC", partners=["dOpen"])
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_injected_apoc_matches_parent(state, expect_papoc=True)
    assert "dOpen" in state["levels"].columns


def test_stitch_on_papoc_partner_rule_keeps_parent_table(tmp_path: Path) -> None:
    """pAPOC named only as a confluence-rule partner (not selected_levels)."""
    spec, _expected = _injected_apoc_child_spec(tmp_path)
    _apply_anchor_setup(spec, anchor="dOpen", partners=["pAPOC"])
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    _assert_injected_apoc_matches_parent(state, expect_papoc=True)


def test_stitch_on_farm_one_anchor_execute_study_cell_ok(tmp_path: Path) -> None:
    """Worker path that failed on the farm: execute_study_cell → run_experiment."""
    spec, _expected = _injected_apoc_child_spec(tmp_path)
    _apply_anchor_setup(spec, anchor="APOC")
    payload = execute_study_cell((spec, str(tmp_path)))
    assert payload["status"] == "ok", payload["error"]
    assert payload["error"] is None


def test_stitch_off_named_apoc_without_ticks_still_refuses(tmp_path: Path) -> None:
    """Stitch-off named APOC stays 0ebc1494: refuse, do not flip apoc_enabled on."""
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv", selected_levels=["APOC"])
    spec["setup"]["min_confluences"] = 1
    spec["setup"]["max_confluences"] = 1
    with pytest.raises(ValueError, match="APOC requires ticks"):
        run_experiment(spec, base_directory=tmp_path, cache_policy="off")


def test_stitch_off_farm_one_anchor_apoc_without_ticks_still_refuses(tmp_path: Path) -> None:
    """Farm w0 stitch-off (empty selected_levels, anchor APOC) still refuses."""
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv")
    _apply_anchor_setup(spec, anchor="APOC")
    with pytest.raises(ValueError, match="APOC requires ticks"):
        run_experiment(spec, base_directory=tmp_path, cache_policy="off")


def test_stitch_off_unnamed_apoc_still_disables_column(tmp_path: Path) -> None:
    """Stitch-off 15s-only cells still drop unused APOC (0ebc1494 disable)."""
    _write_two_session_bars_csv(tmp_path / "bars.csv")
    spec = _lean_run_spec(bars_name="bars.csv", selected_levels=["dOpen", "RTH_Open"])
    spec["levels"]["apoc_enabled"] = True
    state = run_experiment(spec, base_directory=tmp_path, cache_policy="off")
    assert COL_APOC not in state["levels"].columns
    assert "dOpen" in state["levels"].columns
    assert LEVEL_ENGINE_VERSION == 11


def _tiny_stitch_study(
    tmp_path: Path,
    *,
    burst: bool = False,
    day_bins: int = 4,
    value_area_pct: float = 0.70,
    one_cell: bool = False,
) -> dict:
    rows = [
        ("2026-01-15 10:00:00.000", 100.0, 1.0),
        ("2026-01-15 10:00:01.000", 101.0, 1.0),
    ]
    tick = _write_tick_csv(tmp_path / "early.csv", rows)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(__import__("json").dumps(_plan_for(tick, rows)), encoding="utf-8")
    _canonical_15s(tmp_path / "bars.csv", ["2026-01-15 10:00:00"])
    spec = _minimal_study(
        path=str(tmp_path / "bars.csv"),
        instrument="MNQ",
        format_profile="canonical",
        source_timezone="UTC",
        tick_stitch_plan=str(plan_path),
        tick_stitch_x1_burst_included=burst,
    )
    spec["study"]["levels"]["poc_windows"] = []
    spec["study"]["levels"]["prior_day_profile_aggregation_ticks"] = day_bins
    spec["study"]["levels"]["value_area_pct"] = value_area_pct
    if one_cell:
        spec["study"]["factors"]["partner_levels"] = [["SMA_50_1min"]]
        spec["study"]["factors"]["confluence_mode"] = ["global_cluster"]
    return spec


def test_shared_parent_cache_hit_miss_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thesistester.data.tick_stitch import build_stitch_parent_tables
    from thesistester.study.execute import (
        STUDY_APOC_TICK_PARQUET,
        STUDY_PRIOR_PROFILE_PARQUET,
        STUDY_TICK_STITCH_CACHE,
    )

    shared = tmp_path / "shared_cache"
    monkeypatch.setenv("THESISTESTER_TICK_STITCH_CACHE_DIR", str(shared))
    calls = {"build": 0}
    real = build_stitch_parent_tables

    def _wrap(*args, **kwargs):
        calls["build"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr("thesistester.study.execute.build_stitch_parent_tables", _wrap)

    spec = _tiny_stitch_study(tmp_path, burst=False)
    expansion = expand_study(spec, source_spec_parent=tmp_path)
    out1 = tmp_path / "out1"
    _prepare_study_tick_stitch(spec, expansion, output_dir=out1, base_directory=tmp_path)
    assert calls["build"] == 1
    prior1 = (out1 / STUDY_PRIOR_PROFILE_PARQUET).read_bytes()
    apoc1 = (out1 / STUDY_APOC_TICK_PARQUET).read_bytes()
    cache1 = (out1 / STUDY_TICK_STITCH_CACHE).read_text(encoding="utf-8")

    expansion2 = expand_study(spec, source_spec_parent=tmp_path)
    out2 = tmp_path / "out2"
    _prepare_study_tick_stitch(spec, expansion2, output_dir=out2, base_directory=tmp_path)
    assert calls["build"] == 1
    assert (out2 / STUDY_PRIOR_PROFILE_PARQUET).read_bytes() == prior1
    assert (out2 / STUDY_APOC_TICK_PARQUET).read_bytes() == apoc1
    assert (out2 / STUDY_TICK_STITCH_CACHE).read_text(encoding="utf-8") == cache1
    run1 = expansion.experiment["runs"][0]["dataset"]
    run2 = expansion2.experiment["runs"][0]["dataset"]
    assert run1["tick_source_id"] == run2["tick_source_id"]
    assert run1["apoc_tick_source_id"] == run2["apoc_tick_source_id"]
    assert expansion.experiment["runs"][0][_STITCH_DATA_QUALITY_KEY] == expansion2.experiment[
        "runs"
    ][0][_STITCH_DATA_QUALITY_KEY]
    dest_inode = (out2 / STUDY_PRIOR_PROFILE_PARQUET).stat().st_ino
    cache_parquet = next(shared.rglob(STUDY_PRIOR_PROFILE_PARQUET))
    assert cache_parquet.stat().st_ino != dest_inode
    cache_bytes = cache_parquet.read_bytes()
    (out2 / STUDY_PRIOR_PROFILE_PARQUET).write_bytes(b"mutated-dest-must-not-touch-cache")
    assert cache_parquet.read_bytes() == cache_bytes

    burst_spec = _tiny_stitch_study(tmp_path, burst=True)
    burst_exp = expand_study(burst_spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        burst_spec, burst_exp, output_dir=tmp_path / "out_burst", base_directory=tmp_path
    )
    assert calls["build"] == 2

    bin_spec = _tiny_stitch_study(tmp_path, burst=False, day_bins=8)
    bin_exp = expand_study(bin_spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        bin_spec, bin_exp, output_dir=tmp_path / "out_bins", base_directory=tmp_path
    )
    assert calls["build"] == 3

    vapct_spec = _tiny_stitch_study(tmp_path, burst=False, value_area_pct=0.68)
    vapct_exp = expand_study(vapct_spec, source_spec_parent=tmp_path)
    _prepare_study_tick_stitch(
        vapct_spec, vapct_exp, output_dir=tmp_path / "out_vapct", base_directory=tmp_path
    )
    assert calls["build"] == 4

    for parquet in shared.rglob("study.prior_profile.parquet"):
        parquet.chmod(0o644)
        parquet.write_bytes(b"corrupted-parent-table")
    expansion3 = expand_study(spec, source_spec_parent=tmp_path)
    out3 = tmp_path / "out3"
    _prepare_study_tick_stitch(spec, expansion3, output_dir=out3, base_directory=tmp_path)
    assert calls["build"] == 5
    assert (out3 / STUDY_PRIOR_PROFILE_PARQUET).read_bytes() == prior1
    assert (out3 / STUDY_APOC_TICK_PARQUET).read_bytes() == apoc1


def test_shared_parent_cache_two_studies_identical_bundles_and_levels_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hit vs miss: per-study artifacts, ids, data_quality, bundles, levels_meta."""
    import json
    import zipfile

    from thesistester.research_bundle import canonical_bundle_hash
    from thesistester.study.execute import (
        STUDY_APOC_TICK_PARQUET,
        STUDY_PRIOR_PROFILE_PARQUET,
        STUDY_TICK_STITCH_CACHE,
    )

    shared = tmp_path / "shared_cache"
    monkeypatch.setenv("THESISTESTER_TICK_STITCH_CACHE_DIR", str(shared))
    spec = _tiny_stitch_study(tmp_path, burst=False, one_cell=True)
    yaml_path = tmp_path / "study.yaml"
    yaml_path.write_text(__import__("yaml").safe_dump(spec, sort_keys=False), encoding="utf-8")

    out1 = tmp_path / "study_miss"
    out2 = tmp_path / "study_hit"
    first = run_study(yaml_path, output_dir=out1)
    second = run_study(yaml_path, output_dir=out2)
    assert first["executed"] == 1
    assert second["executed"] == 1

    assert (out1 / STUDY_PRIOR_PROFILE_PARQUET).read_bytes() == (
        out2 / STUDY_PRIOR_PROFILE_PARQUET
    ).read_bytes()
    assert (out1 / STUDY_APOC_TICK_PARQUET).read_bytes() == (
        out2 / STUDY_APOC_TICK_PARQUET
    ).read_bytes()
    cache1 = json.loads((out1 / STUDY_TICK_STITCH_CACHE).read_text(encoding="utf-8"))
    cache2 = json.loads((out2 / STUDY_TICK_STITCH_CACHE).read_text(encoding="utf-8"))
    assert cache1 == cache2
    assert cache1["data_quality"]["data_quality.x1_burst_included"] is False

    exp1 = __import__("yaml").safe_load((out1 / "experiment.yaml").read_text(encoding="utf-8"))
    exp2 = __import__("yaml").safe_load((out2 / "experiment.yaml").read_text(encoding="utf-8"))
    ds1 = exp1["runs"][0]["dataset"]
    ds2 = exp2["runs"][0]["dataset"]
    assert ds1["tick_source_id"] == ds2["tick_source_id"] == cache1["tick_source_id"]
    assert ds1["apoc_tick_source_id"] == ds2["apoc_tick_source_id"] == cache1["apoc_tick_source_id"]

    idx1 = pd.read_csv(out1 / "results_index.csv")
    idx2 = pd.read_csv(out2 / "results_index.csv")
    assert list(idx1.columns) == list(idx2.columns)
    assert list(idx1.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert [_csv_truthy(v) for v in idx1["data_quality.x1_burst_included"]] == [
        _csv_truthy(v) for v in idx2["data_quality.x1_burst_included"]
    ]
    assert idx1["bundle_hash"].tolist() == idx2["bundle_hash"].tolist()

    zips1 = sorted(out1.glob("*.research.zip"))
    zips2 = sorted(out2.glob("*.research.zip"))
    assert len(zips1) == len(zips2) == 1
    assert canonical_bundle_hash(zips1[0].read_bytes()) == canonical_bundle_hash(
        zips2[0].read_bytes()
    )
    with zipfile.ZipFile(zips1[0]) as left, zipfile.ZipFile(zips2[0]) as right:
        meta1 = json.loads(left.read("levels_meta.json").decode("utf-8"))
        meta2 = json.loads(right.read("levels_meta.json").decode("utf-8"))
    assert meta1 == meta2
    settings = meta1.get("levels_settings") or {}
    assert settings.get("tick_source_id") == cache1["tick_source_id"]
    assert settings.get("apoc_tick_source_id") == cache1["apoc_tick_source_id"]

    resume = run_study(yaml_path, output_dir=out2)
    assert resume["executed"] == 0
    restored = pd.read_csv(out2 / "results_index.csv")
    assert list(restored.columns)[len(STUDY_INDEX_KEYS) :] == list(_STITCH_QUALITY_COLUMNS)
    assert all(
        _csv_truthy(value) is False for value in restored["data_quality.x1_burst_included"]
    )
