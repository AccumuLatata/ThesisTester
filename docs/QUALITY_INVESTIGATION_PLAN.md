# Quality Investigation Plan — Code Quality and Application Quality (QI)

**Document type:** Investigation roadmap + synthesis protocol + remediation-program template
**Date:** 2026-09-12
**Series code:** **QI** (Quality Investigation). Remediation follow-on series: **QR** (Quality Remediation), defined in §9 but *not* opened by this document.
**Status:** **Planned.** QI-0 baseline numbers in §4 were measured on `main` at `e82c2a9` (2026-09-08) while writing this plan; every other slice is `Not started`. **Blocking precondition:** `main` CI has been red since 2026-09-05 (§4.3); the §4.6 hotfix must land before QI-1…QI-14 start.
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4 (incl. §4.1 golden-master spec and §4.2 PR checklist). The investigation phase (QI-0…QI-15) is **research-only**; the remediation phase (QR) is where code changes happen.
**Inputs (read first, do not redo):**

| Input | What it already settled | How QI uses it |
|---|---|---|
| `AUDIT_FINAL.md` on `origin/cursor/audit-final-merge-3a8e` (2026-08-18, research-honesty audit, slices 0–7, PRs [#390](https://github.com/AccumuLatata/ThesisTester/pull/390)–[#398](https://github.com/AccumuLatata/ThesisTester/pull/398)) | Causal-at-T map, three critical defects (C1–C3), H1–H16, §5 locked contracts, §7 "not found" list | **Carry-over, not re-audit.** QI re-verifies only the *status* of items still open after AH0–AH6 (§A.3), never the math of locked layers |
| `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` (AH0–AH6 landed) | Fixed C1, C2, C3, H1 (partial), H3, H6; locked ten product decisions | QI treats AH §2 as frozen |
| `docs/research/THESISTESTER_ANALYSIS.md` (2026-07-29) | W1–W16 capability/quality weaknesses; most closed by R9–R22 | §A.3 lists which W-items are still relevant |
| `docs/archive/REPOSITORY_INVESTIGATION_WORKSTREAMS.md` (2026-07-23, never executed) | Finding-record schema, classification and severity vocabulary | QI **reuses** its vocabulary (§3.3) so old and new findings are comparable |

> **Why a new plan and not the archived WS plan?** The WS plan was correctness-only, predates R9–R22, the Study/Journal/Assistant subsystems (~60% of today's code), and the 2026-08 honesty audit. It has no code-quality axis, no synthesis protocol, and no path from findings to a remediation program. This document supersedes it for scope; it inherits its evidence discipline.

---

## 1. Purpose and the two quality axes

ThesisTester has grown to **~82k lines of library code, ~18k lines of Streamlit pages, ~93k lines of tests across 145 test files / 3,715 test functions, and 66 docs (~35k lines)** in 1,875 commits. The correctness of the *engine core* has been audited; the *quality of the whole system as an evolving product* has not. Two axes are investigated together because they fail together: unmaintainable code hides application defects, and unclear product behavior produces defensive, tangled code.

| Axis | Question | ISO/IEC 25010 characteristics covered |
|---|---|---|
| **Code quality** | Can the next 100 PRs land as safely as the last 100? | Maintainability (modularity, reusability, analysability, modifiability, testability), Security (code-level), Performance efficiency (code-level), Compatibility |
| **Application quality** | Does the product do what it claims, for every user path, with honest outputs? | Functional suitability (completeness, correctness, appropriateness), Reliability (fault tolerance, recoverability), Usability (operability, error protection, learnability), Portability, Security (trust boundaries) |

### 1.1 Deliverables

1. **Per-slice investigation reports** `docs/quality/QI-<nn>_<slug>.md` (QI-1…QI-14), each ending in a finding table using the §3.3 record schema.
2. **`docs/quality/QI-15_SYNTHESIS.md`** — the merged, deduplicated, scored picture (§7).
3. **`docs/QUALITY_REMEDIATION_PLAN.md`** (QR series) — the improvement program derived from the synthesis (§9 template). Opened only after QI-15 is signed.
4. **Machine-readable finding registry** `docs/quality/findings.csv` (one row per finding, §7.1 columns) so the synthesis is reproducible and the remediation plan can cite finding IDs.

### 1.2 Explicit non-goals of the investigation phase

- No code, test, fixture, config, dependency, or workflow edits outside QI-0's single additive tooling PR (§5, QI-0).
- No golden regeneration, no re-derivation of `AUDIT_FINAL.md` §5 locked contracts, no reopening of completed series (AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX/RS/SB/SIA/SV/SO/SAF/LC/WMV/TV/AP/RP/DA/TJ/JS/AO/SW/AH).
- No product-scope decisions (e.g. "remove voice", "collapse composers"). Those are QR decisions, taken with evidence from QI.
- No benchmarking against competitors; `docs/research/SOTA_BACKTESTING_LANDSCAPE.md` remains the SOTA reference.

---

## 2. Non-negotiable guardrails (all slices)

1. **Research only.** Slices QI-1…QI-15 create files under `docs/quality/` only. Running code, tests, probes, and throwaway scripts under `/tmp` is allowed and expected; committing them is not.
2. **Regression-safe.** `pytest -q` must be identical before and after a slice (no tracked file changed). Probe tests live in `/tmp` and are pasted into the report as evidence.
3. **Drift-safe.** Stay inside the slice's `Scope` file list. Adjacent observations go into the report's `Handoffs` section with the target slice ID — never into another slice's scope.
4. **Evidence or it is not a finding.** Every finding cites file paths + symbols (no line numbers — they drift; the repo already follows this in `ARCHITECTURE.md`), the exact command, its output, and the commit SHA.
5. **Locked contracts are inputs.** Anything in `AUDIT_FINAL.md` §5 or `AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 is a premise. A finding that says "the design should be X instead" is classified *Design limitation* with `confidence=n/a`, and cannot carry severity above Medium.
6. **Financial caution.** Never describe a metric, backtest, or Study result as "correct" or "reliable" in a report unless the slice verified data, execution, P&L, session, and bias controls for that path. Use the vocabulary of §3.3.
7. **Isolation.** Use a throwaway `THESISTESTER_STORE_DIR` under `/tmp` for any probe that touches persistence. Never run probes against a real `.thesistester_store`, never with real `OPENAI_API_KEY`/xAI keys, never commit desk PII (journal fixtures are synthetic).
8. **Docs tracking.** Each finding names the living doc that would need amending during QR (`ASSUMPTIONS_AND_LIMITATIONS.md`, `ARCHITECTURE.md`, `USER_GUIDE.md`, `AGENT_GUIDE.md`, `METRICS_GLOSSARY.md`, or a contract doc). Do not amend it during QI.
9. **Sub-agent prompts** for slices must restate rules 1–8 verbatim (§8.2 template does).

---

## 3. Method

### 3.1 Quality model and metric definitions

All metrics are reproducible from the commands in §A.1. Thresholds are *investigation triggers* (they decide what gets read closely), not pass/fail gates — QR decides gates.

| Metric | Tool | Trigger | Rationale |
|---|---|---|---|
| Cyclomatic complexity per function | `radon cc -s` | grade **D+** (CC ≥ 21) → must be read and classified; **F** (CC ≥ 41) → mandatory finding (`Maintainability risk`) | The engine's F-grade functions are exactly where every audit defect (C1, H6, H7) lived |
| Maintainability Index per module | `radon mi -s` | **MI < 20** → module is a refactor candidate; **MI = 0.00** → structural finding | Nine pages score 0.00 today (§4) |
| Function length | `radon raw` / manual | > 150 physical lines | Streamlit render functions routinely exceed this; the trigger forces a "what could be extracted?" answer |
| Broad exception handlers | `rg 'except Exception|except:'` | each occurrence classified: *narrow-guard OK* / *swallows state* / *hides defect* | 83 today; the Signals page precedent (`ARCHITECTURE.md` "narrow exception guards") is the accepted pattern |
| Dead code candidates | `vulture --min-confidence 60` | each candidate: *false positive (Streamlit callback / registry)* / *dead* / *test-only public API* | 110 candidates today |
| Encapsulation leaks | `rg 'from thesistester\.[\w.]+ import .*\b_[a-z]'` | each cross-module private import | 10 today; each is an implicit API |
| Streamlit coupling in the library | `rg '^import streamlit|^from streamlit' thesistester` | any module other than the documented boundary | 1 today (`thesistester/app_state.py`); the R18 boundary says the library is Streamlit-free |
| `st.session_state` fan-in/fan-out | `rg -c 'st\.session_state' pages` per page, plus key-level producer/consumer graph | keys not in the `ARCHITECTURE.md` contract table | 1,176 references; the contract table is the ground truth |
| Test → module traceability | coverage per module (`--cov-report=term-missing`), plus manual mapping of the 145 test files to the 15 slices | any library module < 70% or any public function with 0 tests | Suite-wide coverage is high but unevenly distributed |
| Test wall-time | `pytest --durations=25` | any single test > 5 s; any file > 60 s | Feedback-loop cost is a maintainability metric |
| Determinism | run the slice's suite twice with `-p no:randomly` and once with `PYTHONHASHSEED` varied; diff outputs | any difference | Repo policy: no dict-order or wall-clock dependence |
| Mutation score (sample) | `mutmut` on `engine/backtest.py`, `engine/intrabar.py`, `analytics/metrics.py`, `analytics/walk_forward.py` only | < 70% killed → coverage is shallow | Only way to distinguish "covered" from "asserted"; sampled (four files, their own test files only) because mutation testing multiplies suite runs by the mutant count |
| Dependency vulnerabilities | `pip-audit` (project deps only; environment-only packages recorded separately) | any known CVE in a declared dependency | See §4 for the environment-vs-project distinction |
| Static security | `bandit -r thesistester -ll` | Medium+ | Yaml load, subprocess spawn (Studies launch), zip extraction (bundles), pickle/parquet, secrets |
| Type-check strictness probe | `mypy --strict` / `pyright` on `thesistester/engine`, `analytics`, `api.py` (read-only, no config committed) | error count per module | Annotations exist almost everywhere (1,588 annotated vs 6 unannotated defs); their *soundness* has never been checked |
| Docs-to-code drift | manual: every `USER_GUIDE.md` H2 vs the page it describes; every `ARCHITECTURE.md` session key vs producer/consumer `rg` | mismatch | Help corpus is built from these files; drift becomes wrong product help |

### 3.2 Application-quality checklists (applied per user-facing slice)

Each user-facing slice (QI-1…QI-10) answers these for every entry point in its scope — UI page, API function, CLI verb:

1. **Happy path** reproduces the documented outcome on `sample_data/` and the QI-0 synthetic fixtures.
2. **Empty / minimal input** (0 trades, 1 session, 1 signal) renders without exception and without misleading numbers.
3. **Malformed input** fails closed with an actionable message (no raw traceback in the UI, typed exception in the API).
4. **Stale-state** (upstream re-run, dataset switch, bundle import) invalidates or flags dependents exactly as `ARCHITECTURE.md` says.
5. **Composer parity** (UI vs API vs CLI vs Study vs Assistant) for the same specification — the audit's central lesson; reuse `tests/test_assistant_execution_parity.py` patterns.
6. **Honesty surface**: every number shown has a glossary entry; every diagnostic carries its caveat; no confirmatory language (`AUDIT_FINAL` H13 pattern).
7. **Persistence round-trip** (save → reload → identical hash) where the slice owns a store namespace.
8. **Performance envelope** on the "realistic" fixture (`tests/fixtures/cai_baseline.py`): wall time and peak RSS recorded, compared to `docs/SIMULATE_PERF.md` / `docs/CAI_BASELINE.md`.
9. **Operability**: can an operator tell *what ran* (identity hashes, provenance) and *why it stopped* (errors, skip reasons) without reading code?
10. **Accessibility of copy**: labels, captions, and help text are consistent across pages for the same concept (e.g. "Admit" vs "entry window" vs "cutoff").

### 3.3 Finding record schema (inherited from the archived WS plan, extended)

Every finding, in the report *and* in `findings.csv`:

| Field | Values |
|---|---|
| `id` | `QI-<slice>-<nn>` |
| `axis` | `code` / `app` / `both` |
| `classification` | Verified defect · Probable defect · Design limitation · Security risk · Documentation drift · **Maintainability risk** (new) · **Test-quality gap** (new) · **UX/operability gap** (new) · Unknown |
| `severity` | Critical / High / Medium / Low — criteria as WS §3 (research-honesty and workflow impact), plus for `code` axis: High = blocks safe change to an engine/analytics path; Medium = raises change cost measurably; Low = cosmetic |
| `confidence` | Verified (reproduced) / Strong (static + partial runtime) / Moderate / Speculative |
| `blast_radius` | list of composers/pages/CLI verbs affected |
| `iso25010` | characteristic(s) |
| `files_symbols` | paths + symbol names |
| `repro_or_reasoning` | exact commands / probe / static trace |
| `expected` / `observed` | |
| `impact` | financial / security / operational / maintenance |
| `regression_surface` | which tests, goldens, contracts would be touched by a fix |
| `remediation_direction` | one sentence, narrow; **never** an implementation |
| `tests_required_later` | |
| `docs_required_later` | living doc + section |
| `locked_by` | `AUDIT_FINAL §5.x` / `AH §2.n` / none |
| `handoff_to` | other slice IDs |
| `prior_id` | `C*/H*/M*/L*` from `AUDIT_FINAL`, or `W*` from `THESISTESTER_ANALYSIS`, if this re-verifies an old item |

### 3.4 Report skeleton (every `docs/quality/QI-<nn>_*.md`)

```
# QI-<nn> — <slice name>
Commit · environment · commands run (verbatim) · time spent
## 1. Scope actually covered (files) and anything skipped (why)
## 2. Code-quality readout (metrics table for this scope, then hot-spot reading notes)
## 3. Application-quality readout (checklist §3.2 per entry point)
## 4. Prior-audit carry-over status (items from §A.3 assigned to this slice)
## 5. Findings (table, §3.3 schema; full records in findings.csv)
## 6. Positive verification (what was checked and is fine — prevents re-audit)
## 7. Handoffs to other slices
## 8. Docs that would need amending in QR (list only)
```

---

## 4. QI-0 baseline — measured on `main @ e82c2a9` (2026-09-08), Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0

These numbers are the **starting line**. QR success is measured against them (§9.4).

### 4.1 Size and shape

| Dimension | Value |
|---|---|
| Library LOC (`thesistester/`) | 81,829 in 196 modules |
| Streamlit pages LOC (`pages/` + `app.py`) | 18,172 in 15 pages + entry |
| Test LOC / files / functions | 92,644 / 145 files (+ `tests/study`, `tests/visualization`, `tests/benchmarks`) / 3,715 `def test_` |
| Docs | 66 markdown files, 34,883 lines (`AGENT_GUIDE.md` ~750 lines; `ASSUMPTIONS_AND_LIMITATIONS.md` ~1,520 lines; `ARCHITECTURE.md` ~1,760 lines) |
| Commits | 1,875 |
| Largest modules | `assistant/results_overview.py` 4,373 · `api.py` 3,204 · `pages/14_Research_Assistant.py` 2,581 · `pages/15_Studies.py` 2,261 · `study/observatory.py` 2,069 · `assistant/orchestrator.py` 2,075 · `pages/1_Data.py` 1,983 · `pages/10_Validation.py` 1,949 · `pages/7_Backtest.py` 1,858 |
| Recent churn (top, last 400 commits) | `tests/study/test_study_observatory.py` 29 · `pages/15_Studies.py` 28 · `study/observatory.py` 26 · `pages/16_Study_Observatory.py` 20 · `study/schema.py` 19 · `api.py` 19 |

### 4.2 Static quality

| Metric | Value |
|---|---|
| `ruff check .` (R9 rule set `E4,E7,E9,F,W`) | clean |
| `ruff format --check .` | clean (367 files) |
| Cyclomatic complexity histogram (2,795 blocks) | A 1,775 · B 619 · C 293 · **D 60 · E 27 · F 21**; average 6.28 (B) |
| F-grade (CC ≥ 41) — engine/analytics/api | `reporting.build_markdown_report` **152** · `engine/backtest.simulate_trades` **133** · `engine/signals.generate_signals` **120** · `api.validate_run_spec` **104** · `research_bundle.load_research_bundle` 75 · `setup.validate_setup_config` 69 · `research_bundle.build_research_bundle` 63 · `engine/signals_3c.detect_3c_setups_with_trigger_timeframe` 59 · `signals_3c.detect_3c_setups` 55 · `api.run_validation` 51 · `analytics/walk_forward.run_walk_forward_sl_tp` 50 |
| F-grade — assistant/study/pages | `assistant/results_overview._format_scalar_for_claim` **120** · `results_overview.compose_deterministic_replies` 73 · `pages/15_Studies._draft_from_builder_widgets` 73 · `study/builder.hydrate_study_draft` 62 · `study/execute.run_study` 60 · `pages/15_Studies._render_build` 59 · `assistant/explainer._derive_caveats` 52 · `assistant/help_corpus.score_corpus_chunk` 51 · `pages/3_Setup_Builder._sync_editor_widget_state` 47 · `study/schema._validate_factors` 46 |
| Maintainability Index = **0.00** | `pages/1_Data.py`, `3_Setup_Builder.py`, `6_Signals.py`, `7_Backtest.py`, `10_Validation.py`, `14_Research_Assistant.py`, `15_Studies.py`, `16_Study_Observatory.py`, `analytics/confluence_attribution.py`; `pages/2_Levels.py` 7.24; `analytics/overfitting.py` 16.09 |
| Pages with ≤ 5 top-level functions (monolithic render) | `10_Validation.py` (1,949 lines, 4 defs) · `7_Backtest.py` (1,858 lines, 5 defs) · `8_Grid_Search.py` (801, 3) · `9_Time_Analysis.py` (719, 1) · `11_Report_Export.py` (386, 3) · `13_Portfolio.py` (122, 0) |
| `st.session_state` references in pages | 1,176 (Studies 235 · Data 170 · Validation 140 · Research Assistant 138) |
| Broad `except Exception` / bare `except` | 83 |
| `TODO/FIXME/XXX/HACK` | 8 |
| `# noqa` / `# type: ignore` | 36 |
| Return-annotated vs unannotated `def` in library | 1,588 vs 6 |
| Library modules importing Streamlit | 1 (`thesistester/app_state.py`) |
| Cross-module private-symbol imports | 10 |
| `vulture` candidates (≥ 60% / ≥ 80% confidence) | 110 / 2 (`assistant/voice/sidecar.py` unused `fp`, `newurl`) |

### 4.3 Test and tooling baseline

| Metric | Value |
|---|---|
| Full suite result | see §4.5 |
| **CI status on `main`** | **Red since 2026-09-05** (first red run: merge of [#440](https://github.com/AccumuLatata/ThesisTester/pull/440); last green: [#439](https://github.com/AccumuLatata/ThesisTester/pull/439) on 2026-08-30). All **37** subsequent merges through `e82c2a9` ([#476](https://github.com/AccumuLatata/ThesisTester/pull/476)) landed on a red `main`; the last 100 `main` runs are 61 success / 38 failure / 1 cancelled. `ruff`, editable-install, and golden-guard jobs pass; all three `pytest` matrix cells fail |
| Root cause of the red (verified in CI logs and reproduced locally) | `tests/test_assistant_page_render.py::test_disabled_discuss_chat_input_does_not_call_handle_results_turn` — Streamlit **1.63.0** `AppTest` now raises `AppTestError: Cannot update a disabled chat_input widget` on `set_value()`; the test's *intent* (handler must not run when disabled) is now enforced by the framework itself, so the test's mechanism is obsolete, not the product. `pyproject.toml` allows `streamlit>=1.56,<2`, so CI silently picked up the new minor |
| Second failure, py3.10 cell only (since at least `e82c2a9`) | `tests/test_journal_join.py::test_nullable_join_columns_stay_object_none — assert nan is None`. The py3.10 cell resolves **pandas 2.3.3** while py3.11/3.12 resolve **pandas 3.0.5** (pandas 3 requires ≥3.11): the matrix is a *pandas-major* split by accident, not by design, and nullable-object semantics differ |
| CI (`.github/workflows/ci.yml`) | ruff lint+format (blocking) · pytest 3.10/3.11/3.12 with coverage (coverage informational, floor 85%, R9 baseline 88%) · clean editable install + `pip check` · golden-regen label guard. **Whatever branch protection exists did not stop 37 merges on red**: e.g. [#476](https://github.com/AccumuLatata/ThesisTester/pull/476) merged with all three `pytest` checks `FAILURE`; [#450](https://github.com/AccumuLatata/ThesisTester/pull/450) merged with `pytest` ×3 **and** `ruff (lint + format)` `FAILURE` (required-status configuration is not visible from the checkout; QI-12 verifies it via repository settings) |
| CI test count / wall time (`e82c2a9`) | 3,966 collected (3,965 pass + 1 fail on py3.11/3.12; 3,963 + 2 fail on py3.10), 5–6 skipped; 4:55–8:08 min per cell |
| Type checker in CI | **none** (no mypy/pyright config anywhere) |
| Security scanning in CI | **none** (no bandit, pip-audit, CodeQL, dependabot/renovate) |
| Import-layer enforcement | **none** mechanical; boundaries live as prose in `AGENT_GUIDE.md` ("`viewer.py` must not import…", "`preview.py` must not import `execute`", etc.) |
| `pip-audit` on the dev VM | project dependencies clean; **environment-only** findings: `setuptools 68.1.2` (PYSEC-2025-49, PYSEC-2026-1918, PYSEC-2026-3447), `urllib3 2.6.3` (PYSEC-2026-141/142), `wheel 0.42.0` (CVE-2026-24049) — none are declared in `pyproject.toml`; QI-12 decides whether pins/caps are warranted |
| Devcontainer | pins Python **3.11** image, installs `requirements.txt` then `pip3 install --user streamlit` separately (drift vs `pyproject.toml`/CI) |
| Runtime limits | `.streamlit/config.toml` `maxMessageSize=400`, `maxUploadSize=350` — a documented transport cap for 15s frames, not a memory strategy |

### 4.4 What the baseline already tells us (hypotheses for the slices, not findings)

- **H-0 (verified, not a hypothesis). The regression-safety framework's CI gate (`ENGINEERING_PROPOSAL` §4 rule 9, "no merge on red") is not operating.** `main` has been red for a week and 37 PRs merged over it; since the failing tests are dependency-induced, the same `pytest` cells were red on those PR branches too, so the gate was visibly red and did not block. Two independent dependency-drift events (Streamlit minor, pandas major split across the matrix) went unnoticed because nothing blocks on red. This is exactly the `ENGINEERING_PROPOSAL` §7 "pandas/numpy major-version drift" risk, realized, plus its Streamlit sibling that the risk register did not list. → **Pre-QI action (§4.6)**, then QI-12 (controls), QI-11 (test mechanism), QI-13 (roadmap "CI green" claims).
- **H-A. The complexity is concentrated exactly where the audit found defects.** `simulate_trades` (133) and `generate_signals` (120) are the two most critical functions in the product and two of the four most complex. R22 isolated `engine.sim_core` but the orchestrating function did not shrink. → QI-4, QI-3, QI-14.
- **H-B. Pages are the under-tested half.** Nine pages have MI 0.00. Streamlit `AppTest` is used for exactly two pages (`tests/test_assistant_page_render.py` → page 14; `tests/study/test_study_observatory.py` → page 16); the thirteen classic/Studies/Journal pages are covered only via `*_page_helpers` unit tests of extracted helpers. The one `AppTest` suite is also the one that broke on the Streamlit minor bump (§4.3). → QI-10, QI-11.
- **H-C. Contracts are prose, not code.** Dozens of "X must not import Y" rules exist in `AGENT_GUIDE.md` with no `import-linter` contract; `app_state.py` already breaks the "library is Streamlit-free" rule. → QI-12, QI-6.
- **H-D. `api.py` is a second monolith.** 3,204 lines, `validate_run_spec` CC 104, 19 commits in the last 400. The facade meant to be "thin" is now the largest surface after the assistant. → QI-6.
- **H-E. Assistant code volume exceeds engine code volume** and has the single most complex function in the repo. Whether that is proportionate is a QR decision; QI-9 measures it. → QI-9.
- **H-F. Documentation is a maintainability cost.** 35k lines across 66 files, with `AGENT_GUIDE.md` acting as a growing rule ledger. → QI-13.

### 4.5 Full-suite run (recorded during QI-0)

See the appendix table §A.4 (filled from the measured run: total tests, pass/fail, wall time, coverage %, 25 slowest tests).

### 4.6 Pre-QI action: restore a green `main` (outside QI scope, required before QI-1…QI-14 start)

QI's guardrail 2 ("`pytest -q` identical before and after") is meaningless while `main` is red, and every slice would re-report the same two failures. Therefore, **before any slice starts**, one narrow hotfix PR (not a QI slice, not QR; it follows `ENGINEERING_PROPOSAL` §4.2 like any PR) should:

1. Rewrite `test_disabled_discuss_chat_input_does_not_call_handle_results_turn` so it asserts the disabled state and that `handle_results_turn` is not invoked *without* calling `set_value()` on a disabled widget (or asserts that `AppTestError` is raised on the attempt) — the RUX rendered-structure baseline rule says "rewrite (never delete) its assertions".
2. Make `test_nullable_join_columns_stay_object_none` explicit about pandas-major semantics (assert the *contract* — object dtype with `None`/NA-equivalent — in a way that holds on both 2.3 and 3.0), or, if the journal code is genuinely wrong on pandas 2.3, fix it (TJ5 contract: "nullable join columns stay object/None").
3. Record in `AGENT_GUIDE.md` §Development environment that CI resolves *latest* Streamlit/pandas within `pyproject.toml` caps, and that the py3.10 cell is the pandas-2 cell.

Deciding whether to pin/cap Streamlit minors, add a pandas-major axis to the matrix explicitly, or enable branch protection is **QI-12 → QR-G**; the hotfix only restores the gate's signal.

---

## 5. Slice map

Fifteen slices. **QI-0 first; QI-1…QI-14 are mutually independent and may run in parallel; QI-15 last.** Each slice is one agent-run and one PR that adds only its report(s) to `docs/quality/` and rows to `findings.csv`.

Legend for each slice: **Scope** (files owned) · **Why** · **Code-quality checks** (beyond §3.1 metrics) · **Application-quality checks** (beyond §3.2) · **Probes** (runtime experiments; all under `/tmp`) · **Carry-over** (items from §A.3) · **Do not** · **Exit criteria**.

---

### QI-0 — Baseline, tooling harness, evidence protocol

**Scope:** repo-wide read; the *only* slice allowed a code PR: `scripts/quality_metrics.py` (radon/vulture/rg counters → JSON), `docs/quality/README.md`, `docs/quality/findings.csv` header, synthetic fixture recipe notes. Tooling is **informational and non-blocking**; no CI job is added (that is QR).
**Why:** every later slice must measure the same way; §4 is the first output of this slice.
**Checks:** record commit, Python, dependency versions (`pip list`), OS; run §A.1 commands; run the full suite twice (determinism), with `--durations=25` and coverage XML kept under `/tmp`; produce per-module coverage table; generate the module → slice ownership map (every `.py` under `thesistester/`, `pages/`, `scripts/`, `examples/` assigned to exactly one slice).
**Probes:** `streamlit run app.py --server.headless true` boots and serves `/_stcore/health`; `python -m thesistester --help`, `study --help`, `journal --help` succeed.
**Do not:** interpret metrics as findings (hypotheses only, §4.4).
**Exit:** §4 tables filled; ownership map complete; `findings.csv` exists with header; report `QI-00_BASELINE.md` committed.

---

### QI-1 — Data ingestion, sessions, derivation, dataset persistence

**Scope:** `thesistester/data/` (`loader.py` incl. R17 vendor profiles, `derive.py`, `resample.py`, `rolls.py`, `sessions.py`, `quantower_ticks.py`), `thesistester/persistence/local_store.py` (dataset namespace), `pages/1_Data.py` (46 defs, 170 session refs), `config.py` instrument presets, `sample_data/`.
**Why:** first gate of every composer; `AUDIT_FINAL` H10/H11 still open; the 15s→1m derivation and tick attach are the newest and most operator-error-prone paths.
**Code-quality checks:** `pages/1_Data.py` MI 0.00 — decompose render tree into the extraction candidates; classify every broad `except` in the loader path; verify `format_profile` allow-list is a single source of truth (loader vs Studies builder `getattr` fallback rule in `AGENT_GUIDE.md` R17 section suggests duplication).
**Application-quality checks:** §3.2 for Upload CSV (canonical, each vendor profile, 15s-primary), Sample, saved dataset restore, tick attach, subtimeframe upload; DST-crossing aware timestamps on the canonical path (H11); duplicate 1m bars on legacy primary (H10); ETH/RTH tagging on holiday-shortened and early-close days; `trading_session_date` vs `session` semantics; roll metadata modes; store round-trip incl. `raw.parquet` sidecar and `ingestion_provenance` schema v1→v2.
**Probes:** synthetic CSVs for each vendor profile with one deliberate defect each (missing bar, duplicate, H<L, negative volume, mixed offsets, misaligned 15s bucket); compare UI vs `api.load_dataset` acceptance for each (composer parity).
**Carry-over:** H9 (`dataset_id` omits ingestion mode), H10, H11; W-items closed (W13 micros landed).
**Do not:** re-derive the `observed_aligned_15s_to_1m_v2` policy or the OHLC-identical duplicate resolution (AUDIT S1 locked).
**Exit:** parity matrix (input defect × composer × outcome) in report; every `pages/1_Data.py` function ≥ CC 21 classified.

---

### QI-2 — Levels engine and point-in-time surface

**Scope:** `thesistester/levels/` (`all.py` orchestrator, `common.py`, `session_date.py`, `sessions.py`, `indicators.py`, `pivots.py`, `session_vwap.py` incl. w/mVWAP, `tpo.py` single prints, `profile.py`, `apoc.py` + `apoc_candidates.py` + `apoc_tick.py`, `rolling_poc_candidates.py` + `rolling_poc_tick.py`, `tick_vap.py` + `tick_requirements.py`, `prev30m_vwap.py`, `defaults.py`, `catalog.py`), `visualization/levels_chart.py`, `pages/2_Levels.py`, `thesistester/persistence/local_store.py` (levels namespace), `docs/POINT_IN_TIME_GUARANTEES.md` as spec.
**Why:** PIT correctness is the product's core claim; the family count has doubled since the R3 audit; two settings planes (product defaults vs keyword defaults, H4) still exist.
**Code-quality checks:** per-family module shape consistency (does every family expose the same compute signature and identity stamping?); `_sync_levels_widget_state` (CC 39) and the Stage-6 widget/persistence sync; `LEVEL_ENGINE_VERSION`/identity-key discipline — is the "no version bump, identity stamps tick" rule mechanically enforced or convention?; dead/non-default bodies (`_rolling_poc` body is documented dead — is it the only one?).
**Application-quality checks:** future-shock property test *generated* for every emitted column (append N bars → earlier values byte-identical), not just the R3 named set — report which columns lack a future-shock test; tick-gated refusals (`APOC requires ticks`, `rolling POC requires ticks`) surface identically in UI/API/Study; Levels page stale-fingerprint logic vs `ARCHITECTURE.md`; catalog completeness (LC series) vs `USER_GUIDE.md`.
**Probes:** programmatic future-shock loop over all level columns on the golden fixture and on a DST-week fixture; H4 probe — same YAML with Advanced OFF vs sparse hand-written keys through `compute_levels`.
**Carry-over:** H4; `AUDIT_FINAL` §5.5 "PIT future-shock rows for `dOpen*` / `prevSettlement` / `pm` profile / `pw*`/`pm*`".
**Do not:** re-audit `trading_session_date` arithmetic, tick bin sizes (4/8/10), or QT-parity decisions (AP/RP locked).
**Exit:** column-level PIT coverage table (column × has-test × future-shock result); settings-plane map.

---

### QI-3 — Setup, confluence, signals, triggers, OTF

**Scope:** `thesistester/setup.py`, `thesistester/engine/signals.py`, `signals_3c.py`, `confluence.py`, `anchor_confluence.py`, `naked.py`, `candidate_level.py`, `otf.py`, `otf_filter.py`, `otf_integration.py`, `visualization/signals_chart.py` (`build_signals_chart` CC 29), `visualization/chart_window.py`, `pages/3_Setup_Builder.py` (23 defs, MI 0.00), `pages/6_Signals.py` (33 defs, MI 0.00), `docs/otf-filter.md` as spec.
**Why:** `generate_signals` CC 120 and both 3c detectors CC 55–59 are the least-decomposed engine functions; `validate_setup_config` CC 69 is the setup contract for five composers; H14 (stale developing-level projection on HTF triggers) is open.
**Code-quality checks:** trigger implementations (`touch`/`reject`/`break`/`reclaim`/`fade`/`3c`) — is there a common trigger protocol or five ad-hoc branches?; `confluence_mode` (`global_cluster` vs `anchor_rules`) code-path duplication; setup normalization vs validation vs API `build_setup` vs Studies expand `_build_setup_for_cell` (CC 25) — how many places normalize a setup?; `_sync_editor_widget_state` CC 47.
**Application-quality checks:** the DA0 lock (`touch`+`both`+`single_position` is long-only) is disclosed wherever `direction` is chosen; naked-level admission is zone-level (documented) — is it labelled so in UI?; Setup library CRUD round-trip; signals table columns vs `ARCHITECTURE.md` row contract; OTF is stored-not-applied on Signals page (verify copy says so).
**Probes:** HTF trigger with `dVWAP` partner — quantify level staleness (H14) on a synthetic drifting-VWAP fixture; composer parity for a setup with `min_valid_confluences: 0` (AO1) across UI/API/Study.
**Carry-over:** H14; §5.5 "whether `confirm_3bar` will be deleted" (is it still present? dead?).
**Do not:** edit or re-audit `_check_touch`, the candidate sort key, or 3c four-rule math (DA0 / AUDIT S3 locked).
**Exit:** trigger × composer parity table; setup-normalization call-site inventory.

---

### QI-4 — Execution engine: simulation, intrabar, exits, admission, metrics

**Scope:** `thesistester/engine/backtest.py` (`simulate_trades` CC 133), `engine/sim_core.py`, `engine/intrabar.py`, `engine/exit_management.py` (BE/trailing), `entry_window_policy.py` + `analytics/entry_window.py` (Admit half), `execution_defaults.py`, direction-collision policy, `analytics/metrics.py`, `visualization/backtest_chart.py` (`build_backtest_candlestick_chart` CC 34), `visualization/trade_review_chart.py`, `trade_review_export.py`, `pages/7_Backtest.py` (5 defs, 1,858 lines), `tests/fixtures/golden/`.
**Why:** highest-value code path; every audit Critical touched it; R22's "narrow the core surface" landed but the orchestrator remains F-grade; goldens gate *legacy* only.
**Code-quality checks:** map `simulate_trades` into its phases (candidate admission → entry → exit walk → P&L → schema → diagnostics) and measure how much of CC 133 belongs to each; identify state carried across loop iterations (the C1 leak class); verify `sim_core` boundary (does any admission/P&L logic live in `sim_core`, violating R22's rule?); exit-reason vocabulary — enumerated or stringly-typed?; trade-schema additive-column discipline — is there a single schema definition?
**Application-quality checks:** §3.2 for Backtest page incl. skip table, Focus overlay, Admit banner, combo attribution expander, trade-review chart (R20 bounded payload), worst-loser export; `allow_all` overlap disclosure at the widget (H5); cutoff-without-flatten UI vs API (H7); OTF timezone UI vs API (H15); `sl_first` × 3c after AH5 — is the AH5 probe a committed test?
**Probes:** phase-timing instrumentation of `simulate_trades` (in `/tmp` copy) on the realistic fixture; H5 two-candidate overlap fixture through UI helper vs `api.run_backtest`; H7/H15 composer parity YAML vs page widgets.
**Carry-over:** H5, H7, H15; W12 (performance profile — hand to QI-14 for measurement, QI-4 for structure).
**Do not:** change or re-record goldens; question `sl_first` default, calendar-date flatten, or `allow_all` default (AH §2.1 locked).
**Exit:** `simulate_trades` phase map with CC per phase; execution parity table (H5/H7/H15 status).

---

### QI-5 — Analytics and validation batteries

**Scope:** `thesistester/analytics/` except `metrics.py`/`entry_window.py` Admit half: `grid.py`, `walk_forward.py` (CC 50), `validation.py`, `monte_carlo.py`, `overfitting.py` (MI 16), `noise.py`, `sensitivity.py`, `excursions.py`, `portfolio.py`, `time_analysis.py`, `otf_validation.py`, `confluence_attribution.py` (MI 0.00), `prev30m_vwap_hit.py`; pages `8_Grid_Search.py`, `9_Time_Analysis.py`, `10_Validation.py` (1,949 lines, 4 defs), `13_Portfolio.py`; `docs/METRICS_GLOSSARY.md` as spec.
**Why:** the batteries multiply engine load and are the "statistical theater" risk (`ENGINEERING_PROPOSAL` §7); `pages/10_Validation.py` is the least-decomposed page; H12/H13 open.
**Code-quality checks:** seeding discipline (`random_state` threaded everywhere? any `np.random.default_rng()` without seed?); result-dict schema versioning consistency across R10/R11/R14/R15/R16/R19/R21 (`schema_version` key present, checked on load?); duplicated "empty-trade safe" scaffolding across modules; `run_walk_forward_sl_tp` decomposition; `confluence_attribution.py` MI 0.00.
**Application-quality checks:** every metric on pages 8/9/10/13 has a `METRICS_GLOSSARY.md` entry (generate the list mechanically); confirmatory language scan (`st.success` on p-values, "significant", "proven") — H13; Focus vs Admit count over-statement under `single_position` (H12); WFA matrix "best cell" disclosure; battery cost warnings present where opt-in toggles exist; Portfolio page (0 defs, 122 lines) — feature completeness vs R21 scope.
**Probes:** run every battery on the golden fixture with two seeds and confirm seed-determinism and seed-sensitivity; H12 fixture (`single_position`, out-of-window blocker); glossary coverage script.
**Carry-over:** H12, H13, H16 (Study ranking ignores WFA OOS — shared with QI-7).
**Do not:** re-open fold construction or `causal_prefix` semantics (AUDIT S5 locked); alter `validation_summary()` shape.
**Exit:** metric × glossary × caveat coverage table; seed-discipline inventory.

---

### QI-6 — Headless facade, CLI, identity, bundles, reporting, classic bridge

**Scope:** `thesistester/api.py` (3,204 lines), `cli.py`, `__main__.py`, `research_identity.py`, `research_bundle.py` (`load_research_bundle` CC 75, `build_research_bundle` CC 63), `reporting.py` (`build_markdown_report` CC 152), `classic_*.py` (context, export, nav, proposal, record, ledger), `persistence/execution_artifacts.py` (1,519 lines), `app_state.py`, pages `11_Report_Export.py`, `12_Research_Bundles.py`.
**Why:** this is *Composer B* plus the bridge to Composer A. It has the highest cross-cutting coupling and the "thin facade" has become the second-largest module. Bundles are the untrusted-input boundary.
**Code-quality checks:** `api.py` responsibility map (facade vs validation vs composition vs persistence vs assistant helpers) — how much is actually facade?; `validate_run_spec` CC 104 — is it a hand-rolled schema? would a declarative schema (dataclass/pydantic-free, e.g. `TypedDict` + one validator table) reduce it without behavior change?; `build_markdown_report` CC 152 — template vs code; bundle key lists (`_MANAGED_RESEARCH_KEYS`, `_BACKTEST_META_KEYS`, hashed `session_keys`) — single source of truth or parallel lists (H1 class)?; `app_state.py` Streamlit import in the library — what depends on it?
**Application-quality checks:** CLI ergonomics (`--help` completeness, exit codes, error messages without tracebacks); `results_index.csv` schema stability; bundle import of *malicious* zips (path traversal, zip bomb size, foreign parquet schema, missing manifest, tampered hash) — fail closed?; page-12 schema-only import vs assistant hash-gated open (AH §2 item 8 locked — verify the three integrity bars are *labelled* distinctly); report markdown vs UI numbers for the same session (identity parity); `canonical_bundle_hash` stability across pandas 2.2 / 3.0 (CI matrix installs latest — does the hash differ by pandas major as the golden README warns?).
**Probes:** adversarial zip set under `/tmp`; CLI run of `examples/studies/pRTH_open_ma.yaml`-derived experiment on the golden fixture, compare `canonical_bundle_hash` with `api.run_experiment` and the UI-equivalent session (existing parity tests as template); pandas-major hash check across two venvs.
**Carry-over:** H1 (residual leftover keys after AH4), H8 (battery `enabled` default-on for raw YAML/assistant `_bounded_spec` — **locked as parked**, verify disclosure only), §5.5 "page 12 hash parked".
**Do not:** propose collapsing composers or the three integrity bars (AH §2 items 1, 2, 8).
**Exit:** `api.py` responsibility map with line share per responsibility; bundle threat-model table with outcomes.

---

### QI-7 — Study system (Runner, Builder, Viewer, Observatory, Admit follow-up, Program A/B packets)

**Scope:** `thesistester/study/` (`schema.py` 973 — `_validate_factors` CC 46; `expand.py`; `execute.py` 1,353 — `run_study` CC 60; `report.py`; `promote.py` — `_compose_promoted_draft` CC 37; `rollup.py`; `viewer.py` 1,174; `observatory.py` 2,069; `builder.py` 1,386 — `hydrate_study_draft` CC 62; `launch.py` 691; `briefing.py`; `admit_followup.py`; `cli_study.py`; `tools.py`), `pages/15_Studies.py` (2,261 lines, 42 defs, 235 session refs), `pages/16_Study_Observatory.py` (966), `examples/studies/**` incl. Program B generator/validator scripts, `docs/STUDY_RUNNER.md` as operator spec, `tests/study/`, `tests/fixtures/study/golden`.
**Why:** highest churn subsystem in the last 400 commits; has its own ledger/resume/subprocess-spawn/pid-claim machinery (operational risk surface); many prose-only import bans (`viewer` ∌ `execute`, `observatory` ∌ Streamlit, `preview` ∌ `execute`).
**Code-quality checks:** mechanically verify every import ban listed in `AGENT_GUIDE.md` §Study (build the import graph with `grimp`/`import-linter` in `/tmp`); schema validation approach (hand-rolled, 973 lines) vs the same problem solved in `api.validate_run_spec` — duplication of the RunSpec validator?; `pages/15_Studies.py` — Build/Inspect/Preview/Launch tabs as four pages fused into one (decomposition candidates, session-key namespaces `studies_*`/`_study_builder_*`/`observatory_*`); `launch.py` cross-platform subprocess/pid code — test coverage on non-Windows for the Windows branches (or vice versa).
**Application-quality checks:** end-to-end `study expand → run → report → promote → observatory` on a 4-cell synthetic study under `/tmp` store; ledger soft-resume after a killed cell; failed-cell honesty in MD/rollup (H16); `experiment.yaml` replay disclosure after AH2 (pinned bytes) — does the emitted YAML say it is *not* `study run`?; Observatory read-only guarantees (never writes `results/studies/`); Builder Advanced-OFF emits explicit `enabled: false` (AH7 parked — verify current state only); Program B `manifest.yaml` / `manifest_tick.yaml` validator scripts run clean.
**Probes:** import-graph contract check; kill-and-resume run; 15s Quantower fixture without `ingestion_mode` (the "different experiment" trap in `AGENT_GUIDE.md`) — is it caught at validate time?
**Carry-over:** H2 (promote pin roots after AH), H16, W11 (closed by R18/RS — record).
**Do not:** propose in-process `run_study()` from pages, auto-refresh, kill/retry, or a ToD factor axis (RS-D2/SAF locked).
**Exit:** import-contract verification table; Study lifecycle E2E evidence; `pages/15_Studies.py` decomposition map.

---

### QI-8 — Trade journal and journal → study

**Scope:** `thesistester/journal/` (`schema.py`, `tradesviz`/AMP loaders, `pair.py`, `reconcile.py`, `join.py` — `_join_trade` CC 33, `levels.py`, `zones.py`, `match.py` — `load_named_cell` CC 35, `counterfactual.py`, `rules.py`, `report.py` — `_q4_q6` CC 36, `cli.py`, `tag_map.yaml`), `pages/17_Journal.py`, `examples/journal/`, `tests/fixtures/journal`.
**Why:** newest subsystem (TJ1–TJ9, JS1–JS2), touches real broker data (PII/fee correctness), PDF parsing (`pdfplumber`), and its own `r_multiple` formulas that must *not* copy the 1-lot engine formulas.
**Code-quality checks:** module boundary rule "journal never calls `simulate_trades`/`compute_all_levels`" verified by import graph; qty-scaled P&L formula has a single home; PDF parser robustness (malformed statement → typed error); `tag_map.yaml` closed set enforcement.
**Application-quality checks:** synthetic TradesViz + AMP fixtures through `journal ingest → reconcile → report`; day-boundary semantics (`trading_session_date`, `eth_start=18:00`) on a Sunday-open fixture; n<30 hiding toggle; JS1/JS2 zones/triggers inference disclosed as inference; store namespace `journal/v1/` isolation; no PII in any committed fixture or example (scan).
**Carry-over:** none from `AUDIT_FINAL` (post-dates it).
**Do not:** implement JS3+, unpark the Quantower Trades loader, or treat tags as triggers (TJ6 locked).
**Exit:** journal E2E evidence; formula-home inventory; PII scan result.

---

### QI-9 — AI Research Assistant and voice

**Scope:** `thesistester/assistant/` (`results_overview.py` 4,373, `orchestrator.py` 2,075, `repository.py`, `workspace.py`, `explainer.py`, `llm.py`, `llm_explainer.py`, `registry.py`, `handlers.py`, `tools.py`, `results_qa.py`, `results_projections.py`, `help_corpus.py`, `product_help.py`, `page_summaries.py`, `ux.py`, `voice/` incl. `sidecar.py`, `xai_realtime.py`, `session.py`), `pages/14_Research_Assistant.py` (2,581), `config/assistant.toml`, `docs/VOICE_SIDECAR_OPS.md`.
**Why:** largest subsystem by LOC; the trust boundary to external LLM providers; many completed contracts (AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX) whose *combined* invariants are only enforced by eval suites.
**Code-quality checks:** `results_overview.py` at 4,373 lines with `_format_scalar_for_claim` CC 120 — what are its responsibilities and could they be tabulated?; registry/handler/capability triple consistency check is a test (`test_assistant_registry_audit.py`) — is it complete for every capability ID?; provider abstraction (OpenAI Responses + xAI realtime) — is provider-specific code isolated?; `sidecar.py` unused variables (vulture 100%); thread/async safety in the voice session.
**Application-quality checks:** fail-closed paths without a key (UI copy, no traceback); secret handling (env → Streamlit secrets → nested TOML; quote/BOM stripping; placeholder rejection; sanitized errors) — add negative probes; prompt-injection and uncited-number evals (`test_assistant_llm_evaluations.py`, `test_assistant_voice_evaluations.py`) — corpus size and coverage of channels (draft/results/help/voice); Help corpus allowlist vs `docs/README.md` maintenance rule 2 (paths frozen) — mechanical check; chat-first UX rendered-structure baseline (`test_assistant_page_render.py`) still matches the page; default-off flags (`study_tools`, `voice`) in tracked TOML.
**Probes:** run evaluation suites; offline "provider stub" run of each channel; static scan for any `st.*` call inside `thesistester/assistant/` (presentation-only rule).
**Carry-over:** §5.5 residual "caller-controlled audit payloads".
**Do not:** propose provider swaps, layout changes (RUX), or reopening any completed assistant series.
**Exit:** capability × handler × test coverage matrix; secret-handling negative-probe table; `results_overview.py` responsibility map.

---

### QI-10 — Streamlit UI layer and `st.session_state` contract

**Scope:** `app.py`, all `pages/*.py` **as a system** (individual page internals are owned by QI-1…QI-9; this slice owns cross-page behavior), `thesistester/app_state.py`, `classic_nav.py`, `timezone_display.py`, `.streamlit/config.toml`, `docs/ARCHITECTURE.md` §"`st.session_state` contract" as spec, `docs/USER_GUIDE.md` as spec.
**Why:** 1,176 `st.session_state` references, one prose contract table, `AppTest` coverage for only two of fifteen pages (14 and 16); the audit's restore-leftover class (H1) is a UI-state-lifecycle problem.
**Code-quality checks:** build the *actual* key graph (producer page → key → consumer page) with `rg` + AST and diff it against the `ARCHITECTURE.md` table (missing keys, orphan keys, undocumented consumers); inventory of invalidation helpers (`_set_active_dataset_state`, nonce bumps, `THESIS_SCOPED_STAGING_KEYS`, bundle apply clears) — one mechanism or several?; widget-key vs research-key naming convention adherence; per-page rerun cost (time to first render with a loaded session) — hand numbers to QI-14; `E402` per-file ignore for pages (`sys.path` bootstrap) — is `pip install -e .` making it unnecessary?
**Application-quality checks:** cross-page stale-state matrix: for each mutation (load data, recompute levels, change setup, regenerate signals, re-backtest, import bundle, switch ingestion mode, switch dataset) × each downstream page → expected invalidation per `ARCHITECTURE.md` vs observed; error surfacing consistency (which pages show tracebacks?); copy consistency for shared concepts (Focus/Admit/cutoff/flatten/OTF; "diagnostic, not proof" caveat presence per page); first-run experience (`app.py` → Data → sample → full loop) timed; `MessageSizeError` path with a >400 MB 15s frame — documented, but is the failure legible?
**Probes:** Streamlit `AppTest` feasibility spike in `/tmp` for two *classic* pages (Data, Backtest), modelled on the existing page-14/16 harnesses — can classic pages be driven under `AppTest` given the `sys.path` bootstrap and the classic `session_state` bus? Record blockers and the per-page render time under `AppTest`; this decides QR-D's UI-test strategy. Also record how the existing `AppTest` suite failed on the Streamlit 1.63 bump (§4.3) as input to the harness design (assert *state*, not *interaction with disabled widgets*).
**Carry-over:** H1 residual (leftover keys), W15 (page numbering gap 4/5 — cosmetic, still present: pages 1,2,3,6…17).
**Do not:** propose layout changes for the Research Assistant page (RUX locked) or hydrating classic state from Studies/Observatory/Journal pages.
**Exit:** key graph diff; stale-state matrix; `AppTest` feasibility verdict.

---

### QI-11 — Test-suite quality

**Scope:** `tests/**` (145 files + `study/`, `visualization/`, `benchmarks/`, `fixtures/`), `pyproject.toml [tool.pytest]`, `[tool.coverage]`, `tests/fixtures/golden/README.md`.
**Why:** 3,715 tests are the regression-safety framework's load-bearing wall; nobody has measured whether they *assert* what they *cover*.
**Checks:** dependency-sensitivity of tests — which tests assert framework *mechanics* (e.g. interacting with a disabled `AppTest` widget) or library-version-specific null semantics rather than product contracts (the two §4.3 failures are the seed list; find the rest by grepping for `proto.`, `set_value`, `is None` on pandas scalars, `dtype == object`); per-module coverage from QI-0 → list of library modules < 70% and public functions with zero direct tests; **mutation sample** (§3.1) on four engine/analytics files; test-smell scan — assertion-free tests, `assert True`, tests asserting on `str(exc)` only, duplicated fixture builders across files (the audit noted "named suites police the contracts they encode"), overspecified snapshot tests that would break on any legitimate change; determinism (two runs, varied `PYTHONHASHSEED`, `-p no:cacheprovider`); slowest 25 and per-file wall time — which are integration tests masquerading as unit tests; golden fixture set — do the three golden families (`test_golden_master`, `test_otf_golden`, `test_entry_window_golden`, `test_fade_golden`) cover every default-on execution path?; eval suites (assistant/voice) — are they deterministic offline?; benchmark tests — informational vs asserting.
**Probes:** `mutmut run --paths-to-mutate thesistester/engine/backtest.py` etc. with the relevant test files only; a deliberately wrong one-line change in `metrics.py` (in `/tmp` copy) to confirm the suite catches it.
**Carry-over:** `AUDIT_FINAL` §7 last row ("goldens are identity, not correctness") — restate, do not re-litigate.
**Do not:** edit tests or fixtures.
**Exit:** module × coverage × mutation × test-count table; test-smell inventory; suite-structure recommendation input for QR (e.g. markers `unit`/`integration`/`golden`/`eval`, parallelization with `pytest-xdist` feasibility).

---

### QI-12 — Tooling, dependencies, CI, packaging, security and supply chain

**Scope:** `pyproject.toml`, `requirements.txt`, `.github/workflows/ci.yml`, `.devcontainer/`, `.streamlit/`, `.env.example`, `scripts/set_store_dir.ps1`, `LICENSE`, `README.md` install/run sections, `config/assistant.toml`, gitignore of `config/assistant.voice.override.toml`, secret paths in `assistant/llm.py`.
**Why:** R9 intentionally kept lint narrow and coverage non-blocking; no type checker, no security scan, no import-layer enforcement, no dependency update automation — every one of these is a standard SOTA control the repo lacks.
**Checks:** **branch-protection reality** (37 merges on red, §4.3 — which required checks are configured, if any; is `pytest (py3.x)` a required status?); dependency-drift exposure (`streamlit>=1.56,<2` admitted the 1.63 `AppTest` change; the matrix is a pandas 2.3/3.0 split by Python-version accident) — enumerate every dependency whose *minor* can change test behavior and whether a cap, a lockfile, or an explicit matrix axis is the right control; `mypy --strict` and `pyright` error counts on `engine/`, `analytics/`, `api.py`, `data/`, `levels/` (read-only run, results only); `bandit -r thesistester -ll`; `pip-audit` restricted to declared deps; dependency range sanity (`pandas<4` allows 3.x — CI installs pandas 3.0.5 on py3.11/3.12 and 2.3.3 on py3.10 while the golden README warns the bundle hash is pandas-major dependent: is the matrix testing both majors *deliberately*?); `kaleido>=1.3.0` uncapped; `requirements.txt` vs `pyproject.toml` drift (`pytest` in `requirements.txt` — app users install the test runner); devcontainer Python 3.11 vs CI 3.10–3.12 vs README; `ruff` rule-set widening candidates (which rule families would fire, count per family — `B`, `UP`, `SIM`, `PL`, `N`, `I`, `C90`); import-linter contract draft (in `/tmp`) encoding every `AGENT_GUIDE.md` import ban — number of violations today; GitHub branch protection expectations vs CI job names; reproducibility (no lockfile — `pip list` in CI is the only record).
**Probes:** the type-check and bandit runs; a `constraints.txt` resolution to see whether a lockfile is trivially derivable.
**Carry-over:** W1–W3, W14 (closed by R9 — record; **W1 "no CI" is closed but its intent "regressions cannot merge silently" is not**, per §4.3); `ENGINEERING_PROPOSAL` §7 "pandas/numpy drift" risk row (realized; Streamlit sibling missing from the register).
**Do not:** change any config.
**Exit:** control gap table (control · present? · cost to add · what it would have caught, citing a past PR/finding where possible).

---

### QI-13 — Documentation, contracts, and drift

**Scope:** `docs/**` (66 files), root `README.md`, `.cursor/rules/thesistester.mdc`, docstrings of public API (`api.py` facade, CLI help text).
**Why:** 35k lines of docs are both the product's honesty surface (Help corpus) and its change-control system (contracts). Unmeasured drift here silently degrades both.
**Checks:** doc inventory with role (living / contract-complete / archive / research) vs `docs/README.md` index — orphans, mis-shelved, duplicates; `AGENT_GUIDE.md` structure — rule ledger growth (count of "do not" sentences per section; which belong in `import-linter`/tests instead of prose); `ASSUMPTIONS_AND_LIMITATIONS.md` — every section still true? (sample verification against code for 15 claims); `ARCHITECTURE.md` session-key table vs QI-10's measured graph; `USER_GUIDE.md` H2s vs actual pages/widgets (Help corpus correctness); `METRICS_GLOSSARY.md` vs QI-5's metric inventory; `ENGINEERING_ROADMAP.md` status table vs reality (any "landed" claim without a merged PR?); broken intra-doc links; contract-doc "Files allowed to touch" lists that reference renamed/removed files; README install instructions reproduce on a clean venv.
**Probes:** link checker; H2 extractor vs page-title extractor; `docs/README.md` maintenance rules compliance script.
**Carry-over:** `AUDIT_FINAL` §5.5 "AGENT_GUIDE L38–39 advertising replay" (verify amended after AH2).
**Do not:** move Help-allowlisted files (maintenance rule 2), edit any doc.
**Exit:** doc inventory with role/owner/last-verified; drift table (claim · location · status); AGENT_GUIDE prose-rule → mechanizable-rule mapping.

---

### QI-14 — Performance, scalability, and resource envelope

**Scope:** cross-cutting measurement of `compute_levels`, `generate_signals`, `simulate_trades`, `run_sl_tp_grid`, WFA, batteries, Study cell execution, Observatory load, page rerun cost; `docs/SIMULATE_PERF.md`, `docs/CAI_BASELINE.md`, `tests/benchmarks/`.
**Why:** `CAI_BASELINE.md` already shows `compute_levels` dominating cold path; batteries and Studies multiply the engine loop; 15s frames hit the Streamlit transport cap; none of this is tracked over time.
**Checks:** re-run `tests/benchmarks/` scenarios and the CAI harness; profile (`cProfile` + `py-spy` if available) the realistic fixture end-to-end and per stage; memory (peak RSS, DataFrame copies — `.copy()` count on hot paths, dtype hygiene such as object columns for timestamps/strings, category candidates); Streamlit page rerun cost with a loaded 15s session; Study parallel `--workers` scaling (1/2/4) and its determinism; Observatory load time vs corpus size; algorithmic complexity notes per hot function (O(signals × bars_held) etc.) versus vectorization feasibility *without* changing outputs (R22 rule).
**Probes:** flame graphs to `/tmp`; a 3-month synthetic 1m + 15s dataset generator for scaling curves.
**Carry-over:** W12; R22 acceptance ("any acceleration must equal serial goldens").
**Do not:** implement optimizations.
**Exit:** stage-level timing/memory table on small/realistic/3-month fixtures; ranked hot-spot list with feasibility notes; drift vs `SIMULATE_PERF.md`/`CAI_BASELINE.md`.

---

### QI-15 — Cross-slice synthesis and remediation-program handoff

**Scope:** `docs/quality/QI-01…QI-14` reports and `findings.csv`.
**Procedure:** §7. **Output:** `docs/quality/QI-15_SYNTHESIS.md` and a draft `docs/QUALITY_REMEDIATION_PLAN.md` following §9.
**Exit:** every finding has exactly one owner workstream in the QR plan or an explicit `won't fix / locked` disposition; the CTO review gate (§7.5) is passed.

---

## 6. Slice dependency and parallelization

```text
§4.6 hotfix (green main)  ── precondition, not a slice
 └──► QI-0 (baseline + harness + ownership map)
 ├──► QI-1  Data            ─┐
 ├──► QI-2  Levels           │
 ├──► QI-3  Setup/Signals    │
 ├──► QI-4  Execution        │
 ├──► QI-5  Analytics        │  independent — run in parallel,
 ├──► QI-6  API/Bundles      │  one agent + one PR each
 ├──► QI-7  Study            │
 ├──► QI-8  Journal          │
 ├──► QI-9  Assistant/Voice  │
 ├──► QI-10 UI/session_state │  (consumes QI-0 ownership map only)
 ├──► QI-11 Tests            │
 ├──► QI-12 Tooling/CI/Sec   │
 ├──► QI-13 Docs             │
 └──► QI-14 Performance     ─┘
          └──► QI-15 Synthesis ──► QR plan (separate document, separate approval)
```

Recommended batching if agent capacity is limited: **Wave A** QI-4, QI-3, QI-6, QI-11 (engine-adjacent, highest information value); **Wave B** QI-1, QI-2, QI-5, QI-10, QI-12; **Wave C** QI-7, QI-8, QI-9, QI-13, QI-14. Handoffs between slices are written into reports, not resolved live.

---

## 7. Synthesis protocol (QI-15)

### 7.1 Finding registry

`docs/quality/findings.csv` columns = §3.3 fields, one row per finding, UTF-8, quoted. Each slice appends only rows with its own `id` prefix. QI-15 never edits slice rows; it adds `merge_group`, `score`, `qr_workstream`, `disposition` columns.

### 7.2 Deduplication and merging rules

1. Same `files_symbols` root cause reported by two slices → one `merge_group`; keep both IDs, the higher severity, and the union of `blast_radius`.
2. A `code` finding and an `app` finding with a causal link (e.g. CC 133 orchestrator ↔ leaked loop variable class) → linked, not merged; the link is the most valuable output of the synthesis.
3. Prior-audit carry-overs: a re-verified open item keeps its `prior_id`; if closed, the row's `disposition=closed-verified` with the AH PR reference.

### 7.3 Scoring model

`score = severity_weight × confidence_weight × blast_radius_count × (1 / fix_cost_class)` with severity weights Critical 8 / High 4 / Medium 2 / Low 1; confidence Verified 1.0 / Strong 0.8 / Moderate 0.5 / Speculative 0.2; blast radius = number of distinct composers/pages/CLI verbs (min 1); fix-cost class 1 (isolated, additive) / 2 (one module, golden-gated) / 3 (cross-module or contract amendment) / 4 (architecture). The score orders the backlog; it does not override the sequencing rule in §9.2 (honesty and safety net first).

### 7.4 Views the synthesis must produce

1. **Heatmap** module-group × ISO 25010 characteristic (count and max severity).
2. **Hot-spot matrix** for the top 30 functions by CC: CC · MI of module · churn · coverage · mutation score (if sampled) · finding count. This is the refactor priority list.
3. **Composer-parity ledger**: every UI/API/CLI/Study/Assistant divergence found, with `locked_by` where applicable.
4. **Contract-mechanization list**: every prose rule (from QI-13 and `AGENT_GUIDE.md`) that can become an `import-linter` contract, a test, or a type — with the count of violations today.
5. **Control-gap table** from QI-12 with the finding IDs each missing control would have caught.
6. **Architecture drift assessment**: measured boundaries vs `ARCHITECTURE.md` boundaries (R9 packaging, R18 headless, R22 sim_core, RS study, TJ journal, assistant presentation-only), with a verdict per boundary: *holds* / *eroding* / *breached*.
7. **Positive-verification register**: everything confirmed fine, so QR does not re-audit it.

### 7.5 Review gate

QI-15 is signed when: (a) all fourteen slice reports exist and each has a `Positive verification` section; (b) `findings.csv` parses and every row has `disposition ∈ {open, closed-verified, locked, wont-fix, duplicate}`; (c) the CTO review (regression and architecture drift first, per repo rules) has classified every `High`+ finding as accepted/deferred/rejected with a one-line reason; (d) the draft QR plan cites finding IDs for every workstream.

---

## 8. Execution model for agents

### 8.1 Branch, PR, and file conventions

- One branch per slice: `cursor/qi-<nn>-<slug>-<hash>`; one PR per slice titled `QI-<nn>: <slice name> (research-only)`.
- PR body must include: commit audited, commands run, finding count by severity, `Positive verification` summary, and the sentence "No tracked file outside `docs/quality/` changed; `pytest -q` unchanged."
- Reports are Markdown under `docs/quality/`; probe scripts are pasted as fenced blocks in the report, never committed.

### 8.2 Slice prompt template (copy-paste for sub-agents)

```markdown
You are auditing ThesisTester (intraday futures backtesting workbench) for code quality and application quality.
Slice: QI-<nn> — <slice name>. Plan: docs/QUALITY_INVESTIGATION_PLAN.md (read §2, §3, §5 QI-<nn>, §A.1–A.3 first).
Baseline: docs/quality/QI-00_BASELINE.md. Prior audit: AUDIT_FINAL.md on origin/cursor/audit-final-merge-3a8e (§5 is LOCKED — treat as premises, never re-audit), docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md §2 (LOCKED).

Hard rules (regression-safe, drift-safe, docs-maintained):
1. Research only. You may create exactly: docs/quality/QI-<nn>_<slug>.md and append rows to docs/quality/findings.csv. Do not edit, create, delete, or reformat any other tracked file. Probe scripts live under /tmp and are pasted into the report.
2. Before and after your work run `pytest -q` and confirm identical results; run `git status --porcelain` and confirm only your two files changed.
3. Stay inside the Scope file list for QI-<nn>. Adjacent observations go to the report's "Handoffs" section with the target slice ID.
4. Every finding uses the §3.3 record schema (ID QI-<nn>-<seq>, axis, classification, severity, confidence, blast radius, ISO 25010, files+symbols without line numbers, exact repro commands + output, expected/observed, impact, regression surface, one-sentence remediation direction, tests and docs required later, locked_by, handoff, prior_id). No evidence → not a finding (record as Unknown).
5. Apply the §3.1 metric triggers and the §3.2 application checklist to every entry point in scope; apply the slice-specific checks and probes in §5 QI-<nn>; re-verify only the *status* of the §A.3 carry-over items assigned to this slice.
6. Use a throwaway THESISTESTER_STORE_DIR under /tmp for anything touching persistence. Never use real API keys or real desk data.
7. Write the "Positive verification" section: what you checked that is fine, so nobody re-audits it.
8. Name, for every finding, the living doc that QR would need to amend (ASSUMPTIONS_AND_LIMITATIONS / ARCHITECTURE / USER_GUIDE / AGENT_GUIDE / METRICS_GLOSSARY / contract doc). Do not amend it now.
9. Never describe a backtest, metric, or Study result as correct or reliable unless you verified data, execution, P&L, session, and bias controls on that path.
10. Commit on branch cursor/qi-<nn>-<slug>-<hash>, push, open a draft PR titled "QI-<nn>: <slice name> (research-only)" with the PR-body items from plan §8.1.

Deliver: the report following plan §3.4, the CSV rows, and a 10-line summary (finding counts by severity, top 3 findings, top 3 positive verifications, handoffs).
```

### 8.3 Status tracker

| Slice | Status | Owner | PR | Findings (C/H/M/L) |
|---|---|---|---|---|
| QI-0 Baseline | **Measured (§4); harness PR not started** | — | — | — |
| QI-1 Data | Not started | — | — | — |
| QI-2 Levels | Not started | — | — | — |
| QI-3 Setup/Signals | Not started | — | — | — |
| QI-4 Execution | Not started | — | — | — |
| QI-5 Analytics | Not started | — | — | — |
| QI-6 API/Bundles | Not started | — | — | — |
| QI-7 Study | Not started | — | — | — |
| QI-8 Journal | Not started | — | — | — |
| QI-9 Assistant/Voice | Not started | — | — | — |
| QI-10 UI/session_state | Not started | — | — | — |
| QI-11 Tests | Not started | — | — | — |
| QI-12 Tooling/CI/Security | Not started | — | — | — |
| QI-13 Docs | Not started | — | — | — |
| QI-14 Performance | Not started | — | — | — |
| QI-15 Synthesis | Not started | — | — | — |

Status vocabulary (from the archived WS plan): `Not started` · `In progress` · `Blocked` · `Completed` · `Needs follow-up`.

---

## 9. From findings to the improvement program (QR series template)

QI-15 drafts `docs/QUALITY_REMEDIATION_PLAN.md` using this template. **Nothing in this section is authorized work until that plan is approved.**

### 9.1 Workstreams (fixed skeleton; contents come from findings)

| QR workstream | Fed by | Typical content | Regression-safety shape |
|---|---|---|---|
| **QR-A Honesty and correctness fixes** | `app` findings, Critical/High, carry-over H-items | Composer-parity fixes, disclosure copy, fail-closed gaps | One PR per finding; probe test red→green; §4.2 checklist; no golden regen unless a dedicated `GOLDEN_REGEN` PR with CSV diff |
| **QR-B Safety net before refactor** | QI-11, QI-12 | Golden coverage for default-on paths not yet golden-gated; mutation-score baseline committed; `import-linter` contracts from the mechanization list (initially *warn*, then *block*); type-checker on `engine/`+`analytics/` (initially informational); coverage floor made blocking at the measured level | Tooling-only PRs; zero runtime change; each new gate is introduced *warn-first* for one release |
| **QR-C Structural refactors (behavior-preserving)** | hot-spot matrix | `simulate_trades` phase extraction inside R22's boundary; `generate_signals` trigger protocol; `validate_run_spec`/`study.schema` declarative validation; `build_markdown_report` templating; bundle key single source of truth; `app_state.py` out of the library | Golden-gated byte-identical; one function per PR; CC target per PR stated; §4.1 applies |
| **QR-D UI decomposition and state lifecycle** | QI-10, MI-0.00 pages | Page render trees split into testable helpers; one invalidation mechanism; session-key graph asserted by a test against `ARCHITECTURE.md`; `AppTest` smoke per page if QI-10 verdict is feasible | Presentation-only PRs; RUX contract respected; session-key contract additive |
| **QR-E Application functions and features** | `app` Medium/Low + UX gaps + proposal §3 gaps still open | Copy consistency, operability (identity/provenance visibility), error legibility, performance fixes justified by QI-14 (R22 rules), feature completions that QI found half-shipped (e.g. Portfolio page depth vs R21 scope) | Opt-in / additive; docs same PR |
| **QR-F Documentation consolidation** | QI-13 | Rule ledger → mechanized rules; doc inventory pruning to `archive/`; living docs re-verified; Help corpus paths frozen | Docs-only PRs; HC allowlist untouched |
| **QR-G Dependency and supply-chain hygiene** | QI-12 | Lockfile/constraints, dependabot or renovate with full-suite gating, `pip-audit`/`bandit` CI jobs (warn-first), devcontainer alignment, pandas-major matrix decision | Tooling-only; version bumps as separate test-gated PRs (proposal §7) |

### 9.2 Sequencing rules (non-negotiable)

1. **QR-A before anything that touches the same file.** Fix what lies before you refactor how it is written (the AUDIT_FINAL lesson: "research-honesty first, not easy-first").
2. **QR-B before QR-C.** No F-grade engine function is refactored until its default-on paths are golden-gated and a mutation baseline exists for its tests.
3. **Warn-first gates.** Every new CI gate (types, imports, security, coverage floor) ships informational for one release, then blocking in its own PR.
4. **One hot spot per PR**, with the measured CC/MI before and after in the PR body.
5. **Docs in the same PR**, per repo rule; `ENGINEERING_ROADMAP.md` gets a QR status row.
6. **No scope creep into product features** from QR-C/D PRs; features are QR-E with their own opt-in flags.

### 9.3 PR acceptance checklist (QR, extends `ENGINEERING_PROPOSAL` §4.2)

- [ ] Cites finding ID(s) from `findings.csv`; disposition updated to `fixed` with PR link.
- [ ] Probe test from the QI report committed as a regression test (red before, green after) for QR-A.
- [ ] Golden-master tests unchanged (or dedicated `GOLDEN_REGEN` PR).
- [ ] For QR-C: CC and MI before/after; no public signature change; byte-identical outputs on golden + feature-path fixtures.
- [ ] For QR-B/G: gate introduced warn-first; documented in `AGENT_GUIDE.md` §Development environment.
- [ ] Living docs amended in the same PR; contract docs amended, not reopened.
- [ ] "Regression safety" paragraph in the PR body.

### 9.4 Success metrics (targets set by QI-15 against §4 baseline; indicative)

| Metric | Baseline (§4) | Indicative target |
|---|---|---|
| F-grade functions in `engine/`, `analytics/`, `api.py` | 11 | 0 (E allowed only with a documented reason) |
| Pages with MI 0.00 | 9 | 0 |
| Prose-only import bans | all | 100% encoded in `import-linter`, blocking |
| Library modules importing Streamlit | 1 | 0 |
| Type-check errors on `engine/`+`analytics/` (strict) | unmeasured | measured, then monotonically decreasing, then blocking |
| Mutation score on sampled engine files | unmeasured | ≥ 80% killed |
| Coverage gate | informational 85% | blocking at measured level |
| Security/dependency scans in CI | none | `bandit` + `pip-audit` blocking on High |
| Broad `except` | 83 | each classified; *hides defect* class = 0 |
| Composer-parity divergences (ledger) | from QI-15 | 0 open outside `locked` |
| `ARCHITECTURE.md` session-key table vs measured graph | unmeasured | asserted by a test |
| Full-suite wall time | §A.4 | tracked; `unit` marker subset < 5 min |

---

## 10. Risk register and stop conditions

| Risk | Mitigation |
|---|---|
| Slice re-audits a locked layer and produces "findings" that contradict `AUDIT_FINAL` §5 | Rule 5 (§2); §A.3 lists what is locked; QI-15 rejects such rows as `locked` |
| Metric theater — chasing CC numbers changes behavior | QR-B precedes QR-C; goldens byte-identical; one hot spot per PR |
| Parallel slices double-report the same root cause | Ownership map (QI-0) assigns every file to one slice; §7.2 merges |
| Investigation sprawls into feature design | §1.2 non-goals; findings carry one-sentence `remediation_direction` only |
| Probe touches real store or secrets | Rule 7; `/tmp` store; CI has no secrets by design |
| Long-running suite slows every slice | QI-0 publishes per-file durations; slices run only their scope's suites plus the golden set, and the full suite once at the end |

**Stop and escalate** (to the CTO review) when a slice finds: a Critical `Verified defect` (do not wait for QI-15 — open an issue-style report immediately, still no fix); evidence that goldens or the suite are red on `main` (already the case at plan time — §4.3/§4.6 — so slices must not start until it is cleared); secrets or PII in tracked files; a locked contract that is demonstrably violated by shipped code (contract *breach*, not disagreement).

---

## Appendix

### A.1 Baseline commands (reproduce §4)

```bash
# environment
python3 --version; python3 -m pip list 2>/dev/null | rg -i 'pandas|numpy|streamlit|plotly|pyarrow|pyyaml|kaleido|pdfplumber'
git rev-parse --short HEAD; git log -1 --format='%ad' --date=short

# size
find thesistester -name '*.py' | xargs cat | wc -l; find pages -name '*.py' | xargs cat | wc -l
find tests -name '*.py' | xargs cat | wc -l; rg -c 'def test_' tests | awk -F: '{s+=$2} END {print s}'
find docs -name '*.md' | wc -l; cat docs/*.md | wc -l

# lint / format (CI parity)
pip install "ruff>=0.16,<0.17"; ruff check . --statistics; ruff format --check .

# complexity / maintainability / dead code
pip install radon vulture
radon cc thesistester pages -s -n D --total-average
radon cc thesistester pages -s -j > /tmp/cc.json     # histogram via a 6-line python snippet
radon mi thesistester pages -s | awk '{ if ($3+0 < 30) print }'
vulture thesistester pages --min-confidence 60 | wc -l

# smells / coupling
rg -n 'except Exception|except:' thesistester pages | wc -l
rg -c -i 'TODO|FIXME|XXX|HACK' thesistester pages | awk -F: '{s+=$2} END {print s}'
rg -c 'type: ignore|noqa' thesistester pages | awk -F: '{s+=$2} END {print s}'
rg -c 'st\.session_state' pages | awk -F: '{s+=$2} END {print s}'
rg -l '^import streamlit|^from streamlit' thesistester
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' pages thesistester | wc -l

# churn
git log -400 --format='' --name-only | rg '\.py$' | sort | uniq -c | sort -rn | head -30

# tests (full, with coverage and durations) — ~40 min on the dev VM
pytest -q -p no:cacheprovider --cov=thesistester --cov-report=term-missing --cov-report=xml --durations=25

# security / supply chain (read-only)
pip install pip-audit bandit; pip-audit --progress-spinner off; bandit -r thesistester -ll -q

# type-check probe (read-only; no config committed)
pip install mypy; mypy --strict --ignore-missing-imports thesistester/engine thesistester/analytics thesistester/api.py | tail -1
```

### A.2 Module → slice ownership (seed; QI-0 completes it to every file)

| Path | Slice |
|---|---|
| `thesistester/data/**`, `pages/1_Data.py`, `config.py`, `persistence/local_store.py` (datasets) | QI-1 |
| `thesistester/levels/**`, `visualization/levels_chart.py`, `pages/2_Levels.py`, `persistence/local_store.py` (levels) | QI-2 |
| `thesistester/setup.py`, `engine/signals*.py`, `engine/confluence.py`, `engine/anchor_confluence.py`, `engine/naked.py`, `engine/candidate_level.py`, `engine/otf*.py`, `visualization/signals_chart.py`, `visualization/chart_window.py`, `pages/3_Setup_Builder.py`, `pages/6_Signals.py` | QI-3 |
| `thesistester/engine/backtest.py`, `engine/sim_core.py`, `engine/intrabar.py`, `engine/exit_management.py`, `entry_window_policy.py`, `execution_defaults.py`, `analytics/metrics.py`, `analytics/entry_window.py` (Admit), `pages/7_Backtest.py`, `visualization/backtest_chart.py`, `visualization/trade_review*` | QI-4 |
| remaining `thesistester/analytics/**`, `pages/8_*.py`, `9_*.py`, `10_*.py`, `13_*.py` | QI-5 |
| `api.py`, `cli.py`, `__main__.py`, `research_identity.py`, `research_bundle.py`, `reporting.py`, `classic_*.py`, `app_state.py`, `persistence/execution_artifacts.py`, `pages/11_*.py`, `12_*.py` | QI-6 |
| `thesistester/study/**`, `pages/15_*.py`, `16_*.py`, `examples/studies/**`, `tests/study/**` (as subject) | QI-7 |
| `thesistester/journal/**`, `pages/17_Journal.py`, `examples/journal/**` | QI-8 |
| `thesistester/assistant/**`, `pages/14_*.py`, `config/assistant.toml` | QI-9 |
| `app.py`, cross-page behavior, `classic_nav.py`, `timezone_display.py`, `.streamlit/` | QI-10 |
| `tests/**` (as subject), `pyproject [tool.pytest|coverage]` | QI-11 |
| `pyproject.toml`, `requirements.txt`, `.github/**`, `.devcontainer/**`, `LICENSE`, `.env.example`, `scripts/**` | QI-12 |
| `docs/**`, `README.md`, `.cursor/rules/**` | QI-13 |
| cross-cutting measurement | QI-14 |

### A.3 Prior-audit carry-over list (status re-verification only)

Closed by AH0–AH6 (verify the fix's probe test exists; do not re-audit): **C1** flatten leak (AH1), **C2** Study replay path (AH2), **C3** OTF-matrix train peek (AH3), **H1** leftover keys / dataset-less bootstrap (AH4, partial — residual to QI-6/QI-10), **H3** `close` as level (AH6), **H6** `sl_first` × 3c entry activation (AH5).

Open or parked (status only, assigned): **H2** promote pin roots → QI-7 · **H4** product-default levels planes → QI-2 · **H5** `allow_all` disclosure → QI-4 · **H7** cutoff without flatten UI/API → QI-4 · **H8** battery default-on (parked, disclosure) → QI-6 · **H9** `dataset_id` ingest story → QI-1 · **H10** Data-page fatal OHLCV → QI-1 · **H11** DST-crossing canonical CSV → QI-1 · **H12** Focus over-statement → QI-5 · **H13** Phase 8 confirmatory copy → QI-5 · **H14** HTF stale developing levels → QI-3 · **H15** OTF TZ UI vs API → QI-4 · **H16** failed-cell honesty / WFA-ignorant ranking → QI-7 (+QI-5). Medium/Low items: QI-15 imports the `AUDIT_FINAL` §4 Medium/Low tables verbatim with `disposition=carry-over` and assigns slices by file path.

From `THESISTESTER_ANALYSIS.md`: W1–W3, W14 closed (R9); W10 closed (R14); W11 closed (R18/RS); W13 closed (R17); W16 closed (R21); **W12** performance → QI-14; **W15** page numbering gap (still 1,2,3,6…) → QI-10 cosmetic.

Locked (never re-audit; premises): `AUDIT_FINAL` §5.1–5.4 and §7; `AUDIT_HONESTY_IMPLEMENTATION_PLAN` §2 and §2.1.

### A.4 Full-suite run recorded during QI-0

Measured by the plan author on the dev VM (Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0), `main@e82c2a9`. QI-0 re-records these into `docs/quality/QI-00_BASELINE.md` after the §4.6 hotfix.

| Item | Value |
|---|---|
| Command | `pytest -q --no-header -p no:cacheprovider --durations=25` |
| Result | **1 failed, 3,965 passed, 5 skipped in 2:19** — identical to the CI py3.12 cell at the same commit (§4.3); the single failure is the Streamlit 1.63 `AppTest` drift |
| With branch coverage (`--cov=thesistester`, `branch = true`) | ≈ 5× slower (962 tests in 2:20 before `-x` stopped it); coverage % recorded in `QI-00_BASELINE.md` (R9 baseline 88%; CI floor 85% informational) |
| Slowest tests | `visualization/test_trade_review_chart.py::test_worst_loser_export_contains_bounded_pngs` 4.51 s (kaleido PNG export) · `test_api.py::test_validation_r16_noise_is_opt_in_and_seeded` 2.11 s · `test_assistant_workspace.py::test_orchestrator_facade_restores_failed_cancelled_and_bundle_handoff` 2.03 s · `test_assistant_execution_parity.py::test_api_cli_and_assistant_canonical_hashes_match` 1.92 s · `test_cli.py::test_parallel_batch_is_identical_to_serial` 1.79 s; only 5 tests exceed 1.5 s, none exceeds 5 s |
| Reading | The suite is **fast** (≈ 35 ms/test) — feedback-loop cost is not the problem; signal integrity (§4.3) and assertion depth (QI-11 mutation sample) are |

### A.5 ISO/IEC 25010 mapping used in `findings.csv`

`functional_suitability` · `performance_efficiency` · `compatibility` · `usability` · `reliability` · `security` · `maintainability` · `portability`. Sub-characteristics are free text in the record.
