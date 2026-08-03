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
For interactive Streamlit research, the Data page can:
1. load a one-minute primary CSV and optionally attach a lower-timeframe CSV; or
2. select the explicit `15s_primary_derive_1m` ingestion mode (Quantower History
   Exporter) to derive complete one-minute canonical bars from a single
   15-second upload and attach that 15-second source as `subtimeframe_data`.

Both interactive lower-data paths are session-scoped producers of the same
`subtimeframe_data` contract today; YAML `dataset.subtimeframe_path` remains
the reproducible headless contract until a later persistence/RunSpec PR.

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

## AI Research Assistant contracts (AIA-0)

`thesistester.assistant` is an additive, non-executing contract layer for the
proposed local AI Research Assistant. `FEATURE_PARITY_REGISTRY` is the source of
truth for the assistant's present product coverage. Every request must first
parse as an `AssistantRequest`, then pass `validate_capability_request()`.

- Unknown request keys and unknown capability IDs fail closed.
- Capability IDs classified as `unsupported` cannot be executed; their
  registry limitation must be surfaced to the user.
- Registry metadata does not grant arbitrary code, shell, or filesystem access.
  Future tools may invoke only their declared public headless symbols.
- Compute-capable rows require the registry's stated confirmation level and
  resource envelope. A confirmed RunSpec is recompiled and validated through
  `validate_run_spec()` at confirmation and again immediately before execution.
- The canonical compiler accepts only executable API sections (`dataset`,
  `levels`, `setup`, `backtest`, optional `grid`, `validation`, and
  `walk_forward`). Do not add prose-only fields such as trend rules or success
  criteria to executable drafts; represent a requirement with a supported
  structured control or leave it as an explicit clarification.
- Route assistant compute only through `AssistantOrchestrator` façade methods
  (`for_local_workspace()`, `dispatch()`, `execute_confirmed_run()`,
  `cancel_run()`, validate/confirm/explain/compare/export/portfolio/handoff).
  The Research Assistant page must remain presentation-only. Every
  non-unsupported registry capability must have a `HANDLER_REGISTRY` entry;
  otherwise mark it `unsupported` with a limitation. Structured errors must
  include `category`, `retryable`, and `remediation`. Apply controls stage
  session draft only and must flash via `assistant_flash`; Confirm lives under
  Plan review after Validate; Run lives on a `confirmed` specification version.
- Completed runs require a readable on-disk research bundle whose
  `canonical_bundle_hash` matches reported provenance before `complete_run`.
  Provenance-gated explanation, comparison, export, and portfolio paths must
  fail closed on hash mismatch. Keep API/CLI/assistant parity coverage in
  `tests/test_assistant_execution_parity.py` and workspace/page-contract
  coverage in `tests/test_assistant_workspace.py` green when touching
  lifecycle, bundle tools, or the Research Assistant page.
- Assistant narratives must stay evidence-backed: extend
  `thesistester/assistant/explainer.py` templates rather than free-text UI
  claims. Every numeric claim needs a packet path; missing evidence becomes a
  limitation. “Best”/“better” language must state metric, candidate set, sample,
  costs, and OOS status. Keep `tests/test_assistant_explainer.py` and
  `tests/test_assistant_comparison.py` green when changing explanation or
  comparison contracts.
- Optional LLM paraphrase (`llm_explainer.explain_packet_with_llm`) is
  evidence-only: structured claims with packet paths, server-resolved values,
  and rejection of uncited numbers (`LLMEvidenceError`) before render. Chat
  (`handle_chat_turn`) drafts non-executing choices only—never `dispatch` or
  `execute_confirmed_run`. Keep `tests/test_assistant_llm_evaluations.py` and
  `tests/test_assistant_registry_audit.py` green when changing the provider
  boundary or registry audit.
- Provider setup: non-secret settings in `config/assistant.toml`; secret via
  rotated `OPENAI_API_KEY` (env first, then Streamlit Secrets
  `OPENAI_API_KEY` / nested `[openai].api_key`). Reject the placeholder
  `REPLACE_WITH_ROTATED_OPENAI_API_KEY`. Recovery/cancellation stays on
  orchestrator `cancel_run` / confirmation lifecycle, not the LLM.
- Document every additive `assistant_*` session key in `ARCHITECTURE.md` and
  `ASSISTANT_SESSION_KEYS`. Thesis switches must clear
  `THESIS_SCOPED_STAGING_KEYS` (including `assistant_bundle_handoff`).

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
- `subtimeframe_conservative` is the only permitted partial-data policy: it
  must preserve strict replay for valid groups, apply SL-first only to recorded
  incomplete/misaligned groups, and reject invalid OHLC or reconciliation
  mismatches. Never describe it as full observed replay.
- Keep one intrabar model fixed across every grid cell and walk-forward fold.
- For R18 batches, supply observed lower data through
  `dataset.subtimeframe_path` and retain the bundle's policy/diagnostic fields.
- Select `quantower_history_exporter` explicitly for semicolon-delimited
  Quantower History Exporter files. `dataset.subtimeframe_format_profile`
  defaults to `canonical`; it never inherits the parent profile.
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

## WFO OTF history policy

When OTF is enabled in walk-forward:

- Default `otf_history_policy=fold_local` (legacy-preserving).
- Opt-in `causal_prefix` allows prior bars before each fold start to establish
  OTF state; only fold-local signals are scored; never use future bars.
- Missing policy must resolve to `fold_local`; invalid values must raise on
  API / compiler / UI boundaries (never silently coerce).
- Record the effective policy on WFO config, summary, fold rows, and
  `walk_forward_otf_filter` metadata.

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
- `dataset.subtimeframe_path` is always canonical OHLCV for R12 replay; it
  never inherits the primary dataset's vendor `format_profile`.
- Preserve captured raw rows only as provenance; use canonical one-minute bars
  for current engine work and do not treat raw ticks as R12 subtimeframe data.
- Confirm the canonical sample CSV remains byte-identical after loader edits.
- Run `pytest -q tests/test_loader.py tests/test_vendor_loaders.py tests/test_local_store.py`
  after R17 changes.

## R19 parameter-sensitivity research safety

- Keep R19 opt-in and retain `validation_summary()` unchanged.
- Re-simulate only a selected grid cell with fixed signals and fixed execution
  assumptions; do not turn R19 into a level/signal optimizer.
- Preserve deterministic step ordering, the tick-rounding policy, and the
  configured perturbation range in exported config.
- Describe OAT sign-flip fragility as a local diagnostic, distinct from R11
  sampling uncertainty, R15 trial-selection risk, and R16 input robustness.
- Run `pytest -q tests/test_sensitivity.py tests/test_api.py tests/test_golden_master.py`
  after R19 changes.

## R20 trade-review visualization safety

- Keep R20 read-only: it may consume existing OHLC/trade/level/zone frames but
  must not modify execution, metrics, signal generation, or research bundles.
- Bound every selected-trade and batch-export payload to the hold interval plus
  an explicit capped row buffer; never add a full-dataset review mode.
- Describe MAE/MFE bands as terminal parent-bar envelopes, not intrabar replay
  or proof of fill ordering. Preserve initial-stop semantics; final-stop
  display is explicitly optional.
- Run `pytest -q tests/visualization/test_trade_review_chart.py tests/test_backtest_chart.py tests/test_golden_master.py`
  after R20 changes.

## R21 portfolio research safety

- Keep R21 post-trade and additive: never route a portfolio policy into
  `simulate_trades` or change single-setup execution semantics.
- Require compatible completed-trade schema and shared parent bar-index bounds;
  treat the portfolio admission policy as a deterministic approximation.
- Keep correlation and leave-one-out contribution framing diagnostic, not
  allocation or future-risk proof.
- Run `pytest -q tests/test_portfolio.py tests/test_api.py tests/test_research_bundle.py tests/test_golden_master.py`
  after R21 changes.

## R22 simulation performance safety

- Treat `docs/SIMULATE_PERF.md` as the informational serial baseline; do not
  claim a speedup without rerunning its exact benchmark scenarios.
- Keep all public `simulate_trades` behavior unchanged through core refactors.
  Any accelerated path must be opt-in and exactly equal to serial golden and
  feature-path outputs.
- Keep optimization work inside `engine.sim_core`; admission, P&L, trade
  schema, and diagnostics remain orchestrated by `backtest.py`.
- Run `pytest -q tests/benchmarks/test_simulate_baseline.py tests/test_golden_master.py tests/test_intrabar.py tests/test_exit_management.py tests/test_phase5_backtest.py`
  after R22 changes.

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
