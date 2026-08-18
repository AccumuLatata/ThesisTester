# ThesisTester audit Slice 4 — Execution (fills, OTF, Admit, R12, R13)

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390), Slice 1 (`AUDIT_SLICE1.md`, PR #391), Slice 2 (`AUDIT_SLICE2.md`, PR #392), Slice 3 (`AUDIT_SLICE3.md`, PR #393). Prior **locked contracts** are treated as given; 3c 4-rule math, level formulas, and `trading_session_date` arithmetic were not re-audited except where execution **reads the row** or **resamples HTF**.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** `tests/test_phase5_backtest.py`, `test_sim_core.py`, `test_intrabar.py`, `test_exit_management.py`, `test_otf.py`, `test_otf_filter.py`, `test_otf_integration.py`, `test_otf_contract.py`, `test_otf_baseline.py`, `test_entry_window_admission.py`, `test_entry_window_sw2b.py`, `test_entry_window_sw3.py`, `test_backtest_grid_defaults.py`, `test_golden_master.py`, `test_otf_golden.py`, `test_entry_window_golden.py` — **705 passed**.
**Runtime probes (not committed tests):** session-flatten `entry_local_ts` leak across candidates; 3c void never fills; residual `confirm_3bar` still fills; `sl_first` 3c uses the full parent bar (pre-entry SL); `allow_all` stacks overlapping simple+3c; OTF `T = trigger_timestamp`; 1D/4h OTF rejected; disabled OTF stamps `otf_filter_passed=True`; Admit uses entry-bar time; `None` vs disabled window are admission-identical; sub-bar entry+SL+TP is SL and never TP; API cutoff works without flatten.
**Goldens:** not used as correctness proof. Three families remain **identity / drift gates** (`docs/ENGINEERING_PROPOSAL.md` §4). They do not prove fill, flatten, R12 residual, R13, cost, or exposure correctness.

This file is the Slice 4 deliverable. Later slices must treat the **locked contracts** in §5 as given, and the **open items** in §6 as still unverified outside this layer.

---

## 0. Contracts used here (not re-proven)

### From Slice 1

1. `session` ≠ `trading_session_date`. `eth_start=18:00` is the CME date contract; `rth_*` is RTH membership.
2. 1D/4h resample is midnight-origin, **not** a CME session. OTF/HTF must not treat it as one.
3. Session flatten (ASSUMPTIONS) is **same-calendar-day RTH-style**, not ETH overnight / not `trading_session_date`.
4. R12 **data** contract: no upsample, no interpolation, volume not reconciled. Conservative incomplete can attach. Fill models are this slice.

### From Slice 2

1. Date-grouped levels use `trading_session_date`. Clock `session` is membership only.
2. 4h pivot / 4h rolling VWAP are midnight-origin. Product default enables them. They are prices on the levels frame, not OTF HTF bars.

### From Slice 3 (locked; do not re-audit 3c 4-rule math)

1. OTF is **not** applied at generation. Full candidate set. For OTF, `T = trigger_timestamp` if present else `timestamp` — for filled 3c that is **reversal completion**, not fill timestamp.
2. Public triggers: `touch` / `reject` / `break` / `reclaim` / `3c`. `confirm_3bar` cannot be generated through UI/API/Study. `simulate_trades` may still implement a residual fill branch.
3. Simple entry: `candidate_next_bar_open` at `bar_index` = canonical trigger-end. 3c filled: `retrace_entry_price` on `entry_bar_index` (`3c_retrace_market`). 3c void: `3c_retrace_void`, must not fill.
4. 3c never backdates to arrival. Filled → fill bar; void → reversal bar. Retrace eligible iff `timestamp > trigger_bar_end` and `<= end + max_wait*Δ`. `max_wait` is a TF duration.
5. `arrival_tolerance_ticks` ignored (effective 0).
6. Two composers: UI pages call the engine directly; they do not call `api.generate_signals`. UI Backtest vs `api.run_backtest` are two composers.
7. Goldens prove default-off pipeline identity, not fill correctness.
8. A disabled `otf_filter` on `signal_settings` is not “OTF ran and passed.”

---

## 1. Architecture of the execution layer

### 1.1 What this layer owns

This layer turns **candidate signals** + **canonical OHLCV** into:

- admitted / skipped / OTF-rejected populations
- filled trades (entry, SL/TP/TIME/SESSION_CLOSE/DATA_END/EOD, costs)
- optional R12 path resolution and R13 BE/trail
- optional Admit `entry_window`

It does **not** generate signals, compute Focus equity, rank grid cells, or construct WFA folds (fold **OTF source** is specified here as a contract for Slice 5).

```text
candidate signals (full population; OTF NOT applied at generation)
        │
        ▼
apply_configured_otf_filter          engine/otf_integration.py
        │  resolve_otf_config (5-step) → apply_otf_filter
        │  T = trigger_timestamp else timestamp
        │  HTF bars with availability_timestamp <= T
        ▼
accepted_signals
        │
        ▼
simulate_trades                      engine/backtest.py
        │  3c void / missing entry bar → silent drop (not a skip row)
        │  simple: next-bar open
        │  3c filled: retrace on entry_bar_index
        │  confirm_3bar residual: bar3_stop_limit_fill at bar_index
        │  Admit (entry-bar local) → cutoff (C9) → exposure
        │  R13 update after completed bar; active next bar
        │  R12 resolve_trade_bar (sim_core → intrabar)
        │  session flatten cap (calendar date of entry_local_ts)
        ▼
trades + skipped_signals + intrabar/exit-mgmt diagnostics
```

### 1.2 Two composers (same functions, different gates)

| Path | OTF | Frame passed as `source_df` / `df` | Admit | Cutoff |
|---|---|---|---|---|
| Classic UI Backtest | `apply_configured_otf_filter` once | prefers `st.session_state["levels"]`, else `"data"` | widgets → `None` if disabled | **gated on** `flat_by_session_close` |
| Classic UI Grid | same helper, **once** before all cells | same levels-prefer frame | inherited `resolve_inherited_entry_window` → `None` if disabled | **gated on** flatten |
| `api.run_backtest` / `run_grid` | same helper, same 5-step resolve | caller `data` | normalize then `None` if disabled | **independent** of flatten |
| `api.run_experiment` | via `run_backtest` / `run_grid` | **`level_payload["levels"]`** | from spec `backtest.entry_window` / `grid.entry_window` | as API |

UI pages do **not** call `api.run_backtest`. Parity is composition, not a shared page function.

### 1.3 Trade / skip row contracts

**Trade (legacy `sl_first` columns)** — `backtest.py` `_TRADE_COLUMNS`. Critical fields:

| Field | Meaning |
|---|---|
| `entry_bar_index` / `entry_timestamp` | simulated fill bar (simple = trigger-end **+ 1**; 3c filled = signal `entry_bar_index`) |
| `entry_model` | `next_bar_open` / `3c_retrace_market` / residual `bar3_stop_limit_fill` |
| `theoretical_*` vs `entry_price`/`exit_price` | unslipped vs adverse-slipped |
| `pnl_points` | **gross** (slipped fills, before commission) |
| `pnl_currency` / `r_multiple` | **net** of round-turn commission |
| `stop_price` | **initial** bracket (not moved BE/trail) |
| `exit_reason` | `SL`/`TP` / `SL_intrabar_path`/`TP_intrabar_path` / `SL_subtimeframe`/`TP_subtimeframe` / `*_fallback` / `BE`/`TRAIL` / `TIME` / `SESSION_CLOSE` / `DATA_END` / `EOD` |
| `status` | always `closed` on emitted trades |

Non-`sl_first` adds `_INTRABAR_TRADE_COLUMNS`. R13-on adds `_EXIT_MANAGEMENT_TRADE_COLUMNS`.

**Skip row** — only when `return_skipped_signals` or `return_result`. Reasons: `outside_entry_window`, `after_entry_cutoff`, `overlapping_position` / `_direction` / `_setup`, `cooldown_active`. **Not** recorded: 3c void, missing future entry bar, flatten `bars_until_close.empty`.

**OTF reject row** — distinct frame (`otf_rejected_signals`). Not a skip.

---

## 2. Must-answer questions

### Q1. UI vs `api.run_backtest`: identical OTF resolve order, `eth_start`, entry-window None-vs-disabled, and levels-vs-data source frame?

**OTF resolve order and `eth_start`: identical function, same 5-step precedence, same instrument `eth_start` — if the caller passes the same blobs. Frame and cutoff composition are not identical.**

`resolve_otf_config` (`otf_integration.py`):

1. `signal_settings["otf_filter"]` if the **key is present**
2. `signal_settings["setup_snapshot"]` effective config
3. `last_signal_setup` effective config
4. `setup_config` effective config
5. canonical **disabled** defaults

Invalid explicit config raises. Disabled is a no-op pass-through (`apply_otf_filter(enabled=False)`).

| Knob | UI `pages/7_Backtest.py` / `8_Grid_Search.py` | `api.run_backtest` / `run_grid` | `run_experiment` |
|---|---|---|---|
| Resolve order | same helper | same helper | same via `run_backtest` |
| `eth_start` | `inst.eth_start` (else `None`) | `inst.eth_start` | `inst.eth_start` |
| OTF `session_timezone` | `exchange_tz` = session `exchange_timezone` **or** `inst.exchange_tz` | **always** `inst.exchange_tz` | same as API |
| OHLCV frame | `levels` if present else `data` | caller `data` | **`levels` frame** |
| Admit `None` vs disabled | normalize; pass `None` if not enabled | same | same |
| `no_new_entries_after` | **only when flatten toggle is on** | **always** from config | same as API |
| R12 intervals | `session_state["base_interval"]` / `subtimeframe_interval` | caller kwargs | declared 15s-primary provenance, else `None` (infer) |

**None vs disabled (Admit):** `normalize_entry_window(None)` and `{enabled: False}` both yield `enabled=False`. `simulate_trades` and both composers then pass `None` into the engine. Probe: identical trade counts. Grid inherit (`resolve_inherited_entry_window`) also yields `entry_window=None` when disabled.

**Levels vs data:** OTF and `simulate_trades` read OHLCV (+ timestamps), not level columns. When `levels` is `data` plus columns (normal classic path), the **bars** match. Divergence cases: UI backtest after Data reload but stale/missing `levels` (falls back to `data`); headless `run_backtest(data, …)` vs `run_experiment` (always levels). Extra level columns are unused by this layer.

**Bad case (composer):** API/YAML can set `no_new_entries_after` with `flat_by_session_close=False`. Engine applies cutoff (probe 10: trade skipped `after_entry_cutoff`). UI widgets disable the cutoff field and force `None` unless flatten is on. Same spec, two admissions.

**Bad case (OTF TZ):** UI OTF uses session `exchange_timezone` if set; API OTF ignores that and uses the instrument preset. Naive decision timestamps localize to whichever TZ that composer passed.

A disabled `otf_filter` on `signal_settings` **wins** over an enabled Setup Builder blob (precedence 1). That is “did not run,” not “ran and passed.” Disabled path still writes `otf_filter_passed=True` + `otf_filter_enabled=False` on every accepted row (probe 5). UI caption when disabled is honest (“all N passed through”).

### Q2. When SL/TP/entry coincide in one sub-bar, is residual ambiguity always SL-first and never credited as TP?

**Yes for observed sub-bars and for `sl_first` parent both-hit. `path_open_proximity` can credit TP when the path hits TP first (not a same-sub-bar residual).**

`resolve_subtimeframe_bar` (`intrabar.py`):

- Pre-entry sub-bars are ignored until `low <= entry <= high`.
- **Entry sub-bar + SL** → `SL` / `subtimeframe_entry_subbar_pessimistic` / `ambiguous=True`. TP on that same sub-bar is not considered.
- **Entry sub-bar + TP only** → TP is **not** credited; walk continues; `ambiguous=True`.
- **Later sub-bar both hit** → `SL` / `subtimeframe_residual_sl_first` / `ambiguous=True`.
- Later single hit → that event (TP allowed after a clean later sub-bar).

Probe 7: one sub-bar with entry 100, SL 98, TP 104 → `exit_kind='SL'`, never TP.

`sl_first` (`resolve_ohlc_bar`): if stop reachable, SL. Both-hit is `legacy_sl_first` + `ambiguous=True`. **`entry_price` is ignored** on this model. 3c/confirm_3bar still pass `entry_activation_price` on the entry parent bar (`backtest.py`); it only affects path / subtimeframe / conservative-fallback TP suppression.

Conservative hole (`sim_core.py`): missing group → parent `sl_first`. If `entry_activation_price` is set and fallback would be TP → **no exit** (`subtimeframe_conservative_entry_parent_unresolved`), not a TP credit. Fallback SL stays SL.

`path_open_proximity`: equal open-to-extreme proximity is SL-first (`intrabar_path_proximity_tie_sl_first`). Same path segment ranks SL before TP (`_first_event_on_path` sort key). A decided O→H→L→C (or O→L→H→C) path **can** credit TP when TP is first after entry. Documented heuristic, not residual-sub-bar.

Covered: `test_subtimeframe_residual_same_subbar_is_pessimistic_and_audited`, `test_subtimeframe_never_credits_target_before_or_unordered_with_entry`.

### Q3. Does `allow_all` plus overlapping 3c/simple signals inflate counts in a way reports under-disclose?

**Yes. Default `allow_all` treats every executable candidate as an independent position. Backtest/Grid widgets have no inflation caption. ASSUMPTIONS §4 states the fact; the pages do not.**

`simulate_trades`: `allow_all` does not sort, does not block, preserves input order (`test_allow_all_preserves_input_order_and_trade_ids`). Restrictive policies sort by `(entry_bar_index, bar_idx, signal_id)` and skip overlaps / cooldown.

Slice 3 already locked: overlapping **3c** setups on the same rounded price are suppressed at generation (`active_until`). **Simple** overlaps (multiple zones / same bar) and **simple + filled 3c** on the same entry bar are not.

Probe 4: simple `bar_index=1` (entry bar 2) + filled 3c `entry_bar_index=2` → `allow_all` emits **2** trades; `single_position` emits **1** and skip `overlapping_position`.

UI (`pages/7_Backtest.py`, `pages/8_Grid_Search.py`): exposure `<selectbox>` has **no help text**. Skip captions distinguish OTF / Admit / exposure only **after** a restrictive policy produces skip rows. `allow_all` skip table is empty, so the inflation is invisible.

3c voids never enter this competition (silent `continue` before Admit). They also never appear as skips — so “accepted trades / candidates” can still look like voids vanished rather than were rejected.

### Q4. Session flatten: any ETH entry flattened at calendar close incorrectly?

**Worse than “flattened at calendar close.” Flatten is calendar-day of `entry_local_ts`, not `trading_session_date` — and `entry_local_ts` in the exit walk is the last first-loop candidate, not this trade.**

Intended contract (ASSUMPTIONS §3, Slice 1): `flat_by_session_close` caps each trade at **that entry’s calendar date** + `session_close_time` (default UI 16:00). Overnight ETH templates are not modeled. Empty `bars_until_close` → `continue` with **no skip row**.

Implemented (`backtest.py`):

```text
first loop:  entry_local_ts = local_timestamps.iloc[entry_bar_index]   # per signal
             candidate stores entry_ts, NOT entry_local_ts
second loop: session_close_ts = entry_local_ts.normalize() + close     # LEAKED last first-loop value
```

Runtime trace (3 simple signals, entries 18:30 / 23:00 Mon and 02:00 Tue; flatten 16:00 ET):

| Signal | True entry | `entry_local_ts` used for flatten | Outcome |
|---|---|---|---|
| 1 | Mon 18:30 | **Tue 02:00** (last candidate) | held through Tue RTH; `DATA_END` at Tue 15:59 |
| 2 | Mon 23:00 | **Tue 02:00** | same |
| 3 | Tue 02:00 | Tue 02:00 | same (this one is “correct” for calendar-RTH flatten) |

Isolated date math for Mon 18:30 + close Mon 16:00 is **empty** (entry is after that calendar close). A **single** Mon-18:30 signal is silently dropped (normalize-trace probe: 0 trades). The multi-signal run **does not drop** — it uses Tuesday’s close.

**Bad case A (probe):** last signal is next-calendar-morning ETH → prior same-CME-session ETH entries (Mon 18:00–23:59) are held overnight and through RTH, then forced at last bar / 16:00. Not CME session close (17:00 / 18:00). Not even this trade’s calendar close.

**Bad case B:** last signal is Mon 18:30 ETH → a later Tue 10:00 RTH entry uses Mon 16:00 as close → empty mask → **silent drop of valid RTH trades**. No skip audit.

**Bad case C (honest calendar-RTH, even if leak were fixed):** Tue 02:00 ETH entry + 16:00 close holds through the cash session. Documented as “RTH-style, ETH overnight not modeled,” but easy to read as “flat at ETH session end.”

`no_new_entries_after` uses first-loop `entry_local_ts` (per-signal). Admit uses `entry_ts`. Only flatten in the second loop is leaked.

Session flatten tests in `test_phase5_backtest.py` are **one-signal RTH 15:58–16:01** fixtures. They cannot see the leak or ETH.

### Q5. Golden families: which engine knobs are uncovered (R13 on, conservative R12, costs > 0, `single_position`)?

**All four, plus flatten, path/subtimeframe R12, and Admit+OTF together.**

| Family | Pipeline | Covered | Explicitly default / absent |
|---|---|---|---|
| Legacy | `pipeline.py` → `simulate_trades` only (no OTF helper) | default-off identity | OTF off (not even called), Admit off, `sl_first`, costs 0, `allow_all`, flatten off, R13 `None` |
| OTF-enabled | `pipeline_otf_enabled.py` → `apply_configured_otf_filter` → `simulate_trades` | enabled 5/15/30-min OTF identity | same execution defaults as legacy |
| Admit-enabled | `pipeline_entry_window_enabled.py` → `simulate_trades(..., entry_window=)` | enabled RTH-segment Admit identity | OTF not applied; same other defaults |

Uncovered by **all three** goldens: `breakeven_after_r` / `trailing_*` (R13 on), `intrabar_model=subtimeframe_conservative` (and `path_open_proximity` / strict `subtimeframe`), `commission_per_side`/`slippage_ticks` > 0, `exposure_policy=single_position` (and `single_direction` / `single_setup`), `flat_by_session_close=True`.

`tests/fixtures/golden/README.md` and Slice 0: goldens prove **legacy-unchanged** / additive enabled identity, not “fills are right.”

### Q6. 3c void never fills; next-bar open vs 3c retrace fill; slippage/commission defaults (zero-cost)?

**Void never fills. Entry models match Slice 3. Defaults are zero-cost; `pnl_points` stays gross when costs are on.**

`simulate_trades` first loop (`backtest.py`):

| Trigger / status | Entry bar | Theoretical price | `entry_model` |
|---|---|---|---|
| `3c` and `status != "filled"` | — | — | **silent continue** (no skip) |
| `3c` filled | `entry_bar_index` | `retrace_entry_price` | `3c_retrace_market` |
| `confirm_3bar` filled | `bar_index` (same bar) | `entry_reference_price` | `bar3_stop_limit_fill` |
| simple | `bar_index + 1` | that bar’s **open** | `next_bar_open` |

Probe 2 / `test_3c_void_is_skipped`: void → 0 trades. Missing `entry_bar_index >= n_bars` also silent-drops.

`confirm_3bar` residual **does fill** (probe 2). Unreachable from `generate_signals` (Slice 3). Hand-built rows or a pickled frame with that trigger still execute. No `test_phase5_*confirm_3bar*` name.

Costs (`_BACKTEST_DEFAULTS`, UI widgets, all golden `BACKTEST_CONFIG`): `commission_per_side=0.0`, `slippage_ticks=0.0`. Non-zero: long entry `+ slip`, exit `− slip` (short mirror); `commission_cost = 2 * per_side`; `pnl_currency`/`r_multiple` net; **`pnl_points` remains gross**. `test_phase5_backtest.py` covers non-zero cost arithmetic.

### Q7. R12 path models: upsample or silent fallback?

**No upsample on any model. Strict `subtimeframe` fail-closed. Conservative fallback is explicit SL-first on holes, fatal on invalid/mismatched OHLC. `sl_first` / `path_open_proximity` do not read lower bars.**

| Model | Lower data | Incomplete / misaligned | Invalid OHLC / OHLC mismatch | Residual same-bar both |
|---|---|---|---|---|
| `sl_first` (default) | unused | n/a | n/a | SL, flagged ambiguous |
| `path_open_proximity` | unused | n/a | n/a | path / proximity-tie SL-first |
| `subtimeframe` | required | **ValueError** | **ValueError** | SL |
| `subtimeframe_conservative` | required | SL-first fallback + diagnostic | **ValueError** | SL (replay) or SL-first fallback |

`_resolve_bar_intervals`: sub must be **strictly finer** and an **exact divisor**. No interpolation, no empty-bar synthesis (ARCHITECTURE R12; Slice 1 data contract). Interval omitted → gap inference (sparse 15s can coarsen; 15s-primary / `run_experiment` should pass declared `parent_interval`/`sub_interval`).

UI warns if a sub model is selected without `subtimeframe_data`; engine still raises on Run.

`sim_core.resolve_trade_bar` is the one-bar boundary; it does not change these rules.

### Q8. R13 BE/trail: commit after completed bars, active next bar?

**Yes. Documented and tested. 3c/confirm_3bar do not arm on the entry parent bar.**

`update_exit_management_after_bar` (`exit_management.py`): commits after the bar that is passed in; docstring: returned stop is active next bar.

`simulate_trades` walk:

- After a bracket hit, **no** R13 update (stop already used this bar).
- Else, if `exit_management_active` and `b < max_bar`: update using this bar’s H/L.
- `can_update`: `next_bar_open` from `b >= entry_bar_index`; 3c/confirm from `b > entry_bar_index`.
- Special case: `allow_same_bar_exit=False` + simple + R13 → update the **entry** bar before the walk so the next bar sees the armed stop (`test_same_bar_exit_disabled_still_arms_breakeven_after_entry_bar_close`).

BE moves stop to **slipped** entry. TRAIL ratchets from best favorable **parent** extreme ± `trailing_distance_ticks`; never loosens. Already-active BE/TRAIL vs TP is resolved by the selected R12 model. `stop_price` column stays the initial stop. Default `None` = legacy fixed bracket.

Covered: `test_exit_management.py` (long/short BE, trail, 3c no-arm on entry bar, path-model interaction, grid sweep).

### Q9. OTF: default off; `availability_timestamp <= T`; WFA `fold_local` vs `causal_prefix` contract for Slice 5?

**Default off. Alignment is `merge_asof(..., direction="backward", allow_exact_matches=True)` on UTC — i.e. latest HTF bar with `availability_timestamp <= T`. 1D/4h are not OTF timeframes. WFA source policy is specified below; fold construction is Slice 5.**

- Default: `_default_otf_filter_config()` / setup blob `enabled=False`. Disabled short-circuit does not call `calculate_otf_state`.
- `T`: `select_signal_decision_timestamp` — `trigger_timestamp` if present and non-null else `timestamp` (Slice 3 locked). Probe: fill 10:00 / trigger 09:45 → `T=09:45`.
- `availability_timestamp = bar_close_timestamp` (`otf.py`). Session reset uses `trading_session_date(..., eth_start)` — **not** clock `session`, **not** 1D resample.
- Supported HTF: `5m`/`15m`/`30m` (+ `*min` aliases). Probe: `1D`/`4h` raise `ValueError`. Slice 1 “do not treat 1D as a CME session” is **closed for OTF** (cannot be selected). `resample_ohlcv` on 5/15/30 is pandas start-label, which aligns for those sizes.
- `alignment_mode` must be `"all"`; `session_reset` must be `"session"`. Unknown / insufficient history → reject (not accept).
- Module docstring on `otf.py` still says “no integration into … backtests, grid-search, walk-forward.” True of **this file’s purity**; product integration is `otf_filter.py` / `otf_integration.py` (Slice 0 flag 3). Do not treat the module docstring as product SoT.

**WFA contract for Slice 5** (`walk_forward.py`, `docs/otf-filter.md`, ARCHITECTURE OTF notes) — do not re-audit fold indices here:

| Policy | Default | OHLCV source | Signals scored | Future after fold end |
|---|---|---|---|---|
| `fold_local` | **yes** (`None` → this) | `df.iloc[fold_start:fold_end_exclusive]` | fold-local only | never |
| `causal_prefix` | no | `df.iloc[:fold_end_exclusive]` (prefix **strictly before** `fold_start`, plus fold) | fold-local only | never |

Unsupported policy raises. Short / unusable fold source → all fold candidates `unknown` → rejected; full-dataset OTF is never used to rescue. `eth_start` / exchange TZ must be the instrument’s. Invalid explicit OTF config fails **before** any fold. Grid applies OTF **once** (not per cell). Slice 5 must verify `causal_prefix` prefix is strictly `< fold start` and that session-fold dates use `trading_session_date`, not this leaky flatten clock.

### Q10. Admit: entry-bar local time; Focus is not re-sim?

**Admit is entry-bar. Focus is out of scope here except the C2/C8 contract: Focus must not be described as `simulate_trades`.**

`entry_window_contains` (`entry_window_policy.py`) classifies the timestamp passed in. `simulate_trades` passes **`entry_ts` = `df.timestamp` at `entry_bar_index`**, with `entry_window_exchange_tz` (instrument exchange TZ; C5). It does **not** reuse session-localized flatten clocks for membership.

C2 probe: signal bar 09:59 (`rth_open_30m`) → next-bar entry 10:00 (`rth_morning`). Window `{rth_open_30m}` → **0 trades**, skip `outside_entry_window` at `entry_bar_index=2`. Signal-bar membership would have admitted.

C1: `RTH_SEGMENTS` live in `entry_window_policy` (engine-safe; analytics re-exports). C3: enabled + empty segments invalid. C4: clock range half-open, no overnight wrap. C6: OTF → Admit → cutoff → exposure; window rejects never compete. C9: window labeled before cutoff; cutoff is strict `>` (entry **at** cutoff admits). C7 (Focus ≡ Admit under `allow_all` + 0 cooldown) is tested in `test_entry_window_admission.py` — Focus math itself is Slice 5.

UI Admit caption: “entry bar” / “Distinct from Time Analysis Focus (post-hoc subset).” Grid inherits a **fixed** window (`resolve_inherited_entry_window`); not a sweep axis.

### Q11. Test gaps vs `otf-filter.md` / SW plan. Goldens ≠ correctness.

Named modules **705 passed**. They police the contracts they encode. Gaps vs the living docs and this slice’s questions:

| Claim / contract | Tests | Gap |
|---|---|---|
| OTF default off; `availability <= T`; trigger_timestamp | `test_otf_filter.py`, `test_otf_contract.py`, OTF golden | no dedicated “disabled `otf_filter_passed=True` is not a pass” honesty test |
| OTF 5/15/30 only; 1D/4h rejected | `test_otf.py` (`4h` in bad-tf parametrize) | — |
| WFA `fold_local` / `causal_prefix` | `test_otf_integration.py` Hardening PR4 | Slice 5 must still lock session-fold dates vs `eth_start` |
| Admit C1–C9 / C7 | `test_entry_window_admission.py`, `sw2b`, `sw3` | — |
| 3c void / next-bar / retrace | `test_phase5_backtest.py` | residual `confirm_3bar` untested |
| Sub-bar residual SL, no pre-entry TP | `test_intrabar.py` | — |
| `sl_first` 3c uses full parent (pre-entry SL) | none found | probe only |
| R13 next-bar | `test_exit_management.py` | not in goldens |
| Costs > 0 | phase5 unit tests | not in goldens |
| `single_position` | phase5 + Admit C7 contrast | not in goldens |
| Session flatten calendar-RTH | phase5 **one-signal RTH** | **no multi-signal leak test; no ETH** |
| UI vs API cutoff-without-flatten | none in named set | probe 10 |
| UI vs API OTF TZ / levels-vs-data | composition inspection | no cross-composer fixture |
| Goldens | three families | identity ≠ fill/flatten/R12/R13/cost/exposure correctness |

`otf-filter.md` still claims it is the SoT and that production must match `test_otf_contract` / `test_otf` / `test_otf_filter`. Those files do **not** cover the flatten leak, `allow_all` inflation honesty, or UI/API cutoff gating.

---

## 3. Prioritized findings

### Critical

1. **`flat_by_session_close` uses a leaked `entry_local_ts` from the last first-loop candidate for every trade.**  
   `simulate_trades` stores `entry_ts` on the candidate but the flatten block reads the loop variable `entry_local_ts` (`backtest.py`). Multi-signal runs assign **one** calendar close to all trades.  
   **Bad case A:** last signal enters Tue 02:00 → Mon 18:30/23:00 ETH entries are held through Tue RTH and exit `DATA_END`/`SESSION_CLOSE` at Tue 15:59/16:00 (runtime trace).  
   **Bad case B:** last signal enters Mon 18:30 → later Tue RTH entries compute Mon 16:00 close → empty `bars_until_close` → **silent drop** (no skip row).  
   One-signal RTH tests stay green. ETH overnight is already “not modeled”; this bug also corrupts **RTH** flatten whenever an after-close candidate is last in the frame.

### High

2. **`allow_all` (default) double-counts overlapping simple/3c fills; Backtest/Grid do not disclose inflation.** Probe 4: two trades on one entry bar vs one under `single_position`. ASSUMPTIONS §4 documents it; widgets have no help text; skip tables are empty under the default so nothing looks wrong.

3. **`sl_first` does not exclude pre-entry movement on 3c/confirm_3bar entry bars.** `resolve_ohlc_bar` ignores `entry_price` for `sl_first`. Probe 3: retrace at 100, parent low 97, SL 2 pts → `SL` even if the low is before the retrace. ASSUMPTIONS §2’s pre-entry exclusion is implemented only on subtimeframe / path-after-entry. Default model is the pessimistic full-bar read.

4. **UI vs API cutoff composition.** UI forces `no_new_entries_after=None` unless flatten is on. API applies cutoff whenever the field is set (probe 10). Headless / Study / Assistant runs are not the Backtest widget.

### Medium

5. **ETH / after-close entries are not a CME-session flatten even if the leak is fixed.** Calendar `normalize()` + 16:00: Mon 18:30 → empty (silent drop); Tue 02:00 → hold through RTH. Uses neither `trading_session_date` nor clock `session`. Matches the written ASSUMPTIONS sentence; contradicts a “session close” mental model.

6. **Silent non-fills have no skip row:** 3c void, missing next/entry bar, flatten empty cap. OTF rejects and Admit/cutoff/exposure skips are audited. Population identity “candidates − rejects − skips = trades” is false.

7. **`pnl_points` is gross; `pnl_currency` / `r_multiple` are net.** Easy to mix in reports (Slice 5). Defaults hide this (zero cost).

8. **`confirm_3bar` residual fill** (`bar3_stop_limit_fill` at `bar_index`). Product generation cannot emit it (Slice 3); execution still will. Untested in the named phase5 file.

9. **OTF UI TZ vs API TZ.** UI OTF `session_timezone` is session `exchange_timezone` or instrument; API is always `inst.exchange_tz`. Naive `T` localization can disagree.

10. **Disabled OTF stamps `otf_filter_passed=True`.** Honest if `otf_filter_enabled` is read; misleading if a consumer filters on `passed` alone. Locked Slice 3: disabled is not “ran and passed.”

11. **Conservative R12 is not a silent upsample**, but interval **inference** on sparse 15s can coarsen the expected grid (Slice 1). `run_experiment` passes declared provenance; UI depends on session `base_interval` / `subtimeframe_interval`. Wrong declared interval → wrong fallback set or strict raise.

### Low

12. **`otf.py` module docstring** still denies backtest/grid/WFA integration (Slice 0 flag 3). Integration is the next two modules.

13. **Signals chart / trade review** (out of fill scope) sit at fill time; OTF `T` is reversal/`trigger_timestamp`. Same class of display-vs-decision clock as Slice 3.

14. **Goldens / 705 tests** do not cover the flatten leak, cutoff-without-flatten, or `allow_all` honesty. Passing CI is not flatten correctness.

---

## 4. Residual risks (not closed here)

- Composer drift: UI cutoff gated on flatten; API not. UI OTF TZ can follow session `exchange_timezone`. `run_experiment` always feeds the **levels** frame; a bare `run_backtest(data)` may not.
- Stale `signal_settings["otf_filter"]` wins over a later Setup Builder enable/disable until signals are regenerated (Slice 0/3 provenance).
- Same-bar MAE/MFE uses **full parent extremes** (can include post-exit extreme). R10 `both_hit_rule` does not inherit R12 (ASSUMPTIONS; Slice 5).
- `path_open_proximity` is a heuristic. Equal-proximity SL-first is tested; “true path” is not.
- Overlapping 3c generation suppression (Slice 3) does not protect `allow_all` simple stacks or concatenated signal frames.
- Flatten empty-cap and 3c void leave no skip — Focus/metrics (Slice 5) can under-count attempted entries.
- WFA `causal_prefix` vs session-fold `eth_start` alignment is **not** proven here.
- 4h/1D levels on the frame are prices only; OTF cannot select them. If a future OTF TF is added, Slice 1 contract 7 applies.
- `pnl_points` vs net currency will look like a metrics bug if Slice 5 assumes both are net.
- Hand-built `confirm_3bar` rows remain an execution back door.

---

## 5. Contracts Slice 5+ must treat as **locked**

1. **Two composers.** UI Backtest/Grid call `apply_configured_otf_filter` + `simulate_trades` / `run_sl_tp_grid` directly. `api.run_backtest` / `run_grid` are the headless composers. `run_experiment` passes the **levels** frame and declared 15s-primary intervals. Do not assume pages call `api.run_backtest`.

2. **OTF is admission, default off.** Resolve order: `signal_settings["otf_filter"]` (key present) → setup snapshot → `last_signal_setup` → `setup_config` → disabled. `T = trigger_timestamp` else `timestamp` (filled 3c: **reversal**, not fill). HTF bar usable iff `availability_timestamp <= T`. Supported TFs: 5/15/30 minutes only. Session reset: `trading_session_date` + `eth_start`, not clock `session`, not 1D/4h. Disabled ≠ passed.

3. **WFA OTF (for Slice 5 to verify, not reinvent):** default `fold_local` = fold OHLCV slice only; `causal_prefix` = `df.iloc[:fold_end]` with prefix **strictly before** fold start; only fold-local signals scored; bars after fold end never used; `None` → `fold_local`; invalid policy raises; short fold → unknown reject. Grid OTF once, not per cell.

4. **Fills.** Simple: next-bar open. 3c filled: retrace on `entry_bar_index`. 3c void: no fill, no skip row. Residual `confirm_3bar`: same-bar `bar3_stop_limit_fill` if a row with that trigger is handed in.

5. **Admit.** Membership is **entry-bar** local time (C2) via `entry_window_policy`. `None` and `{enabled: False}` are admission-identical (engine sees `None`). Window before cutoff (C9). Window rejects never enter exposure (C6). Focus is **not** `simulate_trades` (C8). Grid/WFA inherit a **fixed** window.

6. **Costs default zero.** `pnl_currency` / `r_multiple` net; `pnl_points` gross; `stop_price` = initial risk.

7. **Exposure default `allow_all`.** Independent overlapping fills. Restrictive policies sort and skip. 3c voids never compete.

8. **R12.** No upsample. Strict subtimeframe fail-closed. Conservative = explicit SL-first on holes, fatal on OHLC errors. Same-sub-bar SL+TP (+entry) → SL, never TP. `sl_first` both-hit → SL. `sl_first` does **not** clip to post-entry on 3c.

9. **R13.** Opt-in. Commit after completed parent bar; active next bar. 3c/confirm do not arm on the entry parent. BE/TRAIL vs TP uses the selected R12 model.

10. **Session flatten is calendar-RTH, not CME session, and today is leaky.** Do not treat `SESSION_CLOSE` as `trading_session_date` close or ETH overnight flatten. Empty cap is a silent non-fill. Slice 5 must not assume flatten trades are per-entry-date until the leak is fixed.

11. **Goldens ≠ correctness** of fills, flatten, R12 residual, R13, costs, or exposure.

---

## 6. Contracts still **open** (do not assume)

1. Whether flatten will store per-candidate `entry_local_ts` (today: leaked last candidate).
2. Whether after-close ETH entries will skip, hold to next RTH 16:00, or use `trading_session_date` close.
3. Whether `allow_all` will stay the product default and whether UI/report copy will disclose inflation.
4. Whether `sl_first` will ever honor `entry_activation_price` for 3c.
5. Whether UI will allow `no_new_entries_after` without flatten (today: no; API: yes).
6. Whether `confirm_3bar` will be deleted from `simulate_trades`.
7. Whether silent drops (void / missing bar / empty flatten) will become skip reasons.
8. Whether OTF will ever accept a TF coarser than 30m (today: no; 1D/4h rejected).
9. Whether `pnl_points` will be redefined as net (today: gross).
10. Golden-master: still **identity**, not execution correctness.
11. Slice 5 must still prove Focus honesty copy, WFA session-fold `eth_start` bounds, and `causal_prefix` prefix `< fold start` on **session** folds.

---

## 7. How Slice 5 should start

1. Treat §5 as the trade/skip/OTF/Admit/R12/R13 contract. Do not re-audit 3c 4-rule math, level formulas, or `trading_session_date` arithmetic.
2. Consume: `trades`, `skipped_signals`, `otf_rejected_signals` / `otf_filter_summary`, `entry_window`, `intrabar_diagnostic`, `exit_management_diagnostic`. Do not treat `otf_filter_passed=True` with `otf_filter_enabled=False` as an OTF pass. Do not treat skip-frame row count as “all non-fills.”
3. Focus is post-hoc on **`entry_timestamp`** (C2/C8). It does not re-run `simulate_trades`. Under `allow_all` + 0 cooldown, Focus ≡ Admit identity is already tested (C7); under other exposure policies, Focus **over-states** constrained-path trade counts.
4. WFA: use the OTF history contract in §5.3. Verify session folds key by `trading_session_date` / `eth_start`, not calendar flatten and not clock `session`. Prove `causal_prefix` prefix `< fold start`.
5. Metrics: `pnl_currency`/`r_multiple` are net; `pnl_points` is gross; MAE/MFE are full-parent; R10 `both_hit_rule` ≠ selected R12 model.
6. Grid ranking / WFA train selection must not peek at test (Slice 0 Q). Re-sim loop already contracted here (`run_sl_tp_grid` → `simulate_trades`).
7. Goldens still do not prove analytics correctness.

---

## 8. How Slice 4 started (traceability)

Read Slice 0 map (two composers, goldens ≠ correctness, execution file list), Slice 1 locked clocks (session ≠ session-date; flatten is calendar-RTH; 1D/4h ≠ CME; R12 data contract), Slice 2 levels/PIT usage of `trading_session_date`, and Slice 3 §5 signal-row / OTF-not-at-generation / 3c fill-void contracts.

Scoped to `thesistester/engine/{backtest,sim_core,intrabar,exit_management,otf,otf_filter,otf_integration}.py`; `entry_window_policy.py`; `execution_defaults.py`; `api.run_backtest` / `run_grid` / `run_experiment` levels+subtimeframe handoff; `pages/7_Backtest.py` (execution + skip/OTF/Admit widgets); `pages/8_Grid_Search.py` (execution composition); named goldens/tests; `docs/otf-filter.md`; SESSION_ENTRY_WINDOW C1–C9; ARCHITECTURE R12/R13/SW2–SW6; ASSUMPTIONS §§1–4a.

Did not enter Focus-only analytics beyond Admit consumption, WFA fold construction (except the OTF-on-fold contract), metrics formulas, Study, Assistant, or combo-attribution.
