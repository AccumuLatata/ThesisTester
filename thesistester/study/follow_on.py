"""Follow-on confirmation draft (SV6).

Turns one finished study cell + one NY RTH segment into a **draft** StudySpec:
narrowed factor domains, Admit ``constants.entry_window``, optional pinned
SL/TP, a new ``output_dir``, and lineage in the description.

Does not execute backtests, rewrite the parent study dir artifacts, add a
ToD factor axis, or mutate classic research session keys.
"""

from __future__ import annotations

import copy
import csv
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thesistester.entry_window_policy import (
    RTH_SEGMENT_LABELS,
    entry_window_from_bucket,
)
from thesistester.study.briefing import (
    TOD_MIN_TRADES_WARNING,
    build_study_briefing,
    extract_cell_time_of_day,
    resolve_cell_bundle,
)
from thesistester.study.promote import (
    _cell_from_factors,
    _dump_yaml,
    _narrow_factors_to_survivors,
    _rewrite_dataset_paths_for_draft,
)
from thesistester.study.report import StudyReportError, report_study
from thesistester.study.schema import (
    RUN_NAME_RE,
    StudySpecError,
    load_study_spec,
    validate_study_spec,
)

SPEC_YAML = "study.spec.yaml"
FOLLOW_ON_SEGMENTS: tuple[str, ...] = RTH_SEGMENT_LABELS
_PROTECTED_SPEC_NAMES = frozenset({SPEC_YAML, "study.expansion.json", "experiment.yaml"})


class StudyFollowOnError(ValueError):
    """Raised when a follow-on confirmation draft cannot be produced."""


@dataclass(frozen=True)
class StudyFollowOnResult:
    """Artifacts produced by ``follow_on_study`` (write is optional)."""

    draft_spec: dict[str, Any]
    yaml_text: str
    output_path: Path | None
    parent_study_dir: Path
    parent_study_name: str
    run_name: str
    segment: str
    thin_sample: bool
    pin_grid: bool
    entry_window: dict[str, Any]
    study_name: str


def suggested_follow_on_path(study_dir: str | Path, segment: str) -> Path:
    """Default draft path: ``<study_dir>/follow_on_<segment>.yaml``."""
    return Path(study_dir) / f"follow_on_{_safe_token(segment)}.yaml"


def entry_window_for_rth_segment(
    segment: str,
    *,
    timezone: str = "America/New_York",
) -> dict[str, Any]:
    """Admit window for one canonical NY RTH label. Unknown labels fail closed."""
    label = str(segment or "").strip()
    if label not in FOLLOW_ON_SEGMENTS:
        raise StudyFollowOnError(
            f"Unknown RTH segment {label!r}. Expected one of {list(FOLLOW_ON_SEGMENTS)}."
        )
    try:
        return entry_window_from_bucket(
            "entry_rth_segment",
            label,
            exchange_tz=timezone,
        )
    except ValueError as exc:
        raise StudyFollowOnError(str(exc)) from exc


def build_follow_on_spec(
    source_spec: Mapping[str, Any],
    *,
    factors: Mapping[str, Any],
    segment: str,
    run_name: str,
    parent_study_dir: str | Path,
    pin_stop_loss_ticks: int | None = None,
    pin_take_profit_ticks: int | None = None,
    pin_grid: bool = True,
    thin_sample: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Construct a one-cell Admit confirmation StudySpec. Does not write."""
    if "entry_rth_segment" in factors or "time_of_day" in factors:
        raise StudyFollowOnError(
            "Follow-on must not add time-of-day as a factor axis; "
            "constrain via constants.entry_window."
        )
    if not run_name or str(run_name).strip() in {"—", "-"}:
        raise StudyFollowOnError("run_name is required for a follow-on draft.")

    draft = copy.deepcopy(dict(source_spec))
    study = draft.setdefault("study", {})
    if not isinstance(study, dict):
        raise StudyFollowOnError("source StudySpec study section must be a mapping")

    original_factors = study.get("factors")
    if not isinstance(original_factors, Mapping) or not original_factors:
        raise StudyFollowOnError("source StudySpec is missing study.factors")
    axis_keys = list(original_factors.keys())
    try:
        cell = _cell_from_factors(factors, axis_keys=axis_keys)
        study["factors"] = _narrow_factors_to_survivors(original_factors, [cell])
    except Exception as exc:
        raise StudyFollowOnError(f"Unable to narrow factor settings: {exc}") from exc
    # One narrowed tuple expands to one cell; drop survivor/filter stages.
    study.pop("stage", None)

    constants = dict(study.get("constants") or {})
    existing_window = constants.get("entry_window")
    timezone = "America/New_York"
    if isinstance(existing_window, Mapping) and existing_window.get("timezone"):
        timezone = str(existing_window["timezone"])
    window = entry_window_for_rth_segment(segment, timezone=timezone)
    constants["entry_window"] = window

    pin_notes: list[str] = []
    if pin_grid and pin_stop_loss_ticks is not None and pin_take_profit_ticks is not None:
        backtest = dict(constants.get("backtest") or {})
        backtest["stop_loss_ticks"] = int(pin_stop_loss_ticks)
        backtest["take_profit_ticks"] = int(pin_take_profit_ticks)
        constants["backtest"] = backtest
        grid = constants.get("grid")
        if isinstance(grid, Mapping):
            pinned_grid = dict(grid)
            pinned_grid["enabled"] = False
            constants["grid"] = pinned_grid
        pin_notes.append(
            f"Pinned SL/TP {pin_stop_loss_ticks}/{pin_take_profit_ticks} ticks "
            "and disabled the per-cell SL/TP grid."
        )
    elif pin_grid:
        pin_notes.append(
            "Pin-grid was requested but no best SL/TP ticks were available; "
            "parent backtest/grid settings were left unchanged."
        )
    study["constants"] = constants

    parent_name = str(study.get("name") or "study")
    follow_name = _follow_on_study_name(parent_name, segment)
    study["name"] = follow_name
    study["output_dir"] = _follow_on_output_dir(study.get("output_dir"), parent_name, follow_name)

    parent_dir = Path(parent_study_dir)
    thin_note = (
        f"NY bucket is thin (N < {TOD_MIN_TRADES_WARNING}) — treat as a hint, not a schedule."
        if thin_sample
        else "NY bucket sample cleared the briefing warning gate (or was not re-checked)."
    )
    prior = str(study.get("description") or "").strip()
    follow_note = (
        f"FOLLOW-ON confirmation of {parent_name} "
        f"({parent_dir.as_posix()}, cell {run_name}). "
        f"Factors narrowed to that cell. Admit entry_window NY `{segment}`. "
        f"{thin_note} {' '.join(pin_notes)}"
        " Not a ToD factor axis. Edit and confirm before study run — "
        "this draft does not execute."
    )
    study["description"] = f"{prior} {follow_note}".strip() if prior else follow_note

    search_roots: list[Path] = [Path.cwd().resolve(), parent_dir.resolve()]
    if output_path is not None:
        search_roots.append(Path(output_path).resolve().parent)
    path_notes = _rewrite_dataset_paths_for_draft(study, search_roots=search_roots)
    if path_notes:
        study["description"] = f"{study['description']} {' '.join(path_notes)}"

    try:
        return validate_study_spec(draft)
    except StudySpecError as exc:
        raise StudyFollowOnError(f"Follow-on draft failed StudySpec validation: {exc}") from exc


def follow_on_study(
    study_dir: str | Path,
    *,
    run_name: str | None = None,
    segment: str | None = None,
    pin_grid: bool = True,
    allow_thin: bool = False,
    output: str | Path | None = None,
    write: bool = True,
    force: bool = False,
) -> StudyFollowOnResult:
    """Draft a follow-on StudySpec from a completed study directory.

    ``write=False`` still returns ``yaml_text`` (Inspect download / Preview).
    Default output is ``<study_dir>/follow_on_<segment>.yaml``. Never overwrites
    the parent ``study.spec.yaml``.
    """
    root = Path(study_dir)
    if not root.is_dir():
        raise StudyFollowOnError(f"Study directory does not exist: {root}")
    spec_path = root / SPEC_YAML
    if not spec_path.is_file():
        raise StudyFollowOnError(f"Missing {SPEC_YAML} under {root}")

    try:
        source_spec = load_study_spec(spec_path)
    except StudySpecError as exc:
        raise StudyFollowOnError(f"Unable to load source StudySpec: {exc}") from exc

    factor_map = _load_factor_map(root)
    resolved_run, resolved_segment, briefing = _resolve_run_and_segment(
        root,
        run_name=run_name,
        segment=segment,
        factor_map=factor_map,
    )
    if resolved_run not in factor_map:
        raise StudyFollowOnError(
            f"run_name {resolved_run!r} is missing from study.expansion.json"
        )

    thin_sample, sl_ticks, tp_ticks = _sample_and_grid(
        root,
        resolved_run,
        resolved_segment,
        briefing=briefing,
    )
    if thin_sample and not allow_thin:
        raise StudyFollowOnError(
            f"NY bucket `{resolved_segment}` is thin (N < {TOD_MIN_TRADES_WARNING}). "
            "Pass --allow-thin (or the Inspect checkbox) to draft anyway. "
            "A thin bucket is a hint, not a live schedule."
        )

    out_path: Path | None = None
    if write:
        if output is not None:
            out_path = Path(output)
        else:
            out_path = suggested_follow_on_path(root, resolved_segment)
        _assert_safe_output(out_path, parent_spec=spec_path, force=force)

    draft = build_follow_on_spec(
        source_spec,
        factors=factor_map[resolved_run],
        segment=resolved_segment,
        run_name=resolved_run,
        parent_study_dir=root,
        pin_stop_loss_ticks=sl_ticks if pin_grid else None,
        pin_take_profit_ticks=tp_ticks if pin_grid else None,
        pin_grid=pin_grid,
        thin_sample=thin_sample,
        output_path=out_path,
    )
    yaml_text = _header(
        root,
        run_name=resolved_run,
        segment=resolved_segment,
        thin_sample=thin_sample,
        pin_grid=pin_grid,
    ) + _dump_yaml(draft)

    if write:
        assert out_path is not None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_text, encoding="utf-8")

    window = draft["study"]["constants"]["entry_window"]
    return StudyFollowOnResult(
        draft_spec=draft,
        yaml_text=yaml_text,
        output_path=out_path,
        parent_study_dir=root,
        parent_study_name=str(source_spec["study"].get("name") or ""),
        run_name=resolved_run,
        segment=resolved_segment,
        thin_sample=thin_sample,
        pin_grid=pin_grid,
        entry_window=dict(window) if isinstance(window, Mapping) else {},
        study_name=str(draft["study"]["name"]),
    )


def _resolve_run_and_segment(
    root: Path,
    *,
    run_name: str | None,
    segment: str | None,
    factor_map: Mapping[str, Any],
) -> tuple[str, str, Any]:
    explicit_run = str(run_name).strip() if run_name else ""
    explicit_segment = str(segment).strip() if segment else ""
    if explicit_run and explicit_segment:
        if explicit_run not in factor_map:
            raise StudyFollowOnError(
                f"run_name {explicit_run!r} is missing from study.expansion.json"
            )
        if explicit_segment not in FOLLOW_ON_SEGMENTS:
            raise StudyFollowOnError(
                f"Unknown RTH segment {explicit_segment!r}. "
                f"Expected one of {list(FOLLOW_ON_SEGMENTS)}."
            )
        return explicit_run, explicit_segment, None

    try:
        report = report_study(root, write_artifacts=False)
        briefing = build_study_briefing(report, study_dir=root)
    except StudyReportError as exc:
        raise StudyFollowOnError(
            f"Unable to resolve briefing defaults (pass --run-name and --segment): {exc}"
        ) from exc

    resolved_run = explicit_run or str(getattr(briefing, "run_name", "") or "").strip()
    tod = getattr(briefing, "tod_best", None) or {}
    resolved_segment = explicit_segment or str(tod.get("segment") or "").strip()
    if not resolved_run or resolved_run in {"—", "-"}:
        raise StudyFollowOnError(
            "No briefing cell to follow on. Pass --run-name for a specific rerun."
        )
    if not resolved_segment or resolved_segment in {"—", "-"}:
        raise StudyFollowOnError(
            "No NY segment on the briefing. Pass --segment (one of "
            f"{list(FOLLOW_ON_SEGMENTS)})."
        )
    if resolved_segment not in FOLLOW_ON_SEGMENTS:
        raise StudyFollowOnError(
            f"Unknown RTH segment {resolved_segment!r}. "
            f"Expected one of {list(FOLLOW_ON_SEGMENTS)}."
        )
    return resolved_run, resolved_segment, briefing


def _sample_and_grid(
    root: Path,
    run_name: str,
    segment: str,
    *,
    briefing: Any,
) -> tuple[bool, int | None, int | None]:
    sl_ticks: int | None = None
    tp_ticks: int | None = None
    thin_sample = False
    briefing_run = str(getattr(briefing, "run_name", "") or "")
    tod = getattr(briefing, "tod_best", None) or {}
    grid = getattr(briefing, "best_grid", None) or {}
    if briefing is not None and briefing_run == run_name:
        sl_ticks = _coerce_tick(grid.get("stop_loss_ticks"))
        tp_ticks = _coerce_tick(grid.get("take_profit_ticks"))
        if str(tod.get("segment") or "") == segment:
            warn = tod.get("sample_warning")
            thin_sample = warn is True or str(warn).strip().lower() == "true"

    if sl_ticks is None or tp_ticks is None:
        index_sl, index_tp = _grid_ticks_from_index(root, run_name)
        sl_ticks = sl_ticks if sl_ticks is not None else index_sl
        tp_ticks = tp_ticks if tp_ticks is not None else index_tp

    if briefing is None or briefing_run != run_name or str(tod.get("segment") or "") != segment:
        tod_best = _tod_best_for_run(root, run_name)
        if tod_best and str(tod_best.get("segment") or "") == segment:
            warn = tod_best.get("sample_warning")
            thin_sample = warn is True or str(warn).strip().lower() == "true"
    return thin_sample, sl_ticks, tp_ticks


def _tod_best_for_run(root: Path, run_name: str) -> dict[str, str] | None:
    bundle_rel = _bundle_rel_from_index(root, run_name)
    bundle = resolve_cell_bundle(root, bundle_rel)
    if bundle is None:
        return None
    _display, best, _caption = extract_cell_time_of_day(bundle)
    return best


def _grid_ticks_from_index(root: Path, run_name: str) -> tuple[int | None, int | None]:
    path = root / "results_index.csv"
    if not path.is_file():
        return None, None
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("run_name") or "") != run_name:
                    continue
                return (
                    _coerce_tick(row.get("best_grid_stop_loss_ticks")),
                    _coerce_tick(row.get("best_grid_take_profit_ticks")),
                )
    except (OSError, UnicodeDecodeError, csv.Error):
        return None, None
    return None, None


def _bundle_rel_from_index(root: Path, run_name: str) -> str | None:
    path = root / "results_index.csv"
    if not path.is_file():
        return None
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("run_name") or "") != run_name:
                    continue
                rel = str(row.get("bundle_path") or "").strip()
                return rel or None
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    return None


def _load_factor_map(root: Path) -> dict[str, Any]:
    expansion_path = root / "study.expansion.json"
    if not expansion_path.is_file():
        raise StudyFollowOnError(f"Missing study.expansion.json under {root}")
    try:
        expansion = json.loads(expansion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyFollowOnError(f"Unable to read study.expansion.json: {exc}") from exc
    factor_map = expansion.get("factor_map")
    if not isinstance(factor_map, Mapping) or not factor_map:
        raise StudyFollowOnError("study.expansion.json must contain a non-empty factor_map")
    return dict(factor_map)


def _assert_safe_output(out_path: Path, *, parent_spec: Path, force: bool) -> None:
    if out_path.name in _PROTECTED_SPEC_NAMES:
        raise StudyFollowOnError(
            f"Refusing to write follow-on draft over protected study artifact {out_path.name}"
        )
    try:
        if out_path.resolve() == parent_spec.resolve():
            raise StudyFollowOnError(
                "Refusing to overwrite the parent study.spec.yaml"
            )
    except OSError:
        pass
    if out_path.exists() and not force:
        raise StudyFollowOnError(
            f"Refusing to overwrite existing draft {out_path}; pass --force to replace "
            "(follow-on drafts are meant for human edits)"
        )


def _follow_on_study_name(base: str, segment: str) -> str:
    token = _safe_token(segment)
    suffix = f"fo_{token}"
    if base.endswith(suffix) or f"__{suffix}" in base:
        candidate = base
    else:
        candidate = f"{base}__{suffix}"
    if not RUN_NAME_RE.fullmatch(candidate):
        raise StudyFollowOnError(
            f"Follow-on study.name {candidate!r} is not a valid StudySpec name"
        )
    return candidate


def _follow_on_output_dir(parent_output: Any, parent_name: str, follow_name: str) -> str:
    text = str(parent_output or "").strip()
    if text:
        parent_path = Path(text)
        if parent_path.name == parent_name:
            return parent_path.with_name(follow_name).as_posix()
    return f"results/studies/{follow_name}"


def _safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value).strip())


def _coerce_tick(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return int(number)


def _header(
    root: Path,
    *,
    run_name: str,
    segment: str,
    thin_sample: bool,
    pin_grid: bool,
) -> str:
    thin = "thin" if thin_sample else "ok"
    pin = "pinned" if pin_grid else "parent-grid"
    return (
        "# DRAFT StudySpec produced by `python -m thesistester study follow-on`.\n"
        "# One narrowed cell + Admit entry_window. Does not execute backtests.\n"
        f"# Parent study_dir: {root.as_posix()}\n"
        f"# Cell: {run_name}\n"
        f"# Segment: {segment} (sample={thin}, grid={pin})\n"
        "# Time-of-day is not a factor axis. Edit and confirm before `study run`.\n"
    )
