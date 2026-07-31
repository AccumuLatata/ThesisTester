from __future__ import annotations

import subprocess
import sys

import pandas as pd
import yaml

from thesistester.api import run_experiment
from thesistester.cli import load_experiment_file, run_batch
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
            "sma_lengths": [],
            "ema_lengths": [],
            "sma_timeframes": [],
            "ema_timeframes": [],
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
            "n_bootstrap": 20,
            "n_permutations": 20,
            "random_state": 11,
            "excursion": {"enabled": True, "min_trades": 1},
            "monte_carlo": {
                "enabled": True,
                "n_simulations": 20,
                "random_state": 11,
            },
        },
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
    reference_state = run_experiment(_run("parity"), base_directory=tmp_path)
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
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(
        yaml.safe_dump({"schema_version": 2, "runs": [{"name": "../unsafe"}]}),
        encoding="utf-8",
    )
    try:
        load_experiment_file(invalid)
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("Expected invalid schema to be rejected")
