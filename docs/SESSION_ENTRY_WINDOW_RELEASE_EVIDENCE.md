# Session Entry Window — Release Evidence and Sign-off

**Project:** ThesisTester  
**Feature:** Session entry-window research loop (Focus → Admit → Grid/WFA → export)  
**Document type:** SW7 hardening / release evidence checklist  
**Last updated:** 2026-08-07  
**Baseline commit (main at recording):** `2181e53` (merge of SW6 / #297)  
**Related:** [`SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md`](SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md), [`ASSUMPTIONS_AND_LIMITATIONS.md`](ASSUMPTIONS_AND_LIMITATIONS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ENGINEERING_PROPOSAL.md`](ENGINEERING_PROPOSAL.md) §4

## 1. Release framing (honest)

| Layer | Status | Notes |
|---|---|---|
| Engineering delivery (SW0–SW6) | **Complete** | Focus, engine Admit, API/UI, Promote, Grid/WFA inherit, setup/export/assistant |
| Engineering sign-off (SW7) | **Complete** | Verification suites recorded below; C2 Focus entry-time honesty hardened |
| Real-dataset OOS statistical release | **Open / not executed in-repo** | No real user dataset in the repository; do not fabricate edge |
| Product default | **Disabled** | `entry_window` remains opt-in; Focus is post-hoc only |
| Optional SW2b cutoff skip audit | **Not shipped** | `no_new_entries_after` rejects stay silent; documented in ASSUMPTIONS |

**Verdict for repository state:** Session entry window is **research-ready and
engineering-signed**, disabled by default. Focus alone is **not** deployable-edge
evidence. Constrained Admit / Grid / WFA results are **diagnostics**, not a
statistical release approval from in-repo fixtures.

## 2. Milestone delivery record

| Milestone | Title | Status |
|---|---|---|
| SW0 | Plan + legacy golden gate | Merged [#286](https://github.com/AccumuLatata/ThesisTester/pull/286) |
| SW1 | Post-hoc Focus | Merged [#292](https://github.com/AccumuLatata/ThesisTester/pull/292) |
| SW2 | Engine admission + C7 + enabled golden | Merged [#293](https://github.com/AccumuLatata/ThesisTester/pull/293) |
| SW2b | Cutoff skip audit + honesty | Optional / not started |
| SW3 | API + Backtest Admit UI | Merged [#294](https://github.com/AccumuLatata/ThesisTester/pull/294) |
| SW4 | Promote Focus→Admit handoff | Merged [#295](https://github.com/AccumuLatata/ThesisTester/pull/295) |
| SW5 | Grid + Validation/WFA/sensitivity inherit | Merged [#296](https://github.com/AccumuLatata/ThesisTester/pull/296) |
| SW6 | Setup persistence + Report/Bundles + Assistant | Merged [#297](https://github.com/AccumuLatata/ThesisTester/pull/297) |
| SW7 | Hardening + release evidence | [#298](https://github.com/AccumuLatata/ThesisTester/pull/298) / this document |

## 3. Formal engineering sign-off checklist

Recorded on 2026-08-07 against `thesistester==0.2.0`, Python 3.12.3, pandas 3.0.5,
git baseline `2181e53` plus SW7 hardening commits on this branch.

| Criterion | Result | Evidence |
|---|---|---|
| C1 shared RTH vocabulary | ✅ | `entry_window_policy.RTH_SEGMENTS` / `RTH_SEGMENT_LABELS`; `test_c1_shared_rth_vocabulary` |
| C2 entry-bar membership (Focus + Admit) | ✅ | Engine entry-bar path; Focus UI forces `entry_timestamp`; `test_c2_focus_membership_uses_entry_not_exit_timestamps` |
| C3 multi-segment OR / empty invalid | ✅ | Normalize + filter tests in `test_session_focus` / admission |
| C4 half-open clock / no overnight wrap | ✅ | `test_normalize_clock_range_no_wrap`, `test_filter_clock_range_half_open` |
| C5 TZ law | ✅ | RTH via `entry_window_exchange_tz`; Promote writes TZ; SW3/SW5 C5 tests |
| C6 OTF → window → exposure order | ✅ | `test_window_rejects_never_block_exposure` |
| C7 Focus ≡ Admit under allow_all / cooldown 0 | ✅ | Admission + `test_entry_window_golden` C7 |
| C8 Focus equity subset-replay + banner | ✅ | `summarize_focused_trades` provenance; UI banners |
| C9 window AND cutoff; at-cutoff admits | ✅ | `test_c9_entry_window_and_cutoff_both_apply` |
| Legacy disabled-path golden green | ✅ | `tests/test_golden_master.py` (§4.3) |
| Enabled-window golden green | ✅ | `tests/test_entry_window_golden.py` (§4.3) |
| OTF golden isolation green | ✅ | `tests/test_otf_golden.py` (§4.3) |
| Focus ≠ Admit honesty surfaces | ✅ | UI banners/badges; Report metadata; bundles; `focus_post_hoc` assistant caveat |
| Default-off preserves legacy trades | ✅ | Engine/API/Grid/Setup disabled defaults; identity tests across SW2–SW6 |
| Full CI suite green (local final gate) | ✅ | `pytest -q tests/` → **2523 passed** (§4.4) |
| Required documentation reflects released behavior | ✅ | Plan, ARCHITECTURE, ASSUMPTIONS, USER_GUIDE, ENGINEERING_ROADMAP, this doc |
| No automatic production selection / no durable-edge claim | ✅ | Defaults disabled; Focus honesty; this document forbids fabricating OOS proof |

**Engineering sign-off:** Approved for research use under default-off policy.  
**Statistical / business release:** Not approved from repository fixtures.

## 4. Verification suite results (recorded)

### 4.1 Focus / policy / admission / C7 / C9

```bash
python3 -m pytest -q \
  tests/test_session_focus.py \
  tests/test_entry_window_admission.py
```

**Result:** `30 passed in 0.42s`

### 4.2 API / Promote / Grid-WFA inherit / Setup-export-assistant

```bash
python3 -m pytest -q \
  tests/test_entry_window_sw3.py \
  tests/test_entry_window_sw4.py \
  tests/test_entry_window_sw5.py \
  tests/test_entry_window_sw6.py
```

**Result:** `40 passed in 0.52s`

### 4.3 Golden gates (legacy + enabled-window + OTF isolation)

```bash
python3 -m pytest -q \
  tests/test_golden_master.py \
  tests/test_otf_golden.py \
  tests/test_entry_window_golden.py
```

**Result:** `29 passed in 0.96s`

### 4.4 Final gate

```bash
python3 -m pytest -q tests/
```

**Result:** `2523 passed in 95.41s`

## 5. Honesty review (Focus ≠ Admit)

| Surface | Focus (post-hoc) | Admit (re-sim) |
|---|---|---|
| Time Analysis | Focus badge + honesty + C8 equity caveat; membership uses **entry** timestamps (C2) | Promote arms only; no auto-run |
| Backtest | Overlay KPIs labeled post-hoc | Admit toggle / armed vs applied badges; skip split |
| Grid / Validation | Never auto-inherited | Fixed Admit constraint warning |
| Report / Bundles | Provenance + `is_not_admit` / honesty notes | Admit window + promote provenance exported |
| Assistant | Mandatory `focus_post_hoc` caveat | Prefer Admit evidence for constrained claims |
| Setup library | N/A (saved window is Admit config) | Persisted; does **not** auto-run Backtest |

### Explicit non-claims

- Focus KPIs are a post-hoc trade subset — not constrained path evidence and not
  proof of deployable edge.
- Enabled-window goldens prove **correctness / drift**, not statistical edge.
- Grid/WFA under a fixed window remain **diagnostics**; the window is not a
  swept axis and is not reselected per fold.
- Absence of real-data OOS rows means statistical release remains **open**.
- SW2b cutoff skip audit is **not** part of this release.

## 6. Operational release posture

Until real-dataset OOS evidence exists outside this repository:

1. Ship `entry_window` **disabled by default**.
2. Treat Focus as exploratory; require Promote → Admit re-sim before treating a
   window as a constrained strategy constraint.
3. Keep Focus/Admit labels distinct in UI, exports, and assistant answers.
4. Do not auto-wire setup-library `entry_window` into Backtest Run.
5. Keep SW2b optional; do not imply cutoff rejects are audited skips today.

When real-data OOS work is completed, update this document with filled evidence
blocks and only then reconsider the statistical release line in §1.
