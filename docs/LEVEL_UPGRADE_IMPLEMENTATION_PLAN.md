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
- Default configuration: `left=2`, `right=2`, matching the 5-candle pivot concept.
- Pivot levels must not repaint.

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

### Stage 1 — Add Isolated Level Modules

Add new functionality in isolated modules without changing existing level behavior.

Recommended module structure:

```text
thesistester/levels/pivots.py
thesistester/levels/session_vwap.py
thesistester/levels/tpo.py
```

Alternatively, if the project prefers fewer files, profile-adjacent logic may live in:

```text
thesistester/levels/profile.py
```

Rules:

- Keep existing session, indicator, and profile outputs unchanged.
- Wire new modules into the existing level aggregator only behind explicit settings.
- Default all new features to disabled in the UI.

---

### Stage 2 — Pivots

Implement:

- native 1m pivots,
- resampled 5m, 30m, and 4h pivots,
- confirmation delay,
- higher-timeframe availability only after candle close plus right-window confirmation,
- no forward-fill before confirmation.

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

Implement:

```text
dVWAP_RTH
```

Rules:

- reset every RTH session,
- compute cumulatively and causally,
- emit `NaN` before RTH open,
- handle zero cumulative volume safely,
- do not modify existing rolling VWAP columns.

Required tests:

- exact cumulative VWAP calculation on synthetic data,
- reset across sessions,
- zero-volume handling,
- DST/session-boundary fixture,
- no behavior drift in existing rolling VWAP columns.

Acceptance criteria:

- `dVWAP_RTH` starts only at RTH session open.
- It updates causally bar by bar.
- It resets correctly at the next RTH session.

---

### Stage 4 — Single Prints

Implement TPO-based 30-minute Single Prints using instrument tick size.

Initial columns:

```text
dSinglePrint_30m_NearestAbove
dSinglePrint_30m_NearestBelow
pSinglePrint_30m_NearestAbove
pSinglePrint_30m_NearestBelow
```

Rules:

- Use 30-minute TPO brackets.
- Use completed 30-minute brackets only for the first implementation.
- Freeze historical prior-session values after session close.
- Developing values may change causally as new completed brackets become available.
- Emit `NaN` if no valid Single Print exists.

Required tests:

- fixture with known single print bins,
- no single prints returns `NaN`,
- nearest-above and nearest-below correctness,
- prior-session shift correctness,
- tick-size binning correctness,
- future-shock / point-in-time test.

Acceptance criteria:

- No dynamic Single Print columns are generated.
- Prior-session Single Prints use completed prior sessions only.
- Developing Single Prints do not use incomplete future brackets.

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
