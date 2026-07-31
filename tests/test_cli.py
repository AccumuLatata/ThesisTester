from __future__ import annotations

import subprocess
import sys
import math

import pandas as pd
import yaml

from thesistester.api import (
    build_setup,
    compute_levels,
    generate_signals,
    load_dataset,
    run_backtest,
    run_grid,
    run_validation,
)
from thesistester.cli import load_experiment_file, run_batch
from thesistester.data.loader import format_interval, validate_ohlcv
from thesistester.persistence.local_store import compute_dataset_id
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash


def _write_dataset(path) -> None:
    timestamps = pd.date_range("2026-06-01 09:30", periods=14, freq="1min")
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [100.5] * len(timestamps),
            "low": [99.5] * len(timestamps),
            "close": [100.25 if i % 2 == 0 else 99.75 for i in range(len(timestamps))],
            "volume": [100 + i for i in range(len(timestamps))],
        }
    ).to_csv(path, index=False)


def _run(name: str, *, stop: int = 2) -> dict:
    return {
        "name": name,
        "dataset": {
            "path": "bars.csv",
            "instrument": "ES",
            "source_timezone": "America/New_York",
        },
        "levels": {
            "sma_lengths": [2],
            "ema_lengths": [2],
            "sma_timeframes": ["1min"],
            "ema_timeframes": ["1min"],
            "vwap_windows": [],
            "poc_windows": [],
        },
        "setup": {
            "name": "R18 fixture",
            "description": "CLI parity fixture",
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
            "stop_loss_ticks": stop,
            "take_profit_ticks": 3,
            "exposure_policy": "single_position",
        },
        "grid": {
            "stop_loss_ticks_values": [2, 3],
            "take_profit_ticks_values": [3],
            "ranking_metric": "expectancy_r",
            "min_trades": 1,
        },
        "validation": {
            "n_bootstrap": 500,
            "n_permutations": 500,
            "random_state": 11,
            "excursion": {"enabled": True, "min_trades": 1},
            "monte_carlo": {
                "enabled": True,
                "n_simulations": 100,
                "random_state": 11,
            },
        },
    }


def _manual_ui_equivalent_state(run: dict, base_directory) -> dict:
    dataset = run["dataset"]
    instrument = dataset["instrument"]
    data = load_dataset(
        base_directory / dataset["path"],
        instrument=instrument,
        source_timezone=dataset["source_timezone"],
    )
    report = validate_ohlcv(data)
    base_interval = format_interval(report.inferred_interval)
    dataset_id = compute_dataset_id(
        data,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=dataset["source_timezone"],
        exchange_timezone="America/New_York",
    )
    level_result = compute_levels(data, instrument=instrument, config=run["levels"])
    setup = build_setup(run["setup"])
    signal_result = generate_signals(level_result["levels"], setup, instrument=instrument)
    backtest = run_backtest(
        level_result["levels"],
        signal_result["signals"],
        instrument=instrument,
        config=run["backtest"],
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
        last_signal_setup=setup,
    )
    grid = run_grid(
        level_result["levels"],
        signal_result["signals"],
        instrument=instrument,
        config=run["grid"],
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
        last_signal_setup=setup,
    )
    validation = run_validation(
        backtest["trades"],
        grid=grid["grid_results"],
        tick_size=0.25,
        config=run["validation"],
    )
    return {
        "data": data,
        "dataset_id": dataset_id,
        "instrument": instrument,
        "base_interval": base_interval,
        "source_timezone": dataset["source_timezone"],
        "exchange_timezone": "America/New_York",
        **level_result,
        "levels_data_fingerprint": {
            "instrument": instrument,
            "rows": len(data),
            "timestamp_min": str(data["timestamp"].min()),
            "timestamp_max": str(data["timestamp"].max()),
            "columns": sorted(data.columns),
            "base_interval": base_interval,
            "source_timezone": dataset["source_timezone"],
            "exchange_timezone": "America/New_York",
        },
        "setup_config": setup,
        **signal_result,
        "last_signal_setup": setup,
        "signal_context": {
            "setup_name": setup["name"],
            "confluence_mode": setup["confluence_mode"],
            "setup_caption": (
                "Trigger=touch • Direction=both • Confluences=2–2 • Trigger TF=base • OTF=disabled"
            ),
        },
        "trades": backtest["trades"],
        "trade_summary": backtest["trade_summary"],
        "equity_curve": backtest["equity_curve"],
        "backtest_otf_filter": backtest["otf_filter_summary"],
        "backtest_execution_costs": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
        },
        "grid_results": grid["grid_results"],
        "best_grid_result": grid["best_grid_result"],
        "grid_otf_filter": grid["otf_filter_summary"],
        **validation,
    }


def test_module_cli_bundle_matches_headless_ui_equivalent_pipeline(tmp_path):
    _write_dataset(tmp_path / "bars.csv")
    experiment = {
        "schema_version": 1,
        "output_dir": "cli-output",
        "runs": [_run("parity")],
    }
    yaml_path = tmp_path / "experiment.yaml"
    yaml_path.write_text(yaml.safe_dump(experiment, sort_keys=False), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "thesistester", "run", str(yaml_path), "--workers", "1"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    cli_bundle = (tmp_path / "cli-output" / "parity.research.zip").read_bytes()
    reference_state = _manual_ui_equivalent_state(_run("parity"), tmp_path)
    reference_bundle = build_research_bundle(reference_state)
    assert canonical_bundle_hash(cli_bundle) == canonical_bundle_hash(reference_bundle)


def test_parallel_batch_is_identical_to_serial(tmp_path):
    _write_dataset(tmp_path / "bars.csv")
    experiment = {
        "schema_version": 1,
        "runs": [_run("baseline", stop=2), _run("wider-stop", stop=3)],
    }
    serial = run_batch(
        experiment,
        base_directory=tmp_path,
        output_directory=tmp_path / "serial",
        workers=1,
    )
    parallel = run_batch(
        experiment,
        base_directory=tmp_path,
        output_directory=tmp_path / "parallel",
        workers=2,
    )
    pd.testing.assert_frame_equal(serial, parallel)
    for name in ("baseline", "wider-stop"):
        serial_bundle = (tmp_path / "serial" / f"{name}.research.zip").read_bytes()
        parallel_bundle = (tmp_path / "parallel" / f"{name}.research.zip").read_bytes()
        assert canonical_bundle_hash(serial_bundle) == canonical_bundle_hash(parallel_bundle)


def test_experiment_schema_and_names_fail_fast(tmp_path):
    cases = [
        ({"schema_version": 2, "runs": [{"name": "valid"}]}, "schema_version"),
        ({"schema_version": True, "runs": [{"name": "valid"}]}, "schema_version"),
        ({"schema_version": 1, "runs": [{"name": "../unsafe"}]}, "name must match"),
        (
            {
                "schema_version": 1,
                "runs": [{**_run("typo"), "validaton": {"random_state": 1}}],
            },
            "Unknown run configuration keys",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("unseeded"),
                        "validation": {"random_state": None},
                    }
                ],
            },
            "random_state",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("quoted-bool"),
                        "backtest": {"allow_same_bar_exit": "false"},
                    }
                ],
            },
            "must be a boolean",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("nan-risk"),
                        "backtest": {"stop_loss_ticks": math.nan},
                    }
                ],
            },
            "must be finite",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("negative-target"),
                        "backtest": {"take_profit_ticks": -1},
                    }
                ],
            },
            "must be >",
        ),
    ]
    for index, (payload, message) in enumerate(cases):
        invalid = tmp_path / f"invalid-{index}.yaml"
        invalid.write_text(yaml.safe_dump(payload), encoding="utf-8")
        try:
            load_experiment_file(invalid)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"Expected invalid experiment {index} to be rejected")


def test_programmatic_batch_rejects_unsafe_and_duplicate_names(tmp_path):
    _write_dataset(tmp_path / "bars.csv")
    for runs, message in (
        ([{**_run("safe"), "name": "../escape"}], "name must match"),
        ([_run("same"), _run("same")], "unique"),
    ):
        try:
            run_batch(
                {"schema_version": 1, "runs": runs},
                base_directory=tmp_path,
                output_directory=tmp_path / "output",
            )
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("Expected unsafe programmatic batch to be rejected")
