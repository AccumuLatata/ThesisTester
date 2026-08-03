# OTF Release Evidence and Sign-off

**Project:** ThesisTester  
**Feature:** Directional One Timeframing (OTF) market-condition filter  
**Document type:** Hardening PR 5 release evidence / checklist  
**Last updated:** 2026-08-03  
**Baseline commit (main at recording):** `6fe8c54` (merge of hardening PR 4 / #212)  
**Related:** [`OTF_HARDENING_AND_RELEASE_ROADMAP.md`](OTF_HARDENING_AND_RELEASE_ROADMAP.md), [`research-methodology.md`](research-methodology.md), [`otf-filter.md`](otf-filter.md)

## 1. Release framing (honest)

| Layer | Status | Notes |
|---|---|---|
| Engineering hardening (PR 1–4) | **Complete** | Session parity, UI/docs honesty, enabled golden gate, WFO history policy |
| Engineering sign-off (this PR) | **Complete** | Verification suites recorded below |
| Real-dataset OOS statistical release | **Open / not executed in-repo** | No real user dataset is available in the repository; do not fabricate edge |
| Product default | **Disabled** | OTF remains opt-in; never auto-selected for production |

**Verdict for repository state:** OTF is **research-ready and engineering-signed**,
disabled by default. It is **not** statistically release-approved as a durable
edge from in-repo evidence alone.

## 2. Hardening PR delivery record

| PR | Title | Status |
|---|---|---|
| 1 | Futures-session `eth_start` propagation parity | Merged (#209) |
| 2 | UI and documentation honesty | Merged (#210) |
| 3 | Enabled OTF golden / drift gate | Merged (#211) |
| 4 | Opt-in WFO `otf_history_policy` | Merged (#212) |
| 5 | Real-data protocol + formal engineering sign-off | This document |

## 3. Formal engineering sign-off checklist

Recorded on 2026-08-03 against `thesistester==0.2.0`, Python 3.12.3, pandas 3.0.5,
git `6fe8c54`.

| Criterion | Result | Evidence |
|---|---|---|
| PR 1 session parity verified | ✅ | UI/API/WFO forward `eth_start`; overnight parity tests in `tests/test_otf_integration.py` / `tests/test_api.py` |
| Legacy disabled-path golden green | ✅ | `tests/test_golden_master.py` — 7 passed (included in §4.4) |
| Enabled OTF golden green | ✅ | `tests/test_otf_golden.py` — included in §4.4 (23 total golden-gate tests) |
| OTF future-shock / append-data green | ✅ | `tests/test_otf.py` LookaheadSafety + enabled-golden / WFO history future-shock tests |
| AI/API/UI parity green | ✅ | `tests/test_assistant_execution_parity.py` (8 passed); API WFO/OTF tests in `tests/test_api.py` |
| Full CI suite green (local final gate) | ✅ | `pytest -q tests/` → **1852 passed** (§4.5) |
| Required documentation reflects released behavior | ✅ | README, ARCHITECTURE, ASSUMPTIONS, METRICS, PIT, otf-filter, roadmaps, research-methodology |
| No automatic production selection / no durable-edge claim | ✅ | Defaults disabled; matrix/UI caveats; this document forbids fabricating OOS proof |

**Engineering sign-off:** Approved for research use under default-off policy.  
**Statistical / business release:** Not approved from repository fixtures.

## 4. Verification suite results (recorded)

### 4.1 Focused OTF contract and engine

```bash
python3 -m pytest -q \
  tests/test_otf.py \
  tests/test_otf_filter.py \
  tests/test_otf_contract.py \
  tests/test_otf_integration.py \
  tests/test_otf_validation.py \
  tests/test_otf_baseline.py
```

**Result:** `546 passed in 12.33s`

### 4.2 Persistence, API, and WFO

```bash
python3 -m pytest -q \
  tests/test_setup_config.py \
  tests/test_local_store.py \
  tests/test_api.py \
  tests/test_walk_forward.py
```

**Result:** `151 passed in 6.99s`

### 4.3 AI parity

```bash
python3 -m pytest -q tests/test_assistant_execution_parity.py
```

**Result:** `8 passed in 4.11s`

### 4.4 Golden gates

```bash
python3 -m pytest -q \
  tests/test_golden_master.py \
  tests/test_otf_golden.py
```

**Result:** `23 passed in 0.87s`

### 4.5 Final gate

```bash
python3 -m pytest -q tests/
```

**Result:** `1852 passed in 54.90s`

## 5. Real-dataset OOS evidence (pending user execution)

### 5.1 Status

| Item | Status |
|---|---|
| Protocol published (`docs/research-methodology.md`) | ✅ |
| In-repo real ES/NQ user dataset available | ❌ |
| Matrix executed on real user data | ❌ Not run |
| Multi-regime confirmation | ❌ Not run |
| Statistical release recommendation | ❌ Not issued |

### 5.2 Evidence log template (fill per dataset / regime)

Copy one block per dataset × regime. Reviewers must retain negative/mixed/inconclusive outcomes.

```text
Dataset id / hash:
Instrument:
Source interval:
Exchange timezone:
eth_start:
OTF algorithm version:
Train/OOS date ranges:
WFO used? (yes/no); otf_history_policy:
Train-selected configuration label:
OOS metrics vs no_otf (expectancy / total R / PF / max DD / win rate / trade counts):
Rejection rates:
Is apparent improvement explained only by lower trade frequency? (yes/no/uncertain):
Verdict (improve / worsen / mixed / inconclusive):
Artifact / bundle path:
Reviewer:
Date:
```

### 5.3 Explicit non-claims

- Synthetic overnight fixtures and golden masters prove **correctness / drift**,
  not edge.
- A train-selected matrix winner is **not** a production recommendation.
- Absence of real-data rows above means statistical release remains **open**.

## 6. Operational release posture

Until §5 is completed on real user data:

1. Ship OTF **disabled by default**.
2. Treat Validation matrix / WFO OTF results as **diagnostic**.
3. Require users to follow `docs/research-methodology.md` before enabling OTF
   in any decision process.
4. Keep rejected-signal audit trails and config hashes in research artifacts.

When §5 is completed, update this document with filled evidence blocks and only
then reconsider the statistical release line in the status table.
