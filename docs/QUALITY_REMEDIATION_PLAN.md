# Quality Remediation Plan — QR series (DRAFT)

**Document type:** Remediation program derived from the Quality Investigation (QI) synthesis
**Date:** 2026-09-12 (draft written by QI-15 on `main @ 0b2c451`; review-pass same day: QI-01-04 residual → QR-F, MG mis-tags on C-4/C-12/C-13, tracker 21/4 and 16/5)
**Series code:** **QR** (Quality Remediation). Workstreams **QR-A … QR-G** as fixed by `docs/QUALITY_INVESTIGATION_PLAN.md` §9.1.
**Status:** **DRAFT — nothing in this document is authorized work until the CTO review gate (`QUALITY_INVESTIGATION_PLAN.md` §7.5) is signed and this plan is approved.** Opening any QR PR before that is a process breach.
**Inputs:** `docs/quality/QI-15_SYNTHESIS.md` (views, scores, CTO proposals), `docs/quality/findings.csv` (134 rows with `merge_group` / `score` / `qr_workstream` / `disposition`), `docs/quality/QI-01…QI-14` reports, `docs/quality/QI-00_BASELINE.md` (metrics baseline).
**Locked premises (never reopened by QR):** `AUDIT_FINAL.md` §5 and §7 (`origin/cursor/audit-final-merge-3a8e`), `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1, every completed series' contract doc (AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX/RS/SB/SIA/SV/SO/SAF/LC/WMV/TV/AP/RP/DA/TJ/JS/AO/SW/AH), `ENGINEERING_PROPOSAL.md` §4 (regression-safety framework, incl. §4.1 golden-master spec and §4.2 PR checklist).

> **Financial caution.** QR fixes disclosure, structure, tests, and tooling. No QR PR may describe a backtest, metric, or Study result as correct or reliable; QR-A copy states *what the number is and is not*, it does not certify it.

---

## 1. Purpose, scope, and what QI found

QI-1…QI-14 produced **134 findings** (0 Critical · 13 High · 90 Medium · 31 Low; 111 Verified · 10 Strong · 13 Design-limitation `n/a`). After synthesis: **119 open**, **12 locked** (behavior is an `AUDIT_FINAL` §5 / AH §2 premise; only a disclosure/test residual is QR work), **2 duplicate**, **1 wont-fix**, 0 closed-verified rows (closed carry-overs live in the synthesis §5.7 register).

The shape of the debt (synthesis §5.1, §5.6):

1. **Process breach, not math breach.** The regression-safety gate is not operating (`main` unprotected; 37 merges on red; two dependency-drift events in one week). No locked mathematical contract is breached by shipped code.
2. **Honesty surface lags the locked design.** Every locked two-composer fork (H4/H7/H8/H9/H10/H11/H15) and every High `app` row (H5/H12/H13) is a *disclosure* gap on a page or Help surface — copy-only fixes with financial-misread impact.
3. **Structure is where the audit defects lived.** Eleven F-grade functions in `engine/`, `analytics/`, `api.py`; the top four (`build_markdown_report` 152, `simulate_trades` 133, `generate_signals` 120, `validate_run_spec` 104) carry 30+ findings between them. Refactoring them before the safety net exists is the plan's own top risk.
4. **Safety net is shallow where it matters.** Goldens cover 4 of 8 default-on execution paths; own-file mutation on `walk_forward.py` is 50–60 % and on `backtest.py` 66.7–72.7 %; four locked forks have no lock-the-fork test; import bans are prose.

Scope of QR is exactly the 119 open rows plus the disclosure/test residuals of the 12 locked rows. **Out of scope:** any product decision listed in §7.2 (AH8 / CTO only), any reopening of a completed series, any golden regeneration outside a dedicated `GOLDEN_REGEN` PR.

---

## 2. Guardrails (all QR PRs)

1. **`ENGINEERING_PROPOSAL.md` §4 applies in full**, including §4.1 (golden-master operational spec) and §4.2 (PR acceptance checklist), extended by §5 below.
2. **Sequencing rules of `QUALITY_INVESTIGATION_PLAN.md` §9.2 are non-negotiable:** QR-A before anything touching the same file; QR-B before QR-C; warn-first gates; one hot spot per PR with CC/MI before/after; docs in the same PR; no feature scope creep from QR-C/D.
3. **Locked rows are premises.** A QR PR that changes the behavior of a `disposition=locked` row is rejected at review. Disclosure copy and lock-the-fork tests for those rows are allowed and listed below.
4. **Registry discipline.** Every QR PR cites ≥ 1 finding ID and, on merge, the PR link is recorded against those rows (a QR-owned `fixed_in` note; the QI slice fields are never edited). `findings.csv` remains the SoT for status.
5. **Isolation.** Throwaway `THESISTESTER_STORE_DIR` for any probe; no real keys; no desk PII.
6. **Financial vocabulary.** Use `QUALITY_INVESTIGATION_PLAN.md` §3.3 terms; never "correct", "proven", "reliable" for a number.

---

## 3. Workstreams

Each workstream lists: *fed by* · *open findings (exactly one owner each)* · *locked residuals (disclosure/test only)* · *proposed PR series* · *regression-safety shape* · *living docs amended* · *exit criteria*. Merge-group IDs (`MG-nn`) are defined in `QI-15_SYNTHESIS.md` §3.2.

### QR-A — Honesty and correctness fixes

**Fed by:** `app` findings, High rows, carry-over H-items, `Verified defect` rows (synthesis §6, §6.1).
**Open findings (21):** QI-03-06 (M) · QI-03-08 (M) · QI-04-02 (H) · QI-04-06 (M) · QI-04-10 (L) · QI-05-04 (H) · QI-05-05 (H) · QI-05-06 (M) · QI-05-07 (M) · QI-05-08 (M) · QI-05-09 (H) · QI-05-12 (M) · QI-06-03 (M) · QI-06-08 (M) · QI-06-09 (M) · QI-07-04 (M) · QI-07-05 (M) · QI-07-06 (M) · QI-08-03 (M) · QI-09-06 (L) · QI-10-01 (M).
**Locked residuals (disclosure only, 4):** QI-01-03 (H10 fork sentence) · QI-04-03 (H7 fork label on both composers) · QI-04-04 (H15 clock-fork label) · QI-09-08 (H8 omit=True sentence in Assistant). H11 (QI-01-04) is a QR-F docs residual — typed error only after AH8 unpark (§7.2), not QR-A.

**Proposed PR series (one PR per finding unless grouped by `MG`):**

| PR | Findings | Content (narrow) | Probe → regression test |
|---|---|---|---|
| A-1 | QI-04-02, QI-05-09 (MG-02) | `help=` / caption on Backtest and Grid **Policy** widgets: `allow_all` counts overlapping signals independently; skip table is empty by design. Default unchanged (AH §2.1). | two-candidate overlap recipe (`docs/quality/README.md`) → `tests/test_ui_copy_guards.py` assertion |
| A-2 | QI-04-06 (MG-02) | Persist + caption `direction_collision_diagnostic` next to the Backtest skip table (additive session key, not hashed) or state that classic UI does not show DA1. | `tests/test_backtest_direction_collision.py` extension |
| A-3 | QI-05-04 | One banner sentence on Time/Validation Focus surfaces: Focus fills may differ from Admit under `single_position` (AH §2 item 5 premise). No re-simulation. | H12 fixture (QI-5 §3) → copy guard |
| A-4 | QI-05-05, QI-13-03 (MG-06) | Replace Phase 8 `st.success` with `st.info`/caption; rename `P(mean R > 0)`; add export banner in `build_markdown_report` Validation Diagnostics; glossary rows (with QR-F). `validation_summary()` shape untouched. | `tests/test_phase9_reporting.py` + copy guard |
| A-5 | QI-05-07 | Caption `aggregate_test_total_r` as a fold-sum that may overlap; extend overlap help beyond stitched equity. Fold math untouched (S5). | copy guard |
| A-6 | QI-05-08 | Rewrite Grid ranking help; WFA heatmap caveat caption; drop or pair the OTF-matrix trophy prefix. | copy guard |
| A-7 | QI-06-03, QI-10-01 (MG-01) | Add `otf_validation_matrix/config/summary`, `skipped_signals`, `direction_collision_diagnostic` to `_MANAGED_RESEARCH_KEYS` (clear-only); align `_clear_dataset_dependent_state` with the AH4 leftover set; manage `display_timezone` on apply/switch. No page-12 hash (AH §2 item 8). | leftover probes (QI-6 §3.3, QI-10 §3.2) → `tests/test_research_bundle.py` `test_ah4_*` + `tests/test_data_page_helpers.py` |
| A-8 | QI-06-08, QI-09-08 (locked residual), QI-13-09 (MG-05) | CLI `--help` and Assistant confirm-run sentence: omitted battery `enabled` means **on** for api/CLI/assistant; Study emit stays explicit. Default unchanged (AH §2 item 9). | CLI help assert; copy guard |
| A-9 | QI-05-06, QI-07-04 (MG-08) | Study overview/rollup MD: labeled **Failed** section and failed count (rows stay in overview CSV / rollup N — `AUDIT_FINAL` §5.1 item 34). `primary_metric`: **document** that ranking ignores WFA OOS *unless* the CTO takes the "allow `wfa_median_test_expectancy_r`" decision (§7.2). | `tests/study/test_study_report.py`, rollup tests |
| A-10 | QI-03-08, QI-13-08 (MG-11) | DA0 disclosure (`touch`+`both`+`single_position` is long-only) as `help=` on Setup Builder and Signals Direction controls; USER_GUIDE pitfall cell (with QR-F). Admission unchanged. | copy guard |
| A-11 | QI-03-06 | H14 disclosure at the HTF+3c trigger widget and in ASSUMPTIONS: developing partners are as-of the early window, not HTF close. **Snap-to-`base_end` is a CTO decision (§7.2); not in this PR.** | `tests/test_signals_3c_trigger_timeframe.py` copy/disclosure assert |
| A-12 | QI-07-05 | `validate_study_spec`: error-level warning (or fail-closed, CTO choice) when `format_profile=quantower_history_exporter` and `ingestion_mode` omitted/primary. Does **not** rewrite to 15s-primary (AH §2 item 9). | `tests/study/test_study_schema.py` |
| A-13 | QI-07-06 | `study expand` Replay line + emitted `experiment.yaml`/overview MD carry the AGENT_GUIDE "not `study run`" clause. | expand CLI test |
| A-14 | QI-08-03 | Wrap `pdfplumber.open` failures as `JournalIngestError` in `extract_amp_pdf_text`. | junk-PDF fixture → `tests/test_journal_amp_statement.py` |
| A-15 | QI-05-12 | `otf_validation._simulate`: let typed engine errors propagate or record an error status per row; keep empty-input → empty frame. AH3 prefix slicing untouched. | OTF matrix test; remove the pragma with a named test |
| A-16 | QI-06-09 | Bundle member size cap before `ZipFile.read`; keep schema-only column policy. | adversarial zip recipe → `tests/test_research_bundle.py` |
| A-17 | QI-09-06 | Scrub secret-shaped keys from `AssistantRequest.to_dict()` before `append_conversation_message` (reuse `sidecar.redact_for_logs`). | `tests/test_assistant_orchestrator.py` redaction assert |
| A-18 | QI-04-10 | Backtest trade-table caption: `pnl_points` is the gross alias of `gross_pnl_points`; KPIs use net R (`AUDIT_FINAL` §5.3 item 25). | copy guard |
| A-19 | QI-01-03, QI-04-03, QI-04-04 (locked residuals) | One disclosure sentence per locked fork on **both** composers (Data page + `api.load_dataset` docstring; Backtest cutoff widget + `run_backtest` docstring; OTF TZ). Behavior untouched. | pairs with QR-B B-1 lock-the-fork tests |

**Regression-safety shape:** one PR per finding (or per `MG`); the QI probe becomes a committed test red→green **before** the copy change where a behavior surface exists; §4.2 checklist; **no golden regeneration** — A-7's additive managed keys and A-15's error propagation must leave `trades` byte-identical on goldens.
**Living docs amended in the same PR:** `USER_GUIDE.md` (Exposure, Focus vs Admit, Validation, Session close, Setup Builder, Assistant confirm-run, Studies), `ASSUMPTIONS_AND_LIMITATIONS.md` (H5/H12/H13/H14/H8 sentences, TJ2), `METRICS_GLOSSARY.md` (DA1, Phase 8, aggregate test total R), `ARCHITECTURE.md` (session-key table rows for `direction_collision_diagnostic`, leftover sentence), `STUDY_RUNNER.md` §RS3/§RS4/§SIA, `AGENT_GUIDE.md` CLI/Journal error notes.
**Exit:** every High `app` row and both H1 `Verified defect` rows show `fixed_in`; composer-parity ledger (synthesis §5.3) has 0 open entries whose fix is disclosure; each locked fork has a disclosure on both composers.

### QR-B — Safety net before refactor

**Fed by:** QI-11, QI-12, plus test-gap rows from QI-1/2/4/6/9/10/14.
**Open findings (19):** QI-01-07 (M) · QI-02-02 (M) · QI-04-07 (M) · QI-06-12 (L) · QI-09-04 (M) · QI-10-05 (M) · QI-10-08 (L) · QI-11-01 (M) · QI-11-02 (M) · QI-11-03 (M) · QI-11-04 (M) · QI-11-05 (L) · QI-11-06 (L) · QI-12-04 (M) · QI-12-05 (M) · QI-12-07 (M) · QI-12-09 (L) · QI-14-01 (M) · QI-14-08 (L).

**Proposed PR series (tooling/tests only; zero runtime change):**

| PR | Findings | Content | Gate mode |
|---|---|---|---|
| B-1 | QI-04-07, QI-01-07 (MG-03/MG-10; residuals of locked QI-04-03, QI-04-04, QI-01-03, QI-01-04) | Lock-the-fork tests: H7 (UI `None` vs YAML cutoff), H15 (`session_timezone` per composer), H10 (UI-helper vs `api.load_dataset` fatal admission), H11 (mixed-offset canonical recipe). Tests **fail if a fork is inverted**; product code untouched. | blocking (plain tests) |
| B-2 | QI-11-02 (MG-18) | Additive golden families for default-on paths not yet identity-gated: flatten-on, 3c filled/void, BE/trail, `same_bar_opposite_direction="legacy"`. Recorded via the §4.1 recorder; legacy families never regenerated. | blocking once recorded |
| B-3 | QI-11-04 (MG-18/MG-20) | Own-file asserts for `walk_forward` (overlap-reject stitch, `retention_ratio`, keep `test_otf_integration.py` in the sample) and `backtest` (BE with `allow_same_bar_exit=False`, path-label exit reasons, `both_hit_pct` diagnostic). Commit the `mutmut` sample recipe and baseline numbers to `AGENT_GUIDE.md`. | informational baseline → ≥ 70 % required before QR-C touches either file |
| B-4 | QI-02-02 | Generated append-future-shock test over every emitted level column (§5.5 set incl. `dOpen*`, `prevSettlement`, `pw*`, `pm*`, `pmVA*`) on the R3 fixtures. `trading_session_date` math not re-audited. | blocking |
| B-5 | QI-12-04, QI-11-01 (MG-15) | `--cov-fail-under` at the measured **82 %** warn-first, then blocking; direct tests for `levels/common.py`, journal `rules`/`ledger`, classic helpers; `__main__`/`sidecar`/`xai_realtime` classified untestable-by-design in `AGENT_GUIDE.md`. | warn-first → blocking |
| B-6 | QI-09-04, QI-06-12 (MG-15) | One dispatch/payload test per routed assistant capability ID; CLI process tests for `__main__` and error paths; unit tests for classic render helpers where QI-10's verdict allows. | blocking (plain tests) |
| B-7 | QI-12-07 | `import-linter` contracts C1–C5, C7–C10 from synthesis §5.4 (layers / `allow_indirect_imports` for `expand → cli → cli_study`; explicit Streamlit allow-list). Existing AST tests stay. | warn-first → blocking |
| B-8 | QI-12-05 | `mypy` job on `engine/` + `analytics/` (not `--strict` repo-wide); ratchet file list; `api.py` later. No config change to product code. | informational → per-file blocking |
| B-9 | QI-11-03, QI-10-05, QI-10-08 (MG-26) | AppTest harness: promote `isolate_apptest_globals`; assert `.disabled` / named session keys / labels, never `proto.*`, never `set_value` on disabled widgets, never `list(session_state)`; `serial` marker on AppTest files; narrow the `E402` per-file ignore to `pages/1_Data.py` (or drop after a real editable install). RUX: rewrite, never delete. | blocking (rewrites) |
| B-10 | QI-11-05, QI-11-06 | pytest markers `unit/integration/golden/eval/benchmark/oracle/serial`; assert returned spec/tokens on the 12 no-raise accept tests; optional shared `tests/fixtures/ohlcv.py` builder. Full suite stays the required cell. | warn-first markers |
| B-11 | QI-12-09 | Ruff family widening one PR per family, `B` first (`B023` loop-variable class), then `I`; never `S` on `tests/`; never `PLR2004` first. | warn-first per family |
| B-12 | QI-14-01, QI-14-08 (MG-27) | CAI harness: make `--fixture realistic` run on the tick-gated path (drop `poc_windows` or pass synthetic ticks after `disable_unneeded_tick_families`); informational stage timers on the warm path (hash equality stays the gate). Do not revive typical-price `_rolling_poc`. | informational |
| B-13 | C9, C11, C12 (synthesis §5.4) | Cheap contract tests: `sim_core` import contract; `validation_summary()` key-set assert; session-key contract test (table ⊇ measured research keys) — the last one lands with QR-D D-3's registry. | blocking |

**Regression-safety shape:** tooling-only PRs; every new CI gate is introduced *warn-first* for one release and made blocking in its own PR; golden families are additive; the AppTest rewrites keep every existing assertion's intent (RUX rule).
**Living docs amended:** `AGENT_GUIDE.md` §Development environment (coverage floor + untestable list, mutation recipe, AppTest rules, markers, import-linter, mypy), `tests/fixtures/golden/README.md` default-on branch table, `docs/CAI_BASELINE.md` fixtures section, `ENGINEERING_PROPOSAL.md` §4.1 cross-link.
**Exit (gates QR-C):** four lock-the-fork tests green; 8/8 default-on paths golden-gated; `backtest.py` and `walk_forward.py` own-file mutation ≥ 70 % (target 80 %); coverage floor blocking at 82 %; import-linter and mypy jobs present (warn-first); AppTest suite free of `proto.*` / disabled-`set_value`.

### QR-C — Structural refactors (behavior-preserving)

**Fed by:** hot-spot matrix (synthesis §5.2), `Maintainability risk` rows in library modules.
**Open findings (32):** QI-01-02 (M) · QI-01-06 (L) · QI-02-07 (L) · QI-02-08 (L) · QI-03-01 (H) · QI-03-02 (H) · QI-03-03 (H) · QI-03-07 (L) · QI-03-10 (M) · QI-04-01 (H) · QI-04-09 (L) · QI-05-01 (H) · QI-05-03 (M) · QI-05-14 (L) · QI-06-01 (H) · QI-06-02 (M) · QI-06-04 (M) · QI-06-05 (M) · QI-06-10 (M) · QI-06-11 (L) · QI-07-02 (M) · QI-07-03 (M) · QI-07-07 (M) · QI-07-08 (M) · QI-08-01 (M) · QI-08-02 (M) · QI-08-04 (M) · QI-09-01 (M) · QI-09-02 (M) · QI-10-07 (L) · QI-14-05 (M) · QI-14-09 (L).

**Proposed PR series (one hot spot per PR; CC/MI before → after in the PR body; byte-identical outputs on golden + feature fixtures):**

| PR | Findings | Content | Locked math that must not move |
|---|---|---|---|
| C-1 (pilot) | QI-03-03 (MG-17) | `validate_setup_config` → declarative rule table (no pydantic); error strings stable; `build_setup_config` unchanged. | AH §2 item 10 (`BASE_COLUMNS` rejected); omitted-key defaults |
| C-2 | QI-06-01 (MG-17) | `validate_run_spec` → allow-list/validator table using the C-1 pattern; fail-closed outcomes byte-comparable across `test_api` / `test_cli` / parity tests. | two composers (AH §2 items 1–2); H8 default |
| C-3 | QI-07-03, QI-07-08 (MG-17) | `study.schema` factor/report/ingest tables reused by `validate_study_spec`; Program B `validate_study_file` driven from `generate_packet`'s lock table. | AH §2 item 9; RS1 |
| C-4 | QI-03-10 (MG-17), QI-01-06 (singleton) | Classic Signals generate calls `build_setup_config` for the setup dict (still **not** `run_experiment`); delete page-6 `_normalize_3c_params`; import `FORMAT_PROFILES` / `DERIVE_15S_SUPPORTED_PROFILES` from `loader` in `api.py` and the Data page (builder `getattr` fallback kept per R17). | AH §2 items 1–2 |
| C-5 | QI-06-02 | `build_markdown_report` → section builders / section table; emitted markdown byte-comparable on `tests/test_phase9_reporting.py` fixtures. | none (H13 banner from A-4 rides on the template) |
| C-6 | QI-03-01, QI-14-05 (MG-19) | `generate_signals`: extract TF prep, zone-naked admission, trigger dispatch table; replace `iterrows` with column arrays / `itertuples` behind the existing trigger helpers. Requires B-2/B-3. | `_check_touch`, candidate sort key, 3c four-rule math (S3 / DA0); `VALID_TRIGGERS` public |
| C-7 | QI-03-02 (MG-19) | One shared 3c signal-row mapper; detectors byte-identical. After C-6. | S3 |
| C-8 | QI-05-01 (MG-20) | `run_walk_forward_sl_tp`: extract P0 validate / P3 train-grid / P5 stitch / P6 summary. Requires B-3 (WFA mutation ≥ 70 %). | fold construction, `causal_prefix` (S5, AH §2 item 6) |
| C-9 | QI-04-01, QI-04-09, QI-14-09 (MG-18) | `simulate_trades`: extract **P7** (SL/TP + flatten + exit walk) behind `sim_core`; then P4/P6 admission helpers; centralize skip/exit tokens next to `_SKIPPED_SIGNAL_COLUMNS` (values unchanged); `BarData` float64 arrays. Requires B-2 + B-3. | AH §2.1 defaults; C1/AH1 flatten clock; `sim_core` contains no admission/P&L (R22); 3c void = no skip (§5.3 item 22) |
| C-10 | QI-06-04 (MG-01) | One bundle registry (section → files → session keys → managed? → hashed?) generating the 18 lists. Golden bundle hash unchanged. | hashed `session_keys` set |
| C-11 | QI-06-05 (MG-16) | Split `app_state` into a Streamlit-free store helper + one-function page adapter; document remaining lazy chrome imports; enables B-7's C8 contract. | none |
| C-12 | QI-08-02 (MG-16), QI-08-01 (singleton) | Slim `journal/__init__.py`; call public `classify_zone_triggers` (or lazy import) so journal import does not load `engine.backtest`; one qty-scaled P&L helper shared by `pair` → `_cost_row`; one `_cost_ticks`. | TJ §3.0 qty scaling (do not copy 1-lot engine formulas) |
| C-13 | QI-06-11, QI-05-14 (MG-29), QI-06-10 (singleton) | `execution_artifacts` verify/publish/evict helpers behind existing path-containment guards; promote `_hash_dataframe`, `_directional_grid_metrics`, `_SIMULATION_KWARGS`, `_default_otf_filter_config` to public helpers. | cache-policy defaults |
| C-14 | QI-01-02 | `save_dataset`: extract raw-sidecar / subtf-sidecar policy helpers; preserve/conflict and derive-without-subtf refusal unchanged. | S1 |
| C-15 | QI-05-03 | `confluence_attribution`: split pair/trigger summarizers from display-facing assembly. | none |
| C-16 | QI-09-01, QI-09-02 | `results_overview`: claim-format table + intent→builder table; `_derive_caveats` / `score_corpus_chunk` table-driven; `handle_results_turn` phases. Auditor-safe strings and DI/RI/DX/RQ/HC contracts unchanged. | assistant honesty contracts |
| C-17 | QI-07-02, QI-07-07 | `run_study` confirm/lock/ledger-init/finalize helpers (RS3 abort semantics unchanged); observatory join vs desk vs lens split; Streamlit/Plotly stay on pages. | RS3, SO read-only |
| C-18 | QI-08-04 | Journal `_q4_q6` / `match._classify` payload-to-table helpers; match classes and CF math unchanged. | TJ7/TJ8 |
| C-19 | QI-02-07, QI-03-07, QI-02-08, QI-10-07 (MG-30 + singletons) | Quarantine/delete `_rolling_poc` typical body and `confirm_3bar` helpers **after** the CTO decision in §7.2; optional thin level-family protocol; implement or delete `consume_classic_nav_prefill(page_key)`. | AP/RP; `AUDIT_FINAL` §5.1 item 22 |

**Regression-safety shape:** golden-gated byte-identical outputs (legacy + additive families from B-2); one function per PR; CC target stated; no public signature change; §4.1 applies; C-6/C-8/C-9 blocked until B-2/B-3 exit criteria are met.
**Living docs amended:** `ARCHITECTURE.md` (signal phases, R18 facade paragraph, bundle registry, `app_state` split, TJ boundary), `AGENT_GUIDE.md` (engine/analytics surface, `build_setup` SoT, module rules), `SIMULATE_PERF.md` (re-time after C-9), `STUDY_RUNNER.md` §RS1/§RS3 if phase names are documented.
**Exit:** 0 F-grade functions in `engine/`, `analytics/`, `api.py` (E allowed with a documented reason); `reporting.py`, `api.py`, `engine/signals.py` MI > 0.00; all goldens unchanged (no `GOLDEN_REGEN` label used by QR-C).

### QR-D — UI decomposition and state lifecycle

**Fed by:** QI-10, MI-0.00 pages (MG-22), state-lifecycle rows (MG-01).
**Open findings (10):** QI-01-01 (M) · QI-02-04 (M) · QI-03-04 (M) · QI-03-05 (M) · QI-03-12 (M) · QI-04-05 (M) · QI-05-02 (M) · QI-07-01 (M) · QI-09-03 (M) · QI-10-03 (M).

| PR | Findings | Content |
|---|---|---|
| D-1 | QI-10-03, QI-03-12 (MG-01) | One research-key registry with flags (dataset-clear / apply-clear / thesis-clear / widget) generating the pop lists; on setup save/set-active, pop or fingerprint-flag session `signals` the way dataset clear does. Lands with B-13's session-key contract test. |
| D-2 | QI-04-05, QI-05-02 | Backtest and Validation: extract sidebar settings, run/persist, and display blocks into `*_page_helpers`; session keys unchanged; AppTest smoke (seeded state) per B-9 rules. |
| D-3 | QI-01-01 | Data page: extract module-level upload/save tree; split `_render_subtimeframe_upload` / `_render_tick_attach`; H10 admission untouched (locked). |
| D-4 | QI-02-04, QI-03-04 | Drive Levels snapshot setdefaults / widget sync from `DEFAULT_LEVELS_SETTINGS` + `normalize_levels_config`; drive Setup Builder widget sync from `build_setup_config` / `validate_setup_config` outputs (after C-1). |
| D-5 | QI-03-05 | Signals page: catch typed `ValueError` from engine/validate → `st.error` (no `st.exception`); delete/use `ANCHOR_DIAGNOSTIC_COLUMNS` / `_get_stored_signal_settings`; split render vs sync. |
| D-6 | QI-07-01 | Studies page: extract Build section collectors/renderers; keep launch/inspect helpers; never in-process `run_study` (RS-D9). |
| D-7 | QI-09-03 | Research Assistant page: extract voice/sidecar and Advanced blocks into helpers; RUX layout and session keys unchanged. |

**Regression-safety shape:** presentation-only PRs; RUX contract respected; session-key contract additive; each page gets an AppTest smoke (title + empty warning + named keys) before its split and the same smoke after.
**Living docs amended:** `ARCHITECTURE.md` session-key table + leftover/nonce paragraph, `USER_GUIDE.md` where page copy moves, `AGENT_GUIDE.md` AppTest rules (from B-9).
**Exit:** 0 pages at MI 0.00; one invalidation mechanism (registry) with a test; AppTest smoke for every classic page.

### QR-E — Application functions and features

**Fed by:** `app` Medium/Low + UX gaps + QI-14 performance (R22 rules).
**Open findings (15):** QI-02-03 (M) · QI-02-05 (M) · QI-03-09 (L) · QI-03-11 (L) · QI-05-15 (L) · QI-06-07 (M) · QI-08-05 (M) · QI-09-07 (L) · QI-09-09 (L) · QI-09-10 (L) · QI-09-11 (M) · QI-10-04 (M) · QI-14-03 (M) · QI-14-06 (M) · QI-14-10 (L).
**Locked residuals (2):** QI-04-08 (optional skip rows for *missing-entry* / `confirm_3bar` void only; 3c void stays silent per §5.3 item 22; golden-sensitive) · QI-06-06 (label the three integrity bars on page 12; no hash gate).

| PR | Findings | Content |
|---|---|---|
| E-1 | QI-10-04 | Reuse the Validation "diagnostic, not proof" one-liner on Backtest / Grid / Time / Bundles; Data caption pointing at the 400 MB websocket cap (cap unchanged). |
| E-2 | QI-02-03, QI-02-05 | Levels Calculate routed through the shared `product_tick_family_message` preflight (one refuse string); map known `ValueError` refusals to `st.error` without the traceback expander. Refuse-without-ticks stays (AP/RP). |
| E-3 | QI-06-07 | `cli.main` catches `ValueError`/`OSError` for `run`, prints `str(exc)`, returns `EX_DATAERR`/`EX_NOINPUT`. |
| E-4 | QI-08-05 | Widen `--include-small-n` help and `hidden_slice_count` (or split counters) to Q3 zones/triggers; `REPORT_MIN_N=30` unchanged. |
| E-5 | QI-09-11, QI-09-10, QI-06-06 (locked residual), QI-09-07 | Assistant Draft `min_valid_confluences` `min_value=0` (or AO1 caption); three-bar vocabulary on pages 12 and 14; reuse the OpenAI key unwrap/reject helper for xAI keys. |
| E-6 | QI-03-09, QI-03-11 | Naked any/all help on Setup Builder; optional HTF/3c columns (`trigger_timestamp`, `trigger_timeframe`, `tested_level_price`) in the Signals preview when non-null (`approach_side` stays out per DA4). |
| E-7 | QI-09-09, QI-05-15 | Wire or delete `require_tool_for_numbers` (VA default-off review); stop accepting / document the unused R19 `random_state`. |
| E-8 | QI-14-06 | Vectorize `derive_complete_parent_ohlcv` on-grid groupby under the locked v2 policy; sparse/misaligned diagnostics unchanged; hash-identical outputs. |
| E-9 | QI-14-03, QI-14-10 | W12 acceleration **only** inside `sim_core` / the C-9 P7 extract with serial golden equality on golden + feature fixtures; views instead of copies where folds do not mutate (S5 untouched). After C-9. |
| E-10 | QI-04-08 (locked residual) | Only if the CTO wants it: skip rows for missing-entry / `confirm_3bar` void; `trades` byte-identical on goldens. |

**Regression-safety shape:** opt-in / additive; docs in the same PR; E-8/E-9 are golden-gated byte-identical (R22 acceptance: any acceleration equals serial goldens).
**Living docs amended:** `USER_GUIDE.md` (Levels first-visit refuse, Signals table, Journal CLI, Assistant Draft/Open exact, Research Bundles), `ASSUMPTIONS_AND_LIMITATIONS.md` (15s path, W12, Voice agent), `AGENT_GUIDE.md` (CLI errors, R19 seed note), `VOICE_SIDECAR_OPS.md`, `SIMULATE_PERF.md`.
**Exit:** operability rows closed; no raw traceback on any classic page or CLI verb for typed refusals; W12 row re-timed against `SIMULATE_PERF.md`.

### QR-F — Documentation consolidation

**Fed by:** QI-13, docs-drift rows from other slices, disclosure residuals of locked rows.
**Open findings (16):** QI-02-06 (L) · QI-05-13 (L) · QI-09-05 (M) · QI-12-10 (M) · QI-13-01 (H) · QI-13-02 (M) · QI-13-03 (M) · QI-13-04 (M) · QI-13-05 (M) · QI-13-06 (M) · QI-13-07 (M) · QI-13-08 (M) · QI-13-09 (M) · QI-13-10 (L) · QI-14-02 (M) · QI-14-07 (L).
**Duplicates listed under their primary (2):** QI-05-11 → QI-13-03 · QI-10-02 → QI-13-04.
**Locked residuals (docs only, 5):** QI-01-04 (document the parked mixed-offset `ValueError`; do not type/UTC-normalize until AH8) · QI-01-05 (identity keys paragraph names the H9 lock) · QI-02-01 (label the three levels planes; omit ⇒ on) · QI-05-10 (Grid matches the Backtest UI gate) · QI-14-04 (DEFAULT merge on CAI recipes).

| PR | Findings | Content |
|---|---|---|
| F-1 (wave 0) | QI-13-01, QI-12-10 (MG-13) | `ENGINEERING_ROADMAP.md` QI row rewritten from the merged report set (#479–#493 + QI-15); plan §8.3 tracker filled; drop the CI-red precondition; "blocking on red" → "workflow fails; merge is not blocked until required checks are on" (until G-1 lands, then back to "blocking"); `ENGINEERING_PROPOSAL.md` §7 Streamlit-minor risk row; QR status row added. |
| F-2 (wave 0) | QI-13-02, QI-13-05 | README Phase 4 → seven `VALID_TRIGGERS` tokens (in-place, Help-frozen path); `docs/README.md` indexes `CONFLUENCE_COMBO_ATTRIBUTION_PLAN.md`, single shelf for DA/TJ/JS, lists `docs/quality/` reports. |
| F-3 | QI-13-03, QI-05-13 | `METRICS_GLOSSARY.md` rows: probability_positive, Phase 8 permutation p-value, grid-overfit Best/Median/delta (diagnostic caveats); `AGENT_GUIDE.md` battery `schema_version` table notes the frozen Phase 8 dict. Pairs with A-4. |
| F-4 | QI-13-04 (MG-01) | `ARCHITECTURE.md` session-key table: Validation consumers of `data`/`levels`/`signals`, Portfolio consumer of `trades`, CAI-5 pointer for `classic_*`; widget keys stay out. Pairs with D-1/B-13. |
| F-5 | QI-13-07, QI-13-08, QI-13-09, QI-05-10 (locked), QI-01-04 (locked), QI-01-05 (locked), QI-02-01 (locked), QI-14-04 (locked) | Help-surface disclosure of locked forks: Session close H2 (headless cutoff-without-flatten; Grid = Backtest UI gate), Setup Builder Direction pitfall (DA0), omit=True battery sentence (USER_GUIDE + ASSUMPTIONS), identity-keys paragraph (H9), parked mixed-offset reject (H11), three levels planes (H4), CAI DEFAULT merge. Pairs with A-8/A-10/A-19. |
| F-6 | QI-13-06, QI-09-05 (MG-16) | `AGENT_GUIDE.md` rule ledger → pointers to the import-linter contract (B-7); strip `file:line` cites; amend AIA-0 to name the lazy `st.secrets` fallback (or the extracted Streamlit-free reader if C-11 chooses that). |
| F-7 | QI-14-02, QI-14-07 (MG-27) | Re-record `CAI_BASELINE.md` realistic and small tables on the tick-gated path (after B-12); keep CAI-10 "no second signal cache yet" until warm stage timers exist. |
| F-8 | QI-02-06, QI-13-10 | USER_GUIDE §Levels compact token/family list (pointing at `catalog.py`); either HC-amend a small ASSUMPTIONS subset (TJ6/JS2/RS3) or state in USER_GUIDE Journal that Help caveats are the H2. HC allowlist rule 2 respected. |

**Regression-safety shape:** docs-only PRs; Help-allowlisted files amended in place, never moved (HC rule 2); `test_help_corpus` / copy guards green.
**Exit:** synthesis §5.6 "docs drift" rows closed; `ENGINEERING_ROADMAP.md` carries QI (Completed) and QR (In progress) rows; AGENT_GUIDE has 0 `file:line` cites and points at mechanized contracts.

### QR-G — Dependency and supply-chain hygiene

**Fed by:** QI-12.
**Open findings (6):** QI-07-09 (L) · QI-12-01 (H) · QI-12-02 (H) · QI-12-03 (M) · QI-12-06 (M) · QI-12-08 (M).

| PR | Findings | Content | Gate mode |
|---|---|---|---|
| G-1 (wave 0, settings) | QI-12-01 | **Required status checks on `main`** for the six existing job names (`ruff (lint + format)`, `pytest (py3.10)`, `pytest (py3.11)`, `pytest (py3.12)`, `editable install (no dev extras)`, `golden-master regeneration guard`); job names frozen. Record the setting in `AGENT_GUIDE.md`. | blocking immediately (restores §4 rule 9) |
| G-2 (wave 0) | QI-12-02, QI-12-03 (MG-14) | Commit `constraints.txt` compiled from `pyproject.toml`; CI installs with `-c constraints.txt`; name the pandas-major axis explicitly in the matrix (py3.10 = pandas 2 cell); cap Streamlit minor (`<1.64`) **or** add a Streamlit-minor job; `requirements.txt` becomes a compiled export of the caps (or is deleted with README pointing at `pip install -e .`); `pytest` out of the app file. | blocking (install path) |
| G-3 | QI-12-02 | Dependabot/Renovate config with the full matrix as the merge gate for bumps; version bumps as separate test-gated PRs (`ENGINEERING_PROPOSAL` §7). | warn-first PRs |
| G-4 | QI-12-06, QI-07-09 (MG-31) | `bandit -ll` and `pip-audit` (declared + transitive) CI jobs; Actions pinned to SHAs; `setuptools` cap/bump in `[build-system]`; `hashlib.sha1(..., usedforsecurity=False)` in `study/naming.py` (digest unchanged; run-name identity preserved) or SHA256[:10] in a dedicated identity PR. | warn-first → blocking on High |
| G-5 | QI-12-08 | Devcontainer: `pip install -e '.[dev]'`, drop the extra `streamlit` install, pick one CI Python, stop disabling XSRF/CORS. | n/a |

**Regression-safety shape:** tooling-only; no product change; version bumps never ride along with code PRs.
**Living docs amended:** `AGENT_GUIDE.md` §Development environment and §Regression-safety gates in CI, `ENGINEERING_PROPOSAL.md` §7 risk register, README install/Codespaces.
**Exit:** `gh api …/branches/main/protection` shows the six required checks; `constraints.txt` tracked and used by CI; Dependabot open; `bandit`/`pip-audit` jobs present; 0 floating Action tags.

---

## 4. Sequencing (waves)

Rules from `QUALITY_INVESTIGATION_PLAN.md` §9.2 are applied as ordered waves. A wave may start when its predecessors' *exit criteria that it depends on* are met; waves overlap only where no shared file is involved.

| Wave | Workstreams | Content | Gate to next |
|---|---|---|---|
| **0 — gate and truth** | QR-G G-1, G-2 · QR-F F-1, F-2 | Required checks; constraints + named matrix; docs tell the truth about QI status and CI | required checks visible in branch protection |
| **1 — honesty first** | QR-A A-1 … A-19 (one PR each) | Disclosure and fail-closed fixes; H1 residual leftovers | all High `app` rows `fixed_in`; probes committed as tests |
| **2 — safety net** | QR-B B-1 … B-13 · QR-G G-3 … G-5 · QR-C C-1 pilot | Lock-the-fork tests, golden families, mutation baseline, coverage floor, import-linter/mypy warn-first, AppTest rules, markers; first declarative-validator pilot | B-2 + B-3 exit criteria (8/8 golden paths; mutation ≥ 70 % on `backtest`/`walk_forward`) |
| **3 — structure (non-engine first)** | QR-C C-2 … C-5, C-10 … C-15 · QR-F F-3 … F-6 | Validators, report templating, bundle registry, `app_state` split, journal init, store/analytics helpers | goldens unchanged; CC/MI before/after recorded |
| **4 — engine core and UI** | QR-C C-6 … C-9, C-16 … C-19 · QR-D D-1 … D-7 | `generate_signals`, WFA, `simulate_trades` P7, assistant/Study tables; page splits and key registry | 0 F-grade in engine/analytics/api; 0 MI-0.00 pages |
| **5 — application and consolidation** | QR-E E-1 … E-10 · QR-F F-7, F-8 | Operability, legibility, W12 acceleration inside R22, CAI re-record, Help depth | success metrics §6 met or re-baselined with reasons |

Hard dependencies: A-x before any C/D PR touching the same file · B-2/B-3 before C-6/C-8/C-9 · C-1 before C-2/C-3/D-4 · C-9 before E-9 · B-12 before F-7 · B-7 before F-6 · G-1 before "blocking" wording returns to the docs.

---

## 5. PR acceptance checklist (QR; extends `ENGINEERING_PROPOSAL.md` §4.2)

- [ ] Cites finding ID(s) from `findings.csv`; on merge the PR link is recorded against those rows (`fixed_in`), slice fields untouched.
- [ ] Probe from the QI report committed as a regression test (red before, green after) for QR-A.
- [ ] Golden-master tests unchanged (or a dedicated `GOLDEN_REGEN` PR with CSV diff; never for QR-C).
- [ ] For QR-C: CC and MI before/after in the PR body; no public signature change; byte-identical outputs on golden + feature-path fixtures.
- [ ] For QR-B/G: gate introduced warn-first; documented in `AGENT_GUIDE.md` §Development environment.
- [ ] Locked rows: PR changes disclosure/tests only; a reviewer confirms no `disposition=locked` behavior moved.
- [ ] Living docs amended in the same PR; contract docs amended, not reopened.
- [ ] "Regression safety" paragraph in the PR body; `pytest -q` result quoted.
- [ ] No wording that calls a backtest, metric, or Study result correct or reliable.

---

## 6. Success metrics (indicative; set by QI-15 against the QI-0 baseline)

The full table with measurement commands is `QI-15_SYNTHESIS.md` §8. Headline targets:

| Metric | QI-0 baseline | Target | Owner |
|---|---|---|---|
| Merges to `main` with a red required check | 37 / week; `protected: false` | 0; six required checks | QR-G |
| Dependency-induced failures caught before merge | 0 of 2 | 100 % via bump PRs on the full matrix | QR-G |
| F-grade functions in `engine/` + `analytics/` + `api.py` | 11 | 0 (E only with a reason) | QR-C |
| Pages with MI 0.00 / library modules at MI 0.00 | 8 / 28 total | 0 / ≤ 14 | QR-D / QR-C |
| Prose-only import bans | 6 documented, 3 broken via chains | 100 % in `import-linter`, blocking, 0 broken | QR-B |
| Library modules importing Streamlit | 1 eager + 7 lazy | 0 outside an explicit allow-list | QR-C / QR-B |
| Type-check errors (`engine/`+`analytics/`) | 164 strict (not in CI) | in CI, monotonically decreasing, then blocking | QR-B |
| Mutation score (four sampled files) | 100 / 83.3 / 66.7–72.7 / 50–60 | ≥ 80 % each; ≥ 70 % before any QR-C touch | QR-B |
| Golden-gated default-on paths | 4 of 8 | 8 of 8 | QR-B |
| Coverage gate | informational 85 %; measured 82 % | blocking 82 %, ratchet +1/release; core packages ≥ 85 % | QR-B |
| Security/dependency scans | none | `bandit` + `pip-audit` blocking on High; Actions pinned | QR-G |
| Broad `except` "hides defect" class | 3 (QI-03-05, QI-05-12, QI-08-03) | 0; all 83 classified | QR-A / QR-D |
| Open composer-parity divergences outside `locked` | 16 | 0; every locked fork has a test + disclosure on both composers | QR-A / QR-B |
| Session-key table vs measured graph | 4 consumers missing; 16 aliased names | asserted by a test | QR-D / QR-B |
| Unit-marker suite wall time | one unmarked pile, ~2:15 | `unit` subset < 5 min; AppTest `serial` | QR-B |

---

## 7. Decisions required from the CTO

### 7.1 High-finding dispositions (proposed in `QI-15_SYNTHESIS.md` §6; sign or amend)

All thirteen High rows are proposed **accepted** (QI-03-02 **deferred** behind QI-03-01; QI-03-01 / QI-04-01 / QI-05-01 / QI-06-01 **gated** on QR-B exit criteria). Three Medium `Verified defect` rows (QI-06-03, QI-10-01, QI-08-03) are proposed accepted in the same signature. **Rejected: none.**

### 7.2 Product decisions this plan does not take (parked / locked; AH8 or CTO only)

| Decision | Rows | Plan default until decided |
|---|---|---|
| H7 cutoff-without-flatten composer SoT | QI-04-03, QI-05-10 | label the fork on both composers; lock-the-fork test |
| H15 OTF/Admit timezone SoT | QI-04-04 | label; lock-the-fork test |
| H10 Data-page abort on `FATAL_OHLCV_CODES` | QI-01-03 | document + test the fork |
| H11 typed reject / UTC-normalize for mixed offsets | QI-01-04 | test the recipe; keep raw reject |
| H9 fold `ingestion_mode` into `dataset_id` | QI-01-05 | docs only |
| H4 collapse the three levels planes | QI-02-01, QI-14-04 | label planes; document DEFAULT merge |
| H8 flip omit-means-on | QI-06-08, QI-09-08, QI-13-09 | disclose; default stays on |
| H14 snap projected zone prices to `base_end` vs disclose | QI-03-06 | disclose (A-11); snapping is a 3c-adjacent behavior change |
| 3c-void / missing-entry skip rows | QI-04-08 | keep silent; E-10 only on request |
| Page-12 hash gate | QI-06-06 | schema-only stays (AH §2 item 8) |
| Coworker-portable dataset pin rewrite | QI-07-10 | spec-parent-first stays |
| Delete `confirm_3bar` helpers / `_rolling_poc` typical body | QI-03-07, QI-02-07 | quarantine in C-19 after decision |
| Allow `wfa_median_test_expectancy_r` as Study `primary_metric` | QI-05-06 | document that ranking ignores WFA OOS (A-9) |
| Fail-closed vs error-level warning for Quantower HE + omitted `ingestion_mode` | QI-07-05 | error-level warning (A-12) |
| W15 page renumbering | QI-10-06 | **wont-fix** (proposed); optional USER_GUIDE note |

---

## 8. Status tracker

| Workstream | Status | PRs | Findings owned (open / locked residual / dup) |
|---|---|---|---|
| QR-A Honesty and correctness | Not started (awaiting §7.5 gate) | — | 21 / 4 / 0 |
| QR-B Safety net | Not started | — | 19 / 0 / 0 |
| QR-C Structural refactors | Not started | — | 32 / 0 / 0 |
| QR-D UI decomposition / state | Not started | — | 10 / 0 / 0 |
| QR-E Application functions | Not started | — | 15 / 2 / 0 |
| QR-F Documentation | Not started | — | 16 / 5 / 2 |
| QR-G Dependency / supply chain | Not started | — | 6 / 0 / 0 |
| **Total** | | | **119 / 11 / 2** (+ QI-07-10 locked with no residual, QI-10-06 wont-fix = 134) |

Status vocabulary: `Not started` · `In progress` · `Blocked` · `Completed` · `Needs follow-up`. `ENGINEERING_ROADMAP.md` gets one QR row (F-1) that points here.

---

## 9. Risk register and stop conditions

| Risk | Mitigation |
|---|---|
| Metric theater — chasing CC changes behavior | QR-B exit criteria gate QR-C; goldens byte-identical; one hot spot per PR; mutation ≥ 70 % before touching `backtest`/`walk_forward` |
| A disclosure PR quietly changes a locked default | checklist item "locked rows: disclosure/tests only"; reviewer names the lock in the approval |
| New CI gate blocks unrelated PRs | warn-first for one release; blocking flip in its own PR (§9.2 rule 3) |
| Dependency bump lands with code | Dependabot PRs are separate and test-gated (`ENGINEERING_PROPOSAL` §7) |
| Page split changes rendered structure | AppTest smoke before/after; RUX baseline untouched for page 14 |
| Registry (D-1 / C-10) drops a key that a page still reads | session-key contract test (B-13) lands first; additive-only for one release |
| Golden family recording picks up a non-default path | recorder uses `simulate_trades` keyword defaults except the one path under test; README table names the flag |

**Stop and escalate** to the CTO when a QR PR would: change any `disposition=locked` behavior; require golden regeneration of a legacy family; move a file listed in a Help-corpus allowlist; or reveal a fill/P&L discrepancy (that is an audit item, not a QR item).
