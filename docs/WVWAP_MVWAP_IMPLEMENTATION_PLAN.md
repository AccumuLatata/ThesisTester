# Regression-Safe Implementation Plan: `wVWAP` + `mVWAP`

**Status:** Plan locked (not implemented)  
**Series id:** WMV  
**Document type:** Focused level-family implementation plan  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related docs:** `docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md` (gate/PIT/docs pattern), `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md` (token admission), `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

---

## 1. Purpose

Add two developing (within-period) VWAP levels as siblings of existing `dVWAP`:

```text
wVWAP    # developing VWAP of the current trading week
mVWAP    # developing VWAP of the current trading month
```

Hard availability requirement (locked):

> Both columns must be selectable in **Setup Builder / setup validation** and
> admissible as **StudySpec core/partner tokens**, the same way `dVWAP` is today.

This series is additive, stays behind the existing `session_vwap_enabled` gate
(default-off on `compute_all_levels`), and must leave legacy level/signal/backtest
outputs unchanged when that gate is disabled.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Columns | `wVWAP`, `mVWAP` |
| Family | Same developing-VWAP family as `dVWAP` / `dVWAP_RTH` |
| What they are | **Within-period** developing VWAPs (live week / live month), not prior-period freezes |
| Period keys | Identical to `wOpen` / `mOpen`: `trading_session_date` → `W-SUN` / `M` |
| Session scope | Full CME session (ETH + RTH contribute and emit) — same as `dVWAP` |
| Formula | Typical-price VWAP: `sum(tp*vol)/sum(vol)`, `tp=(H+L+C)/3` |
| Gate | Existing `session_vwap_enabled` (no new settings keys) |
| API default | `compute_all_levels(..., session_vwap_enabled=False)` still emits **no** VWAP columns |
| Product default | Already `session_vwap_enabled=True` — product computes gain two additive columns |
| Engine version | Bump `LEVEL_ENGINE_VERSION` `9 → 10` in the engine PR |
| Catalog | Append to `SESSION_VWAP_COLUMNS` (auto-flows to Study static set + Assistant catalog) |
| Suggested Setup defaults | **Do not** add `wVWAP` / `mVWAP` to `SUGGESTED_DEFAULT_LEVELS` |
| Downstream | Generic level columns — Setup / confluence / signals / backtest consume without engine changes |
| Goldens | No regeneration — `run_legacy_pipeline` never calls `compute_all_levels`; it injects prebuilt signals into `simulate_trades` |

**Feasibility:** High. Math is the existing `dVWAP` loop with a different group key.
Closest precedents: `dVWAP` (CME-session sibling of `dVWAP_RTH`) and `wOpen`/`mOpen`
period keys.

---

## 3. Locked product definition

### 3.1 What `wVWAP` / `mVWAP` are

For each bar `t`:

1. Assign a **trading-session date** via `trading_session_date(local_ts, eth_start)`.
2. Map that date to a **week key** `W-SUN` or **month key** `M` — the same
   construction already used by `compute_session_levels` / `compute_profile_levels`.
3. Emit the cumulative typical-price VWAP of all bars in that period with
   timestamp `≤ t` (including ETH and RTH).

Verbal definition:

> `wVWAP` is the developing VWAP of the current CME trading week.  
> `mVWAP` is the developing VWAP of the current CME trading month.

They are the weekly/monthly analogs of `dVWAP`, just as `wOpen` / `mOpen` are
the weekly/monthly analogs of `dOpen`.

### 3.2 What they are not

| Existing / tempting concept | Why it is not this work |
|---|---|
| `VWAP_rolling_*` | Sliding lookback; not calendar-week/month anchored |
| `dVWAP` | Resets every CME **session**, not every week/month |
| `dVWAP_RTH` | RTH-only; NaN on ETH |
| `wOpen` / `mOpen` | First print of the period, not a volume-weighted average |
| `pwVAH` / `pwPOC` / `pmVAH` / `pmPOC` | **Prior**-period frozen profiles, not developing |
| Hypothetical `pwVWAP` / `pmVWAP` | Prior-week/month **frozen** VWAP — different family; **out of scope** |
| Hypothetical `wVWAP_RTH` / `mVWAP_RTH` | RTH-only HTF VWAPs — **out of scope** |

Do **not** mutate rolling VWAP, `dVWAP`, `dVWAP_RTH`, or prior-profile math.

### 3.3 Period boundaries (normative — must match `wOpen` / `mOpen`)

Copy the existing two-liner; do **not** invent a second week/month model.

```text
session_date    = trading_session_date(local_ts, eth_start)
session_date_ts = pd.to_datetime(session_date)
week_key        = session_date_ts.dt.to_period("W-SUN")
month_key       = session_date_ts.dt.to_period("M")
```

Implementation constraint: `compute_session_vwap_levels` already computes
`session_date` for the `dVWAP` groupby. Derive `week_key` / `month_key` from
**that same Series**. Do not call `trading_session_date` a second time on a
different path.

Verified fixtures (America/New_York, ES `eth_start=18:00`; also proven in
`tests/test_session_levels.py`):

| Timestamp | `session_date` | `W-SUN` | `M` |
|---|---|---|---|
| `2026-06-07 17:59` | `2026-06-07` | `2026-06-01/07` | `2026-06` |
| `2026-06-07 18:00` (Sunday ETH open) | `2026-06-08` | `2026-06-08/14` | `2026-06` |
| `2026-06-30 17:59` | `2026-06-30` | `2026-06-29/07-05` | `2026-06` |
| `2026-06-30 18:00` | `2026-07-01` | `2026-06-29/07-05` | `2026-07` |

| Event | Timestamp (America/New_York) | Effect |
|---|---|---|
| Week roll | `2026-06-07 18:00` | New `wOpen`; `wVWAP` must reset here |
| Month roll | `2026-06-30 18:00` | New `mOpen`; `mVWAP` must reset here |

If `eth_start` is empty, `trading_session_date` already falls back to calendar
date — use that same fallback (do not raise). This matches `dVWAP`.

**Forbidden:** ISO week (`W-MON`), calendar-midnight weeks, RTH-open weeks, or
any period key that would desynchronize `wVWAP` from `wOpen`.

### 3.4 VWAP formula (normative)

Identical typical-price convention as `dVWAP`:

```text
typical_price = (high + low + close) / 3
wVWAP[t]      = cumsum(tp * volume)[t] / cumsum(volume)[t]   # within week_key
mVWAP[t]      = cumsum(tp * volume)[t] / cumsum(volume)[t]   # within month_key
```

`cumsum` resets at each new period key. At bar `t`, only bars at or before `t`
in the same period are used.

| Case | Behavior |
|---|---|
| `sum(volume) == 0` so far in the period | Emit `NaN` (same as `dVWAP`) |
| ETH bars | Contribute and emit (same as `dVWAP`) |
| Gaps / holidays | Use available bars only; do not synthesize |
| Unsorted input | Sort by timestamp internally (existing `session_vwap.py` contract) |
| Disabled gate | Empty DataFrame; no validation; no columns |

### 3.5 Gate and column set (normative)

When `session_vwap_enabled=True`, `compute_session_vwap_levels` emits **exactly**:

```text
dVWAP_RTH
dVWAP
wVWAP
mVWAP
```

in that order. `SESSION_VWAP_COLUMNS` becomes that four-tuple. That exact
four-tuple is the **session-VWAP family frame**, not the full
`compute_all_levels` output. `compute_all_levels(..., session_vwap_enabled=True)`
is additive: the two new names appear **in** the joined frame alongside every
other enabled family.

When `session_vwap_enabled=False` (the `compute_all_levels` default): **none** of
those columns are emitted. Existing disabled isolation tests stay valid after
updating the `compute_session_vwap_levels` “enabled column list” from two names
to four.

No new kwargs on `compute_all_levels`. No new `DEFAULT_LEVELS_SETTINGS` keys.
No new `st.session_state` widget keys.

`session_vwap_anchor` remains validate-only (`SUPPORTED_VWAP_ANCHORS=("RTH",)`).
It does not change grouping for `dVWAP`, `wVWAP`, or `mVWAP`. Do **not** start
using it to RTH-mask the new columns. The RTH column continues to use
`session=="RTH"`.

### 3.6 Why the same gate (not a new flag)

| Option | Verdict |
|---|---|
| New `weekly_monthly_vwap_enabled` | Rejected — extra settings/UI/schema surface for siblings of an already-gated family |
| Always-on like `wOpen` | Rejected — would emit columns from `compute_all_levels` with all gates off; breaks Stage 1 no-op |
| Same `session_vwap_enabled` | **Locked** — exact precedent of adding `dVWAP` beside `dVWAP_RTH` |

Headless / product frames via `DEFAULT_LEVELS_SETTINGS` already set
`session_vwap_enabled=True`. Raw `compute_all_levels(...)` still defaults
`session_vwap_enabled=False` and must stay default-off. After WMV1, a
product-default levels frame gains two additive columns. Setups that do not
select them produce identical signals and trades (generic column consumption).

---

## 4. Setup and Study availability (locked)

This is the hard product requirement. Both surfaces already consume **catalog /
frame columns generically**. The work is to emit the columns and register the
tokens — not to add setup- or study-specific VWAP logic.

### 4.1 Setup Builder / setup validation

| Mechanism | What must happen |
|---|---|
| Emission | With the family enabled, `wVWAP` / `mVWAP` appear on the levels frame |
| Eligibility | `is_setup_eligible_level_column` / `available_level_columns` include them (they are price columns, not diagnostics) |
| Validation | `validate_setup_config` accepts `selected_levels` / `anchor_level` / confluence-rule `level` of `wVWAP` or `mVWAP` (not in `BASE_COLUMNS` or `NON_LEVEL_OUTPUT_COLUMNS`) |
| UI | Setup Builder and Signals multiselects list them once the frame has the columns — no page-specific allowlist to edit |
| Suggested defaults | **Do not** add them to `SUGGESTED_DEFAULT_LEVELS` (LC3: suggested list ⊆ `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` stays true either way; adding them would change new-setup defaults) |

Missing-column honesty stays LC4: a saved setup that names `wVWAP` against a
frame computed with `session_vwap_enabled=False` fail-closes at
`generate_signals` / `run_experiment`. That is correct, same as `dVWAP` today.

### 4.2 Study Runner / Study Builder

| Mechanism | What must happen |
|---|---|
| Static catalog | `SESSION_VWAP_COLUMNS` grows → `STATIC_STUDY_LEVEL_NAMES` / `STUDY_STATIC_LEVEL_NAMES` grow |
| `closed_level_token_set` | Always includes `wVWAP` and `mVWAP` (session-VWAP tokens are **static**, not flag-gated — LC4 honesty: validate admits; generate fail-closes if the gate is off) |
| StudySpec | `factors.core_level` / `factors.partner_levels` may name `wVWAP` / `mVWAP` |
| Study Builder | `builder_token_catalog` is `closed_level_token_set` — tokens appear automatically |
| `study.levels` keys | **No new keys.** Unknown-key allowlist stays `DEFAULT_LEVELS_SETTINGS` |

Do **not** start gating `dVWAP*` / `wVWAP` / `mVWAP` inside
`closed_level_token_set`. That would reopen LC4.

### 4.3 Assistant catalog (automatic)

`SESSION_LEVEL_CATALOG` splices `SESSION_VWAP_LEVEL_NAMES`. Updating
`SESSION_VWAP_COLUMNS` updates the assistant token list. The existing slice
test `catalog[dvwap : dvwap + 2]` must become `dvwap : dvwap + len(...)`.

Thesis-compiler mention of `wvwap` / `mvwap` is **WMV2 only**. Detection today
is `re.search(r"\bdvwap\b", prompt.lower())`, which does **not** match `wvwap`
or `mvwap`. WMV2 must extend that same `if` and keep the existing unresolved
string byte-identical (see WMV2 scope). Not required for Setup/Study
availability.

---

## 5. Architecture and file plan

### 5.1 Engine (WMV1)

Extend `thesistester/levels/session_vwap.py` only. **No new module.**

```python
COL_WVWAP = "wVWAP"
COL_MVWAP = "mVWAP"
SESSION_VWAP_COLUMNS = (COL_DVWAP_RTH, COL_DVWAP, COL_WVWAP, COL_MVWAP)
```

Implementation constraint (regression-safe):

- **Copy** the existing **`dVWAP`** groupby/`cumsum` loop (full session) for
  week and month. Do **not** copy the `dVWAP_RTH` RTH-mask loop.
- Derive `week_key` / `month_key` from the already-computed `session_date`.
- Update the module docstring and `compute_session_vwap_levels` return contract
  (they currently say the enabled path emits both `dVWAP_RTH` and `dVWAP`).
- **Do not** refactor the `dVWAP` / `dVWAP_RTH` loops “while we’re here.”
- Comment the period-key two-liner as identical to `sessions.py` / `profile.py`.
- Do **not** extract a shared `trading_week_key` helper in this series
  (would touch `sessions.py` + `profile.py` for no user-visible gain).

### 5.2 Wiring (automatic vs explicit)

| File | Change in WMV1? | Notes |
|---|---|---|
| `thesistester/levels/session_vwap.py` | Yes | Module docstring, `SESSION_VWAP_COLUMNS`, emit loops, return contract |
| `thesistester/levels/catalog.py` | No edit | Re-exports `SESSION_VWAP_COLUMNS` |
| `thesistester/levels/all.py` | Docstring only | Mention `wVWAP` / `mVWAP` under the existing gate. Join is already additive by new column names. |
| `thesistester/levels/defaults.py` | **No** | Product default already `session_vwap_enabled=True` |
| `thesistester/persistence/local_store.py` | Yes | `LEVEL_ENGINE_VERSION = 10` |
| `thesistester/setup.py` | **No** | Eligibility is generic |
| `thesistester/study/schema.py` | **No** | Static set follows catalog |
| `thesistester/study/builder.py` | **No** | `builder_token_catalog` follows closed set |
| `thesistester/assistant/workspace.py` | **No** | Production `SESSION_LEVEL_CATALOG` unpacks `SESSION_VWAP_LEVEL_NAMES`. Do not hand-edit that tuple. The slice test lives in `tests/test_assistant_workspace.py`. |
| `thesistester/api.py` | **No** | Already passes `session_vwap_enabled` |
| `pages/2_Levels.py` | WMV2 | Checkbox / help copy only. Reuse `_SESSION_VWAP_ENABLED_KEY`. |
| `pages/14_Research_Assistant.py` | WMV2 | Checkbox label only |
| `thesistester/assistant/thesis_compiler.py` | WMV2 | Required: add `\bwvwap\b` / `\bmvwap\b` to the existing `if`. Keep the unresolved string byte-identical. |

### 5.3 Downstream consumption

No confluence / signal / backtest / OTF / study-execute code changes.
`wVWAP` and `mVWAP` are ordinary scalar price columns.

---

## 6. Identity / cache

- No new settings keys → levels-settings hash shape unchanged.
- `LEVEL_ENGINE_VERSION` `9 → 10` invalidates persisted snapshots computed
  under v9 so product-default caches cannot reuse a frame that lacks the new
  vocabulary (same reason `dVWAP` bumped 8 → 9).
- Research-identity tests that assert `>= 9` stay valid; add `>= 10` next to
  the existing `test_dvwap_cme_session.py` version assert (or a sibling).

---

## 7. Point-in-time guarantees

Normative PIT claims (must be tested):

1. At bar `t`, `wVWAP` uses only bars `≤ t` with the same `week_key`.
2. At bar `t`, `mVWAP` uses only bars `≤ t` with the same `month_key`.
3. Appending future bars (same period or next period) must not change any
   prior row’s `wVWAP` / `mVWAP`.
4. A week (month) reset must not carry the previous period’s last value.
5. `dVWAP` and `dVWAP_RTH` values must be **series-equal** to pre-change
   outputs on the same fixture when the gate is on.

Register two rows in `docs/POINT_IN_TIME_GUARANTEES.md` in WMV1.

---

## 8. Regression-safety framework mapping

Maps to `ENGINEERING_PROPOSAL.md` §4:

| Rule | Application here |
|---|---|
| 1. Additive-only | No new kwargs; no positional signature changes |
| 2. Golden-masters | `run_legacy_pipeline` never calls `compute_all_levels`; goldens stay untouched |
| 3. Opt-in default-off | `compute_all_levels` keeps `session_vwap_enabled=False` |
| 4. Schema / engine version | `LEVEL_ENGINE_VERSION = 10` |
| 5. Future-shock PIT | Dedicated tests in `tests/test_wvwap_mvwap.py` |
| 6. `session_state` stability | **No new keys** |
| 7. Determinism | Pure pandas/numpy; no randomness |
| 8. Same-PR docs | §10 list per PR |
| 9. CI green | Full pytest + ruff |
| 10. Honesty | Bar typical-price VWAP, not tick VWAP; developing ≠ prior |

### 8.1 Non-regression contract (normative)

| Surface | Required outcome |
|---|---|
| `dVWAP_RTH` / `dVWAP` | **Value-identical** on every overlapping row when the family is enabled |
| Other level families | **Value-identical**; new columns only |
| Signal / 3c / OTF / `simulate_trades` | **Untouched** |
| Confluence / naked / Setup semantics | Unchanged except two additional selectable price columns when computed |
| `SUGGESTED_DEFAULT_LEVELS` | **Unchanged** — new setups do not silently start selecting HTF VWAPs |
| Study schema version | Stays `1`; no new `study.levels` keys |
| Persistence | Engine version bump only (intentional cache invalidation) |
| UI (WMV1) | No widget/key/layout changes |
| Goldens | No regen |

**Allowed intentional deltas:**

1. Four VWAP columns instead of two when the existing gate is on.
2. Static Study / Assistant catalogs gain `wVWAP` and `mVWAP`.
3. `LEVEL_ENGINE_VERSION` 9 → 10.

**Forbidden:**

- New gates, new rolling windows, RTH-only HTF VWAPs, prior-week/month VWAP.
- Refactoring `sessions.py` / `profile.py` / `dVWAP` loops.
- Changing `SUGGESTED_DEFAULT_LEVELS`.
- Gating session-VWAP tokens inside `closed_level_token_set`.
- Help-path moves. Drive-by assistant/CAI/RUX edits.

---

## 9. Scoped PRs

Three PRs. Do not merge WMV2 before WMV1. Do not implement engine work in WMV0.

### WMV0 — Plan lock (this PR)

| Field | Value |
|---|---|
| **Title** | `WMV0: lock wVWAP/mVWAP implementation plan` |
| **Scope** | `docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md`; index lines in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md` |
| **Behavior** | Documentation only. No `.py` changes |
| **Regression** | Docs-only; no goldens; no `LEVEL_ENGINE_VERSION` |
| **Acceptance** | Plan contains locked semantics (§3), Setup/Study admission (§4), PIT claims (§7), and copy-ready WMV1/WMV2 prompts (§12) |
| **Out of scope** | Any engine/UI/test implementation |

### WMV1 — Engine + catalog + Setup/Study tests

| Field | Value |
|---|---|
| **Title** | `WMV1: emit wVWAP/mVWAP under session_vwap_enabled` |
| **Scope** | `thesistester/levels/session_vwap.py`; `thesistester/levels/all.py` (docstring); `thesistester/persistence/local_store.py` (`LEVEL_ENGINE_VERSION = 10`); `tests/test_wvwap_mvwap.py` (new); targeted edits to existing assertions that hard-code the two-column VWAP set; Setup + Study token tests; living docs in §10.1 |
| **Likely test edits** | `tests/test_stage3_session_vwap.py` (enabled column list → exact four-tuple); `tests/test_dvwap_cme_session.py` (isolation stays green if additive; add `LEVEL_ENGINE_VERSION >= 10`); `tests/test_stage6_levels_ui_settings.py` (enable-case membership must include `wVWAP`/`mVWAP`; those tests do **not** pin an exact column tuple or checkbox copy); `tests/test_assistant_workspace.py` (`catalog[dvwap : dvwap + 2]` → `+ 4` or `+ len(SESSION_VWAP_LEVEL_NAMES)`); `tests/test_setup_config.py`; `tests/study/test_study_schema.py` |
| **Behavior** | Gate off: still no VWAP columns. Gate on: four columns; `dVWAP*` values unchanged. `wVWAP`/`mVWAP` are setup-eligible and Study static tokens |
| **Regression** | Overlapping-column equality; disabled no-op; legacy goldens untouched; no new settings keys |
| **Acceptance** | §11.1–11.4 tests green; `pytest -q tests/test_wvwap_mvwap.py tests/test_stage3_session_vwap.py tests/test_dvwap_cme_session.py tests/test_stage6_levels_ui_settings.py tests/test_setup_config.py tests/study/test_study_schema.py tests/test_assistant_workspace.py tests/test_golden_master.py` plus full `pytest -q` / ruff |
| **Out of scope** | UI copy; `docs/ARCHITECTURE.md` Levels-control table; thesis compiler; USER_GUIDE how-to; new flags; `SUGGESTED_DEFAULT_LEVELS`; period-key extraction; `pwVWAP` / RTH-only HTF |

**WMV1 file-level checklist**

1. Emit `wVWAP` / `mVWAP` in `compute_session_vwap_levels` when `enabled=True`.
   Copy the `dVWAP` loop; derive week/month keys from the existing `session_date`;
   update the module docstring / return contract.
2. Set `SESSION_VWAP_COLUMNS` to the four-tuple (catalog/study/assistant follow).
3. Bump `LEVEL_ENGINE_VERSION` to 10.
4. Prove math, week/month reset alignment with `wOpen`/`mOpen`, ETH emission, zero-volume NaN, future-shock, and `dVWAP*` isolation.
5. Prove Setup: `available_level_columns` includes them; `validate_setup_config` accepts them as `selected_levels` and as `anchor_level`.
6. Prove Study: `wVWAP`/`mVWAP` ∈ `STUDY_STATIC_LEVEL_NAMES` and
   `closed_level_token_set({...gates off...})`; a minimal StudySpec with
   `core_level: [wVWAP]` and one with `partner_levels: [[mVWAP]]` validates.
7. Same-PR docs in §10.1.

### WMV2 — Product copy + thesis hint

| Field | Value |
|---|---|
| **Title** | `WMV2: document wVWAP/mVWAP on Levels/Assistant/Help` |
| **Scope** | `pages/2_Levels.py` checkbox label + help; `pages/14_Research_Assistant.py` checkbox label; `thesistester/assistant/thesis_compiler.py` (see locked copy below); `docs/USER_GUIDE.md`; `docs/STUDY_RUNNER.md` (honesty if living text still implies daily-only; current text is already generic); `docs/ARCHITECTURE.md` Levels-control table row text (**WMV2 owns this row**, not WMV1); `README.md` advanced-levels bullet; `tests/test_thesis_compiler.py` (one additive case). No stage-6 test currently pins the checkbox string. |
| **Behavior** | Labels mention `wVWAP` + `mVWAP`. No compute change |
| **Regression** | No engine/golden/`LEVEL_ENGINE_VERSION` touch. Existing `dVWAP` thesis-compiler cases still pass (`"dVWAP" in item`) |
| **Acceptance** | Checkbox strings include both new names; a `wVWAP`/`mVWAP` prompt without the family enabled appends the existing unresolved string; Help/USER_GUIDE list the columns |
| **Out of scope** | Engine math; new widgets; new session_state keys; suggested-default changes |

Thesis-compiler lock (`thesistester/assistant/thesis_compiler.py`):

- Detection today is `re.search(r"\bdvwap\b", prompt.lower())`. That does
  **not** match `wvwap` or `mvwap` (`_` is a word character, so it also does
  not match `dvwap_rth`).
- WMV2 **must** add `\bwvwap\b` and `\bmvwap\b` to the **same** `if` that
  appends the existing unresolved string. One combined regex is fine.
- Keep the existing unresolved string **byte-identical**:
  `"Enable developing session VWAPs for the dVWAP thesis."`
  Existing `tests/test_thesis_compiler.py` asserts `"dVWAP" in item`. Do not
  invent a second unresolved-string family. A wVWAP-only prompt will then
  receive the dVWAP wording; that copy wart is locked unless a later PR
  extends the string while still containing the substring `"dVWAP"`.

WMV2 may be folded into WMV1 only if WMV1 is already green and the copy diff
stays label-only. Prefer the split so engine review is not mixed with Help copy.

---

## 10. Documentation updates

### 10.1 Same PR as WMV1 (engine contract)

| Doc | Update |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Extend §5b: `wVWAP`/`mVWAP` developing week/month; same typical-price caveat; `LEVEL_ENGINE_VERSION` 10 |
| `docs/POINT_IN_TIME_GUARANTEES.md` | Module blurb + two audit rows + tests column |
| `docs/METRICS_GLOSSARY.md` | Add `wVWAP` / `mVWAP` rows under the developing-VWAP table; gate text becomes “all four columns” |
| `docs/ENGINEERING_ROADMAP.md` | Mark WMV1 landed when merged |
| This doc | Status → WMV1 implemented |

### 10.2 Same PR as WMV2 (Help / UI)

| Doc | Update |
|---|---|
| `docs/USER_GUIDE.md` | Advanced opt-in list includes weekly/monthly developing VWAPs |
| `docs/STUDY_RUNNER.md` | Static catalog sentence mentions `wVWAP` / `mVWAP` if living text still implies daily-only |
| `docs/ARCHITECTURE.md` | Levels-control table quotes the Levels checkbox. **WMV2 owns this row.** |
| `README.md` | Advanced levels bullet |
| This doc | Status → series complete |

Do **not** amend archived `docs/archive/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md`
beyond a one-line pointer if a reviewer wants it; living contract is this file.

---

## 11. Test plan (normative)

New file:

```text
tests/test_wvwap_mvwap.py
```

Reuse the Stage 3 / CME-session bar helpers or the `wOpen`/`mOpen` fixtures.
Hand-compute expected VWAP values; do not snapshot opaque frames.

### 11.1 Gate / isolation

1. Disabled → empty frame, no `wVWAP`/`mVWAP`, no validation (naive timestamps accepted).
2. `compute_all_levels(..., session_vwap_enabled=False)` adds none of the four VWAP columns.
3. `list(compute_session_vwap_levels(..., enabled=True).columns) == ["dVWAP_RTH", "dVWAP", "wVWAP", "mVWAP"]` (exact order). `compute_all_levels(..., session_vwap_enabled=True)` and `tests/test_stage6_levels_ui_settings.py` enable-case asserts are **membership**: `"wVWAP" in columns` and `"mVWAP" in columns`. Do not require the joined frame to contain only those four columns.
4. Enabled → `dVWAP_RTH` and `dVWAP` series-equal to a fixture computed against
   current formulas (copy the existing CME-session expected vectors).
5. Enabled → other families (`wOpen`, `pdPOC`, pivots off, etc.) value-identical
   on overlapping columns.

### 11.2 Math / boundaries

6. Exact `wVWAP` / `mVWAP` on a controlled intra-period fixture (hand-computed).
7. `wVWAP` resets at `2026-06-07 18:00`; first new-week value equals that bar’s
   own typical-price VWAP, not the prior week’s last value.
8. `mVWAP` resets at `2026-06-30 18:00`; same first-bar property.
9. On the `wOpen` / `mOpen` fixtures, period membership of `wVWAP`/`mVWAP`
   matches `wOpen`/`mOpen` (new period starts on the same bar).
10. ETH bars emit non-NaN when cumulative period volume `> 0`.
11. Zero-volume prefix emits `NaN`, then defined values after first positive volume.

### 11.3 PIT

12. Future-shock within the same week (append later week bars → prior `wVWAP` unchanged).
13. Future-shock across a week boundary.
14. Future-shock within the same month and across a month boundary.
15. Mid-period truncation: do not finalize using “end of dataframe” (same as `dVWAP`).

### 11.4 Setup + Study (must ship in WMV1)

16. `available_level_columns` on a frame that includes `wVWAP`/`mVWAP` returns both;
    they are not in `NON_LEVEL_OUTPUT_COLUMNS`.
17. `validate_setup_config` with `selected_levels=["wVWAP"]` (and separately
    `["mVWAP"]`) returns no errors; same for `anchor_rules` with
    `anchor_level="wVWAP"` and a confluence rule on `mVWAP`.
18. `set(SUGGESTED_DEFAULT_LEVELS) <= closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`
    still holds; `wVWAP`/`mVWAP` are **not** in `SUGGESTED_DEFAULT_LEVELS`.
19. `{"wVWAP", "mVWAP"} <= STUDY_STATIC_LEVEL_NAMES`.
20. `closed_level_token_set` with `session_vwap_enabled` omitted or `False` still
    contains `wVWAP` and `mVWAP` (static, like `dVWAP`).
21. Minimal StudySpec `core_level: ["wVWAP"]` validates; `partner_levels: [["mVWAP"]]`
    validates; `core_level: ["notAVWAP"]` still fail-closes.
22. Assistant catalog: `SESSION_VWAP_LEVEL_NAMES` appears as a contiguous slice
    of length 4 after `PRIOR_PROFILE_LEVEL_NAMES`.

### 11.5 WMV2 only

23. Thesis compiler: prompt containing `wVWAP` or `mVWAP` without
    `session_vwap_enabled` adds the existing enable-family assumption.
24. UI/AST tests that pin the Levels checkbox string, if any, accept the new copy.

---

## 12. Copy-ready implementation prompts

### 12.1 WMV1

```text
Implement WMV1 from docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md.

Work regression-safe (docs/ENGINEERING_PROPOSAL.md §4). Extend
thesistester/levels/session_vwap.py so session_vwap_enabled=True emits
dVWAP_RTH, dVWAP, wVWAP, mVWAP in that order. wVWAP/mVWAP are developing
typical-price VWAPs grouped by the same trading_session_date → W-SUN / M
keys as wOpen/mOpen (sessions.py). ETH+RTH contribute and emit. Copy the
existing dVWAP cumsum loop; do not refactor dVWAP/dVWAP_RTH.

Update SESSION_VWAP_COLUMNS (catalog/study/assistant follow). Bump
LEVEL_ENGINE_VERSION 9 → 10. No new compute_all_levels kwargs, no new
DEFAULT_LEVELS_SETTINGS keys, no SUGGESTED_DEFAULT_LEVELS edits, no new
session_state keys, no golden regen, no pwVWAP, no RTH-only HTF VWAPs.

Add tests/test_wvwap_mvwap.py covering §11.1–11.4. Update hard-coded
two-column VWAP assertions. Prove Setup validate + StudySpec tokens.

Same-PR docs: ASSUMPTIONS §5b, POINT_IN_TIME_GUARANTEES, METRICS_GLOSSARY,
roadmap WMV1 status. Do not edit the ARCHITECTURE Levels-control table
in WMV1 (WMV2 owns that checkbox-copy row).

PR body must include a Regression safety paragraph: disabled no-op
preserved; dVWAP* value-identical; goldens untouched (run_legacy_pipeline
never calls compute_all_levels); cache bump is vocabulary-only.
```

### 12.2 WMV2

```text
Implement WMV2 from docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md.

No engine/, no LEVEL_ENGINE_VERSION, no goldens. Update Levels + Assistant
checkbox copy to name dVWAP_RTH + dVWAP + wVWAP + mVWAP. Update the
ARCHITECTURE Levels-control table to quote that checkbox. Add
\bwvwap\b / \bmvwap\b (or one combined regex) to the same thesis_compiler
if that already handles \bdvwap\b. Keep the unresolved string
byte-identical: "Enable developing session VWAPs for the dVWAP thesis."
Do not invent a new unresolved string family. Update USER_GUIDE,
STUDY_RUNNER if needed, README advanced-levels bullet.

Keep Help paths unchanged. Add one thesis-compiler test (wVWAP or mVWAP
prompt without the family enabled). Existing dVWAP cases must still pass.
Mark this plan series complete.
```

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Week/month key drift vs `wOpen` | Same two-liner; alignment test on the existing Sunday-open / month-open fixtures |
| Accidental RTH NaN-gating copied from `dVWAP_RTH` | ETH emission tests; code review checklist |
| Silent change to new-setup defaults | Forbidden `SUGGESTED_DEFAULT_LEVELS` edit; LC3 subset test stays |
| Catalog/engine name drift | Single tuple `SESSION_VWAP_COLUMNS` remains SoT |
| Reviewers confuse developing vs prior VWAP | §3.2 table; glossary wording “current week/month”, not “prior” |
| Product-default frame column growth surprises caches | `LEVEL_ENGINE_VERSION` 10 |

---

## 14. Explicit non-goals

- Prior-week / prior-month frozen VWAP (`pwVWAP`, `pmVWAP`)
- RTH-only weekly/monthly VWAP (`wVWAP_RTH`, `mVWAP_RTH`)
- New settings keys, widgets, or session_state keys
- Adding `wVWAP`/`mVWAP` to `SUGGESTED_DEFAULT_LEVELS`
- Gating session-VWAP tokens in `closed_level_token_set`
- Shared period-key extraction from `sessions.py` / `profile.py`
- Using vestigial `session_vwap_anchor` to change `wVWAP` / `mVWAP` grouping
- Signal-engine, fill-model, golden, or Help-path changes
- Thesis-compiler work in WMV1
- Editing `docs/ARCHITECTURE.md` Levels-control table in WMV1

---

## 15. Per-PR acceptance checklist (§4.2)

Mandatory for WMV1 (engine):

- [ ] Unit tests for exact values, week/month reset, ETH emission, zero-volume
- [ ] Future-shock tests (same period + across boundary)
- [ ] `dVWAP*` isolation (series-equal)
- [ ] Disabled no-op
- [ ] Setup eligibility + `validate_setup_config` accepts `wVWAP`/`mVWAP`
- [ ] Study static token + StudySpec core/partner validate
- [ ] Legacy golden-masters preserved
- [ ] Docs updated in the same PR
- [ ] PR body contains a short “Regression safety” paragraph
- [ ] Narrow surface; no drive-by refactors

Mandatory for WMV2 (copy):

- [ ] UI/Help strings name both new columns
- [ ] Thesis-compiler test; existing `dVWAP` cases still pass
- [ ] No engine or golden touch
