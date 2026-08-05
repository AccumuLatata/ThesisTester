# Regression-Safe Implementation Plan: `prev4hVWAP`

**Status:** Phase 0 — plan lock (not implemented)  

**Document type:** Focused level-family implementation plan  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related docs:** `docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md` (normative parent), `docs/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md`, `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

**Intent:** Implement the **exact same** previous-period VWAP level family as `prev30mVWAP`, with the sole product change that brackets are **4 hours** instead of 30 minutes.

---

## 1. Purpose

Add a new scalar level family:

```text
prev4hVWAP
```

Definition (product intent — identical to prev30m, period length changed):

1. **Level** — the final price of the just-completed **4-hour** VWAP, frozen at the open of the next 4-hour period.
2. **Early-window hit diagnostics** — whether that level was range-touched within the first **1 minute** and first **5 minutes** of the new 4-hour period (plus optional R analytics on those finalized flags).
3. **Validity TTL / stack depth** — frozen level(s) remain valid for a configurable number of subsequent **4-hour** periods; `N > 1` also emits stack columns for confluence.

Hard availability requirement (locked — same as prev30m):

> Available for the **entire trading session (ETH + RTH)**.  
> Not RTH-only.

Additive, opt-in, default-off at the `compute_all_levels` API boundary. Legacy level/signal/backtest outputs unchanged when the gate is disabled.

---

## 2. Normative inheritance from `prev30mVWAP`

**Unless a row in §3 explicitly overrides it, every locked contract in**
`docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md` **applies verbatim with the
substitutions in §2.1.**

Do **not** re-open session clock, halt finalization, PIT, eligibility, or
formula debates. Those were locked and proven for Stage 8.

### 2.1 Mechanical substitutions

| prev30m token | prev4h token |
|---|---|
| `prev30mVWAP` | `prev4hVWAP` |
| `prev30mVWAP_2` … `_N` | `prev4hVWAP_2` … `_N` |
| `prev30mVWAP_hit_m1` / `_hit_m5` | `prev4hVWAP_hit_m1` / `_hit_m5` |
| `prev30m_vwap_enabled` | `prev4h_vwap_enabled` |
| `prev30m_vwap_validity_periods` | `prev4h_vwap_validity_periods` |
| `BRACKET_MINUTES = 30` | `BRACKET_MINUTES = 240` |
| `thesistester/levels/prev30m_vwap.py` | `thesistester/levels/prev4h_vwap.py` |
| `thesistester/analytics/prev30m_vwap_hit.py` | `thesistester/analytics/prev4h_vwap_hit.py` |
| `tests/test_prev30m_vwap.py` | `tests/test_prev4h_vwap.py` |
| `tests/test_prev30m_vwap_hit_analytics.py` | `tests/test_prev4h_vwap_hit_analytics.py` |
| Stage 8 | Stage 9 |

### 2.2 Inherited locks (do not change)

- Session-open (`eth_start`) bracket clock; fail closed if `eth_start` missing.
- ETH + RTH contribute and emit.
- Typical-price VWAP: `tp=(H+L+C)/3`.
- Completion: clock (`timestamp >= bracket_end`) **or** true session transition; **no** mid-session dataset-end finalize.
- Cross-session seed of prior freeze history (up to `N`).
- TTL / replace-on-new-freeze for age-1; stack ages `2…N` when `N > 1`.
- Hit diagnostics: NaN until window completes; nesting `m1=1 ⇒ m5=1`; compute only when `W` is an integer multiple of base interval; denylisted from setup/chart.
- Hit R analytics on **age-1 only**; no `simulate_trades` changes.
- Disabled path: empty frame, no validation, no columns.
- Product defaults may enable; API kwargs default `False` / `1`.

---

## 3. Explicit deltas vs prev30m (only these)

| Topic | prev30m | prev4h (this plan) |
|---|---|---|
| Bracket length | 30 minutes | **240 minutes (4h)** |
| Module / columns / settings | `prev30m*` | `prev4h*` (§2.1) |
| Engine version bump | landed at 5 (after Phase 3) | **5 → 6** in Phase 1 implementation PR |
| Worked example clock | 18:00 / 18:30 / … | 18:00 / 22:00 / 02:00 / 06:00 / 10:00 / 14:00 (see §4) |
| Implementation approach | Dedicated module | **Dedicated module** (clone + parameterize locally). Optional later extraction of shared session-bracket VWAP helper only if behavior-neutral and separately golden-gated — **not** required for MVP. |
| Coexistence | — | Both families may be enabled simultaneously; columns and settings must not collide |

**Forbidden shortcuts:**

- Do not implement prev4h by calling rolling `VWAP_rolling_4h` or mutating it into a freeze.
- Do not reuse RTH-open TPO/APOC brackets.
- Do not share mutable state with `prev30m_vwap.py`.
- Do not rename camelCase product columns to snake_case.

---

## 4. 4h bracket clock (worked example, ES)

Session open: `18:00` exchange-local. Session-open 4h brackets:

| Bracket idx | Local window | Notes |
|---|---|---|
| 0 | 18:00–22:00 | ETH |
| 1 | 22:00–02:00 | ETH overnight |
| 2 | 02:00–06:00 | ETH |
| 3 | 06:00–10:00 | crosses into RTH at 09:30 — **no reset** |
| 4 | 10:00–14:00 | RTH |
| 5 | 14:00–18:00 | Partial vs CME ~17:00 halt → **session-boundary finalize** |

Verbal timeline:

| Clock | Event |
|---|---|
| 18:00–22:00 | Bracket 0 developing; `prev4hVWAP` = prior-session seed (or NaN) |
| 22:00 first bar | Bracket 0 completes → freeze `V0`; emit `prev4hVWAP = V0` |
| 22:00–22:01 / 22:05 | Evaluate `hit_m1` / `hit_m5` vs `V0` (same PIT rules as prev30m) |
| 09:30 RTH open | **No reset**; still on session-open 4h clock |
| ~14:00–17:00 | Final in-session bracket; finalize at session transition if no in-session `>= 18:00` bar |
| Next session 18:00 | Seed = prior-session freeze history (up to `N`); fresh TTL |

---

## 5. Executive summary

| Item | Decision |
|---|---|
| Column (MVP) | `prev4hVWAP` |
| Companion diagnostics (MVP) | `prev4hVWAP_hit_m1`, `prev4hVWAP_hit_m5` |
| Stack (Phase 3) | `prev4hVWAP_2` … `prev4hVWAP_N` when validity `N > 1` |
| Session scope | Full trading session via `trading_session_date` + `eth_start` |
| Bracket anchor | Session open (ETH start), 4h buckets |
| Formula | Typical-price VWAP `(H+L+C)/3` |
| TTL setting | `prev4h_vwap_validity_periods` (int ≥ 1, default `1`) |
| API gate | `prev4h_vwap_enabled=False` on `compute_all_levels` |
| Product default | Enable in `DEFAULT_LEVELS_SETTINGS` (same pattern as prev30m) |
| Engine version | Bump `LEVEL_ENGINE_VERSION` `5 → 6` in Phase 1 |
| Downstream | Generic level column consumption; no signal-engine changes |

**Feasibility:** High. Direct clone of Stage 8 with `BRACKET_MINUTES=240`.

---

## 6. Implementation surface

### 6.1 New modules

```text
thesistester/levels/prev4h_vwap.py
thesistester/analytics/prev4h_vwap_hit.py          # Phase 2
tests/test_prev4h_vwap.py                           # §10 mirror
tests/test_prev4h_vwap_hit_analytics.py             # Phase 2
```

Public helpers (mirror prev30m names):

- `compute_prev4h_vwap_levels(...)`
- `session_bracket_keys(...)` with 4h buckets (or a clearly named 4h variant if sharing the prev30m helper name would collide — prefer module-local `session_bracket_keys` in `prev4h_vwap.py`)
- `prev4h_price_column_names`, `prev4h_stack_column_name`, `is_prev4h_price_level_column`

### 6.2 Wiring (Phase 1)

| File | Change |
|---|---|
| `thesistester/levels/all.py` | kwargs `prev4h_vwap_enabled=False`, `prev4h_vwap_validity_periods=1`; join columns |
| `thesistester/levels/defaults.py` | product defaults enabled + validity `1` |
| `thesistester/levels/__init__.py` | export compute + helpers |
| `thesistester/persistence/local_store.py` | `LEVEL_ENGINE_VERSION = 6` |
| `thesistester/setup.py` | denylist `prev4hVWAP_hit_m1` / `hit_m5` |
| `thesistester/assistant/workspace.py` | catalog age-1 + stack names when enabled |
| `pages/2_Levels.py` | opt-in checkbox + validity/stack-depth input beside prev30m |
| `thesistester/api.py` | validate/passthrough allowlists |
| `tests/test_stage6_levels_ui_settings.py` | DEFAULT equality update |
| Docs §8 | same-PR documentation |

### 6.3 Configuration contract

```python
# DEFAULT_LEVELS_SETTINGS (product)
"prev4h_vwap_enabled": True,
"prev4h_vwap_validity_periods": 1,

# compute_all_levels kwargs (API / low-level)
prev4h_vwap_enabled: bool = False,
prev4h_vwap_validity_periods: int = 1,
```

Validation when enabled: identical to prev30m (tz-aware, instrument, `validity_periods >= 1`, Integral coercion, NaT fail-closed, missing `eth_start` → `ValueError`).

### 6.4 Diagnostic vs level eligibility

| Column | Setup / chart / catalog |
|---|---|
| `prev4hVWAP` / `prev4hVWAP_k` | yes |
| `prev4hVWAP_hit_m1` / `hit_m5` | **no** |

---

## 7. Non-regression (hard gate)

| Surface | Required outcome |
|---|---|
| All existing level families **including `prev30mVWAP`** | Value-identical on overlapping columns when prev4h disabled **and** when enabled |
| Signal / backtest / fills | Untouched |
| Persistence | Additive keys + engine version 5→6 (intentional cache invalidation only) |
| Eligibility denylist | Additive `prev4h` hit entries only |

**Proof:** disabled isolation + overlapping-column equality + full pytest green + legacy goldens untouched.

---

## 8. Documentation updates (same PR as each phase’s code)

| Doc | Update |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | New § for prev4h (point to 4h session-open brackets; inherit prev30m caveats) |
| `docs/POINT_IN_TIME_GUARANTEES.md` | Audit rows + module list |
| `docs/METRICS_GLOSSARY.md` | `prev4hVWAP`, hits, TTL/stack, R analytics |
| `docs/ARCHITECTURE.md` | Module map + settings keys |
| `docs/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md` | Stage 9 pointer to this doc |
| This doc | Status → implemented per phase |

---

## 9. Test plan (normative)

Mirror `docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md` §10 with substitutions in §2.1.

**Mandatory adaptations:**

1. Synthetic fixtures use **4h** blocks (e.g. 18:00–22:00, 22:00–02:00), not 30m.
2. Hand-computed bracket VWAP on a 4h block.
3. RTH-open non-reset test still required (bracket spanning 09:30).
4. Halt / session-boundary finalization on the **14:00–18:00** final bracket (or equivalent last open 4h window).
5. Mid-session truncation future-shock (no dataset-end finalize).
6. Coexistence: enabling prev4h must not alter `prev30mVWAP` columns when both enabled.
7. Phase 3: `N=1` column parity; `N>1` stack ages/TTL/seed/eligibility/future-shock.

Phase 2 analytics tests mirror §10.7 for `prev4h_*` column names and Backtest expander wiring (additive; do not break prev30m expander).

---

## 10. Phased delivery

### Phase 0 — Plan lock (this document)

- Lock “exact same as prev30m, bracket = 4h”.
- No runtime code.

### Phase 1 — Level engine MVP

- `prev4h_vwap.py` + wiring + UI + denylist + `LEVEL_ENGINE_VERSION = 6`
- Columns: `prev4hVWAP`, `prev4hVWAP_hit_m1`, `prev4hVWAP_hit_m5`
- Stack columns when `N > 1` may land in Phase 1 **or** Phase 3; prefer **same split as Stage 8** (scalar MVP first, stack second) unless a single PR stays small and golden-safe.
- Tests: gate, math, ETH+RTH, TTL, hits, future-shock, coexistence with prev30m
- Docs §8

**Recommendation:** Phase 1 = scalar + hits (like Stage 8 Phase 1). Phase 3 = stack. Keeps review/diff focused.

### Phase 2 — Early-window R analytics

- `prev4h_vwap_hit.py` + Backtest expander (parallel to prev30m; shared UI pattern OK if additive)
- No `simulate_trades` changes
- Tests mirroring prev30m §10.7

### Phase 3 — Multi-period stack

- `prev4hVWAP_2` … `_N` via `prev4h_vwap_validity_periods`
- Age-1 unchanged; hits stay age-1 only
- Engine version already bumped in Phase 1; bump again **only if** Phase 3 is a separate PR after Phase 1 shipped (then 6→7). If stack ships inside Phase 1, single bump 5→6 is enough.

---

## 11. UI contract (Levels page)

Under **Advanced opt-in levels**, adjacent to prev30m controls:

1. Checkbox: **Previous 4h VWAP (`prev4hVWAP`)** — `prev4h_vwap_enabled`
2. Number input: **Validity / stack depth (4h periods)** — `prev4h_vwap_validity_periods`, min 1, default 1
3. Help: session-open 4h brackets (ETH+RTH); frozen prior-bracket VWAP; `hit_m1` / `hit_m5` after first 1 / 5 minutes; `N>1` emits stack

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Copy-paste drift from prev30m (30 still hardcoded) | Dedicated module + 4h fixtures; grep gate for `240` / column names |
| Partial final 4h vs 17:00 halt | Same session-transition finalize tests as Stage 8 |
| Accidental RTH NaN-gating | ETH emission tests |
| Colliding with prev30m settings/columns | Distinct keys/names; coexistence equality test |
| `hit_m*` selected as levels | Denylist + eligibility tests |
| Identity cache reuse | Engine version bump |

---

## 13. Open decisions — **locked for this plan**

| Question | Lock |
|---|---|
| Same family semantics as prev30m? | **Yes** — only bracket length changes |
| Bracket length | **4h (240 minutes)** |
| Session clock | Session-open (`eth_start`), ETH+RTH |
| Hits | `hit_m1` **and** `hit_m5` (same early-window contract) |
| Stack | Phase 3 (or with Phase 1 if single PR stays tight) |
| Product default enabled? | **Yes** (match prev30m / other opt-ins) |
| Share code with prev30m in MVP? | **No** — clone module; extract later only if golden-safe |

---

## 14. Implementation sequence (engineer checklist)

1. Land this plan (Phase 0 PR).
2. Add `prev4h_vwap.py` with disabled no-op + enabled compute (`BRACKET_MINUTES=240`).
3. Wire `compute_all_levels` / defaults / UI / API / catalog / denylist.
4. Bump `LEVEL_ENGINE_VERSION` to 6.
5. Land `tests/test_prev4h_vwap.py` (mirror §10 with 4h fixtures + coexistence).
6. Update docs §8.
7. Full pytest green; legacy goldens untouched.
8. Phase 2 analytics helper + expander.
9. Phase 3 stack if not included in step 2–7.
10. Each PR body: regression-safety paragraph (disabled-gate + overlapping-column equality + PIT).

---

## 15. Bottom line

`prev4hVWAP` is Stage 8 with a 4-hour bracket. Inherit every prev30m lock; change only period length, names, settings keys, and engine version. Ship behind `prev4h_vwap_enabled`, prove PIT with future-shock tests, bump `LEVEL_ENGINE_VERSION` to 6, and keep legacy + prev30m outputs identical when the new gate is disabled.
