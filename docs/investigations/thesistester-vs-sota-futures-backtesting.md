# ThesisTester — Current State vs State-of-the-Art Futures Backtesting

**Investigation date:** 2026-07-27  
**Scope:** Map ThesisTester against the SOTA ES/NQ intraday backtesting capability checklist  
**Code changes:** None (investigation only)  
**Companion docs:**
- SOTA checklist (conversation Task 1)
- `docs/investigations/otf-filter-investigation.md`

---

## Executive summary

ThesisTester is a **focused research workbench** for confluence-based ES/NQ intraday setups — not a general-purpose futures day-trading platform (NinjaTrader / Sierra / FX Replay class).

**Positioning:** Strong at **level → confluence → signal → fixed-SL/TP backtest → diagnostic validation**. Weak or absent on **tick/replay/order-flow**, **continuous-contract construction**, **advanced execution realism**, and **modern anti-overfitting tooling** (CPCV, Monte Carlo paths, prop rules).

### Scorecard (vs SOTA checklist)

| Domain | Grade | One-line assessment |
|--------|-------|---------------------|
| 1. Futures contract model | **B+** | ES/NQ specs correct; no micros; no continuous builder |
| 2. Session / timezone | **A−** | Strong RTH/ETH + NY TZ; ETH overnight flatten limited |
| 3. Data quality / resolution | **C+** | Solid CSV 1m+ pipeline; no tick/seconds/API |
| 4. Causal / look-ahead safety | **A** | Explicit PIT guarantees; OTF completed-bars; good tests |
| 5. Execution realism | **C** | Commission + tick slippage; market/retrace only; SL-first OHLC |
| 6. Strategy / research workflow | **A−** | Excellent confluence + 3c + OTF thesis loop |
| 7. Risk / sizing / day constraints | **B** | Exposure + session flat; no risk-% sizing or prop DD |
| 8. Optimization / anti-overfit | **B−** | SL×TP grid + WFO + bootstrap; no CPCV/Monte Carlo paths |
| 9. Analytics & diagnostics | **A−** | Rich R-metrics, time buckets, long/short split |
| 10. Replay / discretionary loop | **D** | Charts exist; no market replay / chart-trading sim |
| 11. Levels / auction context | **A** | Broad level catalog incl. profile/TPO/VWAP/APOC |
| 12. Experiment management | **B+** | Local store, hashes, bundles, exports |
| 13. Product integration | **B** | Clean Streamlit workflow; no live/broker bridge |

**Overall:** ThesisTester is **state-of-the-art for its niche** (confluence/OTF/retracement research on uploaded ES/NQ bars) and **below SOTA as a general futures day-trading backtester**.

---

## 1. What ThesisTester is

| Item | Detail |
|------|--------|
| Product | Streamlit multipage research app |
| Purpose | Empirically validate intraday confluence setups on ES/NQ |
| Research questions | Edge? Timing? Best SL/TP? |
| Stack | Streamlit, pandas, numpy, plotly, pyarrow, pytest |
| Non-goals (stated) | Live trading, order routing, options, multi-leg, portfolio optimization |

**Canonical workflow:**

```text
Data → Levels → Setup Builder → Signals → Backtest
     → Grid Search → Time Analysis → Validation → Report / Bundles
```

---

## 2. Current capabilities (factual inventory)

### 2.1 Data & instruments

| Capability | Status | Notes |
|------------|--------|-------|
| ES / NQ presets | ✅ | tick 0.25; ES $50/pt; NQ $20/pt; `America/New_York` |
| MES / MNQ | ❌ | Not in `INSTRUMENTS` |
| CSV OHLCV load | ✅ | Required cols + aliases; validation |
| Timezone localize/convert | ✅ | Source TZ → exchange TZ |
| Resample 1m→5m/15m/30m/1h/4h/1D | ✅ | No upsample |
| RTH/ETH session tags | ✅ | Clock-based |
| Continuous contract construction | ❌ | Metadata only (`rolls.py`); no Panama/back-adjust |
| Vendor API / live feed | ❌ | Upload-only |
| Tick / seconds / bid-ask / DOM | ❌ | Bar OHLCV only |

### 2.2 Levels / AOI / confluence

| Capability | Status | Notes |
|------------|--------|-------|
| Session levels (ONH/ONL, OR, pdH/L, etc.) | ✅ | Core |
| SMA/EMA, rolling VWAP | ✅ | Core |
| Prior day/week/month VAH/VAL/POC | ✅ | Typical-price volume approx |
| dVWAP_RTH | ✅ | Opt-in |
| Confirmed pivots | ✅ | Opt-in |
| TPO 30m Single Prints | ✅ | Opt-in; scalar nearest above/below |
| APOC / pAPOC | ✅ | Opt-in |
| Global cluster confluence | ✅ | Tick tolerance, min–max levels |
| Anchor-rules confluence | ✅ | Per-rule tolerances + diagnostics |
| Naked / untested levels | ✅ | Filter `any`/`all` |
| Drawn freeform AOIs | ❌ | Computed from level columns only |
| True volume-at-price / full MP object | ❌ | Approximations documented |

### 2.3 Signals

| Trigger | Status | Entry model |
|---------|--------|-------------|
| touch / reject / break / reclaim | ✅ | Next-bar open |
| 3c (retrace entry; muted/SFP variants) | ✅ | Retrace fill on entry bar |
| Directions long/short/both | ✅ | |
| Trigger TF base/1m/5m/15m | ✅ | DST-safe non-base |
| OTF at generation time | ❌ | Metadata only; filter later |

### 2.4 OTF filter

| Item | Status |
|------|--------|
| Engine + filter + integration | ✅ Implemented |
| Applied at backtest / grid / WFO / OTF matrix | ✅ |
| Default disabled (legacy safe) | ✅ |
| Look-ahead safe completed HTF bars | ✅ |
| 529 dedicated tests passing | ✅ |

### 2.5 Backtest engine

| Capability | Status | Notes |
|------------|--------|-------|
| Fixed SL/TP in ticks | ✅ | |
| Commission per side | ✅ | Default 0 |
| Adverse slippage ticks | ✅ | Default 0 |
| Same-bar SL+TP → SL-first | ✅ | Documented pessimism |
| max_holding_bars (TIME exit) | ✅ | |
| flat_by_session_close | ✅ | Same-calendar-day RTH-style |
| no_new_entries_after | ✅ | |
| Exposure policies | ✅ | allow_all / single_position / single_direction / single_setup |
| Cooldown after exit | ✅ | |
| Limit / stop / trailing / scale-in | ❌ | |
| Queue / partial fills / L2 | ❌ | |
| Overnight ETH session template | ❌ | Documented limitation |
| MAE / MFE | ✅ | |

### 2.6 Optimization & validation

| Capability | Status |
|------------|--------|
| SL × TP grid + heatmap | ✅ |
| Directional ranking / min trade gates | ✅ |
| Walk-forward SL/TP selection | ✅ (bar-index folds) |
| Bootstrap expectancy CI | ✅ |
| Sign-flip permutation | ✅ |
| Overfit heuristic on grid | ✅ |
| OTF validation matrix (5 configs) | ✅ |
| CPCV / purged CV | ❌ |
| Monte Carlo equity-path / risk-of-ruin | ❌ |
| Deflated Sharpe / PBO | ❌ |
| Optimize confluence/trigger/OTF jointly | ❌ |

### 2.7 Analytics, UI, persistence

| Capability | Status |
|------------|--------|
| R-multiple KPIs + advanced diagnostics | ✅ |
| Equity / drawdown curve | ✅ |
| Time-of-day / RTH segment analysis | ✅ |
| Long vs short split | ✅ |
| Plotly charts (levels/signals/backtest) | ✅ |
| Market replay / chart-trading simulator | ❌ |
| JSON/MD/CSV research export | ✅ |
| Research ZIP bundles | ✅ |
| Local dataset/levels/signals/setups store | ✅ |
| Config / OTF / algorithm hashing | ✅ |
| Trade runs persisted as first-class store entities | ⚠️ Session + export/bundle only |

---

## 3. Gap analysis vs SOTA checklist

### Must-have core (SOTA research-grade)

| Requirement | ThesisTester | Gap severity |
|-------------|--------------|--------------|
| Correct contract economics | ✅ ES/NQ | Low (add micros optional) |
| RTH/ETH + session exits | ✅ / partial ETH overnight | Medium for overnight systems |
| Causal engine + costs | ✅ when costs enabled | Low (defaults are zero-cost) |
| Multi-TF + levels/filters | ✅ + OTF | — Strength |
| Walk-forward / OOS | ✅ diagnostic | Medium (bar-index folds; no CPCV) |
| Trade audit + chart review | ✅ | Medium (no bar-by-bar replay) |
| Deterministic exportable artifacts | ✅ | — Strength |

### Differentiating / advanced SOTA

| Requirement | ThesisTester | Gap severity |
|-------------|--------------|--------------|
| Tick/second + bid-ask fills | ❌ | High for scalps; Medium for 3c swing-intraday |
| CPCV / deflated Sharpe / Monte Carlo | ❌ / bootstrap only | High for claim-of-edge |
| Order-flow replay | ❌ | High if OF traders are audience; N/A for confluence thesis |
| Prop trailing-DD simulator | ❌ | Medium (audience-dependent) |
| Live vs backtest drift monitor | ❌ | Medium |

### Fake-edge traps (SOTA warning list)

| Trap | ThesisTester posture |
|------|----------------------|
| No commissions/slippage | Defaults **zero** — user must set costs |
| Incomplete bars / settlement early | Strong PIT docs + OTF completed-bar policy |
| Optimize full sample then “validate” same sample | Partial: WFO + holdout matrix exist; easy to misuse grid |
| Ignoring session | Session tags + flat-by-close available |
| % PnL instead of tick value | Uses tick × point_value → R — correct |

---

## 4. Strengths (keep / lean into)

1. **Thesis-shaped workflow** — levels → confluence AOI → retracement (`3c`) → OTF regime gate → SL/TP research matches how serious ES/NQ confluence traders think.
2. **Point-in-time discipline** — documented guarantees, DST-safe trigger bucketing, OTF availability timestamps, fold-local WFO filtering.
3. **Level catalog depth** — session structure + indicators + profile + opt-in TPO/APOC/VWAP/pivots is unusually strong for a research Streamlit app.
4. **Auditability** — rejected OTF signals retained; hashes; research bundles; explicit assumptions docs.
5. **Test culture** — 1,500+ tests; OTF alone 529; contract tests against written specs.

---

## 5. Critical gaps (if goal is broader SOTA day-trading platform)

### P0 — Correctness / realism for claimed edges

1. **Zero-cost defaults** — easy to overstate expectancy; consider research presets with realistic ES/NQ costs.
2. **OHLC path ambiguity** — SL-first is conservative but not tick-true; document when results are decision-grade vs screening-grade.
3. **WFO fold design** — bar-index folds are not calendar/session-aware; can split mid-regime oddly.

### P1 — Product gaps vs day-trader expectations

4. **No market replay** — discretionary skill loop missing (FX Replay / NT Playback class).
5. **No continuous-contract engine** — depends on user-supplied continuous/segmented CSVs.
6. **OTF not applied at signal generation** — correct for research layering, confusing for “only show valid setups.”
7. **Optimization surface too narrow** — SL×TP only; confluence/OTF/trigger params not in one search.

### P2 — Statistical sophistication

8. No CPCV / purge-embargo CV  
9. No Monte Carlo path / risk-of-ruin  
10. No deflated Sharpe / probability of backtest overfitting  

### P3 — Scope expansion (optional)

11. Micros, more symbols  
12. Limit/stop/trailing orders  
13. Prop DD / daily loss / consistency rules  
14. Order flow / footprint (only if audience needs it)  
15. Live/paper/broker bridge (explicitly out of scope today)

---

## 6. Fit to intended OTF + retracement use case

For the stated valuable use case — **OTF up → long on pullback to AOI; OTF down → short on rally to AOI**:

| Layer | Present? | Quality |
|-------|----------|---------|
| AOI = confluence zones | ✅ | Strong (global + anchor) |
| Retracement entry = `3c` | ✅ | Strong, parameterized |
| Regime = OTF filter | ✅ | Strong when enabled at backtest |
| End-to-end composition | ✅ | Works as designed |
| UX clarity of composition | ⚠️ | Stale “PR 5” captions; Signals unfiltered |

**Conclusion:** For this niche thesis, ThesisTester is **aligned and largely complete**. Gaps are mainly realism defaults, validation sophistication, and general day-trader platform features outside the confluence-research niche.

---

## 7. Recommended priority roadmap (investigation opinion only)

Ordered for maximum research integrity, not feature breadth:

1. **Research cost presets** for ES/NQ (commission + 1–2 tick slippage) as first-class defaults option  
2. **Calendar/session-aware walk-forward** folds  
3. **Apply or preview OTF at Signals** (optional mode) for the intended use case  
4. **Monte Carlo + risk-of-ruin** on trade R series  
5. **CPCV / deflated Sharpe** for multi-config searches (grid + OTF matrix)  
6. **Market replay** only if discretionary validation is a product goal  
7. **Continuous roll helper** only if users struggle with CSV prep  

Do **not** chase order-flow / live trading unless the product scope explicitly expands beyond confluence research.

---

## 8. One-page verdict

```text
ThesisTester today
──────────────────
✔ Best-in-class niche: ES/NQ confluence + 3c retracement + OTF regime research
✔ Strong causality, levels, R-metrics, local reproducibility
△ Adequate (not SOTA) execution realism and anti-overfitting toolkit
✘ Not a market-replay / order-flow / prop-challenge / live platform

Use it to: screen and stress confluence theses with honest assumptions.
Don't use it to: claim tick-perfect scalp edges or prop-pass probabilities.
```

---

*Investigation-only. No production code modified.*
