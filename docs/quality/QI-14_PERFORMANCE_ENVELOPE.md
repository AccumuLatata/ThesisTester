# QI-14 — Performance, scalability, and resource envelope

**Slice:** QI-14 (research-only, cross-cutting measurement)
**Status:** Measured
**Audited commit:** `539dd2e` (`539dd2e9dabc9ba918f03b26f66537f3d9fca3ce`) — `origin/main` after [#488](https://github.com/AccumuLatata/ThesisTester/pull/488)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS (`Linux cursor 6.12.94+ x86_64`), 4 CPUs, Python 3.12.3
**Key packages:** pandas 3.0.5 · numpy 2.4.4 · streamlit 1.63.0 · pytest 9.1.1
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi14-store-*`. `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data. Inputs: `tests/fixtures/cai_baseline.py`, `tests/benchmarks/fixtures.py`, synthetic `/tmp` 1m/15s generators. `sample_data/ES_sample_1m.csv` is 12 bars (not used as a timing fixture).
**Finding count:** 10 (C/H/M/L = 0/0/6/4)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day
**py-spy:** not installed. Flame-equivalent: `cProfile` + `pstats` under `/tmp/qi14/cprofile/*.pstats`.

Wall times are **informational**. They are not a correctness claim about P&L, metrics, or Study ranking (`AUDIT_FINAL` §5.1 item 10). R22 remains: any later acceleration must equal serial goldens. This report does **not** call any backtest, metric, or Study result correct or reliable. Vocabulary is plan §3.3.

**Review corrections (schema / honesty only; no product files):** Plan §3.3 `locked_by` is `AUDIT_FINAL §5.x` / `AH §2.n` / `none`. First-pass `R22` / `AUDIT S3` / `DA0` / `AUDIT S1` tokens are withdrawn (proposal or other-series locks; noted in repro). QI-14-04 is the cost of locked omit-means-on (`AH §2 item 9`) — `Design limitation` / `confidence=n/a` / ≤ Medium; expected no longer asks fixtures to skip unnamed `prev30m`. W12 (QI-14-03) stays `Verified` measured status. Named-set AST `iterrows` is **10** (signals 6 + backtest 1 + intrabar 1 + confluence 2), not 9. `.copy()` **68** is reproduced on the named set in §2. Levels 780×50 dtypes are 47 float64 + tz datetime + 1 int64 + 1 string (0 object). Stage-share percents are independently timed medians / e2e median and need not sum to 100%. Study `--workers` walls used a shared store (`levels_hit` on later runs) — not a parallel-efficiency claim. AppTest was a 780-bar 1m session, not a loaded 15s session. Review-pass reproduced the documented realistic `ValueError`, `1568×52` / 32 object / 1.592 MB, and `disable_unneeded_tick_families` clearing `poc_windows`. §A.5 ISO tokens unchanged.

## Commands run (verbatim)

```bash
git fetch origin main
git checkout -b cursor/qi-14-performance-envelope-3958

python3 --version
python3 -c "import pandas,numpy,streamlit,pytest; print(pandas.__version__, numpy.__version__, streamlit.__version__, pytest.__version__)"
git rev-parse HEAD
nproc

# before (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi14-store-before pytest -q --tb=no
# 3966 passed, 5 skipped in 134.21s

# official harnesses + probes (scripts stay under /tmp; not committed)
THESISTESTER_STORE_DIR=/tmp/qi14-store-probes \
  python3 /tmp/qi14/probe_qi14.py
THESISTESTER_STORE_DIR=/tmp/qi14-store-probes \
  python3 /tmp/qi14/run_rest.py          # scaling curve (naive 1m CSV; tz-aware 15s derive)
THESISTESTER_STORE_DIR=/tmp/qi14-store-study \
  python3 /tmp/qi14/probe_study_pages.py # Study workers + AppTest pages
# Observatory re-probe with results/studies/ layout → /tmp/qi14/observatory.json

THESISTESTER_STORE_DIR=/tmp/qi14-store-bench pytest -q --tb=line tests/benchmarks
# 4 passed in 4.25s (small/smoke only)

# after (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi14-store-after pytest -q --tb=no
# 3966 passed, 5 skipped in 131.30s

# review-pass (docs-only honesty/schema; product tree unchanged)
python3 /tmp/qi14-review/verify_schema_ast.py
# findings.csv: 10 QI-14 rows; §3.3 columns; §A.5 ISO; Design limitation n/a only on QI-14-04
# AST copy=68 on named set; iterrows=10 on the four-file list (not 9)
THESISTESTER_STORE_DIR=/tmp/qi14-store-review python3 /tmp/qi14-review/verify_runtime.py
# realistic compute_levels → ValueError rolling POC requires ticks
# poc_windows=[] → levels 780×50 / 0.315 MB; signals 1568×52 / 32 object / 1.592 MB
# normalize(cai_*) prev30m_vwap_enabled=True; disable_unneeded_tick_families poc=[]

# review-pass pytest (docs-only; identical result class)
THESISTESTER_STORE_DIR=/tmp/qi14-store-review-after pytest -q --tb=no
# 3966 passed, 5 skipped in 148.73s
```

Probe transcripts stay under `/tmp/qi14/`. Nothing from `/tmp` is committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (measurement only — QI-14 owns no exclusive source files)**

- Official R22 runner `python3 -m tests.benchmarks.run` (via `run_benchmarks(repeats=5)`).
- Official CAI cold `measure_cai_cold_path` small + realistic.
- Official CAI warm `measure_cai_warm_path` small + realistic (hash equality).
- Stage timings / peak RSS / dtype hygiene on CAI `realistic` with `poc_windows=[]` (current 1m envelope after the tick gate).
- Family breakdown: `compute_session_levels` / `compute_indicator_levels` / `compute_session_vwap_levels` / tick-gated `compute_profile_levels`.
- Synthetic 1-print-per-bar Quantower tick file → `compute_levels(..., poc_windows=["30min"])`.
- Scaling: 2 / 20 / 63 RTH sessions (780 / 7,800 / 24,570 1m bars). 15s derive on 1 and 5 sessions.
- Batteries: `run_sl_tp_grid` 3×3, `run_walk_forward_sl_tp`, `monte_carlo_summary(n=200)`, `validation_summary` on the 780-bar fixture.
- `cProfile` of `compute_levels`, `generate_signals`, `simulate_trades`, `BarData.from_frame`.
- AST `.copy()` / `iterrows` inventory on the hot-path module list.
- Study `run_study(..., workers=1|2|4)` on a 4-cell synthetic spec; `canonical` `bundle_hash` compared.
- Observatory `load_observatory_frame` vs 1/4/16/64 copied studies (4 cells each).
- Streamlit `AppTest` first-render + rerun on `app.py`, Data, Levels, Signals, Backtest, Validation, Observatory with a loaded 780-bar session.
- W12 / R22 status re-verification only. `AUDIT_FINAL` §5 and AH §2 not re-audited.

**Skipped**

- Implementing any optimization (hard rule).
- Regenerating goldens.
- Vendor-width 15s Quantower frames (the documented ~380 MB `MessageSizeError` case). Synthetic 6-column 15s is not that payload.
- AppTest on a **loaded 15s session** (plan §5 QI-14). Timed derive in memory only; page rerun used the 780-bar 1m fixture.
- `py-spy` live attach (binary absent).
- Product-default full Levels page (pivots + single prints + APOC + rolling POC + ticks) as one timing — tick families refuse without files; measured piecewise.

---

## 2. Code-quality readout (hot-path metrics, then reading notes)

QI-0 F-grade set is unchanged. QI-14 only *times* those functions.

| Symbol | CC (QI-0) | This-run role |
|---|---:|---|
| `engine.backtest.simulate_trades` | F 133 | Serial orchestrator. P7 calls `resolve_trade_bar` once per held bar. |
| `engine.signals.generate_signals` | F 120 | Dominant **current** cold cost on CAI realistic (no typical-price rolling POC). 6× `iterrows`. |
| `analytics.walk_forward.run_walk_forward_sl_tp` | F 50 | Multiplies `simulate_trades` per fold × grid cell. 14× `.copy()`. |
| `analytics.grid.run_sl_tp_grid` | — | 9 independent `simulate_trades` on a 3×3. Measured 9.87× one sim. |
| `levels.prev30m_vwap.compute_prev30m_vwap_levels` | — | Product default **on** via `DEFAULT_LEVELS_SETTINGS`. Top user-code `tottime` in the levels profile. |
| `engine.sim_core.BarData.from_frame` / `resolve_trade_bar` | A | R22 boundary. Tuple-of-float snapshot + per-bar dataclass. |

`.copy()` / `iterrows` AST counts on the named hot-path set
(`thesistester/levels/*.py` 27 + `signals.py` 3 + `backtest.py` 0 + `sim_core.py` 0 +
`intrabar.py` 2 + `grid.py` 1 + `walk_forward.py` 14 + `confluence_attribution.py` 20 +
`data/derive.py` 1): **68** `.copy()` Call sites (review-pass reproduced).
`iterrows` on the four files listed in the first pass: **10** (`signals.py` 6,
`backtest.py` 1, `intrabar.py` 1, `confluence_attribution.py` 2) — not 9.
Same set plus `levels/tpo.py` is 11. `sim_core.py` has zero copies and zero `iterrows`.

Memory hygiene on CAI realistic (780 bars):

| Frame | rows × cols | deep memory | object cols |
|---|---:|---:|---:|
| `data` | 780 × 7 | 0.046 MB | 0 |
| `levels` | 780 × 50 | 0.315 MB | 0 object (47 float64 + tz datetime + 1 int64 + 1 string) |
| `signals` | 1,568 × 52 | **1.592 MB** | **32 object** (3c/fade nullable schema on every `touch` row) |

Process peak RSS: ~223 MB after the 780-bar cold path; **749 MB** after the 3-month curve (24,570 bars, 49,766 signal rows / 50.5 MB).

---

## 3. Application-quality readout (envelope checklist)

§3.2 items 1–7 / 9–10 are owned by QI-1…QI-10. This slice owns **item 8** and the QI-14 probes.

| Check | Result (identity / timing only) |
|---|---|
| 8 Perf envelope — official R22 | Serial medians match `SIMULATE_PERF.md` within **+0.0…+4.3%** on this VM. |
| 8 Perf envelope — CAI small | Stages within +12% except `build_research_bundle` **+226%** (QI-14-07). |
| 8 Perf envelope — CAI realistic documented command | **Raises** `rolling POC requires ticks` (QI-14-01). |
| 8 Perf envelope — current realistic (POC stripped) | e2e median **756 ms**; `generate_signals` 45% / `compute_levels` 26% (QI-14-02). |
| Warm path | small speedup **2.328**, hash equal, `levels_hit`. realistic speedup **1.335**, hash equal, `levels_hit`. CAI-10 “no second signal cache yet” still the harness recommendation (QI-14-08). |
| Study `--workers` 1/2/4 | Four cells. `bundle_hash` **byte-identical** across 1/2/4. Walls 2.087 / 1.353 / 0.966 s used a **shared store** (later runs `levels_hit`) and are **not** a workers-scaling efficiency claim. |
| Observatory vs corpus | Linear ~3.2 ms/cell at the 256-cell end (819/256). 17 ms / 4 cells is 4.25 ms/cell — small-N, not the same slope. Warm-with-`prior` ~0.5×. |
| Page rerun (AppTest, 780-bar **1m** session) | First render 0.11–0.32 s; rerun 0.004–0.222 s; 0 exceptions. Pickle of `{data,levels,signals,trades,setup}` = **0.818 MB** vs `.streamlit` `maxMessageSize=400`. **Not** a loaded 15s session (plan check). Vendor-width 15s skipped; synthetic 15s was derive-only. |
| 15s derive | 832 ms / 1,560 bars; 4,157 ms / 7,800 bars; 3-month CSV estimate **9.9 MB** (6 columns). Not the vendor 380 MB frame. |
| Batteries | 3×3 grid **3,346 ms** (9.87× one `simulate_trades`); WFA **2,626 ms**; MC-200 **13 ms**; Phase-8 `validation_summary` **59 ms**. |

---

## 4. Prior-audit carry-over status

| Item | Assigned | Status on `539dd2e` | Evidence |
|---|---|---|---|
| **W12** `simulate_trades` `iterrows` + Python exit walk; grid = full re-sim | QI-14 | **Still the serial envelope.** Not closed. R22 isolated `sim_core` and did **not** accelerate. | `signals.iterrows` still the candidate loop (`backtest.py`). cProfile: 46,110 `resolve_trade_bar` / `resolve_ohlc_bar` / `BarData.at` on 1,568 signals × ~30 hold (default `allow_all` profile). 3×3 grid 9.87× one sim. 3-month: signals 10.4 s + backtest 6.3 s. |
| **R22** any acceleration must equal serial goldens | QI-14 | **Holds as policy.** Informational benches do not gate CI (`median_ms >= 0`, QI-11-05). | This VM’s R22 table matches `SIMULATE_PERF.md` within 4%. `sim_core` still has no admission/P&L (QI-04-03 positive). No optimization PR in this slice. |

H4 (two levels-settings planes) is **QI-2-assigned**, not a QI-14 carry-over. QI-14 only records **cost**: `normalize_levels_config` merges `DEFAULT_LEVELS_SETTINGS`, so omitted `prev30m_vwap_enabled` is **True** on the CAI fixture (QI-14-04). Omit-means-on is locked (`AH §2 item 9`); this slice does not propose flipping it.

---

## 5. Findings

Full records: `docs/quality/findings.csv` (`QI-14-01`…`QI-14-10`).

| ID | Axis | Class | Sev | Conf | Title |
|---|---|---|---|---|---|
| QI-14-01 | app | Documentation drift | Medium | Verified | Documented CAI `realistic` cold command raises `rolling POC requires ticks` |
| QI-14-02 | both | Documentation drift | Medium | Verified | `CAI_BASELINE.md` “levels ~71%” is stale; current realistic is signal-dominated |
| QI-14-03 | both | Design limitation | Medium | Verified | W12 still the serial scale limit; R22 did not accelerate |
| QI-14-04 | both | Design limitation | Medium | n/a | Product-default `prev30m_vwap_enabled=True` is silently merged onto sparse/CAI configs |
| QI-14-05 | code | Maintainability risk | Medium | Verified | `generate_signals` `iterrows` + 32 object columns dominate current cold path |
| QI-14-06 | code | Maintainability risk | Medium | Verified | 15s→1m derive is a Python group loop (~0.53 ms/bar) |
| QI-14-07 | app | Documentation drift | Low | Verified | CAI small `build_research_bundle` is 3.3× the recorded baseline |
| QI-14-08 | code | Test-quality gap | Low | Verified | Warm-path harness has no stage split; CAI-10 signal-share decision is still unmeasured |
| QI-14-09 | code | Maintainability risk | Low | Strong | `BarData.from_frame` boxes every OHLC into Python floats/tuples |
| QI-14-10 | code | Maintainability risk | Low | Verified | WFA 14× and confluence-attribution 20× `.copy()` on already-paid engine outputs |

No Critical. No High. Design-limitation rows stay ≤ Medium (plan §2 rule 5). QI-14-04 is `confidence=n/a` (locked omit-means-on). None of these invert `AUDIT_FINAL` §5 or AH §2.

---

## 6. Positive verification

Do not re-audit these unless the owning file or the fixture recipe changes.

1. **R22 serial ruler still reproduces.** `500×10×50` 4.646 vs 4.645 ms; `500×100×50` 27.997 vs 27.019; `2000×100×200` 55.203 vs 52.943; 3×3 grid 206.871 vs 204.473. Hardware noise, not a rewrite.
2. **`sim_core` contains no admission or P&L** (re-read; QI-4 already closed this). The 46k `resolve_trade_bar` calls are bracket resolution only.
3. **Study workers 1/2/4 emit identical per-cell `bundle_hash`.** The only index delta is `cache_outcome` (`cold` on w1 cell 0 vs `levels_hit` when the shared `/tmp` store is warm). That is cache provenance, not a second experiment. Walls 2.087 / 1.353 / 0.966 s are **not** a parallel-efficiency claim. **Not** a claim that cell expectancy is a validated edge.
4. **CAI warm ↔ cold canonical bundle hashes are equal** on small and on the current realistic path (`f8a5505a…` / `311d6204…`).
5. **AppTest page reruns on a loaded 780-bar 1m session do not raise.** First render ≤ 0.315 s (Levels). Session pickle 0.818 MB ≪ 400 MB websocket cap. This is not a 15s-session measurement.
6. **Observatory load is linear and cheap at research scale** (819 ms cold / 256 cells) once studies sit under `results/studies/`.
7. **Grid multiplicative cost is the documented 9×**, not hidden extra work (9.87× on this fixture).
8. **MC-200 and Phase-8 `validation_summary` are cheap** on 26 trades (13 ms / 59 ms). They are not the W12 multiplier; WFA/grid are.
9. **Official `tests/benchmarks` pytest is green** (4 passed). Those tests still only assert structure + `median_ms >= 0`.
10. **Isolation held:** throwaway `/tmp` store; no API keys; no desk PII.
11. **Before/after `pytest -q` identical:** 3,966 passed, 5 skipped (134.21 s before / 131.30 s after). Review-pass after honesty/schema edits: 3,966 passed, 5 skipped in 148.73 s. Porcelain: only `docs/quality/QI-14_PERFORMANCE_ENVELOPE.md` and `docs/quality/findings.csv`.

---

## 7. Handoffs to other slices

| To | Observation (not a finding against their files) |
|---|---|
| QI-1 | 15s derive ~0.53 ms/bar (QI-14-06). CAI realistic ingest remains ~12.5 ms / 780 bars (QI-01 handoff 0.027 s was a different timer). |
| QI-2 | H4 cost: `DEFAULT_LEVELS_SETTINGS.prev30m_vwap_enabled=True` is why CAI/sparse API configs pay `compute_prev30m_vwap_levels` (`AH §2 item 9` — do not invert). Rolling POC typical-price `_rolling_poc` is dead; tick gate is the live path. |
| QI-3 | `generate_signals` is the current realistic hot function (QI-14-05). 6× `iterrows`. |
| QI-4 | W12 structure unchanged (QI-14-03/09). Do not treat this slice’s battery 339 ms `simulate_trades` as the R22 ruler — that ruler is `tests/benchmarks/run.py`. |
| QI-5 | WFA 2.6 s and 14× `.copy()` (QI-14-10). Grid 9.87×. |
| QI-6 | `run_experiment` calls `disable_unneeded_tick_families` (CAI realistic e2e works). Direct `compute_levels(config=spec["levels"])` does not (CAI cold harness dies). Bundle 3.3× (QI-14-07). |
| QI-7 | Worker index `cache_outcome` is not part of `bundle_hash`. Observatory discovers only `results/studies/` and `out/` children. |
| QI-10 | Loaded **1m** AppTest times above. Empty-page times match QI-10’s 0.12–0.17 s band. 15s page rerun was not measured. |
| QI-11 | Benchmark tests remain informational. Warm harness cannot answer CAI-10’s “warm `generate_signals` share” question (QI-14-08). |
| QI-13 | Living docs to amend are listed in §8. Do not amend in QI. |

---

## 8. Docs that would need amending in QR

List only. **Not amended.**

| Doc | Why QR would touch it |
|---|---|
| `docs/CAI_BASELINE.md` | Realistic command is broken; stage-share table is stale; note `prev30m` product-default merge; bundle 3.3× on small. |
| `docs/SIMULATE_PERF.md` | Re-record after any R22/P7 extract (numbers here are within 4% — optional footnote). State that W12 is still serial. |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | W12 / resource envelope (3-month 20 s e2e / 749 MB RSS on this VM; 15s derive slope). |
| `docs/USER_GUIDE.md` | 15s transport cap is still the vendor-frame story (QI-10). Optional: Studies `--workers` does not change cell `bundle_hash`. |
| `docs/AGENT_GUIDE.md` | CAI harness: call `compute_levels` only after `disable_unneeded_tick_families` (or drop `poc_windows` on the fixture). R22 “measure then accelerate” still open. |
| `docs/ARCHITECTURE.md` | Cache vs identity: warm `levels_hit` changes `cache_outcome` only. |
| `docs/ENGINEERING_PROPOSAL.md` R22 / W12 row | Confirm acceleration is still future work; update the “levels dominate” sentence if it cites CAI-0. |

---

## 9. Exit tables (stage timing / memory / hot spots / drift)

### 9.1 Official R22 vs `SIMULATE_PERF.md`

| Scenario | Bars | Signals | Hold | Doc median ms | This median ms | Drift |
|---|---:|---:|---:|---:|---:|---:|
| `simulate_trades` | 500 | 10 | 50 | 4.645 | 4.646 | +0.0% |
| `simulate_trades` | 500 | 100 | 50 | 27.019 | 27.997 | +3.6% |
| `simulate_trades` | 2,000 | 100 | 200 | 52.943 | 55.203 | +4.3% |
| `run_sl_tp_grid_3x3` | 500 | 50 | 50 | 204.473 | 206.871 | +1.2% |

W12 micro: µs per `(signals × hold)` ≈ 9.4 (small) → 2.9 (large). Fixed per-signal overhead + O(signals × bars_held).

### 9.2 CAI small vs `CAI_BASELINE.md`

| Stage | Doc median ms | This median ms | Drift |
|---|---:|---:|---:|
| `load_dataset` | 6.984 | 7.078 | +1.3% |
| `compute_levels` | 95.309 | 106.355 | +11.6% |
| `generate_signals` | 24.440 | 24.875 | +1.8% |
| `run_backtest` | 17.638 | 18.365 | +4.1% |
| `build_research_bundle` | 17.006 | 55.530 | **+226%** |
| `run_experiment_end_to_end` | 149.799 | 162.957 | +8.8% |

Warm small: cold 164.8 ms / warm 70.8 ms / speedup 2.328 / hash equal / `levels_hit`.

### 9.3 CAI realistic — documented vs current

| Path | Result |
|---|---|
| Documented `python3 -m tests.benchmarks.cai_cold_path --fixture both` | **`ValueError: rolling POC requires ticks: tick_paths is missing or empty`** at the harness’s direct `compute_levels` (before stage timing). |
| Documented table (CAI-0) | levels 1,293 ms (**70.9%** of 1,825 ms e2e) with `poc_windows=["30min"]` (then typical-price `_rolling_poc`). |
| `run_experiment` / warm harness | Succeeds: `disable_unneeded_tick_families` clears unused POC. Warm realistic: cold 732 ms / warm 548 ms / speedup 1.335 / hash equal. |
| This slice, explicit `poc_windows=[]` (prev30m still default-on) | table below |

| Stage (780 bars, no rolling POC) | Median ms | Share of 756 ms e2e |
|---|---:|---:|
| `load_dataset` | 12.5 | 1.7% |
| `compute_levels` | 194.5 | 25.7% |
| `generate_signals` | **339.2** | **44.9%** |
| `run_backtest` | 164.4 | 21.7% |
| `build_research_bundle` | 74.1 | 9.8% |
| `run_experiment_end_to_end` | 756.0 | 100% |

Shares are independently timed stage medians divided by the separate e2e median. They need not sum to 100% (stage-median sum 784.7 ms). Small-fixture isolated stages vs e2e have the same structure (CAI harness times each public function separately from `run_experiment`).

Family (780 bars): session 43 ms · indicators 31 ms · session VWAP 9 ms · profile 30min **refuse** · tick-POC 1 print/bar **310 ms** total `compute_levels`.

cProfile `compute_levels` (one instrumented run, 0.440 s — not the 194.5 ms median): `compute_prev30m_vwap_levels` cumtime **0.163 s**. Profiler overhead; use the median table for envelope, the profile for rank-order.

### 9.4 Scaling (1m, CAI-realistic levels with `poc_windows=[]`)

| Label | Sessions | Bars | Signals | Trades | levels ms | signals ms | backtest ms | e2e ms | RSS MB | signals MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2-sess | 2 | 780 | 1,568 | 26 | 194 | 326 | 164 | 717 | 162 | 1.6 |
| ~1 month | 20 | 7,800 | 15,792 | 260 | 1,049 | 3,330 | 1,811 | 6,308 | 366 | 16.0 |
| ~3 month | 63 | 24,570 | 49,766 | 819 | 3,114 | **10,402** | 6,303 | **20,373** | **749** | **50.5** |

Signals scale ~linear in bars (326 → 10,402 is 31.9× vs 31.5× bars). Backtest 38× (more admitted trades under `single_position` plus per-candidate work). Levels ~16× (sub-linear).

15s derive (tz-aware in memory): 1 sess 832 ms / 1,560 bars; 5 sess 4,157 ms / 7,800 bars; 3-month CSV estimate 9.9 MB.

### 9.5 Ranked hot spots (feasibility only — do not implement)

| Rank | Hot spot | Evidence | Feasibility without output change (R22) |
|---|---|---|---|
| 1 | `generate_signals` row loops | 339 ms / 45% of current realistic e2e; 10.4 s at 3 months; `fast_xs` / `iterrows` in cProfile | High value, **golden-gated**. Column arrays / `itertuples` behind the existing trigger helpers. QI-3 + QR-B mutation first. |
| 2 | `simulate_trades` P7 × batteries | 46k `resolve_trade_bar`; grid 9.87×; WFA 2.6 s; 6.3 s at 3 months | R22 already isolated the boundary. Numba/vector/parallel **only** with serial golden equality. Do not widen `sim_core` into admission/P&L. |
| 3 | `compute_prev30m_vwap_levels` default-on | 163 ms of one levels profile; omitted key → True | Cheap win: honor CAI/sparse explicit-off, or skip when the selected-level set does not name `prev30mVWAP`. PIT tests (QI-2) before any math change. |
| 4 | 15s `derive_complete_parent_ohlcv` | ~0.53 ms/bar Python groups | Vectorized `groupby` under locked `observed_aligned_15s_to_1m_v2`. QI-1. |
| 5 | Signal object schema | 32 object cols; 50 MB at 3 months | Nullable/category **if** hashes stay identical. Identity-sensitive. |
| 6 | `BarData.from_frame` boxing | 0.72 ms / 780 bars × 50 in the profile; 4 Python genexprs | Swap tuples for `float64` arrays inside the R22 module; keep `resolve_ohlc_bar` math. |
| 7 | `build_research_bundle` | 55 ms small vs 17 ms documented; 74 ms realistic | Inventory extra identity/prev30m columns (QI-6). Not an engine loop. |
| 8 | WFA / confluence `.copy()` | 14 / 20 sites | Views where folds are already disjoint. After QR-B. |
| 9 | Typical-price `_rolling_poc` | Dead. Tick path 310 ms on 1 print/bar | Do not revive. Any tick-POC accel needs tick oracles (QI-2). |
| 10 | Page rerun / Observatory / MC | Sub-second at measured sizes | Not the scale problem. |

---

## 10. Probe scripts (pasted; not committed)

Official runners used as-is: `tests/benchmarks/run.py`, `tests/benchmarks/cai_cold_path.py`, `tests/benchmarks/cai_warm_path.py`.

Throwaway drivers (full text under `/tmp/qi14/probe_qi14.py`, `/tmp/qi14/probe_study_pages.py`):

```python
# Isolation wrapper used for every probe
import os
os.environ["THESISTESTER_STORE_DIR"] = "/tmp/qi14-store-probes"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("XAI_API_KEY", None)

from tests.benchmarks.run import run_benchmarks
from tests.benchmarks.cai_cold_path import measure_cai_cold_path
from tests.benchmarks.cai_warm_path import measure_cai_warm_path
print(run_benchmarks(repeats=5))
print(measure_cai_cold_path(kind="small", repeats=5))
# realistic → ValueError rolling POC requires ticks
```

Study workers fingerprint (stable columns only):

```python
# After run_study(..., workers=w), compare:
#   results_index.csv sorted by run_name
#   bundle_hash equal across w in {1,2,4}   → True on 539dd2e
#   cache_outcome may differ if the store is shared
```

cProfile dump:

```python
import cProfile, pstats
pr = cProfile.Profile(); pr.enable(); compute_levels(...); pr.disable()
pr.dump_stats("/tmp/qi14/cprofile/compute_levels.pstats")
pstats.Stats(pr).sort_stats("tottime").print_stats(25)
```

Review-pass essential snippets (schema / AST / runtime; not a new timing campaign):

```python
# Named-set AST (reproduces copy=68, four-file iterrows=10)
HOT_COPY = [
    "thesistester/levels/*.py",  # 27
    "thesistester/engine/signals.py",  # 3
    "thesistester/engine/backtest.py",  # 0
    "thesistester/engine/sim_core.py",  # 0
    "thesistester/engine/intrabar.py",  # 2
    "thesistester/analytics/grid.py",  # 1
    "thesistester/analytics/walk_forward.py",  # 14
    "thesistester/analytics/confluence_attribution.py",  # 20
    "thesistester/data/derive.py",  # 1
]
# iterrows four-file: signals 6, backtest 1, intrabar 1, confluence 2

# Runtime: import api first (avoid research_identity circular import)
from thesistester.api import compute_levels, load_dataset, generate_signals, build_setup
from thesistester.research_identity import normalize_levels_config
from thesistester.levels.tick_requirements import disable_unneeded_tick_families
# cai realistic compute_levels(spec["levels"]) → ValueError rolling POC requires ticks
# poc_windows=[] → levels 780×50 / 0.315 MB; signals 1568×52 / 32 object / 1.592 MB
# normalize(cai_*)["prev30m_vwap_enabled"] is True
# disable_unneeded_tick_families(realistic, setup)["poc_windows"] == []
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged. No optimizations implemented. No goldens regenerated.
