# Rolling POC Quantower Parity — Investigation and Implementation Plan

**Document type:** Focused investigation + fully scoped implementation plan  
**Date:** 2026-09-07  
**Status:** **RP0 locked. RP1–RP2 fully scoped.** Production tick opt-in
(**RP2**) does not merge until the written §4.3 scorecard selects
``tick_last_volume_v1``. Product/library default remains typical.  
**Series code:** **RP** (Rolling POC)  
**Related:** `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md` (AP — A-period only);
`docs/TICK_VAP_IMPLEMENTATION_PLAN.md` (TV — prior-session VA only).  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including the
golden-master operational specification (§4.1) and per-PR checklist (§4.2).

**What’s next:** merge/land this plan, then **RP1** (comparator harness, no
production math change). Do not open RP2 until **RP1g** records the scorecard.

## 1. Problem statement and current evidence

### 1.1 Hypothesis (from the APOC series)

AP1 showed that dumping each bar’s full volume onto typical `(H+L+C)/3` misses
Quantower A-period POC, and that Tick–Tick–Last Last×Volume matched 4/4 on the
written Levels2test scorecard. `POC_rolling_30min` still uses that same typical
allocation via `profile._compute_profile` / `_rolling_poc`. The question is
whether rolling / developing POC needs the same tick source to be the chart
object.

### 1.2 What the repository already proves

| Claim | Evidence | Verdict |
|---|---|---|
| Rolling POC allocates each **derived-1m** bar’s volume to typical `(H+L+C)/3` | `thesistester/levels/profile.py` `_rolling_poc` + typical `prices` | **Confirmed** |
| Same histogram helper as default APOC (`typical_mvp_v1`) | `_compute_profile`; AP1 typical candidate matches `_compute_a_period_poc` | **Confirmed** |
| 15s is not the levels clock | `compute_all_levels` consumes the 1m parent; 15s is ingest + R12 | **Confirmed** |
| `PriorProfileTable` is a full-session prior-VA freeze, not a rolling window | TV3 join via `shift(1)` | **Confirmed** — must not be reused |
| AP1 4/4 tick scorecard transfers to rolling POC | Window identity (below) | **Rejected as a cutover argument** |

### 1.3 Window identity (in-repo, 2026-09-07)

`_rolling_poc` membership is half-open on **bar-open timestamps**:

```text
start = now - 30min
in_window = (timestamp > start) & (timestamp <= now)
```

On a complete 1m grid that is exactly 30 bars. Synthetic RTH hour
(`instrument="ES"`, unique typical per minute, A-period mode at 09:45,
competing mode at 10:00):

| Stamp (NY bar open) | Rolling members | `POC_rolling_30min` | `APOC` |
|---|---|---:|---:|
| 09:59 | 09:30 … 09:59 | 103.75 | `NaN` (A-period not yet emitted) |
| 10:00 | 09:31 … 10:00 | 200.00 | 103.75 (frozen A-period) |

Typical rolling POC **equals** typical APOC **only** on the last A-period bar
(09:59). One minute later they are different objects. APOC’s Levels2test
oracle (values at/after 10:00) is therefore **not** a rolling-POC oracle.

Print coverage of those 1m bars, if timestamps are bar opens, is
`[min(member_open), max(member_open) + 1min)`:

- 09:59 → prints `[09:30, 10:00)` — same clock window as the A-period.
- 10:00 → prints `[09:31, 10:01)` — not the A-period.

### 1.4 Quantower does not name this column

Public Quantower Volume Profile tools are **Session / Left / Right**, **Step**
(fixed adjacent bricks: Minute/Hour/Day/Week/Month × coefficient), and
**Custom** (operator-drawn range). There is no vendor token
`POC_rolling_30min`.

| Quantower tool | Object | Relation to ThesisTester |
|---|---|---|
| Step 30m, RTH template, Volume, 1-tick | Frozen adjacent 30m VAP bricks | First RTH brick **is** APOC, not rolling POC |
| Session / developing profile | Histogram from session open to now | Not a 30m lookback; closest TT name would be parked `dPOC` |
| Custom range ending at `T` spanning 30m | Operator-defined Last×Volume | Closest analog to a **sliding** 30m window, only if the range is rebuilt every minute |
| TPO / Market Profile letters | Time-at-price | `tpo.py` single prints; out of scope |

AP1’s 4/4 result is evidence about **allocation given a window**. It is not
evidence that Quantower displays ThesisTester’s sliding 30m window.

The repository contains no Quantower rolling-POC export, screenshot, or
indicator settings for any session.

## 2. Locked scope and invariants

### In scope

- Identify the Quantower calculation object (tool + data type + period +
  session template + row size + POC tie) before changing production math.
- Compare versioned allocation candidates on **the same locked window**.
- If §4.3 selects a source, RP2 adds that versioned explicit rolling-POC
  source (§5). Product default remains typical.

### Out of scope (entire RP series unless a later plan amends this file)

- `pd*` / `pw*` / `pm*` tick VAP (TV3 identity).
- APOC / pAPOC production source, defaults, or Program B Wave 7 provenance.
- Tick VWAP (`dVWAP*` / `VWAP_rolling_*` / `prev30mVWAP`).
- Developing `dVAH` / `dVAL` / `dPOC` (parked; not emitted).
- Replacing `15s_primary_derive_1m`.
- Using `PriorProfileTable` or `APeriodTickProfileTable` as a rolling window.
- Golden regeneration. Silent default cutover.

### Invariants

1. `compute_profile_levels` without a new explicit source keeps today’s
   typical `POC_rolling_*` values on the same 1m frame.
2. TV3 omit/fail-closed VA is unchanged: no ticks → nine VA columns absent;
   named-VA studies still refuse `VA requires ticks`.
3. 15s remains the bar clock. Ticks are a side histogram input.
4. Missing / malformed / off-grid tick inputs under a future tick source emit
   `NaN`, never typical under a new source identity.
5. Bar-range uniform volume is a **proxy candidate only**. It is not a
   Quantower claim without a written scorecard (AP1: 2/4 on A-period).
6. A 15s typical dump is not a substitute for ticks. AP1 already showed
   finer bars / range-split still missed Quantower POC.

## 3. Candidate table (RP1)

Reuse `apoc_candidates` histogram contracts: off-grid reject (no silent snap);
inclusive range bins; volume conservation
`VOLUME_CONSERVATION_RTOL` / `VOLUME_CONSERVATION_ATOL`; lowest-price POC tie
(`np.argmax` on an ascending grid; Quantower tie is observed, not assumed);
sparse coverage = observed rows only; empty usable observations → `NaN` POC.

Do **not** call `select_a_period_rows` for rolling windows. Window selection is
a separate helper. Histogram builders
(`compute_bar_candidate_profile`, `compute_tick_last_volume_profile`) stay
shared.

| Candidate | Input | Allocation | Purpose |
|---|---|---|---|
| `typical_mvp_v1` | 1m bars in `(now-30min, now]` | Full bar volume at `(H+L+C)/3` | Reproduce production `_rolling_poc` |
| `typical_mvp_15s_v1` | 15s bars whose opens fall in the mapped print window | Same typical dump | Discriminate “finer typical” vs tick. **Not** a Quantower claim |
| `bar_range_uniform_volume_v1` | 1m **or** 15s bars in the locked window (declare which) | Volume split equally across inclusive tick bins `[low, high]` | AP1 proxy; scorecard only |
| `bar_range_tpo_v1` | Same bars | One count per touched tick bin; volume ignored | Discriminate TPO vs VAP |
| `tick_last_volume_v1` | Quantower Tick–Tick–Last prints in the mapped print window | Last × Volume | Test true VAP |

**Locked print-window map for the tick / 15s candidates** (must match 1m bar
membership, not a second clock):

```text
members = 1m opens in (now - 30min, now]
prints  = [min(members), max(members) + 1min)
```

RP1 must also record, as diagnostics not production sources:

- Endpoint variants (`(t0, t1]` vs `[t0, t1)`) if Quantower’s custom range is
  inclusive on the right.
- Session-open developing VAP (`dPOC`-shaped) so a Session-profile oracle is
  not silently scored as rolling 30m.

RP1 computes **sampled stamps**, not every 1m bar: at least RTH 09:59 (A-period
overlap check), 10:00 (divergence check), 11:00, 14:00, plus one ETH stamp if
the Quantower template includes ETH. Full-timeline tick rolling is an RP2
engineering problem (streaming histogram), not an evidence problem.

## 4. Desk-oracle protocol

Keep proprietary inputs outside git. Write the scorecard **before** inspecting
aggregate candidate results.

### 4.1 Package (required)

| Item | Required record |
|---|---|
| Bar source | Original 15s HE export, SHA-256, row count, contract, source TZ, exporter profile; derived-1m policy `observed_aligned_15s_to_1m_v2` |
| Tick source | Tick–Tick–Last SHA-256, row count, source TZ, relationship to the chart feed |
| Quantower oracle | CSV or transcribed table of `(session_date, stamp_NY, poc)` plus screenshot of the **exact tool** and settings |
| Tool identity | One of: Step / Session / Custom; data type (Volume vs trades vs delta); step period × coefficient **or** custom range start/end; session template; custom step (ticks); POC / VA visible; extend-POC setting |
| Audit output | Per stamp: member bar opens, print window, n_bars, n_ticks, candidate POCs, QT value, error in MNQ ticks (0.25) |

Minimum **ten independent stamps** across ≥ four sessions, including the
2026-09-01…09-04 AP1 dates where the same tape exists: narrow and wide 30m
ranges, a sparse/trade-only minute inside the window, a candidate tie, one
ordinary midday stamp, one DST-adjacent session if available. Contract and
template stay fixed inside the comparison set.

### 4.2 Forbidden oracle substitutions

- Using AP1 A-period POC at 10:00 as `POC_rolling_30min` at 10:00.
- Using Quantower Step 30m brick *k* as a sliding window ending inside that
  brick (Step is frozen; rolling has already moved).
- Using prior-day `pdPOC` / session-20 TV3 targets.
- Scoring 15s bar-range as Quantower-compatible without this table.

### 4.3 Source-selection gate (predeclared)

Per stamp, a candidate **hits** if `|poc - qt| ≤ 1 MNQ tick` (`0.25`).

Written threshold **before** looking at aggregates:

- **Select tick Last×Volume** only if it hits on ≥ 8/10 stamps **and** no bar
  proxy hits more stamps.
- **Select a bar proxy** only if it meets 8/10 **and** tick is absent or
  worse; ship it only as a documented bar proxy, never as tick-equivalent.
- **No cutover** if no candidate meets 8/10, or if the Quantower tool is
  Session-developing / Step-brick / TPO rather than a sliding 30m VAP.
- Failure mode: retain documented typical rolling POC; open a bounded
  settings/window investigation. Do not change `LEVEL_ENGINE_VERSION`.

A-period overlap (09:59 typical rolling vs typical APOC) is a **sanity check
of membership**, not a Quantower hit.

## 5. Implementation architecture (locked; RP2 implements only if §4.3 selects)

RP2 implements **exactly one** RP1-selected production source. Until RP1g
writes that selection, this section is the specification, not authorization
to merge engine changes.

### 5.1 Object

`POC_rolling_{window}` under the tick source means:

> POC of Last×Volume prints whose timestamps fall in
> `[min(member_opens), max(member_opens) + 1min)`, where `member_opens` are
> the 1m bar-open timestamps in `(now - window, now]`. Binning is
> `instrument_tick_size` (no extra `aggregation_ticks`). Tie = lowest price
> (`np.argmax` on an ascending grid). PIT: only prints with `ts < now+1min`.

It is **not** A-period APOC, **not** prior-session `pdPOC`, **not**
session-developing `dPOC`, **not** Quantower Step 30m.

The 30min window is the Quantower-lock target. `1h` / `4h` inherit the same
algorithm when those `poc_windows` are requested; they are **not** QT-locked
until a separate oracle exists (same honesty as TV week/month bins 8/10).

### 5.2 Keyword and defaults (AP2 posture)

| Item | Lock |
|---|---|
| Settings / StudySpec key | `rolling_poc_profile_source` |
| Library kwarg | `compute_profile_levels(..., rolling_poc_profile_source=..., tick_paths=...)` keyword-only for the source |
| Omitted key | Implicit `typical_mvp_v1`; pre-RP2 settings hash **unchanged** |
| Product `DEFAULT_LEVELS_SETTINGS` | **Does not** include the key (farm / Levels page stay typical) |
| `OPTIONAL_LEVELS_SETTINGS` | Add `rolling_poc_profile_source` (same set as `apoc_profile_source`) |
| Production source tokens | `typical_mvp_v1` and **only** the §4.3-selected token (expected: `tick_last_volume_v1`) |
| Bar-range / 15s-typical | Comparator-only unless §4.3 selects a bar proxy; never advertised as tick-equivalent |
| `LEVEL_ENGINE_VERSION` | Stays **11** (default algorithm unchanged) |
| Columns | Always emit `POC_rolling_*` for requested windows. Tick source with missing ticks → **`NaN`**, not column omit, not typical fallback |
| Study refuse | **No** `VA requires ticks` analog. 15s-only studies that omit the key keep typical rolling POC |

### 5.3 Tick path (do not reuse VA / APOC tables)

```text
1m parent bars (clock)
        │
        ├─ typical_mvp_v1 ──► existing _rolling_poc (unchanged)
        │
        └─ tick_last_volume_v1
                │
tick_paths[] ──► iter_tick_files (existing TV1 loader)
                │
         session chunks + lookback overlap of max(requested windows)
                │
         two-pointer sliding histogram per 1m bar
                │
         compute_tick_last_volume_profile math (shared bins / tie / conservation)
                │
         POC_rolling_* series
```

Forbidden substitutes: `PriorProfileTable`, `APeriodTickProfileTable`,
`select_a_period_rows`, dumping ticks into `_rolling_poc`’s per-bar Python
scan (`O(bars × ticks_in_window)`).

**Sliding algorithm (normative):**

1. Sort 1m opens; sort ticks by timestamp.
2. For each bar `now` in order, member window `(now - W, now]`.
3. Print window `[t0, t1)` from §3. Advance `left`/`right` pointers only
   forward. Maintain `bin → volume`. POC = argmax (lowest bin on ties).
4. Empty members or empty positive-volume ticks → `NaN`.
5. Off-grid / non-finite / non-positive tick volume: fail that bar to `NaN`
   (or fail the whole series if ingest fails closed — match AP2 empty-table
   behavior at the **file** layer; per-bar NaN for sparse holes).
6. Window may cross CME session open (`eth_start`). Carry a lookback buffer
   of `max(windows)` from the previous chunk. Do not clip to RTH.

`run_experiment` / `compute_levels` must forward `dataset.tick_paths` into
this path even when a prior-VA parquet is already attached (AP2 foot-gun).

### 5.4 Identity

New keys, **only when** `rolling_poc_profile_source` is explicit (implicit
typical is a no-op, like `attach_apoc_identity`):

| Key | Typical explicit | Tick explicit |
|---|---|---|
| `rolling_poc_profile_source` | `typical_mvp_v1` | `tick_last_volume_v1` |
| `rolling_poc_algorithm_version` | `typical_mvp_v1` | `tick_last_volume_v1` |
| `rolling_poc_allocation` | `typical_hlc3_full_volume` | `last_times_volume` |
| `rolling_poc_tick_source_id` | `none` | SHA-256 of tick files **plus** policy `rolling_lookback_v1` and canonical `poc_windows` |

Must not equal VA `tick_source_id` or `apoc_tick_source_id`. Strip these keys
before `compute_all_levels` kwargs (mirror `LEVELS_APOC_IDENTITY_KEYS`).

### 5.5 Point-in-time

Appending future 1m bars or future ticks must not change `POC_rolling_*` at
earlier timestamps. Test with future-shock on both typical (already exists)
and tick source. Current-bar inclusion stays as today: window includes
`timestamp == now` (bar-close confirmed; same limitation as typical).

### 5.6 UI / Program B / goldens

| Surface | RP2 action |
|---|---|
| Levels page | **No** new dropdown (AP2 shipped headless opt-in only) |
| Data page / Help | Honesty sentence only if the key can be set; do not require ticks for non-VA studies |
| Program B YAML | **Do not** add the key (implicit typical). No Wave provenance analog |
| Goldens | **No regen.** `run_legacy_pipeline` never calls `compute_all_levels` |

### 5.7 Performance bound

Naive per-bar tick scan is forbidden. Two-pointer add/remove must be
`O(N + T)` after the sort, plus `O(bins)` POC on each bar. Informational
check on a ≥780-bar fixture with a tiny synthetic tick stream; no CAI wall
time as a CI fail. If the tick path is slower than typical `_rolling_poc` on
that fixture by more than an order of magnitude, stop and fix the algorithm
before merge — do not ship nested scans.

---

## 6. Go / no-go

| Decision | Verdict | Why |
|---|---|---|
| RP0 — lock evidence + this spec | **Go** | Allocation confirmed; window ≠ A-period |
| RP1 — comparator harness | **Go now** | Required discriminator; no production output change |
| RP1g — write §4.3 scorecard into this plan | **Go after RP1** | Merge gate for RP2 |
| RP2 — versioned tick opt-in | **Go only if RP1g selects `tick_last_volume_v1`** | Otherwise close RP2 |
| RP2-cancel — docs-only “retain typical” | **Go if RP1g selects nothing / Session / Step / TPO** | Honesty; no engine change |
| Product-default cutover | **No-go** | AP2 posture |
| Reuse `PriorProfileTable` / `APeriodTickProfileTable` | **No-go** | Wrong object |
| 15s bar-range as Quantower-compatible | **No-go** without §4.3 | AP1 was 2/4 |
| Program B YAML / `LEVEL_ENGINE_VERSION` / golden regen | **No-go** | Default algorithm unchanged |
| Levels-page source widget | **No-go this series** | Narrow; AP2 had none |
| Developing `dPOC` / tick VWAP | **No-go** | Out of series |

---

## 7. Fully scoped PR series

Merge order: **RP0 → RP1 → RP1g → (RP2 | RP2-cancel)**. Do not combine RP1
with RP2. Do not open RP2 and RP1g in parallel.

### RP0 — plan lock

| Field | Scope |
|---|---|
| Title | `RP0: lock Quantower rolling-POC investigation plan` |
| Files | This plan; index-only pointers in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md` |
| Behavior | Documentation only |
| Status | **Landed as the RP0 commit; this document now also scopes RP1–RP2** |
| Forbidden | Engine edits, fixture-data commits, golden regen |

### RP1 — comparator harness (next)

| Field | Scope |
|---|---|
| Title | `RP1: add rolling-POC profile comparison harness` |
| Files | `thesistester/levels/rolling_poc_candidates.py` (**new**); `tests/test_rolling_poc_candidates.py` (**new**); this plan §RP1 implementation record; roadmap/agent one-line status. **May import** `compute_bar_candidate_profile`, `compute_tick_last_volume_profile`, conservation constants from `apoc_candidates.py`. |
| Behavior | Sampled-stamp candidate POCs + auditable histograms. **Zero** change to `_rolling_poc` / `compute_profile_levels` output |
| Public helpers (normative names) | `select_rolling_member_bars(bars, now, window)`; `rolling_print_window(member_opens, bar_interval)`; `compare_rolling_poc_candidates(...)` |
| Window lock | Members: 1m opens in `(now - W, now]`. Prints: `[min(members), max(members)+1min)`. Do **not** call `select_a_period_rows` |
| Candidates | Exact table in §3. `bar_range_uniform_volume_v1` must declare 1m vs 15s in the result metadata |
| Diagnostics (not production tokens) | Optional endpoint-variant and session-open developing VAP helpers, clearly named, not in `BAR_CANDIDATES` |
| Env-gated oracle | `THESISTESTER_RP_QT_1M`, `THESISTESTER_RP_QT_TICKS` (optional), `THESISTESTER_RP_QT_EXPECTED` (CSV: `session_date,stamp_ny,poc`). Skipped in CI. Reports per-stamp error in MNQ ticks for each candidate. Does **not** fail CI on miss; records numbers |
| Acceptance | See §8.1 |
| Forbidden | `profile.py` production edits; `all.py` / `api.py` / defaults / study schema / Program B; `LEVEL_ENGINE_VERSION`; golden regen; committing desk CSVs |

**RP1 implementation record:** fill in this subsection in the RP1 PR (same
pattern as AP1). Must state: typical candidate equals production
`POC_rolling_30min` at the sampled stamp; 09:59 members == A-period bars;
10:00 members drop 09:30; tick candidate at 10:00 does **not** use
`select_a_period_rows`.

### RP1g — scorecard record (docs only)

| Field | Scope |
|---|---|
| Title | `RP1g: record rolling-POC Quantower scorecard` |
| Files | This plan §4.3 result table + go/no-go line; one-line roadmap/agent status |
| Behavior | Write the predeclared threshold outcome. Name the Quantower tool. Select exactly one of: `tick_last_volume_v1` / documented bar proxy / **retain typical (RP2-cancel)** |
| Acceptance | ≥10 stamps; tool identity recorded; per-stamp errors; explicit selected token or cancel |
| Forbidden | Engine edits; treating AP1 4/4 as this scorecard; claiming Step 30m = rolling |

### RP2 — versioned tick source (merge-gated)

Open **only** after RP1g selects `tick_last_volume_v1` (or a named bar proxy;
then implement **that** token, not ticks).

| Field | Scope |
|---|---|
| Title | `RP2: add versioned rolling-POC profile source` |
| Files | `thesistester/levels/profile.py` (source gate; typical branch **byte-identical**); **new** `thesistester/levels/rolling_poc_tick.py` (two-pointer + `attach_rolling_poc_identity` + source id policy); `thesistester/levels/all.py`; `thesistester/levels/defaults.py` (`OPTIONAL_LEVELS_SETTINGS` only); `thesistester/api.py` (forward `tick_paths` when source is tick even if VA parquet present; strip identity keys); `thesistester/study/schema.py` (accept/validate the optional key); `thesistester/persistence/local_store.py` only if identity keys must be listed — prefer stripping in API like APOC; `tests/test_rolling_poc_tick_source.py`; living docs listed in §8.2 |
| Behavior | Keyword-only source. Omitted = today’s typical. Tick = §5.1 object, failure-to-`NaN` |
| Acceptance | See §8.2 |
| Forbidden | Default cutover; VA/APOC math; tick VWAP; `dPOC`; Program B YAML; golden regen; Levels-page widget; nested tick scan; `LEVEL_ENGINE_VERSION` bump |

### RP2-cancel — retain typical (docs only; exclusive with RP2)

| Field | Scope |
|---|---|
| Title | `RP2-cancel: retain typical rolling POC` |
| Files | This plan status; honesty one-liners in `ASSUMPTIONS_AND_LIMITATIONS.md` / `METRICS_GLOSSARY.md` / `POINT_IN_TIME_GUARANTEES.md` stating rolling POC remains 1m typical and is not Quantower sliding VAP |
| Behavior | No engine change |
| Forbidden | Quietly shipping a bar proxy under the old name |

---

## 8. Per-PR acceptance tests

### 8.1 RP1

Must pass:

1. `select_rolling_member_bars` on a complete 09:30–10:29 1m grid: 09:59 →
   30 bars 09:30…09:59; 10:00 → 30 bars 09:31…10:00.
2. Typical candidate POC at 09:59 equals `compute_profile_levels` /
   `_compute_a_period_poc` on those members (same fixture as RP0 proof).
3. Typical candidate at 10:00 **differs** from production `APOC` at 10:00 on
   the competing-mode fixture.
4. `compare_rolling_poc_candidates` does not call `compute_profile_levels`
   internally for the tick/bar-range paths (typical may **assert equal** to
   production, not replace it).
5. Tick candidate print window at 10:00 is `[09:31, 10:01)` given 1m opens,
   not `[09:30, 10:00)`.
6. Off-grid reject, conservation, inclusive range, lowest-price tie, empty →
   `NaN` — reuse AP1 numeric contracts via shared helpers.
7. Isolation: `compute_profile_levels` `POC_rolling_30min` series-equal
   before/after importing the new module on `tests/test_phase3_levels.py`
   simple dataset (or a copied fixture). VA columns still omitted without a
   table.
8. Env-gated oracle skipped when env vars unset.
9. `tests/test_golden_master.py` green; no golden files touched.

### 8.2 RP2

Must pass (in addition to §7 checklist):

1. Omitted `rolling_poc_profile_source`: `POC_rolling_30min` series-equal to
   pre-RP2 on the phase3 simple dataset **and** on an isolation fixture that
   also has `prior_profile_table` (VA join unchanged).
2. Explicit `typical_mvp_v1`: same values as omitted typical; identity keys
   present; settings hash ≠ implicit hash (AP2 pattern).
3. `tick_last_volume_v1` with synthetic ticks: sampled stamps match
   `compare_rolling_poc_candidates` tick POC (RP1 harness is the oracle for
   the engine).
4. Missing / empty `tick_paths` under tick source: `POC_rolling_*` all-NaN;
   no typical fallback; no exception at `compute_profile_levels`.
5. Off-grid tick file: NaN, not snap.
6. Future-shock: append future bars **and** future ticks; prefix values
   unchanged.
7. `PriorProfileTable` present does not substitute for rolling ticks;
   `APeriodTickProfileTable` does not either.
8. `run_experiment` still forwards `dataset.tick_paths` when a VA parquet is
   attached (mirror `tests/test_apoc_tick_source.py` wiring test).
9. Unrelated families series-equal vs typical run: session marks, `dVWAP*`,
   TPO, default APOC, `prev30mVWAP`, `pd*` when the same table is passed.
10. StudySpec unknown key still fail-closed; `rolling_poc_profile_source`
    accepted only as a supported token; Program B YAMLs still omit the key.
11. Identity: rolling tick source id ≠ VA id ≠ APOC id.
12. Two-pointer complexity: unit test that each tick is assigned at most a
    constant number of pointer moves across the bar loop (monotonic
    left/right), not a full rescan.
13. Goldens green; no regen.
14. Living docs in **this** PR: `ASSUMPTIONS_AND_LIMITATIONS.md`,
    `POINT_IN_TIME_GUARANTEES.md`, `METRICS_GLOSSARY.md`, `ARCHITECTURE.md`,
    this plan’s RP2 implementation record. USER_GUIDE one sentence if Help
    already says “rolling POC remain 1m typical.”

---

## 9. Regression-safety checklist (every RP1+ PR)

- Typical `POC_rolling_*` value-identical when the new source is omitted.
- TV3 intact: no table → no `pdVAH`…`pmPOC`; named VA without ticks still
  raises `VA requires ticks`.
- Default APOC remains implicit typical; AP2 tick APOC still independent.
- No change to session levels, session VWAP, TPO, signals, fills, or R12.
- `tests/test_golden_master.py` preserved; no RP PR regenerates goldens.
- Honesty docs only in the PR that makes the described behavior true.
- PR body includes a regression-safety paragraph: default behavior, identity
  / cache, PIT proof, unaffected families.

---

## 10. Copy-ready RP1 prompt

```markdown
Implement RP1 only: rolling-POC comparison harness. Canonical spec:
docs/ROLLING_POC_QUANTOWER_INVESTIGATION_PLAN.md §3, §7 RP1, §8.1.

Do:
- Add thesistester/levels/rolling_poc_candidates.py with
  select_rolling_member_bars, rolling_print_window,
  compare_rolling_poc_candidates.
- Import histogram builders from apoc_candidates. Do not call
  select_a_period_rows. Do not edit profile.py production math.
- Tests in tests/test_rolling_poc_candidates.py covering §8.1 1–8.
- Env-gated oracle skipped in CI (THESISTESTER_RP_QT_*).
- Fill the RP1 implementation record in the plan; one-line roadmap status.

Do not:
- Change _rolling_poc / compute_profile_levels output.
- Add rolling_poc_profile_source.
- Touch VA, APOC production, Program B, goldens, LEVEL_ENGINE_VERSION.
- Commit proprietary desk CSVs.
- Present bar-range as Quantower-compatible.

Regression: typical POC_rolling_30min series-equal on the phase3 simple
dataset; VA omit without a table still holds; test_golden_master.py green.
```

