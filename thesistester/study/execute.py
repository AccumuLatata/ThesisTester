"""Study-owned cell execution loop (RS3).

Uses ``run_experiment`` + ``build_research_bundle`` like ``cli._execute_run``,
but writes bundles/index/ledger incrementally and continues after per-cell
failures. Does **not** call ``run_batch``.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from thesistester.api import run_experiment
from thesistester.research_bundle import build_research_bundle, canonical_bundle_hash
from thesistester.study.expand import ExpansionResult, expand_study, write_expansion_artifacts
from thesistester.study.ledger import (
    cells_to_run,
    empty_ledger,
    load_ledger,
    mark_cell,
    record_confirmation,
    save_ledger,
)
from thesistester.study.schema import StudySpecError, load_study_spec

# Metric keys produced by cli._execute_run (without bundle_path).
R18_INDEX_METRIC_KEYS: tuple[str, ...] = (
    "run_name",
    "bundle_hash",
    "dataset_id",
    "instrument",
    "execution_origin",
    "cache_outcome",
    "trade_count",
    "expectancy_r",
    "total_r",
    "max_drawdown_r",
    "best_grid_stop_loss_ticks",
    "best_grid_take_profit_ticks",
    "validation_trade_count_status",
    "wfa_fold_count",
    "wfa_valid_fold_count",
    "wfa_median_test_expectancy_r",
    "wfa_stitched_oos_total_r",
)

STUDY_INDEX_KEYS: tuple[str, ...] = R18_INDEX_METRIC_KEYS + ("bundle_path", "status")


def build_index_row_from_state(
    *,
    name: str,
    state: Mapping[str, Any],
    bundle: bytes,
) -> dict[str, Any]:
    """Build the R18-parity index row (no bundle_path / status)."""
    summary = state.get("trade_summary") or {}
    best = state.get("best_grid_result") or {}
    validation = state.get("validation_summary") or {}
    walk_forward = state.get("walk_forward_summary") or {}
    cache_provenance = state.get("cache_provenance") or {}
    return {
        "run_name": name,
        "bundle_hash": canonical_bundle_hash(bundle),
        "dataset_id": state.get("dataset_id"),
        "instrument": state.get("instrument"),
        "execution_origin": state.get("execution_origin", "study"),
        "cache_outcome": cache_provenance.get("outcome"),
        "trade_count": summary.get("trade_count"),
        "expectancy_r": summary.get("expectancy_r"),
        "total_r": summary.get("total_r"),
        "max_drawdown_r": summary.get("max_drawdown_r"),
        "best_grid_stop_loss_ticks": best.get("stop_loss_ticks"),
        "best_grid_take_profit_ticks": best.get("take_profit_ticks"),
        "validation_trade_count_status": (validation.get("trade_count") or {}).get("status"),
        "wfa_fold_count": walk_forward.get("fold_count"),
        "wfa_valid_fold_count": walk_forward.get("valid_fold_count"),
        "wfa_median_test_expectancy_r": walk_forward.get("median_test_expectancy_r"),
        "wfa_stitched_oos_total_r": walk_forward.get("stitched_oos_total_r"),
    }


def _failed_index_row(name: str) -> dict[str, Any]:
    row = {key: None for key in R18_INDEX_METRIC_KEYS}
    row["run_name"] = name
    row["execution_origin"] = "study"
    return row


def execute_study_cell(
    task: tuple[dict[str, Any], str],
) -> dict[str, Any]:
    """Execute one cell; always return ok/failed payload (never raise to pool)."""
    run_spec, base_directory = task
    name = str(run_spec["name"])
    try:
        state = run_experiment(
            run_spec,
            base_directory=base_directory,
            execution_origin="study",
            cache_policy="read_write",
        )
        bundle = build_research_bundle(state)
        index_row = build_index_row_from_state(name=name, state=state, bundle=bundle)
        return {
            "status": "ok",
            "name": name,
            "bundle": bundle,
            "index_row": index_row,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — study layer must continue
        return {
            "status": "failed",
            "name": name,
            "bundle": None,
            "index_row": _failed_index_row(name),
            "error": f"{type(exc).__name__}: {exc}",
        }


def cost_hint_lines(
    expansion: ExpansionResult,
    *,
    workers: int,
) -> list[str]:
    """Human/agent cost hints for expand/run previews."""
    lines = [
        f"run_count={expansion.run_count}",
        f"workers={workers}",
    ]
    armed: list[str] = []
    for run in expansion.experiment.get("runs") or []:
        for section in ("grid", "validation", "walk_forward"):
            cfg = run.get(section) or {}
            if isinstance(cfg, Mapping) and cfg.get("enabled") is True:
                armed.append(f"{run.get('name')}.{section}")
    if armed:
        preview = ", ".join(armed[:12])
        suffix = " ..." if len(armed) > 12 else ""
        lines.append(
            "WARNING: enabled grid/validation/walk_forward dominates runtime: "
            f"{preview}{suffix}"
        )
    else:
        lines.append("batteries: grid/validation/walk_forward disabled on all cells")
    return lines


def _write_results_index(output_dir: Path, rows_by_name: Mapping[str, Mapping[str, Any]], run_names: list[str]) -> Path:
    ordered: list[dict[str, Any]] = []
    for name in run_names:
        if name in rows_by_name:
            ordered.append(dict(rows_by_name[name]))
        else:
            ordered.append({**_failed_index_row(name), "status": "pending", "bundle_path": None})
    frame = pd.DataFrame(ordered)
    for key in STUDY_INDEX_KEYS:
        if key not in frame.columns:
            frame[key] = None
    frame = frame.loc[:, list(STUDY_INDEX_KEYS)]
    path = output_dir / "results_index.csv"
    frame.to_csv(path, index=False)
    return path


def _load_existing_index_rows(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "results_index.csv"
    if not path.is_file():
        return {}
    frame = pd.read_csv(path)
    if frame.empty or "run_name" not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for record in frame.to_dict(orient="records"):
        name = record.get("run_name")
        if isinstance(name, str):
            rows[name] = dict(record)
    return rows


def prepare_study_expansion(
    study_path: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], ExpansionResult, Path, Path]:
    """Load StudySpec, expand, write artifacts. Returns spec, expansion, out, base."""
    study_path = Path(study_path).resolve()
    spec = load_study_spec(study_path)
    study = spec["study"]
    configured = output_dir or study.get("output_dir") or f"results/studies/{study['name']}"
    out = Path(configured)
    if not out.is_absolute():
        out = (study_path.parent / out).resolve()
    else:
        out = out.resolve()
    expansion = expand_study(spec)
    write_expansion_artifacts(out, normalized_spec=spec, expansion=expansion)
    return spec, expansion, out, study_path.parent


def _apply_cell_result(
    output_dir: Path,
    *,
    run_names: list[str],
    index_by_name: dict[str, dict[str, Any]],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one cell result into ledger + index; return updated ledger."""
    ledger = load_ledger(output_dir)
    if ledger is None:
        raise StudySpecError(f"Missing study ledger under {output_dir}")
    name = str(payload["name"])
    status = str(payload["status"])
    bundle_name = f"{name}.research.zip"

    if status == "ok":
        bundle = payload.get("bundle")
        if not isinstance(bundle, (bytes, bytearray)):
            ledger = mark_cell(
                ledger,
                name,
                status="failed",
                error="ok payload missing bundle bytes",
                finished=True,
            )
            row = dict(payload.get("index_row") or _failed_index_row(name))
            row["status"] = "failed"
            row["bundle_path"] = None
            index_by_name[name] = row
        else:
            (output_dir / bundle_name).write_bytes(bundle)
            ledger = mark_cell(
                ledger,
                name,
                status="ok",
                error=None,
                bundle_path=bundle_name,
                finished=True,
            )
            row = dict(payload["index_row"])
            row["bundle_path"] = bundle_name
            row["status"] = "ok"
            index_by_name[name] = row
    else:
        ledger = mark_cell(
            ledger,
            name,
            status="failed",
            error=str(payload.get("error") or "unknown error"),
            bundle_path=None,
            finished=True,
        )
        row = dict(payload.get("index_row") or _failed_index_row(name))
        row["status"] = "failed"
        row["bundle_path"] = None
        index_by_name[name] = row

    save_ledger(output_dir, ledger)
    _write_results_index(output_dir, index_by_name, run_names)
    return ledger


def run_study(
    study_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    workers: int | None = None,
    confirm: bool = False,
    force: bool = False,
    cell_executor: Callable[[tuple[dict[str, Any], str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Expand, enforce confirm, execute cells with ledger/resume."""
    spec, expansion, out, base_directory = prepare_study_expansion(
        study_path, output_dir=output_dir
    )
    study = spec["study"]
    workers_n = int(workers if workers is not None else study.get("workers", 1))
    if workers_n < 1:
        raise StudySpecError("workers must be >= 1")

    confirm_above = int(study.get("confirm_above_runs", 200))
    if expansion.run_count >= confirm_above and not confirm:
        raise StudySpecError(
            f"Expansion has {expansion.run_count} run(s) >= confirm_above_runs="
            f"{confirm_above}; re-run with --confirm"
        )

    run_names = [str(run["name"]) for run in expansion.experiment["runs"]]
    existing = load_ledger(out)
    if existing is not None:
        prior_hash = existing.get("study_identity_hash")
        if prior_hash != expansion.study_identity_hash and not force:
            raise StudySpecError(
                "Existing study.ledger.json identity hash does not match this "
                "StudySpec expansion; pass --force to re-run, or use a new output_dir"
            )
        ledger = dict(existing)
        ledger["study_identity_hash"] = expansion.study_identity_hash
        cells = dict(ledger.get("cells") or {})
        for name in run_names:
            cells.setdefault(
                name,
                {
                    "status": "pending",
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                    "bundle_path": None,
                },
            )
        if force:
            for name in run_names:
                cell = dict(cells.get(name) or {})
                cell.update(
                    {
                        "status": "pending",
                        "started_at": None,
                        "finished_at": None,
                        "error": None,
                        "bundle_path": None,
                    }
                )
                cells[name] = cell
        ledger["cells"] = cells
    else:
        ledger = empty_ledger(
            study_identity_hash=expansion.study_identity_hash,
            run_names=run_names,
        )

    if confirm:
        ledger = record_confirmation(ledger, run_count=expansion.run_count)
    save_ledger(out, ledger)

    index_by_name = _load_existing_index_rows(out)
    if force:
        for name in run_names:
            index_by_name.pop(name, None)

    todo = cells_to_run(load_ledger(out) or ledger, run_names, force=force)
    runs_by_name = {str(run["name"]): dict(run) for run in expansion.experiment["runs"]}
    executor_fn = cell_executor or execute_study_cell
    tasks = [(runs_by_name[name], str(base_directory)) for name in todo]

    # Mark running before dispatch.
    ledger = load_ledger(out) or ledger
    for name in todo:
        ledger = mark_cell(ledger, name, status="running", started=True)
    save_ledger(out, ledger)

    # Pool only the picklable module-level default executor. Injected
    # cell_executor callables (tests) always run in-process.
    use_pool = (
        workers_n > 1
        and len(tasks) > 1
        and cell_executor is None
        and executor_fn is execute_study_cell
    )
    if not use_pool:
        for task in tasks:
            payload = executor_fn(task)
            _apply_cell_result(
                out,
                run_names=run_names,
                index_by_name=index_by_name,
                payload=payload,
            )
    else:
        with ProcessPoolExecutor(
            max_workers=min(workers_n, len(tasks)),
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            futures = [pool.submit(execute_study_cell, task) for task in tasks]
            for future in as_completed(futures):
                payload = future.result()
                _apply_cell_result(
                    out,
                    run_names=run_names,
                    index_by_name=index_by_name,
                    payload=payload,
                )

    # Final ordered index (includes soft-resumed ok rows).
    ledger = load_ledger(out) or ledger
    cells = ledger.get("cells") or {}
    for name in run_names:
        if name not in index_by_name:
            cell = cells.get(name) or {}
            if cell.get("status") == "ok" and cell.get("bundle_path"):
                # Should have been loaded; synthesize minimal ok row if missing.
                row = _failed_index_row(name)
                row["status"] = "ok"
                row["bundle_path"] = cell.get("bundle_path")
                index_by_name[name] = row
            else:
                row = _failed_index_row(name)
                row["status"] = cell.get("status", "pending")
                row["bundle_path"] = cell.get("bundle_path")
                index_by_name[name] = row
        else:
            index_by_name[name]["status"] = cells.get(name, {}).get(
                "status", index_by_name[name].get("status")
            )

    index_path = _write_results_index(out, index_by_name, run_names)
    return {
        "output_dir": str(out),
        "run_count": expansion.run_count,
        "executed": len(todo),
        "workers": workers_n,
        "ledger_path": str(out / "study.ledger.json"),
        "results_index_path": str(index_path),
        "study_identity_hash": expansion.study_identity_hash,
        "ledger": load_ledger(out),
        "cost_hints": cost_hint_lines(expansion, workers=workers_n),
    }
