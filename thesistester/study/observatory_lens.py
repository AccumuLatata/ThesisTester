"""SO3 / SO9 Program B Observatory lens (C-24 / QI-07-07).

Display-only projections (``desk_class``, ΔE vs Wave 0, useful-confluence,
heatmap). Does not write study dirs. Does not import Streamlit or Plotly.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from thesistester.study.observatory_support import (
    DESK_CLASS_ORDER,
    HEATMAP_CLASS_Z,
    HEATMAP_SOLO_PARTNER,
    HEATMAP_Z_MISSING,
    _APOC_CORES,
    _NOISY_MIN_TRADES,
    _PF_HOLD_HI,
    _PF_HOLD_LO,
    _PLUS_E_MIN,
    _PRIOR_PROFILE_CORES,
    _RUN2_STUDY_PREFIX,
    _USEFUL_DELTA_E,
    _WAVE0_APOC,
    _WAVE0_LOCK_FIELDS,
    _WAVE0_SOLO,
    _WAVE0_STUDIES,
    _WAVE0_VA,
    _coerce_number,
    _cohort_token,
    _display_token,
    _is_na,
    _status_token,
    canonical_facet_value,
    sample_class_for,
)


def desk_class_for(
    *,
    status: Any,
    sample_class: str,
    trade_count: Any,
    expectancy_r: Any,
    profit_factor: Any,
) -> str:
    """Program B desk overlay (plan §4.7). Not a quality score or Admit."""
    status_token = _status_token(status)
    if status_token == "failed":
        return "failed"
    count = _coerce_number(trade_count)
    if (
        sample_class == "missing_n"
        or status_token == "skipped"
        or (sample_class == "below_min_trades" and (count is None or count < _NOISY_MIN_TRADES))
    ):
        return "unidentified"
    if sample_class == "below_min_trades":
        return "noisy"
    if sample_class != "interpretable":
        return "unidentified"
    expectancy = _coerce_number(expectancy_r)
    profit = _coerce_number(profit_factor)
    if (
        expectancy is not None
        and profit is not None
        and expectancy >= _PLUS_E_MIN
        and profit > _PF_HOLD_HI
    ):
        return "plus_e"
    hold_by_e = expectancy is not None and abs(expectancy) < _PLUS_E_MIN
    hold_by_pf = profit is not None and _PF_HOLD_LO <= profit <= _PF_HOLD_HI
    if hold_by_e or hold_by_pf:
        return "hold"
    if expectancy is not None and expectancy < 0:
        return "dead"
    return "other"


def wave0_study_name_for_core(core: Any) -> str:
    """Tick-gated cores look up ``progB_w0_va`` / ``progB_w0_apoc``; else solo.

    Returns the canonical (Run 1) stem. Run 2 ``progB_r2_*`` Wave 0 rows
    canonicalize to the same stem so ΔE matches inside the fade lock.
    """
    token = _display_token(core)
    if token in _PRIOR_PROFILE_CORES:
        return _WAVE0_VA
    if token in _APOC_CORES:
        return _WAVE0_APOC
    return _WAVE0_SOLO


def _canonical_wave0_study_name(name: Any) -> str | None:
    """Map ``progB_w0_*`` / ``progB_r2_w0_*`` stems onto the Wave 0 set."""
    token = str(name or "").strip()
    if token.startswith(_RUN2_STUDY_PREFIX):
        token = "progB_" + token.removeprefix(_RUN2_STUDY_PREFIX)
    if token in _WAVE0_STUDIES:
        return token
    return None


def partners_nonempty(value: Any) -> bool:
    """True when ``factor_partner_levels`` is a real confirm set."""
    if value is None or _is_na(value):
        return False
    if isinstance(value, (list, tuple)):
        return any(str(item).strip() for item in value)
    text = str(value).strip()
    return bool(text) and text not in {"—", "-", "nan", "None", "null", "[]"}


def is_program_b_pair_row(row: Mapping[str, Any]) -> bool:
    """Pair cell: ``min_valid_confluences >= 1`` and non-empty partners."""
    min_valid = _coerce_number(row.get("min_valid_confluences"))
    if min_valid is None or min_valid < 1:
        return False
    return partners_nonempty(row.get("factor_partner_levels"))


def useful_confluence_for(
    *,
    sample_class: str,
    delta_e: Any,
    profit_factor: Any,
    thinning: Any,
) -> bool:
    """Boolean useful-confluence flag (plan §4.7). Not a usefulness score."""
    if sample_class != "interpretable":
        return False
    delta = _coerce_number(delta_e)
    thin = _coerce_number(thinning)
    profit = _coerce_number(profit_factor)
    if delta is None or thin is None or profit is None:
        return False
    if delta < _USEFUL_DELTA_E:
        return False
    if _PF_HOLD_LO <= profit <= _PF_HOLD_HI:
        return False
    return True


def resolve_program_b_lens(mode: str, frame: pd.DataFrame) -> bool:
    """``auto`` attaches when any filtered row is ``program_b``."""
    token = (mode or "auto").strip().lower()
    if token == "generic":
        return False
    if token == "program_b":
        return True
    if frame.empty or "lens_hint" not in frame.columns:
        return False
    return bool((frame["lens_hint"].astype(str) == "program_b").any())


def attach_program_b_projections(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``desk_class`` / ``delta_e`` / ``thinning`` / ``useful_confluence``.

    Wave 0 lookup is corpus-wide (faceting away ``w0_*`` must not null ΔE).
    Non-``program_b`` rows stay null. Not a new primary metric.
    """
    out = frame.copy()
    for column in ("desk_class", "delta_e", "thinning", "useful_confluence"):
        if column not in out.columns:
            out[column] = pd.NA
    if out.empty:
        return out
    wave0 = _wave0_lookup(out)
    desk_values: list[Any] = []
    delta_values: list[Any] = []
    thin_values: list[Any] = []
    useful_values: list[Any] = []
    for record in out.to_dict(orient="records"):
        if str(record.get("lens_hint") or "") != "program_b":
            desk_values.append(pd.NA)
            delta_values.append(pd.NA)
            thin_values.append(pd.NA)
            useful_values.append(pd.NA)
            continue
        sample = str(
            record.get("sample_class")
            or sample_class_for(record.get("trade_count"), record.get("min_trades"))
        )
        desk = desk_class_for(
            status=record.get("status"),
            sample_class=sample,
            trade_count=record.get("trade_count"),
            expectancy_r=record.get("expectancy_r"),
            profit_factor=record.get("profit_factor"),
        )
        desk_values.append(desk)
        delta = None
        thinning = None
        if is_program_b_pair_row(record):
            core = _display_token(record.get("factor_core_level"))
            key = _wave0_identity(
                record,
                study_name=wave0_study_name_for_core(core),
                core=core,
            )
            found = wave0.get(key)
            if found is not None:
                solo_e, solo_n = found
                pair_e = _coerce_number(record.get("expectancy_r"))
                pair_n = _coerce_number(record.get("trade_count"))
                if solo_e is not None and pair_e is not None:
                    delta = pair_e - solo_e
                if solo_n is not None and pair_n is not None and solo_n != 0:
                    thinning = pair_n / solo_n
        delta_values.append(delta if delta is not None else pd.NA)
        thin_values.append(thinning if thinning is not None else pd.NA)
        useful_values.append(
            useful_confluence_for(
                sample_class=sample,
                delta_e=delta,
                profit_factor=record.get("profit_factor"),
                thinning=thinning,
            )
        )
    out["desk_class"] = desk_values
    out["delta_e"] = delta_values
    out["thinning"] = thin_values
    out["useful_confluence"] = useful_values
    return out


def desk_class_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Counts for the class-count strip. Missing classes are 0."""
    counts = {name: 0 for name in DESK_CLASS_ORDER}
    if frame.empty or "desk_class" not in frame.columns:
        return counts
    series = frame["desk_class"].dropna().astype(str)
    for name, value in series.value_counts().items():
        if name in counts:
            counts[name] = int(value)
    return counts


def heatmap_class_z(desk: Any) -> int:
    """Heatmap color index. ``0`` is missing/pending (grey); ``failed`` is ``1``."""
    if desk is None or _is_na(desk):
        return HEATMAP_Z_MISSING
    token = str(desk).strip()
    if token in {"", "<NA>", "nan", "None", "null"}:
        return HEATMAP_Z_MISSING
    return HEATMAP_CLASS_Z.get(token, HEATMAP_Z_MISSING)


def program_b_heatmap_cells(frame: pd.DataFrame) -> pd.DataFrame:
    """Long ``core × partner × desk_class`` grid. Absent combos are null (grey).

    Empty Wave 0 partners become ``(solo)`` so a Wave-0-only corpus still
    heat-maps. Not an ingest inventory — axes come from observed cells.
    """
    empty = pd.DataFrame(
        columns=[
            "factor_core_level",
            "factor_partner_levels",
            "desk_class",
            "long_trade_count",
            "short_trade_count",
        ]
    )
    if frame.empty:
        return empty
    work = frame.copy()
    if "lens_hint" in work.columns:
        work = work.loc[work["lens_hint"].astype(str) == "program_b"]
    if work.empty:
        return empty
    if "factor_partner_levels" in work.columns:
        work["factor_partner_levels"] = [
            _heatmap_partner_token(value) for value in work["factor_partner_levels"].tolist()
        ]
    else:
        work["factor_partner_levels"] = HEATMAP_SOLO_PARTNER
    from thesistester.study.observatory_query import unique_facet_values

    cores = unique_facet_values(work, "factor_core_level")
    partners = unique_facet_values(work, "factor_partner_levels")
    if not cores or not partners:
        return empty
    by_cell: dict[tuple[Any, Any], dict[str, Any]] = {}
    ordered = work.sort_values(
        [column for column in ("study_name", "run_name") if column in work.columns],
        kind="mergesort",
    )
    for record in ordered.to_dict(orient="records"):
        core = canonical_facet_value(record.get("factor_core_level"))
        partner = canonical_facet_value(record.get("factor_partner_levels"))
        if core is None or partner is None:
            continue
        desk = record.get("desk_class")
        if _is_na(desk) or desk is None:
            desk = None
        else:
            desk = str(desk)
        key = (core, partner)
        if key not in by_cell:
            by_cell[key] = {
                "desk_class": desk,
                "long_trade_count": record.get("long_trade_count"),
                "short_trade_count": record.get("short_trade_count"),
            }
    rows: list[dict[str, Any]] = []
    for core in cores:
        for partner in partners:
            payload = by_cell.get((core, partner), {})
            rows.append(
                {
                    "factor_core_level": core,
                    "factor_partner_levels": partner,
                    "desk_class": payload.get("desk_class"),
                    "long_trade_count": payload.get("long_trade_count"),
                    "short_trade_count": payload.get("short_trade_count"),
                }
            )
    return pd.DataFrame(rows)


def _heatmap_partner_token(value: Any) -> str:
    """Empty Wave 0 partners stay on the heatmap as ``(solo)``."""
    if value is not None and not _is_na(value) and str(value).strip() == HEATMAP_SOLO_PARTNER:
        return HEATMAP_SOLO_PARTNER
    canonical = canonical_facet_value(value)
    if canonical is None:
        return HEATMAP_SOLO_PARTNER
    return str(canonical)


def heatmap_focus_label(core: Any, partner: Any) -> str:
    """``core × partner`` token. Empty partner → ``(solo)`` (plan §4.12)."""
    core_token = "" if core is None or _is_na(core) else str(core).strip()
    return f"{core_token} × {_heatmap_partner_token(partner)}"


def parse_heatmap_focus_label(label: Any) -> tuple[str, str] | None:
    """Split a heatmap-cell label. ``(solo)`` partner → empty string. Fail closed."""
    if label is None or _is_na(label):
        return None
    text = str(label).strip()
    if " × " not in text:
        return None
    core, partner = text.split(" × ", 1)
    core = core.strip()
    partner = partner.strip()
    if not core:
        return None
    if partner == HEATMAP_SOLO_PARTNER:
        return (core, "")
    return (core, partner)


def heatmap_focus_pending_facets(label: Any) -> dict[str, list[Any]]:
    """Core / Partner widget values for a heatmap-cell label (plan §4.12)."""
    parsed = parse_heatmap_focus_label(label)
    if parsed is None:
        return {"factor_core_level": [], "factor_partner_levels": []}
    core, partner = parsed
    pending: dict[str, list[Any]] = {"factor_core_level": [core] if core else []}
    # Empty partner is a real Wave 0 cell. [] would mean "no partner filter"
    # and keep every pair that shares the core (plan §4.12 / §6.11).
    pending["factor_partner_levels"] = [partner] if partner else [HEATMAP_SOLO_PARTNER]
    return pending


def _wave0_identity(record: Mapping[str, Any], *, study_name: str, core: str) -> tuple[str, ...]:
    """Wave 0 match key: study + core + lock fields except ``min_valid_confluences``.

    Pair rows use ``min_valid=1`` so they never share a full ``cohort_key``
    with Wave 0. Instrument / dataset / ingest (and the rest of the lock)
    must still match — otherwise ΔE would mix books. Two dirs with the
    same identity still fail closed.
    """
    return (
        study_name,
        core,
        *(_cohort_token(record.get(field)) for field in _WAVE0_LOCK_FIELDS),
    )


def _wave0_lookup(
    frame: pd.DataFrame,
) -> dict[tuple[str, ...], tuple[float | None, float | None] | None]:
    """``identity → (E, n)`` when exactly one Wave 0 cell; else ``None``."""
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    if frame.empty:
        return {}
    for record in frame.to_dict(orient="records"):
        if str(record.get("lens_hint") or "") != "program_b":
            continue
        name = _canonical_wave0_study_name(record.get("study_name"))
        if name is None:
            continue
        if is_program_b_pair_row(record):
            continue
        core = _display_token(record.get("factor_core_level"))
        if not core:
            continue
        groups.setdefault(_wave0_identity(record, study_name=name, core=core), []).append(record)
    out: dict[tuple[str, ...], tuple[float | None, float | None] | None] = {}
    for key, rows in groups.items():
        if len(rows) != 1:
            out[key] = None
            continue
        out[key] = (
            _coerce_number(rows[0].get("expectancy_r")),
            _coerce_number(rows[0].get("trade_count")),
        )
    return out
