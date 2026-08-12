# Research Study Runner — Implementation Plan (RS)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-11 (amended 2026-08-12: post-MVP sequence lock + review contracts)  
**Status:** **RS1–RS5 complete** (holistic MVP). Post-MVP track plan-locked: **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5**; parked: RS-D1 / RS-D3 / RS-D6  
**Series code:** **RS** (Research Study Runner)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Related living docs:** `docs/AGENT_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/otf-filter.md`, `docs/USER_GUIDE.md`, `docs/STUDY_RUNNER.md`  
**Related but separate:** `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` (within-trade level membership — **not** cross-setup factorial studies; do not merge concepts)  
**Depends on (already shipped):** R18 headless API + batch CLI (`thesistester/api.py`, `thesistester/cli.py`), RunSpec validation, research bundles, `results_index.csv`, Study Runner package `thesistester/study/`

**Supersedes:** conversational design notes about an autonomous research bot / Grok Bot coworker (those remain usage patterns; this plan is the product contract).

**Completeness posture:** RS1–RS5 is the **holistic MVP** (author → expand → confirm → execute with ledger/resume → report → promote). **§12** locks the post-MVP expansion sequence (index PF → default-off assistant capabilities → Studies viewer → per-cell diagnostic rollup → Grok routine pack). Parked items stay out of the critical path.

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
| Primary surface | CLI: `python -m thesistester study {expand,run,report,promote}` |
| Compute core | Existing `run_experiment` + `build_research_bundle` (same path as CLI `_execute_run`); emit `experiment.yaml` for R18 replay |
| Engine / golden impact | **None** for RS1–RS5; RS-D7 may touch CLI index writers only (versioned, default-compatible) — still **no** `engine/` edits |
| Streamlit / pages impact | **None** for RS1–RS5 / RS-D7 / RS6; **RS-D2 only** adds a thin Studies viewer page |
| Assistant impact | Optional **RS6** only: default-off `FEATURE_PARITY_REGISTRY` capabilities (`STUDY.*`); no greenfield MCP server |
| NL / LLM compiler | Parked (RS-D1); closed YAML StudySpec remains the contract |
| External Grok Bot | Out of repo product core; **RS6** documents minimal CLI/confirm recipe; **RS-D5** is the full external routine pack |
| Strategy generation | **Non-goal** (aligns with `ENGINEERING_PROPOSAL.md` §2.2) |
| MVP completeness bar | RS1–RS5 usable end-to-end without Streamlit, NL, or assistant study tools ✅ |
| Post-MVP sequence | **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5** (locked in §12); do not reorder without amending this plan |

**Feasibility:** High. R18 already runs independent RunSpecs and writes bundles + `results_index.csv`. MVP shipped study expansion + study-owned execution ledger + aggregation; post-MVP deepens agent/UI/rollup surfaces without new simulation semantics.

### 2.1 MVP in-scope vs explicitly deferred

| In MVP (RS1–RS5) ✅ | Post-MVP sequenced (§12) | Parked (not sequenced) |
|---|---|---|
| Closed StudySpec YAML + fail-closed validate | **RS-D7** additive index `profit_factor` + `win_rate` | **RS-D1** NL → StudySpec compiler |
| Deterministic expand + golden fixtures | **RS6** default-off `STUDY.*` assistant capabilities | **RS-D3** `run_batch` continue-on-failure |
| Confirm gate + cost hints | **RS-D2** Streamlit Studies **viewer** (artifacts-only) | **RS-D6** multi-partner / tolerance factor types |
| Study-owned execute + per-cell ledger | **RS-D4** per-cell WFA/validation/overfitting diagnostic rollup | Auto-run promotion / scheduled studies |
| Soft resume + workers + continue-on-failure (study layer) | **RS-D5** Grok Bot routine pack (external; after RS6) | UI factor builder / templates marketplace |
| Overview CSV/MD + OTF Δ + honesty | | Embedding Grok host / RabbitMQ / job queue / live MCP server |
| Stage filter + promote → `explicit_cells` draft | | |
| Stage-first example (40) + documented full (800) | | |

---

## 3. Problem statement

### 3.1 User need

Researchers want to say (conceptually):

> Test pdPOC with SMA 50/200 and EMA 21 on 1/5/30m; for each pairing always cover global + anchor, both directions, multiple entries including 3c on multiple trigger TFs, and measure how OTF across TFs changes R.

Today that requires hand-authoring dozens/hundreds of YAML runs, no study identity, and weak cross-run analysis beyond `results_index.csv`.

### 3.2 Gaps at plan time (historical — pre-MVP)

> **Note:** This subsection is the **pre-RS1 gap snapshot**. Do not treat rows as
> current capability status. Living status → §17 + `ENGINEERING_ROADMAP.md`.
> MVP (RS1–RS5) closed the study expand/execute/report/promote gaps. Remaining
> gaps are the §12 post-MVP sequence (index PF, STUDY.* tools, viewer, rollup).

| Desired | State at plan authorship |
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
                    │  Grok Bot / human / RS6     │
                    └──────────────┬──────────────┘
                                   │ study.yaml + CLI (+ STUDY.* tools)
                                   ▼
┌──────────────────────────────────────────────────────────┐
│ thesistester/study/          SHIPPED (RS1–RS5)           │
│  schema → expand → execute(ledger) → report → promote    │
│  + tools.py (RS6) + rollup.py (RS-D4)                    │
│  emits experiment.yaml for R18 replay                    │
└──────────────────────────────┬───────────────────────────┘
                               │ per cell: run_experiment
                               │           + build_research_bundle
                               ▼
┌──────────────────────────────────────────────────────────┐
│ thesistester/{api,cli}.py    EXISTING                    │
│  run_experiment / _execute_run path; run_batch unchanged │
│  RS-D7: additive index columns on writers only           │
└──────────────────────────────┬───────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│ engine / levels / signals                                │
│  NO CHANGES in this series                               │
│ pages/: RS-D2 Studies viewer only (read-only)            │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Package layout (target)

```text
thesistester/study/
  __init__.py          # public exports only
  schema.py            # StudySpec load/validate/normalize (fail-closed) ✅
  expand.py            # StudySpec → experiment dict + factor map ✅
  naming.py            # deterministic filesystem-safe run names ✅
  execute.py           # study-owned cell loop (run_experiment + bundle + index) ✅
  ledger.py            # study manifest + cell registry ✅
  report.py            # aggregate overview from index + factor map ✅
  promote.py           # survivor draft StudySpec writer ✅
  cli_study.py         # argparse handlers (wired from __main__/cli) ✅
  tools.py             # RS6: thin STUDY.* capability adapters (default-off)
  rollup.py            # RS-D4: per-cell diagnostic rollup (compose-only)
docs/STUDY_RUNNER.md   # living operator contract ✅
tests/study/           # unit + golden expand fixtures ✅
examples/studies/      # stage-first example YAML ✅
pages/15_Studies.py    # RS-D2: read-only artifact viewer (name may follow nav)
```

### 5.3 Design principles

1. **Sidecar-in-package:** lives beside R18; does not import Streamlit; does not mutate engine modules.
2. **Fail-closed StudySpec unknown keys** (StudySpec top-level / study / factors / report / stage). Note nuance vs R18: **run-level** unknown keys fail closed (`_RUN_KEYS`); **setup** unknown keys are stripped by `build_setup` — do **not** rely on setup-level fail-closed for factor tags.
3. **Expansion purity:** `expand(study) -> experiment` is pure and golden-testable without market data.
4. **Study-owned execution (locked):** `study run` loops cells using the same composition as `cli._execute_run` (`run_experiment` → `build_research_bundle` → index row), writing bundles/index incrementally and updating the ledger per cell. Still emit `experiment.yaml` so `python -m thesistester run experiment.yaml` can replay. **Do not** call `run_batch` for ledgered study runs — `run_batch` validates all, executes all into memory, then writes artifacts once; any exception yields **no** partial bundles/index (all-or-nothing). Changing that is RS-D3, not RS3.
5. **Factor tags travel with every cell** in `study.expansion.json` / ledger only — never stuff `study_factors` into RunSpec (run-level unknown keys fail) or depend on setup passthrough (stripped).
6. **Default-off integration:** no assistant/page wiring until RS6.
7. **Enabled flags are load-bearing:** when emitting `grid` / `validation` / `walk_forward` mappings, always set `enabled: false` unless the StudySpec explicitly enables them. Footgun is a **present mapping with omitted `enabled`** (defaults **True** in `run_experiment` and arms batteries). Omitting the section entirely is execution-safe; expander still **emits** explicit `{enabled: false}` so replay YAML cannot accidentally gain bare `{}` later.
8. **Execute provenance (locked for RS3):**
   - `cache_policy="read_write"` (same as CLI `_execute_run`).
   - `execution_origin="study"` — requires an **additive** membership of `"study"` in `EXECUTION_ORIGINS` (`research_identity.py`). This is the only intentional non-`study/` code touch in RS1–RS5 besides CLI subparser wiring. Do **not** invent other origins; do **not** use `"cli"` while claiming study provenance.
   - `base_directory` = parent of the StudySpec path (dataset paths resolve like R18 YAML-relative).
9. **Workers (locked for RS3):** `workers: N` runs independent cells via spawn `ProcessPoolExecutor` (same isolation spirit as `run_batch`), but each task must **return** `{ok|failed}` payloads rather than raising past the pool boundary, so continue-on-failure and incremental ledger/index writes remain correct. `workers: 1` is the deterministic default for tests.
10. **Output dir / soft resume (locked for RS3 MVP):**
    - Same `output_dir` + same study identity hash + existing ledger `ok` cell → **skip** re-execution (soft resume).
    - Ledger `failed` / `pending` / missing → run.
    - Spec/expansion identity mismatch vs prior `study.spec.yaml` / hash → refuse unless `--force`.
    - `--force` re-runs all cells (overwrites bundles/index rows for those names).
    - Soft resume is MVP (unattended correctness); full job-queue/cancel UX remains deferred.

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
9. **Global mode (study emission rule):** `selected_levels = [core] + partners`; expander sets `min_confluences = max_confluences = len(selected_levels)`; reject if that length `> 5`. R18 itself enforces `max_confluences ≤ 5` and non-empty `selected_levels`, **not** `min=max=len` — the equality rule is Study Runner’s confluence-geometry contract.
10. **Anchor mode (study emission rule):** always emit `selected_levels: []`; `anchor_level = core`; one required `confluence_rules` entry per partner at `constants.tolerance_ticks`; `min_valid_confluences` from constants must be `≥ 1` and `≤ len(rules)`. R18 does **not** hard-fail non-empty `selected_levels` in anchor mode (signals ignore them for zones); Study Runner still emits `[]` for honesty/UI parity.
11. **Enabled emission:** every expanded run includes `grid: {enabled: false}`, `validation: {enabled: false}`, `walk_forward: {enabled: false}` unless StudySpec constants explicitly enable them. Never emit bare `{}`. Prefer explicit false over omitting the section (see §5.3.7).
12. Optional backtest honesty knobs (`commission_per_side`, `slippage_ticks`, session exits, `intrabar_model`, `entry_window`) pass through when present; defaults match R18/`_BACKTEST_DEFAULTS` if omitted.
13. **Index-row parity:** study execute builds the same metric keys as `cli._execute_run` (plus study `status`). Prefer a local helper in `study/execute.py` with a parity test against CLI keys — **do not** refactor `cli._execute_run` in MVP unless a tiny shared pure helper is extracted with zero behavior change and existing CLI tests stay green.

### 6.3 Staging (v1 support, recommended default practice)

```yaml
stage:
  mode: filter          # filter | explicit_cells
  include:
    trigger: [touch]
    trigger_timeframe: [base]
```

`explicit_cells` shape (normative — RS1 accepts; RS2/RS5 expand/promote):

```yaml
stage:
  mode: explicit_cells
  cells:
    - core_level: pdPOC
      partner_levels: [SMA_50_1min]
      confluence_mode: global_cluster
      trigger: touch
      trigger_timeframe: base
      otf: { enabled: false }
    - core_level: pdPOC
      partner_levels: [EMA_21_5min]
      confluence_mode: anchor_rules
      trigger: 3c
      trigger_timeframe: 5min
      otf:
        enabled: true
        timeframes: [30m]
        alignment_mode: all
        minimum_consecutive_bars: 3
```

| Mode | When | Behavior |
|---|---|---|
| `filter` | RS1 schema + RS2 expand | Subset listed factor axes before cartesian product; `include` keys must be subset of `factors` |
| `explicit_cells` | RS1 schema accept; expand in RS2; promote writer in RS5 | Each `cells[]` entry must supply **every** factor axis key used by the study (no silent defaults from open axes). Cartesian product is skipped. |

RS5: `study promote` reads prior overview → draft StudySpec with `stage.mode: explicit_cells` + `cells: [...]`. Human edit/confirm still required before `study run`.

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
python -m thesistester study run path/to/study.yaml --output-dir out/study1 \
  [--workers N] [--confirm] [--force]

# Aggregate after runs (or re-run report)
python -m thesistester study report out/study1

# Optional (RS5): draft survivor StudySpec — does not execute
python -m thesistester study promote out/study1 --output path/to/draft_study.yaml
```

| Flag | Behavior |
|---|---|
| `--workers N` | Overrides StudySpec `workers` for execute pool |
| `--confirm` | Required when `run_count >= confirm_above_runs` |
| `--force` | Ignore soft-resume skips; re-run all cells (see §5.3.10) |

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
| `profit_factor` / `win_rate` | **MVP:** resolve from bundle `trade_summary` during report (index wins per field when present). **RS-D7:** write both columns on study + CLI `results_index` at ok-cell write time (default-compatible; report already prefers index). |
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

| Gate | MVP (RS1–RS5) | Post-MVP (§12) |
|---|---|---|
| Golden masters | Untouched; **no** regeneration | Same |
| Engine | No edits | No edits |
| Pages | No edits | **RS-D2 only:** one read-only Studies viewer |
| Defaults | `thesistester run` / `run_batch` identical | Same; RS6 tools **default-off** |
| Schema | StudySpec fail-closed | StudySpec unchanged unless parked D6; RS-D7 additive **index columns only** (no Experiment schema bump) |
| Docs / tests | Land same PR | Land same PR; HC allowlist if USER_GUIDE H2 added (D2) |
| PIT | Inherit RunSpec/PIT docs | Same; no new causality claims |

**Forbidden (entire series including post-MVP):** edits under `thesistester/engine/`; fill/signal/confluence-math semantics; golden-master regeneration; changing `run_batch` abort/write defaults; greenfield in-product MCP server.

**Allowed additive non-`study/` touches (post-MVP allow-list):**

| Milestone | Allowed outside `thesistester/study/` |
|---|---|
| RS-D7 | `thesistester/cli.py` `_execute_run` index keys (+ parity tests) |
| RS6 | `assistant/registry.py` (+ handler/orchestrator wiring), `config/assistant.toml` default-off `[assistant.study_tools]` |
| RS-D2 | `pages/15_Studies.py` (or next free slot), USER_GUIDE + HC §7.1.4 / `help_corpus.py` |
| RS-D4 / RS-D5 | Docs/examples primarily; CLI subparser additive for `study rollup` if used |

Allowed read-only imports: `setup` validators/constants, `normalize_otf_filter_config`, `api.run_experiment` / `validate_run_spec` / `build_setup`, `research_bundle.build_research_bundle` / `canonical_bundle_hash`.

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
| **Behavior** | Load YAML → normalize → validate; reject unknown keys; validate factor domains against known trigger/OTF/confluence enums; validate partner/core tokens against closed level set implied by `levels` + known static names (`SUGGESTED_DEFAULT_LEVELS` ∪ implied MA/EMA columns ∪ other product static names as documented in `STUDY_RUNNER.md`); validate `confirm_above_runs >= 1`; study/run names match `_RUN_NAME_RE`; accept `stage.mode` ∈ `{filter, explicit_cells}` with `include` / `cells` shapes per §6.3; require explicit `enabled` on grid/validation/walk_forward when those mappings are present |
| **Out of scope** | Expansion to runs; CLI; engine; pages |
| **Regression** | No existing module behavior change |
| **Acceptance checklist** | |
| | ✅ Valid minimal StudySpec fixture normalizes stably |
| | ✅ Unknown top-level / factor keys fail closed |
| | ✅ Invalid trigger / trigger_timeframe / otf / partner tokens rejected with actionable errors |
| | ✅ `direction` in constants allowed; listing unsupported factor axes errors clearly |
| | ✅ `stage.mode: filter` requires `include`; `explicit_cells` requires non-empty `cells` with all factor keys |
| | ✅ Docs describe schema_version: 1 |
| | ✅ `pytest -q tests/study/test_study_schema.py` green (32 passed); no engine/pages/cli execution surface added |
| | ✅ Stage include/explicit_cells values ⊆ factor domains; levels list shapes fail closed as StudySpecError |

**Copy-ready agent prompt:**

```text
Implement RS1 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS1.
Add thesistester/study/schema.py (+ package init) and docs/STUDY_RUNNER.md schema section.
Fail-closed unknown StudySpec keys. Validate against existing trigger/OTF/confluence enums
and closed partner/core level tokens. Accept stage filter|explicit_cells with §6.3 shapes.
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
| **Behavior** | `expand_study(normalized) -> ExpansionResult{experiment, factor_map, run_count}`; map global/anchor mode_rules per §6.2; inject setup name/instrument/description; canonicalize OTF in factor_map; call `build_setup` or produce dicts that pass `validate_run_spec` for each cell; emit `enabled: false` for grid/validation/walk_forward unless explicitly enabled; implement `stage.filter` and `stage.explicit_cells` (§6.3); write helpers for `study.spec.yaml`, `study.expansion.json`, `experiment.yaml` |
| **Out of scope** | Running backtests; report; confirm enforcement (print count only) |
| **Regression** | Pure functions; no CLI default changes; no `run_batch` edits |
| **Acceptance checklist** | |
| | ✅ Golden expansion fixture: byte-stable experiment YAML + factor_map JSON |
| | ✅ Every expanded run passes `validate_run_spec` |
| | ✅ Anchor cells set `selected_levels=[]`, `anchor_level=core`, required partner rules |
| | ✅ Global cells set `selected_levels=[core]+partners` with min=max=len and len≤5 |
| | ✅ Run names unique and match `_RUN_NAME_RE` |
| | ✅ Stage `filter` reduces cartesian product correctly (example: 800 → 40) |
| | ✅ Stage `explicit_cells` expands exactly the listed cells (no cartesian leakage) |
| | ✅ No bare `grid`/`validation`/`walk_forward` `{}`; enabled false by default |
| | ✅ `tests/study/` green; no engine golden-master regeneration |
| | ✅ OTF alias/canonical duplicates, partner dupes/core-overlap, missing cell axes / backtest fail closed |

**Copy-ready agent prompt:**

```text
Implement RS2 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS2.
Add expand.py + naming.py. Deterministic StudySpec→R18 experiment expansion with factor_map.
Follow §6.2–§6.3 (anchor selected_levels=[], global min=max=len≤5, setup injects, OTF canonicalize,
enabled:false emission, filter + explicit_cells). Golden-test expansion. Every run must pass validate_run_spec.
No backtest execution. No engine/pages/run_batch changes. Docs + roadmap. §4.2.
```

---

### RS3 — CLI `study expand` + `study run` (study-owned execute + ledger)

| | |
|---|---|
| **Scope** | `cli_study.py`; wire `study` subcommands in `cli.py`/`__main__.py`; `execute.py`; `ledger.py`; additive `"study"` in `EXECUTION_ORIGINS`; tests for confirm gate + ledger + partial failure + soft resume + workers=1/N |
| **Behavior** | `expand` writes artifacts + cost hints; `run` expands (if needed), enforces confirm policy, **study-owned cell loop** (`run_experiment` + `build_research_bundle` + incremental index/ledger) with §5.3.8–§5.3.10 provenance/workers/resume locks; preserves R18 bundle layout under study `output_dir`; keeps emitting `experiment.yaml` for replay; failed cell recorded in ledger; remaining cells continue |
| **Out of scope** | Changing `run_batch` semantics; overview Markdown intelligence; assistant tools; job cancel UX |
| **Regression** | `python -m thesistester run` path must remain behavior-identical (additive subparser only; `run_batch` untouched); `EXECUTION_ORIGINS` change is additive membership only |
| **Acceptance checklist** | |
| | ✅ `study expand` writes the three artifacts and prints run_count (+ cost hints) |
| | ✅ `study run` without `--confirm` fails when run_count ≥ confirm_above_runs |
| | ✅ `study run --confirm` executes; ledger marks ok/failed per cell; `execution_origin=study` |
| | ✅ One failing cell leaves prior ok bundles/index rows intact; failure surfaced in ledger |
| | ✅ Soft resume skips ledger `ok` cells only when bundle zip exists; `--force` re-runs; identity mismatch refuses without `--force` |
| | ✅ Confirm/identity gates refuse **before** rewriting expansion artifacts |
| | ✅ `--force` identity swap replaces ledger (no orphan cells / exit-code poison) |
| | ✅ `workers>1` continues on per-cell failure (return payloads, not pool-wide raise); pool death → cell `failed` |
| | ✅ Index columns parity-tested vs `cli._execute_run` (+ study `status`) |
| | ✅ `run_batch` / `thesistester run` tests unchanged and green |
| | ✅ Warn when any cell enables grid/validation/walk_forward |
| | ✅ AGENT_GUIDE headless section gains Study Runner pointer; ARCHITECTURE boundary note |
| | ✅ `tests/study/` + CLI smoke green |

**Note on failure semantics:** RS3 must **not** change `run_batch` to continue-on-failure. Study execute owns continue-capable accounting. Optional later R18 additive flag remains RS-D3.

**Copy-ready agent prompt:**

```text
Implement RS3 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS3 and §5.3.8–§5.3.10.
Wire `python -m thesistester study expand|run`. Implement study-owned execute loop
(reuse run_experiment + build_research_bundle composition like cli._execute_run).
Do NOT call run_batch for ledgered runs; do NOT change run_batch defaults/semantics.
Add "study" to EXECUTION_ORIGINS only (additive). Enforce confirm_above_runs + cost hints.
Ledger with per-cell ok/failed; soft resume + --force; workers return ok/failed payloads.
Index-row key parity vs cli._execute_run. Update AGENT_GUIDE + STUDY_RUNNER.md + ARCHITECTURE + roadmap.
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
| | ✅ Overview join is deterministic and complete for fixture |
| | ✅ Cells below min_trades excluded from “ranked” section but listed under low-N |
| | ✅ OTF delta rows correct vs baseline factor (alias-stable) |
| | ✅ Markdown includes multiple-testing honesty paragraph |
| | ✅ Glossary entries for study overview metrics / OTF Δ |
| | ✅ PF available in overview when bundles present (document source) |
| | ✅ Full suite green |

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
| | ✅ Promote writes draft StudySpec; does not execute |
| | ✅ Example YAML expands to 40 cells with stage filter; full 800 documented as phase-2 |
| | ✅ Tiny CI subset fixture still used for unit/golden (2×2×2) |
| | ✅ USER_GUIDE / STUDY_RUNNER end-to-end recipe |
| | ✅ Core series RS1–RS5 marked implemented on roadmap after green CI |
| | ✅ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS5 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS5.
Add survivor promotion draft helper + examples/studies (stage-first 40-cell default,
full 800 as phase-2 comment) + docs polish.
No auto-execution. No engine/pages. HC allowlist update if USER_GUIDE gains Help content.
§4.2. Mark RS1–RS5 complete on roadmap only when acceptance passes.
```

---

### RS6 — Optional assistant study capabilities — **opt-in, after RS-D7**

Full contract: **§12.3**. Brief scope retained here for §11 continuity.

| | |
|---|---|
| **Scope** | Default-off `STUDY.*` `FEATURE_PARITY_REGISTRY` capabilities wrapping expand/run/report/promote; minimal CLI/confirm recipe docs |
| **Out of scope** | Greenfield MCP server; free-form study invention; Grok Bot product host; Streamlit Studies page (RS-D2) |

**Copy-ready agent prompt:** see §12.3.

---

## 12. Post-MVP expansion series (plan-locked sequence)

### 12.0 Sequencing rules (normative)

Post-MVP work **must** follow this order unless this plan is amended in the same PR that reorders. **No escape hatches** that silently reorder milestones.

```text
RS-D7  →  RS6  →  RS-D2  →  RS-D4  →  RS-D5
  │         │        │         │         └─ external Grok routine pack (docs + recipes)
  │         │        │         └─ per-cell diagnostic rollup (compose existing artifacts only)
  │         │        └─ Streamlit Studies viewer (artifacts-only; no in-app execute)
  │         └─ default-off STUDY.* assistant capabilities + minimal CLI/confirm docs
  └─ additive results_index profit_factor + win_rate (default-compatible)
```

| Rule | Rationale |
|---|---|
| **RS-D7 first** | Tiny additive index win; unblocks PF/WR for agents + viewer without zip scrape; report already prefers index |
| **RS6 after D7** | Assistant wrappers then see a PF-complete index; still one confirm-gated headless contract (no second runner) |
| **RS-D2 viewer-only** | Classic Streamlit stays undisturbed; no StudySpec builder / in-app `study run` in D2 |
| **RS-D4 after survivors-in-use** | Rollup honesty matters once promote workflows exist; compose-only; most MVP cells have batteries off |
| **RS-D5 after RS6** | External coworker consumes frozen CLI + optional STUDY.* tools; not an embedded host |
| **Parked ≠ cancelled** | RS-D1 / RS-D3 / RS-D6 stay available when a concrete need appears; not on the critical path |

**Global regression posture (every post-MVP PR):**

- Satisfy `ENGINEERING_PROPOSAL.md` §4.2.
- **No** `thesistester/engine/` edits; **no** fill/signal/confluence-math changes; **no** golden-master regeneration (none in this series).
- Classic `python -m thesistester run` / `run_batch` abort+write semantics unchanged (study layer remains continue-capable).
- Allow-list non-`study/` touches: RS-D7 may extend `cli.py` `_execute_run` index keys; RS6 may register default-off assistant capabilities/config; RS-D2 may add one read-only page + HC allowlist.
- Assistant Help/Discuss defaults unchanged when RS6 flag is off.
- Docs + tests land in the same PR as code; roadmap/status rows updated same PR.
- Prefer additive modules under `thesistester/study/` (and thin page/assistant wrappers only where listed).

### 12.1 Milestone index

| Order | ID | One-line intent | Pages? | Engine? | Default |
|---|---|---|---|---|---|
| 1 | RS-D7 | Additive index `profit_factor` + `win_rate` | No | No | Additive columns |
| 2 | RS6 | Default-off `STUDY.*` assistant capabilities + minimal CLI/confirm docs | No | No | **Off** |
| 3 | RS-D2 | Studies viewer over artifacts | **Yes (viewer only)** | No | Read-only page |
| 4 | RS-D4 | Per-cell WFA/validation/overfitting diagnostic rollup | No | No | Opt-in CLI/report |
| 5 | RS-D5 | External Grok routine pack | No | No | External docs |
| — | D1/D3/D6 | Parked | — | — | — |

---

### 12.2 RS-D7 — Additive index columns (`profit_factor`, `win_rate`) — **NEXT**

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅ |
| **Scope** | Additive **`profit_factor` and `win_rate`** columns on study-authored and CLI `results_index.csv` writers; report prefers index when present (already implemented in `report._resolve_bundle_metrics`) |
| **Likely files** | `thesistester/study/execute.py` (`R18_INDEX_METRIC_KEYS` / `STUDY_INDEX_KEYS` / `build_index_row_from_state` / `_index_row_from_existing_bundle`); `thesistester/cli.py` `_execute_run` index row (parity); index parity tests; `docs/METRICS_GLOSSARY.md` / `STUDY_RUNNER.md` |
| **Column order (locked)** | Insert both keys on `R18_INDEX_METRIC_KEYS` **immediately after** `max_drawdown_r` (with the other trade-summary metrics), before grid/validation/WFA keys. Keep study `bundle_path` + `status` as the only study-only suffixes on `STUDY_INDEX_KEYS`. |
| **Behavior** | |
| | For **ok** cells, write both columns from `trade_summary` at index-write time (`build_index_row_from_state` + CLI `_execute_run`) |
| | Failed/pending rows: leave `profit_factor` / `win_rate` **null** (never fabricate) |
| | **Soft-resume rehydration:** `_index_row_from_existing_bundle` must also copy `profit_factor` + `win_rate` from bundle `trade_summary` (today it only rehydrates trade_count/expectancy/total/max_dd) — otherwise resumed ok rows stay PF-null and report falls back to zip scrape |
| | CSV serialization: finite floats as usual; `±inf` PF as `"inf"` / `"-inf"` strings (report already coerces these) |
| | **Default-compatible:** older indexes / readers without the columns still work; report keeps bundle fallback |
| | Do **not** bump Experiment `schema_version` solely for this; document as additive index column set |
| | Parity: study execute keys and CLI `_execute_run` keys stay aligned (extend parity test); do not change `run_batch` write timing |
| **Out of scope** | Engine metric formula changes; silent removal of bundle PF path; Studies UI; assistant tools; inventing `win_rate_source` column (report may keep PF-only source tracking) |
| **Regression** | Existing CLI/study index consumers tolerate new columns; no golden engine regen |
| **Acceptance checklist** | |
| | ☐ New ok cells write both `profit_factor` and `win_rate` on `results_index.csv` |
| | ☐ Failed/pending rows keep null PF/WR |
| | ☐ Soft-resume rehydration populates PF/WR from existing bundles |
| | ☐ Report `profit_factor_source=index` when column present and finite/coercible |
| | ☐ Bundle fallback still works when column absent/null |
| | ☐ CLI ↔ study index key parity test updated and green (`R18_INDEX_METRIC_KEYS` extended after `max_drawdown_r`) |
| | ☐ Docs note additive columns + `inf` CSV behavior; no claim of R18 schema break |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D7 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.2.
Add additive profit_factor AND win_rate to study and CLI results_index writers
from trade_summary (insert on R18_INDEX_METRIC_KEYS immediately after
max_drawdown_r). Null on failed/pending. Soft-resume rehydration
(_index_row_from_existing_bundle) must also copy PF/WR. Serialize ±inf as
inf/-inf strings. Keep report bundle fallback. Extend index parity tests.
No engine/pages. No run_batch semantic/timing change. §4.2.
Update STUDY_RUNNER + glossary.
```

---

### 12.3 RS6 — Default-off `STUDY.*` assistant capabilities

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅; **RS-D7** (so tool/index consumers see PF/WR without zip scrape) |
| **Scope** | Thin adapters over existing `thesistester.study` APIs registered in `FEATURE_PARITY_REGISTRY` behind default-off **`[assistant.study_tools] enabled=false`** (fail-closed coerce, same pattern as `[assistant.voice]`); minimal operator docs for external Grok Bot CLI/confirm recipe |
| **Likely files** | `thesistester/study/tools.py`; `thesistester/assistant/registry.py` (+ typed handlers / orchestrator wiring); `config/assistant.toml` `[assistant.study_tools]`; settings loader with fail-closed coerce; `docs/STUDY_RUNNER.md` agent section; `docs/AGENT_GUIDE.md`; `tests/study/` + assistant parity fixtures |
| **Primary surface (locked)** | Assistant capabilities (mirror `PIPELINE.run_experiment` pattern), **not** a greenfield MCP server. Optional: document-only MCP-shaped descriptor appendix for external hosts — **no in-repo MCP runtime** in RS6. Voice/realtime must continue to deny MCP/search. |
| **Capabilities (IDs locked)** | `STUDY.expand`, `STUDY.run`, `STUDY.report`, `STUDY.promote` |
| **Capability modes (locked)** | `expand` / `report` → `EXECUTABLE` or `INSPECT_ONLY` as appropriate for side effects; `run` / `promote` → `EXECUTABLE`. Do **not** invent a new `ConfirmationLevel` enum member. |
| **Confirm nomenclature (locked)** | `STUDY.run` uses `ConfirmationLevel.EXPLICIT_CONFIRMATION`. First gated dispatch returns orchestrator status **`OrchestrationStatus.APPROVAL_REQUIRED`** (existing enum — not a ConfirmationLevel). Retry only after explicit `confirmed=True` (or equivalent UI confirm boundary) with a bound approval payload. |
| **Behavior** | |
| | Inputs: StudySpec path **or** structured dict that must pass `validate_study_spec` before any side effect; `output_dir`; `workers`; promote `top_n` / `metric` / overwrite `force`; run `force` (identity/resume parity with CLI) |
| | Soft resume / identity mismatch / `--force` semantics **must** match `run_study` CLI — tools must not invent weaker gates |
| | Promote overwrite gate matches CLI (`force` required to replace existing draft) |
| | **Confirm parity (two-step):** when `run_count >= confirm_above_runs`, `STUDY.run` must **not** treat a bare habitual boolean as sufficient. Gate with `EXPLICIT_CONFIRMATION` → `APPROVAL_REQUIRED`, then confirmed retry. Approval payload **must** bind `(study_identity_hash, run_count, output_dir)` and `STUDY.run` must refuse if the bound triple does not match the current expansion/target. Below threshold, run may proceed without that gate (CLI parity). Expand/report/promote never require confirm. |
| | Optional helper capability `STUDY.confirm` is allowed only if it mints/records that bound approval — it must not execute cells. |
| | Return structured payloads: `run_count`, cost hints, artifact paths, ledger summary, honesty flags — not free-form “winner” claims |
| | When flag is off: capabilities unregistered **or** every STUDY.* handler refuses with clear “disabled” error; default assistant path identical to pre-RS6 (parity fixtures) |
| | Tools call `expand_study` / `run_study` / `report_study` / `promote_study` — **never** `run_batch` |
| **Docs split** | RS6 lands a **minimal** “CLI + confirm recipe” section. Full multi-step Grok routine pack is **RS-D5** only — do not duplicate divergent long recipes here. |
| **Out of scope** | NL StudySpec compilation (RS-D1); Streamlit Studies page (RS-D2); embedding Grok/RabbitMQ; inventing setups; enabling tools by default; shipping a live MCP server; new ConfirmationLevel values |
| **Regression** | Assistant parity fixtures green with flag off; Help/Discuss unchanged; engine/pages untouched; CLI study commands unchanged |
| **Acceptance checklist** | |
| | ☐ `[assistant.study_tools] enabled` defaults to **false** (fail-closed coerce) |
| | ☐ With flag off, assistant surfaces behave as before RS6 (parity fixtures) |
| | ☐ With flag on, expand/report/promote work without confirm; run uses two-step `EXPLICIT_CONFIRMATION` → `APPROVAL_REQUIRED` when over threshold |
| | ☐ Bound approval triple enforced; lone boolean cannot bypass |
| | ☐ Structured-dict inputs validate via `validate_study_spec` before writes/execute |
| | ☐ `force` / workers / soft-resume / identity mismatch match CLI `run_study` / `promote` |
| | ☐ Tools do not call `run_batch` |
| | ☐ Minimal CLI/confirm recipe docs (RS-D5 owns the full routine pack) |
| | ☐ Full suite + assistant parity green |

**Copy-ready agent prompt:**

```text
Implement RS6 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.3.
Add default-off [assistant.study_tools] + STUDY.* FEATURE_PARITY_REGISTRY
capabilities wrapping expand/run/report/promote. STUDY.run uses
ConfirmationLevel.EXPLICIT_CONFIRMATION; gated calls return
OrchestrationStatus.APPROVAL_REQUIRED; confirmed retry requires approval bound to
(study_identity_hash, run_count, output_dir). No new ConfirmationLevel members.
No MCP server runtime. Match CLI force/workers/resume/promote overwrite.
No engine/pages/run_batch changes. Keep assistant parity fixtures green when flag
off. §4.2. Update STUDY_RUNNER.md (minimal agent recipe) + roadmap.
```

---

### 12.4 RS-D2 — Streamlit Studies viewer (artifacts-only)

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅; **RS-D7** (PF/WR on index); RS6 optional |
| **Scope** | One new Streamlit page that **reads** an existing study output directory and displays ledger + overview artifacts |
| **Likely files** | `pages/15_Studies.py` (or next free nav slot matching repo convention); thin helpers reusing `report_study` / ledger loaders — **do not reimplement** join/rank; `docs/USER_GUIDE.md` H2 + HC §7.1.4 allowlist amend; `ARCHITECTURE.md` boundary note |
| **Behavior** | |
| | User selects / pastes a study `output_dir` (sandbox/path-validate; refuse arbitrary filesystem traversal outside intended roots if the app already has a path policy — otherwise document trusted-local-path assumption) |
| | Show: study identity, run_count, ledger ok/failed/pending, ranked table, low-N, unresolved, OTF Δ summary, `bundle_path` strings |
| | Honesty banner: descriptive ranking ≠ validated edge; multiple-testing; min_trades |
| | Optional: download / show `study.overview.md` / CSV text. **Do not** promise Research-Bundles deep-link-by-path (that page is upload/import oriented); listing `bundle_path` is enough |
| | **Read-only:** no StudySpec editor; no in-app expand / run / promote; must **not** mutate classic research `st.session_state` keys (levels/signals/trades/etc.) |
| **Out of scope** | Factor builder UI; templates marketplace; auto-run; assistant NL; changing headless CLI; portfolio of studies cloud sync |
| **Regression** | Classic pages unchanged in behavior; no engine edits; Help allowlist updated if USER_GUIDE gains H2; nav addition must not break existing page tests |
| **Acceptance checklist** | |
| | ☐ Can load a completed fixture study dir and show ranked/low-N/ledger without running backtests |
| | ☐ Reuses study report/ledger loaders (no divergent ranking logic) |
| | ☐ Honesty caveats visible |
| | ☐ No execute/promote/expand controls that mutate study or research session state |
| | ☐ USER_GUIDE (+ HC §7.1.4 if Help-readable) updated same PR |
| | ☐ Existing Streamlit/assistant tests green; engine goldens untouched |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D2 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.4.
Add a thin Streamlit Studies viewer over existing study artifacts (ledger + overview).
Reuse report_study/ledger loaders. Read-only: no in-app expand/run/promote; do not
mutate research session_state. Honesty banner required. Show bundle_path; no false
deep-link. HC allowlist if USER_GUIDE H2 added. No engine edits. §4.2.
```

---

### 12.5 RS-D4 — Per-cell diagnostic rollup (WFA / validation / overfitting)

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅; meaningful after survivors exist (promote workflow); RS-D2 optional |
| **Scope** | Aggregate **existing** per-cell walk-forward / validation / overfitting diagnostics into study-level summary tables — **compose, do not invent** |
| **Likely files** | `thesistester/study/rollup.py`; CLI `study rollup` and/or report subsection; honesty docs in `ASSUMPTIONS_AND_LIMITATIONS.md` + `STUDY_RUNNER.md` |
| **Semantics (locked)** | |
| | Rollup is a **per-cell table** of fields already present on cell bundles/index — **not** a new cross-study / cross-cell PBO, DSR, or CSCV |
| | Read bundle members such as `walk_forward_summary` / WFA fields already on study index, and `overfitting_summary.json` when present |
| | R15 `overfitting_summary` / `cscv_pbo` require **grid cell trade sequences**. Default study emission keeps `grid`/`validation`/`walk_forward` `enabled: false`, so most MVP cells are `not_run` for these fields — that is expected |
| | Missing batteries → explicit `not_run` / null columns; **never** silently enable grid/validation/walk_forward |
| | Explicit honesty: descriptive rollup ≠ validated edge; refuse “proof of edge” language |
| **Recommended survivor-stage constants** (docs + examples only; not auto-applied): after promote, humans may opt into `walk_forward.enabled: true` and/or `grid.enabled: true` + `validation.overfitting` **with explicit `enabled` flags** (never bare `{}`) before expecting rollup density |
| **Out of scope** | New PBO/DSR algorithm; study-level pooled PBO across factorial cells; auto-enabling batteries on promote/report; changing analytics formulas; engine changes |
| **Regression** | Enabling rollup never changes cell backtest results; classic validation pages unchanged |
| **Acceptance checklist** | |
| | ☐ Rollup reads existing cell artifacts / index WFA columns only |
| | ☐ Missing batteries → explicit null/not_run, not invented scores |
| | ☐ No cross-cell PBO/DSR computation |
| | ☐ Honesty block in MD |
| | ☐ Docs state grid requirement for overfitting fields + survivor opt-in recipe |
| | ☐ No engine/pages golden drift |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D4 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.5.
Add study-level per-cell diagnostic rollup composing existing WFA/validation/
overfitting bundle/index fields. Do NOT invent cross-cell PBO/DSR or auto-enable
batteries. Missing → not_run/null. Honesty required. No engine golden changes. §4.2.
Update STUDY_RUNNER + assumptions (incl. grid requirement for overfitting).
```

---

### 12.6 RS-D5 — Grok Bot routine pack (external)

| | |
|---|---|
| **Depends on** | **RS6** (minimal CLI/confirm docs + optional STUDY.* tools); benefits from RS-D7 index PF |
| **Scope** | **Documentation + example agent routines** for an external coworker (Grok Bot). Prefer living outside the product runtime; in-repo only as docs/examples under `docs/` or `examples/studies/agents/` |
| **Docs split** | Owns the **full** multi-step routine pack. Must not contradict RS6’s minimal recipe; extend it. |
| **Behavior** | |
| | Recipe: stage-first expand → two-step confirm when required → run → report → promote draft → human edit → second pass (optionally enable WFA/grid on survivors before RS-D4 rollup) |
| | Hard rules: never invent factor axes; never bypass confirm; never auto-run promote drafts; always surface honesty / min_trades / multiple-testing |
| | May shell CLI even if `assistant.study_tools.enabled` is off |
| **Out of scope** | Embedding Grok in ThesisTester; RabbitMQ; multi-agent host; product UI for bot orchestration; shipping MCP server |
| **Acceptance checklist** | |
| | ☐ Documented routine pack with copy-ready prompts/commands |
| | ☐ Explicit non-goals: no setup invention, no confirm bypass, no auto-promote execute |
| | ☐ Points at RS6 default-off flag + CLI fallback; references RS-D7 index PF |
| | ☐ No runtime default changes |

**Copy-ready agent prompt:**

```text
Implement RS-D5 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.6.
Add external Grok Bot routine-pack documentation/examples consuming study CLI
and optional STUDY.* tools. Extend (do not fork) RS6 minimal recipe.
No product host embedding. No MCP server. No engine/pages. No default-on tools. §4.2.
```

---

### 12.7 Parked (available, not sequenced)

| ID | Item | When to reopen | Constraints |
|---|---|---|---|
| **RS-D1** | NL → StudySpec compiler | After RS6 when agent drafting is a real bottleneck | LLM may draft YAML only; **validate + human confirm** before any run; never execute unchecked NL |
| **RS-D3** | `run_batch` continue-on-failure | Only if R18 replay parity with study ledger is required | Additive flag; default abort/write semantics stay identical |
| **RS-D6** | Multi-partner clusters / tolerance sweeps | When a concrete study needs new factor types | `schema_version` bump; golden expand fixtures; no engine changes |

Still **non-goals:** auto-promote to live thesis without human confirm; scheduled study daemon; UI factor marketplace; merging with confluence-combo attribution; greenfield in-product MCP server.

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
# Phase 2: remove/widen stage on this unpromoted example (full factor domains).
# Do not drop stage from a study-promote draft and expect 800 — promote narrows
# factors to survivor values. Full cartesian for §6.1 factors = 800 cells.
```

Recommended human workflow (MVP — available now):

1. Stage filter expand/run/report (40 cells).  
2. Promote survivors (`explicit_cells` draft).  
3. Optionally restore/open selected axes on the draft (or on the unpromoted example for full 800).  
4. Interpret OTF Δ with multiple-testing caution.  
5. Prefer non-zero `commission_per_side` / `slippage_ticks` before trusting expectancy ranks.

Recommended workflow after post-MVP sequence (§12):

6. (RS-D7) Prefer index `profit_factor` / `win_rate` when present.  
7. (RS6) Optional default-off `STUDY.*` tools for the same CLI contract — two-step confirm when over threshold.  
8. (RS-D2) Inspect study dirs in the Studies viewer (read-only).  
9. (RS-D4) Roll up per-cell WFA/validation/overfitting diagnostics only where batteries actually ran (opt-in on survivor stage).  
10. (RS-D5) External Grok Bot follows the documented routine pack — never invents axes.

---

## 14. Documentation plan

| Doc | When | Change |
|---|---|---|
| `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | RS0 / post-MVP lock | This plan; status updates per PR |
| `STUDY_RUNNER.md` | RS1–RS5 ✅; each post-MVP PR | Living operator contract |
| `ENGINEERING_ROADMAP.md` | each PR | RS status row + post-MVP sequence |
| `AGENT_GUIDE.md` | RS3 ✅; RS6 | Headless study commands + `study_tools` flag |
| `ARCHITECTURE.md` | RS3 ✅; RS-D2 | Boundary notes (study module; Studies viewer) |
| `ASSUMPTIONS_AND_LIMITATIONS.md` | RS4 ✅; RS-D4 | Study ranking / rollup honesty |
| `METRICS_GLOSSARY.md` | RS4 ✅; RS-D7 | Overview / index PF + WR columns |
| `USER_GUIDE.md` | RS5 ✅; RS-D2 | Studies viewer how-to (HC allowlist) |
| `README.md` (root) | RS5 ✅ | One-liner pointer |
| Grok docs | RS6 minimal recipe; **RS-D5** full pack | External agent recipes (no divergent forks) |
| `CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` | RS0 pointer only | Keep separate; no edits required for RS |

---

## 15. Risk register

| Risk | Mitigation |
|---|---|
| Combinatorial fishing / overfitting | confirm gates; stage-first examples; honesty blocks; no auto-promote |
| Accidental engine edits in agent PRs | PR allow-list in prompts; CI golden gate |
| Factor tags stuffed into RunSpec/setup | External factor_map only; run-level unknown keys fail; setup strips unknowns |
| Assuming `run_batch` supports per-cell failure | Study-owned execute loop; `run_batch` left all-or-nothing (RS-D3 parked) |
| Silent default-on grid/validation | Expander always emits `enabled: false` unless StudySpec enables; never bare `{}` |
| PF/WR missing from R18 index | Study ledger status; PF from bundle; **RS-D7** additive index columns (both required) |
| OTF alias forks in Δ grouping | Canonicalize to `5m`/`15m`/`30m` in factor_map |
| Worker pool aborts entire study on one raise | Tasks return ok/failed payloads; ledger continues |
| Re-run destroys completed work / identity drift | Soft resume + study identity hash + `--force` |
| `execution_origin=study` → `unknown` | Additive `EXECUTION_ORIGINS` membership in RS3 |
| Index column drift vs CLI | Parity test vs `_execute_run` keys (extend in RS-D7) |
| Help corpus drift | HC allowlist PR when USER_GUIDE changes (RS5, RS-D2) |
| Naming collisions / invalid run names | `_RUN_NAME_RE` + output_dir isolation |
| Merging study factorial with combo attribution | Explicit §3.4 boundary; separate docs |
| Treating study emission rules as R18 validator law | Docs call out study-only rules (`min=max=len`, anchor `selected_levels=[]`) |
| Agent tools silently enable large runs | **RS6 default-off**; two-step `EXPLICIT_CONFIRMATION`; parity fixtures |
| Bare `confirm=true` habitually set by LLMs | Approval bound to `(study_identity_hash, run_count, output_dir)` |
| Greenfield MCP runtime / voice MCP bleed | RS6 = registry capabilities only; voice keeps MCP denied |
| Studies UI becomes a second runner | **RS-D2 read-only** — no in-app expand/run/promote; no session mutation |
| Grok invents setups / bypasses confirm | **RS-D5** hard rules + RS6 minimal recipe; closed StudySpec only |
| Rollup invents cross-cell PBO / statistical proof | **RS-D4** per-cell compose-only; null/`not_run` when batteries absent |
| Expecting PBO on default study cells | Docs: overfitting needs grid sequences; survivor opt-in |
| Post-MVP scope creep / reordering | §12.0 sequence lock (no escape hatches); parked D1/D3/D6 |

---

## 16. Definition of done

### 16.1 Core series RS1–RS5 (holistic MVP) — ✅ complete when merged

1. Researcher can author a closed StudySpec and run `study expand|run|report` (+ `promote`) without opening Streamlit.  
2. Expansion is deterministic and golden-tested; stage filter and `explicit_cells` both work; example stage path is 40 cells, full example cartesian is 800.  
3. Large studies require `--confirm`; cost hints warn on enabled batteries.  
4. Study execute continues after cell failure, supports soft resume/`--force`, uses `execution_origin=study`, and does not alter `run_batch`.  
5. Overview joins factors to metrics with OTF Δ and honesty caveats; PF sourced per §9.2.  
6. Classic UI, assistant defaults, engine goldens, and `thesistester run` / `run_batch` remain undisturbed.  
7. External bot can operate by shelling the CLI; first-class `STUDY.*` assistant capabilities remain optional RS6 (after RS-D7).

### 16.2 Post-MVP track — done when §12 sequenced milestones pass their checklists

1. **RS-D7:** additive index `profit_factor` + `win_rate`; report prefers index; CLI↔study parity; `inf` CSV documented.  
2. **RS6:** default-off `STUDY.*` capabilities; two-step confirm; minimal CLI recipe; assistant defaults unchanged when off; no MCP server.  
3. **RS-D2:** read-only Studies viewer over artifacts; honesty visible; no session mutation; HC allowlist if USER_GUIDE grows.  
4. **RS-D4:** per-cell compose-only diagnostic rollup; no cross-cell PBO; null/`not_run` when batteries absent.  
5. **RS-D5:** external routine pack documented; no product host embedding.  
6. Parked items (D1/D3/D6) remain out of critical path unless this plan is amended.

---

## 17. Status tracker

| Milestone | Status |
|---|---|
| RS0 Plan lock | ✅ |
| RS1 Schema | ✅ |
| RS2 Expander | ✅ |
| RS3 CLI expand/run + study-owned ledger | ✅ |
| RS4 Report | ✅ |
| RS5 Staging/promote + examples | ✅ |
| **Post-MVP sequence lock** | ✅ This amendment (§12) |
| RS-D7 Additive index PF + win_rate | ☐ **Next** |
| RS6 Default-off `STUDY.*` assistant capabilities | ☐ After RS-D7 |
| RS-D2 Studies viewer (read-only) | ☐ After RS-D7 |
| RS-D4 Per-cell diagnostic rollup | ☐ After survivors-in-use |
| RS-D5 Grok Bot routine pack | ☐ After RS6 |
| RS-D1 / RS-D3 / RS-D6 | Parked (§12.7) |

---

## 18. Review amendments (changelog)

### 18.1 R18 contract accuracy (prior amendment)

1. Example cartesian count **800** (stage-first **40**), not “1–2k”.
2. Study execution is a **study-owned loop** over `run_experiment` + bundle write; `run_batch` remains all-or-nothing and unchanged.
3. `results_index` does not currently include `profit_factor` / `status` — report/ledger sources specified; optional RS-D7.
4. `grid`/`validation`/`walk_forward` emission must set `enabled: false` explicitly (default-on trap is bare `{}` / omitted `enabled`; omit-section is safe but expander still emits false).
5. Anchor cells emit `selected_levels: []` (study rule; R18 does not hard-fail otherwise); global cells force `min=max=len(selected_levels)` with hard cap 5 (study rule on top of R18 `max≤5`).
6. Expander injects `setup.name` / `instrument` / `description` every cell.
7. Setup unknown-key behavior is strip-not-fail; factor tags stay in study artifacts only.
8. Canonical OTF tokens in factor_map; partner/core closed-set validation; `_RUN_NAME_RE` naming.
9. Constants surface documents day-trading pass-throughs (costs, session exits, entry_window, intrabar).
10. Stage-first examples; confirm cost hints; combo-attribution boundary.

### 18.2 MVP completeness pass (prior amendment)

11. §2.1 MVP in/out table — RS1–RS5 = holistic MVP; RS6/RS-D\* post-MVP.
12. Soft resume + `--force` + study identity mismatch refuse locked in §5.3.10 (MVP, not deferred ops).
13. Workers return ok/failed payloads; incremental ledger under pool (§5.3.9).
14. `execution_origin="study"` + additive `EXECUTION_ORIGINS` membership (§5.3.8); `cache_policy=read_write`.
15. Normative `explicit_cells.cells[]` shape (§6.3); RS2 expands it; RS1 validates it.
16. Index-row parity vs `cli._execute_run` without forcing a risky CLI refactor (§6.2.13).
17. Definition of done / risks / RS3 acceptance updated for resume, workers, provenance.
18. Clarified study emission rules vs R18 validator law (anchor `[]`, `min=max=len`).

### 18.3 Post-MVP sequence lock (prior amendment)

19. Header/status: RS1–RS5 complete; post-MVP track plan-locked.  
20. §2.1 rewritten: sequenced vs parked columns.  
21. §12 replaced thin deferred table with full milestone contracts + §12.7 parked (D1/D3/D6).  
22. Each sequenced milestone has scope, likely files, behavior locks, out-of-scope, regression gates, acceptance checklist, copy-ready agent prompt.  
23. RS-D2 locked **read-only** (no in-app runner). RS6 locked **default-off**. RS-D4 locked **compose-only**. RS-D5 locked **external**.  
24. Docs plan, risks, definition of done (§16.2), and status tracker updated for the post-MVP track.

### 18.4 Post-MVP review contracts (this amendment)

25. Sequence swapped to **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5**; removed “D7 may land before RS6” escape hatch.  
26. RS6 = `FEATURE_PARITY_REGISTRY` `STUDY.*` capabilities + default-off flag; **no greenfield MCP server** (docs-only descriptor appendix at most; voice MCP stays denied).  
27. RS6 confirm = two-step `EXPLICIT_CONFIRMATION` / approval bound to `(study_identity_hash, run_count, output_dir)` — not bare `confirm=true`.  
28. RS6 tool parity: `force` / workers / soft-resume / identity mismatch / promote overwrite; structured dicts must `validate_study_spec` first.  
29. RS-D7 locks **both** `profit_factor` and `win_rate`; null on failed/pending; `±inf` CSV strings; extends `R18_INDEX_METRIC_KEYS`.  
30. RS-D2: reuse report/ledger loaders; no research `session_state` mutation; `bundle_path` listing not false Research-Bundles deep-link; path sandbox note.  
31. RS-D4 renamed/clarified as **per-cell diagnostic rollup** — no cross-cell PBO/DSR; overfitting fields require grid sequences; survivor opt-in recipe documented.  
32. RS6 vs RS-D5 docs split (minimal recipe vs full routine pack).  
33. §5.1/§5.2 updated for shipped MVP + post-MVP `tools.py` / `rollup.py` / Studies page.  
