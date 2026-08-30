"""SO1 Study Observatory — read-only corpus fact table.

Concatenates existing ``results_index.csv`` ⟕ ``study.expansion.json`` plus
StudySpec locks across SV1 catalog hits. Does not call ``report_study``,
``rollup_study``, or ``run_study``. Does not unzip cell bundles.

This module must not import Streamlit, Plotly, ``execute``, ``cli_study``,
``thesistester.cli``, ``launch``, ``builder``, ``promote``, ``tools``, or
``rollup``.
"""

from __future__ import annotations

import json
import math
import numbers
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.report import RESULTS_INDEX, format_partner_levels, otf_canonical_key
from thesistester.study.viewer import (
    STUDY_SPEC_FILENAME,
    StudyCatalogEntry,
    catalog_cache_stamp,
    default_study_viewer_roots,
    discover_study_dirs,
)

EXPANSION_JSON = "study.expansion.json"
LEDGER_JSON = "study.ledger.json"

OBSERVATORY_HONESTY = (
    "Descriptive screen of completed study cells. Ranking many cells is "
    "multiple-testing, not a validated edge. Sort is within a comparability "
    "cohort unless you break the lock. Catalog membership is not a quality score."
)

SORT_ALLOW_LIST: frozenset[str] = frozenset(
    {
        "expectancy_r",
        "profit_factor",
        "win_rate",
        "trade_count",
        "max_drawdown_r",
        "study_name",
        "run_name",
        "status",
    }
)
_SORT_DESC_DEFAULT: frozenset[str] = frozenset(
    {"expectancy_r", "profit_factor", "win_rate", "trade_count"}
)
_SORT_ASC_DEFAULT: frozenset[str] = frozenset(
    {"max_drawdown_r", "study_name", "run_name", "status"}
)

COHORT_FIELDS: tuple[str, ...] = (
    "instrument",
    "dataset_id",
    "ingestion_mode",
    "commission_per_side",
    "slippage_ticks",
    "stop_loss_ticks",
    "take_profit_ticks",
    "trigger",
    "trigger_timeframe",
    "tolerance_ticks",
    "flat_by_session_close",
    "confluence_mode",
    "min_valid_confluences",
    "exposure_policy",
)

CLI_COLUMNS: tuple[str, ...] = (
    "study_name",
    "run_name",
    "instrument",
    "setup_kind",
    "trade_count",
    "expectancy_r",
    "profit_factor",
    "status",
    "sample_class",
)

LOCKED_FRAME_COLUMNS: tuple[str, ...] = (
    "study_dir",
    "study_name",
    "study_identity_hash",
    "run_name",
    "bundle_path",
    "status",
    "instrument",
    "dataset_id",
    "ingestion_mode",
    "trigger",
    "trigger_timeframe",
    "confluence_mode",
    "direction",
    "tolerance_ticks",
    "min_valid_confluences",
    "stop_loss_ticks",
    "take_profit_ticks",
    "commission_per_side",
    "slippage_ticks",
    "flat_by_session_close",
    "exposure_policy",
    "min_trades",
    "primary_metric",
    "lineage_parent",
    "lineage_admit_value",
    "factor_core_level",
    "factor_partner_levels",
    "trade_count",
    "expectancy_r",
    "profit_factor",
    "win_rate",
    "max_drawdown_r",
    "total_r",
    "profit_factor_source",
    "factors_joined",
    "setup_kind",
    "sample_class",
    "cohort_key",
    "lens_hint",
)

STUDIES_COLUMNS: tuple[str, ...] = (
    "study_dir",
    "study_name",
    "study_identity_hash",
    "run_count",
    "ok",
    "failed",
    "skipped",
    "running",
    "pending",
    "ledger_present",
    "index_present",
    "error",
    "mtime",
)

_STAMP_FILES: tuple[str, ...] = (
    STUDY_SPEC_FILENAME,
    EXPANSION_JSON,
    RESULTS_INDEX,
    LEDGER_JSON,
)

_PROGB_NAME = re.compile(r"^progB_")


class ObservatoryError(ValueError):
    """Raised when an Observatory helper receives an illegal argument."""


@dataclass(frozen=True)
class ObservatoryModel:
    """In-memory corpus projection. Never written to a study dir."""

    frame: pd.DataFrame
    studies: pd.DataFrame
    stamp: Mapping[str, tuple[tuple[str, float], ...]]
    discover_stamp: str


def load_observatory_frame(
    *,
    roots: Sequence[Path] | None = None,
    extra_dirs: Sequence[str | Path] = (),
    prior: ObservatoryModel | None = None,
) -> ObservatoryModel:
    """Discover local studies and concat an index-only cell fact table.

    Rebuilds a directory slice only when that directory's artifact mtimes
    change. ``prior`` is process-memory only (CLI stays stateless).
    """
    resolved_roots = (
        default_study_viewer_roots()
        if roots is None
        else tuple(Path(root).resolve() for root in roots)
    )
    entries = discover_study_dirs(resolved_roots, extra_dirs=extra_dirs)
    discover = catalog_cache_stamp(resolved_roots, extra_dirs)
    prior_slices = _index_prior_slices(prior)

    cell_frames: list[pd.DataFrame] = []
    study_rows: list[dict[str, Any]] = []
    stamps: dict[str, tuple[tuple[str, float], ...]] = {}

    for entry in entries:
        key = str(entry.study_dir)
        stamp = dir_artifact_stamp(entry.study_dir)
        stamps[key] = stamp
        cached = prior_slices.get(key)
        if cached is not None and cached[0] == stamp:
            cached_cells, cached_study = cached[1], cached[2]
            if cached_cells is not None and not cached_cells.empty:
                cell_frames.append(cached_cells.copy())
            study_rows.append(dict(cached_study))
            continue
        cells, study_row = _load_study_slice(entry)
        if cells is not None and not cells.empty:
            cell_frames.append(cells)
        study_rows.append(study_row)

    frame = pd.concat(cell_frames, ignore_index=True) if cell_frames else _empty_frame()
    studies = (
        pd.DataFrame(study_rows, columns=list(STUDIES_COLUMNS))
        if study_rows
        else pd.DataFrame(columns=list(STUDIES_COLUMNS))
    )
    return ObservatoryModel(
        frame=frame,
        studies=studies,
        stamp=MappingProxyType(stamps),
        discover_stamp=discover,
    )


def dir_artifact_stamp(study_dir: Path) -> tuple[tuple[str, float], ...]:
    """Mtime tuples for artifacts that exist (plan §4.3)."""
    items: list[tuple[str, float]] = []
    for name in _STAMP_FILES:
        path = study_dir / name
        try:
            if path.is_file():
                items.append((name, float(path.stat().st_mtime)))
        except OSError:
            continue
    return tuple(items)


def cohort_key_from_values(values: Mapping[str, Any]) -> str:
    """Deterministic ``|``-joined cohort key (plan §4.5). Missing → empty token."""
    return "|".join(_cohort_token(values.get(field)) for field in COHORT_FIELDS)


def sample_class_for(trade_count: Any, min_trades: Any) -> str:
    """``missing_n`` / ``below_min_trades`` / ``interpretable`` (plan §4.4)."""
    count = _coerce_number(trade_count)
    if count is None:
        return "missing_n"
    gate = _coerce_number(min_trades)
    threshold = 30.0 if gate is None else float(gate)
    if count < threshold:
        return "below_min_trades"
    return "interpretable"


def setup_kind_for(*, trigger: Any, trigger_timeframe: Any, confluence_mode: Any) -> str:
    """Display/facet chip. Empty tokens stay empty (not inferred)."""
    return (
        f"{_display_token(trigger)}@{_display_token(trigger_timeframe)}/"
        f"{_display_token(confluence_mode)}"
    )


def lens_hint_for(*, study_name: str, has_admit_lineage: bool) -> str:
    """Best-effort program tag. Not a quality score."""
    if _PROGB_NAME.match(study_name or ""):
        return "program_b"
    if has_admit_lineage:
        return "admit_child"
    return "generic"


def apply_facets(
    frame: pd.DataFrame,
    facets: Mapping[str, Sequence[Any]] | None = None,
) -> pd.DataFrame:
    """Keep rows whose facet columns are in the provided value sets."""
    if frame.empty or not facets:
        return frame.copy()
    mask = pd.Series(True, index=frame.index)
    for column, raw_values in facets.items():
        if column not in frame.columns:
            continue
        allowed = list(raw_values)
        if not allowed:
            continue
        mask = mask & frame[column].isin(allowed)
    return frame.loc[mask].reset_index(drop=True)


def majority_cohort_key(frame: pd.DataFrame) -> str | None:
    """Most common ``cohort_key``; ties break lexicographically (plan §4.5)."""
    if frame.empty or "cohort_key" not in frame.columns:
        return None
    counts = frame["cohort_key"].astype(str).value_counts(dropna=False)
    if counts.empty:
        return None
    top = int(counts.iloc[0])
    tied = sorted(str(key) for key, count in counts.items() if int(count) == top)
    return tied[0] if tied else None


def sort_observatory_frame(
    frame: pd.DataFrame,
    *,
    column: str = "expectancy_r",
    descending: bool | None = None,
    cohort_lock: bool = True,
    cohort_key: str | None = None,
    break_comparability: bool = False,
) -> pd.DataFrame:
    """Sort on the locked allow-list. ``total_r`` is refused."""
    if column not in SORT_ALLOW_LIST:
        raise ObservatoryError(
            f"Sort column {column!r} is not allowed. "
            f"Allow-list: {', '.join(sorted(SORT_ALLOW_LIST))}."
        )
    if frame.empty:
        return frame.copy()
    descending_flag = _default_descending(column) if descending is None else bool(descending)
    if (not cohort_lock) or break_comparability or "cohort_key" not in frame.columns:
        return _sort_subset(frame, column, descending_flag).reset_index(drop=True)
    active = cohort_key if cohort_key is not None else majority_cohort_key(frame)
    if active is None:
        return _sort_subset(frame, column, descending_flag).reset_index(drop=True)
    locked = frame.loc[frame["cohort_key"].astype(str) == str(active)]
    rest = frame.loc[frame["cohort_key"].astype(str) != str(active)]
    ordered = [
        _sort_subset(locked, column, descending_flag),
        _sort_subset(rest, ["study_name", "run_name"], False),
    ]
    return pd.concat(ordered, ignore_index=True)


def unique_facet_values(frame: pd.DataFrame, column: str) -> list[Any]:
    """Sorted unique non-null values for a facet column."""
    if frame.empty or column not in frame.columns:
        return []
    seen: set[str] = set()
    values: list[Any] = []
    for value in frame[column].tolist():
        if value is None or _is_na(value):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
    return sorted(values, key=lambda item: str(item))


def displayed_min_trades(frame: pd.DataFrame) -> float | None:
    """Majority ``min_trades`` in *frame*; ties break to the smaller value."""
    if frame.empty or "min_trades" not in frame.columns:
        return None
    counts: dict[float, int] = {}
    for raw in frame["min_trades"].tolist():
        number = _coerce_number(raw)
        if number is None:
            continue
        counts[number] = counts.get(number, 0) + 1
    if not counts:
        return None
    top = max(counts.values())
    tied = sorted(value for value, count in counts.items() if count == top)
    return tied[0]


def format_observatory_table(frame: pd.DataFrame) -> str:
    """Stable text table for ``study observatory`` (no JSON schema)."""
    if frame.empty:
        return "No study cells found under results/studies/ or out/."
    display = frame.reindex(columns=list(CLI_COLUMNS))
    rows: list[tuple[str, ...]] = []
    for record in display.to_dict(orient="records"):
        rows.append(tuple(_cli_cell(record.get(column)) for column in CLI_COLUMNS))
    widths = [len(column) for column in CLI_COLUMNS]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(CLI_COLUMNS))]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)


def observatory_cli_frame(model: ObservatoryModel) -> pd.DataFrame:
    """Deterministic CLI order: ``study_name``, ``run_name``."""
    if model.frame.empty:
        return model.frame.copy()
    return model.frame.sort_values(["study_name", "run_name"], kind="mergesort").reset_index(
        drop=True
    )


def _index_prior_slices(
    prior: ObservatoryModel | None,
) -> dict[str, tuple[tuple[tuple[str, float], ...], pd.DataFrame | None, dict[str, Any]]]:
    if prior is None:
        return {}
    out: dict[str, tuple[tuple[tuple[str, float], ...], pd.DataFrame | None, dict[str, Any]]] = {}
    studies = prior.studies
    if studies.empty or "study_dir" not in studies.columns:
        return {}
    frame = prior.frame
    for record in studies.to_dict(orient="records"):
        key = str(record.get("study_dir") or "")
        if not key:
            continue
        stamp = prior.stamp.get(key)
        if stamp is None:
            continue
        cells = None
        if not frame.empty and "study_dir" in frame.columns:
            slice_frame = frame.loc[frame["study_dir"].astype(str) == key]
            if not slice_frame.empty:
                cells = slice_frame.reset_index(drop=True).copy()
        out[key] = (tuple(stamp), cells, dict(record))
    return out


def _load_study_slice(
    entry: StudyCatalogEntry,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    study_row = _study_row_from_entry(entry, error=None)
    try:
        locks, has_admit = _read_spec_locks(entry.study_dir)
    except Exception as exc:  # noqa: BLE001 — one corrupt spec must not fail the corpus
        study_row["error"] = f"spec: {exc}"
        return None, study_row
    study_row["study_name"] = locks.get("study_name") or entry.study_name
    if locks.get("study_identity_hash"):
        study_row["study_identity_hash"] = locks["study_identity_hash"]
    index_path = entry.study_dir / RESULTS_INDEX
    if not index_path.is_file():
        return None, study_row
    try:
        index = _read_results_index(index_path)
    except Exception as exc:  # noqa: BLE001 — corrupt index isolated to this dir
        study_row["error"] = f"index: {exc}"
        return None, study_row
    try:
        factor_map = _read_factor_map(entry.study_dir)
        if locks.get("study_identity_hash") is None:
            identity = _expansion_identity_hash(entry.study_dir)
            if identity:
                study_row["study_identity_hash"] = identity
                locks["study_identity_hash"] = identity
        cells = _join_index_rows(entry, index, factor_map, locks, has_admit)
    except Exception as exc:  # noqa: BLE001 — flatten/join must not fail the corpus
        study_row["error"] = f"join: {exc}"
        return None, study_row
    return cells, study_row


def _study_row_from_entry(entry: StudyCatalogEntry, *, error: str | None) -> dict[str, Any]:
    return {
        "study_dir": str(entry.study_dir),
        "study_name": entry.study_name,
        "study_identity_hash": entry.study_identity_hash,
        "run_count": entry.run_count,
        "ok": entry.ok,
        "failed": entry.failed,
        "skipped": entry.skipped,
        "running": entry.running,
        "pending": entry.pending,
        "ledger_present": entry.ledger_present,
        "index_present": entry.index_present,
        "error": error,
        "mtime": entry.mtime,
    }


def _read_spec_locks(study_dir: Path) -> tuple[dict[str, Any], bool]:
    spec_path = study_dir / STUDY_SPEC_FILENAME
    if not spec_path.is_file():
        raise ObservatoryError(f"Missing {STUDY_SPEC_FILENAME}")
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ObservatoryError(f"{STUDY_SPEC_FILENAME} must be a mapping")
    study = payload.get("study")
    if not isinstance(study, Mapping):
        raise ObservatoryError(f"{STUDY_SPEC_FILENAME} missing study mapping")
    dataset = study.get("dataset") if isinstance(study.get("dataset"), Mapping) else {}
    constants = study.get("constants") if isinstance(study.get("constants"), Mapping) else {}
    backtest = constants.get("backtest") if isinstance(constants.get("backtest"), Mapping) else {}
    report = study.get("report") if isinstance(study.get("report"), Mapping) else {}
    factors = study.get("factors") if isinstance(study.get("factors"), Mapping) else {}
    lineage = study.get("lineage") if isinstance(study.get("lineage"), Mapping) else None
    admit = lineage.get("admit") if isinstance(lineage, Mapping) else None
    has_admit = isinstance(admit, Mapping)
    parent = "—"
    admit_value: Any = None
    if isinstance(lineage, Mapping):
        raw_parent = lineage.get("parent_output_dir")
        if isinstance(raw_parent, str) and raw_parent.strip():
            parent = Path(raw_parent.strip()).name or "—"
        if has_admit:
            admit_value = admit.get("value")
    min_trades = report.get("min_trades")
    if _coerce_number(min_trades) is None:
        min_trades = 30
    primary = report.get("primary_metric") or "expectancy_r"
    locks = {
        "study_name": str(study.get("name") or study_dir.name),
        "study_identity_hash": None,
        "instrument": dataset.get("instrument"),
        "ingestion_mode": dataset.get("ingestion_mode"),
        "direction": constants.get("direction"),
        "tolerance_ticks": constants.get("tolerance_ticks"),
        "min_valid_confluences": constants.get("min_valid_confluences"),
        "stop_loss_ticks": backtest.get("stop_loss_ticks"),
        "take_profit_ticks": backtest.get("take_profit_ticks"),
        "commission_per_side": backtest.get("commission_per_side"),
        "slippage_ticks": backtest.get("slippage_ticks"),
        "flat_by_session_close": backtest.get("flat_by_session_close"),
        "exposure_policy": backtest.get("exposure_policy"),
        "min_trades": min_trades,
        "primary_metric": primary,
        "trigger": _singleton_factor(factors.get("trigger")),
        "trigger_timeframe": _singleton_factor(factors.get("trigger_timeframe")),
        "confluence_mode": _singleton_factor(factors.get("confluence_mode")),
        "lineage_parent": parent,
        "lineage_admit_value": admit_value,
    }
    return locks, has_admit


def _read_results_index(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "run_name" not in frame.columns:
        raise ObservatoryError(f"{RESULTS_INDEX} must include a run_name column")
    frame = frame.copy()
    frame["run_name"] = [_index_run_name(value) for value in frame["run_name"].tolist()]
    return frame


def _read_factor_map(study_dir: Path) -> dict[str, Mapping[str, Any]]:
    path = study_dir / EXPANSION_JSON
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    raw = payload.get("factor_map")
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for name, factors in raw.items():
        if isinstance(factors, Mapping):
            out[str(name)] = factors
    return out


def _expansion_identity_hash(study_dir: Path) -> str | None:
    path = study_dir / EXPANSION_JSON
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("study_identity_hash")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _join_index_rows(
    entry: StudyCatalogEntry,
    index: pd.DataFrame,
    factor_map: Mapping[str, Mapping[str, Any]],
    locks: Mapping[str, Any],
    has_admit: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    index_by_name = {
        str(record["run_name"]): record
        for record in index.to_dict(orient="records")
        if record.get("run_name") is not None and not _is_na(record.get("run_name"))
    }
    for name, record in index_by_name.items():
        factors = factor_map.get(name)
        joined = factors is not None
        try:
            flat = _flatten_factors(factors) if joined else {}
        except (TypeError, ValueError, RecursionError):
            flat = {}
            joined = False
        row = _cell_row(
            entry=entry,
            locks=locks,
            index_row=record,
            flat=flat,
            joined=joined,
            has_admit=has_admit,
        )
        rows.append(row)
    if not rows:
        return _empty_frame()
    frame = pd.DataFrame(rows)
    return _align_frame_columns(frame)


def _cell_row(
    *,
    entry: StudyCatalogEntry,
    locks: Mapping[str, Any],
    index_row: Mapping[str, Any],
    flat: Mapping[str, Any],
    joined: bool,
    has_admit: bool,
) -> dict[str, Any]:
    trigger = _joined_or_lock(flat, "factor_trigger", locks.get("trigger"))
    trigger_tf = _joined_or_lock(flat, "factor_trigger_timeframe", locks.get("trigger_timeframe"))
    mode = _joined_or_lock(flat, "factor_confluence_mode", locks.get("confluence_mode"))
    direction = _joined_or_lock(flat, "factor_direction", locks.get("direction"))
    instrument = index_row.get("instrument")
    if _is_na(instrument) or instrument is None or str(instrument).strip() == "":
        instrument = locks.get("instrument")
    dataset_id = index_row.get("dataset_id")
    if _is_na(dataset_id):
        dataset_id = None
    pf = _coerce_number(index_row.get("profit_factor"))
    wr = _coerce_number(index_row.get("win_rate"))
    trade_count = _coerce_number(index_row.get("trade_count"))
    min_trades = locks.get("min_trades")
    study_name = str(locks.get("study_name") or entry.study_name)
    cohort_values = {
        "instrument": instrument,
        "dataset_id": dataset_id,
        "ingestion_mode": locks.get("ingestion_mode"),
        "commission_per_side": locks.get("commission_per_side"),
        "slippage_ticks": locks.get("slippage_ticks"),
        "stop_loss_ticks": locks.get("stop_loss_ticks"),
        "take_profit_ticks": locks.get("take_profit_ticks"),
        "trigger": trigger,
        "trigger_timeframe": trigger_tf,
        "tolerance_ticks": locks.get("tolerance_ticks"),
        "flat_by_session_close": locks.get("flat_by_session_close"),
        "confluence_mode": mode,
        "min_valid_confluences": locks.get("min_valid_confluences"),
        "exposure_policy": locks.get("exposure_policy"),
    }
    row: dict[str, Any] = {
        "study_dir": str(entry.study_dir),
        "study_name": study_name,
        "study_identity_hash": locks.get("study_identity_hash") or entry.study_identity_hash,
        "run_name": index_row.get("run_name"),
        "bundle_path": index_row.get("bundle_path"),
        "status": index_row.get("status"),
        "instrument": instrument,
        "dataset_id": dataset_id,
        "ingestion_mode": locks.get("ingestion_mode"),
        "trigger": trigger,
        "trigger_timeframe": trigger_tf,
        "confluence_mode": mode,
        "direction": direction,
        "tolerance_ticks": locks.get("tolerance_ticks"),
        "min_valid_confluences": locks.get("min_valid_confluences"),
        "stop_loss_ticks": locks.get("stop_loss_ticks"),
        "take_profit_ticks": locks.get("take_profit_ticks"),
        "commission_per_side": locks.get("commission_per_side"),
        "slippage_ticks": locks.get("slippage_ticks"),
        "flat_by_session_close": locks.get("flat_by_session_close"),
        "exposure_policy": locks.get("exposure_policy"),
        "min_trades": min_trades,
        "primary_metric": locks.get("primary_metric"),
        "lineage_parent": locks.get("lineage_parent") or "—",
        "lineage_admit_value": locks.get("lineage_admit_value"),
        "factor_core_level": flat.get("factor_core_level"),
        "factor_partner_levels": flat.get("factor_partner_levels"),
        "trade_count": trade_count,
        "expectancy_r": _coerce_number(index_row.get("expectancy_r")),
        "profit_factor": pf,
        "win_rate": wr,
        "max_drawdown_r": _coerce_number(index_row.get("max_drawdown_r")),
        "total_r": _coerce_number(index_row.get("total_r")),
        "profit_factor_source": "index" if pf is not None else "missing",
        "factors_joined": joined,
        "setup_kind": setup_kind_for(
            trigger=trigger, trigger_timeframe=trigger_tf, confluence_mode=mode
        ),
        "sample_class": sample_class_for(trade_count, min_trades),
        "cohort_key": cohort_key_from_values(cohort_values),
        "lens_hint": lens_hint_for(study_name=study_name, has_admit_lineage=has_admit),
    }
    for key, value in flat.items():
        if key not in row:
            row[key] = value
    return row


def _flatten_factors(factors: Mapping[str, Any]) -> dict[str, Any]:
    """Same factor columns as ``report._flatten_factors`` (no bundle reads)."""
    flat: dict[str, Any] = {}
    for key, value in factors.items():
        col = f"factor_{key}"
        if key == "partner_levels":
            flat[col] = format_partner_levels(value)
        elif key == "otf":
            _flatten_otf(flat, col, value)
        else:
            flat[col] = value
    return flat


def _flatten_otf(flat: dict[str, Any], col: str, value: Any) -> None:
    """Match Inspect otf strings when valid; never raise on a bad cell."""
    try:
        flat[col] = otf_canonical_key(value)
        flat["factor_otf_enabled"] = bool(
            normalize_otf_filter_config(dict(value) if isinstance(value, Mapping) else value).get(
                "enabled", False
            )
        )
    except (TypeError, ValueError, RecursionError):
        if isinstance(value, Mapping):
            flat[col] = json.dumps(dict(value), sort_keys=True, default=str)
            flat["factor_otf_enabled"] = bool(value.get("enabled", False))
        else:
            flat[col] = "" if value is None or _is_na(value) else str(value)
            flat["factor_otf_enabled"] = False


def _align_frame_columns(frame: pd.DataFrame) -> pd.DataFrame:
    extras = [column for column in frame.columns if column not in LOCKED_FRAME_COLUMNS]
    extras.sort()
    ordered = [column for column in LOCKED_FRAME_COLUMNS if column in frame.columns]
    return frame.loc[:, ordered + extras]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(LOCKED_FRAME_COLUMNS))


def _singleton_factor(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return None
        item = value[0]
        if isinstance(item, (list, tuple, dict)):
            return None
        return item
    if isinstance(value, dict) or value is None or _is_na(value):
        return None
    return value


def _joined_or_lock(flat: Mapping[str, Any], key: str, lock_value: Any) -> Any:
    """§4.4: joined ``factor_*`` if present, else exclusive spec value."""
    if key in flat:
        return flat.get(key)
    return lock_value


def _index_run_name(value: Any) -> Any:
    """Keep factor_map joins stable when pandas upcasts numeric run names."""
    if value is None or _is_na(value):
        return pd.NA
    boxed = _box_scalar(value)
    if boxed is None or _is_na(boxed):
        return pd.NA
    if isinstance(boxed, bool):
        return str(boxed)
    if isinstance(boxed, numbers.Real) and not isinstance(boxed, bool):
        number = float(boxed)
        if math.isnan(number):
            return pd.NA
        if number.is_integer():
            return str(int(number))
        return format(number, ".15g")
    text = str(boxed).strip()
    return text or pd.NA


def _box_scalar(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (bytes, str)):
        try:
            boxed = item()
            if boxed is not value:
                return boxed
        except (ValueError, TypeError, OverflowError, RecursionError):
            return value
    return value


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if value is pd.NA or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number):
            return None
        return number
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        if text.lower() in {"inf", "+inf", "infinity"}:
            return float("inf")
        if text.lower() in {"-inf", "-infinity"}:
            return float("-inf")
        try:
            return float(text)
        except ValueError:
            return None
    boxed = _box_scalar(value)
    if boxed is not value:
        return _coerce_number(boxed)
    return None


def _is_na(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _cohort_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    boxed = _box_scalar(value)
    if boxed is not value:
        return _cohort_token(boxed)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number):
            return ""
        if number.is_integer():
            return str(int(number))
        return format(number, ".15g")
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _display_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    return str(value).strip()


def _cli_cell(value: Any) -> str:
    if value is None or _is_na(value):
        return "—"
    return str(value)


def _default_descending(column: str) -> bool:
    if column in _SORT_DESC_DEFAULT:
        return True
    if column in _SORT_ASC_DEFAULT:
        return False
    return False


def _sort_subset(
    frame: pd.DataFrame,
    columns: str | list[str],
    descending: bool,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    if isinstance(columns, list):
        keys = list(columns)
        ascending: bool | list[bool] = [True] * len(keys)
    else:
        keys = [columns]
        ascending = not descending
    return frame.sort_values(keys, ascending=ascending, na_position="last", kind="mergesort")
