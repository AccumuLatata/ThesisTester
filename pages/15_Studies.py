"""RS-D2 — read-only Studies viewer over completed study artifacts."""

from __future__ import annotations

import streamlit as st

from thesistester.study.viewer import (
    STUDIES_VIEWER_DIR_KEY,
    StudyViewerError,
    default_study_viewer_roots,
    load_study_view,
)

st.title("Studies")
st.caption(
    "Read-only viewer for completed Research Study Runner output directories. "
    "Expand, run, and promote stay on the CLI (or optional STUDY.* assistant tools)."
)

st.info(
    "**Honesty.** Overview ranking is descriptive screening, not a validated edge. "
    "Interpret with multiple-testing caution and `min_trades` sample-size gates. "
    "`bundle_path` lists per-cell zips — Research Bundles is upload/import oriented "
    "and is not a deep-link target from this page."
)

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

load = st.button("Load study artifacts", type="primary")

if load:
    if not str(raw_dir).strip():
        st.error("Enter a study output directory path.")
        st.stop()
    # Persist only the Studies-scoped path key so reruns (download / expander)
    # keep the view; never touch classic research session_state keys.
    st.session_state[STUDIES_VIEWER_DIR_KEY] = str(raw_dir).strip()

active_dir = st.session_state.get(STUDIES_VIEWER_DIR_KEY)
if not isinstance(active_dir, str) or not active_dir.strip():
    st.caption("Enter a completed study directory, then load artifacts.")
    st.stop()

try:
    model = load_study_view(active_dir, roots=default_study_viewer_roots())
except StudyViewerError as exc:
    st.error(str(exc))
    st.stop()

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
    st.caption(f"Counts from {source}.")
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
# Serve in-memory artifacts so the page stays read-only on disk.
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
