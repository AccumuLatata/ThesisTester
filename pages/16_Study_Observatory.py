"""SO2–SO4 / SO7–SO9 Study Observatory — corpus page, lens, desks, studies pane.

Read-only corpus page. Does not execute studies, write report artifacts,
or hydrate classic research session keys. Desks persist query state only
under the ThesisTester store — never under ``results/studies/``. SO7
surfaces the existing studies grain (ledger progress + study-level Inspect
drill) without inventing cell rows. SO8 labels Active cohort without
changing the raw ``cohort_key``. SO9 facets ``desk_class`` /
``useful_confluence`` when the Program B lens is on and focuses the
heatmap through existing Core / Partner facets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import thesistester.study.observatory as _observatory

# Page-local session keys. Do not from-import these names from observatory.py.
OBSERVATORY_CACHED_MODEL_KEY = "observatory_cached_model"
OBSERVATORY_CACHE_STAMP_KEY = "observatory_cache_stamp"
OBSERVATORY_FACET_STATE_KEY = "observatory_facet_state"
OBSERVATORY_COHORT_LOCK_KEY = "observatory_cohort_lock"
OBSERVATORY_BREAK_COMPARABILITY_KEY = "observatory_break_comparability"
OBSERVATORY_SORT_COLUMN_KEY = "observatory_sort_column"
OBSERVATORY_SELECTED_RUN_KEY = "observatory_selected_run"
OBSERVATORY_COHORT_PICK_KEY = "observatory_cohort_pick"
OBSERVATORY_CELL_SELECT_KEY = "observatory_cell_select"
OBSERVATORY_ACTIVE_LENS_KEY = "observatory_active_lens"
OBSERVATORY_SAVED_DESK_KEY = "observatory_saved_desk_id"
OBSERVATORY_DESK_NAME_KEY = "observatory_desk_name"
OBSERVATORY_STUDY_SELECT_KEY = "observatory_study_select"
OBSERVATORY_SELECTED_STUDY_KEY = "observatory_selected_study"
# One-shot keys. Applied in ``_ensure_defaults`` before any desk widgets exist.
# Mutating a widget-bound key after ``st.selectbox`` / ``st.checkbox`` raises.
OBSERVATORY_PENDING_DESK_KEY = "_observatory_pending_desk"
OBSERVATORY_PENDING_SAVED_ID_KEY = "_observatory_pending_saved_desk_id"
OBSERVATORY_PENDING_FACETS_KEY = "_observatory_pending_facets"
OBSERVATORY_HEATMAP_CELL_KEY = "observatory_heatmap_cell"

# Existing Studies drill keys (same strings as pages/15_Studies.py).
STUDIES_VIEWER_DIR_KEY = "studies_viewer_study_dir"
STUDIES_VIEWER_PENDING_PATH_KEY = "studies_viewer_pending_path"
STUDIES_VIEWER_CACHED_MODEL_KEY = "studies_viewer_cached_model"
STUDIES_VIEWER_CACHED_MODEL_DIR_KEY = "studies_viewer_cached_model_dir"
STUDIES_VIEWER_SELECTED_RUN_KEY = "studies_viewer_selected_run"

_HONESTY_FALLBACK = (
    "Descriptive screen of completed study cells. Ranking many cells is "
    "multiple-testing, not a validated edge. Sort is within a comparability "
    "cohort unless you break the lock. Catalog membership is not a quality score."
)
_EMPTY_CATALOG = (
    "No local studies found under `results/studies/` or `out/`. "
    "Paste a path on Studies — an empty catalog is not an error. "
    "Listing still lives on Studies."
)
_TABLE_DISPLAY_CAP = 200
_FACET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("instrument", "Instrument"),
    ("setup_kind", "Setup kind"),
    ("factor_core_level", "Core level"),
    ("factor_partner_levels", "Partner levels"),
    ("study_name", "Study name"),
    ("status", "Status"),
    ("sample_class", "Sample class"),
    ("stop_loss_ticks", "Stop loss (ticks)"),
    ("take_profit_ticks", "Take profit (ticks)"),
    ("ingestion_mode", "Ingestion"),
    ("directional_integrity", "Directional integrity"),
)
_TABLE_COLUMNS: tuple[str, ...] = (
    "study_name",
    "run_name",
    "instrument",
    "setup_kind",
    "trade_count",
    "long_trade_count",
    "short_trade_count",
    "long_share",
    "expectancy_r",
    "profit_factor",
    "win_rate",
    "status",
    "sample_class",
    "cohort_key",
    "study_dir",
)
_LENS_TABLE_COLUMNS: tuple[str, ...] = (
    "desk_class",
    "delta_e",
    "thinning",
    "useful_confluence",
)
_LENS_MODES: tuple[str, ...] = ("auto", "program_b", "generic")
_DELTA_E_CAPTION = (
    "ΔE mixes confirm value with zone-shape (point vs partner box) — "
    "not a pure confluence effect. +E is not Admit. "
    "n<15 is unidentified; 15≤n<30 is noisy (not +E). "
    "Do not write these numbers onto the Program A scalp map."
)
_PACKET_CHROME_FALLBACK = (
    "15s operator packet: 23 files. Parked VA packet: 4 files. "
    "These counts are lens chrome, not catalog membership."
)
_LENS_FACET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("desk_class", "desk_class"),
    ("useful_confluence", "useful_confluence"),
)
_INERT_LENS_FACETS = "Saved lens facets are inert until the Program B lens is on."
_HEATMAP_FOCUS_CAPTION = (
    "Heatmap focus writes the Core / Partner facets. "
    "Clear those facets to see the full heatmap again."
)

load_observatory_frame = getattr(_observatory, "load_observatory_frame", None)
apply_facets = getattr(_observatory, "apply_facets", None)
sort_observatory_frame = getattr(_observatory, "sort_observatory_frame", None)
majority_cohort_key = getattr(_observatory, "majority_cohort_key", None)
format_cohort_label = getattr(_observatory, "format_cohort_label", None)
cohort_choice_labels = getattr(_observatory, "cohort_choice_labels", None)
cohort_differ_fields = getattr(_observatory, "cohort_differ_fields", None)
unique_facet_values = getattr(_observatory, "unique_facet_values", None)
displayed_min_trades = getattr(_observatory, "displayed_min_trades", None)
constrain_facet_selection = getattr(_observatory, "constrain_facet_selection", None)
cell_choice_labels = getattr(_observatory, "cell_choice_labels", None)
SORT_ALLOW_LIST = getattr(_observatory, "SORT_ALLOW_LIST", frozenset({"expectancy_r"}))
COHORT_FIELDS = getattr(_observatory, "COHORT_FIELDS", ())
OBSERVATORY_HONESTY = getattr(_observatory, "OBSERVATORY_HONESTY", _HONESTY_FALLBACK)
ObservatoryModel = getattr(_observatory, "ObservatoryModel", None)
ObservatoryError = getattr(_observatory, "ObservatoryError", ValueError)
attach_program_b_projections = getattr(_observatory, "attach_program_b_projections", None)
resolve_program_b_lens = getattr(_observatory, "resolve_program_b_lens", None)
desk_class_counts = getattr(_observatory, "desk_class_counts", None)
program_b_heatmap_cells = getattr(_observatory, "program_b_heatmap_cells", None)
heatmap_class_z = getattr(_observatory, "heatmap_class_z", None)
DESK_CLASS_ORDER = getattr(
    _observatory,
    "DESK_CLASS_ORDER",
    ("plus_e", "hold", "dead", "other", "noisy", "unidentified", "failed"),
)
HEATMAP_Z_MAX = getattr(_observatory, "HEATMAP_Z_MAX", 7)
PROGRAM_B_LENS_PACKET_CHROME = getattr(
    _observatory,
    "PROGRAM_B_LENS_PACKET_CHROME",
    _PACKET_CHROME_FALLBACK,
)
list_observatory_desks = getattr(_observatory, "list_observatory_desks", None)
save_observatory_desk = getattr(_observatory, "save_observatory_desk", None)
delete_observatory_desk = getattr(_observatory, "delete_observatory_desk", None)
observatory_desk_query_state = getattr(_observatory, "observatory_desk_query_state", None)
observatory_desk_from_payload = getattr(_observatory, "observatory_desk_from_payload", None)
corpus_progress_counts = getattr(_observatory, "corpus_progress_counts", None)
directional_integrity_counts = getattr(_observatory, "directional_integrity_counts", None)
format_heatmap_direction_count = getattr(_observatory, "format_heatmap_direction_count", None)
sort_observatory_studies = getattr(_observatory, "sort_observatory_studies", None)
observatory_studies_table = getattr(_observatory, "observatory_studies_table", None)
study_choice_labels = getattr(_observatory, "study_choice_labels", None)
inspect_selected_run_for_drill = getattr(_observatory, "inspect_selected_run_for_drill", None)
heatmap_focus_label = getattr(_observatory, "heatmap_focus_label", None)
parse_heatmap_focus_label = getattr(_observatory, "parse_heatmap_focus_label", None)
heatmap_focus_pending_facets = getattr(_observatory, "heatmap_focus_pending_facets", None)
query_facets_for_frame = getattr(_observatory, "query_facets_for_frame", None)
HEATMAP_SOLO_PARTNER = getattr(_observatory, "HEATMAP_SOLO_PARTNER", "(solo)")
LENS_FACET_COLUMNS = getattr(
    _observatory, "LENS_FACET_COLUMNS", ("desk_class", "useful_confluence")
)


def _helpers_ready() -> bool:
    return all(
        callable(fn)
        for fn in (
            load_observatory_frame,
            apply_facets,
            sort_observatory_frame,
            majority_cohort_key,
            format_cohort_label,
            cohort_choice_labels,
            cohort_differ_fields,
            unique_facet_values,
            displayed_min_trades,
            constrain_facet_selection,
            cell_choice_labels,
            attach_program_b_projections,
            resolve_program_b_lens,
            desk_class_counts,
            program_b_heatmap_cells,
            heatmap_class_z,
            list_observatory_desks,
            save_observatory_desk,
            delete_observatory_desk,
            observatory_desk_query_state,
            observatory_desk_from_payload,
            corpus_progress_counts,
            directional_integrity_counts,
            format_heatmap_direction_count,
            sort_observatory_studies,
            observatory_studies_table,
            study_choice_labels,
            inspect_selected_run_for_drill,
            heatmap_focus_label,
            parse_heatmap_focus_label,
            heatmap_focus_pending_facets,
            query_facets_for_frame,
        )
    )


def _ensure_defaults() -> None:
    pending = st.session_state.pop(OBSERVATORY_PENDING_DESK_KEY, None)
    desk = None
    if isinstance(pending, dict) and observatory_desk_from_payload is not None:
        desk = observatory_desk_from_payload(pending)
    elif pending is not None:
        desk = pending
    if desk is not None:
        _apply_observatory_desk(desk)
    pending_facets = st.session_state.pop(OBSERVATORY_PENDING_FACETS_KEY, None)
    if isinstance(pending_facets, dict):
        for column, values in pending_facets.items():
            if column in {name for name, _label in _FACET_COLUMNS}:
                st.session_state[f"observatory_facet_{column}"] = list(values) if values else []
    if OBSERVATORY_PENDING_SAVED_ID_KEY in st.session_state:
        st.session_state[OBSERVATORY_SAVED_DESK_KEY] = str(
            st.session_state.pop(OBSERVATORY_PENDING_SAVED_ID_KEY) or ""
        )
    if OBSERVATORY_COHORT_LOCK_KEY not in st.session_state:
        st.session_state[OBSERVATORY_COHORT_LOCK_KEY] = True
    if OBSERVATORY_BREAK_COMPARABILITY_KEY not in st.session_state:
        st.session_state[OBSERVATORY_BREAK_COMPARABILITY_KEY] = False
    if OBSERVATORY_SORT_COLUMN_KEY not in st.session_state:
        st.session_state[OBSERVATORY_SORT_COLUMN_KEY] = "expectancy_r"
    if OBSERVATORY_ACTIVE_LENS_KEY not in st.session_state:
        st.session_state[OBSERVATORY_ACTIVE_LENS_KEY] = "auto"
    if OBSERVATORY_SAVED_DESK_KEY not in st.session_state:
        st.session_state[OBSERVATORY_SAVED_DESK_KEY] = ""


def _last_stamp_label(model: Any) -> str:
    mtimes: list[float] = []
    studies = getattr(model, "studies", None)
    if isinstance(studies, pd.DataFrame) and not studies.empty and "mtime" in studies.columns:
        for raw in studies["mtime"].tolist():
            try:
                mtimes.append(float(raw))
            except (TypeError, ValueError):
                continue
    stamp = getattr(model, "stamp", {}) or {}
    for items in stamp.values():
        for _name, raw in items:
            try:
                mtimes.append(float(raw))
            except (TypeError, ValueError):
                continue
    if not mtimes:
        return "—"
    latest = datetime.fromtimestamp(max(mtimes), tz=timezone.utc)
    return latest.strftime("%Y-%m-%d %H:%M:%S UTC")


def _open_in_inspect(study_dir: str, run_name: str | None) -> None:
    """Drill into Studies Inspect. Pops Inspect cache so the dir reloads."""
    st.session_state[STUDIES_VIEWER_DIR_KEY] = study_dir
    st.session_state[STUDIES_VIEWER_PENDING_PATH_KEY] = study_dir
    # Always assign. Do not pop the widget key — Streamlit can restore a
    # leftover cell from another dir (shared names like cell_000).
    clearer = inspect_selected_run_for_drill
    st.session_state[STUDIES_VIEWER_SELECTED_RUN_KEY] = (
        clearer(run_name) if callable(clearer) else ""
    )
    st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_KEY, None)
    st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY, None)
    st.switch_page("pages/15_Studies.py")


def _apply_observatory_desk(desk: Any) -> None:
    """Restore query widgets from a saved desk. Does not mutate the fact table.

    Must run before facet / cohort / lens / sort / desk widgets are instantiated.
    """
    state = (
        observatory_desk_query_state(desk)
        if observatory_desk_query_state is not None
        else {
            "saved_desk_id": getattr(desk, "id", ""),
            "name": getattr(desk, "name", ""),
            "facets": dict(getattr(desk, "facets", {}) or {}),
            "cohort_lock": bool(getattr(desk, "cohort_lock", True)),
            "break_comparability": bool(getattr(desk, "break_comparability", False)),
            "active_cohort": getattr(desk, "active_cohort", None),
            "lens": getattr(desk, "lens", None) or "auto",
            "sort_column": getattr(desk, "sort_column", None) or "expectancy_r",
        }
    )
    st.session_state[OBSERVATORY_SAVED_DESK_KEY] = str(state.get("saved_desk_id") or "")
    st.session_state[OBSERVATORY_COHORT_LOCK_KEY] = bool(state.get("cohort_lock", True))
    st.session_state[OBSERVATORY_BREAK_COMPARABILITY_KEY] = bool(
        state.get("break_comparability", False)
    )
    st.session_state[OBSERVATORY_SORT_COLUMN_KEY] = str(state.get("sort_column") or "expectancy_r")
    st.session_state[OBSERVATORY_ACTIVE_LENS_KEY] = str(state.get("lens") or "auto")
    name = str(state.get("name") or "").strip()
    if name:
        st.session_state[OBSERVATORY_DESK_NAME_KEY] = name
    cohort = state.get("active_cohort")
    if cohort:
        st.session_state[OBSERVATORY_COHORT_PICK_KEY] = str(cohort)
    else:
        st.session_state.pop(OBSERVATORY_COHORT_PICK_KEY, None)
    desk_facets = dict(state.get("facets") or {})
    for column, _label in _FACET_COLUMNS:
        values = desk_facets.get(column, ())
        st.session_state[f"observatory_facet_{column}"] = list(values) if values else []
    for column in LENS_FACET_COLUMNS:
        values = desk_facets.get(column, ())
        st.session_state[f"observatory_facet_{column}"] = list(values) if values else []


def _render_saved_desks(
    *,
    facets: dict[str, list[Any]],
    cohort_lock: bool,
    break_comparability: bool,
    active_cohort: str | None,
    lens_mode: str,
    sort_column: str,
) -> None:
    st.markdown("### Saved desks")
    st.caption(
        "A saved desk is a query (facets / cohort / lens / sort), not a validated edge. "
        "Sidecars live under the ThesisTester store, not under results/studies/."
    )
    desks, ignored = list_observatory_desks()
    if ignored:
        st.caption(f"Ignored {len(ignored)} saved-desk file(s) (unknown schema or corrupt).")
    by_id = {desk.id: desk for desk in desks}
    options = [""] + [desk.id for desk in desks]
    labels = {"": "(none)"}
    labels.update({desk.id: f"{desk.name} ({desk.id})" for desk in desks})
    if st.session_state.get(OBSERVATORY_SAVED_DESK_KEY) not in options:
        st.session_state[OBSERVATORY_SAVED_DESK_KEY] = ""
    picked = st.selectbox(
        "Saved desk",
        options=options,
        format_func=lambda ident: labels.get(ident, ident),
        key=OBSERVATORY_SAVED_DESK_KEY,
        help="Load or delete a stored query. Empty store is normal.",
    )
    if OBSERVATORY_DESK_NAME_KEY not in st.session_state:
        st.session_state[OBSERVATORY_DESK_NAME_KEY] = ""
    name = st.text_input(
        "Desk name",
        key=OBSERVATORY_DESK_NAME_KEY,
        help="Name for Save desk. Default is Desk.",
    )
    actions = st.columns(3)
    load = actions[0].button("Load desk", disabled=not bool(picked))
    delete = actions[1].button("Delete desk", disabled=not bool(picked))
    save = actions[2].button("Save desk")
    if load and picked and picked in by_id:
        # Defer widget writes until the next run — keys are already bound this run.
        st.session_state[OBSERVATORY_PENDING_DESK_KEY] = by_id[picked].to_payload()
        st.rerun()
    if delete and picked:
        try:
            delete_observatory_desk(str(picked))
        except OSError as exc:
            st.error(str(exc))
        else:
            st.session_state[OBSERVATORY_PENDING_SAVED_ID_KEY] = ""
            st.rerun()
    if save:
        existing = by_id.get(str(picked)) if picked else None
        desk_name = str(name or "").strip() or (existing.name if existing is not None else "")
        try:
            desk = save_observatory_desk(
                name=desk_name,
                facets=facets,
                cohort_lock=cohort_lock,
                break_comparability=break_comparability,
                active_cohort=active_cohort,
                lens=lens_mode,
                sort_column=sort_column,
                desk_id=str(picked) if picked else None,
            )
        except (OSError, ObservatoryError) as exc:
            st.error(str(exc))
        else:
            st.session_state[OBSERVATORY_PENDING_SAVED_ID_KEY] = desk.id
            st.rerun()


def _load_model(*, refresh: bool) -> Any:
    prior = None
    if not refresh:
        cached = st.session_state.get(OBSERVATORY_CACHED_MODEL_KEY)
        if ObservatoryModel is None or isinstance(cached, ObservatoryModel):
            prior = cached
    model = load_observatory_frame(prior=prior)
    st.session_state[OBSERVATORY_CACHED_MODEL_KEY] = model
    st.session_state[OBSERVATORY_CACHE_STAMP_KEY] = (
        getattr(model, "discover_stamp", ""),
        dict(getattr(model, "stamp", {}) or {}),
    )
    return model


def _render_studies_pane(studies: pd.DataFrame) -> None:
    """Catalog-dir grain. Ledger-only dirs stay here — never as fake cells."""
    st.markdown("### Studies")
    st.caption(
        "One row per catalog dir. Ledger-only dirs appear here, not as invented "
        "cell rows. Counts are ledger status, not a quality score."
    )
    if studies.empty:
        st.caption("No catalog study dirs in this load.")
        return
    ranked = observatory_studies_table(studies)
    shown = ranked.head(_TABLE_DISPLAY_CAP)
    if len(ranked) > _TABLE_DISPLAY_CAP:
        st.caption(f"Showing {_TABLE_DISPLAY_CAP} of {len(ranked)} studies.")
    st.dataframe(shown, hide_index=True, width="stretch")
    records = shown.to_dict(orient="records")
    labels = study_choice_labels(records)
    if not labels:
        return
    if st.session_state.get(OBSERVATORY_STUDY_SELECT_KEY) not in labels:
        st.session_state[OBSERVATORY_STUDY_SELECT_KEY] = labels[0]
    chosen = st.selectbox(
        "Study",
        options=labels,
        key=OBSERVATORY_STUDY_SELECT_KEY,
        help="Open the selected catalog dir in Studies Inspect. Does not pick a cell.",
    )
    picked = records[labels.index(chosen)]
    study_dir = str(picked.get("study_dir") or "").strip()
    st.session_state[OBSERVATORY_SELECTED_STUDY_KEY] = study_dir
    if st.button("Open study in Inspect"):
        if not study_dir:
            st.error("Selected study has no study_dir.")
        else:
            _open_in_inspect(study_dir, None)


def _render_scatter(
    frame: pd.DataFrame,
    *,
    active_cohort: str | None,
    cohort_lock: bool,
    break_comparability: bool,
    min_trades: float | None,
) -> None:
    st.markdown("### n × E scatter")
    st.caption("Color is `sample_class`. Vertical line is the displayed `min_trades` gate.")
    needed = {"trade_count", "expectancy_r"}
    if frame.empty or not needed.issubset(frame.columns):
        st.caption("No cells with trade_count × expectancy_r to chart.")
        return
    work = frame.dropna(subset=["trade_count", "expectancy_r"])
    if work.empty:
        st.caption("No cells with trade_count × expectancy_r to chart.")
        return
    highlight_all = (not cohort_lock) or break_comparability or not active_cohort
    if highlight_all:
        fig = px.scatter(
            work,
            x="trade_count",
            y="expectancy_r",
            color="sample_class" if "sample_class" in work.columns else None,
            hover_name="run_name" if "run_name" in work.columns else None,
            hover_data=["study_name"] if "study_name" in work.columns else None,
            title="trade_count × expectancy_r",
        )
    else:
        mask = work["cohort_key"].astype(str) == str(active_cohort)
        highlight = work.loc[mask]
        other = work.loc[~mask]
        fig = go.Figure()
        if not other.empty:
            other_fig = px.scatter(
                other,
                x="trade_count",
                y="expectancy_r",
                hover_name="run_name" if "run_name" in other.columns else None,
            )
            other_fig.update_traces(
                marker={"color": "#bbbbbb", "opacity": 0.35, "size": 8},
                name="other cohorts",
                showlegend=True,
            )
            for trace in other_fig.data:
                fig.add_trace(trace)
        if not highlight.empty:
            hi_fig = px.scatter(
                highlight,
                x="trade_count",
                y="expectancy_r",
                color="sample_class" if "sample_class" in highlight.columns else None,
                hover_name="run_name" if "run_name" in highlight.columns else None,
                hover_data=["study_name"] if "study_name" in highlight.columns else None,
            )
            for trace in hi_fig.data:
                fig.add_trace(trace)
        fig.update_layout(title="trade_count × expectancy_r (highlight = active cohort)")
        fig.update_xaxes(title="trade_count")
        fig.update_yaxes(title="expectancy_r")
    if min_trades is not None:
        fig.add_vline(
            x=float(min_trades),
            line_dash="dash",
            line_color="#666666",
            annotation_text=f"min_trades={int(min_trades) if float(min_trades).is_integer() else min_trades}",
        )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")


def _program_b_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "lens_hint" not in frame.columns:
        return frame
    return frame.loc[frame["lens_hint"].astype(str) == "program_b"]


def _sync_lens_facets(prog: pd.DataFrame) -> dict[str, list[Any]]:
    """Constrain lens widgets to pre-lens-facet Program B options (plan §6.11).

    Must run before the peek ``apply_facets`` so a stale ``plus_e`` / ``True``
    cannot empty the cohort strip on the same run that those options disappear.
    """
    lens_facets: dict[str, list[Any]] = {}
    for column, _label in _LENS_FACET_COLUMNS:
        widget_key = f"observatory_facet_{column}"
        raw = st.session_state.get(widget_key)
        options = unique_facet_values(prog, column)
        if isinstance(raw, (list, tuple)):
            constrained = constrain_facet_selection(raw, options)
            if list(raw) != constrained:
                st.session_state[widget_key] = constrained
            raw = constrained
        if isinstance(raw, (list, tuple)) and raw:
            lens_facets[column] = list(raw)
    return lens_facets


def _on_heatmap_cell() -> None:
    label = st.session_state.get(OBSERVATORY_HEATMAP_CELL_KEY) or ""
    if heatmap_focus_pending_facets is None or parse_heatmap_focus_label is None:
        return
    # "—" / unparseable must not wipe independently-set Core / Partner facets.
    # Spec clears focus by clearing those widgets, not the other way around.
    if parse_heatmap_focus_label(label) is None:
        return
    st.session_state[OBSERVATORY_PENDING_FACETS_KEY] = heatmap_focus_pending_facets(label)
    st.rerun()


def _render_heatmap_cell_picker(prog: pd.DataFrame) -> None:
    grid = program_b_heatmap_cells(prog) if program_b_heatmap_cells is not None else pd.DataFrame()
    labels: list[str] = []
    seen: set[str] = set()
    if isinstance(grid, pd.DataFrame) and not grid.empty:
        for record in grid.to_dict(orient="records"):
            label = heatmap_focus_label(
                record.get("factor_core_level"),
                record.get("factor_partner_levels"),
            )
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    options = [""] + labels
    current = st.session_state.get(OBSERVATORY_HEATMAP_CELL_KEY)
    cores = list(st.session_state.get("observatory_facet_factor_core_level") or [])
    partners = list(st.session_state.get("observatory_facet_factor_partner_levels") or [])
    inferred = ""
    # One core with an empty Partner widget is "no partner filter", not Wave 0.
    if len(cores) == 1 and len(partners) == 1 and heatmap_focus_label is not None:
        inferred = heatmap_focus_label(cores[0], partners[0])
    if current not in options:
        st.session_state[OBSERVATORY_HEATMAP_CELL_KEY] = inferred if inferred in options else ""
    elif current and heatmap_focus_pending_facets is not None:
        expected = heatmap_focus_pending_facets(current)
        if cores != expected.get("factor_core_level", []) or partners != expected.get(
            "factor_partner_levels", []
        ):
            st.session_state[OBSERVATORY_HEATMAP_CELL_KEY] = inferred if inferred in options else ""
    st.selectbox(
        "Heatmap cell",
        options=options,
        format_func=lambda item: item or "—",
        key=OBSERVATORY_HEATMAP_CELL_KEY,
        on_change=_on_heatmap_cell,
        help=_HEATMAP_FOCUS_CAPTION,
    )
    st.caption(_HEATMAP_FOCUS_CAPTION)


def _render_program_b_lens(frame: pd.DataFrame) -> None:
    st.markdown("### Program B lens")
    st.caption(_DELTA_E_CAPTION)
    prog = _program_b_rows(frame)
    counts = desk_class_counts(prog)
    count_cols = st.columns(len(DESK_CLASS_ORDER))
    for index, name in enumerate(DESK_CLASS_ORDER):
        count_cols[index].metric(name, int(counts.get(name, 0)))
    st.caption(PROGRAM_B_LENS_PACKET_CHROME)
    grid = program_b_heatmap_cells(prog)
    if grid.empty:
        st.caption("No Program B cells to heat-map.")
        return
    cores = list(dict.fromkeys(grid["factor_core_level"].tolist()))
    partners = list(dict.fromkeys(grid["factor_partner_levels"].tolist()))
    z: list[list[int]] = []
    hover: list[list[str]] = []
    format_ls = (
        format_heatmap_direction_count
        if callable(format_heatmap_direction_count)
        else (lambda value: "—" if value is None else str(value))
    )
    by_cell = {
        (
            record["factor_core_level"],
            record["factor_partner_levels"],
        ): record
        for record in grid.to_dict(orient="records")
    }
    for core in cores:
        z_row: list[int] = []
        hover_row: list[str] = []
        for partner in partners:
            rec = by_cell.get((core, partner)) or {}
            desk = rec.get("desk_class")
            z_value = heatmap_class_z(desk)
            z_row.append(z_value)
            if z_value == 0:
                hover_row.append(f"{core} × {partner}: missing / pending")
            else:
                long_n = format_ls(rec.get("long_trade_count"))
                short_n = format_ls(rec.get("short_trade_count"))
                hover_row.append(f"{core} × {partner}: {desk} · L {long_n} / S {short_n}")
        z.append(z_row)
        hover.append(hover_row)
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[str(item) if str(item).strip() else "(solo)" for item in partners],
            y=[str(item) for item in cores],
            text=hover,
            hoverinfo="text",
            colorscale=[
                [0.0, "#bbbbbb"],
                [0.06, "#bbbbbb"],
                [0.14, "#6b2d2d"],
                [0.28, "#9a9a9a"],
                [0.43, "#7a7a7a"],
                [0.57, "#4a4a4a"],
                [0.71, "#8b3a3a"],
                [0.86, "#c4a35a"],
                [1.0, "#2f6b4f"],
            ],
            zmin=0,
            zmax=int(HEATMAP_Z_MAX),
            showscale=False,
        )
    )
    fig.update_layout(
        title="desk_class heatmap (grey = missing / pending)",
        height=max(280, 28 * len(cores) + 80),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="factor_partner_levels",
        yaxis_title="factor_core_level",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Heatmap color is desk_class, not raw expectancy. Program A desk page is unchanged.")


st.title("Study Observatory")
st.caption(
    "Corpus readout of every local study cell under `results/studies/` and `out/`. "
    "Inspect stays the one-study microscope. This page does not run studies."
)
st.info(f"**Honesty.** {OBSERVATORY_HONESTY}")

if not _helpers_ready():
    st.caption(
        "Observatory helpers are missing from `thesistester.study.observatory`. "
        "Update that file from main and fully restart Streamlit. "
        "Paste a path on Studies to inspect one study."
    )
    st.stop()

_ensure_defaults()
refresh = st.button("Refresh")
model = _load_model(refresh=bool(refresh))
studies = (
    model.studies if isinstance(getattr(model, "studies", None), pd.DataFrame) else pd.DataFrame()
)
frame = model.frame if isinstance(getattr(model, "frame", None), pd.DataFrame) else pd.DataFrame()
if not frame.empty:
    frame = attach_program_b_projections(frame)

progress = corpus_progress_counts(studies)
cell_count = int(len(frame))
identity = st.columns(4)
identity[0].metric("Studies", progress["studies"])
identity[1].metric("Cells", cell_count)
identity[2].metric("Running", progress["running"])
identity[3].metric("Last stamp", _last_stamp_label(model))
ledger = st.columns(4)
ledger[0].metric("Ok", progress["ok"])
ledger[1].metric("Failed", progress["failed"])
ledger[2].metric("Pending", progress["pending"])
ledger[3].metric("Skipped", progress["skipped"])
st.caption(
    "Catalog membership is discovery, not a quality score. "
    "Ok / failed / pending / skipped / running are ledger sums across catalog "
    "dirs. Cells is the index grain — ledger-only dirs stay on this strip, "
    "not as invented cell rows. Refresh reloads index + expansion mtimes."
)
if callable(directional_integrity_counts):
    integrity = directional_integrity_counts(frame)
    st.caption(
        f"{integrity.get('long_only', 0)} cells long_only · "
        f"{integrity.get('short_only', 0)} short_only · "
        f"{integrity.get('mixed', 0)} mixed"
    )

if studies.empty and frame.empty:
    st.caption(_EMPTY_CATALOG)
    st.stop()

if not studies.empty:
    _render_studies_pane(studies)

st.markdown("### Facets")
facet_cols = st.columns(2)
facets: dict[str, list[Any]] = {}
for index, (column, label) in enumerate(_FACET_COLUMNS):
    with facet_cols[index % 2]:
        options = unique_facet_values(frame, column)
        widget_key = f"observatory_facet_{column}"
        current = st.session_state.get(widget_key)
        if isinstance(current, (list, tuple)):
            constrained = constrain_facet_selection(current, options)
            if list(current) != constrained:
                st.session_state[widget_key] = constrained
        selected = st.multiselect(label, options=options, key=widget_key)
        if selected:
            facets[column] = list(selected)
st.session_state[OBSERVATORY_FACET_STATE_KEY] = facets
generic_filtered = apply_facets(frame, facets)
peek_lens_mode = str(st.session_state.get(OBSERVATORY_ACTIVE_LENS_KEY) or "auto")
peek_lens_active = bool(resolve_program_b_lens(peek_lens_mode, generic_filtered))
lens_facets: dict[str, list[Any]] = {}
if peek_lens_active:
    lens_facets = _sync_lens_facets(_program_b_rows(generic_filtered))
filtered = apply_facets(
    generic_filtered,
    query_facets_for_frame({}, lens_active=peek_lens_active, lens_facets=lens_facets),
)
keys = unique_facet_values(filtered, "cohort_key") if not filtered.empty else []
differ_fields = cohort_differ_fields(keys)
if differ_fields:
    st.caption("Differing lock fields in this filtered set: " + ", ".join(differ_fields))
elif keys:
    st.caption("All filtered cells share one cohort key.")

st.markdown("### Cohort lock")
lock_cols = st.columns(2)
with lock_cols[0]:
    cohort_lock = st.checkbox(
        "Cohort lock",
        key=OBSERVATORY_COHORT_LOCK_KEY,
        help="Sort and scatter highlight stay inside one comparability cohort.",
    )
with lock_cols[1]:
    break_comparability = st.checkbox(
        "Break comparability",
        key=OBSERVATORY_BREAK_COMPARABILITY_KEY,
        help="Explicit global sort across cohort keys. Banner required.",
    )
spans_keys = (not bool(cohort_lock)) or bool(break_comparability)
if spans_keys:
    st.warning(
        "**Comparability lock is not in effect.** Sort and scatter highlight "
        "span cohort keys. Incomparable locks may share one rank. "
        "This is the only legal global PF/E sort."
    )
if COHORT_FIELDS:
    st.caption("Cohort lock fields: " + ", ".join(COHORT_FIELDS))

majority = majority_cohort_key(filtered) if not filtered.empty else None
if keys:
    default_pick = majority if majority in keys else keys[0]
    if st.session_state.get(OBSERVATORY_COHORT_PICK_KEY) not in keys:
        st.session_state[OBSERVATORY_COHORT_PICK_KEY] = default_pick
    label_by_key = dict(zip(keys, cohort_choice_labels(keys)))
    active_cohort = st.selectbox(
        "Active cohort",
        options=keys,
        key=OBSERVATORY_COHORT_PICK_KEY,
        format_func=lambda key: label_by_key.get(key, format_cohort_label(key)),
        help="Default is the majority key in the filtered set; ties break lexicographically.",
    )
    active_label = label_by_key.get(active_cohort, format_cohort_label(active_cohort))
    if majority is not None and str(active_cohort) == str(majority):
        st.caption(f"Active cohort is the majority key in the filtered set: `{active_label}`.")
    else:
        st.caption(f"Active cohort is operator-picked: `{active_label}`.")
else:
    active_cohort = None
    st.caption("No cohort keys in the filtered set.")

st.markdown("### Lens")
if st.session_state.get(OBSERVATORY_ACTIVE_LENS_KEY) not in _LENS_MODES:
    st.session_state[OBSERVATORY_ACTIVE_LENS_KEY] = "auto"
lens_mode = st.radio(
    "Lens",
    options=list(_LENS_MODES),
    key=OBSERVATORY_ACTIVE_LENS_KEY,
    horizontal=True,
    help="auto attaches Program B chrome when any filtered row is progB_*.",
)
lens_active = bool(resolve_program_b_lens(str(lens_mode), generic_filtered))
carried_lens_facets = any(
    bool(st.session_state.get(f"observatory_facet_{column}"))
    for column, _label in _LENS_FACET_COLUMNS
)
if not lens_active and carried_lens_facets:
    st.caption(_INERT_LENS_FACETS)
if lens_active:
    prog = _program_b_rows(generic_filtered)
    lens_cols = st.columns(2)
    for index, (column, label) in enumerate(_LENS_FACET_COLUMNS):
        with lens_cols[index % 2]:
            options = unique_facet_values(prog, column)
            widget_key = f"observatory_facet_{column}"
            current = st.session_state.get(widget_key)
            if isinstance(current, (list, tuple)):
                constrained = constrain_facet_selection(current, options)
                if list(current) != constrained:
                    st.session_state[widget_key] = constrained
            selected = st.multiselect(label, options=options, key=widget_key)
            if selected:
                lens_facets[column] = list(selected)
            else:
                lens_facets.pop(column, None)
    filtered = apply_facets(
        generic_filtered,
        query_facets_for_frame({}, lens_active=True, lens_facets=lens_facets),
    )
    _render_heatmap_cell_picker(prog)
    _render_program_b_lens(filtered)
elif str(lens_mode) == "generic":
    st.caption("Generic lens: Program B heatmap and desk_class chrome are hidden.")
else:
    st.caption("No `progB_*` rows in the filtered set — Program B lens stays off.")

sort_options = ["expectancy_r"] + sorted(name for name in SORT_ALLOW_LIST if name != "expectancy_r")
if st.session_state.get(OBSERVATORY_SORT_COLUMN_KEY) not in sort_options:
    st.session_state[OBSERVATORY_SORT_COLUMN_KEY] = "expectancy_r"
sort_column = st.selectbox("Sort", options=sort_options, key=OBSERVATORY_SORT_COLUMN_KEY)
save_facets = dict(facets)
for column, _label in _LENS_FACET_COLUMNS:
    raw = st.session_state.get(f"observatory_facet_{column}")
    if isinstance(raw, (list, tuple)) and raw:
        save_facets[column] = list(raw)
_render_saved_desks(
    facets=save_facets,
    cohort_lock=bool(cohort_lock),
    break_comparability=bool(break_comparability),
    active_cohort=str(active_cohort) if active_cohort is not None else None,
    lens_mode=str(lens_mode),
    sort_column=str(sort_column),
)
try:
    ranked = sort_observatory_frame(
        filtered,
        column=str(sort_column),
        cohort_lock=bool(cohort_lock),
        cohort_key=str(active_cohort) if active_cohort is not None else None,
        break_comparability=bool(break_comparability),
    )
except ObservatoryError as exc:
    st.error(str(exc))
    ranked = filtered.copy()

highlight_min = filtered
if bool(cohort_lock) and not bool(break_comparability) and active_cohort is not None:
    if not filtered.empty and "cohort_key" in filtered.columns:
        highlight_min = filtered.loc[filtered["cohort_key"].astype(str) == str(active_cohort)]
min_trades_line = displayed_min_trades(highlight_min)
_render_scatter(
    filtered,
    active_cohort=str(active_cohort) if active_cohort is not None else None,
    cohort_lock=bool(cohort_lock),
    break_comparability=bool(break_comparability),
    min_trades=min_trades_line,
)

st.markdown("### Cells")
if ranked.empty:
    st.caption("No cells match the current facets.")
else:
    shown = ranked.head(_TABLE_DISPLAY_CAP)
    if len(ranked) > _TABLE_DISPLAY_CAP:
        st.caption(f"Showing {_TABLE_DISPLAY_CAP} of {len(ranked)} cells (sorted).")
    if (
        bool(cohort_lock)
        and not bool(break_comparability)
        and active_cohort is not None
        and not shown.empty
        and "cohort_key" in shown.columns
    ):
        other_n = int((shown["cohort_key"].astype(str) != str(active_cohort)).sum())
        if other_n:
            st.caption(
                f"Sorted inside the active cohort. {other_n} other-cohort "
                "row(s) follow by study_name / run_name — not part of the ranked sort."
            )
    table_columns = list(_TABLE_COLUMNS)
    if lens_active:
        table_columns.extend(
            column for column in _LENS_TABLE_COLUMNS if column not in table_columns
        )
    display = shown.reindex(columns=[column for column in table_columns if column in shown.columns])
    st.dataframe(display, hide_index=True, width="stretch")
    records = shown.to_dict(orient="records")
    labels = cell_choice_labels(records)
    if labels:
        if st.session_state.get(OBSERVATORY_CELL_SELECT_KEY) not in labels:
            st.session_state[OBSERVATORY_CELL_SELECT_KEY] = labels[0]
        chosen = st.selectbox("Cell", options=labels, key=OBSERVATORY_CELL_SELECT_KEY)
        picked = records[labels.index(chosen)]
        st.session_state[OBSERVATORY_SELECTED_RUN_KEY] = (
            str(picked.get("study_dir") or ""),
            str(picked.get("run_name") or ""),
        )
        if st.button("Open in Inspect"):
            study_dir = str(picked.get("study_dir") or "").strip()
            run_name = picked.get("run_name")
            if not study_dir:
                st.error("Selected cell has no study_dir.")
            else:
                _open_in_inspect(study_dir, None if run_name is None else str(run_name))
