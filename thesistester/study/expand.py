"""Deterministic StudySpec → R18 experiment expansion (RS2)."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Mapping

import yaml

from thesistester.api import build_setup, validate_run_spec
from thesistester.cli import EXPERIMENT_SCHEMA_VERSION
from thesistester.setup import normalize_otf_filter_config
from thesistester.study.naming import build_run_name
from thesistester.study.schema import (
    RUN_NAME_RE,
    StudySpecError,
    normalize_study_spec,
    validate_study_spec,
)

# Axes that must appear on every expansion cell (factors or explicit_cells).
# Omitting them previously invented silent defaults (touch / base / global_cluster).
_REQUIRED_CELL_AXES = ("confluence_mode", "trigger", "trigger_timeframe")


@dataclass(frozen=True)
class ExpansionResult:
    """Pure expansion outputs (no filesystem side effects)."""

    experiment: dict[str, Any]
    factor_map: dict[str, dict[str, Any]]
    run_count: int
    study_identity_hash: str


def study_identity_hash(normalized_spec: Mapping[str, Any]) -> str:
    """Hash normalized StudySpec bytes with stable key order."""
    payload = json.dumps(normalized_spec, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_otf(raw: Any) -> dict[str, Any]:
    return normalize_otf_filter_config(dict(raw) if isinstance(raw, Mapping) else raw)


def _factor_axes(factors: Mapping[str, Any]) -> list[str]:
    # YAML/dict insertion order is the cartesian axis order.
    return list(factors.keys())


def _apply_stage_filter(
    factors: Mapping[str, Any],
    include: Mapping[str, Any],
) -> dict[str, list[Any]]:
    filtered: dict[str, list[Any]] = {key: list(values) for key, values in factors.items()}
    for key, allowed in include.items():
        axis_values = filtered[key]
        if key == "otf":
            allowed_norm = [_canonical_otf(item) for item in allowed]
            kept = [value for value in axis_values if _canonical_otf(value) in allowed_norm]
        elif key == "partner_levels":
            allowed_sets = [list(item) for item in allowed]
            kept = [value for value in axis_values if list(value) in allowed_sets]
        else:
            allowed_set = set(allowed)
            kept = [value for value in axis_values if value in allowed_set]
        if not kept:
            raise StudySpecError(f"stage.filter include.{key} matched zero factor values")
        filtered[key] = kept
    return filtered


def _explicit_cells(
    factors: Mapping[str, Any],
    cells: list[Any],
) -> list[dict[str, Any]]:
    axis_keys = _factor_axes(factors)
    out: list[dict[str, Any]] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, Mapping):
            raise StudySpecError(f"stage.cells[{index}] must be a mapping")
        assignment: dict[str, Any] = {}
        for key in axis_keys:
            if key not in cell:
                raise StudySpecError(f"stage.cells[{index}] missing factor key {key!r}")
            value = cell[key]
            if key == "otf":
                assignment[key] = _canonical_otf(value)
            elif key == "partner_levels":
                assignment[key] = list(value)
            else:
                assignment[key] = value
        out.append(assignment)
    return out


def _iter_factor_cells(study: Mapping[str, Any]) -> list[dict[str, Any]]:
    factors = dict(study["factors"])
    stage = study.get("stage")
    if isinstance(stage, Mapping) and stage.get("mode") == "explicit_cells":
        return _explicit_cells(factors, list(stage.get("cells") or []))

    working = {key: list(values) for key, values in factors.items()}
    if isinstance(stage, Mapping) and stage.get("mode") == "filter":
        working = _apply_stage_filter(working, dict(stage.get("include") or {}))

    axes = _factor_axes(working)
    cells: list[dict[str, Any]] = []
    for combo in product(*(working[axis] for axis in axes)):
        assignment = {axis: combo[i] for i, axis in enumerate(axes)}
        if "otf" in assignment:
            assignment["otf"] = _canonical_otf(assignment["otf"])
        if "partner_levels" in assignment:
            assignment["partner_levels"] = list(assignment["partner_levels"])
        cells.append(assignment)
    return cells


def _enabled_section(constants: Mapping[str, Any], section: str) -> dict[str, Any]:
    raw = constants.get(section)
    if isinstance(raw, Mapping):
        out = dict(raw)
        if "enabled" not in out:
            raise StudySpecError(f"constants.{section} missing enabled (should be caught by RS1)")
        return out
    return {"enabled": False}


def _partner_required(mode_rules: Mapping[str, Any]) -> bool:
    rules = mode_rules.get("anchor_rules") or {}
    confluence_rules = rules.get("confluence_rules") or {}
    return str(confluence_rules.get("from_partners", "required")) == "required"


def _build_setup_for_cell(
    *,
    study: Mapping[str, Any],
    run_name: str,
    cell: Mapping[str, Any],
) -> dict[str, Any]:
    constants = dict(study.get("constants") or {})
    dataset = dict(study["dataset"])
    instrument = dataset.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        raise StudySpecError(
            "study.dataset.instrument is required for expansion (setup.instrument must match)"
        )

    for axis in _REQUIRED_CELL_AXES:
        if axis not in cell:
            raise StudySpecError(
                f"Expansion cell missing {axis!r}; declare it under factors "
                f"(or stage.explicit_cells) — expand does not invent silent defaults"
            )

    core = str(cell["core_level"])
    partners = [str(token) for token in cell["partner_levels"]]
    if len(partners) != len(set(partners)):
        raise StudySpecError(f"partner_levels for {run_name} contain duplicate tokens: {partners}")
    if core in partners:
        raise StudySpecError(f"partner_levels for {run_name} must not include core_level {core!r}")
    mode = str(cell["confluence_mode"])
    trigger = str(cell["trigger"])
    trigger_timeframe = str(cell["trigger_timeframe"])
    direction = str(
        cell.get("direction") if "direction" in cell else constants.get("direction", "both")
    )
    tolerance = float(constants.get("tolerance_ticks", 0))
    naked_only = bool(constants.get("naked_only", False))
    naked_requirement = str(constants.get("naked_requirement", "any"))
    trigger_params = dict(constants.get("trigger_params") or {})
    entry_window = constants.get("entry_window")
    min_valid = int(constants.get("min_valid_confluences", 1))
    # OTF axis is optional; omit → disabled filter (not a silent trigger/mode invent).
    otf_filter = _canonical_otf(cell["otf"] if "otf" in cell else {"enabled": False})

    if mode == "global_cluster":
        selected_levels = [core, *partners]
        if len(selected_levels) > 5:
            raise StudySpecError(
                f"global_cluster selected_levels length {len(selected_levels)} exceeds 5"
            )
        min_conf = max_conf = len(selected_levels)
        setup_kwargs: dict[str, Any] = {
            "name": run_name,
            "description": str(study.get("description") or ""),
            "instrument": instrument,
            "selected_levels": selected_levels,
            "tolerance_ticks": tolerance,
            "min_confluences": min_conf,
            "max_confluences": max_conf,
            "naked_only": naked_only,
            "naked_requirement": naked_requirement,
            "trigger": trigger,
            "trigger_timeframe": trigger_timeframe,
            "direction": direction,
            "confluence_mode": "global_cluster",
            "anchor_level": None,
            "confluence_rules": [],
            "min_valid_confluences": 1,
            "trigger_params": trigger_params,
            "otf_filter": otf_filter,
            "entry_window": entry_window,
        }
    elif mode == "anchor_rules":
        required = _partner_required(dict(study.get("mode_rules") or {}))
        confluence_rules = [
            {
                "level": partner,
                "tolerance_ticks": tolerance,
                "required": required,
            }
            for partner in partners
        ]
        if min_valid < 1 or min_valid > len(confluence_rules):
            raise StudySpecError(
                f"min_valid_confluences={min_valid} incompatible with "
                f"{len(confluence_rules)} partner rule(s)"
            )
        # Anchor zones ignore selected_levels; emit honest 1/1 placeholders rather
        # than stamping dual-mode global confluence knobs onto anchor setups.
        setup_kwargs = {
            "name": run_name,
            "description": str(study.get("description") or ""),
            "instrument": instrument,
            "selected_levels": [],
            "tolerance_ticks": tolerance,
            "min_confluences": 1,
            "max_confluences": 1,
            "naked_only": naked_only,
            "naked_requirement": naked_requirement,
            "trigger": trigger,
            "trigger_timeframe": trigger_timeframe,
            "direction": direction,
            "confluence_mode": "anchor_rules",
            "anchor_level": core,
            "confluence_rules": confluence_rules,
            "min_valid_confluences": min_valid,
            "trigger_params": trigger_params,
            "otf_filter": otf_filter,
            "entry_window": entry_window,
        }
    else:
        raise StudySpecError(f"Unsupported confluence_mode for expansion: {mode!r}")

    try:
        return build_setup(setup_kwargs)
    except ValueError as exc:
        raise StudySpecError(f"Invalid expanded setup for {run_name}: {exc}") from exc


def _factor_map_entry(cell: Mapping[str, Any]) -> dict[str, Any]:
    """JSON-serializable factor tags for study.expansion.json."""
    entry: dict[str, Any] = {}
    for key, value in cell.items():
        if key == "otf":
            entry[key] = _canonical_otf(value)
        elif key == "partner_levels":
            entry[key] = list(value)
        else:
            entry[key] = value
    return entry


def expand_study(spec: Mapping[str, Any]) -> ExpansionResult:
    """Expand a StudySpec into an R18 experiment dict + factor map.

    Input may be raw or normalized; it is normalized and validated first.
    """
    normalized = validate_study_spec(normalize_study_spec(spec))
    return _expand_validated(normalized)


def _expand_validated(normalized: Mapping[str, Any]) -> ExpansionResult:
    """Expand an already normalized+validated StudySpec."""
    study = normalized["study"]
    cells = _iter_factor_cells(study)
    if not cells:
        raise StudySpecError("Expansion produced zero runs")

    constants = dict(study.get("constants") or {})
    dataset = dict(study["dataset"])
    levels = dict(study.get("levels") or {})
    raw_backtest = constants.get("backtest")
    if not isinstance(raw_backtest, Mapping) or not raw_backtest:
        raise StudySpecError(
            "study.constants.backtest is required for expansion "
            "(non-empty mapping; never emit bare {})"
        )
    backtest = dict(raw_backtest)
    for key in ("stop_loss_ticks", "take_profit_ticks"):
        if key not in backtest:
            raise StudySpecError(f"study.constants.backtest.{key} is required for expansion")
    grid = _enabled_section(constants, "grid")
    validation = _enabled_section(constants, "validation")
    walk_forward = _enabled_section(constants, "walk_forward")

    runs: list[dict[str, Any]] = []
    factor_map: dict[str, dict[str, Any]] = {}
    seen_names: set[str] = set()

    for index, cell in enumerate(cells):
        run_name = build_run_name(str(study["name"]), index=index, factors=cell)
        if run_name in seen_names:
            raise StudySpecError(f"Duplicate run name generated: {run_name}")
        if not RUN_NAME_RE.fullmatch(run_name):
            raise StudySpecError(f"Invalid generated run name: {run_name!r}")
        seen_names.add(run_name)

        setup = _build_setup_for_cell(study=study, run_name=run_name, cell=cell)
        run: dict[str, Any] = {
            "name": run_name,
            "dataset": copy.deepcopy(dataset),
            "levels": copy.deepcopy(levels),
            "setup": setup,
            "backtest": copy.deepcopy(backtest),
            "grid": copy.deepcopy(grid),
            "validation": copy.deepcopy(validation),
            "walk_forward": copy.deepcopy(walk_forward),
        }
        try:
            validate_run_spec(run)
        except ValueError as exc:
            raise StudySpecError(
                f"Expanded run {run_name!r} failed validate_run_spec: {exc}"
            ) from exc
        runs.append(run)
        factor_map[run_name] = _factor_map_entry(cell)

    experiment = {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "output_dir": study.get("output_dir"),
        "workers": int(study.get("workers", 1)),
        "runs": runs,
    }
    return ExpansionResult(
        experiment=experiment,
        factor_map=factor_map,
        run_count=len(runs),
        study_identity_hash=study_identity_hash(normalized),
    )


def _dump_yaml(payload: Mapping[str, Any]) -> str:
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def write_expansion_artifacts(
    output_dir: str | Path,
    *,
    normalized_spec: Mapping[str, Any],
    expansion: ExpansionResult,
) -> dict[str, Path]:
    """Write study.spec.yaml, study.expansion.json, and experiment.yaml."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    spec_path = root / "study.spec.yaml"
    expansion_path = root / "study.expansion.json"
    experiment_path = root / "experiment.yaml"

    spec_path.write_text(_dump_yaml(dict(normalized_spec)), encoding="utf-8")
    expansion_payload = {
        "study_identity_hash": expansion.study_identity_hash,
        "run_count": expansion.run_count,
        "factor_map": expansion.factor_map,
    }
    expansion_path.write_text(
        json.dumps(expansion_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    experiment_path.write_text(_dump_yaml(expansion.experiment), encoding="utf-8")
    return {
        "study.spec.yaml": spec_path,
        "study.expansion.json": expansion_path,
        "experiment.yaml": experiment_path,
    }


def expand_study_to_directory(
    spec: Mapping[str, Any],
    output_dir: str | Path,
) -> ExpansionResult:
    """Validate, expand, and write the three RS2 artifacts."""
    normalized = validate_study_spec(normalize_study_spec(spec))
    expansion = _expand_validated(normalized)
    write_expansion_artifacts(
        output_dir,
        normalized_spec=normalized,
        expansion=expansion,
    )
    return expansion
