# Rolling POC Quantower Parity — Investigation and Implementation Plan

**Document type:** Focused investigation + fully scoped implementation plan
**Date:** 2026-09-07 (rev 3 — desk default-tick amendment)
**Status:** **RP2 implemented (this PR).** Desk amendment 2026-09-07: Quantower
has no sliding 30m rolling-POC VAP oracle. RP1g-equivalent decision selects
``tick_last_volume_v1`` as the **production default** (not opt-in). No
typical / bar-proxy fallback. No ticks → refuse when rolling is required
(``rolling POC requires ticks``), not quiet all-NaN as the product path.
**RP2-cancel is not opened.** This is ThesisTester sliding tick VAP, not a
Quantower rolling-widget parity claim.
**Series code:** **RP** (Rolling POC)  
**Related:** `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md` (AP — A-period only);
`docs/TICK_VAP_IMPLEMENTATION_PLAN.md` (TV — prior-session VA only).  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including the
golden-master operational specification (§4.1) and per-PR checklist (§4.2).

**What’s next:** series complete for rolling POC under the desk amendment.
APOC follow-up (2026-09-07): library/product default is tick Last×Volume;
APOC and rolling refuse without ticks like VA. No typical fallback.

## 1. Problem statement and current evidence

### 1.1 Hypothesis (from the APOC series)

AP1 showed that dumping each bar’s full volume onto typical `(H+L+C)/3` misses
Quantower A-period POC, and that Tick–Tick–Last Last×Volume matched 4/4 on the
written Levels2test scorecard. Pre-RP2 `POC_rolling_30min` used that same
typical allocation via `profile._compute_profile` / `_rolling_poc`. The
question was whether rolling / developing POC needs the same tick source.
Desk amendment 2026-09-07 answers **yes** as the production default (no QT
sliding-widget oracle).

### 1.2 What the repository already proves

| Claim | Evidence | Verdict |
|---|---|---|
| Pre-RP2 rolling POC allocated each **derived-1m** bar’s volume to typical `(H+L+C)/3` | `thesistester/levels/profile.py` `_rolling_poc` + typical `prices` | **Confirmed** (dead/non-default after RP2) |
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
| `profile.py` typical branch “byte-identical” | Adding a source gate changes the file | Do **not** edit `_rolling_poc` **body**. Production `compute_profile_levels` does **not** call it (desk default is tick; no typical fallback) |
| “keyword-only” source | `compute_all_levels` has no `*`; `apoc_profile_source` is a trailing kwarg with default | New kwargs with defaults; do not insert before existing args (positional shift). Do not add `*` |
| Bar-range 1m **or** 15s undeclared | Mixed clocks cannot share an 8/10 gate | Scorecard bar-proxy column is **1m** `bar_range_uniform_volume_v1`. 15s bar-range is diagnostic only. Never ship `typical_mvp_15s_v1` as a production source |
| 8/10 of an unbounded stamp list | Extra easy stamps could inflate the hit rate | Predeclare **exactly 10** gate stamps. Extra stamps are diagnostic, not in §4.3 |
| Tick columns `Last` | Loader emits `timestamp, price, volume` (`quantower_ticks.py`) | Reuse the loader. Helper requires `price`/`volume`, not `Last` |
| Lookback hardcoded 30min | Product `poc_windows=["30min"]`; library `rolling_windows=None` → `DEFAULT_ROLLING_POC_WINDOWS` = `30min`/`1h`/`4h` | Tick lookback buffer = `max(requested windows)`. Do not hardcode 30min |
| Identity strip only in `api.py` | `LEVELS_APOC_IDENTITY_KEYS` are stripped in `api.py`, `research_identity.py`, and `classic_export.py` | New `LEVELS_ROLLING_POC_IDENTITY_KEYS` must be stripped in **all three**. Add `rolling_poc_profile_source` to `OPTIONAL_LEVELS_SETTINGS` |
| Per-bar `compute_tick_last_volume_profile` as the two-pointer | Helper scans one window; calling it per 1m bar is `O(bars × ticks_in_window)` | RP2 two-pointer maintains `bin → volume` incrementally. Helper is RP1/oracle + sampled-stamp equality only |
| §6 “RP2 = ticks only” vs §4.3 bar-proxy select | Pre-amendment tension: selectable tokens were tick **or** 1m `bar_range_uniform_volume_v1` | **Superseded 2026-09-07.** Only `tick_last_volume_v1` is a production token. Do **not** open RP2-cancel. Bar-proxy stays comparator-only. |

Do not reopen `_rolling_poc` math, TV3 omit/fail-closed, AP2 APOC source, goldens, or `LEVEL_ENGINE_VERSION` (stays **11**) from an RP PR.

## 2. Locked scope and invariants

### In scope

- Identify the Quantower calculation object (tool + data type + period +
  session template + row size + POC tie) before changing production math.
- Compare versioned allocation candidates on **the same locked window**.
- Desk amendment: RP2 ships `tick_last_volume_v1` as the **production
  default** (§5). No typical / bar-proxy fallback.

### Out of scope (entire RP series unless a later plan amends this file)

- `pd*` / `pw*` / `pm*` tick VAP (TV3 identity).
- APOC / pAPOC production source, defaults, or Program B Wave 7 provenance.
- Tick VWAP (`dVWAP*` / `VWAP_rolling_*` / `prev30mVWAP`).
- Developing `dVAH` / `dVAL` / `dPOC` (parked; not emitted).
- Replacing `15s_primary_derive_1m`.
- Using `PriorProfileTable` or `APeriodTickProfileTable` as a rolling window.
- Golden regeneration. Flipping APOC’s library default (separate follow-up).

### Invariants

1. Production `POC_rolling_*` is tick Last×Volume. Omitted
   `rolling_poc_profile_source` is tick, not typical. No ticks → all-NaN
   columns (present). Never silent typical.
2. TV3 omit/fail-closed VA is unchanged: no ticks → nine VA columns absent;
   named-VA studies still refuse `VA requires ticks`.
3. The **1m parent** remains the levels clock. 15s remains ingest / R12.
   Ticks are a side histogram input, never the simulation bar loop.
4. Missing / malformed / off-grid tick inputs emit `NaN`, never typical.
5. Bar-range uniform volume is a **proxy candidate only**. It is not a
   Quantower claim and is not a production source.
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

> **Superseded by §4.3 Result (desk amendment 2026-09-07).** The 8/10 QT
> gate below was not collectable (no sliding-widget oracle). Failure-mode
> “retain typical / open RP2-cancel” is **not** in force. Production
> default is `tick_last_volume_v1`. Historical protocol kept for audit.

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
- Failure mode *(superseded)*: retain documented typical rolling POC; open
  a bounded settings/window investigation. Do not change
  `LEVEL_ENGINE_VERSION`.
- `typical_mvp_15s_v1` is never a production source (would put 15s into
  `compute_profile_levels`).

A-period overlap (09:59 typical rolling vs `_compute_a_period_poc(members)`
/ `APOC` **at 10:00**) is a **sanity check of membership**, not a
Quantower hit. Do not compare to the 09:59 `APOC` column (NaN).

#### 4.3 Result (desk amendment 2026-09-07)

| Field | Record |
|---|---|
| Tool identity | **Unavailable.** Quantower has no sliding / custom last-30m rolling POC VAP indicator on the desk. |
| Gate stamps | The 10 predeclared QT stamps were **not collectable** (oracle absent). 8/10 is **N/A**. |
| Per-stamp errors | Not scored. No QT rolling export / screenshot / settings exist. |
| `tick_last_volume_v1` | **Selected as production default by desk amendment**, not by an 8/10 QT table. Trust is AP1 Last×Volume math + the locked RP print window. |
| 1m `bar_range_uniform_volume_v1` | **Not selected.** Comparator-only. Not a Quantower claim. |
| `typical_mvp_v1` / 15s typical | **Not selected.** Old typical rolling runs are obsolete. |
| AP1 A-period 4/4 | **Not reused** as this scorecard. Window ≠ A-period. Step 30m / Session / TPO ≠ rolling. |

**Go / no-go line:** **No QT cutover table.** Select **`tick_last_volume_v1` as the default production source** (desk amendment). Do **not** open RP2-cancel. Do **not** retain typical as product default.

## 5. Implementation architecture (locked; RP2 ships desk-selected tick default)

RP2 implements **exactly one** production source: desk-selected
`tick_last_volume_v1` as the **default**. Typical / bar-proxy are not
production tokens. This section is the shipped architecture.

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
| Library kwarg | `compute_all_levels(..., rolling_poc_profile_source=...)` and `compute_profile_levels(...)` gain **trailing kwargs with defaults**. Do not insert before existing args. Do not add `*` |
| `tick_paths` pass-through | `compute_all_levels` already takes `tick_paths`. RP2 passes it into `compute_profile_levels` even when a prior-VA parquet is attached. Do **not** introduce an `APeriodTickProfileTable`-shaped freeze (every bar has a different window) |
| Omitted key | Implicit **`tick_last_volume_v1`**. `attach_rolling_poc_identity` **always** stamps tick identity (not an AP2 no-op). Settings hash is not the pre-RP2 typical-looking hash |
| Product `DEFAULT_LEVELS_SETTINGS` | **Does not** include the key. Identity attach still stamps tick. Without `tick_paths`, columns are all-NaN |
| `OPTIONAL_LEVELS_SETTINGS` | Add `rolling_poc_profile_source` (same set as `apoc_profile_source`) |
| Production source tokens | **`tick_last_volume_v1` only.** `typical_mvp_v1` and bar-proxy raise. Never `typical_mvp_15s_v1` |
| Bar-range / 15s-typical | Comparator-only (RP1 harness). Never a production source |
| `LEVEL_ENGINE_VERSION` | Stays **11**. Identity keys alone invalidate cache (AP2 pattern). Do not leave callers thinking typical is the default |
| Columns | Always emit `POC_rolling_*` for requested windows. Missing / empty / unsound ticks → **`NaN`**, not column omit, not typical fallback |
| Study refuse | **No** `VA requires ticks` analog. Program B / 15s-only studies that omit the key emit **NaN** rolling POC |

### 5.3 Tick path (do not reuse VA / APOC tables)

```text
1m parent bars (clock)
        │
        └─ tick_last_volume_v1  (default; only production path)
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
         POC_rolling_* series  (all-NaN if ticks missing/empty/unsound)

typical_mvp_v1 / `_rolling_poc` ──► dead/non-default helper (body untouched)
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

New keys **always** attached (omitted source is tick, not typical):

| Key | Implicit / explicit tick |
|---|---|
| `rolling_poc_profile_source` | omitted in product YAML; library default `tick_last_volume_v1` |
| `rolling_poc_algorithm_version` | `tick_last_volume_v1` |
| `rolling_poc_allocation` | `last_times_volume` |
| `rolling_poc_tick_source_id` | SHA-256 of tick files **plus** policy `rolling_lookback_v1` and canonical `poc_windows` (`none` when paths are empty) |

Must not equal VA `tick_source_id` or `apoc_tick_source_id` (different
policy string even on the same files). Strip these keys before
`compute_all_levels` kwargs (new `LEVELS_ROLLING_POC_IDENTITY_KEYS`,
mirror `LEVELS_APOC_IDENTITY_KEYS` in `api.py`, `research_identity.py`,
and `classic_export.py` — all three strip APOC identity today). Add the
source key to `OPTIONAL_LEVELS_SETTINGS` so StudySpec unknown-levels
fail-closed still allows the explicit token. `attach_rolling_poc_identity` is
called from the same sites as `attach_apoc_identity` (`api.py`,
`research_identity.py`) and **always** stamps tick identity.

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
| Data page / Help | Honesty: rolling POC is tick Last×Volume; NaN without ticks. Do not require ticks for non-VA studies |
| Program B YAML | **Do not** add the key. Without ticks, rolling POC is **NaN** (not typical). No Wave provenance analog |
| Goldens | **No regen** unless a golden encodes typical rolling (then update only as required by this default cutover). `run_legacy_pipeline` never calls `compute_all_levels` |

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
| RP1g — write §4.3 scorecard into this plan | **Recorded in this PR** | QT oracle unavailable; desk selects tick default |
| RP2 — default tick Last×Volume | **Go (desk amendment)** | Default `tick_last_volume_v1`; no typical fallback |
| RP2-cancel — docs-only “retain typical” | **No-go** | Superseded by the desk amendment |
| Product-default cutover (rolling POC) | **Go (desk amendment)** | Default is tick; no typical fallback |
| Reuse `PriorProfileTable` / `APeriodTickProfileTable` | **No-go** | Wrong object |
| 15s bar-range as Quantower-compatible | **No-go** | AP1 was 2/4; not selected |
| Program B YAML key / `LEVEL_ENGINE_VERSION` bump / golden regen | **No-go** | Identity keys change the hash; engine version stays 11. Program B omits the key → NaN rolling |
| Levels-page source widget | **No-go this series** | Narrow; AP2 had none |
| Developing `dPOC` / tick VWAP | **No-go** | Out of series |

---

## 7. Fully scoped PR series

Merge order: **RP0 → RP1 → RP1g → RP2**. RP2-cancel was **not opened**
(exclusive alternative superseded by the desk amendment). Do not combine
RP1 with RP2. Do not open RP2 and RP1g in parallel.

### RP0 — plan lock

| Field | Scope |
|---|---|
| Title | `RP0: lock Quantower rolling-POC investigation plan` |
| Files | This plan; index-only pointers in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/AGENT_GUIDE.md` |
| Behavior | Documentation only |
| Status | **Landed as the RP0 commit; this document now also scopes RP1–RP2** |
| Forbidden | Engine edits, fixture-data commits, golden regen |

### RP1 — comparator harness

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

**RP1 implementation record:** `rolling_poc_candidates.py` is a sampled-stamp
comparator. It imports `compute_bar_candidate_profile`,
`compute_tick_last_volume_profile`, and conservation constants from
`apoc_candidates.py`. It does **not** call `select_a_period_rows` or
`compute_profile_levels`. It does **not** edit `profile.py` / `_rolling_poc`.
No tokens were added to `BAR_CANDIDATES`. `typical_mvp_15s_v1` is a **label**
after `compute_bar_candidate_profile(..., candidate="typical_mvp_v1")` on 15s
rows in the theoretical print window.

Window lock: members = 1m opens in `(now - W, now]`; prints =
`[now - W + 1min, now + 1min)` via `rolling_print_window(now, window,
bar_interval="1min")`, **not** `min/max(members)`. Scorecard bar-range is
declared `1m` in result metadata (not a Quantower claim).
`APOCProfileInputError` from a builder is caught and stamped `NaN`; the tick
helper is unchanged.

Verified on the competing-mode fixture (complete 09:30–10:29 1m grid; unique
typical per minute; A-period mode at 09:45; competing mode at 10:00):

- Typical candidate equals then-production (pre-RP2) `POC_rolling_30min` /
  dead helper `_rolling_poc` at the sampled stamp (09:59 → 103.75;
  10:00 → 200.00). After RP2, production without ticks is all-NaN; typical
  is not the product path.
- 09:59 members == A-period bars (`[09:30, 10:00)` / 09:30…09:59). Typical
  rolling equals `_compute_a_period_poc(members)` and equals `APOC` at
  **10:00**. 09:59 `APOC` is NaN and is not the overlap check.
- 10:00 members drop 09:30 (09:31…10:00). Typical rolling differs from
  frozen `APOC` at 10:00.
- Tick print window at 10:00 is `[09:31, 10:01)` even if a 1m row is missing
  (interior gap skips the member; prints unchanged). A missing **edge** 09:30
  row at 09:59 also leaves prints `[09:30, 10:00)` — not `min/max(members)`.
  Tick / 15s filtering uses that theoretical interval, not the A-period
  selector.

Env-gated oracle: `THESISTESTER_RP_QT_1M` + `THESISTESTER_RP_QT_EXPECTED`
(`session_date,stamp_ny,poc`); optional `THESISTESTER_RP_QT_TICKS` /
`THESISTESTER_RP_QT_15S`. Skipped in CI. Reports per-stamp MNQ-tick error;
does **not** fail CI on miss. Naive 1m/15s stamps localize as
`America/New_York` (Quantower HE default); naive tick-fallback stamps
localize as UTC (TV1 disk convention). `session_date` is applied to the
stamp clock when present. Proprietary desk CSVs are not committed.

### RP1g — scorecard record (docs; folded into this RP2 PR)

| Field | Scope |
|---|---|
| Title | Folded into `RP2: default rolling POC to tick Last×Volume` |
| Files | This plan §4.3 result table + go/no-go line; roadmap/agent one-liners |
| Behavior | Record desk amendment: QT sliding oracle unavailable; select `tick_last_volume_v1` as default; do not open RP2-cancel |
| Acceptance | Tool identity = unavailable; 10 gate stamps not collectable (8/10 N/A); explicit selected token = `tick_last_volume_v1` (desk amendment, not QT 8/10) |
| Forbidden | Treating AP1 4/4 as this scorecard; claiming Step 30m / Session / TPO = rolling |

**RP1g implementation record:** Accumu 2026-09-07. Quantower has no sliding /
custom last-30m rolling POC VAP indicator, so no 10-stamp QT scorecard can
be collected. 8/10 is N/A. The desk amendment selects
`tick_last_volume_v1` as the **production default**. Tick / 1m bar-range
were **not** selected by a QT table. AP1 A-period 4/4 is not this
scorecard. RP2-cancel is not opened.

### RP2 — default tick Last×Volume (desk amendment)

Desk amendment supersedes “opt-in / omitted=typical”. Implement
`tick_last_volume_v1` as the **default**.

| Field | Scope |
|---|---|
| Title | `RP2: default rolling POC to tick Last×Volume` |
| Files | `thesistester/levels/profile.py` (source gate + trailing kwargs; do **not** edit `_rolling_poc` body); **new** `thesistester/levels/rolling_poc_tick.py` (two-pointer + identity); `all.py`; `defaults.py` (`OPTIONAL_LEVELS_SETTINGS`); `api.py` / `research_identity.py` / `classic_export.py` (attach + strip); `study/schema.py`; `tests/test_rolling_poc_tick_source.py`; living docs |
| Behavior | Default = tick Last×Volume when `tick_paths` present. No ticks / unsound → all-NaN series (columns present). Never typical. `_rolling_poc` retained as a dead/non-default helper. |
| Acceptance | Amended §8.2: default-with-ticks matches RP1 harness tick POC; no ticks → all-NaN; isolation; future-shock; identity ≠ VA ≠ APOC; goldens green |
| Forbidden | Typical fallback; VA/APOC math change; flipping APOC default; tick VWAP; `dPOC`; Program B YAML key; nested tick scan |

**RP2 implementation record:** Production `POC_rolling_*` is two-pointer
Last×Volume on `[now-W+1min, now+1min)`. `compute_profile_levels` /
`compute_all_levels` default `rolling_poc_profile_source=tick_last_volume_v1`.
`attach_rolling_poc_identity` always stamps tick identity (omitted key is
**not** typical; hash is not the pre-RP2 typical-looking hash).
`LEVEL_ENGINE_VERSION` stays **11**; identity keys invalidate cache.
`PriorProfileTable` / `APeriodTickProfileTable` are not substitutes.
`run_experiment` forwards `dataset.tick_paths` even when a VA parquet is
attached. Program B YAML still omits the key; without ticks those studies
emit NaN rolling POC (they do not name it as a factor). Typical
`_rolling_poc` body is unchanged and is not the product path. This is
ThesisTester sliding tick VAP, not a Quantower rolling-widget claim.
APOC library default remains typical (desk wants that flipped next).

### RP2-cancel — retain typical (docs only; exclusive with RP2; **not opened**)

Not executed. Living docs state the tick default, not typical.

| Field | Scope |
|---|---|
| Title | `RP2-cancel: retain typical rolling POC` |
| Files | Would have written honesty one-liners that rolling POC remains 1m typical. **Do not apply** — superseded by RP2. |
| Behavior | No engine change. Use when §4.3 selects nothing / Session / Step / TPO / 15s typical |
| Forbidden | Quietly shipping a bar proxy under the old name; treating 15s typical as production |

---

## 8. Per-PR acceptance tests

### 8.1 RP1

Historical RP1 gate. After RP2, production `POC_rolling_*` without ticks is
all-NaN; typical equality is vs dead helper `_rolling_poc`, not the product
column.

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

1. Omitted / blank `rolling_poc_profile_source` resolves to
   `tick_last_volume_v1`. Explicit `typical_mvp_v1` / bar-proxy **raise**.
2. Default with ticks: sampled stamps match
   `compare_rolling_poc_candidates` tick POC (RP1 harness is the oracle).
3. No ticks / missing file / empty paths: `POC_rolling_*` all-NaN
   (columns present); values **≠** typical `_rolling_poc`; no exception at
   `compute_profile_levels`.
4. Off-grid / unsound tick in a window: that **bar** NaN, not snap.
5. Future-shock: append future bars **and** future ticks; prefix values
   unchanged.
6. `PriorProfileTable` present does not substitute for rolling ticks;
   `APeriodTickProfileTable` does not either. VA join unchanged when a
   table is passed.
7. `run_experiment` still forwards `dataset.tick_paths` when a VA parquet is
   attached (mirror AP2 wiring) **and** the rolling tick path consumes those
   same paths.
8. Unrelated families isolated: session marks, `dVWAP*`, TPO, default APOC
   stay series-equal when only rolling ticks are added.
9. StudySpec unknown key still fail-closed; `rolling_poc_profile_source`
   accepted only as `tick_last_volume_v1`; Program B YAMLs still omit the key.
10. Identity: `attach_rolling_poc_identity` always stamps tick; rolling tick
    source id ≠ VA id ≠ APOC id. Implicit omitted config is tick identity,
    not pre-RP2 typical.
11. Two-pointer complexity: each tick is assigned at most a constant number
    of pointer moves (monotonic left/right), not a full rescan.
12. Goldens green; no regen unless a golden encoded typical rolling (then
    update only as required by this default cutover and document in the PR).
13. Living docs in **this** PR: `ASSUMPTIONS_AND_LIMITATIONS.md`,
    `POINT_IN_TIME_GUARANTEES.md`, `METRICS_GLOSSARY.md`, `ARCHITECTURE.md`,
    this plan’s RP2 implementation record; USER_GUIDE honesty.

---

## 9. Regression-safety checklist (every RP1+ PR)

- Default `POC_rolling_*` is tick Last×Volume. Missing/empty `tick_paths`
  refuse when rolling is required (`rolling POC requires ticks`), not
  quiet all-NaN as the product path. `_rolling_poc` is dead/non-default.
- TV3 intact: no table → no `pdVAH`…`pmPOC`; named VA without ticks still
  raises `VA requires ticks`.
- Default APOC is the same tick Last×Volume object; named/product APOC
  refuses (`APOC requires ticks`). No typical fallback.
- No change to session levels, session VWAP, TPO, signals, fills, or R12.
- `tests/test_golden_master.py` preserved; no RP PR regenerates goldens
  unless a golden encoded typical rolling.
- Honesty docs only in the PR that makes the described behavior true.
- PR body includes a regression-safety paragraph: default is now tick;
  required families refuse without ticks; typical `_rolling_poc` retained
  only as dead/non-default; identity / cache; PIT proof; unaffected families.

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

## Desk amendment record (2026-09-07, refuse follow-up)

- Default remains ``tick_last_volume_v1``.
- Missing/empty ``tick_paths`` refuse when rolling POC is required
  (``rolling POC requires ticks``), like named-VA — not quiet all-NaN as
  the product path.
- No typical fallback. Unsound prints still emit per-bar ``NaN``.
- APOC follow-up done in the same unified tick-default + refuse PR.
- Do not claim Quantower rolling-widget parity. RP2-cancel stays closed.

Regression: typical POC_rolling_30min series-equal on the phase3 simple
dataset; VA omit without a table still holds; test_golden_master.py green.
```

