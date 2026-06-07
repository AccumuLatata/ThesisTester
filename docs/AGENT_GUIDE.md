# AGENT GUIDE

## Purpose
Regression-safe onboarding guide for contributors/agents working in ThesisTester.

## Fast start
1. Install deps: `pip install -r requirements.txt` (`README.md:7-10`).
2. Run tests: `pytest -q` (`README.md:12-16`).
3. Optional app run: `streamlit run app.py` (`README.md:7-10`).

## Repository conventions (verified)
- Multipage Streamlit workflow with phase pages under `pages/` (`app.py:10-33`).
- Core outputs are passed through `st.session_state` between phases (see `docs/ARCHITECTURE.md`).
- Validation and reporting are explicitly diagnostic/research-only, not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`, `thesistester/reporting.py:13-19`).
- Backtest intrabar ambiguity uses SL-first pessimistic behavior (`thesistester/engine/backtest.py:12-14`, `221-226`).

## Regression-safe rules
- Prefer minimal, surgical changes.
- Preserve phase-to-phase `st.session_state` contracts.
- Do not change assumptions silently; if changed, update docs and references in the same PR.
- Re-run `pytest -q` after edits and report results.
- For docs-only tasks, keep edits to Markdown files and avoid `.py` changes.

## Where each phase lives
- **Phase 1 (Data):** `pages/1_Data.py`, data loaders/validators in `thesistester/data/`.
- **Phase 2/3 (Levels):** `pages/5_Levels.py`, level engines in `thesistester/levels.py`.
- **Phase 6.5 (Setup Builder):** `pages/2_Setup_Builder.py`, setup helpers in `thesistester/setup.py`.
- **Phase 4 (Signals):** `pages/6_Signals.py`, signal/confluence functions in `thesistester/engine/`.
- **Phase 5 (Backtest):** `pages/7_Backtest.py`, simulator in `thesistester/engine/backtest.py`, metrics in `thesistester/analytics/metrics.py`.
- **Phase 6 (Grid):** `pages/8_Grid_Search.py`, grid analytics in `thesistester/analytics/grid.py`.
- **Phase 7 (Time):** `pages/9_Time_Analysis.py`, helpers in `thesistester/analytics/time_analysis.py`.
- **Phase 8 (Validation):** `pages/10_Validation.py`, diagnostics in `thesistester/analytics/validation.py`.
- **Phase 9 (Report/Export):** `pages/11_Report_Export.py`, artifact builders in `thesistester/reporting.py`.
