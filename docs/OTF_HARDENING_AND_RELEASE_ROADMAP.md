# OTF Hardening and Release Roadmap

**Project:** ThesisTester  
**Feature:** Directional One Timeframing (OTF) market-condition filter  
**Status:** v1 is implemented and research-ready; hardening and release evidence remain open  
**Document owner:** ThesisTester engineering  
**Last updated:** 2026-08-03  
**Related documents:** [`otf-filter.md`](otf-filter.md), [`otf-filter-roadmap.md`](otf-filter-roadmap.md), [`ENGINEERING_PROPOSAL.md`](ENGINEERING_PROPOSAL.md), [`ARCHITECTURE.md`](ARCHITECTURE.md)

> Naming note: this roadmap hardens and release-gates **OTF v1**. It does **not**
> introduce an OTF v1.1 algorithm or eligibility-semantics change. Any future
> semantic expansion (for example `any` / hierarchical alignment) would require a
> separate contract version bump and is out of scope here.

## 1. Purpose

This is the implementation-ready roadmap for hardening OTF without rewriting
its v1 engine. It is intentionally separated from
[`otf-filter-roadmap.md`](otf-filter-roadmap.md), which is the historical
implementation record and Definition-of-Done tracker for v1.

The roadmap addresses five concerns:

1. Correct futures-session behavior on every execution surface.
2. Honest, consistent user-facing and engineering documentation.
3. Deterministic enabled-OTF regression coverage in addition to legacy
   disabled-path golden coverage.
4. An optional, explicitly labeled walk-forward OTF history policy that better
   represents information known at a fold boundary.
5. A real-data release gate that does not overstate fixture or in-sample
   evidence.

The feature is named **OTF** (One Timeframing), not “OFT.”

## 2. Current assessment

### 2.1 What remains unchanged

OTF v1 already provides:

- a controlled `up`, `down`, `neutral`, and `unknown` state vocabulary;
- strictly higher-low / lower-high directional rules;
- completed higher-timeframe bar availability semantics;
- point-in-time causal signal alignment;
- `eth_start`-based trading-session reset support;
- disabled-path no-op behavior;
- backward-compatible saved setup loading;
- OTF algorithm and configuration identity;
- preserved candidate and rejected-signal audit trails;
- shared backtest, grid, walk-forward, API, reporting, and validation
  integration;
- deterministic, focused test coverage.

None of these capabilities should be redesigned by this roadmap.

### 2.2 Known gaps

| Priority | Gap | Impact |
|---|---|---|
| P0 | Streamlit Backtest, Grid, and OTF validation matrix omit instrument `eth_start`. | ES/NQ OTF may reset at midnight rather than 18:00 ET, producing incorrect overnight state. |
| P1 | Setup Builder and Signals copy still describes the pre-PR-5 metadata-only state. | Users can be misled about whether OTF is active. |
| P1 | OTF caveats and state contracts are incomplete across architecture, limitations, glossary, and top-level documentation. | Methodology and UI behavior can drift. |
| P2 | Existing golden-master coverage protects the disabled legacy pipeline only. | Enabled OTF behavior lacks a compact, reviewable golden drift gate. |
| P2 | Walk-forward `fold_local` OTF history is deliberately conservative. | Short folds can reject early candidates because no pre-fold completed OTF history is available. |
| Release | Real-dataset OOS validation and formal drift review are not complete. | The feature must not be represented as release-approved evidence of durable edge. |

### 2.3 Explicit non-goals

The following are not part of this roadmap:

- replacing the OTF state machine;
- changing OTF v1’s `all` alignment semantics;
- introducing `any` or hierarchical alignment;
- automatic timeframe or sequence-length optimization;
- automatic production configuration selection;
- chart overlays or replay visuals;
- live-trading automation.

These additions increase degrees of freedom and should be considered only after
the real-data release gate establishes whether OTF provides stable
out-of-sample value.

## 3. Global regression-safety contract

Every PR in this roadmap must comply with
[`ENGINEERING_PROPOSAL.md` §4](ENGINEERING_PROPOSAL.md):

1. **Default-off preservation:** OTF remains disabled by default.
2. **Legacy equality:** With OTF disabled, signals, trades, metrics, grid
   outputs, walk-forward outputs, and legacy golden artifacts remain
   unchanged.
3. **Additive contracts:** New configuration, API, artifact, and
   `st.session_state` fields are additive. Missing legacy fields resolve to
   deterministic defaults.
4. **No silent migration:** Existing setups, signal artifacts, AI run specs,
   and exported bundles must not be silently reinterpreted.
5. **Point-in-time proof:** Any new state, filter, or fold behavior must have
   append-data and future-shock tests proving that data after time `T` cannot
   alter an OTF decision at or before `T`.
6. **Golden protection:** Existing legacy golden artifacts remain unchanged.
   New enabled-mode behavior receives separate canonical golden coverage.
7. **Determinism:** No wall-clock, dictionary-order, or unstated random
   behavior may affect a result.
8. **Same-PR documentation:** `ARCHITECTURE.md`,
   `ASSUMPTIONS_AND_LIMITATIONS.md`, `METRICS_GLOSSARY.md`, and the relevant
   roadmap are updated in the same PR when their contract changes.
9. **AI/API/UI parity:** A configuration created through the AI chat,
   headless API, or Streamlit UI has the same normalized meaning and produces
   equivalent results on the same input.

Each PR body must include a `Regression safety` section stating:

- the preserved legacy guarantees;
- the intentional new or corrected behavior;
- the tests and golden fixtures that enforce each claim;
- whether a schema/version field was added, preserved, or intentionally not
  changed.

## 4. Delivery sequence

| Order | PR | Purpose | Runtime behavior change | Status |
|---|---|---|---|---|
| 1 | PR 1 — Session propagation parity | Fix omitted futures session boundary inputs. | Corrects enabled OTF on affected Streamlit paths only. | Merged |
| 2 | PR 2 — UI and documentation honesty | Remove stale pre-integration wording and complete operational docs. | No engine or filtering logic change. | Merged |
| 3 | PR 3 — Enabled OTF golden gate | Add deterministic enabled-mode drift protection. | No production behavior change. | Merged |
| 4 | PR 4 — Causal-prefix WFO policy | Add optional pre-fold OTF state history. | New opt-in WFO behavior; default unchanged. | Implemented (this branch) |
| 5 | PR 5 — Release evidence and sign-off | Record real-data OOS evidence and formal release decision. | No engine behavior change. | Pending |

**Merge order is strict.** PR 2 must not merge before PR 1: documentation that
claims `eth_start` parity must describe the corrected surfaces. PR 3 should
follow PR 1 so the enabled golden fixture captures correct futures-session
boundaries. PRs 1–3 may be reviewed in parallel but must land in order.
PR 4 depends on PRs 1–3. PR 5 depends on all preceding PRs.

## 5. PR 1 — Futures-session propagation parity

### 5.1 Objective

Pass the instrument’s `eth_start` consistently to OTF execution paths so an
ES/NQ trading session resets at 18:00 ET rather than calendar midnight.

### 5.2 Problem statement

The OTF engine supports `eth_start`, and the public API already forwards
`inst.eth_start`. Streamlit Backtest, Grid, and the validation matrix currently
omit it. Consequently, UI users running overnight futures data can obtain OTF
states that differ from the API and the documented session contract.

**This is a deliberate behavior correction for already-enabled Streamlit
users.** With OTF enabled on Backtest, Grid, or the validation matrix,
overnight accepted/rejected populations and rejection reasons may change after
this PR because session boundaries become ETH-correct. The disabled OTF path
must remain unchanged. The PR body must state this intentional correction
explicitly under `Regression safety`.

### 5.3 In scope

- `pages/7_Backtest.py`
- `pages/8_Grid_Search.py`
- `pages/10_Validation.py`
- `tests/test_otf_integration.py`
- `tests/test_otf_validation.py`
- `tests/test_api.py`
- `docs/otf-filter-roadmap.md`

### 5.4 Implementation requirements

1. Backtest passes `eth_start=inst.eth_start` to
   `apply_configured_otf_filter()`.
2. Grid passes `eth_start=inst.eth_start` to
   `apply_configured_otf_filter()`.
3. The validation matrix passes `eth_start=_inst.eth_start` to
   `run_otf_validation_matrix()`.
4. A known instrument always uses its configured `eth_start`.
5. An unknown instrument uses an explicit existing fallback only; the PR must
   not infer a new session template.
6. OTF result summaries and research-facing metadata record the **effective**
   `eth_start` and session timezone used for the filter application (Backtest,
   Grid, validation matrix, and any shared summary helper touched by this PR).
   This makes UI vs API session-boundary parity inspectable in artifacts
   without requiring readers to infer instrument defaults.
7. Do not modify:
   - OTF state-machine rules;
   - `OTF_ALGORITHM_VERSION`;
   - OTF configuration precedence;
   - disabled-path behavior;
   - setup persistence format.

### 5.5 Required fixtures and tests

Create or extend a deterministic ES/NQ fixture that spans:

- Monday 22:00 ET;
- Monday 23:00 ET;
- Tuesday 00:00 ET;
- Tuesday 00:30 ET;
- the following 18:00 ET boundary.

Add tests that prove:

1. The OTF sequence is continuous through midnight for
   `eth_start="18:00"`.
2. The OTF sequence resets at the next 18:00 ET boundary.
3. UI-equivalent Backtest composition and `api.run_backtest()` return the same:
   - accepted signal IDs;
   - rejected signal IDs;
   - rejection reasons;
   - OTF metadata.
4. UI-equivalent Grid composition and `api.run_grid()` return equivalent OTF
   outputs.
5. UI validation-matrix input produces the same session behavior as the
   headless validation path.
6. Disabled OTF output remains unchanged.

### 5.6 Acceptance criteria

- No known futures execution surface resets OTF at midnight.
- API, Backtest, Grid, WFO, and validation paths have verified
  `session_timezone`/`eth_start` parity.
- OTF summaries / artifact metadata expose the effective `eth_start` and
  session timezone used for filtering.
- WFO fold OTF and Validation `walk_forward_otf_filter` share
  `resolve_otf_session_timezone()` so omitted session-exit timezone falls
  back to exchange timezone in both filter execution and recorded metadata.
- The regression suite proves both the corrected overnight path and unchanged
  disabled path.
- The PR `Regression safety` section explicitly records that enabled Streamlit
  overnight results may change and that disabled-path equality is preserved.

### 5.7 Regression commands

```bash
python3 -m pytest -q \
  tests/test_otf.py \
  tests/test_otf_filter.py \
  tests/test_otf_integration.py \
  tests/test_otf_validation.py \
  tests/test_api.py

python3 -m pytest -q tests/test_golden_master.py
```

## 6. PR 2 — UI and documentation honesty

### 6.1 Objective

Ensure that user-facing text, architecture documentation, methodology, and
limitations describe the OTF implementation that currently runs.

### 6.2 In scope

- `pages/2_Setup_Builder.py`
- `pages/6_Signals.py`
- `pages/7_Backtest.py`
- `pages/8_Grid_Search.py`
- `README.md`
- `docs/otf-filter.md`
- `docs/otf-filter-roadmap.md`
- `docs/ARCHITECTURE.md`
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
- `docs/METRICS_GLOSSARY.md`
- `docs/POINT_IN_TIME_GUARANTEES.md`, if present
- targeted Setup Builder and Signals page-helper tests

### 6.3 Implementation requirements

1. Remove stale claims that OTF is “saved for PR 5,” “metadata only,” or “not
   filtered until PR 5.”
2. Explain the actual composition:
   - Signals preserve the complete candidate population.
   - Backtest and Grid apply OTF before execution.
   - Walk-forward applies OTF inside each fold.
   - Rejected signals remain available for audit/export.
3. Display or describe OTF configuration provenance:
   - signal-run `signal_settings["otf_filter"]` has highest precedence;
   - later Setup Builder edits do not change an existing signal run;
   - users regenerate signals to use changed OTF settings.
4. Document the following limitations:
   - completed HTF bars add intentional decision lag;
   - `unknown`, `neutral`, and opposing state reject directional signals;
   - `eth_start` and session timezone determine futures state boundaries;
   - source data must be strictly finer than selected OTF timeframe;
   - `all` alignment can materially reduce sample size;
   - OTF validation is diagnostic and not proof of edge;
   - current WFO `fold_local` behavior is conservative on fold cold starts.
5. Add all OTF-related `st.session_state` keys, producers, consumers, and
   artifact projections to `ARCHITECTURE.md`.
6. Add glossary definitions for:
   - OTF state;
   - OTF rejection rate;
   - OTF accepted/rejected signal count;
   - train/OOS OTF matrix labels.

### 6.4 Acceptance criteria

- No current UI or document describes OTF as pre-PR-5 metadata-only behavior.
- A user can determine which OTF configuration is active in a research run.
- A researcher can identify conditions that make OTF data or results
  incomparable.
- No runtime behavior changes beyond user-visible explanatory text.

### 6.5 Regression commands

```bash
python3 -m pytest -q \
  tests/test_setup_builder_helpers.py \
  tests/test_signals_page_helpers.py \
  tests/test_otf_integration.py

python3 -m pytest -q tests/
```

## 7. PR 3 — Enabled OTF golden and drift gate

### 7.1 Objective

Add a compact, deterministic regression gate for enabled OTF behavior without
weakening or changing the existing legacy golden gate.

### 7.2 In scope

- `tests/fixtures/golden/`
- golden fixture generator and canonicalization helpers
- `tests/test_golden_master.py`
- `tests/test_otf_golden.py` (new)
- `tests/fixtures/golden/README.md`
- `docs/otf-filter-roadmap.md`

### 7.3 Fixture requirements

Add a small deterministic futures fixture containing:

- one-minute source OHLCV data;
- an overnight session that crosses midnight;
- established OTF-up and OTF-down sequences;
- `neutral` and `unknown` state periods;
- both long and short candidates;
- deterministic accepted and rejected signals;
- deterministic rejection reasons;
- at least one simulated accepted trade.

The fixture is a regression contract, not a performance claim and not a
replacement for real-data validation.

### 7.4 Canonical enabled-OTF projection

Record a reviewable projection containing:

- normalized OTF config;
- OTF algorithm version;
- OTF configuration hash;
- accepted signal IDs;
- rejected signal IDs;
- rejection reasons;
- canonical accepted-trade frame;
- candidate, accepted, rejected, and rejection-rate summary fields.

Use the project’s existing value-level canonical comparison strategy. Do not
introduce unstable byte-level serialization requirements.

### 7.5 Required tests

1. The enabled fixture reproduces its canonical accepted/rejected population.
2. The enabled fixture reproduces its canonical trade projection.
3. Appending future bars does not alter historical enabled OTF decisions.
4. Extreme future highs/lows do not alter historical enabled OTF decisions.
5. The equivalent disabled run preserves the existing legacy golden outputs.
6. The legacy golden files are not changed by this PR.

### 7.6 Acceptance criteria

- Enabled OTF has a deterministic drift gate.
- Legacy golden coverage remains isolated and unchanged.
- Golden updates require an explicit reason, readable difference, and
  regression justification.

### 7.7 Regression commands

```bash
python3 -m pytest -q \
  tests/test_golden_master.py \
  tests/test_otf_golden.py \
  tests/test_otf.py \
  tests/test_otf_filter.py \
  tests/test_otf_contract.py
```

## 8. PR 4 — Opt-in causal-prefix walk-forward OTF history

### 8.1 Objective

Add an opt-in WFO policy that allows each fold to establish OTF state from
strictly earlier observable bars, while preserving current `fold_local`
behavior as the default.

### 8.2 Motivation

`fold_local` is intentionally conservative: it recomputes OTF only from a
fold’s source slice and rejects early candidates when insufficient HTF history
exists. This prevents cross-fold leakage but can be harsher than a live
workflow, where previous completed HTF bars were observable at the beginning
of a new test fold.

The new policy must preserve information-time validity, not import previous
fold performance or signals.

### 8.3 New additive configuration

```yaml
walk_forward:
  otf_history_policy: fold_local
```

Allowed values:

| Value | Meaning | Default |
|---|---|---|
| `fold_local` | Compute OTF from source bars inside each fold only. | Yes |
| `causal_prefix` | Compute OTF from **prefix ∪ fold-local** source bars: bars strictly before fold start establish prior OTF state, and fold-local bars continue the state machine during the fold. Evaluate and score only fold-local signals. | No |

`causal_prefix` is **not** prefix-only. Prior bars seed state; intra-fold
completed HTF bars remain required for ongoing OTF updates. Signal admission
still uses only HTF bars with `availability_timestamp <= decision_timestamp`.

### 8.4 In scope

Core and public facade:

- `thesistester/analytics/walk_forward.py`
- WFO configuration normalization and validation
- `thesistester/api.py`
- `thesistester/reporting.py`
- research bundle and export composition
- `pages/10_Validation.py`

AI chat integration:

- `thesistester/assistant/thesis_compiler.py`
- `thesistester/assistant/workspace.py`
- `thesistester/assistant/registry.py`
- `thesistester/assistant/explainer.py`
- `thesistester/assistant/tools.py`, if required by forwarding or evidence
  projection

Tests:

- `tests/test_walk_forward.py`
- `tests/test_otf_integration.py`
- `tests/test_api.py`
- `tests/test_assistant_execution_parity.py`
- new targeted AI schema/error tests

Documentation:

- `docs/otf-filter.md`
- `docs/otf-filter-roadmap.md`
- `docs/ARCHITECTURE.md`
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
- `docs/AGENT_GUIDE.md`

### 8.5 Causal-prefix contract

1. The OTF source series for a fold is **prefix ∪ fold-local bars** (not
   prefix alone). Prefix bars seed prior state; fold-local bars continue the
   state machine for decisions inside the fold.
2. Prefix source bars are market-state input only.
3. Prefix bars must have timestamps strictly before a fold’s evaluation start.
4. Prefix bars may establish OTF state but may not contribute:
   - candidate signals;
   - accepted/rejected signal counts for the fold;
   - simulated trades;
   - training metrics;
   - OOS metrics;
   - ranking or model-selection evidence.
5. Signals in a fold may use only OTF HTF bars whose availability timestamp is
   at or before that signal’s decision timestamp.
6. A source bar after the fold start must not alter a decision for an earlier
   signal.
7. A source bar after the end of a fold must not affect any result in that
   fold.
8. `fold_local` remains the default and must preserve current results.
9. `causal_prefix` must be visible in:
   - WFO rows;
   - WFO summary;
   - report/export metadata;
   - research artifact;
   - API result;
   - AI evidence packet and caveats.

This is a WFO orchestration policy. It does not change OTF state-machine
semantics. Do not increment `OTF_ALGORITHM_VERSION` unless the OTF calculation
itself changes. Version or fingerprint the WFO policy in WFO result metadata
instead.

### 8.6 AI chat integration requirements

The AI chat is a public execution surface and must be updated in the same PR.

1. The typed RunSpec/compiler accepts `walk_forward.otf_history_policy`.
2. Missing field resolves to `fold_local`.
3. Unsupported values fail clearly; they must not be dropped, coerced, or
   silently replaced.
4. Workspace state merges and preserves the field.
5. AI capability descriptions explain the policy and default.
6. API, UI, and AI results expose the effective normalized policy.
7. AI evidence/reporting includes the policy so a user can interpret
   fold-local cold starts versus causal-prefix history correctly.
8. Direct API and AI-executed runs with the same input have equivalent:
   - effective normalized WFO config;
   - OTF metadata;
   - accepted/rejected candidate populations;
   - WFO fold outputs and metrics.

### 8.7 Required tests

1. Existing `fold_local` output is unchanged.
2. Missing policy defaults to `fold_local`.
3. Invalid policy is rejected consistently by UI, API, compiler, and AI tool
   boundary.
4. `causal_prefix` uses enough strictly preceding completed HTF history to
   evaluate an otherwise cold-start candidate.
5. Prefix bars never appear in scored fold populations or trades.
6. A post-fold-start source bar cannot alter an earlier decision.
7. Appended future data cannot alter historical fold output.
8. Repeated runs are deterministic.
9. Disabled OTF WFO remains unchanged under both policies.
10. UI-equivalent, API, and AI paths produce equivalent results for each
    policy.

### 8.8 Acceptance criteria

- Existing WFO behavior remains the default and is regression-proven.
- Causal-prefix is opt-in, auditable, deterministic, and point-in-time safe.
- The AI cannot omit, invent, or silently change the policy.
- All public execution surfaces share one normalized policy contract.

### 8.9 Regression commands

```bash
python3 -m pytest -q \
  tests/test_walk_forward.py \
  tests/test_otf_integration.py \
  tests/test_api.py \
  tests/test_assistant_execution_parity.py

python3 -m pytest -q \
  tests/test_otf.py \
  tests/test_otf_filter.py \
  tests/test_otf_contract.py \
  tests/test_golden_master.py
```

## 9. PR 5 — Real-data release evidence and formal sign-off

### 9.1 Objective

Close the OTF release gate using reproducible real-data evidence rather than
synthetic fixture behavior or in-sample results.

### 9.2 In scope

- `docs/otf-filter-roadmap.md`
- `docs/research-methodology.md` — **create or update** (this file may not
  yet exist in the repository; do not assume it is present)
- this document, if release status changes
- a structured release-evidence/checklist document, if needed

This PR makes no engine behavior changes.

### 9.3 Required research protocol

Document the protocol in `docs/research-methodology.md` (create the file if
absent) and execute it for each selected ES/NQ dataset and distinct market
regime:

1. Use chronological train/OOS separation only.
2. Evaluate the fixed matrix:
   - no OTF;
   - 15m OTF;
   - 30m OTF;
   - 15m + 30m OTF;
   - 5m + 15m + 30m OTF.
3. If WFO is run, record the selected `otf_history_policy`.
4. Select/rank only from train metrics.
5. Use OOS results for evaluation only.
6. Record:
   - dataset identity and integrity/hash information;
   - instrument;
   - source interval;
   - exchange/session timezone;
   - effective `eth_start` used for OTF;
   - OTF algorithm version;
   - OTF config hash;
   - OTF timeframes and minimum consecutive comparisons;
   - WFO policy and fold settings, if applicable;
   - train/OOS date ranges;
   - candidate, accepted, rejected, and trade counts;
   - rejection rate;
   - OOS expectancy;
   - OOS total R;
   - OOS average R;
   - OOS profit factor;
   - OOS maximum drawdown;
   - OOS win rate;
   - OOS long/short trade counts;
   - an explicit assessment of whether apparent improvement is caused only by
     lower trade frequency.

### 9.4 Formal engineering sign-off

The sign-off records that:

- PR 1 session parity is verified;
- legacy disabled-path golden remains green;
- enabled OTF golden remains green;
- OTF future-shock and append-data tests remain green;
- AI/API/UI parity tests remain green;
- full CI is green;
- all required documentation reflects the released behavior;
- no automatic production selection or claim of durable edge is made.

### 9.5 Acceptance criteria

- The release status is updated based on recorded evidence, not assertion.
- Negative, mixed, or inconclusive OOS results remain documented rather than
  suppressed.
- OTF remains framed as a research filter, not a guarantee of performance.

## 10. Test matrix

### 10.1 Focused OTF contract and engine

```bash
python3 -m pytest -q \
  tests/test_otf.py \
  tests/test_otf_filter.py \
  tests/test_otf_contract.py \
  tests/test_otf_integration.py \
  tests/test_otf_validation.py \
  tests/test_otf_baseline.py
```

### 10.2 Persistence, API, and WFO

```bash
python3 -m pytest -q \
  tests/test_setup_config.py \
  tests/test_local_store.py \
  tests/test_api.py \
  tests/test_walk_forward.py
```

### 10.3 AI parity

```bash
python3 -m pytest -q tests/test_assistant_execution_parity.py
```

### 10.4 Golden gates

```bash
python3 -m pytest -q \
  tests/test_golden_master.py \
  tests/test_otf_golden.py
```

### 10.5 Final gate

```bash
python3 -m pytest -q tests/
```

## 11. Definition of done for this roadmap

This roadmap is complete only when:

- all five PRs have satisfied their acceptance criteria;
- disabled OTF legacy outputs remain unchanged;
- enabled OTF has deterministic golden and future-shock coverage;
- `eth_start` parity is verified across UI, API, validation, WFO, and AI;
- OTF summaries / artifacts record the effective `eth_start` and session
  timezone used for filtering;
- UI and documentation accurately describe enabled OTF behavior;
- `causal_prefix`, if implemented, uses prefix ∪ fold-local source bars,
  remains opt-in/default-`fold_local`, is versioned, documented, and
  parity-tested across AI/API/UI;
- real-data OOS evidence and formal engineering sign-off are recorded
  (including create-or-update of `docs/research-methodology.md`);
- the feature’s release status is updated honestly;
- no OTF algorithm / eligibility-semantics version bump was introduced by
  this hardening series unless a later, separately approved contract change
  explicitly requires it.

## 12. Document change log

| Date | Change |
|---|---|
| 2026-08-03 | Initial hardening and release roadmap published on `main`. |
| 2026-08-03 | Review refinements: rename away from misleading “v1.1”; require strict PR merge order; document PR 1 as intentional enabled-Streamlit overnight correction; require effective `eth_start`/timezone in OTF summaries; clarify `causal_prefix` as prefix ∪ fold-local; require create-or-update for `docs/research-methodology.md`. |
