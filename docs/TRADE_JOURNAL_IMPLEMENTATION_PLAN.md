# Trade Journal — Implementation Plan (TJ)

**Document type:** Focused implementation plan (fully scoped PRs)
**Date:** 2026-09-06 (rev 4 — clock/qty/PIT locks vs live engine)
**Status:** **TJ7 landed.** TJ8 (named-cell match + forward ledger) is next. No page yet.
**Series prefix:** **TJ** (Trade Journal). Not DA, not DI, not R21.
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1
golden-master operational spec and §4.2 per-milestone PR acceptance checklist.
**Reader:** desk owner (Edge Finder), ThesisTester bot, engine contributors.

**Inputs (desk, 2026-09-06 — stay outside git, PII):**

| File | Role |
|---|---|
| TradesViz *executions* CSV (`*_executions_export_20260906*.csv`, 1124 rows) | **Layer 1** — UTC fills, round-trip `spread_id`, `tags` / `notes` / `stop_loss` / `profit_target` |
| AMP Daily Statement PDFs: 27-MAY-26, 12-JUN-26, 23-JUN-26, 29-JUN-26 | **Layer 2** — FCM money truth (fills, fee schedule, P&S) |
| Quantower *Trades* CSV (`01052026-31072026_Trades*.csv`, 394 rows) | Cross-check only (local-clock timestamps; parked). Only source with order type (`Market`/`Limit`) |

**Does not reopen:** `simulate_trades`, signals, levels, R12/R13, DA defaults,
RS execute, SO5/SO6, AP2, Program B Run 1/Run 2 locks, Help-corpus *path* moves.
**Amends (pointer only in TJ0):** DA §8 follow-up; roadmap status row; docs index.

---

## 0. Finding (locked — verified 2026-09-06)

### 0.1 Statement

The desk has three objects. Two are enough:

- **TradesViz executions export** is the journal clock **and** the intent
  layer: UTC timestamps, one `spread_id` per round trip, and free-text
  `tags` / `notes` / `stop_loss` / `profit_target` on the trade.
- **AMP Daily Statement** is the money layer: fill list, exact fee schedule,
  realized P&S.

TradesViz **reconciles exactly** against AMP on the one overlapping day in
the batch (27-May: 40/40 fills, averages to 5 dp, gross $27.00). This is the
same-day golden the previous revision of this plan listed as desk-blocked.

Quantower is demoted. Its fills are identical to TradesViz on the one shared
day (29-May, 66/66), but its timestamps are **local machine time
(Europe/Vienna)**, it has no round-trip key, and it carries no intent. The
previous revision's timezone lock (`America/New_York`, from a `09:30:07`
fill) was wrong — that fill is the London open in Vienna time. Corrected in
§0.6.

### 0.2 TradesViz executions export — parsed 1124 rows

| Field | Observed |
|---|---|
| Columns | `date, symbol, side, currency, underlying, asset_type, price, quantity, commission, fees, stop_loss, profit_target, tags, notes, spread_id` |
| `date` | ISO-8601 with explicit `+0000` on **every** row. UTC. Second resolution |
| Broker-imported fills | **1104** rows, `asset_type=future`, `symbol=MNQM26`, `underlying=MNQ`. **14 NY session days, 2026-05-11 → 2026-06-01.** Nothing imported after 1-Jun |
| Manual entries | **20** rows, `asset_type=stock`, `symbol=MNQ`/`MES` (no month), `quantity` ∈ {0, 1, 2, 6}. All 16 tagged rows and all 16 notes live **here**, none on imported fills |
| `spread_id` | 566 groups. Futures: 546 groups; 539 clean 2-fill round trips, 5 × 4 fills, 2 × 3 fills; 0 span a session date; 3 overlap in time (scale-in) |
| `commission` / `fees` | **always 0.0** — TradesViz is not the cost source |
| `stop_loss` / `profit_target` | `N/A` on every imported fill; populated on 9 manual rows |
| `notes` | HTML with hosted `<img src="/viewfile/…">` references. Not portable; strip to text |
| Hold (futures, per spread) | p25 / median / p75 = **11 s / 24 s / 60 s**, max 24 min |
| Order type | **absent** (TradesViz executions export has no order-type column; Quantower has `Market`/`Limit`) |
| Tag vocabulary (27 tokens) | `ITR-C` 5 · `pdVAL_retest` 4 · `5m50SMA` `CTR-R` `dOpen_retest` `dVWAP` `p30VWAP` `pSettlement_retest` `pdH_SFP` 2 each · `1m9EMA` `4hVWAP` `5m21EMA` `5mCOT` `5mSFP` `APOC` `CTR` `DeltaNode` `GEX2` `ITR` `mVWAP` `p30POC` `pSettlement` `pdEQ_retest` `pdH` `pdH_RTH` `pdLow_retest` `pwVAH` 1 each |

### 0.3 AMP Daily Statement PDF — four days parsed

| Field | Observed |
|---|---|
| Confirmations | Date, FCM trade number, CME, Buy **xor** Sell (x-position), qty, `MNQ`/`MES`, month/year, price |
| Buy/Sell | Recoverable from layout; on 12-JUN 29/29 with averages and P&S **$78.00** exact |
| P&S section | FCM average-matching pairs, not chronological. Daily totals only |
| Fees | Exchange / NFA / Clearing Client / Rithmic TRF / Commission; **23-JUN adds `Liquidation Fee $2.50`** |
| Variants | 2- and 3-page; `../..` continuation; MNQ JUN, MNQ SEP, MES SEP |
| Timestamps | None (date only). PDF only — desk confirmed no CSV/XLS |

### 0.4 Cross-source reconciliation (this batch)

| NY session day | AMP fills | TradesViz fills | Quantower fills | Result |
|---|---:|---:|---:|---|
| 2026-05-27 | 40 | 40 | — | **`reconciled`** — multiset, avg L/S, gross exact |
| 2026-05-29 | — | 66 | 66 | TV ≡ QT multiset; QT clock = TV + 6 h |
| 2026-06-12 | 58 | 0 | — | `journal_missing` (TradesViz import gap) |
| 2026-06-23 | 30 | 1 manual | — | `journal_missing` |
| 2026-06-29 | 18 | 1 manual | — | `journal_missing` |
| 2026-07-03 | — | 0 | 121 | TradesViz gap |
| 2026-07-07 | — | 1 manual | 207 | TradesViz gap |

Join key across sources is **instrument + NY session date + `(price, side,
qty)` multiset**. Identifier namespaces do not overlap (AMP FCM `NUMBER`, QT
`Order ID`, TradesViz `spread_id`).

**Desk action (not a repo task):** the TradesViz broker import stopped on
2026-06-01. Until it is re-synced, every later day is `journal_missing`.
TradesViz documents Rithmic sync as manual-trigger (or R-Trader periodic CSV
→ Google-Drive sync); either keeps Layer 1 alive.

### 0.5 Cost lock (AMP, four statements)

| Component | $ / side |
|---|---:|
| Exchange | 0.35 |
| Clearing Client | 0.13 |
| Rithmic TRF | 0.10 |
| NFA | 0.02 |
| Commission | 0.02 |
| **Total** | **0.62** |

Round-turn **$1.24**, MNQ = MES. In ticks: MNQ tick = $0.50 → **2.48 ticks
per round turn**; MES tick = $1.25 → 0.99 ticks. Program B lock models
`commission_per_side=0.5` + `slippage_ticks=1`; fixed fees alone are 24%
above the lock's commission line. `Liquidation Fee` is a day-level extra,
never smeared into the per-side schedule.

### 0.6 Timezone lock (corrected)

| Source | Clock | Rule |
|---|---|---|
| TradesViz | explicit `+0000` | parse offset; convert to UTC; `session_date` = **`trading_session_date`** in `America/New_York` with `eth_start="18:00"` (`thesistester/levels/session_date.py`) — **not** the NY calendar date |
| AMP | date only | statement date = CME session date (same helper; ETH 18:00 → next calendar date) |
| Quantower | naive, **Europe/Vienna** local (verified: +6 h vs TradesViz UTC on 29-May; CEST = UTC+2, EDT = UTC−4) | if ever loaded, caller must pass `source_tz` explicitly; no default |

Fill→bar join (TJ5) fail-closes if the fill price is outside the joined 15s
bar `[low, high]`. That check is the runtime guard against any residual
clock error.

### 0.7 Tags are intent, not evidence

The tag vocabulary maps closely onto ThesisTester level tokens, but only 16
of 566 spreads are tagged and none of them are imported fills — they are
manual re-entries typed as `stock`, some with `quantity` 0 or 6. Today the
tag layer is a side-journal, not an attribute of executed fills.

The product value the desk asked for — “which levels I used as confluence
and how these levels actually lined up” — needs two things: (a) tags on the
**imported** trade (a TradesViz workflow change), and (b) a **closed
tag→token map** plus a **tag verification** step that measures the distance
from entry to each tagged level on the entry bar (TJ6). Unmapped tags are
kept, counted, and never silently dropped.

Because tags cover 3% of trades, TJ6 also does the inverse for **every**
trade: **level attribution** — which engine level tokens were within
tolerance of the entry price on the entry bar, from the levels frame the app
already computes. Tags then become the *intent* overlay on top of that
*observed* label (“you wrote `pdVAL`; the frame says entry was 3 ticks off
`pwVAH` and 22 ticks off `pdVAL`”).

### 0.8 This journal is not Program B — and the clocks differ

Median hold **24 s**, `Market` in / `Limit` out (from the QT cross-check),
10-tick scalp language in the TV brief. Program B Run 2 is `fade` @ 1min,
80/80. Different products. TJ8 may say “near this level at this time”; it
must not say “executed cell X” unless hold, risk, and trigger are compatible
with that cell's lock. Journal R-multiples default to a **declared journal
risk** (10 ticks unless overridden), never silently the 80-tick study lock.

Structural consequence: **the product the desk trades lives below the study
clock.** 36% of round trips close inside one 15s bar; the studies run at
1min. Nothing in the research corpus has tested a 24-second product. The
journal is the only instrument that makes that gap measurable; TJ5/TJ7 run
on the 15s primary and, where tick exports exist for the day, on ticks.

### 0.9 What this is not

- Not a `simulate_trades` bug or a reason to change costs on existing studies.
- Not broker/live integration (proposal §2.2 anti-roadmap).
- Not a TradesViz API client; file export only.
- Not a second TradesViz. TradesViz already ships MFE/MAE, Exit Insights /
  best-exit, time-of-day and volatility cohorts, tags v2, Monte Carlo,
  second-level replay and notes. TJ does not rebuild generic journal
  statistics (§1.2).
- Not proof of edge or of a durable leak. 546 May round trips are a format
  fixture, not a research conclusion.

### 0.10 Illustrative read of the May book (what the journal will surface)

Computed 2026-09-06 from the TradesViz export with `spread_id` FIFO, AMP
fee schedule, 10-tick declared risk, no slippage model (553 trades, 14 NY
days, MNQ only; four days carry 71% of the trades). **Illustration of the
report shape, not a finding**: n is small, one month, one contract, and the
slices below are multiple comparisons on the same data.

| Cut | n | Gross ticks / trade | Net ticks / trade | Note |
|---|---:|---:|---:|---|
| All | 553 | +1.20 | **−1.28** | gross-positive, fee-negative: cost (2.48 t) > edge (1.20 t) |
| Long / short | 422 / 131 | +2.32 / −2.40 | −0.16 / −4.88 | direction split (DA2 lens) |
| Hold < 15 s | 192 | −16.4 | −18.9 | WR 0.27 |
| Hold 15–60 s | 224 | −0.5 | −3.0 | |
| Hold 1–5 min | 109 | +14.8 | +12.3 | WR 0.68 |
| Hold > 5 min | 28 | +82.8 | +80.3 | WR 0.86 |
| NY 11:00 hour | 94 | +12.2 | +9.7 | best hour |
| NY 10:00 hour | 151 | −1.0 | −3.4 | most-traded hour |
| Days ≥ 60 trades | 4 days | — | avg day net < 0 | days < 60 trades: avg day net > 0 |
| Next trade after 3 losses | 102 | +0.2 | — | vs +1.2 baseline; WR 0.36 |
| Re-entry < 30 s after a loss | 166 | +4.4 | — | vs −3.5 for re-entry ≥ 120 s (opposite of the revenge-trading prior) |
| Direction flipped on every trade | — | −1.20 | — | tautological sign flip of the whole book — **not** the TJ7 null |

Two lessons for the design, independent of whether these numbers persist:

1. **Hold time is an outcome, not a decision.** Losers get cut fast, winners
   are held; the hold table is selection, not a “hold longer” rule. Only a
   counterfactual with a *fixed* rule applied to the same entries (TJ7) can
   separate entry quality from exit quality. This is why TJ7 is a
   first-class milestone, not a report cut.
2. **Priors must be measured, not assumed.** The revenge-trading prior
   (fast re-entry after a loss is bad) is contradicted here. The journal
   must show n and honesty framing on every slice and never moralize.

The “direction flipped” row is a one-shot negation. TJ7’s null **shuffles
existing per-session long/short labels** (preserves that day’s counts) and
reports a percentile. Do not implement the null as a global sign flip.

---

## 1. Value thesis, goals, non-goals

### 1.1 What the journal does for P&L

Realized P&L of a discretionary desk decomposes as

`Σ trades × (gross edge per trade − cost per trade) − behavioural leaks`,

and every term is currently unmeasured because fills, fees and intent live in
three unconnected files. The journal makes each term a number the desk can
act on and, critically, links each number to the research engine so that a
finding becomes a testable rule rather than a feeling. It answers eight
questions; each maps to one milestone that produces the evidence.

| # | Question the desk asks | Evidence produced | Milestone |
|---|---|---|---|
| Q1 | Am I net positive after **real** costs, per instrument-day? | AMP-reconciled net; fee ticks/trade; break-even gross/trade | TJ2–TJ4 |
| Q2 | Where does the R come from and where does it leak? | direction × NY hour × hold × day-intensity cuts, n ≥ 30 gate, honesty caption | TJ3–TJ5, TJ9 |
| Q3 | Which **levels** did I actually trade, and did my tags match reality? | level attribution on every entry bar; tag verification on tagged trades | TJ6 |
| Q4 | Is my edge in the **entry** or in the **exit**? | same entries replayed under fixed brackets (10/10, 10/20 …) with SL-first pessimism, engine cost model | TJ7 |
| Q5 | Is my direction call better than drift? | direction-shuffle null (seeded, K draws) on the realized entries; DA5 drift lens | TJ7 |
| Q6 | Would rule X have helped (cap, window, cooldown, hard stop)? | pre-registered rule applied to history → counterfactual net; then tracked forward | TJ7, TJ8 |
| Q7 | Do I trade what I researched? | named-cell match classes; product mismatch (hold / risk / trigger vs cell lock) | TJ8 |
| Q8 | Is a promoted cell working **live**? | forward ledger: adherence, live E vs backtest E, n | TJ8 |

How each becomes money:

- **Q1** sets the bar. On the May book fees are 2.48 ticks/RT against 1.20
  gross; no exit or setup work matters until gross/trade clears cost. It also
  prices frequency: every avoided coin-flip trade is +2.48 ticks.
- **Q2/Q3** direct attention. Slices are hypotheses (which hour, which side,
  which level family). Level attribution is the one cut no generic journal
  can do, because it needs the desk's own level engine and PIT frame.
- **Q4** is the single largest lever for a scalper. If entries carry edge
  under a mechanical bracket but realized exits do not, the fix is exit
  discipline (and it is cheap). If entries carry no edge under any bracket,
  no exit work helps and the desk should trade the researched product
  instead. TradesViz's best-exit hindsight cannot answer this; a rule-based
  counterfactual run with the same pessimism as the studies can.
- **Q5** protects against a drift illusion: in a trending month a long-biased
  book prints regardless of skill (DA5 lesson applied to the desk).
- **Q6** turns discipline into a tested rule. A rule is written down with a
  date, evaluated on history once, then judged forward — the same
  pre-registration posture as Program B.
- **Q7/Q8** close the research → live → research loop: promoted cells get a
  live scoreboard; live behaviour (which levels, which hours) feeds Program C
  candidate locks.

### 1.2 What ThesisTester must **not** build (TradesViz already does)

Generic P&L calendars, MFE/MAE dispersion charts, best-exit / EOD-exit
hindsight, second-level replay, note management, generic tag statistics,
Monte Carlo on realized P&L, AI coaching. The desk keeps TradesViz for those.
TJ builds only what needs the desk's engine, levels frame, cost model,
nulls, or study corpus.

### 1.3 Goals

1. Ingest TradesViz executions CSV into a typed, fail-closed `FillRecord`
   frame; separate imported fills from manual entries (TJ1).
2. Ingest AMP Daily Statement PDFs into a typed `AmpStatement` (TJ2).
3. Pair fills into `JournalTrade` via `spread_id` with qty-aware FIFO
   fallback; carry tags / notes / declared SL-TP onto the trade (TJ3).
4. Reconcile Layer 1 ↔ Layer 2 per instrument-day; refuse attribution on
   unreconciled days (TJ4).
5. Join journal entries/exits to the 15s / derived-1m clock; ticks when
   present (TJ5).
6. **Level attribution + tag verification:** nearest engine levels on the
   entry bar for every trade; closed tag→token map and distance check for
   tagged trades (TJ6).
7. **Own-entry counterfactuals:** fixed-bracket replay, direction-shuffle
   null, pre-registered rule filters — all over the desk's real entries
   (TJ7).
8. Named-cell match with explicit unmatched classes; forward ledger for
   promoted cells (TJ8).
9. Report + read-only page 17 (TJ9).

### 1.4 Non-goals (entire series)

- Any edit to `simulate_trades`, `_check_touch`, candidate sort, signals, or
  levels math. No `LEVEL_ENGINE_VERSION` bump.
- Golden regeneration.
- TradesViz / AMP / Rithmic / Quantower live API.
- Treating journal expectancy as a study rank key.
- Auto-promote, auto-Admit, Notion writes.
- Rendering or fetching TradesViz-hosted note images.
- Re-costing historical Program A/B cells onto the AMP schedule (parked).
- Rule *search* (optimising Q6 rules in-sample). Rules are declared, then
  evaluated; the code never ranks candidate rules.

---

## 2. Architecture

```
TradesViz executions CSV        AMP Daily Statement PDF
        │                                │
        ▼                                ▼
 TJ1 load_tradesviz_executions    TJ2 load_amp_statement
        │                                │
        └──────────┬─────────────────────┘
                   ▼
            TJ3 pair (spread_id → FIFO fallback) ──► JournalTrade (+tags)
                   │
                   ▼
            TJ4 reconcile_day (multiset + P&S + fees) — fail-closed
                   │
                   ▼
            TJ5 join_bars (15s clock, UTC→NY; ticks when present)
                   │
                   ├──► TJ6 attribute_levels + verify_tags (levels frame, entry bar)
                   │
                   ├──► TJ7 counterfactuals: bracket replay · direction-shuffle null · declared rules
                   │
                   └──► TJ8 match_cell (named RunSpec) + forward ledger
                   │
                   ▼
            TJ9 report / page 17 (read-only)
```

Posture is **R21-shaped**: post-trade ingest + analytics. Journal trades are
a new frame, never written into a research bundle as `simulate_trades`
output. `canonical_bundle_hash` of every existing experiment stays identical.
TJ7 is pure functions over bars/ticks plus a seeded permutation. It must
**not** call `simulate_trades`: that function enters at **next-bar open** on
1-lot candidate signals (`risk_currency` has no qty). Journal fills are
intra-bar, multi-lot, AMP-costed. Reusing it would silently change the entry
model.

Package: `thesistester/journal/` (`schema.py`, `tradesviz.py`,
`amp_statement.py`, `pair.py`, `reconcile.py`, `join.py`, `levels.py`,
`tags.py`, `counterfactual.py`, `rules.py`, `match.py`, `ledger.py`,
`report.py`). CLI: additive `python -m thesistester journal
ingest|reconcile|attribute|counterfactual|match|report` subparser (same
pattern as `study`; do not mutate `run` / `study`). Store (TJ9):
`.thesistester_store/journal/v1/` — sibling of `datasets/` / `setups/`,
**not** under `execution_artifacts/` (CAI-10 LRU only scans that subtree).

---

## 3. Locked contracts

### 3.0 Clock, qty, and PIT (apply to every later TJ PR)

These match live engine helpers. Do not re-derive them.

1. **`session_date`** = `trading_session_date(local_ts, eth_start="18:00")` after
   converting the fill to `America/New_York`. A Sunday 18:05 ET fill is Monday’s
   CME session (AMP statement date). Calendar `NY.date()` would split ETH
   evening fills onto the previous statement and break TJ4.
2. **15s timestamps are bar opens** (`:00/:15/:30/:45`,
   `thesistester/data/derive.py`). Join `open_ts <= ts < open_ts + 15s` in UTC.
   Missing covering bar → `missing_bar` (fail closed), never a silent skip.
3. **Levels live on the derived 1-minute parent**, not the 15s row
   (`docs/15s_primary_derived_1m_implementation_plan.md`). TJ6 looks up the 1m
   bar that contains the fill. **Prior/frozen** tokens (`pd*`, `pw*`, `pm*`,
   `prevSettlement`, `pRTH_*`, overnight highs after the session exists) may
   use that minute. **Developing** tokens (`dVWAP`, `APOC`, MAs, rolling
   VWAP/POC) use the **adjacent previous completed 1m bar** whose close
   is strictly before `entry_timestamp`. A gap or session start omits the
   token rather than walking back to a stale stamp. Using the current
   minute’s close is look-ahead on a 24 s median hold.
4. **Never call `compute_all_levels` from journal code.** Library kwargs
   default `apoc_enabled=False` / `session_vwap_enabled=False`; product
   `DEFAULT_LEVELS_SETTINGS` enables them. Consume an already-built frame;
   missing column → `tag_level_missing` / omit from `levels_within_tolerance`.
   `closed_level_token_set` is settings-dependent — iterate
   `frame.columns ∩ closed_level_token_set(that_frame’s settings)`.
5. **Qty.** Engine `simulate_trades` is 1-lot
   (`gross_pnl_currency = points × point_value`,
   `risk_currency = sl_ticks × tick × point_value`,
   `commission_cost = 2 × commission_per_side`). Journal is not:
   - `gross_pnl_points` = signed price difference (engine-shaped, **not × qty**)
   - `gross_pnl_currency` = `gross_pnl_points × point_value × qty`
   - `commission_cost` = AMP per-side × 2 × qty (TJ4)
   - `r_multiple` = `net_pnl_currency / (journal_risk_ticks × tick_size × point_value × qty)`
   - `net_ticks` / `fee_ticks` = currency / (`tick_size × point_value`) (qty-scaled dollar-ticks)
   Default report is per-trade dollar-ticks; optional per-contract ticks divide by qty. Never mix in one average without a caption.
6. **Tick files** are Quantower Tick-Last (`thesistester/data/quantower_ticks.py`),
   UTC on disk, Last×Volume — not bid/ask. TJ5/TJ7 tick walks use Last.
7. **Price keys** quantize to `instrument.tick_size` (MNQ/MES 0.25). Do not
   `round(price, 2)` as the recon key: 0.25 already fits two decimals, but
   averages in §3.4 are three-dp parser self-checks, not fill keys.

### 3.1 FillRecord (TJ1)

Required columns after load (additive extras allowed, never required):

`fill_id`, `source` (`tradesviz`), `source_group_id` (`spread_id`),
`instrument` (`MNQ`/`MES`), `contract_month`, `contract_year`, `side`
(`buy`/`sell`), `qty` (positive int), `price`, `timestamp` (UTC-aware),
`session_date` (`trading_session_date`, §3.0), `entry_kind` (`imported` | `manual`),
`tags` (tuple of raw tokens), `notes_text` (HTML stripped, may be empty),
`declared_stop`, `declared_target` (float or null).

`fill_id` is deterministic from source row order + (`spread_id`, timestamp,
side, price, qty). Pairing tie-break is `timestamp`, then `fill_id`.

Rules:

- `asset_type=future` → `entry_kind=imported`. Any other `asset_type` →
  `entry_kind=manual`. Manual rows are **retained** for tag/notes lineage but
  are **excluded** from pairing, recon, and P&L by default
  (`include_manual=False`). `quantity == 0` manual rows are kept with
  `qty=None` and flagged `manual_no_qty`.
- Symbol map (locked from this export; unknown patterns fail closed):

| Raw | instrument | month | year |
|---|---|---|---|
| `MNQM26` | MNQ | JUN (`M`) | 2026 |
| `MNQU26` | MNQ | SEP (`U`) | 2026 |
| `MESU26` | MES | SEP | 2026 |
| `MNQ` / `MES` (manual) | as given | null | null |

  CME month codes `F G H J K M N Q U V X Z`; two-digit year `20YY`.
- `date` must carry an explicit offset; a naive value fails closed.
- `commission` / `fees` are read and **discarded** (must not be trusted; they
  are 0 in the desk export). Cost comes from TJ2.
- `stop_loss` / `profit_target`: `N/A` → null; numeric → float.
- `tags`: split on `,`, strip, drop empties, keep order and case as written.
- `notes`: strip HTML to text; `<img>` becomes the literal token
  `[image]`; never fetch.

Profile token: `tradesviz_executions`. **No autodetect.**

### 3.2 AmpStatement (TJ2)

Parse **Trades Confirmations** only for the fill list. P&S section stored as
`ps_pairs` + `ps_usd` for recon, never as journal trades. **Open Positions**,
journal, delivery, expiration, and exercise blocks are ignored — they reuse
the confirmation-row layout and must not enter `fills` or `ps_pairs`.

Side from layout: the `1` in the BUY vs SELL column (gap heuristic verified on
four PDFs). A parse that disagrees with printed `AVERAGE LONG` /
`AVERAGE SHORT` fails closed.

Fee lines: known names `{Exchange, NFA, Clearing Client, Rithmic TRF,
Commission, Liquidation Fee}`. Unknown fee names fail closed.
`per_side_schedule` from the five standard lines only; `Liquidation Fee`
stays `day_fees_extra`. Printed `TOTAL COMMISSION & FEES` must equal the
sum of those lines (1 cent). Distinct `P&S USD` totals fail closed.

Confirmation `TOTAL` buy/sell counts must match confirmation qty sums.
A date + FCM-number row that is not `MNQ`/`MES` CME Future fails closed
(no silent drop). Confirmation dates must match the statement date; P&S
row dates may predate it (prior-day open / liquidation). Price must be
finite and `> 0`.

Two-stage: `extract_amp_pdf_text(path) -> str` (pdfplumber layout) then
`parse_amp_statement_text(text) -> AmpStatement`. CI owns the text parser
against **redacted** text fixtures; PDF extraction is tested on a synthetic
PDF only.

### 3.3 JournalTrade (TJ3)

Pairing order:

1. **`spread_id` grouping** (imported fills). A group whose signed qty nets to
   zero and has exactly one open side becomes trades via qty-aware FIFO
   *inside the group* (a `qty=2` cover against two 1-lot opens emits two
   trades, same exit fill, distinct `lot_seq`).
2. A group that does not net to zero, or that opens both sides, is
   FIFO-matched **inside the group** first (`pair_method=fifo_fallback`) so a
   covering fill cannot be stolen by another `spread_id` on the same
   session. Residual lots, and fills without `spread_id`, then FIFO-match
   per `(instrument, contract, session_date)`.

Direction = side of the opening lot. Tags / notes / declared SL-TP of the
group are copied onto every trade in the group.

Engine-shaped columns, systematic-only fields null:

| Engine column | Journal |
|---|---|
| `trade_id` | `jt:{spread_id}:{lot_seq}` |
| `direction` | `long` / `short` |
| `entry_timestamp` / `exit_timestamp` | UTC |
| `entry_price` / `exit_price` | fill prices |
| `gross_pnl_points` / `gross_pnl_currency` | signed Δprice; currency = points × point value × **qty** (§3.0) |
| `commission_cost` | AMP per-side × 2 × **qty** (TJ4 supplies; null before) |
| `slippage_cost` | null (no model declared; do not invent 1 tick) |
| `net_pnl_currency` | gross − commission − `day_fee_allocation` |
| `r_multiple` | net / (`journal_risk_ticks` × tick × point value × **qty**). Default **10**; if `declared_stop` present, `r_multiple_declared` is also emitted |
| `stop_price` / `target_price` | `declared_stop` / `declared_target` (intent, not executed bracket) |
| `hold_seconds` | exit − entry, seconds (the journal's primary duration; `bars_held` is secondary) |
| `bars_held`, `mae_*`, `mfe_*`, `zone_*`, `signal_id`, `trigger` | null until TJ5–TJ8 |
| `status` | `closed`; unpaired leftover → `open` |

Point values MNQ $2 / MES $5; tick 0.25. Derived, always emitted:
`fee_ticks` (= commission / tick value) and `net_ticks`.

### 3.4 Reconciliation (TJ4)

Per `(session_date, instrument)`:

1. Journal fill multiset `(quantize(price, tick_size), side, qty)` vs AMP confirmations
   (imported fills only).
2. Fill counts equal.
3. Recomputed AMP averages equal printed averages (parser self-check).
4. Journal gross $ vs AMP `P&S` $ (tolerance 1 cent).
5. Fee total vs sum of fee lines.

Statuses: `reconciled` | `journal_missing` | `amp_missing` |
`multiset_mismatch` | `pnl_mismatch`. TJ6–TJ8 refuse days not `reconciled`
unless `allow_unreconciled=True` (default false; UI shows the flag).

Day-level extra fees allocate as `day_fee_allocation` equally across that
instrument-day's **closed imported** trades (documented, not hidden in
`commission_cost`). Open leftovers and manual rows stay null so day extra
cannot be diluted out of realized net.

**Golden:** 27-May (redacted) is the TJ4 overlap golden — 40 fills, avg long
`30132.87500`, avg short `30133.55000`, gross `$27.00`.

### 3.5 Bar join (TJ5)

Clock is the existing 15s primary (`ingestion_mode: 15s_primary_derive_1m`).
Join `timestamp` → **bar open** with `open_ts <= ts < open_ts + 15s` after
converting both to UTC (§3.0). Fill price must satisfy `low <= price <= high`;
else `price_outside_bar`. No covering bar → `missing_bar`.

`bars_held` counts completed 15s bars strictly between entry and exit. If
`bars_held == 0`, `mae_points` / `mfe_points` stay null with
`excursion_unavailable`. Do not fake MAE from the entry bar's unused range
(that range includes pre-fill ticks).

**Tick resolution (optional):** when the loaded session has a Tick-Last series
for that day (`thesistester/data/quantower_ticks.py`, UTC Last prints),
`join_resolution=tick` and excursions/counterfactuals walk prints with
`ts > entry_timestamp`. Resolution is stamped on every derived row
(`resolution` ∈ `15s` | `tick`); rows of different resolution are never
averaged together without the caption saying so.

Contract month vs the continuous 15s series: stamp `contract_month`; a Jun
fill on a Sep-rolled series is `roll_mismatch` unless R7 roll metadata covers
that day.

### 3.6 Level attribution and tag verification (TJ6)

**Level attribution (all trades).** On the **derived 1-minute parent** that
contains the fill (§3.0), for every token in
`frame.columns ∩ closed_level_token_set(frame_settings)` with a non-null
value: `level_distance_ticks = (entry_price − level_value) / tick`. Frozen
tokens use that minute; developing tokens use the adjacent previous
completed 1m bar whose close is strictly before the fill (a gap omits
the token).
Emit `levels_within_tolerance` (tokens with `|distance| ≤ level_tolerance_ticks`,
default **10**, sorted by |distance|), `nearest_level_token`,
`nearest_level_distance_ticks`, and `level_context` ∈ `at_level` |
`between_levels` | `no_frame`. Consumes the frame the Data/Levels page or R18
already produced; recomputes nothing; no write to `results/studies/`.
Default 10 ticks is the stop width of this scalper — `levels_within_tolerance`
is “nearby tokens”, not “the level you meant”.

**Closed tag→token map** (`journal/tags.py`, data not code; unknown tag →
`unmapped`, kept and counted):

| Tag (as written) | Engine token (`thesistester/levels/catalog.py`) | Class |
|---|---|---|
| `pdH`, `pdLow`, `pdEQ` | `pdHigh`, `pdLow`, `pdEQ` | level |
| `pdH_RTH` | `pRTH_High` | level |
| `pdVAL`, `pwVAH` | `pdVAL`, `pwVAH` (tick-gated, TV3; absent without ticks → `tag_level_missing`) | level |
| `dVWAP`, `mVWAP` | `dVWAP`, `mVWAP` | level |
| `4hVWAP` | `VWAP_rolling_4h` | level |
| `p30VWAP` | `prev30mVWAP` | level |
| `APOC`, `pSettlement`, `dOpen` | `APOC`, `prevSettlement`, `dOpen` | level |
| `p30POC` | — (no engine token; parked) | `unmapped` |
| `5m21EMA`, `5m50SMA`, `1m9EMA` | `EMA_21_5min`, `SMA_50_5min`, `EMA_9_1min` | confirm |
| suffix `_retest`, `_SFP`, `_RTH` | stripped into `qualifier`; `_RTH` only re-maps for `pdH` | qualifier |
| `ITR`, `ITR-C`, `CTR`, `CTR-R`, `DeltaNode`, `GEX2`, `5mCOT`, `5mSFP` | — | context (never a level) |

The map is frozen against `closed_level_token_set` at TJ6 time; a mapped
token that is not in the set **under `DEFAULT_LEVELS_SETTINGS`** fails the
TJ6 test suite (`EMA_9_1min` / `SMA_50_5min` / `EMA_21_5min` /
`VWAP_rolling_4h` / `prev30mVWAP` / `mVWAP` / `APOC` are in that product
set). Exact-tag rows win before qualifier stripping (`pdH_RTH` → `pRTH_High`,
not `pdHigh` + `_RTH`). The table is the desk vocabulary observed in this
export; the desk owns additions, the repo owns the map.

**Tag verification (tagged trades).** Per level-class tag:
`tag_distance_ticks`, `tag_aligned = |distance| ≤ tag_tolerance_ticks`
(default **10**), `tag_level_missing` when the token is absent at that bar;
trade-level `tag_alignment` ∈ `all_aligned` | `partial` | `none_aligned` |
`unverifiable`. **Intent vs observed:** `intent_mismatch=True` when no tagged
level is within tolerance but `levels_within_tolerance` is non-empty (the
desk named one level, the frame says another was at hand).

### 3.7 Own-entry counterfactuals (TJ7)

All three take the reconciled `JournalTrade` frame + TJ5 bars/ticks. None
calls `simulate_trades`; none touches research bundles. Output is a new
frame `journal_counterfactuals.parquet` keyed by `trade_id × cf_id`.

**(a) Fixed-bracket replay.** For each trade and each declared bracket
`(sl_ticks, tp_ticks, max_hold_seconds)` in `brackets` (default
`[(10,10,None), (10,20,None), (20,20,None)]`, session end as the hard time
stop): walk **forward from the fill**, not from a 1m next-open.

- **Tick resolution:** prints with `ts > entry_timestamp` in Last order.
- **15s resolution:** do **not** use the entry bar’s full H/L (pre-fill range).
  Start at the **next** 15s open. Same-bar both-hit on later bars is **SL
  first** (engine `sl_first` pessimism only; do not import `simulate_trades`).

Emit `cf_exit_price`, `cf_exit_reason` ∈ `tp` | `sl` | `time_stop` |
`session_end` | `unresolved`, `cf_gross_ticks`, `cf_net_ticks` (AMP fees
applied, qty-scaled §3.0). Aggregate per bracket: `Σ cf_net_ticks − Σ net_ticks` =
**exit-rule delta**. Positive delta = the mechanical rule beats the realized
exits on the same entries (exit leak); negative = the desk's exits add value.
`entry_edge_flag` = best-bracket `cf_net_ticks` mean > 0 with n ≥ 30 **per
resolution**. Caption must say three brackets were looked at (not a single
pre-registered test). Never mix 15s and tick rows in that mean.

**(b) Direction-shuffle null.** Hold entry times, prices, qty, and each trade's
own exit path fixed (realized exit **and** each bracket). **Permute the existing
`direction` labels within `session_date`, preserving that day’s long/short
counts** (shuffle the label vector; do not resample 50/50 — the May book is
~76% long). Seeded RNG (`seed` recorded; K default 1000). Report the realized
`Σ gross_ticks` percentile inside the null distribution
(`direction_null_pct`). Reuses the R15/DA5 presentation grammar (vs-random,
drift-conditioned). A high percentile says the *which-way* call carries
information beyond the day’s mix; ~50 says it does not. This is not the
global sign-flip in §0.10.

**(c) Declared rule filters.** A `JournalRule` is data (YAML/dict), never
searched: `name`, `declared_on` (date, required), and filters from a closed
set — `trade_window_ny` (`HH:MM-HH:MM`), `max_trades_per_day`,
`cooldown_seconds_after_loss`, `stop_after_k_consecutive_losses`,
`daily_loss_stop_ticks`, `hard_stop_ticks` (applies the (a) SL path to
realized exits). Evaluation drops/alters trades in time order and emits
`rule_net_ticks`, `trades_removed`, `rule_delta_ticks`. Trades entered
**before** `declared_on` are `in_sample`; after are `forward`. The report
shows both columns and never a single blended number.

Honesty: every TJ7 table carries n, resolution, seed, brackets and the line
“counterfactuals assume fills at the bar/tick price; no slippage model.”

### 3.8 Named-cell match and forward ledger (TJ8)

**Match.** Input: a **named** completed cell (bundle path or promoted
RunSpec), never the Observatory corpus. Match when all hold: same instrument
and direction; `|Δentry| ≤ match_window` (default 60 s); journal entry within
`match_ticks` (default 8) of the systematic zone or theoretical entry.
Classes: `executed_cell` | `near_level` | `discretionary_only` |
`systematic_unfilled`. `executed_cell` additionally requires hold/risk
compatibility with the cell lock (`hold_seconds` within the cell's bar clock
× `bars_held` band; `journal_risk_ticks` within ±50% of the cell's SL).
Otherwise `product_mismatch` with the failing dimension named. Never
re-ranks `results_index`.

**Forward ledger.** For each promoted cell the desk declares as “trading
live” (`live_since` date), per session_date: systematic signals, journal
trades in each match class, adherence = `executed_cell / (executed_cell +
systematic_unfilled)`, live net ticks vs cell backtest expectancy in the same
units, cumulative n. Read-only over ingested artifacts; no writes to the
promotion registry.

### 3.9 PII and fixtures

Desk exports contain legal name, address, account id, hosted-image links.
**Do not commit them.** Committed fixtures are redacted text extracts and
synthetic CSV/PDF that preserve columns and layout. Tests assert format
contracts (27-May averages, fee lines, `spread_id` 4-fill group, manual
`stock` rows, `+0000` offset), not the desk's P&L.

---

## 4. Milestone table

| Milestone | Intent | Production code |
|---|---|---|
| **TJ0** | Plan lock + evidence + contracts (this PR) | none |
| **TJ1** | `tradesviz_executions` loader + `FillRecord` (imported vs manual) | `journal/tradesviz.py` + tests |
| **TJ2** | AMP PDF → text → `AmpStatement` | `journal/amp_statement.py` + `pdfplumber` dep + tests |
| **TJ3** | `spread_id` pairing + FIFO fallback → `JournalTrade` (+tags, `fee_ticks`, `hold_seconds`) | `journal/pair.py` + schema |
| **TJ4** | Daily recon + CLI `journal reconcile` + 27-May redacted golden | `journal/reconcile.py` |
| **TJ5** | 15s/1m join; tick resolution when present | `journal/join.py` |
| **TJ6** | Level attribution (all trades) + tag→token map + tag verification + CLI `journal attribute` | `journal/levels.py`, `journal/tags.py` |
| **TJ7** | Bracket replay + direction-shuffle null + declared rules + CLI `journal counterfactual` | `journal/counterfactual.py`, `journal/rules.py` |
| **TJ8** | Named-cell match + forward ledger + CLI `journal match` | `journal/match.py`, `journal/ledger.py` |
| **TJ9** | Report + page 17 + USER_GUIDE H2 + HC allowlist | `pages/17_Journal.py` |

Do not reorder TJ1–TJ4. TJ5 may start once TJ3 exists. TJ6 and TJ7 need
TJ5 and are independent of each other. TJ8 needs TJ4 + TJ5. TJ9 last.
Quantower loader is **parked** (would need an explicit `source_tz`; the only
reason to unpark is the order-type column for a Market-vs-Limit entry cut).

---

## 5. Per-milestone acceptance

### TJ0 — Plan lock (this PR)

- [x] Evidence from TradesViz + four AMP PDFs + Quantower cross-check in §0.
- [x] Value thesis (§1.1), non-duplication list (§1.2), May-book illustration
      with endogeneity caveat (§0.10).
- [x] Roadmap row + section, docs index, DA §8 pointer, AGENT_GUIDE one-liner.
- [x] No `thesistester/` production edits. No goldens touched.
- [x] Docs-only. Do not freeze a suite skip. Golden + USER_GUIDE-structure
      tests must stay green; do not cite a pre-existing red test as a TJ0 pass.

### TJ1 — TradesViz loader

- [x] Explicit profile. Offset required. `asset_type` → `entry_kind`.
- [x] Symbol table §3.1; unknown → `ValueError`.
- [x] `session_date` uses `trading_session_date` / `eth_start="18:00"` (ETH 18:05
      ET fixture → next calendar date).
- [x] `commission` / `fees` discarded with a test asserting they are not used.
- [x] Tags split/preserved; notes HTML-stripped with `[image]` token.
- [x] Fixture: synthetic CSV with MNQM26 imports, a 4-fill `spread_id`, a manual
      `stock` row with tags + SL/TP, a `quantity=0` manual row.
- [x] ISO-8601 offset lock (reject `MM-DD-YYYY` / named `UTC`); imported fills
      require a CME contract symbol; `asset_type` stripped; price finite `> 0`.
      Late-ETH after UTC midnight (22:30 ET) stays on the next session date.

### TJ2 — AMP statement parser

- [x] Confirmations vs P&S split; side via layout; averages self-check.
- [x] `Liquidation Fee` kept extra; unknown fee fails.
- [x] Redacted text fixtures: MNQ JUN 3-page, MNQ SEP 2-page, MES SEP 2-page.
- [x] `pdfplumber` pinned in `pyproject.toml` / `requirements.txt`; import
      confined to `journal/amp_statement.py`.
- [x] Review: unknown confirmation/P&S roots fail closed; fee lines must
      sum to printed total; distinct `P&S USD` fail; confirmation `TOTAL`
      qty self-check; P&S may predate statement date; price `> 0`; invalid
      calendar dates are `JournalIngestError`.

### TJ3 — Pair

- [x] `spread_id` clean 2-fill, 4-fill scale-in, non-netting group → FIFO
      inside the group first, leftover → session FIFO / `open`. Interleaved
      3-fill groups do not steal each other's cover. Side / qty / price /
      `entry_kind` / mixed-contract groups fail closed.
- [x] Tags/notes/declared SL-TP propagate; `r_multiple_declared` emitted only
      when `declared_stop` present.
- [x] `journal_risk_ticks` keyword-only, default 10. `r_multiple` denominator
      includes **qty**. `fee_ticks` / `net_ticks` / `hold_seconds` emitted. No
      `simulate_trades` call.

### TJ4 — Reconcile

- [x] **27-May redacted golden** (`reconciled`, exact numbers §3.4).
- [x] `journal_missing` (AMP 12-Jun pattern) and `amp_missing` covered with
      synthetic dates.
- [x] CLI writes `reconcile.json` + `journal_trades.parquet` under an explicit
      `--output-dir`. No write into `results/studies/`.
- [x] Review: recon fill multiset + journal gross stay imported-only
      (`include_manual` is pairing-only); missing / non-integer imported qty
      fails closed; non-finite gross is `pnl_mismatch`; `day_fee_allocation`
      splits across closed imported trades so leftover opens cannot dilute
      day extra fees; AMP costs do not land on manual rows.

### TJ5 — Join

- [x] Uses already-loaded `data` / `subtimeframe_data`; UTC-safe **bar-open** join.
- [x] `price_outside_bar`, `missing_bar`, `excursion_unavailable`, `roll_mismatch` tested.
- [x] Tick path: Last prints with `ts > entry_timestamp`; same trade joined at `15s`
      and `tick` yields identical 1m parent and stamped `resolution`; no
      cross-resolution averaging.
- [x] No level-value edits; no `LEVEL_ENGINE_VERSION` bump; no `compute_all_levels`.

### TJ6 — Level attribution + tag verification

- [x] Attribution on a hand-built **1m** levels frame: `at_level`, `between_levels`,
  `no_frame`; developing token uses previous completed minute; tolerance
  keyword-only default 10.
- [x] Map is data (YAML/dict), unit-tested against
  `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`.
- [x] `unmapped` tags counted, never dropped; exact-tag before qualifier strip.
- [x] Alignment classes + `intent_mismatch` tested (aligned / partial / missing
  token / tagged-A-but-at-B).
- [x] Docs: intent ≠ evidence; alignment is a distance check, not a trigger.

### TJ7 — Own-entry counterfactuals

- [x] Bracket replay: synthetic bar path where TP and SL touch in the same
  **post-entry** bar resolves to `sl`; entry-bar H/L is not used at 15s; tick
  path resolves by Last order after the fill; `session_end` and `unresolved`
  covered. Fees applied from TJ4, qty-scaled.
- [x] Direction-shuffle null: fixed seed reproduces the identical percentile;
  permutation is within `session_date` **and preserves that day’s long/short
  counts**; K keyword-only.
- [x] Rules: each filter type unit-tested; `declared_on` required (missing →
  `ValueError`); `in_sample` vs `forward` split never blended.
- [x] No RNG anywhere except the null; seed in the artifact and the caption.
- [x] Docs: `METRICS_GLOSSARY` entries `exit_rule_delta`, `entry_edge_flag`,
  `direction_null_pct`, `rule_delta_ticks`; `ASSUMPTIONS` (no slippage in
  counterfactuals; SL-first on bars).

### TJ8 — Match + ledger

- Requires a hash-verified bundle or RunSpec path. Corpus-wide matching is
  out (do not unpark SO6).
- `product_mismatch` names the failing dimension; `executed_cell` requires
  hold/risk compatibility.
- Ledger is derived from artifacts; a test asserts no write to the promotion
  registry.
- Does not modify `STUDY_INDEX_KEYS` or `R18_INDEX_METRIC_KEYS`.

### TJ9 — UX

- New page **17 · Journal** (`pages/17_Journal.py`), read-only over ingested
  artifacts. No in-process `run_experiment` / `run_study`; no classic session
  hydrate. Filename `17_` sorts after Observatory `16_`.
- Sections follow Q1–Q8 in order; every table shows n, resolution, recon
  status, and hides slices with n < 30 behind an explicit toggle.
- USER_GUIDE new H2 exact title **`Journal`**, inserted after **Study
  Observatory** and before **When to use Help vs Discuss results**. Same PR
  amends **all** H2 gates: `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` §6.1,
  `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` §7.1.4,
  `thesistester/assistant/help_corpus.py` `_USER_GUIDE_SECTIONS`,
  `tests/test_assistant_user_guide_structure.py` `REQUIRED_USER_GUIDE_H2S`.
  Omitting any of those fails CI. This is HC maintenance, not a new HC series.
- Honesty caption: journal ≠ study cell; fees from AMP; TradesViz P/L ignored;
  tags are trader intent; hold-time cuts are outcome-conditioned;
  counterfactuals carry no slippage.

---

## 6. Regression-safety envelope (every TJ PR)

| Rule (§4) | How TJ satisfies it |
|---|---|
| Additive-only engine | **Zero** engine/signal/level edits. Journal is a new package |
| Golden-master | No existing golden regeneration. New journal fixtures only (redacted) |
| Opt-in | No journal code on the default research path. CLI/page are new entry points |
| Schema-versioned persistence | `journal/v1`; readers tolerate missing recon/attribution/counterfactual/match files |
| Bundle hash neutrality | Journal never writes into research bundles |
| PIT | TJ5–TJ7 use already-emitted bars/ticks/levels; no new level series. Developing levels read the adjacent previous 1m bar whose close is strictly before the fill (a gap omits the token). TJ7 15s walk starts at the next 15s open. Journal never calls `simulate_trades` or `compute_all_levels` |
| Determinism | Pairing is `spread_id` + time + `fill_id` tie-break. The only RNG is the TJ7 null, seeded, seed persisted; shuffle preserves per-session direction counts |
| Same-PR docs | Each PR lists its doc edits; honesty/glossary/architecture only when true |
| PII | Desk exports stay outside git |

---

## 7. Docs each later PR must touch

| PR | Docs |
|---|---|
| TJ0 | This file; `ENGINEERING_ROADMAP.md` status + section; `docs/README.md`; DA §8; `AGENT_GUIDE.md` |
| TJ1 | `ARCHITECTURE.md` (journal package); `ASSUMPTIONS` (TradesViz P/L unused; manual rows excluded by default) |
| TJ2 | `ASSUMPTIONS` (AMP PDF is the fee SoT) |
| TJ3–TJ4 | `METRICS_GLOSSARY.md` (`journal` expectancy, `fee_ticks`, `reconciled`, `r_multiple_declared`); `ASSUMPTIONS` (spread vs FIFO vs P&S) |
| TJ5 | `POINT_IN_TIME_GUARANTEES.md` (fill→bar/tick join; no entry-bar lookahead); `ARCHITECTURE` session keys |
| TJ6 | `METRICS_GLOSSARY.md` (`level_context`, `tag_alignment`, `intent_mismatch`); `ASSUMPTIONS` (intent ≠ evidence; developing vs frozen lookup) |
| TJ7 | `METRICS_GLOSSARY.md` (`exit_rule_delta`, `entry_edge_flag`, `direction_null_pct`, `rule_delta_ticks`); `ASSUMPTIONS` (no slippage; SL-first on post-entry bars; rules declared not searched; shuffle preserves counts). There is no `HONESTY_FRAMING.md` — do not create one |
| TJ8 | `ASSUMPTIONS` (match classes, `product_mismatch`, ledger adherence) |
| TJ9 | `USER_GUIDE.md` H2 `Journal`; HC §6.1; RQ §7.1.4; `_USER_GUIDE_SECTIONS`; structure test; `ARCHITECTURE` page 17 |

---

## 8. Desk workflow (not repo tasks, but the feature is worthless without them)

1. Keep the TradesViz broker import alive (Rithmic manual sync or R-Trader
   periodic CSV → Google-Drive sync). Dead since 2026-06-01.
2. Tag the **imported** trade, not a manual re-entry. Use level tokens from
   the §3.6 map as tags; keep context tags (`ITR`, `CTR`, …) separate.
3. Export executions weekly; drop the file and the week's AMP PDFs into the
   journal input folder (outside git).
4. Write Q6 rules down with a date **before** looking at their history.
5. Optional: export the day's Quantower tick file when a Market-vs-Limit or
   tick-resolution read is wanted.

---

## 9. Parked / follow-ups

- Quantower Trades loader (needs explicit `source_tz=Europe/Vienna`; only
  product need is the order-type column).
- TradesViz *trades* (aggregated) export as an alternative to executions.
- Re-cost Program B cells onto the AMP $1.24 RT schedule (separate series).
- A 15s / tick-clock study lane for the scalp product the desk actually
  trades (§0.8) — Program C or a new lane, decided after TJ7 says whether
  the entries carry edge under a mechanical bracket.
- Program C conditional locks (ToD + OTF) — after Run 2 readout; TJ6 level
  attribution is a candidate source of the level list.
- AP2 (blocked on a Quantower APOC oracle).
- Journal as an R21 portfolio `setup_id` (after TJ5 bar indices exist).
- Tag vocabulary governance (desk-owned list; repo holds the map).
- Entry-time jitter null (shift entries ±k bars) as a second TJ7 null once
  the direction null has a reader.

---

## 10. Agent prompt — TJ1 (next PR)

```text
You are implementing TJ1 from docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md
in the ThesisTester repo. Read §0, §1, §2, §3.0, §3.1, §5 TJ1, and §6 in full
before writing code.

Hard rules:
- Regression-safe per docs/ENGINEERING_PROPOSAL.md §4: additive,
  keyword-only, default = legacy. Do not edit simulate_trades,
  _check_touch, the ["long","short"] loop, or any golden fixture.
- Scope is TJ1 only (TradesViz executions CSV → FillRecord, imported vs
  manual). If you need AMP PDF, pairing, bar join, level attribution,
  counterfactuals, or a Streamlit page, stop and say so.
- Do not commit the desk's TradesViz CSV, AMP PDFs, or Quantower CSV
  (PII). Build synthetic fixtures that preserve columns: MNQM26 imports
  with +0000 offsets, a 4-fill spread_id, a manual asset_type=stock row
  with tags + stop_loss/profit_target, and a quantity=0 manual row.
- commission/fees columns must be read and discarded; add a test.
- Run `python3 -m pytest -q` before and after; both green. Do not skip a
  failing test as “pre-existing” unless it is red on this PR’s `main` and
  you name the node. Run the golden tests and paste their output in the PR
  body.
- Update the TJ1-listed docs in the same PR. Add a "Regression safety"
  paragraph to the PR body.
- Series code is TJ.
```
