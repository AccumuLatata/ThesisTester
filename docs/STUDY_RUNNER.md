# Research Study Runner

**Status:** RS1–RS5 MVP + **RS-D7** + **RS6** + **RS-D2** landed. Post-MVP remaining: **RS-D4 → RS-D5**.  
**Plan:** `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` (§12)  
**Package:** `thesistester.study`

Headless, additive tooling for closed multi-factor confluence studies. Classic
Streamlit research mutate paths and `python -m thesistester run` are unchanged.
RS-D2 adds a **read-only** Studies viewer page over completed study dirs.

This surface answers: *across many closed setups, which factor combinations look
promising?* It is **not** confluence-combo attribution (within-trade membership).

---

## RS1 — StudySpec schema (`schema_version: 1`)

### Load / validate API

```python
from thesistester.study import load_study_spec, normalize_study_spec, validate_study_spec

spec = load_study_spec("path/to/study.yaml")  # load + normalize + validate
```

Fail-closed: unknown StudySpec / study / factors / constants / report / stage keys
raise `StudySpecError`.

### Top-level shape

```yaml
schema_version: 1
study:
  name: pdPOC_mini                    # ^[A-Za-z0-9][A-Za-z0-9_-]*$
  description: optional
  output_dir: results/studies/pdPOC_mini
  workers: 1
  confirm_above_runs: 200
  dataset: { path: data/es_1m.csv, instrument: ES }   # instrument required
  levels: { ... }                     # keys ⊆ DEFAULT_LEVELS_SETTINGS
  constants: { ... }                  # setup + backtest/grid/validation/walk_forward
  factors: { ... }                    # closed axes only
  mode_rules: { ... }                 # required when factors.confluence_mode present
  report: { ... }
  stage: { mode: filter, include: { ... } }   # optional
```

Normalization defaults (when omitted): `workers=1`, `confirm_above_runs=200`,
`description=""`, `output_dir=results/studies/<name>`, and a standard `report`
block (`primary_metric: expectancy_r`, `multiple_testing: warn`, …). Default
`group_by` is the intersection of the preferred axes with this study’s
`factors` (never invents axes the study does not declare).

### Supported factor axes

| Axis | Values |
|---|---|
| `core_level` | non-empty list of closed level tokens |
| `partner_levels` | non-empty list of non-empty partner-sets (lists) |
| `confluence_mode` | `global_cluster`, `anchor_rules` |
| `trigger` | `touch`, `reject`, `break`, `reclaim`, `3c` |
| `trigger_timeframe` | `base`, `1min`, `5min`, `15min` (**not** `30min`) |
| `otf` | list of OTF configs (`normalize_otf_filter_config`); canonical duplicates / aliases fail closed |
| `direction` | optional factor; `long` / `short` / `both` |

Unsupported axes (e.g. `sl_ticks`) fail closed. Partner-sets reject duplicate tokens.

### Closed level token set

A core/partner token is valid if it is in:

1. **Static catalog** — session/profile names including `pdPOC`, `ONH`, `dOpen`,
   `APOC`, single prints, session VWAPs, etc. (see `STUDY_STATIC_LEVEL_NAMES`
   in `thesistester/study/schema.py`), and
2. **Implied by `study.levels`** — `SMA_{len}_{tf}` / `EMA_{len}_{tf}` from
   lengths×timeframes (`null` timeframes → bare `SMA_{len}` / `EMA_{len}` like
   the levels engine; explicit `[]` → no MA tokens), plus `VWAP_rolling_*` /
   `POC_rolling_*` windows, and `prev30mVWAP*` / `Pivot_*` **only when**
   `prev30m_vwap_enabled` / `pivots_enabled` are true in the merged levels
   settings.

Unknown tokens fail at validate time with an actionable error.

### Constants rules (RS1)

- `direction` in constants allowed (`long` / `short` / `both`).
- When `grid` / `validation` / `walk_forward` mappings are present, they **must**
  include explicit `enabled: true|false`. Bare `{}` is rejected (R18 default-on trap).
- `max_confluences` ≤ 5 when provided.
- `dataset` / `backtest` are structural pass-throughs; deep RunSpec validation
  happens after expansion (RS2).
- `levels` keys ⊆ `DEFAULT_LEVELS_SETTINGS`. List fields (`sma_lengths`,
  `ema_lengths`, `*_timeframes`, `vwap_windows`, `poc_windows`,
  `pivot_timeframes`) must be real lists (not strings); lengths must be
  positive ints (not bools). Invalid shapes fail closed as `StudySpecError`.

### Report rules (RS1)

- `schema_version` must be the integer `1` (reject `true` / `1.0`).
- `group_by` keys must be axes present on **this** study’s `factors` (not merely
  any supported axis name).

### Mode rules

Required when `factors.confluence_mode` is present (and forbidden otherwise).

- `global_cluster.selected_levels` must be a **non-empty** list (template strings
  for RS2).
- `anchor_rules.selected_levels` must be `[]`.
- `anchor_rules.anchor_level` must be a non-empty string.
- `anchor_rules.confluence_rules.from_partners` ∈ `{required, optional}`.

### Stage

| Mode | Requirements |
|---|---|
| `filter` | non-empty `include`; keys ⊆ factor axes; each include value ∈ that factor’s domain; no `cells` |
| `explicit_cells` | non-empty `cells`; each cell supplies **every** factor axis with a value ∈ that factor’s domain; no `include` |

### Out of scope for RS1

CLI `study` commands, execution ledger, and overview reporting — see RS3–RS5.

---

## RS2 — Deterministic expansion

### API

```python
from thesistester.study import expand_study, expand_study_to_directory

result = expand_study(spec)  # ExpansionResult
# result.experiment  → R18 experiment mapping (schema_version 1)
# result.factor_map  → {run_name: factors} with canonical OTF
# result.run_count
# result.study_identity_hash

expand_study_to_directory(spec, "out/study1")
# writes study.spec.yaml, study.expansion.json, experiment.yaml
```

No backtests are executed. Every expanded run passes `validate_run_spec`.

### Emission rules

| Mode | Setup fields |
|---|---|
| `global_cluster` | `selected_levels=[core]+partners`; `min_confluences=max_confluences=len`; reject `len>5` |
| `anchor_rules` | `selected_levels=[]`; `anchor_level=core`; one rule per partner (`from_partners` required/optional); placeholder `min/max_confluences=1` |

Also every cell:

- Injects `setup.name` (= run name), `setup.instrument` (= `dataset.instrument`), `setup.description`
- Emits `grid` / `validation` / `walk_forward` with explicit `enabled` (default `{enabled: false}`; never bare `{}`)
- Stores **normalized** OTF (`5m`/`15m`/`30m`) in both setup and factor_map
- Requires `confluence_mode`, `trigger`, and `trigger_timeframe` on every cell (no silent invent)
- Requires non-empty `constants.backtest` with `stop_loss_ticks` / `take_profit_ticks`
- Rejects duplicate partner tokens, partner==core, and OTF alias/canonical duplicates
- Experiment `schema_version` follows R18 `EXPERIMENT_SCHEMA_VERSION` (not StudySpec)

### Staging

| Mode | Expansion |
|---|---|
| omitted / none | Full cartesian product over factor axes (YAML key order) |
| `filter` | Subset listed axes, then cartesian (plan example: 800 → 40 for `touch`+`base`) |
| `explicit_cells` | Exactly the listed cells; no cartesian leakage |

### Run names

Deterministic, unique, match `^[A-Za-z0-9][A-Za-z0-9_-]*$` (same as R18 CLI).
Encoded from study name, cell index, key factors, and a short content fingerprint.

### Golden fixture

`tests/fixtures/study/golden_study.yaml` + `tests/fixtures/study/golden/*` — byte-stable
`experiment.yaml` / `study.expansion.json` / `study.spec.yaml` for an 8-cell mini study.

### Out of scope for RS2

Overview report (RS4) and promote/examples (RS5).

---

## RS3 — CLI expand / run + study-owned ledger

### Commands

```bash
python -m thesistester study expand path/to/study.yaml --output-dir out/study1
python -m thesistester study run path/to/study.yaml --output-dir out/study1 \
  [--workers N] [--confirm] [--force]
```

`python -m thesistester run experiment.yaml` is unchanged (`run_batch` semantics
untouched). Study runs do **not** call `run_batch`; they loop
`run_experiment` → `build_research_bundle` with `execution_origin="study"` and
`cache_policy="read_write"`.

### Confirm / resume / force

| Flag / rule | Behavior |
|---|---|
| `confirm_above_runs` | `study run` refuses when `run_count >= N` unless `--confirm` (**before** rewriting expansion artifacts) |
| Soft resume | Ledger `ok` cells are skipped only when their `bundle_path` zip still exists; missing/null index metrics (incl. RS-D7 PF/WR) are rehydrated from bundle `trade_summary.json`; identity fields prefer prior index row / `dataset_meta.json` |
| `--force` | Re-run all cells; on identity mismatch replaces the ledger (no orphan cells from the prior StudySpec) |
| Workers | `workers>1` uses spawn pool; cell tasks **return** ok/failed payloads (continue-on-failure); pool deaths mark the cell failed |
| Lock | Exclusive `.study.lock` on `output_dir` (fail-closed if another study run holds it) |

### Artifacts (under output_dir)

| File | Role |
|---|---|
| `study.spec.yaml` / `study.expansion.json` / `experiment.yaml` | From expand |
| `study.ledger.json` | Per-cell status (`pending`/`running`/`ok`/`failed`) + confirm record |
| `*.research.zip` | Per-ok-cell bundles |
| `results_index.csv` | R18 metric columns + `bundle_path` + study `status` |

### Cost hints

Expand/run print `run_count`, `workers`, and warn when any cell has
`grid`/`validation`/`walk_forward` enabled.

### Out of scope for RS3

Overview aggregator (`study report`), promote drafts, assistant `STUDY.*` tools.

---

## RS4 — Overview report

### Command

```bash
python -m thesistester study report out/study1
```

Reads a completed study directory (does not re-run backtests).

### Artifacts written

| File | Role |
|---|---|
| `study.overview.csv` | `results_index.csv` ⟕ `study.expansion.json` on `run_name` + resolved PF/win_rate |
| `study.overview.md` | Ranked / low-N / group summaries / OTF Δ + honesty block |
| `study.otf_delta.csv` | metric(OTF variant) − metric(`report.otf_baseline`) per non-OTF factor tuple |

### Join / ranking

- Factor tags flatten to `factor_*` columns (`partner_levels` as `A+B`; `otf` as canonical JSON key).
- Ranked section: `status=ok`, `factors_joined=True`, `trade_count >= min_trades`, non-null `primary_metric`.
- Low-N section: expansion-joined ok cells below `min_trades` (excluded from ranked winners).
- Unresolved section: expansion-joined ok cells meeting `min_trades` but with a null `primary_metric` (e.g. missing PF).
- Index-only orphan rows (`factors_joined=False`) stay in `study.overview.csv` but are excluded from ranked / low-N / unresolved / group summaries / crowning.
- Sort: higher-is-better for `expectancy_r` / `total_r` / `profit_factor` / `trade_count`; lower-is-better for `max_drawdown_r`.
- `multiple_testing: error` suppresses best-cell crowning in Markdown (ranked table still emitted as descriptive).

### Profit factor / win_rate source (RS-D7)

Study + CLI `results_index.csv` writers include additive **`profit_factor`** and
**`win_rate`** columns (immediately after `max_drawdown_r`). Failed/pending rows
leave both null. Soft resume rehydrates/backfills PF/WR from bundle
`trade_summary` when missing. `±inf` PF is stored as float inf; pandas CSV emits
`inf`/`-inf` (report coerces). No Experiment `schema_version` bump.

Report resolves **per field**:

1. Index value when present → for PF, `profit_factor_source=index`
2. Else bundle `trade_summary.json` → `profit_factor_source=bundle`
3. Else `missing`

`win_rate` resolves independently the same way (index then bundle), including
when PF came from the index but `win_rate` did not. Documented in
`METRICS_GLOSSARY.md`.

### OTF Δ

Baseline = normalized `study.report.otf_baseline` (default `{enabled: false}`). Alias-stable via `normalize_otf_filter_config` (`5min` ≡ `5m`). Interpret with multiple-testing caution (`ASSUMPTIONS_AND_LIMITATIONS.md`).

### Out of scope for RS4

LLM narrative, Studies UI page, silent R18 index schema change, promote/examples (RS5).

---

## RS5 — Promote + stage-first examples

### End-to-end recipe

```bash
# 1) Stage-first expand (example → 40 cells)
python -m thesistester study expand \
  examples/studies/pdPOC_ma_confluence_battery.yaml --output-dir out/pdPOC_stage40

# 2) Execute (confirm required when run_count >= confirm_above_runs)
python -m thesistester study run \
  examples/studies/pdPOC_ma_confluence_battery.yaml --output-dir out/pdPOC_stage40 --confirm

# 3) Overview
python -m thesistester study report out/pdPOC_stage40

# 4) Draft survivors (does NOT execute; refuses to overwrite without --force)
python -m thesistester study promote out/pdPOC_stage40 \
  --output drafts/pdPOC_survivors.yaml --top-n 10

# 5) Human edit draft, then expand/run again after confirm
python -m thesistester study expand drafts/pdPOC_survivors.yaml --output-dir out/pdPOC_survivors
```

### `study promote`

| Flag | Behavior |
|---|---|
| `study_dir` | Completed study output (spec + expansion + index/bundles) |
| `--output` | Draft StudySpec path (required); refuses overwrite unless `--force` |
| `--top-n` | Ranked survivors to include (default 10) |
| `--metric` | Optional ranking override (default `report.primary_metric`) |
| `--force` | Replace an existing draft at `--output` |

Draft rules:

- `stage.mode: explicit_cells` with one cell per survivor (every factor axis present)
- Factor domains narrowed to survivor values (cartesian skipped by explicit_cells)
- Relative `dataset.path` / `subtimeframe_path` are absolutized when possible so drafts under `drafts/` do not reinterpret bars paths against the draft parent
- Header comments mark **DRAFT**; description notes source study_dir
- Validates as StudySpec before write; **never** calls execute / `run_batch`
- Phase-2 **800**-cell cartesian is reached by removing/widening `stage` on the **unpromoted** example (full factor domains). Dropping `stage` from a promote draft expands only the narrowed survivor domains — not 800.

### Example

`examples/studies/pdPOC_ma_confluence_battery.yaml`

| Expansion | Cells |
|---|---|
| Active `stage.filter` (`touch` + `base`) | **40** |
| Full cartesian (phase-2; remove/widen stage on this example) | **800** |

CI/golden miniatures remain under `tests/fixtures/study/` (2×2×2). Do not run the
800-cell grid in CI.

### Out of scope for RS5

Auto-run promotion, assistant NL compiler, Studies UI (RS-D2).

---

## RS6 — Default-off `STUDY.*` assistant capabilities

Opt-in assistant wrappers over the same CLI study APIs. **No MCP server.**
Voice/realtime keep MCP/search denied.

### Enable flag

```toml
# config/assistant.toml
[assistant.study_tools]
enabled = false   # default; missing/unknown → disabled (fail-closed)
```

Set `enabled = true` to opt in. When off, `STUDY.*` handlers refuse with a clear
error; Help/Discuss defaults stay unchanged. CLI `python -m thesistester study …`
always works regardless of this flag.

### Capabilities

| ID | Mode | Confirm |
|---|---|---|
| `STUDY.expand` | `EXECUTABLE` | none |
| `STUDY.run` | `EXECUTABLE` | `EXPLICIT_CONFIRMATION` when `run_count >= confirm_above_runs` |
| `STUDY.report` | `EXECUTABLE` | none |
| `STUDY.promote` | `EXECUTABLE` | none |

### Minimal confirm recipe (over threshold)

1. Dispatch `STUDY.run` → `OrchestrationStatus.APPROVAL_REQUIRED` with
   `payload.approval = {study_identity_hash, run_count, output_dir}`.
2. Retry the **same** request with `confirmed=True` **and** echo
   `payload.approval` unchanged.
3. `confirmed=True` alone is **not** sufficient over threshold.

Below `confirm_above_runs`, `STUDY.run` proceeds without that gate (CLI parity).
Inputs: `study_path` **or** validated `study_spec` dict; plus required `output_dir` /
`workers` / `force` as on the CLI. Tools never call `run_batch`.

Assistant dispatch sandboxes `study_path` / `study_dir` / `output_dir` /
`output` and Spec-embedded `dataset.path` / `dataset.subtimeframe_path` /
`study.output_dir` under configured `data_roots` (same posture as other write
tools). Dict `study_spec` relative paths resolve against `base_directory` or cwd
(not the ephemeral temp materialization directory).

Full multi-step external Grok routine pack is **RS-D5** (extends this recipe).

---

## RS-D2 — Studies viewer (read-only)

Streamlit page: **Studies** (`pages/15_Studies.py`).

- Paste a completed study `output_dir` (must stay under repo cwd or local store).
- Loads ledger + overview via `load_ledger` / `report_study(..., write_artifacts=False)`
  (no backtests; does **not** rewrite `study.overview.*` on disk).
- Shows identity, ledger counts, ranked / low-N / unresolved, OTF Δ, `bundle_path`.
- Overview MD/CSV downloads are served from the in-memory aggregate.
- Honesty banner required; no expand / run / promote controls; only the
  Studies-scoped `studies_viewer_study_dir` session key is written (never classic
  research keys); no Research-Bundles deep-link.
- Report bundle reads refuse `bundle_path` values that escape the study directory.

---

## Post-MVP (plan-locked)

See `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` §12. Do not reorder without amending that plan.
**Next code PR = RS-D4 only** (§12.5).

| Order | ID | Intent |
|---|---|---|
| 1 | **RS-D7** ✅ | Additive `results_index` `profit_factor` + `win_rate` (soft-resume PF/WR backfill; ordered CLI↔study key parity) |
| 2 | **RS6** ✅ | Default-off `STUDY.*` assistant capabilities + minimal CLI/confirm docs (two-step confirm; no MCP server) |
| 3 | **RS-D2** ✅ | Streamlit Studies **viewer** (artifacts-only; no in-app run) |
| 4 | **RS-D4** (**next**) | Per-cell WFA/validation/overfitting diagnostic rollup (compose-only; no cross-cell PBO) |
| 5 | **RS-D5** | External Grok Bot routine pack |

Parked: RS-D1 (NL compiler), RS-D3 (`run_batch` continue), RS-D6 (new factor types).
