# OTF Filter — Deep Investigation Report

**Project:** ThesisTester  
**Investigation date:** 2026-07-27  
**Investigator:** Cloud Agent (investigation-only PR)  
**Scope:** End-to-end review of the One Timeframing (OTF) filter — implementation, tests, integration, documentation, and operational correctness  
**Code changes:** None (this PR adds documentation only)

---

## Executive Summary

The OTF (One Timeframing) filter is a **fully implemented, optional, directional market-condition filter** for ThesisTester research workflows. It evaluates already-generated candidate signals against higher-timeframe (5m / 15m / 30m) OTF state and accepts or rejects them before trade simulation.

### Verdict: **Working as intended**

| Area | Status | Evidence |
|------|--------|----------|
| Core state machine | ✅ Correct | Matches `docs/otf-filter.md` contract; 131 engine tests pass |
| Signal eligibility filter | ✅ Correct | Point-in-time alignment via `merge_asof`; 76 filter tests pass |
| Contract compliance | ✅ Correct | 168 contract tests pass against fixtures |
| Legacy regression safety | ✅ Correct | Disabled path is a true no-op; 32 baseline tests pass |
| Research-mode integration | ✅ Correct | Backtest, grid, walk-forward share one path; 83 integration tests pass |
| Statistical validation tooling | ✅ Correct | PR6 matrix helper; 39 validation tests pass |
| Full test suite | ✅ Green | **529 OTF tests + 1,516 total tests — all pass** |
| Documentation | ⚠️ Minor gaps | Authoritative spec complete; 2 stale UI captions; README not updated |
| Release gate | ⏳ Open | Real-dataset OOS validation and formal sign-off still pending per roadmap |

**No blocking implementation defects were found.** The primary open items are documentation hygiene, user-expectation clarity (signals page vs backtest filtering), and the deferred real-dataset statistical validation gate.

---

## 1. What Is the OTF Filter?

### 1.1 Definition

**OTF** = **One Timeframing** — a market-profile concept measuring whether price action is directionally consistent at a higher timeframe.

| State | Meaning |
|-------|---------|
| `up` | Each completed HTF bar makes a **strictly higher low** than the prior completed bar |
| `down` | Each completed HTF bar makes a **strictly lower high** than the prior completed bar |
| `neutral` | History exists but neither directional run meets the minimum consecutive threshold |
| `unknown` | Insufficient history (first bar of session, or fewer than two completed bars) |

OTF is **not** a generic "higher highs / higher lows" trend filter. It measures whether **counter-directional rotations fail** — progressive auction behavior.

### 1.2 Filter behavior (when enabled)

- **Long** signals pass only when **all selected timeframes** are `up`
- **Short** signals pass only when **all selected timeframes** are `down`
- `neutral`, `unknown`, or opposing states **reject** the signal
- Rejected signals are **retained** with audit metadata (not deleted)
- **Default: disabled** — legacy behavior is preserved

### 1.3 Authoritative specification

The behavioral contract lives in `docs/otf-filter.md` (v1, approved). The implementation tracker is `docs/otf-filter-roadmap.md`. All production behavior must match the contract; contract tests enforce this.

---

## 2. Architecture

### 2.1 Three-layer design

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: Integration (otf_integration.py)                      │
│  resolve_otf_config() → apply_configured_otf_filter()           │
│  Used by: Backtest, Grid Search, Walk-Forward, Validation      │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Layer 2: Signal Filter (otf_filter.py)                       │
│  apply_otf_filter() — eligibility, merge_asof alignment         │
│  Long requires up; Short requires down; all TFs must agree      │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Layer 1: State Engine (otf.py)                               │
│  calculate_otf_state() — resample, session reset, state machine │
│  Outputs: otf_state, sequence_length, availability_timestamp    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data flow

1. **Source OHLCV** (typically 1-minute bars) is resampled to the target HTF (5m/15m/30m)
2. Only **complete HTF buckets** are retained (full source coverage, no gaps)
3. **Partial first-session buckets** are discarded (conservative policy)
4. The **state machine** runs per session with configurable `minimum_consecutive_bars` (default 3)
5. Each HTF bar gets an `availability_timestamp` (= bar close time)
6. For each candidate signal, the filter aligns OTF state at the **decision timestamp** using `pd.merge_asof(direction="backward")` — only bars with `availability_timestamp <= decision_timestamp` are visible
7. Signals are split into **accepted** and **rejected** with full audit columns

### 2.3 Decision timestamp rule

```
decision_timestamp = trigger_timestamp (if present and non-null)
                   = timestamp         (otherwise)
```

This is implemented in `select_signal_decision_timestamp()` (`thesistester/engine/otf_filter.py`).

---

## 3. Implementation Inventory

### 3.1 Core engine

| File | Lines | Role |
|------|-------|------|
| `thesistester/engine/otf.py` | ~720 | Pure OTF state calculation (`calculate_otf_state`) |
| `thesistester/engine/otf_filter.py` | 340 | Signal eligibility filter (`apply_otf_filter`) |
| `thesistester/engine/otf_integration.py` | 303 | Research-mode integration (`apply_configured_otf_filter`) |
| `thesistester/engine/__init__.py` | — | Public API exports |

### 3.2 Configuration & persistence

| File | Role |
|------|------|
| `thesistester/setup.py` | `DEFAULT_OTF_FILTER_CONFIG`, `normalize_otf_filter_config`, `validate_otf_filter_config` |
| `thesistester/persistence/local_store.py` | `compute_otf_config_hash`, setup/signal identity integration |

### 3.3 Analytics

| File | Role |
|------|------|
| `thesistester/analytics/walk_forward.py` | Fold-local OTF filtering (`_filter_fold_signals_with_otf`) |
| `thesistester/analytics/otf_validation.py` | PR6 diagnostic validation matrix (`run_otf_validation_matrix`) |

### 3.4 Reporting

| File | Role |
|------|------|
| `thesistester/reporting.py` | `build_otf_filter_metadata`, markdown sections, rejected-signal tables |

### 3.5 UI (Streamlit)

| Page | OTF role |
|------|----------|
| `pages/2_Setup_Builder.py` | OTF config UI, save/load, hash display |
| `pages/6_Signals.py` | OTF metadata in signal identity (**does not filter** during generation) |
| `pages/7_Backtest.py` | OTF applied before `simulate_trades()` |
| `pages/8_Grid_Search.py` | OTF applied once before SL/TP grid |
| `pages/10_Validation.py` | Walk-forward + OTF validation matrix |
| `pages/11_Report_Export.py` | OTF checklist, rejected-signal CSV export |

### 3.6 Tests & fixtures

| File | Tests | Focus |
|------|-------|-------|
| `tests/test_otf.py` | 131 | Engine: state machine, resampling, sessions, DST, lookahead |
| `tests/test_otf_filter.py` | 76 | Eligibility, alignment, disabled regression, empty signals |
| `tests/test_otf_contract.py` | 168 | Fixture integrity vs contract spec |
| `tests/test_otf_baseline.py` | 32 | Legacy behavior unchanged without OTF |
| `tests/test_otf_integration.py` | 83 | Backtest/grid/walk-forward integration, config resolution |
| `tests/test_otf_validation.py` | 39 | PR6 validation matrix |
| `tests/fixtures/otf_fixtures.py` | — | 11 OHLCV scenarios + 3 vector scenarios |

### 3.7 Documentation

| File | Status |
|------|--------|
| `docs/otf-filter.md` | ✅ Complete authoritative v1 contract (§1–§15) |
| `docs/otf-filter-roadmap.md` | ✅ Living implementation tracker |
| `docs/ARCHITECTURE.md` | ❌ No OTF section |
| `README.md` | ❌ Not updated for OTF |

---

## 4. State Machine Deep Dive

The state machine (`_run_state_machine` in `thesistester/engine/otf.py`) implements the contract exactly:

### 4.1 Per-bar logic

For each completed HTF bar B with previous bar P (same session):

```
if B.low > P.low:  up_run += 1   else: up_run = 0    # equal low resets
if B.high < P.high: down_run += 1 else: down_run = 0  # equal high resets

if up_run >= min_bars and down_run < min_bars:   state = "up"
elif down_run >= min_bars and up_run < min_bars: state = "down"
else:                                             state = "neutral"
```

### 4.2 Session boundaries

At each new `trading_session_date` (futures ETH session via `eth_start`):
- `up_run = 0`, `down_run = 0`
- `prev_high = None`, `prev_low = None`
- First bar of session → `unknown`

### 4.3 Key edge cases (all tested)

| Edge case | Behavior | Test coverage |
|-----------|----------|---------------|
| Equal high/low | Resets the respective run counter | `TestEqualHighLow` |
| Inside bars (both runs increment) | `neutral` when both meet threshold | Contract §3.4 |
| Reversal (up → down) | Immediate state change at break bar | `TestReversal` |
| Partial first bucket | Discarded entirely | `TestPartialFirstBucketPolicy` |
| Incomplete HTF bucket | Not in output until all source bars present | `TestCompletedBucketCoverage` |
| DST transition | Distinct timezone-aware bucket identity | DST-specific tests |
| Source interval = target | Raises `ValueError` (must be strictly finer) | Input validation |
| Irregular timestamp gaps | Prevents unsafe HTF completion | Gap detection |

---

## 5. Look-Ahead Safety Analysis

Look-ahead bias is the highest-risk concern for any point-in-time filter. The implementation has **multiple layers of protection**:

### 5.1 Engine-level safeguards

1. **Completed bars only** — in-progress HTF buckets never appear in output
2. **`availability_timestamp`** — equals bar close time; used for all alignment
3. **Append-data invariance** — adding future source data cannot change historical OTF states

### 5.2 Filter-level safeguards

1. **`merge_asof(direction="backward")`** — only past/current bars visible at decision time
2. **No completed bar → `unknown`** — conservative rejection, never optimistic pass
3. **`allow_exact_matches=True`** — bar available exactly at decision time is usable

### 5.3 Integration-level safeguards

1. **Walk-forward fold-local filtering** — train and test OHLCV slices are independent; no cross-fold leakage
2. **Short folds** — insufficient OTF history → all candidates rejected as `unknown` (conservative)
3. **Disabled path** — true no-op; does not call OTF engine at all

### 5.4 Test evidence

`TestLookaheadSafety` (in `tests/test_otf.py`) directly tests:
- In-progress 5m/15m/30m bars excluded from output before close
- Append-data invariance for historical rows
- UTC conversion consistency
- Filter-level: extending source data after signal time does not change prior decisions

**Assessment: Look-ahead protections are thorough and well-tested.**

---

## 6. Configuration System

### 6.1 Canonical config

```python
{
    "enabled": False,              # default — legacy safe
    "timeframes": [],              # subset of {"5m", "15m", "30m"}
    "alignment_mode": "all",       # only "all" in v1
    "minimum_consecutive_bars": 3,
    "directional": True,           # fixed in v1
    "use_completed_bars_only": True,  # fixed in v1
    "session_reset": "session",    # fixed in v1
}
```

### 6.2 Config resolution precedence

1. `signal_settings["otf_filter"]` (if key explicitly present)
2. `signal_settings["setup_snapshot"]`
3. `last_signal_setup`
4. `setup_config`
5. Canonical disabled defaults

**Critical rule:** An explicit but invalid config (e.g. `enabled=True` with no timeframes) always raises `ValueError` — it is never silently treated as disabled.

### 6.3 Identity & hashing

- `OTF_ALGORITHM_VERSION = 1` (`thesistester/engine/otf.py`)
- `compute_otf_config_hash()` — SHA-256 over normalized config + algorithm version
- Ensures reproducible signal/setup identity across runs

---

## 7. Integration Points

### 7.1 Where OTF is applied

| Location | When | Mechanism |
|----------|------|-----------|
| `pages/7_Backtest.py:301` | Before `simulate_trades()` | `apply_configured_otf_filter()` |
| `pages/8_Grid_Search.py:314` | Once before SL/TP grid | Same helper; all grid cells share accepted set |
| `thesistester/analytics/walk_forward.py:305-322` | Per fold, train/test separately | `_filter_fold_signals_with_otf()` |
| `thesistester/analytics/otf_validation.py` | Validation matrix | `apply_otf_filter()` per config row |
| `thesistester/reporting.py` | Export | OTF metadata + rejected signals table |

### 7.2 Where OTF is intentionally NOT applied

| Location | Behavior | Rationale |
|----------|----------|-----------|
| `thesistester/engine/signals.py` | **Zero OTF references** | Candidates generated unfiltered |
| `pages/6_Signals.py` | Metadata only | OTF config stored for identity; no filtering at generation time |

This is **by design** per contract §9: the filter runs after candidate generation, before trade simulation. Users see all candidates on the Signals page; filtering impact is visible on Backtest/Grid/Validation pages.

### 7.3 Session state keys

- `otf_filter_result`, `otf_filter_summary`
- `otf_candidate_signals`, `otf_accepted_signals`, `otf_rejected_signals`
- `backtest_otf_filter`, `grid_otf_filter`, `walk_forward_otf_filter`
- `otf_validation_matrix`, `otf_validation_summary`, `otf_validation_config`

---

## 8. Test Results

### 8.1 OTF-specific suites

```
tests/test_otf.py              131 passed
tests/test_otf_filter.py        76 passed
tests/test_otf_contract.py     168 passed
tests/test_otf_baseline.py      32 passed
tests/test_otf_integration.py   83 passed
tests/test_otf_validation.py    39 passed
─────────────────────────────────────────
OTF total                      529 passed in 11.43s
```

### 8.2 Full suite

```
1,516 passed in 29.49s
```

### 8.3 Notable test categories

| Category | What it proves |
|----------|----------------|
| `TestDisabledRegression` / `TestDisabledIsATrueNoOp` | Legacy behavior identical when OTF disabled |
| `TestLookaheadSafety` | No future data leakage |
| `TestPointInTimeAlignment` | Correct `merge_asof` behavior at signal timestamps |
| `TestMultiTimeframeAllMode` | All selected TFs must agree |
| `TestDirectionalEligibilitySingleTimeframe` | Long→up, Short→down |
| Walk-forward fold tests | Fold-local filtering, no cross-fold leakage |
| Validation matrix tests | Train/OOS split survives filter index reset |

---

## 9. Findings & Recommendations

### 9.1 No blocking defects found

The OTF filter implementation is **coherent, well-tested, and matches its specification**. The three-layer architecture (engine → filter → integration) is clean with a single shared code path across all research modes.

### 9.2 Minor issues (documentation / UX only)

#### Finding 1: Stale UI captions referencing "PR 5"

**Severity:** Low (cosmetic)  
**Impact:** Users may believe OTF filtering is not yet active in backtests

| File | Line | Current text |
|------|------|-------------|
| `pages/6_Signals.py` | ~978 | *"signal generation/backtests are not filtered by OTF until PR 5"* |
| `pages/2_Setup_Builder.py` | ~1013 | Subheader: *"OTF filter configuration (saved for PR 5)"* |
| `pages/2_Setup_Builder.py` | ~1016 | *"standard signal generation/backtests are not filtered by OTF until PR 5"* |

**Reality:** PR 5 is complete. Backtests, grid search, and walk-forward **do** apply OTF filtering when enabled.

**Recommendation:** Update captions to reflect current behavior. Suggested text: *"OTF filtering is applied during backtest, grid search, and walk-forward when enabled. Signal generation produces unfiltered candidates."*

#### Finding 2: Signals page vs backtest filtering mismatch

**Severity:** Low (by design, but potentially confusing)  
**Impact:** Users may expect the Signals page list to reflect OTF filtering

`st.session_state["signals"]` always holds **unfiltered** candidates. OTF acceptance/rejection is only visible after running a backtest (via `otf_accepted_signals` / `otf_rejected_signals` session keys or the backtest OTF summary expander).

**Recommendation:** Consider adding a note on the Signals page when OTF is enabled in the active setup: *"N candidates generated. OTF filtering will be applied at backtest time."*

#### Finding 3: README and ARCHITECTURE.md not updated

**Severity:** Low  
**Impact:** New contributors may not discover the OTF feature

The roadmap (`docs/otf-filter-roadmap.md`) lists README update as an open item.

**Recommendation:** Add a brief OTF section to README and/or `docs/ARCHITECTURE.md` pointing to `docs/otf-filter.md`.

#### Finding 4: Roadmap checklist drift

**Severity:** Low  
**Impact:** Manual checklist items remain unchecked despite automated test coverage

Phase 10 manual checklist items (e.g. "Long with OTF up passes") remain `[ ]` in the roadmap but are covered by the 529 automated tests.

**Recommendation:** Reconcile roadmap checkboxes with test evidence.

### 9.3 Open release-gate items (not bugs)

Per `docs/otf-filter-roadmap.md`:

| Item | Status |
|------|--------|
| Real user dataset OOS validation | ⏳ Pending |
| Regression and drift-safety review sign-off | ⏳ Pending |
| Release approval | ⏳ Pending real-dataset validation |

The PR6 validation matrix (`run_otf_validation_matrix`) provides diagnostic tooling but explicitly states: *"Results are not proof of edge."*

### 9.4 Operational considerations (not defects)

| Consideration | Detail |
|---------------|--------|
| Trade count reduction | OTF filtering reduces accepted signals → lower statistical power; expected behavior |
| Walk-forward short folds | Folds with insufficient OTF history reject all candidates; can produce `no_train_candidate` folds |
| Performance | `calculate_otf_state()` runs once per selected timeframe per filter invocation; acceptable for research use; no cross-timeframe caching |
| Source data requirements | Source interval must be strictly finer than OTF timeframe and exactly divide it |

---

## 10. Dependency Map

```
thesistester/engine/otf.py
  ├── thesistester/data/resample.py (resample_ohlcv)
  ├── thesistester/data/loader.py (infer_base_interval)
  └── thesistester/levels/session_date.py (trading_session_date)

thesistester/engine/otf_filter.py
  └── thesistester/engine/otf.py (calculate_otf_state)

thesistester/engine/otf_integration.py
  ├── thesistester/engine/otf_filter.py
  ├── thesistester/setup.py (config normalization)
  └── thesistester/persistence/local_store.py (config hashing)

thesistester/analytics/walk_forward.py
  └── thesistester/engine/otf_filter.py

thesistester/analytics/otf_validation.py
  ├── thesistester/engine/otf_filter.py
  └── thesistester/engine/backtest.py (simulate_trades)

pages/7_Backtest.py, pages/8_Grid_Search.py
  └── thesistester/engine/otf_integration.py
```

No external OTF package — all logic is internal to ThesisTester with a single shared implementation path.

---

## 11. Quick Reference

### Entry points

```python
# Pure state calculation
from thesistester.engine.otf import calculate_otf_state

# Signal eligibility filter
from thesistester.engine import apply_otf_filter

# Research-mode integration (preferred for pages)
from thesistester.engine import apply_configured_otf_filter, resolve_otf_config

# Config
from thesistester.setup import normalize_otf_filter_config, get_effective_otf_filter_config
```

### Verification commands

```bash
# OTF-specific tests (529 tests)
python3 -m pytest tests/test_otf.py tests/test_otf_filter.py tests/test_otf_contract.py \
  tests/test_otf_baseline.py tests/test_otf_integration.py tests/test_otf_validation.py -v

# Full suite (1,516 tests)
python3 -m pytest tests/ -q
```

### Key documents

| Document | Purpose |
|----------|---------|
| `docs/otf-filter.md` | Authoritative v1 behavioral contract |
| `docs/otf-filter-roadmap.md` | Implementation tracker and release gate |
| `docs/investigations/otf-filter-investigation.md` | This investigation report |

---

## 12. Conclusion

The OTF filter in ThesisTester is **production-quality research tooling** that:

1. Implements the approved v1 contract faithfully
2. Protects against look-ahead bias through completed-bar-only policy, `availability_timestamp` alignment, and fold-local walk-forward filtering
3. Preserves legacy behavior when disabled (true no-op, verified by 32 baseline tests)
4. Provides full audit trails (accepted/rejected signals with reasons, config hashes, algorithm version)
5. Is covered by 529 dedicated tests — all passing

The feature is **working as intended**. Recommended follow-ups are limited to documentation/UX polish (stale UI captions, README update) and the deferred real-dataset statistical validation release gate — none of which indicate implementation defects.

---

*This is an investigation-only document. No production code was modified.*
