# Engineering Roadmap

This document tracks the ThesisTester engineering roadmap milestones.

---

## R1 — Execution costs ✅ Implemented

Adds optional commission and slippage to `simulate_trades`. Defaults preserve legacy
gross behavior. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §1.

---

## R2 — Session-exit logic ✅ Implemented

Adds `flat_by_session_close` mode to `simulate_trades`. `SESSION_CLOSE` and `DATA_END`
exit types supported. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §3.

---

## R3 — Point-in-time audit and causality hardening ✅ Implemented

**Acceptance criteria met:**

- `pytest -q` passes (all non-UI, non-parquet tests pass; parquet failures are
  pre-existing environment-only issues).
- `docs/POINT_IN_TIME_GUARANTEES.md` created and specific to current code.
- Future-shock regression tests added in `tests/test_r3_point_in_time.py` (17 tests).
- No broad refactors made.
- No unrelated behavior changes.
- All confirmed look-ahead issues: **none found**. All level and signal computations
  were already causal. See audit table in `docs/POINT_IN_TIME_GUARANTEES.md`.
- Signal timestamps/bar indices verified to reflect when a signal is
  actually knowable/actionable (tests confirm no backdating).
- Backtest R1/R2 behavior unchanged.
- Documentation updated: `ASSUMPTIONS_AND_LIMITATIONS.md` §6,
  `docs/POINT_IN_TIME_GUARANTEES.md` created.

**Summary of audit findings:**

All audited modules (`levels/sessions.py`, `levels/profile.py`, `levels/indicators.py`,
`engine/naked.py`, `engine/confluence.py`, `engine/anchor_confluence.py`,
`engine/signals.py`, `engine/signals_3c.py`) were found to be causal. No look-ahead
bugs were discovered. The deliverable is therefore documentation + regression tests
rather than code fixes.

See `docs/POINT_IN_TIME_GUARANTEES.md` for the full audit table and known limitations.

---

## R4 — Walk-forward validation

Not yet implemented. Planned for a future milestone.

---

## R5 — Exposure and concurrency model

Not yet implemented. Planned for a future milestone.
