# Research Study Runner — Implementation Plan (RS)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-11 (amended 2026-08-11: R18 contract review)  
**Status:** Plan-locked (RS0) — implementation not started  
**Series code:** **RS** (Research Study Runner)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Related living docs:** `docs/AGENT_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/otf-filter.md`  
**Related but separate:** `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` (within-trade level membership — **not** cross-setup factorial studies; do not merge concepts)  
**Depends on (already shipped):** R18 headless API + batch CLI (`thesistester/api.py`, `thesistester/cli.py`), RunSpec validation, research bundles, `results_index.csv`

**Supersedes:** conversational design notes about an autonomous research bot / Grok Bot coworker (those remain usage patterns; this plan is the product contract).

---

## 1. Purpose

Ship an **additive, headless Research Study Runner** so a researcher (or an external agent such as Grok Bot) can:

1. Declare a **closed multi-factor study** (e.g. pdPOC × MA partners × confluence modes × entries × OTF).
2. **Expand** that study into a deterministic R18 experiment YAML.
3. **Execute** unattended via existing `run_experiment` / bundle machinery (study-owned loop; see §5.3).
4. **Aggregate** results into an honest overview (ranked cells, factor effects, OTF ΔR, sample-size warnings).

The runner must remain **independent of Streamlit day-to-day use**: no engine, fill, confluence-math, or page behavior changes in the core series. Classic UI and assistant confirmation flows keep working unchanged while RS lands.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Research Study Runner |
| Package home | `thesistester/study/` (additive module; not a separate repo) |
| Primary surface | CLI: `python -m thesistester study {expand,run,report}` |
| Compute core | Existing `run_experiment` + `build_research_bundle` (same path as CLI `_execute_run`); emit `experiment.yaml` for R18 replay |
| Engine / golden impact | **None** for RS1–RS5 (no `engine/` edits) |
| Streamlit / pages impact | **None** for RS1–RS5 |
| Assistant / MCP impact | Optional RS6 only; default-off tools |
| NL / LLM compiler | Explicitly deferred (RS-D1); closed YAML StudySpec is the contract |
| External Grok Bot | Out of repo scope; consumes CLI/MCP after RS5/RS6 |
| Strategy generation | **Non-goal** (aligns with `ENGINEERING_PROPOSAL.md` §2.2) |

**Feasibility:** High. R18 already runs independent RunSpecs and writes bundles + `results_index.csv`. The missing product surface is **study expansion + study-owned execution ledger + aggregation**, not new simulation semantics.

---

## 3. Problem statement

### 3.1 User need

Researchers want to say (conceptually):

> Test pdPOC with SMA 50/200 and EMA 21 on 1/5/30m; for each pairing always cover global + anchor, both directions, multiple entries including 3c on multiple trigger TFs, and measure how OTF across TFs changes R.

Today that requires hand-authoring dozens/hundreds of YAML runs, no study identity, and weak cross-run analysis beyond `results_index.csv`.

### 3.2 Gaps today

| Desired | Current state |
|---|---|
| Closed multi-factor confluence/level sweep | Missing (grid sweeps SL/TP, not confluence axes) |
| Deterministic expansion with run-count preview | Missing |
| Confirm gate before large unattended batches | Missing (CLI runs immediately) |
| Study-level ledger of every attempted cell | Partial (`run_batch` is all-or-nothing; no per-cell failure rows) |
| Factor / OTF Δ overview | Missing |
| Agent-operable study surface | R18 run-level only |

### 3.3 Why not “just let an LLM drive Streamlit”

- UI automation is fragile and non-reproducible for scientific claims.
- Free-form agent loops invite setup invention (anti-roadmap: genetic/LLM strategy generation).
- Classic research UX must stay undisturbed during implementation.

### 3.4 Scope boundary vs confluence-combo attribution

| Surface | Question answered |
|---|---|
| **Research Study Runner (this plan)** | Across many closed setups, which factor combinations look promising? |
| **Confluence combo attribution** | Within one setup’s trades, which level memberships co-occur? |

Keep docs, schemas, and agent prompts separate. Do not fold combo attribution into StudySpec factors.

---

## 4. Goals and non-goals

### 4.1 Goals

1. **StudySpec v1** — versioned, fail-closed schema for closed factorial (and staged) studies.
2. **Deterministic expander** — StudySpec → R18 `experiment.yaml` with stable run names and factor tags.
3. **Dry-run / confirm** — expand + count + estimated cost; refuse or require `--confirm` above a threshold.
4. **Study runner** — study-owned cell loop over `run_experiment` + bundle write; write study artifacts beside run bundles; still emit replayable `experiment.yaml`.
5. **Aggregator** — overview tables from study index + factor map (expectancy, PF when available, DD, N, OTF Δ).
6. **Honesty** — multiple-testing warnings, min-trades filters, no “winner” language without caveats.
7. **Regression safety** — zero engine/page golden drift in core PRs; docs + tests land with code.
8. **Usability during build** — each PR shippable; Streamlit path untouched through RS5.

### 4.2 Non-goals (explicit)

| Non-goal | Reason |
|---|---|
| Engine / confluence / fill changes | Out of series; golden identity must hold |
| Streamlit Study UI (MVP) | Headless-first; UI optional later |
| Genetic / open-ended strategy search | §2.2 anti-roadmap |
| LLM inventing levels, tolerances, or SL/TP | Closed factors only |
| Live trading / scheduling daemon / job queue | Unnecessary for local research loop |
| Embedding Grok Bot / RabbitMQ / multi-agent host | External coworker; not product core |
| Portfolio capital simulation across study cells | Use existing post-hoc portfolio analytics later if needed |
| Auto-promote “best cell” into a thesis without human confirm | Human remains decision maker |
| Changing `run_batch` default abort/write semantics | R18 identity; study layer owns continue-capable ledger |

---

## 5. Architecture

### 5.1 Boundary diagram

```text
                    ┌─────────────────────────────┐
                    │  External coworker (opt.)   │
                    │  Grok Bot / human / MCP     │
                    └──────────────┬──────────────┘
                                   │ study.yaml + CLI
                                   ▼
┌──────────────────────────────────────────────────────────┐
│ thesistester/study/          NEW (RS1–RS5)               │
│  schema → expand → execute(ledger) → report              │
│  emits experiment.yaml for R18 replay                    │
└──────────────────────────────┬───────────────────────────┘
                               │ per cell: run_experiment
                               │           + build_research_bundle
                               ▼
┌──────────────────────────────────────────────────────────┐
│ thesistester/{api,cli}.py    EXISTING (untouched logic)  │
│  run_experiment / _execute_run path; run_batch unchanged │
└──────────────────────────────┬───────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│ engine / levels / signals / pages                        │
│  NO CHANGES in RS1–RS5                                   │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Package layout (target)

```text
thesistester/study/
  __init__.py          # public exports only
  schema.py            # StudySpec load/validate/normalize (fail-closed)
  expand.py            # StudySpec → experiment dict + factor map
  naming.py            # deterministic filesystem-safe run names
  execute.py           # study-owned cell loop (run_experiment + bundle + index)
  ledger.py            # study manifest + cell registry
  report.py            # aggregate overview from index + factor map
  cli_study.py         # argparse handlers (wired from __main__/cli)
docs/STUDY_RUNNER.md   # user/agent contract (lands RS1, grows each PR)
tests/study/           # unit + golden expand fixtures
examples/studies/      # stage-first example YAML (RS5; may land earlier as fixture)
```

### 5.3 Design principles

1. **Sidecar-in-package:** lives beside R18; does not import Streamlit; does not mutate engine modules.
2. **Fail-closed StudySpec unknown keys** (StudySpec top-level / study / factors / report / stage). Note nuance vs R18: **run-level** unknown keys fail closed (`_RUN_KEYS`); **setup** unknown keys are stripped by `build_setup` — do **not** rely on setup-level fail-closed for factor tags.
3. **Expansion purity:** `expand(study) -> experiment` is pure and golden-testable without market data.
4. **Study-owned execution (locked):** `study run` loops cells using the same composition as `cli._execute_run` (`run_experiment` → `build_research_bundle` → index row), writing bundles/index incrementally and updating the ledger per cell. Still emit `experiment.yaml` so `python -m thesistester run experiment.yaml` can replay. **Do not** call `run_batch` for ledgered study runs — `run_batch` validates all, executes all into memory, then writes artifacts once; any exception yields **no** partial bundles/index (all-or-nothing). Changing that is RS-D3, not RS3.
5. **Factor tags travel with every cell** in `study.expansion.json` / ledger only — never stuff `study_factors` into RunSpec (run-level unknown keys fail) or depend on setup passthrough (stripped).
6. **Default-off integration:** no assistant/page wiring until RS6.
7. **Enabled flags are load-bearing:** when emitting `grid` / `validation` / `walk_forward` mappings, always set `enabled: false` unless the StudySpec explicitly enables them. Present mapping with omitted `enabled` defaults to **True** in `run_experiment` and silently arms SL/TP grids / batteries.

---

## 6. StudySpec v1 contract (normative)

### 6.1 Top-level shape

Constants are conceptually split to mirror R18 (`_RUN_KEYS` vs setup):

- **Setup constants** — direction, confluence knobs, triggers, OTF defaults, naked_*, `trigger_params`, optional `entry_window`.
- **Run sections** — `backtest`, `grid`, `validation`, `walk_forward` (pass-through; not nested under setup).

```yaml
schema_version: 1
study:
  name: pdPOC_ma_confluence_battery   # must match ^[A-Za-z0-9][A-Za-z0-9_-]*$
  description: optional
  output_dir: results/studies/pdPOC_ma_confluence_battery
  workers: 4
  confirm_above_runs: 200             # require --confirm if expansion >= N

  dataset:                             # R18 dataset mapping (pass-through)
    path: data/es_1m.csv
    instrument: ES
    source_timezone: America/New_York
    # optional: subtimeframe_path, ingestion_mode, format_profile, …

  levels:                              # R18 levels mapping (pass-through + defaults)
    sma_lengths: [50, 200]
    ema_lengths: [21]
    sma_timeframes: [1min, 5min, 30min]
    ema_timeframes: [1min, 5min, 30min]

  constants:
    # --- setup constants ---
    direction: both
    tolerance_ticks: 0                 # global_cluster shared tol; also partner-rule tol in anchor
    min_confluences: 2                 # overridden for global cells to len(selected_levels)
    max_confluences: 2                 # overridden for global cells; hard cap 5
    min_valid_confluences: 1           # anchor mode
    naked_only: false
    naked_requirement: any
    trigger_params: {}                 # 3c defaults apply when empty (entry_retrace_ticks=4, wait=5)
    entry_window: null                 # optional SW pass-through; null = unconstrained
    # --- run sections (never emit bare {} for grid/validation/walk_forward) ---
    backtest:
      stop_loss_ticks: 8
      take_profit_ticks: 16
      exposure_policy: single_position   # explicit; product API default is allow_all
      commission_per_side: 0.0           # recommend non-zero for honest studies
      slippage_ticks: 0.0
      flat_by_session_close: false
      intrabar_model: sl_first           # R12 opt-in models allowed when dataset supports them
    grid: { enabled: false }
    validation: { enabled: false }
    walk_forward: { enabled: false }

  factors:                             # cartesian product unless stage rules say otherwise
    core_level: [pdPOC]
    partner_levels:                    # list of lists; one partner-set per cell
      - [SMA_50_1min]
      - [SMA_50_5min]
      - [SMA_200_30min]
      - [EMA_21_5min]
    confluence_mode: [global_cluster, anchor_rules]
    trigger: [touch, reject, break, reclaim, 3c]
    trigger_timeframe: [base, 1min, 5min, 15min]
    otf:
      - { enabled: false }
      - { enabled: true, timeframes: [5m], alignment_mode: all, minimum_consecutive_bars: 3 }
      - { enabled: true, timeframes: [15m], alignment_mode: all, minimum_consecutive_bars: 3 }
      - { enabled: true, timeframes: [30m], alignment_mode: all, minimum_consecutive_bars: 3 }
      - { enabled: true, timeframes: [5m, 15m, 30m], alignment_mode: all, minimum_consecutive_bars: 3 }

  mode_rules:
    global_cluster:
      selected_levels: ["${core_level}", "${partner_levels...}"]
      # expander sets min_confluences = max_confluences = len(selected_levels);
      # reject if len > 5
    anchor_rules:
      selected_levels: []              # required explicit empty (UI/valid pattern)
      anchor_level: "${core_level}"
      confluence_rules:
        from_partners: required        # each partner → required rule @ constants.tolerance_ticks
    # Forbidden: partner_levels empty; core_level multi-value without explicit product intent

  report:
    primary_metric: expectancy_r       # must be available on study index (see §9)
    secondary_metrics: [profit_factor, max_drawdown_r, trade_count, total_r]
    min_trades: 30
    group_by: [partner_levels, confluence_mode, trigger, trigger_timeframe, otf]
    otf_baseline: { enabled: false }   # Δ metrics vs this factor level
    multiple_testing: warn             # warn | error (error refuses “best cell” summary)

  # Optional staging (see §6.3). Prefer active stage.filter on large examples.
  stage:
    mode: filter
    include:
      trigger: [touch]
      trigger_timeframe: [base]
```

**Example cell counts (literal §6.1 factors):**

| Expansion | Formula | Cells |
|---|---|---|
| Full cartesian | `1 × 4 × 2 × 5 × 4 × 5` | **800** |
| Stage `touch` + `base` | `1 × 4 × 2 × 1 × 1 × 5` | **40** |

“1–2k” only applies if the partner universe expands to all MA columns implied by `levels` (e.g. 6 SMA + 3 EMA). Do not claim 1–2k for the written example.

### 6.2 Expansion semantics (locked)

1. Cartesian product over `factors` keys (order = YAML key order for stable naming).
2. Each cell becomes one R18 run with:
   - `name`: deterministic slug matching `_RUN_NAME_RE` = `^[A-Za-z0-9][A-Za-z0-9_-]*$` (`naming.py`). No dots/spaces.
   - `setup`: built via existing `build_setup` / dicts that pass `validate_run_spec` — **never** hand-rolled invalid keys.
   - Injected every cell: `setup.name` (may equal run name or a stable study cell label), `setup.instrument` (= `dataset.instrument`), `setup.description` (may be empty string).
   - Factor map entry only in study artifacts (`study.expansion.json` / ledger).
3. `direction: both` is one run (engine already supports it). Do **not** expand long/short unless `direction` is listed under `factors`.
4. Trigger timeframe domain = existing `VALID_TRIGGER_TIMEFRAMES` (`base`, `1min`, `5min`, `15min`). Reject `30min` trigger at validate time with a clear error.
5. OTF domain = existing `normalize_otf_filter_config`. Canonical TF tokens in emitted configs and factor_map are `5m` / `15m` / `30m` (aliases `5min` etc. normalize). Store the **normalized** OTF dict (or a stable canonical key) in the factor map so OTF Δ grouping does not fork on alias spelling.
6. Level column names for multi-TF MAs follow product naming: `SMA_{len}_{tf}`, `EMA_{len}_{tf}` with TF ∈ `{1min, 5min, 30min}`.
7. Partner / core level tokens must be ⊆ closed set: known static/session/profile names (e.g. `pdPOC`, `ONH`, …) ∪ MA/EMA columns implied by `levels.*` lengths×timeframes. Unknown tokens fail at StudySpec validate (RS1) or expand (RS2) with actionable errors.
8. Unknown StudySpec keys → validation error. Pass-through blocks (`dataset`, `levels`, run sections) are validated by existing `validate_run_spec` **after** expansion (each run).
9. **Global mode:** `selected_levels = [core] + partners`; expander sets `min_confluences = max_confluences = len(selected_levels)`; reject `len > 5`.
10. **Anchor mode:** `selected_levels = []`; `anchor_level = core`; one required `confluence_rules` entry per partner at `constants.tolerance_ticks`; `min_valid_confluences` from constants (≤ rule count).
11. **Enabled emission:** every expanded run includes `grid: {enabled: false}`, `validation: {enabled: false}`, `walk_forward: {enabled: false}` unless StudySpec constants explicitly enable them. Never omit the mapping or emit bare `{}`.
12. Optional backtest honesty knobs (`commission_per_side`, `slippage_ticks`, session exits, `intrabar_model`, `entry_window`) pass through when present; defaults match R18/`_BACKTEST_DEFAULTS` if omitted.

### 6.3 Staging (v1 support, recommended default practice)

```yaml
stage:
  mode: filter          # filter | explicit_cells
  include:
    trigger: [touch]
    trigger_timeframe: [base]
```

| Mode | When | Behavior |
|---|---|---|
| `filter` | RS1 schema + RS2 expand | Subset listed factor axes before cartesian product |
| `explicit_cells` | RS1 schema accept; promote writer in RS5 | Exact list of factor tuples (survivors); no accidental re-expansion of open axes |

RS5: `study promote` reads prior overview → draft StudySpec with `stage.mode: explicit_cells` (or equivalent survivor list). Human edit/confirm still required before `study run`.

Optional later additive field (RS5 / RS5.1 if needed): `from_report: { study_dir, top_n, metric }` — only if fail-closed tests pass; otherwise keep promote as a draft-file helper without schema creep.

### 6.4 Confirm policy

| Condition | Behavior |
|---|---|
| `expand` | Always allowed; prints run count + estimated cost hints + writes preview artifacts |
| `run` and count < `confirm_above_runs` | Allowed |
| `run` and count ≥ `confirm_above_runs` without `--confirm` | Exit non-zero with message |
| `run --confirm` | Allowed; ledger records confirmation timestamp + count |

**Cost hints (RS3):** print workers, run_count, and warn loudly if any cell has `grid.enabled`, `validation.enabled`, or `walk_forward.enabled` (those dominate R18 runtime). Estimation may be heuristic (cells × workers); exact wall-clock is not a CI gate.

---

## 7. Artifacts (study output contract)

For a study written to `output_dir`:

| Artifact | Writer | Purpose |
|---|---|---|
| `study.spec.yaml` | expand/run | Canonical normalized StudySpec copy |
| `study.expansion.json` | expand | Factor map: `run_name → factors` (OTF canonicalized) |
| `experiment.yaml` | expand | R18 batch file (replay via `python -m thesistester run`) |
| `study.ledger.json` | run | Status per cell (`pending/running/ok/failed`), timestamps, error strings, bundle paths |
| `*.research.zip` | study execute (same as R18) | Per-run bundles |
| `results_index.csv` | study execute | Per-run metrics (R18 column set + study `status` if study-authored) |
| `study.overview.csv` | report | Joined index + factors |
| `study.overview.md` | report | Human/agent summary with honesty caveats |
| `study.otf_delta.csv` | report | Optional; metrics vs OTF baseline factor |

Canonical study identity hash (RS2): hash normalized StudySpec bytes (stable key order) — used in ledger, not for bundle equality.

**Note on `results_index.csv` columns (current R18 `_execute_run`):**  
`run_name`, `bundle_hash`, `dataset_id`, `instrument`, `execution_origin`, `cache_outcome`, `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, `best_grid_*`, `validation_trade_count_status`, `wfa_*`, `bundle_path`.  
**Not present today:** `profit_factor`, `status`, `win_rate`. Study execute may add a study-local `status` column when writing the study index; PF is handled per §9.2.

---

## 8. CLI surface

```bash
# Preview only (no backtests)
python -m thesistester study expand path/to/study.yaml --output-dir out/study1

# Execute (study-owned cell loop; emits/uses experiment.yaml; does not alter run_batch)
python -m thesistester study run path/to/study.yaml --output-dir out/study1 [--workers N] [--confirm]

# Aggregate after runs (or re-run report)
python -m thesistester study report out/study1

# Optional (RS5): draft survivor StudySpec — does not execute
python -m thesistester study promote out/study1 --output path/to/draft_study.yaml
```

Wiring: extend `thesistester/cli.py` / `__main__.py` with a `study` subparser **without** changing `run` argparse defaults or help text semantics. Today `main` asserts `command == "run"` — extend dispatch carefully; existing `tests/test_cli.py` subprocess parity must stay green.

---

## 9. Aggregation / overview contract

### 9.1 Join

`study.overview.csv` = study `results_index.csv` ⟕ `study.expansion.json` on `run_name`.

### 9.2 Metric sources (locked)

| Metric | MVP source |
|---|---|
| `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, `bundle_hash`, `bundle_path` | Study/R18 index columns |
| `status` | Study ledger / study-authored index column (not R18 `run_batch` index) |
| `profit_factor` (and optional `win_rate`) | **Preferred:** read from bundle `trade_summary` during report (or during study execute when writing index). **Optional precursor (RS-D7):** additive R18 index columns — versioned, tested, default-compatible; do not silently change R18 index schema inside RS4 without that precursor. |
| Ranking primary | Must be index-available (`expectancy_r` default). If `primary_metric: profit_factor`, report must resolve PF via bundle/index extension before ranking. |

### 9.3 Derived views

1. **Ranked cells** by `primary_metric` with `trade_count >= min_trades`.
2. **Group summaries** for each `report.group_by` key (median/mean expectancy, cell counts).
3. **OTF delta:** for each non-OTF factor tuple, compute metric(OTF variant) − metric(baseline OTF factor) using canonical OTF keys.
4. **Honesty block** in Markdown: multiple-testing warning, N filter, “descriptive study ranking ≠ validated edge”.
5. **Low-N section:** cells below `min_trades` listed separately, not in ranked winners.

### 9.4 Explicitly out of MVP report

- Automatic WFA/PBO per cell (cells may enable validation in constants; report does not re-battery).
- Pareto frontiers / Bayesian optimization.
- Natural-language LLM narrative (external coworker may add that from `study.overview.md`).

---

## 10. Regression-safety binding

Every RS PR must satisfy `ENGINEERING_PROPOSAL.md` §4.2:

| Gate | RS1–RS5 expectation |
|---|---|
| Golden masters | Untouched; suite remains green; **no** regeneration |
| Engine / pages | No edits (allow-list exceptions only in RS0 docs / RS6 assistant tools) |
| Defaults | Existing `python -m thesistester run` identical (`run_batch` semantics unchanged) |
| Schema | StudySpec versioned; unknown StudySpec keys fail closed |
| Docs | `STUDY_RUNNER.md` + this plan status + roadmap row updated same PR |
| Tests | Expander golden + validator negatives + execute ledger fixtures + report join fixtures |
| PIT | No new causality claims; inherit RunSpec/PIT docs |

**Forbidden in RS1–RS5:** edits under `thesistester/engine/`, `thesistester/levels/` (except read-only imports of validators/constants if needed), `pages/`, fill/signal semantics; changing `run_batch` abort/write behavior.

Allowed read-only imports: `setup` validators/constants, `normalize_otf_filter_config`, `api.run_experiment` / `validate_run_spec` / `build_setup`, `reporting.build_research_bundle` (or current bundle builder symbol), CLI helpers only if imported without altering `run` defaults.

---

## 11. PR sequence (fully scoped)

### RS0 — Plan lock (this document)

| | |
|---|---|
| **Scope** | Add/amend `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`; index in `docs/README.md` + `docs/ENGINEERING_ROADMAP.md` |
| **Code** | None |
| **Tests** | None |
| **Acceptance** | Plan reviewed; R18 contracts accurate; series RS1–RS5 scopes unambiguous; non-goals locked |
| **Risk** | None |

---

### RS1 — StudySpec schema + validation (no execution)

| | |
|---|---|
| **Scope** | `thesistester/study/schema.py` (+ `__init__.py`); `docs/STUDY_RUNNER.md` (schema section); `tests/study/test_study_schema.py` |
| **Behavior** | Load YAML → normalize → validate; reject unknown keys; validate factor domains against known trigger/OTF/confluence enums; validate partner/core tokens against closed level set implied by `levels` + known static names; validate `confirm_above_runs >= 1`; study/run names match `_RUN_NAME_RE`; accept `stage.mode` ∈ `{filter, explicit_cells}` (expand may implement filter only until RS2/RS5); require explicit `enabled` on grid/validation/walk_forward when those mappings are present |
| **Out of scope** | Expansion to runs; CLI; engine; pages |
| **Regression** | No existing module behavior change |
| **Acceptance checklist** | |
| | ☐ Valid minimal StudySpec fixture normalizes stably |
| | ☐ Unknown top-level / factor keys fail closed |
| | ☐ Invalid trigger / trigger_timeframe / otf / partner tokens rejected with actionable errors |
| | ☐ `direction` in constants allowed; listing unsupported factor axes errors clearly |
| | ☐ `stage.mode: explicit_cells` accepted by schema (even if expander promote lands RS5) |
| | ☐ Docs describe schema_version: 1 |
| | ☐ `pytest -q tests/study/test_study_schema.py` green; full suite green |

**Copy-ready agent prompt:**

```text
Implement RS1 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS1.
Add thesistester/study/schema.py (+ package init) and docs/STUDY_RUNNER.md schema section.
Fail-closed unknown StudySpec keys. Validate against existing trigger/OTF/confluence enums
and closed partner/core level tokens. Accept stage filter|explicit_cells.
Require enabled flags on grid/validation/walk_forward mappings when present.
No engine/pages/cli execution. Tests under tests/study/. Update roadmap status RS1.
Follow ENGINEERING_PROPOSAL.md §4.2. Keep classic UI undisturbed.
Do not merge with confluence-combo attribution.
```

---

### RS2 — Deterministic expander → R18 experiment.yaml

| | |
|---|---|
| **Scope** | `expand.py`, `naming.py`; expand golden fixtures; extend `STUDY_RUNNER.md` |
| **Behavior** | `expand_study(normalized) -> ExpansionResult{experiment, factor_map, run_count}`; map global/anchor mode_rules per §6.2; inject setup name/instrument/description; canonicalize OTF in factor_map; call `build_setup` or produce dicts that pass `validate_run_spec` for each cell; emit `enabled: false` for grid/validation/walk_forward unless explicitly enabled; write helpers for `study.spec.yaml`, `study.expansion.json`, `experiment.yaml` |
| **Out of scope** | Running backtests; report; confirm enforcement (print count only) |
| **Regression** | Pure functions; no CLI default changes; no `run_batch` edits |
| **Acceptance checklist** | |
| | ☐ Golden expansion fixture: byte-stable experiment YAML + factor_map JSON |
| | ☐ Every expanded run passes `validate_run_spec` |
| | ☐ Anchor cells set `selected_levels=[]`, `anchor_level=core`, required partner rules |
| | ☐ Global cells set `selected_levels=[core]+partners` with min=max=len and len≤5 |
| | ☐ Run names unique and match `_RUN_NAME_RE` |
| | ☐ Stage `filter` reduces cartesian product correctly (example: 800 → 40) |
| | ☐ No bare `grid`/`validation`/`walk_forward` `{}`; enabled false by default |
| | ☐ Full suite green; no golden-master regeneration |

**Copy-ready agent prompt:**

```text
Implement RS2 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS2.
Add expand.py + naming.py. Deterministic StudySpec→R18 experiment expansion with factor_map.
Follow §6.2 (anchor selected_levels=[], global min=max=len≤5, setup injects, OTF canonicalize,
enabled:false emission). Golden-test expansion. Every run must pass validate_run_spec.
No backtest execution. No engine/pages/run_batch changes. Docs + roadmap. §4.2.
```

---

### RS3 — CLI `study expand` + `study run` (study-owned execute + ledger)

| | |
|---|---|
| **Scope** | `cli_study.py`; wire `study` subcommands in `cli.py`/`__main__.py`; `execute.py`; `ledger.py`; tests for confirm gate + ledger + partial failure |
| **Behavior** | `expand` writes artifacts + cost hints; `run` expands (if needed), enforces confirm policy, **study-owned cell loop** (`run_experiment` + `build_research_bundle` + incremental index/ledger), preserves R18 bundle layout under study `output_dir`, keeps emitting `experiment.yaml` for replay; failed cell recorded in ledger and skipped for remaining cells (continue-on-failure at **study** layer only) |
| **Out of scope** | Changing `run_batch` semantics; overview Markdown intelligence; assistant tools |
| **Regression** | `python -m thesistester run` path must remain behavior-identical (additive subparser only; `run_batch` untouched) |
| **Acceptance checklist** | |
| | ☐ `study expand` writes the three artifacts and prints run_count (+ cost hints) |
| | ☐ `study run` without `--confirm` fails when run_count ≥ confirm_above_runs |
| | ☐ `study run --confirm` executes; ledger marks ok/failed per cell |
| | ☐ One failing cell leaves prior ok bundles/index rows intact; failure surfaced in ledger |
| | ☐ `run_batch` / `thesistester run` tests unchanged and green |
| | ☐ Warn when any cell enables grid/validation/walk_forward |
| | ☐ AGENT_GUIDE headless section gains Study Runner pointer; ARCHITECTURE boundary note |
| | ☐ Full suite green |

**Note on failure semantics:** RS3 must **not** change `run_batch` to continue-on-failure. Study execute owns continue-capable accounting. Optional later R18 additive flag remains RS-D3.

**Copy-ready agent prompt:**

```text
Implement RS3 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS3.
Wire `python -m thesistester study expand|run`. Implement study-owned execute loop
(reuse run_experiment + build_research_bundle composition like cli._execute_run).
Do NOT call run_batch for ledgered runs; do NOT change run_batch defaults/semantics.
Enforce confirm_above_runs + cost hints. Write study ledger with per-cell ok/failed.
Update AGENT_GUIDE + STUDY_RUNNER.md + ARCHITECTURE + roadmap.
No engine/pages. §4.2 checklist. Keep `thesistester run` identical.
```

---

### RS4 — Study report / overview aggregator

| | |
|---|---|
| **Scope** | `report.py`; `study report` CLI; fixtures with synthetic index + expansion map; honesty text in `ASSUMPTIONS_AND_LIMITATIONS.md` + `METRICS_GLOSSARY.md` |
| **Behavior** | Join → overview CSV/MD; ranked cells; group_by summaries; OTF delta vs baseline using canonical OTF keys; min_trades filter; multiple_testing warn block; resolve `profit_factor` via bundle `trade_summary` (or study index if RS-D7 landed) |
| **Out of scope** | LLM narrative; UI page; silent R18 `results_index` schema change without RS-D7 |
| **Acceptance checklist** | |
| | ☐ Overview join is deterministic and complete for fixture |
| | ☐ Cells below min_trades excluded from “ranked” section but listed under low-N |
| | ☐ OTF delta rows correct vs baseline factor (alias-stable) |
| | ☐ Markdown includes multiple-testing honesty paragraph |
| | ☐ Glossary entries for study overview metrics / OTF Δ |
| | ☐ PF available in overview when bundles present (document source) |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS4 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS4.
Add report.py + `study report`. Emit study.overview.csv/md and otf_delta.csv.
Resolve profit_factor from bundle trade_summary unless RS-D7 index columns exist.
Honesty + glossary updates. No engine/pages. No silent R18 index schema change.
Deterministic fixtures. §4.2.
```

---

### RS5 — Staging helpers + survivor promotion + docs polish

| | |
|---|---|
| **Scope** | Stage filter hardening; `study promote` draft generator (`explicit_cells`); examples under `examples/studies/` with **active** stage-first filter (40-cell path) and commented full 800-cell phase-2; USER_GUIDE short section (Help corpus — coordinate HC allowlist if required); roadmap sign-off for core series |
| **Behavior** | From a completed study dir, generate a **draft** StudySpec containing only selected survivor factor tuples, still requiring human edit/confirm before run |
| **Out of scope** | Auto-run promotion; assistant NL |
| **Acceptance checklist** | |
| | ☐ Promote writes draft StudySpec; does not execute |
| | ☐ Example YAML expands to 40 cells with stage filter; full 800 documented as phase-2 |
| | ☐ Tiny CI subset fixture still used for unit/golden (2×2×2) |
| | ☐ USER_GUIDE / STUDY_RUNNER end-to-end recipe |
| | ☐ Core series RS1–RS5 marked implemented on roadmap after green CI |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS5 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS5.
Add survivor promotion draft helper + examples/studies (stage-first 40-cell default,
full 800 as phase-2 comment) + docs polish.
No auto-execution. No engine/pages. HC allowlist update if USER_GUIDE gains Help content.
§4.2. Mark RS1–RS5 complete on roadmap only when acceptance passes.
```

---

### RS6 — Optional agent tools (MCP / assistant) — **opt-in, after core**

| | |
|---|---|
| **Scope** | Thin tools wrapping `expand` / `run` / `report` for Research Assistant and/or MCP server descriptors; default **disabled** |
| **Behavior** | Tools accept StudySpec path or structured dict; always return run_count and require explicit confirm tool call mirroring CLI `--confirm` |
| **Out of scope** | Free-form “invent a study from vibes”; Grok Bot product integration; Streamlit redesign |
| **Regression** | Assistant parity fixtures must stay green; tools disabled by default |
| **Acceptance checklist** | |
| | ☐ Default assistant path unchanged |
| | ☐ Enabled tools cannot bypass confirm threshold |
| | ☐ Docs: how external Grok Bot should call CLI/MCP |
| | ☐ Full suite + assistant parity green |

**Copy-ready agent prompt:**

```text
Implement RS6 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS6.
Add default-off assistant/MCP tools for study expand/run/report with confirm parity.
Do not change engine or classic pages. Keep assistant parity fixtures green. §4.2.
```

---

## 12. Deferred follow-ups (not in core series)

| ID | Item | Notes |
|---|---|---|
| RS-D1 | NL → StudySpec compiler | LLM may draft YAML; human/validator gate required; never execute unchecked NL |
| RS-D2 | Streamlit “Studies” page | Thin viewer of overview artifacts only |
| RS-D3 | Continue-on-failure flag on `run_batch` | Additive R18 change; study layer already continues; only if replay parity desired |
| RS-D4 | Study-aware WFA/PBO rollup | Compose existing batteries; do not invent new inference |
| RS-D5 | Grok Bot routine pack | External; document recipe only in RS6 |
| RS-D6 | Multi-partner clusters / tolerance sweeps | New factor types; schema_version bump |
| RS-D7 | Additive R18 index columns (`profit_factor`, optional `win_rate`) | Small versioned R18 follow-up; unblocks PF ranking without zip scrape; default-compatible |

---

## 13. Worked example (acceptance narrative, not a CI mega-grid)

The motivating pdPOC study is **supported** by the schema. CI must **not** run the full **800**-cell grid. Instead:

1. Unit/golden tests use a **2×2×2** miniature (2 partners × 2 modes × 2 OTF) plus one 3c/trigger_tf smoke cell.
2. `examples/studies/pdPOC_ma_confluence_battery.yaml` ships with an **active** `stage.filter` (recommended first pass = **40** cells) and comments documenting the full **800**-cell phase-2 factor lists:

```yaml
stage:
  mode: filter
  include:
    trigger: [touch]
    trigger_timeframe: [base]
# Phase 2: remove/widen stage after promote, or open trigger/trigger_timeframe axes
# on survivor partners only. Full cartesian for §6.1 factors = 800 cells.
```

Recommended human workflow after RS5:

1. Stage filter expand/run/report (40 cells).  
2. Promote survivors (`explicit_cells` draft).  
3. Open triggers/TFs/3c on the reduced set.  
4. Interpret OTF Δ with multiple-testing caution.  
5. Prefer non-zero `commission_per_side` / `slippage_ticks` before trusting expectancy ranks.

---

## 14. Documentation plan

| Doc | When | Change |
|---|---|---|
| `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | RS0 | This plan; status updates per PR |
| `STUDY_RUNNER.md` | RS1–RS5 | Living operator contract |
| `ENGINEERING_ROADMAP.md` | each PR | RS status row |
| `AGENT_GUIDE.md` | RS3 | Headless study commands |
| `ARCHITECTURE.md` | RS3 | Boundary note: study module → `run_experiment` / bundles; `run_batch` unchanged |
| `ASSUMPTIONS_AND_LIMITATIONS.md` | RS4 | Study ranking / multiple-testing honesty |
| `METRICS_GLOSSARY.md` | RS4 | Overview / OTF Δ terms |
| `USER_GUIDE.md` | RS5 | Short recipe (HC allowlist if needed) |
| `README.md` (root) | RS5 | One-liner pointer optional |
| `CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` | RS0 pointer only | Keep separate; no edits required for RS |

---

## 15. Risk register

| Risk | Mitigation |
|---|---|
| Combinatorial fishing / overfitting | confirm gates; stage-first examples; honesty blocks; no auto-promote |
| Accidental engine edits in agent PRs | PR allow-list in prompts; CI golden gate |
| Factor tags stuffed into RunSpec/setup | External factor_map only; run-level unknown keys fail; setup strips unknowns |
| Assuming `run_batch` supports per-cell failure | Study-owned execute loop; `run_batch` left all-or-nothing (RS-D3) |
| Silent default-on grid/validation | Expander always emits `enabled: false` unless StudySpec enables |
| PF/status missing from R18 index | Study ledger status; PF from bundle or RS-D7 |
| OTF alias forks in Δ grouping | Canonicalize to `5m`/`15m`/`30m` in factor_map |
| Help corpus drift | HC allowlist PR when USER_GUIDE changes |
| Naming collisions / invalid run names | `_RUN_NAME_RE` + output_dir isolation |
| Merging study factorial with combo attribution | Explicit §3.4 boundary; separate docs |

---

## 16. Definition of done (core series RS1–RS5)

1. Researcher can author a closed StudySpec and run `study expand|run|report` without opening Streamlit.  
2. Expansion is deterministic and golden-tested; example stage path is 40 cells, full example cartesian is 800.  
3. Large studies require `--confirm`; cost hints warn on enabled batteries.  
4. Overview joins factors to metrics with OTF Δ and honesty caveats; PF sourced per §9.2.  
5. Classic UI, assistant defaults, engine goldens, and `thesistester run` / `run_batch` remain undisturbed.  
6. External bot (e.g. Grok Bot) can operate by shelling the CLI; first-class MCP/assistant tools optional in RS6.

---

## 17. Status tracker

| Milestone | Status |
|---|---|
| RS0 Plan lock | ✅ This document (amended for R18 contract accuracy) |
| RS1 Schema | ☐ |
| RS2 Expander | ☐ |
| RS3 CLI expand/run + study-owned ledger | ☐ |
| RS4 Report | ☐ |
| RS5 Staging/promote + examples | ☐ |
| RS6 Optional agent tools | ☐ Deferred until after RS5 |

---

## 18. RS0 review amendments (changelog)

Locked corrections from plan review against HEAD R18 APIs:

1. Example cartesian count **800** (stage-first **40**), not “1–2k”.
2. Study execution is a **study-owned loop** over `run_experiment` + bundle write; `run_batch` remains all-or-nothing and unchanged.
3. `results_index` does not currently include `profit_factor` / `status` — report/ledger sources specified; optional RS-D7.
4. `grid`/`validation`/`walk_forward` emission must set `enabled: false` explicitly (default-on trap).
5. Anchor cells require `selected_levels: []`; global cells force `min=max=len(selected_levels)` with hard cap 5.
6. Expander injects `setup.name` / `instrument` / `description` every cell.
7. Setup unknown-key behavior is strip-not-fail; factor tags stay in study artifacts only.
8. Canonical OTF tokens in factor_map; partner/core closed-set validation; `_RUN_NAME_RE` naming.
9. Constants surface documents day-trading pass-throughs (costs, session exits, entry_window, intrabar).
10. `explicit_cells` accepted in schema; stage-first examples; confirm cost hints; combo-attribution boundary.
