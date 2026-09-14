"""RS-D2 / SV1 / SV2 / SV5 read-only Studies viewer façade.

C-24 (QI-07-07) splits catalog discovery and ledger/rollup progress into
``viewer_catalog`` / ``viewer_progress``. Public names stay here.

Loads completed study artifacts via ``report_study`` / ``load_ledger``. Does not
execute cells, promote drafts, rewrite overview artifacts, or mutate classic
research session state.

SV3 Plotly charts stay on ``pages/15_Studies.py``. This module must not import
Plotly, Streamlit, or ``observatory``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from thesistester.study.briefing import (
    StudyMoneyBriefing,
    build_study_briefing,
    bundle_missing_caption,
    empty_briefing,
    extract_cell_grid,
    extract_cell_time_of_day,
    resolve_cell_bundle,
)
from thesistester.study.ledger import load_ledger
from thesistester.study.report import (
    RESULTS_INDEX,
    StudyReportError,
    StudyReportResult,
    _bundle_path_within_study,
    _load_report_config,
    _read_bundle_trade_summary,
    report_study,
)
from thesistester.study.viewer_catalog import (
    CATALOG_DISPLAY_CAP,
    CATALOG_SCAN_PREFIXES,
    STUDY_SPEC_FILENAME,
    StudyCatalogEntry,
    StudyViewerError,
    catalog_cache_stamp,
    catalog_load_path,
    default_study_viewer_roots,
    discover_study_dirs,
    format_study_catalog_table,
    is_study_dir,
    resolve_catalog_roots,
    resolve_study_dir,
    split_catalog_scan_paths,
    _read_catalog_parent,
    _read_identity,
)
from thesistester.study.viewer_progress import (
    FAILED_ERROR_PREVIEW_CHARS,
    FAILED_ERROR_PRINT_CAP,
    LAUNCH_LOG_NAME,
    LAUNCH_LOG_TAIL_BYTES,
    ROLLUP_CSV_NAME,
    ROLLUP_MD_NAME,
    TERMINAL_LEDGER_STATUSES,
    StudyLedgerProgress,
    StudyRollupView,
    _cell_ids_with_status,
    _index_status_counts,
    _ledger_status_counts,
    _running_ids_from_overview,
    failed_cell_error_lines,
    failed_cells_frame,
    preview_error_text,
    read_rollup_files,
    summarize_ledger_progress,
    tail_launch_log,
    unique_failed_error_lines,
)

__all__ = [
    "CATALOG_DISPLAY_CAP",
    "CATALOG_SCAN_PREFIXES",
    "CLASSIC_RESEARCH_SESSION_KEYS",
    "FAILED_ERROR_PREVIEW_CHARS",
    "FAILED_ERROR_PRINT_CAP",
    "LAUNCH_LOG_NAME",
    "LAUNCH_LOG_TAIL_BYTES",
    "PEEK_KPI_COLUMNS",
    "RANKED_FACTOR_COLUMNS",
    "ROLLUP_CSV_NAME",
    "ROLLUP_MD_NAME",
    "STUDIES_CATALOG_ENTRIES_KEY",
    "STUDIES_CATALOG_ROOTS_KEY",
    "STUDIES_VIEWER_CACHED_MODEL_DIR_KEY",
    "STUDIES_VIEWER_CACHED_MODEL_KEY",
    "STUDIES_VIEWER_CATALOG_SELECT_KEY",
    "STUDIES_VIEWER_DIR_KEY",
    "STUDIES_VIEWER_PENDING_PATH_KEY",
    "STUDIES_VIEWER_SELECTED_RUN_KEY",
    "STUDY_SPEC_FILENAME",
    "TERMINAL_LEDGER_STATUSES",
    "StudyCatalogEntry",
    "StudyCellPeek",
    "StudyLedgerProgress",
    "StudyRollupView",
    "StudyViewerError",
    "StudyViewerModel",
    "_read_catalog_parent",
    "catalog_cache_stamp",
    "catalog_load_path",
    "default_study_viewer_roots",
    "discover_study_dirs",
    "failed_cell_error_lines",
    "failed_cells_frame",
    "format_study_catalog_table",
    "is_study_dir",
    "load_study_view",
    "peek_run_names",
    "peek_study_cell",
    "peek_zip_bytes",
    "preview_error_text",
    "read_rollup_files",
    "resolve_catalog_roots",
    "resolve_study_dir",
    "split_catalog_scan_paths",
    "study_viewer_model_is_current",
    "summarize_ledger_progress",
    "tail_launch_log",
    "unique_failed_error_lines",
]

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
# The Studies page binds its own copies — do not from-import these names
# there (stale / mid-init viewer raises ImportError and bricks the page).
STUDIES_VIEWER_DIR_KEY = "studies_viewer_study_dir"
STUDIES_VIEWER_CACHED_MODEL_KEY = "studies_viewer_cached_model"
STUDIES_VIEWER_CACHED_MODEL_DIR_KEY = "studies_viewer_cached_model_dir"
STUDIES_CATALOG_ENTRIES_KEY = "studies_catalog_entries"
STUDIES_CATALOG_ROOTS_KEY = "studies_catalog_roots_key"
STUDIES_VIEWER_PENDING_PATH_KEY = "studies_viewer_pending_path"
STUDIES_VIEWER_CATALOG_SELECT_KEY = "studies_viewer_catalog_select"
STUDIES_VIEWER_SELECTED_RUN_KEY = "studies_viewer_selected_run"

PEEK_KPI_COLUMNS: tuple[str, ...] = (
    "status",
    "trade_count",
    "profit_factor",
    "win_rate",
    "max_drawdown_r",
    "best_grid_stop_loss_ticks",
    "best_grid_take_profit_ticks",
    "bundle_path",
    "profit_factor_source",
)
RANKED_FACTOR_COLUMNS: tuple[str, ...] = (
    "factor_partner_levels",
    "factor_trigger",
    "factor_trigger_timeframe",
    "factor_direction",
    "factor_confluence_mode",
)


def _display_scalar(value: Any) -> str:
    if value is None:
        return "—"
    try:
        if value is pd.NA or pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else "—"


def _run_name_text(value: Any) -> str:
    """Stable non-empty run_name, or empty string for null / NaN cells."""
    if value is None:
        return ""
    try:
        if value is pd.NA or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def _overview_row(overview: pd.DataFrame, run_name: str) -> dict[str, Any] | None:
    if overview is None or overview.empty or "run_name" not in overview.columns:
        return None
    match = overview.loc[overview["run_name"].map(_run_name_text) == run_name]
    if match.empty:
        return None
    return {str(col): match.iloc[0][col] for col in match.columns}


def _mapping_ledger_cells(ledger: Mapping[str, Any] | None) -> dict[str, Any]:
    """Shallow copy of mapping ledger cells. Skips corrupt non-mapping values."""
    if not isinstance(ledger, Mapping):
        return {}
    cells = ledger.get("cells")
    if not isinstance(cells, Mapping):
        return {}
    mapped: dict[str, Any] = {}
    for name, cell in cells.items():
        if not isinstance(cell, Mapping):
            continue
        key = _run_name_text(name)
        if key:
            mapped[key] = dict(cell)
    return mapped


def _ledger_cell(cells: Mapping[str, Any] | None, run_name: str) -> Mapping[str, Any] | None:
    if not isinstance(cells, Mapping):
        return None
    cell = cells.get(run_name)
    return cell if isinstance(cell, Mapping) else None


def peek_run_names(overview: pd.DataFrame, ledger: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Union of overview ``run_name`` values and mapping ledger cell keys."""
    names: set[str] = set()
    if overview is not None and not overview.empty and "run_name" in overview.columns:
        names.update(
            text
            for text in (_run_name_text(name) for name in overview["run_name"].tolist())
            if text
        )
    names.update(_mapping_ledger_cells(ledger))
    return tuple(sorted(names))


@dataclass(frozen=True)
class StudyCellPeek:
    """Read-only one-cell Inspect projection. Not a classic-session import."""

    run_name: str
    present: bool
    factors: dict[str, str]
    kpis: dict[str, str]
    ledger_status: str | None
    ledger_error: str | None
    trade_summary: dict[str, Any] | None
    trade_summary_caption: str | None
    zip_path: Path | None
    zip_name: str | None
    best_grid: dict[str, Any] | None
    grid_display: pd.DataFrame
    grid_caption: str | None
    time_of_day: pd.DataFrame
    time_of_day_best: dict[str, str] | None
    time_of_day_caption: str | None


def peek_study_cell(model: StudyViewerModel, run_name: str) -> StudyCellPeek:
    """Index + ledger error + optional zip members (sandboxed).

    Reads ``trade_summary.json``, and when present ``best_grid_result.json`` /
    ``grid_results.parquet`` / ``trades.parquet`` for ToD. Does not hydrate
    classic session keys or unzip equity / signals. Escaping ``bundle_path``
    is refused. Missing zip member is a caption.
    """
    name = str(run_name or "").strip()
    row = _overview_row(model.report.overview, name)
    cell = _ledger_cell(getattr(model, "ledger_cells", None), name)
    present = row is not None or cell is not None
    factors: dict[str, str] = {}
    kpis: dict[str, str] = {}
    if row is not None:
        for col, value in row.items():
            if str(col).startswith("factor_"):
                factors[str(col)] = _display_scalar(value)
        metric = model.report.primary_metric
        for col in (metric, *PEEK_KPI_COLUMNS):
            if col in row:
                kpis[col] = _display_scalar(row[col])
    ledger_status = None
    ledger_error = None
    if cell is not None:
        ledger_status = str(cell.get("status") or "") or None
        if ledger_status == "failed":
            error = cell.get("error")
            ledger_error = "unknown error" if error is None or str(error) == "" else str(error)

    bundle_rel = ""
    if row is not None:
        bundle_rel = _display_scalar(row.get("bundle_path"))
        if bundle_rel == "—":
            bundle_rel = ""
    if not bundle_rel and cell is not None:
        raw_bundle = cell.get("bundle_path")
        if raw_bundle is not None and str(raw_bundle).strip():
            bundle_rel = str(raw_bundle).strip()

    trade_summary = None
    caption = None
    zip_path = None
    zip_name = None
    if not bundle_rel:
        if present:
            caption = "No bundle_path on this cell — peek does not open a zip."
    else:
        resolved = _bundle_path_within_study(model.study_dir, bundle_rel)
        if resolved is None:
            caption = "bundle_path is outside the study directory and was refused."
        elif not resolved.is_file():
            caption = "bundle_path is not a file inside the study directory."
        else:
            zip_path = resolved
            zip_name = resolved.name
            trade_summary = _read_bundle_trade_summary(resolved)
            if trade_summary is None:
                caption = "trade_summary.json is missing from the zip (or unreadable)."
    grid_bundle = resolve_cell_bundle(model.study_dir, bundle_rel or None)
    missing = (
        None
        if grid_bundle is not None
        else bundle_missing_caption(model.study_dir, bundle_rel or None)
    )
    best_grid, grid_display, grid_caption = extract_cell_grid(grid_bundle, missing_caption=missing)
    time_of_day, tod_best, tod_caption = extract_cell_time_of_day(
        grid_bundle, missing_caption=missing
    )
    return StudyCellPeek(
        run_name=name,
        present=present,
        factors=factors,
        kpis=kpis,
        ledger_status=ledger_status,
        ledger_error=ledger_error,
        trade_summary=trade_summary,
        trade_summary_caption=caption,
        zip_path=zip_path,
        zip_name=zip_name,
        best_grid=best_grid,
        grid_display=grid_display,
        grid_caption=grid_caption,
        time_of_day=time_of_day,
        time_of_day_best=tod_best,
        time_of_day_caption=tod_caption,
    )


def peek_zip_bytes(peek: StudyCellPeek, *, study_dir: Path) -> bytes | None:
    """Read sandboxed zip bytes for download. Does not write the study dir."""
    if peek.zip_path is None:
        return None
    root = Path(study_dir).resolve()
    resolved = peek.zip_path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        return None
    return resolved.read_bytes()


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
    failed_cells_display: pd.DataFrame
    unique_error_lines: tuple[str, ...]
    rollup_present: bool
    rollup_display: pd.DataFrame
    rollup_md: str
    launch_log_present: bool
    launch_log_tail: str
    peek_run_names: tuple[str, ...]
    ledger_cells: dict[str, Any]
    briefing: StudyMoneyBriefing


def study_viewer_model_is_current(model: object) -> bool:
    """True when a cached Inspect model has SV2/SV4/SV5 briefing fields."""
    return all(
        hasattr(model, name)
        for name in (
            "failed_cells_display",
            "unique_error_lines",
            "rollup_present",
            "rollup_display",
            "rollup_md",
            "launch_log_present",
            "launch_log_tail",
            "peek_run_names",
            "ledger_cells",
            "briefing",
        )
    )


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

    A readable ledger plus an absent ``results_index.csv`` path (first cell
    still running) yields a ledger-only model: progress is shown, ranked
    tables stay empty. A present path that is not a readable CSV — including
    a directory, parse failure, or missing ``run_name`` — still raises
    ``StudyViewerError``.
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
    if ledger is not None and not index_path.exists():
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
        "best_grid_stop_loss_ticks",
        "best_grid_take_profit_ticks",
        *RANKED_FACTOR_COLUMNS,
        "bundle_path",
        "profit_factor_source",
    ]
    overview_csv_text = report.overview.to_csv(index=False) if not report.overview.empty else ""
    failed_display = failed_cells_frame(ledger)
    unique_lines = unique_failed_error_lines(ledger)
    rollup = read_rollup_files(root)
    log_tail = tail_launch_log(root)
    briefing = (
        empty_briefing(reason="Ledger-only view: briefing waits for results_index.csv.")
        if not report_present
        else build_study_briefing(report, study_dir=root)
    )
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
        failed_cells_display=failed_display,
        unique_error_lines=unique_lines,
        rollup_present=rollup.present,
        rollup_display=rollup.frame,
        rollup_md=rollup.markdown,
        launch_log_present=log_tail is not None,
        launch_log_tail=log_tail or "",
        peek_run_names=peek_run_names(report.overview, ledger),
        ledger_cells=_mapping_ledger_cells(ledger),
        briefing=briefing,
    )
