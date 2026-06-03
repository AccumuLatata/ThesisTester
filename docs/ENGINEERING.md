# ThesisTester — Engineering & Design Document

*Intraday confluence-setup backtesting & research app (Streamlit + Python)*

**Status:** Draft v0.1 · **Owner:** AccumuLatata · **Last updated:** 2026-06-03

---

## 1. Purpose & Scope

ThesisTester is a research tool to **empirically validate intraday trading setups** built
on the *confluence* of one or more price reference levels (SMAs, VWAPs, profile levels,
prior session highs/lows, etc.).

It answers three research questions:

1. **Edge** — Does reacting to a price level (or a *cluster* of 1–5 levels) produce a
   statistically significant, positive expectancy?
2. **Timing** — *When* during the session does the setup work best / worst
   (time-of-day breakdown)?
3. **Risk management** — Which **Stop-Loss (SL) / Take-Profit (TP)** combination
   maximises risk-adjusted return for that setup?

**Non-goals (v1):** live trading, order routing, options, multi-leg strategies,
portfolio optimisation. This is a *research* tool, not an execution engine.

> ⚠️ **Methodological warning (read first).** Testing many confluence × SL × TP × time
> combinations is a multiple-comparisons problem. Without correction you *will* find
> spurious "edges". Statistical validation (§9) is a first-class feature, not an afterthought.

---

## 2. Glossary of Reference Levels (Confluences)

Every "confluence" is just a **price reference** computed per bar/session. The engine treats
them uniformly: each produces a price (or a band) at a given timestamp.

### 2.1 Dynamic / indicator levels (recomputed each bar)
| Code | Definition | Params |
|---|---|---|
| `SMA` | Simple Moving Average | length(s), source |
| `EMA` | Exponential Moving Average | length(s), source |
| `VWAP_rolling` | Volume-Weighted Avg Price over a **rolling window** | window ∈ {15m, 30m, 1h, 4h} |
| `POC_rolling` | Point of Control (most-traded price) of a **rolling** volume profile | window ∈ {30m, 1h, 4h} |

### 2.2 Session / structural levels (fixed once formed)
| Code | Definition |
|---|---|
| `ONH` / `ONL` | Overnight session High / Low |
| `OR_High` / `OR_Low` | Opening-Range High / Low (configurable OR length, e.g. 5/15/30m) |
| `RTH_Open` | Regular-Trading-Hours session open |
| `prevSettlement` | Prior session settlement price |
| `dOpen` / `wOpen` / `mOpen` | **Current** Day / Week / Month open |
| `pdOpen` / `pwOpen` / `pmOpen` | **Prior** Day / Week / Month open |
| `pdHigh` / `pdLow` | Prior Day High / Low |
| `pwHigh` / `pwLow` | Prior Week High / Low |
| `pmHigh` / `pmLow` | Prior Month High / Low |
| `pdEQ` / `pwEQ` / `pmEQ` | Prior Day / Week / Month **Equilibrium** (50% midpoint = (H+L)/2) |

### 2.3 Volume-profile levels (per prior session, from market profile)
| Code | Definition |
|---|---|
| `pdVAH` / `pdVAL` / `pdPOC` | Prior **Day** Value Area High / Low / Point of Control |
| `pwVAH` / `pwVAL` / `pwPOC` | Prior **Week** Value Area High / Low / Point of Control |
| `pmVAH` / `pmVAL` / `pmPOC` | Prior **Month** Value Area High / Low / Point of Control |

> Value Area = price range containing **70%** of traded volume around the POC (configurable).

### 2.4 "Naked" levels
A level is **naked** (a.k.a. *virgin/untested*) if price has **not traded back to it**
since it was formed. Toggling *"naked only"* filters signals to first-touch interactions.
This is a documented edge hypothesis (untested levels act as stronger magnets/reactors) —
we will *test* it, not assume it.

---

## 3. Core Concepts

### 3.1 Setup = Trigger × Confluence × Risk
A **setup** is defined by:

- **Confluence set** `C = {level_1, … , level_k}`, `1 ≤ k ≤ 5` (hard cap 5, default 3).
- **Cluster tolerance** `τ` — levels must sit within `τ` of each other (in ticks, points,
  % or ATR-multiples) to count as a confluence *zone*.
- **Interaction trigger** — how price must engage the zone:
  - `touch` (price tags the zone)
  - `reject` (touch + close back out → mean-reversion / fade)
  - `break` (close through → continuation/breakout)
  - `reclaim` (break then close back → trap)
- **Direction** — long / short / both.
- **Risk model** — SL and TP definitions (§7).
- **Session filter** — time-of-day window (§8) and date range.

### 3.2 What we measure (per trade & aggregate)
Entry, exit, MAE/MFE, R-multiple, P&L, holding time, time-of-day bucket, which level(s)
triggered, naked flag, and the active SL/TP grid cell.

---

## 4. System Architecture

```
                ┌──────────────────────────────────────────────┐
                │                Streamlit UI                   │
                │  Config • Run • Results • Stats • Export       │
                └───────────────┬──────────────────────────────┘
                                │ calls (pure functions, cached)
        ┌───────────────────────┼───────────────────────────────┐
        ▼                       ▼                                ▼
┌───────────────┐      ┌──────────────────┐            ┌──────────────────┐
│  Data Layer   │      │  Level Engine     │            │  Backtest Engine │
│  ingest+clean │ ───► │  computes all     │ ─levels──► │  signals→trades  │
│  resample     │      │  reference levels │            │  SL/TP grid       │
└───────────────┘      └──────────────────┘            └────────┬─────────┘
                                                                ▼
                                                      ┌──────────────────┐
                                                      │  Analytics/Stats │
                                                      │  ToD, SL/TP grid │
                                                      │  significance     │
                                                      └──────────────────┘
```

**Design principles**
- **Pure, deterministic functions** for compute (easy to test, cache with `st.cache_data`).
- **Vectorised** with pandas/numpy; the backtest loop is event-based but level computation is vectorised.
- **Stateless UI** — config in, results out. All heavy state cached and keyed by config hash.
- **Reproducibility** — every run produces a config JSON + result manifest (seed, data hash).

---

## 5. Data Layer

### 5.1 Requirements
Intraday OHLCV with **volume** (needed for VWAP & volume profile) and a session model that
distinguishes **overnight (ETH)** vs **RTH**. Designed for **futures** (ES/NQ/CL etc.) but
works for any instrument with sessions.

| Need | Why |
|---|---|
| 1-minute (or finer) OHLCV+Volume | base for resampling, VWAP, profiles |
| Exchange timezone & session calendar | RTH/ETH split, ONH/ONL, settlement |
| Tick size / point value | risk in ticks, R-multiples, P&L |

### 5.2 Sources (pluggable adapters)
- **CSV / Parquet upload** (MVP — works offline, fully reproducible).
- Optional API adapters later: Databento, Polygon.io, IQFeed (futures intraday + volume).
- **Free intraday with true volume profile is limited** — plan around user-supplied data first.

### 5.3 Pipeline
`load → validate (gaps, dupes, monotonic ts) → localise tz → tag session (ETH/RTH) →
resample to needed frames → cache`.

---

## 6. Level Engine

One module per level family, each exposing `compute(df, params) -> Series/DataFrame` that
returns the level price aligned to the base timeline.

- `indicators.py` — SMA, EMA, rolling VWAP, rolling POC.
- `sessions.py` — d/w/m opens, prior O/H/L, EQ, ON H/L, OR, RTH_Open, settlement.
- `profile.py` — market/volume profile → POC, VAH, VAL (day/week/month).
- `naked.py` — given a level series + price path, flag whether each level is still untested.

**Volume profile method:** bin traded volume by price (tick-bucketed), POC = max-volume bin,
Value Area grown outward from POC until 70% volume captured (TPO-style optional later).

---

## 7. Backtest Engine

### 7.1 Signal generation
1. Build the active level series for each selected confluence.
2. At each bar, find **zones** where ≥`k` selected levels cluster within `τ`.
3. Emit a candidate signal when the configured **trigger** fires against a zone.
4. Apply filters: direction, naked-only, session/time window, max trades per zone.

### 7.2 Trade simulation (bar-by-bar, conservative fills)
- **Entry:** at trigger bar close (or next-bar open — configurable; default next-bar open to avoid look-ahead).
- **SL / TP definitions** (each independently selectable):
  - Fixed: ticks / points / %.
  - **ATR-multiple** (volatility-normalised) — recommended default.
  - Structural: opposite side of zone, swing, OR boundary.
- **Intrabar priority rule:** if both SL & TP could fill in one bar, assume **SL first**
  (pessimistic) unless intrabar/finer data available. *Document this assumption loudly.*
- Record MAE/MFE, R-multiple, bars held, exit reason.

### 7.3 SL/TP grid search
Cartesian sweep over SL ∈ {…} × TP ∈ {…} (and optional R:R), producing a **heatmap**
of expectancy / Sharpe / win-rate / profit factor per cell. Vectorise where possible;
cache by (signals-hash × grid).

---

## 8. Time-of-Day Analysis

- Bucket each trade by entry time into configurable bins (e.g. 30-min, or named sessions:
  *Asia, London, NY-open, NY-lunch, NY-PM, close*).
- Per bucket metrics: trade count, win-rate, avg R, expectancy, profit factor, equity slice.
- Visuals: bar chart of expectancy-by-bucket + heatmap **(time-of-day × SL/TP)**.
- Surface sample size per bucket; flag buckets with `n < n_min` as **not interpretable**.

---

## 9. Statistical Validation (first-class)

Because the search space is large, we guard against overfitting:

| Technique | What it controls |
|---|---|
| **Out-of-sample / walk-forward split** | in-sample optimisation vs OOS confirmation |
| **Sample-size gating** | hide/flag results with `n < n_min` (default 30) |
| **Bootstrap / Monte-Carlo on trade order** | distribution of expectancy, not a point estimate |
| **Multiple-testing correction** (Benjamini–Hochberg FDR / Bonferroni) | inflated significance from grid search |
| **Baseline / null comparison** | vs random-entry & buy-and-hold-intraday benchmark |
| **Deflated Sharpe Ratio** (Bailey & López de Prado) | Sharpe inflated by number of trials |

> **References:** Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*; López de Prado
> (2018), *Advances in Financial Machine Learning* (backtest overfitting, PBO);
> Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns* (t-stat haircuts for
> multiple testing); Benjamini & Hochberg (1995) FDR control. These motivate the safeguards above.

Every results page shows: sample size, confidence interval on expectancy, and an
**overfitting caveat** when many combinations were screened.

---

## 10. Streamlit UI

Multi-page app (`st.navigation` / `pages/`):

1. **📥 Data** — upload/select instrument, tz, session model, validate & preview.
2. **🧩 Setup Builder** — pick 1–5 confluences, tolerance, trigger, direction, naked toggle.
3. **🛡️ Risk** — SL/TP definitions and grid ranges.
4. **▶️ Run** — execute backtest (cached); progress + config summary.
5. **📊 Results** — equity curve, trade table, KPIs, MAE/MFE, drawdown.
6. **🕐 Time-of-Day** — expectancy by bucket + heatmaps.
7. **🔥 SL/TP Grid** — heatmap explorer.
8. **🧪 Validation** — OOS, bootstrap, multiple-testing-adjusted significance.
9. **💾 Export** — config JSON, trades CSV, summary PDF/markdown.

UX rules: every run is reproducible (config hash shown); all heavy compute behind
`st.cache_data`; never block UI without a spinner + sample-size warnings.

---

## 11. Tech Stack & Repo Structure

**Stack:** Python 3.11+, Streamlit, pandas, numpy, plotly (charts), pandas-ta or custom
indicators, pyarrow (parquet), pytest. Optional: numba/polars for speed; `exchange_calendars` for sessions.

```
ThesisTester/
├── app.py                      # Streamlit entry
├── pages/                      # one file per UI page (§10)
├── thesistester/
│   ├── data/                   # loaders, validation, sessions, resample
│   ├── levels/                 # indicators.py, sessions.py, profile.py, naked.py
│   ├── engine/                 # signals.py, backtest.py, sltp_grid.py
│   ├── analytics/              # metrics.py, timeofday.py, stats.py
│   └── config.py               # typed config (pydantic/dataclasses)
├── tests/                      # pytest unit + golden-trade tests
├── sample_data/                # tiny fixture for demo & CI
├── requirements.txt
├── docs/ENGINEERING.md         # this file
└── README.md
```

---

## 12. Build Roadmap (incremental, demoable each phase)

| Phase | Deliverable | Outcome |
|---|---|---|
| **0** | Repo scaffold, requirements, sample data, CI (pytest) | App boots, data loads |
| **1** | Data layer + session tagging (RTH/ETH) + resampling | Validated bars on screen |
| **2** | Level engine: session levels (opens, prior O/H/L, EQ, ON, OR, settlement) | Levels plotted |
| **3** | Indicator levels (SMA/EMA/VWAP/rolling POC) + volume profile (VAH/VAL/POC) | Full level set |
| **4** | Confluence detection (k≤3) + naked logic + triggers | Signals on chart |
| **5** | Backtest engine + single SL/TP + KPIs + equity curve | First end-to-end edge test |
| **6** | SL/TP grid heatmap | Best risk model per setup |
| **7** | Time-of-day breakdown | When it works |
| **8** | Extend k to 5; statistical validation suite (§9) | Trustworthy results |
| **9** | Export/reporting + polish | Shareable research output |

Recommend shipping **Phases 0–5 as MVP**, then 6–9.

---

## 13. Key Assumptions & Decisions (to confirm)

1. **Primary instrument/asset class?** (drives session model — futures assumed: ES/NQ.)
2. **Data source** for MVP — CSV/Parquet upload? What timezone & bar size will you provide?
3. **Default cluster tolerance unit** — ticks, points, % or ATR? (ATR recommended.)
4. **Intrabar fill assumption** — SL-first pessimistic is the default; OK?
5. **Entry timing** — next-bar open (no look-ahead) default; OK?
6. **Value-area %** — 70% standard; configurable.

---

## 14. Risks & Limitations

- **Look-ahead bias** — strict next-bar fills + session boundaries enforced in code & tests.
- **Backtest overfitting** — the central risk; mitigated by §9, not eliminated.
- **Data quality** — gaps/half-days/DST; validation layer + exchange calendar.
- **Intrabar ambiguity** — 1-min bars can't resolve SL-vs-TP-first; document & optionally
  ingest finer data.
- **Survivorship/continuous-contract issues** for futures (roll method) — note in data layer.

---

*End of document — feedback welcome before we scaffold Phase 0.*
