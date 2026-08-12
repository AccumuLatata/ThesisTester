"""RS-D2 read-only Studies viewer helpers.

Loads completed study artifacts via ``report_study`` / ``load_ledger``. Does not
execute cells, promote drafts, rewrite overview artifacts, or mutate classic
research session state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from thesistester.persistence.local_store import get_store_root
from thesistester.study.ledger import load_ledger
from thesistester.study.report import StudyReportError, StudyReportResult, report_study

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
    report: StudyReportResult
    ranked_display: pd.DataFrame
    low_n_display: pd.DataFrame
    unresolved_display: pd.DataFrame
    otf_delta_display: pd.DataFrame
    overview_md: str
    overview_csv_text: str


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
    """Load ledger + report for a completed study directory (no writes/backtests)."""
    root = resolve_study_dir(study_dir, roots=roots)
    try:
        # Viewer must not rewrite overview artifacts on a completed study dir.
        report = report_study(root, write_artifacts=False)
    except StudyReportError as exc:
        raise StudyViewerError(str(exc)) from exc

    # Ledger is optional; corrupt JSON must not hard-fail the Studies page.
    try:
        ledger = load_ledger(root)
        ledger_summary = _ledger_status_counts(ledger)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
        ledger = None
        ledger_summary = {}
    if not ledger_summary:
        ledger_summary = _index_status_counts(report.overview)

    identity_hash, run_count, spec_name = _read_identity(root)
    if run_count is None:
        run_count = int(len(report.overview)) if not report.overview.empty else None
    study_name = report.study_name or spec_name or root.name

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
