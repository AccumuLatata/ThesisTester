"""RS-D2/RS-D8/RS-D9 + SB2/SB3 — Studies inspect, preview, CLI-spawn, and Build tab."""

from __future__ import annotations

import copy
from typing import Any

import streamlit as st

from thesistester.config import INSTRUMENTS, TIMEZONE_OPTIONS
from thesistester.data import loader as _data_loader
from thesistester.data.derive import INGESTION_MODE_15S_PRIMARY_DERIVE_1M
from thesistester.engine.intrabar import VALID_INTRABAR_MODELS
from thesistester.execution_defaults import EXPOSURE_POLICY_OPTIONS
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.levels.indicators import SUPPORTED_INDICATOR_TIMEFRAMES
from thesistester.setup import TRIGGER_TIMEFRAME_CHOICES, VALID_TRIGGERS
from thesistester.study.builder import (
    DIRECTION_MODE_CONSTANT,
    DIRECTION_MODE_FACTOR,
    DIRECTION_MODE_OPTIONS,
    INGESTION_MODE_PRIMARY,
    MULTIPLE_TESTING_OPTIONS,
    OTF_PRESET_LABELS,
    OTF_PRESET_ORDER,
    PRIMARY_METRIC_OPTIONS,
    STAGE_MODE_EXPLICIT,
    STAGE_MODE_FILTER,
    STAGE_MODE_OPTIONS,
    STUDIES_BUILDER_DRAFT_KEY,
    STUDIES_BUILDER_PENDING_SYNC_KEY,
    StudyDraft,
    TF_MODE_EXPLICIT,
    TF_MODE_OPTIONS,
    WIDGET_KEY_BATTERY_GRID,
    WIDGET_KEY_BATTERY_VALIDATION,
    WIDGET_KEY_BATTERY_WALK_FORWARD,
    WIDGET_KEY_COMMISSION,
    WIDGET_KEY_CONFIRM_ABOVE_RUNS,
    WIDGET_KEY_CONFLUENCE_ANCHOR,
    WIDGET_KEY_CONFLUENCE_GLOBAL,
    WIDGET_KEY_CORE_LEVEL,
    WIDGET_KEY_DATASET_PATH,
    WIDGET_KEY_DESCRIPTION,
    WIDGET_KEY_DIRECTION_CONSTANT,
    WIDGET_KEY_DIRECTION_MODE,
    WIDGET_KEY_DIRECTION_VALUES,
    WIDGET_KEY_EMA_ADD_LENGTH,
    WIDGET_KEY_EMA_LENGTHS,
    WIDGET_KEY_EMA_TF_MODE,
    WIDGET_KEY_EMA_TIMEFRAMES,
    WIDGET_KEY_EXPOSURE_POLICY,
    WIDGET_KEY_FLAT_BY_SESSION_CLOSE,
    WIDGET_KEY_FORMAT_PROFILE,
    WIDGET_KEY_EXPLICIT_DELETE,
    WIDGET_KEY_FROM_PARTNERS,
    WIDGET_KEY_GRID_SL_VALUES,
    WIDGET_KEY_GRID_TP_VALUES,
    WIDGET_KEY_GROUP_BY,
    WIDGET_KEY_INGESTION_MODE,
    WIDGET_KEY_INSTRUMENT,
    WIDGET_KEY_INTRABAR_MODEL,
    WIDGET_KEY_LEVELS_ADVANCED,
    WIDGET_KEY_MAX_CONFLUENCES,
    WIDGET_KEY_MIN_CONFLUENCES,
    WIDGET_KEY_MIN_TRADES,
    WIDGET_KEY_MIN_VALID_CONFLUENCES,
    WIDGET_KEY_MULTIPLE_TESTING,
    WIDGET_KEY_NAKED_ONLY,
    WIDGET_KEY_NAKED_REQUIREMENT,
    WIDGET_KEY_NAME,
    WIDGET_KEY_OTF,
    WIDGET_KEY_OTF_BASELINE,
    WIDGET_KEY_OUTPUT_DIR,
    WIDGET_KEY_PRIMARY_METRIC,
    WIDGET_KEY_PIVOTS_ENABLED,
    WIDGET_KEY_PIVOT_TIMEFRAMES,
    WIDGET_KEY_POC_WINDOWS,
    WIDGET_KEY_PREV30M_ENABLED,
    WIDGET_KEY_SLIPPAGE,
    WIDGET_KEY_SMA_ADD_LENGTH,
    WIDGET_KEY_SMA_LENGTHS,
    WIDGET_KEY_SMA_TF_MODE,
    WIDGET_KEY_SMA_TIMEFRAMES,
    WIDGET_KEY_SOURCE_TIMEZONE,
    WIDGET_KEY_STAGE_MODE,
    WIDGET_KEY_STOP_LOSS,
    WIDGET_KEY_TAKE_PROFIT,
    WIDGET_KEY_TOLERANCE_TICKS,
    WIDGET_KEY_TRIGGER,
    WIDGET_KEY_TRIGGER_TIMEFRAME,
    WIDGET_KEY_VWAP_WINDOWS,
    WIDGET_KEY_WORKERS,
    _partner_set_widget_key,
    _stage_include_widget_key,
    apply_grid_tick_widgets,
    apply_levels_tf_mode,
    builder_token_catalog,
    coerce_partner_levels,
    coerce_whole_number,
    clamp_widget_selection,
    collect_stage_include,
    constrain_group_by,
    declared_factor_domains,
    default_study_draft,
    delete_stage_cells,
    draft_from_mapping,
    draft_to_mapping,
    draft_warnings,
    emit_study_spec,
    emit_study_yaml,
    explicit_cell_row_label,
    format_csv_values,
    format_stage_value,
    hydrate_study_yaml,
    infer_stage_mode_label,
    infer_tf_mode,
    levels_advanced_enabled,
    ma_length_options,
    otf_for_selected_presets,
    otf_preset_ids,
    parse_csv_tokens,
    preferred_group_by,
    stage_mode_from_label,
)
from thesistester.study.launch import (
    LAUNCH_LOG_NAME,
    STUDIES_LAUNCH_APPROVAL_KEY,
    STUDIES_LAUNCH_OUTPUT_DIR_KEY,
    LaunchPlan,
    StudyLaunchError,
    approval_matches,
    approval_payload,
    build_launch_plan,
    default_output_dir_from_yaml,
    format_argv,
    plan_with_confirm,
    planned_argv,
    read_launch_pid_status,
    reset_launch_session_for_preview,
    spawn_launch,
)
from thesistester.study.preview import (
    STUDIES_PREVIEW_CACHED_KEY,
    STUDIES_PREVIEW_CACHED_YAML_KEY,
    STUDIES_PREVIEW_YAML_KEY,
    StudyPreview,
    example_study_spec_path,
    preview_study_spec,
    preview_study_yaml,
)
from thesistester.study.schema import StudySpecError
from thesistester.study.viewer import (
    STUDIES_VIEWER_CACHED_MODEL_DIR_KEY,
    STUDIES_VIEWER_CACHED_MODEL_KEY,
    STUDIES_VIEWER_DIR_KEY,
    StudyViewerError,
    default_study_viewer_roots,
    load_study_view,
    resolve_study_dir,
)

# Do not import FORMAT_PROFILE_LABELS or normalize_builder_format_profile from
# builder. A stale builder.py raises ImportError and bricks the Studies page.
# Prefer the live loader catalog (same object as Data). Fall back only when
# that name is missing or not a non-empty dict. Page-local normalize matches
# current builder semantics (blank → canonical; do not rewrite unknown tokens).
# Do not getattr-normalize from builder: an older builder still clamps unknown
# tokens to canonical.
_FORMAT_PROFILE_LABELS_FALLBACK = {
    "canonical": "Canonical / Quantower OHLCV",
    "quantower_history_exporter": "Quantower History Exporter (semicolon)",
    "ninjatrader": "NinjaTrader export",
    "sierra_intraday": "Sierra Intraday CSV",
    "databento_trades": "Databento trades CSV",
    "tick_capture": "Generic tick capture CSV",
    "second_capture": "Generic second capture CSV",
}


def _bind_format_profile_labels(loader_module: Any) -> dict[str, str]:
    labels = getattr(loader_module, "FORMAT_PROFILE_LABELS", None)
    if isinstance(labels, dict) and labels:
        return labels
    return dict(_FORMAT_PROFILE_LABELS_FALLBACK)


FORMAT_PROFILE_LABELS = _bind_format_profile_labels(_data_loader)


def normalize_builder_format_profile(value: Any) -> str:
    if value is None:
        return "canonical"
    if isinstance(value, str):
        token = value.strip()
        return token or "canonical"
    return "canonical"


# Page-local ingest labels. Do not import the Data page (classic ingest UI).
# Toggle must not rewrite format_profile or intrabar_model.
_INGESTION_MODE_LABELS = {
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M: (
        "Recommended: 15-second primary — derive one-minute canonical"
    ),
    INGESTION_MODE_PRIMARY: "Legacy: one-minute primary (advanced)",
}
_INGESTION_MODE_OPTIONS = (
    INGESTION_MODE_15S_PRIMARY_DERIVE_1M,
    INGESTION_MODE_PRIMARY,
)


def _resolved_builder_ingestion_mode(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return INGESTION_MODE_PRIMARY


st.title("Studies")
st.caption(
    "Inspect a completed study output directory, preview a canonical StudySpec "
    "YAML (cell count / confirm gate), or build one without typing YAML. "
    "Run via CLI (Preview tab) spawns the existing "
    "`python -m thesistester study run` process. Promote stays on the CLI "
    "(or optional STUDY.* assistant tools)."
)

st.info(
    "**Honesty.** Overview ranking is descriptive screening, not a validated edge. "
    "Interpret with multiple-testing caution and `min_trades` sample-size gates. "
    "`bundle_path` lists per-cell zips — Research Bundles is upload/import oriented "
    "and is not a deep-link target from this page. Preview `run_count` is a "
    "combinatorial screening size, not independent statistical tests."
)

inspect_tab, preview_tab, build_tab = st.tabs(
    ["Inspect output dir", "Preview StudySpec", "Build StudySpec"]
)


def _render_inspect() -> None:
    # Prefill the path widget from the last successfully loaded Studies dir.
    if "studies_viewer_path_input" not in st.session_state and isinstance(
        st.session_state.get(STUDIES_VIEWER_DIR_KEY), str
    ):
        st.session_state["studies_viewer_path_input"] = st.session_state[STUDIES_VIEWER_DIR_KEY]

    raw_dir = st.text_input(
        "Study output directory",
        key="studies_viewer_path_input",
        help=(
            "Absolute or repo-relative path to a study dir (must contain "
            "study.spec.yaml; results_index.csv after the first cell finishes). "
            "A readable study.ledger.json is enough for Inspect progress while "
            "the first cell is still running. Paths must stay under the repo "
            "working directory or the local ThesisTester store."
        ),
        placeholder="out/pdPOC_stage40",
    )

    load_col, refresh_col = st.columns(2)
    load = load_col.button("Load study artifacts", type="primary")
    refresh = refresh_col.button("Refresh")

    path_stripped = str(raw_dir).strip()
    if load:
        if not path_stripped:
            st.error("Enter a study output directory path.")
            return
        # Persist only the Studies-scoped path key so reruns (download / expander)
        # keep the view; never touch classic research session_state keys.
        st.session_state[STUDIES_VIEWER_DIR_KEY] = path_stripped
    elif refresh and path_stripped:
        # Refresh must honor the current path widget. Operators often edit the
        # text field and hit Refresh without Load; ignoring the widget would
        # re-aggregate a stale STUDIES_VIEWER_DIR_KEY while the UI shows another path.
        st.session_state[STUDIES_VIEWER_DIR_KEY] = path_stripped

    active_dir = st.session_state.get(STUDIES_VIEWER_DIR_KEY)
    if refresh and (not isinstance(active_dir, str) or not active_dir.strip()):
        st.error("Load a study output directory before refreshing.")
        return
    if not isinstance(active_dir, str) or not active_dir.strip():
        st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_KEY, None)
        st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY, None)
        st.caption("Enter a study output directory, then load artifacts.")
        return

    # Streamlit executes every tab body on each script rerun. Cache the viewer
    # model so Preview-tab Validate/Preview (and download/expander clicks) do
    # not re-aggregate a large study_dir. Reload only on Load / Refresh, or
    # when the cached path no longer matches the selected directory.
    need_reload = bool(load or refresh) or (
        st.session_state.get(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY) != active_dir
        or st.session_state.get(STUDIES_VIEWER_CACHED_MODEL_KEY) is None
    )
    if need_reload:
        try:
            model = load_study_view(active_dir, roots=default_study_viewer_roots())
        except StudyViewerError as exc:
            st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_KEY, None)
            st.session_state.pop(STUDIES_VIEWER_CACHED_MODEL_DIR_KEY, None)
            st.error(str(exc))
            return
        st.session_state[STUDIES_VIEWER_CACHED_MODEL_KEY] = model
        st.session_state[STUDIES_VIEWER_CACHED_MODEL_DIR_KEY] = active_dir
    else:
        model = st.session_state[STUDIES_VIEWER_CACHED_MODEL_KEY]

    st.subheader(model.study_name)
    meta_cols = st.columns(4)
    meta_cols[0].metric("Run count", model.run_count if model.run_count is not None else "—")
    meta_cols[1].metric("Ranked", len(model.ranked_display))
    meta_cols[2].metric("Low-N", len(model.low_n_display))
    meta_cols[3].metric("Unresolved", len(model.unresolved_display))

    st.caption(f"Directory: `{model.study_dir}`")
    if model.study_identity_hash:
        st.caption(f"Study identity hash: `{model.study_identity_hash}`")
    st.caption(
        f"Primary metric: `{model.report.primary_metric}` · "
        f"min_trades={model.report.min_trades} · "
        f"multiple_testing={model.report.multiple_testing}"
        + (" · best-cell crowning suppressed" if model.report.best_cell_suppressed else "")
    )

    st.markdown("### Ledger status")
    progress = model.ledger_progress
    if progress.total > 0:
        st.progress(progress.fraction)
        parts = [f"{progress.done}/{progress.total} cells complete"]
        if progress.running_ids:
            shown = ", ".join(f"`{name}`" for name in progress.running_ids[:3])
            extra = (
                f" (+{len(progress.running_ids) - 3} more)" if len(progress.running_ids) > 3 else ""
            )
            parts.append(f"running: {shown}{extra}")
        elif progress.running_count:
            parts.append(f"{progress.running_count} running")
        if progress.pending:
            parts.append(f"{progress.pending} pending")
        st.caption(" · ".join(parts) + ". Cell-status counts, not a quality metric.")
    if not model.report_present:
        st.caption(
            "Ledger-only view: `results_index.csv` is absent. "
            "Ranked tables stay empty until Refresh after the index appears."
        )
    if model.ledger_summary:
        source = "ledger" if model.ledger_present else "results_index status"
        st.caption(f"Counts from {source}. Click Refresh while a CLI `study run` is in flight.")
        st.dataframe(
            {
                "status": list(model.ledger_summary.keys()),
                "count": list(model.ledger_summary.values()),
            },
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No ledger or status column available.")

    st.markdown("### Ranked cells")
    if model.ranked_display.empty:
        if not model.report_present:
            st.info("Ranked tables stay empty until Refresh after `results_index.csv` appears.")
        else:
            st.info("No ranked cells (check min_trades / ok status / primary metric).")
    else:
        st.dataframe(model.ranked_display, hide_index=True, width="stretch")

    st.markdown("### Low-N cells")
    if model.low_n_display.empty:
        st.caption("None.")
    else:
        st.dataframe(model.low_n_display, hide_index=True, width="stretch")

    st.markdown("### Unresolved primary metric")
    if model.unresolved_display.empty:
        st.caption("None.")
    else:
        st.dataframe(model.unresolved_display, hide_index=True, width="stretch")

    st.markdown("### OTF Δ")
    if model.otf_delta_display.empty:
        st.caption("No OTF Δ rows (baseline disabled or no matching pairs).")
    else:
        st.dataframe(model.otf_delta_display, hide_index=True, width="stretch")

    st.markdown("### Overview markdown")
    st.download_button(
        "Download study.overview.md",
        data=model.overview_md if model.overview_md.endswith("\n") else model.overview_md + "\n",
        file_name="study.overview.md",
        mime="text/markdown",
    )
    if model.overview_csv_text:
        st.download_button(
            "Download study.overview.csv",
            data=model.overview_csv_text,
            file_name="study.overview.csv",
            mime="text/csv",
        )
    with st.expander("Show study.overview.md", expanded=False):
        st.markdown(model.overview_md)


def _read_loaded_study_spec_text() -> str | None:
    """Read Inspect ``study.spec.yaml`` (sandboxed). None after a visible error."""
    active_dir = st.session_state.get(STUDIES_VIEWER_DIR_KEY)
    if not isinstance(active_dir, str) or not active_dir.strip():
        st.error("Load a study output directory on the Inspect tab first.")
        return None
    try:
        root = resolve_study_dir(active_dir, roots=default_study_viewer_roots())
    except StudyViewerError as exc:
        st.error(str(exc))
        return None
    spec_path = root / "study.spec.yaml"
    if not spec_path.is_file():
        st.error(f"No study.spec.yaml under {root}")
        return None
    return spec_path.read_text(encoding="utf-8")


def _copy_spec_from_loaded_dir() -> bool:
    text = _read_loaded_study_spec_text()
    if text is None:
        return False
    st.session_state[STUDIES_PREVIEW_YAML_KEY] = text
    _clear_launch_session()
    return True


def _clear_launch_session() -> None:
    st.session_state.pop(STUDIES_LAUNCH_APPROVAL_KEY, None)
    st.session_state.pop(STUDIES_LAUNCH_OUTPUT_DIR_KEY, None)


def _spawn_or_error(plan: LaunchPlan) -> None:
    try:
        result = spawn_launch(plan)
    except StudyLaunchError as exc:
        st.error(str(exc))
        return
    st.success(
        f"Started CLI pid `{result.pid}`. Watch **Inspect → Refresh** / ledger. "
        f"Log: `{result.log_path}`."
    )


def _render_launch_controls(preview: StudyPreview, yaml_text: str) -> None:
    st.markdown("### Run via CLI")
    st.caption(
        "Starts the same `python -m thesistester study run` process as the terminal. "
        "Cells do not execute inside this page."
    )
    if STUDIES_LAUNCH_OUTPUT_DIR_KEY not in st.session_state:
        st.session_state[STUDIES_LAUNCH_OUTPUT_DIR_KEY] = default_output_dir_from_yaml(yaml_text)

    output_raw = st.text_input(
        "CLI output directory",
        key=STUDIES_LAUNCH_OUTPUT_DIR_KEY,
        help=(
            "Must stay under the repo working directory or the local ThesisTester store. "
            "Does not default to the Inspect directory. Dataset paths are pinned absolute "
            "in study.launch.yaml — prefer a new output_dir for UI launches."
        ),
        placeholder="results/studies/my_study",
    )
    override = st.checkbox("Override workers", value=False, key="studies_launch_override_workers")
    workers = None
    if override:
        workers = int(
            st.number_input(
                "Workers",
                min_value=1,
                value=max(int(preview.workers), 1),
                step=1,
                key="studies_launch_workers",
            )
        )
    force = st.checkbox(
        "Pass --force (re-run all cells / ignore identity mismatch)",
        value=False,
        key="studies_launch_force",
    )
    st.info(
        "**Honesty.** Combinatorial `run_count` is a screening size, not independent "
        "statistical tests. Large factorials need the two-step confirm. Launching the "
        "CLI does not validate an edge. The child is the same `study run` as the terminal."
    )
    if not preview.expanded:
        st.warning(
            "Over preview cap — launch from this page is refused. Shrink the study "
            "or use the CLI after `study expand`."
        )
        return

    cached_yaml = st.session_state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
    try:
        plan = build_launch_plan(
            yaml_text,
            cached_yaml=cached_yaml if isinstance(cached_yaml, str) else None,
            expanded=preview.expanded,
            run_count=preview.run_count,
            output_dir_raw=str(output_raw or ""),
            force=bool(force),
            workers=workers,
        )
    except StudyLaunchError as exc:
        st.caption(str(exc))
        plan = None

    stored = st.session_state.get(STUDIES_LAUNCH_APPROVAL_KEY)
    if plan is not None and stored is not None and not approval_matches(stored, plan):
        st.session_state.pop(STUDIES_LAUNCH_APPROVAL_KEY, None)
        stored = None

    if plan is not None:
        st.caption(
            f"Pinned identity `{plan.study_identity_hash}` "
            "(confirm binds this hash, not the unpinned preview hash)."
        )
        st.code(format_argv(planned_argv(plan)), language="text")
        status = read_launch_pid_status(plan.output_dir)
        if status is not None:
            state = "alive" if status.alive else "not alive"
            st.caption(f"Last launch pid `{status.pid}` ({state}).")
        st.caption(
            f"Child stdout/stderr → `{LAUNCH_LOG_NAME}` in the CLI output dir "
            "(Inspect **Refresh** / ledger for cell progress; Streamlit "
            "`Ignoring changed path` under results/ is the watcher, not this log)."
        )

    if plan is not None and not plan.needs_confirm:
        if st.button("Run via CLI", type="primary"):
            _spawn_or_error(plan)
        return

    bind_col, run_col = st.columns(2)
    do_bind = bind_col.button("Bind confirm")
    do_confirm_run = run_col.button("Confirm and run", type="primary")
    if stored is not None:
        st.caption("Confirm is bound for this hash / run_count / output_dir.")
    if do_bind:
        if plan is None:
            st.error("Fix output directory / preview before binding confirm.")
            return
        st.session_state[STUDIES_LAUNCH_APPROVAL_KEY] = approval_payload(plan)
        st.success(
            "Confirm bound to "
            f"hash=`{plan.study_identity_hash}` · run_count={plan.run_count} · "
            f"output_dir=`{plan.output_dir}`."
        )
        return
    if do_confirm_run:
        if plan is None:
            st.error("Fix output directory / preview before Confirm and run.")
            return
        try:
            confirmed = plan_with_confirm(plan, st.session_state.get(STUDIES_LAUNCH_APPROVAL_KEY))
        except StudyLaunchError as exc:
            st.error(str(exc))
            return
        _spawn_or_error(confirmed)


def _render_preview_result(preview: StudyPreview, yaml_text: str) -> None:
    st.success(f"Preview `{preview.study_name}`")
    cols = st.columns(4)
    shown_count = preview.run_count if preview.expanded else preview.effective_run_count_estimate
    cols[0].metric("Cells (effective)", shown_count)
    cols[1].metric("Full cartesian", preview.cartesian_product)
    cols[2].metric("Workers", preview.workers)
    cols[3].metric("Needs --confirm", "yes" if preview.needs_confirm else "no")
    st.caption(
        f"confirm_above_runs={preview.confirm_above_runs} · "
        f"expanded={preview.expanded} · "
        f"identity `{preview.study_identity_hash}`"
    )
    if preview.cap_warning:
        st.warning(preview.cap_warning)
    st.write("Axis sizes:", preview.axis_sizes)
    if preview.effective_run_count_estimate != preview.cartesian_product:
        st.caption(
            f"Staged/matched estimate {preview.effective_run_count_estimate} vs "
            f"unstaged cartesian {preview.cartesian_product}."
        )
    st.write("Battery flags:", preview.battery_enabled)
    for line in preview.hint_lines:
        if line.startswith("WARNING"):
            st.warning(line)
        else:
            st.caption(line)
    st.info(
        "**Honesty.** Combinatorial `run_count` is a screening size, not independent "
        "statistical tests. Large factorials need `--confirm` (two-step Bind confirm "
        "then Confirm and run). Descriptive ranking after a run is not a validated edge. "
        "The child process is `python -m thesistester study run …`."
    )
    _render_launch_controls(preview, yaml_text)


def _render_preview() -> None:
    st.text_area(
        "Canonical StudySpec YAML (`schema_version: 1`)",
        key=STUDIES_PREVIEW_YAML_KEY,
        height=360,
        help=(
            "Paste a real StudySpec. Shorthand keys (core vs core_level) and "
            "English prompts fail closed. Dataset CSV need not exist for preview."
        ),
    )
    action_cols = st.columns(3)
    do_preview = action_cols[0].button("Validate / Preview", type="primary")
    load_example = action_cols[1].button("Load example")
    copy_loaded = action_cols[2].button("Copy spec from loaded dir")

    if load_example:
        try:
            path = example_study_spec_path()
        except StudySpecError as exc:
            st.error(str(exc))
            return
        st.session_state[STUDIES_PREVIEW_YAML_KEY] = path.read_text(encoding="utf-8")
        st.session_state.pop(STUDIES_PREVIEW_CACHED_KEY, None)
        st.session_state.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
        _clear_launch_session()
        st.rerun()

    if copy_loaded:
        if _copy_spec_from_loaded_dir():
            st.session_state.pop(STUDIES_PREVIEW_CACHED_KEY, None)
            st.session_state.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
            _clear_launch_session()
            st.rerun()
        return

    raw = str(st.session_state.get(STUDIES_PREVIEW_YAML_KEY, ""))
    if do_preview:
        try:
            with st.spinner("Expanding StudySpec…"):
                preview = preview_study_yaml(raw)
        except (StudySpecError, ValueError) as exc:
            st.session_state.pop(STUDIES_PREVIEW_CACHED_KEY, None)
            st.session_state.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
            _clear_launch_session()
            st.error(str(exc))
            return
        prev_cached_yaml = st.session_state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
        st.session_state[STUDIES_PREVIEW_CACHED_KEY] = preview
        st.session_state[STUDIES_PREVIEW_CACHED_YAML_KEY] = raw
        # Drop armed confirm always; reseed CLI output_dir when the YAML changed
        # so a new StudySpec cannot inherit the previous study's launch directory.
        reset_launch_session_for_preview(
            st.session_state,
            prev_cached_yaml=prev_cached_yaml if isinstance(prev_cached_yaml, str) else None,
            new_yaml=raw,
        )
        _render_preview_result(preview, raw)
        return

    # Button clicks are ephemeral; keep the last successful preview while the
    # YAML textarea is unchanged (Inspect downloads / tab switches rerun the app).
    cached = st.session_state.get(STUDIES_PREVIEW_CACHED_KEY)
    cached_yaml = st.session_state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
    if isinstance(cached, StudyPreview) and isinstance(cached_yaml, str) and cached_yaml == raw:
        _render_preview_result(cached, raw)
        return

    st.caption(
        "Paste YAML, then Validate / Preview. Run via CLI appears after a successful preview."
    )


_TRIGGER_OPTIONS = ("touch", "reject", "break", "reclaim", "3c")
_DIRECTION_VALUES = ("long", "short", "both")
_NAKED_REQUIREMENTS = ("any", "all")
_FROM_PARTNERS_OPTIONS = ("required", "optional")
_BUILDER_HONESTY = (
    "**Honesty.** Combinatorial `run_count` is a screening size, not independent "
    "statistical tests. Large factorials need `--confirm` (two-step Bind confirm "
    "then Confirm and run on the Preview tab). Descriptive ranking after a run "
    "is not a validated edge. The child process is "
    "`python -m thesistester study run …`."
)


def _ensure_builder_draft() -> StudyDraft:
    if STUDIES_BUILDER_DRAFT_KEY not in st.session_state:
        st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(default_study_draft())
        st.session_state[STUDIES_BUILDER_PENDING_SYNC_KEY] = True
    draft = draft_from_mapping(st.session_state.get(STUDIES_BUILDER_DRAFT_KEY))
    if st.session_state.pop(STUDIES_BUILDER_PENDING_SYNC_KEY, False):
        _sync_builder_widgets(draft)
    return draft


def _sync_builder_widgets(draft: StudyDraft) -> None:
    """Overwrite widget keys before widgets instantiate (hydrate / start-from-example)."""
    st.session_state[WIDGET_KEY_NAME] = draft.name
    st.session_state[WIDGET_KEY_DESCRIPTION] = (
        "" if draft.description is None else draft.description
    )
    st.session_state[WIDGET_KEY_WORKERS] = int(draft.workers)
    st.session_state[WIDGET_KEY_CONFIRM_ABOVE_RUNS] = int(draft.confirm_above_runs)
    st.session_state[WIDGET_KEY_OUTPUT_DIR] = draft.output_dir or ""
    st.session_state[WIDGET_KEY_DATASET_PATH] = draft.dataset_path
    st.session_state[WIDGET_KEY_INSTRUMENT] = draft.instrument
    st.session_state[WIDGET_KEY_SOURCE_TIMEZONE] = draft.source_timezone or ""
    st.session_state[WIDGET_KEY_FORMAT_PROFILE] = normalize_builder_format_profile(
        draft.format_profile
    )
    st.session_state[WIDGET_KEY_INGESTION_MODE] = _resolved_builder_ingestion_mode(
        draft.ingestion_mode
    )
    sma_lengths = [int(item) for item in (draft.levels.get("sma_lengths") or [])]
    ema_lengths = [int(item) for item in (draft.levels.get("ema_lengths") or [])]
    st.session_state[WIDGET_KEY_SMA_LENGTHS] = sma_lengths
    st.session_state[WIDGET_KEY_EMA_LENGTHS] = ema_lengths
    st.session_state[WIDGET_KEY_SMA_TF_MODE] = infer_tf_mode(draft.levels, "sma_timeframes")
    st.session_state[WIDGET_KEY_EMA_TF_MODE] = infer_tf_mode(draft.levels, "ema_timeframes")
    sma_tfs = draft.levels.get("sma_timeframes")
    ema_tfs = draft.levels.get("ema_timeframes")
    st.session_state[WIDGET_KEY_SMA_TIMEFRAMES] = (
        [str(item) for item in sma_tfs] if isinstance(sma_tfs, list) else []
    )
    st.session_state[WIDGET_KEY_EMA_TIMEFRAMES] = (
        [str(item) for item in ema_tfs] if isinstance(ema_tfs, list) else []
    )
    st.session_state[WIDGET_KEY_LEVELS_ADVANCED] = levels_advanced_enabled(draft.levels)
    st.session_state[WIDGET_KEY_VWAP_WINDOWS] = format_csv_values(
        draft.levels.get("vwap_windows", DEFAULT_LEVELS_SETTINGS["vwap_windows"])
    )
    st.session_state[WIDGET_KEY_POC_WINDOWS] = format_csv_values(
        draft.levels.get("poc_windows", DEFAULT_LEVELS_SETTINGS["poc_windows"])
    )
    st.session_state[WIDGET_KEY_PREV30M_ENABLED] = bool(
        draft.levels.get("prev30m_vwap_enabled", DEFAULT_LEVELS_SETTINGS["prev30m_vwap_enabled"])
    )
    st.session_state[WIDGET_KEY_PIVOTS_ENABLED] = bool(
        draft.levels.get("pivots_enabled", DEFAULT_LEVELS_SETTINGS["pivots_enabled"])
    )
    st.session_state[WIDGET_KEY_PIVOT_TIMEFRAMES] = format_csv_values(
        draft.levels.get("pivot_timeframes", DEFAULT_LEVELS_SETTINGS["pivot_timeframes"])
    )
    st.session_state[WIDGET_KEY_CORE_LEVEL] = list(draft.core_level)
    for index, partner_set in enumerate(draft.partner_levels):
        st.session_state[_partner_set_widget_key(index)] = list(partner_set)
    st.session_state[WIDGET_KEY_CONFLUENCE_GLOBAL] = "global_cluster" in draft.confluence_mode
    st.session_state[WIDGET_KEY_CONFLUENCE_ANCHOR] = "anchor_rules" in draft.confluence_mode
    st.session_state[WIDGET_KEY_TRIGGER] = list(draft.trigger)
    st.session_state[WIDGET_KEY_TRIGGER_TIMEFRAME] = list(draft.trigger_timeframe)
    st.session_state[WIDGET_KEY_OTF] = [
        preset_id for preset_id in otf_preset_ids(draft.otf) if preset_id is not None
    ]
    st.session_state[WIDGET_KEY_DIRECTION_MODE] = (
        DIRECTION_MODE_FACTOR if draft.direction_as_factor else DIRECTION_MODE_CONSTANT
    )
    st.session_state[WIDGET_KEY_DIRECTION_CONSTANT] = draft.direction_constant
    st.session_state[WIDGET_KEY_DIRECTION_VALUES] = list(draft.direction_values)
    st.session_state[WIDGET_KEY_TOLERANCE_TICKS] = float(draft.tolerance_ticks)
    st.session_state[WIDGET_KEY_NAKED_ONLY] = bool(draft.naked_only)
    st.session_state[WIDGET_KEY_NAKED_REQUIREMENT] = draft.naked_requirement
    backtest = draft.backtest
    st.session_state[WIDGET_KEY_STOP_LOSS] = int(backtest.get("stop_loss_ticks") or 8)
    st.session_state[WIDGET_KEY_TAKE_PROFIT] = int(backtest.get("take_profit_ticks") or 16)
    st.session_state[WIDGET_KEY_COMMISSION] = float(backtest.get("commission_per_side") or 0.0)
    st.session_state[WIDGET_KEY_SLIPPAGE] = float(backtest.get("slippage_ticks") or 0.0)
    st.session_state[WIDGET_KEY_EXPOSURE_POLICY] = str(
        backtest.get("exposure_policy") or "single_position"
    )
    st.session_state[WIDGET_KEY_INTRABAR_MODEL] = str(backtest.get("intrabar_model") or "sl_first")
    st.session_state[WIDGET_KEY_FLAT_BY_SESSION_CLOSE] = bool(
        backtest.get("flat_by_session_close", False)
    )
    st.session_state[WIDGET_KEY_BATTERY_GRID] = draft.grid.get("enabled") is True
    st.session_state[WIDGET_KEY_BATTERY_VALIDATION] = draft.validation.get("enabled") is True
    st.session_state[WIDGET_KEY_BATTERY_WALK_FORWARD] = draft.walk_forward.get("enabled") is True
    st.session_state[WIDGET_KEY_GRID_SL_VALUES] = format_csv_values(
        draft.grid.get("stop_loss_ticks_values")
    )
    st.session_state[WIDGET_KEY_GRID_TP_VALUES] = format_csv_values(
        draft.grid.get("take_profit_ticks_values")
    )
    st.session_state[WIDGET_KEY_MIN_CONFLUENCES] = int(draft.min_confluences)
    st.session_state[WIDGET_KEY_MAX_CONFLUENCES] = int(draft.max_confluences)
    st.session_state[WIDGET_KEY_MIN_VALID_CONFLUENCES] = int(draft.min_valid_confluences)
    st.session_state[WIDGET_KEY_FROM_PARTNERS] = draft.from_partners
    st.session_state[WIDGET_KEY_STAGE_MODE] = infer_stage_mode_label(draft.stage_mode)
    domains = declared_factor_domains(draft)
    for axis in domains:
        raw_include = draft.stage_include.get(axis) if draft.stage_mode == "filter" else None
        labels = (
            [format_stage_value(axis, item) for item in raw_include]
            if isinstance(raw_include, list)
            else []
        )
        allowed = [format_stage_value(axis, item) for item in domains[axis]]
        st.session_state[_stage_include_widget_key(axis)] = clamp_widget_selection(labels, allowed)
    st.session_state[WIDGET_KEY_EXPLICIT_DELETE] = []
    st.session_state[WIDGET_KEY_PRIMARY_METRIC] = draft.primary_metric
    st.session_state[WIDGET_KEY_MIN_TRADES] = int(draft.min_trades)
    st.session_state[WIDGET_KEY_MULTIPLE_TESTING] = draft.multiple_testing
    factor_keys = set(domains)
    if draft.group_by is not None:
        group_by_widget = constrain_group_by(list(draft.group_by), factor_keys)
    elif draft.emit_group_by:
        group_by_widget = []
    else:
        group_by_widget = preferred_group_by(factor_keys)
    st.session_state[WIDGET_KEY_GROUP_BY] = group_by_widget
    st.session_state[WIDGET_KEY_OTF_BASELINE] = draft.otf_baseline.get("enabled") is True


def _default_partner_token(catalog: tuple[str, ...], cores: list[str]) -> str:
    core_set = {str(token) for token in cores}
    for token in catalog:
        if token not in core_set:
            return token
    if catalog:
        return catalog[0]
    return "pdPOC"


def _int_list(values: Any) -> list[int]:
    out: list[int] = []
    if not isinstance(values, list):
        return out
    for item in values:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _session_int_list(key: str, fallback: Any = None) -> list[int]:
    """Read a multiselect list without treating ``[]`` as missing (falsy ``or``)."""
    raw = st.session_state.get(key)
    if raw is None:
        return _int_list(fallback)
    return _int_list(raw)


def _clamped_multiselect(key: str, options: list[Any]) -> list[Any] | None:
    """Return a clamped selection when session values left ``options``, else None."""
    raw = st.session_state.get(key)
    if raw is None:
        return None
    clamped = clamp_widget_selection(raw, options)
    if list(raw) != clamped:
        return clamped
    return None


def _draft_from_builder_widgets(base: StudyDraft) -> StudyDraft:
    """Collect widget values onto a copy of ``base`` (preserves stage/report/pass-through)."""
    draft = draft_from_mapping(draft_to_mapping(base))
    draft.name = str(st.session_state.get(WIDGET_KEY_NAME) or "").strip() or "untitled_study"
    description = st.session_state.get(WIDGET_KEY_DESCRIPTION)
    if base.description is None and (description is None or str(description) == ""):
        draft.description = None
    else:
        draft.description = str(description or "")
    output_raw = str(st.session_state.get(WIDGET_KEY_OUTPUT_DIR) or "").strip()
    draft.output_dir = output_raw or None
    draft.workers = int(st.session_state.get(WIDGET_KEY_WORKERS) or 1)
    draft.confirm_above_runs = int(st.session_state.get(WIDGET_KEY_CONFIRM_ABOVE_RUNS) or 200)
    draft.dataset_path = str(st.session_state.get(WIDGET_KEY_DATASET_PATH) or "").strip()
    draft.instrument = str(st.session_state.get(WIDGET_KEY_INSTRUMENT) or draft.instrument)
    timezone = str(st.session_state.get(WIDGET_KEY_SOURCE_TIMEZONE) or "").strip()
    draft.source_timezone = timezone or None
    draft.format_profile = normalize_builder_format_profile(
        st.session_state.get(WIDGET_KEY_FORMAT_PROFILE)
    )
    draft.ingestion_mode = _resolved_builder_ingestion_mode(
        st.session_state.get(WIDGET_KEY_INGESTION_MODE)
    )

    levels = copy.deepcopy(dict(draft.levels))
    # Persist [] when the operator clears lengths. Omitting the key lets
    # closed_level_token_set merge DEFAULT_LEVELS_SETTINGS [50, 200] / [9, 21].
    levels["sma_lengths"] = _session_int_list(WIDGET_KEY_SMA_LENGTHS)
    levels["ema_lengths"] = _session_int_list(WIDGET_KEY_EMA_LENGTHS)
    levels = apply_levels_tf_mode(
        levels,
        "sma_timeframes",
        str(st.session_state.get(WIDGET_KEY_SMA_TF_MODE) or TF_MODE_EXPLICIT),
        [str(item) for item in (st.session_state.get(WIDGET_KEY_SMA_TIMEFRAMES) or [])],
    )
    levels = apply_levels_tf_mode(
        levels,
        "ema_timeframes",
        str(st.session_state.get(WIDGET_KEY_EMA_TF_MODE) or TF_MODE_EXPLICIT),
        [str(item) for item in (st.session_state.get(WIDGET_KEY_EMA_TIMEFRAMES) or [])],
    )
    if st.session_state.get(WIDGET_KEY_LEVELS_ADVANCED):
        levels["vwap_windows"] = parse_csv_tokens(
            str(st.session_state.get(WIDGET_KEY_VWAP_WINDOWS) or "")
        )
        levels["poc_windows"] = parse_csv_tokens(
            str(st.session_state.get(WIDGET_KEY_POC_WINDOWS) or "")
        )
        levels["prev30m_vwap_enabled"] = bool(st.session_state.get(WIDGET_KEY_PREV30M_ENABLED))
        levels["pivots_enabled"] = bool(st.session_state.get(WIDGET_KEY_PIVOTS_ENABLED))
        levels["pivot_timeframes"] = parse_csv_tokens(
            str(st.session_state.get(WIDGET_KEY_PIVOT_TIMEFRAMES) or "")
        )
    else:
        for key in (
            "vwap_windows",
            "poc_windows",
            "prev30m_vwap_enabled",
            "pivots_enabled",
            "pivot_timeframes",
        ):
            levels.pop(key, None)
    draft.levels = levels

    draft.core_level = [str(item) for item in (st.session_state.get(WIDGET_KEY_CORE_LEVEL) or [])]
    partner_sets: list[list[str]] = []
    for index in range(max(len(base.partner_levels), 1)):
        raw = st.session_state.get(_partner_set_widget_key(index))
        if raw is None:
            if index < len(base.partner_levels):
                partner_sets.append(list(base.partner_levels[index]))
            continue
        partner_sets.append([str(item) for item in raw])
    draft.partner_levels = coerce_partner_levels(partner_sets)
    modes: list[str] = []
    if st.session_state.get(WIDGET_KEY_CONFLUENCE_GLOBAL):
        modes.append("global_cluster")
    if st.session_state.get(WIDGET_KEY_CONFLUENCE_ANCHOR):
        modes.append("anchor_rules")
    draft.confluence_mode = modes
    draft.trigger = [str(item) for item in (st.session_state.get(WIDGET_KEY_TRIGGER) or [])]
    draft.trigger_timeframe = [
        str(item) for item in (st.session_state.get(WIDGET_KEY_TRIGGER_TIMEFRAME) or [])
    ]
    draft.otf = otf_for_selected_presets(
        [str(item) for item in (st.session_state.get(WIDGET_KEY_OTF) or [])],
        draft.otf,
    )
    draft.direction_as_factor = (
        st.session_state.get(WIDGET_KEY_DIRECTION_MODE) == DIRECTION_MODE_FACTOR
    )
    draft.direction_constant = str(st.session_state.get(WIDGET_KEY_DIRECTION_CONSTANT) or "both")
    draft.direction_values = [
        str(item) for item in (st.session_state.get(WIDGET_KEY_DIRECTION_VALUES) or [])
    ]
    draft.tolerance_ticks = coerce_whole_number(st.session_state.get(WIDGET_KEY_TOLERANCE_TICKS, 0))
    draft.naked_only = bool(st.session_state.get(WIDGET_KEY_NAKED_ONLY))
    draft.naked_requirement = str(st.session_state.get(WIDGET_KEY_NAKED_REQUIREMENT) or "any")
    backtest = copy.deepcopy(dict(draft.backtest))
    backtest["stop_loss_ticks"] = int(st.session_state.get(WIDGET_KEY_STOP_LOSS) or 8)
    backtest["take_profit_ticks"] = int(st.session_state.get(WIDGET_KEY_TAKE_PROFIT) or 16)
    backtest["commission_per_side"] = float(st.session_state.get(WIDGET_KEY_COMMISSION) or 0.0)
    backtest["slippage_ticks"] = float(st.session_state.get(WIDGET_KEY_SLIPPAGE) or 0.0)
    backtest["exposure_policy"] = str(
        st.session_state.get(WIDGET_KEY_EXPOSURE_POLICY) or "single_position"
    )
    backtest["intrabar_model"] = str(st.session_state.get(WIDGET_KEY_INTRABAR_MODEL) or "sl_first")
    backtest["flat_by_session_close"] = bool(st.session_state.get(WIDGET_KEY_FLAT_BY_SESSION_CLOSE))
    draft.backtest = backtest
    draft.grid = apply_grid_tick_widgets(
        draft.grid,
        enabled=bool(st.session_state.get(WIDGET_KEY_BATTERY_GRID)),
        sl_text=str(st.session_state.get(WIDGET_KEY_GRID_SL_VALUES) or ""),
        tp_text=str(st.session_state.get(WIDGET_KEY_GRID_TP_VALUES) or ""),
    )
    validation = copy.deepcopy(dict(draft.validation))
    validation["enabled"] = bool(st.session_state.get(WIDGET_KEY_BATTERY_VALIDATION))
    draft.validation = validation
    walk_forward = copy.deepcopy(dict(draft.walk_forward))
    walk_forward["enabled"] = bool(st.session_state.get(WIDGET_KEY_BATTERY_WALK_FORWARD))
    draft.walk_forward = walk_forward
    draft.min_confluences = int(st.session_state.get(WIDGET_KEY_MIN_CONFLUENCES) or 2)
    draft.max_confluences = int(st.session_state.get(WIDGET_KEY_MAX_CONFLUENCES) or 2)
    draft.min_valid_confluences = int(st.session_state.get(WIDGET_KEY_MIN_VALID_CONFLUENCES) or 1)
    draft.from_partners = str(st.session_state.get(WIDGET_KEY_FROM_PARTNERS) or "required")
    domains = declared_factor_domains(draft)
    factor_keys = set(domains)
    if WIDGET_KEY_STAGE_MODE in st.session_state:
        draft.stage_mode = stage_mode_from_label(str(st.session_state[WIDGET_KEY_STAGE_MODE]))
        if draft.stage_mode == "filter":
            selected_labels = {
                axis: [
                    str(item)
                    for item in (st.session_state.get(_stage_include_widget_key(axis)) or [])
                ]
                for axis in domains
            }
            draft.stage_include = collect_stage_include(domains, selected_labels)
    if WIDGET_KEY_PRIMARY_METRIC in st.session_state:
        draft.primary_metric = str(st.session_state[WIDGET_KEY_PRIMARY_METRIC])
        if draft.primary_metric not in PRIMARY_METRIC_OPTIONS:
            draft.primary_metric = "expectancy_r"
    if WIDGET_KEY_MIN_TRADES in st.session_state:
        draft.min_trades = int(st.session_state[WIDGET_KEY_MIN_TRADES] or 0)
    if WIDGET_KEY_MULTIPLE_TESTING in st.session_state:
        draft.multiple_testing = str(st.session_state[WIDGET_KEY_MULTIPLE_TESTING])
        if draft.multiple_testing not in MULTIPLE_TESTING_OPTIONS:
            draft.multiple_testing = "warn"
    if WIDGET_KEY_GROUP_BY in st.session_state:
        selected_group = constrain_group_by(
            [str(item) for item in (st.session_state.get(WIDGET_KEY_GROUP_BY) or [])],
            factor_keys,
        )
        if selected_group:
            draft.group_by = selected_group
            draft.emit_group_by = True
        else:
            draft.group_by = None
            draft.emit_group_by = bool(base.emit_group_by and base.group_by is None)
    if WIDGET_KEY_OTF_BASELINE in st.session_state:
        baseline = copy.deepcopy(dict(draft.otf_baseline))
        baseline["enabled"] = bool(st.session_state[WIDGET_KEY_OTF_BASELINE])
        draft.otf_baseline = baseline
    return draft


def _apply_builder_draft_to_preview(draft: StudyDraft) -> str:
    """Locked SB2 Apply to Preview sequence (§4.7). Does not spawn or auto-preview."""
    yaml_text = emit_study_yaml(draft)
    prev_cached_yaml = st.session_state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)
    st.session_state[STUDIES_PREVIEW_YAML_KEY] = yaml_text
    st.session_state.pop(STUDIES_PREVIEW_CACHED_KEY, None)
    st.session_state.pop(STUDIES_PREVIEW_CACHED_YAML_KEY, None)
    reset_launch_session_for_preview(
        st.session_state,
        prev_cached_yaml=prev_cached_yaml if isinstance(prev_cached_yaml, str) else None,
        new_yaml=yaml_text,
    )
    return yaml_text


def _render_builder_live_strip(draft: StudyDraft) -> tuple[StudyPreview | None, Exception | None]:
    try:
        spec = emit_study_spec(draft)
        preview = preview_study_spec(spec)
    except (StudySpecError, ValueError) as exc:
        st.error(str(exc))
        return None, exc
    st.subheader(preview.study_name or draft.name)
    cols = st.columns(4)
    shown_count = preview.run_count if preview.expanded else preview.effective_run_count_estimate
    cols[0].metric("Cells (effective)", shown_count)
    cols[1].metric("Full cartesian", preview.cartesian_product)
    cols[2].metric("Workers", preview.workers)
    cols[3].metric("Needs --confirm", "yes" if preview.needs_confirm else "no")
    st.caption(
        f"confirm_above_runs={preview.confirm_above_runs} · "
        f"expanded={preview.expanded} · "
        f"identity `{preview.study_identity_hash}` "
        "(launch re-hashes after dataset pin)"
    )
    if preview.cap_warning:
        st.warning(preview.cap_warning)
    st.write("Axis sizes:", preview.axis_sizes)
    if preview.effective_run_count_estimate != preview.cartesian_product:
        st.caption(
            f"Staged/matched estimate {preview.effective_run_count_estimate} vs "
            f"unstaged cartesian {preview.cartesian_product}."
        )
    st.write("Battery flags:", preview.battery_enabled)
    for line in preview.hint_lines:
        if line.startswith("WARNING"):
            st.warning(line)
        else:
            st.caption(line)
    st.info(_BUILDER_HONESTY)
    return preview, None


def _render_ma_length_block(label: str, lengths_key: str, add_key: str, current: list[int]) -> None:
    extra_raw = st.session_state.get(add_key)
    extra = int(extra_raw) if extra_raw not in (None, "") else None
    options = ma_length_options(current, extra)
    st.multiselect(f"{label} lengths", options=options, key=lengths_key)
    add_kwargs: dict[str, Any] = {
        "min_value": 1,
        "step": 1,
        "key": add_key,
        "help": (
            "Typed lengths appear in the multiselect on the next rerun; select them to include."
        ),
    }
    if add_key not in st.session_state:
        add_kwargs["value"] = 9
    st.number_input(f"Add {label} length", **add_kwargs)


def _render_tf_mode_block(label: str, mode_key: str, tfs_key: str) -> None:
    st.radio(f"{label} timeframes", options=list(TF_MODE_OPTIONS), key=mode_key)
    if st.session_state.get(mode_key) == TF_MODE_EXPLICIT:
        st.multiselect(
            f"{label} explicit TFs",
            options=list(SUPPORTED_INDICATOR_TIMEFRAMES),
            key=tfs_key,
        )


def _hydrate_builder_draft(draft: StudyDraft) -> None:
    st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(draft)
    st.session_state[STUDIES_BUILDER_PENDING_SYNC_KEY] = True
    st.rerun()


def _render_builder_stage(partial: StudyDraft) -> None:
    st.markdown("### Stage")
    st.radio("Stage mode", options=list(STAGE_MODE_OPTIONS), key=WIDGET_KEY_STAGE_MODE)
    mode = st.session_state.get(WIDGET_KEY_STAGE_MODE)
    domains = declared_factor_domains(partial)
    if mode == STAGE_MODE_FILTER:
        st.caption(
            "Include pickers are ⊆ the current factor widgets. Empty axis → omitted. "
            "Filter requires at least one include key."
        )
        for axis, domain in domains.items():
            labels = [format_stage_value(axis, item) for item in domain]
            include_key = _stage_include_widget_key(axis)
            clamped_include = _clamped_multiselect(include_key, labels)
            if clamped_include is not None:
                st.session_state[_stage_include_widget_key(axis)] = clamped_include
            st.multiselect(
                f"include.{axis}",
                options=labels,
                key=_stage_include_widget_key(axis),
            )
    elif mode == STAGE_MODE_EXPLICIT:
        cells = list(partial.stage_cells)
        if not cells:
            st.warning(
                "explicit_cells is empty — hydrate a promote draft or Preview YAML. "
                "Emit refuses an empty cell list. No add-cell constructor."
            )
            return
        rows = []
        for index, cell in enumerate(cells):
            row = {"#": index}
            for axis, value in cell.items():
                row[axis] = format_stage_value(axis, value)
            rows.append(row)
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("Delete selected rows only. Promote draft / YAML hydrate is the add path.")
        delete_options = list(range(len(cells)))
        clamped_delete = _clamped_multiselect(WIDGET_KEY_EXPLICIT_DELETE, delete_options)
        if clamped_delete is not None:
            st.session_state[WIDGET_KEY_EXPLICIT_DELETE] = clamped_delete
        st.multiselect(
            "Rows to delete",
            options=delete_options,
            format_func=lambda index: explicit_cell_row_label(index, cells[index]),
            key=WIDGET_KEY_EXPLICIT_DELETE,
        )
        if st.button("Delete selected rows"):
            selected = {
                int(item) for item in (st.session_state.get(WIDGET_KEY_EXPLICIT_DELETE) or [])
            }
            draft = _draft_from_builder_widgets(partial)
            draft.stage_cells = delete_stage_cells(draft.stage_cells, selected)
            _hydrate_builder_draft(draft)


def _render_builder_report(partial: StudyDraft) -> None:
    st.markdown("### Report")
    factor_keys = set(declared_factor_domains(partial))
    metric_options = list(PRIMARY_METRIC_OPTIONS)
    if partial.primary_metric not in metric_options:
        metric_options = [partial.primary_metric, *metric_options]
    st.selectbox("primary_metric", options=metric_options, key=WIDGET_KEY_PRIMARY_METRIC)
    report_cols = st.columns(2)
    report_cols[0].number_input("min_trades", min_value=0, step=1, key=WIDGET_KEY_MIN_TRADES)
    testing_options = list(MULTIPLE_TESTING_OPTIONS)
    if partial.multiple_testing not in testing_options:
        testing_options = [partial.multiple_testing, *testing_options]
    report_cols[1].selectbox(
        "multiple_testing", options=testing_options, key=WIDGET_KEY_MULTIPLE_TESTING
    )
    group_options = sorted(factor_keys)
    clamped_group = _clamped_multiselect(WIDGET_KEY_GROUP_BY, group_options)
    if clamped_group is not None:
        st.session_state[WIDGET_KEY_GROUP_BY] = clamped_group
    st.multiselect(
        "group_by",
        options=group_options,
        key=WIDGET_KEY_GROUP_BY,
        help="Only declared factor axes. Empty omits the key (normalize default) unless the draft had explicit null.",
    )
    st.checkbox("otf_baseline.enabled", key=WIDGET_KEY_OTF_BASELINE)


def _render_build() -> None:
    base = _ensure_builder_draft()
    st.caption(
        "Author a closed StudySpec. Apply to Preview writes YAML onto the Preview tab — "
        "Validate / Preview is still required. This tab does not spawn CLI. "
        "Launch still refuses a missing dataset CSV; preview does not need the file."
    )

    st.markdown("### Identity")
    st.text_input("Study name", key=WIDGET_KEY_NAME)
    st.text_input("Description", key=WIDGET_KEY_DESCRIPTION)
    id_cols = st.columns(3)
    id_cols[0].number_input("Workers", min_value=1, step=1, key=WIDGET_KEY_WORKERS)
    id_cols[1].number_input(
        "confirm_above_runs", min_value=1, step=1, key=WIDGET_KEY_CONFIRM_ABOVE_RUNS
    )
    id_cols[2].text_input(
        "Output dir (optional)",
        key=WIDGET_KEY_OUTPUT_DIR,
        placeholder="results/studies/<name>",
    )

    st.markdown("### Dataset")
    st.text_input("Dataset path", key=WIDGET_KEY_DATASET_PATH)
    instrument_options = list(INSTRUMENTS.keys())
    if base.instrument and base.instrument not in instrument_options:
        instrument_options = [base.instrument, *instrument_options]
    st.selectbox("Instrument", options=instrument_options, key=WIDGET_KEY_INSTRUMENT)
    timezone_options = ["", *TIMEZONE_OPTIONS]
    if base.source_timezone and base.source_timezone not in timezone_options:
        timezone_options = [base.source_timezone, *timezone_options]
    st.selectbox("Source timezone", options=timezone_options, key=WIDGET_KEY_SOURCE_TIMEZONE)
    ingest_options = list(_INGESTION_MODE_OPTIONS)
    if (
        isinstance(base.ingestion_mode, str)
        and base.ingestion_mode.strip()
        and base.ingestion_mode not in ingest_options
    ):
        ingest_options = [base.ingestion_mode, *ingest_options]
    if st.session_state.get(WIDGET_KEY_INGESTION_MODE) not in ingest_options:
        seeded = _resolved_builder_ingestion_mode(base.ingestion_mode)
        st.session_state[WIDGET_KEY_INGESTION_MODE] = seeded
        if seeded not in ingest_options:
            ingest_options = [seeded, *ingest_options]
    # No on_change: emit/warnings handle profile and intrabar contradictions.
    st.radio(
        "Ingestion mode",
        options=ingest_options,
        format_func=lambda key: _INGESTION_MODE_LABELS.get(key, str(key)),
        horizontal=True,
        key=WIDGET_KEY_INGESTION_MODE,
        help=(
            "Recommended for Quantower 15-second exports: derive one-minute "
            "canonical bars and retain 15s for R12. Legacy treats the file as "
            "the decision timeframe. Changing this radio does not rewrite "
            "format profile or intrabar model."
        ),
    )
    if (
        st.session_state.get(WIDGET_KEY_INGESTION_MODE)
        == INGESTION_MODE_15S_PRIMARY_DERIVE_1M
    ):
        st.caption(
            "15s-primary requires Quantower History Exporter (semicolon). "
            "Do not set subtimeframe_path. Recommended intrabar_model is "
            "subtimeframe_conservative (sparse minutes). Launch still requires "
            "the CSV on disk."
        )
    else:
        st.caption(
            "Legacy: the file is the decision timeframe. Optional "
            "subtimeframe_path remains YAML/hydrate-only — this tab does not "
            "add a subtimeframe path widget."
        )
    profile_options = list(FORMAT_PROFILE_LABELS)
    if (
        isinstance(base.format_profile, str)
        and base.format_profile.strip()
        and base.format_profile not in profile_options
    ):
        profile_options = [base.format_profile, *profile_options]
    if st.session_state.get(WIDGET_KEY_FORMAT_PROFILE) not in profile_options:
        seeded = normalize_builder_format_profile(base.format_profile)
        st.session_state[WIDGET_KEY_FORMAT_PROFILE] = seeded
        if seeded not in profile_options:
            profile_options = [seeded, *profile_options]
    st.selectbox(
        "CSV format profile",
        options=profile_options,
        format_func=lambda key: FORMAT_PROFILE_LABELS.get(key, str(key)),
        help="Explicit selection only; ThesisTester never auto-detects vendor formats.",
        key=WIDGET_KEY_FORMAT_PROFILE,
    )

    st.markdown("### Levels → tokens")
    length_cols = st.columns(2)
    with length_cols[0]:
        _render_ma_length_block(
            "SMA",
            WIDGET_KEY_SMA_LENGTHS,
            WIDGET_KEY_SMA_ADD_LENGTH,
            _session_int_list(WIDGET_KEY_SMA_LENGTHS, base.levels.get("sma_lengths")),
        )
        _render_tf_mode_block("SMA", WIDGET_KEY_SMA_TF_MODE, WIDGET_KEY_SMA_TIMEFRAMES)
    with length_cols[1]:
        _render_ma_length_block(
            "EMA",
            WIDGET_KEY_EMA_LENGTHS,
            WIDGET_KEY_EMA_ADD_LENGTH,
            _session_int_list(WIDGET_KEY_EMA_LENGTHS, base.levels.get("ema_lengths")),
        )
        _render_tf_mode_block("EMA", WIDGET_KEY_EMA_TF_MODE, WIDGET_KEY_EMA_TIMEFRAMES)
    st.checkbox("Override windows / extras", key=WIDGET_KEY_LEVELS_ADVANCED)
    if st.session_state.get(WIDGET_KEY_LEVELS_ADVANCED):
        with st.expander("vwap / poc / prev30m / pivots", expanded=True):
            st.text_input("vwap_windows", key=WIDGET_KEY_VWAP_WINDOWS)
            st.text_input("poc_windows", key=WIDGET_KEY_POC_WINDOWS)
            st.checkbox("prev30m_vwap_enabled", key=WIDGET_KEY_PREV30M_ENABLED)
            st.checkbox("pivots_enabled", key=WIDGET_KEY_PIVOTS_ENABLED)
            st.text_input("pivot_timeframes", key=WIDGET_KEY_PIVOT_TIMEFRAMES)

    live_levels = apply_levels_tf_mode(
        apply_levels_tf_mode(
            {
                **dict(base.levels),
                "sma_lengths": _session_int_list(
                    WIDGET_KEY_SMA_LENGTHS, base.levels.get("sma_lengths")
                ),
                "ema_lengths": _session_int_list(
                    WIDGET_KEY_EMA_LENGTHS, base.levels.get("ema_lengths")
                ),
            },
            "sma_timeframes",
            str(
                st.session_state.get(WIDGET_KEY_SMA_TF_MODE)
                or infer_tf_mode(base.levels, "sma_timeframes")
            ),
            [str(item) for item in (st.session_state.get(WIDGET_KEY_SMA_TIMEFRAMES) or [])],
        ),
        "ema_timeframes",
        str(
            st.session_state.get(WIDGET_KEY_EMA_TF_MODE)
            or infer_tf_mode(base.levels, "ema_timeframes")
        ),
        [str(item) for item in (st.session_state.get(WIDGET_KEY_EMA_TIMEFRAMES) or [])],
    )
    catalog = builder_token_catalog(live_levels)
    shown = ", ".join(catalog[:20])
    extra = f" … +{len(catalog) - 20} more" if len(catalog) > 20 else ""
    st.caption(f"**Closed tokens ({len(catalog)}):** {shown}{extra}")

    st.markdown("### Factors")
    core_options = list(dict.fromkeys([*catalog, *base.core_level]))
    st.multiselect("core_level", options=core_options, key=WIDGET_KEY_CORE_LEVEL)
    st.caption("partner_levels is always a list of sets (list-of-lists).")
    partner_count = max(len(base.partner_levels), 1)
    for index in range(partner_count):
        current = list(base.partner_levels[index]) if index < len(base.partner_levels) else []
        options = list(dict.fromkeys([*catalog, *current]))
        st.multiselect(
            f"Partner set {index + 1}",
            options=options,
            key=_partner_set_widget_key(index),
        )
    add_col, remove_col = st.columns(2)
    if add_col.button("Add partner set"):
        draft = _draft_from_builder_widgets(base)
        draft.partner_levels = coerce_partner_levels(draft.partner_levels)
        draft.partner_levels.append([_default_partner_token(catalog, draft.core_level)])
        st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(draft)
        st.session_state[STUDIES_BUILDER_PENDING_SYNC_KEY] = True
        st.rerun()
    if remove_col.button("Remove last partner set", disabled=partner_count <= 1):
        draft = _draft_from_builder_widgets(base)
        if len(draft.partner_levels) > 1:
            draft.partner_levels = draft.partner_levels[:-1]
        st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(draft)
        st.session_state[STUDIES_BUILDER_PENDING_SYNC_KEY] = True
        st.rerun()
    mode_cols = st.columns(2)
    mode_cols[0].checkbox("global_cluster", key=WIDGET_KEY_CONFLUENCE_GLOBAL)
    mode_cols[1].checkbox("anchor_rules", key=WIDGET_KEY_CONFLUENCE_ANCHOR)
    trigger_options = [item for item in _TRIGGER_OPTIONS if item in VALID_TRIGGERS]
    st.multiselect("trigger", options=trigger_options, key=WIDGET_KEY_TRIGGER)
    st.multiselect(
        "trigger_timeframe",
        options=list(TRIGGER_TIMEFRAME_CHOICES),
        key=WIDGET_KEY_TRIGGER_TIMEFRAME,
        help="30min is not a valid trigger timeframe.",
    )
    st.pills(
        "OTF presets",
        options=list(OTF_PRESET_ORDER),
        format_func=lambda preset_id: OTF_PRESET_LABELS.get(preset_id, preset_id),
        selection_mode="multi",
        key=WIDGET_KEY_OTF,
        help="No chips → OTF axis omitted (expand treats as off).",
    )
    st.radio("Direction", options=list(DIRECTION_MODE_OPTIONS), key=WIDGET_KEY_DIRECTION_MODE)
    if st.session_state.get(WIDGET_KEY_DIRECTION_MODE) == DIRECTION_MODE_FACTOR:
        st.multiselect(
            "Direction factor values",
            options=list(_DIRECTION_VALUES),
            key=WIDGET_KEY_DIRECTION_VALUES,
        )
    else:
        st.selectbox(
            "Direction constant",
            options=list(_DIRECTION_VALUES),
            key=WIDGET_KEY_DIRECTION_CONSTANT,
        )

    st.markdown("### Constants")
    const_cols = st.columns(3)
    const_cols[0].number_input(
        "tolerance_ticks", min_value=0.0, step=0.5, key=WIDGET_KEY_TOLERANCE_TICKS
    )
    const_cols[1].checkbox("naked_only", key=WIDGET_KEY_NAKED_ONLY)
    const_cols[2].selectbox(
        "naked_requirement", options=list(_NAKED_REQUIREMENTS), key=WIDGET_KEY_NAKED_REQUIREMENT
    )
    st.markdown("#### Backtest (required)")
    bt_cols = st.columns(4)
    bt_cols[0].number_input("stop_loss_ticks", min_value=1, step=1, key=WIDGET_KEY_STOP_LOSS)
    bt_cols[1].number_input("take_profit_ticks", min_value=1, step=1, key=WIDGET_KEY_TAKE_PROFIT)
    bt_cols[2].number_input(
        "commission_per_side", min_value=0.0, step=0.25, key=WIDGET_KEY_COMMISSION
    )
    bt_cols[3].number_input("slippage_ticks", min_value=0.0, step=0.25, key=WIDGET_KEY_SLIPPAGE)
    bt2 = st.columns(3)
    exposure_options = list(EXPOSURE_POLICY_OPTIONS)
    current_exposure = str(base.backtest.get("exposure_policy") or "single_position")
    if current_exposure not in exposure_options:
        exposure_options = [current_exposure, *exposure_options]
    bt2[0].selectbox("exposure_policy", options=exposure_options, key=WIDGET_KEY_EXPOSURE_POLICY)
    intrabar_options = sorted(VALID_INTRABAR_MODELS)
    current_intrabar = str(base.backtest.get("intrabar_model") or "sl_first")
    if current_intrabar not in intrabar_options:
        intrabar_options = [current_intrabar, *intrabar_options]
    bt2[1].selectbox("intrabar_model", options=intrabar_options, key=WIDGET_KEY_INTRABAR_MODEL)
    bt2[2].checkbox("flat_by_session_close", key=WIDGET_KEY_FLAT_BY_SESSION_CLOSE)
    st.markdown("#### Batteries")
    bat_cols = st.columns(3)
    bat_cols[0].checkbox("grid.enabled", key=WIDGET_KEY_BATTERY_GRID)
    bat_cols[1].checkbox("validation.enabled", key=WIDGET_KEY_BATTERY_VALIDATION)
    bat_cols[2].checkbox("walk_forward.enabled", key=WIDGET_KEY_BATTERY_WALK_FORWARD)
    if st.session_state.get(WIDGET_KEY_BATTERY_GRID):
        st.text_input(
            "grid stop_loss_ticks_values",
            key=WIDGET_KEY_GRID_SL_VALUES,
            help="Comma-separated ints. Required when grid is enabled.",
        )
        st.text_input(
            "grid take_profit_ticks_values",
            key=WIDGET_KEY_GRID_TP_VALUES,
            help="Comma-separated ints. Required when grid is enabled.",
        )
    with st.expander("Advanced constants", expanded=False):
        st.caption(
            "expand overrides min/max confluences for global_cluster; these are not factor axes."
        )
        adv = st.columns(3)
        adv[0].number_input("min_confluences", min_value=1, step=1, key=WIDGET_KEY_MIN_CONFLUENCES)
        adv[1].number_input("max_confluences", min_value=1, step=1, key=WIDGET_KEY_MAX_CONFLUENCES)
        adv[2].number_input(
            "min_valid_confluences", min_value=1, step=1, key=WIDGET_KEY_MIN_VALID_CONFLUENCES
        )
        st.selectbox(
            "from_partners", options=list(_FROM_PARTNERS_OPTIONS), key=WIDGET_KEY_FROM_PARTNERS
        )
        st.caption(
            "entry_window / trigger_params are pass-through from the hydrated draft "
            "(SB2 does not clone Setup Builder’s entry-window block)."
        )

    partial = _draft_from_builder_widgets(base)
    _render_builder_stage(partial)
    _render_builder_report(partial)

    try:
        draft = _draft_from_builder_widgets(base)
    except (TypeError, ValueError) as exc:
        st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(base)
        st.error(str(exc))
        return
    st.session_state[STUDIES_BUILDER_DRAFT_KEY] = draft_to_mapping(draft)
    for warning in draft_warnings(draft):
        st.warning(warning)

    st.markdown("### Live strip")
    preview, emit_error = _render_builder_live_strip(draft)

    st.markdown("### Actions")
    action_cols = st.columns(4)
    start_example = action_cols[0].button("Start from example", key="_study_builder_start_example")
    load_preview = action_cols[1].button(
        "Load YAML from Preview tab", key="_study_builder_load_preview"
    )
    copy_loaded = action_cols[2].button("Copy spec from loaded dir", key="_study_builder_copy_spec")
    apply_preview = action_cols[3].button(
        "Apply to Preview",
        type="primary",
        disabled=preview is None,
        key="_study_builder_apply_preview",
    )
    if start_example:
        try:
            path = example_study_spec_path()
            hydrated = hydrate_study_yaml(path.read_text(encoding="utf-8"))
        except StudySpecError as exc:
            st.error(str(exc))
            return
        _hydrate_builder_draft(hydrated)
    if load_preview:
        raw = str(st.session_state.get(STUDIES_PREVIEW_YAML_KEY) or "")
        if not raw.strip():
            st.error("Preview YAML is empty.")
            return
        try:
            _hydrate_builder_draft(hydrate_study_yaml(raw))
        except StudySpecError as exc:
            st.error(str(exc))
            return
    if copy_loaded:
        text = _read_loaded_study_spec_text()
        if text is None:
            return
        try:
            _hydrate_builder_draft(hydrate_study_yaml(text))
        except StudySpecError as exc:
            st.error(str(exc))
            return
    if apply_preview:
        if emit_error is not None:
            st.error(str(emit_error))
            return
        try:
            _apply_builder_draft_to_preview(draft)
        except (StudySpecError, ValueError) as exc:
            st.error(str(exc))
            return
        st.success(
            "YAML is on the Preview tab — use **Validate / Preview**, then existing "
            "Run via CLI / Bind confirm. This tab does not spawn the CLI."
        )
    if preview is not None:
        try:
            yaml_text = emit_study_yaml(draft)
        except (StudySpecError, ValueError):
            yaml_text = None
        if yaml_text is not None:
            st.download_button(
                "Download StudySpec YAML",
                data=yaml_text if yaml_text.endswith("\n") else yaml_text + "\n",
                file_name=f"{draft.name or 'study'}.yaml",
                mime="text/yaml",
                help="Browser download of emit_study_yaml. Not a store write; not the Inspect study.spec.yaml path.",
            )


# Visual tab order is Inspect | Preview | Build. Execute Build before Preview
# so Apply can write STUDIES_PREVIEW_YAML_KEY (and reset the launch output-dir
# widget) before those widgets instantiate — Streamlit rejects post-mount writes.
with inspect_tab:
    _render_inspect()

with build_tab:
    _render_build()

with preview_tab:
    _render_preview()
