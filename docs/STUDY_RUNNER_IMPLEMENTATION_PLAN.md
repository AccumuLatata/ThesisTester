# Research Study Runner — Implementation Plan (RS)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-11 (amended 2026-08-12: post-MVP sequence lock + review contracts + code-audit hardening + RS-D8 authoring-preview sequence + **RS-D9 CLI-launch sequence** + **RS-D9 review contracts**: pin both dataset keys, pinned-hash confirm, exclusive/portable pid; amended 2026-08-14: parked form-builder → separate **SB** series; amended 2026-08-16: Inspect catalog/visualization → separate **SV** series)  
**Status:** **RS1–RS5 + RS-D7 + RS6 + RS-D2 + RS-D4 + RS-D5 + RS-D8 + RS-D9 complete**. Parked: RS-D1 / RS-D3 / RS-D6. Study Builder UX: `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md` (SB1–SB3 ✅; not an RS PR). Study Viewer UX: `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV0 locked; not an RS PR)
**Series code:** **RS** (Research Study Runner)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Related living docs:** `docs/AGENT_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/otf-filter.md`, `docs/USER_GUIDE.md`, `docs/STUDY_RUNNER.md`, `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md` (SB — form compiler; does not change this series’ execute/preview/launch contracts), `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV — Inspect catalog/quality/charts/peek/briefing; does not change this series’ execute/preview/launch contracts), `docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md` (SAF — Admit follow-up drafts; does not change this series’ execute loop or RS5 “promote never executes”)  
**Related but separate:** `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` (within-trade level membership — **not** cross-setup factorial studies; do not merge concepts)  
**Depends on (already shipped):** R18 headless API + batch CLI (`thesistester/api.py`, `thesistester/cli.py`), RunSpec validation, research bundles, `results_index.csv`, Study Runner package `thesistester/study/`

**Supersedes:** conversational design notes about an autonomous research bot / Grok Bot coworker (those remain usage patterns; this plan is the product contract).

**Completeness posture:** RS1–RS5 is the **holistic MVP** (author → expand → confirm → execute with ledger/resume → report → promote). **§12** locks the post-MVP expansion sequence (index PF → default-off assistant capabilities → Studies viewer → per-cell diagnostic rollup → Grok routine pack → Studies authoring preview → **Studies CLI-launch button**). Parked items stay out of the critical path. Academic execute remains the headless CLI; RS-D9 is a control-plane spawn of that same CLI, not a second runner.

---

## 1. Purpose

Ship an **additive, headless Research Study Runner** so a researcher (or an external agent such as Grok Bot) can:

1. Declare a **closed multi-factor study** (e.g. pdPOC × MA partners × confluence modes × entries × OTF).
2. **Expand** that study into a deterministic R18 experiment YAML.
3. **Execute** unattended via existing `run_experiment` / bundle machinery (study-owned loop; see §5.3).
4. **Aggregate** results into an honest overview (ranked cells, factor effects, OTF ΔR, sample-size warnings).

The runner must remain **independent of Streamlit day-to-day research**: no engine, fill, or confluence-math changes in this series. Classic UI and assistant confirmation flows stay unchanged through MVP and through default-off RS6. The only planned page addition is the **read-only** RS-D2 Studies viewer; **RS-D8** extends that same page with a **preview-only** StudySpec authoring pane (validate + expand dry-run + ledger watch). **RS-D9** adds a **Confirm / Run via CLI** control on that same pane that **spawns** the existing `python -m thesistester study run` process — it must **not** call `run_study()` in-process, must **not** dispatch `STUDY.run`, and must **not** invent a second execute loop.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Research Study Runner |
| Package home | `thesistester/study/` (additive module; not a separate repo) |
| Primary surface | CLI: `python -m thesistester study {expand,run,report,promote,rollup}` |
| Compute core | Existing `run_experiment` + `build_research_bundle` (same path as CLI `_execute_run`); emit `experiment.yaml` for R18 replay |
| Engine / golden impact | **None** for RS1–RS5; RS-D7 may touch CLI index writers only (versioned, default-compatible) — still **no** `engine/` edits |
| Streamlit / pages impact | **None** for RS1–RS5 / RS-D7 / RS6; **RS-D2** adds a thin Studies viewer page; **RS-D8** extends that page with a preview-only authoring pane; **RS-D9** adds a CLI-spawn button on that same pane (same nav slot; still no in-process `run_study`) |
| Assistant impact | Optional **RS6** only: default-off `FEATURE_PARITY_REGISTRY` capabilities (`STUDY.*`); no greenfield MCP server |
| NL / LLM compiler | Parked (RS-D1); closed YAML StudySpec remains the contract. RS-D8 does **not** compile English or shorthand dialects |
| External Grok Bot | Out of repo product core; **RS6** documents minimal CLI/confirm recipe; **RS-D5** is the full external routine pack |
| Strategy generation | **Non-goal** (aligns with `ENGINEERING_PROPOSAL.md` §2.2) |
| MVP completeness bar | RS1–RS5 usable end-to-end without Streamlit, NL, or assistant study tools ✅ |
| Post-MVP sequence | **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5 → RS-D8 → RS-D9** (locked in §12); do not reorder without amending this plan |

**Feasibility:** High. R18 already runs independent RunSpecs and writes bundles + `results_index.csv`. MVP shipped study expansion + study-owned execution ledger + aggregation; post-MVP deepens agent/UI/rollup surfaces without new simulation semantics.

### 2.1 MVP in-scope vs explicitly deferred

| In MVP (RS1–RS5) ✅ | Post-MVP sequenced (§12) | Parked (not sequenced) |
|---|---|---|
| Closed StudySpec YAML + fail-closed validate | **RS-D7** additive index `profit_factor` + `win_rate` | **RS-D1** NL → StudySpec compiler |
| Deterministic expand + golden fixtures | **RS6** default-off `STUDY.*` assistant capabilities | **RS-D3** `run_batch` continue-on-failure |
| Confirm gate + cost hints | **RS-D2** Streamlit Studies **viewer** (artifacts-only) | **RS-D6** multi-partner / tolerance factor types |
| Study-owned execute + per-cell ledger | **RS-D4** per-cell WFA/validation/overfitting diagnostic rollup | Auto-run promotion / scheduled studies |
| Soft resume + workers + continue-on-failure (study layer) | **RS-D5** Grok Bot routine pack (external; after RS6) | Templates marketplace |
| Overview CSV/MD + OTF Δ + honesty | **RS-D8** Studies authoring preview (validate + expand dry-run + ledger watch) | Embedding Grok host / RabbitMQ / job queue / live MCP server |
| Stage filter + promote → `explicit_cells` draft | **RS-D9** Studies CLI-launch button (spawn existing `study run`; no in-process execute) | |
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
> sequenced gap after D8 is **RS-D9** (Studies page button that spawns the
> existing CLI `study run`). Parked: D1/D3/D6.

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
| Streamlit Study UI (MVP) | Headless-first; RS-D2 viewer + RS-D8 preview are post-MVP; RS-D9 is CLI-spawn only |
| In-process Streamlit `run_study` / `STUDY.run` from the Studies page | Confirm gates and ledgered execute stay in the CLI child (`cli_study._cmd_run` → `run_study`). The page must not become a second runner. **RS-D9** may spawn that CLI; it may not call `run_study()` on the Streamlit request |
| Promote-execute from the Studies page | Promote stays CLI/RS6; D9 does not add Promote |
| Job queue / scheduler / cancel daemon | Detached `Popen` (RS-D9) is a convenience spawn, not a queue. No retry/watchdog/kill UI |
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
│  + tools.py (RS6) + rollup.py (RS-D4) + preview.py (RS-D8)  │
│  + launch.py (RS-D9: argv + detached CLI spawn)            │
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
│ pages/: RS-D2 inspect; RS-D8 preview; RS-D9 CLI spawn (no in-process execute) │
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
  tools.py             # RS6: thin STUDY.* capability adapters (default-off) ✅
  rollup.py            # RS-D4: per-cell diagnostic rollup (compose-only) ✅
  viewer.py            # RS-D2: read-only Studies viewer helpers ✅
  preview.py           # RS-D8: validate + expand dry-run preview (no execute)
  launch.py            # RS-D9: argv builder + detached `study run` spawn (no execute import) ✅
docs/STUDY_RUNNER.md   # living operator contract ✅
tests/study/           # unit + golden expand fixtures ✅
examples/studies/      # stage-first example YAML ✅
pages/15_Studies.py    # RS-D2 inspect; RS-D8 preview; RS-D9 CLI-spawn (same nav slot)
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

**Note on `results_index.csv` columns (current writers, RS-D7):**  
R18/`cli._execute_run` + study `R18_INDEX_METRIC_KEYS`: `run_name`, `bundle_hash`, `dataset_id`, `instrument`, `execution_origin`, `cache_outcome`, `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, **`profit_factor`**, **`win_rate`**, `best_grid_*`, `validation_trade_count_status`, `wfa_*` (+ CLI/study `bundle_path`).  
Study-authored index also appends **`status`** (`ok`/`failed`/`pending`). Report still falls back to bundle `trade_summary` when PF/WR are absent/null (older indexes).

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

# Optional (RS-D4): compose per-cell WFA/validation/overfitting diagnostics
python -m thesistester study rollup out/study1
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
| `profit_factor` / `win_rate` | **RS-D7 ✅:** written on study + CLI `results_index` at ok-cell write time (after `max_drawdown_r`; null on failed/pending; soft-resume rehydrate + field backfill). Report prefers index per field; bundle fallback for older/null rows. |
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
| Pages | No edits | **RS-D2:** one read-only Studies viewer; **RS-D8:** same page, preview pane; **RS-D9:** same page, CLI-spawn controls (no in-process execute) |
| Defaults | `thesistester run` / `run_batch` identical | Same; RS6 tools **default-off** |
| Schema | StudySpec fail-closed | StudySpec unchanged unless parked D6; RS-D7 additive **index columns only** (no Experiment schema bump) |
| Docs / tests | Land same PR | Land same PR; HC allowlist if USER_GUIDE H2 added (D2, D8, D9) |
| PIT | Inherit RunSpec/PIT docs | Same; no new causality claims |

**Forbidden (entire series including post-MVP):** edits under `thesistester/engine/`; fill/signal/confluence-math semantics; golden-master regeneration; changing `run_batch` abort/write defaults; greenfield in-product MCP server.

**Allowed additive non-`study/` touches (post-MVP allow-list):**

| Milestone | Allowed outside `thesistester/study/` |
|---|---|
| RS-D7 | `thesistester/cli.py` `_execute_run` index keys (+ parity tests) |
| RS6 | `assistant/registry.py` (+ handler/orchestrator wiring), `config/assistant.toml` default-off `[assistant.study_tools]` |
| RS-D2 | `pages/15_Studies.py` (or next free slot), USER_GUIDE + HC §7.1.4 / `help_corpus.py` |
| RS-D4 / RS-D5 | Docs/examples primarily; CLI subparser additive for `study rollup` if used |
| RS-D8 | Same `pages/15_Studies.py` + `thesistester/study/preview.py`; USER_GUIDE (prefer extend existing Studies H2); HC §7.1.4 only if a **new** H2 is added |
| RS-D9 | Same `pages/15_Studies.py` + new `thesistester/study/launch.py`; USER_GUIDE (prefer extend existing Studies H2); HC §7.1.4 only if a **new** H2 is added. **No** `cli_study.py` argv changes; **no** `execute.py` edits |

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
RS-D7  →  RS6  →  RS-D2  →  RS-D4  →  RS-D5  →  RS-D8  →  RS-D9
  │         │        │         │         │         │         └─ Studies CLI-launch button (spawn existing `study run`; no in-process execute)
  │         │        │         │         │         └─ Studies authoring preview (validate + dry expand + ledger watch)
  │         │        │         │         └─ external Grok routine pack (docs + recipes)
  │         │        │         └─ per-cell diagnostic rollup (compose existing artifacts only)
  │         │        └─ Streamlit Studies viewer (artifacts-only inspect; no in-process execute)
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
| **RS-D8 after D5** | Authoring preview on the existing Studies page; YAML contract unchanged; still not a second runner |
| **RS-D9 after D8** | Convenience spawn of the **same** CLI argv from the preview pane; in-process `run_study` stays forbidden; confirm/sandbox/lock gates must not weaken |
| **Parked ≠ cancelled** | RS-D1 / RS-D3 / RS-D6 stay available when a concrete need appears; not on the critical path |

**Global regression posture (every post-MVP PR):**

- Satisfy `ENGINEERING_PROPOSAL.md` §4.2.
- **No** `thesistester/engine/` edits; **no** fill/signal/confluence-math changes; **no** golden-master regeneration (none in this series).
- Classic `python -m thesistester run` / `run_batch` abort+write semantics unchanged (study layer remains continue-capable).
- Allow-list non-`study/` touches: RS-D7 may extend `cli.py` `_execute_run` index keys; RS6 may register default-off assistant capabilities/config; RS-D2 may add one read-only page + HC allowlist; **RS-D8 and RS-D9 may edit that same Studies page only** (no new nav slot; no classic research pages). D9 must **not** change `cli_study.py` argv or `execute.py`.
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
| 6 | RS-D8 | Studies authoring preview (validate + dry expand + ledger watch) | **Yes (same Studies page; preview only)** | No | No in-process execute |
| 7 | RS-D9 | Studies CLI-launch button (spawn existing `study run`) | **Yes (same Studies page; spawn only)** | No | Detached CLI child |
| — | D1/D3/D6 | Parked | — | — | — |

---

### 12.2 RS-D7 — Additive index columns (`profit_factor`, `win_rate`) — ✅

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅ |
| **Scope** | Additive **`profit_factor` and `win_rate`** columns on study-authored and CLI `results_index.csv` writers; report prefers index when present (already implemented in `report._resolve_bundle_metrics`) |
| **Likely files** | `thesistester/study/execute.py` (`R18_INDEX_METRIC_KEYS` / `STUDY_INDEX_KEYS` / `build_index_row_from_state` / `_index_row_from_existing_bundle` / final soft-resume repair loop); `thesistester/cli.py` `_execute_run` index row (parity); `tests/study/test_study_execute.py` parity + focused PF/WR tests; `docs/METRICS_GLOSSARY.md` / `STUDY_RUNNER.md`; module docstring on `study/report.py` (drop “RS-D7 optional” wording once green) |
| **Column order (locked)** | Insert both keys on `R18_INDEX_METRIC_KEYS` **immediately after** `max_drawdown_r` (with the other trade-summary metrics), before grid/validation/WFA keys: `…, max_drawdown_r, profit_factor, win_rate, best_grid_stop_loss_ticks, …`. Keep study `bundle_path` + `status` as the only study-only suffixes on `STUDY_INDEX_KEYS`. |
| **Behavior** | |
| | For **ok** cells, write both columns from `trade_summary` at index-write time (`build_index_row_from_state` + CLI `_execute_run`) |
| | Failed/pending rows: leave `profit_factor` / `win_rate` **null** (never fabricate) |
| | **NaN → null:** if `trade_summary` yields non-finite NaN for PF/WR, store **null** (same honesty as report `_coerce_float`) |
| | **Soft-resume full rehydrate:** `_index_row_from_existing_bundle` must also copy `profit_factor` + `win_rate` from bundle `trade_summary` (today it only rehydrates trade_count/expectancy/total/max_dd) |
| | **Soft-resume field backfill (locked hole):** today’s final repair only rehydrates when **both** `trade_count` and `expectancy_r` are missing. Pre-D7 ok rows often already have those metrics but **lack** PF/WR columns. After D7, when `status=ok` + bundle path and either PF or WR is missing/null/NaN, **backfill only the missing PF/WR fields** from bundle `trade_summary` without wiping other index columns. Without this, soft-resume keeps zip-scrape forever for otherwise-healthy rows |
| | **CSV / `±inf`:** store Python `float("inf")` / `float("-inf")` in the row dict; `DataFrame.to_csv` emits `inf` / `-inf` (report already coerces those strings). Do **not** invent a custom string serializer unless a test proves pandas diverges |
| | **Default-compatible:** older indexes / readers without the columns still work; `_write_results_index` / `_load_existing_index_rows` already tolerate additive columns; report keeps bundle fallback |
| | Do **not** bump Experiment `schema_version` solely for this; document as additive index column set |
| | Do **not** add `win_rate` to StudySpec `_INDEX_PRIMARY_METRICS` / ranking allow-list (schema stays expectancy/total/max_dd/trade_count/profit_factor) |
| | **Ordered parity (locked):** CLI `_execute_run` dict keys and `R18_INDEX_METRIC_KEYS` must match **as ordered tuples**, not merely as sets. Strengthen `test_index_columns_parity_vs_cli_execute_run` accordingly. Do not change `run_batch` write timing / abort semantics |
| **Out of scope** | Engine metric formula changes; silent removal of bundle PF path; Studies UI; assistant tools; inventing `win_rate_source` column (report keeps PF-only source tracking); making `win_rate` a StudySpec primary_metric |
| **Regression** | Existing CLI/study index consumers tolerate new columns; no golden engine regen |
| **Acceptance checklist** | |
| | ☑ New ok cells write both `profit_factor` and `win_rate` on `results_index.csv` (column order after `max_drawdown_r`) |
| | ☑ Failed/pending rows keep null PF/WR |
| | ☑ Soft-resume full rehydrate populates PF/WR from existing bundles |
| | ☑ Soft-resume field backfill fills PF/WR on pre-D7 ok rows that already have trade_count/expectancy |
| | ☑ NaN PF/WR from trade_summary become null on the index |
| | ☑ `±inf` PF round-trips via CSV to report (`profit_factor_source=index`) |
| | ☑ Report `profit_factor_source=index` when column present and coercible (incl. `±inf`) |
| | ☑ Bundle fallback still works when column absent/null |
| | ☑ Ordered CLI ↔ study `R18_INDEX_METRIC_KEYS` parity test green |
| | ☑ Docs note additive columns + `inf` CSV behavior; `report.py` docstring no longer calls D7 optional; no claim of R18 Experiment schema break |
| | ☑ Soft-resume rehydrate preserves identity (`dataset_id` / `instrument`) via prior row or `dataset_meta.json` |
| | ☑ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D7 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.2 + §12.8.
Add additive profit_factor AND win_rate to study and CLI results_index writers
from trade_summary (insert on R18_INDEX_METRIC_KEYS immediately after
max_drawdown_r). Null on failed/pending. NaN → null. Soft-resume:
(_index_row_from_existing_bundle) must copy PF/WR, AND final repair must
field-backfill missing PF/WR on ok+bundle rows even when trade_count/
expectancy already present. Store ±inf as float inf; rely on pandas CSV
inf/-inf (no custom serializer). Keep report bundle fallback. Strengthen
ordered CLI↔study key parity test + focused PF/WR tests. No engine/pages.
No run_batch semantic/timing change. Do not add win_rate as StudySpec
primary_metric. §4.2. Update STUDY_RUNNER + glossary + report.py docstring.
```

---

### 12.3 RS6 — Default-off `STUDY.*` assistant capabilities — ✅

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅; **RS-D7** (so tool/index consumers see PF/WR without zip scrape) |
| **Scope** | Thin adapters over existing `thesistester.study` APIs registered in `FEATURE_PARITY_REGISTRY` behind default-off **`[assistant.study_tools] enabled=false`** (fail-closed coerce, same pattern as `[assistant.voice]`); minimal operator docs for external Grok Bot CLI/confirm recipe |
| **Likely files** | `thesistester/study/tools.py` (+ small settings loader mirroring `assistant/voice/settings.py` `_coerce_enabled_flag`); `thesistester/assistant/registry.py` (+ typed handlers / orchestrator wiring); `config/assistant.toml` `[assistant.study_tools]`; `docs/STUDY_RUNNER.md` agent section; `docs/AGENT_GUIDE.md`; `tests/study/` + assistant parity / registry-audit fixtures |
| **Primary surface (locked)** | Assistant capabilities (mirror `PIPELINE.run_experiment` pattern), **not** a greenfield MCP server. Optional: document-only MCP-shaped descriptor appendix for external hosts — **no in-repo MCP runtime** in RS6. Voice/realtime must continue to deny MCP/search. |
| **Capabilities (IDs locked)** | `STUDY.expand`, `STUDY.run`, `STUDY.report`, `STUDY.promote` |
| **Capability modes (locked)** | All four → `CapabilityMode.EXECUTABLE` (each writes artifacts: expansion / cells / overview / draft YAML). Do **not** invent a new `ConfirmationLevel` enum member. |
| **Confirmation levels (locked)** | `expand` / `report` / `promote` → `ConfirmationLevel.NONE`. `run` → `ConfirmationLevel.EXPLICIT_CONFIRMATION`. |
| **Confirm nomenclature (locked)** | First gated `STUDY.run` dispatch returns orchestrator status **`OrchestrationStatus.APPROVAL_REQUIRED`** (existing enum — **not** a ConfirmationLevel). Orchestrator `confirmed=True` alone is **not** sufficient over threshold. |
| **Approval payload (locked)** | Bound object on `AssistantRequest.payload` (exact key name may be `approval` or `study_approval`, but must be documented once and tested), shape at minimum: `{study_identity_hash, run_count, output_dir}` using the same `study_identity_hash` helper as expand/ledger. Confirmed retry must refuse if the bound triple does not match the current expansion/target. |
| **Flag / registry posture (locked)** | **Register** `STUDY.*` in `FEATURE_PARITY_REGISTRY` when the code ships (keeps registry-audit deterministic), but every handler **refuses first** with a clear “study tools disabled” error when `enabled` is false / missing / non-boolean. Missing `[assistant.study_tools]` section → disabled. Do not leave a second “unregister when off” path that drifts audit counts. |
| **Behavior** | |
| | Inputs: StudySpec path **or** structured dict that must pass `validate_study_spec` before any side effect; `output_dir`; `workers`; promote `top_n` / `metric` / overwrite `force`; run `force` (identity/resume parity with CLI) |
| | Soft resume / identity mismatch / `--force` semantics **must** match `run_study` CLI — tools must not invent weaker gates |
| | Promote overwrite gate matches CLI (`force` required to replace existing draft) |
| | **Confirm parity (two-step):** when `run_count >= confirm_above_runs`, gate with `EXPLICIT_CONFIRMATION` → `APPROVAL_REQUIRED`, then confirmed retry **with** the bound approval payload. Below threshold, run may proceed without that gate (CLI parity). Expand/report/promote never require confirm. |
| | Optional helper capability `STUDY.confirm` is allowed only if it mints/records that bound approval — it must not execute cells. |
| | Return structured payloads: `run_count`, cost hints, artifact paths, ledger summary, honesty flags — not free-form “winner” claims |
| | Tools call `expand_study` / `run_study` / `report_study` / `promote_study` — **never** `run_batch` |
| **Docs split** | RS6 lands a **minimal** “CLI + confirm recipe” section. Full multi-step Grok routine pack is **RS-D5** only — do not duplicate divergent long recipes here. |
| **Out of scope** | NL StudySpec compilation (RS-D1); Streamlit Studies page (RS-D2); embedding Grok/RabbitMQ; inventing setups; enabling tools by default; shipping a live MCP server; new ConfirmationLevel values; INSPECT_ONLY STUDY.* modes |
| **Regression** | Assistant parity fixtures green with flag off; Help/Discuss unchanged; engine/pages untouched; CLI study commands unchanged; registry-audit expects STUDY.* ids present but disabled-by-default |
| **Acceptance checklist** | |
| | ☑ `[assistant.study_tools] enabled` defaults to **false** (fail-closed coerce; missing section → disabled) |
| | ☑ With flag off, STUDY.* handlers refuse; other assistant surfaces behave as before RS6 (parity fixtures) |
| | ☑ With flag on, expand/report/promote work without confirm; run uses two-step `EXPLICIT_CONFIRMATION` → `APPROVAL_REQUIRED` when over threshold |
| | ☑ Bound approval triple enforced; `confirmed=True` alone cannot bypass |
| | ☑ Structured-dict inputs validate via `validate_study_spec` before writes/execute |
| | ☑ `force` / workers / soft-resume / identity mismatch match CLI `run_study` / `promote` |
| | ☑ Tools do not call `run_batch` |
| | ☑ All four capabilities are `EXECUTABLE` with confirmation levels as locked above |
| | ☑ Minimal CLI/confirm recipe docs (RS-D5 owns the full routine pack) |
| | ☑ Full suite + assistant parity + registry-audit green |

**Copy-ready agent prompt:**

```text
Implement RS6 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.3.
Add default-off [assistant.study_tools] (fail-closed coerce like voice) +
STUDY.{expand,run,report,promote} FEATURE_PARITY_REGISTRY capabilities
(EXECUTABLE). Register always; handlers refuse when disabled. Confirmation:
expand/report/promote NONE; run EXPLICIT_CONFIRMATION. Gated run returns
OrchestrationStatus.APPROVAL_REQUIRED; confirmed retry requires payload
approval bound to (study_identity_hash, run_count, output_dir) — confirmed=True
alone is insufficient. No new ConfirmationLevel members. No MCP server.
Match CLI force/workers/resume/promote overwrite. No engine/pages/run_batch.
Keep assistant parity fixtures green when flag off. §4.2.
Update STUDY_RUNNER.md (minimal agent recipe) + roadmap.
```

---

### 12.4 RS-D2 — Streamlit Studies viewer (artifacts-only) — ✅

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅; **RS-D7** (PF/WR on index); RS6 optional |
| **Scope** | One new Streamlit page that **reads** an existing study output directory and displays ledger + overview artifacts |
| **Likely files** | `pages/15_Studies.py` (**preferred** — next free numeric slot after `14_Research_Assistant.py`; rename only if nav convention conflicts); thin helpers reusing `report_study` / ledger loaders — **do not reimplement** join/rank; `docs/USER_GUIDE.md` H2 + HC §7.1.4 allowlist amend; `ARCHITECTURE.md` boundary note |
| **Behavior** | |
| | User selects / pastes a study `output_dir` (sandbox/path-validate; refuse arbitrary filesystem traversal outside intended roots if the app already has a path policy — otherwise document trusted-local-path assumption) |
| | Show: study identity, run_count, ledger ok/failed/pending, ranked table, low-N, unresolved, OTF Δ summary, `bundle_path` strings |
| | Honesty banner: descriptive ranking ≠ validated edge; multiple-testing; min_trades |
| | Optional: download / show `study.overview.md` / CSV text. **Do not** promise Research-Bundles deep-link-by-path (that page is upload/import oriented); listing `bundle_path` is enough |
| | **Read-only inspect pane:** no in-app expand-to-disk / run / promote; must **not** mutate classic research `st.session_state` keys (levels/signals/trades/etc.). A StudySpec **preview textarea** is **RS-D8** (same page; still no execute) — do not add it in the D2 PR |
| **Out of scope** | Factor builder UI (separate **SB** series); templates marketplace; auto-run; assistant NL; changing headless CLI; portfolio of studies cloud sync; **StudySpec paste/preview (RS-D8)** |
| **Regression** | Classic pages unchanged in behavior; no engine edits; Help allowlist updated if USER_GUIDE gains H2; nav addition must not break existing page tests |
| **Acceptance checklist** | |
| | ☑ Can load a completed fixture study dir and show ranked/low-N/ledger without running backtests |
| | ☑ Reuses study report/ledger loaders (no divergent ranking logic) |
| | ☑ Honesty caveats visible |
| | ☑ No execute/promote/expand controls that mutate study or research session state |
| | ☑ USER_GUIDE (+ HC §7.1.4 if Help-readable) updated same PR |
| | ☑ Existing Streamlit/assistant tests green; engine goldens untouched |
| | ☑ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D2 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.4.
Add a thin Streamlit Studies viewer over existing study artifacts (ledger + overview).
Reuse report_study/ledger loaders. Read-only: no in-app expand/run/promote; do not
mutate research session_state. Honesty banner required. Show bundle_path; no false
deep-link. HC allowlist if USER_GUIDE H2 added. No engine edits. §4.2.
```

---

### 12.5 RS-D4 — Per-cell diagnostic rollup (WFA / validation / overfitting) — ✅

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
| **Recommended survivor-stage constants** (docs + examples only; not auto-applied): after promote, humans may opt into `walk_forward.enabled: true` and/or `grid.enabled: true` + `validation.enabled: true` + `validation.overfitting.enabled: true` (**explicit `enabled` flags**; never bare `{}`; parent validation gate required) before expecting rollup density |
| **Out of scope** | New PBO/DSR algorithm; study-level pooled PBO across factorial cells; auto-enabling batteries on promote/report; changing analytics formulas; engine changes |
| **Regression** | Enabling rollup never changes cell backtest results; classic validation pages unchanged |
| **Acceptance checklist** | |
| | ☑ Rollup reads existing cell artifacts / index WFA columns only |
| | ☑ Missing batteries → explicit null/not_run, not invented scores |
| | ☑ No cross-cell PBO/DSR computation |
| | ☑ Honesty block in MD |
| | ☑ Docs state grid requirement for overfitting fields + survivor opt-in recipe |
| | ☑ No engine/pages golden drift |
| | ☑ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D4 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.5.
Add study-level per-cell diagnostic rollup composing existing WFA/validation/
overfitting bundle/index fields. Do NOT invent cross-cell PBO/DSR or auto-enable
batteries. Missing → not_run/null. Honesty required. No engine golden changes. §4.2.
Update STUDY_RUNNER + assumptions (incl. grid requirement for overfitting).
```

---

### 12.6 RS-D5 — Grok Bot routine pack (external) — ✅

| | |
|---|---|
| **Depends on** | **RS6** (minimal CLI/confirm docs + optional STUDY.* tools); benefits from RS-D7 index PF |
| **Scope** | **Documentation + example agent routines** for an external coworker (Grok Bot). Prefer living outside the product runtime; in-repo only as docs/examples under `docs/` or `examples/studies/agents/` |
| **Docs split** | Owns the **full** multi-step routine pack. Must not contradict RS6’s minimal recipe; extend it. |
| **Shipped** | `docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md` + `examples/studies/agents/` (SYSTEM + stage-first / confirm-bound / survivor-diagnostics prompts); operator pointer in `STUDY_RUNNER.md` §RS-D5 |
| **Behavior** | |
| | Recipe: stage-first expand → two-step confirm when required → run → report → promote draft → human edit → second pass (optionally enable WFA/grid on survivors before RS-D4 rollup) |
| | Hard rules: never invent factor axes; never bypass confirm; never auto-run promote drafts; always surface honesty / min_trades / multiple-testing |
| | May shell CLI even if `assistant.study_tools.enabled` is off |
| **Out of scope** | Embedding Grok in ThesisTester; RabbitMQ; multi-agent host; product UI for bot orchestration; shipping MCP server |
| **Acceptance checklist** | |
| | ☑ Documented routine pack with copy-ready prompts/commands |
| | ☑ Explicit non-goals: no setup invention, no confirm bypass, no auto-promote execute |
| | ☑ Points at RS6 default-off flag + CLI fallback; references RS-D7 index PF |
| | ☑ No runtime default changes |

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

Still **non-goals:** auto-promote to live thesis without human confirm; scheduled study daemon / job queue; UI factor **marketplace**; merging with confluence-combo attribution; greenfield in-product MCP server; **in-process** Streamlit `run_study` / `STUDY.run` from the Studies page (RS-D8 preview does not reopen this; **RS-D9** is CLI-spawn only and does not reopen in-process execute).

**Study Builder (separate SB series):** the parked “form-based factor builder” is specified in `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md` (SB0–SB3). It emits canonical `schema_version: 1` YAML onto the existing Preview pane. It is **not** a marketplace, **not** an NL compiler (RS-D1 stays parked), and **not** new factor types (RS-D6 stays parked). Do not implement SB inside an RS PR.

**Study Viewer (separate SV series):** local study catalog, failed-cell / group-summary / rollup-file Inspect panes, overview charts, and cell peek are specified in `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV0–SV4). That series does **not** reopen this §12.4 RS-D2 contract (path-paste Inspect, `write_artifacts=False`, no classic-session mutation, no Research-Bundles deep-link). Local catalog is **not** “portfolio of studies cloud sync” (still out of scope here). Do not implement SV inside an RS PR.

**Study Admit Follow-up (separate SAF series):** drafting a linked child StudySpec with Admit locked to a post-hoc ToD bucket is specified in `docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md` (SAF1–SAF3 shipped; SAF4 parked). That series does **not** reopen RS5 “promote never executes” or this series’ execute loop. Default `study promote` (flags omitted) stays identical. Do not implement SAF inside an RS PR.

---

### 12.8 First implementable PR (kickoff)

**RS-D7 ✅, RS6 ✅, RS-D2 ✅, RS-D4 ✅, RS-D5 ✅, RS-D8 ✅, and RS-D9 ✅ shipped.** Sequenced post-MVP track complete; parked items (§12.7) stay out unless this plan is amended.

Historical D7 implementer notes (kept for audit):

Use the §12.2 copy-ready prompt verbatim. Extra implementer notes:

1. Touch `build_index_row_from_state`, CLI `_execute_run`, **and** `_index_row_from_existing_bundle`.  
2. **Also** extend the final soft-resume repair loop in `run_study` so ok+bundle rows with present trade_count/expectancy but missing PF/WR get **field-level** PF/WR backfill (see §12.2 hole).  
3. Strengthen parity test to **ordered** CLI `_execute_run` keys ↔ `R18_INDEX_METRIC_KEYS` (not set equality / `co_consts` smoke alone).  
4. Focused tests: ok → PF/WR present (order after `max_drawdown_r`); failed/pending → null; soft-resume full rehydrate → PF/WR; soft-resume field backfill on pre-D7-shaped ok rows; NaN → null; `inf` CSV → report `profit_factor_source=index`.  
5. Leave `report._resolve_bundle_metrics` preference path alone unless a bug is proven — it already prefers index. Update the `report.py` module docstring that still says “RS-D7 remains optional.”  
6. Update glossary + `STUDY_RUNNER.md` RS4 PF source note to “RS-D7 landed” only after green.  
7. Mark roadmap RS-D7 ✅ in the same PR; do **not** start RS6 in that PR.

---

### 12.9 RS-D8 — Studies authoring preview (validate + expand dry-run + ledger watch) — ✅

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅ (schema + pure `expand_study`); **RS-D2** ✅ (same Studies page / path sandbox / honesty banner); RS-D5 optional (CLI recipe unchanged — one operator sentence is enough; do not rewrite the Grok pack) |
| **Scope** | Let a researcher **paste or edit canonical StudySpec YAML** on the existing Studies page, **validate + expand in memory**, and see **how many cells** would run and whether `--confirm` is required — then go run it on the CLI. Optionally **watch** an in-flight CLI study via ledger refresh. **Compose existing APIs; do not invent a second runner.** |
| **Likely files** | `thesistester/study/preview.py` (pure helper); `pages/15_Studies.py` (second pane/tab on the **same** nav slot); `thesistester/study/viewer.py` only if ledger-refresh needs a thin wrapper; `tests/study/test_study_preview.py` (+ existing `test_study_viewer.py` regression); `docs/STUDY_RUNNER.md` §RS-D8; `docs/USER_GUIDE.md` (prefer **extend** H2 `Studies viewer (read-only)` — no new H2 unless Help retrieval requires it); `docs/ARCHITECTURE.md` boundary sentence; `docs/AGENT_GUIDE.md` heading/pointer; roadmap/status |
| **Import allow-list (locked)** | `preview.py` may import `thesistester.study.schema` (`StudySpecError`, `normalize_study_spec`, `validate_study_spec`) and `thesistester.study.expand` (`expand_study`, `_apply_stage_filter` / public equivalent, `study_identity_hash`). **Must not import** `thesistester.study.execute` (that module pulls `run_experiment` / process pools / locks), `thesistester.cli.run_batch`, `promote`, or assistant `STUDY.*` handlers. Battery hints are computed from **constants** in `preview.py` (all expanded cells share `grid`/`validation`/`walk_forward`); do **not** call `execute.cost_hint_lines`. Optional: a tiny hint helper may live in `expand.py` or `preview.py` — not in `execute.py`. |
| **YAML load path (locked)** | Textarea / file bytes → `yaml.safe_load` → must be a mapping → `normalize_study_spec` → `validate_study_spec`. Invalid YAML / non-mapping → `StudySpecError`, **no** expand. `load_study_spec` remains path-only; do not require a temp file for paste. Dataset `path` is a string at validate time (`validate_run_spec` does not require the CSV to exist) — example preview must work without `data/es_1m.csv`. |
| **YAML contract (locked)** | |
| | Accept **only** `schema_version: 1` StudySpec YAML (same keys as `load_study_spec` / `validate_study_spec`) |
| | **No** NL → YAML compiler (that remains parked **RS-D1**) |
| | **No** shorthand dialect (`core` vs `core_level`, `partners` vs `partner_levels`, `report.primary` vs `report.primary_metric`, `min_trades` under `constants`, omitted `mode_rules`) — unknown/wrong keys fail closed with the existing `StudySpecError` text |
| | Optional **Load example** reads `examples/studies/pdPOC_ma_confluence_battery.yaml` resolved from the **repo root** (cwd / documented project root). Clear error if missing. Optional **Copy spec from loaded study dir** reads `study.spec.yaml` already sandboxed by RS-D2 |
| **Preview semantics (locked)** | |
| | Helper `preview_study_spec(spec) -> StudyPreview` (name may vary; keep it in `preview.py`) must: (1) normalize + validate; (2) report per-axis domain sizes from `study.factors` (`partner_levels` size = number of partner-sets); (3) `cartesian_product` = product of those sizes (1 if no factor axes); (4) `effective_run_count_estimate` honoring `stage` using the **same intersection semantics as** `expand._apply_stage_filter` — **not** raw include-list lengths. `explicit_cells` → `len(cells)`; `filter` → product of **matched** domain sizes after include∩factor-domain (OTF canonicalized; partner-sets list-equal); unmatched include tokens do not inflate the estimate; empty match → `StudySpecError` (same as expand); no stage → `cartesian_product`; (5) if `effective_run_count_estimate <= PREVIEW_EXPAND_CAP` (**2_000**, constant in `preview.py`), call **in-memory** `expand_study` and surface exact `run_count`, `study_identity_hash`, `workers`, and constants-based battery hints; (6) if over cap, **do not** call `expand_study` — return the matched estimate, `expanded=False`, axis sizes, battery flags from constants, and a clear warning |
| | **Cap rationale:** `expand_study` runs `build_setup` + `validate_run_spec` per cell. 40 (stage-first) and 800 (full example cartesian) stay under 2_000. 20_000 would freeze Streamlit; 2_000 is a hard UI ceiling, not a target. Show a spinner while expanding. |
| | `needs_confirm = count >= confirm_above_runs` with `>=` matching `run_study` (use exact `run_count` when expanded, else the matched estimate). Confirm is run-count-only; still **display** `study.workers`. |
| | Battery flags from **constants** (`grid` / `validation` / `walk_forward` `enabled`), not by executing cells. Warn when any is true (CLI-equivalent meaning; do not iterate 2_000 run dicts). |
| | Error split: schema/`StudySpecError` vs expand/`validate_run_spec` failures both surface as preview failures; neither implies execute started. |
| | Default filesystem side effects: **none**. Do **not** call `expand_study_to_directory`, `run_study`, `run_experiment`, `run_batch`, `report_study` (write path), `promote_study`, or assistant `STUDY.*` handlers |
| | Optional **Save YAML** (not required for D8 MVP, but if shipped): write the **validated** YAML text to an **operator-chosen new path** under the RS-D2 sandbox (repo cwd or local store). Refuse overwrite unless an explicit force control. **Never** default the save path to the inspect dir’s `study.spec.yaml` (that would clobber a completed study). Saving must **not** expand-to-disk or execute |
| **UI (locked)** | |
| | Same page `pages/15_Studies.py` — add a clearly labeled pane/tab (e.g. **Preview StudySpec** vs **Inspect output dir**). **Do not** add a new sidebar page / numeric slot |
| | Controls allowed: YAML textarea; Validate / Preview; Load example; Copy spec from loaded dir; **Refresh** ledger (inspect pane); optional Save YAML as above |
| | Controls **forbidden**: Run study, Confirm-and-run, Promote, Enable batteries, Dispatch `STUDY.run`, any widget that calls execute |
| | Display: study name; `workers`; axis sizes; `cartesian_product`; staged vs unstaged (matched estimate vs full cartesian) when `stage` is present; exact `run_count` when expanded; `confirm_above_runs` + `needs_confirm`; identity hash; battery enabled flags; constants-based hint lines; `StudySpecError` on failure |
| | Honesty (required, visible with every successful preview): combinatorial `run_count` is a **screening size**, not independent statistical tests; large factorials need `--confirm` on CLI; descriptive ranking after a run ≠ validated edge; execute remains `python -m thesistester study run …` |
| | Session state: Studies-scoped keys only. New key e.g. `studies_preview_yaml`. **Must not** collide with existing `studies_viewer_path_input` / `STUDIES_VIEWER_DIR_KEY`. **Must not** mutate classic research `st.session_state` keys (`CLASSIC_RESEARCH_SESSION_KEYS`). Preserve RS-D2 inspect-dir behavior |
| **Ledger watch / progress (locked)** | |
| | Progress means **read-only refresh** of an existing study `output_dir` ledger (`pending` / `running` / `ok` / `failed` counts already defined). The page does **not** start or resume execution |
| | **Required:** an explicit **Refresh** control on the inspect pane (Load already reloads on Streamlit rerun; Refresh makes in-flight CLI runs obvious) that reloads via existing `load_study_view` / `load_ledger` with `report_study(..., write_artifacts=False)` |
| | **Optional:** auto-refresh, **default off**. Button-only is the expected Streamlit path; if auto-refresh is added it must stay off by default, only while `pending+running > 0`, interval ≥ 10s |
| | Do not spawn subprocesses, workers, or `study run` from the page to “help” progress |
| **Out of scope** | NL compiler (RS-D1); shorthand/alias StudySpec dialect; form-based factor builder (separate **SB** series — not RS-D8); templates marketplace; in-app expand-to-disk as a substitute for CLI `study expand`; in-app execute / promote; auto-enabling `grid`/`validation`/`walk_forward`; new ConfirmationLevel values; MCP server; new nav page; engine / classic research page edits; golden regeneration; rewriting the RS-D5 Grok pack |
| **Regression** | |
| | RS-D2 inspect path keeps working (load completed fixture dir → ranked/low-N/ledger, no writes) |
| | `expand_study` golden fixtures unchanged (preview **calls** expand, does not change it) |
| | `assistant.study_tools` remains default-off; Help/Discuss defaults unchanged |
| | No `engine/` edits; no `run` / `run_batch` semantic change; no STUDY.* handler changes required (page must not call them) |
| | USER_GUIDE: prefer extending the existing H2 `Studies viewer (read-only)`. **If** a new H2 is added, amend RQ §7.1.4 + `_USER_GUIDE_SECTIONS` + freeze tests **in the same PR** |
| **Acceptance checklist** | |
| | ☑ `preview_study_spec` on the stage-first example → exact `run_count=40`, `cartesian_product=800` (1×4×2×5×4×5), `needs_confirm` false at default `confirm_above_runs=200` |
| | ☑ Filter estimate uses matched `_apply_stage_filter` sizes: duplicate include tokens do **not** inflate the estimate (same count as expand) |
| | ☑ Invalid YAML / non-mapping / shorthand (`factors.core`) → `StudySpecError`, no expand, no execute |
| | ☑ Missing `mode_rules` when `confluence_mode` present → fail closed (existing schema) |
| | ☑ Over-cap estimate skips `expand_study` and still shows matched axis sizes + warning |
| | ☑ Import/AST guard: `preview.py` must **not import** `thesistester.study.execute` / `run_experiment` / `run_batch` / `expand_study_to_directory` / `promote_study` |
| | ☑ Page has no Run / Promote execute controls; classic research session keys untouched; no collision with `studies_viewer_path_input` |
| | ☑ Viewer Refresh reloads ledger counts without rewriting `study.overview.*` |
| | ☑ Optional Save YAML **not shipped** (D8 MVP) |
| | ☑ Honesty visible on successful preview |
| | ☑ Docs: `STUDY_RUNNER.md` §RS-D8 + USER_GUIDE extend + ARCHITECTURE one-liner + AGENT_GUIDE pointer + roadmap status; no new USER_GUIDE H2 (HC allowlist unchanged) |
| | ☑ Existing `tests/study/` + Streamlit/assistant tests green; engine goldens untouched |
| | ☑ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D8 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.9.
Add a Studies authoring preview on the existing pages/15_Studies.py (no new nav
slot): paste canonical schema_version:1 StudySpec YAML, yaml.safe_load →
normalize/validate → in-memory expand_study, show run_count / cartesian_product /
matched stage estimate / needs_confirm / workers / identity / constants battery
hints. Filter estimate MUST use expand._apply_stage_filter matched sizes (not
raw include-list lengths). PREVIEW_EXPAND_CAP=2000. preview.py must NOT import
thesistester.study.execute or call cost_hint_lines. No NL/shorthand compiler.
No in-app study run/promote/expand-to-disk. Save YAML (if any) must not default
to the inspect dir study.spec.yaml. Ledger progress = read-only Refresh of an
existing output_dir (write_artifacts=False). Honesty required. Studies-scoped
session keys only (do not collide with studies_viewer_path_input). No engine
golden drift. Prefer extend USER_GUIDE H2; HC allowlist only if a new H2 is
added. §4.2.
```

---

### 12.10 RS-D9 — Studies CLI-launch button (spawn existing `study run`) — ✅

| | |
|---|---|
| **Depends on** | RS1–RS5 ✅ (`cli_study._cmd_run` → `run_study`); **RS-D2** ✅ (path sandbox / honesty / Inspect Refresh); **RS-D8** ✅ (`StudyPreview`, identity hash, `needs_confirm`, `PREVIEW_EXPAND_CAP`, cached YAML). RS6 confirm *shape* is the bound triple to copy — do **not** dispatch `STUDY.run` from the page |
| **Scope** | After a successful preview, let a researcher start the **same** headless CLI they would type, without hand-saving YAML or leaving the Studies page. The page **spawns** `sys.executable -m thesistester study run …` as a **detached** subprocess. It does **not** call `run_study()` in-process, does **not** call `run_batch`, does **not** dispatch `STUDY.run`, and does **not** add a second execute implementation. |
| **Product intent (locked)** | |
| | 1. **Single academic execute path:** `thesistester.study.execute.run_study` reached only via CLI (`python -m thesistester study run` → `cli_study._cmd_run`). RS-D9 is a **control-plane spawn** of that argv. |
| | 2. Convenience must **not** weaken confirm (`>= confirm_above_runs`), sandbox (RS-D2 roots), identity mismatch, `.study.lock`, or `--force` semantics. |
| | 3. Local single-user is assumed. The risk to lock is **control-plane drift / confirm / Streamlit reruns**, not fill math. |
| | 4. Detached `Popen` is **not** a job queue, scheduler, or daemon (those remain non-goals). |
| **Likely files** | `thesistester/study/launch.py` (**new**; argv + path pin + spawn + pid/log); `pages/15_Studies.py` (controls on the **Preview** pane after a successful cached preview); `tests/study/test_study_launch.py` (new); `tests/study/test_study_preview.py` (extend page AST / session-key allow-list; **keep** `preview.py` import guard); `docs/STUDY_RUNNER.md` §RS-D9; `docs/USER_GUIDE.md` (prefer **extend** H2 `Studies viewer (read-only)` — no new H2 unless Help retrieval requires it); `docs/ARCHITECTURE.md` boundary sentence; `docs/AGENT_GUIDE.md` heading/pointer; roadmap/status; optional **one-liner** in `STUDY_RUNNER_GROK_ROUTINE_PACK.md` (do **not** rewrite the pack) |
| **Import allow-list (locked)** | |
| | `launch.py` may import: `thesistester.study.schema` (`StudySpecError`, `normalize_study_spec`, `validate_study_spec`); `thesistester.study.expand.study_identity_hash` (hash the **pinned** spec the child will load — do **not** call `expand_study` at spawn); `yaml` / `subprocess` / `sys` / `os` / `json` / `pathlib` / `ctypes` (Windows pid-alive query only). Trusted sandbox roots are **inlined** as `_default_trusted_roots()` (cwd + store; must match `default_study_viewer_roots()`). Optional: a tiny `resolve_launch_output_dir` helper in `launch.py` (output dir may **not** exist yet — do **not** reuse `resolve_study_dir` as-is; that helper requires an existing directory). |
| | `launch.py` **must not import** `thesistester.study.execute`, `thesistester.study.viewer`, `thesistester.cli`, `run_batch`, `promote`, `tools.py` / `STUDY.*` handlers, or assistant modules. The Studies page imports launch before viewer; a launch→viewer import can mid-init viewer and `ImportError` the page. Do **not** acquire `.study.lock` in the Streamlit process (Windows-safe; lock stays the CLI child’s job). |
| | `preview.py` import allow-list is **unchanged** (still no `execute`). Do **not** put spawn helpers in `preview.py`. |
| | `pages/15_Studies.py` may import `thesistester.study.launch` plus existing preview/viewer/schema. **Must not** import `run_study` / `promote_study` / `expand_study_to_directory` / assistant handlers. Import the `launch` **submodule** directly — do **not** add `launch.py` to `thesistester.study.__init__` (that module already pulls `execute`). |
| | **Package-init honesty:** `from thesistester.study.launch import …` still runs `study/__init__.py`, which already imports `execute` (D8 `preview` import does the same). D9’s load-bearing invariant is **do not call** `run_study()` and **do not take** `.study.lock` in the UI process — not “execute is never imported.” AST-guard `launch.py` itself. Lazy `__init__` is **out of D9 scope**. |
| **CLI argv (locked — no parser change)** | Existing `cli_study.py` `study run` shape is sufficient. D9 **must not** add flags or change `_cmd_run`. Built argv: |

```text
{sys.executable} -m thesistester study run {launch_yaml} --output-dir {output_dir}
  [--workers N]    # only when the optional UI override is set
  [--confirm]      # only when needs_confirm AND the second confirm step succeeded
  [--force]        # only when the optional checkbox is on (default off)
```

| | |
|---|---|
| | Child `cwd` = `Path.cwd()` (same as a human at repo root). Inherit `os.environ`. Document: start Streamlit from the repo root so `-m thesistester` and relative `data/…` resolve like a terminal CLI. |
| | Argv is a **list** (`shell=False`). Do **not** invoke `python -m thesistester run` (R18 replay) or `study expand` as a substitute for `study run`. |
| | Show the planned argv in the UI (honesty). Tests assert argv **parity** with what a human would type for the same spec/dir/flags, and that `--output-dir` is the resolved **absolute** path. |
| **Launch YAML (locked)** | |
| | Canonical `schema_version: 1` from the preview textarea (the snapshot bound to the last successful preview). |
| | Write `{output_dir}/study.launch.yaml` — **never** `study.spec.yaml`. `run_study` still writes `study.spec.yaml` **after** gates pass. |
| | **Never** default the launch path (or output_dir) to the Inspect dir’s `study.spec.yaml`. |
| | **Pipeline order (locked):** `yaml.safe_load` → `normalize_study_spec` / `validate_study_spec` → **pin** → **sandbox** → **hash** → write launch YAML. Do not write or spawn if any step refuses. |
| | **Pin both dataset keys** — local helper in `launch.py` iterates `("path", "subtimeframe_path")` with the same search-roots-then-cwd rule as `promote._rewrite_dataset_paths_for_draft`. Do **not** import `promote.py` or `tools.py`. Search roots = launch `_default_trusted_roots()` (cwd + store; same values as `default_study_viewer_roots()`, but do **not** import `viewer`) then `Path.cwd()` (authoring YAML is session text, not a file on disk). Prefer an existing file under those roots; else absolutize against `Path.cwd()`. Rationale: CLI `base_directory` is `study_path.parent`; a YAML sitting under `output_dir` would otherwise reinterpret relative `data/es_1m.csv` (and R12 `subtimeframe_path`) as `{output_dir}/data/…`. |
| | **Refuse spawn** if a pinned dataset path is **not an existing file** (fail closed; do not launch a doomed child). Preview may still succeed without the CSV; launch must not. |
| | **Do not rewrite** `study.output_dir` inside `study.launch.yaml`. The child uses absolute `--output-dir`. Extra rewrite of YAML `output_dir` would change the identity hash unless it is included in the hashed dict — leave it as-authored. |
| | Refuse dataset/output paths outside RS-D2 roots (cwd + local store) **after pin**, including `..` traversal and absolute escapes (same spirit as RS6 `_ensure_study_spec_paths_within_roots`: both dataset keys **and** the resolved launch `output_dir`). |
| | `output_dir` may not exist yet: resolve against cwd, sandbox, `mkdir(parents=True)`. Always pass `--output-dir` as that resolved absolute path. |
| | Overwrite of launch metadata in the chosen `output_dir` (`study.launch.yaml` / `.log` / `.pid` / `.json`) is allowed. D9 must **not** rewrite a completed study’s `study.spec.yaml`. |
| | **Identity (locked):** pinning dataset paths **changes** `study_identity_hash` vs `StudyPreview.study_identity_hash` (unpinned textarea) and vs a CLI run of the same relative YAML whose parent is `examples/studies/`. Bind the confirm triple to the **pinned** spec (what the child will hash after load+normalize). **Never** store or echo `StudyPreview.study_identity_hash` as the launch triple hash — that would refuse every over-threshold spawn. Display the **pinned** hash on the launch pane (preview hash may be secondary). Prefer a **new** `output_dir` for UI launches; launching into an existing CLI dir whose `study.spec.yaml` identity ≠ pinned launch spec makes the child refuse without `--force`. `--force` is not a resume shortcut. Document in USER_GUIDE / STUDY_RUNNER. |
| | **Round-trip test:** dump `study.launch.yaml` → `load` + normalize + `study_identity_hash` equals the triple’s pinned hash. |
| **Confirm (CLI parity, `>=`) (locked)** | |
| | Use exact `StudyPreview.run_count` and `confirm_above_runs` (`needs_confirm = run_count >= confirm_above_runs`, matching `run_study`). |
| | **Under threshold:** one control **Run via CLI**. Do **not** pass `--confirm`. |
| | **Over threshold:** **two-step**. (1) First control stores bound triple `{pinned_study_identity_hash, run_count, resolved_output_dir}` in Studies-scoped session state — RS6 *shape*, but the hash is **recomputed after pin**, not copied from `StudyPreview`. Does **not** spawn. Does **not** stash a sticky `--confirm` that a later rerun can fire. (2) Second control **Confirm and run** must echo that triple against the **current** pinned hash + current `run_count` + current resolved `output_dir`. Only then spawn with `--confirm`. |
| | One widget click must not both arm confirm and spawn. A lone checkbox / `confirmed=True` is insufficient. |
| | Extra UI gate (in addition to the triple): textarea must equal the cached preview YAML (`STUDIES_PREVIEW_CACHED_YAML_KEY`). If the operator edited YAML, they must **Validate / Preview** again. Clear any armed approval on YAML / pinned hash / run_count / output_dir change. |
| | If `preview.expanded is False` (over `PREVIEW_EXPAND_CAP=2000`): **refuse spawn**. Exact `run_count` / child identity cannot be bound honestly. Operator must shrink the study or use CLI after `study expand`. |
| | Do **not** call `expand_study` again on the Streamlit request at spawn (would freeze the app on ~1800 cells). Re-`yaml.safe_load` + normalize/validate + pin + `study_identity_hash` only. |
| | `--force` is a **separate** optional checkbox, **default off**, **not** implied by confirm, **not** implied by soft-resume. Distinct from promote `--force`. |
| **Anti-double-start / Streamlit reruns (locked)** | |
| | Spawn **only** on an explicit `st.button(...)` (or equivalent) **true** branch. Tab switches, Inspect Refresh, Validate/Preview, download clicks, and widget-default reruns must **not** respawn. Do **not** store `should_launch=True` in `st.session_state` that fires on every subsequent rerun. |
| | **Exclusive pid claim before `Popen`:** if `study.launch.pid` exists and `launch_pid_is_alive(pid)` → refuse. If the pid is dead or the file is empty/invalid → unlink (stale). Then exclusive-create the pid file (`os.O_CREAT` + `os.O_EXCL` + `os.O_WRONLY`) to claim the slot **before** `Popen`. The in-flight placeholder is **this process's pid** (alive), never `0` (which `launch_pid_is_alive` treats as dead and would let a second tab steal the claim). Write the child pid after spawn. If `Popen` fails, unlink the claim and restore any prior `study.launch.log`. A second tab that loses `O_EXCL` must refuse (no TOCTOU double-spawn). |
| | **`launch_pid_is_alive(pid)` (stdlib only; no `psutil`):** POSIX: `os.kill(pid, 0)` — `ProcessLookupError` → dead, `PermissionError` → alive. **Windows: never `os.kill`** (not an existence probe; can signal/terminate). Use `ctypes` `OpenProcess` query (e.g. `PROCESS_QUERY_LIMITED_INFORMATION` / `SYNCHRONIZE`) + `CloseHandle`. `pid <= 0` → not alive. PID reuse after a finished study is an accepted local-single-user limitation; document it. |
| | The child CLI still takes `.study.lock`; a concurrent human CLI on the same dir fails closed there. D9 must not probe/hold that lock in the Streamlit process. |
| | No auto-retry, no queue, no watchdog that restarts a dead child. |
| **Detach / progress (locked)** | |
| | `subprocess.Popen` — **not** `run` / `check_call` / `wait` / `communicate` on the Streamlit request. `shell=False`; argv is a sequence. |
| | POSIX: `start_new_session=True` so Streamlit exit/SIGHUP does not kill the study; `close_fds=True` so the child does not inherit Streamlit sockets. |
| | Windows: `creationflags` = `subprocess.CREATE_NEW_PROCESS_GROUP` combined with `subprocess.CREATE_NO_WINDOW`. Do **not** set `DETACHED_PROCESS` (redirected stdout/stderr are not inherited, so `study.launch.log` stays empty; Win32 also ignores `CREATE_NO_WINDOW` when combined with it). Do not use `CREATE_NEW_CONSOLE`. Child env must set `PYTHONUNBUFFERED=1` so the log is not block-buffered. |
| | Redirect child stdout+stderr to `{output_dir}/study.launch.log`. **Truncate** that log on each new **successful** spawn (open `'w'` at `Popen` time) so the file matches this launch. Do not truncate when spawn is refused. |
| | Write `{output_dir}/study.launch.pid` and `{output_dir}/study.launch.json` (`pid`, `argv`, **pinned** `study_identity_hash`, `run_count`, `output_dir`, `confirm`, `force`, `started_at`, log path, launch yaml path). |
| | Return immediately with pid + “watch **Inspect → Refresh** / ledger; log at `study.launch.log`”. Showing last N lines of that log on the launch pane is allowed (not a job queue). |
| | Progress UX remains RS-D8: Inspect **Refresh** (`report_study(..., write_artifacts=False)`). Optional auto-refresh stays **default off**. |
| | **No** cancel/kill/promote control in D9 (operator stops the OS process if needed). Showing “PID alive / not alive” from the pid file is allowed. |
| **Workers (locked)** | Display `StudyPreview.workers`. Optional override number input; default = unset (omit `--workers` so the CLI uses the StudySpec). Override must be `int >= 1`; invalid → refuse spawn. Do not silently pass `--workers 1`. |
| **UI (locked)** | |
| | Same page `pages/15_Studies.py`, **Preview StudySpec** pane, **after** a successful cached preview. **Do not** add a new sidebar page / numeric slot. |
| | Controls allowed: `output_dir` text field (default from YAML `study.output_dir` if present, else empty — **never** default to the Inspect dir); optional workers override; optional `--force` checkbox default off; **Run via CLI** / **Confirm and run** as specified; planned argv display; **pinned** identity hash (required); pid/alive status; path to `study.launch.log` (optional last N lines). |
| | Controls **still forbidden**: Promote; Enable batteries; Dispatch `STUDY.run`; in-process `run_study`; expand-to-disk; new nav page; classic research session mutation. |
| | Honesty (required, visible with launch controls): combinatorial `run_count` is a **screening size**, not independent tests; large factorials need the two-step confirm; launching the CLI does not validate an edge; the child is the same `study run` as the terminal; prefer a **new** `output_dir` (existing CLI dir with a different identity refuses without `--force`); start Streamlit from the repo root. |
| **Session state (locked)** | Studies-scoped keys only. New keys e.g. `studies_launch_output_dir`, `studies_launch_approval` (bound triple of **pinned** hash + run_count + resolved output_dir). Must **not** collide with `studies_viewer_path_input` / `STUDIES_VIEWER_*` / `STUDIES_PREVIEW_*`. Must **not** mutate `CLASSIC_RESEARCH_SESSION_KEYS`. Armed approval clears when YAML, **pinned** hash, run_count, or output_dir changes. |
| **Out of scope** | NL compiler (RS-D1); shorthand/alias dialect; form-based factor builder (separate **SB** series — not RS-D9); in-process execute; promote from the page; job queue / scheduler / kill UI; new CLI flags; `execute.py` / `cli_study.py` edits; `run_batch` continue (RS-D3); new factor types (RS-D6); MCP; engine / classic research pages; golden regeneration; rewriting the RS-D5 Grok pack; enabling `assistant.study_tools`; changing `PREVIEW_EXPAND_CAP` or `preview.py` import allow-list; writing `experiment.yaml` from the page; lazy `study/__init__.py` (optional hardening, not D9) |
| **Regression** | |
| | RS-D8 preview behavior unchanged (cap, matched stage estimate, no `execute` import). |
| | RS-D2 inspect + Refresh unchanged. |
| | CLI `study run` argv and `run_study` gates **unchanged** (the child **is** the runner). |
| | RS6 tools remain default-off; the page must not call them. |
| | No `engine/` edits; no `run` / `run_batch` semantic change; no golden regeneration. |
| | USER_GUIDE: prefer extending H2 `Studies viewer (read-only)`. **If** a new H2 is added, amend RQ §7.1.4 + `_USER_GUIDE_SECTIONS` + freeze tests **in the same PR**. |
| **Acceptance checklist** | |
| | ☑ Argv builder: under threshold → no `--confirm`; over threshold without second step → no spawn and no `--confirm` in argv; over threshold + matching bound triple → `--confirm` present |
| | ☑ `--force` absent unless checkbox on; `--workers N` present only when override set and `N >= 1` |
| | ☑ Stale textarea (≠ cached preview YAML) → refuse spawn; armed approval cleared |
| | ☑ Bound-triple mismatch (hash / run_count / output_dir) → refuse spawn |
| | ☑ `preview.expanded is False` → refuse spawn |
| | ☑ Path sandbox: `../` and extra-root absolute paths refused **after pin**; launch YAML not written |
| | ☑ Both `dataset.path` and `dataset.subtimeframe_path` pinned in written `study.launch.yaml` (relative `data/…` does not stay relative to `output_dir`) |
| | ☑ Pinned dataset path that is not an existing file → refuse spawn |
| | ☑ Confirm triple uses **pinned** hash; using `StudyPreview.study_identity_hash` must fail the test |
| | ☑ YAML round-trip: load(`study.launch.yaml`) + normalize + hash equals the triple hash |
| | ☑ `study.output_dir` inside launch YAML is not rewritten; `--output-dir` argv is absolute |
| | ☑ Launch file is `study.launch.yaml`, **not** `study.spec.yaml` |
| | ☑ Spawn helper uses `Popen` (not `wait`); argv is a list; `shell=False`; tests **mock** `Popen` — do not execute cells |
| | ☑ Exclusive pid claim before `Popen` (mocked `O_EXCL` race → second spawn refused) |
| | ☑ Second spawn refused while launch pid is alive (mocked) |
| | ☑ `launch_pid_is_alive` on Windows does not call `os.kill` (AST or monkeypatch guard) |
| | ☑ Windows spawn flags omit `DETACHED_PROCESS`; include `CREATE_NO_WINDOW` + `CREATE_NEW_PROCESS_GROUP`; child env `PYTHONUNBUFFERED=1` |
| | ☑ Streamlit rerun without a new button click does not call spawn (no sticky `should_launch`) |
| | ☑ `preview.py` still must **not** import `thesistester.study.execute` / `run_study` / `run_batch` (existing AST guard stays green) |
| | ☑ `launch.py` AST/import guard: no `thesistester.study.execute` / `run_study` / `run_batch` / `promote_study` / `STUDY.run` |
| | ☑ Page AST: no `run_study` / `promote_study` / `expand_study_to_directory` / `STUDY.run`; session-key allow-list extended for launch keys only |
| | ☑ Inspect Refresh still reloads ledger without rewriting `study.overview.*` |
| | ☑ Honesty visible with launch controls |
| | ☑ Docs: `STUDY_RUNNER.md` §RS-D9 + USER_GUIDE extend + ARCHITECTURE one-liner + AGENT_GUIDE pointer + roadmap status; no new USER_GUIDE H2 (HC allowlist unchanged unless a new H2 is added); optional Grok-pack one-liner that the button is the same CLI, not a second contract |
| | ☑ Existing `tests/study/` + Streamlit/assistant tests green; engine goldens untouched |
| | ☑ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS-D9 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §12.10.
Add a Studies CLI-launch button on the existing pages/15_Studies.py Preview pane
(no new nav slot). After a successful RS-D8 preview, spawn the existing CLI as a
detached subprocess — do NOT call run_study() in-process, do NOT dispatch STUDY.run,
do NOT call run_batch, do NOT change cli_study.py argv or execute.py.

Argv is a list (shell=False; sys.executable -m thesistester):
  study run {output_dir}/study.launch.yaml --output-dir {absolute_output_dir}
  [--workers N] [--confirm] [--force]
Pass --confirm ONLY when run_count >= confirm_above_runs AND a second Confirm-and-run
step echoes the bound triple {pinned_study_identity_hash, run_count, resolved_output_dir}
(RS6 shape; hash recomputed AFTER pin — never StudyPreview.study_identity_hash;
>= matching run_study). One click must not arm confirm and spawn. --force is a separate
checkbox, default off. Omit --workers unless the optional override is set (>= 1).

New module thesistester/study/launch.py. Pipeline: safe_load → normalize/validate →
pin → sandbox → hash → write. Pin BOTH dataset.path and dataset.subtimeframe_path
(promote-style search-roots-then-cwd; search roots = default_study_viewer_roots() then
cwd; do not import promote.py or tools.py). Refuse if a pinned dataset path is not an
existing file. Do not rewrite study.output_dir inside the launch YAML. Write
study.launch.yaml (NOT study.spec.yaml). Display the pinned hash on the pane.

Popen detached: POSIX start_new_session=True and close_fds=True; Windows
CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW (never DETACHED_PROCESS — it drops
redirected stdout so study.launch.log stays empty; never CREATE_NEW_CONSOLE).
Child env PYTHONUNBUFFERED=1. Log to study.launch.log (truncate only on successful
spawn).
Exclusive-create study.launch.pid (O_EXCL) BEFORE Popen; stale dead-pid files may be
unlinked. launch_pid_is_alive: POSIX os.kill(pid, 0); Windows ctypes OpenProcess —
NEVER os.kill on Windows. No psutil. pid + study.launch.json.

launch.py and preview.py must NOT import thesistester.study.execute. launch.py must
NOT import thesistester.study.viewer (trusted roots are inlined). Do not add launch
to study/__init__.py. Do not acquire .study.lock in the Streamlit process. Package init
already imports execute (D8); D9 invariant is do not CALL run_study.

Refuse spawn when: textarea != cached preview YAML; bound triple mismatch;
preview.expanded is False (over PREVIEW_EXPAND_CAP); output_dir / dataset path outside
RS-D2 roots (after pin); pinned CSV missing; launch pid still alive or O_EXCL lost.
Do not re-expand at spawn. Do not store should_launch=True in session_state.
Studies-scoped keys only (no collision with studies_viewer_path_input / STUDIES_PREVIEW_*).
No Promote / enable-batteries. Progress = existing Inspect Refresh. Honesty required
(prefer new output_dir; identity mismatch needs --force; start Streamlit from repo root).
Prefer extend USER_GUIDE H2 Studies viewer (read-only); HC allowlist only if a new H2
is added. Tests: mock Popen (do not run cells); subtimeframe pin; pinned-hash triple
(not preview hash); YAML round-trip hash; O_EXCL race; Windows pid helper must not
call os.kill; argv list with absolute --output-dir. §4.2.
```

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
11. (RS-D8) Paste canonical StudySpec YAML in the Studies preview pane to see cell count / confirm gate. Watch in-flight CLI runs via ledger refresh.  
12. (RS-D9) After a successful preview, **Run via CLI** / **Confirm and run** spawns the same `python -m thesistester study run` argv (detached). Progress remains Inspect Refresh. Promote stays CLI.

---

## 14. Documentation plan

| Doc | When | Change |
|---|---|---|
| `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | RS0 / post-MVP lock | This plan; status updates per PR |
| `STUDY_RUNNER.md` | RS1–RS5 ✅; each post-MVP PR | Living operator contract |
| `ENGINEERING_ROADMAP.md` | each PR | RS status row + post-MVP sequence |
| `AGENT_GUIDE.md` | RS3 ✅; RS6 | Headless study commands + `study_tools` flag |
| `ARCHITECTURE.md` | RS3 ✅; RS-D2; **RS-D8**; **RS-D9** | Boundary notes (study module; Studies viewer + preview + CLI spawn) |
| `ASSUMPTIONS_AND_LIMITATIONS.md` | RS4 ✅; RS-D4 | Study ranking / rollup honesty |
| `METRICS_GLOSSARY.md` | RS4 ✅; RS-D7 | Overview / index PF + WR columns |
| `USER_GUIDE.md` | RS5 ✅; RS-D2; **RS-D8**; **RS-D9** | Studies viewer how-to; extend same H2 for preview + CLI spawn (HC allowlist only if new H2) |
| `README.md` (root) | RS5 ✅ | One-liner pointer |
| Grok docs | RS6 minimal recipe; **RS-D5** ✅ full pack (`STUDY_RUNNER_GROK_ROUTINE_PACK.md` + `examples/studies/agents/`) | External agent recipes (no divergent forks) |
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
| Help corpus drift | HC allowlist PR when USER_GUIDE **adds an H2** (RS5, RS-D2, RS-D8/D9 if new title) |
| Naming collisions / invalid run names | `_RUN_NAME_RE` + output_dir isolation |
| Merging study factorial with combo attribution | Explicit §3.4 boundary; separate docs |
| Treating study emission rules as R18 validator law | Docs call out study-only rules (`min=max=len`, anchor `selected_levels=[]`) |
| Agent tools silently enable large runs | **RS6 default-off** (handlers refuse); two-step `EXPLICIT_CONFIRMATION`; parity fixtures |
| Bare `confirmed=True` / habitual boolean set by LLMs | Approval payload bound to `(study_identity_hash, run_count, output_dir)` — orchestrator flag alone insufficient |
| Soft-resume leaves PF/WR null on healthy pre-D7 rows | RS-D7 field-level backfill when ok+bundle and PF/WR missing |
| Greenfield MCP runtime / voice MCP bleed | RS6 = registry capabilities only; voice keeps MCP denied |
| Studies UI becomes a second runner | **RS-D2 inspect** + **RS-D8 preview** stay non-execute; **RS-D9** may only spawn the existing CLI argv (no in-process `run_study` / `STUDY.run`); two-step bound confirm; button-click spawn only; `preview.py` / `launch.py` must not import `execute.py` |
| Streamlit rerun respawns a study | Spawn only in `st.button` true branch; exclusive-create `study.launch.pid` before `Popen`; refuse if pid alive or `O_EXCL` lost; no sticky `should_launch` session flag |
| Confirm collapsed to one click / `--confirm` leaked under threshold | Two-step when `run_count >= confirm_above_runs`; bound triple `{pinned_hash, run_count, resolved_output_dir}` (never `StudyPreview.study_identity_hash`); `--confirm` omitted otherwise |
| Launch YAML reinterprets relative dataset paths | Pin **both** `dataset.path` and `dataset.subtimeframe_path` (search-roots-then-cwd) into `study.launch.yaml`; never write `study.spec.yaml` from the page; sandbox RS-D2 roots **after pin**; refuse missing CSV |
| Confirm triple uses preview hash after pin | Recompute hash on the pinned spec; YAML round-trip test; show pinned hash on the pane |
| `os.kill(pid, 0)` on Windows | Portable `launch_pid_is_alive`: POSIX `os.kill`; Windows `OpenProcess` — never `os.kill` on NT |
| Two tabs double-spawn | `O_EXCL` pid claim before `Popen`; stale dead-pid unlink then claim |
| UI launch identity ≠ prior CLI ledger | Bind confirm to **pinned** spec hash; prefer a new `output_dir`; `--force` remains explicit (not a resume shortcut) |
| Page blocks on large factorials at spawn | Detached `Popen`; do not re-`expand_study` at spawn; over-cap (`expanded=False`) refuse |
| Job-queue scope creep | No scheduler / retry / kill UI; detached spawn is not a daemon |
| Shorthand/NL paste silently “fixed” into a study | RS-D8 fail-closed on canonical schema only; NL compiler stays parked RS-D1 |
| Preview expand of huge factorials hangs the app | `PREVIEW_EXPAND_CAP=2000`; over-cap returns **matched** estimate without `expand_study`; spinner while expanding |
| Filter estimate overcounts vs expand | Estimate uses `_apply_stage_filter` intersection, not raw include-list lengths |
| Preview imports the runner (`execute.py`) | Import allow-list: schema + expand only; battery hints from constants |
| Save YAML clobbers a completed study | Never default to inspect dir `study.spec.yaml`; sandbox + overwrite force |
| Preview writes experiment.yaml / starts cells | `preview.py` forbids importing `execute` / `run_experiment` / `run_batch` and calling `expand_study_to_directory`; AST+import guard |
| Grok invents setups / bypasses confirm | **RS-D5** hard rules + RS6 minimal recipe; closed StudySpec only |
| Rollup invents cross-cell PBO / statistical proof | **RS-D4** per-cell compose-only; null/`not_run` when batteries absent |
| Expecting PBO on default study cells | Docs: overfitting needs grid sequences; survivor opt-in |
| Post-MVP scope creep / reordering | §12.0 sequence lock (no escape hatches); parked D1/D3/D6; D8 does not reopen D1; D9 does not reopen in-process execute |

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

1. **RS-D7:** additive index `profit_factor` + `win_rate`; soft-resume full rehydrate + field backfill; ordered CLI↔study parity; NaN→null; `inf` CSV documented; report prefers index.  
2. **RS6:** registered-but-disabled-by-default `STUDY.*` capabilities; two-step bound approval; minimal CLI recipe; assistant defaults unchanged when off; no MCP server.  
3. **RS-D2:** read-only Studies viewer over artifacts; honesty visible; no session mutation; HC allowlist if USER_GUIDE grows.  
4. **RS-D4:** per-cell compose-only diagnostic rollup; no cross-cell PBO; null/`not_run` when batteries absent.  
5. **RS-D5:** external routine pack documented; no product host embedding.  
6. **RS-D8:** Studies page preview pane validates canonical YAML + in-memory expand under cap 2000; matched stage estimate; constants battery hints; no `execute.py` import; ledger watch is read-only Refresh.  
7. **RS-D9:** Studies page spawns the existing `study run` CLI (detached); two-step bound confirm over threshold using the **pinned** identity hash; pin both dataset path keys; exclusive pid claim + portable pid-alive; `study.launch.yaml` + pid/log; no in-process `run_study`; no CLI/execute edits; no job queue.  
8. Parked items (D1/D3/D6) remain out of critical path unless this plan is amended.

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
| RS-D7 Additive index PF + win_rate | ✅ |
| RS6 Default-off `STUDY.*` assistant capabilities | ✅ |
| RS-D2 Studies viewer (read-only) | ✅ |
| RS-D4 Per-cell diagnostic rollup | ✅ |
| RS-D5 Grok Bot routine pack | ✅ |
| RS-D8 Studies authoring preview | ✅ |
| RS-D9 Studies CLI-launch button | ✅ |
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

### 18.4 Post-MVP review contracts (prior amendment)

25. Sequence swapped to **RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5**; removed “D7 may land before RS6” escape hatch.  
26. RS6 = `FEATURE_PARITY_REGISTRY` `STUDY.*` capabilities + default-off flag; **no greenfield MCP server** (docs-only descriptor appendix at most; voice MCP stays denied).  
27. RS6 confirm = two-step `EXPLICIT_CONFIRMATION` / approval bound to `(study_identity_hash, run_count, output_dir)` — not bare `confirm=true`.  
28. RS6 tool parity: `force` / workers / soft-resume / identity mismatch / promote overwrite; structured dicts must `validate_study_spec` first.  
29. RS-D7 locks **both** `profit_factor` and `win_rate`; null on failed/pending; `±inf` CSV strings; extends `R18_INDEX_METRIC_KEYS`.  
30. RS-D2: reuse report/ledger loaders; no research `session_state` mutation; `bundle_path` listing not false Research-Bundles deep-link; path sandbox note.  
31. RS-D4 renamed/clarified as **per-cell diagnostic rollup** — no cross-cell PBO/DSR; overfitting fields require grid sequences; survivor opt-in recipe documented.  
32. RS6 vs RS-D5 docs split (minimal recipe vs full routine pack).  
33. §5.1/§5.2 updated for shipped MVP + post-MVP `tools.py` / `rollup.py` / Studies page.  

### 18.5 Implementability polish (prior amendment)

34. §3.2 marked historical pre-MVP; living status is §17 / roadmap.  
35. §10 regression table extended with post-MVP allow-list (cli index / assistant registry / one Studies page).  
36. RS-D7: column order after `max_drawdown_r`; soft-resume `_index_row_from_existing_bundle` must rehydrate PF/WR; §12.8 first-PR kickoff.  
37. RS6: `[assistant.study_tools]` config pattern; clarify `ConfirmationLevel.EXPLICIT_CONFIRMATION` vs `OrchestrationStatus.APPROVAL_REQUIRED`; bound approval triple; no new ConfirmationLevel members.  
38. RS-D2: prefer `pages/15_Studies.py` as next free nav slot.

### 18.6 Code-audit hardening for next-wave perfection (this amendment)

39. §7 artifacts note corrected: study index already has `status`; PF/WR remain the RS-D7 gap (not “status missing”).  
40. **RS-D7 soft-resume field backfill:** pre-D7 ok rows with trade_count/expectancy but missing PF/WR must get PF/WR from the bundle without requiring a full rehydrate (today’s repair only fires when both core metrics are missing).  
41. RS-D7: NaN → null; `±inf` via native float + pandas CSV (no custom serializer); **ordered** CLI↔study key parity; do not add `win_rate` as StudySpec primary_metric; update `report.py` docstring in the D7 PR.  
42. **RS6 registry posture:** always register `STUDY.*`, handlers refuse when `[assistant.study_tools] enabled` is false/missing (deterministic registry-audit).  
43. RS6: all four capabilities `EXECUTABLE`; confirm levels `NONE`/`NONE`/`EXPLICIT`/`NONE` for expand/report/run/promote; approval object on `AssistantRequest.payload`; `confirmed=True` alone insufficient over threshold.  
44. §12.8 kickoff expanded with field-backfill + ordered-parity + focused test matrix.  

### 18.7 RS-D5 ship

45. External Grok routine pack landed as docs/examples only:
   `docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md` + `examples/studies/agents/`
   (SYSTEM + stage-first / confirm-bound / survivor-diagnostics prompts).  
46. Extends RS6 minimal confirm recipe (bound approval / CLI `--confirm`); no
   product host, RabbitMQ, or MCP server; `assistant.study_tools` remains
   default-off.  
47. At D5 ship, the then-sequenced post-MVP track (D7→RS6→D2→D4→D5) was marked complete; parked D1/D3/D6 unchanged. **Superseded for “what’s next” by §18.8 (RS-D8).**

### 18.8 RS-D8 authoring-preview sequence (this amendment)

48. Sequenced **RS-D8** after RS-D5: Studies **authoring preview** on the existing `pages/15_Studies.py` (no new nav slot).  
49. Canonical `schema_version: 1` YAML only — **not** RS-D1 NL compiler, **not** a shorthand dialect, **not** a form-based factor builder in D8 (builder is the separate SB series; marketplace stays a non-goal).  
50. Preview = `yaml.safe_load` → normalize/validate → in-memory `expand_study` under `PREVIEW_EXPAND_CAP=2000`; show `run_count`, `cartesian_product`, matched staged vs unstaged, `needs_confirm`, `workers`, identity hash, constants battery flags.  
51. **No** in-app `study run` / promote / expand-to-disk; execute remains CLI/RS6. Optional Save YAML is text-only under the RS-D2 path sandbox and **must not** default to inspect `study.spec.yaml`.  
52. Progress = read-only ledger **Refresh** of an existing `output_dir` (auto-refresh optional default-off; button-only expected). Do not spawn execution from the page.  
53. Honesty required on every successful preview; Studies-scoped session keys only (no collision with `studies_viewer_path_input`); import+AST guard — `preview.py` must not import `execute.py`.  
54. Filter estimate uses `_apply_stage_filter` **intersection**, not raw include-list lengths.  
55. USER_GUIDE: prefer extending H2 `Studies viewer (read-only)`; HC §7.1.4 allowlist only if a new H2 is added.  
56. §12.0 / §12.1 / status tracker / risks / §16.2 / docs plan updated; next code PR = RS-D8 only.

### 18.9 RS-D8 ship

57. `thesistester/study/preview.py` + Studies **Preview StudySpec** pane; inspect **Refresh**; no Save YAML in D8 MVP.  
58. USER_GUIDE H2 `Studies viewer (read-only)` extended (no new H2 / no HC allowlist change).  
59. Sequenced post-MVP track through RS-D8 marked complete; parked D1/D3/D6 unchanged. **Superseded for “what’s next” by §18.10 (RS-D9).**

### 18.10 RS-D9 CLI-launch sequence (this amendment)

60. Sequenced **RS-D9** after RS-D8: Studies **CLI-launch button** on the existing `pages/15_Studies.py` Preview pane (no new nav slot).  
61. **Single CLI execute path preserved:** the child is `sys.executable -m thesistester study run` → `cli_study._cmd_run` → `run_study`. The page must **not** call `run_study()` in-process, must **not** dispatch `STUDY.run`, must **not** call `run_batch`, and must **not** change `cli_study.py` argv or `execute.py`.  
62. New module `thesistester/study/launch.py`: argv builder + dataset-path pin + detached `Popen` + `study.launch.yaml` / `.log` / `.pid` / `.json`. **Must not import** `execute.py`. Do not add `launch` to `study/__init__.py`. `preview.py` import allow-list unchanged.  
63. Confirm = CLI parity (`run_count >= confirm_above_runs`): under threshold → **Run via CLI** without `--confirm`; over threshold → two-step bound triple `{pinned_study_identity_hash, run_count, resolved_output_dir}` (RS6 shape; hash after pin) then **Confirm and run** with `--confirm`. One click must not arm and spawn. `--force` is a separate default-off checkbox.  
64. Refuse spawn when textarea ≠ cached preview YAML, bound triple mismatches, `preview.expanded is False` (over cap 2000), paths escape RS-D2 roots, pinned CSV missing, or launch pid is still alive / `O_EXCL` lost. Do not re-`expand_study` at spawn.  
65. Pin relative `dataset.path` **and** `dataset.subtimeframe_path` (search-roots-then-cwd; roots = viewer roots then cwd) so a YAML written under `output_dir` cannot reinterpret `data/es_1m.csv`. Refuse spawn if a pinned path is not an existing file. Never write `study.spec.yaml` from the page; never default output_dir to the Inspect dir; do not rewrite `study.output_dir` inside the launch YAML.  
66. Detached spawn is **not** a job queue: no retry/watchdog/kill UI; progress remains Inspect **Refresh**. Streamlit reruns must not respawn (button-click only; no sticky `should_launch`).  
67. USER_GUIDE: prefer extending H2 `Studies viewer (read-only)`; HC §7.1.4 allowlist only if a new H2 is added.  
68. §12.0 / §12.1 / status tracker / risks / §16.2 / docs plan updated; next code PR = **RS-D9 only**. Parked D1/D3/D6 unchanged.

### 18.11 RS-D9 review-contract amend

69. Confirm triple hash is the **pinned** spec (`pinned_study_identity_hash`); **never** `StudyPreview.study_identity_hash`. YAML round-trip hash test. Show pinned hash on the launch pane.  
70. Pin helper iterates `("path", "subtimeframe_path")`. Pipeline: normalize → pin → sandbox → hash → write.  
71. Exclusive-create `study.launch.pid` (`O_EXCL`) **before** `Popen`; stale dead-pid unlink. Portable `launch_pid_is_alive`: POSIX `os.kill(pid, 0)`; **Windows never `os.kill`** (`ctypes` `OpenProcess`). No `psutil`. PID reuse accepted (local single-user).  
72. Detach flags named: POSIX `start_new_session=True` + `close_fds=True`; Windows `CREATE_NEW_PROCESS_GROUP` + `CREATE_NO_WINDOW` (**not** `DETACHED_PROCESS`). Child env `PYTHONUNBUFFERED=1`. Argv is a list; `shell=False`.  
73. Package `__init__.py` already imports `execute` (D8); D9 invariant is do not **call** `run_study` / do not take `.study.lock` in the UI. Lazy `__init__` out of D9 scope.  
74. Prefer new `output_dir` for UI launches; existing CLI dir identity mismatch refuses without `--force`. Start Streamlit from repo root. Copy-ready prompt + risks + `STUDY_RUNNER.md` §RS-D9 updated.

### 18.12 RS-D9 ship

75. `thesistester/study/launch.py` + Studies **Run via CLI** / **Bind confirm** / **Confirm and run** on the Preview pane; detached `Popen`; `study.launch.yaml` (not `study.spec.yaml`); exclusive pid claim; pinned-hash confirm.  
76. USER_GUIDE H2 `Studies viewer (read-only)` extended (no new H2 / no HC allowlist change).  
77. Sequenced post-MVP track through RS-D9 marked complete; parked D1/D3/D6 unchanged.

### 18.13 RS-D9 Windows log-handle follow-up

78. Windows spawn must **not** set `DETACHED_PROCESS` when stdout/stderr are redirected to `study.launch.log` (handles are not inherited; log stays empty; `CREATE_NO_WINDOW` is ignored when combined with it). Use `CREATE_NEW_PROCESS_GROUP` + `CREATE_NO_WINDOW`. Child env `PYTHONUNBUFFERED=1`. Streamlit `Ignoring changed path` under `results/` is the file watcher, not the study log.
