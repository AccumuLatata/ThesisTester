# ThesisTester audit Slice 3 — Setup, confluence, naked, signals, 3c

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390), Slice 1 (`AUDIT_SLICE1.md`, PR #391), Slice 2 (`AUDIT_SLICE2.md`, PR #392). Prior **locked contracts** are treated as given; level math / `trading_session_date` / loader TZ were not re-audited.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/test_setup_config.py`, `test_setup_builder_helpers.py`, `test_phase4_engine.py`, `test_anchor_confluence.py`, `test_candidate_level.py`, `test_signals_3c.py`, `test_signals_3c_trigger_timeframe.py`, `test_signals_page_helpers.py`, `test_3c_mode_integration.py`, `test_r3_point_in_time.py` — **357 passed**.
**Runtime probes (not committed tests):** `validate_setup_config` accepts `selected_levels=["close","ONH"]`; `api.build_setup` + `api.generate_signals` emit `close|ONH` zones and 3 touch signals; hits are rejected; `generate_signals(trigger="confirm_3bar")` raises; OTF is stored on `signal_settings` and is absent from signal columns.
**Goldens:** not used as correctness proof. Goldens remain a **legacy-unchanged identity** gate (`docs/ENGINEERING_PROPOSAL.md` §4). They do not prove 3c fill/void index honesty, naked arrival-bar filtering, or trigger-TF alignment.

This file is the Slice 3 deliverable. Later slices must treat the **locked contracts** in §5 as given, and the **open items** in §6 as still unverified outside this layer.

---

## 0. Contracts used here (not re-proven)

### From Slice 1

1. `session` ≠ `trading_session_date`.
2. 15s-derived 1m ≠ vendor 1m.
3. 1D/4h resample is midnight-origin, not a CME session.
4. Rolls never rewrite prices.
5. R12 data contract is coverage/reconcile, not fills.

### From Slice 2 (do not re-audit level math / `trading_session_date`)

1. Two settings planes: product = `DEFAULT_LEVELS_SETTINGS` via `normalize_levels_config`; library = `compute_all_levels` keyword defaults. Bare `compute_all_levels(df)` is **not** the product experiment.
2. Classic `_normalize_levels_settings` ≠ API normalizer (old snapshots → advanced OFF / ticks 1).
3. `session` is membership; `trading_session_date` is CME date.
4. Missing `session`: `sessions.py` does not re-tag; gated families do. UI tags first; `api.compute_levels` does not.
5. Clock-gated families emit on clock; incomplete in-window data is a valid emit.
6. `prev30mVWAP_hit_m1/m5` are diagnostics, **not** setup-eligible. `prev30mVWAP` / `_k` are price levels. `build_setup` / `generate_signals` / Study must keep rejecting hits.
7. Same-bar close is included in SMA/EMA/rolling VWAP/POC/dVWAP — known limitation, not future-bar leak.
8. 4h calendar resample is not a CME session. Product default enables `Pivot_4h_*` and `VWAP_rolling_4h`.
9. Second `compute_session_levels` is redundant and currently argument-identical. `session_levels` is **not** a per-session table.
10. Goldens prove identity, not correctness.

**Inherited causality:** naked/confluence/signals inherit level causality. If a setup names `Pivot_4h_*` or `VWAP_rolling_4h`, those values are midnight-origin. Column selection for confluence must use `available_level_columns` / `validate_setup_config` — never raw `levels.columns`.

---

## 1. Architecture of the setup / zone / signal layer

### 1.1 What this layer owns

This layer turns a **setup config** + a **levels frame** into:

- confluence **zones** (global cluster or anchor rules)
- `<level>_naked` flags (forward scan)
- candidate **signal rows** (`touch` / `reject` / `break` / `reclaim` / `3c`)

It does **not** apply OTF admission, Admit, or `simulate_trades`. Setup may **store** `otf_filter` and `entry_window`; application is Slice 4.

```text
levels frame (OHLCV + level columns + optional hits)
        │
        ▼
setup_config  (thesistester/setup.py)
        │  selected_levels / anchor+rules / trigger / TF / 3c params
        │  otf_filter stored (default off) — NOT applied
        │
        ├─ detect_confluence_zones          engine/confluence.py
        │     or detect_anchor_confluence_zones  engine/anchor_confluence.py
        ├─ flag_naked_levels                engine/naked.py
        └─ generate_signals                 engine/signals.py
              ├─ simple: trigger-TF OHLC vs zone envelope
              └─ 3c: CandidateLevel per zone-level → signals_3c.py
                    base: detect_3c_setups
                    non-base: project zones → detect_3c_setups_with_trigger_timeframe
```

### 1.2 Two composers (same functions, different gates)

| Path | Entry | Setup gate | Zone engine | OTF at generation? |
|---|---|---|---|---|
| Classic UI | `pages/6_Signals.py` | Manual: `available_level_columns` picker. Saved/active: `validate_setup_config` **plus** compatibility vs `available_level_columns` (Generate disabled on blockers) | page calls `detect_*` then `engine.generate_signals` | **No.** Caption + sidebar state the later-admission contract |
| Headless API | `api.build_setup` → `api.generate_signals` | `validate_setup_config` only | API calls the same engines | **No.** `apply_configured_otf_filter` is only in `api.run_backtest` / `run_grid` |
| Study / CLI / Assistant | `api.run_experiment` → `api.generate_signals` | same as API (schema trigger allow-list = `VALID_TRIGGERS`; **no** `is_setup_eligible` in `study/schema.py`) | same as API | **No** at this stage |

`pages/3_Setup_Builder.py` is the setup library / editor. It stores `otf_filter` (default disabled) and builds configs via `build_setup_config` + `validate_setup_config`. It does not generate signals.

UI pages compose `thesistester.engine` **directly**. They do not call `api.generate_signals`. Parity is a tested composition contract, not a shared function.

### 1.3 Row contracts (what a later slice may consume)

**Zone row (global)** — `confluence.py` `_ZONE_COLUMNS`:
`timestamp`, `bar_index` (canonical/base), `zone_low/high/mid`, `level_count`, `level_names` (`|`), `level_prices` (`|`).

**Zone row (anchor)** — adds `confluence_mode`, `anchor_level`, `anchor_price`, `valid_confluence_count` (rules only; **excludes** anchor), `required_valid`, `rule_results` (JSON of all rules, valid and invalid). `level_names` / `level_count` **include** the anchor plus valid rules only.

**Naked frame** — copy of input with `<level>_naked` bools. Formation bar is marked naked and **never touch-tested** (`naked.py`). Status at bar `i` uses bars `0..i` only.

**Signal row** — `signals.py` `_SIGNAL_COLUMNS`. Critical fields for Slice 4:

| Field | Simple (`touch/reject/break/reclaim`) | `3c` filled | `3c` void |
|---|---|---|---|
| `bar_index` / `timestamp` | canonical bar at **trigger-candle end** (`base_end_bar_index` / `base_end_timestamp`) | canonical **retrace fill** bar | canonical **reversal** bar |
| `trigger_timestamp` | trigger-candle **completion** (`trigger_bar_end_timestamp`; equals `timestamp` on `base`) | reversal trigger-candle completion | same |
| `trigger_bar_index` | trigger-df index | trigger reversal index (base 3c: equals base reversal) | same |
| `entry_model` | `candidate_next_bar_open` | `3c_retrace_market` | `3c_retrace_void` |
| `status` | `candidate` | `filled` | `void` |
| `entry_bar_index` / `retrace_entry_price` | unused | set | `None` |
| `arrival_bar_index` | unused | canonical arrival (non-base: trigger arrival `base_end`) | same |

Signals are **never** backdated to the 3c arrival bar. `trigger="confirm_3bar"` is **not** in `VALID_TRIGGERS`.

### 1.4 Two objects that must not be conflated

| Object | Used by | Price tested |
|---|---|---|
| Zone envelope `[zone_low, zone_high]` | simple triggers | whole band |
| `CandidateLevel.level_price` (one row per `level_names` member) | `3c` | each level independently, then merge by `(rounded price, direction, arrival_bar, source_mode)` |

`from_global_cluster_zones` / `from_anchor_zones` expand one zone into N candidates. A `3c` signal can therefore attach to one level inside a multi-level zone.

---

## 2. Must-answer questions

### Q1. Non-base 3c: is retrace monitoring strictly after trigger-candle completion, and is `max_entry_wait_bars_after_reversal` counted only in trigger TF?

**Yes, with a tested half-open time window — not a count of completed trigger candles.**

`detect_3c_setups_with_trigger_timeframe` (`signals_3c.py`):

- Structure (arrival / inside / SFP / reversal) is evaluated on `trigger_df`.
- Retrace scan starts at `base_reversal_idx + 1` and requires `base.timestamp > reversal_trigger_ts` where `reversal_trigger_ts = trigger_bar_end_timestamp`.
- Window end: `window_end_ts = reversal_trigger_ts + max_wait * trigger_timeframe_delta`.
- Eligible: `reversal_trigger_ts < b_ts <= window_end_ts`.

**Bad case (documented by tests, not a lookahead):** 1-min base, 5-min trigger, reversal candle `[09:35, 09:40)` → `trigger_bar_end_timestamp = 09:40`. The 09:40 1-min bar (first bar **at** completion) is **excluded**. First eligible bar is 09:41. Encoded in `test_base_bar_before_reversal_ts_does_not_fill` and the comment “base 10 ts=09:40 not eligible” in `test_fill_after_window_end_not_allowed`.

README (“after reversal trigger candle completion”) is true in the conservative sense (no fill inside the reversal HTF candle) and **stricter** by one base bar than “first bar whose open equals completion.”

`max_wait` is a **duration** (`max_wait * TF delta`), not “N subsequent completed trigger rows.” `resolved_through_trigger = t_rev_idx + max_wait` is only for overlapping-setup suppression (`active_until_by_key`). `max_wait=0` → empty window → always void (`test_max_entry_wait_counts_trigger_bars_not_base_bars`).

Base 3c (`detect_3c_setups`) counts **base** bars: `watch_end = reversal_idx + max_wait`, scan `reversal_idx+1 .. watch_end`.

### Q2. Naked filter: arrival-bar only in all confluence modes (global + anchor + 3c sources)?

**Zone-admission is at `zone["bar_index"]`. That equals 3c arrival only on base TF. It is not per-level for 3c.**

`generate_signals` (`signals.py`):

```text
ncount = _naked_count(level_names, zone.bar_index, naked_flags)
naked_only + any  → drop if ncount == 0
naked_only + all  → drop if ncount < level_count
```

Then remaining zones become 3c candidates (global or `_source_mode == "anchor_rules"`).

| Path | Naked lookup index | Per-level 3c reject? |
|---|---|---|
| Simple, any TF | zone `bar_index` (simple non-base **also** requires `bar_index == trigger base_end`, so this is trigger-end) | N/A (zone envelope) |
| 3c base | zone `bar_index` == candidate arrival | **No.** `naked_only=any` admits the zone; 3c may fire on a **tested sibling** level |
| 3c non-base | **Filter** uses original **base** zone `bar_index` (any intra-window zone row that survived). **Metadata** `was_naked_before_arrival` uses trigger arrival `base_end_bar_index` | **No** per-level reject |

Non-base 3c metadata path (`signals.py` `trigger_base_end_map`) is arrival-bar-at-HTF-end. The **filter** is not. `_project_zones_to_trigger_df` maps every intra-window zone onto the same trigger bar.

**Bad case:** 5-min trigger, developing or static level naked at minute 1 of the window, touched at minute 3. Zone row at minute 1 passes `naked_only`; it projects to the 5-min arrival candle; 3c evaluates the **full** 5-min OHLC. Filter and arrival clock disagree.

`flag_naked_levels` itself is PIT-safe (forward scan; `test_naked_flags_future_shock`). Formation bar is never touch-tested — a same-bar form+touch stays naked (`naked.py` notes).

Product composers pass `naked_flags` into `generate_signals` **only when `naked_only`** (UI and `api.generate_signals`). `was_naked_before_arrival` is therefore usually `None` unless the filter is on.

Covered: `TestNakedFilter` in `test_phase4_engine.py` (simple + base zone bar). **Not covered:** non-base 3c naked_only; 3c + `any` sibling; anchor vs global naked parity.

### Q3. Does any chart or saved-run path rewrite `bar_index` / `timestamp` after generation?

**No value rewrite. Save reorders rows.**

| Path | Mutates `bar_index` / `timestamp` cells? |
|---|---|
| `visualization/signals_chart.py` | No. Plots `signals["timestamp"]` vs `entry_reference_price`. Hover has no `bar_index` / `trigger_timestamp`. |
| `visualization/levels_chart.py` | No. Plots level columns vs `levels_df["timestamp"]`. |
| `pages/6_Signals.py` display | No. Dataframe of generated/loaded columns. |
| `save_signal_run` | `_canonicalize_dataframe` **sorts by `timestamp`** and `reset_index` (`local_store.py`). Values kept; row order / RangeIndex change. |
| `load_signal_run` | `read_parquet` as stored. No recompute. |

Charts can **imply** causality: a filled 3c marker sits at the **fill** timestamp, not at reversal/`trigger_timestamp`. That matches the row contract; it hides decision time. Not a rewrite.

### Q4. Is `confirm_3bar` unreachable from UI/API/Study, or still callable via a back door?

**Unreachable from product generation. Helper and execution still know the name.**

| Surface | `confirm_3bar`? |
|---|---|
| `setup.VALID_TRIGGERS` / `signals.VALID_TRIGGERS` | absent |
| `validate_setup_config` / `build_setup_config` | rejected (`test_invalid_trigger_invalid`) |
| `generate_signals` | `ValueError` (`test_confirm_3bar_is_no_longer_valid_trigger`; probe confirmed) |
| Setup Builder / Signals widgets | `["touch","reject","break","reclaim","3c"]` |
| Study schema | imports `VALID_TRIGGERS` |
| `_check_confirm_3bar` | **still public-ish**; PIT test calls it directly |
| `engine/backtest.py` / WFA entry helper | still branch on `trigger == "confirm_3bar"` (Slice 4: hand-built rows) |

No UI/API/Study composer can emit `trigger="confirm_3bar"` through `generate_signals`. The back door is **import + helper**, or a **hand-built signal row** into `simulate_trades`.

### Q5. OTF is NOT applied at signal generation — confirm all composers.

**Confirmed. Stored, not applied.**

| Composer | Evidence |
|---|---|
| `engine.generate_signals` | no `otf` import / call |
| `api.generate_signals` | builds zones/naked/signals only; `_normalize_signal_settings_for_hash` **stores** `otf_filter` from `setup_snapshot` |
| `pages/6_Signals.py` | caption: “OTF admission is applied later in Backtest, Grid, and Walk-forward — not on this page.” Generate path does not call `apply_configured_otf_filter` |
| `pages/3_Setup_Builder.py` | stores `otf_filter` via `normalize_otf_filter_config` |
| `api.run_backtest` / `run_grid` | **do** call `apply_configured_otf_filter` (Slice 4) |

Probe: `api.generate_signals` result has `signal_settings["otf_filter"]` (default disabled) and **zero** `otf*` signal columns. Full candidate population is emitted (`README` / ARCHITECTURE / Slice 0).

Config provenance (not re-audited as admission): a saved run’s `signal_settings["otf_filter"]` wins later; regenerate to pick up Setup Builder edits.

### Q6. Can hit columns / OHLCV / `session` leak into confluence as fake prices if validate is bypassed?

**Hits: blocked by `validate_setup_config`. OHLCV / `session`: UI gated, API/engine not.**

| Column class | `is_setup_eligible` / `available_level_columns` | `validate_setup_config` | Engine `detect_confluence_zones` |
|---|---|---|---|
| `prev30mVWAP_hit_m1/m5` | excluded (`NON_LEVEL_OUTPUT_COLUMNS`) | **rejected** | would treat 0/1 as prices near zero if passed |
| `timestamp/open/high/low/close/volume/session/settlement` | excluded (`BASE_COLUMNS`) | **accepted** | numeric OHLCV/`volume`/`settlement` cluster as prices; `session` strings fail `float()` and are skipped |
| real level columns | included | accepted (existence **not** checked in global mode) | used as-is |

**Bad case (probed):** `selected_levels=["close","ONH"]` → `validate_setup_config` → `[]`. `api.build_setup` accepts. `api.generate_signals` emits zones `close|ONH` and 3 touch signals. `available_level_columns` returns only `["ONH"]`.

UI:

- Manual picker options = `available_level_columns` (cannot pick `close` / hits).
- Saved/active: `_saved_setup_generation_blockers` flags anything **not** in `available_level_columns` → Generate disabled. So UI treats OHLCV as “unavailable,” even though validate would not.

Engine has **no** eligibility check. Direct `detect_confluence_zones(df, ["close","ONH"], ...)` is the bypass. `test_setup_config.py` asserts picker exclusion of `BASE_COLUMNS` and does **not** assert validate rejects them. Hit rejection is tested in `test_prev30m_vwap.py` (Slice 2), not in the Slice 3 setup suite.

Global API silently **drops** missing level names (`present_cols` filter). Anchor API **raises** on missing columns. Composer asymmetry.

### Q7. 3c 4-rule / 8-variant model vs code: `arrival_tolerance_ticks` ignored? never backdate to arrival? fill vs void index semantics?

**Model matches code. Tolerance forced to 0. Never backdated. Fill/void index as documented.**

**4 rules (long)** — `detect_3c_setups` / non-base analog:

1. Arrival touches/passes: `low <= level` (tol forced 0).
2. Arrival closes above: `close > level`.
3. Reversal closes above arrival **high** (`close > bar1_high`); consecutive **inside** candles (`high <= arr_high and low >= arr_low`) are skipped (muted).
4. After reversal, first bar with `low <= reversal_close - retrace_ticks * tick` fills.

Short is the mirror. SFP = reversal **and** sweep of the opposite arrival extreme. Eight variants via `_variant()`; `test_variants_long_short_muted_sfp` covers all eight.

`arrival_tolerance_ticks`: `_normalize_3c_params` in `setup.py`, `signals.py`, and `signals_3c.py` **always** writes `0.0`. `_find_tested_level_for_arrival` (legacy `confirm_3bar` only) hardcodes `tol = 0.0`. `test_legacy_config_with_nonzero_arrival_tolerance_is_ignored`.

**Never backdate:** `bar_index` / `timestamp` = entry bar if filled, else reversal bar. `test_3c_signals_not_backdated`, PIT table, README Phase 4.

**Fill vs void:**

| | `status` | `bar_index`/`timestamp` | `entry_bar_index` | `retrace_entry_price` | `entry_model` |
|---|---|---|---|---|---|
| fill | `filled` | fill bar | fill | trigger price | `3c_retrace_market` |
| void | `void` | reversal bar | `None` | `None` | `3c_retrace_void` |

Non-base adds `trigger_arrival_bar_index` / `trigger_reversal_bar_index` / `trigger_timestamp`. Invariant in `detect_3c_setups_with_trigger_timeframe` docstring: those three are trigger-df indices; `arrival/reversal/entry/bar_index` are canonical.

`confirm_3bar` is a **different** 3-bar model (bar3 same-bar fill, optional `arrival_tolerance` ignored in the helper’s arrival finder). It is not the product 3c.

### Q8. Trigger TF (`base`/`1min`/`5min`/`15min`): `bar_index`/`timestamp` vs `trigger_timestamp` alignment for simple triggers and 3c?

**Aligned as README Phase 4 states, given trigger TF ≥ base and regular bars.**

`_prepare_trigger_dataframe`:

- `base`: identity; `trigger_bar_end_timestamp = timestamp`.
- else: DST-safe UTC floor → group OHLC; levels/`session`/hits aggregated **`last`**; `trigger_bar_end = start + TF delta`; `base_end_*` = last base bar in the bucket.

| Trigger | `bar_index` / `timestamp` | `trigger_timestamp` |
|---|---|---|
| Simple `base` | trigger bar = base bar | same |
| Simple non-base | **only** zones whose `bar_index == base_end_bar_index` (intra-window zones dropped) | HTF completion |
| 3c `base` | fill or reversal base bar | **reversal bar `timestamp`** (not fill) |
| 3c non-base | fill or reversal **base** bar | reversal **HTF completion** |

**Bad case (unguarded):** trigger TF **finer** than base (5-min data + `1min` trigger). No fail-closed check. Floor groups each 5-min bar as a 1-min bucket with 5-min OHLC and a 1-min wait delta. Product widgets always offer `1min`. Typical research data is 1-min, so this is residual unless someone loads a coarser canonical frame.

Incomplete last HTF group (dataset ends mid-bucket) is treated as a complete trigger candle (same class as Slice 2 clock-incomplete emit).

Simple non-base + **developing** levels: trigger OHLC is the full HTF range; zone prices are as-of **base_end** only. A mid-window extreme can “touch” a zone that only existed at the last minute. Not future-bar leak (decision `T` = HTF close); it is HTF-range vs last-bar level. Static levels (`pdHigh`) are honest.

### Q9. Global cluster vs anchor-based confluence: tick tolerances, required/optional rules, zone diagnostics honesty?

**Two engines, two honesty levels. Both per-bar / no lookahead.**

| | Global (`detect_confluence_zones`) | Anchor (`detect_anchor_confluence_zones`) |
|---|---|---|
| Tolerance | one shared `tolerance_ticks` (price range ≤ `tol * tick_size`) | per-rule `tolerance_ticks`; `distance_ticks = abs(price-anchor)/tick`; valid iff `<= tol + 1e-9` |
| Membership | greedy sliding window, **non-overlapping**; `max_confluences` cap 5 | all **required** valid **and** `valid_count >= min_valid_confluences` |
| Optional rules | N/A | may fail; still in `rule_results`; not in `level_names` |
| Diagnostics | envelope + names/prices only | full per-rule audit (`reason`: `within_tolerance` / `outside_tolerance` / `missing_price` / `missing_column`) |
| `level_count` | capped cluster size | `1 + valid_confluence_count` (anchor included) |
| `tick_size <= 0` | not checked | `ValueError` |
| Missing columns | silent skip | required missing → no zone; optional missing → recorded, zone may still emit |

**Honesty issues:**

1. Greedy `j = k` after emit: if 6 levels fit in tolerance, first 5 are emitted (`max_confluences`) and the 6th is **skipped entirely** (cannot form a leftover cluster).
2. Duplicate prices count as separate members.
3. `ANCHOR_CONFLUENCE.md` does not say `level_count` includes the anchor. Signals page expands `rule_results` honestly (`_parse_anchor_rule_results`).
4. Negative tolerances: validate rejects; raw engine would make clustering/validity nearly impossible (not product-reachable).

Future-shock: `test_confluence_zones_future_shock`, `test_anchor_confluence_future_shock` — identity of zones at `T`, not “the greedy grouping is the right research object.”

### Q10. Test gaps vs README / PIT claims. Goldens ≠ correctness.

PIT (`docs/POINT_IN_TIME_GUARANTEES.md`) claims that match code for **base** simple + **base** 3c + naked forward scan + per-bar zones. Gaps:

| Claim / area | Tests | Gap |
|---|---|---|
| Non-base 3c retrace after completion + TF wait | `test_signals_3c_trigger_timeframe.py` (strong) | no future-shock on non-base 3c |
| Never backdate 3c | `test_3c_signals_not_backdated` (base only) | void/fill index on non-base covered in TF file; PIT future-shock is base |
| `arrival_tolerance` ignored | `test_signals_3c.py` | — |
| 8 variants | `test_variants_long_short_muted_sfp` | — |
| Naked at arrival, all modes | simple base only | no 3c / no non-base / no `any` sibling |
| Hits rejected | `test_prev30m_vwap.py` (out of Slice 3 suite) | `test_setup_config.py` does not assert hit or `BASE_COLUMNS` reject |
| OHLCV cannot be a level | picker test only | **API accepts `close`** (probe) |
| `confirm_3bar` not public | phase4 + PIT helper | backtest still implements it (Slice 4) |
| OTF not applied here | README + composer inspection + probe | no dedicated “generate_signals never calls apply_otf” unit in this slice’s files (`test_otf_integration` notes import unchanged) |
| Trigger TF finer than base | none | unguarded |
| Intra-window zone projection for non-base 3c | projection unit test | no developing-level stale-price case |
| Goldens | not in this slice | identity ≠ 3c/naked/TF correctness |

`test_3c_mode_integration.py` only asserts `level_source_mode` (`global_cluster` vs `user_anchor`).

---

## 3. Prioritized findings

### High

1. **`validate_setup_config` does not reject `BASE_COLUMNS`.** Headless `api.build_setup` + `api.generate_signals` will cluster `close` (or `volume`/`settlement`) with real levels and emit signals. UI pickers and saved-setup compatibility use `available_level_columns`, so the classic path is gated. Engine has no second check. **Bad case:** `selected_levels=["close","ONH"]` → 3 `close|ONH` zones and 3 touch signals (runtime probe). Hits remain rejected (Slice 2 contract held).

2. **Non-base 3c projects every intra-window zone onto the trigger candle.** Simple triggers keep only `base_end` zones. For developing levels (`dVWAP`, SMA, rolling VWAP/POC), a mid-window zone price is tested against the **completed** HTF OHLC. Decision time is HTF close (not a future-bar leak); the **level-as-of** is stale. Static levels are unaffected.

3. **`naked_only` is zone-admission, not per-`CandidateLevel`.** Combined with (2), non-base 3c can admit on an early-window naked bar and evaluate arrival on the full HTF candle. `naked_only=any` + 3c can fire on a tested sibling inside an admitted zone.

### Medium

4. **No fail-closed when trigger TF is finer than the canonical interval.** Widgets always offer `1min`. Coarse base + `1min` trigger yields 1-min labels on coarser OHLC and a 1-min 3c wait.

5. **Non-base 3c wait window is `(reversal_end, reversal_end + max_wait*Δ]`**. Skips the completion-timestamp base bar. README is slightly looser (“after completion”). Implemented duration ≠ “N completed trigger candles.” Incomplete HTF stubs are treated as complete candles.

6. **Global greedy cap discards leftover levels** (`j = k` after `max_confluences`). Anchor `level_count` includes the anchor; `valid_confluence_count` does not — easy to misread diagnostics.

7. **Simple triggers use the zone envelope; 3c uses per-level prices.** Same setup, different tested object. Not documented as a first-class split in README Phase 4.

8. **Missing global level columns are dropped silently** in the engine/API; anchor missing columns raise (API) or block (UI).

9. **`naked_flags` are omitted from `generate_signals` unless `naked_only`.** Stored frames still have flags; signal metadata `was_naked_before_arrival` is usually empty.

### Low

10. **Signals chart plots fill/void `timestamp`, not `trigger_timestamp`.** Display can be read as “signal time = fill time.” No engine rewrite.

11. **Saved-run canonicalize sorts by `timestamp`.** Values unchanged; order may change.

12. **`confirm_3bar` helper remains** for PIT/backtest. Product generation is closed.

13. **`levels_chart` / `signals_chart` do not filter eligibility.** They plot whatever `selected_levels` the page passes. Pages pass picker/setup lists.

---

## 4. Residual risks (not closed here)

- Composer drift: UI cannot select `close`; API/Study can. Slice 6/7 must not assume validate ≡ eligible.
- Non-base 3c + developing levels: stale intra-window zone price vs HTF range (finding 2).
- Formation-bar naked = True even if that bar traded the level (`naked.py` MVP note).
- Same-bar close in SMA/EMA/VWAP/POC/dVWAP (Slice 2 #7) is inside every zone/signal that uses those columns. Signals are bar-close confirmed.
- 4h / midnight-origin levels in a setup (Slice 2 #8) flow through as ordinary prices.
- `_prepare_trigger_dataframe` aggregates **all** non-OHLC columns as `last`, including `session` and hit flags. Harmless unless those columns are selected as levels.
- Overlapping 3c setups on the same rounded price are suppressed via `active_until` (causal: earlier arrival owns the level until fill/void/invalidation). Slice 4 `allow_all` exposure can still stack **simple** overlaps.
- Hand-built `confirm_3bar` rows into `simulate_trades` (Slice 4).
- Goldens / Phase 4 tests prove identity and local fixtures, not “zones are the correct market object.”

---

## 5. Contracts Slice 4+ must treat as **locked**

1. **OTF is not applied at generation.** All composers emit the full candidate population. `otf_filter` on the setup / `signal_settings` is provenance for later admission. Decision `T` for OTF (when applied) is `trigger_timestamp` if present else `timestamp` (`docs/POINT_IN_TIME_GUARANTEES.md` / `otf-filter.md`) — do not use 3c fill `timestamp` as `T`.

2. **Public triggers** are only `touch`, `reject`, `break`, `reclaim`, `3c`. `confirm_3bar` cannot be generated through UI/API/Study. Execution may still see the string on hand-built rows.

3. **Simple entry model** is `candidate_next_bar_open` at `bar_index` = canonical trigger-end. **3c filled** enters at `retrace_entry_price` on `entry_bar_index` (`3c_retrace_market`). **3c void** is `3c_retrace_void` and must not fill.

4. **3c index contract:** never backdate to arrival. Filled → fill bar; void → reversal bar. Non-base: `trigger_*` indices are trigger-df; `arrival/reversal/entry/bar_index` are canonical. Retrace eligible iff `timestamp > trigger_bar_end` and `<= end + max_wait*Δ`.

5. **`arrival_tolerance_ticks` is ignored** (effective 0) on every normalize path.

6. **Naked filter** is zone-admission at `zone.bar_index` (simple non-base: that is trigger-end). 3c does not drop individual tested siblings when `naked_requirement="any"`.

7. **Column eligibility:** hits must stay rejected by validate. `available_level_columns` is the only gate that also excludes OHLCV/`session`. Raw `levels.columns` or validate-only headless configs can leak `close` as a fake price.

8. **Two confluence engines.** Global = shared tick window, greedy, cap 5, no per-rule audit. Anchor = per-rule ticks, required/optional, `min_valid_confluences` counts **rules only**, diagnostics in `rule_results`. Causality is per-bar, inherited from levels.

9. **Two tested objects.** Simple = zone envelope. 3c = each `level_prices` member via `CandidateLevel`.

10. **Charts / parquet do not recompute `bar_index` / `timestamp`.** Save may sort by timestamp.

11. **Goldens ≠ correctness** of this layer.

12. **Trigger TF allow-list** is `base|1min|5min|15min`. Alignment above assumes trigger TF ≥ base and pandas start-label bars.

---

## 6. Contracts still **open** (do not assume)

1. Whether `validate_setup_config` will ever reject `BASE_COLUMNS` (today: no).
2. Whether non-base 3c will keep intra-window zone projection or snap to `base_end` like simple triggers.
3. Whether `naked_only` will become per-`level_id` for 3c.
4. Whether trigger TF finer than base will fail closed.
5. Whether the completion-timestamp base bar will become eligible for 3c retrace (tests currently forbid it).
6. Whether `confirm_3bar` will be deleted from `signals.py` / `backtest.py`.
7. Whether product path will pass `naked_flags` into `generate_signals` when `naked_only` is false (diagnostics only).
8. Whether PIT will gain non-base 3c / non-base simple future-shock rows.
9. Golden-master: still **identity**, not signal/3c correctness.

---

## 7. How Slice 4 should start

1. Treat §5 as the signal/zone/naked/3c contract. Do not re-audit level formulas, `trading_session_date`, or 3c 4-rule math except where **execution** reads the row.
2. Consume: `entry_model`, `status`, `entry_bar_index`, `retrace_entry_price`, `trigger_timestamp`, `bar_index`. For OTF, `T = trigger_timestamp` else `timestamp` — for filled 3c that is **reversal completion**, not fill.
3. Do not treat `confirm_3bar` as a product trigger; do audit the residual fill branch if `simulate_trades` still implements it.
4. Non-base 3c retrace must not fill on bars with `timestamp <= trigger_bar_end_timestamp`. `max_wait` is a TF **duration**.
5. OTF/Admit apply **after** this layer. A disabled `otf_filter` on `signal_settings` is not “OTF ran and passed.”
6. UI Backtest vs `api.run_backtest` are two composers (Slice 0). Do not assume pages call `api.generate_signals`.
7. Goldens prove default-off pipeline identity, not fill correctness.

---

## 8. How Slice 3 started (traceability)

Read Slice 0 map (module table, UI vs API composers, “OTF not applied here,” goldens ≠ correctness), Slice 1 locked clocks, and Slice 2 §6 levels/PIT contracts. Did not re-audit `trading_session_date`, family math, `simulate_trades`, or `otf_filter.py` admission.

Scoped to `thesistester/setup.py`; `engine/confluence.py`, `anchor_confluence.py`, `candidate_level.py`, `naked.py`, `signals.py`, `signals_3c.py`; `api.build_setup` / `api.generate_signals`; `pages/3_Setup_Builder.py`, `pages/6_Signals.py`; `visualization/signals_chart.py`, `levels_chart.py`; the named tests; `docs/ANCHOR_CONFLUENCE.md`; README Phase 4 / 3c; PIT signals/naked/confluence sections.

Did not enter `simulate_trades`, OTF admission, Admit, grid, WFA, or Study execute (Study schema trigger allow-list and missing eligibility check noted only as a composer residual).
