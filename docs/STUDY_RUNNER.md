# Research Study Runner

**Status:** RS1–RS5 MVP + **RS-D7** + **RS6** + **RS-D2** + **RS-D4** + **RS-D5** + **RS-D8** + **RS-D9** landed. Parked: RS-D1 / RS-D3 / RS-D6.  
**Plan:** `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` (§12)  
**Package:** `thesistester.study`  
**Study Builder:** `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`. **SB1–SB3** ✅.
Compiler `thesistester.study.builder` emits / hydrates canonical
`schema_version: 1` YAML. Studies **Build StudySpec** authors via widgets,
Apply to Preview, hydrate from Preview / Inspect spec, download YAML.
Build always writes `dataset.format_profile` from the R17 allow-list
(same labels as Data). Omitted / blank → `canonical` (runner default).
Unknown non-blank tokens fail emit — they are not rewritten to `canonical`.
History Exporter CSVs need **Quantower History Exporter (semicolon)**.
Execute is still CLI (`study run` / Preview **Run via CLI**). Inspect may
show an additive ledger progress strip (Refresh still explicit). Does not
change preview / CLI-spawn / execute semantics.
**SIA** (Study Ingest Alignment) ✅
`docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md`. New studies and the
pdPOC teaching example emit `dataset.ingestion_mode: 15s_primary_derive_1m`
(Quantower 15s path, `intrabar_model: subtimeframe_conservative`). Omitted
mode remains `primary` (the dopen example is legacy 1m). Execute is still
CLI / `run_experiment`. Studies does not walk the Data page.
**SV** (Study Viewer) 📝
`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`. SV0 plan-locked; SV1–SV4 not
started. Catalog / quality panes / overview charts / cell peek on the
existing Inspect tab. Does not change preview / CLI-spawn / execute.
Inspect remains artifacts-only (`report_study(..., write_artifacts=False)`).

Headless, additive tooling for closed multi-factor confluence studies. Classic
Streamlit research mutate paths and `python -m thesistester run` are unchanged.
RS-D2 adds a **read-only** Studies viewer; RS-D4 adds compose-only diagnostic
rollup; RS-D5 is the external Grok routine pack (docs/examples only). RS-D8
extends the Studies page with a YAML preview pane. **RS-D9** adds a button on
that pane that **spawns** the existing CLI `study run` — not a second
in-process runner.

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
| Lock | Exclusive `.study.lock` on `output_dir` (fail-closed if another study run holds it). POSIX: `fcntl.flock`; Windows: `msvcrt.locking`. Contention → “holds the lock”; unsupported/I/O lock failures keep a distinct error (not a phantom concurrent run). Importing `thesistester.study` must not require POSIX-only `fcntl` (Studies viewer on Windows). |

### Artifacts (under output_dir)

| File | Role |
|---|---|
| `study.spec.yaml` / `study.expansion.json` / `experiment.yaml` | From expand |
| `study.ledger.json` | Per-cell status (`pending`/`running`/`ok`/`failed`) + confirm record + `error` |
| `*.research.zip` | Per-ok-cell bundles |
| `results_index.csv` | R18 metric columns + `bundle_path` + study `status` |

`study run` prints `Cell status: ok=… failed=…` and, when any cell failed, the
unique `cells.*.error` strings (capped) so a shared ingest/config fault is
visible without opening the ledger. Full per-cell text stays in
`study.ledger.json`.

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

MNQ dOpen × MA / 3c: `examples/studies/dopen_ma_3c_mnq.yaml` — **8** cells (no
stage filter) plus a per-cell 4×5 SL/TP grid inside the $40 / $500 envelope.

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

Full multi-step external Grok routine pack is **RS-D5** (extends this recipe —
see below). Do not duplicate a divergent long recipe here.

---

## RS-D5 — External Grok Bot routine pack

Normative pack: [`STUDY_RUNNER_GROK_ROUTINE_PACK.md`](STUDY_RUNNER_GROK_ROUTINE_PACK.md)  
Copy-ready prompts: [`examples/studies/agents/`](../examples/studies/agents/)

Extends the RS6 minimal confirm recipe (does not fork it). External coworkers
shell the CLI even when `[assistant.study_tools] enabled=false`.

| Rule | Behavior |
|---|---|
| Surfaces | CLI always; optional RS6 `STUDY.*` when enabled; RS-D2 viewer read-only; RS-D4 rollup opt-in |
| Recipe | stage-first expand → confirm+run → report → promote **draft** → human edit → second pass → optional rollup |
| Hard stops | no axis invention; no confirm bypass; no auto-run of promote drafts |
| Honesty | always surface multiple-testing / `min_trades`; prefer RS-D7 index PF/WR |
| Non-goals | no embedded Grok host; no RabbitMQ; no MCP server; no runtime default-on tools |

---

## RS-D2 — Studies viewer (read-only)

Streamlit page: **Studies** (`pages/15_Studies.py`).

- Paste a study `output_dir` (completed or in-flight; must stay under repo cwd or local store).
- Loads ledger + overview via `load_ledger` / `report_study(..., write_artifacts=False)`
  (no backtests; does **not** rewrite `study.overview.*` on disk).
- Shows identity, ledger counts, ranked / low-N / unresolved, OTF Δ, `bundle_path`.
- Inspect **ledger progress** (additive): `st.progress` from
  `ok+failed+skipped / run_count` plus current `running` cell name(s).
  Explicit **Refresh** still reloads; no auto-refresh, kill, or retry.
  A readable ledger with a missing `results_index.csv` file (first cell still
  running) is a ledger-only view — progress shown, ranked tables empty.
  A present but unreadable or invalid index still errors (no fallback).
- Overview MD/CSV downloads are served from the in-memory aggregate.
- Honesty banner required; no expand / run / promote controls; only
  Studies-scoped session keys are written (`studies_viewer_study_dir` plus
  inspect-model / preview-result caches so Streamlit tab reruns do not
  re-aggregate or drop results — never classic research keys); no
  Research-Bundles deep-link.
- Report bundle reads refuse `bundle_path` values that escape the study directory.
- Package import is Windows-safe: `study.execute` binds `fcntl` / `msvcrt`
  optionally so opening this page cannot raise `ModuleNotFoundError: fcntl`.
- **RS-D8** adds a preview pane on this same page.
- **RS-D9** may spawn the existing CLI `study run` from Preview;
  Inspect remains artifacts-only; the page must not call `run_study()` in-process.
- **SV** (separate series; `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`) may add
  catalog / quality / charts / cell peek on this Inspect pane. It must not
  reopen the read-only / no-classic-session / no-Bundles-deep-link rules above.

---

## RS-D4 — Per-cell diagnostic rollup

```bash
python -m thesistester study rollup out/study1
```

Writes `study.rollup.csv` + `study.rollup.md` by composing existing per-cell
index WFA columns and bundle members (`walk_forward_meta.json`,
`validation_summary.json`, `overfitting_summary.json`).

| Rule | Behavior |
|---|---|
| Compose-only | No cross-cell / pooled PBO, DSR, or CSCV |
| Missing batteries | `*_battery=not_run` and null metrics (default study emission) |
| Overfitting density | Needs grid cell trade sequences + `validation.enabled: true` + `validation.overfitting.enabled: true` |
| Honesty | Descriptive rollup ≠ validated edge |

**Survivor-stage opt-in (docs only; not auto-applied):** after promote, set
explicit `walk_forward.enabled: true` and/or `grid.enabled: true` **with**
`validation.enabled: true` **and** `validation.overfitting.enabled: true`
(never bare `{}`; parent `validation.enabled` must be on or overfitting is
skipped) before expecting dense rollup columns. See
`ASSUMPTIONS_AND_LIMITATIONS.md`.

---

## RS-D8 — Studies authoring preview

Same Streamlit page (`pages/15_Studies.py`), **Preview StudySpec** pane.

```text
yaml.safe_load → normalize_study_spec → validate_study_spec → in-memory expand_study
```

| Rule | Behavior |
|---|---|
| YAML | Canonical `schema_version: 1` only (fail-closed). No NL / shorthand compiler |
| Preview | Show `run_count`, full cartesian, matched stage estimate, `needs_confirm`, `workers`, identity, constants battery hints |
| Cap | Skip in-memory expand above `PREVIEW_EXPAND_CAP` (2_000); still show matched estimate |
| Imports | `preview.py` does not import `thesistester.study.execute` |
| Progress | Explicit **Refresh** of an existing study-dir ledger; does not start `study run` |
| Streamlit caches | Inspect model + last preview result are Studies-scoped session caches (tab reruns must not re-aggregate or drop metrics) |
| Execute | CLI (`study run --confirm`) / optional RS6 tools. **RS-D9** may spawn that same CLI from this pane |

Stage-first example preview: **40** cells vs full cartesian **800**. Dataset CSV need not exist for preview.

---

## RS-D9 — Studies CLI-launch button

Same Streamlit page (`pages/15_Studies.py`), **Preview StudySpec** pane, after a
successful preview. Helper: `thesistester/study/launch.py` (does **not** import
`execute.py`).

```bash
python -m thesistester study run study.launch.yaml --output-dir <dir> [--confirm] [--force] [--workers N]
```

| Rule | Behavior |
|---|---|
| Single runner | Child is CLI `study run` → `run_study`. The page does **not** call `run_study()` in-process or dispatch `STUDY.run` |
| Confirm | `run_count >= confirm_above_runs` → **Bind confirm** then **Confirm and run** with `--confirm`. Bound triple `{pinned_study_identity_hash, run_count, resolved_output_dir}` is hashed **after pin** — never `StudyPreview.study_identity_hash`. Under threshold: **Run via CLI** without `--confirm` |
| YAML | Writes `{output_dir}/study.launch.yaml`. Pin **both** `dataset.path` and `dataset.subtimeframe_path` (viewer roots then cwd). Never clobber inspect `study.spec.yaml`. Refuse if a pinned CSV is missing. Do not rewrite `study.output_dir` in the launch YAML. Re-previewing **changed** YAML clears armed confirm and reseeds CLI `output_dir` from the new Spec |
| Identity | Prefer a **new** `output_dir`. Launching into an existing CLI dir with a different identity refuses without `--force` |
| Detach | `Popen` (`shell=False`; POSIX new session + `close_fds`; Windows `CREATE_NEW_PROCESS_GROUP` + `CREATE_NO_WINDOW`, **not** `DETACHED_PROCESS` — that flag drops redirected stdout so `study.launch.log` stays empty). Child env `PYTHONUNBUFFERED=1`. Exclusive `O_EXCL` pid claim before spawn (in-flight placeholder is the Streamlit pid, not `0`). Windows PID probe via `OpenProcess`, not `os.kill`. Progress = Inspect **Refresh** (honors the current Inspect path field) + `study.launch.log`. Streamlit `Ignoring changed path` under `results/` is the watcher, not the study log |
| Not a queue | No scheduler / retry / kill UI. Streamlit reruns do not respawn. Refuse if launch pid is still alive or `O_EXCL` is lost |
| Cap | `preview.expanded is False` (over 2_000) refuses launch from the page |

Preview does not require the dataset CSV to exist; **launch does** (pinned path must be a file). Start Streamlit from the repo root.

---

## Post-MVP (plan-locked)

See `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` §12. Sequenced milestones
**RS-D7 → RS6 → RS-D2 → RS-D4 → RS-D5 → RS-D8 → RS-D9** are complete.
Parked items stay out of the critical path unless that plan is amended.

| Order | ID | Intent |
|---|---|---|
| 1 | **RS-D7** ✅ | Additive `results_index` `profit_factor` + `win_rate` (soft-resume PF/WR backfill; ordered CLI↔study key parity) |
| 2 | **RS6** ✅ | Default-off `STUDY.*` assistant capabilities + minimal CLI/confirm docs (two-step confirm; no MCP server) |
| 3 | **RS-D2** ✅ | Streamlit Studies **viewer** (artifacts-only; no in-app run) |
| 4 | **RS-D4** ✅ | Per-cell WFA/validation/overfitting diagnostic rollup (compose-only; no cross-cell PBO) |
| 5 | **RS-D5** ✅ | External Grok Bot routine pack (`STUDY_RUNNER_GROK_ROUTINE_PACK.md` + `examples/studies/agents/`) |
| 6 | **RS-D8** ✅ | Studies authoring preview (canonical YAML validate + in-memory expand; cell count / confirm gate; ledger watch) |
| 7 | **RS-D9** ✅ | Studies CLI-launch button (spawn existing `study run`; no in-process execute) |

Parked: RS-D1 (NL compiler), RS-D3 (`run_batch` continue), RS-D6 (new factor types).

---

## SB — Study Builder (operator contract)

**Status:** SB1–SB3 landed. Plan: `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`.

Build compiles a closed `StudyDraft` into the same `schema_version: 1` StudySpec
the CLI already runs. It does **not** execute cells, spawn `study run`, promote,
or mutate classic research session state.

| Step | What happens | What does not happen |
|---|---|---|
| Widgets / Start from example / Load Preview / Copy spec | Hydrate `StudyDraft` (pending-sync widget overwrite) | No NL/shorthand compiler; tokens stay in `closed_level_token_set` |
| Live strip | Page calls `preview_study_spec(emit_study_spec(draft))` | No cartesian math on the page; over-cap still uses the preview estimate |
| Apply to Preview | `emit_study_yaml` → `STUDIES_PREVIEW_YAML_KEY`; pop preview cache; `reset_launch_session_for_preview` | No auto-preview; no CLI spawn; no `study.launch.yaml` |
| Validate / Preview → Run via CLI | Existing RS-D8 / RS-D9 on the Preview tab | Build has no Run / Bind confirm / Promote |
| Download StudySpec YAML | Browser download of `emit_study_yaml` | Not a store write; never defaults to the Inspect dir’s `study.spec.yaml` |

Stage: **Full cartesian** omits `stage`; **Filter** writes `include` keys whose
values are ⊆ current factor widgets (pdPOC example: `trigger=[touch]`,
`trigger_timeframe=[base]` → 40 vs 800); **Explicit cells** is delete-only
(promote draft / YAML hydrate is the add path). Empty `stage.cells` fails emit.
Filter / `group_by` / delete-row pickers drop stale session values when a
domain shrinks (Streamlit rejects selected values that are not in `options`).

Report: `primary_metric`, `min_trades`, `multiple_testing`, `group_by` ⊆ declared
factors (empty omits the key so normalize applies the default), `otf_baseline.enabled`.

### SB1 compiler (no Streamlit)

Pure helper `thesistester.study.builder`: `StudyDraft` →
`validate_study_spec(normalize_study_spec(emit(draft)))`. Hydrate is the inverse
for identity-hash round-trip. Pages import this module directly (same
pattern as `launch.py`). **No Streamlit. No execute / launch / preview import.**

| API | Role |
|---|---|
| `default_study_draft` | Valid 2-cell default (1×1×2×1×1) |
| `emit_study_spec` / `emit_study_yaml` | Canonical YAML; `mode_rules` for listed modes only; batteries always have `enabled` |
| `hydrate_study_draft` / `hydrate_study_yaml` | Lossless vs `load_study_spec` identity hash on the golden + examples |
| `builder_token_catalog` | `sorted(closed_level_token_set(levels))` |
| `OTF_PRESETS` | Off / 5m / 15m / 30m / combo chips |

Execute remains `python -m thesistester study run`. Apply to Preview writes the
Preview textarea key before that widget mounts (Build body runs first).

---

## SV — Study Viewer (operator contract)

**Status:** SV0 plan-locked. SV1–SV4 not started. Plan:
`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`.

Inspect today is path-paste + tables (RS-D2). SV is an additive Inspect UX
on the **same** Studies page so operators can reopen local studies and read
errors / quality / overview without opening every artifact by hand. Execute
stays CLI (`study run` / Preview **Run via CLI**). Promote stays CLI.

| Step | What happens (when shipped) | What does not happen |
|---|---|---|
| Catalog (SV1) | One-level scan of `results/studies/` and `out/` under cwd + store; click sets the existing Inspect path and `load_study_view` | Recursive repo walk; `report_study` during discover; cloud sync; new store schema |
| `study list` (SV1) | Additive CLI over the same discover helper; sandboxed `--root` (study dir / prefix dir / trusted root per plan §4.9) | Any change to `expand\|run\|report\|promote\|rollup` argv; `viewer.py` importing `cli_study` |
| Quality panes (SV2) | Failed-cell `error` table; `report.group_summaries`; read `study.rollup.*` **if present**; tail `study.launch.log` | `rollup_study()` (that helper writes); auto-`study report` write |
| Overview charts (SV3) | Plotly from already-loaded ranked / group frames | New metrics; unzip-all-cells equity charts |
| Cell peek (SV4) | Selected `run_name` → index + ledger error + optional `trade_summary.json` | `apply_research_bundle_to_session`; classic session keys; Bundles / Backtest deep-link |

**Honesty.** Catalog listing is discovery, not a quality score. Ledger
`ok`/`failed` counts and Inspect progress are cell-status, not edge.
Overview charts inherit RS4 ranking caveats (descriptive screen,
`min_trades`, multiple-testing). Rollup-if-present is compose-only
diagnostics. Cell peek is not a validated edge.

**Until SV1 ships:** paste `output_dir` on Inspect (existing RS-D2). CLI
files remain the academic path (`study report`, `study.ledger.json`,
optional `study rollup`).
