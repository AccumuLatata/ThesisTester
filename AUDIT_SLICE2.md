# ThesisTester audit Slice 2 — Levels and point-in-time

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390) and Slice 1 (`AUDIT_SLICE1.md`, PR #391). Slice 1 locked contracts in this file’s §0 are treated as given; loader math was not re-audited.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/test_r3_point_in_time.py`, `test_session_levels.py`, `test_phase3_levels.py`, `test_stage1_level_plumbing.py` through `test_stage6_levels_ui_settings.py`, `test_dvwap_cme_session.py`, `test_prev30m_vwap.py`, `test_levels_page_helpers.py` — **352 passed**.
**Goldens:** not used as correctness proof. Goldens remain a **legacy-unchanged / default-off identity** gate (`docs/ENGINEERING_PROPOSAL.md` §4). They do not prove causality, clock-gates, or product-default math.

This file is the Slice 2 deliverable. Later slices must treat the **locked contracts** in §8 as given, and the **open items** as still unverified outside this layer.

---

## 0. Slice 1 contracts used here (not re-proven)

1. Canonical OHLCV: `timestamp` tz-aware exchange TZ, OHLCV; optional `session` ∈ {RTH, ETH} from clock `[09:30, 16:00)`.
2. Naive CSV: localize(`source_tz`) → convert(`target`). Aware: convert(embedded); `source_tz` ignored. Display TZ is export-only.
3. `session` ≠ `trading_session_date`. `eth_start=18:00` is the CME date contract; `rth_*` is RTH membership. All ES/NQ/MES/MNQ share both. Do not group/flatten/fold on `session` as if it were CME date.
4. 15s-primary derived 1m ≠ vendor 1m. Sparse on-grid minutes retained (v2). No empty-bar synth.
5. R12 data contract: no upsample, no interpolation. Volume not part of reconcile. Conservative incomplete can attach.
6. Rolls never rewrite prices.
7. Resample `1D` / `4h` is midnight-origin, **not** a CME session day. Do not treat resampled 1D columns as CME sessions.
8. If a family re-derives `session` when missing, it must use the same instrument as Data (`tag_session(df, instrument)`).
9. Do not treat derived-1m VWAP/POC as comparable to vendor-native 1m without a new `DataIdentity`.

`thesistester/levels/session_date.py` math is **not** re-audited. This slice only re-verifies **usage**.

---

## 1. Architecture of the levels layer

### 1.1 What this layer owns

The levels layer attaches **scalar, bar-aligned price columns** (plus two diagnostic hit flags) onto canonical OHLCV. It does **not** detect confluence, generate signals, or simulate fills.

```text
canonical OHLCV (+ optional session)
        │
        ▼
compute_all_levels  (thesistester/levels/all.py)
        ├─ compute_session_levels     sessions.py      always on
        ├─ compute_indicator_levels   indicators.py    always on (windows may be empty)
        ├─ compute_profile_levels     profile.py       always on
        ├─ compute_pivot_levels       pivots.py        gate default False
        ├─ compute_session_vwap_levels session_vwap.py gate default False
        ├─ compute_tpo_levels         tpo.py           gate default False
        ├─ compute_apoc_levels        apoc.py          gate default False
        └─ compute_prev30m_vwap_levels prev30m_vwap.py gate default False
        │
        ├─ UI: pages/2_Levels.py also calls compute_session_levels AGAIN
        └─ API: api.compute_levels also calls compute_session_levels AGAIN
                (after normalize_levels_config → product defaults)
```

Two clocks (Slice 1) remain inverted at this layer:

| Clock | Used for | Must not be used for |
|---|---|---|
| `session` ∈ {RTH, ETH} | RTH membership (OR, ONH gate, RTH_Open, dVWAP_RTH, TPO, APOC) | CME date grouping |
| `trading_session_date(..., eth_start)` | pd*/pw*/pm*, dVWAP, prev30m brackets, TPO/APOC session keys, week/month keys derived from it | Clock RTH/ETH membership |

No family groups on `session` as if it were a CME date. `session.eq("RTH"|"ETH")` is only a membership mask; aggregates then `groupby(session_date)`.

### 1.2 Three composers (same functions, different gates)

| Path | Entry | Settings source | Tags missing `session`? | Second `compute_session_levels`? |
|---|---|---|---|---|
| Classic UI | `pages/2_Levels.py` widgets | Widget values seeded from `DEFAULT_LEVELS_SETTINGS` (advanced ON, OR 15). Stale/old-snapshot helper `_normalize_levels_settings` setdefaults **advanced OFF / agg ticks 1** | Yes, `tag_session(base_df, instrument)` before both calls | Yes, same `instrument` + widget `opening_range_minutes` |
| Headless API | `api.compute_levels` | `normalize_levels_config` → `{**DEFAULT_LEVELS_SETTINGS, **raw}` (advanced ON, OR 15) | **No.** Relies on `load_dataset` / caller | Yes, same `instrument` + `int(settings["opening_range_minutes"])` |
| Study | `api.run_experiment` → `compute_levels` | `run["levels"]` through the same normalizer; omitted keys = product defaults | Same as API (`load_dataset` tags) | Same as API |

`compute_all_levels` **keyword** defaults are a fourth, legacy-additive surface: OR **30**, all Stage 1+ gates **False**, SMA/EMA `(20, 50, 200)` unlabeled, VWAP `(15min, 30min, 1h, 4h)`, POC `(30min, 1h, 4h)`, prior-profile ticks **1**. Documented in `levels/defaults.py`, `docs/ARCHITECTURE.md` Stage 6, and ASSUMPTIONS 5a–5e. **Do not treat a bare `compute_all_levels(df)` call as the product.**

### 1.3 `session_levels` is not a collapsed session table

Both composers store a second full bar-aligned frame from `compute_session_levels` (OHLCV + structural columns). It is **not** a per-session aggregate. `compute_all_levels` already embeds those columns. The second call is redundant compute, currently argument-identical (Q2).

Cache hit (`api.compute_levels` `read` / `read_write`): returns the pair written from that same call (`levels.parquet` + `session_levels.parquet`). No second live compute; OR/instrument identity is whatever was stored.

---

## 2. Must-answer questions

### Q1. Which PIT rows are still inspection-only (`—` in the R3 table), and have post-R3 families been future-shock tested at the same standard?

**Three living `—` rows remain. Post-R3 families have dedicated future-shock tests; they are not all the same fixture style as R3.**

R3 table (`docs/POINT_IN_TIME_GUARANTEES.md`) marks `—` = code inspection, no dedicated future-shock. Those rows are still:

| Family | Source | Dedicated R3-style future-shock? | What exists instead |
|---|---|---|---|
| `dOpen` / `wOpen` / `mOpen` | `_current_opens` `transform("first")` | **No** | Correctness + DST: `test_session_levels.py::test_dopen_uses_eth_session_start_not_midnight`, `test_trading_session_date_and_dopen_across_{spring,fall}_dst_*`. Prefix identity: `test_batch_vs_incremental_causality_matches_with_eth_session_boundaries` includes these columns |
| `prevSettlement` | `_prev_settlement` `shift(1)` | **No** | Fallback correctness: `test_prev_settlement_fallback_uses_prior_rth_close_not_post_rth`. Prefix identity: same batch-vs-incremental suite |
| `pmVAH` / `pmVAL` / `pmPOC` | `_map_prior_profile_levels(month_key)` | **No** | Value/key tests in `test_phase3_levels.py` (`test_prior_month_profile_levels_*`, aggregation-tick isolation). **No** `test_prior_month_profile_future_shock`. Day/week profile **are** future-shocked in `test_r3_point_in_time.py` |

`test_batch_vs_incremental_*` is causal (prefix vs full-batch row identity) but is **not** the R3 future-shock pattern (append extreme later bars, assert prefix unchanged). Inspection-only in the living table is still accurate for those three rows.

**Table overclaim (not a `—` row, but a Tests-column error):** `pwHigh/pwLow/pwOpen/pwEQ` and `pmHigh/pmLow/pmOpen/pmEQ` are listed as covered by `test_prior_session_levels_future_shock`. That test asserts only `pdHigh/pdLow/pdOpen/pdEQ`. The day-3 shock is still the same week/month, so a current-period leak into `pw*`/`pm*` would **not** be caught by the asserted columns. Structural week/month causality is actually carried by batch-vs-incremental + `test_weekly_levels_use_trading_session_week_keys` / `test_monthly_levels_use_trading_session_month_keys`, not by that R3 test.

**Post-R3 families (after the June 2026 R3 milestone) — future-shock status:**

| Family | Future-shock tests | Same standard as R3? |
|---|---|---|
| Asia / London | `test_r3_point_in_time.py::test_{asia,london}_levels_future_shock_append_does_not_change_prior` **and** `test_session_levels.py` twins | **Yes** — prefix through close, append extreme later bar, prefix unchanged |
| `pRTH_High/Low/Open` | `test_r3_point_in_time.py::test_prth_high_low_future_shock` + session-levels twin | **Yes** |
| Pivots | `test_stage2_pivot_levels.py::test_pivot_levels_are_point_in_time_safe_under_future_shock` | **Yes** (plus confirmation-delay tests) |
| `dVWAP_RTH` | `test_stage3_session_vwap.py::test_dvwap_rth_future_shock`, `test_dvwap_rth_future_shock_across_sessions` | **Yes** |
| `dVWAP` (CME) | `test_dvwap_cme_session.py::test_dvwap_future_shock_within_session`, `test_dvwap_future_shock_across_sessions` | **Yes** |
| TPO SP | `test_stage4_single_prints.py` two future-shock tests | **Yes** |
| APOC / pAPOC | `test_stage5_apoc_levels.py` two future-shock tests | **Yes** |
| `prev30mVWAP` + stack + hits | `test_prev30m_vwap.py::test_future_shock_append_in_session`, `test_future_shock_append_next_session`, `test_mid_session_dataset_end_does_not_finalize_future_shock`, `test_phase3_future_shock_with_stack` | **Yes**, and stricter: mid-session truncation must **not** finalize (R3 families have no equivalent halt/truncation case) |

**Not future-shocked at R3 standard even though the table says Causal? = Yes:** OR (gate + clock-vs-first-bar tests only), `RTH_Open` (gate only), ONH/ONL (gate only), higher-TF SMA/EMA (alignment/no-lookahead tests in `test_phase3_levels.py`, not append-extreme), `pm*` profile (above).

**Verdict:** Inspection-only `—` rows are still `dOpen/wOpen/mOpen`, `prevSettlement`, `pmVAH/pmVAL/pmPOC`. Post-R3 families **have** been future-shock tested. OR / `RTH_Open` / ONH / higher-TF MAs / structural `pw*`/`pm*` are weaker than the table’s wording implies.

---

### Q2. Does `api.compute_levels`’ second `compute_session_levels` use identical OR minutes / instrument as `compute_all_levels` in all paths (UI, cache hit, Study)?

**Yes on live compute for UI / API / Study. Cache hit returns the stored pair (no live second call). Residual is compositional, not a current OR/instrument split.**

`_LEVEL_ARGUMENT_MAP` remaps only prior-profile tick key names. `opening_range_minutes` is passed through unchanged.

| Path | `compute_all_levels` | Second `compute_session_levels` | Match? |
|---|---|---|---|
| API cold | `instrument=instrument`, `**kwargs` includes `opening_range_minutes` from `normalize_levels_config` | `instrument=instrument`, `opening_range_minutes=int(settings["opening_range_minutes"])` | **Yes.** Same `data` object (not re-tagged) |
| Study | `run_experiment` → `compute_levels(data, instrument=instrument, config=run.get("levels"))` | Same function | **Yes** |
| UI | widget `instrument` (from `st.session_state["instrument"]`, Data page) + widget `opening_range_minutes` | Same two values on possibly tagged `base_df` | **Yes** |
| API cache hit | no compute | no compute; returns `cached.levels` + `cached.session_levels` written together | **Identical by artifact**, not re-checked against current kwargs |

**Bad case that does *not* currently fire:** if a future editor changed only one of the two call sites, `levels["OR_*"]` and `session_levels["OR_*"]` would diverge. There is **no** test that `result["levels"][OR cols] == result["session_levels"][OR cols]` after `compute_levels`.

**Not an OR mismatch, but a tagging mismatch (composer):** UI tags missing `session` before *both* calls. API `compute_levels` does not tag. On untagged input, both `compute_session_levels` invocations NaN session-dependent columns (identical), while gated families inside `compute_all_levels` re-tag and still emit. That is Q8, not an OR-minutes bug.

**Keyword-default trap:** `compute_all_levels(..., instrument="ES")` without `opening_range_minutes` uses **30**. Product / API / UI first-visit use **15**. A researcher comparing a raw library call to `api.compute_levels` will see different OR columns. That is Q6, not a double-call split.

---

### Q3. Are `prev30mVWAP_hit_*` columns ever selectable as setup levels despite `NON_LEVEL_OUTPUT_COLUMNS`?

**Not on product pickers or validated setup/Study tokens. They still appear on the Levels preview table, and `build_setup_config` does not strip them.**

`thesistester/setup.py`:

- `NON_LEVEL_OUTPUT_COLUMNS = frozenset({"prev30mVWAP_hit_m1", "prev30mVWAP_hit_m5"})`
- `is_setup_eligible_level_column` / `available_level_columns` exclude them
- `validate_setup_config` rejects them in `selected_levels`, `anchor_level`, and each confluence-rule `level`

Surfaces:

| Surface | Hit columns selectable? | Evidence |
|---|---|---|
| Levels plot multiselect | **No** | `pages/2_Levels.py`: `plottable_level_columns` uses `is_setup_eligible_level_column` |
| Levels preview `st.dataframe` | **Visible** (not a picker) | `level_columns` = all non-base cols; `preview_cols` includes hits |
| Setup Builder / Signals pickers | **No** | both call `available_level_columns` |
| `api.build_setup` / `api.generate_signals` | **Rejected** | both run `validate_setup_config` |
| Study factor tokens | **Rejected** | `closed_level_token_set` uses `prev30m_price_column_names` (price stack only); `prev30mVWAP_hit_*` not in `STUDY_STATIC_LEVEL_NAMES`; unknown tokens fail closed |
| `build_setup_config` alone | **Copies through** | no filter; only later validate catches |
| Chart auto-plot | **No** | `visualization/backtest_chart.py` and `test_hit_columns_not_setup_or_chart_eligible` |

Test: `tests/test_prev30m_vwap.py::test_hit_columns_not_setup_or_chart_eligible` — picker exclusion, validate error containing `"diagnostic"`, assistant `level_columns` omission.

**Bad case:** a hand-edited setup JSON / raw `build_setup_config(...)` that lists `prev30mVWAP_hit_m1` and is passed **around** `validate_setup_config` into `detect_confluence_zones` would treat 0/1 flags as prices near zero. Product composers do not do this. Slice 3+ (setup/confluence) must keep the validate gate; this slice does not audit `engine/confluence.py`.

Stack columns `prev30mVWAP_2`…`_N` **are** setup-eligible by design (`is_prev30m_price_level_column`; ARCHITECTURE Stage 6).

---

### Q4. Clock-gate vs bar-existence for OR / Asia / London / APOC: any path that emits early?

**No path emits before the clock gate. Incomplete windows *do* emit after the clock if any in-window bars exist. That is documented, not a lookahead bug.**

| Family | Gate | In-window membership | Early emit? | Incomplete emit after clock? |
|---|---|---|---|---|
| OR | `session_midnight + rth_start + opening_range_minutes` (`local_ts >= available_after`) | RTH and `start_minute ≤ minute_of_day < end_minute` (seconds ignored) | **No.** Bars inside the window stay NaN. `test_opening_range_not_visible_before_or_end`, `test_opening_range_not_visible_on_new_session_eth_bar` | **Yes.** Missing 09:30 still emits at clock end from 09:31–09:34 (`test_opening_range_availability_is_clock_based_not_first_rth_bar`). Empty window → all-NaN |
| Asia | `window_key` date + `asia_end` (default 00:00) | ETH ∩ `[asia_start, asia_end)` (wraps midnight) | **No.** `test_asia_levels_gated_until_close` / hidden-during-window | **Yes** if any ETH bar in window. Empty window → all-NaN. Empty `asia_start`/`asia_end` → all-NaN (fail closed) |
| London | session-key date + `london_end` (default 05:00) | ETH ∩ `[02:00, 05:00)` | **No.** `test_london_levels_gated_until_close` | Same as Asia |
| APOC | theoretical `session_date @ rth_start + 30min`, **not** first actual RTH bar | RTH ∩ `[RTH_open, RTH_open+30)` | **No.** 09:30/09:45 NaN; 10:00 emits (`test_apoc_is_nan_before_a_period_completion`, `test_apoc_appears_at_a_period_completion`) | **Yes** if any A-period bars exist. No A-period bars → NaN after the gate (`test_apoc_missing_a_period_returns_nan`) — does **not** synthesize from later RTH |
| TPO developing (related) | `rth_open + (bucket_idx+1)*30min`; emit iff `end_ts <= row_ts` | RTH bars in that clock bucket | **No.** `test_no_developing_sp_before_first_completed_bracket` | **Yes** — sparse bucket still freezes at clock end |

**ONH/ONL** are *bar-existence* gated (first RTH timestamp of that `session_date`), not a clock. They stay NaN through ETH even after overnight is economically complete. Conservative; not early.

**Minute-of-day vs seconds:** OR uses `hour*60+minute`. A 15s bar at `09:44:45` stays in a 15-min OR; availability is `09:45:00`. Not early. For 1-minute left-labeled bars, the first post-window bar open equals last in-window bar close — clock-gate aligns with bar-close of the window.

**No emit-early path found** under correct `session` tags. A **wrong** pre-tagged `session` (RTH before 09:30) can put negative TPO buckets on the timeline (`tpo.py` `elapsed_minutes // 30`); that is caller contract abuse, not a clock-gate hole. `sessions.py` does not re-tag (Q8).

---

### Q5. Per-family causality: can a level at time T use future bars (lookahead / future-shock)?

**Batch compute often *reads* the full frame, then *gates* or `shift(1)`s. That is causal iff the gate/shift is correct. Code + tests say yes for implemented families; residual is untested rows (Q1) and same-bar close inclusion.**

Causal pattern used everywhere:

1. **Prior-period:** aggregate the whole period, `shift(1)`, map back. Bars on period P see only P−1. Appending P+1 cannot change P’s prior columns.
2. **Clock/completion gate:** aggregate a window, emit only when `timestamp >= window_end`. In-window bars are strictly before the gate (half-open windows).
3. **Running/cumulative:** `cumsum` / `rolling` / `ewm` / per-bar `timestamps <= now` (rolling POC).
4. **HTF / pivot:** detect with right-side bars, expose only at `align_timestamp = pivot_open + (right+1)*TF` via `merge_asof(direction="backward")`.

| Family | Can T use bars > T? | Mechanism | Risk if broken |
|---|---|---|---|
| pd*/pw*/pm* structural | No | `shift(1)` on `trading_session_date` / week / month keys | Current session high leaking into “prior” |
| dOpen/wOpen/mOpen | No | `transform("first")` of current period | None for lookahead; they are *live* opens (doc limitation) |
| RTH_Open | No | first RTH open of `session_date`, gated `timestamp >= first_rth_ts` | Visible on ETH |
| ONH/ONL | No | overnight ETH max/min, gated at first RTH (overnight is before RTH) | Post-RTH 16:00–18:00 excluded (`t >= 18:00` or `t < 09:30`) |
| Asia/London | No | ETH window agg + close clock | Rolling during window |
| pONH/pONL/pRTH_* | No | `shift(1)` on per-session aggregates | Current session RTH leaking into pRTH |
| OR | No | window agg + clock | Visible during OR; later RTH leaking into OR |
| prevSettlement | No | `shift(1)` last settlement or last RTH close | Post-RTH close used as settlement (tested; fallback is RTH-only) |
| pd/pw/pm VAH/VAL/POC | No | `_map_prior_profile_levels` + `shift(1)` | Incomplete current day used as prior |
| POC_rolling_* | No | `(start, now]` per bar | Future volume in bin |
| SMA/EMA base | No | `rolling`/`ewm` include bar *i* close (ASSUMPTIONS #5 / PIT #7) | Intrabar use of close — documented intent |
| SMA/EMA HTF | No | resample + `align_timestamp = open+TF`; `merge_asof` backward | HTF value before candle close |
| VWAP_rolling_* | No | time-indexed rolling through *i* | Same close-known note |
| Pivots | Detection uses `shift(-right)`; **exposure** delayed | `align_timestamp` + backward asof | Unconfirmed pivot visible |
| dVWAP_RTH / dVWAP | No | per-session `cumsum` on bars ≤ t | Future PV in the session |
| TPO dSP | No | completed brackets `end_ts <= row_ts` only | Current 30m bracket leaking |
| TPO pSP | No | prior session’s full bracket set at next RTH | Current session altering prior SP |
| APOC | No | A-period bars `< RTH_open+30`; emit `>=` that clock | Later RTH in APOC |
| pAPOC | No | prior session APOC, frozen | Next session rewriting pAPOC |
| prev30mVWAP | No | freeze only on clock completion or **true** session transition; **no** dataframe-end finalize | Mid-session truncate rewriting freezes |
| hit_m1 / hit_m5 | No | in-window rows stay NaN; finalize `timestamp >= window_end` from in-window touches only | Rewriting the 09:30 row after the fact |

**Honesty limitations (not lookahead):** typical-price VAP; same-bar close in rolling series; clock-incomplete windows; ONH hidden during ETH; Asia/London not rolling; `dOpen` is live; TPO developing never emits the last RTH 30m bracket of the day (no RTH bar at 16:00) while `pSinglePrint` of the *next* session includes that last bucket — causal, but developing vs prior sets differ by that last bracket.

**4h pivot / 4h rolling VWAP:** `resample_ohlcv(..., "4h")` is midnight-origin (Slice 1 contract 7). Causal, but **not** a CME session bar. Do not read `Pivot_4h_*` as session-anchored.

---

### Q6. Product defaults (`DEFAULT_LEVELS_SETTINGS`, advanced ON) vs `compute_all_levels` keyword gates default OFF — where do UI/API/Study disagree?

**UI first-visit, API `compute_levels()`, and Study omitted-`levels` agree on product defaults. Bare `compute_all_levels()` does not. Classic snapshot `_normalize_levels_settings` disagrees on *missing* keys.**

| Setting | `compute_all_levels` kwargs | `DEFAULT_LEVELS_SETTINGS` / API / Study / UI widgets | UI `_normalize_levels_settings` on **missing** keys |
|---|---|---|---|
| `opening_range_minutes` | **30** | **15** | unchanged if absent (no setdefault) |
| `sma_lengths` | `None` → (20, 50, 200) unlabeled | [50, 200] on 1/5/30min | n/a |
| `ema_lengths` | `None` → (20, 50, 200) unlabeled | [9, 21] on 1/5/30min | n/a |
| `sma/ema_timeframes` | `None` → `SMA_N` / `EMA_N` | `["1min","5min","30min"]` → `SMA_50_1min` etc. | sort only |
| `vwap_windows` | `None` → 15m/30m/1h/4h | 30m/4h | sort only |
| `poc_windows` | `None` → 30m/1h/4h | 30m | sort only |
| prior-profile ticks | **1 / 1 / 1** | **4 / 8 / 10** | **1 / 1 / 1** |
| `pivots_enabled` and other Stage 6+ gates | **False** | **True** | **False** |
| `session_vwap_anchor` | `"RTH"` | `"RTH"` (UI hardcodes; no widget) | `"RTH"` |
| `prev30m_vwap_validity_periods` | 1 | 1 | 1 |

Evidence: `thesistester/levels/all.py` signature; `thesistester/levels/defaults.py`; `normalize_levels_config`; `pages/2_Levels.py` widgets + `_normalize_levels_settings`; `test_api.py::test_compute_levels_uses_shared_product_defaults`; `test_stage6_levels_ui_settings.py::test_product_defaults_match_requested_levels_configuration` vs `test_empty_dict_gets_all_defaults`; `test_stage1_level_plumbing.py::test_compute_all_levels_no_new_columns_with_default_settings`; study `schema.py` `{**DEFAULT_LEVELS_SETTINGS, **levels_map}`.

**Documented and intentional:** ASSUMPTIONS 5a–5e, ARCHITECTURE Stage 6, `defaults.py` module docstring, `research_identity.normalize_levels_config` docstring (“Classic page sparse setdefaults remain a separate legacy UX path”).

**Real disagreement (not just library vs product):**

1. **Old saved Levels snapshots** missing Stage 6 keys load as gates **OFF** and missing agg-tick keys as **1** (`_normalize` + `_sync_levels_widget_state`). API `normalize_levels_config({})` would turn those same missing keys **ON** / **4/8/10**. Reloading an old snapshot on the page ≠ re-running the same dict through `api.compute_levels`. Historical identity preservation vs product fill — two normalizers.
2. **UI does not call `normalize_levels_config`.** First-visit widgets match product, but identity for classic page state uses `_normalize_levels_settings` (setdefault False/1) then `LevelsIdentity.from_page_state` which *does* run `normalize_levels_config` on stored `levels_settings`. If stored settings are complete (they are, after a successful calculate), hashes match. If someone stuffed a sparse dict into `levels_settings`, page identity would fill with **product ON** while the page helper would have treated it as OFF for stale-compare. Edge case; calculate path writes a full widget dict.
3. **Study `closed_level_token_set`:** `prev30m` / `Pivot_*` tokens are admitted only when the matching enable flag is on. Static catalog always includes session/profile/dVWAP/APOC/SP names even if a study disables those gates — a study can *name* `APOC` as `core_level` while `apoc_enabled=False` (engine would lack the column). Schema validates tokens against the catalog, not against “column will exist.” Out of this slice’s Study audit, but it is a defaults/eligibility seam for Slice 6.

**UI vs API first-visit / `compute_levels()` / Study omit-levels:** agree (product ON, OR 15, ticks 4/8/10).

---

### Q7. Session-date usage: does every family that needs a CME date actually call `trading_session_date` (not clock `session`)?

**Yes. No family groups on clock `session` as a date. Week/month keys are derived from `trading_session_date`, not calendar midnight.**

| Family | CME date? | Call site |
|---|---|---|
| sessions.py pd*/dOpen/OR/ONH/Asia/London/pRTH/prevSettlement | **Yes** | `compute_session_levels`: `session_date = trading_session_date(local_ts, eth_start)`; `week_key`/`month_key` = `to_period("W-SUN"|"M")` on that date |
| profile.py prior day/week/month | **Yes** | `day_key = trading_session_date(...)`; week/month from `day_key` |
| session_vwap.py `dVWAP` / `dVWAP_RTH` groups | **Yes** | `session_date = trading_session_date(...)`; RTH mask is clock `session` |
| tpo.py | **Yes** | `work["_session_date"] = trading_session_date(...)` |
| apoc.py | **Yes** | same |
| prev30m_vwap.py | **Yes** | `session_dates = trading_session_date(...)`; brackets from `eth_start` session open (`D-1 @ 18:00`) |
| indicators.py | **No CME date** | time rolling + calendar resample |
| pivots.py | **No CME date** | fractal + calendar resample (incl. **4h midnight-origin**) |

`session.eq("RTH"|"ETH")` appears only as a membership filter (OR, ONH overnight, RTH_Open, dVWAP_RTH, TPO, APOC). Aggregates then key by `session_date`. This matches Slice 1 contract 3.

`prev30m` fail-closes if `eth_start` is empty (`ValueError`). `dVWAP` / session levels / profile **fall back to calendar date** when `eth_start` is empty (`trading_session_date` → `base_date`). Product presets all have `eth_start="18:00"`. Empty-`eth_start` is a test monkeypatch path only.

---

### Q8. Missing-`session` re-tag: same instrument as Data?

**Families that re-tag use `tag_session(work, instrument=instrument)` with the `compute_*` instrument argument. `sessions.py` does *not* re-tag. Composers disagree on whether missing `session` is filled before structural levels run.**

| Module | If `session` missing | Instrument used |
|---|---|---|
| `sessions.py` | Session-dependent columns **all-NaN** (docstring). `dOpen/wOpen/mOpen`, pd*/pw*/pm* structural, `prevSettlement` (close fallback) still compute | N/A — no `tag_session` |
| `session_vwap.py` | `tag_session(work, instrument=instrument)` | same param as `compute_all_levels` |
| `tpo.py` | same | same |
| `apoc.py` | same | same |
| `prev30m_vwap.py` | same (then unused for grouping; date/bracket clock is `trading_session_date`) | same |
| `profile.py` / `indicators.py` / `pivots.py` | do not read `session` | profile uses instrument for tick + `eth_start` only |

Composer wrap:

| Path | Pre-tag | Instrument source |
|---|---|---|
| Data page | always `tag_session(..., instrument)` on install | Data widget |
| Levels UI | if missing, `tag_session(base_df, instrument)` with `st.session_state["instrument"]` | **same key as Data** (no separate Levels instrument widget) |
| `api.load_dataset` / `run_experiment` | tags | run `instrument` |
| `api.compute_levels` | **does not tag** | — |
| Bare `compute_all_levels` | only gated families tag | function `instrument` (default `"ES"`) |

**Bad case:** untagged frame into `api.compute_levels` or `compute_all_levels` → `OR_*/ONH/RTH_Open/Asia/London` NaN in **both** `levels` and `session_levels`, while `dVWAP_RTH` / TPO / APOC / prev30m still compute (re-tagged as ES unless overridden). Structural vs gated families disagree on the same frame. Product UI/API ingest paths tag first, so this is a **library/facade** hole, not the Data→Levels happy path.

**Wrong-instrument re-tag:** if `session` is already present (Data tagged ES) and Levels/`compute_levels` is called with `instrument="NQ"`, gated families **do not** re-tag; they trust the column. ES/NQ/MES/MNQ share `rth_start/rth_end` (Slice 1), so membership is identical today. Tick size is also 0.25 for all four; point value differs but is unused in levels. Residual is a future instrument with a different RTH window.

No test in the named set calls `compute_session_levels` on a frame **without** `session` to lock the all-NaN contract. Gated-family missing-`session` **is** tested (`test_session_column_derived_from_instrument_config`, `test_session_column_can_be_absent`, `test_session_column_absent_derives_from_instrument_config`, prev30m fixtures that drop/omit as applicable).

---

### Q9. Test gaps vs `POINT_IN_TIME_GUARANTEES.md`. Goldens ≠ correctness.

Named modules: **352 passed**. They police the contracts they encode. Gaps vs the living PIT table and this slice’s questions:

| Claim / contract | Test status |
|---|---|
| `dOpen/wOpen/mOpen` future-shock | **Untested** at R3 standard. Prefix identity + DST/open-source tests only. Table: `—` (accurate) |
| `prevSettlement` future-shock | **Untested** at R3 standard. Fallback + prefix identity. Table: `—` (accurate) |
| `pmVAH/pmVAL/pmPOC` future-shock | **Untested.** Table: `—` (accurate) |
| `pw*`/`pm*` structural listed as “Same” as `test_prior_session_levels_future_shock` | **Overclaim.** That test does not assert those columns |
| OR future-shock (extreme later RTH must not change OR after clock) | **Untested.** Gate + clock-vs-first-bar + batch-vs-incremental only |
| `RTH_Open` / ONH future-shock | **Untested.** Gate tests only |
| HTF SMA/EMA future-shock | Alignment/no-lookahead tests; **no** append-extreme in `test_r3` or `test_phase3` |
| API second `compute_session_levels` OR/instrument parity vs `levels` columns | **Untested** |
| `compute_session_levels` without `session` → NaN | **Untested** |
| UI vs API vs Study live OR/instrument identity | Architectural; no single cross-composer test in the named set |
| Hit columns not setup-selectable | **Covered** (`test_hit_columns_not_setup_or_chart_eligible`) |
| Product vs keyword defaults | **Covered** as two separate suites (stage1 default-off vs stage6/API product-on). Easy to confuse |
| Clock-gate no-early-emit OR/Asia/London/APOC | **Covered** |
| Incomplete OR emit after clock | **Covered** |
| Incomplete APOC / empty A-period | **Covered** |
| prev30m mid-session truncate / session-boundary finalize | **Covered** |
| Missing-`session` re-tag uses `instrument` | Covered for VWAP/TPO/APOC; not for `sessions.py` (it does not re-tag) |
| `1D`/`4h` ≠ CME session on Levels | Indicators do not offer `1D`. **4h pivot + 4h VWAP are midnight-origin.** No test says “4h pivot is not a session bar” |
| Goldens | Unused here. Per Slice 0/1: **identity**, not PIT correctness |

`test_stage1_level_plumbing.py` locking gates default-off is a **golden-adjacent identity** test for `compute_all_levels()`, not proof that product defaults are causal.

---

## 3. Family-by-family causal availability table

Columns: **Avail** = when a non-NaN may appear. **Eligible** = setup/plot (`is_setup_eligible_level_column`). **FS** = dedicated future-shock at R3 standard.

| Family | CME date? | Re-tag if no `session`? | Avail | Clock vs bars | Eligible | FS | Notes |
|---|---|---|---|---|---|---|---|
| pdHigh/Low/Open/EQ | `trading_session_date` | n/a (no session needed) | first bar of next session | completed prior session | yes | yes (pd* only) | `shift(1)` |
| pw* / pm* structural | week/month of session date | n/a | first bar of next week/month | completed prior period | yes | **overclaimed** | see Q1 |
| dOpen/wOpen/mOpen | session/week/month date | n/a | first bar of *current* period | live open | yes | **—** | not a prior level |
| RTH_Open | session date + RTH mask | **no** (NaN) | first RTH bar | bar-existence | yes | gate only | |
| ONH/ONL | session date + ETH overnight | **no** (NaN) | first RTH bar | bar-existence | yes | gate only | hidden all ETH |
| AsiaHigh/Low | session date + ETH window | **no** (NaN) | `asia_end` clock | clock; incomplete OK | yes | yes | default 20:00–00:00 |
| LondonHigh/Low | session date + ETH window | **no** (NaN) | `london_end` clock | clock; incomplete OK | yes | yes | default 02:00–05:00 |
| pONH/pONL/pRTH_* | session date + shift(1) | **no** (NaN if no session) | all bars of next session | completed prior | yes | yes (pRTH) | pRTH ≠ pd* |
| OR_High/Low | session date + RTH window | **no** (NaN) | RTH start + N min clock | clock; incomplete OK | yes | gate + incremental | keyword N=30 vs product 15 |
| prevSettlement | session date | n/a (RTH used if present) | first bar of next session | `shift(1)` | yes | **—** | settlement col or last RTH close |
| pd/pw/pm VAH/VAL/POC | session/week/month date | n/a | first bar of next period | `shift(1)` | yes | day+week yes; **month —** | typical-price VAP; ticks 1 vs 4/8/10 |
| POC_rolling_* | no | n/a | once window has bars ≤ T | `(start, now]` | yes | yes | O(N²) |
| SMA_N / EMA_N | no | n/a | bar N−1 | includes bar i close | yes | yes (base) | keyword vs product lengths |
| SMA_N_TF / EMA_N_TF | no (calendar resample) | n/a | after HTF close | asof backward | yes | alignment tests | no 1D; 5/30min only |
| VWAP_rolling_* | no | n/a | rolling window ≤ T | includes bar i | yes | yes | 4h is time window, not CME |
| Pivot_* | no (calendar resample; **4h midnight**) | n/a | after right+1 TF closes | delayed exposure | yes | yes | gate default off |
| dVWAP_RTH | session date + RTH | **yes**, `instrument` | first RTH bar | cumsum ≤ T | yes | yes | NaN on ETH |
| dVWAP | session date (ETH+RTH) | yes (unused for CME group) | first bar of CME session | cumsum ≤ T | yes | yes | calendar fallback if no `eth_start` |
| dSinglePrint_30m_* | session date + RTH | **yes**, `instrument` | after first completed 30m clock bracket | clock; incomplete OK | yes | yes | last RTH bracket often never develops |
| pSinglePrint_30m_* | session date + RTH | yes | first RTH of next session | prior full set | yes | yes | may include last bracket dSP never showed |
| APOC | session date + theoretical RTH open | **yes**, `instrument` | `RTH_open+30` clock | clock; incomplete OK | yes | yes | not from TPO |
| pAPOC | session date | yes | first RTH of next session | prior APOC | yes | yes | |
| prev30mVWAP / `_2`…`_N` | session date + `eth_start` open | yes (then unused) | first bar of next 30m (or session seed) | clock or session transition; **no** EOF finalize | yes | yes | fail-closed without `eth_start` |
| prev30mVWAP_hit_m1/m5 | same brackets | — | after 1m/5m window; in-window NaN | clock | **no** | yes (with price cols) | diagnostic only |

---

## 4. Prioritized findings

### Critical

None that silently leak future bars into a level at T on the product UI / `api.compute_levels` / Study ingest path. The layer’s worst issues are **honesty of the PIT table, composer defaults, and missing-`session` split** — not an un-gated lookahead in a shipped family.

### High

1. **PIT table overclaims tests for `pw*`/`pm*` structural and leaves OR/`RTH_Open`/ONH/HTF MAs weaker than “Causal? = Yes” reads.**  
   `test_prior_session_levels_future_shock` does not assert week/month columns. A current-week leak into `pwHigh` would pass that test. Bad case: researcher treats the Tests column as coverage.

2. **Three inspection-only families still have no R3 future-shock (`dOpen*`, `prevSettlement`, `pm` profile).**  
   Code looks causal (`first` / `shift(1)`). Prefix identity covers session-column `dOpen`/`prevSettlement` only. Month profile has **neither** future-shock nor batch-vs-incremental.

3. **Missing-`session` split: `sessions.py` fail-closed NaN vs gated families re-tag.**  
   Untagged `compute_all_levels` / `api.compute_levels` emits dVWAP/TPO/APOC/prev30m and blanks OR/ONH/Asia/London/RTH_Open. UI and `load_dataset` hide this. Bad case: notebook / assistant passing a resampled preview without `session` (`api.preview_resampled_ohlcv` omits `session` — Slice 1 Q residual).

4. **Two defaults planes will keep producing “wrong OR / missing pivots” reports.**  
   Bare `compute_all_levels(df)` → OR 30, no advanced, SMA 20/50/200, ticks 1. Product → OR 15, advanced ON, SMA 50/200@TF, ticks 4/8/10. This is documented; it is still the highest operational foot-gun in the layer.

### Medium

5. **Classic `_normalize_levels_settings` setdefaults (gates False, ticks 1) ≠ `normalize_levels_config` (product ON, ticks 4/8/10).**  
   Intentional for old snapshots. Sparse dicts are interpreted differently by page helper vs API. `test_empty_dict_gets_all_defaults` locks the page helper to OFF.

6. **Redundant second `compute_session_levels` is currently identical, untested as a pair.**  
   Drift risk if one call site changes. Cache hit is fine (single write).

7. **Clock-gate emits incomplete OR/Asia/London/APOC/TPO.**  
   Documented. Strategies that assume “15-minute OR means 15 minutes of bars” are wrong on gappy 15s-primary / sparse 1m (Slice 1 v2 retain sparse). Not lookahead; honesty.

8. **`build_setup_config` does not strip hit columns; Levels preview lists them.**  
   Validated paths reject. Raw/engine bypass is a Slice 3 concern.

9. **4h pivot (and optional 4h VWAP) are midnight-origin resamples.**  
   Causal. Not CME `eth_start`. Slice 1 contract 7 applies on the Levels frame when those columns exist (product default **includes** `Pivot_4h_*` and `VWAP_rolling_4h`).

### Low

10. **TPO developing vs prior last-bracket gap.** Last RTH 30m bucket rarely gets a developing emit (no RTH bar at 16:00) but is included in next session `pSinglePrint`. Causal; easy to misread as “prior SP is the last developing snapshot.”

11. **`prev30m` tags `session` then groups only on `trading_session_date`.** Harmless; the tag is unused for brackets.

12. **PIT doc still says “specific to R3 (June 2026)”** while the table already includes post-R3 families. Scope sentence is stale; the table is the living inventory.

13. **No named test that `session` is never used as a group-by date.** Verified by inspection only.

---

## 5. Residual risks (not closed here)

- Confluence / signals / naked **inherit** level causality (PIT table). Not audited (Slice 3+). A non-eligible hit column slipped past validate would become a ~0–1 “price.”
- `analytics/prev30m_vwap_hit.py` join-at-entry (Slice 5). Engine columns are causal; analytics must not treat in-window NaNs as 0.
- OTF / WFA / session flatten vs these columns (Slice 4). Especially `1D`/`4h` HTF and `Pivot_4h_*`.
- Derived-1m VWAP/POC ≠ vendor 1m (Slice 1 contract 9). Product defaults enable those families.
- Instrument change without Data reload: Levels uses `session_state["instrument"]`. Today RTH windows match across the four presets.
- Cache artifact written under product settings, later consumed after `LEVEL_ENGINE_VERSION` bump — persistence concern (Slice 7), not PIT math.
- Empty `eth_start` calendar fallback in session/profile/dVWAP vs prev30m fail-closed — only a custom-instrument risk.

---

## 6. Contracts Slice 3+ must treat as **locked**

1. **Two settings planes.** Product = `DEFAULT_LEVELS_SETTINGS` via `normalize_levels_config` (UI widgets, `api.compute_levels`, Study omit/merge). Library = `compute_all_levels` keyword defaults (OR 30, gates False, different MA/VWAP/POC/ticks). Do not compare them as the same experiment without a new `LevelsIdentity`.
2. **Classic snapshot helper is not the API normalizer.** Missing Stage 6 keys → OFF / ticks 1 on the page; product fill on the API.
3. **`session` is membership; `trading_session_date` is CME date.** Every date-grouped family in `levels/` calls `trading_session_date` (Q7). Week/month keys are session-date periods, not calendar-midnight weeks.
4. **Missing `session`:** `sessions.py` does **not** re-tag (NaN session-dependent). `session_vwap` / `tpo` / `apoc` / `prev30m` re-tag with `tag_session(df, instrument)` using the compute instrument. UI tags first; API `compute_levels` does not.
5. **Clock-gated families (OR, Asia, London, APOC, TPO brackets, prev30m freeze) emit on clock, not on full bar coverage.** Incomplete in-window data is a valid emit. Empty window → NaN. No empty-bar synthesis.
6. **`prev30mVWAP_hit_m1/m5` are diagnostics.** Not setup-eligible, not plot-default. `prev30mVWAP` / `prev30mVWAP_k` are price levels. `build_setup` / `generate_signals` / Study tokens must keep rejecting hits.
7. **Same-bar close** is included in SMA/EMA/rolling VWAP/POC/dVWAP typical price. Signals are bar-close confirmed (ASSUMPTIONS). Intrabar use of those columns is a known limitation, not a future-bar leak.
8. **4h (and any calendar resample) on this layer is not a CME session day** (Slice 1 contract 7). Product default enables `Pivot_4h_*` and `VWAP_rolling_4h`.
9. **Second `compute_session_levels` in UI and `api.compute_levels` is redundant and currently argument-identical** (same instrument, same OR minutes, same frame). Cache returns the written pair.
10. **Goldens / stage1 default-off tests prove identity of the legacy additive API, not product-default correctness or PIT.**

---

## 7. Contracts still **open** (do not assume)

1. Whether `sessions.py` will ever re-tag missing `session` (parity with gated families) or stay fail-closed.
2. Whether `api.compute_levels` will tag like the UI / `load_dataset`.
3. Whether the redundant `session_levels` compute will be replaced by a column slice of `levels`.
4. Whether the PIT table will gain future-shock rows for `dOpen*`, `prevSettlement`, `pm` profile, OR, and asserted `pw*`/`pm*` structural columns.
5. Whether clock-incomplete OR/Asia/London/APOC will gain a “coverage ratio” or stay silent-incomplete.
6. Whether UI `_normalize_levels_settings` and `normalize_levels_config` will ever share one function (would change old-snapshot identity).
7. Whether `Pivot_4h` should be session-anchored (today: no).
8. Golden-master: still **identity**, not levels correctness.

---

## 8. How Slice 3 should start

1. Treat §6 as the levels/PIT contract. Do not re-audit `trading_session_date` math or loader TZ.
2. When selecting columns for confluence, use `available_level_columns` / `validate_setup_config` — never raw `levels.columns` (hits + OHLCV + `session` would leak).
3. Do not treat `session_levels` as a different OR/instrument compute; it is the same structural function. Do not treat it as a per-session table.
4. If a setup names `Pivot_4h_*` or `VWAP_rolling_4h`, those values are midnight-origin, not `eth_start`.
5. If a test or Study cell calls `compute_all_levels` without going through `normalize_levels_config`, it is **not** the product default experiment.
6. Naked/confluence causality is inherited: if you add a new level family, it needs a future-shock row in `POINT_IN_TIME_GUARANTEES.md`, not a golden.

---

## 9. How Slice 2 started (traceability)

Read Slice 0 map (module table, UI vs API composers, goldens ≠ correctness) and Slice 1 locked contracts. Re-verified `trading_session_date` **usage** in every `levels/` family; did not re-audit `session_date.py`. Scoped to `thesistester/levels/` (except `session_date` math), `normalize_levels_config`, `api.compute_levels`, `pages/2_Levels.py`, the named tests, and the listed docs. Did not enter `engine/confluence.py`, `engine/signals*.py`, backtest, OTF, Study execution, or `analytics/prev30m_vwap_hit.py`.
