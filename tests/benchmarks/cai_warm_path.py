"""Informational cold-vs-warm levels-cache timings for CAI-10.

Non-gating: wall times vary by hardware. Correctness continues to rely on
canonical bundle-hash equality (measured here as a boolean, not a threshold).
Used to decide whether a second signal-artifact cache layer is warranted.
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from tests.fixtures.cai_baseline import CAI_FIXTURE_KIND, cai_run_spec, write_cai_bars
from thesistester.api import run_experiment
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash


def _timed_ms(operation, *, repeats: int) -> dict[str, float]:
    samples: list[float] = []
    operation()  # warmup
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1_000)
    ordered = sorted(samples)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[max(0, int(len(samples) * 0.95) - 1)], 3),
    }


def measure_cai_warm_path(
    *,
    kind: CAI_FIXTURE_KIND,
    repeats: int = 3,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare cold vs warm ``read_write`` ``run_experiment`` on one fixture."""
    root = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="cai10_"))
    root.mkdir(parents=True, exist_ok=True)
    store = root / "store"
    bars_path = write_cai_bars(root / f"{kind}_bars.csv", kind=kind)
    spec = cai_run_spec(dataset_path=str(bars_path.resolve()), kind=kind)

    cold_state = run_experiment(
        spec,
        base_directory=root,
        cache_policy="read_write",
        store_root=store,
    )
    cold_hash = canonical_bundle_hash(build_research_bundle(cold_state))

    def _run_warm():
        return run_experiment(
            spec,
            base_directory=root,
            cache_policy="read_write",
            store_root=store,
        )

    warm_timing = _timed_ms(_run_warm, repeats=repeats)
    warm_state = _run_warm()
    warm_hash = canonical_bundle_hash(build_research_bundle(warm_state))

    def _run_cold_bypass():
        return run_experiment(
            spec,
            base_directory=root,
            cache_policy="off",
            store_root=store / "bypass",
        )

    cold_timing = _timed_ms(_run_cold_bypass, repeats=repeats)

    cold_levels_ms = None
    warm_levels_share = None
    # Approximate levels share from cold baseline docs when available; here we
    # report end-to-end only so signal-cache decisions stay evidence-based.
    speedup = None
    if cold_timing["median_ms"] > 0:
        speedup = round(cold_timing["median_ms"] / max(warm_timing["median_ms"], 1e-9), 3)

    signal_cache_recommendation = (
        "defer_signal_cache"
        if (warm_timing["median_ms"] < cold_timing["median_ms"] * 0.7)
        else "revisit_after_further_levels_tuning"
    )
    # If warm is already much faster, levels cache is working; signals are the
    # next candidate only when warm end-to-end remains levels-dominated.
    # Without a stage breakdown here, recommend measuring generate_signals share
    # on warm runs before adding a signal artifact layer.
    if speedup is not None and speedup >= 1.5:
        signal_cache_recommendation = "measure_warm_signal_share_before_second_layer"
    else:
        signal_cache_recommendation = "prioritize_levels_cache_effectiveness_first"

    return {
        "fixture": kind,
        "bar_count": int(len(cold_state["data"])),
        "cold_policy": "off",
        "warm_policy": "read_write",
        "cold_end_to_end": cold_timing,
        "warm_end_to_end": warm_timing,
        "speedup_cold_over_warm": speedup,
        "canonical_bundle_hash_equal": cold_hash == warm_hash,
        "cold_bundle_hash": cold_hash,
        "warm_bundle_hash": warm_hash,
        "cold_cache_outcome": (cold_state.get("cache_provenance") or {}).get("outcome"),
        "warm_cache_outcome": (warm_state.get("cache_provenance") or {}).get("outcome"),
        "signal_cache_recommendation": signal_cache_recommendation,
        "notes": [
            "Informational only — never a CI pass/fail threshold.",
            "Deterministic correctness remains canonical bundle-hash equality.",
            "Signal second-layer cache deferred until warm generate_signals share "
            "is measured after levels-cache warm hits.",
        ],
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "unused_placeholders": {
            "cold_levels_ms": cold_levels_ms,
            "warm_levels_share": warm_levels_share,
        },
    }


def run_cai_warm_path_benchmarks(
    *,
    kinds: tuple[CAI_FIXTURE_KIND, ...] = ("small",),
    repeats: int = 3,
) -> list[dict[str, Any]]:
    return [measure_cai_warm_path(kind=kind, repeats=repeats) for kind in kinds]


def _print_report(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        print(
            f"fixture={report['fixture']} bars={report['bar_count']} "
            f"hash_equal={report['canonical_bundle_hash_equal']} "
            f"speedup={report['speedup_cold_over_warm']}"
        )
        print(
            f"  cold_median_ms={report['cold_end_to_end']['median_ms']} "
            f"warm_median_ms={report['warm_end_to_end']['median_ms']}"
        )
        print(f"  signal_cache_recommendation={report['signal_cache_recommendation']}")
        print(f"  environment={report['environment']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=("small", "realistic", "both"),
        default="small",
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.fixture == "both":
        selected: tuple[CAI_FIXTURE_KIND, ...] = ("small", "realistic")
    else:
        selected = (args.fixture,)  # type: ignore[assignment]
    _print_report(run_cai_warm_path_benchmarks(kinds=selected, repeats=args.repeats))
