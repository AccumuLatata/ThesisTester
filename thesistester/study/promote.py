"""Survivor promotion draft helper (RS5) + Admit follow-up YAML (SAF1/SAF2).

Reads a completed study directory's overview ranking and writes a **draft**
StudySpec with ``stage.mode: explicit_cells`` for the selected survivor factor
tuples. Inspect **Draft Admit follow-up** uses the in-memory Admit path
(``draft_admit_followup_yaml`` / ``run_inspect_admit_followup``) and never
writes ``drafts/``. Never executes backtests — human edit/confirm remains
required before ``study run``.
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
from thesistester.study.admit_followup import (
    ADMIT_TOD_GROUP,
    ADMIT_TOD_GROUPS,
    ADMIT_TOD_MODE,
    AdmitFollowupError,
    apply_admit_followup,
)
from thesistester.study.expand import coerce_source_spec_parent, dataset_path_search_roots
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
                f"run_names must be ranked-eligible survivors; missing or not ranked: {missing}"
            )
        # Preserve caller order; drop duplicates.
        out: list[str] = []
        for name in selected:
            if name not in out:
                out.append(name)
        return out
    return list(ranked_run_names[:top_n])


def _rewrite_dataset_paths_for_draft(
    study: dict[str, Any],
    *,
    search_roots: Sequence[Path],
) -> list[str]:
    """Pin relative dataset paths so draft relocation cannot reinterpret them.

    ``study run`` resolves relative ``dataset.path`` against the StudySpec
    parent. Promote often writes under ``drafts/`` (or cwd), which would break
    paths authored for the original study file. Prefer an existing file under
    ``search_roots`` (spec parent first, cwd last); otherwise absolutize
    against cwd so the draft no longer depends on its own parent directory.
    """
    dataset = study.get("dataset")
    if not isinstance(dataset, dict):
        return []
    notes: list[str] = []
    roots = [Path(root).resolve() for root in search_roots]
    for key in ("path", "subtimeframe_path"):
        raw = dataset.get(key)
        if raw is None:
            continue
        if not isinstance(raw, (str, Path)):
            continue
        path = Path(raw)
        if path.is_absolute():
            dataset[key] = str(path)
            continue
        found: Path | None = None
        for root in roots:
            candidate = (root / path).resolve()
            if candidate.is_file():
                found = candidate
                break
        if found is not None:
            dataset[key] = str(found)
            notes.append(f"dataset.{key} resolved to existing file {found.as_posix()}")
        else:
            pinned = (Path.cwd() / path).resolve()
            dataset[key] = str(pinned)
            notes.append(
                f"dataset.{key} pinned to {pinned.as_posix()} "
                f"(relative path was not found under search roots; verify before study run)"
            )
    return notes


def build_promoted_draft(
    source_spec: Mapping[str, Any],
    *,
    factor_map: Mapping[str, Mapping[str, Any]],
    selected_run_names: Sequence[str],
    source_study_dir: str | Path,
    primary_metric: str,
    top_n: int,
    output_path: str | Path | None = None,
    source_spec_parent: str | Path | None = None,
) -> dict[str, Any]:
    """Construct a draft StudySpec with ``stage.mode: explicit_cells``."""
    if not selected_run_names:
        raise StudyPromoteError(
            "No ranked survivor cells to promote. Re-run `study report` after "
            "more ok cells meet min_trades, or widen the source study."
        )

    study = copy.deepcopy(dict(source_spec["study"]))
    # Default promote is RS5: never copy parent lineage (stale admit metadata).
    # ``--admit-tod`` re-attaches a new closed mapping in ``apply_admit_followup``.
    study.pop("lineage", None)
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
        "Edit and confirm before study run — auto-execution is unsupported. "
        "Phase-2 800-cell cartesian requires restoring the original full factor "
        "domains (or removing stage from the unpromoted example) — not dropping "
        "stage from this narrowed survivor draft."
    )
    study["description"] = f"{prior_desc} {promote_note}".strip() if prior_desc else promote_note

    source_root = Path(source_study_dir).resolve()
    extra_roots: list[Path] = [source_root]
    if output_path is not None:
        extra_roots.append(Path(output_path).resolve().parent)
    search_roots = dataset_path_search_roots(
        source_spec_parent=source_spec_parent,
        extra_roots=extra_roots,
    )
    path_notes = _rewrite_dataset_paths_for_draft(study, search_roots=search_roots)
    if path_notes:
        study["description"] = f"{study['description']} {' '.join(path_notes)}"

    draft = {
        "schema_version": int(source_spec["schema_version"]),
        "study": study,
    }
    # Fail closed: draft must validate as a StudySpec before we write it.
    return validate_study_spec(draft)


def _compose_promoted_draft(
    root: Path,
    *,
    top_n: int,
    metric: str | None,
    run_names: Sequence[str] | None,
    admit_tod: str | None,
    admit_run_name: str | None,
    output_path: Path | None,
    write_artifacts: bool = True,
    tod_group: str | None = None,
    allow_thin: bool = False,
) -> tuple[dict[str, Any], list[str], str]:
    """Build a promoted (and optional Admit) draft in memory.

    Does not write the draft YAML. ``write_artifacts=True`` (CLI ``promote_study``)
    may rewrite parent ``study.overview.*`` / ``study.otf_delta.csv``. The
    Inspect in-memory path passes ``False`` so a Preview draft cannot mutate
    the parent study dir.
    """
    spec_path = root / SPEC_YAML
    if not spec_path.is_file():
        raise StudyPromoteError(f"Missing {SPEC_YAML} under {root}")

    try:
        source_spec = load_study_spec(spec_path)
    except StudySpecError as exc:
        raise StudyPromoteError(f"Unable to load source StudySpec: {exc}") from exc

    try:
        report = report_study(root, write_artifacts=write_artifacts)
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

    admit_mode = str(admit_tod).strip() if admit_tod is not None else None
    if admit_run_name is not None and not str(admit_run_name).strip():
        raise StudyPromoteError("--admit-run-name must be a non-empty ranked run_name")
    if admit_run_name is not None and admit_mode is None:
        raise StudyPromoteError("--admit-run-name requires --admit-tod")
    if (tod_group is not None or allow_thin) and admit_mode is None:
        raise StudyPromoteError("--tod-group / --allow-thin require --admit-tod")
    resolved_group = ADMIT_TOD_GROUP
    if tod_group is not None:
        resolved_group = str(tod_group).strip()
        if resolved_group not in ADMIT_TOD_GROUPS:
            raise StudyPromoteError(
                f"--tod-group must be one of {sorted(ADMIT_TOD_GROUPS)}; got {tod_group!r}"
            )
    if admit_mode is not None:
        if admit_mode != ADMIT_TOD_MODE:
            raise StudyPromoteError(
                f"--admit-tod must be {ADMIT_TOD_MODE!r} when set; got {admit_tod!r}"
            )
        if top_n != 1 and admit_run_name is None:
            raise StudyPromoteError(
                "--admit-tod requires --top-n 1 or --admit-run-name (one cell per draft)"
            )
        if admit_run_name is not None:
            selected = select_survivor_run_names(
                ranked_names,
                top_n=top_n,
                run_names=[str(admit_run_name).strip()],
            )
        else:
            selected = select_survivor_run_names(ranked_names, top_n=1, run_names=None)
    else:
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
    raw_parent = expansion.get("source_spec_parent")
    source_spec_parent = (
        coerce_source_spec_parent(raw_parent) if isinstance(raw_parent, str) else None
    )

    draft = build_promoted_draft(
        source_spec,
        factor_map=factor_map,
        selected_run_names=selected,
        source_study_dir=root,
        primary_metric=primary,
        top_n=top_n,
        output_path=output_path,
        source_spec_parent=source_spec_parent,
    )

    if admit_mode is not None:
        parent_hash = expansion.get("study_identity_hash")
        if not isinstance(parent_hash, str) or not parent_hash.strip():
            raise StudyPromoteError(
                "study.expansion.json missing study_identity_hash; re-run study expand"
            )
        parent_study = source_spec.get("study")
        parent_name = "study"
        instrument = ""
        if isinstance(parent_study, Mapping):
            parent_name = str(parent_study.get("name") or "study")
            dataset = parent_study.get("dataset")
            if isinstance(dataset, Mapping):
                instrument = dataset.get("instrument")
        run_name = selected[0]
        try:
            draft = apply_admit_followup(
                draft,
                parent_study_dir=root,
                parent_study_name=parent_name,
                parent_identity_hash=parent_hash.strip(),
                parent_run_name=run_name,
                bundle_rel=_overview_bundle_rel(report, run_name),
                min_trades=int(report.min_trades),
                instrument=str(instrument or ""),
                group_col=resolved_group,
                allow_thin=bool(allow_thin),
            )
        except AdmitFollowupError as exc:
            raise StudyPromoteError(str(exc)) from exc

    return draft, list(selected), primary


def _promote_yaml_text(
    draft: Mapping[str, Any],
    *,
    root: Path,
    selected: Sequence[str],
    primary: str,
    top_n: int,
    run_names: Sequence[str] | None,
    admit_tod: str | None,
    admit_run_name: str | None,
) -> str:
    admit_header = ""
    if admit_tod is not None:
        admit_header = (
            "# Admit follow-up: one-cell constrained re-sim (Focus ≠ Admit).\n"
            "# Engine path is constants.backtest.entry_window "
            "(and grid.entry_window when grid is present).\n"
            "# This command never executes backtests.\n"
        )
    header = (
        "# DRAFT StudySpec produced by `python -m thesistester study promote`.\n"
        "# Human edit + confirm are required before `study run`.\n"
        "# This command never executes backtests.\n"
        f"{admit_header}"
        f"# Source study_dir: {root.as_posix()}\n"
        f"# Survivors: {len(selected)} cell(s) by {primary} "
        f"(top_n={top_n if run_names is None and admit_run_name is None else 'explicit'}).\n"
        "# dataset.path values are absolutized when possible so relocating this\n"
        "# draft under drafts/ does not reinterpret relative bars paths.\n"
        "# Phase-2 800-cell cartesian: restore original full factor domains on the\n"
        "# unpromoted example (or remove its stage filter) — do not drop stage from\n"
        "# this narrowed survivor draft and expect 800 cells.\n"
    )
    return header + _dump_yaml(draft)


def draft_admit_followup_yaml(
    study_dir: str | Path,
    *,
    admit_run_name: str | None = None,
) -> str:
    """In-memory Admit follow-up YAML (SAF1 helper). Never writes. Never executes."""
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyPromoteError(f"Study directory does not exist: {root}")
    draft, selected, primary = _compose_promoted_draft(
        root,
        top_n=1,
        metric=None,
        run_names=None,
        admit_tod=ADMIT_TOD_MODE,
        admit_run_name=admit_run_name,
        output_path=None,
        write_artifacts=False,
    )
    return _promote_yaml_text(
        draft,
        root=root,
        selected=selected,
        primary=primary,
        top_n=1,
        run_names=None,
        admit_tod=ADMIT_TOD_MODE,
        admit_run_name=admit_run_name,
    )


def inspect_cell_in_flight(
    ledger_cells: Mapping[str, Any] | None,
    run_name: str,
    *,
    running_ids: Sequence[str] = (),
) -> bool:
    """True when the crowned cell is still ``running`` or ``pending``."""
    name = str(run_name or "").strip()
    if not name:
        return False
    if name in {str(item) for item in running_ids}:
        return True
    if not isinstance(ledger_cells, Mapping):
        return False
    cell = ledger_cells.get(name)
    if not isinstance(cell, Mapping):
        return False
    return str(cell.get("status") or "") in {"running", "pending"}


def inspect_admit_followup_ready(briefing: Any) -> bool:
    """True when Inspect has a ranked crown and a NY ToD segment."""
    run_name = getattr(briefing, "run_name", None)
    if not isinstance(run_name, str) or not run_name.strip() or run_name.strip() == "—":
        return False
    if str(getattr(briefing, "source", "") or "") != "ranked":
        return False
    tod = getattr(briefing, "tod_best", None) or {}
    if not isinstance(tod, Mapping):
        return False
    segment = str(tod.get("segment") or "").strip()
    return bool(segment) and segment != "—"


def run_inspect_admit_followup(
    study_dir: str | Path,
    *,
    run_name: str,
    ledger_cells: Mapping[str, Any] | None = None,
    running_ids: Sequence[str] = (),
    trusted_roots: Sequence[Path] | None = None,
) -> str:
    """Inspect Admit draft YAML. Extra-root / in-flight refuse. Never writes files."""
    name = str(run_name or "").strip()
    if not name:
        raise StudyPromoteError("No ranked cell to draft Admit follow-up")
    if inspect_cell_in_flight(ledger_cells, name, running_ids=running_ids):
        raise StudyPromoteError(
            f"Selected cell {name!r} is still running or pending; wait for it to finish"
        )
    candidate = Path(study_dir).expanduser().resolve()
    if trusted_roots:
        allowed = tuple(Path(root).resolve() for root in trusted_roots)
        if not any(candidate == root or candidate.is_relative_to(root) for root in allowed):
            raise StudyPromoteError(
                "Study path is outside the trusted local roots "
                f"(cwd and store). Resolved path: {candidate}"
            )
    if not candidate.is_dir():
        raise StudyPromoteError(f"Study directory does not exist: {candidate}")
    return draft_admit_followup_yaml(candidate, admit_run_name=name)


def _overview_bundle_rel(report: Any, run_name: str) -> str | None:
    """``bundle_path`` for a ranked run from the overview frame."""
    overview = getattr(report, "overview", None)
    if overview is None or getattr(overview, "empty", True):
        return None
    if "run_name" not in overview.columns or "bundle_path" not in overview.columns:
        return None
    matched = overview.loc[overview["run_name"].astype(str) == str(run_name)]
    if matched.empty:
        return None
    raw = matched.iloc[0].get("bundle_path")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def promote_study(
    study_dir: str | Path,
    *,
    output: str | Path,
    top_n: int = 10,
    metric: str | None = None,
    run_names: Sequence[str] | None = None,
    force: bool = False,
    admit_tod: str | None = None,
    admit_run_name: str | None = None,
    tod_group: str | None = None,
    allow_thin: bool = False,
) -> StudyPromoteResult:
    """Write a draft survivor StudySpec; never executes backtests.

    ``admit_tod`` omitted → RS5 promote (no lineage, no Admit window).
    ``admit_tod='auto'`` → one-cell Admit follow-up (SAF1).
    ``tod_group`` / ``allow_thin`` require ``admit_tod`` (SAF3).
    """
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyPromoteError(f"Study directory does not exist: {root}")

    out_path = Path(output)
    if out_path.exists() and not force:
        raise StudyPromoteError(
            f"Refusing to overwrite existing draft {out_path}; pass --force to replace "
            "(promote drafts are meant for human edits)"
        )

    draft, selected, primary = _compose_promoted_draft(
        root,
        top_n=top_n,
        metric=metric,
        run_names=run_names,
        admit_tod=admit_tod,
        admit_run_name=admit_run_name,
        output_path=out_path,
        tod_group=tod_group,
        allow_thin=allow_thin,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _promote_yaml_text(
            draft,
            root=root,
            selected=selected,
            primary=primary,
            top_n=top_n,
            run_names=run_names,
            admit_tod=admit_tod,
            admit_run_name=admit_run_name,
        ),
        encoding="utf-8",
    )

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
