"""RS-D2 read-only Studies viewer helpers.

Loads completed study artifacts via ``report_study`` / ``load_ledger``. Does not
execute cells, promote drafts, rewrite overview artifacts, or mutate classic
research session state.

Inspect progress is derived from the already-loaded ledger / overview counts
(``ok`` + ``failed`` + ``skipped`` over ``run_count``). It is not a quality
metric, ETA, or job queue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from thesistester.persistence.local_store import get_store_root
from thesistester.study.ledger import load_ledger
from thesistester.study.report import (
    RESULTS_INDEX,
    StudyReportError,
    StudyReportResult,
    _load_report_config,
    report_study,
)

TERMINAL_LEDGER_STATUSES = frozenset({"ok", "failed", "skipped"})

CLASSIC_RESEARCH_SESSION_KEYS = frozenset(
    {
        "data",
        "levels",
        "session_levels",
        "levels_settings",
        "setup",
        "signals",
        "zones",
        "trades",
        "trade_summary",
        "backtest_config",
        "grid_results",
        "best_grid_result",
        "validation_summary",
        "walk_forward_summary",
    }
)

# Studies page may persist only these keys (not classic research keys).
STUDIES_VIEWER_DIR_KEY = "studies_viewer_study_dir"
# Cached StudyViewerModel so Streamlit tab/widget reruns do not re-aggregate.
STUDIES_VIEWER_CACHED_MODEL_KEY = "studies_viewer_cached_model"
STUDIES_VIEWER_CACHED_MODEL_DIR_KEY = "studies_viewer_cached_model_dir"


class StudyViewerError(ValueError):
    """Raised when a study directory cannot be loaded for the viewer."""


def default_study_viewer_roots() -> tuple[Path, ...]:
    """Trusted local roots: repo cwd + ThesisTester store (assistant parity)."""
    return (Path.cwd().resolve(), get_store_root().resolve())


def resolve_study_dir(
    raw: str | Path,
    *,
    roots: Sequence[Path] | None = None,
) -> Path:
    """Resolve ``raw`` and refuse paths outside ``roots`` when provided."""
    if isinstance(raw, str) and not raw.strip():
        raise StudyViewerError("Study output directory path is required.")
    candidate = Path(raw).expanduser().resolve()
    allowed = tuple(Path(root).resolve() for root in (roots if roots is not None else ()))
    if allowed and not any(candidate.is_relative_to(root) for root in allowed):
        raise StudyViewerError(
            "Study path is outside the trusted local roots "
            f"(cwd and store). Resolved path: {candidate}"
        )
    if not candidate.is_dir():
        raise StudyViewerError(f"Study directory does not exist: {candidate}")
    return candidate


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


def _read_identity(study_dir: Path) -> tuple[str | None, int | None, str | None]:
    """Return (study_identity_hash, run_count, study_name) best-effort."""
    identity_hash: str | None = None
    run_count: int | None = None
    study_name: str | None = None
    expansion_path = study_dir / "study.expansion.json"
    if expansion_path.is_file():
        try:
            payload = json.loads(expansion_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, Mapping):
            raw_hash = payload.get("study_identity_hash")
            if isinstance(raw_hash, str) and raw_hash.strip():
                identity_hash = raw_hash.strip()
            raw_count = payload.get("run_count")
            if isinstance(raw_count, int) and not isinstance(raw_count, bool):
                run_count = raw_count
            factor_map = payload.get("factor_map")
            if run_count is None and isinstance(factor_map, Mapping):
                run_count = len(factor_map)
    spec_path = study_dir / "study.spec.yaml"
    if spec_path.is_file():
        try:
            import yaml

            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            spec = None
        if isinstance(spec, Mapping):
            study = spec.get("study")
            if isinstance(study, Mapping):
                name = study.get("name")
                if isinstance(name, str) and name.strip():
                    study_name = name.strip()
    return identity_hash, run_count, study_name


@dataclass(frozen=True)
class StudyViewerModel:
    """Read-only snapshot for the Streamlit Studies page."""

    study_dir: Path
    study_name: str
    study_identity_hash: str | None
    run_count: int | None
    ledger_summary: dict[str, int]
    ledger_present: bool
    report_present: bool
    ledger_progress: StudyLedgerProgress
    report: StudyReportResult
    ranked_display: pd.DataFrame
    low_n_display: pd.DataFrame
    unresolved_display: pd.DataFrame
    otf_delta_display: pd.DataFrame
    overview_md: str
    overview_csv_text: str


def _report_settings_from_spec(study_dir: Path) -> tuple[str, int, str]:
    """Best-effort ``study.report`` fields for a ledger-only Inspect view."""
    try:
        cfg = _load_report_config(study_dir)
    except StudyReportError:
        return "expectancy_r", 30, "warn"
    report = cfg.get("report") if isinstance(cfg, Mapping) else None
    if not isinstance(report, Mapping):
        return "expectancy_r", 30, "warn"
    primary = str(report.get("primary_metric") or "expectancy_r")
    try:
        min_trades = int(report.get("min_trades", 30))
    except (TypeError, ValueError):
        min_trades = 30
    multiple = str(report.get("multiple_testing") or "warn")
    return primary, min_trades, multiple


def _placeholder_report(
    *,
    study_name: str,
    primary_metric: str = "expectancy_r",
    min_trades: int = 30,
    multiple_testing: str = "warn",
) -> StudyReportResult:
    """Empty report when ``results_index.csv`` is not written yet (in-flight)."""
    empty = pd.DataFrame()
    return StudyReportResult(
        overview=empty,
        ranked=empty,
        low_n=empty,
        unresolved=empty,
        group_summaries={},
        otf_delta=empty,
        markdown=(
            "# Ledger-only Inspect view\n\n"
            f"`{RESULTS_INDEX}` is not written yet. Cell progress comes from "
            "`study.ledger.json`. Ranked / low-N / OTF tables stay empty until "
            "Refresh after the index appears.\n"
        ),
        paths={},
        primary_metric=primary_metric,
        min_trades=min_trades,
        multiple_testing=multiple_testing,
        best_cell_suppressed=multiple_testing == "error",
        study_name=study_name,
    )


def _display_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame is None or frame.empty:
        # Preserve caller order but drop duplicates (primary may equal a fixed col).
        ordered = list(dict.fromkeys(columns))
        return pd.DataFrame(columns=ordered)
    present: list[str] = []
    seen: set[str] = set()
    for col in columns:
        if col in frame.columns and col not in seen:
            present.append(col)
            seen.add(col)
    return frame.loc[:, present].copy()


def load_study_view(
    study_dir: str | Path,
    *,
    roots: Sequence[Path] | None = None,
) -> StudyViewerModel:
    """Load ledger + report for a study directory (no writes/backtests).

    A readable ledger plus a missing ``results_index.csv`` file (first cell
    still running) yields a ledger-only model: progress is shown, ranked
    tables stay empty. A present but unreadable or invalid index still
    raises ``StudyViewerError`` — do not treat every index-related report
    error as in-flight.
    """
    root = resolve_study_dir(study_dir, roots=roots)

    # Ledger is optional; corrupt JSON must not hard-fail the Studies page.
    try:
        ledger = load_ledger(root)
        ledger_summary = _ledger_status_counts(ledger)
        running_ids = _cell_ids_with_status(ledger, "running")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
        ledger = None
        ledger_summary = {}
        running_ids = ()

    identity_hash, run_count, spec_name = _read_identity(root)
    index_path = root / RESULTS_INDEX
    if ledger is not None and not index_path.is_file():
        report_present = False
        primary, min_trades, multiple = _report_settings_from_spec(root)
        report = _placeholder_report(
            study_name=spec_name or root.name,
            primary_metric=primary,
            min_trades=min_trades,
            multiple_testing=multiple,
        )
    else:
        try:
            # Viewer must not rewrite overview artifacts on a completed study dir.
            report = report_study(root, write_artifacts=False)
            report_present = True
        except StudyReportError as exc:
            raise StudyViewerError(str(exc)) from exc

    if not ledger_summary:
        ledger_summary = _index_status_counts(report.overview)
    if not running_ids:
        running_ids = _running_ids_from_overview(report.overview)

    if run_count is None:
        run_count = int(len(report.overview)) if not report.overview.empty else None
    study_name = report.study_name or spec_name or root.name
    ledger_progress = summarize_ledger_progress(
        ledger_summary,
        run_count=run_count,
        running_ids=running_ids,
    )

    ranked_cols = [
        "run_name",
        "status",
        "trade_count",
        report.primary_metric,
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "bundle_path",
        "profit_factor_source",
    ]
    overview_csv_text = report.overview.to_csv(index=False) if not report.overview.empty else ""
    return StudyViewerModel(
        study_dir=root,
        study_name=study_name,
        study_identity_hash=identity_hash,
        run_count=run_count,
        ledger_summary=ledger_summary,
        ledger_present=ledger is not None,
        report_present=report_present,
        ledger_progress=ledger_progress,
        report=report,
        ranked_display=_display_columns(report.ranked, ranked_cols),
        low_n_display=_display_columns(
            report.low_n,
            ["run_name", "trade_count", report.primary_metric, "profit_factor", "bundle_path"],
        ),
        unresolved_display=_display_columns(
            report.unresolved,
            [
                "run_name",
                "trade_count",
                report.primary_metric,
                "profit_factor_source",
                "bundle_path",
            ],
        ),
        otf_delta_display=report.otf_delta.copy() if not report.otf_delta.empty else pd.DataFrame(),
        overview_md=report.markdown,
        overview_csv_text=overview_csv_text,
    )
