"""SO1 Observatory corpus join — index ⟕ expansion ⟕ spec locks (C-24 / QI-07-07).

Read-only. Does not call ``report_study`` / ``rollup_study`` / ``run_study``.
Does not unzip cell bundles. Does not write ``results/studies/``.
Does not import Streamlit, Plotly, ``execute``, or ``cli_study``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.observatory_support import (
    EXPANSION_JSON,
    LOCKED_FRAME_COLUMNS,
    STUDIES_COLUMNS,
    STUDY_SPEC_FILENAME,
    _STAMP_FILES,
    ObservatoryError,
    classify_drift_class,
    cohort_key_from_values,
    lens_hint_for,
    sample_class_for,
    setup_kind_for,
    _coerce_number,
    _index_run_name,
    _is_na,
    _joined_or_lock,
    _singleton_factor,
)
from thesistester.study.report import RESULTS_INDEX, format_partner_levels, otf_canonical_key
from thesistester.study.viewer import (
    StudyCatalogEntry,
    catalog_cache_stamp,
    discover_study_dirs,
)


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
    if roots is None:
        from thesistester.study import observatory as _observatory

        resolved_roots = _observatory.default_study_viewer_roots()
    else:
        resolved_roots = tuple(Path(root).resolve() for root in roots)
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
        "long_trade_count": _coerce_number(index_row.get("long_trade_count")),
        "short_trade_count": _coerce_number(index_row.get("short_trade_count")),
        "long_share": _coerce_number(index_row.get("long_share")),
        "long_expectancy_r": _coerce_number(index_row.get("long_expectancy_r")),
        "short_expectancy_r": _coerce_number(index_row.get("short_expectancy_r")),
        "directional_integrity": (
            None
            if _is_na(index_row.get("directional_integrity"))
            or index_row.get("directional_integrity") is None
            else str(index_row.get("directional_integrity"))
        ),
        "collision_pairs": _coerce_number(index_row.get("collision_pairs")),
        "collision_resolved_long": _coerce_number(index_row.get("collision_resolved_long")),
        "expectancy_r": _coerce_number(index_row.get("expectancy_r")),
        "random_null_expectancy_r": _coerce_number(index_row.get("random_null_expectancy_r")),
        "random_null_std_r": _coerce_number(index_row.get("random_null_std_r")),
        "random_p_value_ge": _coerce_number(index_row.get("random_p_value_ge")),
        "expectancy_minus_null_r": _coerce_number(index_row.get("expectancy_minus_null_r")),
        "drift_class": classify_drift_class(index_row.get("random_p_value_ge")),
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
