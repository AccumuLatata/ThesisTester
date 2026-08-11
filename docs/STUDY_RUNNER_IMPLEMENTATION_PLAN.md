# Research Study Runner — Implementation Plan (RS)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-11  
**Status:** Plan-locked (RS0) — implementation not started  
**Series code:** **RS** (Research Study Runner)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Related living docs:** `docs/AGENT_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/otf-filter.md`  
**Depends on (already shipped):** R18 headless API + batch CLI (`thesistester/api.py`, `thesistester/cli.py`), RunSpec validation, research bundles, `results_index.csv`

**Supersedes:** conversational design notes about an autonomous research bot / Grok Bot coworker (those remain usage patterns; this plan is the product contract).

---

## 1. Purpose

Ship an **additive, headless Research Study Runner** so a researcher (or an external agent such as Grok Bot) can:

1. Declare a **closed multi-factor study** (e.g. pdPOC × MA partners × confluence modes × entries × OTF).
2. **Expand** that study into a deterministic R18 experiment YAML.
3. **Execute** unattended via the existing batch runner.
4. **Aggregate** results into an honest overview (ranked cells, factor effects, OTF ΔR, sample-size warnings).

The runner must remain **independent of Streamlit day-to-day use**: no engine, fill, confluence-math, or page behavior changes in the core series. Classic UI and assistant confirmation flows keep working unchanged while RS lands.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Research Study Runner |
| Package home | `thesistester/study/` (additive module; not a separate repo) |
| Primary surface | CLI: `python -m thesistester study {expand,run,report}` |
| Compute core | Existing `run_batch` / `run_experiment` only |
| Engine / golden impact | **None** for RS1–RS5 (no `engine/` edits) |
| Streamlit / pages impact | **None** for RS1–RS5 |
| Assistant / MCP impact | Optional RS6 only; default-off tools |
| NL / LLM compiler | Explicitly deferred (RS-D1); closed YAML StudySpec is the contract |
| External Grok Bot | Out of repo scope; consumes CLI/MCP after RS5/RS6 |
| Strategy generation | **Non-goal** (aligns with `ENGINEERING_PROPOSAL.md` §2.2) |

**Feasibility:** High. R18 already parallelizes independent RunSpecs and writes bundles + `results_index.csv`. The missing product surface is **study expansion + ledger + aggregation**, not new simulation semantics.

---

## 3. Problem statement

### 3.1 User need

Researchers want to say (conceptually):

> Test pdPOC with SMA 50/200 and EMA 21 on 1/5/30m; for each pairing always cover global + anchor, both directions, multiple entries including 3c on multiple trigger TFs, and measure how OTF across TFs changes R.

Today that requires hand-authoring dozens/thousands of YAML runs, no study identity, and weak cross-run analysis beyond `results_index.csv`.

### 3.2 Gaps today

| Desired | Current state |
|---|---|
| Closed multi-factor confluence/level sweep | Missing (grid sweeps SL/TP, not confluence axes) |
| Deterministic expansion with run-count preview | Missing |
| Confirm gate before large unattended batches | Missing (CLI runs immediately) |
| Study-level ledger of every attempted cell | Partial (per-run bundles only) |
| Factor / OTF Δ overview | Missing |
| Agent-operable study surface | R18 run-level only |

### 3.3 Why not “just let an LLM drive Streamlit”

- UI automation is fragile and non-reproducible for scientific claims.
- Free-form agent loops invite setup invention (anti-roadmap: genetic/LLM strategy generation).
- Classic research UX must stay undisturbed during implementation.

---

## 4. Goals and non-goals

### 4.1 Goals

1. **StudySpec v1** — versioned, fail-closed schema for closed factorial (and staged) studies.
2. **Deterministic expander** — StudySpec → R18 `experiment.yaml` with stable run names and factor tags.
3. **Dry-run / confirm** — expand + count + estimated cost; refuse or require `--confirm` above a threshold.
4. **Study runner** — invoke existing batch machinery; write study artifacts beside run bundles.
5. **Aggregator** — overview tables from `results_index.csv` + study factor map (expectancy, PF, DD, N, OTF Δ).
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
│  schema → expand → ledger → report                       │
└──────────────────────────────┬───────────────────────────┘
                               │ experiment.yaml (R18)
                               ▼
┌──────────────────────────────────────────────────────────┐
│ thesistester/{api,cli}.py    EXISTING (untouched logic)  │
│  run_batch → run_experiment → bundles + results_index    │
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
  ledger.py            # study manifest + cell registry
  report.py            # aggregate overview from index + factor map
  cli_study.py         # argparse handlers (wired from __main__/cli)
docs/STUDY_RUNNER.md   # user/agent contract (lands RS1, grows each PR)
tests/study/           # unit + golden expand fixtures
```

### 5.3 Design principles

1. **Sidecar-in-package:** lives beside R18; does not import Streamlit; does not mutate engine modules.
2. **Fail-closed unknown keys** on StudySpec (same spirit as RunSpec validation).
3. **Expansion purity:** `expand(study) -> experiment` is pure and golden-testable without market data.
4. **Execution thinness:** runner writes files then calls `run_batch` (or subprocess `python -m thesistester run` — prefer in-process `run_batch` for determinism/tests).
5. **Factor tags travel with every cell** so aggregation never parses run names as the sole identity.
6. **Default-off integration:** no assistant/page wiring until RS6.

---

## 6. StudySpec v1 contract (normative)

### 6.1 Top-level shape

```yaml
schema_version: 1
study:
  name: pdPOC_ma_confluence_battery   # filesystem-safe
  description: optional
  output_dir: results/studies/pdPOC_ma_confluence_battery
  workers: 4
  confirm_above_runs: 200             # require --confirm if expansion >= N

  dataset:                             # R18 dataset mapping (pass-through)
    path: data/es_1m.csv
    instrument: ES
    source_timezone: America/New_York

  levels:                              # R18 levels mapping (pass-through + defaults)
    sma_lengths: [50, 200]
    ema_lengths: [21]
    sma_timeframes: [1min, 5min, 30min]
    ema_timeframes: [1min, 5min, 30min]

  constants:                           # applied to every run; not swept
    direction: both
    tolerance_ticks: 0                 # global_cluster shared tol
    min_confluences: 2
    max_confluences: 2
    min_valid_confluences: 1           # anchor mode
    naked_only: false
    naked_requirement: any
    trigger_params: {}
    backtest:
      stop_loss_ticks: 8
      take_profit_ticks: 16
      exposure_policy: single_position
    grid: { enabled: false }
    validation: { enabled: false }

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
    # How factors map into setup fields
    global_cluster:
      selected_levels: ["${core_level}", "${partner_levels...}"]
    anchor_rules:
      anchor_level: "${core_level}"
      confluence_rules:
        from_partners: required        # each partner → required rule @ constants.tolerance_ticks
    # Forbidden: partner_levels empty; core_level multi-value without explicit product intent

  report:
    primary_metric: expectancy_r
    secondary_metrics: [profit_factor, max_drawdown_r, trade_count, total_r]
    min_trades: 30
    group_by: [partner_levels, confluence_mode, trigger, trigger_timeframe, otf]
    otf_baseline: { enabled: false }   # Δ metrics vs this factor level
    multiple_testing: warn             # warn | error (error refuses “best cell” summary)

  stage: null                          # optional; see §6.3
```

### 6.2 Expansion semantics (locked)

1. Cartesian product over `factors` keys (order = YAML key order for stable naming).
2. Each cell becomes one R18 run with:
   - `name`: deterministic slug from study name + factor hash/short encoding (`naming.py`).
   - `setup`: built via existing `build_setup` / normalized dict — **never** hand-rolled invalid keys.
   - `study_factors`: mirrored into study ledger (not required inside RunSpec if unknown-key fail-closed forbids it; keep factor map in study artifacts).
3. `direction: both` is one run (engine already supports it). Do **not** expand long/short unless `direction` is listed under `factors`.
4. Trigger timeframe domain = existing `VALID_TRIGGER_TIMEFRAMES` (`base`, `1min`, `5min`, `15min`). Reject `30min` trigger at validate time with a clear error.
5. OTF domain = existing OTF config validator (`normalize_otf_filter_config`).
6. Level column names for multi-TF MAs follow product naming: `SMA_{len}_{tf}`, `EMA_{len}_{tf}`.
7. Unknown StudySpec keys → validation error. Pass-through blocks (`dataset`, `levels`, `backtest`) are validated by existing RunSpec validators **after** expansion (each run).

### 6.3 Staging (v1 support, recommended default practice)

Optional `stage` block to avoid accidental 1–2k-run fishing:

```yaml
stage:
  mode: filter          # filter | explicit_cells
  include:
    trigger: [touch]
    trigger_timeframe: [base]
  # Later stages reference prior study output survivors — RS5 may add
  # `from_report: { study_dir, top_n, metric }` as additive schema_version: 1 field
  # if tests prove fail-closed behavior; otherwise ship in RS5.1.
```

MVP (RS1–RS2): support `mode: filter` only (subset axes before product).  
RS5: add survivor promotion helper (read prior overview → new StudySpec draft).

### 6.4 Confirm policy

| Condition | Behavior |
|---|---|
| `expand` | Always allowed; prints run count + writes preview artifacts |
| `run` and count < `confirm_above_runs` | Allowed |
| `run` and count ≥ `confirm_above_runs` without `--confirm` | Exit non-zero with message |
| `run --confirm` | Allowed; ledger records confirmation timestamp + count |

---

## 7. Artifacts (study output contract)

For a study named `S` written to `output_dir`:

| Artifact | Writer | Purpose |
|---|---|---|
| `study.spec.yaml` | expand/run | Canonical normalized StudySpec copy |
| `study.expansion.json` | expand | Factor map: `run_name → factors` |
| `experiment.yaml` | expand | R18 batch file |
| `study.ledger.json` | run | Status per cell (`pending/running/ok/failed`), timestamps, bundle paths |
| `*.research.zip` | R18 | Per-run bundles (unchanged) |
| `results_index.csv` | R18 | Per-run metrics (unchanged) |
| `study.overview.csv` | report | Joined index + factors |
| `study.overview.md` | report | Human/agent summary with honesty caveats |
| `study.otf_delta.csv` | report | Optional; metrics vs OTF baseline factor |

Canonical study identity hash (RS2): hash normalized StudySpec bytes (stable key order) — used in ledger, not for bundle equality.

---

## 8. CLI surface

```bash
# Preview only (no backtests)
python -m thesistester study expand path/to/study.yaml --output-dir out/study1

# Execute (calls run_batch on generated experiment.yaml)
python -m thesistester study run path/to/study.yaml --output-dir out/study1 [--workers N] [--confirm]

# Aggregate after runs (or re-run report)
python -m thesistester study report out/study1
```

Wiring: extend `thesistester/cli.py` / `__main__.py` with a `study` subparser **without** changing `run` behavior or defaults.

---

## 9. Aggregation / overview contract

### 9.1 Join

`study.overview.csv` = `results_index.csv` ⟕ `study.expansion.json` on `run_name` / `name`.

### 9.2 Required columns (minimum)

Factor columns + `trade_count`, `expectancy_r`, `total_r`, `max_drawdown_r`, `bundle_hash`, `bundle_path`, `status`.

### 9.3 Derived views

1. **Ranked cells** by `primary_metric` with `trade_count >= min_trades`.
2. **Group summaries** for each `report.group_by` key (median/mean expectancy, cell counts).
3. **OTF delta:** for each non-OTF factor tuple, compute metric(OTF variant) − metric(baseline OTF factor).
4. **Honesty block** in Markdown: multiple-testing warning, N filter, “descriptive study ranking ≠ validated edge”.

### 9.4 Explicitly out of MVP report

- Automatic WFA/PBO per cell (cells may enable validation in `constants`, but report does not re-battery).
- Pareto frontiers / Bayesian optimization.
- Natural-language LLM narrative (external coworker may add that from `study.overview.md`).

---

## 10. Regression-safety binding

Every RS PR must satisfy `ENGINEERING_PROPOSAL.md` §4.2:

| Gate | RS1–RS5 expectation |
|---|---|
| Golden masters | Untouched; suite remains green; **no** regeneration |
| Engine / pages | No edits (allow-list exceptions only in RS0 docs / RS6 assistant tools) |
| Defaults | Existing `python -m thesistester run` identical |
| Schema | StudySpec versioned; unknown keys fail closed |
| Docs | `STUDY_RUNNER.md` + this plan status + roadmap row updated same PR |
| Tests | Expander golden + validator negatives + report join fixtures |
| PIT | No new causality claims; inherit RunSpec/PIT docs |

**Forbidden in RS1–RS5:** edits under `thesistester/engine/`, `thesistester/levels/` (except read-only imports of validators/constants if needed), `pages/`, fill/signal semantics.

Allowed read-only imports: `setup` validators/constants, `otf` normalize, `cli.run_batch`, `api.validate_run_spec` / `build_setup`.

---

## 11. PR sequence (fully scoped)

### RS0 — Plan lock (this document)

| | |
|---|---|
| **Scope** | Add `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`; index in `docs/README.md` + `docs/ENGINEERING_ROADMAP.md` |
| **Code** | None |
| **Tests** | None |
| **Acceptance** | Plan reviewed; series RS1–RS5 scopes unambiguous; non-goals locked |
| **Risk** | None |

---

### RS1 — StudySpec schema + validation (no execution)

| | |
|---|---|
| **Scope** | `thesistester/study/schema.py` (+ `__init__.py`); `docs/STUDY_RUNNER.md` (schema section); `tests/study/test_study_schema.py` |
| **Behavior** | Load YAML → normalize → validate; reject unknown keys; validate factor domains against known trigger/OTF/confluence enums; validate `confirm_above_runs >= 1`; filesystem-safe `study.name` |
| **Out of scope** | Expansion to runs; CLI; engine; pages |
| **Regression** | No existing module behavior change |
| **Acceptance checklist** | |
| | ☐ Valid minimal StudySpec fixture normalizes stably |
| | ☐ Unknown top-level / factor keys fail closed |
| | ☐ Invalid trigger / trigger_timeframe / otf rejected with actionable errors |
| | ☐ `direction` in constants allowed; listing unsupported factor axes errors clearly |
| | ☐ Docs describe schema_version: 1 |
| | ☐ `pytest -q tests/study/test_study_schema.py` green; full suite green |

**Copy-ready agent prompt:**

```text
Implement RS1 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS1.
Add thesistester/study/schema.py (+ package init) and docs/STUDY_RUNNER.md schema section.
Fail-closed unknown keys. Validate against existing trigger/OTF/confluence enums.
No engine/pages/cli execution. Tests under tests/study/. Update roadmap status RS1.
Follow ENGINEERING_PROPOSAL.md §4.2. Keep classic UI undisturbed.
```

---

### RS2 — Deterministic expander → R18 experiment.yaml

| | |
|---|---|
| **Scope** | `expand.py`, `naming.py`; expand golden fixtures; extend `STUDY_RUNNER.md` |
| **Behavior** | `expand_study(normalized) -> ExpansionResult{experiment, factor_map, run_count}`; map global/anchor mode_rules; call `build_setup` or produce dicts that pass `validate_run_spec` for each cell; write helpers for `study.spec.yaml`, `study.expansion.json`, `experiment.yaml` |
| **Out of scope** | Running backtests; report; confirm enforcement (print count only) |
| **Regression** | Pure functions; no CLI default changes |
| **Acceptance checklist** | |
| | ☐ Golden expansion fixture: byte-stable experiment YAML + factor_map JSON |
| | ☐ Every expanded run passes `validate_run_spec` |
| | ☐ Anchor cells set `anchor_level=core` and required partner rules |
| | ☐ Global cells set `selected_levels=[core]+partners` with min=max=len |
| | ☐ Run names unique + filesystem-safe |
| | ☐ Stage `filter` reduces cartesian product correctly |
| | ☐ Full suite green; no golden-master regeneration |

**Copy-ready agent prompt:**

```text
Implement RS2 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS2.
Add expand.py + naming.py. Deterministic StudySpec→R18 experiment expansion with factor_map.
Golden-test expansion. Every run must pass validate_run_spec. No backtest execution.
No engine/pages changes. Docs + roadmap. Regression-safe per §4.2.
```

---

### RS3 — CLI `study expand` + `study run` (batch invoke + ledger)

| | |
|---|---|
| **Scope** | `cli_study.py`; wire `study` subcommands in `cli.py`/`__main__.py`; `ledger.py`; tests for confirm gate + ledger |
| **Behavior** | `expand` writes artifacts; `run` expands (if needed), enforces confirm policy, calls existing `run_batch`, updates ledger statuses, preserves R18 bundle/`results_index.csv` layout under study `output_dir` |
| **Out of scope** | Overview Markdown intelligence beyond pointing at `results_index.csv`; assistant tools |
| **Regression** | `python -m thesistester run` path must remain behavior-identical (additive subparser only) |
| **Acceptance checklist** | |
| | ☐ `study expand` writes the three artifacts and prints run_count |
| | ☐ `study run` without `--confirm` fails when run_count ≥ confirm_above_runs |
| | ☐ `study run --confirm` executes and ledger marks ok/failed per cell |
| | ☐ Failed cell does not crash entire batch accounting (surface error in ledger; match `run_batch` failure semantics — if `run_batch` currently aborts all-or-nothing, document and keep parity; do not silently change R18 abort semantics) |
| | ☐ Existing CLI run tests still green |
| | ☐ AGENT_GUIDE headless section gains Study Runner pointer |
| | ☐ Full suite green |

**Note on failure semantics:** RS3 must **not** change `run_batch` exception behavior to “continue on failure” unless done in a dedicated additive flag defaulting to legacy abort. Prefer ledger + documented parity first.

**Copy-ready agent prompt:**

```text
Implement RS3 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS3.
Wire `python -m thesistester study expand|run`. Use existing run_batch; do not change its defaults/semantics.
Enforce confirm_above_runs. Write study ledger. Update AGENT_GUIDE + STUDY_RUNNER.md + roadmap.
No engine/pages. §4.2 checklist. Keep `thesistester run` identical.
```

---

### RS4 — Study report / overview aggregator

| | |
|---|---|
| **Scope** | `report.py`; `study report` CLI; fixtures with synthetic `results_index.csv` + expansion map; honesty text in `ASSUMPTIONS_AND_LIMITATIONS.md` + `METRICS_GLOSSARY.md` (study ranking terms) |
| **Behavior** | Join → overview CSV/MD; ranked cells; group_by summaries; OTF delta vs baseline; min_trades filter; multiple_testing warn block |
| **Out of scope** | LLM narrative; UI page; changing bundle schema |
| **Acceptance checklist** | |
| | ☐ Overview join is deterministic and complete for fixture |
| | ☐ Cells below min_trades excluded from “ranked” section but listed under low-N |
| | ☐ OTF delta rows correct vs baseline factor |
| | ☐ Markdown includes multiple-testing honesty paragraph |
| | ☐ Glossary entries for study overview metrics / OTF Δ |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS4 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS4.
Add report.py + `study report`. Emit study.overview.csv/md and otf_delta.csv.
Honesty + glossary updates. No engine/pages. Deterministic fixtures. §4.2.
```

---

### RS5 — Staging helpers + survivor promotion + docs polish

| | |
|---|---|
| **Scope** | Stage filter hardening; `study promote` (or `expand --from-overview`) draft generator; examples under `examples/studies/`; USER_GUIDE short section (Help corpus — coordinate HC allowlist if required); roadmap sign-off for core series |
| **Behavior** | From a completed study dir, generate a **draft** StudySpec containing only selected survivor factor tuples (explicit_cells), still requiring human edit/confirm before run |
| **Out of scope** | Auto-run promotion; assistant NL |
| **Acceptance checklist** | |
| | ☐ Promote writes draft StudySpec; does not execute |
| | ☐ Example pdPOC×MA study YAML present and expands in tests (may use tiny factor subset for CI) |
| | ☐ USER_GUIDE / STUDY_RUNNER end-to-end recipe |
| | ☐ Core series RS1–RS5 marked implemented on roadmap after green CI |
| | ☐ Full suite green |

**Copy-ready agent prompt:**

```text
Implement RS5 only from docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md §11 RS5.
Add survivor promotion draft helper + examples/studies + docs polish.
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
| RS-D3 | Continue-on-failure batch flag | Additive R18 change; separate PR if needed |
| RS-D4 | Study-aware WFA/PBO rollup | Compose existing batteries; do not invent new inference |
| RS-D5 | Grok Bot routine pack | External; document recipe only in RS6 |
| RS-D6 | Multi-partner clusters / tolerance sweeps | New factor types; schema_version bump |

---

## 13. Worked example (acceptance narrative, not a CI mega-grid)

The motivating pdPOC study is **supported** by the schema. CI must **not** run the full ~1–2k-cell grid. Instead:

1. Unit/golden tests use a **2×2×2** miniature (2 partners × 2 modes × 2 OTF) plus one 3c/trigger_tf smoke cell.
2. `examples/studies/pdPOC_ma_confluence_battery.yaml` may contain the full factor lists for humans/agents, with `confirm_above_runs: 200` and a commented `stage.filter` recommended first pass:

```yaml
stage:
  mode: filter
  include:
    trigger: [touch]
    trigger_timeframe: [base]
```

Recommended human workflow after RS5:

1. Stage filter expand/run/report.  
2. Promote survivors.  
3. Open triggers/TFs/3c on the reduced set.  
4. Interpret OTF Δ with multiple-testing caution.

---

## 14. Documentation plan

| Doc | When | Change |
|---|---|---|
| `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | RS0 | This plan; status updates per PR |
| `STUDY_RUNNER.md` | RS1–RS5 | Living operator contract |
| `ENGINEERING_ROADMAP.md` | each PR | RS status row |
| `AGENT_GUIDE.md` | RS3 | Headless study commands |
| `ASSUMPTIONS_AND_LIMITATIONS.md` | RS4 | Study ranking / multiple-testing honesty |
| `METRICS_GLOSSARY.md` | RS4 | Overview / OTF Δ terms |
| `USER_GUIDE.md` | RS5 | Short recipe (HC allowlist if needed) |
| `ARCHITECTURE.md` | RS3 or RS5 | Boundary note: study module → R18 only |
| `README.md` (root) | RS5 | One-liner pointer optional |

---

## 15. Risk register

| Risk | Mitigation |
|---|---|
| Combinatorial fishing / overfitting | confirm gates; stage filter; honesty blocks; no auto-promote |
| Accidental engine edits in agent PRs | PR allow-list in prompts; CI golden gate |
| RunSpec unknown-key clash if factor tags stuffed into setup | Keep factor_map external in study artifacts |
| `run_batch` all-or-nothing failures | Document parity in RS3; defer continue-on-failure |
| Help corpus drift | HC allowlist PR when USER_GUIDE changes |
| Naming collisions across studies | Study output_dir isolation + unique run name slug |

---

## 16. Definition of done (core series RS1–RS5)

1. Researcher can author a closed StudySpec and run `study expand|run|report` without opening Streamlit.  
2. Expansion is deterministic and golden-tested.  
3. Large studies require `--confirm`.  
4. Overview joins factors to metrics with OTF Δ and honesty caveats.  
5. Classic UI, assistant defaults, engine goldens, and `thesistester run` remain undisturbed.  
6. External bot (e.g. Grok Bot) can operate by shelling the CLI; first-class MCP/assistant tools optional in RS6.

---

## 17. Status tracker

| Milestone | Status |
|---|---|
| RS0 Plan lock | ✅ This document |
| RS1 Schema | ☐ |
| RS2 Expander | ☐ |
| RS3 CLI expand/run + ledger | ☐ |
| RS4 Report | ☐ |
| RS5 Staging/promote + examples | ☐ |
| RS6 Optional agent tools | ☐ Deferred until after RS5 |
