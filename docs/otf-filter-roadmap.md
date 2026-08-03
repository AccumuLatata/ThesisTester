# OTF Filter Implementation Roadmap

**Project:** ThesisTester  
**Status:** Hardening PR 1–3 merged; hardening PR 4 (`otf_history_policy`) implemented; PR 6 real-dataset OOS/drift/release gate still open  
**Owner:** ThesisTester engineering  
**Last updated:** 2026-08-03  
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
- [x] Pure OTF calculation engine implemented (`thesistester/engine/otf.py`)
- [x] Look-ahead protections tested against production engine
- [x] Signal eligibility integration implemented
- [x] Setup persistence and compatibility implemented
- [x] UI controls implemented
- [x] Backtest, grid-search, and walk-forward integration completed
- [x] Reporting and export completed
- [x] Documentation completed
- [x] Statistical validation diagnostic tooling implemented (see Phase 10)
- [x] Futures-session `eth_start` propagation parity across Streamlit Backtest, Grid, validation matrix, API, and WFO summaries (hardening PR 1; see `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md`)
- [x] UI/docs honesty: no stale pre-PR-5 “metadata only” copy; README/ARCHITECTURE/ASSUMPTIONS/METRICS/PIT describe live OTF composition (hardening PR 2)
- [x] Enabled-OTF additive golden / drift gate with overnight ETH fixture, future-shock tests, and legacy isolation (hardening PR 3)
- [x] Opt-in WFO `otf_history_policy` (`fold_local` default / `causal_prefix`) with API/UI/assistant parity (hardening PR 4)
- [ ] Out-of-sample validation on a real user dataset (PR 6 DoD)
- [ ] Regression and drift-safety review sign-off (PR 6 DoD)
- [ ] Release approved (pending real user dataset validation)

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
- Focused OTF verification: **223 passed** (`python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q`)
- Full-suite regression verification: **1106 passed** (`python3 -m pytest tests/ -q`)
- Baseline fixture file: `tests/fixtures/otf_fixtures.py`
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
- Focused verification command/result: `python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q` → **223 passed**
- Full-suite verification command/result: `python3 -m pytest tests/ -q` → **1106 passed**
- OHLCV fixture file: `tests/fixtures/otf_fixtures.py`
- Resample helper implementation: `thesistester/data/resample.py`
- Focused helper regression tests: `tests/test_loader.py`
- Related PR: PR 1 — OTF specification and deterministic fixtures

### PR 2 prerequisites carried forward

- The production OTF engine must apply the verified availability contract: `bar_close_timestamp <= signal_decision_timestamp`.
- Future-shock / append-data invariance must be tested against the real OTF engine.
- Partial first session-boundary bucket handling remains a deliberate implementation decision.

## Phase 2 — Build the pure OTF engine

**Status:** Complete (finalized in PR #79 against `main`; PR #78 superseded)

### Target files

- `thesistester/engine/otf.py` ✅ Created
- `tests/test_otf.py` ✅ Created

### Work items

- [x] Validate required OHLCV columns.
- [x] Validate timestamps and timezone handling.
- [x] Implement 5m, 15m, and 30m resampling (via `resample_ohlcv()`).
- [x] Implement completed-bar alignment using source-bar close timestamps and complete source coverage.
- [x] Implement OTF state calculation.
- [x] Implement sequence length and reference timestamp outputs.
- [x] Implement session-reset behavior.
- [x] Expose a stable public API.
- [x] Add module-level documentation.

### Implemented API

```python
calculate_otf_state(
    df: pd.DataFrame,
    timeframe: str,
    *,
    minimum_consecutive_bars: int = 3,
    session_timezone: str | None = None,
    eth_start: str | None = None,
    session_reset: str = "session",
) -> pd.DataFrame
```

- Canonical public timeframe labels: `5m`, `15m`, `30m`
- Backward-compatible aliases: `5min`, `15min`, `30min`
- Internal normalization before resampling:

```python
{
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
}
```

### Output fields (complete)

```text
bar_start_timestamp       — pandas left-label of the resampled HTF bucket
bar_close_timestamp       — bar_start + timeframe_duration
availability_timestamp    — equal to bar_close_timestamp
open, high, low, close, volume  — aggregated OHLCV of the completed HTF bar
trading_session_date      — date label from trading_session_date()
otf_state                 — "up" | "down" | "neutral" | "unknown"
otf_sequence_length       — active directional run length (0 for neutral/unknown)
up_run                    — consecutive higher-low counter
down_run                  — consecutive lower-high counter
otf_reference_timestamp   — bar_close_timestamp of the previous bar (NaT for first bar)
```

### Partial first session-bucket policy (decision)

**Decision:** Discard any HTF bar whose `bar_start_timestamp` is strictly earlier than the first source bar's timestamp within that trading session.

**Rationale:** This is the most conservative, research-safe policy. A partial first bucket contains OHLCV values that do not represent a full period and may bias high/low comparisons. Discarding it ensures only complete bars contribute to OTF state calculations.

**Implementation:** `_discard_partial_first_buckets()` in `thesistester/engine/otf.py`.

**Example:** If the session opens at 09:31 ET and the 09:30 5m bucket has started before the first source bar, that bucket is discarded. The first usable HTF bar is the one whose `bar_start_timestamp >= 09:31`.

### Source-bar completion and bucket-coverage policy

- Source rows are **start-labelled** bars.
- `source_bar_close_timestamp = source_bar_start_timestamp + inferred_source_interval`
- `latest_source_availability_timestamp = max(source_bar_close_timestamp)`
- An HTF bucket is retained only when:
  - `bar_close_timestamp <= latest_source_availability_timestamp`
  - the first expected source row is present
  - the final expected source row is present
  - source timestamps are continuous at the inferred interval
  - the expected source-row count is present (`target_duration / source_interval`)
- The target timeframe must be exactly divisible by the inferred source interval.
- Equal or coarser source intervals are rejected.
- Irregular timestamps that prevent trustworthy interval inference are rejected.
- No next-bucket sentinel row is required; the last required source row completes the HTF bucket.
- DST-safe bucket identity uses the actual timezone-aware resampler labels. Repeated
  fall-back wall-clock times retain distinct UTC offsets and are not merged;
  spring-forward nonexistent local times are not fabricated.

### Look-ahead safety guarantees

1. **In-progress bars excluded:** After resampling, bars whose `bar_close_timestamp` exceeds the latest source-bar availability or lack full expected source coverage are removed before any state computation.

2. **Append-data invariance:** Historical output rows with `availability_timestamp <= T` are unchanged when data after `T` is appended. Proven by `TestLookaheadSafety::test_appending_bars_does_not_change_complete_historical_rows`.

3. **Future-shock invariance:** `TestLookaheadSafety::test_future_highs_lows_do_not_alter_historical_rows` confirms extreme future bar values do not alter prior completed rows.

4. **Exact-close availability:** A bar whose `bar_close_timestamp` equals the latest source-bar availability is included in the output (§6.3). Proven by `TestLookaheadSafety::test_bar_available_exactly_at_close_timestamp`.

5. **Session-boundary counter isolation:** Prior-session `up_run`/`down_run` counters cannot appear in the new session. Proven by `TestLookaheadSafety::test_session_boundary_reset_does_not_leak_prior_counters`.

### Acceptance criteria

- [x] The engine is independent of Streamlit pages.
- [x] The engine is deterministic.
- [x] The engine does not mutate caller-owned data.
- [x] Unit tests cover normal and invalid input, canonical/alias timeframes, completion boundaries, gap handling, and deterministic OHLCV validation (`tests/test_otf.py`).

## Phase 3 — Prove look-ahead safety

**Status:** Complete (merged into final PR #79 against `main`; PR #78 superseded)

Look-ahead and drift safety tests are implemented in `tests/test_otf.py::TestLookaheadSafety` and run against the production engine.

### Work items

- [x] Test that unfinished 5m bars cannot affect earlier signals.
- [x] Test that unfinished 15m bars cannot affect earlier signals.
- [x] Test that unfinished 30m bars cannot affect earlier signals.
- [x] Test that future highs, lows, and closes do not alter prior completed rows.
- [x] Test that appending bars after timestamp `T` does not change completed OTF outputs at or before `T`.
- [x] Test session-boundary behavior.
- [x] Test timezone-aware and timezone-naive inputs.
- [x] Test resampling boundaries for the supported source intervals.
- [x] Test exact-close completion without sentinel rows.
- [x] Test missing-source-coverage bucket exclusion.
- [x] Test spring-forward DST completion and append-data invariance.
- [x] Test fall-back repeated-hour separation and append-data invariance.

### Acceptance criteria

The following property holds:

```text
Completed OTF output rows with availability_timestamp <= T are unchanged when data after T is appended.
```

Proven by `tests/test_otf.py::TestLookaheadSafety::test_appending_bars_does_not_change_complete_historical_rows`.

## Phase 4 — Integrate at signal eligibility

**Status:** Partially complete (PR 3 pure filter layer complete; orchestration wiring deferred)

### Target areas (PR 3 scope)

- Pure post-generation eligibility filtering module.
- Signal context and metadata for accepted/rejected outputs.
- Disabled-path regression safety.
- Deterministic point-in-time OTF alignment.

### Work items

- [x] Implement `apply_otf_filter` using the shared OTF engine.
- [x] Keep `simulate_trades` focused on execution rather than regime calculation.
- [x] Preserve all original signal columns and `signal_id` values.
- [x] Preserve OTF-rejected signals separately from accepted rows.
- [x] Add deterministic rejection reasons in selected-timeframe order.
- [x] Keep OTF rejection distinct from execution skips and 3c void semantics.
- [x] Verify disabled filtering returns the legacy signal population and does not call the OTF engine.
### Phase 4 work items (PR 3 follow-up)

- [x] Harden disabled mode to be a true no-op: validates only `enabled` is bool, skips all other validation.
- [x] Add stable enabled-empty-signals path: returns correct schema without calling OTF engine.
- [x] Centralize timeframe normalization in `normalize_otf_timeframe()` in `thesistester/engine/otf.py`.
- [x] Remove duplicate `_TIMEFRAME_ALIASES` mapping from `otf_filter.py`.
- [x] Export `normalize_otf_timeframe` from `thesistester.engine`.
- [x] Add focused regression tests for disabled no-op, enabled-empty, and normalization.
- [ ] Wire default app/page/research orchestration to consume accepted-signal output (deferred).

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

### Acceptance criteria (PR 3)

- Long and short filtering is directionally correct.
- Neutral and unknown states are handled explicitly.
- Rejected signals are inspectable.
- Existing backtest execution behavior remains unchanged because no default orchestration wiring is added in PR 3.

## Phase 5 — Add persistence and versioning

*Status:* Partially complete

**Implementation Notes:**
* Setup identity complete.
* Signal-settings identity complete.
* Research-artifact fingerprint integration deferred to PR 5.
* Reporting/export identity deferred to PR 5.
* No execution or research-mode integration in PR 4.
  
### Work items

- [x] Add an optional `otf_filter` block to setup configuration.
- [x] Define backward-compatible defaults for legacy setups.
- [x] Add configuration validation.
- [x] Add OTF algorithm version metadata (`OTF_ALGORITHM_VERSION = 1`).
- [x] Add OTF configuration hashing (`compute_otf_config_hash`).
- [x] Include OTF identity in setup fingerprints.
- [x] Include OTF identity in signal-settings fingerprints.
- [x] Test save/load round trips.
- [x] Test loading setups created before OTF support.
- [x] Keep setup schema version unchanged (`SETUP_SCHEMA_VERSION = 1`); no migration required because `otf_filter` is optional and legacy-absent payloads are supported.
- [x] Enforce strict invalid-config identity: invalid explicit OTF config raises `ValueError`; only absent/null resolves to disabled defaults.
- [x] Include OTF identity in final research artifacts, reports, grid results, walk-forward results, and exports. (Complete in PR 5.)
- [x] Reporting and export identity integration. (Complete in PR 5.)

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
- Explicit invalid OTF configuration is rejected and never silently hashed as disabled.
- Missing legacy configuration alone resolves to disabled defaults.
- Research-artifact fingerprint integration is complete in PR 5.

## Phase 6 — UI configuration controls

*Status:* Partially complete

### Work items

- [x] Add Setup Builder OTF configuration section (saved setup metadata path).
- [x] Add enable/disable control.
- [x] Add 5m, 15m, and 30m timeframe selection.
- [x] Add alignment-mode control fixed to `all`.
- [x] Add minimum sequence length.
- [x] Add session-reset policy fixed to `session`.
- [x] Add clear completed-bar/look-ahead explanation.
- [x] Validate enabled filters with no selected timeframe.
- [x] Display metadata status on Signals page with explicit non-integration boundary.

### Acceptance criteria

- The UI cannot create invalid OTF configurations.
- Disabled is the default for existing and new workflows unless deliberately changed.
- The displayed configuration matches the configuration used by the engine.

## Phase 7 — Integrate all research modes

**Status:** Complete (PR 5, hardened in PR 5 follow-up)

### Work items

- [x] Standard backtest uses the filtered signal set.
- [x] SL/TP grid search uses the same filtered signal set for every risk combination.
- [x] Walk-forward uses only information available within each fold (fold-local OTF filtering).
- [x] OTF configuration remains fixed across folds (no per-fold optimization).
- [x] Future research modes consume the shared filter output via `apply_configured_otf_filter()`.
- [x] Add integration tests for each mode (`tests/test_otf_integration.py`).
- [x] Walk-forward fold-local OTF handles insufficient fold-local history by rejecting all fold candidates as `unknown`, not by crashing or using full-dataset OTF state.
- [x] Walk-forward page catches invalid explicit OTF config with a clear error before running or installing results.

### Acceptance criteria

- [x] No duplicate OTF implementations exist.
- [x] Grid-search comparisons use identical eligible signals.
- [x] Walk-forward evaluation contains no OTF leakage from future folds.
- [x] Short folds with insufficient OTF history are handled deterministically (all candidates rejected as unknown).

### Implementation Notes

* Shared integration helper: `thesistester/engine/otf_integration.py`.
* `apply_configured_otf_filter()` resolves config from session context and applies `apply_otf_filter()` once.
* Config resolution precedence documented in `docs/otf-filter.md §13b`.
* Backtest, grid search, walk-forward pages updated.
* Session state keys: `otf_filter_result`, `otf_filter_summary`, `otf_candidate_signals`, `otf_accepted_signals`, `otf_rejected_signals`, `backtest_otf_filter`, `grid_otf_filter`, `walk_forward_otf_filter`.
* Walk-forward fold-local OTF: `train_df` used as source for train signals, `test_df` for test signals.
* `_filter_fold_signals_with_otf()` private helper in `walk_forward.py` handles insufficient fold history by catching `ValueError` against `_EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS` and rejecting all candidates as unknown. Unknown `ValueError` instances are re-raised. Invalid config raises before reaching the helper via pre-fold `normalize_otf_filter_config()` call.
* OTF fold metadata columns added to `_RESULT_COLUMNS` in `walk_forward.py`.

## Phase 8 — Reporting and exports

**Status:** Complete (PR 5, hardened in PR 5 follow-up)

### Work items

- [x] Display candidate signal count.
- [x] Display OTF-passed signal count.
- [x] Display OTF-rejected signal count.
- [x] Display rejection percentage.
- [x] Display the active OTF configuration.
- [x] Add rejected-signal table or export.
- [x] Include OTF algorithm version and configuration hash in research artifacts.
- [x] Distinguish disabled filtering from zero-pass filtering.
- [x] Render `None` counts as `—` instead of `"None"` when partial metadata is available (e.g., only walk-forward OTF data present).
- [x] Preserve zero counts as `0`, not `—`.

### Acceptance criteria

A user can determine exactly:

- [x] Whether OTF was enabled.
- [x] Which timeframes were used.
- [x] Which algorithm version was used.
- [x] How many signals were rejected and why.
- [x] Partial metadata (e.g., only walk-forward scope ran) renders unavailable counts as `—`, not `None`.

### Implementation Notes

* `build_otf_filter_metadata()` added to `thesistester/reporting.py`.
* `_dash_if_none()` helper added to `thesistester/reporting.py`; used by `_otf_markdown_section()` and imported by `pages/11_Report_Export.py`.
* `build_research_artifact()` includes an `"otf_filter"` section and `"otf_rejected_signals"` table.
* `build_markdown_report()` includes an OTF summary section via `_otf_markdown_section()`.
* Report/Export page (`pages/11_Report_Export.py`) adds OTF checklist and rejected-signal CSV download.
* Four distinct artifact states: OTF available+enabled, available+disabled, unavailable.
* OTF rejections remain distinct from exposure-policy skips and 3c void status.

## Phase 9 — Documentation

**Status:** In progress (PR 1 delivers initial documentation; PR 5 updates)

### Work items

- [x] Create this living roadmap.
- [x] Document the OTF definition.
- [x] Document state transitions and sequence breaks.
- [x] Document resampling and completed-bar rules.
- [x] Document session and timezone policy.
- [x] Document configuration examples.
- [x] Document rejected-signal interpretation.
- [x] Document walk-forward treatment.
- [x] Document algorithm versioning and drift controls.
- [x] Document PR 5 research-mode integration in `docs/otf-filter.md §13b`.
- [ ] Update `README.md` and relevant methodology documentation.

### Recommended documentation files

- `docs/otf-filter-roadmap.md` — this implementation tracker.
- `docs/otf-filter.md` — user-facing methodology and behavior.
- `docs/research-methodology.md` — impact on research validity and walk-forward analysis.

## Phase 10 — Statistical validation and release gate

**Status:** Partially complete (PR 6) — diagnostic matrix tooling implemented; real-dataset OOS confirmation, drift-review sign-off, and release approval remain open.

### Comparison matrix

- [x] No OTF filter.
- [x] 15m only.
- [x] 30m only.
- [x] 15m + 30m.
- [x] 5m + 15m + 30m.

### Metrics (implemented)

- [x] Trade count (train and OOS separately).
- [x] Expectancy per trade (train and OOS).
- [x] Total R (train and OOS).
- [x] Average R (train and OOS).
- [x] Profit factor (train and OOS).
- [x] Maximum drawdown (train and OOS).
- [x] Win rate (train and OOS).
- [x] Long/short trade count (train and OOS).
- [x] Rejection rate and delta vs no_otf baseline.
- [x] OOS expectancy delta vs no_otf baseline.

### Metrics (deferred — use existing Time Analysis / trade diagnostics)

- [ ] Session and time-of-day performance (use Phase 7 time analysis on accepted trades).
- [ ] Time in market.
- [ ] Full long/short performance beyond trade counts.

### Validation rules

- [x] Chronological train/OOS split (default 70/30).  No shuffling.
- [x] Train metrics only used for ranking/selection (train_rank, is_train_selected).
- [x] OOS metrics provided for evaluation only; never influence selection.
- [x] Configuration selection explicitly labeled (selected_by_train_metric).
- [x] UI, report, and artifact include multiple caveats.
- [x] No configuration automatically selected for production use.
- [ ] Confirm improvements across multiple market periods (requires real user dataset).
- [ ] Confirm results are not caused only by lower trade frequency (user must assess per dataset).

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

**Status:** Complete (final verified documentation state)

- [x] Documentation and state-transition contract (`docs/otf-filter.md`).
- [x] Deterministic OTF fixtures (`tests/fixtures/otf_fixtures.py`) with 11 OHLCV scenarios + 3 vector scenarios.
- [x] Baseline regression tests (`tests/test_otf_baseline.py`).
- [x] Contract integrity and vector tests (`tests/test_otf_contract.py`).
- [x] Updated roadmap (`docs/otf-filter-roadmap.md`).
- [x] No production behavior change.
- [x] Phase 0 remains partially complete; Phase 1 is complete.
- [x] Futures trading-session boundary corrected (eth_start convention; midnight is NOT a boundary).
- [x] HTF bar timestamp/availability semantics clarified (bar_start vs bar_close vs availability).
- [x] Overnight futures-session fixture added (Scenario 14).
- [x] Look-ahead fixture updated with explicit start/close/availability timestamps.
- [x] Schema inventory added to Phase 0 evidence.
- [x] Partial first session-bucket handling remains deferred to PR 2.
- [x] Production-engine future-shock and append-data invariance tests remain deferred to PR 2.

**Test evidence (final verified state):**

```
python3 -m pytest tests/test_loader.py tests/test_otf_contract.py tests/test_otf_baseline.py -q
# 223 passed

python3 -m pytest tests/ -q
# 1106 passed
```

**Regression statement:**

Production OTF behavior is not implemented in PR 1.
Existing application behavior is unchanged.
No production files outside `docs/` and `tests/` were modified.

### PR 2 — Pure OTF engine

- `thesistester/engine/otf.py`.
- Unit tests.
- Look-ahead tests.
- Feature remains unused by default.

**PR 2 verified evidence:**

```text
python3 -m pytest tests/test_otf.py tests/test_otf_contract.py tests/test_otf_baseline.py tests/test_loader.py -q
# 354 passed in 3.83s

python3 -m pytest tests/ -q
# 1237 passed in 29.26s
```

### PR 3 — Signal filtering

- `thesistester/engine/otf_filter.py` pure eligibility filter module.
- `tests/test_otf_filter.py` focused validation/alignment/regression coverage.
- Optional engine package export via `thesistester/engine/__init__.py`.
- No Streamlit/persistence/backtest-page/grid/walk-forward/report wiring.

**PR 3 verified evidence:**

```text
python3 -m pytest tests/test_otf_filter.py tests/test_otf.py tests/test_otf_contract.py tests/test_otf_baseline.py tests/test_loader.py -q
# 430 passed in 5.38s

python3 -m pytest tests/ -q
# 1313 passed in 30.69s
```

### PR 4 — Persistence and UI

- Setup configuration.
- Backward-compatible loading.
- Versioning and hashing.
- User controls and validation.

**PR 4 implementation files (narrow scope):**

- `thesistester/setup.py`
- `thesistester/persistence/local_store.py`
- `thesistester/persistence/__init__.py`
- `thesistester/engine/otf.py` (algorithm version constant only)
- `pages/2_Setup_Builder.py`
- `pages/6_Signals.py`
- `tests/test_setup_config.py`
- `tests/test_local_store.py`
- `tests/test_setup_builder_helpers.py`
- `tests/test_signals_page_helpers.py`
- `docs/otf-filter.md`
- `docs/otf-filter-roadmap.md`

**PR 4 decisions:**

- Setup schema version unchanged (`SETUP_SCHEMA_VERSION = 1`) because OTF is an optional backward-compatible field.
- Legacy setups without `otf_filter` continue loading and resolve to canonical disabled effective defaults.
- OTF identity hash includes normalized `otf_filter` and `OTF_ALGORITHM_VERSION`.
- Timeframe order is preserved in enabled config/hash identity.
- Signals page messaging explicitly states PR 4 metadata-only boundary (no execution filtering yet).

**PR 4 verified evidence:**

```text
python3 -m pytest tests/test_setup_config.py tests/test_local_store.py tests/test_setup_builder_helpers.py tests/test_signals_page_helpers.py -q
# 193 passed

python3 -m pytest tests/test_otf_filter.py tests/test_otf.py tests/test_otf_contract.py tests/test_otf_baseline.py -q
# 407 passed

python3 -m pytest tests/ -q
# 1369 passed
```

### PR 5 — Research integration and reporting

- Backtest integration.
- Grid-search integration.
- Walk-forward fold-local OTF integration.
- Reporting and export metadata.

**PR 5 implementation files (narrow scope):**

- `thesistester/engine/otf_integration.py` (new)
- `thesistester/engine/__init__.py` (exports)
- `thesistester/analytics/walk_forward.py` (fold-local OTF)
- `thesistester/reporting.py` (OTF metadata)
- `pages/7_Backtest.py` (OTF filter before `simulate_trades`)
- `pages/8_Grid_Search.py` (OTF filter before grid)
- `pages/10_Validation.py` (OTF config forwarded to walk-forward)
- `pages/11_Report_Export.py` (OTF checklist + rejected-signal export)
- `tests/test_otf_integration.py` (76 integration tests)
- `docs/otf-filter.md`
- `docs/otf-filter-roadmap.md`

**PR 5 decisions:**

- One shared integration helper (`apply_configured_otf_filter`) centralizes filter application; pages do not duplicate OTF logic.
- OTF config resolution precedence: signal_settings["otf_filter"] > signal_settings["setup_snapshot"] > last_signal_setup > setup_config > disabled defaults.
- `st.session_state["signals"]` never overwritten; candidate signals always preserved.
- Walk-forward applies OTF per-fold using the fold's own OHLCV slice to prevent future state leakage.
- Grid applies OTF once before the SL/TP grid; all cells use the same accepted signal set.
- OTF rejections kept distinct from exposure-policy skips and 3c void status.
- Disabled path: `simulate_trades()`, grid, and walk-forward receive exactly the same signals as before PR 5.

**PR 5 follow-up hardening decisions:**

- `OtfFilterResult` is now `frozen=True`; attribute reassignment raises `FrozenInstanceError`. DataFrame attributes remain internally mutable, but slot references are frozen.
- Unused `field` import removed from `otf_integration.py`.
- `pages/10_Validation.py`: `resolve_otf_config()` moved inside the `try` block. Invalid explicit OTF config shows `"OTF filter configuration error: <details>"` and does not install stale walk-forward results. Walk-forward execution errors continue to show `"Walk-forward diagnostics error: <details>"`.
- `walk_forward.py`: `_filter_fold_signals_with_otf()` private helper added. Fold-local OTF with insufficient source history (< 2 bars) catches `ValueError` and rejects all fold candidates as OTF `unknown`. Only expected OTF interval/insufficiency errors are caught; programming errors propagate. Invalid config `ValueError` propagates before reaching the helper.
- `reporting.py`: `_dash_if_none()` helper added. `_otf_markdown_section()` uses it to render `None` as `—` for algorithm version, counts, and config hash. Zero counts render as `0`.
- `pages/11_Report_Export.py`: OTF caption uses `_dash_if_none()` for accepted/rejected/candidate counts. Partial metadata (e.g., only walk-forward OTF data) renders as `—` instead of `None`.

**PR 5 final fix decisions (strict walk-forward OTF config validation):**

- `run_walk_forward_sl_tp()` calls `normalize_otf_filter_config()` before the fold loop. Invalid explicit OTF config (e.g. `enabled=True` with no timeframes, unsupported timeframe label) raises `ValueError` immediately; no fold results are produced and no silent fallback occurs.
- `_filter_fold_signals_with_otf()` now catches `ValueError` only when `str(exc)` contains a pattern from `_EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS`. Unknown `ValueError` instances are re-raised to prevent silent swallowing of programming errors or data integrity failures.
- Invalid config is never silently converted into rejected fold signals — it always raises before fold processing begins.

**PR 5 verified evidence (after final fix):**

```text
python3 -m pytest tests/test_otf_integration.py tests/test_otf_filter.py tests/test_otf.py tests/test_setup_config.py tests/test_walk_forward.py tests/test_phase9_reporting.py -q
# 387 passed

python3 -m pytest tests/test_otf_integration.py -q
# 83 passed (61 original + 15 follow-up + 7 final fix)

python3 -m pytest tests/ -q
# 1477 passed in 31.90s
```

*Note: `test_local_store.py` failures are pre-existing missing-dependency failures (pyarrow/fastparquet) unrelated to OTF.*

### PR 6 — Validation and release

- Statistical comparison matrix (diagnostic tooling).
- Documentation completion (methodology + release-gate criteria).
- Drift review sign-off (still open — prior look-ahead/regression tests exist; formal PR 6 review not closed).
- Release approval with the feature disabled by default (still open — pending real user dataset).

## Definition of done

- [x] Existing users see no behavior change unless OTF is enabled.
- [x] OTF uses completed bars only.
- [x] Historical OTF states are invariant when future data is appended.
- [x] OTF-rejected signals are inspectable.
- [x] One shared implementation is used across all research modes.
- [x] OTF configuration is persisted and fingerprinted.
- [x] Legacy saved setups load successfully.
- [x] Reports identify the complete OTF configuration and algorithm version.
- [x] Documentation describes the exact methodology.
- [ ] Out-of-sample validation is complete. (PR 6)
- [ ] Regression and drift-safety reviews are complete. (PR 6)

## Progress log

| Date | Phase / change | Evidence or link | Notes |
|---|---|---|---|
| 2026-07-23 | Roadmap created | _This document_ | Initial regression-safe and drift-safe plan. |
| 2026-07-23 | Phase 0 partially complete | `tests/test_otf_baseline.py`, `docs/otf-filter-roadmap.md` | Baseline captured; schema inventory recorded; final verification shows 223 focused tests and 1106 full-suite tests passing; report-artifact schema remains deferred. |
| 2026-07-23 | Phase 1 complete | `docs/otf-filter.md`, `tests/fixtures/otf_fixtures.py`, `tests/test_otf_contract.py` | OTF v1 contract approved; 11 OHLCV scenarios + 3 vector scenarios; direct resampler drift guard added; final verification shows 223 focused tests and 1106 full-suite tests passing. |
| 2026-07-24 | Phase 2 complete in final PR #79 against `main` | `thesistester/engine/otf.py`, `tests/test_otf.py`, `docs/otf-filter.md`, `docs/otf-filter-roadmap.md` | Pure OTF engine finalized in PR #79; PR #78 is superseded and must not be merged. Canonical public timeframe labels (`5m`/`15m`/`30m`), internal `*min` normalization, source-bar close semantics, complete-source-coverage filtering, deterministic OHLCV validation, DST-safe bucket assignment using actual timezone-aware resampler labels, and no-sentinel completion are all implemented. Focused verification: 354 passed in 3.83s. Full suite: 1237 passed in 29.26s. |
| 2026-07-24 | Phase 3 complete (merged into final PR #79) | `tests/test_otf.py::TestLookaheadSafety` | 5m/15m/30m in-progress bar exclusion proven under source-bar close semantics; append-data invariance compares full historical output rows; future-shock invariance, new-session invariance, exact-close availability, missing-coverage exclusion, session-boundary counter isolation, and DST spring-forward/fall-back invariance are all proven against the production engine. |
| 2026-07-24 | Phase 4 partially complete (PR 3 pure layer) | `thesistester/engine/otf_filter.py`, `tests/test_otf_filter.py`, `docs/otf-filter.md`, `docs/otf-filter-roadmap.md` | Added pure `apply_otf_filter()` eligibility layer with deterministic config validation, decision-timestamp selection (`trigger_timestamp` fallback to `timestamp`), causal as-of alignment via `availability_timestamp <= decision_timestamp`, accepted/rejected output split, deterministic rejection reasons, and disabled-path no-engine-call regression guard. Focused verification: 400 passed in 3.67s. Full suite: 1283 passed in 21.95s. No Streamlit/persistence/backtest wiring added. |
| 2026-07-24 | Phase 4 follow-up: disabled no-op hardening, enabled-empty-signals path, centralized timeframe normalization | `thesistester/engine/otf.py`, `thesistester/engine/otf_filter.py`, `thesistester/engine/__init__.py`, `tests/test_otf_filter.py`, `docs/otf-filter.md`, `docs/otf-filter-roadmap.md` | Disabled mode now short-circuits immediately after validating `enabled` is bool; all other config/signal/timestamp/source validation is skipped. Enabled mode with empty signals returns stable empty accepted/rejected schemas without calling OTF engine. Added `normalize_otf_timeframe()` as the single authoritative normalization helper in `otf.py`; removed duplicate alias mapping from `otf_filter.py`. Exported `normalize_otf_timeframe` from `thesistester.engine`. Focused verification: 430 passed in 5.38s. Full suite: 1313 passed in 30.69s. |
| 2026-07-24 | Phase 5 partially complete + Phase 6 partial (PR 4) | `thesistester/setup.py`, `thesistester/persistence/local_store.py`, `pages/2_Setup_Builder.py`, `pages/6_Signals.py`, related tests/docs | Added canonical OTF setup config normalization/validation/effective helper, backward-compatible setup save/load handling without schema bump, OTF algorithm/version hash metadata, setup/signal identity inclusion, Setup Builder OTF controls with deterministic hydration, and explicit Signals metadata-only messaging (no execution integration yet). Phase 5 research-artifact identity deferred to PR 5. Initial verification (pre-follow-up): 170 targeted tests, 407 focused OTF tests, 1346 full-suite tests passing. |
| 2026-07-24 | PR 4 follow-up: hardened invalid-OTF UI state; strict hash identity preserved | `pages/6_Signals.py`, `pages/2_Setup_Builder.py`, `tests/test_signals_page_helpers.py`, `tests/test_setup_builder_helpers.py`, `tests/test_local_store.py`, `docs/otf-filter-roadmap.md`, `docs/otf-filter.md` | Strict hashing: `compute_signal_settings_hash` raises on invalid explicit OTF; missing OTF resolves to disabled defaults; no silent fallback. Signals page: `_try_normalize_signal_settings_for_hash` wrapper at all UI call sites; signal generation/comparison/save blocked on invalid OTF identity. Setup Builder: `_resolve_otf_for_ui` pure helper for editor seeding and summary rendering; malformed OTF hydrates disabled defaults with explicit warning; caller dicts never mutated. Phase 5 marked partially complete; research-artifact identity deferred. Post-follow-up intermediate verification: 193 targeted tests + 407 OTF-focused tests; full suite: 1369 passed. |
| 2026-07-24 | PR 4 final fix: atomic saved-run identity transitions; shared save-path eligibility helper | `pages/6_Signals.py`, `tests/test_signals_page_helpers.py`, `docs/otf-filter-roadmap.md` | Added `_resolve_loaded_signal_identity` pure helper: validates settings and persisted hash before touching session state; computes and verifies hash from normalized settings; returns trusted/invalid/unavailable status. Added `_validate_signal_artifact_identity_for_save` shared helper: enforces trusted status + hash integrity + current-controls match for both "Save current signals" paths. Load path: artifacts always installed for inspection; settings/hash atomically cleared when identity is untrusted; `signal_artifact_identity_status` set to trusted/invalid/unavailable. Generation path: sets trusted identity + clears error on success. Save paths: consolidated to single shared helper; no fallback hash produced for invalid/unavailable artifacts. Final verification: 218 targeted tests + 407 OTF-focused tests; full suite: 1394 passed in 30.36s. |
| 2026-07-25 | Phase 7 and Phase 8 complete (PR 5) | `thesistester/engine/otf_integration.py`, `thesistester/analytics/walk_forward.py`, `thesistester/reporting.py`, `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/10_Validation.py`, `pages/11_Report_Export.py`, `tests/test_otf_integration.py`, `docs/otf-filter.md §13b`, `docs/otf-filter-roadmap.md` | Added shared `apply_configured_otf_filter()` integration helper with `OtfFilterResult` dataclass and `resolve_otf_config()` (precedence-based). Standard backtest filters before `simulate_trades()`; stores candidate/accepted/rejected in session state. Grid search applies OTF once before the SL/TP grid; all cells use the same accepted signal set. Walk-forward applies OTF per-fold using fold-local OHLCV slices (no future leakage). Reporting includes OTF metadata section and markdown summary; rejected signals available for CSV export. OTF rejections remain distinct from exposure-policy skips and 3c void. Disabled regression guarantee: exact legacy signals, trades, grid, and walk-forward output when OTF is off. Focused verification: 61 integration tests passed. Full suite: 1455 passed in 33.47s. |
| 2026-07-26 | PR 5 follow-up hardening (frozen dataclass, short-fold robustness, None formatting, page error handling) | `thesistester/engine/otf_integration.py`, `thesistester/analytics/walk_forward.py`, `thesistester/reporting.py`, `pages/10_Validation.py`, `pages/11_Report_Export.py`, `tests/test_otf_integration.py` | `OtfFilterResult` made `frozen=True`; unused `field` import removed; `_filter_fold_signals_with_otf()` helper added for short-fold robustness; `_dash_if_none()` helper added for None formatting; Validation page catches invalid OTF config with dedicated `try/except ValueError`. 76 integration tests (61 original + 15 follow-up) passed. Full suite: 1470 passed. |
| 2026-07-26 | PR 5 final fix — strict OTF config validation before walk-forward folds | `thesistester/analytics/walk_forward.py`, `tests/test_otf_integration.py`, `docs/otf-filter.md`, `docs/otf-filter-roadmap.md` | `run_walk_forward_sl_tp()` now calls `normalize_otf_filter_config()` before the fold loop; invalid explicit config (e.g. `enabled=True` with no timeframes, unsupported timeframe) raises `ValueError` immediately and no fold results are produced. `_filter_fold_signals_with_otf()` now catches `ValueError` only when the message matches `_EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS`; all other `ValueError` instances are re-raised. 7 new focused tests added (TestWalkForwardOtfConfigValidation; 83 integration tests total). Full suite: 1477 passed in 31.90s. |
| 2026-07-26 | Phase 10 partially complete (PR 6) — OTF statistical validation diagnostic tooling + release-gate docs | `thesistester/analytics/otf_validation.py`, `tests/test_otf_validation.py`, `pages/10_Validation.py`, `thesistester/reporting.py`, `pages/11_Report_Export.py`, `docs/otf-filter.md §15`, `docs/otf-filter-roadmap.md` | Added `run_otf_validation_matrix()` — fixed five-configuration matrix on chronological train/OOS split (default 70/30); train-only ranking; reporting/UI/docs. OTF remains disabled by default. DoD items for real-dataset OOS validation, drift-review sign-off, and release approval remain open. Session/time-of-day/time-in-market metrics deferred to existing Time Analysis diagnostics. |
| 2026-07-26 | PR 6 follow-up — train/OOS split identity fix + honest roadmap status | `thesistester/analytics/otf_validation.py`, `tests/test_otf_validation.py`, `thesistester/reporting.py`, `docs/otf-filter-roadmap.md`, `docs/otf-filter.md` | Fixed enabled-path train/OOS period assignment to use a stamped row-id column that survives `apply_otf_filter()` `reset_index`; added non-default-index regression test; strip reserved `execution_kwargs`; omit artifact/markdown OTF validation section when not run; corrected Phase 10 / PR 6 status overclaims. |
| 2026-08-03 | Hardening PR 1 — futures-session `eth_start` propagation parity | `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/10_Validation.py`, `thesistester/engine/otf_integration.py`, `thesistester/analytics/otf_validation.py`, `thesistester/reporting.py`, `tests/test_otf_integration.py`, `tests/test_otf_validation.py`, `tests/test_api.py`, `docs/otf-filter-roadmap.md` | Streamlit Backtest/Grid/OTF validation matrix now forward instrument `eth_start` (matching API/WFO). `OtfFilterResult` summaries, research OTF metadata, WFO OTF summary, and validation-matrix rows record effective `session_timezone`/`eth_start`. Intentional enabled-Streamlit overnight correction; disabled path unchanged. See `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md` §5. |
| 2026-08-03 | Hardening PR 2 — UI and documentation honesty | `pages/2_Setup_Builder.py`, `pages/6_Signals.py`, `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/METRICS_GLOSSARY.md`, `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/otf-filter.md`, `docs/otf-filter-roadmap.md`, `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md` | Removed stale “until PR 5 / metadata only” UI copy; documented live OTF composition, config provenance, eth_start/session limitations, OTF session_state keys, and glossary terms. No engine/filtering logic changes. See `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md` §6. |
| 2026-08-03 | Hardening PR 3 — enabled OTF golden / drift gate | `tests/fixtures/golden/generate_otf_enabled.py`, `pipeline_otf_enabled.py`, `record_otf_enabled_golden.py`, `otf_enabled_*` artifacts, `tests/test_otf_golden.py`, `.github/workflows/ci.yml`, `tests/fixtures/golden/README.md`, roadmaps | Additive overnight ETH enabled-OTF golden family with accepted/rejected/trade projections, future-shock tests, and legacy-isolation assertions. Legacy golden files unchanged. CI golden-guard narrowed to legacy artifact filenames. See `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md` §7. |
| 2026-08-03 | Hardening PR 4 — opt-in WFO `otf_history_policy` | `thesistester/analytics/walk_forward.py`, `thesistester/api.py`, `pages/10_Validation.py`, `pages/14_Research_Assistant.py`, assistant compiler/workspace/explainer/registry, reporting, docs, tests | Added `fold_local` (default) and `causal_prefix` OTF history policies for walk-forward; prefix∪fold-local source; PIT/future-shock coverage; API/UI/AI parity; policy recorded in WFO metadata. See `docs/OTF_HARDENING_AND_RELEASE_ROADMAP.md` §8. |
| 2026-08-03 | Hardening PR 4 follow-up — explainer/compiler policy honesty | `thesistester/assistant/explainer.py`, `thesistester/assistant/thesis_compiler.py`, tests | Explainer reads `walk_forward_summary.otf_history_policy` even when assumptions lack `walk_forward`; compiler delegates validation to `normalize_otf_history_policy`. |
| 2026-08-03 | Hardening PR 4 follow-up — WFA matrix policy parity | `thesistester/api.py`, `pages/10_Validation.py`, tests | API `run_wfa_matrix` now receives the same `otf_history_policy` as the primary WFO run; matrix config records the effective policy. |
| 2026-08-03 | Hardening PR 3 follow-up — signal bar_index/timestamp alignment | `tests/fixtures/golden/generate_otf_enabled.py`, `pipeline_otf_enabled.py`, `otf_enabled_*` artifacts, `tests/test_otf_golden.py` | Candidate `bar_index` now resolves to the dataset positional index of `timestamp` so OTF accept/reject decisions and next-bar trade entries stay aligned; goldens regenerated. |
| 2026-08-03 | Hardening PR 1 follow-up — WFO OTF timezone honesty | `thesistester/analytics/walk_forward.py`, `pages/10_Validation.py`, `tests/test_otf_integration.py` | Fold-level OTF uses `resolve_otf_session_timezone(session_timezone, exchange_timezone)` so omitted session-exit timezone falls back to exchange timezone; Validation `walk_forward_otf_filter` records that same resolved value. |

## Open questions

1. ~~What exact state-transition rule should define a broken OTF sequence?~~ **Resolved:** Sequence breaks when the qualifying condition is not met (lower low breaks up; equal or higher high breaks down). See `docs/otf-filter.md §3.6`.
2. ~~Should OTF state reset at every exchange session, or can it carry across sessions?~~ **Resolved:** Reset at every trading-session boundary using `trading_session_date()`. See `docs/otf-filter.md §3.10`.
3. ~~For each signal type, what is the precise decision timestamp?~~ **Resolved** for simple triggers and 3c in v1; see `docs/otf-filter.md §6.4`. Trade entry timestamp is after the OTF decision and does not affect it.
4. ~~Should insufficient history return `unknown` or `neutral`?~~ **Resolved:** `unknown`. See `docs/otf-filter.md §3.9`.
5. ~~Is equal source/target interval supported?~~ **Resolved:** Not supported in OTF v1; source must be strictly finer. PR 2 must validate. See `docs/otf-filter.md §5`.
6. ~~How should HTF bar timestamps be interpreted in pandas resampling output?~~ **Resolved:** Pandas left label = `bar_start_timestamp`; `bar_close_timestamp = bar_start_timestamp + timeframe_duration`; `availability_timestamp = bar_close_timestamp`. Row label is NOT the availability timestamp. See `docs/otf-filter.md §6.1`.
7. ~~Should the first release support only source intervals at or below 5 minutes?~~ **Resolved in PR 2.** The pure engine accepts any trustworthy source interval that is strictly finer than the target timeframe and divides it exactly; equal, coarser, non-divisible, or irregular inputs are rejected.
8. Should 5m OTF be treated as a regime filter, an entry confirmation, or both? **Deferred to Phase 6 (UI controls).**
9. Which report artifact should become the authoritative record of OTF configuration? **Deferred to Phase 8 (reporting).**
10. ~~How should partial first buckets of a trading session be handled in resampling?~~ **Resolved in PR 2.** Discard any HTF bar whose `bar_start_timestamp` is strictly earlier than the first source bar in that session. Implemented in `_discard_partial_first_buckets()` in `thesistester/engine/otf.py`.

## Change log

| Date | Change |
|---|---|
| 2026-07-23 | Initial roadmap created. |
| 2026-07-23 | PR 1: OTF v1 contract approved; `docs/otf-filter.md` created; deterministic fixtures added; contract and baseline tests added; final verified scope is documentation/tests only with production OTF still unimplemented. |
| 2026-07-24 | PR 2 pure OTF engine finalized in PR #79 against `main`; PR #78 superseded. Canonical public timeframe API aligned to `5m`/`15m`/`30m`; internal resampler normalization retained; source-bar start/close semantics and complete-source-coverage rule enforced; DST-safe resampler-label bucket assignment added; sentinel rows removed; focused verification: 354 passed in 3.83s; full suite: 1237 passed in 29.26s; no production behavior changes outside the pure engine/docs/tests scope. |
| 2026-07-24 | PR 3 pure OTF eligibility layer added: `thesistester/engine/otf_filter.py` and `tests/test_otf_filter.py`. Filter is deterministic, preserves candidate signals, splits accepted/rejected outputs, uses decision timestamp selection (`trigger_timestamp` then `timestamp`), applies causal as-of alignment (`availability_timestamp <= decision_timestamp`), adds deterministic rejection reasons, and guarantees disabled-path no-engine-call behavior. Focused verification: 400 passed in 3.67s; full suite: 1283 passed in 21.95s. Integration into Streamlit pages/persistence/backtests/grid-search/walk-forward/reporting remains deferred. |
| 2026-07-24 | PR 3 follow-up: disabled-path hardened to true no-op (validates only `enabled` bool); enabled-empty-signals returns stable empty schemas without OTF engine call; `normalize_otf_timeframe()` added as single authoritative normalization helper in `otf.py`, duplicate alias mapping removed from `otf_filter.py`; helper exported from `thesistester.engine`. Focused verification: 430 passed in 5.38s; full suite: 1313 passed in 30.69s. |
| 2026-07-24 | PR 4 configuration/persistence/versioning/UI metadata layer | Canonical OTF setup + identity work in setup/persistence/UI/test/docs files | Added canonical `otf_filter` model (`normalize_otf_filter_config`, `validate_otf_filter_config`, `get_effective_otf_filter_config`), setup persistence/load compatibility without schema bump, `OTF_ALGORITHM_VERSION = 1`, deterministic `compute_otf_config_hash`, signal-settings identity normalization, Setup Builder OTF controls/hydration, and explicit Signals non-integration messaging. Phase 5 partially complete; research-artifact identity deferred to PR 5. Initial focused verification: 170 targeted tests + 407 OTF-focused tests; full suite: 1346 passed in 31.71s. |
| 2026-07-24 | PR 4 follow-up: hardened invalid-OTF UI state and strict hash identity; roadmap corrected | `pages/6_Signals.py`, `pages/2_Setup_Builder.py`, `tests/test_signals_page_helpers.py`, `tests/test_setup_builder_helpers.py`, `tests/test_local_store.py`, `docs/otf-filter-roadmap.md`, `docs/otf-filter.md` | Strict hashing preserved: invalid explicit OTF never silently hashes as disabled; `ValueError` raised on all malformed paths. Signals page: added `_try_normalize_signal_settings_for_hash` wrapper; signal generation/comparison/save blocked on invalid OTF. Setup Builder: added `_resolve_otf_for_ui` pure helper; malformed OTF hydrates disabled defaults with explicit warning; no dict mutation. Phase 5 corrected to partially complete. Intermediate focused verification: 193 targeted + 407 OTF tests; full suite: 1369 passed. |
| 2026-07-24 | PR 4 final fix: atomic saved-run identity transitions; shared save-path eligibility helper | `pages/6_Signals.py`, `tests/test_signals_page_helpers.py`, `docs/otf-filter-roadmap.md` | Added `_resolve_loaded_signal_identity` and `_validate_signal_artifact_identity_for_save` pure helpers. Load path atomically transitions to trusted or untrusted identity; artifacts always loadable for inspection; stale prior settings/hash cleared on untrusted load. Generation path stamps `signal_artifact_identity_status = trusted`. Both save paths use single shared helper; blocked on invalid/unavailable identity; hash integrity verified. Final focused verification: 218 targeted + 407 OTF tests; full suite: 1394 passed in 30.36s. |
