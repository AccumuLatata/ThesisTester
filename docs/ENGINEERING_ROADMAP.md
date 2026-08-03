# Engineering Roadmap

This document tracks the ThesisTester engineering roadmap milestones in established
phase order.

The proposed AI Research Assistant has a separate, regression-safe implementation
plan in `docs/AI_RESEARCH_ASSISTANT_ROADMAP.md`. Its AIA-series milestones are
additive to this R-series and must follow its stated regression gates.

Classic workspace ↔ Assistant unification follows
`docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md` (CAI-series). CAI milestones are
also additive and must preserve engine/golden-master semantics.

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
- Recording policy default remains `manual` (CAI-0); `all_executions` deferred
  to CAI-7.

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
- Idempotent by `canonical_bundle_hash` (`force_new` opt-in for a new record);
  reuse picks a readable stored provenance bundle (skips stale matches) and
  classic recording deletes orphan UUID zips after reuse.
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
