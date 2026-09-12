# QI-12 — Tooling, dependencies, CI, packaging, security and supply chain

**Slice:** QI-12 (research-only)
**Status:** Measured
**Audited commit:** `32ad34c` (`32ad34c6ece44dfe90911cdd7460e9b9e3ff15bc`) — `main` after [#483](https://github.com/AccumuLatata/ThesisTester/pull/483) (QI-11)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3
**Key packages (this VM, `requirements.txt` path):** pandas 3.0.5 · numpy 2.4.4 · streamlit 1.63.0 · plotly **7.0.0** · pyarrow **25.0.1** · PyYAML 6.0.3 · kaleido 1.4.0 · pdfplumber 0.11.10 · pytest 9.1.1
**Probe tools (user-site, not committed):** ruff 0.16.7 · mypy 2.3.1 · pyright 1.1.414 · bandit 1.9.4 · pip-audit 2.10.1 · grimp 3.17 · import-linter · pip-tools
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi12-store-*`. `OPENAI_API_KEY` / `XAI_API_KEY` unset. No desk data.
**Finding count:** 10 (C/H/M/L = 0/2/7/1)
**Time spent:** one agent run on 2026-09-12; honesty/schema review the same day

**Review re-verification (docs-only):** branch protection, #476/#450, the 34 failed `#440`–`#477` merge-pushes, CI `#479` `pip list`, mypy/pyright/bandit/ruff family counts, `pip-audit`, `pip-compile` pin census, and the import-linter draft were re-run on this branch. Corrections below are count/schema honesty, not new slices. `prior_id` keeps `W*` / `plan §4.4 H-*` only (QI-11 disambiguation); `ENGINEERING_PROPOSAL §7` is not a §3.3 `prior_id`. pyright is **1421 errors in 41 files** (58 analyzed, not 58-with-errors). `pip-compile` pyproject output is **145 lines / 50 `==` pins**, not 145 pins. `journal.triggers → engine.signals` is JS2-by-design, not an AGENT_GUIDE import-ban break. Dummy `sk-`/`xai-` shapes exist in tests; no live keys. Coverage 82% is the QI-0/QI-11 figure on the same product tree (`e30cc48`), not a re-measure at `32ad34c`. Dependabot *alerts* are unread (403 / `security_and_analysis: null`); version updates are absent (`no dependabot.yml`).

No config, workflow, dependency, or product file was edited. Probes and the import-linter draft live under `/tmp/qi12/` and are pasted below. This slice does **not** claim any backtest, metric, or Study result is correct.

## Commands run (verbatim)

```bash
python3 --version
git rev-parse HEAD
python3 -c "import pandas,numpy,streamlit,plotly,pyarrow,yaml,pytest; print(...)"

# before (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi12-store-before pytest -q --tb=no

# GitHub (branch protection + red-merge reality)
gh api repos/AccumuLatata/ThesisTester/branches/main
gh api repos/AccumuLatata/ThesisTester/rulesets
gh pr view 476 --json statusCheckRollup,mergedAt,title
gh pr view 450 --json statusCheckRollup,mergedAt,title
gh run list --repo AccumuLatata/ThesisTester --branch main --workflow ci.yml --limit 120

# CI resolved versions (last green main push #479, run 34703848937)
gh run view 34703848937 --log   # pip list in pytest py3.10 / py3.12

# read-only static
python3 -m ruff check . --statistics
python3 -m ruff format --check .
for fam in B UP SIM PL N I C90 S; do
  python3 -m ruff check . --select "$fam" --statistics --exit-zero
done
python3 -m mypy --strict --ignore-missing-imports --cache-dir /tmp/qi12/mypy-cache \
  thesistester/engine thesistester/analytics thesistester/api.py \
  thesistester/data thesistester/levels
python3 -m pyright --outputjson thesistester/engine thesistester/analytics \
  thesistester/api.py thesistester/data thesistester/levels
python3 -m bandit -r thesistester -ll -q -f json -o /tmp/qi12/bandit.json
python3 -m pip_audit --progress-spinner off
python3 -m piptools compile --output-file /tmp/qi12/constraints-pyproject.txt pyproject.toml
python3 -m piptools compile --output-file /tmp/qi12/constraints-req.txt requirements.txt
lint-imports --config /tmp/qi12/import_linter_draft.ini
python3 /tmp/qi12/probe_imports.py

# after (guardrail 2)
THESISTESTER_STORE_DIR=/tmp/qi12-store-after pytest -q --tb=no
# 3966 passed, 5 skipped in 142.45 s — identical pass/fail/skip to before
```

Probe transcripts stay under `/tmp/qi12/`. Nothing from `/tmp` is committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered (QI-12 exclusive owner, read-only)**

| Path | What was measured |
|---|---|
| `pyproject.toml` | runtime ranges, `dev` extra, ruff/pytest/coverage tool tables, build-backend |
| `requirements.txt` | app-install path vs `pyproject` caps |
| `.github/workflows/ci.yml` | six job *names*, triggers, coverage floor, action pins |
| `.devcontainer/devcontainer.json` | image, install commands, Streamlit CORS/XSRF |
| `.env.example` | store-only; no key names |
| `.gitignore` | `.env`, `.streamlit/secrets.toml`, `config/assistant.voice.override.toml`, `uv.lock` |
| `scripts/set_store_dir.ps1` | writes gitignored `.env`; no secrets |
| `LICENSE` | MIT (W14) |
| `config/assistant.toml` | default-off `study_tools` / `voice` (secret/config hygiene only; QI-9 owns content) |
| Secret paths in `thesistester/assistant/llm.py` | resolution order, placeholder reject, sanitizer (file owned by QI-9) |

**Read as spec (not owned)**

- Root `README.md` install/run (QI-13)
- `docs/AGENT_GUIDE.md` §Development environment / CI table
- `docs/ENGINEERING_PROPOSAL.md` §4 rule 9, §7
- `docs/ENGINEERING_ROADMAP.md` R9
- `tests/fixtures/golden/README.md` pandas-major hash skip (QI-13)
- `.streamlit/` (QI-10)

**Skipped**

- `scripts/quality_metrics.py` — QI-0 harness exception
- Changing any config (hard rule)
- Re-deriving `AUDIT_FINAL` §5 / AH §2
- Bundle zip-bomb behavior (QI-06-09 already recorded; this slice owns the *missing CI control*)
- Page/`app.py` Streamlit session graph (QI-10)

---

## 2. Code-quality readout

### 2.1 Control inventory (exit table)

| Control | Present? | Cost to add (QR-G / QR-B) | What it would have caught |
|---|---|---|---|
| Required status checks on `main` (`ruff (lint + format)`, `pytest (py3.10/3.11/3.12)`, `editable install (no dev extras)`, `golden-master regeneration guard`) | **No.** `gh api …/branches/main` → `protected: false`, `required_status_checks.enforcement_level: off`, `checks: []`. Repo rulesets `[]`. | Settings-only; no product change | [#476](https://github.com/AccumuLatata/ThesisTester/pull/476) merged 2026-09-08 with pytest ×3 `FAILURE`. [#450](https://github.com/AccumuLatata/ThesisTester/pull/450) merged 2026-09-05 with **ruff + pytest ×3 `FAILURE`**. Plan §4.3: 37 merges on red through `#476`; this run’s last 120 `main` CI rows include 34 failed *merge* pushes from `#440` (2026-09-05) through `#477` (33 unique PRs; `#471` has two failed push runs). → QI-12-01 |
| Lockfile / `constraints.txt` | **No** tracked lock. `uv.lock` is gitignored (Streamlit Cloud parser note). `pip-compile` from `pyproject.toml` produced a **145-line / 50-pin** constraints file in `/tmp` in seconds | Low (commit compile output; refresh in a gated PR) | Streamlit 1.63 `AppTest` pickup inside `>=1.56,<2` (hotfix [#478](https://github.com/AccumuLatata/ThesisTester/pull/478)). App-install vs CI plotly/pyarrow major split (this VM). → QI-12-02 |
| Dependabot / Renovate + full-suite gate | **No** `.github/dependabot.yml`. Alerts endpoint 403; `security_and_analysis: null` (not a readable enabled/disabled). Version updates are absent. | Low–med (config + warn-first) | Same two drift events; stale transitive `cryptography`/`jinja2` on long-lived VMs. → QI-12-02, QI-12-06 |
| Explicit pandas-major matrix axis | **Accidental only.** py3.10 → pandas **2.3.3** / numpy **2.2.6**; py3.11/3.12 → pandas **3.0.5** / numpy **2.5.3** (CI `#479` `pip list`). Caps are `pandas>=2.2,<4` | Low (name the axis in `ci.yml`; do not treat it as three identical cells) | `test_nullable_join_columns_stay_object_none` py3.10 `nan is None` (plan §4.3; #478). → QI-12-02 |
| Streamlit minor cap or matrix | **No.** `streamlit>=1.56,<2` admits every 1.x. CI `#479` and this VM both resolve **1.63.0** (current latest) | Low (cap `,<1.64` *or* a Streamlit-minor job) | #478 `AppTestError: Cannot update a disabled chat_input` — QI-11-03 residual proto/`set_value` is the next recurrence. → QI-12-02, QI-12-10 |
| Coverage floor blocking | **Informational.** `COVERAGE_FLOOR: 85`; job emits `::warning`, never fails. R9 baseline 88%. QI-0/QI-11 measured **82%** @ `e30cc48` (same product tree) | Low once QR-B picks the measured floor | H-0b: six-point drop from R9 never blocked a merge. → QI-12-04 |
| Type-checker in CI | **None.** No mypy/pyright config anywhere | Med, warn-first on `engine/`+`analytics/` | **164** mypy `--strict` / **1421** pyright errors (41 files; 58 analyzed) on the five-tree set — never a gate. → QI-12-05 |
| `bandit` in CI | **None** | Low, `-ll` warn-first | 1 High (SHA1 `study.naming`) + 4 Medium (`urlopen` in assistant LLM/voice). → QI-12-06 |
| `pip-audit` in CI | **None** | Low, project-deps only | Transitive-of-declared advisories on this VM: `cryptography 41.0.7`, `jinja2 3.1.2`, `idna 3.13`, `urllib3 2.6.3`. Fresh `pip-compile` already resolves `cryptography==50.0.1`, `jinja2==3.1.6`, `urllib3==2.7.0`. → QI-12-06 |
| Import-layer enforcement | **None** mechanical. Scattered AST guards in `tests/study/*` (QI-11-owned) check *direct* imports | Med (warn-first `import-linter`) | Over-specified 8-contract draft: **4 kept / 4 broken**. Documented AGENT_GUIDE/ARCHITECTURE import bans (6): **3 kept / 3 broken** — preview↛execute and launch↛viewer via `expand → cli → cli_study` chains; Streamlit-in-library: 7 lazy importers after ignoring `app_state`. `builder↛execute` is a call-ban. `journal.triggers → engine.signals` is JS2, not a ban. → QI-12-07 |
| Ruff widening (`B`,`UP`,`SIM`,`PL`,`N`,`I`,`C90`) | **No.** R9 set `E4,E7,E9,F,W` is clean (intentional) | Med, one family per PR | Counts: B 44 · UP 93 · SIM 139 · PL 2091 · N 35 · I 178 · C90 178. `S` is 12368, almost all `S101` asserts. → QI-12-09 |
| CodeQL / secret scanning | Token 403; alerts API unread. No workflow | Med | Would not have caught the Streamlit/pandas test breaks; would catch leaked keys if any were committed (none found; tests hold dummy `sk-`/`xai-` shapes). → QI-12-06 |
| Action SHA pins | **No.** `actions/checkout@v7`, `setup-python@v7`, `upload-artifact@v7` (floating major tags) | Low | Tag-move supply-chain on the regression gate itself. → QI-12-06 |
| Devcontainer ≡ CI / README | **No.** Image `python:1-3.11-bookworm`; `pip3 install -r requirements.txt` then **uncapped** `pip3 install --user streamlit`; `packages.txt` referenced but **absent**; `postAttachCommand` sets `--server.enableCORS false --server.enableXsrfProtection false` | Low (align image + editable install; do not disable XSRF) | Codespaces boots a different Python, a different Streamlit than CI, and a CSRF-off server. → QI-12-08 |

### 2.2 Dependency ranges vs what actually installs

`pyproject.toml` comment claims ranges “mirror `requirements.txt` … with conservative next-major caps” so a major bump is a test-gated PR (`ENGINEERING_PROPOSAL` §7). That is **false for the app-install path**.

| Package | `pyproject.toml` | `requirements.txt` | This VM | CI py3.10 `#479` | CI py3.12 `#479` | `pip-compile` pyproject | `pip-compile` requirements |
|---|---|---|---|---|---|---|---|
| streamlit | `>=1.56,<2` | `>=1.56` | 1.63.0 | 1.63.0 | 1.63.0 | 1.63.0 | 1.63.0 |
| pandas | `>=2.2,<4` | `>=2.2` | 3.0.5 | **2.3.3** | 3.0.5 | 3.0.5 | 3.0.5 |
| numpy | `>=1.26,<3` | `>=1.26` | 2.4.4 | **2.2.6** | **2.5.3** | 2.5.3 | 2.5.3 |
| plotly | `>=5.22,<7` | `>=5.22` | **7.0.0** | 6.9.0 | 6.9.0 | **6.9.0** | **7.0.0** |
| pyarrow | `>=16,<25` | `>=16` | **25.0.1** | 24.0.0 | 24.0.0 | **24.0.0** | **25.0.1** |
| kaleido | `>=1.3.0` (no upper) | same | 1.4.0 | 1.4.0 | 1.4.0 | 1.4.0 | 1.4.0 |
| pdfplumber | `>=0.11.4,<0.12` | same | 0.11.10 | 0.11.10 | 0.11.10 | 0.11.10 | 0.11.10 |
| pytest | `>=8.2` (dev extra) | **`>=8.2` (app file)** | 9.1.1 | (dev extra) | 9.1.1 | — | 9.1.1 |
| ruff | `>=0.16,<0.17` (dev) | absent | 0.16.7 | — | 0.16.7 | — | — |

README / `AGENT_GUIDE` fast-start still say `pip install -r requirements.txt`. CI says `pip install -e ".[dev]"`. Those two commands are **not** the same resolve.

`kaleido>=1.3.0` is the only runtime dep with **no next-major cap** on *either* path. `pytest` / `pytest-cov` minors are uncapped; ruff is correctly minor-capped.

`pip-compile` from `pyproject.toml` is trivially derivable (**50** `==` pins in a 145-line file). A lockfile is not blocked by tooling — it was a choice (`uv.lock` gitignore comment names Streamlit Cloud, not `constraints.txt`).

### 2.3 Type-check probe (read-only; no config committed)

`mypy --strict --ignore-missing-imports` on `engine/` + `analytics/` + `api.py` + `data/` + `levels/`:

**164 errors in 34 files** (58 sources checked). Top files: `engine/signals.py` 21 · `persistence/local_store.py` 16 (import-pulled) · `api.py` 16 · `engine/backtest.py` 13. Top codes: `type-arg` 78 · `arg-type` 27 · `union-attr` 20. Matches QI-0’s 163 on the three-tree subset; the fifth tree adds one.

`pyright` (default, no config) on the same five trees:

**1421 errors in 41 files** (58 analyzed). Top files: `analytics/walk_forward.py` 295 · `analytics/excursions.py` 116 · `levels/indicators.py` 104 · `engine/signals.py` 91. Top rules: `reportAttributeAccessIssue` 837 · `reportArgumentType` 419. Annotations exist; **soundness has never been checked in CI** (W3 residual).

### 2.4 Bandit / pip-audit

`bandit -r thesistester -ll`: **5 issues**, all High confidence.

| Sev | Test | Symbol |
|---|---|---|
| High | B324 | `thesistester.study.naming` SHA1 (handoff QI-7: likely `usedforsecurity=False` identity, not a password hash) |
| Medium | B310 ×4 | `urllib.request.urlopen` in `assistant.llm` and `assistant.voice.xai_realtime` (handoff QI-9) |

`pip-audit` on this VM: **no direct declared runtime package** (`streamlit`, `pandas`, `numpy`, `plotly`, `pyarrow`, `PyYAML`, `kaleido`, `pdfplumber`) appears in the advisory table.

| Class | Packages (this VM) |
|---|---|
| Transitive of declared | `cryptography 41.0.7` (via `pdfplumber`/`pdfminer.six`) · `jinja2 3.1.2` (via Streamlit) · `idna 3.13` · `urllib3 2.6.3` |
| Environment-only | `ansible`/`ansible-core`, `pip`, `PyJWT`, `setuptools 68.1.2` (PYSEC-2025-49 / 2026-1918 / 2026-3447), `wheel 0.42.0` (CVE-2026-24049), `httplib2` |
| Build-system declared | `setuptools>=68` in `[build-system]` — no upper cap; the env copy is the CVE set |

`pip-audit -r requirements.txt` failed here (`ensurepip` missing); classification used the env audit + the declared-name filter. A fresh `pip-compile` already moves the transitive set to fixed versions — the gap is **no CI job and no refresh policy**, not an unknown CVE in `pandas`/`streamlit` themselves.

Ruff `S105` “hardcoded password” (34) is a false-friend on `*_token` / column names (`LEVEL_TOKEN_COUNT_COL`, `"failed"`). Not a finding.

### 2.5 Ruff widening candidates (R9 left these out on purpose)

Current set `E4,E7,E9,F,W`: **clean**. `ruff format --check .`: **368 files** already formatted.

| Family | Hits | Notes for QR |
|---|---|---|
| B | 44 | 19 `B905` zip-without-strict; 18 `B009`; 4 `B023` loop-variable (the C1 class) |
| UP | 93 | mostly `UP035` / `UP006` (py3.10 still required) |
| SIM | 139 | style; 2 `SIM115` open-without-context |
| PL | 2091 | 1088 `PLR2004` magic values — not a first-wave gate |
| N | 35 | OHLC / level shorthand |
| I | 178 | isort; mechanical |
| C90 | 178 | complexity — overlaps radon F/E already owned by other slices |
| S | 12368 | 12275 `S101` assert; do **not** enable on `tests/` |

Widening is a reviewable QR-B PR per family, as `AGENT_GUIDE` already says. Not a defect that R9 stayed narrow.

### 2.6 Import-linter draft (`/tmp/qi12/import_linter_draft.ini`)

Two readings of the same graph (204 files, 1346 dependencies):

| Set | Contracts | Result |
|---|---|---|
| Over-specified draft (includes builder call-ban + journal↛signals) | 8 | **4 kept / 4 broken** |
| Documented AGENT_GUIDE / ARCHITECTURE *import* bans + H-C Streamlit | 6 | **3 kept / 3 broken** |

| Contract | Documented? | Result | Reading |
|---|---|---|---|
| `preview` ↛ `execute` | Yes (RS-D8) | BROKEN | *Chain*: `preview → expand → cli → cli_study → execute`. Direct import is absent (AST tests in `tests/study/test_study_preview.py` still hold). `STUDY_RUNNER` already admits package-init honesty |
| `viewer` ↛ cli/execute/rollup/observatory/promote/admit/plotly/streamlit | Yes (SV/SO + ARCHITECTURE) | KEPT | Direct *and* chain |
| `observatory` ↛ cli_study/execute/streamlit/plotly | Yes (SO) | KEPT | |
| `admit_followup` ↛ execute/launch/viewer/cli/streamlit | Yes (SAF / ARCHITECTURE) | KEPT | |
| `launch` ↛ `viewer` | Yes (ARCHITECTURE). Draft also forbade execute/cli/promote | BROKEN | Same `expand → cli → cli_study → viewer` chain. `launch.py` itself does not import `viewer` |
| `builder` ↛ `execute` | **No** — SB/RS-D9 is a *call* ban (`do not call run_study`) | KEPT | Pads the 8-contract kept count if included |
| `journal` ↛ `engine.signals` (also backtest / `levels.all` / `sim_core`) | **No** — JS2 landed `journal.triggers` as a `classify_zone_triggers` wrapper | BROKEN if included | Direct `journal.triggers → engine.signals._classify_zone_triggers_detail` is QI-8 (private import), not an import-ban miss. Long chains through `study.schema → tick_vap → execution_artifacts → api` are layering |
| library ↛ `streamlit` except `app_state` | Yes (H-C / R18) | BROKEN (1 ignore) | Extra **direct** importers: `assistant.llm`, `assistant.voice.xai_realtime`, `classic_context`, `classic_ledger`, `classic_nav`, `classic_proposal`, `classic_record` (lazy; `rg '^import streamlit'` still only hits `app_state.py`) |

`rg '^import streamlit\|^from streamlit' thesistester` → **1 file** (`app_state.py`), matching QI-0. Grimp sees the lazy imports the regex misses. QI-06-05 already named the classic_* set; this slice records that **no import-linter contract exists to keep it from growing**. The finding is the missing mechanical gate, not “JS2 must un-import `engine.signals`”.

### 2.7 Scripts / packaging / secrets (in-scope files)

- `LICENSE` is MIT, copyright 2026 AccumuLatata. **W14 closed.**
- `scripts/set_store_dir.ps1` writes UTF-8-no-BOM `.env` with `THESISTESTER_STORE_DIR` only; `-UserEnv` sets a user env var. No key material.
- `.env.example` documents **only** `THESISTESTER_STORE_DIR`. ThesisTester does not load API keys from `.env` (`llm.require_openai_api_key` docstring: env then Streamlit Secrets; never tracked config).
- `.gitignore` covers `.env`, `.streamlit/secrets.toml`, `config/assistant.voice.override.toml`. None of those are tracked (`git ls-files` empty).
- `config/assistant.toml`: `[assistant.study_tools] enabled=false`, `[assistant.voice] enabled=false`. Discuss/help channels are enabled but still require a key at runtime.
- `llm._usable_openai_api_key` strips whitespace, UTF-8 BOM, wrapping quotes, and rejects `REPLACE_WITH_ROTATED_OPENAI_API_KEY`. Errors go through `_sanitize_provider_error_text`. Tracked-file scan: **no live keys**. Dummy `sk-abc123` / `xai-test-key` shapes live in `tests/test_assistant_*.py` (sanitizer / fail-closed fixtures). `AKIA` has no matches.
- No `CODEOWNERS`, no `SECURITY.md`, no `.pre-commit-config.yaml`, no `constraints.txt`.
- Package version `thesistester.__version__ = "0.2.0"` (QI-6-owned file; packaging reads it).

---

## 3. Application-quality readout

§3.2 page/API checklists are **not** this slice. Tooling/entry-point checks:

| Entry | Happy | Empty / malformed | Honesty / operability |
|---|---|---|---|
| `pip install -r requirements.txt` (README spec) | Resolves; admits plotly 7 / pyarrow 25 | N/A | Diverges from CI / `pyproject` caps (QI-12-03) |
| `pip install -e ".[dev]"` (AGENT_GUIDE) | CI `#479` green on 3.10/3.11/3.12 | N/A | Resolves latest inside caps; no lock |
| `python -m thesistester` / `streamlit run` | QI-0 already booted `--help` and `/_stcore/health`. Not re-run as a correctness claim | N/A | Devcontainer disables XSRF/CORS (QI-12-08) |
| Secret resolution | Fail-closed without a key (`LLMConfigurationError`); placeholder rejected | Malformed key (BOM/quotes) stripped | Never reads `assistant.toml` for the key. `.env.example` does not invite committing keys |

Composer parity for install paths **fails**: README app-install ≠ CI resolve (plotly/pyarrow majors). That is a packaging honesty issue, not a fill issue.

---

## 4. Prior-audit carry-over status

| Item | Status this slice |
|---|---|
| **W1** “No CI” (closed by R9) | **Closed as written** — `.github/workflows/ci.yml` exists and runs on every PR/`main` push. **Intent residual open:** “regressions cannot merge silently” is **not** true. `main` is unprotected; #476/#450 merged on red. → QI-12-01 |
| **W2** “No packaging” (closed by R9) | **Closed as written** — `pyproject.toml` + `pip install -e .`. **Residual:** `requirements.txt` still uncapped; app-install ≠ CI. → QI-12-03 |
| **W3** “No lint/format/type-check” (closed by R9 for lint/format) | **Lint/format closed** (`ruff` clean, minor-capped). **Type-check still absent.** No pre-commit. → QI-12-05 |
| **W14** “No LICENSE” (closed by R9) | **Closed-verified.** MIT `LICENSE` present |
| **`ENGINEERING_PROPOSAL` §7** “pandas/numpy major-version drift” | **Realized.** Mitigation listed “CI matrix + conservative caps + dependabot/renovate gated by full suite”. Caps exist on `pyproject` only; matrix is a pandas-major split *by accident*; dependabot is **off**. Streamlit-minor sibling is **missing from the register** → QI-12-02, QI-12-10 |
| Plan §4.4 **H-0** (CI gate not operating) | Re-verified on `32ad34c`. `#478` restored *signal* (green cells) but **not** the merge gate. `#477` still merged on red after the plan was written |
| Plan §4.4 **H-0b** (coverage floor silent) | Still informational; 82% vs 85%/88% (QI-0/QI-11 @ `e30cc48`; same product tree). Policy → QI-12-04; module debt is QI-11-01 |
| Plan §4.4 **H-C** (contracts are prose) | Documented import bans 3/6 broken (chains + Streamlit-in-library). 8-contract draft 4/8 over-counts JS2 / builder. Viewer/observatory AST tests already police *direct* bans. → QI-12-07 |

Locked premises: `AUDIT_FINAL` §5.1–5.4 and §7; AH §2 / §2.1. Not re-audited.

---

## 5. Findings

Full records in `docs/quality/findings.csv`. Summary:

| ID | Class | Sev | One line |
|---|---|---|---|
| QI-12-01 | Verified defect | High | `main` is unprotected; the six CI job names are not required status checks. #476/#450 (and the §4.3 red-merge window) merged on red |
| QI-12-02 | Verified defect | High | No lockfile/Dependabot; Streamlit minors and an accidental pandas 2.3/3.0 matrix are free to change test semantics. EP §7 realized (+ Streamlit sibling) |
| QI-12-03 | Documentation drift | Medium | `requirements.txt` does not mirror `pyproject` caps; README app-install resolves plotly 7 / pyarrow 25 while CI stays on 6.9 / 24.0. `pytest` is in the app file |
| QI-12-04 | Test-quality gap | Medium | Coverage floor 85% is `::warning` only; measured 82% vs R9 88%. Never blocked |
| QI-12-05 | Maintainability risk | Medium | No mypy/pyright in CI. `--strict` 164 / pyright 1421 in 41 files (58 analyzed) on engine+analytics+api+data+levels |
| QI-12-06 | Security risk | Medium | No bandit / pip-audit / CodeQL / Dependabot config. Transitive CVEs on the VM; 5 bandit Medium+ |
| QI-12-07 | Maintainability risk | Medium | No import-linter. Documented bans 3/6 broken (chains + Streamlit-in-library). Draft 4/8 over-counts JS2 / builder |
| QI-12-08 | Security risk | Medium | Devcontainer: Python 3.11 ≠ CI matrix; extra uncapped `streamlit`; CORS+XSRF disabled; missing `packages.txt` |
| QI-12-09 | Design limitation | Low | R9 ruff set is intentionally narrow. Widening counts recorded (B 44 … PL 2091). `confidence=n/a` |
| QI-12-10 | Documentation drift | Medium | `ENGINEERING_PROPOSAL` §7 names pandas/numpy drift and lists mitigations that are not operating; Streamlit-minor is absent from the register |

---

## 6. Positive verification

What was checked and is fine, so QI-15 / QR do not re-audit it:

1. **Local suite on this `main` is green** before and after the two `docs/quality/` files: `3966 passed, 5 skipped` in 144.40 s then 142.45 s, exit 0 both times (Python 3.12.3 / pandas 3.0.5 / streamlit 1.63.0). Suite result only — not fill correctness (`AUDIT_FINAL` §5.1 item 10 / §7).
2. **`ruff check` (R9 set) and `ruff format --check` are clean** (368 files).
3. **W1 “no CI” is closed as written.** Six named jobs exist and ran on `#479` (all success on the merge push; golden-guard skipped on `push` as designed).
4. **W2 “no packaging” is closed as written.** `pip install -e .` job + `thesistester.__version__`.
5. **W14 is closed-verified.** MIT `LICENSE`.
6. **Direct declared runtime deps are not in the `pip-audit` table** on this VM.
7. **No live keys / desk PII in tracked files.** `.env`, Streamlit secrets, and the voice override are gitignored and untracked. `assistant.toml` does not store keys; `study_tools` / `voice` stay default-off. Test fixtures use dummy `sk-`/`xai-` shapes only.
8. **Secret resolution is fail-closed and sanitized** (`require_openai_api_key` / placeholder reject / BOM-quote strip / `_sanitize_provider_error_text`). `.env.example` is store-only. Fail-closed holds with those env vars unset.
9. **`pip-compile` can produce a constraints file today** (50 pins / 145 lines from `pyproject.toml`). QR-G is not blocked on tooling.
10. **Viewer / observatory / admit_followup *direct* import bans hold** on the grimp graph (AST tests are not theater for those three). `builder` has no documented import ban.
11. **Isolation:** throwaway `/tmp` stores; no API keys used; no config edits.

---

## 7. Handoffs to other slices

| To | Observation (not a finding of theirs until they verify) |
|---|---|
| QI-6 | Streamlit-in-library extras (`classic_*`, `assistant.llm`) — QI-06-05. Zip size cap is QI-06-09; this slice only notes the missing `bandit` job |
| QI-7 | `preview`/`launch` → `execute`/`viewer` is a *chain* via `expand → cli → cli_study`. `study/__init__.py` imports `execute`. SHA1 in `study.naming` (bandit High) |
| QI-8 | `journal.triggers` **directly** imports `engine.signals._classify_zone_triggers_detail` (JS2 wrapper; private-import leak). Long chains through `api` are layering, not a `simulate_trades` call |
| QI-9 | `urlopen` B310; Streamlit Secrets fallback is a lazy `import streamlit` inside `llm.py` / `xai_realtime.py` |
| QI-10 | `classic_nav` Streamlit import; `.streamlit/config.toml` not opened here |
| QI-11 | Coverage-floor *policy* is this slice; module debt is QI-11-01. AppTest Streamlit-minor coupling is QI-11-03. Markers/xdist are QI-11-05 |
| QI-13 | README / AGENT_GUIDE / ROADMAP claim CI is “blocking on red” and that `requirements.txt` mirrors `pyproject` caps. Do not amend in QI |
| QI-14 | None. Kaleido PNG cost stays QI-11/14 |

---

## 8. Docs that would need amending in QR

List only. **Not amended.**

| Doc | Why QR might touch it |
|---|---|
| `docs/AGENT_GUIDE.md` §Development environment / “Regression-safety gates in CI” | Jobs are labelled “blocking” but they do not block merge. Record required-check names, lockfile/constraints policy, type-checker warn-first, pandas-major axis, Streamlit-minor rule |
| `docs/ENGINEERING_PROPOSAL.md` §4 rule 9 | “no merge on red” is not enforced |
| `docs/ENGINEERING_PROPOSAL.md` §7 | Mitigations for pandas/numpy drift are incomplete; add Streamlit-minor sibling |
| `docs/ENGINEERING_ROADMAP.md` R9 | “CI … blocking on red” overclaim |
| `docs/ARCHITECTURE.md` | Import bans become `import-linter` contracts; Streamlit-in-library exception list |
| `README.md` (QI-13) | App-install vs `pip install -e ".[dev]"`; do not claim the ranges are mirrored |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Only if QR discloses the pandas-major / Streamlit-minor test envelope to operators |

---

## 9. Probe scripts (pasted; not committed)

Import-linter draft header (`/tmp/qi12/import_linter_draft.ini`):

```ini
[importlinter]
root_package = thesistester
include_external_packages = True

[importlinter:contract:preview-no-execute]
name = preview.py must not import study.execute
type = forbidden
source_modules = thesistester.study.preview
forbidden_modules = thesistester.study.execute
# … viewer / observatory / admit_followup / launch / builder /
# journal / library-streamlit-free (app_state ignore only)
```

Constraints proof (throwaway):

```bash
python3 -m piptools compile --output-file /tmp/qi12/constraints-pyproject.txt pyproject.toml
python3 -m piptools compile --output-file /tmp/qi12/constraints-req.txt requirements.txt
# pyproject → 145 lines / 50 == pins; plotly==6.9.0 pyarrow==24.0.0
# requirements → plotly==7.0.0 pyarrow==25.0.1
```

---

## Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged.
