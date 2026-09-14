# AGENT GUIDE

## Purpose
Regression-safe onboarding guide for contributors/agents working in ThesisTester.

## Fast start
1. App install: `pip install -e . -c constraints.txt` (`README.md` Run locally).
   `pyproject.toml` is the only range SoT; `constraints.txt` is the lock
   (QI-12-03 / QR G-3). There is no `requirements.txt`. `streamlit run app.py`
   puts the main-script directory (repo root) on `sys.path`. AppTest
   `from_file` of a page puts `pages/` on `sys.path[0]`; non-Data pages then
   resolve `thesistester` via this editable install (QI-10-08 / B-14).
   `pages/1_Data.py` also self-bootstraps `REPO_ROOT`.
2. Tests (needs the `dev` extra — `pytest` is not on the app path):
   `pip install -e ".[dev]" -c constraints.txt` then `pytest -q`.
3. Optional app run: `streamlit run app.py`. Repo
   `.streamlit/config.toml` sets `server.maxMessageSize = 400` (MB websocket
   payload; Streamlit default is 200) and `server.maxUploadSize = 350`.
   `MessageSizeError` is that transport cap, not host RAM. Restart Streamlit
   after editing the file. Headless `python -m thesistester` is uncapped.
4. Codespaces / Dev Containers (G-5 / QI-12-08): the image is Python **3.12**
   (CI lint / scanners / `pytest (py3.12)`). Bind the editor and install to
   `/usr/local/bin/python` (not Debian bookworm 3.11). `updateContentCommand`
   is `/usr/local/bin/python -m pip install --user -e '.[dev]'
   -c constraints.txt`. `postAttachCommand` is
   `/usr/local/bin/python -m streamlit run app.py` — do not disable
   XSRF/CORS (including `STREAMLIT_SERVER_ENABLE_*`). Do not add
   a second Streamlit install. Do not edit `.streamlit/config.toml` from the
   container spec (QI-10). Fail-closed lock: `tests/test_g5_devcontainer.py`.

## Headless and agent operation (R18)

Use `thesistester.api` for one in-process research pipeline or the versioned YAML
runner for independent batches. `validate_run_spec` is the shared fail-closed
RunSpec gate: C-2 (QI-06-01 / MG-17) walks `RUN_SPEC_RULES` (run, dataset,
levels, setup, backtest, grid, subtimeframe, walk_forward, validation).
Own table — do not import `SETUP_CONFIG_RULES`. `api.FORMAT_PROFILES` is
the loader object. No pydantic. No composer collapse.

```bash
python -m thesistester run experiment.yaml --workers 4
```

### Research Study Runner (RS1–RS5 + post-MVP through RS-D9)

For closed multi-factor confluence studies, use the additive Study Runner (see
`docs/STUDY_RUNNER.md`). It expands a StudySpec to an R18 experiment, then
executes cells via a **study-owned** `run_experiment` loop (ledger + soft resume),
aggregates an honest overview, and can draft survivor StudySpecs. It does **not**
change `run_batch` abort semantics. `validate_study_spec` (C-3 / QI-07-03 /
MG-17) walks own `STUDY_FACTOR_AXIS_RULES` / `STUDY_REPORT_FIELD_RULES` /
`STUDY_INGEST_RULES`. Required / supported axes and expand re-checks
(`STUDY_EXPAND_REQUIRED_AXES`) are derived from that factor table. Own
table — do not import `SETUP_CONFIG_RULES` or `RUN_SPEC_RULES`. Omitted
`ingestion_mode` stays the ingest-row `omit_means` (`primary`, AH §2 item 9).
C-5 is reporting (`build_markdown_report` section table; walker AST-bound).
C-6 (QI-05-14 / QI-06-11 / MG-29) promotes `directional_grid_metrics`,
`SIMULATION_KWARGS`, `default_otf_filter_config` (copy of
`DEFAULT_OTF_FILTER_CONFIG`), `hash_dataframe`, and `dash_if_none`
(private aliases kept). `_empty_trades_df` stays a QI-4 handoff.
C-7 (QI-06-04) generates managed/known/required/hash-exclusion lists from
`BUNDLE_KEY_REGISTRY`; `build_research_bundle` / `load_research_bundle`
walk `BUNDLE_SECTION_IO`. C-8 (QI-06-05) splits saved-dataset bootstrap:
Streamlit-free `saved_dataset_state` (`restore_saved_dataset_provenance`
takes a mapping) + one-function `app_state` adapter (lazy Streamlit).
`classic_*` Streamlit imports stay lazy. C-9 (QI-08-02) slims the journal
barrel and lazy-binds classify so `import thesistester.journal` does not
load `engine.backtest`. C-10 (QI-08-01) is one qty-scaled P&L helper
(`qty_scaled_journal_pnl`) plus shared `journal_cost_ticks`. C-11 (QI-06-10)
extracts execution-artifact verify/publish/evict helpers behind containment
guards. C-12 (QI-01-02) extracts raw/subtf sidecar policy helpers from
`save_dataset` (preserve/conflict and derive-without-subtf refusal
unchanged). C-13 (QI-05-03) splits pair/trigger summarizers into
`confluence_pair_trigger.py`; public combo helpers stay on
`confluence_attribution`. C-14 (QI-03-01) extracts `generate_signals`
phases (TF prep, zone-naked admission, trigger dispatch table).
`_check_touch`, the candidate sort key, 3c math (S3 / DA0), and public
`VALID_TRIGGERS` stay untouched. C-15 (QI-14-05) replaces `iterrows`
with column arrays / `iloc` behind those helpers (nullable dtypes
unchanged — hashes stay identical). Empty trigger frames stay an
empty HTF map. C-16 (QI-03-02) shares one 3c signal-row mapper
(`_map_3c_setup_to_signal`) and detector scan/merge helpers; S3 arrival /
reversal / retrace / SFP math is unchanged. The mapper branches on
`effective_trigger_timeframe == "base"` (base trigger indices = base
indices); HTF reads setup `trigger_*` and does not fall back to base
indices when `trigger_df` is missing. C-17 (QI-05-01) extracts WFA
P0 validate / P3 train-grid / P5 stitch / P6 summary helpers from
`run_walk_forward_sl_tp`. Fold construction and `causal_prefix` stay
untouched (S5). C-18 (QI-04-09) centralizes skip/exit tokens next to
`_SKIPPED_SIGNAL_COLUMNS`; string values unchanged. `entry_window`
aliases window/cutoff tokens locally (does not import `engine.backtest`).
C-19 (QI-04-01) extracts `simulate_trades` P7 (SL/TP + flatten + exit
walk) behind the R22 boundary (`sim_core.compute_session_close_cap` /
`walk_trade_exit` calling `resolve_trade_bar`); then P4/P6 admission
helpers. Public signature unchanged. `sim_core` still holds no
admission / P&L. AH §2.1 defaults, C1/AH1 flatten clock, and 3c-void
silent `continue` stay untouched. Next: C-20.
Stage-first example:
`examples/studies/pdPOC_ma_confluence_battery.yaml` (40 cells, 15s-primary; full 800 is phase-2).

```bash
python -m thesistester study expand study.yaml --output-dir out/study1
python -m thesistester study run study.yaml --output-dir out/study1 --confirm
python -m thesistester study report out/study1
python -m thesistester study promote out/study1 --output draft.yaml --top-n 10
# optional replay of the emitted experiment (same dataset bytes when the
# expand-time file still exists; still run_batch — fail-fast, origin=cli,
# no index status — not study run):
python -m thesistester run out/study1/experiment.yaml
```

Optional **RS6** assistant capabilities (`STUDY.expand|run|report|promote`) are
registered but **default-off** via `[assistant.study_tools] enabled=false` in
`config/assistant.toml`. When enabled, `STUDY.run` over `confirm_above_runs`
requires a two-step confirm: first dispatch returns `APPROVAL_REQUIRED` with a
bound `payload.approval` triple `(study_identity_hash, run_count, output_dir)`;
retry with `confirmed=True` **and** that approval echoed. No MCP server. Prefer
the CLI when the flag is off.

**RS-D5** external coworker pack (extends the RS6 minimal recipe; no product
host): `docs/STUDY_RUNNER_GROK_ROUTINE_PACK.md` + copy-ready prompts under
`examples/studies/agents/`.

**Import contracts (B-10 / QI-12-07).** Direct Study / journal / library
import bans are `.importlinter` C1–C5 and C7–C10 (`QI-15_SYNTHESIS.md` §5.4).
CI job `import-linter (warn-first)` runs `lint-imports` and emits `::warning`
on broken contracts; it does **not** fail and is **not** one of the six G-1
required names. C1/C4 ignore only the known `expand → cli` hop of
`expand → cli → cli_study` (not blanket `allow_indirect_imports`). C7 is
expected broken via `journal.levels → study.schema → tick_vap →
execution_artifacts → api` (C-9 landed: package-init no longer loads
`engine.backtest`; it does not keep C7). C8 allow-list: lazy `app_state` adapter (C-8), lazy
classic chrome (`classic_context` / `classic_ledger` / `classic_nav` /
`classic_proposal` / `classic_record`), and the two secret readers
(`assistant.llm`, `assistant.voice.xai_realtime`) until F-9. Eager
Streamlit importers in the library are 0.
C10 is page-scoped (`pages/15_Studies.py` ↛ `FORMAT_PROFILE_LABELS` from
builder) and is gated by `tests/test_import_linter_contracts.py`. **C9**
(`sim_core` ↛ `entry_window_policy` / `analytics.*`) is kept (B-19 /
QI-4 §6.3); the AST gate resolves parent-package and relative imports
so those forms cannot false-green. **C12** is the `validation_summary()`
four-key freeze (`tests/test_validation.py`), not an import contract.
Empty / no-valid-trade paths stay on the same four keys (`None` not
NaN, `insufficient`). Blocking flip is a later PR.

**RS-D8:** Studies page authoring preview — canonical StudySpec YAML
validate + in-memory expand (cell count / confirm gate). `preview.py` must not
import `thesistester.study.execute` (import-linter **C1**).

**RS-D2 Inspect progress:** ledger `done/total` + running cell names on
Studies Inspect. Explicit Refresh only — do not add auto-refresh, kill,
retry, or in-process `run_study`.

**RS-D9:** Studies Preview pane may spawn the existing CLI
(`python -m thesistester study run`) as a detached subprocess. Do not call
`run_study()` in-process. Over `confirm_above_runs`, require the same two-step
bound triple as RS6, hashed on the **pinned** spec (not the preview hash).
Pin both `dataset.path` and `dataset.subtimeframe_path`. Exclusive pid claim
before `Popen`; Windows pid-alive must not use `os.kill`. Windows spawn must
not set `DETACHED_PROCESS` (empty `study.launch.log`). See `docs/STUDY_RUNNER.md`
§RS-D9 and plan §12.10.

**SB (shipped):** Study Builder UX — `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`
(SB1–SB3). Form compiler to canonical StudySpec YAML on Studies **Build
StudySpec**; Apply to Preview then existing Validate / Preview → Run via CLI.
Do not call `run_study()` from the Build tab. Parked RS-D1 / D3 / D6 stay parked.
Operator contract: `docs/STUDY_RUNNER.md` §SB.

**SIA (shipped):** Studies authoring alignment to the Data-page 15s-primary
RunSpec — `docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md`. New drafts
emit `15s_primary_derive_1m` with MNQ + UTC + History Exporter
(`default_study_draft()` only; `StudyDraft()` field defaults stay legacy).
The pdPOC example stays ES / NY. Operator template:
`examples/studies/pRTH_open_ma.yaml`. Do not point a 15s Quantower file at a
study without that mode (omitted = `primary` = a different experiment).
`validate_study_spec` emits an error-level warning (does not rewrite to
15s-primary) when `format_profile` is Quantower History Exporter and
`ingestion_mode` is omitted or `primary` (QI-07-05).
Do not implement further SIA work by importing `pages/1_Data.py`, reading
classic `st.session_state`, or editing `engine/` / `api.run_experiment`
loaders.

**SV (SV1–SV5 shipped):** Study Viewer Inspect catalog + quality panes +
overview charts + cell peek + trader briefing —
`docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md`.
`discover_study_dirs` + Inspect **Load selected** + additive
`python -m thesistester study list` + failed-cell / group / rollup-if-present
/ launch-log tail + locked Plotly on already-loaded ranked / group frames
(page only) + one-cell `trade_summary.json` peek + SV5 briefing / per-cell
SL/TP grid / NY RTH ToD (`thesistester/study/briefing.py`). Do not implement
further SV work inside an RS/SB/SIA PR. Discover must not call `report_study`.
Do not call `run_study()`, `report_study` write, or `rollup_study()` from
Inspect. `viewer.py` must not import `cli_study` / `thesistester.cli` /
`execute` / `rollup` / Plotly / Streamlit (import-linter **C2**). Do not hydrate classic
`st.session_state`. Do not add time-of-day as a StudySpec factor axis.
Operator contract: `docs/STUDY_RUNNER.md` §SV.

**SO (SO9 shipped):** Study Observatory —
`docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md`.
`load_observatory_frame` + `pages/16_Study_Observatory.py` + additive
`python -m thesistester study observatory` + Program B lens + saved desks
under `{store}/study_observatory/desks` + studies pane + display-only
cohort labels (raw `cohort_key` unchanged) + lens-as-filter (`desk_class`
/ `useful_confluence` + heatmap focus via existing core/partner facets;
`schema_version` stays 1). Reuse `discover_study_dirs`.
Do not implement SO5/SO6 inside an RS/SV/SAF PR. Do not unpark
SO5/SO6. Do not call `report_study`
per study, `run_study()`, `rollup_study()`, or unzip-all. `observatory.py`
must not import `cli_study` / `execute` / Streamlit / Plotly (import-linter **C3**). `viewer.py`
must not import `observatory`. Do not write `results/studies/`. Operator
contract: `docs/STUDY_RUNNER.md` §SO.

**SAF (SAF1–SAF3 shipped):** Study Admit Follow-up —
`docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md`.
`study promote --admit-tod auto` drafts a linked child StudySpec with Admit
on `backtest`/`grid` `entry_window` and optional `study.lineage`.
`--tod-group` / `--allow-thin` are CLI-only. Inspect **Draft Admit follow-up**
stays RTH + thin-refuse and writes Preview YAML only. Catalog `parent` is
best-effort YAML. Do not implement SAF4. Promote without `--admit-tod`
stays RS5. Do not auto-`study run`. Do not add ToD as a factor axis. Operator
contract: `docs/STUDY_RUNNER.md` §SAF.

The API handoffs are typed but intentionally remain plain `pandas.DataFrame` /
`dict` values:

1. `load_dataset(...) -> DataFrame` returns validated, exchange-timezone,
   session-tagged OHLCV.
2. `compute_levels(...) -> LevelsResult` returns `levels`, `session_levels`,
   and canonical `levels_settings`.
3. `build_setup(...) -> dict` applies the Setup Builder normalization and
   validation contract. `validate_setup_config` in `thesistester/setup.py`
   is the SoT validator: C-1 (QI-03-03 / MG-17) walks a declarative
   `SETUP_CONFIG_RULES` table (identity, enums, `global_cluster`,
   `anchor_rules`, `trigger_params`, otf, `entry_window`). No pydantic.
   `build_setup_config` is the SoT builder. C-4 (QI-03-10 / MG-17): Classic
   Signals generate calls `build_setup_config` for the setup dict only —
   still **not** `run_experiment` (AH §2 items 1–2). Page-local
   `_normalize_3c_params` is deleted; 3c / AO1 `min_valid=0` go through BSC.
   Page-6 collects kwargs with `build_setup_kwargs_from_mapping` (saved
   mapping + page overrides). Engine `_source_mode` is attached only at
   `generate_signals` time — not stored on the setup dict or in signal
   settings identity. AH §2 item 10 / AH6: `BASE_COLUMNS` and `close` fail
   closed. Omitted-key defaults stay unchanged. C-2 / C-3 reuse the
   validator table pattern. C-5 (QI-06-02): `build_markdown_report` walks
   `MARKDOWN_REPORT_SECTIONS` (own table; walker AST-bound; A-4 H13 banner
   stays the first line under `## Validation Diagnostics`, bound on
   `_md_validation`). C-6 (QI-05-14 / QI-06-11): analytics public surface is
   `directional_grid_metrics` and `SIMULATION_KWARGS` (R15/R19 share the
   kwargs set); OTF default is `default_otf_filter_config` (copy of
   `DEFAULT_OTF_FILTER_CONFIG`); bundle parquet
   projection is `hash_dataframe`; Report captions use `dash_if_none`.
   Private `_` aliases remain for same-module callers. C-7 (QI-06-04)
   is the bundle key registry (`BUNDLE_KEY_REGISTRY` / `BUNDLE_SECTION_IO`).
   C-8 (QI-06-05) is the Streamlit-free `saved_dataset_state` store plus
   the one-function `app_state` page adapter (restore is store-only).
   C-9 (QI-08-02) slims `journal/__init__.py` (lazy JS/TJ exports) and
   lazy-binds `_classify_zone_triggers_detail` in `journal/triggers.py`.
   C-10 (QI-08-01) is `qty_scaled_journal_pnl` (pair then `_cost_row`) plus
   shared `journal_cost_ticks`. C-11 (QI-06-10) extracts verify/publish/evict
   helpers from `execution_artifacts.py` (containment guards unchanged).
   C-12 (QI-01-02) extracts `_apply_raw_sidecar_policy` /
   `_apply_subtf_sidecar_policy` from `save_dataset` (S1 preserve/conflict
   and derive-without-subtf refusal unchanged). C-13 (QI-05-03) splits
   pair/trigger summarizers into `confluence_pair_trigger.py` (public
   combo helpers still imported from `confluence_attribution`). C-14
   (QI-03-01) extracts engine `generate_signals` phases: TF prep
   (`_prepare_generate_trigger_frame`), zone-naked admission
   (`_admit_zones_for_signals`), and the trigger dispatch tables
   (`_SIMPLE_TRIGGER_CHECKERS` / `_APPROACH_SIDE_CHECKERS`) plus the
   existing 3c row-mapping body (`_generate_3c_signals`). `_check_touch`,
   the candidate sort key, 3c detectors, and public `VALID_TRIGGERS` are
   unchanged. Identity vs `origin/main` is live `hash_dataframe` /
   `assert_frame_equal` (not same-process self-compare; hexes are not
   frozen). C-15 (QI-14-05) replaces `iterrows` with column arrays /
   `iloc` behind the C-14 helpers (`_index_trigger_rows_by_base_end`
   as a `_TriggerRowRef` column-array index, admission, 3c HTF lookup
   via `_index_base_end_by_trigger_bar`, zone projection). Empty trigger
   frames stay an empty map (iterrows-equivalent; no column access).
   Nullable dtypes were not changed. C-16 (QI-03-02) unifies the two
   3c row-mappers (`_map_3c_setup_to_signal`) and extracts shared
   detector scan/merge helpers so both public 3c detectors stay ≤ CC 30.
   Mapper path is the timeframe string, not `trigger_df is None`.
   S3 math is unchanged. C-17 (QI-05-01) extracts WFA P0/P3/P5/P6
   helpers; fold construction and `causal_prefix` stay untouched.
   C-18 (QI-04-09) centralizes skip/exit tokens; values unchanged.
   `entry_window` aliases stay local (no `engine.backtest` import).
   C-19 (QI-04-01) extracts `simulate_trades` P7 behind R22
   (`walk_trade_exit` / flatten cap in `sim_core`); P4/P6 admission
   helpers stay in `backtest.py`. No public signature change.
   Next: C-20.
4. `generate_signals(...) -> SignalsResult` returns zones, naked flags,
   signals, and deterministic settings identity. Engine orchestration
   is the C-14 helpers; C-15 is the `iterrows` replacement behind them;
   C-16 is the shared 3c row-mapper.
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
backtest/grid section selects `intrabar_model: subtimeframe` unless
`dataset.ingestion_mode: 15s_primary_derive_1m` supplies the lower frame from
the same 15-second CSV.
For interactive Streamlit research, the Data page **recommends**
`15s_primary_derive_1m` for Quantower History Exporter 15-second uploads
(Upload-CSV default). That mode derives one-minute canonical bars from a
single 15-second file (policy `observed_aligned_15s_to_1m_v2`: retain sparse
on-grid minutes; drop only misaligned) and attaches the source as
`subtimeframe_data`. Prefer `intrabar_model: subtimeframe_conservative` for
trade-only Rithmic/Quantower exports; strict `subtimeframe` needs complete
four-bar coverage (Quantower Build empty bars).
Legacy one-minute primary + optional dual-upload remains available under
**Legacy / advanced**. Entering Upload CSV with an active one-minute session
(e.g. after Sample) realigns the radio to legacy primary so dual-upload stays
reachable; an empty Upload-CSV visit keeps the recommended 15s default.
Explicit radio choices are preserved. After a CSV install, selector sync must
not rewrite `data_ingestion_mode_selector` when it already matches — Streamlit
rejects mutating that key after the ingestion-mode radio is instantiated.

Switching ingestion modes clears 15s-primary artifacts and invalidates the
primary CSV uploader so a 15-second export cannot be re-parsed as one-minute
primary data on the next rerun. While the radio selects
`15s_primary_derive_1m`, the separate lower-timeframe uploader stays hidden
even if stale one-minute `data` remains and provenance has not been installed
yet.

Local save/restore persists the attached 15-second source and
`ingestion_provenance` (dataset schema v2). Headless YAML may use either
legacy dual-file `dataset.subtimeframe_path` or one-file
`dataset.ingestion_mode: 15s_primary_derive_1m` (not both). Omitting
`ingestion_mode` keeps the API/CLI primary contract unchanged.

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

One-file 15-second-primary shape (derives complete one-minute parents; do not
also set `subtimeframe_path`):

```yaml
schema_version: 1
output_dir: results
runs:
  - name: nq_15s_primary_r12
    dataset:
      path: data/nq_15s.csv
      instrument: NQ
      source_timezone: America/New_York
      format_profile: quantower_history_exporter
      ingestion_mode: 15s_primary_derive_1m
    levels:
      opening_range_minutes: 30
    setup:
      name: NQ 15s primary
      description: Derived 1m with retained 15s R12 source
      instrument: NQ
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
      intrabar_model: subtimeframe
    grid:
      enabled: false
    validation:
      enabled: false
```

H8 (locked, AH §2 item 9): omitted battery `enabled` means **on** for
`api.run_experiment`, `python -m thesistester run`, and Assistant confirmed
runs. The example above sets `enabled: false` on purpose. Study expand still
emits explicit `false`. Nested OTF validation matrix is default-off. Do not
flip `.get("enabled", True)`.

Anchor-only (opt-in): `confluence_mode: anchor_rules`, `confluence_rules: []`,
`min_valid_confluences: 0`. Default `min_valid` stays 1. See
`docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md`.

Agent safety requirements:

- Treat YAML and API arguments as research specifications, not permission to
  alter engine behavior. Unknown facade configuration keys fail closed.
  `selected_levels` / anchor rule levels reject `close` and other OHLCV
  `BASE_COLUMNS`; those columns are not levels.
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

## AI Research Assistant contracts (AIA-0+)

`thesistester.assistant` is the shipped AI Research Assistant stack (AIA/C2/CAI +
RQ/HC/DI/RI/VA/DX/RUX). Status index: `docs/ENGINEERING_ROADMAP.md`.
`FEATURE_PARITY_REGISTRY` is the source of truth for present product coverage.
Every request must first parse as an `AssistantRequest`, then pass
`validate_capability_request()`.

- **Audit-payload rule (QI-09-06):** `_record_audit` and
  `AssistantRequest.to_dict` must run persist surfaces through
  `thesistester.assistant.redact.redact_for_logs` (re-exported as
  `sidecar.redact_for_logs`; do not fork the key list) before
  `append_conversation_message`. Do not write plaintext `api_key` (or
  other secret-shaped keys) into `tool_transcript` / conversation JSON.
  `to_dict` must not import the voice sidecar / engine stack. Dispatch
  confirmation still reads live `request.payload`. If redaction does not
  return a mapping, persist must fail closed (skip/raise), never write
  the unredacted tool entry. Keep the orchestrator audit-scrub probe
  and AIA registry tests green when changing audit persist.
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
  otherwise mark it `unsupported` with a limitation. The QI-09-04 / B-8
  zero-mention routed IDs (DATA.* defaults, HOME.workflow_guide,
  VALIDATION.run_otf_matrix, BACKTEST/GRID.manage_execution_defaults,
  CLASSIC.propose_page_change) must have a dispatch or payload test in
  `tests/test_assistant_handlers.py`; `get_handler` is unit-tested there.
  Other routed IDs keep a dispatch/payload test (any test file) or an
  explicit untestable tag. Structured errors must
  include `category`, `retryable`, and `remediation`. Apply/Draft/Validate/
  Cancel/Compare/Portfolio outcomes must flash via `assistant_flash` (Advanced
  defaults closed on the chat-first hub). Confirm lives under Plan review after
  Validate; Run lives on a `confirmed` specification version.
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
  and rejection of uncited numbers (`LLMEvidenceError`) before render.   Chat
  (`handle_chat_turn`) drafts non-executing choices only—never `dispatch` or
  `execute_confirmed_run`. Persist clarifications in both structured
  `clarifications` and readable `content` (`format_assistant_draft_reply`);
  the Research Assistant page must render `format_chat_message_body` and must
  not present Conversation audit JSON as the primary chat surface. Default RA
  UX is chat-first (thesis + chat); Advanced draft/runs/compare and Debug
  JSON/audit stay collapsed; do not reintroduce an Open-research-pages strip
  (classic nav is enough). Keep
  `tests/test_assistant_llm_evaluations.py`,
  `tests/test_assistant_workspace.py`,
  `tests/test_ui_copy_guards.py`, and
  `tests/test_assistant_registry_audit.py` green when changing the provider
  boundary, chat UX, or registry audit.
- Provider setup: non-secret settings in `config/assistant.toml`; secret via
  rotated `OPENAI_API_KEY` (env first, then Streamlit Secrets top-level
  `OPENAI_API_KEY`, else nested `[openai].api_key` /
  `[openai].OPENAI_API_KEY`). Strip one layer of wrapping quotes / BOM.
  Reject the placeholder `REPLACE_WITH_ROTATED_OPENAI_API_KEY`. When the
  Responses call fails, raise `LLMProviderError` with prefix
  `OpenAI structured request failed` plus sanitized HTTP/provider detail
  (never raw `sk-…`, Bearer tokens, or the exact configured key). Mark HTTP
  `400`/`401`/`403`/`404` as `retryable=False`. Chat + Help share this
  client — if both fail with the opaque main-branch message, fix deploy
  secrets / merge the transport-detail PR before debugging schemas.
  Help citations must use `doc_id="registry"` (alias `registry_digest` is
  normalized). Research Assistant Discuss/Help/Draft share one page-level
  `st.chat_input` (RUX-3); do not reintroduce nested `text_input` + Send or
  deferred-clear flags for retired keys (`product-help-input`,
  `results-qa-input-*`, `assistant_results_qa_drafts`,
  `assistant_product_help_draft`).
  Recovery/cancellation stays on orchestrator `cancel_run` / confirmation
  lifecycle, not the LLM.
- Document every additive `assistant_*` session key in `ARCHITECTURE.md` and
  `ASSISTANT_SESSION_KEYS`. Thesis switches must clear
  `THESIS_SCOPED_STAGING_KEYS` (including `assistant_bundle_handoff`).
- Multi-turn results discussion and product help (RQ-series) have a **single**
  contract: `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md`. This is the only
  active implementation surface for those channels. AIA
  (`AI_RESEARCH_ASSISTANT_ROADMAP.md`), C2 (`AI_CHAT_2_ENGINEERING_ROADMAP.md`),
  and CAI (`CLASSIC_ASSISTANT_INTEGRATION_PLAN.md`) are **completed implemented
  roadmaps** — do not reopen them for results/help, and do not implement from
  the VA-1 stub in the voice doc. Implement only the active RQ PR’s
  **Files allowed to touch** list. Keep thesis-draft `handle_chat_turn`,
  results Q&A, and product help as separate channels; results/help messages
  must omit `choices` (draft hydration hazard); results may use RO
  `BUNDLE.import` but never `execute_confirmed_run` / `PIPELINE.*`; reuse C2-6
  grounding token rules. RQ-1 implements VA-1. Document any new `assistant_*`
  keys for these channels in `ARCHITECTURE.md` and `ASSISTANT_SESSION_KEYS` in
  the same PR. **RQ series is complete (RQ-0…RQ-5).** **RQ-0** shipped config
  sections + `thesistester/assistant/help_corpus.py` (§7.1 allowlist) and
  `load_results_qa_settings` / `load_product_help_settings` /
  `is_draft_channel_message` in `llm.py`. **RQ-1** shipped
  `results_qa.py`, `handle_results_turn`, Discuss results UI (originally
  keyed `st.text_input` + send — **superseded by RUX-3** page-level
  mode-scoped `st.chat_input`), draft history isolation, and
  `assistant_results_qa_drafts` (retired in RUX-3). **RQ-2** shipped
  `results_projections.py` (`results.projections.*`) and optional RO
  `TIME.analyze` enrichment (`allow_time_enrichment` default false).
  **RQ-3** shipped `product_help.py`, `handle_help_turn`, Help / how it works
  UI, corpus retrieval wiring, and `assistant_product_help_draft` — never load
  `AGENT_GUIDE` into Help. **RQ-4** shipped
  `classic_focus_channel="results_qa"` beside string `classic_focus_run_id`.
  **RQ-5** froze honesty/injection evals in
  `tests/test_assistant_llm_evaluations.py` (release gate). Do not reopen RQ
  for new features; voice remains VA-series only.
- Help **content/allowlist coverage** (making all primary features explainable
  via Help) has a **single** contract:
  `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` (HC-series, ✅ HC-0…HC-4).
  Maintain `docs/USER_GUIDE.md` with RQ §7.1.4 + `help_corpus.py` in the same
  PR; keep `tests/test_assistant_help_coverage.py` §5 bank + parity gates green;
  follow HC §1.1 for intent-aware retrieval (do not naively demote glossary);
  never allowlist stub/empty USER_GUIDE H2s; do not fork `product_help` / merge
  Help into thesis draft chat; never load `AGENT_GUIDE` into the user Help
  corpus.
- Research Assistant **page layout / surface prominence** has a **single**
  contract: `docs/RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md` (RUX-series, ✅
  RUX-0…RUX-5 complete; evidence
  `docs/archive/RESEARCH_ASSISTANT_UX_REFOCUS_EVIDENCE.md`). **Do not reopen RUX for
  layout changes; amend this contract instead.** RUX is **presentation-only**:
  it may change containers, ordering, captions, and additive presentation
  session keys on `pages/14_Research_Assistant.py`, and must not touch the
  engine, `thesistester/api.py`, `pages/1..13`, or
  `thesistester/assistant/{orchestrator,repository,registry,handlers,tools,results_qa,help_corpus,explainer}.py`
  logic. Channel separation, evidence grounding, confirmation gates, Discuss
  eligibility, voice gating/keys, and the CAI focus-key shape stay frozen; only
  the two RQ §1 `UI attach` rows are amendable, in the same PR that moves the
  widget. Navigation phrases live in one place (`assistant/ux.py` constants from
  RUX-1) — do not hand-write them at call sites. Keep the rendered-structure
  baseline `tests/test_assistant_page_render.py` green and rewrite (never
  delete) its assertions when layout changes. AppTest rule: `AGENT_GUIDE.md`
  §Development environment (B-12 / QI-11-03) — no `proto.*`, no disabled
  `set_value`.
- Realtime voice review (VA-series) has a **single** contract for **voice
  transport**: `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (rewritten
  post-RQ / post-HC; do not add a parallel voice-transport plan). **VA series
  is complete (VA-0…VA-6).** VA-1 is RQ-1; VA-0…VA-5 shipped
  contracts/session/tools/PTT/realtime sidecar; **VA-6** froze
  honesty/injection/grounding evals in
  `tests/test_assistant_voice_evaluations.py` (release gate; default remains
  `assistant.voice.enabled=false` in tracked TOML). Operators enable/switch
  modes from Research Assistant sidebar Voice controls
  (`config/assistant.voice.override.toml`, gitignored). Do not reopen VA/RQ/HC
  for voice features without a new contract amendment. Spoken Help inherits
  the HC-complete USER_GUIDE corpus + RQ §7.1.4 allowlist — do not widen §7.1
  from voice work. Prefer calling shipped `handle_results_turn` /
  `handle_help_turn` for spoken Discuss/Help rather than forking channel or
  corpus logic; voice tool calling may use only the VA-3 allowlist
  (`get_run_overview` / `get_metric` / `list_caveats` / `compare_two_runs`)
  and must never expose
  compute/`web_search`/`x_search`/`file_search`/`mcp`/`save_comparison` on
  voice sessions; results/voice may use RO `BUNDLE.import` but never
  `execute_confirmed_run` / `PIPELINE.*`; reuse C2-6/RQ grounding token rules
  (`voice/grounding.audit_spoken_text`); results/help/voice messages must not
  include `choices`. Document any new `assistant_voice_*` keys in
  `ARCHITECTURE.md` and `ASSISTANT_SESSION_KEYS` in the same PR. Keep HC
  coverage gates and VA-6 evals green
  (`tests/test_assistant_help_coverage.py`,
  `tests/test_assistant_voice_evaluations.py`).
- Full-duplex **discuss intelligence content parity** (making VA-5 overview/KPI
  talk reuse DI builders/paths/overlay/no-topic-swap without cloning the typed
  recovery pipeline) has a **single** follow-on contract:
  `docs/DUPLEX_INTELLIGENCE_IMPLEMENTATION.md` (DX-series). Do not reopen DI or
  VA wholesale for this; stay inside DX scope tables. DX must reuse DI pure
  functions (not fork cue/path tables), must not switch providers, must not
  pre-gate live PCM, must not default-enable voice, and must keep VA-6 / DI /
  RQ honesty suites green. DX-1 must honor the contract freezes for veto×legacy
  narrative strip, **veto ≠ unmatched** (export/use `has_overview_negative_cue`;
  unmatched / no-text → neutral `run_overview`, not remediation),
  session-transcript selector (no sidecar buffer peek), intent sample-size
  alias → `results.trade_summary.trade_count`, DI reply→envelope projection,
  and speakable `summary`-first preference. DX-2 adds the frozen §4.3 duplex
  overview constraint needles to realtime/results `build_honesty_instructions`
  only (not PTT/Help); sidecar must keep consuming that single builder.
  **DX-0…DX-3 are complete** — do not reopen DX for feature work without a
  contract amendment; keep `tests/test_assistant_duplex_intelligence.py` §9
  bank green alongside VA-6 / DI / RQ honesty suites.
- Specialist Discuss intelligence (best SL/TP, time, validation/WFA,
  single-metric, meaning overlays, mixed-ask composition, bounded trade
  projections, duplex specialist envelopes) has a **single** continuation
  contract: `docs/RESEARCH_INTELLIGENCE_IMPLEMENTATION.md` (RI-series).
  **RI-0…RI-10 complete** (`grid_ranking`, `time_ranking`, `validation_wfa`,
  `robustness_tier2`, `assumptions_costs`, `deep_trade`, `single_metric` +
  residual veto matcher + digit-free meaning overlay +
  `compose_deterministic_replies` + capped deep-trade projections + duplex
  specialist envelopes via shared `build_deterministic_discuss_reply`). Do not
  reopen DI/DX/RQ wholesale; amend the RI contract for follow-ons.
  Keep the RQ auditor fail-closed; fail-open only via frozen intent→allowlist
  builders. Permanent residuals (bare stop/ranking/monte) keep DX veto ≠
  unmatched. Never answer OOS/WFA asks with in-sample `single_metric` leaves.
  Keep RQ-5 / DI / DX / RI banks green.

## Development environment (R9)
- Editable install with tooling: `pip install -e ".[dev]" -c constraints.txt`
  (packaging metadata and caps live in `pyproject.toml`; `constraints.txt` is
  the CI lock — QI-12-02 / QR G-2).
- **Codespaces / Dev Containers (G-5 / QI-12-08).**
  `.devcontainer/devcontainer.json` uses Python **3.12**
  (`/usr/local/bin/python`) and
  `/usr/local/bin/python -m pip install --user -e '.[dev]' -c constraints.txt`.
  No extra `streamlit` install. Attach is
  `/usr/local/bin/python -m streamlit run app.py` (XSRF/CORS stay on;
  CLI flags and `STREAMLIT_SERVER_ENABLE_*` env aliases).
  `.streamlit/config.toml` is product transport caps only — do not rewrite
  it here. Lock: `tests/test_g5_devcontainer.py`. A full image-build
  workflow is optional and is **not** a G-1 required check.
- Before pushing, run exactly what CI runs:
  1. `ruff check .`
  2. `ruff format --check .`
  3. `pytest -q`
- **Pytest markers (B-15 / QI-11-05).** Registered warn-first:
  `unit` / `integration` / `golden` / `eval` / `benchmark` / `oracle` /
  `serial`. The required CI cell is still the **full suite** (`pytest -q`
  — do not add `-m unit` to G-1 jobs). Local loop: `pytest -m unit -q`
  (exit: < 5 min). Unmarked tests are legal and become `unit` at
  collection (`tests/conftest.py`). `--strict-markers` fails unknown
  names only. Do not add `pytest-xdist` until every AppTest module (or
  AppTest function in a mixed file) is `serial` (already true: B-12 /
  B-13). `oracle` is env-gated desk data and stays skipped in CI.
  Mixed oracle files keep unit siblings unmarked at module level.
  Benchmarks assert `median_ms >= 0` only — not a performance gate.
  Fail-closed lock: `tests/test_pytest_markers.py`.
- **Named-suite convention (B-16 / QI-11-06).** Accept-path tests assert the
  returned spec, accepted token, or helper state — not a bare no-raise.
  `validate_study_spec` / `validate_run_spec` / `clear_*` / dir-lock
  re-acquire / `_fsync_file` swallows are the QI-11 §2.5 twelve. Token
  asserts on `validate_run_spec` run **after** the call (admission, not
  fixture construction). A loosened validator or a no-op helper must
  fail those asserts. C-1 / C-3 (validator refactors) may land only
  while `tests/test_qi11_accept_asserts.py` stays green: each of the
  twelve bodies needs a non-tautological `assert` plus the named
  contract needles. `assert True` does not satisfy QI-11 §6.8. Fixture
  builders (`_bar` / `_ohlcv` / `_signal`) stay in the suite that owns
  the contract; do not consolidate them in the same PR as a validator
  or engine change.
- Lint scope is `E4`, `E7`, `E9`, `F`, `W`, plus **`B`** (QI-12-09 / B-17;
  first widening family: `B023` loop-variable = C1 class, `B905`
  zip-without-strict). Equal-length invariant zips use `strict=True`
  (groupby keys, TPO bucket↔bar, cohort tokens/labels). Sliding-window
  `zip(xs, xs[1:])` and ragged `split("|")` name/price pairs keep
  `strict=False`. Line length 100. Python only — Markdown is excluded
  so documentation snippets are never rewritten by the formatter. One
  family per PR; never a side effect of feature work. Never enable `S` on
  `tests/` (S101 assert flood). Never `PLR2004` as a first wave. Tests
  ignore noisy `B009`/`B905`/`B017`/`B904`; `B023` stays enforced — a
  family prefix ignore (`B` / `B0` / `B02`) must not swallow it.
  Fail-closed lock: `tests/test_ruff_b_family.py`. Next family (UP / I /
  SIM / …) is its own PR.
- **CAI cold-path harness (B-18 / QI-14-01).**
  `cai_levels_config(kind="realistic")` is tick-gated (`poc_windows=[]`).
  `measure_cai_cold_path` calls `compute_levels` only after
  `disable_unneeded_tick_families` on named setup tokens (`selected_levels`
  / anchor / rules), not the setup mapping keys. Do not revive
  typical-price `_rolling_poc`.
  `--fixture both` / `--fixture realistic` emit six stage rows. Timing
  tables stay informational; F-10 re-records them.
- **E402 / page import path (B-14 / QI-10-08).** Only `pages/1_Data.py` may
  execute code before importing `thesistester` (it inserts `REPO_ROOT` onto
  `sys.path`). The ruff `E402` per-file ignore is that file only — do not
  restore `"pages/*.py" = ["E402"]`. Other pages import at module top and
  resolve `thesistester` via the documented editable install
  (`pip install -e . -c constraints.txt`). `streamlit run app.py` puts the
  repo root on `sys.path` (Streamlit 1.63 prepends the **main** script
  directory). AppTest `from_file` of a page puts `pages/` on `sys.path[0]`.
  Without the editable install, non-Data pages then need the repo root on
  `sys.path` (B-13 smoke does this). Fail-closed lock:
  `tests/test_ruff_e402_pages.py`. Do not drop Data's bootstrap in a
  product PR until AppTest always injects the repo root and the
  editable-install job remains required.
- `ruff` is version-capped in the `dev` extra so formatting decisions cannot change under CI
  without an explicit bump. CI installs that spec with `-c constraints.txt`.
- **Lock + caps (G-2).** CI installs with `-c constraints.txt`. The `dev`
  extra (including G-4 `bandit` / `pip-audit`) must appear as `==` pins in
  that lock. Streamlit is
  capped `>=1.56,<1.64` so a 1.64 AppTest/proto change cannot silent-resolve
  (#478 was 1.63). Pandas majors are a **named** matrix axis, not an accident:
  `pytest (py3.10)` is the pandas **2** cell; `pytest (py3.11)` and
  `pytest (py3.12)` are pandas **3** cells (pandas 3 requires Python ≥3.11).
  Those six G-1 job display names are frozen — do not rename them to advertise
  the pandas major.
- Regen the lock (do not hand-edit pins):
  `uv pip compile pyproject.toml --extra dev --universal --python-version 3.10 -o constraints.txt`
- Version bumps arrive as Dependabot PRs (`.github/dependabot.yml`, weekly)
  against `constraints.txt` pins. `versioning-strategy: increase-if-necessary`
  widens a `pyproject.toml` cap only when the candidate sits outside it
  (so a Streamlit 1.64 PR moves the pin *and* the `<1.64` cap together and
  then hits the G-1 matrix). Do not land a bump inside a product PR.
  App/dev install is `pip install -e .` / `pip install -e ".[dev]"` against
  that lock (G-3); `pytest` lives in the `dev` extra only.
- **Mutation baseline (B-4 / QI-11-04).** Own-file comparison-swap sample on
  `engine/backtest.py` and `analytics/walk_forward.py` (QI-11 §2.2 / §10).
  Recipe: `python -m tests.fixtures.mutation.mutate_sample`. Committed
  baseline: `tests/fixtures/mutation/baseline.json`. Isolation: scratch
  package + `--import-mode=importlib` from a neutral cwd. The walk-forward
  sample **keeps** `tests/test_otf_integration.py` (`fold_local` already
  lives there) and the C-17 helpers (`_validate_walk_forward_run`,
  `_stitch_walk_forward_oos`) so P0 fold-size and overlap-reject
  comparisons stay inside the 12-site named surface. Gate for C-14 /
  C-17 / C-19: ≥ 70 % own-file killed
  (target 80 %). B-4 recorded adjusted rates: `backtest.py` 100 % and
  `walk_forward.py` 100 % (12/12). Timeouts count as killed. This is **not** a
  required CI cell. Do not add `[tool.mutmut]` here — QI-12 owns packaging.
- **Coverage floor (B-6 / QI-12-04).** `pytest` cells report statement+branch
  coverage of `thesistester` and emit `::warning` when the total is below
  **82%** (`COVERAGE_FLOOR` in `.github/workflows/ci.yml`). That is the
  QI-0 / QI-11 measured line (35,598 stmts / 5,132 missed; 14,994 branches /
  3,117 partial at `e30cc48`), not the R9 88% baseline or the old 85%
  informational line. The job still **does not** fail: `--cov-fail-under` and
  `[tool.coverage.report] fail_under` stay unset. A later PR flips the same
  floor to blocking, then ratchet +1 pt per release.
- **Import-linter (B-10 / QI-12-07).** `.importlinter` encodes QI-15 §5.4
  contracts C1–C5 and C7–C10. The CI job `import-linter (warn-first)` runs
  `lint-imports` and emits `::warning` on broken contracts; it **does not**
  fail. Config/runtime errors (no contract report) still fail the job.
  C7 is expected broken via journal.levels → study.schema → tick_vap →
  execution_artifacts → api (C-9 landed: package-init no longer loads
  `engine.backtest`; it does not keep C7). C9 (`sim_core` ↛ `entry_window_policy` / `analytics.*`)
  is kept (B-19 / QI-4 §6.3); AST resolves parent-package and relative
  imports. C12 is `tests/test_validation.py`, not this job. This job
  is **not** a G-1 required check. A later PR
  flips the same contracts to blocking. Do not rename the six required
  display names to absorb it.
- **mypy (B-11 / QI-12-05).** `[tool.mypy]` is path-scoped to
  `thesistester/engine` and `thesistester/analytics` with `--strict`,
  `--ignore-missing-imports`, and `--no-site-packages`. Not repo-wide.
  `api.py` / `data/` / `levels/` later. QI-12 §2.3 five-tree probe was
  **164** strict; B-11 records **97** engine/analytics-path errors in
  `tests/fixtures/mypy/baseline.json` (import-pulled errors are logged,
  not ratcheted). `--no-site-packages`
  keeps numpy stubs from aborting a 3.10-target run. The CI job
  `mypy (informational)` runs
  `python -m tests.fixtures.mypy.check_ratchet` and emits `::warning` on
  type errors or a ratchet increase; it **does not** fail. Config/runtime
  crashes (no type-check report) still fail the job. This job is **not**
  a G-1 required check. Count is monotonically decreasing per release —
  do not raise the committed total. A later PR flips the same scope to
  blocking. Do not invoke mypy from required pytest cells.
- **Security scans (G-4 / QI-12-06 / QI-07-09).** CI jobs
  `bandit (warn-first)` (`bandit -ll` on `thesistester`) and
  `pip-audit (warn-first)` (declared + transitive of the locked install)
  emit `::warning` and stay green. Config/runtime crashes still fail
  (missing bandit report / missing pip-audit "vulnerabilit" text).
  Neither job is a G-1 required check. Both scanners live in the `dev`
  extra and **must be pinned in `constraints.txt`** (same lock rule as
  B-10/B-11). **High must stay 0** (`tests/test_g4_security_scans.py`;
  empty/non-JSON bandit output is a fail, not High = 0). Medium
  `urlopen` (B310 in assistant LLM/voice) is warn-first. Blocking flip
  is a later PR.
  Actions are SHA-pinned (`checkout` / `setup-python` / `upload-artifact`
  v7.x commits). `[build-system]` is `setuptools>=83,<85` (clears
  PYSEC-2025-49 / 2026-1918 / 2026-3447). Study run-name fingerprints
  keep SHA-1 with `usedforsecurity=False` — digest unchanged; RS2
  golden names stay identical. SHA-256 switch is a dedicated identity
  PR. Do not add these jobs to the six frozen display names.
- **AppTest harness (B-12 / B-13 / MG-26).** Assert widget `.disabled`,
  named session keys, and rendered labels. `set_value` only on enabled
  widgets via `tests.apptest_helpers.set_enabled_value`. Missing
  `.disabled` fails closed (do not treat it as enabled). Never read
  `proto.*` — Streamlit 1.63 (#478 / plan §4.3) raises `AppTestError` on
  disabled `chat_input.set_value`. Never `list(session_state)` (QI-10-05:
  Streamlit 1.63 raises `KeyError` key `"0"`). Mark AppTest modules (or
  AppTest functions in a mixed file) `serial`. B-15 registered
  `unit` / `integration` / `golden` / `eval` / `benchmark` / `oracle`;
  AppTest `serial` items collect as `integration` so `-m unit` stays off
  the harness. Shared isolate fixture: `isolate_apptest_globals` in
  `tests/conftest.py` (autouse; restores the real
  `sys.modules["streamlit"]` before *and* after each test so helper
  stubs cannot brick `AppTest.run`; snapshots `__main__` / `sys.path`
  at setup and restores them after). Classic
  smoke: `tests/test_classic_pages_apptest.py` (`app.py` empty info; Data
  Sample auto-load; Backtest warning without `signals`; seed
  `signals`/`levels` before Backtest widgets). Per-page first render < 1 s.
  E402 ignore is `pages/1_Data.py` only (B-14 / QI-10-08); other pages
  rely on `pip install -e .` or the smoke helper that inserts repo root.
  `tests/test_ruff_e402_pages.py` fails closed if the ignore widens or
  another page grows a `sys.path` bootstrap.
  `tests/test_apptest_harness_rules.py` is fail-closed: discovers every
  `AppTest` import, AST-binds `serial`, rejects `proto` / bound
  `.set_value` / `list(session_state)`. RUX: rewrite assertions, never
  delete. Do not add classic click-through of Run (QI-10 §3.6: not
  feasible on an empty page).
- **Untestable-by-design (B-7 / QI-11-01).** Do not chase line coverage on
  these modules (QI-11 §2.3 debt map). Test the contracts named here; do
  not spawn a live sidecar or a provider socket:
  - `thesistester/__main__.py` — `if __name__` guard only. `cli.main()` is
    exercised from journal/study CLI tests; `test_cli.py` covers
    argparse / `run_batch`, not the `__main__` wrapper.
  - `thesistester/assistant/voice/sidecar.py` — subprocess / network
    lifecycle. Voice tests cover bind/redact, not launch or the health loop.
  - `thesistester/assistant/voice/xai_realtime.py` — provider I/O. Evals
    and realtime tests stub transports.

## Regression-safety gates in CI
`.github/workflows/ci.yml` runs on every push to `main` and every pull request.
These six job **display names** are the required status checks on `main`
(QI-12-01 / QR G-1; restores `ENGINEERING_PROPOSAL.md` §4 rule 9). The
branch-protection setting **is live** (admin-applied; **strict** up-to-date
requirement + **enforce admins** / `enforcement_level: everyone`). CI is
**blocking on red**: a red cell among these six **blocks** merge to `main`
(QI-12-10 / QI-13-01 — this wording is true only because the checks are
required). Names are frozen — renaming a job is a dedicated
protection-settings PR, not a side effect of feature work.
Required-check matching is exact-string on the display name; other workflow
cells do not block merge.

| Job | Gate |
|---|---|
| `ruff (lint + format)` | `ruff check` + `ruff format --check`; required on `main` |
| `pytest (py3.10)` | full suite; required on `main`. Coverage warns below the measured 82% floor (B-6 / QI-12-04); still not blocking (`--cov-fail-under` is a later PR) |
| `pytest (py3.11)` | full suite; required on `main` |
| `pytest (py3.12)` | full suite; required on `main` |
| `editable install (no dev extras)` | `pip install -e .` + import + `pip check` in a clean venv; required on `main` |
| `golden-master regeneration guard` | required on `main`; fails any PR that changes legacy golden artifacts without the `GOLDEN_REGEN` label. Job is `pull_request`-only (`ci.yml`); that is the merge path |
| `import-linter (warn-first)` | **not** required. B-10 / QI-12-07: `lint-imports` on `.importlinter` (C1–C5, C7–C10). Emits `::warning` on broken contracts; job stays green. Config/runtime errors (no contract report) still fail the job. Blocking flip is a later PR |
| `mypy (informational)` | **not** required. B-11 / QI-12-05: `--strict --ignore-missing-imports --no-site-packages` on `engine/` + `analytics/` only (not repo-wide). Per-file ratchet vs `tests/fixtures/mypy/baseline.json` (scoped paths only). Emits `::warning` on type errors / ratchet-up; job stays green. Config/runtime errors (no type-check report) still fail the job. `api.py` later. Blocking flip is a later PR |
| `bandit (warn-first)` | **not** required. G-4 / QI-12-06: `bandit -ll` on `thesistester`. High = 0 via `tests/test_g4_security_scans.py` (empty/non-JSON report fails). Medium findings emit `::warning`; job stays green. Config/runtime errors (no report) still fail. Blocking flip is a later PR |
| `pip-audit (warn-first)` | **not** required. G-4 / QI-12-06: declared + transitive audit of `pip install -e . -c constraints.txt` with locked `pip-audit>=2.7,<3`. Advisories emit `::warning`; job stays green. Missing report text or non-1 runtime errors still fail. Blocking flip is a later PR |

Verify the live gate from a non-admin token. `GET …/branches/main/protection`
is admin-only and returns **403** for integration tokens — do not treat that
403 as “protection is off”. Use the readable branch payload:

`gh api repos/AccumuLatata/ThesisTester/branches/main --jq '.protection.required_status_checks.contexts'`

Expect exactly these six strings, with `protected: true` and
`enforcement_level: everyone`: `ruff (lint + format)`, `pytest (py3.10)`,
`pytest (py3.11)`, `pytest (py3.12)`, `editable install (no dev extras)`,
`golden-master regeneration guard`.

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

## OTF validation matrix error surface

`run_otf_validation_matrix` / `_simulate` (QI-05-12): empty accepted
signals stay an empty trades frame (honest 0 trades). A `simulate_trades`
engine error **propagates** (typed); it must not look like a 0-trade
matrix row. `_simulate` has no `except`. The matrix loop re-raises
`ValueError` unchanged and wraps other exceptions as `ValueError`
(same narrow-guard as `apply_otf_filter`). AH3 train-price prefix
slicing is unchanged. Validation page already surfaces `ValueError`
as `st.error`. Do not restore
`except Exception: return _empty_trades_df()`.

## WFO OTF history policy

C-17 (QI-05-01) extracts P0 validate (`_validate_walk_forward_run`),
P3 train-grid (`_train_fold_grid`), P5 stitch (`_stitch_walk_forward_oos`),
and P6 summary (`_assemble_walk_forward_result`) from
`run_walk_forward_sl_tp`. Fold constructors (`_bar_fold_boundaries`,
`_session_fold_boundaries`) and `causal_prefix` (`_otf_source_for_fold`,
`_filter_fold_signals_with_otf`) stay in-place. The B-4 mutation
recipe names those P0/P5 helpers so overlap-reject and fold-size
`==` / `<=` sites stay in the 12-site sample. Identity vs the PR base
is live `assert_frame_equal` / field equality + `hash_dataframe` on
folds, OOS trades, and stitched equity (bars, sessions, overlap
first/last/reject, OTF, entry window, anchored, empty). Do not freeze
hexes. Compare detailed results by fields, not `WalkForwardResult`
class identity (the exec'd baseline class is a different object).

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

## Battery `schema_version` (B-19 / QI-05-13 / C12)

Result-dict version keys (QI-5 §2.4). Phase 8 is a **frozen unversioned**
shape — do not add `schema_version` or a fifth top-level key.

| Battery | `schema_version` | Notes |
|---|---|---|
| R10 `excursion_summary` | 1 | |
| R11 `monte_carlo_summary` | 1 | |
| R14 WFA `WalkForwardResult` / summary | **2** | |
| R15 `overfitting_summary` | 1 | Keep opt-in; do not change `validation_summary()` |
| R16 `noise_summary` | 1 | Keep opt-in; do not change `validation_summary()` |
| R19 `sensitivity_summary` | 1 | Keep opt-in; do not change `validation_summary()` |
| R21 `portfolio_summary` | 1 | |
| Phase 8 `validation_summary` | **none** | Frozen `{bootstrap, permutation, trade_count, grid_overfit}`. Empty / all-NaN: `None` not NaN + `insufficient`. Lock: `tests/test_validation.py` |
| OTF matrix | none | DataFrame |
| Grid | none | DataFrame |

## R15 overfitting research safety

- Keep R15 opt-in and retain `validation_summary()` unchanged.
- Treat PBO/DSR/vs-random as diagnostics of declared historical trials/nulls,
  never as proof of a durable edge.
- Use explicit `random_state`; do not replace local seeded RNG with global
  sampling.
- Preserve grid-cell execution assumptions when re-simulating sequences or
  random schedules. Shared execution-kwarg allow-list is public
  `SIMULATION_KWARGS` (R19 imports the same set). Directional columns come
  from public `directional_grid_metrics`.
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

## Locked composer forks (H7 / H10 / H15)

Disclosure only — do not invert these forks (A-22 / F-6). H7/H15 lock tests
are B-1; H10/H11 lock tests are B-2.

| Fork | Classic UI | `thesistester.api` / CLI / Study / Assistant | Lock tests |
|---|---|---|---|
| H7 cutoff without flatten | Backtest/Grid force `no_new_entries_after=None` when flatten is off | YAML cutoff still applies (`after_entry_cutoff`) | `tests/test_ah8_cutoff_without_flatten.py` |
| H15 OTF / Admit TZ | Backtest: Data-page `exchange_timezone` or instrument TZ | always `inst.exchange_tz` | `tests/test_ah8_otf_tz_ui_vs_api.py` |
| H10 fatal OHLCV | Legacy 1m primary installs + warns | `load_dataset` raises `ValueError` | `tests/test_data_page_helpers.py` (`test_h10_*`) |
| H11 mixed offsets | raw reject (pandas 3 `ValueError`; pandas 2 `.dt` `AttributeError`; not `DataValidationError`) | same (do not UTC-normalize) | `tests/test_loader.py` (`test_h11_*`) |

## R17 ingestion research safety

- Keep `dataset.format_profile` explicit in API/CLI specifications; canonical
  remains the default and no format auto-detection is permitted. Study builder
  emit always writes the key from the R17 allow-list (omitted / blank →
  `canonical`; unknown non-blank tokens fail emit).   The Studies page must not
  import `FORMAT_PROFILE_LABELS`, `normalize_builder_format_profile`,
  `INGESTION_MODE_PRIMARY`, or `WIDGET_KEY_INGESTION_MODE` from builder
  (stale `builder.py` bricks the page, including Inspect/Preview;
  import-linter **C10** / `tests/test_import_linter_contracts.py`). Bind
  labels from loader via a type-checked `getattr` plus local fallback; keep
  page-local normalize (blank → `canonical`; do not rewrite unknown tokens).
  Page-local ingest tokens; seed/Apply via getattr/hasattr (and
  `dataset_extra` when the first-class field is missing). C-2 (QI-01-06):
  `validate_run_spec` imports `FORMAT_PROFILES` /
  `DERIVE_15S_SUPPORTED_PROFILES` / `SUBTIMEFRAME_FORMAT_PROFILES` from
  loader. The Data page binds the derive and dual-upload subsets with the
  same type-checked `getattr` fallback. Builder `_FORMAT_PROFILE_LABELS_FALLBACK`
  stays.
- `dataset.subtimeframe_path` is always canonical OHLCV for R12 replay; it
  never inherits the primary dataset's vendor `format_profile`. Prefer
  `dataset.ingestion_mode: 15s_primary_derive_1m` when the primary file is
  itself the 15-second Quantower export; do not combine that mode with
  `subtimeframe_path`.
- 15s-primary derive (Data + `run_experiment`) resolves OHLC-identical
  source duplicate opens with `prepare_15s_source_for_derivation` before
  `derive_complete_parent_ohlcv` (lowest volume kept; audit in
  `ingestion_provenance`). OHLC conflicts stay fail-closed. Do not
  auto-dedup native one-minute primary bars. Do not put a second policy in
  the Data page.
- Preserve captured raw rows only as provenance; use canonical one-minute bars
  for current engine work and do not treat raw ticks as R12 subtimeframe data.
- Confirm the canonical sample CSV remains byte-identical after loader edits.
- Run `pytest -q tests/test_loader.py tests/test_vendor_loaders.py tests/test_local_store.py tests/test_data_page_helpers.py`
  after R17 changes. Keep H10/H11 lock tests green; do not invert the forks.

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
- Keep optimization work inside `engine.sim_core`. C-19 placed the serial
  P7 walk (`walk_trade_exit`) and AH1 flatten-cap math
  (`compute_session_close_cap`) behind `resolve_trade_bar`. Admission
  (window / cutoff / exposure / 3c-void), skip-row schema, costs, P&L,
  trade records, and diagnostics remain orchestrated by `backtest.py`.
  Do not widen `sim_core` into those concerns. C-20 may switch `BarData`
  storage; E-10 may accelerate only inside this boundary.
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
- **Phase 2/3 (Levels):** `pages/2_Levels.py`, level engines in `thesistester/levels/`.
- **Phase 6.5 (Setup Builder):** `pages/3_Setup_Builder.py`, setup helpers in `thesistester/setup.py`.
- **Phase 4 (Signals):** `pages/6_Signals.py`, signal/confluence functions in `thesistester/engine/`.
- **Phase 5 (Backtest):** `pages/7_Backtest.py`, simulator in `thesistester/engine/backtest.py`, metrics in `thesistester/analytics/metrics.py`.
- **Phase 6 (Grid):** `pages/8_Grid_Search.py`, grid analytics in `thesistester/analytics/grid.py`. C-6: `directional_grid_metrics` is public (R15 reuses it).
- **Phase 7 (Time):** `pages/9_Time_Analysis.py`, helpers in `thesistester/analytics/time_analysis.py`.
- **Phase 8 (Validation):** `pages/10_Validation.py`, diagnostics in `thesistester/analytics/validation.py`.
- **Phase 9 (Report/Export):** `pages/11_Report_Export.py`, artifact builders in `thesistester/reporting.py`. C-5 (QI-06-02): `build_markdown_report` walks `MARKDOWN_REPORT_SECTIONS` (walker AST-bound); emitted markdown is fixture-locked. C-6: page captions import `dash_if_none`; bundle parquet projection is `hash_dataframe`.
- **Research Bundles:** `pages/12_Research_Bundles.py`, bundle helpers in `thesistester/research_bundle.py`.
- **Portfolio:** `pages/13_Portfolio.py`.
- **Research Assistant:** `pages/14_Research_Assistant.py`, `thesistester/assistant/`.
- **Docs index:** `docs/README.md` (living vs contract vs archive/research).
- **Developing week/month VWAP (WMV):** `docs/WVWAP_MVWAP_IMPLEMENTATION_PLAN.md` (WMV0–WMV2 complete).
- **Anchor-only (AO):** `docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md` (AO1 implemented; empty rules + `min_valid=0` only).
- **Tick VAP (TV):** `docs/TICK_VAP_IMPLEMENTATION_PLAN.md` (TV1–TV4 landed; series complete). Tick-last ingest for prior VA only; attach paths on Data / Studies Build; no ticks → those nine columns absent; do not retick VWAP / OR / 3c.
- **A-period POC parity (AP):** `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md` (AP3 + desk default-tick follow-up). Default `apoc_profile_source` is `tick_last_volume_v1`. Named/product APOC without `tick_paths` refuses (`APOC requires ticks`); never typical fallback. Do not ship a bar-range proxy as Quantower-compatible. Tick math is reused from `apoc_candidates` via `apoc_tick.py`. Do not reuse `PriorProfileTable` as APOC. `run_experiment` / `compute_levels` must forward `dataset.tick_paths` into the A-period table even when a prior-VA parquet is present. Identity always stamps tick APOC; `LEVEL_ENGINE_VERSION` stays 11. Fresh Program B Wave 7 lives in `manifest_tick.yaml` (placeholder ticks, omitted source = product tick). Historical ZIPs stay typical-labeled; do not rewrite them. **Rolling POC is RP, not AP.** Product prior-profile aggregation is desk **4/8/10** (not a QT day lock).
- **Rolling POC parity (RP):** `docs/ROLLING_POC_QUANTOWER_INVESTIGATION_PLAN.md` (RP2 default tick Last×Volume + VA-style refuse follow-up). Production `POC_rolling_*` is two-pointer Last×Volume on `[now-W+1min, now+1min)`. Missing ticks refuse when rolling is required (`rolling POC requires ticks`), never typical and not quiet all-NaN as the product path. Do **not** edit `_rolling_poc` **body** (dead/non-default). Do not treat AP1’s 4/4 as a QT rolling scorecard. Do not reuse `PriorProfileTable` / `APeriodTickProfileTable`. Do not open RP2-cancel. Do not claim Quantower rolling-widget parity. No `LEVEL_ENGINE_VERSION` bump; identity keys stamp tick. Studies that name neither VA nor APOC/rolling still run on 15s-only.
- **Directional attribution (DA):** `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md` (DA0 locked). `touch` + `direction: both` + `single_position` is a long-only sample. Series code is **DA**; **DI is Discuss Intelligence**. Do not edit `_check_touch` or the candidate sort key. Do not rerun Program B on `touch` expecting shorts.
- **Journal → Study (JS):** `docs/JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md` (JS2 landed; JS0 locked). Zone attribution (`detect_confluence_zones` on the previous completed 1m bar: `bar_open + 1min <= fill`; exact `09:30:00` uses `09:29`, not TJ6 `_expected_previous_open`) + CLI `journal zones` + page 17 Q3 Zones. Trigger inference (`classify_zone_triggers` wrapper; 1m + `15s_proxy`; `trigger_timeframe="base"` never `"1min"`; 3c not inferred) + CLI `journal triggers` + page 17 Q3 Inferred trigger. C-9 (QI-08-02): journal barrel lazy-exports helpers; `triggers.py` lazy-imports `_classify_zone_triggers_detail` so `import thesistester.journal` does not load `engine.backtest` or bind `simulate_trades`. Call-ban unchanged. Later: frequency-selected `explicit_cells` StudySpec with fail-closed `holdout`, TJ8 multi-bundle rule-vs-desk. Gate A can stop the series after JS2. Do not add a 15s trigger lane, invent core×partner×trigger cartesians, omit `constants.backtest` SL/TP, regenerate goldens, select factors by outcome, or auto-run the proposed study. No new USER_GUIDE H2. Do not implement JS inside a TJ/DA PR.
- **Trade journal (TJ):** `docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md` (TJ9 landed; series complete). TradesViz executions CSV (Layer 1, UTC) + AMP Daily Statement PDF (Layer 2, fees) only; Quantower loader parked (Vienna-local clock). `session_date` is `trading_session_date` (`eth_start=18:00`), not NY calendar date. Journal `r_multiple` / currency P&L scale with **qty**; do not copy 1-lot `simulate_trades` formulas. C-10 (QI-08-01): `qty_scaled_journal_pnl` is the write home; `journal_cost_ticks` is shared. Do not call `simulate_trades` or `compute_all_levels` from journal code. Developing levels use the adjacent previous 1m bar whose close is strictly before the fill (a gap omits the token). Store under `.thesistester_store/journal/v1/` (not `execution_artifacts/`). Page 17 is read-only over ingested artifacts (Q1–Q8; n < 30 hidden unless toggled). Do not commit desk PII exports. TradesViz `commission`/`fees` are unused; AMP is the fee SoT. Tags are intent — verify against the levels frame, never treat as a trigger. `touch`/`3c` are context (entry style; `3c` is desk-written, not journal-inferred). TJ7 15s walk starts at the next 15s open; the only RNG is the seeded direction-shuffle null (preserves per-session long/short counts); discipline rules are declared with a date, never searched. TJ8 matches **one** named hash-verified cell (never the Observatory corpus); `product_mismatch` names hold/risk; the live-declaration file is read-only. Do not rebuild generic journal stats TradesViz already provides.
  Journal CLI: `JournalIngestError` prints `journal <cmd> failed: …` and
  exits 2 with no traceback — including malformed / empty / non-PDF AMP
  bytes at `extract_amp_pdf_text` (QI-08-03). Do not let pdfplumber/pdfminer
  leak a stack through `journal reconcile`.
- **Voice sidecar ops:** `docs/VOICE_SIDECAR_OPS.md`.
