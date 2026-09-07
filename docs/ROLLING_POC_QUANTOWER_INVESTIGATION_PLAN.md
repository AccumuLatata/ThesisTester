# Rolling POC Quantower Parity — Investigation Plan

**Document type:** Focused investigation plan  
**Date:** 2026-09-07  
**Status:** **RP0 locked.** Allocation hypothesis confirmed in-repo. Quantower
object is **not** identified. Production tick opt-in is **no-go** until a
written rolling-window scorecard exists.  
**Series code:** **RP** (Rolling POC)  
**Related:** `docs/APOC_QUANTOWER_INVESTIGATION_PLAN.md` (AP — A-period only);
`docs/TICK_VAP_IMPLEMENTATION_PLAN.md` (TV — prior-session VA only).  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, including the
golden-master operational specification (§4.1) and per-PR checklist (§4.2).

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
- If evidence supports a change, a later PR may add a versioned explicit
  rolling-POC source. Product default remains typical until that gate passes.

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

## 5. Go / no-go

| Decision | Verdict | Why |
|---|---|---|
| RP0 — lock this plan | **Go** | Allocation confirmed; window ≠ A-period; QT object unnamed |
| RP1 — comparator harness + env-gated oracle | **Go** | Required. AP1 transfer is insufficient. No production output change |
| RP2 — versioned tick opt-in analogous to AP2 | **No-go until the §4.3 scorecard selects `tick_last_volume_v1`** | No rolling oracle in-repo; QT Step 30m is APOC’s cousin, not this column; per-bar tick scan is a different architecture from `APeriodTickProfileTable` |
| Cut over product default | **No-go** | Even after a selected source, default stays typical (AP2 posture) |
| Reuse `PriorProfileTable` | **No-go** | Full-session prior freeze |
| Present 15s bar-range as Quantower-compatible | **No-go** without §4.3 | AP1 already 2/4 on a simpler window |

If RP1 later selects ticks, RP2 must be a new plan amendment: keyword-only
`rolling_poc_profile_source`, sampled-stamp PIT tests, failure-to-`NaN`,
identity keys separate from VA and APOC, and a streaming/windowed histogram
that does **not** nest a full tick scan inside `_rolling_poc`’s Python loop.
That work is not authorized by this document.

## 6. Fully scoped PR series

### RP0 — plan lock (this PR)

| Field | Scope |
|---|---|
| Title | `RP0: lock Quantower rolling-POC investigation plan` |
| Files | This plan; index-only pointers in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`, and `docs/AGENT_GUIDE.md` |
| Behavior | Documentation only; no level calculation, cache, default, study, or UI change |
| Acceptance | Window identity, candidate table, oracle protocol, source gate, and RP2 no-go are explicit |
| Forbidden | Engine edits, fixture-data commits, result reruns, golden regeneration |

### RP1 — comparator (authorized after RP0)

| Field | Scope |
|---|---|
| Title | `RP1: add rolling-POC profile comparison harness` |
| Files | New pure window-select helper (or extend `apoc_candidates` **without** teaching it A-period defaults); tests; optional env-gated desk-oracle test; this plan status |
| Behavior | Compute candidates at sampled stamps; **do not** modify `_rolling_poc` output |
| Acceptance | Membership test (09:59 typical rolling == typical APOC helper on a complete 1m A-period; 10:00 diverges); conservation / off-grid / tie tests reused; production `POC_rolling_30min` series-equal on isolation fixtures; VA omit/fail-closed unchanged |
| Forbidden | `profile.py` production cutover, defaults, `LEVEL_ENGINE_VERSION`, Program B, golden regen |

### RP2 — selected-source implementation

**Not authorized.** Open only after §4.3 selects a source in writing.

## 7. Regression-safety checklist

Every RP1+ PR must:

- Leave `compute_profile_levels` typical `POC_rolling_*` value-identical when
  the new source is omitted.
- Preserve TV3: no table → no `pdVAH`…`pmPOC`; named VA without ticks still
  raises `VA requires ticks`.
- Assert rolling-POC work does not alter session levels, session VWAP, TPO,
  default APOC, signals, or fills.
- Run and preserve `tests/test_golden_master.py`; no RP PR regenerates golden
  artifacts.
- Update honesty docs only in the PR that makes the described behavior true.
- Include a PR-body regression-safety paragraph identifying default behavior,
  source identity/cache handling, point-in-time proof, and unaffected
  families.
