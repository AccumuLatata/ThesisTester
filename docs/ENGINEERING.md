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
> Prior day/week/month profiles also support independent aggregation-tick multiples. The
> effective prior-profile bin size is `instrument_tick_size × aggregation_ticks`, and these
> controls affect only `pd*`, `pw*`, and `pm*` value-area/POC levels — not exchange tick
> size, rolling POC windows, or other downstream logic.

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
  - `3c` (three-candle level interaction + reversal + retracement entry)
- **Trigger timeframe** — candle-close trigger logic runs on the configured trigger
  timeframe (`base`, `1min`, `5min`, `15min`) for all supported triggers including `3c`.
  Default `base` preserves legacy behavior. Different trigger timeframes are treated as
  separate strategy hypotheses. For non-base triggers, emitted `bar_index` and `timestamp`
  remain aligned to the canonical/base bar at trigger close (or fill for `3c`), while
  `trigger_timestamp` captures trigger-candle completion/actionability.
  For `3c` with non-base trigger timeframe, arrival, inside/muted candles, SFP tagging,
  and reversal confirmation are evaluated on trigger-timeframe candles; retrace fill is
  evaluated on canonical/base bars after reversal trigger candle completion.
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

## Source Timezone Import Note

- Imported OHLCV data is canonicalized to the instrument exchange timezone before
  session tagging, level generation, signal generation, backtesting, and time analysis.
- For timezone-naive CSV timestamps, the Data page source timezone selector determines
  how timestamps are localized before conversion.
- For timezone-aware CSV timestamps, the embedded timestamp timezone is trusted and the
  selector is ignored.
- ES/NQ exchange timezone remains `America/New_York`.

---

## 6. Level Engine

One module per level family, each exposing `compute(df, params) -> Series/DataFrame` that
returns the level price aligned to the base timeline.

- `indicators.py` — SMA, EMA, rolling VWAP.
- `sessions.py` — d/w/m opens, prior O/H/L, EQ, ON H/L, OR, RTH_Open, settlement.
- `profile.py` — market/volume profile → rolling POC + prior POC/VAH/VAL (day/week/month).
- `naked.py` — given a level series + price path, flag whether each level is still untested.

**Volume profile method:** bin traded volume by price (tick-bucketed), POC = max-volume bin,
Value Area grown outward from POC until 70% volume captured (TPO-style optional later).
Current MVP allocates each bar's full volume to one price bin (typical price), until true
tick/volume-at-price data is available.

---

## 7. Backtest Engine

### 7.1 Signal generation
1. Build the active level series for each selected confluence.
2. At each bar, find **zones** where ≥`k` selected levels cluster within `τ`.
3. Emit a candidate signal when the configured **trigger** fires against a zone.
4. Apply filters: direction, naked-only, session/time window, max trades per zone.

#### 7.1.1 Trigger spec: `3c`

The `3c` trigger is a 3-candle level-interaction entry with 4 core rules and 8 named
variants.

**8 variants**

| Variant | Notes |
|---|---|
| `3c_long` | Standard long |
| `3c_short` | Standard short |
| `3c_long_muted` | Long with inside candle(s) between arrival and reversal |
| `3c_short_muted` | Short with inside candle(s) between arrival and reversal |
| `3c_sfp_long` | Long SFP reversal |
| `3c_sfp_short` | Short SFP reversal |
| `3c_sfp_long_muted` | Muted + SFP long |
| `3c_sfp_short_muted` | Muted + SFP short |

**4 rules — Long**

1. **Arrival candle** must touch or pass through the key level (`bar_low <= level_price`).
2. **Arrival candle** must close above the key level (`bar_close > level_price`).
3. **Reversal candle** must close above the arrival candle high (`reversal_close > arrival_high`).
4. **Entry candle** must retrace at least `entry_retrace_ticks` below the reversal close;
   once retraced, trigger market long.

**4 rules — Short** (mirror image)

1. Arrival candle must touch or pass through the key level (`bar_high >= level_price`).
2. Arrival candle must close below the key level (`bar_close < level_price`).
3. Reversal candle must close below the arrival candle low (`reversal_close < arrival_low`).
4. Entry candle must retrace at least `entry_retrace_ticks` above the reversal close;
   once retraced, trigger market short.

**Muted variant**

If the candle immediately after the arrival candle is an inside candle relative to the
arrival candle range (high ≤ arrival high and low ≥ arrival low), it is skipped.  All
consecutive inside candles are skipped.  The first candle that breaks the arrival range
and closes beyond the relevant extreme becomes the reversal candle.  The setup is tagged
as `is_muted = True` and the `inside_candle_count` field records how many were skipped.

**SFP variant**

- Long SFP: reversal candle low takes out the arrival candle low (`reversal_low < arrival_low`).
- Short SFP: reversal candle high takes out the arrival candle high (`reversal_high > arrival_high`).

**User-configurable parameters**

| Parameter | Meaning |
|---|---|
| `entry_retrace_ticks` | Ticks price must retrace after reversal close before entry triggers. Default `4`. |
| `max_entry_wait_bars_after_reversal` | Bars to wait for retracement. Default `5`. |

**`arrival_tolerance_ticks` — deprecated**

`arrival_tolerance_ticks` is **not user-configurable**.  Arrival must actually touch the
key level; a near miss does not qualify.  The parameter is still accepted in
`trigger_params` for backward compatibility with old saved configs, but its value is
always ignored — effective tolerance is forced to zero.

**Historical note (removed trigger: `confirm_3bar`)**

> `confirm_3bar` is not supported in the current app. The supported triggers are:
> `touch`, `reject`, `break`, `reclaim`, and `3c`.

**Historical parameters table (reference only)**

| Parameter | Meaning |
|---|---|
| `activation_retrace_ticks` | Number of ticks bar 3 must retrace against intended direction from bar 3 open before activation. |
| `entry_offset_ticks` | Entry offset in ticks from bar 3 open (separate from activation retrace). |
| `direction` | `long`, `short`, or `both`. |
| `entry_fill_model` | Default: bar-3 stop-limit-style model using both activation and entry price checks. |
| `max_wait_bars` | Default `1` for this pattern; retracement must occur during bar 3 only. |
| `allow_equal_close` | Optional boolean; default `false`. If `false`, reversal close must be strictly above/below arrival close. |

> Backward compatibility: legacy `retrace_entry_ticks` is mapped to `activation_retrace_ticks`.

**Historical setup flow (removed `confirm_3bar`, reference only)**

**Long setup**

- **Bar 1 — Arrival candle (level-specific):**

  ```text
  approach_from_above = bar1_open > level OR previous_close > level
  level_hit = bar1_low <= level + tol
  close_reclaimed = bar1_close > level
  ```

  From qualifying touched levels, the tested level is the **highest** touched level.

- **Bar 2 — Reversal candle / micro-structure shift:**

  ```text
  bar2_close > bar1_close
  ```

  If `allow_equal_close = true`:

  ```text
  bar2_close >= bar1_close
  ```

- **Bar 3 — Retracement and activation checks:**
  Long activation and entry:

  ```text
  activation_price = bar3_open - activation_retrace_ticks * tick_size
  entry_price      = bar3_open + entry_offset_ticks * tick_size
  ```

  Fill condition (OHLC proxy):

  ```text
  bar3_low <= activation_price
  AND
  bar3_high >= entry_price
  ```

  If both are not touched in bar 3, setup is `void`.

**Short setup**

- **Bar 1 — Arrival candle (level-specific):**

  ```text
  approach_from_below = bar1_open < level OR previous_close < level
  level_hit = bar1_high >= level - tol
  close_reclaimed = bar1_close < level
  ```

  From qualifying touched levels, the tested level is the **lowest** touched level.

- **Bar 2 — Reversal candle / micro-structure shift:**

  ```text
  bar2_close < bar1_close
  ```

  If `allow_equal_close = true`:

  ```text
  bar2_close <= bar1_close
  ```

- **Bar 3 — Retracement and activation checks:**
  Short activation and entry:

  ```text
  activation_price = bar3_open + activation_retrace_ticks * tick_size
  entry_price      = bar3_open - entry_offset_ticks * tick_size
  ```

  Fill condition (OHLC proxy):

  ```text
  bar3_high >= activation_price
  AND
  bar3_low <= entry_price
  ```

  If both are not touched in bar 3, setup is `void`.

**Implementation notes**

1. **Confluence is context, not tested price**
   - Arrival is evaluated against concrete `level_prices` in the zone.
2. **SFP reversal tagging**
   - Long `sfp_reversal`: `bar2_low < bar1_low` and reversal close valid.
   - Short `sfp_reversal`: `bar2_high > bar1_high` and reversal close valid.
3. **OHLC sequence ambiguity**
   - With bar data, activation and entry touch order inside bar 3 is unknown.
   - v1 marks setup `filled` when both are touched and logs `bar3_sequence_assumed_from_ohlc`.
   - True sequencing requires lower-timeframe/tick data.

### 7.2 Trade simulation (bar-by-bar, conservative fills)
- **Entry:** at trigger bar close (or next-bar open — configurable; default next-bar open to avoid look-ahead).
  Exception: `3c` filled signals use an entry-bar retracement trigger/price.
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
   - When `3c` is selected, expose:
     - Direction: long / short / both
     - Entry retrace ticks
     - Max entry wait bars after reversal
     - Note: arrival tolerance is not user-configurable (arrival must strictly touch key level)
3. **🛡️ Risk** — SL/TP definitions and grid ranges.
4. **▶️ Run** — execute backtest (cached); progress + config summary.
5. **📊 Results** — equity curve, trade table, KPIs, MAE/MFE, drawdown.
6. **🕐 Time-of-Day** — expectancy by bucket + heatmaps.
7. **🔥 SL/TP Grid** — heatmap explorer.
8. **🧪 Validation** — OOS, bootstrap, multiple-testing-adjusted significance.
9. **💾 Export** — config JSON, trades CSV, summary PDF/markdown.

UX rules: every run is reproducible (config hash shown); all heavy compute behind
`st.cache_data`; never block UI without a spinner + sample-size warnings.

- Streamlit widget/layout calls should use the current `width=` API (`"stretch"` /
  `"content"`) instead of deprecated `use_container_width`. This API requires
  **Streamlit ≥ 1.56** — the minimum version at which `width="stretch"` is
  consistently supported for `st.dataframe`, `st.plotly_chart`, and `st.button`.
  `requirements.txt` pins `streamlit>=1.56` accordingly.
- The Signals page keeps saved-setup and saved-signal-run metadata in `st.session_state`
  with local dirty/refresh handling so ordinary reruns avoid repeated filesystem scans.

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
| **4** | Confluence detection (k≤3) + naked logic + triggers (including `3c`) | Signals on chart |
| **5** | Backtest engine + single SL/TP + KPIs + equity curve + entry-bar retracement-trigger entries (`3c`) | First end-to-end edge test |
| **6** | SL/TP grid heatmap | Best risk model per setup |
| **7** | Time-of-day breakdown | When it works |
| **8** | Extend k to 5; statistical validation suite (§9) | Trustworthy results |
| **9** | Export/reporting + polish | Shareable research output |

Recommend shipping **Phases 0–5 as MVP**, then 6–9.

---

## Phase 4 Implementation Notes

- **Phase 4 signals are candidates only.** No trade simulation, SL/TP, exits, P&L,
  equity curves, MAE/MFE, or drawdown analysis are implemented in Phase 4. These begin
  in Phase 5.
- **Naked-level logic is an MVP approximation.** Formation is detected when a level
  column value first becomes non-NaN or changes from the prior bar. Testing can only
  occur on subsequent bars (the formation bar itself is never counted as tested). Later
  versions may require formation timestamps specific to each level family (e.g.
  `OR_High` is only finalized after the opening-range window closes).
- **Candidate signals** are stored in `st.session_state["signals"]` via the Signals
  page (`pages/6_Signals.py`) for consumption by Phase 5 backtesting.
- **DST-safe non-base trigger bucketing:** when trigger timeframe is non-base and
  timestamps are timezone-aware, trigger-bar flooring is performed in UTC and then
  converted back to the original timezone. This avoids ambiguous local-time flooring
  failures around DST boundaries while preserving canonical/base timestamp semantics.
- **`3c` trigger implementation:** uses `entry_retrace_ticks` (entry retrace after reversal
  close) and `max_entry_wait_bars_after_reversal` as independently configurable parameters.
  `arrival_tolerance_ticks` is deprecated — arrival must strictly touch the key level; any
  nonzero value in old configs is silently ignored.  Setups where the entry retrace is not
  hit within the watch window are included with `status="void"` to preserve research value.
  `3c` supports all trigger timeframes (`base`, `1min`, `5min`, `15min`):
  - **Base/current-timeframe 3c**: all rules evaluated on canonical/base bars (unchanged path).
  - **Non-base 3c**: arrival, inside/muted candles, SFP tagging, and reversal confirmation are
    evaluated on trigger-timeframe candles.  Retrace entry fill is evaluated on canonical/base
    bars after reversal trigger candle completion.  `max_entry_wait_bars_after_reversal` counts
    trigger-timeframe bars, not base bars.  Emitted `entry_bar_index` and `retrace_entry_price`
    are base-indexed so backtest execution remains unchanged.

  Index semantics for both base and non-base 3c:
  - `arrival_bar_index`, `reversal_bar_index`, `entry_bar_index`, `bar_index` are canonical/base indices.
  - `trigger_arrival_bar_index`, `trigger_reversal_bar_index`, `trigger_bar_index` are trigger-df indices.
  - `trigger_bar_index == trigger_reversal_bar_index` for 3c.
  - `trigger_timestamp` is the reversal trigger candle completion timestamp.
  - `timestamp == base_df["timestamp"].iloc[bar_index]` holds for all 3c signals.
  - Invalid edge-case setups (for example missing retrace trigger prices or out-of-range
    base/reversal indices at dataset boundaries) are skipped defensively instead of
    crashing signal generation.
- **Signals page observability guards:** generation and chart rendering are wrapped with
  narrow exception guards so failures are surfaced in-page (`st.error` + traceback)
  instead of triggering a full Streamlit page crash.

---

## Phase 5 Implementation Notes

- **Phase 5 implements single SL/TP trade simulation.** `thesistester/engine/backtest.py`
  converts Phase 4 candidate signals into simulated trades using one fixed tick-based
  SL/TP configuration per run.
- **Simple triggers** (touch / reject / break / reclaim) enter at next-bar open to preserve
  no-look-ahead integrity. With non-base trigger timeframe selection, this still means
  `bar_index + 1` on the canonical/base DataFrame, i.e., the first base bar after the
  trigger candle has fully closed. For these rows, `timestamp` remains the canonical/base
  timestamp at `bar_index`; `trigger_timestamp` is the trigger-candle completion timestamp.
- **`3c` filled signals** enter on their signal bar at `entry_reference_price`
  because Phase 4 only emits `status="filled"` after the entry retrace has already
  been hit.  `status="void"` rows are skipped.
- **Intrabar ambiguity uses SL-first** (pessimistic rule): when both SL and TP are reachable
  within the same OHLC bar the engine exits at SL, since intrabar event order is unknowable.
- **Phase 6** implements SL/TP grid search (see Phase 6 notes below).

## Phase 6 Implementation Notes

- **Grid search reuses the Phase 5 engine.** `thesistester/analytics/grid.py` sweeps every
  `(stop_loss_ticks, take_profit_ticks)` pair by calling `simulate_trades()` and
  `summarize_trades()` for each cell — no trade-simulation logic is duplicated.
- **`run_sl_tp_grid()`** returns one tidy summary row per cell including expectancy, total R,
  win rate, profit factor, max drawdown R, and optional ratio / point columns.
- **`best_grid_result()`** filters by a minimum trade count and returns the row with the
  highest value of the chosen metric (default `expectancy_r`).
- **No walk-forward or statistical validation** is implemented in Phase 6.  Grid search is
  purely descriptive: sweeping many SL/TP combinations on the same dataset can overfit.
  Out-of-sample validation belongs to a later phase.
- **Grid Search page** (`pages/8_Grid_Search.py`) exposes SL/TP ranges, optional max-holding
  bars, allow-same-bar-exit, ranking metric, and min-trade-count controls.  Results are stored
  in `st.session_state["grid_results"]` and `st.session_state["best_grid_result"]`.
  Four heatmaps (expectancy, total R, win rate, max drawdown R) are displayed via Plotly.

## Phase 6.5 Implementation Notes

- **Setup Builder is functional.** `pages/2_Setup_Builder.py` now builds and validates reusable
  setup dictionaries and stores the active setup in `st.session_state["setup_config"]`.
- **Local setup-library persistence.** Setup metadata and configs are stored in
  `.thesistester_store/setups/` via `thesistester/persistence/local_store.py`
  (`save_setup`, `list_saved_setups`, `load_setup`, `delete_setup`) using JSON payloads.
  Active setup compatibility remains in-session via `st.session_state["setup_config"]`
  and optional in-session history `st.session_state["setup_configs"]`.
- **Saved setups workflow in Setup Builder.** Users can load to editor, duplicate, set active,
  and delete saved setups. Listing is newest-first and dataset-aware when `dataset_id` is present.
- **Dataset-mismatch protection.** On dataset switch, incompatible active setups are cleared
  (when setup `dataset_id` differs from active `dataset_id`) to prevent silent stale reuse.
- **Signals setup-source selection.** `pages/6_Signals.py` supports three explicit sources:
  manual controls, active setup (`st.session_state["setup_config"]`), and saved setup library.
  Manual controls remain available and unchanged.
- **Dataset-aware setup library selection in Signals.** Signals lists current-dataset and
  global setups by default, with optional inclusion of other-dataset setups and clear relation labels.
- **Saved-run setup snapshot copy.** Signals can copy setup snapshots from selected saved signal
  runs back into Setup Builder session state (`setup_config` and `_setup_builder_editor_config`)
  for review/edit/save workflows without auto-persisting a new setup.

---

## Anchor Confluence Workflow (Implemented through Phase 8)

### 1. Setup config fields

Saved setup configs support both global and anchor confluence modes:

```python
{
    "confluence_mode": "global_cluster" | "anchor_rules",
    "anchor_level": str | None,
    "confluence_rules": list[dict],
    "min_valid_confluences": int,
}
```

Anchor rule schema:

```python
{
    "level": str,
    "tolerance_ticks": float,
    "required": bool,
}
```

### 2. Engine routing

Signals page routing for setup-source saved setups:

```text
global_cluster -> detect_confluence_zones()
anchor_rules -> detect_anchor_confluence_zones()
```

Manual Signals-page controls remain the global-cluster flow.

### 3. Output schema compatibility

The anchor engine emits the same core zone columns used downstream:

```text
timestamp
bar_index
zone_low
zone_high
zone_mid
level_count
level_names
level_prices
```

It also adds diagnostics:

```text
confluence_mode
anchor_level
anchor_price
valid_confluence_count
required_valid
rule_results
```

### 4. Backward compatibility

- Old configs without `confluence_mode` default to `global_cluster`.
- Existing global-confluence behavior remains preserved.
- Manual Signals flow remains global-cluster only.

### 5. Diagnostics

- `rule_results` is JSON emitted by `detect_anchor_confluence_zones()`.
- Signals parses `rule_results` into a per-rule audit table for display.
- Invalid optional confluences are included in diagnostics but excluded from zone boundaries (`zone_low`, `zone_high`, `zone_mid`) and included-level fields.

---

## 13. Key Assumptions & Decisions (confirmed)

1. **Primary instruments:** ES and NQ futures.
2. **Data source for MVP:** CSV upload.
3. **Default cluster tolerance unit:** ticks.
4. **Intrabar fill assumption:** SL-first / pessimistic when both SL and TP are reachable in one candle.
5. **Default entry timing:** next-bar open for simple triggers to avoid look-ahead bias.
6. **Value-area percentage:** 70% default.
7. **Trigger-specific exception:** `3c` filled signals do not use default next-bar-open entry; they use the entry-bar retracement trigger/price model.

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

---

## Phase 7 Implementation Notes

- **Descriptive diagnostics only.** Phase 7 analyzes completed Phase 5 trades and does not
  resimulate trades or change execution logic.
- **Time buckets and RTH segments** are derived from entry or exit timestamps converted to the
  instrument exchange timezone.
- **Grouped summaries include trade count and low-sample warnings** so users do not overinterpret
  small samples.
- **Statistical validation is deferred to Phase 8.**

---

## Phase 8 Implementation Notes

- **Diagnostic only, not proof of edge.** All Phase 8 outputs provide evidence and
  warnings to support research decisions. They do not prove a trading edge or constitute
  statistical significance in the formal hypothesis-testing sense.
- **Bootstrap (`bootstrap_expectancy_ci`) assumes the observed sample represents the
  trade distribution.** Results are unreliable for very small samples (< 30 trades).
  The percentile bootstrap is simple and appropriate for exploratory research; BCa or
  other corrections are left for future work.
- **Sign-flip permutation test (`permutation_test_expectancy`) assumes sign symmetry
  around zero and ignores serial dependence between trades.** The null hypothesis is that
  trade outcomes are symmetric around zero expectancy. Clustered or autocorrelated trades
  will produce anti-conservative p-values. This is a simplified diagnostic, not a
  definitive proof.
- **Grid-search overfit warning (`grid_overfit_diagnostics`) is heuristic and
  deterministic.** The risk level is based on the number of valid grid cells and the gap
  between best and median metric values. No formal multiple-comparison correction (e.g.
  Bonferroni, Holm, FDR) is applied; that belongs to future research.
- **Stronger validation (walk-forward, out-of-sample, Bayesian inference, serial-
  dependence modelling, formal multiple-hypothesis correction) belongs to future
  research phases** and is explicitly out of scope for Phase 8.

---

## Phase 9 Implementation Notes

- **Session-state export only.** Phase 9 serializes current in-memory research outputs
  into export artifacts and does not recompute backtests or mutate prior analysis.
- **No persistence layer is added.** There is no database storage, user account model,
  cloud sync, or automatic job scheduling in this phase.
- **Large raw tables are excluded by default.** Full `data` and `levels` tables are not
  included in the consolidated artifact to keep export size practical.
- **Dual-format reporting.** Exports include a machine-readable JSON artifact and a human-
  readable Markdown report, plus CSV downloads for key result tables.
- **Research-only caveats are embedded in outputs.** Artifacts explicitly reiterate
  historical-data limitations, intrabar ambiguity assumptions, overfit risk, and that
  outputs are not trading advice.

---

## R8 Implementation Notes — Save-as-Default Execution Settings

- **UI/persistence layer only.** No changes to `thesistester/engine/backtest.py`,
  `thesistester/analytics/grid.py`, `thesistester/analytics/metrics.py`, reporting,
  or calculation logic.
- **Explicit-save-only policy.** Running a backtest or grid search never auto-saves
  defaults.  Defaults are persisted only when the user explicitly clicks
  **💾 Save execution settings as default**.
- **Namespace isolation.** `backtest_defaults` and `grid_defaults` are independent
  keys in `ui_state.json`.  Writing one never affects the other or any unrelated keys
  such as `active_dataset_id`.
- **Schema version guard.** Both namespaces include `defaults_schema_version = 1`.
  A mismatch causes the namespace to be ignored and widgets to fall back to their
  built-in `value=` defaults.
- **Validation before injection.** Saved defaults pass through
  `thesistester/execution_defaults.py` before reaching `st.session_state`.
  Invalid values (out-of-range numbers, unknown policy/timezone/metric strings,
  malformed time strings, non-bool booleans) are dropped silently.
- **Session-state safety.** Defaults are injected only into absent session-state keys
  (`if key not in session_state`).  In-session user edits are never overwritten.
- **Reset preserves downstream results.** `reset_backtest_session_keys` and
  `reset_grid_session_keys` remove only the known execution-settings widget keys.
  Result keys such as `backtest_execution_costs`, `grid_results`, and
  `grid_execution_costs` are preserved for downstream pages (Validation, Report).
