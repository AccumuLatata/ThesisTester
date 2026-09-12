# QI-15 — Cross-slice synthesis and remediation-program handoff

**Slice:** QI-15 (research-only; §1.2 file exceptions: this report, `docs/QUALITY_REMEDIATION_PLAN.md` draft, four additive columns on `docs/quality/findings.csv`)
**Status:** Draft for CTO review gate (plan §7.5). CTO dispositions in §6 are **proposals**; Accumu signs.
**Census note (post-#494):** the disposition counts in §2–§4 and §3.6 are the QI-15 snapshot (119 open / 12 locked / 2 duplicate / 1 wont-fix). The fix-vs-close re-baseline in `docs/QUALITY_REMEDIATION_PLAN.md` §2 moved 13 rows to `wont-fix`/`duplicate` (now 106 open); `docs/quality/findings.csv` is the SoT.
**Review correction (same PR, research-only):** merge-group census was 25/76/58 against a 26-group CSV (MG-04 was a singleton). MG-04 dissolved; QI-01-04 residual moved QR-A→QR-F (document parked H11, do not unpark); §4.1 now lists all four score=5.0 rows; `n/a` weight and 1-decimal rounding stated. Slice evidence fields untouched.
**Synthesised commit:** `0b2c451` (`main` after [#493](https://github.com/AccumuLatata/ThesisTester/pull/493), QI-14). Slice reports were audited on `e30cc48` / `32ad34c` / `539dd2e`; this synthesis re-verified only status and metrics on `0b2c451`.
**Environment:** Ubuntu 24.04 (`Linux 6.12.94+ x86_64`), Python 3.12.3, pandas 3.0.5, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1 (installed for re-measurement; not a repo dependency).
**Inputs:** `docs/QUALITY_INVESTIGATION_PLAN.md` §2, §3.3, §7, §8.1, §9; `docs/quality/QI-00_BASELINE.md`; `docs/quality/QI-01…QI-14`; `docs/quality/findings.csv` (134 rows). Locked premises: `AUDIT_FINAL.md` §5 (`origin/cursor/audit-final-merge-3a8e`), `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1.
**Time spent:** one agent run on 2026-09-12 (Claude Fable 5.1, one-time exception recorded in the task).

> **Financial caution (plan §2 rule 6).** Nothing in this synthesis describes a backtest, metric, or Study result as correct. Every "holds" below is a *process / identity / status* statement carried over from the slice that verified it.

## Commands run (verbatim)

```bash
git fetch origin main && git checkout main && git reset --hard origin/main   # 0b2c451
git checkout -b cursor/qi-15-synthesis-32f0

# registry parse + report presence
python3 - <<'EOF'
import csv, collections
rows = list(csv.DictReader(open('docs/quality/findings.csv', encoding='utf-8')))
print(len(rows), collections.Counter(r['severity'] for r in rows))
EOF
for f in docs/quality/QI-0[1-9]*.md docs/quality/QI-1[0-4]*.md; do rg -n '^## 6\. Positive verification' "$f"; done

# re-measurement for §5.2 (informational)
pip install radon
python3 -m radon cc thesistester pages -s -j > /tmp/qi15/cc.json
python3 -m radon mi thesistester pages -s -j > /tmp/qi15/mi.json
git log -400 --format='' --name-only | rg '\.py$' | sort | uniq -c | sort -rn

# guardrail 2 (throwaway store; keys unset)
export THESISTESTER_STORE_DIR=/tmp/qi15/store-before; unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no -p no:cacheprovider          # before any file change
export THESISTESTER_STORE_DIR=/tmp/qi15/store-after
pytest -q --tb=no -p no:cacheprovider          # after the three files
git status --porcelain
```

The disposition/score assignment script lives at `/tmp/qi15/assign.py` (throwaway; its logic is restated in §3–§4 so the CSV columns are reproducible by hand). It appends the four columns **textually**: every one of the 134 slice rows is byte-identical to `HEAD` up to the appended `,merge_group,score,qr_workstream,disposition` suffix (verified with `git show HEAD:docs/quality/findings.csv` line-by-line `startswith`).

---

## 1. Review-gate inputs (§7.5 a) — fourteen reports, all with Positive verification

| Slice | Report | Slice PR | Audited commit | Findings C/H/M/L | §6 Positive verification |
|---|---|---|---|---|---|
| QI-1 | `QI-01_DATA_INGESTION.md` | [#484](https://github.com/AccumuLatata/ThesisTester/pull/484) | `32ad34c` | 0/0/6/1 | present (11 items) |
| QI-2 | `QI-02_LEVELS_ENGINE_PIT.md` | [#485](https://github.com/AccumuLatata/ThesisTester/pull/485) | `32ad34c` | 0/0/5/3 | present (10) |
| QI-3 | `QI-03_SETUP_SIGNALS_OTF.md` | [#481](https://github.com/AccumuLatata/ThesisTester/pull/481) | `e30cc48` | 0/3/6/3 | present (12) |
| QI-4 | `QI-04_EXECUTION_ENGINE.md` | [#480](https://github.com/AccumuLatata/ThesisTester/pull/480) | `e30cc48` | 0/2/6/2 | present (12) |
| QI-5 | `QI-05_ANALYTICS_VALIDATION_BATTERIES.md` | [#488](https://github.com/AccumuLatata/ThesisTester/pull/488) | `32ad34c` | 0/4/8/3 | present (10) |
| QI-6 | `QI-06_HEADLESS_FACADE.md` | [#482](https://github.com/AccumuLatata/ThesisTester/pull/482) | `e30cc48` | 0/1/9/2 | present (10) |
| QI-7 | `QI-07_STUDY_SYSTEM.md` | [#492](https://github.com/AccumuLatata/ThesisTester/pull/492) | `539dd2e` | 0/0/8/2 | present (10) |
| QI-8 | `QI-08_TRADE_JOURNAL.md` | [#491](https://github.com/AccumuLatata/ThesisTester/pull/491) | `539dd2e` | 0/0/5/0 | present (11) |
| QI-9 | `QI-09_RESEARCH_ASSISTANT_VOICE.md` | [#490](https://github.com/AccumuLatata/ThesisTester/pull/490) | `539dd2e` | 0/0/7/4 | present (10) |
| QI-10 | `QI-10_UI_SESSION_STATE.md` | [#487](https://github.com/AccumuLatata/ThesisTester/pull/487) | `32ad34c` | 0/0/5/3 | present (12) |
| QI-11 | `QI-11_TEST_SUITE_QUALITY.md` | [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) | `e30cc48` | 0/0/4/2 | present (10) |
| QI-12 | `QI-12_TOOLING_CI_SECURITY.md` | [#486](https://github.com/AccumuLatata/ThesisTester/pull/486) | `32ad34c` | 0/2/7/1 | present (11) |
| QI-13 | `QI-13_DOCS_CONTRACTS_DRIFT.md` | [#489](https://github.com/AccumuLatata/ThesisTester/pull/489) | `539dd2e` | 0/1/8/1 | present (12) |
| QI-14 | `QI-14_PERFORMANCE_ENVELOPE.md` | [#493](https://github.com/AccumuLatata/ThesisTester/pull/493) | `539dd2e` | 0/0/6/4 | present (11) |
| **Total** | 14 reports | | | **0 / 13 / 90 / 31 = 134** | **14 / 14** |

Every report follows the plan §3.4 skeleton and every slice recorded `pytest -q` identical before/after (3,966 passed, 5 skipped) with porcelain limited to its two `docs/quality/` files. No slice found a Critical `Verified defect`; no slice reported secrets/PII in tracked files; no slice reported a locked-contract *breach* (only locked-contract *costs*, §7). The plan §10 stop conditions were therefore never triggered.

---

## 2. Registry totals (`findings.csv`, 134 rows, 23 columns after this slice)

### 2.1 Severity × disposition

| Severity | open | locked | duplicate | wont-fix | closed-verified | Total |
|---|---:|---:|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 | 0 | **0** |
| High | 13 | 0 | 0 | 0 | 0 | **13** |
| Medium | 77 | 11 | 2 | 0 | 0 | **90** |
| Low | 29 | 1 | 0 | 1 | 0 | **31** |
| **Total** | **119** | **12** | **2** | **1** | **0** | **134** |

`closed-verified` is **0 in the CSV by construction**: slices only wrote rows for open findings. The items that *were* re-verified closed (C1, C2, C3, H3, H6, H1-managed-set, W1/W2/W14 as written, AH2 replay copy) never became rows; they are carried in the §5.7 positive-verification register with their AH/R PR references so QR does not re-audit them (§7.2 rule 3 satisfied via the register, not via rows).

### 2.2 Classification · axis · confidence

| Classification | n | | Axis | n | | Confidence | n |
|---|---:|---|---|---:|---|---|---:|
| Maintainability risk | 49 | | code | 68 | | Verified | 111 |
| UX/operability gap | 23 | | app | 49 | | Strong | 10 |
| Documentation drift | 21 | | both | 17 | | n/a (Design limitation) | 13 |
| Design limitation | 17 | | | | | Moderate / Speculative | 0 |
| Test-quality gap | 14 | | | | | | |
| Verified defect | 5 | | | | | | |
| Security risk | 5 | | | | | | |

Reading: the investigation produced **evidence-grade rows** (111 Verified + 10 Strong; zero Moderate/Speculative). The five `Verified defect` rows are all Medium/High *process or lifecycle* defects (QI-12-01 branch protection, QI-12-02 dependency drift, QI-06-03 / QI-10-01 H1 leftovers, QI-08-03 PDF exception leak) — none is a fill/P&L defect. That is consistent with `AUDIT_FINAL` having already fixed C1–C3 and with QI's mandate (status re-verification, not re-audit).

### 2.3 Rows per slice and per QR workstream

| Slice | rows | | Workstream | rows (open + locked residual + dup) |
|---|---:|---|---|---|
| QI-05 | 15 | | QR-A Honesty and correctness | 25 (21 open · 4 locked residual) |
| QI-03 · QI-06 | 12 · 12 | | QR-B Safety net | 19 (19 open) |
| QI-09 | 11 | | QR-C Structural refactors | 32 (32 open) |
| QI-04 · QI-07 · QI-12 · QI-13 · QI-14 | 10 each | | QR-D UI decomposition / state | 10 (10 open) |
| QI-02 · QI-10 | 8 · 8 | | QR-E Application functions | 17 (15 open · 2 locked residual) |
| QI-01 | 7 | | QR-F Documentation | 23 (16 open · 5 locked residual · 2 duplicate) |
| QI-11 | 6 | | QR-G Dependency / supply chain | 6 (6 open) |
| QI-08 | 5 | | no workstream | 2 (QI-07-10 locked, no residual; QI-10-06 wont-fix) |

---

## 3. Deduplication, merging, links, carry-over (§7.2)

### 3.1 Conventions used in the four new columns

| Column | Rule |
|---|---|
| `merge_group` | `MG-nn-<slug>`. Two kinds, stated per group below: **root-cause** (same `files_symbols` cause; §7.2 rule 1 — highest severity and union blast radius are those of the group) and **class** (same fix pattern across files; one PR series). Singletons have an empty `merge_group` (a 1-member group is not a group). |
| `disposition` | `open` = actionable in QR · `locked` = classification *Design limitation*, `confidence=n/a`, and `locked_by` names an `AUDIT_FINAL` §5 / AH §2 premise — the behavior is not to be changed; the row's *disclosure/test residual* (if any) is owned by the named `qr_workstream` and flagged "disclosure only" in the QR plan · `duplicate` = identical fix in the same file as another row (primary named in §3.3) · `wont-fix` = explicit CTO-proposed no-action · `closed-verified` = unused (§2.1). |
| `score` | §7.3 formula, **open rows only** (blank for locked/duplicate/wont-fix), rounded to 1 decimal. |
| `qr_workstream` | exactly one of QR-A…QR-G; blank only for `wont-fix` and for the one locked row with no residual (QI-07-10). A locked row's workstream is the *disclosure/test* residual, never an unpark/invert. |

### 3.2 Merge groups (25 groups, 88 rows; 46 singletons)

| Group | Kind | Root cause / class | Members (primary first) | Kept severity | Union blast radius |
|---|---|---|---|---|---|
| MG-01-h1-leftover-lifecycle | root-cause (H1 class) | Independent research-key lists (dataset-clear · exec-clear · AH4 managed · thesis staging · fingerprint) disagree; docs SoT incomplete | **QI-10-01**, QI-06-03, QI-10-03, QI-06-04, QI-03-12, QI-13-04, QI-10-02 (dup) | Medium (Verified defect ×2) | Data · Levels · Setup · Signals · Backtest · Time · Report · Bundles · Validation · Portfolio · Assistant apply |
| MG-02-allow-all-disclosure-h5 | root-cause (H5) | `allow_all` overlap inflates N with no page-level disclosure; DA1 diagnostic discarded on Composer A | **QI-04-02**, QI-05-09, QI-04-06 | High | Backtest · Grid · Time · combo N · API/Study (diagnostic parity) |
| MG-03-cutoff-fork-h7 | root-cause (H7, locked) | Cutoff-without-flatten: UI forces `None`, headless applies | QI-04-03 (locked), QI-05-10 (locked), **QI-13-07**, QI-04-07 | Medium | Backtest · Grid · API · CLI · Study · Help |
| MG-05-omit-means-on-disclosure-h8 | root-cause (H8, locked behavior) | Omitted battery `enabled` ⇒ on for api/CLI/assistant; undisclosed | **QI-06-08**, QI-13-09, QI-09-08 (locked) | Medium | API · CLI · Assistant · hand YAML · Help |
| MG-06-confirmatory-copy-h13 | root-cause (H13) | Phase 8 `st.success` / confirmatory labels; missing glossary rows | **QI-05-05**, QI-13-03, QI-05-11 (dup) | High | Validation · Report export · Help |
| MG-08-study-ranking-h16 | root-cause (H16) | Ranking ignores WFA OOS; failed cells unlabeled in MD/rollup | **QI-05-06**, QI-07-04 | Medium | Study report · rollup · promote · index |
| MG-09-levels-planes-h4 | root-cause (H4, locked) | Three levels default planes; omit ⇒ on for `prev30m_vwap` | QI-02-01 (locked), QI-14-04 (locked) | Medium | Levels · API · CLI · Study · Assistant · CAI |
| MG-10-ingest-forks-h9-h10-h11 | root-cause (locked forks) + test | H10 legacy primary admits fatals on UI; H11 mixed-offset raw ValueError; H9 `dataset_id` omits mode; no lock-the-fork tests | QI-01-03 (locked), QI-01-04 (locked), QI-01-05 (locked), **QI-01-07** | Medium | Data · API · CLI · Study · Assistant · store |
| MG-11-da0-direction-disclosure | root-cause (DA0 disclosure) | `touch`+`both`+`single_position` long-only not disclosed at Direction widgets / Help | **QI-03-08**, QI-13-08 | Medium | Setup Builder · Signals · Help |
| MG-12-three-integrity-bars-m14 | root-cause (M14) | Page 12 schema-only vs assistant hash-fail-closed vs open-exact unlabeled | QI-06-06 (locked), **QI-09-10** | Medium | Bundles · Assistant · Help |
| MG-13-ci-gate-reality | root-cause | `main` unprotected; docs claim "blocking on red"; QI status rows stale | **QI-12-01**, QI-13-01, QI-12-10 | High (Verified defect) | every PR · ROADMAP · AGENT_GUIDE · PROPOSAL §7 |
| MG-14-dependency-envelope | root-cause | No lock/constraints; accidental pandas-major split; two install SoTs; devcontainer off-envelope | **QI-12-02**, QI-12-03, QI-12-08 | High (Verified defect) | CI matrix · README/devcontainer · pages 14/16 AppTest · journal join · golden hash skip |
| MG-15-coverage-debt | class | Informational floor below itself; assistant/classic/CLI/journal/`levels/common` untested | **QI-12-04**, QI-11-01, QI-09-04, QI-06-12 | Medium | CI · assistant · classic bridge · CLI · journal · levels |
| MG-16-import-boundary-mechanization | root-cause (H-C) | Prose import bans; Streamlit lazily re-enters the library; journal package-init loads engine | **QI-12-07**, QI-13-06, QI-06-05, QI-09-05, QI-08-02 | Medium | study · journal · assistant · classic bridge · 7 pages |
| MG-17-hand-rolled-validators | class | Three hand-rolled F-grade schema validators plus duplicated setup assembly and the Program B validator | **QI-06-01**, QI-03-03, QI-07-03, QI-03-10, QI-07-08 | High | API · CLI · Study · Assistant · Setup Builder · Signals |
| MG-18-simulate-trades | root-cause + gates | F-grade orchestrator (P7 alone F); goldens/mutation too shallow to refactor; serial replay cost | **QI-04-01**, QI-11-02, QI-11-04, QI-04-09, QI-14-03, QI-14-09 | High | Backtest · API · Grid · WFA · Study · CLI |
| MG-19-generate-signals | root-cause | F-grade signal orchestrator + duplicated 3c assembly; row-wise pandas is the cold-path limiter | **QI-03-01**, QI-03-02, QI-14-05 | High | Signals · API · CLI · Study · Assistant |
| MG-20-walk-forward | root-cause | F(50) WFA multiplier; own-file mutation 50–60 %; 14 `.copy()` | **QI-05-01**, QI-14-10 (+ QI-11-04 gate in MG-18) | High | Validation · API · Study · CLI |
| MG-22-page-monoliths | class (MI 0.00 pages) | Render trees fused with sync/persist; no AppTest | **QI-01-01**, QI-02-04, QI-03-04, QI-03-05, QI-04-05, QI-05-02, QI-07-01, QI-09-03 | Medium | Data · Levels · Setup · Signals · Backtest · Validation · Studies · Assistant |
| MG-24-untyped-errors-at-boundary | class | Untyped exceptions reach operator (traceback / swallowed into empty frame / pdfminer stack) | **QI-08-03**, QI-05-12, QI-06-07, QI-02-05 | Medium (Verified defect ×1) | journal CLI · OTF matrix · CLI run · Levels |
| MG-26-apptest-harness | root-cause | AppTest asserts framework mechanics; harness isolation not shared; page `sys.path` bootstrap | **QI-11-03**, QI-10-05, QI-10-08 | Medium | pages 14/16 · CI · Data/Backtest AppTest |
| MG-27-cai-baseline-stale | root-cause | `CAI_BASELINE.md` describes a removed typical-price loop; realistic fixture dies on tick gate; warm harness has no stage timers | **QI-14-01**, QI-14-02, QI-14-07, QI-14-08 | Medium | CAI harness · docs · QR-E perf priority |
| MG-29-private-cross-module-imports | class | Implicit APIs across analytics/bundle/page | **QI-05-14**, QI-06-11 | Low | analytics · bundle hash · Report |
| MG-30-dead-non-product-paths | class | `_rolling_poc` typical body; `confirm_3bar` helpers | **QI-02-07**, QI-03-07 | Low | library callers · WFA/backtest fill |
| MG-31-security-scan-gaps | root-cause | No bandit/pip-audit/Action pins; SHA1 flagged without `usedforsecurity` | **QI-12-06**, QI-07-09 | Medium | CI · study naming · assistant HTTP |

Group numbers are stable identifiers; gaps (MG-04, MG-07, MG-21, MG-23, MG-25, MG-28) were candidate groups dissolved into singletons. MG-04 (H15) was a 1-member group (QI-04-04 only): §3.1 forbids that. QI-04-07 is the lock-the-fork *test* for both H7 and H15 — linked to QI-04-04 per §7.2 rule 2, not merged (one `merge_group` column; H7 is the shared `files_symbols` pair with QI-04-03). Other dissolved candidates had different root causes (e.g. the seven MI-0.00 *library* modules — `local_store`, `confluence_attribution`, `execution_artifacts`, study viewer/observatory/builder, journal, assistant — stay singletons).

### 3.3 Duplicates (2) and wont-fix (1)

| Row | Disposition | Primary | Reason |
|---|---|---|---|
| QI-05-11 | duplicate | **QI-13-03** | Identical fix: add Phase 8 / grid-overfit rows to `docs/METRICS_GLOSSARY.md`. QI-13 owns `docs/**`. |
| QI-10-02 | duplicate | **QI-13-04** | Identical fix: add Validation/Portfolio consumers and a CAI-5 pointer to the `ARCHITECTURE.md` session-key table. |
| QI-10-06 | wont-fix (proposed) | — | W15 page-numbering gap (1,2,3,6…17) is cosmetic; renumbering would move Help-allowlisted page names (HC rule 2 risk) and churn `test_ui_copy_guards.py`. A one-line "historical gap" note in `USER_GUIDE.md` may ride along with any QR-F PR; it is not tracked as work. |

### 3.4 Code ↔ app causal links (§7.2 rule 2 — linked, not merged)

These pairs are the most valuable output: the `code` row explains *why* the `app` row keeps recurring, and the QR plan sequences them (QR-A disclosure first, then QR-B gates, then QR-C structure).

| code row (structure) | app row(s) (behavior / honesty) | Link |
|---|---|---|
| QI-04-01 `simulate_trades` CC 133 (P7 F-grade) | QI-04-02 / QI-05-09 H5 disclosure; QI-04-06 DA1 discarded; QI-04-08 silent voids; QI-14-03 serial replay | Every H5/DA1/void surface is a literal inside the same F-grade function; skip/exit vocabulary is stringly-typed (QI-04-09). C1 lived in this loop-carried-state class. |
| QI-03-01 / QI-03-02 `generate_signals` + 3c detectors | QI-03-06 H14 (HTF developing-level staleness); QI-03-11 preview omits HTF columns; QI-14-05 cold-path limiter | H14 disclosure and any snap decision land in the 3c projection branch of a CC 120 function; QR-C must not touch S3 math. |
| QI-06-01 `validate_run_spec` CC 104 (+ QI-03-03, QI-07-03) | QI-06-08 / QI-09-08 / QI-13-09 H8 omit-means-on; QI-07-05 SIA 15s omit; QI-01-06 profile literals | Every "omitted key ⇒ default" honesty gap is a branch in a hand-rolled validator that has no declarative table to disclose from. |
| QI-06-04 bundle key tables (18 lists) + QI-10-03 six pop lists | QI-06-03 / QI-10-01 H1 leftovers (Verified defects) | Leftovers recur because membership is edited in parallel lists; a single registry is the structural fix, additive managed keys are the honesty fix. |
| QI-06-02 `build_markdown_report` CC 152 | QI-05-05 H13 export banner missing | The banner would be one more `if` in the highest-CC function in the repo. |
| QI-05-01 `run_walk_forward_sl_tp` CC 50 | QI-05-07 M9 fold-sum headline; QI-05-08 M10 heatmap contest copy | Aggregate/stitch semantics are computed and captioned in the same function; copy fixes are safe now, extraction only after QI-11-04. |
| QI-07-02 `run_study` CC 60 · QI-07-03 study schema | QI-07-04 H16 failed-cell honesty; QI-05-06 ranking allowlist | Failed-cell N and `_INDEX_PRIMARY_METRICS` are two edit sites in the same schema/execute pair. |
| QI-09-01 `results_overview` F-grade pair | QI-09-11 AO1 clamp; QI-09-10 three-bar vocabulary | Assistant honesty strings are table-shaped but not tabulated; QR-D/E copy is safe now, extraction is QR-C. |
| QI-12-01 / QI-12-02 (gate + envelope) | QI-11-03 AppTest mechanics; QI-13-01 "blocking" prose | The red week of 2026-09-05 was three findings interacting: no required checks × uncapped minor × framework-mechanic asserts. |

### 3.5 Prior-audit carry-over status (§A.3 → rows)

| Prior | Status re-verified by | Disposition in registry |
|---|---|---|
| C1 flatten leak | QI-4 §6.1 (AH1 probe tests present) | closed-verified (register §5.7; no row) |
| C2 Study replay path | QI-7 §6.3 (9 `test_ah2_*` pass) | closed-verified (register) |
| C3 OTF-matrix train peek | QI-5 §6.1 (`test_ah3_p1_*` family) | closed-verified (register) |
| H1 leftover keys | QI-6 §6.1 / QI-10 §6.2 managed set clears; **residual** QI-06-03, QI-10-01, QI-06-04, QI-10-03 | open (MG-01) |
| H2 promote pin roots | QI-7 §6.3 implemented; portable rewrite parked | locked (QI-07-10) |
| H3 `close` as level | QI-3 §6.7 (AH6 tests) | closed-verified (register) |
| H4 levels planes | QI-02-01, QI-14-04 | locked (MG-09) — docs residual QR-F |
| H5 `allow_all` disclosure | QI-04-02, QI-05-09 | **open High** (MG-02) QR-A |
| H6 `sl_first` × 3c | QI-4 §6.2 (`test_ah5_sl_first_3c_entry.py`) | closed-verified (register) |
| H7 cutoff-without-flatten | QI-04-03, QI-05-10, QI-13-07, QI-04-07 | locked (MG-03) — disclosure QR-A/F, lock-the-fork test QR-B |
| H8 battery omit-means-on | QI-06-08, QI-09-08, QI-13-09 | open (disclosure) / locked behavior (MG-05) |
| H9 `dataset_id` ingest story | QI-01-05 | locked (MG-10) |
| H10 Data-page fatal OHLCV | QI-01-03 (+ QI-01-07 test) | locked (MG-10) |
| H11 DST-crossing canonical CSV | QI-01-04 (+ QI-01-07 test) | locked (MG-10) — docs residual QR-F; do not unpark |
| H12 Focus over-statement | QI-05-04 | **open High** QR-A |
| H13 confirmatory copy | QI-05-05, QI-05-11, QI-13-03 | **open High** (MG-06) QR-A |
| H14 HTF stale developing levels | QI-03-06 | open (product decision + disclosure) QR-A |
| H15 OTF TZ UI vs API | QI-04-04 (+ QI-04-07 test, linked) | locked (singleton; test lives in MG-03) |
| H16 failed-cell / WFA-ignorant ranking | QI-05-06, QI-07-04 | open (MG-08) QR-A |
| M2 / M5 / M7 / M8 / M9 / M10 / M14 / M20 | QI-02-02 · QI-03-09 · QI-04-08 · QI-04-10 · QI-05-07 · QI-05-08 · QI-06-06 + QI-09-10 · QI-04-07 | as per rows (M7, M14 partly locked) |
| L3 / L9 / L10 | QI-03-07 · QI-09-09 · QI-09-06 | open Low |
| W1 "no CI" / W2 packaging / W14 licence | QI-12 §6.3–6.5 closed *as written*; intent residual → QI-12-01 | closed-verified (register) + open (MG-13) |
| W3 type/lint | QI-12-05, QI-12-09 | open QR-B |
| W12 performance | QI-14-03, QI-14-09 | open (MG-18) |
| W15 page numbering | QI-10-06 | wont-fix (proposed) |
| `AUDIT_FINAL` §7 last row (goldens ≠ correctness) | QI-11-02 restates; not re-litigated | open QR-B (additive families) |

`AUDIT_FINAL` §4 Medium/Low items **not** re-verified by any slice were not imported as rows: the plan's §A.3 sentence ("QI-15 imports … verbatim with `disposition=carry-over`") conflicts with §7.5's closed disposition vocabulary and with §7.1 ("QI-15 never edits slice rows"). Resolution proposed here: they stay in `AUDIT_FINAL` as the SoT; QR-A's checklist (plan §3.4) requires each QR-A PR to cite the AUDIT M/L id it closes. No new rows were invented.

Slice `prior_id` values that are **not** `C*/H*/M*/L*` / `W*` (§3.3 vocabulary) are left as written (QI-15 does not edit slice fields): `plan §4.4 H-0` (QI-11-03, QI-12-02), `plan §4.4 H-0b` (QI-11-01, QI-12-04), `plan §4.4 H-C` (QI-12-07), `AUDIT_FINAL §7 last row` (QI-11-02). They are plan-hypothesis / goldens-identity cross-refs, not AUDIT finding IDs. Six rows use the literal `none`; empty `prior_id` means "no carry-over".

### 3.6 Full disposition index (all 134 rows)

Machine-readable SoT is `findings.csv`; this index is for review. Score blank = not scored (locked / duplicate / wont-fix).

| Row | Sev | Class | Disposition | WS | Merge group | Score |
|---|---|---|---|---|---|---:|
| QI-01-01 | M | Maint | open | QR-D | MG-22-page-monoliths | 2.0 |
| QI-01-02 | M | Maint | open | QR-C | — | 5.0 |
| QI-01-03 | M | Design | locked | QR-A | MG-10-ingest-forks-h9-h10-h11 | — |
| QI-01-04 | M | Design | locked | QR-F | MG-10-ingest-forks-h9-h10-h11 | — |
| QI-01-05 | M | Design | locked | QR-F | MG-10-ingest-forks-h9-h10-h11 | — |
| QI-01-06 | L | Maint | open | QR-C | — | 1.5 |
| QI-01-07 | M | Test | open | QR-B | MG-10-ingest-forks-h9-h10-h11 | 2.0 |
| QI-02-01 | M | Design | locked | QR-F | MG-09-levels-planes-h4 | — |
| QI-02-02 | M | Test | open | QR-B | — | 10.0 |
| QI-02-03 | M | UX | open | QR-E | — | 3.0 |
| QI-02-04 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-02-05 | M | UX | open | QR-E | MG-24-untyped-errors-at-boundary | 2.0 |
| QI-02-06 | L | Docs | open | QR-F | — | 3.0 |
| QI-02-07 | L | Maint | open | QR-C | MG-30-dead-non-product-paths | 1.0 |
| QI-02-08 | L | Maint | open | QR-C | — | 0.3 |
| QI-03-01 | H | Maint | open | QR-C | MG-19-generate-signals | 10.0 |
| QI-03-02 | H | Maint | open | QR-C | MG-19-generate-signals | 10.0 |
| QI-03-03 | H | Maint | open | QR-C | MG-17-hand-rolled-validators | 12.0 |
| QI-03-04 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-03-05 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-03-06 | M | Design | open | QR-A | — | 10.0 |
| QI-03-07 | L | Design | open | QR-C | MG-30-dead-non-product-paths | 1.0 |
| QI-03-08 | M | UX | open | QR-A | MG-11-da0-direction-disclosure | 4.0 |
| QI-03-09 | L | UX | open | QR-E | — | 1.0 |
| QI-03-10 | M | Maint | open | QR-C | MG-17-hand-rolled-validators | 3.3 |
| QI-03-11 | L | UX | open | QR-E | — | 1.0 |
| QI-03-12 | M | UX | open | QR-D | MG-01-h1-leftover-lifecycle | 2.4 |
| QI-04-01 | H | Maint | open | QR-C | MG-18-simulate-trades | 9.6 |
| QI-04-02 | H | UX | open | QR-A | MG-02-allow-all-disclosure-h5 | 12.0 |
| QI-04-03 | M | Design | locked | QR-A | MG-03-cutoff-fork-h7 | — |
| QI-04-04 | M | Design | locked | QR-A | — | — |
| QI-04-05 | M | Maint | open | QR-D | MG-22-page-monoliths | 0.8 |
| QI-04-06 | M | UX | open | QR-A | MG-02-allow-all-disclosure-h5 | 6.0 |
| QI-04-07 | M | Test | open | QR-B | MG-03-cutoff-fork-h7 | 6.0 |
| QI-04-08 | M | Design | locked | QR-E | — | — |
| QI-04-09 | L | Maint | open | QR-C | MG-18-simulate-trades | 1.6 |
| QI-04-10 | L | Docs | open | QR-A | — | 1.6 |
| QI-05-01 | H | Maint | open | QR-C | MG-20-walk-forward | 8.0 |
| QI-05-02 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-05-03 | M | Maint | open | QR-C | — | 3.0 |
| QI-05-04 | H | UX | open | QR-A | — | 12.0 |
| QI-05-05 | H | UX | open | QR-A | MG-06-confirmatory-copy-h13 | 8.0 |
| QI-05-06 | M | UX | open | QR-A | MG-08-study-ranking-h16 | 1.0 |
| QI-05-07 | M | UX | open | QR-A | — | 2.0 |
| QI-05-08 | M | UX | open | QR-A | — | 4.0 |
| QI-05-09 | H | UX | open | QR-A | MG-02-allow-all-disclosure-h5 | 4.0 |
| QI-05-10 | M | Design | locked | QR-F | MG-03-cutoff-fork-h7 | — |
| QI-05-11 | M | Docs | duplicate | QR-F | MG-06-confirmatory-copy-h13 | — |
| QI-05-12 | M | Maint | open | QR-A | MG-24-untyped-errors-at-boundary | 1.6 |
| QI-05-13 | L | Maint | open | QR-F | — | 3.0 |
| QI-05-14 | L | Maint | open | QR-C | MG-29-private-cross-module-imports | 0.5 |
| QI-05-15 | L | Maint | open | QR-E | — | 2.0 |
| QI-06-01 | H | Maint | open | QR-C | MG-17-hand-rolled-validators | 8.0 |
| QI-06-02 | M | Maint | open | QR-C | — | 2.0 |
| QI-06-03 | M | **Defect** | open | QR-A | MG-01-h1-leftover-lifecycle | 2.0 |
| QI-06-04 | M | Maint | open | QR-C | MG-01-h1-leftover-lifecycle | 0.7 |
| QI-06-05 | M | Maint | open | QR-C | MG-16-import-boundary-mechanization | 4.7 |
| QI-06-06 | M | Design | locked | QR-E | MG-12-three-integrity-bars-m14 | — |
| QI-06-07 | M | UX | open | QR-E | MG-24-untyped-errors-at-boundary | 2.0 |
| QI-06-08 | M | Docs | open | QR-A | MG-05-omit-means-on-disclosure-h8 | 6.0 |
| QI-06-09 | M | Security | open | QR-A | — | 3.2 |
| QI-06-10 | M | Maint | open | QR-C | — | 1.0 |
| QI-06-11 | L | Maint | open | QR-C | MG-29-private-cross-module-imports | 2.0 |
| QI-06-12 | L | Test | open | QR-B | MG-15-coverage-debt | 2.0 |
| QI-07-01 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-07-02 | M | Maint | open | QR-C | — | 2.0 |
| QI-07-03 | M | Maint | open | QR-C | MG-17-hand-rolled-validators | 3.0 |
| QI-07-04 | M | UX | open | QR-A | MG-08-study-ranking-h16 | 6.0 |
| QI-07-05 | M | UX | open | QR-A | — | 3.0 |
| QI-07-06 | M | UX | open | QR-A | — | 4.0 |
| QI-07-07 | M | Maint | open | QR-C | — | 3.0 |
| QI-07-08 | M | Maint | open | QR-C | MG-17-hand-rolled-validators | 2.0 |
| QI-07-09 | L | Security | open | QR-G | MG-31-security-scan-gaps | 1.0 |
| QI-07-10 | L | Design | locked | — | — | — |
| QI-08-01 | M | Maint | open | QR-C | — | 3.0 |
| QI-08-02 | M | Maint | open | QR-C | MG-16-import-boundary-mechanization | 2.0 |
| QI-08-03 | M | **Defect** | open | QR-A | MG-24-untyped-errors-at-boundary | 2.0 |
| QI-08-04 | M | Maint | open | QR-C | — | 2.0 |
| QI-08-05 | M | UX | open | QR-E | — | 4.0 |
| QI-09-01 | M | Maint | open | QR-C | — | 2.0 |
| QI-09-02 | M | Maint | open | QR-C | — | 2.0 |
| QI-09-03 | M | Maint | open | QR-D | MG-22-page-monoliths | 1.0 |
| QI-09-04 | M | Test | open | QR-B | MG-15-coverage-debt | 4.0 |
| QI-09-05 | M | Docs | open | QR-F | MG-16-import-boundary-mechanization | 4.0 |
| QI-09-06 | L | Security | open | QR-A | — | 1.0 |
| QI-09-07 | L | UX | open | QR-E | — | 1.0 |
| QI-09-08 | M | Design | locked | QR-A | MG-05-omit-means-on-disclosure-h8 | — |
| QI-09-09 | L | Design | open | QR-E | — | 1.0 |
| QI-09-10 | L | UX | open | QR-E | MG-12-three-integrity-bars-m14 | 2.0 |
| QI-09-11 | M | UX | open | QR-E | — | 2.0 |
| QI-10-01 | M | **Defect** | open | QR-A | MG-01-h1-leftover-lifecycle | 5.0 |
| QI-10-02 | M | Docs | duplicate | QR-F | MG-01-h1-leftover-lifecycle | — |
| QI-10-03 | M | Maint | open | QR-D | MG-01-h1-leftover-lifecycle | 3.3 |
| QI-10-04 | M | UX | open | QR-E | — | 8.0 |
| QI-10-05 | M | Test | open | QR-B | MG-26-apptest-harness | 4.0 |
| QI-10-06 | L | Docs | wont-fix | — | — | — |
| QI-10-07 | L | Maint | open | QR-C | — | 1.0 |
| QI-10-08 | L | Maint | open | QR-B | MG-26-apptest-harness | 1.0 |
| QI-11-01 | M | Test | open | QR-B | MG-15-coverage-debt | 12.0 |
| QI-11-02 | M | Test | open | QR-B | MG-18-simulate-trades | 5.0 |
| QI-11-03 | M | Test | open | QR-B | MG-26-apptest-harness | 4.8 |
| QI-11-04 | M | Test | open | QR-B | MG-18-simulate-trades | 4.0 |
| QI-11-05 | L | Test | open | QR-B | — | 1.0 |
| QI-11-06 | L | Test | open | QR-B | — | 2.0 |
| QI-12-01 | H | **Defect** | open | QR-G | MG-13-ci-gate-reality | 20.0 |
| QI-12-02 | H | **Defect** | open | QR-G | MG-14-dependency-envelope | 20.0 |
| QI-12-03 | M | Docs | open | QR-G | MG-14-dependency-envelope | 6.0 |
| QI-12-04 | M | Test | open | QR-B | MG-15-coverage-debt | 2.0 |
| QI-12-05 | M | Maint | open | QR-B | — | 6.0 |
| QI-12-06 | M | Security | open | QR-G | MG-31-security-scan-gaps | 8.0 |
| QI-12-07 | M | Maint | open | QR-B | MG-16-import-boundary-mechanization | 10.0 |
| QI-12-08 | M | Security | open | QR-G | MG-14-dependency-envelope | 2.0 |
| QI-12-09 | L | Design | open | QR-B | — | 0.5 |
| QI-12-10 | M | Docs | open | QR-F | MG-13-ci-gate-reality | 4.0 |
| QI-13-01 | H | Docs | open | QR-F | MG-13-ci-gate-reality | 8.0 |
| QI-13-02 | M | Docs | open | QR-F | — | 8.0 |
| QI-13-03 | M | Docs | open | QR-F | MG-06-confirmatory-copy-h13 | 4.0 |
| QI-13-04 | M | Docs | open | QR-F | MG-01-h1-leftover-lifecycle | 8.0 |
| QI-13-05 | M | Docs | open | QR-F | — | 2.0 |
| QI-13-06 | M | Maint | open | QR-F | MG-16-import-boundary-mechanization | 8.0 |
| QI-13-07 | M | Docs | open | QR-F | MG-03-cutoff-fork-h7 | 10.0 |
| QI-13-08 | M | Docs | open | QR-F | MG-11-da0-direction-disclosure | 4.0 |
| QI-13-09 | M | Docs | open | QR-F | MG-05-omit-means-on-disclosure-h8 | 6.0 |
| QI-13-10 | L | Docs | open | QR-F | — | 3.0 |
| QI-14-01 | M | Docs | open | QR-B | MG-27-cai-baseline-stale | 2.0 |
| QI-14-02 | M | Docs | open | QR-F | MG-27-cai-baseline-stale | 2.0 |
| QI-14-03 | M | Design | open | QR-E | MG-18-simulate-trades | 4.0 |
| QI-14-04 | M | Design | locked | QR-F | MG-09-levels-planes-h4 | — |
| QI-14-05 | M | Maint | open | QR-C | MG-19-generate-signals | 5.0 |
| QI-14-06 | M | Maint | open | QR-E | — | 3.0 |
| QI-14-07 | L | Docs | open | QR-F | MG-27-cai-baseline-stale | 1.0 |
| QI-14-08 | L | Test | open | QR-B | MG-27-cai-baseline-stale | 1.0 |
| QI-14-09 | L | Maint | open | QR-C | MG-18-simulate-trades | 1.6 |
| QI-14-10 | L | Maint | open | QR-E | MG-20-walk-forward | 1.0 |

---

## 4. Scoring (§7.3)

`score = severity_weight × confidence_weight × blast_radius_count × (1 / fix_cost_class)`; Critical 8 / High 4 / Medium 2 / Low 1; Verified 1.0 / Strong 0.8 / Moderate 0.5 / Speculative 0.2. Plan §7.3 has no `n/a` weight: the one **open** `confidence=n/a` row (QI-12-09, Design limitation, `locked_by=none`) uses **0.5** (same as Moderate — `n/a` is a classification marker, not Verified evidence). Locked `n/a` rows are not scored. No Moderate/Speculative rows exist. `blast_radius_count` is the hand-counted number of distinct composers, pages, or CLI verbs named in the row's `blast_radius` (min 1). Fix-cost class: **1** isolated/additive (copy, `help=`, docs, tests, settings, tooling config) · **2** one module, golden-gated (single-function extraction; page split; additive managed keys) · **3** cross-module or contract amendment (registries, `app_state` split, Signals → `build_setup_config`) · **4** architecture (none assigned — no open row proposes an architecture change; composer collapse is locked). Scores are stored at **1 decimal** (`2/3 → 0.7`, `10/3 → 3.3`, `14/3 → 4.7`, `1/3 → 0.3`). Some integer `(blast, cost)` pairs collide; the §4.1 factor column is the disambiguation for every row with score ≥ 5.0. Scores order the backlog; they do **not** override §9.2 sequencing.

### 4.1 Top open rows by score (all 33 with score ≥ 5.0)

| Rank | Score | Row | Sev · Conf · BR · Cost | WS | Group | One line |
|---:|---:|---|---|---|---|---|
| 1 | 20.0 | QI-12-02 | H · V · 5 · 1 | QR-G | MG-14 | No constraints/lockfile; accidental pandas-major split; no Dependabot |
| 1 | 20.0 | QI-12-01 | H · V · 5 · 1 | QR-G | MG-13 | `main` has no required status checks; red PRs merge |
| 3 | 12.0 | QI-11-01 | M · V · 6 · 1 | QR-B | MG-15 | 14 modules < 70 %; `levels/common` untested |
| 3 | 12.0 | QI-05-04 | H · V · 3 · 1 | QR-A | — | H12 Focus ≠ Admit banner sentence |
| 3 | 12.0 | QI-04-02 | H · V · 3 · 1 | QR-A | MG-02 | H5 `allow_all` Policy widget has no `help=` |
| 3 | 12.0 | QI-03-03 | H · V · 6 · 2 | QR-C | MG-17 | `validate_setup_config` CC 69 hand-rolled |
| 7 | 10.0 | QI-13-07 | M · V · 5 · 1 | QR-F | MG-03 | Help Session-close H2 omits the headless fork |
| 7 | 10.0 | QI-12-07 | M · V · 5 · 1 | QR-B | MG-16 | No import-linter; chains and lazy Streamlit invisible |
| 7 | 10.0 | QI-03-06 | M · V · 5 · 1 | QR-A | — | H14 HTF+3c developing-level staleness undisclosed |
| 7 | 10.0 | QI-03-02 | H · V · 5 · 2 | QR-C | MG-19 | 3c detectors F-grade, duplicated assembly |
| 7 | 10.0 | QI-03-01 | H · V · 5 · 2 | QR-C | MG-19 | `generate_signals` CC 120 |
| 7 | 10.0 | QI-02-02 | M · V · 5 · 1 | QR-B | — | §5.5 PIT columns lack generated append-FS tests |
| 13 | 9.6 | QI-04-01 | H · S · 6 · 2 | QR-C | MG-18 | `simulate_trades` CC 133, P7 alone F |
| 14 | 8.0 | QI-13-06 | M · V · 4 · 1 | QR-F | MG-16 | AGENT_GUIDE 87-line prose rule ledger with rotting cites |
| 14 | 8.0 | QI-13-04 | M · V · 4 · 1 | QR-F | MG-01 | ARCHITECTURE key table misses Validation/Portfolio |
| 14 | 8.0 | QI-13-02 | M · V · 4 · 1 | QR-F | — | README still says five triggers |
| 14 | 8.0 | QI-13-01 | H · V · 2 · 1 | QR-F | MG-13 | ROADMAP/plan say QI Not started; "blocking on red" |
| 14 | 8.0 | QI-12-06 | M · V · 4 · 1 | QR-G | MG-31 | No bandit / pip-audit / Action pins |
| 14 | 8.0 | QI-10-04 | M · S · 5 · 1 | QR-E | — | "diagnostic, not proof" only on Validation/Report |
| 14 | 8.0 | QI-06-01 | H · V · 4 · 2 | QR-C | MG-17 | `validate_run_spec` CC 104 = 27.5 % of `api.py` |
| 14 | 8.0 | QI-05-05 | H · V · 2 · 1 | QR-A | MG-06 | H13 `st.success` on p ≤ 0.05 |
| 14 | 8.0 | QI-05-01 | H · V · 4 · 2 | QR-C | MG-20 | `run_walk_forward_sl_tp` CC 50 |
| 23 | 6.0 | QI-13-09 | M · V · 3 · 1 | QR-F | MG-05 | H8 omit-means-on absent from USER_GUIDE/ASSUMPTIONS |
| 23 | 6.0 | QI-12-05 | M · V · 3 · 1 | QR-B | — | No type checker (164 mypy strict / 1,421 pyright) |
| 23 | 6.0 | QI-12-03 | M · V · 3 · 1 | QR-G | MG-14 | `requirements.txt` vs `pyproject` two SoTs |
| 23 | 6.0 | QI-07-04 | M · V · 3 · 1 | QR-A | MG-08 | H16 Failed section missing in overview/rollup MD |
| 23 | 6.0 | QI-06-08 | M · V · 3 · 1 | QR-A | MG-05 | H8 CLI/API disclosure |
| 23 | 6.0 | QI-04-07 | M · V · 3 · 1 | QR-B | MG-03 | H7/H15 lock-the-fork tests absent |
| 23 | 6.0 | QI-04-06 | M · V · 3 · 1 | QR-A | MG-02 | DA1 diagnostic discarded on Composer A |
| 30 | 5.0 | QI-10-01 | M · V · 5 · 2 | QR-A | MG-01 | H1 dataset-switch clear list narrower than AH4 |
| 30 | 5.0 | QI-14-05 | M · V · 5 · 2 | QR-C | MG-19 | `generate_signals` row-wise pandas limiter |
| 30 | 5.0 | QI-11-02 | M · V · 5 · 2 | QR-B | MG-18 | no flatten-on / 3c / BE golden family |
| 30 | 5.0 | QI-01-02 | M · V · 5 · 2 | QR-C | — | `local_store.save_dataset` E-grade |

29 rows score > 5.0; four-way tie at 5.0 (first-pass table omitted QI-10-01). Full ordering: sort `findings.csv` by `score` descending (119 scored rows).

### 4.2 Score mass per workstream (open rows)

| WS | rows | Σ score | Reading |
|---|---:|---:|---|
| QR-A | 21 | 98.4 | Many cost-1 disclosure rows; four High carry-overs (H5 ×2, H12, H13) |
| QR-B | 19 | 79.3 | Dominated by coverage debt, import-linter, PIT tests, lock-the-fork tests |
| QR-C | 32 | 113.8 | Six High F-grade orchestrators; long tail of cost-2 extractions |
| QR-D | 10 | 14.5 | Page splits score low individually (BR 1, cost 2) but gate AppTest coverage |
| QR-E | 15 | 37.0 | Operability/legibility; W12 acceleration sits here per template |
| QR-F | 16 | 78.0 | Help-surface drift is cheap and broad (BR 2–5, cost 1) |
| QR-G | 6 | 57.0 | Two 20-point Verified defects; settings/config only |

---

## 5. Views (§7.4)

### 5.1 Heatmap — module group × ISO 25010 characteristic (count / max severity)

Counted from each row's `iso25010` tokens (a row with two tokens counts in two cells). Module group = owning slice.

| Module group | functional_suitability | reliability | usability | maintainability | performance_efficiency | compatibility | security | portability | rows |
|---|---|---|---|---|---|---|---|---|---:|
| Data/ingest/store | 3 / M | 1 / M | 1 / M | 4 / M | — | 1 / L | — | — | 7 |
| Levels/PIT | 2 / M | 1 / M | 4 / M | 4 / M | — | 2 / M | — | — | 8 |
| Setup/signals/OTF | 1 / M | 1 / M | 5 / M | 7 / **H** | — | 1 / M | — | — | 12 |
| Execution engine | 5 / **H** | 1 / M | 4 / **H** | 4 / **H** | — | 2 / M | — | — | 10 |
| Analytics/batteries | 6 / **H** | 1 / M | 7 / **H** | 7 / **H** | — | 2 / M | — | — | 15 |
| API/CLI/bundles/report/bridge | 3 / M | 3 / M | 3 / M | 7 / **H** | — | 1 / M | 2 / M | — | 12 |
| Study system | 2 / M | — | 3 / M | 6 / M | — | 1 / L | 1 / L | 1 / L | 10 |
| Trade journal | — | 1 / M | 2 / M | 3 / M | — | 1 / M | — | — | 5 |
| Assistant/voice | 2 / M | 1 / M | 4 / M | 6 / M | — | 1 / M | 2 / L | — | 11 |
| UI/session_state | 1 / M | 1 / M | 2 / M | 5 / M | — | 2 / M | — | 1 / L | 8 |
| Test suite | 2 / M | 1 / M | — | 6 / M | 1 / L | 1 / M | — | — | 6 |
| Tooling/CI/security | — | 4 / **H** | — | 9 / **H** | — | 5 / **H** | 2 / M | 2 / M | 10 |
| Docs/contracts | 2 / M | 1 / **H** | 6 / M | 4 / **H** | — | 2 / M | — | — | 10 |
| Performance (cross-cutting) | — | — | — | 4 / M | 10 / M | 1 / M | — | — | 10 |
| **All** | 29 / H | 17 / H | 41 / H | **76 / H** | 11 / M | 23 / H | 7 / M | 4 / M | 134 |

Reading: **maintainability is the dominant characteristic (76 rows) and the only one that is High in six groups**; the High *functional_suitability / usability* cells sit in exactly the two groups the audit already flagged (execution, analytics) and are honesty-surface rows (H5/H12/H13), not fill defects. Security is Medium-capped and concentrated in the tooling group (missing scanners) rather than in product code. Performance is Medium-only (W12 is a cost, not a defect). No group is Critical.

### 5.2 Hot-spot matrix — top 30 functions by CC (re-measured on `0b2c451`)

CC/MI: radon 6.0.1 on this tree (identical F-grade set and integers to QI-0). Churn: commits touching the file in the last 400 `main` commits *at `0b2c451`* — this window now contains the QI PRs, so page/Study churn reads lower than QI-0's window (e.g. `pages/15_Studies.py` 10 vs 27); treat as relative. Coverage: QI-0 §A.4 per-module branch coverage. Mutation: QI-11 §2.2 (four sampled files). "Findings naming the function" = rows whose `files_symbols` cite the symbol; "rows naming the file" = any row citing the module.

| # | Function | CC | Module MI | Churn | Cov % | Mutation % killed | Findings naming the function | Rows naming file | Structural owner |
|---|---|---:|---:|---:|---:|---|---|---:|---|
| 1 | `reporting.py::build_markdown_report` | 152 | 0.00 | 1 | 86 | — | QI-06-02 | 3 | QR-C |
| 2 | `engine/backtest.py::simulate_trades` | 133 | 12.95 | 4 | 95 | 66.7 raw / 72.7 adj | QI-04-01, QI-04-02, QI-04-08, QI-08-02, QI-11-04, QI-14-03 | 9 | QR-C (after QR-B) |
| 3 | `engine/signals.py::generate_signals` | 120 | 0.00 | 3 | 84 | — | QI-03-01, QI-03-02, QI-03-06, QI-03-09, QI-11-02, QI-14-02, QI-14-05 | 9 | QR-C (after QR-B) |
| 4 | `assistant/results_overview.py::_format_scalar_for_claim` | 120 | 0.00 | 0 | 84 | — | QI-09-01 | 1 | QR-C |
| 5 | `api.py::validate_run_spec` | 104 | 0.00 | 18 | 81 | — | QI-01-06, QI-06-01, QI-07-03, QI-07-05 | 18 | QR-C |
| 6 | `research_bundle.py::load_research_bundle` | 75 | 3.79 | 2 | 87 | — | QI-06-04, QI-06-06, QI-06-09 | 8 | QR-C |
| 7 | `assistant/results_overview.py::compose_deterministic_replies` | 73 | 0.00 | 0 | 84 | — | QI-09-01 | 1 | QR-C |
| 8 | `pages/15_Studies.py::_draft_from_builder_widgets` | 73 | 0.00 | 10 | n/a | — | QI-07-01 | 2 | QR-D |
| 9 | `setup.py::validate_setup_config` | 69 | 14.80 | 7 | 89 | — | QI-03-03 | 3 | QR-C |
| 10 | `research_bundle.py::build_research_bundle` | 63 | 3.79 | 2 | 87 | — | QI-06-04, QI-14-07 | 8 | QR-C |
| 11 | `study/builder.py::hydrate_study_draft` | 62 | 0.00 | 5 | 84 | — | QI-07-07 | 3 | QR-C |
| 12 | `study/execute.py::run_study` | 60 | 0.00 | 6 | 76 | — | QI-07-02 | 2 | QR-C |
| 13 | `engine/signals_3c.py::detect_3c_setups_with_trigger_timeframe` | 59 | 23.90 | 0 | 86 | — | QI-03-02, QI-03-06 | 2 | QR-C (S3 math locked) |
| 14 | `pages/15_Studies.py::_render_build` | 59 | 0.00 | 10 | n/a | — | QI-07-01 | 2 | QR-D |
| 15 | `engine/signals_3c.py::detect_3c_setups` | 55 | 23.90 | 0 | 86 | — | QI-03-02 | 2 | QR-C (S3 math locked) |
| 16 | `assistant/explainer.py::_derive_caveats` | 52 | 0.00 | 0 | 91 | — | QI-09-02 | 1 | QR-C |
| 17 | `assistant/help_corpus.py::score_corpus_chunk` | 51 | 17.39 | 2 | 83 | — | QI-09-02 | 2 | QR-C |
| 18 | `api.py::run_validation` | 51 | 0.00 | 18 | 81 | — | QI-06-01, QI-06-08 | 18 | QR-C |
| 19 | `analytics/walk_forward.py::run_walk_forward_sl_tp` | 50 | 21.10 | 0 | 88 | 50 raw / 60 adj | QI-05-01, QI-11-04 | 4 | QR-C (after QI-11-04) |
| 20 | `pages/3_Setup_Builder.py::_sync_editor_widget_state` | 47 | 0.00 | 2 | n/a | — | QI-03-04 | 6 | QR-D |
| 21 | `study/schema.py::_validate_factors` | 46 | 0.00 | 19 | 85 | — | QI-07-03 | 5 | QR-C |
| 22 | `assistant/orchestrator.py::handle_results_turn` | 40 | 0.00 | 0 | 71 | — | QI-09-02 | 2 | QR-C |
| 23 | `api.py::run_experiment` | 40 | 0.00 | 18 | 81 | — | QI-06-01, QI-06-08, QI-13-09 | 18 | QR-C |
| 24 | `pages/15_Studies.py::_render_inspect` | 40 | 0.00 | 10 | n/a | — | QI-07-01 | 2 | QR-D |
| 25 | `classic_proposal.py::validate_classic_proposal` | 39 | 28.20 | 0 | 67 | — | — (file: QI-06-05, QI-06-12) | 2 | QR-B coverage first |
| 26 | `pages/2_Levels.py::_sync_levels_widget_state` | 39 | 7.24 | 3 | n/a | — | QI-02-04 | 6 | QR-D |
| 27 | `study/promote.py::_compose_promoted_draft` | 37 | 16.79 | 5 | 84 | — | — (file: QI-07-10 locked) | 1 | none (E-grade, tested) |
| 28 | `journal/report.py::_q4_q6` | 36 | 0.00 | 7 | 77 | — | QI-08-04 | 3 | QR-C |
| 29 | `assistant/results_qa.py::_recover_results_reply` | 36 | 21.30 | 0 | 87 | — | — (file: QI-09-02) | 1 | QR-C (with QI-09-02) |
| 30 | `pages/15_Studies.py::_render_inspect_peek` | 36 | 0.00 | 10 | n/a | — | — (file: QI-07-01) | 2 | QR-D (with QI-07-01) |

Refactor priority (QR-C order, after QR-B gates): **(1)** `validate_setup_config` → `validate_run_spec` → `study.schema` as one declarative-table pattern (MG-17; no goldens involved, fail-closed outcomes byte-comparable); **(2)** `build_markdown_report` templating (no goldens; markdown byte-comparable on fixtures); **(3)** `generate_signals` TF-prep / zone-admission / trigger-dispatch extraction (golden-gated; S3/DA0 math untouched) then 3c row-mapper sharing; **(4)** `simulate_trades` P7 extraction behind `sim_core` only after MG-18 gates (flatten-on / 3c / BE golden families, mutation baseline ≥ 70 % on own-file suite); **(5)** `run_walk_forward_sl_tp` after own-file asserts (QI-11-04); **(6)** bundle key registry; **(7)** assistant tables; **(8)** Study `run_study` / builder / observatory; **(9)** journal helpers. Page functions (#8, #14, #20, #24, #26, #30) are QR-D.

### 5.3 Composer-parity ledger

Every UI / API / CLI / Study / Assistant divergence recorded by the slices. "Locked" means the *behavior* fork is an `AUDIT_FINAL` §5 / AH §2 premise; only disclosure or lock-the-fork tests are QR work.

| # | Divergence | Composers | Status on audited tree | `locked_by` | Row(s) | Disposition |
|---|---|---|---|---|---|---|
| P1 | Legacy-primary UI installs bars with fatal OHLCV codes then warns; API/CLI/Study/Assistant reject (H10) | UI vs headless | fork present | AH §2.1 parked composer forks; S1 no auto-dedup | QI-01-03, QI-01-07 | locked; test QR-B |
| P2 | Mixed-offset canonical CSV: raw pandas `ValueError` (UI shows `utc=True` hint) (H11) | all (same reject, untyped) | parked | AH §8 H11 | QI-01-04, QI-01-07 | locked; test QR-B |
| P3 | `dataset_id` omits ingestion mode; same parent bars share levels across modes (H9) | store / identity | as locked | `AUDIT_FINAL` §5.1 item 9; AH §2 item 9 | QI-01-05 | locked; docs QR-F |
| P4 | Five `format_profile` literals kept in lockstep by hand | Data page · API · Studies builder | equal today | none | QI-01-06 | open QR-C |
| P5 | Three levels default planes; Study Advanced-OFF pops keys then product-fills; sparse YAML enables `prev30m_vwap` (H4) | Levels page · API · Study · Assistant · CAI | as locked | AH §2 item 9 | QI-02-01, QI-14-04 | locked; docs QR-F |
| P6 | Tick-refusal message text/timing differs (library first-family vs API preflight vs Study named-token) | Levels page · API · Study | fail-closed in all three | AP/RP refuse (behavior) — message not locked | QI-02-03 | open QR-E |
| P7 | Classic Signals bypasses `build_setup_config`; page-6 duplicates 3c normalizer; Study/API second assembly layer | Signals page · API · Study · Assistant | key drift risk (AO1 fork) | AH §2 items 1–2 (do not collapse) | QI-03-10 | open QR-C |
| P8 | HTF+3c developing-partner level is early-window price vs completed HTF OHLC (H14) | all composers using 3c + non-base TF | unchanged since audit | `AUDIT_FINAL` H14 open; §5.3 described | QI-03-06 | open QR-A (disclosure; snap = CTO decision) |
| P9 | Direction widget lacks DA0 disclosure (`touch`+`both`+`single_position` long-only) | Setup Builder · Signals · Help | disclosed only on Backtest/docs | DA0 (behavior) | QI-03-08, QI-13-08 | open QR-A/QR-F |
| P10 | `allow_all` overlap inflates N; skip table empty; no widget `help=` (H5) | Backtest · Grid | undisclosed on page | AH §2.1 default locked; presentation not | QI-04-02, QI-05-09 | **open High QR-A** |
| P11 | Cutoff-without-flatten: UI forces `None`, YAML applies (H7) | Backtest/Grid UI vs API/CLI/Study | as locked | `AUDIT_FINAL` §5.1 item 6 | QI-04-03, QI-05-10, QI-13-07, QI-04-07 | locked; Help QR-F; test QR-B |
| P12 | OTF/Admit clock: UI `exchange_timezone`, headless `inst.exchange_tz` (H15) | Backtest UI vs headless | as locked | `AUDIT_FINAL` §5.1 item 5 | QI-04-04, QI-04-07 | locked; test QR-B |
| P13 | Backtest OHLCV frame: UI `levels`-if-present else `data`; headless always levels frame | UI vs `run_experiment` | as locked (QI-4 parity table) | `AUDIT_FINAL` §5.1 item 7 | no row (positive verification) | locked, no action |
| P14 | DA1 `direction_collision_diagnostic` returned by API, discarded by page 7 | UI vs API/Study | present | none | QI-04-06 | open QR-A |
| P15 | Focus fills ≠ Admit fills under `single_position`; banner is subset-replay only (H12) | Time · Validation · Backtest | reproduced (substitution) | AH §2 item 5 (status) | QI-05-04 | **open High QR-A** |
| P16 | Study ranking rejects `wfa_median_test_expectancy_r` as `primary_metric` (H16) | Study index vs WFA | present | none | QI-05-06 | open QR-A |
| P17 | Omitted battery `enabled` ⇒ on for api/CLI/assistant; Study emit explicit false; nested OTF matrix default-off (H8) | API · CLI · Assistant vs Study | as locked; disclosure uneven | AH §2 item 9; §2.1 parked | QI-06-08, QI-09-08, QI-13-09 | open (disclosure) / locked (behavior) |
| P18 | Three integrity bars (page-12 schema-only · assistant hash-fail-closed · open-exact) unlabeled on pages 12/14 | Bundles · Assistant | bars distinct, unlabeled | AH §2 item 8; §5.4 | QI-06-06, QI-09-10 | locked bars; labels QR-E |
| P19 | CLI `run` wraps actionable message in a traceback; `study`/`journal` CLIs exit typed | CLI verbs | present | none | QI-06-07 | open QR-E |
| P20 | Hand-authored Study YAML with Quantower HE + omitted `ingestion_mode` runs as primary (a different experiment) | Study CLI vs Builder | Builder warns; validate does not | AH §2 item 9 (omit=primary) — detection not locked | QI-07-05 | open QR-A |
| P21 | `study expand` Replay line / emitted YAML do not say "not `study run`" | Study CLI vs docs | docs honest, CLI not | AH §2 item 7 (behavior) | QI-07-06 | open QR-A |
| P22 | Assistant Draft form clamps `min_valid_confluences` ≥ 1; YAML/API/Setup Builder allow 0 (AO1) | Assistant vs others | present | AO1 (behavior) | QI-09-11 | open QR-E |
| P23 | `--include-small-n` CLI help / `hidden_slice_count` are Q2-only; page 17 help complete | journal CLI vs page | present | none | QI-08-05 | open QR-E |
| P24 | Dataset-switch clear list ≠ AH4 managed set; `display_timezone` survives apply (H1 residual) | Data · Bundles · downstream pages | present (Verified defect) | none (AH4 closed named keys) | QI-10-01, QI-06-03 | open QR-A |

**Parity that holds (positive):** API ↔ CLI `canonical_bundle_hash` identity (QI-6 §6.3); UI-equivalent and assistant hash parity tests green; Study workers 1/2/4 identical per-cell hashes (QI-14 §6.3); `VALID_TRIGGERS` lockstep engine ↔ setup ↔ API (QI-3 §6.1); AO1 `min_valid=0` accepted by BSC / validate / API / Study expand (QI-3 §6.4); 15s-primary fail-closed identically on UI and API (QI-1 §6.2); `FATAL_OHLCV_CODES` single frozenset shared by page and API (QI-1 §6.8). None of these is a fill-correctness claim.

### 5.4 Contract-mechanization list

Prose rules (from `AGENT_GUIDE.md` / `ARCHITECTURE.md`, QI-13 §9 and QI-12 §2.6) that can become an `import-linter` contract, a test, or a type — with violations measured today.

| # | Prose rule | Mechanize as | Violations today | Rows | WS |
|---|---|---|---|---|---|
| C1 | `study/preview.py` must not import `execute` (RS-D8) | import-linter (`forbidden`, with `allow_indirect_imports` or layers for `expand → cli → cli_study`) | direct 0; **chain 1** (`expand → thesistester.cli → cli_study → execute`) + package-init eager `run_study` | QI-12-07, QI-13-06 | QR-B |
| C2 | `study/viewer.py` ↛ `cli_study` / `cli` / `execute` / `rollup` / `observatory` / Plotly / Streamlit (SV/SO) | import-linter | 0 (direct and chain) | QI-12-07 | QR-B |
| C3 | `study/observatory.py` ↛ `cli_study` / `execute` / Streamlit / Plotly (SO) | import-linter | 0 | QI-12-07 | QR-B |
| C4 | `study/launch.py` ↛ `viewer` (and ↛ `execute`, AH2/RS-D9) | import-linter | direct 0; **chain 1** (same `cli_study` function import) | QI-12-07 | QR-B |
| C5 | `study/admit_followup.py` ↛ execute/launch/viewer/cli/Streamlit (SAF) | import-linter | 0 | QI-12-07 | QR-B |
| C6 | Pages 15/16 / Build / Inspect must not **call** `run_study()` (RS-D9) | AST call-graph test (already exists in `tests/study`); not an import contract | 0 calls; note any `import thesistester.study.*` *loads* `execute` via `__init__` | QI-07 §2.2 | keep (QR-B documents) |
| C7 | Journal never calls `simulate_trades` / `compute_all_levels` (TJ) | import-linter `forbidden` on `engine.backtest`, `levels.all`, `engine.sim_core`; **not** on `engine.signals` (JS2 wrapper is legitimate) | call-ban 0; **package-init loads `engine.backtest`** via `journal/__init__` + private `engine.signals._classify_zone_triggers_detail` import | QI-08-02 | QR-C (slim init) + QR-B (contract) |
| C8 | Library is Streamlit-free except documented chrome (R18 / H-C) | import-linter layers: `thesistester` (minus allow-list) ↛ `streamlit` | **8 direct importers**: `app_state` (eager) + lazy `assistant.llm`, `assistant.voice.xai_realtime`, `classic_context`, `classic_ledger`, `classic_nav`, `classic_proposal`, `classic_record` | QI-06-05, QI-09-05, QI-12-07 | QR-C (split `app_state`) · QR-F (amend AIA-0/R18 wording) · QR-B (contract with explicit allow-list) |
| C9 | `sim_core` contains no admission / P&L (R22) | import-linter (`sim_core` ↛ `entry_window_policy`, `analytics.*`) + existing benches | 0 | QI-4 §6.3, QI-14 §6.2 | QR-B (cheap to encode) |
| C10 | Studies page ↛ `FORMAT_PROFILE_LABELS` from `builder` (R17 getattr rule) | import-linter | not re-run by QI-13; runtime labels are one object | QI-01-06 | QR-C (SoT extract) · QR-B (contract) |
| C11 | `ARCHITECTURE.md` session-key table = producer/consumer graph | test asserting table ⊇ literal `session_state["…"]` research keys and consumer columns | **16 table-not-code** (constant-aliased / API-written) · **4 consumers missing** (Validation ×3, Portfolio) · chrome keys only in CAI-5 | QI-13-04, QI-10-02, QI-10-03 | QR-D (registry) + QR-B (test) |
| C12 | `validation_summary()` shape frozen `{bootstrap, permutation, trade_count, grid_overfit}` | test on key set | 0 (held) | QI-05-13 | QR-B (one assert) |
| C13 | Four golden families cover default-on execution paths | golden family per default-on path (flatten-on, 3c filled/void, BE/trail, `same_bar_opposite_direction=legacy`) | **4 default-on paths without a family** | QI-11-02 | QR-B |
| C14 | PIT: every emitted level column is future-shock safe | generated append-FS test over all 59 columns | probe prefix-identical; **committed tests cover the R3 named set only** | QI-02-02 | QR-B |
| C15 | H7 / H15 / H10 / H11 forks are the shipped contract | lock-the-fork tests (fail if inverted) | **0 committed tests** for any of the four | QI-04-07, QI-01-07 | QR-B |
| C16 | Coverage floor 85 % (R9 88 %) | blocking `--cov-fail-under` at the measured level | measured **82 %**; floor informational | QI-12-04, QI-11-01 | QR-B (warn-first) |
| C17 | Annotated code is type-sound | `mypy` warn-first on `engine/` + `analytics/` | **164** strict errors / 34 files (`type-arg` 78) | QI-12-05 | QR-B |
| C18 | "CI jobs are blocking" | GitHub required status checks | **false** today (`protected: false`) | QI-12-01, QI-13-01 | QR-G |
| C19 | Broad `except` classified (83) | ruff `BLE001` allow-list or per-site comment | classified by slices: narrow-guard OK except QI-03-05 (traceback), QI-05-12 (swallows into empty frame), QI-08-03 (pdfminer leak) | QI-03-05, QI-05-12, QI-08-03 | QR-A/D fixes; QR-B rule later |
| C20 | Loop-variable capture (C1 class) | ruff `B023` | **4 hits** | QI-12-09 | QR-B (B family first) |
| C21 | `file:line` citations forbidden in living docs | link/cite checker | 7 unique cites (8 occurrences) in `AGENT_GUIDE.md` | QI-13-06 | QR-F |
| C22 | Help corpus allowlist paths frozen (HC rule 2) | existing `test_help_corpus` | 0 (held) | QI-9 §6.2, QI-13 §6.2 | keep |

Remaining ~70 "do not" sentences in `AGENT_GUIDE.md` (do not reopen series, do not regen goldens, do not invert locks) stay prose: they are governance, not code shape.

### 5.5 Control-gap table (QI-12 §2.1 with the finding IDs each missing control would have caught)

| Control | Present? | Cost | Would have caught / would gate | Rows |
|---|---|---|---|---|
| Required status checks on `main` (six existing job names) | **No** (`protected: false`) | settings-only | [#476](https://github.com/AccumuLatata/ThesisTester/pull/476), [#450](https://github.com/AccumuLatata/ThesisTester/pull/450) and the other merges on red; every future QR gate | QI-12-01, QI-13-01, QI-12-10 |
| Lockfile / `constraints.txt` (50 pins derivable) | No | low | Streamlit 1.63 pickup ([#478](https://github.com/AccumuLatata/ThesisTester/pull/478)); plotly 7 / pyarrow 25 on the app-install path | QI-12-02, QI-12-03 |
| Dependabot / Renovate with full-suite gate | No | low–med | same two drift events; stale `cryptography` / `jinja2` transitives | QI-12-02, QI-12-06 |
| Explicit pandas-major matrix axis | accidental (py3.10 = pandas 2.3.3) | low | `test_nullable_join_columns_stay_object_none` (#478); golden hash skip semantics | QI-12-02 |
| Streamlit minor cap or dedicated job | No | low | `AppTestError` on 2026-09-05; next `proto` / `set_value` change | QI-12-02, QI-11-03 |
| Coverage floor blocking at measured level | informational | low | six-point drift from R9 88 % → 82 % | QI-12-04, QI-11-01, QI-09-04, QI-06-12 |
| Type checker (warn-first, `engine/` + `analytics/`) | No | med | budget for QR-C extractions of `simulate_trades` / `generate_signals` / `validate_run_spec` | QI-12-05 (gates QI-04-01, QI-03-01, QI-06-01) |
| `bandit -ll` | No | low | SHA1 without `usedforsecurity`; `urlopen` review | QI-12-06, QI-07-09 |
| `pip-audit` (declared + transitive) | No | low | transitive advisories on long-lived VMs | QI-12-06 |
| `import-linter` (warn-first) | No | med | chains C1/C4, Streamlit re-entry C8, journal init C7 | QI-12-07, QI-06-05, QI-08-02, QI-09-05, QI-13-06 |
| Ruff family widening (B first) | No (R9 intentional) | med / family | `B023` loop-variable class (C1); `SIM115` open-without-context | QI-12-09 |
| Action SHA pins | No (`@v7` floating) | low | tag-move supply chain on the gate itself | QI-12-06 |
| Devcontainer ≡ CI (`pip install -e '.[dev]'`, XSRF on) | No | low | Codespaces off-envelope; CSRF-off forwarded port | QI-12-08, QI-12-03 |
| AppTest harness rules (isolate fixture; no `proto.*`; no disabled `set_value`; named keys) | partial (#478) | low | the 2026-09-05 red; any classic-page AppTest port | QI-11-03, QI-10-05, QI-10-08 |
| pytest markers (`unit/integration/golden/eval/benchmark/serial`) | No | low | `< 5 min` unit subset; xdist prerequisite | QI-11-05 |
| Mutation baseline (four sampled files) | No | med | `walk_forward` 50–60 %, `backtest` 66.7–72.7 % below the 70 % trigger | QI-11-04 |
| Golden families for default-on paths | 4 of 8 paths | med | flatten-on / 3c / BE / opposite-direction legacy identity before any P7 extraction | QI-11-02 |
| Session-key contract test | No | low | 4 missing consumers, 16 table-not-code names, next H1 leftover | QI-13-04, QI-10-03, QI-10-01 |
| Generated PIT append-FS over all columns | No (probe only) | low | a current-week leak into `pw*` / `pm*` columns | QI-02-02 |
| Lock-the-fork tests (H7/H15/H10/H11) | No | low | silent inversion of a locked admission by AH8 or a pandas minor | QI-04-07, QI-01-07 |
| CodeQL / secret scanning | unreadable (403) | med | none of the QI findings; leaked keys if any (none found) | QI-12-06 |

### 5.6 Architecture drift assessment (measured vs `ARCHITECTURE.md` boundaries)

| Boundary | Contract | Measured (slices) | Verdict | Rows |
|---|---|---|---|---|
| R9 packaging / lint / CI | `pip install -e .`; ruff clean; CI gates merges | ruff/format clean (368 files); editable-install job green; **no required checks**; `requirements.txt` ≠ `pyproject` resolve; pages `sys.path` bootstrap + blanket `E402` ignore | **Breached on the gate**, eroding on install SoT | QI-12-01, QI-12-03, QI-10-08 |
| R18 headless library (Streamlit-free; `api.py` thin facade) | library never imports Streamlit; `api.py` = typed facade | 1 eager + 7 lazy Streamlit importers; `api.py` is ~8 % facade / 36 % validation / 44 % composition; `validate_run_spec` CC 104 | **Breached** (Streamlit) · **eroding** (facade) | QI-06-05, QI-09-05, QI-12-07, QI-06-01 |
| R22 `sim_core` boundary | `sim_core` = BarData + bracket resolution only; acceleration must equal serial goldens | no admission / P&L in `sim_core` (QI-4, QI-14); orchestrator not shrunk (P7 alone F 45); R22 serial ruler reproduces | **Holds**; orchestrator debt is the QR-C item | QI-04-01, QI-14-09 |
| Two-composer contract (AH §2 items 1–2) | Composer A (pages) and Composer B (`run_experiment`) stay distinct; forks are locked, not hidden | forks present as locked (H7/H15/H10/H11/H4/H8/H9); disclosure uneven; Signals bypasses BSC | **Holds by lock**; disclosure eroding | MG-02/03/05/09/10, QI-04-04, QI-03-10 |
| AH4 restore lifecycle (managed keys clear; no page-12 hash) | managed set cleared on apply; three integrity bars distinct | managed set clears; **residual leftovers** (`otf_validation_*`, `skipped_signals`, `direction_collision_diagnostic`, `display_timezone`); dataset-switch clear list narrower than AH4 | **Eroding** (residual H1 class) | QI-06-03, QI-10-01, QI-10-03, QI-06-04 |
| RS Study import bans (preview/viewer/observatory/launch/admit_followup) | listed modules never import `execute` / Streamlit / Plotly | direct bans hold and are AST-tested; **chains** `expand → cli → cli_study` reach `execute`; package-init eager `run_study` | **Holds directly; eroding via chains** | QI-12-07, QI-13-06, QI-07 §2.2 |
| RS-D9 pages ↛ in-process `run_study()` | pages spawn detached CLI only | 0 calls; `spawn_launch` only; no auto-refresh/kill/retry | **Holds** | QI-7 §6.2 |
| TJ journal off the R18 engine path | journal never calls `simulate_trades` / `compute_all_levels`; no Streamlit in library | call-ban holds; **import graph eroded** (package-init loads `engine.backtest`; private `engine.signals` import) | **Eroding** | QI-08-02 |
| Assistant presentation-only (AIA-0) | no widgets / session writes in `thesistester/assistant/`; RUX layout frozen | 0 widgets; only `st.secrets` lazy fallback; RUX baseline 16 tests green | **Holds** (AIA-0 sentence needs the documented exception) | QI-09-05 |
| Levels PIT (`POINT_IN_TIME_GUARANTEES.md`) | every emitted column future-shock safe; `LEVEL_ENGINE_VERSION` discipline | 59/59 columns prefix-identical on two fixtures; version 11 unchanged; committed tests cover the R3 named set only | **Holds**; test coverage gap | QI-02-02 |
| Identity keys (`dataset_id`, `source_binding_key`, bundle hash) | stable across composers and pandas majors | API ↔ CLI ↔ UI-equivalent hashes equal; pandas-3 golden record matches; bindings partition by mode while `dataset_id` does not (H9, locked) | **Holds** | QI-01-05 (locked) |
| Help corpus freeze (HC rule 2) | seven allowlisted paths frozen; USER_GUIDE 25 H2s | exact match; 0 broken links | **Holds** | QI-13 §6.2–6.4 |
| Session-key contract table (`ARCHITECTURE.md`) | table = producer/consumer SoT | 162 literal keys vs 109 table names; 4 consumers missing; 16 constant-aliased names absent from code literals | **Eroding** | QI-13-04, QI-10-02 |
| Regression-safety framework (`ENGINEERING_PROPOSAL` §4 rule 9 "no merge on red") | red CI blocks merge | 37 merges on red through 2026-09-08; docs still say "blocking" | **Breached** (process), docs drift | QI-12-01, QI-13-01, QI-12-10 |

Three breaches (CI gate, Streamlit-in-library, "no merge on red" process), five eroding, seven holding. No locked *mathematical* contract (`AUDIT_FINAL` §5.1–5.4) is breached by shipped code; every locked item re-verified as "still describes shipped wiring".

### 5.7 Positive-verification register (do not re-audit in QR)

Consolidated from the fourteen §6 sections; each entry names the slice that holds the evidence. These are process / identity / status statements — **not** correctness claims about fills, metrics, or Studies.

**Audit carry-overs closed in code + probe tests**
- C1 flatten leak: per-candidate `entry_local_ts`; `empty_session_close_cap`; `tests/test_ah1_session_flatten.py` (QI-4 §6.1).
- C2 Study replay path / H2 pin roots: spec-parent-first search; 9 `test_ah2_*` (QI-7 §6.3).
- C3 OTF-matrix train peek: `test_ah3_p1_*` family; train sim uses `source_df.iloc[:split_bar]` (QI-5 §6.1).
- H3 / AH6 `close`-as-level: `BASE_COLUMNS` rejected; `tests/test_ah6_base_columns.py` (QI-3 §6.7).
- H6 / AH5 `sl_first` × 3c entry: `_path_after_entry`; `tests/test_ah5_sl_first_3c_entry.py` committed (QI-4 §6.2, §6.9).
- H1 *managed* keys: AH4 P1–P5 clear on apply; `bundle_import_omitted_data` set on dataset-less import (QI-6 §6.1, QI-10 §6.2).
- AH2 replay copy in `AGENT_GUIDE.md` / `STUDY_RUNNER.md` amended ("same bytes when the expand-time file exists; still `run_batch`; not `study run`") — §5.5 docs item closed (QI-13 §6.1).
- W1 CI / W2 packaging / W14 licence closed as written (QI-12 §6.3–6.5).

**Locked contracts re-verified as shipped wiring (status only)**
- AH §2.1 defaults unchanged: `exposure_policy="allow_all"`, `intrabar_model="sl_first"`, `flat_by_session_close=False` (QI-4 §6.11).
- `AUDIT_FINAL` §5.1 items 5–7 (H15 / H7 / backtest frame) still describe shipped wiring; not inverted (QI-4 §6.12, parity table).
- S1: 15s-primary misaligned minute dropped, never synthesized; native 1m never auto-deduped (QI-1 §6.2).
- S3 / DA0: `confirm_3bar` cannot be generated; simple HTF keeps `base_end` zones, 3c projects intra-window zones (QI-3 §6.2, §6.8).
- S5: WFA overlap-reject withholds stitched equity; fold construction not reopened (QI-5 §6.10).
- AP/RP: `typical_mvp_v1` unselectable on the product path; `_rolling_poc` not the product path; refuse without ticks (QI-2 §6.5–6.6).
- AH §2 item 8: page 12 stays schema-only; assistant/`complete_run` hash-fail-closed is a separate bar (QI-6 §6.2).
- RS-D2/RS-D9/SAF: pages never call `run_study()`; no auto-refresh/kill/retry; ToD is not a factor axis (QI-7 §6.2, §6.7).
- TJ6 / JS: tags are context, 3c is not inferred; `tag_map.yaml` closed set; JS3+ and Quantower Trades loader absent (QI-8 §6.5, §6.6, §6.9).
- RUX rendered-structure baseline: 16 page-render tests match; one `chat_input` per mode (QI-9 §6.8).

**Identity / determinism / isolation**
- API ↔ CLI `canonical_bundle_hash` identical (`062106ac…`) on the golden NQ fixture; UI-equivalent and assistant parity tests pass; pandas-3 golden hash record matches; timestamp-neutral (QI-6 §6.3, §6.7).
- CAI warm ↔ cold hashes equal on small and realistic; Study workers 1/2/4 identical per-cell `bundle_hash` (QI-14 §6.3–6.4).
- `generate_signals` and `simulate_trades` deterministic on probe fixtures (SHA-256 identical across runs) (QI-3 §6.9, QI-4 §6.6).
- Full suite deterministic: 3,966 passed / 5 skipped under default, `PYTHONHASHSEED=0`, `PYTHONHASHSEED=1`; five skips are env-gated desk oracles, not flakiness (QI-11 §6.1, §2.6).
- `dataset_id` parity `DataIdentity.dataset_id()` ↔ `compute_dataset_id`; `source_binding_key` includes mode/policy (QI-1 §6.4).
- Store round-trips hash-identical (sample; 15s parent + `subtimeframe.parquet`; schema v2 write / v1+v2 read) (QI-1 §6.5).
- `LEVEL_ENGINE_VERSION` = 11; all 59 emitted level columns prefix-identical under generated future shock on May/June and DST-week fixtures (QI-2 §6.3–6.4).
- Every slice used a throwaway `/tmp` store, no API keys, no desk PII; committed journal fixtures/examples PII scan 0 hits (QI-8 §6.7).

**Fail-closed / boundary behavior**
- Malformed engine inputs raise typed `ValueError` (SL, policy, cutoff, flatten-without-close; empty SL list; illegal `otf_history_policy`) (QI-4 §6.5, QI-5 §6.6).
- Empty-trade metrics: `trade_count=0`, rate/expectancy `None` not NaN; `validation_summary` empty path returns null metrics + `insufficient` (QI-4 §6.4, QI-5 §6.2).
- Bundles: malformed / missing-manifest / non-zip fail closed; path-traversal members never written (QI-6 §6.5).
- Secrets: OpenAI key BOM/quote unwrap, placeholder reject, sanitized provider errors; fail-closed without a key on both providers; tracked TOML never stores keys; `.env.example` store-only (QI-9 §6.4–6.6, QI-12 §6.7–6.8).
- Eval suites offline and deterministic (41 LLM + 26 voice tests) (QI-9 §6.3, QI-11 §6.4).
- Registry ↔ handler ↔ capability triple mechanically consistent (55 / 30 / 0 invalid) (QI-9 §6.1).
- Journal: never calls `simulate_trades` / `compute_all_levels`; Sunday 18:05 ET → Monday session; qty scaling matches TJ §3.0 on the 2-lot probe; journal store `journal/v1` refuses `results/studies/` (QI-8 §6.1–6.4).
- Study: ledger soft-resume re-queues a killed-looking cell; failed cells cannot be promoted; Observatory writes zero files into study dirs; Builder batteries-OFF emits explicit `enabled: false`; Program B manifests validate clean (QI-7 §6.4–6.8).
- Streamlit headless boots and serves `/_stcore/health`; `python -m thesistester {,study,journal} --help` exit 0 (QI-0 §6.5–6.6).

**Docs / tooling**
- `ruff check` (R9 set) and `ruff format --check` clean (368 files) (QI-12 §6.2).
- Help `USER_GUIDE` allowlist = exact 25-H2 match; allowlisted ARCHITECTURE/ASSUMPTIONS/OTF titles exist; 0 broken intra-doc links; "Files allowed to touch" lists point at existing paths (QI-13 §6.2–6.5).
- Fifteen sampled ASSUMPTIONS process claims hold against signatures/constants/import graph (QI-13 §6.6).
- `.cursor/rules/thesistester.mdc` matches `ENGINEERING_PROPOSAL` §4 (QI-13 §6.12).
- R22 serial ruler reproduces within hardware noise; official `tests/benchmarks` green (structure-only asserts) (QI-14 §6.1, §6.9).
- `pip-compile` derives a 50-pin constraints file from `pyproject.toml` today; QR-G is not tooling-blocked (QI-12 §6.9).

---

## 6. CTO disposition proposals — High findings (§7.5 c)

Proposed by this synthesis for Accumu's signature. Regression and architecture drift were weighed first per repo rules. **Nothing here merges a locked AH / `AUDIT_FINAL` contract into "fix now".**

| Row | Sev | Finding (one line) | Proposed | One-line reason | WS · wave |
|---|---|---|---|---|---|
| QI-12-01 | High | `main` unprotected; six CI jobs are not required checks | **accepted** | Settings-only; restores `ENGINEERING_PROPOSAL` §4 rule 9; every later QR gate depends on it; zero runtime risk | QR-G · wave 0 |
| QI-12-02 | High | No constraints/lockfile; accidental pandas-major matrix; no Dependabot; Streamlit minor uncapped | **accepted** | Two realized drift events in one week; `pip-compile` output exists; warn-first Dependabot with the full suite as gate | QR-G · wave 0 |
| QI-13-01 | High | ROADMAP / plan §8.3 say QI Not started; "blocking on red" prose | **accepted** | Docs-only; misleads agents today; cite the fourteen merged QI PRs and this synthesis | QR-F · wave 0 |
| QI-04-02 | High | Backtest Policy widget has no `allow_all` overlap disclosure (H5) | **accepted** | Presentation-only `help=`/caption; AH §8 parked H5 *as presentation*, so disclosure is the sanctioned residual; default stays `allow_all` (AH §2.1) | QR-A · wave 1 |
| QI-05-09 | High | Grid Policy widget inherits the H5 gap | **accepted** | Same PR as QI-04-02 (MG-02); copy only | QR-A · wave 1 |
| QI-05-04 | High | Focus KPIs read as Admit-equivalent under `single_position` (H12) | **accepted** | One banner sentence; AH §2 item 5 (Focus ≠ Admit except `allow_all` + 0 cooldown) is the premise being disclosed, not changed; no re-simulation | QR-A · wave 1 |
| QI-05-05 | High | Phase 8 `st.success` on p ≤ 0.05; confirmatory label; export banner missing (H13) | **accepted** | Copy/styling only; `validation_summary()` shape frozen (no key added); export banner is a reporting string, not a schema change | QR-A · wave 1 |
| QI-03-03 | High | `validate_setup_config` CC 69 hand-rolled validator | **accepted** | First declarative-table pilot for MG-17: no goldens, error strings kept stable, `tests/test_setup_config.py` + AH6 tests are the gate; do not flip omitted-key defaults (AH §2 item 10) | QR-C · wave 2 |
| QI-06-01 | High | `validate_run_spec` CC 104 (27.5 % of `api.py`) | **accepted (after QI-03-03 pilot)** | Same pattern once proven; `test_api` / `test_cli` / parity tests gate; fail-closed outcomes byte-comparable; no composer collapse | QR-C · wave 3 |
| QI-05-01 | High | `run_walk_forward_sl_tp` CC 50 | **accepted, gated** | Only after QI-11-04 own-file asserts lift WFA mutation above 70 %; fold construction / `causal_prefix` (S5, AH §2 item 6) untouched | QR-C · wave 3 |
| QI-03-01 | High | `generate_signals` CC 120 | **accepted, gated** | After QR-B adds a 3c/fade identity family and mutation baseline; extract TF-prep / zone admission / trigger dispatch; `_check_touch` and 3c math (S3, DA0) byte-identical | QR-C · wave 3 |
| QI-03-02 | High | 3c detectors F-grade; duplicated assembly | **deferred** | Depends on QI-03-01 landing; shares one row-mapper; separate PR so S3 math stays reviewable in isolation | QR-C · wave 4 |
| QI-04-01 | High | `simulate_trades` CC 133; P7 exit walk alone F-grade | **accepted, gated** | Last engine refactor: requires QI-11-02 golden families (flatten-on, 3c, BE/trail, opposite-direction legacy) and QI-11-04 backtest mutation ≥ 70 % first; P7 extraction behind `sim_core` with byte-identical goldens (§4.1); no default flips (AH §2.1) | QR-C · wave 4 |

**Rejected: none.** No High row asks for a locked behavior change.

### 6.1 Annex — Medium `Verified defect` rows (proposed for the same signature)

| Row | Finding | Proposed | Reason |
|---|---|---|---|
| QI-06-03 | AH4 residual leftovers (`otf_validation_*`, `skipped_signals`, `direction_collision_diagnostic`) survive apply | **accepted** | Additive `_MANAGED_RESEARCH_KEYS` (clear-only); AH4 probe tests extend; no page-12 hash (AH §2 item 8) |
| QI-10-01 | Dataset-switch clear list narrower than AH4; `display_timezone` unmanaged | **accepted** | Align `_clear_dataset_dependent_state` with the AH4 leftover set; same PR series as QI-06-03 (MG-01) |
| QI-08-03 | pdfplumber exception leaks a pdfminer stack from `journal reconcile` | **accepted** | Wrap as `JournalIngestError`; TJ2 trust boundary; additive junk-PDF test |

### 6.2 Product decisions this synthesis explicitly does **not** take (parked / locked; CTO or AH8 only)

H7 composer SoT · H15 TZ SoT · H10 Data-page abort · H11 typed reject · H9 `dataset_id` ingest story · H4 plane collapse · H8 omit-means-on flip · H14 snap-to-`base_end` (vs disclose) · 3c-void skip rows (§5.3 item 22) · page-12 hash · coworker-portable pin rewrite · `confirm_3bar` deletion · WFA-OOS as `primary_metric` (QI-05-06 offers "allow" or "document"; the plan carries "document" until decided).

---

## 7. Locked-contract register (12 rows, `disposition=locked`)

| Row | Prior | Locked by | What stays | Residual carried (workstream) |
|---|---|---|---|---|
| QI-01-03 | H10 | AH §2.1 parked forks; S1 | UI legacy-primary admits fatals; headless rejects | Disclosure sentence + lock-the-fork test via QI-01-07 (QR-A / QR-B) |
| QI-01-04 | H11 | AH §8 | Raw `ValueError` on mixed offsets | Document the parked reject (QR-F). Lock-the-fork test via QI-01-07 (QR-B). Typed error / UTC-normalize only after AH8 unpark (§6.2) — not a QR-A fix |
| QI-01-05 | H9 | `AUDIT_FINAL` §5.1 item 9; AH §2 item 9 | `dataset_id` omits mode | ARCHITECTURE identity-keys paragraph (QR-F) |
| QI-02-01 | H4 | AH §2 item 9 | Three planes; omit ⇒ on | Label the planes in living docs (QR-F) |
| QI-04-03 | H7 | `AUDIT_FINAL` §5.1 item 6; AH §8 | UI forces cutoff `None` without flatten | Label the fork on both composers (QR-A); Help via QI-13-07 (QR-F); test via QI-04-07 (QR-B) |
| QI-04-04 | H15 | `AUDIT_FINAL` §5.1 item 5; AH §8 | UI `exchange_timezone` vs headless `inst.exchange_tz` | Disclose clock fork (QR-A); test via QI-04-07 (QR-B) |
| QI-04-08 | M7 | `AUDIT_FINAL` §5.3 item 22 | 3c void = no fill, no skip row | Optional skip rows for missing-entry / `confirm_3bar` void only (QR-E, golden-sensitive) |
| QI-05-10 | H7 | `AUDIT_FINAL` §5.1 item 6 | Grid matches Backtest UI gate | Document in USER_GUIDE Grid (QR-F) |
| QI-06-06 | M14 | AH §2 item 8; §5.4; §5.5 page-12 hash parked | Page 12 schema-only | Label the three bars on page 12 (QR-E) |
| QI-07-10 | H2 | AH §2.1 replay; AH2 §6.2 | Spec-parent-first pin; no portable rewrite | none (docs already state it) |
| QI-09-08 | H8 | AH §2 item 9; §2.1 | Assistant `_bounded_spec` omit ⇒ on | omit=True sentence in Assistant/USER_GUIDE (QR-A, with QI-06-08) |
| QI-14-04 | H4 | AH §2 item 9 | `prev30m_vwap` enabled when key omitted | Document DEFAULT merge on CAI recipes (QR-F) |

---

## 8. Indicative §9.4 success metrics (targets vs QI-0 baseline)

| Metric | QI-0 baseline (`6786713`) | Indicative target | Measured by | Rows |
|---|---|---|---|---|
| Merges to `main` with a red required check | 37 in the week to 2026-09-08; `protected: false` | **0**; `required_status_checks.checks` = the six job names | `gh api repos/…/branches/main/protection` | QI-12-01 |
| Dependency-induced test failures detected before merge | 0 of 2 | 100 % (bump PRs run the full matrix) | Dependabot/Renovate PR history | QI-12-02 |
| Tracked dependency resolve | none (`uv.lock` gitignored) | `constraints.txt` committed; CI installs with `-c`; named pandas-major axis; Streamlit cap or minor job | `ci.yml`, `constraints.txt` | QI-12-02, QI-12-03 |
| F-grade functions in `engine/`, `analytics/`, `api.py` | **11** (152/133/120/104/75/69/63/59/55/51/50) | 0 F; E only with a documented reason; each QR-C PR states before/after CC | `radon cc -n E` | MG-17/18/19/20, QI-06-02 |
| Pages with MI 0.00 | 8 (+ `confluence_attribution.py`; 28 modules total at 0.00) | 0 pages at 0.00; library MI-0.00 count monotonically decreasing (28 → ≤ 14 by end of QR-C/D) | `radon mi` | MG-22, QR-C singletons |
| Prose-only import bans | all (6 documented; 3 hold, 3 broken via chains) | 100 % encoded in `import-linter`; warn-first then blocking; 0 broken contracts | `lint-imports` | QI-12-07, QI-13-06 |
| Library modules importing Streamlit | 1 eager (`app_state.py`) + 7 lazy | 0 outside an explicit allow-list; `app_state` split into store helper + page adapter | import-linter contract C8 | QI-06-05, QI-09-05 |
| Type-check errors (`engine/` + `analytics/`, strict) | 164 in 34 files (unmeasured in CI) | measured in CI (warn-first) → monotonically decreasing → blocking on `engine/`+`analytics/` | `mypy` job | QI-12-05 |
| Mutation score on sampled engine/analytics files | `intrabar` 100 · `metrics` 83.3 · `backtest` 66.7–72.7 · `walk_forward` 50–60 | ≥ 80 % on all four (own-file suites); baseline committed before any QR-C extraction of `backtest` / `walk_forward` | `mutmut` sample | QI-11-04 |
| Golden families vs default-on paths | 4 families / 4 of 8 default-on paths | 8 of 8 (flatten-on, 3c filled/void, BE/trail, opposite-direction legacy added; no regen of legacy) | golden CI job | QI-11-02 |
| Coverage gate | informational 85 %; measured **82 %**; 14 modules < 70 % | blocking at 82 % (warn-first one release), ratchet +1 pt per release; no `engine/`, `analytics/`, `data/`, `levels/` module < 85 % (`levels/common.py` 59 → ≥ 85) | `--cov-fail-under` | QI-12-04, QI-11-01 |
| Security / dependency scans in CI | none | `bandit -ll` + `pip-audit` warn-first → blocking on High; Actions pinned to SHAs | CI jobs | QI-12-06, QI-07-09 |
| Broad `except` | 83 | each classified in-repo (comment or allow-list); *hides defect* class = 0 (today: QI-03-05, QI-05-12, QI-08-03) | `rg` + ruff `BLE001` | MG-24 |
| Composer-parity divergences (ledger §5.3) | 24 entries: 8 locked (one, P13, without a row), 16 open | 0 open outside `locked`; every locked fork has a lock-the-fork test and a disclosure on both composers | ledger re-run | MG-02/03/05/10, QI-04-04, QI-04-07, QI-01-07 |
| `ARCHITECTURE.md` session-key table vs measured graph | 109 table names vs 162 literals; 4 consumers missing | asserted by a test (table ⊇ research keys and consumers); one key registry generates the pop lists | new test | QI-13-04, QI-10-03 |
| PIT append-FS test coverage | R3 named set only (59/59 columns pass a probe) | generated test over every emitted column on the R3 fixtures | `tests/test_r3_point_in_time.py` | QI-02-02 |
| Full-suite wall time / structure | 2:09–2:26 uninstrumented; one unmarked pile of 3,966 | tracked per release; `unit` marker subset < 5 min; AppTest files `serial`-marked before any xdist | `--durations`, markers | QI-11-05 |
| Honesty caveat presence per KPI page | Validation + Report only | "diagnostic, not proof" one-liner on Backtest / Grid / Time / Bundles; H5/H12/H13 copy landed | `tests/test_ui_copy_guards.py` | QI-10-04, MG-02, QI-05-04, MG-06 |
| CAI baseline reproducibility | realistic fixture dies on tick gate; documented stage shares stale | `--fixture realistic` runs; realistic table re-recorded on the tick-gated path; warm stage timers present | CAI harness | MG-27 |

---

## 9. Handoff to the QR plan (sequence summary)

`docs/QUALITY_REMEDIATION_PLAN.md` (draft, §9 template) orders the work as:

- **Wave 0 — gate and truth (QR-G + QR-F, settings/docs only):** required status checks (QI-12-01) · constraints + named matrix axis (QI-12-02, QI-12-03) · ROADMAP/AGENT_GUIDE/PROPOSAL truth (QI-13-01, QI-12-10) · README triggers (QI-13-02). Dependabot (G-3), scanners (G-4), and devcontainer (QI-12-08 / G-5) wait for wave 2.
- **Wave 1 — honesty first (QR-A), copy/disclosure only, one PR per finding:** H5 (MG-02) · H12 (QI-05-04) · H13 (MG-06) · H1 residual leftovers (QI-06-03, QI-10-01) · H8 disclosure (MG-05) · H16 (MG-08) · DA0 (MG-11) · Study CLI honesty (QI-07-05, QI-07-06) · fail-closed gaps (QI-08-03, QI-05-12, QI-06-09, QI-09-06) · H14 disclosure (QI-03-06; snap decision to CTO).
- **Wave 2 — safety net (QR-B + QR-G G-3…G-5), tooling/tests only:** lock-the-fork tests (QI-04-07, QI-01-07) · PIT generated FS (QI-02-02) · golden families for default-on paths (QI-11-02) · mutation baseline (QI-11-04) · coverage floor blocking at 82 % (QI-12-04, QI-11-01, QI-09-04, QI-06-12) · import-linter warn-first (QI-12-07) · mypy warn-first (QI-12-05) · markers (QI-11-05) · AppTest harness rules (MG-26) · CAI harness fix (QI-14-01) · QR-G Dependabot / `bandit`+`pip-audit`+pins / devcontainer (QI-12-02 residual, QI-12-06, QI-07-09, QI-12-08). Then the QR-C pilot: `validate_setup_config` (QI-03-03).
- **Wave 3 — structure (QR-C), golden-gated, one hot spot per PR:** `validate_run_spec` → `study.schema` (MG-17) · `build_markdown_report` (QI-06-02) · `generate_signals` (QI-03-01, then QI-14-05) · `run_walk_forward_sl_tp` (QI-05-01) · bundle registry (QI-06-04) · `app_state` split (QI-06-05) · journal init (QI-08-02).
- **Wave 4 — engine core and UI (QR-C/QR-D):** `simulate_trades` P7 (QI-04-01, QI-14-09) · 3c row-mapper (QI-03-02) · page splits (MG-22) · session-key registry (QI-10-03) · assistant tables (QI-09-01, QI-09-02) · Study/journal/store modules.
- **Wave 5 — application functions (QR-E) and docs consolidation (QR-F):** operability/copy (QI-02-03, QI-06-07, QI-08-05, QI-09-11, QI-10-04, …) · W12 acceleration inside R22 (QI-14-03, QI-14-06) · glossary/Help/CAI docs · AGENT_GUIDE ledger → contracts (QI-13-06).

Every workstream section in the QR plan cites its finding IDs; every open row appears in exactly one workstream; locked rows appear only as disclosure/test residuals (never as "unpark/invert the lock"); `duplicate` rows are listed under their primary; the single `wont-fix` is recorded in the QR plan §7.

---

## 10. Guardrail evidence

| Check | Result |
|---|---|
| `pytest -q --tb=no -p no:cacheprovider` **before** (branch at `0b2c451`, no file changed) | **3,966 passed, 5 skipped** in 133.22 s, exit 0 |
| `pytest -q --tb=no -p no:cacheprovider` **after** (three files added/changed) | **3,966 passed, 5 skipped** in 125.59 s, exit 0 — identical pass/fail/skip (plan §2 rule 2) |
| Review-pass `pytest -q --tb=no -p no:cacheprovider` (honesty/schema edits only) | **3,966 passed, 5 skipped** in 137.21 s, exit 0 — identical pass/fail/skip |
| `git status --porcelain` | `docs/quality/QI-15_SYNTHESIS.md` (new) · `docs/QUALITY_REMEDIATION_PLAN.md` (new) · `docs/quality/findings.csv` (modified, append-only) |
| `findings.csv` parse | 134 rows × 23 columns; every row `disposition ∈ {open, closed-verified, locked, wont-fix, duplicate}`; every `open` row has a `score`; every non-`wont-fix` row except QI-07-10 has a `qr_workstream` |
| Slice fields untouched | all 135 header+data lines of `HEAD:docs/quality/findings.csv` are a strict prefix of the new lines (textual append; no re-quoting) |
| Isolation | throwaway `THESISTESTER_STORE_DIR` under `/tmp/qi15`; `OPENAI_API_KEY` / `XAI_API_KEY` unset; no desk data |

## Research-only sentence

No product, test, fixture, golden, workflow, config, or living-doc file was edited. The only tracked changes are `docs/quality/QI-15_SYNTHESIS.md` (new), `docs/QUALITY_REMEDIATION_PLAN.md` (new draft, not authorized work), and four additive columns (`merge_group`, `score`, `qr_workstream`, `disposition`) on `docs/quality/findings.csv` with every slice-written field byte-identical. `pytest -q` is unchanged. No QR fix was started.
