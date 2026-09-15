"""Phase 8 — Statistical Validation and Robustness Diagnostics.

Analyses completed trades from Phase 5 using bootstrap confidence intervals,
sign-flip permutation tests, trade-count diagnostics, and grid-search overfit
warnings.  No trade re-simulation is performed.

⚠️  All outputs are diagnostic only — not proof of edge.

QR D-4 / QI-05-02: sidebar, WFA/OTF persist, batteries, Phase 8 display, and
OTF matrix live in ``*_page_helpers``. Session keys and H12/H13/M9/M10 copy
are unchanged. Prelude (Admit inherit + Focus/H12) stays on this page.
"""

from __future__ import annotations

import streamlit as st

from thesistester.analytics.entry_window import (
    FOCUS_HONESTY_BANNER,
    FOCUS_STATUS_BADGE,
    pick_inherited_entry_window_source,
    resolve_inherited_entry_window,
)
from thesistester.analytics.validation import validation_summary
from thesistester.config import INSTRUMENTS
from thesistester.validation_batteries_page_helpers import render_validation_batteries
from thesistester.validation_display_page_helpers import render_phase8_results
from thesistester.validation_otf_page_helpers import render_otf_validation_matrix
from thesistester.validation_sidebar_page_helpers import render_validation_sidebar
from thesistester.validation_wfa_page_helpers import render_wfa_otf_diagnostics

st.title("📊 Statistical Validation")
st.caption(
    "Diagnostic only — not proof of edge. Covers bootstrap/permutation, walk-forward, "
    "optional overfitting/noise/sensitivity batteries, excursion/Monte Carlo analytics, "
    "and the OTF validation matrix."
)

# ── Require trades ────────────────────────────────────────────────────────────
trades_raw = st.session_state.get("trades")
if trades_raw is None or trades_raw.empty:
    st.warning("No trades found. Please run a backtest first.")
    st.stop()

backtest_exposure_policy = (st.session_state.get("exposure_policy") or {}).get("exposure_policy")
if backtest_exposure_policy == "allow_all":
    st.warning(
        "Exposure policy is `allow_all`: overlapping trades may inflate trade count "
        "and understate uncertainty. For validation-grade results, consider "
        "`single_position` or another restrictive policy."
    )

_validation_instrument = st.session_state.get("instrument", "ES")
_validation_inst = INSTRUMENTS.get(_validation_instrument)
# C5: RTH / naive basis matches API noise→run_backtest (instrument exchange TZ).
_validation_exchange_tz = (
    (_validation_inst.exchange_tz if _validation_inst else None)
    or st.session_state.get("exchange_timezone")
    or "America/New_York"
)
_session_entry_window = st.session_state.get("entry_window")
_inherited_source = pick_inherited_entry_window_source(
    _session_entry_window,
    st.session_state.get("grid_entry_window"),
)
# Armed caption only when the pending Promote window is the inherited source.
_inherited_armed = (
    bool(st.session_state.get("entry_window_armed"))
    and isinstance(_session_entry_window, dict)
    and bool(_session_entry_window.get("enabled"))
    and _inherited_source is _session_entry_window
)
_validation_ew = resolve_inherited_entry_window(
    _inherited_source,
    exchange_tz=_validation_exchange_tz,
    armed=_inherited_armed,
)
if _validation_ew["enabled"]:
    st.warning(_validation_ew["warning"])
    st.caption(
        f"Inherited Admit window for WFA / overfitting / sensitivity: "
        f"**{_validation_ew['label']}**"
        + (" · armed (pending Backtest re-sim)" if _validation_ew["armed"] else "")
    )
else:
    st.caption("No Admit `entry_window` inherited — validation batteries use all-day admission.")

_focus_window = st.session_state.get("focus_entry_window") or {}
_focus_prov = st.session_state.get("focus_provenance") or {}
_focus_summary = st.session_state.get("focused_trade_summary")
# Same session predicate as Time Analysis / Backtest — enabled window alone is leftover-prone.
_has_focus = bool(
    isinstance(_focus_summary, dict)
    and isinstance(_focus_window, dict)
    and _focus_window.get("enabled")
)
if _has_focus:
    st.caption(f"**{FOCUS_STATUS_BADGE}**")
    st.warning(FOCUS_HONESTY_BANNER)
    # QI-05-04 / A-3: consumer-only H12 sentence. Do not edit FOCUS_HONESTY_BANNER.
    st.caption(
        "Under `single_position`, Focus fills may differ from an Admit re-sim "
        "(occupancy can substitute which `signal_id` fills). Focus N is not an Admit N "
        "(counts may match while fill sets differ)."
    )
    if isinstance(_focus_prov, dict) and _focus_prov:
        st.caption(
            f"Focus provenance in session: "
            f"{_focus_prov.get('trade_count_after', 0)} / "
            f"{_focus_prov.get('trade_count_before', 0)} trades "
            "(post-hoc subset — not Validation battery input)."
        )

# ── Optional grid results ─────────────────────────────────────────────────────
grid_raw = st.session_state.get("grid_results")

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    settings = render_validation_sidebar(st, grid_raw=grid_raw)

n_bootstrap = settings["n_bootstrap"]
n_permutations = settings["n_permutations"]
confidence = settings["confidence"]
random_seed = settings["random_seed"]
min_trades_soft = settings["min_trades_soft"]
min_trades_hard = settings["min_trades_hard"]
grid_metric = settings["grid_metric"]

# ── Run validation ────────────────────────────────────────────────────────────
if st.button("▶ Run Validation", type="primary"):
    with st.spinner("Running validation diagnostics…"):
        summary = validation_summary(
            trades_raw,
            grid=grid_raw,
            n_bootstrap=n_bootstrap,
            n_permutations=n_permutations,
            confidence=confidence,
            random_state=random_seed,
            min_trades_soft=min_trades_soft,
            min_trades_hard=min_trades_hard,
            selected_grid_metric=grid_metric,
        )
    st.session_state["validation_summary"] = summary
    st.success("Validation complete.")

render_wfa_otf_diagnostics(st, validation_ew=_validation_ew)
render_validation_batteries(
    st,
    trades_raw=trades_raw,
    grid_raw=grid_raw,
    validation_ew=_validation_ew,
    random_seed=random_seed,
)

# ── Display results if available ──────────────────────────────────────────────
summary = st.session_state.get("validation_summary")
if summary is None:
    st.info("Configure settings in the sidebar and click **Run Validation**.")
    st.stop()

render_phase8_results(
    st,
    summary=summary,
    grid_raw=grid_raw,
    confidence=confidence,
)
st.divider()
render_otf_validation_matrix(st)
