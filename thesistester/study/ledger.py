"""Study ledger — per-cell status registry for study-owned execution (RS3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

LEDGER_FILENAME = "study.ledger.json"
LEDGER_STATUSES = frozenset({"pending", "running", "ok", "failed", "skipped"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ledger_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / LEDGER_FILENAME


def empty_ledger(*, study_identity_hash: str, run_names: list[str]) -> dict[str, Any]:
    """Create a fresh ledger with all cells pending."""
    return {
        "study_identity_hash": study_identity_hash,
        "confirm": None,
        "cells": {
            name: {
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "error": None,
                "bundle_path": None,
            }
            for name in run_names
        },
    }


def load_ledger(output_dir: str | Path) -> dict[str, Any] | None:
    path = ledger_path(output_dir)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid ledger at {path}: expected mapping")
    return dict(payload)


def save_ledger(output_dir: str | Path, ledger: Mapping[str, Any]) -> Path:
    path = ledger_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(ledger), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def record_confirmation(
    ledger: dict[str, Any],
    *,
    run_count: int,
) -> dict[str, Any]:
    ledger = dict(ledger)
    ledger["confirm"] = {
        "confirmed": True,
        "timestamp": _utc_now(),
        "run_count": int(run_count),
    }
    return ledger


def mark_cell(
    ledger: dict[str, Any],
    run_name: str,
    *,
    status: str,
    error: str | None = None,
    bundle_path: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> dict[str, Any]:
    if status not in LEDGER_STATUSES:
        raise ValueError(f"Invalid ledger status: {status!r}")
    ledger = dict(ledger)
    cells = dict(ledger.get("cells") or {})
    cell = dict(cells.get(run_name) or {})
    cell["status"] = status
    if started:
        cell["started_at"] = _utc_now()
    if finished:
        cell["finished_at"] = _utc_now()
    if error is not None:
        cell["error"] = error
    elif status == "ok":
        cell["error"] = None
    if bundle_path is not None:
        cell["bundle_path"] = bundle_path
    cells[run_name] = cell
    ledger["cells"] = cells
    return ledger


def cells_to_run(
    ledger: Mapping[str, Any],
    run_names: list[str],
    *,
    force: bool,
) -> list[str]:
    """Return run names that still need execution."""
    cells = ledger.get("cells") or {}
    selected: list[str] = []
    for name in run_names:
        if force:
            selected.append(name)
            continue
        cell = cells.get(name) or {}
        if cell.get("status") == "ok":
            continue
        selected.append(name)
    return selected
