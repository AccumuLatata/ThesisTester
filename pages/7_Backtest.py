"""Phase 5 — Backtest page.

Converts Phase 4 candidate signals into simulated trades using a single
fixed SL/TP configuration and displays KPIs, equity curve, and trade table.

QR D-3 / QI-04-05: sidebar, run/persist, and display live in
``*_page_helpers``. Session keys and H7/H15 call-site Names are unchanged.
"""

from __future__ import annotations

import streamlit as st

from thesistester.app_state import bootstrap_active_saved_dataset
from thesistester.backtest_display_page_helpers import render_backtest_results
from thesistester.backtest_page_helpers import signal_setup_context
from thesistester.backtest_run_page_helpers import run_and_persist_backtest
from thesistester.backtest_sidebar_page_helpers import render_backtest_sidebar
from thesistester.classic_context import render_classic_thesis_chrome
from thesistester.classic_ledger import render_classic_execution_ledger
from thesistester.classic_nav import (
    render_classic_nav_prefill_caption,
    render_discuss_this_run,
)
from thesistester.classic_proposal import render_classic_proposal_card
from thesistester.classic_record import render_record_and_discuss
from thesistester.config import INSTRUMENTS
from thesistester.execution_defaults import apply_backtest_defaults
from thesistester.persistence import get_backtest_defaults
from thesistester.timezone_display import ensure_display_timezone

st.title("📊 Backtest")
st.caption("Diagnostic only — not proof of edge.")
bootstrap_active_saved_dataset()
render_classic_thesis_chrome(
    page_key="backtest",
    dataset_id=st.session_state.get("dataset_id"),
)
# Prefill / proposal / Discuss must render before any st.stop() guard so empty
# Backtest pages still surface Assistant navigation and thesis-run discussion.
render_classic_nav_prefill_caption(target_page="pages/7_Backtest.py")
render_classic_proposal_card(target_page="pages/7_Backtest.py")
render_discuss_this_run(page_key="backtest")

# ── Require signals ───────────────────────────────────────────────────────────
if "signals" not in st.session_state:
    st.warning(
        "No signals found. Please load data on the **Data** page, compute "
        "levels on the **Levels** page, and generate signals on the **Signals** page first."
    )
    st.stop()

signals = st.session_state["signals"]
signal_context = st.session_state.get("signal_context")
if signals is None or signals.empty:
    st.warning("Signal table is empty. Please generate signals on the **Signals** page first.")
    st.stop()

# ── Prefer levels df for full timeline; fall back to data ─────────────────────
if "levels" in st.session_state:
    ohlcv_df = st.session_state["levels"]
elif "data" in st.session_state:
    ohlcv_df = st.session_state["data"]
else:
    st.error("No OHLCV data available. Please load data on the **Data** page.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
inst = INSTRUMENTS.get(instrument)
tick_size = inst.tick_size if inst else 0.25
point_value = inst.point_value if inst else 50.0
exchange_tz = st.session_state.get("exchange_timezone") or (
    inst.exchange_tz if inst else "America/New_York"
)
ensure_display_timezone(st.session_state, exchange_timezone=exchange_tz)

setup_context_caption = signal_setup_context(signals, signal_context)
if setup_context_caption:
    st.caption(setup_context_caption)

# ── Load saved execution defaults (once per session) ──────────────────────────
if "_backtest_defaults_applied" not in st.session_state:
    _saved = get_backtest_defaults()
    if _saved:
        apply_backtest_defaults(st.session_state, _saved)
    st.session_state["_backtest_defaults_applied"] = True

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    settings = render_backtest_sidebar(
        st,
        instrument=instrument,
        tick_size=tick_size,
        point_value=point_value,
        exchange_tz=exchange_tz,
    )

# ── Run ───────────────────────────────────────────────────────────────────────
if settings["run_btn"]:
    run_and_persist_backtest(
        st,
        settings=settings,
        ohlcv_df=ohlcv_df,
        signals=signals,
        exchange_tz=exchange_tz,
        inst=inst,
        tick_size=tick_size,
        point_value=point_value,
    )

# ── Display ───────────────────────────────────────────────────────────────────
trades = st.session_state.get("trades")
summary = st.session_state.get("trade_summary")
curve = st.session_state.get("equity_curve")
skipped_signals = st.session_state.get("skipped_signals")

if trades is None:
    st.info("Configure settings in the sidebar and click **▶ Run backtest**.")
    st.stop()

render_record_and_discuss(page_key="backtest")
render_classic_execution_ledger(page_key="backtest")
render_backtest_results(
    st,
    signals=signals,
    trades=trades,
    summary=summary,
    curve=curve,
    skipped_signals=skipped_signals,
    ohlcv_df=ohlcv_df,
    instrument=str(instrument),
)
