"""SV2 Study ledger / rollup / launch-log projections (C-24 / QI-07-07).

Read-only. Does not call ``rollup_study`` or rewrite overview artifacts.
Does not import Streamlit, Plotly, or ``observatory``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

TERMINAL_LEDGER_STATUSES = frozenset({"ok", "failed", "skipped"})
FAILED_ERROR_PRINT_CAP = 5
FAILED_ERROR_PREVIEW_CHARS = 160
LAUNCH_LOG_TAIL_BYTES = 8192
ROLLUP_CSV_NAME = "study.rollup.csv"
ROLLUP_MD_NAME = "study.rollup.md"
LAUNCH_LOG_NAME = "study.launch.log"


def failed_cell_error_lines(
    cells: dict,
    run_names: list[str],
    *,
    max_unique: int = FAILED_ERROR_PRINT_CAP,
) -> list[str]:
    """Return summary lines for unique failed-cell errors (first example each).

    CLI print text is frozen — ``cli_study`` imports this helper.
    """
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in run_names:
        cell = cells.get(name)
        if not isinstance(cell, Mapping):
            continue
        if cell.get("status") != "failed":
            continue
        error = str(cell.get("error") or "unknown error")
        if error in seen:
            continue
        seen.add(error)
        unique.append((name, error))
    if not unique:
        return []
    shown = unique[: max(0, int(max_unique))]
    lines = ["Failed cell errors (unique):"]
    lines.extend(f"  {name}: {error}" for name, error in shown)
    extra = len(unique) - len(shown)
    if extra > 0:
        lines.append(f"  … +{extra} more unique error(s) in study.ledger.json")
    return lines


def failed_cells_frame(ledger: Mapping[str, Any] | None) -> pd.DataFrame:
    """Every ledger cell with ``status=failed`` (``run_name``, ``error``)."""
    columns = ["run_name", "error"]
    if ledger is None:
        return pd.DataFrame(columns=columns)
    cells = ledger.get("cells")
    if not isinstance(cells, Mapping):
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, str]] = []
    for name, cell in cells.items():
        if not isinstance(cell, Mapping):
            continue
        if str(cell.get("status") or "") != "failed":
            continue
        error = cell.get("error")
        text = "unknown error" if error is None or str(error) == "" else str(error)
        rows.append({"run_name": str(name), "error": text})
    rows.sort(key=lambda item: item["run_name"])
    return pd.DataFrame(rows, columns=columns)


def unique_failed_error_lines(
    ledger: Mapping[str, Any] | None,
    *,
    max_unique: int = FAILED_ERROR_PRINT_CAP,
) -> tuple[str, ...]:
    """Caption lines: unique failed-cell errors, capped (same text as CLI)."""
    if ledger is None:
        return ()
    cells = ledger.get("cells")
    if not isinstance(cells, Mapping):
        return ()
    mapping = dict(cells) if not isinstance(cells, dict) else cells
    names = [str(name) for name in mapping]
    return tuple(failed_cell_error_lines(mapping, names, max_unique=max_unique))


def preview_error_text(text: str, *, max_chars: int = FAILED_ERROR_PREVIEW_CHARS) -> str:
    """Truncate a long error for the Inspect table; expander keeps full text."""
    raw = str(text)
    limit = max(0, int(max_chars))
    if len(raw) <= limit:
        return raw
    if limit <= 3:
        return raw[:limit]
    return raw[: limit - 3] + "..."


@dataclass(frozen=True)
class StudyRollupView:
    """Read-only ``study.rollup.*`` projection. Never written by the viewer."""

    present: bool
    frame: pd.DataFrame
    markdown: str


def read_rollup_files(study_dir: Path) -> StudyRollupView:
    """Read existing rollup files. Does not call ``rollup_study``."""
    csv_path = Path(study_dir) / ROLLUP_CSV_NAME
    md_path = Path(study_dir) / ROLLUP_MD_NAME
    if not csv_path.is_file():
        return StudyRollupView(present=False, frame=pd.DataFrame(), markdown="")
    try:
        frame = pd.read_csv(csv_path)
    except (OSError, UnicodeDecodeError, ValueError, pd.errors.ParserError):
        frame = pd.DataFrame()
    markdown = ""
    if md_path.is_file():
        try:
            markdown = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            markdown = ""
    return StudyRollupView(present=True, frame=frame, markdown=markdown)


def tail_launch_log(
    study_dir: Path,
    *,
    max_bytes: int = LAUNCH_LOG_TAIL_BYTES,
) -> str | None:
    """Last ``max_bytes`` of ``study.launch.log``, or ``None`` if absent.

    Decodes UTF-8 with replacement. Streamlit watcher lines are not this file.
    """
    path = Path(study_dir) / LAUNCH_LOG_NAME
    if not path.is_file():
        return None
    limit = max(0, int(max_bytes))
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit:
                handle.seek(-limit, 2)
            data = handle.read(limit)
    except OSError:
        return None
    return data.decode("utf-8", errors="replace")


def _ledger_status_counts(ledger: Mapping[str, Any] | None) -> dict[str, int]:
    if ledger is None:
        return {}
    cells = ledger.get("cells")
    if not isinstance(cells, Mapping):
        return {}
    counts: dict[str, int] = {}
    for cell in cells.values():
        if isinstance(cell, Mapping):
            status = str(cell.get("status") or "unknown")
        else:
            status = "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _index_status_counts(overview: pd.DataFrame) -> dict[str, int]:
    if overview.empty or "status" not in overview.columns:
        return {}
    counts: dict[str, int] = {}
    for status in overview["status"].astype(str).tolist():
        counts[status] = counts.get(status, 0) + 1
    return counts


def _cell_ids_with_status(ledger: Mapping[str, Any] | None, status: str) -> tuple[str, ...]:
    if ledger is None:
        return ()
    cells = ledger.get("cells")
    if not isinstance(cells, Mapping):
        return ()
    names: list[str] = []
    for name, cell in cells.items():
        if isinstance(cell, Mapping):
            cell_status = str(cell.get("status") or "unknown")
        else:
            cell_status = "unknown"
        if cell_status == status:
            names.append(str(name))
    return tuple(sorted(names))


def _running_ids_from_overview(overview: pd.DataFrame) -> tuple[str, ...]:
    if overview is None or overview.empty:
        return ()
    if "status" not in overview.columns or "run_name" not in overview.columns:
        return ()
    mask = overview["status"].astype(str) == "running"
    names = overview.loc[mask, "run_name"].astype(str).tolist()
    return tuple(sorted(name for name in names if name.strip()))


@dataclass(frozen=True)
class StudyLedgerProgress:
    """Cell-status progress for Inspect. Not a quality or ETA metric."""

    done: int
    total: int
    pending: int
    running_count: int
    running_ids: tuple[str, ...]
    in_flight: bool
    fraction: float


def summarize_ledger_progress(
    ledger_summary: Mapping[str, int] | None,
    *,
    run_count: int | None = None,
    running_ids: Sequence[str] = (),
) -> StudyLedgerProgress:
    """Derive done/total progress from ledger (or index) status counts.

    ``done`` is terminal statuses only (``ok`` + ``failed`` + ``skipped``).
    ``total`` is ``max(counted cells, declared run_count)``.
    """
    summary = dict(ledger_summary or {})
    done = 0
    pending = 0
    running_count = 0
    counted = 0
    for status, raw in summary.items():
        try:
            count = int(raw)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        counted += count
        key = str(status)
        if key in TERMINAL_LEDGER_STATUSES:
            done += count
        elif key == "pending":
            pending += count
        elif key == "running":
            running_count += count
    declared = 0
    if isinstance(run_count, int) and not isinstance(run_count, bool) and run_count > 0:
        declared = run_count
    total = max(counted, declared)
    fraction = (done / total) if total else 0.0
    fraction = min(1.0, max(0.0, float(fraction)))
    ids = tuple(str(name) for name in running_ids if str(name).strip())
    running_count = max(running_count, len(ids))
    return StudyLedgerProgress(
        done=done,
        total=total,
        pending=pending,
        running_count=running_count,
        running_ids=ids,
        in_flight=pending > 0 or running_count > 0,
        fraction=fraction,
    )
