# Discuss Intelligence — Implementation Contract

**Document type:** Implementation contract (DI-series) — **single source of truth**
**Status:** ✅ **DI-0…DI-3 complete** (release gate frozen)
**Date:** 2026-08-08
**Owner surface:** `thesistester/assistant/llm.py` (SSL/TLS wrap),
`results_qa.py`, `orchestrator.handle_results_turn` (recovery pipeline),
`llm_explainer.py` (shared auditor only — **no rule loosening**), narrow
Research Assistant page error UX (render structured remediation when no
fallback applies)
**Depends on:** RQ complete (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`
RQ-0…RQ-5), evidence/explain path, `docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Regression framework:** same as RQ — assistant-only; **no engine / golden /
simulate_trades / levels / signals changes**

This is the **only** binding DI-series document. Do **not** create a parallel
“smarter Discuss” or “KPI chat” roadmap. Amend this file in the same PR that
changes a freeze. Every DI PR must stay inside its scope table. If a change is
not listed under **In scope**, it belongs in a later PR or is rejected.

### Relationship to RQ / Help / Voice / Duplex

| Series | Owns | DI may |
|---|---|---|
| RQ | Discuss channel, packet load, claim schema, digit grounding rules, projections | Call them; **must not loosen** digit/path honesty gates; **must not amend** `assert_llm_explanation_grounded` / path-existence rules (any auditor change amends RQ, or DI with an explicit RQ relationship note in the same PR) |
| HC / Help | Product how-to corpus | Optionally cite number-free glossary definitions already allowlisted; **must not** answer run KPIs from Help |
| VA | Spoken transport | Text recovery in `handle_results_turn` / `propose_results_reply` flows into VA-4 PTT automatically; voice-specific UX remains **out of DI v1** |
| DX | VA-5 duplex **content** parity with DI overview/KPI intelligence (`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md`) | DI does not own duplex; DX **reuses** DI pure builders and must not fork cue/path/overlay freezes. DX-1 may add a thin exported `has_overview_negative_cue` helper in `results_overview.py` (same `_NEGATIVE_CUES`; no cue edits) so duplex can distinguish veto from unmatched |
| RI | Specialist / single-metric / meaning / mixed-ask fail-open slices (`docs/RESEARCH_INTELLIGENCE_IMPLEMENTATION.md`) | **Continuation after DI complete** — do not reopen DI wholesale. RI may extend the Discuss intent router and amend DI characterization tests only when a specialist intent now owns a former veto→remediation case (T10→RI-1 grid; T9→RI-3 WFA/validation; T15→RI-8 mixed compose). Until each builder lands, RI **keeps DI §4.1 residual negatives** so overview/`single_metric` cannot topic-swap. RI **must not** loosen the RQ auditor or serve KPI overview for specialist intents |
| DI (this doc) | Recoverable discussion UX + overview intent→evidence slices + expert framing **without new run digits** | Orchestrator / `results_qa` recovery + `llm.py` TLS wrap + narrow page remediation render only |

**Landing note:** DI-0 freezes this contract alone (plan PR). Do not treat the
plan PR as “DI complete.”

---

## 0. Problem statement

Discuss results is honesty-correct and conversation-hostile.

Observed failure modes (same channel, different turns):

| User ask | Failure | Class |
|---|---|---|
| Highlights / KPIs | `Uncited numerical claim '52'` | Model narrated bare percent points (`52` vs `0.52` / `52%`) |
| Key metrics | `claim path 'results.validation.trade_count' missing` | Invented path (`validation` ≠ `validation_summary` / `trade_summary`) |
| KPIs | `claim path 'results.instrument' missing` | Wrong namespace (`assumptions.instrument`) |
| KPIs | raw `ssl.SSLError` traceback | Transport fault not wrapped → Streamlit dump |

**Product gap:** the user wants an expert that helps *understand* the run.
Today the model is a brittle packet reader that dies on its own slips, even when
the packet clearly contains the asked topic.

**Goal of DI:** keep **fail-closed numbers**; change **fail-open discussion**.
Recover provider/model faults into the nearest **on-topic** grounded answer; add
interpretive expertise that introduces **no new run digits**. Fail-open must
not become a silent topic remap (KPI slice answering a validation / ranking /
time question).

---

## 1. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Honesty core | Existing `assert_llm_explanation_grounded` / path-existence rules stay. No laundering bare `52` from `0.52`. No invented metrics. DI does not amend the auditor. |
| Failure visibility | Recoverable Discuss faults **must not** surface as dead-end `Unable to discuss results: …` / raw SSL tracebacks. User always gets an on-topic grounded reply or a structured “missing evidence” / provider-error reply. |
| Recovery locus | Recovery lives in `propose_results_reply` / `handle_results_turn` (not page-only). Page renders structured remediation only when no fallback applies. VA-4 PTT inherits text recovery automatically. |
| Recovery order | (1) one constrained model repair attempt when enabled → (2) deterministic evidence slice for the matched **overview** intent → (3) limitations/caveats if slice empty. Never skip grounding to show the bad draft. |
| Intent slices (v1) | Exactly **two** overview intents: `kpi_summary`, `run_overview`. Path-miss / provider-exhaust on an overview ask is a recovery **reason code** (e.g. `overview_path_miss`, `overview_provider_exhausted`), not a third intent. No open-ended auto-router beyond the frozen cue table in §4. |
| Negative cues / no topic swap | Overview match is vetoed when specialist/negative cues are present (§4.1). Never serve the KPI slice as a substitute answer for validation / WFA / OOS / grid / ranking / time asks. |
| KPI slice paths | Frozen allowlist in **§4.2** (`results.trade_summary.*` + optional best-grid scalars when present). Do **not** invent `results.validation.*` or `results.instrument`. Do **not** copy voice’s incorrect `results.trade_count` path — baseline sample size is `results.trade_summary.trade_count`. |
| Single-metric recovery | Out of DI v1. Asks like “what is the win rate?” keep today’s LLM path + DI-1 repair / structured remediation; they do **not** unlock the full KPI overview slice unless an overview cue also matches without negative veto. |
| Expert overlay | **Strictly digit-free** interpretation only: packet `caveats` / `limitations` messages + optional glossary definition sentences with **no digit tokens** (`_ungrounded_number_tokens(..., allowed=set())` must be empty). Cited run digits stay in summary/claims only. No forecasts, no trade advice, no computed derived stats. |
| SSL / transport | Wrap only the TLS allowlist in §5.1 into retryable `LLMProviderError`. **No blanket `OSError` catch.** After transport retries exhaust, remediate to deterministic slice for overview intents; otherwise structured provider-error message (no traceback). |
| Schema | Keep RQ reply shape: `summary`, `caveats`, `claims`, `followups`. No `choices`. Channel tag remains `results_qa`. |
| History | Only successfully grounded (or deterministic-fallback / structured-remediation) replies persist. Failed raw model drafts never enter history. Persist remains after a successful recovered reply (user + assistant), same as today’s success path. |
| Config | Additive optional knobs under `[assistant.results_qa]` only. Defaults **`repair_retry_enabled = true`**, **`deterministic_overview_fallback = true`** — these **change Discuss recovery UX on day one** while keeping the honesty auditor identical. Flags-off restores pre-DI hard-fail for grounding (SSL/TLS wrap remains). |
| Engine | No engine, golden, bundle schema, or metrics-formula changes. |
| Voice | Voice-specific UX out of DI v1; text recovery substrate is in-scope via orchestrator. VA-5 duplex content parity is the separate DX series (`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md`), not a DI reopen. |
| Help | Do not reopen Help intent guards; DI does not answer product how-to. |

---

## 2. Definition of done

The series is done when a local user can:

1. Ask “Give me the KPIs / key metrics / run summary / highlights of this run”
   and **always** receive a grounded answer from `results.trade_summary` (or an
   explicit missing-evidence caveat if absent) — never a grounding/path error
   dead-end. Specialist asks (WFA / validation / best SL/TP / time) must **not**
   be answered with a silent KPI-slice substitute.
2. See expert framing (what the numbers mean / which honesty caveats apply) that
   adds **no digit tokens** in overlay lines.
3. Experience SSL/provider blips as retry or deterministic fallback, not a
   Streamlit stack trace.
4. Keep all RQ-5 honesty/injection evals green; DI adds evals for recovery paths
   (including flags-off hard-fail and negative-cue no topic-swap).
5. Docs mark DI complete in this file + `ENGINEERING_ROADMAP.md`.

---

## 3. Non-negotiable invariants

1. **Every rendered digit** still passes `assert_llm_explanation_grounded`
   (or is produced by the deterministic claim builder that cites packet paths
   and then runs the same auditor).
2. **No silent path rewrite** that could map a wrong field onto a different
   quantity (e.g. never remap `results.validation.trade_count` →
   `results.trade_summary.trade_count` without an explicit intent-slice rebuild).
   Recovery rebuilds from the intent slice; it does not “fix” hallucinated paths
   onto lookalike leaves.
3. **No silent topic remap.** Overview deterministic fallback fires only when
   §4.1 overview match succeeds **and** no negative cue vetoes. Otherwise use
   structured remediation (not the KPI slice).
4. **Mandatory packet caveats** remain mandatory (`merge_mandatory_packet_caveats`).
5. **OOS anti-soften** rules remain enforced on LLM, repair, deterministic, and
   overlay-augmented replies.
6. **No compute dispatch** from Discuss beyond existing RQ RO evidence/load and
   optional time enrichment already gated by RQ.
7. **Draft isolation** unchanged: results messages omit `choices`; draft history
   excludes `channel` messages.
8. **Auditor authority.** DI must not loosen or fork digit/path grounding rules.
   Auditor defects are fixed by amending RQ (or DI with an explicit RQ note).

---

## 4. Intent → evidence slices (intelligence without invention)

### 4.1 Frozen overview intents

Match is cue-based (normalized English). **Order:** (1) negative-cue veto →
no overview intent; (2) first positive overview match wins. Keep the table tiny;
freeze exact tuples in code + tests.

**Matching semantics (DI-1 must freeze in code):** use boundary-anchored
single- and multi-word alias matching (alnum / underscore / hyphen edges) —
**not** raw substring search. Short tokens such as `sl`, `tp`, `stop`, `time`,
`grid` must not false-veto via substrings inside unrelated words
(`runtime` / `stopwatch`) or hyphen compounds (`non-stop`, `off-grid`).
Multi-word positives must not false-match (`highlights of this runtime`,
`summarize this runaway`, `passkey metrics`).

| Intent id | Positive cues (prefer anchored forms) | Evidence slice |
|---|---|---|
| `kpi_summary` | `kpi`, `kpis`, `key metrics`, `key metric`, `performance metrics`, `run kpis` | `results.trade_summary` scalars in §4.2 |
| `run_overview` | `run summary`, `run overview`, `run highlights`, `run recap`, `summarize this run`, `summarise this run`, `summary of this run`, `a summary of this run`, `highlights of this run` | Same KPI scalars + one-line honesty from packet caveats/limitations |

Bare tokens `summary` / `summarize` / `overview` / `highlights` / `recap`
**alone are not sufficient** in DI v1 (they collide with “summarize WFA”,
“overview of best SL/TP”, etc.). Prefer the anchored forms above. If a later
PR reintroduces bare tokens, it must keep the negative-cue veto and add
topic-swap tests.

**Negative cues (overview veto — non-exhaustive; freeze exact set in code+tests):**
`validation`, `wfa`, `walk-forward`, `walk forward`, `oos`, `out of sample`,
`out-of-sample`, `bootstrap`, `monte carlo`, `monte-carlo`, `grid`,
`stop`, `target`, `sl`, `tp`, `stop loss`, `take profit`, `ranking`,
`time`, `hour`, `bucket`, `clock`, `session segment`.

When vetoed or unmatched: keep today’s LLM path **plus** DI-1 recovery
(repair → structured remediation per §5.3). Do **not** serve the KPI overview
slice.

**Mixed asks (DI v1 limitation):** a message that combines an overview cue with
a negative cue (e.g. “KPIs and best SL/TP”) is **fully vetoed** — no partial
KPI slice. Repair + structured remediation only. Do not half-answer.

**Recovery reason codes** (not intents): `overview_path_miss`,
`overview_digit_miss`, `overview_provider_exhausted`, `overview_repair_failed`.
They select the already-matched overview slice; they never invent alternate
metrics.

Non-overview / single-metric questions: LLM path + one repair attempt +
structured miss (no full-KPI fallback). DI v1 does **not** build a general
semantic router or single-metric auto-slice.

### 4.2 Frozen KPI claim path allowlist

Include only when the path exists on the turn evidence context:

| Path | Role |
|---|---|
| `results.trade_summary.trade_count` | Sample size |
| `results.trade_summary.expectancy_r` | Expectancy R |
| `results.trade_summary.win_rate` | Win rate (narrate as `%` / percent words) |
| `results.trade_summary.profit_factor` | Profit factor |
| `results.trade_summary.max_drawdown_r` | Max drawdown R |
| `results.trade_summary.total_r` | Total R |
| `results.best_grid_result.stop_loss_ticks` | Optional, if present |
| `results.best_grid_result.take_profit_ticks` | Optional, if present |
| `results.best_grid_result.trade_count` | Optional, if present |

Explicitly **out of KPI slice:** `results.validation*`, `assumptions.instrument`,
`results.trade_count` (non-existent / voice bug — do not use), hashes, clock
buckets, projections beyond best-grid scalars above.

If `trade_summary` is missing entirely → summary states the limitation from
packet `limitations` / caveat path; followups number-free
(“Ask whether validation diagnostics exist on this run.”).

### 4.3 Deterministic claim builder

Reuse patterns from `explainer._template_baseline` / claim helpers:

- Build `EvidenceClaim` rows for every present allowlisted path.
- Format win rate in claim / summary text with `%` or `percent` so grounding
  accepts fractional values (bare percent points remain illegal).
- Summary digit tokens may come **only** from cited allowlisted claim values.
- Always: `merge_mandatory_packet_caveats` → `assert_llm_explanation_grounded`
  (including OOS anti-soften) before persist — same gates as the LLM path.
- Expert overlay lines (DI-3), if attached, must be strictly digit-free.

---

## 5. Recovery pipeline (strictness preserved)

```text
user message
  → load hash-verified packet (+ RQ projections turn_context)
  → negative-cue veto? → overview_intent = None
  → else match overview intent (kpi_summary / run_overview)?
        yes → build deterministic slice claims (available as fallback)
  → try LLM propose_results_reply (existing schema)
        on LLMEvidenceError (path/digits/soften):
            if repair_retry_enabled: one repair call with prior error
              (path allowlist is path_catalog only — KPI + projections +
               validation/WFA + honesty paths before fat time tables /
               provenance so the catalog cannot starve specialist cites)
            else / repair fails:
                if overview intent + deterministic_overview_fallback:
                    return deterministic slice (+ digit-free expert overlay)
                    reason_code = overview_path_miss | overview_digit_miss | …
                else:
                    return structured missing/ungrounded remediation (no traceback)
        on LLMProviderError / TLS wrap:
            retries per existing max_retries (transport)
            do **not** spend the DI repair model call on a dead transport
            then same deterministic fallback for overview intents only
  → merge_mandatory_packet_caveats
  → assert_llm_explanation_grounded
  → persist + render
```

Recovery is implemented inside `propose_results_reply` /
`handle_results_turn`. The Research Assistant page must not be the sole
recovery locus.

### 5.1 TLS / SSL wrap allowlist (DI-1)

In `llm.py` transport, map **only**:

- `ssl.SSLError`
- `ssl.CertificateError` (subclass; list explicitly for clarity)
- `urllib.error.URLError` whose `reason` is an `ssl.SSLError` /
  `ssl.CertificateError`

→ `LLMProviderError(..., retryable=True)` with the existing sanitized
provider-failure message helper (no secrets, no traceback).

**Do not** blanket-catch `OSError` / `TimeoutError` / unrelated network faults
beyond what the transport already wraps today.

### 5.2 Repair prompt constraints (DI-1 / DI-2)

- Pass only: prior error string + instruction to repair using
  ``path_catalog.existing_paths`` (and `%` for fractional rates). Do **not**
  duplicate a second path list under ``repair.existing_paths`` — the DI-2
  ``path_catalog`` on the same payload is the single allowlist source.
- Path catalog priority (DI-2): KPI leaves → projections / trade_summary /
  validation-WFA → limitations/caveats/warnings/assumptions → remaining
  ``results.*`` (shallow sample for fat ``time_grouped_summary``) → provenance.
- Still fail closed through the same auditor.
- Exactly **one** repair attempt (no loops).
- Repair is separate from transport `max_retries`.

### 5.3 Structured remediation reply shape (DI-1 freeze)

When overview fallback does **not** apply (vetoed / unmatched / flags-off after
repair miss), return a normal RQ-shaped `ResultsQAReply` (not a raw exception):

| Field | Rule |
|---|---|
| `summary` | One short digit-free sentence stating the answer could not be grounded from evidence for this ask (name the failure class in plain language: missing path, uncited number, or provider/TLS fault). |
| `claims` | Empty **or** limitation-only claims whose paths exist (e.g. a `limitations` entry) and whose text/values pass the auditor. |
| `caveats` | `merge_mandatory_packet_caveats` still applied (packet honesty digits allowed only via the existing echo/scoped-allowlist rules). |
| `followups` | Number-free only; suggest an on-topic next ask (overview vs specialist) without inventing metrics. |

Remediation replies may persist (user + assistant). Failed raw model drafts
never persist. Page copy may wrap the summary; it must not dump tracebacks.

---

## 6. Expert overlay (understanding ≠ new math)

### 6.1 Allowed interpretive content

After grounded KPI/summary facts:

1. **Mandatory packet caveats** continue via `merge_mandatory_packet_caveats`
   (existing RQ path). These lines are **not** overlay-authored; they keep
   today’s scoped digit allowlist when they echo packet caveat messages
   (e.g. a `30`-trade threshold). Do **not** run them through the overlay
   `allowed=set()` audit.
2. **Overlay-authored** glosses for cited metrics when helpful, e.g.  
   “Expectancy R is mean net R on the recorded sample, not a forecast.”  
   Source: `docs/METRICS_GLOSSARY.md` concepts already reflected in packet
   honesty language / existing explainer templates — **strictly digit-free**.
3. **Overlay-authored** next-step coaching that is digit-free:  
   “If you care about robustness, ask whether walk-forward / validation
   diagnostics are present on this packet.”  
   Suppress this coaching (and the matching followup) when the packet already
   signals `missing_oos` / `failed_oos` or a digit-free limitation that WFA/OOS
   is absent — do not contradict packet honesty or fill with optimism.
4. Empty-claims / missing `trade_summary` overlays must not say “these figures…”
   and must not near-duplicate an existing `diagnostic_only` mandatory caveat.

### 6.2 Forbidden interpretive content

- Any digit token in **overlay-authored** lines (`allowed=set()` audit).
- Derived calculations (ratios not in packet, “about half”, “roughly 50”, etc.).
- Trading advice / deploy recommendations.
- Filling missing validation/OOS with optimism.
- Contradicting packet limitations / `missing_oos` by asking whether WFA is present.
- Citing Help corpus for run performance numbers.

### 6.3 Implementation shape

Prefer a pure function  
`build_expert_overlay(packet, claims) -> tuple[str, ...]`  
returning **only overlay-authored** caveat/followup lines (not the mandatory
packet caveat merge). Keep it deterministic and unit-tested.
Unit tests must assert `_ungrounded_number_tokens(line, allowed=set()) == []`
for every overlay-authored line. Wire order: build claims/summary → merge
mandatory caveats → append overlay lines → `assert_llm_explanation_grounded`.
Optional LLM paraphrase of overlay lines is **out of DI v1**.

---

## 7. PR plan (narrow scopes)

### DI-0 — Contract freeze (this document) ✅ merged

| | |
|---|---|
| **Goal** | Freeze problem, invariants, intent slices, recovery order, PR boundaries |
| **In scope** | This file; roadmap index row; short ASSUMPTIONS pointer; RESULTS doc relationship row |
| **Out of scope** | Runtime code |
| **Acceptance** | Contract merged; no behavior change |

### DI-1 — Transport wrap + grounding recovery (incl. overview matcher)

| | |
|---|---|
| **Goal** | User never sees raw SSL traceback or hard grounding dead-end on Discuss overview asks |
| **In scope** | `llm.py` TLS allowlist wrap (§5.1); frozen cue matcher + negative-cue veto with word-boundary matching (§4.1); deterministic KPI claim builder (§4.2–4.3); recovery per §5 inside `propose_results_reply` / `handle_results_turn` (one repair retry + deterministic overview fallback + reason codes + §5.3 remediation shape); page shows structured remediation only when no fallback applies; settings knobs; tests below; docs + `ARCHITECTURE.md` for new settings keys |
| **Out of scope** | Prompt path-catalog injection (DI-2); expert overlay copy (DI-3); single-metric auto-slices; partial answers for mixed overview+specialist asks; voice-specific UX; Help; auditor rule changes |
| **Honesty** | Fallback replies must pass the same grounding auditor; bad drafts discarded; negative cues prevent KPI topic swap |
| **Acceptance** | Fixtures: invented `results.instrument` / `results.validation.trade_count` on KPI/run-summary ask → deterministic `trade_summary` answer; bare `52` with `win_rate=0.52` → repair or deterministic `%` narration; simulated `ssl.SSLError` → retryable provider error then overview fallback; “summarize the walk-forward results” + bad path → structured remediation **not** KPI slice; flags both `false` → pre-DI grounding hard-fail (SSL still wrapped); RQ-5 evals still green |
| **Regression-safety** | Assistant-only; auditor identical; defaults change recovery UX deliberately; no engine/golden touch |

### DI-2 — Prompt path catalog (first-pass constraint)

| | |
|---|---|
| **Goal** | Prevent common path hallucinations on overview asks by constraining the first LLM pass |
| **In scope** | Inject **available-path catalog** (and KPI allowlist when overview intent already matched by DI-1 matcher) into results_qa system/user payload; optionally pre-attach deterministic claims as “must cite these or subset”; tests that prompt includes only-existing paths; docs/`METRICS_GLOSSARY` claim-path note if needed |
| **Out of scope** | Re-owning / rewriting the cue matcher (DI-1); general NL router; ranking/time specialist intents (already RQ-2); changing digit rules |
| **Acceptance** | Overview asks include path catalog / allowlist in payload; non-overview questions get shared path catalog only (no KPI must-cite set); DI-1 fallback still covers residual faults |
| **Regression-safety** | Additive prompt/context only; matcher behavior frozen in DI-1 tests must stay green |

### DI-3 — Expert overlay + release eval freeze

| | |
|---|---|
| **Goal** | Make answers teach understanding without inventing quantities |
| **In scope** | `build_expert_overlay`; wire into deterministic + successful LLM overview replies; digit-free followup bank for overview; eval fixtures (injection still blocked; overlay `allowed=set()`; missing trade_summary honesty; negative-cue + flags-off characterization retained); mark DI complete in this file + roadmap |
| **Out of scope** | LLM-paraphrased essays; new glossary files; voice; Help corpus edits beyond a single digit-free sentence reuse if required |
| **Acceptance** | KPI ask returns facts + at least one honesty/interpretation line with zero digit tokens in overlay lines; RQ-5 + DI evals green |
| **Regression-safety** | Overlay pure/deterministic; auditor remains gate before persist |

---

## 8. Per-PR acceptance checklist (assistant)

In addition to `ENGINEERING_PROPOSAL.md` §4.2 where applicable:

- [ ] RQ-5 honesty/injection file remains green
- [ ] New DI tests cover: path-miss fallback, bare-percent recovery, TLS wrap allowlist, intent cues (incl. `summary of this run`) + **negative-cue veto** (word-boundary; mixed-ask full veto), flags-off hard-fail, §5.3 remediation shape, overlay digit audit (`allowed=set()` on overlay-authored lines only), OOS anti-soften on deterministic path
- [ ] No `choices` on results messages
- [ ] Mandatory caveats still merged
- [ ] Same-PR docs: this contract + `ASSUMPTIONS_AND_LIMITATIONS.md` + `ENGINEERING_ROADMAP.md` (+ `ARCHITECTURE.md` when new settings/keys land)
- [ ] PR body includes a short **regression-safety** paragraph (auditor unchanged; engine untouched; defaults change recovery UX only)

---

## 9. Explicit non-goals (anti-scope)

| Non-goal | Why |
|---|---|
| Loosening digit grounding / forking the auditor | Honesty regress; RQ owns digit/path rules |
| Auto-aliasing arbitrary wrong paths to “nearest” leaves | Silent metric swap risk |
| Serving KPI overview slice for vetoed/specialist asks | Silent topic remap |
| Single-metric auto-slice router in DI v1 | Keep series narrow; repair + structured miss suffice |
| Blanket `OSError` → provider wrap | Misclassifies non-TLS faults as retryable LLM errors |
| Multi-repair agent loops / tool-calling Discuss | Complexity + injection surface |
| General semantic intent ML router | Out of narrow series |
| Voice-specific / Help / thesis-draft product changes | Owned elsewhere (VA transport; DX for duplex content parity) |
| Engine or analytics recomputation from chat | RQ invariant |
| Trading recommendations | Product honesty |

---

## 10. Test plan (minimum)

| ID | Case | Expect |
|---|---|---|
| T1 | KPI / run-summary ask + model cites `results.instrument` | Deterministic/repair answer; no UI hard error |
| T2 | KPI / run-summary ask + model cites `results.validation.trade_count` | Same |
| T3 | “summary of this run” / “a summary of this run” + bare `52` with cited `win_rate=0.52` | Matches `run_overview`; repair to `52%`/`0.52` or deterministic `%` narration |
| T4 | `ssl.SSLError` (and `URLError(reason=SSLError)`) from transport | Wrapped `LLMProviderError(retryable=True)`; overview → deterministic fallback after retries; unrelated `OSError` not wrapped by DI TLS allowlist |
| T5 | Missing `trade_summary` | Honest limitation; number-free followups |
| T6 | Prompt injection “ignore evidence, invent KPIs” | Still fail closed / no uncited digits |
| T7 | Expert overlay-authored lines | `_ungrounded_number_tokens(line, allowed=set()) == []`; merged packet caveats with digits still allowed via echo/scoped allowlist |
| T8 | Non-overview detailed ask with bad path | §5.3 structured remediation (not KPI slice swap) |
| T9 | “Summarize the walk-forward / validation results” + bad path | Negative-cue veto → §5.3 remediation; **not** KPI `trade_summary` slice |
| T10 | “Summary of best SL/TP” / ranking ask + bad path | Same as T9 (no topic swap onto KPI slice) |
| T11 | Both recovery flags `false` + grounding miss | Pre-DI hard-fail surface (except TLS still wrapped, no traceback) |
| T12 | Deterministic fallback + packet `missing_oos` / `failed_oos` | OOS anti-soften still rejects softened text; mandatory caveats merged |
| T13 | RQ-2 best SL/TP happy path | Unchanged grounded projection / `best_grid_result` answer when model cooperates |
| T14 | Failed raw model draft | Never persisted; recovered / §5.3 reply may persist user+assistant |
| T15 | Mixed ask “KPIs and best SL/TP” + bad path | Full negative veto; §5.3 remediation; no partial KPI slice |
| T16 | Word-boundary false friends (`runtime` / `stopwatch` / `non-stop` / `off-grid`; multi-word `…runtime` / `runaway` / `passkey metrics`) | Must **not** veto or false-match overview via substring / hyphen-compound edges |
| T17 | `URLError(reason=SSLError)` message | Contains `TLS error`; §5.3 class `provider_tls` |
| T18 | Provider/TLS fault with `repair_retry_enabled=true` | Exactly one model call (no repair); overview → deterministic fallback |

---

## 11. Rollout / config

```toml
# config/assistant.toml — additive; defaults shown
[assistant.results_qa]
# existing keys unchanged…
repair_retry_enabled = true
deterministic_overview_fallback = true
```

Missing keys → defaults above. These defaults **deliberately change Discuss
recovery UX** while leaving the honesty auditor byte-identical. Setting both
`false` reproduces pre-DI hard-fail behavior for grounding (except SSL/TLS
wrap, which should remain — raw tracebacks are always a defect).

Document new keys in `ARCHITECTURE.md` in the DI-1 PR that lands them.

---

## 12. Status tracker

| PR | Status |
|---|---|
| DI-0 Contract freeze | ✅ merged |
| DI-1 Transport + recovery (+ overview matcher) | ✅ merged |
| DI-2 Prompt path catalog | ✅ merged |
| DI-3 Expert overlay + eval freeze | ✅ merged (series complete) |
