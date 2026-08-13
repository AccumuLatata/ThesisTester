"""RS-D2/RS-D8/RS-D9 — Studies inspect, preview, and CLI-spawn (no in-process execute)."""

from __future__ import annotations

import streamlit as st

from thesistester.study.launch import (
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

st.title("Studies")
st.caption(
    "Inspect a completed study output directory, or preview a canonical StudySpec "
    "YAML (cell count / confirm gate). Run via CLI spawns the existing "
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

inspect_tab, preview_tab = st.tabs(["Inspect output dir", "Preview StudySpec"])


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
            "Absolute or repo-relative path to a completed study dir "
            "(must contain study.spec.yaml / results_index.csv). "
            "Paths must stay under the repo working directory or the local ThesisTester store."
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
        st.caption("Enter a completed study directory, then load artifacts.")
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


def _copy_spec_from_loaded_dir() -> bool:
    active_dir = st.session_state.get(STUDIES_VIEWER_DIR_KEY)
    if not isinstance(active_dir, str) or not active_dir.strip():
        st.error("Load a study output directory on the Inspect tab first.")
        return False
    try:
        root = resolve_study_dir(active_dir, roots=default_study_viewer_roots())
    except StudyViewerError as exc:
        st.error(str(exc))
        return False
    spec_path = root / "study.spec.yaml"
    if not spec_path.is_file():
        st.error(f"No study.spec.yaml under {root}")
        return False
    st.session_state[STUDIES_PREVIEW_YAML_KEY] = spec_path.read_text(encoding="utf-8")
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


with inspect_tab:
    _render_inspect()

with preview_tab:
    _render_preview()
