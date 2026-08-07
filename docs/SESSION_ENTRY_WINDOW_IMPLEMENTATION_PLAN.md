# Session Entry Window — Implementation Plan

**Document type:** Implementation plan (fully scoped PRs)  
**Date:** 2026-08-06  
**Last revised:** 2026-08-07 (pre-implementation audit; renamed from proposal)  
**Status:** Ready for implementation — **SW1 next** (zero engine risk)  
**Inputs:** Time Analysis / Backtest UX gap analysis; design-review contracts C1–C9; codebase audit vs `simulate_trades` / golden / session_state; `docs/ENGINEERING_PROPOSAL.md` §4  
**Related code:** `thesistester/analytics/time_analysis.py`, `thesistester/engine/backtest.py`, `thesistester/analytics/grid.py`, `thesistester/analytics/walk_forward.py`, `thesistester/analytics/overfitting.py`, `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/9_Time_Analysis.py`, `pages/10_Validation.py`, `thesistester/api.py`  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4 (including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist)

**Supersedes:** `docs/SESSION_ENTRY_WINDOW_PROPOSAL.md` (renamed).

---

## 0. Pre-implementation audit (2026-08-07)

### Verdict

**No hard blockers for SW1.** Legacy golden identity for engine defaults remains sound. One SW2 honesty issue was resolved by splitting cutoff skip-audit into **SW2b** (see §8). Gaps below are incorporated into this plan.

| Check | Result |
|---|---|
| Legacy golden vs skip audit | Golden pipeline uses default `return_result=False`; asserts **trades only**. Default `entry_window=None` keeps trades identity. |
| Product skip capture | Backtest/API use `return_result=True`; UI currently labels all skips as exposure-only → **SW2 must not expand skip reasons without UI/docs honesty** (hence SW2b / SW3 labeling). |
| session_state key collisions | Proposed Focus/Admit keys unused today. |
| Focus metrics path | Use `metrics.summarize_trades` + `metrics.equity_curve` (not `time_analysis.summarize_by_group`). `sample_warning` is **provenance/UI**, not a `summarize_trades` field. |
| `_RTH_SEGMENTS` | Private today → SW1 exports public `RTH_SEGMENT_LABELS` / bounds helpers (C1). |
| Setup persistence | Follow OTF **additive normalize** pattern; do **not** require `SETUP_SCHEMA_VERSION` bump (OTF did not bump it). |
| Grid/WFA | Explicit keyword-only `entry_window=None`; also add to `overfitting._SIMULATION_KWARGS` in SW5 or sensitivity silently drops it. |
| SW1 engine independence | Confirmed — analytics + UI overlays only. |
| Test filenames | `tests/test_golden_master.py`, `tests/test_otf_golden.py` exist; SW0 evidence: **23 passed**. |

---

## 1. Executive summary

ThesisTester already surfaces the insight that **all-day Performance Summary can look terrible while a single RTH segment (e.g. `rth_open_30m`) looks promising**. Time Analysis does that well as a **descriptive** layer. What the product cannot do today is close the research loop:

1. **Focus** the Performance Summary on one time bucket (post-hoc).
2. **Promote** that bucket into a first-class **entry window** rule.
3. **Re-simulate** under that rule (correct exposure/cooldown interaction).
4. **Grid** SL/TP inside that constrained window.
5. **Validate** (WFA / MC / sensitivity) under the **same** constraint — without silently re-picking the best hour.

This plan ships that loop as an additive, opt-in, golden-gated capability series (**SW0–SW7**, plus optional **SW2b**), sequenced so post-hoc exploration lands before any engine change, and so engine admission is proven against the existing legacy golden family before UI/grid/validation wiring multiplies surface area.

**Positioning:** deepen session-aware confluence research for ES/NQ. Time-of-day becomes a **declared strategy constraint**, not an unconstrained search axis (default).

---

## 2. Problem statement

### 2.1 User-observed failure mode

| Surface | Typical reading | What it actually measures |
|---|---|---|
| Backtest **Performance Summary** | “Strategy is terrible” | Expectancy of **all admitted entries** across the whole session |
| Time Analysis row **`rth_open_30m`** | “Setup looks promising” | Descriptive KPIs on the **subset** of completed trades whose entry fell in 09:30–09:59 ET |

Intraday markets are non-stationary across the RTH day. Aggregating them washes out session-specific edge.

### 2.2 Product gaps today

| Desired action | Current state |
|---|---|
| Filter Performance Summary / equity / advanced risk to one RTH segment | **Missing** |
| Admit entries only in a declared window at simulation time | **Missing** (only silent `no_new_entries_after` upper cutoff) |
| Run Grid / WFA / sensitivity under that constraint | **Missing** |
| Honesty labeling: post-hoc subset vs re-sim | **Partial** |

### 2.3 Why “just filter the table” is not enough

Post-hoc subsetting answers: *“Of the trades that filled under the all-day policy, how did this bucket do?”*

It does **not** answer: *“If I had refused all non-window entries, how would exposure, cooldown, and later signals interact?”*

For deployment honesty, the product must support **engine admission** after discovery — not only analytics filtering.

---

## 3. Recommended research loop (product contract)

| Step | Name | User action | System behavior | Honesty label |
|---|---|---|---|---|
| **1** | **Discover** | Run Backtest → Time Analysis | Descriptive grouping | “Descriptive on this sample; not a live schedule” |
| **2** | **Scope** | Declare intended window | Persist in session/setup/backtest settings | Pre-declared filter category |
| **3** | **Re-sim** | Run Backtest with entry window | Engine admits only in-window entries; audited skips | “Constrained re-simulation” |
| **4** | **Optimize** | Run Grid with the **same** window | Fixed policy across cells | Window is constraint, not fitness axis |
| **5** | **Prove** | Validation / WFA / MC / sensitivity | Same window; no per-fold best-hour reselection | Diagnostic, not proof of edge |

**Sample-size gate:** UI must surface `trade_count` and a provenance `sample_warning` (`trade_count < min_trades`) whenever a Focused or constrained summary is shown.

---

## 4. Goals and non-goals

### 4.1 Goals

1. Post-hoc **Focus** of Performance Summary + equity + trade list on a time bucket.
2. First-class **entry window** admission in `simulate_trades` (opt-in, default off).
3. Auditable skips for window rejects; cutoff audit isolated in SW2b.
4. Propagation through API → Backtest → Grid → Validation/WFA/sensitivity → reporting.
5. Time Analysis **Promote** CTA (SW4).
6. Same-PR documentation.
7. Full regression safety per §4.

### 4.2 Non-goals

| Non-goal | Why |
|---|---|
| Sweeping RTH segments / clock minutes as a default Grid axis | Overfitting risk; deferred |
| Changing RTH segment definitions | Needs dedicated versioned PR |
| Replacing / conflating OTF with clock windows | Orthogonal |
| Live broker session calendars | Research-only tool |
| Claiming OOS edge from Focused summaries | Honesty |
| Auto-Promote best bucket | Violates pre-declaration |

---

## 5. Design principles

1. **Additive, opt-in, default-off** — unset / `None` / `enabled=False` reproduces legacy (`ENGINEERING_PROPOSAL.md` §4 rules 1, 3).
2. **Two modes, never conflated:** `focus` (post-hoc) vs `admit` (re-sim).
3. **Shared public RTH vocabulary (C1)** — export labels/bounds from `time_analysis`; no duplicated minute bounds.
4. **Audited window admission** — `outside_entry_window` in `skipped_signals` when capture is on. Cutoff audit (`after_entry_cutoff`) is **SW2b**, not bundled into SW2 UI-blind.
5. **Fixed constraint in Grid/WFA/sensitivity** — not a swept axis.
6. **Same-PR docs.**
7. **Golden before engine** — SW0 evidence; SW2 must keep legacy trades identical.

---

## 6. Technical design

### 6.0 Normative contracts (C1–C9) — binding acceptance rules

| ID | Contract |
|---|---|
| **C1** | Shared exported RTH segment vocabulary (labels + minute bounds). Callers must not hardcode segment intervals. |
| **C2** | Filter on **entry-bar** local time (simulated entry bar), not signal-bar time. Next-bar-open can place the signal in `rth_open_30m` and the entry in `rth_morning` — both Focus and Admit classify by **entry**. Focus defaults to `entry_timestamp` (Time Analysis default). |
| **C3** | Multi-segment allowlist = **OR** (entry matches any listed segment). Empty list with `enabled=True` is invalid. |
| **C4** | Clock range is half-open `[start, end)` in local minutes; **no overnight wrap in v1** (`end <= start` → validation error). Segment mode already uses exclusive end minutes. |
| **C5** | TZ law: RTH-segment mode **always** evaluates in instrument exchange/session TZ (never display TZ). `timezone: None` normalizes to exchange/session TZ; Promote must write that TZ explicitly into the normalized dict. Hour/30m Focus maps to `clock_range` using the active bucket TZ basis. |
| **C6** | Filter order: OTF (pre-sim) → entry_window (admission) → exposure/cooldown. Neither replaces the other; window rejects never enter exposure competition. |
| **C7** | Focus ≡ Admit identity under `exposure_policy="allow_all"` + `cooldown_bars_after_exit=0`: `set(admit.signal_id) == set(focus_filter(all_day).signal_id)`. Required SW2 acceptance test. Divergence under other exposure policies is expected (why Admit exists). |
| **C8** | Focus equity/DD is **subset-replay only** (equity rebuilt from filtered completed trades), not path DD under the all-day admission set. Banner required whenever Focus equity/DD is shown. |
| **C9** | `entry_window` AND `no_new_entries_after` both apply when set. Cutoff uses strict `>` (entry **at** cutoff still admits). Prefer `entry_window` for new UX; keep cutoff for backward compat. |

### 6.1 Config shape (canonical)

```python
entry_window: dict[str, Any] | None = None
# Normalized form when enabled:
{
    "enabled": False,
    "mode": "rth_segments",              # "rth_segments" | "clock_range"
    "rth_segments": [],                  # e.g. ["rth_open_30m"]
    "start_time": None,                  # "HH:MM" or "HH:MM:SS"
    "end_time": None,                    # exclusive end
    "timezone": None,                    # None => session/exchange TZ
}
```

**Normalization rules:**

- Missing / `None` / `enabled=False` → legacy (no filter).
- `mode="rth_segments"` → non-empty subset of public `RTH_SEGMENT_LABELS`.
- `mode="clock_range"` → both times; half-open; no wrap (C4).
- One mode active; invalid combos fail before sim/filter.
- AND with `no_new_entries_after` (C9).

**Bucket → config mapping (SW1 Focus / SW4 Promote):**

| Source group column | Mapped `entry_window` |
|---|---|
| `entry_rth_segment` | `mode=rth_segments`, `rth_segments=[value]` |
| `entry_hour_bucket` (e.g. `"09:00"`) | `mode=clock_range`, `[HH:00, HH+1:00)` |
| `entry_30min_bucket` (e.g. `"09:30"`) | `mode=clock_range`, `[HH:MM, HH:MM+30)` |

**Setup persistence (SW6):** additive optional key + `normalize_entry_window` / effective getter with disabled default — **same pattern as `otf_filter`**, not a required `SETUP_SCHEMA_VERSION` bump.

### 6.2 Analytics: Focus (post-hoc) — SW1

Prefer shared pure module `thesistester/analytics/entry_window.py` (imported by Time Analysis UI; later by engine/API) **or** helpers in `time_analysis.py` that re-export public segment vocabulary. Avoid duplicating bounds.

| Function | Behavior |
|---|---|
| `RTH_SEGMENTS` / `RTH_SEGMENT_LABELS` | Public export of today’s bounds (C1); matcher shared |
| `normalize_entry_window(...)` | Validate/normalize; fill exchange TZ when `timezone` is None (C5) |
| `entry_window_contains(local_ts, entry_window)` | Membership predicate (C2–C5) |
| `entry_window_from_bucket(col, value, ...)` | Map table selection → normalized config (TZ written) |
| `filter_trades_by_entry_window(trades, entry_window, ...)` | Bucket/mask → filtered copy |
| `summarize_focused_trades(...)` | filter → `metrics.summarize_trades` + `metrics.equity_curve` (+ optional direction split) |
| `focus_provenance(...)` | includes `sample_warning`, counts, mode label, C8 equity caveat flag |

No engine calls. Deterministic. Empty-safe. Shared helpers must be importable by SW2 engine without Streamlit.

### 6.3 Engine: Admit (re-sim) — SW2

```python
simulate_trades(..., *, entry_window: dict | None = None)
```

- Disabled → legacy path (golden identity).
- Outside window → not admitted; when capture on → `skip_reason="outside_entry_window"`.
- Ordering: after entry localization, before exposure (C6).
- **C7 test required** in SW2: Focus filter on unconstrained all-day trades ≡ Admit trades when `allow_all` + 0 cooldown.

**SW2 out of scope:** changing `no_new_entries_after` skip audit; Streamlit skip captions (see SW2b / SW3).

### 6.3b Cutoff skip audit — SW2b (optional, isolated)

Convert silent `no_new_entries_after` `continue` into `skip_reason="after_entry_cutoff"` when skip capture is on, **and** update Backtest/ASSUMPTIONS copy that currently says skips are exposure-only. Do not ship audit without honesty relabel. Legacy trades under default kwargs remain golden-identical.

### 6.4 API / pages / session_state

| Surface | Change |
|---|---|
| API / Grid / WFA / sensitivity | Accept/passthrough `entry_window` (SW3/SW5); sensitivity via `_SIMULATION_KWARGS` |
| `pages/7_Backtest.py` | Focus overlay (SW1); Admit controls + skip labeling (SW3) |
| `pages/9_Time_Analysis.py` | Focus (SW1); Promote (SW4) |
| `pages/8_Grid_Search.py` / `10_Validation.py` | Inherit fixed window (SW5) |
| Reporting / bundles | Persist window + focus provenance (SW6) |

**Additive session_state keys:**

| Key | Producer | Consumer | Schema |
|---|---|---|---|
| `entry_window` | Backtest / Promote / Setup | Grid, Validation, API, Report | normalized dict |
| `entry_window_armed` | Promote (SW4) | Backtest / Time Analysis armed banner | `bool` — True until constrained re-sim |
| `entry_window_promote_provenance` | Promote (SW4) | banners / thin-sample audit | dict (`status`, counts, `sample_warning`) |
| `focus_entry_window` | Focus action | Backtest / Time Analysis overlay | dict or `None` |
| `focused_trade_summary` | Focus action | UI | same as `trade_summary` |
| `focused_equity_curve` | Focus action | UI | same as `equity_curve` |
| `focused_trades` | Focus action | trade table / export | DataFrame subset |
| `focus_provenance` | Focus action | banners / export | dict |

Existing keys keep producers/consumers. Focus keys are overlays — Clear Focus restores full-run view without re-sim.

Also document existing `skipped_signals` in ARCHITECTURE when SW3/SW2b touch skip UX (currently used but missing from contract table).

### 6.5 Skip-reason vocabulary (additive)

| `skip_reason` | When |
|---|---|
| existing exposure reasons | unchanged |
| `outside_entry_window` | SW2 |
| `after_entry_cutoff` | SW2b |

### 6.6 UI copy requirements (non-optional)

- Focus banner: **“Post-hoc subset — not re-simulated. Exposure/cooldown still reflect the all-day run.”**
- Focus equity (C8): **“Equity/drawdown rebuilt from the filtered trade subset only.”**
- After Promote + before re-run: **“Entry window armed. Run Backtest to re-simulate under this constraint.”**
- After constrained run: **“Constrained re-simulation — only in-window entries were admitted.”**
- Thin sample: provenance `sample_warning`; never “best entry” without count.

---

## 7. Regression-safety framework (binding)

Every SW PR satisfies `ENGINEERING_PROPOSAL.md` §4 and §4.2. Engine-touching work follows §4.1.

| §4 rule | Application |
|---|---|
| 1 Additive-only engine | `entry_window=None` default; no positional changes |
| 2 Golden before engine | SW0 evidence; SW2 keeps `trades_legacy` identical |
| 3 Opt-in default-off | `enabled=False` / absent |
| 4 Persistence | Additive normalize (OTF pattern); version bump only if truly required |
| 5 PIT | Window uses entry-bar local time only (C2) |
| 6 session_state | Additive keys; ARCHITECTURE same PR |
| 7 Determinism | Pure functions |
| 8 Same-PR docs | Per PR below |
| 9 CI | pytest + lint green |
| 10 Honesty | Focus vs Admit; C8 |

**Golden strategy:** legacy family always green; SW2 adds additive enabled-window family with legacy isolation (like enabled-OTF).

**PR body must include Regression safety paragraph:** engine touched? which goldens? defaults legacy? Focus vs Admit tests?

---

## 8. Implementation roadmap — fully scoped PRs

### Dependency graph

```text
SW0  Plan lock + golden confirmation
  │
  ├─► SW1  Post-hoc Focus analytics + UI overlay
  │         (no engine)
  │
  └─► SW2  Engine entry_window + outside_entry_window + C7 + enabled golden
            │
            ├─► SW2b (optional) after_entry_cutoff audit + skip UI/docs honesty
            │
            ├─► SW3  API + Backtest Admit controls (+ skip labeling for window)
            │         │
            │         ├─► SW4  Promote + Focus↔Admit handoff  ← NEXT
            │         │
            │         ├─► SW5  Grid + Validation/WFA/sensitivity inherit
            │         │         (incl. overfitting._SIMULATION_KWARGS)
            │         │
            │         └─► SW6  Setup normalize + Report/Bundles + Assistant
            │
            └─► SW7  Hardening + release evidence
```

SW1 may land in parallel with SW2 design after SW0. SW3+ require SW2. **Do not start SW2 until C7 fixture design is clear; do not merge cutoff audit without SW2b honesty scope.**

---

### SW0 — Plan lock & golden confirmation

**Goal.** Lock this document; prove legacy golden green before engine work.

**Scope.**

- [x] Golden evidence: `pytest tests/test_golden_master.py tests/test_otf_golden.py` → 23 passed.
- [x] Implementation plan + ENGINEERING_ROADMAP pointer.
- [x] Pre-implementation audit + C1–C9 + SW2b split.
- [ ] No production runtime behavior changes in the SW0 docs PR itself.

**Regression safety.** Docs-only for SW0 commit series prior to SW1 code.

**Suggested PR title:** `SW0: session entry window implementation plan + golden gate`

---

### SW1 — Post-hoc Focus analytics + UI overlay

**Goal.** Focus a Time Analysis bucket and see full Performance Summary / equity / trade list as a labeled post-hoc overlay.

**Scope.**

- [ ] Public `RTH_SEGMENT_LABELS` (+ bounds helper) from `time_analysis` (C1).
- [ ] Pure helpers: normalize, `entry_window_from_bucket`, filter, `summarize_focused_trades`, provenance (`sample_warning`).
- [ ] Unit tests: segments, clock_range, hour/30m mapping, empty trades, TZ law for segments (C5), C8 provenance flag.
- [ ] `pages/9_Time_Analysis.py`: select bucket → Focus / Clear Focus; focused KPI section + banners.
- [ ] `pages/7_Backtest.py`: if Focus set, overlay toggle for summary/equity/trades **without** destroying `trade_summary` / `equity_curve` / `trades`.
- [ ] Honesty banners (Focus + C8).
- [ ] Docs: USER_GUIDE, ARCHITECTURE keys, ASSUMPTIONS.
- [ ] **Zero** `simulate_trades` changes.

**Out of scope.** Engine admission; Promote (SW4); Grid/WFA; setup persistence.

**Regression safety.** Analytics/UI additive; legacy goldens untouched; Time Analysis unchanged when Focus unused.

**Tests.** `tests/test_session_focus.py`; `tests/test_phase7_time_analysis.py` still green.

**Acceptance.**

- [ ] Focus `rth_open_30m` → full `summarize_trades` suite on subset.
- [ ] Clear Focus restores full-run view without re-sim.
- [ ] Banner + C8 equity caveat visible when Focus active.
- [ ] CI green; §4.2.

**Suggested PR title:** `SW1: post-hoc time-bucket Focus summary (no re-sim)`

---

### SW2 — Engine `entry_window` admission + C7 + enabled golden

**Goal.** Opt-in admission with `outside_entry_window` skips; legacy trades golden-identical; C7 Focus≡Admit gate.

**Scope.**

- [ ] Shared normalize used by engine (import from analytics module or thin engine wrapper).
- [ ] `simulate_trades(..., *, entry_window=None)`.
- [ ] Skip rows when capture on.
- [ ] Enabled-window golden family + legacy isolation.
- [ ] C7 identity test (`allow_all`, cooldown 0).
- [ ] Boundary tests (09:30 inclusive / 10:00 exclusive); signal-in-segment / entry-out-of-segment (next-bar-open, C2).

**Out of scope.** `after_entry_cutoff` (SW2b); Streamlit Admit controls (SW3); changing RTH **bounds**.

**Regression safety.** Default off → legacy trades value-equal; no legacy golden regen.

**Suggested PR title:** `SW2: opt-in entry_window admission (golden-gated, C7)`

---

### SW2b — Cutoff skip audit + honesty (optional)

**Goal.** Audit `no_new_entries_after` skips without lying in the UI.

**Scope.** Engine skip row + Backtest caption/ASSUMPTIONS relabel (“exposure and entry-policy skips” or split counts).

**Regression safety.** Trades identical under default kwargs; skip frame only changes when cutoff rejects exist and capture is on.

---

### SW3 — API + Backtest Admit UI

Wire `entry_window` into `api.run_backtest` + Backtest controls; show window skip counts separately from exposure; constrained-run banner. Defaults disabled → identical behavior.

**Scope.**

- [x] `_BACKTEST_DEFAULTS["entry_window"]=None`; `validate_run_spec` + `run_backtest` normalize/passthrough.
- [x] `pages/7_Backtest.py`: Admit toggle (RTH segments / clock range); pass to `simulate_trades`.
- [x] Skip captions: split `outside_entry_window` vs exposure/other; Admit honesty banner.
- [x] Additive execution-defaults keys for Admit widgets (no schema bump).
- [x] Docs: USER_GUIDE, ARCHITECTURE (`entry_window`, `skipped_signals`), ASSUMPTIONS, roadmap/status.
- [x] Tests: API default-off parity, enabled admit+skip, validate_run_spec, defaults sanitize, `partition_skip_counts`.

**Out of scope.** SW2b cutoff audit; Promote (SW4); Grid/WFA inherit (SW5); setup library persistence (SW6).

**Regression safety.** Default-off → legacy-identical trades; engine already gated in SW2; no golden trade mutation.

---

### SW4 — Promote + Focus↔Admit handoff  ← **implement next**

Promote Focused/selected bucket → `entry_window` armed (no auto-run); thin-sample confirm; distinct Focus vs Admit badges.

**Scope.**

- [x] Pure helpers: `promote_entry_window`, widget-state mapping, apply/clear armed session handoff.
- [x] Time Analysis: **Promote to Admit** CTA; thin-sample confirm when `sample_warning`; no auto-run.
- [x] Promote writes explicit TZ into normalized dict (C5); overwrites Backtest Admit widget keys.
- [x] Distinct badges: Focus vs Admit armed vs Admit applied; armed banner before re-sim.
- [x] Backtest: show armed banner (not constrained-re-sim claim) until Run; clear arming on successful sim.
- [x] Docs: USER_GUIDE, ARCHITECTURE keys, ASSUMPTIONS, roadmap/status.
- [x] Tests: `tests/test_entry_window_sw4.py` (no engine).

**Out of scope.** Grid/WFA inherit (SW5); setup library persistence (SW6); SW2b cutoff audit; auto-Promote best bucket.

**Regression safety.** Analytics/UI additive; no `simulate_trades` changes; Focus overlays untouched by Promote/Clear armed; default-off Admit widgets until Promote or manual toggle.

---

### SW5 — Grid + Validation / WFA / sensitivity inheritance

Keyword-only passthrough on `run_sl_tp_grid`, walk-forward, and **`overfitting._SIMULATION_KWARGS`**. UI warning: not a swept axis. No per-fold segment reselection.

---

### SW6 — Setup persistence, Report/Bundles, Assistant honesty

Additive setup key + normalize/default (OTF pattern). Export provenance. Assistant must not claim edge from Focus alone.

---

### SW7 — Hardening + release evidence

Parity audit; goldens green; `docs/SESSION_ENTRY_WINDOW_RELEASE_EVIDENCE.md`; honesty review.

---

## 9. Deferred follow-ups

| Item | Why deferred |
|---|---|
| Time as Grid/WFA axis | Multiple-testing risk |
| Overnight clock wrap | v1 complexity |
| Signal-time filter in `generate_signals` | Sim admission sufficient for v1 |
| Holiday calendars | Data problem |
| Auto-Promote best bucket | Pre-declaration discipline |

---

## 10. Risk register

| Risk | Mitigation |
|---|---|
| Focus treated as deployable edge | Banners; Promote→re-sim; Assistant honesty |
| Thin buckets over-trusted | provenance `sample_warning` + Promote confirm |
| Skip UI honesty drift | SW2b / SW3 labeling; do not audit cutoff blind |
| Legacy golden break | Default-off + trades identity tests |
| TZ confusion | C5; segments always session TZ |
| Sensitivity silently drops window | SW5 `_SIMULATION_KWARGS` |
| session_state sprawl | ARCHITECTURE per PR |

---

## 11. Success criteria

1. Discover strong open / weak all-day (existing + Focus).
2. One-click Focus full metric suite (**SW1**).
3. Promote → constrained Backtest (**SW3–SW4**).
4. Grid + Validation under same window (**SW5**).
5. Save/export with honest labels (**SW6–SW7**).
6. Legacy defaults golden-identical throughout.

---

## 12. Per-PR acceptance checklist

- [ ] Deterministic unit tests for new behavior.
- [ ] Legacy golden preserved.
- [ ] Enabled-window golden when engine path added.
- [ ] Docs same PR (ASSUMPTIONS, ARCHITECTURE, USER_GUIDE, METRICS as needed).
- [ ] Focus vs Admit honesty (incl. C8 when Focus equity shown).
- [ ] C1–C9 respected for any contract touched.
- [ ] CI green; Regression safety paragraph in PR body.
- [ ] Status tracker updated.

---

## 13. Status tracker

| Milestone | Status | PR |
|---|---|---|
| SW0 Plan + golden confirmation | Merged | [#286](https://github.com/AccumuLatata/ThesisTester/pull/286) |
| SW1 Post-hoc Focus | Merged | [#292](https://github.com/AccumuLatata/ThesisTester/pull/292) |
| SW2 Engine admission + C7 + golden | Merged | [#293](https://github.com/AccumuLatata/ThesisTester/pull/293) |
| SW2b Cutoff skip audit + honesty | Optional / not started | — |
| SW3 API + Backtest Admit UI | Merged | [#294](https://github.com/AccumuLatata/ThesisTester/pull/294) |
| SW4 Promote handoff UX | Open | [#295](https://github.com/AccumuLatata/ThesisTester/pull/295) |
| SW5 Grid + Validation inheritance | Not started | — |
| SW6 Persistence + export + assistant | Not started | — |
| SW7 Hardening + release evidence | Not started | — |

---

## 14. Appendix — industry practice (design justification)

- Trade the session you tested; all-day aggregates can hide session edge.
- Pre-declare filters; validate forward; treat post-hoc discovery as exploration only.
- SOTA landscape §9: time-of-day breakdowns are essential for NQ/ES confluence research — this plan turns that diagnostic into a constrained workflow without becoming a strategy factory.
