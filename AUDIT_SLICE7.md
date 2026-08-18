# ThesisTester audit Slice 7 — Persistence, identity, API/CLI, bundles, reporting, classic, assistant

**Mode:** research / investigation only. No application-code changes.
**Depends on:** Slice 0 (`AUDIT_OVERVIEW.md`, PR #390), Slice 1 (`AUDIT_SLICE1.md`, PR #391), Slice 2 (`AUDIT_SLICE2.md`, PR #392), Slice 3 (`AUDIT_SLICE3.md`, PR #393), Slice 4 (`AUDIT_SLICE4.md`, PR #394), Slice 5 (`AUDIT_SLICE5.md`, PR #395), Slice 6 (`AUDIT_SLICE6.md`, PR #396). Prior **locked contracts** are treated as given. Level/3c/fill/WFA/Study-expand math were not re-audited except where API/CLI/assistant **compose** them differently.
**Checkout:** `main` at `83a42f8` (PR #388), pandas 3.0.5.
**Named tests run:** identity / cache / bundle / CLI / API / reporting / classic-export / local_store / assistant tools+parity+contracts / study tools — **313 passed**.
**Goldens:** `tests/fixtures/golden/*` and `legacy_bundle_hash.txt` are **legacy-unchanged identity** gates. They do not prove cache honesty, restore isolation, report labeling, or assistant safety.

This file is the Slice 7 (last slice) deliverable. The **FINAL MERGE** must treat §5 as the persistence / composer / assistant contract, and §6 as still unverified product decisions.

---

## 0. Contracts used here (not re-proven)

### From Slice 6 (locked)

1. Study is a composer over `validate_run_spec` + `run_experiment`. It does not call `run_batch`. Cells continue after failure. `execution_origin="study"`.
2. Expand does not invent trigger / mode / TF. Omitted OTF → disabled. Batteries emit `{enabled: false}`, never `{}`.
3. Omitted `study.levels` keys fill the **product** plane (`DEFAULT_LEVELS_SETTINGS`), not bare `compute_all_levels`.
4. Omitted `dataset.ingestion_mode` is `primary`. Build first-visit is `15s_primary_derive_1m`.
5. Study setup validate is `validate_setup_config` only. Factors cannot name `close` today. API/CLI can still leak `BASE_COLUMNS`.
6. Failed cells: ledger+index `failed`, null PF/WR, no zip; excluded from ranked/promote; included in overview CSV and rollup row count.
7. PF/WR: index then bundle `trade_summary`; no live recompute.
8. Promote writes drafts, never executes. Paths may be rewritten cwd-first.
9. Inspect/viewer do not call `run_study`. Page must not write classic research keys.
10. Study does not run Focus or `run_otf_validation_matrix`. Ranking stays in-sample `primary_metric`.
11. Do **not** assume `thesistester run <study>/experiment.yaml` equals `study run` of the source YAML (relative `dataset.path` resolves against different parents).
12. Goldens ≠ correctness. Ranked/promoted cell is not a deployable parameter.

### Also locked (handoff)

Two composers (UI vs API). `session` ≠ `trading_session_date`. Flatten is calendar-RTH. OTF `T` = `trigger_timestamp` else `timestamp`. `pnl_points` gross / `r_multiple` net. Focus post-hoc. OTF-matrix train-path leak. `validate_setup_config` does not reject `close`.

---

## 1. Architecture of this layer

### 1.1 What this layer owns

Slice 7 is the **orchestration and persistence** surface. It does not invent fills, signals, or a second simulator.

```text
RunSpec / classic session / StudySpec cell
        │
        ├─ UI pages 1–10/13     → engine/analytics directly (composer A)
        ├─ api.run_experiment   → load → compute_levels → generate_signals
        │                         → run_backtest(levels frame) → optional batteries
        ├─ cli.run_batch        → run_experiment(origin=cli, cache=read_write)
        │                         fail-fast; base_directory = experiment.yaml parent
        ├─ study.execute        → same run_experiment(origin=study, cache=read_write)
        │                         continue-on-failure; base_directory = StudySpec parent
        └─ assistant.tools      → same run_experiment(origin=assistant, cache=read_write)
                                  base_directory = dataset.path parent
        │
        ▼
bundle-ready state  → build_research_bundle / reporting.build_research_artifact
        │
        ├─ identity: DataIdentity / LevelsIdentity / ExperimentIdentity
        ├─ cache:    execution_artifacts/v1 (source binding → data/levels)
        ├─ store:    .thesistester_store (user trees ≠ cache eviction)
        └─ restore:  apply_research_bundle_to_session + Data-page nonce
```

| Surface | Calls `run_experiment`? | Cache policy | Origin |
|---|---|---|---|
| Classic UI pages | **No** | `off` (no artifact wiring) | session / `"classic"` on export |
| `api.run_experiment` default | Yes | **`off`** | `"api"` |
| `cli.run_batch` | Yes | `read_write` | `"cli"` |
| `study.execute_study_cell` | Yes | `read_write` | `"study"` |
| `assistant.tools.run_experiment` | Yes | `read_write` | `"assistant"` |
| `pages/14` Run confirmed | Yes (via `execute_confirmed_run` → `PIPELINE.run_experiment`) | `read_write` | `"assistant"` |

`thesistester/app_state.py` is the only library module that imports Streamlit at module scope. `classic_*` and some assistant modules import Streamlit lazily.

### 1.2 Identity vs cache vs bundle hash (do not conflate)

| Digest | Inputs | Used for |
|---|---|---|
| `dataset_id` / `DataIdentity.dataset_id()` | Parent OHLC content hash + instrument + interval + TZs. **Excludes** `format_profile`, `ingestion_mode`, subtimeframe | Legacy dataset identity |
| `data_artifact_key` | `dataset_id` fields **plus** `format_profile` + schema versions | Data cache object |
| `source_binding_key` | Source **file bytes** + instrument + TZs + profile + **`ingestion_mode`** + `derivation_policy` | Warm skip of CSV parse |
| `levels_artifact_key` | Settings hash + `LEVEL_ENGINE_VERSION` + data artifact key | Levels cache |
| `run_spec_hash` | Entire RunSpec JSON | Experiment identity (not a cache key) |
| `canonical_bundle_hash` | Logical zip members; strips `created_at` and confluence-combo siblings | Provenance / complete_run |

`build_identity_metadata` **omits** `execution_origin` so origin cannot change bundle hashes (`research_identity.py`).

### 1.3 Four RunSpec authors (same validator, different completeness)

| Author | Invents omitted keys? | Gate |
|---|---|---|
| Raw YAML / `validate_run_spec` | Product levels fill; `ingestion_mode` → `primary`; batteries `.get("enabled", True)` | Shared validator |
| `classic_export.classic_state_to_run_spec` | **No** — `ClassicExportGap` | Requires `levels_settings`; no default injection |
| `thesis_compiler.compile_run_spec` | **No** — rejects non-canonical keys | Explicit API sections only |
| Study expand | Product plane; batteries `{enabled:false}` | Slice 6 lock |

---

## 2. Must-answer questions

### Q1. Warm cache hash-stable including 15s-primary? Can two different ingest stories collide?

**Cold vs warm `run_experiment` is hash-stable for `canonical_bundle_hash`, parent frames, and 15s `subtimeframe_data` on the tested paths. Source bindings do not cross `ingestion_mode`. `dataset_id` / data-artifact keys *can* collide when two ingest stories produce the same parent OHLC.**

Evidence:

- `tests/test_cai3_cached_pipeline.py` `test_cold_and_warm_read_write_match_bundle_and_frames`, `test_off_and_read_write_bundle_hashes_match`.
- `tests/test_15s_primary_persistence.py` `test_api_15s_primary_cache_write_does_not_warm_cross_primary_mode` — warm `data` status `hit`; bundle hashes and both frames equal; derive binding ≠ primary binding on the same 15s bytes.

15s-primary warm path (`api._load_15s_primary_experiment_data`): **always** re-reads and re-derives the source CSV. Artifact may replace **parent only** when `binding.identity.dataset_id() == data_identity.dataset_id()` (`api.py`). Subtimeframe is never served from a data artifact.

Source binding partitions on ingest story (`execution_artifacts.source_binding_key`):

```854:864:thesistester/persistence/execution_artifacts.py
    payload = {
        "kind": SOURCE_BINDING_KIND,
        ...
        "ingestion_mode": str(ingestion_mode or "primary"),
        "derivation_policy": derivation_policy,
    }
```

`DataIdentity.dataset_id()` does **not** include `ingestion_mode` or `derivation_policy` (`research_identity.py` L112–129; `local_store.compute_dataset_id`).

| Collision | Result |
|---|---|
| Same 15s bytes, `15s_primary_derive_1m` vs omitted/`primary` | Different experiment (`base_interval` 1m vs 15s). Bindings isolated. Tested (SIA + 15s persistence). |
| Native 1m CSV vs 15s-derived 1m with **identical parent OHLC** | **Same** `dataset_id` and (same profile) `data_artifact_key`. Levels cache can hit across stories. Subtimeframe / R12 path still differs. **No named test.** |
| `LEVEL_ENGINE_VERSION` bump | Levels miss (`_MISS_ENGINE_INCOMPATIBLE`). Fail-closed. Tested. |
| Stale source bytes | Binding `source_content_hash` miss. Tested. |
| Derive **code** change, same `derivation_policy` string | Binding key unchanged → stale parent artifact + fresh source. **No test.** |
| RunSpec `dataset.data_identity` / `data_artifact_key` | Validated, **ignored** at load. Execution recomputes identity. Spec can lie. |
| Direct `compute_levels(data=A, data_identity=B, cache_policy="read")` | Levels artifact for B served on frame A. `run_experiment` does not expose this (passes recomputed identity). |

**Bad case (medium):** operator A runs 15s-primary derive; operator B points a vendor 1m file whose derived-equivalent OHLC matches. Same levels cache object; R12 subtimeframe (A) vs none/other (B). Parent+levels look identical; fills can differ.

**Cache policy who-sets-what:** API default `off`; CLI / study / assistant force `read_write`; classic UI bypasses artifacts. Unknown policy → `off`.

---

### Q2. Bundle restore vs leftover uploaders / session_state: can restore mix stale Data-page frames with bundle trades?

**Uploader nonce is still implemented and tested. Restore can still mix leftover *non-managed* keys (and a saved-dataset bootstrap) with imported trades.**

ARCHITECTURE nonce claim (`docs/ARCHITECTURE.md` L1211–1218) is **accurate when the Data page runs** after import:

- `apply_research_bundle_to_session` sets `DATA_PAGE_INVALIDATE_SOURCE_KEY = True` (`research_bundle.py` L1073–1077).
- `pages/1_Data.py` `_consume_data_page_source_invalidation` increments primary + subtimeframe uploader nonces and pops stale upload signatures.

**What restore writes:** `session_values` from included sections; Admit widgets rehydrated from `entry_window`; invalidate flag.

**What it clears:** `_MANAGED_RESEARCH_KEYS` only (plus Admit widgets). Then restores included keys.

**Not in `_MANAGED_RESEARCH_KEYS` and not in `_BACKTEST_META_KEYS`:**

| Leftover key | In UI bundle? | In CLI/`run_experiment` bundle? | Risk after import |
|---|---|---|---|
| `otf_filter_summary` / `otf_filter_result` | Written by page 7; **not exported** | `run_experiment` writes `backtest_otf_filter` only; **also not exported** | Report reads `otf_filter_summary` (`reporting.build_otf_filter_metadata` L260) → **prior UI OTF counts on imported trades** |
| `setup_config` | Survives | Written to state; **not** in `_SIGNALS_META_KEYS` | Report `configuration.setup_config` can be pre-import setup |
| `focused_trades` / `focused_equity_curve` | Session-local by design | N/A | Focus UI vs restored `trades` |
| `dataset_source_path` / `source_csv_path` | Survives | N/A | Path caption vs imported bars |
| `display_timezone` / `raw_data` | Survives | N/A | Export TZ / raw capture describe old session |

**Bootstrap mix (high):** `pages/12_Research_Bundles.py` L27 calls `bootstrap_active_saved_dataset()` **first** on every rerun. Import of a dataset-less (backtest-only) zip pops `data`, then `st.rerun()`. Next run: `"data" not in session` → bootstrap reloads the **active saved dataset** while restored `trades` remain (`app_state.py` L82–126).

**Bad case:** session has saved dataset A. Import a zip with `included.dataset=false` and trades from experiment B. After rerun: `data`=A, `trades`=B. Charts / identity badges disagree. Assistant “Open exact” hash-verifies first (`orchestrator.restore_run_bundle_to_session`); page 12 `load_research_bundle` does **not**.

**Page 12 hash:** schema/section validation only (`pages/12_Research_Bundles.py` L167–242). Tampered `trades.parquet` imports.

---

### Q3. Assistant numbers without packet paths? Can tools invent metrics?

**Discuss / LLM Explain: every numeric claim needs a packet path and is server-audited. Help uses a corpus digit allowlist (not packet paths). Voice persisted text is fail-closed; live PCM can speak first. Projections are deterministic post-hoc math, not LLM invention.**

| Channel | Gate | Invent? |
|---|---|---|
| Discuss (`results_qa`) | System prompt + `assert_llm_explanation_grounded` (`results_qa.py` L106–132, L305–311) | No if auditor passes |
| LLM Explain | Same auditor | No |
| Deterministic Explain | `assert_claims_grounded` on structured claims | No; narrative is code-built |
| Help | `assert_help_reply_grounded` — digit tokens must appear in corpus/registry | No run metrics (remediated) |
| Voice transcript | `audit_spoken_text` vs bound packet + tool returns | Persisted text replaced if ungrounded |
| Voice live PCM | Documented: cannot pre-gate once spoken (`sidecar.py` L509–531) | **Brief spoken hallucination possible** |
| `results_projections` | Server-computed; ephemeral `results.projections.*` | Not invented; still post-hoc ranking |

AGENT_GUIDE L315–316 (“every numeric claim needs a packet path”) is **true for Discuss/Explain**, not for Help (by design) or live voice.

**Bad case (blocked):** model writes “PF 2.5” citing `win_rate=0.6` → `Uncited numerical claim`.

**Bad case (open):** realtime duplex utters “profit factor 3.2” before transcript remediation. `require_tool_for_numbers = true` in `config/assistant.toml` is **loaded and unused**.

**Hash gap:** `summarize_bundle_time_analysis` / `run_bundle_otf_validation` / `preview_bundle_resample` / `validate_bundle_roll_assumptions` call `_read_verified_bundle` **without** `expected_hash` / `require_hash=True` (`tools.py` L798–864). Swapped file at an allowed path yields invented-looking analytics from tampered bytes. Discuss/complete_run paths that pass `expected_hash` stay fail-closed.

---

### Q4. `STUDY.run` without approval triple? What is default-off vs what actually executes?

**Default-off is real. `confirmed=True` alone is insufficient *over* `confirm_above_runs` (default 200). Under that threshold, `confirmed=True` executes without the triple. The Streamlit page does not call `STUDY.run`.**

| Flag / tool | Default | Executes? |
|---|---|---|
| `[assistant.study_tools] enabled` | **`false`** (`config/assistant.toml` L41–44) | Handler raises `StudyToolsDisabledError` before work |
| `[assistant.voice] enabled` | **`false`** | No sidecar |
| `[assistant.execution] require_explicit_confirmation` | `true` | Orchestrator APPROVAL_REQUIRED |
| `[assistant.results_qa]` / `[assistant.product_help]` | `true` | Chat only; AGENT_GUIDE: never `PIPELINE.*` / `execute_confirmed_run` |
| Voice tools | Read-only allowlist | Cannot execute |

`STUDY.run` when flag **on**:

1. `ensure_study_tools_enabled()`.
2. If `run_count >= confirm_above_runs` (default **200**): `_validate_approval` requires `payload.approval == {study_identity_hash, run_count, output_dir}` (`study/tools.py` L345–379). `confirmed=True` alone raises.
3. Orchestrator surfaces the bound triple on APPROVAL_REQUIRED (`orchestrator.py` L292–308). Forged `action=list` does not skip (`L2023–2024`).
4. Then in-process `run_study` (`run_study_capability` L439).

**Bad case (by design, under-documented):** pdPOC 40-cell study with `study_tools` on. `dispatch(STUDY.run, confirmed=True)` **without** `payload.approval` executes — 40 < 200. Triple is a large-N gate, not a universal execute lock.

**Other execute surfaces:**

| Path | Gate |
|---|---|
| Page 14 **Run confirmed research** | `execute_confirmed_run` — repository `spec.status == "confirmed"` (`pages/14_Research_Assistant.py` L2054–2059) |
| `orchestrator.dispatch(PIPELINE.run_experiment, confirmed=True)` | **No** repository Confirm. Handler runs payload `run_spec` immediately (`handlers.py` L104–109). Chat/Discuss do not call this. Library/agent surface. |
| `TIME.analyze` / OTF / resample / roll | EXPLICIT or none; **no bundle hash** (Q3) |
| Voice | No execute tools |

---

### Q5. Secrets in logs / artifacts / assistant traces / `.env`?

**Repo contract is tight. Keys are not in TOML or `.env.example`. Provider errors are sanitized. Residual: audit payloads are caller-controlled; sidecar env forward is required.**

| Channel | Finding |
|---|---|
| `.env.example` | **Only** `THESISTESTER_STORE_DIR` |
| `load_repo_dotenv` | Applies **only** `THESISTESTER_STORE_DIR`; other `.env` keys ignored (`local_store.py` L98–103) |
| `config/assistant.toml` | Non-secret settings. No API keys |
| `OPENAI_API_KEY` / `XAI_API_KEY` | Env first, then Streamlit Secrets; placeholder strings rejected |
| LLM errors | `_sanitize_provider_error_text` strips exact key + `Bearer …` (`llm.py` L50–61) |
| Voice sidecar | `# Never log api_key`; `redact_for_logs`; loopback bind; browser gets ephemeral token only |
| Bundles | No secret schema fields. User prose in setup description could leak if the operator put a key there |
| `_record_audit` | Persists `request.to_dict()` **without** secret scrubbing (`orchestrator.py` ~L2054) — malicious `api_key` field in a custom payload would be stored |

**Bad case (low):** a caller puts `OPENAI_API_KEY` in a tool payload → conversation JSON on disk. Not the default UI path.

---

### Q6. Prose fields becoming executable RunSpec keys?

**No on the shipped compilers. Chat/thesis text cannot become `selected_levels` / `trigger` / `dataset.path`.**

| Path | Prose → executable? |
|---|---|
| `thesis_compiler.compile_run_spec` / `map_thesis_choices_to_run_spec` | **No.** Unknown keys raise (`thesis_compiler.py` L112–117, L198–215). Prose only feeds clarifications |
| `handle_chat_turn` | Drafts non-executing choices; never `dispatch` / `execute_confirmed_run` (AGENT_GUIDE L325–326) |
| `classic_export.classic_state_to_run_spec` | **No.** Missing params → `ClassicExportGap`; never invents levels (`classic_export.py` L144–151, L636–637) |
| `classic_proposal` | Allowlisted page patches; Apply is a separate user action |
| Study YAML from assistant | `yaml.safe_dump` of a validated mapping only |

**Bad case (blocked):** chat “use dVWAP as the level” stays a clarification unless `levels.session_vwap_enabled` is staged as a structured key.

---

### Q7. `run_batch` vs `run_study`: fail-fast vs continue; `execution_origin`; `base_directory`; index column parity

**Slice 6 lock confirmed at the CLI/API layer. They share `validate_run_spec` + `run_experiment`. They do not share abort semantics, origin, path parent, or index `status`.**

| | `run_batch` (`cli.py`) | `run_study` (locked) |
|---|---|---|
| Fail vs continue | **Fail-fast.** `_execute_run` has no try/except (L117–127). First raise aborts; index write is after the loop (L199–204) → **no index if any cell dies** | Continue; failed row + no zip |
| `execution_origin` | `"cli"` | `"study"` |
| `cache_policy` | `read_write` | `read_write` |
| `base_directory` | `experiment_path.parent` (`cli.main` L251–254) | StudySpec parent |
| Index | `R18_INDEX_METRIC_KEYS` + `bundle_path` | Same metrics + `bundle_path` + **`status`** |
| Validator | Same `validate_run_spec` (L18, L62, L182) | Same, inside `run_experiment` |

`_coerce_index_float` is **duplicated** in `cli.py` (comment L78–79) to avoid cli↔study import. Behavior is intended to stay aligned.

**Bad case:** 5-run YAML, run 2 raises in `generate_signals`. Run 1 zip may already exist in workers>1 memory but **no** `results_index.csv`. Study would mark cell 2 `failed` and continue.

**Replay:** `python -m thesistester run out/study1/experiment.yaml` is fail-fast, `origin=cli`, and resolves relative `dataset.path` against **output_dir**. AGENT_GUIDE L38–39 still advertises this as “unchanged R18 path.” Slice 6 critical finding **stands**.

Assistant `base_directory` is `dataset_path.parent` (`tools.py` L355) — a **third** parent plane.

---

### Q8. UI vs API vs CLI vs Assistant composer disagreement

**Two execution composers remain (UI pages vs `run_experiment`). CLI / study / assistant are the same API composer with different provenance/cache/path parents. Disagreements that change admissions or batteries are still live.**

| Topic | UI | API / CLI / assistant / study | Severity |
|---|---|---|---|
| OTF resolve **order** | Shared `resolve_otf_config` (signal_settings → setup → …) | Same | Aligned |
| OTF **timezone** | `session_state.exchange_timezone or inst.exchange_tz` (`pages/7_Backtest.py` L207–209) | `session_timezone=inst.exchange_tz` (`api.run_backtest` L1605) — **ignores** `dataset.exchange_timezone` used for load (L2583) | **High** (Slice 4 lock still true) |
| OTF `T` | `trigger_timestamp` else `timestamp` | Same engine | Aligned |
| Cutoff without flatten | Widgets force `no_new_entries_after=None` unless flatten on (page 7 L397–398) | YAML accepted; passed through (`api.py` L1624) | **High** |
| Backtest frame | `levels` if present else `data` (page 7 L194–198) | Always `level_payload["levels"]` (`api.py` L2677–2678) | **High** when stale |
| `BASE_COLUMNS` / `close` | Pickers use `available_level_columns` | `validate_setup_config` rejects hits only (`setup.py` L405–412), **not** `BASE_COLUMNS` | **Medium** (Slice 3 lock) |
| Batteries `enabled` | Page widgets | `.get("enabled", True)` for grid/WFA/validation (`api.py` L2766, L2806, L2841). Assistant `_bounded_spec` same trap (`tools.py` L70, L91, L113). Study emits `{enabled:false}` | **High** for raw YAML |
| Omitted `ingestion_mode` | Data page recommends 15s-primary | `primary` (`api.py` L543, L2587) | **High** for 15s files |
| Omitted `levels` | Page sparse setdefaults | `{**DEFAULT_LEVELS_SETTINGS, **raw}` | **Medium** |
| Classic export cutoff | Clears cutoff when flatten off (`classic_export.py` L252–256) — **UI-shaped**, not raw YAML | YAML can keep cutoff | Composer fork |

Pages **never** call `api.run_experiment`. Parity is tested (`test_api.py`, `test_cli.py`, `test_assistant_execution_parity.py`), not a shared page function.

**Bad case (OTF TZ):** Data page sets `exchange_timezone: "UTC"` on MNQ. UI OTF localizes naive `T` to UTC. Headless OTF uses instrument `America/Chicago` (or preset). Same bars, different HTF alignment.

**Bad case (enabled trap):**

```yaml
grid:
  stop_loss_ticks_values: [4, 8, 12]
  take_profit_ticks_values: [8, 16, 24]
  # enabled omitted → full grid runs
```

Study expand cannot emit this (Slice 6). Hand-written R18 YAML and assistant `_bounded_spec` can.

---

### Q9. `reporting.py`: diagnostic-only banners exported? `pnl_points` vs net? Focus/OTF honesty in the zip?

**Report is a session dump, not a re-sim. R10–R16 / OTF-matrix / combo / portfolio banners exist. Phase 8 `validation_summary` has no section banner and no `diagnostic_only` flag. Trade CSVs include unlabeled gross `pnl_points` next to net-R summaries. OTF honesty in the *research bundle* is structurally missing; the *report* zip can attach leftover session OTF.**

| Section | MD banner | JSON flag |
|---|---|---|
| Excursion / MC / noise / sensitivity / portfolio | `⚠️ Diagnostic only` (`reporting.py` L1505–1593) | No `diagnostic_only` key |
| OTF **validation** matrix | `⚠️ Diagnostic only` | No |
| Confluence combo | `⚠️ Diagnostic only` (recomputed on export from session trades) | No |
| Phase 8 `validation_summary` | **Metrics only** (`## Validation Diagnostics` L1491–1497) | Raw dict L379 |
| Walk-forward | Metrics only | No |
| Global `_CAVEATS` | “validation diagnostics are descriptive only” (L30–35) | Caveats list |

Focus/Admit: `build_entry_window_metadata` exports `is_post_hoc` / `is_not_admit` (good). Focus frames are **not** in the research bundle.

OTF filter: `build_otf_filter_metadata` reads **`otf_filter_summary`**, not `backtest_otf_filter` (L243–260). `_BACKTEST_META_KEYS` includes neither (L59–77). So:

- Live UI session → report OTF section is honest for *that* session.
- After bundle import, leftover `otf_filter_summary` can describe a **different** backtest.
- CLI/study zip never carries backtest OTF counts.

**`pnl_points`:** glossary / Slice 5 lock: gross. `r_multiple` / `pnl_currency` net. Report MD quotes win rate / avg R / total R (net). `trades.csv` / JSON tables / bundle `trades.parquet` dump engine columns **without** a gross/net label (`pages/11_Report_Export.py` L299–332).

**Bad case:** costs > 0. Analyst sums exported `pnl_points` and compares to `trade_summary.total_r` → systematic mismatch.

**Timezone:** artifact includes `timezone_contract`; table timestamps converted to `display_timezone`; `generated_at` is UTC. Tested.

Page 11 does **not** call `bootstrap_active_saved_dataset`. It exports whatever is in session (including leftovers).

---

### Q10. Test gaps vs `AGENT_GUIDE`. Goldens ≠ correctness.

**313 passed** on the named Slice 7 suites. Coverage is strong on identity normalization, cold/warm bundle parity, 15s binding isolation, bundle schema, CLI validate, classic export gaps, STUDY default-off + approval triple, Discuss/Explain grounding, dotenv store-only.

AGENT_GUIDE remaining claims vs this slice:

| AGENT_GUIDE claim | Verdict |
|---|---|
| L38–39 replay `experiment.yaml` as unchanged R18 | **False as identity** (Slice 6 + Q7) |
| L154–155 omitted `ingestion_mode` = primary | True |
| L263–264 canonical hash ignores zip time metadata | True |
| L308–309 completed-run hash match | True on **assistant** complete/open-exact; **false** on page 12 import |
| L293–297 compiler rejects prose-only fields | True |
| L315–316 every numeric claim needs a packet path | True for Discuss/Explain; not Help/live voice |
| L325–326 chat never dispatch/execute | True |
| L338–348 secrets not in TOML; sanitize provider errors | True |
| Help-corpus paths frozen | True (`help_corpus.py`; AGENT_GUIDE excluded from corpus) |

**Missing tests vs this slice’s claims:**

| Gap | Severity |
|---|---|
| Primary 1m vs 15s-derived 1m sharing `data_artifact_key` / levels hit | **High** |
| Page 12 import of hash-tampered zip | **High** |
| Bootstrap-after-dataset-less-import mixes `data`/`trades` | **High** |
| Leftover `otf_filter_summary` / `setup_config` / `focused_trades` after import | **High** |
| `_BACKTEST_META_KEYS` omits OTF summaries | **High** |
| `run_experiment` ignores RunSpec `data_identity` | **Medium** |
| Derive-code change under constant `derivation_policy` | **Medium** |
| Phase 8 MD/JSON diagnostic labeling | **Medium** |
| `pnl_points` unlabeled in export | **Medium** |
| `PIPELINE.dispatch(confirmed=True)` vs `execute_confirmed_run` | **Medium** |
| TIME/OTF/resample/roll bundle reads without hash | **Medium** |
| `close` in `selected_levels` rejected (API) | **Medium** (locked leak; still no test) |
| `require_tool_for_numbers` unused | **Low** |
| Goldens / 313 passed ≠ restore/composer honesty | **Low** (process) |

---

## 3. Prioritized findings

### Critical

None that silently rewrite fills on the default `run_experiment` / verified-artifact path. The worst Slice 7 failures are **honesty, restore isolation, and composer disagreement** — they can make two “the same” experiments or reports describe different admissions or leftover diagnostics.

### High

1. **Research-bundle restore does not manage OTF / setup / Focus frames; Report reads leftover `otf_filter_summary`.**  
   `_MANAGED_RESEARCH_KEYS` and `_BACKTEST_META_KEYS` omit `otf_filter_summary` / `backtest_otf_filter` / `setup_config` / `focused_trades`. `run_experiment` stores `backtest_otf_filter`; reporting reads `otf_filter_summary`.  
   `research_bundle.py` L59–77, L120–212; `api.py` L2725; `reporting.py` L260; `pages/7_Backtest.py` L635–639.  
   **Bad case:** UI OTF run (12 rejected), then import a CLI zip (different trades, OTF off). Report OTF section still shows 12 rejected.

2. **Page 12 import is not hash-fail-closed; dataset-less import + `bootstrap_active_saved_dataset` can pair saved `data` with bundle `trades`.**  
   `pages/12_Research_Bundles.py` L27, L167–242; `app_state.py` L82–85. Assistant open-exact verifies hash.  
   **Bad case:** backtest-only zip + active saved dataset A.

3. **Uploader nonce works; leftover *session keys* still mix.** ARCHITECTURE nonce claim holds for Data-page widgets (`research_bundle.py` L1073–1077). It does not cover F1 leftovers.

4. **Composer admissions still disagree (Slice 4, still true at this layer).**  
   OTF TZ: UI session vs API instrument (`pages/7_Backtest.py` L207–209 vs `api.py` L1605).  
   Cutoff-without-flatten: YAML yes, UI/classic-export no.  
   Frame: UI `levels` else `data`; API always levels.  
   **Bad case:** `exchange_timezone: UTC` in YAML load + instrument Chicago OTF.

5. **Raw YAML / assistant `_bounded_spec` default-on batteries.**  
   `grid`/`walk_forward`/`validation` `.get("enabled", True)` (`api.py` L2766+). Study cannot emit this.  
   **Bad case:** omitted `enabled` on a `grid:` block runs a full sweep.

6. **`dataset_id` does not encode ingest story.** Same parent OHLC → shared levels cache across primary vs 15s-derived. Bindings do not cross.  
   `research_identity.DataIdentity.dataset_id`; `execution_artifacts.source_binding_key`.

7. **Advertised `experiment.yaml` replay ≠ `study run` when paths are relative.** AGENT_GUIDE L38–39 still says it. `cli.main` L251–254 vs study parent. Fail-fast vs continue. Extra index `status` column.

### Medium

8. **`validate_setup_config` still accepts `BASE_COLUMNS` (`close`).** UI pickers filter; API/CLI/assistant `build_setup` do not. Slice 3 lock confirmed.

9. **Phase 8 `validation_summary` exported without a diagnostic-only section banner or flag.** Relies on global caveats. R10–R16 are labeled; Phase 8 is not.

10. **Export CSVs mix unlabeled gross `pnl_points` with net-R summaries.**

11. **`PIPELINE.run_experiment` via `dispatch(confirmed=True)` skips repository Confirm.** Page 14 uses `execute_confirmed_run`. Chat does not dispatch. Library/agent surface.

12. **Bundle analytics tools skip hash verification** (`tools.py` L798+). Discuss/complete_run do not.

13. **`compute_levels` trusts caller `data_identity` for cache lookup** (`api.py` L1417–1425). Not on `run_experiment` path.

14. **RunSpec `data_identity` / `data_artifact_key` are non-authoritative.** Validated, ignored at execute.

15. **Voice live PCM can speak ungrounded digits; `require_tool_for_numbers` is dead config.**

16. **Omitted `levels:` → full product `DEFAULT_LEVELS_SETTINGS`.** Classic export refuses to invent. Headless expands silently.

17. **Three `base_directory` parents** (experiment YAML / StudySpec / dataset file) + promote cwd-first pin (Slice 6).

18. **`STUDY.run` under `confirm_above_runs` (200) executes with `confirmed=True` and no triple** when `study_tools` is on.

### Low

19. `format_profile` omitted from `dataset_id` (documented CAI-1).
20. Audit `tool_entry.request` not secret-scrubbed.
21. 15s-primary always re-parses source (correctness-preserving).
22. Goldens / 313 passed ≠ restore or composer honesty.
23. `app.py` hub copy still linear through Report; Studies is a parallel product (Slice 0 flag).

---

## 4. Residual risks (not closed here)

- Slice 4 flatten leak and Slice 5 Focus / WFA / OTF-matrix bugs still apply to **per-cell and restored bundles** if an operator opens a zip on classic pages.
- Soft resume / warm cache trust existing artifacts when identity hashes match; derive-code drift without a `derivation_policy` bump is untested.
- `study_identity_hash` is authored StudySpec bytes, not merged product levels or resolved CSV bytes (Slice 6 residual).
- Help corpus can lag UI labels (frozen paths — do not casually move).
- Operator notes outside the repo (chat, Notion) may store provider keys; that is not a code path and was not treated as product SoT.
- Windows store `MAX_PATH` / `\\?\` prefixing is implemented in `execution_artifacts` / `local_store` and was not re-probed on Windows here.

---

## 5. Contracts the FINAL MERGE must lock

### Pipeline / composers

1. **Two execution composers.** UI pages call engine/analytics directly. `run_experiment` is the headless composer. CLI / study / assistant call `run_experiment` only (different origin / cache / `base_directory`). Pages do not call `run_experiment`.
2. **Shared validator, not shared defaults.** `validate_run_spec` is one function. Omitted `ingestion_mode` = `primary`. Omitted levels keys = product `DEFAULT_LEVELS_SETTINGS`. Omitted battery `enabled` = **True** on API/CLI/assistant; Study emits `{enabled:false}`.
3. **`validate_setup_config` does not reject `BASE_COLUMNS`.** UI pickers do. Study factors cannot name `close` today.
4. **OTF `T` = `trigger_timestamp` else `timestamp`.** OTF TZ: UI may use session `exchange_timezone`; API OTF uses `inst.exchange_tz`.
5. **Cutoff-without-flatten is headless-legal; UI/classic-export force `None`.**
6. **`run_experiment` always backtests the levels frame.** UI prefers levels else data.
7. **`run_batch` fail-fast, `origin=cli`, no `status` column, index written only if all cells succeed.** `run_study` continue, `origin=study`, index includes `status`. Relative paths: experiment parent vs StudySpec parent vs assistant dataset parent. Replay of `experiment.yaml` is **not** `study run`.
8. **Cache:** API default `off`; CLI/study/assistant `read_write`. Cold vs warm bundle hash equal on tested paths including 15s-primary. `execution_origin` excluded from identity. `dataset_id` excludes ingest story; `source_binding_key` includes it. Subtimeframe is never a data artifact. Engine-version drift is a miss.
9. **Goldens ≠ correctness.** Legacy identity only.

### Persistence / bundles / report

10. **Nonce invalidation** prevents leftover *upload widgets* from replacing imported `data` after Data-page navigation. It does **not** clear `otf_filter_summary`, `setup_config`, or `focused_trades`.
11. **Page 12 import** is schema-only. Assistant complete/open-exact is hash-fail-closed.
12. **Bootstrap** rehydrates saved `data` when missing — including after a dataset-less bundle import.
13. **Report is session export, not re-sim.** Combo is recomputed from session trades (diagnostic). Phase 8 has no `diagnostic_only` flag. `pnl_points` is gross; crowned R is net.
14. **Dotenv loads only `THESISTESTER_STORE_DIR`.** Secrets via env / Streamlit Secrets, never `assistant.toml` / `.env.example`.

### Assistant / classic

15. **`STUDY.*` default-off.** When on: over `confirm_above_runs` (default 200) requires bound approval triple; `confirmed=True` alone is insufficient. Under threshold, `confirmed=True` executes. Voice default-off; voice tools cannot execute.
16. **Discuss/Explain numbers require packet paths + auditor.** Help uses corpus digits. Live voice PCM is not pre-gated.
17. **Prose cannot become RunSpec keys** (`thesis_compiler`, `classic_export`). Chat never `dispatch` / `execute_confirmed_run`.
18. **Page 14 Run confirmed** goes through `execute_confirmed_run` (confirmed spec). Direct `PIPELINE.dispatch(confirmed=True)` is a separate library gate.
19. **Help-corpus paths stay frozen.** Do not move USER_GUIDE / ARCHITECTURE / ASSUMPTIONS / METRICS / otf-filter / research-methodology / README to “fix” honesty.

### Prior slices (still merge-blocking)

20. Focus post-hoc; WFA overlap sum; OTF-matrix train-path leak; flatten calendar-RTH; `session` ≠ `trading_session_date`; product vs bare levels; Study ranking ignores WFA OOS; failed cells under-reported in study MD.

---

## 6. Open items (do not assume)

1. Whether `dataset_id` / levels cache will include `ingestion_mode` + `derivation_policy` (or a derive-code version).
2. Whether `_MANAGED_RESEARCH_KEYS` / `_BACKTEST_META_KEYS` will include OTF summaries and `setup_config`, and whether reporting will read `backtest_otf_filter`.
3. Whether page 12 import will require `canonical_bundle_hash` (assistant-parity).
4. Whether bootstrap will refuse to refill `data` after a bundle import that omitted dataset.
5. Whether `validate_setup_config` will reject `BASE_COLUMNS`.
6. Whether battery `enabled` will default **false** (Study already does).
7. Whether API OTF will honor `dataset.exchange_timezone`.
8. Whether UI will allow cutoff without flatten (or YAML will reject it).
9. Whether Phase 8 JSON/MD will gain `diagnostic_only` / a banner; whether trade CSV will label `pnl_points` gross.
10. Whether `PIPELINE.dispatch` will require a confirmed repository spec (page already does).
11. Whether TIME/OTF/resample/roll tools will require `expected_hash`.
12. Whether `confirm_above_runs` under-threshold `STUDY.run` will still require the triple.
13. Whether AGENT_GUIDE L38–39 will stop advertising experiment.yaml replay as identity-equivalent.
14. Whether product will pin Study `dataset.path` at expand time (Slice 6 open).

---

## 7. How the FINAL MERGE should start

1. Treat §5 as the locked persistence / composer / assistant contract. Do not re-open fill/3c/WFA math except to list inherited bugs on restored bundles.
2. Do not treat passing goldens, 313 Slice 7 tests, or a matching `canonical_bundle_hash` as proof that restore, report labels, or UI↔API admissions agree.
3. Do not treat page 12 import, Report zip, and Assistant open-exact as the same integrity bar.
4. Do not treat `thesistester run experiment.yaml` as `study run`.
5. Do not treat Discuss packet-path grounding as covering Help, live voice, or hash-less bundle analytics.
6. Single remaining SoT question for merge: **what is causal at time T** across levels, 3c, OTF, R12, Admit, WFA — plus **which composer** applied it.

---

## 8. How Slice 7 started (traceability)

Read Slice 0 map (two composers; Slice 7 include list; Qs 445–451), Slices 1–5 locked clocks/PIT/signals/fills/analytics, Slice 6 §5 Study locks + §7 start notes.

Scoped to `thesistester/api.py` (full orchestration), `cli.py`, `research_identity.py`, `research_bundle.py`, `reporting.py`, `persistence/`, `classic_*`, `assistant/` (+ `voice/`), `pages/11_Report_Export.py`, `12_Research_Bundles.py`, `14_Research_Assistant.py`, `app.py`, `app_state.py`, `config/assistant.toml`, `.env.example`, matching tests, and AGENT_GUIDE remaining + ASSUMPTIONS persistence/export + voice/help docs.

Did not re-audit level family math, 3c rules, `simulate_trades` fills, WFA fold construction, or Study expand/report/promote internals except API/CLI replay and `STUDY.run` approval.
