# ThesisTester User Guide

User-facing how-tos for classic pages and Research Assistant Help.
This file is the primary Help corpus home for workflow questions (HC-series).

**Help allowlist (HC-1):** only the filled H2 sections listed in RQ §7.1
`user_guide` are Help-readable. Remaining `_Stub (HC-0)_` sections are structure
placeholders for HC-2/HC-3 and are **not** allowlisted.

Deep metric definitions stay in `docs/METRICS_GLOSSARY.md`. Engine honesty and
limits stay in `docs/ASSUMPTIONS_AND_LIMITATIONS.md`. Operator/agent runbooks
(`docs/AGENT_GUIDE.md`) are never part of user Help.

## Purpose and honesty

ThesisTester is a research-screening backtester for futures day-trading
workflows (levels → setups → signals → backtest / grid / validation). Help
answers from allowlisted docs only; it does not invent run metrics, prove OOS
edge, or place live trades. Performance questions belong in **Discuss results**.

## Classic workflow overview

**What it is.** The classic Streamlit pages are a linear research path for one
instrument/dataset. Research Assistant sits beside that path for thesis draft,
Discuss results, and Help.

**Related terms.** workflow, classic pages, Data, Levels, Setup Builder,
Signals, Backtest, research path, how to start

**How to use.**

1. **Data** — load or upload OHLCV, set instrument / timezone / format profile,
   validate roll metadata, optionally save the dataset locally.
2. **Levels** — configure level families, then **Calculate levels** /
   **Recalculate levels**.
3. **Setup Builder** (optional but recommended) — save a reusable setup and
   **Set active**.
4. **Signals** — generate confluence zones and candidate entries (OTF is not
   applied on this page).
5. **Backtest** — set SL/TP, costs, exposure, intrabar model; **Run backtest**.
6. Later pages (Grid, Time, Validation, Report, Bundles, Portfolio) refine and
   export — covered in later Help sections.

**What it is not.** Completing the path does not prove an edge. In-sample KPIs
are diagnostics. Ask Help for how-tos; use Discuss results for run metrics.

**Related pages.** Data → Levels → Setup Builder → Signals → Backtest; Research
Assistant for thesis / Discuss / Help.

## Data

**What it is.** The **Data** page loads and validates OHLCV for the active
instrument, builds dataset identity, and records futures roll assumptions.

**When to use it.** First step of every classic run — before Levels or Signals.

**Related terms.** import, upload, CSV, Quantower, NinjaTrader, Sierra,
Databento, timezone, instrument, sample data, format profile, ingestion mode,
15-second primary, roll metadata, saved datasets, dataset identity

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Instrument` | Contract metadata (tick size, point value) | Wrong instrument → wrong R and costs |
| `Source` | `Sample data` or `Upload CSV` | — |
| `Ingestion mode` | Recommended 15s-primary (derive 1m) vs legacy 1m primary | 15s path still researches on derived 1m bars |
| `CSV format profile` | Explicit vendor layout (no auto-detect) | ThesisTester never auto-detects formats |
| `Source timestamp timezone` | How source timestamps are interpreted | Wrong TZ shifts sessions/levels |
| Futures roll controls | `Roll method`, contract/adjustment/rule fields | Validate before trusting continuous history |
| `Local dataset name` + **Save dataset locally** | Persist into the local store | Store may not persist if `THESISTESTER_STORE_DIR` is unset |

**How to use.**

1. Optionally pick a row under **Saved datasets** → **Load saved dataset**.
2. Choose **Instrument** and **Source**.
3. For uploads: set **Ingestion mode**, **CSV format profile**, **Source
   timestamp timezone**, upload the CSV; optionally preview resampled TFs.
4. Review validation metrics (rows, inferred interval, RTH/ETH, issues).
5. Set **Futures roll assumptions** → **Validate roll metadata**.
6. Name the dataset → **Save dataset locally** when you want reuse.

**What it is not.**

- Not a live data feed or broker connection.
- Primary duplicates are never silently auto-deduped (volume/VWAP honesty).
- Lower-timeframe dual-upload is optional/legacy and for replay diagnostics.
- Format profiles are explicit; wrong profile → bad bars, not a soft warning-only
  success.

**Related pages.** Levels (next); Backtest may need lower TF data for some
intrabar models.

## Levels

**What it is.** The **Levels** page computes session, indicator, profile, and
opt-in advanced level columns for the active dataset.

**When to use it.** After Data is loaded; required before Setup Builder or
Signals.

**Related terms.** calculate levels, recalculate, opening range, SMA, EMA,
VWAP, POC, value area, prior day VA, pivots, dVWAP, TPO, APOC, prev30mVWAP,
saved snapshots, regenerate

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Opening range duration (minutes)` | OR window length | — |
| `SMA lengths` / `EMA lengths` + timeframes | Indicator levels on chosen TFs | Comma-separated lengths must parse |
| `Rolling VWAP windows` / `Rolling POC windows` | Intraday rolling anchors | Large data + rolling POC can be slow |
| `Value area (%)` + prior D/W/M VA aggregation ticks | Profile VA/POC binning | Aggregation ticks ≠ instrument tick size |
| **Advanced opt-in levels** | Pivots, dVWAP_RTH, TPO single prints, APOC, prev30mVWAP | Off unless enabled |
| **Calculate levels** / **Recalculate levels** | Build or refresh level artifacts | Stale after data/settings change |

**How to use.**

1. Confirm Data is loaded (page warns otherwise).
2. Configure OR / SMA / EMA / VWAP / POC / VA (+ advanced opt-ins if needed).
3. Click **Calculate levels** or **Recalculate levels** (or load a matching
   saved snapshot).
4. Optionally **Save levels locally**.
5. Preview/plot with **Levels to plot** and **Chart range** (visualization only).

**What it is not.** Chart range does not change saved level artifacts. Failed
recalculations keep the previous successful levels. Levels are research inputs,
not trade signals by themselves.

**Related pages.** Data (prerequisite); Setup Builder / Signals (consumers).

## Setup Builder

**What it is.** The **Setup Builder** page defines a reusable setup: which levels
participate, confluence rules, naked-level filters, trigger logic, direction,
and optional OTF filter settings for later simulation pages.

**When to use it.** After Levels exist; before or alongside Signals when you
want a saved/active setup instead of one-off manual signal config.

**Related terms.** setup, confluence, tolerance ticks, naked, trigger, touch,
reject, break, reclaim, 3c, trigger timeframe, direction, OTF filter, active
setup, save setup, thesis link

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Confluence mode` | `Global cluster` or `Anchor-based rules` | Anchor mode needs a valid anchor level |
| `Selected level columns` / anchor + confluence levels | Which levels can cluster | Unavailable levels block clean saves |
| `Tolerance ticks` / per-level tolerances | How close levels must be | Too wide → noisy zones |
| `Minimum` / `Maximum confluences` | Cluster size bounds | Max < min yields nothing useful |
| `Naked only` + `Naked requirement` | Untested-level filter (`any` / `all`) | — |
| `Trigger` | `touch`, `reject`, `break`, `reclaim`, `3c` | 3c adds retrace / wait-bar params |
| `Trigger timeframe` | Base or higher TF for trigger logic | Non-base 3c splits work across TFs |
| `Direction` | `long`, `short`, or `both` | — |
| `Enable OTF filter` + OTF TFs / min bars | Higher-TF one-timeframing gate | Default off; applied later, not on Signals |

**How to use.**

1. Load Levels first.
2. Optionally load from **Local setup library** → **Load to editor** /
   **Set active**.
3. Edit **Setup name**, confluence mode, naked, trigger, timeframe, direction,
   and optional OTF block.
4. **Save setup** (becomes active) or clear with **Clear active setup**.
5. Use the active/saved setup on **Signals**, then Backtest / Grid / Validation.

**What it is not.**

- Saving a setup does not generate signals or run a backtest.
- OTF defaults **disabled**. Signals keep the full candidate population; Backtest
  / Grid / Walk-forward apply OTF when enabled (rejected candidates stay for
  audit).
- Cross-dataset loads may warn; unavailable level refs need explicit
  **Save with unavailable levels removed**.

**Related pages.** Levels; Signals; Backtest / Grid / Validation (OTF consumers).

## Signals

**What it is.** The **Signals** page detects confluence zones and generates
candidate entry signals from levels + setup parameters.

**When to use it.** After Levels (and usually an active/saved setup). Required
before Backtest.

**Related terms.** generate signals, confluence zones, candidates, setup source,
active setup, saved setup, naked levels, trigger, signal table, signal runs

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Setup source` | Manual / active setup / library setup | Library OTF snapshot is whatever was saved |
| Manual confluence + trigger controls | Same concepts as Setup Builder | Easy to drift from the saved setup |
| **Generate signals** | Build zones + candidate entries | Does **not** apply OTF admission |
| Saved signal runs | Load/save/delete generated artifacts | Needs trusted dataset + levels identity |

**How to use.**

1. Ensure Data → Levels are ready.
2. Choose **Setup source** (`Use active setup` is the usual path).
3. Click **Generate signals**.
4. Inspect **Confluence zones detected**, **Signals generated**, tables, and
   optional chart (**Chart range** is visualization-only).
5. Optionally **Save current signals** or **Copy setup to Setup Builder**.

**What it is not.**

- Not a broker order blaster and not a filled-trade list.
- **OTF is not applied here** — admission happens later on Backtest / Grid /
  Walk-forward when enabled.
- Chart overlays do not change the signal artifact.

**Related pages.** Setup Builder; Backtest (next consumer).

## Backtest

**What it is.** The **Backtest** page simulates trades from Phase-4 candidate
signals with fixed SL/TP plus optional costs, intrabar resolution, exit
management, session-flat, and exposure policies.

**When to use it.** After Signals exist and you want path KPIs for one SL/TP
(and related execution assumptions).

**Related terms.** run backtest, stop loss ticks, take profit ticks, commission
per side, slippage ticks, slippage_ticks, exposure policy, cooldown, intrabar,
session close, break-even, trailing stop, win rate, avg R, expectancy

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Stop loss (ticks)` / `Take profit (ticks)` | Bracket size in instrument ticks | R is relative to SL distance |
| `Commission per side (currency/contract)` | Fee each side; round-trip ≈ `2 ×` | Leaving 0 overstates net edge |
| `Slippage (ticks per side)` | Adverse ticks at entry and exit (`slippage_ticks`) | Same — optimistic fills if 0 |
| `Intrabar resolution` | SL-first, OHLC path, or lower-TF replay variants | Paths are assumptions, not tick truth |
| `Flat by session close` + close time/TZ | Force exits at session boundary | Display TZ ≠ engine session TZ |
| `Policy` (exposure) | `allow_all`, `single_position`, `single_direction`, `single_setup` | Skips ≠ OTF rejects ≠ 3c voids |
| `Cooldown bars after exit` | Bars before a new entry is allowed | — |
| Exit management expander | Break-even / trailing after R multiple | Stops update after completed bars |

**How to use.**

1. Confirm Signals are loaded.
2. Set SL/TP, costs, intrabar model, session exit, and exposure policy in
   **Backtest settings**.
3. Optionally **Save execution settings as default**.
4. Click **Run backtest**.
5. Read OTF-rejected / exposure-skip notes, **Performance summary**, equity
   curve, breakdowns, and trade table. Use Discuss results for run Q&A.

**What it is not.**

- Not proof of OOS edge; one backtest is an in-sample diagnostic under stated
  assumptions.
- Intrabar models do not recover the true tick path; residual SL/TP ambiguities
  are counted, not wished away.
- Help will not invent your best SL/TP — ask **Discuss results** for bound run
  metrics.

**Related pages.** Signals (prerequisite); Grid Search for SL/TP sweeps; Research
Assistant Discuss for performance questions.

## Grid Search

_Stub (HC-0)._ How to run a grid search, choose ranking metric / min trades, and
read the best cell without treating IS selection as proof. Filled in HC-2.

## Time Analysis

_Stub (HC-0)._ How to use time buckets and the limits of “best entry” language.
Filled in HC-2.

## Validation and robustness

_Stub (HC-0)._ How to run WFA / Monte Carlo / robustness batteries as
diagnostics, not proof. Filled in HC-2.

## Report Export

_Stub (HC-0)._ What exports contain and how they relate to research bundles.
Filled in HC-2.

## Research Bundles

_Stub (HC-0)._ How to import/export bundles, hash identity, and restore vs
recompute. Filled in HC-2.

## Portfolio

_Stub (HC-0)._ Multi-setup portfolio scope and honesty limits. Filled in HC-2.

## Research Assistant (draft, Discuss, Help)

_Stub (HC-0)._ Thesis draft vs Discuss results vs Help; confirm/run gates.
Filled in HC-3.

## Research mode on classic pages

_Stub (HC-0)._ How to link a thesis and record/discuss a classic run. Filled in
HC-3.

## When to use Help vs Discuss results

_Stub (HC-0)._ Help = product/how-to from docs; Discuss = bound run metrics.
Filled in HC-3.
