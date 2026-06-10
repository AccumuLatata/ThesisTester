# Engineering Roadmap

This document tracks the ThesisTester engineering roadmap milestones in established
phase order.

---

## R1 — Execution Realism ✅ Implemented

Adds optional commission and slippage to `simulate_trades`. Defaults preserve legacy
gross behavior. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §1.

---

## R2 — Session-Aware Day-Trading Engine ✅ Implemented

Adds `flat_by_session_close` mode to `simulate_trades`. `SESSION_CLOSE` and `DATA_END`
exit types supported. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §3.

---

## R3 — Point-in-Time Audit and Fixes ✅ Implemented

R3 adds future-shock regression tests and documentation. Merge readiness still requires
the repository test suite to pass in CI/local verification.

- `docs/POINT_IN_TIME_GUARANTEES.md` created and specific to current code.
- Future-shock regression tests added in `tests/test_r3_point_in_time.py` (17 tests).
- `ASSUMPTIONS_AND_LIMITATIONS.md` updated with PIT scope and limitations.
- Audited paths showed no look-ahead bugs; deliverable is documentation plus regression
  coverage for audited behaviors.
- `confirm_3bar` is treated as legacy/internal in R3 documentation because it is not in
  the public `generate_signals()` trigger set.

See `docs/POINT_IN_TIME_GUARANTEES.md` for audit details, coverage notes, and limits.

---

## R4 — Exposure and Trade Lifecycle Model ✅ Implemented

Adds explicit overlap admission controls (`allow_all`, `single_position`,
`single_direction`, `single_setup`) with deterministic signal admission order,
optional cooldown, skipped-signal diagnostics, scoped UI controls, validation
warning, and scoped export assumptions.

---

## R5 — Walk-Forward / Out-of-Sample Validation ✅ Implemented

Adds deterministic bar-window walk-forward diagnostics for train-window SL/TP
selection and following out-of-sample evaluation, with compact validation-page
UI integration and scoped export/report fields.

---

## R6 — Institutional Metrics Upgrade ✅ Implemented

Adds additive institutional-grade trade diagnostics (distribution, tail, streak,
drawdown-pain, and outlier-dependency metrics) to summaries, grid results,
compact UI/report sections, and targeted regression coverage.

---

## R7 — Futures Contract Roll Methodology ✅ Implemented

Adds explicit roll-policy modes (`single_contract`, `external_continuous`,
`segmented_contracts`), compact data-page assumptions controls, roll metadata
validation/gap diagnostics, and export/report inclusion of roll assumptions for
auditability without introducing internal price adjustment.

---

## R8 — Save-as-Default Execution Settings ✅ Implemented

Adds narrow, regression-safe user-controlled persistence for Backtest and Grid
Search execution settings.

### Scope

UI/persistence layer only. Engine and analytics code (`simulate_trades`,
`run_sl_tp_grid`, `thesistester/analytics/metrics.py`) are **unaffected**.

### Features

- **💾 Save execution settings as default** button on Backtest and Grid Search
  sidebar pages.  Settings are persisted only on explicit click, never on run.
- **↩ Reset to built-in defaults** button clears saved defaults and reverts
  widgets to built-in values on the next render.
- Saved defaults are loaded once per session and injected only into absent
  `st.session_state` keys — in-session user edits are never overwritten.
- **Independent namespaces** in `ui_state.json`:
  - `backtest_defaults` — covers SL/TP ticks, commission, slippage, max-holding-bars,
    same-bar exit, session close, timezone, no-new-entries cutoff, exposure policy, cooldown.
  - `grid_defaults` — same fields plus SL/TP range start/stop/step, ranking metric,
    min trades, directional ranking settings.
- Saving Backtest defaults never affects Grid defaults, and vice versa.
- Both namespaces are **versioned** (`defaults_schema_version = 1`). Schema drift
  (version mismatch) causes defaults to be silently ignored; widgets fall back to
  their built-in values.
- Invalid saved values (unknown policy/timezone/metric, out-of-range numbers,
  malformed time strings, non-bool booleans) are **dropped silently** before
  injection so they never reach the engine.
- Existing unrelated UI state keys (e.g. `active_dataset_id`) are always preserved.

### New files

| File | Purpose |
|---|---|
| `thesistester/execution_defaults.py` | Validation, injection, and collection helpers |
| `tests/test_backtest_grid_defaults.py` | 43 tests: roundtrip, isolation, schema drift, reset, validation, engine isolation |

### Modified files

| File | Change |
|---|---|
| `thesistester/persistence/local_store.py` | Added `BACKTEST_DEFAULTS_SCHEMA_VERSION`, `GRID_DEFAULTS_SCHEMA_VERSION`, and 6 new functions |
| `thesistester/persistence/__init__.py` | Exported new constants and functions |
| `pages/7_Backtest.py` | Added stable `key=` to execution-setting widgets; load/save/reset logic |
| `pages/8_Grid_Search.py` | Added stable `key=` to execution-setting widgets; load/save/reset logic |
