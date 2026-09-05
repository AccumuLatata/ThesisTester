# APOC Quantower Parity — Investigation and Implementation Plan

**Document type:** Focused investigation plan  
**Date:** 2026-09-05  
**Status:** **AP0 locked — evidence collection pending.** No engine behavior has changed.  
**Series code:** **AP** (A-Period POC)  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including the
golden-master operational specification (§4.1) and per-PR checklist (§4.2).

## 1. Problem statement and current evidence

The desk reports that, for MNQ RTH 2026-09-04, Quantower displayed an A-period
POC of `29625.00`, while ThesisTester produced `29611.75` from the same
Quantower History Exporter 15-second source after UTC → `America/New_York`
normalization. The reported A-period is `[09:30, 10:00)` New York time.

The repository independently confirms the ThesisTester side: `APOC` currently
uses 1-minute OHLCV bars, assigns each bar's entire volume to
`(high + low + close) / 3`, then computes the tick-binned POC. It excludes ETH,
appears only from A-period completion, and carries the previous finalized
session value as `pAPOC`.

The repository does **not** contain the 2026-09-04 MNQ export, a Quantower APOC
reference file, or a recorded Quantower indicator/template configuration.
Therefore the observation proves a discrepancy, but does not yet prove that
Quantower uses uniform bar-range volume allocation, TPO allocation, or tick
Last×Volume for this level. A bar-range method reproducing one session is not
sufficient evidence to label that method Quantower-compatible.

## 2. Locked scope and invariants

### In scope

- Determine the calculation object used by the Quantower A-period POC on
  reproducible MNQ fixtures.
- Select a source/allocation method only after comparative evidence.
- If evidence supports a change, introduce a versioned, explicit APOC source
  and preserve point-in-time semantics.
- Record enough provenance that future Program B results identify the APOC
  object used.

### Out of scope

- `pd*` / `pw*` / `pm*` tick VAP, including its TV-series identity contract.
- Rolling POC, VA, VWAP, opening range, session marks, TPO single prints,
  signals, confluence, fills, or simulation.
- Replacing the 15-second-primary / derived-1-minute product clock.
- Retrospective mutation, deletion, or reinterpretation of Program B results.
- Claiming agreement with Quantower from an unverified proxy.

### Invariants

1. The A-period is RTH-only and half-open: `[RTH open, RTH open + 30 minutes)`.
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

## 3. Evidence protocol (required before production math)

### 3.1 Desk evidence package

Keep proprietary inputs outside git. Each package must include:

| Item | Required record |
|---|---|
| Bar source | Original 15-second HE export, SHA-256, row count, instrument/contract, source timezone, and exporter profile |
| Quantower oracle | A CSV or manually transcribed table of date → APOC/pAPOC, plus a screenshot/export of the exact indicator and its settings |
| Chart context | Data provider, chart aggregation, session template, exchange timezone, bar-build mode, profile row size, and POC/tie setting if exposed |
| Tick source, when used | Tick–Tick–Last export SHA-256, row count, source timezone, and relationship to the chart data feed |
| Audit output | The selected A-period bars/ticks, local timestamps, source rows, candidate histogram, target value, error in points, and error in MNQ ticks |

The reference table must include at least ten independent sessions: the named
2026-09-04 case, narrow and wide A-period ranges, sparse/trade-only 15-second
data, a candidate tie, ordinary days, and a DST-adjacent session where
available. The data provider, contract and session template must remain fixed
within the comparison set.

### 3.2 Controlled candidate comparison

AP1 compares candidates without changing production output:

| Candidate | Allocation | Purpose |
|---|---|---|
| `typical_mvp_v1` | Full bar volume at `(H+L+C)/3` | Reproduce current engine |
| `bar_range_uniform_volume_v1` | Each bar's volume divided equally across all inclusive tick bins from low to high | Test the desk hypothesis |
| `bar_range_tpo_v1` | One time unit per touched inclusive tick bin per bar; bar volume ignored | Distinguish TPO-style behavior |
| `tick_last_volume_v1` | Quantower Tick–Tick–Last price × volume inside the A-period | Test true VAP when matching tick data exists |

Before candidates run, AP1 must lock:

- Whether range endpoints are rounded, rejected, or snapped to the instrument
  grid; the policy must reject unsound input rather than silently alter it.
- Inclusive range-bin semantics and zero-range behavior.
- Volume conservation tolerance for volume-based candidates.
- Exact POC tie policy. ThesisTester currently resolves equal bin volume to the
  lowest price; Quantower behavior must be observed rather than assumed.
- The minimum coverage/completeness requirement for sparse bar and tick data.

### 3.3 Source-selection gate

The named 2026-09-04 value must be within one MNQ tick (`±0.25`). A candidate
also needs the predeclared multi-session score threshold in AP1; the threshold
and reference rows must be written before inspecting aggregate candidate
results. Failure has a defined outcome:

- No candidate meets the threshold: do not cut over; retain documented
  typical-price APOC and open a bounded data/settings investigation.
- Only tick Last×Volume meets the threshold: select tick VAP; do not present a
  bar proxy as Quantower-compatible.
- A bar method meets the threshold but tick evidence is absent or divergent:
  ship it only as a documented bar proxy, not a claim of tick equivalence.

## 4. Implementation architecture after selection

AP2 implements exactly one AP1-selected source.

1. Add a keyword-only `apoc_profile_source` with a versioned value. Direct
   library defaults remain legacy-compatible and `apoc_enabled=False` remains a
   true no-op.
2. For an OHLC-derived source, calculate only from the selected session's
   A-period rows after exchange-timezone conversion.
3. For a tick source, build an A-period profile table keyed by RTH session date
   from the existing Quantower Tick–Tick–Last loader. It must filter ticks to
   the A-period in exchange time; the full-session `PriorProfileTable` is not
   a substitute.
4. Add the source, algorithm version, allocation settings, and input source
   identity to the levels settings identity. A source change used by product
   defaults requires a `LEVEL_ENGINE_VERSION` bump.
5. Do not silently change the meaning of persisted APOC results. Historical
   product/default behavior requires either an explicit opt-in source or a
   versioned cache/metadata cutover.

## 5. Fully scoped PR series

### AP0 — plan lock (this PR)

| Field | Scope |
|---|---|
| Title | `AP0: lock Quantower APOC investigation plan` |
| Files | This plan; index-only pointers in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, and `docs/AGENT_GUIDE.md` |
| Behavior | Documentation only; no level calculation, cache, default, study, or UI change |
| Acceptance | Scope, evidence protocol, candidate gate, AP1–AP3 boundaries, and regression rules are explicit |
| Forbidden | Engine edits, fixture-data commits, result reruns, golden regeneration |

### AP1 — comparator and evidence discriminator

| Field | Scope |
|---|---|
| Title | `AP1: add APOC profile comparison harness` |
| Files | New pure candidate module under `thesistester/levels/`; `tests/test_apoc_candidates.py`; tiny synthetic fixtures; optional env-gated desk-oracle test; this plan and roadmap status |
| Behavior | Compute candidate profiles and auditable histograms without modifying `compute_apoc_levels` output |
| Acceptance | Hand-computed allocation, conservation, bin-edge, zero-range, tie, timezone, sparse-input, and candidate-isolation tests; optional desk test records per-session error |
| Forbidden | `apoc.py` production cutover, defaults, `LEVEL_ENGINE_VERSION`, Program B, golden regeneration |

### AP2 — selected-source implementation

| Field | Scope |
|---|---|
| Title | `AP2: add versioned APOC profile source` |
| Files | `thesistester/levels/apoc.py`, `all.py`, API/identity/cache plumbing, only the required source helper, source-specific tests, and living docs |
| Behavior | Implement the AP1-selected source, failure-to-`NaN` contract, source identity, and pAPOC propagation |
| Acceptance | Reference fixture gate, complete current Stage 5 coverage, source-specific PIT tests, and series equality for unrelated level families |
| Forbidden | Prior VA changes, tick simulation clock, rolling-POC rewrite, execution changes, golden regeneration |

### AP3 — Program B provenance

| Field | Scope |
|---|---|
| Title | `AP3: version Program B APOC provenance` |
| Files | Program B generator/manifests/docs and existing study/result identity metadata only where needed to record APOC source/version |
| Behavior | Existing Wave 7 output is labeled legacy typical-price; fresh runs record selected source/version |
| Acceptance | YAML generation/validation remains deterministic; no historical ZIP rewrite; no non-APOC wave changes |
| Forbidden | Rerunning studies, changing Program B research locks, or modifying VA waves |

Merge order is AP0 → AP1 → AP2 → AP3. AP2 is blocked until AP1’s written
evidence gate selects a source.

## 6. Regression-safety checklist

Every AP1+ PR must:

- Preserve `compute_apoc_levels(..., enabled=False)` as a no-validation,
  no-column return.
- Retain or replace every Stage 5 test with an explicitly named source
  contract: disabled behavior, sort alignment, session derivation, RTH/ETH,
  A-period availability, zero/missing input, pAPOC, ties, and future shocks.
- Assert `APOC`/`pAPOC` changes do not alter session levels, rolling POC,
  session VWAP, single prints, prior tick-VAP columns, signals, or fills.
- Run and preserve `tests/test_golden_master.py`; no AP PR regenerates golden
  artifacts.
- Update `ASSUMPTIONS_AND_LIMITATIONS.md`,
  `POINT_IN_TIME_GUARANTEES.md`, `METRICS_GLOSSARY.md`, and
  `ARCHITECTURE.md` only in the PR that makes the described behavior true.
- Include a PR-body regression-safety paragraph identifying default behavior,
  source identity/cache handling, point-in-time proof, and unaffected
  families.

## 7. Program B operational note

Wave 7 currently enables APOC and pAPOC on the 15-second-primary/derived
one-minute path. Its existing or future results calculated before AP2 use the
legacy typical-price APOC object and must not be compared to Quantower A-period
POC as if they were equivalent. AP3 records that provenance; it does not
rewrite prior research.
