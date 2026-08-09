# Realtime Voice Agent — Implementation Contract

**Document type:** Implementation contract (VA-series) — **single source of truth for voice**
**Status:** VA-0…VA-6 complete — voice release gate closed (`enabled=false` by default)
**Date:** 2026-08-06
**Owner surface:** `thesistester/assistant/voice/` + Research Assistant page only
**Provider (speech):** xAI Grok Voice (`grok-voice-think-fast-2.0`; see §4)
**Provider (text channel logic):** existing OpenAI structured client for spoken
Discuss / Help turns that reuse `handle_results_turn` / `handle_help_turn`
**Depends on:**
- C2 complete (`docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` through PR6)
- RQ series complete (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` RQ-0…RQ-5)
- HC series complete (`docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` HC-0…HC-4)
  — Help **content/allowlist** substrate (`USER_GUIDE` + RQ §7.1.4); voice does
  not own or reopen HC
- `docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2

This is the **only** binding VA-series document for **voice transport**. Do
**not** create a parallel voice-transport roadmap. Amend this file in the same
PR that changes a freeze. Every VA PR must stay inside its scope table. If a
change is not listed under **In scope**, it belongs in a later PR or is
rejected.

**Duplex discuss-intelligence follow-on:** VA-5 full-duplex **content** parity
with DI overview/KPI intelligence is owned by
`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md` (DX-series, ✅ DX-0…DX-3). DX
enriched VA-3 tool envelopes and realtime honesty instructions by **reusing**
DI builders; it must not reopen VA provider/topology/TTL/default-on freezes or
fork DI cue/path rules. Do not reopen DX/VA casually for duplex intelligence —
amend the DX contract (and add a VA relationship note here only when a VA
freeze must change). Keep `tests/test_assistant_duplex_intelligence.py` §9
green beside VA-6.

### Why this document was rewritten (not left as a stale pre-RQ draft)

The previous VA contract was written **before** the RQ text substrate shipped.
Leaving it unchanged would drift against:

1. VA-1 / text Discuss results — **already implemented** as RQ-1.
2. Product help **channel** — **already implemented** as RQ-3 (voice should
   speak it too).
3. Classic Discuss deep-link — **already implemented** as RQ-4.
4. Honesty/injection eval freeze — **already implemented** as RQ-5.
5. Product intent clarified: voice should feel like **the same channels in
   speech**, not a second evidence dialect.

**Post-HC note (2026-08-06):** HC-0…HC-4 later widened Help **content**
(`docs/USER_GUIDE.md` + RQ §7.1.4 allowlist + §1.1 retrieval + §5 bank). That
does **not** reopen RQ-3 channel logic and does **not** change VA freezes —
spoken Help still calls `handle_help_turn` and inherits the expanded corpus.
VA must not fork corpus rules, invent parallel how-to docs, or weaken
`tests/test_assistant_help_coverage.py` parity/bank gates.

**Decision:** keep the same path (`docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md`)
and rewrite in place. Do **not** add a second voice plan file. Prior freezes
that remain valid are restated below; freezes that conflicted with “spoken RQ
channels” are amended explicitly in §0 / §11.

### Text substrate ownership (do not re-implement)

| Capability | Canonical home | Voice may |
|---|---|---|
| Multi-turn results Q&A | RQ-1 `results_qa` / `handle_results_turn` | Call it; never fork reply logic |
| Grid/time projections | RQ-2 `results_projections` | Inherit via results turns |
| Product help **channel** | RQ-3 `product_help` / `handle_help_turn` | Call it; never fork channel/grounding |
| Help **corpus content/allowlist** | HC (`USER_GUIDE` + RQ §7.1.4 / `help_corpus.py`) | Inherit via Help turns; never widen §7.1 or add voice-only corpus sources |
| Classic Discuss focus | RQ-4 `classic_focus_*` | Reuse navigation; no new focus keys |
| Honesty eval freeze | RQ-5 `test_assistant_llm_evaluations.py` | Extend with voice-specific gates only |
| Help coverage bank / parity | HC-4 `tests/test_assistant_help_coverage.py` | Keep green; do not bypass or duplicate |
| Discuss intelligence (text / PTT inherit) | DI (`docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md`) | PTT primary inherits via `handle_results_turn`; do not fork DI recovery into VA |
| Duplex content parity (VA-5) | DX (`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md`) | Enrich tool envelopes / realtime instructions only per DX; no provider swap; no live-PCM pre-gate |

VA-1 in this series is a **completed stub**. Do not open a parallel VA-1 PR.

---

## 0. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Product shape | Voice is a **spoken transport** over the shipped RQ honesty rules for Discuss results and Help — same channels, same fail-closed grounding, talking instead of typing |
| Results load path | Voice may use RO `BUNDLE.import` (evidence) via `explain_run` / results turns; never `execute_confirmed_run` / `PIPELINE.*` |
| Secrets | `XAI_API_KEY`: env → Secrets top-level → `[xai].api_key` (mirror OpenAI). Long-lived key never embeds in page modules or browser |
| Persistence | Voice sessions = sibling `voice_sessions/vs_[0-9a-f]{32}.json`; do not widen `Conversation` or reuse `_ID_RE` |
| Compare tool | Pure `compare_evidence` only — no `save_comparison` |
| UI attach | Completed-run expander (Discuss voice) + existing Help panel (Help voice); thesis `st.chat_input` untouched |
| Draft hydration | Results/help/voice messages must **omit** `choices` |
| Grounding | Reuse C2-6 / RQ digit-token rules; spoken trusted UI / TTS text must pass the same numeric audit (digit tokens). Spoken-word number phrases (“twelve”) are out of v1 audit scope |
| VA-4 path (**amended**) | Primary: STT → `handle_results_turn` or `handle_help_turn` → speak grounded reply via TTS. Secondary fallback (no OpenAI / unrecognized): deterministic VA-3 tool → template → TTS |
| VA-5 path | Browser ↔ localhost FastAPI sidecar ↔ xAI realtime WS; custom function tools only (VA-3 schemas); component deferred |
| Model / cost | Pin `grok-voice-think-fast-2.0`; budget ~$0.08/min S2S; no rolling `latest` in evals |
| Default | `assistant.voice.enabled = false` through VA-6 |

---

## 1. Definition of done

The series is done when a local user can:

1. Select a completed, hash-verified research run (or open Help).
2. Already discuss that run / ask product questions in **text** (RQ complete).
3. Opt in to voice from Research Assistant **sidebar Voice controls** (or
   `assistant.voice.enabled = true`) + `XAI_API_KEY`; OpenAI key still required
   for spoken Discuss/Help turns that reuse RQ handlers. Sidebar choices
   persist to gitignored `config/assistant.voice.override.toml`.
4. Use **push-to-talk** to ask the same classes of questions as Discuss results
   / Help and hear a grounded spoken reply (VA-4).
5. Optionally switch Mode to **realtime** for full-duplex spoken Q&A with model
   tool-calling via the localhost sidecar (VA-5).
6. Hear/see only numbers that resolve to the `EvidencePacket`, allowlisted
   tool returns, or Help corpus/registry grounding rules for that turn.
7. See a persisted transcript + tool/channel audit on the thesis conversation.
8. Fall back to deterministic Explain + text Discuss/Help if voice fails.

Voice remains **default-off** after VA-6 unless a separate, explicit enable
decision lands later.

---

## 2. Non-negotiable invariants

1. **No engine touch.** Do not modify `simulate_trades`, levels, signals,
   validation math, or golden fixtures in any VA PR.
2. **Additive only.** New modules under `thesistester/assistant/voice/` and
   narrow orchestrator/page additions. Legacy chat/explain/RQ paths keep
   current semantics when voice is disabled.
3. **Evidence-bound (results).** A results voice session binds exactly one
   `run_id` + expected `canonical_bundle_hash`. Hash mismatch fails closed.
4. **Read-only tools (realtime / fallback).** Voice tool calling may use only
   the VA-3 allowlist. Never `PIPELINE.*`, `execute_confirmed_run`, compute
   `dispatch`, filesystem, shell, broker, `web_search`, `x_search`,
   `file_search`, or `mcp`.
5. **Channel reuse.** Spoken Discuss must call `handle_results_turn` (or a
   thin façade that does). Spoken Help must call `handle_help_turn`. Do not
   re-implement packet grounding, projections, or corpus allowlists. Do not
   amend RQ §7.1 / HC USER_GUIDE coverage from VA PRs — corpus widen stays HC.
6. **Grounding.** Numeric tokens in spoken trusted output must resolve under
   the same RQ rules as text for that channel; else fail/flag before playback
   of a “trusted” answer (degraded remediation copy is allowed).
7. **Secrets.** `XAI_API_KEY` server-side / sidecar only. Realtime (VA-5)
   browser traffic goes to the localhost sidecar; the sidecar owns the
   upstream xAI connection.
8. **Default off.** `assistant.voice.enabled = false` in `config/assistant.toml`.
9. **Same-PR docs.** Every PR that adds behavior updates the docs listed in
   that PR’s scope. New `assistant_voice_*` session keys are documented in
   `ARCHITECTURE.md` in the same PR.
10. **CI green.** `ruff check .`, `ruff format --check .`, `pytest -q`.
11. **PR body.** Every VA PR includes a **Regression safety** paragraph.

---

## 3. Architecture (frozen)

```text
Research Assistant (opt-in Voice)
        │
        ├── Text Discuss / Help (RQ — already shipped) ─────────────┐
        ├── VA-4 PTT spoken channels:                               │
        │     STT → handle_results_turn / handle_help_turn → TTS   │
        │     fallback: intent → VA-3 tool → template → TTS         │
        └── VA-5 realtime: browser ↔ localhost sidecar ↔ xAI        │
                │                                                   ▼
        VoiceSessionService / voice tools                 AssistantOrchestrator
          bind run+hash; allowlisted RO tools               handle_results_turn
                                                            handle_help_turn
                                                            explain_run / BUNDLE.import
```

| Path | Role | Forbidden |
|---|---|---|
| `results_qa.py` / `handle_results_turn` | Text + spoken Discuss logic | Audio I/O, xAI, compute dispatch |
| `product_help.py` / `handle_help_turn` | Text + spoken Help logic | Run metrics unless remediation; web search |
| `thesistester/assistant/voice/contracts.py` | Schema-versioned records | I/O, Streamlit, network |
| `thesistester/assistant/voice/settings.py` | Load voice config + key resolution | UI |
| `thesistester/assistant/voice/session.py` | Session lifecycle + instruction build | Tool execution beyond allowlist |
| `thesistester/assistant/voice/xai_realtime.py` | STT/TTS + sidecar upstream helpers | Embedding keys in page code |
| `thesistester/assistant/voice/intent.py` | Deterministic VA-4 fallback router | Free-form NL as primary path |
| `thesistester/assistant/voice/tools.py` | Tool schemas + router (VA-3/VA-5) | Widening to write/compute |
| `thesistester/assistant/voice/grounding.py` | Numeric audit helpers for spoken text | Trusting raw model speech |
| `thesistester/assistant/voice/sidecar.py` | Localhost realtime WS + tool bridge | Non-localhost bind / multi-tenant auth |
| `pages/14_Research_Assistant.py` | Presentation only | Packet construction, secrets |

**Provider note:** Pin `grok-voice-think-fast-2.0` for speech. Thesis-draft chat
and RQ text/spoken channel logic stay on the existing OpenAI structured client
unless a later amendment says otherwise. VA-5 model tool-calling is xAI-native;
it must still execute only VA-3 tools and fail closed on ungroundable numbers.

---

## 4. Config contract (lands in VA-0)

Additive block only; do not reorder or rename existing `[assistant]` /
`[assistant.results_qa]` / `[assistant.product_help]` keys.

```toml
[assistant.voice]
enabled = false
provider = "xai"
model = "grok-voice-think-fast-2.0"   # pin dated id; do not use rolling latest in CI/evals
voice = "eve"
mode = "push_to_talk"              # VA-4; "realtime" added in VA-5
channels = ["results_qa", "product_help"]
max_session_minutes = 15
store_audio = false
allow_web_search = false
require_tool_for_numbers = true
ephemeral_token_ttl_seconds = 300
max_history_messages = 12
max_retries = 2
```

**Model pin policy:** Prefer dated `grok-voice-think-fast-2.0` (post 2026-08-05
`grok-voice-latest` cutover). Do not ship evals against rolling
`grok-voice-latest`. Budget Think Fast 2.0 speech-to-speech at about
**$0.08 / audio minute**. VA-4 also incurs unary STT/TTS plus OpenAI structured
cost for channel turns.

**Key policy:**

| Key | Required for |
|---|---|
| `XAI_API_KEY` | All voice modes (STT/TTS and/or realtime) |
| `OPENAI_API_KEY` | Spoken Discuss/Help turns that call RQ handlers (VA-4 primary) |
| Neither | Deterministic Explain / offline RQ disabled remediation (already shipped) |

Missing OpenAI during VA-4 primary Discuss/Help → clear remediation + optional
deterministic VA-3 fallback for results overview/caveats/metrics only (never
fabricate Help corpus answers).

---

## 5. Feasibility & PR count (executive)

### Is this straightforward now?

**Yes, relative to building Discuss/Help from scratch — with caveats.**

| Already done (RQ/C2) | Still to build (VA) |
|---|---|
| Evidence packet + grounding | xAI credential + STT/TTS clients |
| `handle_results_turn` / projections | Voice session bind + persistence |
| `handle_help_turn` + corpus allowlist | Deterministic fallback tools |
| Draft isolation / no `choices` | PTT UI + spoken grounding gate |
| Classic Discuss deep-link | Localhost realtime sidecar + tool bridge |
| Honesty/injection eval patterns | Voice eval freeze + ops docs |

Voice is **not** “flip a mic onto the text box.” It is a transport, session,
secret, and spoken-grounding series on top of a finished text substrate.

### How many PRs?

| ID | Status | Role |
|---|---|---|
| VA-1 | ✅ Done via RQ-1 | Text Discuss substrate |
| VA-0 | ✅ Done | Contracts + flag + docs freeze |
| VA-2 | ✅ Done | xAI credentials + session service + STT/TTS helpers |
| VA-3 | ✅ Done | Read-only voice tools + grounding helpers |
| VA-4 | ✅ Done | Push-to-talk spoken Discuss/Help (first user-visible) |
| VA-5 | ✅ Done | Full-duplex realtime sidecar |
| VA-6 | ✅ Done | Voice evals + release gate |

**Remaining implementation PRs: 0.** VA-0 ✅ / VA-2 ✅ / VA-3 ✅ / VA-4 ✅ / VA-5 ✅ / VA-6 ✅.

Do **not** collapse VA-4 into VA-5. Half-duplex spoken channels prove value and
honesty first. Do **not** reopen RQ for voice features.

### Difficulty (technical, not calendar)

| PR | Invasiveness | Main risk |
|---|---|---|
| VA-0 | Trivial | Config loader edge cases |
| VA-2 | Low–medium | Secret resolution; session id / store shape |
| VA-3 | Medium | Allowlist discipline; compare fail-closed |
| VA-4 | Medium | Dual-key UX; speaking RQ replies without leaking uncited digits; Streamlit audio |
| VA-5 | Highest | Sidecar lifecycle + WS tool bridge + Streamlit reruns |
| VA-6 | Low | Eval completeness only |

Optional product stop after VA-4 is allowed: mark VA-5 deferred in VA-6 docs if
product chooses half-duplex-only for v1.

---

## 6. PR sequence overview

```text
VA-0 ──► VA-2 ──► VA-3 ──► VA-4 ──► VA-5 ──► VA-6
              ▲
              └── VA-1 already satisfied by RQ-1…RQ-5
```

| # | ID | Goal | Hard reject if… |
|---|---|---|---|
| 1 | VA-0 | Contracts + flag + docs freeze | Any network/UI/orchestrator behavior |
| 2 | VA-2 | Credentials + session + STT/TTS helpers | Tool router or Streamlit mic |
| 3 | VA-3 | Read-only voice tools | UI enablement or realtime WS client |
| 4 | VA-4 | PTT spoken Discuss/Help | Full-duplex / custom component |
| 5 | VA-5 | Full-duplex realtime mode | Telephony, multi-tenant, audio blob store |
| 6 | VA-6 | Evals + release gate | Flipping default `enabled=true` |

VA-2 and VA-3 must not enable mic UI. VA-4 requires VA-2+VA-3. VA-5 requires
VA-4. VA-6 requires VA-5 **or** an explicit “VA-5 deferred” amendment if product
stops at half-duplex.

---

## 7. Detailed PR scopes

### VA-0 — Contracts, flag, docs freeze

**Goal:** Freeze schemas and defaults with zero runtime behavior change.

#### In scope
| Item | Detail |
|---|---|
| Docs | This file is canonical; update `ENGINEERING_ROADMAP.md` voice row; assumptions note; architecture note that `assistant_voice_*` keys are reserved |
| Config | Add `[assistant.voice]` to `config/assistant.toml` exactly as §4 |
| Code | `thesistester/assistant/voice/__init__.py` (exports only) |
| Code | `voice/contracts.py` — `VoiceSessionRecord`, `VoiceTranscriptTurn`, `VoiceToolInvocation`, `GroundingVerdict` (schema_versioned) |
| Code | `voice/settings.py` — `load_voice_settings()`; missing section → `enabled=False` safe defaults; non-boolean `enabled` fails closed |
| Tests | `tests/test_assistant_voice_contracts.py` — schema round-trip, defaults, enabled=false |

#### Out of scope
- Any call to xAI / OpenAI / WebSocket
- Changes to `orchestrator.py`, `llm.py`, pages
- Session_state keys
- Enabling UI affordances

#### Acceptance
- [x] `load_voice_settings().enabled is False` on current config
- [x] `load_llm_settings()` / RQ settings loaders still succeed with `[assistant.voice]` present
- [x] Existing RQ/C2 tests green; no new third-party dependency
- [x] `ruff` + `pytest -q` green

#### Regression safety
Additive package + config defaults. No engine, no golden, no C2/RQ path edits.
If `assistant.voice` is absent, settings loader behaves as disabled.

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
docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md   # ownership pointer only
docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md     # related-docs / VA↔HC pointer only
```

#### Implemented contract (fill when merged)
- `config/assistant.toml` ships `[assistant.voice]` exactly as §4 with
  `enabled = false`.
- Package `thesistester/assistant/voice/` exports schema-versioned
  `VoiceSessionRecord`, `VoiceTranscriptTurn`, `VoiceToolInvocation`,
  `GroundingVerdict` plus `load_voice_settings()` (missing section → disabled
  safe defaults; non-boolean `enabled` fails closed).
- Contract `from_dict` paths fail closed: missing required keys raise
  `VoiceContractError` (not bare `KeyError`); `provider`/`model`/`voice` reject
  null/non-string values; transcript turn `channel` must match the session
  channel (no mixed histories).
- `tests/test_assistant_voice_contracts.py` gates schema round-trip, tracked
  defaults, RQ/LLM loader coexistence, and the fail-closed parse rules above.
- No network, UI, orchestrator, session_state, or third-party dependency
  changes. Runtime STT/TTS/session/tools remain VA-2+.

---

### VA-1 — Text substrate — **completed via RQ (+ HC Help corpus)**

**Do not implement from this section.**

| Item | Pointer |
|---|---|
| Discuss results | RQ-1 (`results_qa` / `handle_results_turn`) |
| Projections | RQ-2 (`results_projections`) |
| Product help **channel** | RQ-3 (`product_help` / `handle_help_turn`) |
| Help **corpus content** | HC-0…HC-4 (`docs/USER_GUIDE.md` + RQ §7.1.4) |
| Classic focus | RQ-4 (`classic_focus_channel`) |
| Honesty evals | RQ-5 (`test_assistant_llm_evaluations.py`) |
| Help coverage freeze | HC-4 (`tests/test_assistant_help_coverage.py`) |

#### Implemented contract (via RQ-1…RQ-5 + HC-0…HC-4)
- Text Discuss + Help channel + classic deep-link + honesty freeze are shipped
  (RQ). Help feature/how-to corpus coverage is shipped (HC).
- Voice PRs must call RQ handlers; spoken Help inherits HC corpus via
  `handle_help_turn`. Do not re-implement results/help logic or corpus rules.
- Voice series proceeds from VA-0 / VA-2+.

---

### VA-2 — xAI credentials + session service + STT/TTS helpers

**Goal:** Server-side session + credential + unary speech primitives. No mic UI.

#### In scope
| Item | Detail |
|---|---|
| Code | `voice/xai_realtime.py` — ephemeral token mint (`POST /v1/realtime/client_secrets`); unary STT (`POST /v1/stt`) and TTS (`POST /v1/tts`) helpers; stdlib/`urllib` or existing HTTP style from `llm.py`; 30s timeout; retries from settings |
| Code | `voice/session.py` — `VoiceSessionService.create_session(thesis_id, run_id|None, *, expected_hash|None, mode, channel)` binds results sessions to hash-verified packet; Help sessions bind thesis/conversation only (no packet). Persist `VoiceSessionRecord`; build honesty instructions |
| Persistence | `assistant/theses/{thesis_id}/voice_sessions/{session_id}.json` with `kind: "voice_session"` and `vs_[0-9a-f]{32}` ids. Do **not** widen `Conversation` |
| Code | `end_session` marks ended; flush transcript turns via conversation append / tool_entry (best-effort) |
| Code | Key resolution: env → Secrets `XAI_API_KEY` → `[xai].api_key`; reject placeholders |
| Tests | `tests/test_assistant_voice_session.py` — mock HTTP; no/placeholder key; bad hash; missing run; Help session without run; instruction policy strings; session id format |

#### Out of scope
- Tool JSON schemas / execution (VA-3)
- Streamlit widgets / mic
- Browser WebSocket client
- Live network in CI

#### Acceptance
- [x] Mint without key → structured fail closed
- [x] Results session without verified bundle → fail closed
- [x] Instructions always include: evidence/docs-only, no trade advice, numbers only from tools/packet/corpus rules, sample-size/OOS caveats for results
- [x] No `XAI_API_KEY` appears in any page module
- [x] OpenAI `llm.py` untouched except if a shared HTTP helper extract is required (prefer not)

#### Regression safety
New modules only. Flag still false → no user-visible change. C2/RQ OpenAI
paths untouched.

#### Files allowed to touch
```
thesistester/assistant/voice/xai_realtime.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/settings.py
thesistester/assistant/voice/contracts.py
thesistester/assistant/voice/__init__.py
thesistester/assistant/repository.py            # only if persisting sessions needs store helpers
tests/test_assistant_voice_session.py
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/ARCHITECTURE.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
```

#### Implemented contract (fill when merged)
- `voice/xai_realtime.py`: `require_xai_api_key()` (env → Secrets
  `XAI_API_KEY` → `[xai].api_key`; placeholders rejected),
  `mint_ephemeral_token` (`POST /v1/realtime/client_secrets`), unary
  `speech_to_text` / `text_to_speech` with stdlib urllib transports, 30s
  timeout, retries from settings. Injectable transports; no live network in CI.
- `voice/session.py`: `VoiceSessionService.create_session` /
  `end_session` / transcript append; results sessions bind hash-verified
  `EvidencePacket` via `AssistantTools.build_bundle_evidence_packet`; Help
  sessions omit run/hash. Honesty instructions always include
  evidence/docs-only, no trade advice, numbers-only-from-tools/packet/corpus,
  and sample-size/OOS caveats for results.
- Persistence: `LocalThesisRepository.save_voice_session` /
  `get_voice_session` under `theses/{thesis_id}/voice_sessions/vs_*.json`
  (`kind: voice_session`); does not widen `Conversation` or reuse `_ID_RE`.
  Saves validate via `VoiceSessionRecord.from_dict`, use optimistic
  ``revision`` concurrency, and map invalid `vs_` ids to
  `AssistantRepositoryError`. Optional bound `conversation_id` is persisted.
  `end_session` best-effort flushes transcript/tool audits via
  `append_conversation_message` (messages omit `choices`; flush is idempotent).
- xAI helpers fail closed on empty/placeholder explicit `api_key=` and reject
  CR/LF/`"` tokens in multipart filename/fields.
- Results bind resolves bundle paths inside `AssistantTools.data_roots` before
  any byte read; hash verification stays in `build_bundle_evidence_packet`.
- `tests/test_assistant_voice_session.py` gates key fail-closed, mocked HTTP,
  bad/missing hash, Help-without-run, instruction policy strings, `vs_` ids,
  and no `XAI_API_KEY` in page modules.
- Flag still `enabled=false`; no mic UI / tool router (VA-3/VA-4).

---

### VA-3 — Read-only voice tool surface

**Goal:** Freeze the only functions the realtime model (and VA-4 fallback) may
invoke outside RQ channel handlers.

#### In scope
| Item | Detail |
|---|---|
| Code | `voice/tools.py` — `VOICE_TOOL_SCHEMAS` + `execute_voice_tool(name, args, *, session) -> dict` |
| Tools (exact v1 set) | `get_run_overview` → report/caveats from **cached bound packet** |
| | `get_metric` → `{path}` typed value; unknown/empty/`..` fail |
| | `list_caveats` → packet caveats |
| | `compare_two_runs` → `{other_run_id}` hash-verify + `compare_evidence`; **no** `save_comparison` |
| Deny | Anything else, including search/`mcp`/`PIPELINE.*`/`execute_confirmed_run` |
| Audit | Each call → one session `VoiceToolInvocation` + best-effort conversation `tool_transcript` when `conversation_id` is bound |
| Grounding helper | `voice/grounding.py` — reuse C2-6 / RQ token normalization; digit-token audit for spoken strings (claim **values** only) |
| Tests | `tests/test_assistant_voice_tools.py` — allowlist, deny, path traversal, compare hash fail, injection names, grounding cases |

#### Out of scope
- Enabling `assistant.voice.enabled`
- UI / mic / WebSocket client
- Replacing RQ channel handlers
- Registry expansion beyond calling existing orchestrator read APIs

#### Acceptance
- [x] Unknown tool name → fail; no side effects
- [x] Model-requested `execute_confirmed_run` / `web_search` never execute
- [x] `get_metric` rejects unknown/empty paths
- [x] `compare_two_runs` fails closed on hash missing/mismatch
- [x] Exactly one transcript audit row per invocation attempt

#### Regression safety
Thin adapters over existing explain/compare/packet. No page behavior while
flag is false.

#### Files allowed to touch
```
thesistester/assistant/voice/tools.py
thesistester/assistant/voice/grounding.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/__init__.py
tests/test_assistant_voice_tools.py
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
docs/AGENT_GUIDE.md
```

#### Implemented contract (fill when merged)
- `voice/tools.py`: frozen `VOICE_TOOL_SCHEMAS` for exact v1 set
  (`get_run_overview`, `get_metric`, `list_caveats`, `compare_two_runs`) plus
  `execute_voice_tool(name, args, *, session=VoiceToolSession)`.
- Deny-by-default: unknown / injection names (`web_search`,
  `execute_confirmed_run`, `PIPELINE.*`, `mcp`, `save_comparison`, …) fail
  closed with no tool side effects beyond one audit row.
- `get_metric` rejects empty paths, `..` / separators, unknown roots, missing
  paths, empty values, and non-scalar (object/array) leaves.
  `compare_two_runs` hash-verifies the other run via
  `build_bundle_evidence_packet` and returns pure `compare_evidence` with
  `persisted=false` (never `save_comparison`).
- Each invocation attempt appends exactly one `VoiceToolInvocation` on the
  voice session record (success or failure; durable after `end_session`) and
  best-effort flushes one conversation `tool_transcript` entry when a
  `conversation_id` is bound. Bound packets rehydrate across service instances
  from persisted run/hash.
- `voice/grounding.py`: `audit_spoken_text` reuses C2-6 / RQ
  `_normalize_number_token` / digit-token rules and returns `GroundingVerdict`
  with claim-value allowlists (caveat/hash strings do not launder metrics).
- `tests/test_assistant_voice_tools.py` gates allowlist, deny, path traversal,
  compare hash fail, injection names, and grounding cases.
- Flag still `enabled=false`; no mic UI (VA-4).

---

### VA-4 — Push-to-talk spoken Discuss / Help

**Goal:** First user-visible voice loop that feels like **the same writing
channels, spoken**. Free-form duplex remains VA-5.

#### In scope
| Item | Detail |
|---|---|
| UI | Opt-in Voice controls: (a) inside completed-run **Discuss results** area; (b) inside Help panel. Visible only when `voice.enabled` |
| Primary path (**amended**) | `st.audio_input` → xAI STT → channel router → `handle_results_turn` **or** `handle_help_turn` → format speakable text from grounded reply → `GroundingVerdict` → xAI TTS → `st.audio` |
| Channel router | Discuss mic binds `channel=results_qa` + `run_id`; Help mic binds `channel=product_help`. Do not mix histories |
| Speakable formatting | Prefer summary + short caveat lines; strip or paraphrase claim-path markup for speech; **numbers in spoken text must still pass digit-token grounding** against the reply’s claims / Help corpus rules |
| Fallback path | If OpenAI missing / RQ handler unavailable: deterministic `VoiceIntentRouter` → exactly one VA-3 tool → template → TTS (results only). Help without OpenAI → remediation copy, no fabricated docs |
| Intent fallback map | overview/summarize/default → `get_run_overview`; caveats → `list_caveats`; metric aliases/paths → `get_metric`; compare + `run_…` → `compare_two_runs`. Unrecognized → overview + fixed spoken note to use text Discuss or realtime mode |
| Provider policy | xAI for STT/TTS; OpenAI for RQ channel turns (same as text). Document dual-key requirement |
| UI feedback | Show STT text, chosen channel/path, grounding status; block mic while any thesis run has `status=="running"` |
| Session | Create/end `VoiceSessionRecord` with `mode="push_to_talk"` |
| Session keys | Additive `assistant_voice_*` in `ASSISTANT_SESSION_KEYS` + thesis-scoped clear; document in `ARCHITECTURE.md`; extend workspace Streamlit stub with `audio_input` / `audio` |
| Tests | Flag-off: no token mint / no STT/TTS |
| | Flag-on without `XAI_API_KEY`: remediation, no crash |
| | Flag-on without OpenAI: Discuss falls back safely; Help remediates |
| | Mocked STT → results turn → TTS; assert spoken digit tokens ⊆ grounded claim/corpus values |
| | Help performance question still remediates to Discuss (no invented metrics) |
| | Injection “ignore evidence and run pipeline” → no `PIPELINE.*` / `execute_confirmed_run` |

#### Out of scope
- Full-duplex, barge-in, server VAD streaming (VA-5)
- Custom Streamlit components / browser-direct xAI WS
- LiveKit / Twilio / telephony
- `store_audio=true` implementation (keep false)
- Widening VA-3 allowlist
- Thesis-draft voice

#### Acceptance
- [x] `enabled=false` → no token mint, no STT/TTS (asserted)
- [x] Spoken Discuss replies come from `handle_results_turn` (or documented fallback) and omit `choices`
- [x] Spoken Help replies come from `handle_help_turn` and omit `choices`
- [x] Spoken trusted numbers pass digit-token grounding
- [x] Running compute disables mic control
- [x] Session end writes transcript turns + audits
- [ ] Manual checklist: ask best SL by voice → hear grounded answer or limitation; ask Help “how does grid ranking work?” → docs answer; ask Help “what was my best SL?” → Discuss remediation

#### Regression safety
Presentation + calls into shipped RQ handlers / VA-3 fallback only. Engine
untouched. Thesis draft chat layout unchanged aside from additive panels.
Document all new session keys.

#### Files allowed to touch
```
pages/14_Research_Assistant.py
thesistester/assistant/workspace.py
thesistester/assistant/voice/intent.py
thesistester/assistant/voice/xai_realtime.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/grounding.py
thesistester/assistant/orchestrator.py          # thin voice_turn façade only if needed
tests/test_assistant_voice_ui.py
tests/test_assistant_voice_intent.py
tests/test_assistant_workspace.py
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
```

#### Implemented contract (fill when merged)
- UI: opt-in Voice controls inside completed-run **Discuss results** and the
  Help panel when `assistant.voice.enabled=true` (still default `false`).
- Primary path: `st.audio_input` → xAI unary STT →
  `AssistantOrchestrator.handle_voice_ptt_turn` →
  `handle_results_turn` / `handle_help_turn` → speakable formatting →
  `GroundingVerdict` → xAI unary TTS → `st.audio`.
- Fallback (results, no OpenAI / RQ unavailable): `VoiceIntentRouter` → exactly
  one VA-3 tool → unwrap `execute_voice_tool` envelope → template → TTS.
  RQ non-completed responses remediate (no silent fallback). Help without
  OpenAI remediates (no fabricated docs). Perf questions still remediate to
  Discuss. Primary RQ calls use `persist_conversation=False` so voice flush
  owns a single channel history write.
- Session: short-lived `VoiceSessionRecord` with `mode="push_to_talk"`;
  transcript + audits flush on end. No ephemeral token mint on the PTT path.
- Session keys: `assistant_voice_results_sessions`,
  `assistant_voice_help_session_id`, `assistant_voice_last_turn`,
  `assistant_voice_playback` (thesis-scoped clear; documented in ARCHITECTURE).
- Mic blocked while any thesis run has `status=="running"`.
- Tests: `tests/test_assistant_voice_intent.py`,
  `tests/test_assistant_voice_ui.py` (flag-off, missing keys, primary/fallback,
  Help remediation, injection deny, digit grounding).

---

### VA-5 — Full-duplex realtime (Grok Voice WebSocket)

**Goal:** Sub-second duplex review with server VAD and barge-in, still
allowlist-bound.

#### In scope
| Item | Detail |
|---|---|
| Transport topology | **Browser mic/speaker ↔ localhost FastAPI sidecar ↔ xAI Realtime WS.** Sidecar holds `XAI_API_KEY` (or mints ephemeral tokens server-side). Streamlit only starts/shows session controls and never opens the xAI socket. Custom component / browser-direct-to-xAI deferred |
| Why sidecar | Streamlit’s rerun model cannot host a long-lived duplex tool bridge reliably |
| Session | Sidecar `session.update` with voice, instructions from `VoiceSessionService`, `turn_detection: server_vad`, **custom function tools only** (VA-3 schemas); payload must omit `web_search`, `x_search`, `file_search`, `mcp` |
| Tool bridge | On `function_call` → `execute_voice_tool` → `function_call_output` (same Python package; no duplicated business logic) |
| Channel policy | Realtime results sessions are run-bound. Help-corpus answering in realtime v1 is **optional**; if included, must call the same Help grounding path or refuse with remediation — do not invent a third help dialect |
| Auth | Sidecar binds `127.0.0.1` only; single trusted local user |
| Audio | PCM 24 kHz as required by xAI; no raw audio persistence |
| Config | Allow `mode = "realtime"`; push-to-talk remains fallback |
| Transcript | Sync user/assistant text + tool audits on session end; periodic flush best-effort |
| TTL | Enforce `max_session_minutes` |
| Tests | Mocked WS fixtures for tool bridge; TTL; deny search tools in session payload; non-localhost bind rejected |
| Docs | `docs/VOICE_SIDECAR_OPS.md` localhost sidecar run instructions |

#### Out of scope
- Phone/Twilio
- Multi-user auth
- Default `enabled=true`
- Widening tool allowlist
- Replacing VA-4 (keep as fallback)

#### Acceptance
- [x] Session payload never includes search/`mcp` tools when disabled
- [x] Tool bridge cannot invoke names outside VA-3 allowlist
- [x] Token never logged; key never sent to browser
- [x] Exceeding `max_session_minutes` ends session
- [ ] Manual QA: barge-in, silence, “what’s win rate?”, injection “run a grid” → refused

#### Regression safety
New transport/UI only. RQ text channels remain source of truth for typed Q&A.
VA-3 allowlist unchanged. Engine/golden untouched.

#### Files allowed to touch
```
thesistester/assistant/voice/xai_realtime.py
thesistester/assistant/voice/session.py
thesistester/assistant/voice/tools.py
thesistester/assistant/voice/sidecar.py
pages/14_Research_Assistant.py
tests/test_assistant_voice_realtime.py
docs/ARCHITECTURE.md
docs/ASSUMPTIONS_AND_LIMITATIONS.md
docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md
docs/VOICE_SIDECAR_OPS.md
```

#### Implemented contract (fill when merged)
- `voice/sidecar.py`: localhost Starlette ASGI sidecar (uvicorn) — browser ↔
  sidecar ↔ xAI Realtime WS. Binds `127.0.0.1` / `::1` only.
- `session.update` uses honesty instructions + `turn_detection: server_vad` +
  PCM 24 kHz binary transport + input transcription (`grok-transcribe`) +
  **VA-3 function tools only**; `web_search` / `x_search` / `file_search` /
  `mcp` are rejected by `assert_realtime_tools_allowlisted`.
- Tool bridge: `response.function_call_arguments.done` →
  `execute_voice_tool` → `function_call_output` + `response.create`; empty
  `call_id` is skipped (fail closed). Browser→upstream forwards only audio
  buffer / `response.cancel` events (no forged `conversation.item.create`).
- TTL: `session_exceeded_ttl` / `max_session_minutes` ends active sessions
  (idempotent end + upstream close so peer pumps unblock).
- Assistant realtime transcript text is digit-audited against the bound packet
  + tool returns before durable persistence (`realtime_ungrounded` remediation
  replaces uncited numbers). Live PCM cannot be pre-gated once uttered.
- Client HTML initializes `mediaStream` with JS `null` (not Python `None`).
- Streamlit (when `assistant.voice.mode = "realtime"`) registers sessions via
  `POST /v1/sessions` and opens the sidecar `/client` page; host/`client_url`
  must be loopback; never opens xAI WS and never embeds `XAI_API_KEY`. PTT
  remains available as fallback.
- Streamlit probes `GET /health` before register and exposes **Launch local
  sidecar** (`ensure_local_sidecar`) so WinError 10061 / connection-refused
  is recoverable without leaving the page. Launch remains loopback-only and
  inherits env for `XAI_API_KEY` (never embeds the key in page code).
- Help realtime deferred (results_qa run-bound only in v1).
- Tests: `tests/test_assistant_voice_realtime.py`.
- Ops: `docs/VOICE_SIDECAR_OPS.md` sidecar run instructions.

---

### VA-6 — Evaluation suite + release gate

**Goal:** Close the research-integrity gate for voice. Do **not** flip default-on.

#### In scope
| Item | Detail |
|---|---|
| Tests | `tests/test_assistant_voice_evaluations.py`: forbidden tool/injection; uncited spoken/transcript numbers; hash mismatch on session create; token mint failures; max session duration; spoken Discuss/Help omit `choices`; draft history still excludes voice/channel tags; voice cannot execute/confirm runs; flag-off no side effects; Help performance still remediates |
| Docs | Assumptions (shipped limitations), `AGENT_GUIDE.md` (VA PR rules), `ENGINEERING_ROADMAP.md` (VA ✅ or “VA-5 deferred”), this file (release gate closed). Optional `METRICS_GLOSSARY.md` spoken display note if needed |
| Ops | Budget ~$0.08/min S2S (+ STT/TTS + OpenAI for VA-4 channel turns); `max_session_minutes` guidance |
| Flag | Leave `enabled=false`; document opt-in steps |

#### Out of scope
- New features / extra tools
- Provider swap for thesis chat
- Default enable

#### Acceptance
- [x] Full suite green including RQ-5 / C2-6 evals
- [x] Voice eval file fails CI if allowlist or grounding regresses
- [x] Deterministic explain/compare usable with zero voice/xAI config
- [x] Release checklist in PR body completed

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
- [x] §4.2 items for assistant-surface PR
- [x] No golden file diffs
- [x] `enabled` still false
- [ ] Manual half-duplex smoke (and duplex if VA-5 shipped) recorded in PR notes
- [x] Cost/privacy assumptions updated

#### Implemented contract (fill when merged)
- `tests/test_assistant_voice_evaluations.py` freezes VA honesty/injection/
  grounding: forbidden tools, uncited spoken digits (PTT + realtime durable
  assistant transcripts), hash-mismatch bind, token-mint fail-closed, TTL,
  flag-off no STT/mint/sidecar register, spoken Discuss/Help omit `choices`,
  draft history excludes voice/channel tags, Help performance remediation,
  deterministic explain/compare with zero xAI, realtime client HTML has no
  Python `None` leak.
- Default remains `assistant.voice.enabled = false` (asserted against
  `config/assistant.toml`).
- Docs: Assumptions (shipped limitations + opt-in/budget), AGENT_GUIDE (VA
  complete), ENGINEERING_ROADMAP (VA ✅), METRICS_GLOSSARY spoken note, this
  file (release gate closed).

---

## 8. Per-PR regression-safety template (copy into every VA PR body)

```markdown
## Regression safety
- Engine / levels / signals / goldens: untouched
- C2 thesis chat (`handle_chat_turn`): untouched
- RQ text Discuss/Help handlers: called, not forked (unless this PR is a
  narrowly scoped bugfix revealed by voice evals)
- Voice flag default: false
- New behavior requires: <flag / completed run / keys>
- Results/help/voice messages omit `choices`
- Tests gating this PR: <list>
- Docs updated this PR: <list>
```

---

## 9. Explicit non-goals (series-wide)

- Voice-driven strategy generation or autonomous grid/WFA
- Live trading / broker commands
- Replacing classic Streamlit workflows
- Multi-tenant auth / cloud sync
- Persisting raw microphone audio by default
- Enabling xAI web/X search on results sessions
- Migrating drafting chat off OpenAI
- Thesis-draft voice (voice is Discuss/Help only in v1)
- Any `simulate_trades` / levels / golden change
- Reopening RQ for voice features

---

## 10. Testing matrix

| Gate | VA-0 | VA-2 | VA-3 | VA-4 | VA-5 | VA-6 |
|---|---|---|---|---|---|---|
| ruff + pytest | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| No golden diffs | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Schema/unit | ✓ | | | | | |
| Session / mock HTTP | | ✓ | | | | ✓ |
| Tool allowlist | | | ✓ | ✓ | ✓ | ✓ |
| Spoken RQ channel path | | | | ✓ | | ✓ |
| Flag-off no mint | | | | ✓ | ✓ | ✓ |
| Mocked WS tool bridge | | | | | ✓ | ✓ |
| Full voice eval file | | | | | | ✓ |

---

## 11. Closed decisions (frozen; amend only with docs PR)

| # | Decision | Frozen default |
|---|---|---|
| 1 | VA-4 STT/TTS | xAI unary STT + TTS |
| 2 | VA-4 primary answer path | STT → RQ `handle_results_turn` / `handle_help_turn` → grounded speak → TTS |
| 3 | VA-4 fallback | Deterministic intent → VA-3 tool → template → TTS (results); Help remediates if no OpenAI |
| 4 | VA-5 transport | Browser ↔ **localhost FastAPI sidecar** ↔ xAI (component deferred) |
| 5 | Default voice id | `eve` |
| 6 | `compare_two_runs` in v1 allowlist | **include** (pure `compare_evidence`; no persist) |
| 7 | Model pin string | `grok-voice-think-fast-2.0` (not rolling `latest`) |
| 8 | Voice session persistence | Sibling `voice_sessions/` docs with `vs_` ids |
| 9 | Free-form duplex NL | **VA-5 only**; VA-4 is half-duplex channel transport |
| 10 | Dual keys | `XAI_API_KEY` required for speech; `OPENAI_API_KEY` required for primary spoken RQ turns |

Changing these defaults requires a docs amendment in the PR that changes them.

---

## 12. Agent instructions (for implementers)

When implementing any VA PR:

1. Read **only** this document’s section for that VA ID (plus §0 freezes).
2. Touch **only** files in **Files allowed to touch** (plus test fixtures they
   need). Ask for a contract amendment PR before expanding the file list.
3. Keep work regression-safe per §2 and `docs/ENGINEERING_PROPOSAL.md` §4.
4. Update documentation in the **same** PR — amend this file; do not add a
   second voice roadmap.
5. Do not enable voice by default.
6. Do not add search tools or compute tools “for convenience.”
7. Results/voice may use RO `BUNDLE.import` (evidence); never
   `execute_confirmed_run` / `PIPELINE.*`.
8. Results/help/voice messages must not include `choices`.
9. Prefer calling shipped RQ handlers over inventing parallel spoken dialects.
10. Keep HC Help coverage/parity gates green; do not widen §7.1 from VA PRs.
11. Fill **Implemented contract** under that VA section when merging.

### Copy-ready kickoff prompt (VA-0)

```markdown
Implement VA-0 from docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md exactly.

Constraints:
- Contracts/config/docs freeze only. No network, UI, orchestrator, or mic behavior.
- Follow the PR’s Files allowed to touch list.
- Add [assistant.voice] to config/assistant.toml exactly as §4 (enabled=false).
- Add thesistester/assistant/voice/{__init__,contracts,settings}.py with
  load_voice_settings() safe defaults when the section is missing.
- Do not implement STT/TTS, tools, or page widgets.
- Same-PR docs: ENGINEERING_ROADMAP voice status, ASSUMPTIONS note, ARCHITECTURE
  reserved assistant_voice_* keys, AGENT_GUIDE pointer, fill VA-0 Implemented.
- Keep HC Help coverage/parity gates green; do not widen §7.1 or reopen HC.
- PR body must include a Regression safety paragraph.
- Keep ruff + pytest green. No new third-party dependency.
```

---

## 13. References

- xAI Voice Agent: https://docs.x.ai/developers/model-capabilities/audio/voice-agent
- Speech-to-speech: https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech
- Ephemeral tokens: https://docs.x.ai/developers/model-capabilities/audio/ephemeral-tokens
- Launch / Think Fast 2.0: https://x.ai/news/grok-voice-think-fast-2
- RQ contract (text channel substrate): `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`
- HC contract (Help corpus content/allowlist): `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md`
- C2 grounding gate: `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md`
- Regression framework: `docs/ENGINEERING_PROPOSAL.md` §4
- `thesistester/assistant/results_qa.py`
- `thesistester/assistant/product_help.py`
- `thesistester/assistant/help_corpus.py`
- `thesistester/assistant/llm_explainer.py`
- `thesistester/assistant/orchestrator.py`
- `pages/14_Research_Assistant.py`
- Help coverage freeze: `tests/test_assistant_help_coverage.py`

---

## 14. Status ledger

| ID | Status |
|---|---|
| VA-1 (text Discuss via RQ-1) | ✅ Implemented (RQ) |
| RQ help/projections/focus/evals | ✅ Implemented (RQ-2…RQ-5) — voice depends, does not re-own |
| HC Help corpus coverage | ✅ Implemented (HC-0…HC-4) — spoken Help inherits; VA does not re-own |
| VA-0 | ✅ Implemented (contracts/flag/docs freeze) |
| VA-2 | ✅ Implemented (credentials + session + STT/TTS helpers) |
| VA-3 | ✅ Implemented (read-only tools + grounding helpers) |
| VA-4 | ✅ Implemented (PTT spoken Discuss/Help) |
| VA-5 | ✅ Implemented (localhost realtime sidecar) |
| VA-6 | ✅ Implemented (evals + release gate; default remains off) |
