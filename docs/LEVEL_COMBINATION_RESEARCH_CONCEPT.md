# Level-combination research concept (Program B)

**Document type:** Research design (concept). Not a desk runbook. Not a StudySpec dump.  
**Date:** 2026-08-20  
**Status:** Concept published. Not executed. Does **not** amend the locked Notion *Process and roadmap* page.  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4 (docs-only; no engine/golden touch)  
**Related:** `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` (Program A — executed product funnel), `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md` (complete token list + work-through), `docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/research-methodology.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`  
**Notion contract (short):** [Level combination research (Program B)](https://app.notion.com/p/3c2c7b8aa40d81c9a687ee6ec2129b42) — sibling of the locked desk page; does not amend it.  
**Bot runbook + YAMLs:** `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` · `examples/studies/program_b/`

**Current lock (2026-08-20):** `dVWAP` is **not** a required partner. **Wave 0:** all 50 locations **alone** (`partner_levels: [[]]`, `min_valid_confluences: 0`, AO1 point zone), split into a 15s StudySpec (41 non-VA) and a tick-gated VA StudySpec (9). Then the same 50 against **MAs, rolling VWAPs, and pivots** — Wave 4 is tick-gated. First product: MNQ `touch` @ `1min`, pair confluence **10** ticks, SL/TP **80/80** ($40 / $40), costs **`commission_per_side: 0.5`** + **`slippage_ticks: 1.0`**, flatten **true**. Full table: `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md` §0.1–§0.2. Compute / run count are not constraints.

Program A answered a different question and is finished. This file is the concept that was asked for.

---

## 0. What was asked vs what was built

| | Asked (this file) | Built and run (Program A) |
|---|---|---|
| Object of study | **Variety of level classes**, in **combination** with confluence classes | Which **named cores** survive a coin-flip kill list under two locked products |
| Location model | Level × (MA / rolling VWAP / pivot). `dVWAP` is an optional **core**, never a mandatory partner | Only core + required `dVWAP` |
| Combination | The **experiment**. Solo-dead cores stay in the pair design | Consolation prize after solo survive. Killed names stay off the map |
| Pairing rule | Pre-registered **complementary structures** by class | Leftover extras around the one survivor (`ONH`) |
| Readout | Interaction, thinning, class × trigger, then (later) Admit | Promote / hold / kill / STOP |
| Stop rule | A *structure* is unidentified if `n<30`. A *class* is not dropped from pairs because solo E < 0 | L2 all-low-N → STOP the product funnel |
| Result | Not run | Clean negative: ONH MNQ note, extras empty, MES kill, nothing Admitted |

Program A was the right **product** funnel for the locked desk page. It is the wrong design for “holistically test a variety of levels in combination.”

Do not reopen Program A from this file. Do not put killed Program A names back on the scalp map. Do not invent a study from the ONH note. If Program B is ever run, it is a **new named program** with its own contract page.

---

## 1. Research question

For discretionary intra-day NQ/ES (MNQ/MES first), which **classes of named price location**, used as the **anchor**, have a location-conditioned return distribution that is **altered — not merely thinned —** by **classes of additional evidence**?

Three claims this must be able to distinguish:

1. **Location has no edge, confirmation has no edge** — combination is a coin-flip with fewer trades.
2. **Location is dead alone, alive with complementary evidence** — the actual confluence hypothesis. Program A cannot see this: it kills the core first.
3. **Location is alive alone, confirmation only starves n** — stacking is folklore.

Program A tested claim (1)/(3) under a single location model (`dVWAP` required, 10-tick scalp / 20-tick swing) and then stopped. It never tested claim (2).

---

## 2. Completeness without a 73×72 bag

The intended grid is **every location alone** (Wave 0: 50) **then** every location × the three confirm families (50 × 22 = 1,100 per product). Compute is not a reason to shrink it.

What is still the wrong “holistic”: every token vs every other token, including MA×MA, pivot×pivot, and `dVWAP` welded onto every cell (73 × 72 × trigger × width). Ranked cells stay descriptive (`docs/ASSUMPTIONS_AND_LIMITATIONS.md`). One extra per cell; stacks later.

---

## 3. Design principles

1. **Complete location list, structured by wave — not a 24-name kill list and not a 73×72 bag.** Every named location that is not an MA, rolling VWAP, or pivot is an anchor (50 tokens). Wave 0 is that list **alone**. Then work through pair waves. Do not drop a name because solo E < 0 or an earlier family bled.
2. **Solo is the baseline; combination is the experiment.** A core that is dead alone stays in the pair design. A core that fails with MAs still gets rolling VWAP and pivots.
3. **`dVWAP` is not mandatory.** It is wave-5 **core** only. `ONH`+`dVWAP` is Program A, not this grid.
4. **Confirms are three families:** MA, rolling VWAP, pivot. One extra per cell on the first grid. Two-confirm stacks later, only on identified cells.
5. **Compute is not a constraint.** Wave 0 is 50 solo cells. Then 50 × 22 = 1,100 pair cells per product. Widget-maximal (48 confirms → 2,400) is a second pass. Structure the work; do not thin the list to save runs.
6. **Triggers, ToD, SL/TP, instrument are factors, not more levels.** One product at a time. Do not cartesian 10 vs 20 in one study.
7. **Research readout ≠ product Admit.** Report n / E[R] / PF per cell. Coin-flip / promote / Admit stay the later product filter (n≥30, `|E|<0.03` or PF ∈ [0.95, 1.05] → hold, Admit = `backtest.entry_window`). Ranked cells stay descriptive (`docs/ASSUMPTIONS_AND_LIMITATIONS.md`).

---

## 4. Factor L — complete location list (50)

Do not invent tokens (`ONMid`, `RTH_Mid`, `RTH_High`, `dSP_high` are not in the closed set). Full names, wave order, and checklist: `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md`.

| Wave | Class | Count | Tokens |
|---|---|---:|---|
| 1 | Session extremes | 12 | `ONH` `ONL` `pONH` `pONL` `AsiaHigh` `AsiaLow` `LondonHigh` `LondonLow` `OR_High` `OR_Low` `pRTH_High` `pRTH_Low` |
| 2 | Session opens | 8 | `dOpen` `RTH_Open` `pRTH_Open` `pdOpen` `wOpen` `pwOpen` `mOpen` `pmOpen` |
| 3 | Prior range / EQ / settlement | 10 | `pdHigh` `pdLow` `pdEQ` `pwHigh` `pwLow` `pwEQ` `pmHigh` `pmLow` `pmEQ` `prevSettlement` |
| 4 | Prior profile | 9 | `pdPOC` `pdVAH` `pdVAL` `pwPOC` `pwVAH` `pwVAL` `pmPOC` `pmVAH` `pmVAL` |
| 5 | Session VWAP **as cores** | 4 | `dVWAP` `dVWAP_RTH` `wVWAP` `mVWAP` |
| 6 | Single prints | 4 | `dSinglePrint_30m_NearestAbove` `dSinglePrint_30m_NearestBelow` `pSinglePrint_30m_NearestAbove` `pSinglePrint_30m_NearestBelow` |
| 7 | APOC | 2 | `APOC` `pAPOC` |
| 8 | Frozen prior 30m VWAP | 1 | `prev30mVWAP` |

50 = 49 static + `prev30mVWAP`. MAs, rolling VWAPs, and pivots are **confirms**, not cores on this grid. `POC_rolling_30min` is the only default-73 leftover; optional later family, not this grid.

---

## 5. Factor C — MA / rolling VWAP / pivot

Default confirms (**22**). Widget-maximal (**48**) is a second pass. Exact spellings: `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md` §2.

| Family | Default tokens | Count |
|---|---|---:|
| **MA** | `SMA_50_*` `SMA_200_*` `EMA_9_*` `EMA_21_*` × `1min`/`5min`/`30min` | 12 |
| **Rolling VWAP** | `VWAP_rolling_30min` `VWAP_rolling_4h` | 2 |
| **Pivot** | `Pivot_{1m,5m,30m,4h}_{High,Low}` | 8 |

Cell: `core_level=L`, `partner_levels=[X]`, `from_partners: required`, `min_valid_confluences: 1`, `anchor_rules`. One extra. No `dVWAP` partner.

Two MAs in one set = negative control only. `dVWAP`+`VWAP_rolling_*` as partners is not this grid (`dVWAP` is a core in wave 5). Level+level pairs (`ONH`+`pdPOC`) are a different program; not this list.

---

## 6. Work-through (compute is not the constraint)

```text
pick ONE product lock

Wave 0 15s (progB_w0_solo.yaml, min_valid: 0)   # 41 non-VA cores, AO1
  for L in 41 non-VA anchors:
    core=L, partner_levels=[]

Waves 1–3, 5–8  (own studies, min_valid: 1)
  for wave in (1, 2, 3, 5, 6, 7, 8):
    for family in (MA, rVWAP, pivot):  # all 22 default confirms
      for L in wave:
        for X in family:
          core=L, partners=[X]

Wave 0 VA + Wave 4  (manifest_va.yaml) — park until ticks
```

Catalog Wave 0 is still **50** solo cells (41 + 9). Then 50 × 22 = **1,100** pair cells per product. Operator 15s packet: `manifest.yaml` (smoke + 41 solos + 21 family YAMLs = **944**). Tick packet: `manifest_va.yaml` (9 solos + Wave 4 = **207**). Do not put VA tokens in a 15s YAML — TV3 refuses the whole study. Second product is a separate study. Widget 50 × 48 = 2,400 after the default 22.

Do not stop a wave because cells are thin. n<30 = unidentified for *that pair*, not a license to skip the rest of the name.

A later two-confirm stack (`L` + one MA + one rolling VWAP) is only for identified cells. Cap core+partners ≤ 5.

---

## 8. Other factors (hold or cross, do not dump into L)

| Factor | Hold while mapping L × C | Cross later |
|---|---|---|
| **T Trigger** | One product at a time | Same cell, `touch` vs `3c`, **same width** (Program A L6b shape) — estimates waiting vs touch per *class*, not only for ONH |
| **W Width** | Confluence **10** ticks (`tolerance_ticks`) | Do not pick width by in-sample R. 20 is a later product |
| **S SL/TP** | **80 / 80** ($40 / $40 on MNQ, 1R) | 40/40 later sensitivity only. Do not cartesian 40 vs 80 |
| **Costs** | `commission_per_side: 0.5`, `slippage_ticks: 1.0` | $2 RT = 0.05R. Do not run a zero-cost twin |
| **I Instrument** | MNQ first | MES transfer last, money map explicit |
| **Time** | `flat_by_session_close: true` | Post-hoc 30m NY. Never a StudySpec factor. Admit only via `study promote --admit-tod auto` |
| **OTF** | Off | Validation matrix on a promoted single setup (`docs/research-methodology.md`), not `factors.otf` |
| **Side** | `both` | Direction read after a cell is identified, not a first-screen cartesian |

Ingest / `intrabar_model` / `exposure_policy` are locks in `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md` §0.1. They are not research axes.

---

## 9. Evaluation (holistic readout)

Per cell, n≥30 to *interpret*. n<30 = unidentified, not “killed class.”

| Metric | Meaning |
|---|---|
| `n`, `expectancy_r`, PF, CI | Descriptive screen. Primary rank key is `expectancy_r`, never `total_r` |
| **ΔE vs other confirms on the same L** | Did this family change E vs the other two families at the same location? |
| **ΔE vs Wave 0 (same core)** | Did the partner change E vs the AO1 point-zone solo cell? 15s cores: `progB_w0_solo.yaml`. VA cores: `progB_w0_va.yaml` (tick-gated) |
| **ΔE vs partner-alone** | Is this the partner’s edge with a location sticker? (Setup replay; MA / pivot / rVWAP are confirms, not cores) |
| **Thinning** `n(combo)/n(core)` | Confirmation that only starves |
| **Year split** | Stability, not a new factor |
| Coin-flip / promote / Admit | **Product filter after** the map exists. Same numeric locks as Program A |

Interaction, simply:

```text
useful confluence  ⇔  n≥30  and  ΔE vs the relevant baseline ≥ 0.03
                      and  PF moves off [0.95, 1.05]
                      and  thinning is not the whole story
```

A green ToD pocket is not a cell. A class with solo E < 0 and pair ΔE ≥ 0.03 is exactly the combination result Program A was structurally unable to produce.

Combo attribution (already shipped) is **retrospective** on optional/mixed setups. It is not a substitute for required C3 cells. Do not auto-tighten from the same sample.

---

## 10. Ideal sequence (complete coverage)

```text
B0  Lock this file + LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md
B0s Solo map              50 cores, partner [], min_valid: 0 (AO1). 15s = 41 (`progB_w0_solo`); VA = 9 (`progB_w0_va`, ticks)
B1  Default pair grid     50 × 22, touch @ 1min, confluence 10, SL/TP 80/80 ($40). Wave 4 tick-gated
B2  Second product        same 1,100, other trigger/width — separate study
B3  Widget pass           extra MA lengths + VWAP_rolling_15min/1h on interesting waves
B4  Two-confirm stacks    only on identified cells
B5  ToD overlay           post-hoc; Admit path only if a product is named
B6  Width / SL-TP         only on identified product candidates
B7  Instrument transfer   MES last
```

**Stop rules (Program B):**

- A **pair** with `n<30` is unidentified. Finish the rest of that name’s families anyway.
- Do **not** open all-optional StudySpec discovery because a wave was thin.
- Program A L2 STOP does not end this grid.

**Still forbidden (honesty, not product taste):**

- StudySpec `from_partners: optional` as a way to keep `dVWAP` required (it does not).
- `min_valid: N` on a study that also emits the 1-partner `{dVWAP}` baseline.
- Promote on `E>0` and `PF≥1.0` (that promotes `pwEQ`).
- Admit via setup-only `constants.entry_window`.
- Inventing tokens, triggers, or factor axes.
- Writing Program B results onto the Program A scalp/swing map as if they were the same contract.

---

## 11. What “complete” means

Every one of the **50** anchors has a **solo** cell (Wave 0, n / E[R] / PF) **and** has been run against every one of the **22** default confirms, under at least one product lock. Widget 48 and a second product are completeness of the *menu*, not a license to skip Wave 0 or the 1,100.

It does **not** require `dVWAP` as a partner, level+level pairs, or parked tokens.

---

## 12. Realization on ThesisTester

Primitives and the operator packet exist. Remaining work is **running** the grid, not inventing tokens or a location-only path.

| Need | Today | Gap |
|---|---|---|
| `core_level` × `partner_levels` | StudySpec / Study Runner | None for the 50×22 grid |
| Location-only (no partner) | AO1 + `progB_w0_solo.yaml` (`[[]]` + `min_valid: 0` → point zone `[P,P]`) | None. Do not replay Setup Builder for the solo baseline |
| Interaction report | Cells have E, n, PF | No first-class ΔE table. Spreadsheet / research report is enough |
| Matrix | `examples/studies/program_b/` + `generate_program_b_yaml.py` | Do not hand-edit token lists. Regenerator + `validate_program_b_yaml.py` |
| Product Admit | `study promote --admit-tod auto` | Unchanged. Do not auto-promote from this grid |
| Desk contract | Notion *Process and roadmap* | **Leave it locked.** Program B gets its own page if it runs |

No new factor axes. No golden regen. No engine series. Cap remains core + partners ≤ 5.

---

## 13. What Program A already contributes (do not rerun)

Treat these as **known Program A facts** (required-`dVWAP` kill list) on the 2024-07-31 → 2026-08-06 MNQ 15s HE slice (costs 0.5/1.0, flatten copied `false`):

- Under touch/10/40 + required `dVWAP`, only `ONH` is above the product promote bar. `pwEQ` is a coin-flip hold.
- Required extras around `ONH` at 10 ticks are almost never present. That does **not** speak to `ONH`+`SMA_*` / `VWAP_rolling_*` / `Pivot_*`.
- 3c/20/80 + required `dVWAP` wipe. Same-width wait hurts that ONH location. MES transfer kills the live claim.

Those facts bound one Program A corner. They do not thin this 50×22 grid.

---

## 14. Decision

The original ask was Program B. The executed work was Program A.

Next research step, if any, is **not** “another ONH leftover pair,” **not** “put `RTH_Open` back on the scalp map,” and **not** a required-`dVWAP` replay. It is: run the 15s operator packet in `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` — smoke, then Wave 0 (`progB_w0_solo.yaml`), then waves 1–3 and 5–8 of `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md`. Park `manifest_va.yaml` (Wave 0 VA + Wave 4) until ticks.

The Program A desk page stays locked / wait. This grid is a different contract.
