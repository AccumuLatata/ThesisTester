# QI-13 — Documentation, contracts, and drift

**Slice:** QI-13 (research-only)
**Status:** Completed
**Audited commit:** `539dd2e` (`539dd2e9dabc9ba918f03b26f66537f3d9fca3ce`) — `main` after merge of [#488](https://github.com/AccumuLatata/ThesisTester/pull/488) (QI-5)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi13-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 10 (C/H/M/L = 0/1/8/1)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day.

`AUDIT_FINAL.md` §5 and `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 are premises. This slice does **not** move Help-allowlisted files or amend any living doc. No backtest, metric, or Study result is described as correct or reliable. Vocabulary is plan §3.3.

**Inputs consumed (not re-audited):** QI-5 metric×glossary table (`QI-05-11`); QI-10 session-key graph (`QI-10-02`); QI-12 CI/required-check reality (`QI-12-01`, `QI-12-10`); AH2 docs task in `AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §6.2.

**Review corrections (schema / honesty only; no living docs):** `§1` said “QI-0 exclusive ownership” (copy-paste). Primary named files are **23** (22 table rows; `SIMULATE_PERF.md` · `CAI_BASELINE.md` share one row), not 25. Contracts named files are **31**, not 32. Dual-listed DA/TJ/JS = 3 holds. At audited `539dd2e`, `docs/quality/*.md` is **11** (this report is this PR). `.cursor/rules/thesistester.mdc` is **22** lines (`wc -l`), not 23. Session-key literals matching QI-10-02 are **162**, not 164 — first-pass added `app_state.py` (`subtimeframe_fallback_parent_bars`, `subtimeframe_restore_warning`). Main ARCHITECTURE table **109** holds. First-pass Files-allowed **383** is unreproducible; review-pass is **17** `#### Files allowed to touch` sections, **200** fenced path tokens, **0** missing. QI-12-07 is **3/6** documented import bans broken (**2** chain + **1** lazy-direct Streamlit), not “only via chains.” `locked_by` parentheticals stripped to plan §3.3 (`AUDIT_FINAL §5.x` / `AH §2.n` / `none`). First-pass claimed `/tmp/qi13_probes.py` was pasted in §10; it was a stub — review-pass snippets are pasted below. Plan §5 exit inventory (role/owner/last-verified) and drift table (claim · location · status) added. AH2 closed claim now includes the living grep hits.

## Commands run (verbatim)

```bash
git fetch origin main
git checkout main && git pull origin main   # 539dd2e
git checkout -b cursor/qi-13-docs-contracts-drift-1edd

export THESISTESTER_STORE_DIR=/tmp/qi13-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no                                          # before: 3966 passed, 5 skipped in 134.28s

python3 /tmp/qi13_probes.py                                # inventory / links / ledger / Help / keys
gh pr list --repo AccumuLatata/ThesisTester --state merged --search "QI-"
git fetch origin cursor/audit-final-merge-3a8e --depth=1
python3 -m pip install --target /tmp/qi13-clean-site -r requirements.txt

export THESISTESTER_STORE_DIR=/tmp/qi13-store-after
pytest -q --tb=no                                          # after: identical pass/fail/skip class

# review-pass (docs-only honesty/schema)
python3 /tmp/qi13_review_probe.py
export THESISTESTER_STORE_DIR=/tmp/qi13-store-review-after
pytest -q --tb=no
# review after: 3966 passed, 5 skipped in 133.57s (0:02:13) — identical result class
```

First-pass `/tmp/qi13_probes.py` was not retained. Review-pass script: `/tmp/qi13_review_probe.py` (pasted in §10). Transcripts stay under `/tmp/qi13-evidence/`. Nothing from `/tmp` is committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-13 exclusive ownership: every markdown under `docs/**`, root `README.md`, `.cursor/rules/thesistester.mdc`)

Counts below are **`539dd2e`** unless marked “this PR”.

| Shelf | Count | Lines |
|---|---:|---:|
| `docs/**/*.md` | **78** | **46,277** |
| Living Primary (`docs/README.md` table) | **23** named files (22 rows; `SIMULATE_PERF.md` · `CAI_BASELINE.md` share a row). **3** also in Contracts (DA/TJ/JS) | — |
| Normative contracts | **31** named files | — |
| `docs/archive/` | 11 (10 listed files + `archive/README.md`; index matches) | — |
| `docs/research/` | 3 (2 snapshots + `research/README.md`; index matches) | — |
| `docs/quality/` | **11** md at `539dd2e` (QI-00…QI-06, QI-10…QI-12, `README.md`). This PR adds the 12th. `findings.csv` is not `.md` | — |
| Root `README.md` | 1 (Help-allowlisted `whole_file`) | 347 |
| `tests/fixtures/golden/README.md` | 1 (QI-13-owned spec; QI-11 reads) | — |
| `.cursor/rules/thesistester.mdc` | 1 | **22** |

Headline living docs: `AGENT_GUIDE.md` 757 · `ASSUMPTIONS_AND_LIMITATIONS.md` 1,524 · `ARCHITECTURE.md` 1,748 · `USER_GUIDE.md` 1,267 · `METRICS_GLOSSARY.md` 768 · `ENGINEERING_ROADMAP.md` 1,633.

### 1.1 Inventory (role / owner / last-verified)

Plan §5 QI-13 exit. Owner is QI-13 for every path in this table (plan §A.2). Last-verified = this SHA’s living tree (`539dd2e`).

| Path / shelf | Role | Owner | Last-verified |
|---|---|---|---|
| `docs/README.md` Primary (23 files) | living | QI-13 | `539dd2e` |
| `docs/README.md` Contracts (31 files) | contract-complete | QI-13 | `539dd2e` |
| `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` | orphan (implemented; unindexed) | QI-13 | `539dd2e` |
| `docs/archive/` (11) | archive | QI-13 | `539dd2e` |
| `docs/research/` (3) | research snapshot | QI-13 | `539dd2e` |
| `docs/quality/` (11 md @ `539dd2e`) | investigation reports | QI-13 | `539dd2e` |
| `README.md` | living / Help `whole_file` | QI-13 | `539dd2e` |
| `tests/fixtures/golden/README.md` | living spec (QI-11 reads) | QI-13 | `539dd2e` |
| `.cursor/rules/thesistester.mdc` | agent rule | QI-13 | `539dd2e` |

**Read as spec (other slices own the code):** `thesistester/assistant/help_corpus.py` (`HELP_CORPUS_MANIFEST`, `_USER_GUIDE_SECTIONS`); `pages/*.py` titles/widgets; `engine/backtest.py` / `setup.py` / `levels/defaults.py` / `levels/all.py` / `data/derive.py` / `api.py` / `journal/**` / `study/observatory.py` for the 15 ASSUMPTIONS samples; QI-5 / QI-10 / QI-12 reports.

**Skipped**

- Re-audit of locked engine math (AUDIT S1–S5, DA0 `_check_touch`, 3c four-rule). Status of *claims* only.
- QI-7 / QI-8 / QI-9 / QI-14 reports (not on `main` at this SHA).
- Moving or amending Help-allowlisted files.
- A Debian `python3-venv` clean venv (package absent). README install was reproduced with `pip install --target` instead.

---

## 2. Code-quality readout (docs as a maintainability surface)

Docs are not radon-scored. The §3.1 docs-to-code trigger and plan §4.4 **H-F** apply.

| Metric | This `539dd2e` | vs QI-0 `6786713` / plan `e82c2a9` |
|---|---|---|
| `docs/**/*.md` files | **78** | QI-0: 67 before harness, then quality/; plan: 66 |
| `docs/**/*.md` lines | **46,277** | plan top-level `cat docs/*.md` 34,883 (excludes nested) |
| `AGENT_GUIDE` do-not / must-not / never **lines** | **87** across 21 H2s | unmeasured before |
| Import/call-ban sentences (must not import/call) | **10** explicit (Study + journal + wrapped Studies-page `FORMAT_PROFILE_*`). Line-regex first-pass **9** missed the wrap | QI-12-07 already encoded 6 documented import bans |
| Line-number citations in `AGENT_GUIDE` | **7** unique `file:line` cites (`README.md:7-10` ×2, `README.md:12-16`, `app.py:10-33`, `validation.py:13`, `pages/10_Validation.py:18`, `reporting.py:13-19`, `backtest.py:12-14`) — 8 occurrences | ARCHITECTURE forbids line anchors |
| Intra-doc markdown links | **169** local OK + **155** external at `539dd2e` (**0** missing). This report adds 1 external GitHub link | — |
| Help `USER_GUIDE` H2 allowlist | **25 / 25** exact match | HC freeze holds |
| `docs/README.md` unindexed `docs/**/*.md` | **11** | see §3.1 |

`AGENT_GUIDE.md` do-not density (exit criterion — rule ledger):

| H2 | do-not lines |
|---|---:|
| AI Research Assistant contracts (AIA-0+) | 28 |
| Headless and agent operation (R18) | 21 |
| R17 ingestion research safety | 7 |
| Where each phase lives | 6 |
| R12 intrabar research safety | 5 |
| Remaining 16 H2s | 0–3 each |

The two densest sections are the Study/Assistant rule ledgers. Those prose bans are the import-linter candidates. QI-12-07: **3/6** documented import bans broken — **2** via import *chains* (`preview→execute`, `launch→viewer`) and **1** lazy-**direct** Streamlit (classic_* / assistant modules; `rg '^import streamlit'` still only hits `app_state.py`). Finding QI-13-06.

`.cursor/rules/thesistester.mdc` restates regression-safety + docs-with-code. It does not duplicate the 87-line ledger. Not a finding.

---

## 3. Application-quality readout (docs / Help / install)

§3.2 page checklists are owned by QI-1…QI-10. This slice answers the **honesty surface** and **Help corpus** items.

### 3.1 Doc inventory vs `docs/README.md`

| Path | Role in `docs/README.md` | Verdict |
|---|---|---|
| Primary table (**23** files) | living | Index exists |
| Contracts list (**31** files) | complete — amend carefully | Index exists |
| `docs/archive/**` | archive README lists all 10 files + itself | **Holds** |
| `docs/research/**` | research README lists both snapshots + itself | **Holds** |
| `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` | **absent** | Orphan. Status line says Phase 6 implemented. Prose cites `docs/anchor_confluence_regression_safe_plan.md` (now `docs/archive/…`; backtick, not a markdown link) |
| `docs/DIRECTIONAL_INTEGRITY_IMPLEMENTATION_PLAN.md`, `TRADE_JOURNAL_…`, `JOURNAL_TO_STUDY_…` | **Primary and Contracts** | Dual-listed vs maintenance rule 1 |
| `docs/quality/README.md` + QI-01…QI-12 reports except QI-00 | directory mentioned on the QI Primary row; quality README links only the harness + QI-00 | Landed slice reports are not individually indexed |
| Help-allowlisted seven | named; rule 2 freeze restated | **Holds** |

Finding QI-13-05.

### 3.2 `USER_GUIDE.md` H2s vs pages vs Help

| Page title | USER_GUIDE H2 | In `_USER_GUIDE_SECTIONS`? |
|---|---|---|
| Data / Levels / Setup Builder / Signals / Backtest | same names | yes |
| SL/TP Grid Search | Grid Search | yes |
| Time Analysis | Time Analysis | yes |
| Statistical Validation | Validation and robustness | yes (title wording differs; Help key is the H2) |
| Report / Export | Report Export | yes |
| Research Bundles / Portfolio / Research Assistant / Study Observatory / Journal | match | yes |
| Studies | Research Study Runner (headless) **and** Studies viewer (read-only) | yes (one page, two H2s — by HC design) |

Concept H2s (Exposure, Intrabar, Exit management, Session close, Focus vs Admit, Research mode, Help vs Discuss) have no page file. That is correct.

Allowlist drift: `missing_from_allowlist=[]`, `allowlist_not_in_doc=[]`. **Holds.**

Widget-label sample: Setup Builder `Trigger` lists all seven `VALID_TRIGGERS` (`touch`/`reject`/`break`/`reclaim`/`3c`/`fade`/`continuation`). Direction pitfall is `—` (QI-13-08). Session close H2 documents the UI flatten gate and does not name the locked headless cutoff-without-flatten fork (QI-13-07). `USER_GUIDE.md` has **no** `thesistester run` / omit=`enabled` sentence (QI-13-09). Exposure H2 **does** disclose `allow_all` inflation and DA0 long-only.

### 3.3 `ARCHITECTURE.md` session-key table vs QI-10

Re-measured on `539dd2e` (QI-10 was `32ad34c`; no product files changed for this graph). Methodology is QI-10 review-pass: `session_state["…"]` / `.get` / `.pop` / `.setdefault` / `"…" in session_state` on `app.py` + 15 pages + `classic_nav.py` + `timezone_display.py`.

| | Count |
|---|---:|
| Main contract table names | **109** (108 backtick-only rows + 1 DA2 multi-key row) |
| `session_state` string literals (QI-10-02 file set) | **162** |
| First-pass **164** | withdrawn — added `app_state.py` only (`subtimeframe_fallback_parent_bars`, `subtimeframe_restore_warning`) |
| Table keys absent as literals | **16** — same set as QI-10-02 (tick/bundle aliases, `direction_collision_diagnostic`, portfolio/trade-review names, `backtest_same_bar_opposite_direction`) |
| Extra measured consumers vs table | `data`/`levels`/`signals` → Validation; `trades` → Portfolio |

Finding QI-13-04 (docs-side of QI-10-02). Not a new key-graph methodology.

### 3.4 `METRICS_GLOSSARY.md` vs QI-5 inventory

Mechanical needles from QI-05 §3.1 / `QI-05-11` on this tree: **all false**.

`probability_positive`, `P(mean R > 0)`, `p-value (positive)`, `p_value_positive`, `Best − Median`, `grid_overfit`, `Grid-search overfit`, `best_vs_median` — **zero hits** in `METRICS_GLOSSARY.md`.

Glossary Notes still say Validation page outputs are diagnostic. Core / R10–R16 / R19 / R21 / WFA / OTF / Study / journal rows that QI-5 marked “yes” still have H2/H3 homes. Finding QI-13-03. This slice does **not** call those page-10 numbers correct.

### 3.5 `ENGINEERING_ROADMAP.md` vs merged PRs

Roadmap QI row (living status SoT per `docs/README.md` rule 1) still says:

- **Planned.** QI-1…QI-14 ``Not started``
- **Precondition:** `main` CI red since 2026-09-05 must be cleared first
- R9 body: CI **blocking on red**

Merged on this repo before `539dd2e`:

| PR | Title | Merged |
|---|---|---|
| #477 | Quality Investigation Plan | 2026-09-12 |
| #478 | CI: restore green main | 2026-09-12 |
| #479 | QI-0 Baseline | 2026-09-12 |
| #480–#488 | QI-4, QI-3, QI-6, QI-11, QI-1, QI-2, QI-12, QI-10, QI-5 | 2026-09-12 |

Ten QI reports exist under `docs/quality/`. Local `pytest -q` on this SHA is green (3966 passed). Finding QI-13-01. The “blocking” wording is the same class as QI-12-10; this row adds the stale QI tracker and the still-printed CI-red precondition.

Completed series rows (RQ/DI/DX/RI/HC/VA/CAI/C2/AIA/SW/RS/SB/SIA/SV/SO/AH/SAF/LC/WMV/DA/TJ/JS/AO/TV/AP/RP/RUX) remain marked landed/complete. This slice did not find a “landed” series **without** a merged PR. Positive for those rows.

### 3.6 Broken links and “Files allowed to touch”

- Markdown links under `docs/**` + root `README.md` + golden README: **0 missing** local targets (169 ok, 155 external).
- Contract `#### Files allowed to touch` lists (HC / RQ / VA; **17** sections): **200** fenced path tokens, **0** missing. First-pass **383** / 10 false friends is unreproducible (no retained extractor) and is withdrawn. A whole-index path-like-backtick walk is thousands of hits and is not this check.

### 3.7 README install (clean target)

`python3 -m pip install --target /tmp/qi13-clean-site -r requirements.txt` succeeded (streamlit **1.63.0**, pandas **3.0.5**, plotly 7.0.0, …). Isolated `PYTHONPATH` (repo removed from `sys.path`): `import streamlit, pandas` works; `import thesistester` raises `ModuleNotFoundError`. From repo cwd, `import thesistester` resolves `thesistester/__init__.py`. Matches README: requirements.txt is the **app** path; `pip install -e ".[dev]"` is the library path. Not a finding. `python3-venv` was unavailable on this image; `--target` is the substitute.

Root `README.md` Phase 4 still says **five** trigger types (`touch`, `reject`, `break`, `reclaim`, `3c`) and does not mention `fade` / `continuation`. `VALID_TRIGGERS` has seven. README is Help `whole_file`. Finding QI-13-02.

### 3.8 Fifteen ASSUMPTIONS claims vs code

Sampled; status only. Not a correctness claim about fills or Study ranking.

| # | Claim (ASSUMPTIONS) | Probe | Status |
|---|---|---|---|
| 1 | `commission_per_side=0.0`, `slippage_ticks=0.0` | `simulate_trades` signature | **Holds** |
| 2 | `intrabar_model="sl_first"` default | same | **Holds** |
| 3 | `exposure_policy="allow_all"` default | same | **Holds** |
| 4 | TIME cap = `entry_bar_index + max_holding_bars - 1` | `backtest.py` `time_cap_bar` | **Holds** |
| 5 | SESSION_CLOSE uses entry calendar date, not `trading_session_date` | `session_close_ts = entry_local_ts.normalize() + …` | **Holds** |
| 6 | §4b DA0 lock is still the documented behaviour | §4b present; `_check_touch` not re-audited | **Holds as documentation of a lock** |
| 7 | OTF is not applied on Signals | `rg apply_otf` on `pages/6_Signals.py` empty | **Holds** |
| 8 | Focus is post-hoc, not `simulate_trades` | `summarize_focused_trades` has no `simulate_trades` import | **Holds** |
| 9 | Session VWAP: product defaults ON, `compute_all_levels` kwarg default OFF | `defaults.py` `session_vwap_enabled: True`; `all.py` `False` | **Holds** (H4 two-plane, already named) |
| 10 | Journal `r_multiple` is qty-scaled | `journal/schema.py` | **Holds** |
| 11 | Journal never calls `simulate_trades` / `compute_all_levels` | no such imports under `journal/` | **Holds** (JS2 may import `engine.signals` / `confluence` — not these two) |
| 12 | Observatory does not write `results/studies/` | writes only `_atomic_write_desk_json` under the desks dir | **Holds** |
| 13 | Study cells emit `enabled: false` (ASSUMPTIONS RS4) | ASSUMPTIONS §RS4; Study emit not re-run | **Holds as written for Study**. Classic headless omit=on is **not** in ASSUMPTIONS (QI-13-09) |
| 14 | Derive policy `observed_aligned_15s_to_1m_v2` | `data/derive.py` constant | **Holds** |
| 15 | `confirm_3bar` not in `VALID_TRIGGERS` | `setup.py` / `signals.py` frozensets | **Holds** |
| + | `LEVEL_ENGINE_VERSION` is 11 | `persistence/local_store.py` | **Holds** |

### 3.9 Drift table (claim · location · status)

Plan §5 QI-13 exit. Status of *claims* only.

| Claim | Location | Status |
|---|---|---|
| QI-1…14 `Not started`; `main` CI red since 2026-09-05 | `ENGINEERING_ROADMAP.md` QI row | **Drift** (QI-13-01) |
| CI jobs “blocking on red” | ROADMAP R9; `AGENT_GUIDE` CI table | **Drift** (QI-13-01; QI-12-10 sibling) |
| Five trigger types (`touch`…`3c`) | `README.md` Phase 4 | **Drift** (QI-13-02) |
| Phase 8 confirmatory labels have glossary rows | `METRICS_GLOSSARY.md` | **Drift** (QI-13-03) |
| Main key table lists Validation / Portfolio consumers | `ARCHITECTURE.md` session-key table | **Drift** (QI-13-04) |
| One living home per topic; every contract indexed | `docs/README.md` | **Drift** (QI-13-05) |
| Import/call bans are mechanized; cites are path-only | `AGENT_GUIDE.md` | **Drift / maintainability** (QI-13-06) |
| Session close Help names the UI-vs-API fork | `USER_GUIDE.md` Session close H2 | **Drift** (QI-13-07) |
| Setup Builder Direction pitfall names DA0 | `USER_GUIDE.md` Setup Builder | **Drift** (QI-13-08) |
| Classic-headless omit=`enabled` default-on | `USER_GUIDE.md` / ASSUMPTIONS | **Drift** (QI-13-09) |
| Help retrieves journal/Study ASSUMPTIONS H2s | `help_corpus._ASSUMPTIONS_SECTIONS` (8 of 23) | **Drift** (QI-13-10) |
| AH2 replay is same bytes + still `run_batch` + not `study run` | `AGENT_GUIDE.md` Fast-start; `STUDY_RUNNER.md` RS3 | **Holds** (closed-verified; grep in §10) |
| “unchanged R18 path” still advertised | same two files | **Gone** |
| USER_GUIDE 25 H2s = `_USER_GUIDE_SECTIONS` | `help_corpus.py` | **Holds** |
| ARCHITECTURE / ASSUMPTIONS / OTF allowlisted titles exist | same | **Holds** (`allowlist_not_in_doc` empty) |
| 15 sampled ASSUMPTIONS process claims | ASSUMPTIONS vs signatures/imports | **Holds** as written (§3.8) |
| 0 broken local markdown links | `docs/**` + root + golden README | **Holds** (169 / 0) |
| Files-allowed fenced lists point at existing paths | 17 HC/RQ/VA sections | **Holds** (200 / 0) |
| Archive / research READMEs list every file | those trees | **Holds** |
| README `requirements.txt` install resolves | `--target` substitute | **Holds** |
| Completed non-QI series “landed” without a merged PR | ROADMAP + `gh pr list` | **Holds** on the sample |

---

## 4. Prior-audit carry-over status

| Item | Assigned | Status on `539dd2e` |
|---|---|---|
| `AUDIT_FINAL` §5.5 / AH2 “AGENT_GUIDE L38–39 advertising replay” | this slice | **Closed-verified (docs).** Review-pass `rg` (output in §10): `AGENT_GUIDE` L38–40 “same dataset bytes” / “still run_batch” / “not study run”; `STUDY_RUNNER.md` L288–291 same. Phrase “unchanged R18 path” is **gone** from both living files (historical only in the AH plan). Pin math / promote roots remain QI-7 (H2). Do not re-audit C2. |
| H7 USER_GUIDE Session close | QI-4 code; this slice docs | Still UI-gate only (QI-13-07) |
| H8 USER_GUIDE/CLI omit disclosure | QI-6 code; this slice docs | Still missing on USER_GUIDE / ASSUMPTIONS classic path (QI-13-09) |
| H5 `allow_all` inflation | QI-4 page widget; USER_GUIDE Exposure | **USER_GUIDE Holds.** Page `help=` is QI-04-02 |
| DA0 in USER_GUIDE | QI-3 widgets; Exposure H2 | **Exposure H2 Holds.** Setup Builder H2 Direction pitfall empty (QI-13-08) |
| QI-05-11 glossary gaps | QI-5 | Still present (QI-13-03) |
| QI-10-02 key table | QI-10 | Still present (QI-13-04) |
| QI-12-10 “blocking” | QI-12 | Still present; folded into QI-13-01 |

Locked premises not re-opened: `AUDIT_FINAL` §5.1–5.4 / §7; AH §2 / §2.1.

---

## 5. Findings

| ID | Sev | Class | One-line |
|---|---|---|---|
| QI-13-01 | High | Documentation drift | ROADMAP QI row still says QI-1…14 Not started and CI red; R9/AGENT_GUIDE still say CI is blocking |
| QI-13-02 | Medium | Documentation drift | Help-allowlisted README lists five triggers; code has seven |
| QI-13-03 | Medium | Documentation drift | METRICS_GLOSSARY still misses Phase 8 confirmatory labels (QI-05-11) |
| QI-13-04 | Medium | Documentation drift | ARCHITECTURE main key table missing Validation/Portfolio consumers (QI-10-02) |
| QI-13-05 | Medium | Documentation drift | `docs/README.md` orphan + dual-list + quality reports unindexed |
| QI-13-06 | Medium | Maintainability risk | AGENT_GUIDE 87 do-not lines; import bans and `file:line` cites are prose-only |
| QI-13-07 | Medium | Documentation drift | USER_GUIDE Session close omits the locked H7 headless fork |
| QI-13-08 | Medium | Documentation drift | USER_GUIDE Setup Builder Direction pitfall omits DA0 (Help how-to) |
| QI-13-09 | Medium | Documentation drift | USER_GUIDE / ASSUMPTIONS omit H8 classic-headless omit=on |
| QI-13-10 | Low | Documentation drift | ASSUMPTIONS Help allowlist frozen; 15 journal/study H2s are not Help-retrievable |

Full records: `docs/quality/findings.csv` (`QI-13-*` only).

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR-F do not re-do it:

1. **AH2 AGENT_GUIDE / STUDY_RUNNER replay copy was amended.** Replay is described as same dataset bytes when the expand-time file exists, still `run_batch`, **not** `study run`. Carry-over §5.5 “stop advertising identity-equivalent replay” is **closed on the docs side**.
2. **Help `USER_GUIDE` allowlist is an exact 25-H2 match** with the living file. Rule 2 freeze is intact.
3. **Every allowlisted ARCHITECTURE / ASSUMPTIONS / OTF section title still exists** (`allowlist_not_in_doc` empty). The frozen *subsets* are intentional HC, not broken titles.
4. **Zero broken intra-doc markdown links** in `docs/**`, root README, and the golden README (169 local + 155 external).
5. **Contract `#### Files allowed to touch` fenced lists do not point at deleted paths** (review-pass: 17 sections, 200 tokens, 0 missing). First-pass 383 is withdrawn.
6. **Fifteen sampled ASSUMPTIONS engine/journal/Study *process* claims hold** against signatures, constants, and import graph (table §3.8). Not a fill-correctness claim.
7. **USER_GUIDE page coverage is complete** for all 15 Streamlit pages (Studies split across two H2s by design). OTF-not-on-Signals is stated on the Signals H2.
8. **USER_GUIDE Exposure H2 discloses `allow_all` inflation and DA0** (`touch`+`both`+`single_position` long-only).
9. **Archive and research READMEs list every file in those trees.**
10. **README `requirements.txt` install resolves** (streamlit 1.63.0 / pandas 3.0.5 on this `--target`). `thesistester` is importable from repo cwd, not from an isolated site-packages — as the two README install blocks describe.
11. **Completed roadmap series (non-QI) are not “landed” without a merged PR** on the sample checked via `gh pr list` + file existence.
12. **`.cursor/rules/thesistester.mdc` matches the living regression-safety rule** (ENGINEERING_PROPOSAL §4) without a second conflicting ledger.

---

## 7. Handoffs to other slices

| To | Observation (not a finding) |
|---|---|
| QI-3 | DA0 widget `help=` still missing (QI-03-08). This slice only records the Help-corpus Setup H2 gap |
| QI-4 | H7 composer fork unchanged. Session close Help copy is QI-13-07 |
| QI-5 | Glossary needles unchanged. Do not re-scan METRICS_GLOSSARY for Phase 8 |
| QI-6 | H8 `.get("enabled", True)` unchanged. CLI `--help` / USER_GUIDE omit sentence is QI-13-09 |
| QI-7 | AH2 **code** pin / H2 promote roots. Docs advertising is closed here |
| QI-9 | Help allowlist lives in `help_corpus.py` (QI-9-owned). QR-F that widens ASSUMPTIONS/OTF/ARCHITECTURE sections is an HC amend, not a path move |
| QI-10 | Key graph numbers reproduced; QI-10-02 remains the measurement SoT |
| QI-12 | Required-status / “blocking” gate is QI-12-01. This slice only records the living-doc wording |
| QI-15 | Status-tracker ownership: QI slices cannot amend `QUALITY_INVESTIGATION_PLAN.md` §8.3 or ROADMAP; QR-F must name an owner |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice. Help-allowlisted files stay in place (rule 2).

| Doc | Why QR-F would touch it |
|---|---|
| `docs/ENGINEERING_ROADMAP.md` | QI status row; R9 “blocking on red”; drop CI-red precondition |
| `docs/AGENT_GUIDE.md` | CI table “blocking”; replace `file:line` cites; optionally mechanize import bans (pointer to import-linter) |
| `docs/QUALITY_INVESTIGATION_PLAN.md` §8.3 | Tracker still “Not started” — QI slices cannot update it |
| `README.md` | Phase 4 five-trigger sentence (Help `whole_file`) |
| `docs/METRICS_GLOSSARY.md` | Phase 8 `P(mean R > 0)` / permutation p / grid-overfit Best−Median rows |
| `docs/ARCHITECTURE.md` | Session-key consumer table (Validation / Portfolio); leftover sentence already QI-6 |
| `docs/README.md` | Index `CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`; de-dual DA/TJ/JS; link `docs/quality/README.md` |
| `docs/quality/README.md` | Enumerate landed QI-01… reports (harness README currently names only QI-00) |
| `docs/USER_GUIDE.md` | Session close H7 fork; Setup Direction DA0 pitfall; optional CLI H8 sentence (in-place Help amend) |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Classic-headless H8 omit=on sentence |
| `docs/ENGINEERING_PROPOSAL.md` §7 / §4 rule 9 | Streamlit-minor sibling + “CI green” vs required checks (QI-12-10) |
| `docs/STUDY_RUNNER.md` | No AH2 replay amend needed (already honest) |
| `docs/HELP_CORPUS_COVERAGE_IMPLEMENTATION.md` | Only if QR widens ASSUMPTIONS/OTF/ARCHITECTURE allowlists (HC PR; do not move paths) |
| `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` | Shelf as contract-complete; fix archive successor pointer |

---

## 9. AGENT_GUIDE prose-rule → mechanizable-rule mapping

Exit criterion. **Mapping only** — no `import-linter` config committed (QI-12 owns tooling).

| Prose rule (AGENT_GUIDE) | Mechanizable as | Violations today (QI-12-07 / this slice) |
|---|---|---|
| `preview.py` must not import `execute` | import-linter / AST test | Direct ban **holds**; chain via `expand`→`cli` is the residual (QI-12-07) |
| `viewer.py` ↛ `cli_study` / `cli` / `execute` / `rollup` / Plotly / Streamlit | import-linter | Direct **holds** |
| `observatory.py` ↛ `cli_study` / `execute` / Streamlit / Plotly | import-linter | Direct **holds** |
| `viewer.py` ↛ `observatory` | import-linter | **Holds** |
| Do not call `run_study()` from pages / Build / Inspect | call-graph / AST (not import) | RS-D9 lock; QI-7 |
| Journal ↛ `simulate_trades` / `compute_all_levels` | import-linter | **Holds** (this slice import scan) |
| Studies page ↛ `FORMAT_PROFILE_LABELS` from `builder` | import-linter | AGENT_GUIDE R17; not re-run |
| Library Streamlit-free except documented chrome | import-linter layers | **Broken** as lazy-**direct** imports (classic_* / assistant), not only chains (QI-12-07) |
| “CI jobs are blocking” | required-status check (QI-12) | **False** today — QI-13-01 |
| `file:line` citations | delete or path-only (ARCHITECTURE rule) | 7 unique cites (8 occurrences) — QI-13-06 |
| Remaining ~70 do-not lines (do not reopen series, do not regen goldens, do not invert locks) | tests that already exist / contract docs | Keep as prose; do not invent import rules |

---

## 10. Probe scripts (review-pass; not committed)

First-pass `/tmp/qi13_probes.py` was not retained. Review-pass: `/tmp/qi13_review_probe.py`. Essential measurements on `539dd2e` product files + this report:

```text
docs/**/*.md @ 539dd2e: 78 files / 46,277 lines
docs/quality/*.md @ 539dd2e: 11
Primary named .md: 23; Contracts named .md: 31; dual: DA, TJ, JS
unindexed @ 539dd2e (excl. docs/README.md self): 11
AGENT_GUIDE H2: 21; do-not lines: 87; unique file:line cites: 7
USER_GUIDE allowlist: 25/25; ARCH/ASS/OTF allowlist_not_in_doc: []
ASSUMPTIONS H2: 23; extra vs allowlist: 15
session_state literals (QI-10 set): 162; +app_state only: 2; table names: 109
VALID_TRIGGERS: 7; README fade/continuation: false
glossary needles: all false
AH2 "unchanged R18 path": gone; "same dataset bytes" / "not study run": present
Files-allowed sections: 17; fenced tokens: 200; missing: 0
local md links: 169 ok / 0 miss; external @ 539dd2e: 155
thesistester.mdc: 22 lines
```

AH2 living grep (review-pass):

```text
docs/AGENT_GUIDE.md:38:# optional replay of the emitted experiment (same dataset bytes when the
docs/AGENT_GUIDE.md:39:# expand-time file still exists; still run_batch — fail-fast, origin=cli,
docs/AGENT_GUIDE.md:40:# no index status — not study run):
docs/STUDY_RUNNER.md:288:`python -m thesistester run experiment.yaml` still uses `run_batch` (fail-fast,
docs/STUDY_RUNNER.md:290:loads the **same dataset bytes** when the expand-time file still exists. It is
docs/STUDY_RUNNER.md:291:**not** `study run`. Study runs do **not** call `run_batch`; they loop
# "unchanged R18 path" — 0 hits in AGENT_GUIDE.md / STUDY_RUNNER.md
```

Review-pass inventory + QI-10 key-set (essential):

```python
from pathlib import Path
import re, ast
ROOT = Path("/workspace")
print("docs md", len(list((ROOT/"docs").rglob("*.md"))))
SS = re.compile(
    r"session_state\s*(?:\[\s*['\"]([^'\"]+)['\"]\s*\]"
    r"|\.\s*(?:get|pop|setdefault)\s*\(\s*['\"]([^'\"]+)['\"])"
    r"|['\"]([^'\"]+)['\"]\s+in\s+session_state"
)
files = [ROOT/"app.py", *sorted((ROOT/"pages").glob("*.py")),
         ROOT/"thesistester/classic_nav.py", ROOT/"thesistester/timezone_display.py"]
keys = set()
for p in files:
    for m in SS.finditer(p.read_text(encoding="utf-8")):
        keys.add(next(g for g in m.groups() if g))
print("qi10-set literals", len(keys))
```

README install substitute (no `python3-venv` on this image):

```bash
python3 -m pip install --target /tmp/qi13-clean-site -r requirements.txt
cd /tmp
PYTHONPATH=/tmp/qi13-clean-site python3 -c "import streamlit,pandas; print(streamlit.__version__, pandas.__version__)"
# thesistester is ModuleNotFoundError until repo cwd or pip install -e .
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
