"""RS-D4 per-cell diagnostic rollup (compose-only).

Aggregates existing walk-forward / validation / overfitting fields from the
study ``results_index`` and per-cell research bundles. Does **not** invent
cross-cell PBO/DSR/CSCV, and never enables batteries.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from thesistester.study.report import _bundle_path_within_study

RESULTS_INDEX = "results_index.csv"
ROLLUP_CSV = "study.rollup.csv"
ROLLUP_MD = "study.rollup.md"
NOT_RUN = "not_run"
PRESENT = "present"

_INDEX_WFA_KEYS = (
    "wfa_fold_count",
    "wfa_valid_fold_count",
    "wfa_median_test_expectancy_r",
    "wfa_stitched_oos_total_r",
)

ROLLUP_COLUMNS: tuple[str, ...] = (
    "run_name",
    "status",
    "bundle_path",
    "wfa_battery",
    "wfa_fold_count",
    "wfa_valid_fold_count",
    "wfa_median_test_expectancy_r",
    "wfa_stitched_oos_total_r",
    "wfa_status",
    "wfa_stitched_oos_status",
    "validation_battery",
    "validation_trade_count_status",
    "validation_grid_overfit_risk",
    "overfitting_battery",
    "overfitting_available",
    "overfitting_pbo",
    "overfitting_dsr",
)


class StudyRollupError(ValueError):
    """Raised when a study directory cannot be rolled up."""


@dataclass(frozen=True)
class StudyRollupResult:
    """Artifacts produced by ``rollup_study``."""

    frame: pd.DataFrame
    markdown: str
    paths: dict[str, Path]
    study_name: str
    cell_count: int
    wfa_present_count: int
    validation_present_count: int
    overfitting_present_count: int


def _load_results_index(study_dir: Path) -> pd.DataFrame:
    path = study_dir / RESULTS_INDEX
    if not path.is_file():
        raise StudyRollupError(f"Missing {RESULTS_INDEX} under {study_dir}")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, ValueError) as exc:
        raise StudyRollupError(f"Unable to read {path}: {exc}") from exc
    if frame.empty:
        raise StudyRollupError(f"{RESULTS_INDEX} is empty under {study_dir}")
    if "run_name" not in frame.columns:
        raise StudyRollupError(f"{RESULTS_INDEX} must include a run_name column")
    if frame["run_name"].duplicated().any():
        dupes = sorted(
            {str(name) for name in frame.loc[frame["run_name"].duplicated(), "run_name"]}
        )
        preview = ", ".join(dupes[:8])
        suffix = " ..." if len(dupes) > 8 else ""
        raise StudyRollupError(
            f"{RESULTS_INDEX} contains duplicate run_name values: {preview}{suffix}"
        )
    return frame


def _read_study_name(study_dir: Path) -> str:
    spec_path = study_dir / "study.spec.yaml"
    if not spec_path.is_file():
        return study_dir.name
    try:
        import yaml
    except ImportError:
        return study_dir.name
    try:
        payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        return study_dir.name
    if isinstance(payload, Mapping):
        study = payload.get("study")
        if isinstance(study, Mapping):
            name = study.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return study_dir.name


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_null_or_value(value: Any) -> Any:
    return None if _is_missing(value) else value


def _read_zip_json(bundle_path: Path, member: str) -> dict[str, Any] | None:
    if not bundle_path.is_file():
        return None
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            if member not in archive.namelist():
                return None
            raw = json.loads(archive.read(member).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return dict(raw) if isinstance(raw, Mapping) else None


def _walk_forward_summary_from_bundle(bundle_path: Path) -> dict[str, Any] | None:
    meta = _read_zip_json(bundle_path, "walk_forward_meta.json")
    if meta is None:
        return None
    nested = meta.get("walk_forward_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    # Tolerate a flat summary dict.
    if "fold_count" in meta or "status" in meta:
        return dict(meta)
    return None


def _validation_summary_from_bundle(bundle_path: Path) -> dict[str, Any] | None:
    meta = _read_zip_json(bundle_path, "validation_summary.json")
    if meta is None:
        return None
    nested = meta.get("validation_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    if "trade_count" in meta or "grid_overfit" in meta:
        return dict(meta)
    return None


def _overfitting_summary_from_bundle(bundle_path: Path) -> dict[str, Any] | None:
    meta = _read_zip_json(bundle_path, "overfitting_summary.json")
    if meta is None:
        return None
    nested = meta.get("overfitting_summary")
    if isinstance(nested, Mapping):
        return dict(nested)
    if "available" in meta or "pbo" in meta or "deflated_sharpe" in meta:
        return dict(meta)
    return None


def _compose_row(study_dir: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    run_name = row.get("run_name")
    status = row.get("status")
    bundle_rel = row.get("bundle_path")
    out: dict[str, Any] = {
        "run_name": run_name,
        "status": status if not _is_missing(status) else None,
        "bundle_path": bundle_rel if isinstance(bundle_rel, str) and bundle_rel.strip() else None,
        "wfa_battery": NOT_RUN,
        "wfa_fold_count": None,
        "wfa_valid_fold_count": None,
        "wfa_median_test_expectancy_r": None,
        "wfa_stitched_oos_total_r": None,
        "wfa_status": None,
        "wfa_stitched_oos_status": None,
        "validation_battery": NOT_RUN,
        "validation_trade_count_status": None,
        "validation_grid_overfit_risk": None,
        "overfitting_battery": NOT_RUN,
        "overfitting_available": None,
        "overfitting_pbo": None,
        "overfitting_dsr": None,
    }

    index_wfa_present = any(not _is_missing(row.get(key)) for key in _INDEX_WFA_KEYS)
    if index_wfa_present:
        out["wfa_battery"] = PRESENT
        for key in _INDEX_WFA_KEYS:
            out[key] = _as_null_or_value(row.get(key))

    validation_status = _as_null_or_value(row.get("validation_trade_count_status"))
    if validation_status is not None:
        out["validation_battery"] = PRESENT
        out["validation_trade_count_status"] = validation_status

    bundle_path: Path | None = None
    if isinstance(bundle_rel, str) and bundle_rel.strip():
        bundle_path = _bundle_path_within_study(study_dir, bundle_rel)

    if bundle_path is not None:
        wfa_summary = _walk_forward_summary_from_bundle(bundle_path)
        if wfa_summary is not None:
            out["wfa_battery"] = PRESENT
            if out["wfa_fold_count"] is None:
                out["wfa_fold_count"] = _as_null_or_value(wfa_summary.get("fold_count"))
            if out["wfa_valid_fold_count"] is None:
                out["wfa_valid_fold_count"] = _as_null_or_value(wfa_summary.get("valid_fold_count"))
            if out["wfa_median_test_expectancy_r"] is None:
                out["wfa_median_test_expectancy_r"] = _as_null_or_value(
                    wfa_summary.get("median_test_expectancy_r")
                )
            if out["wfa_stitched_oos_total_r"] is None:
                out["wfa_stitched_oos_total_r"] = _as_null_or_value(
                    wfa_summary.get("stitched_oos_total_r")
                )
            out["wfa_status"] = _as_null_or_value(wfa_summary.get("status"))
            out["wfa_stitched_oos_status"] = _as_null_or_value(
                wfa_summary.get("stitched_oos_status")
            )

        validation_summary = _validation_summary_from_bundle(bundle_path)
        if validation_summary is not None:
            out["validation_battery"] = PRESENT
            trade_count = validation_summary.get("trade_count")
            if isinstance(trade_count, Mapping) and out["validation_trade_count_status"] is None:
                out["validation_trade_count_status"] = _as_null_or_value(trade_count.get("status"))
            grid_overfit = validation_summary.get("grid_overfit")
            if isinstance(grid_overfit, Mapping):
                out["validation_grid_overfit_risk"] = _as_null_or_value(
                    grid_overfit.get("risk_level")
                )

        overfitting_summary = _overfitting_summary_from_bundle(bundle_path)
        if overfitting_summary is not None:
            out["overfitting_battery"] = PRESENT
            available = overfitting_summary.get("available")
            out["overfitting_available"] = (
                bool(available) if isinstance(available, bool) else _as_null_or_value(available)
            )
            pbo = overfitting_summary.get("pbo")
            if isinstance(pbo, Mapping):
                out["overfitting_pbo"] = _as_null_or_value(pbo.get("pbo"))
            dsr = overfitting_summary.get("deflated_sharpe")
            if isinstance(dsr, Mapping):
                out["overfitting_dsr"] = _as_null_or_value(dsr.get("dsr"))

    return out


def build_rollup_frame(study_dir: str | Path) -> pd.DataFrame:
    """Compose the per-cell diagnostic table (no artifact writes)."""
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyRollupError(f"Study directory does not exist: {root}")
    index = _load_results_index(root)
    rows = [_compose_row(root, record) for record in index.to_dict(orient="records")]
    frame = pd.DataFrame(rows)
    for key in ROLLUP_COLUMNS:
        if key not in frame.columns:
            frame[key] = None
    return frame.loc[:, list(ROLLUP_COLUMNS)]


def render_rollup_markdown(
    *,
    study_name: str,
    frame: pd.DataFrame,
) -> str:
    """Human/agent markdown with honesty caveats (no proof-of-edge language)."""
    wfa_n = int((frame["wfa_battery"] == PRESENT).sum()) if not frame.empty else 0
    val_n = int((frame["validation_battery"] == PRESENT).sum()) if not frame.empty else 0
    of_n = int((frame["overfitting_battery"] == PRESENT).sum()) if not frame.empty else 0
    lines = [
        f"# Study diagnostic rollup — {study_name}",
        "",
        "## Honesty",
        "",
        "This rollup **composes existing per-cell diagnostics only**. It does not "
        "compute cross-cell PBO, DSR, or CSCV, and it does not prove edge. "
        "Missing batteries appear as `not_run` / null — expected when "
        "`grid` / `validation` / `walk_forward` stay `enabled: false` (study default).",
        "",
        "R15 `overfitting_summary` / `cscv_pbo` require **grid cell trade sequences**. "
        "After promote, opt into survivor-stage batteries with explicit `enabled: true` "
        "flags (never bare `{}`) before expecting dense overfitting columns.",
        "",
        "## Battery coverage",
        "",
        f"- cells={len(frame)}",
        f"- wfa_battery=present: {wfa_n}",
        f"- validation_battery=present: {val_n}",
        f"- overfitting_battery=present: {of_n}",
        "",
        "## Per-cell table",
        "",
    ]
    display_cols = [
        "run_name",
        "status",
        "wfa_battery",
        "wfa_median_test_expectancy_r",
        "validation_battery",
        "validation_trade_count_status",
        "overfitting_battery",
        "overfitting_pbo",
        "overfitting_dsr",
        "bundle_path",
    ]
    present = [col for col in display_cols if col in frame.columns]
    if frame.empty:
        lines.append("_No cells._")
    else:
        header = "| " + " | ".join(present) + " |"
        sep = "| " + " | ".join("---" for _ in present) + " |"
        lines.extend([header, sep])
        for record in frame.to_dict(orient="records"):
            cells = []
            for col in present:
                value = record.get(col)
                if _is_missing(value):
                    cells.append("")
                else:
                    # Keep markdown tables intact when values contain pipes.
                    cells.append(str(value).replace("|", "\\|"))
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def rollup_study(study_dir: str | Path) -> StudyRollupResult:
    """Write ``study.rollup.csv`` / ``study.rollup.md`` for a completed study dir."""
    root = Path(study_dir)
    frame = build_rollup_frame(root)
    study_name = _read_study_name(root)
    markdown = render_rollup_markdown(study_name=study_name, frame=frame)
    csv_path = root / ROLLUP_CSV
    md_path = root / ROLLUP_MD
    frame.to_csv(csv_path, index=False)
    md_path.write_text(markdown if markdown.endswith("\n") else markdown + "\n", encoding="utf-8")
    return StudyRollupResult(
        frame=frame,
        markdown=markdown,
        paths={ROLLUP_CSV: csv_path, ROLLUP_MD: md_path},
        study_name=study_name,
        cell_count=int(len(frame)),
        wfa_present_count=int((frame["wfa_battery"] == PRESENT).sum()) if not frame.empty else 0,
        validation_present_count=(
            int((frame["validation_battery"] == PRESENT).sum()) if not frame.empty else 0
        ),
        overfitting_present_count=(
            int((frame["overfitting_battery"] == PRESENT).sum()) if not frame.empty else 0
        ),
    )
