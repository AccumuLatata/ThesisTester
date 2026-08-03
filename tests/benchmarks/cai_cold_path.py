"""Informational cold-path stage timings for CAI-0.

This harness characterizes the current headless path that always reloads CSV
and recomputes levels. It is intentionally non-gating: wall time varies by
hardware and package versions. CI only smoke-tests that the scenarios run and
emit the expected stage names.
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from tests.fixtures.cai_baseline import CAI_FIXTURE_KIND, cai_run_spec, write_cai_bars
from thesistester.api import (
    build_setup,
    compute_levels,
    generate_signals,
    load_dataset,
    run_backtest,
    run_experiment,
)
from thesistester.research_bundle import build_research_bundle


def _timed_ms(operation: Callable[[], object], *, repeats: int) -> dict[str, float]:
    samples: list[float] = []
    operation()
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1_000)
    ordered = sorted(samples)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[max(0, int(len(samples) * 0.95) - 1)], 3),
    }


def measure_cai_cold_path(
    *,
    kind: CAI_FIXTURE_KIND,
    repeats: int = 5,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Measure one fixture size through the current cold headless path."""
    root = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="cai0_"))
    root.mkdir(parents=True, exist_ok=True)
    bars_path = write_cai_bars(root / f"{kind}_bars.csv", kind=kind)
    spec = cai_run_spec(dataset_path=str(bars_path.resolve()), kind=kind)
    dataset = dict(spec["dataset"])
    instrument = str(dataset["instrument"])
    source_timezone = str(dataset["source_timezone"])
    exchange_timezone = str(dataset["exchange_timezone"])

    data = load_dataset(
        bars_path,
        instrument=instrument,
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
        format_profile=str(dataset.get("format_profile", "canonical")),
    )
    level_result = compute_levels(data, instrument=instrument, config=spec["levels"])
    setup = build_setup(dict(spec["setup"]))
    signal_result = generate_signals(level_result["levels"], setup, instrument=instrument)
    backtest_result = run_backtest(
        level_result["levels"],
        signal_result["signals"],
        instrument=instrument,
        config=spec["backtest"],
        setup_config=setup,
        signal_settings=signal_result["signal_settings"],
        last_signal_setup=setup,
    )
    # Use the public composition path for bundle construction so the stage
    # measures production artifact packaging rather than a hand-built dict.
    experiment_state = run_experiment(spec, base_directory=root)

    stages = [
        (
            "load_dataset",
            lambda: load_dataset(
                bars_path,
                instrument=instrument,
                source_timezone=source_timezone,
                exchange_timezone=exchange_timezone,
                format_profile=str(dataset.get("format_profile", "canonical")),
            ),
        ),
        (
            "compute_levels",
            lambda: compute_levels(data, instrument=instrument, config=spec["levels"]),
        ),
        (
            "generate_signals",
            lambda: generate_signals(level_result["levels"], setup, instrument=instrument),
        ),
        (
            "run_backtest",
            lambda: run_backtest(
                level_result["levels"],
                signal_result["signals"],
                instrument=instrument,
                config=spec["backtest"],
                setup_config=setup,
                signal_settings=signal_result["signal_settings"],
                last_signal_setup=setup,
            ),
        ),
        (
            "build_research_bundle",
            lambda: build_research_bundle(experiment_state),
        ),
        (
            "run_experiment_end_to_end",
            lambda: run_experiment(spec, base_directory=root),
        ),
    ]

    rows: list[dict[str, Any]] = []
    for stage_name, operation in stages:
        timing = _timed_ms(operation, repeats=repeats)
        rows.append(
            {
                "fixture": kind,
                "stage": stage_name,
                "bar_count": int(len(data)),
                "poc_windows": list(spec["levels"].get("poc_windows") or []),
                **timing,
            }
        )

    return {
        "fixture": kind,
        "bar_count": int(len(data)),
        "dataset_path": str(bars_path),
        "levels_config": dict(spec["levels"]),
        "selected_levels": list(spec["setup"]["selected_levels"]),
        "signal_count": int(len(signal_result["signals"])),
        "trade_count": int(len(backtest_result["trades"])),
        "stages": rows,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": sys.executable,
        },
    }


def run_cai_cold_path_benchmarks(
    *,
    kinds: tuple[CAI_FIXTURE_KIND, ...] = ("small", "realistic"),
    repeats: int = 5,
) -> list[dict[str, Any]]:
    """Return cold-path measurements for one or more fixture sizes."""
    return [measure_cai_cold_path(kind=kind, repeats=repeats) for kind in kinds]


def _print_report(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        print(
            f"fixture={report['fixture']} bars={report['bar_count']} "
            f"signals={report['signal_count']} trades={report['trade_count']}"
        )
        for stage in report["stages"]:
            print(
                f"  {stage['stage']}: median_ms={stage['median_ms']} "
                f"p95_ms={stage['p95_ms']} poc={stage['poc_windows']}"
            )
        print(f"  environment={report['environment']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=("small", "realistic", "both"),
        default="both",
        help="Which CAI fixture size(s) to measure.",
    )
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    selected: tuple[CAI_FIXTURE_KIND, ...]
    if args.fixture == "both":
        selected = ("small", "realistic")
    else:
        selected = (args.fixture,)  # type: ignore[assignment]
    _print_report(run_cai_cold_path_benchmarks(kinds=selected, repeats=args.repeats))
