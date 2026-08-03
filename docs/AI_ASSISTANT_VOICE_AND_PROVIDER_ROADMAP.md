# AI Assistant Voice & Provider Roadmap

**Project:** ThesisTester  
**Feature:** Optional voice input/output and multi-provider LLM support for the
Research Assistant  
**Status:** proposed implementation contract (not started)  
**Document owner:** ThesisTester engineering  
**Last updated:** 2026-08-03  
**Related documents:**
[`AI_CHAT_2_ENGINEERING_ROADMAP.md`](AI_CHAT_2_ENGINEERING_ROADMAP.md),
[`AI_RESEARCH_ASSISTANT_ROADMAP.md`](AI_RESEARCH_ASSISTANT_ROADMAP.md),
[`ARCHITECTURE.md`](ARCHITECTURE.md),
[`AGENT_GUIDE.md`](AGENT_GUIDE.md),
[`ASSUMPTIONS_AND_LIMITATIONS.md`](ASSUMPTIONS_AND_LIMITATIONS.md)

> Naming note: this roadmap adds **optional voice transport** and an **optional
> xAI/Grok text provider**. It does **not** make the LLM the backtest engine,
> bypass confirmation, enable live trading, or require replacing OpenAI text
> chat.

---

## 1. Purpose

After AI Chat 2.0 PR6, the Research Assistant already supports:

- non-executing text chat that drafts thesis choices;
- evidence-only LLM paraphrase of completed runs;
- human-gated validate → confirm → `execute_confirmed_run`;
- OpenAI Responses structured output via `StructuredLLMClient`.

Users now want to know whether voice chat and/or Grok 4.5 can participate in
that loop. This roadmap answers with a regression-safe PR sequence:

1. Keep text chat working exactly as today unless a provider PR explicitly
   changes it.
2. Add voice as an **optional** input/output mode on
   `pages/14_Research_Assistant.py`.
3. Allow Grok/xAI as an **optional** text provider without forcing a switch.
4. Preserve every research-integrity gate from AI Chat 2.0.

## 2. Definition of done

Track A (voice v1) is done when a user can optionally speak or upload audio on
the Research Assistant page, see a transcript enter the existing chat
transcript, receive the same non-executing draft/clarifications path as typed
chat, optionally hear a spoken paraphrase of the assistant reply, and still
must use the explicit confirmation lifecycle to run research.

Track B (provider choice) is done when `config/assistant.toml` can select
`openai` or `xai` for structured text chat/explain, credentials remain
env-only, and all existing confirmation/evidence evaluation tests stay green.

Track C/D items below are deferred product expansions and are **not** part of
the initial release gate.

## 3. Non-negotiable invariants

These extend AI Chat 2.0 invariants; violating any one fails the PR:

1. Existing engine, signal, level, analytics, and API semantics remain unchanged.
2. Voice and provider work are additive; default config preserves current
   OpenAI text-only behavior.
3. Chat turns — typed or spoken — never call `dispatch` or
   `execute_confirmed_run`.
4. LLM output remains untrusted input; structured schema validation and
   evidence grounding still fail closed.
5. No LLM receives arbitrary filesystem, shell, SQL, engine, broker, or live
   order access.
6. No silent configuration changes and no autonomous experiment execution.
7. Provider secrets are environment-injected only; never committed.
8. Live web/X search tools stay disabled for research chat unless a later
   dedicated PR opts them in with explicit product approval.
9. Docs, tests, and `ARCHITECTURE.md` session-key updates ship in the same PR
   as behavior.
10. Every PR must keep `ruff check .`, `ruff format --check .`, and `pytest -q`
    green.

## 4. Current baseline (do not regress)

| Surface | Current behavior |
|---|---|
| Text chat | `st.chat_input` → `create_openai_client` → `handle_chat_turn` → non-executing `ThesisDraft` |
| Explain | Optional evidence-only paraphrase via `explain_packet_with_llm` |
| Execute | UI/orchestrator confirmation lifecycle only |
| Provider | `provider = "openai"`, `model = "gpt-5.6-luna"` in `config/assistant.toml` |
| Secret | `OPENAI_API_KEY` env only |
| Voice | None |
| Streaming / WebSocket | None |
| Tool loop | `max_tool_rounds` configured but unused; no function calling |

Relevant code:

- `thesistester/assistant/llm.py`
- `thesistester/assistant/llm_intent.py`
- `thesistester/assistant/llm_explainer.py`
- `thesistester/assistant/orchestrator.py` (`handle_chat_turn`)
- `pages/14_Research_Assistant.py`
- `config/assistant.toml`
- `tests/test_assistant_llm*.py`, `tests/test_assistant_llm_evaluations.py`

## 5. Product decisions locked by this roadmap

| Decision | Choice |
|---|---|
| Is voice required? | No — optional mode |
| Must text chat switch to Grok? | No |
| Voice v1 transport | Push-to-talk / audio upload → STT → existing chat path → optional TTS |
| True realtime duplex voice | Deferred (Track C) |
| Can voice execute runs? | No |
| Can Grok text execute runs? | No |
| Provider selection | Config-driven (`openai` default, optional `xai`) |
| Conversational confirm-and-run | Deferred (Track D); remains button/lifecycle driven |

## 6. Architecture target

```text
Research Assistant page
  ├── Text chat (default; unchanged unless Track B enables xAI)
  │     └─ StructuredLLMClient.complete_structured
  │          └─ handle_chat_turn → compile_thesis → staged draft
  │
  └── Optional voice mode (Track A)
        ├─ mic / audio upload
        ├─ SpeechToTextClient.transcribe → transcript text
        ├─ same handle_chat_turn path as typed chat
        └─ optional TextToSpeechClient.synthesize → audio reply

Confirm / Run controls remain UI + orchestrator only
  └─ validate → confirm → execute_confirmed_run → api.run_experiment
```

Provider boundary remains protocol-based:

```text
StructuredLLMClient  (text chat + explain)
SpeechToTextClient   (voice in)
TextToSpeechClient   (voice out)
```

No provider SDK may enter engine/analytics code. Assistant adapters stay in
`thesistester/assistant/`.

## 7. PR sequence overview

| PR | Track | Title | Depends on |
|---|---|---|---|
| **AV-1** | A | Voice contracts, config, disabled-by-default settings | — |
| **AV-2** | A | STT adapter with fake transport + fail-closed errors | AV-1 |
| **AV-3** | A | Orchestrator `handle_voice_turn` façade (STT → chat) | AV-2 |
| **AV-4** | A | Optional TTS adapter for assistant replies | AV-1 |
| **AV-5** | A | Streamlit optional voice controls on Research Assistant | AV-3, AV-4 |
| **AV-6** | A | Voice evaluation / regression release gate | AV-5 |
| **AP-1** | B | Provider factory + xAI structured text client | — (parallel to A after AV-1 config shape if shared) |
| **AP-2** | B | Wire page/orchestrator to provider factory; keep OpenAI default | AP-1 |
| **AP-3** | B | Provider evaluation / regression release gate | AP-2 |
| **AR-1** | C | Realtime duplex spike (design-only or prototype behind flag) | AV-6 |
| **AE-1** | D | Conversational plan proposal + explicit confirm bridge | AP-3 recommended |

PRs AV-\* and AP-\* may proceed on parallel branches after AV-1 lands the shared
config keys. Do not combine voice UI and provider migration in one PR.

---

## 8. Track A — Optional voice v1 (push-to-talk)

### AV-1 — Voice contracts and disabled-by-default config

**Goal:** introduce versioned voice settings and typed errors without enabling
any network or UI behavior.

**Scope**
- Extend `config/assistant.toml` with an additive `[assistant.voice]` table:
  - `enabled = false`
  - `stt_provider = "none"` (later `"xai"` or `"openai"`)
  - `tts_provider = "none"`
  - `tts_enabled = false`
  - max upload bytes / max duration seconds
- Add `VoiceSettings` dataclass and loader validation in
  `thesistester/assistant/llm.py` or a new `voice.py` settings module.
- Add typed errors: `VoiceConfigurationError`, `VoiceProviderError`.
- Document defaults in `ASSUMPTIONS_AND_LIMITATIONS.md` and point here from
  `AI_CHAT_2_ENGINEERING_ROADMAP.md`.

**Out of scope:** STT/TTS network clients, Streamlit mic UI, provider text
swap, realtime WebSockets, tool calling.

**Likely files**
- `config/assistant.toml`
- `thesistester/assistant/voice.py` (new; settings/errors only)
- `tests/test_assistant_voice_settings.py` (new)
- `docs/AI_ASSISTANT_VOICE_AND_PROVIDER_ROADMAP.md`
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
- `docs/ARCHITECTURE.md` (config note only)

**Acceptance**
- Default config loads with voice disabled.
- Enabling voice with `stt_provider = "none"` fails closed at settings
  validation when a voice API is requested later; AV-1 itself must not call
  network.
- Existing LLM settings tests remain green; OpenAI text path untouched.

**Regression gate**
- `pytest -q tests/test_assistant_llm.py tests/test_assistant_voice_settings.py`
- Full suite green.

---

### AV-2 — Speech-to-text adapter

**Goal:** convert audio bytes to transcript text through an injectable
transport; no orchestrator or UI wiring yet.

**Scope**
- Add `SpeechToTextClient` protocol and one concrete adapter (prefer xAI STT
  `https://api.x.ai/v1/stt` **or** OpenAI transcription; pick one in the PR
  description and stick to it).
- Env secret only (`XAI_API_KEY` and/or reuse `OPENAI_API_KEY` depending on
  chosen provider).
- Validate content type, size, and duration bounds before upload.
- Fake transport tests for success, empty transcript, timeout, HTTP failure,
  oversized audio.
- Reject placeholder credentials the same way OpenAI text does.

**Out of scope:** TTS, page UI, chat persistence, realtime streaming mic,
server-side VAD, web search tools.

**Likely files**
- `thesistester/assistant/voice_stt.py` (new)
- `tests/test_assistant_voice_stt.py` (new)
- `docs/AGENT_GUIDE.md` (credential note)

**Acceptance**
- `transcribe(audio_bytes, *, mime_type) -> str` returns non-empty stripped
  text or raises typed error.
- No assistant/repository imports from the STT module.
- No production network calls in unit tests.

**Regression gate**
- Focused voice + existing LLM tests green.
- Confirm no new dependency forces an OpenAI/xAI SDK into engine packages.

---

### AV-3 — Orchestrator voice turn façade

**Goal:** one audited path from transcript-capable audio input to the existing
non-executing chat turn.

**Scope**
- Add `AssistantOrchestrator.handle_voice_turn(...)` that:
  1. requires voice settings enabled;
  2. transcribes via injected `SpeechToTextClient`;
  3. calls existing `handle_chat_turn(...)` with the transcript;
  4. persists ordinary user/assistant conversation messages (user content is
     the transcript; metadata may record `source: "voice"`).
- Return both transcript and `ThesisDraft`.
- Fail closed on empty transcript.
- Unit test: voice turn never monkeypatches into `dispatch` /
  `execute_confirmed_run` (mirror
  `test_chat_turn_cannot_bypass_confirmation_or_dispatch`).

**Out of scope:** Streamlit widgets, TTS playback, provider text migration,
confirm-and-run from voice.

**Likely files**
- `thesistester/assistant/orchestrator.py`
- `thesistester/assistant/__init__.py` (exports if needed)
- `tests/test_assistant_orchestrator.py` and/or
  `tests/test_assistant_voice_orchestrator.py`
- `tests/test_assistant_llm_evaluations.py` (add voice bypass case)

**Acceptance**
- Identical drafting semantics to typed chat for the same transcript text.
- Conversation revision rules unchanged.
- Spoken “run without confirmation” still cannot execute.

**Regression gate**
- Existing chat confirmation-bypass evaluation remains green.
- Repository conversation schema stays backward compatible; unknown message
  metadata must not break readers.

---

### AV-4 — Optional text-to-speech adapter

**Goal:** synthesize spoken audio for assistant reply text only; still no page
wiring required to merge if tests cover the adapter alone, but prefer landing
before AV-5.

**Scope**
- Add `TextToSpeechClient` protocol + one concrete adapter (xAI TTS
  `https://api.x.ai/v1/tts` or OpenAI speech).
- Synthesize only plain assistant-facing summary text supplied by the caller;
  do not speak raw RunSpec JSON dumps by default.
- Bound max characters; fail closed on empty text.
- Fake transport tests for success/failure/timeout.

**Out of scope:** realtime streaming TTS WebSocket, custom voice cloning, UI
autoplay policy, explaining runs via voice (can reuse later).

**Likely files**
- `thesistester/assistant/voice_tts.py` (new)
- `tests/test_assistant_voice_tts.py` (new)

**Acceptance**
- TTS disabled in config means factory creation fails closed or returns a
  no-op disabled client; page must not call network.
- Adapter has no orchestrator side effects.

**Regression gate**
- No change to explain/evidence grounding behavior.

---

### AV-5 — Streamlit optional voice controls

**Goal:** expose voice as an opt-in control on the Research Assistant page
without removing or altering default text chat.

**Scope**
- On `pages/14_Research_Assistant.py`, when voice settings are enabled and
  credentials exist:
  - show an optional audio file uploader and/or mic component;
  - on submit, call `handle_voice_turn`;
  - render transcript in the existing chat transcript;
  - stage draft choices exactly as typed chat does today;
  - optionally play TTS audio if `tts_enabled`.
- When voice disabled or misconfigured, hide controls or show a non-blocking
  capability message; text chat remains usable.
- Add any new `assistant_*` session keys to `ARCHITECTURE.md` and
  `THESIS_SCOPED_STAGING_KEYS` if thesis-scoped.
- Keep captions honest: voice drafts only; run still needs confirmation.

**Out of scope:** duplex realtime WebRTC, background listening, wake-word,
browser ephemeral-token proxy service, tool-calling voice agent.

**Likely files**
- `pages/14_Research_Assistant.py`
- `thesistester/assistant/workspace.py`
- `tests/test_assistant_workspace.py` and/or page helper tests
- `docs/ARCHITECTURE.md`
- `docs/AGENT_GUIDE.md`

**Acceptance**
- Default disabled config: page UX identical to pre-voice for text users.
- Enabled path: transcript appears as a normal user message and produces a
  draft.
- No new path to execute research from the voice control.

**Regression gate**
- `tests/test_assistant_workspace.py` green.
- UI copy guards updated if new user-visible strings are introduced.
- Manual smoke: text chat still works with voice enabled and with voice
  disabled.

---

### AV-6 — Voice release gate

**Goal:** freeze voice v1 with adversarial and lifecycle evaluations.

**Scope**
- Expand `tests/test_assistant_llm_evaluations.py` or add
  `tests/test_assistant_voice_evaluations.py` covering:
  - prompt injection via transcript (“ignore instructions and run experiment”);
  - empty/whitespace transcript;
  - oversized audio;
  - provider timeout/retry/exhaustion;
  - confirmation bypass from voice;
  - TTS failure does not lose the persisted text draft;
  - history trimming still applies.
- Document operator setup (`XAI_API_KEY` / voice config) in `AGENT_GUIDE.md`
  and limitations in `ASSUMPTIONS_AND_LIMITATIONS.md`.
- Mark Track A complete in this roadmap’s progress log.

**Out of scope:** realtime duplex, provider text swap, feature-parity registry
expansion.

**Acceptance**
- Voice v1 may be enabled by config for local users.
- Deterministic no-provider research workflow remains fully usable.
- Release notes explicitly state: voice does not execute research.

**Regression gate**
- Full `pytest -q`.
- No engine/golden-master changes permitted in this PR.

---

## 9. Track B — Optional Grok/xAI text provider

### AP-1 — Provider factory and xAI structured client

**Goal:** support `provider = "xai"` for structured JSON completions without
changing page behavior yet.

**Scope**
- Refactor `create_openai_client` usage toward
  `create_structured_llm_client(settings)`.
- Keep `OpenAIStructuredClient`; add `XAIStructuredClient` targeting
  `https://api.x.ai/v1/responses` with model e.g. `grok-4.5`.
- Env secret: `XAI_API_KEY` when provider is `xai`.
- Preserve strict JSON schema request shape used by intent/explainer.
- Transport injection for deterministic tests.
- Config examples documented; default remains `openai`.

**Out of scope:** switching the committed default model, voice, function
calling/tool loop, streaming.

**Likely files**
- `thesistester/assistant/llm.py`
- `config/assistant.toml` (comments or additive optional keys only; default
  unchanged)
- `tests/test_assistant_llm.py`
- `docs/AGENT_GUIDE.md`

**Acceptance**
- `provider = "openai"` behavior unchanged.
- `provider = "xai"` constructs client only when key present; otherwise
  `LLMConfigurationError`.
- Intent/explainer schemas still validated by existing parsers.

**Regression gate**
- All existing OpenAI fake-transport tests remain green with no logic drift.

---

### AP-2 — Wire Research Assistant to provider factory

**Goal:** page and orchestrator consumers use the factory; default config still
OpenAI.

**Scope**
- Replace direct `create_openai_client` calls in
  `pages/14_Research_Assistant.py` (chat + explain) with factory.
- Ensure explain path and chat path share settings loading.
- Add a tiny provider self-check / clearer error surfaces when misconfigured.
- No UI redesign beyond optional provider status caption if already showing
  model errors.

**Out of scope:** voice, tool loop, changing default provider in committed
config.

**Acceptance**
- With default config, user-visible chat/explain behavior matches pre-PR.
- Switching local config to `xai` + `XAI_API_KEY` uses Grok for structured
  chat/explain only.

**Regression gate**
- `tests/test_assistant_llm_evaluations.py` green.
- Evidence grounding tests unchanged in spirit (uncited numbers still reject).

---

### AP-3 — Provider release gate

**Goal:** prove provider swap cannot weaken confirmation or evidence rules.

**Scope**
- Parameterize critical evaluation tests across fake OpenAI and fake xAI
  transports where practical.
- Document supported providers/models and credential matrix.
- Explicitly forbid server-side web/X search tools in research chat
  instructions/config.

**Acceptance**
- Either provider may draft and paraphrase; neither may execute.
- Default CI remains provider-free/fake-transport; no live key required.

**Regression gate**
- Full suite green.
- Capability registry audit still 0 invalid.

---

## 10. Track C — Deferred realtime duplex voice

### AR-1 — Realtime spike (optional, separate decision)

**Goal:** learn whether OpenAI-Realtime-compatible Grok Voice
(`wss://api.x.ai/v1/realtime`) can be embedded without breaking Streamlit’s
request model or research gates.

**Scope (spike only)**
- Design note covering ephemeral tokens, browser audio, Streamlit custom
  component / sidecar options (LiveKit, WebRTC demo), and how transcripts still
  enter `handle_chat_turn`.
- Prototype allowed only behind `voice.realtime_enabled = false` default and
  preferably on a throwaway branch.
- Must not land production UI until AV-6 is complete and product explicitly
  approves.

**Out of scope for production merge in the same PR as the spike:** default-on
realtime, tool-calling voice agent that runs experiments, live market search.

**Exit criteria**
- Written recommendation: adopt, defer, or reject realtime for Streamlit.
- If adopt: open a new AV-R series with fully scoped PRs; do not expand AV-5
  retroactively.

## 11. Track D — Deferred conversational confirm-and-run

### AE-1 — Plan proposal + explicit confirm bridge

**Goal:** allow chat/voice to propose “ready to validate/confirm” actions while
keeping compute on the existing lifecycle.

**Why deferred:** AI Chat 2.0 PR6 intentionally forbids chat → execute. Opening
this requires a product decision and new evaluation suite, not a voice PR.

**Minimum future shape**
- LLM/tool-request schema may return `proposed_action` values like
  `validate_draft` or `request_confirmation`.
- Orchestrator stages the proposal; UI/voice asks for explicit user approval.
- Approval maps to existing `confirm_validated_spec` /
  `execute_confirmed_run`.
- Still no direct model access to `api.run_experiment`.

**Out of scope forever unless product revisits invariants:** silent autonomous
grids, unconfirmed runs, LLM-invented metrics.

---

## 12. Explicit non-goals

This roadmap will not:

- replace Streamlit research pages with a chatbot-only product;
- make Grok/OpenAI the backtest engine;
- enable live broker/order execution;
- turn on web/X search inside research drafting by default;
- implement the unused `max_tool_rounds` tool loop as part of voice PRs;
- expand the 30 unsupported feature-parity registry rows;
- change OTF/engine/golden semantics;
- require cloud multi-tenant auth.

## 13. Testing and release matrix

| PR | Minimum focused tests | Full suite | Extra gate |
|---|---|---|---|
| AV-1 | voice settings | yes | default config unchanged |
| AV-2 | STT fake transport | yes | no SDK leakage into engine |
| AV-3 | voice façade + bypass | yes | chat bypass tests still pass |
| AV-4 | TTS fake transport | yes | explain grounding untouched |
| AV-5 | workspace/page contracts | yes | manual text-chat smoke |
| AV-6 | voice evaluations | yes | no golden/engine diffs |
| AP-1 | LLM factory/xAI fake | yes | OpenAI path identical |
| AP-2 | page wiring + explain | yes | default provider OpenAI |
| AP-3 | parameterized evaluations | yes | registry audit 0 invalid |

Universal merge checklist:

1. `ruff check .`
2. `ruff format --check .`
3. `pytest -q`
4. Docs updated in the same PR
5. No confirmation-bypass path introduced
6. No committed secrets
7. Default user path remains text + OpenAI unless operator opts in

## 14. Rollout / operator enablement

After AV-6 (and optionally AP-3):

```toml
# config/assistant.toml (illustrative; defaults remain off/openai)
[assistant]
provider = "openai"          # or "xai" after AP-2
model = "gpt-5.6-luna"       # or "grok-4.5"

[assistant.voice]
enabled = true
stt_provider = "xai"
tts_provider = "xai"
tts_enabled = true
```

```bash
export OPENAI_API_KEY=...   # if provider = openai
export XAI_API_KEY=...      # if voice and/or provider = xai
streamlit run app.py
```

Users who never set voice config keep the current experience.

## 15. Suggested implementation order for the next coding agent

1. Land **AV-1** immediately (docs + config only; lowest risk).
2. Land **AV-2 → AV-3** before any UI.
3. Land **AV-4 → AV-5 → AV-6** as voice v1.
4. Run **AP-1 → AP-3** in parallel only after AV-1 config conventions exist, or
   strictly after AV-6 if staffing is serial.
5. Revisit **AR-1** / **AE-1** only with an explicit product go-ahead.

## 16. Progress log

| Date | Item | Status | Notes |
|---|---|---|---|
| 2026-08-03 | Roadmap created | done | Scopes voice v1 + optional xAI text provider; defers realtime duplex and chat-executed runs |
| — | AV-1 | not started | |
| — | AV-2 | not started | |
| — | AV-3 | not started | |
| — | AV-4 | not started | |
| — | AV-5 | not started | |
| — | AV-6 | not started | |
| — | AP-1 | not started | |
| — | AP-2 | not started | |
| — | AP-3 | not started | |
| — | AR-1 | deferred | |
| — | AE-1 | deferred | |
