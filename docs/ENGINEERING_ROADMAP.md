# Engineering Roadmap

This document tracks the ThesisTester engineering roadmap milestones in established
phase order. Lean docs index: [`docs/README.md`](README.md).

Assistant-related contracts:

| Surface | Canonical doc | Status |
|---|---|---|
| Results discussion + product help | `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` (RQ) | ✅ **Complete** — RQ-0…RQ-5 (Discuss + rankings + Help + classic focus + honesty/injection eval freeze) |
| Discuss intelligence (recovery + expert framing) | `docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md` (DI) | ✅ **Complete** — DI-0…DI-3 (fail-closed numbers, fail-open discussion with negative-cue no topic-swap + digit-free expert overlay; no engine/golden touch) |
| Duplex intelligence (realtime content parity) | `docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md` (DX) | ✅ **Complete** — DX-0…DX-3 (DI-shaped duplex tool envelopes + veto≠unmatched + realtime instruction needles + §9 eval freeze); voice default remains off; no provider swap / live-PCM pre-gate / engine touch |
| Research intelligence (specialist Discuss slices) | `docs/RESEARCH_INTELLIGENCE_IMPLEMENTATION.md` (RI) | ✅ **Complete** — RI-0…RI-10 (grid + time + validation/WFA + single-metric + meaning overlay + mixed-ask composition + tier-2 robustness + assumptions/costs + bounded deep-trade projections + duplex specialist envelopes); permanent residual veto ≠ unmatched for bare stop/ranking/monte; identical RQ auditor; no engine/golden touch; voice default remains off |
| Help corpus coverage (feature/how-to docs) | `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` (HC) | ✅ **Complete** — HC-0…HC-4 + HC-5/HC-6 maintenance (USER_GUIDE how-tos + Exposure / Intrabar / Exit management / Session close / Focus vs Admit depth + §7.1.4 allowlist + retrieval boosts + §5 bank freeze) |
| Voice review | `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (VA) | ✅ **Complete** — VA-0…VA-6 (contracts → session/STT/TTS → tools → PTT → realtime sidecar → evals/release gate); default `assistant.voice.enabled=false`; duplex **content** parity follow-on is DX (do not reopen VA/HC/RQ wholesale) |
| Classic ↔ Assistant bridge | `docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md` (CAI) | ✅ Implemented (CAI-0…CAI-10) |
| Thesis draft / explain loop | `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` (C2) | ✅ Implemented (through PR6) |
| AIA Research Assistant foundations | `docs/AI_RESEARCH_ASSISTANT_ROADMAP.md` (AIA) | ✅ Implemented — do not open new results/help PRs from AIA text |
| Session entry window research loop | `docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md` (SW); evidence `docs/archive/SESSION_ENTRY_WINDOW_RELEASE_EVIDENCE.md` | ✅ **Engineering-signed (SW0–SW7 + SW2b)** — Focus → Admit → Grid/WFA inherit; cutoff skip audit; C1–C9; default-off; golden-gated per `ENGINEERING_PROPOSAL.md` §4 |
| Research Study Runner | `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` (RS); operator `docs/STUDY_RUNNER.md`; Grok pack `docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md` | ✅ **RS1–RS5 MVP + RS-D7 + RS6 + RS-D2 + RS-D4 + RS-D5 + RS-D8 + RS-D9**; parked D1/D3/D6 |
| Study Builder (UX) | `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md` (SB) | ✅ **SB1–SB3 complete**. Emits canonical StudySpec YAML onto the existing Studies Preview pane; no in-process execute; no new factor axes |
| Study Ingest Alignment | `docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md` (SIA) | ✅ **SIA0–SIA3**. Studies authoring/defaults/examples only; execute stays `run_experiment`; no engine/Data edits |
| Study Viewer (Inspect UX) | `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV); operator `docs/STUDY_RUNNER.md` §SV | ✅ **SV0–SV5**. Catalog + `study list` + quality panes + overview charts + cell peek + trader briefing / per-cell SL/TP grid / NY RTH ToD. No in-process execute; no classic-session hydrate |
| Study Observatory (corpus UX) | `docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md` (SO); operator `docs/STUDY_RUNNER.md` §SO | **SO9 shipped** (fact table + CLI + page 16 + Program B lens + saved desks + studies pane + cohort labels + lens-as-filter). SO5 watch / SO6 Discuss parked. Read-only concat of existing study artifacts; no execute; no classic hydrate |
| Audit honesty remediations | `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` (AH) | **AH0–AH6.** Flatten leak fixed; Study paths pinned; OTF-matrix train prefix-sliced; leftover bundle keys managed; `sl_first` honors 3c entry activation; `BASE_COLUMNS` rejected in setup validator. No composer collapse; no golden regen except AH5 hard-stop |
| Study Admit Follow-up | `docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md` (SAF); operator `docs/STUDY_RUNNER.md` §SAF | **SAF1–SAF3 shipped** (CLI `--admit-tod auto` + `--tod-group` / `--allow-thin` + Inspect draft → Preview + catalog `parent`). SAF4 parked. Promote without flags stays RS5. No auto-run; no ToD factor axis |
| Level Catalog Contract | `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md` (LC) | **LC4 landed.** Series complete. Catalog completeness/correctness for already-emitted levels. No new price series; no `LEVEL_ENGINE_VERSION`; no golden regen |
| Developing week/month VWAP | `docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md` (WMV) | **WMV2 landed.** Series complete. Developing `wVWAP` / `mVWAP` siblings of `dVWAP`; Setup/Study tokens; Help/UI copy. Same `session_vwap_enabled` gate; `LEVEL_ENGINE_VERSION` 10; no golden regen |
| Level-as-anchor combination protocol | `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` | **Program A** (docs-only, executed desk funnel). Closed token inventory + staged `core_level` × complementary partners; L1 coin-flip-first / L2 low-N stop / Admit=`backtest.entry_window`. No new factor axes / engine / goldens |
| Level-combination research concept | `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md` · inventory `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md` · runbook `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` | **Program B** (operator packet). Wave 0 solo (AO1) + 50 × MA / rolling VWAP / pivot, split 15s (`manifest.yaml`, 23/944) vs tick-gated VA (`manifest_va.yaml`, 4/207). `dVWAP` is an optional core, not a required partner. Does not amend the Notion desk lock page |
| Directional integrity & edge attribution | `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md` (DA) | **DA6 landed** (DA0 locked, DA1–DA5 landed). Program B Run 2 packet (`fade` @ 1min, `same_bar_opposite_direction: raise`, `report.random_baseline` 50). Series code is **DA** (DI is Discuss Intelligence). Run 1 YAMLs untouched; generator defaults unchanged; no existing-golden regen |
| Trade journal (fills ↔ FCM truth) | `docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md` (TJ) | **TJ0 locked.** Quantower Trades CSV (timestamps) + AMP Daily Statement PDF (money). Qty-aware FIFO; AMP fees $1.24 RT; no engine/golden touch. Same-day AMP↔QT overlap golden still desk-blocked |
| Anchor-only (`min_valid=0`) | `docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md` (AO) | **AO1 implemented.** Opt-in `anchor_rules` with empty partners so a location can be traded alone. Default `min_valid` stays 1. Global cluster / `simulate_trades` / pipeline composition frozen. No golden regen |
| Tick VAP (prior-profile allocation) | `docs/TICK_VAP_IMPLEMENTATION_PLAN.md` (TV) | **TV1–TV4 landed.** Series complete. Data / Study Builder `tick_paths` + Help honesty. Quantower tick-last ingest for `pd*` / `pw*` / `pm*` VA only; 15s stays the bar clock; omit/fail-closed without ticks; product day bin 1; `LEVEL_ENGINE_VERSION` 11; no golden regen |
| A-period POC Quantower parity | `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md` (AP) | **AP1 implemented — evidence collection pending.** Current APOC is a 1-minute typical-price proxy. The comparison harness is isolated from production APOC. A versioned source change still requires a reproducible Quantower oracle. |
| Research Assistant page layout / prominence | `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` (RUX); evidence `docs/archive/RESEARCH_ASSISTANT_UX_REFOCUS_EVIDENCE.md` | ✅ **Complete** — RUX-0…RUX-5 ([#305](https://github.com/AccumuLatata/ThesisTester/pull/305): discuss-first modes + mode-scoped chat_input + Help re-anchor + evidence). Presentation-only: do not reopen for layout changes; amend the RUX contract instead |

Completed AIA/C2/CAI roadmaps remain the source of truth for what they shipped;
new results/help/voice work must not reopen them. All are additive to this
R-series and must preserve engine/golden-master semantics.

Session-constraint work is specified in
`docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md` (engineering sign-off in
`docs/archive/SESSION_ENTRY_WINDOW_RELEASE_EVIDENCE.md`) and must not reopen R9–R22
milestone text; SW series preserves legacy golden identity.

---

## CAI-0 — Classic/Assistant Cold-Path Baseline ✅ Implemented

Freezes the current headless cold path before shared data/levels artifacts are
introduced.

### Features

- Deterministic fixtures in `tests/fixtures/cai_baseline.py`:
  - `small` (60 bars, no rolling POC) for CI harness smoke;
  - `realistic` (780 bars / two RTH sessions, `poc_windows=["30min"]`) for
    informational timing only.
- Informational stage harness:
  `python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5`
- Baseline record and recording-policy decision in `docs/CAI_BASELINE.md`.
- Initial classic-to-thesis recording policy: **manual record-after-run**.

### Regression safety

- No production cache, UI, API default, or engine behavior change.
- Wall time is informational only and is not a CI threshold.
- Existing API/CLI/Assistant canonical-hash parity remains the correctness gate.

### Tests

- `tests/benchmarks/test_cai_cold_path.py` asserts small-fixture harness
  structure and keeps the assistant parity fixture green.

### Observed baseline implication

On the realistic fixture, `compute_levels` dominated end-to-end cold median
time (~71%). CAI-2/CAI-3 therefore target verified levels-artifact reuse first.

---

## CAI-1 — Shared Research Identity ✅ Implemented

Creates one Streamlit-free source of truth for levels normalization and
content-addressed data/levels/experiment identity before any cache lookup.

### Features

- `thesistester/research_identity.py`:
  - `normalize_levels_config(config, *, instrument)`
  - frozen `DataIdentity`, `LevelsIdentity`, `ExperimentIdentity`
  - constructors from loaded data, RunSpec, classic page state, and bundle meta
- `api.compute_levels` uses the shared normalizer.
- `run_experiment` adds additive `data_identity`, `levels_identity`,
  `experiment_identity`, and `execution_origin`.
- Optional bundle member `research_identity.json` restores `data_identity` /
  `levels_identity` when present; pre-CAI-1 bundles remain loadable without
  those fields.
- Bundle restore writes/reads `format_profile` in `dataset_meta.json` (with
  `data_identity` fallback) and clears stale `experiment_identity` /
  `execution_origin` on import.

### Regression safety

- No production cache lookup.
- `DataIdentity.dataset_id()` preserves `compute_dataset_id` semantics
  (`format_profile` is additive metadata only).
- `execution_origin` is provenance-only and does not enter the hashed identity
  bundle member.
- Engine/golden-master outputs unchanged; classic Levels UX normalizer for
  stale checks is untouched.

### Tests

- `tests/test_research_identity.py` covers normalization/hash parity, identity
  constructors, old-bundle compatibility, and origin-independent bundle hashes.

---

## CAI-2 — Durable Execution-Artifact Store ✅ Implemented

Internal content-addressed cache for canonical data and levels, separate from
user-facing dataset/levels snapshots.

### Features

- `thesistester/persistence/execution_artifacts.py`:
  - `read_verified_data_artifact` / `read_verified_levels_artifact`
  - `write_data_artifact` / `write_levels_artifact`
  - `invalidate_data_artifact` / `invalidate_levels_artifact`
- Schema-versioned root:
  `.thesistester_store/execution_artifacts/v1/{data,levels,locks}/`
- Atomic temp-dir publish with fsync + per-identity exclusive locks.
- Manifests store identity payloads, engine/artifact schema versions, and
  `created_at` / `accessed_at` for later retention (CAI-10).

### Regression safety

- No automatic consumption by `run_experiment`, pages, CLI, or Assistant.
- Verified reads return `ArtifactMiss` instead of raising on corrupt or
  incompatible artifacts.
- UX `save_levels` / `find_matching_levels` namespace and behavior unchanged.
- Data artifact keys include `format_profile`; legacy `dataset_id` unchanged.

### Tests

- `tests/test_execution_artifacts.py`: cold miss, hit, corrupt manifest,
  missing parquet, schema/engine drift, concurrent publish, path containment,
  invalidation, and UX snapshot isolation.

---

## CAI-3 — Cached Headless Pipeline Parity ✅ Implemented

Wires verified execution artifacts into the public headless API behind an
explicit cache policy without changing research semantics.

### Features

- `run_experiment(..., cache_policy=..., store_root=...)` and
  `compute_levels(..., cache_policy=..., data_identity=..., store_root=...)`.
- Default policy ``off`` preserves the legacy cold path.
- CLI and Assistant use ``read_write``.
- Source-bytes binding index enables warm CSV skip; levels artifacts skip
  recomputation on exact `LevelsIdentity` hit.
- `cache_provenance` (`bypassed|cold|data_hit|levels_hit`) on run state,
  Assistant tool results, and persisted thesis run provenance (for provenance
  cards); excluded from canonical bundle hash.

### Regression safety

- Cold vs warm equal canonical bundle hashes and frame/diagnostic values.
- Corrupt/missing artifacts, stale source bytes, and changed levels settings
  fall back to cold compute and never fail a valid run.
- Golden-master legacy pipeline unchanged (does not enable cache).
- Classic session DataFrames are never used as a cache source.

### Tests

- `tests/test_cai3_cached_pipeline.py` covers bypassed default, cold/warm
  parity, CSV-skip warm path, corrupt levels fallback, settings/source drift,
  and provenance exclusion from bundles.

---

## CAI-4 — Classic-State-to-RunSpec Export ✅ Implemented

Pure exporter from canonical classic page state to a validated public RunSpec
draft. Does not execute research or invent missing parameters.

### Features

- `thesistester/classic_export.py`:
  - `classic_state_export_gaps(...)`
  - `classic_state_to_run_spec(...)`
- Consumes `data` / provenance, `levels_settings`, `setup_config` /
  `last_signal_setup`, and backtest policy snapshots (or `backtest_config`).
- Preferred verified data artifact reference plus required path verified
  against `DataIdentity` (blank `source_path` kwargs falls through to state).
- Additive `dataset.data_artifact_key` / `dataset.data_identity` on RunSpec.

### Regression safety

- Streamlit-free; no page wiring or thesis recording yet (CAI-5/CAI-6).
- Missing/stale/mismatched state yields explicit gaps; no default injection
  (including non-integer `levels_data_fingerprint.rows` → `stale_levels`).
- Exported vs equivalent hand-authored RunSpec: equal canonical bundle hashes.

### Tests

- `tests/test_classic_export.py`.

---

## CAI-5 — Thesis Research Context Lifecycle ✅ Implemented

Additive classic-workspace thesis context so Setup Builder / Signals /
Backtest / Research Bundles can enter or leave research mode without changing
executable page settings or recording runs.

### Features

- `thesistester/classic_context.py`:
  - session helpers (`init_classic_session_state`, `link_thesis`,
    `exit_research_mode`, `sync_classic_context_for_dataset`, recording policy,
    pending navigation, flash)
  - `render_classic_thesis_chrome(...)` (lazy Streamlit import)
- Setup Builder: **Create thesis** / **Link existing thesis**
- Signals, Backtest, Research Bundles: compact breadcrumb + exit/relink
- Links sync `assistant_selected_thesis_id` via `select_thesis`

### Regression safety

- Protected classic producer keys retain value/type across link/exit/dataset
  switch.
- Dataset switch clears thesis-scoped classic keys (no cross-dataset leak).
  An unset bound (link before data) adopts the first observed `dataset_id`.
  Context clear also resets `_classic_relink_open_*` UI flags.
- Pending navigation uses allowlisted `st.switch_page` targets.
- Bundle import re-syncs classic context against the imported dataset.
- Linking never starts runs or creates specification versions.
- Recording policy default remains `manual` (CAI-0); `all_executions` behavior
  is implemented in CAI-7.

### Tests

- `tests/test_classic_context.py`.

---

## CAI-6 — Attach Completed Classic Run to Thesis ✅ Implemented

Register a completed classic research bundle as an immutable thesis run without
recomputing the experiment. Explicit **Record and discuss this run** only.

### Features

- Registry: `BUNDLE.register_external_run` (import/export, explicit confirmation).
- `AssistantTools.verify_external_research_bundle(...)`.
- `AssistantOrchestrator.register_external_bundle_run(...)` with
  `execution_origin="classic"`, CAI-4 RunSpec confirmation, audit transcript.
- Idempotent by `canonical_bundle_hash` + matching stored RunSpec (`force_new`
  opt-in); reuse skips stale/drifted matches, reports stored
  `execution_origin`, and classic recording preflights required sections,
  honors `store_root`, and deletes orphan UUID zips on failure or reuse
  (retaining cancelled-run provenance bundles).
- `thesistester/classic_record.py` + Backtest / Research Bundles UI button.
- Opens Research Assistant via classic pending navigation after success.

### Regression safety

- Hash and evidence packet match the original bundle; no
  `run_experiment_to_bundle` during registration.
- Tampered / missing / corrupt / out-of-root bundles fail closed.
- Does not bypass confirmation for future `execute_confirmed_run` recompute.
- Classic link/create path remains non-recording (`classic_context` unchanged).

### Tests

- `tests/test_classic_record.py`.

---

## CAI-7 — Research-Mode Execution Ledger ✅ Implemented

Opt-in `all_executions` recording under an active thesis so Backtest attempts
are persisted before execution and terminalized as completed, failed, or
cancelled — preventing selective preservation of only favorable outcomes.

### Features

- Classic chrome policy selectbox: `manual` (default) or `all_executions`.
- `thesistester/classic_ledger.py`: begin / complete / fail helpers over
  `ResearchRun` with `request.action="classic_execution_ledger"`.
- Backtest wraps `▶ Run backtest` when research mode + `all_executions`;
  surfaces thesis run ledger table.
- Assistant Research runs labels ledger vs manual-record vs assistant runs;
  provenance card includes origin page, config hash, recording policy.

### Regression safety

- Failed/cancelled never appear as completed or left `running`.
- Bundle-write or `complete_run` failure after simulation → `failed` with
  request retained (orphan zip removed).
- Backtest post-begin exceptions always call `fail_classic_execution_ledger`.
- Shared policy widget key synced from session (no stale per-page revert).
- `manual` policy or no thesis context: classic Backtest path unchanged.
- Ledger APIs stay out of `classic_context` (link/create non-recording).

### Tests

- `tests/test_classic_ledger.py` (incl. `complete_run` failure terminalization).
- `tests/test_classic_context.py` (policy widget key sync).

---

## CAI-8 — Bidirectional Navigation and Identity-Aware UI ✅ Implemented

Makes the classic ↔ Assistant research graph visible without duplicating pages.

### Features

- `thesistester/classic_nav.py`: Discuss this run, Open exact run in Backtest,
  clarification→classic navigation + caption prefill, identity badge helpers.
- Session: `classic_active_run_id`, `classic_focus_run_id`, `classic_nav_prefill`.
- Identity relation codes from immutable identities (metadata/peek only until
  open/restore/explain/compare).
- Surfaces: Backtest/Bundles Discuss; Assistant Open exact + clarification
  Open; Data/Levels/Setup/Backtest prefill captions; chrome active-run badge.

### Regression safety

- Badge tests assert relation codes, not display labels.
- Thesis switch clears run/focus/prefill; cross-thesis run selection fails closed.
- Open exact remains hash-verified bundle restore.
- Clarification path does not auto-mutate classic page settings and does not
  stage `classic_pending_navigation` (Data/Levels lack chrome consumers).
- Backtest clarification prefill renders before signals/trades `st.stop()`.
- Discuss realigns Assistant thesis selection; stale active-run breadcrumb
  falls back to latest discussable run.
- Recording APIs stay out of `classic_context`.

### Tests

- `tests/test_classic_nav.py`.

---

## CAI-9 — Evidence-Backed Page Capability Expansion ✅ Implemented

Closes the “second application” gap with bounded, hash-verified page summaries
and controlled classic proposals (charts stay on classic pages).

### Features

- `thesistester/assistant/page_summaries.py` + inspect handlers for Levels,
  Signals, Backtest, Grid, Validation.
- Evidence packet page-summary paths + grounded templates.
- `CLASSIC.propose_page_change` / `classic_proposal.py`: draft stage + explicit
  Apply on Setup Builder / Backtest (`classic_page_proposal` with `thesis_id`);
  same-thesis re-link preserves staged proposals; SL/TP drafts require `>= 1`.
- Assistant UI: per-run page summary buttons + proposal staging.

### Regression safety

- Numeric claims grounded in evidence paths; handlers never return DataFrames.
- Hash mismatch fails closed on inspect.
- Proposals do not mutate classic settings until Apply; thesis-scoped apply.
- Thesis switch clears staged proposals; apply/stage stay out of
  `classic_context`.
- Discuss requires completed hash-verified bundle provenance.

### Tests

- `tests/test_cai9_page_capabilities.py`.

---

## CAI-10 — Artifact Operations, Retention, and Performance Hardening ✅ Implemented

Makes internal execution artifacts observable and operable for long research use
without auto-deleting user-owned research assets.

### Features

- Inspect/list: identity, size, age, producer, schema/engine, hit counts;
  store-level hit/miss stats (`list_execution_artifacts`,
  `get_execution_cache_stats`).
- Safe delete + full-store bounded eviction (`max_entries` /
  `max_total_bytes` / `max_age_seconds` from `accessed_at`) under
  `execution_artifacts/v1` only.
- Source relocation: `rebind_source_path` after content-identity verification.
- Assistant: `CACHE.inspect_artifacts`, `CACHE.delete_artifact`,
  `CACHE.evict_artifacts`, `CACHE.rebind_source_path`.
- Warm-path informational harness (`tests/benchmarks/cai_warm_path.py`);
  signal second-layer cache remains deferred.

### Regression safety

- Eviction never touches `datasets` / `levels` / `signals` / `setups` /
  `assistant`.
- Retained research bundles remain self-contained after eviction.
- Cache deletion → cold miss → equal canonical bundle hash on recompute.
- Benchmarks are non-gating; correctness stays hash/golden-master based.

### Tests

- `tests/test_cai10_artifact_ops.py`
- `tests/benchmarks/test_cai_warm_path.py`

---

## R1 — Execution Realism ✅ Implemented

Adds optional commission and slippage to `simulate_trades`. Defaults preserve legacy
gross behavior. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §1.

---

## R2 — Session-Aware Day-Trading Engine ✅ Implemented

Adds `flat_by_session_close` mode to `simulate_trades`. `SESSION_CLOSE` and `DATA_END`
exit types supported. Documented in `ASSUMPTIONS_AND_LIMITATIONS.md` §3.

---

## R3 — Point-in-Time Audit and Fixes ✅ Implemented

R3 adds future-shock regression tests and documentation. Merge readiness still requires
the repository test suite to pass in CI/local verification.

- `docs/POINT_IN_TIME_GUARANTEES.md` created and specific to current code.
- Future-shock regression tests added in `tests/test_r3_point_in_time.py` (17 tests).
- `ASSUMPTIONS_AND_LIMITATIONS.md` updated with PIT scope and limitations.
- Audited paths showed no look-ahead bugs; deliverable is documentation plus regression
  coverage for audited behaviors.
- `confirm_3bar` is treated as legacy/internal in R3 documentation because it is not in
  the public `generate_signals()` trigger set.

See `docs/POINT_IN_TIME_GUARANTEES.md` for audit details, coverage notes, and limits.

---

## R4 — Exposure and Trade Lifecycle Model ✅ Implemented

Adds explicit overlap admission controls (`allow_all`, `single_position`,
`single_direction`, `single_setup`) with deterministic signal admission order,
optional cooldown, skipped-signal diagnostics, scoped UI controls, validation
warning, and scoped export assumptions.

---

## R5 — Walk-Forward / Out-of-Sample Validation ✅ Implemented

Adds deterministic bar-window walk-forward diagnostics for train-window SL/TP
selection and following out-of-sample evaluation, with compact validation-page
UI integration and scoped export/report fields.

---

## R6 — Institutional Metrics Upgrade ✅ Implemented

Adds additive institutional-grade trade diagnostics (distribution, tail, streak,
drawdown-pain, and outlier-dependency metrics) to summaries, grid results,
compact UI/report sections, and targeted regression coverage.

---

## R7 — Futures Contract Roll Methodology ✅ Implemented

Adds explicit roll-policy modes (`single_contract`, `external_continuous`,
`segmented_contracts`), compact data-page assumptions controls, roll metadata
validation/gap diagnostics, and export/report inclusion of roll assumptions for
auditability without introducing internal price adjustment.

---

## R8 — Save-as-Default Execution Settings ✅ Implemented

Adds narrow, regression-safe user-controlled persistence for Backtest and Grid
Search execution settings.

### Scope

UI/persistence layer only. Engine and analytics code (`simulate_trades`,
`run_sl_tp_grid`, `thesistester/analytics/metrics.py`) are **unaffected**.

### Features

- **💾 Save execution settings as default** button on Backtest and Grid Search
  sidebar pages.  Settings are persisted only on explicit click, never on run.
- **↩ Reset to built-in defaults** button clears saved defaults and reverts
  widgets to built-in values on the next render.
- Saved defaults are loaded once per session and injected only into absent
  `st.session_state` keys — in-session user edits are never overwritten.
- **Independent namespaces** in `ui_state.json`:
  - `backtest_defaults` — covers SL/TP ticks, commission, slippage, max-holding-bars,
    same-bar exit, session close, timezone, no-new-entries cutoff, exposure policy, cooldown.
  - `grid_defaults` — same fields plus SL/TP range start/stop/step, ranking metric,
    min trades, directional ranking settings.
- Saving Backtest defaults never affects Grid defaults, and vice versa.
- Both namespaces are **versioned** (`defaults_schema_version = 1`). Schema drift
  (version mismatch) causes defaults to be silently ignored; widgets fall back to
  their built-in values.
- Invalid saved values (unknown policy/timezone/metric, out-of-range numbers,
  malformed time strings, non-bool booleans) are **dropped silently** before
  injection so they never reach the engine.
- Existing unrelated UI state keys (e.g. `active_dataset_id`) are always preserved.

### New files

| File | Purpose |
|---|---|
| `thesistester/execution_defaults.py` | Validation, injection, and collection helpers |
| `tests/test_backtest_grid_defaults.py` | Covers roundtrip persistence, namespace isolation, schema drift, reset behavior, validation/sanitization, widget/result key separation, and engine isolation |

### Modified files

| File | Change |
|---|---|
| `thesistester/persistence/local_store.py` | Added `BACKTEST_DEFAULTS_SCHEMA_VERSION`, `GRID_DEFAULTS_SCHEMA_VERSION`, and 6 new functions |
| `thesistester/persistence/__init__.py` | Exported new constants and functions |
| `pages/7_Backtest.py` | Added stable `key=` to execution-setting widgets; load/save/reset logic |
| `pages/8_Grid_Search.py` | Added stable `key=` to execution-setting widgets; load/save/reset logic |

---

## R9 — Engineering Hygiene: Packaging, CI, Lint ✅ Implemented

First milestone of the proposal roadmap (`docs/ENGINEERING_PROPOSAL.md` §5 R9). Makes the
repo's regression-safety conventions machine-enforced instead of aspirational. **No runtime
behavior change:** the only code edits are mechanical (ruff safe fixes and one formatting
pass), verified by the unchanged 1516-test suite.

### Scope

Tooling, CI, and documentation only. Engine, analytics, levels, persistence, and UI logic are
**unaffected**; no `st.session_state` key was added, removed, or re-typed.

### Features

- **Packaging** — `pyproject.toml` (setuptools) makes `thesistester` importable after
  `pip install -e .`, with `requires-python = ">=3.10"`, dependency ranges mirroring
  `requirements.txt` plus conservative next-major caps, and a `dev` extra
  (`pytest`, `pytest-cov`, `ruff`). Version is read from `thesistester.__version__`, so it
  cannot drift from the package.
- **CI** (`.github/workflows/ci.yml`), blocking on red:
  - `ruff check` + `ruff format --check`;
  - full suite on Python 3.10 / 3.11 / 3.12 with `--cov=thesistester`;
  - clean-venv `pip install -e .` + import + `pip check`;
  - **golden-master regeneration guard** — fails any PR that changes
    `tests/fixtures/golden/**` without the `GOLDEN_REGEN` label
    (`docs/ENGINEERING_PROPOSAL.md` §4.1 rule 3).
  - Coverage is reported with an informational floor (warn only, never blocking); the R9
    baseline is 88% statement+branch coverage.
- **Lint/format** — deliberately minimal ruff rule set (`E4`, `E7`, `E9`, `F`, `W`) at line
  length 100, with two documented per-file ignores: `E402` for Streamlit pages (they bootstrap
  `sys.path` before importing) and `E741` for test fixtures using `l`/`O` bar shorthand.
  Markdown is excluded: ruff formats fenced Python blocks, which would rewrite illustrative
  snippets in historical design documents. A
  one-time `ruff format` pass landed in its own commit; AST dumps of all 108 tracked Python
  files are identical pre/post format, so the pass is provably semantics-preserving.
- **Golden-master spec** — `tests/fixtures/golden/README.md` records the operational contract
  (files, recording, verification, regeneration policy). Two measured findings shape it:
  the repo's deterministic frame hash is *not* stable across pandas majors (dtype renames,
  `datetime64[ns]` → `datetime64[us]`), and `build_research_bundle` bytes are not reproducible
  (wall-clock `created_at` + zip metadata). Golden comparison is therefore value-level, with
  bundle hashing over a canonical projection and scoped to the recorded pandas major. Golden
  *data* is now active: a dedicated pre-R12 PR records a deterministic three-session NQ
  fixture, nine legacy trades (including six same-bar both-hit cases), readable CSV,
  provenance manifest, and canonical bundle hash. `tests/test_golden_master.py` rebuilds
  the fixture and gates exact legacy values on every supported Python/pandas matrix cell.
- **LICENSE** — MIT.

### New files

| File | Purpose |
|---|---|
| `pyproject.toml` | Packaging metadata, dependency ranges/caps, ruff/pytest/coverage config |
| `.github/workflows/ci.yml` | Lint, test matrix, packaging check, golden-regeneration guard |
| `LICENSE` | MIT license |
| `tests/fixtures/golden/README.md` | Golden-master operational spec (§4.1) |

### Modified files

| File | Change |
|---|---|
| `.gitignore` | Re-includes `tests/fixtures/golden/*.parquet` (repo-wide `*.parquet` ignore would otherwise silently drop golden fixtures); ignores ruff/coverage/packaging artifacts |
| 101 `.py` files | One-time `ruff format` pass (formatting only) |
| 13 `.py` files | Ruff safe lint fixes: unused imports/locals, split import line, two placeholder f-strings, `== False` → `.eq(False)` |
| `README.md`, `docs/AGENT_GUIDE.md`, `docs/ARCHITECTURE.md` | Dev setup, CI gates, golden policy, packaging boundary |

---

## R10 — MAE/MFE Excursion Analytics & SL/TP Calibration ✅ Implemented

Adds a pure post-trade analytics layer over the engine's existing
`mae_points` / `mfe_points` trade columns. No engine behavior changes and no
golden-fixture regeneration required.

### Scope

Analytics, Validation-page display, report/export, research-bundle persistence,
and docs only. `simulate_trades()` output and trade-admission semantics are
**unchanged**.

### Features

- `thesistester/analytics/excursions.py`:
  - R-normalized MAE/MFE (`mae_r`, `mfe_r`) using each trade's
    `stop_loss_ticks * tick_size` risk distance.
  - Edge-ratio and giveback diagnostics.
  - Grouped MAE/MFE distributions by existing trade columns (direction,
    trigger, trigger variant, level-source mode, RTH/time buckets).
  - MAE×MFE quadrant counts for default 1R/1R thresholds.
  - Counterfactual SL/TP hit-probability grid from terminal excursions with
    explicit `both_hit_rule` (`stop_first`, `target_first`,
    `exclude_ambiguous`). Default `stop_first` matches the engine's
    pessimistic same-bar ambiguity rule.
  - Bars-held edge-ratio decay proxy.
- Validation page:
  - Independent **MAE/MFE excursion analytics** section.
  - Stores additive session keys: `excursion_summary`, `excursion_config`,
    `excursion_grouped_summary`, `excursion_calibration_grid`,
    `excursion_quadrant_summary`.
  - Shows edge metrics, MAE/MFE scatter, grouped table, quadrant table, and
    SL/TP probability heatmap.
- Report/export:
  - JSON artifact includes `results.excursion_summary` and excursion tables.
  - Markdown report adds an **Excursion Analytics** section only when results
    exist.
  - CSV downloads include grouped, calibration-grid, and quadrant outputs.
  - Research bundles roundtrip the new R10 session keys.

### Regression safety

- No engine or level/signal computation changes.
- Deterministic: no RNG.
- Empty/partial trade tables are safe.
- R10 summary is schema-versioned (`schema_version = 1`).
- Docs updated in the same PR: glossary formulas, assumptions/caveats,
  architecture session-state contract, and this roadmap entry.

### Tests

- `tests/test_excursions.py`: hand-computed R normalization, distributions,
  quadrants, stop-first / target-first / exclude-ambiguous calibration,
  edge-ratio decay proxy, empty safety, and stable summary keys.
- Existing report and research-bundle tests extended for R10 JSON/Markdown/CSV
  and bundle roundtrip.

---

## R11 — Monte Carlo Simulation Suite ✅ Implemented

Adds seeded trade-sequence Monte Carlo diagnostics on completed backtest trades.
No engine behavior changes and no golden-fixture regeneration required.

### Scope

Pure analytics plus Validation-page display, report/export, research-bundle
persistence, stale-state cleanup, and docs. The existing `validation_summary()`
contract remains unchanged.

### Features

- `thesistester/analytics/monte_carlo.py`:
  - `path_metrics_from_r()` for final R, max drawdown R (same 0R-anchored
    drawdown convention as `metrics.py`), and max loss streak.
  - `monte_carlo_reshuffle()` — random permutations of realized trade order.
  - `monte_carlo_skip()` — independent missed-trade robustness by replacing
    random trade slots with 0R.
  - `monte_carlo_block_resample()` — circular fixed-block bootstrap preserving
    local streak structure better than iid reshuffle.
  - `monte_carlo_summary()` — schema-versioned (`schema_version = 1`) export
    contract with observed equity, per-method percentile bands, drawdown
    exceedance probabilities, and equity-fan bands.
- Validation page:
  - Independent **Monte Carlo path robustness** section with method selection,
    simulation count, seed, skip fraction, block length, drawdown thresholds, and
    its own run button.
  - Stores additive session keys: `monte_carlo_summary`,
    `monte_carlo_config`.
  - Displays observed/P50/P95 metrics, drawdown probability table, and fan chart
    per selected method.
- Report/export/bundles:
  - JSON artifact includes `results.monte_carlo_summary`.
  - Markdown report adds a **Monte Carlo Path Robustness** section only when
    results exist.
  - Research bundles roundtrip Monte Carlo summary/config.
  - Data reload clears stale R10/R11 analytics keys.

### Regression safety

- No engine, levels, signals, or `validation_summary()` changes.
- Deterministic RNG via `np.random.default_rng(random_state)`.
- Empty/missing `r_multiple` tables are safe.
- Full outputs are additive and schema-versioned.
- Docs updated in the same PR: glossary formulas, assumptions/caveats,
  architecture session-state contract, and this roadmap entry.

### Tests

- `tests/test_monte_carlo.py`: path metrics, empty safety, seeded
  determinism, reshuffle final-R preservation, skip behavior, block-resample
  streak preservation fixture, fan-chart shape, drawdown probabilities, and
  stable summary keys.
- Existing report and research-bundle tests extended for R11 JSON/Markdown and
  bundle roundtrip.

---

## R18 — Headless Research API + Batch Experiment Runner ✅ Implemented

Adds a typed, Streamlit-free orchestration facade and versioned batch runner
over the existing pure research pipeline. No engine behavior, Streamlit page,
or `st.session_state` contract changes.

### Scope

New API/CLI entry points, canonical bundle comparison, packaging dependency,
tests, and documentation. Existing level, signal, OTF, simulation, grid, and
validation implementations are **unchanged**.

### Features

- `thesistester/api.py`:
  - typed plain-data handoffs for dataset, levels, setup, signals, backtest,
    grid, and validation;
  - UI-equivalent shared OTF pre-filter composition for backtest and grid;
  - deterministic Phase 8, R10 excursion, and R11 Monte Carlo battery;
  - `run_experiment()` produces the mapping consumed by research bundles.
- `thesistester/cli.py` and `thesistester/__main__.py`:
  - `python -m thesistester run experiment.yaml`;
  - schema-version-1 YAML with unique safe run names and paths relative to the
    definition;
  - one research bundle per run plus `results_index.csv`;
  - spawned `ProcessPoolExecutor` parallelism across independent runs only,
    preserving YAML result order.
- `canonical_bundle_hash()` compares logical bundle contents. It omits
  nondeterministic manifest/archive time metadata and hashes parquet members
  through the established DataFrame projection.
- PyYAML is an explicit runtime dependency in both install paths.

### Regression safety

- Zero engine-internal changes and zero page changes.
- Existing pages continue to use `st.session_state`; the API is an additional
  consumer of existing pure functions.
- Unknown facade configuration keys fail closed.
- Seeded diagnostics remain deterministic, and each individual run remains
  single-threaded.
- Bundle schema remains version 1; raw ZIP bytes are never treated as a
  determinism contract.
- Agent documentation restates PIT boundaries, multiple-testing risk, and
  diagnostic-not-proof framing.

### Tests

- `tests/test_api.py`: API/UI backtest-composition parity, deterministic grid
  and validation batteries, plain-data outputs, and fail-closed config.
- `tests/test_cli.py`: real module CLI bundle parity, canonical hash equality,
  schema validation, and serial-vs-parallel identity for both index rows and
  every output bundle.

---

## R12 — Look-Inside-Bar Intrabar Fill Refinement ✅ Implemented

Adds deterministic, explicit SL/TP event-order assumptions while preserving
the exact legacy engine path by default.

### Features

- `intrabar_model="sl_first"` remains the default and preserves legacy trade
  columns, values, reasons, and return types.
- `path_open_proximity` walks O→H→L→C or O→L→H→C according to the extreme
  nearest the open; proximity ties remain pessimistic and audited.
- `subtimeframe` walks observed lower bars in order. Coverage must be strictly
  finer, complete, exactly divisible, duplicate-free, and OHLC-reconciling;
  there is no silent fallback.
- `subtimeframe_conservative` is an explicit, opt-in mixed model for vendor
  exports with isolated lower-bar gaps: complete reconciled groups replay
  observed bars, while unavailable groups use SL-first and are audited.
- Preparation caches per-row OHLC validation masks, then evaluates them only
  for complete, exactly aligned groups. This preserves strict errors and
  conservative fallback semantics while avoiding repeated per-group coercion.
- Non-legacy trades append model, resolution, parent-both-hit, residual
  ambiguity, and lower exit timestamp fields.
- `SimulationResult` provides skipped signals and schema-versioned run
  diagnostics without changing the legacy DataFrame/tuple API.
- Grid and walk-forward hold one model fixed and expose diagnostic columns.
- R18 schema version 1 accepts optional `dataset.subtimeframe_path`; reports
  and bundles preserve policy, diagnostic, and lower-data provenance.
- The Data page provides an optional canonical lower-timeframe CSV upload for
  interactive R12 runs. It produces the existing session contract only after
  strict parent coverage/alignment/OHLC reconciliation; the R18 YAML path and
  engine behavior are unchanged.

### Regression safety

- A dedicated prerequisite PR activates the §4.1 golden gate before any engine
  edit. Its fixture contains six deliberate both-hit legacy trades.
- No golden artifact is regenerated by R12.
- Default `sl_first` output remains exact, including canonical bundle hash.
- New parameters are keyword-only and non-legacy behavior is opt-in.
- The interactive lower-timeframe upload invalidates execution-derived session
  outputs when changed, while retaining primary data, levels, and signals.
- Future-shock tests cover all three models.
- Parent-bar MAE/MFE, exposure admission, costs, holding limits, and forced
  exit semantics remain unchanged.

### Tests

- `tests/test_intrabar.py`: hand-computed long/short path order, proximity tie,
  observed lower-timeframe ordering, residual ambiguity, strict coverage,
  legacy identity, grid diagnostics, and future-shock safety.
- `tests/test_golden_master.py`: exact legacy values, dtype families, readable
  projection, and pandas-major-scoped bundle hash.
- API/CLI, defaults, grid, walk-forward, reporting, and research-bundle tests
  cover end-to-end policy propagation and persistence.

---

## R13 — Break-Even and Trailing Stop Exit Management ✅ Implemented

Adds the two dynamic bracket-management rules used most often by discretionary
day traders while keeping the fixed-bracket legacy engine untouched by default.

### Features

- `simulate_trades()` accepts keyword-only:
  - `breakeven_after_r`;
  - `trailing_after_r`;
  - `trailing_distance_ticks`.
- Defaults `None` preserve fixed SL/TP behavior and golden-master outputs.
- Stop management commits after completed bars and becomes active on the next
  parent bar. This avoids optimistic same-bar OHLC ordering assumptions.
- Break-even exits use reason `BE`; trailing exits use reason `TRAIL`.
- `stop_price` remains the initial bracket stop; moved-stop evidence is stored
  in additive audit columns such as `active_stop_price_at_exit`,
  activation bar indices, and `stop_adjustment_path`.
- Grid supports capped BE/trailing cartesian sweeps. UI grid runs apply one
  fixed policy across every cell by default; R18/API callers may provide
  explicit value lists.
- Walk-forward applies the train-selected BE/trailing parameters to OOS folds.
- Reports and research bundles preserve policy/diagnostic snapshots.

### Regression safety

- No golden artifacts are regenerated.
- Legacy `sl_first` + no exit management remains byte/value identical.
- All new behavior is opt-in and deterministic.
- Initial-risk R denominators and MAE/MFE semantics remain unchanged.
- R12 intrabar models still own stop-vs-target event ordering for active stops.
- Invalid configurations fail closed: trailing requires a positive distance;
  thresholds/distances must be finite and positive.

### Tests

- `tests/test_exit_management.py`: long/short BE, slippage-costed BE, long/short
  trailing, entry-bar no-arm behavior, R12 model interactions, invalid config,
  disabled legacy schema, and grid cell cap.
- Existing golden, intrabar, grid, walk-forward, API/CLI, defaults, reporting,
  and research-bundle tests extended for R13 propagation and persistence.

---

## R14 — Session-Aware Walk-Forward + WFA Matrix ✅ Implemented

Extends R5 walk-forward validation with observed trading-session boundaries
while retaining legacy bar-index rolling folds as the default.

### Features

- `fold_mode="sessions"` constructs folds from complete ETH-boundary-aware
  trading-session dates; shortened observed sessions remain atomic.
- `window_mode` supports fixed rolling and growing anchored train windows.
- Fold rows add session boundaries/counts, expectancy retention ratio, and
  degradation percentage while preserving all legacy columns.
- `WalkForwardResult` returns folds, fold-owned OOS trades, stitched equity,
  schema-version-2 summary, and warnings.
- Overlapping OOS windows default to no stitch; explicit `first`/`last`
  ownership deduplicates executable entries.
- `run_wfa_matrix()` emits deterministic train-session × test-session
  robustness cells for the Validation heatmap.
- Validation UI, R18 API/CLI, reports, CSV export, stale-state cleanup, and
  research bundles preserve all R14 artifacts.

### Regression safety

- Default `fold_mode="bars"` and `window_mode="rolling"` reproduce the existing
  boundary sequence and fold execution.
- No engine, level, signal, or golden artifact changes.
- Session folds assign signals by executable entry ownership and never split an
  observed trading session.
- Future-shock tests prove appended sessions do not alter existing folds.
- Overlap handling is explicit; stitched equity cannot silently double-count.

### Tests

- `tests/test_walk_forward.py`: shortened-session atomicity, rolling/anchored
  boundaries, bar-mode identity, stitched OOS equity, overlap ownership,
  session future shock, and deterministic matrix ordering.
- API/CLI, reporting, research-bundle, OTF, and golden tests cover R14
  propagation and regression safety.

---

## R15 — PBO, Deflated Sharpe, and Vs-Random ✅ Implemented

Adds a separate, opt-in multiple-testing diagnostic battery; the existing
Phase 8 heuristic `grid_overfit_diagnostics()` and `validation_summary()`
contract are unchanged.

### Features

- `thesistester/analytics/overfitting.py`:
  - deterministic CSCV/PBO over retained per-cell grid trade sequences;
  - unannualized per-trade R PSR and DSR using declared grid trial counts;
  - seeded vs-random next-open entry benchmark using the existing simulator and
    matching execution assumptions;
  - fail-closed selection: DSR and vs-random require a replayed grid cell that
    passes the declared selection rule, never the separate Phase 5 trade table;
  - schema-version-1 combined summary and explicit caveat.
- Validation page has an independent, cost-labelled R15 run button and displays
  PBO, deflated Sharpe probability, vs-random p-value, and CSCV split rows.
- R18 API/CLI, reports, research bundles, stale-state cleanup, and bundle
  previews preserve R15 summary/config.

### Regression safety

- No engine, signal, level, grid-summary, or `validation_summary()` change.
- Heavy re-simulation is opt-in; RNG uses explicit local seeded streams.
- CSCV split enumeration and grid-cell tie order are deterministic.
- Existing grid-overfit heuristic remains available alongside R15.
- All Sharpe outputs are explicitly non-annualized per-trade R diagnostics.

### Tests

- `tests/test_overfitting.py`: exact four-partition CSCV fixture
  (`PBO=1/3`), deterministic splits, PSR/DSR availability/deflation, seeded
  vs-random finite p-values, and stable summary schema.
- API, CLI, report, research-bundle, and legacy validation tests cover opt-in
  persistence and unchanged default paths.

---

## R16 — Price-Series Noise Test ✅ Implemented

Adds an opt-in full-pipeline input-robustness diagnostic. It does not alter
levels, signals, engine semantics, or the existing validation contract.

### Features

- `thesistester/analytics/noise.py` applies seeded symmetric OHLC noise scaled
  by rolling ATR or bar range, then repairs high/low bounds so every synthetic
  bar remains valid.
- The R18 facade recomputes levels, signals, OTF admission, and trades for
  each replica; parent OHLC input is copied and lower-timeframe intrabar data
  remains pinned rather than fabricated.
- The schema-version-1 result records perturbation settings, expectancy/PF
  percentile bands, and baseline-trade persistence keyed by `signal_id`
  (falling back to direction plus entry timestamp).
- Validation UI, YAML/API execution, reports, research bundles, and stale-data
  cleanup preserve the exported summary.

### Regression safety

- No engine, level, signal, grid, or `validation_summary()` behavior changes.
- Replica streams use local explicit seeded RNGs and stable sequential order.
- The source DataFrame is never mutated; every replica validates OHLC bounds.
- Heavy work remains opt-in with a visible `replicas × full pipeline` cost
  warning. A 1,000-replica run is supported but may be expensive before R22.

### Tests

- Property-style loops assert ATR- and range-scaled replicas preserve OHLC
  validity and source immutability.
- Seeded summary/schema tests lock deterministic output.
- A single-bar trigger fixture verifies materially degraded persistence under
  perturbation.
- API, report, bundle, and existing golden-master gates cover additive wiring.

---

## R22 — `simulate_trades` Performance Baseline and Core Boundary ✅ Implemented

Adds a reproducible serial performance ruler and a narrow internal hot-path
boundary without changing simulation behavior or adding an accelerated mode.

### Features

- `tests/benchmarks/` supplies deterministic, informational workloads for
  signal scaling, bars-held scaling, and a 3×3 grid multiplier.
- `docs/SIMULATE_PERF.md` records the command, fixture design, environment,
  median/p95 baseline measurements, and the acceleration decision record.
- `thesistester.engine.sim_core` owns immutable parent OHLC snapshots and
  one-bar bracket resolution; `simulate_trades` remains the sole orchestrator
  of admission, caps, MAE/MFE, costs, trade records, and diagnostics.

### Regression safety

- The public `simulate_trades` signature, defaults, trade schema, and return
  forms are unchanged.
- No vectorized, Numba, or parallel path is enabled. Future acceleration must
  measure against the committed baseline and assert exact serial parity.
- Legacy goldens, intrabar variants, exit management, and Phase-5 admission
  tests gate the internal extraction.

### Tests

- Benchmark fixture smoke tests confirm all documented scenarios run.
- Golden master, intrabar, exit-management, and Phase-5 engine tests retain
  exact legacy behavior after the core-boundary extraction.

---

## R21 — Multi-Setup Portfolio Layer ✅ Implemented

Adds an opt-in, post-trade portfolio diagnostic that composes independent
completed setup runs without changing single-setup execution semantics.

### Features

- `thesistester/analytics/portfolio.py` tags and merges same-instrument,
  shared-bar-index trade frames, then applies deterministic R4-equivalent
  portfolio admission (`allow_all`, single position/direction/setup, cooldown).
- It produces combined R/currency equity, return and drawdown correlation
  matrices, admission diagnostics, and leave-one-out marginal contribution.
- The Portfolio page accepts current Backtest trades plus completed trade CSVs;
  reports and research bundles preserve schema-version-1 summaries and tables.

### Regression safety

- R21 is additive post-trade analytics only. It neither invokes nor modifies
  `simulate_trades`, signals, levels, or individual setup outputs.
- Every input requires canonical completed-trade columns; supplied parent bar
  counts hard-fail out-of-range bar indices.
- Results state that portfolio outputs are not continuous capital, margin,
  liquidity, or fill simulations.

### Tests

- Disjoint setups under `allow_all` equal the sum of parts.
- Hand-computed overlap, direction, cooldown, and bar-index fixtures lock
  admission behavior; correlation matches pandas reference.
- API, research-bundle, legacy golden, lint, full-suite, and package gates
  cover additive wiring.

---

## R20 — Trade-Review Visualization (Replay-lite) ✅ Implemented

Adds an opt-in, read-only per-trade inspection view without changing levels,
signals, trade execution, metrics, or persisted research results.

### Features

- The Backtest page provides a bounded selected-trade candlestick window with
  entry, initial SL/TP, actual exit, linked level/zone overlays, and terminal
  MAE/MFE envelope shading.
- Users can export a ZIP of PNG reviews for up to twenty worst losing trades;
  each image independently clips OHLC, levels, and zones to the selected
  trade's buffer.
- `kaleido` supplies the Plotly PNG renderer. The export fails visibly if its
  renderer is unavailable instead of silently substituting another format.

### Regression safety

- R20 reads existing frames only and never invokes or alters the engine.
- Review windows are strictly bounded to the selected hold interval plus a
  user-capped buffer; no full-dataset review mode exists.
- MAE/MFE shading is explicitly documented as a terminal parent-bar envelope,
  not an intrabar path or fill-order reconstruction.

### Tests

- Figure-structure smoke tests assert single-trade markers, SL/TP/final-stop
  and MAE/MFE shapes, JSON serializability, input immutability, and bounded
  per-trade windows.
- Golden-master trade fixtures and engine semantics are unchanged.

---

## R19 — Parameter Sensitivity Profiling (SPP-lite) ✅ Implemented

Adds an opt-in, schema-version-1 local execution-parameter robustness
diagnostic without changing engine, signal, grid, or `validation_summary()`
semantics.

### Features

- `thesistester/analytics/sensitivity.py` replays one selected grid cell while
  changing one active numeric execution parameter at a time over deterministic
  ±fraction steps.
- It records expectancy-R, profit-factor, and trade-count curves, and flags a
  parameter as fragile only where the curve contains both positive and
  negative expectancy values. Tick-valued parameters use nearest-integer tick
  rounding with duplicate candidates collapsed; R thresholds remain continuous.
- R18 API/YAML validation, the Validation page, reports, research bundles, and
  stale-data cleanup preserve the exported summary.

### Regression safety

- The feature is default-off and purely additive; it reuses the unchanged
  serial `simulate_trades` engine through explicit selected-cell replays.
- No RNG is required, but `random_state` remains recorded for stable
  configuration identity and forward compatibility.
- The UI presents replay cost before running; local OAT curves explicitly do
  not establish interaction robustness, sampling uncertainty, or future edge.

### Tests

- Cliff-edge and plateau fixtures assert sign-flip fragility classification,
  tick rounding, and deterministic output.
- API/YAML, report/bundle, lint, full-suite, and golden-master gates protect
  the unchanged legacy pipeline.

---

## R17 — Vendor Ingestion and Tick Capture ✅ Implemented

Adds explicit, opt-in data-format profiles while retaining the existing
canonical/Quantower CSV parser as the unchanged default path.

### Features

- `load_ohlcv()` accepts `canonical`, `ninjatrader`, `sierra_intraday`,
  `databento_trades`, `tick_capture`, and `second_capture` profiles; no
  profile is auto-detected.
- NinjaTrader semicolon exports, Sierra Date/Time + Last exports, and
  Databento fixed-point trade rows are normalized into canonical OHLCV.
- Trade/tick/second captures aggregate deterministically to one-minute OHLCV
  (first/max/min/last/sum); Databento bid/ask fields are retained in raw
  capture only and remain unused by the bar engine.
- Local datasets can persist an optional `raw.parquet` sidecar with profile,
  raw-row count, and interval provenance. Dataset IDs continue to hash only
  canonical engine input.
- UI/API/CLI accept the explicit profile and MNQ/MES presets use CME-standard
  0.25-point ticks with $2/$5 point values respectively.

### Regression safety

- The canonical profile remains the default and current sample CSV output is
  byte-identical to the legacy loader.
- No engine, level, signal, R7 roll metadata, or R12 subtimeframe semantics
  changed. Captured ticks are not presented as subtimeframe replay data.
- All vendor mappings are profile-gated; selecting the wrong profile fails
  clearly instead of silently reinterpreting a file.

### Tests

- Synthetic NinjaTrader, Sierra, Databento, and generic capture fixtures
  verify canonical bar output and raw quote preservation.
- Canonical sample identity, loader aliases, raw-sidecar round trip, MNQ/MES
  contract values, API validation, and full golden-master gates remain covered.

---

## Session Entry Window (SW0–SW7 + SW2b) ✅ Engineering-signed

Closes the Discover → Scope → Re-sim → Optimize → Prove loop when Time Analysis
shows a strong RTH segment (e.g. `rth_open_30m`) while the all-day Performance
Summary looks poor. SW2b cutoff skip audit shipped as follow-up (#299).

**Canonical spec:** `docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md` (normative contracts **C1–C9**)  
**Release evidence:** `docs/archive/SESSION_ENTRY_WINDOW_RELEASE_EVIDENCE.md`

| Milestone | Intent |
|---|---|
| SW0 | Plan lock + legacy golden gate confirmation + C1–C9 ✅ |
| SW1 | Post-hoc Focus summary (no re-sim); shared RTH export ✅ |
| SW2 | Opt-in `entry_window` admission + enabled golden + Focus≡Admit (C7) ✅ |
| SW2b | Audit `no_new_entries_after` → `after_entry_cutoff` + UI/docs honesty ✅ ([#299](https://github.com/AccumuLatata/ThesisTester/pull/299)) |
| SW3 | API + Backtest Admit controls ✅ |
| SW4 | Time Analysis Promote + Focus↔Admit handoff ✅ |
| SW5 | Grid + Validation/WFA/sensitivity inherit window (fixed constraint) ✅ |
| SW6 | Setup persistence, export, assistant honesty ✅ |
| SW7 | Hardening + release evidence ✅ ([#298](https://github.com/AccumuLatata/ThesisTester/pull/298)) |

**Regression posture:** additive, default-off; legacy `trades_legacy` golden
must stay value-identical; Focus and Admit must never be conflated in UI copy;
C7 identity required when engine-touched.

---

## Research Study Runner (RS0–RS5 MVP + post-MVP) 📝 Plan-locked

Additive headless **StudySpec → expand → study-owned execute → report → promote**
series so researchers (or external agents) can run closed multi-factor
confluence studies without touching engine/pages. Classic Streamlit research
remains undisturbed through RS5. Distinct from confluence-combo attribution
(`docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`).

**Canonical spec:** `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` (§12 post-MVP)

| Milestone | Intent |
|---|---|
| RS0 | Plan lock + roadmap/docs index ✅ |
| RS1 | StudySpec schema + fail-closed validation ✅ |
| RS2 | Deterministic expander → `experiment.yaml` + factor map ✅ |
| RS3 | CLI `study expand|run` + study-owned ledger/resume/workers + confirm ✅ |
| RS4 | Overview aggregator (CSV/MD, OTF Δ, honesty; PF from bundles) ✅ |
| RS5 | Staging/promote drafts + stage-first examples + USER_GUIDE recipe ✅ |
| **Post-MVP sequence** | **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5 → RS-D8 → RS-D9** (do not reorder without plan amend) |
| RS-D7 | Additive `results_index` `profit_factor` + `win_rate` (soft-resume field backfill + ordered key parity) ✅ |
| RS6 | Default-off registered `STUDY.*` capabilities (handlers refuse when off) + minimal CLI/confirm docs ✅ |
| RS-D2 | Streamlit Studies **viewer** (artifacts-only; no in-app run) ✅ |
| RS-D4 | Per-cell WFA/validation/overfitting diagnostic rollup (compose-only) ✅ |
| RS-D5 | External Grok Bot routine pack (docs + `examples/studies/agents/`) ✅ |
| RS-D8 | Studies authoring preview (canonical YAML validate + dry expand + ledger watch) ✅ |
| RS-D9 | Studies CLI-launch button (spawn existing `study run`; no in-process execute) ✅ |
| Parked | RS-D1 NL compiler; RS-D3 `run_batch` continue; RS-D6 new factor types |

**Regression posture:** no `engine/` edits in this series; no golden regeneration;
`python -m thesistester run` / `run_batch` semantics identical (study layer owns
continue-capable ledger + soft resume); RS-D7 additive/default-compatible index
columns; RS6 tools **default-off** with two-step confirm (no MCP server); RS-D2
**read-only** viewer; RS-D4 per-cell compose-only (no cross-cell PBO); RS-D5
external docs/examples only (no product host / MCP); RS-D8 preview on the
same Studies page; RS-D9 may spawn the existing CLI `study run`
from that page (no in-process `run_study`; two-step confirm on the **pinned**
hash; pin both dataset path keys; exclusive pid claim; not a job queue);
combinatorial fishing mitigated by confirm gates, stage-first examples
(40 vs 800), and multiple-testing honesty.

## Study Builder (SB0–SB3) ✅ Complete

Additive Studies **Build** tab that compiles a closed `StudyDraft` into
`schema_version: 1` YAML and applies it to the existing Preview textarea.
Inspect, Preview, CLI spawn, expand, execute, promote, and report stay
behavior-identical. Not a Setup Builder clone; not an NL compiler.

**Canonical spec:** `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| SB0 | Plan lock + docs index ✅ |
| SB1 | Pure `StudyDraft` emit / hydrate compiler (no UI) ✅ |
| SB2 | Build tab P0 + live strip + Apply to Preview ✅ |
| SB3 | Stage / report / hydrate / download + docs closeout ✅ |

**Regression posture:** no `engine/` edits; no StudySpec / expand / launch /
execute behavior change; no golden regeneration; Studies-scoped session keys
only; USER_GUIDE extends H2 `Studies viewer (read-only)` (no new H2). Parked
RS-D1 / D3 / D6 stay parked.

## Study Ingest Alignment (SIA0–SIA3) ✅

Studies authoring drifted from the Data-page recommended ingest
(`15s_primary_derive_1m` + attached 15s R12 source). SIA makes **new**
StudySpecs emit that existing `run_experiment` contract. Omitted
`ingestion_mode` remains `primary`. Not a second engine; not a page robot.

**Canonical spec:** `docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| SIA0 | Plan lock + docs index |
| SIA1 | Builder field / new-draft defaults / emit-hydrate / warnings / schema token |
| SIA2 | Build tab ingest radio (no auto-rewrite of profile/intrabar) |
| SIA3 | pdPOC teaching example + docs + vendor-15s parity test |

**Regression posture:** no `engine/` / `derive.py` / `api.py` loader edits; no
classic Data/Backtest edits; no expand/execute/launch behavior change; no
golden regeneration; legacy YAML that omits `ingestion_mode` stays `primary`.
Parked: copy-from-session; Data/API loader dedup; API omitted-mode default
change.

Post-SIA: `default_study_draft()` ingest identity is MNQ + UTC +
`data/mnq_15s.csv` (AMP/Rithmic HE). `StudyDraft()` field defaults stay
legacy-safe. Operator template: `examples/studies/pRTH_open_ma.yaml`.

## Study Viewer (SV0–SV5) ✅ SV5 shipped

Inspect today is catalog + path-paste + tables + quality panes + overview
charts + cell peek + trader briefing (`report_study(..., write_artifacts=False)`).
SV1 lists local study dirs and reuses the existing Load path. SV2 projects
failed-cell errors, group summaries, optional rollup files, and a launch-log
tail. SV3 plots already-loaded ranked / group frames (page-only Plotly). SV4
peeks one cell’s index + ledger error + optional `trade_summary.json` on that
**same** Studies page. **SV5** adds a deterministic briefing (highest
primary-metric cell + settings + best SL/TP + NY RTH bucket) and projects
one-cell `grid_results.parquet` / `trades.parquet` ToD — still no second
runner or classic `st.session_state` mutation.

**Canonical spec:** `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| SV0 | Plan lock + docs index ✅ |
| SV1 | Local catalog (`results/studies/` + `out/`, one level) + click-to-load + `study list` ✅ (sandboxed `--root` per plan §4.9; `viewer.py` must not import `cli_study` / `thesistester.cli` / `execute`) |
| SV2 | Failed-cell errors + `group_summaries` + read-only rollup files if present + launch-log tail ✅ |
| SV3 | Locked Plotly set from already-loaded ranked / group frames ✅ |
| SV4 | Cell peek (`trade_summary.json` + index + ledger error); no Bundles hydrate ✅ |
| SV5 | Trader briefing + ranked `best_grid_*` + peek SL/TP grid / NY RTH ToD ✅ |

**Regression posture:** no `engine/` edits; no golden regeneration; no
`report_study` write on Inspect; do **not** call `rollup_study()` (it writes);
no `apply_research_bundle_to_session`; Studies-scoped session keys only;
USER_GUIDE extends H2 `Studies viewer (read-only)` (no new H2). Parked
RS-D1 / D3 / D6 stay parked. RS-D2/D8/D9/SB/SIA behavior stays identical
except additive Inspect panes and additive `study list`.

## Study Observatory (SO0–SO9) — SO9 shipped; SO5/SO6 parked

Corpus-level read-only investigation of every local study cell (facets,
comparability cohort, n×E scatter, optional Program B lens, saved desks,
studies pane, readable cohort labels, lens-as-filter). Inspect stays the
one-study microscope. Discover reuses SV1
`discover_study_dirs`. Do **not** call `report_study` per study, unzip-all,
or write `results/studies/`. Do **not** unpark SO5/SO6.

**Canonical spec:** `docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| SO0 | Plan lock + docs index ✅ |
| SO1 | Fact table + mtime cache + `study observatory` CLI ✅ |
| SO2 | `pages/16_Study_Observatory.py` + USER_GUIDE H2 + HC allowlist ✅ |
| SO3 | Program B lens (desk_class, ΔE vs `w0_solo` / `w0_va`, heatmap) ✅ |
| SO4 | Saved desks under store `study_observatory/` ✅ |
| SO5 | Parked — opt-in corpus-strip watch |
| SO6 | Parked — grounded Discuss over the filtered frame |
| SO7 | Corpus studies pane (ledger strip + catalog-dir table + study drill) ✅ |
| SO8.0 | Plan lock for SO8/SO9 ✅ |
| SO8 | Cohort literacy (display labels; raw `cohort_key` unchanged) ✅ |
| SO9 | Lens as filter (`desk_class` / `useful_confluence` + heatmap focus) ✅ |

**Regression posture:** no `engine/` edits; no golden regeneration; no
`report_study` write; no `rollup_study()`; no `apply_research_bundle_to_session`;
Observatory-scoped keys + existing Studies drill keys only; `viewer.py` must
not import `observatory`. Parked RS-D1 / D3 / D6 stay parked.

## Audit Honesty (AH0–AH6) — AH0–AH6

Research-honesty remediations from the 2026-08-18 audit merge. The engine
happy path stays causal; identity / flatten / restore / one headless
eligibility hole do not. Implement **one PR per finding family**. Do not
collapse the two composers, flip omitted-key defaults, or regen goldens
(except AH5 hard-stop).

**Canonical spec:** `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| AH0 | Plan lock + docs index ✅ |
| AH1 | Per-candidate flatten `entry_local_ts`; `empty_session_close_cap` skip ✅ |
| AH2 | Pin Study dataset paths at expand; promote/launch search spec parent first ✅ |
| AH3 | Prefix-slice OTF-matrix train prices (`otf_validation.py` only) ✅ |
| AH4 | Manage leftover bundle session keys; no dataset-less bootstrap refill ✅ |
| AH5 | `sl_first` honors 3c entry activation (golden-stop if legacy trades move) ✅ |
| AH6 | Reject `BASE_COLUMNS` in `validate_setup_config` ✅ |

**Regression posture:** §4 golden families stay identity-only. Probe tests
must fail on `main` before each fix. Help-corpus paths frozen. Parked:
composer forks, API `enabled` default flip, page-12 hash, ETH-as-CME flatten,
`allow_all` default change. Do not reopen RS/SB/SIA/SV/SW contracts except
the landed AH2 path-pin / AGENT_GUIDE replay honesty.

## Study Admit Follow-up (SAF0–SAF3) — SAF1–SAF3 shipped

After an all-day study, SV5 names the strongest NY RTH segment on the
crowned cell (post-hoc). SAF drafts a **child** StudySpec that re-sims that
cell with Admit locked — `constants.backtest.entry_window` and
`constants.grid.entry_window` (the engine path). Optional `study.lineage`
links parent → child. `study promote` without `--admit-tod` stays RS5.
Promote still never executes. Time-of-day stays off the factor cartesian.

**Canonical spec:** `docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| SAF0 | Plan lock + docs index ✅ |
| SAF1 | CLI `--admit-tod auto` + lineage + engine-correct window stamp ✅ |
| SAF2 | Inspect **Draft Admit follow-up** → Preview (no spawn) ✅ |
| SAF3 | `--tod-group` hour/30min + `--allow-thin` + catalog parent column (this PR) |
| SAF4 | Parked: one-click child launch |

**Regression posture:** no `engine/` edits; no golden regeneration; default
promote identical; no `run_study` from promote/Inspect button; no new
USER_GUIDE H2. Parked RS-D1 / D3 / D6 stay parked.

## Level Catalog Contract (LC0–LC4) — LC4 landed

Prior-profile VAH/VAL/POC twins are already computed; LC1 admits all nine as
StudySpec tokens (was `pdPOC` only). LC2 aligns pivot tokens to engine
columns (`Pivot_1m_*` / `5m` / `30m` / `4h`). LC3 makes suggested Setup
defaults and Assistant omitted-key options a subset of
`closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` (`VWAP_rolling_30min` /
`4h`; widget catalogs stay widget-only). LC4 fail-closes API
`generate_signals` / `run_experiment` / study cells when global-cluster
`selected_levels` are absent from the frame (same `ValueError` as
anchor-rules). The confluence library stays permissive. Do not rename
engine columns, emit new families, flip `compute_all_levels` defaults,
or bump `LEVEL_ENGINE_VERSION`.

**Canonical spec:** `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| LC0 | Plan lock + docs index ✅ |
| LC1 | Shared static catalog + admit `pd/pw/pm` VAH/VAL/POC twins ✅ |
| LC2 | Pivot tokens = `Pivot_1m_*` / `Pivot_5m_*` / `Pivot_30m_*` / `Pivot_4h_*` ✅ |
| LC3 | Suggested/Assistant catalogs ⊆ default `closed_level_token_set` ✅ |
| LC4 | API global-cluster missing-column fail-closed (library unchanged) ✅ |

**Regression posture:** no level-value edits; no golden regeneration; no
`LEVEL_ENGINE_VERSION` bump. Parked: developing H/L/VA, rolling VAH/VAL, IB,
`15min` MAs, adding `1h` to default `vwap_windows`, pivot `1min` aliases.

## Developing week/month VWAP (WMV0–WMV2) — series complete

Add developing `wVWAP` / `mVWAP` as within-week / within-month siblings of
`dVWAP`. Same `session_vwap_enabled` gate; same `W-SUN` / `M` keys as
`wOpen` / `mOpen`. Setup Builder and StudySpec must admit the tokens
(static catalog via `SESSION_VWAP_COLUMNS`). Do not add prior-week/month
VWAP, RTH-only HTF VWAPs, new settings keys, or `SUGGESTED_DEFAULT_LEVELS`
edits.

**Canonical spec:** `docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| WMV0 | Plan lock + docs index ✅ |
| WMV1 | Engine emit + `LEVEL_ENGINE_VERSION` 10 + Setup/Study token tests + living engine docs ✅ |
| WMV2 | Levels/Assistant/Help copy + thesis-compiler hint ✅ |

**Regression posture:** additive columns only when the existing session-VWAP
gate is on; `dVWAP*` value-identical; `compute_all_levels` default remains
off; no golden regeneration; no new `st.session_state` keys. Parked:
`pwVWAP` / `pmVWAP`, `wVWAP_RTH` / `mVWAP_RTH`, period-key extraction.

## Anchor-only (`min_valid=0`) (AO0–AO1) — AO1 implemented

Allow `anchor_rules` with no partners so a named location can be traded
alone. Opt-in: default `min_valid` stays 1; empty rules + that default
still emit no zones. Point zone `[P, P]` at the live anchor; do not apply
`tolerance_ticks` as a halo. Study `[[]]` is legal only for exclusive
`anchor_rules` + explicit `min_valid: 0`. Global cluster / fills /
pipeline composition stay frozen.

**Canonical spec:** `docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| AO0 | Plan lock + docs index (this PR) |
| AO1 | Detector empty-rules / `min_valid` floor + setup/API/study gates + Setup/Signals/Study Builder + tests + living docs |

**Regression posture:** defaults unchanged; `test_empty_rules_returns_empty_schema`
stays; omitted `min_valid` resolves to 1; no golden regen; no
`LEVEL_ENGINE_VERSION`; no desk L1/L2 rewrite. Parked: anchor ± N-tick
band, `pwVWAP`/`pmVWAP`, Study emit of 1-level `global_cluster`.

## Tick VAP (TV0–TV4) — series complete

Prior-profile `pdVAH` / `pdVAL` / `pdPOC` (and `pw*` / `pm*` VA) become
Quantower tick Last×Volume VAP. 15s stays the OHLC / study clock. Ticks
are ingest-only for those nine columns. No ticks → columns absent →
named-VA generate refuses / cells `failed`. Product day aggregation
becomes 1-tick in TV3 so POC is the same grid Accumu fades. Do not
retick `dVWAP`, OR, ONH, touch, 3c, or R12. Do not keep 1m typical under
the same token names.

**Canonical spec:** `docs/TICK_VAP_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| TV0 | Plan lock + docs index ✅ |
| TV1 | Quantower tick-last loader + monthly combine + session-chunk (no emission change) ✅ |
| TV2 | `PriorProfileTable` from ticks; reuse `_compute_profile`; parquet persist (no cutover) ✅ |
| TV3 | Identity cutover: tick VAP as `pd*`/`pw*`/`pm*`; omit without ticks; fail-closed; day bin 4→1; `LEVEL_ENGINE_VERSION` 11 ✅ |
| TV4 | Data / Study Builder `tick_paths` + Help honesty ✅ |

**Regression posture:** loader/table additive in TV1–TV2; TV3 is a versioned
VA identity change (goldens untouched — `run_legacy_pipeline` never calls
`compute_all_levels`); `dVWAP*` / session marks / rolling POC / APOC
value-identical; farm studies that do not name VA tokens stay 15s-only.
TV3 must migrate stand-in `pdPOC` study fixtures and add `tick_paths` on
`examples/studies/pdPOC_ma_confluence_battery.yaml` (that example *is*
named-VA). Product day key is `prior_day_profile_aggregation_ticks`;
`compute_all_levels` kwargs stay `prior_*_aggregation_ticks`.
Parked: `typical_mvp` same-name alias, developing `dVAH`, APOC/rolling-POC
VAP, tick VWAP, bid/ask VAP.

## A-Period POC Quantower parity (AP0–AP3) — AP1 implemented, evidence pending

The desk observed a mismatch between Quantower A-period POC and ThesisTester's
one-minute typical-price APOC. Current code confirms the ThesisTester
approximation, but the repository has no 2026-09-04 MNQ source fixture or
Quantower APOC oracle. AP0 therefore locks evidence collection and candidate
discrimination before any production-math change. Do not infer Quantower's
algorithm from one matching bar-range reconstruction.

**Canonical spec:** `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md`

| Milestone | Intent |
|---|---|
| AP0 | Evidence contract, candidate-selection gate, and scoped PR sequence ✅ |
| AP1 | Pure candidate comparator and optional desk-oracle test; no production output change ✅ |
| AP2 | Implement one AP1-selected, versioned APOC source with PIT and failure-to-NaN contracts |
| AP3 | Stamp Program B Wave 7 APOC provenance; do not rewrite historical results |

**Regression posture:** preserve the disabled APOC no-op, A-period/RTH/ETH
availability, pAPOC freeze, and unrelated level families. Goldens remain
unchanged. A product-default source change requires identity/cache versioning;
missing selected-source inputs must not silently emit legacy typical APOC.

## Trade Journal (TJ0–TJ7) — TJ0 locked

Post-trade ingest of discretionary fills so the desk can measure realized
outcomes against AMP money truth and (later) a named systematic cell.
R21-shaped: new `thesistester/journal/` package; no `simulate_trades` /
signals / levels edits; no golden regen; desk PDFs/CSV stay out of git.

**Canonical spec:** `docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md`

| Milestone | Intent |
|---|---|
| TJ0 | Plan lock + desk-file evidence + contracts (this PR) |
| TJ1 | Quantower Trades CSV → `FillRecord` (`quantower_trades`, NY timestamps) |
| TJ2 | AMP Daily Statement PDF → `AmpStatement` (layout Buy/Sell + fees) |
| TJ3 | Qty-aware FIFO on `Position ID` → `JournalTrade` (default 10-tick R) |
| TJ4 | Daily recon (multiset + P&S + fees); fail-closed if not `reconciled` |
| TJ5 | Join to 15s/1m clock; MAE/MFE only when `bars_held ≥ 1` |
| TJ6 | Named-cell counterfactual match (`executed_cell` / `near_level` / …) |
| TJ7 | Report + page 17 Journal (read-only; USER_GUIDE H2 + HC allowlist) |

**Regression posture:** additive package only. QT `Fee`/`Gross P/L` are unused
(always 0 in the desk export). AMP is the fee SoT. Journal expectancy does
not re-rank studies. PII fixtures are redacted.

## Studies Inspect ledger progress (additive)

Inspect shows `done/total` + current `running` cell names from the loaded
ledger (`summarize_ledger_progress` in `thesistester/study/viewer.py`).
Refresh remains explicit. Ledger-only fallback when `results_index.csv` is
absent (not when a present index is unreadable). Not a job queue; no
auto-refresh; no engine / golden / schema change.
