"""RS-D8 in-memory StudySpec preview (validate + expand dry-run).

Composes ``validate_study_spec`` / ``expand_study``. Does **not** execute cells,
write expansion artifacts, or import ``thesistester.study.execute``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from thesistester.study.expand import _apply_stage_filter, expand_study, study_identity_hash
from thesistester.study.schema import StudySpecError, normalize_study_spec, validate_study_spec

PREVIEW_EXPAND_CAP = 2_000
EXAMPLE_STUDY_RELATIVE = Path("examples/studies/pdPOC_ma_confluence_battery.yaml")
STUDIES_PREVIEW_YAML_KEY = "studies_preview_yaml"

_BATTERY_SECTIONS = ("grid", "validation", "walk_forward")


@dataclass(frozen=True)
class StudyPreview:
    """Pure preview of a canonical StudySpec (no filesystem side effects)."""

    study_name: str
    workers: int
    confirm_above_runs: int
    needs_confirm: bool
    axis_sizes: dict[str, int]
    cartesian_product: int
    effective_run_count_estimate: int
    run_count: int | None
    expanded: bool
    study_identity_hash: str
    battery_enabled: dict[str, bool]
    hint_lines: tuple[str, ...]
    cap_warning: str | None


def example_study_spec_path() -> Path:
    """Resolve the stage-first example from cwd or the repository root."""
    candidates = (
        Path.cwd() / EXAMPLE_STUDY_RELATIVE,
        Path(__file__).resolve().parents[2] / EXAMPLE_STUDY_RELATIVE,
    )
    for path in candidates:
        if path.is_file():
            return path
    raise StudySpecError(
        f"Example StudySpec not found at {EXAMPLE_STUDY_RELATIVE} "
        "(looked under cwd and repository root)."
    )


def preview_study_yaml(text: str) -> StudyPreview:
    """Parse YAML text then preview. Invalid YAML / non-mapping → StudySpecError."""
    if not str(text).strip():
        raise StudySpecError("StudySpec YAML is empty")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StudySpecError(f"Invalid StudySpec YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise StudySpecError("StudySpec YAML must contain a mapping")
    return preview_study_spec(payload)


def preview_study_spec(spec: Mapping[str, Any]) -> StudyPreview:
    """Normalize, validate, estimate cell count, and expand in memory under cap."""
    normalized = validate_study_spec(normalize_study_spec(spec))
    study = normalized["study"]
    factors = dict(study.get("factors") or {})
    axis_sizes = {str(axis): len(list(values)) for axis, values in factors.items()}
    cartesian_product = _product(axis_sizes)
    estimate = _effective_run_count_estimate(study)
    identity = study_identity_hash(normalized)
    workers = int(study.get("workers", 1))
    confirm_above = int(study.get("confirm_above_runs", 200))
    battery_enabled = _battery_flags(dict(study.get("constants") or {}))
    hints = _battery_hint_lines(battery_enabled)

    expanded = False
    run_count: int | None = None
    cap_warning: str | None = None
    if estimate <= PREVIEW_EXPAND_CAP:
        expansion = expand_study(normalized)
        run_count = int(expansion.run_count)
        identity = expansion.study_identity_hash
        expanded = True
        count_for_confirm = run_count
    else:
        cap_warning = (
            f"In-memory expand skipped: estimated {estimate} cells exceeds "
            f"PREVIEW_EXPAND_CAP={PREVIEW_EXPAND_CAP}. Showing matched estimate only."
        )
        count_for_confirm = estimate

    return StudyPreview(
        study_name=str(study.get("name") or ""),
        workers=workers,
        confirm_above_runs=confirm_above,
        needs_confirm=count_for_confirm >= confirm_above,
        axis_sizes=axis_sizes,
        cartesian_product=cartesian_product,
        effective_run_count_estimate=estimate,
        run_count=run_count,
        expanded=expanded,
        study_identity_hash=identity,
        battery_enabled=battery_enabled,
        hint_lines=hints,
        cap_warning=cap_warning,
    )


def _product(sizes: Mapping[str, int]) -> int:
    if not sizes:
        return 1
    return int(math.prod(int(value) for value in sizes.values()))


def _effective_run_count_estimate(study: Mapping[str, Any]) -> int:
    factors = dict(study.get("factors") or {})
    stage = study.get("stage")
    if isinstance(stage, Mapping) and stage.get("mode") == "explicit_cells":
        cells = stage.get("cells") or []
        return len(list(cells))
    working = {str(key): list(values) for key, values in factors.items()}
    if isinstance(stage, Mapping) and stage.get("mode") == "filter":
        working = _apply_stage_filter(working, dict(stage.get("include") or {}))
    return _product({key: len(values) for key, values in working.items()})


def _battery_flags(constants: Mapping[str, Any]) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for section in _BATTERY_SECTIONS:
        raw = constants.get(section)
        enabled = False
        if isinstance(raw, Mapping):
            enabled = raw.get("enabled") is True
        flags[section] = enabled
    return flags


def _battery_hint_lines(flags: Mapping[str, bool]) -> tuple[str, ...]:
    armed = [name for name, enabled in flags.items() if enabled]
    if armed:
        joined = ", ".join(armed)
        return (f"WARNING: enabled {joined} dominates runtime",)
    return ("batteries: grid/validation/walk_forward disabled",)
