# QI-00 — Baseline, tooling harness, evidence protocol

**Slice:** QI-0 (research-only + §1.2 harness exception)
**Status:** Measured
**Audited commit:** `6786713` (`67867135f43a0be9684f449cb29455e6c6a3989a`) — `main` after merge of [#478](https://github.com/AccumuLatata/ThesisTester/pull/478) (CI restore) on top of [#477](https://github.com/AccumuLatata/ThesisTester/pull/477) (this plan)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS (`Linux cursor 6.12.94+ x86_64`), Python 3.12.3
**Key packages:** pandas 3.0.5 · numpy 2.4.4 · streamlit 1.63.0 · plotly 7.0.0 · pyarrow 25.0.1 · PyYAML 6.0.3 · kaleido 1.4.0 · pdfplumber 0.11.10 · pytest 9.1.1 · ruff 0.16.7 · radon 6.0.1 · vulture 2.16 · pip-audit 2.10.1 · bandit 1.9.4 · mypy 2.3.1 · pytest-cov 7.1.0
**Full `pip list`:** `/tmp/qi0-pip-list.txt` (111 lines; not committed)
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi0-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 0 (C/H/M/L = 0/0/0/0). Metrics are hypotheses only (plan §4.4).
**Time spent:** one agent run on 2026-09-12.

Plan §4 numbers were measured on `main @ e82c2a9` (2026-09-08). This report **re-measures** the same tables on `6786713` and notes drift. It does not copy the plan snapshot as SoT.

## Commands run (verbatim)

```bash
python3 --version
python3 -m pip list
git rev-parse HEAD
git log -1 --format='%ad' --date=short
uname -a

find thesistester -name '*.py' | wc -l
find thesistester -name '*.py' | xargs cat | wc -l
find pages -name '*.py' | xargs cat | wc -l
find tests -name '*.py' | wc -l
rg -c 'def test_' tests | awk -F: '{s+=$2} END {print s}'
find docs -name '*.md' | wc -l
cat docs/*.md | wc -l

ruff check . --statistics
ruff format --check .

radon cc thesistester pages -s -n D --total-average
radon cc thesistester pages -s -j > /tmp/qi0-cc.json
radon mi thesistester pages -s
vulture thesistester pages --min-confidence 60
vulture thesistester pages --min-confidence 80

rg -n 'except Exception|except:' thesistester pages | wc -l
rg -n '\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b' thesistester pages
rg -c 'type: ignore|noqa' thesistester pages | awk -F: '{s+=$2} END {print s}'
rg -c 'st\.session_state' pages | awk -F: '{s+=$2} END {print s}'
rg -l '^import streamlit|^from streamlit' thesistester
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' pages thesistester | wc -l

git log -400 --format='' --name-only | rg '\.py$' | sort | uniq -c | sort -rn | head -30

# before harness files (throwaway store)
THESISTESTER_STORE_DIR=/tmp/qi0-store-before pytest -q --tb=no
# coverage + durations (XML under /tmp; after pytest-cov install)
THESISTESTER_STORE_DIR=/tmp/qi0-store-cov pytest -q -p no:cacheprovider \
  --cov=thesistester --cov-report=term-missing \
  --cov-report=xml:/tmp/qi0-coverage/coverage.xml --durations=25
# second determinism pass
THESISTESTER_STORE_DIR=/tmp/qi0-store-det pytest -q -p no:cacheprovider --durations=25
# after harness files
THESISTESTER_STORE_DIR=/tmp/qi0-store-after pytest -q --tb=no

python scripts/quality_metrics.py --output /tmp/qi0-metrics.json

python -m thesistester --help
python -m thesistester study --help
python -m thesistester journal --help
streamlit run app.py --server.headless true --server.port 8765
curl -sf http://127.0.0.1:8765/_stcore/health

pip-audit --progress-spinner off
bandit -r thesistester -ll -q
mypy --strict --ignore-missing-imports thesistester/engine thesistester/analytics thesistester/api.py
```

Harness reproduction of the §A.1 counters lives in `scripts/quality_metrics.py` (committed). Probe transcripts stay under `/tmp`.

---

## 1. Scope actually covered and anything skipped

**Covered**

- Repo-wide read of `thesistester/`, `pages/`, `scripts/`, `examples/` for the exclusive ownership map (172 `.py` files + root `app.py`).
- §A.1 static counters on `6786713`.
- Full-suite `pytest` before the harness files (green).
- CLI `--help` for `python -m thesistester`, `study`, `journal`.
- Headless Streamlit boot + `/_stcore/health`.
- Read-only `pip-audit`, `bandit -ll`, `mypy --strict` (results recorded; interpretation is QI-12).
- Prior-audit **assignment** of §A.3 items to slices (status re-verification is those slices’ work).
- `AUDIT_FINAL.md` §5 / AH §2 treated as premises; not re-audited.

**Skipped (out of scope)**

- Mutation testing (`mutmut`) — QI-11.
- Per-entry-point §3.2 application checklist — QI-1…QI-10.
- Branch-protection / required-status reality — QI-12.
- Docs-to-code drift of living docs — QI-13.
- Performance envelopes / flame graphs — QI-14.
- Interpreting any metric as a finding.

**Tracked files this slice is allowed to add:** `scripts/quality_metrics.py`, `docs/quality/README.md`, `docs/quality/findings.csv` (header only), `docs/quality/QI-00_BASELINE.md`. Synthetic fixture recipes are notes in `docs/quality/README.md`, not committed CSVs.

---

## 2. Code-quality readout (re-measured §4 tables)

Headline sizes use the §A.1 `find | xargs cat | wc -l` / `rg` commands. JSON twin: `/tmp/qi0-metrics.json` via `scripts/quality_metrics.py`.

### 2.1 Size and shape vs plan `e82c2a9`

| Dimension | Plan `e82c2a9` | This `6786713` | Drift |
|---|---|---|---|
| Library LOC / modules (`thesistester/`) | 81,829 / **153** | **81,848** / **153** | +19 LOC; module count unchanged. +19 is `thesistester/journal/join.py` (575 → 594) from #478 |
| Streamlit pages LOC / files (`pages/` only) | **18,172** / 15 | **18,172** / 15 | none. `app.py` is 51 lines (QI-10), excluded from this count |
| Test LOC-proxy / files / `def test_` | 92,644 / **196** / **3,715** | files **196** / `def test_` **3,715** | file and `def test_` unchanged |
| Collected tests | **3,966** collected (3,965 pass + 1 fail; 5–6 skipped) | **3,966 passed + 5 skipped** | fail cleared by #478; collection size matches passed+failed of the plan run |
| Docs (`docs/**/*.md`) | 66 files, 34,883 top-level `cat docs/*.md` lines | **67** files before this PR; top-level `cat docs/*.md` **35,599** | +1 file (`QUALITY_INVESTIGATION_PLAN.md` via #477); +716 top-level lines. This PR adds `docs/quality/*.md` (QI-13 inventory) |
| `AGENT_GUIDE` / `ASSUMPTIONS` / `ARCHITECTURE` | ~750 / ~1,520 / ~1,760 | 757 / 1,524 / 1,748 | small; #478 added 8 lines to `AGENT_GUIDE.md` |
| Commits | 1,875 | **1,883** | +8 |
| Largest modules | same order | `results_overview.py` 4,373 · `api.py` 3,204 · `pages/14` 2,581 · `pages/15` 2,261 · `orchestrator.py` 2,075 · `observatory.py` 2,069 · `pages/1` 1,983 · `pages/10` 1,949 · `pages/7` 1,858 | LOC of the named set unchanged vs the plan list |

Recent churn (top, last 400 commits) — still Study-heavy; journal has entered the top 15:

| Commits | Path |
|---|---|
| 29 | `tests/study/test_study_observatory.py` |
| 27 | `pages/15_Studies.py` (plan 28) |
| 26 | `thesistester/study/observatory.py` |
| 20 | `tests/study/test_study_viewer.py` (new vs plan top) |
| 20 | `pages/16_Study_Observatory.py` |
| 19 | `thesistester/study/schema.py` |
| 19 | `thesistester/api.py` |

### 2.2 Static quality vs plan `e82c2a9`

| Metric | Plan `e82c2a9` | This `6786713` | Drift |
|---|---|---|---|
| `ruff check .` (E4,E7,E9,F,W) | clean | clean | none |
| `ruff format --check .` | clean (367 files) | clean (367 files) before this PR | harness file formatted with ruff so the tree stays clean |
| CC histogram / blocks / average | A 1,775 · B 619 · C 293 · D 60 · E 27 · F 21; 2,795 blocks; avg 6.28 (B) | A **1,776** · B 619 · C 293 · D 60 · E 27 · F 21; **2,796** blocks; avg **6.28** (B) | +1 A-grade block |
| F-grade functions | 21 named in §4.2 | **same 21**, same CC integers | none |
| Pages with MI 0.00 (plan callout) | 8 pages + `analytics/confluence_attribution.py`; `pages/2_Levels.py` 7.24; `overfitting.py` 16.09 | those nine still hold (`2_Levels.py` 7.24; `overfitting.py` 16.09) | **plus** 19 other library modules also measure MI 0.00 (see list). Plan §4.2 highlighted pages + one analytics file; it did not claim that list was exhaustive. Not a finding |
| Pages ≤ 5 top-level functions | 10_Validation 4 / 7_Backtest 5 / 8_Grid 3 / 9_Time 1 / 11_Report 3 / 13_Portfolio 0 | identical | none |
| `st.session_state` matching lines | 1,176 (Studies 235 · Data 170 · Validation 140 · Assistant 138) | **1,176** (same four heads) | none |
| Broad `except Exception` / bare `except` | 83 | **83** | none |
| `TODO/FIXME/XXX/HACK` (no `-i`) | 0 real | **0**. `-i` still hits 8 `todo` locals in `study/execute.py` | none |
| `# noqa` / `# type: ignore` | 36 | **36** | none |
| Return annotations | 1,588 vs 6 (plan heuristic) | same-line `def … ->` **1,598**; AST walk **2,416** annotated / **32** unannotated | +10 same-line arrows. The plan’s “6 unannotated” is a different (narrower) count than a full AST walk. Both recorded; not a finding |
| Library Streamlit imports | 1 (`app_state.py`) | **1** (`thesistester/app_state.py`) | none |
| Cross-module private-import `rg` | 10 | **10** | none. Several hits are `import public as _alias` (regex false friends). QI-6/QI-7 classify |
| `vulture` ≥60 / ≥80 | 110 / 2 (`sidecar.py` `fp`, `newurl`) | **110** / **2** (same two at 100%) | none |

F-grade (CC ≥ 41), engine/analytics/api-adjacent — unchanged:

| CC | Symbol |
|---|---|
| 152 | `reporting.build_markdown_report` |
| 133 | `engine/backtest.simulate_trades` |
| 120 | `engine/signals.generate_signals` |
| 104 | `api.validate_run_spec` |
| 75 | `research_bundle.load_research_bundle` |
| 69 | `setup.validate_setup_config` |
| 63 | `research_bundle.build_research_bundle` |
| 59 | `engine/signals_3c.detect_3c_setups_with_trigger_timeframe` |
| 55 | `engine/signals_3c.detect_3c_setups` |
| 51 | `api.run_validation` |
| 50 | `analytics/walk_forward.run_walk_forward_sl_tp` |

F-grade — assistant / study / pages — unchanged:

| CC | Symbol |
|---|---|
| 120 | `assistant/results_overview._format_scalar_for_claim` |
| 73 | `results_overview.compose_deterministic_replies` |
| 73 | `pages/15_Studies._draft_from_builder_widgets` |
| 62 | `study/builder.hydrate_study_draft` |
| 60 | `study/execute.run_study` |
| 59 | `pages/15_Studies._render_build` |
| 52 | `assistant/explainer._derive_caveats` |
| 51 | `assistant/help_corpus.score_corpus_chunk` |
| 47 | `pages/3_Setup_Builder._sync_editor_widget_state` |
| 46 | `study/schema._validate_factors` |

MI = 0.00 measured on this tree (28 modules):

`reporting.py`, `api.py`, `analytics/confluence_attribution.py`, `assistant/{workspace,orchestrator,results_overview,results_projections,repository,explainer}.py`, `persistence/{execution_artifacts,local_store}.py`, `engine/signals.py`, `journal/{match,report,counterfactual}.py`, `study/{observatory,builder,execute,viewer,schema}.py`, `pages/{1_Data,3_Setup_Builder,6_Signals,7_Backtest,10_Validation,14_Research_Assistant,15_Studies,16_Study_Observatory}.py`.

Page shape (top-level `def` only; classes excluded so the count matches plan §4.2):

| Page | LOC | top-level `def` |
|---|---|---|
| `1_Data.py` | 1,983 | 46 (plus 3 classes) |
| `2_Levels.py` | 919 | 9 |
| `3_Setup_Builder.py` | 1,451 | 23 |
| `6_Signals.py` | 1,701 | 33 |
| `7_Backtest.py` | 1,858 | 5 |
| `8_Grid_Search.py` | 801 | 3 |
| `9_Time_Analysis.py` | 719 | 1 |
| `10_Validation.py` | 1,949 | 4 |
| `11_Report_Export.py` | 386 | 3 |
| `12_Research_Bundles.py` | 266 | 15 |
| `13_Portfolio.py` | 122 | 0 |
| `14_Research_Assistant.py` | 2,581 | 13 |
| `15_Studies.py` | 2,261 | 42 (plus 1 class) |
| `16_Study_Observatory.py` | 966 | 14 |
| `17_Journal.py` | 209 | 4 |

### 2.3 Test and tooling baseline vs plan §4.3

| Metric | Plan `e82c2a9` | This `6786713` |
|---|---|---|
| Full suite | 1 failed, 3,965 passed, 5 skipped in 2:19 (Streamlit 1.63 `AppTest` drift) | **3,966 passed, 5 skipped in 2:16** (`pytest -q` before harness). #478 restored green on this Python 3.12 / pandas 3.0.5 / streamlit 1.63.0 cell |
| CI status on `main` | Red since 2026-09-05 | Precondition claimed met: #478 merged. QI-0 **did not** query GitHub branch protection or the Actions matrix (QI-12). Local py3.12 cell is green |
| Type checker in CI | none | still none. Read-only `mypy --strict --ignore-missing-imports` on `engine/` + `analytics/` + `api.py`: **163 errors in 33 files** (31 sources requested; imports pulled extras). Handoff QI-12 |
| Security scanning in CI | none | still none. `bandit -r thesistester -ll`: 1 High (SHA1 in `study/naming.py`) + 4 Medium (`urllib.request.urlopen` in assistant LLM/voice). Handoff QI-12 / QI-7 / QI-9 |
| `pip-audit` | project-direct clean; env `setuptools` / `urllib3` / `wheel` | **No direct declared package** (`streamlit`, `pandas`, `numpy`, `plotly`, `pyarrow`, `PyYAML`, `kaleido`, `pdfplumber`) appears in the advisory table. Transitive of declared deps on this VM: `cryptography 41.0.7` (via `pdfminer.six` ← `pdfplumber`), `Jinja2 3.1.2` (via `altair`/`pydeck` ← Streamlit), `idna`/`urllib3` (via `requests`). Environment-only: `ansible`/`ansible-core`, `pip`, `PyJWT`, `setuptools`, `wheel`, `httplib2`. Handoff QI-12. Not classified here |
| Import-layer enforcement | none mechanical | unchanged |
| Devcontainer / runtime caps | recorded in the plan | not re-opened (QI-12 / QI-10) |

### 2.4 Hypotheses (not findings) — plan §4.4 restated with this tree

These remain **hypotheses** for later slices. QI-0 does not promote them to findings.

- **H-0 (status update, still not a QI-0 finding).** The plan verified `main` red and 37 merges over red cells. This checkout is locally green after #478. Whether required status checks now block merges is **unverified** (QI-12). The Streamlit-minor / pandas-major split described in §4.3 is still the QI-12 dependency-drift story.
- **H-0b.** Coverage vs the 85% informational floor / 88% R9 baseline — see §2.5 once the coverage XML is parsed. Classification of *where* misses matter is QI-11.
- **H-A…H-F.** Unchanged triggers: F-grade still sits on `simulate_trades` / `generate_signals` / `validate_run_spec` / `build_markdown_report`; eight pages still MI 0.00; `api.py` still 3,204 LOC; assistant volume still leads; docs still ~35k top-level lines. Ownership below assigns the files.

### 2.5 Full-suite run (plan §4.5 / §A.4)

See §A.4 at the bottom of this file (filled from the measured runs on this VM).

---

## 3. Application-quality readout (QI-0 probes only)

§3.2 checklists are **not** applied here (user-facing slices own them). QI-0 probes:

| Probe | Command | Result |
|---|---|---|
| Streamlit boot | `streamlit run app.py --server.headless true --server.port 8765` | Uvicorn on `:8765` in 2 s |
| Health | `curl -sf http://127.0.0.1:8765/_stcore/health` | `ok` |
| CLI root | `python -m thesistester --help` | exit 0; verbs `run`, `study`, `journal` |
| Study CLI | `python -m thesistester study --help` | exit 0; `expand/run/report/promote/rollup/list/observatory` |
| Journal CLI | `python -m thesistester journal --help` | exit 0; `reconcile/attribute/counterfactual/match/zones/triggers/report` |
| Console scripts | `python -m importlib.metadata` entry points | no standalone `study` / `journal` console script (matches plan) |

These probes confirm **process boot**, not backtest / metric / Study correctness.

---

## 4. Prior-audit carry-over status (assignment only)

`AUDIT_FINAL.md` §5 and AH §2 are **premises**. QI-0 does not re-verify probe tests.

**Closed by AH0–AH6** (later slices confirm the probe test still exists; do not re-audit math): C1 → QI-4 · C2 → QI-7 · C3 → QI-5 · H1 partial → QI-6 / QI-10 · H3 → QI-3 · H6 → QI-4.

**Open or parked (status only):**

| Item | Slice |
|---|---|
| H2 promote pin roots | QI-7 |
| H4 levels planes | QI-2 |
| H5 `allow_all` disclosure | QI-4 |
| H7 cutoff-without-flatten | QI-4 |
| H8 battery default-on (parked) | QI-6 |
| H9 `dataset_id` ingest story | QI-1 |
| H10 Data-page fatal OHLCV | QI-1 |
| H11 DST-crossing canonical CSV | QI-1 |
| H12 Focus over-statement | QI-5 |
| H13 Phase 8 confirmatory copy | QI-5 |
| H14 HTF stale developing levels | QI-3 |
| H15 OTF TZ UI vs API | QI-4 |
| H16 failed-cell honesty / WFA-ignorant ranking | QI-7 (+ QI-5) |
| W12 performance | QI-14 |
| W15 page numbering gap 4/5 | QI-10 |
| W1–W3, W14 closed-by-R9 intent residual | QI-12 |
| Medium/Low tables | QI-15 imports verbatim |

Locked: `AUDIT_FINAL` §5.1–5.4 and §7; AH §2 / §2.1. Never re-audit.

---

## 5. Findings

**None.** `docs/quality/findings.csv` ships the §3.3 header only. Plan §4.4 items stay hypotheses.

---

## 6. Positive verification

What was checked and is fine, so later slices do not re-do this baseline:

1. **Local full suite on this `main` is green** after #478: 3,966 passed, 5 skipped (`pytest -q`, Python 3.12.3, pandas 3.0.5, streamlit 1.63.0). This is a *suite* result, not a claim that goldens prove flatten / restore / composer admissions (`AUDIT_FINAL` §5.1 item 10).
2. **`ruff check` and `ruff format --check` are clean** on the audited tree (367 files).
3. **§A.1 static counters reproduce** through `scripts/quality_metrics.py` (CC histogram, F-grade set, vulture 110/2, except 83, TODO 0, noqa 36, session_state 1,176, Streamlit-in-library 1, private-import `rg` 10, LOC 81,848 / 18,172).
4. **Ownership map is exclusive and complete** for every `.py` under `thesistester/`, `pages/`, `scripts/`, `examples/`, plus root `app.py` (172 files; 0 unassigned; 0 double-owned).
5. **CLI module interface boots:** `python -m thesistester --help` / `study --help` / `journal --help` exit 0. No extra console scripts.
6. **Streamlit headless serves `/_stcore/health` → `ok`.**
7. **No real TODO/FIXME/XXX/HACK markers** in `thesistester/` or `pages/` (case-sensitive §A.1 command).
8. **Isolation:** throwaway `/tmp` store; no API keys; no desk PII committed or pasted.
9. **Direct declared runtime deps** do not appear as `pip-audit` rows on this VM (transitive / image packages are QI-12).
10. **Harness is informational:** no CI workflow file was added.

---

## 7. Handoffs to other slices

| To | Observation (not a finding) |
|---|---|
| QI-1 | `pages/1_Data.py` MI 0.00, 46 defs, 170 session-state lines; `local_store.py` MI 0.00; `data/loader.py` MI 14.62 / two D-grade fns; H9/H10/H11 |
| QI-2 | `pages/2_Levels.py` MI 7.24; `_sync_levels_widget_state` E (39); H4 |
| QI-3 | `generate_signals` F 120 / MI 0.00; 3c F 55–59; `validate_setup_config` F 69; page 3 F 47 / MI 0.00; page 6 MI 0.00; `engine/__init__.py` owned here (re-exports QI-4 symbols — do not treat as dual ownership) |
| QI-4 | `simulate_trades` F 133; `pages/7_Backtest.py` MI 0.00 / 5 defs; H5/H7/H15/H6; `visualization/__init__.py` owned here |
| QI-5 | `confluence_attribution.py` MI 0.00; `walk_forward` F 50; `overfitting.py` MI 16.09; `pages/10_Validation.py` 1,949 / 4 defs / MI 0.00; H12/H13/H16 share |
| QI-6 | `api.py` 3,204 / `validate_run_spec` F 104 / MI 0.00; `reporting.build_markdown_report` F 152; `app_state.py` is the sole library Streamlit import; H1 residual / H8; `thesistester/__init__.py` owned here (version attr used by packaging → QI-12 note) |
| QI-7 | Highest recent churn; `pages/15` F 73+59 / 235 session lines; `run_study` F 60; H2/H16; SHA1 in `study/naming.py` (bandit High) |
| QI-8 | `journal/join.py` +19 LOC from #478 (TJ5 null cells); several journal modules MI 0.00 |
| QI-9 | `results_overview.py` 4,373 / `_format_scalar_for_claim` F 120; vulture 100% `sidecar.py` `fp`/`newurl`; bandit Medium `urlopen` in `llm.py` / `xai_realtime.py` |
| QI-10 | 1,176 session-state lines; `app.py` / `classic_nav.py` / `timezone_display.py`; W15; H1 residual |
| QI-11 | Exclusive owner of `tests/**`. Coverage XML at `/tmp/qi0-coverage/coverage.xml`. Suite wall time ~2:16 without cov. Determinism + mutation + smell scan |
| QI-12 | Exclusive owner of `scripts/**` except this harness; CI / deps / `mypy` 163 / `pip-audit` transitive / bandit / branch protection / H-0 gate reality |
| QI-13 | Exclusive owner of `docs/**` (including this file after merge). Docs file count 67 → 69 with QI-0 files. Do not amend living docs in QI |
| QI-14 | Durations file from the coverage run; CAI `realistic` recipe in `docs/quality/README.md`; W12 |

**Package-init exclusivity (do not re-open as dual ownership):**

- `thesistester/engine/__init__.py` → QI-3; re-exports `simulate_trades` / intrabar / exit → QI-4 reads, does not own.
- `thesistester/persistence/__init__.py` → QI-1; re-exports `execution_artifacts` → QI-6 reads.
- `thesistester/visualization/__init__.py` → QI-4; `levels_chart` / `signals_chart` / `chart_window` → QI-2 / QI-3 read.
- `thesistester/analytics/__init__.py` → QI-5; `metrics` / `entry_window` → QI-4 read.

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/AGENT_GUIDE.md` | Development-environment note already touched by #478; QI-12 may add lockfile / required-check / type-checker policy |
| `docs/ARCHITECTURE.md` | Session-key table vs measured graph (QI-10); Streamlit-in-library boundary (`app_state.py`) |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Only if a later slice verifies an honesty-surface mismatch (not done here) |
| `docs/USER_GUIDE.md` | Page/widget drift (QI-13 / user-facing slices) |
| `docs/METRICS_GLOSSARY.md` | Metric inventory (QI-5) |
| `docs/ENGINEERING_ROADMAP.md` | QI/QR status row (QI-15 / QR) |
| `docs/ENGINEERING_PROPOSAL.md` §7 | Streamlit-minor sibling of the pandas-drift risk (QI-12) |
| `docs/README.md` | Index line for `docs/quality/` (QI-13) |

---

## 9. Exclusive module → slice ownership map

SoT for later slices. Every path appears once. Spec docs named in a slice Scope are **read as spec** and owned by QI-13. `tests/**` is QI-11 even when it exercises another slice.

Counts: QI-0 1 · QI-1 11 · QI-2 22 · QI-3 15 · QI-4 13 · QI-5 18 · QI-6 16 · QI-7 23 · QI-8 18 · QI-9 32 · QI-10 3 · QI-11 0 in this tree · QI-12 0 `.py` (owns `scripts/set_store_dir.ps1` and non-harness scripts) · QI-13 0 `.py` · QI-14 0 (measurement only).

`examples/journal/` has no `.py` (YAML only; QI-8). `config/assistant.toml` is QI-9 (not `.py`). `.streamlit/` is QI-10.

| Path | Slice |
|---|---|
| `scripts/quality_metrics.py` | QI-0 |
| `pages/1_Data.py` | QI-1 |
| `thesistester/config.py` | QI-1 |
| `thesistester/data/__init__.py` | QI-1 |
| `thesistester/data/derive.py` | QI-1 |
| `thesistester/data/loader.py` | QI-1 |
| `thesistester/data/quantower_ticks.py` | QI-1 |
| `thesistester/data/resample.py` | QI-1 |
| `thesistester/data/rolls.py` | QI-1 |
| `thesistester/data/sessions.py` | QI-1 |
| `thesistester/persistence/__init__.py` | QI-1 |
| `thesistester/persistence/local_store.py` | QI-1 |
| `pages/2_Levels.py` | QI-2 |
| `thesistester/levels/__init__.py` | QI-2 |
| `thesistester/levels/all.py` | QI-2 |
| `thesistester/levels/apoc.py` | QI-2 |
| `thesistester/levels/apoc_candidates.py` | QI-2 |
| `thesistester/levels/apoc_tick.py` | QI-2 |
| `thesistester/levels/catalog.py` | QI-2 |
| `thesistester/levels/common.py` | QI-2 |
| `thesistester/levels/defaults.py` | QI-2 |
| `thesistester/levels/indicators.py` | QI-2 |
| `thesistester/levels/pivots.py` | QI-2 |
| `thesistester/levels/prev30m_vwap.py` | QI-2 |
| `thesistester/levels/profile.py` | QI-2 |
| `thesistester/levels/rolling_poc_candidates.py` | QI-2 |
| `thesistester/levels/rolling_poc_tick.py` | QI-2 |
| `thesistester/levels/session_date.py` | QI-2 |
| `thesistester/levels/session_vwap.py` | QI-2 |
| `thesistester/levels/sessions.py` | QI-2 |
| `thesistester/levels/tick_requirements.py` | QI-2 |
| `thesistester/levels/tick_vap.py` | QI-2 |
| `thesistester/levels/tpo.py` | QI-2 |
| `thesistester/visualization/levels_chart.py` | QI-2 |
| `pages/3_Setup_Builder.py` | QI-3 |
| `pages/6_Signals.py` | QI-3 |
| `thesistester/engine/__init__.py` | QI-3 |
| `thesistester/engine/anchor_confluence.py` | QI-3 |
| `thesistester/engine/candidate_level.py` | QI-3 |
| `thesistester/engine/confluence.py` | QI-3 |
| `thesistester/engine/naked.py` | QI-3 |
| `thesistester/engine/otf.py` | QI-3 |
| `thesistester/engine/otf_filter.py` | QI-3 |
| `thesistester/engine/otf_integration.py` | QI-3 |
| `thesistester/engine/signals.py` | QI-3 |
| `thesistester/engine/signals_3c.py` | QI-3 |
| `thesistester/setup.py` | QI-3 |
| `thesistester/visualization/chart_window.py` | QI-3 |
| `thesistester/visualization/signals_chart.py` | QI-3 |
| `pages/7_Backtest.py` | QI-4 |
| `thesistester/analytics/entry_window.py` | QI-4 |
| `thesistester/analytics/metrics.py` | QI-4 |
| `thesistester/engine/backtest.py` | QI-4 |
| `thesistester/engine/exit_management.py` | QI-4 |
| `thesistester/engine/intrabar.py` | QI-4 |
| `thesistester/engine/sim_core.py` | QI-4 |
| `thesistester/entry_window_policy.py` | QI-4 |
| `thesistester/execution_defaults.py` | QI-4 |
| `thesistester/visualization/__init__.py` | QI-4 |
| `thesistester/visualization/backtest_chart.py` | QI-4 |
| `thesistester/visualization/trade_review_chart.py` | QI-4 |
| `thesistester/visualization/trade_review_export.py` | QI-4 |
| `pages/10_Validation.py` | QI-5 |
| `pages/13_Portfolio.py` | QI-5 |
| `pages/8_Grid_Search.py` | QI-5 |
| `pages/9_Time_Analysis.py` | QI-5 |
| `thesistester/analytics/__init__.py` | QI-5 |
| `thesistester/analytics/confluence_attribution.py` | QI-5 |
| `thesistester/analytics/excursions.py` | QI-5 |
| `thesistester/analytics/grid.py` | QI-5 |
| `thesistester/analytics/monte_carlo.py` | QI-5 |
| `thesistester/analytics/noise.py` | QI-5 |
| `thesistester/analytics/otf_validation.py` | QI-5 |
| `thesistester/analytics/overfitting.py` | QI-5 |
| `thesistester/analytics/portfolio.py` | QI-5 |
| `thesistester/analytics/prev30m_vwap_hit.py` | QI-5 |
| `thesistester/analytics/sensitivity.py` | QI-5 |
| `thesistester/analytics/time_analysis.py` | QI-5 |
| `thesistester/analytics/validation.py` | QI-5 |
| `thesistester/analytics/walk_forward.py` | QI-5 |
| `pages/11_Report_Export.py` | QI-6 |
| `pages/12_Research_Bundles.py` | QI-6 |
| `thesistester/__init__.py` | QI-6 |
| `thesistester/__main__.py` | QI-6 |
| `thesistester/api.py` | QI-6 |
| `thesistester/app_state.py` | QI-6 |
| `thesistester/classic_context.py` | QI-6 |
| `thesistester/classic_export.py` | QI-6 |
| `thesistester/classic_ledger.py` | QI-6 |
| `thesistester/classic_proposal.py` | QI-6 |
| `thesistester/classic_record.py` | QI-6 |
| `thesistester/cli.py` | QI-6 |
| `thesistester/persistence/execution_artifacts.py` | QI-6 |
| `thesistester/reporting.py` | QI-6 |
| `thesistester/research_bundle.py` | QI-6 |
| `thesistester/research_identity.py` | QI-6 |
| `examples/studies/program_b/generate_program_b_yaml.py` | QI-7 |
| `examples/studies/program_b/validate_program_b_yaml.py` | QI-7 |
| `pages/15_Studies.py` | QI-7 |
| `pages/16_Study_Observatory.py` | QI-7 |
| `thesistester/study/__init__.py` | QI-7 |
| `thesistester/study/admit_followup.py` | QI-7 |
| `thesistester/study/apoc_provenance.py` | QI-7 |
| `thesistester/study/briefing.py` | QI-7 |
| `thesistester/study/builder.py` | QI-7 |
| `thesistester/study/cli_study.py` | QI-7 |
| `thesistester/study/execute.py` | QI-7 |
| `thesistester/study/expand.py` | QI-7 |
| `thesistester/study/launch.py` | QI-7 |
| `thesistester/study/ledger.py` | QI-7 |
| `thesistester/study/naming.py` | QI-7 |
| `thesistester/study/observatory.py` | QI-7 |
| `thesistester/study/preview.py` | QI-7 |
| `thesistester/study/promote.py` | QI-7 |
| `thesistester/study/report.py` | QI-7 |
| `thesistester/study/rollup.py` | QI-7 |
| `thesistester/study/schema.py` | QI-7 |
| `thesistester/study/tools.py` | QI-7 |
| `thesistester/study/viewer.py` | QI-7 |
| `pages/17_Journal.py` | QI-8 |
| `thesistester/journal/__init__.py` | QI-8 |
| `thesistester/journal/amp_statement.py` | QI-8 |
| `thesistester/journal/cli.py` | QI-8 |
| `thesistester/journal/counterfactual.py` | QI-8 |
| `thesistester/journal/join.py` | QI-8 |
| `thesistester/journal/ledger.py` | QI-8 |
| `thesistester/journal/levels.py` | QI-8 |
| `thesistester/journal/match.py` | QI-8 |
| `thesistester/journal/pair.py` | QI-8 |
| `thesistester/journal/reconcile.py` | QI-8 |
| `thesistester/journal/report.py` | QI-8 |
| `thesistester/journal/rules.py` | QI-8 |
| `thesistester/journal/schema.py` | QI-8 |
| `thesistester/journal/tags.py` | QI-8 |
| `thesistester/journal/tradesviz.py` | QI-8 |
| `thesistester/journal/triggers.py` | QI-8 |
| `thesistester/journal/zones.py` | QI-8 |
| `pages/14_Research_Assistant.py` | QI-9 |
| `thesistester/assistant/__init__.py` | QI-9 |
| `thesistester/assistant/comparison.py` | QI-9 |
| `thesistester/assistant/contracts.py` | QI-9 |
| `thesistester/assistant/explainer.py` | QI-9 |
| `thesistester/assistant/handlers.py` | QI-9 |
| `thesistester/assistant/help_corpus.py` | QI-9 |
| `thesistester/assistant/llm.py` | QI-9 |
| `thesistester/assistant/llm_explainer.py` | QI-9 |
| `thesistester/assistant/llm_intent.py` | QI-9 |
| `thesistester/assistant/orchestrator.py` | QI-9 |
| `thesistester/assistant/page_summaries.py` | QI-9 |
| `thesistester/assistant/product_help.py` | QI-9 |
| `thesistester/assistant/registry.py` | QI-9 |
| `thesistester/assistant/registry_audit.py` | QI-9 |
| `thesistester/assistant/repository.py` | QI-9 |
| `thesistester/assistant/results_overview.py` | QI-9 |
| `thesistester/assistant/results_projections.py` | QI-9 |
| `thesistester/assistant/results_qa.py` | QI-9 |
| `thesistester/assistant/thesis_compiler.py` | QI-9 |
| `thesistester/assistant/tools.py` | QI-9 |
| `thesistester/assistant/ux.py` | QI-9 |
| `thesistester/assistant/voice/__init__.py` | QI-9 |
| `thesistester/assistant/voice/contracts.py` | QI-9 |
| `thesistester/assistant/voice/grounding.py` | QI-9 |
| `thesistester/assistant/voice/intent.py` | QI-9 |
| `thesistester/assistant/voice/session.py` | QI-9 |
| `thesistester/assistant/voice/settings.py` | QI-9 |
| `thesistester/assistant/voice/sidecar.py` | QI-9 |
| `thesistester/assistant/voice/tools.py` | QI-9 |
| `thesistester/assistant/voice/xai_realtime.py` | QI-9 |
| `thesistester/assistant/workspace.py` | QI-9 |
| `app.py` | QI-10 |
| `thesistester/classic_nav.py` | QI-10 |
| `thesistester/timezone_display.py` | QI-10 |

---

## 10. Probe scripts (pasted; not committed)

Histogram over `radon cc -j` (same logic as `scripts/quality_metrics.py`):

```python
import json
from collections import Counter
data = json.load(open("/tmp/qi0-cc.json"))
grades = Counter()
for blocks in data.values():
    for b in blocks:
        if isinstance(b, dict) and b.get("rank"):
            grades[b["rank"]] += 1
print(dict(sorted(grades.items())), "blocks", sum(grades.values()))
```

Streamlit + CLI isolation wrapper used for probes:

```bash
export THESISTESTER_STORE_DIR=/tmp/qi0-store-streamlit
mkdir -p "$THESISTESTER_STORE_DIR"
unset OPENAI_API_KEY XAI_API_KEY
streamlit run app.py --server.headless true --server.port 8765 \
  --browser.gatherUsageStats false
curl -sf http://127.0.0.1:8765/_stcore/health
python3 -m thesistester --help
python3 -m thesistester study --help
python3 -m thesistester journal --help
```

Synthetic fixture recipes for later slices: `docs/quality/README.md`.

---

## A.4 Full-suite run recorded during QI-0

Measured on this VM (Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0), `main@6786713`, throwaway store.

| Item | Value |
|---|---|
| Before-harness command | `pytest -q --tb=no` (`THESISTESTER_STORE_DIR=/tmp/qi0-store-before`) |
| Before-harness result | **3,966 passed, 5 skipped in 136.73 s (2:16)** — exit 0. Plan `e82c2a9` A.4 was 1 fail / 3,965 pass in 2:19; the fail was the #478 Streamlit 1.63 `AppTest` mechanism. Identical collection, green |
| Coverage + durations | `pytest -q -p no:cacheprovider --cov=thesistester --cov-report=term-missing --cov-report=xml:/tmp/qi0-coverage/coverage.xml --durations=25` — XML kept under `/tmp` (not committed). Filled after that run completes in this agent session |
| Second determinism pass | `pytest -q -p no:cacheprovider --durations=25` — filled after that run |
| After-harness `pytest -q` | must match the before-harness line (guardrail 2) |
| Reading | Suite is fast (~35 ms/test without coverage). Feedback-loop cost is not the problem. Signal integrity of CI required checks is QI-12. Assertion depth is QI-11 |

Per-module coverage table, modules < 70%, and the slowest 25 tests are appended once the coverage XML exists. Until then this paragraph is a placeholder owned by the same QI-0 commit cycle.

---

## Research-only sentence

No product, test, fixture, workflow, or living-doc file was edited. The only tracked additions are the §1.2 harness files: `scripts/quality_metrics.py`, `docs/quality/README.md`, `docs/quality/findings.csv` (header), and this report `docs/quality/QI-00_BASELINE.md`. Tooling is informational; **no CI job was added**.
