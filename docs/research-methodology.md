# Research Methodology — OTF Filter Evaluation

**Project:** ThesisTester  
**Scope:** Directional One Timeframing (OTF) market-condition filter  
**Status:** Protocol published (hardening PR 5)  
**Last updated:** 2026-08-03  
**Related:** [`otf-filter.md`](otf-filter.md), [`OTF_HARDENING_AND_RELEASE_ROADMAP.md`](archive/OTF_HARDENING_AND_RELEASE_ROADMAP.md), [`OTF_RELEASE_EVIDENCE.md`](archive/OTF_RELEASE_EVIDENCE.md), [`ASSUMPTIONS_AND_LIMITATIONS.md`](ASSUMPTIONS_AND_LIMITATIONS.md)

## 1. Purpose

This document is the authoritative **user-facing research protocol** for evaluating
whether an OTF configuration improves out-of-sample (OOS) behavior for a given
ES/NQ (or related) dataset and setup thesis.

It does **not** claim that OTF has a durable edge. Synthetic fixtures and
in-repository samples are insufficient for statistical release. Users must run
this protocol on their own chronological datasets and record results honestly —
including negative, mixed, or inconclusive outcomes.

## 2. Preconditions

Before running the protocol:

1. Load a point-in-time-valid OHLCV dataset with known:
   - instrument
   - source interval (must be strictly finer than selected OTF timeframes)
   - source / exchange timezone
   - dataset identity / hash (as produced by ThesisTester persistence)
2. Confirm instrument `eth_start` (e.g. `"18:00"` for ES/NQ) and exchange timezone.
3. Generate candidate signals with the intended setup (Signals page remains
   candidate-only; OTF is applied later).
4. Keep OTF **disabled by default** until you deliberately enable matrix / WFO
   comparisons.

## 3. Fixed OTF comparison matrix

Evaluate these five configurations (no shuffling; chronological split only):

| Label | OTF |
|---|---|
| `no_otf` | Disabled (baseline) |
| `otf_15m` | 15m only |
| `otf_30m` | 30m only |
| `otf_15m_30m` | 15m + 30m (`all` alignment) |
| `otf_5m_15m_30m` | 5m + 15m + 30m (`all` alignment) |

Use OTF v1 defaults unless a controlled sensitivity study is explicitly scoped:

- `alignment_mode: all`
- `minimum_consecutive_bars: 3`
- `session_reset: session`
- `directional: true`
- `use_completed_bars_only: true`

**UI path:** Validation → OTF validation matrix  
**API path:** `thesistester.api.run_otf_validation` / `run_otf_validation_matrix`

## 4. Train / OOS rules (anti-overfit)

1. Split candidates **chronologically** (default 70/30). Never shuffle.
2. Rank / select configurations using **train metrics only**
   (`train_rank`, `is_train_selected`).
3. Use **OOS metrics for evaluation only**. OOS must never influence selection.
4. Do **not** pick a configuration from full-dataset results and treat it as
   unbiased OOS evidence.
5. Treat multi-configuration comparison as a multiple-testing risk; require
   caution before claiming improvement over `no_otf`.

## 5. Optional walk-forward extension

If walk-forward is run in addition to the matrix:

1. Record `otf_history_policy`:
   - `fold_local` (default; conservative cold starts)
   - `causal_prefix` (opt-in; prefix∪fold-local OTF source)
2. Record fold mode, window mode, train/test/step sizes, ranking metric,
   overlap policy, and exchange/`eth_start` settings.
3. Do not select WFA matrix cells by OOS performance and then report that
   selection as unbiased.

## 6. Required recording fields

For **each** dataset × market regime × configuration comparison, record:

| Field | Notes |
|---|---|
| Dataset identity / integrity hash | Persistence dataset id / content hash |
| Instrument | e.g. ES, NQ |
| Source interval | Must divide selected OTF timeframes |
| Exchange / session timezone | e.g. America/New_York |
| Effective `eth_start` | Used for OTF session reset |
| OTF algorithm version | `OTF_ALGORITHM_VERSION` |
| OTF config hash | Per configuration |
| OTF timeframes + min consecutive bars | Explicit |
| WFO policy + fold settings | If WFO used |
| Train / OOS date ranges | Chronological |
| Candidate / accepted / rejected counts | Per config, train and OOS |
| Rejection rate | And delta vs `no_otf` |
| OOS expectancy, total R, avg R | Evaluation view |
| OOS profit factor, max drawdown, win rate | Evaluation view |
| OOS long/short trade counts | Directional sample sizes |
| Trade-frequency assessment | Explicit yes/no: is apparent improvement explained only by fewer trades / lower power? |
| Verdict | Improve / worsen / mixed / inconclusive — with caveats |

Store results in a research artifact / report export and keep the OTF checklist
and rejected-signal tables for audit.

## 7. Interpreting results

- Fewer trades under OTF is **not** automatically better or worse.
- Thin OOS samples make expectancy / PF / win rate unreliable.
- Train-selected winners that degrade in OOS are a warning of overfit.
- Negative or inconclusive outcomes must be retained in the evidence record.
- OTF remains a **research admission filter**, not production advice and not a
  guarantee of edge.

## 8. Repository limitation (honest status)

As of hardening PR 5, **no real user dataset is available in this repository**.
Therefore:

- This protocol is published and ready to execute.
- No statistical release recommendation is made from synthetic fixtures alone.
- Engineering correctness / regression gates are tracked separately in
  [`OTF_RELEASE_EVIDENCE.md`](archive/OTF_RELEASE_EVIDENCE.md).

Users should paste completed matrix/WFO evidence into that evidence document
(or an attached research bundle) when performing a true statistical release
review.
