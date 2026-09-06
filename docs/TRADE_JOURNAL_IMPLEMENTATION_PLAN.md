# Trade Journal — Implementation Plan (TJ)

**Document type:** Focused implementation plan (fully scoped PRs)
**Date:** 2026-09-06
**Status:** **TJ0 locked.** No production journal code has landed.
**Series prefix:** **TJ** (Trade Journal). Not DA, not DI, not R21.
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1
golden-master operational spec and §4.2 per-milestone PR acceptance checklist.
**Reader:** desk owner (Edge Finder), ThesisTester bot, engine contributors.

**Inputs (desk, 2026-09-06 — stay outside git):**

| File | Role |
|---|---|
| Quantower *Trades* CSV dated `01052026-31072026` | Layer 1 — timestamped fills (394 rows) |
| AMP Daily Statement PDFs: 27-MAY-26, 12-JUN-26, 23-JUN-26, 29-JUN-26 | Layer 2 — FCM money truth |

**Does not reopen:** `simulate_trades`, signals, levels, R12/R13, DA defaults,
RS execute, SO5/SO6, AP2, Program B Run 1/Run 2 locks, Help-corpus *path* moves.
**Amends (pointer only in TJ0):** DA §8 follow-up; roadmap status row; docs index.

---

## 0. Finding (locked — verified 2026-09-06)

### 0.1 Statement

The desk already has the two objects a journal layer needs: **Quantower fills
with timestamps** and **AMP EOD statements as money ground truth**. They are
complementary, not substitutes. Neither file, alone, can produce an
engine-compatible completed-trade table that is both time-joinable and
cost-honest.

A journal integration is feasible and is the highest-leverage remaining
product step after DA: it measures whether the *trader* is the edge or the
leak, under the same cost and session contracts the research engine already
uses.

### 0.2 What each source actually contains

**Quantower Trades CSV (Layer 1) — parsed 394 data rows**

| Field | Observed |
|---|---|
| Columns | `Date/Time`, `Symbol`, `Side`, `Order type`, `Quantity`, `Price`, `Trade ID`, `Order ID`, `Position ID`, plus unused P/L columns |
| Calendar coverage | **3 days only:** 2026-05-29, 2026-07-03, 2026-07-07. Filename range 01-May–31-Jul is **not** a completeness guarantee |
| Symbols | `MNQM6@CME` (Jun), `MNQU6` (Sep), `MESU6` (Sep). Format is not stable |
| Qty | 392 × `|qty|=1`, **2 × `qty=2`** (cover-two in one fill). `Quantity` is signed (`+1` buy, `-1` sell) |
| Position ID | **3 IDs total** (one per contract+account), not one per trade. FIFO must be inventory on this key |
| Order / Trade ID | 394 unique each. `Trade ID` = `{order_id}@{abs_qty}` |
| `Gross P/L`, `Fee`, `Net P/L` | **always 0**. Costs cannot come from Quantower |
| Order types | Market 211 / Limit 183. Dominant journal pattern: Market in, Limit out (183/198 paired trades) |
| Comment | Rare; one OCO-style `"Orders X,Y are linked."` — not a structured bracket |
| Expiration | Present on Sep rows (`18.9.26 …`); empty + `Symbol type=Unknown` on Jun `MNQM6@CME` |

**AMP Daily Statement PDF (Layer 2) — four days parsed**

| Field | Observed |
|---|---|
| Confirmations | Date, FCM trade number, CME, Buy **xor** Sell (x-position, not a printed token), qty, `MNQ`/`MES`, month/year, price |
| Buy/Sell | Recoverable from layout. On 12-JUN-26: 29/29, averages **exactly** match the printed `AVERAGE LONG/SHORT`, gross P&S **exactly** `$78.00` |
| P&S section | FCM average-matching pairs, **not** chronological FIFO. Use for daily totals only |
| Fees | Exchange / NFA / Clearing Client / Rithmic TRF / Commission. **23-JUN-26 adds `Liquidation Fee $2.50`** |
| Variants | 2-page and 3-page; `../..` continuation; MNQ JUN, MNQ SEP, MES SEP |
| Timestamps | **None.** Date only |
| Format | PDF only (desk confirmed no CSV/XLS). Parser contract is layout-preserving PDF |

### 0.3 The two sources do not overlap in this batch

| AMP statement day | QT fills that day |
|---|---|
| 2026-05-27 | 0 |
| 2026-06-12 | 0 |
| 2026-06-23 | 0 |
| 2026-06-29 | 0 |

QT days 2026-05-29 / 07-03 / 07-07 have no AMP PDF in the batch.

AMP FCM `NUMBER` (e.g. `16731279`) is a **different namespace** from Quantower
`Order ID` (e.g. `109382411`). Join key is **instrument-day + `(price, side, qty)`
multiset**, never ID equality.

TJ4 therefore ships a fail-closed reconcilation: an AMP day with zero QT fills
is `qt_missing`; a QT day with no statement is `amp_missing`; only an exact
multiset match is `reconciled`. This batch is a valid test of the *missing*
paths. A same-day overlap golden is **blocked on the desk** (export QT for an
AMP day, or an AMP PDF for 29-May / 3-Jul / 7-Jul).

### 0.4 Pairing: 1:1 is wrong; qty-aware FIFO is required

Naive “next opposite fill” pairing on `Position ID` invented a 95-hour hold
and a fantasy `$994` gross. Qty-aware FIFO on the same 394 fills:

| | |
|---|---|
| Paired trades | **198** (qty-weighted lots; the two `qty=2` covers become two 1-lot closes) |
| Leftover inventory | **0** |
| Hold min / p25 / median / p75 / max | 0 s / 9.75 s / **24.5 s** / 102.5 s / 36 min |
| Holds `< 15 s` | **71 / 198 (36%)** — no completed 15s bar |
| Direction | 131 long / 67 short |
| Gross $ (MNQ $2/pt, MES $5/pt) | **+$42.00** |
| Fees at AMP schedule $1.24 RT | **−$245.52** |
| Net | **−$203.52** · PF 0.86 · WR 39% |

1:1 pairing is a spec error. AMP P&S pairing is a different object (daily
realized, average-matched). The journal trade is **inventory FIFO per
`Position ID`**.

### 0.5 Cost lock (AMP, four statements)

Per-side fees are identical on MNQ and MES when no liquidation line is present:

| Component | $ / side |
|---|---:|
| Exchange | 0.35 |
| Clearing Client | 0.13 |
| Rithmic TRF | 0.10 |
| NFA | 0.02 |
| Commission | 0.02 |
| **Total** | **0.62** |

Round-turn **$1.24**. Program B lock models `commission_per_side=0.5` +
`slippage_ticks=1` (= $1.00 RT commission+fees + $1.00 RT MNQ slip). **Fixed
fees alone are 24% above the lock's commission line**, before any slippage.
23-JUN-26 adds a day-level `Liquidation Fee` that must **not** be smeared
into the per-side schedule.

Fee drag on the 198-trade QT sample is **6× gross**. This is already a
money-path finding: the book is fee-killed; shorts print, longs leak
(net long −$382 / short +$178 at $1.24 RT, 10-tick R-denominator).

### 0.6 Timezone lock

QT `Date/Time` has no zone column. 2026-07-03 first fill is **09:30:07** —
CME equity-index RTH open to the second. Treat naive timestamps as
`America/New_York`. Do not infer Vienna (statement address) or UTC. Engine
session TZ is already `America/New_York`. TJ5 fill→bar join uses this zone
and fail-closes if the fill price is outside the joined 15s bar's `[low, high]`.

### 0.7 This journal is not Program B

Median hold **24.5 s**, 183/198 Market-in / Limit-out, 10-tick scalp language
already in the TV brief. Program B Run 2 is `fade` @ 1min, 80/80 ($40/$40).
They are **different products**. TJ6 may say “you traded near this level at
this time”; it must not say “you executed cell X” unless the journal trade's
hold, risk, and trigger are compatible with that cell's lock. R-multiples on
the journal default to a **declared journal risk** (desk 10-tick scalp unless
overridden), never silently the 80-tick study lock.

### 0.8 What this is not

- Not a `simulate_trades` bug or a reason to change costs on existing studies.
- Not broker/live integration (proposal §2.2 anti-roadmap).
- Not a Quantower Orders / OCO parser. Linked-order comments stay provenance.
- Not proof of edge or of a durable leak. n=198 across 3 days is a format
  fixture, not a research conclusion.

---

## 1. Goals / non-goals

**Goals**

1. Ingest Quantower Trades CSV into a typed, fail-closed `FillRecord` frame (TJ1).
2. Ingest AMP Daily Statement PDFs into a typed `AmpStatement` (fills + fee
   schedule + P&S totals) (TJ2).
3. Pair fills into journal trades via qty-aware FIFO on `Position ID` (TJ3).
4. Reconcile Layer 1 ↔ Layer 2 per instrument-day; refuse attribution on
   unreconciled days (TJ4).
5. Join journal entries/exits to the 15s (and derived 1m) clock and optional
   named levels (TJ5).
6. Match journal trades to systematic signals of a *named* RunSpec / promoted
   cell as a diagnostic, with explicit unmatched classes (TJ6).
7. Report + a read-only Streamlit pane: recon strip, fee drag, direction split,
   match table (TJ7).

**Non-goals (entire series)**

- Any edit to `simulate_trades`, `_check_touch`, candidate sort, signals, or
  levels math.
- Golden regeneration.
- Live AMP / Rithmic / Quantower API.
- AMP CSV (does not exist).
- Auto-promote, auto-Admit, Notion writes.
- Treating journal expectancy as a study rank key.
- Bid/ask or queue modeling.
- Re-costing historical Program A/B cells onto the AMP schedule (separate
  decision; parked).

---

## 2. Architecture

```
Quantower Trades CSV          AMP Daily Statement PDF
        │                              │
        ▼                              ▼
 TJ1 load_quantower_trades      TJ2 load_amp_statement
        │                              │
        └──────────┬───────────────────┘
                   ▼
            TJ3 fifo_pair_fills ──► JournalTrade frame
                   │
                   ▼
            TJ4 reconcile_day (multiset + fees + P&S)
                   │  fail-closed if not reconciled
                   ▼
            TJ5 join_bars (15s clock, NY) + optional levels
                   │
                   ▼
            TJ6 match_counterfactual (named RunSpec only)
                   │
                   ▼
            TJ7 report / page 17 (read-only)
```

Posture is **R21-shaped**: post-trade ingest + analytics. Journal trades are
a new frame. They are never written into a research bundle as if they were
`simulate_trades` output. `canonical_bundle_hash` of every existing experiment
stays identical.

Suggested package: `thesistester/journal/` (`schema.py`, `quantower_trades.py`,
`amp_statement.py`, `pair.py`, `reconcile.py`, `join.py`, `match.py`,
`report.py`). CLI: `python -m thesistester journal ingest|reconcile|report`.
Store (TJ7): `.thesistester_store/journal/v1/` — user-owned, never evicted by
CAI-10 artifact eviction.

---

## 3. Locked contracts

### 3.1 FillRecord (TJ1)

Required columns after load (additive extras allowed, never required):

`fill_id`, `source`, `source_trade_id`, `source_order_id`, `position_id`,
`instrument` (`MNQ`/`MES`), `contract_month`, `contract_year`, `side`
(`Buy`/`Sell`), `qty` (positive int), `price`, `order_type`,
`timestamp` (UTC-aware, converted from naive NY), `session_date` (NY date).

Fail closed: missing required QT columns, unparseable datetime, unknown
root (not `MNQ`/`MES`), `qty==0`, non-finite price. Extra QT columns
(`Comment`, empty trailer, BOM on `Account`) are ignored.

Symbol map (locked from this export; unknown patterns fail closed):

| Raw | instrument | month | year |
|---|---|---|---|
| `MNQM6@CME` / `MNQM6` | MNQ | JUN | 2026 |
| `MNQU6` / `MNQU6@CME` | MNQ | SEP | 2026 |
| `MESU6` / `MESU6@CME` | MES | SEP | 2026 |

CME month codes: `F G H J K M N Q U V X Z`. Year digit `6` → 2026 in this
decade; do not invent a century heuristic beyond `2000 + 10*k + digit` with
`k` chosen so the year is in `[2020, 2035]`.

Profile token: `quantower_trades`. **No autodetect.**

### 3.2 AmpStatement (TJ2)

Parse **Trades Confirmations** only for the fill list. P&S section is stored
as `ps_pairs` + `ps_usd` for recon, never as journal trades.

Side from layout: the `1` sitting in the BUY column vs SELL column
(x-position / gap heuristic verified on all four PDFs). A parse that
disagrees with printed `AVERAGE LONG` / `AVERAGE SHORT` (when both present)
fails closed.

Fee lines: known names `{Exchange, NFA, Clearing Client, Rithmic TRF,
Commission, Liquidation Fee}`. Unknown fee names fail closed (do not drop).
`per_side_schedule` is computed only from the five standard lines;
`Liquidation Fee` stays `day_fees_extra`.

Two-stage parser: `extract_amp_pdf_text(path) -> str` (pdfplumber layout)
then `parse_amp_statement_text(text) -> AmpStatement`. CI owns the text
parser against committed **redacted** text fixtures. PDF extraction is
tested with a synthetic/redacted PDF, never the desk's named statements.

### 3.3 JournalTrade (TJ3)

Qty-aware FIFO per `position_id`, time-sorted. A `qty=2` cover against two
open 1-lots emits **two** journal trades (same exit fill, distinct
`lot_seq`). Direction = side of the opening lot (`Buy`→long, `Sell`→short).

Map onto the engine *shape* where honest; leave systematic-only fields null:

| Engine column | Journal |
|---|---|
| `trade_id` | `jt:{position_id}:{lot_seq}` |
| `direction` | `long`/`short` |
| `entry_timestamp` / `exit_timestamp` | FIFO open/close (UTC) |
| `entry_price` / `exit_price` | fill prices |
| `theoretical_entry_price` | null until TJ5/TJ6 |
| `gross_pnl_points` / `gross_pnl_currency` | from prices × qty × point value |
| `commission_cost` | AMP per-side × 2 × qty (not QT `Fee`) |
| `slippage_cost` | null until a model is declared (do not invent 1 tick) |
| `net_pnl_currency` | gross − commission − day_fee_allocation (TJ4) |
| `r_multiple` | net / (`journal_risk_ticks` × tick × point_value). Default **10** |
| `bars_held` | null until TJ5 |
| `signal_id`, `trigger`, `zone_*`, `mae_*`, `mfe_*` | null until TJ5/TJ6 |
| `status` | `closed` (open leftover lots fail the day unless flagged `open`) |

Point values: MNQ $2, MES $5 (existing contract table). Tick 0.25 both.

R21 `_REQUIRED_COLUMNS` can be filled only after TJ5 writes bar indices.
Until then the journal frame is **not** a portfolio input.

### 3.4 Reconciliation (TJ4)

Per `(session_date, instrument)`:

1. QT fill multiset `(round(price, 2), side, qty)` vs AMP confirmation multiset.
2. Fill counts equal.
3. Recomputed AMP averages equal printed averages (parser self-check).
4. QT FIFO gross $ vs AMP `P&S` $ (tolerance 1 cent).
5. Fee total vs sum of fee lines.

Statuses: `reconciled` | `qt_missing` | `amp_missing` | `multiset_mismatch` |
`pnl_mismatch`. TJ6 refuses days that are not `reconciled` unless the caller
passes an explicit `allow_unreconciled=True` (default false; UI shows the
flag, does not hide it).

Day-level extra fees (liquidation) allocate as `day_fee_allocation` equally
across that instrument-day's journal trades (documented, not hidden in
`commission_cost`).

### 3.5 Bar join (TJ5)

Clock is the existing 15s primary (`ingestion_mode: 15s_primary_derive_1m`).
Join `timestamp` → bar with `open <= ts < open+15s` on NY-normalized bars.
Fill price must satisfy `low <= price <= high`; else `price_outside_bar`.

`bars_held` counts completed 15s bars strictly between entry and exit.
If `bars_held == 0`, `mae_points` / `mfe_points` stay null with
`excursion_unavailable` (36% of the fixture). Do not fake MAE from the
entry bar's unused range.

Optional level tag: nearest *already computed* level within `N` ticks at the
entry bar. Does not recompute levels. Missing levels → `level_unresolved`.

Contract month vs continuous 15s series: stamp `contract_month` on the
journal row. A Jun fill joined to a Sep-rolled continuous series is
`roll_mismatch` unless the dataset's R7 roll metadata covers that day.

### 3.6 Counterfactual match (TJ6)

Input: a **named** completed cell (bundle path or promoted RunSpec), not the
whole Observatory corpus.

A journal trade matches a systematic trade/signal when all hold:

- same `instrument` and `direction`
- absolute entry-time delta ≤ `match_window` (default 60 s)
- journal entry price within `match_ticks` (default 8) of the systematic
  zone or theoretical entry
- journal `r_multiple` denominator compatibility is **not** required for
  `near_level`; it **is** required for `executed_cell`

Classes: `executed_cell` | `near_level` | `discretionary_only` |
`systematic_unfilled`. Never re-rank `results_index`. Output is an
attribution table: entry slip vs next-open model, hold vs bracket,
override R.

### 3.7 PII and fixtures

Desk PDFs/CSV contain legal name, address, account id. **Do not commit
them.** Committed fixtures are redacted text extracts + a synthetic PDF
and a synthetic QT CSV that preserve layout/columns. Tests assert format
contracts (averages, fee lines, FIFO qty=2, 09:30:07 TZ), not the desk's
P&L.

---

## 4. Milestone table

| Milestone | Intent | Production code |
|---|---|---|
| **TJ0** | Plan lock + evidence + contracts (this PR) | none |
| **TJ1** | `quantower_trades` loader + `FillRecord` | `journal/quantower_trades.py` + tests |
| **TJ2** | AMP PDF → text → `AmpStatement` | `journal/amp_statement.py` + `pdfplumber` dep + tests |
| **TJ3** | Qty-aware FIFO → `JournalTrade` | `journal/pair.py` + schema |
| **TJ4** | Daily recon + CLI `journal reconcile` | `journal/reconcile.py` |
| **TJ5** | 15s/1m join + optional level tag | `journal/join.py` |
| **TJ6** | Named-cell counterfactual matcher | `journal/match.py` |
| **TJ7** | Report + page 17 + USER_GUIDE H2 + HC allowlist | `pages/17_Journal.py` |

Do not reorder TJ1–TJ4. TJ5 may start once TJ3 exists (bar join does not
need AMP), but TJ6 must not run on unreconciled days (needs TJ4). TJ7 last.

---

## 5. Per-milestone acceptance

### TJ0 — Plan lock (this PR)

- [x] Evidence from the four AMP PDFs + QT CSV recorded in §0.
- [x] Roadmap row + docs index + DA §8 pointer + AGENT_GUIDE one-liner.
- [ ] No `thesistester/` production edits. No goldens touched.
- [ ] `python3 -m pytest -q` green vs `main` (ignore only pre-existing).

### TJ1 — Quantower Trades loader

- Explicit profile; BOM + trailing empty column tolerated.
- Symbol table in §3.1; unknown symbol → `ValueError`.
- Naive dt → `America/New_York` → UTC. Fixture includes a `09:30:07` row.
- Signed qty → positive `qty` + `side`. `qty=2` preserved on the fill.
- QT P/L columns discarded (assert they may be zero; do not trust them).
- Tests: 3-day synthetic CSV covering Jun+Sep MNQ, MES, qty=2, linked comment.

### TJ2 — AMP statement parser

- Confirmations vs P&S split. Side via layout. Averages self-check.
- Liquidation Fee kept extra. Unknown fee name fails.
- 2-page and 3-page redacted text fixtures (MNQ JUN, MNQ SEP, MES SEP).
- `pdfplumber` pinned in `pyproject.toml` / `requirements.txt` (needed: no
  AMP CSV). Import confined to `journal/amp_statement.py`.

### TJ3 — FIFO pair

- Fixture: 1-lot in/out, qty=2 cover of two shorts, same-second cluster,
  MES+MNQ same day (two `position_id`s), leftover open lot → `open` status.
- Golden values: 198-shaped synthetic counts, not the desk's dollars.
- `journal_risk_ticks` keyword-only, default 10.
- Does not call `simulate_trades`.

### TJ4 — Reconcile

- Missing-day statuses covered by the real (non-overlapping) pattern using
  synthetic dates.
- Overlap golden: blocked until the desk provides one same-day pair. Until
  then, a **hand-built** overlapping fixture (QT rows whose prices are copied
  from a redacted AMP confirmation list) is acceptable.
- CLI writes `reconcile.json` + `journal_trades.parquet` under an explicit
  `--output-dir`. No write into `results/studies/`.

### TJ5 — Join

- Uses existing loaded `data` / `subtimeframe_data`; does not load CSVs itself
  beyond calling `load_ohlcv` with an explicit profile.
- `price_outside_bar` and `excursion_unavailable` tested.
- No `LEVEL_ENGINE_VERSION` bump. No level-value edits.

### TJ6 — Match

- Requires a hash-verified bundle or RunSpec path. Corpus-wide matching is
  out of scope (do not unpark SO6).
- Classes and windows in §3.6. Docs: diagnostic, not Admit, not live.
- Does not modify `STUDY_INDEX_KEYS` or `R18_INDEX_METRIC_KEYS`.

### TJ7 — UX

- New page **17 · Journal**. Read-only over ingested artifacts. No in-process
  `run_experiment` / `run_study`. No classic session hydrate.
- USER_GUIDE new H2 + HC §7.1.4 allowlist in the same PR (HC-5/HC-6
  maintenance, not a new HC series).
- Honesty caption: journal ≠ study cell; fees from AMP; QT P/L ignored.

---

## 6. Regression-safety envelope (every TJ PR)

| Rule (§4) | How TJ satisfies it |
|---|---|
| Additive-only engine | **Zero** engine/signal/level edits. Journal is a new package |
| Golden-master | No existing golden regeneration. New journal fixtures only |
| Opt-in | No journal code on the default research path. CLI/page are new entry points |
| Schema-versioned persistence | `journal/v1`; readers tolerate missing recon/match files |
| Bundle hash neutrality | Journal never writes into research bundles |
| PIT | TJ5 join uses already-emitted bars; no new level series |
| Determinism | No RNG. FIFO is time + `fill_id` tie-break (source order) |
| Same-PR docs | Each PR lists its doc edits. ASSUMPTIONS / glossary / architecture only when the described behaviour becomes true |
| PII | Desk exports stay outside git |

---

## 7. Docs each later PR must touch

| PR | Docs |
|---|---|
| TJ0 | This file; `ENGINEERING_ROADMAP.md` status + section; `docs/README.md`; DA §8; `AGENT_GUIDE.md` |
| TJ1 | `ARCHITECTURE.md` (journal package); `ASSUMPTIONS` (QT P/L is unused) |
| TJ2 | `ASSUMPTIONS` (AMP PDF is the fee SoT) |
| TJ3–TJ4 | `METRICS_GLOSSARY.md` (`journal` expectancy, `reconciled`); `ASSUMPTIONS` (FIFO ≠ P&S) |
| TJ5 | `POINT_IN_TIME_GUARANTEES.md` (fill→bar join); `ARCHITECTURE` session keys |
| TJ6 | `ASSUMPTIONS` (match classes); DA §8 stays a pointer |
| TJ7 | `USER_GUIDE.md` H2; HC allowlist; `ARCHITECTURE` page 17 |

---

## 8. Parked / follow-ups

- Same-day AMP↔QT overlap golden from the desk (unblocks a real TJ4 golden).
- Quantower *Orders* export (brackets / OCO / SL-TP intent).
- Re-cost Program B cells onto the AMP $1.24 RT schedule (changes study
  numbers; separate series, golden-gated if it touches execute).
- Program C conditional locks (ToD + OTF) — still after Run 2 readout.
- AP2 (still blocked on a Quantower APOC oracle).
- Journal as an R21 portfolio setup_id (only after TJ5 bar indices exist).
- Multi-account / MES-only cost table drift (today MNQ=MES=$0.62/side).

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
- Scope is TJ1 only (Quantower Trades CSV → FillRecord). If you need
  AMP PDF, FIFO pairing, bar join, or a Streamlit page, stop and say so.
- Do not commit the desk's real AMP PDFs or Quantower CSV (PII). Build
  redacted/synthetic fixtures that preserve columns and the 09:30:07
  timezone case.
- Run `python3 -m pytest -q` before and after; both green (ignore only
  pre-existing failures already on main). Run the golden tests and paste
  their output in the PR body.
- Update the TJ1-listed docs in the same PR. Add a "Regression safety"
  paragraph to the PR body.
- Series code is TJ.
```
