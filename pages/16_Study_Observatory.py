"""SO2 Study Observatory — corpus fact table, facets, cohort lock, Inspect drill.

Read-only corpus page. Does not execute studies, write report artifacts,
or hydrate classic research session keys. Program B heatmap / desks are SO3/SO4.
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
)
_TABLE_COLUMNS: tuple[str, ...] = (
    "study_name",
    "run_name",
    "instrument",
    "setup_kind",
    "trade_count",
    "expectancy_r",
    "profit_factor",
    "win_rate",
    "status",
    "sample_class",
    "cohort_key",
    "study_dir",
)

load_observatory_frame = getattr(_observatory, "load_observatory_frame", None)
apply_facets = getattr(_observatory, "apply_facets", None)
sort_observatory_frame = getattr(_observatory, "sort_observatory_frame", None)
majority_cohort_key = getattr(_observatory, "majority_cohort_key", None)
unique_facet_values = getattr(_observatory, "unique_facet_values", None)
displayed_min_trades = getattr(_observatory, "displayed_min_trades", None)
constrain_facet_selection = getattr(_observatory, "constrain_facet_selection", None)
cell_choice_labels = getattr(_observatory, "cell_choice_labels", None)
SORT_ALLOW_LIST = getattr(_observatory, "SORT_ALLOW_LIST", frozenset({"expectancy_r"}))
COHORT_FIELDS = getattr(_observatory, "COHORT_FIELDS", ())
OBSERVATORY_HONESTY = getattr(_observatory, "OBSERVATORY_HONESTY", _HONESTY_FALLBACK)
ObservatoryModel = getattr(_observatory, "ObservatoryModel", None)
ObservatoryError = getattr(_observatory, "ObservatoryError", ValueError)


def _helpers_ready() -> bool:
    return all(
        callable(fn)
        for fn in (
            load_observatory_frame,
            apply_facets,
            sort_observatory_frame,
            majority_cohort_key,
            unique_facet_values,
            displayed_min_trades,
            constrain_facet_selection,
            cell_choice_labels,
        )
    )


def _ensure_defaults() -> None:
    if OBSERVATORY_COHORT_LOCK_KEY not in st.session_state:
        st.session_state[OBSERVATORY_COHORT_LOCK_KEY] = True
    if OBSERVATORY_BREAK_COMPARABILITY_KEY not in st.session_state:
        st.session_state[OBSERVATORY_BREAK_COMPARABILITY_KEY] = False
    if OBSERVATORY_SORT_COLUMN_KEY not in st.session_state:
        st.session_state[OBSERVATORY_SORT_COLUMN_KEY] = "expectancy_r"


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
    run_text = "" if run_name is None else str(run_name).strip()
    if run_text and run_text not in {"<NA>", "nan", "None"}:
        st.session_state[STUDIES_VIEWER_SELECTED_RUN_KEY] = run_text
    st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_KEY, None)
    st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY, None)
    st.switch_page("pages/15_Studies.py")


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

study_count = int(len(studies))
cell_count = int(len(frame))
running = (
    int(studies["running"].fillna(0).sum())
    if not studies.empty and "running" in studies.columns
    else 0
)
strip = st.columns(4)
strip[0].metric("Studies", study_count)
strip[1].metric("Cells", cell_count)
strip[2].metric("Running", running)
strip[3].metric("Last stamp", _last_stamp_label(model))
st.caption(
    "Catalog membership is discovery, not a quality score. Refresh reloads index + expansion mtimes."
)

if studies.empty and frame.empty:
    st.caption(_EMPTY_CATALOG)
    st.stop()

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
filtered = apply_facets(frame, facets)

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

keys = unique_facet_values(filtered, "cohort_key") if not filtered.empty else []
majority = majority_cohort_key(filtered) if not filtered.empty else None
if keys:
    default_pick = majority if majority in keys else keys[0]
    if st.session_state.get(OBSERVATORY_COHORT_PICK_KEY) not in keys:
        st.session_state[OBSERVATORY_COHORT_PICK_KEY] = default_pick
    active_cohort = st.selectbox(
        "Active cohort",
        options=keys,
        key=OBSERVATORY_COHORT_PICK_KEY,
        help="Default is the majority key in the filtered set; ties break lexicographically.",
    )
    if majority is not None and str(active_cohort) == str(majority):
        st.caption(f"Active cohort is the majority key in the filtered set: `{active_cohort}`.")
    else:
        st.caption(f"Active cohort is operator-picked: `{active_cohort}`.")
else:
    active_cohort = None
    st.caption("No cohort keys in the filtered set.")

sort_options = ["expectancy_r"] + sorted(name for name in SORT_ALLOW_LIST if name != "expectancy_r")
if st.session_state.get(OBSERVATORY_SORT_COLUMN_KEY) not in sort_options:
    st.session_state[OBSERVATORY_SORT_COLUMN_KEY] = "expectancy_r"
sort_column = st.selectbox("Sort", options=sort_options, key=OBSERVATORY_SORT_COLUMN_KEY)
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
    display = shown.reindex(
        columns=[column for column in _TABLE_COLUMNS if column in shown.columns]
    )
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
