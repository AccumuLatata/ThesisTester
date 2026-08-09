# ThesisTester User Guide

User-facing how-tos for classic pages and Research Assistant Help.
This file is the primary Help corpus home for workflow questions (HC-series).

**Help allowlist (HC-1…HC-3 + HC-5/HC-6):** the filled H2 sections listed in RQ
§7.1 `user_guide` are Help-readable (classic + Assistant how-tos, plus dedicated
**Exposure policy**, **Intrabar resolution**, **Exit management**, **Session
close and entry cutoff**, and **Focus vs Admit**).

Deep metric definitions stay in `docs/METRICS_GLOSSARY.md`. Engine honesty and
limits stay in `docs/ASSUMPTIONS_AND_LIMITATIONS.md`. Operator/agent runbooks
(`docs/AGENT_GUIDE.md`) are never part of user Help.

## Purpose and honesty

ThesisTester is a research-screening backtester for futures day-trading
workflows (levels → setups → signals → backtest / grid / validation). Help
answers from allowlisted docs only; it does not invent run metrics, prove OOS
edge, or place live trades. Performance questions belong in **Discuss results**
(Research Assistant mode **Discuss runs**).

## Classic workflow overview

**What it is.** The classic Streamlit pages are a linear research path for one
instrument/dataset. Research Assistant sits beside that path with modes
**Discuss runs**, **Help**, and **Draft thesis** (surfaces: Discuss results,
Help / how it works, Assistant chat).

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
6. **Grid Search** / **Time Analysis** / **Validation and robustness** refine
   diagnostics; **Report Export** / **Research Bundles** / **Portfolio** export
   or combine results (see those Help sections).

**What it is not.** Completing the path does not prove an edge. In-sample KPIs
are diagnostics. Ask Help for how-tos; use **Discuss results** in mode
**Discuss runs** for run metrics.

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
| `Ingestion mode` | Recommended 15s-primary (derive 1m) vs legacy 1m primary | Sparse Quantower/Rithmic minutes are retained; use R12 `subtimeframe_conservative` unless Build empty bars is on |
| `CSV format profile` | Explicit vendor layout (no auto-detect) | ThesisTester never auto-detects formats |
| `Source timestamp timezone` | How source timestamps are interpreted | Wrong TZ shifts sessions/levels |
| Futures roll controls | `Roll method`, contract/adjustment/rule fields | Validate before trusting continuous history |
| `Local dataset name` + **Save dataset locally** | Persist into the local store | Set `THESISTESTER_STORE_DIR` (`.env` or `scripts/set_store_dir.ps1`) so the store is explicit and durable |

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
| **Advanced opt-in levels** | Pivots, dVWAP_RTH, dVWAP (CME session), TPO single prints, APOC, prev30mVWAP | Built-in defaults enable all families; uncheck a box to omit |
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
optional OTF filter settings, and an optional Admit `entry_window` for later
simulation pages.

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
| `Save Admit entry window on setup` | Persists normalized Admit `entry_window` | Default off; distinct from Time Analysis Focus |

**How to use.**

1. Load Levels first.
2. Optionally load from **Local setup library** → **Load to editor** /
   **Set active**.
3. Edit **Setup name**, confluence mode, naked, trigger, timeframe, direction,
   optional OTF block, and optional Admit entry window.
4. **Save setup** (becomes active) or clear with **Clear active setup**.
5. Use the active/saved setup on **Signals**, then Backtest / Grid / Validation.

**What it is not.**

- Saving a setup does not generate signals or run a backtest.
- A saved setup `entry_window` does **not** auto-apply Admit on Backtest Run —
  arm/apply Admit via Backtest controls or Time Analysis **Promote to Admit**.
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
| `Setup source` | `Configure manually` / `Use active setup` / `Use saved setup from library` | Library OTF snapshot is whatever was saved |
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
| `Intrabar resolution` | See **Intrabar resolution** | Paths are assumptions, not tick truth |
| `Flat by session close` + close time/TZ | See **Session close and entry cutoff** | Display TZ ≠ engine session TZ |
| `Policy` (exposure) | See **Exposure policy** | Skips ≠ OTF rejects ≠ 3c voids |
| `Cooldown bars after exit` | See **Exposure policy** | `0` = no post-exit spacing |
| `Constrain entries to time window` (Admit) | See **Focus vs Admit** | Re-sim only — not Time Analysis Focus |
| `Exit management (break-even / trailing)` | See **Exit management (break-even and trailing)** | Stops update after completed bars |

**How to use.**

1. Confirm Signals are loaded.
2. Set SL/TP, costs, **Intrabar resolution**, session exit, optional **Entry
   window (Admit)**, exit management, and exposure **Policy** / cooldown in
   **Backtest settings** (see the dedicated Help sections named above).
3. Optionally **Save execution settings as default**.
4. Click **Run backtest**.
5. Read OTF-rejected / skip notes (window vs cutoff vs exposure), **Performance summary**,
   equity curve, breakdowns, and trade table. Use **Discuss results** (mode
   **Discuss runs**) for run Q&A.

**What it is not.**

- Not proof of OOS edge; one backtest is an in-sample diagnostic under stated
  assumptions.
- Help will not invent your best SL/TP — ask **Discuss results** in mode
  **Discuss runs** for bound run metrics.

**Related pages.** Signals; **Exposure policy**; **Intrabar resolution**;
**Exit management (break-even and trailing)**; **Session close and entry
cutoff**; **Focus vs Admit**; Grid Search; Research Assistant **Discuss runs**.

## Exposure policy

**What it is.** Exposure policy is the Backtest (and Portfolio) admission gate
that decides whether an otherwise-executable signal may open a new trade while
other trades are still open — or during an optional cooldown after exit. On the
**Backtest** page the control is labeled **Policy** under the **Exposure policy**
subheader; the engine field is `exposure_policy`.

**When to use it.** Use restrictive policies when you want path KPIs that
respect “one book / one direction / one setup at a time.” Keep `allow_all` when
screening every signal independently (legacy default).

**Related terms.** exposure, exposure policy, Policy, allow_all, single_position,
single_direction, single_setup, cooldown, cooldown bars after exit,
overlapping_position, overlapping_direction, overlapping_setup, cooldown_active,
skipped signals, blocking trade, exposure_group_key

**Key settings.**

| Control / value | Meaning | Common pitfall |
|---|---|---|
| `allow_all` (default) | Every executable signal may trade; overlapping signals are independent | Inflates trade count vs a real one-position book; cooldown is a no-op here |
| `single_position` | At most one open trade at a time (any direction/setup) | Later signals skip as `overlapping_position` |
| `single_direction` | At most one open trade per direction (`long` / `short`) | Opposite side can still overlap |
| `single_setup` | At most one open trade per setup group. Backtest key order: `setup_name` → `zone_id` → `level_source_label` → `level_names` → else `trigger\|direction` | Shared `level_names` can collide even when zone labels differ; trigger/direction is last resort |
| `Cooldown bars after exit` | Under `single_*` only: after a blocking trade exits, wait this many bars before admitting another in the same exposure group | No-op under `allow_all`; skip reason is `cooldown_active` when entry is after exit but inside cooldown |

**How admission works (Backtest).**

1. Window / cutoff rejects (`outside_entry_window`, `after_entry_cutoff`) are
   evaluated **before** exposure — rejected candidates never compete for a slot.
2. Under restrictive policies, candidates are ordered by entry bar, signal bar,
   then `signal_id` (deterministic).
3. A candidate is blocked when any relevant prior trade still covers
   `entry_bar_index` through `exit_bar_index + cooldown_bars_after_exit`.
4. Skips appear in **Skipped signals** with `skip_reason`, `blocking_trade_id`,
   and `exposure_group_key`. These are **not** OTF rejects and **not** `3c` voids.
5. Backtest captions split skip counts: outside entry window / after entry
   cutoff / exposure-other.

**Portfolio note.** Portfolio uses the same four policy **names** after merging
completed per-setup trades (diagnostic merge — not a live margin engine), but
grouping differs: Portfolio `single_setup` keys on merged `setup_id` (not the
Backtest signal-field chain above). Portfolio admission skips show
`skip_reason` / `blocking_trade_id` in **Portfolio admission skips** and do
**not** emit `exposure_group_key`. Prefer upstream Backtest `allow_all` so the
portfolio gate is applied once at merge time. Cooldown is likewise a no-op
under Portfolio `allow_all`.

**How to use.**

1. Open **Backtest** → **Exposure policy**.
2. Choose **Policy** and optional **Cooldown bars after exit**.
3. **Run backtest**, then inspect **Skipped signals** if trade count looks thin.
4. On **Portfolio**, set `Portfolio exposure policy` / cooldown → **Run
   portfolio analysis**, then read **Portfolio admission skips**.
5. Grid / Validation inherit one fixed exposure policy across cells/folds —
   exposure is not a swept axis.

**What it is not.**

- Not a capital, margin, or broker risk engine.
- Not OTF filtering and not Focus (Focus never re-runs exposure/cooldown).
- Default `allow_all` is for screening compatibility — not a claim that
  overlapping fills are realistic.

**Related pages.** Backtest; Portfolio; **Focus vs Admit**; Grid Search.

## Intrabar resolution

**What it is.** **Intrabar resolution** chooses how Backtest orders stop vs
target when both are reachable inside one parent OHLC bar (or lower-TF group).
Control label: `Intrabar resolution`. Engine field: `intrabar_model`.

**When to use it.** Always set deliberately before trusting same-bar SL/TP
outcomes. Default `sl_first` is the legacy pessimistic path.

**Related terms.** intrabar, intrabar resolution, intrabar_model, sl_first,
path_open_proximity, subtimeframe, subtimeframe_conservative, both-hit,
ambiguous resolution, lower timeframe, R12

**Key settings.**

| Value | Meaning | Common pitfall |
|---|---|---|
| `sl_first` (default) | If stop and target are both reachable in one bar, stop wins | Pessimistic; not “true path” |
| `path_open_proximity` | Deterministic O→H→L→C or O→L→H→C from open proximity; equal proximity stays SL-first | Sensitivity assumption, not tick reconstruction |
| `subtimeframe` | Walk observed lower-TF bars in time order | Fails closed unless lower data is strictly finer, complete, and reconciles to parent OHLC |
| `subtimeframe_conservative` | Observed replay on complete reconciled groups; SL-first fallback on missing/misaligned groups | Not full observed replay on sparse minutes |

**How to use.**

1. On **Backtest**, open **Intrabar resolution**.
2. Pick a model. For `subtimeframe*`, ensure lower-TF data is loaded (Data page
   dual-upload or `15s_primary_derive_1m` provenance).
3. **Run backtest**, then read intrabar diagnostics (both-hit / ambiguity
   counts). Glossary: **R12 intrabar diagnostics**.

**What it is not.**

- Not tick-path truth. Residual same-bar / same-sub-bar ambiguity still resolves
  SL-first and is counted, not wished away.
- Lower-TF replay only reduces uncertainty to the lower bar size.
- MAE/MFE parent-bar extremes are separate from R12 event ordering.

**Related pages.** Backtest; Data (lower-TF / derive mode); metrics R12.

## Exit management (break-even and trailing)

**What it is.** Optional completed-bar stop management after a trade is open.
UI expander: **`Exit management (break-even / trailing)`**. Defaults off keep
the fixed SL/TP bracket.

**When to use it.** When you want research paths that move/ratchet stops after
favorable R thresholds — not for broker OCO semantics.

**Related terms.** exit management, break-even, breakeven, trailing stop,
breakeven_after_r, trailing_after_r, trailing_distance_ticks, BE, TRAIL, R13

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Enable break-even move` + `Move stop to break-even after R` | After a completed bar reaches that favorable R, move stop to slipped entry; active next bar | BE exits can still be slightly negative after costs/slippage |
| `Enable trailing stop` + `Start trailing after R` | Arms trailing after completed-bar favorable R | Threshold is completed-bar, not intrabar arming |
| `Trailing distance (ticks)` | Distance from best favorable parent high/low | Trail never loosens; active from next bar |

**How to use.**

1. On **Backtest**, open **Exit management (break-even / trailing)**.
2. Enable BE and/or trail; set R thresholds (and trail distance).
3. **Run backtest**; read BE/TRAIL exit captions and R13 diagnostics.

**What it is not.**

- Not proof of edge; opt-in research assumption.
- Does not change initial risk used for R / MAE/MFE normalization (`stop_price`
  stays the initial bracket stop).
- Same-bar conflicts between an active managed stop and the fixed target still
  follow the selected **Intrabar resolution** model.

**Related pages.** Backtest; **Intrabar resolution**; metrics R13.

## Session close and entry cutoff

**What it is.** Backtest **Session exit policy** controls forced flat at a
session clock and an optional no-new-entries cutoff. Distinct from Admit
`entry_window` (see **Focus vs Admit**).

**When to use it.** When you want same-calendar-day RTH-style flattening instead
of holding to the last bar of the loaded dataset (`EOD`).

**Related terms.** Flat by session close, Session close time, Session timezone,
No new entries after, no_new_entries_after, SESSION_CLOSE, DATA_END, EOD,
after_entry_cutoff, session exit policy

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Flat by session close` | When on, exits are capped at the configured close for the entry date | Off → default `EOD` is last bar in the **dataset**, not a session bell |
| `Session close time` | Local close clock (`HH:MM` / `HH:MM:SS`) | Interpreted in `Session timezone` |
| `Session timezone` | IANA TZ for close / cutoff clocks | Display/export TZ on other pages is not this clock |
| `No new entries after (optional)` | When flat-by-close is on, reject entries after this local clock | Skip reason `after_entry_cutoff`; cutoff uses strict `>` (entry **at** cutoff still admits) |

**How exits / skips read.**

- `SESSION_CLOSE`: forced flat at last bar at-or-before close when SL/TP not hit.
- `DATA_END`: data ended before session close; force-closed at last available bar.
- Window vs cutoff: if both Admit window and cutoff would reject, skip labeling
  prefers `outside_entry_window` (admitted set identical either order).

**How to use.**

1. On **Backtest** → **Session exit policy**, enable **Flat by session close**.
2. Set **Session close time** / **Session timezone**; optionally **No new
   entries after**.
3. **Run backtest**; inspect exit reasons and skip captions
   (outside window / after cutoff / exposure-other).

**What it is not.**

- Not overnight ETH session templates (same-calendar-day RTH-style only today).
- Not Admit Focus/Promote windows — cutoff clocks ≠ entry-window membership TZ
  rules (`session_timezone` vs exchange TZ for RTH segments).

**Related pages.** Backtest; **Focus vs Admit**; **Exposure policy**.

## Grid Search

**What it is.** The **SL/TP Grid Search** page sweeps stop-loss × take-profit
cells over the same Phase-4 candidate signals, ranks cells, and shows heatmaps
plus a full results table.

**When to use it.** After Signals exist and you want to compare many SL/TP pairs
under one fixed execution/path assumption (not after treating one lucky cell as
proof).

**Related terms.** grid search, run grid, SL/TP, stop-loss range, take-profit
range, ranking metric, expectancy_r, min trade count, best SL/TP pair, heatmap,
directional ranking, IS selection

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `SL start` / `SL stop` / `SL step` | Stop-loss sweep in ticks | Huge grids are slow and easy to overfit |
| `TP start` / `TP stop` / `TP step` | Take-profit sweep in ticks | Same |
| Costs / intrabar / session / exposure | Same family as Backtest | One fixed policy applies to **every** cell |
| Inherited `entry_window` (Admit) | Fixed constraint from Backtest/Promote | Not a swept axis — all cells share it |
| `Ranking metric` | Aggregate options include `expectancy_r`, `total_r`, `profit_factor`, `win_rate` | Best cell is in-sample under that metric |
| `Min trade count` | Drop thin cells before ranking | Too low → noisy “winners” |
| **Enable directional ranking** | When on, ranks by **Directional ranking metric** instead of `Ranking metric` | Extra selection degrees of freedom |
| `Directional ranking metric` / `Min long trades` / `Min short trades` | Shown when directional ranking is enabled | Side-specific mins can empty the ranked set |

**How to use.**

1. Prerequisites: Data → Levels → Signals (non-empty candidates). Optionally
   arm/apply an Admit `entry_window` on Backtest first.
2. Set SL/TP ranges, execution assumptions, `Ranking metric`, and `Min trade
   count` (still applied to every cell). If **Enable directional ranking** is
   on, ranking uses **Directional ranking metric** plus `Min long trades` /
   `Min short trades` instead of the aggregate `Ranking metric`.
3. Click **Run grid search**.
4. Read **Best SL/TP pair**, heatmaps, and **Full grid results**.
5. Treat the winner as a hypothesis to validate — not as OOS proof.

**What it is not.**

- Not proof the best cell will work forward. In-sample selection can overfit.
- OTF (when enabled) is applied once before the grid; every cell sees the same
  accepted candidate set.
- One market-path / exit-management assumption is shared across cells.
- Time-of-day is not optimized here; an inherited Admit window is a fixed
  constraint, not a fitness axis.

**Related pages.** Signals; Backtest (single cell / Admit); Validation (overfit / WFA).

## Time Analysis

**What it is.** The **Time Analysis** page is a descriptive breakdown of
**already completed** trades by time-of-day / session windows. It does **not**
re-simulate trades. Optional **Focus summary** recomputes the full Performance
Summary / equity on one bucket as a **post-hoc subset** (still no re-sim;
membership always uses **entry** timestamps even when charts group by exit).

**When to use it.** After a Backtest has produced a trade list and you want to
see when trades clustered — with sample-size humility. Use Focus when a bucket
(e.g. `rth_open_30m`) looks strong and you want the full KPI suite on that
subset before Promoting it into an Admit constraint.

**Related terms.** time analysis, time bucket, entry hour, 30min bucket, RTH
segment, grouping, heatmap, best entry time, session window, no re-simulation,
Focus summary, post-hoc subset, Promote to Admit

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Display/export timezone` | Labels for display/export | Not the engine’s session clock by itself |
| `Time bucket timezone` | Exchange/session vs display TZ for buckets | Mixing TZ bases confuses “best hour” stories |
| `Timestamp basis` | `entry_timestamp` or `exit_timestamp` | Exit basis changes charts only; Focus/Promote still use entry-time buckets (C2) |
| `Primary grouping` / optional secondary | How rows are aggregated | Tiny groups look dramatic |
| `Minimum trades warning threshold` | Soft warning for thin buckets | Ignoring it invites noise |
| `Metric for chart / heatmap` | Which KPI to plot | Charts ≠ causation |
| `Promote to Admit` | See **Focus vs Admit** — arms Backtest `entry_window` | Does **not** auto-run Backtest |

**How to use.**

1. Run a Backtest first (needs `trades`).
2. Choose timezone basis, timestamp basis, groupings, and chart metric.
3. Inspect the grouped table, charts/heatmap, and trade-count distribution.
4. Use thin-bucket warnings: low `trade_count` groups are not “best entries.”
5. Optional Focus / Promote / Admit loop: see **Focus vs Admit**.

**What it is not.**

- Not a re-optimization engine and not a signal generator.
- Focus is **not** an entry constraint and does **not** re-run
  `simulate_trades`, exposure, or cooldown — equity/drawdown is a **subset
  replay** of filtered completed trades (see **Focus vs Admit**).
- “Best hour” language is descriptive on this sample only — not a schedule to
  trade live.
- RTH segment labeling can stay on exchange/session time even when hourly
  buckets use display TZ.

**Related pages.** Backtest; **Focus vs Admit**; Report Export (shared display TZ).

## Focus vs Admit

**What it is.** Two different time-window tools that must not be confused:
**Focus summary** (Time Analysis post-hoc subset) vs **Admit** / **Entry window
(Admit)** (Backtest constrained re-simulation). **Promote to Admit** only arms
the Backtest widgets.

**When to use it.** Use Focus to inspect one bucket’s completed trades. Use
Promote + Admit when you want path KPIs under that entry-time constraint.

**Related terms.** Focus, Focus summary, Clear Focus, Promote to Admit, Admit,
Entry window, Constrain entries to time window, entry_window, post-hoc,
constrained re-simulation, RTH segments, clock range, outside_entry_window

**Key settings.**

| Control / surface | Meaning | Common pitfall |
|---|---|---|
| Time Analysis `Focus summary` | Filters completed trades by **entry** bucket; recomputes KPIs/equity | Does **not** call `simulate_trades`; no exposure/cooldown re-run |
| `Timestamp basis` on charts | May be entry or exit for display | Focus/Promote membership always uses **entry** timestamps (C2) |
| `Promote to Admit` | Arms Backtest `entry_window` from Focus/selected bucket | Does **not** auto-run; thin samples need confirm |
| Backtest `Constrain entries to time window` | Opt-in Admit re-sim (`entry_window`) | Default off = legacy all-day admission |
| `Window mode` / RTH segments / clock range | Admit membership on **entry-bar** local time | Window rejects never enter exposure competition |
| Armed vs applied badges | Armed = pending Promote; applied = constrained run done | All-day Run (Admit off) does **not** consume an armed handoff |

**How to use (Promote → Admit).**

1. Complete a Backtest with trades.
2. On **Time Analysis**, set primary grouping to `entry_rth_segment` /
   `entry_hour_bucket` / `entry_30min_bucket`.
3. Select a bucket → **Focus summary** (optional inspect) → **Promote to Admit**.
4. Open **Backtest**; confirm **Entry window (Admit)** widgets / armed banner.
5. **Run backtest** for constrained re-sim (“only in-window entries were
   admitted”). Inspect `outside_entry_window` skips separately from exposure.

**What it is not.**

- Focus equity/drawdown is a **subset replay** of filtered trades — not
  all-day admission path drawdown.
- Promote is not proof of edge; Focus alone must not be treated as deployable.
- Grid / WFA inherit a fixed enabled Admit window when present — not a swept
  axis. Under `allow_all` + zero cooldown, Focus and Admit can share the same
  `signal_id` set (C7); restrictive exposure can diverge.

**Related pages.** Time Analysis; Backtest; **Exposure policy**;
**Session close and entry cutoff**.

## Validation and robustness

**What it is.** The **Statistical Validation** page runs optional diagnostic
batteries (bootstrap/permutation, walk-forward / WFA, overfitting, noise,
sensitivity, MAE/MFE, Monte Carlo, OTF matrix). Results are **diagnostic only —
not proof of edge**.

**When to use it.** After Backtest trades exist (and often after Grid Search when
you care about SL/TP selection risk).

**Related terms.** validation, robustness, walk-forward, WFA, Monte Carlo,
bootstrap, permutation, overfitting, PBO, DSR, noise test, sensitivity, MAE/MFE,
OTF validation matrix, diagnostic only

**Key settings / batteries.**

| Control / battery | Meaning | Common pitfall |
|---|---|---|
| **Run Validation** | Bootstrap CI, sign-flip permutation, trade-count, grid-overfit checks | CI including zero ≠ “confirmed edge” |
| Walk-forward / OOS (+ optional WFA matrix) | Folded train/test diagnostics | “Diagnostic only — walk-forward can still overfit” |
| Overfitting-detection battery | CSCV/PBO, deflated Sharpe, vs-random | Quantifies selection risk, not future profit |
| Price-series noise test | Local input sensitivity | Not a live-edge certificate |
| Parameter sensitivity | One-at-a-time local flatness | Flat ≠ durable |
| MAE/MFE excursion analytics | Bar-level excursion diagnostics | Not true intrabar path order |
| Monte Carlo path robustness | Resamples the realized R sequence (`reshuffle` / `skip` / `block_resample`) | No trade re-simulation; not future proof |
| OTF filter validation matrix | Fixed multi-config train/OOS comparison | Do not pick production OTF from one matrix pass |

**How to use.**

1. Have Backtest trades (Grid results help overfit / sensitivity / WFA grids).
2. Set sidebar seeds, sample counts, and min-trade soft/hard gates.
3. Run the core **Run Validation**, then opt into WFA / overfit / noise /
   sensitivity / excursions / Monte Carlo / OTF matrix as needed.
4. Read each battery’s honesty caption before acting on rankings.

**What it is not.**

- Not a hypothesis test that “proves” a strategy.
- Batteries appear only **when run** — missing sections mean they were not
  executed in this session, not that they passed.
- `allow_all` exposure upstream can inflate trade counts and understate
  uncertainty.

**Related pages.** Backtest; Grid Search; Report Export / Bundles for artifacts.

## Report Export

**What it is.** The **Report / Export** page downloads reproducible research
artifacts (JSON, Markdown, CSVs) from the current session state.

**When to use it.** After you have (at least) setup/signals/trades and want a
portable report or per-table CSV extract.

**Related terms.** report export, download JSON, markdown report, research
artifact, signals.csv, trades.csv, grid_results, checklist, display timezone

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Display/export timezone` | TZ used in exported labels | Does not rewrite engine session time |
| Session artifacts checklist | Shows which blocks are present | Optional diagnostics stay empty until run |
| **⬇️ Download JSON artifact** / **⬇️ Download Markdown report** | Primary report downloads | Incomplete session → sparse files |
| Per-table CSV downloads | Optional extracts when tables exist | — |
| Inspect previous artifact | Upload `research_artifact.json` read-only | Preview only — does not restore a live session |

**How to use.**

1. Complete upstream research (core path: setup, signals, trades).
2. Check the session / entry-window (Focus/Admit) / OTF artifact checklists.
3. Set display/export timezone.
4. Use **⬇️ Download JSON artifact**, **⬇️ Download Markdown report**, and any
   available CSV downloads.

**What it is not.**

- Not a full session restore tool (see Research Bundles for zip snapshots).
- Missing checklist rows mean those diagnostics were never run — not a silent
  pass.
- Focus checklist rows are post-hoc provenance — not Admit constrained-re-sim
  evidence.
- Uploaded JSON inspection is read-only preview.

**Related pages.** All upstream analytics pages; Research Bundles for zip
import/export.

## Research Bundles

**What it is.** The **Research Bundles** page exports/imports a portable zip
snapshot of research state for the session (dataset, levels, signals, backtest,
grid, validation batteries, portfolio, etc. when present).

**When to use it.** To move a research snapshot between machines/sessions, or to
reload a prior bundle into classic pages.

**Related terms.** research bundle, download bundle, import bundle, zip
snapshot, hash identity, restore session, record and discuss, portable state

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| **Export preview** | Which artifacts will be included | Empty session → nothing meaningful to export |
| **Download research bundle** | Writes a timestamped zip | Bundle ≠ live broker state |
| **Upload research bundle** + **Import bundle into session** | Restores included artifacts into session | Re-check classic context after import |
| **Thesis recording** (when available) | **Record and discuss this run** / **Discuss this run** | Discuss needs a recorded run, not only live trades |

**How to use.**

1. Build research state across classic pages.
2. Review **Export preview** → **Download research bundle**.
3. On another session: upload the zip → review contents → **Import bundle into
   session** → open the listed pages.
4. Optionally use **Record and discuss this run** / **Discuss this run** when a
   thesis context is active.

**What it is not.**

- Not a substitute for Report Export’s human-readable Markdown/CSV pack (different
  job).
- Import restores research artifacts; it does not re-prove metrics or invent
  missing batteries.
- Classic zip import validates manifest/schema/members. `canonical_bundle_hash`
  fail-closed checks apply when recording/discussing a thesis-bound run — not as
  a re-hash gate on zip restore itself.

**Related pages.** Report Export; classic pages listed in the import flash
(Data through Portfolio).

## Portfolio

**What it is.** The **Portfolio** page merges completed, independently simulated
setup trade lists under a portfolio exposure policy for diagnostic combined
equity / contribution / correlation views.

**When to use it.** When you have **at least two** completed-trade tables for the
same instrument/timeline — any mix of in-session Backtest `trades` and uploaded
CSVs (two CSVs alone is valid if session trades are empty).

**Related terms.** portfolio, multi-setup, combined equity, marginal
contribution, correlation, portfolio exposure policy, admitted trades, skipped
trades, diagnostic merge

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| `Current setup label` | Name for the in-session trade table (shown when Backtest `trades` exist) | Absent when session trades are empty |
| `Additional completed-trade CSV exports` | Upload one or more trade CSVs | Need ≥2 setup tables total across session + uploads |
| `Portfolio exposure policy` | Same four **names** as Backtest **Policy** (see **Exposure policy**); `single_setup` groups by merged `setup_id` | Applied after merge — not a live margin engine; not the Backtest signal-field group key |
| `Cooldown bars after exit` | Portfolio-level spacing after a blocking exit under `single_*` | No-op under `allow_all` (same as Backtest) |

**How to use.**

1. Export/collect completed-trade CSVs (often from Report Export).
2. Provide ≥2 setup trade tables: use session Backtest `trades` and/or
   **Additional completed-trade CSV exports**.
3. Set labels (when shown), portfolio exposure, cooldown → **Run portfolio
   analysis**.
4. Read combined equity, marginal contribution, correlation, and admission skips.

**What it is not.**

- **Not** a capital, margin, liquidity, or fill simulation — post-hoc merge only.
- Upstream per-setup runs should usually use `allow_all` so the portfolio policy
  is applied once at merge time.
- Diagnostic only; combined R/DD is not proof of a deployable book.

**Related pages.** Backtest; **Exposure policy**; Report Export (`trades.csv`).

## Research Assistant (draft, Discuss, Help)

**What it is.** The **Research Assistant** page manages theses with three peer modes
(`Discuss runs` / `Help` / `Draft thesis`) hosting separated chat surfaces:
**Discuss results** (completed-run Q&A; default mode), **Help / how it works**,
and thesis **Assistant chat** (draft). Optional validate → confirm → run stays
under collapsed Advanced.

**When to use it.** To discuss a thesis-recorded run, ask how product features
work, or draft/confirm an Assistant research plan — without mixing those jobs
into one thread.

**Related terms.** thesis, Discuss runs, Discuss results, Help / how it works,
Assistant chat, draft, Advanced, Validate executable RunSpec, Confirm validated
RunSpec, Run confirmed research, linked runs, clarification, specification
version

**Key settings / surfaces.**

| Control / surface | Meaning | Common pitfall |
|---|---|---|
| Mode selector (`Discuss runs` / `Help` / `Draft thesis`) | Chooses which channel surface is open | Modes are navigation only — histories stay isolated |
| **Discuss results** (`Discuss runs` mode) | Multi-turn Q&A on one completed run (DI recovery + digit-free expert framing) | Needs a thesis-recorded run; hash-verified evidence |
| `Help / how it works` (`Help` mode) | Allowlisted docs + capability registry | Not a second results explainer |
| `Assistant chat` (`Draft thesis` mode) | Thesis drafting only — choices + clarifications | Not for run metrics or product docs |
| `Advanced: draft, runs & compare` | Optional draft → validate → confirm → run path | Classic pages remain the primary workflow |
| `Draft research plan` (optional) | Persists an immutable specification version | `Apply` controls only stage the session draft |
| `Validate executable RunSpec` → `Confirm validated RunSpec` | Confirmation-/schema-gated | Confirm appears only after Validate succeeds **and** clarifications are clear |
| `Run confirmed research` | Executes only a **Confirmed** spec version | Apply/Draft alone never start compute |

**How to use (Assistant confirm/run path).**

1. Create or select a thesis in the sidebar.
2. Open **Draft thesis** for **Assistant chat** and/or use Advanced structured
   controls.
3. Open **Advanced: draft, runs & compare** → **Plan review**. Optionally
   **Draft research plan**, then **Validate executable RunSpec**. Resolve
   clarifications if shown, then **Confirm validated RunSpec** (Confirm lives
   under Plan review, not inside the Specifications list).
4. Open a Confirmed specification → **Run confirmed research**.
5. For completed-run questions, stay on (or open) **Discuss runs** → **Discuss
   results**. For feature how-tos, open **Help**.

**How to discuss a completed run.**

1. Record the run under a thesis (**Record and discuss this run** on Backtest, or
   run via a Confirmed Assistant specification).
2. Open Research Assistant with that thesis selected.
3. Choose mode **Discuss runs** (the default).
4. Select the completed run in the run picker.
5. Ask in the page chat box under **Discuss results**
   (placeholder: **Ask about this completed run**) — for example expectancy,
   best SL/TP, entry windows, KPIs / key metrics, costs/assumptions, exit reasons
   / extreme trades / streaks (when trade tables were recorded), or a run summary.
   Answers stay
   grounded in hash-verified evidence for that run only (see **When to use Help
   vs Discuss results** for DI overview vs specialist cues).

Classic **Discuss this run** deep-links into the same **Discuss runs** mode with
the run preselected for **Discuss results**. Discuss Q&A lives in that mode, not under Advanced.

**What it is not.**

- Draft chat does not show Help or Discuss history (channel isolation).
- Help does not invent run metrics or undocumented settings.
- Linked runs list **thesis-recorded** runs only — classic exploration without
  research mode is never listed.

**Related pages.** Classic research mode (record/discuss); USER_GUIDE how-tos
via Help.

## Research mode on classic pages

**What it is.** Classic **research mode** links a thesis on classic pages so you
can **Record and discuss this run** or **Discuss this run** without leaving the
Data → … → Backtest path.

**When to use it.** When you want classic exploration under a thesis identity
and later Discuss results in Research Assistant.

**Related terms.** research mode, Thesis research context, create and link
thesis, link thesis, Record and discuss this run, Discuss this run, recording
policy, manual record, all executions, exit research mode, identity badge

**Key settings.**

| Control | Meaning | Common pitfall |
|---|---|---|
| Setup Builder → `Thesis research context` | Create/link a thesis (optional) | Linking does **not** record a run |
| Research-mode breadcrumb | Shows thesis + recording policy | Exit research mode leaves page settings unchanged |
| `Recording policy` | `Manual — Record and discuss after a run` or `All executions — ledger every Backtest attempt` | Manual leaves exploration untracked until you record |
| **Record and discuss this run** | Attaches the current research bundle under the thesis | Needs research mode + completed artifacts |
| **Discuss this run** | Opens Assistant focused on a recorded run | Does not re-register; errors if nothing recorded yet |

**How to use.**

1. On Setup Builder, open **Thesis research context** → tabs **Create thesis** /
   **Link existing** → **Create and link thesis** or **Link thesis** (enters
   research mode).
2. Run the classic path (Data → Levels → Signals → Backtest, etc.).
3. After a completed backtest (or bundle with backtest artifacts): **Record and
   discuss this run**, or **Discuss this run** if already recorded.
4. Research Assistant opens mode **Discuss runs** with that run preselected for
   **Discuss results**. Discuss Q&A is in that mode; Advanced may also expand
   Linked research runs for diagnostics, but that is not where you ask.

**What it is not.**

- Research mode is not automatic live trading and not a substitute for Help.
- Exploratory runs without research mode never appear in Linked runs.
- Record attaches the current bundle without recomputing metrics.

**Related pages.** Research Assistant (Discuss); Research Bundles (export +
record/discuss entry).

## When to use Help vs Discuss results

**What it is.** A trust-boundary guide for choosing the right Assistant surface.

**When to use it.** Anytime you are unsure whether to ask in Help, Discuss, or
draft chat.

**Related terms.** Help vs Discuss, product help, how it works, run metrics,
best SL, expectancy, KPIs, key metrics, run summary, remediation, draft chat,
documentation-grounded, Discuss Intelligence

**Decision table.**

| Question type | Use | Do not |
|---|---|---|
| How does a page/setting work? How-to / workflow (incl. exposure policy) | **Help / how it works** | Discuss (no run packet) |
| What were my KPIs / run summary / expectancy / best SL/TP on this run? | **Discuss results** (bound run) | Help (remediates; no invented numbers) |
| What does expectancy_r / Monte Carlo mean (definition, no run digits)? | **Help** (glossary/how-to) or Discuss for packet-cited values | Mixing definition asks into invented run figures |
| Refine thesis choices / clarifications | **Assistant chat** (draft) | Help or Discuss |
| Undocumented / invented controls (e.g. fake modes) | Help must not invent UI absent from allowlisted docs (say not documented) | Fabricating UI that does not exist |

**How to use.**

1. Open Research Assistant with a thesis selected.
2. For feature how-tos: mode **Help** → **Help / how it works** → ask in the
   page chat box (placeholder: **Ask how ThesisTester works**) — examples:
   import data, Setup Builder, exposure policy, grid ranking, validation.
3. For completed-run metrics: mode **Discuss runs** → select the run → ask in
   the page chat box under **Discuss results**
   (placeholder: **Ask about this completed run**). Prefer clear overview cues
   (`KPIs`, `key metrics`, `run summary`) or specialist cues (validation /
   best SL/TP / time / Monte Carlo / overfitting / OTF / costs / assumptions).
   Mixed asks such as “KPIs and best SL/TP” return a composed grounded answer
   from both topics when evidence exists (up to three topics; broader mixes ask
   you to narrow).
4. If Help redirects you to Discuss, open **Discuss runs** for that run — do
   not expect Help to invent performance numbers.

**Discuss Intelligence (DI) cues — user-facing.**

- Overview asks (`KPIs`, `key metrics`, `run summary`, `highlights of this run`)
  return grounded `trade_summary` scalars (optional best-grid ticks when
  present). Digits stay fail-closed.
- Specialist asks (validation / WFA / OOS / grid ranking / best SL/TP / time
  buckets / Monte Carlo / overfitting / sensitivity / noise / portfolio / OTF /
  costs / exposure / assumptions) stay on-topic — Discuss does **not** silently
  substitute a KPI overview. Mixed multi-topic asks compose grounded slices when
  evidence exists (capped); over-broad mixes ask you to narrow.
- On path/digit slips, Discuss may repair once or fall back to a deterministic
  overview slice (overview asks only) or a structured missing-evidence reply —
  not a raw traceback.
- Expert framing after facts is **digit-free** interpretation (metric meaning /
  caveats). It does not invent new run numbers or trading advice.

To discuss a completed run after classic research mode: use **Record and discuss
this run** (or **Discuss this run**), then stay on Research Assistant **Discuss
runs** with that run selected.

**What it is not.**

- Help is not a second results explainer (DI recovery/overlay live in Discuss).
- Discuss is not thesis drafting and not general product docs.
- Draft chat ignores Help/Discuss history on purpose (trust boundary).

**Related pages.** Research Assistant surfaces above; classic research mode for
recording runs to discuss.
