# Journal → Study Implementation Plan (JS)

**Series code:** JS
**Status:** JS1 landed (zone attribution + Q3 Zones + `journal zones`). JS0 locked.
**Date:** 2026-09-07 (rev 2 — review locks vs live engine/schema)
**Depends on:** TJ9 landed (`docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md`).
**Regression frame:** `docs/ENGINEERING_PROPOSAL.md` §4 (additive, keyword-only,
default = legacy; golden-master operational spec §4.1; per-PR checklist §4.2).

Every later JS PR implements exactly one milestone below. Do not reopen TJ, DA,
Program B, or a 15s/tick trigger lane from a JS PR.

---

## 0. Finding (locked — verified 2026-09-07 against `origin/main`)

### 0.1 Statement

The journal already measures what the desk *did*. It does not say which
**confluence zone** or which **engine trigger** a real fill corresponds to, and
it does not turn that observation into a **StudySpec the desk can run on
history it did not trade**. That gap is the only remaining research-facing
hole after TJ9. Filling it is valuable only if the output changes a desk
decision (where to spend attention; whether a rule implied by live behaviour
has edge off the discovery window; whether to keep trading it). Adding
columns or a page that do not change a decision is out.

### 0.2 What the journal already emits (do not rebuild)

Verified in `thesistester/journal/` on this `main`:

| Milestone | Artifact / columns | Decision it already serves |
|---|---|---|
| TJ1–TJ4 | `FillRecord` → `JournalTrade` → `reconcile.json` | Q1 real-cost P&L |
| TJ5 | 15s join; optional Tick-Last walk; `resolution ∈ {15s, tick}` | clock + MAE/MFE |
| TJ6 | `levels_within_tolerance`, `nearest_level_token`, `nearest_level_distance_ticks`, `level_context`, `tag_alignment`, `intent_mismatch` (`journal/levels.py`) | Q3 *individual* tokens |
| TJ7 | fixed-bracket replay, seeded direction-shuffle null, declared rules (`journal/counterfactual.py`) | Q4/Q5/Q6 on the desk's own entries |
| TJ8 | one named hash-verified cell; `executed_cell` / `near_level` / `discretionary_only` / `systematic_unfilled` / `product_mismatch`; forward ledger | Q7/Q8 for **one** declared cell |
| TJ9 | page 17 + `journal report`; Q1–Q8; n ≥ 30 gate; `REPORT_HONESTY` | readout |

Journal production code imports **five** engine-side symbols and no more
(`rg "^from thesistester" thesistester/journal/*.py`):

- `levels.session_date.trading_session_date` — same ETH 18:00 session date as studies
- `levels.defaults.DEFAULT_LEVELS_SETTINGS` + `study.schema.closed_level_token_set` — which columns to *read*
- `research_bundle.canonical_bundle_hash` — TJ8 bundle verify
- `persistence.local_store.get_store_root` — `.thesistester_store/journal/v1/`

There is no call to `simulate_trades`, `compute_all_levels`,
`detect_confluence_zones`, or `generate_signals`. AST tests in
`tests/test_journal_report.py` (and TJ6/TJ7 tests) enforce the first two.
Store writes fail closed on `results/studies/` (`_assert_output_dir`).

**TJ6 is not zone attribution.** `_attribute_trade` (`journal/levels.py`)
measures distance from the fill to each closed token and keeps those within
tolerance. It never clusters tokens into a zone and never records width or
member count.

**TJ8 is not trigger inference.** `load_named_cell` (`journal/match.py`)
reads one declared bundle's `trades.parquet` (required) and
`signals.parquet` (optional; empty frame if absent) plus
`trade_summary.json` / `dataset_meta.json`. It classifies time/price
proximity plus hold/risk compatibility. It does not ask what trigger
the engine would have called at the fill. There is no `signals.csv` /
`trades.csv` inside a research bundle.

### 0.3 Engine surfaces that already exist (reuse; do not fork)

`detect_confluence_zones` (`thesistester/engine/confluence.py`) is a pure,
no-lookahead function. Inputs: levels frame, `level_columns`, `tick_size`,
`tolerance_ticks`, `min_confluences` (default 2), `max_confluences` (default 5,
capped at 5). Output columns: `timestamp`, `bar_index`, `zone_low`,
`zone_high`, `zone_mid`, `level_count`, `level_names` (`|`-separated),
`level_prices`. Greedy non-overlapping windows; only levels present on bar
*i* are used for bar *i*. **JS1 calls this function.** It does not
reimplement clustering and does not call `compute_all_levels`.

Trigger classifiers in `thesistester/engine/signals.py` are **private**:
`_check_touch`, `_check_reject`, `_check_break`, `_check_reclaim`,
`_check_fade`, `_check_continuation`, `_check_confirm_3bar`. Simple
checkers evaluate on the **prepared trigger frame** from
`_prepare_trigger_dataframe` (they read `base_end_timestamp` /
`trigger_bar_end_timestamp`). Passing raw OHLCV into `_check_*` is a
`KeyError`. Signatures are **not uniform**: touch/reject/break/reclaim
take `direction`; fade/continuation do **not** — they derive one implied
side from the previous trigger-bar close vs the zone
(`_approach_side` / `_implied_approach_direction`). Fade on a one-row
frame always returns `None` (no previous bar).
`VALID_TRIGGERS = {touch, reject, break, reclaim, 3c, fade, continuation}`.
There is no public read-only entry point. **JS2 adds one wrapper** that
prepares the frame, then delegates to those existing functions. It does
not edit their bodies.

`TRIGGER_TIMEFRAME_CHOICES = (base, 1min, 5min, 15min)` (`thesistester/setup.py`).
`15s` is not a trigger timeframe. `ingestion_mode=15s_primary_derive_1m`
(`thesistester/data/derive.py`) derives a 1m parent whose `timestamp` is
the **bar open** (minute floor). **The engine has no 15s-clock trigger
lane.** Building one is parked (§9), not JS.

### 0.4 Study schema surfaces that already exist (do not add factor axes)

`thesistester/study/schema.py` already accepts the factor axes JS3 will
populate: `core_level`, `partner_levels`, `confluence_mode`, `trigger`,
`trigger_timeframe`, `otf`, `direction`. Required: `core_level` +
`partner_levels`. Constants already include `tolerance_ticks`,
`min_confluences`, `max_confluences`, `entry_window`. Optional `lineage`
is a **closed** key set (`parent_output_dir`, `parent_identity_hash`,
`parent_run_name`, `admit`) used by SAF Admit-follow-up — **do not reuse
it** for journal provenance.

`_STUDY_KEYS` is a closed allowlist. Unknown keys fail
(`_unknown_keys(study, _STUDY_KEYS)`). JS3 adds one optional key,
`holdout` (§3.3). Absent `holdout` is valid and is today's behaviour.

There is no dataset date-window field. The dataset file *is* the period.
`dataset.path` is a required string; the file need not exist at
`validate_study_spec` time. `study_identity_hash` (`study/expand.py`) is
SHA-256 of the normalized spec with sorted keys — a present `holdout`
block is therefore part of identity automatically.

Expand (`study/expand.py`) does **not** invent silent cell defaults.
Every expansion cell must carry `confluence_mode`, `trigger`, and
`trigger_timeframe` (`_REQUIRED_CELL_AXES`). `study.constants.backtest`
must be a non-empty mapping that includes `stop_loss_ticks` and
`take_profit_ticks` or expand refuses. For `global_cluster`, expand sets
`min_confluences = max_confluences = len(core + partners)` — JS1
min/max clustering knobs do **not** survive into the cell setup.

`run_study` (`study/execute.py`) already refuses **before** writing
expansion artifacts (`confirm_above_runs`, identity mismatch). The
dataset is **not** loaded in that window today (cells load it later).
The JS3 session-overlap refuse therefore **loads timestamps in that
same gate window** when `holdout` is present; it does not wait until
cell start (too late — artifacts would already be written).
`study/launch.py` does not import `execute` and must **not** grow a
dataset scan; preview may show the holdout block.

### 0.5 Product-clock gap (inherited from TJ §0.8; not re-measured here)

TJ §0.8 is locked: median hold 24 s; 36% of May round trips close inside
one 15s bar; Program B Run 2 is `fade` @ 1min, 80/80. Different products.
Nothing in the research corpus has tested a 24-second product. JS studies
are therefore a **1m proxy** of the scalp book, not a test of the scalp
product. `product_mismatch` (TJ8) will fire on hold/risk for most of
those trades against a 1m cell — that is a finding, not a bug.

This PR does **not** contain a TJ7 Q4 15s-vs-tick readout. Those numbers
are desk-private and are a §8 workflow item before Gate A / the parked
15s-lane decision. Do not invent them.

### 0.6 What this series does not claim

- That the desk's May tags, zones, or hours are an edge. n is small; one
  month; one contract; slices are multiple comparisons (TJ §0.10).
- That inferring an engine trigger reconstructs what the trader saw.
  Inference is "what `classify_zone_triggers` would have printed on the
  completed bar before the fill."
- That a journal-derived StudySpec is ready to Admit. It is a draft. The
  human fills `dataset.path`, runs it as any other study, and reads JS4.

### 0.7 Review locks (rev 2 — verified 2026-09-07 against this tree)

These are plan defects found against live helpers. Later JS PRs implement
the corrected contracts in §3, not the rev-1 wording.

| Defect | Live fact | Locked correction |
|---|---|---|
| TJ6 artifact named `attribution.parquet` in §2 | `journal/levels.py` writes `journal_attribution.parquet` | Use that name |
| TJ8 `signals.csv` | Bundles ship `signals.parquet` / `trades.parquet` | JS4 reads those members via `load_named_cell` |
| Wrapper calls `_check_*` on raw OHLCV | Checkers need `_prepare_trigger_dataframe` columns | Wrapper prepares internally |
| Wrapper signature treats fade like touch | `_check_fade` has no `direction`; needs previous bar | Delegate with real signatures; never one-row fade |
| "close strictly before fill" on 1m stamps | 1m `timestamp` is bar **open**; TJ6 `_expected_previous_open` at exact minute equality walks back **two** minutes | JS uses `bar_open + 1min <= entry` (just-closed bar). Do **not** reuse `_expected_previous_open` for zones |
| JS2 golden inclusion on every `signals.csv` | Fade/OTF goldens are **projections**; no `level_prices` | New synthetic fixture; do not rewrite goldens |
| Independent `top_k_core × partner_sets × triggers` | `product()` invents untraded cells; expand also requires `trigger_timeframe` | `stage.mode: explicit_cells` of observed (family × trigger) groups |
| Proposed YAML omits `constants.backtest` | Expand requires SL/TP; default exposure is `allow_all` | Stamp declared backtest knobs; never silent Program B 80/80 |
| `constants.min/max_confluences` = JS1 params | `global_cluster` cells force min=max=len(selected) | Do not stamp JS1 min/max as study clustering |
| NY hour list as `entry_window` | `normalize_entry_window` is `rth_segments` or `clock_range` | Contiguous clock_range or omit |
| Holdout "after dataset loaded" | `run_study` has not loaded the dataset before writes | Load **timestamps** in the existing pre-write gate; launch.py stays schema-only |
| `trigger_direction_consistent` for touch | `_check_touch` is direction-agnostic | Null when the only 1m label is `touch` |
| JS1 15s `approach_side` vs JS2 fade | Fade uses 1m previous **trigger-bar** close | Different objects; never join |
| D1 "clear 2.48 t" vs frequency-not-outcome | JS1 tables may show net ticks as readout | JS3 must not rank or filter on `net_ticks` |

Do not reopen `_check_touch`, the `["long","short"]` loop, `simulate_trades`
sort key, or production goldens from a JS PR.

---

## 1. Value thesis, decisions, non-goals

### 1.1 Four decisions (if a milestone does not change one, do not build it)

| # | Question | Decision it changes | Milestone |
|---|---|---|---|
| D1 | Which zones (width, member count, members) do I actually trade, and which of those groups clear 2.48 t net? | Where to spend attention; which families to stop trading | JS1 |
| D2 | What would the engine have called my entry on the completed bar before the fill, and which of those labels pay? | Whether discretionary entries resemble any researched trigger | JS2 |
| D3 | Does the systematic rule my behaviour implies have edge on history I did not trade? | Keep trading it discretionarily, trade the rule, or drop it | JS3 |
| D4 | Once the rule exists, am I trading it, and is live E tracking backtest E? | Adherence; kill/keep | JS4 |

How each becomes money:

- **D1** is the cut TJ6 cannot make. Token-near is not zone-near. A 2-level
  2-tick cluster is a different product from a 4-level 8-tick cluster. The
  desk already pays 2.48 t/RT (TJ §0.5); a zone family that does not clear
  that is a stop-trading decision, not a chart annotation.
- **D2** tells the desk whether "I fade ONH" is what the engine would have
  called `fade` on the previous completed bar, or a story. If no trigger
  group reaches n ≥ 30, the honest answer is "I do not trade engine
  triggers" and JS3 has nothing to propose.
- **D3** is the only way a journal observation becomes a *testable rule*.
  Selection is by **frequency**, never by net ticks, so the study is not
  fitted to May P&L. Evaluation is on a dataset whose sessions are disjoint
  from the discovery window (`holdout`, refuse-not-filter).
- **D4** closes TJ Q7/Q8 for the proposed cells instead of one hand-picked
  Program B cell. No new page.

### 1.2 Why this is not more complexity

JS1/JS2 add columns to artifacts TJ already writes and one Q3 subsection
each on page 17. JS3 emits a YAML the desk already knows how to run
(`study` CLI / Study Builder). JS4 is a multi-bundle loop over TJ8. No new
Streamlit page, no new store root, no new factor axis, no new trigger
timeframe, no 15s/tick study lane.

Gate A (§4) can stop the series after JS2 with two cheap, still-useful
diagnostics and no schema change.

### 1.3 Goals

1. **JS0 (this PR).** Lock the series. Docs only.
2. **JS1.** Attribute every reconciled, bar-joined trade to the engine
   zone on the previous completed 1m bar. Q3 "Zones" cut. CLI
   `journal zones`.
3. **JS2.** Public `classify_zone_triggers` wrapper; infer triggers on
   the previous completed 1m bar (and a labelled 15s proxy). Q3
   "Inferred trigger" cut. CLI `journal triggers`.
4. **JS3 (Gate A).** Emit `proposal.json` + a schema-1 StudySpec YAML.
   Additive optional `holdout`. Never run the study.
5. **JS4.** `journal match --bundles` + page 17 Q7/Q8 rule-vs-desk table.

### 1.4 Non-goals (entire series)

- A 15s or tick-clock trigger lane (`15s` is not in
  `TRIGGER_TIMEFRAME_CHOICES`). Parked (§9).
- Any edit to `simulate_trades`, `_check_*` **bodies**,
  `detect_confluence_zones` body, candidate sort, or levels math. No
  `LEVEL_ENGINE_VERSION` bump.
- Golden regeneration. JS2's inclusion test uses a **new synthetic
  fixture**. It may *read* golden files only to assert they stayed
  byte-identical; it never rewrites them and it does not reconstruct
  zones from projected `signals.csv` columns.
- Parameter search. `tolerance_ticks`, `min_confluences`, `max_confluences`,
  `top_k_*`, `max_cells`, bracket set are declared constants recorded in
  the artifact. The code never ranks zone definitions or rules by outcome.
- Selecting factor values by net ticks, expectancy, or win rate.
- Auto-run of the proposed study, auto-Admit, auto-promote, Notion writes,
  Study Builder "load proposal" (parked).
- Journal expectancy as a study rank key (TJ §1.4 stands).
- Reusing `study.lineage` for journal provenance (SAF contract).
- Inferring what the trader saw; reconstructing a chart; fetching
  TradesViz note images.
- New USER_GUIDE H2 (no HC allowlist change). Amend the existing
  **Journal** H2 only.
- Desk PII in git.

---

## 2. Architecture

```
TJ6 journal_attribution.parquet ─┐
1m levels frame (built) ─────────┼─► JS1 journal/zones.py
TJ5 15s / 1m bars ───────────────┘     detect_confluence_zones (pure, previous completed 1m bar)
                               +zone_* columns → journal_zones.parquet
                                      │
                                      ▼
                          JS2 journal/triggers.py
                               engine.signals.classify_zone_triggers  (new, public, prepares + delegates)
                               previous completed 1m bar + 15s_proxy
                               +inferred_triggers_* → journal_triggers.parquet
                                      │
                                      ▼
                          JS3 journal/propose.py     CLI: journal propose-study
                               proposal.json + <name>.study.yaml
                               NEVER calls run_study / run_experiment / simulate_trades
                                      │
                       desk fills dataset.path with a pre-discovery file
                       desk runs the study out of band (existing study CLI)
                                      ▼
                          JS4 journal match --bundles … --proposal proposal.json
                               Q7/Q8 rule-vs-desk (TJ8 loop; live_since = proposal date)
```

Package additions: `thesistester/journal/zones.py` (JS1). Later PRs:
`triggers.py`, `propose.py`. CLI remains the additive `journal` subparser
(`thesistester/journal/cli.py`). Store remains
`.thesistester_store/journal/v1/` — not `execution_artifacts/`, not
`results/studies/`. Proposed YAML may be written next to the journal
artifacts; the desk copies it to wherever they run studies.

The only engine edit in the series is JS2's public wrapper. The only
schema edit in the series is JS3's optional `holdout` key.

---

## 3. Locked contracts

### 3.0 Clock, PIT, and parameters (apply to every later JS PR)

These extend TJ §3.0. Do not re-derive them.

1. **`session_date`** = `trading_session_date(local_ts, eth_start="18:00")`
   after converting the fill to `America/New_York`. Same helper TJ1–TJ8 use.
2. **Zone and trigger evaluation bar** = the last **1m** bar whose
   **open + 1 minute ≤ `entry_timestamp`** (half-open). 1m timestamps
   are bar **opens** (`thesistester/data/derive.py`). A fill at exactly
   `09:30:00` therefore uses the `09:29` bar (that bar has closed).
   `close < entry` (strict) would drop equality at the close and is
   wrong. **Do not call** TJ6 `_previous_completed_bar` /
   `_expected_previous_open` for this snapshot: at exact minute stamps
   those helpers return `floor(entry) - 2min` (`09:28` for a `09:30:00`
   fill) so developing-token lookup is one extra bar stale. JS is
   engine-aligned (signal at bar close → fill at next open). Promote a
   shared helper only if it implements `open + duration <= entry` and
   TJ6 is left on its existing helper. The containing minute
   (`open ≤ entry < open+1min`) is never used. A gap or session-open
   fill omits the zone/trigger rather than walking back to a stale
   stamp. Frozen tokens on the previous bar are still valid; developing
   tokens on the containing bar would leak on a 24 s hold.
3. **15s proxy (JS2 only)** = the last completed 15s bar with
   `open + 15s ≤ entry_timestamp` (same half-open rule; 15s timestamps
   are bar opens). Labelled `15s_proxy` because the engine has no 15s
   trigger lane. Never averaged with the 1m inference. Pass that 15s
   frame to the wrapper with `trigger_timeframe="base"` — never `"1min"`
   (that would resample). JS1 `approach_side` (two completed 15s bars)
   is **not** the fade `_approach_side` (previous 1m trigger-bar close).
4. **Never call `compute_all_levels` or `simulate_trades`.** JS1 consumes
   the same already-built 1m levels frame TJ6 consumes (`journal attribute
   --levels`). Missing column → that token is absent from the cluster
   input, not invented.
5. **Declared zone parameters.** `tolerance_ticks`, `min_confluences`,
   `max_confluences`, and the level-column list are a file the desk writes
   **before** looking at outcomes. Defaults = study defaults on
   `DEFAULT_LEVELS_SETTINGS` (do not silently pick a tolerance that
   maximises n). Hash (`zone_params_hash`) is stamped on every derived row.
   Rows of different hashes are never averaged.
6. **Qty / R / fees.** TJ §3.0.5 stands. Declared journal risk remains 10
   ticks unless overridden. AMP fees remain the cost SoT.
7. **Resolution stamp.** Every derived row carries `resolution` and
   `recon_status`. Unreconciled days fail closed unless
   `--allow-unreconciled` (same posture as TJ6).
8. **n ≥ 30** on every report cut. Hidden behind the existing page-17
   toggle. Honesty caption = `REPORT_HONESTY` plus the JS-specific line
   in §3.1 / §3.2.
9. **No RNG** anywhere in JS.
10. **Output dir.** Same `_assert_output_dir` refuse of
    `results/studies/`. Proposed YAML is not a study *run*.

### 3.1 JS1 — Zone attribution (`thesistester/journal/zones.py`)

**Inputs.** TJ6 `journal_attribution.parquet` (or TJ3/TJ5 trades if
attribution columns are already present), the already-built 1m levels
frame, the declared zone-parameter file. Do not look for
`attribution.parquet`.

**Call.** For each trade, take the previous completed 1m row as a
one-row frame and call `detect_confluence_zones`. Clustering is already
per-bar (greedy windows do not span bars), so a one-row call must match
the slice of a full-session call for that `bar_index`. Precomputing the
whole session is allowed only when a test proves that identity.

**Additive columns** (append to the attribution frame; do not drop TJ6
columns):

| Column | Definition |
|---|---|
| `zone_params_hash` | SHA-256 of the canonical parameter payload (level columns + tolerance + min/max) |
| `zone_id` | `session_date:bar_ts:zone_low:zone_high` or null |
| `zone_low`, `zone_high`, `zone_mid` | from the engine row |
| `zone_width_ticks` | `(zone_high − zone_low) / tick_size` |
| `zone_level_count` | engine `level_count` |
| `zone_level_names` | engine `level_names` (`|`-separated, stable token order) |
| `entry_zone_relation` | `inside` / `above_within_tol` / `below_within_tol` / `no_zone` |
| `entry_offset_ticks` | signed `(entry_price − zone_mid) / tick_size`; null when `no_zone` |
| `approach_side` | from the two completed 15s bars before the fill: `from_above` / `from_below` / `inside` / `unknown`. **Not** engine fade `approach_side` (`above`/`below` from previous 1m close) |
| `nearest_zone_distance_ticks` | when `no_zone` and another zone exists on that bar; else null |

**Relation.** `inside` = `zone_low ≤ entry ≤ zone_high`.
`above_within_tol` / `below_within_tol` = outside the zone but within
`tolerance_ticks` of the near edge (the same tolerance that built the
zone — do not introduce a second tolerance). If several zones exist on
the bar, pick the one with the smallest absolute distance from
`zone_mid` to the entry; tie-break by `zone_low` then `level_names`.

**Page 17.** Q3 gains a **Zones** subsection, not a new Q. Cuts: net
ticks by `zone_level_count` (2 / 3 / 4+), by width bucket (≤2 t, 3–4 t,
5+ t), by `entry_zone_relation`, by `zone_level_names` set (sets with
n ≥ 30 only). Every table shows n, resolution, recon_status,
`zone_params_hash`. Caption:

> zone = `detect_confluence_zones` on the 1m bar completed before the
> fill; parameters declared (not searched); journal is not a study cell.

**CLI.** `journal zones --trades … --levels … --zone-params … --output-dir …`
writes `journal_zones.parquet` + `zones.json` (params, hash, n, omitted
counts). Missing later artifacts stay omitted (TJ9 posture).

**Kill criterion (desk, not code).** If fewer than 30 trades land
`inside` or within-tol of any zone, D1 is answered ("I do not trade the
engine's zones") and Gate A fails.

### 3.2 JS2 — Trigger inference

**Engine change (the only one in the series).** Additive public function
in `thesistester/engine/signals.py`:

```python
def classify_zone_triggers(
    df: pd.DataFrame,
    zone: pd.Series,
    trigger_bar_idx: int,
    direction: str,
    *,
    trigger_timeframe: str = "base",
    trigger_params: dict | None = None,
) -> tuple[str, ...]
```

- Calls `_prepare_trigger_dataframe(df, trigger_timeframe)` **first**.
  Then calls the existing `_check_touch`, `_check_reject`, `_check_break`,
  `_check_reclaim`, `_check_fade`, `_check_continuation` with their **live
  signatures** and bookkeeping dummies (`signal_id=0`, `naked_count=0`,
  `naked_req="any"` — checkers do not filter on naked). Returns the
  sorted tuple of trigger names that returned a dict.
- Maps `trigger_bar_idx` the same way `generate_signals` does
  (`base_end_bar_index` → prepared row). Fade/continuation require
  `trigger_bar_idx >= 1` on the prepared frame; the caller must pass
  enough history. A one-row frame is a valid empty result, not a crash.
- Touch/reject/break/reclaim receive `direction` (the trade's side).
  Fade/continuation **must not** be passed `direction` — they emit one
  implied side from `_approach_side`.
- Does **not** call `_check_confirm_3bar` / `3c`. That checker needs a
  3-bar lookback whose later bars can close after the fill. Parked (§9).
- Does **not** apply naked / entry-window / candidate-sort / direction
  collision gates. Those are `generate_signals` jobs. The wrapper is a
  classifier, not a signal factory.
- `generate_signals` does **not** call the wrapper (default-inert).
- No `_check_*` body changes. No new trigger names.
- Journal 1m inference calls the wrapper with `trigger_timeframe="base"`
  on the 1m frame. The 15s proxy uses `"base"` on the 15s frame.

**Acceptance against goldens (JS2, not JS0).** Do **not** reconstruct
zones from checked-in `signals.csv`. Those files are projections:

- `tests/fixtures/golden/fade_enabled_signals.csv` — `signal_id, bar_index, trigger, direction, approach_side, entry_model`
- OTF accepted/rejected CSVs — filter diagnostics, not zone rows

Neither has `zone_low` / `level_prices`. JS2 adds a **new synthetic
fixture** (OHLCV + zone Series + expected label set) and asserts
`expected ⊆ classify_zone_triggers(...)`. Extra labels are allowed
(touch is a subset of reject). Existing golden files stay
byte-identical; the test never writes them. Optional: also assert
inclusion against any family that already serializes a full signal row
— there is none today.

**Journal side** (`thesistester/journal/triggers.py`). For each trade
with a non-null `zone_id`, evaluate on the previous completed 1m bar
(engine-equivalent) and on the previous completed 15s bar
(`15s_proxy`). Additive columns:

| Column | Definition |
|---|---|
| `inferred_triggers_1m` | sorted tuple, possibly empty |
| `inferred_triggers_15s` | sorted tuple; `resolution` stamp `15s_proxy` |
| `trigger_bar_lag_seconds` | `entry_timestamp − (evaluated_1m_bar_open + 1min)` |
| `trigger_direction_consistent` | see below |

Empty tuple is a valid outcome (`none`), counted, not dropped.

**`trigger_direction_consistent`.** `_check_touch` is direction-agnostic
(DA §0). Evaluating the trade's side therefore always "matches" for
touch. Lock:

- `None` when the 1m tuple is empty, or when it contains only `touch`
- `True` when at least one of `reject` / `break` / `reclaim` fired for
  the trade's side, or when `fade` / `continuation` implied direction
  equals the trade direction
- `False` when fade/continuation fired with the opposite implied side
  and no matching reject/break/reclaim

Do not compare JS1 `approach_side` to fade `_approach_side`.

**Page 17.** Q3 gains **Inferred trigger**. Distribution and net ticks
per 1m label; multi-label counted once per label; n ≥ 30. Caption:

> engine would-have-called on the completed bar before the fill; not the
> trader's perception; 15s is a proxy (no engine 15s trigger lane); 3c
> not inferred.

**CLI.** `journal triggers --zones … --bars … --output-dir …`.

### 3.3 JS3 — Proposal (`thesistester/journal/propose.py`)

**Gate.** Do not start JS3 unless Gate A (§4) passed.

**Declared knobs** (keyword-only; recorded in `proposal.json`; not
searched):

| Knob | Default | Role |
|---|---|---|
| `top_k_groups` | 4 | most frequent Gate A `(zone_level_names, inferred 1m trigger)` groups among `inside` ∪ within-tol trades |
| `hour_min_n` | 30 | NY hour must reach this n to enter `entry_window` |
| `max_cells` | 24 | hard refuse if explicit-cell count (groups × 2 directions) would exceed this |
| `confluence_mode` | `global_cluster` | existing mode; do not invent one |
| `trigger_timeframe` | `1min` | factor axis required by expand; never `15s` |
| `proposal_sl_ticks` | 10 | `constants.backtest.stop_loss_ticks` — journal declared risk, **not** engine 8 and **not** Program B 80 |
| `proposal_tp_ticks` | 10 | `constants.backtest.take_profit_ticks` — same posture |
| `proposal_exposure_policy` | `allow_all` | stamped explicitly; never silent |
| `proposal_commission_per_side` | `0.0` | engine default; caption that this is **not** AMP SoT |

**Do not emit independent marginals.** `top_k_core × top_k_partner_sets ×
top_k_triggers` invents cells the desk never traded (core A paired with
a partner set observed only under core C). Selection unit is the Gate A
group:

1. Count `(zone_level_names set, inferred_triggers_1m label)` among
   `inside` ∪ within-tol trades. Ignore empty trigger tuples. Multi-label
   trades count once per label (same as the JS2 table).
2. Keep groups with n ≥ 30 (Gate A universe). Rank by n, tie-break by
   `zone_level_names` then trigger name.
3. Take `top_k_groups`. For each group, `core_level` = the most frequent
   token in that set among those trades (tie: token name);
   `partner_levels` = the remaining tokens in engine `level_names` order
   with the core stripped. Empty partners refuse that group (expand
   requires a non-empty partner-set for `global_cluster`).
4. Emit **`stage.mode: explicit_cells`**: each group × `{long, short}`.
   Factor lists are the closed unions of those cell values (schema still
   needs `factors.*` to contain every explicit-cell token).
5. If explicit-cell count > `max_cells`, refuse (do not trim).

Direction is **always** both sides as separate cells (DA2). Do not drop
a side because the May book is long-biased. Do **not** set
`constants.direction: both` on a single cell — that is the DA
`touch`+`both` collision. Split sides so each expanded run is one-sided.

**Selection is by frequency, never by outcome.** JS1 net-tick tables (D1)
are readout only. `propose-study` must not read `net_ticks` except in a
test that permutes the column and asserts the proposed cells are
unchanged. Do not filter groups by "clears 2.48 t".

**Output A — `proposal.json`** in the journal store:

- `discovery_sessions`: sorted ISO session dates present in the journal
- `source_artifact_hashes`: trades / attribution / zones / triggers
- `zone_params_hash`
- knobs
- selected groups with their n (not a cartesian of independent lists)
- the sentence `selected by frequency, not by outcome`

**Output B — schema-1 StudySpec YAML** (`<name>.study.yaml`) that
**expands**, not merely validates:

- `factors.core_level` / `partner_levels` / `trigger` / `direction` /
  `confluence_mode: [global_cluster]` / `trigger_timeframe: [1min]`
  (expand `_REQUIRED_CELL_AXES` — omitting `trigger_timeframe` invents
  nothing; it **refuses**)
- `stage.mode: explicit_cells` + `stage.cells` as above
- `mode_rules.global_cluster.selected_levels` = union of proposed tokens
- `study.levels` = the JS1 declared zone-parameter settings (same file),
  not a silent `DEFAULT_LEVELS_SETTINGS`
- `constants.tolerance_ticks` = JS1 parameter. Do **not** stamp JS1
  `min_confluences` / `max_confluences` as study clustering — expand
  already forces `min = max = len(core+partners)` for `global_cluster`
- `constants.entry_window` = see clock-range lock below
- `constants.backtest` **required** (expand refuses a missing/empty
  mapping). Stamp at least:

```yaml
backtest:
  stop_loss_ticks: <proposal_sl_ticks>
  take_profit_ticks: <proposal_tp_ticks>
  exposure_policy: <proposal_exposure_policy>
  commission_per_side: <proposal_commission_per_side>
  slippage_ticks: 0.0
  flat_by_session_close: false
  same_bar_opposite_direction: legacy
```

  Do not copy Program B 80/80. Do not omit SL/TP and hope
  `_BACKTEST_DEFAULTS` (8/16) fill them — expand requires the keys on
  the spec.
- `dataset.instrument: MNQ`
- `dataset.path: REPLACE_WITH_PRE_DISCOVERY_DATASET` (valid string;
  launch fails if the file does not exist — fail-closed reminder)
- `report.multiple_testing: warn`
- `description` contains the provenance sentence and the proposal hash
- new optional block:

```yaml
holdout:
  exclude_sessions: [2026-05-11, …]   # ISO dates; the discovery window
  reason: journal_discovery
  proposal_hash: <sha256 of proposal.json>
```

**`entry_window`.** Qualifying NY hours (instrument exchange TZ,
`America/New_York` for MNQ) with n ≥ `hour_min_n` among the selected
groups' trades. Emit only via `normalize_entry_window` shape
(`thesistester/entry_window_policy.py`):

- If qualifying hours form one contiguous half-open range, emit
  `{enabled: true, mode: clock_range, start_time, end_time,
  timezone: America/New_York, rth_segments: []}`
- If none qualify, or the hours are non-contiguous (a single
  `clock_range` would smuggle empty hours), **omit** `entry_window` and
  caption the qualifying hours in `proposal.json` / YAML `description`

Never invent an hour-list key. Do not reuse `study.lineage`.

**Schema change (JS3 only).** Add `holdout` to `_STUDY_KEYS`. Absent /
null → omit (legacy). Present → mapping with exactly those three keys;
`exclude_sessions` is a non-empty list of ISO dates; `reason` is a
non-empty string; `proposal_hash` is a 64-char hex digest. Unknown
subkeys fail. Validator does **no I/O**.

**Launch refuse (JS3 only).** In `run_study` **only**, after
`prepare_study_expansion(..., write_artifacts=False)` and **before**
`write_expansion_artifacts`: if `holdout` is present, load **timestamp**
column(s) from `dataset.path` (same pin rules as expand), compute
session dates via `trading_session_date(..., eth_start="18:00")` in the
instrument exchange TZ, and raise `StudySpecError` on any intersection
with `exclude_sessions`. Do **not** filter bars. When `holdout` is
absent the extra scan does not run (default-inert). Do **not** add this
scan to `study/launch.py` (that module must not import `execute` or load
OHLCV). Preview may show the holdout block; it must not run the study.

**`propose-study` never executes.** AST test: `propose.py` and the CLI
handler contain no `run_study(`, `run_experiment(`, `simulate_trades(`,
`generate_signals(`, `compute_all_levels(`.

### 3.4 JS4 — Rule vs desk (extend TJ8)

`journal match` gains `--bundles` (repeatable hash-verified zips or a
glob) and `--proposal` (path to `proposal.json`). Single-`--bundle`
behaviour is unchanged (TJ8 tests stay green).

- Each bundle is hash-verified as today (`trades.parquet` required;
  `signals.parquet` optional — same `_read_bundle_members` as TJ8).
- `live_since` defaults to the day **after** the last
  `discovery_sessions` date so the ledger is forward of the window that
  proposed the cell.
- Writes one `match_*.parquet` + ledger per `cell_id` under the journal
  store; does not write the promotion registry; does not touch
  `STUDY_INDEX_KEYS`.

Page 17 Q7: one row per proposed cell — match-class counts, backtest E
from the bundle summary, desk realized E on `executed_cell` trades,
adherence, n, resolution, recon_status. Q8 ledger as today. No new page.
No new USER_GUIDE H2.

### 3.5 PII and fixtures

TJ §3.9 stands. JS fixtures are synthetic or redacted. Zone-parameter
examples in `examples/` use public tokens only. Desk exports, AMP PDFs,
and tick files stay out of git.

---

## 4. Milestone table and gates

| Milestone | Intent | Production code |
|---|---|---|
| **JS0** | Plan lock (this PR) | none |
| **JS1** | Zone attribution + Q3 Zones + `journal zones` | `journal/zones.py` |
| **JS2** | `classify_zone_triggers` + inference + Q3 trigger cut | `engine/signals.py` (wrapper only), `journal/triggers.py` |
| **Gate A** | ≥ 1 (zone family × 1m trigger) group with n ≥ 30 in the discovery window | desk readout of JS1/JS2; no code |
| **JS3** | `propose-study` + `holdout` | `journal/propose.py`, `study/schema.py`, `study/execute.py` (refuse in `run_study` only; not `launch.py`) |
| **JS4** | Multi-bundle match + Q7/Q8 rule-vs-desk | `journal/match.py`, `pages/17_Journal.py` |

Do not start JS3 unless Gate A passed. Do not start JS4 unless the desk
has run the proposed study on a pre-discovery dataset. If Gate A fails,
the series **stops**. JS1/JS2 remain useful diagnostics.

JS1 and JS2 are sequential (JS2 needs `zone_id`). JS3 needs both. JS4
needs JS3 + an out-of-band study run.

Quantower / 15s-lane / Study Builder prefill stay parked (§9).

---

## 5. Per-milestone acceptance

### JS0 — Plan lock (this PR)

- [x] Verified facts in §0 with file paths; no invented Q4/Q8 numbers; no
      desk PII. Rev 2 locks in §0.7 vs live engine/schema.
- [x] Four decisions (§1.1), complexity argument (§1.2), non-goals (§1.4),
      Gate A (§4).
- [x] Locked contracts for JS1–JS4 (§3), including bar-open half-open
      clock, wrapper prepare+signatures, explicit_cells (no invented
      cartesian), expand-required YAML keys, holdout pre-write timestamp
      scan.
- [x] Roadmap row + section, docs index, AGENT_GUIDE one-liner, TJ §9
      pointer, TJ §1.4 clarification.
- [x] No `thesistester/` production edits. No goldens touched.
- [x] Docs-only. Golden + USER_GUIDE-structure tests stay green. Do not
      cite a pre-existing red test as a JS0 pass — name it.

### JS1 — Zone attribution

- [x] `detect_confluence_zones` is imported and called; no local cluster
      reimplementation. AST: no `compute_all_levels(`, `simulate_trades(`,
      `generate_signals(`.
- [x] Previous-completed-1m-bar only (`bar_open + 1min <= entry`);
      containing minute unused; gap → `no_zone`. Does not call
      `_expected_previous_open` (exact `09:30:00` fill → `09:29` bar).
- [x] Hand-built 1m fixture: one bar, two tokens 1 tick apart, tolerance
      2 → one zone, `inside` / `above_within_tol` / `no_zone` rows match
      hand calculation. Identity: per-trade one-row call equals the
      `bar_index` slice of a full-session `detect_confluence_zones` call.
- [x] PIT future-shock: appending bars after the fill does not change
      any `zone_*` column (`tests/test_r3_point_in_time.py` shape).
- [x] Parameter hash stamped; two param files produce two hashes; they
      are never averaged in the report.
- [x] Q3 Zones subsection; n ≥ 30 gate; caption locked in §3.1.
- [x] CLI refuses `results/studies/`.
- [x] Same-PR docs: §7 JS1 row.

### JS2 — Trigger inference

- [ ] Wrapper calls `_prepare_trigger_dataframe`; `git diff` on `_check_*`
      bodies is empty; fade/continuation are invoked without `direction`.
- [ ] `generate_signals` does not call the wrapper.
- [ ] New synthetic inclusion fixture (expected ⊆ returned labels).
      Existing golden files byte-identical (legacy + fade / OTF /
      entry-window families). Do not reconstruct zones from projected
      `signals.csv`.
- [ ] 3c not inferred; empty tuple is valid.
- [ ] 1m vs `15s_proxy` never averaged; both stamped; 15s call uses
      `trigger_timeframe="base"`.
- [ ] `trigger_direction_consistent` is null for touch-only.
- [ ] PIT future-shock on inferred columns.
- [ ] Q3 Inferred trigger subsection; caption locked in §3.2.
- [ ] Same-PR docs: §7 JS2 row + `ASSUMPTIONS` (inference ≠ perception).

### JS3 — Proposal

- [ ] Gate A recorded in the PR body (which group, n). If Gate A failed,
      this PR does not exist.
- [ ] Emitted YAML passes `validate_study_spec` **and** `expand_study`
      (has `factors.trigger_timeframe`, non-empty `constants.backtest`
      with SL/TP, `stage.explicit_cells`).
- [ ] Permuting `net_ticks` does not change proposed cells.
- [ ] Independent core × partner × trigger cartesian is not implemented.
- [ ] explicit-cell count > `max_cells` refuses.
- [ ] `holdout` absent → existing study fixtures / examples still
      validate. `holdout` present → overlap with `exclude_sessions`
      raises `StudySpecError` in `run_study` before expansion writes; a
      disjoint dataset proceeds. No bar is dropped. `launch.py` has no
      dataset scan.
- [ ] `entry_window` is `normalize_entry_window` shape or omitted.
- [ ] AST: `propose.py` does not call run/simulate/generate.
- [ ] Same-PR docs: `STUDY_RUNNER.md` (`holdout`); §7 JS3 row.

### JS4 — Rule vs desk

- [ ] Single-`--bundle` TJ8 tests unchanged.
- [ ] `--bundles` + `--proposal` writes one match/ledger per cell;
      `live_since` after discovery window.
- [ ] No write to the promotion registry; no `STUDY_INDEX_KEYS` change.
- [ ] Page 17 Q7/Q8 table; no new H2; no HC allowlist edit.
- [ ] Same-PR docs: §7 JS4 row.

---

## 6. Regression-safety envelope (every JS PR)

| Rule (`ENGINEERING_PROPOSAL.md` §4) | How JS satisfies it |
|---|---|
| Additive-only engine | JS2 adds one unused-by-default function that prepares the trigger frame then delegates. `_check_*` / `detect_confluence_zones` / `simulate_trades` bodies untouched. No positional signature changes |
| Golden-master | No golden regeneration. JS2 inclusion uses a new synthetic fixture. Existing goldens stay byte-identical. JS0/JS1/JS3/JS4 do not touch engine outputs |
| Opt-in | Journal CLIs are new entry points. `holdout` absent = today's `run_study`. Wrapper unused by `generate_signals` |
| Schema-versioned persistence | Still `journal/v1`; new files (`journal_zones.parquet`, `journal_triggers.parquet`, `proposal.json`) are optional readers (TJ9 omit-if-missing) |
| Bundle hash neutrality | Journal never writes research bundles. Proposed YAML is not a run |
| PIT | Previous completed bar only (`bar_open + duration <= entry`); future-shock tests on JS1/JS2 |
| Determinism | No RNG. Frequency sort is token-name stable on ties |
| Same-PR docs | §7 table |
| `st.session_state` | JS1/JS2/JS4 may add keys on page 17 only; record them in `ARCHITECTURE.md`. No classic research keys |
| PII | Desk exports stay outside git |
| Honesty | Every new table carries n, resolution, recon, params hash, and the §3 caption |

PR body of every later JS PR includes a **Regression safety** paragraph
and the §4.2 checklist (unit tests, goldens preserved, no new RNG, docs
in the same PR, CI green).

---

## 7. Docs each later PR must touch

| PR | Docs |
|---|---|
| JS0 | This file; `ENGINEERING_ROADMAP.md` status + section; `docs/README.md`; `AGENT_GUIDE.md`; TJ §1.4 + §9; DA §8 one-liner |
| JS1 | `ARCHITECTURE.md` (page-17 keys if any); `METRICS_GLOSSARY.md` (`zone_id`, `zone_width_ticks`, `entry_zone_relation`, `zone_params_hash`); `ASSUMPTIONS` (declared params; previous-bar snapshot vs TJ6 mixed lookup); USER_GUIDE Journal H2 (Zones subsection — **same H2 title**) |
| JS2 | `METRICS_GLOSSARY.md` (`inferred_triggers_1m`, `inferred_triggers_15s`, `trigger_bar_lag_seconds`); `ASSUMPTIONS` (inference ≠ perception; 15s proxy; 3c omitted); `ARCHITECTURE.md` (`classify_zone_triggers`); USER_GUIDE Journal H2 |
| JS3 | `STUDY_RUNNER.md` (`holdout` refuse-not-filter in `run_study` only); `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` one-liner if the schema-key table lives there; `ASSUMPTIONS` (frequency not outcome; discovery window; explicit_cells; declared backtest locks, not Program B 80/80); USER_GUIDE Journal H2 (`propose-study` does not run) |
| JS4 | `ASSUMPTIONS` (rule vs desk; `live_since` after discovery); `ARCHITECTURE.md` (multi-bundle); USER_GUIDE Journal H2 |

Do **not** add a USER_GUIDE H2. Do **not** touch HC §6.1 / RQ §7.1.4 /
`_USER_GUIDE_SECTIONS` / `REQUIRED_USER_GUIDE_H2S` unless a later PR
actually changes an H2 title (it must not).

There is no `HONESTY_FRAMING.md` — do not create one.

---

## 8. Desk workflow (not repo tasks; the feature is worthless without them)

1. **Before JS3.** Load Tick-Last for the discovery sessions and rerun
   `journal counterfactual` at `resolution=tick`. Compare the Q4 bracket
   table to the 15s run. That readout (redacted) decides whether the
   parked 15s/tick study lane is worth a future series. It is **not** a
   JS milestone.
2. **Before JS1.** Write the zone-parameter file (level columns +
   tolerance + min/max) **once**, before looking at zone P&L.
3. **After JS2.** Read Gate A. If no (zone family × trigger) group has
   n ≥ 30, stop. Do not invent a proposal from thin slices.
4. **After JS3.** Obtain an MNQ 1m (or `15s_primary_derive_1m`) dataset
   whose sessions are disjoint from `holdout.exclude_sessions`. Replace
   `REPLACE_WITH_PRE_DISCOVERY_DATASET`. Run the study as any other
   study. Do not Admit from the proposal YAML.
5. **After that run.** `journal match --bundles … --proposal proposal.json`.
   From the proposal date on, the ledger is forward-only.
6. Keep exporting executions + AMP weekly (TJ §8). A second discovery
   window (June+) is the honest replication of JS1/JS2 cuts; it is not
   this series.

---

## 9. Parked / follow-ups

- 15s / tick-clock **trigger** lane (`15s` added to
  `TRIGGER_TIMEFRAME_CHOICES` + `generate_signals` on a 15s clock).
  Decided by the §8 Q4 tick-vs-15s readout **and** by whether JS4
  `product_mismatch` dominates. Not JS.
- `3c` / `_check_confirm_3bar` inference (multi-bar; PIT-risky).
- Study Builder "load proposal" button.
- Entry-time jitter null (TJ §9) as a second TJ7 null.
- Program C conditional locks sourced from JS1 zone families — after
  Run 2 readout **and** after Gate A.
- Journal as an R21 portfolio `setup_id`.
- Auto-Admit / Notion writes (anti-roadmap).
- Re-costing Program B cells onto the AMP $1.24 RT schedule (TJ §9).

---

## 10. Agent prompt — JS1 (next PR)

```text
You are implementing JS1 from docs/JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md
in the ThesisTester repo. Read §0, §1, §2, §3.0, §3.1, §5 JS1, §6, and §7
JS1 in full before writing code. Also read docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md
§3.0 and §3.6 (TJ6) and thesistester/engine/confluence.py.

Hard rules:
- Regression-safe per docs/ENGINEERING_PROPOSAL.md §4: additive,
  keyword-only, default = legacy. Do not edit simulate_trades,
  _check_touch (or any _check_*), detect_confluence_zones body, the
  ["long","short"] loop, or any golden fixture.
- Scope is JS1 only (zone attribution on the previous completed 1m bar
  + Q3 Zones + CLI `journal zones`). If you need trigger inference,
  classify_zone_triggers, holdout, propose-study, or multi-bundle match,
  stop and say so.
- Call detect_confluence_zones; do not reimplement clustering. Never
  call compute_all_levels or simulate_trades. Evaluate on the last 1m
  bar with bar_open + 1min <= entry_timestamp (timestamps are bar
  opens). Never the containing minute. Fill at exactly 09:30:00 uses
  the 09:29 bar. Do not reuse TJ6 _expected_previous_open (that helper
  returns 09:28 at an exact 09:30:00 fill).
- Zone parameters are a declared file, hashed, not searched.
- Do not commit desk PII. Synthetic fixtures only.
- Run `python3 -m pytest -q` before and after; both green. Do not skip a
  failing test as “pre-existing” unless it is red on this PR’s `main`
  and you name the node. Run the golden tests and paste their output in
  the PR body.
- Update the JS1-listed docs in the same PR. Do not add a USER_GUIDE H2
  and do not touch HC allowlists. Add a "Regression safety" paragraph
  to the PR body.
- Series code is JS.
```
