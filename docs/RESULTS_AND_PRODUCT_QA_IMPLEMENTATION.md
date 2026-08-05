# Results Discussion & Product Help — Implementation Contract

**Document type:** Implementation contract (RQ-series) — **single source of truth**
**Status:** proposed — not shipped
**Date:** 2026-08-05
**Owner surface:** `thesistester/assistant/` + Research Assistant page (+ narrow classic-nav entry points)
**Provider (text):** existing OpenAI structured client (`config/assistant.toml` / `OPENAI_API_KEY`)
**Depends on:** C2 complete (`docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` through PR6),
evidence/explain path (`EvidencePacket`, `explain_run`, `explain_run_with_llm`),
`docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Voice relationship:** This series **implements VA-1** from
`docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md`. Voice PRs VA-0 / VA-2+ remain on
that document. Do **not** create a parallel voice roadmap.

This is the **only** binding contract for multi-turn **results discussion** and
**product/how-it-works help**. Do not create parallel results-Q&A or product-help
roadmaps. Amend this file in the same PR that changes a freeze. Every RQ PR must
stay inside its scope table. If a change is not listed under **In scope**, it
belongs in a later PR or is rejected.

### Related docs (completed roadmaps — not competing open plans)

| Doc | Role vs this contract |
|---|---|
| `docs/AI_RESEARCH_ASSISTANT_ROADMAP.md` | ✅ Implemented AIA foundations — keep for invariants; not the results/help surface |
| `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` | ✅ Implemented C2 thesis-draft / explain / provenance loop |
| `docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md` | ✅ Implemented CAI classic↔assistant bridge; RQ-4 owns Discuss deep-link polish |
| `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` | Proposed voice-only series after RQ-1; VA-1 text substrate is RQ-1 here |
| `docs/ENGINEERING_ROADMAP.md` | Index / status tracker — points here for RQ work |

---

## 0. Product intent

Today ThesisTester has three AI-adjacent surfaces that do **not** cover the
requested product:

| Surface | What it does | Gap |
|---|---|---|
| Research Assistant chat | Drafts thesis → structured `choices` | Does not discuss completed runs |
| Explain / LLM explain | One-shot narrative of an `EvidencePacket` | Not multi-turn Q&A |
| Classic “Discuss this run” | Navigates to Research Assistant | Lands in thesis-draft chat |

**Target UX — three channels, one assistant surface:**

```text
Thesis draft chat     → build / refine the experiment (existing handle_chat_turn)
Discuss results       → multi-turn grounded Q&A on one completed run (this series)
Help / How it works   → explain app features, pages, metrics, workflow (this series)
```

Example results questions this series must answer from evidence (not opinion):

1. What was the best time to enter this setup?
2. What is the best SL and target combination under the recorded ranking rule?
3. What are win rate / expectancy / drawdown / profit factor on the sample?
4. How stable is the edge under WFA / bootstrap / Monte Carlo when present?

Example help questions:

1. How does Grid Search ranking work?
2. What is walk-forward vs in-sample grid selection?
3. How do I get from a thesis to a confirmed run?
4. What does `expectancy_r` mean and what caveats apply?

---

## 1. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Channel separation | Thesis draft, results Q&A, and product help are **separate channels**. Never merge into one prompt that can draft `choices` and cite run metrics in the same turn. |
| Results load path | `handle_results_turn` may use RO `BUNDLE.import` (evidence) via the existing explain/evidence path; never `execute_confirmed_run` / `PIPELINE.*` mutators |
| Canonical evidence | Hash-verified `EvidencePacket` is the only numeric source for results answers |
| Grounding | Reuse C2-6 / `llm_explainer` token/percent/caveat rules; uncited numbers fail closed before persist/render |
| Draft hydration | Results and help assistant messages **must omit** `choices` |
| Message tags | Additive message fields only: `"channel"` ∈ {`results_qa`, `product_help`}, plus `"run_id"` for results turns. No Conversation schema bump |
| UI attach (results) | Completed-run expander on Research Assistant; do not replace thesis-draft `st.chat_input` |
| UI attach (help) | Separate Help panel / tab on Research Assistant (not inside a run expander) |
| Help corpus | Curated, versioned local docs + `FEATURE_PARITY_REGISTRY` summaries only — no web search, no arbitrary filesystem |
| Provider | Text stays on existing OpenAI structured client; no Anthropic/xAI in RQ PRs |
| Voice | Out of series except that **RQ-1 satisfies VA-1**. VA-0/VA-2+ stay in the voice contract |
| Engine | No `simulate_trades`, levels, signals, validation-math, or golden fixture changes |
| Default availability | Results/help text channels may ship when `OPENAI_API_KEY` is configured; without a key, deterministic Explain remains available and chat surfaces remediation |

---

## 2. Definition of done

The series is done when a local user can:

1. Select a completed, hash-verified research run.
2. Ask multi-turn questions about that run’s results and receive grounded answers
   with cited packet paths for every numeric claim.
3. Get clear limitations when evidence is missing (e.g. no time analysis in
   bundle, no grid, thin sample).
4. Ask how ThesisTester features work and receive answers grounded in the
   curated help corpus + registry, without invented performance claims.
5. Enter Discuss-results from classic Backtest / Research Bundles against the
   correct run binding (not only thesis-draft focus).
6. Keep thesis-draft chat, deterministic Explain, and one-shot LLM explain
   behavior unchanged when the new channels are unused.
7. Pass honesty/injection evals: no compute dispatch from chat, no uncited
   numbers, no trade advice presented as recommendation.

Voice (VA-4/VA-5) remains optional follow-on work on the voice contract after
RQ-1 lands.

---

## 3. Non-negotiable invariants

1. **No engine touch.** Do not modify `simulate_trades`, levels, signals,
   validation math, or golden fixtures in any RQ PR.
2. **Additive only.** New modules under `thesistester/assistant/` and narrow
   orchestrator/page/classic-nav additions. Legacy chat/explain paths keep
   current semantics when the new UI is unused.
3. **Evidence-bound results.** A results session binds exactly one `run_id` +
   expected `canonical_bundle_hash`. Hash mismatch fails closed.
4. **Read-only results tools.** Results path may call only allowlisted RO
   operations defined in this contract. Never `PIPELINE.*`,
   `execute_confirmed_run`, filesystem/shell/broker, or web search.
5. **Grounding.** Numeric tokens in results (and any help reply that cites
   metrics) must resolve to packet paths, allowlisted tool returns, or
   verbatim help-corpus figures; else fail/flag before trusted UI render.
6. **No draft contamination.** Results/help messages never include `choices`.
   Thesis draft hydration must ignore non-draft channels.
7. **Honesty framing.** Sample-size, costs, intrabar, OOS, and multiple-testing
   caveats from the packet remain mandatory; the model must not soften them
   into trade advice.
8. **Same-PR docs.** Every PR that adds behavior updates the docs listed in
   that PR’s scope. New `assistant_*` session keys are documented in
   `ARCHITECTURE.md` in the same PR.
9. **CI green.** `ruff check .`, `ruff format --check .`, `pytest -q`.
10. **PR body.** Every RQ PR includes a **Regression safety** paragraph stating
    what is untouched (engine/goldens/C2 thesis chat) and which tests gate the
    change. Follow `docs/ENGINEERING_PROPOSAL.md` §4 / §4.2.

---

## 4. Architecture (frozen)

```text
pages/14_Research_Assistant.py  (presentation only)
        │
        ├── Thesis draft chat ──► handle_chat_turn          (existing)
        ├── Discuss results   ──► handle_results_turn       (RQ-1+)
        └── Help / How it works ► handle_help_turn          (RQ-3)
                │
                ▼
        AssistantOrchestrator
                │
        ┌───────┴────────────────────────────┐
        ▼                                    ▼
 results_qa.py                         product_help.py
   packet + history →                  corpus chunks + registry
   grounded ResultsQAReply             → grounded HelpReply
        │                                    │
        └──────────┬─────────────────────────┘
                   ▼
            OpenAI structured client (llm.py)
                   │
                   ▼
        LocalThesisRepository conversations
        (additive channel / run_id tags on messages)
```

| Module | Role | Forbidden |
|---|---|---|
| `thesistester/assistant/results_qa.py` | Multi-turn grounded results replies | Audio, compute dispatch, draft `choices` |
| `thesistester/assistant/results_projections.py` | Deterministic top-N grid / time rankings for packet enrichment | Engine re-sim; free-form LLM |
| `thesistester/assistant/product_help.py` | Multi-turn help replies over curated corpus | Run metrics unless explicitly out of scope; web search |
| `thesistester/assistant/help_corpus.py` | Load/index allowlisted markdown + registry digests | Arbitrary path reads outside allowlist |
| `AssistantOrchestrator.handle_results_turn` | Bind run → evidence → results_qa → persist | `PIPELINE.*` / confirm/execute |
| `AssistantOrchestrator.handle_help_turn` | Load corpus context → product_help → persist | Bundle import / run metrics by default |
| `pages/14_Research_Assistant.py` | Presentation only | Packet construction, secrets, direct repo I/O |

**Reuse (do not fork):**

- `build_evidence_packet` / `explain_run` evidence import
- `assert_llm_explanation_grounded` (or a shared helper extracted from
  `llm_explainer.py` only when needed)
- `FEATURE_PARITY_REGISTRY` / `audit_capability_registry`
- `page_summaries` bounded JSON (already projected into packets)
- Existing `TIME.analyze` handler for optional RO enrichment when time summary
  is absent (RQ-2 only; gated)

---

## 5. Channel & message contracts

### 5.1 Channels

| `channel` | Purpose | Required fields on messages | May include `choices` |
|---|---|---|---|
| _(absent / draft)_ | Thesis drafting (legacy) | existing | Yes (assistant) |
| `results_qa` | Discuss one completed run | `run_id` | **No** |
| `product_help` | App/feature help | none | **No** |

### 5.2 Reply schemas

**Results (`ResultsQAReply`):**

```json
{
  "summary": "string",
  "caveats": ["string"],
  "claims": [{"text": "string", "path": "string"}],
  "followups": ["string"]
}
```

Server resolves each `path` against the bound `EvidencePacket` (or RQ-2
projection object nested under `results.*`), attaches values, and runs the
existing numeric grounding audit.

**Help (`HelpReply`):**

```json
{
  "summary": "string",
  "caveats": ["string"],
  "citations": [{"doc_id": "string", "section": "string"}],
  "followups": ["string"]
}
```

Help replies must not introduce uncited quantitative performance claims about
the user’s runs. If the user asks about *their* results inside Help, the UI/orchestrator
must redirect to Discuss results (structured remediation), not invent numbers.

### 5.3 Persistence

- Append to the active thesis conversation (same `Conversation` store).
- Filter history for each turn by `channel` (and `run_id` for results).
- Trim with existing `max_history_messages` from `config/assistant.toml`.
- Tool/transcript audit remains under Debug; friendly chat renders via
  `format_chat_message_body` / role helpers extended for the new channels.

---

## 6. Evidence context for results Q&A

### 6.1 Tier-1 context (always in packet when present)

| Artifact | Answers |
|---|---|
| `results.trade_summary` | Win rate, expectancy, PF, drawdown, trade count |
| `results.best_grid_result` + grid assumptions | Best SL/TP under recorded ranking metric / min trades |
| `results.time_grouped_summary` | Best entry windows (RTH segment / hour / 30m) |
| Cost / exposure / intrabar / seeds assumptions | Honesty framing |
| Packet `caveats` / `limitations` | Mandatory uncertainty |

### 6.2 Tier-2 context (when present)

`walk_forward_summary`, `validation_summary`, `monte_carlo_summary`,
`overfitting_summary`, `sensitivity_summary`, `noise_summary`,
`portfolio_summary`, OTF summaries, page summaries.

### 6.3 Missing-evidence policy (locked)

| User question class | If evidence missing |
|---|---|
| Best SL/TP | State limitation; do not invent. Point to Grid assumptions / that grid was not run |
| Best entry time | State limitation if `time_grouped_summary` absent. RQ-2 may optionally run RO `TIME.analyze` on the bound bundle and merge a bounded summary into the turn context; never silent re-sim of the full thesis |
| Robustness | State which batteries are absent; never imply OOS proof from IS metrics |

Full trade parquet is **not** sent to the LLM. Deep trade QA (worst losers,
exit-reason breakdown) uses bounded projections only (RQ-2+), never raw frames.

---

## 7. Help corpus contract

### 7.1 Allowlisted sources (v1)

Exact allowlist lands in RQ-0 as a manifest; v1 intent:

| `doc_id` | Source path | Use |
|---|---|---|
| `readme` | `README.md` | Product overview / workflow |
| `architecture` | `docs/ARCHITECTURE.md` | Page/session contracts (selected sections) |
| `metrics` | `docs/METRICS_GLOSSARY.md` | Metric definitions |
| `assumptions` | `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Honesty / limitations |
| `agent_guide` | `docs/AGENT_GUIDE.md` | Operator workflow (selected sections) |
| `research_methodology` | `docs/research-methodology.md` | Research framing |
| `otf` | `docs/otf-filter.md` | OTF behavior |
| `registry` | generated digest of `FEATURE_PARITY_REGISTRY` | Supported vs unsupported capabilities |

### 7.2 Corpus rules

1. Load only allowlisted paths under the repo root (canonicalized; reject `..`).
2. Chunk by heading; attach `{doc_id, section, text}` to the model.
3. Cap total prompt bytes (config knobs in RQ-0/RQ-3).
4. Prefer registry digests over inventing feature support.
5. No network retrieval.

---

## 8. Config contract

Additive keys only; do not reorder/rename existing `[assistant]` keys.

```toml
[assistant.results_qa]
# Text results discussion (RQ-1). Uses existing OpenAI client/settings.
enabled = true
max_history_messages = 12
# When true (RQ-2), allow RO TIME.analyze if time_grouped_summary missing.
allow_time_enrichment = false

[assistant.product_help]
enabled = true
max_history_messages = 12
max_corpus_chars = 24000
```

Secret resolution remains the existing OpenAI path. No new provider keys in RQ.

---

## 9. PR sequence overview

| PR | ID | Title | Merge blocks if… |
|---|---|---|---|
| 1 | RQ-0 | Contracts + channel taxonomy + corpus manifest + docs freeze | Any user-visible chat behavior |
| 2 | RQ-1 | Multi-turn results Q&A (implements VA-1) | Help channel, classic deep-link polish, voice |
| 3 | RQ-2 | Deterministic rankings + optional RO time enrichment | Product help |
| 4 | RQ-3 | Product / how-it-works help channel | Classic entry polish |
| 5 | RQ-4 | Classic “Discuss this run” → results binding + UX polish | Evals-only follow-ups |
| 6 | RQ-5 | Evals + release gate | Flipping undocumented defaults / widening tools |

Dependency graph:

```text
RQ-0 ──► RQ-1 ──► RQ-2 ──► RQ-4 ──► RQ-5
              └──► RQ-3 ─────────────┘
```

- **RQ-1 implements VA-1.** After RQ-1 merges, update
  `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` Implemented contract for VA-1
  and keep VA-0 / VA-2+ sequencing unchanged.
- RQ-2 and RQ-3 may proceed in parallel after RQ-1 (RQ-3 only needs RQ-0 +
  shared message-channel helpers from RQ-1).
- RQ-4 needs RQ-1 (results binding). Prefer RQ-2 before RQ-4 so classic entry
  lands with strong “best time / best SL-TP” answers.
- Do **not** collapse RQ-1 into voice work. Do **not** collapse help into
  results.

---

## 10. Detailed PR scopes

### RQ-0 — Contracts, channel taxonomy, corpus manifest, docs freeze

**Goal:** Freeze schemas, config defaults, corpus allowlist, and ownership of
VA-1 without changing runtime UX.

#### In scope
| Item | Detail |
|---|---|
| Docs | This file is canonical; index pointer in `ENGINEERING_ROADMAP.md`; note in `ASSUMPTIONS_AND_LIMITATIONS.md` + `ARCHITECTURE.md` that `results_qa` / `product_help` channels and config blocks are reserved; `AGENT_GUIDE.md` points agents here for results/help work |
| Docs | Amend `REALTIME_VOICE_AGENT_IMPLEMENTATION.md` § VA-1 with an ownership note: “Implementation owned by RQ-1 in `RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`; do not implement VA-1 in a parallel PR.” |
| Config | Add `[assistant.results_qa]` and `[assistant.product_help]` to `config/assistant.toml` exactly as §8 |
| Code | `thesistester/assistant/help_corpus.py` — allowlist manifest + pure loaders/chunkers; **no orchestrator wiring** |
| Code | Settings loaders for the two new blocks (safe defaults if section missing) colocated with existing assistant settings style |
| Tests | Manifest path safety (`..` rejected), default settings, `load_llm_settings()` still succeeds with new sections |

#### Out of scope
- Any call to OpenAI / UI chat widgets / orchestrator methods
- `results_qa.py` / `product_help.py` reply loops
- Session_state keys beyond documenting reserved names

#### Acceptance
- [ ] New config sections parse; missing sections → safe defaults
- [ ] Help corpus loader refuses non-allowlisted paths
- [ ] Existing `tests/test_assistant_llm*.py` unchanged and green
- [ ] No new third-party dependency
- [ ] `ruff` + `pytest -q` green

#### Regression safety
Additive config + docs + inert corpus module. No engine, no golden, no C2 path
edits. If new sections are absent, loaders behave as disabled/default.

#### Files allowed to touch
```
config/assistant.toml
thesistester/assistant/help_corpus.py
thesistester/assistant/settings_qa.py          # or extend existing settings module if one already fits; keep additive
tests/test_assistant_help_corpus.py
tests/test_assistant_qa_settings.py
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/ENGINEERING_ROADMAP.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ARCHITECTURE.md
docs/AGENT_GUIDE.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md    # VA-1 ownership note only
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### RQ-1 — Multi-turn results Q&A (implements VA-1)

**Goal:** Ship grounded multi-turn discussion of a completed run in text.
This PR **is** VA-1.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/results_qa.py` — `propose_results_reply(client, *, packet, history, user_message) -> ResultsQAReply` with schema in §5.2 |
| Code | System prompt: evidence-only; no trade advice; no calculations beyond packet; distinguish IS vs robustness; ask follow-ups when evidence missing |
| Code | Grounding via `assert_llm_explanation_grounded` or shared helper extracted from `llm_explainer.py` (extract only if required; do not fork rules) |
| Code | `AssistantOrchestrator.handle_results_turn(thesis_id, run_id, message, *, conversation_id=..., client=...)` — `get_run` → hash-verified evidence (existing explain/`BUNDLE.import` evidence path) → `propose_results_reply` → persist user+assistant messages with `"channel": "results_qa"` and `"run_id"`; assistant message omits `choices` |
| Code | History trim filtered by `channel` + `run_id` |
| UI | Inside each completed-run expander in `pages/14_Research_Assistant.py` (beside Explain / LLM explain): **Discuss results** with keyed nested `st.chat_input` or `st.text_input`+button — **no mic**; do not replace thesis-draft `st.chat_input` |
| Session keys | Additive cache keys if needed, e.g. `assistant_results_qa_drafts` — document in `ARCHITECTURE.md` + `ASSISTANT_SESSION_KEYS`; clear appropriately on thesis switch |
| Tests | `tests/test_assistant_results_qa.py` + extend `tests/test_assistant_llm_evaluations.py`: injection → no `execute_confirmed_run` / no `PIPELINE.*`; RO `BUNDLE.import` allowed; uncited numbers rejected; missing run; hash mismatch; history trim by channel+run_id; `handle_chat_turn` still never loads bundles; results messages omit `choices` |
| Docs | Mark VA-1 Implemented contract in the voice doc; mark RQ-1 implemented here; update `ARCHITECTURE.md` / `ASSUMPTIONS_AND_LIMITATIONS.md` / `AGENT_GUIDE.md` |

#### Out of scope
- xAI, audio, STT/TTS, WebSockets
- Product help channel
- `results_projections` / `TIME.analyze` enrichment (RQ-2)
- Classic deep-link binding (RQ-4)
- Changing thesis-draft `handle_chat_turn` prompt/schema
- Rewriting deterministic `explain_evidence_report` templates (call them; don’t rewrite)

#### Acceptance
- [ ] `handle_results_turn` never calls `execute_confirmed_run` and never dispatches `PIPELINE.*` / mutators (asserted). RO `BUNDLE.import` (action `evidence`) allowed
- [ ] Uncited numeric token → error before UI persistence/render
- [ ] Hash mismatch → structured failure; no packet leak
- [ ] Without provider key, deterministic explain still works; results Q&A surfaces clear remediation
- [ ] `handle_chat_turn` behavior fixtures remain green unchanged
- [ ] Persisted results assistant messages omit `choices`
- [ ] User can ask “best SL/TP?” and “expectancy?” against a fixture packet and receive path-cited claims when those fields exist

#### Regression safety
New orchestrator method + optional UI block. Thesis drafting and one-shot
`explain_run_with_llm` keep prior contracts. No engine/golden changes.

#### Files allowed to touch
```
thesistester/assistant/results_qa.py
thesistester/assistant/orchestrator.py          # additive method only
thesistester/assistant/repository.py            # only if message tag helpers needed
thesistester/assistant/llm_explainer.py         # shared grounding helper extract only if required
thesistester/assistant/workspace.py             # session keys / formatters only if required
thesistester/assistant/__init__.py              # exports
pages/14_Research_Assistant.py                  # expander Discuss results only
tests/test_assistant_results_qa.py
tests/test_assistant_llm_evaluations.py
tests/test_assistant_workspace.py               # only if new session keys
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md     # VA-1 implemented contract
docs/AGENT_GUIDE.md
docs/ENGINEERING_ROADMAP.md                     # status note
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### RQ-2 — Deterministic rankings & optional time enrichment

**Goal:** Make the two highest-value trader questions first-class and reliable:
best entry time and best SL/TP — without letting the LLM invent rankings.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/results_projections.py` — pure functions: `project_grid_rankings(packet_or_grid, *, top_n, metric)` and `project_time_rankings(time_grouped_summary, *, bucket_col, metric, min_trades)` returning JSON-safe tables with stable paths |
| Code | Merge projections into results-turn context under `results.projections.*` (ephemeral turn context and/or packet extension used only for Q&A — must not mutate on-disk bundles) |
| Code | When `assistant.results_qa.allow_time_enrichment = true` **and** `time_grouped_summary` missing, `handle_results_turn` may dispatch RO `TIME.analyze` on the bound bundle, then project rankings; audit one tool-transcript entry; fail closed on hash/provenance errors |
| Code | Prompt/tooling guidance so “best” language must state metric, candidate set, min-trades filter, and IS vs OOS status (mirror explainer honesty) |
| Tests | Ranking determinism; empty/missing inputs; enrichment flag off → no `TIME.analyze`; flag on + missing time → RO analyze once; never `PIPELINE.*` |
| Docs | Document projection paths + enrichment flag in `ARCHITECTURE.md` / assumptions |

#### Out of scope
- Product help
- Sending full `trades` frames to the LLM
- Changing grid/time analytics formulas
- UI redesign beyond showing projection-backed claims already returned by RQ-1

#### Acceptance
- [ ] Fixture with grid → “best SL/TP” cites projection/best_grid paths and ranking metric
- [ ] Fixture with time summary → “best entry window” cites ranked bucket + sample size / warnings
- [ ] Enrichment default remains `false`; enabling it is explicit
- [ ] No bundle bytes rewritten

#### Regression safety
Pure projection helpers + optional RO analyze. Engine/goldens/thesis chat
untouched. Default config preserves RQ-1 behavior.

#### Files allowed to touch
```
thesistester/assistant/results_projections.py
thesistester/assistant/results_qa.py            # consume projections in prompt/context
thesistester/assistant/orchestrator.py          # optional RO TIME.analyze branch
config/assistant.toml                           # allow_time_enrichment default false
tests/test_assistant_results_projections.py
tests/test_assistant_results_qa.py              # extend
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/METRICS_GLOSSARY.md                        # only if new displayed ranking labels need glossary cross-links
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### RQ-3 — Product / how-it-works help channel

**Goal:** Answer feature and workflow questions from curated docs + registry,
without mixing in run performance claims.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/product_help.py` — `propose_help_reply(client, *, corpus_chunks, history, user_message) -> HelpReply` |
| Code | `AssistantOrchestrator.handle_help_turn(thesis_id, message, *, conversation_id=..., client=...)` — load corpus via `help_corpus.py`, build registry digest, call product_help, persist with `"channel": "product_help"`, omit `choices` |
| Code | Intent guard: if message clearly asks for *this run’s* performance numbers, return structured remediation pointing to Discuss results (no fabricated metrics) |
| UI | Research Assistant Help panel (collapsed expander or tab sibling to chat hub) with its own keyed input; do not reuse thesis `st.chat_input` |
| Session keys | Additive help draft/cache keys if needed; document + thesis-scope clear as appropriate |
| Tests | Path allowlist; citation required; performance-question remediation; no bundle import; no `choices`; history trim by channel |
| Docs | Assumptions note: help is documentation-grounded, not a second results explainer |

#### Out of scope
- Results packet loading
- Voice
- Editing product docs for marketing tone (content edits only if a citation target is wrong/ambiguous)
- Web search / external URLs as required citations

#### Acceptance
- [ ] “How does grid ranking work?” returns citations to glossary/architecture/registry
- [ ] “What was my best SL?” in Help → remediation to Discuss results, no numbers
- [ ] Non-allowlisted doc paths never load
- [ ] Thesis draft chat fixtures unchanged

#### Regression safety
New channel + UI panel. No engine/golden changes. Results path untouched when
Help unused.

#### Files allowed to touch
```
thesistester/assistant/product_help.py
thesistester/assistant/help_corpus.py           # retrieval wiring only
thesistester/assistant/orchestrator.py          # additive handle_help_turn
thesistester/assistant/workspace.py             # keys/formatters if needed
thesistester/assistant/__init__.py
pages/14_Research_Assistant.py                  # Help panel only
tests/test_assistant_product_help.py
tests/test_assistant_help_corpus.py             # extend
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/AGENT_GUIDE.md
docs/ENGINEERING_ROADMAP.md
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### RQ-4 — Classic entry points & UX polish

**Goal:** Make Discuss results reachable from the classic research loop with the
correct run binding.

#### In scope
| Item | Detail |
|---|---|
| Code | Extend `thesistester/classic_nav.py` / discuss-run helpers so “Discuss this run” sets additive focus state: target thesis (ledger if present), `run_id`, and `channel=results_qa` |
| UI | Research Assistant consumes focus state on load: opens Advanced → Linked runs → that run’s Discuss results thread (or equivalent visible binding), and does **not** only focus thesis-draft chat |
| UI | Copy clarity: thesis chat caption remains “draft only”; Discuss results / Help labeled distinctly |
| Pages | `pages/7_Backtest.py`, `pages/12_Research_Bundles.py` (and Grid/Time only if a discuss affordance already exists or is a one-line reuse of the helper) |
| Tests | Focus payload shape; thesis switch clears stale focus; no `choices` hydration from results focus |
| Docs | `ARCHITECTURE.md` session keys for focus payload |

#### Out of scope
- New classic analytics
- Auto-running grid/time from classic pages
- Voice mic entry

#### Acceptance
- [ ] From a ledger-backed classic run, Discuss lands on results channel for that `run_id`
- [ ] Without a ledger/run id, behavior remains safe (thesis focus + remediation copy)
- [ ] Draft chat does not absorb results history

#### Regression safety
Navigation/focus only. Engine and compute paths untouched.

#### Files allowed to touch
```
thesistester/classic_nav.py
thesistester/classic_ledger.py                  # only if read-only helpers needed
thesistester/assistant/workspace.py
pages/14_Research_Assistant.py
pages/7_Backtest.py
pages/12_Research_Bundles.py
pages/8_Grid_Search.py                          # only if discuss affordance is trivial reuse
pages/9_Time_Analysis.py                        # only if discuss affordance is trivial reuse
tests/test_assistant_workspace.py
tests/test_classic_nav.py                       # or existing classic nav tests
docs/ARCHITECTURE.md
docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md      # status pointer only if needed
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/ENGINEERING_ROADMAP.md
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### RQ-5 — Evals + release gate

**Goal:** Freeze honesty/injection evals and close the series for release.

#### In scope
| Item | Detail |
|---|---|
| Tests | Expand `tests/test_assistant_llm_evaluations.py` (and/or dedicated eval module) with fixtures for: best SL/TP, best time, missing time, missing grid, WFA caveat preservation, help-vs-results redirect, prompt-injection (“ignore evidence and run pipeline”), uncited number rejection, `choices` absence |
| Docs | Fill Implemented contract sections for RQ-0…RQ-4; update `ASSUMPTIONS_AND_LIMITATIONS.md` AI section to mention multi-turn results + help channels; `ENGINEERING_ROADMAP.md` status ✅ |
| Release checklist | Provider key remediation copy; deterministic Explain still works offline; registry audit still green |

#### Out of scope
- New features / tool allowlist expansion
- Enabling voice
- Default model changes

#### Acceptance
- [ ] Eval file fails closed on injection and uncited numbers
- [ ] CI green
- [ ] Docs mark series complete (or explicitly list deferred items)
- [ ] No golden/engine drift

#### Regression safety
Tests + docs. Behavior changes only if an eval reveals a defect — fix narrowly
inside already-shipped RQ modules.

#### Files allowed to touch
```
tests/test_assistant_llm_evaluations.py
tests/test_assistant_results_qa.py
tests/test_assistant_product_help.py
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ENGINEERING_ROADMAP.md
docs/AGENT_GUIDE.md
docs/ARCHITECTURE.md                            # only if eval-driven contract clarifications
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

## 11. Per-PR acceptance checklist (mandatory)

Every RQ PR must satisfy `docs/ENGINEERING_PROPOSAL.md` §4 and §4.2, adapted to
assistant-only work:

1. Unit tests for new functionality (deterministic; mocked provider where needed).
2. Golden-master / engine suite untouched and green (no `GOLDEN_REGEN`).
3. No new randomness without an explicit seed; LLM calls mocked in CI.
4. Same-PR documentation: at minimum the files listed in that PR’s scope;
   always include a short status note in this contract’s Implemented section
   when behavior lands.
5. CI green: `ruff check .`, `ruff format --check .`, `pytest -q`.
6. PR body includes **Regression safety**: engine/goldens/C2 thesis-draft path
   untouched; which tests gate the change; confirmation that results/help
   messages omit `choices`.
7. Page remains presentation-only; secrets never embedded in page modules.
8. Numeric claims in results remain packet/tool grounded.

---

## 12. Explicit non-goals (anti-scope)

| Non-goal | Why |
|---|---|
| Merging results/help into thesis-draft chat | Draft hydration + trust-boundary collision |
| LLM-authored trade recommendations | Honesty / non-advisory product stance |
| Full trade-frame / parquet to the model | Context blowup + leakage of ungroundable detail |
| Web search / browsing tools | Local-first, fail-closed corpus |
| Second backtest engine inside the agent | Registry + API remain the only compute path |
| Voice / xAI in RQ PRs | Owned by VA-series after RQ-1 |
| Anthropic or multi-provider abstraction | Out of series unless a later proposal amends §1 freezes |
| Strategy generation / auto-retune SL from chat | Research tool, not strategy factory |
| Multi-tenant hosted agent | Single-user local assistant contract |

---

## 13. Risk register

| Risk | Mitigation |
|---|---|
| LLM invents “best hour” without time evidence | Missing-evidence policy + grounding fail-closed; RQ-2 projections |
| Results messages hydrate draft `choices` | Persist without `choices`; page hydration filters draft channel only; tests |
| Help channel answers performance questions badly | Explicit remediation to Discuss results; eval fixture |
| Optional `TIME.analyze` becomes hidden compute | Default `allow_time_enrichment=false`; audit transcript; RO only |
| Prompt injection (“run the pipeline”) | Eval suite; orchestrator allowlist; no tools exposed to results/help LLM in v1 beyond server-side RO import/enrichment |
| Corpus drift / wrong citations | Allowlist + section citations; prefer glossary/registry for definitions |
| Scope creep into voice | VA ownership note; RQ PRs reject audio/xAI files |

---

## 14. Mapping to prior investigation recommendations

| Recommendation | Contract home |
|---|---|
| Ship multi-turn results chat on EvidencePacket | RQ-1 (= VA-1) |
| Keep Explain as one-shot deterministic/LLM paraphrase | Untouched; remains sibling control |
| Do not merge into thesis draft chat | §1 freeze + RQ-1/RQ-3 UI rules |
| Best time / best SL-TP from existing analytics | RQ-1 (packet) + RQ-2 (rankings/enrichment) |
| Separate product help channel on docs/registry | RQ-0 corpus + RQ-3 |
| Classic Discuss deep-link to results | RQ-4 |
| Voice later | VA-0 / VA-2+ after RQ-1 |

---

## 15. Suggested copy-ready agent prompt (RQ-1 first implementation)

Use only after RQ-0 is merged. Agents must work regression-safe and update docs
in the same PR.

```markdown
Implement RQ-1 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- You are implementing VA-1 / RQ-1 only. No voice, no product help, no TIME.analyze enrichment.
- Follow the PR’s Files allowed to touch list. Do not modify engine, levels, signals, goldens, or handle_chat_turn semantics.
- Add thesistester/assistant/results_qa.py and AssistantOrchestrator.handle_results_turn.
- Ground all numeric claims with existing llm_explainer rules; fail closed on uncited numbers.
- Persist messages with channel=results_qa and run_id; omit choices on assistant messages.
- UI: Discuss results inside completed-run expander only; do not replace thesis st.chat_input.
- Tests: tests/test_assistant_results_qa.py + extend test_assistant_llm_evaluations.py per the contract acceptance list.
- Same-PR docs: ARCHITECTURE.md, ASSUMPTIONS_AND_LIMITATIONS.md, AGENT_GUIDE.md, mark VA-1 + RQ-1 implemented contracts.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green.
```

---

## 16. Status ledger

| ID | Status |
|---|---|
| RQ-0 | Proposed |
| RQ-1 (VA-1) | Proposed |
| RQ-2 | Proposed |
| RQ-3 | Proposed |
| RQ-4 | Proposed |
| RQ-5 | Proposed |
