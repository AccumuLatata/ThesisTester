# Rolling POC Quantower Parity — Investigation and Implementation Plan

**Document type:** Focused investigation + fully scoped implementation plan
**Date:** 2026-09-07 (rev 2 — review locks vs live helpers)
**Status:** **RP0 locked. RP1–RP2 fully scoped.** Production opt-in
(**RP2**) does not merge until the written §4.3 scorecard selects
``tick_last_volume_v1`` or 1m ``bar_range_uniform_volume_v1``. Product/library
default remains typical.
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

Typical rolling **membership** at 09:59 is the A-period 1m set
(`[09:30, 10:00)` bar opens). Typical rolling POC at 09:59 therefore equals
`_compute_a_period_poc(members)` and equals **`APOC` at 10:00** (first emit).
The 09:59 `APOC` **column is NaN** (`timestamp >= RTH_open + 30min`). One
minute later they are different objects. APOC’s Levels2test oracle (values
at/after 10:00) is therefore **not** a rolling-POC oracle.

Tick / 15s print coverage is the **theoretical** wall-clock window on the
aligned 1m grid, not `min/max(members)`:

```text
prints = [now - W + 1min, now + 1min)
```

- 09:59 → `[09:30, 10:00)` — same clock window as the A-period.
- 10:00 → `[09:31, 10:01)` — not the A-period.

On a complete 1m grid this coincides with `[min(members), max(members)+1min)`.
A missing interior or edge 1m row must **not** shrink the tick window (§1.5).

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

Reproduced 2026-09-07 on this tree (`compute_profile_levels` +
`compute_apoc_levels`, complete 1m RTH hour, `instrument="ES"`): 09:59
members = 30 bars `09:30…09:59`, `APOC` is **NaN**; 10:00 members =
`09:31…10:00`, `APOC` equals the frozen A-period typical POC (not the
10:00 rolling value). An ETH `09:29` bar is **not** in the 09:59 window
(`timestamp > now-30min`).

### 1.5 Review locks (rev 2 — verified 2026-09-07 against this tree)

| Defect | Live fact | Locked correction |
|---|---|---|
| Invariant “15s remains the bar clock” | 15s is ingest/R12; levels clock is the derived **1m parent** (`compute_all_levels`) | 1m parent = levels clock; 15s = ingest; ticks = side histogram |
| Print window = `min/max(members)` | Mid-gap 1m rows still span min→max (includes gap ticks); a missing **edge** bar shrinks the tape. Quantower custom 30m is wall-clock | Tick/15s print window is a function of `now` and `W` on the aligned grid: `[now-W+1min, now+1min)`. Gaps do not shrink it. Typical still uses surviving 1m members |
| `typical_mvp_15s_v1` as a helper token | `BAR_CANDIDATES` is `{typical_mvp_v1, bar_range_uniform_volume_v1, bar_range_tpo_v1}` — 15s is not in it | Select 15s rows, call `compute_bar_candidate_profile(..., candidate="typical_mvp_v1")`, **label** the result `typical_mvp_15s_v1`. Do not add tokens to `BAR_CANDIDATES` |
| Shared tick helper returns NaN on bad ticks | `compute_tick_last_volume_profile` **raises** `APOCProfileInputError` (off-grid, non-finite, `volume<=0`) | Do not change that helper. RP1 catches → stamp `NaN`. RP2: file ingest fail → all-NaN series; sparse/empty window or unsound ticks in one window → **that bar** `NaN` |
| RP1 “typical at 09:59 equals `compute_profile_levels` APOC” | `APOC` emits only at `timestamp >= RTH_open+30min` (10:00). 09:59 `APOC` is NaN | Typical rolling at 09:59 equals `_compute_a_period_poc(members)`, which equals **`APOC` at 10:00**, not the 09:59 APOC column |
| `profile.py` typical branch “byte-identical” | Adding a source gate changes the file | Do **not** edit `_rolling_poc` **body**. Gate in `compute_profile_levels` / `all.py`: typical still calls existing `_rolling_poc` |
| “keyword-only” source | `compute_all_levels` has no `*`; `apoc_profile_source` is a trailing kwarg with default | New kwargs with defaults; do not insert before existing args (positional shift). Do not add `*` |
| Bar-range 1m **or** 15s undeclared | Mixed clocks cannot share an 8/10 gate | Scorecard bar-proxy column is **1m** `bar_range_uniform_volume_v1`. 15s bar-range is diagnostic only. Never ship `typical_mvp_15s_v1` as a production source |
| 8/10 of an unbounded stamp list | Extra easy stamps could inflate the hit rate | Predeclare **exactly 10** gate stamps. Extra stamps are diagnostic, not in §4.3 |
| Tick columns `Last` | Loader emits `timestamp, price, volume` (`quantower_ticks.py`) | Reuse the loader. Helper requires `price`/`volume`, not `Last` |
| Lookback hardcoded 30min | Product `poc_windows=["30min"]`; library `rolling_windows=None` → `DEFAULT_ROLLING_POC_WINDOWS` = `30min`/`1h`/`4h` | Tick lookback buffer = `max(requested windows)`. Do not hardcode 30min |
| Identity strip only in `api.py` | `LEVELS_APOC_IDENTITY_KEYS` are stripped in `api.py`, `research_identity.py`, and `classic_export.py` | New `LEVELS_ROLLING_POC_IDENTITY_KEYS` must be stripped in **all three**. Add `rolling_poc_profile_source` to `OPTIONAL_LEVELS_SETTINGS` |
| Per-bar `compute_tick_last_volume_profile` as the two-pointer | Helper scans one window; calling it per 1m bar is `O(bars × ticks_in_window)` | RP2 two-pointer maintains `bin → volume` incrementally. Helper is RP1/oracle + sampled-stamp equality only |
| §6 “RP2 = ticks only” vs §4.3 bar-proxy select | Selectable production tokens are tick **or** 1m `bar_range_uniform_volume_v1` | RP2 implements the **one** §4.3 token. RP2-cancel if nothing / Session / Step / TPO / 15s typical |

Do not reopen `_rolling_poc` math, TV3 omit/fail-closed, AP2 APOC source, goldens, or `LEVEL_ENGINE_VERSION` (stays **11**) from an RP PR.

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
3. The **1m parent** remains the levels clock. 15s remains ingest / R12.
   Ticks are a side histogram input, never the simulation bar loop.
4. Missing / malformed / off-grid tick inputs under a future tick source emit
   `NaN`, never typical under a new source identity.
5. Bar-range uniform volume is a **proxy candidate only**. It is not a
   Quantower claim without a written scorecard (AP1: 2/4 on A-period).
6. A 15s typical dump is not a substitute for ticks. AP1 already showed
   finer bars / range-split still missed Quantower POC.

## 3. Candidate table (RP1)

Reuse `apoc_candidates` histogram **builders**, not `BAR_CANDIDATES` as a
closed RP token list. Off-grid reject (no silent snap); inclusive range
bins; volume conservation `VOLUME_CONSERVATION_RTOL` /
`VOLUME_CONSERVATION_ATOL`; lowest-price POC tie (`np.argmax` on an
ascending grid; Quantower tie is observed, not assumed); sparse 1m
coverage = observed rows only for **bar** candidates; empty usable
observations → `NaN` POC.

Do **not** call `select_a_period_rows` for rolling windows. Window
selection is a separate helper. Histogram builders
(`compute_bar_candidate_profile`, `compute_tick_last_volume_profile`) stay
shared. `typical_mvp_15s_v1` is a **label**: run
`compute_bar_candidate_profile(..., candidate="typical_mvp_v1")` on 15s
rows. Do not add that label to `BAR_CANDIDATES` (AP1 contract).

If `compute_tick_last_volume_profile` raises `APOCProfileInputError` for a
stamp, the tick candidate at that stamp is `NaN` (harness catch), not a
crash and not a snap.

| Candidate | Input | Allocation | Purpose |
|---|---|---|---|
| `typical_mvp_v1` | 1m bars in `(now-30min, now]` | Full bar volume at `(H+L+C)/3` | Reproduce production `_rolling_poc` |
| `typical_mvp_15s_v1` | 15s HE bars whose opens fall in the **theoretical** print window | Same typical dump via `candidate="typical_mvp_v1"` | Discriminate “finer typical” vs tick. **Not** a Quantower claim. **Not** a production token |
| `bar_range_uniform_volume_v1` | **1m** members (same as typical). 15s bar-range is diagnostic only | Volume split equally across inclusive tick bins `[low, high]` | AP1 proxy; scorecard column is 1m |
| `bar_range_tpo_v1` | Same **1m** members | One count per touched tick bin; volume ignored | Discriminate TPO vs VAP |
| `tick_last_volume_v1` | Quantower Tick–Tick–Last prints in the theoretical print window (`price`×`volume` via `iter_tick_files`) | Last × Volume | Test true VAP |

**Locked print-window map** (tick / 15s candidates). Must not be a second
*membership* clock, and must not shrink when a 1m row is missing:

```text
members = 1m opens in (now - W, now]          # typical / 1m bar-range
prints  = [now - W + 1min, now + 1min)        # aligned 1m grid; ticks/15s
```

On a complete 1m grid this equals `[min(members), max(members)+1min)`
(09:59 → `[09:30, 10:00)`; 10:00 → `[09:31, 10:01)`). If `09:32` is
absent, **members** skip that bar; **prints** stay `[09:30, 10:00)` at
09:59 (Quantower tape is not dropped because derive dropped a minute).
Do not implement prints as `min/max(members)` — that includes mid-gap
ticks while shrinking on a missing edge bar.

Window math is `pd.Timedelta` on the timestamp values (same as
`_rolling_poc`), not “30 RTH minutes”. DST spring-forward may yield
fewer 1m members; record that as honesty, do not special-case.

RP1 must also record, as diagnostics not production sources:

- Endpoint variants (`(t0, t1]` vs `[t0, t1)`) if Quantower’s custom range is
  inclusive on the right.
- Session-open developing VAP (`dPOC`-shaped) so a Session-profile oracle is
  not silently scored as rolling 30m.

RP1 computes **sampled stamps**, not every 1m bar. Harness output **must**
include RTH 09:59 (A-period overlap check), 10:00 (divergence check), 11:00,
14:00, plus one ETH stamp if the Quantower template includes ETH. Extra
stamps are diagnostic. The §4.3 merge gate uses **exactly 10 predeclared**
stamps (declared in RP1g **before** looking at aggregates). Full-timeline
tick rolling is an RP2 engineering problem (streaming histogram), not an
evidence problem.

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

Written threshold **before** looking at aggregates. Gate set = **exactly
the 10 predeclared stamps** in the scorecard table (extra stamps are
diagnostic and do not enter the 8/10 count):

- **Select tick Last×Volume** only if it hits on ≥ 8 of those 10 stamps
  **and** no 1m bar proxy hits more of those 10.
- **Select a 1m bar proxy** only if it meets 8/10 **and** tick is absent or
  worse; ship it only as a documented bar proxy, never as tick-equivalent.
  The selectable bar token is 1m `bar_range_uniform_volume_v1` only.
- **No cutover** if no candidate meets 8/10, or if the Quantower tool is
  Session-developing / Step-brick / TPO rather than a sliding 30m VAP.
- Failure mode: retain documented typical rolling POC; open a bounded
  settings/window investigation. Do not change `LEVEL_ENGINE_VERSION`.
- `typical_mvp_15s_v1` is never a production source (would put 15s into
  `compute_profile_levels`).

A-period overlap (09:59 typical rolling vs `_compute_a_period_poc(members)`
/ `APOC` **at 10:00**) is a **sanity check of membership**, not a
Quantower hit. Do not compare to the 09:59 `APOC` column (NaN).

## 5. Implementation architecture (locked; RP2 implements only if §4.3 selects)

RP2 implements **exactly one** RP1-selected production source. Until RP1g
writes that selection, this section is the specification, not authorization
to merge engine changes.

### 5.1 Object

`POC_rolling_{window}` under the tick source means:

> POC of Last×Volume prints whose timestamps fall in
> `[now - window + 1min, now + 1min)` on an aligned 1m grid
> (`now` = bar-open timestamp of the row). Binning is
> `instrument_tick_size` (no extra `aggregation_ticks`). Tie = lowest price
> (`np.argmax` on an ascending grid). PIT: prints with
> `now - W + 1min <= ts < now + 1min` only — future ticks with
> `ts >= now+1min` must not change this row.

It is **not** A-period APOC, **not** prior-session `pdPOC`, **not**
session-developing `dPOC`, **not** Quantower Step 30m. Member bars for the
typical path remain `(now - window, now]`.

The 30min window is the Quantower-lock target. `1h` / `4h` inherit the same
algorithm when those `poc_windows` are requested; they are **not** QT-locked
until a separate oracle exists (same honesty as TV week/month bins 8/10).

### 5.2 Keyword and defaults (AP2 posture)

| Item | Lock |
|---|---|
| Settings / StudySpec key | `rolling_poc_profile_source` |
| Library kwarg | `compute_all_levels(..., rolling_poc_profile_source=...)` and `compute_profile_levels(...)` gain **trailing kwargs with defaults** (AP2 `apoc_profile_source` pattern). Do not insert before existing args. Do not add `*` |
| `tick_paths` pass-through | `compute_all_levels` already takes `tick_paths`. RP2 passes it into `compute_profile_levels` for the tick source. Do **not** introduce an `APeriodTickProfileTable`-shaped freeze (every bar has a different window) |
| Omitted key | Implicit `typical_mvp_v1`; pre-RP2 settings hash **unchanged** (`attach_rolling_poc_identity` is a no-op when the key is absent, like `attach_apoc_identity`) |
| Product `DEFAULT_LEVELS_SETTINGS` | **Does not** include the key (farm / Levels page stay typical) |
| `OPTIONAL_LEVELS_SETTINGS` | Add `rolling_poc_profile_source` (same set as `apoc_profile_source`) |
| Production source tokens | `typical_mvp_v1` and **only** the §4.3-selected token (`tick_last_volume_v1` **or** 1m `bar_range_uniform_volume_v1`). Never `typical_mvp_15s_v1` |
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
         incremental bin→volume; same bins / tie / conservation as
         compute_tick_last_volume_profile (do **not** call that helper per bar)
                │
         POC_rolling_* series
```

Forbidden substitutes: `PriorProfileTable`, `APeriodTickProfileTable`,
`select_a_period_rows`, dumping ticks into `_rolling_poc`’s per-bar Python
scan (`O(bars × ticks_in_window)`).

**Sliding algorithm (normative):**

1. Sort 1m opens; sort ticks by timestamp.
2. For each bar `now` in order, member window `(now - W, now]` (typical
   path / diagnostics). Tick print window `[now - W + 1min, now + 1min)`.
3. Advance `left`/`right` pointers only forward over the print window.
   Maintain `bin → volume`. POC = argmax (lowest bin on ties).
4. Empty members or empty positive-volume ticks → `NaN`.
5. Off-grid / non-finite / non-positive tick volume in a window: that **bar**
   is `NaN` (catch `APOCProfileInputError`; do not change the shared helper
   to return NaN). File-layer ingest failure (unreadable / empty
   `tick_paths`) → **all** requested `POC_rolling_*` NaN, matching AP2
   empty-table at the file layer. Sparse hole (no ticks in window) → that
   bar NaN, others proceed.
6. Window may cross CME session open (`eth_start`). Carry a lookback buffer
   of `max(requested windows)` from the previous chunk — product default
   `poc_windows` is `["30min"]`, but library `rolling_windows=None` is
   `30min/1h/4h`. Do not hardcode 30min. Do not clip to RTH.

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

Must not equal VA `tick_source_id` or `apoc_tick_source_id` (different
policy string even on the same files). Strip these keys before
`compute_all_levels` kwargs (new `LEVELS_ROLLING_POC_IDENTITY_KEYS`,
mirror `LEVELS_APOC_IDENTITY_KEYS` in `api.py`, `research_identity.py`,
and `classic_export.py` — all three strip APOC identity today). Add the
source key to `OPTIONAL_LEVELS_SETTINGS` so StudySpec unknown-levels
fail-closed still allows the opt-in. `attach_rolling_poc_identity` is
called from the same sites as `attach_apoc_identity` (`api.py`,
`research_identity.py`).

### 5.5 Point-in-time

Appending future 1m bars or future ticks must not change `POC_rolling_*` at
earlier timestamps. Test with future-shock on both typical (already exists:
`test_r3_point_in_time.py::test_rolling_poc_future_shock`) and tick source.
Current-bar inclusion stays as today: window includes `timestamp == now`
because each engine row is a **completed** bar whose open is `timestamp`
(bar-close confirmed; same limitation as typical). Do not treat `timestamp`
as an intra-bar clock.

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
| RP2 — versioned source opt-in | **Go if RP1g selects `tick_last_volume_v1` or 1m `bar_range_uniform_volume_v1`** | Implement that **one** token |
| RP2-cancel — docs-only “retain typical” | **Go if RP1g selects nothing / Session / Step / TPO / 15s typical** | Honesty; no engine change |
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
| Files | `thesistester/levels/rolling_poc_candidates.py` (**new**); `tests/test_rolling_poc_candidates.py` (**new**); this plan §RP1 implementation record; roadmap/agent one-line status. **May import** `compute_bar_candidate_profile`, `compute_tick_last_volume_profile`, conservation constants from `apoc_candidates.py`. Must **not** add tokens to `BAR_CANDIDATES`. |
| Behavior | Sampled-stamp candidate POCs + auditable histograms. **Zero** change to `_rolling_poc` / `compute_profile_levels` output |
| Public helpers (normative names) | `select_rolling_member_bars(bars, now, window)`; `rolling_print_window(now, window, bar_interval="1min")` (theoretical `[now-W+1min, now+1min)`, **not** min/max of members); `compare_rolling_poc_candidates(...)` |
| Window lock | Members: 1m opens in `(now - W, now]`. Prints: `[now - W + 1min, now + 1min)`. Do **not** call `select_a_period_rows`. Gap test: drop one interior 1m row → members skip it, prints unchanged |
| Candidates | Exact table in §3. Scorecard `bar_range_uniform_volume_v1` is 1m. 15s typical is a labeled typical_mvp_v1 call |
| Diagnostics (not production tokens) | Optional endpoint-variant and session-open developing VAP helpers, clearly named, not in `BAR_CANDIDATES` |
| Env-gated oracle | `THESISTESTER_RP_QT_1M`, `THESISTESTER_RP_QT_TICKS` (optional), `THESISTESTER_RP_QT_15S` (optional; skip 15s candidates if unset), `THESISTESTER_RP_QT_EXPECTED` (CSV: `session_date,stamp_ny,poc` timezone-aware). Skipped in CI. Does **not** fail CI on miss; records numbers |
| Acceptance | See §8.1 |
| Forbidden | `profile.py` production edits; `all.py` / `api.py` / defaults / study schema / Program B; `LEVEL_ENGINE_VERSION`; golden regen; committing desk CSVs |

**RP1 implementation record:** fill in this subsection in the RP1 PR (same
pattern as AP1). Must state: typical candidate equals production
`POC_rolling_30min` at the sampled stamp; 09:59 members == A-period bars
and typical rolling equals `_compute_a_period_poc(members)` / `APOC` at
**10:00** (09:59 `APOC` is NaN); 10:00 members drop 09:30; tick print
window at 10:00 is `[09:31, 10:01)` even if a 1m row is missing; tick
candidate does **not** use `select_a_period_rows`.

### RP1g — scorecard record (docs only)

| Field | Scope |
|---|---|
| Title | `RP1g: record rolling-POC Quantower scorecard` |
| Files | This plan §4.3 result table + go/no-go line; one-line roadmap/agent status |
| Behavior | Write the predeclared threshold outcome. Name the Quantower tool. Select exactly one of: `tick_last_volume_v1` / documented bar proxy / **retain typical (RP2-cancel)** |
| Acceptance | The 10 predeclared gate stamps; tool identity recorded; per-stamp errors; explicit selected token or cancel. Extra stamps do not enter 8/10 |
| Forbidden | Engine edits; treating AP1 4/4 as this scorecard; claiming Step 30m = rolling |

### RP2 — versioned source (merge-gated)

Open **only** after RP1g selects `tick_last_volume_v1` or 1m
`bar_range_uniform_volume_v1`. Implement **that** token, not both.

| Field | Scope |
|---|---|
| Title | `RP2: add versioned rolling-POC profile source` |
| Files | `thesistester/levels/profile.py` (**source gate + trailing `rolling_poc_profile_source` / `tick_paths` kwargs**; do not edit `_rolling_poc` body); **new** `thesistester/levels/rolling_poc_tick.py` if ticks selected (two-pointer incremental histogram + `attach_rolling_poc_identity` + `LEVELS_ROLLING_POC_IDENTITY_KEYS` + source id policy) **or** a bar-proxy module if §4.3 selects 1m `bar_range_uniform_volume_v1` (no two-pointer; still catch `APOCProfileInputError` → bar `NaN`); `thesistester/levels/all.py` (pass `rolling_poc_profile_source` and `tick_paths` into `compute_profile_levels`); `thesistester/levels/defaults.py` (`OPTIONAL_LEVELS_SETTINGS` only); `thesistester/api.py` (forward `tick_paths` when rolling source is tick even if VA parquet present; `attach_rolling_poc_identity`; strip `LEVELS_ROLLING_POC_IDENTITY_KEYS`); `thesistester/research_identity.py` (attach + strip, same as APOC); `thesistester/classic_export.py` (strip); `thesistester/study/schema.py` (unknown levels already use `OPTIONAL_LEVELS_SETTINGS`); `tests/test_rolling_poc_tick_source.py`; living docs listed in §8.2 |
| Behavior | Trailing kwarg with default. Omitted = today’s typical. Selected source = §5.1 object, failure-to-`NaN`. `_rolling_poc` body untouched |
| Acceptance | See §8.2 |
| Forbidden | Default cutover; VA/APOC math; tick VWAP; `dPOC`; Program B YAML; golden regen; Levels-page widget; nested tick scan; `LEVEL_ENGINE_VERSION` bump |

### RP2-cancel — retain typical (docs only; exclusive with RP2)

| Field | Scope |
|---|---|
| Title | `RP2-cancel: retain typical rolling POC` |
| Files | This plan status; honesty one-liners in `ASSUMPTIONS_AND_LIMITATIONS.md` / `METRICS_GLOSSARY.md` / `POINT_IN_TIME_GUARANTEES.md` stating rolling POC remains 1m typical and is not Quantower sliding VAP |
| Behavior | No engine change. Use when §4.3 selects nothing / Session / Step / TPO / 15s typical |
| Forbidden | Quietly shipping a bar proxy under the old name; treating 15s typical as production |

---

## 8. Per-PR acceptance tests

### 8.1 RP1

Must pass:

1. `select_rolling_member_bars` on a complete 09:30–10:29 1m grid: 09:59 →
   30 bars 09:30…09:59; 10:00 → 30 bars 09:31…10:00. An ETH 09:29 bar is
   not a 09:59 member.
2. Typical candidate POC at 09:59 equals `_compute_a_period_poc` on those
   members and equals production `APOC` **at 10:00** on the same fixture.
   09:59 `APOC` is NaN.
3. Typical candidate at 10:00 **differs** from production `APOC` at 10:00 on
   the competing-mode fixture.
4. `compare_rolling_poc_candidates` does not call `compute_profile_levels`
   internally for the tick/bar-range paths (typical may **assert equal** to
   production, not replace it).
5. `rolling_print_window` at 10:00 is `[09:31, 10:01)`. After dropping the
   09:32 1m row, prints at 09:59 stay `[09:30, 10:00)` (do not shrink).
6. Off-grid reject, conservation, inclusive range, lowest-price tie, empty →
   `NaN` — reuse AP1 numeric contracts via shared helpers. Off-grid tick
   stamp → caught `NaN`, not an uncaught `APOCProfileInputError`.
7. Isolation: `compute_profile_levels` `POC_rolling_30min` series-equal
   before/after importing the new module on `tests/test_phase3_levels.py`
   simple dataset (or a copied fixture). VA columns still omitted without a
   table. `_rolling_poc` source is unchanged (`git diff` empty on that
   function).
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
   attached (mirror `tests/test_apoc_tick_source.py` wiring test) **and**
   the rolling tick path consumes those same paths (no second attach, no
   `PriorProfileTable` / `APeriodTickProfileTable` substitute).
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
  select_rolling_member_bars, rolling_print_window(now, window, bar_interval),
  compare_rolling_poc_candidates.
- Import histogram builders from apoc_candidates. Do not call
  select_a_period_rows. Do not edit profile.py / _rolling_poc.
  Do not add tokens to BAR_CANDIDATES. Label 15s typical after calling
  typical_mvp_v1 on 15s rows.
- Print window is [now-W+1min, now+1min), not min/max(members).
- Catch APOCProfileInputError → stamp NaN; do not change the helper.
- Tests in tests/test_rolling_poc_candidates.py covering §8.1 1–8.
- Env-gated oracle skipped in CI (THESISTESTER_RP_QT_*).
- Fill the RP1 implementation record in the plan; one-line roadmap status.

Do not:
- Change _rolling_poc / compute_profile_levels output.
- Add rolling_poc_profile_source.
- Touch VA, APOC production, Program B, goldens, LEVEL_ENGINE_VERSION.
- Commit proprietary desk CSVs.
- Present bar-range as Quantower-compatible.
- Treat 09:59 APOC column as the A-period overlap check (it is NaN).

Regression: typical POC_rolling_30min series-equal on the phase3 simple
dataset; VA omit without a table still holds; test_golden_master.py green.
```

