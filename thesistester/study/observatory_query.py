"""Observatory query / display helpers (C-24 / QI-07-07).

Facets, sort, cohort labels, CLI table. Read-only. No Streamlit / Plotly.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import pandas as pd

from thesistester.study.observatory_join import ObservatoryModel
from thesistester.study.observatory_lens import _heatmap_partner_token
from thesistester.study.observatory_support import (
    CLI_COLUMNS,
    COHORT_FIELDS,
    LENS_FACET_COLUMNS,
    SORT_ALLOW_LIST,
    STUDIES_TABLE_COLUMNS,
    ObservatoryError,
    _cli_cell,
    _default_descending,
    _coerce_number,
    _error_text_present,
    _facet_sort_key,
    _is_na,
    _sort_subset,
    canonical_facet_value,
)


def parse_cohort_key(key: Any) -> dict[str, str]:
    """Split a raw ``cohort_key`` into ``COHORT_FIELDS`` tokens (plan §4.11).

    Token count must match ``len(COHORT_FIELDS)``. Otherwise return ``{}``
    (fail closed). Display only — does not change key composition.
    """
    if key is None or _is_na(key):
        return {}
    tokens = str(key).split("|")
    if len(tokens) != len(COHORT_FIELDS):
        return {}
    return {field: token for field, token in zip(COHORT_FIELDS, tokens, strict=True)}


def format_cohort_label(key: Any) -> str:
    """Short display label for a raw ``cohort_key`` (plan §4.11).

    Malformed keys (parse → ``{}``) return the raw string. Empty tokens → ``—``.
    """
    raw = "" if key is None or _is_na(key) else str(key)
    parsed = parse_cohort_key(raw)
    if not parsed:
        return raw

    def _short(field: str) -> str:
        token = parsed.get(field, "")
        return token if token else "—"

    return (
        f"{_short('instrument')} · {_short('dataset_id')} · "
        f"SL{_short('stop_loss_ticks')}/TP{_short('take_profit_ticks')} · "
        f"{_short('trigger')}@{_short('trigger_timeframe')} · "
        f"min_valid={_short('min_valid_confluences')}"
    )


def cohort_choice_labels(keys: Sequence[Any]) -> list[str]:
    """Unique Active-cohort labels, parallel to ``keys`` (plan §4.11)."""
    raws = ["" if key is None or _is_na(key) else str(key) for key in keys]
    shorts = [format_cohort_label(raw) for raw in raws]
    groups: dict[str, list[int]] = {}
    for index, short in enumerate(shorts):
        groups.setdefault(short, []).append(index)
    labels = list(shorts)
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        parsed_group = [parse_cohort_key(raws[index]) for index in indexes]
        differ = [
            field
            for field in COHORT_FIELDS
            if len({row.get(field, "") for row in parsed_group}) > 1
        ]
        if not differ:
            continue
        for index, parsed in zip(indexes, parsed_group, strict=True):
            extra = " · ".join(f"{field}={parsed.get(field, '')}" for field in differ)
            labels[index] = f"{shorts[index]} · {extra}"
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    if any(count > 1 for count in counts.values()):
        for index, label in enumerate(labels):
            if counts[label] > 1:
                labels[index] = f"{label} — {raws[index]}"
    return labels


def cohort_differ_fields(keys: Sequence[Any]) -> tuple[str, ...]:
    """§4.5 field names whose parsed values are not identical across ``keys``.

    Empty if fewer than two keys or all raw keys are equal. Distinct raw
    keys that fail parse (empty dict) must not look like a shared lock —
    return every ``COHORT_FIELDS`` name (fail closed).
    """
    raws = ["" if key is None or _is_na(key) else str(key) for key in keys]
    if len(raws) < 2 or len(set(raws)) == 1:
        return ()
    parsed_rows = [parse_cohort_key(raw) for raw in raws]
    differ = tuple(
        field for field in COHORT_FIELDS if len({row.get(field, "") for row in parsed_rows}) > 1
    )
    if differ:
        return differ
    if any(not row for row in parsed_rows):
        return tuple(COHORT_FIELDS)
    return ()


def _facet_canonical(column: str, value: Any) -> Any:
    """Column-aware facet token. Empty partners are ``(solo)`` (plan §4.12)."""
    if column == "factor_partner_levels":
        return _heatmap_partner_token(value)
    return canonical_facet_value(value)


def query_facets_for_frame(
    generic: Mapping[str, Sequence[Any]] | None,
    *,
    lens_active: bool,
    lens_facets: Mapping[str, Sequence[Any]] | None = None,
) -> dict[str, list[Any]]:
    """Generic facets always. Lens columns only while the Program B lens is on."""
    merged: dict[str, list[Any]] = {}
    for column, values in dict(generic or {}).items():
        if column in LENS_FACET_COLUMNS:
            continue
        tokens = list(values or ())
        if tokens:
            merged[column] = tokens
    if lens_active:
        for column in LENS_FACET_COLUMNS:
            tokens = list((lens_facets or {}).get(column) or ())
            if tokens:
                merged[column] = tokens
    return merged


def apply_facets(
    frame: pd.DataFrame,
    facets: Mapping[str, Sequence[Any]] | None = None,
) -> pd.DataFrame:
    """Keep rows whose facet columns are in the provided value sets.

    Numeric tokens use :func:`canonical_facet_value` so ``80`` and ``80.0``
    match (same honesty as ``cohort_key`` integer tokens). Raw ``isin``
    would hide one lock when YAML stored an int and pandas upcast a float.
    Empty ``factor_partner_levels`` match ``(solo)`` so a heatmap Wave 0
    cell can write the existing Partner widget (plan §4.12).
    """
    if frame.empty or not facets:
        return frame.copy()
    mask = pd.Series(True, index=frame.index)
    for column, raw_values in facets.items():
        if column not in frame.columns:
            continue

        def _token(item: Any, *, _column: str = column) -> Any:
            return _facet_canonical(_column, item)

        allowed = {_token(value) for value in raw_values}
        allowed.discard(None)
        if not allowed:
            continue
        mask = mask & frame[column].map(_token).isin(allowed)
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
    """Sorted unique non-null values for a facet column.

    Returns Python scalars (not numpy) so Streamlit widgets can serialize
    the option list. Integer-valued numbers collapse to ``int``.
    """
    if frame.empty or column not in frame.columns:
        return []
    seen: set[Any] = set()
    values: list[Any] = []
    for value in frame[column].tolist():
        canonical = _facet_canonical(column, value)
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        values.append(canonical)
    return sorted(values, key=_facet_sort_key)


def constrain_facet_selection(
    selected: Sequence[Any] | None,
    options: Sequence[Any],
) -> list[Any]:
    """Keep widget values that still exist in *options* (canonical match)."""
    if not selected or not options:
        return []
    by_key = {canonical_facet_value(option): option for option in options}
    by_key.pop(None, None)
    out: list[Any] = []
    seen: set[Any] = set()
    for value in selected:
        key = canonical_facet_value(value)
        if key is None or key not in by_key or key in seen:
            continue
        seen.add(key)
        out.append(by_key[key])
    return out


def cell_choice_labels(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Unique Inspect-drill labels. Duplicate ``study / run`` get ``study_dir``."""
    bases: list[str] = []
    for row in rows:
        bases.append(_cell_base_label(row))
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    labels: list[str] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        base = bases[index]
        if counts[base] == 1:
            labels.append(base)
            continue
        directory = str(row.get("study_dir") or "").strip() or f"row-{index}"
        label = f"{base} — {directory}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} #{seen[label]}"
        labels.append(label)
    return labels


def _cell_base_label(row: Mapping[str, Any]) -> str:
    study = row.get("study_name")
    run = row.get("run_name")
    study_s = "—" if study is None or _is_na(study) else str(study)
    run_s = "—" if run is None or _is_na(run) else str(run)
    return f"{study_s} / {run_s}"


def corpus_progress_counts(studies: pd.DataFrame) -> dict[str, int]:
    """Sum ledger counts across catalog dirs. Missing columns stay 0."""
    counts = {
        "studies": 0 if studies.empty else int(len(studies)),
        "ok": 0,
        "failed": 0,
        "skipped": 0,
        "running": 0,
        "pending": 0,
    }
    if studies.empty:
        return counts
    for column in ("ok", "failed", "skipped", "running", "pending"):
        if column not in studies.columns:
            continue
        total = 0
        for raw in studies[column].tolist():
            number = _coerce_number(raw)
            if number is None or not math.isfinite(number):
                continue
            total += int(number)
        counts[column] = total
    return counts


def directional_integrity_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Count DA2 integrity classes on the fact table. Missing column → zeros."""
    counts = {"long_only": 0, "short_only": 0, "mixed": 0, "empty": 0}
    if frame.empty or "directional_integrity" not in frame.columns:
        return counts
    for value in frame["directional_integrity"].tolist():
        if value is None or _is_na(value):
            continue
        token = str(value)
        if token in counts:
            counts[token] += 1
    return counts


def drift_class_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Count DA5 drift classes on the fact table. Missing column → zeros."""
    counts = {"above_null": 0, "at_null": 0, "unknown": 0}
    if frame.empty or "drift_class" not in frame.columns:
        return counts
    for value in frame["drift_class"].tolist():
        if value is None or _is_na(value):
            continue
        token = str(value)
        if token in counts:
            counts[token] += 1
    return counts


def format_heatmap_direction_count(value: Any) -> str:
    """``L n / S n`` tooltip token. Missing / non-finite → ``—`` (never ``nan``)."""
    number = _coerce_number(value)
    if number is None or not math.isfinite(number):
        return "—"
    if float(number).is_integer():
        return str(int(number))
    return f"{number:g}"


def sort_observatory_studies(studies: pd.DataFrame) -> pd.DataFrame:
    """Parse errors and in-flight dirs before completed names.

    Display order only. Does not change cell ranking or invent cell rows.
    """
    if studies.empty:
        return studies.copy()
    work = studies.copy()
    if "error" in work.columns:
        work["_error_rank"] = [
            0 if _error_text_present(value) else 1 for value in work["error"].tolist()
        ]
    else:
        work["_error_rank"] = 1
    for column, dest in (
        ("running", "_running"),
        ("pending", "_pending"),
        ("failed", "_failed"),
    ):
        if column in work.columns:
            work[dest] = pd.to_numeric(work[column], errors="coerce").fillna(0)
        else:
            work[dest] = 0
    if "study_name" not in work.columns:
        work["study_name"] = ""
    if "study_dir" not in work.columns:
        work["study_dir"] = ""
    work = work.sort_values(
        by=["_error_rank", "_running", "_pending", "_failed", "study_name", "study_dir"],
        ascending=[True, False, False, False, True, True],
        kind="mergesort",
    )
    return work.drop(columns=["_error_rank", "_running", "_pending", "_failed"]).reset_index(
        drop=True
    )


def observatory_studies_table(studies: pd.DataFrame) -> pd.DataFrame:
    """Display projection of the studies grain (plan §4.2)."""
    ranked = sort_observatory_studies(studies)
    columns = [column for column in STUDIES_TABLE_COLUMNS if column in ranked.columns]
    return ranked.reindex(columns=columns)


def inspect_selected_run_for_drill(run_name: Any) -> str:
    """Value to write onto ``studies_viewer_selected_run`` before ``switch_page``.

    Cell drill returns the run. Study-level drill returns ``""`` so a leftover
    shared name (``cell_000``) cannot stick. Do **not** ``pop`` that widget
    key — Streamlit can restore a popped value when Inspect remounts.
    """
    if run_name is None or _is_na(run_name):
        return ""
    text = str(run_name).strip()
    if not text or text in {"<NA>", "nan", "None"}:
        return ""
    return text


def study_choice_labels(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Unique study-drill labels. Duplicate ``study_name`` get ``study_dir``."""
    bases: list[str] = []
    for row in rows:
        name = row.get("study_name")
        bases.append("—" if name is None or _is_na(name) else str(name))
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    labels: list[str] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        base = bases[index]
        if counts[base] == 1:
            labels.append(base)
            continue
        directory = str(row.get("study_dir") or "").strip() or f"row-{index}"
        label = f"{base} — {directory}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} #{seen[label]}"
        labels.append(label)
    return labels


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
