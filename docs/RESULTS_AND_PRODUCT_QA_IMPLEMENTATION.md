# Results Discussion & Product Help — Implementation Contract

**Document type:** Implementation contract (RQ-series) — **single source of truth**
**Status:** ✅ complete — RQ-0…RQ-5 implemented (release gate frozen)
**Date:** 2026-08-05
**Owner surface:** `thesistester/assistant/` + Research Assistant page (+ narrow classic-nav entry points)
**Provider (text):** existing OpenAI structured client (`config/assistant.toml` / `OPENAI_API_KEY`)
**Depends on:** C2 complete (`docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` through PR6),
evidence/explain path (`EvidencePacket`, `explain_run`, `explain_run_with_llm`),
`docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Voice relationship:** This series **implements VA-1** from
`docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (channel substrate). Help
**corpus** substrate for spoken Help is HC-complete
(`docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md`). Voice PRs VA-0 / VA-2+ remain
on the VA document. Do **not** create a parallel voice roadmap or reopen HC
from VA.

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
| `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` | Voice-only series (post-RQ / post-HC); VA-1 text substrate is RQ-1 here; Help corpus substrate is HC-complete; VA-0 contracts/flag freeze landed there; VA-2+ remain there |
| `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` | ✅ HC-0…HC-4 Help **content/allowlist** coverage (USER_GUIDE + §7.1.4 + §5 bank); amends §7.1 only via HC maintenance PRs — does not reopen RQ-3 channel logic |
| `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` | ✅ RUX series complete (RUX-0…RUX-5; evidence `docs/archive/RESEARCH_ASSISTANT_UX_REFOCUS_EVIDENCE.md`) — owns Research Assistant **page layout / surface prominence**. This contract keeps owning Discuss/Help channel logic, grounding, evidence, remediation, message tags, and classic-focus key shape. Do not reopen RQ channel logic for layout work; amend the RUX contract instead. |
| `docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md` | ✅ DI-0…DI-3 complete (recovery UX + overview intent slices + path catalog + digit-free expert overlay). **Must not loosen or amend** RQ digit/path honesty gates / `assert_llm_explanation_grounded`; must not silently remap specialist asks onto KPI slices. |
| `docs/RESEARCH_INTELLIGENCE_IMPLEMENTATION.md` | ✅ RI-0…RI-10 complete — fail-open specialist / single-metric / meaning / mixed-ask / deep-trade slices + duplex specialist envelopes. **Must not loosen or amend** RQ digit/path honesty gates; consumes RQ-2 projections; no engine recompute from chat; permanent residual cues keep veto ≠ unmatched. |
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
| Draft history isolation | Additive history selection only (not a prompt/schema change): `handle_chat_turn` must exclude messages with `channel` set (treat absent/`None` as draft). Page draft hydration (`assistant_draft_prompt` / `choices`) must ignore non-draft channels. Lands in RQ-1 (helpers may land in RQ-0). |
| Results load path | `handle_results_turn` may use RO `BUNDLE.import` (evidence) via the existing explain/evidence path; never `execute_confirmed_run` / `PIPELINE.*` mutators |
| Canonical evidence | Hash-verified `EvidencePacket` is the only numeric source for results answers |
| Grounding | Reuse C2-6 / `llm_explainer` token/percent/caveat rules; uncited numbers fail closed before persist/render. `followups` fail closed if they contain digit tokens not present in cited claim values (or omit numbers entirely). Cited claim values include int/float plus pure numeric strings; cited `HH:MM` / `H:MM` clock bucket labels ground matching clock spans as wholes (component digits are not allowlisted); European decimal commas (`0,25`) and `Prozent` / spaced `%` narration follow the same normalizers; hash/path/column-name strings do not contribute digits. |
| Projection grounding (RQ-2) | Ground against an ephemeral turn context / packet copy that includes `results.projections.*`; never mutate on-disk bundles. Path existence uses the same object the model saw. |
| Draft hydration | Results and help assistant messages **must omit** `choices` |
| Message tags | Additive message fields only: `"channel"` ∈ {`results_qa`, `product_help`}, plus `"run_id"` for results turns. No Conversation schema bump. Leave `Conversation.selected_run_id` unused in RQ (binding is message `run_id` + classic focus). |
| UI attach (results) | **Discuss runs** mode on Research Assistant (not inside a Linked-run expander). **Input widget (RUX-3):** exactly one page-level mode-scoped `st.chat_input` routed to `handle_results_turn` for the selected run (never nested; never a second page-level chat input). Placement amended by RUX-2; widget amended by RUX-3 — see `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md`. |
| UI attach (help) | **Help** mode on Research Assistant (peer to Discuss; not inside a run expander). Same page-level mode-scoped `st.chat_input` pattern routed to `handle_help_turn` (RUX-3). |
| Classic focus | Keep `classic_focus_run_id` as an optional run-id **string** (do **not** convert it to a dict). RQ-4 adds exactly one companion key `classic_focus_channel` whose only legal non-null v1 value is `"results_qa"` (`None`/absent = legacy). `discuss_run` / `set_classic_focus_run` set both; consume clears both atomically; thesis-scoped clear includes both. No other focus-key namespace. |
| Help corpus | Curated, versioned local docs + `FEATURE_PARITY_REGISTRY` summaries only — no web search, no arbitrary filesystem. RQ-0 ships the frozen path + section allowlist in §7.1 exactly (no agent-invented sections). No `AGENT_GUIDE` in v1 user Help. |
| Help numeric grounding | Digit tokens in Help `summary` / `caveats` / `followups` must appear as **matched number tokens** (same tokenizer as LLM evidence grounding) in the attached corpus chunk texts and/or registry digest JSON for that turn; else fail closed before persist/render. A reply token like `1` must not ride on a different corpus number such as `10`. Prefer number-free Help text. Never answer the user’s run performance from Help (remediate to Discuss results). |
| History trim | Per-channel `max_history_messages` under `[assistant.results_qa]` / `[assistant.product_help]` **overrides** top-level `[assistant].max_history_messages` when the channel section is present; else fall back to top-level. |
| Ranking metric (RQ-2) | Default ranking metric comes from the packet / `best_grid_result` recorded ranking metric (else the configured grid metric used when the grid was run), restricted to allowlisted aggregate **and directional** grid metrics; unknown names fall through to the next preference then `expectancy_r`. Optional side trade-count filters from `assumptions.grid` apply when present. JSON-null profit-factor on all-wins rows ranks as +inf; projection `best` pins packet `best_grid_result` when re-rank disagrees. The model must not choose the ranking metric. Empty authoritative `grid_results` tables fall back to packet `best_grid_result`. |
| Provider | Text stays on existing OpenAI structured client; no Anthropic/xAI in RQ PRs |
| Settings home | Prefer extending existing assistant settings loaders (`llm.py` / colocated style) over a new settings module unless loaders truly diverge |
| Voice | Out of series except that **RQ-1 satisfies VA-1**. VA-0/VA-2+ stay in the voice contract |
| Engine | No `simulate_trades`, levels, signals, validation-math, or golden fixture changes |
| Default availability | Config may default `enabled = true` for results/help; channels are usable only when `OPENAI_API_KEY` is configured. Without a key, UI remediates and deterministic Explain remains available. |

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
   Thesis draft hydration must ignore non-draft channels. `handle_chat_turn`
   history selection must exclude messages with `channel` set (additive filter
   only — not a prompt/schema rewrite).
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

Server resolves each `path` against the bound `EvidencePacket` (or, from RQ-2,
an ephemeral turn context / packet copy that includes `results.projections.*`),
attaches values, and runs the existing numeric grounding audit on that same
object. Paths are relative to the packet/turn-context root (not the outer
user JSON); leading `evidence_packet.` / `packet.` wrappers are stripped
repeatedly, and non-negative JSON array indices are valid path segments. Digit
tokens in `summary`, `caveats`, `claims[].text`, and `followups` must resolve
to cited claim values (or packet caveat echo rules for caveat lines); otherwise
fail closed before persist/render. Fractional rates may be narrated as `N%` /
`N %` or `N percent` / `N pct` / `N Prozent` (not as clock-like `H:MM percent`).
European decimal commas (`0,25`) ground as the cited float `0.25`; thousands
groups (`25,000`) are not treated as decimals. Prefer number-free `followups`.

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
the user’s runs. If the user asks about *their* results inside Help, the
UI/orchestrator must redirect to Discuss results (structured remediation), not
invent numbers.

**Help numeric grounding (locked):** Before persist/render, scan digit tokens in
`summary`, `caveats`, and `followups` with the same numeric-token regex family
as C2-6 / `llm_explainer` (including optional `%` suffixes). Every such token
must appear as a **matched number token** (same tokenizer / normalization) in
the concatenation of (a) corpus chunk `text` fields attached to that turn and
(b) the registry digest JSON string attached to that turn. A reply token like
`1` / `3` must not ride on a different corpus number such as `10` / `30`.
Tokens that fail are rejected (`HelpEvidenceError` or equivalent) — do not
silently strip and accept. Prefer number-free `followups`. Help has no
`claims[{path}]`; corpus/registry number-token match is the sole numeric ground.

### 5.3 Persistence

- Append to the active thesis conversation (same `Conversation` store).
- Filter history for each turn by `channel` (and `run_id` for results).
  Draft turns (`handle_chat_turn`) exclude any message with `channel` set.
- Trim with the channel’s `max_history_messages` when
  `[assistant.results_qa]` / `[assistant.product_help]` is present; otherwise
  fall back to top-level `[assistant].max_history_messages`.
- Do not set or widen `Conversation.selected_run_id` for RQ binding; results
  binding is message-level `run_id` (+ classic focus for navigation).
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

### 7.1 Allowlisted sources (v1) — frozen

RQ-0 must encode this table as the machine-readable manifest. Agents must **not**
add `doc_id`s, paths, or section titles beyond this freeze without amending this
contract in the same PR.

**Heading match rule (locked):**

1. Parse GitHub-flavored ATX headings (`#`…`######`).
2. `section` identity = heading text after stripping leading `#` markers and
   surrounding whitespace (exact string match; case-sensitive).
3. Allowlist keys below are **H2** titles (`## …`) unless `mode = whole_file`.
4. When an H2 is allowlisted, the chunk is that heading plus body until the next
   H2 or higher; nested H3+ content is included under the parent H2 key (H3s are
   not separately allowlisted).
5. `mode = whole_file` means every H2 in the file is eligible (plus any
   preface before the first H2 as `section = "__preface__"`).
6. Paths are resolved relative to the repository root; reject `..` and any path
   outside the allowlisted relative path after canonicalization.

| `doc_id` | Source path | Mode | Allowlisted H2 section titles (exact) |
|---|---|---|---|
| `readme` | `README.md` | `whole_file` | _(all H2s + `__preface__`)_ |
| `metrics` | `docs/METRICS_GLOSSARY.md` | `whole_file` | _(all H2s + `__preface__`)_ |
| `research_methodology` | `docs/research-methodology.md` | `whole_file` | _(all H2s + `__preface__`)_ |
| `architecture` | `docs/ARCHITECTURE.md` | `sections` | See exact H2 list in §7.1.1 (includes backtick characters in the session_state title) |
| `assumptions` | `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | `sections` | See exact H2 list in §7.1.2 |
| `otf` | `docs/otf-filter.md` | `sections` | See exact H2 list in §7.1.3 |
| `user_guide` | `docs/USER_GUIDE.md` | `sections` | See exact H2 list in §7.1.4 (HC-1…HC-3 filled how-tos; full §6.1 skeleton) |
| `registry` | _(generated; not a file path)_ | `digest` | Built at turn time from `FEATURE_PARITY_REGISTRY` / `audit_capability_registry()` as a JSON-safe list of `{capability_id, status, public_symbol?, confirmation?, limitation?}` only — no source files, no handler code |

#### 7.1.1 Exact `architecture` H2 titles (frozen)

Match these strings exactly after stripping the leading `##` and surrounding
whitespace (backticks around `st.session_state` are part of the heading text):

```text
AI Research Assistant contract boundary (AIA-0)
Classic ↔ Assistant navigation and identity badges (CAI-8)
Evidence-backed page capabilities (CAI-9)
End-to-end data flow
`st.session_state` contract (current)
```

#### 7.1.2 Exact `assumptions` H2 titles (frozen)

```text
Verified engine assumptions (current implementation)
6) Point-in-time correctness (R3 audit)
Validation implications
Futures roll methodology (R7)
AI Research Assistant / optional LLM (PR6 release gate)
Voice agent (VA-series — complete; default off)
OTF filter (One Timeframing)
Practical interpretation
```

#### 7.1.3 Exact `otf` H2 titles (frozen)

```text
Purpose
§1 — Concept
§2 — State vocabulary
§3 — State-transition rules
§4 — Configuration parameters
§5 — Supported higher timeframes
§6 — Completed-bar availability and look-ahead safety
§7 — Timezone and session alignment
§8 — Directional eligibility
§9 — Rejected signals
§13b — PR 5 Research-Mode Integration
§15 — Release-Gate Documentation
```

#### 7.1.4 Exact `user_guide` H2 titles (HC-1…HC-3 + HC-5/HC-6; amend via HC PRs)

Match these strings exactly after stripping the leading `##` and surrounding
whitespace. HC-3 completed the classic §6.1 skeleton; HC-5 adds **Exposure
policy**; HC-6 adds P0 settings depth H2s. Every USER_GUIDE H2 below is filled
and Help-readable.

```text
Purpose and honesty
Classic workflow overview
Data
Levels
Setup Builder
Signals
Backtest
Exposure policy
Intrabar resolution
Exit management (break-even and trailing)
Session close and entry cutoff
Grid Search
Time Analysis
Focus vs Admit
Validation and robustness
Report Export
Research Bundles
Portfolio
Research Assistant (draft, Discuss, Help)
Research mode on classic pages
Research Study Runner (headless)
Studies viewer (read-only)
When to use Help vs Discuss results
```

**Explicitly excluded from v1 (fail closed if requested):**

- `docs/AGENT_GUIDE.md` and any other operator/agent/CI runbook
- Architecture: packaging, CAI-1…CAI-7/CAI-10 store/export/ledger internals,
  R9–R22 engine-boundary sections not listed above
- OTF: `§10 — Regression safety`; `§11 — Output fields`;
  `§12 — Algorithm versioning and deterministic identity`;
  `§13 — Open questions (resolved for v1)`; and any “Historical PR …” /
  deferred-fingerprint subsections not under an allowlisted H2
- Assumptions H2s not listed above
- USER_GUIDE H2s not listed in §7.1.4

If a later PR widens Help, it must amend **this table** and the RQ-0 manifest
in the same PR.

### 7.2 Corpus rules

1. Load only §7.1 allowlisted paths under the repo root (canonicalized; reject
   `..` and non-allowlisted paths).
2. Chunk by heading using §7.1 match rules; attach
   `{doc_id, section, text}` **only** for allowlisted sections (or whole_file /
   `__preface__` as specified).
3. Cap total prompt bytes (`max_corpus_chars` in `[assistant.product_help]`).
4. Prefer `registry` digest over inventing feature support.
5. No network retrieval.
6. Citations in `HelpReply` must reference `{doc_id, section}` pairs that were
   actually attached to that turn (or `doc_id = "registry"` with
   `section = "digest"`).

---

## 8. Config contract

Additive keys only; do not reorder/rename existing `[assistant]` keys.

```toml
[assistant.results_qa]
# Text results discussion (RQ-1). Uses existing OpenAI client/settings.
# enabled=true is OK; runtime still requires OPENAI_API_KEY or UI remediates.
enabled = true
# Overrides top-level [assistant].max_history_messages for this channel.
max_history_messages = 12
# When true (RQ-2), allow RO TIME.analyze if time_grouped_summary missing.
allow_time_enrichment = false

[assistant.product_help]
# enabled=true is OK; runtime still requires OPENAI_API_KEY or UI remediates.
enabled = true
# Overrides top-level [assistant].max_history_messages for this channel.
max_history_messages = 12
max_corpus_chars = 24000
```

Secret resolution remains the existing OpenAI path. No new provider keys in RQ.
When a channel section is absent, loaders use safe defaults (`enabled=false` or
equivalent disabled behavior + top-level history trim) so missing TOML never
widens surface area unexpectedly.

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
| Code | `thesistester/assistant/help_corpus.py` — encode §7.1 path + section allowlist + heading match rules as pure loaders/chunkers; **no orchestrator wiring**; refuse `AGENT_GUIDE`, non-allowlisted paths, and non-allowlisted H2s |
| Code | Settings loaders for the two new blocks (missing section → disabled/safe defaults; present section uses §8 values including per-channel history override) — **prefer extending** `llm.py` / existing assistant settings style; add a separate module only if loaders truly diverge |
| Code | Optional pure helpers for draft-channel message filtering (e.g. `is_draft_channel_message`) usable by RQ-1; no orchestrator behavior change required in RQ-0 |
| Tests | Manifest equals §7.1 freeze; path/section safety (`..` rejected; `AGENT_GUIDE` rejected; architecture `Packaging and tooling boundary (R9)` rejected; otf `§10 — Regression safety` rejected; allowlisted H2 accepted); default settings; `load_llm_settings()` still succeeds with new sections |

#### Out of scope
- Any call to OpenAI / UI chat widgets / orchestrator methods
- `results_qa.py` / `product_help.py` reply loops
- Session_state keys beyond documenting reserved names
- Loading `docs/AGENT_GUIDE.md` into the Help corpus
- Widening §7.1 beyond the frozen table

#### Acceptance
- [ ] New config sections parse; missing sections → safe defaults (channel disabled)
- [ ] Help corpus loader encodes §7.1 exactly; refuses non-allowlisted paths/sections
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
thesistester/assistant/llm.py                  # preferred: additive settings loaders / helpers
tests/test_assistant_help_corpus.py
tests/test_assistant_qa_settings.py
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/ENGINEERING_ROADMAP.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ARCHITECTURE.md
docs/AGENT_GUIDE.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md    # VA-1 ownership note only
```

#### Implemented contract
- `config/assistant.toml` ships `[assistant.results_qa]` and
  `[assistant.product_help]` per §8.
- `load_results_qa_settings` / `load_product_help_settings` in
  `thesistester/assistant/llm.py`: missing section → `enabled=False` +
  top-level history fallback; present section applies per-channel overrides.
  Channel `enabled` / `allow_time_enrichment` flags fail closed on non-boolean
  spellings (e.g. the string `"false"` does not enable a channel).
- `thesistester/assistant/help_corpus.py` encodes §7.1 / §7.1.1–§7.1.3
  (path + section allowlist, heading match rules, registry digest helper).
  Whole-file `__preface__` is content before the first H2 (includes H1 title
  blocks); H2 bodies end at the next H2 or higher; section-mode docs still omit
  preface unless explicitly allowlisted. Resolved paths must match the
  allowlisted relative location (symlink smuggling of excluded docs fails closed).
- `is_draft_channel_message` helper lands for RQ-1 (no orchestrator wiring yet):
  missing/`None` channel → draft; any set channel value (including `""`) →
  non-draft.
- Tests: `tests/test_assistant_help_corpus.py`,
  `tests/test_assistant_qa_settings.py`.

---

### RQ-1 — Multi-turn results Q&A (implements VA-1)

**Goal:** Ship grounded multi-turn discussion of a completed run in text.
This PR **is** VA-1.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/results_qa.py` — `propose_results_reply(client, *, packet, history, user_message) -> ResultsQAReply` with schema in §5.2 |
| Code | System prompt: evidence-only; no trade advice; no calculations beyond packet; distinguish IS vs robustness; ask follow-ups when evidence missing |
| Code | Grounding via `assert_llm_explanation_grounded` or shared helper extracted from `llm_explainer.py` (extract only if required; do not fork rules). Extend grounding to cover `followups` digit tokens (§1 / §5.2). |
| Code | `AssistantOrchestrator.handle_results_turn(thesis_id, run_id, message, *, conversation_id=..., client=...)` — `get_run` → hash-verified evidence (existing explain/`BUNDLE.import` evidence path) → `propose_results_reply` → persist user+assistant messages with `"channel": "results_qa"` and `"run_id"`; assistant message omits `choices` |
| Code | History trim filtered by `channel` + `run_id` using the channel’s `max_history_messages` override |
| Code | **Additive draft history isolation:** `handle_chat_turn` message selection excludes messages with `channel` set and channel-less `role: tool` audit lines (user/assistant draft turns only); page draft hydration ignores non-draft channels. This is history filtering only — do **not** rewrite the draft prompt text or `choices` schema. Persisted results assistant `content` includes path-cited Claims; thesis-scoped clearing must drop `assistant_results_qa_drafts` and `results-qa-input-*` widget keys. |
| UI | Inside each completed-run expander in `pages/14_Research_Assistant.py` (beside Explain / LLM explain): **Discuss results** with keyed `st.text_input` + send button — **no mic**, no nested `st.chat_input`; do not replace thesis-draft `st.chat_input` |
| Session keys | Additive cache keys if needed, e.g. `assistant_results_qa_drafts` — document in `ARCHITECTURE.md` + `ASSISTANT_SESSION_KEYS`; clear appropriately on thesis switch |
| Tests | `tests/test_assistant_results_qa.py` + extend `tests/test_assistant_llm_evaluations.py`: injection → no `execute_confirmed_run` / no `PIPELINE.*`; RO `BUNDLE.import` allowed; uncited numbers rejected (incl. followups); missing run; hash mismatch; history trim by channel+run_id; draft history excludes tagged channels; `handle_chat_turn` still never loads bundles; results messages omit `choices` |
| Docs | Mark VA-1 Implemented contract in the voice doc; mark RQ-1 implemented here; update `ARCHITECTURE.md` / `ASSUMPTIONS_AND_LIMITATIONS.md` / `AGENT_GUIDE.md` |

#### Out of scope
- xAI, audio, STT/TTS, WebSockets
- Product help channel
- `results_projections` / `TIME.analyze` enrichment (RQ-2)
- Classic deep-link binding (RQ-4)
- Rewriting thesis-draft `handle_chat_turn` prompt text or `choices` schema (history filter is in scope)
- Rewriting deterministic `explain_evidence_report` templates (call them; don’t rewrite)
- Nested `st.chat_input` for Discuss results

#### Acceptance
- [x] `handle_results_turn` never calls `execute_confirmed_run` and never dispatches `PIPELINE.*` / mutators (asserted). RO `BUNDLE.import` (action `evidence`) allowed
- [x] Uncited numeric token (including in `followups`) → error before UI persistence/render
- [x] Hash mismatch → structured failure; no packet leak
- [x] Without provider key, deterministic explain still works; results Q&A surfaces clear remediation (`enabled=true` alone is insufficient without a key)
- [x] `handle_chat_turn` excludes `channel`-tagged messages from history; draft hydration ignores non-draft channels; prior draft fixtures remain green
- [x] Persisted results assistant messages omit `choices`
- [x] User can ask “best SL/TP?” and “expectancy?” against a fixture packet and receive path-cited claims when those fields exist

#### Regression safety
New orchestrator method + optional UI block + additive draft history filter.
Thesis drafting semantics and one-shot `explain_run_with_llm` keep prior
contracts when only draft messages exist. No engine/golden changes.

#### Files allowed to touch
```
thesistester/assistant/results_qa.py
thesistester/assistant/orchestrator.py          # handle_results_turn + additive draft history filter in handle_chat_turn
thesistester/assistant/repository.py            # only if message tag helpers needed
thesistester/assistant/llm_explainer.py         # shared grounding helper extract only if required (incl. followups)
thesistester/assistant/llm.py                   # only if channel settings helpers needed
thesistester/assistant/workspace.py             # session keys / formatters / draft hydration filter
thesistester/assistant/__init__.py              # exports
pages/14_Research_Assistant.py                  # expander Discuss results (text_input+button) + draft hydration filter
tests/test_assistant_results_qa.py
tests/test_assistant_llm_evaluations.py
tests/test_assistant_workspace.py               # only if new session keys / hydration filter
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md     # VA-1 implemented contract
docs/AGENT_GUIDE.md
docs/ENGINEERING_ROADMAP.md                     # status note
```

#### Implemented contract
- `thesistester/assistant/results_qa.py` — `propose_results_reply`, history filter,
  reply formatting; channel tag `results_qa`
- `AssistantOrchestrator.handle_results_turn` — `explain_run` / RO `BUNDLE.import`
  evidence → grounded reply → persist `channel`+`run_id` messages (no `choices`)
- `handle_chat_turn` + page hydration / thesis chat display ignore non-draft channels
- `assert_llm_explanation_grounded(..., followups=())` covers followup digit tokens
- UI: Discuss results in completed-run expander via keyed `st.text_input` + send
- Session key: `assistant_results_qa_drafts` (thesis-scoped)
- Tests: `tests/test_assistant_results_qa.py` + evaluation/workspace extensions
- VA-1 satisfied by this PR (voice series may proceed to VA-2+)

---

### RQ-2 — Deterministic rankings & optional time enrichment

**Goal:** Make the two highest-value trader questions first-class and reliable:
best entry time and best SL/TP — without letting the LLM invent rankings.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/results_projections.py` — pure functions: `project_grid_rankings(packet_or_grid, *, top_n, metric)` and `project_time_rankings(time_grouped_summary, *, bucket_col, metric, min_trades)` returning JSON-safe tables with stable paths. `resolve_time_bucket_col` prefers the requested bucket column when it has a usable non-null label, else falls back through `entry_rth_segment` → `entry_30min_bucket` → `entry_hour_bucket` so Time Analysis clock-bucket exports still produce a non-null `best.bucket`. |
| Code | Default `metric` for grid rankings: packet / `best_grid_result` recorded ranking metric, else the configured grid metric from assumptions when the grid was run. **Do not** let the LLM choose the ranking metric. |
| Code | Merge projections into an **ephemeral** results-turn context under `results.projections.*` (packet copy / turn-only object). Grounding path resolution and number audit must use that same extended object. Must not mutate on-disk bundles. |
| Code | When `assistant.results_qa.allow_time_enrichment = true` **and** `time_grouped_summary` missing, `handle_results_turn` may dispatch RO `TIME.analyze` on the bound bundle, then project rankings; audit one tool-transcript entry; fail closed on hash/provenance errors |
| Code | Prompt/tooling guidance so “best” language must state metric, candidate set, min-trades filter, and IS vs OOS status (mirror explainer honesty) |
| Tests | Ranking determinism; empty/missing inputs; metric default source; enrichment flag off → no `TIME.analyze`; flag on + missing time → RO analyze once; never `PIPELINE.*`; grounding accepts projection paths only on the ephemeral context |
| Docs | Document projection paths + enrichment flag in `ARCHITECTURE.md` / assumptions |

#### Out of scope
- Product help
- Sending full `trades` frames to the LLM
- Changing grid/time analytics formulas
- UI redesign beyond showing projection-backed claims already returned by RQ-1
- Persisting projections into research bundles

#### Acceptance
- [x] Fixture with grid → “best SL/TP” cites projection/best_grid paths and the recorded/default ranking metric (not model-chosen)
- [x] Fixture with time summary → “best entry window” cites ranked bucket + sample size / warnings
- [x] Enrichment default remains `false`; enabling it is explicit
- [x] No bundle bytes rewritten; grounding walks the ephemeral extended context only

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

#### Implemented contract
- `thesistester/assistant/results_projections.py` — `project_grid_rankings`,
  `project_time_rankings`, `build_ephemeral_results_context`,
  `resolve_grid_ranking_defaults`
- Ephemeral paths: `results.projections.grid_rankings.*` /
  `results.projections.time_rankings.*` (plus optional
  `results.time_grouped_summary` when enriched/present)
- Grid metric defaults from `best_grid_result.ranking_metric` else
  `assumptions.grid.ranking_metric` else `expectancy_r` (never model-chosen)
- `handle_results_turn` merges projections into turn context; when
  `allow_time_enrichment=true` and time summary missing, RO `TIME.analyze`
  once after hash verification (audited); default config remains `false`
- `propose_results_reply(..., turn_context=)` grounds claims against the
  ephemeral context; bundles are never rewritten
- Tests: `tests/test_assistant_results_projections.py` + results_qa extension

---

### RQ-3 — Product / how-it-works help channel

**Goal:** Answer feature and workflow questions from curated docs + registry,
without mixing in run performance claims.

#### In scope
| Item | Detail |
|---|---|
| Code | `thesistester/assistant/product_help.py` — `propose_help_reply(client, *, corpus_chunks, registry_digest, history, user_message) -> HelpReply` |
| Code | `AssistantOrchestrator.handle_help_turn(thesis_id, message, *, conversation_id=..., client=...)` — load corpus via `help_corpus.py` (§7.1 only), build registry digest, call product_help, persist with `"channel": "product_help"`, omit `choices` |
| Code | Intent guard: if message clearly asks for *this run’s* performance numbers (concrete metric nouns / past-tense run asks / run-anchored results), return structured remediation pointing to Discuss results (no fabricated metrics). Do **not** remediate possessive product nouns alone (`my grid`, `this run` in workflow questions), vague export/workflow phrasing (`where are my results?`), or definition/computation asks about metric nouns (`How is my expectancy computed?`, `What does this performance metric mean?`). Definition escape uses compute/define/mean collocates only — not bare `docs`/`metric` — and yields to strong run anchors (`what was/were my`, `on this run`). |
| Code | Enforce §5.2 Help numeric grounding (number-token match in attached corpus/registry; fail closed on uncited digit tokens) |
| UI | Research Assistant Help panel (collapsed expander or tab sibling to chat hub) with keyed `st.text_input` + send button; do not reuse thesis `st.chat_input`; no nested `st.chat_input` |
| Session keys | Additive help draft/cache keys if needed; document + thesis-scope clear as appropriate |
| Tests | §7.1 path/section allowlist; citation must reference attached chunks; digit-token grounding; performance-question remediation; no bundle import; no `choices`; history trim by channel; `AGENT_GUIDE` never loaded |
| Docs | Assumptions note: help is documentation-grounded, not a second results explainer |

#### Out of scope
- Results packet loading
- Voice
- Editing product docs for marketing tone (content edits only if a citation target is wrong/ambiguous)
- Web search / external URLs as required citations
- Shipping `docs/AGENT_GUIDE.md` (or other agent/CI internals) through Help
- Widening §7.1 allowlist

#### Acceptance
- [x] “How does grid ranking work?” returns citations to §7.1-allowlisted glossary/architecture/registry only
- [x] “What was my best SL?” in Help → remediation to Discuss results, no numbers
- [x] Uncited digit token in Help summary/caveats/followups → error before persist/render
- [x] Non-allowlisted doc paths and sections never load
- [x] Thesis draft chat fixtures unchanged

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

#### Implemented contract
- `thesistester/assistant/product_help.py` — `propose_help_reply`,
  `is_run_performance_question` / remediation, digit-token grounding,
  history filter, `channel=product_help`
- `help_corpus.select_help_corpus_chunks` — lexical retrieval under §7.1 +
  `max_corpus_chars` (no network; no `AGENT_GUIDE`)
- `AssistantOrchestrator.handle_help_turn` — corpus + registry digest → reply →
  persist messages without `choices`; never bundle import / `PIPELINE.*`
- UI: Help / how it works expander (`st.text_input` + send) sibling to thesis chat
- Session key: `assistant_product_help_draft` (thesis-scoped)
- Tests: `tests/test_assistant_product_help.py` + help_corpus/workspace extensions

---

### RQ-4 — Classic entry points & UX polish

**Goal:** Make Discuss results reachable from the classic research loop with the
correct run binding.

#### Frozen focus shape (do not re-litigate)

| Key | Type | Semantics |
|---|---|---|
| `classic_focus_run_id` | optional `str` | **Unchanged.** Non-empty run id string to focus; never a dict/object. |
| `classic_focus_channel` | `"results_qa"` or `None` | **RQ-4 additive companion.** Only legal non-`None` v1 value is `"results_qa"`. `None`/absent = legacy Discuss behavior (thesis alignment + run focus banner only). |

Rules:

1. Do **not** replace `classic_focus_run_id` with a structured payload.
2. Do **not** invent any other focus-key namespace (`assistant_focus_*`, etc.).
3. `discuss_run` / `set_classic_focus_run` must set `classic_focus_run_id` and
   `classic_focus_channel = "results_qa"` together.
4. Consume must clear **both** keys atomically (extend
   `consume_classic_focus_run` or add a thin wrapper that returns
   `{run_id, channel}` while still nulling both).
5. Add `classic_focus_channel` to `CLASSIC_SESSION_KEYS` and
   `CLASSIC_THESIS_SCOPED_KEYS` in `classic_context.py` so thesis
   switch/exit clears it with the existing run focus.

#### In scope
| Item | Detail |
|---|---|
| Code | Implement the frozen focus shape above in `classic_nav.py` + `classic_context.py`; wire `discuss_run` to set both keys |
| UI | Research Assistant consumes `{classic_focus_run_id, classic_focus_channel}` on load: when channel is `results_qa`, preselect **Discuss runs** + that run’s Discuss results thread **and** force-open Advanced → Linked-run expanders; when channel is absent/`None`, keep legacy banner/thesis focus behavior |
| UI | Copy clarity: thesis chat caption remains “draft only”; Discuss results / Help labeled distinctly |
| Pages | `pages/7_Backtest.py`, `pages/12_Research_Bundles.py` (and Grid/Time only if a discuss affordance already exists or is a one-line reuse of the helper) |
| Tests | Focus pair shape; atomic clear; thesis switch clears both; unknown channel values fail closed or coerce to legacy (`None`); no `choices` hydration from results focus |
| Docs | `ARCHITECTURE.md` documents `classic_focus_channel` beside `classic_focus_run_id` |

#### Out of scope
- New classic analytics
- Auto-running grid/time from classic pages
- Voice mic entry
- Converting `classic_focus_run_id` to a dict/object
- Any focus key other than `classic_focus_run_id` + `classic_focus_channel`

#### Acceptance
- [x] From a ledger-backed classic run, Discuss sets both keys and Assistant opens results channel for that `run_id`
- [x] Absent/`None` `classic_focus_channel` preserves legacy Discuss navigation
- [x] Thesis switch/exit clears both focus keys
- [x] Draft chat does not absorb results history

#### Regression safety
Navigation/focus only. Engine and compute paths untouched.
`classic_focus_run_id` string semantics preserved for existing consumers.

#### Files allowed to touch
```
thesistester/classic_nav.py
thesistester/classic_context.py                 # CLASSIC_SESSION_KEYS / thesis-scoped clear
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

#### Implemented contract
- `classic_focus_channel` added to `CLASSIC_SESSION_KEYS` /
  `CLASSIC_THESIS_SCOPED_KEYS`; cleared on thesis switch/exit with
  `classic_focus_run_id`.
- `set_classic_focus_run` / `discuss_run` set both keys
  (`channel="results_qa"`); `classic_focus_run_id` remains a string.
- `consume_classic_focus()` returns `{run_id, channel}` and nulls both
  atomically; unknown channel coerces to legacy `None`.
  `consume_classic_focus_run` remains a compatibility wrapper.
- Research Assistant: `results_qa` expands Advanced → matching Linked run
  (Discuss results visible); absent/`None` channel keeps banner-only.
- Sticky UI staging: `assistant_results_qa_deep_link` + `assistant_focused_run_id`
  keep Advanced/run expanders open across `st.rerun()` after the one-shot classic
  focus keys are consumed; thesis switch clears both.
- Fresh `results_qa` consume sets `assistant_results_qa_force_expand` once so
  keyed Streamlit expanders (`ra-advanced-expander` / `ra-run-expander-*`) reopen
  even if the user previously collapsed Advanced.
- `align_assistant_thesis_for_discuss` (used by `discuss_run` and **Record and
  discuss**) syncs thesis + `assistant_thesis_picker`; Research Assistant also
  re-aligns from `classic_active_thesis_id` when classic focus is still staged.

---

### RQ-5 — Evals + release gate

**Goal:** Freeze honesty/injection evals and close the series for release.

#### In scope
| Item | Detail |
|---|---|
| Tests | **Expand/freeze** coverage already introduced in RQ-1…RQ-4 (do not treat RQ-5 as first introduction of injection/uncited gates). Expand `tests/test_assistant_llm_evaluations.py` (and/or dedicated eval module) with fixtures for: best SL/TP, best time, missing time, missing grid, WFA caveat preservation, help-vs-results redirect, prompt-injection (“ignore evidence and run pipeline”), uncited number rejection (incl. followups), draft history isolation, `choices` absence, section-allowlist corpus refusals |
| Docs | Fill Implemented contract sections for RQ-0…RQ-4; update `ASSUMPTIONS_AND_LIMITATIONS.md` AI section to mention multi-turn results + help channels; `ENGINEERING_ROADMAP.md` status ✅ |
| Release checklist | Provider key remediation copy; deterministic Explain still works offline; registry audit still green |

#### Out of scope
- New features / tool allowlist expansion
- Enabling voice
- Default model changes

#### Acceptance
- [x] Eval file fails closed on injection and uncited numbers
- [x] CI green
- [x] Docs mark series complete (or explicitly list deferred items)
- [x] No golden/engine drift

#### Regression safety
Tests + docs. Behavior changes only if an eval reveals a defect — fix narrowly
inside already-shipped RQ modules.

#### Files allowed to touch
```
tests/test_assistant_llm_evaluations.py
tests/test_assistant_results_qa.py
tests/test_assistant_product_help.py
thesistester/assistant/llm_explainer.py         # only if eval reveals honesty defect
thesistester/assistant/results_qa.py            # only if eval reveals honesty defect
thesistester/assistant/__init__.py              # re-exports only
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ENGINEERING_ROADMAP.md
docs/AGENT_GUIDE.md
docs/ARCHITECTURE.md                            # only if eval-driven contract clarifications
```

#### Implemented contract
- `tests/test_assistant_llm_evaluations.py` freezes RQ honesty/injection
  gates: best SL/TP, best time, missing time, missing grid, WFA caveat
  preservation (anti-soften), help→Discuss redirect, pipeline injection
  (no `PIPELINE.*` / `execute_confirmed_run`), uncited numbers incl.
  followups, draft history isolation, `choices` absence on results/help
  messages, §7.1 section-allowlist corpus refusals (incl. `AGENT_GUIDE`).
- Eval-driven honesty fix (narrow): `merge_mandatory_packet_caveats` in
  `llm_explainer` / `results_qa` / one-shot explain so packet caveats cannot
  be omitted; `assert_llm_explanation_grounded` rejects OOS/WFA soften
  language when packet codes `missing_oos` / `failed_oos` are present.
- Release checklist covered in the same eval file: provider-key remediation
  copy (`Set OPENAI_API_KEY to a rotated credential.`), deterministic
  `explain_evidence` offline, `audit_capability_registry` has no `invalid`
  rows.
- Deferred (explicit): voice (VA-series), default model changes, tool
  allowlist expansion — see §12 non-goals.

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
| Results/help history leaks into thesis draft | Additive `handle_chat_turn` filter excludes `channel`-tagged messages; page hydration ignores non-draft; tests in RQ-1/RQ-5 |
| Results messages hydrate draft `choices` | Persist without `choices`; page hydration filters draft channel only; tests |
| Nested `st.chat_input` breaks page input | v1 freezes keyed `st.text_input` + send button for Discuss/Help |
| Help channel answers performance questions badly | Explicit remediation to Discuss results; eval fixture |
| Help invents numbers not in docs | §5.2 verbatim corpus/registry digit grounding; fail closed |
| Help exposes agent/CI internals | Frozen §7.1 section allowlist; `AGENT_GUIDE` excluded |
| Optional `TIME.analyze` becomes hidden compute | Default `allow_time_enrichment=false`; audit transcript; RO only |
| Model picks ranking metric | RQ-2 freeze: packet/recorded/configured metric only |
| Prompt injection (“run the pipeline”) | Eval suite; orchestrator allowlist; no tools exposed to results/help LLM in v1 beyond server-side RO import/enrichment |
| Corpus drift / wrong citations | Frozen §7.1 table + heading match rules; prefer glossary/registry |
| Scope creep into voice | VA ownership note; RQ PRs reject audio/xAI files |
| Focus shape drift | RQ-4: keep string `classic_focus_run_id`; sole companion `classic_focus_channel` |

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

## 15. Suggested copy-ready agent prompts

Agents must work regression-safe and update docs in the same PR.

### 15.1 RQ-0

```markdown
Implement RQ-0 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- Contracts/config/corpus manifest only. No OpenAI calls, UI chat widgets, or orchestrator reply loops.
- Follow the PR’s Files allowed to touch list. Prefer extending thesistester/assistant/llm.py for settings loaders.
- Add help_corpus.py encoding §7.1 / §7.1.1–§7.1.3 exactly (paths, whole_file vs sections, exact H2 title strings, heading match rules, registry digest shape). Reject `..`, AGENT_GUIDE, and any H2 not listed (e.g. architecture "Packaging and tooling boundary (R9)"; otf "§10 — Regression safety").
- Do not invent extra doc_ids or section titles beyond §7.1.
- Add [assistant.results_qa] and [assistant.product_help] to config/assistant.toml exactly as §8.
- Missing TOML sections → channel disabled / safe defaults. Present sections use per-channel max_history_messages override semantics.
- Optional: pure is_draft_channel_message (or equivalent) helper for RQ-1; no behavior change to handle_chat_turn yet.
- Same-PR docs per RQ-0 scope, including VA-1 ownership note in REALTIME_VOICE_AGENT_IMPLEMENTATION.md.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green. No new third-party dependency.
```

### 15.2 RQ-1 (after RQ-0)

```markdown
Implement RQ-1 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- You are implementing VA-1 / RQ-1 only. No voice, no product help, no TIME.analyze enrichment.
- Follow the PR’s Files allowed to touch list. Do not modify engine, levels, signals, or goldens.
- Add thesistester/assistant/results_qa.py and AssistantOrchestrator.handle_results_turn.
- Additive draft history isolation: handle_chat_turn must exclude messages with channel set; page draft hydration must ignore non-draft channels. Do not rewrite draft prompt text or choices schema.
- Ground all numeric claims (including followups) with existing llm_explainer rules; fail closed on uncited numbers.
- Persist messages with channel=results_qa and run_id; omit choices on assistant messages. Do not set Conversation.selected_run_id for RQ binding.
- UI: Discuss results inside completed-run expander only; keyed st.text_input + send button; no nested st.chat_input; do not replace thesis st.chat_input.
- Without OPENAI_API_KEY, remediate clearly; deterministic Explain still works.
- Tests: tests/test_assistant_results_qa.py + extend test_assistant_llm_evaluations.py per the contract acceptance list.
- Same-PR docs: ARCHITECTURE.md, ASSUMPTIONS_AND_LIMITATIONS.md, AGENT_GUIDE.md, mark VA-1 + RQ-1 implemented contracts.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green.
```

### 15.3 RQ-3 (after RQ-0 + shared channel helpers from RQ-1)

```markdown
Implement RQ-3 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- Product/help channel only. No results packet loading, no voice, no AGENT_GUIDE corpus, no §7.1 widening.
- Follow the PR’s Files allowed to touch list. Do not modify engine, levels, signals, or goldens.
- Add product_help.py and AssistantOrchestrator.handle_help_turn over help_corpus §7.1 allowlist + registry digest.
- Intent guard: run-performance questions → structured remediation to Discuss results (no fabricated numbers).
- Enforce Help numeric grounding (§5.2): every digit token in summary/caveats/followups must be a matched number token in attached corpus texts or registry digest JSON; else fail closed.
- Citations must reference doc_id/section pairs actually attached (registry uses section="digest").
- UI: Help panel with keyed st.text_input + send button; do not reuse thesis st.chat_input.
- Persist channel=product_help; omit choices; trim history by channel using product_help max_history_messages.
- Tests per RQ-3 acceptance; thesis draft fixtures unchanged.
- Same-PR docs per RQ-3 scope.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green.
```

### 15.4 RQ-2 (after RQ-1)

```markdown
Implement RQ-2 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- Deterministic rankings + optional RO TIME.analyze only. No product help, no voice, no bundle mutation.
- Follow the PR’s Files allowed to touch list. Do not modify engine, levels, signals, goldens, or grid/time formulas.
- Add results_projections.py: project_grid_rankings / project_time_rankings with stable JSON-safe paths.
- Default grid ranking metric = packet/best_grid_result recorded metric, else configured grid metric from assumptions. Model must not choose the metric.
- Merge projections only into an ephemeral turn context under results.projections.*; grounding audits that same object.
- allow_time_enrichment default false; when true and time_grouped_summary missing, RO TIME.analyze once + audit transcript; never PIPELINE.*.
- “Best” language must state metric, candidate set, min-trades, IS vs OOS status.
- Tests per RQ-2 acceptance.
- Same-PR docs per RQ-2 scope.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green.
```

### 15.5 RQ-4 (after RQ-1; prefer after RQ-2)

```markdown
Implement RQ-4 from docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md exactly.

Constraints:
- Classic Discuss → results-channel binding only. No new analytics, no voice, no focus-key invention beyond the freeze.
- Follow the PR’s Files allowed to touch list.
- Keep classic_focus_run_id as a string. Add companion classic_focus_channel with only legal non-None value "results_qa".
- discuss_run / set_classic_focus_run set both keys; consume clears both atomically; add classic_focus_channel to CLASSIC_SESSION_KEYS and CLASSIC_THESIS_SCOPED_KEYS.
- Research Assistant: when channel is results_qa, preselect Discuss runs + that run’s Discuss thread and keep Advanced/Linked-run force-open; None/absent channel keeps legacy behavior.
- Do not convert classic_focus_run_id into a dict. Do not add assistant_focus_* keys.
- Tests: pair shape, atomic clear, thesis switch clears both, legacy path preserved, no choices hydration.
- Same-PR docs: ARCHITECTURE.md documents classic_focus_channel.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green.
```

---

## 16. Status ledger

| ID | Status |
|---|---|
| RQ-0 | Implemented |
| RQ-1 (VA-1) | Implemented |
| RQ-2 | Implemented |
| RQ-3 | Implemented |
| RQ-4 | Implemented |
| RQ-5 | Implemented (series complete) |
