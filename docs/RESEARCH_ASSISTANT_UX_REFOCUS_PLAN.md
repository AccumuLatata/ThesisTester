# Research Assistant UX Refocus — Implementation Contract (RUX-series)

**Document type:** Implementation contract (RUX-series) — **single source of truth for Research Assistant page layout/prominence**
**Status:** 🟡 In progress — RUX-0 implemented (contract + rendered-structure
baseline); RUX-1 implemented ([#301](https://github.com/AccumuLatata/ThesisTester/pull/301));
RUX-2 implemented ([#302](https://github.com/AccumuLatata/ThesisTester/pull/302));
RUX-3 implemented ([#303](https://github.com/AccumuLatata/ThesisTester/pull/303));
RUX-4…RUX-5 specified, not implemented
**Date:** 2026-08-07
**Owner surface:** `pages/14_Research_Assistant.py` + presentation-only helpers in
`thesistester/assistant/` (`ux.py` new, `workspace.py`, `llm.py` settings loader)
**Depends on:** RQ complete (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`),
HC complete (`docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md`), CAI complete
(`docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md`), VA complete
(`docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md`), `docs/ENGINEERING_PROPOSAL.md`
§4 / §4.1 / §4.2
**Series prefix:** `RUX` (Research-assistant UX)

This is the **only** binding contract for Research Assistant page layout and
surface prominence. It is a **presentation-layer series**: it must not change the
engine, the public `thesistester.api` façade, the assistant orchestrator /
repository / registry / handlers, the classic pipeline, or any research semantics.
Every RUX PR must stay inside its scope table. If a change is not listed under
**In scope**, it belongs in a later PR or is rejected.

### Related docs (completed contracts — not competing open plans)

| Doc | Role vs this contract |
|---|---|
| `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` (RQ) | ✅ Complete. Owns Discuss/Help **channel logic, grounding, evidence, and trust boundaries**. RUX owns **where those surfaces render**. RUX amends only the two RQ §1 freezes named in §1.2 of this doc, in the same PR that moves the widget. |
| `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` (HC) | ✅ Complete. Owns Help **corpus/allowlist**. RUX may edit allowlisted `USER_GUIDE` section **bodies** for navigation accuracy; it must not add/remove/rename allowlisted sections. |
| `docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md` (CAI) | ✅ Complete. Owns the classic↔assistant bridge and focus keys. RUX keeps `classic_focus_run_id` / `classic_focus_channel` semantics byte-identical and only changes what the Assistant page *does* on consume. |
| `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (VA) | ✅ Complete. Voice is transport over Discuss/Help. RUX **relocates** the voice blocks with their channels; widget keys and gating stay identical. |
| `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` (C2) | ✅ Complete thesis-draft/explain loop. RUX demotes the draft surface's prominence; the loop itself is untouched. |
| `docs/ENGINEERING_ROADMAP.md` | Index / status tracker — points here for RUX work |

---

## 0. Product intent and evidence

### 0.1 Observed problem

The Research Assistant page is one Streamlit page hosting three isolated AI
channels plus an optional second research pipeline. Measured from source
(`pages/14_Research_Assistant.py`, ~2412 lines as of RUX-0) and verified by
rendering the page under `streamlit.testing.v1.AppTest`, today's prominence
order is:

| Rank in viewport | Surface | Current placement |
|---|---|---|
| 1 | **Assistant chat** (thesis drafting) | Always open; owns the page-level `st.chat_input` |
| 2 | Help / how it works | Collapsed expander (`expanded=False`) |
| 3 | Optional second pipeline (draft → validate → confirm → run), linked runs, compare/portfolio | Collapsed `Advanced: draft, runs & compare` |
| 4 | **Discuss results** | Nested three levels deep: Advanced → Linked run expander → `if run.status == "completed"` branch |
| 5 | Raw JSON / conversation audit | Collapsed `Debug: raw JSON & conversation audit` |

Rendered evidence (AppTest, seeded thesis, no runs): open subheaders are
`Assistant chat`, `Plan review`, `Specifications`, `Linked research runs`; the
only unnested chat widget is the draft `st.chat_input`; Help is one of ~15
expanders in a no-run AppTest render (more nested expanders appear once runs
exist).

The two jobs the page is actually valued for — **discussing completed runs** and
**answering questions about the application** — are respectively the deepest and
the second-most-hidden surfaces. Discuss is currently reachable in normal use
only because `classic_nav.discuss_run` force-opens two expanders
(`force_results_qa_expanders_open`). That is a working deep-link, but it means the
primary job is a side door into a drafting workstation.

### 0.2 Product decision

Invert prominence. Do **not** remove capability.

```text
Research Assistant page purpose (target):
  1. Discuss completed runs        → primary, default surface
  2. Answer app/how-it-works asks  → one click, peer to Discuss
  3. Draft theses (optional)       → demoted, still fully functional
  4. Validate/confirm/run/compare  → unchanged, collapsed Advanced
  5. Raw JSON / audit              → unchanged, collapsed Debug
```

Classic pages (`Data → Levels → Setup Builder → Signals → Backtest → …`) remain
the primary research pipeline. RUX reinforces that; it does not touch it.

---

## 1. Frozen design decisions (do not re-litigate in RUX PRs)

### 1.1 Hard invariants (violating any of these fails review)

| Freeze | Rule |
|---|---|
| Presentation-only | RUX changes layout, ordering, containers, captions, and presentation session keys. No RUX PR may edit `thesistester/assistant/{orchestrator,repository,registry,handlers,tools,thesis_compiler,explainer,results_qa,help_corpus,comparison,page_summaries}.py` logic, `thesistester/api.py`, `thesistester/research_*`, engine modules, or `pages/1..13`. |
| Channel separation | Thesis draft / `results_qa` / `product_help` stay separate channels with separate orchestrator entrypoints and separate history filters. A mode selector is **navigation**, never prompt merging. One rendered mode = one channel. |
| Draft history isolation | `is_draft_channel_message` / `chat_message_display_role` filtering stays exactly as-is. Draft hydration keeps ignoring `channel`-tagged messages. |
| Evidence path | Discuss keeps `handle_results_turn` + hash-verified `EvidencePacket`; Help keeps `handle_help_turn` + allowlisted corpus. No new numeric source, no new tool call, no `PIPELINE.*` from either. |
| Second pipeline intact | `Advanced: draft, runs & compare` keeps its internals byte-for-byte except for the block explicitly moved in RUX-2 (§5.3). Validate → Confirm → Run stays confirmation- and schema-gated in the same order. |
| Classic bridge | `classic_focus_run_id` (string) + `classic_focus_channel` (`"results_qa"` only) semantics, `consume_classic_focus`, `apply_consumed_classic_focus`, `align_assistant_thesis_for_discuss`, and `force_results_qa_expanders_open` all keep working. RUX may **add** mode/run preselection on consume; it may not remove the existing expander force-open (belt-and-braces for legacy deep-links). |
| Discuss eligibility | The predicate stays exactly `run.status == "completed" and isinstance(run.provenance, dict)` plus `load_results_qa_settings().enabled`. Voice keeps requiring `require_run_bundle_hash(run.provenance)`. No widening. |
| Voice gating | Voice UI stays behind `resolve_voice_settings().enabled`, keeps `thesis_has_running_run` pausing, and keeps identical widget keys (`voice-results-audio-{run_id}`, `voice-help-audio`, `voice-realtime-start-{run_id}`) and identical copy strings (`Voice discuss (push-to-talk)`, `Voice help (push-to-talk)`, `Voice discuss (realtime)`). |
| Surface names | The user-facing names `Assistant chat`, `Discuss results`, `Help / how it works`, `Advanced: draft, runs & compare`, `Debug: raw JSON & conversation audit`, `Linked research runs`, `Plan review`, `Specifications` are **not renamed** by this series. Only placement and the navigation phrases in §1.3 change. This keeps the Help corpus, `USER_GUIDE` section titles, and eval banks stable. |
| Session-key discipline | New keys are additive, listed in `ASSISTANT_SESSION_KEYS`, cleared appropriately on thesis switch, and documented in `docs/ARCHITECTURE.md` in the same PR (`ENGINEERING_PROPOSAL.md` §4 rule 6). |
| No engine/golden impact | No RUX PR may modify anything under `tests/fixtures/golden/` or engine math. `tests/test_golden_master.py` must stay green and unmodified. |
| One page | No new Streamlit page file, no `st.navigation` rewrite, no `st.page_link` strip (`test_ui_copy_guards.py` guard stays). |

### 1.2 RQ freezes this series amends (only these, only where stated)

`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` §1 contains two placement
freezes written when nested chat widgets were unavailable:

| RQ §1 row | Current text (abridged) | RUX amendment | Amended in |
|---|---|---|---|
| `UI attach (results)` | "Completed-run expander on Research Assistant; do not replace thesis-draft `st.chat_input`. v1 input widget: keyed `st.text_input` + send button" | Discuss renders as a top-level mode surface, not inside the run expander. Widget stays keyed `st.text_input` + send in RUX-2. RUX-3 may promote the **page-level** (non-nested) `st.chat_input` to the active mode. | RUX-2 (placement), RUX-3 (widget) |
| `UI attach (help)` | "Separate Help panel / tab on Research Assistant (not inside a run expander); same `st.text_input` + send button pattern" | Satisfied and strengthened: Help becomes a peer mode instead of a collapsed expander. | RUX-2 |

Both amendments are edits to the RQ document performed **in the same PR** that
changes the behavior, per the RQ amendment rule. No other RQ freeze is touched —
channel separation, grounding, remediation, message tags, history trim, and
classic-focus key shape all stay as frozen.

### 1.3 Navigation-phrase migration (single source of truth)

User-facing `Advanced → …` / Help-pointer strings live in page captions, Help
system/remediation text, and allowlisted docs. **Exact inventory for RUX-1
extraction** (byte-identical values; line numbers as of RUX-0):

| Constant | Current fragment (verbatim) | Call sites today |
|---|---|---|
| `DISCUSS_NAV_HINT` | `Advanced → Linked runs → Discuss results` | page L553; composed into `product_help` remediation `followups` L208 (`Open {hint} for a completed run.`) |
| `DISCUSS_NAV_SHORT` | `Advanced → Linked runs` | page L592; `product_help` system prompt L54 + `_REMEDIATION_SUMMARY` L149 |
| `HELP_NAV_HINT` | `Help / how it works below` | page L554 (`use {hint}.` inside the draft-chat caption) |
| `ADVANCED_PLAN_NAV_HINT` | `Advanced → Plan review` | page L1497 |
| `ADVANCED_COMPARE_NAV_HINT` | `Advanced → Compare completed runs` | page L2249, L2257 (two flashes, one fragment) |
| `ADVANCED_PORTFOLIO_NAV_HINT` | `Advanced → Portfolio analysis` | page L2338 |

**Not extracted in RUX-1** (left as-is until RUX-2 docs pass):

- Page **comment** L447 (`Advanced → Linked-run` — not user-facing)
- `docs/USER_GUIDE.md` / `ARCHITECTURE.md` / `ENGINEERING.md` /
  `RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` navigation sentences (updated in
  RUX-2 when the layout flips; USER_GUIDE bodies are Help corpus evidence)
- `tests/test_assistant_workspace.py` source guard (rewritten in RUX-2)

**Freeze:** RUX-1 lands the six constants above in `thesistester/assistant/ux.py`
and substitutes **only** the page + `product_help.py` call sites listed in the
table. Values stay byte-identical (pure refactor). RUX-2 flips the Discuss/Help
constant values and updates docs/tests in the same PR. After RUX-1, no RUX PR
may hand-write a navigation phrase at a page or `product_help` call site —
import the constant.

`product_help.py` is otherwise off-limits to RUX: only the three Discuss-nav
strings become imports; prompt structure, grounding, and remediation logic are
untouched.

---

## 2. Target layout

```text
Research Assistant                                     (title + caption: discuss-first)
┌ sidebar ───────────────────────────────────────────┐
│ Theses: New thesis name / Create / Select          │  unchanged
│ Voice controls                                     │  unchanged
└────────────────────────────────────────────────────┘
Thesis name · Revision N · lifecycle                    unchanged
Flash / classic-focus / active-handoff banners          unchanged
▸ Manage thesis                            (collapsed)  unchanged

What do you want to do?   [ Discuss runs | Help | Draft thesis ]     ← new, segmented_control
                          default from [assistant.ux].default_mode = "discuss"

── mode = Discuss runs (default) ────────────────────────────────────
   Run: [ Run 1a2b3c4d · spec v3 · classic · 2026-08-06 ▾ ]          ← new picker
   Spec v3 · origin `7_Backtest` · bundle `9f2c…`                    reused provenance caption
   ┌ thread (st.chat_message bubbles, results_qa + run_id filter) ┐  MOVED, filters identical
   │ …                                                            │
   └──────────────────────────────────────────────────────────────┘
   [ Ask about this run                          ] [Send results question]   MOVED, keys identical
   Voice discuss (push-to-talk) / (realtime)                        MOVED, keys identical
   Secondary: [Explain run] [Open exact run in Backtest] [Restore]  MOVED from Linked run
   empty state → "No completed thesis-recorded run yet…" when no recorded runs;
                  when runs exist but `[assistant.results_qa] enabled = false`,
                  keep picker + Explain/Open/Restore and say Discuss Q&A is
                  unavailable (do not hide secondary actions).

── mode = Help ──────────────────────────────────────────────────────
   Help / how it works  (same caption, thread, input, send, voice help)  PROMOTED from expander
   when `[assistant.product_help] enabled = false` → disabled guidance (not blank)

── mode = Draft thesis (optional) ───────────────────────────────────
   Assistant chat  (same caption, thread, page-level chat_input)         DEMOTED from hero

▸ Advanced: draft, runs & compare              (collapsed, all modes)
    How to start · Structured controls · Reuse saved setup
    Draft research plan / Validate executable RunSpec
    Plan review → Confirm validated RunSpec
    Specifications → Run confirmed research
    Linked research runs → Cancel · Page summaries (JSON) · Propose classic
                           page change · Generate evidence-only AI explanation
                           (LLM explain stays here) · report/artifact ·
                           identity caption · Debug: provenance
                           (Discuss / voice-discuss / Explain / Open exact /
                            Restore moved out — see §5.3 movement map)
    Compare completed runs · Portfolio analysis · Saved comparisons
▸ Debug: raw JSON & conversation audit         (collapsed)             unchanged
```

Rationale for keeping Advanced visible in **every** mode rather than making it a
fourth mode: the deep-link force-open path (`ASSISTANT_ADVANCED_EXPANDER_KEY`,
`linked_run_expander_key`) keeps working untouched, and no user can reach a state
where Confirm/Run is unreachable. §2 is descriptive; the §5.3 movement map is
binding when they differ.

---

## 3. Non-goals (explicitly out of scope for the whole series)

- No change to backtest/levels/signals/validation math, or to golden fixtures.
- No change to `AssistantOrchestrator`, repository schema, registry, handlers, tools, or `thesistester.api`.
- No removal or disabling of the thesis draft → validate → confirm → run pipeline.
- No merging of channels, no new LLM prompt, no new capability, no new tool.
- No new persisted artifacts and no store schema bump.
- No changes to classic pages, classic recording policy, or bundle/identity logic.
- No renaming of user-facing surface names (§1.1) or `USER_GUIDE` H2 titles.
- No dependency changes. Streamlit floor stays `>=1.56`; RUX uses only widgets available there (`segmented_control` ≥1.40, keyed `expander` ≥1.55, page-level `chat_input`).
- No multi-user, no auth, no telemetry.

---

## 4. New surface area (complete list)

### 4.1 New module `thesistester/assistant/ux.py` (presentation helpers only)

Pure functions and constants — no I/O, no LLM, no orchestrator calls:

| Symbol | Purpose |
|---|---|
| `ASSISTANT_MODE_DISCUSS / _HELP / _DRAFT` | Mode ids (`"discuss"`, `"help"`, `"draft"`) |
| `ASSISTANT_MODES` | Ordered tuple for the selector |
| `ASSISTANT_MODE_LABELS` | Mode id → user label (`"Discuss runs"`, `"Help"`, `"Draft thesis"`) |
| `ASSISTANT_MODE_SESSION_KEY = "assistant_ux_mode"` | Selector widget/session key |
| `DISCUSS_RUN_PICKER_KEY = "assistant_discuss_run_picker"` | Run selectbox widget key |
| `DISCUSS_NAV_HINT`, `DISCUSS_NAV_SHORT`, `HELP_NAV_HINT`, `ADVANCED_PLAN_NAV_HINT`, `ADVANCED_COMPARE_NAV_HINT`, `ADVANCED_PORTFOLIO_NAV_HINT` | §1.3 navigation fragments (single source of truth) |
| `resolve_mode(session_state, *, default_mode, requested=None)` | Coerce/validate mode; unknown value → default |
| `recorded_completed_runs(runs)` | Completed + provenance dict (RQ-independent); picker + Explain/Open/Restore |
| `discussable_runs(runs, *, results_qa_enabled)` | Q&A eligibility: recorded ∩ results_qa enabled (§1.1) |
| `default_discuss_run_id(runs, *, focused_run_id)` | Focused run if eligible, else newest eligible, else `None` |
| `run_picker_label(run)` | Deterministic label reusing existing id/spec/kind formatting |

### 4.2 New session keys (additive)

| Key | Type | Producer | Cleared on |
|---|---|---|---|
| `assistant_ux_mode` | `str` (mode id) | Mode selector widget + deep-link preselect | thesis switch (thesis-scoped staging), then re-defaulted from config |
| `assistant_discuss_run_picker` | `str \| None` (run id) | Run selectbox + deep-link preselect | thesis switch |

Both are registered in `ASSISTANT_SESSION_KEYS`, added to
`THESIS_SCOPED_STAGING_KEYS`, and documented in `docs/ARCHITECTURE.md` in the PR
that introduces them. Widget-key writes happen **before** the widget is
instantiated, following the existing `assistant_thesis_picker` precedent.

**Clear-path mechanics (binding for RUX-1):** `clear_thesis_scoped_state` does
**not** iterate `THESIS_SCOPED_STAGING_KEYS` — it hardcodes each reset (see
`workspace.py`). RUX-1 must therefore:

1. Add both keys to `ASSISTANT_SESSION_KEYS` and `THESIS_SCOPED_STAGING_KEYS`
   (documentation / inventory).
2. Set defaults in `init_assistant_session_state`
   (`assistant_ux_mode` ← `load_assistant_ux_settings().default_mode`,
   `assistant_discuss_run_picker` ← `None`).
3. Explicitly reset both inside `clear_thesis_scoped_state` (same pattern as
   `assistant_focused_run_id` / `assistant_results_qa_deep_link`): mode back to
   the configured default, picker to `None`.
4. Also `pop` the Streamlit widget keys `assistant_ux_mode` /
   `assistant_discuss_run_picker` in the existing widget-key cleanup loop when
   they are bound as widgets (same hazard as `results-qa-input-*`), **or** write
   the defaults into those keys before the widgets bind — pick one approach and
   document it in the RUX-1 PR body; do not leave a stale selectbox option after
   thesis switch.

**Discussable vs hash-verified (binding for RUX-2 UX, not a predicate change):**
The frozen UI eligibility predicate stays `status == "completed"` +
`isinstance(provenance, dict)` + RQ enabled — matching today's Discuss gate.
Successful `handle_results_turn` / deterministic Explain / Voice still require
`require_run_bundle_hash` (and typically `bundle_path`). RUX-2 must keep today's
fail-closed error surfacing on Send/Explain/Voice for hash-less rows; it must
**not** silently widen the picker predicate to the Compare-style
hash+`bundle_path` filter. Optionally caption hash-less selected runs with the
existing provenance/identity messaging — no new error path.

### 4.3 New config section

```toml
[assistant.ux]
# Which surface the Research Assistant opens on. "discuss" | "help" | "draft".
default_mode = "discuss"
```

Loader `load_assistant_ux_settings()` + `AssistantUxSettings` dataclass in
`thesistester/assistant/llm.py`, mirroring `load_results_qa_settings` /
`load_product_help_settings`: missing section or unknown value → safe default
`"discuss"`. This is a **preselection** setting only — there is exactly one
layout code path (no legacy layout branch, no drift surface).

### 4.4 New test harness

`tests/test_assistant_page_render.py` — first `streamlit.testing.v1.AppTest` use
in the repo. Renders `pages/14_Research_Assistant.py` in-process against a
temporary store (`THESISTESTER_STORE_DIR`) with a seeded thesis, and asserts
**structure** (which surfaces are open, which widgets exist, which mode is
active) instead of grepping source strings. Feasibility verified before writing
this plan: the page renders under AppTest with no exception, exposing subheaders,
expander labels, chat inputs, and text inputs.

---

## 5. PR breakdown

Six PRs. Each is independently revertable and independently shippable. `RUX-2` is
the only invasive one; `RUX-0`/`RUX-1` de-risk it and `RUX-3`+ are optional
polish on top.

### 5.1 RUX-0 — Contract, render harness, baseline snapshot *(no product change)* — ✅ **Implemented**

**Goal:** land this contract, register the series, and create the structural
regression net that RUX-2 will be judged against.

**In scope**

| File | Change |
|---|---|
| `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` | This document (new) |
| `docs/ENGINEERING_ROADMAP.md` | One index row: Research Assistant UX refocus → this doc (RUX), status Planned |
| `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` | One **Related docs** row pointing here for UI placement; explicit note that RQ channel logic is not reopened |
| `docs/AGENT_GUIDE.md` | Short RUX paragraph beside the RQ/HC/VA ownership notes |
| `tests/test_assistant_page_render.py` | New AppTest harness + baseline assertions of **today's** layout |

**Baseline assertions (must pass on current `main` before any layout change)**

1. No-thesis render shows exactly the `Create or select a thesis to begin.` info and stops.
2. With a seeded thesis: `Assistant chat` subheader present; `Help / how it works` present as a collapsed expander; `Advanced: draft, runs & compare` present and collapsed; `Debug: raw JSON & conversation audit` present and collapsed.
3. Exactly one `chat_input` on the page (the draft input).
4. Draft chat renders no `product_help` / `results_qa` bubbles when such messages exist in the conversation (channel isolation, rendered — not source-grepped).
5. A staged `classic_focus_run_id` + `classic_focus_channel="results_qa"` results in `ASSISTANT_ADVANCED_EXPANDER_KEY` and `linked_run_expander_key(run_id)` being set open.
6. Rendering the page leaves a `spawn`-context process pool usable (harness hygiene, §5.1.1).

Assertions 4 and 5 are the **behavioral contract RUX-2 must preserve**; they are
rewritten (not deleted) in RUX-2 to target the new layout.

**Out of scope:** any change to `pages/`, `thesistester/`, or `config/`.

**Tests:** new file green; full suite green and unchanged elsewhere.

**Acceptance:** doc merged; harness runs in CI; zero product diff
(`git diff --stat` touches only `docs/` + the new test).

**Rollback:** revert the commit; nothing depends on it yet.

#### 5.1.1 Harness hygiene (binding for every future `AppTest` module)

Streamlit's script runner installs the rendered page as
`sys.modules["__main__"]` and puts the page directory on `sys.path`. Left in
place, `thesistester.cli.run_batch`'s `spawn`-context `ProcessPoolExecutor`
children re-import the Research Assistant page as their main module, crash, and
surface as `BrokenProcessPool` in `tests/test_cli.py::test_parallel_batch_is_identical_to_serial`
— an order-dependent failure with no apparent connection to the assistant.

**Rule:** every `AppTest` render must restore `sys.modules["__main__"]` and
`sys.path` immediately after the run (`_run_app` in the harness), backed by an
autouse fixture as defence in depth, and the module must keep the guard test that
starts a `spawn` pool after a render. When a second `AppTest` module appears
(RUX-2/RUX-3), promote the isolation fixture to `tests/conftest.py` rather than
copying it.

**Implementation record.** `tests/test_assistant_page_render.py` renders the page
against a temporary store (`THESISTESTER_STORE_DIR`) and asserts top-level
element order via `AppTest.main.children`, collapse state via
`expander.proto.expanded`, chat-input ownership via `AppTest.chat_input`, and
deep-link force-open via the session keys `ASSISTANT_ADVANCED_EXPANDER_KEY` /
`linked_run_expander_key(run_id)`. Each load-bearing assertion was
mutation-verified: forcing `Help / how it works` open fails the prominence test,
deleting the `force_results_qa_expanders_open` call fails the deep-link test, and
dropping the `is_draft_channel_message` guard in `chat_message_display_role`
fails the channel-isolation test, and dropping the `__main__`/`sys.path` restore
fails the spawn-pool guard. Help/Discuss-dependent assertions are gated on
`load_product_help_settings().enabled`, and no assertion depends on voice being
enabled, so a local `config/assistant.voice.override.toml` cannot flip results.

---

### 5.2 RUX-1 — UX foundation *(no visible change)* — ✅ **Implemented** ([#301](https://github.com/AccumuLatata/ThesisTester/pull/301))

**Goal:** introduce mode/nav plumbing and the navigation-phrase single source of
truth without changing a single rendered pixel.

**In scope**

| File | Change |
|---|---|
| `thesistester/assistant/ux.py` | New module per §4.1. Nav-phrase constants hold **byte-identical current fragments** from the §1.3 inventory (six constants). |
| `thesistester/assistant/__init__.py` | Re-export the new public names (additive) |
| `thesistester/assistant/llm.py` | `AssistantUxSettings` + `load_assistant_ux_settings()` (§4.3) |
| `config/assistant.toml` | `[assistant.ux] default_mode = "discuss"` |
| `thesistester/assistant/workspace.py` | Register `assistant_ux_mode` / `assistant_discuss_run_picker` in `ASSISTANT_SESSION_KEYS` + `THESIS_SCOPED_STAGING_KEYS`; defaults in `init_assistant_session_state`; **explicit** resets in `clear_thesis_scoped_state` per §4.2 (tuple membership alone is not enough) |
| `thesistester/assistant/product_help.py` | **Only** substitute the three Discuss-nav call sites with `DISCUSS_NAV_HINT` / `DISCUSS_NAV_SHORT` (values unchanged) |
| `pages/14_Research_Assistant.py` | **Only** substitute the §1.3 page call sites with the six constants (values unchanged; compose around fragments where today's sentence wraps them) |
| `docs/ARCHITECTURE.md` | Document the two new session keys, clear-path mechanics, and the `[assistant.ux]` section |
| `tests/test_assistant_ux.py` | New: `resolve_mode`, `discussable_runs`, `default_discuss_run_id`, `run_picker_label`, settings loader (missing section, unknown value, valid values); assert constant values equal today's fragments |
| `tests/test_assistant_page_render.py` | Extend: rendered captions still contain the current nav fragments (proves the refactor is value-preserving) |

**Implementation notes**

- `discussable_runs` must apply the frozen predicate only — no sorting change; the page's existing `reversed(runs)` display order is preserved by the caller.
- `resolve_mode` must never raise: unknown/absent → configured default → `"discuss"`.
- Settings loader must tolerate a missing file and a missing section exactly like the RQ loaders.
- Nav-constant substitution must keep surrounding sentence text identical (compose `f"…{DISCUSS_NAV_HINT}…"` rather than rewriting captions).
- Clear-path: follow §4.2 mechanics; do not assume `THESIS_SCOPED_STAGING_KEYS` membership alone clears anything.

**Tests:** new unit tests; `tests/test_assistant_product_help.py`,
`tests/test_assistant_llm_evaluations.py`, `tests/test_assistant_voice_session.py`,
`tests/test_assistant_qa_settings.py` must pass **unmodified** — that is the
proof the refactor changed no strings.

**Acceptance:** full suite green with zero edits to existing assertions; AppTest
baseline from RUX-0 still passes unchanged.

**Rollback:** revert; the constants are additive and unused by layout yet.

---

### 5.3 RUX-2 — Layout inversion: Discuss-first modes *(the substantive PR)*

**Goal:** deliver the product decision (§0.2). Discuss becomes the default
surface, Help becomes a peer mode, draft chat is demoted, Advanced/Debug keep
their internals.

**In scope**

| File | Change |
|---|---|
| `pages/14_Research_Assistant.py` | Mode selector; Discuss mode surface (run picker + moved thread/input/voice + secondary actions + empty state); Help mode (block promoted out of its expander); Draft mode (existing block, now mode-scoped); hoist `runs = orchestrator.list_runs(thesis_id)` and `load_results_qa_settings()` above the mode block and reuse inside Advanced; deep-link consume also preselects mode + run; nav-phrase constants flipped to the new locations |
| `thesistester/assistant/ux.py` | Flip nav-phrase constant **values** to the new navigation (e.g. Discuss hint → "the Discuss runs mode on Research Assistant") |
| `thesistester/assistant/workspace.py` | Additive helper for deep-link mode/run preselection if needed (no change to existing focus helpers' semantics) |
| `docs/USER_GUIDE.md` | Update navigation steps in the three affected sections (titles unchanged): Research Assistant surfaces table + how-to, Research mode step 4, Help-vs-Discuss steps 2–3 |
| `docs/ARCHITECTURE.md` | Replace the "chat-first" paragraph with the discuss-first mode layout; update the two `Advanced → Linked runs` references |
| `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` | Amend the two §1 UI-attach freezes per §1.2 and the §RQ-4 UI note (channel logic untouched) |
| `docs/ENGINEERING.md` | Update the realtime-voice navigation line |
| `app.py` | One-line pointer refresh (Research Assistant = discuss runs + product help) |
| `tests/test_assistant_page_render.py` | Rewrite structural assertions to the new layout (modes, default = Discuss, Discuss thread/input at top level, Help mode, Advanced/Debug still collapsed, channel isolation preserved, deep-link → Discuss mode + preselected run **and** still force-opens the Advanced/run expanders). **First addition in RUX-2:** seed at least one completed discussable run (status `completed` + dict provenance) so AppTest can assert Discuss thread/input visibility and catch duplicate widget keys — RUX-0's deep-link baseline uses an orphan `run_id` and only proves expander force-open session keys |
| `tests/test_assistant_workspace.py` | Update the `Advanced → Linked runs` source guard and any placement-dependent ordering assertions |
| `tests/test_assistant_help_coverage.py` | Update `test_help_expander_discoverability_caption_lists_example_topics` (Help is a mode, not an expander); keep the caption-content assertions |
| `tests/test_ui_copy_guards.py` | Rename `test_assistant_page_is_chat_first_...` → discuss-first; keep the no-`page_link` / no-nav-strip guards |

**Movement map (exact)**

| Block | From | To | Rule |
|---|---|---|---|
| Discuss results caption + thread + `results-qa-input-{run_id}` + `results-qa-send-{run_id}` + `handle_results_turn` call + clear-flag logic | inside Linked-run expander, inside `if run.status == "completed" and isinstance(run.provenance, dict)` **and** `results_qa.enabled` | Discuss mode surface: picker/secondary via `recorded_completed_runs`; Q&A/voice additionally gated by `results_qa.enabled` (same sibling split as pre-RUX-2) | Widget keys, session keys, filters, and error handling copied verbatim; only indentation/container changes |
| Voice discuss PTT + realtime blocks | same run expander | Discuss mode, directly under the Discuss input | Same keys, same `thesis_has_running_run` gate, same `require_run_bundle_hash` check, same copy |
| `Explain run` + explanation display, `Open exact run in Backtest`, `Restore bundle into research pages` | run expander | **Duplicated intent, single render:** rendered in Discuss mode for the selected run; removed from the run expander to avoid duplicate widget keys | Keys stay unique because each is rendered exactly once per run per rerun |
| `Generate evidence-only AI explanation` (+ LLM explanation display) | run expander | **Stays in Advanced → Linked run expander** (explicit decision) | Deterministic Explain moves with Discuss; LLM explain remains an Advanced secondary action so RUX-2 does not invent a fourth Discuss-mode AI surface. Document this asymmetry in the RUX-2 PR body. |
| Help block (caption, thread, `product-help-input`, `product-help-send`, voice help) | `st.expander("Help / how it works")` | Help mode container, same order | Copy and keys verbatim |
| Assistant chat (caption, bubbles, `st.chat_input`) | page hero | Draft mode | `st.chat_input` stays page-level and is rendered **only** in Draft mode → still exactly one per rerun |
| Everything else under Advanced/Debug | unchanged | unchanged | No edits beyond the removed Discuss/voice/explain blocks and the hoisted `runs` variable |

**Hard implementation rules**

1. **No duplicate widget keys.** Every moved widget must be rendered in exactly one place per rerun. The run expander loses the blocks that moved.
2. **Mode-scoped rendering.** Exactly one of the three mode bodies renders per rerun; the mode selector is the only cross-mode widget.
3. **Deep-link superset.** On `classic_focus_channel == "results_qa"`: preselect mode `discuss` + the focused run, **and** keep calling `force_results_qa_expanders_open`. Legacy behavior is a subset of new behavior.
4. **Widget-key write order.** `assistant_ux_mode` / `assistant_discuss_run_picker` are written before their widgets are instantiated (existing `assistant_thesis_picker` precedent).
5. **Flash preserved.** All existing `set_assistant_flash` call sites stay; Advanced actions still surface outcomes at the hub after rerun.
6. **Repository reads unchanged in count or kind.** Hoisting `list_runs` must not add a second call; it is the same read, earlier.
7. **No behavior on empty state.** No run → guidance text only; no orchestrator call.

**Tests:** rewritten render assertions above, plus the full existing suite. RQ/HC/VA
channel, grounding, corpus, and eval tests must pass with **no assertion edits**
except the three placement-dependent source guards listed in the scope table.

**Acceptance**

- Default render on a thesis with ≥1 eligible run: Discuss mode active, thread + input visible without opening any expander.
- Default render with no eligible run: Discuss empty state naming `Record and discuss this run`.
- Help reachable in one click; Draft reachable in one click; Advanced and Debug still collapsed by default.
- `Confirm validated RunSpec` and `Run confirmed research` reachable via Advanced in every mode.
- Classic `Discuss this run` and `Record and discuss` land on the run's Discuss thread.
- Zero diff in `thesistester/assistant/{orchestrator,repository,registry,handlers,tools,results_qa,help_corpus,explainer}.py` and in `tests/fixtures/`.

**Rollback:** single revert restores the previous layout; RUX-1 plumbing stays
harmless (constants revert to their original values with the same commit).

---

### 5.4 RUX-3 — Chat input for the active mode *(optional, recommended)*

**Goal:** make Discuss and Help feel like chats rather than forms.

**In scope**

| File | Change |
|---|---|
| `pages/14_Research_Assistant.py` | Render exactly one **page-level** `st.chat_input` whose target is the active mode: Discuss → `handle_results_turn` for the selected run, Help → `handle_help_turn`, Draft → `handle_chat_turn` (unchanged). Placeholder text is mode-specific. Keep the widget for layout stability but set `disabled=True` when Discuss has no selected run / Results Q&A is off, or Help is off. |
| `thesistester/assistant/ux.py` | `chat_input_placeholder(mode)` + `chat_input_key(mode, run_id=None)` + `chat_input_disabled(...)` helpers |
| `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` | Amend the two §1 UI-attach widget rows (v1 `text_input` → mode-scoped page-level `chat_input`); note `st.chat_input` remains page-level, never nested |
| `docs/ARCHITECTURE.md` | Update the Discuss/Help draft-key notes to reflect widget change |
| `tests/test_assistant_page_render.py` | Assert exactly one `chat_input` per rerun in every mode; submitting in Discuss mode calls `handle_results_turn` with the selected `run_id`; submitting in Help mode calls `handle_help_turn`; no `choices` on either |

**Session-key decision (must be explicit in the PR body)**

`assistant_results_qa_drafts`, `assistant_product_help_draft`, and the
`assistant_clear_*` deferred-clear flags exist to persist unsent `text_input`
content. With `chat_input` they have no producer. Choose **one** and document it:

- **(a) Retire** them: remove from `ASSISTANT_SESSION_KEYS` / clear paths, update `docs/ARCHITECTURE.md` and the tests that assert the clear-flag mechanics. Cleanest; a documented session-key contract change.
- **(b) Retain** them as inert compatibility keys with a comment. Zero contract change, some dead surface.

Recommendation: **(a)**, because retained-but-unproduced keys are exactly the
drift this repo's session-key discipline exists to prevent.

**Regression note:** unsent-draft persistence across reruns is intentionally
dropped (`chat_input` is a trigger widget). Call this out in the PR body and in
`ARCHITECTURE.md`; it is a UX simplification, not a data loss path — nothing
unsent was ever persisted to the store.

**Acceptance:** exactly one chat input per rerun in all three modes; channel
routing proven by rendered tests; gated modes render `disabled` chat_input
(no-run Discuss / RQ-off / Help-off); no nested `chat_input` anywhere (keeps the
Streamlit `>=1.56` floor honest).

**Rollback:** revert restores `text_input` + Send (and the keys, if (a) was taken,
in the same revert).

---

### 5.5 RUX-4 — Help/remediation and eval-bank re-anchor

**Goal:** make the Help channel's own answers describe the new navigation, and
prove it with the existing coverage machinery.

**In scope**

| File | Change |
|---|---|
| `thesistester/assistant/product_help.py` | Nav-phrase constants only (already imported after RUX-1); no prompt-structure or grounding change |
| `docs/USER_GUIDE.md` | Add "how do I discuss a run" style navigation coverage inside existing allowlisted sections (no new/renamed H2) |
| `tests/test_assistant_help_coverage.py` | Extend the Q-H bank with a navigation question ("How do I discuss a completed run?") and assert corpus retrieval of the Research-Assistant / Help-vs-Discuss sections |
| `tests/test_assistant_product_help.py` | Assert remediation summary still contains `Discuss results` and now names the mode, and that no run metric is invented |
| `tests/test_assistant_llm_evaluations.py` | Update only expectations that quote navigation phrasing; honesty/injection freezes untouched |
| `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` | Maintenance note: bodies re-anchored, allowlist unchanged |

**Out of scope:** widening the corpus allowlist, adding docs to the manifest,
changing grounding rules, or touching the `AGENT_GUIDE`-exclusion rule.

**Acceptance:** Help answers route users to the Discuss mode; corpus allowlist
diff is empty; RQ-5 honesty/injection evals green.

**Rollback:** revert; RUX-2 layout is unaffected.

---

### 5.6 RUX-5 — Release evidence and closeout

**Goal:** record the evidence and flip status, per the SW-series precedent.

**In scope**

| File | Change |
|---|---|
| `docs/RESEARCH_ASSISTANT_UX_REFOCUS_EVIDENCE.md` | New: before/after layout, rendered-assertion inventory, deep-link verification, manual walkthrough screenshots/recording, full-suite result |
| `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` | Status → Complete; per-PR outcomes |
| `docs/ENGINEERING_ROADMAP.md` | Index row → Complete (RUX-0…RUX-5) |
| `docs/AGENT_GUIDE.md` | "Do not reopen RUX for layout changes; amend this contract instead" |

**Acceptance:** evidence doc contains rendered proof for every §5.3 acceptance
bullet; suite green.

---

## 6. Regression-safety framework mapping (`ENGINEERING_PROPOSAL.md` §4)

Map to the **numbered rules 1–10 under `ENGINEERING_PROPOSAL.md` §4** (not to
§4.1 / §4.2 — those subsections are the golden-master operational spec and the
per-milestone PR acceptance checklist).

| Rule | How RUX complies |
|---|---|
| §4 rule 1 — Additive-only engine changes | No engine file is touched by any RUX PR. Enforced by the §5 scope tables and a diff review of `thesistester/` |
| §4 rule 2 — Golden-master before engine change | Not applicable (no engine change); `tests/test_golden_master.py` and `tests/fixtures/golden/` must be **unmodified** in every RUX diff — this is the stated gate |
| §4 rule 3 — Opt-in, default-off features | No new behavior flag. The one new setting (`[assistant.ux].default_mode`) only preselects an existing surface, so there is a single layout code path (a "legacy layout" flag would create the drift this rule guards against) |
| §4 rule 4 — Schema-versioned persistence | No persisted artifact changes; no store schema bump |
| §4 rule 5 — Point-in-time proof | Not applicable (no new computation) |
| §4 rule 6 — `st.session_state` contract stability | Existing keys keep producer/consumer/schema. Two additive keys, documented in `ARCHITECTURE.md` in the same PR. RUX-3's key retirement is an explicit, documented contract change with test updates |
| §4 rule 7 — Determinism | Mode/run resolution is pure and order-deterministic; run picker default derives from the existing run list order; no wall-clock or dict-order dependence |
| §4 rule 8 — Same-PR documentation | Every PR's scope table names its doc edits. Navigation phrases that become false are fixed in the PR that makes them false |
| §4 rule 9 — CI gate | Full pytest + ruff green per PR; no merge on red |
| §4 rule 10 — Honesty framing | Unchanged: Discuss stays evidence-only, Help stays corpus-grounded with remediation |

### 6.1 Golden-master equivalent for this series

There is no engine output to freeze, so RUX's load-bearing control is the
**rendered-structure baseline** (`tests/test_assistant_page_render.py`) captured
in RUX-0 against current `main`. It replaces brittle source-string greps with
assertions on what the page actually renders, and the two behavioral assertions
(channel isolation, deep-link force-open) are the invariants RUX-2 is judged
against. Regeneration policy mirrors `ENGINEERING_PROPOSAL.md` §4.1 item 3:
baseline assertions change only in a PR that states why, and never silently.
RUX-0 does **not** seed a completed discussable run (deep-link uses an orphan
`run_id` to prove force-open keys only); RUX-2 must add that fixture before
rewriting prominence assertions.

---

## 7. Test inventory (must stay green)

**Unchanged, no assertion edits allowed** (proof of non-regression):
`tests/test_golden_master.py`, `tests/test_assistant_execution_parity.py`,
`tests/test_assistant_orchestrator.py`, `tests/test_assistant_repository.py`,
`tests/test_assistant_results_qa.py`, `tests/test_assistant_results_projections.py`,
`tests/test_assistant_explainer.py`, `tests/test_assistant_llm_explainer.py`,
`tests/test_assistant_help_corpus.py`, `tests/test_assistant_user_guide_structure.py`,
`tests/test_assistant_registry_audit.py`, `tests/test_assistant_tools.py`,
`tests/test_assistant_comparison.py`, `tests/test_assistant_lifecycle_integration.py`,
`tests/test_classic_nav.py`, `tests/test_classic_record.py`,
`tests/test_classic_context.py`, `tests/test_classic_export.py`,
`tests/test_cai*.py`, `tests/test_assistant_voice_*.py` (voice copy strings are
frozen by §1.1).

**Expected to change, and only where listed:**

| Test | PR | Why |
|---|---|---|
| `tests/test_assistant_page_render.py` | RUX-0 (new), RUX-1, RUX-2, RUX-3 | The structural baseline itself |
| `tests/test_assistant_ux.py` | RUX-1 (new) | New pure helpers + settings loader |
| `tests/test_assistant_workspace.py` | RUX-2 | `Advanced → Linked runs` source guard + placement ordering |
| `tests/test_assistant_help_coverage.py` | RUX-2, RUX-4 | Help expander → Help mode; nav question added to bank |
| `tests/test_ui_copy_guards.py` | RUX-2 | chat-first → discuss-first guard rename |
| `tests/test_assistant_product_help.py` | RUX-4 | Remediation navigation wording |
| `tests/test_assistant_llm_evaluations.py` | RUX-4 | Only navigation-quoting expectations |
| `tests/test_assistant_qa_settings.py` | RUX-1 | Optional: co-locate the new UX settings loader tests |

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Duplicate Streamlit widget keys after moving Discuss/voice/explain blocks | Medium | Page crash (`StreamlitDuplicateElementId`) | §5.3 rule 1 (render once per rerun); RUX-2 AppTest must seed a completed discussable run and render Discuss/Help/Draft modes so a duplicate key fails CI, not the user (RUX-0 baseline has no eligible run and cannot catch this) |
| Classic `Discuss this run` deep-link regresses | Medium | Primary workflow broken | Deep-link is a **superset**: preselect mode + run *and* keep `force_results_qa_expanders_open`; asserted in RUX-0 baseline and re-asserted in RUX-2 |
| Confirm/Run becomes unreachable | Low | Second pipeline unusable | Advanced stays rendered in all modes; explicit RUX-2 acceptance bullet |
| Help answers give stale navigation for a release window | Medium | Trust erosion in the Help channel | Nav phrases are one constant after RUX-1 and flip inside RUX-2; `USER_GUIDE` bodies fixed in the same PR |
| Channel isolation breaks while restructuring containers | Low | RQ freeze violation, prompt contamination | Filters/entrypoints untouched; rendered isolation assertion in the baseline; RQ channel tests must pass unmodified |
| Advanced actions lose visible feedback when a mode body re-renders | Low | Actions look like no-ops | All `set_assistant_flash` sites retained; flash renders at hub level above the mode block |
| Voice regression (blocked mic, wrong run binding) | Low | VA release gate | Voice blocks move with their channel; keys, gating, and copy frozen by §1.1; VA tests unmodified |
| Scope creep into orchestrator/engine "while cleaning up UI" | Medium | Loss of regression safety | §1.1 file blocklist + per-PR zero-diff acceptance check on `thesistester/assistant/*` core modules and `tests/fixtures/` |
| RUX-3 drops unsent-draft persistence | High (by design) | Minor UX surprise | Documented in PR body + `ARCHITECTURE.md`; nothing unsent was ever persisted |
| Streamlit floor mismatch for new widgets | Low | Install-time break | Only `segmented_control` (≥1.40), keyed `expander` (≥1.55), page-level `chat_input` used; floor stays `>=1.56`; no nested `chat_input` |

---

## 9. Per-PR acceptance checklist (mandatory)

Every RUX PR must tick all of these in its body:

- [ ] Scope matches exactly one §5 subsection; no file outside its **In scope** table is modified.
- [ ] Zero diff in `thesistester/api.py`, engine modules, `pages/1..13`, `tests/fixtures/`, and the core assistant modules named in §1.1.
- [ ] `tests/test_golden_master.py` unmodified and green.
- [ ] Full `pytest` green; `ruff check` + `ruff format --check` green.
- [ ] Rendered-structure tests updated/extended, not deleted.
- [ ] Channel separation, evidence path, and confirmation gates verifiably unchanged (RQ/CAI/VA tests pass without assertion edits, except those explicitly listed for that PR).
- [ ] New/changed `st.session_state` keys documented in `docs/ARCHITECTURE.md` in the same PR.
- [ ] Any navigation phrase that became false is fixed in this PR (page, `product_help.py` constants, `USER_GUIDE`, engineering docs).
- [ ] If an RQ freeze changed, `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` is amended in this PR (§1.2 lists the only amendable rows).
- [ ] PR body contains a short "regression safety" paragraph: what could have drifted, and which test proves it did not.
- [ ] Manual walkthrough evidence for user-visible PRs (RUX-2, RUX-3): default render, Help mode, Draft mode, Advanced reachable, classic deep-link landing.

---

## 10. Sequencing

```text
RUX-0 (docs + render baseline)      ── prerequisite for everything
   └─ RUX-1 (foundation, invisible)  ── prerequisite for RUX-2
        └─ RUX-2 (layout inversion)  ── delivers the product decision
             ├─ RUX-3 (chat input)   ── optional polish, independently revertable
             └─ RUX-4 (help re-anchor)
                  └─ RUX-5 (evidence + closeout)
```

RUX-0 and RUX-1 are zero-risk (docs/tests and a value-preserving refactor).
RUX-2 is the single reviewable behavior change and can be reverted alone. RUX-3
and RUX-4 are independent of each other. Ship RUX-2 and let it settle before
RUX-3, so any layout complaint is separable from the widget change.
