# Complete level list × MA / rolling VWAP / pivot

**Document type:** Inventory + work-through order (Program B lock).  
**Date:** 2026-08-20  
**Status:** Verified against `closed_level_token_set`. Not executed. Does **not** amend the locked Notion *Process and roadmap* page.  
**Concept:** `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`  
**Notion:** [Level combination research (Program B)](https://app.notion.com/p/3c2c7b8aa40d81c9a687ee6ec2129b42)

`dVWAP` is **not** a required partner. It is an optional **core** (wave 5). Every cell is one named location against one MA, one rolling VWAP, or one pivot.

Compute and run count are not constraints. Completeness and structure are.

---

## 0. Split (do not invert)

| Side | What | Count |
|---|---|---:|
| **Anchors** | Named locations you test | **50** (49 static + `prev30mVWAP`) |
| **Wave 0 — solo** | Each anchor, **no** partner | **50** |
| **Confirms (default)** | What you test them against | **22** (12 MA + 2 rolling VWAP + 8 pivot) |
| **One-partner cells / product** | `core=L`, `partners=[X]` | **1,100** |
| **Confirms (widget-maximal)** | Same families, full editor catalog | **48** (36 MA + 4 rolling VWAP + 8 pivot) |
| **One-partner cells / product (widget)** | after the default 22 are done | **2,400** |

Default closed set is 73 = 50 anchors + 22 confirms + `POC_rolling_30min` (not in the requested confirm set; optional extra, §4).

Partner ≠ core. Pair studies: `from_partners: required`, `min_valid_confluences: 1`, `anchor_rules`. No `dVWAP` in `partner_levels`.

**Wave 0 (solo)** is a **separate** study: `partner_levels: [[]]`, `min_valid_confluences: 0`, `confluence_mode: [anchor_rules]` only (AO1). Do not put `[]` in the same StudySpec as the 22 confirms (`min_valid: 1` cannot emit empty sets).

---

## 0.1 Locked constants (do not cartesian)

Yes: **anchor** = `core_level`. **Confluence** = one partner inside **10 ticks of the anchor** (`anchor_rules`: distance is partner-price vs anchor-price). Trigger is `touch` of that zone.

| Lock | Value | Why |
|---|---|---|
| Instrument | MNQ first | Same tape as the desk. MES later, money map explicit |
| Mode | `anchor_rules` | Location is the decision; partner is evidence |
| `from_partners` | `required` | Causal AND. Optional StudySpec drops the lock |
| `min_valid_confluences` | **`0` on Wave 0 only**; `1` on pair waves | AO1: empty partners legal iff exclusive `anchor_rules` and explicit `0` |
| `tolerance_ticks` | **10** | Confluence width. Distance audit (nearest stack p25/p50/p75 = 0/0/2). Not the stop |
| Trigger | `touch` @ `1min` | First product. `3c` is a later separate study |
| Direction | `both` | Side is a readout, not a first cartesian |
| SL / TP | **80 / 80** | $40 / $40 = 1R. MNQ $0.50/tick |
| Commission | **`0.5` per side** | Currency, not ticks. Round-trip **$1.00** |
| Slippage | **`1.0` tick per side** | Engine has no separate “spread” field. 1 tick in + 1 tick out = **$1.00** RT. Models a 1-tick spread |
| Round-trip friction | **$2.00 = 0.05R** | At 80-tick risk. Zero-cost screens lie |
| Exposure | `single_position` | One trade at a time |
| Flatten at close | **`true`** | New day-trade program. Program A L1 was `false` — those E numbers are not this lock |
| Intrabar | `subtimeframe_conservative` | 15s HE |
| Ingest | Quantower HE, UTC, `15s_primary_derive_1m` | Same as finished desk L1 files |
| OTF | off | Validation matrix later, not `factors.otf` |
| ToD | post-hoc only | Never a StudySpec factor |

Do not omit costs (engine default 0/0 is gross-era). Do not cartesian 40 vs 80, 10 vs 20, or cost-on vs cost-off.

---

## 0.2 Wave 0 — levels alone (50 cells)

Question: which of the 50 named locations have **positive expectancy when traded with no confluence**?

```yaml
factors:
  core_level: [<all 50 anchors>]
  partner_levels:
    - []
  confluence_mode: [anchor_rules]
  trigger: [touch]
  trigger_timeframe: [1min]
constants:
  min_valid_confluences: 0    # explicit; omit → 1 → no zones
```

AO1 (`docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md`, shipped on `main`): empty rules + `min_valid: 0` emit a **point zone** `[P, P]` at the live anchor price on every bar where that price is finite. `touch` means the bar’s high/low contains `P`. `tolerance_ticks: 10` is **unused** here (it is partner-to-anchor distance, not an entry halo). This is not “ONH ± 10 ticks.” That halo does not exist.

Same product locks as §0.1 otherwise (MNQ, 80/80, costs 0.5 / 1.0, flatten true).

Run Wave 0 **first**, as its own study (50 cells). Then the 1,100 pair cells. A pair’s ΔE vs its solo cell mixes “value of the confirm” with **zone-shape change** (point vs partner bounding box). Report both; do not treat ΔE as a pure confluence effect.

Readout (same honesty as pairs): n, `expectancy_r`, PF. Interpret at n≥30. Coin-flip hold if `|E|<0.03` or PF ∈ [0.95, 1.05]. “Positive expectancy” for this question = n≥30 and E≥0.03 and PF>1.05. Descriptive, not Admit.

---

## 1. Anchors — complete list (50)

Every default token that is **not** an MA, **not** a rolling VWAP, **not** a pivot. Work through **by wave**. Wave 0 uses this same list with no partners. Do not skip a later wave because an earlier name bled.

### Wave 1 — Session extremes (12)

Overnight / prior overnight, Asia, London, opening range, prior RTH range.

| # | Token | Notes |
|---|---|---|
| 1 | `ONH` | Overnight high |
| 2 | `ONL` | Overnight low |
| 3 | `pONH` | Prior overnight high |
| 4 | `pONL` | Prior overnight low |
| 5 | `AsiaHigh` | |
| 6 | `AsiaLow` | |
| 7 | `LondonHigh` | |
| 8 | `LondonLow` | |
| 9 | `OR_High` | Opening range high (default 15m) |
| 10 | `OR_Low` | Opening range low |
| 11 | `pRTH_High` | Prior RTH high |
| 12 | `pRTH_Low` | Prior RTH low |

There is **no** `RTH_High` / `RTH_Low` / `dHigh` / `OR_Mid` token.

### Wave 2 — Session opens (8)

| # | Token | Notes |
|---|---|---|
| 13 | `dOpen` | Today’s session open |
| 14 | `RTH_Open` | Today’s RTH open |
| 15 | `pRTH_Open` | Prior RTH open |
| 16 | `pdOpen` | Prior day open |
| 17 | `wOpen` | Week open |
| 18 | `pwOpen` | Prior week open |
| 19 | `mOpen` | Month open |
| 20 | `pmOpen` | Prior month open |

### Wave 3 — Prior range / EQ / settlement (10)

| # | Token | Notes |
|---|---|---|
| 21 | `pdHigh` | Prior day high |
| 22 | `pdLow` | Prior day low |
| 23 | `pdEQ` | Prior day equilibrium |
| 24 | `pwHigh` | |
| 25 | `pwLow` | |
| 26 | `pwEQ` | |
| 27 | `pmHigh` | |
| 28 | `pmLow` | |
| 29 | `pmEQ` | |
| 30 | `prevSettlement` | |

`pdHigh` / `pdVAH` are economic siblings if stacked as *partners*. Here they are **separate cores**. Run both.

### Wave 4 — Prior profile (9)

Typical-price MVP `(H+L+C)/3`, 70% VA, `shift(1)`. Not true VAP.

| # | Token |
|---|---|
| 31 | `pdPOC` |
| 32 | `pdVAH` |
| 33 | `pdVAL` |
| 34 | `pwPOC` |
| 35 | `pwVAH` |
| 36 | `pwVAL` |
| 37 | `pmPOC` |
| 38 | `pmVAH` |
| 39 | `pmVAL` |

### Wave 5 — Session VWAP as cores (4)

These are **levels you may test**, not required partners. `dVWAP` as core + `SMA_50_5min` is a legal cell. `ONH` + `dVWAP` is **not** this program.

| # | Token | Notes |
|---|---|---|
| 40 | `dVWAP` | Full CME session VWAP |
| 41 | `dVWAP_RTH` | RTH-only VWAP |
| 42 | `wVWAP` | Week VWAP |
| 43 | `mVWAP` | Month VWAP |

No `wVWAP_RTH` / `mVWAP_RTH`.

### Wave 6 — Single prints (4)

| # | Token |
|---|---|
| 44 | `dSinglePrint_30m_NearestAbove` |
| 45 | `dSinglePrint_30m_NearestBelow` |
| 46 | `pSinglePrint_30m_NearestAbove` |
| 47 | `pSinglePrint_30m_NearestBelow` |

### Wave 7 — APOC (2)

| # | Token |
|---|---|
| 48 | `APOC` |
| 49 | `pAPOC` |

### Wave 8 — Frozen prior 30m VWAP (1 default)

| # | Token | Notes |
|---|---|---|
| 50 | `prev30mVWAP` | Age-1 spelling (not `prev30mVWAP_1`) |

Widget opt-in, same wave, later: `prev30mVWAP_2` `prev30mVWAP_3`.

---

## 2. Confirms — what you test those 50 against

### 2.1 Default menu (22) — work this first

**MAs (12)** — SMA 50/200 × 1min/5min/30min; EMA 9/21 × 1min/5min/30min.

`SMA_50_1min` `SMA_50_5min` `SMA_50_30min`  
`SMA_200_1min` `SMA_200_5min` `SMA_200_30min`  
`EMA_9_1min` `EMA_9_5min` `EMA_9_30min`  
`EMA_21_1min` `EMA_21_5min` `EMA_21_30min`

**Rolling VWAPs (2)**

`VWAP_rolling_30min` `VWAP_rolling_4h`

**Pivots (8)** — engine spelling is `1m`/`5m`/`30m`/`4h`, not `1min`.

`Pivot_1m_High` `Pivot_1m_Low`  
`Pivot_5m_High` `Pivot_5m_Low`  
`Pivot_30m_High` `Pivot_30m_Low`  
`Pivot_4h_High` `Pivot_4h_Low`

Per anchor: 12 + 2 + 8 = 22 cells. Per wave-1 (12 anchors): 264 cells. Full default grid: **50 × 22 = 1,100** per product.

### 2.2 Widget-maximal menu (48) — second pass

Enable in `study.levels`: `sma_lengths` / `ema_lengths` = `{9,20,21,50,100,200}`, `vwap_windows` = `{15min,30min,1h,4h}`.

**Extra MAs (+24)** — SMA 9/20/21/100 × 3 TFs; EMA 20/50/100/200 × 3 TFs.  
**Extra rolling VWAPs (+2):** `VWAP_rolling_15min` `VWAP_rolling_1h`.  
Pivots unchanged (8).

There is **no** MA `15min` TF. Do not invent `SMA_50_15min`.

### 2.3 How pivots attach (not floor pivots)

Pivots are **partners**, same shape as an MA. They are not cores on this grid. They are not classic PP/R1/S1.

```text
core_level: ONH
partner_levels: [Pivot_5m_High]
tolerance_ticks: 10          # |Pivot_5m_High − ONH| ≤ 10 ticks
```

What the token is (`thesistester/levels/pivots.py`):

- Latest **confirmed fractal** swing: high is a local max vs `left` bars and `right` bars (default **2 / 2**).
- PIT: the value is published only after `right+1` bars of that TF (`align_timestamp = pivot_bar + 3 × TF`). Unconfirmed swings are not in the column.
- Settings keys are `1min`/`5min`/`30min`/`4h`. Column spelling is `Pivot_1m_*` (not `Pivot_1min_*`).
- Defaults already emit all 8 (`pivots_enabled: true`). If that gate is off, the tokens are illegal.

A zone fires when the latest confirmed pivot **price** sits within 10 ticks of the **anchor price**. Example: ONH is 21450.00 and `Pivot_5m_High` is 21448.50 → 6 ticks → valid. The 5m swing is “at” the overnight high.

Run **all 8** per anchor. `ONH`+`Pivot_5m_High` (same-side structure) and `ONH`+`Pivot_5m_Low` (opposite swing) are different theses; do not drop Low because High feels more natural. Do **not** put two pivots in one partner set (same swing structure, two TFs). Do not invent `Pivot_15m_*` or floor-pivot names.

---

## 3. Work-through order

Finish a wave before the next. Inside a wave, finish one confirm **family** across all names in that wave before the next family. Collect n / E[R] / PF per cell. Do not kill a name off later families because MA cells bled.

```text
pick ONE product lock (do not mix touch/10 with 3c/20)

Wave 0  (own study, min_valid: 0)
  for L in all 50 anchors:
    core=L, partner_levels=[]          # point zone at L

Waves 1–8  (own studies, min_valid: 1)
  for wave in 1..8:
    for family in (MA, rolling VWAP, pivot):
      for L in wave:
        for X in family:
          core=L, partners=[X]
          required, anchor_rules
          NO dVWAP partner
```

**First product lock:** §0.1. MNQ, `touch` @ `1min`, confluence **10** ticks, SL/TP **80 / 80**, costs **0.5 / 1.0**, flatten **true**. No `dVWAP` partner.

Why 80 not 40: MNQ ~30k vs ~18k. Tick dollar value is unchanged ($0.50); 40 ticks is a smaller fraction of typical range. $40 is the desk full-risk cap. Zone stays 10 — “partner within 10 ticks of the anchor,” not the stop.

Do **not** cartesian 40 vs 80, 10 vs 20, or cost-on vs cost-off. 40/40 is a later sensitivity on identified cells only. Second product (`3c` @ 20, same 80/80 and same costs) after the default 1,100, or as a separate study.

One extra only on the first grid. Two-confirm stacks (`ONH` + `SMA_50_5min` + `VWAP_rolling_30min`) are a later pass on cells that are identified (`n≥30` and not a coin-flip). Cap core+partners ≤ 5.

Two MAs in one partner set are the same information — negative control only, not the main grid.

---

## 4. Not in this grid

| Token / name | Why |
|---|---|
| `POC_rolling_30min` (`1h` / `4h` widget) | Developing profile, not a requested confirm. Optional later family |
| `dVWAP` as a **partner** on every cell | Explicitly not this program |
| `dHigh` `dLow` `dEQ` `RTH_High` `RTH_Low` | Parked compute — engine does not emit |
| `dVAH` `dVAL` `dPOC` `VAH_rolling_*` `VAL_rolling_*` | Parked |
| `OR_Mid` IB / 60m IB `pVWAP` `pRTH_VWAP` | Parked |
| Classic floor pivots (PP/R1) | Not tokens |
| `prev30mVWAP_hit_m1` / `_hit_m5` | Diagnostics, not StudySpec tokens |
| `wVWAP_RTH` `mVWAP_RTH` `Pivot_1min_*` `SMA_50_15min` | Do not invent |

---

## 5. Reproduce

```bash
python3 -c "
from thesistester.levels.catalog import STATIC_STUDY_LEVEL_NAMES
from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS
from thesistester.study.schema import closed_level_token_set
s = closed_level_token_set(DEFAULT_LEVELS_SETTINGS)
anchors = sorted(STATIC_STUDY_LEVEL_NAMES | {'prev30mVWAP'})
print(len(s), len(anchors))
"
```

Verified 2026-08-20: default closed **73**; anchors **50**; default confirms **22**; leftover in the 73-set = `POC_rolling_30min` only.
