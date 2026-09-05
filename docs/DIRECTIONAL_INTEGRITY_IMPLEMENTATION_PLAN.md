# Directional Integrity & Edge Attribution — implementation plan (DA)

**Status:** **DA0 locked.** **DA1 landed.** **DA2 landed.** DA3–DA6 not started.
**Series prefix:** **DA** (Directional Attribution, DA0–DA6). **DI is taken** by
Discuss Intelligence (`docs/DISCUSS_INTELLIGENCE_IMPLEMENTATION.md`, DI-0…DI-3).
Do not title PRs `DI1` / `DI2`.
**Does not reopen:** AO, RS, AH, AP, TV, Discuss Intelligence (DI-0…DI-3).
Observatory / Study Runner surfaces may be amended additively (DA2, DA5); parked
SO5/SO6 stay parked.
**Regression gate:** `docs/ENGINEERING_PROPOSAL.md` §4 (§4.1 golden-master, §4.2 PR checklist).
**Reader:** desk owner (Edge Finder), ThesisTester bot, engine contributors.

---

## 0. Finding (locked — verified 2026-09-05)

### 0.1 Statement

Under the lock shared by **Program A** (`docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` §6.0) and **Program B** (`docs/PROGRAM_B_OPERATOR_RUNBOOK.md` §1):

```
trigger: touch @ 1min · direction: both · exposure_policy: single_position
```

**every accepted trade is long. No short is ever simulated.** The 944-cell Program B Run 1 corpus and the Program A L1 kill list are long-only samples. Every "+E", "dead", and "hold" verdict on them is a verdict about *buying* a level touch, never about *fading* or *shorting* it.

### 0.2 Mechanism (code path, all on `main`)

1. `thesistester/engine/signals.py::_check_touch` is direction-agnostic: it fires when `bar.low <= zone_high and bar.high >= zone_low`. The simple-trigger loop is `for zone in filtered_zones: for d in ["long", "short"]` when `direction == "both"`. Every touched zone therefore emits **two** candidates — long first (`signal_id = k`), short second (`signal_id = k+1`) — with identical `bar_index`, identical next-bar `entry_bar_index`, and identical `entry_price` (next bar open). With several zones on one bar the lowest `signal_id` is still the first zone's long.
2. `thesistester/engine/backtest.py::simulate_trades` sorts candidates by `(entry_bar_index, bar_idx, signal_id)` whenever `exposure_policy != "allow_all"`. On a flat book the long is processed first and accepted; the same-entry-bar short is then blocked and skipped as `overlapping_position` (`single_position`) or `overlapping_setup` (`single_setup` with a shared group key). Subsequent touches while that long is open are also skipped (occupancy). **Every accepted trade is long; not every touch becomes a trade.**
3. `anchor_rules` mode does not bypass this: for `touch` it enters the same `else` branch in `generate_signals`. The Study Runner executes `api.run_experiment → api.generate_signals → api.run_backtest → simulate_trades`, so every Program B cell went through this path. Classic Backtest / Setup Builder with the same lock is the same object.

There is **no** exposure policy under which `touch` + `both` is a meaningful long-vs-short test of a level:

- `allow_all` / `single_direction` open a long *and* a short at the same price on the same bar (a hedged pair). With symmetric SL/TP and SL/TP exits the pair's net is about `−2 × costs`; `flat_by_session_close` / TIME can make the pair's net nonzero.
- `single_position` collapses to long-only via `signal_id` order (`overlapping_position`).
- `single_setup` collapses to long-only **only when the group key is shared** (typical: same `level_names` / zone). Skip reason is `overlapping_setup`, not `overlapping_position`. The fallback key `trigger_direction:{trigger}|{direction}` includes direction, so that path would hedge. Program B `anchor_rules` fills `level_names` and is the shared-key case.

### 0.3 Evidence

Synthetic mean-reverting (OU) 1-minute series crossing a two-level zone 516 times, `touch`, `both`, SL/TP 40/40, run against `main` `bece2f4`:

```python
zones = detect_confluence_zones(df, ["LVL_A", "LVL_B"], 0.25, tolerance_ticks=8, min_confluences=2)
sigs = generate_signals(df, zones, trigger="touch", direction="both", tick_size=0.25)
trades, skipped = simulate_trades(df, sigs, tick_size=0.25, point_value=2.0,
                                  stop_loss_ticks=40, take_profit_ticks=40,
                                  exposure_policy=policy, return_skipped_signals=True)
```

| `exposure_policy` | trades | long | short | same-bar shorts skipped as |
|---|---:|---:|---:|---|
| `allow_all` | 1032 | 516 | 516 | (none — hedged pairs fill) |
| `single_position` | 235 | **235** | **0** | `overlapping_position` (516) |
| `single_direction` | 470 | 235 | 235 | `overlapping_direction` (occupancy, not the same-bar pair) |
| `single_setup` (shared `level_names`) | long-only | all | **0** | `overlapping_setup` (not `overlapping_position`) |

Corroboration inside the Run 1 corpus itself (Notion *Run 1 results — Edge Finder*, 2026-09-05): the "kill list" (worst E at n≥100) is dominated by **highs** and `*_High` partners — `ONH × EMA_9_5min` −0.28, `LondonHigh × Pivot_5m_High` −0.21, `pdHigh × VWAP_rolling_30min` −0.20, `dSP_Above × Pivot_4h_High` −0.21 — while the playable list is rich in **lows** — `pmLow × Pivot_1m_Low` +0.33, `ONL × EMA_21_5min` +0.23, `pdLow × Pivot_5m_High` +0.23, `pRTH_Low × VWAP_rolling_4h` +0.18. Buying supports and buying resistances is exactly the fingerprint of a long-only sample on an upward-drifting MNQ window. It is not evidence that lows are edges and highs are not.

### 0.4 What this is not

- Not a `simulate_trades` bug. The engine does what the exposure contract says. The tie-break is deterministic and documented by the sort key.
- Not a reason to discard the corpus. The 944 bundles are valid **long-side** measurements. DA2 makes that readable without a rerun.
- Not a Program A vs Program B issue. Both `touch` products inherit the same lock. The Program A `3c` swing product does not (§0.5).

### 0.5 Trigger coverage — the artefact is specific to `touch`

Every trigger was run under the same lock (`direction: both`, `single_position`, 80/80) on a 6000-bar OU series with **two** confluence zones so cross-zone same-bar collisions could also appear:

| trigger | candidates L / S | same-bar opposite-direction pairs | trades L / S | long share |
|---|---|---:|---|---:|
| `touch` | 1654 / 1654 | 1546 (every touch bar) | 306 / 0 | **1.000** |
| `reject` | 776 / 835 | 58 (cross-zone only) | 149 / 155 | 0.490 |
| `break` | 428 / 431 | 0 | 132 / 127 | 0.510 |
| `reclaim` | 738 / 799 | 46 (cross-zone only) | 147 / 151 | 0.493 |
| `3c` (filled) | 386 / 470 | 0 | 120 / 140 | 0.462 |

Why: `reject`, `break`, and `reclaim` condition on `close` vs the zone edges (long reject: touch and `close > zone_high`; short reject: touch and `close < zone_low`). `3c` arrival (`_find_tested_level_for_arrival`) conditions on `close` vs the **tested level price** plus approach-from-above/below, not merely zone edges. Within one zone the two directions are mutually exclusive on a bar. `touch` conditions on overlap only. The residual `reject` / `reclaim` pairs (≈3–4 % of candidates) are a different object — one wide bar closing *between* two zones, long-rejecting the lower and short-rejecting the upper — and are still resolved by `signal_id` order. DA1 reports them; DA3 lets a study refuse them.

Consequences for existing corpora: the Program A **swing** product (`3c` @ 1min) is two-sided and is **not** affected. The Program A **scalp** L1 (`touch`) and all of Program B Run 1 (`touch`) are.

### 0.6 Golden fixtures encode the artefact

`tests/fixtures/study/golden/study.spec.yaml` is `touch` + `both` + `single_position`. `tests/fixtures/golden/pipeline.py` is `allow_all` (so the *legacy trade golden does not contain the long-only artefact*). Stage 5 / study goldens that use `touch` + `both` + `single_position` **do**. Every DA change must leave both existing goldens byte-identical under default flags. No `GOLDEN_REGEN` in this series. Do not treat a green `tests/test_golden_master.py` as proof that Program B admission is unchanged.

---

## 1. Goals / non-goals

**Goals**

1. Make single-sidedness **visible** on every study row, in the Observatory, and in the Notion readout, for both existing and future corpora (DA1, DA2).
2. Give the engine an **explicit, opt-in** rule for same-bar opposite-direction candidates so silent tie-break can never again be mistaken for a decision (DA3).
3. Ship a trigger whose direction is **derived from approach side** — the only trigger that represents "fade the level" as a discretionary trader means it (DA4).
4. Put a **drift null** next to every expectancy so a long-only +0.07R on a bull window cannot read as edge (DA5).
5. Re-author the Program B packet as **Run 2** under the corrected trigger, with direction split and drift null in the readout lock (DA6).

**Non-goals**

- No re-interpretation of Run 1 in code. Judgement stays with Edge Finder.
- No change to `signal_id` assignment order, `simulate_trades` sort key, or any default.
- No new factor axes in Program B Run 2 beyond replacing `touch` with `fade`.
- No trade-journal import (tracked as a follow-up in §8).
- No Notion API writes from the repo.

---

## 2. Regression-safety envelope (applies to every DA PR)

| Rule (§4) | How DA satisfies it |
|---|---|
| Additive-only engine changes | New `simulate_trades` kwargs are keyword-only (after `*`), default to legacy. New `SimulationResult` field has a default on **both** construction sites (empty early-return and main return). No frame column added to `trades` or `skipped_signals` under default flags. |
| Golden-master before engine touch | DA1, DA3, DA4 each run `tests/test_golden_*.py` (legacy + OTF + entry-window families) and the RS2 study golden unchanged. DA4 adds a **new** golden (`fade` fixture) rather than altering an existing one. |
| Opt-in, default-off | `same_bar_opposite_direction="legacy"` default. `fade` / `continuation` are new trigger tokens, never substituted for `touch`. Drift null is `report.random_baseline.enabled: false` by default. |
| Schema-versioned persistence | Study index gains keys on `STUDY_INDEX_KEYS` only — **not** `R18_INDEX_METRIC_KEYS` (CLI RS-D7 ordered parity stays frozen). Readers tolerate missing keys (older `study.index.parquet` still loads). |
| Bundle hash neutrality | Existing diagnostics live **inside** `trade_summary.json` via `_BACKTEST_META_KEYS` and **are hashed**. Do not copy that pattern. DA1 must not change `canonical_bundle_hash` of a default `run_experiment` bundle. |
| PIT proof | DA4 adds a future-shock test for `fade`. |
| Determinism | No randomness except DA5, which reuses the seeded `vs_random_benchmark`. |
| Same-PR docs | Each PR lists its doc edits. `ASSUMPTIONS_AND_LIMITATIONS.md` §4b in DA0; honesty/glossary/architecture only when the described behaviour becomes true. Help-corpus paths (`USER_GUIDE`, `ASSUMPTIONS`) stay frozen — amend in place. |
| Help vs Discuss Intelligence | Series code is **DA**. Do not reuse **DI**. |
| Small surface | One concern per PR. DA3 and DA4 are independent and may land in either order after DA1. |

Forbidden in this series: editing `_check_touch`; reordering the `["long", "short"]` loop; changing the candidate sort key; regenerating any golden; changing `touch` semantics in any way.

---

## 3. PR sequence and dependencies

```
DA0  docs freeze + honesty callouts                (docs only)            ← this PR
DA1  engine: direction-collision diagnostic         (engine, additive)  ← landed
DA2  direction split: summary → index → Observatory (analytics/study/UI)   ← unlocks Run 1 re-read
DA3  engine: same_bar_opposite_direction policy     (engine, opt-in)       (needs DA1)
DA4  engine: fade / continuation triggers           (engine/setup/schema/UI, opt-in)
DA5  study: drift null in index + Observatory       (analytics/study/UI, opt-in)  (needs DA2)
DA6  Program B Run 2 packet + runbook v2            (docs + generator)     (needs DA2, DA4, DA5)
```

DA2 is the first PR that changes what the desk can *see*; run it before any rerun decision. DA3 is the guard that prevents recurrence. DA4 is the product change. DA5/DA6 are the research payoff.

---

## 4. PR specifications

### DA0 — Docs freeze and honesty callouts (docs only)

**Files**

- `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md` (this file).
- `docs/README.md` — Primary living row + Engine / data contracts bullet.
- `docs/ENGINEERING_ROADMAP.md` — status-index row (code **DA**, not DI).
- `docs/AGENT_GUIDE.md` — one pointer under “Where each phase lives”.
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md` — subsection **4b** after **4a** (not before it).
- `docs/USER_GUIDE.md` — exposure-policy pitfalls: `touch`+`both`+`single_position` is long-only; `single_setup` skip reason is `overlapping_setup`.
- `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` — one callout above §1: "Run 1 (this lock) is a long-only sample; see DA plan §0. Do not start Run 2 on this table."
- `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` — one callout above §6.0 with the same sentence for the L1 kill list.

**Acceptance:** docs render; no code; `git diff --check`; no remaining `DI0`–`DI6` tokens for this series; Discuss Intelligence `(DI)` rows untouched.

**Regression safety:** docs only. Honesty describes current engine behaviour; it does not change admission.

---

### DA1 — Engine diagnostic: same-bar opposite-direction collisions

**Goal:** quantify, on every simulation, how many candidate pairs shared `entry_bar_index` with opposite direction, and how the tie-break resolved them.

**Files**

- `thesistester/engine/backtest.py`
- `thesistester/api.py` (`run_backtest` return dict)
- `thesistester/research_bundle.py` — **no** `_BACKTEST_META_KEYS` / hashed-member change in DA1 (see Persistence). Touch this file only if implementing the hash-safe persist listed there.
- `tests/test_backtest_direction_collision.py` (new)
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/METRICS_GLOSSARY.md`, `docs/ARCHITECTURE.md`

**Engine change (additive)**

```python
@dataclass
class SimulationResult:
    trades: pd.DataFrame
    skipped_signals: pd.DataFrame
    intrabar_diagnostic: dict[str, Any]
    exit_management_diagnostic: dict[str, Any]
    direction_collision_diagnostic: dict[str, Any] = field(default_factory=dict)
```

Computed inside `simulate_trades` **after** the admission loop (so DA3 `skip_both` / occupancy appear in `resolved_*`), from `ordered_candidates` + accepted trades + skipped_signals. Grouping is `(entry_bar_index, bar_idx)` — **bar-level, not per-zone**. A long from zone A and a short from zone B on the same entry bar is one pair.

```python
{
  "policy": "legacy",                       # DA3 reports the active policy here
  "candidate_pairs": int,                   # (entry_bar_index, bar_idx) groups containing both directions
  "resolved_long": int,                     # pairs in which a long was accepted
  "resolved_short": int,                    # pairs in which a short was accepted (not mutually exclusive with resolved_long)
  "resolved_none": int,                     # pairs where neither side was accepted (cutoff/cooldown/DA3 skip_both)
  "accepted_trade_share_from_pairs": float, # accepted trades that came from a collision pair / all accepted
}
```

Under `allow_all` / `single_direction`, both sides of a `touch` pair fill: `resolved_long == resolved_short == candidate_pairs` (each pair counted on both sides; they are not a partition). `resolved_none == 0` unless cutoff/cooldown ate the pair.

**API:** `run_backtest` adds `"direction_collision_diagnostic"` to its return dict and to `BacktestResult`. `run_experiment` may copy it onto in-memory state under a key that is **not** in `_BACKTEST_META_KEYS`.

**Persistence (hash-neutral — do not copy existing diagnostics):** `backtest_intrabar_diagnostic` / `backtest_exit_management_diagnostic` are nested inside `trade_summary.json` and **are included** in `canonical_bundle_hash`. Adding a sibling key there changes every study-cell hash and breaks the RS2 study golden. DA1 therefore:

- does **not** add the diagnostic to `_BACKTEST_META_KEYS` / `trade_summary.json`;
- does **not** add a hashed zip member or a new `manifest.session_keys` entry (those are hashed; only confluence-combo keys are stripped today);
- if a later PR persists the file, it must add the member to `_CANONICAL_HASH_EXCLUDED_FILES` **and** strip the session key from the hashed `session_keys` projection in the same PR, then re-assert `tests/test_golden_master.py` + RS2 study golden.

Until that hash-safe persist exists, DA2 `collision_pairs` is `None` on older bundles.

**Tests**

- Hand fixture: 3 touch bars, `both`, `single_position` → `candidate_pairs == 3`, `resolved_long == 3`, `resolved_short == 0`.
- Same fixture, `single_direction` → both sides accepted; assert `resolved_long == resolved_short == 3`, `resolved_none == 0`.
- `allow_all` → both accepted; same counts as `single_direction`.
- Legacy return shapes (`DataFrame`, `tuple`) untouched; `return_result=True` only path exposes the field.
- Golden tests unchanged.

**Acceptance:** all above green; both `SimulationResult(...)` call sites (empty early-return and main return) pass the new field. `SimulationResult` is `@dataclass(frozen=True)` — add `field(default_factory=dict)` so positional construction of the four existing fields keeps working.

**Regression safety paragraph (PR body):** no frame changes; no sort change; new dataclass field defaulted; diagnostic computed after admission from existing locals; goldens compared and identical; `canonical_bundle_hash` of a default `run_experiment` bundle identical to pre-PR (diagnostic not in `trade_summary.json`).

---

### DA2 — Direction split: trade summary → study index → Observatory → re-read Run 1

**Goal:** every study cell shows long/short n and E, plus a `directional_integrity` class, without a rerun.

**Files**

- `thesistester/analytics/metrics.py` (reuse `summarize_trades_by_direction`; no new math)
- `thesistester/study/execute.py` — new `DA_DIRECTION_INDEX_KEYS`; `STUDY_INDEX_KEYS` extended; direction keys attached in `execute_study_cell` / `--rebuild-direction`, **not** inside `build_index_row_from_state` (that helper stays R18-shaped); bundle rehydrate. **`_failed_index_row` must seed `DA_DIRECTION_INDEX_KEYS` as `None`** (it currently seeds only `R18_INDEX_METRIC_KEYS` and is used for failed / pending / soft-resume rows at the six call sites). Without that, any study with a failed cell writes a parquet whose columns ≠ `STUDY_INDEX_KEYS`.
- `thesistester/study/report.py` — `study.direction.csv`; overview columns
- `thesistester/study/observatory.py` — fact-table columns; facet; banner counts
- `pages/16_Study_Observatory.py` — cells table columns, `directional_integrity` facet, corpus banner line
- `thesistester/cli.py` — `study report --rebuild-direction` only. **Do not** change `_execute_run` / `R18_INDEX_METRIC_KEYS` (RS-D7 CLI↔study ordered parity stays frozen).
- `tests/study/test_study_execute.py` (`STUDY_INDEX_KEYS` column assertion; leave the R18 tuple test unchanged), `tests/study/test_study_report.py`, `tests/study/test_study_observatory.py`, `tests/test_cli.py`
- `docs/STUDY_RUNNER.md`, `docs/METRICS_GLOSSARY.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ARCHITECTURE.md`

**Index keys (study-owned — not R18)**

```
STUDY_INDEX_KEYS = R18_INDEX_METRIC_KEYS + DA_DIRECTION_INDEX_KEYS + ("bundle_path", "status")

DA_DIRECTION_INDEX_KEYS =
  long_trade_count, short_trade_count,
  long_expectancy_r, short_expectancy_r,
  long_share,                      # long_trade_count / trade_count, None when trade_count == 0
  directional_integrity            # "long_only" | "short_only" | "mixed" | "empty"
  collision_pairs, collision_resolved_long   # from DA1 in-memory/state when present, else None
```

Do **not** append these to `R18_INDEX_METRIC_KEYS`. That tuple is the CLI `_execute_run` contract (`tests/study/test_study_execute.py` ordered-parity). Direction split is a study-index concern. `build_index_row_from_state` stays R18-only so `tuple(study_row.keys()) == R18_INDEX_METRIC_KEYS` remains true. `_failed_index_row` is the study-index writer for non-ok rows — extend it, or parquet column alignment breaks.

Classification: `long_only` if `short_trade_count == 0 and trade_count > 0`; `short_only` symmetric; `mixed` otherwise; `empty` when `trade_count == 0`.

**Rehydrate:** `_read_bundle_trade_summary` already reads `trade_summary.json`. Add `_read_bundle_trades(bundle_path) -> pd.DataFrame | None` reading **`trades.parquet`** from the research zip (reuse `read_zip_parquet` in `thesistester/study/briefing.py`). Bundles do **not** ship `trades.csv`. Then `summarize_trades_by_direction`. `--rebuild-direction` iterates `study.index.parquet` rows with a `bundle_path`, fills only the new keys, rewrites the parquet atomically, and never touches existing metric values. Idempotent. Default `study report` **without** the flag must not rewrite older indexes.

**Observatory**

- Fact table: new columns; `directional_integrity` becomes a facet (multi-select).
- Corpus banner: `N cells long_only · M short_only · K mixed` next to the existing counts.
- Program B lens heatmap: unchanged colours; cell tooltip adds `L n / S n`.
- Cells table: `long_trade_count`, `short_trade_count`, `long_share` after `trade_count`.

**Tests**

- Index row from a state with mixed trades → correct split and `mixed`.
- Index row from long-only state → `long_only`, `short_trade_count == 0`.
- Older index parquet without the new keys loads in `load_observatory_frame` (keys filled with `None`).
- `--rebuild-direction` on the RS2 golden study output: fills keys; all pre-existing columns byte-equal before/after.
- `STUDY_INDEX_KEYS` column assertion updated; `tuple(cli_row.keys()) == R18_INDEX_METRIC_KEYS` unchanged.
- Failed / pending / soft-resume rows from `_failed_index_row` contain every `DA_DIRECTION_INDEX_KEYS` key as `None`; a mixed ok+failed study writes `list(index.columns) == list(STUDY_INDEX_KEYS)`.

**Acceptance:** `python -m thesistester study report results/studies/progB_w1_ext_ma --rebuild-direction` on the operator machine yields `long_only` on every cell (this is the expected, confirming result). Observatory banner shows the count.

**Regression safety:** additive study-index keys only; R18/CLI untouched; existing metric values never rewritten; Observatory tolerant of missing keys; no engine touch; no bundle-hash change.

---

### DA3 — Engine: `same_bar_opposite_direction` policy (opt-in)

**Goal:** make the tie-break a declared decision.

**Files**

- `thesistester/engine/backtest.py`
- `thesistester/api.py` (`_BACKTEST_DEFAULTS`, `run_backtest` passthrough)
- `thesistester/study/schema.py` (`constants.backtest.same_bar_opposite_direction`)
- `pages/7_Backtest.py` (advanced expander select; default legacy)
- `tests/test_backtest_direction_collision.py` (extend), `tests/study/test_study_schema.py`
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`

**Engine kwarg** (keyword-only, after the existing `*` in `simulate_trades`)

```python
same_bar_opposite_direction: str = "legacy"   # "legacy" | "skip_both" | "raise"
```

DA1's diagnostic is computed after the admission loop, so `skip_both` appears as `resolved_none` without a second pass.

- `legacy` — current behaviour; diagnostic (DA1) reports `policy: legacy`.
- `skip_both` — for each collision pair under `single_position` / `single_setup` (same group key), skip **both** candidates with new `skip_reason = "direction_conflict"`, `blocking_trade_id = NA`. Only emitted when the policy is not `legacy`, so legacy `skipped_signals` frames are unchanged.
- `raise` — `ValueError` naming the first colliding `(entry_bar_index, signal_ids)`. For CI-guarding studies.

Under `allow_all` and `single_direction` the policy is a no-op (no collision resolution happens there); documented.

**Schema:** optional key; validator accepts the three tokens; expand passes it through `backtest` constants; Program B generator gets a `--same-bar-policy` flag used by DA6.

**Tests**

- `skip_both` on the 3-touch fixture → 0 trades, 6 skipped with `direction_conflict`.
- `raise` → `ValueError` with both `signal_id`s in the message.
- `legacy` → identical frames to a pre-PR capture (assert equality on the fixture).
- Goldens unchanged.

**Regression safety:** keyword-only, default legacy; new `skip_reason` only appears under non-default policy; no sort change.

---

### DA4 — Engine: `fade` and `continuation` triggers (approach-side aware)

**Goal:** a level trigger whose side is a function of where price came from, so `direction: both` can never yield an opposite-direction pair on one bar.

**Files**

- `thesistester/engine/signals.py` — `VALID_TRIGGERS += {"fade", "continuation"}`; `_check_fade`, `_check_continuation`; shared `_approach_side(df, zone, trigger_bar_idx) -> "above" | "below" | None`
- `thesistester/setup.py` — **same** `VALID_TRIGGERS` tokens (schema imports this frozenset; both copies must stay in lockstep); `trigger_params` defaults
- `thesistester/study/schema.py` (`VALID_TRIGGERS` import surface)
- `pages/3_Setup_Builder.py`, `pages/15_Studies.py` (trigger select options)
- `tests/test_signals_fade.py` (new), `tests/test_r3_point_in_time.py` (future-shock case), `tests/fixtures/golden/` — **new** `fade_enabled_*` golden set via a `generate_fade_enabled.py` / `record_fade_enabled_golden.py` pair mirroring the OTF/entry-window goldens
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/USER_GUIDE.md`, `docs/METRICS_GLOSSARY.md` (if new signal columns), `docs/ARCHITECTURE.md`, `tests/fixtures/golden/README.md`

**Semantics (locked)**

Let `prev_close = close[trigger_bar_idx − 1]`, `bar` the trigger bar, zone `[zone_low, zone_high]`.

```
touched         := bar.low <= zone_high and bar.high >= zone_low
approach_side   := "above" if prev_close > zone_high
                   "below" if prev_close < zone_low
                   None    otherwise (prev_close inside zone, or no previous bar)

fade:          approach "above" → long   (price fell into support, buy the test)
               approach "below" → short  (price rose into resistance, sell the test)
continuation:  approach "above" → short  (price fell into the level, sell the break)
               approach "below" → long
```

- A signal is emitted only if `touched and approach_side is not None`. Exactly one direction **per zone per bar**. `direction` argument filters: `long` / `short` keep only that side; `both` keeps whichever the approach implies. Two zones on one bar can still emit opposite directions (prev close between them) — the same cross-zone object as `reject` / `reclaim`. Do not assert `groupby(bar_index).direction.nunique().max() == 1` on multi-zone fixtures.
- **Emit-once:** do not drop `_check_fade` / `_check_continuation` inside `for d in directions` unless the checker returns `None` when `d` ≠ implied side. If the checker ignores `d` and emits the approach side, the loop would write **two duplicate same-side candidates**. Prefer one call per zone (outside the direction loop), then filter on `direction`.
- Optional `trigger_params`: `require_close_confirmation: bool = False` — for `fade`, also require `bar.close` back on the approach side of the zone (mirrors `_check_reject` geometry); for `continuation`, require `bar.close` through the far edge. Default off so the base trigger is the exact directional analogue of `touch`.
- `entry_model` stays `candidate_next_bar_open`; `entry_ref = bar.close`. All existing exposure/cost/intrabar logic applies unchanged.
- **`approach_side` is fade/continuation-only.** Do **not** add it to `_SIGNAL_COLUMNS`, `_empty_signals_df`, or `_make_signal`. Those frames are written to hashed `signals.parquet` (`_hash_dataframe` includes column names and dtypes); widening every trigger — including `touch` — would change `canonical_bundle_hash` of every future default run vs the recorded Run 1 bundles, and no existing golden pins that (legacy pipeline builds signals by hand; RS2 is an expansion golden). Attach `approach_side` in `generate_signals` **after** `_make_signal`, and only on rows whose `trigger` is `fade` or `continuation`. Empty frames and all legacy triggers keep today's column set. Downstream OTF/attribution already select by name and must tolerate a missing key. Enabled-OTF / entry-window goldens project a **column subset** (`_SIGNAL_PROJECTION_COLUMNS`) — do **not** add `approach_side` there. If a new golden serialises a fade signals frame, it is a new fixture, never a regen.
- Multi-timeframe: reuses `_prepare_trigger_dataframe`; `prev_close` is the previous **trigger-timeframe** bar close.

**PIT:** `prev_close` is strictly in the past; appending future bars cannot change any emitted signal. Test asserts frame equality after appending 50 bars.

**Tests**

- Hand fixtures: approach from above + touch → `fade` long, `continuation` short; from below → mirrored; prev close inside zone → no signal; first bar → no signal.
- `direction="long"` filters out the short case.
- `both` never yields two directions **for one zone** on one bar. Property test: single-zone OU series `groupby(bar_index).direction.nunique().max() == 1`. A separate two-zone fixture documents that cross-zone opposite pairs remain possible.
- `require_close_confirmation` cases.
- Through `simulate_trades` with `single_position` **and one zone**: `direction_collision_diagnostic.candidate_pairs == 0`.
- New golden recorded and asserted; existing goldens unchanged.
- `generate_signals(..., trigger="touch")` column set equals pre-PR `_SIGNAL_COLUMNS` (no `approach_side`). A `touch` `run_experiment` bundle has `canonical_bundle_hash` identical to a pre-PR capture of the same fixture.

**Regression safety:** new tokens only; `touch` semantics and `_SIGNAL_COLUMNS` untouched; `approach_side` never appears on legacy-trigger frames; `canonical_bundle_hash` of a default `touch` bundle identical to pre-PR; new golden instead of regen.

---

### DA5 — Drift null next to every expectancy (opt-in)

**Goal:** a study cell reports how far its `expectancy_r` sits from a direction-matched random-entry null on the same bars, same SL/TP, same costs.

**Files**

- `thesistester/study/schema.py` — `report.random_baseline: {enabled: bool=false, n_replicas: int=50, random_state: int=42}`
- `thesistester/study/execute.py` — after each cell, if enabled, call `analytics.overfitting.vs_random_benchmark` with the cell's `execution_kwargs` (same `exposure_policy`, flatten, costs, intrabar). Append the mapped keys to `STUDY_INDEX_KEYS` (still not R18). Map existing return keys:
  `null_expectancy_mean` → `random_null_expectancy_r`,
  `null_expectancy_std` → `random_null_std_r`,
  `p_value_greater_or_equal` → `random_p_value_ge`,
  plus `expectancy_minus_null_r` = `expectancy_r - random_null_expectancy_r`.
- `thesistester/study/report.py` — overview + ranked columns; rank stays `primary_metric` (never re-rank by the null)
- `thesistester/study/observatory.py`, `pages/16_Study_Observatory.py` — columns + a `drift_class` facet: `above_null` if `random_p_value_ge < 0.05`, `at_null` otherwise, `unknown` when disabled
- `tests/study/test_study_execute.py`, `tests/study/test_study_report.py`, `tests/study/test_study_observatory.py`
- `docs/STUDY_RUNNER.md`, `docs/METRICS_GLOSSARY.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

**Notes**

- `random_entry_signals` already samples directions from the reference trades (`thesistester/analytics/overfitting.py`), so a long-only cell gets a long-only null — the correct drift comparator. Pass `execution_kwargs` through unchanged (`exposure_policy`, flatten, costs, intrabar).
- Cost: `n_replicas × simulate_trades(n ≈ trade_count)`; at 50 replicas this is small relative to level computation. Off by default; Program B Run 2 turns it on at 50.
- Not a significance claim. `METRICS_GLOSSARY.md` wording: "percentile of observed E among seeded random-entry replicas; diagnostic".

**Regression safety:** off by default; index keys additive; execution of the cell itself unchanged (null computed after the bundle is written and hashed).

---

### DA6 — Program B Run 2 packet and runbook v2 (docs + generator)

**Goal:** re-run the 944-cell 15s grid once, correctly, and lock a readout that cannot hide a one-sided sample.

**Files**

- `examples/studies/program_b/generate_program_b_yaml.py` — flags `--trigger {touch,fade}`, `--same-bar-policy`, `--random-baseline N`, `--output-dir`; default output unchanged (Run 1 files stay reproducible)
- `examples/studies/program_b_run2/` — generated 23 YAMLs + `manifest.yaml` + `README.md`
- `examples/studies/program_b/validate_program_b_yaml.py` — accept a manifest path; validate the Run 2 lock table
- `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` — §1 gains a **Run 2 lock table**; §4 gains the Run 2 list; §5 gains the readout lock below; Run 1 table kept as historical with the long-only callout
- `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md` — Factor C note: `fade` is the level-test trigger; `touch` retained for continuation-agnostic frequency studies only
- `tests/study/test_program_b_yaml.py` — Run 2 manifest expands to 944 cells; every YAML carries the Run 2 locks

**Run 2 locks (delta vs Run 1 only)**

| Lock | Run 1 | Run 2 |
|---|---|---|
| Trigger | `touch` @ 1min | **`fade`** @ 1min (`require_close_confirmation: false`) |
| `same_bar_opposite_direction` | (legacy, implicit) | `raise` — a collision is a spec error. Valid because each Run 2 cell is **one zone** (`anchor_rules`, one partner or solo point). Do not use `raise` on multi-zone `global_cluster` studies. |
| `report.random_baseline` | off | `enabled: true, n_replicas: 50` |
| Everything else | — | identical (MNQ, `both`, `single_position`, 80/80, costs, flatten 16:00, 15s ingest, `min_trades` 30) |

**Readout lock additions (§5)**

- A cell is **unreadable** if `directional_integrity != "mixed"` **and** the core is not a directional-by-construction level (e.g. `dSP_Above` may legitimately be short-heavy). Record the reason.
- Report `long_expectancy_r` / `short_expectancy_r` with their `n`; a cell is **+E** only if the pooled E qualifies **and** neither side has `n ≥ 30` with `E < −0.03` (a one-sided edge must be named as such, not pooled).
- Report `expectancy_minus_null_r`; a cell whose pooled E qualifies but `random_p_value_ge ≥ 0.05` is **hold**, not +E.
- Run 1 vs Run 2 on the same cell is **not** a paired comparison (different trigger). Report both rows; do not compute ΔE.

**Acceptance:** `validate_program_b_yaml.py examples/studies/program_b_run2/manifest.yaml` prints `ok 23 studies / 944 cells`; smoke cell runs with `collision_pairs == 0` and `directional_integrity == "mixed"` (or a documented reason).

**Regression safety:** Run 1 YAMLs untouched; generator defaults unchanged; no engine code.

---

## 5. What the desk does with Run 1 now

1. Merge DA0. Annotate the Notion *Run 1 results — Edge Finder* page header: "Long-only sample (touch + both + single_position). Directional read pending DA2."
2. Merge DA2; run `study report --rebuild-direction` over `results/studies/progB_*`. Expected: every cell `long_only`. If any cell is *not* `long_only`, stop and report — that would falsify §0 and this plan.
3. Do not rerun anything until DA4 + DA6 are merged. A rerun on `touch` reproduces the artefact.
4. Read Run 1 as "buy-the-touch" only. `pmLow × Pivot_1m_Low` +0.33 is a statement about buying pmLow; `ONH × EMA_9_5min` −0.28 says nothing about shorting ONH.

---

## 6. Test matrix summary

| PR | New tests | Goldens |
|---|---|---|
| DA1 | collision diagnostic × 3 policies; legacy return shapes | unchanged |
| DA2 | index split; integrity classes; rebuild idempotence; tolerant load; `_failed_index_row` seeds DA keys | unchanged |
| DA3 | `skip_both`, `raise`, `legacy` equality | unchanged |
| DA4 | fade/continuation geometry; one-per-zone filter; two-zone cross-zone doc; PIT; touch column-set + bundle-hash identity; through-engine zero collisions on one zone | **+1 new** (`fade_enabled_*`) |
| DA5 | baseline keys; off-by-default; rank unaffected | unchanged |
| DA6 | Run 2 manifest expand + lock validation | unchanged |

Full suite (`python3 -m pytest -q`) must stay green on every PR. Do not freeze a test count in this file; use the suite size on that PR's `main`.

---

## 7. Copy-paste prompt (one PR at a time)

```text
You are implementing DA<k> from docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md
in the ThesisTester repo. Read §0, §2, and §4 DA<k> in full before writing code.

Hard rules:
- Regression-safe per docs/ENGINEERING_PROPOSAL.md §4: additive, keyword-only,
  default = legacy. Do not edit _check_touch, the ["long","short"] loop, or the
  simulate_trades candidate sort key. Do not regenerate any golden fixture.
- Run `python3 -m pytest -q` before and after; both must be green. Run the golden
  tests explicitly and paste their output in the PR body.
- Update the docs listed for DA<k> in the same PR (ASSUMPTIONS_AND_LIMITATIONS,
  METRICS_GLOSSARY, ARCHITECTURE, ENGINEERING_ROADMAP status row, plus the
  operator docs named). Add a "Regression safety" paragraph to the PR body.
- Scope is DA<k> only. If you find you need something from another DA PR,
  stop and say so rather than widening the diff.
- Series code is DA. Do not implement or title this work as DI — that is
  Discuss Intelligence.
```

---

## 8. Follow-ups (out of scope, recorded)

- **Trade-journal import** (executed fills → same engine, same costs) so discretionary outcomes can be compared to the systematic counterfactual per setup. Highest long-run value; separate plan.
- **Conditional locks** for a small Program C: pre-registered ToD window and OTF state as part of the L0 lock, not post-hoc slices.
- **Notion Results schema**: add `Long n`, `Short n`, `Integrity`, `E − null` columns so DA2/DA5 outputs have a home. Manual desk change; not a repo task.
