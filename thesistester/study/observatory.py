"""SO1–SO4 Study Observatory — fact table, Program B lens, saved desks.

Concatenates existing ``results_index.csv`` ⟕ ``study.expansion.json`` plus
StudySpec locks across SV1 catalog hits. SO3 attaches optional Program B
projections (``desk_class``, ΔE vs Wave 0, thinning, useful-confluence).
SO4 persists query-only desks under the ThesisTester store. Does not call
``report_study``, ``rollup_study``, or ``run_study``. Does not unzip cell
bundles. Does not write ``results/studies/``.

This module must not import Streamlit, Plotly, ``execute``, ``cli_study``,
``thesistester.cli``, ``launch``, ``builder``, ``promote``, ``tools``, or
``rollup``.
"""

from __future__ import annotations

import json
import math
import numbers
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from thesistester.levels.catalog import PRIOR_PROFILE_LEVEL_NAMES
from thesistester.persistence.local_store import get_store_root
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
_PRIOR_PROFILE_CORES = frozenset(PRIOR_PROFILE_LEVEL_NAMES)
_WAVE0_SOLO = "progB_w0_solo"
_WAVE0_VA = "progB_w0_va"
DESK_CLASS_ORDER: tuple[str, ...] = (
    "plus_e",
    "hold",
    "dead",
    "other",
    "noisy",
    "unidentified",
    "failed",
)
# Heatmap z: 0 = missing/pending (grey). failed is 1 so it is not grey.
HEATMAP_Z_MISSING = 0
HEATMAP_CLASS_Z: dict[str, int] = {
    "failed": 1,
    "unidentified": 2,
    "noisy": 3,
    "other": 4,
    "dead": 5,
    "hold": 6,
    "plus_e": 7,
}
HEATMAP_Z_MAX = 7
HEATMAP_SOLO_PARTNER = "(solo)"
# Lens chrome only — not ingest inventory (plan §4.6 / §6.4).
PROGRAM_B_LENS_PACKET_CHROME = (
    "15s operator packet: 23 files. Parked VA packet: 4 files. "
    "These counts are lens chrome, not catalog membership."
)
_WAVE0_LOCK_FIELDS: tuple[str, ...] = tuple(
    field for field in COHORT_FIELDS if field != "min_valid_confluences"
)
_PF_HOLD_LO = 0.95
_PF_HOLD_HI = 1.05
_PLUS_E_MIN = 0.03
_USEFUL_DELTA_E = 0.03
_NOISY_MIN_TRADES = 15.0
DESK_SCHEMA_VERSION = 1
DESK_STORE_NAMESPACE = "study_observatory"
DESK_STORE_DIRNAME = "desks"
DESK_LENS_MODES: frozenset[str] = frozenset({"auto", "program_b", "generic"})
DESK_FACET_COLUMNS: tuple[str, ...] = (
    "instrument",
    "setup_kind",
    "factor_core_level",
    "factor_partner_levels",
    "study_name",
    "status",
    "sample_class",
    "stop_loss_ticks",
    "take_profit_ticks",
    "ingestion_mode",
)
_DESK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")


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
    """PRIOR_PROFILE cores look up ``progB_w0_va``; else ``progB_w0_solo``."""
    token = _display_token(core)
    if token in _PRIOR_PROFILE_CORES:
        return _WAVE0_VA
    return _WAVE0_SOLO


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
    empty = pd.DataFrame(columns=["factor_core_level", "factor_partner_levels", "desk_class"])
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
    cores = unique_facet_values(work, "factor_core_level")
    partners = unique_facet_values(work, "factor_partner_levels")
    if not cores or not partners:
        return empty
    by_cell: dict[tuple[Any, Any], str | None] = {}
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
            by_cell[key] = desk
    rows: list[dict[str, Any]] = []
    for core in cores:
        for partner in partners:
            rows.append(
                {
                    "factor_core_level": core,
                    "factor_partner_levels": partner,
                    "desk_class": by_cell.get((core, partner)),
                }
            )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class ObservatoryDesk:
    """Saved Observatory query. Not a fact table and not a validated edge."""

    id: str
    name: str
    facets: Mapping[str, tuple[Any, ...]]
    cohort_lock: bool
    break_comparability: bool
    active_cohort: str | None
    lens: str
    sort_column: str
    schema_version: int = DESK_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "id": self.id,
            "name": self.name,
            "facets": {key: list(values) for key, values in self.facets.items()},
            "cohort_lock": bool(self.cohort_lock),
            "break_comparability": bool(self.break_comparability),
            "active_cohort": self.active_cohort,
            "lens": self.lens,
            "sort_column": self.sort_column,
        }


def observatory_desks_dir(*, store_root: Path | None = None) -> Path:
    """``{store}/study_observatory/desks``. Never a study ``output_dir``."""
    root = Path(store_root).resolve() if store_root is not None else get_store_root()
    return root / DESK_STORE_NAMESPACE / DESK_STORE_DIRNAME


def observatory_desk_query_state(desk: ObservatoryDesk) -> dict[str, Any]:
    """Map a desk onto query fields the page restores. Not a fact table."""
    facets = {column: list(desk.facets.get(column, ())) for column in DESK_FACET_COLUMNS}
    return {
        "saved_desk_id": desk.id,
        "name": desk.name,
        "facets": facets,
        "cohort_lock": bool(desk.cohort_lock),
        "break_comparability": bool(desk.break_comparability),
        "active_cohort": desk.active_cohort,
        "lens": desk.lens,
        "sort_column": desk.sort_column,
    }


def list_observatory_desks(
    *,
    store_root: Path | None = None,
) -> tuple[tuple[ObservatoryDesk, ...], tuple[str, ...]]:
    """Load schema-v1 desks. Missing dir is empty. Corrupt / v2 files ignored."""
    directory = observatory_desks_dir(store_root=store_root)
    if not directory.is_dir():
        return (), ()
    try:
        paths = sorted(directory.glob("*.json"), key=lambda item: item.name)
    except OSError:
        return (), ()
    desks: list[ObservatoryDesk] = []
    ignored: list[str] = []
    for path in paths:
        try:
            desk = parse_observatory_desk(path)
        except (OSError, TypeError, ValueError, KeyError):
            ignored.append(path.name)
            continue
        if desk is None:
            ignored.append(path.name)
            continue
        desks.append(desk)
    desks.sort(key=lambda item: (item.name.lower(), item.id))
    return tuple(desks), tuple(ignored)


def save_observatory_desk(
    *,
    name: str,
    facets: Mapping[str, Sequence[Any]] | None = None,
    cohort_lock: bool = True,
    break_comparability: bool = False,
    active_cohort: str | None = None,
    lens: str = "auto",
    sort_column: str = "expectancy_r",
    desk_id: str | None = None,
    store_root: Path | None = None,
) -> ObservatoryDesk:
    """Persist query state only. Creates the store sidecar on first save."""
    directory = observatory_desks_dir(store_root=store_root)
    ident = _resolve_save_desk_id(desk_id, name)
    desk = ObservatoryDesk(
        id=ident,
        name=_normalize_desk_name(name),
        facets=_normalize_desk_facets(facets),
        cohort_lock=bool(cohort_lock),
        break_comparability=bool(break_comparability),
        active_cohort=_normalize_optional_token(active_cohort),
        lens=_normalize_desk_lens(lens),
        sort_column=_normalize_desk_sort(sort_column),
        schema_version=DESK_SCHEMA_VERSION,
    )
    _atomic_write_desk_json(directory / f"{desk.id}.json", desk.to_payload())
    return desk


def delete_observatory_desk(desk_id: str, *, store_root: Path | None = None) -> bool:
    """Delete one desk JSON. Unknown / unsafe ids are a no-op."""
    ident = _normalize_desk_id(desk_id)
    if ident is None:
        return False
    directory = observatory_desks_dir(store_root=store_root)
    path = directory / f"{ident}.json"
    try:
        resolved_dir = directory.resolve()
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.parent != resolved_dir or not resolved.is_file():
        return False
    resolved.unlink()
    return True


def parse_observatory_desk(path: Path) -> ObservatoryDesk | None:
    """Return a v1 desk or ``None`` when the file is corrupt / unknown schema.

    Must not raise — a bad sidecar cannot fail Observatory page load.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return observatory_desk_from_payload(payload, file_stem=path.stem)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ObservatoryError,
        TypeError,
        ValueError,
    ):
        return None


def observatory_desk_from_payload(
    payload: Any,
    *,
    file_stem: str | None = None,
) -> ObservatoryDesk | None:
    """Parse an in-memory desk payload. Filename stem must match ``id`` when given."""
    if not isinstance(payload, Mapping):
        return None
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != DESK_SCHEMA_VERSION:
        return None
    ident = _normalize_desk_id(payload.get("id") or file_stem)
    if ident is None:
        return None
    if file_stem is not None and file_stem != ident:
        return None
    raw_name = payload.get("name")
    if raw_name is not None and not isinstance(raw_name, str):
        return None
    facets = payload.get("facets")
    if facets is not None and not isinstance(facets, Mapping):
        return None
    try:
        return ObservatoryDesk(
            id=ident,
            name=_normalize_desk_name(raw_name or ident),
            facets=_normalize_desk_facets(facets if isinstance(facets, Mapping) else None),
            cohort_lock=_coerce_desk_bool(payload.get("cohort_lock", True), default=True),
            break_comparability=_coerce_desk_bool(
                payload.get("break_comparability", False),
                default=False,
            ),
            active_cohort=_normalize_optional_token(payload.get("active_cohort")),
            lens=_normalize_desk_lens(payload.get("lens")),
            sort_column=_normalize_desk_sort(payload.get("sort_column")),
            schema_version=DESK_SCHEMA_VERSION,
        )
    except (ObservatoryError, TypeError, ValueError):
        return None


def _normalize_desk_name(name: Any) -> str:
    text = str(name or "").strip()
    return text[:80] if text else "Desk"


def _new_desk_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_desk_name(name).lower()).strip("-")
    token = slug[:40] or "desk"
    return f"{token}-{uuid.uuid4().hex[:8]}"


def _resolve_save_desk_id(desk_id: Any, name: str) -> str:
    if desk_id is None or (isinstance(desk_id, str) and not desk_id.strip()):
        return _new_desk_id(name)
    if not isinstance(desk_id, str):
        raise ObservatoryError("saved-desk id must be a string")
    ident = _normalize_desk_id(desk_id)
    if ident is None:
        raise ObservatoryError(f"Invalid saved-desk id: {desk_id!r}")
    return ident


def _normalize_desk_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not _DESK_ID_RE.match(token):
        return None
    return token


def _normalize_optional_token(value: Any) -> str | None:
    if value is None or _is_na(value):
        return None
    if not isinstance(value, str):
        raise ObservatoryError("desk token field must be a string or null")
    text = value.strip()
    if not text or text in {"<NA>", "nan", "None", "null"}:
        return None
    return text


def _coerce_desk_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ObservatoryError("desk boolean field must be true, false, or omitted")


def _normalize_desk_lens(value: Any) -> str:
    if value is None:
        return "auto"
    if not isinstance(value, str):
        raise ObservatoryError("desk lens must be a string")
    token = value.strip().lower()
    return token if token in DESK_LENS_MODES else "auto"


def _normalize_desk_sort(value: Any) -> str:
    if value is None:
        return "expectancy_r"
    if not isinstance(value, str):
        raise ObservatoryError("desk sort_column must be a string")
    token = value.strip()
    return token if token in SORT_ALLOW_LIST else "expectancy_r"


def _as_facet_sequence(raw: Any) -> Sequence[Any]:
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
        raise ObservatoryError("desk facet values must be a list")
    return raw


def _normalize_desk_facets(
    facets: Mapping[str, Sequence[Any]] | None,
) -> MappingProxyType:
    cleaned: dict[str, tuple[Any, ...]] = {}
    if not facets:
        return MappingProxyType(cleaned)
    if not isinstance(facets, Mapping):
        raise ObservatoryError("desk facets must be an object")
    for column in DESK_FACET_COLUMNS:
        raw = facets.get(column)
        if raw is None:
            continue
        values: list[Any] = []
        seen: set[Any] = set()
        for item in _as_facet_sequence(raw):
            canonical = canonical_facet_value(item)
            if canonical is None or canonical in seen:
                continue
            seen.add(canonical)
            values.append(canonical)
        if values:
            cleaned[column] = tuple(values)
    return MappingProxyType(cleaned)


def _atomic_write_desk_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write ``<id>.json`` inside the desks dir. Never follows a symlink out."""
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    resolved_dir = directory.resolve()
    resolved = (resolved_dir / path.name).resolve()
    if resolved.parent != resolved_dir:
        raise ObservatoryError("saved-desk path escaped the desks directory")
    tmp = resolved.with_name(f".{resolved.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(resolved)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _heatmap_partner_token(value: Any) -> str:
    """Empty Wave 0 partners stay on the heatmap as ``(solo)``."""
    canonical = canonical_facet_value(value)
    if canonical is None:
        return HEATMAP_SOLO_PARTNER
    return str(canonical)


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
        name = str(record.get("study_name") or "")
        if name not in {_WAVE0_SOLO, _WAVE0_VA}:
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


def _status_token(value: Any) -> str:
    if value is None or _is_na(value):
        return ""
    return str(value).strip().lower()


def apply_facets(
    frame: pd.DataFrame,
    facets: Mapping[str, Sequence[Any]] | None = None,
) -> pd.DataFrame:
    """Keep rows whose facet columns are in the provided value sets.

    Numeric tokens use :func:`canonical_facet_value` so ``80`` and ``80.0``
    match (same honesty as ``cohort_key`` integer tokens). Raw ``isin``
    would hide one lock when YAML stored an int and pandas upcast a float.
    """
    if frame.empty or not facets:
        return frame.copy()
    mask = pd.Series(True, index=frame.index)
    for column, raw_values in facets.items():
        if column not in frame.columns:
            continue
        allowed = {canonical_facet_value(value) for value in raw_values}
        allowed.discard(None)
        if not allowed:
            continue
        mask = mask & frame[column].map(canonical_facet_value).isin(allowed)
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
        canonical = canonical_facet_value(value)
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        values.append(canonical)
    return sorted(values, key=_facet_sort_key)


def canonical_facet_value(value: Any) -> Any:
    """Stable facet token. ``80`` / ``80.0`` / ``np.int64(80)`` → ``80``."""
    if value is None or _is_na(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return None
        if math.isfinite(number) and number.is_integer():
            return int(number)
        return number
    boxed = _box_scalar(value)
    if boxed is not value:
        return canonical_facet_value(boxed)
    text = str(value).strip()
    return text if text else None


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


def _facet_sort_key(value: Any) -> tuple[int, float | str]:
    if isinstance(value, bool):
        return (2, "true" if value else "false")
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return (0, float(value))
    return (1, str(value))


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
