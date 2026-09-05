# APOC Quantower Parity — Investigation and Implementation Plan

**Document type:** Focused investigation plan
**Date:** 2026-09-05
**Status:** **AP0 locked — evidence collection pending.** No engine behavior has changed.
**Series code:** **AP** (A-Period POC)
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including the
golden-master operational specification (§4.1) and per-PR checklist (§4.2).

**Does not reopen:** R9–R22 milestone text; TV `pd*` / `pw*` / `pm*` identity
(`LEVEL_ENGINE_VERSION` 11); rolling-POC VAP; WMV `dVWAP*` math; TPO single
prints; 15s-primary / derived-1m product clock; Help-corpus *path* moves;
`simulate_trades` / R12 / 3c / touch.

**Amends:** TV parked “APOC VAP rewrite” only — this file is the living SoT for
A-period POC allocation investigation. Rolling-POC VAP remains parked on the
TV series. LC locked contract #3 is **not** amended in AP0; AP2 must add the
TV-style one-line pointer if and when APOC allocation under the same names
changes.

**Related living docs (amend only the sentence that is newly true, in the PR that makes it true):**
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/POINT_IN_TIME_GUARANTEES.md`,
`docs/METRICS_GLOSSARY.md`, `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`,
`docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md`,
`docs/LEVEL_CATALOG_CONTRACT_IMPLEMENTATION_PLAN.md` (AP2 only, contract #3).

---

## 1. Problem statement and current evidence

The desk reports that, for MNQ RTH 2026-09-04, Quantower displayed an A-period
POC of `29625.00`, while ThesisTester produced `29611.75` from the same
Quantower History Exporter 15-second source after UTC → `America/New_York`
normalization. The reported A-period is `[09:30, 10:00)` New York time.

The repository independently confirms the ThesisTester **production object**:

- `APOC` is computed in `thesistester/levels/apoc.py` from whatever OHLCV
  frame the caller passes. The product path is
  `ingestion_mode: 15s_primary_derive_1m`; APOC then runs on the **derived
  1-minute** bars, not on the 15-second source rows.
- Each bar’s entire volume is assigned to `(high + low + close) / 3`, then
  tick-binned with `instrument.tick_size` (MNQ `0.25`) via `_compute_profile`.
  There is no `aggregation_ticks` multiplier on APOC today.
- ETH is excluded. APOC appears from the first RTH row at or after A-period
  end. `pAPOC` is the previous **observed** RTH session’s APOC.
- `compute_apoc_levels(..., enabled=False)` is a true no-op. Direct
  `compute_all_levels` defaults `apoc_enabled=False`. Product
  `DEFAULT_LEVELS_SETTINGS["apoc_enabled"]` is `True` (Levels page, headless
  API, Program B Wave 7).

The function does **not** require 1-minute bars. Feeding raw 15-second rows
into `compute_apoc_levels` is a different object than the product 1-minute
path. An ad-hoc UTC→NY conversion that `tz_localize`s naive UTC stamps as
`America/New_York` is also a different object than the loader’s
`source_timezone: UTC` then `tz_convert` path.

The repository does **not** contain the 2026-09-04 MNQ export, a Quantower APOC
reference file, or a recorded Quantower indicator/template configuration.
Therefore the observation proves a discrepancy, but does not yet prove that
Quantower uses uniform bar-range volume allocation, TPO allocation, tick
Last×Volume, a coarser row size, or a different bar aggregation.

Clues that must be recorded, not assumed:

- `29611.75` sits on MNQ’s 0.25 grid and **not** on a 1.00 grid.
- `29625.00` sits on both. That is compatible with a 1-tick POC that happens
  to land on a round number, **or** with a 4-tick / 1.00 Quantower row size.
- The 13.25-point gap is 53 MNQ ticks. TV already showed that allocation and
  row size are independent knobs; one matching bar-range reconstruction of
  one session is not sufficient evidence to label that method
  Quantower-compatible.

## 2. Locked scope and invariants

### In scope

- Determine the calculation object used by the Quantower A-period POC on
  reproducible MNQ fixtures, including Quantower’s indicator class
  (TPO vs volume profile vs custom period POC), bar aggregation, and row size.
- Select a source/allocation method only after comparative evidence.
- If evidence supports a change, introduce a versioned, explicit **opt-in**
  APOC source and preserve point-in-time semantics. Production default
  emission stays typical-price until a later, explicit identity cutover.
- Record enough provenance that future Program B results identify the APOC
  object used.

### Out of scope

- `pd*` / `pw*` / `pm*` tick VAP, including its TV-series identity contract.
- Rolling POC, VA, VWAP, opening range, session marks, TPO single prints,
  signals, confluence, fills, or simulation.
- Replacing the 15-second-primary / derived-1-minute product clock.
- Retrospective mutation, deletion, or reinterpretation of Program B results.
- Claiming agreement with Quantower from an unverified proxy.
- Changing product or library defaults so that `apoc_enabled=True` silently
  emits a new APOC object under the same column names.

### Invariants

1. The A-period is RTH-only and half-open: `[RTH open, RTH open + 30 minutes)`.
   Bar timestamps are **bar-open**. On derived 1-minute bars the last included
   bar is `09:59`; on 15-second bars it is `09:59:45`. The `10:00` bar is the
   first availability row, not an A-period input. Whether Quantower includes a
   `10:00` print is an evidence item, not a license to change this window.
2. `APOC` remains unavailable before the first RTH row at or after the
   A-period end and remains `NaN` on ETH rows.
3. `pAPOC` remains a frozen value visible from the next RTH open. The
   immediately-prior-observed-session rule remains until Quantower evidence
   specifically disproves it for holidays/gaps.
4. Required profile inputs that are missing, malformed, off-grid under the
   selected policy, or incomplete under the selected source contract produce
   `NaN`; they never fall back to typical-price APOC while bearing a new source
   identity.
5. All allocation, binning, rounding, and POC tie rules are deterministic and
   explicitly tested.
6. Library `compute_apoc_levels` / `compute_all_levels` keep
   `apoc_enabled=False` by default. Product `apoc_enabled=True` does **not**
   authorize a math change. New behavior requires an explicit source key
   whose default reproduces today’s typical-price APOC.
7. Window membership uses tz-aware comparison against `exchange_tz` RTH open
   (`America/New_York` for MNQ). Naive UTC stamps are localized as UTC then
   converted; they are never localized as New York.

## 3. Evidence protocol (required before production math)

### 3.1 Desk evidence package

Keep proprietary inputs outside git. Each package must include:

| Item | Required record |
|---|---|
| Bar source | Original 15-second HE export, SHA-256, row count, instrument/contract, `source_timezone` (must be UTC for the named HE file), exporter profile, and whether empty 15-second slots were built |
| Ingest path | Exact ThesisTester path used to obtain `29611.75`: `format_profile`, `source_timezone: UTC`, `tz_convert` (not localize-as-NY), `ingestion_mode: 15s_primary_derive_1m`, instrument `MNQ`. Record the derived-1m A-period row count |
| Quantower oracle | A CSV or manually transcribed table of date → APOC/pAPOC, plus a screenshot/export of the exact indicator **class** (TPO POC vs volume-profile POC vs custom period POC) and its settings |
| Chart context | Data provider, chart aggregation (tick / 15s / 1m), session template, exchange timezone, bar-build mode (open time vs close time), **profile row size in ticks and points**, and POC/tie setting if exposed |
| Tick source, when used | Tick–Tick–Last export SHA-256, row count, source timezone, and relationship to the chart data feed |
| Audit output | The selected A-period bars/ticks, local timestamps, source rows, candidate histogram, target value, error in points, and error in MNQ ticks **and** in Quantower row-size units |

The reference table must include at least ten independent sessions: the named
2026-09-04 case, narrow and wide A-period ranges, sparse/trade-only 15-second
data, a candidate tie, ordinary days, and a DST-adjacent session where
available. The data provider, contract and session template must remain fixed
within the comparison set.

Before any candidate is scored against Quantower, AP1 must **reproduce
`29611.75`** from the named export on the production 15s→1m typical path. If
that reconstruction fails, the desk number is not yet an engine-allocation
discrepancy; stop and audit ingest, timezone, and bar frequency. Do not
discriminate allocation candidates against an unreproduced baseline.

### 3.2 Controlled candidate comparison

AP1 compares candidates without changing production output. Allocation and
bar/tick timeframe are independent axes. Every bar candidate is run on both
the derived 1-minute A-period bars and the raw 15-second A-period bars.
Row size is a third axis: instrument tick (`0.25`) and the Quantower screenshot
row size (if different).

| Candidate | Allocation | Purpose |
|---|---|---|
| `typical_mvp_v1` | Full bar volume at `(H+L+C)/3` | Reproduce current engine on 1m; test 15s typical as a confounder |
| `bar_range_uniform_volume_v1` | Each bar's volume divided equally across all inclusive tick bins from low to high | Test the desk hypothesis |
| `bar_range_tpo_v1` | One time unit per touched inclusive tick bin per bar; bar volume ignored | Distinguish TPO-style behavior |
| `tick_last_volume_v1` | Quantower Tick–Tick–Last price × volume inside the A-period | Test true VAP when matching tick data exists |

`typical_mvp_v1` on derived 1-minute bars must match `compute_apoc_levels`
on the same frame (synthetic CI fixture, exact equality). That is the
harness integrity check; it does not require desk data.

Before candidates run, AP1 must lock:

- Whether range endpoints are rounded, rejected, or snapped to the instrument
  grid; the policy must reject unsound input rather than silently alter it.
- Inclusive range-bin semantics, inverted H/L handling, and zero-range
  behavior (a `high == low` bar places its whole volume / one TPO on that
  price).
- Volume conservation tolerance for volume-based candidates.
- Exact POC tie policy. ThesisTester currently resolves equal bin volume to the
  lowest price; Quantower behavior must be observed rather than assumed.
- The minimum coverage/completeness requirement for sparse bar and tick data.
- The Quantower object class from the screenshot. Do not score a TPO
  candidate as a volume-profile hit, or the reverse.

### 3.3 Source-selection gate

Holdout is mandatory. Before inspecting **holdout or aggregate** candidate
errors, AP1 must write:

1. The named 2026-09-04 session plus the development-session IDs.
2. The holdout-session IDs (at least three of the ten).
3. The numeric threshold: a candidate must match the Quantower oracle within
   **± one Quantower profile row** on the named session, and must meet the
   predeclared holdout score (median absolute error and max error, in row
   units). If the screenshot row size is 1 tick, that named-session band is
   `±0.25`. If it is 4 ticks, the band is `±1.00`. Do not hardcode `±0.25`
   when the oracle grid is coarser.
4. Which Quantower object class is being matched.

Failure has a defined outcome:

- No candidate meets the threshold: do not cut over; retain documented
  typical-price APOC and open a bounded data/settings investigation.
- Only tick Last×Volume meets the threshold: select tick VAP as the **opt-in**
  source; do not present a bar proxy as Quantower-compatible.
- A bar method meets the threshold but tick evidence is absent or divergent:
  ship it only as a documented bar proxy, not a claim of tick equivalence.
- A method matches only on 15-second bars, or only at a non-production row
  size: record that as a different object. It may become an opt-in source; it
  must not be described as a drop-in replacement of the current 1-minute
  typical APOC without saying so in honesty docs.

Matching the named session alone never selects a source.

## 4. Implementation architecture after selection

AP2 implements the AP1-selected source as an **additive, default-preserving
option**. It does not replace the emitted object for existing callers.

1. Add a keyword-only `apoc_profile_source` whose default is `typical_mvp_v1`.
   Direct library defaults remain legacy-compatible and `apoc_enabled=False`
   remains a true no-op. Product `DEFAULT_LEVELS_SETTINGS` keeps today’s
   typical-price APOC (explicit `typical_mvp_v1` once the key exists).
   `_normalize_levels_settings` must `setdefault` the new key to
   `typical_mvp_v1` so old snapshots do not change behavior.
2. For an OHLC-derived source, calculate only from the selected session's
   A-period rows using tz-aware comparison against exchange-local RTH open.
   The production clock remains derived 1-minute unless AP1 selected a 15s
   object and the source value says so.
3. For a tick source, build an A-period profile table keyed by RTH session date
   from the existing Quantower Tick–Tick–Last loader. It must filter ticks to
   the A-period in exchange time; the full-session `PriorProfileTable` is not
   a substitute. Point-in-time: ticks at or after A-period end cannot change
   earlier `APOC` / `pAPOC` rows.
4. Put `apoc_profile_source`, algorithm version, allocation/row-size settings,
   and input source identity (including `"none"` when ticks are unused)
   **inside** the levels settings dict hashed by
   `compute_levels_settings_hash`. A side-channel hash is a cache-collision
   defect (TV3 precedent). Adding the key with typical default does **not**
   require a `LEVEL_ENGINE_VERSION` bump. Changing the object emitted under
   `APOC` / `pAPOC` for product defaults **does**, and is **out of AP2**.
5. Do not silently change the meaning of persisted APOC results. A later
   product-default cutover is a dedicated AP PR: desk decision, AP1 gate
   green, `LEVEL_ENGINE_VERSION` bump, LC contract #3 amendment, honesty docs,
   and Program B YAML already pinned by AP3.

## 5. Fully scoped PR series

### AP0 — plan lock (this PR)

| Field | Scope |
|---|---|
| Title | `AP0: lock Quantower APOC investigation plan` |
| Files | This plan; index pointers in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, and `docs/AGENT_GUIDE.md`; one-line TV parked-item pointer |
| Behavior | Documentation only; no level calculation, cache, default, study, or UI change |
| Acceptance | Scope, evidence protocol, candidate gate, AP1–AP3 boundaries, product-vs-library defaults, and regression rules are explicit |
| Forbidden | Engine edits, fixture-data commits, result reruns, golden regeneration |

### AP1 — comparator and evidence discriminator

| Field | Scope |
|---|---|
| Title | `AP1: add APOC profile comparison harness` |
| Files | New pure candidate module (e.g. `thesistester/levels/apoc_candidates.py`); `tests/test_apoc_candidates.py`; tiny synthetic fixtures; optional env-gated desk-oracle test; this plan and roadmap status |
| Behavior | Compute candidate profiles and auditable histograms without modifying `compute_apoc_levels` output |
| Acceptance | Equality of `typical_mvp_v1` (1m) vs `compute_apoc_levels`; hand-computed allocation, conservation, bin-edge, zero-range, inverted H/L, tie, timezone, sparse-input, 1m-vs-15s isolation, and candidate-isolation tests; optional desk test records per-session error vs the written holdout gate |
| Forbidden | Importing the candidate module from `apoc.py`, `all.py`, `api.py`, `defaults.py`, or `thesistester.levels.__all__`; edits to `profile.py` helpers, production `apoc.py` math, product defaults, `LEVEL_ENGINE_VERSION`, Program B, UI, golden regeneration |

### AP2 — selected-source implementation

| Field | Scope |
|---|---|
| Title | `AP2: add versioned opt-in APOC profile source` |
| Files | `thesistester/levels/apoc.py`, `all.py`, API/identity/cache plumbing, `_normalize_levels_settings` default, only the required source helper, source-specific tests, and living docs. Levels-page control is optional and must default to typical |
| Behavior | Implement the AP1-selected source behind `apoc_profile_source`, failure-to-`NaN` contract, source identity, and pAPOC propagation. Default callers keep typical-price APOC byte-for-byte |
| Acceptance | Existing Stage 5 expected values still pass under default/`typical_mvp_v1`; selected-source tests; missing-input → `NaN` (no typical fallback); source-specific PIT tests; series equality for unrelated level families; settings-hash changes when source/tick identity changes |
| Forbidden | Product-default cutover; `LEVEL_ENGINE_VERSION` bump unless a later dedicated cutover PR; prior VA changes; tick simulation clock; rolling-POC rewrite; execution changes; golden regeneration; LC catalog token renames |

### AP3 — Program B provenance

| Field | Scope |
|---|---|
| Title | `AP3: version Program B APOC provenance` |
| Files | Program B generator/manifests/docs and existing study/result identity metadata only where needed to record APOC source/version; Wave 7 YAML `levels` pin `apoc_profile_source: typical_mvp_v1` once the key exists |
| Behavior | Existing Wave 7 output is labeled legacy typical-price; generator emits an explicit typical pin so a later product cutover cannot silently rewrite Wave 7 on regenerate; fresh opt-in runs record selected source/version |
| Acceptance | YAML generation/validation remains deterministic; no historical ZIP rewrite; no non-APOC wave changes |
| Forbidden | Rerunning studies, changing Program B research locks, or modifying VA waves |

Merge order is AP0 → AP1 → AP2 → AP3. AP2 is blocked until AP1’s written
evidence gate selects a source. AP2 remains default-preserving even after
selection. A product-default cutover is a later AP PR, not AP2.

## 6. Regression-safety checklist

Map to `docs/ENGINEERING_PROPOSAL.md` §4:

| §4 rule | AP lock |
|---|---|
| 1 Additive-only | Keyword-only `apoc_profile_source`; default `typical_mvp_v1`; no positional signature change |
| 2 Golden-master | Preserve `tests/test_golden_master.py`. Goldens **do not cover APOC**: `run_legacy_pipeline` never calls `compute_all_levels`. Stage 5 + isolation tests are the numeric gate |
| 3 Opt-in, default-off | New math is opt-in via source key. `apoc_enabled=False` stays a no-op. Product `apoc_enabled=True` stays typical until a later versioned cutover |
| 4 Schema/identity | Source key lives inside the hashed settings dict; old snapshots `setdefault` to typical |
| 5 PIT | Future-shock on selected source, including later ticks |
| 6 `st.session_state` | Existing `levels_apoc_enabled` / `levels_settings` keys keep schema; new keys additive and documented in `ARCHITECTURE.md` in the PR that adds them |
| 7 Determinism | No wall-clock; explicit tie/rounding/bin policies |
| 8 Same-PR docs | Honesty / glossary / architecture / LC #3 only when the described behavior becomes true |
| 9 CI | Full pytest + ruff; no merge on red |
| 10 Honesty | Do not claim Quantower equivalence for a bar proxy |

Every AP1+ PR must:

- Preserve `compute_apoc_levels(..., enabled=False)` as a no-validation,
  no-column return.
- Retain or replace every Stage 5 test with an explicitly named source
  contract: disabled behavior, sort alignment, session derivation, RTH/ETH,
  A-period availability, zero/missing input, pAPOC, ties, and future shocks.
  Default-source tests must keep today’s expected values (`100.75` fixtures
  and equivalent).
- Assert `APOC`/`pAPOC` default-path changes do not occur, and that any
  opt-in source does not alter session levels, rolling POC, session VWAP,
  single prints, prior tick-VAP columns, signals, or fills.
- Run and preserve `tests/test_golden_master.py`; no AP PR regenerates golden
  artifacts. Do not treat a green golden file as proof that APOC math is
  unchanged.
- Update `ASSUMPTIONS_AND_LIMITATIONS.md`,
  `POINT_IN_TIME_GUARANTEES.md`, `METRICS_GLOSSARY.md`, and
  `ARCHITECTURE.md` only in the PR that makes the described behavior true.
- Include a PR-body regression-safety paragraph identifying default behavior,
  source identity/cache handling, point-in-time proof, unaffected families,
  and the golden-vs-Stage-5 coverage split.

## 7. Program B operational note

Wave 7 currently enables APOC and pAPOC on the 15-second-primary/derived
one-minute path (`apoc_enabled: true`, no source key). Its existing or future
results calculated before an explicit source pin use the legacy typical-price
APOC object and must not be compared to Quantower A-period POC as if they were
equivalent. AP3 records that provenance and pins
`apoc_profile_source: typical_mvp_v1` on Wave 7 YAML; it does not rewrite
prior research and does not rerun studies.
