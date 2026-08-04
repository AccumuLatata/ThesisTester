"""Research bundle export/import page."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.classic_context import (
    render_classic_thesis_chrome,
    set_classic_flash,
    sync_classic_context_for_dataset,
)
from thesistester.classic_nav import render_discuss_this_run
from thesistester.classic_record import render_record_and_discuss
from thesistester.research_bundle import (
    apply_research_bundle_to_session,
    build_research_bundle,
    load_research_bundle,
)

st.title("🧳 Research Bundles")
st.caption("Export and import portable research state snapshots for this session.")
bootstrap_active_saved_dataset()
render_classic_thesis_chrome(
    page_key="research_bundles",
    dataset_id=st.session_state.get("dataset_id"),
)


def _is_dataframe(value: object) -> bool:
    return isinstance(value, pd.DataFrame)


def _will_include_dataset() -> bool:
    return _is_dataframe(st.session_state.get("data"))


def _will_include_subtimeframe() -> bool:
    return _is_dataframe(st.session_state.get("subtimeframe_data"))


def _will_include_levels() -> bool:
    return _is_dataframe(st.session_state.get("levels")) and _is_dataframe(
        st.session_state.get("session_levels")
    )


def _will_include_signals() -> bool:
    return (
        _is_dataframe(st.session_state.get("signals"))
        and _is_dataframe(st.session_state.get("confluence_zones"))
        and _is_dataframe(st.session_state.get("naked_flags"))
    )


def _will_include_backtest() -> bool:
    return _is_dataframe(st.session_state.get("trades")) and _is_dataframe(
        st.session_state.get("equity_curve")
    )


def _will_include_grid() -> bool:
    return _is_dataframe(st.session_state.get("grid_results"))


def _will_include_validation() -> bool:
    return st.session_state.get("validation_summary") is not None


def _will_include_excursion() -> bool:
    return st.session_state.get("excursion_summary") is not None


def _will_include_monte_carlo() -> bool:
    return st.session_state.get("monte_carlo_summary") is not None


def _will_include_noise() -> bool:
    return st.session_state.get("noise_summary") is not None


def _will_include_overfitting() -> bool:
    return st.session_state.get("overfitting_summary") is not None


def _will_include_sensitivity() -> bool:
    return st.session_state.get("sensitivity_summary") is not None


def _will_include_portfolio() -> bool:
    return st.session_state.get("portfolio_summary") is not None


section_rows = [
    {"Artifact": "Dataset", "Will include": "✅" if _will_include_dataset() else "❌"},
    {
        "Artifact": "Lower-timeframe fill data",
        "Will include": "✅" if _will_include_subtimeframe() else "❌",
    },
    {"Artifact": "Levels", "Will include": "✅" if _will_include_levels() else "❌"},
    {"Artifact": "Signals", "Will include": "✅" if _will_include_signals() else "❌"},
    {"Artifact": "Backtest", "Will include": "✅" if _will_include_backtest() else "❌"},
    {"Artifact": "Grid search", "Will include": "✅" if _will_include_grid() else "❌"},
    {"Artifact": "Validation", "Will include": "✅" if _will_include_validation() else "❌"},
    {
        "Artifact": "Excursion analytics",
        "Will include": "✅" if _will_include_excursion() else "❌",
    },
    {"Artifact": "Monte Carlo", "Will include": "✅" if _will_include_monte_carlo() else "❌"},
    {"Artifact": "Noise test", "Will include": "✅" if _will_include_noise() else "❌"},
    {
        "Artifact": "Overfitting diagnostics",
        "Will include": "✅" if _will_include_overfitting() else "❌",
    },
    {
        "Artifact": "Parameter sensitivity",
        "Will include": "✅" if _will_include_sensitivity() else "❌",
    },
    {"Artifact": "Portfolio", "Will include": "✅" if _will_include_portfolio() else "❌"},
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

if _will_include_backtest():
    render_record_and_discuss(page_key="research_bundles")
# Discuss needs a thesis-recorded run, not live session trades/equity.
render_discuss_this_run(page_key="research_bundles")

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
            {
                "Artifact": "Dataset",
                "Included in bundle": "✅" if included.get("dataset") else "❌",
            },
            {
                "Artifact": "Lower-timeframe fill data",
                "Included in bundle": (
                    "✅"
                    if isinstance(
                        loaded_bundle.get("session_values", {}).get("subtimeframe_data"),
                        pd.DataFrame,
                    )
                    else "❌"
                ),
            },
            {"Artifact": "Levels", "Included in bundle": "✅" if included.get("levels") else "❌"},
            {
                "Artifact": "Signals",
                "Included in bundle": "✅" if included.get("signals") else "❌",
            },
            {
                "Artifact": "Backtest",
                "Included in bundle": "✅" if included.get("backtest") else "❌",
            },
            {
                "Artifact": "Grid search",
                "Included in bundle": "✅" if included.get("grid") else "❌",
            },
            {
                "Artifact": "Validation",
                "Included in bundle": "✅" if included.get("validation") else "❌",
            },
            {
                "Artifact": "Excursion analytics",
                "Included in bundle": "✅" if included.get("excursion") else "❌",
            },
            {
                "Artifact": "Monte Carlo",
                "Included in bundle": "✅" if included.get("monte_carlo") else "❌",
            },
            {
                "Artifact": "Noise test",
                "Included in bundle": "✅" if included.get("noise") else "❌",
            },
            {
                "Artifact": "Overfitting diagnostics",
                "Included in bundle": "✅" if included.get("overfitting") else "❌",
            },
            {
                "Artifact": "Parameter sensitivity",
                "Included in bundle": "✅" if included.get("sensitivity") else "❌",
            },
            {
                "Artifact": "Portfolio",
                "Included in bundle": "✅" if included.get("portfolio") else "❌",
            },
        ]

        st.caption("Bundle validated. Review contents before importing.")
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

        if st.button("Import bundle into session", type="primary"):
            try:
                result = apply_research_bundle_to_session(loaded_bundle, st.session_state)
            except ValueError as exc:
                st.error(str(exc))
            else:
                # Chrome already ran with the pre-import dataset_id; sync now so a
                # changed bundle dataset cannot leave research mode bound to the old id.
                imported_dataset_id = st.session_state.get("dataset_id")
                sync_classic_context_for_dataset(
                    st.session_state,
                    imported_dataset_id if isinstance(imported_dataset_id, str) else None,
                )
                set_classic_flash(
                    st.session_state,
                    level="success",
                    message=(
                        f"Imported {result.get('restored_count', 0)} session keys from "
                        "bundle. Classic research context was re-checked against the "
                        "imported dataset. Navigate to Data, Levels, Setup Builder, "
                        "Signals, Backtest, Grid Search, Time Analysis, Validation, "
                        "Report / Export, or Portfolio pages to continue."
                    ),
                )
                st.rerun()
