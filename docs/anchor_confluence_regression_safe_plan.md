# Regression-Safe Implementation Plan: Anchor-Based Per-Confluence Model

## Implementation Status

As of Phase 8, the anchor-confluence rollout described in this document has been implemented through the Setup Builder -> Signals -> Backtest workflow.

Completed:

- Phase 1: Global confluence regression tests
- Phase 2: Setup config extension
- Phase 3: Anchor confluence engine
- Phase 4: Engine export
- Phase 5: Setup Builder UI
- Phase 6: Signals page routing
- Phase 7: Anchor diagnostics display
- Phase 8: UX/downstream messaging cleanup

This document remains the historical rollout plan and design reference.

Future extensions listed later in this document remain future work.

## 1. Purpose

This document defines a regression-safe implementation plan for adding an **anchor-based per-confluence model** to ThesisTester.

The current application supports a **global cluster confluence model**:

> The user selects multiple computed level columns, sets one global tick tolerance, and the engine automatically detects clusters of levels within that shared tolerance.

The desired new model supports an **anchor-based confluence workflow**:

> The user selects one anchor level, adds supporting confluence levels, assigns a separate `+/- x ticks` tolerance to each confluence, and the engine determines which confluences are valid for each bar.

The update must preserve existing behavior, tests, and backtest reproducibility.

---

## 2. Current Behavior Summary

### 2.1 Current confluence model

Current confluence detection is implemented by:

```text
thesistester/engine/confluence.py
```

Primary function:

```python
detect_confluence_zones(
    df,
    level_columns,
    tick_size,
    tolerance_ticks,
    min_confluences=2,
    max_confluences=5,
)
```

Current logic:

1. For every bar, collect all non-null selected level prices.
2. Sort level prices from low to high.
3. Apply a greedy sliding-window cluster algorithm.
4. Emit a confluence zone if enough levels fit within:

```text
tolerance_ticks * tick_size
```

### 2.2 Current user-facing model

Current UI allows the user to configure:

```text
selected_levels
tolerance_ticks
min_confluences
max_confluences
naked_only
naked_requirement
trigger
direction
trigger_params
```

### 2.3 Current limitation

The current implementation has **one global tolerance**.

It does not support:

- one anchor/base level;
- manually configured confluence rules;
- different tick tolerances per confluence;
- required versus optional confluence rules;
- per-rule validity diagnostics.

---

## 3. Target Behavior

Add a second confluence mode named:

```text
anchor_rules
```

The existing mode should be named:

```text
global_cluster
```

### 3.1 Global cluster mode

This is the existing behavior.

Example:

```text
Selected levels: ONH, OR_High, VWAP_rolling_1h, pdPOC
Tolerance: 4 ticks
Min confluences: 2
Max confluences: 5
```

Meaning:

> Detect any cluster of selected levels whose total price range is within 4 ticks.

### 3.2 Anchor-based rules mode

Example:

```text
Anchor level: pdHigh

Confluence rules:
- VWAP_rolling_1h within +/- 4 ticks, required
- pdPOC within +/- 6 ticks, optional
- OR_High within +/- 2 ticks, optional

Minimum valid confluences: 2
```

Meaning:

> For each bar, evaluate the distance between `pdHigh` and each configured confluence level. A confluence is valid if its absolute distance from the anchor is less than or equal to its own tolerance. Emit a zone only if all required rules are valid and the minimum number of valid confluences is met.

---

## 4. Design Principles

### 4.1 Do not replace existing logic

Do **not** rewrite `detect_confluence_zones()` as part of this change.

The existing global cluster model remains the baseline and must continue to behave exactly as before.

### 4.2 Add new logic beside old logic

Add a separate engine function:

```python
detect_anchor_confluence_zones(...)
```

Recommended file:

```text
thesistester/engine/anchor_confluence.py
```

### 4.3 Preserve downstream compatibility

The new anchor-based engine must emit the same core zone columns currently expected downstream:

```text
timestamp
bar_index
zone_low
zone_high
zone_mid
level_count
level_names
level_prices
```

This minimizes required changes to:

```text
generate_signals()
backtest()
validation pages
report export
```

### 4.4 Add diagnostics, but do not require downstream consumers to use them

The anchor engine may add extra columns for transparency:

```text
confluence_mode
anchor_level
anchor_price
valid_confluence_count
required_valid
rule_results
```

Downstream code should ignore these unless explicitly used for display.

---

## 5. Data Model Changes

### 5.1 Existing setup config fields

Current setup config fields must remain supported:

```python
{
    "name": str,
    "description": str,
    "instrument": str,
    "selected_levels": list[str],
    "tolerance_ticks": float,
    "min_confluences": int,
    "max_confluences": int,
    "naked_only": bool,
    "naked_requirement": str,
    "trigger": str,
    "direction": str,
    "trigger_params": dict,
}
```

### 5.2 New setup config fields

Add the following fields:

```python
{
    "confluence_mode": "global_cluster" | "anchor_rules",
    "anchor_level": str | None,
    "confluence_rules": list[dict],
    "min_valid_confluences": int,
}
```

### 5.3 Backward-compatible defaults

For old saved configs that do not contain `confluence_mode`, default to:

```python
confluence_mode = "global_cluster"
```

For old saved configs, the following default values are acceptable:

```python
anchor_level = None
confluence_rules = []
min_valid_confluences = 1
```

### 5.4 Recommended confluence rule schema

Each confluence rule should use this structure:

```python
{
    "level": "VWAP_rolling_1h",
    "tolerance_ticks": 4.0,
    "required": True,
}
```

Field meanings:

| Field | Type | Meaning |
|---|---:|---|
| `level` | `str` | Name of the confluence level column |
| `tolerance_ticks` | `float` | Maximum allowed absolute distance from anchor, measured in ticks |
| `required` | `bool` | Whether this rule must be valid for the setup to qualify |

---

## 6. Engine Design

### 6.1 New function signature

Add:

```python
def detect_anchor_confluence_zones(
    df: pd.DataFrame,
    anchor_level: str,
    confluence_rules: list[dict],
    tick_size: float,
    min_valid_confluences: int = 1,
) -> pd.DataFrame:
    ...
```

### 6.2 Per-bar algorithm

For each row/bar:

1. Read the anchor level price.
2. If the anchor level is missing or NaN, skip the bar.
3. For each confluence rule:
   1. Read the confluence level price.
   2. If missing or NaN, mark the rule invalid with reason `missing_price`.
   3. Compute:

      ```python
      distance_ticks = abs(confluence_price - anchor_price) / tick_size
      ```

   4. Mark valid if:

      ```python
      distance_ticks <= tolerance_ticks
      ```

4. Check all required rules.
5. Count valid confluence rules.
6. Emit a zone only if:

```text
all required rules are valid
AND
valid_confluence_count >= min_valid_confluences
```

### 6.3 Zone construction

If a valid anchor-based confluence zone is found, include:

```text
anchor price + all valid confluence prices
```

Then compute:

```python
zone_low = min(included_prices)
zone_high = max(included_prices)
zone_mid = (zone_low + zone_high) / 2.0
level_count = len(included_prices)
```

`level_names` should include the anchor level plus valid confluence levels:

```text
pdHigh|VWAP_rolling_1h|pdPOC
```

`level_prices` should use the same order:

```text
4500.0|4500.75|4499.5
```

### 6.4 Invalid optional rules

Invalid optional rules should not prevent a zone if the minimum valid count is met.

They should also not be included in:

```text
level_names
level_prices
zone_low
zone_high
zone_mid
```

But they should be represented in diagnostics.

### 6.5 Invalid required rules

If any required rule is invalid, no zone should be emitted for that bar.

### 6.6 Missing confluence prices

A missing confluence price should be treated as invalid for that rule.

If the missing rule is required, the setup is invalid for that bar.

If the missing rule is optional, the setup may still qualify if enough other confluences are valid.

### 6.7 Floating-point tolerance

Use a small epsilon when comparing computed tick distances:

```python
epsilon = 1e-9
is_valid = distance_ticks <= tolerance_ticks + epsilon
```

This avoids rejecting a confluence due to harmless floating-point representation error.

### 6.8 Invalid tick size

If `tick_size <= 0`, return an empty DataFrame or raise a clear `ValueError`.

Preferred for safety:

```python
raise ValueError("tick_size must be > 0")
```

Tests should cover this.

---

## 7. Output Schema

### 7.1 Required core columns

The anchor engine must return the core zone schema:

```text
timestamp
bar_index
zone_low
zone_high
zone_mid
level_count
level_names
level_prices
```

### 7.2 Recommended diagnostic columns

Add:

```text
confluence_mode
anchor_level
anchor_price
valid_confluence_count
required_valid
rule_results
```

### 7.3 `rule_results` format

For MVP simplicity, store `rule_results` as a JSON string.

Example:

```json
[
  {
    "level": "VWAP_rolling_1h",
    "price": 4500.75,
    "tolerance_ticks": 4.0,
    "distance_ticks": 3.0,
    "required": true,
    "valid": true,
    "reason": "within_tolerance"
  },
  {
    "level": "OR_High",
    "price": 4502.0,
    "tolerance_ticks": 2.0,
    "distance_ticks": 8.0,
    "required": false,
    "valid": false,
    "reason": "outside_tolerance"
  }
]
```

This gives auditability without changing the existing signal-generation contract.

---

## 8. Setup Validation Changes

Modify:

```text
thesistester/setup.py
```

### 8.1 Add valid confluence modes

Add:

```python
VALID_CONFLUENCE_MODES = frozenset({"global_cluster", "anchor_rules"})
```

### 8.2 Extend `build_setup_config()`

Add optional parameters:

```python
confluence_mode: str = "global_cluster"
anchor_level: str | None = None
confluence_rules: list[dict] | None = None
min_valid_confluences: int = 1
```

Return these in the config.

### 8.3 Extend `validate_setup_config()`

Validate `confluence_mode` first.

If omitted, treat as:

```python
"global_cluster"
```

### 8.4 Validation rules for global mode

Existing validation remains unchanged:

```text
selected_levels must be non-empty
tolerance_ticks must be a number >= 0
min_confluences must be >= 1
max_confluences must be >= min_confluences
max_confluences must be <= 5
```

### 8.5 Validation rules for anchor mode

For `anchor_rules`, validate:

```text
anchor_level must be a non-empty string
confluence_rules must be a non-empty list
min_valid_confluences must be an integer >= 1
min_valid_confluences must be <= number of confluence_rules
```

For each rule:

```text
rule.level must be a non-empty string
rule.level must not equal anchor_level
rule.tolerance_ticks must be a number >= 0
rule.required must be boolean-compatible
```

Also validate duplicate confluence levels.

Recommended rule:

```text
No duplicate confluence rule levels are allowed.
```

Rationale: duplicate rule levels would inflate valid confluence counts artificially.

### 8.6 Optional cross-check against available columns

`validate_setup_config()` currently validates structure, not whether columns exist in the current levels DataFrame.

Keep it that way for compatibility.

Column existence should be checked in UI/runtime because available columns depend on computed levels.

---

## 9. UI Changes

Modify:

```text
pages/2_Setup_Builder.py
pages/6_Signals.py
```

### 9.1 Setup Builder mode selector

Add a radio/selectbox:

```text
Confluence mode
- Global cluster
- Anchor-based rules
```

Map display labels to internal values:

```python
{
    "Global cluster": "global_cluster",
    "Anchor-based rules": "anchor_rules",
}
```

### 9.2 Global cluster UI

When mode is `global_cluster`, preserve current UI exactly:

```text
Level columns
Tolerance ticks
Min confluences
Max confluences
```

This is critical for regression safety.

### 9.3 Anchor-based UI

When mode is `anchor_rules`, show:

```text
Anchor level
Confluence levels
```

For each selected confluence level, show:

```text
Tolerance ticks
Required checkbox
```

Also show:

```text
Minimum valid confluences
```

### 9.4 Suggested UI defaults

Anchor level:

```text
First available default selected level, if available
```

Confluence levels:

```text
Suggested default levels excluding anchor level
```

Tolerance per rule:

```text
4.0 ticks
```

Required:

```text
False by default
```

Minimum valid confluences:

```text
1 or 2 depending on number of selected rules
```

Conservative default:

```python
min_valid_confluences = 1
```

Research-oriented default:

```python
min_valid_confluences = min(2, len(confluence_rules))
```

Prefer the conservative default for MVP to avoid surprising users.

### 9.5 Prevent anchor duplication

When user selects an anchor level, exclude it from the confluence-level multiselect options.

### 9.6 Signals page manual controls

The Signals page currently allows manual configuration if no saved setup is used.

For regression safety, there are two options:

#### Option A: Only support anchor mode through Setup Builder initially

This is safest.

Signals page manual controls remain global-cluster only.

If a saved setup has `confluence_mode = anchor_rules`, Signals page routes to the anchor engine.

#### Option B: Add full anchor manual controls to Signals page

This is more complete but creates more UI regression risk.

Recommended MVP: **Option A**.

Add full manual anchor controls later if needed.

---

## 10. Signal Generation Routing

Modify:

```text
pages/6_Signals.py
```

Current behavior:

```python
zones = detect_confluence_zones(
    levels_df,
    level_columns=selected_levels,
    tick_size=tick_size,
    tolerance_ticks=tolerance_ticks,
    min_confluences=min_conf,
    max_confluences=max_conf,
)
```

New behavior:

```python
confluence_mode = saved_setup.get("confluence_mode", "global_cluster") if saved_setup else "global_cluster"

if confluence_mode == "global_cluster":
    zones = detect_confluence_zones(
        levels_df,
        level_columns=selected_levels,
        tick_size=tick_size,
        tolerance_ticks=tolerance_ticks,
        min_confluences=min_conf,
        max_confluences=max_conf,
    )
elif confluence_mode == "anchor_rules":
    zones = detect_anchor_confluence_zones(
        levels_df,
        anchor_level=anchor_level,
        confluence_rules=confluence_rules,
        tick_size=tick_size,
        min_valid_confluences=min_valid_confluences,
    )
else:
    st.error(f"Unsupported confluence mode: {confluence_mode}")
    st.stop()
```

### 10.1 Preserve `generate_signals()` call

Do not change `generate_signals()` unless strictly necessary.

It should continue receiving:

```python
generate_signals(
    levels_df,
    zones=zones,
    trigger=trigger,
    direction=direction,
    tick_size=tick_size,
    trigger_params=trigger_params,
    naked_only=naked_only,
    naked_flags=naked_flags if naked_only else None,
    naked_requirement=naked_requirement,
)
```

### 10.2 Naked-level logic

Current naked-level logic uses:

```python
flag_naked_levels(..., touch_tolerance_ticks=0)
```

Do not change this in the same feature.

Reason: naked-level behavior is separate from anchor-confluence validation. Changing it would increase regression risk.

---

## 11. Testing Plan

### 11.1 Add regression tests for existing global confluence behavior

If not already present, add tests that lock current behavior of:

```python
detect_confluence_zones()
```

Important cases:

1. Empty level columns returns empty zone DataFrame.
2. Missing selected columns returns empty zone DataFrame.
3. Levels within tolerance emit a zone.
4. Levels outside tolerance do not emit a zone.
5. Duplicate prices count as independent levels.
6. `max_confluences` caps output at 5.
7. Greedy non-overlapping behavior remains unchanged.

### 11.2 Add new anchor engine tests

Create:

```text
tests/test_anchor_confluence.py
```

Minimum required tests:

#### Test 1: exact match is valid

Anchor and confluence are the same price.

Expected:

```text
one zone emitted
distance_ticks = 0
valid_confluence_count = 1
```

#### Test 2: within tolerance is valid

Anchor = `4500.00`, confluence = `4500.75`, tick size = `0.25`, tolerance = `3`.

Distance:

```text
0.75 / 0.25 = 3 ticks
```

Expected:

```text
valid
```

#### Test 3: outside tolerance is invalid

Anchor = `4500.00`, confluence = `4501.00`, tick size = `0.25`, tolerance = `3`.

Distance:

```text
1.00 / 0.25 = 4 ticks
```

Expected:

```text
no zone
```

#### Test 4: required invalid blocks setup

One required rule outside tolerance.

Expected:

```text
no zone emitted
```

#### Test 5: optional invalid does not block if minimum valid count is met

Rules:

```text
Rule A valid, optional
Rule B invalid, optional
min_valid_confluences = 1
```

Expected:

```text
zone emitted
```

#### Test 6: minimum valid count not met

Rules:

```text
Rule A valid
Rule B invalid
min_valid_confluences = 2
```

Expected:

```text
no zone
```

#### Test 7: missing anchor skips bar

Anchor price is NaN.

Expected:

```text
no zone
```

#### Test 8: missing optional confluence does not block if enough others are valid

Expected:

```text
zone emitted if min_valid_confluences is still satisfied
```

#### Test 9: missing required confluence blocks setup

Expected:

```text
no zone
```

#### Test 10: zone boundaries include anchor plus valid confluences only

Invalid optional confluence must not affect:

```text
zone_low
zone_high
zone_mid
level_names
level_prices
```

#### Test 11: tick_size <= 0 raises clear error

Expected:

```text
ValueError
```

#### Test 12: empty confluence rules returns empty DataFrame

Expected:

```text
empty zones DataFrame with expected columns
```

### 11.3 Setup validation tests

Extend existing setup tests or create:

```text
tests/test_setup_anchor_rules.py
```

Test:

1. Old config without `confluence_mode` remains valid if it was previously valid.
2. Valid `anchor_rules` config passes.
3. Missing anchor fails.
4. Empty confluence rules fail.
5. Negative tolerance fails.
6. Duplicate rule levels fail.
7. Anchor reused as confluence fails.
8. `min_valid_confluences > len(confluence_rules)` fails.
9. Invalid `confluence_mode` fails.
10. Non-boolean-compatible `required` fails.

### 11.4 UI smoke tests/manual checks

Manual checks are acceptable for Streamlit MVP if no UI test framework exists.

Checklist:

1. Existing global setup can still be created.
2. Existing global setup can still generate signals.
3. Anchor setup can be created.
4. Anchor setup appears as saved setup on Signals page.
5. Anchor setup generates zones.
6. Anchor setup generates signals.
7. Backtest works after anchor-generated signals.
8. Validation page works after anchor-generated backtest trades.
9. Report export does not fail.

---

## 12. Regression-Safe Rollout Sequence

Follow this order exactly.

### Phase 1: Lock current behavior

- Add or confirm tests for `detect_confluence_zones()`.
- Run full test suite.
- Do not change production code yet.

Expected risk: very low.

### Phase 2: Extend setup config backward-compatibly

Modify:

```text
thesistester/setup.py
```

Add:

```text
confluence_mode
anchor_level
confluence_rules
min_valid_confluences
```

Ensure old configs still validate.

Expected risk: low.

### Phase 3: Add anchor engine

Add:

```text
thesistester/engine/anchor_confluence.py
```

Add tests:

```text
tests/test_anchor_confluence.py
```

Do not connect UI yet.

Expected risk: low.

### Phase 4: Export engine

Modify:

```text
thesistester/engine/__init__.py
```

Export:

```python
from .anchor_confluence import detect_anchor_confluence_zones
```

Expected risk: low.

### Phase 5: Add Setup Builder UI

Modify:

```text
pages/2_Setup_Builder.py
```

Add mode switch.

Preserve existing global UI unchanged when mode is `global_cluster`.

Expected risk: moderate.

### Phase 6: Add Signals routing

Modify:

```text
pages/6_Signals.py
```

Route saved anchor setups to `detect_anchor_confluence_zones()`.

Keep manual Signals-page controls global-only for MVP unless explicitly needed.

Expected risk: moderate.

### Phase 7: Add diagnostics display

On Signals page, if zones contain anchor diagnostic columns, display them.

Suggested display columns:

```text
timestamp
bar_index
anchor_level
anchor_price
valid_confluence_count
level_names
level_prices
rule_results
```

Expected risk: low.

### Phase 8: Full regression pass

Run:

```bash
pytest
```

Then manually test Streamlit app flow:

```text
Data -> Levels -> Setup Builder -> Signals -> Backtest -> Validation -> Report Export
```

Expected risk: low if prior phases passed.

---

## 13. Acceptance Criteria

The implementation is complete when all of the following are true.

### 13.1 Functional acceptance criteria

- User can select `Global cluster` mode and behavior remains unchanged.
- User can select `Anchor-based rules` mode in Setup Builder.
- User can select exactly one anchor level.
- User can select one or more confluence levels.
- Each confluence level has its own `tolerance_ticks`.
- Each confluence level can be marked required or optional.
- User can set `min_valid_confluences`.
- Anchor zones are emitted only when required rules and minimum valid count are satisfied.
- Signals can be generated from anchor zones.
- Backtests can be run from anchor-generated signals.

### 13.2 Regression acceptance criteria

- Existing global cluster behavior is unchanged.
- Old setup configs without `confluence_mode` still work.
- Existing tests pass.
- New anchor tests pass.
- Backtest and validation pages do not need model-specific changes.

### 13.3 Research/auditability acceptance criteria

For anchor-generated zones, the user can inspect:

- anchor level;
- anchor price;
- valid confluence count;
- included valid confluence levels;
- per-rule validation result;
- per-rule distance in ticks;
- per-rule tolerance in ticks;
- whether each rule was required.

---

## 14. Out-of-Scope for First Version

Do not include these in the first implementation:

- database or disk persistence;
- grid search over per-confluence tolerances;
- level-family tolerance presets;
- confluence scoring or weighting;
- per-rule directionality;
- optimization of anchor-rule sets;
- changes to naked-level touch tolerance;
- changes to stop-loss/take-profit handling;
- changes to `generate_signals()` unless absolutely necessary.

These can be considered later.

---

## 15. Future Extensions

After the MVP is stable, consider adding:

### 15.1 Level-family tolerance presets

Example:

```text
Structural levels: 2 ticks
VWAP levels: 4 ticks
Profile levels: 6 ticks
Moving average levels: 8 ticks
```

This is more statistically disciplined than arbitrary per-level tuning.

### 15.2 Persistent setup library

Store setup configs to disk or a database so research setups are reproducible.

Each saved setup should include:

```text
instrument
timeframe
data range
level parameters
confluence mode
anchor rules
trigger settings
SL/TP settings
created timestamp
version
```

### 15.3 Multiple testing controls

If users later optimize many confluence combinations, add warnings or analytics for:

- number of tested variants;
- out-of-sample performance;
- walk-forward validation;
- bootstrap confidence intervals;
- permutation tests;
- deflated Sharpe / multiple-testing adjustments.

---

## 16. Recommended Implementation Checklist

Use this checklist while building.

```text
[ ] Add/verify regression tests for existing global confluence engine
[ ] Add VALID_CONFLUENCE_MODES in setup.py
[ ] Extend build_setup_config() with new optional fields
[ ] Extend validate_setup_config() for anchor_rules
[ ] Confirm old configs still validate as global_cluster
[ ] Add anchor_confluence.py
[ ] Implement detect_anchor_confluence_zones()
[ ] Add empty output schema helper
[ ] Add rule_results diagnostics
[ ] Add anchor engine tests
[ ] Export detect_anchor_confluence_zones from engine/__init__.py
[ ] Add Setup Builder confluence mode selector
[ ] Preserve existing global UI exactly
[ ] Add anchor-level selector
[ ] Add confluence-level multiselect
[ ] Add per-confluence tolerance inputs
[ ] Add per-confluence required checkboxes
[ ] Add min_valid_confluences input
[ ] Save anchor config through build_setup_config()
[ ] Add Signals page routing by confluence_mode
[ ] Keep manual Signals controls global-only for MVP
[ ] Display anchor diagnostics if available
[ ] Run pytest
[ ] Manual test global cluster flow
[ ] Manual test anchor rules flow
[ ] Manual test backtest after anchor signals
[ ] Manual test validation/report pages after anchor backtest
```

---

## 17. Final Recommendation

Implement the new model as an additive feature:

```text
Mode 1: global_cluster
Mode 2: anchor_rules
```

Do not remove or rewrite the current global clustering implementation.

The global model remains the statistically clean baseline. The new anchor-based model provides the more realistic discretionary-trading structure needed for precise thesis testing.

This additive architecture is the safest path for preserving current functionality while expanding the application toward the intended research workflow.
