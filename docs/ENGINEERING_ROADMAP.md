# Engineering Roadmap

This document tracks the ThesisTester engineering roadmap milestones in established
phase order.

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
  *data* lands in a dedicated follow-up PR before R12.
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
