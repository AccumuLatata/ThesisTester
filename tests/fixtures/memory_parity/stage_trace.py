"""§8 full-CSV stage-trace harness (Linux-only, flag off, one process).

Owner addition (binding, not in the plan text): reset ``VmHWM`` by writing
``5`` to ``/proc/self/clear_refs`` immediately after the load-time
``prepare_subtimeframe_conservative_context`` call inside
``_load_15s_primary_experiment_data`` returns — not after ``R_load``.
The wrapper drops the discarded map and runs ``gc.collect()`` before
``clear_refs``, so the reset excludes that map. ``R_pre_prepare.hwm`` is
taken immediately before that prepare call. Consequently ``R_load.hwm``
and every later ``hwm`` start from that reset.

Does not run the 50 replicas (stop after ``R_done``). Non-invasive hooks only.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .capture import isolate_store, locate_full_spec
from .cells import FULL_CELL, rewrite_full_spec_dataset
from .compat import resolve_all_hooks, resolve_hook
from .hooks import (
    API_GENERATE_ALIASES,
    BUNDLE_ALIASES,
    LOAD_ALIASES,
    PREPARE_ALIASES,
    restore_aliases,
    skip_replica_loop,
    wrap_callable,
)

KIB_PER_GIB = 1024.0 * 1024.0
CLEAR_REFS = Path("/proc/self/clear_refs")
STATUS_PATH = Path("/proc/self/status")


class StageTraceError(RuntimeError):
    pass


@dataclass
class Sample:
    rss_kib: float | None = None
    hwm_kib: float | None = None

    @property
    def rss_gib(self) -> float | None:
        return None if self.rss_kib is None else self.rss_kib / KIB_PER_GIB

    @property
    def hwm_gib(self) -> float | None:
        return None if self.hwm_kib is None else self.hwm_kib / KIB_PER_GIB


@dataclass
class TraceState:
    prepare_calls: int = 0
    samples: dict[str, Sample] = field(default_factory=dict)
    reset_after_load_prepare: bool = False


def read_vm() -> tuple[float, float]:
    """Return (VmRSS, VmHWM) in KiB from ``/proc/self/status``."""
    rss: float | None = None
    hwm: float | None = None
    try:
        text = STATUS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise StageTraceError(f"failed to read {STATUS_PATH}: {exc}") from exc
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            rss = float(line.split()[1])
        elif line.startswith("VmHWM:"):
            hwm = float(line.split()[1])
    if rss is None or hwm is None:
        raise StageTraceError("VmRSS/VmHWM missing from /proc/self/status")
    return rss, hwm


def reset_vmhwm() -> None:
    """Write ``5`` to ``/proc/self/clear_refs`` (sets VmHWM back to current RSS)."""
    if not CLEAR_REFS.is_file():
        raise StageTraceError(f"{CLEAR_REFS} is not available (Linux-only trace)")
    try:
        CLEAR_REFS.write_text("5", encoding="ascii")
    except OSError as exc:
        raise StageTraceError(f"failed to reset VmHWM via {CLEAR_REFS}: {exc}") from exc


def collect_and_reset_vmhwm() -> None:
    """gc the discarded load-time map, then reset VmHWM to current RSS."""
    gc.collect()
    reset_vmhwm()


def sample(name: str, state: TraceState, *, collect: bool, rss: bool) -> Sample:
    if collect:
        gc.collect()
    rss_kib: float | None
    hwm_kib: float
    current_rss, current_hwm = read_vm()
    rss_kib = current_rss if rss else None
    hwm_kib = current_hwm
    out = Sample(rss_kib=rss_kib, hwm_kib=hwm_kib)
    state.samples[name] = out
    return out


def _require_linux() -> None:
    if not STATUS_PATH.is_file() or not CLEAR_REFS.is_file():
        raise StageTraceError(
            "§8 stage trace is Linux-only (/proc/self/status and clear_refs required)"
        )


def evaluate_rule_8_1(
    *,
    r_load_rss_gib: float,
    r_signals_rss_gib: float,
    r_ctx_rss_gib: float,
    map_step_gib: float,
) -> dict[str, Any]:
    """First matching §8.1 rule. Thresholds use post-gc rss."""
    if r_load_rss_gib >= 4.0 and map_step_gib < 0.5:
        return {
            "rule": 1,
            "name": "loader_is_the_peak",
            "order": "MW-L before MW1; re-trace after MW-L",
        }
    if r_load_rss_gib >= 2.0 and map_step_gib >= 1.5:
        return {
            "rule": 2,
            "name": "loader_still_resident_map_still_large",
            "order": "MW1, then MW-L, then MW2",
        }
    if r_load_rss_gib <= 1.2 and 1.5 <= map_step_gib <= 3.5 and 5.5 <= r_ctx_rss_gib <= 8.0:
        capacity_blocks = r_signals_rss_gib > 4.5
        return {
            "rule": 3,
            "name": "planned_split",
            "order": "MW1 → MW2; no MW-L",
            "capacity_check_r_signals_rss_gt_4_5": capacity_blocks,
            "capacity_result": (
                "stop_and_revise_before_MW1" if capacity_blocks else "capacity_check_passed"
            ),
        }
    return {
        "rule": 4,
        "name": "anything_else_stops_the_series",
        "order": "stop and revise this plan before coding",
        "r_load_rss_gib": r_load_rss_gib,
        "map_step_gib": map_step_gib,
        "r_ctx_rss_gib": r_ctx_rss_gib,
        "r_signals_rss_gib": r_signals_rss_gib,
    }


def compute_b(*, r_pre_prepare_hwm_gib: float, r_signals_hwm_gib: float) -> float:
    """``B = max(R_pre_prepare.hwm, R_signals.hwm)`` after the prepare reset."""
    return max(r_pre_prepare_hwm_gib, r_signals_hwm_gib)


def make_prepare_wrapper(
    original: Callable[..., Any], state: TraceState
) -> Callable[..., Any]:
    """Wrap load-time prepare: sample, drop the map, then reset VmHWM."""

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        load_time = state.prepare_calls == 0
        if load_time:
            sample("R_pre_prepare", state, collect=False, rss=False)
        result = original(*args, **kwargs)
        state.prepare_calls += 1
        if load_time:
            # Caller discards this return. Drop our reference *before*
            # clear_refs so VmHWM excludes the load-time map.
            result = None
            collect_and_reset_vmhwm()
            state.reset_after_load_prepare = True
            return None
        if state.prepare_calls == 2:
            # First simulate_trades context is alive (we hold ``result``).
            sample("R_ctx", state, collect=True, rss=True)
        return result

    return wrapped


def _install_trace_hooks(state: TraceState) -> list[Any]:
    undo: list[Any] = []

    def prepare_factory(original: Callable[..., Any]) -> Callable[..., Any]:
        return make_prepare_wrapper(original, state)

    def load_factory(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            sample("R_load", state, collect=True, rss=True)
            return result

        return wrapped

    def signals_factory(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            sample("R_signals", state, collect=True, rss=True)
            return result

        return wrapped

    def bundle_factory(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            sample("R_bundle", state, collect=False, rss=True)
            result = original(*args, **kwargs)
            sample("R_done", state, collect=True, rss=True)
            return result

        return wrapped

    undo.extend(wrap_callable(PREPARE_ALIASES, prepare_factory))
    undo.extend(wrap_callable(LOAD_ALIASES, load_factory))
    undo.extend(wrap_callable(API_GENERATE_ALIASES, signals_factory))
    undo.extend(wrap_callable(BUNDLE_ALIASES, bundle_factory))
    return undo


def run_stage_trace(
    *,
    csv_path: Path,
    output_json: Path,
    run_label: str,
    full_spec_path: Path | None = None,
) -> dict[str, Any]:
    _require_linux()
    if sys.platform != "linux":
        raise StageTraceError("§8 stage trace is Linux-only")
    resolve_all_hooks()
    run_study = resolve_hook("thesistester.study.execute", "run_study").value

    work = Path(output_json).resolve().parent / f"stage_trace_work_{run_label}"
    work.mkdir(parents=True, exist_ok=True)
    study_out = work / "study"
    source = Path(full_spec_path) if full_spec_path is not None else locate_full_spec()
    yaml_path = rewrite_full_spec_dataset(source, work / "study.yaml", csv_path)

    state = TraceState()
    undo = _install_trace_hooks(state)
    try:
        with isolate_store(work):
            with skip_replica_loop():
                run_study(
                    yaml_path,
                    output_dir=study_out,
                    workers=1,
                    confirm=False,
                    force=True,
                )
    finally:
        restore_aliases(undo)

    required = ("R_pre_prepare", "R_load", "R_signals", "R_ctx", "R_bundle", "R_done")
    missing = [name for name in required if name not in state.samples]
    if missing:
        raise StageTraceError(
            f"stage-trace missed stop(s) {missing}; prepare_calls={state.prepare_calls} "
            f"reset_after_load_prepare={state.reset_after_load_prepare}"
        )
    if not state.reset_after_load_prepare:
        raise StageTraceError("VmHWM was not reset after the load-time prepare")

    def _gib(name: str, attr: str) -> float:
        value = getattr(state.samples[name], attr)
        if value is None:
            raise StageTraceError(f"{name}.{attr} is missing")
        return float(value)

    r_load_rss = _gib("R_load", "rss_gib")
    r_signals_rss = _gib("R_signals", "rss_gib")
    r_ctx_rss = _gib("R_ctx", "rss_gib")
    map_step = r_ctx_rss - r_signals_rss
    r_pre_hwm = _gib("R_pre_prepare", "hwm_gib")
    r_signals_hwm = _gib("R_signals", "hwm_gib")
    b_value = compute_b(r_pre_prepare_hwm_gib=r_pre_hwm, r_signals_hwm_gib=r_signals_hwm)
    rule = evaluate_rule_8_1(
        r_load_rss_gib=r_load_rss,
        r_signals_rss_gib=r_signals_rss,
        r_ctx_rss_gib=r_ctx_rss,
        map_step_gib=map_step,
    )

    def _pack(name: str) -> dict[str, float | None]:
        item = state.samples[name]
        return {"rss_gib": item.rss_gib, "hwm_gib": item.hwm_gib}

    payload = {
        "run_label": run_label,
        "cell": FULL_CELL.cell_id,
        "linux_only": True,
        "flag": "off",
        "replicas": "skipped_after_R_done",
        "reset": {
            "where": "immediately after load-time prepare_subtimeframe_conservative_context",
            "not_after": "R_load",
            "clear_refs_value": 5,
            "applied": state.reset_after_load_prepare,
        },
        "stops": {name: _pack(name) for name in required},
        "map_step_gib": map_step,
        "B_gib": b_value,
        "B_definition": "max(R_pre_prepare.hwm, R_signals.hwm) after the prepare reset",
        "rule_8_1": rule,
        "prepare_calls": state.prepare_calls,
        "pid": os.getpid(),
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True, help="Full farm Quantower 15s CSV")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--full-spec", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        payload = run_stage_trace(
            csv_path=args.csv,
            output_json=args.output_json,
            run_label=args.run_label,
            full_spec_path=args.full_spec,
        )
    except StageTraceError as exc:
        print(f"STOP AND REPORT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
