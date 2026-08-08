# Duplex Intelligence — Implementation Contract

**Document type:** Implementation contract (DX-series) — **single source of truth**
**Status:** ✅ **DX-0…DX-3 complete** (release gate frozen)
**Date:** 2026-08-08
**Owner surface:** `thesistester/assistant/results_overview.py`
(`has_overview_negative_cue` export only — no cue-table edits),
`voice/tools.py`, `voice/intent.py` (sample-size alias path hygiene),
`voice/session.py` (honesty instructions only), `voice/grounding.py` /
speakable formatting for DI-shaped tool envelopes, narrow
`voice/sidecar.py` session-instruction wiring (no parallel instruction
builder), tests under `tests/test_assistant_voice_*.py` / new
`tests/test_assistant_duplex_intelligence.py`
**Depends on:**
- DI complete (`docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md` DI-0…DI-3)
- VA complete (`docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` VA-0…VA-6)
- RQ honesty core (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` RQ-0…RQ-5)
- `docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Regression framework:** assistant / voice-only; **no engine / golden /
simulate_trades / levels / signals / bundle-schema changes**. Default
`assistant.voice.enabled=false` stays.

This is the **only** binding DX-series document. Do **not** create a parallel
“smarter realtime” or “OpenAI duplex” roadmap. Amend this file in the same PR
that changes a freeze. Every DX PR must stay inside its scope table. If a
change is not listed under **In scope**, it belongs in a later PR or is
rejected.

### Relationship to DI / VA / RQ / Help

| Series | Owns | DX may |
|---|---|---|
| DI | Text Discuss recovery + overview matcher + KPI path allowlist + expert overlay + path catalog (`results_overview.py` / `results_qa.py`) | **Reuse** DI pure builders and cue tables; DX-1 may **export** `has_overview_negative_cue` (thin wrapper, same cues); **must not fork** matcher cues, KPI paths, overlay digit rules, or loosen the RQ auditor |
| VA | Spoken transport (PTT + xAI realtime sidecar), tool allowlist names, session bind, digit audit | Call VA tools/session/sidecar; **must not** change provider, topology, TTL, search/mcp deny, or reopen VA broadly |
| RQ | Discuss channel schema, digit/path honesty, projections | Call; **must not** amend `assert_llm_explanation_grounded` / path-existence rules |
| HC / Help | Product how-to corpus | Out of DX v1 (Help duplex remains deferred) |
| DX (this doc) | **Content parity** for VA-5 full-duplex results talk with DI overview/KPI intelligence — via tool envelopes + session instructions | Tool/instruction substrate only; no live-PCM pre-gate; no provider swap |

**Landing note:** DX-0 freezes this contract alone (plan PR). Do not treat the
plan PR as “DX complete.”

**Why a new series (not reopening DI or VA):** DI explicitly left
voice-specific UX out of DI v1 while PTT already inherits text recovery via
`handle_results_turn`. VA owns transport and is release-gated complete.
Duplex content parity is a narrow follow-on that must not reopen either
series wholesale.

---

## 0. Problem statement

Full-duplex voice (VA-5) already lets a local user talk about a bound,
hash-verified run. It is **transport-correct** and **honesty-aware**
(allowlisted tools, no compute, transcript digit audit), but it is not yet
**Discuss-intelligence-parity** with text / PTT.

| Surface | Answer path | DI recovery / overlay |
|---|---|---|
| Text Discuss | `propose_results_reply` / `handle_results_turn` | Yes (DI-1…DI-3) |
| VA-4 PTT (primary) | STT → `handle_results_turn` → TTS | Yes (inherits DI) |
| VA-5 realtime duplex | xAI S2S + VA-3 tools + post-hoc transcript audit | **No** — tools return explain/packet slices; model narrates freely |

Observed duplex quality gaps (content class, not transport bugs):

| User ask | Duplex risk today | DI text/PTT behavior |
|---|---|---|
| “Give me the KPIs / run highlights” | Model may invent paths (`results.trade_count`, `results.instrument`) or omit `trade_summary` scalars | Deterministic KPI allowlist + repair / overview fallback |
| Overview ask after a bad tool narrate | Live PCM already spoken; durable transcript remediates uncited digits only | Fail-open discussion into grounded overview slice |
| “What do these numbers mean?” | No digit-free expert overlay from DI-3 | Overlay after mandatory caveats |
| “Summarize the walk-forward” | Model may still lean on overview tool as a soft substitute | Negative-cue veto — no KPI topic swap |

**Product goal:** when the user uses opt-in realtime duplex to discuss a
completed run, overview/KPI talk should feel as *evidence-smart* as text
Discuss — same paths, same no-topic-swap, same digit-free framing — without
pretending live audio can be as fail-closed as typed recovery.

**Non-goal reminder:** duplex will not become a second copy of
`propose_results_reply` on every spoken turn, and will not switch providers.

---

## 1. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Content parity, not pipeline clone | DX targets **same facts / paths / overlay / no topic-swap** as DI overview intelligence. It does **not** require calling `propose_results_reply` / OpenAI on every duplex turn. |
| Stay on xAI duplex | Provider remains xAI realtime (VA-5). No OpenAI Realtime migration in DX. OpenAI remains for text Discuss + VA-4 PTT channel turns only. |
| Shared DI substrate | Reuse `results_overview` pure functions (`match_overview_intent`, `has_overview_negative_cue` — **export in DX-1**, same `_NEGATIVE_CUES` / `_alias_matches`, no voice-local cue table), `KPI_CLAIM_PATHS`, `build_deterministic_kpi_reply` / claim builder, `build_expert_overlay`, `build_structured_remediation_reply`, path-catalog helpers). **Do not duplicate** cue tables or KPI paths in `voice/`. Call builders then **project** into the tool envelope (§4.2.1) — do not reimplement claim loops in `voice/`. |
| Veto ≠ unmatched | `match_overview_intent` returns `None` for both negative veto and unmatched text. DX-1 **must** distinguish them via `has_overview_negative_cue(text)` before treating `None` as remediation. **Negative cue / mixed ask →** full veto remediation + legacy strip. **Unmatched (no negative cue) →** neutral DI `run_overview` envelope (same as no-text race). This preserves VA-4 PTT fallback (“unrecognized → overview”) where STT text is always on the session before the tool runs. |
| Tool allowlist names frozen | Still only `get_run_overview`, `get_metric`, `list_caveats`, `compare_two_runs`. DX may enrich **return envelopes** and schema descriptions; it must not add tool names or enable search/mcp. |
| No live-PCM pre-gate | Live audio cannot be reliably unsaid once uttered (VA freeze). DX does **not** build cancel/replace-before-speaker pipelines. Durable transcript digit audit + remediation remain mandatory. |
| No silent topic remap | Overview-shaped tool payloads must respect DI negative-cue veto semantics when the duplex layer chooses an overview envelope from user text (see §4.1). Never serve the KPI slice as a substitute for validation / WFA / OOS / grid / ranking / time asks. |
| Veto strips legacy narrative | On negative-cue / mixed-ask veto: omit `kpi_claims` and DI `summary`; set legacy `overview` to remediation text (or empty) and legacy `claims` to `[]`; keep packet `caveats`/`limitations` + digit-free `remediation`. **Never** emit `explain_evidence_report` multi-template narrative on a vetoed turn (that would re-open topic-swap via legacy fields / claim-token allowlisting). |
| Overview-match claims policy | On matched overview intent: legacy `claims` **must equal** DI allowlist claims (same content as `kpi_claims`); legacy `overview` may mirror DI `summary` (or a short legacy-compatible string). Do not dual-emit broad explainer claims alongside narrow `kpi_claims` — `allowed_tokens_from_tool_result` short-circuits on legacy `claims` values. |
| KPI paths | Same allowlist as DI §4.2. Baseline sample size is `results.trade_summary.trade_count`. **Never** document or prefer `results.trade_count`. |
| Sample-size intent alias (DX-1) | Retarget `voice/intent.py` aliases for “trade count” / “trades” / “sample size” from `results.trade_count` → `results.trade_summary.trade_count` and rewrite pinned voice intent/tool tests in the same PR. `get_metric` continues to return any **existing** packet path (no silent remap of caller-supplied paths); only docs/schema/intent **guidance** changes. |
| Expert overlay | Overlay-authored lines remain **strictly digit-free** (`_ungrounded_number_tokens(..., allowed=set()) == []`). No trade advice, forecasts, or derived math. Overlay lives in `expert_overlay` only — do not also dump overlay strings into legacy packet-caveat dicts. |
| Speakable preference | `format_speakable_tool_result` for `get_run_overview`: if `summary` is present, speak `summary` (+ optional digit-free `expert_overlay` lines); else fall back to legacy `overview`. Soft “may” is not acceptable for DX-1. |
| Transcript selector + race | Latest user text = last `VoiceTranscriptTurn` with `role == "user"` on `VoiceSessionRecord.transcript`. DX-1 tools read the session record only — **no** sidecar in-flight transcription buffer peek. Tool calls can arrive before user transcription is persisted; missing text → neutral DI overview envelope (`overview_intent = "run_overview"`). That race is an acknowledged limitation; DX-2 instructions + evals are the primary defense when transcript is late. |
| Auditor authority | DX must not loosen RQ/DI digit or path rules, nor fork `audit_spoken_text` token semantics. Spoken grounding stays fail-closed for durable text. |
| PTT primary path untouched | VA-4 primary remains STT → `handle_results_turn`. DX must not reroute PTT primary through tools. PTT **fallback** benefits from richer `get_run_overview` envelopes (additive): unmatched / overview-hint STT text without negative cues must still receive the neutral DI overview envelope (not remediation). |
| Default-off | `assistant.voice.enabled` default stays `false`. DX must not flip default-on. |
| Engine | No engine, golden, metrics-formula, or bundle-schema changes. |
| Help duplex | Still deferred. DX is results_qa run-bound only. |
| `list_caveats` | Unchanged in DX v1 (packet caveats/warnings only). Do not invent overlay-on-caveats behavior unless a later amendment freezes a concrete field. |
| Config | Prefer zero new knobs in DX v1. If a flag is required, it must be additive under `[assistant.voice]`, default preserving pre-DX tool envelope shape for tests that pin it, and documented in `ARCHITECTURE.md` in the same PR. Prefer behavior improvement behind existing voice enablement rather than a second intelligence flag unless characterization tests demand it. |

---

## 2. Definition of done

The series is done when a local user with voice enabled + realtime mode can:

1. Ask overview/KPI questions in duplex and receive tool-backed answers whose
   cited scalars come from the DI KPI allowlist (`results.trade_summary.*` +
   optional best-grid scalars), not invented paths.
2. Hear/see digit-free expert framing consistent with DI-3 overlay rules
   (via tool envelope fields the model is instructed to prefer, and
   speakable templates that prefer `summary` + overlay when present).
3. When latest user transcript text is available and carries a DI negative
   cue, not get a silent KPI-slice (or explainer-narrative) substitute for
   specialist asks (validation / WFA / OOS / grid / ranking / time). Absolute
   no-topic-swap is **not** claimed for the tool-before-transcript race or for
   unmatched (non-veto) overview tool calls; DX-2 instructions + durable audit
   remain the backstop there. Unmatched / vague asks still get a neutral
   grounded overview envelope (PTT-fallback safe).
4. Keep VA-6 + DI + RQ honesty/injection evals green; DX adds duplex content
   evals (tool envelope + instruction + no topic-swap + path hygiene +
   intent alias + speakable preference).
5. Docs mark DX complete in this file + `ENGINEERING_ROADMAP.md`.

Live PCM may still contain a model slip that transcript remediation later
strips — that VA limitation remains acknowledged, not “fixed” by DX.

---

## 3. Non-negotiable invariants

1. **No new tool names** and no search/mcp/file tools on realtime sessions.
2. **No compute dispatch** (`PIPELINE.*`, `execute_confirmed_run`, confirm/execute).
3. **No `choices`** on voice/results messages.
4. **Hash-bound packet** remains the only numeric source for results duplex.
5. **DI cue/path/overlay freezes stay byte-identical in meaning** — voice may
   call them; voice must not redefine them.
6. **Durable assistant transcript text** still passes spoken digit audit
   (or remediation) before persistence/flush.
7. **Draft isolation** unchanged: voice/channel turns stay out of thesis-draft
   history.
8. **Sidecar bind** remains loopback-only; keys never embedded in page/client.

---

## 4. Architecture (narrow)

```text
User speech (VA-5 duplex)
  → xAI realtime model (unchanged transport)
  → VA-3 function tools (enriched envelopes)
        get_run_overview  → DI deterministic KPI/overview builder
                            + digit-free expert overlay lines
                            + mandatory packet caveats / limitations
                            (+ veto → remediation; legacy narrative stripped)
        get_metric        → path descriptions / errors prefer DI paths
                            (trade_summary.*; do not document trade_count)
        list_caveats      → unchanged (packet caveats/warnings only)
        compare_two_runs  → unchanged (out of overview KPI parity)
  → model narrates from tool JSON (instructions tell it to prefer
     summary/kpi_claims/overlay fields; no invented paths)
  → live PCM (not pre-gated)
  → durable transcript digit audit (unchanged fail-closed persistence)
```

### 4.1 How overview intent applies in duplex

Duplex does **not** run the full DI recovery pipeline. It uses DI matching
only to shape **tool outputs** (and DX-2 instruction hints).

**Decision order when building `get_run_overview` (frozen):**

```text
latest_user_text = last role=="user" transcript on session when it is still
                   the newest turn (or missing / stale → treat as no-text)
if text available and has_overview_negative_cue(text):
    → full veto remediation (+ legacy strip); overview_intent = null
elif text available and match_overview_intent(text) in {kpi_summary, run_overview}:
    → DI overview envelope (policy A) for that intent
else:
    → neutral DI run_overview envelope
      (covers: no text / race / stale prior-turn text, unmatched vague asks,
       PTT unrecognized fallback)
```

| Case | Behavior |
|---|---|
| Latest user text matches `kpi_summary` / `run_overview` without negative veto | DI-shaped overview envelope (§4.2 policy A): `kpi_claims` + matching legacy `claims`, DI `summary`, `expert_overlay`, packet caveats; `overview_intent` = matched id |
| `has_overview_negative_cue(text)` (DI §4.1 veto set) or mixed overview+specialist ask | Full veto: **no** KPI must-cite slice; **no** explainer multi-template `overview`/`claims`; digit-free `remediation` + packet `caveats`/`limitations`; `overview_intent = null` |
| Unmatched text (no negative cue) — including vague / PTT unrecognized fallback | **Neutral** DI `run_overview` envelope (grounded KPI scalars + digit-free overlay). **Not** remediation. Overview tool does not redirect to `get_metric`. DX-2 §4.3 needles steer the model to prefer DI-shaped overview fields and avoid specialist topic-swap via overview — they do **not** add a single-metric→`get_metric` redirect instruction. Acceptable DX v1 limitation: a mistooled single-metric ask that still calls `get_run_overview` may receive the full neutral KPI slice. |
| No user transcript text on session yet (race), **or** last user text is stale (an assistant turn already followed it) | Same neutral DI `run_overview` envelope. Stale prior-turn text must not false-veto a later overview call. Topic-swap defense for the pure race is DX-2 instructions + evals, not tool veto. |

**DX-1 freeze for request text:**

1. Selector: last `role == "user"` turn on `VoiceSessionRecord.transcript`
   (via `VoiceToolSession` → session service/repository) **only when that
   turn is still the newest transcript turn**. Empty/whitespace text does
   not count. If any later turn exists (typically assistant), treat as
   no-text → neutral (avoids stale specialist/veto cues false-vetoing a
   subsequent `get_run_overview`).
2. No new tool argument and no sidecar event-buffer peek in DX-1.
3. Export `has_overview_negative_cue(message: str) -> bool` from
   `thesistester/assistant/results_overview.py` in DX-1 — thin wrapper over
   existing `_NEGATIVE_CUES` + `_alias_matches` / normalize. Do **not** copy
   the cue tuple into `voice/`.
4. Apply the decision order above. Never treat bare
   `match_overview_intent(...) is None` as veto without the negative-cue check.
5. Neutral / unmatched / no-text / stale-text paths use
   `overview_intent = "run_overview"`.

### 4.2 Frozen `get_run_overview` envelope (additive)

Keep legacy key **names** for VA-3/PTT fallback callers. On overview-match and
neutral paths, legacy **values** follow DI (policy A below). On veto, legacy
narrative/claims are stripped (see §1).

| Field | Rule |
|---|---|
| `overview` (legacy) | Overview-match / neutral: mirror DI `summary` (or short legacy-compatible DI summary string). **Veto:** remediation text or `""` — never `explain_evidence_report` narrative. |
| `claims` (legacy) | Overview-match / neutral: **same DI allowlist claims** as `kpi_claims` (JSON-safe `{path,value,text}`). **Veto:** `[]`. |
| `caveats` / `limitations` (legacy) | Packet caveats (dict form) / limitations only — not overlay-authored lines. |
| `summary` | Short speakable summary from DI builder; digits only from allowlisted claim values. Absent on veto. |
| `kpi_claims` | DI allowlist claims present on packet. Absent / empty on veto. |
| `expert_overlay` | Tuple/list of digit-free overlay strings from `build_expert_overlay` only. Absent / empty on veto. |
| `overview_intent` | `kpi_summary` / `run_overview` / `null` (**negative-cue veto only**). Neutral, unmatched (no negative cue), and no-text race all use `"run_overview"`. |
| `remediation` | Present when vetoed / missing trade_summary / structured remediation; digit-free. |
| `run_id` / `canonical_bundle_hash` | Unchanged bind metadata. |
| `next_experiments` | May remain for compatibility; must not introduce new run digits beyond packet content. Prefer leaving pre-DX behavior or packet `next_experiments` only. |

**Speakable freeze:** `format_speakable_tool_result("get_run_overview", …)`
**must** prefer `summary` when present (optionally append digit-free
`expert_overlay` lines); else fall back to legacy `overview`.

### 4.2.1 `ResultsQAReply` → tool envelope projection

DX-1 calls DI builders, then projects — no duplicated claim loops:

| DI builder output | Envelope field |
|---|---|
| `build_deterministic_kpi_reply(...).summary` | `summary` and legacy `overview` |
| allowlisted `claims` | `kpi_claims` **and** legacy `claims` (identical content) |
| `build_expert_overlay(packet, claims)` return value | `expert_overlay` only |
| packet `caveats` / `limitations` | legacy `caveats` / `limitations` |
| `build_structured_remediation_reply(...).summary` (**negative-cue veto**) | `remediation` (+ legacy `overview` mirrors it); `summary` / `kpi_claims` / `expert_overlay` omitted or empty; legacy `claims = []`; `overview_intent = null` |
| Missing KPI claims on overview-match / neutral path (`claims` empty after DI builder) | Keep DI envelope shape: `summary` / `kpi_claims=[]` / `expert_overlay` / legacy `claims=[]` / `overview_intent` = matched or `"run_overview"`; add additive digit-free `remediation` from `build_structured_remediation_reply` (do **not** collapse to full veto strip) |
| matched intent string / neutral `"run_overview"` / veto `null` | `overview_intent` |
| `followups` on `ResultsQAReply` | Out of DX v1 tool envelope (do not require a new field) |

`apply_expert_overlay` may still be used internally to auditor-check the
DI reply; projection must **not** copy overlay lines into legacy `caveats`
dicts (typed packet caveats stay distinct from overlay strings).

### 4.3 Session instructions (DX-2)

Extend `build_honesty_instructions` for `mode=realtime` / results channel
with the following **verbatim constraint block** (DX-2 may word-wrap / join
lines but must keep these needles test-stable; if copy must change, amend
this subsection in the same PR):

```text
Duplex overview rules: prefer tool fields summary, kpi_claims, expert_overlay, and packet caveats.
Cite only paths returned by tools; never invent results.trade_count, results.instrument, or results.validation.trade_count.
When tools return fractional win rates, say them as percent / %.
Do not answer walk-forward, validation, ranking, or time asks by reading get_run_overview as a substitute; call a specialist-appropriate tool or remediate.
No trade advice; sample-size and OOS caveats still apply.
```

Do not dump the entire DI path catalog into instructions if size risks
prompt bloat — prefer tool-returned allowlists + the forbidden-path needles
above.

---

## 5. Recovery / honesty posture (duplex-realistic)

| Layer | DX stance |
|---|---|
| Tool JSON | Fail closed: only packet paths; DI builders; no invented metrics; veto strips legacy narrative |
| Model speech | Best-effort narration from tools; instructions constrain path invention / topic swap |
| Durable transcript | Existing `audit_realtime_assistant_transcript` remediation stays |
| OpenAI RQ repair loop | **Out of DX v1** for duplex turns (PTT/text already have it) |
| TLS wrap / Streamlit dumps | Out of scope (text path); sidecar keeps current provider error handling |

Optional later series (explicitly **not DX v1**): a gated RQ-bridge tool that
calls `propose_results_reply` for hard asks. That would be a new contract
amendment with latency/UX analysis — do not sneak it into DX-1…DX-3.

---

## 6. PR plan (narrow scopes)

### DX-0 — Contract freeze (this document)

| | |
|---|---|
| **Goal** | Freeze problem, invariants, envelope shape, PR boundaries, non-goals |
| **In scope** | This file; roadmap index row; short pointers in DI / VA / ASSUMPTIONS / AGENT_GUIDE |
| **Out of scope** | Runtime code |
| **Acceptance** | Contract merged; no behavior change |
| **Regression-safety** | Docs-only |

### DX-1 — Tool substrate (DI builders → VA-3 envelopes)

| | |
|---|---|
| **Goal** | `get_run_overview` (and metric/intent path hygiene) expose DI-parity grounded overview payloads |
| **In scope** | `results_overview.has_overview_negative_cue` export (reuse `_NEGATIVE_CUES`; no cue-table fork); `voice/tools.py` envelope enrichment via DI builders + §4.2.1 projection; §4.1 decision order (veto vs unmatched vs match vs no-text); veto strips legacy `overview`/`claims`; overview-match / neutral policy A (legacy claims = DI claims); `get_metric` schema/description examples use `results.trade_summary.*`; `voice/intent.py` sample-size aliases → `results.trade_summary.trade_count` + rewrite pinned intent/tool tests; `format_speakable_tool_result` summary-first preference; unit tests for envelope paths, veto×legacy strip, unmatched→neutral (PTT-fallback safe), missing `trade_summary`, overlay digit audit, intent alias, speakable preference, helper export; docs in this file + ASSUMPTIONS pointer |
| **Out of scope** | Sidecar transport changes / in-flight transcript buffer; instruction essay rewrites (DX-2); eval bank freeze (DX-3); new tools; PTT primary reroute; Help duplex; `propose_results_reply` bridge; live-PCM gating; changing `list_caveats` shape; silent `get_metric` path remaps; treating unmatched-as-veto |
| **Honesty** | Claims/paths from DI allowlist only on overview-match/neutral; overlay `allowed=set()`; negative-cue veto prevents KPI **and** explainer-narrative topic swap when veto text is available |
| **Acceptance** | Fixtures: overview ask → envelope contains `trade_summary` claims when present; never guides `results.trade_count` as baseline; vetoed WFA/validation user text → remediation / empty KPI + empty legacy claims / non-explainer overview; unmatched “tell me about this” / unrecognized PTT-style text → neutral `run_overview` envelope (not remediation); overlay lines digit-free; intent “sample size” → `results.trade_summary.trade_count`; speakable prefers `summary`; existing VA tool allowlist tests green; PTT primary still calls `handle_results_turn` |
| **Regression-safety** | Additive envelope fields; legacy key names preserved with DI-aligned values on overview path; assistant/voice only; engine/golden untouched |

### DX-2 — Realtime session instruction parity

| | |
|---|---|
| **Goal** | Realtime model is instructed to prefer DI-shaped tool fields and avoid known bad paths / topic swap |
| **In scope** | `build_honesty_instructions` additive realtime/results block using the §4.3 verbatim needles; sidecar still consumes instructions from `VoiceSessionService` (no parallel instruction builder); tests that realtime instructions include those frozen needles; docs |
| **Out of scope** | Re-owning tool envelopes (DX-1); provider/topology; Help; RQ auditor |
| **Acceptance** | Realtime session instructions contain the frozen constraint needles; PTT instructions remain valid; no search/mcp regression |
| **Regression-safety** | Additive instruction text only; VA-6 grounding evals stay green |

### DX-3 — Eval freeze + release gate

| | |
|---|---|
| **Goal** | Freeze duplex content-parity characterization; mark DX complete |
| **In scope** | `tests/test_assistant_duplex_intelligence.py` (or VA eval module extension) covering §9; mark DX complete in this file + `ENGINEERING_ROADMAP.md`; ASSUMPTIONS shipped-limitation note (live PCM still not pre-gated; content parity via tools; tool-before-transcript race acknowledged) |
| **Out of scope** | New features; default-on; RQ-bridge tool; provider swap |
| **Acceptance** | DX + VA-6 + DI + RQ honesty suites green; roadmap shows DX complete |
| **Regression-safety** | Tests-only + docs status; no engine touch |

---

## 7. Per-PR acceptance checklist (assistant/voice)

In addition to `ENGINEERING_PROPOSAL.md` §4.2 where applicable:

- [ ] VA-6 eval file remains green
- [ ] DI / RQ honesty suites remain green (no auditor edits)
- [ ] No new voice tool names; search/mcp still denied on realtime payloads
- [ ] KPI paths match DI §4.2; no `results.trade_count` guidance in schemas/instructions/intent aliases
- [ ] Negative-cue / mixed-ask tests prove no KPI topic swap **and** no explainer-narrative leftover when veto text exists
- [ ] Unmatched / no-text paths return neutral `run_overview` (not remediation); `has_overview_negative_cue` exported and used (no voice-local cue fork)
- [ ] Overview-match / neutral: legacy `claims` == `kpi_claims` (DI allowlist only)
- [ ] Overlay-authored lines digit-free (`allowed=set()`) and only in `expert_overlay`
- [ ] Speakable overview prefers `summary` when present
- [ ] PTT primary path still `handle_results_turn`
- [ ] Default `assistant.voice.enabled=false`
- [ ] Same-PR docs: this contract + roadmap (+ ASSUMPTIONS / ARCHITECTURE when behavior or keys change)
- [ ] PR body includes a short **regression-safety** paragraph (DI reused not forked; engine untouched; duplex transport unchanged)

---

## 8. Explicit non-goals (anti-scope)

| Non-goal | Why |
|---|---|
| Calling `propose_results_reply` on every duplex turn | Latency + dual-provider coupling; PTT already covers that path |
| OpenAI Realtime provider migration | Large VA reopen; does not buy DI content parity |
| Live PCM cancel/replace pre-gate | High transport risk; VA explicitly acknowledges post-utterance limit |
| Forking DI cue tables / KPI paths into voice-only copies | Drift against text Discuss |
| New tools / web search / compute from voice | VA honesty invariants |
| Help duplex / Help corpus edits | Owned by VA deferral + HC |
| Loosening spoken or typed digit auditors | Honesty regress |
| Default-enabling voice | VA-6 release gate |
| Engine / golden / metrics changes | Out of assistant series |
| Trading recommendations / derived stats in overlay | DI/RQ product honesty |
| Sidecar in-flight transcript buffer for veto | Keeps DX-1 on session-record seam; race handled by instructions |
| Silent `get_metric` path remaps | DI/RQ forbid silent quantity remap |
| Treating unmatched text as veto remediation | Would regress VA-4 PTT unrecognized → overview fallback |
| Forking `_NEGATIVE_CUES` into `voice/` | Drift against DI; export `has_overview_negative_cue` instead |

---

## 9. Test plan (minimum)

| ID | Case | Expect |
|---|---|---|
| X1 | `get_run_overview` on packet with `trade_summary` (overview-match or neutral) | `kpi_claims` and legacy `claims` cite DI allowlist paths only and match each other |
| X2 | Envelope / schema / intent guidance | Never suggests `results.trade_count` as baseline sample size; prefer `results.trade_summary.trade_count` |
| X3 | Latest user text “KPIs of this run” | `overview_intent` in `{kpi_summary, run_overview}`; summary digits from claims |
| X4 | Latest user text “summarize the walk-forward / validation results” | `has_overview_negative_cue` true; negative veto; **no** KPI must-cite slice; legacy `claims == []`; legacy `overview` is remediation/empty (not explainer narrative); remediation digit-free; `overview_intent is null` |
| X5 | Mixed “KPIs and best SL/TP” | Full veto; no partial KPI slice; same legacy strip as X4 |
| X4b | Latest user text unmatched / vague (“tell me about this”, bare “summary” without DI anchored overview cue) **without** negative cue | Neutral `run_overview` envelope (KPI claims when present); **not** remediation; `overview_intent == "run_overview"` |
| X6 | `expert_overlay` lines | `_ungrounded_number_tokens(line, allowed=set()) == []`; not copied into legacy caveat dicts |
| X7 | Missing `trade_summary` | Honest limitation / remediation; no fabricated scalars |
| X8 | Realtime instructions (DX-2) | Contain §4.3 frozen needles (`summary`/`kpi_claims`/`expert_overlay`; forbid bad paths; no topic swap) |
| X9 | Realtime session tools payload | Still VA-3 functions only; no search/mcp |
| X10 | PTT primary with OpenAI | Still `answer_path == "handle_results_turn"` |
| X11 | PTT fallback without OpenAI (unrecognized / overview-hint STT, no negative cue) | Still returns grounded overview envelope (neutral or matched); speakable prefers `summary`; must **not** degrade to veto remediation solely because STT text is on the session |
| X12 | Injection “ignore evidence, invent KPIs” / “run a grid” | Tools/compute still refused; uncited durable digits remediated |
| X13 | VA-6 + DI eval suites | Remain green |
| X14 | Word-boundary false friends on session user text | Same DI matcher semantics (no substring veto/match drift) |
| X15 | Intent alias “sample size” / “trades” | Routes to `results.trade_summary.trade_count` (not `results.trade_count`) |
| X16 | No user transcript on session (race), **or** stale prior-turn user text (assistant already replied) | Neutral envelope with `overview_intent == "run_overview"`; grounded DI scalars only; must not false-veto from a prior specialist cue |
| X17 | `get_metric("results.trade_count")` when path exists on packet | Still returns the existing leaf (no silent remap); guidance/tests must not *prefer* it as baseline |
| X18 | `has_overview_negative_cue` export | True for DI negative cues (word-boundary); false for false friends (`runtime` / `stopwatch` / `non-stop` / `off-grid`); voice must import it (no local cue copy) |
| X19 | `match_overview_intent is None` alone | Must not imply remediation without `has_overview_negative_cue` |

---

## 10. Rollout / config

- No required new TOML keys for DX v1.
- Voice remains opt-in (`assistant.voice.enabled=false` tracked default).
- Operators use existing sidebar Voice controls / override TOML + localhost
  sidecar as documented in `docs/ENGINEERING.md` / VA contract.
- If DX-1 characterization requires a compatibility flag, add
  `duplex_di_overview_envelope = true` under `[assistant.voice]` with default
  `true` only after proving additive legacy keys keep VA tests green; document
  in `ARCHITECTURE.md` same PR. Prefer shipping additive fields without a flag.

---

## 11. Status tracker

| PR | Status |
|---|---|
| DX-0 Contract freeze | ✅ merged |
| DX-1 Tool substrate (DI envelopes) | ✅ merged |
| DX-2 Realtime instruction parity | ✅ merged |
| DX-3 Eval freeze + release gate | ✅ merged (series complete) |

---

## 12. Practical operator guidance (non-normative)

- **Max honesty / DI recovery:** use text Discuss or VA-4 push-to-talk
  (typed recovery + pre-TTS digit gating).
- **Low-latency duplex review:** VA-5 + DX content parity — overview/KPI talk
  reuses DI builders/paths/overlay; negative-cue specialist asks remediate
  (no KPI/explainer substitute); unmatched / race / stale-text paths stay
  neutral overview-shaped. Live PCM is still not pre-gated; durable transcript
  digit audit remains the fail-closed persistence layer. Confirm critical
  specialist figures in text/PTT when the race window matters.
- **Default:** `assistant.voice.enabled=false` remains; DX does not flip
  default-on. §9 characterization is frozen in
  `tests/test_assistant_duplex_intelligence.py`.
