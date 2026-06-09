# Level Upgrade Engineering & Implementation Plan

## Purpose

This document defines the regression-safe and drift-safe implementation plan for adding new level families to ThesisTester:

1. Confirmed multi-timeframe pivots
2. Developing session VWAP
3. TPO-based 30m Single Prints
4. APOC and pAPOC

The goal is to extend the level engine without changing existing level behavior, signal behavior, or backtest semantics unless a user explicitly enables the new levels.

---

## Executive Summary

ThesisTester currently has a clean level architecture:

- Levels are computed as scalar timeline columns.
- Existing families are separated into session, indicator, and profile levels.
- Signal and backtest logic consume level columns generically.
- Therefore, the safest implementation path is to add new level columns while preserving downstream contracts.

The largest design risk is Single Prints. Single Prints are naturally multi-price structures, while the current system expects scalar level columns. This document therefore defines a scalar output contract for the first implementation.

---

## Required Spec Decisions

### 1. Pivots

Approved definition:

- Use confirmed fractal pivots.
- A pivot at candle `k` becomes available only after `R` right-side candles have closed.
- Availability timing is `pivot_candle_close_time + R * timeframe_duration`.
- Default configuration: `left=2`, `right=2`, matching the 5-candle pivot concept.
- Pivot levels must not repaint.
- Supported labels remain exactly: `1min`, `5min`, `30min`, `4h`.

Initial output columns:

```text
Pivot_1m_High
Pivot_1m_Low
Pivot_5m_High
Pivot_5m_Low
Pivot_30m_High
Pivot_30m_Low
Pivot_4h_High
Pivot_4h_Low
```

Semantics:

- Each column represents the latest confirmed pivot level for that timeframe and side.
- When pivots are disabled (`pivots_enabled=False`), pivot computation remains a true no-op:
  empty DataFrame, no timestamp validation, no added columns.
- Do not store all historical pivots in dynamic columns in the first implementation.
- SFP, liquidity grab, breaker, or retest interpretation should not be embedded in the level engine initially. The level engine should produce clean levels only.

Future signal logic may classify interactions separately as:

- trade into pivot from above or below,
- sweep and reclaim,
- breaker retest,
- failed auction.

---

### 2. dVWAP

Recommended first implementation:

```text
dVWAP_RTH
```

Definition:

- Developing VWAP from RTH session start.
- Reset every RTH session.
- Use cumulative typical price multiplied by volume divided by cumulative volume.
- Emit `NaN` before RTH session start.
- Remain causal by using only bars available at or before the current timestamp.

Formula:

```text
dVWAP = cumulative_sum(typical_price * volume) / cumulative_sum(volume)
```

Where:

```text
typical_price = (high + low + close) / 3
```

Important constraints:

- Do not modify existing rolling VWAP behavior.
- Keep the session anchor explicit.
- A later extension may add `dVWAP_ETH` if the session model supports it cleanly.

---

### 3. Single Prints

Single Prints are the highest architectural-risk feature because they are naturally multi-level structures.

Do not implement dynamic columns such as:

```text
SinglePrint_1
SinglePrint_2
SinglePrint_3
```

These would be fragile, hard to cache deterministically, and inconsistent with the current scalar-column level architecture.

Approved scalar output contract for the first implementation:

```text
dSinglePrint_30m_NearestAbove
dSinglePrint_30m_NearestBelow
pSinglePrint_30m_NearestAbove
pSinglePrint_30m_NearestBelow
```

Definitions:

- `dSinglePrint` = developing current-session TPO single print level.
- `pSinglePrint` = prior completed session's frozen single print level.
- `NearestAbove` = closest valid single print price above the current bar close.
- `NearestBelow` = closest valid single print price below the current bar close.
- If no valid level exists, emit `NaN`.

Recommended first-version rule:

- Use only completed 30-minute brackets when calculating developing Single Prints.
- Do not include the current incomplete 30-minute bracket in the first implementation.

This avoids unnecessary intrabar drift and makes point-in-time behavior easier to test.

---

### 4. APOC / pAPOC

Approved definition:

```text
APOC = POC of the first completed RTH 30-minute bracket.
pAPOC = previous session's APOC.
```

Initial output columns:

```text
APOC
pAPOC
```

Availability rules:

- `APOC` is `NaN` until the first RTH 30-minute bracket has completed.
- `pAPOC` is available from the next session start.
- If the A-period has insufficient or missing data, emit `NaN`.

Important clarification:

- Do not define APOC as the highest-volume 30-minute POC of the full day. That would only be knowable after the full session and would create lookahead bias.
- For this implementation, APOC means the A-period POC: the POC of the first completed RTH 30-minute bracket.

---

## Implementation Plan

### Stage 0 — Spec Lock

Before coding, lock:

- output column names,
- RTH/ETH anchoring for dVWAP,
- pivot `left` and `right` defaults,
- Single Print scalar output contract,
- APOC definition and availability gate.

No implementation should begin before these semantics are documented.

---

### Stage 1 — Add Isolated Level Modules ✅ COMPLETE

**Status:** Implemented in PR #68; complete once merged. Plumbing only — no level algorithms implemented yet.

Added modules:

```text
thesistester/levels/pivots.py       — compute_pivot_levels() stub
thesistester/levels/session_vwap.py — compute_session_vwap_levels() stub
thesistester/levels/tpo.py          — compute_tpo_levels() stub (covers SP + APOC)
```

All three functions accept an `enabled` / gate keyword that defaults to `False`.
When the gate is disabled the function returns an empty DataFrame immediately
(true no-op — no timestamp validation).  When the gate is enabled the function
first validates that `timestamp` is tz-aware (raises `ValueError` for naive
timestamps), then raises `NotImplementedError` until the corresponding stage is
implemented.  This means `compute_all_levels` can call them without producing any
new columns or incurring any validation cost under the default (disabled) settings.

`compute_all_levels` (`thesistester/levels/all.py`) now accepts the following new
keyword arguments, all defaulting to the no-op state:

```
pivots_enabled=False
pivot_timeframes=None
pivot_left=2
pivot_right=2
session_vwap_enabled=False
session_vwap_anchor="RTH"
single_prints_enabled=False
apoc_enabled=False
```

`thesistester/levels/__init__.py` exports all three new compute functions.

Tests added in `tests/test_stage1_level_plumbing.py` (27 tests):

- new modules are importable and exported from the package,
- settings constants are correctly defined,
- disabled stubs return empty DataFrames with the correct index length,
- `compute_all_levels` with default settings produces zero new columns,
- explicit disabled gates also produce zero new columns,
- enabling any gate raises `NotImplementedError` (stub contract),
- stubs require a tz-aware `timestamp` column.

Rules:

- Keep existing session, indicator, and profile outputs unchanged. ✅
- Wire new modules into the existing level aggregator only behind explicit settings. ✅
- Default all new features to disabled in the UI. ✅

---

### Stage 2 — Pivots

**Status:** Implemented in PR #69; complete once merged.

Implemented in `thesistester/levels/pivots.py`.

Implement:

- native 1m pivots,
- resampled 5m, 30m, and 4h pivots,
- confirmation delay,
- higher-timeframe availability only after candle close plus right-window confirmation,
- no forward-fill before confirmation.

Implemented contract:

- `pivot_timeframes=None` computes all supported pivot timeframes.
- Enabled output is limited to scalar latest-confirmed columns:
  `Pivot_1m_High/Low`, `Pivot_5m_High/Low`, `Pivot_30m_High/Low`, `Pivot_4h_High/Low`.
- `pivot_left` and `pivot_right` must be positive integers.
- Requesting a pivot timeframe smaller than the loaded base interval raises `ValueError`.
- Before the first confirmed pivot exists, pivot columns remain `NaN`.

Required tests:

- synthetic pivot high fixture,
- synthetic pivot low fixture,
- no pivot before confirmation,
- future-shock / point-in-time test,
- multi-timeframe alignment test,
- missing candle / gap tolerance test.

Acceptance criteria:

- Pivot levels are never visible before confirmation.
- Existing levels are unchanged when pivots are disabled.
- Higher-timeframe pivots do not leak before the higher-timeframe candle and right-window confirmation are complete.

---

### Stage 3 — dVWAP

**Status:** Implemented in this PR; complete once merged.

Implemented in `thesistester/levels/session_vwap.py`.

Implements:

```text
dVWAP_RTH
```

Rules:

- reset every RTH session,
- compute cumulatively and causally,
- emit `NaN` on non-RTH bars (pre-open and post-close),
- handle zero cumulative volume safely (emit `NaN`),
- do not modify existing rolling VWAP columns.

Output column:
- `dVWAP_RTH` — developing VWAP from RTH session start.

Formula:

```text
typical_price = (high + low + close) / 3
dVWAP_RTH[t] = cumsum(typical_price * volume) / cumsum(volume)
```

Session `session` column:
- If present, used directly.
- If absent, derived from timestamp and instrument config via `tag_session`.

Implemented tests in `tests/test_stage3_session_vwap.py` (28 tests):

- disabled returns empty DataFrame (no validation),
- disabled accepts naive timestamps,
- `compute_all_levels` with `session_vwap_enabled=False` produces no `dVWAP_RTH`,
- exact bar-by-bar cumulative VWAP values,
- output column name is `dVWAP_RTH`,
- index length matches input,
- session reset across two RTH sessions,
- session 1 last value does not carry to session 2,
- ETH bars before RTH emit NaN,
- ETH bars after RTH close emit NaN,
- only RTH bars have non-NaN dVWAP,
- zero-volume single bar emits NaN,
- zero-volume then positive volume: NaN then valid VWAP,
- multiple zero-volume bars then valid VWAP,
- unsupported anchor raises ValueError,
- unsupported instrument raises ValueError,
- naive timestamp raises ValueError,
- disabled mode accepts naive timestamps / unsupported anchor / unsupported instrument,
- existing level columns unchanged when VWAP disabled,
- no dVWAP column without explicit enable,
- dVWAP column present when enabled,
- future-shock: appending future RTH bars does not change prior values,
- future-shock across sessions,
- session column derived from instrument config when absent,
- NQ instrument supported.

Acceptance criteria:

- `dVWAP_RTH` starts only at RTH session open.
- It updates causally bar by bar.
- It resets correctly at the next RTH session.
- Non-RTH bars always emit `NaN`.

---

### Stage 4 — Single Prints

**Status:** Implemented in this PR; complete once merged.

Implemented in `thesistester/levels/tpo.py`.

Implements TPO-based 30-minute Single Prints using instrument tick size.

Output columns:

```text
dSinglePrint_30m_NearestAbove
dSinglePrint_30m_NearestBelow
pSinglePrint_30m_NearestAbove
pSinglePrint_30m_NearestBelow
```

Rules:

- Use RTH 30-minute TPO brackets (non-RTH bars do not contribute).
- Use completed 30-minute brackets only (current incomplete bracket is excluded).
- Price bins are instrument tick increments (tick_size from `INSTRUMENTS`).
- A bin is a Single Print if it is touched by exactly one completed bracket per session.
- Nearest-above uses strict `price > close`; nearest-below uses strict `price < close`.
- Freeze prior-session Single Print set once that session is complete.
- Developing values may change causally as new completed brackets become available.
- Emit `NaN` if no valid Single Print exists or for non-RTH bars.
- If `session` column is absent, derive from instrument config via `tag_session`.

Implemented tests in `tests/test_stage4_single_prints.py` (37 tests):

- disabled returns empty DataFrame (no validation),
- disabled accepts naive timestamps and unsupported instruments,
- `apoc_enabled=True` still raises `NotImplementedError`,
- `compute_all_levels` with `single_prints_enabled=False` produces no SP columns,
- enabling SP produces exactly the four scalar columns (no dynamic columns),
- tick-size binning correctness (bins based on instrument tick size),
- bins touched by multiple brackets are excluded,
- single-bracket: all bins are Single Prints,
- no developing SP before first bracket completes,
- developing SP appear after bracket completes,
- current incomplete bracket is excluded,
- nearest-above/below use strict comparison to close,
- developing SP update causally when new bracket completes,
- prior-session SP maps to next session,
- prior-session values are frozen,
- prior-session NaN when no prior SP,
- ETH bars do not contribute to SP sets,
- ETH bars emit NaN for developing and prior-session SP columns,
- session column derived from instrument config when absent,
- future-shock: appending future current-session bars does not alter earlier values,
- future-shock: appending next-session bars does not alter prior-session SP values,
- unsorted input produces same result as sorted input,
- naive timestamp raises ValueError,
- unsupported instrument raises ValueError,
- NQ instrument supported,
- existing level outputs unchanged when SP disabled,
- pivots and dVWAP unchanged when SP enabled,
- `compute_all_levels` with SP enabled adds exactly the four SP columns.

Known limitations:

- No APOC / pAPOC yet (Stage 5).
- No full market-profile object.
- No volume-at-price.
- No dynamic list of all Single Print bins.

Acceptance criteria:

- `single_prints_enabled=False` remains a true no-op.
- `single_prints_enabled=True` produces only the four scalar SP columns.
- `apoc_enabled=True` still raises `NotImplementedError`.
- SP uses completed 30-min RTH brackets only.
- Current incomplete bracket is excluded.
- TPO bins use instrument tick size.
- Nearest above/below use strict comparison to current close.
- Prior-session SP are frozen and use completed prior sessions only.
- ETH bars do not contribute.
- Point-in-time future-shock tests pass.
- Existing default outputs remain unchanged.

---

### Stage 5 — APOC / pAPOC

Implement:

```text
APOC
pAPOC
```

Rules:

- APOC is the POC of the first completed RTH 30-minute bracket.
- APOC is unavailable before that bracket completes.
- pAPOC is the previous session's frozen APOC.
- Missing or insufficient A-period data should produce `NaN`.

Required tests:

- APOC unavailable before A-period close,
- APOC appears after A-period close,
- pAPOC maps to the next session,
- missing A-period returns `NaN`,
- future-shock / point-in-time test.

Acceptance criteria:

- APOC never appears before the first RTH 30-minute bracket is complete.
- pAPOC is stable throughout the next session.
- No full-session lookahead is used.

---

### Stage 6 — UI and Persistence

Add controls to the Levels page, default disabled:

```text
Enable pivots
Enable dVWAP
Enable Single Prints
Enable APOC / pAPOC
```

Rules:

- Include all new settings in the existing level settings hash.
- Ensure cached level snapshots remain deterministic.
- Existing saved snapshots must continue loading.
- Do not change existing default enabled levels.

Acceptance criteria:

- New levels are only computed when explicitly enabled.
- Existing saved level snapshots remain compatible.
- Recomputing with identical settings produces deterministic outputs.

---

### Stage 7 — Documentation

Update at minimum:

```text
docs/POINT_IN_TIME_GUARANTEES.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
```

Document:

- pivot confirmation delay,
- dVWAP session anchor,
- Single Print scalar contract,
- APOC availability gate,
- developing versus historical semantics,
- known limitations,
- no-lookahead assumptions.

Acceptance criteria:

- Documentation is updated in the same PR as code.
- Point-in-time guarantees explicitly cover every new level family.
- Known limitations are transparent and test-aligned.

---

## Recommended PR Breakdown

### PR 1 — Pivots + dVWAP

Scope:

- Add confirmed pivots.
- Add `dVWAP_RTH`.
- Add UI toggles.
- Add tests and documentation for these two families.

Reason:

- These are lower-risk, scalar, causal level additions.
- They can be validated independently without touching TPO complexity.

---

### PR 2 — APOC / pAPOC

Scope:

- Add APOC and pAPOC.
- Reuse existing profile/POC logic where possible.
- Add A-period availability tests and documentation.

Reason:

- APOC is profile-adjacent but still scalar and relatively contained.

---

### PR 3 — Single Prints

Scope:

- Add scalar Single Print outputs.
- Add TPO/tick-size binning logic.
- Add developing and prior-session variants.
- Add extensive point-in-time tests and documentation.

Reason:

- This is the highest architectural-risk feature and should be isolated.

---

## Global Acceptance Criteria

The implementation is acceptable only if:

- Existing level columns are unchanged when new features are disabled.
- Existing tests pass.
- New levels are `NaN` before their valid availability point.
- Pivot levels never appear before confirmation.
- APOC never appears before the first RTH 30-minute bracket is complete.
- pAPOC and prior Single Prints use completed prior sessions only.
- No downstream signal or backtest logic needs to be changed.
- Saved level and signal snapshots continue loading.
- Documentation is updated in the same PR.

---

## Validation Checklist

Before merging any implementation PR:

```bash
pytest -q
```

Also verify:

- unchanged settings produce unchanged existing level outputs,
- new features default to disabled,
- point-in-time tests cover every new level family,
- session boundary tests cover relevant RTH behavior,
- documentation matches implemented behavior.

---

## Key Risk

The primary unresolved risk is TPO Single Prints.

Because Single Prints are naturally multi-price sets and the current architecture is scalar-column-based, the first implementation must keep the scalar contract defined in this document. Any richer multi-level representation should be deferred until the application has an explicit data model for set-valued levels.
