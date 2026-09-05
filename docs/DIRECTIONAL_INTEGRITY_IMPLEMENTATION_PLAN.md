# Directional Integrity & Edge Attribution — implementation plan (DI)

**Status:** DI0 proposed (this document). DI1–DI6 not started.  
**Series prefix:** `DI` (DI0–DI6). Does not reopen AO, RS, SO, AH.  
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

1. `thesistester/engine/signals.py::_check_touch` is direction-agnostic: it fires when `bar.low <= zone_high and bar.high >= zone_low`. With `direction == "both"` the simple-trigger loop iterates `["long", "short"]`, so every touch bar emits **two** candidates — long first (`signal_id = k`), short second (`signal_id = k+1`) — with identical `bar_index`, identical `entry_bar_index`, identical `entry_price`.
2. `thesistester/engine/backtest.py::simulate_trades` sorts candidates by `(entry_bar_index, bar_idx, signal_id)` whenever `exposure_policy != "allow_all"`. The long is processed first and accepted; the short on the same bar is then blocked by the long it shares an entry bar with and skipped as `overlapping_position`. Deterministic, every bar.
3. `anchor_rules` mode does not bypass this: for `touch` it enters the same `else` branch in `generate_signals`. The Study Runner executes `api.run_experiment → api.generate_signals → api.run_backtest → simulate_trades`, so every Program B cell went through this path.

Note that there is **no** exposure policy under which `touch` + `both` is a meaningful directional test: `allow_all` opens a long *and* a short at the same price on the same bar (a hedged pair whose net is `−2 × costs` under symmetric SL/TP); `single_direction` accepts both sides and produces the same hedged pairs; `single_position` / `single_setup` collapse to long-only via `signal_id` order.

### 0.3 Evidence

Synthetic mean-reverting (OU) 1-minute series crossing a two-level zone 516 times, `touch`, `both`, SL/TP 40/40, run against `main` `bece2f4`:

```python
zones = detect_confluence_zones(df, ["LVL_A", "LVL_B"], 0.25, tolerance_ticks=8, min_confluences=2)
sigs = generate_signals(df, zones, trigger="touch", direction="both", tick_size=0.25)
trades, skipped = simulate_trades(df, sigs, tick_size=0.25, point_value=2.0,
                                  stop_loss_ticks=40, take_profit_ticks=40,
                                  exposure_policy=policy, return_skipped_signals=True)
```

| `exposure_policy` | trades | long | short | shorts skipped as `overlapping_position` |
|---|---:|---:|---:|---:|
| `allow_all` | 1032 | 516 | 516 | 0 |
| `single_position` | 235 | **235** | **0** | 516 |
| `single_direction` | 470 | 235 | 235 | 0 (skipped as `overlapping_direction` instead) |

Corroboration inside the Run 1 corpus itself (Notion *Run 1 results — Edge Finder*, 2026-09-05): the "kill list" (worst E at n≥100) is dominated by **highs** and `*_High` partners — `ONH × EMA_9_5min` −0.28, `LondonHigh × Pivot_5m_High` −0.21, `pdHigh × VWAP_rolling_30min` −0.20, `dSP_Above × Pivot_4h_High` −0.21 — while the playable list is rich in **lows** — `pmLow × Pivot_1m_Low` +0.33, `ONL × EMA_21_5min` +0.23, `pdLow × Pivot_5m_High` +0.23, `pRTH_Low × VWAP_rolling_4h` +0.18. Buying supports and buying resistances is exactly the fingerprint of a long-only sample on an upward-drifting MNQ window. It is not evidence that lows are edges and highs are not.

### 0.4 What this is not

- Not a `simulate_trades` bug. The engine does what the exposure contract says. The tie-break is deterministic and documented by the sort key.
- Not a reason to discard the corpus. The 944 bundles are valid **long-side** measurements. DI2 makes that readable without a rerun.
- Not a Program A vs Program B issue. Both inherit the same lock.

### 0.5 Golden fixtures encode the artefact

`tests/fixtures/study/golden/study.spec.yaml` is `touch` + `both` + `single_position`. `tests/fixtures/golden/pipeline.py` is `allow_all`. Every DI change must leave both goldens byte-identical under default flags. No `GOLDEN_REGEN` in this series.

---

## 1. Goals / non-goals

**Goals**

1. Make single-sidedness **visible** on every study row, in the Observatory, and in the Notion readout, for both existing and future corpora (DI1, DI2).
2. Give the engine an **explicit, opt-in** rule for same-bar opposite-direction candidates so silent tie-break can never again be mistaken for a decision (DI3).
3. Ship a trigger whose direction is **derived from approach side** — the only trigger that represents "fade the level" as a discretionary trader means it (DI4).
4. Put a **drift null** next to every expectancy so a long-only +0.07R on a bull window cannot read as edge (DI5).
5. Re-author the Program B packet as **Run 2** under the corrected trigger, with direction split and drift null in the readout lock (DI6).

**Non-goals**

- No re-interpretation of Run 1 in code. Judgement stays with Edge Finder.
- No change to `signal_id` assignment order, `simulate_trades` sort key, or any default.
- No new factor axes in Program B Run 2 beyond replacing `touch` with `fade`.
- No trade-journal import (tracked as a follow-up in §8).
- No Notion API writes from the repo.

---

## 2. Regression-safety envelope (applies to every DI PR)

| Rule (§4) | How DI satisfies it |
|---|---|
| Additive-only engine changes | New `simulate_trades` kwargs are keyword-only, default to legacy. New `SimulationResult` field has a default. No frame column added to `trades` or `skipped_signals` under default flags. |
| Golden-master before engine touch | DI1, DI3, DI4 each run `tests/test_golden_*.py` and the RS2 study golden unchanged. DI4 adds a **new** golden (`fade` fixture) rather than altering an existing one. |
| Opt-in, default-off | `same_bar_opposite_direction="legacy"` default. `fade` / `continuation` are new trigger tokens, never substituted for `touch`. Drift null is `report.random_baseline.enabled: false` by default. |
| Schema-versioned persistence | Study index gains keys; `STUDY_INDEX_KEYS` extended at the end; readers tolerate missing keys (older `study.index.parquet` still loads). |
| PIT proof | DI4 adds a future-shock test for `fade`. |
| Determinism | No randomness except DI5, which reuses the seeded `vs_random_benchmark`. |
| Same-PR docs | Each PR lists its doc edits. `ASSUMPTIONS_AND_LIMITATIONS.md` gets a new §"Direction attribution" in DI0 and is amended per PR. |
| Small surface | One concern per PR. DI3 and DI4 are independent and may land in either order after DI1. |

Forbidden in this series: editing `_check_touch`; reordering the `["long", "short"]` loop; changing the candidate sort key; regenerating any golden; changing `touch` semantics in any way.

---

## 3. PR sequence and dependencies

```
DI0  docs freeze + honesty callouts                (docs only)            ← this PR
DI1  engine: direction-collision diagnostic         (engine, additive)
DI2  direction split: summary → index → Observatory (analytics/study/UI)   ← unlocks Run 1 re-read
DI3  engine: same_bar_opposite_direction policy     (engine, opt-in)       (needs DI1)
DI4  engine: fade / continuation triggers           (engine/setup/schema/UI, opt-in)
DI5  study: drift null in index + Observatory       (analytics/study/UI, opt-in)  (needs DI2)
DI6  Program B Run 2 packet + runbook v2            (docs + generator)     (needs DI2, DI4, DI5)
```

DI2 is the first PR that changes what the desk can *see*; run it before any rerun decision. DI3 is the guard that prevents recurrence. DI4 is the product change. DI5/DI6 are the research payoff.

---

## 4. PR specifications

### DI0 — Docs freeze and honesty callouts (docs only)

**Files**

- `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md` (this file).
- `docs/README.md` — index row under *Engine / data contracts*.
- `docs/ENGINEERING_ROADMAP.md` — status-index row.
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md` — new subsection **"Direction attribution under `direction: both`"** stating §0.1–0.2 verbatim-short, with the three-policy table from §0.3.
- `docs/PROGRAM_B_OPERATOR_RUNBOOK.md` — one callout above §1: "Run 1 (this lock) is a long-only sample; see DI plan §0. Do not start Run 2 on this table."
- `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` — one callout above §6.0 with the same sentence for the L1 kill list.

**Acceptance:** docs render; no code; `pytest tests/test_docs*.py`-style doc-link tests (if any) green.

**Regression safety:** none required (docs only).

---

### DI1 — Engine diagnostic: same-bar opposite-direction collisions

**Goal:** quantify, on every simulation, how many candidate pairs shared `entry_bar_index` with opposite direction, and how the tie-break resolved them.

**Files**

- `thesistester/engine/backtest.py`
- `thesistester/api.py` (`run_backtest` return dict)
- `thesistester/research_bundle.py` (bundle write, additive key)
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

Computed inside `simulate_trades` after `ordered_candidates` is built (so it reflects post-cutoff candidates), before the blocking loop:

```python
{
  "policy": "legacy",                       # DI3 will report the active policy here
  "candidate_pairs": int,                   # (entry_bar_index, bar_idx) groups containing both directions
  "resolved_long": int,                     # pairs where the accepted trade is long
  "resolved_short": int,
  "resolved_none": int,                     # pairs where both were skipped (cutoff/cooldown/DI3 skip_both)
  "accepted_trade_share_from_pairs": float, # accepted trades that came from a collision pair / all accepted
}
```

Under `allow_all` the dict is emitted with `candidate_pairs` counted and `resolved_*` reflecting that both were accepted (`resolved_long = resolved_short = candidate_pairs`).

**API:** `run_backtest` adds `"direction_collision_diagnostic"` to its return dict. Bundle gets `direction_collision_diagnostic.json` (additive file; canonical bundle hash projection excludes it, as with other diagnostics — verify against `canonical_bundle_hash` exclusions and add if needed).

**Tests**

- Hand fixture: 3 touch bars, `both`, `single_position` → `candidate_pairs == 3`, `resolved_long == 3`, `resolved_short == 0`.
- Same fixture, `single_direction` → both sides accepted; assert `resolved_long == resolved_short == 3`, `resolved_none == 0`.
- `allow_all` → both accepted; same counts as `single_direction`.
- Legacy return shapes (`DataFrame`, `tuple`) untouched; `return_result=True` only path exposes the field.
- Golden tests unchanged.

**Acceptance:** all above green; `SimulationResult` construction sites that pass positional args still work (field has default).

**Regression safety paragraph (PR body):** no frame changes; no sort change; new dataclass field defaulted; diagnostic computed from existing local variables; goldens compared and identical.

---

### DI2 — Direction split: trade summary → study index → Observatory → re-read Run 1

**Goal:** every study cell shows long/short n and E, plus a `directional_integrity` class, without a rerun.

**Files**

- `thesistester/analytics/metrics.py` (reuse `summarize_trades_by_direction`; no new math)
- `thesistester/study/execute.py` — `R18_INDEX_METRIC_KEYS` additive tail; `build_index_row_from_state`; bundle rehydrate
- `thesistester/study/report.py` — `study.direction.csv`; overview columns
- `thesistester/study/observatory.py` — fact-table columns; facet; banner counts
- `pages/16_Study_Observatory.py` — cells table columns, `directional_integrity` facet, corpus banner line
- `thesistester/cli.py` — `study report --rebuild-direction` (reads `trades.csv` from each cell bundle; writes/updates index keys) — **this is how Run 1 is re-read**
- `tests/study/test_study_execute.py` (update exact-key assertion), `tests/study/test_study_report.py`, `tests/study/test_study_observatory.py`, `tests/test_cli.py`
- `docs/STUDY_RUNNER.md`, `docs/METRICS_GLOSSARY.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ARCHITECTURE.md`

**Index keys (appended to `R18_INDEX_METRIC_KEYS`, before `bundle_path`/`status`)**

```
long_trade_count, short_trade_count,
long_expectancy_r, short_expectancy_r,
long_share,                      # long_trade_count / trade_count, None when trade_count == 0
directional_integrity            # "long_only" | "short_only" | "mixed" | "empty"
collision_pairs, collision_resolved_long   # from DI1 when present, else None
```

Classification: `long_only` if `short_trade_count == 0 and trade_count > 0`; `short_only` symmetric; `mixed` otherwise; `empty` when `trade_count == 0`.

**Rehydrate:** `_read_bundle_trade_summary` already reads `trade_summary.json`; add `_read_bundle_trades(bundle_path) -> pd.DataFrame | None` reading `trades.csv` (nested or flat), then `summarize_trades_by_direction`. `--rebuild-direction` iterates `study.index.parquet` rows with a `bundle_path`, fills only the new keys, rewrites the parquet atomically, and never touches existing metric values. Idempotent.

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
- Exact-key test in `test_study_execute.py` updated to the new tuple.

**Acceptance:** `python -m thesistester study report results/studies/progB_w1_ext_ma --rebuild-direction` on the operator machine yields `long_only` on every cell (this is the expected, confirming result). Observatory banner shows the count.

**Regression safety:** additive keys only; existing metric values never rewritten; Observatory tolerant of missing keys; no engine touch.

---

### DI3 — Engine: `same_bar_opposite_direction` policy (opt-in)

**Goal:** make the tie-break a declared decision.

**Files**

- `thesistester/engine/backtest.py`
- `thesistester/api.py` (`_BACKTEST_DEFAULTS`, `run_backtest` passthrough)
- `thesistester/study/schema.py` (`constants.backtest.same_bar_opposite_direction`)
- `pages/7_Backtest.py` (advanced expander select; default legacy)
- `tests/test_backtest_direction_collision.py` (extend), `tests/study/test_study_schema.py`
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`

**Engine kwarg**

```python
same_bar_opposite_direction: str = "legacy"   # "legacy" | "skip_both" | "raise"
```

- `legacy` — current behaviour; diagnostic (DI1) reports `policy: legacy`.
- `skip_both` — for each collision pair under `single_position` / `single_setup` (same group key), skip **both** candidates with new `skip_reason = "direction_conflict"`, `blocking_trade_id = NA`. Only emitted when the policy is not `legacy`, so legacy `skipped_signals` frames are unchanged.
- `raise` — `ValueError` naming the first colliding `(entry_bar_index, signal_ids)`. For CI-guarding studies.

Under `allow_all` and `single_direction` the policy is a no-op (no collision resolution happens there); documented.

**Schema:** optional key; validator accepts the three tokens; expand passes it through `backtest` constants; Program B generator gets a `--same-bar-policy` flag used by DI6.

**Tests**

- `skip_both` on the 3-touch fixture → 0 trades, 6 skipped with `direction_conflict`.
- `raise` → `ValueError` with both `signal_id`s in the message.
- `legacy` → identical frames to a pre-PR capture (assert equality on the fixture).
- Goldens unchanged.

**Regression safety:** keyword-only, default legacy; new `skip_reason` only appears under non-default policy; no sort change.

---

### DI4 — Engine: `fade` and `continuation` triggers (approach-side aware)

**Goal:** a level trigger whose side is a function of where price came from, so `direction: both` can never yield an opposite-direction pair on one bar.

**Files**

- `thesistester/engine/signals.py` — `VALID_TRIGGERS += {"fade", "continuation"}`; `_check_fade`, `_check_continuation`; shared `_approach_side(df, zone, trigger_bar_idx) -> "above" | "below" | None`
- `thesistester/setup.py` (validator token list; `trigger_params` defaults)
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

- A signal is emitted only if `touched and approach_side is not None`. Exactly one direction per bar. `direction` argument filters: `long` / `short` keep only that side; `both` keeps whichever the approach implies.
- Optional `trigger_params`: `require_close_confirmation: bool = False` — for `fade`, also require `bar.close` back on the approach side of the level (mirrors `_check_reject` geometry); for `continuation`, require `bar.close` through the far edge. Default off so the base trigger is the exact directional analogue of `touch`.
- `entry_model` stays `candidate_next_bar_open`; `entry_ref = bar.close`. All existing exposure/cost/intrabar logic applies unchanged.
- New signal columns: `approach_side` (`above`/`below`). Added to `_SIGNAL_COLUMNS` with `None` for other triggers — verify that `_empty_signals_df` and downstream OTF/attribution tolerate it (they select by name). If any golden serialises the full signals frame, add the column to that golden **only via a new fixture**, never by regenerating.
- Multi-timeframe: reuses `_prepare_trigger_dataframe`; `prev_close` is the previous **trigger-timeframe** bar close.

**PIT:** `prev_close` is strictly in the past; appending future bars cannot change any emitted signal. Test asserts frame equality after appending 50 bars.

**Tests**

- Hand fixtures: approach from above + touch → `fade` long, `continuation` short; from below → mirrored; prev close inside zone → no signal; first bar → no signal.
- `direction="long"` filters out the short case.
- `both` never yields two signals on one bar (property test over a random OU series: `groupby(bar_index).direction.nunique().max() == 1`).
- `require_close_confirmation` cases.
- Through `simulate_trades` with `single_position`: `direction_collision_diagnostic.candidate_pairs == 0`.
- New golden recorded and asserted; existing goldens unchanged.

**Regression safety:** new tokens only; `touch` untouched; new column is `None` for all legacy triggers; new golden instead of regen.

---

### DI5 — Drift null next to every expectancy (opt-in)

**Goal:** a study cell reports how far its `expectancy_r` sits from a direction-matched random-entry null on the same bars, same SL/TP, same costs.

**Files**

- `thesistester/study/schema.py` — `report.random_baseline: {enabled: bool=false, n_replicas: int=50, random_state: int=42}`
- `thesistester/study/execute.py` — after each cell, if enabled, call `analytics.overfitting.vs_random_benchmark` with the cell's `execution_kwargs` (same `exposure_policy`, flatten, costs, intrabar) and write:
  `random_null_expectancy_r`, `random_null_std_r`, `random_p_value_ge`, `expectancy_minus_null_r`
- `thesistester/study/report.py` — overview + ranked columns; rank stays `primary_metric` (never re-rank by the null)
- `thesistester/study/observatory.py`, `pages/16_Study_Observatory.py` — columns + a `drift_class` facet: `above_null` if `random_p_value_ge < 0.05`, `at_null` otherwise, `unknown` when disabled
- `tests/study/test_study_execute.py`, `tests/study/test_study_report.py`, `tests/study/test_study_observatory.py`
- `docs/STUDY_RUNNER.md`, `docs/METRICS_GLOSSARY.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`

**Notes**

- `random_entry_signals` is direction-matched, so a long-only cell gets a long-only null — the correct drift comparator.
- Cost: `n_replicas × simulate_trades(n ≈ trade_count)`; at 50 replicas this is small relative to level computation. Off by default; Program B Run 2 turns it on at 50.
- Not a significance claim. `METRICS_GLOSSARY.md` wording: "percentile of observed E among seeded random-entry replicas; diagnostic".

**Regression safety:** off by default; index keys additive; execution of the cell itself unchanged (null computed after the bundle is written and hashed).

---

### DI6 — Program B Run 2 packet and runbook v2 (docs + generator)

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
| `same_bar_opposite_direction` | (legacy, implicit) | `raise` — a collision is a spec error under `fade` |
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

1. Merge DI0. Annotate the Notion *Run 1 results — Edge Finder* page header: "Long-only sample (touch + both + single_position). Directional read pending DI2."
2. Merge DI2; run `study report --rebuild-direction` over `results/studies/progB_*`. Expected: every cell `long_only`. If any cell is *not* `long_only`, stop and report — that would falsify §0 and this plan.
3. Do not rerun anything until DI4 + DI6 are merged. A rerun on `touch` reproduces the artefact.
4. Read Run 1 as "buy-the-touch" only. `pmLow × Pivot_1m_Low` +0.33 is a statement about buying pmLow; `ONH × EMA_9_5min` −0.28 says nothing about shorting ONH.

---

## 6. Test matrix summary

| PR | New tests | Goldens |
|---|---|---|
| DI1 | collision diagnostic × 3 policies; legacy return shapes | unchanged |
| DI2 | index split; integrity classes; rebuild idempotence; tolerant load | unchanged |
| DI3 | `skip_both`, `raise`, `legacy` equality | unchanged |
| DI4 | fade/continuation geometry; filter; one-per-bar property; PIT; through-engine zero collisions | **+1 new** (`fade_enabled_*`) |
| DI5 | baseline keys; off-by-default; rank unaffected | unchanged |
| DI6 | Run 2 manifest expand + lock validation | unchanged |

Full suite (`python3 -m pytest -q`) must stay green on every PR (1516+ tests at time of writing).

---

## 7. Copy-paste prompt (one PR at a time)

```text
You are implementing DI<k> from docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md
in the ThesisTester repo. Read §0, §2, and §4 DI<k> in full before writing code.

Hard rules:
- Regression-safe per docs/ENGINEERING_PROPOSAL.md §4: additive, keyword-only,
  default = legacy. Do not edit _check_touch, the ["long","short"] loop, or the
  simulate_trades candidate sort key. Do not regenerate any golden fixture.
- Run `python3 -m pytest -q` before and after; both must be green. Run the golden
  tests explicitly and paste their output in the PR body.
- Update the docs listed for DI<k> in the same PR (ASSUMPTIONS_AND_LIMITATIONS,
  METRICS_GLOSSARY, ARCHITECTURE, ENGINEERING_ROADMAP status row, plus the
  operator docs named). Add a "Regression safety" paragraph to the PR body.
- Scope is DI<k> only. If you find you need something from another DI PR,
  stop and say so rather than widening the diff.
```

---

## 8. Follow-ups (out of scope, recorded)

- **Trade-journal import** (executed fills → same engine, same costs) so discretionary outcomes can be compared to the systematic counterfactual per setup. Highest long-run value; separate plan.
- **Conditional locks** for a small Program C: pre-registered ToD window and OTF state as part of the L0 lock, not post-hoc slices.
- **Notion Results schema**: add `Long n`, `Short n`, `Integrity`, `E − null` columns so DI2/DI5 outputs have a home. Manual desk change; not a repo task.
