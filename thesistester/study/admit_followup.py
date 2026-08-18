"""SAF1 Admit follow-up draft helper.

Selects the briefing NY ``entry_rth_segment`` bucket, maps it to an engine
Admit window, stamps setup + backtest + grid, and builds optional
``study.lineage``. Never executes backtests.

Must not import ``execute``, ``launch``, ``viewer``, ``cli_study``,
``thesistester.cli``, Streamlit, pages, or ``run_batch``.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.entry_window_policy import entry_window_from_bucket
from thesistester.study.briefing import (
    TOD_GROUP_COL,
    extract_cell_time_of_day,
    resolve_cell_bundle,
)
from thesistester.study.schema import RUN_NAME_RE, StudySpecError, validate_study_spec

ADMIT_TOD_GROUP = "entry_rth_segment"
ADMIT_RULE = "briefing_best_avg_r"
ADMIT_TOD_MODE = "auto"


class AdmitFollowupError(ValueError):
    """Raised when an Admit follow-up draft cannot be produced."""


def exchange_tz_for_instrument(instrument: str) -> str:
    """Instrument-table exchange TZ (ES/MNQ → America/New_York). No second clock."""
    token = str(instrument or "").strip()
    inst = INSTRUMENTS.get(token)
    if inst is None:
        raise AdmitFollowupError(
            f"Unknown study.dataset.instrument {token!r}; cannot resolve exchange TZ "
            f"for Admit. Supported: {sorted(INSTRUMENTS)}"
        )
    return str(inst.exchange_tz)


def slugify_admit_bucket(value: str) -> str:
    """Bucket label → study.name slug (``:`` stripped)."""
    slug = str(value).strip().replace(":", "")
    if not slug or not RUN_NAME_RE.fullmatch(slug):
        raise AdmitFollowupError(
            f"Admit bucket {value!r} does not yield a valid study.name slug"
        )
    return slug


def child_study_name(parent_name: str, bucket_value: str) -> str:
    """``{parent}_admit_{slug}`` matching ``study.name`` allow-list."""
    base = str(parent_name or "").strip() or "study"
    name = f"{base}_admit_{slugify_admit_bucket(bucket_value)}"
    if not RUN_NAME_RE.fullmatch(name):
        raise AdmitFollowupError(f"Admit child study.name is invalid: {name!r}")
    return name


def select_admit_bucket(
    frame: pd.DataFrame,
    *,
    min_trades: int,
    group_col: str = ADMIT_TOD_GROUP,
) -> dict[str, Any]:
    """Pick the briefing-best NY bucket; refuse ties and thin samples.

    Sort matches ``briefing._best_tod_bucket`` (prefer non-``sample_warning``,
    ``avg_r`` desc, label asc). SAF1 hard-codes ``entry_rth_segment``.
    """
    if group_col != ADMIT_TOD_GROUP:
        raise AdmitFollowupError(
            f"SAF1 Admit only supports {ADMIT_TOD_GROUP!r}; got {group_col!r}"
        )
    if frame is None or frame.empty or "avg_r" not in frame.columns:
        raise AdmitFollowupError(
            "No time-of-day groups in this cell zip; cannot draft Admit follow-up"
        )
    if group_col not in frame.columns:
        raise AdmitFollowupError(
            f"Time-of-day table is missing {group_col!r}; cannot draft Admit follow-up"
        )
    work = frame.copy()
    work["avg_r"] = pd.to_numeric(work["avg_r"], errors="coerce")
    work = work.loc[work["avg_r"].notna()]
    if work.empty:
        raise AdmitFollowupError(
            "No time-of-day bucket has a numeric avg_r; cannot draft Admit follow-up"
        )
    if "sample_warning" in work.columns:
        solid = work.loc[~work["sample_warning"].fillna(True)]
        if not solid.empty:
            work = solid
    work = work.sort_values(
        ["avg_r", group_col],
        ascending=[False, True],
        kind="mergesort",
    )
    if len(work) >= 2:
        top_r = float(work.iloc[0]["avg_r"])
        next_r = float(work.iloc[1]["avg_r"])
        if top_r == next_r:
            raise AdmitFollowupError(
                "Admit bucket is tied on avg_r; refuse to pick a winner. "
                "Inspect Time Analysis / briefing and choose explicitly later."
            )
    top = work.iloc[0]
    label = str(top.get(group_col) or "").strip()
    if not label or label == "—":
        raise AdmitFollowupError("Admit bucket label is empty; cannot draft follow-up")
    trade_count = pd.to_numeric(top.get("trade_count"), errors="coerce")
    sample_warning = bool(top["sample_warning"]) if "sample_warning" in top.index else False
    n = None if pd.isna(trade_count) else int(trade_count)
    thin = bool(sample_warning or n is None or n < int(min_trades))
    if thin:
        raise AdmitFollowupError(
            f"Admit bucket {label!r} is thin "
            f"(sample_warning={sample_warning}, N={n}, min_trades={min_trades}). "
            "SAF1 refuses thin buckets (--allow-thin is SAF3)."
        )
    return {
        "group": group_col,
        "value": label,
        "avg_r": float(top["avg_r"]),
        "trade_count": n,
        "sample_warning": sample_warning,
        "thin": False,
        "min_trades": int(min_trades),
        "rule": ADMIT_RULE,
    }


def resolve_admit_bundle(
    study_dir: Path,
    bundle_rel: str | None,
) -> Path:
    """Sandbox the selected cell zip inside the parent study dir."""
    bundle = resolve_cell_bundle(Path(study_dir), bundle_rel)
    if bundle is None:
        raise AdmitFollowupError(
            "Selected cell has no readable in-dir research zip; "
            "cannot extract time-of-day for Admit follow-up"
        )
    return bundle


def extract_admit_bucket(
    bundle_path: Path,
    *,
    min_trades: int,
) -> dict[str, Any]:
    """NY ``entry_rth_segment`` best bucket from ``trades.parquet`` (no re-sim)."""
    display, _best, caption = extract_cell_time_of_day(
        Path(bundle_path),
        min_trades=int(min_trades),
    )
    if display is None or display.empty:
        detail = caption or "empty time-of-day table"
        raise AdmitFollowupError(
            f"Cannot extract NY RTH buckets from {Path(bundle_path).name}: {detail}"
        )
    return select_admit_bucket(display, min_trades=int(min_trades))


def admit_window_for_bucket(
    bucket_value: str,
    *,
    exchange_tz: str,
) -> dict[str, Any]:
    """Normalized Admit window for the selected NY RTH segment."""
    try:
        window = entry_window_from_bucket(
            ADMIT_TOD_GROUP,
            bucket_value,
            exchange_tz=exchange_tz,
        )
    except ValueError as exc:
        raise AdmitFollowupError(f"Cannot map Admit bucket to entry_window: {exc}") from exc
    if not isinstance(window, Mapping) or not window.get("enabled"):
        raise AdmitFollowupError("entry_window_from_bucket did not return an enabled Admit window")
    return copy.deepcopy(dict(window))


def stamp_admit_windows(study: dict[str, Any], window: Mapping[str, Any]) -> None:
    """Stamp setup + engine Admit paths. Do not flip grid.enabled."""
    constants = study.get("constants")
    if not isinstance(constants, dict):
        raise AdmitFollowupError("study.constants must be a mapping to stamp Admit windows")
    payload = copy.deepcopy(dict(window))
    constants["entry_window"] = copy.deepcopy(payload)
    backtest = constants.get("backtest")
    if not isinstance(backtest, dict):
        raise AdmitFollowupError("study.constants.backtest is required to stamp Admit")
    backtest["entry_window"] = copy.deepcopy(payload)
    grid = constants.get("grid")
    if isinstance(grid, dict):
        grid["entry_window"] = copy.deepcopy(payload)


def build_admit_lineage(
    *,
    parent_output_dir: Path,
    parent_identity_hash: str,
    parent_run_name: str,
    bucket: Mapping[str, Any],
) -> dict[str, Any]:
    """Closed ``study.lineage`` mapping (SAF1 emits ``briefing_best_avg_r``)."""
    identity = str(parent_identity_hash or "").strip()
    run_name = str(parent_run_name or "").strip()
    if not identity:
        raise AdmitFollowupError("parent_identity_hash is required for study.lineage")
    if not run_name:
        raise AdmitFollowupError("parent_run_name is required for study.lineage")
    return {
        "parent_output_dir": Path(parent_output_dir).resolve().as_posix(),
        "parent_identity_hash": identity,
        "parent_run_name": run_name,
        "admit": {
            "group": str(bucket["group"]),
            "value": str(bucket["value"]),
            "rule": str(bucket.get("rule") or ADMIT_RULE),
            "min_trades": int(bucket["min_trades"]),
            "thin": bool(bucket.get("thin", False)),
        },
    }


def apply_admit_followup(
    draft: Mapping[str, Any],
    *,
    parent_study_dir: Path,
    parent_study_name: str,
    parent_identity_hash: str,
    parent_run_name: str,
    bundle_rel: str | None,
    min_trades: int,
    instrument: str,
) -> dict[str, Any]:
    """Post-pass: stamp Admit windows + lineage + child identity; re-validate."""
    root = Path(parent_study_dir).resolve()
    bundle = resolve_admit_bundle(root, bundle_rel)
    bucket = extract_admit_bucket(bundle, min_trades=int(min_trades))
    exchange_tz = exchange_tz_for_instrument(instrument)
    window = admit_window_for_bucket(str(bucket["value"]), exchange_tz=exchange_tz)

    payload = copy.deepcopy(dict(draft))
    study = payload.get("study")
    if not isinstance(study, dict):
        raise AdmitFollowupError("Admit follow-up draft is missing study mapping")

    stamp_admit_windows(study, window)
    child_name = child_study_name(parent_study_name, str(bucket["value"]))
    child_output = f"results/studies/{child_name}"
    if Path(child_output).resolve() == root:
        raise AdmitFollowupError(
            "Admit child output_dir must not reuse the parent study directory"
        )
    study["name"] = child_name
    study["output_dir"] = child_output
    study["lineage"] = build_admit_lineage(
        parent_output_dir=root,
        parent_identity_hash=parent_identity_hash,
        parent_run_name=parent_run_name,
        bucket=bucket,
    )
    prior = str(study.get("description") or "").strip()
    admit_note = (
        f"Admit follow-up of {root.as_posix()} cell {parent_run_name} "
        f"({ADMIT_TOD_GROUP}={bucket['value']}). Constrained re-sim (Focus ≠ Admit), "
        "not a new screen. Engine path is constants.backtest.entry_window "
        "(and grid.entry_window when grid is present)."
    )
    study["description"] = f"{prior} {admit_note}".strip() if prior else admit_note

    try:
        return validate_study_spec(payload)
    except StudySpecError as exc:
        raise AdmitFollowupError(f"Admit follow-up draft failed StudySpec validation: {exc}") from exc
