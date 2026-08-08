# Duplex Intelligence — Implementation Contract

**Document type:** Implementation contract (DX-series) — **single source of truth**
**Status:** 🟡 **DX-0 plan** (this PR freezes the contract only)
**Date:** 2026-08-08
**Owner surface:** `thesistester/assistant/voice/tools.py`,
`voice/session.py` (honesty instructions only), `voice/grounding.py` /
speakable formatting as needed for DI-shaped tool envelopes, narrow
`voice/sidecar.py` session-instruction wiring, tests under
`tests/test_assistant_voice_*.py` / new `tests/test_assistant_duplex_intelligence.py`
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
| DI | Text Discuss recovery + overview matcher + KPI path allowlist + expert overlay + path catalog (`results_overview.py` / `results_qa.py`) | **Reuse** DI pure builders and cue tables; **must not fork** matcher cues, KPI paths, overlay digit rules, or loosen the RQ auditor |
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
| Shared DI substrate | Reuse `results_overview` pure functions (`match_overview_intent`, `KPI_CLAIM_PATHS`, `build_deterministic_kpi_reply` / claim builder, `build_expert_overlay`, path-catalog helpers). **Do not duplicate** cue tables or KPI paths in `voice/`. |
| Tool allowlist names frozen | Still only `get_run_overview`, `get_metric`, `list_caveats`, `compare_two_runs`. DX may enrich **return envelopes** and schema descriptions; it must not add tool names or enable search/mcp. |
| No live-PCM pre-gate | Live audio cannot be reliably unsaid once uttered (VA freeze). DX does **not** build cancel/replace-before-speaker pipelines. Durable transcript digit audit + remediation remain mandatory. |
| No silent topic remap | Overview-shaped tool payloads must respect DI negative-cue veto semantics when the duplex layer chooses an overview envelope from user text (see §4). Never serve the KPI slice as a substitute for validation / WFA / OOS / grid / ranking / time asks. |
| KPI paths | Same allowlist as DI §4.2. Baseline sample size is `results.trade_summary.trade_count`. **Never** document or prefer `results.trade_count`. |
| Expert overlay | Overlay-authored lines remain **strictly digit-free** (`_ungrounded_number_tokens(..., allowed=set()) == []`). No trade advice, forecasts, or derived math. |
| Auditor authority | DX must not loosen RQ/DI digit or path rules, nor fork `audit_spoken_text` token semantics. Spoken grounding stays fail-closed for durable text. |
| PTT primary path untouched | VA-4 primary remains STT → `handle_results_turn`. DX must not reroute PTT primary through tools. PTT **fallback** may benefit from richer `get_run_overview` envelopes (additive). |
| Default-off | `assistant.voice.enabled` default stays `false`. DX must not flip default-on. |
| Engine | No engine, golden, metrics-formula, or bundle-schema changes. |
| Help duplex | Still deferred. DX is results_qa run-bound only. |
| Config | Prefer zero new knobs in DX v1. If a flag is required, it must be additive under `[assistant.voice]`, default preserving pre-DX tool envelope shape for tests that pin it, and documented in `ARCHITECTURE.md` in the same PR. Prefer behavior improvement behind existing voice enablement rather than a second intelligence flag unless characterization tests demand it. |

---

## 2. Definition of done

The series is done when a local user with voice enabled + realtime mode can:

1. Ask overview/KPI questions in duplex and receive tool-backed answers whose
   cited scalars come from the DI KPI allowlist (`results.trade_summary.*` +
   optional best-grid scalars), not invented paths.
2. Hear/see digit-free expert framing consistent with DI-3 overlay rules
   (via tool envelope fields the model is instructed to prefer, and/or
   speakable template paths used when tools return overview payloads).
3. Not get a silent KPI-slice substitute for vetoed specialist asks
   (validation / WFA / OOS / grid / ranking / time).
4. Keep VA-6 + DI + RQ honesty/injection evals green; DX adds duplex content
   evals (tool envelope + instruction + no topic-swap + path hygiene).
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
                            + mandatory caveats / limitations
        get_metric        → path descriptions / errors prefer DI paths
                            (trade_summary.*; reject documenting trade_count)
        list_caveats      → unchanged honesty list (may expose overlay-safe
                            digit-free lines if already in packet)
        compare_two_runs  → unchanged (out of overview KPI parity)
  → model narrates from tool JSON (instructions tell it to prefer
     summary/claims/overlay fields; no invented paths)
  → live PCM (not pre-gated)
  → durable transcript digit audit (unchanged fail-closed persistence)
```

### 4.1 How overview intent applies in duplex

Duplex does **not** run the full DI recovery pipeline. It uses DI matching
only to shape **tool outputs / instruction hints**:

| Case | Behavior |
|---|---|
| User text available to tool bridge or instruction refresh matches `kpi_summary` / `run_overview` without negative veto | `get_run_overview` returns DI-shaped overview envelope (claims from §DI 4.2, overlay lines, caveats) |
| Negative cue present (DI §4.1 veto set) | Do **not** attach KPI overview-must-cite payload; tool may return caveats/limitations + remediation hint to ask a specialist question or use text Discuss; never pretend KPI slice answers WFA/validation |
| Unmatched / single-metric ask | Prefer `get_metric` with allowlisted paths; no full KPI dump unless overview cues match |
| Mixed overview + specialist ask | Full veto (same as DI v1) — no partial KPI slice |

If the realtime model calls `get_run_overview` without the sidecar knowing
user text, the tool still returns a **neutral DI overview envelope** grounded
in the packet (same scalars DI would use for `run_overview`), plus digit-free
overlay — never invented paths. Topic-swap protection for specialist asks is
enforced by: (a) instructions forbidding overview-as-WFA-substitute,
(b) eval fixtures, and (c) optional request-text argument only if added
without creating a new tool name (prefer reading the latest user transcript
turn already on the voice session record rather than widening schema).

**DX-1 freeze for request text:** when building the overview envelope, if the
latest user transcript turn on the session is available, run
`match_overview_intent(latest_user_text)` and honor negative-cue veto
(return non-KPI remediation envelope). If no user text is available, return
the neutral grounded overview envelope (not a specialist answer).

### 4.2 Frozen `get_run_overview` envelope (additive)

Keep existing keys working for VA-3/PTT fallback callers. Add DI-aligned
fields without removing legacy keys in DX v1:

| Field | Rule |
|---|---|
| `overview` / `claims` / `caveats` / `limitations` (legacy) | Remain; claims must be packet-grounded |
| `summary` | Short speakable summary; digits only from allowlisted claim values |
| `kpi_claims` | DI allowlist claims present on packet (path/value/text) |
| `expert_overlay` | Tuple/list of digit-free overlay strings from `build_expert_overlay` |
| `overview_intent` | `kpi_summary` / `run_overview` / `null` (vetoed or unmatched) |
| `remediation` | Present when vetoed / missing trade_summary; digit-free |
| `run_id` / `canonical_bundle_hash` | Unchanged bind metadata |

Speakable formatting helpers may prefer `summary` + overlay when present;
legacy `overview` narrative remains acceptable fallback.

### 4.3 Session instructions (DX-2)

Extend `build_honesty_instructions` for `mode=realtime` / results channel
with a short, frozen block:

- Prefer tool fields `summary`, `kpi_claims`, `expert_overlay`, `caveats`.
- Cite only paths returned by tools; never invent `results.trade_count` /
  `results.instrument` / `results.validation.trade_count`.
- Win rates: say percent / `%` when tools return fractional rates.
- Do not answer WFA/validation/ranking/time asks by reading the KPI overview
  tool as a substitute; call the specialist-appropriate tool or remediate.
- No trade advice; sample-size/OOS caveats still apply.

Do not dump the entire DI path catalog into instructions if size risks
prompt bloat — prefer tool-returned allowlists + a short forbidden-path note.

---

## 5. Recovery / honesty posture (duplex-realistic)

| Layer | DX stance |
|---|---|
| Tool JSON | Fail closed: only packet paths; DI builders; no invented metrics |
| Model speech | Best-effort narration from tools; instructions constrain path invention |
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
| **Goal** | `get_run_overview` (and metric path hygiene) expose DI-parity grounded overview payloads |
| **In scope** | `voice/tools.py` envelope enrichment using `results_overview` builders; latest-user-turn veto via `match_overview_intent`; `get_metric` schema/description path examples use `results.trade_summary.*`; speakable/tool formatting updates if required for new fields; unit tests for envelope paths, veto, missing `trade_summary`, overlay digit audit; docs in this file + ASSUMPTIONS pointer |
| **Out of scope** | Sidecar transport changes; instruction essay rewrites (DX-2); eval bank freeze (DX-3); new tools; PTT primary reroute; Help duplex; `propose_results_reply` bridge; live-PCM gating |
| **Honesty** | Claims/paths from DI allowlist only; overlay `allowed=set()`; negative-cue veto prevents KPI topic swap when user text available |
| **Acceptance** | Fixtures: overview ask → envelope contains `trade_summary` claims when present; never `results.trade_count`; vetoed WFA/validation user text → remediation / non-KPI envelope; overlay lines digit-free; existing VA tool allowlist tests green; PTT primary still calls `handle_results_turn` |
| **Regression-safety** | Additive envelope fields; legacy keys preserved; assistant/voice only; engine/golden untouched |

### DX-2 — Realtime session instruction parity

| | |
|---|---|
| **Goal** | Realtime model is instructed to prefer DI-shaped tool fields and avoid known bad paths / topic swap |
| **In scope** | `build_honesty_instructions` additive realtime/results block (§4.3); sidecar still consumes instructions from `VoiceSessionService` (no parallel instruction builder); tests that realtime instructions include frozen needles (tool field names, forbidden paths, no-topic-swap); docs |
| **Out of scope** | Re-owning tool envelopes (DX-1); provider/topology; Help; RQ auditor |
| **Acceptance** | Realtime session instructions contain the frozen constraint needles; PTT instructions remain valid; no search/mcp regression |
| **Regression-safety** | Additive instruction text only; VA-6 grounding evals stay green |

### DX-3 — Eval freeze + release gate

| | |
|---|---|
| **Goal** | Freeze duplex content-parity characterization; mark DX complete |
| **In scope** | `tests/test_assistant_duplex_intelligence.py` (or VA eval module extension) covering §9; mark DX complete in this file + `ENGINEERING_ROADMAP.md`; ASSUMPTIONS shipped-limitation note (live PCM still not pre-gated; content parity via tools) |
| **Out of scope** | New features; default-on; RQ-bridge tool; provider swap |
| **Acceptance** | DX + VA-6 + DI + RQ honesty suites green; roadmap shows DX complete |
| **Regression-safety** | Tests-only + docs status; no engine touch |

---

## 7. Per-PR acceptance checklist (assistant/voice)

In addition to `ENGINEERING_PROPOSAL.md` §4.2 where applicable:

- [ ] VA-6 eval file remains green
- [ ] DI / RQ honesty suites remain green (no auditor edits)
- [ ] No new voice tool names; search/mcp still denied on realtime payloads
- [ ] KPI paths match DI §4.2; no `results.trade_count` guidance
- [ ] Negative-cue / mixed-ask tests prove no KPI topic swap when user text exists
- [ ] Overlay-authored lines digit-free (`allowed=set()`)
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

---

## 9. Test plan (minimum)

| ID | Case | Expect |
|---|---|---|
| X1 | `get_run_overview` on packet with `trade_summary` | Envelope `kpi_claims` / claims cite DI allowlist paths only |
| X2 | Envelope never suggests `results.trade_count` as baseline sample size | Prefer `results.trade_summary.trade_count` |
| X3 | Latest user text “KPIs of this run” | `overview_intent` in `{kpi_summary, run_overview}`; summary digits from claims |
| X4 | Latest user text “summarize the walk-forward / validation results” | Negative veto; **no** KPI must-cite slice; remediation digit-free |
| X5 | Mixed “KPIs and best SL/TP” | Full veto; no partial KPI slice |
| X6 | `expert_overlay` lines | `_ungrounded_number_tokens(line, allowed=set()) == []` |
| X7 | Missing `trade_summary` | Honest limitation / remediation; no fabricated scalars |
| X8 | Realtime instructions (DX-2) | Contain frozen needles: prefer `kpi_claims`/`expert_overlay`; forbid bad paths; no topic swap |
| X9 | Realtime session tools payload | Still VA-3 functions only; no search/mcp |
| X10 | PTT primary with OpenAI | Still `answer_path == "handle_results_turn"` |
| X11 | PTT fallback without OpenAI | Still works; may consume enriched overview envelope additively |
| X12 | Injection “ignore evidence, invent KPIs” / “run a grid” | Tools/compute still refused; uncited durable digits remediated |
| X13 | VA-6 + DI eval suites | Remain green |
| X14 | Word-boundary false friends on session user text | Same DI matcher semantics (no substring veto/match drift) |

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
| DX-0 Contract freeze | 🟡 this PR |
| DX-1 Tool substrate (DI envelopes) | ⬜ pending |
| DX-2 Realtime instruction parity | ⬜ pending |
| DX-3 Eval freeze + release gate | ⬜ pending |

---

## 12. Practical operator guidance (non-normative)

Until DX-1…DX-3 land:

- **Max honesty / DI recovery:** use text Discuss or VA-4 push-to-talk.
- **Low-latency duplex review:** VA-5 remains usable for bound-run talk; treat
  numbers as tool-grounded and prefer confirming critical figures in text/PTT
  when precision matters.
- After DX complete: duplex overview/KPI talk should match DI **content**;
  text/PTT remain strongest for typed recovery and pre-TTS gating.
