# Realtime Voice Agent — Codebase Reassessment

**Date:** 2026-08-04  
**Against:** `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` vs current `main`-line assistant code  
**Verdict:** Keep the series shape (VA-0→VA-6, text before speech, default-off, RO tools).  
Amend several contracts before VA-0 merges; VA-5 needs a transport decision rewrite or it will stall.

---

## 1. What is already strong (keep)

| Strength | Evidence |
|---|---|
| Evidence-bound + hash fail-closed | Matches `explain_run` / `compare_completed_runs` / `require_run_bundle_hash` |
| No engine / golden touch | Aligns with `ENGINEERING_PROPOSAL.md` §4 and `AGENT_GUIDE.md` |
| Default-off + secrets server-side | Matches C2-6 credential pattern intent |
| Text substrate before speech (VA-1 before VA-4) | Correct; C2-6 grounding exists to reuse |
| Narrow file allowlists + regression paragraph | Matches §4.2 / assistant PR culture |
| VA-3 deny list includes `web_search` / `x_search` / compute | xAI session tools *do* support those; explicit deny is load-bearing |
| Dependency graph VA-1 ∥ VA-2 after VA-0 | Sound |
| C2-6 eval suite as precedent | `tests/test_assistant_llm_evaluations.py` is the right template for VA-6 |

---

## 2. Plan vs reality mismatches (must-fix)

### 2.1 `handle_results_turn` cannot “never call `dispatch`”

**Plan (VA-1 Acceptance):** asserts `handle_results_turn` never calls `dispatch` / `execute_confirmed_run`.

**Reality:** Loading a completed run’s evidence goes through
`AssistantOrchestrator.explain_run` → `dispatch(AssistantRequest(capability_id="BUNDLE.import", …))`
(`orchestrator.py` ~1088–1128). Chat’s “never dispatch” invariant
(`handle_chat_turn`, C2-6) is special because chat is non-executing and
bundle-free. Results Q&A **must** import evidence.

**Fix:** Acceptance = never call `execute_confirmed_run`, never dispatch
`PIPELINE.*` / mutators / export / portfolio; **allow** read-only
`BUNDLE.import` (action `evidence`) and existing compare path. Tests should
monkeypatch and assert capability allowlist, not `dispatch.assert_not_called()`.

### 2.2 Secrets resolution shape is wrong / incomplete

**Plan §4:** `XAI_API_KEY` env first, else Streamlit Secrets `[xai].api_key`.

**Reality (`llm.py` `require_openai_api_key`):** env → Secrets **top-level**
`OPENAI_API_KEY` → nested `[openai].api_key`; placeholders rejected.

**Fix:** Mirror exactly: env `XAI_API_KEY` → Secrets `XAI_API_KEY` →
`[xai].api_key`; define `_XAI_API_KEY_PLACEHOLDER` and reject it. Document in
VA-0/VA-2.

### 2.3 Repository has no voice-session store; ID regex cannot hold `voice_*`

**Plan VA-2:** `VoiceSessionService.create_session` “persists `VoiceSessionRecord`”;
`repository.py` optional.

**Reality:**
- `ASSISTANT_REPOSITORY_SCHEMA_VERSION = 1` with **exact** field sets
  (`_require_fields`); no voice kind.
- `_ID_RE` only allows `th_|run_|conv_` (`repository.py` L25).
- Conversations already have append-only `messages` + `tool_transcript`
  (`append_conversation_message`); message dicts are JSON-validated but
  **not** field-locked — additive tags like `"channel": "results_qa"` need
  **no** schema bump.

**Fix (freeze in VA-0):**
1. Persist voice sessions as **new files** under
   `assistant/theses/{thesis_id}/voice_sessions/{session_id}.json` with
   `kind: "voice_session"` and either bump store marker rules or keep
   conversation schema at v1 and treat voice as additive sibling docs
   (prefer sibling docs; do not widen Conversation fields).
2. Define `session_id` format explicitly (e.g. `vs_` + 32 hex) and extend
   validation only for that store — do **not** reuse `_ID_RE` as-is.
3. Prefer flushing transcripts via existing
   `append_conversation_message(..., tool_entry=...)` rather than inventing a
   second audit channel.

### 2.4 Dual-provider dependency for VA-4 is unspecified

**Plan VA-4 flow:** STT/TTS on xAI, reply via `handle_results_turn` (OpenAI
`StructuredLLMClient` / `results_qa`).

**Reality:** Thesis chat + LLM explain use OpenAI only (`config/assistant.toml`
`provider = "openai"`, `create_openai_client`). PTT therefore needs
**both** `OPENAI_API_KEY` and `XAI_API_KEY` unless redesigned.

**Fix:** State explicitly in VA-4:
- Option A (default): PTT requires both keys; remediation message lists both.
- Option B (preferred for fewer secrets): PTT answer path = VA-3 tools +
  deterministic/`get_run_overview` text → xAI TTS only (no OpenAI). Keep
  OpenAI `handle_results_turn` for the **text** “Discuss results” expander.

### 2.5 Streamlit UI attachment points need concrete contracts

**Page reality (`pages/14_Research_Assistant.py`):**
- Thesis drafting already owns main-body `st.chat_input` (~L261).
- Completed-run UX lives inside per-run `st.expander` under “Research runs”
  (~L1182+), beside Explain / LLM explain / export — **this** is the attach
  point for Discuss results / Voice.
- Streamlit 1.60 (repo pin `>=1.56,<2`) allows nested/multiple `chat_input`
  and has `st.audio_input` (default **16 kHz**) plus
  `st.chat_input(..., accept_audio=True)`.
- Page contract tests (`tests/test_assistant_workspace.py`) stub Streamlit
  and AST-scan the page; new widgets must be added to the stub list
  (`audio_input`, `audio`) or tests break.
- Undocumented session keys already used on the page:
  `assistant_focused_run_id`, `assistant_page_summaries` — existing drift vs
  `ASSISTANT_SESSION_KEYS` / `ARCHITECTURE.md`.

**Fix:**
- VA-1: pin UI to completed-run expander; use keyed nested `st.chat_input`
  **or** `st.text_input`+button (document choice). Do not replace thesis chat.
- VA-4: pin `st.audio_input` sample_rate vs xAI STT expectations; note 16 kHz
  default vs realtime PCM 24 kHz (VA-5).
- VA-4/VA-1: extend workspace stub + `ASSISTANT_SESSION_KEYS` /
  `THESIS_SCOPED_STAGING_KEYS` for any `assistant_voice_*` / results-QA staging;
  clear voice session keys on thesis switch.
- Nice-to-have: fold undocumented page keys into `ASSISTANT_SESSION_KEYS` in a
  non-VA cleanup PR (do not block VA).

### 2.6 Grounding helper split will drift from C2-6

**Reality:** Grounding lives in private helpers inside
`llm_explainer.py` (`_NUMBER_RE`, `_token_grounded`,
`assert_llm_explanation_grounded`) with percent↔fraction and caveat-echo
rules. Plan adds `voice/grounding.py::audit_transcript_numbers(text, allowed_values)`
with a looser API.

**Fix:** VA-1 must either (a) extract shared public helpers from
`llm_explainer.py` into a small module used by both, or (b) require
results_qa to call `assert_llm_explanation_grounded` on structured replies.
VA-3 `audit_transcript_numbers` must reuse the **same** token normalization /
percent rules. Spoken-word numbers (“ten trades”) are **out of scope** —
document as known limitation (digit-token audit only).

### 2.7 Orchestrator compare / overview APIs are not “packet getters”

**Plan VA-3 tools:** `get_run_overview`, `get_metric`, `list_caveats`,
`compare_two_runs`.

**Reality façades:**
- Overview ≈ `explain_run` → `explain_evidence_report` + caveats on packet
- Metric ≈ path walk on `EvidencePacket.to_dict()` (private `_path_get` in
  explainer/llm_explainer)
- Compare ≈ `compare_completed_runs(left_run, right_run, …)` which re-imports
  both bundles via `BUNDLE.import`

**Fix:** VA-3 must call orchestrator façades / bound session packet — not invent
parallel bundle loaders. Cache bound packet on `VoiceSessionRecord` / session
service to avoid re-import every tool call. `compare_two_runs` must load the
**other** `ResearchRun` via `get_run`, verify hash, then call
`compare_completed_runs` (or shared compare helper). Deny path traversal
(`..`, empty, non-dot paths) in `get_metric`.

### 2.8 VA-2 “retries from settings” has no voice retry field

**Plan:** xAI mint uses “retries from settings”.  
**Reality:** Retries live on `LLMSettings.max_retries` for OpenAI only;
`[assistant.voice]` block has no `max_retries`.

**Fix:** Add `max_retries` to `[assistant.voice]` in VA-0 config contract, or
hardcode mint retries=2 mirroring `llm.py` and document it.

### 2.9 VA-5 transport is under-scoped relative to Streamlit

**Plan:** Browser custom component (preferred) or `components.html`; tool bridge
server-side; FastAPI sidecar escape hatch.

**Reality:** Streamlit script model is request/rerun; long-lived browser WS +
synchronous `function_call` → Python `execute_voice_tool` is not a thin UI PR.
Custom components are a separate package/build surface; sidecar is a second
process with auth/localhost assumptions.

**Fix before VA-5 starts (open decision #2 rewrite):**
- Freeze **one** transport: (1) localhost sidecar owning WS+tools, Streamlit
  only mints token/session id and embeds audio UI, **or** (2) defer full-duplex
  and stop product at VA-4 until a component design spike lands.
- Do not leave “preferred component / optional sidecar” ambiguous in the
  binding contract.
- VA-5 file allowlist must include whatever process entrypoint is chosen
  (`ENGINEERING.md` run instructions in same PR).

### 2.10 Model pin timing

xAI docs: `grok-voice-latest` aliases `grok-voice-think-fast-1.0` and updates to
`grok-voice-think-fast-2.0` on **2026-08-05**. Pin dated snapshot in config if
behavior stability matters for evals; document in VA-0 open decisions.

---

## 3. Over-scoped / under-scoped PRs

| PR | Assessment |
|---|---|
| **VA-0** | Right size. Add: persistence contract for voice sessions, secret precedence, `max_retries`, grounding-share decision, VA-5 transport freeze. |
| **VA-1** | Slightly over-scoped UI (“`st.chat_input` scoped to run”) without Streamlit constraints; under-specified persistence tags and dispatch allowlist. Still correctly sequenced. |
| **VA-2** | Under-specified persistence/ID; otherwise OK. Do not mint tokens in CI. |
| **VA-3** | Right size if tools are thin adapters over existing façades + cached packet. |
| **VA-4** | Over-scoped if it also invents dual-provider product policy mid-PR; under-scoped on Streamlit stub/test updates and thesis-scoped key clearing. |
| **VA-5** | **Severely under-scoped** as written. Treat as design-spike-gated or sidecar-first. |
| **VA-6** | Right size as gate; depends on whatever mode actually shipped. |

**Do not collapse** VA-1 into VA-4 / VA-5 into VA-4 — still correct.

---

## 4. Missing regression risks

1. **Thesis chat regression:** shared `st.chat_input` / layout changes breaking drafting (`handle_chat_turn` path).
2. **False “no dispatch” test** teaching implementers to bypass `BUNDLE.import` and load zips in the page (violates presentation-only rule).
3. **Grounding drift** between `llm_explainer` and `voice/grounding` → uncited numbers trusted in one channel.
4. **Conversation audit pollution:** results_qa / voice turns mixed into thesis-draft hydration (`pages/14_…py` ~L242–253 hydrates latest assistant `choices`). Messages tagged `results_qa` / voice must **not** supply `choices` or hydration will overwrite drafts.
5. **Optimistic concurrency:** multi-append turns need fresh `expected_revision` (see `handle_chat_turn` pattern).
6. **Running compute + voice:** page can have `run.status == "running"`; mic disable must use orchestrator `list_runs`, not assume single-run UI state.
7. **Compare tool side effects:** `compare_completed_runs` persists a `Comparison` record — voice `compare_two_runs` should either reuse that (document write) or call pure `compare_evidence` on two packets to stay read-only. **Prefer pure compare on cached packets** so voice remains RO.
8. **Session key leaks across theses** if voice keys omit `THESIS_SCOPED_STAGING_KEYS`.
9. **Page source contracts** in `test_assistant_workspace.py` fail if new Streamlit APIs aren’t stubbed.
10. **xAI built-in tools:** session payload must omit `web_search`, `x_search`, `file_search`, `mcp` — not only “don’t implement them in Python.”

---

## 5. Sequencing problems

1. VA-3 `compare_two_runs` RO purity vs `compare_completed_runs` persistence — resolve in VA-0/VA-3 scope text **before** coding.
2. Shared grounding extract belongs in **VA-1** (not deferred to VA-3) if results_qa is to match C2-6.
3. VA-2 before persistence contract → stall; freeze store layout in VA-0.
4. VA-4 before dual-provider decision → broken local enable checklist.
5. VA-5 before transport freeze → multi-week thrash; optionally allow VA-6 against VA-4-only (plan already allows this — keep and emphasize).

---

## 6. Gaps that would stall implementers

1. Where `VoiceSessionRecord` is stored and which schema version changes.
2. Whether `handle_results_turn` may call `dispatch` for `BUNDLE.import`.
3. Exact UI widget + key names inside the completed-run expander.
4. Whether voice compare may write comparison records.
5. How the browser tool bridge reaches `execute_voice_tool` under Streamlit.
6. Whether PTT needs OpenAI.
7. How results_qa history is selected (filter `channel==results_qa` for bound `run_id` vs whole conversation).
8. `Conversation.selected_run_id` exists but is unused — clarify ignore vs set-on-discuss.
9. Config: `load_llm_settings` ignores unknown tables today (safe), but
   `load_voice_settings` must not break if section absent — plan OK; add test.
10. Manual QA uses live xAI — no recorded fixture format for STT/TTS/WS events beyond “mock.”

---

## 7. Prioritized plan edits

### Must-fix before VA-0 merge

1. Rewrite VA-1 acceptance: allow RO `BUNDLE.import`; forbid compute/mutators.
2. Freeze voice-session persistence path, `vs_` id format, no Conversation field widening.
3. Align XAI secret precedence with `llm.py` (env → top-level Secrets → nested).
4. Add `[assistant.voice].max_retries` (or hardcode=2) to §4 config.
5. Freeze grounding: share C2-6 token rules; digit-token only for speech audit.
6. Freeze VA-3 `compare_two_runs` as **pure** packet compare (no `save_comparison`).
7. Freeze VA-4 provider policy (dual key vs tools+TTS-only).
8. Pin UI attach point: completed-run expander; nested keyed input; thesis chat untouched.
9. Note hydration hazard: results/voice assistant messages must not include `choices`.
10. Rewrite open decision #2: sidecar-first **or** VA-5 deferred; no ambiguous “preferred component.”
11. Document `grok-voice-latest` alias rollover (2026-08-05) and pin policy.
12. Cross-link this reassessment from the implementation contract header.

### Nice-to-have

1. Prefer `st.chat_input(accept_audio=True)` vs separate `st.audio_input` after spike.
2. Use `Conversation.selected_run_id` when opening Discuss results.
3. Clean up undocumented `assistant_page_summaries` / `assistant_focused_run_id` outside VA series.
4. Add metric path catalog snippet to `METRICS_GLOSSARY.md` earlier than VA-6.
5. VA-0 test that `load_llm_settings()` still works with `[assistant.voice]` present.
6. Explicit deny of xAI `file_search` / `mcp` in session payload tests (VA-5/VA-6).

---

## 8. §4 / AGENT_GUIDE alignment checklist (for every VA PR)

From `ENGINEERING_PROPOSAL.md` §4 / §4.2 and `AGENT_GUIDE.md` assistant rules:

- [ ] Engine / goldens untouched; no golden diffs
- [ ] Opt-in default-off (`assistant.voice.enabled = false`)
- [ ] Additive `assistant_voice_*` keys documented in `ARCHITECTURE.md` + `ASSISTANT_SESSION_KEYS`
- [ ] Thesis switch clears scoped voice staging keys
- [ ] Page stays presentation-only (orchestrator façades only)
- [ ] Evidence narratives grounded; uncited numbers fail closed
- [ ] Same-PR docs (`ASSUMPTIONS_AND_LIMITATIONS.md`, roadmap, this contract)
- [ ] PR body **Regression safety** paragraph
- [ ] `ruff` + `pytest -q` green
- [ ] Keep `tests/test_assistant_llm_evaluations.py` green when touching grounding/chat

---

## 9. Second-pass fixes applied (2026-08-04 follow-up)

After the first reassessment was folded into the implementation contract, a
second pass closed remaining executable holes:

1. **VA-4 intent→tool gap:** “tools + TTS” without an intent step was not
   executable. Frozen: deterministic `VoiceIntentRouter` only; no LLM intent;
   free-form spoken NL deferred to VA-5; free-form text stays VA-1.
2. **VA-4 test contradiction:** removed leftover “STT→results_qa→TTS” wording.
3. **Model/cost:** pin `grok-voice-think-fast-2.0`; budget ~$0.08/min S2S;
   do not eval against rolling `grok-voice-latest`.
4. **VA-5 topology:** Browser ↔ localhost sidecar ↔ xAI (sidecar owns key/WS);
   not “mint ephemeral in Streamlit + ambiguous browser socket.”
5. **Definition of done:** split text Q&A / PTT tool-voice / realtime NL so
   product value is honest per milestone.

---

## 10. Recommended implementer prompt (copy)

```markdown
Implement only <VA-ID> from docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
(reassessment rationale: docs/REALTIME_VOICE_AGENT_REASSESSMENT.md).

Hard rules:
- Touch only that VA’s Files allowed to touch (+ fixtures).
- Regression-safe: no engine/levels/signals/golden changes.
- assistant.voice.enabled stays false.
- Results/voice paths may dispatch BUNDLE.import (evidence) only; never
  execute_confirmed_run / PIPELINE.* / web_search / x_search / file_search / mcp.
- Reuse C2-6 numeric grounding rules; do not fork token semantics.
- Results/voice messages must not include `choices` (draft hydration hazard).
- VA-4: deterministic intent router only — no OpenAI, no free-form spoken NL.
- Document assistant_voice_* keys in ARCHITECTURE.md + ASSISTANT_SESSION_KEYS.
- Update docs in the same PR; fill Implemented contract section when done.
- PR body must include Regression safety paragraph per the contract template.
```
