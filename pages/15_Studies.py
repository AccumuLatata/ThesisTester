"""RS-D2 — read-only Studies viewer over completed study artifacts."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from thesistester.study.viewer import (
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

raw_dir = st.text_input(
    "Study output directory",
    value="",
    help=(
        "Absolute or repo-relative path to a completed study dir "
        "(must contain study.spec.yaml / results_index.csv). "
        "Paths must stay under the repo working directory or the local ThesisTester store."
    ),
    placeholder="out/pdPOC_stage40",
)

load = st.button("Load study artifacts", type="primary")

if not load:
    st.stop()

if not str(raw_dir).strip():
    st.error("Enter a study output directory path.")
    st.stop()

try:
    model = load_study_view(raw_dir, roots=default_study_viewer_roots())
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
overview_path = model.report.paths.get("study.overview.md")
if isinstance(overview_path, Path) and overview_path.is_file():
    st.download_button(
        "Download study.overview.md",
        data=overview_path.read_text(encoding="utf-8"),
        file_name="study.overview.md",
        mime="text/markdown",
    )
csv_path = model.report.paths.get("study.overview.csv")
if isinstance(csv_path, Path) and csv_path.is_file():
    st.download_button(
        "Download study.overview.csv",
        data=csv_path.read_text(encoding="utf-8"),
        file_name="study.overview.csv",
        mime="text/csv",
    )
with st.expander("Show study.overview.md", expanded=False):
    st.markdown(model.overview_md)
