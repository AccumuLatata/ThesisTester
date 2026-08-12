"""Survivor promotion draft helper (RS5).

Reads a completed study directory's overview ranking and writes a **draft**
StudySpec with ``stage.mode: explicit_cells`` for the selected survivor factor
tuples. Never executes backtests — human edit/confirm remains required before
``study run``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from thesistester.setup import normalize_otf_filter_config
from thesistester.study.report import (
    StudyReportError,
    report_study,
    split_ranked_and_low_n,
)
from thesistester.study.schema import StudySpecError, load_study_spec, validate_study_spec

SPEC_YAML = "study.spec.yaml"


class StudyPromoteError(ValueError):
    """Raised when survivor promotion cannot produce a draft StudySpec."""


@dataclass(frozen=True)
class StudyPromoteResult:
    """Artifacts produced by ``promote_study``."""

    draft_spec: dict[str, Any]
    output_path: Path
    selected_run_names: list[str]
    cell_count: int
    primary_metric: str
    top_n: int
    source_study_dir: Path
    study_name: str


def _dump_yaml(payload: Mapping[str, Any]) -> str:
    return yaml.safe_dump(
        dict(payload),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def _cell_from_factors(
    factors: Mapping[str, Any],
    *,
    axis_keys: Sequence[str],
) -> dict[str, Any]:
    """Build an ``explicit_cells`` entry covering every factor axis."""
    cell: dict[str, Any] = {}
    for key in axis_keys:
        if key not in factors:
            raise StudyPromoteError(
                f"Selected survivor is missing factor axis {key!r} in expansion map"
            )
        value = factors[key]
        if key == "partner_levels":
            cell[key] = list(value)
        elif key == "otf":
            cell[key] = normalize_otf_filter_config(
                dict(value) if isinstance(value, Mapping) else value
            )
        else:
            cell[key] = value
    return cell


def _narrow_factors_to_survivors(
    original_factors: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
) -> dict[str, list[Any]]:
    """Keep original axis order; restrict domains to values used by survivors."""
    narrowed: dict[str, list[Any]] = {}
    for axis, domain in original_factors.items():
        seen: list[Any] = []
        for cell in cells:
            value = cell[axis]
            if axis == "otf":
                candidate = normalize_otf_filter_config(
                    dict(value) if isinstance(value, Mapping) else value
                )
                if candidate not in seen:
                    seen.append(candidate)
            elif axis == "partner_levels":
                candidate = list(value)
                if candidate not in seen:
                    seen.append(candidate)
            else:
                if value not in seen:
                    seen.append(value)
        # Preserve original domain order for stability when possible.
        ordered: list[Any] = []
        if axis == "otf":
            domain_norm = [
                normalize_otf_filter_config(dict(item) if isinstance(item, Mapping) else item)
                for item in domain
            ]
            for item in domain_norm:
                if item in seen and item not in ordered:
                    ordered.append(item)
            for item in seen:
                if item not in ordered:
                    ordered.append(item)
        elif axis == "partner_levels":
            domain_lists = [list(item) for item in domain]
            for item in domain_lists:
                if item in seen and item not in ordered:
                    ordered.append(item)
            for item in seen:
                if item not in ordered:
                    ordered.append(item)
        else:
            for item in domain:
                if item in seen and item not in ordered:
                    ordered.append(item)
            for item in seen:
                if item not in ordered:
                    ordered.append(item)
        if not ordered:
            raise StudyPromoteError(f"Survivor set produced empty domain for factors.{axis}")
        narrowed[axis] = ordered
    return narrowed


def select_survivor_run_names(
    ranked_run_names: Sequence[str],
    *,
    top_n: int,
    run_names: Sequence[str] | None = None,
) -> list[str]:
    """Choose survivor run names (explicit list or top-N from ranked order)."""
    if top_n < 1:
        raise StudyPromoteError("top_n must be an integer >= 1")
    if run_names is not None:
        selected = [str(name) for name in run_names]
        if not selected:
            raise StudyPromoteError("run_names must be a non-empty list when provided")
        missing = [name for name in selected if name not in set(ranked_run_names)]
        # Allow explicit selection from ranked only (honesty: do not promote low-N).
        if missing:
            raise StudyPromoteError(
                "run_names must be ranked-eligible survivors; missing or not ranked: "
                f"{missing}"
            )
        # Preserve caller order; drop duplicates.
        out: list[str] = []
        for name in selected:
            if name not in out:
                out.append(name)
        return out
    return list(ranked_run_names[:top_n])


def build_promoted_draft(
    source_spec: Mapping[str, Any],
    *,
    factor_map: Mapping[str, Mapping[str, Any]],
    selected_run_names: Sequence[str],
    source_study_dir: str | Path,
    primary_metric: str,
    top_n: int,
) -> dict[str, Any]:
    """Construct a draft StudySpec with ``stage.mode: explicit_cells``."""
    if not selected_run_names:
        raise StudyPromoteError(
            "No ranked survivor cells to promote. Re-run `study report` after "
            "more ok cells meet min_trades, or widen the source study."
        )

    study = copy.deepcopy(dict(source_spec["study"]))
    axis_keys = list(study["factors"].keys())
    cells: list[dict[str, Any]] = []
    for name in selected_run_names:
        if name not in factor_map:
            raise StudyPromoteError(f"Selected run {name!r} missing from study.expansion.json")
        cells.append(_cell_from_factors(factor_map[name], axis_keys=axis_keys))

    study["factors"] = _narrow_factors_to_survivors(study["factors"], cells)
    study["stage"] = {"mode": "explicit_cells", "cells": cells}

    base_name = str(study.get("name") or "study")
    draft_name = f"{base_name}_survivors"
    study["name"] = draft_name
    study["output_dir"] = f"results/studies/{draft_name}"
    prior_desc = str(study.get("description") or "").strip()
    promote_note = (
        f"DRAFT from study promote of {Path(source_study_dir).as_posix()} "
        f"({len(cells)} ranked survivor cell(s) by {primary_metric}, top_n={top_n}). "
        "Edit and confirm before study run — auto-execution is unsupported."
    )
    study["description"] = f"{prior_desc} {promote_note}".strip() if prior_desc else promote_note

    draft = {
        "schema_version": int(source_spec["schema_version"]),
        "study": study,
    }
    # Fail closed: draft must validate as a StudySpec before we write it.
    return validate_study_spec(draft)


def promote_study(
    study_dir: str | Path,
    *,
    output: str | Path,
    top_n: int = 10,
    metric: str | None = None,
    run_names: Sequence[str] | None = None,
) -> StudyPromoteResult:
    """Write a draft survivor StudySpec; never executes backtests."""
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyPromoteError(f"Study directory does not exist: {root}")
    spec_path = root / SPEC_YAML
    if not spec_path.is_file():
        raise StudyPromoteError(f"Missing {SPEC_YAML} under {root}")

    try:
        source_spec = load_study_spec(spec_path)
    except StudySpecError as exc:
        raise StudyPromoteError(f"Unable to load source StudySpec: {exc}") from exc

    try:
        report = report_study(root)
    except StudyReportError as exc:
        raise StudyPromoteError(f"Unable to build overview for promote: {exc}") from exc

    primary = metric or report.primary_metric
    if metric is not None and metric != report.primary_metric:
        ranked, _low, _unresolved = split_ranked_and_low_n(
            report.overview,
            primary_metric=metric,
            min_trades=report.min_trades,
        )
        ranked_names = [str(name) for name in ranked["run_name"].tolist()]
        primary = metric
    else:
        ranked_names = [str(name) for name in report.ranked["run_name"].tolist()]

    selected = select_survivor_run_names(
        ranked_names,
        top_n=top_n,
        run_names=run_names,
    )

    expansion_path = root / "study.expansion.json"
    if not expansion_path.is_file():
        raise StudyPromoteError(f"Missing study.expansion.json under {root}")
    try:
        expansion = json.loads(expansion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyPromoteError(f"Unable to read study.expansion.json: {exc}") from exc
    factor_map = expansion.get("factor_map")
    if not isinstance(factor_map, Mapping) or not factor_map:
        raise StudyPromoteError("study.expansion.json must contain a non-empty factor_map")

    draft = build_promoted_draft(
        source_spec,
        factor_map=factor_map,
        selected_run_names=selected,
        source_study_dir=root,
        primary_metric=primary,
        top_n=top_n,
    )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# DRAFT StudySpec produced by `python -m thesistester study promote`.\n"
        "# Human edit + confirm are required before `study run`.\n"
        "# This command never executes backtests.\n"
        f"# Source study_dir: {root.as_posix()}\n"
        f"# Survivors: {len(selected)} cell(s) by {primary} "
        f"(top_n={top_n if run_names is None else 'explicit'}).\n"
    )
    out_path.write_text(header + _dump_yaml(draft), encoding="utf-8")

    return StudyPromoteResult(
        draft_spec=draft,
        output_path=out_path,
        selected_run_names=list(selected),
        cell_count=len(selected),
        primary_metric=primary,
        top_n=top_n,
        source_study_dir=root,
        study_name=str(draft["study"]["name"]),
    )
