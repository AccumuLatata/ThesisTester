# Level-as-Anchor Confluence Combination Research Plan

**Document type:** Research protocol + realization map (not an engine series)  
**Date:** 2026-08-19  
**Status:** Protocol published. Inventory verified against `main` (`56c9d59`) via `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`.  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4 (this file is docs-only; no engine/golden touch)  
**Related:** `docs/STUDY_RUNNER.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`, `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md`, `docs/research-methodology.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

---

## 1. Objective

Systematically test **named price locations as the intra-day NQ/ES (MNQ/MES) decision**, and treat every other study token as **evidence that the location is in play** (confluence), not as a peer in a bag.

This matches discretionary practice:

```text
Where is the location I care about?
  → Is it in play (confluence / developing fair value / leftover auction)?
    → How do I enter (touch fade vs 3c wait)?
      → What context admits the trade (OTF, RTH clock, side)?
```

The product already has the two seams this protocol needs:

| Seam | What it answers | Must not confuse with |
|---|---|---|
| **Study Runner** (`core_level` × `partner_levels`) | Which *required* location + evidence sets earn R across a closed cartesian | Within-trade membership |
| **Combo attribution** (Backtest expander) | Which *observed* subsets actually fired when `min_valid_confluences` is low | A new signal model |

The ideal program uses **both**. It does **not** run one giant cartesian of every token against every other token.

---

## 2. Why levels-as-anchor is the correct design

### 2.1 Discretionary economics

A prior-day high, overnight high, or prior POC is a **location**: other traders can name it, rest liquidity against it, and defend or break it. A 21-EMA or a 1-minute pivot is a **moving confirmation**. Stacking moving marks as if they were locations invents a different thesis (trend-following / trailing fair value), not “level + confluence.”

The locked desk contract (Notion *Process and roadmap*, 2026-08-19) already encodes this:

- Two products, never one cartesian: **scalp = `touch` @ `1min`**, **swing = `3c` @ `1min`**.
- Zone width locked from a distance audit (10 scalp / 20 swing ticks on MNQ). Do not pick width by backtest R.
- Required first partner: **`dVWAP`**.
- Mode: **`anchor_rules`**. `global_cluster` only after survivors, and only for a stacked pile of 2–3 marks.
- Sequence: kill list → pairwise among survivors → post-hoc ToD → SL/TP grid → rush check (touch vs 3c).
- Primary metric: **`expectancy_r`**. Never rank on `total_r`. ToD is never a StudySpec factor.

This plan **keeps those locks** and completes the scientific coverage of “all *useful* combinations” without violating them.

### 2.2 Engine semantics already match the mental model

`anchor_rules` (see `docs/ANCHOR_CONFLUENCE.md`):

1. One **anchor** column must exist.
2. Each partner is a rule (`tolerance_ticks`, `required` / `optional`).
3. `min_valid_confluences` is the evidence threshold **in addition to** all required rules.

Study expand (`docs/STUDY_RUNNER.md` RS2):

- `anchor_rules`: `anchor_level = core`, one rule per partner, `from_partners ∈ {required, optional}`.
- `global_cluster`: `selected_levels = [core] + partners`, and **`min_confluences = max_confluences = N`**. A missing core zeros the whole cell (LC4 fail-closed at API).
- Hard cap: **core + partners ≤ 5**. Partner ≠ core. Duplicate partner tokens fail closed.

So “test levels as the anchor against confluences” is already the StudySpec native shape: vary `core_level`, vary `partner_levels` as **sets**, keep product constants locked.

### 2.3 Why a full token cartesian is the *wrong* ideal (even with infinite compute)

Compute is not the constraint. **Selection bias** is.

Bailey & López de Prado (*The Probability of Backtest Overfitting*; Deflated Sharpe Ratio) show that the number of **trials you looked at** — not the ones you report — inflates Sharpe / expectancy. ThesisTester already treats ranked cells as descriptive (`multiple_testing: warn|error`; `docs/ASSUMPTIONS_AND_LIMITATIONS.md`). A 73-core × 72-partner × 2-mode × 5-trigger × 4-tf × 5-OTF × 2-side grid is ~2×10⁶ cells **before** 2- and 3-partner sets. That is not a complete research program; it is a machine for crowning noise.

Practitioner confluence literature (ORB + VWAP + volume-profile work) converges on the same operational bound: **2–3 complementary filters outperform 8-filter walls**, which starve the sample. Volume-profile geometry alone is often folklore; the value is **location + confirmation**, not stacking siblings from the same family.

“All useful combinations” therefore means: **every economically distinct hypothesis is tested once, in order, with a pre-registered kill/promote rule** — not that every syntactic product of `closed_level_token_set` is a cell.

---

## 3. Verified token inventory (studies)

Authoritative implication function: `thesistester.study.schema.closed_level_token_set`.  
Static names: `thesistester.levels.catalog.STATIC_STUDY_LEVEL_NAMES`.  
Product defaults: `thesistester.levels.defaults.DEFAULT_LEVELS_SETTINGS`.

Verified 2026-08-19:

| Universe | Count | Rule |
|---|---:|---|
| Static catalog | **49** | Always admitted (compute gates may still be off at generate time) |
| Default-implied extras | **24** | SMA/EMA × TF, rolling VWAP/POC, `prev30mVWAP`, `Pivot_*` |
| **Default closed set** | **73** | `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` |
| Widget-maximal extras | **+30** | Full `INDICATOR_LENGTH_OPTIONS` + extra VWAP/POC windows + `prev30mVWAP_2/3` |
| Widget-maximal closed set | **103** | Still not a cartesian license |

Reproduce:

```bash
python3 -c "from thesistester.study.schema import closed_level_token_set; from thesistester.levels.defaults import DEFAULT_LEVELS_SETTINGS; print(len(closed_level_token_set(DEFAULT_LEVELS_SETTINGS))); print('\\n'.join(sorted(closed_level_token_set(DEFAULT_LEVELS_SETTINGS))))"
```

### 3.1 How a token becomes legal

A `core_level` / partner string is valid iff it is in the closed set implied by `study.levels` after `{**DEFAULT_LEVELS_SETTINGS, **study.levels}`:

1. **Static** — session / prior-profile / session-VWAP / single-print / APOC names. Rolling VWAP/POC are **never** static.
2. **Implied** — `SMA_{n}_{tf}` / `EMA_{n}_{tf}` from lengths × timeframes (`null` TFs → bare `SMA_n`; explicit `[]` → no MA tokens); `VWAP_rolling_*` / `POC_rolling_*` from windows; `prev30mVWAP*` only if `prev30m_vwap_enabled`; `Pivot_*` only if `pivots_enabled`. Pivot spelling is engine truth: `Pivot_1m_*` / `Pivot_5m_*` / `Pivot_30m_*` / `Pivot_4h_*` (not `Pivot_1min_*`).
3. Unknown tokens fail at `validate_study_spec`. Missing columns fail at `api.generate_signals` (LC4).

Widget catalogs (`INDICATOR_LENGTH_OPTIONS` = 9/20/21/50/100/200; `VWAP_WINDOW_OPTIONS` = 15min/30min/1h/4h; `POC_WINDOW_OPTIONS` = 30min/1h/4h) are **settings editors**, not implied tokens.

### 3.2 Static catalog (49)

**Session structural (30)** — `SESSION_STRUCTURAL_LEVEL_NAMES`:

`ONH` `ONL` `pONH` `pONL` `AsiaHigh` `AsiaLow` `LondonHigh` `LondonLow` `OR_High` `OR_Low` `RTH_Open` `pRTH_Open` `pRTH_High` `pRTH_Low` `prevSettlement` `dOpen` `wOpen` `mOpen` `pdOpen` `pwOpen` `pmOpen` `pdHigh` `pdLow` `pwHigh` `pwLow` `pmHigh` `pmLow` `pdEQ` `pwEQ` `pmEQ`

**Prior profile (9)** — always-on typical-price MVP `(H+L+C)/3`, 70% VA, `shift(1)`:

`pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC`

**Session VWAP (4)** — gated by `session_vwap_enabled` at compute, admitted statically:

`dVWAP_RTH` `dVWAP` `wVWAP` `mVWAP`

There is **no** `wVWAP_RTH` / `mVWAP_RTH`.

**Single prints (4)**:

`dSinglePrint_30m_NearestAbove` `dSinglePrint_30m_NearestBelow` `pSinglePrint_30m_NearestAbove` `pSinglePrint_30m_NearestBelow`

**APOC (2):** `APOC` `pAPOC`

### 3.3 Default-implied extras (24)

| Family | Tokens |
|---|---|
| SMA | `SMA_50_1min` `SMA_50_5min` `SMA_50_30min` `SMA_200_1min` `SMA_200_5min` `SMA_200_30min` |
| EMA | `EMA_9_1min` `EMA_9_5min` `EMA_9_30min` `EMA_21_1min` `EMA_21_5min` `EMA_21_30min` |
| Rolling VWAP | `VWAP_rolling_30min` `VWAP_rolling_4h` |
| Rolling POC | `POC_rolling_30min` |
| Prev 30m VWAP | `prev30mVWAP` (validity=1; age-1 spelling, not `prev30mVWAP_1`) |
| Confirmed pivots | `Pivot_1m_High` `Pivot_1m_Low` `Pivot_5m_High` `Pivot_5m_Low` `Pivot_30m_High` `Pivot_30m_Low` `Pivot_4h_High` `Pivot_4h_Low` |

`prev30mVWAP_hit_m1` / `prev30mVWAP_hit_m5` are **non-level diagnostics** (`NON_LEVEL_OUTPUT_COLUMNS`). They are not StudySpec tokens.

### 3.4 Opt-in extras (widget-maximal, +30)

Only if `study.levels` enables them:

- Extra MA lengths 9/20/21/100 (SMA) and 20/50/100/200 (EMA) × `{1min,5min,30min}`
- `VWAP_rolling_15min` `VWAP_rolling_1h`
- `POC_rolling_1h` `POC_rolling_4h`
- `prev30mVWAP_2` `prev30mVWAP_3` (validity ≥ 2 / 3)

MA `15min` timeframe is **not** an engine TF (`SUPPORTED_INDICATOR_TIMEFRAMES` = 1min/5min/30min). Do not invent `SMA_50_15min`.

### 3.5 Not tokens (do not invent)

Parked compute (LC §8) — columns the engine does **not** emit:

`dHigh` `dLow` `dEQ` `RTH_High` `RTH_Low` `dVAH` `dVAL` `dPOC` `VAH_rolling_*` `VAL_rolling_*` `OR_Mid` IB / 60m initial balance `pVWAP` `pRTH_VWAP` ETH-only VWAP classic floor pivots (PP/R1)

Hit flags, OHLCV, `session`, `settlement` are not levels.

### 3.6 Non-level factor axes (closed)

These are **not** confluence tokens. They are how the same location thesis is *entered* or *admitted*:

| Axis | Domain | Role in this protocol |
|---|---|---|
| `confluence_mode` | `anchor_rules`, `global_cluster` | Anchor first; global only on 2–3 survivor stacks |
| `trigger` | `touch`, `reject`, `break`, `reclaim`, `3c` | Product lock: scalp=`touch`, swing=`3c`. Others = later sensitivity |
| `trigger_timeframe` | `base`, `1min`, `5min`, `15min` (not `30min`) | Product lock: `1min` |
| `otf` | normalized OTF configs | Context filter **after** location survivors (`docs/research-methodology.md`) |
| `direction` | `long`, `short`, `both` | First screen: `both`. Side from trade `direction` / combo×direction, not a first cartesian |

Constants that are **locks**, not axes: `tolerance_ticks`, SL/TP, `min_valid_confluences`, `from_partners`, costs, `intrabar_model`. Time-of-day is post-hoc (`entry_rth_segment`); constrain later via `constants.entry_window` (Admit), never as a factor.

---

## 4. Economic taxonomy (how to think, not how to cartesian)

Every default token sits in exactly one **family**. Combinations are useful only when families are **complementary** (different information), not when they are **siblings** (same information, different spelling).

| Family | Tokens | Default role | Why |
|---|---|---|---|
| **S1 Session extremes** | `ONH` `ONL` `pONH` `pONL` `AsiaHigh` `AsiaLow` `LondonHigh` `LondonLow` `OR_High` `OR_Low` `pRTH_High` `pRTH_Low` | **Anchor candidates** | Named liquidity / range edges |
| **S2 Session opens** | `RTH_Open` `pRTH_Open` `dOpen` `wOpen` `mOpen` `pdOpen` `pwOpen` `pmOpen` | **Anchor candidates** | Auction open / gap / week-month context |
| **S3 Prior range** | `pdHigh` `pdLow` `pwHigh` `pwLow` `pmHigh` `pmLow` `pdEQ` `pwEQ` `pmEQ` `prevSettlement` | **Anchor candidates** | Calendar range / equilibrium. Raw H/L are often redundant with VA edges; EQ is the cleaner first screen |
| **P Prior profile** | `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC` | **Anchor candidates** (swing also: HTF VA) | Accepted value. Typical-price MVP — treat as location, not true VAP |
| **V Developing VWAP** | `dVWAP` `dVWAP_RTH` `wVWAP` `mVWAP` `VWAP_rolling_30min` `VWAP_rolling_4h` `prev30mVWAP` | **Confirmation** (`dVWAP` required first). Swing-only cores: `wVWAP` `mVWAP` | In-play fair value. `dVWAP` is not also a kill-list core |
| **C Developing profile** | `POC_rolling_30min` `APOC` `pAPOC` | **Confirmation** (rarely a core) | Intraday accepted price; noisy as a location |
| **A Auction leftover** | four `*SinglePrint_30m_*` | **Anchor or late confirmation** | Unfinished auction; thin by construction |
| **M Moving average** | default SMA/EMA set | **Confirmation on survivors only** | Moves. Illegal as first-screen cores |
| **K Pivot** | eight `Pivot_*` | **Confirmation on survivors only** | Swing structure, not a session location |

**Complementary** = different families (e.g. `ONH` + `dVWAP` + `pdVAL`).  
**Sibling / illegal stack** = same family in one partner set (e.g. `SMA_50_1min` + `SMA_50_5min`; `pdVAH` + `pdHigh`; `dVWAP` + `dVWAP_RTH`). One representative per family per cell.

Suggested Setup defaults (`ONH` `ONL` Asia/London `OR_*` `RTH_Open` `pRTH_*` `pdHigh` `pdLow` `pdPOC` `VWAP_rolling_30min`) are a **chart convenience subset**, not the research kill list.

---

## 5. Two combination problems (keep them separate)

### 5.1 Prospective — required evidence (StudySpec)

Question: *If I refuse to trade location L unless evidence set E is present, do I earn R?*

Mechanism: `anchor_rules` + `from_partners: required` + `min_valid_confluences` matching the required count. Each cell is a **causal** thesis: the zone does not exist without those partners.

This is the only honest way to rank “which confluence matters.” Optional partners + low `min_valid` mix theses inside one expectancy number.

### 5.2 Retrospective — observed evidence (attribution)

Question: *When I allowed any 1-of-N optional supports, which subsets actually traded?*

Mechanism: already shipped (`docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` Phases 1–6): exact combo, membership, parsed level-count, soft pairs, combo×direction, opt-in combo×3c variant.

Use this **after** a survivor exists and you deliberately run `from_partners: optional` with `min_valid_confluences: 1` as a **discovery** pass. Then promote observed pairs into a **new required-partner study** on a later chronological slice. Do **not** auto-tighten Setup Builder from the same sample (explicit non-goal of combo attribution).

Nested-set honesty: exact combo treats `A|B` and `A|B|C` as different; pairs exist specifically so a productive pair is not hidden by a third tag.

---

## 6. Ideal protocol (complete useful coverage)

Two locked products. One instrument first (MNQ). One confirmation (`dVWAP`) until a location survives. Then complementary families only. Context last. Robustness last.

```text
L0  Locks (do not cartesian)
L1  Location kill-list          core × {dVWAP}          required
L1b Alternate-confirm retry     killed cores × 1 other family (optional completeness)
L2  Pairwise                    survivors × complementary family (2–3 marks)
L3  Triple                      only if two complementary pair Δs are material
L4  Context                     OTF matrix, then direction read, then post-hoc ToD
L5  Economics                   SL/TP grid (SL ≤ 80 MNQ ticks), costs on
L6  Rush check                  same survivor, touch vs 3c (reentry leak)
L7  Transfer                    ES/MES; second dataset; WFO / holdout
```

Do not skip ahead because a cell is green. Do not put a killed scalp name back on the scalp map because a 30m ToD slice was green.

### 6.0 Locks (L0)

| Lock | Scalp | Swing |
|---|---|---|
| Trigger | `touch` @ `1min` | `3c` @ `1min` |
| Zone / `tolerance_ticks` | 10 | 20 |
| SL / TP (first screen) | 40 / 40 | 80 / 80 |
| Partner | `dVWAP` required | `dVWAP` required |
| Mode | `anchor_rules` | `anchor_rules` |
| `from_partners` | `required` | `required` |
| Direction | `both` | `both` |
| Instrument first | MNQ | MNQ |
| Ingest | Quantower HE 15s, `source_timezone: UTC`, `ingestion_mode: 15s_primary_derive_1m`, `intrabar_model: subtimeframe_conservative` | same |
| Money | $0.50/tick MNQ; commission/slippage **non-zero** before trusting ranks | same |
| Rank | `expectancy_r`; `min_trades: 30`; `multiple_testing: warn` | same |
| Mix forbidden | touch with 3c, 10 with 20, both modes, long vs short, in one first study | same |

Grid / validation / walk_forward always `enabled: true|false`. Never bare `{}`. `--confirm` if `run_count >= confirm_above_runs`. Never auto-run a promote draft.

### 6.1 L1 — Location kill-list

**Hypothesis:** location L is worth a product *at all* when developing session VWAP is also in the zone.

**Cores (current desk list):**

- Profile: `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC`
- Session extremes: `ONH` `ONL`
- Single prints (4)
- EQ: `pdEQ` `pwEQ` `pmEQ`
- Opens: `dOpen` `pdOpen` `wOpen` `pwOpen` `mOpen` `pmOpen` `RTH_Open` `pRTH_Open`
- Swing-only extras as cores: `wVWAP` `mVWAP`

**Stay off L1 unless explicitly extended:** MAs and pivots as cores; `pRTH_High`/`pRTH_Low`; `pONH`/`pONL`; Asia/London; OR; `prevSettlement`; raw `pd/pw/pm High/Low`; `APOC`/`pAPOC`; `dVWAP_RTH`; `dVWAP` as a core.

**Cell math:** one product × N cores × 1 partner set `{dVWAP}` × locked trigger/tf/mode = **N cells**. Scalp 24 + RTH add-on 2 is already the executed map. Swing is the same list plus `wVWAP`/`mVWAP`.

**Promote rule (pre-register, do not tune after seeing ranks):**

- Ranked if `trade_count >= 30` and `expectancy_r > 0` **and** profit factor ≥ 1.0.
- Coin-flip band: `|expectancy_r| < 0.03` or PF ∈ [0.95, 1.05] → hold for L1b, do not pairwise yet.
- Kill: negative expectancy at n≥30, or n too thin after a full 2y sample.
- Descriptive only. A +0.07R survivor is a **license to pairwise**, not a live edge.

### 6.2 L1b — Alternate-confirm retry (completeness pass)

A location can be real and still die next to `dVWAP` (fair value already *is* the location; or VWAP is elsewhere all day). Completeness requires **one** retry per killed/coin-flip core against **one representative from a different confirmation family**, still `anchor_rules` / required / same product locks:

| Retry family | One representative | When |
|---|---|---|
| Prior day profile | `pdPOC` or nearer of `pdVAH`/`pdVAL` | Session-extreme cores |
| Session leftover | nearer single-print | Profile / EQ cores |
| HTF VWAP | `wVWAP` (scalp) / already a swing core | Opens / EQ |
| Rolling VWAP | `VWAP_rolling_30min` | If `dVWAP` was redundant with the core |
| One MA | `EMA_21_5min` **only** | Last retry, survivors-or-coin-flip only |

Still **one partner per cell**. Do not AND two retries. If L1b also kills the name, it is off that product’s map.

This is the “don’t miss a useful combo” clause. It is **O(cores × 1–2)**, not O(cores × 73).

### 6.3 L2 — Pairwise among survivors (the actual combination test)

**Hypothesis:** given location L that already survived L1, does a *second, complementary* mark improve expectancy vs the `dVWAP`-only baseline **on the same sample definition**?

Partner sets (exactly one extra family; `dVWAP` stays):

```text
[dVWAP, X]
```

where X is one representative from a family **≠ V and ≠ L’s family**.

**Default X menu for an ONH-class survivor** (complete useful menu, not a grab bag):

| X | Family | Discretionary meaning |
|---|---|---|
| `pdPOC` | P | Value accepted into the overnight edge |
| `pdVAH` or `pdVAL` (the one nearer ONH/ONL) | P | VA edge, not both |
| `pdEQ` | S3 | Prior equilibrium (skip if L is already an EQ) |
| `wVWAP` | V-HTF | Weekly fair value (sibling of `dVWAP` only at HTF) |
| `POC_rolling_30min` | C | Intraday POC |
| nearer `pSinglePrint_30m_*` | A | Leftover auction |
| `OR_High` / `OR_Low` (matching side) | S1 | Only after RTH exists; skip if L is OR |
| `EMA_21_5min` | M | One MA, not the MA zoo |
| `SMA_50_5min` | M | Second MA cell, not stacked with EMA in the same set |
| `Pivot_30m_High` / `_Low` (matching side) | K | One HTF pivot |

**Illegal L2 sets:** two MAs; two pivots; `pdVAH`+`pdHigh`; `dVWAP`+`dVWAP_RTH`; `dVWAP`+`VWAP_rolling_30min` (same-family developing VWAP); core duplicated as partner.

**Baseline cell required in the same study:** `{dVWAP}` alone, so Δ expectancy / Δ n / Δ PF is a paired comparison, not a cross-study glance.

**Promote to L3:** extra mark raises OOS-or-holdout `expectancy_r` without collapsing n below 30, and the Δ is not explained only by “fewer trades.” Else keep the pair as optional-discovery only (L2-disc).

**L2-disc (optional, after required L2):** same cores, `from_partners: optional`, `min_valid_confluences: 1`, partners = `{dVWAP, X1, X2, X3}` (≤4 partners). Read **Pairs** + exact combo×direction. Promote only pairs that also won as **required** on a later slice.

### 6.4 L3 — Triple (rare)

Only when **two different** L2 extras each beat the `dVWAP` baseline. Then one cell:

```text
[dVWAP, X, Y]
```

with X, Y complementary. Cap 3 marks (desk lock). Do not build 4- and 5-level ANDs. `max_confluences ≤ 5` is an engine cap, not a research target.

### 6.5 L4 — Context (not confluence)

Apply **after** a location thesis exists.

1. **OTF** — fixed 5-config matrix from `docs/research-methodology.md` (`no_otf`, 15m, 30m, 15+30, 5+15+30). Chronological train/OOS. Train selects; OOS evaluates. Fewer trades ≠ better.
2. **Direction** — do not cartesian `long`/`short` on the first screen. Read combo×direction / Long-Short KPIs. If one side is the whole edge, a **follow-up** study may lock that side.
3. **ToD** — post-hoc NY `entry_rth_segment` / 30m on finished zips. `n>=15` descriptive; **`n<30` never Admitted**. Focus ≠ Admit.

### 6.6 L5 — Economics

Per-cell SL/TP grid on survivors only. MNQ SL at or under 80 ticks ($40). Grid is **not** a factor axis (Inspect `best_grid_*` / `grid_results.parquet`). Costs stay on.

### 6.7 L6 — Rush check

Same survivor, two locked products (touch/10 vs 3c/20). Measures the known leak (re-entering the touch 2–3 times). Do not mix in one study.

### 6.8 L7 — Transfer / robustness

Repeat L1–L6 on ES/MES **only for survivors**, not the full kill list. Then walk-forward (`enabled: true` on a **small** survivor study). Then a later chronological dataset. Failure to transfer kills the live claim, not the descriptive MNQ note.

---

## 7. Multiple-testing and honesty (normative)

| Rule | Why |
|---|---|
| Count **studies and cells looked at**, not just reported winners | DSR / PBO: trials include killed cells |
| Primary = `expectancy_r`; secondary = PF, max DD, n, total R as **context** | `total_r` crowns high-frequency noise |
| `min_trades: 30` for ranking; hide-thin on attribution (`min_trades=10` UI default) | Low-n expectancy is not a result |
| `multiple_testing: warn` on screens; `error` (no crowning) on large L2 menus | Study report already supports this |
| Family-wise, not token-wise | 12 MA tokens are ~2 hypotheses (fast/slow), not 12 |
| Chronological holdout: select on train / early years, evaluate on later years | No shuffle |
| OTF protocol stays the OTF SoT | Do not invent a second OOS rule |
| Combo attribution is diagnostic | Observed-only; membership/pairs double-count; 3c names may be tested-level-only |
| Profile math is typical-price MVP | Do not claim VAP precision |
| Zero-cost ranks are invalid for promotion | Commission + slippage required |

SOTA gap (proposal §3): PBO / deflated Sharpe / CPCV are **not implemented**. Until they are, the operational substitute is: **small staged studies, pre-registered promote rules, holdout, and `multiple_testing: error` before any “best cell” language.**

---

## 8. How to realize it in ThesisTester today

No new factor axis. No engine change. No pairwise-zone emission. Realization is **authoring discipline + the existing CLI**.

### 8.1 Surfaces

| Step | Tool |
|---|---|
| Author | Studies **Build StudySpec** or YAML (`examples/studies/` as shape, not as the map) |
| Preview count | `python -m thesistester study expand SPEC --output-dir OUT` |
| Run | `study run …` (`--confirm` if ≥ `confirm_above_runs`) |
| Rank | `study report OUT` + Inspect briefing / quality panes |
| ToD / grid | Inspect post-hoc (not factors). Admit via `study promote --admit-tod auto` **only** when n≥30 |
| Observed combos | Classic Backtest expander on a promoted single-setup replay, or bundle `confluence_combo_*` |
| Log | One Notion **Runs** row + one **Results** row per cell (desk contract) |

### 8.2 StudySpec shape (every L1/L2 study)

```yaml
schema_version: 1
study:
  name: scalp_touch_10_ONH_pairs   # ^[A-Za-z0-9][A-Za-z0-9_-]*$
  workers: 1                       # raise only on POSIX after smoke
  confirm_above_runs: 200
  dataset:
    path: data/mnq_15s.csv
    instrument: MNQ
    format_profile: quantower_history_exporter
    source_timezone: UTC
    ingestion_mode: 15s_primary_derive_1m
  levels: {}                       # DEFAULT merge; add windows only if you name those tokens
  constants:
    direction: both
    tolerance_ticks: 10            # 20 on swing
    min_valid_confluences: 1
    trigger_params: {}
    entry_window: null
    backtest:
      stop_loss_ticks: 40          # 80 on swing
      take_profit_ticks: 40
      exposure_policy: single_position
      commission_per_side: 0.5
      slippage_ticks: 1.0
      intrabar_model: subtimeframe_conservative
    grid: {enabled: false}         # true only on L5 survivors
    validation: {enabled: false}
    walk_forward: {enabled: false}
  factors:
    core_level: [ONH]              # L1: the kill-list; L2: survivors only
    partner_levels:
      - [dVWAP]                    # baseline cell — required
      - [dVWAP, pdPOC]
      - [dVWAP, pdVAL]
      - [dVWAP, wVWAP]
      - [dVWAP, EMA_21_5min]
    confluence_mode: [anchor_rules]
    trigger: [touch]               # swing: [3c]
    trigger_timeframe: [1min]
    # otf / direction omitted until L4
  mode_rules:
    anchor_rules:
      selected_levels: []
      anchor_level: "${core_level}"
      confluence_rules:
        from_partners: required
  report:
    primary_metric: expectancy_r
    secondary_metrics: [profit_factor, max_drawdown_r, trade_count, total_r]
    min_trades: 30
    group_by: [core_level, partner_levels]
    multiple_testing: warn
```

L1 is the same file with `core_level: [/* kill list */]` and `partner_levels: [[dVWAP]]` only.

### 8.3 What not to copy from shipped examples

| Example | Useful as | Harmful if copied blindly |
|---|---|---|
| `pdPOC_ma_confluence_battery.yaml` | Stage-first *shape* (40 cells) | Mixes both modes, 5 triggers, 4 TFs, 5 OTFs, MA partners on an un-killed core — that is a teaching cartesian, not this protocol |
| `pRTH_open_ma.yaml` | MNQ 15s ingest + costs | `pRTH_Open` is already **killed** on scalp; MA-as-first-partner without `dVWAP`; mixed touch/3c; wide grid |
| `dopen_ma_3c_mnq.yaml` | Tiny 3c shape | Legacy 1m primary (different dataset identity) |

### 8.4 Cell-budget guide (complete useful, not maximal syntactic)

| Stage | Typical cells | Notes |
|---|---:|---|
| L1 scalp | 24–28 | Already run |
| L1 swing | ~28 | In flight per desk roadmap |
| L1b | ≤ 2 × killed cores | One retry family each |
| L2 per survivor | 8–12 incl. baseline | Complementary menu above |
| L3 | 0–3 | Rare |
| L4 OTF | 5 × survivors | Existing OTF matrix |
| L6 rush | 2 × survivors | Separate studies |
| L7 ES transfer | L2 size | Survivors only |

A **complete** program for one instrument × two products is on the order of **low hundreds of cells**, staged, not millions.

### 8.5 Reading results

1. Overview ranked by `expectancy_r` (n≥30).
2. Group-by `core_level` then `partner_levels` — L1 asks “which location”; L2 asks “which extra mark vs `[dVWAP]`.”
3. Inspect NY ToD on the **finished** zip. Do not Admit thin buckets.
4. If L2-disc was run: Backtest **Pairs** (anchor-aware `ONH|X` only when mode is `anchor_rules`) and exact combo×direction.
5. Log the kill/stay/coin-flip decision the same day.

---

## 9. Later product work (only if the loop should be first-class)

These are **optional** future series. Do not start them to “finish” this protocol — YAML + CLI already realize it.

| Idea | Why | Constraint |
|---|---|---|
| Family catalog helper (`S1`/`P`/`V`/…) | Stop sibling stacks at emit time | Research classification; must not fork `catalog.py` engine names |
| Study Builder “complementary partners” widget | One representative per family | Fail closed; no new factor axis |
| Stage recipes (L1/L2/L4) in Grok pack | Copy-ready coworker prompts | Same RS-D5 hard rules: no invent, no auto-run promote |
| PBO / DSR / CPCV | Close the SOTA validation gap | Own golden-gated analytics series; default-off |
| Directed membership / pairs | PR 6 left those tabs undirected | Analytics-only |
| Engine “one zone per valid rule” | Would multiply fills | Explicit non-goal of combo attribution; likely never default |

Do **not**: invent tokens, add ToD as a factor, cartesian width, genetic search, or auto-recommend “drop this level” from attribution.

---

## 10. Decision checklist (next run)

Ask before expanding any StudySpec:

1. Which **product** (scalp vs swing)? Which **lock** stays identical?
2. Which **stage** (L1–L7)? If the answer is “this 30m window” or “a new axis,” it is drift — do not run.
3. Is every core a **location family** (S/P/A), not M/K?
4. Is every partner set **one representative per family**, with `dVWAP` first?
5. Is there a **baseline cell** for any pairwise claim?
6. Are costs on? Is ingest 15s-primary? Is `--confirm` required?
7. What is the **pre-registered** promote/kill rule?

---

## 11. Copy-ready coworker prompt

```text
You are an external ThesisTester coworker. Follow docs/STUDY_RUNNER.md,
docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md, and examples/studies/agents/SYSTEM.md.

Hard rules:
- Work regression-safe. Do not invent factor axes, tokens, or triggers.
- Do not mix scalp (touch @ 1min, 10 ticks, 40/40) with swing (3c @ 1min, 20 ticks, 80/80).
- Mode is anchor_rules. Partner sets must include dVWAP. One representative per family.
- ToD is never a factor. Do not auto-run a promote draft. --confirm if run_count is high.
- Rank on expectancy_r. Descriptive ≠ edge. Log kill/stay with n and PF.

Task: author/expand/run only the next protocol stage the human names (L1, L1b, L2, …).
1. Expand and report run_count.
2. Run (add --confirm when required).
3. Report ranked / low-N / unresolved with honesty.
4. Promote draft only if asked; STOP for human edit + confirm.
```

---

## 12. Status vs desk roadmap (2026-08-19)

| Protocol stage | Desk status | Implication |
|---|---|---|
| L0 locks + distance audit | Done | Widths frozen |
| L1 scalp | Done — only **ONH** stays (+0.07R, n=47, PF 1.16, descriptive) | L2 scalp = ONH pairs |
| L1 RTH add-on | Done — both killed | Do not retry as scalp cores |
| Scalp ToD | Done — no solid green; do not Admit | |
| L1 swing | Running | Wait; do not pairwise swing names yet |
| L1b | Not started | Completeness for coin-flip / killed **locations** only |
| L2+ | Waiting | ONH plus any swing survivors |

The next *useful* combination study on the current scalp map is **not** a new kill list. It is **L2: `ONH` + `dVWAP` + one complementary X**, with `{dVWAP}` as the baseline cell, same scalp locks.
