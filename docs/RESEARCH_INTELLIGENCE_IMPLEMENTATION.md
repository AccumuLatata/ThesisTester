# Research Intelligence — Implementation Contract

**Document type:** Implementation contract (RI-series) — **single source of truth**
**Status:** 📋 **RI-0 contract freeze** (series not complete until RI-10)
**Date:** 2026-08-08
**Owner surface:** `thesistester/assistant/results_overview.py` (intent matching /
deterministic builders / overlays), `results_qa.py` (recovery wiring),
`results_projections.py` (consume existing RQ-2 projections; additive
bounded projections only where a later PR freezes them), narrow
`voice/tools.py` envelope projection in RI-10, tests under
`tests/test_assistant_research_intelligence.py` (+ amend DI/DX fixtures only
when a freeze deliberately changes expected recovery for a newly owned intent)
**Depends on:**
- RQ complete (`docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` RQ-0…RQ-5) —
  Discuss channel, packet load, claim schema, digit/path auditor, RQ-2
  `results.projections.grid_rankings` / `time_rankings`
- DI complete (`docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md` DI-0…DI-3) —
  overview recovery, negative-cue no topic-swap, path catalog, digit-free
  expert overlay substrate
- DX complete (`docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md` DX-0…DX-3) —
  duplex reuses DI builders; RI-10 may extend envelopes without forking DX
- `docs/ENGINEERING_PROPOSAL.md` §4 / §4.1 / §4.2
**Regression framework:** assistant-only (voice envelope only in RI-10);
**no engine / golden / simulate_trades / levels / signals / bundle-schema /
metrics-formula changes**. RQ auditor (`assert_llm_explanation_grounded` and
path-existence rules) stays **byte-identical** unless a PR amends RQ with an
explicit relationship note (default: **never**).

This is the **only** binding RI-series document. Do **not** create a parallel
“smarter Discuss”, “agent understands results”, or “loosen grounding for UX”
roadmap. Amend this file in the same PR that changes a freeze. Every RI PR
must stay inside its scope table. If a change is not listed under **In scope**,
it belongs in a later PR or is rejected.

### Why a new series (continuation, not reopen)

DI solved **fail-open overview discussion** while keeping **fail-closed
numbers**. Specialist asks (best SL/TP, time, WFA/validation, single metrics,
Tier-2 batteries) intentionally stayed on LLM + repair → structured
remediation. That residual is **quality**, not a bug: DI refused silent KPI
topic-swap.

RI continues DI: add **fail-open specialist intent→evidence slices** with the
**same honesty bar**. Do not reopen DI/DX/RQ wholesale. Do not replace
strictness with a chatty model.

### Relationship to RQ / DI / DX / Help / Voice

| Series | Owns | RI may |
|---|---|---|
| RQ | Channel, packet, projections, digit/path auditor | **Call / consume**; must not loosen `assert_llm_explanation_grounded` or invent packet fields |
| DI | Overview intents `kpi_summary` / `run_overview`, overview recovery order, overview negative-cue veto, path catalog, digit-free overlay substrate | **Extend** matcher into a unified Discuss intent router (§4); keep DI overview behavior for pure overview asks; amend DI characterization tests only when a specialist intent now owns a former “veto→remediation” case |
| DX | Duplex overview envelopes | RI-1…RI-9 text-first; **RI-10** projects new specialist builders into duplex tools without forking cue/path tables |
| HC / Help | Product how-to | Must not answer run performance from Help; RI does not reopen Help |
| VA | Spoken transport | Out of RI except RI-10 envelope parity; voice default stays off |
| RI (this doc) | Specialist (+ single-metric + meaning + mixed-ask) fail-open slices on Discuss | Intent→allowlisted claims→deterministic builders→same auditor→digit-free meaning overlays |

**Landing note:** RI-0 freezes this contract alone (plan PR). Do not treat the
plan PR as “RI complete.”

---

## 0. Problem statement

Discuss is honesty-correct for overview KPIs and conversation-hostile for the
questions researchers actually ask about a completed run.

| User ask | Today (post DI/DX) | Class |
|---|---|---|
| “Give me the KPIs” / “summarize this run” | Fail-open deterministic KPI slice | Covered (DI) |
| “What is the best SL and TP pair?” | LLM must cite projections; uncited digits → remediation | Gap (evidence often present) |
| “Best entry time / hour bucket?” | Same fragile path | Gap |
| “Walk-forward / OOS / validation?” | Overview veto → LLM/remediation | Gap |
| “What is the win rate?” | No single-metric slice | Gap |
| “KPIs and best SL/TP” | Full veto → remediation | Gap (composition) |
| “What does expectancy mean for this run?” | Thin digit-free overlay only on overview | Gap (meaning) |

**Product goal:** an evidence-driven research AI that can chat about **all
material run results and their meaning**, without becoming a chatty bot that
invents edge.

**Non-goal:** trading advice, strategy auto-retune, engine recompute from chat,
or softening OOS / selection-bias honesty.

---

## 1. Frozen design decisions (do not re-litigate in implementation PRs)

| Freeze | Rule |
|---|---|
| Honesty core | Existing RQ auditor and path-existence rules stay. No bare-percent laundering. No invented metrics. No trade advice. No forecasts. No computed derived stats absent from the packet/projection allowlist. |
| Fail-closed numbers / fail-open discussion | Every rendered digit is auditor-grounded (LLM, repair, or deterministic builder). Fail-open means **on-topic deterministic slice or honest missing-evidence**, never an ungrounded draft. |
| Continuation | DI overview slices remain. RI adds specialist/single-metric/meaning/mixed-ask slices. Do not delete DI recovery; do not serve KPI overview for a matched specialist intent. |
| Unified intent router | One matcher (`match_discuss_intent` or equivalent) returns exactly one intent id or `None`. **Priority order frozen in §4.1.** First match wins. Word-boundary / hyphen-safe alias matching (same DI semantics) is mandatory. |
| No silent topic remap | A matched intent may only claim paths from **that** intent’s frozen allowlist (§4.2+). Never answer WFA with `trade_summary` KPIs. Never answer grid with time rankings. |
| Missing evidence | If the matched intent’s required evidence is absent → digit-free (or claim-free) **limitation reply** naming the missing battery; merge mandatory packet caveats; number-free followups. Do **not** invent SL/TP/time/OOS figures. |
| Projections authority | Grid/time rankings come from RQ-2 `results.projections.*` (and recorded `best_grid_result` where allowlisted). The model must **not** choose ranking metrics or re-rank. |
| Schema | Keep RQ reply shape: `summary`, `caveats`, `claims`, `followups`. No `choices`. Channel remains `results_qa`. |
| History | Only grounded / deterministic / structured-remediation / missing-evidence replies persist. Failed raw drafts never persist. |
| Config | Additive knobs under `[assistant.results_qa]` only. Default **`deterministic_specialist_fallback = true`**. Flags-off restores pre-RI specialist behavior (LLM + repair + §5.3 remediation) while overview DI flags remain independent. |
| Engine | No engine, golden, bundle schema, or metrics-formula changes. |
| Help / thesis draft | Out of RI. |
| Auditor ownership | RI must not fork or loosen the auditor. Auditor defects amend RQ (or RI with explicit RQ note in the same PR). |

---

## 2. Definition of done

The series is done when a local user, in Discuss results on a bound completed
run, can:

1. Ask best SL/TP / grid ranking and **always** receive a grounded answer from
   `results.projections.grid_rankings` / allowlisted `best_grid_result` leaves
   (or an explicit missing-grid limitation) — never an uncited-number dead-end
   when the projection exists.
2. Ask best entry time / session bucket and receive the same class of guarantee
   from `time_rankings` / bounded time evidence (or missing-time limitation).
3. Ask validation / WFA / OOS and receive grounded allowlisted leaves (or
   honest absence) — never IS KPIs silently substituted as OOS proof.
4. Ask a single allowlisted metric (“what is the win rate?”) and receive that
   one grounded claim (or missing-leaf limitation) without requiring a full
   overview dump.
5. Ask mixed on-topic combinations (e.g. KPIs + best SL/TP) and receive a
   **composed** grounded answer (RI-8), not a full veto dead-end.
6. See meaning overlays that explain what cited numbers mean / which honesty
   caveats apply, still **digit-free** outside cited claim values.
7. Keep RQ-5 + DI + DX honesty/characterization suites green; RI adds its own
   eval bank. Docs mark RI complete in this file + `ENGINEERING_ROADMAP.md`.

---

## 3. Non-negotiable invariants

1. **Every rendered digit** passes `assert_llm_explanation_grounded` (or is
   produced by a deterministic claim builder that cites existing paths and then
   runs the same auditor).
2. **No silent path rewrite** across quantities or namespaces
   (`results.validation.*` ≠ `results.validation_summary.*`;
   `results.trade_count` ≠ `results.trade_summary.trade_count`;
   `results.instrument` does not exist — use `assumptions.instrument`).
3. **No silent topic remap** across intents.
4. **Mandatory packet caveats** remain mandatory (`merge_mandatory_packet_caveats`).
5. **OOS anti-soften** remains enforced on LLM, repair, deterministic,
   composed, and overlay-augmented replies.
6. **No compute dispatch** from Discuss beyond existing RQ RO evidence/load and
   optional time enrichment already gated by RQ. RI-9 may add **bounded
   projections from already-loaded bundle tables** only — never silent full
   re-sim / thesis pipeline execution.
7. **Draft isolation** unchanged: results messages omit `choices`; draft history
   excludes `channel` messages.
8. **Selection-bias honesty:** grid/time “best” answers must surface
   ranking metric, selection scope / in-sample nature, and OOS status (or
   mandatory caveats that already say so). Never imply out-of-sample proof from
   in-sample rankings alone.
9. **Regression-safety:** assistant-only; DI overview happy paths stay green;
   engine/golden untouched; each PR documents a short regression-safety
   paragraph in the PR body.

---

## 4. Intent → evidence slices

### 4.1 Unified matcher (priority order)

Normalize with DI’s boundary-anchored alias matching (alnum / underscore /
hyphen edges). **Order — first match wins:**

| Priority | Intent id | Owner PR | Positive cues (freeze exact tuples in code+tests; prefer anchored forms) |
|---|---|---|---|
| 1 | `grid_ranking` | RI-1 | `best sl`, `best tp`, `best sl/tp`, `best stop`, `stop loss`, `take profit`, `sl/tp`, word-boundary `sl` / `tp` when co-present with best/pair/grid/ranking cues as frozen in tests, `grid ranking`, `grid rank`, `ranking metric` + grid context per freeze |
| 2 | `time_ranking` | RI-2 | `best time`, `best entry`, `entry time`, `time bucket`, `session segment`, `hour bucket`, word-boundary `time` / `hour` / `bucket` / `clock` with ranking/best/entry collocates per freeze |
| 3 | `validation_wfa` | RI-3 | `validation`, `wfa`, `walk-forward`, `walk forward`, `oos`, `out of sample`, `out-of-sample`, `bootstrap`, `permutation` (validation sense) |
| 4 | `robustness_tier2` | RI-5 | `monte carlo`, `monte-carlo`, `overfitting`, `sensitivity`, `noise test`, `noise summary`, `portfolio summary`, `otf validation` |
| 5 | `assumptions_costs` | RI-6 | `commission`, `slippage`, `exposure policy`, `intrabar model`, `costs`, `assumptions` (run-assumption sense; not Help how-to) |
| 6 | `single_metric` | RI-4 | Frozen metric-noun table (§4.4) with define/value collocates (`what is`, `what's`, `whats`, `show`, `give me`) — **not** bare nouns alone |
| 7 | `kpi_summary` | DI (unchanged cues) | Existing DI KPI positive cues |
| 8 | `run_overview` | DI (unchanged cues) | Existing DI run-overview positive cues |

**Multi-intent / mixed asks (until RI-8):** if two or more intents from
priorities 1–8 would match, return intent `mixed_ask` → structured remediation
asking the user to narrow (**not** KPI slice, **not** partial specialist).
RI-8 replaces `mixed_ask` remediation with composition (§4.6).

**Overview negative cues:** after RI-1+, overview matching must still refuse
specialist topics. Implement by running the unified router (specialists before
overview). Do **not** keep a divergent second cue table that can drift from
§4.1. DX `has_overview_negative_cue` may be redefined as “specialist or mixed
would match” via shared helpers (RI-10 or earlier shared export when needed) —
amend DX relationship note in the same PR; do not fork cue strings.

**Unmatched:** keep today’s LLM path + one repair + §5.3 remediation (DI).
No general semantic ML router.

**False friends:** retain DI T16 discipline (`runtime`, `stopwatch`, `non-stop`,
`off-grid`, `passkey metrics`, etc.). Each specialist PR extends false-friend
fixtures for its short tokens.

### 4.2 `grid_ranking` claim allowlist (RI-1)

Include only when path exists on the turn evidence context:

| Path | Role |
|---|---|
| `results.projections.grid_rankings.metric` | Ranking metric label/key |
| `results.projections.grid_rankings.metric_source_path` | Where metric was resolved |
| `results.projections.grid_rankings.min_trades` | Eligibility floor |
| `results.projections.grid_rankings.candidate_count` | Trial count |
| `results.projections.grid_rankings.eligible_count` | Eligible count |
| `results.projections.grid_rankings.selection_scope` | e.g. `in_sample_grid` |
| `results.projections.grid_rankings.oos_status` | OOS honesty |
| `results.projections.grid_rankings.best.stop_loss_ticks` | Best SL |
| `results.projections.grid_rankings.best.take_profit_ticks` | Best TP |
| `results.projections.grid_rankings.best.trade_count` | Trades at best cell |
| `results.projections.grid_rankings.best.metric_value` | Ranked metric value |
| `results.best_grid_result.stop_loss_ticks` | Fallback when projection best absent but recorded best exists |
| `results.best_grid_result.take_profit_ticks` | Fallback |
| `results.best_grid_result.trade_count` | Fallback |
| `assumptions.costs_exposure.commission_per_side` | Cost honesty (optional) |
| `assumptions.costs_exposure.slippage_ticks` | Cost honesty (optional) |
| `assumptions.grid.ranking_metric` | Fallback metric label when projection metric absent |

**Required for a numeric “best SL/TP” answer:** at least one SL and one TP path
from projection best or `best_grid_result`. Otherwise → missing-grid limitation.

**Explicitly out:** inventing ranks, choosing a different metric, narrating
full grid matrices, implying OOS confirmation when `oos_status` / caveats say
otherwise.

### 4.3 `time_ranking` claim allowlist (RI-2)

| Path | Role |
|---|---|
| `results.projections.time_rankings.bucket_col` | Bucket identity |
| `results.projections.time_rankings.metric` | Metric key |
| `results.projections.time_rankings.min_trades` | Floor |
| `results.projections.time_rankings.selection_scope` | In-sample time scope |
| `results.projections.time_rankings.best.bucket` | Best bucket label |
| `results.projections.time_rankings.best.trade_count` | Sample size |
| `results.projections.time_rankings.best.metric_value` | Metric |
| `results.projections.time_rankings.best.sample_warning` | Honesty when thin |

If projection absent and no usable `results.time_grouped_summary` rows →
missing-time limitation (RQ §6.3). Do not invent clocks.

### 4.4 `validation_wfa` claim allowlist (RI-3)

Freeze a **small** leaf set (extend only by amending this table):

| Path | Role |
|---|---|
| `results.walk_forward_summary.fold_count` | Folds |
| `results.walk_forward_summary.valid_fold_count` | Valid folds |
| `results.walk_forward_summary.median_test_expectancy_r` | Median OOS expectancy |
| `results.walk_forward_summary.stitched_oos_total_r` | Stitched OOS total R (if present) |
| `results.walk_forward_summary.stitched_oos_status` | Stitched status (if present) |
| `results.walk_forward_summary.status` | Summary status (if present) |
| `results.validation_summary.bootstrap.ci_lower` | Bootstrap CI (if present) |
| `results.validation_summary.bootstrap.ci_upper` | Bootstrap CI (if present) |
| `results.validation_summary.bootstrap.probability_positive` | P(mean R>0) (if present) |
| `results.validation_summary.grid_overfit.risk_level` | Grid overfit risk (if present) |

If neither WFA nor validation leaves exist → missing-validation limitation.
Never cite `results.trade_summary.*` inside this intent’s builder.

### 4.5 `single_metric` router (RI-4)

Frozen noun → path map (initial set; amend table to grow):

| Noun cues | Path |
|---|---|
| `win rate` | `results.trade_summary.win_rate` |
| `expectancy` / `expectancy_r` | `results.trade_summary.expectancy_r` |
| `profit factor` | `results.trade_summary.profit_factor` |
| `max drawdown` / `drawdown` | `results.trade_summary.max_drawdown_r` |
| `total r` | `results.trade_summary.total_r` |
| `trade count` / `number of trades` / `sample size` | `results.trade_summary.trade_count` |
| `avg r` / `average r` | `results.trade_summary.avg_r` |
| `median r` | `results.trade_summary.median_r` |
| `sharpe` | `results.trade_summary.sharpe_like_r` |
| `sortino` | `results.trade_summary.sortino_like_r` |
| `ulcer` | `results.trade_summary.ulcer_index_r` |
| `recovery factor` | `results.trade_summary.recovery_factor` |

Rules:

- Require a value collocate (`what is` / `what's` / `show` / `give me` / …)
  **or** an explicit metric question form frozen in tests.
- One noun match → one claim path. If path missing/null → missing-leaf
  limitation.
- Do **not** expand to full KPI overview unless overview cues also uniquely
  match without specialist competition (overview intents remain separate).
- Win rate narration must use `%` / percent words consistent with DI grounding.

### 4.6 `robustness_tier2` (RI-5) and `assumptions_costs` (RI-6)

**RI-5 allowlist (presence-first):** for each battery, cite only existing
`.available` / `.status` / a tiny frozen scalar set per battery
(`monte_carlo_summary`, `overfitting_summary`, `sensitivity_summary`,
`noise_summary`, `portfolio_summary`, `otf_validation_summary` /
`otf_validation.available`). Prefer “which batteries exist + status” over deep
nested dumps. Missing all → limitation.

**RI-6 allowlist:**

| Path | Role |
|---|---|
| `assumptions.costs_exposure.commission_per_side` | Commission |
| `assumptions.costs_exposure.slippage_ticks` | Slippage |
| `assumptions.costs_exposure.exposure_policy` | Exposure |
| `assumptions.costs_exposure.intrabar_model` | Intrabar |
| `assumptions.costs_exposure.stop_loss_ticks` | Configured SL (not grid best) |
| `assumptions.costs_exposure.take_profit_ticks` | Configured TP |
| `assumptions.entry_window.focus.enabled` | Focus flag (if present) |
| `assumptions.instrument` | Instrument identity |
| `assumptions.dataset.dataset_fingerprint` | Dataset identity when present |

No performance KPIs in this builder.

### 4.7 Mixed-ask composition (RI-8)

When multiple intents match:

1. Determine the set of matched intents (same cue tables).
2. Build claims per intent allowlist (deterministic).
3. Concatenate summaries in **priority order** (§4.1), separated clearly.
4. Merge caveats (mandatory packet + per-slice honesty); dedupe messages.
5. Followups number-free; prefer next unanswered specialist topic.
6. Run the auditor once on the composed reply.

Hard cap: compose at most **three** intents per turn; if more match → ask to
narrow. Never compose Help/thesis topics.

### 4.8 Deterministic builders

Prefer pure functions colocated with DI builders in `results_overview.py`
(or a thin `results_slices.py` imported by overview/qa — **one** home, no
fork):

- `build_deterministic_grid_ranking_reply(...)`
- `build_deterministic_time_ranking_reply(...)`
- `build_deterministic_validation_wfa_reply(...)`
- `build_deterministic_single_metric_reply(...)`
- `build_deterministic_robustness_reply(...)`
- `build_deterministic_assumptions_reply(...)`
- `compose_deterministic_replies(...)` (RI-8)

Each builder:

1. Emits `EvidenceClaim` rows only for existing allowlisted paths.
2. Writes a short summary that only narrates cited values.
3. Merges mandatory caveats; appends digit-free meaning lines when RI-7 wired.
4. Passes `assert_llm_explanation_grounded` before return.

### 4.9 Recovery order (extends DI §5)

For a Discuss turn:

1. `intent = match_discuss_intent(user_message)`
2. LLM draft (optional) with path catalog; if intent known, include that
   intent’s allowlist as preferred/must-cite subset (DI-2 pattern).
3. Auditor → on success, persist (attach RI-7 overlay when enabled).
4. On grounding/provider fault:
   1. One repair if enabled and fault class allows (DI rules).
   2. If `deterministic_specialist_fallback` and intent is a specialist /
      single-metric / composed intent → deterministic builder / composer.
   3. If overview intent → existing DI deterministic overview fallback.
   4. Else §5.3 structured remediation.
5. Missing required evidence for a matched specialist intent short-circuits to
   the limitation builder **without** requiring an LLM failure first
   (recommended) or equivalently after empty-slice detection — freeze one
   behavior in RI-1 tests and keep it for later PRs.

---

## 5. Meaning overlay v2 (RI-7)

Extends DI-3; does not replace mandatory caveats.

| Allowed | Forbidden |
|---|---|
| Digit-free glossary sentences for **cited** metric nouns | Any digit token in overlay-authored lines (`allowed=set()`) |
| Packet caveat/limitation restatements already digit-audited | Derived ratios / “about half” / forecasts |
| Selection-bias / in-sample / missing-OOS coaching tied to cited `oos_status` or caveat codes | Trade advice / “deploy this” |
| Sample-size caution when cited `trade_count` exists (speak qualitatively: “sample size is cited in claims”) without re-printing digits in overlay | Contradicting `missing_oos` / `failed_oos` |

Wire order unchanged: claims/summary → mandatory caveats → overlay → auditor.

Optional LLM paraphrase of overlay remains **out of RI**.

---

## 6. Deep trade projections (RI-9) — bounded only

**In series but last-wave analytics:** additive ephemeral projections under
`results.projections.*` built from already-available bundle tables / trade
summaries — never full trade parquet to the model.

Initial freeze (amend to expand):

| Projection | Purpose | Caps |
|---|---|---|
| `results.projections.exit_reason_counts` | Exit-reason histogram | Top N reasons (N≤12) + other |
| `results.projections.extreme_trades` | Worst/best R trades summary | N≤5 each; only R + exit_reason + timestamps if already present |
| `results.projections.streak_summary` | Max consecutive wins/losses if not already in trade_summary | Scalars only |

Intent cues + allowlists land in the same RI-9 PR. If tables absent →
limitation. No engine re-sim.

---

## 7. PR plan (narrow scopes)

### RI-0 — Contract freeze (this document)

| | |
|---|---|
| **Goal** | Freeze problem, invariants, intent priority, allowlists, PR boundaries, anti-scope |
| **In scope** | This file; `ENGINEERING_ROADMAP.md` index row; relationship pointers in `RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`, `DISCUSS_INTELLIGENCE_IMPLEMENTATION.md`, `ASSUMPTIONS_AND_LIMITATIONS.md`, `AGENT_GUIDE.md` |
| **Out of scope** | Runtime code |
| **Acceptance** | Contract merged; no behavior change |
| **Regression-safety** | Docs-only |

### RI-1 — Grid / best SL–TP fail-open slice

| | |
|---|---|
| **Goal** | “Best SL/TP” always grounded when projection/recorded best exists |
| **In scope** | Unified matcher skeleton with priorities 1 + 7–8 (grid + existing overview); `build_deterministic_grid_ranking_reply`; wire recovery §4.9 for `grid_ranking`; path-catalog preferred paths for grid; settings `deterministic_specialist_fallback`; tests; docs; amend DI T10 characterization for **grid** asks from “remediation” to “deterministic grid slice / missing-grid limitation” |
| **Out of scope** | Time/WFA/single-metric builders; mixed composition; duplex; auditor changes; engine |
| **Honesty** | Must cite metric + selection_scope/oos_status (or mandatory caveats); no metric shopping |
| **Acceptance** | Fixture with `grid_rankings.best` + model uncited digits → deterministic SL/TP answer; missing grid → limitation; “summarize this run” still DI overview; “KPIs and best SL/TP” still mixed remediation until RI-8; RQ-5 + DI overview tests green |
| **Regression-safety** | Assistant-only; overview path unchanged; flags-off restores pre-RI grid fragility |

### RI-2 — Time / session ranking slice

| | |
|---|---|
| **Goal** | Fail-open best entry time / bucket answers |
| **In scope** | `time_ranking` cues + builder §4.3; recovery wiring; tests/false friends; docs |
| **Out of scope** | New TIME.analyze behavior beyond existing RQ gate; grid changes; duplex |
| **Acceptance** | Projection present + bad LLM draft → deterministic time best; absent → missing-time limitation; no clock invention |
| **Regression-safety** | Assistant-only; RI-1 tests stay green |

### RI-3 — Validation + WFA/OOS slice

| | |
|---|---|
| **Goal** | Fail-open validation/WFA discussion without IS KPI substitution |
| **In scope** | `validation_wfa` cues + builder §4.4; OOS anti-soften fixtures; docs |
| **Out of scope** | Tier-2 MC/overfit batteries (RI-5); changing validation engine outputs |
| **Acceptance** | WFA ask + bad path → walk_forward leaves; validation ask → validation leaves; missing both → limitation; never answers with `trade_summary` expectancy as OOS proof |
| **Regression-safety** | Assistant-only; DI “no KPI topic swap” remains true (specialist slice ≠ KPI slice) |

### RI-4 — Single-metric router

| | |
|---|---|
| **Goal** | Fail-open one-leaf metric answers |
| **In scope** | `single_metric` cue/collocate table §4.5; one-claim builder; win-rate `%` narration; tests for each noun; docs / `METRICS_GLOSSARY` path note if needed |
| **Out of scope** | Expanding beyond §4.5 without amending this contract; overview rewrite |
| **Acceptance** | “What is the win rate?” → single grounded claim; unknown metric noun → unmatched (LLM/remediation), not wrong leaf; overview asks unchanged |
| **Regression-safety** | Assistant-only; no silent remap of wrong paths |

### RI-5 — Tier-2 robustness slices

| | |
|---|---|
| **Goal** | Presence/status-grounded answers for MC / overfit / sensitivity / noise / portfolio / OTF |
| **In scope** | `robustness_tier2` cues + presence-first builder §4.6; tests; docs |
| **Out of scope** | Deep nested battery dumps; new robustness algorithms |
| **Acceptance** | Ask Monte Carlo when summary present → grounded status/scalars; all absent → limitation |
| **Regression-safety** | Assistant-only |

### RI-6 — Assumptions & costs slice

| | |
|---|---|
| **Goal** | Grounded costs/exposure/intrabar/focus/instrument framing |
| **In scope** | `assumptions_costs` cues + builder §4.6; tests; docs |
| **Out of scope** | Help how-to; performance KPIs |
| **Acceptance** | “What costs were assumed?” → allowlisted assumption claims; no expectancy narration |
| **Regression-safety** | Assistant-only |

### RI-7 — Grounded meaning overlay v2

| | |
|---|---|
| **Goal** | Improve understanding without new digits |
| **In scope** | Extend `build_expert_overlay` (or `build_meaning_overlay`) for specialist + single-metric + overview replies; glossary/caveat templates; `allowed=set()` tests; docs |
| **Out of scope** | LLM-paraphrased essays; new glossary files beyond reusing allowlisted sentences; trade advice |
| **Acceptance** | Grid/KPI/single-metric replies include ≥1 digit-free meaning/honesty line; overlay audit green; OOS anti-soften retained |
| **Regression-safety** | Overlay pure/deterministic; auditor remains gate |

### RI-8 — Mixed-ask composition

| | |
|---|---|
| **Goal** | “KPIs and best SL/TP” becomes a composed grounded answer |
| **In scope** | `mixed_ask` → `compose_deterministic_replies` §4.7; 3-intent cap; tests amending DI T15 / DX X5 expectations for composition; docs / USER_GUIDE ask examples |
| **Out of scope** | Composing unmatched LLM topics; Help+Discuss merge |
| **Acceptance** | Mixed KPIs+SL/TP with evidence → composed claims from both allowlists; >3 intents → narrow-ask remediation; auditor passes once |
| **Regression-safety** | No topic remap outside matched allowlists |

### RI-9 — Bounded deep-trade projections

| | |
|---|---|
| **Goal** | Answer a narrow class of trade-structure questions without raw frames |
| **In scope** | Ephemeral projections §6; intent cues + allowlists; missing-table limitations; tests; docs |
| **Out of scope** | Full trade parquet to LLM; exit-model engine changes; arbitrary SQL-like chat |
| **Acceptance** | Exit-reason ask with tables → capped histogram claims; without tables → limitation; no engine touch |
| **Regression-safety** | Projections ephemeral (Discuss turn only); assistant-only |

### RI-10 — Duplex parity + release eval freeze

| | |
|---|---|
| **Goal** | Specialist content parity for duplex tools + series completion gate |
| **In scope** | Project RI builders into duplex tool envelopes (shared helpers; no cue fork); optional gated RQ-bridge **only if** needed for hard asks and frozen here; `tests/test_assistant_research_intelligence.py` §10 bank; USER_GUIDE “what you can ask”; mark RI complete in this file + roadmap; ASSUMPTIONS pointer update |
| **Out of scope** | Provider swap; live-PCM pre-gate; default-on voice; Help duplex; OpenAI migration |
| **Acceptance** | Duplex specialist ask returns grounded specialist envelope or limitation (not KPI topic-swap); RI §10 + RQ-5 + DI + DX banks green; roadmap ✅ |
| **Regression-safety** | Voice default remains off; DX overview behavior preserved for pure overview asks |

---

## 8. Per-PR acceptance checklist (assistant)

In addition to `ENGINEERING_PROPOSAL.md` §4.2 where applicable:

- [ ] RQ-5 honesty/injection file remains green
- [ ] DI overview happy paths remain green (unless a listed characterization
      amendment for an intent now owned by RI)
- [ ] DX §9 bank remains green (until RI-10 deliberate amendments)
- [ ] New RI tests cover: intent cues + false friends, allowlist-only claims,
      missing-evidence limitation, no topic remap, flags-off pre-RI specialist
      fragility, OOS anti-soften, overlay digit audit when overlay touched
- [ ] No `choices` on results messages
- [ ] Mandatory caveats still merged
- [ ] Same-PR docs: this contract + touched relationship docs
  (`ASSUMPTIONS_AND_LIMITATIONS.md`, `ENGINEERING_ROADMAP.md`,
  `ARCHITECTURE.md` when settings/keys land, `USER_GUIDE.md` when ask UX lands)
- [ ] PR body includes a short **regression-safety** paragraph (auditor
      unchanged; engine untouched; which recovery UX deliberately changes)

---

## 9. Explicit non-goals (anti-scope)

| Non-goal | Why |
|---|---|
| Loosening digit grounding / forking the auditor | Honesty regress; institutional bar |
| Silent path aliasing to “nearest” leaves | Metric swap risk |
| Serving KPI overview for specialist intents | Topic remap (DI invariant) |
| Chatty unconstrained narration of uncited digits | Toy behavior |
| General semantic ML intent router | Drift + opacity |
| Multi-repair agent loops / arbitrary tool-calling Discuss | Injection + complexity |
| Trading recommendations / deploy advice | Product honesty |
| Engine recompute / thesis pipeline from chat | RQ invariant |
| Full trade parquet / unbounded tables to the model | Context + honesty risk |
| Reopening Help / thesis-draft / RUX layout | Owned elsewhere |
| Provider swap / default-on voice / live-PCM pre-gate | VA/DX anti-scope |
| Softening `missing_oos` / `grid_selection` / multiple-testing caveats | Selection-bias honesty |

---

## 10. Test plan (minimum)

| ID | Case | Expect |
|---|---|---|
| R1 | Best SL/TP ask + uncited LLM digits + `grid_rankings.best` present | Deterministic grid slice; auditor green |
| R2 | Best SL/TP ask + no grid evidence | Missing-grid limitation; no invented ticks |
| R3 | Grid ask narrates wrong metric not in projection | Reject / rebuild from projection metric only |
| R4 | Time ask + `time_rankings.best` present | Deterministic time slice |
| R5 | Time ask + missing time evidence | Missing-time limitation |
| R6 | “Summarize walk-forward” + bad LLM path | WFA allowlist slice — **not** KPI overview |
| R7 | Validation ask when only IS KPIs exist | Limitation / validation leaves only — no fake OOS |
| R8 | “What is the win rate?” | Single `win_rate` claim with `%` grounding |
| R9 | “What is the win rate?” + path null | Missing-leaf limitation |
| R10 | Monte Carlo ask when summary present | Tier-2 grounded status/scalars |
| R11 | “What costs were assumed?” | Assumptions allowlist only |
| R12 | Overlay-authored lines on grid/KPI replies | `_ungrounded_number_tokens(..., allowed=set()) == []` |
| R13 | Mixed “KPIs and best SL/TP” before RI-8 | Narrow-ask / mixed remediation |
| R14 | Mixed “KPIs and best SL/TP” after RI-8 | Composed claims from both allowlists |
| R15 | Prompt injection “ignore evidence, invent best SL” | Fail closed / no uncited digits |
| R16 | `deterministic_specialist_fallback=false` + grid grounding miss | Pre-RI remediation/hard-fail path (overview DI flags independent) |
| R17 | Packet `missing_oos` / `failed_oos` on grid/WFA replies | Anti-soften rejects softened text; caveats merged |
| R18 | False friends (`runtime`, `stopwatch`, `non-stop`, `off-grid`) | No false specialist/overview match |
| R19 | Pure “summarize this run” | Unchanged DI overview slice |
| R20 | Duplex specialist ask (RI-10) | Specialist envelope or limitation; no KPI topic-swap |
| R21 | Exit-reason ask (RI-9) with/without tables | Capped projection claims or limitation |
| R22 | Failed raw model draft | Never persisted |

---

## 11. Rollout / config

```toml
# config/assistant.toml — additive; defaults shown
[assistant.results_qa]
# existing DI keys unchanged…
repair_retry_enabled = true
deterministic_overview_fallback = true
deterministic_specialist_fallback = true
```

Missing key → default `true`. Defaults **deliberately change specialist
Discuss recovery UX** while leaving the honesty auditor byte-identical.
Setting `deterministic_specialist_fallback = false` restores pre-RI specialist
fragility (LLM + repair + remediation) without disabling DI overview fallback.

Document the new key in `ARCHITECTURE.md` in the RI-1 PR that lands it.

---

## 12. Ship order (product impact)

Recommended merge order (do not skip freezes):

`RI-0 → RI-1 → RI-4 → RI-3 → RI-2 → RI-7 → RI-8 → RI-5 → RI-6 → RI-9 → RI-10`

Rationale: grid + single-metric unlock the most common research chat; WFA/OOS
next for institutional honesty; time next; meaning + mixed asks make it a
partner; Tier-2/assumptions/deep-trade complete coverage; duplex last so text
builders are stable.

---

## 13. Status tracker

| PR | Status |
|---|---|
| RI-0 Contract freeze | 📋 this PR |
| RI-1 Grid / best SL–TP slice | ⬚ pending |
| RI-2 Time / session ranking slice | ⬚ pending |
| RI-3 Validation + WFA/OOS slice | ⬚ pending |
| RI-4 Single-metric router | ⬚ pending |
| RI-5 Tier-2 robustness slices | ⬚ pending |
| RI-6 Assumptions & costs slice | ⬚ pending |
| RI-7 Grounded meaning overlay v2 | ⬚ pending |
| RI-8 Mixed-ask composition | ⬚ pending |
| RI-9 Bounded deep-trade projections | ⬚ pending |
| RI-10 Duplex parity + eval freeze | ⬚ pending |
