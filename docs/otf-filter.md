# OTF v1 Behavioral Contract

**Project:** ThesisTester  
**Feature:** Directional One Timeframing (OTF) market-condition filter  
**Contract version:** v1  
**Status:** Approved — specification only; production engine not yet implemented  
**Last updated:** 2026-07-23

## Purpose

This document is the single authoritative specification for OTF v1 behavior in ThesisTester.  
Every implementation, test, and fixture must reference this document and use the exact definitions below.

When a production engine is built (PR 2), it must match every assertion in `tests/test_otf_contract.py` and produce the expected states in `tests/fixtures/otf_fixtures.py`.  If any production behavior differs from this document, the document must be updated and the contract version incremented before the engine is merged.

---

## §1 — Concept

One Timeframing (OTF) is a market-profile concept that measures whether a market is directionally consistent at a given time scale.

- **OTF up:** Each completed higher-timeframe bar makes a strictly higher low than the previous completed bar.  The upside auction is progressive; downside rotations fail to break the prior bar's low.
- **OTF down:** Each completed higher-timeframe bar makes a strictly lower high than the previous completed bar.  The downside auction is progressive; upside rotations fail to break the prior bar's high.
- **Neutral / broken:** Neither condition is met.

OTF is not a conventional "higher highs and higher lows" trend definition.  It focuses specifically on whether counter-directional rotations are failing, not on whether the market is reaching new price extremes.

---

## §2 — State vocabulary

OTF v1 uses exactly four controlled states:

| State | Meaning |
|---|---|
| `up` | An established OTF up condition (see §3.4). |
| `down` | An established OTF down condition (see §3.4). |
| `neutral` | History is available but no directional sequence meets the minimum threshold. |
| `unknown` | Insufficient history to evaluate (first bar of a session, or fewer than two completed bars). |

No other state values are permitted in v1.

---

## §3 — State-transition rules

### §3.1 — Initialization

At the start of each session (see §3.10):

```
up_run   = 0
down_run = 0
state    = unknown
prev_bar = None
```

The first completed bar of a session always produces `unknown` state.

### §3.2 — Up-run counter

At each new completed bar B with previous completed bar P (within the same session):

```
if B.low > P.low:
    up_run += 1
else:
    up_run = 0          # Equal low also resets the counter (see §3.8)
```

### §3.3 — Down-run counter

At each new completed bar B with previous completed bar P (within the same session):

```
if B.high < P.high:
    down_run += 1
else:
    down_run = 0        # Equal high also resets the counter (see §3.8)
```

### §3.4 — State determination

After updating the counters:

```
if up_run >= minimum_consecutive_bars and down_run < minimum_consecutive_bars:
    state = up
elif down_run >= minimum_consecutive_bars and up_run < minimum_consecutive_bars:
    state = down
else:
    state = neutral     # Includes the case where both counters meet the threshold (contradictory)
```

The `else` branch covers:
- Neither counter has reached the threshold.
- Both counters simultaneously meet the threshold (e.g., an extended run of inside bars with progressively higher lows AND lower highs).  This is explicitly `neutral` because the signals are contradictory.

### §3.5 — Neutral state

State is `neutral` when:
- Two or more bars exist within the current session (insufficient history is excluded), AND
- Neither `up_run` nor `down_run` has reached `minimum_consecutive_bars`.

`neutral` is distinct from `unknown`.  Once a second bar is seen, the state is never `unknown` again within that session.

### §3.6 — Sequence break

An OTF sequence breaks at the bar where its counter resets:

- **Up break:** `B.low <= P.low` → `up_run = 0`.  State becomes `neutral` (or `down` if `down_run >= minimum`).
- **Down break:** `B.high >= P.high` → `down_run = 0`.  State becomes `neutral` (or `up` if `up_run >= minimum`).

A broken sequence does not linger.  The bar that causes the break immediately changes state.

### §3.7 — Reversal

A reversal occurs when:

1. One directional sequence is established (e.g., `state = up`).
2. The up sequence breaks at a subsequent bar (`up_run` resets to 0).
3. Over the following bars, the opposite counter builds until it reaches `minimum_consecutive_bars`.
4. State transitions to the opposite direction (e.g., `state = down`).

There is no immediate reversal on a single bar.  The opposite sequence must build independently.

### §3.8 — Equal-high and equal-low handling

Strict inequality is required in both directions:

- `B.low == P.low` is **not** a higher low.  `up_run` resets to 0.
- `B.high == P.high` is **not** a lower high.  `down_run` resets to 0.

Rationale: equal extremes indicate stalled directional momentum, not continuation.  The strict rule prevents ambiguous sequence-length reporting and is consistent with how market-profile practitioners define OTF continuation.

### §3.9 — Insufficient history

`unknown` is returned when fewer than 2 completed bars are available in the current session (i.e., when there is no previous bar to compare against).  This applies to:

- The first completed bar of a session.
- A dataset containing only one row.

`unknown` is the correct signal for downstream code to interpret as "no OTF information available."  It must not be treated as equivalent to `neutral`.

### §3.10 — Session reset

OTF state resets at every session boundary.  The state from the previous session does **not** carry forward.

```
on_new_session():
    up_run   = 0
    down_run = 0
    state    = unknown
    prev_bar = None
```

Session boundaries are determined by the `session_timezone` configuration parameter, which defaults to the exchange's primary timezone (`America/New_York` for US equity-index futures).

Session carry (preserving state across sessions) is not supported in v1.

---

## §4 — Configuration parameters

```python
{
    "enabled": False,
    "timeframes": [],                    # e.g., ["5m", "15m", "30m"]
    "alignment_mode": "all",             # only "all" is supported in v1
    "minimum_consecutive_bars": 3,
    "directional": True,
    "use_completed_bars_only": True,     # required; non-negotiable
    "session_reset": "session",          # only "session" is supported in v1
}
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `False` | When `False`, no OTF filtering is applied and existing behavior is unchanged. |
| `timeframes` | list[str] | `[]` | Selected OTF timeframes.  Must be a subset of `{"5m", "15m", "30m"}`. |
| `alignment_mode` | str | `"all"` | How multiple timeframes are combined.  Only `"all"` is supported in v1. |
| `minimum_consecutive_bars` | int | `3` | Minimum number of consecutive qualifying bars to establish a directional state. |
| `directional` | bool | `True` | Whether the filter is direction-aware (long requires OTF up; short requires OTF down). |
| `use_completed_bars_only` | bool | `True` | Must be `True`.  Use only completed higher-timeframe bars to prevent look-ahead bias. |
| `session_reset` | str | `"session"` | Session-boundary behavior.  Only `"session"` (reset at each session) is supported in v1. |

---

## §5 — Supported higher timeframes

v1 supports exactly three higher-timeframe intervals:

| Label | Bar closes at | Notes |
|---|---|---|
| `5m` | :00, :05, :10, …, :55 | 12 bars per hour |
| `15m` | :00, :15, :30, :45 | 4 bars per hour |
| `30m` | :00, :30 | 2 bars per hour |

The source data must be at a granularity finer than the target timeframe (e.g., 1-minute bars for 5m OTF).  Resampling must use only bars that have closed at or before the signal decision timestamp.

---

## §6 — Completed-bar availability and look-ahead safety

This is the most critical correctness constraint of the OTF implementation.

### §6.1 — Rule

For a signal at timestamp T, the OTF engine may use only completed higher-timeframe bars whose close time is **at or before** T:

```
available_bars = {bar : bar.close_time <= T}
```

The in-progress higher-timeframe bar (whose close time is after T) must not be used.  Its eventual high or low is not known at time T, and using it constitutes look-ahead bias.

### §6.2 — Boundary behavior

A higher-timeframe bar that closes exactly at T (i.e., `bar.close_time == T`) is available for signals at T.

### §6.3 — Signal decision timestamps

| Signal type | Decision timestamp T |
|---|---|
| `touch` | Close of the signal bar |
| `reject` | Close of the signal bar |
| `break` | Close of the signal bar |
| `reclaim` | Close of the signal bar |
| `3c` | Close of the confirmation (third) bar |

### §6.4 — Example

Given a signal at 09:33 and 5-minute OTF:

- The 5m bar covering 09:25–09:30 closed at 09:30 ≤ 09:33 → **available**.
- The 5m bar covering 09:30–09:35 closes at 09:35 > 09:33 → **not available**.
- The eventual high of the 09:30–09:35 bar is not yet known at 09:33.

The OTF state for the signal at 09:33 is computed using the completed 5m bar whose close time is 09:30, not the in-progress bar.

---

## §7 — Timezone and session alignment

- All timestamps must be timezone-aware.
- The session timezone defaults to `America/New_York`.
- Session boundaries are computed in the session timezone.
- A bar from 16:59 ET is in a different session than a bar from 09:30 ET the following day.
- Resampling to 5m, 15m, or 30m must be aligned to session-local clock boundaries, not UTC.

---

## §8 — Directional eligibility

### §8.1 — Single-timeframe eligibility

| Signal direction | OTF state | Filter result |
|---|---|---|
| `long` | `up` | **Pass** |
| `long` | `down` | Reject |
| `long` | `neutral` | Reject |
| `long` | `unknown` | Reject |
| `short` | `down` | **Pass** |
| `short` | `up` | Reject |
| `short` | `neutral` | Reject |
| `short` | `unknown` | Reject |

`neutral` and `unknown` always reject, regardless of signal direction.

### §8.2 — All-timeframe alignment ("all" mode)

A signal passes only if **every selected timeframe** is in the required state for the signal direction:

- For `long`: all selected timeframes must be `up`.
- For `short`: all selected timeframes must be `down`.

A single timeframe in `neutral`, `unknown`, or the opposing directional state rejects the signal.

### §8.3 — Rejection reasons

Every rejected signal must record a deterministic, human-readable rejection reason.  Examples:

```
"15m OTF state is neutral; all timeframes must be up for long"
"30m OTF state is down; all timeframes must be up for long"
"OTF state is unknown; insufficient history"
```

---

## §9 — Rejected signals

Signals rejected by OTF must not be deleted.  They are retained with:

```
otf_filter_enabled:  True
otf_filter_passed:   False
otf_filter_reason:   <reason string>
otf_<tf>_state:      <state per timeframe>
otf_<tf>_sequence_length: <int>
otf_<tf>_reference_timestamp: <pd.Timestamp>
```

This allows post-hoc analysis of how many signals were rejected, for which timeframes, and why.  It is essential for comparing filtered versus unfiltered backtests.

---

## §10 — Regression safety

When `enabled = False` (the default):

```
signal_count  ==  legacy signal_count
trade_count   ==  legacy trade_count
metrics       ==  legacy metrics
```

Existing saved setups without an `otf_filter` block must load and behave exactly as before OTF support was added.

---

## §11 — Output fields

The OTF engine must return the following fields for each signal evaluation:

| Field | Type | Description |
|---|---|---|
| `otf_state` | str | One of `"up"`, `"down"`, `"neutral"`, `"unknown"` |
| `otf_sequence_length` | int | Current run length (up_run or down_run, whichever is active) |
| `otf_reference_timestamp` | pd.Timestamp or None | Timestamp of the last completed HTF bar used for evaluation |

For multi-timeframe integration, these fields are prefixed with the timeframe label (e.g., `otf_5m_state`, `otf_15m_sequence_length`).

---

## §12 — Algorithm versioning

OTF algorithm versioning and configuration hashing are reserved for PR 5 (persistence and versioning).  Do not introduce production version metadata in PRs 1–3.

The contract version identifier (`v1`) is used in fixture files and this document to tie expected states to the specification.  When the specification is amended, increment the version in this document, the fixtures, and the progress log.

---

## §13 — Open questions (resolved for v1)

| Question | Decision | Rationale |
|---|---|---|
| Alignment mode | `all` only in v1 | Conservative directional confirmation; `any` and hierarchical deferred |
| Default enabled state | Disabled | Preserves legacy behavior |
| Completed bars only | Required | Prevents look-ahead bias |
| Minimum sequence length | 3 bars (configurable) | Initial default; subject to statistical validation in Phase 10 |
| Equal-high/equal-low | Strict inequality; break the sequence | Consistent with market-profile convention; avoids ambiguity |
| Insufficient history | Return `unknown` | `neutral` would imply an evaluation was made; `unknown` is more accurate |
| Session reset | Reset at each session | Session carry introduces subtle look-ahead risk when prior-session extremes are not yet tested |
| 5m as entry confirmation | Out of scope for v1 filter logic | Covered by existing trigger timeframe infrastructure |

---

## §14 — Related files

| File | Purpose |
|---|---|
| `docs/otf-filter-roadmap.md` | Implementation tracker with progress log and PR sequence |
| `tests/fixtures/otf_fixtures.py` | Deterministic OHLCV fixtures and expected-state test vectors |
| `tests/test_otf_contract.py` | Fixture-integrity and contract-consistency tests |
| `tests/test_otf_baseline.py` | Regression baseline tests (OTF absent/disabled) |
| `thesistester/engine/otf.py` | Production engine (to be created in PR 2) |
