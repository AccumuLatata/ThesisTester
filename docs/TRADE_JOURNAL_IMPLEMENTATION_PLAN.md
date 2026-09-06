# Trade Journal — Implementation Plan (TJ)

**Document type:** Focused implementation plan (fully scoped PRs)
**Date:** 2026-09-06 (rev 2 — TradesViz replaces Quantower as Layer 1)
**Status:** **TJ0 locked.** No production journal code has landed.
**Series prefix:** **TJ** (Trade Journal). Not DA, not DI, not R21.
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1
golden-master operational spec and §4.2 per-milestone PR acceptance checklist.
**Reader:** desk owner (Edge Finder), ThesisTester bot, engine contributors.

**Inputs (desk, 2026-09-06 — stay outside git, PII):**

| File | Role |
|---|---|
| TradesViz *executions* CSV (`*_executions_export_20260906*.csv`, 1124 rows) | **Layer 1** — UTC fills, round-trip `spread_id`, `tags` / `notes` / `stop_loss` / `profit_target` |
| AMP Daily Statement PDFs: 27-MAY-26, 12-JUN-26, 23-JUN-26, 29-JUN-26 | **Layer 2** — FCM money truth (fills, fee schedule, P&S) |
| Quantower *Trades* CSV (`01052026-31072026_Trades*.csv`, 394 rows) | Cross-check only (local-clock timestamps; parked) |

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

### 0.5 Cost lock (AMP, four statements)

| Component | $ / side |
|---|---:|
| Exchange | 0.35 |
| Clearing Client | 0.13 |
| Rithmic TRF | 0.10 |
| NFA | 0.02 |
| Commission | 0.02 |
| **Total** | **0.62** |

Round-turn **$1.24**, MNQ = MES. Program B lock models
`commission_per_side=0.5` + `slippage_ticks=1`; fixed fees alone are 24%
above the lock's commission line. `Liquidation Fee` is a day-level extra,
never smeared into the per-side schedule.

### 0.6 Timezone lock (corrected)

| Source | Clock | Rule |
|---|---|---|
| TradesViz | explicit `+0000` | parse offset; convert to UTC; `session_date` = NY date |
| AMP | date only | statement date = NY session date |
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

### 0.8 This journal is not Program B

Median hold **24 s**, `Market` in / `Limit` out (from the QT cross-check),
10-tick scalp language in the TV brief. Program B Run 2 is `fade` @ 1min,
80/80. Different products. TJ7 may say “near this level at this time”; it
must not say “executed cell X” unless hold, risk, and trigger are compatible
with that cell's lock. Journal R-multiples default to a **declared journal
risk** (10 ticks unless overridden), never silently the 80-tick study lock.

### 0.9 What this is not

- Not a `simulate_trades` bug or a reason to change costs on existing studies.
- Not broker/live integration (proposal §2.2 anti-roadmap).
- Not a TradesViz API client; file export only.
- Not proof of edge or of a durable leak. 546 May round trips are a format
  fixture, not a research conclusion.

---

## 1. Goals / non-goals

**Goals**

1. Ingest TradesViz executions CSV into a typed, fail-closed `FillRecord`
   frame; separate imported fills from manual entries (TJ1).
2. Ingest AMP Daily Statement PDFs into a typed `AmpStatement` (TJ2).
3. Pair fills into `JournalTrade` via `spread_id` with qty-aware FIFO
   fallback; carry tags / notes / declared SL-TP onto the trade (TJ3).
4. Reconcile Layer 1 ↔ Layer 2 per instrument-day; refuse attribution on
   unreconciled days (TJ4).
5. Join journal entries/exits to the 15s / derived-1m clock (TJ5).
6. **Tag verification:** closed tag→token map; per tagged level, distance
   from entry on the entry bar; alignment classes (TJ6).
7. Named-cell counterfactual match with explicit unmatched classes (TJ7).
8. Report + read-only page 17 (TJ8).

**Non-goals (entire series)**

- Any edit to `simulate_trades`, `_check_touch`, candidate sort, signals, or
  levels math. No `LEVEL_ENGINE_VERSION` bump.
- Golden regeneration.
- TradesViz / AMP / Rithmic / Quantower live API.
- Treating journal expectancy as a study rank key.
- Auto-promote, auto-Admit, Notion writes.
- Rendering or fetching TradesViz-hosted note images.
- Re-costing historical Program A/B cells onto the AMP schedule (parked).

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
            TJ5 join_bars (15s clock, UTC→NY)
                   │
                   ├──► TJ6 verify_tags (tag→token map; entry-bar level distance)
                   │
                   └──► TJ7 match_counterfactual (named RunSpec only)
                   │
                   ▼
            TJ8 report / page 17 (read-only)
```

Posture is **R21-shaped**: post-trade ingest + analytics. Journal trades are
a new frame, never written into a research bundle as `simulate_trades`
output. `canonical_bundle_hash` of every existing experiment stays identical.

Package: `thesistester/journal/` (`schema.py`, `tradesviz.py`,
`amp_statement.py`, `pair.py`, `reconcile.py`, `join.py`, `tags.py`,
`match.py`, `report.py`). CLI: `python -m thesistester journal
ingest|reconcile|verify-tags|report`. Store (TJ8):
`.thesistester_store/journal/v1/` — user-owned, never evicted by CAI-10.

---

## 3. Locked contracts

### 3.1 FillRecord (TJ1)

Required columns after load (additive extras allowed, never required):

`fill_id`, `source` (`tradesviz`), `source_group_id` (`spread_id`),
`instrument` (`MNQ`/`MES`), `contract_month`, `contract_year`, `side`
(`buy`/`sell`), `qty` (positive int), `price`, `timestamp` (UTC-aware),
`session_date` (NY date), `entry_kind` (`imported` | `manual`),
`tags` (tuple of raw tokens), `notes_text` (HTML stripped, may be empty),
`declared_stop`, `declared_target` (float or null).

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
`ps_pairs` + `ps_usd` for recon, never as journal trades.

Side from layout: the `1` in the BUY vs SELL column (gap heuristic verified on
four PDFs). A parse that disagrees with printed `AVERAGE LONG` /
`AVERAGE SHORT` fails closed.

Fee lines: known names `{Exchange, NFA, Clearing Client, Rithmic TRF,
Commission, Liquidation Fee}`. Unknown fee names fail closed.
`per_side_schedule` from the five standard lines only; `Liquidation Fee`
stays `day_fees_extra`.

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
2. A group that does not net to zero, or fills without `spread_id`, fall to
   **qty-aware FIFO per `(instrument, contract, session_date)`** and are
   flagged `pair_method=fifo_fallback`.

Direction = side of the opening lot. Tags / notes / declared SL-TP of the
group are copied onto every trade in the group.

Engine-shaped columns, systematic-only fields null:

| Engine column | Journal |
|---|---|
| `trade_id` | `jt:{spread_id}:{lot_seq}` |
| `direction` | `long` / `short` |
| `entry_timestamp` / `exit_timestamp` | UTC |
| `entry_price` / `exit_price` | fill prices |
| `gross_pnl_points` / `gross_pnl_currency` | prices × qty × point value |
| `commission_cost` | AMP per-side × 2 × qty (TJ4 supplies; null before) |
| `slippage_cost` | null (no model declared; do not invent 1 tick) |
| `net_pnl_currency` | gross − commission − `day_fee_allocation` |
| `r_multiple` | net / (`journal_risk_ticks` × tick × point value). Default **10**; if `declared_stop` present, `r_multiple_declared` is also emitted |
| `stop_price` / `target_price` | `declared_stop` / `declared_target` (intent, not executed bracket) |
| `bars_held`, `mae_*`, `mfe_*`, `zone_*`, `signal_id`, `trigger` | null until TJ5–TJ7 |
| `status` | `closed`; unpaired leftover → `open` |

Point values MNQ $2 / MES $5; tick 0.25.

### 3.4 Reconciliation (TJ4)

Per `(session_date, instrument)`:

1. Journal fill multiset `(round(price, 2), side, qty)` vs AMP confirmations
   (imported fills only).
2. Fill counts equal.
3. Recomputed AMP averages equal printed averages (parser self-check).
4. Journal gross $ vs AMP `P&S` $ (tolerance 1 cent).
5. Fee total vs sum of fee lines.

Statuses: `reconciled` | `journal_missing` | `amp_missing` |
`multiset_mismatch` | `pnl_mismatch`. TJ6/TJ7 refuse days not `reconciled`
unless `allow_unreconciled=True` (default false; UI shows the flag).

Day-level extra fees allocate as `day_fee_allocation` equally across that
instrument-day's trades (documented, not hidden in `commission_cost`).

**Golden:** 27-May (redacted) is the TJ4 overlap golden — 40 fills, avg long
`30132.87500`, avg short `30133.55000`, gross `$27.00`.

### 3.5 Bar join (TJ5)

Clock is the existing 15s primary (`ingestion_mode: 15s_primary_derive_1m`).
Join `timestamp` → bar with `open_ts <= ts < open_ts + 15s` after converting
both to UTC. Fill price must satisfy `low <= price <= high`; else
`price_outside_bar`.

`bars_held` counts completed 15s bars strictly between entry and exit. If
`bars_held == 0`, `mae_points` / `mfe_points` stay null with
`excursion_unavailable`. Do not fake MAE from the entry bar's unused range.

Contract month vs the continuous 15s series: stamp `contract_month`; a Jun
fill on a Sep-rolled series is `roll_mismatch` unless R7 roll metadata covers
that day.

### 3.6 Tag verification (TJ6)

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
token that is not in the set fails the TJ6 test suite. The table is the desk
vocabulary observed in this export; the desk owns additions, the repo owns
the map.

For each journal trade with ≥1 level-class tag, on the **entry bar** of the
already-computed levels frame:

- `tag_distance_ticks` = `(entry_price − level_value) / tick` per tag
- `tag_aligned` = `|distance| ≤ tag_tolerance_ticks` (default **10**, the
  Program B pair tolerance)
- `tag_level_missing` when the token is absent from the frame at that bar
- trade-level `tag_alignment` ∈ `all_aligned` | `partial` | `none_aligned`
  | `unverifiable`

Does not recompute levels; consumes the frame the Data/Levels page or R18
already produced. Does not write to `results/studies/`.

### 3.7 Counterfactual match (TJ7)

Input: a **named** completed cell (bundle path or promoted RunSpec), never
the Observatory corpus. Match when all hold: same instrument and direction;
`|Δentry| ≤ match_window` (default 60 s); journal entry within `match_ticks`
(default 8) of the systematic zone or theoretical entry. Classes:
`executed_cell` | `near_level` | `discretionary_only` |
`systematic_unfilled`. `executed_cell` additionally requires hold/risk
compatibility with the cell lock. Never re-ranks `results_index`.

### 3.8 PII and fixtures

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
| **TJ3** | `spread_id` pairing + FIFO fallback → `JournalTrade` (+tags) | `journal/pair.py` + schema |
| **TJ4** | Daily recon + CLI `journal reconcile` + 27-May redacted golden | `journal/reconcile.py` |
| **TJ5** | 15s/1m join | `journal/join.py` |
| **TJ6** | Tag→token map + tag verification + CLI `journal verify-tags` | `journal/tags.py` |
| **TJ7** | Named-cell counterfactual matcher | `journal/match.py` |
| **TJ8** | Report + page 17 + USER_GUIDE H2 + HC allowlist | `pages/17_Journal.py` |

Do not reorder TJ1–TJ4. TJ5 may start once TJ3 exists. TJ6 needs TJ5.
TJ7 needs TJ4 + TJ5. TJ8 last. Quantower loader is **parked** (would need an
explicit `source_tz`; no product need while TradesViz imports).

---

## 5. Per-milestone acceptance

### TJ0 — Plan lock (this PR)

- [x] Evidence from TradesViz + four AMP PDFs + Quantower cross-check in §0.
- [x] Roadmap row + section, docs index, DA §8 pointer, AGENT_GUIDE one-liner.
- [x] No `thesistester/` production edits. No goldens touched.
- [x] `python3 -m pytest -q` matches `main` (one pre-existing failure).

### TJ1 — TradesViz loader

- Explicit profile. Offset required. `asset_type` → `entry_kind`.
- Symbol table §3.1; unknown → `ValueError`.
- `commission` / `fees` discarded with a test asserting they are not used.
- Tags split/preserved; notes HTML-stripped with `[image]` token.
- Fixture: synthetic CSV with MNQM26 imports, a 4-fill `spread_id`, a manual
  `stock` row with tags + SL/TP, a `quantity=0` manual row.

### TJ2 — AMP statement parser

- Confirmations vs P&S split; side via layout; averages self-check.
- `Liquidation Fee` kept extra; unknown fee fails.
- Redacted text fixtures: MNQ JUN 3-page, MNQ SEP 2-page, MES SEP 2-page.
- `pdfplumber` pinned in `pyproject.toml` / `requirements.txt`; import
  confined to `journal/amp_statement.py`.

### TJ3 — Pair

- `spread_id` clean 2-fill, 4-fill scale-in, non-netting group → FIFO
  fallback, leftover → `open`.
- Tags/notes/declared SL-TP propagate; `r_multiple_declared` emitted only
  when `declared_stop` present.
- `journal_risk_ticks` keyword-only, default 10. No `simulate_trades` call.

### TJ4 — Reconcile

- **27-May redacted golden** (`reconciled`, exact numbers §3.4).
- `journal_missing` (AMP 12-Jun pattern) and `amp_missing` covered with
  synthetic dates.
- CLI writes `reconcile.json` + `journal_trades.parquet` under an explicit
  `--output-dir`. No write into `results/studies/`.

### TJ5 — Join

- Uses already-loaded `data` / `subtimeframe_data`; UTC-safe join.
- `price_outside_bar`, `excursion_unavailable`, `roll_mismatch` tested.
- No level-value edits; no `LEVEL_ENGINE_VERSION` bump.

### TJ6 — Tag verification

- Map is data (YAML/dict), unit-tested against `closed_level_token_set`.
- `unmapped` tags counted, never dropped; qualifiers separated.
- Alignment classes tested on a hand-built levels frame (aligned / partial /
  missing token).
- Docs: intent ≠ evidence; alignment is a distance check, not a trigger.

### TJ7 — Match

- Requires a hash-verified bundle or RunSpec path. Corpus-wide matching is
  out (do not unpark SO6).
- Does not modify `STUDY_INDEX_KEYS` or `R18_INDEX_METRIC_KEYS`.

### TJ8 — UX

- New page **17 · Journal**, read-only over ingested artifacts. No in-process
  `run_experiment` / `run_study`; no classic session hydrate.
- USER_GUIDE new H2 + HC §7.1.4 allowlist in the same PR (HC maintenance).
- Honesty caption: journal ≠ study cell; fees from AMP; TradesViz P/L ignored;
  tags are trader intent.

---

## 6. Regression-safety envelope (every TJ PR)

| Rule (§4) | How TJ satisfies it |
|---|---|
| Additive-only engine | **Zero** engine/signal/level edits. Journal is a new package |
| Golden-master | No existing golden regeneration. New journal fixtures only (redacted) |
| Opt-in | No journal code on the default research path. CLI/page are new entry points |
| Schema-versioned persistence | `journal/v1`; readers tolerate missing recon/tag/match files |
| Bundle hash neutrality | Journal never writes into research bundles |
| PIT | TJ5/TJ6 use already-emitted bars/levels; no new level series |
| Determinism | No RNG. Pairing is `spread_id` + time + `fill_id` tie-break |
| Same-PR docs | Each PR lists its doc edits; honesty/glossary/architecture only when true |
| PII | Desk exports stay outside git |

---

## 7. Docs each later PR must touch

| PR | Docs |
|---|---|
| TJ0 | This file; `ENGINEERING_ROADMAP.md` status + section; `docs/README.md`; DA §8; `AGENT_GUIDE.md` |
| TJ1 | `ARCHITECTURE.md` (journal package); `ASSUMPTIONS` (TradesViz P/L unused; manual rows excluded by default) |
| TJ2 | `ASSUMPTIONS` (AMP PDF is the fee SoT) |
| TJ3–TJ4 | `METRICS_GLOSSARY.md` (`journal` expectancy, `reconciled`, `r_multiple_declared`); `ASSUMPTIONS` (spread vs FIFO vs P&S) |
| TJ5 | `POINT_IN_TIME_GUARANTEES.md` (fill→bar join); `ARCHITECTURE` session keys |
| TJ6 | `METRICS_GLOSSARY.md` (`tag_alignment`); `ASSUMPTIONS` (intent ≠ evidence) |
| TJ7 | `ASSUMPTIONS` (match classes) |
| TJ8 | `USER_GUIDE.md` H2; HC allowlist; `ARCHITECTURE` page 17 |

---

## 8. Parked / follow-ups

- **Desk:** re-sync the TradesViz broker import (dead since 2026-06-01);
  tag the *imported* trade instead of re-entering it manually.
- Quantower Trades loader (needs explicit `source_tz=Europe/Vienna`; no
  product need while TradesViz imports).
- TradesViz *trades* (aggregated) export as an alternative to executions.
- Re-cost Program B cells onto the AMP $1.24 RT schedule (separate series).
- Program C conditional locks (ToD + OTF) — after Run 2 readout.
- AP2 (blocked on a Quantower APOC oracle).
- Journal as an R21 portfolio `setup_id` (after TJ5 bar indices exist).
- Tag vocabulary governance (desk-owned list; repo holds the map).

---

## 9. Agent prompt — TJ1 (next PR)

```text
You are implementing TJ1 from docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md
in the ThesisTester repo. Read §0, §2, §3.1, §5 TJ1, and §6 in full
before writing code.

Hard rules:
- Regression-safe per docs/ENGINEERING_PROPOSAL.md §4: additive,
  keyword-only, default = legacy. Do not edit simulate_trades,
  _check_touch, the ["long","short"] loop, or any golden fixture.
- Scope is TJ1 only (TradesViz executions CSV → FillRecord, imported vs
  manual). If you need AMP PDF, pairing, bar join, tag map, or a
  Streamlit page, stop and say so.
- Do not commit the desk's TradesViz CSV, AMP PDFs, or Quantower CSV
  (PII). Build synthetic fixtures that preserve columns: MNQM26 imports
  with +0000 offsets, a 4-fill spread_id, a manual asset_type=stock row
  with tags + stop_loss/profit_target, and a quantity=0 manual row.
- commission/fees columns must be read and discarded; add a test.
- Run `python3 -m pytest -q` before and after; both green (ignore only
  pre-existing failures already on main). Run the golden tests and paste
  their output in the PR body.
- Update the TJ1-listed docs in the same PR. Add a "Regression safety"
  paragraph to the PR body.
- Series code is TJ.
```
