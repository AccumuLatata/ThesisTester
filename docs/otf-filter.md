# OTF v1 Behavioral Contract

**Project:** ThesisTester  
**Feature:** Directional One Timeframing (OTF) market-condition filter  
**Contract version:** v1  
**Status:** Approved — contract implemented through PR 5 (research-mode integration)  
**Last updated:** 2026-07-26

## Purpose

This document is the single authoritative specification for OTF v1 behavior in ThesisTester.  
Every implementation, test, and fixture must reference this document and use the exact definitions below.

The production implementation must match every assertion in `tests/test_otf_contract.py`, `tests/test_otf.py`, and `tests/test_otf_filter.py`. If any production behavior differs from this document, the document must be updated and the contract version incremented before changes are merged.

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
- A dataset containing only one **completed HTF bar** within the current session.

`unknown` is the correct signal for downstream code to interpret as "no OTF information available."  It must not be treated as equivalent to `neutral`.

### §3.10 — Session reset

OTF state resets at every trading-session boundary.  The state from the previous trading session does **not** carry forward.

```
on_new_session():
    up_run   = 0
    down_run = 0
    state    = unknown
    prev_bar = None
```

**Trading-session date convention**

Session boundaries are determined using `thesistester/levels/session_date.py::trading_session_date(local_ts, eth_start)`, the canonical ThesisTester session-date helper, applied in the instrument's exchange-local timezone (`exchange_tz`, default `America/New_York`).

For instruments with a configured `eth_start` (e.g., ES and NQ futures with `eth_start = "18:00"`):

- A bar whose exchange-local time is **at or after** `eth_start` belongs to the **next calendar date's** trading session (e.g., Monday 22:00 ET belongs to Tuesday's trading session).
- A bar whose exchange-local time is **before** `eth_start` belongs to the **same calendar date's** trading session (e.g., Tuesday 00:30 ET also belongs to Tuesday's trading session).
- **Midnight is not a trading-session boundary.** A futures session started at 18:00 ET on Monday evening continues through midnight and into Tuesday morning without resetting OTF state.
- The true session boundary occurs at `eth_start` on the next trading day (e.g., 18:00 ET on Tuesday marks the start of Wednesday's session).

The `trading_session_date` for a bar is the date label produced by the `trading_session_date()` helper, not the calendar date of the bar's UTC or local timestamp.

**Example (ES futures, eth_start = "18:00", exchange_tz = "America/New_York")**

| Bar timestamp (ET) | Calendar date | `trading_session_date` |
|---|---|---|
| 2026-01-05 22:00 (Mon) | 2026-01-05 | 2026-01-06 (Tue) |
| 2026-01-05 23:00 (Mon) | 2026-01-05 | 2026-01-06 (Tue) |
| 2026-01-06 00:00 (Tue) | 2026-01-06 | 2026-01-06 (Tue) |
| 2026-01-06 00:30 (Tue) | 2026-01-06 | 2026-01-06 (Tue) |
| 2026-01-06 18:00 (Tue) | 2026-01-06 | 2026-01-07 (Wed) ← boundary |

OTF state is continuous across midnight (bars at 22:00 Mon through 00:30 Tue are all in the Tuesday session).  The session boundary and OTF reset occur at 18:00 ET on Tuesday.

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
| `minimum_consecutive_bars` | int | `3` | Number of consecutive qualifying bar comparisons required to establish a directional state.  With the default of 3, the state first becomes directional at the 4th bar of a session (one anchor bar plus three subsequent qualifying comparisons). |
| `directional` | bool | `True` | Whether the filter is direction-aware (long requires OTF up; short requires OTF down). |
| `use_completed_bars_only` | bool | `True` | Must be `True`.  Use only completed higher-timeframe bars to prevent look-ahead bias. |
| `session_reset` | str | `"session"` | Session-boundary behavior.  Only `"session"` (reset at each trading-session boundary) is supported in v1. |

Canonical setup normalization rules used by `thesistester.setup`:

- Missing `otf_filter` in legacy setups is treated as the canonical disabled default block.
- `None`/`null` `otf_filter` is treated as canonical disabled defaults.
- Canonical timeframe labels are `5m`, `15m`, `30m`; aliases `5min`, `15min`, `30min` are accepted and normalized through `normalize_otf_timeframe()`.
- `enabled=True` requires at least one timeframe.
- Duplicate timeframes after alias normalization are invalid.
- `minimum_consecutive_bars` must be an integer `>= 1`; `bool` is invalid.
- v1 policy values are fixed: `alignment_mode="all"`, `directional=True`, `use_completed_bars_only=True`, `session_reset="session"`.
- Disabled configs normalize to one deterministic representation:
  `{"enabled": False, "timeframes": [], "alignment_mode": "all", "minimum_consecutive_bars": 3, "directional": True, "use_completed_bars_only": True, "session_reset": "session"}`.

---

## §5 — Supported higher timeframes

v1 supports exactly three higher-timeframe intervals:

| Label | Bar closes at | Notes |
|---|---|---|
| `5m` | :00, :05, :10, …, :55 | 12 bars per hour |
| `15m` | :00, :15, :30, :45 | 4 bars per hour |
| `30m` | :00, :30 | 2 bars per hour |

Canonical public OTF timeframe labels are `5m`, `15m`, and `30m`.  The pure PR 2 engine accepts `5min`, `15min`, and `30min` as backward-compatible aliases, but they are aliases only and are normalized internally before calling `resample_ohlcv()`.  The single authoritative normalization helper is `normalize_otf_timeframe()` exported from `thesistester.engine.otf`; both `calculate_otf_state()` and `apply_otf_filter()` delegate to this helper so callers do not need their own alias tables.

The source data must be at a granularity **strictly finer** than the target timeframe (e.g., 1-minute bars for 5m OTF).  Using a source interval equal to the target timeframe produces no resampling and is not supported by OTF v1.  The production engine in PR 2 must validate that the source interval is strictly finer than each selected OTF timeframe, and that the target timeframe is exactly divisible by the inferred source interval.  When the source interval cannot be inferred safely from the input timestamps, the pure engine must reject the input rather than guessing completion.  Resampling must use only bars that have closed at or before the signal decision timestamp.

---

## §6 — Completed-bar availability and look-ahead safety

This is the most critical correctness constraint of the OTF implementation.

### §6.1 — Timestamp definitions

Source rows in ThesisTester are **start-labelled** bars.  For an inferred source
interval `Δ`, a source row labelled `source_bar_start_timestamp` covers the
half-open window `[source_bar_start_timestamp, source_bar_start_timestamp + Δ)`
and becomes final at `source_bar_close_timestamp = source_bar_start_timestamp + Δ`.

Three distinct timestamps govern every higher-timeframe bar:

| Term | Definition |
|---|---|
| `bar_start_timestamp` | The timestamp of the first source-interval bar included in the resampled HTF bar.  This is also the **row label** produced by `pandas.DataFrame.resample()` (which uses left-labeled, left-closed buckets by default). |
| `bar_close_timestamp` | `bar_start_timestamp + timeframe_duration`.  This is when the bar is fully formed and its OHLCV values are final. |
| `availability_timestamp` | Equal to `bar_close_timestamp`.  A bar is available for OTF evaluation only after it has closed. |

**Critical:** The resampled row label (`bar_start_timestamp`) must never be interpreted as proof that the bar was available at that label.  A production engine must calculate `bar_close_timestamp = bar_start_timestamp + timeframe_duration` to determine availability.

**PR 2 timestamp approach:** The production OTF engine will preserve the pandas start-label convention while adding an explicit `bar_close_timestamp` (and equivalently `availability_timestamp`) column derived by adding the timeframe duration to each row label.  This preserves compatibility with existing ThesisTester resampling output and makes availability unambiguous.

### §6.2 — Rule

For a signal at timestamp T, the OTF engine may use only completed higher-timeframe bars whose `availability_timestamp` is **at or before** T:

```
available_bars = {bar : bar.availability_timestamp <= T}
                ≡ {bar : bar.bar_close_timestamp <= T}
                ≡ {bar : bar.bar_start_timestamp + timeframe_duration <= T}
```

The in-progress higher-timeframe bar (whose `bar_close_timestamp` is after T) must not be used.  Its eventual high or low is not known at time T, and using it constitutes look-ahead bias.

Because the source rows are start-labelled, the production engine must compare
`bar_close_timestamp` with the **latest source-bar availability**, not with the
last observed source row label:

```python
latest_source_availability_timestamp = max(source_bar_start_timestamp + source_interval)
completed_htf_bar = bar_close_timestamp <= latest_source_availability_timestamp
```

An HTF bucket is complete only when its expected source coverage is fully present:

- The first expected source row is present.
- The final expected source row is present.
- Source timestamps inside the bucket are continuous at the inferred interval.
- The bucket contains exactly `target_duration / source_interval` source rows.

Missing-data buckets are excluded.  A large gap must not falsely complete a bar.

### §6.3 — Boundary behavior

A higher-timeframe bar that closes exactly at T (i.e., `bar.bar_close_timestamp == T`) is available for signals at T.

Example: with 1-minute source data, the row labelled 09:04 becomes available at
09:05.  Therefore, source rows labelled 09:00, 09:01, 09:02, 09:03, and 09:04
fully complete the 5-minute bucket labelled 09:00 and closing at 09:05.  No
separate 09:05 source-row sentinel is required.

### §6.4 — Signal decision timestamps

| Signal type | Decision timestamp T |
|---|---|
| `touch` | Close of the signal bar |
| `reject` | Close of the signal bar |
| `break` | Close of the signal bar |
| `reclaim` | Close of the signal bar |
| `3c` | Close of the confirmation (third) bar |

The OTF decision must occur at the signal decision timestamp T, not at trade entry time.

PR 3 defines one deterministic selector for signal-decision timestamps:

- Use `trigger_timestamp` when present and non-null.
- Otherwise fall back to `timestamp`.

This applies to base and non-base simple triggers, and to base/non-base `3c`
rows under current signal semantics.

### §6.5 — Bucket semantics

Resampled HTF bars use left-closed, left-labeled buckets.  In ThesisTester, `thesistester.data.resample.resample_ohlcv()` delegates to `pandas.DataFrame.resample()` on a timezone-aware `timestamp` index and preserves that index timezone.  Bucket boundaries therefore follow the input index's wall-clock timezone, not a separate UTC-anchored labeling scheme.  With exchange-local input, the labels land on exchange-local :05/:15/:30 boundaries.

Bucket identity is based on the actual timezone-aware resampler label (i.e. the
distinct absolute instant), not on a naive local clock string.  Across DST
fall-back transitions, `01:00 -0400` and `01:00 -0500` are different buckets
and must never be merged.  Across spring-forward transitions, nonexistent local
times are not fabricated; a bucket can close at `03:00 EDT` immediately after
starting at `01:55 EST` because five absolute minutes have elapsed.

| Timeframe | Example bucket | `bar_start_timestamp` | `bar_close_timestamp` | Availability |
|---|---|---|---|---|
| `5m` | 09:25–09:30 | 09:25 | 09:30 | signal T ≥ 09:30 |
| `15m` | 09:15–09:30 | 09:15 | 09:30 | signal T ≥ 09:30 |
| `30m` | 09:00–09:30 | 09:00 | 09:30 | signal T ≥ 09:30 |

Current helper behavior is wall-clock aligned rather than independently session-anchored: if the first source bar arrives at 18:02 ET, the first 5m bucket is still labeled 18:00 ET and is therefore a partial bucket.  PR 2 uses the conservative policy of discarding such partial first-session buckets, and it also excludes any other bucket whose expected source coverage is incomplete.  The same complete-source-coverage rule applies across DST transitions; repeated fall-back buckets stay distinct by offset, and spring-forward gaps do not create synthetic rows.

### §6.6 — Example

Given a signal at 09:33 and 5-minute OTF (source: 1-minute bars):

- The 5m bucket starting at 09:25 has `bar_close_timestamp = 09:30 ≤ 09:33` → **available**.
- The 5m bucket starting at 09:30 has `bar_close_timestamp = 09:35 > 09:33` → **not available** (in progress).
- The resampled row label "09:30" does NOT indicate the bar was available at 09:30; availability is at 09:35.
- The eventual high of the 09:30–09:35 bar is not yet known at 09:33.

The OTF state for the signal at 09:33 is computed using the completed 5m bar with `bar_start_timestamp = 09:25` and `bar_close_timestamp = 09:30`, not the in-progress bar.

---

## §7 — Timezone and session alignment

- Timestamps may be timezone-aware, or timezone-naive with an explicit timezone supplied so they can be localized before OTF processing.
- The exchange-local timezone is the instrument's `exchange_tz` property (default `America/New_York` for ES/NQ futures).
- Trading-session boundaries are computed using `trading_session_date(local_ts, eth_start)` from `thesistester/levels/session_date.py`, applied in the exchange-local timezone.
- For futures instruments with a configured `eth_start` (e.g., `"18:00"` for ES/NQ), the session begins in the evening of the prior calendar day.  A bar timestamped 22:00 ET on Monday and a bar timestamped 00:30 ET on Tuesday both belong to Tuesday's trading session.
- Midnight (00:00 ET) is not a trading-session boundary for futures instruments with `eth_start` set.
- `thesistester.data.resample.resample_ohlcv()` preserves the timezone of the input `timestamp` column.  With exchange-local source data, HTF labels remain in the exchange-local timezone.
- The current helper is exchange-local wall-clock aligned.  It is not separately anchored to session start beyond normal clock alignment.
- For ES/NQ futures with `eth_start = "18:00"` ET, the session open still lands on clean 5m, 15m, and 30m boundaries because 18:00 is evenly divisible by those intervals.
- Across daylight-saving transitions, the timestamp index keeps the exchange-local timezone and the HTF labels follow local clock behavior (for example, spring-forward jumps from 01:55 EST to 03:00 EDT; fall-back repeats the 01:00 hour with the new offset).
- DST bucket identity is based on distinct timezone-aware instants.  Repeated fall-back local times retain their UTC offsets and are not merged; spring-forward nonexistent local times are not fabricated.

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

The PR 3 eligibility filter runs **after candidate signal generation** and
**before any explicit consumer chooses accepted signals for trade simulation**.
`generate_signals()` remains candidate-only, and `simulate_trades()` remains
execution-only.

Signals rejected by OTF must not be deleted. The filter returns:

1. Accepted signals.
2. OTF-rejected signals.

Both outputs preserve original candidate row content and `signal_id` values.
OTF rejection is a separate concept from 3c `void` status and from execution
skip reasons produced by exposure policy.

Rejected signals are retained with:

```
otf_filter_enabled:  True
otf_filter_passed:   False
otf_filter_reason:   <reason string>
otf_<tf>_state:      <state per timeframe>
otf_<tf>_sequence_length: <int>
otf_<tf>_reference_timestamp: <pd.Timestamp>
```

Per-timeframe metadata columns are emitted only for the selected timeframe set
for that invocation; unselected timeframes are not implied/evaluated.

For each selected timeframe, PR 3 aligns OTF state causally using:

```text
availability_timestamp <= decision_timestamp
```

using backward/as-of matching only (never forward-filling future rows). If no
completed OTF bar is available yet, state is `unknown`, sequence length is `0`,
and reference timestamp is `NaT`.

Rejected rows must carry deterministic non-empty reasons identifying the first
failing timeframe in caller-selected order. Accepted rows must have
`otf_filter_reason = None`.

This allows post-hoc analysis of how many signals were rejected, for which
timeframes, and why. It is essential for comparing filtered versus unfiltered
backtests.

---

## §10 — Regression safety

When `enabled = False` (the default):

```
signal_count  ==  legacy signal_count
trade_count   ==  legacy trade_count
metrics       ==  legacy metrics
```

Existing saved setups without an `otf_filter` block must load and behave exactly as before OTF support was added.

PR 3 disabled-path contract:

- `apply_otf_filter()` validates only that `enabled` is a boolean before returning.
- All timeframe, `alignment_mode`, `minimum_consecutive_bars`, `session_reset`, signal direction, timestamp, and source-data validation is skipped.
- All candidate signals are returned as accepted.
- Rejected output is empty.
- The OTF state engine is not called.
- Per-timeframe metadata is not added when no timeframe is selected.
- Legacy candidate population, ordering, and values are preserved.

PR 3 enabled-empty-signals contract:

When `enabled=True` and the `signals` DataFrame has zero rows:

- Configuration and selected-timeframe validation is still performed (invalid config still raises).
- The function returns two empty DataFrames (accepted and rejected) with identical schemas.
- The schema includes all original signal columns plus `otf_signal_decision_timestamp`, per-selected-timeframe metadata (`otf_<tf>_state`, `otf_<tf>_sequence_length`, `otf_<tf>_reference_timestamp`), and `otf_filter_enabled`, `otf_filter_passed`, `otf_filter_reason`.
- Metadata columns for unselected timeframes are absent.
- No signal direction or timestamp columns are required.
- Source OHLCV data is not inspected.
- The OTF state engine is not called.

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

## §12 — Algorithm versioning and deterministic identity

PR 4 introduces explicit configuration identity metadata while keeping trade/signal
execution behavior unchanged:

- OTF algorithm semantic version constant: `OTF_ALGORITHM_VERSION = 1` in `thesistester/engine/otf.py`.
- Deterministic OTF config hash: `compute_otf_config_hash(config)` in `thesistester/persistence/local_store.py`.
- Hash payload includes both:
  - normalized canonical `otf_filter` config
  - `OTF_ALGORITHM_VERSION`
- Hashes are stable across dictionary key ordering.
- Timeframe aliases hash identically to canonical labels.
- Legacy-missing `otf_filter` and explicit canonical disabled defaults hash identically.
- Enabled/disabled, timeframe selection/order, and threshold differences hash differently.

Timeframe order policy for identity:

- PR 4 treats timeframe order as identity-significant and preserves caller-selected order in normalized enabled configs.
- Rationale: rejection reasons are deterministic in selected-timeframe order, so preserving order maintains reproducible audit identity.

### Strict invalid-config identity policy

- **Missing `otf_filter`** → resolves to canonical disabled defaults (legacy-safe).
- **Explicit valid `otf_filter`** → normalizes to canonical form; aliases resolve to canonical labels.
- **Explicit invalid `otf_filter`** → `normalize_otf_filter_config` raises `ValueError`; hashing is aborted.
- Invalid explicit OTF configuration is **never** silently hashed as disabled. This prevents malformed or enabled configurations from colliding with the canonical disabled identity.
- Only the absent/null field resolves to disabled defaults — an explicit but malformed block always fails validation.
- UI surfaces (Setup Builder, Signals page) may catch `ValueError` at call sites, display a user-facing blocker or warning, and disable operations that require a trusted OTF identity. They must not overwrite malformed state silently or claim it is the same as disabled.

### Research-artifact fingerprint integration (deferred)

PR 4 implements OTF identity for setup and signal-settings fingerprints only. OTF identity is **not** yet embedded in:

- Final research artifacts or report outputs
- Grid-search result metadata
- Walk-forward evaluation outputs
- Exports

Research-artifact fingerprint integration is complete as of PR 5.

The contract version identifier (`v1`) remains the behavior-spec version for this
document/fixtures and is distinct from `OTF_ALGORITHM_VERSION`.

### PR 4 non-integration boundary

Setup Builder and Signals surfaces may display stored OTF configuration metadata,
algorithm version, and config hash, but PR 4 did **not** wire OTF into standard
signal generation/backtest/grid/walk-forward/report/export execution paths.

Persistence compatibility note:

- Setup persistence schema version remains unchanged (`SETUP_SCHEMA_VERSION = 1`).
- Legacy setup files without `otf_filter` continue to load.
- New setup saves include normalized canonical OTF configuration metadata.

---

## §13b — PR 5 Research-Mode Integration

PR 5 wires the configured OTF eligibility output into standard backtests, grid search,
walk-forward diagnostics, and reporting/export metadata. It does not add OTF parameter
optimization, new alignment modes, incomplete-bar modes, session carry, or statistical
release-gate conclusions. Existing research behavior remains unchanged when OTF is disabled.

### Shared integration helper

`thesistester/engine/otf_integration.py` provides one shared, deterministic integration
entry point so filter logic is not duplicated across pages or modes.

```python
apply_configured_otf_filter(
    *,
    source_df: pd.DataFrame,
    candidate_signals: pd.DataFrame,
    setup_config: dict | None = None,
    signal_settings: dict | None = None,
    last_signal_setup: dict | None = None,
    session_timezone: str | None = None,
    eth_start: str | None = None,
) -> OtfFilterResult
```

The returned `OtfFilterResult` exposes:

| Field | Description |
|---|---|
| `candidate_signals` | Original unmodified candidate signals (deep copy) |
| `accepted_signals` | OTF-accepted candidates (or all when disabled) |
| `rejected_signals` | OTF-rejected candidates (or empty when disabled) |
| `otf_filter_config` | Resolved effective OTF configuration dict |
| `otf_filter_enabled` | Boolean — whether OTF was active |
| `otf_algorithm_version` | `OTF_ALGORITHM_VERSION` value |
| `otf_config_hash` | Canonical hex hash of the effective config |
| `candidate_signal_count` | Total input signals |
| `otf_accepted_signal_count` | Accepted after filtering |
| `otf_rejected_signal_count` | Rejected after filtering |

### OTF config resolution precedence

When resolving the effective OTF configuration for a research execution, the following
priority order is used (first match wins):

1. `signal_settings["otf_filter"]` — explicit key present in signal settings.
2. `signal_settings["setup_snapshot"]` — effective OTF from signal-run snapshot.
3. `last_signal_setup` — effective OTF from last signal generation setup.
4. `setup_config` — active setup config effective OTF.
5. Canonical disabled defaults.

Invalid explicit OTF config always raises `ValueError`; it is never silently treated as
disabled (strict identity policy from PR 4).

### Standard backtest integration

Before calling `simulate_trades()`, the backtest page:

1. Resolves effective OTF config for the current signal set / setup context.
2. Applies OTF filtering once using the shared integration helper.
3. Passes only `accepted_signals` to `simulate_trades()`.
4. Stores original candidates and rejected rows separately for audit.

Session state keys established by the backtest page:

| Key | Description |
|---|---|
| `otf_filter_result` | Full `OtfFilterResult` object |
| `otf_filter_summary` | Summary dict with counts and metadata |
| `otf_candidate_signals` | Original unmodified candidates |
| `otf_accepted_signals` | OTF-accepted signals |
| `otf_rejected_signals` | OTF-rejected signals |
| `backtest_otf_filter` | Summary dict stored on the backtest result |

`st.session_state["signals"]` is **never** overwritten; generated candidate signals are
always preserved as-is.

When OTF is disabled, `simulate_trades()` receives exactly the same rows it received
before PR 5. Trade tables, equity curves, summaries, and skipped-signal behavior are
unchanged.

### Grid-search integration

OTF filtering is applied **once** before the SL/TP grid runs. Every SL/TP combination
uses the same accepted signal set. Recomputing per-cell would be incorrect and expensive.

Grid results include OTF metadata for reporting:

| Metadata | Description |
|---|---|
| `otf_filter_enabled` | Whether OTF was active |
| `otf_candidate_signal_count` | Total candidates before filtering |
| `otf_accepted_signal_count` | Accepted signals used for all cells |
| `otf_rejected_signal_count` | Rejected candidates |
| `otf_config_hash` | Hex hash of the effective config |
| `otf_algorithm_version` | `OTF_ALGORITHM_VERSION` |

The `grid_otf_filter` session key stores OTF metadata for the current grid run.

When OTF is disabled, grid output is identical to pre-PR 5 output.

### Walk-forward integration

Walk-forward OTF filtering is fold-local to prevent future-data leakage.

**Config validation before fold processing:**
`run_walk_forward_sl_tp()` validates and normalizes the configured OTF block via
`normalize_otf_filter_config()` before any fold is processed.  If the OTF config
is explicitly invalid (e.g., `enabled=True` with no timeframes, or an unsupported
timeframe label), `ValueError` is raised immediately and no fold results are
produced.  This preserves the strict invalid-config identity policy established in
PR 4 — invalid explicit OTF config is never silently converted into fold-level
rejected signals.

For each fold:

- Training signals are filtered using only the training OHLCV slice as `source_df`.
- Test signals are filtered using only the test OHLCV slice as `source_df`.
- OTF state from later folds never influences earlier fold evaluations.
- If a fold slice has insufficient source history for OTF state evaluation (fewer than 2 bars, or timestamps that cannot produce a trustworthy inferred source interval), all fold candidate signals are treated as OTF `unknown` and therefore rejected. The fold does not crash.  Full-dataset or future OTF state is never used to rescue short folds.
- Only expected "insufficient fold-local OTF history" errors are handled (matched against `_EXPECTED_OTF_INSUFFICIENT_HISTORY_PATTERNS`).  Unexpected `ValueError` instances are re-raised.
- If all train candidates are OTF-rejected, the fold receives `status = "no_train_candidate"` — the same deterministic behavior as having no train signals.

Fold metadata includes OTF counts where practical:

- `train_otf_candidate_count`, `train_otf_accepted_count`, `train_otf_rejected_count`
- `test_otf_candidate_count`, `test_otf_accepted_count`, `test_otf_rejected_count`
- `otf_filter_enabled`

When OTF is disabled, walk-forward output is identical to pre-PR 5 output.

### Reporting and export metadata

`build_research_artifact()` includes an `"otf_filter"` section:

```json
"otf_filter": {
  "available": true,
  "enabled": true,
  "config": {"enabled": true, "timeframes": ["15m", "30m"], ...},
  "algorithm_version": 1,
  "config_hash": "...",
  "candidate_signal_count": 100,
  "accepted_signal_count": 70,
  "rejected_signal_count": 30,
  "rejection_rate": 0.30,
  "applied_scopes": ["backtest", "grid", "walk_forward"]
}
```

The section distinguishes four states:

| `available` | `enabled` | Meaning |
|---|---|---|
| `true` | `true` | OTF was active; counts reflect actual filtering |
| `true` | `false` | OTF was explicitly disabled; all signals passed through |
| `false` | — | OTF data not available (no backtest result in session) |

When metadata is partial (e.g., only walk-forward OTF data is present without full
signal counts), count fields such as `candidate_signal_count`, `accepted_signal_count`,
and `rejected_signal_count` may be `None` / unavailable.  The markdown report and
Report/Export UI render these as `—` (not `"None"`).  Zero counts render as `0`.

Research artifacts also include an `"otf_rejected_signals"` table in the `"tables"`
section when rejected signals are present.

Markdown reports include a dedicated OTF section summarizing enabled/disabled status,
selected timeframes, algorithm version and config hash, candidate/accepted/rejected
counts, rejection rate, and the disabled-regression guarantee.

### Signal distinction guarantee

OTF rejections are tracked and displayed separately from:

- **Exposure-policy skipped signals** — signals not traded due to open-position limits.
- **3c `void` status** — signals voided by the 3c pattern engine.

These three categories are stored in separate session state keys and reported separately
in both the UI and artifact metadata.

### Disabled regression guarantee

When OTF is disabled or absent:

- `simulate_trades()` receives exactly the same rows as before PR 5.
- Grid cells use exactly the same signal population as before PR 5.
- Walk-forward folds contain exactly the same signals as before PR 5.
- Report/artifact content for non-OTF sections is unchanged.

The disabled path short-circuits before any OTF engine calls, timeframe normalization,
or signal inspection.

---

## §13 — Open questions (resolved for v1)

| Question | Decision | Rationale |
|---|---|---|
| Alignment mode | `all` only in v1 | Conservative directional confirmation; `any` and hierarchical deferred |
| Default enabled state | Disabled | Preserves legacy behavior |
| Completed bars only | Required | Prevents look-ahead bias |
| Minimum sequence length | 3 qualifying comparisons (configurable) | Initial default; subject to statistical validation in Phase 10 |
| Equal-high/equal-low | Strict inequality; break the sequence | Consistent with market-profile convention; avoids ambiguity |
| Insufficient history | Return `unknown` | `neutral` would imply an evaluation was made; `unknown` is more accurate |
| Session reset | Reset at each trading-session boundary using `trading_session_date()` | Session carry introduces subtle look-ahead risk when prior-session extremes are not yet tested |
| Futures session boundary | `eth_start` (e.g., 18:00 ET for ES/NQ); midnight is NOT a boundary | Matches ThesisTester's existing instrument-aware session model in `thesistester/levels/session_date.py` |
| 5m as entry confirmation | Out of scope for v1 filter logic | Covered by existing trigger timeframe infrastructure |
| HTF bar timestamp labeling | PR 2 will add explicit `bar_close_timestamp` alongside pandas start labels | Preserves existing resampling convention while making availability unambiguous |
| Equal source/target interval | Not supported in OTF v1; source must be strictly finer | Resampling equal intervals produces no useful higher-timeframe information; PR 2 must validate |

---

## §15 — PR 6 Release-Gate Documentation

**Status:** PR 6 — OTF statistical validation diagnostic tooling and release-gate documentation.
Real-dataset OOS confirmation, drift-review sign-off, and release approval remain open
(see `docs/otf-filter-roadmap.md` Definition of done).

### OTF default state

OTF remains **disabled by default** in all research modes.  Enabling OTF requires an
explicit user action in the Setup Builder and is never automatic.

### Validation methodology

PR 6 adds a fixed five-configuration comparison matrix evaluated on a chronological
train/OOS split.  The matrix compares:

1. **no_otf** — OTF filter disabled (baseline)
2. **otf_15m** — 15m only
3. **otf_30m** — 30m only
4. **otf_15m_30m** — 15m + 30m
5. **otf_5m_15m_30m** — 5m + 15m + 30m

All enabled configurations use OTF v1 defaults:
- `alignment_mode: all`
- `minimum_consecutive_bars: 3`
- `session_reset: session`

### Anti-overfit rules

- **Train/OOS split is chronological** (default 70/30).  No shuffling.
- **Selection (train_rank, is_train_selected) uses train metrics only.**
- **OOS metrics must never influence configuration selection.**
- **Do not select an OTF configuration based on full-dataset results.**
- Results are labeled as diagnostic.  The UI, markdown report, and JSON artifact
  all include warnings that results are not proof of edge.

### Interpreting reduced trade count

An OTF-enabled configuration that produces fewer trades is not necessarily better.
Lower trade count reduces statistical power and makes all metrics less reliable.
It is also not inherently worse.  Do not interpret trade-count reduction as a signal
in either direction without adequate sample size in both periods.

### OOS evaluation priority

OOS performance is the evaluation view.  Train metrics are used for ranking/selection
only.  A configuration that looks better in train but worse in OOS is a warning sign
of potential overfit.

### Multiple-comparison caution

Comparing five configurations against a baseline inflates the risk of spurious results.
Any apparent improvement in a single OTF configuration over no-OTF in OOS should be
treated with extra caution.

### Minimum sample-size caution

OTF filtering reduces the number of accepted signals and therefore the number of
simulated trades.  With very few trades in either the train or OOS period, all
metrics (expectancy, win rate, profit factor) are unreliable.  The trade-count
diagnostic from Phase 8 applies to each period independently.

### No real user dataset available

PR 6 cannot make a true business or statistical release recommendation because no
real user dataset is available in the repository.  Do not fabricate validation
conclusions.  The OTF validation matrix is a tool for the user to evaluate with
their own data; it is not a pre-evaluated result.

### Release-gate criteria

Release approval requires that all of the following are true:

| Criterion | Status |
|---|---|
| Existing disabled behavior unchanged | ✅ Verified by regression tests |
| OTF uses completed bars only | ✅ Enforced by engine; tests in test_otf.py |
| Historical states remain append-data / future-shock invariant | ✅ Tested in test_otf.py::TestLookaheadSafety |
| OTF-rejected signals are inspectable | ✅ Stored in session state; available for CSV export |
| One shared implementation used across research modes | ✅ `apply_otf_filter()` via `apply_configured_otf_filter()` |
| OTF config / version / hash present in artifacts | ✅ `otf_config_hash`, `otf_algorithm_version` in all results |
| Legacy setups load | ✅ Backward-compatible persistence; no schema bump required |
| OOS validation tooling available and diagnostic | ✅ `run_otf_validation_matrix()` in `otf_validation.py` |
| OOS validation complete on real user dataset | ⏳ Open — no real user dataset in repo |
| Regression / drift-safety review sign-off | ⏳ Open — prior engine tests exist; formal PR 6 sign-off pending |
| No unsupported OTF mode enabled | ✅ Only `alignment_mode: all`, `session_reset: session` in v1 |

---

## §14 — Related files

| File | Purpose |
|---|---|
| `docs/otf-filter-roadmap.md` | Implementation tracker with progress log and PR sequence |
| `tests/fixtures/otf_fixtures.py` | Deterministic OHLCV fixtures and expected-state test vectors |
| `tests/test_otf_contract.py` | Fixture-integrity and contract-consistency tests |
| `tests/test_otf_baseline.py` | Regression baseline tests (OTF absent/disabled) |
| `tests/test_otf_filter.py` | PR 3 OTF eligibility-filter validation and regression tests |
| `tests/test_otf_integration.py` | PR 5 research-mode integration tests |
| `tests/test_otf_validation.py` | PR 6 OTF validation matrix tests |
| `thesistester/engine/otf.py` | Production OTF state engine (PR 2) |
| `thesistester/engine/otf_filter.py` | Pure PR 3 eligibility-filter application layer |
| `thesistester/engine/otf_integration.py` | PR 5 shared integration helper (`apply_configured_otf_filter`) |
| `thesistester/analytics/otf_validation.py` | PR 6 OTF validation matrix helper |
| `thesistester/analytics/walk_forward.py` | Walk-forward with fold-local OTF filtering |
| `thesistester/reporting.py` | Research artifacts and markdown reports with OTF metadata |
