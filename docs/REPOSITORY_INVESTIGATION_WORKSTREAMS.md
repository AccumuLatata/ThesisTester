# Repository Investigation Workstreams

**Repository:** `AccumuLatata/ThesisTester`  
**Investigation mode:** Research only  
**Status:** Planned  
**Created:** 2026-07-23

## 1. Mission

Conduct an evidence-based, repository-wide investigation of ThesisTester to determine whether its code paths, financial calculations, data handling, user workflows, persistence, exports, and documented behavior operate correctly.

This phase is strictly investigative. It may identify defects and recommend remediation, but it must not implement fixes or change application code, tests, configuration, dependencies, workflows, or existing documentation.

## 2. Non-negotiable guardrails

Every workstream must follow these rules:

1. **Research only:** Do not edit, create, delete, rename, or reformat application code, tests, configuration, dependency files, workflows, or existing documentation.
2. **No pull request:** Do not create a remediation PR or commit proposed fixes.
3. **No destructive actions:** Do not alter persistent data, tracked fixtures, repository settings, external services, or user environments.
4. **Regression-safe:** Existing behavior must remain unchanged. Tests may be executed, but test files and fixtures must not be modified.
5. **Drift-safe:** Stay within the assigned workstream. Record adjacent issues as handoffs rather than expanding scope silently.
6. **Reproducible evidence:** Record exact commands, environment details, inputs, outputs, file paths, symbols, and relevant line ranges.
7. **No unsupported conclusions:** Distinguish verified defects, suspected risks, design limitations, and unverified unknowns.
8. **Financial caution:** Do not describe backtest output as reliable unless the relevant data, execution, P&L, session, and bias controls have been verified.
9. **Safe test execution:** Prefer isolated, read-only, deterministic execution. Do not use production credentials or proprietary data.
10. **Documentation tracking:** Each finding must identify documentation that would require updating during a later remediation phase. Do not make those updates during this investigation.

## 3. Scope-control process

### Status values

Use only:

- `Not started`
- `In progress`
- `Blocked`
- `Completed`
- `Needs follow-up`

### Finding classifications

- **Verified defect:** Reproduced or established directly from executable behavior and code evidence.
- **Probable defect:** Strong evidence exists, but runtime reproduction is incomplete.
- **Design limitation:** Behavior is intentional or structurally constrained but may invalidate user expectations.
- **Security risk:** A plausible confidentiality, integrity, availability, or trust-boundary weakness.
- **Documentation drift:** Documentation conflicts with or omits actual behavior.
- **Unknown:** Evidence is insufficient; further access, data, or controlled testing is required.

### Severity criteria

- **Critical:** Can broadly invalidate research results, cause severe compromise, or make the application unusable without an effective safeguard.
- **High:** Can materially distort trading conclusions, compromise untrusted-input handling, or break a core workflow.
- **Medium:** Produces incorrect or fragile behavior under realistic conditions but has limited scope or a practical workaround.
- **Low:** Minor correctness, usability, maintainability, or documentation issue with limited immediate impact.

### Required finding record

Every finding must include:

1. Finding ID and workstream ID
2. Title and classification
3. Severity and confidence
4. Affected files and symbols
5. Preconditions and tested environment
6. Exact reproduction procedure or static reasoning
7. Expected behavior
8. Observed behavior
9. Financial, security, or operational impact
10. Regression surface
11. Narrow recommended remediation direction
12. Tests required in a later implementation phase
13. Documentation updates required later
14. Dependencies or handoffs to other workstreams

## 4. Investigation workstreams

### WS-00 — Baseline, inventory, and evidence protocol

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Establish the immutable investigation baseline and repository map used by every specialist.

**Tasks:**

- Record commit SHA, branch, repository state, operating system, Python version, and dependency versions.
- Inventory entry points, packages, pages, tests, data samples, configuration, persistence, and documentation.
- Map intended workflows and subsystem dependencies.
- Define shared evidence and finding templates.
- Record commands that are safe to run and commands that require isolation.

**Exit criteria:**

- Baseline commit and environment are documented.
- Repository map is complete enough to assign every relevant file to at least one workstream.
- No tracked file has changed.

---

### WS-01 — Test execution, determinism, and coverage

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Establish the actual test status and identify untested critical behavior.

**Tasks:**

- Run the documented test command in an isolated environment.
- Record collection errors, failures, warnings, duration, and dependency versions.
- Run tests repeatedly where needed to identify nondeterminism or state leakage.
- Map tests to core modules and financial invariants.
- Identify missing regression cases without writing tests.
- Assess whether random seeds, temporary files, time zones, and test order are controlled.

**Required focus:**

- Gap fills and same-bar sequencing
- Contract metadata ingestion
- Holidays, early closes, DST, and overnight sessions
- Missing and malformed bars
- Overlapping trades and capital assumptions
- Bundle and upload abuse cases
- Full upload-to-export workflow

**Exit criteria:**

- Exact test results are recorded and reproducible.
- Critical coverage gaps are mapped to modules and expected future tests.
- No tests or fixtures have been changed.

---

### WS-02 — Runtime startup and Streamlit workflow verification

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that the application starts and that every user-facing workflow functions without uncaught errors.

**Tasks:**

- Launch the app in an isolated environment using documented instructions.
- Inspect every page, widget, navigation path, state transition, and error state.
- Exercise the canonical workflow: Data → Levels → Setup → Signals → Backtest → Grid → Time Analysis → Validation → Export.
- Verify refresh, rerun, empty-state, repeated-run, and invalid-input behavior.
- Check widget-key collisions, stale session state, download behavior, and error visibility.
- Record browser and Streamlit runtime details.

**Exit criteria:**

- Every page and core workflow has a recorded outcome.
- Failures include reproducible inputs and traces.
- UI testing does not modify tracked repository files.

---

### WS-03 — Futures data ingestion and validation

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Determine whether market data is ingested, normalized, validated, and propagated without silent corruption.

**Tasks:**

- Trace CSV ingestion through canonical storage and downstream consumers.
- Verify timestamp parsing, timezone handling, sorting, duplicates, nulls, OHLC consistency, volume rules, and frequency inference.
- Investigate whether contract identifiers and other required metadata survive ingestion.
- Test malformed, adversarial, sparse, out-of-order, and duplicate datasets safely.
- Verify fatal versus advisory validation behavior.
- Check assumptions about bar-open versus bar-close timestamps.

**Exit criteria:**

- The accepted data contract is documented from actual behavior.
- Silent normalization or metadata loss is identified.
- Invalid-data continuation paths are classified.

---

### WS-04 — Futures rolls and continuous-contract correctness

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that contract boundaries, roll events, and price adjustments are detectable and financially coherent.

**Tasks:**

- Trace contract metadata from upload through roll validation and backtesting.
- Verify supported roll methods and boundary detection.
- Examine raw, back-adjusted, ratio-adjusted, and segmented-contract assumptions where applicable.
- Test artificial gaps, overlapping contracts, missing contract IDs, and multiple roll boundaries.
- Determine whether volume/open-interest roll conventions are supported or merely implied.
- Assess impact on levels, signals, fills, and P&L.

**Exit criteria:**

- Roll validation availability and limitations are established.
- Any artificial price/P&L discontinuity risk is quantified with a minimal example.

---

### WS-05 — Session, exchange-calendar, and resampling correctness

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that session tagging, forced exits, and higher-timeframe bars reflect futures-market conventions.

**Tasks:**

- Trace RTH/ETH definitions and timezone conversions.
- Test normal sessions, holidays, early closes, DST transitions, maintenance windows, and overnight sessions.
- Examine missing-close-bar behavior and session-date attribution.
- Verify resampling origin, offset, labels, closure, partial bars, and missing constituent bars.
- Compare outputs against explicit reference calculations or authoritative exchange-session definitions.

**Exit criteria:**

- Supported session models and calendar exclusions are explicit.
- Resampling alignment and partial-bar behavior are reproduced and assessed.

---

### WS-06 — Signal generation and point-in-time integrity

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that signals use only information available at the decision time and behave consistently across supported setups.

**Tasks:**

- Trace each signal implementation and setup configuration.
- Check indexing, shifts, rolling windows, resampled inputs, level availability, and entry timestamps.
- Search for look-ahead bias, accidental future leakage, and same-bar ambiguity.
- Verify behavior at dataset boundaries, missing bars, duplicated bars, and session transitions.
- Reconcile representative signals manually from source bars.

**Exit criteria:**

- Each signal family has a point-in-time evidence record.
- Ambiguous or leaking paths are isolated with minimal examples.

---

### WS-07 — Execution, fills, stops, targets, and trade lifecycle

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Determine whether simulated trade execution is internally consistent and suitably conservative for bar-based futures research.

**Tasks:**

- Trace order creation, entry, stop, target, timeout, session-close, and conflict handling.
- Investigate open-through-stop and open-through-target gaps.
- Investigate same-bar entry/exit ordering, especially 3c retracement behavior.
- Verify long/short symmetry, tick rounding, slippage, commissions, point values, and exit reasons.
- Assess overlapping trades, position rules, partial fills, liquidity, and queue assumptions.
- Compare representative trades with independent manual calculations.

**Exit criteria:**

- Fill policy is fully characterized.
- Every ambiguous OHLC sequence is identified and classified.
- Financial impact is demonstrated for material execution assumptions.

---

### WS-08 — P&L, portfolio, risk, and analytics correctness

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that reported performance statistics mean what users are likely to infer and are calculated correctly.

**Tasks:**

- Reconcile trade P&L, commissions, slippage, point values, and cumulative equity manually.
- Verify drawdown, win rate, expectancy, profit factor, trade duration, and risk metrics.
- Examine ordering by entry/exit timestamps and treatment of overlapping exposure.
- Determine whether metrics are trade-sequence diagnostics or portfolio/capital returns.
- Test empty, single-trade, all-win, all-loss, zero-variance, and extreme-value cases.
- Assess quantity, margin, capital, leverage, and concurrent-risk assumptions.

**Exit criteria:**

- Material metrics are independently reconciled.
- Labels and economic interpretations are classified as accurate, misleading, or incomplete.

---

### WS-09 — Statistical validation, optimization, and overfitting controls

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Assess whether grid search and statistical validation support defensible research conclusions.

**Tasks:**

- Trace parameter search, ranking, train/test separation, and validation outputs.
- Check deterministic seeding and repeated-run consistency.
- Investigate multiple-testing bias, selection bias, leakage, and overfitting controls.
- Verify treatment of small samples, non-independent trades, and unstable estimates.
- Review bootstrap or Monte Carlo assumptions where present.
- Determine whether reported confidence language is statistically justified.

**Exit criteria:**

- Statistical methods and assumptions are mapped to implementation.
- Unsupported inference or overconfidence risks are documented.

---

### WS-10 — Persistence, state, reporting, and exports

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Verify that saved setups, session state, reports, and exported artifacts preserve correct and complete information.

**Tasks:**

- Trace local persistence, identifiers, overwrite behavior, serialization, and reload behavior.
- Test stale, missing, malformed, and incompatible stored records safely.
- Compare displayed results with exported results.
- Verify deterministic ordering, numeric precision, time zones, metadata, and provenance.
- Check multi-user/shared-deployment assumptions without altering external systems.

**Exit criteria:**

- Round-trip behavior is documented.
- Data loss, stale-state, collision, or provenance risks are identified.

---

### WS-11 — Research bundles and untrusted-input security

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Assess security, integrity, and availability risks from uploaded CSV, ZIP, parquet, and research-bundle content.

**Tasks:**

- Map trust boundaries and all upload/import paths.
- Inspect member count, compressed size, expanded size, expansion ratio, duplicate names, schemas, and type handling.
- Examine integrity checks, hashes, fingerprints, and derived-artifact provenance.
- Use safe synthetic metadata and bounded fixtures; do not generate a destructive payload.
- Assess path traversal, unsafe deserialization, memory exhaustion, CPU exhaustion, and malformed parquet behavior.
- Verify that imports cannot silently claim validation they have not earned.

**Exit criteria:**

- Resource and integrity controls are fully inventoried.
- Safe reproduction evidence exists for material weaknesses.

---

### WS-12 — Dependency, packaging, environment, and CI reproducibility

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Determine whether a clean environment can reproduce installation, tests, and startup without dependency drift.

**Tasks:**

- Record Python compatibility and dependency resolution behavior.
- Inspect lower/upper bounds, transitive dependencies, deprecated APIs, and platform assumptions.
- Perform isolated clean-install checks on feasible Python versions without changing repository files.
- Inventory CI, linting, typing, formatting, coverage, and dependency-security automation.
- Identify missing runtime metadata and lock/constraint strategy.

**Exit criteria:**

- Supported and unsupported environments are evidence-based.
- Reproducibility and dependency-drift risks are documented.

---

### WS-13 — Documentation and user-expectation drift

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Compare documented claims, workflows, assumptions, and limitations against verified behavior.

**Tasks:**

- Compare README and docs with code and runtime findings.
- Check workflow order, installation, supported instruments, sessions, timestamps, fills, metrics, rolls, and validation claims.
- Identify missing warnings that could cause financial misinterpretation.
- Build a later-phase documentation update list tied to finding IDs.
- Do not edit documentation during this investigation.

**Exit criteria:**

- Every verified behavioral mismatch has a documentation-drift record.
- Required future documentation changes are traceable to findings.

---

### WS-14 — Cross-workstream regression and drift review

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Challenge specialist conclusions, remove duplicates, identify contradictions, and ensure no subsystem was missed.

**Tasks:**

- Review all specialist evidence against the baseline commit.
- Check that findings remain within scope and use consistent severity criteria.
- Reproduce high-impact findings independently where feasible.
- Map interactions among data, rolls, sessions, signals, execution, analytics, persistence, and exports.
- Identify changes in repository state or environment that could invalidate conclusions.
- Confirm that no tracked files were modified during investigation.

**Exit criteria:**

- High and critical findings have independent review.
- Contradictions and duplicates are resolved.
- Scope coverage and repository cleanliness are confirmed.

---

### WS-15 — Final synthesis and remediation handoff

**Status:** Not started  
**Owner:** Unassigned

**Objective:** Produce the final evidence-based investigation report without implementing changes.

**Tasks:**

- Summarize verified behavior, defects, limitations, security risks, and unknowns.
- Rank findings by financial impact, user impact, exploitability, and remediation dependency.
- Separate immediate safeguards from later implementation work.
- Create a narrow, regression-safe remediation sequence.
- Specify future tests and documentation updates for each remediation item.
- State clearly what was not tested and why.

**Exit criteria:**

- Findings are traceable to workstreams and evidence.
- The remediation roadmap does not contain code changes.
- No claim of “error-free” is made unless all material paths have been verified with adequate evidence.

## 5. Workstream dependency order

Recommended sequence:

1. WS-00 baseline
2. WS-01, WS-03, WS-12 in parallel
3. WS-02 after a reproducible environment is available
4. WS-04 and WS-05 after data behavior is established
5. WS-06 after data, roll, session, and resampling assumptions are established
6. WS-07 after signal timing is established
7. WS-08 and WS-09 after execution semantics are established
8. WS-10 and WS-11 after artifact schemas and state flows are mapped
9. WS-13 after runtime and financial behavior are verified
10. WS-14 cross-review
11. WS-15 final synthesis

A downstream workstream must not silently redefine an upstream assumption. It must record a contradiction and return it for review.

## 6. Progress tracker

| ID | Workstream | Status | Owner | Evidence/report | Blockers |
|---|---|---|---|---|---|
| WS-00 | Baseline, inventory, and evidence protocol | Not started | Unassigned | — | — |
| WS-01 | Test execution, determinism, and coverage | Not started | Unassigned | — | WS-00 |
| WS-02 | Runtime startup and Streamlit workflows | Not started | Unassigned | — | WS-00, WS-12 |
| WS-03 | Futures data ingestion and validation | Not started | Unassigned | — | WS-00 |
| WS-04 | Futures rolls and continuous contracts | Not started | Unassigned | — | WS-03 |
| WS-05 | Sessions, exchange calendars, and resampling | Not started | Unassigned | — | WS-03 |
| WS-06 | Signals and point-in-time integrity | Not started | Unassigned | — | WS-03, WS-04, WS-05 |
| WS-07 | Execution and trade lifecycle | Not started | Unassigned | — | WS-06 |
| WS-08 | P&L, portfolio, risk, and analytics | Not started | Unassigned | — | WS-07 |
| WS-09 | Statistical validation and overfitting | Not started | Unassigned | — | WS-07, WS-08 |
| WS-10 | Persistence, reporting, and exports | Not started | Unassigned | — | WS-02, WS-08 |
| WS-11 | Research bundles and untrusted inputs | Not started | Unassigned | — | WS-00 |
| WS-12 | Dependencies, packaging, environment, and CI | Not started | Unassigned | — | WS-00 |
| WS-13 | Documentation and expectation drift | Not started | Unassigned | — | WS-02–WS-12 |
| WS-14 | Cross-workstream regression and drift review | Not started | Unassigned | — | WS-01–WS-13 |
| WS-15 | Final synthesis and remediation handoff | Not started | Unassigned | — | WS-14 |

## 7. Stop and escalation conditions

Stop the affected task and record a blocker if:

- Investigation requires modifying a tracked file.
- A command may alter external or persistent data.
- Required credentials, proprietary data, or production access are unavailable.
- A test can only be reproduced with an unsafe payload or uncontrolled resource use.
- Repository HEAD changes after the baseline is recorded.
- Evidence contradicts an established upstream assumption.
- Scope expansion would duplicate or bypass another workstream.

Do not solve the issue during this phase. Record the narrowest reproducible evidence and hand it to WS-14 and WS-15.

## 8. Completion definition

The investigation is complete only when:

- Every workstream is `Completed`, `Blocked`, or `Needs follow-up` with a documented reason.
- Every relevant repository area is mapped to a workstream.
- Runtime and test commands include exact outcomes.
- Material financial calculations have independent reference checks.
- High-impact findings have cross-workstream review.
- Unknowns and untested paths are explicit.
- The repository remains unchanged except for this investigation tracker document.
- No implementation, remediation, or code change has been performed.
