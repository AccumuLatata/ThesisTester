# ThesisTester audit overview (Slice 0)

**Mode:** research / investigation only. No application-code changes.
**Scope:** independent repo map so later in-depth slices can go deep without rereading the tree.
**Checkout verified against:** `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/POINT_IN_TIME_GUARANTEES.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `README.md`, `thesistester/api.py`, `app.py`, `thesistester/cli.py`, plus package `__init__`s, page imports, and test layout.

This file is the Slice 0 deliverable. Later agents should treat it as the starting contract map, then verify the listed files — not the whole repo.

---

## 1. Product, entry points, runtime data flow

### What it is

ThesisTester is an **intraday futures strategy-research workbench** (ES / NQ / MES / MNQ). It is not a live trading system and does not claim a durable edge.

The research object is a **confluence setup**: selected session/structural/indicator/profile levels → zone detection (global cluster or anchor rules) → trigger (`touch` / `reject` / `break` / `reclaim` / `3c`) → candidate signals → bar-by-bar simulation under explicit execution assumptions (costs, exposure, session flatten, R12 intrabar model, R13 BE/trail, optional OTF admission, optional entry-window Admit).

Outputs are **diagnostics**. Validation, walk-forward, OTF matrix, Focus, and Study reports are honesty-gated screening tools.

### Three entry points (same engine, different composers)

| Surface | Entry | Role |
|---|---|---|
| Streamlit UI | `streamlit run app.py` → `pages/*.py` | Classic research loop. Pages **compose `thesistester.engine` / `analytics` / `setup` directly**. They do **not** generally call `thesistester.api`. Session bus: `st.session_state` (contract table in `docs/ARCHITECTURE.md`). |
| Headless facade | `thesistester.api` | Streamlit-free orchestration: `load_dataset → compute_levels → build_setup → generate_signals → run_backtest → run_grid → run_validation` plus `run_experiment` (bundle-ready dict). Owns composition only; no alternate trading logic. |
| CLI / Study | `python -m thesistester` → `thesistester/__main__.py` → `cli.py` | YAML schema v1 batches: `run_experiment` + `build_research_bundle()`. Workers isolate **independent runs**; a single pipeline stays single-threaded. Study Runner (`thesistester/study/`) expands a StudySpec to an R18 experiment and runs cells via its **own** `run_experiment` loop (does **not** call `run_batch`). |

Assistant compute (`thesistester/assistant/tools.py`) also routes through `api.run_experiment` / `validate_run_spec`, not through page code.

`thesistester/app_state.py` is the only library module that imports Streamlit **at module scope**. Several `classic_*` and assistant modules import Streamlit **lazily inside functions**. Data, levels, engine, analytics, persistence, reporting, and visualization stay Streamlit-free.

### Real runtime data flow

The README one-liner `Data → Levels → Setup Builder → Signals → Backtest` is the **classic mutate path**. The ARCHITECTURE mermaid then continues Grid → Time → Validation → Report, with Bundles / Portfolio / Assistant as **parallel consumers**, and Studies as a **parallel non-mutating** surface.

```text
CSV / vendor profile / 15s-primary derive
        │
        ▼
canonical OHLCV (exchange TZ) + session tag (RTH/ETH)
   [optional subtimeframe_data for R12]
        │
        ▼
compute_all_levels  (+ session_levels table)
        │
        ▼
setup_config  (levels, trigger, confluence mode, optional otf_filter)
        │
        ▼
zones + naked flags + candidate signals     ← OTF is NOT applied here
        │
        ▼
apply_configured_otf_filter  (Backtest / Grid / WFA only, default off)
        │
        ▼
simulate_trades  (fills, costs, exposure, session flatten,
                  R12, R13, optional Admit entry_window)
        │
        ├─► metrics / equity / skip audit
        ├─► Grid (same engine, SL/TP sweep; OTF once before cards)
        ├─► Time Analysis Focus (post-hoc subset; no re-sim)
        ├─► Admit Promote → re-sim under entry_window
        ├─► Validation / WFA / batteries / OTF matrix
        ├─► Report + Research Bundles + Portfolio
        ├─► Research Assistant (discuss bound evidence / Help)
        └─► Study Runner (factorial cells → same run_experiment)
```

**Critical composition facts (verified in code):**

1. **Signals emit the full candidate population.** OTF and Admit filter at execution, not at generation (`README.md`, `docs/ARCHITECTURE.md` OTF notes, `api.generate_signals` vs `api.run_backtest`).
2. **OTF config provenance:** `signal_settings["otf_filter"]` wins over later Setup Builder edits. Regenerating signals is required to pick up OTF changes.
3. **UI Backtest OHLCV source:** `pages/7_Backtest.py` prefers `st.session_state["levels"]`, else `"data"`. `api.run_experiment` passes the **levels** frame into `run_backtest`. Both frames carry OHLCV; levels also carry level columns. Later slices must confirm OTF/WFA never accidentally consume future level columns as if they were market state.
4. **UI vs API are two composers of the same functions.** Parity is a tested contract (`tests/test_api.py`, `tests/test_cli.py`, `tests/test_assistant_execution_parity.py`), not a shared page function. A bug can exist in one composer only.
5. **Focus ≠ Admit.** Focus filters completed trades by **entry** time and rebuilds subset equity (no `simulate_trades`). Admit is a constrained re-simulation (`entry_window` on `simulate_trades`). Contracts C1–C9: `docs/SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md`.
6. **Studies does not walk the Data page or classic `session_state`.** Parity is the RunSpec / `run_experiment` contract (`pages/15_Studies.py`, `thesistester/study/`).
7. **There are no `pages/4_*.py` or `pages/5_*.py`.** Numbering jumps `3_Setup_Builder` → `6_Signals`.

### Session-state bus (classic path)

Authoritative producer/consumer table: `docs/ARCHITECTURE.md` § `st.session_state` contract. Studies-only keys (`studies_builder_*`, `studies_catalog_*`, `studies_viewer_*`) must not be read from Data / Levels / Setup.

Handoff keys that later slices will treat as the pipeline:

| Stage | Produced keys | Next consumer |
|---|---|---|
| Data | `data`, `instrument`, TZ keys, `format_profile`, optional `subtimeframe_*`, `ingestion_provenance` | Levels, Backtest/Grid/WFA (R12) |
| Levels | `levels`, `session_levels`, `levels_settings`, fingerprint | Setup, Signals, Backtest |
| Setup | `setup_config` (+ library on disk) | Signals, OTF resolve |
| Signals | `signals`, `confluence_zones`, `naked_flags`, `signal_settings`, hash, `last_signal_setup` | Backtest, Grid |
| Backtest | `trades`, `trade_summary`, `equity_curve`, skip/OTF/intrabar/exit-mgmt keys | Time, Validation, Report, Bundles |
| Time | `time_*`, Focus/Promote `focus_*` / `entry_window_*` | Backtest Admit, Report |
| Validation | `validation_summary`, WFA/R10–R16/R19/OTF-matrix keys | Report, Bundles, Assistant |
| Bundles / Portfolio / Assistant | restore / composite / evidence packets | parallel |

### Persistence topology (not in the live loop, but on every path)

Store root: process `THESISTESTER_STORE_DIR` → repo `.env` (`THESISTESTER_STORE_DIR` only) → `<repo>/.thesistester_store`.

User trees: `datasets/`, `levels/`, `signals/`, `setups/`, `assistant/`. Internal cache: `execution_artifacts/v1/` (CAI-2/3). UI defaults: `ui_state.json`. Eviction must never touch user trees.

---

## 2. Module map

### `thesistester/` (packaged library)

| Area | Owns | Couples to |
|---|---|---|
| `config.py` | `Instrument` presets (tick, point value, `America/New_York`, RTH 09:30–16:00, `eth_start=18:00`, Asia 20:00–00:00, London 02:00–05:00), `TIMEZONE_OPTIONS`, OHLCV required columns | Data session tag, levels, OTF, Admit, display |
| `timezone_display.py` | Display/export TZ only (`display_timezone`). Engine stays on exchange TZ | Pages 1/7/9/11, report export |
| `data/loader.py` | Vendor profiles: `canonical`, `ninjatrader`, `sierra_intraday`, `quantower_history_exporter`, `databento_trades`, `tick_capture`, `second_capture`. TZ localize/convert, validate, interval infer | `api.load_dataset`, Data page, derive, R12 interval parse |
| `data/sessions.py` | `tag_session` → `session` ∈ {RTH, ETH} from **clock** vs `rth_start`/`rth_end` | Levels (if `session` missing they re-derive), UI |
| `data/resample.py` | OHLCV resample 1min…1D | Data page preview, OTF HTF, higher-TF indicators/pivots |
| `data/derive.py` | `15s_primary_derive_1m`, policy `observed_aligned_15s_to_1m_v2` | Data page, `api._load_15s_primary_experiment_data`, identity cache key |
| `data/rolls.py` | Roll **metadata / gap diagnostics only** — no continuous-contract synthesis | Data page, `api.validate_roll_assumptions` |
| `levels/session_date.py` | `trading_session_date` (ETH 18:00 boundary; midnight is not a reset) | Session levels, dVWAP, prev30m, OTF, WFA |
| `levels/sessions.py` | Structural/session levels (pd*, ONH/ONL, Asia/London, OR, RTH_Open, prevSettlement, pRTH_*) | `levels/all.py`, PIT suite |
| `levels/indicators.py` `profile.py` `pivots.py` `session_vwap.py` `tpo.py` `apoc.py` `prev30m_vwap.py` | Indicator / profile / advanced families | `all.py`; product gates in `defaults.py` |
| `levels/all.py` | Orchestrates families. **Keyword gates default False** (legacy additive API) | `api.compute_levels` via `research_identity.normalize_levels_config` |
| `levels/defaults.py` | **Product** defaults (advanced families **True**; OR 15; SMA/EMA/VWAP/POC windows) | API, Levels page, Study schema, identity |
| `levels/common.py` | Shared window labels / helpers | Study schema, indicators |
| `setup.py` | Setup normalize/validate, trigger/TF allow-lists, OTF setup blob, eligible level columns (excludes `prev30mVWAP_hit_*`) | Signals, Setup Builder, API, study, persistence hashes |
| `entry_window_policy.py` | Engine-safe C1 RTH segments + `normalize_entry_window` / `entry_window_contains`. **No analytics import** (avoids `simulate_trades` ↔ `analytics.grid` cycle) | Engine, setup, execution_defaults, analytics re-exports |
| `execution_defaults.py` | Sanitize persisted Backtest/Grid widget defaults (Streamlit-free) | Pages 7/8, persistence `ui_state.json` |
| `engine/confluence.py` `anchor_confluence.py` `candidate_level.py` `naked.py` | Zones + naked flags (per-bar; inherit level causality) | `api.generate_signals`, Signals page |
| `engine/signals.py` `signals_3c.py` | Public triggers + 3c 4-rule / 8-variant model; DST-safe non-base TF grouping | Setup, backtest entry models |
| `engine/otf.py` | Pure HTF one-timeframing **state machine** | `otf_filter.py`; uses `data.resample` + `levels.session_date` |
| `engine/otf_filter.py` `otf_integration.py` | Admission + config resolve + `OtfFilterResult` | `api.run_backtest` / `run_grid` / WFA, pages 7/8/10 |
| `engine/backtest.py` | `simulate_trades`: admission, next-bar vs 3c retrace fill, costs, exposure, session flatten, skip reasons | `sim_core`, `intrabar`, `exit_management`, `entry_window_policy` |
| `engine/sim_core.py` | R22 extracted bar-resolve core | `backtest.py` |
| `engine/intrabar.py` | R12 models: `sl_first` (default), `path_open_proximity`, `subtimeframe`, `subtimeframe_conservative` | Data page compatibility report; backtest/grid/WFA |
| `engine/exit_management.py` | R13 BE/trail; commit after bar close, active next bar | `simulate_trades` |
| `analytics/metrics.py` | KPIs, equity, directional summaries | Backtest, grid, Focus, report |
| `analytics/grid.py` | SL/TP sweep — **calls `simulate_trades`** | Page 8, overfitting replay |
| `analytics/time_analysis.py` | Buckets; **re-exports C1 `RTH_SEGMENTS` from `entry_window_policy`** | Page 9 |
| `analytics/entry_window.py` | Focus / Promote / inherit / honesty banners; re-exports policy | Pages 7/8/9/10, reporting, bundles |
| `analytics/validation.py` `walk_forward.py` `excursions.py` `monte_carlo.py` `overfitting.py` `noise.py` `sensitivity.py` `otf_validation.py` `portfolio.py` `confluence_attribution.py` `prev30m_vwap_hit.py` | Post-trade / robustness / portfolio / combo diagnostics | Page 10/13, API, report |
| `api.py` | Typed facade + `validate_run_spec` + `run_experiment` + cache policy | CLI, study.execute, assistant.tools, classic_export |
| `cli.py` `__main__.py` | YAML batch + `results_index.csv`; no study↔cli cycle (`_coerce_index_float` duplicated by design) | `research_bundle` |
| `study/*` | RS/SB/SIA/SV: schema, expand, execute, report, promote, rollup, preview, launch, builder, viewer, optional assistant tools | `api.run_experiment` only; viewer must not import execute/cli/rollup/Streamlit/Plotly |
| `research_identity.py` | `DataIdentity` / `LevelsIdentity` / `ExperimentIdentity`; shared levels normalizer | API cache, bundles, classic export |
| `research_bundle.py` | Zip snapshot + `canonical_bundle_hash` (never raw ZIP bytes) | CLI, assistant complete_run, page 12 |
| `reporting.py` | Artifact / MD / CSV export from **current state** (no re-sim) | Page 11 |
| `persistence/local_store.py` | User snapshots, hashes, UI defaults, dotenv | Pages, app_state |
| `persistence/execution_artifacts.py` | Content-addressed data/levels cache | `api` CAI-3; `read` can import `api.load_dataset` |
| `classic_*.py` | Thesis chrome, nav, ledger, export, record, proposal | Pages 3/6/7/12/14; lazy Streamlit |
| `assistant/*` + `assistant/voice/*` | Registry, orchestrator, Help corpus, Discuss, LLM, voice sidecar (default off) | `api`, bundles, `config/assistant.toml`, env/Secrets |
| `visualization/*` | Plotly charts (levels/signals/backtest/trade-review) | Pages 2/6/7; no engine logic |
| `app_state.py` | Restore saved dataset into session | Data + most classic pages |

### `pages/` (not packaged)

| Page | Owns | Must not be treated as |
|---|---|---|
| `app.py` (root) | Hub copy + “data loaded?” | Engine |
| `1_Data.py` | Ingest, vendor profile, 15s-primary vs legacy dual-upload, rolls UX, resample preview, R12 compatibility **report** (never patches) | Level math |
| `2_Levels.py` | Family toggles, `compute_all_levels`, fingerprint stale-check, save | Signal logic |
| `3_Setup_Builder.py` | Setup library, confluence mode, OTF blob, suggested levels | Execution |
| `6_Signals.py` | Zones, naked, `generate_signals`, saved runs, copy-setup-back | OTF admission |
| `7_Backtest.py` | OTF + `simulate_trades` + Focus overlay + Admit + combo attribution + R20 review | Signal generation |
| `8_Grid_Search.py` | Same execution assumptions; OTF once; ranking / directional gates | Per-cell OTF re-resolve |
| `9_Time_Analysis.py` | Buckets, Focus, Promote | Re-simulation |
| `10_Validation.py` | Phase 8 + R10–R16/R19 + WFA + OTF matrix | Engine fills |
| `11_Report_Export.py` | Export from session | Recompute trades |
| `12_Research_Bundles.py` | Zip export/import / restore keys | Classic mutate except restore |
| `13_Portfolio.py` | R21 via `api.run_portfolio_analysis` | Capital simulator |
| `14_Research_Assistant.py` | Presentation + orchestrator dispatch | In-page `run_experiment` |
| `15_Studies.py` | Build / Preview / Inspect / CLI spawn | Classic `session_state` / in-process `run_study` |

### `tests/`

| Cluster | Files (representative) | Guards |
|---|---|---|
| Data / vendor / derive / rolls | `test_loader`, `test_vendor_loaders`, `test_derive`, `test_rolls`, `test_15s_primary_persistence`, `test_data_page_helpers` | Ingest, TZ, 15s policy |
| Levels / PIT | `test_r3_point_in_time`, `test_session_levels`, `test_phase3_levels`, `test_stage1`–`test_stage6_*`, `test_dvwap_cme_session`, `test_prev30m_vwap*` | Future-shock + family contracts |
| Setup / confluence / signals / 3c | `test_setup_*`, `test_phase4_engine`, `test_anchor_confluence`, `test_candidate_level`, `test_signals_*`, `test_3c_*` | Generation causality |
| Execution | `test_phase5_backtest`, `test_sim_core`, `test_intrabar`, `test_exit_management`, `test_otf*`, `test_entry_window_*` | Fills, OTF, Admit |
| Analytics / WFA | `test_phase5_metrics`, `test_phase6_grid`, `test_phase7_time_analysis`, `test_phase8_validation`, `test_walk_forward`, `test_session_focus`, `test_excursions`, `test_monte_carlo`, `test_overfitting`, `test_noise`, `test_sensitivity`, `test_otf_validation`, `test_portfolio`, `test_confluence_attribution` | Diagnostics honesty |
| Golden | `tests/fixtures/golden/*`, `test_golden_master`, `test_otf_golden`, `test_entry_window_golden` | **Legacy-unchanged** gate, plus additive OTF/Admit families |
| API / CLI / identity / cache | `test_api`, `test_cli`, `test_research_identity`, `test_cai3_*`, `test_execution_artifacts`, `test_local_store`, `test_research_bundle` | Composer + cache parity |
| Study | `tests/study/test_study_*` | Expand/execute/report boundaries |
| Assistant / classic / UI | `test_assistant_*`, `test_classic_*`, `test_cai9_*`, `test_ui_copy_guards`, `tests/visualization/*` | Evidence, Help, nav |
| Benchmarks | `tests/benchmarks/` | Informational CAI / simulate timing |

Golden operational spec: `tests/fixtures/golden/README.md` + `docs/ENGINEERING_PROPOSAL.md` §4. Goldens prove **default-off legacy identity**, not engine correctness.

### `docs/`

| Class | Use in audit |
|---|---|
| **Living primary** (`docs/README.md`) | `ARCHITECTURE`, `AGENT_GUIDE`, `ASSUMPTIONS_AND_LIMITATIONS`, `POINT_IN_TIME_GUARANTEES`, `USER_GUIDE`, `METRICS_GLOSSARY`, `ENGINEERING_ROADMAP`, `otf-filter.md`, `research-methodology.md`, `ANCHOR_CONFLUENCE.md` |
| **Normative frozen contracts** | SW, 15s-primary, prev30m, Study RS/SB/SIA/SV, assistant RQ/HC/DI/RI/DX/VA/RUX/CAI/C2/AIA |
| **§4 only living in** `ENGINEERING_PROPOSAL.md` | Golden + PR checklist. **§§1–3 are a pre-R9 snapshot** — do not treat as current capability |
| `archive/` `research/` | Historical. Not status SoT |

### Other roots (not in lead slices, but real)

- `config/assistant.toml` — non-secret assistant settings (`study_tools` default off; voice default off).
- `.env.example` — **only** `THESISTESTER_STORE_DIR`. Secrets: `OPENAI_API_KEY` via env or Streamlit Secrets (see `AGENT_GUIDE`).
- `examples/studies/` — StudySpecs + external coworker prompts.
- `sample_data/`, `scripts/`, `.streamlit/config.toml` (350 MB upload / 400 MB websocket).
- **No top-level `vendor/` package.** Vendor fixtures: `tests/fixtures/vendor/`. Roll logic: `thesistester/data/rolls.py`.

---

## 3. Highest-risk / highest-leverage correctness areas

Ordered by **research-correctness leverage** (lookahead / PIT / session / fills), not by UI surface area.

| Rank | Area | Why it is high leverage | Primary files | Tests to start from |
|---|---|---|---|---|
| 1 | **Lookahead / PIT on levels** | Every zone/signal inherits level causality. R3 audit is the SoT but is vintage-bounded (see §5). Same-bar close/volume in SMA/EMA/VWAP/POC/dVWAP is **documented intent**, not next-bar. Clock-gated OR / Asia / London / APOC / prev30m vs bar-existence. | `levels/*.py`, `docs/POINT_IN_TIME_GUARANTEES.md` | `test_r3_point_in_time.py`, stage/family tests |
| 2 | **Timezone + trading session** | Three clocks: source TZ, engine `exchange_timezone`, display TZ. Session date uses `eth_start` (18:00 ET); calendar midnight is not a CME reset. Dual helpers: `data.sessions.tag_session` (RTH/ETH **clock**) vs `levels.session_date.trading_session_date` (session **date**). WFA/OTF/dVWAP/ONH depend on the latter. Session flatten is **same-calendar-day RTH-style**; overnight ETH flatten is **not** modeled (`ASSUMPTIONS`). | `config.py`, `data/loader.py`, `data/sessions.py`, `levels/session_date.py`, `timezone_display.py` | `test_loader`, `test_session_levels`, `test_dvwap_cme_session`, `test_signals_trigger_timeframe_dst` |
| 3 | **3c trigger** | Looks forward within a wait window; must never backdate `bar_index` to arrival. Non-base TF: structure on trigger candles, retrace fill on **base** bars; wait counts trigger bars. Deprecated `arrival_tolerance_ticks` ignored (strict touch). Legacy `confirm_3bar` helper still in `signals.py` but **not** a public `generate_signals` trigger. | `engine/signals_3c.py`, `engine/signals.py` | `test_signals_3c*.py`, `test_3c_mode_integration.py`, PIT 3c cases |
| 4 | **Fills / slippage / R12 / R13** | Simple triggers: next-bar open. Filled 3c: `retrace_entry_price` on `entry_bar_index`. Default `sl_first` if SL and TP both reachable. `path_open_proximity` is a heuristic, not truth. `subtimeframe` fail-closed; `subtimeframe_conservative` SL-first on holes. Costs default **zero**. MAE/MFE uses **full parent extremes** (can include post-exit extreme in-bar). BE/trail activate **next bar**. | `engine/backtest.py`, `sim_core.py`, `intrabar.py`, `exit_management.py` | `test_phase5_backtest`, `test_intrabar`, `test_exit_management`, `test_sim_core` |
| 5 | **OTF admission** | Default off. Applied at Backtest/Grid/WFA, not Signals. Decision `T` = `trigger_timestamp` else `timestamp`; only HTF bars with `availability_timestamp <= T`. WFA `fold_local` (default) vs `causal_prefix`. Config hash + `eth_start` must match instrument. | `engine/otf*.py`, `docs/otf-filter.md` | `test_otf*.py`, `test_otf_golden.py` |
| 6 | **Entry window (Focus vs Admit)** | C1 segments must stay single-sourced (`entry_window_policy.RTH_SEGMENTS`). Admit uses **entry-bar local time**, not signal-bar. Window checked before cutoff (C9). Focus must not be described as re-sim. Grid/WFA inherit a **fixed** window (not a sweep axis). | `entry_window_policy.py`, `analytics/entry_window.py`, `engine/backtest.py` | `test_entry_window_*.py` |
| 7 | **Walk-forward** | Legacy default `fold_mode="bars"`. Session folds use ETH-aware dates. Stitched OOS must not double-count overlap (default reject). OTF history policy can leak if `causal_prefix` is mis-implemented. Train-selected params on test = leakage if mislabeled. | `analytics/walk_forward.py`, page 10 | `test_walk_forward.py` |
| 8 | **Golden vs engine** | Three families: **legacy** (OTF/Admit/R12-off), **OTF-enabled**, **entry_window-enabled**. Legacy goldens are a drift gate, **not** a correctness proof. Regenerating legacy artifacts requires `GOLDEN_REGEN` + `--confirm-regenerate`. Pandas-major hash skip is intentional. | `tests/fixtures/golden/`, `test_golden_master.py` | Read `fixtures/golden/README.md` before any engine claim |
| 9 | **15s-primary derive vs vendor 1m** | Derived 1m volume (hence VWAP/POC) ≠ vendor-native 1m. Same source bytes + different `ingestion_mode` are different `DataIdentity`s. Duplicate OHLC-identical 15s rows resolved pre-derive; native 1m never auto-deduped. | `data/derive.py`, `data/loader.py` | `test_derive.py`, `test_15s_primary_persistence.py` |
| 10 | **UI / API / Study composer drift** | Three orchestrations of the same functions. Cache warm path must not change hashes. Study execute must not alter `run_batch` abort semantics. | `api.py`, `cli.py`, `study/execute.py`, pages 7/8 | `test_api`, `test_cli`, `test_cai3_*`, `tests/study/test_study_execute.py` |

**Lower leverage for a correctness audit (still real product risk):** Assistant evidence/honesty, Help corpus drift, voice sidecar, Windows store paths, Streamlit payload caps. Put these last.

---

## 4. Recommended sequential slice plan

Lead draft (5 slices) is a usable first cut but **too wide in the middle** (signals+execution together; analytics+study together; kitchen-sink Slice 5) and **wrong on `vendor/rolls`**. Below: **7 slices**. Each is one cloud-agent deep-dive. Later slices may assume earlier **contracts** (not earlier findings).

**vs lead draft (justification):**

| Lead | Change | Why |
|---|---|---|
| Slice 1 Data & time + `vendor/rolls` | Keep, but replace `vendor/rolls` with real paths; add `session_date` + derive + vendor **fixtures** | No `vendor/` package. Session-date is the CME clock contract every later PIT/OTF/WFA slice needs. |
| Slice 2 Levels **and** setup/confluence | **Split.** Slice 2 = levels only | ~10 causal families + PIT table is a full deep-dive. Adding setup/confluence forces a shallow pass. |
| Slice 3 Signals **and** execution | **Split.** Slice 3 = setup/zones/naked/signals/3c; Slice 4 = execution (fills/OTF/Admit/R12/R13) | Different failure modes (generation causality vs fill/admission). Combined, neither gets future-shock depth. |
| Slice 4 Analytics + study | **Split.** Slice 5 = analytics/WFA; Slice 6 = study | Study is a second product surface with hard import/session boundaries; WFA/Focus honesty is a different audit. |
| Slice 5 Assistant + persistence + API + remaining UI | Keep as **Slice 7** (last) | Needs locked pipeline contracts. Includes UI↔API parity and golden **policy**, not a second engine rewrite. |

**Cross-cutting rule for every slice:** also read the **`api.py` function(s) that compose that stage** and the matching page. Do not dump all of `api.py` into one slice.

**Shared exclude for all slices:** do not implement, refactor, or “fix” code; flag only. Do not reopen frozen assistant contracts (AIA/C2/CAI/RQ/…) except to note honesty/PIT impact. Do not regenerate goldens.

### Slice 1 — Data, time, session identity

**Depends on:** nothing.
**Produces for later slices:** canonical OHLCV schema; source→exchange TZ rules; `session` vs `trading_session_date`; 15s-primary vs legacy dual-file; roll-assumption honesty; R12 **data** contract (coverage/reconcile), not fill models.

**Include**

- `thesistester/data/` (`loader.py`, `sessions.py`, `resample.py`, `derive.py`, `rolls.py`)
- `thesistester/config.py`
- `thesistester/timezone_display.py`
- `thesistester/levels/session_date.py` (session-date **contract** only)
- `thesistester/api.py` — `load_dataset`, `_load_experiment_data`, `_load_15s_primary_experiment_data`, `preview_resampled_ohlcv`, `validate_roll_assumptions` (ignore the rest)
- `pages/1_Data.py`
- `tests/test_loader.py`, `test_vendor_loaders.py`, `test_derive.py`, `test_rolls.py`, `test_15s_primary_persistence.py`, `test_data_page_helpers.py`, `test_signals_trigger_timeframe_dst.py` (TZ/DST ingest angle only)
- `tests/fixtures/vendor/`
- Docs: `ASSUMPTIONS` ingest/derive/roll bullets; `docs/15s_primary_derived_1m_implementation_plan.md`; ARCHITECTURE R17 + 15s + TZ captions

**Do not wander into:** level family math, signals, `simulate_trades`, OTF state machine, assistant, study builder (except noting SIA RunSpec ingest tokens), `engine/intrabar.py` fill logic (compatibility **report** on the Data page is in-scope; path models are Slice 4).

### Slice 2 — Levels and point-in-time

**Depends on:** Slice 1 session/TZ/bar identity.
**Produces:** causal availability table per family; product-default vs `compute_all_levels` keyword-default split; setup-eligible vs diagnostic columns.

**Include**

- `thesistester/levels/` **except** treat `session_date.py` as already contracted (re-verify usage only)
- `thesistester/research_identity.py` — `normalize_levels_config` only
- `thesistester/api.py` — `compute_levels` only (note it calls `compute_all_levels` **and** `compute_session_levels` again)
- `pages/2_Levels.py`
- Tests: `test_r3_point_in_time.py`, `test_session_levels.py`, `test_phase3_levels.py`, `test_stage1_level_plumbing.py` … `test_stage6_levels_ui_settings.py`, `test_dvwap_cme_session.py`, `test_prev30m_vwap.py`, `test_levels_page_helpers.py`
- Docs: `POINT_IN_TIME_GUARANTEES.md` (full table), `levels` sections of ASSUMPTIONS, ARCHITECTURE Stage 6, `docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md`

**Do not wander into:** `engine/confluence.py`, `engine/signals*.py`, backtest, OTF, study, assistant. `analytics/prev30m_vwap_hit.py` is Slice 5 (trade-time contingency).

### Slice 3 — Setup, confluence, naked, signals, 3c

**Depends on:** Slice 2 level columns + eligibility.
**Produces:** zone/naked/signal row contracts; 3c timestamp/index semantics; trigger-TF alignment; “OTF not applied here”.

**Include**

- `thesistester/setup.py`
- `thesistester/engine/confluence.py`, `anchor_confluence.py`, `candidate_level.py`, `naked.py`, `signals.py`, `signals_3c.py`
- `thesistester/api.py` — `build_setup`, `generate_signals`
- `pages/3_Setup_Builder.py`, `pages/6_Signals.py`
- `thesistester/visualization/signals_chart.py`, `levels_chart.py` (display only; flag if they imply causality)
- Tests: `test_setup_config.py`, `test_setup_builder_helpers.py`, `test_phase4_engine.py`, `test_anchor_confluence.py`, `test_candidate_level.py`, `test_signals_3c.py`, `test_signals_3c_trigger_timeframe.py`, `test_signals_page_helpers.py`, `test_3c_mode_integration.py`, PIT signal/naked/confluence cases in `test_r3_point_in_time.py`
- Docs: `ANCHOR_CONFLUENCE.md`, README 3c / Phase 4, PIT signals section

**Do not wander into:** `simulate_trades`, OTF **admission** (`otf_filter` / `otf_integration` — Setup may **store** `otf_filter` config; that blob’s **application** is Slice 4), entry-window Admit, grid, WFA, study execute.

### Slice 4 — Execution engine (fills, OTF, Admit, R12, R13)

**Depends on:** Slice 3 signal row semantics (`entry_model`, `status`, `entry_bar_index`, `retrace_entry_price`, `trigger_timestamp`).
**Produces:** fill/skip/cost/exposure/session-close/OTF/Admit/intrabar/exit-mgmt contracts; UI vs `api.run_backtest` / `run_grid` composition.

**Include**

- `thesistester/engine/backtest.py`, `sim_core.py`, `intrabar.py`, `exit_management.py`, `otf.py`, `otf_filter.py`, `otf_integration.py`
- `thesistester/entry_window_policy.py` (Admit `contains` / normalize)
- `thesistester/execution_defaults.py`
- `thesistester/api.py` — `run_backtest`, `run_grid` (and how `run_experiment` passes levels + subtimeframe)
- `pages/7_Backtest.py` (execution + skip/OTF/Admit widgets only), `pages/8_Grid_Search.py` (execution composition only)
- Golden **pipelines**: `tests/fixtures/golden/pipeline.py`, `pipeline_otf_enabled.py`, `pipeline_entry_window_enabled.py` + `test_golden_master.py`, `test_otf_golden.py`, `test_entry_window_golden.py`
- Tests: `test_phase5_backtest.py`, `test_sim_core.py`, `test_intrabar.py`, `test_exit_management.py`, `test_otf.py`, `test_otf_filter.py`, `test_otf_integration.py`, `test_otf_contract.py`, `test_otf_baseline.py`, `test_entry_window_admission.py`, `test_entry_window_sw2b.py`, `test_entry_window_sw3.py`, `test_backtest_grid_defaults.py`
- Docs: `otf-filter.md`, SW plan C1–C9, ARCHITECTURE R12/R13/SW2–SW6, ASSUMPTIONS §§1–4a

**Do not wander into:** Focus-only helpers beyond what Admit consumes; WFA fold construction (Slice 5, except OTF-on-fold application which this slice must specify as a **contract** for Slice 5); metrics formulas; study; assistant; combo-attribution UI (Slice 5).

### Slice 5 — Analytics, Focus, validation, walk-forward

**Depends on:** Slice 4 trade/skip/OTF/Admit schemas.
**Produces:** metric definitions vs implementation; Focus honesty; WFA leakage; battery “diagnostic only” claims; combo attribution vs engine.

**Include**

- `thesistester/analytics/` **except** treat `grid.py` **ranking/metrics** here and **re-sim loop** as already contracted in Slice 4 (verify they stay aligned)
- `thesistester/analytics/entry_window.py` (Focus/Promote/inherit)
- `thesistester/api.py` — `run_validation`, `run_walk_forward`, `run_time_analysis`, `run_otf_validation`, `run_noise_test`, `run_sensitivity_profile`, `run_portfolio_analysis`
- `pages/8_Grid_Search.py` (ranking / directional gates), `pages/9_Time_Analysis.py`, `pages/10_Validation.py`, `pages/13_Portfolio.py`
- Tests: `test_phase5_metrics.py`, `test_institutional_metrics.py`, `test_phase6_grid.py`, `test_phase7_time_analysis.py`, `test_phase8_validation.py`, `test_walk_forward.py`, `test_session_focus.py`, `test_entry_window_sw4.py`, `test_entry_window_sw5.py`, `test_entry_window_sw6.py`, `test_excursions.py`, `test_monte_carlo.py`, `test_overfitting.py`, `test_noise.py`, `test_sensitivity.py`, `test_otf_validation.py`, `test_portfolio.py`, `test_confluence_attribution.py`, `test_prev30m_vwap_hit_analytics.py`
- Docs: `METRICS_GLOSSARY.md`, `research-methodology.md`, ARCHITECTURE R14–R16/R19/R21, ASSUMPTIONS validation/WFA/Focus

**Do not wander into:** `simulate_trades` internals (Slice 4), study execute/ledger, assistant Discuss projections except to **list** which metric leaves they cite, report zip format (Slice 7).

### Slice 6 — Study Runner

**Depends on:** Slices 1–5 RunSpec / `run_experiment` contracts.
**Produces:** expand↔execute fidelity; resume/lock; honesty of report/promote/rollup; Studies page isolation.

**Include**

- `thesistester/study/` (all)
- `pages/15_Studies.py`
- `examples/studies/` (as spec fixtures, not engine)
- `tests/study/`
- Docs: `STUDY_RUNNER.md`, RS/SB/SIA/SV plans (amend-only)

**Do not wander into:** `engine/`, Data/Levels/Signals pages, classic `session_state`, assistant STUDY.* tools except the **default-off / approval-triple** contract (full assistant stack is Slice 7). Do not import `pages/1_Data.py` from study code (SIA rule).

### Slice 7 — Persistence, identity/cache, API/CLI orchestration, bundles, reporting, classic, assistant, remaining UI

**Depends on:** Slices 1–6 stage contracts.
**Produces:** composer parity (`run_experiment` vs pages vs assistant); cache warm ≠ semantic change; bundle hash stability; report honesty; assistant evidence/security; leftover UI.

**Include**

- `thesistester/api.py` — `validate_run_spec`, `run_experiment` (full), remaining helpers
- `thesistester/cli.py`, `__main__.py`
- `thesistester/research_identity.py` (full), `research_bundle.py`, `reporting.py`
- `thesistester/persistence/`
- `thesistester/classic_*.py`, `app_state.py`
- `thesistester/assistant/` (including `voice/`)
- `pages/11_Report_Export.py`, `12_Research_Bundles.py`, `14_Research_Assistant.py`, `app.py`
- `config/assistant.toml`, `.env.example`, `.streamlit/config.toml`
- `thesistester/visualization/backtest_chart.py`, `trade_review_*.py`, `chart_window.py`
- Tests: `test_api.py`, `test_cli.py`, `test_research_identity.py`, `test_research_bundle.py`, `test_phase9_reporting.py`, `test_local_store.py`, `test_execution_artifacts.py`, `test_cai3_cached_pipeline.py`, `test_cai10_artifact_ops.py`, `test_cai9_page_capabilities.py`, `test_classic_*.py`, `test_app_state.py`, `test_assistant_*.py`, `test_ui_copy_guards.py`, `test_streamlit_server_limits.py`, `tests/visualization/*`, `tests/benchmarks/` (informational only)
- Docs: ARCHITECTURE CAI/R18/R20 + persistence topology; `AGENT_GUIDE` assistant/secrets; `ENGINEERING_PROPOSAL.md` §4 (golden **policy**, not a re-audit of fills); Help-corpus allowlist docs if honesty claims drift

**Do not wander into:** re-auditing level formulas, 3c rules, or fill models except where API/page/assistant **compose them differently**.

---

## 5. Doc-vs-code drift already visible (flag only)

These are overview-depth flags. Later slices confirm or dismiss.

1. **`ENGINEERING_PROPOSAL.md` §§1–3** still read as “today” (1-min only, SL-first only, no headless API). Banner says they are a pre-R9 snapshot; `docs/README.md` agrees. **Do not use §§1–3 as capability SoT.**

2. **`POINT_IN_TIME_GUARANTEES.md` vintage.** Header: R3 / June 2026, “do not extend claims beyond what is tested here.” Body later adds OTF + WFA OTF policies. **Audited-module table omits** `backtest.py`, `sim_core.py`, `intrabar.py`, `exit_management.py`, `otf_filter.py`, `walk_forward.py`. Slice 2/4 must not treat the table as exhaustive.

3. **`engine/otf.py` module docstring** still says the calculator has “no integration into … backtests, grid-search, walk-forward.” True of this file’s **purity**; false as a product statement. Integration is `otf_filter.py` / `otf_integration.py`. Easy to misread.

4. **`compute_all_levels` vs `DEFAULT_LEVELS_SETTINGS`.** `levels/all.py` documents advanced gates **disabled by default** (low-level API). Product/API/UI defaults in `levels/defaults.py` enable them. Intentional, but easy to audit as a bug.

5. **`api.compute_levels` double session-level call.** `compute_all_levels` already runs `compute_session_levels`; `compute_levels` then computes `session_levels` again for the table handoff. Flag redundancy / argument-drift risk.

6. **ARCHITECTURE Streamlit claim** is narrowly true (module-scope `app_state` only). Lazy `import streamlit` now exists in `classic_*.py` and assistant voice/llm. Headless-purity story is still intact for engine/analytics.

7. **Lead draft path `vendor/rolls` does not exist.** Rolls = `thesistester/data/rolls.py`; vendor CSVs = `tests/fixtures/vendor/`; profiles = `data/loader.py`.

8. **ARCHITECTURE mermaid** is linear through Report; Studies (`pages/15`) is a parallel, non-mutating product. README workflow stops at Backtest. Both are incomplete vs the full graph in §1.

9. **Session flatten vs CME session.** ASSUMPTIONS: optional `flat_by_session_close` is same-calendar-day RTH-style; ETH overnight templates not modeled. Easy to confuse with `eth_start` session **date** used by levels/OTF/WFA.

10. **Goldens ≠ correctness.** `tests/fixtures/golden/README.md` is explicit. Docs that say “golden-gated” mean **legacy identity**, not “fills are right.”

11. **Help-corpus paths are frozen** (`docs/README.md` maintenance rule). USER_GUIDE / ARCHITECTURE / ASSUMPTIONS / METRICS / otf-filter / research-methodology / root README. Slice 7 honesty audit must not propose casual path moves.

---

## 6. Open questions later slices must answer

### Slice 1

- Are timezone-naive vs aware CSV paths fully fail-closed for mixed files?
- Does 15s-primary duplicate resolution ever drop a **conflicting** group, or only OHLC-identical?
- Do roll diagnostics ever get treated as adjusted continuous prices downstream?
- Does `tag_session` (clock RTH) ever disagree with `trading_session_date` (18:00) in a way pages/engine mix?

### Slice 2

- Which PIT rows are still inspection-only (`—` in the R3 table), and have post-R3 families been future-shock tested at the same standard?
- Does `api.compute_levels`’ second `compute_session_levels` use identical OR minutes / instrument as `compute_all_levels` in all paths (UI, cache hit, Study)?
- Are `prev30mVWAP_hit_*` columns ever selectable as setup levels despite `NON_LEVEL_OUTPUT_COLUMNS`?
- Clock-gate vs bar-existence for OR / Asia / London / APOC: any path that emits early?

### Slice 3

- Non-base 3c: is retrace monitoring strictly after trigger-candle **completion**, and is `max_entry_wait_bars_after_reversal` counted only in trigger TF?
- Naked filter: arrival-bar only in all confluence modes (global + anchor + 3c sources)?
- Does any chart or saved-run path rewrite `bar_index` / `timestamp` after generation?
- Is `confirm_3bar` unreachable from UI/API/Study, or still callable via a back door?

### Slice 4

- UI vs `api.run_backtest`: identical OTF resolve order, `eth_start`, entry-window None-vs-disabled, and levels-vs-data source frame?
- When SL/TP/entry coincide in one sub-bar, is residual ambiguity always SL-first and never credited as TP?
- Does `allow_all` exposure plus overlapping 3c/simple signals inflate counts in a way reports under-disclose?
- Session flatten: any ETH entry flattened at calendar close incorrectly?
- Golden families: which engine knobs are **uncovered** (R13 on, conservative R12, costs > 0, `single_position`)?

### Slice 5

- Focus equity: any UI copy that implies path drawdown under all-day admission?
- WFA session folds: off-by-one on `eth_start` session dates? Overlap stitch leaking trades?
- `causal_prefix` OTF: prefix strictly `< fold start`?
- Excursion calibration (`both_hit_rule`) vs selected R12 model: still independent, and is that labeled?
- Grid “best cell” ranking vs WFA train selection: any test-sample peek?

### Slice 6

- Expand → cell RunSpec: bitwise-identical to a hand-written R18 YAML for the same factors?
- Soft resume: can a failed cell be skipped in a way that silently drops it from honesty totals?
- Promote: any auto-run path? Studies Preview/Build: any in-process `run_study`?
- Report PF/win-rate source: index vs bundle `trade_summary` — which wins, and is it labeled?

### Slice 7

- Cold vs warm `run_experiment`: equal `canonical_bundle_hash` in all ingestion modes (including 15s-primary + subtimeframe re-read)?
- Bundle restore: can leftover Streamlit upload widgets overwrite imported `data` (ARCHITECTURE claims a nonce flag — still true)?
- Assistant: any numeric claim without a packet path? Can `STUDY.run` / confirmed execute fire without the bound approval triple?
- Secrets: does any code log or persist `OPENAI_API_KEY` / Bearer material?
- `classic_export` / assistant compiler: can a prose field become an executable RunSpec key?

### Cross-slice (merge report)

- Single SoT for “what is causal at time T” across levels, 3c, OTF, R12, Admit, WFA.
- Whether UI, API, CLI, Study, and Assistant can disagree on one experiment without a test failing.
- Whether living docs (PIT table, OTF module docstring, proposal §§1–3) should be amended after slices — **do not amend in Slice 0.**

---

## How the next agent should start

1. Read **this file** and the **include list for your slice only**.
2. Read the named living/contract docs in that include list.
3. Trace **page composer** and **`api.py` composer** for that stage side by side.
4. Run (or read) the listed tests; do not treat goldens as proof of correctness.
5. Return findings as: contract, evidence (file + test), severity (lookahead / honesty / drift / isolation), and open questions you closed or created.
6. Do not implement fixes. Do not wander outside your exclude list unless a dependency is missing from Slice 0 — then record the gap for the merge report.
)
