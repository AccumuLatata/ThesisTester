# OTF Filter Implementation Roadmap

**Project:** ThesisTester  
**Status:** Planned  
**Owner:** ThesisTester engineering  
**Last updated:** 2026-07-23  
**Feature:** Directional One Timeframing (OTF) market-condition filter

## Document purpose

This document is the living implementation plan for adding an optional OTF filter to ThesisTester. Update the status, decisions, test evidence, and links as work progresses. Keep the implementation regression-safe and drift-safe.

## Current status

- [x] OTF behavior specification approved
- [x] Baseline behavior and metrics captured
- [x] Deterministic OTF fixtures created (11 OHLCV scenarios + 3 vector scenarios)
- [x] Futures session boundary semantics documented (eth_start; midnight is NOT a boundary)
- [x] HTF bar timestamp/availability semantics documented (bar_start / bar_close / availability)
- [x] Schema version inventory captured
- [ ] Pure OTF calculation engine implemented
- [ ] Look-ahead protections tested against production engine
- [ ] Signal eligibility integration implemented
- [ ] Setup persistence and compatibility implemented
- [ ] UI controls implemented
- [ ] Backtest, grid-search, and walk-forward integration completed
- [ ] Reporting and export completed
- [ ] Documentation completed
- [ ] Statistical validation completed
- [ ] Release approved

## Objective

Add an optional, directional OTF market-condition filter for setups using 5-minute, 15-minute, and 30-minute timeframes.

When disabled, the application must preserve existing behavior. When enabled:

- Long setups pass only when the selected OTF timeframes are up.
- Short setups pass only when the selected OTF timeframes are down.
- Neutral, unknown, or opposing OTF conditions reject the setup.
- Only completed higher-timeframe bars may be used.
- Rejected setups remain available for audit and analysis.

## Initial approved scope

### OTF states

Use a controlled state vocabulary:

- `up`
- `down`
- `neutral`
- `unknown`

Initial directional interpretation:

- OTF up: the current completed bar has a higher low than the preceding completed bar.
- OTF down: the current completed bar has a lower high than the preceding completed bar.
- Neutral: neither directional condition is established.
- Broken sequence: the current OTF sequence is invalidated according to the documented state-transition rules.

The exact state-transition rules must be finalized before production implementation and covered by deterministic tests.

### Initial configuration

```text
enabled: false
timeframes: []
alignment_mode: all
minimum_consecutive_bars: 3
directional: true
use_completed_bars_only: true
session_reset: session
```

### Initial timeframe logic

The first release supports:

- 5-minute OTF
- 15-minute OTF
- 30-minute OTF

The first release implements `all` alignment only: every selected timeframe must agree with the signal direction. `any` and hierarchical confirmation modes are deferred until the initial implementation is validated.

## Non-negotiable engineering constraints

### Regression safety

With OTF disabled:

```text
legacy signals == new signals
legacy trades == new trades
legacy metrics == new metrics
```

Existing saved setups without OTF configuration must continue to load and behave as before.

### Drift safety

Every OTF-enabled research result must identify:

- Dataset identity.
- Source interval.
- Source and exchange timezone.
- OTF algorithm version.
- OTF configuration hash.
- Setup configuration hash.
- Levels configuration hash.
- Signal configuration hash.

Results generated with different OTF algorithms or configurations must not appear equivalent.

### Look-ahead safety

For each signal, use only the most recent completed higher-timeframe bar available at the signal decision timestamp. Never use the eventual high, low, or close of a higher-timeframe bar that had not yet closed.

## Implementation roadmap

## Phase 0 — Freeze the baseline

**Status:** Partially complete (PR 1)

### Work items

- [x] Capture the current test result and environment.
- [x] Capture representative signal counts, trade counts, and metrics.
- [x] Record current setup, signal, persistence, and report schema versions.
- [x] Create a deterministic OHLCV fixture containing up, down, neutral, and broken OTF conditions.
- [x] Add a baseline regression test for OTF-disabled behavior.

### Acceptance criteria

- A repeatable baseline exists.
- The baseline can be compared after each implementation phase.
- No production behavior changes in this phase.

### Schema inventory (evidence for Phase 0 completion)

The following schema version constants are defined in `thesistester/persistence/local_store.py`:

| Constant | Value | Covers |
|---|---|---|
| `PERSISTENCE_SCHEMA_VERSION` | 1 | Top-level persistence layout version |
| `LEVEL_ENGINE_VERSION` | 3 | Session-level calculation engine version |
| `SIGNAL_RUN_SCHEMA_VERSION` | 1 | Signal-run directory and parquet schema |
| `SETUP_SCHEMA_VERSION` | 1 | Setup JSON configuration schema |
| `BACKTEST_DEFAULTS_SCHEMA_VERSION` | 1 | Backtest defaults schema |
| `GRID_DEFAULTS_SCHEMA_VERSION` | 1 | Grid-search defaults schema |

Application version: `thesistester.__version__ = "0.2.0"` (defined in `thesistester/__init__.py`).

Report and research artifact schema: no standalone schema version constant exists for reporting output.  Report artifacts are generated by `thesistester/reporting.py` and `thesistester/research_bundle.py`.  A baseline report schema identity is deferred to Phase 8 (reporting) when OTF metadata fields are added.

### Evidence / links

- Baseline test file: `tests/test_otf_baseline.py`
- Focused OTF verification: **223 passed in 0.86s** (`python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q`)
- Full-suite regression verification: **1106 passed in 23.20s** (`python3 -m pytest tests/ -q`)
- Baseline fixture file: `tests/fixtures/otf_fixtures.py`
- Schema version source: `thesistester/persistence/local_store.py`
- Related PR: PR 1 — OTF specification and deterministic fixtures

## Phase 1 — Finalize the OTF contract

**Status:** Complete (PR 1, updated PR 1 follow-up)

### Work items

- [x] Finalize the exact OTF state machine.
- [x] Define how many consecutive bars are required.
- [x] Define how a sequence breaks.
- [x] Define whether OTF state resets at each trading session.
- [x] Define handling for insufficient history.
- [x] Define the timestamp at which each signal is evaluated.
- [x] Document futures trading-session boundary semantics (eth_start convention).
- [x] Define bar_start_timestamp, bar_close_timestamp, and availability_timestamp.
- [x] Document all decisions in this file and the methodology documentation.

### Acceptance criteria

- The state vocabulary and transitions are unambiguous.
- Every edge case has an expected outcome.
- A developer can implement the rules without making undocumented assumptions.

### Decisions

| Decision | Outcome | Date | Rationale |
|---|---|---|---|
| Alignment mode for v1 | `all` | 2026-07-23 | Conservative directional confirmation. |
| Default enabled state | Disabled | 2026-07-23 | Preserves legacy behavior. |
| Completed bars only | Required | 2026-07-23 | Prevents look-ahead bias. |
| Minimum sequence length | 3 qualifying comparisons | 2026-07-23 | First becomes directional at 4th bar (anchor + 3 subsequent). Configurable and subject to validation. |
| Equal-high/equal-low | Strict inequality; resets counter | 2026-07-23 | Avoids ambiguous sequence length; consistent with MP convention. |
| Insufficient history | Returns `unknown` | 2026-07-23 | `neutral` implies an evaluation; `unknown` is more accurate. |
| Session reset | Reset at each trading-session boundary | 2026-07-23 | Session carry introduces subtle look-ahead risk. |
| State vocabulary | `up`, `down`, `neutral`, `unknown` | 2026-07-23 | Covers all states including contradictory and uninitialized. |
| Futures session boundary | `eth_start` determines boundary (18:00 ET for ES/NQ); midnight is NOT a boundary | 2026-07-23 | Matches ThesisTester's `trading_session_date()` in `thesistester/levels/session_date.py`. |
| HTF bar timestamp labeling | `bar_start_timestamp` (pandas left label) + explicit `bar_close_timestamp` | 2026-07-23 | Preserves pandas convention; makes availability unambiguous. Row label ≠ availability. |
| HTF bucket alignment | Match `resample_ohlcv()` wall-clock labels in the input timezone; not a separate UTC-midnight/session-anchor rule | 2026-07-23 | `DataFrame.resample()` preserves the tz-aware index timezone. For ES/NQ, 18:00 ET still lands on clean 5m/15m/30m boundaries. |
| Equal source/target interval | Not supported in OTF v1; source must be strictly finer | 2026-07-23 | Resampling equal intervals produces no higher-timeframe information; deferred to PR 2 for validation. |

### Evidence / links

- Contract document: `docs/otf-filter.md`
- Contract test file: `tests/test_otf_contract.py`
- Direct actual-resampler drift guard: `TestLookaheadSafety.test_actual_resample_5m_uses_close_timestamp_for_otf_availability`
- Focused verification command/result: `python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q` → **223 passed in 0.86s**
- Full-suite verification command/result: `python3 -m pytest tests/ -q` → **1106 passed in 23.20s**
- OHLCV fixture file: `tests/fixtures/otf_fixtures.py`
- Resample helper implementation: `thesistester/data/resample.py`
- Focused helper regression tests: `tests/test_loader.py`
- Related PR: PR 1 — OTF specification and deterministic fixtures

### PR 2 prerequisites carried forward

- The production OTF engine must apply the verified availability contract: `bar_close_timestamp <= signal_decision_timestamp`.
- Future-shock / append-data invariance must be tested against the real OTF engine.
- Partial first session-boundary bucket handling remains a deliberate implementation decision.

## Phase 2 — Build the pure OTF engine

**Status:** Not started

### Target files

- `thesistester/engine/otf.py`
- `tests/test_otf.py`

### Work items

- [ ] Validate required OHLCV columns.
- [ ] Validate timestamps and timezone handling.
- [ ] Implement 5m, 15m, and 30m resampling.
- [ ] Implement completed-bar alignment.
- [ ] Implement OTF state calculation.
- [ ] Implement sequence length and reference timestamp outputs.
- [ ] Implement session-reset behavior.
- [ ] Expose a stable public API.
- [ ] Add module-level documentation.

### Suggested API

```python
calculate_otf_state(
    df: pd.DataFrame,
    timeframe: str,
    *,
    minimum_consecutive_bars: int = 3,
    session_timezone: str | None = None,
    session_reset: str = "session",
) -> pd.DataFrame
```

### Required output fields

```text
otf_state
otf_sequence_length
otf_reference_timestamp
```

### Acceptance criteria

- The engine is independent of Streamlit pages.
- The engine is deterministic.
- The engine does not mutate caller-owned data.
- Unit tests cover normal and invalid input.

## Phase 3 — Prove look-ahead safety

**Status:** Not started

### Work items

- [ ] Test that unfinished 15m bars cannot affect earlier signals.
- [ ] Test that unfinished 30m bars cannot affect earlier signals.
- [ ] Test that future highs, lows, and closes do not alter prior states.
- [ ] Test that appending bars after timestamp `T` does not change OTF states at or before `T`.
- [ ] Test session-boundary behavior.
- [ ] Test timezone-aware and timezone-naive inputs.
- [ ] Test resampling boundaries for the supported source intervals.

### Acceptance criteria

The following property must hold:

```text
OTF state for timestamps <= T is unchanged when data after T is appended.
```

Any failure blocks integration.

## Phase 4 — Integrate at signal eligibility

**Status:** Not started

### Target areas

- Signal-generation orchestration.
- Signal context and metadata.
- Existing signal persistence.
- Existing skipped-signal/audit pathways.

### Work items

- [ ] Implement `apply_otf_filter` using the shared OTF engine.
- [ ] Apply the filter after candidate signal generation and before backtesting.
- [ ] Keep `simulate_trades` focused on execution rather than regime calculation.
- [ ] Preserve all original signal columns.
- [ ] Preserve OTF-rejected signals separately.
- [ ] Add deterministic rejection reasons.
- [ ] Keep OTF rejection distinct from execution skips.
- [ ] Verify disabled filtering returns the legacy signal population.

### Suggested metadata

```text
otf_5m_state
otf_5m_sequence_length
otf_5m_reference_timestamp
otf_15m_state
otf_15m_sequence_length
otf_15m_reference_timestamp
otf_30m_state
otf_30m_sequence_length
otf_30m_reference_timestamp
otf_filter_enabled
otf_filter_passed
otf_filter_reason
```

### Acceptance criteria

- Long and short filtering is directionally correct.
- Neutral and unknown states are handled explicitly.
- Rejected signals are inspectable.
- Existing backtest execution behavior is unchanged for accepted signals.

## Phase 5 — Add persistence and versioning

**Status:** Not started

### Work items

- [ ] Add an optional `otf_filter` block to setup configuration.
- [ ] Define backward-compatible defaults for legacy setups.
- [ ] Add configuration validation.
- [ ] Add OTF algorithm version metadata.
- [ ] Add OTF configuration hashing.
- [ ] Include OTF identity in signal and research fingerprints.
- [ ] Test save/load round trips.
- [ ] Test loading setups created before OTF support.
- [ ] Add migration logic only if required by the repository schema.

### Configuration shape

```python
"otf_filter": {
    "enabled": False,
    "timeframes": [],
    "alignment_mode": "all",
    "minimum_consecutive_bars": 3,
    "directional": True,
    "use_completed_bars_only": True,
    "session_reset": "session",
}
```

### Acceptance criteria

- Legacy setup files load successfully.
- New configurations round-trip without loss.
- Different OTF configurations produce different research identities.

## Phase 6 — Implement UI controls

**Status:** Not started

### Work items

- [ ] Add an expandable market-regime filter section.
- [ ] Add enable/disable control.
- [ ] Add 5m, 15m, and 30m timeframe selection.
- [ ] Add alignment-mode control, initially fixed to or limited to `all`.
- [ ] Add minimum sequence length.
- [ ] Add session-reset policy.
- [ ] Add clear completed-bar/look-ahead explanation.
- [ ] Validate enabled filters with no selected timeframe.
- [ ] Display the active configuration in the backtest page.

### Acceptance criteria

- The UI cannot create invalid OTF configurations.
- Disabled is the default for existing and new workflows unless deliberately changed.
- The displayed configuration matches the configuration used by the engine.

## Phase 7 — Integrate all research modes

**Status:** Not started

### Work items

- [ ] Standard backtest uses the filtered signal set.
- [ ] SL/TP grid search uses the same filtered signal set for every risk combination.
- [ ] Walk-forward uses only information available within each fold.
- [ ] OTF configuration remains fixed across folds unless explicit training-only optimization is implemented.
- [ ] Future research modes consume the shared filter output rather than reimplementing OTF.
- [ ] Add integration tests for each mode.

### Acceptance criteria

- No duplicate OTF implementations exist.
- Grid-search comparisons use identical eligible signals.
- Walk-forward evaluation contains no OTF leakage from future folds.

## Phase 8 — Reporting and exports

**Status:** Not started

### Work items

- [ ] Display candidate signal count.
- [ ] Display OTF-passed signal count.
- [ ] Display OTF-rejected signal count.
- [ ] Display rejection percentage.
- [ ] Display the active OTF configuration.
- [ ] Add rejected-signal table or export.
- [ ] Include OTF algorithm version and configuration hash in research artifacts.
- [ ] Distinguish disabled filtering from zero-pass filtering.

### Acceptance criteria

A user can determine exactly:

- Whether OTF was enabled.
- Which timeframes were used.
- Which algorithm version was used.
- How many signals were rejected and why.

## Phase 9 — Documentation

**Status:** In progress (PR 1 delivers initial documentation)

### Work items

- [x] Create this living roadmap.
- [x] Document the OTF definition.
- [x] Document state transitions and sequence breaks.
- [x] Document resampling and completed-bar rules.
- [x] Document session and timezone policy.
- [ ] Document configuration examples.
- [ ] Document rejected-signal interpretation.
- [ ] Document walk-forward treatment.
- [ ] Document algorithm versioning and drift controls.
- [ ] Update `README.md` and relevant methodology documentation.

### Recommended documentation files

- `docs/otf-filter-roadmap.md` — this implementation tracker.
- `docs/otf-filter.md` — user-facing methodology and behavior.
- `docs/research-methodology.md` — impact on research validity and walk-forward analysis.

## Phase 10 — Statistical validation and release gate

**Status:** Not started

### Comparison matrix

- [ ] No OTF filter.
- [ ] 15m only.
- [ ] 30m only.
- [ ] 15m + 30m.
- [ ] 5m + 15m + 30m.

### Metrics

- [ ] Trade count.
- [ ] Expectancy per trade.
- [ ] Total R.
- [ ] Average R.
- [ ] Profit factor.
- [ ] Maximum drawdown.
- [ ] Win rate.
- [ ] Long/short performance.
- [ ] Session and time-of-day performance.
- [ ] Time in market.

### Validation rules

- [ ] Do not select the preferred configuration on the full evaluation dataset.
- [ ] Use training data for parameter selection.
- [ ] Use out-of-sample data for final evaluation.
- [ ] Confirm improvements are not caused only by lower trade frequency.
- [ ] Confirm results across multiple market periods and instruments where appropriate.

## Test plan

### Unit tests

- [ ] Up sequence.
- [ ] Down sequence.
- [ ] Neutral state.
- [ ] Broken up sequence.
- [ ] Broken down sequence.
- [ ] Minimum sequence length.
- [ ] Missing columns.
- [ ] Invalid timestamps.
- [ ] Empty input.
- [ ] Duplicate timestamps.
- [ ] Timezone-aware input.
- [ ] Timezone-naive input with configured timezone.
- [ ] Session boundaries.

### Filter tests

- [ ] Long with OTF up passes.
- [ ] Short with OTF down passes.
- [ ] Long with OTF down rejects.
- [ ] Short with OTF up rejects.
- [ ] Neutral rejects.
- [ ] All-timeframe agreement.
- [ ] No selected timeframes is rejected by validation.
- [ ] Disabled filter preserves the original dataframe.
- [ ] Rejection reasons are deterministic.

### Regression tests

- [ ] Legacy signal columns remain unchanged with OTF disabled.
- [ ] Legacy trade output remains unchanged with OTF disabled.
- [ ] Legacy metrics remain unchanged with OTF disabled.
- [ ] Existing saved datasets remain loadable.
- [ ] Existing saved setups remain loadable.
- [ ] Existing grid-search behavior remains unchanged when OTF is disabled.
- [ ] Existing walk-forward behavior remains unchanged when OTF is disabled.

## Pull request sequence

### PR 1 — Specification and fixtures

**Status:** Complete (follow-up corrections applied)

- [x] Documentation and state-transition contract (`docs/otf-filter.md`).
- [x] Deterministic OHLCV fixtures (`tests/fixtures/otf_fixtures.py`).
- [x] Baseline regression tests (`tests/test_otf_baseline.py`).
- [x] Contract integrity and vector tests (`tests/test_otf_contract.py`).
- [x] Updated roadmap (`docs/otf-filter-roadmap.md`).
- [x] No production behavior change.
- [x] Futures trading-session boundary corrected (eth_start convention; midnight is NOT a boundary).
- [x] HTF bar timestamp/availability semantics clarified (bar_start vs bar_close vs availability).
- [x] Overnight futures-session fixture added (Scenario 14).
- [x] Look-ahead fixture updated with explicit start/close/availability timestamps.
- [x] Schema inventory added to Phase 0 evidence.

**Test evidence (PR 1 follow-up):**

```
python -m pytest tests/test_otf_contract.py tests/test_otf_baseline.py -v
RESULT: 199 passed in 0.67s

python -m pytest tests/ --ignore=tests/test_app_state.py -q
RESULT: 1097 passed in 22.10s
```

**Pre-existing excluded test:** `tests/test_app_state.py` requires a running Streamlit application instance.  This failure is pre-existing, unrelated to OTF changes, and exists on the base branch.

**Regression statement:**

Production OTF behavior is not implemented in PR 1.
Existing application behavior is unchanged.
No production files outside `docs/` and `tests/` were modified.

### PR 2 — Pure OTF engine

- `thesistester/engine/otf.py`.
- Unit tests.
- Look-ahead tests.
- Feature remains unused by default.

### PR 3 — Signal filtering

- Shared filter application.
- Rejected-signal preservation.
- Disabled-filter regression coverage.

### PR 4 — Persistence and UI

- Setup configuration.
- Backward-compatible loading.
- Versioning and hashing.
- User controls and validation.

### PR 5 — Research integration and reporting

- Backtest integration.
- Grid-search integration.
- Walk-forward integration.
- Reporting and export metadata.

### PR 6 — Validation and release

- Statistical comparison matrix.
- Documentation completion.
- Drift review.
- Release approval with the feature disabled by default.

## Definition of done

- [ ] Existing users see no behavior change unless OTF is enabled.
- [ ] OTF uses completed bars only.
- [ ] Historical OTF states are invariant when future data is appended.
- [ ] OTF-rejected signals are inspectable.
- [ ] One shared implementation is used across all research modes.
- [ ] OTF configuration is persisted and fingerprinted.
- [ ] Legacy saved setups load successfully.
- [ ] Reports identify the complete OTF configuration and algorithm version.
- [ ] Documentation describes the exact methodology.
- [ ] Out-of-sample validation is complete.
- [ ] Regression and drift-safety reviews are complete.

## Progress log

| Date | Phase / change | Evidence or link | Notes |
|---|---|---|---|
| 2026-07-23 | Roadmap created | _This document_ | Initial regression-safe and drift-safe plan. |
| 2026-07-23 | Phase 0 partially complete | `tests/test_otf_baseline.py` | 898 pre-existing tests pass; baseline captured; schema inventory deferred until follow-up. |
| 2026-07-23 | Phase 1 complete | `docs/otf-filter.md`, `tests/fixtures/otf_fixtures.py`, `tests/test_otf_contract.py` | OTF v1 contract approved; 13 OHLCV scenarios + 3 vector scenarios; 177 new tests pass. |
| 2026-07-23 | PR 1 follow-up corrections | `docs/otf-filter.md`, `docs/otf-filter-roadmap.md`, `tests/fixtures/otf_fixtures.py`, `tests/test_otf_contract.py` | Session boundary corrected (eth_start; midnight NOT a boundary); HTF timestamp semantics added (bar_start/close/availability); overnight fixture added (Scenario 14); schema inventory added; 199 OTF tests + 1097 total pass. |

## Open questions

1. ~~What exact state-transition rule should define a broken OTF sequence?~~ **Resolved:** Sequence breaks when the qualifying condition is not met (lower low breaks up; equal or higher high breaks down). See `docs/otf-filter.md §3.6`.
2. ~~Should OTF state reset at every exchange session, or can it carry across sessions?~~ **Resolved:** Reset at every trading-session boundary using `trading_session_date()`. See `docs/otf-filter.md §3.10`.
3. ~~For each signal type, what is the precise decision timestamp?~~ **Resolved** for simple triggers and 3c in v1; see `docs/otf-filter.md §6.4`. Trade entry timestamp is after the OTF decision and does not affect it.
4. ~~Should insufficient history return `unknown` or `neutral`?~~ **Resolved:** `unknown`. See `docs/otf-filter.md §3.9`.
5. ~~Is equal source/target interval supported?~~ **Resolved:** Not supported in OTF v1; source must be strictly finer. PR 2 must validate. See `docs/otf-filter.md §5`.
6. ~~How should HTF bar timestamps be interpreted in pandas resampling output?~~ **Resolved:** Pandas left label = `bar_start_timestamp`; `bar_close_timestamp = bar_start_timestamp + timeframe_duration`; `availability_timestamp = bar_close_timestamp`. Row label is NOT the availability timestamp. See `docs/otf-filter.md §6.1`.
7. Should the first release support only source intervals at or below 5 minutes? **Deferred to PR 2.**
8. Should 5m OTF be treated as a regime filter, an entry confirmation, or both? **Deferred to Phase 6 (UI controls).**
9. Which report artifact should become the authoritative record of OTF configuration? **Deferred to Phase 8 (reporting).**
10. How should partial first buckets of a trading session be handled in resampling? **Deferred to PR 2.** The lookahead fixture uses bars starting on a clean bucket boundary; production alignment needs to be specified in PR 2.

## Change log

| Date | Change |
|---|---|
| 2026-07-23 | Initial roadmap created. |
| 2026-07-23 | PR 1: OTF v1 contract approved; `docs/otf-filter.md` created; deterministic OHLCV fixtures added; contract and baseline tests added; Phase 0 and Phase 1 marked complete. |
| 2026-07-23 | PR 1 follow-up: Corrected futures-session boundary semantics; added bar_start/bar_close/availability timestamp definitions; added overnight session fixture (Scenario 14); added schema inventory to Phase 0; updated Phase 0 status to "Partially complete"; resolved open questions 2, 5, 6; updated test evidence to 199 OTF tests / 1097 total. |
