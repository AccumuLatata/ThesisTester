# Level-as-Anchor Confluence Combination Research Plan

**Document type:** Research protocol + realization map (not an engine series)  
**Date:** 2026-08-19  
**Status:** Protocol published, then amended the same day against engine semantics, Study expand, and the locked desk contract (Notion *Process and roadmap*). Inventory still verified against `main` (`56c9d59`) via `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)`.  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4 (this file is docs-only; no engine/golden touch)  
**Related:** `docs/STUDY_RUNNER.md`, `docs/ANCHOR_CONFLUENCE.md`, `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`, `docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md`, `docs/research-methodology.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/STUDY_ADMIT_FOLLOWUP_IMPLEMENTATION_PLAN.md`  
**Desk-page switch (Notion contract, do not dump this protocol):** `docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md`

Normative amendments in this revision (do not silently revert):

1. L1 coin-flip is applied **before** promote. `pwEQ` stays held.
2. Required L1/L2 studies use `min_valid_confluences: 1` (all required partners still must fire).
3. L2 all-low-N → **stop**. Do not open all-optional discovery on the same slice.
4. L1b is **named coin-flips only** (`pwEQ`). Killed names stay off the map.
5. Admit is `backtest.entry_window` (+ `grid.entry_window`), not setup-only `constants.entry_window`.
6. L4 OTF is the Validation matrix, **not** a StudySpec `otf` factor.
7. L0 names `exposure_policy`, flatten-at-close, and the ES/MES money map.
8. Complementary means **different information**. Family letters are a catalog, not a license.

---

## 1. Objective

Systematically test **named price locations as the intra-day NQ/ES (MNQ/MES) decision**, and treat every other study token as **evidence that the location is in play** (confluence), not as a peer in a bag.

This matches discretionary practice:

```text
Where is the location I care about?
  → Is it in play (confluence / developing fair value / leftover auction)?
    → How do I enter (touch fade vs 3c wait)?
      → What context admits the trade (RTH clock, side; OTF only as a later Validation matrix)?
```

The product already has the two seams this protocol needs:

| Seam | What it answers | Must not confuse with |
|---|---|---|
| **Study Runner** (`core_level` × `partner_levels`) | Which *required* location + evidence sets earn R across a closed cartesian | Within-trade membership |
| **Combo attribution** (Backtest expander) | Which *observed* subsets actually fired when optional rules are present | A new signal model |

The ideal program uses **both**. It does **not** run one giant cartesian of every token against every other token. StudySpec `from_partners` is all-or-nothing today — it does **not** emit “`dVWAP` required + X optional.” Do not pretend YAML already covers that discovery shape (§5.2, §9).

---

## 2. Why levels-as-anchor is the correct design

### 2.1 Discretionary economics

A prior-day high, overnight high, or prior POC is a **location**: other traders can name it, rest liquidity against it, and defend or break it. A 21-EMA or a 1-minute pivot is a **moving confirmation**. Stacking moving marks as if they were locations invents a different thesis (trend-following / trailing fair value), not “level + confluence.”

The locked desk contract (Notion *Process and roadmap*, 2026-08-19) already encodes this. **This plan does not replace that page.** If a step here is not on that page, it is either a realization detail or it is forbidden until the desk page is amended on purpose.

Desk locks this plan keeps:

- Two products, never one cartesian: **scalp = `touch` @ `1min`**, **swing = `3c` @ `1min`**.
- Zone width locked from a distance audit (10 scalp / 20 swing ticks on MNQ). Do not pick width by backtest R. Do not cartesian 10 vs 20.
- Required first partner: **`dVWAP`**. It is not also a kill-list core.
- Mode: **`anchor_rules`**. `global_cluster` only after survivors, and only for a stacked pile of 2–3 marks.
- Desk sequence: kill list → pairwise among survivors → post-hoc ToD → SL/TP grid → rush check.
- Primary metric: **`expectancy_r`**. Never rank on `total_r`. ToD is never a StudySpec factor.
- Killed scalp names stay **off the scalp map**. A green 30m slice does not revive them.

This plan adds realization rules (engine `min_valid`, Admit path, L2 power stop, money map) and **does not** insert new research steps in front of pairwise. L1b is scoped to desk-named coin-flips only. OTF is not a stage between pairwise and ToD.

Swing L1 extras `wVWAP` / `mVWAP` as cores (still with required `dVWAP`) are a **desk-listed VWAP-stack thesis**, not complementary confirmation. Allowed only because the desk listed them as swing kill-list extras.

### 2.2 Engine semantics (StudySpec native shape)

`anchor_rules` (engine: `thesistester/engine/anchor_confluence.py`):

1. One **anchor** column must exist.
2. Each partner is a rule (`tolerance_ticks`, `required` / `optional`).
3. A zone emits only when **every required rule is valid** and `valid_count >= min_valid_confluences`.
4. `valid_count` includes **all** valid rules, required and optional. It is **not** “this many extras on top of the required set.”

Study expand (`from_partners`) stamps the **same** `required` flag on every partner. Mixed required/optional rules exist in Setup Builder / the engine; they are **not** a StudySpec emission today.

Study expand (`docs/STUDY_RUNNER.md` RS2):

- `anchor_rules`: `anchor_level = core`, one rule per partner, `from_partners ∈ {required, optional}`.
- `global_cluster`: `selected_levels = [core] + partners`, and **`min_confluences = max_confluences = N`**. A missing core zeros the whole cell (LC4 fail-closed at API).
- Hard cap: **core + partners ≤ 5** (`len(partner_set) + 1 <= 5`). Partner ≠ core. Duplicate partner tokens fail closed.
- Per cell: `1 <= min_valid_confluences <= len(partner_set)` or expand fails.

So “test levels as the anchor against confluences” is already the StudySpec native shape: vary `core_level`, vary `partner_levels` as **sets**, keep product constants locked.

Required L1/L2 studies in this protocol: `from_partners: required` and **`min_valid_confluences: 1`**. With every partner required, `min_valid: 1` and `min_valid: N` are equivalent **except** that `min_valid: N` cannot share a study with the 1-partner `{dVWAP}` baseline cell. Expand then raises `min_valid_confluences=N incompatible with 1 partner rule(s)`.

### 2.3 Why a full token cartesian is the *wrong* ideal (even with infinite compute)

Compute is not the constraint. **Selection bias** is.

Bailey & López de Prado (*The Probability of Backtest Overfitting*; Deflated Sharpe Ratio) show that the number of **trials you looked at** — not the ones you report — inflates Sharpe / expectancy. ThesisTester already treats ranked cells as descriptive (`multiple_testing: warn|error`; `docs/ASSUMPTIONS_AND_LIMITATIONS.md`). A 73-core × 72-partner × 2-mode × 5-trigger × 4-tf × 5-OTF × 2-side grid is **2,102,400** cells before 2- and 3-partner sets. That is not a complete research program; it is a machine for crowning noise.

Practitioner confluence literature (ORB + VWAP + volume-profile work) converges on the same operational bound: **2–3 complementary filters outperform 8-filter walls**, which starve the sample. Volume-profile geometry alone is often folklore; the value is **location + confirmation**, not stacking siblings.

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
| `otf` | normalized OTF configs | **Not a first-screen or L2 factor.** If used: classic Validation matrix on a promoted single setup (§6.5) |
| `direction` | `long`, `short`, `both` | First screen: `both`. Side from trade `direction` / combo×direction, not a first cartesian |

Constants that are **locks**, not axes: `tolerance_ticks`, SL/TP, `min_valid_confluences` (= 1 on required studies), `from_partners` (= `required` on L1/L2), costs, `intrabar_model`, `exposure_policy`, `flat_by_session_close`.

Time-of-day is post-hoc (`entry_rth_segment`). **Never a factor.** Admit a later constrained re-sim only via `study promote --admit-tod auto` (or the same stamp: `constants.entry_window` **and** `constants.backtest.entry_window` **and** `grid.entry_window` when grid is present). Engine path is `backtest.entry_window`. Setup-only `constants.entry_window` does **not** constrain `simulate_trades`. Focus ≠ Admit.

---

## 4. Economic taxonomy (catalog + sibling list)

Every default token sits in exactly one **family**. That partition is a catalog (73/73, no overlap). It is **not** a sufficient rule for “complementary.”

| Family | Tokens | Default role | Why |
|---|---|---|---|
| **S1 Session extremes** | `ONH` `ONL` `pONH` `pONL` `AsiaHigh` `AsiaLow` `LondonHigh` `LondonLow` `OR_High` `OR_Low` `pRTH_High` `pRTH_Low` | **Anchor candidates** | Named liquidity / range edges |
| **S2 Session opens** | `RTH_Open` `pRTH_Open` `dOpen` `wOpen` `mOpen` `pdOpen` `pwOpen` `pmOpen` | **Anchor candidates** | Auction open / gap / week-month context |
| **S3 Prior range** | `pdHigh` `pdLow` `pwHigh` `pwLow` `pmHigh` `pmLow` `pdEQ` `pwEQ` `pmEQ` `prevSettlement` | **Anchor candidates** | Calendar range / equilibrium. Raw H/L are often redundant with VA edges; EQ is the cleaner first screen |
| **P Prior profile** | `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC` | **Anchor candidates** (swing also: HTF VA) | Accepted value. Typical-price MVP — treat as location, not true VAP |
| **V Developing VWAP** | `dVWAP` `dVWAP_RTH` `wVWAP` `mVWAP` `VWAP_rolling_30min` `VWAP_rolling_4h` `prev30mVWAP` | **Confirmation** (`dVWAP` required first). Swing-only cores: `wVWAP` `mVWAP` | In-play fair value. `dVWAP` is not also a kill-list core |
| **C Developing profile** | `POC_rolling_30min` `APOC` `pAPOC` | **Confirmation** (rarely a core) | Intraday accepted price; noisy as a location |
| **A Auction leftover** | four `*SinglePrint_30m_*` | **Anchor or late confirmation** | Unfinished auction; thin by construction |
| **M Moving average** | default SMA/EMA set | **Confirmation on survivors only** (desk: **later** than first pairwise) | Moves. Illegal as first-screen cores |
| **K Pivot** | eight `Pivot_*` | **Confirmation on survivors only** (same later pass as M) | Swing structure, not a session location |

**Complementary** = different *information* (e.g. `ONH` + `dVWAP` + `pdVAL`: overnight edge + session fair value + prior accepted-value edge).

**Economic siblings — illegal in one partner set** (even when families differ):

| Sibling set | Why they are the same information |
|---|---|
| Same-session raw H/L + VA edge (`pdVAH`+`pdHigh`, `pdVAL`+`pdLow`, week/month analogues) | Range extreme vs value-area edge of the same auction |
| Two MAs in one set | Fast/slow average of the same tape |
| Two pivots in one set | Same swing structure, two spellings |
| Developing VWAP cluster: `dVWAP` + `dVWAP_RTH` + `VWAP_rolling_*` + `prev30mVWAP` | Same in-play fair-value family |
| Core duplicated as partner | Expand rejects this |

**Named exceptions** (desk or later pass only; say so in the study description):

- Swing L1 cores `wVWAP` / `mVWAP` with required `dVWAP` — VWAP-stack kill-list extra, not complementary confirmation.
- Optional later cell `[dVWAP, wVWAP]` on an L1 survivor — HTF tightness filter (price near both VWAPs). Different thesis. **Not** in the first L2 menu.

Suggested Setup defaults (`ONH` `ONL` `AsiaHigh` `AsiaLow` `LondonHigh` `LondonLow` `OR_High` `OR_Low` `RTH_Open` `pRTH_High` `pRTH_Low` `pdHigh` `pdLow` `pdPOC` `VWAP_rolling_30min`) are a **chart convenience subset** (`SUGGESTED_DEFAULT_LEVELS`). They are not the research kill list. That list has `pRTH_High`/`pRTH_Low` and **not** `pRTH_Open`.

---

## 5. Two combination problems (keep them separate)

### 5.1 Prospective — required evidence (StudySpec)

Question: *If I refuse to trade location L unless evidence set E is present, do I earn R?*

Mechanism: `anchor_rules` + `from_partners: required` + **`min_valid_confluences: 1`**. Each cell is a **causal** thesis: every listed partner must be inside tolerance.

This is the only honest way to rank “which confluence matters.” Optional partners + low `min_valid` mix theses inside one expectancy number.

Do **not** set `min_valid` to the partner-set length. L2 requires the `{dVWAP}` baseline in the **same** study. `min_valid: 2` fails expand on that 1-partner cell.

### 5.2 Retrospective — observed evidence (attribution)

Question: *When extra supports were allowed to be optional, which subsets actually traded?*

Mechanism: already shipped (`docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` Phases 1–6): exact combo, membership, parsed level-count, soft pairs, combo×direction, opt-in combo×3c variant. Membership / Pairs tabs remain **undirected** after Phase 6. 3c names may be tested-level-only.

Honest discovery while keeping the `dVWAP` lock needs **mixed** rules: `dVWAP` required, extras optional, `min_valid: 1`. Setup Builder can do that. **Study expand cannot** (`from_partners` is all-or-nothing).

Therefore:

- **Forbidden:** StudySpec `from_partners: optional` + `min_valid: 1` + `{dVWAP, X1, X2, X3}`. That admits ONH + X with **no** `dVWAP` and mixes theses.
- **Allowed today:** required L2 cells (causal AND), then Backtest expander on those zips (exact combo is the AND that already fired).
- **Allowed today, not a study factor:** one Setup Builder replay of the L1 survivor with `dVWAP` required and extras optional; read Pairs / exact combo×direction; promote only pairs that later win as **required** on a **later chronological slice**.
- **Forbidden:** auto-tighten Setup Builder from the same sample (explicit non-goal of combo attribution).
- **Forbidden:** opening the optional-discovery path because every required L2 cell was low-N on the same 2y slice (§6.3).

Nested-set honesty: exact combo treats `A|B` and `A|B|C` as different; pairs exist specifically so a productive pair is not hidden by a third tag.

---

## 6. Ideal protocol (complete useful coverage)

Two locked products. One instrument first (MNQ). One confirmation (`dVWAP`) until a location survives. Then complementary information only. Desk sequence. Robustness last.

```text
L0  Locks (do not cartesian)
L1  Location kill-list          core × {dVWAP}          required
L1b Named coin-flip only        desk-listed coin-flip × 1 other confirm
L2  Pairwise                    survivors × complementary X (no M/K yet)
L2m MA / pivot partners         later desk step, survivors only
L3  Triple                      only if two different-information L2 extras each beat baseline
L4  Context                     post-hoc ToD, then direction read; OTF = Validation matrix if at all
L5  Economics                   SL/TP grid (MNQ SL ≤ 80 ticks / $40), costs on
L6  Product compare             same survivor, touch/10 vs 3c/20 (separate studies)
L6b Leak isolate                optional later: same width, touch vs 3c
L7  Transfer                    ES/MES survivors only; re-audit dollars; then WFO / holdout
```

Do not skip ahead because a cell is green. Do not put a killed scalp name back on the scalp map because a 30m ToD slice was green.

### 6.0 Locks (L0)

| Lock | Scalp | Swing |
|---|---|---|
| Trigger | `touch` @ `1min` | `3c` @ `1min` |
| Zone / `tolerance_ticks` | 10 | 20 |
| SL / TP (first screen) | 40 / 40 ($20 / 1R on MNQ) | 80 / 80 ($40 / 1R on MNQ) |
| Partner | `dVWAP` required | `dVWAP` required |
| Mode | `anchor_rules` | `anchor_rules` |
| `from_partners` | `required` | `required` |
| `min_valid_confluences` | `1` | `1` |
| Direction | `both` | `both` |
| `exposure_policy` | `single_position` | `single_position` |
| `flat_by_session_close` | Copy the finished L1 run. New first screen: `true` (intra-day) and log it | same |
| Instrument first | MNQ | MNQ |
| Ingest | Quantower HE 15s, `source_timezone: UTC`, `ingestion_mode: 15s_primary_derive_1m`, `intrabar_model: subtimeframe_conservative` | same |
| Point value | MNQ $0.50 / tick (`tick_size` 0.25 × `point_value` 2.0) | same |
| Costs | `commission_per_side: 0.5` (currency / side, not per tick); `slippage_ticks: 1.0` | same |
| Rank | `expectancy_r`; `min_trades: 30`; `multiple_testing: warn` | same |
| Mix forbidden | touch with 3c, 10 with 20, both modes, long vs short, in one first study | same |

L2+ must copy the finished L1 study’s flatten / exposure / costs / ingest / window. Changing flatten between L1 and L2 is a new sample definition.

Grid / validation / walk_forward always `enabled: true|false`. Never bare `{}`. `--confirm` if `run_count >= confirm_above_runs`. Never auto-run a promote draft.

Engine defaults if omitted: `exposure_policy: allow_all`, `flat_by_session_close: false`, `commission_per_side: 0.0`. Omitting those locks is not “desk default.”

### 6.1 L1 — Location kill-list

**Hypothesis:** location L is worth a product *at all* when developing session VWAP is also in the zone.

**Cores (current desk list):**

- Profile: `pdVAH` `pdVAL` `pdPOC` `pwVAH` `pwVAL` `pwPOC` `pmVAH` `pmVAL` `pmPOC`
- Session extremes: `ONH` `ONL`
- Single prints (4)
- EQ: `pdEQ` `pwEQ` `pmEQ`
- Opens: `dOpen` `pdOpen` `wOpen` `pwOpen` `mOpen` `pmOpen` `RTH_Open` `pRTH_Open`
- Swing-only extras as cores: `wVWAP` `mVWAP` (VWAP-stack thesis; §2.1)

**Stay off L1 unless the desk page explicitly extends it:** MAs and pivots as cores; `pRTH_High`/`pRTH_Low`; `pONH`/`pONL`; Asia/London; OR; `prevSettlement`; raw `pd/pw/pm High/Low`; `APOC`/`pAPOC`; `dVWAP_RTH`; `dVWAP` as a core.

**Cell math:** one product × N cores × 1 partner set `{dVWAP}` × locked trigger/tf/mode = **N cells**. Scalp 24 (`scalp_touch_10_anchor`) + RTH add-on 2 (`RTH_Open`, `pRTH_Open`) is the executed map. Swing is that 26 plus `wVWAP`/`mVWAP` (28).

**Decision rule (pre-register; apply in this order; do not retune after seeing ranks):**

1. **Coin-flip first.** If `n >= 30` and (`|expectancy_r| < 0.03` **or** PF ∈ [0.95, 1.05]) → **hold**. Do not pairwise. L1b only if the desk names that coin-flip. Test case: `pwEQ` (+0.011R, n=81, PF 1.023) is a hold, even though E>0 and PF≥1.0.
2. **Promote to L2** only if `n >= 30` **and** `expectancy_r >= 0.03` **and** `PF > 1.05`. Test case: `ONH` (+0.074R, n=47, PF 1.162) promotes.
3. **Kill** if `expectancy_r < 0` at `n >= 30`, or `n < 30` after the full 2y window.
4. Descriptive only. A +0.07R survivor with max DD 4.45R and total R +3.475 over two years is a **license to pairwise**, not a live edge. Secondary metrics (PF, max DD, n, total R) stay on the Results row.

### 6.2 L1b — Named coin-flip only

**Not** a replay of killed cores. Killed names (`RTH_Open`, `pRTH_Open`, weekly VA, single prints, `dOpen`, …) stay off the scalp map.

Current desk coin-flip: **`pwEQ`**. One cell, same scalp locks, `from_partners: required`, `min_valid: 1`, **one** partner that is not `dVWAP` (different information; default `pdPOC`). If that cell also fails the §6.1 rule, `pwEQ` stays off the pairwise map.

Do not AND two retries. Do not invent L1b for a killed name because completeness feels better. Amending this scope requires amending the desk page.

### 6.3 L2 — Pairwise among survivors (first combination test)

**Hypothesis:** given location L that already survived L1, does a *second, complementary* mark improve expectancy vs the `dVWAP`-only baseline **on the same sample definition** (same window, flatten, costs, ingest)?

This Δ is **in-sample and paired**. It is not OOS. Do not write “OOS-or-holdout” unless a chronological holdout was reserved *before* looking at L2 ranks.

Partner sets (exactly one extra information source; `dVWAP` stays):

```text
[dVWAP, X]
```

**First L2 menu for an ONH-class survivor** (desk pairwise; **no M/K** — those are L2m):

| X | Information | Skip when |
|---|---|---|
| `pdPOC` | Prior accepted value | — |
| nearer of `pdVAH` / `pdVAL` | Prior VA edge (one only) | — |
| `pdEQ` | Prior equilibrium | L is already an EQ |
| `POC_rolling_30min` | Intraday accepted price | — |
| nearer `pSinglePrint_30m_*` | Leftover auction | L is already a single-print |
| `OR_High` / `OR_Low` (matching side) | Opening-range edge | L is OR; before RTH exists |

**Illegal in any L2 set:** two MAs; two pivots; `pdVAH`+`pdHigh` (economic siblings); any developing-VWAP cluster pair; core as partner.

**Not in first L2:** `EMA_*`, `SMA_*`, `Pivot_*` (L2m). `wVWAP` (named V-HTF exception; later, described as tightness, not complementary).

**Baseline cell required in the same study:** `{dVWAP}` alone.

**L2 power / low-N (pre-register):**

`ONH + dVWAP` on 2024-07-31 → 2026-08-06 is **n = 47**. A required extra mark is an AND. At a 50% keep rate, n ≈ 24 → below `min_trades: 30`.

- Rank a pair only if `n >= 30` and the pair beats `{dVWAP}` on `expectancy_r` **and** the Δ is not explained only by “fewer trades.”
- If **every** pair is `n < 30`: **STOP**. Log “L2 under-powered on this window.” Do **not** open all-optional discovery on the same slice. Options: longer dataset, wait for swing survivors, or leave pairs as unranked notes (`n >= 15` descriptive, never promote).

**Promote to L3:** two extras from **different information** (not two MAs, not POC+VAH of the same session) each beat `{dVWAP}` at `n >= 30`. No holdout language unless a holdout exists.

### 6.3b L2m — MA / pivot partners (later desk step)

Desk roadmap: “MA partners on survivors” is **after** pairwise, not inside it. One MA per cell (`EMA_21_5min`, then separately `SMA_50_5min`). One HTF pivot per cell (`Pivot_30m_High` / `_Low`, matching side). Same baseline `{dVWAP}`. Same low-N stop. Do not stack two MAs in one set. Do not run L2m because L2 was all low-N.

### 6.4 L3 — Triple (rare)

Only when two **different-information** L2 extras each beat `{dVWAP}` at `n >= 30`. Then one cell:

```text
[dVWAP, X, Y]
```

Cap 3 marks (desk lock). Engine will accept two MAs; this protocol will not. Do not build 4- and 5-level ANDs. `max_confluences ≤ 5` is an engine cap, not a research target.

### 6.5 L4 — Context (not confluence)

Apply **after** a location thesis exists. Desk order: pairwise → **ToD** → grid → rush. This plan does **not** put OTF in front of ToD.

1. **ToD** — post-hoc NY `entry_rth_segment` / 30m on finished zips. `n >= 15` is readable / “solid” on the desk page; **`n < 30` never Admitted**. Focus ≠ Admit. Engine Admit = `study promote --admit-tod auto` (stamps setup + `backtest.entry_window` + `grid.entry_window`). Hand-editing only `constants.entry_window` is a no-op on fills.
2. **Direction** — do not cartesian `long`/`short` on the first screen. Read combo×direction / Long-Short KPIs. If one side is the whole edge, a **follow-up** study may lock that side.
3. **OTF (optional, not a study factor)** — classic Validation `run_otf_validation_matrix` on a **promoted single setup**, five configs from `docs/research-methodology.md` (`no_otf`, 15m, 30m, 15+30, 5+15+30). Chronological train/OOS. Train selects; OOS evaluates. Fewer trades ≠ better. Study `factors.otf` is a full-sample cartesian (`study.otf_delta.csv` is not that protocol). Do not 5-way-factor ONH (n=47).

### 6.6 L5 — Economics

Per-cell SL/TP grid on survivors only. **MNQ** SL at or under 80 ticks ($40). Grid is **not** a factor axis (Inspect `best_grid_*` / `grid_results.parquet`). Costs stay on. This $40 sentence is MNQ-only (§6.8).

### 6.7 L6 — Product compare vs leak isolate

**L6 (desk rush check):** same survivor, two locked products, **separate studies**: scalp `touch` / 10 / 40/40 vs swing `3c` / 20 / 80/80. That is a **product comparison**. Do not attribute the Δ to “re-entering the touch 2–3 times” — width and trigger are both different.

**L6b (optional, later):** same width and SL/TP, `touch` vs `3c`. That isolates the reentry leak. Do not mix L6 and L6b in one study.

### 6.8 L7 — Transfer / robustness

Repeat **L2+** on ES/MES **only for survivors**, not the full kill list. Then walk-forward (`enabled: true` on a **small** survivor study). Then a later chronological dataset. Failure to transfer kills the live claim, not the descriptive MNQ note.

Tick size is 0.25 on MNQ/NQ/MES/ES, so 10/20 ticks is the same **price** distance. Dollar risk is not:

| Instrument | $ / tick | 80-tick SL |
|---|---:|---:|
| MNQ | 0.50 | $40 |
| MES | 1.25 | $100 |
| NQ | 5.00 | $400 |
| ES | 12.50 | $1,000 |

Do **not** copy “SL ≤ 80 ticks ($40)” onto ES. Re-audit the dollar envelope (or convert a chosen dollar cap to ticks: $40 / $12.50 ≈ 3.2 ES ticks — usually too tight, which is why a new audit is required). Widths may stay 10/20 ticks if the distance audit is treated as price-distance; say so on the Results row.

---

## 7. Multiple-testing and honesty (normative)

| Rule | Why |
|---|---|
| Count **studies and cells looked at**, not just reported winners | DSR / PBO: trials include killed cells |
| Primary = `expectancy_r`; secondary = PF, max DD, n, total R as **context** | `total_r` crowns high-frequency noise |
| `min_trades: 30` for ranking; hide-thin on attribution (`min_trades=10` UI default) | Low-n expectancy is not a result |
| `multiple_testing: warn` on screens; `error` (no crowning) on large L2 menus | Study report already supports this |
| Information-wise, not token-wise | 12 MA tokens are ~2 hypotheses (fast/slow), not 12 |
| Chronological holdout: select on train / early years, evaluate on later years | No shuffle. Do not claim OOS on a full-sample L2 |
| OTF SoT is `docs/research-methodology.md` | Do not invent a second OOS rule via `factors.otf` |
| Combo attribution is diagnostic | Observed-only; membership/pairs double-count; 3c names may be tested-level-only |
| Profile math is typical-price MVP | Do not claim VAP precision |
| Zero-cost ranks are invalid for promotion | Commission + slippage required |
| All-optional StudySpec discovery is invalid here | Drops the `dVWAP` lock |

SOTA gap (proposal §3): PBO / deflated Sharpe / CPCV are **not implemented**. Until they are, the operational substitute is: **small staged studies, pre-registered promote rules, holdout, and `multiple_testing: error` before any “best cell” language.**

---

## 8. How to realize it in ThesisTester today

No new factor axis. No engine change. No pairwise-zone emission. Realization is **authoring discipline + the existing CLI**. Mixed required/optional discovery is Setup Builder, not Study expand.

### 8.1 Surfaces

| Step | Tool |
|---|---|
| Author | Studies **Build StudySpec** or YAML (`examples/studies/` as shape, not as the map) |
| Preview count | `python -m thesistester study expand SPEC --output-dir OUT` |
| Run | `study run …` (`--confirm` if ≥ `confirm_above_runs`) |
| Rank | `study report OUT` + Inspect briefing / quality panes |
| ToD | Inspect post-hoc (not a factor) |
| Admit | `study promote --admit-tod auto` **only** when n≥30 (stamps setup + `backtest.entry_window` + `grid.entry_window`) |
| OTF | Validation → OTF matrix on a promoted single setup — **not** `factors.otf` |
| Observed extras with `dVWAP` still required | Setup Builder mixed rules, then Backtest expander — **not** `from_partners: optional` |
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
    min_valid_confluences: 1       # required studies; do not set to partner-set length
    trigger_params: {}
    entry_window: null             # Admit later via promote --admit-tod auto (also stamps backtest)
    backtest:
      stop_loss_ticks: 40          # 80 on swing
      take_profit_ticks: 40
      exposure_policy: single_position
      commission_per_side: 0.5     # currency per side
      slippage_ticks: 1.0
      flat_by_session_close: true  # copy finished L1 if that run differed
      intrabar_model: subtimeframe_conservative
    grid: {enabled: false}         # true only on L5 survivors
    validation: {enabled: false}
    walk_forward: {enabled: false}
  factors:
    core_level: [ONH]              # L1: the kill-list; L2: survivors only
    partner_levels:
      - [dVWAP]                    # baseline cell — required in the same L2 study
      - [dVWAP, pdPOC]
      - [dVWAP, pdVAL]
      - [dVWAP, pdEQ]
      - [dVWAP, POC_rolling_30min]
    confluence_mode: [anchor_rules]
    trigger: [touch]               # swing: [3c]
    trigger_timeframe: [1min]
    # otf / direction omitted. OTF is not a study factor in this protocol.
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
    multiple_testing: warn         # error if the L2 menu grows large
```

L1 is the same file with the kill-list in `core_level` and `partner_levels: [[dVWAP]]` only. Copy flatten / exposure / costs from the finished L1 zip when authoring L2.

### 8.3 What not to copy from shipped examples

| Example | Useful as | Harmful if copied blindly |
|---|---|---|
| `pdPOC_ma_confluence_battery.yaml` | Stage-first *shape* (40 cells) | Mixes both modes, 5 triggers, 4 TFs, 5 OTFs, MA partners on an un-killed core — that is a teaching cartesian, not this protocol |
| `pRTH_open_ma.yaml` | MNQ 15s ingest + costs | `pRTH_Open` is already **killed** on scalp; MA-as-first-partner without `dVWAP`; mixed touch/3c; wide grid |
| `dopen_ma_3c_mnq.yaml` | Tiny 3c shape | Legacy 1m primary (different dataset identity) |

### 8.4 Cell-budget guide (complete useful, not maximal syntactic)

| Stage | Typical cells | Notes |
|---|---:|---|
| L1 scalp | 24 | Done (`scalp_touch_10_anchor`) |
| L1 RTH add-on | 2 | Done; both killed |
| L1 swing | 28 | In flight |
| L1b | 0–1 | `pwEQ` only unless the desk names another coin-flip |
| L2 per survivor | 6–8 incl. baseline | First menu; no M/K |
| L2m | 2–4 | Later; one MA or one pivot per cell |
| L3 | 0–3 | Rare; different information |
| L4 ToD | 0 study cells | Post-hoc on finished zips |
| L4 OTF | 5 configs × 1 setup | Validation matrix, not study cells |
| L6 | 2 × survivors | Separate product studies |
| L6b | 2 × survivors | Same width; optional |
| L7 ES transfer | L2 size | Survivors only; re-audit $ |

A **complete** program for one instrument × two products is on the order of **low hundreds of cells**, staged, not millions.

### 8.5 Reading results

1. Overview ranked by `expectancy_r` (n≥30). Apply coin-flip **before** “E>0.”
2. Group-by `core_level` then `partner_levels` — L1 asks “which location”; L2 asks “which extra mark vs `[dVWAP]`.”
3. Inspect NY ToD on the **finished** zip. Do not Admit thin buckets. Admit only through `--admit-tod auto`.
4. If every L2 pair is low-N: stop. Do not open optional StudySpec discovery.
5. Log the kill / hold / stay decision the same day (Runs + Results).

---

## 9. Later product work (only if the loop should be first-class)

These are **optional** future series. Do not start them to “finish” this protocol.

| Idea | Why | Constraint |
|---|---|---|
| Mixed `from_partners` / per-rule required flags | Honest L2 discovery without dropping `dVWAP` | New StudySpec emission; fail closed; no new factor axis |
| Family + sibling-list helper | Stop economic-sibling stacks at emit time | Research classification; must not fork `catalog.py` engine names |
| Study Builder “complementary partners” widget | One extra information source | Fail closed; no new factor axis |
| Stage recipes (L1/L2/L4) in Grok pack | Copy-ready coworker prompts | Same RS-D5 hard rules: no invent, no auto-run promote |
| PBO / DSR / CPCV | Close the SOTA validation gap | Own golden-gated analytics series; default-off |
| Directed membership / pairs | Phase 6 left those tabs undirected | Analytics-only |
| Engine “one zone per valid rule” | Would multiply fills | Explicit non-goal of combo attribution; likely never default |

Do **not**: invent tokens, add ToD as a factor, cartesian width, genetic search, auto-recommend “drop this level” from attribution, or treat `factors.otf` as the OTF methodology.

---

## 10. Decision checklist (next run)

Ask before expanding any StudySpec:

1. Which **product** (scalp vs swing)? Which **lock** stays identical (including flatten / exposure / costs)?
2. Which **stage** (L1, L1b, L2, L2m, L3, L5–L7)? If the answer is “this 30m window,” “OTF as a factor,” or “a new axis,” it is drift — do not run.
3. Is every core a **location** (S1/S2/S3/P/A) or a desk-listed swing V extra (`wVWAP`/`mVWAP`)? Not M/K.
4. Is every partner set **`dVWAP` + at most one extra information source**, with no economic siblings?
5. Is there a **baseline `{dVWAP}` cell** for any pairwise claim? Is `min_valid_confluences: 1`?
6. Are costs on (`0.5` / `1.0`)? Is ingest 15s-primary? Is `--confirm` required?
7. What is the **pre-registered** decision rule (§6.1 / L2 low-N stop)?
8. If this is Admit: will `backtest.entry_window` be stamped, or only setup?

---

## 11. Copy-ready coworker prompt

```text
You are an external ThesisTester coworker. Follow docs/STUDY_RUNNER.md,
docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md, and examples/studies/agents/SYSTEM.md.

Hard rules:
- Work regression-safe. Do not invent factor axes, tokens, or triggers.
- Do not mix scalp (touch @ 1min, 10 ticks, 40/40) with swing (3c @ 1min, 20 ticks, 80/80).
- Mode is anchor_rules. from_partners is required. min_valid_confluences is 1.
- Partner sets must include dVWAP. At most one extra information source. No economic siblings.
- Do not set factors.otf. Do not use from_partners: optional (drops the dVWAP lock).
- ToD is never a factor. Admit only via study promote --admit-tod auto (backtest.entry_window).
- Copy flatten / exposure / costs from the finished L1 run onto L2.
- Do not retry killed scalp names. L1b is pwEQ only unless the desk page names another coin-flip.
- Coin-flip first (|E|<0.03 or PF in [0.95,1.05]), then promote (n>=30 and E>=0.03 and PF>1.05).
- If every L2 pair is n<30: STOP. Do not open optional discovery on the same slice.
- --confirm if run_count is high. Do not auto-run a promote draft.
- Rank on expectancy_r. Descriptive ≠ edge. Log kill/hold/stay with n, PF, max DD.

Task: author/expand/run only the next protocol stage the human names (L1, L1b, L2, L2m, …).
1. Expand and report run_count.
2. Run (add --confirm when required).
3. Report ranked / low-N / unresolved with honesty.
4. Promote draft only if asked; STOP for human edit + confirm.
```

---

## 12. Status vs desk roadmap (2026-08-19)

Source: Notion *Process and roadmap* + Results rows for `scalp_touch_10_anchor` / `scalp_rth_open_10_anchor`. Window 2024-07-31 → 2026-08-06, MNQ 15s HE, costs 0.5 / 1.0.

| Protocol stage | Desk status | Implication |
|---|---|---|
| L0 locks + distance audit | Done | Widths frozen (10 / 20). Do not cartesian width. |
| L1 scalp (`scalp_touch_10_anchor`, 24) | Done — **ONH** stays: +0.074R, n=47, PF 1.162, total R +3.475, max DD 4.45R, WR 57.4%. Descriptive. | License to **first** L2 only (no M/K). Expect low-N. |
| L1 scalp coin-flip | **`pwEQ`**: +0.011R, n=81, PF 1.023, Ranked=NO, max DD 5.825R | Hold. Do not pairwise. L1b only if the desk keeps this as a named retry. |
| L1 RTH add-on | Done — `RTH_Open` −0.09R n=407; `pRTH_Open` −0.27R n=191 | Off the scalp map. Do **not** retry as cores. |
| Scalp ToD | Done — ONH has no solid n≥15 green 30m bucket. `RTH_Open` 13:00 +0.37R n=25 **not Admitted** | Do not revive killed names from a ToD slice. |
| L1 swing (`swing_3c_20_anchor`, 28) | Running | Wait. Do not pairwise swing names yet. |
| L1b | Not started | `pwEQ` × one other confirm **only**. Not a killed-core replay. |
| L2 first pairwise | Waiting | `ONH` + `{dVWAP}` baseline + complementary X (P/C/A/OR/EQ). Pre-register the all-low-N stop. |
| L2m MA / pivot | Later (desk) | Not inside first L2. |
| L3+ | Waiting | Only after two different-information L2 extras clear n≥30. |
| L4 ToD | Scalp done | Swing ToD after swing L1. Admit only n≥30 via `--admit-tod auto`. |
| L4 OTF | Not a desk step | Optional Validation matrix on a promoted single setup. Not `factors.otf`. |
| L5–L6 | Later | Survivors only. L6 = product compare; L6b = same-width leak isolate. |
| L7 | Not started | Survivors only. Re-audit ES/MES dollars. |

The next *useful* combination study on the current scalp map is **not** a new kill list and **not** L1b on killed names. It is **L2: `ONH` + `dVWAP` + one complementary X**, with `{dVWAP}` as the baseline cell, same scalp locks as the finished L1 run, `min_valid: 1`, no MA/pivot in the first pass, and a written stop if every pair is n<30.
