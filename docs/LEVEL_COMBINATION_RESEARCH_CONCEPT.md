# Level-combination research concept (Program B)

**Document type:** Research design (concept). Not a desk runbook. Not a StudySpec dump.  
**Date:** 2026-08-20  
**Status:** Concept published. Not executed. Does **not** amend the locked Notion *Process and roadmap* page.  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4 (docs-only; no engine/golden touch)  
**Related:** `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` (Program A — executed product funnel), `docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/research-methodology.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`  
**Notion contract (short):** [Level combination research (Program B)](https://app.notion.com/p/3c2c7b8aa40d81c9a687ee6ec2129b42) — sibling of the locked desk page; does not amend it.

Program A answered a different question and is finished. This file is the concept that was asked for.

---

## 0. What was asked vs what was built

| | Asked (this file) | Built and run (Program A) |
|---|---|---|
| Object of study | **Variety of level classes**, in **combination** with confluence classes | Which **named cores** survive a coin-flip kill list under two locked products |
| Location model | Two models: core-only **and** core + `dVWAP` | Only core + required `dVWAP` |
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

## 2. Why a token cartesian is still the wrong “holistic”

Holistic means **every economically distinct hypothesis is identified once**. It does not mean every syntactic product of `closed_level_token_set` (73 default tokens; 103 widget-maximal).

A 73 × 72 × trigger × width grid is a machine for crowning noise (Bailey & López de Prado, *The Probability of Backtest Overfitting*). Practitioner confluence work converges on the same bound: **2–3 complementary filters**, not 8-filter AND walls.

The constraint is **identifiability**, not compute. Ignore wall-clock. Do not ignore the number of trials you looked at (`docs/ASSUMPTIONS_AND_LIMITATIONS.md`; ranked cells stay descriptive).

---

## 3. Design principles

1. **Sample levels by class, not by listing every token.** Representatives cover the variety. Sibling tokens (`pdVAH` vs `pdHigh`, `SMA_50_5min` vs `EMA_21_5min`) are the same information unless a named exception says otherwise.
2. **Combination is the experiment.** A core that fails solo remains in the pair design. That is the opposite of Program A L1b, on purpose.
3. **`dVWAP` is a factor, not air.** Required `dVWAP` answers “is this location near session fair value?” It does **not** answer “does this level work?” Those are different theses. Test both.
4. **Pair by complementary information, not by leftover names.** Family letters in Program A are a catalog. Complementary structures are pre-registered here.
5. **Triggers, ToD, SL/TP, instrument are factors, not more levels.** Cross them after the location × confluence map exists, or hold them locked while that map is built. Do not cartesian them with every pair.
6. **Research readout ≠ product Admit.** Report interaction first. Coin-flip / promote / Admit stay the *later* product filter, with the same honesty locks (n≥30, `|E|<0.03` or PF ∈ [0.95, 1.05] → hold, Admit = `backtest.entry_window`).
7. **Two products stay two products.** `touch` @ 10 ticks and `3c` @ 20 ticks are different theses. Estimate the class × trigger interaction; do not mix them in one StudySpec.

---

## 4. Factor L — variety of levels (representatives)

Use Program A’s family catalog (`docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` §4). Pick **representatives**. Do not invent tokens (`ONMid`, `RTH_Mid`, `RTH_High`, `dSP_high` are not in the closed set).

| Class | Information | Representatives (default closed-set tokens) | Role |
|---|---|---|---|
| **S1 Session extreme** | Named auction edge / liquidity | `ONH` `ONL` `pRTH_High` `pRTH_Low` `OR_High` `OR_Low` | Core |
| **S2 Session open** | Auction open / gap | `dOpen` `RTH_Open` `pRTH_Open` `pdOpen` | Core |
| **S3 Prior range / EQ** | Calendar range / equilibrium | `pdEQ` `pwEQ` | Core |
| **P Prior profile** | Yesterday’s accepted value (typical-price MVP, not VAP) | `pdPOC` `pdVAH` `pdVAL` `pwPOC` | Core |
| **V Session VWAP** | In-play / HTF fair value | `dVWAP` `dVWAP_RTH` `wVWAP` | Confirmation first; `dVWAP_RTH` / `wVWAP` as cores only in B1 |
| **C Developing profile** | Today’s accepted price | `POC_rolling_30min` `APOC` | Confirmation; rarely a core |
| **A Auction leftover** | Unfinished auction | `dSinglePrint_30m_NearestAbove` `dSinglePrint_30m_NearestBelow` | Core or late confirmation |
| **M Flowing mean** | Trend / trailing fair | `SMA_50_5min` `EMA_21_5min` | Confirmation, not a first-screen core |
| **K Pivot** | Local swing structure | `Pivot_5m_High` `Pivot_30m_High` | Confirmation, not a first-screen core |

That is **~24 representatives, 9 classes**. It covers the variety. The other 49 default tokens are siblings or HTF repeats (`pm*`, `SMA_200_*`, `Pivot_1m_*`). Use a sibling only when the representative cell is identified **and** the sibling tests a different horizon (day vs week), not a spelling.

Parked compute (`dHigh`, developing VA, IB, `OR_Mid`, `pVWAP`, MA `15min`) is out of scope until those tokens exist.

---

## 5. Factor C — confluence structures (not leftover extras)

A “confluence” is a **structure**, not a token.

| Structure | Hypothesis | Implementation |
|---|---|---|
| **C0 None** | Location only | `partner_levels: []` is illegal on today’s StudySpec (partner set required). Realization: one dummy is not acceptable. Use a **Setup Builder** core-only replay, or add a later StudySpec “core-only” emission. Until that exists, B1 is Setup / engine, not a kill-list YAML. |
| **C1 Fair-value lock** | Location is in play only near session VWAP | `partner_levels: [dVWAP]`, `from_partners: required`, `min_valid_confluences: 1` — this is Program A L1 |
| **C2 Same-class** | Redundancy. Should *not* add E | e.g. `ONH`+`ONL`, `pdVAH`+`pdVAL`, `SMA_50_5min`+`EMA_21_5min` (illegal sibling — run only as a **negative control**) |
| **C3 Complementary location** | Second map, different information | Pre-registered pairs in §7 |
| **C4 Flowing confirm** | Trend alignment at a location | Core + one of M/K. Different thesis from C3 |
| **C5 Cluster** | Two complementary extras | Core + loc₂ + flow, cap core+partners ≤ 5. Only if C3 and C4 are each identified |
| **C6 Optional presence** | Zone can fire without every name | Mixed required/optional is **Setup Builder only**. StudySpec `from_partners: optional` drops a required `dVWAP` lock. Do not use optional StudySpec as a substitute for C1 |

`from_partners` is all-or-nothing. `valid_count` includes required rules. Required studies that must share a `{dVWAP}` baseline use `min_valid_confluences: 1`. Those locks stay.

---

## 6. The missing axis: B1 vs B2

This is the hole that made Program A feel like the wrong build.

| Model | Partner lock | Question |
|---|---|---|
| **B1 Location-only** | No `dVWAP` requirement | Does this *level class* condition returns at all? |
| **B2 Fair-value-conditioned** | `dVWAP` required | Does this level class matter **when price is also near session fair value**? |

Program A ran **only B2**, then killed cores that were dead *near `dVWAP`*. A session open that is noise next to `dVWAP` can still be a location (gap, drive, fail). A profile edge that is dead alone can be alive next to a flowing mean. Those are Program B cells. They are not “revive `dOpen` on the scalp map.”

Run B1 and B2 on the **same** representatives, same trigger, same width, same window. The contrast *is* the result:

- B1 dead, B2 alive → the edge is “near fair at that name,” not the name.
- B1 alive, B2 dead / thinner → `dVWAP` is the wrong lock for that class.
- Both dead → that class is not a location under this trigger/width.
- Both alive, ΔE ≈ 0, n₂ ≪ n₁ → `dVWAP` only starves.

---

## 7. Pre-registered complementary pairs (C3)

Complementary = different information. Economic siblings stay illegal in one required set (Program A §4).

| Core class | Partner class | Example cells | Why this pair exists |
|---|---|---|---|
| S1 extreme | P profile | `ONH`+`pdVAH`, `ONL`+`pdVAL`, `ONH`+`pdPOC` | Edge vs accepted value |
| S1 extreme | S2 open | `ONH`+`RTH_Open`, `ONH`+`dOpen` | Overnight leftover vs today’s auction open |
| S1 extreme | C developing | `ONH`+`POC_rolling_30min` | Named edge vs today’s accepted |
| S2 open | P profile | `dOpen`+`pdPOC`, `RTH_Open`+`pdPOC` | Open vs yesterday’s fair |
| S2 open | S3 EQ | `RTH_Open`+`pdEQ` | Open vs prior balance |
| P profile | V VWAP | `pdPOC`+`dVWAP`, `pdVAH`+`dVWAP` | This is B2 on a profile core |
| S3 EQ | P profile | `pwEQ`+`pdPOC` | Week balance vs day accepted — **only as a Program B cell**, not Program A L1b revival |
| A leftover | V VWAP | `dSinglePrint_30m_NearestAbove`+`dVWAP` | Unfinished auction near fair |
| Any location core | M flow | `ONH`+`SMA_50_5min`, `pdPOC`+`EMA_21_5min` | C4 — later than C3, not “first leftover extra” |
| Any location core | K pivot | `ONH`+`Pivot_5m_High` | C4 local structure |

**Negative controls (expect no added E):** `ONH`+`ONL`, `pdVAH`+`pdVAL`, `dVWAP`+`dVWAP_RTH`, `SMA_50_5min`+`EMA_21_5min`.

**Illegal in one required set:** `pdVAH`+`pdHigh`, two MAs as *the* thesis (negative control only), `dVWAP`+`VWAP_rolling_30min`, core duplicated as partner.

First C3 pass: **one extra**, `anchor_rules`, required. Not a 9-way AND. Not `global_cluster` (that is a stacked pile after a structure is identified).

---

## 8. Other factors (hold or cross, do not dump into L)

| Factor | Hold while mapping L × C | Cross later |
|---|---|---|
| **T Trigger** | One product at a time | Same cell, `touch` vs `3c`, **same width** (Program A L6b shape) — estimates waiting vs touch per *class*, not only for ONH |
| **W Width** | 10 scalp / 20 swing as two products | Width × class only after a class is identified. Do not pick width by in-sample R |
| **S SL/TP** | 1:1 lock (40/40 or 80/80) | Grid on identified cells only. Lock stays unless the desk page is amended |
| **I Instrument** | MNQ first | MES transfer last, same ticks, money map explicit |
| **Time** | Full RTH (or the copied flatten policy) | Post-hoc 30m NY. Never a StudySpec factor. Admit only via `study promote --admit-tod auto` |
| **OTF** | Off | Validation matrix on a promoted single setup (`docs/research-methodology.md`), not `factors.otf` |
| **Side** | `both` | Direction read after a cell is identified, not a first-screen cartesian |

Flatten, costs, ingest, `intrabar_model`, `exposure_policy` copy the finished Program A L1 slice when Program B is realized, and **log them**. They are not research axes.

---

## 9. Evaluation (holistic readout)

Per cell, n≥30 to *interpret*. n<30 = unidentified, not “killed class.”

| Metric | Meaning |
|---|---|
| `n`, `expectancy_r`, PF, CI | Descriptive screen. Primary rank key is `expectancy_r`, never `total_r` |
| **ΔE vs B1** | Did the partner change the location-only distribution? |
| **ΔE vs B2 / `{dVWAP}` baseline** | Did the extra change the fair-value-conditioned distribution? |
| **ΔE vs partner-alone** | Is this the partner’s edge with a location sticker? |
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
B0  Lock taxonomy + representative table + complementary pair list (this file)
B1  Location-only map          each representative as core, no dVWAP lock
B2  Fair-value contrast        same cores × {dVWAP}          ← Program A L1 is this, on a subset
B3  Negative controls          same-class / sibling pairs
B4  Complementary pairs        C3 on every class that is identifiable in B1 or B2
                               (solo-dead cores stay in)
B5  Flowing confirm            C4 on cells that are identifiable after B4
B6  Cluster                    C5 only if C3 and C4 each beat their baseline
B7  Trigger swap               same width, touch vs 3c, per identified class
B8  ToD overlay                post-hoc; Admit path only if a product is named
B9  Width / SL-TP              only on identified product candidates
B10 Instrument transfer        MES last
```

**Stop rules (Program B):**

- A **pair structure** with every cell `n<30` is unidentified. Retire *that structure* (e.g. “required extra at 10 ticks around ONH”). Do **not** retire the class. Do **not** open all-optional StudySpec discovery on the same slice.
- A **class** is retired from later C4/C5 only if B1, B2, and B4 are all dead or unidentified.
- Product STOP (Program A L2) does not end Program B.

**Still forbidden (honesty, not product taste):**

- StudySpec `from_partners: optional` as a way to keep `dVWAP` required (it does not).
- `min_valid: N` on a study that also emits the 1-partner `{dVWAP}` baseline.
- Promote on `E>0` and `PF≥1.0` (that promotes `pwEQ`).
- Admit via setup-only `constants.entry_window`.
- Inventing tokens, triggers, or factor axes.
- Writing Program B results onto the Program A scalp/swing map as if they were the same contract.

---

## 11. What “complete” means

Complete Program B has, for each of the 9 classes:

1. A B1 estimate (location-only) or a written reason it is impossible (StudySpec partner-required → Setup replay).
2. A B2 estimate (fair-value lock).
3. At least one C3 pair that is complementary, plus one negative control.
4. A trigger-swap on any class that is identified in (1)–(3).
5. A written interaction table (ΔE, thinning), not a kill list.

It does **not** require every sibling token, MA length, or pivot TF. HTF repeats (`pw*` / `pm*`, `SMA_200_*`) are a second horizon pass after the day-scale map exists.

---

## 12. Realization on ThesisTester (when this is built)

Primitives already exist. Missing pieces are **program**, not engine:

| Need | Today | Gap |
|---|---|---|
| `core_level` × `partner_levels` | StudySpec / Study Runner | None for B2, C3, C4, C5 |
| B1 location-only | Partner set required on StudySpec | Setup Builder / engine replay, or a later core-only emission |
| Mixed required/optional | Setup Builder + combo attribution | Do not fake it with `from_partners: optional` |
| Interaction report | Cells have E, n, PF | No first-class ΔE / thinning table. Add a research report, not a new factor axis |
| Representative matrix | Hand YAML | Generate from §4 × §7. Do not hand-author 200 studies |
| Product Admit | `study promote --admit-tod auto` | Unchanged |
| Desk contract | Notion *Process and roadmap* | **Leave it locked.** Program B gets its own page if it runs |

No new factor axes. No golden regen. No engine series. Cap remains core + partners ≤ 5.

---

## 13. What Program A already contributes (do not rerun)

Treat these as **known B2 facts** on the 2024-07-31 → 2026-08-06 MNQ 15s HE slice (costs 0.5/1.0, flatten copied `false`):

- Under **B2 + touch/10/40**, only `ONH` is above the product promote bar. `pwEQ` is a coin-flip hold. The rest of the 24-name kill list bleeds or is thin.
- Required extras around `ONH` at 10 ticks are almost never present (`n<30` / empty). That structure is unidentified. It does **not** prove S1 × C3 is empty at other widths, in B1, or with M/K.
- **B2 + 3c/20/80** wipe. `ONH` does not transfer to wait-for-3c.
- Same-width L6b: waiting **hurts** that ONH location.
- MES transfer of the ONH B2 note **kills** the live claim.

Those facts bound one corner of the map (S1 `ONH`, C1, two products). They are not a holistic combination result.

---

## 14. Decision

The original ask was Program B. The executed work was Program A.

Next research step, if any, is **not** “another ONH leftover pair” and **not** “put `RTH_Open` back on the scalp map.” It is: adopt this concept as a **named program**, lock B0 (this table), and run B1 → B2 contrast on the representative set.

Until that amendment exists on a **new** contract page, the desk stays on wait.
