"""TJ9 Journal — read-only Q1–Q8 report over ingested journal/v1 artifacts.

Does not call ``run_experiment`` or ``run_study``. Does not hydrate classic
session keys. Does not write research bundles or ``results/studies/``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from thesistester.journal.report import (
    REPORT_HONESTY,
    JournalIngestError,
    journal_store_dir,
    load_journal_artifacts,
    report_from_artifacts,
)
from thesistester.persistence.local_store import display_store_path

JOURNAL_DIR_KEY = "journal_dir"
JOURNAL_INCLUDE_SMALL_N_KEY = "journal_include_small_n"
JOURNAL_CACHED_ARTIFACTS_KEY = "journal_cached_artifacts"

_EMPTY = (
    "No `journal_trades.parquet` in this directory. Run "
    "`python -m thesistester journal reconcile` (then attribute / "
    "counterfactual / match as needed) and point here. "
    "Missing later artifacts omit Q3–Q8; they are not errors."
)
_Q_TITLES = (
    ("Q1 · Costs and reconciled net", "q1"),
    ("Q2 · Where R comes from", "q2"),
    ("Q3 · Levels and tags", "q3"),
    ("Q4 · Entry vs exit", "q4"),
    ("Q5 · Direction vs drift", "q5"),
    ("Q6 · Declared rules", "q6"),
    ("Q7 · Named-cell match", "q7"),
    ("Q8 · Forward ledger", "q8"),
)


def _default_dir() -> str:
    return display_store_path(journal_store_dir())


def _ensure_defaults() -> None:
    if JOURNAL_DIR_KEY not in st.session_state:
        st.session_state[JOURNAL_DIR_KEY] = _default_dir()
    if JOURNAL_INCLUDE_SMALL_N_KEY not in st.session_state:
        st.session_state[JOURNAL_INCLUDE_SMALL_N_KEY] = False


def _show_table(frame: pd.DataFrame, *, empty: str) -> None:
    if frame is None or frame.empty:
        st.caption(empty)
        return
    st.dataframe(frame, width="stretch", hide_index=True)


def _clear_journal_cache() -> None:
    st.session_state.pop(JOURNAL_CACHED_ARTIFACTS_KEY, None)


_ensure_defaults()
st.title("Journal")
st.caption(
    "Read-only Q1–Q8 report over ingested journal/v1 artifacts. "
    "This page does not run experiments or studies."
)
st.info(f"**Honesty.** {REPORT_HONESTY}")

st.text_input(
    "Journal directory",
    key=JOURNAL_DIR_KEY,
    help="Default is `.thesistester_store/journal/v1/`. Not under execution_artifacts/.",
)
include_small = st.checkbox(
    "Show slices with n < 30",
    key=JOURNAL_INCLUDE_SMALL_N_KEY,
    help="Q2 slices with n < 30 stay hidden unless this is on. Applies after Load without a second click.",
)
load = st.button("Load report")

if load:
    raw_dir = str(st.session_state.get(JOURNAL_DIR_KEY) or "").strip()
    if not raw_dir:
        st.warning("Set a journal directory first.")
        st.stop()
    path = Path(raw_dir).expanduser()
    if not path.is_dir():
        _clear_journal_cache()
        st.caption(_EMPTY)
        st.stop()
    try:
        st.session_state[JOURNAL_CACHED_ARTIFACTS_KEY] = load_journal_artifacts(path)
    except JournalIngestError as exc:
        _clear_journal_cache()
        st.error(str(exc))
        st.stop()

artifacts = st.session_state.get(JOURNAL_CACHED_ARTIFACTS_KEY)
if artifacts is None:
    st.caption(_EMPTY)
    st.stop()

try:
    report = report_from_artifacts(artifacts, include_small_n=bool(include_small))
except JournalIngestError as exc:
    st.error(str(exc))
    st.stop()

present = report.present
if not present.get("trades"):
    st.caption(_EMPTY)
    st.stop()

st.caption(
    f"Q2 slices with n < 30: {report.hidden_slice_count}"
    + (" (shown)." if report.include_small_n else " (hidden).")
    + " Per-trade dollar-ticks are qty-scaled."
)

st.subheader(_Q_TITLES[0][0])
st.caption(report.captions["q1"])
_show_table(report.q1_days, empty="No instrument-day rows.")

st.subheader(_Q_TITLES[1][0])
st.caption(report.captions["q2"])
_show_table(report.q2_slices, empty="No Q2 slices at the current n gate.")

st.subheader(_Q_TITLES[2][0])
st.caption(report.captions["q3"])
if not present.get("attribution"):
    st.caption("Q3 omitted — attribution artifact not present.")
else:
    _show_table(report.q3_context, empty="No level_context rows.")
    _show_table(report.q3_levels, empty="No nearest-level rows.")
    _show_table(report.q3_tags, empty="No tag-alignment rows.")

st.subheader(_Q_TITLES[3][0])
st.caption(report.captions["q4"])
if not present.get("counterfactual"):
    st.caption("Q4 omitted — counterfactual artifact not present.")
else:
    _show_table(report.q4_brackets, empty="No bracket rows.")

st.subheader(_Q_TITLES[4][0])
st.caption(report.captions["q5"])
if not present.get("counterfactual"):
    st.caption("Q5 omitted — counterfactual artifact not present.")
else:
    null = report.q5_null
    st.write(
        {
            "n": null.get("n"),
            "direction_null_pct": null.get("direction_null_pct"),
            "seed": null.get("seed"),
            "k": null.get("k"),
            "resolution": null.get("resolution"),
            "recon_status": null.get("recon_status"),
        }
    )

st.subheader(_Q_TITLES[5][0])
st.caption(report.captions["q6"])
if not present.get("counterfactual"):
    st.caption("Q6 omitted — counterfactual artifact not present.")
else:
    _show_table(report.q6_rules, empty="No declared-rule rows.")

st.subheader(_Q_TITLES[6][0])
st.caption(report.captions["q7"])
if not present.get("match"):
    st.caption("Q7 omitted — match artifact not present.")
else:
    _show_table(report.q7_matches, empty="No match-class rows.")

st.subheader(_Q_TITLES[7][0])
st.caption(report.captions["q8"])
if not present.get("match"):
    st.caption("Q8 omitted — match artifact not present.")
else:
    _show_table(report.q8_ledger, empty="No forward-ledger rows.")
