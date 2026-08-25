"""TV3 identity cutover — plan §10.3.

No 1m-typical fallback under ``pd*`` / ``pw*`` / ``pm*`` names. Goldens
(``tests/test_golden_master.py``) are not regenerated.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from thesistester.api import generate_signals
from thesistester.config import INSTRUMENTS
from thesistester.data.quantower_ticks import TickChunk
from thesistester.data.sessions import tag_session
from thesistester.levels import PRIOR_PROFILE_LEVEL_NAMES, compute_all_levels, compute_profile_levels
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.session_date import trading_session_date
from thesistester.levels.sessions import compute_session_levels
from thesistester.levels.tick_vap import (
    TICK_SOURCE_NONE,
    attach_tick_identity,
    build_prior_profile_table,
)
from thesistester.persistence.local_store import LEVEL_ENGINE_VERSION, compute_levels_settings_hash
from thesistester.research_identity import normalize_levels_config
from thesistester.setup import build_setup_config
from thesistester.study.execute import execute_study_cell
from thesistester.study.expand import expand_study
from thesistester.study.schema import (
    STUDY_SCHEMA_VERSION,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)
from tests.fixtures.assistant_parity import parity_run_spec, write_parity_bars

TZ = "America/New_York"
PDPOC_EXAMPLE = Path("examples/studies/pdPOC_ma_confluence_battery.yaml")


def _bars(
    start: str,
    closes: list[float],
    volumes: list[float] | None = None,
    *,
    freq: str = "1min",
) -> pd.DataFrame:
    ts = pd.date_range(start=start, periods=len(closes), freq=freq, tz=TZ)
    vols = volumes if volumes is not None else [1.0] * len(closes)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": vols,
        }
    )


def _tick_chunks(df: pd.DataFrame, *, instrument: str = "ES") -> list[TickChunk]:
    inst = INSTRUMENTS[instrument]
    work = df.sort_values("timestamp").reset_index(drop=True).copy()
    local_ts = work["timestamp"].dt.tz_convert(TZ)
    work["session_date"] = trading_session_date(local_ts, inst.eth_start)
    chunks: list[TickChunk] = []
    for session, group in work.groupby("session_date", sort=True):
        stamps = pd.to_datetime(group["timestamp"], utc=True)
        ticks = pd.DataFrame(
            {
                "timestamp": stamps,
                "price": group["close"].to_numpy(dtype="float64"),
                "volume": group["volume"].to_numpy(dtype="float64"),
            }
        )
        chunks.append(
            TickChunk(
                session_date=session if isinstance(session, date) else pd.Timestamp(session).date(),
                ticks=ticks,
                source_paths=("cutover-synthetic",),
                filename_window_mismatch=False,
                warnings=(),
                first_row_utc=pd.Timestamp(stamps.min()),
                last_row_utc=pd.Timestamp(stamps.max()),
                filename_window_start=None,
                filename_window_end=None,
            )
        )
    return chunks


def _table(df: pd.DataFrame, **kwargs):
    return build_prior_profile_table(_tick_chunks(df), instrument="ES", **kwargs)


def _two_session_df() -> pd.DataFrame:
    day1 = _bars("2026-06-01 09:30:00", [100.00, 100.25, 100.50], [10.0, 30.0, 5.0], freq="1h")
    day2 = _bars("2026-06-02 09:30:00", [101.00, 101.25], [8.0, 9.0], freq="1h")
    return pd.concat([day1, day2], ignore_index=True)


def _minimal_study(*, core: str = "ONH", tick_paths: list[str] | None = None) -> dict:
    dataset: dict = {"path": "data/es_1m.csv", "instrument": "ES"}
    if tick_paths is not None:
        dataset["tick_paths"] = tick_paths
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study": {
            "name": "tv3_cutover",
            "dataset": dataset,
            "levels": {
                "sma_lengths": [50],
                "ema_lengths": [21],
                "sma_timeframes": ["1min"],
                "ema_timeframes": ["1min"],
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
                "core_level": [core],
                "partner_levels": [["SMA_50_1min"]],
                "confluence_mode": ["global_cluster"],
                "trigger": ["touch"],
                "trigger_timeframe": ["base"],
                "otf": [{"enabled": False}],
            },
            "mode_rules": {
                "global_cluster": {
                    "selected_levels": ["${core_level}", "${partner_levels...}"],
                },
            },
            "report": {
                "primary_metric": "expectancy_r",
                "secondary_metrics": ["profit_factor"],
                "min_trades": 30,
                "multiple_testing": "warn",
            },
        },
    }


def test_compute_profile_levels_omits_va_without_table_rolling_poc_value_equal():
    df = _two_session_df()
    without = compute_profile_levels(df, instrument="ES", rolling_windows=["30min"])
    with_table = compute_profile_levels(
        df,
        instrument="ES",
        rolling_windows=["30min"],
        prior_profile_table=_table(df),
    )
    for name in PRIOR_PROFILE_LEVEL_NAMES:
        assert name not in without.columns
    assert "POC_rolling_30min" in without.columns
    pd.testing.assert_series_equal(without["POC_rolling_30min"], with_table["POC_rolling_30min"])


def test_dvwap_series_equal_to_frozen_typical_vector():
    df = tag_session(
        _bars("2026-06-02 09:30:00", [100.0, 110.0, 120.0], [1.0, 1.0, 2.0]),
        "ES",
    )
    out = compute_all_levels(
        df,
        instrument="ES",
        sma_lengths=[],
        ema_lengths=[],
        vwap_windows=[],
        poc_windows=[],
        session_vwap_enabled=True,
    )
    # H=L=C ⇒ typical = close. Same-session cumsum: 100, 105, 112.5.
    pd.testing.assert_series_equal(
        out["dVWAP"],
        pd.Series([100.0, 105.0, 112.5], index=out.index, name="dVWAP"),
        check_names=True,
    )


def test_session_marks_value_equal_without_tick_table():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-02 18:00:00",
                    "2026-06-03 08:00:00",
                    "2026-06-03 09:30:00",
                ]
            ).tz_localize(TZ),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.0, 102.0, 103.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    tagged = tag_session(df, "ES")
    session = compute_session_levels(tagged, instrument="ES")
    combined = compute_all_levels(
        tagged,
        instrument="ES",
        sma_lengths=[],
        ema_lengths=[],
        vwap_windows=[],
        poc_windows=[],
    )
    for col in ("ONH", "ONL", "dOpen", "RTH_Open"):
        pd.testing.assert_series_equal(session[col], combined[col], check_names=True)


def test_table_shift_maps_prior_session_and_first_session_is_nan():
    df = _two_session_df()
    out = compute_profile_levels(
        df, instrument="ES", rolling_windows=["30min"], prior_profile_table=_table(df)
    )
    first = out[out["timestamp"].dt.date == pd.Timestamp("2026-06-01").date()]
    second = out[out["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()]
    assert first["pdPOC"].isna().all()
    assert first["pdVAH"].isna().all()
    assert first["pdVAL"].isna().all()
    np.testing.assert_allclose(second["pdPOC"].to_numpy(), [100.25, 100.25])
    np.testing.assert_allclose(second["pdVAH"].to_numpy(), [100.25, 100.25])
    np.testing.assert_allclose(second["pdVAL"].to_numpy(), [100.00, 100.00])


def test_future_tick_session_does_not_change_earlier_pdva():
    base = _two_session_df()
    table_base = _table(base)
    out_base = compute_profile_levels(
        base, instrument="ES", rolling_windows=["30min"], prior_profile_table=table_base
    )
    day3 = _bars("2026-06-03 09:30:00", [999.0, 1000.0], [9_999.0, 9_999.0], freq="1h")
    extended = pd.concat([base, day3], ignore_index=True)
    out_ext = compute_profile_levels(
        extended,
        instrument="ES",
        rolling_windows=["30min"],
        prior_profile_table=_table(extended),
    )
    mask = out_base["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()
    mask_ext = out_ext["timestamp"].dt.date == pd.Timestamp("2026-06-02").date()
    for col in ("pdVAH", "pdVAL", "pdPOC"):
        pd.testing.assert_series_equal(
            out_base.loc[mask, col].reset_index(drop=True),
            out_ext.loc[mask_ext, col].reset_index(drop=True),
        )


def test_product_day_aggregation_is_one_week_month_unchanged():
    assert DEFAULT_LEVELS_SETTINGS["prior_day_profile_aggregation_ticks"] == 1
    assert DEFAULT_LEVELS_SETTINGS["prior_week_profile_aggregation_ticks"] == 8
    assert DEFAULT_LEVELS_SETTINGS["prior_month_profile_aggregation_ticks"] == 10


def test_level_engine_version_is_11():
    assert LEVEL_ENGINE_VERSION == 11


def test_tick_source_id_is_inside_settings_hash():
    base = normalize_levels_config({}, instrument="ES")
    none = attach_tick_identity(base, tick_source_id=TICK_SOURCE_NONE)
    other = attach_tick_identity(base, tick_source_id="abc")
    assert none["tick_source_id"] == TICK_SOURCE_NONE
    assert none["va_source"] == "tick_last"
    assert compute_levels_settings_hash(none) != compute_levels_settings_hash(base)
    assert compute_levels_settings_hash(none) != compute_levels_settings_hash(other)


def test_named_pdvah_studyspec_without_ticks_refuses():
    with pytest.raises(StudySpecError, match="VA requires ticks"):
        validate_study_spec(normalize_study_spec(_minimal_study(core="pdVAH")))


def test_onh_standin_studyspec_validates_without_ticks():
    validated = validate_study_spec(normalize_study_spec(_minimal_study(core="ONH")))
    assert validated["study"]["factors"]["core_level"] == ["ONH"]


def test_named_va_with_tick_paths_validates_and_example_expands():
    validated = validate_study_spec(
        normalize_study_spec(_minimal_study(core="pdVAH", tick_paths=["data/es_ticks.csv"]))
    )
    assert validated["study"]["dataset"]["tick_paths"] == ["data/es_ticks.csv"]

    raw = yaml.safe_load(PDPOC_EXAMPLE.read_text(encoding="utf-8"))
    example = validate_study_spec(normalize_study_spec(raw))
    assert example["study"]["dataset"]["tick_paths"]
    expansion = expand_study(example)
    assert expansion.run_count == 40
    assert example["study"]["factors"]["core_level"] == ["pdPOC"]


def test_generate_signals_pdvah_on_no_table_frame_raises_lc4():
    df = compute_all_levels(
        tag_session(_bars("2026-06-02 09:30:00", [100.0, 101.0, 102.0]), "ES"),
        instrument="ES",
        sma_lengths=[],
        ema_lengths=[],
        vwap_windows=[],
        poc_windows=[],
    )
    assert "pdVAH" not in df.columns
    setup = build_setup_config(
        name="tv3_lc4",
        description="test",
        instrument="ES",
        selected_levels=["pdVAH"],
        tolerance_ticks=4.0,
        min_confluences=1,
        max_confluences=5,
        naked_only=False,
        naked_requirement="any",
        trigger="touch",
        direction="both",
        trigger_params={},
    )
    with pytest.raises(ValueError, match="Setup references unavailable level columns:") as exc:
        generate_signals(df, setup)
    assert "pdVAH" in str(exc.value)


def test_execute_study_cell_records_lc4_failed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("thesistester.api._require_ticks_for_named_va", lambda *a, **k: None)
    write_parity_bars(tmp_path / "bars.csv")
    spec = parity_run_spec(dataset_path="bars.csv", name="tv3_lc4_cell")
    spec["setup"]["selected_levels"] = ["pdVAH"]
    payload = execute_study_cell((spec, str(tmp_path)))
    assert payload["status"] == "failed"
    assert payload["bundle"] is None
    error = payload["error"] or ""
    assert error.startswith("ValueError:")
    assert "unavailable level columns" in error
    assert "pdVAH" in error


def test_fifteen_second_onh_dvwap_studyspec_validates_without_ticks():
    raw = _minimal_study(core="ONH")
    raw["study"]["factors"]["partner_levels"] = [["dVWAP"]]
    validated = validate_study_spec(normalize_study_spec(raw))
    assert validated["study"]["factors"]["core_level"] == ["ONH"]
    assert validated["study"]["factors"]["partner_levels"] == [["dVWAP"]]
    assert "tick_paths" not in validated["study"]["dataset"]
