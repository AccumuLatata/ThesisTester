# ThesisTester — In-Depth Repository Analysis

**Document type:** Repository analysis (feature scope, quality, functionality)
**Date:** 2026-07-29
**Method:** Static analysis of the full tree plus runtime verification: `pytest -q` (**1516 passed in ~31 s**), two end-to-end engine smoke runs on synthetic NQ 1-minute data (levels → confluence → signals → backtest → metrics → validation), and manual review of the core engine, analytics, and all 14 documents in `docs/`. No code was modified.

Related documents:

- `docs/SOTA_BACKTESTING_LANDSCAPE.md` — market research this analysis is compared against.
- `docs/ENGINEERING_PROPOSAL.md` — comparison + regression-safe roadmap built on both.

---

## 1. Verdict (TL;DR)

ThesisTester v0.2.0 is a **focused, well-tested Python/Streamlit research workbench** for intraday ES/NQ futures confluence setups: CSV OHLCV in → levels → confluence zones → trigger signals → fixed SL/TP bar-by-bar backtest → grid search, time analysis, statistical validation, walk-forward, and reproducible export.

Its distinguishing strength is **engineering discipline unusual for a solo research tool**: an explicit point-in-time audit with future-shock regression tests, a 1.8:1 test-to-code ratio, deterministic seeded statistics, schema-versioned persistence, and meticulous honesty documentation about what its numbers do and do not mean. Its weaknesses are structural, not sloppiness: **no CI, no packaging, bar-level OHLC simulation only, CSV-only ingestion, Streamlit-only workflow, and a deliberately narrow realism/validation envelope** compared to state-of-the-art platforms.

**Quality scorecard** (10 = best-in-class):

| Dimension | Score | Note |
|---|---|---|
| Functional correctness of what is implemented | 9 | 1516 tests green; PIT audit; deterministic; verified end-to-end |
| Test quality & coverage breadth | 8 | Broad unit/contract/regression coverage; no CI, no coverage gates, no property-based tests |
| Code quality & documentation | 8 | Excellent docstrings/design notes/docs set; no lint/type config, no packaging |
| Simulation realism vs SOTA | 4 | OHLC bars, SL-first, fixed bracket only; no intrabar resolution, bid/ask, order types |
| Data capability vs SOTA | 3 | CSV-only, ES/NQ presets, no tick/quote/depth, no continuous-contract synthesis |
| Validation/robustness science vs SOTA | 5 | Bootstrap + permutation + WFA present; no Monte Carlo suite, PBO/DSR, noise tests |
| Analytics depth | 6 | Strong trade-statistics (R6) incl. MAE/MFE capture; MAE/MFE *analytics* not surfaced |
| Workflow/automation | 3 | Streamlit multipage only; no CLI/headless API, no batch experiments, no replay |

**Comparator note:** the "vs SOTA" scores weight the quantitative-research tier (StrategyQuant X, Build Alpha, RealTest, AmiBroker, VectorBT, LEAN) and the analyzer subsystems of retail platforms more heavily than chart/replay tooling, per the framing in `docs/SOTA_BACKTESTING_LANDSCAPE.md` §1.1. ThesisTester is a quantitative setup-research tool, not a replay platform; "no replay" above is recorded as a workflow fact, not scored as a deficiency against order-flow replay tools.

---

## 2. Repository snapshot

| Fact | Value | Evidence |
|---|---|---|
| Version | 0.2.0 | `thesistester/__init__.py` |
| Language | Python (≥3.10 idioms: `list[str] \| None`, `zoneinfo`) | package source |
| Package LOC | ~13,494 (`thesistester/`) | `wc -l` |
| Pages LOC | ~6,800 (10 Streamlit pages) | tree scan |
| Test LOC | ~24,900 (48 files) | tree scan |
| Test suite | **1516 collected, 1516 passed, ~31 s** | `pytest -q` run 2026-07-29 |
| Dependencies | streamlit ≥1.56, pandas ≥2.2, numpy ≥1.26, plotly ≥5.22, pyarrow ≥16, pytest ≥8.2 | `requirements.txt` |
| Packaging | **none** — no `pyproject.toml`, not pip-installable | tree scan |
| CI | **none** — no `.github/`, no lint/type/pre-commit config | tree scan |
| License | **none** | tree scan; GitHub license field null |
| Docs | 14 markdown docs (~6.3k lines) + README | `docs/` |
| Git history | 349 commits; development via phased PRs (Phase 1–9, R1–R8, OTF PR 1–6, Stage 1–7) | `git log` |
| Runtime store | `.thesistester_store/` (gitignored): datasets, levels, signals, setups, UI defaults | `docs/ARCHITECTURE.md` |

Architecture (verified against `docs/ARCHITECTURE.md`):

```text
CSV OHLCV (ES/NQ, typically 1m, tz-normalized)
  → levels (session + indicator/profile + opt-in auction structure)   [thesistester/levels/]
  → confluence zones (global cluster | anchor rules) + naked flags     [thesistester/engine/]
  → trigger signals (touch/reject/break/reclaim/3c, ± OTF filter)      [thesistester/engine/]
  → fixed SL/TP backtest (next-bar / 3c retrace entry, SL-first)       [thesistester/engine/backtest.py]
  → metrics / SL×TP grid / time buckets / bootstrap+permutation+WFA    [thesistester/analytics/]
  → report / JSON+parquet research bundles                             [thesistester/reporting.py, research_bundle.py]
```

State flows between pages through a documented `st.session_state` contract (24 keys with producer/consumer tables in `docs/ARCHITECTURE.md`).

---

## 3. Feature scope (as implemented)

### 3.1 Data layer (Phase 1)

- CSV OHLCV ingestion (`timestamp/open/high/low/close/volume`) with header aliases (Quantower-style `Date Time`, `Volume(from bar)`), dot-date day-first parsing, upload or path (`thesistester/data/loader.py`).
- Timezone handling: naive timestamps localized to a user-selected source timezone and converted to the exchange timezone (`America/New_York`); aware timestamps converted directly (`pages/1_Data.py`, README Phase 1).
- Base-interval inference from timestamp gaps; RTH/ETH session tagging per instrument calendar (`thesistester/data/sessions.py`); resampling `1min→1D` (`thesistester/data/resample.py`).
- Instrument presets: ES and NQ only (tick 0.25; $50/$20 per point; RTH 09:30–16:00 ET) (`thesistester/config.py`). No MNQ/MES/CL/GC.
- Roll metadata modes (`single_contract`, `external_continuous`, `segmented_contracts`) with gap diagnostics — **no price adjustment synthesis** (R7, `thesistester/data/rolls.py`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §Roll).
- Local persistence of datasets as parquet + JSON meta (`thesistester/persistence/local_store.py`).

### 3.2 Level engine (Phases 2–3, Stages 1–6)

- Session/structural levels: overnight high/low, opening range, RTH open, prior day/week/month O/H/L/EQ, settlement preview (`thesistester/levels/sessions.py`).
- Indicator/profile levels: SMA/EMA (multi-timeframe), rolling VWAP, rolling POC windows, prior day/week/month VAH/VAL/POC with 70% value area on tick-bucketed bins (`thesistester/levels/indicators.py`, `profile.py`).
- Opt-in advanced families (all default **disabled**, regression-safe): confirmed pivots (`pivots.py`), developing session VWAPs (`session_vwap.py`: `dVWAP_RTH` + `dVWAP`), TPO 30m Single Prints (`tpo.py`), APOC/pAPOC (`apoc.py`).
- Orchestration via `compute_all_levels()` emitting scalar columns onto the shared DataFrame (`thesistester/levels/all.py`); a smoke run produced **52 level columns** on 3 days of synthetic 1-minute NQ data.
- Known approximation: profile bins use bar-level typical price `(H+L+C)/3`, not true volume-at-price (documented in `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §5d).

### 3.3 Confluence & signals (Phase 4, OTF PR 1–6)

- Global cluster confluence (`detect_confluence_zones`, greedy sliding-window over selected level columns within a tick tolerance) and anchor-rule confluence (per-rule tolerances around an anchor level, with rich per-zone diagnostics) (`thesistester/engine/confluence.py`, `anchor_confluence.py`, `docs/ANCHOR_CONFLUENCE.md`).
- Naked/untested level flags via pure forward scan (`thesistester/engine/naked.py`).
- Five trigger types: `touch`, `reject`, `break`, `reclaim`, `3c` (`thesistester/engine/signals.py`, `signals_3c.py`). The `3c` trigger implements a documented 4-rule / 8-variant model (muted, SFP) with configurable retrace ticks and wait window.
- Trigger timeframe support (`base`, `1min`, `5min`, `15min`) with DST-safe UTC flooring for tz-aware data (README Phase 4; `docs/ARCHITECTURE.md` notes).
- **OTF (One Timeframing) directional filter** — a pure, contract-tested HTF filter with its own authoritative spec (`docs/otf-filter.md`), persistence versioning, research-mode integration, and a validation release gate (PRs 1–6).
- Saved signal runs with settings-hash matching and copy-back-to-Setup-Builder (README).

### 3.4 Backtest engine (Phase 5, R1, R2, R4)

`simulate_trades()` in `thesistester/engine/backtest.py` (717 lines, reviewed in full):

- Entries: simple triggers at **next-bar open** (no look-ahead); filled `3c` signals at `retrace_entry_price`; void 3c rows skipped. Legacy `confirm_3bar` path retained internally.
- Exits: fixed SL/TP bracket with **SL-first pessimistic rule** when both are reachable in one bar (documented in module design notes); optional `max_holding_bars` TIME exit; optional session-aware `flat_by_session_close` producing `SESSION_CLOSE`/`DATA_END` (R2); default legacy `EOD` at dataset end.
- Costs (R1): optional per-side commission and adverse slippage ticks; defaults zero for backward compatibility; slippage applied to entry and exit fills (stop anchored to the *slipped* entry — verified numerically in a smoke run: 12-tick stop, 1-tick slippage, $2/side commission → −1.15R per loser, matching hand calculation).
- Exposure/lifecycle (R4): `allow_all` (default), `single_position`, `single_direction`, `single_setup` admission policies with deterministic ordering, optional cooldown, and optional skipped-signal diagnostics.
- Rich trade schema (44 columns) including `mae_points`/`mfe_points` excursion tracking, entry model, exit reason, zone provenance, and cost breakdown.

### 3.5 Analytics (Phases 5–8, R5, R6)

- `summarize_trades()`: win rate, expectancy, profit factor, avg/median/std R, Sharpe-like/Sortino-like R, ulcer index, drawdown, streaks, tail ratio, skew/kurtosis, outlier-dependency, recovery factor, payoff stability (R6 institutional metrics) (`thesistester/analytics/metrics.py`); long/short splits in UI and grid rows.
- SL×TP grid search with directional metrics and balanced weaker-side ranking gates (`thesistester/analytics/grid.py`).
- Time-of-day bucketing by RTH segment/hour/30-min with low-sample warnings (`thesistester/analytics/time_analysis.py`).
- Statistical validation (Phase 8): bootstrap expectancy CI (seeded), sign-flip permutation test, trade-count adequacy, heuristic grid-overfit warning — all explicitly **diagnostic, not proof of edge** (`thesistester/analytics/validation.py`).
- Walk-forward diagnostics (R5): deterministic bar-index folds; train-window SL/TP selection → OOS evaluation; fold-local OTF filtering with leakage-safe "insufficient history → reject as unknown" handling (`thesistester/analytics/walk_forward.py`, `otf_validation.py`).

### 3.6 Workflow & persistence (Phases 6.5, 9, R8)

- Multipage Streamlit UI: Data → Setup Builder → Levels → Signals → Backtest → Grid → Time → Validation → Report/Export → Research Bundles (page numbering skips 3–4 — removed stale pages, cosmetic gap).
- Setup library with dataset scoping, duplicate/activate/delete, compatibility checks (`pages/2_Setup_Builder.py`).
- Save-as-default execution settings with independent, schema-versioned `backtest_defaults`/`grid_defaults` namespaces, silent-drop validation of stale values, never auto-saved (R8, `thesistester/execution_defaults.py`).
- Export: `research_artifact.json`, `research_report.md`, CSV tables; zip research bundles (parquet + JSON) with import (`thesistester/reporting.py`, `research_bundle.py`).
- Plotly charting for levels/signals/backtest overlays with windowing/payload-reduction work already done (`thesistester/visualization/`, `docs/chart-visualization-engineering-rollout.md`).

---

## 4. Functionality verification (runtime evidence)

Performed 2026-07-29 on Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.60.0:

1. **Full test suite:** `pytest -q` → **1516 passed in 30.87 s**, zero failures/skips/xfail noise.
2. **End-to-end smoke run A** (3 days synthetic 1-min NQ random-walk): `compute_all_levels` → 52 columns/1170 rows; confluence/signals/trades handled empty sets gracefully (no crashes on zero zones/signals/trades; metrics return `None` cleanly).
3. **End-to-end smoke run B** (price constructed to touch prior-day high): 270 zones → 12 touch signals → 12 trades with `entry_model=next_bar_open`, SL exits, correct MAE/MFE tracking, and net-of-cost R exactly matching hand calculation (−1.15R = −1R gross − 1 tick round-trip slippage − $4 commission, over $60 risk). Confirms cost model arithmetic and stop-anchoring semantics.
4. **Validation pipeline:** `validation_summary()` returned seeded bootstrap CI and permutation outputs deterministically.

The documented pipeline in README/ARCHITECTURE matches observable behavior; no undocumented behavior was encountered in the exercised paths.

---

## 5. Quality assessment

### 5.1 Strengths

- **Point-in-time rigor rare in this class of tool.** A completed R3 audit (`docs/POINT_IN_TIME_GUARANTEES.md`) enumerates per-family causality guarantees; `tests/test_r3_point_in_time.py` adds 17 future-shock regression tests proving appending future bars cannot change past level values. This is exactly the class of bug that silently invalidates retail backtests.
- **Deliberate pessimism where ambiguity exists.** SL-first intrabar rule is a documented design decision, not an accident (`thesistester/engine/backtest.py` design notes; `docs/ASSUMPTIONS_AND_LIMITATIONS.md` §2). Simple triggers enter at next-bar open; signals emit when knowable, never backdated.
- **Honesty layer.** Validation outputs, walk-forward, and metrics all carry explicit "diagnostic, not proof of edge" framing; assumption docs enumerate precisely what is and isn't modeled (e.g., `allow_all` can inflate trade counts; bar-index WFA is not session-aware).
- **Regression-safe engineering culture, evidenced in git history.** New capabilities arrive opt-in with defaults preserving legacy behavior (R1 zero-cost default; Stage 2–6 level families default disabled; R8 versioned defaults with silent-drop validation). Legacy configs are normalized, never crash (`_normalize_levels_settings`).
- **Determinism.** Seeded bootstrap/permutation; deterministic fold splits, admission ordering, and settings hashes — results are reproducible and bundle-exportable.
- **Test depth.** ~1,516 tests vs ~13.5k package LOC (~1.8:1 LOC ratio) across unit, contract (OTF), DST, persistence-versioning, UI-helper, and regression themes; organized by phase (`test_phase*.py`) and milestone (`test_r3_*`, `test_stage*`, `test_otf_*`).
- **Documentation set.** 14 maintained docs: architecture with a `session_state` contract table, assumptions/limitations, metrics glossary, PIT guarantees, engineering roadmap (R1–R8 all marked implemented), OTF spec, agent onboarding guide. Documentation is updated in the same PRs as behavior (per `docs/AGENT_GUIDE.md` rules and observed history).

### 5.2 Weaknesses and risks

| # | Weakness | Classification | Impact |
|---|---|---|---|
| W1 | **No CI** — tests/lint never run automatically on PRs | Process gap | Regressions can merge silently; the project's own R3 doc notes merge readiness "requires the test suite to pass in CI/local verification" but no CI exists |
| W2 | **No packaging** (`pyproject.toml` absent), not pip-installable; Python version unpinned | Engineering hygiene | Harder to reuse engine headlessly or as a library; environment drift risk (verified: repo claims pandas ≥2.2; env runs pandas 3.0.5 — passing today, unpinned tomorrow) |
| W3 | **No lint/format/type-check config** (no ruff/black/mypy/pre-commit) | Engineering hygiene | Style drift accumulates with agent-driven contributions |
| W4 | **OHLC bar-level simulation only.** Intrabar order unknowable → SL-first; no look-inside-bar, tick, bid/ask, or volume-at-price fills | Design limitation (documented) | The biggest realism gap vs SOTA; can misprice fast stop/target sequences and limit-at-level fills |
| W5 | **Fixed bracket only.** No trailing stops, break-even moves, scale-outs, time-in-trade caps other than bar count, or order-type modeling | Design limitation | Many real day-trading exits cannot be expressed |
| W6 | **CSV-only ingestion.** No Databento/Polygon/NinjaTrader/Sierra exports beyond Quantower aliases; no tick/second/quote data | Design limitation | Data acquisition friction; realism upgrades blocked at the source |
| W7 | **No continuous-contract synthesis/back-adjustment** (metadata + gap diagnostics only, R7) | Documented scope decision | Long-horizon level stats across rolls require external pre-adjustment |
| W8 | **Validation science thin vs SOTA:** bootstrap CI + sign-flip permutation only; no Monte Carlo suite (reshuffle/skip/resample), no PBO/DSR, no noise tests, no vs-random benchmark | Feature gap | Weaker overfitting defense than SQX/Build Alpha/AmiBroker |
| W9 | **MAE/MFE captured but not analyzed.** Trades record `mae_points`/`mfe_points` (verified in schema and smoke run) but no distributions, edge-ratio, or excursion-based SL/TP calibration UI exists | Feature gap | Cheap, high-value analytics left on the table |
| W10 | **Walk-forward is bar-index based**, not calendar/session-aware; single-metric fold selection | Documented limitation | Fold boundaries can split sessions mid-day; WFA matrix views absent |
| W11 | **Streamlit-only workflow.** No CLI, no headless experiment runner, no notebooks; pages carry UI-helper logic tested indirectly | Design limitation | Batch research, automation, and AI-agent operation are awkward; session-state coupling limits reuse |
| W12 | **Performance profile:** `simulate_trades` uses `signals.iterrows()` plus a Python bar-by-bar exit walk (O(signals × bars_held)); grid = full re-simulation per cell | Scaling limitation | Fine for research-scale sweeps on months of 1-min data; will chafe on multi-year multi-setup sweeps (no vectorization/numba/parallelism) |
| W13 | **Only ES/NQ presets; no micros (MNQ/MES)** | Feature gap | Micro contracts are the natural sizing vehicle for the target user |
| W14 | **No LICENSE** | Legal/process | Blocks redistribution and corporate adoption |
| W15 | **Page numbering gap** (pages 1,2,5–12; no 3/4) | Cosmetic | Signals removed features to users; minor confusion |
| W16 | **No portfolio-level simulation:** one setup/one instrument/one risk config per run; no combined-equity multi-setup analysis | Feature gap | Cannot answer "what does trading 3 setups together look like?" |

### 5.3 Test-quality notes

- Strengths: phase/milestone organization; contract tests for OTF with deterministic fixtures (`tests/fixtures/otf_fixtures.py`); future-shock PIT tests; persistence versioning/reset/isolation tests (`tests/test_backtest_grid_defaults.py`); DST trigger-timeframe tests; narrow exception-guard tests for pages.
- Gaps: no coverage measurement configured (`pytest-cov` absent), no property-based testing (hypothesis), no golden-master/snapshot tests for engine outputs (numeric regressions are caught by targeted assertions only), Streamlit pages are tested via extracted helpers rather than UI-level tests (a reasonable, deliberate trade-off).

---

## 6. Position within its own roadmap

The repo's tracked milestones R1–R8 are all marked **implemented** (`docs/ENGINEERING_ROADMAP.md`): execution costs, session-aware exits, PIT audit, exposure model, walk-forward, institutional metrics, roll methodology, save-as-defaults. The OTF filter track (PRs 1–6) and level-upgrade track (Stages 1–7) are likewise complete. There is **no published forward roadmap** beyond these — the project is at a natural "what next?" decision point, which `docs/ENGINEERING_PROPOSAL.md` addresses.

---

## 7. Summary judgment

ThesisTester is a **correct, careful, and well-documented narrow tool**. What it implements, it implements to a high standard with verification discipline that many commercial tools lack (PIT guarantees, seeded determinism, pessimism-by-design). Its ceiling is set by four structural choices: OHLC-bar simulation, CSV-only data, fixed-bracket exits, and Streamlit-only workflow. None of these are defects; all are documented scope decisions. The opportunity — developed in the companion proposal — is that its weakest-vs-SOTA areas (Monte Carlo battery, MAE/MFE analytics, intrabar realism, calendar-aware WFA, headless automation) are precisely the areas where incremental, additive, regression-safe engineering yields outsized research value for its NQ/ES level-confluence niche.
