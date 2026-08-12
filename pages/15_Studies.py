"""RS-D2/RS-D8 — Studies inspect viewer + authoring preview (no in-app execute)."""

from __future__ import annotations

import streamlit as st

from thesistester.study.preview import (
    STUDIES_PREVIEW_YAML_KEY,
    StudyPreview,
    example_study_spec_path,
    preview_study_yaml,
)
from thesistester.study.schema import StudySpecError
from thesistester.study.viewer import (
    STUDIES_VIEWER_DIR_KEY,
    StudyViewerError,
    default_study_viewer_roots,
    load_study_view,
    resolve_study_dir,
)

st.title("Studies")
st.caption(
    "Inspect a completed study output directory, or preview a canonical StudySpec "
    "YAML (cell count / confirm gate). Expand, run, and promote stay on the CLI "
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

    if load:
        if not str(raw_dir).strip():
            st.error("Enter a study output directory path.")
            return
        # Persist only the Studies-scoped path key so reruns (download / expander)
        # keep the view; never touch classic research session_state keys.
        st.session_state[STUDIES_VIEWER_DIR_KEY] = str(raw_dir).strip()

    active_dir = st.session_state.get(STUDIES_VIEWER_DIR_KEY)
    if refresh and (not isinstance(active_dir, str) or not active_dir.strip()):
        st.error("Load a study output directory before refreshing.")
        return
    if not isinstance(active_dir, str) or not active_dir.strip():
        st.caption("Enter a completed study directory, then load artifacts.")
        return

    try:
        model = load_study_view(active_dir, roots=default_study_viewer_roots())
    except StudyViewerError as exc:
        st.error(str(exc))
        return

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
    return True


def _render_preview_result(preview: StudyPreview) -> None:
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
        "statistical tests. Large factorials need `--confirm` on the CLI. Descriptive "
        "ranking after a run is not a validated edge. Execute remains "
        "`python -m thesistester study run …`."
    )


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
        st.rerun()

    if copy_loaded:
        if _copy_spec_from_loaded_dir():
            st.rerun()
        return

    if not do_preview:
        st.caption("Paste YAML, then Validate / Preview. Execute stays on the CLI.")
        return

    raw = st.session_state.get(STUDIES_PREVIEW_YAML_KEY, "")
    try:
        with st.spinner("Expanding StudySpec…"):
            preview = preview_study_yaml(str(raw))
    except (StudySpecError, ValueError) as exc:
        st.error(str(exc))
        return
    _render_preview_result(preview)


with inspect_tab:
    _render_inspect()

with preview_tab:
    _render_preview()
