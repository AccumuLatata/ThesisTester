# Session Entry Window — Product & Engineering Proposal

**Document type:** Proposal + implementation roadmap (fully scoped PRs)  
**Date:** 2026-08-06  
**Status:** Proposal (implementation not started; SW0 docs lock in [#286](https://github.com/AccumuLatata/ThesisTester/pull/286))  
**Inputs:** Time Analysis / Backtest UX gap analysis; `docs/ENGINEERING_PROPOSAL.md` §4; `docs/USER_GUIDE.md` (Time Analysis); `docs/SOTA_BACKTESTING_LANDSCAPE.md` §9 item 7; industry session-filter practice  
**Related code:** `thesistester/analytics/time_analysis.py`, `thesistester/engine/backtest.py`, `thesistester/analytics/grid.py`, `thesistester/analytics/walk_forward.py`, `thesistester/analytics/sensitivity.py`, `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/9_Time_Analysis.py`, `pages/10_Validation.py`, `thesistester/api.py`  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4 (including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist)

---

## 1. Executive summary

ThesisTester already surfaces the insight that **all-day Performance Summary can look terrible while a single RTH segment (e.g. `rth_open_30m`) looks promising**. Time Analysis does that well as a **descriptive** layer. What the product cannot do today is close the research loop:

1. **Focus** the Performance Summary on one time bucket (post-hoc).
2. **Promote** that bucket into a first-class **entry window** rule.
3. **Re-simulate** under that rule (correct exposure/cooldown interaction).
4. **Grid** SL/TP inside that constrained window.
5. **Validate** (WFA / MC / sensitivity) under the **same** constraint — without silently re-picking the best hour.

This proposal ships that loop as an additive, opt-in, golden-gated capability series (**SW0–SW7**), sequenced so post-hoc exploration lands before any engine change, and so engine admission is proven against the existing legacy golden family before UI/grid/validation wiring multiplies surface area.

**Positioning:** deepen the niche ThesisTester already owns — session-aware confluence research for ES/NQ — rather than adding a free-form “optimize over every clock minute” miner. Time-of-day becomes a **declared strategy constraint**, not an unconstrained search axis (default).

---

## 2. Problem statement

### 2.1 User-observed failure mode

| Surface | Typical reading | What it actually measures |
|---|---|---|
| Backtest **Performance Summary** | “Strategy is terrible” (e.g. WR 25%, PF 0.69, Total R −11) | Expectancy of **all admitted entries** across the whole session |
| Time Analysis row **`rth_open_30m`** | “Setup looks promising” (e.g. WR 71%, PF 4.3, Total R +7.3 on n=7) | Descriptive KPIs on the **subset** of completed trades whose entry fell in 09:30–09:59 ET |

These are not contradictory. Intraday markets are non-stationary across the RTH day (U-shaped volume/volatility; open vs midday vs power hour are different participant regimes). Aggregating them washes out session-specific edge — a known pitfall in day-trading research.

### 2.2 Product gaps today

| Desired action | Current state |
|---|---|
| Filter Performance Summary / equity / advanced risk to one RTH segment | **Missing** (Time Analysis overall summary stays full-set; group table is a partial substitute) |
| Admit entries only in a declared window at simulation time | **Missing** (only `no_new_entries_after` upper cutoff; silent skip; no lower bound; not segment allowlist) |
| Run Grid / WFA under that constraint | **Missing** (session policy passthrough exists for flat-by-close / upper cutoff only; no entry-window field) |
| Honesty labeling: post-hoc subset vs re-sim | **Partial** (USER_GUIDE already says Time Analysis does not re-simulate; no Focus/Promote UX) |

### 2.3 Why “just filter the table” is not enough

Post-hoc subsetting answers: *“Of the trades that filled under the all-day policy, how did this bucket do?”*

It does **not** answer: *“If I had refused all non-window entries, how would exposure, cooldown, and later signals interact?”*

A midday loser that blocked an open-window candidate never appears in the filtered open-window subset. For deployment honesty, the product must support **engine admission** after discovery — not only analytics filtering.

---

## 3. Recommended research loop (product contract)

This is the user-facing contract every PR must preserve in copy and behavior:

| Step | Name | User action | System behavior | Honesty label |
|---|---|---|---|---|
| **1** | **Discover** | Run Backtest → open Time Analysis → inspect RTH / hour / 30m groups | Existing descriptive grouping (`add_time_buckets` + `summarize_by_group`) | “Descriptive on this sample; not a live schedule” |
| **2** | **Scope** | Declare intended window (segment allowlist and/or `[start, end)`) as thesis constraint | Persist intent in session/setup/backtest settings | Pre-declared filter category, not silent cherry-pick |
| **3** | **Re-sim** | Run Backtest with entry window enabled | Engine admits only in-window entries; skipped signals audited | “Constrained re-simulation” |
| **4** | **Optimize** | Run Grid with the **same** window (fixed; not swept by default) | Every cell shares entry-window policy | Window is constraint, not fitness axis |
| **5** | **Prove** | Validation / WFA / MC / sensitivity under the same window | Fold logic inherits settings; no per-fold best-hour reselection | Diagnostic, not proof of edge |

**Sample-size gate (cross-cutting):** UI and assistant language must surface `trade_count` / `sample_warning` whenever a Focused or constrained summary is shown. Thin buckets (e.g. n=7) are hypotheses, not edges.

---

## 4. Goals and non-goals

### 4.1 Goals

1. Post-hoc **Focus** of Performance Summary + equity + trade list on a time bucket.
2. First-class **entry window** admission in `simulate_trades` (opt-in, default off).
3. Auditable skips (`skip_reason` for window rejects), parity with exposure skips.
4. Propagation through API → Backtest → Grid → Validation/WFA/sensitivity → reporting/export.
5. Time Analysis **Promote** CTA: “Use as entry window” → writes config for re-sim.
6. Documentation + Help corpus updates in the same PRs that change behavior.
7. Full regression safety per §4 (legacy goldens untouched; additive enabled-window golden family).

### 4.2 Non-goals (explicit)

| Non-goal | Why |
|---|---|
| Sweeping RTH segments / clock minutes as a default Grid axis | Multiple-testing / data-mining risk; deferred to optional advanced research mode (out of SW0–SW7) |
| Changing RTH segment definitions | Would break Time Analysis comparability; any change needs a dedicated versioned PR (shared export may rename private `_RTH_SEGMENTS` → public constant **without** changing bounds) |
| Replacing OTF or conflating OTF with clock windows | Orthogonal filters (regime vs clock); both may apply (§6.7) |
| Live session clocks / broker session calendars | Research-only tool; use existing instrument RTH/ETH + IANA TZ |
| Claiming OOS edge from Focused summaries | Honesty framing forbids this |
| Auto-detecting “best hour” into live config without user confirm | Must be explicit Promote + re-sim |

---

## 5. Design principles

1. **Additive, opt-in, default-off** — unset / `None` / `enabled=False` reproduces legacy byte-for-byte (`ENGINEERING_PROPOSAL.md` §4 rules 1, 3).
2. **Two modes, never conflated in UI:**
   - `focus` = post-hoc subset of completed trades (no re-sim).
   - `admit` = engine entry constraint (re-sim).
3. **One shared segment vocabulary** — export today’s `_RTH_SEGMENTS` (and matcher) as a public constant/helper used by Time Analysis, Focus, Admit, and Promote. No duplicated minute bounds.
4. **Audited admission for the window** — `outside_entry_window` skips when capture is on. Upper-cutoff audit (`after_entry_cutoff`) is **SW2b**, isolated from SW2 admission so golden risk stays narrow.
5. **Fixed constraint in Grid/WFA/sensitivity by default** — window is execution policy, like costs/exposure — not a fitness axis.
6. **Same-PR docs** — ARCHITECTURE session_state, ASSUMPTIONS, USER_GUIDE, METRICS_GLOSSARY, this roadmap status.
7. **Golden before engine** — SW0 confirms legacy gate; SW2 may not land without it green.

---

## 6. Technical design

### 6.0 Normative contracts (binding for all SW PRs)

These rules are acceptance criteria, not suggestions.

| # | Contract | Detail |
|---|---|---|
| **C1** | **Shared RTH segments** | Export current `_RTH_SEGMENTS` + minute matcher from `time_analysis` (or a tiny shared module both Focus and Admit import). Bounds stay identical to today’s Time Analysis table. Promote/Focus/Admit must not redefine labels. |
| **C2** | **Filter on entry-bar local time** | Window membership uses the **entry bar** timestamp localized to the session/exchange TZ — same basis as Time Analysis `entry_timestamp` bucketing. Signal-bar time is **not** used. Next-bar-open can place signal in `rth_open_30m` and entry in `rth_morning`; both Focus and Admit classify by entry. |
| **C3** | **Multi-segment = OR (union)** | `rth_segments: ["rth_open_30m", "rth_power_hour"]` admits if entry falls in **any** listed segment. Empty list with `enabled=True` is invalid. |
| **C4** | **Clock range = half-open `[start, end)`** | Same-day only in v1; `end <= start` → validation error (no overnight wrap). Segment mode already uses exclusive end minutes. |
| **C5** | **TZ law** | RTH-segment mode **always** evaluates in instrument exchange / session TZ (ES/NQ: `America/New_York`), never display/export TZ. `timezone: None` ⇒ exchange/session TZ. Promote must write that TZ explicitly into the normalized dict. Display TZ may label UI only. |
| **C6** | **Filter order** | `OTF (pre-sim candidate filter) → entry_window (admission) → exposure/cooldown`. Neither replaces the other; both may reject. Document in ASSUMPTIONS. |
| **C7** | **Focus ≡ Admit identity (hard gate)** | Under `exposure_policy="allow_all"`, `cooldown_bars_after_exit=0`, same normalized window + TZ: `set(admit_trades.signal_id) == set(focus_filter(all_day_trades).signal_id)`. Required SW2 acceptance test. When exposure/cooldown ≠ allow_all/0, sets may diverge — that divergence is the reason Admit exists. |
| **C8** | **Focus equity honesty** | Focused equity / max-DD is a **replay of the subset as if those were the only trades**, not path drawdown under the all-day admission set. Banner must state this. |
| **C9** | **AND with `no_new_entries_after`** | When both set, entry must pass **both**. Prefer `entry_window` for new UX; keep cutoff for backward compat. |

### 6.1 Config shape (canonical)

New execution-policy field (Backtest / Grid / WFA / sensitivity / API). Defaults preserve legacy:

```python
entry_window: dict[str, Any] | None = None
# Normalized form when present:
{
    "enabled": False,                    # master switch; False/None/absent => legacy
    "mode": "rth_segments",              # "rth_segments" | "clock_range"
    "rth_segments": [],                  # non-empty subset of shared RTH labels; OR semantics
    "start_time": None,                  # "HH:MM" or "HH:MM:SS" when mode=clock_range
    "end_time": None,                    # exclusive end; required with start_time
    "timezone": "America/New_York",      # IANA; None normalizes to exchange/session TZ (C5)
}
```

**Normalization rules:**

- Missing key / `None` / `enabled=False` → no filtering (legacy).
- `mode="rth_segments"` requires non-empty subset of **exported** shared segment labels (C1, C3).
- `mode="clock_range"` requires both times; half-open `[start, end)` (C4); reject wrap.
- Mutual exclusivity: only one mode active; invalid combos fail validation before sim.
- Interaction with `no_new_entries_after`: AND (C9).
- API defaults: add `entry_window=None` to `_BACKTEST_DEFAULTS` / `_GRID_DEFAULTS` (and validation execution passthrough); old payloads without the key normalize to disabled — never reject.

**Setup persistence (SW6):** optional `entry_window` on setup config, schema-versioned, default absent/disabled so old setups load unchanged (same pattern as `otf_filter`).

### 6.2 Analytics: Focus (post-hoc)

New pure helpers in `thesistester/analytics/time_analysis.py` (prefer extending this module; if extracted, both must import shared segments from one place — C1):

| Function | Behavior |
|---|---|
| `filter_trades_by_entry_window(trades, entry_window, ...)` | Ensure time buckets on **entry** timestamp + session TZ → boolean mask → filtered copy |
| `summarize_focused_trades(trades, entry_window, ...)` | filter → `summarize_trades` + `equity_curve` + optional direction split |
| `focus_provenance(entry_window, trade_count_before, trade_count_after)` | dict for UI banner / export metadata (`mode`, segments/range, TZ, counts) |

No engine calls. Deterministic. Empty-safe.

**Honesty (C8):** Focused equity curve / max-DD are subset-replay metrics. Banner required whenever Focus is active (see §6.6).

### 6.3 Engine: Admit (re-sim)

In `simulate_trades` (keyword-only):

```python
entry_window: dict[str, Any] | None = None,
```

Admission check (after entry timestamp localization, **before** appending to `candidate_rows`, same gate region as `no_new_entries_after`):

1. If window disabled → legacy path.
2. Compute **entry-bar** local time / minute-of-day (C2, C5) — same localization helper as session close / cutoff.
3. Membership: segment allowlist OR (C3) or clock `[start, end)` (C4).
4. If outside window → do **not** admit; if `return_skipped_signals` or `return_result`, append skip with:
   - `skip_reason`: `outside_entry_window`
   - additive columns only: `entry_window_mode`, `entry_local_time` (optional); existing skip schema keys stay stable.

**Ordering (C6):** OTF → entry_window → exposure. Windowed-out signals never enter exposure competition.

**SW2 vs SW2b:** SW2 lands `entry_window` only. Auditing today’s silent `no_new_entries_after` continue as `skip_reason="after_entry_cutoff"` is **SW2b** (same capture flags; trade rows under default kwargs remain golden-identical). Do not widen SW2 with that refactor.

### 6.4 API / pages / session_state

| Surface | Change |
|---|---|
| `api.run_backtest` / `run_grid` / WFA / `sensitivity` `execution_kwargs` | Accept normalized `entry_window`; pass through to `simulate_trades` / grid cells |
| `pages/7_Backtest.py` | Entry window controls; Focus overlay; clear distinction when re-running |
| `pages/9_Time_Analysis.py` | Row/segment **Focus summary** + **Promote to entry window** |
| `pages/8_Grid_Search.py` | Inherit entry window; not a grid axis |
| `pages/10_Validation.py` | Inherit from backtest settings / explicit control; WFA + sensitivity use same policy |
| Reporting / bundles | Persist `entry_window` + focus provenance in artifacts |

**Additive session_state keys** (never rename existing):

| Key | Producer | Consumer | Schema |
|---|---|---|---|
| `entry_window` | Backtest / Time Analysis Promote / Setup | Grid, Validation, API, Report | normalized dict |
| `focus_entry_window` | Time Analysis Focus / Backtest Focus | Backtest summary panel, Report | dict or `None` |
| `focused_trade_summary` | Focus action | UI display | same shape as `trade_summary` |
| `focused_equity_curve` | Focus action | UI display | same shape as `equity_curve` (subset-replay; C8) |
| `focused_trades` | Focus action | trade table / export | DataFrame subset |

Existing keys (`trades`, `trade_summary`, `equity_curve`, `time_grouped_summary`, …) keep producers/consumers. Focused keys are overlays — clearing Focus restores full-set view without re-running sim and **must not mutate** `trade_summary` / `equity_curve` / `trades`.

### 6.5 Skip-reason vocabulary (additive)

| `skip_reason` | Milestone | Meaning |
|---|---|---|
| existing exposure reasons | — | unchanged |
| `outside_entry_window` | **SW2** | entry-bar local time failed `entry_window` |
| `after_entry_cutoff` | **SW2b** | failed `no_new_entries_after` when skip capture on |

### 6.6 UI copy requirements (non-optional)

- Focus banner: **“Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run. Equity/drawdown here replay the subset only.”**
- After Promote + before re-run: **“Entry window armed. Run Backtest to re-simulate under this constraint.”**
- After constrained run: **“Constrained re-simulation — only in-window entries were admitted.”**
- Thin sample: reuse / extend `sample_warning` thresholds; never use “best entry” language without count.
- Promote confirm when `sample_warning` / below `min_trades`: require explicit confirm.

### 6.7 Shared module sketch (SW1/SW2 prerequisite work)

Landed with first consumer (SW1 or SW2, whichever merges first); the other imports it:

```text
time_analysis.py (or thesistester/analytics/rth_segments.py)
  RTH_SEGMENTS: list[tuple[int, int, str]]   # public; same bounds as today’s _RTH_SEGMENTS
  rth_segment_for_minute(minute: int) -> str
  entry_window_contains(local_ts, entry_window) -> bool   # C2–C5
  normalize_entry_window(raw, *, exchange_tz) -> dict | None
  segment_label_to_entry_window(label, *, exchange_tz) -> dict  # Promote helper
```

---

## 7. Regression-safety framework (binding)

Every SW PR must satisfy `docs/ENGINEERING_PROPOSAL.md` §4 and §4.2. Engine-touching work additionally follows §4.1.

### 7.1 Rules mapped to this feature

| §4 rule | Application |
|---|---|
| 1 Additive-only engine changes | `entry_window=None` default; no positional signature changes |
| 2 Golden-master before engine | **SW0** verifies legacy gate; **SW2** must keep `trades_legacy` identical |
| 3 Opt-in default-off | `enabled=False` / absent |
| 4 Schema-versioned persistence | setup / defaults namespace version bump when `entry_window` persists |
| 5 PIT / lookahead | Not a new level series; still require tests that membership uses **entry-bar local time only** (C2) — no future bars, no signal-bar substitution |
| 6 session_state stability | additive keys only; overlays must not mutate full-run keys; ARCHITECTURE updated same PR |
| 7 Determinism | pure functions; no wall clock |
| 8 Same-PR documentation | listed per PR below |
| 9 CI gate | full pytest + lint green |
| 10 Honesty framing | Focus vs Admit labels; C8 equity copy; USER_GUIDE |

### 7.2 Golden strategy

1. **Legacy family (existing):** must remain green through all SW PRs. SW2 default-off path is the hard gate. CI `golden-guard` continues to require `GOLDEN_REGEN` only for legacy filenames (same pattern as OTF).
2. **Enabled entry-window family (new, SW2):** additive artifacts under `tests/fixtures/golden/` analogous to enabled-OTF:
   - deterministic fixture with trades straddling segment boundaries (09:30 / 10:00) and next-bar-open signal/entry split
   - recorded accepted trades + skipped_signals projection with `outside_entry_window`
   - recorder script requiring `--confirm-regenerate`
   - tests asserting legacy isolation (enabled-window recorder must not rewrite legacy files)
   - document as **§2.3** in `tests/fixtures/golden/README.md` (mirror OTF §2.2)
3. **Focus ≡ Admit identity (C7):** unit/integration test in SW2; re-asserted in SW7.

### 7.3 Per-PR regression paragraph (required in PR body)

Each implementation PR body must include a short **Regression safety** section stating:

- whether engine code changed;
- which golden families were run;
- that defaults reproduce legacy;
- what new tests cover Focus vs Admit distinction (and C7 when engine-touched).

---

## 8. Implementation roadmap — fully scoped PRs

### Dependency graph

```text
SW0  Golden gate confirmation (docs + CI evidence; no behavior)
  │
  ├─► SW1  Post-hoc Focus analytics + Time Analysis / Backtest overlay UI
  │         (no engine; may land shared RTH export — C1)
  │
  └─► SW2  Engine entry_window admission + enabled-window golden (+ C7 identity)
            │
            ├─► SW2b Optional: audit no_new_entries_after → after_entry_cutoff
            │         (isolated; trade-set identity under default kwargs)
            │
            ├─► SW3  API + Backtest controls (Admit path)
            │         │
            │         ├─► SW4  Time Analysis Promote + Focus↔Admit handoff UX
            │         │
            │         ├─► SW5  Grid + Validation/WFA/sensitivity inheritance
            │         │
            │         └─► SW6  Setup persistence + Report/Bundles + Assistant honesty
            │
            └─► SW7  Hardening: docs corpus, release evidence, drift review
```

SW1 may land **in parallel** with SW2 after SW0 (no code dependency). Shared segment export (C1) lands with whichever of SW1/SW2 merges first. SW3+ require SW2. SW2b may follow SW2 anytime; not required for SW3. SW4 may start UI stubs after SW1 but must not claim Admit until SW3 wires re-sim.

---

### SW0 — Golden gate confirmation & proposal lock

**Goal.** Prove the legacy golden family is green on the branch base before any engine work; lock this proposal as the implementation contract.

**Scope.**

- [x] Run and record evidence: `pytest tests/test_golden_master.py tests/test_otf_golden.py` → **23 passed**.
- [x] Add this document (`docs/SESSION_ENTRY_WINDOW_PROPOSAL.md`) and pointer from `docs/ENGINEERING_ROADMAP.md`.
- [x] No production code changes.

**Out of scope.** Any `simulate_trades` edits; any UI.

**Regression safety.** Docs-only / evidence-only; no runtime drift.

**Acceptance.**

- [x] Proposal on PR branch with roadmap pointer.
- [x] Legacy + OTF golden tests green on the PR branch.
- [ ] Proposal merged (or base-available).

**Suggested PR title:** `SW0: session entry window proposal + golden gate confirmation`

---

### SW1 — Post-hoc Focus analytics + UI overlay

**Goal.** Let users click a Time Analysis bucket (or select a segment) and see a **Focused** Performance Summary, equity curve, and trade list — clearly labeled as post-hoc.

**Scope.**

- [ ] Export shared RTH segment API if not already landed (C1).
- [ ] Pure helpers: `filter_trades_by_entry_window`, `summarize_focused_trades`, provenance helper (C2, C5).
- [ ] Unit tests: segment filter, multi-segment OR (C3), clock_range (C4), empty trades, TZ = session/exchange not display (C5), `sample_warning` preserved.
- [ ] `pages/9_Time_Analysis.py`: “Focus summary on this bucket”; additive session_state keys; focused KPIs.
- [ ] `pages/7_Backtest.py`: if `focus_entry_window` set, overlay / toggle without destroying `trade_summary` / `trades` / `equity_curve`.
- [ ] Honesty banners including subset-replay equity language (C8).
- [ ] No calls that re-run `simulate_trades`.

**Out of scope.** Engine admission; Grid/WFA; setup persistence; Promote-to-re-sim (SW4).

**Regression safety.** Analytics-only; no engine; legacy goldens untouched; Time Analysis outputs unchanged when Focus unused; overlay keys never mutate full-run keys.

**Tests.**

- [ ] `tests/test_session_focus.py` — deterministic fixtures with known segment labels + boundary cases (09:59 vs 10:00 entry).
- [ ] Existing `tests/test_phase7_time_analysis.py` still green (no segment definition drift).

**Docs.** USER_GUIDE Time Analysis (+ Focus + C8); ARCHITECTURE session_state keys; ASSUMPTIONS (post-hoc ≠ deployable constraint); METRICS_GLOSSARY if provenance fields need names.

**Acceptance.**

- [ ] User can Focus `rth_open_30m` and see recomputed metric suite via `summarize_trades` on the subset.
- [ ] Clearing Focus restores full-run view without re-sim.
- [ ] Banner visible whenever Focus active (includes subset-replay equity note).
- [ ] §4.2 checklist satisfied; CI green.

**Suggested PR title:** `SW1: post-hoc time-bucket Focus summary (no re-sim)`

---

### SW2 — Engine `entry_window` admission + enabled golden

**Goal.** Add opt-in entry-window admission to `simulate_trades` with audited skips; prove legacy goldens unchanged; record enabled-window golden family; prove Focus ≡ Admit under allow_all (C7).

**Scope.**

- [ ] Shared normalize/contains helpers if not landed in SW1 (C1–C5) — `thesistester/engine/entry_window.py` or shared analytics module; keep import graph clean.
- [ ] `simulate_trades(..., *, entry_window=None)` keyword-only.
- [ ] Admission gate on **entry-bar** local time + `outside_entry_window` skip rows when capture requested.
- [ ] Enabled-window golden fixtures + recorder + tests (legacy isolation asserted).
- [ ] Document family in `tests/fixtures/golden/README.md` §2.3; CI golden-guard stays legacy-filename-scoped (additive family does not need `GOLDEN_REGEN`).
- [ ] Unit tests: inclusive start / exclusive end; boundaries 09:30 and 10:00; signal-in-segment / entry-out-of-segment (next-bar-open); multi-segment OR; disabled path identity; windowed-out never blocks exposure; **C7 Focus ≡ Admit identity**.

**Out of scope.** Streamlit UI; Grid/WFA wiring; changing RTH segment **bounds**; `after_entry_cutoff` audit (**SW2b**).

**Regression safety.**

- [ ] Default `entry_window=None` → legacy trades golden **value-equal**.
- [ ] No regeneration of legacy golden without `GOLDEN_REGEN` (§4.1).
- [ ] New golden family additive only.
- [ ] C7 identity test green.

**Tests.**

- [ ] Legacy golden suite green.
- [ ] `tests/test_entry_window_admission.py` (includes C7).
- [ ] `tests/test_entry_window_golden.py` (enabled family).

**Docs.** ASSUMPTIONS (admission vs Focus; C6 filter order; C9 AND with cutoff); ARCHITECTURE (engine parameter); `tests/fixtures/golden/README.md` §2.3; this proposal status → SW2 done.

**Acceptance.**

- [ ] Constrained sim admits only in-window entries on fixture.
- [ ] Skips auditable with `outside_entry_window`.
- [ ] Legacy golden untouched and green.
- [ ] C7 identity holds.
- [ ] §4.2 checklist + regression paragraph in PR body.

**Suggested PR title:** `SW2: opt-in entry_window admission (golden-gated)`

---

### SW2b — Audit parity for `no_new_entries_after` *(optional, isolated)*

**Goal.** Convert silent cutoff `continue` into audited `skip_reason="after_entry_cutoff"` when skip capture is requested — without changing the admitted trade set.

**Scope.**

- [ ] When `return_skipped_signals` or `return_result`, record cutoff rejects; when both false, behavior/shape unchanged.
- [ ] Identity test: default kwargs trade frame value-equal to pre-SW2b (and legacy golden still green).

**Out of scope.** Any change to cutoff semantics (`>` vs `>=`); UI; entry_window changes.

**Regression safety.** Trade admission set immutable; skip rows additive only under capture flags.

**Suggested PR title:** `SW2b: audit no_new_entries_after skips (after_entry_cutoff)`

---

### SW3 — API + Backtest UI for Admit path

**Goal.** Users can configure and run a constrained backtest from the Backtest page and headless API.

**Scope.**

- [ ] `api.run_backtest` settings schema: accept `entry_window`; validate/normalize; pass to `simulate_trades`.
- [ ] `_BACKTEST_DEFAULTS` / related defaults: `entry_window=None`; absent key ≡ disabled.
- [ ] `pages/7_Backtest.py`: controls for mode (`rth_segments` multiselect / clock range), show exchange/session TZ (C5), enable toggle.
- [ ] Surface skip counts for `outside_entry_window` beside exposure skips.
- [ ] Constrained-run honesty banner after run when window enabled.
- [ ] API unit/integration tests.

**Out of scope.** Grid/WFA (SW5); Promote CTA (SW4); setup library save (SW6).

**Regression safety.** UI/API defaults leave window disabled → identical to pre-SW3 runs; no engine default change.

**Tests.**

- [ ] API tests: disabled ≡ omit key; enabled filters trades; invalid config errors cleanly; TZ normalization (C5).
- [ ] Optional Streamlit-free settings builder unit test.

**Docs.** USER_GUIDE Backtest section; ARCHITECTURE API settings; ASSUMPTIONS; METRICS if skip reasons listed in glossary.

**Acceptance.**

- [ ] End-to-end: enable `rth_open_30m` → Run Backtest → Performance Summary reflects only admitted trades; skips listed.
- [ ] Disabled path matches prior behavior on golden fixture via API.
- [ ] CI green; §4.2.

**Suggested PR title:** `SW3: Backtest + API entry_window controls`

---

### SW4 — Time Analysis Promote + Focus↔Admit handoff

**Goal.** One-click research loop from discovery to armed constraint.

**Scope.**

- [ ] Time Analysis actions per selected group/segment:
  1. **Focus summary** (SW1 — ensure wired to row selection).
  2. **Promote to entry window** — writes normalized `st.session_state["entry_window"]` via `segment_label_to_entry_window` (C1, C5); does **not** auto-run sim.
- [ ] Clear CTA to Backtest: “Run Backtest to re-simulate under this window.”
- [ ] Guardrails: confirm dialog if promoting a bucket below `min_trades` / `sample_warning`.
- [ ] Keep Focus and Admit visually distinct (two banners / two badges).

**Out of scope.** Auto-running backtest on Promote; changing Grid.

**Regression safety.** UI/session_state additive; no engine change beyond using SW2/SW3 paths; Promote does not mutate `trades` until re-run.

**Tests.**

- [ ] Pure helper: segment label → normalized `entry_window` dict (TZ set per C5).
- [ ] Promote does not mutate `trades` / `trade_summary` until Backtest re-run.

**Docs.** USER_GUIDE research loop (Discover → Scope → Re-sim); ASSUMPTIONS; this proposal status.

**Acceptance.**

- [ ] From `rth_open_30m` row: Focus works; Promote arms config; Backtest run applies Admit.
- [ ] Thin-sample confirm path works.
- [ ] CI green; §4.2.

**Suggested PR title:** `SW4: Time Analysis Focus + Promote to entry window`

---

### SW5 — Grid + Validation / WFA / sensitivity inheritance

**Goal.** Steps 4–5 of the research loop: optimize and validate under the **same** entry window.

**Scope.**

- [ ] `run_sl_tp_grid` / `api.run_grid`: passthrough `entry_window` to every cell (fixed policy); `_GRID_DEFAULTS["entry_window"]=None`.
- [ ] Walk-forward / WFA matrix: passthrough; **no** per-fold reselection of segments.
- [ ] `sensitivity.py` `execution_kwargs`: passthrough `entry_window` (already kwargs-shaped).
- [ ] `pages/8_Grid_Search.py` + `pages/10_Validation.py`: show active window; controls to edit or clear; warning that window is not a swept axis.
- [ ] Grid/WFA/sensitivity result metadata includes entry_window fingerprint/hash for artifact honesty.
- [ ] Tests: two-cell grid with window enabled → both cells see same admission constraint; WFA fold uses window; sensitivity OAT cell inherits window.

**Out of scope.** Adding entry window as a grid search dimension; portfolio multi-setup window matrix.

**Regression safety.** Default disabled → grid/WFA/sensitivity outputs match prior goldens/tests; additive metadata only when enabled.

**Tests.**

- [ ] Grid passthrough unit test.
- [ ] WFA passthrough unit test.
- [ ] Sensitivity `execution_kwargs` passthrough unit test.
- [ ] Existing grid/WFA suites green with defaults.

**Docs.** USER_GUIDE Grid + Validation; ASSUMPTIONS (no axis sweeping); ARCHITECTURE; research-methodology note if applicable.

**Acceptance.**

- [ ] Constrained grid runs without treating time as a parameter axis.
- [ ] Validation battery (incl. sensitivity) respects window.
- [ ] CI green; §4.2.

**Suggested PR title:** `SW5: Grid + Validation inherit entry_window (fixed constraint)`

---

### SW6 — Setup persistence, Report/Bundles, Assistant honesty

**Goal.** Make the constraint durable across sessions and visible in exports / Discuss-results language.

**Scope.**

- [ ] Optional `entry_window` on setup config via `build_setup_config` / normalize / validate; schema version bump; old setups load with disabled default.
- [ ] Report Export + Research Bundles: include `entry_window`, focus provenance, skip_reason counts, Focus-vs-Admit flag.
- [ ] Assistant projections / Help:
  - If constrained Admit run present → cite results **under declared window**.
  - Else → keep descriptive Time Analysis language + sample warnings; **do not** imply a live schedule from “best entry window” alone.
  - Never claim edge from Focus-only summaries.
- [ ] Defaults namespace compatibility (`_normalize_*`) for backtest defaults if persisted.

**Out of scope.** New assistant tools beyond honesty/projection updates; auto-thesis rewriting.

**Regression safety.** Absent key ≡ disabled; bundle schema additive; assistant must not claim edge from Focus alone.

**Tests.**

- [ ] Setup load/save round-trip with and without entry_window.
- [ ] Bundle/report includes new fields when present; omits cleanly when absent.
- [ ] Assistant projection unit tests: descriptive vs constrained-run gates; Focus-alone blocked from deployable language.

**Docs.** USER_GUIDE Setup + Export; ARCHITECTURE persistence; HELP corpus coverage if required by allowlist process; ASSUMPTIONS; METRICS_GLOSSARY skip reasons.

**Acceptance.**

- [ ] Save setup with window → reload → Backtest/Grid see same constraint.
- [ ] Exported artifact shows window + whether summary was Focus vs Admit.
- [ ] CI green; §4.2.

**Suggested PR title:** `SW6: persist entry_window in setups, exports, assistant honesty`

---

### SW7 — Hardening, release evidence, drift review

**Goal.** Engineering release readiness for the feature series (same spirit as OTF hardening).

**Scope.**

- [ ] Cross-page parity audit: Backtest / Grid / Validation / API / Assistant settings fingerprints match.
- [ ] Enabled entry-window golden still green; legacy golden still green; C7 identity still green.
- [ ] Docs drift pass: USER_GUIDE, ASSUMPTIONS, ARCHITECTURE, METRICS, AGENT_GUIDE cross-links, this proposal status all ✅.
- [ ] `docs/SESSION_ENTRY_WINDOW_RELEASE_EVIDENCE.md` — commands run, fixtures used, known limits (sample size, C6/C9 filter stacking, no overnight wrap in v1, C8 subset-replay equity).
- [ ] Final honesty review: no UI/assistant string implies OOS proof from Focus.

**Out of scope.** Real-user OOS statistical approval (user-executed, like OTF); advanced “time as grid axis” research mode.

**Regression safety.** Prefer docs + tests only; any code fix must be default-preserving.

**Acceptance.**

- [ ] Evidence doc merged.
- [ ] Parity checklist complete.
- [ ] CI green; engineering review sign-off recorded in evidence doc.

**Suggested PR title:** `SW7: session entry window hardening + release evidence`

---

## 9. Deferred follow-ups (explicitly not in SW0–SW7)

| Item | Rationale for deferral |
|---|---|
| Entry window as Grid/WFA search axis | High overfitting risk; needs multiple-testing framework |
| Overnight-wrapping clock ranges | Edge-case complexity; v1 half-open same-day is enough for RTH segments |
| Signal-generation-time filter (pre-sim in `generate_signals`) | ENGINEERING.md aspirational; admission at **entry** time is the v1 contract (C2) |
| Per-vendor session calendars / holidays | Instrument presets already cover ES/NQ RTH; holiday calendars are a data problem |
| Auto-Promote best bucket | Violates pre-declaration discipline |

---

## 10. Risk register

| Risk | Mitigation |
|---|---|
| Users treat Focus KPIs as deployable edge | Mandatory banners (incl. C8); Promote requires re-sim; Assistant honesty (SW4/SW6/SW7) |
| Thin buckets (n≪30) over-trusted | `sample_warning` + confirm on Promote |
| Legacy golden broken by engine/skip work | SW2: default-off identity; skip rows only when capture on; SW2b isolated |
| TZ confusion (display vs session) | C5 law; Promote writes exchange TZ; UI shows session TZ for segments |
| Focus/Admit disagree for same window | C7 identity test under allow_all/0 cooldown; document divergence when exposure on |
| Signal vs entry at segment boundary | C2 + explicit next-bar-open boundary tests |
| Segment definition drift | C1 shared export; phase-7 tests must stay green |
| Double-filtering with OTF / cutoff | C6 order + C9 AND docs; neither replaces the other |
| Scope creep into time-axis optimization | Non-goals + SW5 warning copy |
| session_state key sprawl / full-run mutation | Overlay-only keys; tests that Focus clear restores without re-sim |

---

## 11. Success criteria

The feature series is successful when a trader can:

1. See that all-day results are poor while `rth_open_30m` looks strong (**Discover** — already exists, enriched by Focus).
2. Focus the full metric suite on that bucket in one click (**SW1**).
3. Promote it to an entry window and re-run Backtest (**SW3–SW4**).
4. Grid SL/TP and run Validation/sensitivity under that same window without the tool silently expanding back to all-day (**SW5**).
5. Save/export the constraint with honest labeling (**SW6–SW7**).
6. Throughout: **legacy defaults remain golden-identical**; C7 holds; CI green; docs match behavior.

---

## 12. Per-PR acceptance checklist (copy into every SW PR)

Mandatory (from `ENGINEERING_PROPOSAL.md` §4.2), plus feature-specific items:

- [ ] Unit tests for new functionality (deterministic).
- [ ] Golden-master tests preserved (legacy outputs unchanged).
- [ ] If engine-enabled path added: enabled entry-window golden/tests added; README §2.3 updated.
- [ ] If engine-touched: C7 Focus ≡ Admit identity test present/green.
- [ ] Normative contracts C1–C9 respected for any path touched.
- [ ] `random_state` only where randomness exists (N/A for pure window filters).
- [ ] Docs updated same PR: ASSUMPTIONS, ARCHITECTURE, USER_GUIDE, and METRICS/glossary as needed.
- [ ] Focus vs Admit honesty copy present (incl. C8 when Focus UI touched).
- [ ] CI green (pytest + lint).
- [ ] Small surface area; PR body includes **Regression safety** paragraph.
- [ ] This proposal’s status checkbox / tracker for the SW item marked done.

---

## 13. Status tracker

| Milestone | Status | PR |
|---|---|---|
| SW0 Proposal + golden confirmation | Proposal revised (normative contracts C1–C9); legacy + OTF golden gate green (`23 passed`) | [#286](https://github.com/AccumuLatata/ThesisTester/pull/286) |
| SW1 Post-hoc Focus | Not started | — |
| SW2 Engine admission + golden + C7 | Not started | — |
| SW2b Cutoff skip audit | Not started (optional) | — |
| SW3 API + Backtest UI | Not started | — |
| SW4 Promote handoff UX | Not started | — |
| SW5 Grid + Validation/sensitivity inheritance | Not started | — |
| SW6 Persistence + export + assistant | Not started | — |
| SW7 Hardening + release evidence | Not started | — |

---

## 14. Appendix — industry practice (design justification)

- **Trade the session you tested.** Aggregated all-day stats can hide open-session edge and midday leak; session-specific metrics are the honest unit of analysis for intraday systems.
- **Pre-declare filters; limit filter layers; validate forward.** Post-hoc discovery of a bucket is allowed as exploration; promoting it without OOS/WFA is data-mining.
- **SOTA landscape (§9):** time-of-day / regime breakdowns are essential for NQ/ES confluence edges; this proposal converts that diagnostic into a constrained research workflow without becoming a strategy factory.

These references inform UX honesty and sequencing; they do not expand SW0–SW7 scope.
