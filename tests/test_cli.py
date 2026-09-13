from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

import thesistester.api as api
from thesistester.api import (
    build_setup,
    compute_levels,
    generate_signals,
    load_dataset,
    run_backtest,
    run_grid,
    run_validation,
)
from thesistester.cli import load_experiment_file, main, run_batch
from thesistester.data.loader import format_interval, validate_ohlcv
from thesistester.persistence.local_store import compute_dataset_id
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.research_identity import DataIdentity, LevelsIdentity


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
            "apoc_enabled": False,
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
    source_timezone = dataset["source_timezone"]
    exchange_timezone = "America/New_York"
    format_profile = str(dataset.get("format_profile", "canonical"))
    data_identity = DataIdentity.from_loaded_data(
        data,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=format_profile,
    )
    dataset_id = data_identity.dataset_id()
    assert dataset_id == compute_dataset_id(
        data,
        instrument=instrument,
        base_interval=base_interval,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )
    level_result = compute_levels(data, instrument=instrument, config=run["levels"])
    levels_identity = LevelsIdentity.from_normalized(data_identity, level_result["levels_settings"])
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
        "source_timezone": source_timezone,
        "exchange_timezone": exchange_timezone,
        "format_profile": format_profile,
        **level_result,
        "levels_data_fingerprint": {
            "instrument": instrument,
            "rows": len(data),
            "timestamp_min": str(data["timestamp"].min()),
            "timestamp_max": str(data["timestamp"].max()),
            "columns": sorted(data.columns),
            "base_interval": base_interval,
            "source_timezone": source_timezone,
            "exchange_timezone": exchange_timezone,
        },
        "data_identity": data_identity.to_dict(),
        "levels_identity": levels_identity.to_dict(),
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
        "backtest_intrabar_policy": {
            "schema_version": 1,
            "intrabar_model": "sl_first",
            "subtimeframe_data_supplied": False,
        },
        "backtest_intrabar_diagnostic": backtest["intrabar_diagnostic"],
        "backtest_exit_management_policy": {
            "schema_version": 1,
            "breakeven_after_r": None,
            "trailing_after_r": None,
            "trailing_distance_ticks": None,
        },
        "backtest_exit_management_diagnostic": backtest["exit_management_diagnostic"],
        "backtest_execution_costs": {
            "commission_per_side": 0.0,
            "slippage_ticks": 0.0,
        },
        "grid_results": grid["grid_results"],
        "best_grid_result": grid["best_grid_result"],
        "grid_otf_filter": grid["otf_filter_summary"],
        "grid_intrabar_policy": {
            "schema_version": 1,
            "intrabar_model": "sl_first",
            "subtimeframe_data_supplied": False,
        },
        "grid_exit_management_policy": {
            "schema_version": 1,
            "breakeven_after_r_values": [None],
            "trailing_after_r_values": [None],
            "trailing_distance_ticks_values": [None],
            "max_grid_cells": 500,
        },
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


def test_experiment_forwards_subtimeframe_data_to_r15_replay(tmp_path, monkeypatch):
    """R15 grid replay must retain the grid's lower-timeframe fill input."""
    _write_dataset(tmp_path / "bars.csv")
    base = pd.read_csv(tmp_path / "bars.csv")
    subtimeframe_rows = []
    for parent in base.itertuples(index=False):
        timestamp = pd.Timestamp(parent.timestamp)
        subtimeframe_rows.extend(
            [
                (timestamp, parent.open, parent.high, parent.open, parent.open),
                (
                    timestamp + pd.Timedelta(seconds=15),
                    parent.open,
                    parent.open,
                    parent.low,
                    parent.low,
                ),
                (
                    timestamp + pd.Timedelta(seconds=30),
                    parent.low,
                    parent.open,
                    parent.low,
                    parent.open,
                ),
                (
                    timestamp + pd.Timedelta(seconds=45),
                    parent.open,
                    max(parent.open, parent.close),
                    min(parent.open, parent.close),
                    parent.close,
                ),
            ]
        )
    pd.DataFrame(
        subtimeframe_rows,
        columns=["timestamp", "open", "high", "low", "close"],
    ).assign(volume=25).to_csv(tmp_path / "subtimeframe.csv", index=False)

    run = _run("r15-subtimeframe")
    run["dataset"]["subtimeframe_path"] = "subtimeframe.csv"
    run["grid"]["intrabar_model"] = "subtimeframe"
    run["validation"] = {"overfitting": {"enabled": True}}
    captured: dict = {}

    def capture_validation(*_args, **kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(api, "run_validation", capture_validation)
    state = api.run_experiment(run, base_directory=tmp_path)

    execution_kwargs = captured["execution_kwargs"]
    assert execution_kwargs["intrabar_model"] == "subtimeframe"
    assert execution_kwargs["subtimeframe_data"] is state["subtimeframe_data"]


def test_experiment_loads_subtimeframe_as_canonical_with_vendor_parent(tmp_path, monkeypatch):
    """R12 lower-timeframe replay accepts canonical OHLCV beside a vendor parent."""
    _write_dataset(tmp_path / "canonical_parent.csv")
    parent = pd.read_csv(tmp_path / "canonical_parent.csv")
    (tmp_path / "ninjatrader_parent.txt").write_text(
        "".join(
            f"{pd.Timestamp(row.timestamp):%Y%m%d %H%M%S};{row.open};{row.high};"
            f"{row.low};{row.close};{row.volume}\n"
            for row in parent.itertuples(index=False)
        )
    )
    subtimeframe = []
    for row in parent.itertuples(index=False):
        timestamp = pd.Timestamp(row.timestamp)
        subtimeframe.extend(
            [
                (timestamp, row.open, row.high, row.open, row.open),
                (
                    timestamp + pd.Timedelta(seconds=30),
                    row.open,
                    max(row.open, row.close),
                    min(row.low, row.close),
                    row.close,
                ),
            ]
        )
    pd.DataFrame(
        subtimeframe,
        columns=["timestamp", "open", "high", "low", "close"],
    ).assign(volume=25).to_csv(tmp_path / "subtimeframe.csv", index=False)

    run = _run("vendor-parent-canonical-subtimeframe")
    run["dataset"].update(
        {
            "path": "ninjatrader_parent.txt",
            "format_profile": "ninjatrader",
            "subtimeframe_path": "subtimeframe.csv",
        }
    )
    captured: dict = {}

    def capture_validation(*_args, **kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(api, "run_validation", capture_validation)
    state = api.run_experiment(run, base_directory=tmp_path)

    assert state["subtimeframe_data"]["timestamp"].size == len(subtimeframe)
    assert captured["execution_kwargs"]["subtimeframe_data"] is state["subtimeframe_data"]


def test_parallel_batch_is_identical_to_serial(tmp_path):
    _write_dataset(tmp_path / "bars.csv")
    path_run = _run("path-model", stop=3)
    path_run["backtest"]["intrabar_model"] = "path_open_proximity"
    path_run["grid"]["intrabar_model"] = "path_open_proximity"
    path_run["grid"]["trailing_after_r_values"] = [None, 1.0]
    path_run["grid"]["trailing_distance_ticks_values"] = [None, 2.0]
    path_run["grid"]["max_grid_cells"] = 8
    path_run["walk_forward"] = {
        "enabled": True,
        "fold_mode": "bars",
        "window_mode": "rolling",
        "train_bars": 6,
        "test_bars": 4,
        "step_bars": 4,
        "stop_loss_ticks_values": [2],
        "take_profit_ticks_values": [3],
    }
    experiment = {
        "schema_version": 1,
        "runs": [_run("baseline", stop=2), path_run],
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
    for name in ("baseline", "path-model"):
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
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("bad-intrabar"),
                        "backtest": {"intrabar_model": "clairvoyant"},
                    }
                ],
            },
            "intrabar_model",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("missing-sub-bars"),
                        "backtest": {"intrabar_model": "subtimeframe"},
                    }
                ],
            },
            "subtimeframe_path",
        ),
        (
            {
                "schema_version": 1,
                "runs": [
                    {
                        **_run("bad-trailing"),
                        "backtest": {"trailing_after_r": 1.0},
                    }
                ],
            },
            "trailing_distance_ticks",
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


def test_study_report_rebuild_direction_flag():
    from thesistester.cli import _parser

    parser = _parser()
    flagged = parser.parse_args(["study", "report", "/tmp/x", "--rebuild-direction"])
    assert flagged.rebuild_direction is True
    default = parser.parse_args(["study", "report", "/tmp/x"])
    assert default.rebuild_direction is False


_H8_CLI_HELP_NEEDLES = (
    "omitted battery enabled means on",
    "study emit stays explicit false",
    "otf validation matrix is default-off",
)


def _cli_help_blobs() -> tuple[str, str]:
    import argparse

    from thesistester.cli import _parser

    parser = _parser()
    run_help = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            run_help = action.choices["run"].format_help()
            break
    if run_help is None:
        raise AssertionError("cli parser has no run subparser")
    return parser.format_help(), run_help


def _collapsed(text: str) -> str:
    return " ".join(text.lower().split())


def test_cli_help_discloses_omitted_battery_enabled_means_on():
    """QI-06-08 / A-9: ``--help`` must name omit-means-on (not a comment needle)."""
    top, run_help = _cli_help_blobs()
    for blob, label in ((top, "top-level --help"), (run_help, "run --help")):
        collapsed = _collapsed(blob)
        missing = [needle for needle in _H8_CLI_HELP_NEEDLES if needle not in collapsed]
        assert missing == [], f"{label} missing H8 needles {missing}"
        assert "qi-06-08" not in collapsed, f"{label} leaked a source-comment needle"


def test_omitted_grid_enabled_still_runs_qi0608(tmp_path):
    """QI-06-08 / A-9: omitted ``grid.enabled`` still runs (locked H8). Do not flip."""
    _write_dataset(tmp_path / "bars.csv")
    omitted = _run("omit-enabled")
    assert "enabled" not in omitted["grid"]
    on_state = api.run_experiment(omitted, base_directory=tmp_path)
    assert on_state.get("grid_results") is not None
    assert not on_state["grid_results"].empty

    off = _run("explicit-false")
    off["grid"] = {**off["grid"], "enabled": False}
    off_state = api.run_experiment(off, base_directory=tmp_path)
    assert "grid_results" not in off_state


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


def _module_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """QI-06-12 / QI-6 §3.2: exercise ``python -m thesistester`` (__main__)."""
    return subprocess.run(
        [sys.executable, "-m", "thesistester", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_module_cli_help_exits_zero():
    """QI-6 §3.2: ``--help`` exit 0; verbs run / study / journal."""
    top = _module_cli("--help")
    assert top.returncode == 0, top.stderr
    assert "Traceback" not in top.stderr
    # Fail-closed: argparse usage token, not H8 prose ("Run deterministic…",
    # "Study emit stays…") which would make substring verb checks pass anyway.
    assert "{run,study,journal}" in top.stdout
    run_help = _module_cli("run", "--help")
    assert run_help.returncode == 0, run_help.stderr
    assert "Traceback" not in run_help.stderr
    run_blob = " ".join(run_help.stdout.lower().split())
    assert "experiment" in run_blob
    assert "--workers" in run_help.stdout
    assert "--output-dir" in run_help.stdout


def test_module_cli_run_error_paths_exit_one(tmp_path):
    """QI-6 §3.2: missing file / invalid YAML / empty runs → exit 1 + traceback."""
    missing = tmp_path / "missing.yaml"
    missing_proc = _module_cli("run", str(missing))
    assert missing_proc.returncode == 1
    assert "Traceback" in missing_proc.stderr
    assert "Unable to load experiment file" in missing_proc.stderr

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("[\n", encoding="utf-8")
    invalid_proc = _module_cli("run", str(invalid))
    assert invalid_proc.returncode == 1
    assert "Traceback" in invalid_proc.stderr
    assert "Unable to load experiment file" in invalid_proc.stderr

    empty = tmp_path / "empty-runs.yaml"
    empty.write_text("schema_version: 1\nruns: []\n", encoding="utf-8")
    empty_proc = _module_cli("run", str(empty))
    assert empty_proc.returncode == 1
    assert "Traceback" in empty_proc.stderr
    assert "Experiment file must define a non-empty runs list" in empty_proc.stderr


def test_cli_main_error_paths_raise_value_error(tmp_path):
    """QI-06-07 residual: ``cli.main`` does not catch ValueError (raw traceback)."""
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ValueError, match="Unable to load experiment file"):
        main(["run", str(missing)])

    not_mapping = tmp_path / "list.yaml"
    not_mapping.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping"):
        main(["run", str(not_mapping)])

    empty = tmp_path / "empty-runs.yaml"
    empty.write_text("schema_version: 1\nruns: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty runs list"):
        main(["run", str(empty)])

    unknown = tmp_path / "unknown-key.yaml"
    unknown.write_text(
        "schema_version: 1\nruns:\n  - name: x\nextra: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown experiment configuration keys"):
        main(["run", str(unknown)])


def test_cli_main_resolves_yaml_workers_and_output_dir(tmp_path, monkeypatch, capsys):
    """``main`` uses YAML workers when ``--workers`` is omitted; flag output wins."""
    yaml_path = tmp_path / "experiment.yaml"
    yaml_path.write_text("schema_version: 1\nruns: []\n", encoding="utf-8")
    captured: dict = {}

    monkeypatch.setattr(
        "thesistester.cli.load_experiment_file",
        lambda _path: {"schema_version": 1, "workers": 2, "runs": [{"name": "stub"}]},
    )

    def _fake_batch(experiment, *, base_directory, output_directory, workers):
        captured["experiment"] = experiment
        captured["base_directory"] = base_directory
        captured["output_directory"] = Path(output_directory)
        captured["workers"] = workers
        return pd.DataFrame([{"run_name": "stub"}])

    monkeypatch.setattr("thesistester.cli.run_batch", _fake_batch)

    flag_out = tmp_path / "flag-out"
    assert main(["run", str(yaml_path), "--output-dir", str(flag_out)]) == 0
    assert captured["workers"] == 2
    assert captured["output_directory"] == flag_out
    printed = capsys.readouterr().out
    assert "Completed 1 run(s) with 2 worker(s)." in printed

    monkeypatch.setattr(
        "thesistester.cli.load_experiment_file",
        lambda _path: {"schema_version": 1, "runs": [{"name": "stub"}]},
    )
    captured.clear()
    assert main(["run", str(yaml_path)]) == 0
    assert captured["workers"] == 1
    assert captured["output_directory"] == yaml_path.parent / "thesistester_results"


def test_cli_main_run_writes_index(tmp_path, capsys):
    _write_dataset(tmp_path / "bars.csv")
    yaml_path = tmp_path / "experiment.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "output_dir": "cli-main-out",
                "workers": 1,
                "runs": [_run("cli-main")],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    code = main(["run", str(yaml_path), "--workers", "1"])
    assert code == 0
    printed = capsys.readouterr().out
    assert "Completed 1 run(s)" in printed
    assert "results_index.csv" in printed
    assert (tmp_path / "cli-main-out" / "results_index.csv").is_file()


def test_cli_main_dispatches_study_and_journal(monkeypatch):
    monkeypatch.setattr(
        "thesistester.study.cli_study.dispatch_study",
        lambda args: 17,
    )
    monkeypatch.setattr(
        "thesistester.journal.cli.dispatch_journal",
        lambda args: 23,
    )
    assert main(["study", "list"]) == 17
    assert (
        main(
            [
                "journal",
                "report",
                "--journal-dir",
                "/tmp/journal",
                "--output-dir",
                "/tmp/out",
            ]
        )
        == 23
    )
