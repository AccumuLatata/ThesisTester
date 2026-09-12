# QI-10 — Streamlit UI layer and `st.session_state` contract

**Slice:** QI-10 (research-only)
**Status:** Completed
**Audited commit:** `32ad34c` (`32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc`) — `main` after merge of [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) (QI-11) on top of QI-0 / QI-3 / QI-4 / QI-6
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1, vulture 2.16
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi10-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data. No 400 MB frame generated.
**Finding count:** 8 (C/H/M/L = 0/0/5/3)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day.

`AUDIT_FINAL.md` §5 and `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 are premises. This slice does **not** propose Research Assistant layout changes (RUX locked) or hydrating classic state from Studies / Observatory / Journal. No backtest, metric, or Study result is described as correct or reliable.

**Review corrections (schema / honesty only; no product files):** `prior_id` on QI-10-05 dropped `plan §4.4 H-B` (plan §3.3 allows only `AUDIT_FINAL` `C*/H*/M*/L*` or `W*`). Invalidation inventory is **six** lists, not five; `dataset-clear ⊂ _MANAGED_RESEARCH_KEYS` is false (27 dataset-only keys, 39 managed-only including the AH4 leftover class). Key-graph **229** is unreproducible; review-pass is **162** `session_state` string-literal accesses vs **109** table names. Widget `backtest_*`/`grid_*` `key=` args are **58** (86 string literals with those prefixes), not ~80. Function lengths: `discuss_run` **62**, `render_discuss_this_run` **58**. First-pass claimed probe scripts were pasted in §10; they were not — review-pass essential snippets are pasted below. AppTest smoke re-verified (behavior identical; wall times vary).

## Commands run (verbatim)

```bash
git fetch origin main
git checkout main && git pull origin main   # 32ad34c
git checkout -b cursor/qi-10-ui-session-state-d0fb

export THESISTESTER_STORE_DIR=/tmp/qi10-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no                                          # before: 3966 passed, 5 skipped in 138.46s

radon cc app.py thesistester/classic_nav.py thesistester/timezone_display.py -s --total-average
radon mi app.py thesistester/classic_nav.py thesistester/timezone_display.py -s
vulture app.py thesistester/classic_nav.py thesistester/timezone_display.py --min-confidence 60
rg -n 'except Exception|except:' app.py thesistester/classic_nav.py thesistester/timezone_display.py
rg -c 'st\.session_state' pages
rg -n 'sys\.path|E402' pages app.py pyproject.toml

# probes (scripts under /tmp; transcripts /tmp/qi10-evidence/)
python3 /tmp/qi10_key_graph.py
python3 /tmp/qi10_invalidation.py
python3 /tmp/qi10_copy_errors.py
python3 /tmp/qi10_stale_matrix.py
python3 /tmp/qi10_leftover_and_nav.py
python3 /tmp/qi10_apptest_spike.py

export THESISTESTER_STORE_DIR=/tmp/qi10-store-after
pytest -q --tb=no                                          # after: 3966 passed, 5 skipped in 131.21s

# review-correction pass (same tree; docs/quality only)
python3 /tmp/qi10_review_probe.py
python3 /tmp/qi10_key_graph.py
python3 /tmp/qi10_apptest_spike.py
radon cc/mi + vulture --min-confidence 60 on owned files
rg -c 'st\.session_state' pages | awk -F: '{s+=$2} END {print s}'   # 1176

export THESISTESTER_STORE_DIR=/tmp/qi10-store-review-after
pytest -q --tb=no                                          # review-after: 3966 passed, 5 skipped in 133.41s
```

First-pass `/tmp/qi10_*.py` scripts were not retained and were not pasted. Review-pass scripts are in §10. They were never committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership)

| Path | LOC | Role |
|---|---:|---|
| `app.py` | 51 | Multipage home; reads `data` only |
| `thesistester/classic_nav.py` | 491 | CAI-8 Discuss / Open-exact / clarification nav; lazy Streamlit |
| `thesistester/timezone_display.py` | 105 | `display_timezone` contract + export conversion |
| `.streamlit/config.toml` | 7 | `maxUploadSize=350` / `maxMessageSize=400` |

**Read as spec (QI-13-owned):** `docs/ARCHITECTURE.md` §`st.session_state` contract + CAI-5/CAI-8 key tables; `docs/USER_GUIDE.md`.

**Read as graph sources (not owned):** all `pages/*.py` for producer/consumer / invalidation / copy only. `thesistester/app_state.py` and `research_bundle.py` are QI-6 (Streamlit-in-library / AH4 apply).

**Skipped**

- Page internals (QI-1…QI-9 exclusive). Observations that live inside one page go to Handoffs.
- Re-audit of AH4 leftover *math* (QI-06-03 already measured apply leftovers). This slice re-verifies **status** and adds the Data-page clear sibling.
- Allocating a >400 MB 15s frame (host RAM / time). `MessageSizeError` is judged from config + zero in-app handlers.
- Hydrating classic keys from Studies / Observatory / Journal (forbidden).
- Research Assistant layout (RUX locked).

---

## 2. Code-quality readout

### 2.1 Metrics (owned files)

| Metric | Value | Trigger? |
|---|---|---|
| `radon cc` (24 blocks) | average **B 5.54**. Highest: `discuss_run` C(18), `open_exact_run_in_backtest` C(15), `render_discuss_this_run` C(15), `convert_dataframe_timestamps_for_display` C(11) | No D+ |
| `radon mi` | `app.py` A **72.27** · `classic_nav.py` A **32.62** · `timezone_display.py` A **42.17** | None < 20 |
| Function length | `discuss_run` **62** lines; `open_exact` 56; `render_discuss` **58**. None > 150 | No |
| Broad `except` | 4: TZ nonexistent/ambiguous (narrow-guard OK); `discuss_run` `get_run` (fallback); `render_discuss_this_run` identity badge `except Exception` `# noqa: BLE001` (caption, does not swallow fills) | Classified; none hides a fill |
| `vulture` ≥60 | 7 symbols (`consume_classic_focus_run`, `open_exact_run_in_backtest`, `navigate_clarification_to_classic`, `render_*`, TZ converters) | **False positives** — page / Report callbacks |
| `TODO/FIXME` | 0 | — |
| Streamlit in library | `classic_nav.py` lazy `import streamlit` in two renderers (QI-06-05 already named the classic-* family; this file is the QI-10 instance) | Handoff QI-6 / QI-12 |
| Coverage (QI-0) | `classic_nav.py` **59%**; `timezone_display.py` **88%** | Handoff QI-11 |

`app.py` is a 51-line markdown landing page. No cyclomatic hot spot.

### 2.2 `E402` / `sys.path` bootstrap

`pyproject.toml` `[tool.ruff.lint.per-file-ignores]` sets `"pages/*.py" = ["E402"]` with the comment that pages bootstrap `sys.path` before importing `thesistester`.

Measured: **only** `pages/1_Data.py` inserts `REPO_ROOT` onto `sys.path`. The other 14 pages import `thesistester` at module top with no bootstrap. This VM has **no** `thesistester` dist-info (`pip show thesistester` → not found); imports succeed because the process cwd is the repo. `pip install -e .` is **not** what makes the other pages work here.

`AppTest.from_file("pages/7_Backtest.py")` still imported because the probe added `/workspace` to `sys.path`. A page script whose `sys.path[0]` is `pages/` (Streamlit / AppTest) relies on cwd or an editable install — except Data, which self-bootstraps. Finding QI-10-08. File owner of `pyproject.toml` is QI-12.

### 2.3 Widget-key vs research-key convention

Observed split (not a defect by itself):

| Namespace | Shape | In main ARCHITECTURE table? |
|---|---|---|
| Research artifacts | unprefixed nouns (`data`, `trades`, `signals`, `focused_trades`) | Yes (most) |
| Classic chrome | `classic_*` | **CAI-5 table**, not the main contract table |
| Assistant | `assistant_*` / `THESIS_SCOPED_STAGING_KEYS` | Assistant section, not main table |
| Studies / Observatory / Journal | `studies_*` / `observatory_*` / `journal_*` | Prose above the table (“must not be read from Data/Levels/Setup”) |
| Widgets | `backtest_sl_ticks`, `grid_*_widget`, `_tick_paths_text` | A few tick/uploader rows only |

Adherence is **mostly held**. Underscore prefix marks widget/nonce keys. The gap is that the **main** contract table is treated as SoT for “the session bus” while CAI-5 / widget / assistant keys live in other sections — QI-10-02.

### 2.4 Invalidation helpers — several mechanisms, not one

| Mechanism | Owner | What it clears | What it leaves |
|---|---|---|---|
| `_clear_dataset_dependent_state` | Data (QI-1) | levels, signals, trades, grid, WFA, batteries, portfolio, ticks, trade-review | **`focused_trades` / `focused_equity_curve` / `otf_filter_summary` / `skipped_signals` / `otf_validation_*` / `signal_settings` / `setup_config` / `display_timezone`** |
| `_clear_execution_dependent_state` | Data (QI-1) | execution + battery outputs only | levels, signals, Focus, OTF leftovers, setup |
| Uploader nonces + `_data_page_invalidate_source` | Data + bundle apply | leftover *upload widgets* | not research leftovers (AH4 sentence already says this) |
| `apply_research_bundle_to_session` + `_MANAGED_RESEARCH_KEYS` (99) | QI-6 | AH4 set incl. `setup_config`, `focused_trades`, `otf_filter_summary`, `signal_settings` | **`display_timezone`, `resampled_data`, `otf_validation_*`, `skipped_signals`, `direction_collision_diagnostic`** (QI-06-03) |
| `THESIS_SCOPED_STAGING_KEYS` (15) | QI-9 workspace | assistant drafts / focus / voice / UX mode on thesis switch | classic research keys (by design) |
| Levels fingerprint | QI-2 | flags stale; does **not** pop `signals` / `trades` | QI-03-12 / QI-04 leftover class |
| `init_classic_session_state` | QI-6 context | `setdefault` only | never clears leftovers |

**Six** invalidation/flag lists (not five). `init_classic_session_state` is `setdefault` only and is not an invalidation mechanism. Dataset-clear is **not** a subset of `_MANAGED_RESEARCH_KEYS` (27 keys in dataset-clear only; 39 managed keys not in dataset-clear, including the AH4 leftover class). Finding QI-10-03. Dataset-clear vs AH4 leftover-class disagreement is QI-10-01 (H1 residual on the UI lifecycle).

---

## 3. Application-quality readout (§3.2 + QI-10 checks)

Entry points: `app.py` (home), classic ↔ Assistant nav (`classic_nav.py`), timezone display/export, Streamlit transport caps. Individual page happy-paths are owned by QI-1…QI-9; this slice checks **cross-page** contract only.

### 3.1 Happy path / empty / malformed (cross-page)

| Check | Evidence | Verdict |
|---|---|---|
| Home empty | AppTest `app.py` 0.169 s: title `ThesisTester`; info “No data loaded yet — head to the **Data** page” | Empty OK |
| Home with data | Static: `if "data" in st.session_state` → success “Data loaded in session: N bars.” Not AppTest-seeded (home does not write `data`) | Copy OK |
| Data empty session | AppTest `pages/1_Data.py` 0.506 s: **Sample auto-load** — success “Loaded 12 bars.”; `data` / `dataset_id` / `instrument` / `display_timezone` / `exchange_timezone` present. Matches ARCHITECTURE “Sample auto-load applies only to empty sessions” | First-run gate works under AppTest |
| Backtest empty | AppTest 0.120 s: title `Backtest`; **0 main buttons**; `classic_nav_prefill` key present (`None` via `init_classic_session_state`). Source: warning + `st.stop()` if `signals` absent — chrome (prefill / Discuss) runs **before** the stop | Fail-closed, no traceback |
| Backtest + data, no signals | AppTest 0.161 s: same stop; `data` present; still 0 run widgets (sidebar is after the stop) | Cannot drive Run without seeding `signals` |
| Assistant control | AppTest 0.159 s: title `Research Assistant`; “Create or select a thesis”; no layout commentary | Smoke only |
| TZ helpers | `ensure_display_timezone` does not overwrite a valid current TZ. Naive stamp localize → warning, then convert | Display/export helper only — not a fill claim |
| Malformed bundle apply | Not re-run (QI-6). Typed `ValueError` on missing `session_values` reproduced when the first leftover probe passed raw zip bytes | QI-6 |
| Composer parity (§3.2.5) | QI-10 owns no simulate/generate path. Clarification nav maps only the four allowlisted classic pages; Observatory wording → `None` | N/A for fills |
| Persistence (§3.2.7) | QI-10 owns no store namespace. Open-exact restore is hash-gated CAI-8 (not re-audited) | N/A |

### 3.2 Stale-state matrix (mutation × downstream)

ARCHITECTURE expectation vs measured clear lists + leftover probes. “Pops” = key removed. “Flags” = stale banner, dependents left. “Leftover” = key remains and a downstream page can still read it.

| Mutation | Expected (ARCHITECTURE) | Observed | Downstream risk |
|---|---|---|---|
| Load / switch dataset (`_set_active_dataset_state` when `dataset_id` changes) | Dependents invalidated; Sample must not replace in-session bars | `_clear_dataset_dependent_state` pops levels/signals/trades/grid/WFA/batteries. **Does not** pop `focused_trades`, `otf_filter_summary`, `signal_settings`, `setup_config` (runtime: all four still `True` in session after the helper). `setup_config` popped only if `setup.dataset_id` mismatches | After a later Backtest, leftover `focused_trades` can arm the Focus overlay (`pages/7_Backtest.py` reads it). H1 class on **dataset switch**, not only bundle apply |
| Switch ingestion / attach 15s | Execution dependents cleared | `_clear_execution_dependent_state` — no levels/signals/Focus/OTF leftovers | Stale signals/levels can still be sent to Backtest |
| Recompute levels | Fingerprint flags stale levels | Page 2 flags; **no** pop of `signals` / `trades` | QI-03-12 / QI-04 handoff |
| Setup save / Set active | Dependents flagged or invalidated | Page 3 does not mention `signals` (QI-03-12) | Stale candidates |
| Regenerate signals | New `signals`; trades invalidated or flagged | Page 6 does not pop `trades` (QI-04) | Leftover trades |
| Re-backtest | New `trades`; time/validation flagged | Page 7 overwrites trades; does not pop `time_bucketed_trades` / `validation_summary` | Leftover Time/Validation |
| Import bundle (AH4) | Isolated snapshot; listed leftovers cleared; nonce ≠ leftovers | AH4 keys **clear**. Residual apply leftovers unchanged vs QI-06-03. `display_timezone` **survives** (`UTC` after a zip without that key). `bundle_import_omitted_data` **True** on dataset-less zip | QI-06-03 + QI-10-01 |
| Thesis switch | `THESIS_SCOPED_STAGING_KEYS` cleared; classic research keys untouched | Staging tuple is assistant-only (by design) | Do not hydrate classic from Assistant (locked) |

Full JSON: `/tmp/qi10-evidence/stale_matrix.json`.

### 3.3 Key graph vs `ARCHITECTURE.md` table

`session_state["…"]` / `.get` / `.pop` / `.setdefault` / `"…" in session_state` string literals on `app.py` + 15 pages + owned modules: **162** unique keys (review-pass; first-pass **229** is unreproducible and withdrawn). Main contract table: **109** names. `st.session_state` matching **lines**: **1,176** (`rg -c`, unchanged vs QI-0).

**Table keys absent as `session_state` string literals** (`in_table_not_code`, 16): `tick_paths`, `_tick_paths_text`, `_tick_upload_signature`, `_tick_uploader_nonce`, `tick_attach_warnings`, `tick_row_count`, `tick_session_count`, `bundle_import_omitted_data`, `derived_parent_diagnostics`, `direction_collision_diagnostic`, `portfolio_config`, `portfolio_trades`, `portfolio_drawdown_correlation`, `trade_review_buffer_rows`, `trade_review_trade_id`, `backtest_same_bar_opposite_direction`. Tick/bundle/portfolio names are **constant-aliased** (`TICK_PATHS_KEY`, `BUNDLE_IMPORT_OMITTED_DATA_KEY`) or written from API/apply. `backtest_same_bar_opposite_direction` is a widget `key=` token, not a `session_state["…"]` literal.

**Research consumers missing from the table** (literal `session_state` reads):

| Key | Table consumers | Extra measured consumers |
|---|---|---|
| `data` | Levels, Backtest, Grid, Bundles, TJ5 | **Validation** (`pages/10_Validation.py`) batteries / OTF source |
| `levels` | Setup, Signals, Backtest, Grid, Bundles | **Validation**; Assistant page (read-only, QI-9) |
| `signals` | Backtest, Grid, Report, Bundles | **Validation** |
| `trades` | Time, Validation, Report, Bundles | **Portfolio** (`pages/13_Portfolio.py`) |

**QI-10 chrome keys documented in the CAI-5 table, not the main consumer table:** `classic_active_run_id`, `classic_focus_run_id`, `classic_focus_channel`, `classic_nav_prefill`, `classic_pending_navigation`. `data_identity` / `levels_identity` (written by `open_exact_run_in_backtest` when restore omitted them) live in CAI-1 prose and `_MANAGED_RESEARCH_KEYS`, not the CAI-5 table and not the main consumer table.

**58 `backtest_*` / `grid_*` widget `key=` args** (86 string literals with those prefixes in the same file set) are correctly *not* in the research table. That is convention, not drift. First-pass “~80” is withdrawn.

Finding QI-10-02.

### 3.4 Honesty / copy / errors / transport

| Surface | OTF-not-at-signals | “diagnostic, not proof” | Focus post-hoc | `MessageSizeError` | Raw traceback |
|---|---|---|---|---|---|
| `app.py` | Yes (default-off + “not during signal generation”) | Weaker: “research diagnostics only, not trading advice” | — | no | no |
| Data | — | no | — | no | no |
| Levels | — | no | — | no | `st.code` traceback on calc failure |
| Setup | — | no | Admit vs Focus caption | no | no |
| Signals | **Yes** (“not on this page”) | no | — | no | `st.exception` ×2 (QI-03-05) |
| Backtest | — | no | Focus overlay captions | no | untyped `Exception` **re-raised** after ledger fail |
| Grid | — | no | — | no | no |
| Time | — | no | **Yes** | no | no |
| Validation | — | **Yes** (page banner) | — | no | no |
| Report | — | **Yes** | **Yes** | no | no |
| Bundles / Portfolio / Journal / Observatory / Assistant | — | no | — | no | Assistant: many `except Exception` (QI-9) |

`MessageSizeError` is documented in `USER_GUIDE.md` Data, `ARCHITECTURE.md` R9, `AGENT_GUIDE.md`, and `tests/test_streamlit_server_limits.py` (400 / 350). **Zero** hits in `pages/` or `app.py`. A >400 MB websocket payload would surface as Streamlit’s own error page, not an in-app caption. Finding QI-10-04.

### 3.5 `classic_nav` contract probes

| Probe | Result |
|---|---|
| Clarification map | dataset→Data; setup→Setup Builder; vwap→Levels; commission→Backtest; “observatory cohort”→`None` (no classic hydrate) |
| `consume_classic_nav_prefill(..., page_key="backtest")` after a Data-targeted prefill | **Consumes anyway** (`page_key` body is `pass`). Render helper checks `target_page` first, so the shipped UI is safe | QI-10-07 |
| Open-exact / Discuss | Unit-tested in `tests/test_classic_nav.py` (16 tests). Not re-audited. `vulture` unused = false friends |

### 3.6 AppTest feasibility verdict (QR-D input)

**Verdict: feasible for smoke + seeded-state tests; not feasible as an empty-page click-through of classic Data→Backtest.**

| Page | First render | Exception | Notes |
|---|---|---|---|
| `app.py` | 0.169 s first-pass / **0.167 s** review | none | Empty-state info |
| `pages/1_Data.py` | 0.506 s / **0.596 s** | none | Sample auto-load (12 bars). `sys.path` bootstrap works under AppTest |
| `pages/7_Backtest.py` empty | 0.120 s / **0.154 s** | none | `st.stop()` before sidebar; 0 run widgets |
| `pages/7_Backtest.py` + tiny `data` | 0.161 s / **0.115 s** | none | Still stopped (no `signals`) |
| `pages/14_Research_Assistant.py` | 0.159 s / **0.178 s** | none | Control; existing harness |

**Blockers / harness rules (Streamlit 1.63, same class as plan §4.3):**

1. `list(app.session_state)` / integer indexing raises `KeyError: st.session_state has no key "0"`. Assert **named keys** (`"data" in app.session_state`), never iterate the mapping.
2. Do **not** `set_value()` on disabled widgets (`AppTestError` — #478 / QI-11-03).
3. Promote `isolate_apptest_globals` (`sys.modules["__main__"]` + `sys.path` snapshot). AppTest of Data mutates both (page bootstrap).
4. Seed `signals` (and usually `levels`) before a Backtest interaction test; otherwise the page never instantiates SL/TP widgets.
5. `thesistester` is not an installed distro on this VM — AppTest must put the repo root on `sys.path` (Data self-bootstraps; Backtest does not).

QR-D should start with per-page **smoke** (title + empty warning + named session keys), then seeded interaction. Do not assert `proto.*`. Finding QI-10-05.

### 3.7 Performance envelope (handoff QI-14)

AppTest first-render with empty/sample session (not CAI realistic, not 15s): home 0.17 s · Data 0.51 s · Backtest 0.12 s. No RSS measured. Not a QI-10 finding.

---

## 4. Prior-audit carry-over status

| Item | Assigned | Status on `32ad34c` | Notes |
|---|---|---|---|
| **H1** leftover keys / dataset-less bootstrap (AH4, residual) | QI-6 / QI-10 | **Partial closed.** AH4-P1–P5 still the apply SoT (QI-6). Apply still clears `setup_config` / `focused_trades` / `otf_filter_summary` / `signal_settings`. Apply still **leaves** `display_timezone` (`UTC` reproduced). **New QI-10 residual:** `_clear_dataset_dependent_state` does **not** clear the AH4 leftover set — dataset switch is a second H1 surface | Do not reopen AH4 math. QI-10-01 |
| **W15** page numbering 4/5 | QI-10 | **Still present.** Files `1,2,3,6…17`. `tests/test_ui_copy_guards.py` asserts `5_Levels.py` / `2_Setup_Builder.py` do not exist | Cosmetic. QI-10-06 |
| Streamlit 1.63 AppTest | QI-11 / QI-10 | #478 rewrote the disabled `chat_input` test. Iteration of `session_state` is a **new** 1.63 pitfall for classic harnesses | QI-10-05 / QI-11-03 |

Locked premises not re-opened: two composers; do not hydrate classic from Studies/Observatory/Journal; RUX layout; page-12 schema-only.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Sev | Class | Title |
|---|---|---|---|
| QI-10-01 | Medium | Verified defect | H1 residual: dataset-clear leaves Focus/OTF/setup/`signal_settings`; apply leaves `display_timezone` |
| QI-10-02 | Medium | Documentation drift | Main session-key table missing Validation/Portfolio consumers; `classic_*` only in CAI-5 |
| QI-10-03 | Medium | Maintainability risk | Six invalidation lists; dataset-clear and AH4 managed disagree in both directions |
| QI-10-04 | Medium | UX/operability gap | Shared-concept copy uneven; `MessageSizeError` not on any page |
| QI-10-05 | Medium | Test-quality gap | Classic AppTest smoke is feasible; 1.63 `session_state` iteration + Backtest `st.stop` are harness rules |
| QI-10-06 | Low | Documentation drift | W15: page numbers still skip 4 and 5 |
| QI-10-07 | Low | Maintainability risk | `consume_classic_nav_prefill(page_key=…)` is a no-op |
| QI-10-08 | Low | Maintainability risk | Blanket `pages/*.py` E402 ignore; only Data bootstraps `sys.path`; package has no dist-info |

No Critical. No High. No finding proposes RUX layout or classic hydration from Studies.

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **Owned modules are not complexity hot spots.** No D+ / F-grade; MI A on `app.py` / `classic_nav.py` / `timezone_display.py`.
2. **AH4 *managed* leftovers still clear on apply** — leftover `setup_config` / `focused_trades` / `otf_filter_summary` / `signal_settings` gone after a backtest-only zip. `bundle_import_omitted_data` is True when the zip omits `data`. (QI-6 SoT; re-verified only.)
3. **Sample auto-load on empty Data** matches ARCHITECTURE / USER_GUIDE. AppTest: 12 bars, no exception. Navigation-must-not-replace is a Data-page rule (QI-1), not re-litigated.
4. **Backtest without `signals` fail-closes** with a warning and `st.stop()`, after chrome. No traceback on the empty path.
5. **`app.py` honesty copy** states research-diagnostics-only, validation-does-not-prove-edge, default `sl_first`, OTF default-off / not at signal generation.
6. **Signals page states OTF is not applied there** (ARCHITECTURE / USER_GUIDE). Setup captions Admit ≠ Focus.
7. **Validation and Report** already carry “diagnostic, not proof” / Focus post-hoc sentences.
8. **Timezone helper** does not overwrite a valid `display_timezone`; naive localize warns. `DISPLAY_TIMEZONE_KEY == "display_timezone"`.
9. **Clarification nav** maps only the four allowlisted classic pages; Observatory wording does not map (no classic hydrate).
10. **`.streamlit/config.toml`** is 350 / 400 and gated by `tests/test_streamlit_server_limits.py`.
11. **`classic_nav` public API is tested** (`tests/test_classic_nav.py`, 16 tests). vulture hits are Streamlit / caller false friends.
12. **AppTest smoke of `app.py`, Data, Backtest, Assistant does not raise** when the harness avoids `list(session_state)` and disabled `set_value`.

---

## 7. Handoffs to other slices

| To | Observation (not a finding here) |
|---|---|
| QI-1 | `_clear_dataset_dependent_state` / `_clear_execution_dependent_state` lists; Sample auto-load; tick constant keys |
| QI-2 | Levels fingerprint flags without popping `signals` / `trades`; `st.code` traceback |
| QI-3 | QI-03-05 `st.exception`; QI-03-12 setup does not pop `signals` |
| QI-4 | Leftover `trades` after signal regen; Backtest re-raises untyped `Exception`; Focus overlay reads leftover `focused_trades` |
| QI-5 | Validation already has the caveat; Grid/Time/Portfolio copy; leftover `validation_*` after re-backtest |
| QI-6 | QI-06-03 apply leftovers; `app_state` Streamlit import; lazy `classic_nav` Streamlit; `_MANAGED_RESEARCH_KEYS` vs dataset-clear |
| QI-7 / QI-8 / QI-9 | Isolated `studies_*` / `journal_*` / `assistant_*` namespaces — do not hydrate classic |
| QI-11 | AppTest isolate fixture; `list(session_state)` KeyError; classic_nav 59% coverage |
| QI-12 | E402 per-file-ignore; no editable dist-info; Streamlit-minor AppTest pitfalls |
| QI-13 | ARCHITECTURE table vs graph; USER_GUIDE H2 vs pages; W15 |
| QI-14 | AppTest first-render times (sample/empty only) |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/ARCHITECTURE.md` §`st.session_state` contract | Add Validation/Portfolio consumers; point at CAI-5 for `classic_*`; leftover sentence: dataset-clear ≠ AH4 managed set; `display_timezone` leftover |
| `docs/USER_GUIDE.md` | Page-numbering (W15) if QR renumbers; Data `MessageSizeError` is docs-only today; shared “diagnostic, not proof” if QR-E copies it to more pages |
| `docs/AGENT_GUIDE.md` | AppTest harness rules (named keys, no disabled `set_value`, isolate `__main__`); E402 / editable-install note |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Only if QR treats leftover Focus-after-dataset-switch as an honesty sentence |
| `docs/ENGINEERING_ROADMAP.md` | QR-D UI-test strategy once QI-15 scores QI-10-05 |

---

## 9. Exit criteria

| Exit | Delivered |
|---|---|
| Key graph diff vs ARCHITECTURE | §3.3 + `/tmp/qi10-evidence/key_graph.json` |
| Stale-state matrix | §3.2 |
| AppTest feasibility verdict | §3.6 — **feasible for smoke/seeded state; not for empty classic click-through** |
| Report + CSV + 10-line summary | this file + `findings.csv` QI-10-* rows |

---

## 10. Probe scripts (review-pass; not committed)

First-pass `/tmp/qi10_*.py` scripts were not retained. Review-pass scripts: `/tmp/qi10_review_probe.py`, `/tmp/qi10_key_graph.py`, `/tmp/qi10_apptest_spike.py`. Transcripts: `/tmp/qi10-review/`.

Leftover apply + dataset-clear + nav (review-pass on `32ad34c` product files):

```text
apply survive: display_timezone=true resampled_data=true otf_validation_*=true
               skipped_signals=true direction_collision_diagnostic=true
               setup_config=false focused_trades=false
               otf_filter_summary=false signal_settings=false
               bundle_import_omitted_data=true
dataset_clear survive: focused_trades=true otf_filter_summary=true
               signal_settings=true setup_config=true
               signals=false trades=false levels=false
dataset_clear ⊂ managed: FALSE (27 dataset-only; 39 managed-only)
nav: consume(page_key="backtest") still popped a Data-targeted prefill
session_state literals: 162; table names: 109; widget backtest_/grid_ key=: 58
```

AppTest (Streamlit 1.63; first-pass / review-pass):

```text
app_py         ok t=0.169 / 0.167  info=No data loaded yet
data_empty     ok t=0.506 / 0.596  success=Loaded 12 bars  (sample auto-load)
backtest_empty ok t=0.120 / 0.154  0 buttons (st.stop before sidebar)
assistant      ok t=0.159 / 0.178
list(session_state) → KeyError key "0"
```

Review-pass leftover + nav + clear-list diff (essential):

```python
from thesistester.research_bundle import (
    _MANAGED_RESEARCH_KEYS,
    apply_research_bundle_to_session,
)
from thesistester.classic_nav import (
    consume_classic_nav_prefill,
    set_classic_nav_prefill,
)

session = {
    "display_timezone": "UTC",
    "focused_trades": "FOCUS",
    "setup_config": {"x": 1},
    "signal_settings": {"y": 1},
    "otf_filter_summary": {"z": 1},
    "otf_validation_matrix": 1,
    "skipped_signals": 1,
}
apply_research_bundle_to_session({"session_values": {"trade_summary": {"n": 1}}}, session)
# display_timezone remains; AH4 leftovers cleared; bundle_import_omitted_data True

state = {}
set_classic_nav_prefill(state, target_page="pages/1_Data.py", note="check dataset")
consume_classic_nav_prefill(state, page_key="backtest")  # pops anyway
assert state.get("classic_nav_prefill") is None
```

---

## A.1 Full-suite guardrail

| Run | Command | Result |
|---|---|---|
| Before | `THESISTESTER_STORE_DIR=/tmp/qi10-store-before pytest -q --tb=no` | **3966 passed, 5 skipped in 138.46 s**, exit 0 |
| After | `THESISTESTER_STORE_DIR=/tmp/qi10-store-after pytest -q --tb=no` | **3966 passed, 5 skipped in 131.21 s**, exit 0 |
| Review-after | `THESISTESTER_STORE_DIR=/tmp/qi10-store-review-after pytest -q --tb=no` | **3966 passed, 5 skipped in 133.41 s**, exit 0 |

`git status --porcelain` must show only `docs/quality/QI-10_UI_SESSION_STATE.md` and `docs/quality/findings.csv`.

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
