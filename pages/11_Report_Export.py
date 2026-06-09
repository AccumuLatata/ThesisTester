"""Phase 9 — Research report and export page."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from thesistester.config import TIMEZONE_OPTIONS
from thesistester.reporting import (
    build_markdown_report,
    build_research_artifact,
    dataframe_to_csv_bytes,
)
from thesistester.timezone_display import (
    convert_dataframe_timestamps_for_display,
    ensure_display_timezone,
    timezone_contract_caption,
)

st.title("🧾 Report / Export")
st.caption("Export reproducible research artifacts from current session state.")
exchange_tz = st.session_state.get("exchange_timezone") or "America/New_York"
ensure_display_timezone(st.session_state, exchange_timezone=exchange_tz)
st.selectbox(
    "Display/export timezone",
    options=TIMEZONE_OPTIONS,
    key="display_timezone",
    help="Controls timezone conversion for exported CSV/JSON timestamps.",
)
st.caption(timezone_contract_caption(st.session_state))
display_tz = st.session_state.get("display_timezone", exchange_tz)


REQUIRED_ITEMS = [
    ("Setup config", "setup_config"),
    ("Signals", "signals"),
    ("Trades", "trades"),
    ("Grid results", "grid_results"),
    ("Time analysis", "time_grouped_summary"),
    ("Validation", "validation_summary"),
]


def _has_value(key: str) -> bool:
    value = st.session_state.get(key)
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _fmt(v: Any, fmt: str = ".2f", fallback: str = "—") -> str:
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return fallback


artifact = build_research_artifact(st.session_state)

backtest_costs = st.session_state.get("backtest_execution_costs") or {}
grid_costs = st.session_state.get("grid_execution_costs") or {}
report_costs = (
    backtest_costs
    if backtest_costs
    else grid_costs
)
if report_costs:
    artifact["execution_cost_assumptions"] = {
        "commission_per_side": float(report_costs.get("commission_per_side", 0.0)),
        "slippage_ticks": float(report_costs.get("slippage_ticks", 0.0)),
        "metrics_basis": (
            "net-of-cost"
            if (
                float(report_costs.get("commission_per_side", 0.0)) > 0.0
                or float(report_costs.get("slippage_ticks", 0.0)) > 0.0
            )
            else "gross==net (zero costs)"
        ),
    }

report_markdown = build_markdown_report(artifact)
if report_costs:
    report_markdown += (
        "\n## Execution Cost Assumptions\n"
        f"- Commission per side: {float(report_costs.get('commission_per_side', 0.0)):.4f}\n"
        f"- Slippage ticks (per side): {float(report_costs.get('slippage_ticks', 0.0)):.4f}\n"
        f"- Metrics basis: {artifact['execution_cost_assumptions']['metrics_basis']}\n"
    )

status_rows = [
    {"Item": item, "Session state key": key, "Available": "✅" if _has_value(key) else "❌"}
    for item, key in REQUIRED_ITEMS
]
st.subheader("Run completeness checklist")
st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True)

if not _has_value("setup_config"):
    st.warning("No setup config found. Export will include empty configuration fields.")
if not _has_value("signals"):
    st.warning("No signals found. Signal exports will be empty.")
if not _has_value("trades"):
    st.warning("No trades found. Backtest exports will be empty.")
if not _has_value("validation_summary"):
    st.warning("No validation summary found. Validation section will be incomplete.")

results = artifact.get("results", {})
trade_summary = results.get("trade_summary") or {}
validation_summary = results.get("validation_summary") or {}
trade_count_diag = validation_summary.get("trade_count") if isinstance(validation_summary, dict) else {}

st.subheader("Summary")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Signals", results.get("signal_count", 0))
col2.metric("Trades", results.get("trade_count", 0))
col3.metric(
    "Win rate",
    _fmt(trade_summary.get("win_rate"), ".1%") if trade_summary.get("win_rate") is not None else "—",
)
col4.metric("Avg R", _fmt(trade_summary.get("avg_r")))
col5.metric("Total R", _fmt(trade_summary.get("total_r")))
col6.metric("Validation", (trade_count_diag or {}).get("status", "—"))

if report_costs:
    st.caption(
        "Execution cost assumptions included in exports: "
        f"commission/side={float(report_costs.get('commission_per_side', 0.0)):.4f}, "
        f"slippage_ticks={float(report_costs.get('slippage_ticks', 0.0)):.4f}, "
        f"metrics={artifact.get('execution_cost_assumptions', {}).get('metrics_basis', '—')}."
    )

st.subheader("Downloads")
json_text = json.dumps(artifact, indent=2)
st.download_button(
    "⬇️ Download JSON artifact",
    data=json_text,
    file_name="research_artifact.json",
    mime="application/json",
)

st.download_button(
    "⬇️ Download Markdown report",
    data=report_markdown,
    file_name="research_report.md",
    mime="text/markdown",
)

csv_exports = [
    ("signals", "signals.csv"),
    ("trades", "trades.csv"),
    ("equity_curve", "equity_curve.csv"),
    ("grid_results", "grid_results.csv"),
    ("time_grouped_summary", "time_grouped_summary.csv"),
]

for key, filename in csv_exports:
    value = st.session_state.get(key)
    if isinstance(value, pd.DataFrame):
        converted_df, conversion_warnings = convert_dataframe_timestamps_for_display(
            value,
            display_timezone=display_tz,
            canonical_timezone=exchange_tz,
        )
        st.download_button(
            f"⬇️ Download {filename}",
            data=dataframe_to_csv_bytes(converted_df),
            file_name=filename,
            mime="text/csv",
            key=f"download_{key}",
        )
        for warning in conversion_warnings:
            st.warning(warning)

st.subheader("Report preview")
st.markdown(report_markdown)

with st.expander("JSON artifact preview"):
    st.json(artifact)

st.subheader("Inspect previous artifact (optional)")
uploaded = st.file_uploader("Upload research_artifact.json", type=["json"])
if uploaded is not None:
    try:
        uploaded_artifact = json.loads(uploaded.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        st.error("Invalid JSON file.")
    else:
        st.success("Artifact loaded (read-only preview).")
        up_meta = uploaded_artifact.get("metadata", {}) if isinstance(uploaded_artifact, dict) else {}
        up_results = uploaded_artifact.get("results", {}) if isinstance(uploaded_artifact, dict) else {}
        up_summary = up_results.get("trade_summary") if isinstance(up_results, dict) else {}

        st.write(f"Generated at: {up_meta.get('generated_at', '—')}")
        st.write(f"Signal count: {up_results.get('signal_count', '—')}")
        st.write(f"Trade count: {up_results.get('trade_count', '—')}")
        if isinstance(up_summary, dict):
            st.write(f"Avg R: {_fmt(up_summary.get('avg_r'))}")
            st.write(f"Total R: {_fmt(up_summary.get('total_r'))}")
