"""Command-line batch runner for headless ThesisTester experiments."""

from __future__ import annotations

import argparse
import os
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from thesistester.api import run_experiment
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash

EXPERIMENT_SCHEMA_VERSION = 1
_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def load_experiment_file(path: str | Path) -> dict[str, Any]:
    """Load and validate a versioned YAML batch definition."""
    experiment_path = Path(path)
    try:
        payload = yaml.safe_load(experiment_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to load experiment file {experiment_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Experiment file must contain a YAML mapping")
    if payload.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported experiment schema_version: {payload.get('schema_version')!r}; "
            f"expected {EXPERIMENT_SCHEMA_VERSION}"
        )
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Experiment file must define a non-empty runs list")

    names: list[str] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"runs[{index}] must be a mapping")
        name = run.get("name")
        if not isinstance(name, str) or not _RUN_NAME_RE.fullmatch(name):
            raise ValueError(
                f"runs[{index}].name must match {_RUN_NAME_RE.pattern!r}; got {name!r}"
            )
        names.append(name)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Run names must be unique; duplicates: {duplicates}")
    return payload


def _execute_run(
    task: tuple[dict[str, Any], str],
) -> tuple[str, bytes, dict[str, Any]]:
    run_spec, base_directory = task
    name = str(run_spec["name"])
    state = run_experiment(run_spec, base_directory=base_directory)
    bundle = build_research_bundle(state)
    summary = state.get("trade_summary") or {}
    best = state.get("best_grid_result") or {}
    validation = state.get("validation_summary") or {}
    index_row = {
        "run_name": name,
        "bundle_hash": canonical_bundle_hash(bundle),
        "dataset_id": state.get("dataset_id"),
        "instrument": state.get("instrument"),
        "trade_count": summary.get("trade_count"),
        "expectancy_r": summary.get("expectancy_r"),
        "total_r": summary.get("total_r"),
        "max_drawdown_r": summary.get("max_drawdown_r"),
        "best_grid_stop_loss_ticks": best.get("stop_loss_ticks"),
        "best_grid_take_profit_ticks": best.get("take_profit_ticks"),
        "validation_trade_count_status": (validation.get("trade_count") or {}).get("status"),
    }
    return name, bundle, index_row


def run_batch(
    experiment: Mapping[str, Any],
    *,
    base_directory: str | Path,
    output_directory: str | Path,
    workers: int = 1,
) -> pd.DataFrame:
    """Run independent experiments serially or in isolated worker processes."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    runs = experiment.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Experiment must contain a non-empty runs list")
    tasks = [(dict(run), str(Path(base_directory).resolve())) for run in runs]
    if workers == 1:
        completed = [_execute_run(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
            completed = list(executor.map(_execute_run, tasks))

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for name, bundle, row in completed:
        bundle_name = f"{name}.research.zip"
        (output / bundle_name).write_bytes(bundle)
        index_rows.append({**row, "bundle_path": bundle_name})
    index = pd.DataFrame(index_rows)
    index.to_csv(output / "results_index.csv", index=False)
    return index


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m thesistester",
        description="Run deterministic ThesisTester research experiments.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run a versioned YAML experiment batch")
    run_parser.add_argument("experiment", type=Path, help="Path to experiment YAML")
    run_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Independent worker processes (default: YAML workers or 1)",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: YAML output_dir or ./thesistester_results)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)
    if args.command != "run":
        raise AssertionError(f"Unhandled command: {args.command}")
    experiment_path = args.experiment.resolve()
    experiment = load_experiment_file(experiment_path)
    workers = args.workers if args.workers is not None else int(experiment.get("workers", 1))
    configured_output = experiment.get("output_dir", "thesistester_results")
    output = args.output_dir or Path(configured_output)
    if not output.is_absolute():
        output = experiment_path.parent / output
    index = run_batch(
        experiment,
        base_directory=experiment_path.parent,
        output_directory=output,
        workers=workers,
    )
    print(f"Completed {len(index)} run(s) with {workers} worker(s).")
    print(f"Results index: {(output / 'results_index.csv').resolve()}")
    return os.EX_OK
