# Journal → Study Implementation Plan (JS)

**Series code:** JS
**Status:** JS0 plan lock (this PR). No production code.
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
reads one declared bundle's `signals.csv` / `trades.csv` and classifies
time/price proximity plus hold/risk compatibility. It does not ask what
trigger the engine would have called at the fill.

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
`_check_fade`, `_check_continuation`, `_check_confirm_3bar`. They evaluate
on bar close and return a signal dict or `None`.
`VALID_TRIGGERS = {touch, reject, break, reclaim, 3c, fade, continuation}`.
There is no public read-only entry point. **JS2 adds one wrapper** that
delegates to the existing `_check_*` functions. It does not edit their
bodies.

`TRIGGER_TIMEFRAME_CHOICES = (base, 1min, 5min, 15min)` (`thesistester/setup.py`).
`15s` is not a trigger timeframe. `ingestion_mode=15s_primary_derive_1m`
(`thesistester/data/derive.py`) derives a 1m parent and uses 15s for
intrabar resolution (R12). **The engine has no 15s-clock trigger lane.**
Building one is parked (§9), not JS.

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

`run_study` (`study/execute.py`) already refuses **before** writing
expansion artifacts (`confirm_above_runs`, identity mismatch). The JS3
session-overlap refuse lives in that same gate window.

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
- Golden regeneration. JS2's inclusion test *reads* golden `signals.csv`;
  it never rewrites it.
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
TJ6 attribution.parquet ─┐
1m levels frame (built) ─┼─► JS1 journal/zones.py
TJ5 15s / 1m bars       ─┘     detect_confluence_zones (pure, previous completed 1m bar)
                               +zone_* columns → journal_zones.parquet
                                      │
                                      ▼
                          JS2 journal/triggers.py
                               engine.signals.classify_zone_triggers  (new, public, delegates)
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

Package additions (later PRs, not this one): `thesistester/journal/zones.py`,
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
2. **Zone and trigger evaluation bar** = the last **1m** bar whose close is
   **strictly before** `entry_timestamp`. The containing minute is never
   used. A gap or session-open fill omits the zone/trigger rather than
   walking back to a stale stamp. This is stricter than TJ6 (TJ6 may use
   the containing minute for *frozen* tokens). JS uses one snapshot so
   developing and frozen tokens are contemporaneous. Frozen tokens on the
   previous bar are still valid; developing tokens on the containing bar
   would leak on a 24 s hold.
3. **15s proxy (JS2 only)** = the last completed 15s bar whose close is
   strictly before the fill. Labelled `15s_proxy` because the engine has
   no 15s trigger lane. Never averaged with the 1m inference.
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
frame, the declared zone-parameter file.

**Call.** For each trade, take the previous completed 1m row as a
one-row frame and call `detect_confluence_zones`. Do not precompute
zones for the whole session inside journal code unless a test proves
identity with the per-trade call (the function is already per-bar).

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
| `approach_side` | from the two completed 15s bars before the fill: `from_above` / `from_below` / `inside` / `unknown` |
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

- Calls the existing `_check_touch`, `_check_reject`, `_check_break`,
  `_check_reclaim`, `_check_fade`, `_check_continuation` with bookkeeping
  dummies (`signal_id=0`, `naked_count=0`, `naked_req` that does not
  filter). Returns the sorted tuple of trigger names that returned a
  dict.
- Does **not** call `_check_confirm_3bar` / `3c`. That checker needs a
  3-bar lookback whose later bars can close after the fill. Parked (§9).
- Does **not** apply naked / entry-window / candidate-sort / direction
  collision gates. Those are `generate_signals` jobs. The wrapper is a
  classifier, not a signal factory.
- `generate_signals` does **not** call the wrapper (default-inert).
- No `_check_*` body changes. No new trigger names.

**Acceptance against goldens (JS2, not JS0).** For every row of every
checked-in golden `signals.csv` whose `trigger` is in
`{touch, reject, break, reclaim, fade, continuation}`, reconstruct the
zone Series from that row's `zone_low` / `zone_high` / `level_names` /
`level_prices` and assert
`row.trigger in classify_zone_triggers(...)`.
This is an **inclusion** test. Extra labels are allowed (touch is a
subset of reject). Golden files stay byte-identical; the test never
writes them.

**Journal side** (`thesistester/journal/triggers.py`). For each trade
with a non-null `zone_id`, evaluate on the previous completed 1m bar
(engine-equivalent) and on the previous completed 15s bar
(`15s_proxy`). Additive columns:

| Column | Definition |
|---|---|
| `inferred_triggers_1m` | sorted tuple, possibly empty |
| `inferred_triggers_15s` | sorted tuple; `resolution` stamp `15s_proxy` |
| `trigger_bar_lag_seconds` | `entry_timestamp − evaluated_bar_close` (1m) |
| `trigger_direction_consistent` | True iff at least one 1m label's implied direction equals the trade direction (`fade`/`continuation` have an implied approach; touch/reject/break/reclaim use the `direction` argument that matches the trade) |

Empty tuple is a valid outcome (`none`), counted, not dropped.

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
| `top_k_core` | 2 | most frequent tokens among `inside` ∪ within-tol trades |
| `top_k_partner_sets` | 2 | most frequent partner sets (zone members minus core) |
| `top_k_triggers` | 2 | most frequent 1m inferred triggers (ignore `none`) |
| `hour_min_n` | 30 | NY hour must reach this n to enter `entry_window` |
| `max_cells` | 24 | hard refuse if cartesian expansion would exceed this |
| `confluence_mode` | `global_cluster` | existing mode; do not invent one |
| `trigger_timeframe` | `1min` | engine-equivalent; never `15s` |

Direction is **always** `[long, short]` (DA2). Do not drop a side because
the May book is long-biased.

**Selection is by frequency, never by outcome.** A test must assert that
permuting `net_ticks` does not change the proposed factors.

Default cartesian: 2 cores × 2 partner sets × 2 triggers × 2 directions
= 16 cells. If the desk raises a `top_k` and cartesian > `max_cells`,
`propose-study` refuses (does not silently drop cells). Dropping order
is not implemented because refuse-not-trim is the point.

**Output A — `proposal.json`** in the journal store:

- `discovery_sessions`: sorted ISO session dates present in the journal
- `source_artifact_hashes`: trades / attribution / zones / triggers
- `zone_params_hash`
- knobs
- selected factor values with their n
- the sentence `selected by frequency, not by outcome`

**Output B — schema-1 StudySpec YAML** (`<name>.study.yaml`):

- `factors.core_level` / `partner_levels` / `trigger` / `direction` as above
- `factors.confluence_mode: [global_cluster]` + required `mode_rules`
  (`global_cluster.selected_levels` = union of proposed tokens)
- `constants.tolerance_ticks` / `min_confluences` / `max_confluences` =
  JS1 parameters
- `constants.entry_window` = NY hours with n ≥ `hour_min_n`, or omitted
  if none qualify (caption that fact)
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

**Schema change (JS3 only).** Add `holdout` to `_STUDY_KEYS`. Absent /
null → omit (legacy). Present → mapping with exactly those three keys;
`exclude_sessions` is a non-empty list of ISO dates; `reason` is a
non-empty string; `proposal_hash` is a 64-char hex digest. Unknown
subkeys fail. Validator does **no I/O**.

**Launch refuse (JS3 only).** In `run_study` / `launch`, **after** the
dataset is loaded and **before** expansion artifacts are written: if
`holdout` is present, compute the dataset's session dates via
`trading_session_date` and raise `StudySpecError` on any intersection
with `exclude_sessions`. Do **not** filter bars. When `holdout` is
absent the extra scan does not run (default-inert). Preview may show
the holdout block; it must not run the study.

**`propose-study` never executes.** AST test: `propose.py` and the CLI
handler contain no `run_study(`, `run_experiment(`, `simulate_trades(`,
`generate_signals(`, `compute_all_levels(`.

### 3.4 JS4 — Rule vs desk (extend TJ8)

`journal match` gains `--bundles` (repeatable hash-verified zips or a
glob) and `--proposal` (path to `proposal.json`). Single-`--bundle`
behaviour is unchanged (TJ8 tests stay green).

- Each bundle is hash-verified as today.
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
| **JS3** | `propose-study` + `holdout` + launch refuse | `journal/propose.py`, `study/schema.py`, `study/execute.py` / `launch.py` (refuse only) |
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
      desk PII.
- [x] Four decisions (§1.1), complexity argument (§1.2), non-goals (§1.4),
      Gate A (§4).
- [x] Locked contracts for JS1–JS4 (§3).
- [x] Roadmap row + section, docs index, AGENT_GUIDE one-liner, TJ §9
      pointer, TJ §1.4 clarification.
- [x] No `thesistester/` production edits. No goldens touched.
- [x] Docs-only. Golden + USER_GUIDE-structure tests stay green. Do not
      cite a pre-existing red test as a JS0 pass — name it.

### JS1 — Zone attribution

- [ ] `detect_confluence_zones` is imported and called; no local cluster
      reimplementation. AST: no `compute_all_levels(`, `simulate_trades(`,
      `generate_signals(`.
- [ ] Previous-completed-1m-bar only; containing minute unused; gap →
      `no_zone`.
- [ ] Hand-built 1m fixture: one bar, two tokens 1 tick apart, tolerance
      2 → one zone, `inside` / `above_within_tol` / `no_zone` rows match
      hand calculation. Identity: per-trade call equals calling the
      engine function on that one-row frame.
- [ ] PIT future-shock: appending bars after the fill does not change
      any `zone_*` column (`tests/test_r3_point_in_time.py` shape).
- [ ] Parameter hash stamped; two param files produce two hashes; they
      are never averaged in the report.
- [ ] Q3 Zones subsection; n ≥ 30 gate; caption locked in §3.1.
- [ ] CLI refuses `results/studies/`.
- [ ] Same-PR docs: §7 JS1 row.

### JS2 — Trigger inference

- [ ] `classify_zone_triggers` public; `_check_*` bodies unchanged
      (`git diff` on those functions is empty).
- [ ] `generate_signals` does not call the wrapper.
- [ ] Golden inclusion test on all checked-in `signals.csv` rows whose
      trigger is in the six-name set. Golden files byte-identical
      (legacy golden + fade / OTF / entry-window families).
- [ ] 3c not inferred; empty tuple is valid.
- [ ] 1m vs `15s_proxy` never averaged; both stamped.
- [ ] PIT future-shock on inferred columns.
- [ ] Q3 Inferred trigger subsection; caption locked in §3.2.
- [ ] Same-PR docs: §7 JS2 row + `ASSUMPTIONS` (inference ≠ perception).

### JS3 — Proposal

- [ ] Gate A recorded in the PR body (which group, n). If Gate A failed,
      this PR does not exist.
- [ ] Emitted YAML passes `validate_study_spec`.
- [ ] Permuting `net_ticks` does not change proposed factors.
- [ ] cartesian > `max_cells` refuses.
- [ ] `holdout` absent → existing study fixtures / examples still
      validate. `holdout` present → overlap with `exclude_sessions`
      raises `StudySpecError` before expansion writes; a disjoint
      dataset proceeds. No bar is dropped.
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
| Additive-only engine | JS2 adds one unused-by-default function. `_check_*` / `detect_confluence_zones` / `simulate_trades` bodies untouched. No positional signature changes |
| Golden-master | No golden regeneration. JS2 inclusion test reads goldens. JS0/JS1/JS3/JS4 do not touch engine outputs |
| Opt-in | Journal CLIs are new entry points. `holdout` absent = today's `run_study`. Wrapper unused by `generate_signals` |
| Schema-versioned persistence | Still `journal/v1`; new files (`journal_zones.parquet`, `journal_triggers.parquet`, `proposal.json`) are optional readers (TJ9 omit-if-missing) |
| Bundle hash neutrality | Journal never writes research bundles. Proposed YAML is not a run |
| PIT | Previous completed bar only; future-shock tests on JS1/JS2 |
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
| JS3 | `STUDY_RUNNER.md` (`holdout` refuse-not-filter); `STUDY_RUNNER_IMPLEMENTATION_PLAN.md` one-liner if the schema-key table lives there; `ASSUMPTIONS` (frequency not outcome; discovery window); USER_GUIDE Journal H2 (`propose-study` does not run) |
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
  bar whose close is strictly before the fill; never the containing
  minute.
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
