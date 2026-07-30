# Engineering Proposal — Closing the Gap to State of the Art, Regression-Safely

**Document type:** Proposal + engineering roadmap
**Date:** 2026-07-29
**Inputs:** `docs/SOTA_BACKTESTING_LANDSCAPE.md` (market research), `docs/THESISTESTER_ANALYSIS.md` (repository analysis with runtime verification).
**Status of this document:** Proposal. Nothing here is implemented. Each milestone is designed to land as its own PR series following the repo's established regression-safe conventions (`docs/AGENT_GUIDE.md`, R1–R8 precedent).

---

## 1. Executive summary

ThesisTester already out-executes most retail tools on **correctness discipline** (point-in-time guarantees, determinism, pessimistic ambiguity resolution, honesty documentation). It under-delivers on four capability axes where state-of-the-art tools concentrate their value for intraday NQ/ES researchers:

1. **Simulation realism** — OHLC-bar fills only, fixed bracket exits, no look-inside-bar.
2. **Validation science** — bootstrap + permutation, but no Monte Carlo suite, no PBO/deflated-Sharpe, no noise tests.
3. **Excursion analytics** — MAE/MFE is captured per trade but never analyzed; the SL/TP calibration loop SOTA tools build around it (RealTest, AmiBroker, Build Alpha Edge Ratio) is missing.
4. **Workflow automation** — Streamlit-only; no headless engine API, batch experiments, or CI.

The proposal: **do not chase the incumbents' breadth** (replay, live trading, strategy generation, order types zoo). Instead, deepen the niche ThesisTester already owns — *programmatic level-confluence statistics for intraday index futures* — through fourteen additive milestones (R9–R22), each opt-in, default-off, schema-versioned, and gated by the existing test suite plus new golden-master and future-shock tests. First milestone is engineering hygiene (CI + packaging + lint), because every subsequent milestone's regression safety depends on it. A dedicated performance milestone (R22) is included because the validation-battery milestones multiply re-simulation load on the engine's Python-level loop.

---

## 2. Strategic positioning

### 2.1 The niche to own

From the landscape research (`docs/SOTA_BACKTESTING_LANDSCAPE.md` §9): **no single product combines** programmatic volume-profile/level primitives, realistic intraday fills, MAE/MFE-driven SL/TP tooling, and modern overfitting batteries. StrategyQuant X + AmiBroker/RealTest lead on validation; Sierra/ATAS own replay realism; LEAN/Nautilus own execution modeling. ThesisTester's defensible position is the intersection: a levels engine + session-aware event studies + statistical validation, purpose-built for the ES/NQ confluence-setups research loop.

Benchmark classes follow the landscape's framing (`§1.1`): ThesisTester is a **quantitative setup-research tool**, so every roadmap milestone below is benchmarked against quant engines, robustness specialists, and the *analyzer subsystems* of retail platforms (Strategy Analyzer, WFO, Portfolio Maestro, Bar Magnifier) — never against chart/replay features, which are anti-scope (§2.2).

### 2.2 Explicit non-goals (anti-roadmap)

These are SOTA capabilities we recommend **never** building, with reasons:

| Non-goal | Who already owns it | Why not |
|---|---|---|
| Live trading / broker integration | NT, LEAN, MultiCharts | Regulatory, operational, and support burden; destroys the tool's research-only simplicity |
| DOM/L2-accurate market replay | ATAS, Bookmap, Jigsaw, Sierra | Requires MBO data infrastructure and a fundamentally different product; ThesisTester exports setups that users can manually verify in these tools |
| Genetic/LLM strategy generation | StrategyQuant X, Build Alpha, Composer | ThesisTester is hypothesis-driven (trader's thesis in), not a strategy factory; generation would import the overfitting problems its validation layer exists to fight |
| Order-type zoo (OCO/trailing/iceberg/MIT) | LEAN, NT, TradeStation | Fixed brackets cover the day-trading style being researched; only trailing/break-even (R13 below) is worth the complexity |
| Charting-platform breadth (scanners, DOM, 300 indicators) | Sierra, MotiveWave, TradingView | Not the research bottleneck |
| Cloud accounts / multi-user sync | QuantConnect | Local-first is a feature for this user |

### 2.3 Design principle

Every milestone follows the repo's proven pattern: **new capability arrives disabled or as a pure addition; defaults reproduce legacy behavior byte-for-byte; persisted state is schema-versioned; legacy configs are normalized, never rejected; point-in-time properties are proved by future-shock tests; docs land in the same PR.**

---

## 3. Capability comparison — ThesisTester vs SOTA taxonomy

Status: ✅ present · 🟡 partial · ❌ absent. Priority reflects leverage for the NQ/ES level-confluence niche (§2.1), not absolute importance.

| Domain | SOTA capability (taxonomy #) | ThesisTester today | Status | Priority |
|---|---|---|---|---|
| Data | Tick/second data (1, 3) | 1-min+ OHLC bars only | ❌ | High |
| Data | Bid/ask quote series (2) | None | ❌ | Medium |
| Data | Alternative bar types — range/volume/renko/delta (4) | Time bars only (1min–1D) | ❌ | Low |
| Data | Footprint / L2 / MBO history (5, 6) | None | ❌ | Low (non-goal) |
| Data | Continuous futures roll rules + adjustment (7, 8) | Roll metadata modes + gap diagnostics; **no adjustment synthesis** (R7) | 🟡 | Medium |
| Data | Multi-timeframe / multi-series (9) | Trigger timeframes, HTF indicators, OTF filter | ✅ | — |
| Data | RTH/ETH session templates & calendars (10) | ES/NQ presets, RTH/ETH tagging, DST-safe | ✅ | — |
| Data | Multi-vendor feed integration (11) | CSV only (+Quantower aliases) | 🟡 | High |
| Data | Point-in-time datasets (12) | PIT-audited level engine (R3) | ✅ | — |
| Realism | Look-inside-bar intrabar fills (13) | SL-first pessimism only | ❌ | **Highest** |
| Realism | Tick replay of logic (14) | None | ❌ | Low (non-goal) |
| Realism | Bid/ask-based fills (15) | None | ❌ | Medium |
| Realism | Queue-position modeling (16, 17) | None | ❌ | Low (non-goal) |
| Realism | Configurable slippage & commissions (18, 19) | Fixed-tick adverse slippage + per-side commission (R1) | ✅ | — |
| Realism | Latency modeling (20) | None | ❌ | Low (non-goal) |
| Realism | Order-type set (21) | Fixed SL/TP bracket + TIME/SESSION exits only | 🟡 | Medium |
| Realism | Margin/buying power (22) | None | ❌ | Low |
| Realism | Portfolio capital modeling (23) | None | ❌ | Medium |
| Realism | Look-ahead guards (24) | Next-bar-open entries, PIT audit, future-shock tests | ✅ | — |
| Realism | Volume-at-price fill validation (25) | Bar typical-price approximation for profiles | 🟡 | Medium |
| Strategy dev | Visual/no-code builder (26) | Setup Builder page (library, dataset-scoped) | ✅ | — |
| Strategy dev | DSL / SDK (27, 28) | Python functions (unpackaged) | 🟡 | Medium |
| Strategy dev | Indicator library (29, 30) | SMA/EMA/VWAP/POC + auction structure; user-column extension | 🟡 | Low |
| Strategy dev | Profile-native primitives (31) | VAH/VAL/POC day/week/month, rolling POC/VWAP, dVWAP, TPO SP, APOC | ✅ | — |
| Strategy dev | Multi-instrument signals (32) | Single instrument per run | ❌ | Low |
| Strategy dev | ML / AI integration (33, 34) | None | ❌ | Low (watch only) |
| Optimization | Grid optimization (35) | SL×TP grid with directional ranking | ✅ | — |
| Optimization | Genetic / PSO / CMA-ES (36, 37) | None | ❌ | Low |
| Optimization | Walk-forward optimization (38) | Deterministic bar-index WFA (R5) | 🟡 | High |
| Optimization | WFA matrix / cluster analysis (39) | None | ❌ | Medium |
| Optimization | Custom fitness (40) | Rank by any grid metric | 🟡 | Medium |
| Optimization | Distributed/parallel (41) | None (single-process loops) | ❌ | Medium |
| Validation | Monte Carlo suite (42) | Bootstrap CI + sign-flip permutation only | 🟡 | **Highest** |
| Validation | Monte Carlo retest — randomized params/slippage/data (43) | None | ❌ | High |
| Validation | Noise tests (44) | None | ❌ | Medium |
| Validation | Vs-random benchmark (45) | None | ❌ | Medium |
| Validation | SPP / parameter sensitivity (46) | Grid heatmap only; no perturbation curves | 🟡 | Medium |
| Validation | Multi-market/timeframe cross-validation (47) | None | ❌ | Low |
| Validation | PBO / Deflated Sharpe (48, 49) | Heuristic grid-overfit warning only | ❌ | High |
| Validation | Purged/embargoed CV (50) | None | ❌ | Low |
| Validation | Incubation / live-drift tracking (51) | None | ❌ | Low |
| Analytics | Core metrics suite (52) | Win rate through ulcer index, tails, streaks (R6) | ✅ | — |
| Analytics | R-multiple distributions (53) | Computed (R-centric engine) | ✅ | — |
| Analytics | **MAE/MFE analysis & edge ratio (54)** | Captured per trade, **never analyzed** | 🟡 | **Highest** |
| Analytics | Time-of-day / day-of-week / streaks (55) | RTH segment/hour/30-min buckets + streak metrics | ✅ | — |
| Analytics | Equity/drawdown curves + MC bands (56) | Equity curve yes; MC percentile bands no | 🟡 | High |
| Analytics | Trade-by-trade export (57) | CSV/JSON/parquet bundles (Phase 9) | ✅ | — |
| Analytics | Strategy correlation matrices (58) | None | ❌ | Medium |
| Analytics | Parameter-surface viz (59) | Plotly SL×TP heatmap | 🟡 | Low |
| Analytics | Shareable reports (60) | Markdown + JSON artifact; no HTML | 🟡 | Low |
| Workflow | Market replay (61, 62) | None | ❌ | Low (non-goal) |
| Workflow | Forward-test / live path (63, 64) | None | ❌ | Low (non-goal) |
| Workflow | Parameter-set versioning (65) | Settings hashes + saved runs + defaults versioning | ✅ | — |
| Workflow | Multi-setup portfolio runs (66) | None | ❌ | Medium |
| Workflow | Journaling integration (67) | None | ❌ | Low |
| Workflow | Headless/batch compute (68) | None — Streamlit only | ❌ | High |

### 3.1 What the comparison shows

- ThesisTester is **already at or near SOTA** for its niche in: session/level primitives, PIT discipline, deterministic versioning of research artifacts, R-centric trade metrics, time-of-day breakdowns.
- The **highest-leverage gaps** are exactly four: intrabar fill realism (taxonomy #13), Monte Carlo battery (#42/43/56), MAE/MFE analytics (#54), and headless batch workflow (#68) — plus the validation-science pair PBO/DSR (#48/49) and calendar-aware WFA (#38) close behind.
- The ❌ items marked Low are deliberate non-goals (§2.2) or poor effort/return trades for this niche.

---

## 4. Regression-safety framework (applies to every milestone)

The repo's conventions already encode most of this framework; R9 makes it enforceable in CI.

1. **Additive-only engine changes.** New parameters are keyword-only with defaults reproducing legacy behavior (precedent: R1 `commission_per_side=0.0`; R2 `flat_by_session_close=False`; Stage 2–6 level families default disabled). No existing positional signatures change.
2. **Golden-master tests before touching the engine.** Before any milestone that modifies `simulate_trades` or level/signal computation, capture current outputs on fixed synthetic fixtures into golden files (hashes or parquet snapshots) with a test asserting equality. Legacy mode must keep passing them after the change.
3. **Opt-in, default-off features.** Every new behavior ships behind an explicit flag that defaults to off; enabling it is the only way behavior changes (precedent: `_normalize_levels_settings` adds disabled defaults so old snapshots load safely).
4. **Schema-versioned persistence.** New persisted artifacts/namespaces get a version key; version drift is silently ignored with fallback (precedent: `defaults_schema_version`, OTF persistence versioning).
5. **Point-in-time proof for new computations.** Any new level, filter, or fold logic gets future-shock tests (append future bars → past values unchanged) following `tests/test_r3_point_in_time.py`.
6. **`st.session_state` contract stability.** Existing keys keep producer/consumer/schema; new keys are additive and recorded in `docs/ARCHITECTURE.md` in the same PR.
7. **Determinism.** All randomized procedures take `random_state` seeds; all folds/splits are deterministic; no wall-clock or dict-order dependence.
8. **Same-PR documentation.** `ASSUMPTIONS_AND_LIMITATIONS.md`, `METRICS_GLOSSARY.md`, `ARCHITECTURE.md`, and `ENGINEERING_ROADMAP.md` updated with the behavior change, per `docs/AGENT_GUIDE.md`.
9. **CI gate.** After R9: full pytest + lint on every PR; no merge on red.
10. **Honesty framing.** New statistical outputs ship with the same "diagnostic, not proof of edge" caveats as Phase 8/R5.

### 4.1 Golden-master operational spec

The golden-master mechanism (rule 2) is the load-bearing control for the only invasive engine milestones (R12/R13) and for any future engine refactor. It must be specified before any engine change:

1. **Minimal canonical fixture** under `tests/fixtures/golden/`:
   - `dataset_nq_1m_small.parquet` — one small synthetic NQ 1-minute dataset (a few RTH days), or a deterministic generator used by tests.
   - `legacy_bundle_hash.txt` — the research-bundle hash produced by current `main` in legacy mode.
   - `trades_legacy.parquet` — the canonical legacy-mode trade frame for that fixture.
2. **Recording and verification.** Golden tests run the legacy pipeline on the fixture and assert exact equality — bundle hash string-compare and trade-frame value equality (parquet/pandas). Legacy mode must keep passing after any engine change.
3. **Regeneration policy.** Golden outputs change only via a dedicated, reviewable PR that includes: the reason, a readable diff (CSV) of golden vs. new, and regression justification. CI blocks PRs that alter golden outputs unless an explicit `GOLDEN_REGEN` label and approval are present. Intentional new behavior always lands behind a new flag; the legacy golden is never silently regenerated.
4. **Brittleness control.** Keep golden scope minimal (small fixture) so legitimate improvements are not blocked; scope goldens to *legacy-mode* outputs only, per §7.

### 4.2 Per-milestone PR acceptance checklist

Mandatory for every PR touching engine or analytics:

- Unit tests for new functionality (single-run, deterministic).
- Golden-master tests preserved (legacy outputs unchanged).
- `random_state` seed parameter wherever randomness exists; deterministic otherwise.
- Documentation updates in the same PR: `ASSUMPTIONS_AND_LIMITATIONS.md` (caveats), `METRICS_GLOSSARY.md` (new stats), `ARCHITECTURE.md` (API / `st.session_state` contract changes if any).
- CI green across the matrix.
- Small surface area; purpose-limited commits; a short "regression safety" paragraph in the PR body stating how golden gating is preserved.

---

## 5. Roadmap — milestones R9 through R22

Milestones extend the existing R-series (`docs/ENGINEERING_ROADMAP.md` R1–R8). Order is the recommended implementation sequence; dependencies are noted. Each milestone lists: goal → SOTA benchmark → scope → regression-safety → acceptance.

### R9 — Engineering hygiene: CI, packaging, lint, coverage *(prerequisite for everything)*

- **Goal:** Make regression safety automatic instead of aspirational.
- **Benchmark:** N/A — internal. (Addresses analysis weaknesses W1–W3, W14.)
- **Scope:**
  - `pyproject.toml` (setuptools or hatchling): package metadata, `thesistester` importable after `pip install -e .`, Python `>=3.10`, dependency ranges mirroring `requirements.txt` (which stays for the app), and a `dev` extras group (`pytest`, `pytest-cov`, `ruff`).
  - GitHub Actions `.github/workflows/ci.yml`: matrix `pytest -q --cov=thesistester` on Python 3.10/3.11/3.12; `ruff check` + `ruff format --check`; coverage reported (informational threshold, e.g. warn below current level — monitor, don't block initially).
  - Minimal `ruff` config (line length consistent with current style); one-time `ruff format` pass isolated in its own commit.
  - Add a LICENSE file (owner decision: MIT suggested for adoption).
  - `tests/fixtures/golden/README.md` describing the golden-fixture format and regeneration policy from §4.1 (spec only — golden *data* is added in a follow-up PR before the first engine-touching milestone, not in R9 itself).
- **Regression-safety:** No runtime code changes except mechanical formatting; golden behavior proven by the suite itself (1516 tests).
- **Acceptance:** CI green on `main`; `pip install -e .` works in a fresh venv and `python -c "import thesistester"` succeeds; coverage report visible in CI; `tests/fixtures/golden/README.md` present. Suggested PR title: `R9: packaging + CI + LICENSE (regression-safe)`. Concrete `pyproject.toml` / `ci.yml` templates and a copy-ready implementation prompt live in the R9 PR description, not in this document, so they stay current with the code they scaffold.

### R10 — MAE/MFE excursion analytics & SL/TP calibration *(highest research value per effort)*

- **Goal:** Turn the already-captured `mae_points`/`mfe_points` into the calibration tooling RealTest/AmiBroker/Build Alpha users rely on.
- **Benchmark:** RealTest MAE/MFE distributions & trade plots; AmiBroker Pro MAE/MFE stats; Build Alpha **Edge Ratio** (edge magnitude + decay).
- **Scope:** New pure module `thesistester/analytics/excursions.py`: MAE/MFE distributions by direction/trigger/setup/time-bucket; excursion heatmap (MAE×MFE quadrant analysis); "give-back" curve — for each candidate stop distance s and target distance t, empirical hit probabilities derived from excursions (with explicit caveat that bar-level excursions bound but do not order intrabar events); Edge-Ratio-style summary (mean favorable excursion in R vs adverse, and its decay across bars held). Validation page section + report/export fields.
- **Regression-safety:** Pure post-trade analytics; reads existing trade columns only; no engine changes. Deterministic; empty-trade safe like `metrics.py`.
- **Acceptance:** Golden tests on fixed trade fixtures; glossary entries in `METRICS_GLOSSARY.md`; UI section hidden when no trades.

### R11 — Monte Carlo simulation suite

- **Goal:** The SOTA baseline robustness battery on realized trade sequences.
- **Benchmark:** AmiBroker Monte Carlo (CDF, straw-broom, MC-as-objective), NinjaTrader/TradeStation MC, SQX Monte Carlo trade manipulation (9+ sim types).
- **Scope:** New `thesistester/analytics/monte_carlo.py` (seeded): trade **reshuffle** (order permutation → drawdown distribution), trade **skip** (randomly drop x% → robustness to missed fills), block **resample** (stationary bootstrap preserving streak structure — answers the serial-dependence caveat already documented in `validation.py`); outputs: percentile bands for final R / max drawdown R / longest loss streak, probability of drawdown > X R, equity-curve fan chart data. Validation page section + export.
- **Regression-safety:** New additive module; consumes `r_multiple` sequences; seeded like existing bootstrap; no changes to `validation.py` outputs (new keys alongside, never inside, existing result dicts consumed downstream).
- **Acceptance:** Deterministic outputs under fixed seed verified by golden tests; block-resample preserves streak statistics better than iid reshuffle (asserted on a streaked fixture); docs caveats added.

### R12 — Look-inside-bar intrabar fill refinement

- **Goal:** Replace single-rule SL-first pessimism with a *configurable* intrabar resolution model — the single biggest realism gap vs SOTA.
- **Benchmark:** TradingView **Bar Magnifier** (minimum viable: refine with lower timeframe), TradeStation **Look-Inside-Bar**, NinjaTrader **High fill resolution** (sub-series down to 1 tick for fills only).
- **Scope:** `simulate_trades(..., intrabar_model: str = "sl_first")` — new keyword-only parameter. Models:
  1. `"sl_first"` (default; legacy behavior, golden-tested, byte-identical to current outputs).
  2. `"path_open_proximity"` — deterministic heuristic reconstructing likely intrabar path from OHLC relationship (NT-style 3-virtual-bar split).
  3. `"subtimeframe"` — when the canonical data is finer than the decision timeframe, walk sub-bars to order SL/TP hits (uses existing resample machinery); most defensible with real data.
  **Contracts:** both non-legacy models are fully deterministic by design — determinism is a feature, so no `random_state` is required for them; the parameter is reserved (and becomes mandatory) only if a *probabilistic* intrabar path model is ever introduced later. Exit reasons gain a suffix (e.g. `SL_intrabar_path`, `TP_subtimeframe`) so results remain distinguishable. Trade schema is additive-only: new columns for `intrabar_model`, plus an `intrabar_diagnostic` payload — count/percent of same-bar both-hit events, ambiguous-resolution count, bars affected — which is also surfaced in the exported research artifact. Grid search exposes the model choice so users can measure result sensitivity to intrabar assumptions (a robustness signal in itself).
- **Regression-safety:** Default keeps legacy behavior byte-identical (§4.1 golden-masters gate this); new models additive; trade schema additive columns only; session_state keys unchanged.
- **Acceptance:** Golden-master equality for default; per-model unit tests with hand-computed OHLC fixtures covering both-hit same-bar orderings; PIT future-shock tests (appending future bars must not change past outputs under any model); diagnostic counts verified on fixtures with known both-hit bars; `ASSUMPTIONS_AND_LIMITATIONS.md` updated (SL-first no longer the only modeled resolution; ambiguity caveats restated per model).

### R13 — Exit flexibility: break-even move and trailing stop (opt-in)

- **Goal:** Express the two exit adjustments day-traders actually use, without opening the full order-type zoo.
- **Benchmark:** Common subset of NT/TradeStation bracket management (breakeven-after-R, trail-after-R in tick steps).
- **Scope:** `simulate_trades(..., breakeven_after_r: float | None = None, trailing_after_r: float | None = None, trailing_distance_ticks: float | None = None)`; new exit reasons `BE` and `TRAIL`; MAE/MFE semantics unchanged; grid optionally sweeps the two new parameters (cartesian with SL/TP, capped to keep cell counts sane — reuse the existing grid-overfit heuristics as a guardrail).
- **Regression-safety:** Defaults `None` → legacy path untouched (golden-gated); additive schema columns.
- **Acceptance:** Hand-computed fixtures for BE/TRAIL sequences; interaction tests with R12 intrabar models; grid-overfit warning thresholds re-validated.

### R14 — Calendar/session-aware walk-forward + WFA matrix

- **Goal:** Fix the documented R5 limitation ("bar-index windows, not calendar/session-aware") and add the matrix view.
- **Benchmark:** TradeStation WFO (rolling/anchored, cluster analysis), SQX Walk-Forward Matrix, AmiBroker sliced IS/OOS equity.
- **Scope:** Fold boundaries on session counts (e.g. train 60 sessions / test 20 sessions) instead of bar indices; anchored and rolling modes; per-fold IS→OOS degradation ratio; WFA matrix view (multiple train/test window combinations → stability heatmap); stitched OOS equity curve across folds. Existing bar-index mode retained as `fold_mode="bars"` default for one release, then reconsider `="sessions"` default only behind an explicit migration note.
- **Regression-safety:** New `fold_mode` keyword defaults to legacy `"bars"`; legacy fold outputs golden-gated; new fold logic gets future-shock + fold-boundary PIT tests (no fold may see future data, incl. fold-local OTF history handling already present).
- **Acceptance:** Session folds never split an RTH session mid-day (asserted on holiday-shortened fixtures); matrix heatmap renders from deterministic fixtures; R5 docs updated.

### R15 — Overfitting-detection battery: PBO, Deflated Sharpe, vs-random

- **Goal:** Upgrade the heuristic grid-overfit warning to the quantitative multiple-testing corrections SOTA tools mainstreamed.
- **Benchmark:** PBO via CSCV and DSR (Bailey/López de Prado; implemented accessibly in VectorBT Pro's purged combinatorial CV); Build Alpha **Vs Random**.
- **Scope:** `thesistester/analytics/overfitting.py`: CSCV-based **PBO estimate** over grid-search trade sequences (configurable number of partitions, deterministic assignment); **Deflated/Probabilistic Sharpe** on the selected configuration given number of effective trials; **vs-random benchmark** — distribution of expectancy from N seeded random entry signals with identical exit/cost/exposure settings (reuses `simulate_trades`, proving engine composability). Validation page extends the existing heuristic panel rather than replacing it.
- **Regression-safety:** New additive module; existing `grid_overfit_diagnostics` untouched; seeded; heavy computations opt-in via UI toggles with explicit cost warnings.
- **Acceptance:** PBO implementation reproduces published toy examples (test fixtures from the Bailey/López de Prado reference cases); vs-random on a degenerate no-edge fixture yields p ≈ uniform behavior; honesty caveats in UI + docs.

### R16 — Noise test (price-series perturbation robustness)

- **Goal:** Build Alpha's signature **Noise Test** for the confluence niche: is the setup robust to small perturbations of the very bars that define its levels and triggers?
- **Benchmark:** Build Alpha Noise Test (perturb O/H/L/C by % of ATR → 1,000 synthetic series → re-trade; optional noise-adjusted optimization).
- **Scope:** `thesistester/analytics/noise.py`: seeded OHLC perturbation (proportional to per-bar range or rolling ATR, high/low consistency enforced: high ≥ max(open, close, perturbed), etc.); re-run the *entire* levels → confluence → signals → backtest pipeline per replica (this is the expensive part and the reason R19 should land first for acceptable UX); report distribution of expectancy/PF across replicas and the fraction of original trades that persist.
- **Regression-safety:** Read-only over a copied DataFrame; the canonical pipeline functions must accept injected data without side effects (they already do — pure functions); deterministic seeds.
- **Acceptance:** Perturbed OHLC invariants hold in all replicas (property-style loop assertions); a deliberately fragile fixture (single-bar trigger) shows visibly degraded persistence, demonstrating the test detects fragility; runtime budget documented.

### R17 — Data ingestion expansion: vendor formats + tick/quote capture

- **Goal:** Unblock realism upgrades at the source and cut data-acquisition friction.
- **Benchmark:** Databento (CME tick + continuous symbology), NinjaTrader/Sierra/Quantower export formats; QC futures data conventions (roll mapping/normalization) for guidance only.
- **Scope:** Extend `thesistester/data/loader.py` with format profiles: NinjaTrader export, Sierra Intraday CSV export, Databento CSV (trades; optional `bid_price`/`ask_price` columns preserved but unused by the bar engine); **capture-only** support for tick/second CSVs (stored resampled to 1-min via existing `resample.py`, raw preserved in the local store for future engines); MNQ/MES instrument presets added to `config.py` (trivial, high user value for sizing); loader profiles are additive aliases, current CSV contract untouched.
- **Regression-safety:** Existing loader tests and alias behavior golden-gated; new profiles keyed by explicit user selection, never auto-detection that could reinterpret current files; roll metadata modes (R7) unchanged.
- **Acceptance:** Round-trip tests per vendor fixture (small synthetic files in each format); current sample CSV produces byte-identical canonical output; new presets validated against CME contract specs.

### R18 — Headless research API + batch experiment runner

- **Goal:** Decouple the engine from Streamlit so research can be automated, parallelized, and operated by AI agents — the 2025–2026 SOTA workflow trend (VectorBT PRO's agent-friendly APIs, RealTest + Claude Code loop, leakage-aware agent architectures).
- **Benchmark:** VectorBT/VectorBT PRO scripting UX; QuantRocket Moonshot batch parameter scans; SQX cross-check funnels (as a sequencing concept).
- **Scope:** `thesistester/api.py` — a thin, typed, Streamlit-free facade: `load_dataset → compute_levels → build_setup → generate_signals → run_backtest → run_grid → run_validation` returning plain DataFrames/dicts (today's pages already call mostly-pure functions; the facade formalizes and documents the composition). `thesistester/cli.py` (`python -m thesistester run experiment.yaml`): batch experiment definitions (dataset, level config, setup, SL/TP grid, validation battery) writing research bundles per run; `concurrent.futures` parallelism across independent runs (single-run internals stay single-threaded → deterministic); results index CSV across runs.
- **Regression-safety:** Zero changes to engine internals; pages keep working off `session_state` (facade is an additional consumer of the same pure functions); CLI is a new entry point, app untouched; depends on R9 packaging for sane distribution.
- **Acceptance:** CLI reproduces a UI-equivalent run bit-for-bit on a fixture (compared via research-bundle hashes); parallel runs produce identical results to serial; agent-operability documented in `docs/AGENT_GUIDE.md` (typed handoffs, PIT guarantees restated for agent consumers per the landscape's leakage-aware consensus).

### R19 — Parameter sensitivity profiling (SPP-lite)

- **Goal:** StrategyQuant's System-Parameter-Permutation idea, scoped: how flat is the edge around the chosen configuration?
- **Benchmark:** SQX SPP / Optimization Profile; TradeStation WFA sensitivity graphs.
- **Scope:** For a selected grid cell, perturb each numeric parameter one-at-a-time (±x% in deterministic steps) *holding others fixed*, re-simulate, and plot expectancy/PF curves per parameter; a parameter is "fragile" if expectancy sign flips within the perturbation window; summary panel on the Validation page. Reuses R18's batch machinery for runtime.
- **Regression-safety:** Pure additive analytics; seeded; no engine changes.
- **Acceptance:** A cliff-edge fixture (edge exists only at exactly one SL value) is flagged fragile; a plateau fixture is not; docs interpret vs. the R11/R15 batteries (different questions: local sensitivity vs sampling uncertainty vs multiple-testing).

### R20 — Trade-review visualization ("replay-lite")

- **Goal:** The 20% of replay value that fits a bar-data tool: per-trade chart inspection, not DOM replay.
- **Benchmark:** RealTest trade plots; NinjaTrader trade markers on chart; ATAS/Sierra replay explicitly cited as the *manual-mechanics verification* complement, not a target to clone.
- **Scope:** Backtest page trade table → click a trade → candlestick window (entry ± N bars) with entry/SL/TP lines, actual exit marker, MAE/MFE excursion shading, zone/level overlay from existing `thesistester/visualization/` payload-windowing machinery. Batch mode: PNG/ export of worst-N losers for review folders.
- **Regression-safety:** Visualization-only; reads existing trade + levels frames; chart windowing (Phase-3 chart rollout) reused.
- **Acceptance:** Windowed payload size bounded (existing chart-performance constraints); golden HTML/figure-structure smoke tests; no new engine surface.

### R21 — Multi-setup portfolio layer

- **Goal:** Answer "what do three setups traded together look like?" — combined equity, correlation, and capital-aware exposure.
- **Benchmark:** RealTest multi-strategy portfolio stats + correlation matrices; TradeStation Portfolio Maestro; SQX Portfolio Master.
- **Scope:** `thesistester/analytics/portfolio.py`: merge per-setup trade frames (same instrument, shared bar index) with a portfolio-level exposure policy (max concurrent positions, per-direction caps — reusing R4's admission machinery at the portfolio level); combined equity in R and currency; setup-vs-setup return/drawdown correlation matrix; per-setup marginal contribution. Export as a portfolio research bundle.
- **Regression-safety:** Operates on outputs of independent per-setup runs (no change to single-run semantics); additive analytics.
- **Acceptance:** Portfolio of disjoint setups equals sum of parts under `allow_all`-equivalent portfolio policy; overlapping fixtures match hand-computed admission; correlation matrix matches pandas reference on fixtures.

### R22 — `simulate_trades` performance baseline and scaling path

- **Goal:** Treat the engine's Python-level loop as a first-class engineering concern *before* the validation-battery milestones multiply its load. `simulate_trades` iterates signals (`iterrows`) and walks exits bar-by-bar in Python — O(signals × bars_held) — and R11 (Monte Carlo), R15 (PBO/vs-random), R16 (noise replicas), and R19 (sensitivity perturbations) each re-run it many times, while grid search already re-simulates per cell. This is the roadmap's primary scale bottleneck (analysis W12).
- **Benchmark:** N/A — internal. Informed by the SOTA split (vectorized engines for parameter-space exploration vs. event-driven engines for realism), but the goal here is narrow: keep current semantics, remove the throughput ceiling.
- **Scope (baseline first, optimize second):**
  1. **Instrument, don't optimize yet.** Add timers and microbenchmarks under `tests/benchmarks/` measuring `simulate_trades` and `run_sl_tp_grid` wall-time on fixed fixtures (varying signal counts and bars-held); record results in a committed `docs/SIMULATE_PERF.md` baseline. Any later acceleration PR must state its measured improvement against this baseline.
  2. **Narrow the core surface.** Refactor `simulate_trades` internals so the per-trade decision logic is isolated behind a clear, small core API — such that any later optimization (vectorization, Numba on the hot exit-walk loop, or parallel grid cells via R18) touches only the core implementation, never the semantics. No behavior change; the §4.1 golden-masters must stay byte-identical through this refactor.
  3. **Acceleration (only if the baseline justifies it):** vectorized/Numba hot loop, or `multiprocessing`/joblib across independent grid cells and Monte Carlo replicas exposed through the R18 API. Acceleration that changes *any* numeric output is out of scope — parallel/vectorized paths must reproduce the serial golden outputs exactly.
- **Regression-safety:** Baseline instrumentation and the core-surface refactor are internal-only; golden-masters gate byte-identical behavior. Any accelerated execution path must produce outputs identical to the serial reference on the golden fixtures (asserted in CI).
- **Acceptance:** `docs/SIMULATE_PERF.md` exists with reproducible baseline timings; the refactored core passes the full suite and golden tests unchanged; if an accelerated path is added, a CI test asserts its outputs equal the serial path on fixtures, and `SIMULATE_PERF.md` records the measured speedup.

---

## 6. Sequencing and dependencies

```text
R9 (CI/packaging/lint + golden-spec)
 ├──► R10 (MAE/MFE analytics)          ── cheap, immediate value
 ├──► R11 (Monte Carlo suite)          ── independent, high value
 ├──► R12 (look-inside-bar)            ── gated by §4.1 golden-masters
 │     └──► R13 (BE/trailing exits)    ── engine surface after R12
 ├──► R14 (session-aware WFA)          ── independent of R12/R13
 ├──► R15 (PBO/DSR/vs-random)          ── benefits from R18 + R22 for runtime
 ├──► R16 (noise test)                 ── should follow R18 + R22 (full-pipeline replicas)
 ├──► R17 (data ingestion)             ── independent; enables future tick realism
 ├──► R22 (simulate_trades perf)       ── baseline early; refactor before R15/R16/R19 load
 └──► R18 (headless API + CLI)         ── after R9; accelerates R15/R16/R19; hosts R22 parallelism
        └──► R19 (SPP-lite)            ── uses R18 batch runs
R20 (trade-review viz)                 ── independent, anytime after R10
R21 (portfolio layer)                  ── last; composes per-setup outputs
```

**Recommended first wave (foundations + quick wins):** R9 → R10 → R11 → R18.
**Second wave (realism + validation depth):** R12 → R13 → R14 → R15.
**Third wave (scale + polish):** R16 → R17 → R19 → R20 → R21.
**Cross-cutting:** R22 runs alongside the waves — baseline instrumentation right after R9, the core-surface refactor before the R15/R16/R19 validation-battery load lands, and optional acceleration only where the baseline justifies it.

Rationale: R9 makes every later change verifiably regression-free; R10/R11 deliver SOTA-parity validation value at a fraction of engine-surgery risk; R18 multiplies the value of every subsequent analytics milestone by making them batch-runnable and agent-operable; R12/R13 are the only invasive engine changes and are deliberately scheduled after the safety net (golden-masters from R9, users calibrated by R10/R11) exists; R22 ensures the engine can actually carry the re-simulation load those batteries impose.

---

## 7. Risk register for the roadmap

| Risk | Milestones | Mitigation |
|---|---|---|
| Intrabar models create false confidence ("now it's realistic!") | R12, R13 | Every new model ships with exported ambiguity diagnostics (both-hit counts) and docs stating OHLC ordering remains unknowable; sub-bar model is the recommended one when data allows |
| Runtime blowup from full-pipeline replicas | R15, R16, R19 | R22 baseline + core refactor first; seeded subsampling, opt-in toggles, R18 parallelism, explicit cost warnings in UI |
| Statistical theater — batteries misread as proof | R11, R15, R16, R19 | Same honesty framing as Phase 8; glossary entries defining exactly what each number means; PBO/DSR assumptions stated (trade-sequence stationarity, trial-count estimation) |
| Golden-master brittleness blocks legitimate engine improvements | R9→R12/13, R22 | Golden files scoped to *legacy-mode* outputs on a minimal fixture; §4.1 documented regeneration procedure with `GOLDEN_REGEN` label + approval |
| Performance refactor drifts numeric outputs | R22 | Golden-masters must stay byte-identical through the refactor; accelerated paths asserted equal to the serial reference in CI |
| Scope creep toward non-goals (replay, live trading) | All | §2.2 anti-roadmap is the standing decision record; revisit only via an explicit proposal amendment |
| pandas/numpy major-version drift | R9 | CI matrix + conservative version caps in `pyproject.toml`; dependabot/renovate PRs gated by full suite |

---

## 8. What success looks like

After the first two waves, a ThesisTester research loop for an NQ opening-range confluence setup looks like: ingest vendor data (R17) → compute levels with proved PIT behavior (existing) → backtest with configurable intrabar resolution and break-even/trailing management (R12/R13) → calibrate SL/TP from excursion analytics instead of grid-fishing (R10) → validate with Monte Carlo bands, session-aware WFA matrix, PBO/DSR, and vs-random (R11/R14/R15) → reproduce the whole study headlessly from a versioned experiment file (R18) → export a bundle whose every number is deterministic, seeded, and documented.

That is a tool no incumbent offers for this niche, built entirely through additive, opt-in, golden-gated milestones — with the 1516-test suite green at every step.
