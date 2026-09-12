# QI-08 — Trade journal and journal → study

**Slice:** QI-8 (research-only)
**Status:** Completed
**Audited commit:** `539dd2e` (`539dd2e9dabc9ba918f03b26f66537f3d9fca3ce`) — `main` after [#488](https://github.com/AccumuLatata/ThesisTester/pull/488) (QI-5)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, pytest 9.1.1, radon 6.0.1, vulture 2.16, pdfplumber 0.11.10
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi08-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data. No real AMP PDFs or broker statements.
**Finding count:** 5 (C/H/M/L = 0/0/5/0)
**Before/after `pytest -q`:** **3966 passed, 5 skipped** (141.26 s / 151.17 s) — identical pass/fail/skip. Porcelain: only the two `docs/quality/` files.
**Time spent:** one agent run on 2026-09-12.

Locked inputs treated as premises (not re-audited): `AUDIT_FINAL.md` §5; `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 / §2.1; TJ §3.0 clock/qty/PIT; TJ6 **tags ≠ triggers**; JS0 locks (do not implement JS3+, do not unpark Quantower Trades, do not add a 15s trigger lane). Plan §A.3 assigns **no** AUDIT H-items to this slice. No backtest, metric, or Study result is described as correct or reliable.

## Commands run (verbatim)

```bash
python3 --version
git rev-parse HEAD
git log -1 --format='%h %ad %s' --date=short

export THESISTESTER_STORE_DIR=/tmp/qi08-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no

radon cc thesistester/journal pages/17_Journal.py -s -n D --total-average
radon mi thesistester/journal pages/17_Journal.py -s
vulture thesistester/journal pages/17_Journal.py --min-confidence 60
rg -n 'except Exception|except:' thesistester/journal pages/17_Journal.py
rg -n 'type: ignore|noqa' thesistester/journal pages/17_Journal.py
rg -c 'st\.session_state' pages/17_Journal.py
rg -n 'from thesistester\.[\w.]+ import .*\b_[a-z]' thesistester/journal pages/17_Journal.py
rg -n '^import streamlit|^from streamlit' thesistester/journal
rg -n 'pdfplumber' thesistester pages
rg -n 'simulate_trades|compute_all_levels' thesistester/journal pages/17_Journal.py
bandit -r thesistester/journal -ll -q

export THESISTESTER_STORE_DIR=/tmp/qi08-store-probes
PYTHONPATH=/workspace python3 /tmp/qi08_probes.py
PYTHONPATH=/workspace python3 /tmp/qi08_import_trace.py
python3 -m thesistester journal --help
python3 -m thesistester journal reconcile --executions /tmp/qi08-e2e/tv.csv \
  --statements /tmp/qi08-e2e/amp.txt --output-dir /tmp/qi08-cli-e2e
python3 -m thesistester journal report --journal-dir /tmp/qi08-cli-e2e \
  --output-dir /tmp/qi08-cli-e2e/report
python3 -m thesistester journal reconcile --executions /tmp/qi08-e2e/tv.csv \
  --statements /tmp/qi08-pdf/junk.pdf --output-dir /tmp/qi08-cli-bad

pytest -q -p no:cacheprovider tests/test_journal_*.py
PYTHONHASHSEED=0 pytest -q -p no:cacheprovider tests/test_journal_tradesviz.py \
  tests/test_journal_amp_statement.py tests/test_journal_pair.py \
  tests/test_journal_reconcile.py tests/test_journal_report.py
PYTHONHASHSEED=1 pytest -q -p no:cacheprovider <same files>

export THESISTESTER_STORE_DIR=/tmp/qi08-store-after
pytest -q --tb=no
git status --porcelain
```

Probe scripts live under `/tmp/qi08_probes.py` and `/tmp/qi08_import_trace.py` (not committed). Transcripts: `/tmp/qi08-evidence/probes.json`, `/tmp/qi08-evidence/import_trace.json`.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-0 exclusive ownership)**

| Path | Role |
|---|---|
| `thesistester/journal/schema.py` | Typed records, closed vocabularies, honesty strings |
| `thesistester/journal/tradesviz.py` | TJ1 executions loader |
| `thesistester/journal/amp_statement.py` | TJ2 PDF extract + text parse (`pdfplumber` only here) |
| `thesistester/journal/pair.py` | TJ3 pairing + pre-cost P&L |
| `thesistester/journal/reconcile.py` | TJ4 AMP recon + cost rewrite |
| `thesistester/journal/join.py` | TJ5 15s/1m/tick join (`_join_trade` E 33) |
| `thesistester/journal/tags.py` + `tag_map.yaml` | TJ6 closed map |
| `thesistester/journal/levels.py` | TJ6 attribution (consumes built frame) |
| `thesistester/journal/zones.py` | JS1 `detect_confluence_zones` on previous 1m |
| `thesistester/journal/triggers.py` | JS2 inference |
| `thesistester/journal/counterfactual.py` | TJ7 replay / null |
| `thesistester/journal/rules.py` | TJ7 declared rules |
| `thesistester/journal/match.py` | TJ8 named-cell (`load_named_cell` E 35) |
| `thesistester/journal/ledger.py` | TJ8 forward ledger |
| `thesistester/journal/report.py` | TJ9 Q1–Q8 (`_q4_q6` E 36) |
| `thesistester/journal/cli.py` | `journal` verbs (no `ingest` / `propose`) |
| `thesistester/journal/__init__.py` | Barrel re-export |
| `pages/17_Journal.py` | Read-only page 17 |
| `examples/journal/zone_params_example.yaml` | Declared JS1 params example |

**Read as spec (QI-13 / QI-11 owned; not claimed):** `docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md`, `docs/JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md` TJ/JS2, `docs/USER_GUIDE.md` Journal H2, `docs/METRICS_GLOSSARY.md` journal metrics, `tests/fixtures/journal/**` (PII scan + shape only).

**Skipped**

- JS3 `propose.py` / JS4 multi-bundle — not in tree; do not implement.
- Quantower Trades loader — parked; not present.
- Re-auditing TJ6 tag-distance math or JS2 `_check_*` bodies (locked).
- AppTest of page 17 (QI-10 owns AppTest feasibility). Page copy/helpers were read statically + report API was exercised.
- Performance envelope on CAI `realistic` (QI-14). Journal path is ingest/report, not `simulate_trades`.
- Mutation sample (QI-11).

---

## 2. Code-quality readout

### 2.1 Metrics (journal + page 17)

| Metric | Value |
|---|---|
| LOC | 9,338 library + 209 page = **9,547** |
| `radon cc` D+ | `_q4_q6` E **36** (129 lines) · `load_named_cell` E **35** (70) · `_join_trade` E **33** (108) · `_q3_triggers` D **27** (87) · `match._classify` D **24** (128) · `rules._apply_one` D **23** (74). Average **B 5.99** over 366 blocks. **No F-grade** (CC ≥ 41) |
| MI = 0.00 | `match.py`, `report.py`, `counterfactual.py` (matches QI-00). `join.py` 7.27 · `rules.py` 8.88 · `levels.py` 9.71 — all < 20 trigger |
| Page 17 | MI **A 43.21**, 4 defs, 209 lines, 8 `st.session_state` lines |
| Broad `except` | **0** in journal + page 17 |
| `# type: ignore` | 5 (pair Literal casts) + 1 in report |
| Streamlit in library | **0** |
| `pdfplumber` | `amp_statement.py` only (lazy import) |
| `bandit -ll` | clean |
| `vulture` ≥60 | CLI entry points + dataclass fields + closed-set frozensets — **false friends** (public API / schema constants). No dead product function |

### 2.2 Import graph (plan §5 QI-8)

**Call sites:** no journal module imports or calls `simulate_trades` / `compute_all_levels`. `hasattr(thesistester.journal, "simulate_trades")` is False.

**Source imports (external `thesistester.*`):**

| Module | Imports |
|---|---|
| `tradesviz` / `join` / `zones` / `match` | `levels.session_date.trading_session_date` |
| `levels` | `levels.defaults.DEFAULT_LEVELS_SETTINGS`; `study.schema.closed_level_token_set` |
| `zones` | `engine.confluence.detect_confluence_zones` |
| `triggers` | `engine.signals._classify_zone_triggers_detail` (**private**) |
| `match` | `research_bundle.canonical_bundle_hash` |
| `report` | `persistence.local_store.get_store_root` |
| page 17 | `local_store.display_store_path` |

**Runtime:** `import thesistester` does **not** load `engine.backtest`. `import thesistester.journal.schema` **does** — because `journal/__init__.py` eagerly imports `triggers` / `zones` / `levels`, and `from thesistester.engine.signals` / `engine.confluence` executes `engine/__init__.py`, which re-exports `simulate_trades`. Finding QI-08-02. Call-site ban still holds.

`propose.py` absent. No Quantower Trades loader symbol.

### 2.3 Qty-scaled P&L formula homes (inventory)

TJ §3.0 / glossary formulas are implemented in **more than one write site**:

| Home | What it computes |
|---|---|
| `pair._closed_trade` | `gross_pnl_points` (not × qty); `gross_pnl_currency = points × pv × qty`; pre-cost `net = gross`; `r_multiple`; `net_ticks` |
| `reconcile._cost_row` | AMP `commission = per_side × 2 × qty`; rewrites `net_pnl_currency`, `fee_ticks`, `net_ticks`, `r_multiple`, `r_multiple_declared` |
| `counterfactual` + `rules` | Duplicate `_cost_ticks` (fee_ticks + day extra / tick_value); CF `gross = points × qty / tick` |
| `report._currency_to_ticks` | Read-side `currency / (tick × pv)` |

Probe 2-lot MNQ long 100→101: points **1.0** (not qty-scaled), currency **4.0**, net_ticks **8.0**, r **0.4** — matches §3.0. After AMP costs on the E2E 2-lot 1.25-pt trade: gross **$5.00**, commission **$2.48**, fee_ticks **4.96**, net_ticks **5.04**. Finding QI-08-01 (structure). The numbers are **not** a claim that a desk book is correct.

### 2.4 Hot-spot notes

- `_join_trade` E 33: 15s vs tick resolution, missing-bar / price-outside / excursion / roll flags. Branchy, 108 lines (under the 150-line length trigger).
- `load_named_cell` E 35: hash verify, corpus refuse, member read — the TJ8 trust boundary.
- `_q4_q6` E 36: JSON payload → Q4/Q5/Q6 tables. MI 0.00 on `report.py` (1,212 lines).
- `triggers` reuses `zones._as_*` / `_load_table` privates (intra-package). Cross-package leak is the signals private (QI-08-02).

---

## 3. Application-quality readout (§3.2 + QI-8 checks)

Entry points: CLI `journal {reconcile,attribute,counterfactual,match,zones,triggers,report}`; page 17 (report only). There is **no** `api.journal_*` and **no** `ingest` verb — `reconcile` is the ingest.

### 3.1 Happy path — synthetic ingest → reconcile → report

Throwaway TV CSV + AMP **text** (not a desk PDF) under `/tmp/qi08-e2e`. Two closed MNQ trades: 2026-05-14 2-lot (AMP present) and Sunday-ETH 1-lot (AMP absent).

| Check | Result |
|---|---|
| `load_tradesviz_executions` + `reconcile_journal` | 2 closed trades. May-14 `reconciled`; May-18 `amp_missing` |
| TradesViz `commission`/`fees` | Read then discarded (not on FillRecord columns) |
| CLI `journal reconcile` → `journal report` | exit 0; wrote `reconcile.json` + `journal_trades.parquet` + `report.json` |
| `schema_version` | `journal/v1` |
| Missing later artifacts | `present.attribution/counterfactual/match/zones/triggers` all false; Q3–Q8 omitted, not errors |
| Honesty strings | `REPORT_HONESTY` / `ZONES_HONESTY` / `TRIGGERS_HONESTY` on report + page `st.info` |
| Page 17 | Does not call `run_experiment` / `run_study` / `simulate_trades` (docstring + imports) |

This is **ingest/report plumbing**, not a verified P&L of a real desk.

### 3.2 Empty / malformed / fail-closed

| Input | Outcome |
|---|---|
| Missing executions file (CLI) | `JournalIngestError`, rc **2**, **no** traceback: `journal reconcile failed: TradesViz executions file not found: …` |
| Empty / junk / non-PDF bytes via `extract_amp_pdf_text` | **`PdfminerException`** (“No /Root object!”), **not** `JournalIngestError` |
| Same junk `.pdf` via CLI `reconcile` | Full traceback through `__main__` → `dispatch_journal` → `pdfplumber.open`; process exit **1** |
| AMP text missing `DAILY STATEMENT` | typed `JournalIngestError` |
| Write under `results/studies/` | typed refuse (reconcile and report) |

Finding QI-08-03. Text extracts and missing files fail closed; **malformed PDF does not**.

### 3.3 Sunday-open / `trading_session_date`

UTC `2026-05-17T22:05:00+00:00` = Sunday 18:05 America/New_York → `session_date` **2026-05-18** (Monday CME session). Calendar Sunday is not used. Matches TJ §3.0 item 1.

### 3.4 n < 30 toggle

`include_small_n` default **False**. On the 2-trade book: Q2 hidden **6**, shown **0**; toggle on → 6 Q2 rows. On a 5-trade JS1/JS2 fixture: Q3 zones/triggers hidden unless toggled. **`hidden_slice_count` counts Q2 only** (and still counts when the toggle shows them). CLI `--include-small-n` help: “Include **Q2** slices…”. Page checkbox help names Q2 + Q3 Zones + Q3 Inferred trigger (matches `USER_GUIDE.md`). Finding QI-08-05.

Q3 **levels/tags** (TJ6) have no n-gate — TJ9 as written. Not a finding.

### 3.5 JS1 / JS2 inference disclosure

| Surface | Disclosure |
|---|---|
| `ZONES_HONESTY` | previous completed 1m; params declared not searched; not a study cell |
| `TRIGGERS_HONESTY` | engine would-have-called; not perception; 15s is a proxy; 3c not inferred |
| Q3 caption | “Tags are trader intent. Alignment is a distance check, **not a trigger**.” |
| `tag_map` `3c` / `touch` | class **`context`**, token None |
| Page 17 | Q3 Zones / Inferred trigger omitted when parquet absent |

TJ6 lock holds at the honesty surface. Tags are not fed to `classify_zone_triggers`.

### 3.6 Store isolation + composer shape

`journal_store_dir()` = `<THESISTESTER_STORE_DIR>/journal/v1`. Not under `execution_artifacts/`. Probe store siblings: `journal` only. CAI-10 does not scan it (ARCHITECTURE; not re-measured here). Page keys `journal_dir` / `journal_include_small_n` / `journal_cached_artifacts` only. No `api.py` journal facade (handoff QI-6).

### 3.7 Persistence / parity / operability / a11y

- Reconcile write → `load_journal_artifacts` → `report_from_artifacts` round-trip on the synthetic dir.
- CLI vs library `reconcile_files` / `report_files` share the same writers. Page is report-only (TJ9 lock — do not hydrate classic keys).
- CLI journal verbs print `journal <cmd> failed: …` for `JournalIngestError` (QI-06-07 residual does **not** apply to those typed paths). PDF is the exception (QI-08-03).
- Copy: “qty-scaled”, “tags are intent”, JS1/JS2 inference captions are consistent across schema / report / page / USER_GUIDE. CLI `--include-small-n` is the drift (QI-08-05).

### 3.8 `tag_map.yaml` closed set

102 exact rows. File classes ⊆ `{level, confirm, unmapped}`. Context list is separate. `resolve_tag` rejects class `trigger` (`JournalIngestError: tag map class 'trigger' is not closed`). Unknown → `unmapped`. `p30POC` stays unmapped (not a rolling-POC alias). `pdH_RTH` exact-wins to `pRTH_High` (not `pdHigh`+`_RTH`). 101 mapped tokens; 28 confirm MAs/rPOC are **not** in `closed_level_token_set(DEFAULT_LEVELS_SETTINGS)` (73 tokens) — settings-dependent omit, TJ6. Not a defect.

### 3.9 PII scan

Scanned `tests/fixtures/journal/**`, `examples/journal/**`, `tag_map.yaml` for emails, phones, SSN-like, password/key keywords, unredacted AMP client names. **0 hits.** AMP fixtures use `REDACTED CLIENT`. Synthetic TV has no account identifiers. Probe inputs were generated under `/tmp` (not desk exports).

---

## 4. Prior-audit carry-over status

Plan §A.3 / QI-00 assign **none** of C1–C3 / H1–H16 / W* to QI-8. Journal post-dates `AUDIT_FINAL`.

| Item | Status |
|---|---|
| TJ6 tags ≠ triggers | **Holds** (map classes, Q3 caption, tags not passed to trigger inference) |
| JS3+ | **Not implemented** (`propose.py` absent; CLI has no `propose`) |
| Quantower Trades loader | **Still parked** (no symbol; ROADMAP / AGENT_GUIDE) |
| QI-06-07 journal CLI traceback | Typed `JournalIngestError` paths are clean; malformed PDF is QI-08-03 |
| QI-11-01 journal coverage | `rules.py` 68% / `ledger.py` 69% / `report.py` 114 misses — already QI-11; not re-filed |
| QI-12-07 private signals import | Confirmed; this slice owns QI-08-02 |

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Sev | Class | Title |
|---|---|---|---|
| QI-08-01 | Medium | Maintainability risk | Qty-scaled P&L has two write homes (`pair._closed_trade` + `reconcile._cost_row`) plus duplicated `_cost_ticks` |
| QI-08-02 | Medium | Maintainability risk | `journal/__init__` barrel + JS2 private `_classify_zone_triggers_detail` loads `engine.backtest` without calling it |
| QI-08-03 | Medium | Verified defect | Malformed AMP PDF raises `PdfminerException`; CLI traceback, exit 1 |
| QI-08-04 | Medium | Maintainability risk | `match` / `report` / `counterfactual` MI 0.00; three E-grade functions (33–36) |
| QI-08-05 | Medium | UX/operability gap | `--include-small-n` help and `hidden_slice_count` are Q2-only; toggle also gates Q3 Zones / Inferred trigger |

No Critical. No High. TJ6 / JS0 / Quantower-parked are premises, not findings.

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **Journal does not call `simulate_trades` or `compute_all_levels`.** No source import of those names; `thesistester.journal` does not re-export them. TJ7 walks 15s/ticks locally.
2. **Sunday 18:05 ET fill → Monday `session_date`** via `trading_session_date(..., eth_start="18:00")`.
3. **Synthetic CLI E2E** `reconcile` → `report` writes `journal/v1` artifacts; missing Q3–Q8 files omit sections (not errors). Store is `<store>/journal/v1`, refuses `results/studies/`.
4. **Qty scaling matches TJ §3.0 on the 2-lot probe** (points unscaled; currency / R / dollar-ticks × qty). TradesViz fees discarded; AMP is the cost SoT on `reconciled` days only; unreconciled costs stay null.
5. **JS1/JS2 disclosed as inference** (`ZONES_HONESTY`, `TRIGGERS_HONESTY`, page captions). `3c`/`touch` are context tags. 3c is not inferred.
6. **`tag_map.yaml` class set is closed**; unknown and `p30POC` stay unmapped; exact rows beat qualifier strip.
7. **PII scan of committed journal fixtures/examples: 0 hits.**
8. **Page 17 is read-only** (MI A 43.21; no Streamlit in the library; no `except Exception`; n<30 checkbox rebuilds from cache).
9. **JS3+ and Quantower Trades loader are absent** (parked).
10. **CLI typed ingest errors** (missing file) are rc 2 without traceback. Scoped journal suite 272 passed; hashseed 0/1 118/118 identical on the five-file subset. Isolation: `/tmp` store; no API keys.

---

## 7. Handoffs to other slices

| To | Observation (not a finding of theirs until they verify) |
|---|---|
| QI-3 | `engine/__init__.py` eagerly imports `simulate_trades`. Any `from thesistester.engine.*` (JS1 confluence, JS2 signals) loads the backtest module. Public `classify_zone_triggers` exists; journal uses the private detail helper |
| QI-6 | No `api.journal_*`. Journal CLI is cleaner than `run` for `JournalIngestError`; PDF path still tracebacks through `__main__` |
| QI-7 | `levels.py` imports `study.schema.closed_level_token_set` (TJ6 specified). JS3 still gated |
| QI-10 | Page 17 session keys (`journal_*`) vs ARCHITECTURE table; AppTest not attempted |
| QI-11 | `rules.py` / `ledger.py` <70%; `report.py` 114 misses; no AppTest of page 17; PDF typed-wrap needs a probe test |
| QI-12 | Private import already in the QI-12-07 linter draft; wrap `pdfplumber` before import-linter treats it as a new boundary |
| QI-13 | CLI `--include-small-n` help vs USER_GUIDE / page help; glossary journal block already honest |
| QI-14 | No journal timing envelope recorded |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/ARCHITECTURE.md` TJ / JS2 | Import-graph reality (`engine/__init__` load); PDF fail-closed sentence |
| `docs/AGENT_GUIDE.md` Journal / JS | Private-wrapper vs `classify_zone_triggers`; n<30 CLI wording |
| `docs/USER_GUIDE.md` Journal H2 | Already names Q3 in the toggle; CLI help would need to match |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` TJ2 | Malformed-PDF exception type |
| `docs/METRICS_GLOSSARY.md` journal metrics | Only if QR consolidates the P&L home (formulas already listed) |
| `docs/TRADE_JOURNAL_IMPLEMENTATION_PLAN.md` §3.0 / §3.2 | Formula-home / PDF typed-error acceptance (contract doc) |
| `docs/JOURNAL_TO_STUDY_IMPLEMENTATION_PLAN.md` §3.2 | JS2 should call the public wrapper (contract doc) |

---

## 9. Probe scripts (pasted; not committed)

E2E TV + AMP text (synthetic; no desk PII):

```python
# Sunday 18:05 ET = 2026-05-17T22:05:00+00:00 → session_date 2026-05-18
# 2-lot MNQ 29584.00 / 29585.25 → gross $5.00 vs AMP P&S $5.00 CR
# See /tmp/qi08_probes.py _tiny_tv / _tiny_amp
```

Malformed PDF:

```bash
printf '%%PDF-1.4\nnot a real pdf\n%%%%EOF\n' > /tmp/qi08-pdf/junk.pdf
python3 -m thesistester journal reconcile \
  --executions /tmp/qi08-e2e/tv.csv \
  --statements /tmp/qi08-pdf/junk.pdf \
  --output-dir /tmp/qi08-cli-bad
# PdfminerException traceback; exit 1
```

Import isolation:

```python
import thesistester  # backtest not loaded
import thesistester.journal.schema  # backtest + signals + levels.all loaded; simulate_trades not on journal
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
