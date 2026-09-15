"""Data-page summary / roll / 15s diagnostic display (QR D-5 / QI-01-01).

Streamlit-free: callers pass ``st``.
"""

from __future__ import annotations

import pandas as pd

from thesistester.config import INSTRUMENTS
from thesistester.data.loader import (
    duplicate_timestamp_report,
    primary_duplicate_volume_comparison,
)
from thesistester.data.rolls import (
    ROLL_METHODS,
    detect_contract_column,
    validate_roll_metadata,
)
from thesistester.timezone_display import timezone_contract_caption
from thesistester.data_page_constants import SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY


def render_derived_parent_diagnostics(
    st,
    dropped_buckets: pd.DataFrame,
    sparse_buckets: pd.DataFrame | None = None,
) -> None:
    """Show sparse/dropped minute diagnostics for 15-second-primary uploads."""
    dropped_count = 0 if dropped_buckets is None else int(len(dropped_buckets))
    sparse_count = 0 if sparse_buckets is None else int(len(sparse_buckets))
    if sparse_count == 0 and dropped_count == 0:
        st.info(
            "All source minutes had complete aligned 15-second coverage; "
            "no sparse or misaligned parent minutes were reported."
        )
        return
    if sparse_count > 0:
        st.info(
            f"Retained {sparse_count:,} sparse source minute(s) with fewer than four "
            "on-grid 15-second prints (normal for Quantower/Rithmic trade-only exports "
            "without Build empty bars). Those minutes remain in canonical one-minute "
            "data; use R12 model `subtimeframe_conservative` for observed replay plus "
            "SL-first fallback on sparse minutes. Strict `subtimeframe` requires complete "
            "coverage (enable Build empty bars in Quantower if you need that)."
        )
        st.dataframe(sparse_buckets, width="stretch")
        st.download_button(
            "Download sparse-minute diagnostics CSV",
            data=sparse_buckets.to_csv(index=False).encode("utf-8"),
            file_name="derived_1m_sparse_minutes.csv",
            mime="text/csv",
            key="download_sparse_minute_diagnostics",
        )
    if dropped_count > 0:
        st.warning(
            f"Dropped {dropped_count:,} misaligned source minute(s). "
            "Those minutes are absent from the derived one-minute canonical data."
        )
        st.dataframe(dropped_buckets, width="stretch")
        st.download_button(
            "Download dropped-minute diagnostics CSV",
            data=dropped_buckets.to_csv(index=False).encode("utf-8"),
            file_name="derived_1m_dropped_minutes.csv",
            mime="text/csv",
            key="download_dropped_minute_diagnostics",
        )


def render_15s_source_duplicate_caption(st, provenance) -> None:
    """Show resolved 15s source-duplicate audit when provenance recorded one."""
    if not isinstance(provenance, dict):
        return
    groups = provenance.get("source_duplicate_groups_resolved")
    if not groups:
        return
    discarded = int(provenance.get("source_duplicate_rows_discarded") or 0)
    st.caption(
        f"Resolved {int(groups):,} OHLC-identical 15-second duplicate group(s) "
        f"({discarded:,} extra row(s) dropped; lowest volume kept). "
        "Native one-minute primary bars are never auto-deduplicated."
    )


def render_dataset_summary(
    st,
    df,
    *,
    instrument: str,
    base_interval: str | None,
    source_timezone: str | None,
    exchange_timezone: str | None,
    report=None,
    resampled_data: dict | None = None,
    saved_dataset_loaded: bool = False,
):
    st.success(f"Loaded {len(df):,} bars.")
    st.caption(f"{df['timestamp'].min()} → {df['timestamp'].max()}")
    st.caption(timezone_contract_caption(st.session_state))

    summary_cols = st.columns(4)
    summary_cols[0].metric("Rows", f"{len(df):,}")
    summary_cols[1].metric("Inferred base interval", base_interval or "unknown")
    summary_cols[2].metric("RTH bars", int((df["session"] == "RTH").sum()))
    summary_cols[3].metric("ETH bars", int((df["session"] == "ETH").sum()))

    if report is not None:
        detail_cols = st.columns(2)
        detail_cols[0].metric("Validation issues", len(report.issues))
        detail_cols[1].metric("Instrument", instrument)
        if report.is_clean:
            st.info("Validation passed ✓")
        else:
            st.warning("Validation issues detected:")
            for issue in report.messages():
                st.write(f"- {issue}")
            primary_duplicate_report = _primary_duplicate_report(df, report)
            if primary_duplicate_report is not None:
                group_count = int(primary_duplicate_report["timestamp"].nunique())
                st.warning(
                    f"Primary duplicate report: {group_count:,} duplicate timestamp groups. "
                    "Primary bars are never deduplicated automatically because their "
                    "volume can affect VWAP and profile calculations."
                )
                st.dataframe(primary_duplicate_report, width="stretch")
                st.download_button(
                    "Download primary duplicate report CSV",
                    data=primary_duplicate_report.to_csv(index=False).encode("utf-8"),
                    file_name="primary_duplicate_report.csv",
                    mime="text/csv",
                )
                lower_data = st.session_state.get("subtimeframe_data")
                diagnostic_only = False
                if not isinstance(lower_data, pd.DataFrame):
                    lower_data = st.session_state.get(SUBTIMEFRAME_DIAGNOSTIC_DATA_KEY)
                    diagnostic_only = isinstance(lower_data, pd.DataFrame)
                if isinstance(lower_data, pd.DataFrame):
                    volume_comparison = primary_duplicate_volume_comparison(df, lower_data)
                    matched_count = int(
                        volume_comparison["comparison_status"].eq("matched_one").sum()
                    )
                    st.info(
                        f"Primary/lower volume comparison: {matched_count:,} of "
                        f"{len(volume_comparison):,} duplicate groups have exactly one "
                        "primary volume matching the lower-bar aggregate. This is "
                        "diagnostic only; primary data remains unchanged."
                    )
                    if diagnostic_only:
                        st.caption(
                            "Lower data is retained for this comparison only and is not active "
                            "for lower-timeframe execution."
                        )
                    st.dataframe(volume_comparison, width="stretch")
                    st.download_button(
                        "Download primary/lower volume comparison CSV",
                        data=volume_comparison.to_csv(index=False).encode("utf-8"),
                        file_name="primary_lower_volume_comparison.csv",
                        mime="text/csv",
                    )
    elif saved_dataset_loaded:
        st.info("Loaded canonical dataset from local store.")
    else:
        st.info("Using dataset from current session.")

    for timeframe, out in (resampled_data or {}).items():
        with st.expander(f"{timeframe} preview ({len(out):,} rows)"):
            st.dataframe(out.head(50), width="stretch")

    st.subheader("Base timeframe preview")
    st.dataframe(df.head(50), width="stretch")


def _primary_duplicate_report(df: pd.DataFrame, report) -> pd.DataFrame | None:
    """Return a duplicate diagnostic only when primary validation found duplicates."""
    if report is None or not any(issue.code == "duplicate_timestamps" for issue in report.issues):
        return None
    return duplicate_timestamp_report(df)


def render_roll_assumptions(st, df, *, instrument: str) -> None:
    st.subheader("Futures roll assumptions")
    existing_policy = st.session_state.get("roll_policy")
    if not isinstance(existing_policy, dict):
        existing_policy = {}

    detected_contract_column = detect_contract_column(df)
    roll_method_options = [
        "single_contract",
        "external_continuous",
        "segmented_contracts",
    ]
    default_roll_method = existing_policy.get("roll_method", "single_contract")
    if default_roll_method not in ROLL_METHODS:
        default_roll_method = "single_contract"
    roll_method = st.selectbox(
        "Roll method",
        options=roll_method_options,
        index=roll_method_options.index(default_roll_method),
        key="roll_method_selector",
    )

    contract_column = (
        st.text_input(
            "Contract column",
            value=(
                existing_policy.get("contract_column") or detected_contract_column or "contract"
            ),
            key="roll_contract_column_input",
        ).strip()
        or "contract"
    )

    adjustment_options = [
        "unknown",
        "back_adjusted",
        "ratio_adjusted",
        "panama",
        "none",
    ]
    roll_rule_options = [
        "unknown",
        "volume",
        "open_interest",
        "calendar",
        "first_notice",
        "last_trade",
    ]

    default_adjustment = existing_policy.get("adjustment_method", "unknown")
    if default_adjustment not in adjustment_options:
        default_adjustment = "unknown"
    default_roll_rule = existing_policy.get("roll_rule", "unknown")
    if default_roll_rule not in roll_rule_options:
        default_roll_rule = "unknown"

    if roll_method == "external_continuous":
        adjustment_method = st.selectbox(
            "Adjustment method",
            options=adjustment_options,
            index=adjustment_options.index(default_adjustment),
            key="roll_adjustment_method_selector",
        )
        roll_rule = st.selectbox(
            "Roll rule",
            options=roll_rule_options,
            index=roll_rule_options.index(default_roll_rule),
            key="roll_rule_selector",
        )
    else:
        adjustment_method = "unknown"
        roll_rule = "unknown"

    st.session_state["roll_policy"] = {
        "roll_method": roll_method,
        "contract_column": contract_column,
        "adjustment_method": adjustment_method,
        "roll_rule": roll_rule,
    }

    tick_size = INSTRUMENTS[instrument].tick_size if instrument in INSTRUMENTS else None
    if st.button("Validate roll metadata"):
        st.session_state["roll_validation"] = validate_roll_metadata(
            df,
            roll_method=roll_method,
            contract_column=contract_column,
            adjustment_method=adjustment_method,
            roll_rule=roll_rule,
            tick_size=tick_size,
        )

    validation = st.session_state.get("roll_validation")
    if not isinstance(validation, dict):
        return

    st.metric("Roll metadata valid", "✅" if validation.get("valid") else "❌")
    st.write(f"Contract count: {validation.get('contract_count', '—')}")
    warnings = validation.get("warnings")
    if isinstance(warnings, list) and warnings:
        st.warning("Warnings:")
        for warning in warnings:
            st.write(f"- {warning}")
    roll_gaps = validation.get("roll_gaps")
    if isinstance(roll_gaps, list) and roll_gaps:
        st.dataframe(pd.DataFrame(roll_gaps), width="stretch")
