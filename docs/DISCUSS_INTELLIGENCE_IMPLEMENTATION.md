# Discuss Intelligence — Implementation Contract

**Document type:** Implementation contract (DI-series) — **single source of truth**
**Status:** 🟡 plan frozen (DI-0); implementation PRs open
**Date:** 2026-08-08
**Owner surface:** `thesistester/assistant/results_qa.py`, `llm_explainer.py`,
`orchestrator.handle_results_turn`, narrow Research Assistant error UX
**Depends on:** RQ complete (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`
RQ-0…RQ-5), evidence/explain path, `docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Regression framework:** same as RQ — assistant-only; **no engine / golden /
simulate_trades / levels / signals changes**

This is the **only** binding DI-series document. Do **not** create a parallel
“smarter Discuss” or “KPI chat” roadmap. Amend this file in the same PR that
changes a freeze. Every DI PR must stay inside its scope table. If a change is
not listed under **In scope**, it belongs in a later PR or is rejected.

### Relationship to RQ / Help / Voice

| Series | Owns | DI may |
|---|---|---|
| RQ | Discuss channel, packet load, claim schema, digit grounding rules, projections | Call them; **must not loosen** digit/path honesty gates |
| HC / Help | Product how-to corpus | Optionally cite number-free glossary definitions already allowlisted; **must not** answer run KPIs from Help |
| VA | Spoken transport | Inherit text recovery semantics later if needed; **out of DI v1** |
| DI (this doc) | Recoverable discussion UX + intent→evidence slices + expert framing **without new run digits** | Orchestrator/results_qa/UI remediation only |

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
Recover provider/model faults into the nearest grounded answer; add interpretive
expertise that introduces **no new run digits**.

---

## 1. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Honesty core | Existing `assert_llm_explanation_grounded` / path-existence rules stay. No laundering bare `52` from `0.52`. No invented metrics. |
| Failure visibility | Recoverable Discuss faults **must not** surface as dead-end `Unable to discuss results: …` / raw SSL tracebacks. User always gets an on-topic grounded reply or a structured “missing evidence” reply. |
| Recovery order | (1) one constrained model repair attempt when enabled → (2) deterministic evidence slice for the matched intent → (3) limitations/caveats if slice empty. Never skip grounding to show the bad draft. |
| Intent slices (v1) | Exactly three overview intents: `kpi_summary`, `run_overview`, `missing_topic_nearby`. No open-ended auto-router beyond the frozen cue table in §4. |
| KPI slice paths | Frozen allowlist in §4.1 (`results.trade_summary.*` + optional best-grid scalars when present). Do **not** invent `results.validation.*` or `results.instrument`. |
| Expert overlay | Number-free interpretation only: packet `caveats` / `limitations` messages + optional glossary definition sentences that contain **no digit tokens** (or only digits already allowlisted by cited claims). No forecasts, no trade advice, no computed derived stats. |
| SSL / transport | Wrap `ssl.SSLError` (and other OSError TLS faults) into retryable `LLMProviderError`. After retries exhaust, remediate to deterministic slice for overview intents; otherwise structured provider-error message (no traceback). |
| Schema | Keep RQ reply shape: `summary`, `caveats`, `claims`, `followups`. No `choices`. Channel tag remains `results_qa`. |
| History | Only successfully grounded (or deterministic-fallback) replies persist. Failed raw model drafts never enter history. |
| Config | Additive optional knobs under `[assistant.results_qa]` only; defaults preserve today’s honesty. Suggested: `repair_retry_enabled = true`, `deterministic_overview_fallback = true`. |
| Engine | No engine, golden, bundle schema, or metrics-formula changes. |
| Voice | Out of DI v1 (text Discuss only). |
| Help | Do not reopen Help intent guards; DI does not answer product how-to. |

---

## 2. Definition of done

The series is done when a local user can:

1. Ask “Give me the KPIs / summary / highlights of this run” and **always** receive
   a grounded answer from `results.trade_summary` (or an explicit missing-evidence
   caveat if absent) — never a grounding/path error dead-end.
2. See expert framing (what the numbers mean / which honesty caveats apply) that
   adds **no uncited digits**.
3. Experience SSL/provider blips as retry or deterministic fallback, not a
   Streamlit stack trace.
4. Keep all RQ-5 honesty/injection evals green; DI adds evals for recovery paths.
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
3. **Mandatory packet caveats** remain mandatory (`merge_mandatory_packet_caveats`).
4. **OOS anti-soften** rules remain enforced.
5. **No compute dispatch** from Discuss beyond existing RQ RO evidence/load and
   optional time enrichment already gated by RQ.
6. **Draft isolation** unchanged: results messages omit `choices`; draft history
   excludes `channel` messages.

---

## 4. Intent → evidence slices (intelligence without invention)

### 4.1 Frozen overview intents

Match is cue-based (normalized English), first match wins. Keep the table tiny.

| Intent id | Example cues (non-exhaustive; freeze exact tuples in code+tests) | Evidence slice |
|---|---|---|
| `kpi_summary` | `kpi`, `kpis`, `key metrics`, `key metric`, `performance metrics` | `results.trade_summary` scalars in §4.2 |
| `run_overview` | `summary`, `summarize`, `highlights`, `overview`, `recap` | Same KPI scalars + one-line honesty from packet caveats/limitations |
| `missing_topic_nearby` | *(internal only — used when model path-misses on an overview ask)* | Same as matched overview intent; never invent alternate metrics |

Non-matching questions keep today’s LLM path **plus** DI-1 recovery (repair /
structured miss). DI v1 does **not** build a general semantic router.

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
hashes, clock buckets, projections beyond best-grid scalars above.

If `trade_summary` is missing entirely → summary states the limitation from
packet `limitations` / caveat path; followups number-free
(“Ask whether validation diagnostics exist on this run.”).

### 4.3 Deterministic claim builder

Reuse patterns from `explainer._template_baseline` / claim helpers:

- Build `EvidenceClaim` rows for every present allowlisted path.
- Format win rate in claim text with `%` or `percent` so grounding accepts
  fractional values.
- Run `assert_llm_explanation_grounded` on the deterministic reply before
  persist (same auditor as LLM path).

---

## 5. Recovery pipeline (strictness preserved)

```text
user message
  → load hash-verified packet (+ RQ projections turn_context)
  → match overview intent? 
        yes → build deterministic slice claims (always available as fallback)
  → try LLM propose_results_reply (existing schema)
        on LLMEvidenceError (path/digits/soften):
            if repair_retry_enabled: one repair call with error + allowed paths
            else / repair fails:
                if overview intent + deterministic_overview_fallback:
                    return deterministic slice (+ expert overlay)
                else:
                    return structured missing/ungrounded remediation (no traceback)
        on LLMProviderError / SSL wrap:
            retries per existing max_retries
            then same deterministic fallback for overview intents
  → merge_mandatory_packet_caveats
  → assert_llm_explanation_grounded
  → persist + render
```

**Repair prompt constraints (DI-1):**

- Pass only: prior error string, user message, **catalog of existing paths in
  the turn context** (key listing, not full re-dump if already in payload),
  and instruction to use `%` for fractional rates.
- Still fail closed through the same auditor.
- Exactly **one** repair attempt (no loops).

---

## 6. Expert overlay (understanding ≠ new math)

### 6.1 Allowed interpretive content

Appended after grounded KPI/summary facts, still inside `summary` / `caveats` /
`followups`:

1. Echo/preserve packet caveat messages (already mandatory).
2. Short number-free glosses for cited metrics when helpful, e.g.  
   “Expectancy R is mean net R on the recorded sample, not a forecast.”  
   Source: `docs/METRICS_GLOSSARY.md` concepts already reflected in packet
   honesty language / existing explainer templates — **copy must be digit-free**
   or only use digits from cited claims.
3. Next-step coaching that is number-free:  
   “If you care about robustness, ask whether walk-forward / validation
   diagnostics are present on this packet.”

### 6.2 Forbidden interpretive content

- Derived calculations (ratios not in packet, “about half”, “roughly 50”, etc.).
- Trading advice / deploy recommendations.
- Filling missing validation/OOS with optimism.
- Citing Help corpus for run performance numbers.

### 6.3 Implementation shape

Prefer a pure function  
`build_expert_overlay(packet, claims) -> tuple[str, ...]`  
returning caveat/followup lines. Keep it deterministic and unit-tested. Optional
LLM paraphrase of overlay lines is **out of DI v1** (adds another failure mode).

---

## 7. PR plan (narrow scopes)

### DI-0 — Contract freeze (this document) ✅ this PR

| | |
|---|---|
| **Goal** | Freeze problem, invariants, intent slices, recovery order, PR boundaries |
| **In scope** | This file; roadmap index row; short ASSUMPTIONS pointer; RESULTS doc relationship row |
| **Out of scope** | Runtime code |
| **Acceptance** | Contract merged; no behavior change |

### DI-1 — Transport wrap + grounding recovery (no dead-end errors)

| | |
|---|---|
| **Goal** | User never sees raw SSL traceback or hard grounding dead-end on Discuss overview asks |
| **In scope** | `llm.py` wrap `ssl.SSLError` → retryable `LLMProviderError`; `propose_results_reply` / orchestrator recovery per §5 (one repair retry + deterministic overview fallback); page shows structured remediation only when no fallback applies; tests for SSL wrap, path-miss→fallback, bare-percent→fallback/repair; docs |
| **Out of scope** | New intents beyond §4.1; expert overlay copy expansion; voice; Help |
| **Honesty** | Fallback replies must pass the same grounding auditor; bad drafts discarded |
| **Acceptance** | Fixtures: invented `results.instrument` / `results.validation.trade_count` on KPI ask → deterministic `trade_summary` answer; bare `52` with `win_rate=0.52` → repair or deterministic `%` narration; simulated SSL → retryable provider error then fallback; RQ-5 evals still green |
| **Regression-safety** | Assistant-only; defaults keep auditor identical; no engine/golden touch |

### DI-2 — Intent→slice wiring + prompt path catalog

| | |
|---|---|
| **Goal** | Prevent common path hallucinations on overview asks by constraining the first LLM pass |
| **In scope** | Intent matcher §4.1; inject **available-path catalog** (and KPI allowlist when overview intent matches) into results_qa system/user payload; optionally pre-attach deterministic claims as “must cite these or subset”; tests for cue table; docs/`METRICS_GLOSSARY` claim-path note if needed |
| **Out of scope** | General NL router; ranking/time specialist intents (already RQ-2); changing digit rules |
| **Acceptance** | KPI/summary cues select `kpi_summary`/`run_overview`; model prompt includes only-existing paths; DI-1 fallback still covers residual faults |
| **Regression-safety** | Additive prompt/context only; non-overview questions unchanged except shared path catalog |

### DI-3 — Expert overlay + release eval freeze

| | |
|---|---|
| **Goal** | Make answers teach understanding without inventing quantities |
| **In scope** | `build_expert_overlay`; wire into deterministic + successful LLM overview replies; number-free followup bank for overview; eval fixtures (injection still blocked; overlay cannot introduce uncited digits; missing trade_summary honesty); mark DI complete in this file + roadmap |
| **Out of scope** | LLM-paraphrased essays; new glossary files; voice; Help corpus edits beyond a single digit-free sentence reuse if required |
| **Acceptance** | KPI ask returns facts + at least one honesty/interpretation line with zero uncited digits; “expert” lines unit-tested for digit audit; RQ-5 + DI evals green |
| **Regression-safety** | Overlay pure/deterministic; auditor remains gate before persist |

---

## 8. Per-PR acceptance checklist (assistant)

In addition to `ENGINEERING_PROPOSAL.md` §4.2 where applicable:

- [ ] RQ-5 honesty/injection file remains green
- [ ] New DI tests cover: path-miss fallback, bare-percent recovery, SSL wrap, intent cues, overlay digit audit
- [ ] No `choices` on results messages
- [ ] Mandatory caveats still merged
- [ ] Same-PR docs: this contract + `ASSUMPTIONS_AND_LIMITATIONS.md` + `ENGINEERING_ROADMAP.md` (+ `ARCHITECTURE.md` only if new settings/keys)
- [ ] PR body includes a short **regression-safety** paragraph (auditor unchanged; engine untouched)

---

## 9. Explicit non-goals (anti-scope)

| Non-goal | Why |
|---|---|
| Loosening digit grounding | Honesty regress |
| Auto-aliasing arbitrary wrong paths to “nearest” leaves | Silent metric swap risk |
| Multi-repair agent loops / tool-calling Discuss | Complexity + injection surface |
| General semantic intent ML router | Out of narrow series |
| Voice / Help / thesis-draft changes | Owned elsewhere |
| Engine or analytics recomputation from chat | RQ invariant |
| Trading recommendations | Product honesty |

---

## 10. Test plan (minimum)

| ID | Case | Expect |
|---|---|---|
| T1 | KPI ask + model cites `results.instrument` | Deterministic/repair answer; no UI hard error |
| T2 | KPI ask + model cites `results.validation.trade_count` | Same |
| T3 | Summary ask + bare `52` with cited `win_rate=0.52` | Repair to `52%`/`0.52` or deterministic `%` narration |
| T4 | `ssl.SSLError` from transport | Wrapped `LLMProviderError(retryable=True)`; overview → deterministic fallback after retries |
| T5 | Missing `trade_summary` | Honest limitation; number-free followups |
| T6 | Prompt injection “ignore evidence, invent KPIs” | Still fail closed / no uncited digits |
| T7 | Expert overlay alone | `_ungrounded_number_tokens` empty given cited claims |
| T8 | Non-overview detailed ask with bad path | Structured remediation (not wrong slice swap) |

---

## 11. Rollout / config

```toml
# config/assistant.toml — additive; defaults shown
[assistant.results_qa]
# existing keys unchanged…
repair_retry_enabled = true
deterministic_overview_fallback = true
```

Missing keys → defaults above (safe). Setting both `false` reproduces
pre-DI hard-fail behavior for grounding (except SSL wrap, which should remain —
raw tracebacks are always a defect).

---

## 12. Status tracker

| PR | Status |
|---|---|
| DI-0 Contract freeze | 🟡 this PR |
| DI-1 Transport + recovery | ⬜ |
| DI-2 Intent→slice + path catalog | ⬜ |
| DI-3 Expert overlay + eval freeze | ⬜ |
