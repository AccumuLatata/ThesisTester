# ThesisTester audit Slice 1 — Data, time, session identity

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390).
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/test_loader.py`, `test_vendor_loaders.py`, `test_derive.py`, `test_rolls.py`, `test_15s_primary_persistence.py`, `test_data_page_helpers.py`, `test_signals_trigger_timeframe_dst.py` — **126 passed**.
**Goldens:** not used as correctness proof. Slice 1 has no golden-master ingest suite; vendor fixture identity checks prove *this fixture matches this aggregation*, not that vendor math is universally correct.

This file is the Slice 1 deliverable. Later slices must treat the **locked contracts** in §8 as given, and the **open items** as still unverified outside this layer.

---

## 1. Architecture of the data layer

### 1.1 What this layer owns

The data layer turns an explicit vendor/CSV upload into **canonical exchange-TZ OHLCV** plus a clock `session` tag. It does **not** compute levels, signals, fills, or OTF state.

```text
explicit format_profile + source_tz + target_tz
        │
        ▼
load_ohlcv  (thesistester/data/loader.py)     ← R17 sole adapter
        │  vendor/tick → 1m bars (capture profiles)
        │  naive → localize(source) → convert(target)
        │  aware → convert(embedded) → target  (source_tz ignored)
        ▼
REQUIRED_COLUMNS: timestamp, open, high, low, close, volume
        │
        ├─ primary / Sample ──────────────────────────────┐
        │                                                │
        ├─ 15s_primary_derive_1m (Quantower HE only)     │
        │     prepare_15s_source_for_derivation          │
        │     derive_complete_parent_ohlcv (v2 observed) │
        │     parent = canonical `data`                  │
        │     source attached as subtimeframe_data       │
        │                                                │
        ├─ legacy dual-upload (1m primary only)          │
        │     optional lower CSV → conservative R12 gate │
        │                                                │
        ▼                                                ▼
tag_session(instrument)  → session ∈ {RTH, ETH}   (clock 09:30–16:00)
        │
        ▼
session_state / api.run_experiment
        │
        ├─ roll_policy / roll_validation   (diagnostics only; no price rewrite)
        ├─ resample preview                (1min…1D; no upsample)
        └─ display_timezone                (export copy only; engine unchanged)
```

There is **no** `vendor/` package. Profiles live in `loader.FORMAT_PROFILES`. Vendor fixtures live in `tests/fixtures/vendor/`.

### 1.2 Two composers (same functions, different gates)

| Path | Entry | Ingest composer | Fatal OHLCV gate |
|---|---|---|---|
| Classic UI | `pages/1_Data.py` | `load_ohlcv` → `tag_session`; 15s mode via `_prepare_15s_primary_dataset` | **15s-primary parent:** fail-closed. **Legacy primary:** *not* fail-closed — validation is warning-only. Lower dual-upload: fail-closed on fatals / OHLC mismatch. |
| Headless | `api.load_dataset` / `_load_experiment_data` / `_load_15s_primary_experiment_data` | same loader + `tag_session` | `load_dataset` treats `duplicate_timestamps`, `missing_values`, `high_below_low`, `open_close_outside_range`, `negative_volume` as fatal. Gaps are not fatal. |

`api.preview_resampled_ohlcv` is a bounded resample **without** `tag_session`. The Data-page preview re-tags via `cached_resample_and_tag`.

### 1.3 Two clocks that must not be inverted

| Clock | Function | Rule | Written by Data page? |
|---|---|---|---|
| `session` | `data.sessions.tag_session` | Exchange-local wall clock in `[rth_start, rth_end)` → `RTH`, else `ETH`. Uses `rth_start`/`rth_end` only (`09:30`/`16:00`). **Does not use `eth_start`.** | Yes, on every install path |
| `trading_session_date` | `levels.session_date.trading_session_date` | Exchange-local date; if `local.time >= eth_start` (`18:00`), date += 1 day. Empty `eth_start` → calendar date. Midnight is not a CME reset. | **No** |

All four instrument presets (`ES`/`NQ`/`MES`/`MNQ`) share `America/New_York`, RTH `09:30–16:00`, `eth_start=18:00`. Micros differ only in `point_value` (MES `$5`, MNQ `$2`).

### 1.4 Timezone triple

| Token | Meaning | Mutates engine bars? |
|---|---|---|
| `source_timezone` | Localize **naive** timestamps only. Default: NT → `UTC`; else instrument `exchange_tz`. | Yes, on naive files |
| `exchange_timezone` / `target_tz` | Canonical engine TZ after convert | Yes (the stored `timestamp`) |
| `display_timezone` | `timezone_display.py`; export/display copy | **No.** `convert_dataframe_timestamps_for_display` copies; naive export columns localize to canonical first and emit a warning |

`TIMEZONE_OPTIONS`: `America/New_York`, `UTC`, `Europe/Berlin`, `Europe/London`, `America/Chicago`. Data page has **no** display-TZ widget; `ensure_display_timezone` seeds it from exchange TZ.

### 1.5 SIA / RunSpec ingest tokens (note only)

Closed allow-list on `api.validate_run_spec` / study schema:

`dataset.path`, `instrument`, `source_timezone`, `exchange_timezone`, `format_profile`, `subtimeframe_path`, `subtimeframe_format_profile`, `ingestion_mode` (`primary` | `15s_primary_derive_1m`).

Omit `ingestion_mode` → **primary**. `15s_primary_derive_1m` requires `quantower_history_exporter` and **rejects** `subtimeframe_path`. Studies Build first-visit default is 15s-primary; classic API/CLI default is not. Studies does not walk `pages/1_Data.py`.

---

## 2. Must-answer questions

### Q1. Are timezone-naive vs aware CSV paths fully fail-closed for mixed files?

**Mostly fail-closed; not wrapped as `DataValidationError`; pandas 3 also rejects valid mixed-offset aware files.**

`load_ohlcv` (`loader.py`) after `pd.to_datetime(..., format="mixed")`:

- If `df["timestamp"].dt.tz is None`: `tz_localize(source)` then `tz_convert(target)`. Nonexistent / ambiguous DST → `DataValidationError`.
- Else: `tz_convert(target)`. **`source_tz` is ignored** (tested: `test_timezone_aware_timestamps_ignore_source_timezone`).

**Homogeneous files**

| File | Behavior | Evidence |
|---|---|---|
| All naive | Localize to `source_tz` (or NT default UTC / target) | `test_naive_source_timezone_converts_to_target_timezone` |
| All aware, **one** offset / UTC | Convert embedded → target; source selector unused | `test_timezone_aware_timestamps_ignore_source_timezone` |
| All naive, **wrong** source TZ | **Silent wrong localize** (e.g. ET printed as naive + `source_tz=UTC` → 05:30 ET). Documented operator contract, not mixed-file. | Runtime: `2026-06-02 09:30:00` + UTC → `05:30-04:00` |

**Mixed files (pandas 3.0.5 runtime)**

| Mix | Result | Exception |
|---|---|---|
| Naive + aware (`09:30` and `09:31-04:00`) | Does **not** load | raw `ValueError`: `Mixed timezones detected. Pass utc=True...` |
| Aware `+00:00` + aware `-04:00` | Does **not** load | same raw `ValueError` |
| Aware `-05:00` + `-04:00` (DST spring-forward pair) | Does **not** load on **canonical** path | same raw `ValueError` |
| Same DST pair via vendor profile | **Loads** — profile path UTC-normalizes before canonical re-entry | `loader._read_explicit_profile` comment + `test_quantower_history_exporter_profile_handles_dst_offset_change` |

The canonical path does **not** pass `utc=True` into `to_datetime`. Vendor profiles serialize `pd.to_datetime(..., utc=True).astype(str)` before re-calling `load_ohlcv`, precisely so DST-crossing offsets do not hit this pandas 3 trap.

`derive_complete_parent_ohlcv` separately fail-closes naive sources (`test_timezone_naive_source_fails_closed`).

**Bad case:** a researcher uploads a DST-crossing **canonical** CSV whose stamps already carry `-05:00`/`-04:00`. Load dies with a pandas message that tells them to pass `utc=True` — an option the public API does not expose. Data page catches `(DataValidationError, ValueError)` so the UI shows the error; it is still not a typed ingest error. **No test covers mixed naive/aware or mixed-offset canonical CSVs.**

**Verdict:** mixed naive/aware does not silently convert. Fail-closed is real. It is **not** fully product-grade: exception type is wrong, and pandas 3 mixed-offset aware (including honest DST files) is over-closed on the canonical path only.

---

### Q2. Does 15s-primary duplicate resolution ever drop a conflicting group, or only OHLC-identical?

**Only OHLC-identical (including exact copies). Conflicting OHLC fail-closed. Native 1m is never auto-deduped.**

`prepare_15s_source_for_derivation` (`loader.py`):

1. `validate_ohlcv`; other fatals (`missing_values`, `high_below_low`, `open_close_outside_range`, `negative_volume`) abort **before** resolve.
2. If any group is not `ohlc_identical_group`, `resolve_ohlc_identical_duplicates` raises `DataValidationError` → wrapped `ValueError` (`conflicting OHLC cannot be resolved`).
3. Policy `ohlc_identical_keep_lowest_volume`: keep the lowest-volume row (`mergesort` then `iloc[0]`).

Shared by Data `_prepare_15s_primary_dataset` and `api._load_15s_primary_experiment_data`. Audit lands in `ingestion_provenance`.

Legacy dual-upload: fail-closed until the operator clicks **Use OHLC-identical duplicates for lower-timeframe replay only**. Same resolver; same conflict abort.

**Bad case:** two 15s rows at `09:30:00` with highs `101` vs `103` → `ValueError` / UI error; no parent is installed (`test_prepare_15s_source_ohlc_conflict_fails_closed`, `test_api_15s_primary_ohlc_conflict_source_duplicates_fail_closed`).

Volume-only conflict (same OHLC, different volume) **is** resolved by dropping the higher volume. That is intentional and audited.

---

### Q3. Do roll diagnostics ever get treated as adjusted continuous prices downstream?

**No, not in this layer. R7 never rewrites OHLC.**

`rolls.validate_roll_metadata` / `compute_roll_gaps` sort a **copy**, compute `next_open - previous_close`, return a dict. Input frame is unchanged (`test_validate_roll_metadata_does_not_mutate_input_dataframe`; runtime confirmed).

Data page stores `roll_policy` + `roll_validation` in `session_state` and shows gaps. `api.validate_roll_assumptions` is read-only. Consumers in-tree: `reporting.py` (export text), `assistant.tools` (same facade). **No** `engine/` / `levels/` / `analytics/` import adjusts prices from roll gaps.

`segmented_contracts` always appends: *“R7 does not adjust OHLC prices across roll gaps; metrics may include roll discontinuities.”*

**Bad case:** operator selects `external_continuous` + `back_adjusted`. ThesisTester records the declaration. Uploaded closes are used as-is. If the CSV was *not* actually back-adjusted, roll gaps sit inside every downstream metric. That is honesty risk, not a silent adjuster.

---

### Q4. Does `tag_session` (clock RTH) ever disagree with `trading_session_date` (18:00) in a way pages/engine mix?

**They disagree by design. The Data page does not mix them. Later stages use both for different jobs.**

Runtime (ES, `America/New_York`):

| Local stamp | `session` | Calendar date | `trading_session_date` |
|---|---|---|---|
| Mon 17:00 | ETH | Mon | **Mon** |
| Mon 18:00 | ETH | Mon | **Tue** |
| Mon 18:30 | ETH | Mon | **Tue** |
| Tue 00:30 | ETH | Tue | Tue |
| Tue 09:29 | ETH | Tue | Tue |
| Tue 09:30 | RTH | Tue | Tue |
| Tue 15:59 | RTH | Tue | Tue |
| Tue 16:00 | ETH | Tue | Tue |

Disagreement window: **calendar 16:00–24:00 and 00:00–09:30** are ETH; **18:00–24:00** already belong to the **next** CME date. The 16:00–18:00 ETH pocket is still *today’s* trading date.

**Who writes what**

- Data / `api.load_dataset` / 15s-primary: `tag_session` only. Summary metrics count `session==RTH/ETH`. No `trading_session_date` column.
- Levels (out of math scope, contract only): `session` = RTH membership (`dVWAP_RTH`, TPO, APOC, OR, pRTH_*). `trading_session_date` = CME grouping (`pd*`, `dVWAP`, profile day key, prev30m brackets, WFA/OTF later). If `session` is missing, several families re-call `tag_session`.
- Session flatten (ASSUMPTIONS): **same-calendar-day RTH-style**, not ETH overnight / not `trading_session_date`. Slice 4 must not treat flatten as CME-session close.

**Bad case if mixed:** grouping Monday 18:30 ETH bars by calendar Monday (or by `session==ETH` as if one overnight bag) attaches them to the wrong CME date vs `pdHigh` / `dVWAP` / WFA session folds. Data page itself does not do that. Slice 2+ must not use `session` as a date key.

---

### Q5. Source TZ selector vs embedded offset vs display TZ: any silent conversion?

**Three explicit rules; one silent operator footgun; display never mutates engine data.**

1. **Naive + selector:** localize to selected `source_timezone`, convert to instrument `exchange_tz`. Changing the selector on a naive file **changes** bar instants. Documented in the Data-page help string.
2. **Aware + selector:** selector is ignored; embedded offset/zone wins (`test_timezone_aware_timestamps_ignore_source_timezone`).
3. **Display TZ:** copy-convert for export (`test_artifact_export_uses_display_timezone_for_timestamp_columns` in `test_phase9_reporting.py`, out of named set). Runtime: engine series identity preserved; display tz becomes `Europe/Berlin` on the copy.
4. **Databento:** `ts_event` ns UTC → `tz_convert(target)`. `source_tz` unused.
5. **NinjaTrader default:** naive bars treated as UTC (`_default_source_timezone`). A NT file whose clock is already ET, left on the UTC default, **silently** shifts 4–5 hours. Profile default is documented; not a mixed-file bug.
6. **Vendor re-entry:** UTC string round-trip is an internal normalize, not a second research TZ.

No path converts engine `data` to `display_timezone` in place.

---

### Q6. Vendor profiles (Quantower, NinjaTrader, Sierra, Databento, tick/second): aggregation, missing bars, DST, MNQ/MES

R17: **explicit profile only**. Wrong profile → missing-column `DataValidationError` (`test_vendor_profile_must_be_explicit`). ThesisTester does not sniff headers.

| Profile | Parse | Aggregation | Missing bars | DST | Notes |
|---|---|---|---|---|---|
| `canonical` | comma CSV, aliases (`Date Time`/`DateTime`/`Time left`, `Volume(from bar)`) | none | not filled; `significant_gaps` warning | naive: localize fail-closed on ambiguous/nonexistent; **aware mixed offsets fail pandas 3** | Dot-dates `d.m.yy` forced `dayfirst` |
| `quantower_history_exporter` | `;` + `Time left` | none (already bars) | not filled | UTC-normalize then canonical — DST offset change works | **Only** profile allowed for 15s-primary |
| `ninjatrader` | `;` headerless; 6 fields = bars, 3/5 = capture | capture → 1m floor | empty minutes omitted | same localize rules; default source **UTC** | NT fixture `20260602 133000` + UTC → `09:30-04:00` |
| `sierra_intraday` | `Date`+`Time` or timestamp; `Last`→`close` | none | not filled | localize | Missing required cols fail-closed |
| `databento_trades` | `action==T`; `ts_event` ns UTC; price ÷ 1e9 if ≥ 1e7 | tick → 1m floor first/max/min/last, volume=sum `size` | empty minutes omitted | UTC→target | Bid/ask kept on **raw sidecar only**; not R12 / not spread |
| `tick_capture` / `second_capture` | `timestamp,price,volume` | same 1m floor | empty minutes omitted | localize | Identical aggregators |

**Instrument presets:** MES/MNQ share ES/NQ session clocks and `tick_size=0.25`. Point values `$5` / `$2` (`test_micro_futures_presets_match_cme_contract_point_values`). Session tagging does not special-case micros.

**Capture raw** is stored as `raw_data` on the Data page for NT/Databento/tick/second. ASSUMPTIONS: raw bid/ask are **not** used for spread or R12. Engine sees 1m canonical only.

**Vendor 1m ≠ derived 1m.** `test_quantower_vendor_15s_derives_and_reconciles_with_r12` proves *this* 15s fixture’s derived parent equals *this* 1m fixture. That is identity on a complete, hand-built pair — not a general vendor-correctness proof. Live Quantower 1m vs 15s often diverge in volume (hence VWAP/POC). `DataIdentity` hashes the resulting frame; modes are different datasets.

---

### Q7. R12 subtimeframe coverage/reconcile: can incomplete lower-TF data pass, upsample, or silently fall back?

**Incomplete can pass (conservative attach). Upsample is refused. Silent fallback is not on the Data page; interval inference can still mis-label sparse dual-upload.**

**Coverage/reconcile contract** (`engine/intrabar.py` — data contract only):

- Strict (`prepare_subtimeframe_context`): every parent must have exactly `parent/sub` sub-bars, exact timestamps, finite valid OHLC, and first/max/min/last OHLC within `tick_size * 1e-6`. Else raise. **Volume is not reconciled.**
- Conservative (`prepare_subtimeframe_conservative_context`): incomplete / misaligned → `fallback_reasons` (not replayed). Invalid OHLC or OHLC mismatch still fatal.
- `inspect_subtimeframe_compatibility`: read-only issue table. Data page uses it only when conservative **raises**. Never patches bars (ASSUMPTIONS / ARCHITECTURE R12).

**Upsample:** `resample_ohlcv` returns the original frame when `target_interval <= base_interval` (runtime: 5min→1min identity). `_resolve_bar_intervals` requires strictly finer exact multiple.

**15s-primary**

- Sparse on-grid minutes **retained** in canonical `data` (v2). Off-grid minutes **dropped** (absent from parent, diagnostic only).
- R12 postcondition uses **declared** `1min` / `15s`. Gap-mode inference on one-print-per-minute sources sees `1min` and would raise `strictly finer` without overrides (`test_one_print_per_minute_passes_declared_interval_r12_postcondition`).
- Incomplete coverage **passes** conservative prepare; `fallback_reasons` populated; UI shows sparse diagnostics. Strict `subtimeframe` later requires complete minutes (Slice 4).

**Legacy dual-upload (Data page)**

- `_load_subtimeframe_upload` uses conservative prepare **without** declared intervals.
- Incomplete coverage **passes** with an explicit warning + `subtimeframe_fallback_parent_bars` (`test_load_subtimeframe_upload_accepts_incomplete_bars_for_conservative_model`).
- OHLC mismatch **rejects** and clears loaded lower data (`test_load_subtimeframe_upload_rejects_parent_ohlc_mismatch`).
- **Inference hazard:** a 30s-majority sparse 15s file infers `30s` → `expected_count=2`. Conservative may accept a 2-bar group as “complete” vs a 30s grid, not vs a 15s grid. One-print-per-minute infers `1min` and fail-closes. 15s-primary avoids this via declared intervals; API `run_experiment` also prefers provenance `source_interval` so sparse 15s does not “poison later UI Backtest/Grid/WFO” (comment at `api.py` ~2747).

**API dual-upload (`dataset.subtimeframe_path`)**

- `load_dataset` only (fatal OHLCV). **No** coverage/reconcile at load. Incomplete lower frames are attached. Engine-time model decides (Slice 4).

**Not silent on Data page:** warnings + captions. **Can pass incomplete:** yes, by contract, for conservative. **No upsample. No empty-bar synthesis.**

---

### Q8. Resample / derive 15s→1m: OHLC correctness, volume, session tags, future leakage

**Derive (v2) — locked aggregation**

For each exchange-local minute with ≥1 unique on-grid open in `{ :00, :15, :30, :45 }`:

```text
timestamp = minute open (fold-preserving floor)
open      = first observed open
high      = max high
low       = min low
close     = last observed close
volume    = sum volume   ← can differ from vendor-native 1m
```

Off-grid stamps → drop that minute (`timestamp_misalignment`). Sparse → keep + `incomplete_coverage`. Empty slots **never** synthesized. Cadence: on-grid gaps must be exact 15s multiples; off-grid-only sources fail (`test_invalid_source_cadence_fail_closed`).

DST: local-minute floor preserves fold (`test_exchange_local_bucketing_across_dst_spring_forward` / `fall_back`).

**Future leakage:** parent `m` uses only stamps inside `m`. Appending a later minute does not change prior parents or sparse/dropped tables (`test_future_shock_append_does_not_change_prior_parents_or_diagnostics`). No lookahead.

Session tags: applied **after** derive via `tag_session` on parent and source separately. Not inherited from a child-majority vote.

**Resample (`resample_ohlcv`)**

- Supported: `1min`, `5min`, `15min`, `30min`, `1h`, `4h`, `1D`.
- Agg: first/max/min/last; volume `sum(min_count=1)`; drop all-NaN buckets.
- No upsample.
- Labels follow pandas timezone-aware resample (exchange-local wall clock). 5/15/30min + DST labels tested (`test_resample_ohlcv_uses_exchange_local_wall_clock_boundaries`, `test_resample_ohlcv_preserves_local_timezone_labels_across_dst_transitions`).
- Data-page preview **re-tags** `session` from the **bucket open**, not from child mix.
- `api.preview_resampled_ohlcv` does **not** tag session.

**1D / 4h are calendar-origin, not CME 18:00.** Runtime: hours `16:00…01:00` ET resample to `1D` labels `00:00` Mon and `00:00` Tue; Monday’s daily bar includes `18:00–23:00` (already **Tuesday** `trading_session_date`). Both daily bars tag `ETH` because midnight is ETH. 4h labels `16:00`, `20:00`, `00:00` — none align to 18:00. **This is not a session-day bar.** OTF/HTF consumers (Slice 4) must not treat `1D` resample as a CME session.

No future-bar leakage: a bucket only contains stamps in `[label, label+freq)`.

---

### Q9. Test gaps vs claimed contracts. Goldens prove identity, not correctness.

Named modules: **126 passed**. They police the contracts they encode. Gaps:

| Claim / contract | Test status |
|---|---|
| Mixed naive/aware fail-closed | **Untested.** Runtime: pandas `ValueError`, not `DataValidationError`. |
| Mixed-offset aware / DST-crossing **canonical** CSV | **Untested.** Runtime: rejected on pandas 3. Vendor path covered. |
| 15s OHLC-conflict fail-closed | Covered (loader + API + Data helper). |
| Native 1m never auto-deduped | Covered by caption/helpers; Data page still **installs** duplicate primaries. |
| UI vs API fatal OHLCV parity | **Not tested.** API fatal; Data legacy primary warning-only. |
| Rolls never mutate OHLC | Covered. Downstream “no adjust” is architectural (no engine import). |
| `session` vs `trading_session_date` disagreement table | **No dedicated test** in the named set. |
| Display TZ does not mutate engine | Covered in reporting tests, not named Slice 1 set. |
| R12 volume reconcile | **Not a contract** — and untested as a negative (volume mismatch still passes). |
| Legacy dual-upload interval inference on 30s-majority sparse 15s | **Untested.** |
| `1D`/`4h` ≠ CME session | **Untested.** 5/15/30min wall-clock only. |
| Quantower 15s→1m == vendor 1m fixture | Covered — **identity on that fixture**, not general vendor correctness. |
| Goldens | Slice 1 unused. Per Slice 0 / `fixtures/golden/README.md`: legacy identity gate, not ingest correctness. |

`test_signals_trigger_timeframe_dst.py` (ingest angle only): assumes already tz-aware NY bars across fallback; checks 5min trigger flooring does not explode. It does **not** test CSV ingest DST.

15s plan Goals still say “complete aligned coverage is required before a one-minute bar is emitted” (§2). §3.1 v2 amendment and code retain sparse minutes. **Doc-internal drift** inside the plan; ARCHITECTURE + ASSUMPTIONS match v2.

---

## 3. Prioritized findings

### Critical

None that silently rewrite research prices or drop conflicting 15s groups. The layer’s worst failures are **honesty / composer / TZ over-close**, not a hidden continuous-contract synthesizer.

### High

1. **Canonical path + pandas 3 rejects mixed-offset aware timestamps, including honest DST-crossing CSVs.**  
   `load_ohlcv` canonical `to_datetime(format="mixed")` without `utc=True`. Vendor profiles UTC-normalize first; canonical does not. Bad case: file with `2026-03-08 01:59:00-05:00` then `03:00:00-04:00` → raw `ValueError`. Operator cannot pass `utc=True`. Source selector is irrelevant (stamps are aware).

2. **Data-page legacy primary does not fail-closed on fatal OHLCV; API does.**  
   `api.load_dataset` aborts on duplicates / missing / HL / OC-range / negative volume. `pages/1_Data.py` primary branch always `tag_session` + `_set_active_dataset_state` and only **warns**. Duplicate 1m bars (VWAP/POC-sensitive) can enter classic `session_state` and be saved. 15s-primary parent path *does* fail-closed. Composer drift for Slice 7.

3. **`1D` (and 4h) resample is midnight-origin, not CME `eth_start`.**  
   A calendar `1D` bar mixes two `trading_session_date`s after 18:00. Session tag is ETH because the label is 00:00. Preview-only today, but OTF/HTF must not treat it as a session day (Slice 4).

### Medium

4. **Mixed-file errors are untyped `ValueError`**, with a pandas hint that implies an API the product does not offer. Fail-closed, poor diagnostics. No test.

5. **Legacy dual-upload R12 interval is inferred, not declared.** Sparse 15s with modal 30s gaps can be treated as a 30s grid (`expected_count=2`). 15s-primary and `run_experiment` provenance path declare `15s`. Incomplete still **passes** conservative attach (intentional) but the expected grid can be wrong.

6. **R12 reconcile ignores volume.** A lower file that matches OHLC but not volume attaches. Primary/lower volume comparison is diagnostic-only and never selects a primary row.

7. **Wrong naive `source_timezone` is a silent shift.** Especially NT default UTC vs ET-printed files. Documented; easy to miss next to the “aware ignores selector” rule.

8. **`session` vs `trading_session_date` are easy to invert** in later pages. Data page only shows clock RTH/ETH counts. 16:00–18:00 ETH is still *today’s* CME date; 18:00+ ETH is *tomorrow’s*. Session flatten is calendar-RTH, not this date (ASSUMPTIONS).

### Low

9. **`api.preview_resampled_ohlcv` omits `session`**; Data-page preview re-tags. Assistant resample preview (if it uses the API helper) will lack session.

10. **15s plan Goals vs v2 body** still disagree on “complete coverage required to emit a parent.” Code = v2 retain sparse.

11. **`DataIdentity` omits `ingestion_mode`.** Safety relies on different frame bytes / separate cache binding keys. Same derived parent from two stories would collide; current derive-from-source vs load-1m paths produce different hashes in practice.

12. **Capture profiles always floor to 1 minute**, including `second_capture`. Sub-minute engine bars are not a product path.

---

## 4. Residual risks (not closed here)

- Session flatten vs CME date vs clock `session` on overnight ETH entries (Slice 4).
- Whether Backtest/Grid/WFA consume Data-page `subtimeframe_interval` inference vs declared provenance when a bundle is restored (Slice 4/7).
- Warm-cache 15s-primary: `_load_15s_primary_experiment_data` may replace parent with artifact data when `dataset_id` matches, while **source is always re-read**. Residual: artifact parent vs freshly derived parent if identity hash is insufficiently strict (Slice 7).
- OTF HTF resample using `1D`/`4h` as if session-aligned (Slice 4).
- Levels using missing-`session` re-tag vs pre-tagged Data frame if instrument changes without reload (Slice 2).
- Operator-declared `external_continuous` that is not actually adjusted (honesty, not a code path).

---

## 5. Contracts Slice 2+ must treat as **locked**

1. **Canonical OHLCV schema:** `timestamp` (tz-aware, exchange TZ), `open`, `high`, `low`, `close`, `volume`. Optional `session` ∈ {`RTH`,`ETH`} from clock `[09:30,16:00)`. Loader sorts; `was_monotonic_before_sort` is diagnostic only.

2. **Source → exchange TZ:** naive → localize(`source_tz`) → convert(`target_tz`); aware → convert(embedded) → `target_tz`. `source_tz` unused for aware. Display TZ is export-only.

3. **`session` ≠ `trading_session_date`.** Do not group, flatten, or fold on `session` as if it were the CME date. `eth_start=18:00` is the date contract; `rth_*` is the RTH membership contract. All four symbols share both.

4. **15s-primary vs legacy dual-file:**  
   - Mode `15s_primary_derive_1m` + `quantower_history_exporter` only.  
   - Policy `observed_aligned_15s_to_1m_v2`: sparse on-grid minutes retained; misaligned dropped; no empty-bar synth.  
   - Derived 1m volume ≠ vendor 1m volume; identities are not interchangeable.  
   - Duplicate policy: OHLC-identical 15s resolved pre-derive (lowest volume); conflicts fail-closed; native 1m never auto-deduped.  
   - Dual-upload hidden while the radio says derive.  
   - `subtimeframe_path` illegal in this mode. Omit mode → primary.

5. **R12 data contract (not fill models):**  
   - Strict: complete, aligned, OHLC-reconciled; no upsample; no interpolation.  
   - Conservative: incomplete/misalign → fallback reasons; OHLC mismatch fatal.  
   - Volume not part of reconcile.  
   - Compatibility report never patches.  
   - 15s-primary **must** pass declared `parent_interval=1min`, `sub_interval=15s` into conservative prepare.

6. **Rolls:** metadata/gap diagnostics only. No continuous synthesis. Gaps remain in prices.

7. **Resample:** no upsample; financial OHLC; calendar/`freq` origin — **not** `eth_start` for `1D`/`4h`.

8. **SIA ingest tokens:** the `_DATASET_KEYS` / `STUDY_INGESTION_MODES` set above. Studies parity is RunSpec, not Data-page `session_state`.

---

## 6. Contracts still **open** (do not assume)

1. Whether mixed-offset aware canonical ingest will be UTC-normalized (vendor already is) or stay pandas-3-rejected.
2. Whether Data-page primary fatal OHLCV will be aligned with `api.load_dataset`.
3. Whether legacy dual-upload will gain declared 15s intervals (parity with 15s-primary).
4. Whether R12 should ever reconcile volume (today: no).
5. Session-flatten vs `trading_session_date` vs clock `session` on ETH overnight (Slice 4).
6. UI vs API vs Study vs Assistant ingest parity beyond the tokens listed (Slice 6/7).
7. Golden-master: still **identity**, not ingest correctness.

---

## 7. How Slice 2 should start

1. Treat §5 as the bar/TZ/session-date contract. Re-verify `trading_session_date` **usage** in each level family; do not re-audit this file’s math.
2. If a family re-derives `session` when the column is missing, confirm it uses the same instrument as Data (`tag_session(df, instrument)`).
3. Do not treat resampled `1D` columns (if any appear on Levels) as CME sessions.
4. Do not treat derived-1m VWAP/POC as comparable to a vendor-native 1m study without a new `DataIdentity`.
