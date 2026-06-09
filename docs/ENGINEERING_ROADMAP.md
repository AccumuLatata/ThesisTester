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

## R4 — Exposure and Trade Lifecycle Model

Not yet implemented. Planned for a future milestone.

---

## R5 — Walk-Forward / Out-of-Sample Validation

Not yet implemented. Planned for a future milestone.

---

## R6 — Institutional Metrics Upgrade

Not yet implemented. Planned for a future milestone.

---

## R7 — Futures Contract Roll Methodology

Not yet implemented. Planned for a future milestone.
