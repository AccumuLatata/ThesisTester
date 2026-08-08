# Research Assistant UX Refocus — Release Evidence and Closeout

**Project:** ThesisTester  
**Feature:** Research Assistant page layout / surface prominence (discuss-first)  
**Document type:** RUX-5 release evidence / engineering sign-off  
**Last updated:** 2026-08-08  
**Baseline commit (main at recording):** `a3e4789` (merge of RUX-4 / #304)  
**Related:** [`RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md`](RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md),
[`ARCHITECTURE.md`](ARCHITECTURE.md), [`USER_GUIDE.md`](USER_GUIDE.md),
[`ENGINEERING_PROPOSAL.md`](ENGINEERING_PROPOSAL.md) §4

## 1. Release framing (honest)

| Layer | Status | Notes |
|---|---|---|
| Engineering delivery (RUX-0…RUX-4) | **Complete** | Contract → foundation → layout inversion → chat_input → Help re-anchor |
| Engineering sign-off (RUX-5) | **Complete** | Rendered-structure proof + full suite recorded below |
| Channel / evidence / corpus logic | **Unchanged** | RQ/HC/VA/CAI freezes hold; RUX is presentation-only |
| Product research pipeline | **Unchanged** | Classic `Data → … → Backtest` remains primary |

**Verdict for repository state:** Research Assistant is **discuss-first by
default**. Discuss runs and Help are peer modes; Draft thesis and Advanced
validate→confirm→run remain available but demoted. This is a **layout /
prominence** release, not a new research capability.

## 2. Milestone delivery record

| ID | Title | Status |
|---|---|---|
| RUX-0 | Contract + AppTest rendered-structure baseline | Merged [#300](https://github.com/AccumuLatata/ThesisTester/pull/300) |
| RUX-1 | UX foundation (`ux.py`, `[assistant.ux]`, nav constants) | Merged [#301](https://github.com/AccumuLatata/ThesisTester/pull/301) |
| RUX-2 | Layout inversion: Discuss-first modes | Merged [#302](https://github.com/AccumuLatata/ThesisTester/pull/302) |
| RUX-3 | Mode-scoped page-level `st.chat_input` | Merged [#303](https://github.com/AccumuLatata/ThesisTester/pull/303) |
| RUX-4 | Help remediation + USER_GUIDE / Q-H13 re-anchor | Merged [#304](https://github.com/AccumuLatata/ThesisTester/pull/304) |
| RUX-5 | Evidence + closeout | [#305](https://github.com/AccumuLatata/ThesisTester/pull/305) / this document |

## 3. Before / after layout

### 3.1 Before (RUX-0 measured prominence)

| Rank | Surface | Placement |
|---|---|---|
| 1 | Assistant chat (draft) | Always open; owned page-level `st.chat_input` |
| 2 | Help / how it works | Collapsed expander |
| 3 | Advanced draft → validate → confirm → run | Collapsed Advanced |
| 4 | Discuss results | Nested: Advanced → Linked run → completed branch |
| 5 | Debug JSON / audit | Collapsed Debug |

### 3.2 After (RUX-2…RUX-3 target)

| Rank | Surface | Placement |
|---|---|---|
| 1 | **Discuss runs** (default) | Mode body: run picker + Discuss results thread + mode-scoped chat_input + Explain / Open / Restore + voice |
| 2 | **Help** | Peer mode: Help thread + mode-scoped chat_input + voice |
| 3 | **Draft thesis** | Demoted mode: Assistant chat + mode-scoped chat_input |
| 4 | Advanced validate → confirm → run / Linked runs / compare | Still collapsed Advanced (LLM explain stays here) |
| 5 | Debug JSON / audit | Still collapsed Debug |

Navigation is a mode selector only — channel histories stay isolated.

## 4. §5.3 acceptance → rendered proof

Every RUX-2 acceptance bullet is proven by `tests/test_assistant_page_render.py`
(AppTest against a temporary store). Manual UI walkthrough is encoded in these
assertions (same observables Streamlit would show).

| §5.3 acceptance | Proof |
|---|---|
| Default render with ≥1 eligible run: Discuss mode active; thread + input visible without opening any expander | `test_default_prominence_is_discuss_with_collapsed_secondary_surfaces` — mode `discuss`, picker = seeded run, Advanced/Debug collapsed, exactly one chat_input with Discuss placeholder |
| Default render with no eligible run: empty state names `Record and discuss this run` | `test_default_discuss_empty_state_names_record_and_discuss` |
| Help reachable in one click; Draft in one click; Advanced/Debug collapsed by default | Mode session-key switch in chat_input / caption tests; Advanced/Debug `expanded is False` in default prominence test |
| Confirm / Run reachable via Advanced in every mode | Default prominence asserts Plan review / Specifications / Linked research runs under Advanced; Advanced rendered after every mode body |
| Classic `Discuss this run` / Record-and-discuss land on the run's Discuss thread | `test_classic_results_qa_deep_link_preselects_discuss_and_force_opens` — mode Discuss + picker = focused run **and** Advanced/run expander force-open keys |
| Orphan / ineligible deep-link honesty | `test_classic_results_qa_orphan_deep_link_still_force_opens_expanders`, `test_orphan_deep_link_with_other_runs_warns_instead_of_silent_swap` |
| Channel isolation preserved | `test_results_qa_history_never_renders_in_the_draft_or_help_threads` |
| Zero core-module / fixtures drift (series invariant) | Diff review per PR scope tables; `tests/test_golden_master.py` unmodified and green |

### 4.1 Additional RUX-3 / RUX-4 proof (post-layout)

| Concern | Proof |
|---|---|
| Exactly one page-level chat_input in every mode | `test_page_renders_exactly_one_chat_input_in_every_mode` |
| Discuss/Help/Draft submit routing; no `choices` on Discuss/Help | `test_discuss_chat_input_routes_to_handle_results_turn`, `test_help_chat_input_routes_to_handle_help_turn_without_choices`, `test_draft_chat_input_routes_to_handle_chat_turn` |
| Disabled chat_input when channel cannot accept input | `test_disabled_discuss_chat_input_does_not_call_handle_results_turn` (+ Help disabled guidance) |
| Help remediation names Discuss runs mode | `tests/test_assistant_product_help.py`, `test_rq5_help_vs_results_redirect_for_performance_question` |
| Q-H13 discuss-a-run corpus retrieval | `tests/test_assistant_help_coverage.py` (Q-H13 in HC §5 bank) |

## 5. Deep-link verification

Contract: `classic_focus_channel == "results_qa"` is a **superset** of legacy
behavior.

1. Consume `{classic_focus_run_id, classic_focus_channel}` atomically.
2. Preselect `assistant_ux_mode=discuss` + `assistant_discuss_run_picker=run_id`.
3. Keep sticky `assistant_results_qa_deep_link` + `force_results_qa_expanders_open`
   (Advanced + Linked-run expander keys).
4. When the focused run is missing/ineligible while other recorded runs exist,
   warn — do not silently imply the wrong thread.

Evidence: AppTest deep-link tests above; classic bridge tests in
`tests/test_classic_nav.py` / `tests/test_classic_context.py` remain green
without RUX assertion edits to CAI focus-key shape.

## 6. Manual walkthrough matrix (encoded in AppTest)

| Walkthrough step | AppTest / suite stand-in |
|---|---|
| Open Research Assistant with thesis + completed run → default Discuss | `test_default_prominence_is_discuss_with_collapsed_secondary_surfaces` |
| Switch to Help mode | Help mode render + chat_input placeholder / routing tests |
| Switch to Draft mode | Draft captions + chat_input routing |
| Open Advanced → Plan review / Confirm / Run still present | Advanced subheader set in default prominence test |
| Classic Discuss this run deep-link | Deep-link preselect + force-open tests |
| RQ-off / Help-off empty guidance | `test_discuss_mode_reports_disabled_results_qa_not_missing_runs`, `test_help_mode_shows_disabled_guidance_when_product_help_off` |

Screenshots/recordings are optional for this series: the binding regression net
is the rendered-structure baseline (§6.1 of the plan), not pixel artifacts.

## 7. Verification suite results (recorded)

Recorded on 2026-08-08 against `thesistester==0.2.0`, Python 3.12.3,
pandas 3.0.5, git baseline `a3e4789` plus this RUX-5 closeout branch.

### 7.1 Rendered-structure + UX helpers + Help coverage + UI copy + golden

```bash
python3 -m pytest -q \
  tests/test_assistant_page_render.py \
  tests/test_assistant_ux.py \
  tests/test_assistant_help_coverage.py \
  tests/test_ui_copy_guards.py \
  tests/test_golden_master.py
```

**Result:** `88 passed in 6.33s`

### 7.2 Final gate

```bash
python3 -m pytest -q
```

**Result:** `2559 passed in 99.72s`

### 7.3 Lint

```bash
python3 -m ruff check pages/14_Research_Assistant.py \
  thesistester/assistant/ux.py \
  thesistester/assistant/workspace.py \
  thesistester/assistant/product_help.py
```

**Result:** All checks passed.

## 8. Formal engineering sign-off checklist

| Criterion | Result | Evidence |
|---|---|---|
| Discuss-first default (§0.2 / §5.3) | ✅ | §3–§4 AppTest inventory |
| Deep-link superset (mode + run + force-open) | ✅ | §5 |
| Channel isolation | ✅ | `test_results_qa_history_never_renders_in_the_draft_or_help_threads` |
| One page-level chat_input; never nested | ✅ | RUX-3 AppTest + source guards |
| Help nav / remediation re-anchored | ✅ | RUX-4 USER_GUIDE + Q-H13 + product_help assertions |
| Golden master unmodified & green | ✅ | §7.1 |
| Full suite green | ✅ | §7.2 — **2559 passed** |
| Docs reflect released layout | ✅ | Plan Complete; ARCHITECTURE; USER_GUIDE; RQ UI-attach; this evidence doc |
| Presentation-only (no engine / API / core assistant logic reopen) | ✅ | Per-PR scope tables; series file blocklist |

**Engineering sign-off:** Approved — Research Assistant UX refocus (RUX-0…RUX-5)
is complete.  
**Do not reopen RUX for layout changes;** amend
`docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` (and this evidence doc) instead.
