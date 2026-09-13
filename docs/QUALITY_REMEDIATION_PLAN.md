# Quality Remediation Plan — QR series (DRAFT, fix-vs-close re-baseline)

**Document type:** Remediation program derived from the Quality Investigation (QI) synthesis — implementation plan with fully scoped PRs
**Date:** 2026-09-12. Rev 1 = QI-15 draft ([#494](https://github.com/AccumuLatata/ThesisTester/pull/494), `main @ 29167c2`). **Rev 2 (this document) = fix-vs-close re-baseline:** every finding is either scoped into a concrete PR, kept `locked` (disclosure/test residual only), or closed (`wont-fix` / `duplicate`) with a one-line rationale mirrored in `docs/quality/findings.csv`.
**Series code:** **QR** (Quality Remediation). Workstreams **QR-A … QR-G** as fixed by `docs/QUALITY_INVESTIGATION_PLAN.md` §9.1.
**Status:** **DRAFT — nothing here is authorized work until the CTO review gate (`QUALITY_INVESTIGATION_PLAN.md` §7.5) is signed (§7 below).** Opening any QR PR before that is a process breach.
**Inputs (SoT order):** `docs/quality/findings.csv` (134 rows; `disposition` / `qr_workstream` / `merge_group` / `score` columns) · `docs/quality/QI-15_SYNTHESIS.md` (views, scores, CTO proposals — historical; census numbers there predate this rev) · `docs/quality/QI-01…QI-14` (probe recipes cited per PR) · `docs/QUALITY_INVESTIGATION_PLAN.md` §3, §7.5, §9 · `docs/ENGINEERING_PROPOSAL.md` §4.
**Locked premises (never reopened by QR):** `AUDIT_FINAL.md` §5 and §7 (`origin/cursor/audit-final-merge-3a8e`), `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1, every completed series' contract doc (AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX/RS/SB/SIA/SV/SO/SAF/LC/WMV/TV/AP/RP/DA/TJ/JS/AO/SW/AH), `ENGINEERING_PROPOSAL.md` §4 (incl. §4.1 golden-master spec, §4.2 PR checklist).

> **Financial caution.** QR fixes disclosure, structure, tests, and tooling. No QR PR may describe a backtest, metric, or Study result as correct or reliable; QR-A copy states *what a number is and is not*, it does not certify it.

---

## 1. Purpose, scope, out-of-scope

### 1.1 Purpose

Turn the 134 QI findings into a regression-safe program: **106 open rows → 102 PR rows (99 distinct PRs; F-4/F-7/F-8 are delivered inside A-4/A-12/A-9)** — one PR per finding unless a real `MG-*` shares one change, **12 locked rows → disclosure/test residuals only**, **16 rows closed** (13 `wont-fix`, 3 `duplicate`).

### 1.2 In scope

- The 106 `open` rows, each owned by exactly one workstream and one PR id (§3).
- Disclosure on both composers, lock-the-fork tests, and living-doc honesty for the 12 `locked` rows.
- Tooling / CI gates introduced warn-first (§4).

### 1.3 Out of scope (explicit)

- **The ongoing Study need not stop or rerun.** A detached `python -m thesistester study run` process (ledger + per-cell bundles under `results/studies/`) is unaffected by any QR PR: QR-C engine PRs are gated byte-identical on goldens and feature fixtures, so no completed cell's `bundle_hash` is invalidated; a running process keeps its already-imported code; soft-resume (`RS3`) continues to work on the same ledger. No QR PR touches `results/studies/`, `study_observatory/desks`, or the Study ledger format.
- **No golden regeneration inside QR-C.** Legacy families are never regenerated; new families (B-3) are additive; any regen is a dedicated `GOLDEN_REGEN` PR with CSV diff, outside QR-C.
- **No reopening of locked math or product decisions.** H4/H7/H8/H9/H10/H11/H15 forks, 3c four-rule math (S3), fold construction (S5), `allow_all` / `sl_first` / flatten defaults (AH §2.1), page-12 schema-only bar (AH §2 item 8), RUX layout, RS-D9 call ban. Product decisions are parked in §7.2.
- **No reopening of completed series**, no composer collapse (AH §2 items 1–2), no Help-allowlisted file moves (HC rule 2), no re-running QI slices.
- Feature work beyond what a finding names (QR-E is opt-in/additive only).

---

## 2. Disposition census after this pass

### 2.1 Severity × disposition (from `findings.csv`)

| Severity | open | locked | duplicate | wont-fix | closed-verified | Total |
|---|---:|---:|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 |
| High | **13** | 0 | 0 | 0 | 0 | 13 |
| Medium | **76** | 11 | 2 | 1 | 0 | 90 |
| Low | **17** | 1 | 1 | 12 | 0 | 31 |
| **Total** | **106** | **12** | **3** | **13** | **0** | **134** |

Rev 1 → Rev 2 delta: open 119 → 106 (−13); wont-fix 1 → 13 (+12); duplicate 2 → 3 (+1). `closed-verified` stays 0 by rule (never invented; closed carry-overs live in `QI-15_SYNTHESIS.md` §5.7).

### 2.2 Open rows per workstream

| WS | open | locked residual | duplicate (listed under primary) | PRs |
|---|---:|---:|---:|---:|
| QR-A Honesty and correctness | 22 | 4 | 0 | 22 |
| QR-B Safety net | 19 | 0 | 0 | 19 |
| QR-C Structural refactors | 27 | 0 | 0 | 25 |
| QR-D UI decomposition / state | 10 | 0 | 0 | 10 |
| QR-E Application functions | 10 | 2 | 0 | 11 |
| QR-F Documentation | 12 | 5 | 3 | 10 |
| QR-G Dependency / supply chain | 6 | 0 | 0 | 5 |
| no workstream | 0 | 1 (QI-07-10, no residual) | 0 | — |
| **Total** | **106** | **12** | **3** | **102 PR rows / 99 distinct PRs** (some findings ride in an `MG` PR) |

### 2.3 Newly closed in this pass (rationales; mirrored in `findings.csv`)

| Row | Sev | Was | Now | Rationale (one line) |
|---|---|---|---|---|
| QI-02-06 | L | open QR-F | **wont-fix** | USER_GUIDE §Levels under-describes always-on session tokens; no misread risk — `catalog.py` / `closed_level_token_set` is the SoT and Setup Builder pickers already show the closed set. |
| QI-02-07 | L | open QR-C | **wont-fix** | `_rolling_poc` typical body is dead and fenced: `typical_mvp_v1` is unselectable on the product path and refuse-without-ticks is tested (QI-2 §6.5–6.6); deletion is a parked CTO decision (§7.2), not a QR PR. |
| QI-02-08 | L | open QR-C | **wont-fix** | Optional level-family protocol (cost class 3) with no defect and no hot-spot trigger; additive kwargs are the locked keyword contract (AH / AUDIT P2). |
| QI-03-07 | L | open QR-C | **wont-fix** | `confirm_3bar` helpers cannot be generated (QI-3 §6.2) and `AUDIT_FINAL` §5.1 item 22 keeps the residual fill; delete/quarantine is the parked §5.5 question (§7.2). |
| QI-05-15 | L | open QR-E | **wont-fix** | R19 OAT is deterministic; the stored `random_state` is inert and no operator surface claims randomness; removing the kwarg is an API change with no honesty gain. |
| QI-07-08 | M | open QR-C | **wont-fix** | `examples/studies/program_b/validate_program_b_yaml.py` is example tooling outside the library radon scope and the §9.4 F-grade metric; manifests validate clean (20/898, 8/253); revisit only if Program B locks change. |
| QI-09-07 | L | open QR-E | **wont-fix** | Quoted/BOM xAI keys fail closed (`VoiceProviderError`), no leak; voice is default-off (VA); revisit if voice leaves default-off. |
| QI-09-09 | L | open QR-E | **wont-fix** | `require_tool_for_numbers` is an unused default-off flag behind the VA lock; wire-or-delete is a VA follow-up decision (§7.2), not QR scope. |
| QI-10-07 | L | open QR-C | **wont-fix** | Dead `page_key` parameter; the shipped render helper checks `target_page` first (QI-10 §3.5), so the UI is safe; delete when `classic_nav` is next touched. |
| QI-13-10 | L | open QR-F | **wont-fix** | Help retrieval of TJ/JS/RS ASSUMPTIONS H2s is an HC-allowlist widening decision (HC §7.1); USER_GUIDE Journal/Studies H2s cover the how-to depth (QI-13 §3.2). |
| QI-14-07 | L | open QR-F | **duplicate → QI-14-02** | Same action, same file: re-record `CAI_BASELINE.md` tables (small bundle row rides the realistic re-record in F-10). |
| QI-14-08 | L | open QR-B | **wont-fix** | Warm-path stage timers only matter if the parked CAI-10 second cache is proposed; hash equality remains the correctness gate. |
| QI-14-10 | L | open QR-E | **wont-fix** | 14 + 20 `.copy()` sites are noise against the W12 engine-replay multiplier; revisit after E-10 only if RSS at 3-month scale still matters. |

Kept-open Low rows (not closed because a MUST-FIX trigger applies): QI-04-10 (financial misread: `pnl_points` vs net R) · QI-09-06 (Security risk) · QI-06-12 / QI-11-05 / QI-11-06 / QI-12-09 / QI-10-08 (test/tooling gates for later refactors) · QI-01-06 / QI-04-09 / QI-05-14 / QI-06-11 / QI-14-09 (ride inside named hot-spot PRs) · QI-03-09 / QI-03-11 / QI-09-10 (cheap riders in wave 5 PRs that touch the same widgets).

Workstream moves in this pass: QI-10-04 QR-E → **QR-A** (page-level "diagnostic, not proof" caveat is honesty copy with financial-misread risk) · QI-05-13 QR-F → **QR-B** (the freeze is best mechanized as a key-set assert, B-19). Pre-existing closures unchanged: QI-05-11 → QI-13-03, QI-10-02 → QI-13-04 (duplicates), QI-10-06 (wont-fix, W15).

---

## 3. Workstreams and PR tables

Column key: **Files (expected)** = paths a reviewer should expect in the diff (from the finding's `files_symbols`); **Probe → regression test** = the QI probe that must become a committed test (red → green for QR-A; identity for QR-C); **Exit / merge gate** = what CI/review must show. `MG-*` ids are defined in `QI-15_SYNTHESIS.md` §3.2. Wave numbers are in §4.

### QR-A — Honesty and correctness fixes

**Owned open (22):** QI-03-06 · QI-03-08 · QI-04-02 · QI-04-06 · QI-04-10 · QI-05-04 · QI-05-05 · QI-05-06 · QI-05-07 · QI-05-08 · QI-05-09 · QI-05-12 · QI-06-03 · QI-06-08 · QI-06-09 · QI-07-04 · QI-07-05 · QI-07-06 · QI-08-03 · QI-09-06 · QI-10-01 · QI-10-04.
**Locked residuals (disclosure only, 4):** QI-01-03 (H10) · QI-04-03 (H7) · QI-04-04 (H15) · QI-09-08 (H8, Assistant sentence).
**Closed here:** none (QR-A rows all carry a financial-misread or fail-closed trigger).
**Regression-safety shape:** one PR per finding (or per `MG`); probe becomes a committed test; §4.2 checklist; **no golden regeneration** — A-7/A-8 (additive managed keys) and A-17 (error propagation) must leave `trades` and bundle hashes byte-identical on goldens.

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| A-1 | QI-04-02 (H), QI-05-09 (H) — MG-02 | `pages/7_Backtest.py` (`exposure_policy` selectbox), `pages/8_Grid_Search.py` (Policy selectbox) | `help=` + caption: `allow_all` counts overlapping signals independently; skip table is empty by design. Default unchanged (AH §2.1). | Two-candidate overlap recipe (`docs/quality/README.md`; QI-4 §3) → `tests/test_ui_copy_guards.py` help-presence assert on both pages | `USER_GUIDE.md` §Exposure policy widget row (Backtest + Grid); `ASSUMPTIONS_AND_LIMITATIONS.md` H5 sentence | copy guard green; goldens untouched; no `simulate_trades` diff |
| A-2 | QI-04-06 (M) — MG-02 | `pages/7_Backtest.py` (run persist), `docs/ARCHITECTURE.md` | Persist `direction_collision_diagnostic` (additive, unhashed session key) and caption it next to the skip table — or state that classic UI does not show DA1. | `tests/test_backtest_direction_collision.py` extension: page helper stores `candidate_pairs` after a `return_result` run | `ARCHITECTURE.md` session-key row; `METRICS_GLOSSARY.md` DA1; `USER_GUIDE.md` Exposure | key additive; AH4 managed set decision recorded (clear-only) |
| A-3 | QI-05-04 (H) | `pages/9_Time_Analysis.py`, `pages/10_Validation.py` Focus provenance (`FOCUS_HONESTY_BANNER` consumer text only; `analytics/entry_window.py` untouched) | One banner sentence: Focus fills may differ from Admit under `single_position` (AH §2 item 5 premise). No re-simulation. | H12 fixture (QI-5 §3; `single_position` + out-of-window blocker) → named test asserting fill sets unequal and C7 identity (`allow_all` + 0 cooldown) + caption presence | `USER_GUIDE.md` Focus vs Admit; `ASSUMPTIONS_AND_LIMITATIONS.md` H12 | test red→green; Focus helpers unchanged |
| A-4 | QI-05-05 (H) — MG-06; delivers QR-F QI-13-03 | `pages/10_Validation.py` (permutation `st.success`, `P(mean R > 0)` metric), `thesistester/reporting.py` (`## Validation Diagnostics` banner string), `docs/METRICS_GLOSSARY.md` | `st.success` → `st.info`/caption; rename label; add diagnostic banner line in export. `validation_summary()` shape untouched. | Copy guard on page 10 + `tests/test_phase9_reporting.py` banner assert | `METRICS_GLOSSARY.md` rows: probability_positive, Phase 8 permutation p-value, grid-overfit Best/Median/delta; `USER_GUIDE.md` Validation; `ASSUMPTIONS` H13 | `validation_summary` key-set test (B-19) green; report fixtures updated for banner only |
| A-5 | QI-05-07 (M) | `pages/10_Validation.py` (`overlap_policy` help, WFA summary captions) | Caption `aggregate_test_total_r` as an overlapping fold-sum; extend overlap help beyond stitched equity. Fold math untouched (S5). | Existing overlap-reject warning test + caption presence | `METRICS_GLOSSARY.md` Aggregate test total R caveat; `ASSUMPTIONS` M9; `USER_GUIDE.md` WFA | `walk_forward.py` not in diff |
| A-6 | QI-05-08 (M) | `pages/8_Grid_Search.py` (`ranking_metric` help), `pages/10_Validation.py` (WFA heatmap caption, OTF trophy prefix) | Diagnostic wording on Grid ranking; WFA heatmap caveat caption; drop or pair the OTF-matrix trophy prefix. | Copy guard | `USER_GUIDE.md` Grid / WFA; `ASSUMPTIONS` M10 | ranking math untouched |
| A-7 | QI-06-03 (M, Verified defect) — MG-01 | `thesistester/research_bundle.py` (`_MANAGED_RESEARCH_KEYS`) | Add `otf_validation_matrix/config/summary`, `skipped_signals`, `direction_collision_diagnostic` as **clear-only** managed keys. No page-12 hash (AH §2 item 8). | QI-6 §3.3 leftover probe → `tests/test_research_bundle.py` `test_ah4_*` sibling: keys absent after a zip without those sections | `ARCHITECTURE.md` leftover sentence + session-key table | golden bundle hash unchanged (keys not hashed); AH4 tests green |
| A-8 | QI-10-01 (M, Verified defect) — MG-01 | `pages/1_Data.py` (`_clear_dataset_dependent_state`), `thesistester/timezone_display.py` / `research_bundle.py` (`display_timezone` handling) | Align dataset-switch clear list with the AH4 leftover set (`focused_trades`, `focused_equity_curve`, `otf_filter_summary`, `signal_settings`, `setup_config` on `dataset_id` change); manage-or-reset `display_timezone` on apply/switch. | QI-10 §3.2 stale-state probe → `tests/test_data_page_helpers.py` clear test + `test_research_bundle.py` display-timezone case | `ARCHITECTURE.md` session-key table (`display_timezone`, `focused_trades`) | stale-state matrix row "load/switch dataset" shows no leftover |
| A-9 | QI-06-08 (M) — MG-05; residual of locked QI-09-08; delivers QR-F QI-13-09 | `thesistester/cli.py` (`_parser` help), `pages/14_Research_Assistant.py` confirm-run caption, `docs/USER_GUIDE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Omitted battery `enabled` means **on** for api/CLI/assistant; Study emit stays explicit `false`; nested OTF matrix is default-off. Default unchanged (AH §2 item 9). | CLI `--help` text assert; keep a probe that omitted `grid.enabled` still runs | `USER_GUIDE.md` classic headless + Assistant confirm-run; `ASSUMPTIONS` H8 sentence; `AGENT_GUIDE.md` | `.get("enabled", True)` unchanged in diff |
| A-10 | QI-07-04 (M) — MG-08 | `thesistester/study/report.py` (`render_overview_markdown`), `thesistester/study/rollup.py` (`rollup_study`) | Labeled **Failed** section / failed count in overview and rollup MD. Failed rows stay in overview CSV and rollup N (`AUDIT_FINAL` §5.1 item 34); ranked/promote unchanged. | Mixed ok/failed fixture (QI-7 §9) → `tests/study/test_study_report.py` + rollup test: MD contains Failed heading + error text | `STUDY_RUNNER.md` §RS4; `USER_GUIDE.md` Studies Inspect vs report | promote selection unchanged; overview CSV byte-identical |
| A-11 | QI-05-06 (M) — MG-08 | `docs/STUDY_RUNNER.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` (and `study/schema.py` **only if** the CTO chooses "allow") | Default: **document** that Study ranking ignores WFA OOS (`wfa_median_test_expectancy_r` stored, not rankable). If CTO chooses "allow" (§7.2): add the token to `_INDEX_PRIMARY_METRICS` when the column exists. | `tests/study/test_study_schema.py` accept/reject for the token (whichever is chosen) | `STUDY_RUNNER.md` primary_metric; `ASSUMPTIONS` H16 | WFA math untouched |
| A-12 | QI-03-08 (M) — MG-11; delivers QR-F QI-13-08 | `pages/3_Setup_Builder.py` (direction selectbox), `pages/6_Signals.py` (direction selectbox), `docs/USER_GUIDE.md` | DA0 disclosure as `help=`: `touch`+`both`+`single_position` is long-only (ASSUMPTIONS §4b). Admission unchanged. | Copy guard on both widgets + USER_GUIDE Setup Builder pitfall cell | `USER_GUIDE.md` Setup Builder Direction pitfall (Help-allowlisted, in place) | `setup.py` / `signals.py` not in diff |
| A-13 | QI-03-06 (M, H14) | `pages/6_Signals.py` (HTF trigger_timeframe + 3c controls caption), `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/POINT_IN_TIME_GUARANTEES.md` | **Disclose** H14 at the HTF+3c widget and in ASSUMPTIONS: developing partners (dVWAP/SMA/rolling VWAP) are the early-window value tested against completed HTF OHLC; decision T is HTF close. **Snap-to-`base_end` is a CTO decision (§7.2), not this PR.** | Drift-VWAP HTF recipe (`docs/quality/README.md`) → `tests/test_signals_3c_trigger_timeframe.py` disclosure/caption assert + a fixture that records the current projection (locks status, does not demand a change) | `ASSUMPTIONS`; `USER_GUIDE.md` Signals 3c HTF; `POINT_IN_TIME_GUARANTEES.md` | `_project_zones_to_trigger_df` not in diff; goldens untouched |
| A-14 | QI-07-05 (M) | `thesistester/study/schema.py` (`validate_study_spec`), `thesistester/study/builder.py` (`_WARNING_QUANTOWER_PRIMARY` reuse) | Error-level warning (or fail-closed, CTO choice §7.2) when `format_profile=quantower_history_exporter` and `ingestion_mode` omitted/primary. Never rewrites to 15s-primary (AH §2 item 9). | 15s HE fixture without `ingestion_mode` (QI-7 §10) → `tests/study/test_study_schema.py`: warning/`StudySpecError` raised; 15s-primary + Quantower accepted | `AGENT_GUIDE.md` SIA paragraph; `STUDY_RUNNER.md` §SIA; `USER_GUIDE.md` Studies dataset | Program B manifests still validate clean |
| A-15 | QI-07-06 (M) | `thesistester/study/cli_study.py` (`_cmd_expand` Replay line), `thesistester/study/expand.py` (`write_expansion_artifacts` comment), `thesistester/study/report.py` (overview MD line) | Carry the AGENT_GUIDE "same bytes when the expand-time file exists; still `run_batch`; not `study run`" clause onto the CLI line, `experiment.yaml` comment, overview MD. | Expand CLI stdout assert | `STUDY_RUNNER.md` §RS3 (already true; CLI now matches) | `run_batch` semantics unchanged (AH §2 item 7) |
| A-16 | QI-08-03 (M, Verified defect) — MG-24 | `thesistester/journal/amp_statement.py` (`extract_amp_pdf_text`) | Wrap `pdfplumber.open` / pdfminer failures as `JournalIngestError`; keep missing-file and text-parse paths. | Junk / empty / non-PDF bytes → `tests/test_journal_amp_statement.py`: typed error; `journal reconcile` rc 2, no `Traceback` in stderr | `ASSUMPTIONS` TJ2; `AGENT_GUIDE.md` Journal CLI errors | journal suites green |
| A-17 | QI-05-12 (M) — MG-24 | `thesistester/analytics/otf_validation.py` (`_simulate`) | Typed engine errors propagate (or the row records an error status); empty-input → empty frame kept. AH3 prefix slicing untouched. | Cell whose `simulate_trades` raises must not look like 0 trades → `tests/test_otf_validation.py`; remove the `pragma` only with the named test | `AGENT_GUIDE.md` OTF matrix error surface | `test_ah3_p1_*` family green |
| A-18 | QI-06-09 (M, Security risk) | `thesistester/research_bundle.py` (`_read_uploaded_bytes`, `_read_parquet_from_zip`) | Reject a named member over a size cap **before** `ZipFile.read`; schema-only column policy unchanged; no hash gate. | Adversarial zip recipe (`docs/quality/README.md`; QI-6 §9) → `tests/test_research_bundle.py`: oversized member → `ValueError`; traversal ignored; honest fixture loads | `ARCHITECTURE.md` bundle trust boundary; `USER_GUIDE.md` Research Bundles | page 12 stays schema-only (AH §2 item 8) |
| A-19 | QI-09-06 (L, Security risk) | `thesistester/assistant/orchestrator.py` (`_record_audit`), `thesistester/assistant/contracts.py` (`AssistantRequest.to_dict`) | Scrub secret-shaped keys (reuse `sidecar.redact_for_logs`) before `append_conversation_message`. Dispatch confirmation unchanged. | Payload `api_key` absent/`[redacted]` in transcript and on-disk JSON → `tests/test_assistant_orchestrator.py` | `ASSUMPTIONS` AI Research Assistant; `AGENT_GUIDE.md` audit-payload rule | AIA registry tests green |
| A-20 | QI-04-10 (L) | `pages/7_Backtest.py` (trade table caption) | Caption: `pnl_points` is the gross alias of `gross_pnl_points`; KPIs use net R (`AUDIT_FINAL` §5.3 item 25). | Caption presence helper test | `USER_GUIDE.md` Backtest trade table | columns unchanged (identity) |
| A-21 | QI-10-04 (M) | `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/9_Time_Analysis.py`, `pages/12_Research_Bundles.py`, `pages/1_Data.py` | Reuse the Validation "diagnostic, not proof" one-liner on Backtest / Grid / Time / Bundles; Data caption pointing at the 400 MB websocket cap (cap unchanged). | `tests/test_ui_copy_guards.py` per-page sentence; `tests/test_streamlit_server_limits.py` unchanged | `USER_GUIDE.md` Data / honesty | `.streamlit/config.toml` not in diff |
| A-22 | residuals of locked QI-01-03 (H10), QI-04-03 (H7), QI-04-04 (H15) | `pages/1_Data.py` legacy-primary caption + `api.load_dataset` docstring; `pages/7_Backtest.py` cutoff widget caption + `api.run_backtest` docstring (cutoff + TZ) | One sentence per locked fork on **both** composers; behavior untouched. | Pairs with B-1 / B-2 lock-the-fork tests (must land first or together) | `USER_GUIDE.md` Data H2 + Session close (with F-6); `ASSUMPTIONS` §3; `AGENT_GUIDE.md` composer table | no admission diff; lock tests green |

**Exit:** all 13 High `app`/docs rows and the three Medium `Verified defect` rows carry `fixed_in`; composer-parity ledger (`QI-15_SYNTHESIS.md` §5.3) has 0 open entries whose fix is disclosure; every locked fork has a disclosure on both composers.

### QR-B — Safety net before refactor

**Owned open (19):** QI-01-07 · QI-02-02 · QI-04-07 · QI-05-13 · QI-06-12 · QI-09-04 · QI-10-05 · QI-10-08 · QI-11-01 · QI-11-02 · QI-11-03 · QI-11-04 · QI-11-05 · QI-11-06 · QI-12-04 · QI-12-05 · QI-12-07 · QI-12-09 · QI-14-01.
**Closed here:** QI-14-08 (wont-fix).
**Regression-safety shape:** tooling/tests only; zero runtime change; every new CI gate warn-first for one release, then blocking in its own PR; golden families additive; AppTest rewrites keep every assertion's intent (RUX).

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| B-1 | QI-04-07 (M) — MG-03; tests for locked QI-04-03 / QI-04-04 | `tests/test_ah8_cutoff_without_flatten.py`, `tests/test_ah8_otf_tz_ui_vs_api.py` (names illustrative) | Lock-the-fork tests: H7 (UI forces `None`; YAML cutoff applies with `after_entry_cutoff` skips), H15 (recorded `session_timezone` per composer). **Fail if a fork is inverted.** | QI-4 §3 / Appendix A recipes | `tests/fixtures/golden/README.md` uncovered-path list | tests green on both composers; no product diff |
| B-2 | QI-01-07 (M) — MG-10; tests for locked QI-01-03 / QI-01-04 | `tests/test_loader.py`, `tests/test_data_page_helpers.py` | H10 paired UI-helper vs `api.load_dataset` fatal-code admission (locks the fork); H11 mixed-offset canonical + QT-aware recipe (raw `ValueError` today). | QI-1 §3 parity matrix recipes | `AGENT_GUIDE.md` R17 test list | naive DST tests still green |
| B-3 | QI-11-02 (M) — MG-18 | `tests/fixtures/golden/` (new families + recorder), `tests/test_*_golden.py` | Additive golden families for default-on paths not identity-gated: flatten-on, 3c filled/void (`sl_first`), BE/trail, `same_bar_opposite_direction="legacy"`. Legacy families never regenerated. | §4.1 recorder; keep `test_ah1_*` / `test_ah5_*` as probes | `tests/fixtures/golden/README.md` default-on branch table; `ENGINEERING_PROPOSAL.md` §4.1 cross-link | 8/8 default-on paths gated; golden-guard job unchanged |
| B-4 | QI-11-04 (M) — MG-18 / MG-20 | `tests/test_walk_forward.py`, `tests/test_phase5_backtest.py`, `docs/AGENT_GUIDE.md` | Own-file asserts: WFA overlap-reject stitch, `retention_ratio`, `fold_local` vs `causal_prefix` (keep `test_otf_integration.py` in the sample); backtest BE with `allow_same_bar_exit=False`, path-label exit reasons, `both_hit_pct`. Commit the `mutmut` sample recipe + baseline. | QI-11 §2.2 / §10 mutation recipe | `AGENT_GUIDE.md` §Development environment mutation baseline | `backtest.py` ≥ 70 % and `walk_forward.py` ≥ 70 % own-file killed (target 80 %) — **hard gate for C-14/C-17/C-19** |
| B-5 | QI-02-02 (M) | `tests/test_r3_point_in_time.py` | Generated append-future-shock over every emitted level column (§5.5 set: `dOpen*`, `wOpen`, `mOpen`, `prevSettlement`, `pw*`, `pm*`, `pmVA*`) on the R3 fixtures + DST week. `trading_session_date` math not re-audited. | QI-2 §10 probe (59/59 prefix-identical) | `POINT_IN_TIME_GUARANTEES.md` Tests column | 59/59 columns asserted |
| B-6 | QI-12-04 (M) — MG-15 | `.github/workflows/ci.yml` (`COVERAGE_FLOOR`), `pyproject.toml [tool.coverage]` | Floor at the measured **82 %**, warn-first one release, then `--cov-fail-under` blocking; ratchet +1 pt per release thereafter. | none (existing coverage job) | `AGENT_GUIDE.md` §Development environment; `ENGINEERING_ROADMAP.md` R9 coverage sentence | second PR flips to blocking |
| B-7 | QI-11-01 (M) — MG-15 | `tests/test_levels_common.py` (new), `tests/test_journal_rules.py` / `test_journal_ledger.py`, `tests/test_classic_*.py` | Direct tests for `levels/common.py` (`require_tz_aware_timestamp`, `normalized_window_label` Timedelta branch), journal `rules`/`ledger`, classic helpers; classify `__main__` / `sidecar` / `xai_realtime` untestable-by-design. | QI-11 §2.3 debt map | `AGENT_GUIDE.md` untestable-by-design list | `levels/common.py` ≥ 85 %; no module in `engine/`, `analytics/`, `data/`, `levels/` < 85 % |
| B-8 | QI-09-04 (M) — MG-15 | `tests/test_assistant_handlers.py` (new or extended) | One dispatch/payload test per routed capability ID (DATA.* defaults, HOME.workflow_guide, VALIDATION.run_otf_matrix, BACKTEST/GRID.manage_execution_defaults, CLASSIC.propose_page_change); `get_handler` unit test. | QI-9 §3 capability matrix | `AGENT_GUIDE.md` capability test-completeness sentence | `handlers.py` coverage ≥ 70 % |
| B-9 | QI-06-12 (L) — MG-15 | `tests/test_cli.py`, `tests/test_classic_*.py` | CLI process tests for `__main__` and error paths; unit tests for classic render helpers (Streamlit stub per QI-10 verdict). | QI-6 §3.2 | none | `cli.py` ≥ 70 % |
| B-10 | QI-12-07 (M) — MG-16 | `.importlinter` (or `pyproject [tool.importlinter]`), `.github/workflows/ci.yml` | Contracts C1–C5, C7–C10 from `QI-15_SYNTHESIS.md` §5.4: layers / `allow_indirect_imports` for `expand → cli → cli_study`; Streamlit explicit allow-list (`app_state`, classic chrome, two secret readers until C-8/F-9); journal ↛ `engine.backtest` / `levels.all` / `sim_core`; `sim_core` ↛ admission/analytics. Warn-first. | QI-12 §2.6 draft (`/tmp/qi12/import_linter_draft.ini`) | `ARCHITECTURE.md` import-ban paragraphs; `AGENT_GUIDE.md` §Study | 0 broken contracts after C-8/C-9; blocking flip in its own PR |
| B-11 | QI-12-05 (M) | `.github/workflows/ci.yml`, `pyproject [tool.mypy]` (path-scoped) | `mypy` job on `engine/` + `analytics/` (not `--strict` repo-wide; `--ignore-missing-imports`), informational; per-file ratchet; `api.py` later. | QI-12 §2.3 counts (164 strict) | `AGENT_GUIDE.md` §Development environment | count recorded; monotonically decreasing per release |
| B-12 | QI-11-03 (M) — MG-26 | `tests/test_assistant_page_render.py`, `tests/study/test_study_observatory.py` | Assert widget `.disabled` / named session keys / rendered labels; `set_value` only on enabled widgets behind a thin helper; never `proto.*`; `serial` marker. RUX: rewrite, never delete. | plan §4.3 / #478 lesson | `AGENT_GUIDE.md` AppTest rule | 0 `proto.` reads; 0 disabled `set_value` |
| B-13 | QI-10-05 (M) — MG-26 | `tests/conftest.py` (promote `isolate_apptest_globals`), `tests/test_classic_pages_apptest.py` (new smoke) | Shared AppTest fixture; smoke for `app.py`, Data (sample auto-load), Backtest (warning without `signals`); seed `signals`/`levels` before interaction; never `list(session_state)`. | QI-10 §3.6 verdict + §10 probes | `AGENT_GUIDE.md` AppTest rules | smoke green; per-page render < 1 s |
| B-14 | QI-10-08 (L) — MG-26 | `pyproject.toml` (`per-file-ignores`) | Narrow the `E402` ignore to `pages/1_Data.py` (or drop the bootstrap after a real editable install path is documented). | ruff | `AGENT_GUIDE.md` install -e / AppTest path | `ruff check` clean |
| B-15 | QI-11-05 (L) | `pyproject.toml [tool.pytest.ini_options]`, marker decorators | Markers `unit/integration/golden/eval/benchmark/oracle/serial` (warn-first); full suite stays the required cell; `serial` on AppTest files before any xdist. | none | `AGENT_GUIDE.md` §Development environment | `unit` subset < 5 min |
| B-16 | QI-11-06 (L) | `tests/study/test_study_schema.py`, `tests/study/test_study_execute.py`, `tests/test_backtest_grid_defaults.py` | Replace the 12 no-raise accept tests with returned-spec/token asserts; dir-lock re-acquire and `_fsync_file` cases assert state. Fixture consolidation only in a separate PR. | QI-11 §2.5 smell list | `AGENT_GUIDE.md` named-suite convention | **gate for C-1 / C-3** (validator refactors) |
| B-17 | QI-12-09 (L) | `pyproject.toml [tool.ruff.lint]` | Widen by one family, `B` first (`B023` loop-variable = C1 class; `B905`), tests excluded where noisy; never `S` on `tests/`; never `PLR2004` first. Warn-first per family. | QI-12 §2.5 counts | `AGENT_GUIDE.md` (already says one family per PR) | `ruff check` clean after each family |
| B-18 | QI-14-01 (M) — MG-27 | `tests/fixtures/cai_baseline.py` (`cai_levels_config`), `tests/benchmarks/cai_cold_path.py` | `--fixture realistic` runs on the tick-gated path (drop `poc_windows` or pass synthetic ticks after `disable_unneeded_tick_families`). Do not revive typical-price `_rolling_poc`. | QI-14 §9.3 | `CAI_BASELINE.md` Fixtures and commands; `AGENT_GUIDE.md` CAI note | `measure_cai_cold_path(kind="realistic")` emits six stage rows |
| B-19 | QI-05-13 (L) + contracts C9/C12 | `tests/test_validation.py` (key-set assert), `.importlinter` (`sim_core` contract, with B-10) | Mechanize the `validation_summary()` four-key freeze; `sim_core` ↛ `entry_window_policy` / `analytics.*`. | QI-5 §6.2; QI-4 §6.3 | `AGENT_GUIDE.md` battery `schema_version` table | asserts green |

**Exit (gates QR-C):** B-1/B-2 lock tests green · 8/8 default-on golden paths · `backtest.py` and `walk_forward.py` own-file mutation ≥ 70 % · coverage floor blocking at 82 % · import-linter and mypy jobs present (warn-first) · AppTest suite free of `proto.*` / disabled `set_value` · B-16 accept tests assert tokens.

### QR-C — Structural refactors (behavior-preserving)

**Owned open (27):** QI-01-02 · QI-01-06 · QI-03-01 · QI-03-02 · QI-03-03 · QI-03-10 · QI-04-01 · QI-04-09 · QI-05-01 · QI-05-03 · QI-05-14 · QI-06-01 · QI-06-02 · QI-06-04 · QI-06-05 · QI-06-10 · QI-06-11 · QI-07-02 · QI-07-03 · QI-07-07 · QI-08-01 · QI-08-02 · QI-08-04 · QI-09-01 · QI-09-02 · QI-14-05 · QI-14-09.
**Closed here:** QI-02-07, QI-02-08, QI-03-07, QI-07-08, QI-10-07 (wont-fix; §2.3).
**Regression-safety shape:** golden-gated **byte-identical** outputs (legacy + B-3 families); one hot spot per PR; CC/MI before → after in the PR body; no public signature change; §4.1 applies; **no `GOLDEN_REGEN` label may appear on a QR-C PR**; C-14/C-15/C-16/C-17/C-19/C-20 blocked until B-3 + B-4 exit criteria hold.

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| C-1 (pilot) | QI-03-03 (H) — MG-17 | `thesistester/setup.py` (`validate_setup_config`) | Declarative rule table (no pydantic) covering the existing clusters; error strings stable; `build_setup_config` unchanged. `BASE_COLUMNS` rejection (AH §2 item 10) and omitted-key defaults unchanged. | `tests/test_setup_config.py`, `tests/test_ah6_base_columns.py`; one row per cluster after extraction | `AGENT_GUIDE.md` build_setup / validate_setup_config | CC 69 → ≤ 20 stated; identical error strings on the existing negative cases; B-16 green |
| C-2 | QI-06-01 (H) — MG-17; rides QI-01-06 (L) | `thesistester/api.py` (`validate_run_spec`, allow-list tables), imports from `thesistester/data/loader.py` (`FORMAT_PROFILES`, `DERIVE_15S_SUPPORTED_PROFILES`) and `pages/1_Data.py` | Allow-list/validator table using the C-1 pattern; profile literals sourced from `loader` (builder `getattr` fallback kept per R17). Fail-closed outcomes byte-comparable. No composer collapse. | `tests/test_api.py`, `tests/test_cli.py`, `tests/test_assistant_execution_parity.py`; equality assert `api set == set(FORMAT_PROFILES)` | `ARCHITECTURE.md` R18 facade paragraph; `AGENT_GUIDE.md` facade + R17 | CC 104 → ≤ 25; `validate_run_spec` share of `api.py` < 15 %; parity hashes unchanged |
| C-3 | QI-07-03 (M) — MG-17 | `thesistester/study/schema.py` (`validate_study_spec`, `_validate_factors`, `_validate_constants`) | Declarative factor/report/ingest tables; expand re-checks reuse them. Omitted-key defaults unchanged (AH §2 item 9). | `tests/study/test_study_schema.py` (+ one row per supported axis) | `STUDY_RUNNER.md` §RS1; `AGENT_GUIDE.md` §Study | CC 46 → ≤ 20; Program B manifests validate clean |
| C-4 | QI-03-10 (M) — MG-17 | `pages/6_Signals.py` (generate path, delete `_normalize_3c_params`), `thesistester/setup.py` | Classic Signals generate calls `build_setup_config` for the setup dict only (still **not** `run_experiment`, AH §2 items 1–2). | Parity: page-6-equivalent kwargs vs `build_setup_config` hash for a saved setup incl. 3c params and `min_valid=0` (AO1) | `AGENT_GUIDE.md` build_setup is the SoT; `ARCHITECTURE.md` composers | Signals output byte-identical on the CAI fixture |
| C-5 | QI-06-02 (M) | `thesistester/reporting.py` (`build_markdown_report`) | Section builders / section table; emitted markdown byte-comparable on fixtures (A-4 banner already in place). | `tests/test_phase9_reporting.py` + section-order fixture | `USER_GUIDE.md` Report / Export only if wording moves | CC 152 → ≤ 20; markdown byte-identical |
| C-6 | QI-05-14 (L), QI-06-11 (L) — MG-29 | `thesistester/analytics/grid.py`, `overfitting.py`, `sensitivity.py`, `otf_validation.py`, `research_bundle.py` (`_hash_dataframe`), `pages/11_Report_Export.py` | Promote `_directional_grid_metrics`, `_SIMULATION_KWARGS`, `_default_otf_filter_config`, `_hash_dataframe` to public helpers (thin wrappers); inline/export `_dash_if_none`. Prerequisite for C-13/C-17 extracts. | existing directional/OTF/sensitivity asserts; `tests/test_golden_master.py` hash | `AGENT_GUIDE.md` analytics public surface; `ARCHITECTURE.md` hash projection | private cross-module imports 10 → ≤ 5 (`rg` count) |
| C-7 | QI-06-04 (M) — MG-01 | `thesistester/research_bundle.py` (18 key tables → one registry) | One registry: section → files → session keys → managed? → hashed?; generate `_MANAGED_RESEARCH_KEYS`, `_*_META_KEYS`, `_KNOWN_FILES`, `_SECTION_REQUIRED_FILES`, hash exclusions. | Registry completeness test; `tests/test_research_bundle.py`; golden bundle hash | `ARCHITECTURE.md` bundle members | canonical bundle hash unchanged; CC 75/63 → ≤ 25 |
| C-8 | QI-06-05 (M) — MG-16 | `thesistester/app_state.py` (split), new Streamlit-free store helper, one page adapter; `classic_*` lazy imports documented | Streamlit-free `bootstrap` logic + one-function page adapter; enables B-10's C8 contract. | `tests/test_app_state.py` without Streamlit runtime; AH4 skip-flag behavior kept | `ARCHITECTURE.md` R9 Streamlit-in-library paragraph; `AGENT_GUIDE.md` | eager Streamlit importers in library = 0 outside allow-list |
| C-9 | QI-08-02 (M) — MG-16 | `thesistester/journal/__init__.py`, `thesistester/journal/triggers.py` | Slim the barrel init; call public `classify_zone_triggers` (or lazy import) so importing `thesistester.journal` does not load `engine.backtest`. Call-ban unchanged. | Import test: journal import leaves `simulate_trades` unbound; `tests/test_journal_triggers.py` | `ARCHITECTURE.md` TJ boundary; `JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md` §3.2; `AGENT_GUIDE.md` JS | import-linter C7 kept |
| C-10 | QI-08-01 (M) | `thesistester/journal/pair.py`, `reconcile.py`, `counterfactual.py`, `rules.py`, `report.py` | One qty-scaled P&L helper used by `pair` then `_cost_row`; one shared `_cost_ticks`. Never copies 1-lot engine formulas (TJ §3.0). | Helper unit: points unscaled, currency/R/ticks × qty; AMP rewrite leaves points unchanged | `METRICS_GLOSSARY.md` journal block; `TRADE_JOURNAL_IMPLEMENTATION_PLAN.md` §3.0 | journal E2E artifacts byte-identical on the synthetic fixture |
| C-11 | QI-06-10 (M) | `thesistester/persistence/execution_artifacts.py` | Extract verify/publish/evict helpers behind existing path-containment guards; no cache-policy default change. | `tests/test_execution_artifacts.py`, `tests/test_cai3_cached_pipeline.py`, cold/warm hash tests | `ARCHITECTURE.md` cache vs identity | warm ↔ cold hashes equal; MI 0.00 → > 0 |
| C-12 | QI-01-02 (M) | `thesistester/persistence/local_store.py` (`save_dataset`) | Extract raw-sidecar / subtf-sidecar policy helpers; preserve/conflict and derive-without-subtf refusal unchanged (S1). | `tests/test_local_store.py`, `tests/test_15s_primary_persistence.py`; one row per sidecar conflict | `ARCHITECTURE.md` datasets layout / schema v1→v2 | store round-trips hash-identical |
| C-13 | QI-05-03 (M) | `thesistester/analytics/confluence_attribution.py` | Split pair/trigger summarizers from display-facing dataclass assembly; public combo helpers kept. After C-6. | `tests/test_confluence_attribution.py` | `AGENT_GUIDE.md` only if helpers move | MI 0.00 → > 0; combo tables byte-identical |
| C-14 | QI-03-01 (H) — MG-19 | `thesistester/engine/signals.py` (`generate_signals`) | Extract TF prep, zone-naked admission, trigger dispatch table. `_check_touch`, candidate sort key, 3c math (S3 / DA0) and public `VALID_TRIGGERS` untouched. **After B-3 + B-4.** | `tests/test_phase4_engine.py`, 3c/fade/OTF goldens (identity); per-phase unit tests | `AGENT_GUIDE.md` engine surface; `ARCHITECTURE.md` signal phases | CC 120 → ≤ 30; SHA-256 of `generate_signals` output identical on CAI + golden fixtures |
| C-15 | QI-14-05 (M) — MG-19 | `thesistester/engine/signals.py` | Replace `iterrows` with column arrays / `itertuples` behind the C-14 helpers; nullable dtypes only if hashes stay identical. After C-14. | goldens + CAI cold-path hash | `CAI_BASELINE.md`; `AGENT_GUIDE.md` | byte-identical; realistic e2e time recorded before/after |
| C-16 | QI-03-02 (H) — MG-19 | `thesistester/engine/signals_3c.py`, `thesistester/engine/signals.py` (3c mapping loops) | One shared 3c signal-row mapper; detectors byte-identical (S3). After C-14. | `tests/test_signals_3c.py`, `test_signals_3c_trigger_timeframe.py`, `test_ah5_sl_first_3c_entry.py` | `AGENT_GUIDE.md` (or `POINT_IN_TIME_GUARANTEES.md` only if projection semantics are named) | CC 59/55 → ≤ 30 each |
| C-17 | QI-05-01 (H) — MG-20 | `thesistester/analytics/walk_forward.py` (`run_walk_forward_sl_tp`) | Extract P0 validate / P3 train-grid / P5 stitch / P6 summary helpers. Fold construction and `causal_prefix` untouched (S5, AH §2 item 6). **After B-4 (WFA ≥ 70 %) and C-6.** | `tests/test_walk_forward.py`, `test_otf_integration.py`, `test_otf_validation.py` AH3 | `AGENT_GUIDE.md` WFA surface | CC 50 → ≤ 20; WFA artifacts byte-identical |
| C-18 | QI-04-09 (L) — MG-18 | `thesistester/engine/backtest.py` (token constants next to `_SKIPPED_SIGNAL_COLUMNS`), `analytics/entry_window.py` | Centralize skip/exit tokens as constants; string values unchanged. Prepares C-19. | Invariant test: every emit site ∈ frozen set; `partition_skip_counts` covers it | `USER_GUIDE.md` skip list only if values change (they must not) | goldens untouched |
| C-19 | QI-04-01 (H) — MG-18 | `thesistester/engine/backtest.py` (`simulate_trades` P7 → then P4/P6), `thesistester/engine/sim_core.py` | Extract **P7** (SL/TP + flatten + exit walk) behind the R22 boundary; then P4/P6 admission helpers. No public signature change; `sim_core` still holds no admission/P&L; AH §2.1 defaults, C1/AH1 flatten clock, 3c-void-no-skip (§5.3 item 22) untouched. **After B-3 + B-4 (backtest ≥ 70 %).** | `test_golden_master.py`, `test_otf_golden.py`, `test_entry_window_golden.py`, `test_fade_golden.py` + B-3 families; `test_ah1_session_flatten.py`; `test_ah5_*`; `test_phase5_backtest.py` | `SIMULATE_PERF.md` re-time; `AGENT_GUIDE.md` module rule | CC 133 → ≤ 40 stated (P7 helper ≤ 30); all goldens byte-identical; R22 ruler within noise |
| C-20 | QI-14-09 (L) — MG-18 | `thesistester/engine/sim_core.py` (`BarData`) | Store `float64` arrays inside `BarData`; `resolve_ohlc_bar` math unchanged. After C-19. | goldens + `tests/test_intrabar.py` + R22 benches | `SIMULATE_PERF.md` R22 core boundary | byte-identical; serial ruler recorded |
| C-21 | QI-09-01 (M) | `thesistester/assistant/results_overview.py` | Claim-format table (`path_pattern`, type, template, reject) + intent → builder table; auditor-safe strings and DI/RI/DX contracts unchanged. | `tests/test_assistant_results_qa.py`, `test_assistant_discuss_intelligence.py`, `test_assistant_research_intelligence.py`, LLM evals | `ARCHITECTURE.md` Discuss honesty paragraph | CC 120/73 → ≤ 30; evals green |
| C-22 | QI-09-02 (M) | `thesistester/assistant/explainer.py`, `help_corpus.py`, `orchestrator.py` (`handle_results_turn`) | Table-drive `_derive_caveats` and `score_corpus_chunk`; split `handle_results_turn` phases; channel contracts (RQ/HC/DI) unchanged. After C-21. | explainer / help_corpus / help_coverage / eval suites | `AGENT_GUIDE.md` assistant surface | CC 52/51/40 → ≤ 25 |
| C-23 | QI-07-02 (M) | `thesistester/study/execute.py` (`run_study`) | Extract confirm / lock / ledger-init / finalize helpers; public `run_study` signature and RS3 abort semantics unchanged. | `tests/study/test_study_execute.py`, `test_ah2_study_path_pin.py`; named leftover-running → re-queue probe (QI-7 §9) | `STUDY_RUNNER.md` §RS3 only if phase names documented | CC 60 → ≤ 25; 4-cell soft-resume probe identical |
| C-24 | QI-07-07 (M) | `thesistester/study/observatory.py`, `viewer.py`, `builder.py` | Observatory join vs desk vs lens split; builder hydrate/emit helpers; Streamlit/Plotly stay on pages; read-only guarantees kept (SO). | `tests/study/test_study_observatory.py` (post B-12), `test_study_viewer.py`, `test_study_builder.py` | `ARCHITECTURE.md` SO/SV module map | MI 0.00 → > 0 on the three modules; zero writes into study dirs |
| C-25 | QI-08-04 (M) | `thesistester/journal/match.py`, `report.py` (`_q4_q6`), `counterfactual.py`, `join.py` | Payload-to-table helpers from `_q4_q6` and `match._classify`; match classes and CF math unchanged. | journal match / report / counterfactual / join suites | `ARCHITECTURE.md` TJ8/TJ9 if helpers move | MI 0.00 → > 0; report artifacts byte-identical |

**Exit:** 0 F-grade functions in `engine/`, `analytics/`, `api.py` (E only with a documented reason); `reporting.py`, `api.py`, `engine/signals.py` MI > 0.00; library MI-0.00 count 28 → ≤ 14; all goldens unchanged.

### QR-D — UI decomposition and state lifecycle

**Owned open (10):** QI-01-01 · QI-02-04 · QI-03-04 · QI-03-05 · QI-03-12 · QI-04-05 · QI-05-02 · QI-07-01 · QI-09-03 · QI-10-03.
**Closed here:** none.
**Regression-safety shape:** presentation-only; RUX respected; session-key contract additive; every page gets a B-13 AppTest smoke **before** its split and the same smoke after.

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| D-1 | QI-10-03 (M) — MG-01 | `pages/1_Data.py` (clear lists), `thesistester/research_bundle.py` (managed set consumer), `thesistester/assistant/workspace.py` (`THESIS_SCOPED_STAGING_KEYS`), new key registry module | One research-key registry with flags (dataset-clear / apply-clear / thesis-clear / widget) generating the pop lists; additive-only for one release. | Registry completeness test (every managed key is dataset-clear or explicitly sticky) + session-key contract test (table ⊇ measured keys/consumers) | `ARCHITECTURE.md` leftover + nonce paragraph; session-key table | stale-state matrix (QI-10 §3.2) shows no leftover in any row |
| D-2 | QI-03-12 (M) — MG-01 | `pages/3_Setup_Builder.py` (save / set-active), `pages/6_Signals.py` | On setup save/set-active, pop or fingerprint-flag session `signals` the way dataset clear does; surface the existing controls-changed warning on view. | QI-10 stale-state row "setup mutation × Signals/Backtest" → page-helper test | `ARCHITECTURE.md` `setup_config` vs `signals` contract | stale candidates cannot reach Backtest unflagged |
| D-3 | QI-04-05 (M) — MG-22 | `pages/7_Backtest.py` → `*_page_helpers` | Extract sidebar settings, run/persist, display blocks; session keys unchanged. After A-1/A-2/A-20/A-21/A-22 (same file). | Helper unit tests for `effective_no_new_entries_after` and OTF TZ assembly; B-13 smoke before/after | `ARCHITECTURE.md` session-key table if keys move | MI 0.00 → > 0; smoke identical |
| D-4 | QI-05-02 (M) — MG-22 | `pages/10_Validation.py` → helpers | Extract sidebar, WFA/OTF run persist, Phase 8 display blocks. After A-3/A-4/A-5/A-6. | Helper tests for permutation copy and overlap-help assembly; smoke | `ARCHITECTURE.md` validation / WFA / OTF keys | MI 0.00 → > 0 |
| D-5 | QI-01-01 (M) — MG-22 | `pages/1_Data.py` | Extract module-level upload/save tree; split `_render_subtimeframe_upload` / `_render_tick_attach`. H10 admission untouched (locked). After A-8/A-22. | `tests/test_data_page_helpers.py`; smoke (sample auto-load) | `ARCHITECTURE.md` Data page keys; `AGENT_GUIDE.md` | MI 0.00 → > 0; D-grade renderers → C |
| D-6 | QI-02-04 (M) — MG-22 | `pages/2_Levels.py` (`_sync_levels_widget_state`, `_normalize_levels_settings`) | Drive snapshot setdefaults and widget sync from `DEFAULT_LEVELS_SETTINGS` / `normalize_levels_config`; no third default table; composers not collapsed. | `tests/test_stage6_levels_ui_settings.py`, `tests/test_levels_page_helpers.py` | `ARCHITECTURE.md` Stage-6 sync / snapshot helper | CC 39 → ≤ 20 |
| D-7 | QI-03-04 (M) — MG-22 | `pages/3_Setup_Builder.py` (`_sync_editor_widget_state`, fallbacks) | Drive widget sync from `build_setup_config` / `validate_setup_config` outputs (after C-1); split render vs sync. | `tests/test_setup_builder_helpers.py`; smoke | `ARCHITECTURE.md` `_setup_builder_*` keys | CC 47 → ≤ 20 |
| D-8 | QI-03-05 (M) — MG-22 / MG-24 | `pages/6_Signals.py` | Catch typed `ValueError` from engine/validate → `st.error` (no `st.exception`); delete or use `ANCHOR_DIAGNOSTIC_COLUMNS` / `_get_stored_signal_settings`; split render vs sync. After A-12/A-13/C-4. | Page-helper test that generate blockers stay typed; smoke | `USER_GUIDE.md` Signals errors | 0 `st.exception` on page 6 |
| D-9 | QI-07-01 (M) — MG-22 | `pages/15_Studies.py` | Extract Build section collectors/renderers; keep launch/inspect helpers; never in-process `run_study` (RS-D9). | `tests/study/test_study_builder.py`; smoke | `ARCHITECTURE.md` session-key table; `USER_GUIDE.md` Studies tabs | CC 73/59 → ≤ 30; `page15_run_study_call=false` |
| D-10 | QI-09-03 (M) — MG-22 | `pages/14_Research_Assistant.py` | Extract voice/sidecar and Advanced blocks into helpers; RUX layout and session keys unchanged. | 16 RUX page-render tests unchanged (rewrite never delete); sidecar URL/localhost helper tests | `ARCHITECTURE.md` presentation-only paragraph | RUX baseline green |

**Exit:** 0 pages at MI 0.00; one invalidation mechanism (registry) with a test; AppTest smoke for every classic page.

### QR-E — Application functions and features

**Owned open (10):** QI-02-03 · QI-02-05 · QI-03-09 · QI-03-11 · QI-06-07 · QI-08-05 · QI-09-10 · QI-09-11 · QI-14-03 · QI-14-06.
**Locked residuals (2):** QI-04-08 (optional skip rows for missing-entry / `confirm_3bar` void only; 3c void stays silent, §5.3 item 22) · QI-06-06 (label the three integrity bars on page 12; no hash gate).
**Closed here:** QI-05-15, QI-09-07, QI-09-09, QI-14-10 (wont-fix; §2.3).
**Regression-safety shape:** opt-in / additive; docs in the same PR; E-9/E-10 golden-gated byte-identical (R22: any acceleration equals serial goldens).

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| E-1 | QI-02-03 (M) | `pages/2_Levels.py` (`_calculate`), `thesistester/levels/tick_requirements.py` (shared formatter) | Route page Calculate through the same `product_tick_family_message` preflight (one refuse string across UI / API / Study). Refuse-without-ticks stays (AP/RP). | Composer-parity test: UI helper / `api.compute_levels` / `validate_study_spec` share the family substring | `USER_GUIDE.md` §Levels first-visit refuse; `ARCHITECTURE.md` | one message class; no typical fallback |
| E-2 | QI-02-05 (M) — MG-24 | `pages/2_Levels.py` (`_calculate_levels_transaction`, `_render_levels_calculation_status`) | Known `ValueError` refusals → `st.error` without `st.code(traceback)`; expander only for unexpected types. | Helper test: refuse status exposes `error_message` without traceback | `ARCHITECTURE.md` Levels calculation observability | no raw traceback on the refuse path |
| E-3 | QI-06-07 (M) — MG-24 | `thesistester/cli.py` (`main`), `thesistester/__main__.py` | Catch `ValueError`/`OSError` for the `run` verb; print `str(exc)`; return `EX_DATAERR` / `EX_NOINPUT`. | `tests/test_cli.py`: missing file / empty runs → rc ≠ 0, no `Traceback` in stderr | `AGENT_GUIDE.md` CLI errors | `study` / `journal` verbs unchanged |
| E-4 | QI-08-05 (M) | `thesistester/journal/cli.py`, `thesistester/journal/report.py` (`hidden_slice_count`) | Widen `--include-small-n` help and `hidden_slice_count` (or split counters) to Q3 zones/triggers; `REPORT_MIN_N=30` and default-hide unchanged. | Help-text assert; hidden count includes Q3 when present | `AGENT_GUIDE.md` Journal n<30 sentence | page 17 caption count matches CLI |
| E-5 | QI-09-11 (M) | `pages/14_Research_Assistant.py` (`min_valid_confluences` number_input) | `min_value=0` (AO1 legal) or caption that zero is YAML/Setup-Builder only. `validate_setup_config` untouched. | Widget min_value / copy assert; AO1 API accept tests kept | `USER_GUIDE.md` Assistant Draft setup | RUX layout unchanged |
| E-6 | QI-09-10 (L) — MG-12; residual of locked QI-06-06 | `pages/14_Research_Assistant.py` (Open exact caption), `pages/12_Research_Bundles.py` | Three-bar vocabulary (page-12 schema-only · assistant hash-fail-closed · open-exact) on both pages. No hash gate on page 12. | Copy assert on both pages; `test_ah4_p5_page_12_stays_schema_only` unchanged | `USER_GUIDE.md` Research Bundles + Open exact; `ARCHITECTURE.md` persistence bars | bars remain mechanically distinct |
| E-7 | QI-03-09 (L) | `pages/3_Setup_Builder.py` (naked controls) | Reuse the Signals any/all zone-level help on Setup Builder naked controls. Rides with A-12 if timing allows. | Copy guard | `USER_GUIDE.md` Setup Builder naked filters | admission unchanged (M5) |
| E-8 | QI-03-11 (L) | `pages/6_Signals.py` (`display_cols`) | Optional HTF/3c columns (`trigger_timestamp`, `trigger_timeframe`, `tested_level_price`) when non-null; `approach_side` stays out (DA4). After A-13. | Helper test that `display_cols` includes them when present | `ARCHITECTURE.md` preview subset; `USER_GUIDE.md` Signals table | `_SIGNAL_COLUMNS` unchanged |
| E-9 | QI-14-06 (M) | `thesistester/data/derive.py` (`derive_complete_parent_ohlcv`) | Vectorize the on-grid groupby under the locked `observed_aligned_15s_to_1m_v2` policy; sparse/misaligned diagnostics unchanged. | `tests/test_15s_*` byte-identical; derivation provenance | `ASSUMPTIONS` 15s path; `USER_GUIDE.md` Data 15s-primary | outputs hash-identical; 1-week derive time recorded |
| E-10 | QI-14-03 (M) — MG-18 | `thesistester/engine/sim_core.py` / C-19 P7 helper; `docs/SIMULATE_PERF.md` | W12 acceleration **only** inside the R22 boundary; serial equality on golden + B-3 fixtures; admission never parallelized. After C-19/C-20. | goldens + `tests/benchmarks/test_simulate_baseline.py` R22 scenarios | `SIMULATE_PERF.md`; `ASSUMPTIONS` W12; `ENGINEERING_PROPOSAL.md` R22 | byte-identical; no `GOLDEN_REGEN` |
| E-11 | residual of locked QI-04-08 | `thesistester/engine/backtest.py` (P4 `continue` sites) | **Only on CTO request (§7.2):** skip rows for missing-entry / `confirm_3bar` void; 3c void stays silent. `trades` byte-identical. | Skip-schema tests with `return_result=False` identity | `ASSUMPTIONS` §3; `USER_GUIDE.md` skip notes | goldens untouched |

**Exit:** no raw traceback on any classic page or CLI verb for typed refusals; operability rows closed; W12 row re-timed against `SIMULATE_PERF.md`.

### QR-F — Documentation consolidation

**Owned open (12):** QI-09-05 · QI-12-10 · QI-13-01 · QI-13-02 · QI-13-03 · QI-13-04 · QI-13-05 · QI-13-06 · QI-13-07 · QI-13-08 · QI-13-09 · QI-14-02.
**Duplicates listed under their primary (3):** QI-05-11 → QI-13-03 · QI-10-02 → QI-13-04 · QI-14-07 → QI-14-02.
**Locked residuals (docs only, 5):** QI-01-04 (parked mixed-offset reject; do not type/UTC-normalize) · QI-01-05 (identity keys name the H9 lock) · QI-02-01 (three levels planes; omit ⇒ on) · QI-05-10 (Grid = Backtest UI gate) · QI-14-04 (DEFAULT merge on CAI recipes).
**Closed here:** QI-02-06, QI-13-10 (wont-fix), QI-14-07 (duplicate).
**Regression-safety shape:** docs-only; Help-allowlisted files amended in place, never moved (HC rule 2); `test_help_corpus` and copy guards green.

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| F-1 | QI-13-01 (H), QI-12-10 (M) — MG-13 | `docs/ENGINEERING_ROADMAP.md`, `docs/QUALITY_INVESTIGATION_PLAN.md` §8.3, `docs/AGENT_GUIDE.md` CI table, `docs/ENGINEERING_PROPOSAL.md` §4 rule 9 / §7 | QI row rewritten from the merged report set (#479–#494 + this plan); tracker filled; drop the CI-red precondition; **"blocking on red" restored** because G-1 required checks are live (QI-12-10 / QI-13-01); Streamlit-minor risk row; QR status row. | Optional docs test: ROADMAP QI row names each existing `docs/quality/QI-*.md` | (this PR is docs) | link checker 0 broken |
| F-2 | QI-13-02 (M) | `README.md` Phase 4 | "five trigger types" → the seven `VALID_TRIGGERS` tokens; 3c four-rule text kept; file not moved. | Copy guard: README trigger list ⊇ `VALID_TRIGGERS` | — | Help-allowlist digest updated in place |
| F-3 | QI-13-05 (M) | `docs/README.md`, `docs/quality/README.md`, `docs/CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md` shelf pointer | Index CONFLUENCE_COMBO as contract-complete; DA/TJ/JS in exactly one shelf; list `docs/quality/` reports. | Optional link-coverage check | — | 0 orphan docs |
| F-4 | QI-13-03 (M) — MG-06 (+ dup QI-05-11) | `docs/METRICS_GLOSSARY.md` | **Delivered inside A-4** (same PR): Phase 8 + grid-overfit rows with diagnostic caveats. | Glossary needle test for the three labels | — | closes with A-4 |
| F-5 | QI-13-04 (M) — MG-01 (+ dup QI-10-02) | `docs/ARCHITECTURE.md` session-key table | Validation consumers of `data`/`levels`/`signals`; Portfolio consumer of `trades`; CAI-5 pointer for `classic_*`; widget keys stay out. Lands with D-1's contract test. | Session-key contract test (D-1) | — | table ⊇ measured research keys |
| F-6 | QI-13-07 (M) — MG-03; residuals of locked QI-05-10, QI-01-04, QI-01-05, QI-02-01, QI-14-04 | `docs/USER_GUIDE.md` (Session close, Data, Levels, Grid), `docs/ARCHITECTURE.md` (identity keys; levels defaults vs kwargs), `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/CAI_BASELINE.md` | Help-surface disclosure of locked forks: headless cutoff-without-flatten + Grid = Backtest gate (H7); parked mixed-offset reject (H11); `dataset_id` omits mode (H9); three levels planes / omit ⇒ on (H4); DEFAULT merge on CAI recipes. Pairs with A-22. | Copy guard on Session close H2 | — | every locked fork has a Help sentence |
| F-7 | QI-13-08 (M) — MG-11 | `docs/USER_GUIDE.md` Setup Builder | **Delivered inside A-12**: DA0 sentence in the Direction pitfall cell. | Copy guard | — | closes with A-12 |
| F-8 | QI-13-09 (M) — MG-05 | `docs/USER_GUIDE.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | **Delivered inside A-9**: omitted battery `enabled` ⇒ on for api/CLI; Study emit explicit `false`. | Help-text assert (A-9) | — | closes with A-9 |
| F-9 | QI-13-06 (M), QI-09-05 (M) — MG-16 | `docs/AGENT_GUIDE.md` (rule ledger), `docs/ARCHITECTURE.md` (AIA-0, import-ban paragraphs) | Rule ledger → pointers to the B-10 import-linter contract; strip `file:line` cites; AIA-0 names the lazy `st.secrets` fallback (or the Streamlit-free reader if C-8 extracts one). After B-10. | Cite checker (0 `file:line`) | — | 0 `file:line` cites; AIA-0 true |
| F-10 | QI-14-02 (M) — MG-27 (+ dup QI-14-07) | `docs/CAI_BASELINE.md` | Re-record realistic and small tables (incl. bundle row) on the tick-gated path after B-18; keep CAI-10 "no second signal cache yet". | B-18 harness output | `ENGINEERING_PROPOSAL.md` if it cites the 71 % sentence | tables reproducible from `--fixture both` |

**Exit:** `QI-15_SYNTHESIS.md` §5.6 docs-drift rows closed; `ENGINEERING_ROADMAP.md` carries QI (Completed) and QR (In progress) rows; AGENT_GUIDE has 0 `file:line` cites and points at mechanized contracts.

### QR-G — Dependency and supply-chain hygiene

**Owned open (6):** QI-07-09 · QI-12-01 · QI-12-02 · QI-12-03 · QI-12-06 · QI-12-08.
**Closed here:** none.
**Regression-safety shape:** tooling-only; version bumps never ride along with code PRs (`ENGINEERING_PROPOSAL` §7).

| PR | Findings | Files (expected) | Narrow change | Probe → regression test | Docs in same PR | Exit / merge gate |
|---|---|---|---|---|---|---|
| G-1 | QI-12-01 (H, Verified defect) — MG-13 | GitHub branch protection (settings; **applied** 2026-09-12: six frozen contexts, strict + enforce_admins), `docs/AGENT_GUIDE.md` | **Required status checks on `main`** for the six existing job names (`ruff (lint + format)`, `pytest (py3.10)`, `pytest (py3.11)`, `pytest (py3.12)`, `editable install (no dev extras)`, `golden-master regeneration guard`); job names frozen; no rename in the same change. Living doc must state the gate **is on** (do not leave “Accumu must apply” / “when live” as pending). | `gh api repos/…/branches/main --jq '.protection.required_status_checks.contexts'` shows the six names (`GET …/protection` is admin-only 403; 403 ≠ unprotected) | `AGENT_GUIDE.md` §Regression-safety gates in CI | blocking immediately (restores §4 rule 9) |
| G-2 | QI-12-02 (H, Verified defect) — MG-14 | `constraints.txt` (new), `.github/workflows/ci.yml`, `pyproject.toml`, `.github/dependabot.yml` (new) | Commit `pip-compile` constraints; CI installs with `-c constraints.txt`; name the pandas-major axis (py3.10 = pandas 2 cell); cap Streamlit minor (`<1.64`) **or** add a Streamlit-minor job; Dependabot/Renovate with the full matrix as gate for bumps. | Optional: assert `pandas.__version__` major per matrix cell; #478 AppTest/journal-join contracts kept | `AGENT_GUIDE.md` §Development environment; `ENGINEERING_PROPOSAL.md` §7 | next Streamlit/pandas bump arrives as a PR, not a silent resolve |
| G-3 | QI-12-03 (M) — MG-14 | `requirements.txt` (**deleted**), `README.md`, `.devcontainer/devcontainer.json` (install line) | **Deleted `requirements.txt`.** App/README/devcontainer install is `pip install -e .` (`-c constraints.txt`); `pytest` in the `dev` extra only. | N/A after delete (compiled-export probe does not apply) | `README.md` install; `AGENT_GUIDE.md` Fast start | one install SoT |
| G-4 | QI-12-06 (M, Security risk), QI-07-09 (L, Security risk) — MG-31 | `.github/workflows/ci.yml` (`bandit -ll`, `pip-audit`, SHA-pinned actions), `pyproject.toml [build-system]`, `thesistester/study/naming.py` | Warn-first `bandit` + `pip-audit` (declared + transitive); Actions pinned to SHAs; `setuptools` cap/bump; `hashlib.sha1(..., usedforsecurity=False)` (digest unchanged; RS2 run names identical) — SHA256 switch only as a dedicated identity PR. | `tests/study` naming/expand golden names unchanged; bandit baseline | `AGENT_GUIDE.md` §Development environment; optional `SECURITY.md` | bandit High = 0; blocking flip in its own PR |
| G-5 | QI-12-08 (M, Security risk) — MG-14 | `.devcontainer/devcontainer.json` | `pip install -e '.[dev]'`; drop the extra `streamlit` install; one CI Python; stop disabling XSRF/CORS. `.streamlit/config.toml` untouched. | Optional devcontainer build workflow | `AGENT_GUIDE.md`; `README.md` Codespaces | Codespaces = CI envelope |

**Exit:** six required checks visible in branch protection; `constraints.txt` tracked and used by CI; Dependabot open; `bandit`/`pip-audit` jobs present; 0 floating Action tags.

---

## 4. Wave sequencing (QI §9.2 applied)

| Wave | PRs | Content | Gate to next wave |
|---|---|---|---|
| **0 — gate and truth** (settings/docs only) | G-1 · G-2 · G-3 · F-1 · F-2 · F-3 | Required checks; constraints + named matrix + Dependabot; one install SoT; docs tell the truth about QI status and CI | six required checks visible; `constraints.txt` in CI |
| **1 — honesty first** (copy/disclosure/fail-closed; one PR per finding) | A-1 … A-22 (+ F-4/F-7/F-8 delivered inside A-4/A-12/A-9; F-6 with A-22) · B-1 · B-2 | Every High `app` row; H1 residual leftovers; fail-closed gaps; disclosure on both composers for locked forks with their lock-the-fork tests | all High `app`/docs rows `fixed_in`; B-1/B-2 green |
| **2 — safety net** (tests/tooling) | B-3 … B-19 · G-4 · G-5 · **C-1 pilot** (after B-16) | Golden families, mutation baseline, PIT generated FS, coverage floor, import-linter/mypy warn-first, AppTest rules, markers, ruff B, CAI harness, scanners | **B-3 + B-4 exit criteria**: 8/8 golden paths; `backtest.py` and `walk_forward.py` own-file mutation ≥ 70 % |
| **3 — structure, non-engine first** | C-2 … C-13 · D-1 · D-2 · F-5 · F-9 · F-10 | Validators, report templating, helper promotion, bundle registry, `app_state` split, journal init/helpers, store/analytics extracts; key registry + stale-signals | goldens unchanged; CC/MI before/after recorded per PR |
| **4 — engine core and UI** | C-14 … C-25 · D-3 … D-10 | `generate_signals` → 3c mapper → WFA → `simulate_trades` P7 → `BarData`; assistant/Study/journal tables; page splits | 0 F-grade in engine/analytics/api; 0 MI-0.00 pages |
| **5 — application and acceleration** | E-1 … E-11 | Operability/legibility; Signals HTF columns; derive vectorization; W12 acceleration inside R22 | success metrics §6 met or re-baselined with reasons |

**Hard rules:** QR-A before any C/D PR touching the same file (A-1/A-2/A-20/A-21/A-22 → D-3; A-3…A-6 → D-4; A-8/A-22 → D-5; A-12/A-13/C-4 → D-8; A-7 → C-7; A-4 → C-5; A-17 → C-17) · B-16 before C-1/C-3 · B-3 + B-4 before C-14/C-16/C-17/C-19/C-20 · C-1 before C-2/C-3/D-7 · C-6 before C-13/C-17 · C-14 before C-15/C-16 · C-19 before C-20/E-10 · B-10 before F-9 · B-18 before F-10 · G-1 before the docs say "blocking" again · every new gate warn-first for one release, blocking in its own PR · one hot spot per PR with CC/MI before → after · docs in the same PR · no feature scope creep from C/D PRs.

**Ongoing Study:** no wave requires stopping or rerunning a Study in flight (§1.3); Study-facing PRs (A-10, A-11, A-14, A-15, C-3, C-23, C-24, D-9) change report/validation/page code and helper structure only, never the ledger, cell bundles, or `run_batch` semantics.

---

## 5. PR acceptance checklist (QR; extends `ENGINEERING_PROPOSAL.md` §4.2)

- [ ] Cites the finding ID(s) and PR id from §3; on merge the PR link is recorded against those rows (`fixed_in` note), QI slice fields untouched.
- [ ] QR-A: the QI probe is a committed regression test, red before / green after; copy asserted by a guard.
- [ ] Golden-master tests unchanged; **no `GOLDEN_REGEN` label on a QR-C PR**; new families additive only (B-3).
- [ ] QR-C: CC and MI before → after in the PR body; no public signature change; byte-identical outputs on golden + feature-path fixtures; B-3/B-4 gates met for engine/WFA files.
- [ ] QR-B/G: gate introduced warn-first; documented in `AGENT_GUIDE.md` §Development environment; blocking flip is a separate PR.
- [ ] Locked rows: PR changes disclosure/tests only; the reviewer names the lock in the approval.
- [ ] Living docs amended in the same PR (column "Docs in same PR"); contract docs amended, not reopened; Help-allowlisted files never moved.
- [ ] "Regression safety" paragraph in the PR body with the `pytest -q` result quoted; for Study-facing PRs, one sentence confirming no ledger / bundle / `run_batch` change.
- [ ] No wording that calls a backtest, metric, or Study result correct or reliable.

---

## 6. Success metrics vs QI-0 baseline (indicative)

| Metric | QI-0 baseline (`6786713`) | Target | Owner PRs |
|---|---|---|---|
| Merges to `main` with a red required check | 37 / week; `protected: false` | 0; six required checks | G-1 |
| Dependency-induced failures caught before merge | 0 of 2 | 100 % via bump PRs on the full matrix | G-2 |
| Tracked dependency resolve | none | `constraints.txt` in CI; named pandas axis; Streamlit cap or job | G-2, G-3 |
| F-grade functions in `engine/` + `analytics/` + `api.py` | 11 | 0 (E only with a reason) | C-1, C-2, C-5, C-7, C-14, C-16, C-17, C-19 |
| Pages at MI 0.00 / library modules at MI 0.00 | 8 / 28 total | 0 / ≤ 14 | D-3…D-10 / C-11…C-13, C-21…C-25 |
| Prose-only import bans | 6 documented, 3 broken via chains | 100 % in `import-linter`, blocking, 0 broken | B-10, C-8, C-9, F-9 |
| Library modules importing Streamlit | 1 eager + 7 lazy | 0 outside an explicit allow-list | C-8, B-10 |
| Type-check errors (`engine/`+`analytics/`, strict) | 164 (not in CI) | in CI, monotonically decreasing, then blocking | B-11 |
| Mutation score (four sampled files) | 100 / 83.3 / 66.7–72.7 / 50–60 | ≥ 80 % each; ≥ 70 % before any QR-C touch | B-4 |
| Golden-gated default-on paths | 4 of 8 | 8 of 8 | B-3 |
| Coverage gate | informational 85 %; measured 82 %; 14 modules < 70 % | blocking 82 %, +1 pt/release; core packages ≥ 85 % | B-6, B-7, B-8, B-9 |
| Security / dependency scans | none | `bandit` + `pip-audit` blocking on High; Actions pinned | G-4 |
| Broad `except` "hides defect" class | 3 (QI-03-05, QI-05-12, QI-08-03) | 0; all 83 classified | A-16, A-17, D-8 |
| Open composer-parity divergences outside `locked` | 16 | 0; every locked fork has a test + disclosure on both composers | A-1…A-22, B-1, B-2 |
| Session-key table vs measured graph | 4 consumers missing; 16 aliased names | asserted by a test; one key registry | D-1, F-5 |
| PIT append-FS coverage | R3 named set | every emitted column | B-5 |
| Unit-marker suite wall time | one unmarked pile, ~2:15 | `unit` subset < 5 min; AppTest `serial` | B-15 |
| Honesty caveat per KPI page | Validation + Report only | Backtest / Grid / Time / Bundles + H5/H12/H13 copy | A-1, A-3, A-4, A-21 |
| CAI baseline reproducibility | realistic dies on tick gate | `--fixture both` runs; tables re-recorded | B-18, F-10 |

---

## 7. CTO decisions required

### 7.1 High-finding signature block (`QUALITY_INVESTIGATION_PLAN.md` §7.5 c)

Proposed in `QI-15_SYNTHESIS.md` §6 and restated here with PR ids. Sign, amend, or reject per row.

| Row | Finding | Proposed | PR | Signature |
|---|---|---|---|---|
| QI-12-01 | `main` unprotected | accepted | G-1 | ☐ |
| QI-12-02 | no constraints; accidental pandas split; Streamlit uncapped | accepted | G-2 | ☐ |
| QI-13-01 | ROADMAP / plan / "blocking" prose stale | accepted | F-1 | ☐ |
| QI-04-02 | Backtest Policy `allow_all` disclosure (H5) | accepted (copy only) | A-1 | ☐ |
| QI-05-09 | Grid Policy inherits H5 | accepted (same PR) | A-1 | ☐ |
| QI-05-04 | Focus ≠ Admit banner (H12) | accepted | A-3 | ☐ |
| QI-05-05 | Phase 8 `st.success` / label / export banner (H13) | accepted | A-4 | ☐ |
| QI-03-03 | `validate_setup_config` CC 69 | accepted (pilot) | C-1 | ☐ |
| QI-06-01 | `validate_run_spec` CC 104 | accepted after pilot | C-2 | ☐ |
| QI-05-01 | `run_walk_forward_sl_tp` CC 50 | accepted, gated on B-4 | C-17 | ☐ |
| QI-03-01 | `generate_signals` CC 120 | accepted, gated on B-3/B-4 | C-14 | ☐ |
| QI-03-02 | 3c detectors F-grade | deferred behind C-14 | C-16 | ☐ |
| QI-04-01 | `simulate_trades` CC 133 (P7 F) | accepted, gated on B-3/B-4 | C-19 | ☐ |

Medium `Verified defect` rows proposed accepted in the same signature: QI-06-03 (A-7), QI-10-01 (A-8), QI-08-03 (A-16). **Rejected: none.** Closures in §2.3 (13 `wont-fix`, 1 new `duplicate`) are proposed for the same signature.

### 7.2 Product decisions this plan does not take (parked / locked; AH8 or CTO only)

| Decision | Rows | Plan default until decided |
|---|---|---|
| H7 cutoff-without-flatten composer SoT | QI-04-03, QI-05-10 | A-22 disclosure + F-6 Help; B-1 lock test |
| H15 OTF/Admit timezone SoT | QI-04-04 | A-22 disclosure; B-1 lock test |
| H10 Data-page abort on `FATAL_OHLCV_CODES` | QI-01-03 | A-22 disclosure; B-2 lock test |
| H11 typed reject / UTC-normalize for mixed offsets | QI-01-04 | F-6 docs; B-2 recipe test; raw reject kept |
| H9 fold `ingestion_mode` into `dataset_id` | QI-01-05 | F-6 docs only |
| H4 collapse the three levels planes | QI-02-01, QI-14-04 | F-6 docs; D-6 removes the page's third table without changing planes |
| H8 flip omit-means-on | QI-06-08, QI-09-08, QI-13-09 | A-9 disclosure; default stays on |
| H14 snap projected zone prices to `base_end` vs disclose | QI-03-06 | A-13 disclosure; snap is a 3c-adjacent behavior change |
| 3c-void / missing-entry skip rows | QI-04-08 | silent; E-11 only on request |
| Page-12 hash gate | QI-06-06 | schema-only stays (AH §2 item 8); E-6 labels |
| Coworker-portable dataset pin rewrite | QI-07-10 | spec-parent-first stays; no residual |
| Delete `confirm_3bar` helpers / `_rolling_poc` typical body | QI-03-07, QI-02-07 (wont-fix) | reopen only if the CTO decides to delete |
| Wire or delete `require_tool_for_numbers` (VA) | QI-09-09 (wont-fix) | VA follow-up, not QR |
| Allow `wfa_median_test_expectancy_r` as Study `primary_metric` | QI-05-06 | A-11 documents; "allow" branch pre-scoped in A-11 |
| Fail-closed vs error-level warning for Quantower HE + omitted `ingestion_mode` | QI-07-05 | A-14 error-level warning |
| W15 page renumbering | QI-10-06 (wont-fix) | no action; optional USER_GUIDE note |

---

## 8. Status tracker

| Workstream | Status | PRs planned | Findings owned (open / locked residual / dup) |
|---|---|---:|---|
| QR-A Honesty and correctness | Not started (awaiting §7.5 gate) | 22 | 22 / 4 / 0 |
| QR-B Safety net | Not started | 19 | 19 / 0 / 0 |
| QR-C Structural refactors | Not started | 25 | 27 / 0 / 0 |
| QR-D UI decomposition / state | Not started | 10 | 10 / 0 / 0 |
| QR-E Application functions | Not started | 11 | 10 / 2 / 0 |
| QR-F Documentation | In progress (F-1 · F-2) | 10 (3 delivered inside QR-A PRs) | 12 / 5 / 3 |
| QR-G Dependency / supply chain | In progress (G-1 · G-2 · G-3) | 5 | 6 / 0 / 0 |
| Closed (no workstream) | — | — | 13 wont-fix · 1 locked without residual (QI-07-10) |
| **Total** | | **102 PR rows, 99 distinct** | **106 / 11 / 3 + 13 wont-fix + QI-07-10 = 134** |

Status vocabulary: `Not started` · `In progress` · `Blocked` · `Completed` · `Needs follow-up`. `ENGINEERING_ROADMAP.md` gets one QR row (F-1) that points here.

---

## 9. Risk register and stop conditions

| Risk | Mitigation |
|---|---|
| Metric theater — chasing CC changes behavior | B-3/B-4 exit criteria gate C-14…C-20; goldens byte-identical; one hot spot per PR; mutation ≥ 70 % before touching `backtest`/`walk_forward` |
| A disclosure PR quietly changes a locked default | checklist "locked rows: disclosure/tests only"; reviewer names the lock; B-1/B-2 lock tests fail on inversion |
| New CI gate blocks unrelated PRs | warn-first one release; blocking flip in its own PR |
| Dependency bump rides with code | Dependabot PRs separate and matrix-gated (G-2) |
| Page split changes rendered structure | B-13 smoke before/after; RUX baseline untouched for page 14 |
| Key registry (D-1 / C-7) drops a key a page still reads | session-key contract test lands first; additive-only for one release |
| Golden family recording picks up a non-default path | recorder uses `simulate_trades` keyword defaults except the one path under test; README table names the flag |
| An in-flight Study is disturbed by a QR merge | no QR PR touches ledger / cell bundles / `run_batch`; engine PRs are byte-identical; a running process keeps its imported code (§1.3) |
| Closed rows hide a real defect | every closure has a one-line rationale (§2.3) and a reopen condition in §7.2 where applicable; closures are part of the §7.1 signature |

**Stop and escalate** to the CTO when a QR PR would: change any `disposition=locked` behavior; require golden regeneration of a legacy family; move a Help-allowlisted file; touch `results/studies/` or the Study ledger; or reveal a fill/P&L discrepancy (that is an audit item, not a QR item).
