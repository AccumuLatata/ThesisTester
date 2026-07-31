# AGENT GUIDE

## Purpose
Regression-safe onboarding guide for contributors/agents working in ThesisTester.

## Fast start
1. Install deps: `pip install -r requirements.txt` (`README.md:7-10`).
2. Run tests: `pytest -q` (`README.md:12-16`).
3. Optional app run: `streamlit run app.py` (`README.md:7-10`).

## Headless and agent operation (R18)

Use `thesistester.api` for one in-process research pipeline or the versioned YAML
runner for independent batches:

```bash
python -m thesistester run experiment.yaml --workers 4
```

The API handoffs are typed but intentionally remain plain `pandas.DataFrame` /
`dict` values:

1. `load_dataset(...) -> DataFrame` returns validated, exchange-timezone,
   session-tagged OHLCV.
2. `compute_levels(...) -> LevelsResult` returns `levels`, `session_levels`,
   and canonical `levels_settings`.
3. `build_setup(...) -> dict` applies the Setup Builder normalization and
   validation contract.
4. `generate_signals(...) -> SignalsResult` returns zones, naked flags,
   signals, and deterministic settings identity.
5. `run_backtest(...) -> BacktestResult` and `run_grid(...) -> GridResult`
   apply the shared OTF filter before the unchanged engine functions.
6. `run_validation(...) -> ValidationResult` runs seeded Phase 8 diagnostics
   plus explicitly enabled R10/R11 batteries.
7. `run_experiment(...) -> dict` returns a bundle-ready mapping with the same
   research keys used by the Streamlit workflow.

Experiment files require `schema_version: 1`, a non-empty `runs` list, and
unique filesystem-safe run names. Dataset paths are resolved relative to the
YAML file. Each run writes `<name>.research.zip`; `results_index.csv` records
the canonical bundle hash and key metrics. `--workers N` uses isolated spawned
processes across runs only. Each individual levels/signals/backtest/grid/
validation pipeline stays single-threaded, and output order follows YAML order.
R12 adds optional `dataset.subtimeframe_path`; it is required when an enabled
backtest/grid section selects `intrabar_model: subtimeframe`.

Minimal complete shape:

```yaml
schema_version: 1
output_dir: results
workers: 2
runs:
  - name: es_touch_baseline
    dataset:
      path: data/es_1m.csv
      instrument: ES
      source_timezone: America/New_York
    levels:
      opening_range_minutes: 30
    setup:
      name: ES touch
      description: RTH open confluence
      instrument: ES
      selected_levels: [dOpen, RTH_Open]
      tolerance_ticks: 0
      min_confluences: 2
      max_confluences: 2
      naked_only: false
      naked_requirement: any
      trigger: touch
      trigger_timeframe: base
      direction: both
      confluence_mode: global_cluster
      anchor_level: null
      confluence_rules: []
      min_valid_confluences: 1
      trigger_params: {}
      otf_filter: null
    backtest:
      stop_loss_ticks: 8
      take_profit_ticks: 16
      exposure_policy: single_position
    grid:
      stop_loss_ticks_values: [4, 8, 12]
      take_profit_ticks_values: [8, 16, 24]
      ranking_metric: expectancy_r
      min_trades: 30
    validation:
      n_bootstrap: 2000
      n_permutations: 5000
      random_state: 42
      excursion:
        enabled: true
        min_trades: 10
      monte_carlo:
        enabled: true
        n_simulations: 2000
        random_state: 42
```

Agent safety requirements:

- Treat YAML and API arguments as research specifications, not permission to
  alter engine behavior. Unknown facade configuration keys fail closed.
- Preserve explicit `random_state` values. Never compare raw ZIP bytes:
  `canonical_bundle_hash()` removes archive/manifest time metadata and hashes
  logical DataFrame contents.
- Point-in-time guarantees are bounded by
  `docs/POINT_IN_TIME_GUARANTEES.md`. The facade adds no causality guarantee:
  confluence inherits the causality of supplied level columns, same-bar
  close/volume assumptions still apply, and externally supplied non-causal
  data remains non-causal.
- Do not select parameters using the final test sample and then describe that
  sample as out-of-sample. Batch scale increases multiple-testing risk; use
  walk-forward/OOS and robustness diagnostics, and retain all attempted runs.
- Outputs are research-screening diagnostics, not proof of edge or executable
  trading advice. Existing intrabar, execution-cost, roll, and serial-
  dependence limitations remain unchanged.

## Development environment (R9)
- Editable install with tooling: `pip install -e ".[dev]"` (packaging metadata and pinned
  tool config live in `pyproject.toml`).
- Before pushing, run exactly what CI runs:
  1. `ruff check .`
  2. `ruff format --check .`
  3. `pytest -q`
- Lint scope is deliberately narrow (`E4`, `E7`, `E9`, `F`, `W` at line length 100) and applies
  to Python only — Markdown is excluded so documentation snippets are never rewritten by the
  formatter. Widening the rule set is a separate, reviewable PR — never a side effect of
  feature work.
- `ruff` is version-capped in the `dev` extra so formatting decisions cannot change under CI
  without an explicit bump.

## Regression-safety gates in CI
`.github/workflows/ci.yml` runs on every push to `main` and every pull request:

| Job | Gate |
|---|---|
| `ruff (lint + format)` | `ruff check` + `ruff format --check`; blocking |
| `pytest (py3.10/3.11/3.12)` | full suite per matrix cell; blocking. Coverage is reported and warns below an informational floor, never blocks |
| `editable install (no dev extras)` | `pip install -e .` + import + `pip check` in a clean venv; blocking |
| `golden-master regeneration guard` | blocks any PR that changes `tests/fixtures/golden/**` without the `GOLDEN_REGEN` label |

## Golden-master policy (engine/analytics work)
- Read `tests/fixtures/golden/README.md` before touching `simulate_trades`, level
  computation, or signal generation. It is the operational spec for
  `docs/ENGINEERING_PROPOSAL.md` §4.1.
- The gate is active. Run `pytest -q tests/test_golden_master.py` before and
  after engine edits. It rebuilds the deterministic NQ fixture and compares
  exact legacy trade values; the bundle hash is additionally checked on its
  recorded pandas major.
- Legacy-mode outputs are the contract: new behavior ships behind a default-off flag, so
  goldens must stay valid. Never regenerate a golden to make a diff go away.
- Golden regeneration is its own PR with a readable CSV diff, justification, and the
  `GOLDEN_REGEN` label. The only write command is
  `python -m tests.fixtures.golden.record_golden --confirm-regenerate`.

## R12 intrabar research safety

- Never change the `sl_first` default or its legacy trade schema without a
  separate approved golden-regeneration decision.
- Treat `path_open_proximity` as sensitivity analysis, not recovered event
  order. Do not choose it because it produces the best result.
- `subtimeframe` must fail closed on missing, duplicate, unsorted, non-dividing,
  or parent-OHLC-inconsistent lower rows. Never interpolate or silently fall
  back to an OHLC heuristic.
- Keep one intrabar model fixed across every grid cell and walk-forward fold.
- For R18 batches, supply observed lower data through
  `dataset.subtimeframe_path` and retain the bundle's policy/diagnostic fields.
- Run `pytest -q tests/test_golden_master.py tests/test_intrabar.py` after any
  execution-path edit.

## R13 exit-management research safety

- Break-even/trailing defaults must remain `None`; legacy goldens must stay
  unchanged.
- Treat BE/trailing as strategy parameters, not evidence of better fills.
  Grid/WFO sweeps must preserve the selected values explicitly in exported
  policy snapshots.
- Stop movement is completed-bar and active on the next parent bar. Do not
  introduce same-bar arming without a separate proposal and new ambiguity tests.
- Keep `stop_price` as the initial bracket stop and keep R-multiple/MAE/MFE
  semantics based on initial risk.
- Run `pytest -q tests/test_golden_master.py tests/test_exit_management.py tests/test_intrabar.py`
  after any BE/trailing or intrabar interaction edit.

## R14 walk-forward research safety

- Keep `fold_mode="bars"` and `window_mode="rolling"` as backward-compatible
  defaults.
- Session folds use observed ETH-boundary trading dates. Do not claim an
  exchange holiday calendar or complete-session certification without a
  schedule source.
- Assign session-fold signals by executable entry bar, not formation bar.
- Never stitch overlapping OOS windows without explicit `first`/`last`
  ownership; default `reject` is the safe policy.
- Do not select the best WFA matrix cell using its OOS performance and then
  report that same result as unbiased.
- Run `pytest -q tests/test_walk_forward.py tests/test_otf_integration.py`
  after any fold, session, or matrix change.

## R15 overfitting research safety

- Keep R15 opt-in and retain `validation_summary()` unchanged.
- Treat PBO/DSR/vs-random as diagnostics of declared historical trials/nulls,
  never as proof of a durable edge.
- Use explicit `random_state`; do not replace local seeded RNG with global
  sampling.
- Preserve grid-cell execution assumptions when re-simulating sequences or
  random schedules.
- Run `pytest -q tests/test_overfitting.py tests/test_phase8_validation.py`
  after changing R15 statistics or validation integration.

## R16 noise-test research safety

- Keep R16 opt-in and retain `validation_summary()` unchanged.
- Perturb only a copied OHLC frame and assert high/low consistency for every
  replica; never mutate uploaded/canonical data.
- Re-run the canonical levels → signals → OTF → backtest path rather than
  approximating a noisy trade sequence.
- Use explicit local seeded RNG and preserve the noise scale, seed, matching
  rule, and subtimeframe policy in the exported config.
- Do not synthesize lower-timeframe data; document pinned lower-timeframe
  replay as a limitation.
- Run `pytest -q tests/test_noise.py tests/test_api.py tests/test_golden_master.py`
  after R16 changes.

## R17 ingestion research safety

- Keep `dataset.format_profile` explicit in API/CLI specifications; canonical
  remains the default and no format auto-detection is permitted.
- Preserve captured raw rows only as provenance; use canonical one-minute bars
  for current engine work and do not treat raw ticks as R12 subtimeframe data.
- Confirm the canonical sample CSV remains byte-identical after loader edits.
- Run `pytest -q tests/test_loader.py tests/test_vendor_loaders.py tests/test_local_store.py`
  after R17 changes.

## Repository conventions (verified)
- Multipage Streamlit workflow with phase pages under `pages/` (`app.py:10-33`).
- Core outputs are passed through `st.session_state` between phases (see `docs/ARCHITECTURE.md`).
- Validation and reporting are explicitly diagnostic/research-only, not proof of edge (`thesistester/analytics/validation.py:13`, `pages/10_Validation.py:18`, `thesistester/reporting.py:13-19`).
- Backtest intrabar ambiguity uses SL-first pessimistic behavior (`thesistester/engine/backtest.py:12-14`, `221-226`).

## Regression-safe rules
- Prefer minimal, surgical changes.
- Preserve phase-to-phase `st.session_state` contracts.
- Do not change assumptions silently; if changed, update docs and references in the same PR.
- Re-run `pytest -q` after edits and report results.
- For docs-only tasks, keep edits to Markdown files and avoid `.py` changes.

## Where each phase lives
- **Phase 1 (Data):** `pages/1_Data.py`, data loaders/validators in `thesistester/data/`.
- **Phase 2/3 (Levels):** `pages/5_Levels.py`, level engines in `thesistester/levels.py`.
- **Phase 6.5 (Setup Builder):** `pages/2_Setup_Builder.py`, setup helpers in `thesistester/setup.py`.
- **Phase 4 (Signals):** `pages/6_Signals.py`, signal/confluence functions in `thesistester/engine/`.
- **Phase 5 (Backtest):** `pages/7_Backtest.py`, simulator in `thesistester/engine/backtest.py`, metrics in `thesistester/analytics/metrics.py`.
- **Phase 6 (Grid):** `pages/8_Grid_Search.py`, grid analytics in `thesistester/analytics/grid.py`.
- **Phase 7 (Time):** `pages/9_Time_Analysis.py`, helpers in `thesistester/analytics/time_analysis.py`.
- **Phase 8 (Validation):** `pages/10_Validation.py`, diagnostics in `thesistester/analytics/validation.py`.
- **Phase 9 (Report/Export):** `pages/11_Report_Export.py`, artifact builders in `thesistester/reporting.py`.
