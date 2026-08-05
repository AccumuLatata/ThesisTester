# Regression-Safe Implementation Plan: `prev30mVWAP`

**Status:** Spec / plan only — not implemented  
**Document type:** Focused level-family implementation plan  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related docs:** `docs/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md`, `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

---

## 1. Purpose

Add a new scalar level family:

```text
prev30mVWAP
```

Definition (product intent):

1. **Level** — the final price of the just-completed 30-minute VWAP, frozen at the open of the next 30-minute period.
2. **First-minute hit diagnostic** — measure whether that level was touched within the first minute of the new 30-minute period (and expose R-multiple analytics conditional on that hit).
3. **Validity TTL** — the frozen level remains valid for a configurable number of subsequent 30-minute periods only.

Hard availability requirement (locked):

> The level must be available for the **entire trading session (ETH + RTH)**.  
> It must **not** be RTH-only like `dVWAP_RTH`, TPO Single Prints, or APOC.

This plan is additive, opt-in, default-off at the `compute_all_levels` API boundary, and must leave legacy level/signal/backtest outputs unchanged when the new gate is disabled.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Column (MVP) | `prev30mVWAP` |
| Companion diagnostic (MVP) | `prev30mVWAP_hit_m1` (boolean / 0-1 float) |
| Session scope | Full trading session via `trading_session_date` + instrument `eth_start` |
| Bracket anchor | **Session open (ETH start)**, not RTH open |
| Bars that contribute | All session bars (ETH and RTH) |
| Bars that emit | All session bars inside the validity window (ETH and RTH) |
| Formula | Typical-price VWAP: `sum(tp*vol)/sum(vol)`, `tp=(H+L+C)/3` |
| Availability | First bar of the period after a completed bracket; prior-session seed at next session open |
| TTL setting | `prev30m_vwap_validity_periods` (int ≥ 1, default `1`) |
| API gate | `prev30m_vwap_enabled=False` on `compute_all_levels` |
| Product default | Enable in `DEFAULT_LEVELS_SETTINGS` (same pattern as pivots / dVWAP / SP / APOC) |
| Engine version | Bump `LEVEL_ENGINE_VERSION` `3 → 4` in the implementation PR |
| Downstream | Generic level column → Setup / confluence / signals / backtest consume without signal-engine changes |

**Feasibility:** High. Closest precedents are APOC freeze/carry, TPO 30m bracket lifecycle, and session VWAP math. The new work is the **session-open (ETH) bracketization + full-session emission + TTL + first-minute hit diagnostic**.

---

## 3. Locked product definition

### 3.1 What `prev30mVWAP` is

For each completed 30-minute bracket `k` in a trading session:

1. Compute the bracket VWAP from all bars whose open timestamps fall in bracket `k`.
2. At the **first bar of bracket `k+1`**, freeze that end-of-bracket VWAP as `prev30mVWAP`.
3. Hold that constant scalar until it is replaced by a newer completed bracket or expires by TTL.

Verbal definition matching the original request:

> `prev30mVWAP` is the last price of the 30-minute VWAP before the new 30m VWAP opens.

### 3.2 What it is not

| Existing column / concept | Why it is not `prev30mVWAP` |
|---|---|
| `VWAP_rolling_30min` | Sliding lookback; continuously updates; not a frozen prior-period level |
| `dVWAP_RTH` | Developing from RTH open; NaN on ETH; not period-frozen |
| RTH-anchored TPO/APOC brackets | Exclude ETH; emit NaN on ETH; wrong availability contract |

Do **not** reuse or mutate rolling VWAP or `dVWAP_RTH` behavior.

### 3.3 Full-session availability (ETH + RTH) — locked

| Concern | Locked behavior |
|---|---|
| Session grouping | `trading_session_date(local_ts, eth_start)` |
| Session open | Instrument `eth_start` (ES/NQ/MES/MNQ: `18:00` exchange-local) |
| Bracket clock | Minutes since **session open**, floored into 30-minute buckets |
| Contribution | ETH and RTH bars both contribute to bracket VWAP |
| Emission | ETH and RTH bars both emit `prev30mVWAP` when a valid frozen value exists |
| Off-session / unknown | If a bar cannot be assigned a session date, emit `NaN` |
| RTH-only gate | **Forbidden** for this family |

Consequence: unlike Stage 3–5 RTH families, overnight ETH testing can select and interact with `prev30mVWAP`.

### 3.4 Bracketization algorithm (normative)

Let:

- `session_open_ts` = exchange-local midnight-of-session-date logic is **not** used for the clock; use the session’s ETH start timestamp:
  - For session date `D`, `session_open_ts = (D - 1 day) @ eth_start` when `eth_start` is evening (e.g. 18:00), consistent with `trading_session_date` (bars at/after 18:00 belong to the next calendar date’s session).
- Implementation must derive `session_open_ts` from the same `trading_session_date` + `eth_start` contract already used by session levels, not invent a second session model.

For each bar in a session:

```text
minutes_since_open = floor((bar_ts_local - session_open_ts) / 1 minute)
bracket_idx        = floor(minutes_since_open / 30)
bracket_start      = session_open_ts + bracket_idx * 30min
bracket_end        = bracket_start + 30min
```

A bracket is **complete** at the first timestamp `>= bracket_end` (APOC-style clock completion), or when the session ends and the bracket contained at least one bar with positive cumulative volume semantics defined below.

Only **completed** brackets may produce a freeze. The current incomplete bracket never contributes its developing VWAP to `prev30mVWAP`.

### 3.5 VWAP formula (normative)

Identical typical-price convention as `dVWAP_RTH` / rolling VWAP:

```text
typical_price = (high + low + close) / 3
bracket_vwap  = sum(typical_price * volume) / sum(volume)
```

over bars in the completed bracket only.

Edge cases:

| Case | Behavior |
|---|---|
| `sum(volume) == 0` for the bracket | No freeze produced; previous valid level continues under TTL, else `NaN` |
| Missing OHLC | Existing loader fatal validation remains upstream; level code assumes valid OHLCV |
| Gaps inside a bracket | Use available bars only; do not synthesize bars |
| Unsorted input | Sort by timestamp internally (same contract as other level modules); join alignment via `compute_all_levels` sorted timeline |

### 3.6 Validity TTL (point 3) — locked

Setting:

```text
prev30m_vwap_validity_periods: int >= 1   # default 1
```

Semantics for the MVP **single scalar column**:

1. When bracket `k` completes with a valid VWAP `V_k`, schedule level `V_k` to be active for brackets `k+1 .. k+N` inclusive.
2. At the open of bracket `k+1`, emit `prev30mVWAP = V_k`.
3. If a newer bracket `k+j` completes before expiry, **replace** with `V_(k+j)` and reset the TTL window to the next `N` brackets.
4. If no valid freeze exists for the current bracket under the TTL window, emit `NaN`.

With continuous data and `N >= 1`, the common case is: during bracket `k+1`, `prev30mVWAP == V_k` (classic previous-period VWAP).  
`N > 1` keeps a freeze alive across thin/gappy stretches where intermediate brackets fail to produce a valid VWAP (zero volume / empty), and documents the research horizon. It does **not** invent a multi-price stack in MVP.

**Out of MVP (optional follow-up, same family):** multi-period stack columns

```text
prev30mVWAP      # age = 1 (immediate prior)
prev30mVWAP_2    # age = 2
…
prev30mVWAP_N    # age = N
```

for confluence across the last `N` completed period VWAPs. Do not implement the stack until the scalar MVP is golden-gated.

### 3.7 Cross-session seed — locked

To make ETH open of a new session testable:

- When session `S` ends, remember the last valid completed-bracket VWAP of `S` (if any).
- From the **first bar of session `S+1`**, emit that value as `prev30mVWAP` with a fresh TTL of `N` brackets counted in `S+1`.
- If session `S` produced no valid freeze, session `S+1` starts at `NaN` until its first bracket completes.

This mirrors `pAPOC` / prior-session carry intent, but the carried value remains named `prev30mVWAP` (no separate `pPrev30mVWAP` column in MVP).

### 3.8 First-minute hit (point 2) — locked

#### 3.8.1 Level-adjacent diagnostic column

```text
prev30mVWAP_hit_m1
```

Definition:

- Evaluate only at bars belonging to the **first minute** of a 30-minute bracket in which `prev30mVWAP` is non-NaN at bracket open.
- Hit rule (range touch, consistent with engine touch semantics):

```text
bar.low <= prev30mVWAP <= bar.high
```

- For all bars in that first minute after a hit is observed on any of those bars, the diagnostic may be `1.0` for the remainder of the minute (or emitted as a bracket-constant flag — see implementation note below).
- For bars outside the first minute: emit `NaN` or `0.0`? **Locked:** emit `0.0` after the first minute of the bracket if the level was valid at bracket open and not hit in minute 1; emit `1.0` for the whole bracket once minute-1 hit is known; emit `NaN` when `prev30mVWAP` is NaN at bracket open.

Implementation note (PIT-safe):

- Minute-1 hit becomes knowable only after the first-minute bars have been seen.
- Prefer a **bracket-constant flag finalized at the end of the first minute** and forward-filled for the rest of the bracket (causal: first-minute completion time).
- Do **not** rewrite earlier bars after later information arrives in a way that breaks future-shock tests; compute in timestamp order.

Recommended emission contract (normative for tests):

| Time within bracket | `prev30mVWAP` valid at open? | Emission |
|---|---|---|
| Before first-minute completion | yes | `NaN` on `hit_m1` (unknown yet) |
| At/after first-minute completion | yes, touched in minute 1 | `1.0` for remaining bars of that bracket |
| At/after first-minute completion | yes, not touched | `0.0` for remaining bars of that bracket |
| Any | no | `NaN` |

This keeps point-in-time honesty: the hit flag is not visible before minute 1 completes.

#### 3.8.2 R-multiple analytics (point 2, analytics layer)

“Measure the R whether the level was hit within the first minute” is implemented as **post-trade analytics**, not as a change to fill logic:

1. When trades are generated against setups that include `prev30mVWAP` (selected level / anchor / confluence member), attach or join:
   - `prev30mVWAP_hit_m1_at_signal` (or at entry bracket open)
2. Analytics helpers summarize `r_multiple` conditioned on `hit_m1 ∈ {0,1}`.

MVP placement:

- Phase A (levels PR): ship `prev30mVWAP` + `prev30mVWAP_hit_m1` columns only.
- Phase B (analytics PR, same roadmap item, can be same PR if small): add a pure analytics function, e.g. `analytics/prev30m_vwap_hit.py` → grouped R stats; UI read-only table on Backtest/Signals diagnostics.

No change to `simulate_trades` fill semantics.

---

## 4. Non-goals

- Do not change `VWAP_rolling_*`, `dVWAP_RTH`, TPO, or APOC formulas/availability.
- Do not implement `dVWAP_ETH` in this workstream.
- Do not implement multi-period VWAP stack columns in MVP.
- Do not add new signal triggers specific to prev30mVWAP (use existing touch/reject/break/reclaim/3c).
- Do not require engine golden regeneration for legacy mode (gate default-off).
- Do not NaN-gate this family to RTH.

---

## 5. Architecture and file plan

### 5.1 New module

```text
thesistester/levels/prev30m_vwap.py
```

Public API:

```python
def compute_prev30m_vwap_levels(
    df: pd.DataFrame,
    instrument: str = "ES",
    *,
    enabled: bool = False,
    validity_periods: int = 1,
) -> pd.DataFrame:
    ...
```

Disabled contract (mandatory, Stage 2–5 precedent):

- `enabled=False` → empty DataFrame, same index, **no** timestamp validation, **no** new columns.

Enabled output columns:

```text
prev30mVWAP
prev30mVWAP_hit_m1
```

### 5.2 Wiring

| File | Change |
|---|---|
| `thesistester/levels/all.py` | Add kwargs `prev30m_vwap_enabled=False`, `prev30m_vwap_validity_periods=1`; join new columns |
| `thesistester/levels/defaults.py` | Product defaults: `prev30m_vwap_enabled=True`, `prev30m_vwap_validity_periods=1` |
| `thesistester/research_identity.py` | Allow new keys via `DEFAULT_LEVELS_SETTINGS` (unknown-key rejection) |
| `thesistester/persistence/local_store.py` | `LEVEL_ENGINE_VERSION = 4` |
| `thesistester/assistant/workspace.py` | Add `prev30mVWAP` to `SESSION_LEVEL_CATALOG` / level discovery |
| `pages/2_Levels.py` (or current Levels page) | Opt-in checkbox + validity integer input under advanced levels |
| `thesistester/api.py` | Pass through normalized settings into `compute_all_levels` |
| `thesistester/analytics/` (Phase B) | Optional R-stats helper by `hit_m1` |
| Docs listed in §9 | Same-PR documentation |

### 5.3 Shared helpers (drift control)

Prefer extracting a small shared helper if TPO/APOC bracket math is duplicated enough to risk drift:

```text
thesistester/levels/session_brackets.py  # optional, only if extraction stays behavior-neutral
```

Constraints if extracted:

- Extraction PR must be behavior-neutral for TPO/APOC (golden / existing stage tests unchanged), **or**
- Keep bracketization local to `prev30m_vwap.py` in MVP and defer extraction.

**Recommendation:** keep local in MVP (session-open clock differs from RTH-open TPO/APOC). Do not force a shared helper that mixes two clocks.

### 5.4 Downstream consumption

No confluence/signal/backtest code changes required for the level itself:

- `available_level_columns()` picks up non-OHLCV columns.
- Setup Builder / anchor confluence can select `prev30mVWAP`.
- Naked flags apply generically if enabled.

---

## 6. Configuration contract

### 6.1 Settings keys

```python
# DEFAULT_LEVELS_SETTINGS (product)
"prev30m_vwap_enabled": True,
"prev30m_vwap_validity_periods": 1,

# compute_all_levels kwargs (API / low-level)
prev30m_vwap_enabled: bool = False,
prev30m_vwap_validity_periods: int = 1,
```

### 6.2 Validation

When enabled:

| Input | Error |
|---|---|
| Naive timestamps | `ValueError` (existing `require_tz_aware_timestamp`) |
| Unknown instrument | `ValueError` |
| `validity_periods < 1` | `ValueError` |
| Non-integer validity | `ValueError` |

When disabled: accept anything; return empty frame (no validation).

### 6.3 Identity / cache

- New settings participate in levels settings hash via `normalize_levels_config`.
- `LEVEL_ENGINE_VERSION` bump invalidates stale persisted level snapshots computed under v3 — required because engine output vocabulary grows and identity must not silently reuse old caches when product defaults enable the family.

---

## 7. Point-in-time guarantees

Normative PIT claims (must be tested):

1. At bar `t`, `prev30mVWAP` uses only completed brackets whose `bracket_end <= t` (plus prior-session seed already finalized before `t`).
2. Appending future bars must not change any prior row’s `prev30mVWAP`.
3. `prev30mVWAP_hit_m1` at bar `t` uses only bars at or before `t`; it stays `NaN` until the first minute of the bracket has completed.
4. ETH bars never wait on RTH open for emission; overnight bars emit once a freeze exists.
5. Current incomplete bracket VWAP never leaks into `prev30mVWAP`.

Register these rows in `docs/POINT_IN_TIME_GUARANTEES.md` in the implementation PR.

---

## 8. Regression-safety framework mapping

Maps to `ENGINEERING_PROPOSAL.md` §4:

| Rule | Application here |
|---|---|
| 1. Additive-only | New kwargs default off; no positional signature breaks |
| 2. Golden-masters | Legacy mode / disabled gate must keep existing goldens byte/value-identical |
| 3. Opt-in default-off | `compute_all_levels(..., prev30m_vwap_enabled=False)` |
| 4. Schema / engine version | `LEVEL_ENGINE_VERSION = 4` |
| 5. Future-shock PIT | Dedicated tests in `tests/test_prev30m_vwap.py` |
| 6. `session_state` stability | Additive UI keys only; document in `ARCHITECTURE.md` if pages store new keys |
| 7. Determinism | Pure pandas/numpy; no randomness |
| 8. Same-PR docs | §9 list |
| 9. CI green | Full pytest + ruff |
| 10. Honesty | Document approximation (bar typical-price VWAP, not tick VWAP) |

### 8.1 Per-PR acceptance checklist (§4.2)

Mandatory for every implementation PR:

- [ ] Unit tests for bracket VWAP, freeze timing, ETH emission, TTL, hit_m1 timing
- [ ] Future-shock tests (append current-session + next-session bars)
- [ ] Disabled no-op tests (including naive timestamps accepted when disabled)
- [ ] `compute_all_levels` isolation: disabled → no new columns; other families unchanged
- [ ] Legacy golden-masters preserved
- [ ] Docs updated in same PR
- [ ] PR body contains a short “Regression safety” paragraph
- [ ] Narrow surface area; no drive-by refactors of TPO/APOC/dVWAP

---

## 9. Documentation updates (same PR as code)

| Doc | Update |
|---|---|
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | New § for prev30mVWAP caveats (session-open brackets, typical-price, TTL, hit_m1 delay) |
| `docs/POINT_IN_TIME_GUARANTEES.md` | Audit table rows + module list entry |
| `docs/METRICS_GLOSSARY.md` | Define `prev30mVWAP`, `prev30mVWAP_hit_m1`, TTL setting, R-conditional analytics |
| `docs/ARCHITECTURE.md` | Levels module map + settings keys if contract surface changes |
| `docs/ENGINEERING.md` | Short level-family mention if the levels catalog section lists families |
| `docs/LEVEL_UPGRADE_IMPLEMENTATION_PLAN.md` | Add “Stage 8 — prev30mVWAP” pointer to this doc (do not rewrite Stages 1–7 history) |
| This doc | Mark status → Implemented when merged |

---

## 10. Test plan (normative)

New file:

```text
tests/test_prev30m_vwap.py
```

### 10.1 Gate / contract

1. Disabled → empty DataFrame, no columns, no validation.
2. Disabled accepts naive timestamps / bad instrument / validity `< 1`.
3. Enabled + naive timestamps → `ValueError`.
4. Enabled + bad instrument → `ValueError`.
5. Enabled + `validity_periods=0` → `ValueError`.
6. `compute_all_levels(..., prev30m_vwap_enabled=False)` adds no prev30m columns.
7. Enabling adds exactly `prev30mVWAP` and `prev30mVWAP_hit_m1`.
8. Existing families unchanged when prev30m enabled (column-value equality on overlapping columns).

### 10.2 Bracket math / freeze

9. Exact bracket VWAP on a synthetic 30-minute block (hand-computed).
10. No emission during the first bracket of a session without prior-session seed.
11. Emission starts at first bar of bracket `k+1`.
12. Value is constant for all bars inside a validity window.
13. Incomplete current bracket excluded.
14. Zero-volume bracket produces no freeze.

### 10.3 Full-session ETH + RTH

15. ETH bars before RTH emit non-NaN when a freeze exists (contrast: `dVWAP_RTH` is NaN).
16. ETH bars contribute volume/price to overnight brackets.
17. RTH bars continue the same session bracket clock (no reset at RTH open).
18. Session reset: last value of session `S` does not bleed incorrectly into unrelated dates; seed into `S+1` only via explicit prior-session seed rule.
19. Fixture covering overnight ETH → RTH → post-RTH ETH on ES (`eth_start="18:00"`).

### 10.4 TTL

20. `N=1`: level from bracket `k` present in `k+1`, replaced at `k+2` by `V_(k+1)` when available.
21. `N>1` with a zero-volume intermediate bracket: prior freeze survives until TTL expiry.
22. After TTL expiry with no replacement → `NaN`.

### 10.5 First-minute hit

23. Touch in first minute → `hit_m1` becomes `1.0` only after first-minute completion.
24. No touch in first minute → `0.0` after first-minute completion.
25. Before first-minute completion → `NaN` on `hit_m1`.
26. When `prev30mVWAP` is NaN at bracket open → `hit_m1` is `NaN`.
27. Touch only in minute 2+ does **not** count as minute-1 hit.

### 10.6 Future-shock / determinism

28. Append future bars in-session → prior values unchanged.
29. Append next-session bars → prior session values unchanged.
30. Unsorted input equals sorted input.
31. NQ instrument supported.

### 10.7 Analytics (Phase B)

32. Grouped mean/median/count of `r_multiple` by `hit_m1` on a tiny synthetic trade frame.
33. Empty-trade safe.

---

## 11. Phased delivery

### Phase 0 — Plan lock (this document)

- Lock full-session ETH+RTH availability.
- Lock session-open bracket clock.
- Lock TTL + hit_m1 contracts.
- No runtime code.

### Phase 1 — Level engine MVP (implementation PR)

Scope:

- `prev30m_vwap.py`
- `compute_all_levels` wiring
- defaults / normalize / Levels UI controls
- `LEVEL_ENGINE_VERSION = 4`
- catalog / API passthrough
- tests §10.1–10.6
- docs §9

Acceptance:

- Disabled path legacy-identical.
- ETH+RTH emission proven by tests.
- PIT future-shock green.
- CI green.

### Phase 2 — First-minute R analytics (same PR if small; else follow-up)

Scope:

- Pure analytics helper + optional diagnostics panel.
- No `simulate_trades` changes.
- Tests §10.7.
- Glossary entries for conditional R stats.

### Phase 3 — Optional multi-period stack (future)

Only if research needs confluence of `V_(k-1) … V_(k-N)` simultaneously.

- Additive columns `prev30mVWAP_2 … _N`
- Separate gate or reuse validity setting
- New tests; no change to MVP column semantics

---

## 12. UI contract (Levels page)

Under advanced / opt-in levels:

1. Checkbox: **Previous 30m VWAP (`prev30mVWAP`)** — bound to `prev30m_vwap_enabled`.
2. Number input: **Validity (30m periods)** — bound to `prev30m_vwap_validity_periods`, min 1, default 1.
3. Short help text:
   - Session-open 30m brackets (ETH+RTH).
   - Frozen prior-bracket VWAP.
   - `hit_m1` finalized after the first minute.

Do not place these controls in the hero/primary SMA-EMA area; keep with other opt-in level families.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Confusing session-open brackets with RTH TPO brackets | Explicit docs + tests that RTH open does **not** reset the clock |
| Accidental RTH NaN-gating copy-paste from `session_vwap.py` / `tpo.py` | Dedicated ETH emission tests; code review checklist item |
| `hit_m1` look-ahead | NaN until first-minute completion; future-shock tests |
| TTL ambiguity | Normative §3.6; tests for replace vs expire |
| Identity cache reuse after new columns | Engine version bump to 4 |
| Product default enable surprises headless users | Only product defaults enable; raw `compute_all_levels` stays off |
| Drift from rolling VWAP | Separate module; never call rolling VWAP helpers for this freeze |

---

## 14. Worked example (ES, conceptual)

Session open: `18:00` exchange-local.

| Clock | Event |
|---|---|
| 18:00–18:30 | Bracket 0 developing; `prev30mVWAP` = prior-session seed (or NaN) |
| 18:30:00 | Bracket 0 completes → freeze `V0` |
| 18:30 first bar | `prev30mVWAP = V0` (ETH bar emits) |
| 18:30–18:31 | Evaluate hit vs `V0`; `hit_m1` still NaN until 18:31 |
| ≥ 18:31 | `hit_m1` = 1/0 for rest of 18:30–19:00 bracket |
| 09:30 RTH open | **No reset**; still on session-open clock |
| Next bracket open | Replace with newest completed VWAP; TTL resets |

---

## 15. Implementation sequence (engineer checklist)

1. Add `thesistester/levels/prev30m_vwap.py` with disabled no-op + enabled compute.
2. Wire `compute_all_levels` kwargs/defaults; keep API default `False`.
3. Extend `DEFAULT_LEVELS_SETTINGS` + Levels UI + API passthrough + catalog.
4. Bump `LEVEL_ENGINE_VERSION` to 4.
5. Land `tests/test_prev30m_vwap.py` (gate, math, ETH+RTH, TTL, hit_m1, future-shock).
6. Update docs in §9.
7. Run full pytest + ruff; confirm legacy goldens untouched.
8. Phase 2 analytics helper if not included in step 1–7.
9. PR body: regression-safety paragraph referencing disabled-gate + golden preservation + PIT tests.

---

## 16. Open items explicitly closed by this plan

| Question | Resolution |
|---|---|
| RTH-only or full session? | **Full session (ETH + RTH)** |
| Bracket anchor? | **Session open (`eth_start`), not RTH open** |
| Point 2 meaning? | Diagnostic column `prev30mVWAP_hit_m1` + optional R analytics conditioned on it |
| Point 3 meaning? | Integer TTL in 30m periods; default 1; replace-on-new-freeze |
| Cross-session? | Prior-session last freeze seeds next session open |
| Multi-level stack? | Out of MVP (Phase 3) |

---

## 17. Verdict

`prev30mVWAP` is feasible and fits the existing scalar level architecture. Points 2 and 3 are feasible without engine fill changes. The critical design lock versus earlier RTH-family precedents is:

> **Session-open 30-minute brackets with ETH+RTH contribution and emission.**

Implement behind `prev30m_vwap_enabled`, prove PIT with future-shock tests, bump `LEVEL_ENGINE_VERSION` to 4, and keep legacy outputs identical when disabled.
