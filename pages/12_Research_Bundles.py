"""Research bundle export/import page."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    load_research_bundle,
)

st.title("🧳 Research Bundles")
st.caption("Export and import portable research state snapshots for this session.")
bootstrap_active_saved_dataset()


def _is_dataframe(value: object) -> bool:
    return isinstance(value, pd.DataFrame)


def _will_include_dataset() -> bool:
    return _is_dataframe(st.session_state.get("data"))


def _will_include_levels() -> bool:
    return _is_dataframe(st.session_state.get("levels")) and _is_dataframe(st.session_state.get("session_levels"))


def _will_include_signals() -> bool:
    return (
        _is_dataframe(st.session_state.get("signals"))
        and _is_dataframe(st.session_state.get("confluence_zones"))
        and _is_dataframe(st.session_state.get("naked_flags"))
    )


def _will_include_backtest() -> bool:
    return _is_dataframe(st.session_state.get("trades")) and _is_dataframe(st.session_state.get("equity_curve"))


def _will_include_grid() -> bool:
    return _is_dataframe(st.session_state.get("grid_results"))


def _will_include_validation() -> bool:
    return st.session_state.get("validation_summary") is not None


section_rows = [
    {"Artifact": "Dataset", "Will include": "✅" if _will_include_dataset() else "❌"},
    {"Artifact": "Levels", "Will include": "✅" if _will_include_levels() else "❌"},
    {"Artifact": "Signals", "Will include": "✅" if _will_include_signals() else "❌"},
    {"Artifact": "Backtest", "Will include": "✅" if _will_include_backtest() else "❌"},
    {"Artifact": "Grid search", "Will include": "✅" if _will_include_grid() else "❌"},
    {"Artifact": "Validation", "Will include": "✅" if _will_include_validation() else "❌"},
]
has_meaningful_state = any(row["Will include"] == "✅" for row in section_rows)

st.subheader("Export preview")
st.dataframe(pd.DataFrame(section_rows), width="stretch", hide_index=True)

if not has_meaningful_state:
    st.warning("No meaningful research state found to export yet.")
else:
    bundle_bytes = build_research_bundle(st.session_state)
    file_name = f"thesistester_bundle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    st.download_button(
        "Download research bundle",
        data=bundle_bytes,
        file_name=file_name,
        mime="application/zip",
    )

st.divider()
st.subheader("Import bundle")

uploaded = st.file_uploader("Upload research bundle", type=["zip"])
if uploaded is not None:
    try:
        loaded_bundle = load_research_bundle(uploaded)
    except ValueError as exc:
        st.error(str(exc))
    else:
        manifest = loaded_bundle.get("manifest", {})
        included = manifest.get("included", {}) if isinstance(manifest, dict) else {}
        preview_rows = [
            {"Artifact": "Dataset", "Included in bundle": "✅" if included.get("dataset") else "❌"},
            {"Artifact": "Levels", "Included in bundle": "✅" if included.get("levels") else "❌"},
            {"Artifact": "Signals", "Included in bundle": "✅" if included.get("signals") else "❌"},
            {"Artifact": "Backtest", "Included in bundle": "✅" if included.get("backtest") else "❌"},
            {"Artifact": "Grid search", "Included in bundle": "✅" if included.get("grid") else "❌"},
            {"Artifact": "Validation", "Included in bundle": "✅" if included.get("validation") else "❌"},
        ]

        st.caption("Bundle validated. Review contents before importing.")
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

        if st.button("Import bundle into session", type="primary"):
            try:
                result = apply_research_bundle_to_session(loaded_bundle, st.session_state)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success(f"Imported {result.get('restored_count', 0)} session keys from bundle.")
                st.info(
                    "Import complete. Navigate to Data, Levels, Signals, Backtest, Time Analysis, "
                    "or Report / Export pages to continue."
                )
