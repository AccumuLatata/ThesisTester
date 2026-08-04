# Realtime Voice Agent — Implementation Contract

**Document type:** Implementation contract (VA-series) — **single source of truth**
**Status:** proposed — not shipped
**Date:** 2026-08-04
**Owner surface:** `thesistester/assistant/` + Research Assistant page only
**Provider:** xAI Grok Voice (`grok-voice-think-fast-2.0`; see §4)
**Depends on:** C2 complete (`docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` through PR6),
`docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2

This is the **only** binding VA-series document. Do not create parallel voice
roadmaps or reassessment files; amend this contract in the same PR that
changes a freeze. Every VA PR must stay inside its scope table. If a change
is not listed under **In scope**, it belongs in a later PR or is rejected.

---

## 0. Frozen design decisions (do not re-litigate in implementation PRs)

These were locked against the live assistant codebase before VA-0:

| Freeze | Rule |
|---|---|
| Results load path | `handle_results_turn` / voice may use RO `BUNDLE.import` (evidence) via `explain_run`; never `execute_confirmed_run` / `PIPELINE.*` |
| Secrets | `XAI_API_KEY`: env → Secrets top-level → `[xai].api_key` (mirror OpenAI) |
| Persistence | Voice sessions = sibling `voice_sessions/vs_[0-9a-f]{32}.json`; do not widen `Conversation` or reuse `_ID_RE` |
| Compare tool | Pure `compare_evidence` only — no `save_comparison` |
| UI attach | Completed-run expander only; thesis `st.chat_input` untouched |
| Draft hydration | Results/voice messages must **omit** `choices` |
| Grounding | Reuse C2-6 token/percent/caveat rules; digit-token audit only for speech |
| VA-4 path | Deterministic intent → VA-3 tool → template → TTS; **no OpenAI**, no free-form spoken NL |
| VA-5 path | Browser ↔ localhost FastAPI sidecar ↔ xAI; component deferred |
| Model / cost | Pin `grok-voice-think-fast-2.0`; budget ~$0.08/min S2S; no rolling `latest` in evals |
| Default | `assistant.voice.enabled = false` through VA-6 |

---

## 1. Definition of done

The series is done when a local user can:

1. Select a completed, hash-verified research run.
2. Discuss that run in **text** via grounded multi-turn results Q&A (VA-1).
3. Opt in to voice (`assistant.voice.enabled = true` + `XAI_API_KEY` set).
4. Use **push-to-talk** to invoke allowlisted evidence tools and hear
   template-spoken results (VA-4).
5. Optionally use **realtime** free-form spoken Q&A with model tool-calling
   via the localhost sidecar (VA-5).
6. Hear/see only numbers that resolve to the `EvidencePacket` or to values
   returned by allowlisted read-only tools in that session.
7. See a persisted transcript + tool audit on the thesis conversation.
8. Fall back to deterministic explain + text results Q&A if voice fails.

Voice remains **default-off** after VA-6 unless a separate, explicit enable
decision lands later.

---

## 2. Non-negotiable invariants

1. **No engine touch.** Do not modify `simulate_trades`, levels, signals,
   validation math, or golden fixtures in any VA PR.
2. **Additive only.** New modules under `thesistester/assistant/voice/` and
   narrow orchestrator/page additions. Legacy chat/explain paths keep current
   semantics when voice is disabled.
3. **Evidence-bound.** A voice session binds exactly one `run_id` + expected
   `canonical_bundle_hash`. Hash mismatch fails closed (same as `BUNDLE.import`).
4. **Read-only tools.** Voice may call only the VA-3 allowlist. Never
   `PIPELINE.*`, `execute_confirmed_run`, `dispatch` of compute, filesystem,
   shell, broker, `web_search`, `x_search`, `file_search`, or `mcp`.
5. **Grounding.** Numeric tokens in structured results-Q&A output and in
   audited voice transcripts must resolve to packet paths or tool-returned
   values; else fail/flag before trusted UI render (C2-6 parity).
6. **Secrets.** `XAI_API_KEY` server-side / sidecar only. The Streamlit page
   never embeds the long-lived key. Realtime (VA-5) browser traffic goes to
   the localhost sidecar; the sidecar owns the upstream xAI connection.
7. **Default off.** `assistant.voice.enabled = false` in `config/assistant.toml`.
8. **Same-PR docs.** Every PR that adds behavior updates the docs listed in
   that PR’s scope. New `assistant_voice_*` session keys are documented in
   `ARCHITECTURE.md` in the same PR.
9. **CI green.** `ruff check .`, `ruff format --check .`, `pytest -q`.
10. **PR body.** Every VA PR includes a **Regression safety** paragraph stating
    what is untouched (engine/goldens/C2 chat) and which tests gate the change.

---

## 3. Architecture (frozen)

```text
Research Assistant (opt-in Voice panel)
        │
        ├── VA-1 text results_qa ─────────────────────────────┐
        ├── VA-4 PTT: STT → intent → tools → TTS (xAI unary) │
        └── VA-5 realtime: browser ↔ localhost sidecar ↔ xAI │
                │                                            │
                ▼                                            ▼
        VoiceSessionService / voice tools              AssistantOrchestrator
          bind run+hash; allowlisted RO tools            explain_run /
                                                         BUNDLE.import(evidence)
                                                         → EvidencePacket
```

| Path | Role | Forbidden |
|---|---|---|
| `thesistester/assistant/results_qa.py` | Multi-turn grounded text Q&A | Audio, xAI, compute dispatch |
| `thesistester/assistant/voice/contracts.py` | Schema-versioned records | I/O, Streamlit, network |
| `thesistester/assistant/voice/settings.py` | Load voice config + key resolution | UI |
| `thesistester/assistant/voice/session.py` | Session lifecycle + instruction build | Tool execution side effects beyond allowlist |
| `thesistester/assistant/voice/xai_realtime.py` | STT/TTS + sidecar upstream xAI helpers | Embedding keys in page code |
| `thesistester/assistant/voice/intent.py` | Deterministic VA-4 intent router | LLM intent / free-form NL |
| `thesistester/assistant/voice/tools.py` | Tool schemas + router | Widening to write/compute |
| `thesistester/assistant/voice/grounding.py` | Numeric audit helpers | Trusting raw model speech |
| `thesistester/assistant/voice/sidecar.py` | Localhost realtime WS + tool bridge (VA-5) | Non-localhost bind / multi-tenant auth |
| `pages/14_Research_Assistant.py` | Presentation only | Packet construction, secrets |

**Provider note:** There is no separate “Grok 4.5 realtime” model ID. Pin
`grok-voice-think-fast-2.0` in config (§4). Thesis-drafting chat and text
results Q&A stay on the existing OpenAI structured client for this series.

---

## 4. Config contract (lands in VA-0)

Additive block only; do not reorder or rename existing `[assistant]` keys.

```toml
[assistant.voice]
enabled = false
provider = "xai"
model = "grok-voice-think-fast-2.0"   # pin dated id; do not use rolling latest in CI/evals
voice = "eve"
mode = "push_to_talk"              # VA-4; "realtime" added in VA-5
max_session_minutes = 15
store_audio = false
allow_web_search = false
require_tool_for_numbers = true
ephemeral_token_ttl_seconds = 300
max_history_messages = 12
max_retries = 2
```

**Model pin policy:** Prefer dated `grok-voice-think-fast-2.0` (post 2026-08-05
alias cutover). Do not ship evals against rolling `grok-voice-latest`. Budget
for Think Fast 2.0 speech-to-speech at about **$0.08 / audio minute** (1.0 was
~$0.05). STT/TTS unary endpoints are billed separately per xAI docs when used
in VA-4.

Secret resolution (mirror `llm.py` / `require_openai_api_key`):
1. env `XAI_API_KEY`
2. Streamlit Secrets top-level `XAI_API_KEY`
3. Streamlit Secrets nested `[xai].api_key`
Reject placeholder strings (define `_XAI_API_KEY_PLACEHOLDER`).

---

## 5. PR sequence overview

| PR | ID | Title | Merge blocks if… |
|---|---|---|---|
| 1 | VA-0 | Contracts + flag + docs freeze | Any network/UI/orchestrator behavior |
| 2 | VA-1 | Text results Q&A | Audio or xAI dependencies |
| 3 | VA-2 | xAI token + session service | Tool router or Streamlit mic |
| 4 | VA-3 | Read-only voice tools | UI enablement or realtime WS client |
| 5 | VA-4 | Push-to-talk half-duplex UI | Full-duplex / custom component |
| 6 | VA-5 | Full-duplex realtime mode | Telephony, multi-tenant, audio blob store |
| 7 | VA-6 | Evals + release gate | Flipping default `enabled=true` |

**Do not collapse VA-1 into VA-4.** Text grounding must land and pass before
speech. **Do not collapse VA-5 into VA-4.** Half-duplex proves value first.

Dependency graph:

```text
VA-0 ──► VA-1 ──► VA-4 ──► VA-5 ──► VA-6
         │         ▲
         └──► VA-2 ──► VA-3 ──┘
```

VA-1 and VA-2 may proceed in parallel after VA-0. VA-3 requires VA-2
(session bind) and VA-1 (shared results semantics). VA-4 requires VA-1+VA-3.
VA-5 requires VA-4. VA-6 requires VA-5 (or VA-4 if product stops at half-duplex;
still run the full eval file against whatever mode shipped).

---

## 6. Detailed PR scopes

### VA-0 — Contracts, flag, docs freeze

**Goal:** Freeze schemas and defaults with zero runtime behavior change for
users.

#### In scope
| Item | Detail |
|---|---|
| Docs | This file is canonical; keep index pointer in `ENGINEERING_ROADMAP.md`; assumptions note in `ASSUMPTIONS_AND_LIMITATIONS.md`; architecture note that `assistant_voice_*` keys are reserved for later PRs |
| Config | Add `[assistant.voice]` to `config/assistant.toml` exactly as §4 |
| Code | `thesistester/assistant/voice/__init__.py` (exports only) |
| Code | `thesistester/assistant/voice/contracts.py` — frozen dataclasses / typed dicts: `VoiceSessionRecord` (schema_version, session_id, thesis_id, run_id, canonical_bundle_hash, mode, created_at, ended_at, status), `VoiceTranscriptTurn`, `VoiceToolInvocation`, `GroundingVerdict` |
| Code | `thesistester/assistant/voice/settings.py` — `load_voice_settings()` reading toml; returns dataclass; ignores missing section with safe defaults (`enabled=False`) |
| Tests | `tests/test_assistant_voice_contracts.py` — schema round-trip, default settings, enabled=false |

#### Out of scope
- Any call to xAI / OpenAI / WebSocket
- Any change to `orchestrator.py`, `llm.py`, `llm_explainer.py`, pages
- Session_state keys (none yet)
- Enabling UI affordances

#### Acceptance
- [ ] `load_voice_settings().enabled is False` on current config
- [ ] `load_llm_settings()` still succeeds with `[assistant.voice]` present
- [ ] Existing `tests/test_assistant_llm*.py` unchanged and green
- [ ] No new third-party dependency
- [ ] `ruff` + `pytest -q` green

#### Regression safety
Additive package + config defaults. No engine, no golden, no C2 path edits.
If `assistant.voice` is absent, settings loader must behave as disabled.

#### Files allowed to touch
```
config/assistant.toml
thesistester/assistant/voice/__init__.py
thesistester/assistant/voice/contracts.py
thesistester/assistant/voice/settings.py
tests/test_assistant_voice_contracts.py
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
docs/ENGINEERING_ROADMAP.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ARCHITECTURE.md
docs/AGENT_GUIDE.md
```

---

### VA-1 — Multi-turn results Q&A (text substrate)

**Goal:** Add grounded multi-turn discussion of a completed run **in text**.
Voice later reuses this path; this PR ships user value without audio.

#### In scope
| Item | Detail |
|---|---|
| Code | New `thesistester/assistant/results_qa.py` — `propose_results_reply(client, *, packet, history, user_message) -> ResultsQAReply` with schema `{summary, caveats, claims[{text,path}], followups}` |
| Code | Grounding: reuse / share helpers with `llm_explainer.py` (extract shared numeric grounding into a small private helper **only if** needed; prefer calling existing validators to avoid drift) |
| Code | `AssistantOrchestrator.handle_results_turn(thesis_id, run_id, message, *, conversation_id=...)` — load run via `get_run`, hash-verified evidence via existing `explain_run` / `BUNDLE.import` evidence path, call results_qa, persist user+assistant messages with additive `"channel": "results_qa"` and `"run_id"` (no Conversation schema bump; message dicts are not field-locked) |
| Code | Grounding: call `assert_llm_explanation_grounded` or extracted shared helpers from `llm_explainer.py` — do not fork token/percent/caveat rules |
| UI | Inside each completed-run expander in `pages/14_Research_Assistant.py` (beside Explain / LLM explain): “Discuss results” with keyed nested `st.chat_input` or `st.text_input`+button — **no mic**; do not replace thesis-draft `st.chat_input` |
| Tests | `tests/test_assistant_results_qa.py` + extend `tests/test_assistant_llm_evaluations.py`: injection→no `execute_confirmed_run` / no `PIPELINE.*`; RO `BUNDLE.import` allowed; uncited numbers rejected; missing run; hash mismatch; history trim filtered by `channel`+`run_id`; `handle_chat_turn` still never loads bundles; results messages must not include `choices` (draft hydration hazard at page L242–253) |

#### Out of scope
- xAI, audio, STT/TTS, WebSockets
- New registry compute capabilities
- Changing thesis-drafting `handle_chat_turn` prompt/schema
- Changing deterministic `explain_evidence_report` templates (call them; don’t rewrite)

#### Acceptance
- [ ] `handle_results_turn` never calls `execute_confirmed_run` and never dispatches `PIPELINE.*` / mutators (asserted). RO `BUNDLE.import` (action `evidence`) is allowed — unlike `handle_chat_turn`
- [ ] Uncited numeric token → error before UI persistence/render
- [ ] Hash mismatch → structured failure; no packet leak
- [ ] Without provider key, deterministic explain still works; results Q&A surfaces clear remediation
- [ ] `handle_chat_turn` behavior fixtures remain green unchanged
- [ ] Persisted results assistant messages omit `choices` so thesis draft hydration cannot adopt them

#### Regression safety
New orchestrator method + optional UI block. Thesis drafting and one-shot
`explain_run_with_llm` keep prior contracts. No engine/golden changes.

#### Files allowed to touch
```
thesistester/assistant/results_qa.py
thesistester/assistant/orchestrator.py          # additive method only
thesistester/assistant/repository.py            # only if message tag/schema needs additive field
thesistester/assistant/llm_explainer.py         # shared grounding helper extract only if required
thesistester/assistant/__init__.py              # exports
pages/14_Research_Assistant.py                  # expander only
tests/test_assistant_results_qa.py
tests/test_assistant_llm_evaluations.py
docs/ARCHITECTURE.md                            # any new assistant_* keys
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md     # mark VA-1 implemented contract
docs/AGENT_GUIDE.md                             # results_qa rule
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### VA-2 — xAI credentials + session service

**Goal:** Server-side session + credential primitives. No mic UI.
Ephemeral-token helpers may land here for later sidecar use, but the Streamlit
page must not depend on browser-held xAI tokens.

#### In scope
| Item | Detail |
|---|---|
| Code | `voice/xai_realtime.py` — `mint_ephemeral_token(*, api_key, expires_after_seconds) -> EphemeralToken` via `POST https://api.x.ai/v1/realtime/client_secrets`; stdlib/`urllib` or existing HTTP style from `llm.py`; 30s timeout; retries from settings |
| Code | `voice/session.py` — `VoiceSessionService.create_session(thesis_id, run_id, *, expected_hash, mode)` loads packet via orchestrator evidence import, caches bound packet, persists `VoiceSessionRecord`, builds system instructions (honesty preamble + tool-number policy + caveats summary) |
| Persistence | Store under `assistant/theses/{thesis_id}/voice_sessions/{session_id}.json` with `kind: "voice_session"` and `session_id` matching `vs_[0-9a-f]{32}`. Do **not** widen `Conversation` fields or reuse `_ID_RE` (only `th_/run_/conv_`). Conversation schema stays v1; voice sessions are sibling docs |
| Code | `VoiceSessionService.end_session(session_id)` marks ended; flush transcript turns via `append_conversation_message` / `tool_entry` (best-effort) |
| Code | Key resolution in `voice/settings.py`: env → Secrets `XAI_API_KEY` → `[xai].api_key`; reject placeholders; mint retries from `assistant.voice.max_retries` |
| Tests | `tests/test_assistant_voice_session.py` — mock HTTP; no key; placeholder key; bad hash; missing run; instruction contains required policy strings; session id format |

#### Out of scope
- Tool JSON schemas / execution (VA-3)
- Streamlit widgets
- Browser WebSocket client
- Live network in CI

#### Acceptance
- [ ] Mint without key → structured fail closed
- [ ] Create session without verified bundle → fail closed
- [ ] Instructions always include: evidence-only, no trade advice, numbers only from tools/packet, sample-size/OOS caveats
- [ ] No `XAI_API_KEY` appears in any page module
- [ ] OpenAI `llm.py` untouched

#### Regression safety
New modules only. Flag still false → no user-visible change. C2 OpenAI path
untouched.

#### Files allowed to touch
```
thesistester/assistant/voice/xai_realtime.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/settings.py
thesistester/assistant/voice/contracts.py       # only if session fields need additive tweak
thesistester/assistant/voice/__init__.py
thesistester/assistant/repository.py            # only if persisting sessions needs store helpers
tests/test_assistant_voice_session.py
docs/ASSUMPTIONS_AND_LIMITATIONS.md             # XAI_API_KEY note
docs/ARCHITECTURE.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### VA-3 — Read-only voice tool surface

**Goal:** Freeze the only functions the voice model may invoke.

#### In scope
| Item | Detail |
|---|---|
| Code | `voice/tools.py` — `VOICE_TOOL_SCHEMAS` + `execute_voice_tool(name, args, *, session) -> dict` |
| Tools (exact v1 set) | `get_run_overview` → `explain_evidence_report` / caveats from **cached bound packet** (no re-import) |
| | `get_metric` → `{path}` → typed value from bound packet; unknown/empty/`..` paths fail |
| | `list_caveats` → packet caveats list |
| | `compare_two_runs` → `{other_run_id}` → load other run, hash-verify, `compare_evidence` on packets; **must not** call `repository.save_comparison` (stay read-only) |
| Deny | Anything else, including `web_search`, `x_search`, `file_search`, `mcp`, `PIPELINE.*`, `execute_confirmed_run`, export mutators |
| Audit | Each call → one conversation `tool_transcript` entry via `append_conversation_message(..., tool_entry=...)` (args digest + ok/error + result digest) |
| Grounding helper | `voice/grounding.py` — reuse C2-6 token normalization/percent rules from `llm_explainer` (extract shared helpers if needed); digit-token audit only (spoken-word numbers out of scope) |
| Tests | `tests/test_assistant_voice_tools.py` — allowlist, deny, path traversal, compare missing hash, injection names, grounding helper cases |

#### Out of scope
- Enabling `assistant.voice.enabled`
- UI / mic / WebSocket client
- Adding `get_claim_safe_narration` (defer post-VA-6 unless needed for latency)
- Registry expansion beyond calling existing orchestrator read APIs

#### Acceptance
- [ ] Unknown tool name → fail; no side effects
- [ ] Model-requested `execute_confirmed_run` / `web_search` never execute
- [ ] `get_metric` rejects unknown/empty paths
- [ ] `compare_two_runs` fails closed if other run hash missing/mismatch
- [ ] Exactly one transcript audit row per invocation attempt

#### Regression safety
Thin adapters over existing explain/compare/packet. No public API semantic
change. No page behavior change while flag is false.

#### Files allowed to touch
```
thesistester/assistant/voice/tools.py
thesistester/assistant/voice/grounding.py
thesistester/assistant/voice/session.py         # wire execute_voice_tool only
thesistester/assistant/voice/__init__.py
tests/test_assistant_voice_tools.py
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
docs/AGENT_GUIDE.md
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### VA-4 — Push-to-talk half-duplex UI

**Goal:** First user-visible voice loop: speak an allowlisted evidence-tool
command, hear a template-rendered tool result. Free-form NL discussion stays
on VA-1 (text) and VA-5 (realtime model tool-calling).

#### In scope
| Item | Detail |
|---|---|
| UI | Opt-in panel inside completed-run expander on `pages/14_Research_Assistant.py` when `voice.enabled` **and** completed run selected |
| Provider policy | **XAI-only for PTT.** No OpenAI key required for voice. Text “Discuss results” remains OpenAI `handle_results_turn` (VA-1). Dual-key STT→`results_qa`→TTS is explicitly **out of series** |
| Intent→tool (frozen) | After STT, `VoiceIntentRouter` maps transcript → **exactly one** VA-3 tool via deterministic allowlisted patterns (overview/summarize/default → `get_run_overview`; caveats → `list_caveats`; metric aliases/paths → `get_metric`; compare + `run_…` id → `compare_two_runs`). Unrecognized speech → `get_run_overview` plus a fixed spoken note that free-form Q&A is text Discuss results or realtime mode. **No LLM intent step in VA-4** |
| Speak path | Template-render tool JSON/text to a speakable string (numbers only from tool return) → xAI TTS → `st.audio`. Run `GroundingVerdict` on that string vs tool-returned values |
| Flow | `st.audio_input` (document sample_rate; Streamlit default 16 kHz ≠ VA-5 PCM 24 kHz) → xAI STT (`POST /v1/stt`) → intent router → `execute_voice_tool` → template → TTS (`POST /v1/tts`) → playback |
| UI | Show STT text, chosen tool, tool result, grounding status; block mic while any thesis run has `status=="running"` (`list_runs`) |
| Session | Create/end `VoiceSessionRecord` with `mode="push_to_talk"` |
| Session keys | Additive `assistant_voice_*` in `ASSISTANT_SESSION_KEYS` + `THESIS_SCOPED_STAGING_KEYS`; document in `ARCHITECTURE.md` same PR; clear on thesis switch. Extend `tests/test_assistant_workspace.py` Streamlit stub with `audio_input` / `audio` |
| Config | Keep default `mode = "push_to_talk"` |
| Tests | Flag-off: no token mint / no STT/TTS (asserted) |
| | Flag-on without `XAI_API_KEY`: remediation error, no crash |
| | Mocked STT → intent → tool → template → TTS; assert spoken text numbers ⊆ tool values; unrecognized intent falls back safely |

#### Out of scope
- Free-form NL spoken Q&A (that is VA-5 / text VA-1)
- LLM-based intent classification
- Full-duplex, barge-in, server VAD streaming
- Custom Streamlit components / `components.html` WebSocket
- LiveKit / Twilio / telephony
- `store_audio=true` implementation (keep false; ignore flag or reject true)
- Changing VA-3 allowlist

#### Acceptance
- [ ] `enabled=false` → no token mint, no STT/TTS calls (asserted)
- [ ] Spoken reply numbers come only from the executed tool’s return (grounding pass)
- [ ] Unrecognized transcript does not invent metrics
- [ ] Running compute disables mic control
- [ ] Session end writes transcript turns + tool audits to conversation store
- [ ] Manual checklist (not CI): record “caveats” → hear caveat list; record gibberish → overview + fallback note

#### Regression safety
Presentation + VA-1/VA-3 calls only. Engine untouched. Thesis draft chat
layout unchanged aside from additive expander/panel. Document all new
session keys.

#### Files allowed to touch
```
pages/14_Research_Assistant.py
thesistester/assistant/workspace.py             # ASSISTANT_SESSION_KEYS additive
thesistester/assistant/voice/intent.py          # deterministic VoiceIntentRouter
thesistester/assistant/voice/xai_realtime.py    # STT/TTS helpers
thesistester/assistant/voice/session.py
thesistester/assistant/orchestrator.py          # only if a thin voice_turn façade is needed
tests/test_assistant_voice_ui.py
tests/test_assistant_voice_intent.py
tests/test_assistant_workspace.py               # key list expectations
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### VA-5 — Full-duplex realtime (Grok Voice WebSocket)

**Goal:** Sub-second duplex review with server VAD and barge-in, still
allowlist-bound.

#### In scope
| Item | Detail |
|---|---|
| Transport topology (frozen) | **Browser mic/speaker ↔ localhost FastAPI sidecar ↔ xAI Realtime WS.** Sidecar holds `XAI_API_KEY` (or mints ephemeral tokens server-side for its own upstream WS). Streamlit only starts/shows session controls and never opens the xAI socket. Custom Streamlit component / browser-direct-to-xAI is deferred (spike-only) |
| Why sidecar | Streamlit’s rerun model cannot host a long-lived duplex tool bridge reliably; one local process owns WS + `execute_voice_tool` |
| Session | Sidecar applies `session.update` with voice, instructions from `VoiceSessionService`, `turn_detection: server_vad`, **custom function tools only** (VA-3 schemas); payload must omit `web_search`, `x_search`, `file_search`, `mcp` |
| Tool bridge | On `function_call` → sidecar calls `execute_voice_tool` → `function_call_output` (same Python package / no duplicated business logic) |
| Auth | Sidecar binds to `127.0.0.1` only; single trusted local user; document that it is not a multi-tenant server |
| Audio | PCM 24 kHz as required by xAI; no raw audio persistence (`store_audio` stays false) |
| Config | Allow `mode = "realtime"`; push-to-talk remains available as fallback |
| Transcript | Sync assistant/user text + tool audits to repository on session end; periodic flush best-effort |
| TTL | Enforce `max_session_minutes`; token/session refresh only via sidecar |
| Tests | Mocked WS event fixtures for tool bridge; TTL; deny search/`file_search`/`mcp` tools in session payload; non-localhost bind rejected |
| Docs | `ENGINEERING.md` localhost sidecar run instructions in the same PR |

#### Out of scope
- Phone/Twilio
- Multi-user auth
- Default `enabled=true`
- Widening tool allowlist
- Replacing VA-4 (keep as fallback)

#### Acceptance
- [ ] Session payload never includes `web_search` / `x_search` when `allow_web_search=false`
- [ ] Tool bridge cannot invoke names outside VA-3 allowlist
- [ ] Token never logged; key never sent to browser
- [ ] Exceeding `max_session_minutes` ends session
- [ ] Manual QA: barge-in, silence, “what’s win rate?”, injection “run a grid” → refused

#### Regression safety
New transport/UI only. VA-1 remains source of truth for text channel. VA-3
allowlist unchanged. Engine/golden untouched.

#### Files allowed to touch
```
thesistester/assistant/voice/xai_realtime.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/tools.py           # schema export for session.update only
thesistester/assistant/voice/sidecar.py         # localhost FastAPI entry (single-user)
pages/14_Research_Assistant.py
tests/test_assistant_voice_realtime.py
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
docs/ENGINEERING.md                             # sidecar run instructions (required)
```

#### Implemented contract (fill when merged)
_Pending implementation._

---

### VA-6 — Evaluation suite + release gate

**Goal:** Close the research-integrity gate. Do **not** flip default-on.

#### In scope
| Item | Detail |
|---|---|
| Tests | `tests/test_assistant_voice_evaluations.py` covering: forbidden tool/injection; uncited transcript numbers; hash mismatch on session create; token mint failures; max session duration; results_qa ↔ voice tool parity; voice cannot execute/confirm runs; flag-off no side effects |
| Docs | `ASSUMPTIONS_AND_LIMITATIONS.md` (shipped limitations), `METRICS_GLOSSARY.md` (spoken metric display rules), `AGENT_GUIDE.md` (VA PR rules), `ENGINEERING_ROADMAP.md` (VA status), this file (mark release gate closed) |
| Ops note | Budget ~$0.08/min for Think Fast 2.0 S2S (+ STT/TTS for VA-4); `max_session_minutes` guidance in assumptions |
| Flag | Leave `enabled=false`; document opt-in steps for local user |

#### Out of scope
- New features / extra tools
- Provider swap for thesis chat
- Default enable

#### Acceptance
- [ ] Full suite green including C2-6 evals
- [ ] Voice eval file fails CI if allowlist or grounding regresses
- [ ] Deterministic explain/compare usable with zero voice/xAI config
- [ ] Release checklist in PR body completed

#### Regression safety
Tests + docs + policy only. No engine semantics. No golden regen.

#### Files allowed to touch
```
tests/test_assistant_voice_evaluations.py
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/METRICS_GLOSSARY.md
docs/AGENT_GUIDE.md
docs/ENGINEERING_ROADMAP.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
# bugfix only if evals expose defects in voice modules — no feature creep
```

#### Release checklist (PR body)
- [ ] §4.2 items for assistant-surface PR
- [ ] No golden file diffs
- [ ] `enabled` still false
- [ ] Manual duplex/half-duplex smoke recorded in PR notes
- [ ] Cost/privacy assumptions updated

#### Implemented contract (fill when merged)
_Pending implementation._

---

## 7. Per-PR regression-safety template (copy into every VA PR body)

```markdown
## Regression safety
- Engine / levels / signals / goldens: untouched
- C2 thesis chat (`handle_chat_turn`): untouched unless this is VA-1 (additive only)
- Voice flag default: false
- New behavior requires: <flag / completed run / key>
- Tests gating this PR: <list>
- Docs updated this PR: <list>
```

---

## 8. Explicit non-goals (series-wide)

- Voice-driven strategy generation or autonomous grid/WFA
- Live trading / broker commands
- Replacing classic Streamlit workflows
- Multi-tenant auth / cloud sync
- Persisting raw microphone audio by default
- Enabling xAI web/X search on results sessions
- Migrating drafting chat off OpenAI
- Any `simulate_trades` / levels / golden change

---

## 9. Testing matrix

| Gate | VA-0 | VA-1 | VA-2 | VA-3 | VA-4 | VA-5 | VA-6 |
|---|---|---|---|---|---|---|---|
| ruff + pytest | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| No golden diffs | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Schema/unit | ✓ | | | | | | |
| Grounding / no dispatch | | ✓ | | ✓ | ✓ | | ✓ |
| Mocked HTTP token | | | ✓ | | | | ✓ |
| Tool allowlist | | | | ✓ | | ✓ | ✓ |
| Flag-off no mint | | | | | ✓ | ✓ | ✓ |
| Mocked WS tool bridge | | | | | | ✓ | ✓ |
| Full voice eval file | | | | | | | ✓ |

---

## 10. Cost, privacy, failure

| Topic | Policy |
|---|---|
| Cost | ~$0.08 × S2S audio minutes (Think Fast 2.0); hard cap `max_session_minutes`; VA-4 also incurs unary STT/TTS |
| Keys | Server/sidecar `XAI_API_KEY` only; browser never holds the long-lived key |
| Audio blobs | Not persisted (`store_audio=false`) |
| Transcripts | Schema-versioned text + tool audit in assistant store |
| Failure | Deterministic explain + VA-1 text Q&A remain available |

---

## 11. Open decisions (resolve during VA-0 review; then freeze)

| # | Decision | Frozen default |
|---|---|---|
| 1 | VA-4 STT | xAI batch STT |
| 2 | VA-5 transport | Browser ↔ **localhost FastAPI sidecar** ↔ xAI (component deferred) |
| 3 | Default voice id | `eve` |
| 4 | `compare_two_runs` in v1 allowlist | **include** (pure `compare_evidence`; no persist) |
| 5 | Model pin string | `grok-voice-think-fast-2.0` (not rolling `latest`) |
| 6 | VA-4 answer path | Deterministic intent → VA-3 tool → template → TTS (**no OpenAI**, no free-form NL) |
| 7 | Voice session persistence | Sibling `voice_sessions/` docs with `vs_` ids |
| 8 | Free-form spoken NL | **VA-5 only** (model tool-calling); VA-1 covers free-form **text** |

Changing these defaults requires a docs amendment in the PR that changes them.

---

## 12. Agent instructions (for implementers)

When implementing any VA PR:

1. Read **only** this document’s section for that VA ID (plus §0 freezes).
2. Touch **only** files in **Files allowed to touch** (plus test fixtures they
   need). Ask for a contract amendment PR before expanding the file list.
3. Keep work regression-safe per §2 and `docs/ENGINEERING_PROPOSAL.md` §4.
4. Update documentation in the **same** PR — amend this file, do not add a
   second voice roadmap.
5. Do not enable voice by default.
6. Do not add search tools or compute tools “for convenience.”
7. Results/voice may use RO `BUNDLE.import` (evidence); never
   `execute_confirmed_run` / `PIPELINE.*`.
8. Results/voice messages must not include `choices` (draft hydration hazard).
9. Fill **Implemented contract** under that VA section when merging.

---

## 13. References

- xAI Voice: https://docs.x.ai/developers/model-capabilities/audio/voice
- Speech-to-speech: https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech
- Ephemeral tokens: https://docs.x.ai/developers/model-capabilities/audio/ephemeral-tokens
- Launch note: https://x.ai/news/grok-voice-agent-api
- `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` (C2-6 grounding gate)
- `docs/ENGINEERING_PROPOSAL.md` §4
- `thesistester/assistant/llm_explainer.py`
- `thesistester/assistant/orchestrator.py` (`handle_chat_turn`, `explain_run`, `compare_completed_runs`)
- `thesistester/assistant/repository.py` (conversation append / exact schema fields)
- `pages/14_Research_Assistant.py` (UI attach point: completed-run expander)
