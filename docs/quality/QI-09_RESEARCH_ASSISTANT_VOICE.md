# QI-9 — AI Research Assistant and voice

**Slice:** QI-9 (research-only)
**Status:** Completed
**Audited commit:** `539dd2e` (`539dd2e9dabc9ba918f03b26f66537f3d9fca3ce`) — `main` after merge of [#488](https://github.com/AccumuLatata/ThesisTester/pull/488) (QI-5)
**Commit date:** 2026-09-12
**Environment:** Ubuntu 24.04.4 LTS, Python 3.12.3, pandas 3.0.5, numpy 2.4.4, streamlit 1.63.0, radon 6.0.1, vulture 2.16, bandit 1.9.4, pytest 9.1.1
**Store:** `THESISTESTER_STORE_DIR=/tmp/qi09-store-*` (throwaway). `OPENAI_API_KEY` / `XAI_API_KEY` unset. Stub providers only. No desk data.
**Finding count:** 11 (C/H/M/L = 0/1/6/4)
**Time spent:** one agent run on 2026-09-12.

`AUDIT_FINAL.md` §5 and `docs/AUDIT_HONESTY_IMPLEMENTATION_PLAN.md` §2 are premises. Completed assistant series (AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX) stay locked — this slice does **not** propose provider swaps, RUX layout changes, or reopening those contracts. No backtest, metric, or Study result is described as correct or reliable.

## Commands run (verbatim)

```bash
git fetch origin main
git checkout main && git pull origin main
# HEAD 539dd2e9dabc9ba918f03b26f66537f3d9fca3ce
git checkout -b cursor/qi-09-research-assistant-voice-033a

export THESISTESTER_STORE_DIR=/tmp/qi09-store-before
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=no
# before: 3966 passed, 5 skipped in 142.82s (0:02:22)

radon cc thesistester/assistant pages/14_Research_Assistant.py -s -n D --total-average
radon mi thesistester/assistant pages/14_Research_Assistant.py -s
vulture thesistester/assistant pages/14_Research_Assistant.py --min-confidence 60
vulture thesistester/assistant pages/14_Research_Assistant.py --min-confidence 80
bandit -r thesistester/assistant -ll -q
rg -n 'except Exception|except:' thesistester/assistant pages/14_Research_Assistant.py
rg -c 'st\.session_state' pages/14_Research_Assistant.py

PYTHONPATH=/workspace python3 /tmp/qi09_probes.py > /tmp/qi09-probes.json

export THESISTESTER_STORE_DIR=/tmp/qi09-store-evals
unset OPENAI_API_KEY XAI_API_KEY
pytest -q --tb=line \
  tests/test_assistant_llm_evaluations.py \
  tests/test_assistant_voice_evaluations.py \
  tests/test_assistant_registry_audit.py \
  tests/test_assistant_page_render.py \
  tests/test_assistant_help_corpus.py \
  tests/test_assistant_help_coverage.py \
  tests/test_assistant_llm.py \
  tests/test_assistant_voice_contracts.py \
  tests/test_assistant_execution_parity.py
# 199 passed in 14.15s

# collected: llm evals 41 · voice evals 26 · registry audit 3 · page render 16 · help coverage 55
```

Probe script lives at `/tmp/qi09_probes.py` (pasted in §10). Transcripts are not committed.

---

## 1. Scope actually covered (files) and anything skipped (why)

**Covered** (QI-0 exclusive ownership; 32 paths)

| Path | LOC | Role |
|---|---:|---|
| `thesistester/assistant/results_overview.py` | 4,373 | DI/RI Discuss matching, claim formatting, deterministic replies |
| `pages/14_Research_Assistant.py` | 2,581 | Chat-first Research Assistant page (RUX locked) |
| `thesistester/assistant/orchestrator.py` | 2,075 | Dispatch + draft/results/help/voice channel façades + `_record_audit` |
| `thesistester/assistant/voice/sidecar.py` | 1,266 | VA-5 localhost ASGI bridge |
| `thesistester/assistant/repository.py` | 1,230 | Local thesis / conversation / run store |
| `thesistester/assistant/workspace.py` | 1,221 | Session bootstrap / thesis-scoped staging |
| `thesistester/assistant/explainer.py` | 1,172 | Evidence packet + `_derive_caveats` |
| `thesistester/assistant/results_projections.py` | 1,115 | Grid/time/deep-trade hydration |
| `thesistester/assistant/voice/session.py` | 1,087 | PTT lifecycle / honesty |
| `thesistester/assistant/tools.py` | 903 | Headless adapters + `_bounded_spec` |
| remaining `thesistester/assistant/**` (21 modules) | 8,639 | Registry, handlers, LLM, Help, voice transport, UX |
| `config/assistant.toml` | — | Tracked non-secret settings; `study_tools` / `voice` default-off |
| `docs/VOICE_SIDECAR_OPS.md` | — | Read as spec (QI-13 owns the file) |
| **QI-9 `.py` total** | **25,662** | |

**Skipped (out of scope or not feasible here)**

- Live OpenAI / xAI calls — forbidden (rule 6). Channels exercised via existing offline evals + stub transports.
- Sidecar live WebSocket pumps / `ensure_local_sidecar` spawn — untestable-by-design (QI-11-01). Offline bind/redact/health-shape covered by voice evals.
- Mutation testing — QI-11.
- RUX layout / provider-swap proposals — locked; not opened.
- Living-doc amendments — named only (§8).
- `classic_*` chrome and page-12 import — QI-6. Assistant open-exact labels verified here only.

---

## 2. Code-quality readout

### 2.1 Metrics (QI-9 files, `539dd2e`)

| Metric | Value |
|---|---|
| `radon cc` D+ in scope | **F:** `_format_scalar_for_claim` **120**, `compose_deterministic_replies` **73**, `explainer._derive_caveats` **52**, `help_corpus.score_corpus_chunk` **51**. **E:** `handle_results_turn` 40, `_recover_results_reply` 36, `propose_results_reply` 35, `format_speakable_tool_result` 35, `VoiceSessionRecord.__post_init__` 34, `propose_help_reply` 33, `_decode_results_payload` 32, `_evaluate_discuss_match` 32, `_pump_upstream_to_browser` 32, `build_evidence_packet` 31, `_answer_results_ptt` 30. Average **B (6.00)** over 797 blocks |
| MI = 0.00 | `results_overview.py` · `orchestrator.py` · `workspace.py` · `repository.py` · `explainer.py` · `results_projections.py` · `pages/14_Research_Assistant.py`. `voice/session.py` 6.12 · `sidecar.py` 8.12 · `tools.py` 9.21 |
| Function length > 150 | `compose_deterministic_replies` 242 · `_format_scalar_for_claim` 239 · `build_prompt_path_catalog` 150 |
| Broad `except Exception` / bare `except` | **42** in `thesistester/assistant/` + **9** on page 14. Classified in §2.4 |
| `vulture` ≥80 | **4** unused params on `sidecar._NoRedirectHandler.redirect_request` (`fp`, `headers`, `msg`, `newurl`) — stdlib override signature; **false positive** (QI-0 named `fp`/`newurl`) |
| `vulture` ≥60 notable | `VoiceSettings.require_tool_for_numbers` unused outside `settings.py` (QI-09-09); several public aliases (`build_meaning_overlay`, `match_overview_intent`) used by tests/pages |
| Streamlit in assistant package | **2** lazy `import streamlit` (`llm._read_streamlit_openai_api_key`, `voice.xai_realtime._read_streamlit_xai_api_key`) + `st.secrets` only. No widgets. AST probe: 4 hits, all secrets |
| Coverage (QI-0 table, same product tree) | `handlers.py` 46% · `sidecar.py` 48% · `xai_realtime.py` 63% · `grounding.py` 66% · `orchestrator.py` 71% · `session.py` 72% · `results_overview.py` 84% (226 miss, top-10 absolute). Classification already QI-11-01 — not re-filed |
| `bandit -ll` | 4× B310 `urlopen` (`llm.py` ×1, `xai_realtime.py` ×3). URLs are hardcoded `https://api.openai.com/v1/responses` / `https://api.x.ai/v1` via `urllib.request.Request`. CI gap is **QI-12-06**; not re-filed |
| Page 14 | 2,581 LOC · 13 top-level `def` · 138 `st.session_state` lines · MI 0.00 |

### 2.2 `results_overview.py` responsibility map (exit criterion)

AST on `539dd2e`: **4,373** physical lines, **108** top-level functions, **0** classes. CC 120 / 73 match QI-0.

| Bucket | Symbols (count) | Approx LOC | CC hot | Role |
|---|---:|---:|---|---|
| Frozen config & cue tables | module constants | ~830 | n/a | Intent IDs, `REASON_*`, `KPI_CLAIM_PATHS` / `GRID_*` / `TIME_*` / `VALIDATION_*` / `ROBUSTNESS_*` / `ASSUMPTIONS_*`, overlay gloss |
| Intent matching & routing | 37 | ~570 | `_evaluate_discuss_match` E 32; `match_discuss_intent` D 21 | Normalize text → specialist/overview intent; residual veto |
| Evidence gates & projection glue | 26 | ~540 | low–mid | `present_*` / `has_*` / `_ensure_*_context` |
| Path catalog / citation hints | 2 | ~256 | `collect_existing_paths` ~15–20 | Bounded `existing_paths` + LLM `preferred_claim_paths` |
| Scalar → claim formatting | 2 | ~241 | **`_format_scalar_for_claim` F 120** (239 lines) | Path-typed narration; digit-grounding reject |
| Deterministic reply builders | 20 | ~1,179 | mid | Per-intent `build_deterministic_*` + `build_missing_*` |
| Mixed-ask composition | 4 | ~315 | **`compose_deterministic_replies` F 73** (242 lines) | RI-8 cap ≤3, `_absorb` dedupe, one overlay/auditor pass |
| Expert overlay / OOS / followups | ~12 | ~584 | `build_expert_overlay` D 24 | Digit-free meaning overlay |
| Recovery taxonomy | 2 | ~17 | low | `classify_recovery_reason` / `failure_class_from_exception` |
| Duplex envelope router | 1 | ~76 | `build_deterministic_discuss_reply` D 27 | Dispatch to builders or compose |
| Dynamic allowlist builders | 2 | ~97 | low | Indexed deep-trade / confluence paths |

**`_format_scalar_for_claim` is tabulatable.** Decision order is a `(path_pattern, value_type, template, reject_rule)` table: boolean honesty leaves → type reject → win-rate percent → numeric-by-prefix → time-bucket label → quoted string (reject ungrounded digits) → instrument mapping → fallback numeric. Boolean/suffix order (e.g. `valid_fold_count` before `fold_count`) must stay ordered.

**`compose_deterministic_replies` is partially tabulatable.** Intent→builder→evidence-gate is a table; `_absorb` claim-path dedupe and grid×assumptions / KPI×single-metric overlap stay as orchestration. Finding QI-09-01.

### 2.3 Registry × handler consistency

`FEATURE_PARITY_REGISTRY` = **55**. `HANDLER_REGISTRY` = **30**. `audit_capability_registry()`: routed 30 · unsupported 25 · **invalid 0**. `_assert_handler_coverage()` at orchestrator import. `get_handler` is None for no routed ID. No handler key outside the registry.

`tests/test_assistant_registry_audit.py` (3 tests) is a **structural** gate: no invalid rows; markdown lists every ID; routed have handlers; unsupported have limitations. It does **not** dispatch. Nine routed IDs have **zero** test-file mentions of the capability string (QI-09-04). Full matrix in §5.1.

### 2.4 Broad-except classification (assistant package + page 14)

| Class | Sites | Verdict |
|---|---|---|
| *narrow-guard OK* | `llm` / `xai_realtime` secrets `.get` and Streamlit import; `llm._openai_http_error_detail` body read; orchestrator `_record_audit` re-raises unless `best_effort`; page `_client_url_is_localhost` parse | Fail-closed or re-raise |
| *swallows chrome crash* | page identity captions (`except Exception:` → “identity unavailable”); sidecar pump teardown | UI must not die; loses diagnostic |
| *hides defect* | none confirmed — page open-exact / chat paths do `st.error(f"…{exc}")` | Actionable, not silent |
| *BLE001 fail-closed* | `orchestrator.dispatch` unexpected → audit + `APPROVAL_REQUIRED` / structured error | Honesty-preserving |

### 2.5 Provider isolation

OpenAI Responses (`llm.OpenAIStructuredClient`, endpoint `https://api.openai.com/v1/responses`) does not import `voice.*`. xAI unary/WS (`voice.xai_realtime`, `sidecar`) does not import `llm.py`. The **only** bridge is `VoiceSessionService.run_push_to_talk_turn` (xAI STT/TTS, optional OpenAI for results/help text). Sidecar never talks to OpenAI. Browser never receives the long-lived xAI key (page rejects sidecar JSON containing `api_key` / `token` / `client_secret` / `authorization`). `mint_ephemeral_token` exists and is tested fail-closed; **sidecar WS uses the full Bearer key server-side** (VA-5 localhost model; `VOICE_SIDECAR_OPS.md` is silent on ephemeral). Not a provider-swap proposal.

---

## 3. Application-quality readout (§3.2 per entry point)

### 3.1 Draft channel — `AssistantOrchestrator.handle_chat_turn`

| Check | Result |
|---|---|
| Happy path | Offline evals: `propose_thesis_draft` stub → persist messages. No capability `dispatch` |
| Empty / malformed | Empty thesis gate on page 14 (`test_no_thesis_selected_renders_only_the_thesis_gate`) |
| Fail-closed without key | `require_openai_api_key` → `LLMConfigurationError` “Set OPENAI_API_KEY to a rotated credential.” Page: `st.error(str(exc))` |
| Injection | `test_prompt_injection_cannot_request_tools_or_execution`; `test_chat_turn_cannot_bypass_confirmation_or_dispatch` |
| Composer parity | Draft does not run the pipeline. Confirm-run goes through `execute_confirmed_run` (AH §2 item 1 — two composers; not collapsed) |
| Honesty | Prose cannot become RunSpec keys (`AUDIT_FINAL` §5.4 item 40; evals) |
| Persistence | Conversation messages; draft history excludes `results_qa` / `product_help` / voice tags |
| AO1 authoring | Draft setup form `min_valid_confluences` `min_value=1` — cannot author locked-legal `0` (QI-09-11; QI-03 handoff) |

### 3.2 Results / Discuss — `handle_results_turn` / `results_qa`

| Check | Result |
|---|---|
| Happy path | Deterministic overview + specialist builders; optional LLM overlay. Offline RQ-5 / DI / RI evals green (41 llm-eval tests) |
| Empty / no run | Page disabled chat_input + guidance (`test_discuss_mode_reports_disabled_results_qa_not_missing_runs`). #478: no `set_value` on disabled widget |
| Injection | `test_results_qa_injection_cannot_dispatch_pipeline` |
| Uncited numbers | `test_explanation_rejects_uncited_numerical_claims`; RQ-5 clock/hash/decimal suite |
| Stale-state | Thesis switch clears `THESIS_SCOPED_STAGING_KEYS` (QI-10). Not re-audited |
| Time enrichment | TOML `allow_time_enrichment = false` (default-off) |
| Hash / open-exact | Button “Open exact run in Backtest”; hash prefix shown; **no** “schema-only” / “hash-fail-closed” / “integrity bar” copy (QI-09-10) |

### 3.3 Help — `handle_help_turn` / `product_help`

| Check | Result |
|---|---|
| Allowlist vs `docs/README.md` rule 2 | **Aligned.** Manifest paths = README frozen set. All seven files on disk. `AGENT_GUIDE.md` excluded. Probe `help_allowlist.aligned=true` |
| Performance question | Redirects to Discuss (`test_rq5_help_vs_results_redirect_for_performance_question`) |
| Section refusals | `test_rq5_section_allowlist_corpus_refusals`. HC-4 bank: 55 tests in `test_assistant_help_coverage.py` |
| No key | Same `LLMConfigurationError` → page `st.error` |
| Help digits | Corpus digits, not packet paths (`AUDIT_FINAL` L13 / §5.4 item 41) — not reopened |

### 3.4 Voice — PTT + sidecar (default-off)

| Check | Result |
|---|---|
| Flag | `load_voice_settings().enabled is False`. Tracked TOML `[assistant.voice] enabled = false`. `test_va6_voice_flag_remains_default_off` |
| No xAI key | `VoiceConfigurationError` “Set XAI_API_KEY to a rotated credential (env or Streamlit Secrets).” `test_va6_token_mint_fails_closed_without_key` |
| Help without OpenAI | `HELP_NO_OPENAI_REMEDIATION` — no fabricated docs |
| Injection | `test_va6_forbidden_tools_never_execute` ×9; `test_va6_ptt_injection_cannot_dispatch_pipeline`; `session.update` omits search/mcp |
| Spoken digits | `audit_spoken_text` / realtime transcript fail-closed. `require_tool_for_numbers` is **still unused** at runtime (AUDIT L9; QI-09-09) |
| Thread safety | No in-process locks. Persistence uses repository OCC. Sidecar `_active` dict is single-user localhost (VA-5). Not a multi-tenant finding |
| vulture `fp`/`newurl` | Intentional `_NoRedirectHandler.redirect_request` signature |

### 3.5 Direct `dispatch` / Study tools / execution

| Check | Result |
|---|---|
| Confirmation | `PIPELINE.run_experiment` without `confirmed` → `approval_required` (orchestrator tests) |
| `study_tools` | Tracked TOML `enabled = false`. `load_study_tools_settings().enabled is False` |
| H8 `_bounded_spec` | `grid.get("enabled", True)` (and walk_forward / validation / nested MC). Omitted `enabled` still runs the cap check (parked; QI-09-08) |
| Bundle import | Hash-fail-closed on assistant open-exact (AH §2 item 8). Zip size cap is QI-06-09 (handoff; not re-tested here) |
| Composer parity | `test_api_cli_and_assistant_canonical_hashes_match` in the 199-test scoped run — **hash identity**, not fill correctness |

### 3.6 Page 14 chat-first UX (RUX — verify only)

16 `AppTest` tests still match the page: default Discuss, one `chat_input` per mode, Advanced/Debug collapsed, channel isolation, deep-link preselect, disabled Discuss/Help guidance. **No layout change proposed.**

---

## 4. Prior-audit carry-over status

| Item | Assigned | Status on `539dd2e` | Finding |
|---|---|---|---|
| `AUDIT_FINAL` §5.5 / §7 residual **“caller-controlled audit payloads”** (L10) | QI-9 | **Still open.** `AssistantRequest.to_dict` returns unfiltered `payload`. `_record_audit` persists `request` into `tool_transcript`. Probe wrote `api_key=sk-injected-should-not-persist` into conversation JSON under `/tmp`. Default UI path does not inject keys | QI-09-06 |
| `AUDIT_FINAL` L9 `require_tool_for_numbers` dead | voice-adjacent (not in plan §A.3 list; in-scope) | **Still unused** outside `voice/settings.py`. vulture 60%. Voice default-off. Persisted-transcript grounding still holds | QI-09-09 |
| H8 battery omit=on | QI-6 filed QI-06-08; handoff assistant `_bounded_spec` | **Still parked.** `_bounded_spec` uses `.get("enabled", True)` | QI-09-08 |
| Page-12 vs assistant integrity bars | QI-06-06 handoff | Assistant shows hash prefix + “Open exact”; does **not** name the three bars | QI-09-10 |
| AIA/C2/CAI/RQ/HC/DI/RI/DX/VA/RUX | locked | Eval suites + registry audit + page-render baseline green offline. **Not reopened** | — |

Closed AH items (C1–C3, H1 partial, H3, H6) are not this slice.

---

## 5. Findings

Full records in `docs/quality/findings.csv` (`QI-09-*` only).

| ID | Axis | Class | Sev | Conf | One-line |
|---|---|---|---|---|---|
| QI-09-01 | code | Maintainability risk | High | Verified | `results_overview.py` 4,373 LOC / MI 0.00; `_format_scalar_for_claim` F 120; `compose_deterministic_replies` F 73 |
| QI-09-02 | code | Maintainability risk | Medium | Verified | Remaining F-grade: `_derive_caveats` 52, `score_corpus_chunk` 51; E-grade Discuss/Help/PTT cluster; four other MI 0.00 library modules |
| QI-09-03 | code | Maintainability risk | Medium | Verified | `pages/14_Research_Assistant.py` MI 0.00, 2,581 LOC, 13 defs, 138 session lines, 9 broad excepts |
| QI-09-04 | code | Test-quality gap | Medium | Verified | 9 routed capabilities have zero test-file mentions of the ID; registry audit is structural only |
| QI-09-05 | both | Documentation drift | Medium | Verified | `ARCHITECTURE.md` AIA-0 still says the package “does not execute research, import Streamlit”; two lazy `st.secrets` imports + `dispatch` execution exist |
| QI-09-06 | app | Security risk | Low | Verified | L10 / §5.5: caller-controlled `api_key` in `payload` is persisted unscrubbed |
| QI-09-07 | app | UX/operability gap | Low | Verified | xAI key path does not strip BOM/wrapping quotes (OpenAI does); quoted key is treated as usable |
| QI-09-08 | app | Design limitation | Medium | n/a | `_bounded_spec` still omit=`enabled` True (H8 parked; assistant locus) |
| QI-09-09 | code | Design limitation | Low | Verified | `require_tool_for_numbers` still unused at runtime (AUDIT L9) |
| QI-09-10 | app | UX/operability gap | Low | Verified | Page 14 Open-exact shows a hash prefix but does not label the three integrity bars |
| QI-09-11 | app | UX/operability gap | Medium | Verified | Draft form `min_valid_confluences` `min_value=1` cannot author AO1 `0` |

---

## 5.1 Capability × handler × test matrix (exit criterion)

Audit on `539dd2e`: 55 / 30 / 0 invalid. “ID mentions” = test `.py` files containing the exact capability string.

| Capability | Mode | Handler | Audit | ID mentions | Behavioral coverage |
|---|---|---|---|---:|---|
| `HOME.workflow_guide` | I | `_handle_home_guide` | routed | 0 | none dedicated |
| `HOME.session_data_status` | U | — | unsupported | 0 | limitation only |
| `DATA.load_ohlcv` | U | — | unsupported | 0 | — |
| `DATA.inspect_dataset` | I | `_handle_inspect_dataset` | routed | 0 | none dedicated |
| `DATA.preview_resampled_timeframes` | E | `_handle_preview_resample` | routed | 0 | none dedicated |
| `DATA.manage_saved_datasets` | X | `_handle_manage_datasets` | routed | 0 | none dedicated |
| `DATA.configure_subtimeframe` | U | — | unsupported | 0 | — |
| `DATA.download_intrabar_compatibility` | U | — | unsupported | 0 | — |
| `DATA.configure_roll_assumptions` | E | `_handle_roll_assumptions` | routed | 0 | none dedicated |
| `SETUP.configure` | U | — | unsupported | 0 | — |
| `SETUP.manage_saved_setups` | X | `_handle_manage_setups` | routed | 1 | orchestrator |
| `SETUP.inspect_active_setup` | U | — | unsupported | 0 | — |
| `LEVELS.configure_and_compute` | U | — | unsupported | 0 | — |
| `LEVELS.manage_saved_snapshots` | U | — | unsupported | 0 | — |
| `LEVELS.inspect_and_chart` | I | `_handle_inspect_levels` | routed | 1 | CAI-9 |
| `SIGNALS.generate` | U | — | unsupported | 0 | — |
| `SIGNALS.manage_saved_runs` | U | — | unsupported | 0 | — |
| `SIGNALS.inspect_and_chart` | I | `_handle_inspect_signals` | routed | 1 | CAI-9 |
| `BACKTEST.configure_and_run` | U | — | unsupported | 2 | limitation tests |
| `BACKTEST.manage_execution_defaults` | E | `_handle_backtest_defaults` | routed | 0 | none dedicated |
| `BACKTEST.inspect_results` | I | `_handle_inspect_backtest` | routed | 1 | CAI-9 |
| `BACKTEST.export_trade_review` | U | — | unsupported | 0 | — |
| `GRID.configure_and_run` | U | — | unsupported | 0 | — |
| `GRID.inspect_results` | I | `_handle_inspect_grid` | routed | 1 | CAI-9 |
| `GRID.manage_execution_defaults` | E | `_handle_grid_defaults` | routed | 0 | none dedicated |
| `TIME.analyze` | E | `_handle_time_analyze` | routed | 1 | projections |
| `VALIDATION.run_core` … `run_walk_forward` (7) | U | — | unsupported | 0 | pipeline-only |
| `VALIDATION.run_otf_matrix` | E | `_handle_otf_matrix` | routed | 0 | none dedicated |
| `VALIDATION.inspect_results` | I | `_handle_inspect_validation` | routed | 1 | CAI-9 |
| `CLASSIC.propose_page_change` | X | `_handle_propose_classic_page_change` | routed | 0 | method-tested in CAI-9 (`propose_classic_page_change`), ID unmentioned |
| `CACHE.inspect_artifacts` / `delete_artifact` / `evict_artifacts` / `rebind_source_path` | I/X | four `_handle_cache_*` | routed | 1 each | CAI-10; delete/rebind presence-only |
| `EXPORT.build_research_artifact` | X | `_handle_export_artifact` | routed | 2 | orchestrator + parity |
| `EXPORT.download_tables` / `inspect_uploaded_artifact` | U | — | unsupported | 0 | — |
| `BUNDLE.export` | U | — | unsupported | 0 | — |
| `BUNDLE.import` | X | `_handle_bundle_import` | routed | 6 | strongest (evidence path) |
| `BUNDLE.register_external_run` | X | `_handle_register_external_run` | routed | 1 | classic record |
| `PORTFOLIO.import_trades` / `inspect_results` | U | — | unsupported | 0 | — |
| `PORTFOLIO.analyze` | E | `_handle_portfolio_analyze` | routed | 2 | orchestrator + parity |
| `PIPELINE.validate_run_spec` | E | `_handle_validate_run_spec` | routed | 3 | contracts + orchestrator |
| `PIPELINE.run_experiment` | E | `_handle_run_experiment` | routed | 10 | strongest (confirm gate + evals + voice) |
| `STUDY.expand` / `run` / `report` / `promote` | E | four `_handle_study_*` | routed | 1–4 | `tests/study/test_study_tools.py` |

**Structural triple is complete. Behavioral triple is not** for the nine routed IDs with zero ID mentions (plus cache delete/rebind dispatch). `get_handler` / `tool_limits_from_envelope` have no direct tests (QI-11-01).

---

## 5.2 Secret-handling negative-probe table (exit criterion)

Isolation: `unset OPENAI_API_KEY XAI_API_KEY`; stub strings `sk-qi09-stub-not-a-real-key-XXXX` / `xai-qi09-stub-not-a-real-key-YYYY` only. Command: `PYTHONPATH=/workspace python3 /tmp/qi09_probes.py`.

| Probe | Expected | Observed | Verdict |
|---|---|---|---|
| Missing OpenAI env + no secrets | Typed `LLMConfigurationError` | “Set OPENAI_API_KEY to a rotated credential.” | Pass |
| Missing xAI env + no secrets | Typed `VoiceConfigurationError` | “Set XAI_API_KEY to a rotated credential (env or Streamlit Secrets).” | Pass |
| OpenAI placeholder `REPLACE_WITH_ROTATED_OPENAI_API_KEY` | Reject | `None` | Pass |
| xAI placeholders / `replace_with*` prefix | Reject | `None` | Pass |
| OpenAI BOM + wrapping `'…'`/`"…"` | Strip → usable | stripped | Pass |
| xAI BOM | Strip or reject | **BOM kept** (`bom_stripped=false`) | QI-09-07 |
| xAI wrapping `"…"` | Strip or reject | **quotes kept**; nested secrets returned `"xai-qi09-stub-…"` | QI-09-07 |
| Tracked `config/assistant.toml` key assignment | Absent | no `api_key` / `OPENAI_API_KEY` / `XAI_API_KEY` assignment | Pass |
| `study_tools` / `voice` tracked flags | Default-off | both `enabled is False` via loaders | Pass |
| OpenAI sanitizer: exact key + `sk-*` + `Bearer` | Redacted | `***` / `sk-***` / `Bearer ***`; full key absent | Pass |
| xAI unary HTTP error | No key echo | Generic `VoiceProviderError("xAI JSON request failed.")` — no body echo | Pass (different strategy) |
| Sidecar log redact | Secret keys redacted | `redact_for_logs` + `_FORBIDDEN_LOG_KEYS` (existing tests) | Pass |
| Page sidecar JSON guard | Reject secret field names | static: refuses `api_key`/`token`/`client_secret`/`authorization` | Pass |
| Caller `payload.api_key` via `_record_audit` | Scrubbed or rejected | **Persisted** in `tool_transcript` + conversation JSON | QI-09-06 |
| Env → flat secrets → nested `[openai].api_key` / `[xai].api_key` | Documented order | Code matches. Nested OpenAI quoted key unwraps; nested xAI does not | OpenAI pass / xAI QI-09-07 |

---

## 6. Positive verification

What was checked and is fine — do not re-audit:

1. **Registry ↔ handler triple is mechanically consistent:** 55 / 30 / 0 invalid. Import-time `_assert_handler_coverage`. Registry audit tests green.
2. **Help corpus allowlist matches `docs/README.md` rule 2** (seven frozen paths + digest; `AGENT_GUIDE.md` excluded). All files on disk.
3. **Eval suites are offline and green** on this tree: 41 LLM + 26 voice collected tests; scoped 199 passed with keys unset. Prompt-injection and uncited-number cases exist for draft/results/help/voice.
4. **Fail-closed without a key** on both providers (typed errors; page `st.error`; no traceback in the handler path).
5. **Tracked TOML never stores keys.** `study_tools` and `voice` default-off. Discuss/help `enabled=true` still require a runtime key.
6. **OpenAI secret hygiene holds:** BOM/quote unwrap, placeholder reject, `_sanitize_provider_error_text` redacts exact key / `sk-*` / Bearer.
7. **Presentation-only for widgets holds:** no `st.chat_input` / `st.button` / session writes inside `thesistester/assistant/`. The only `st.*` is `st.secrets` (QI-09-05 names the AIA-0 sentence, not a widget leak).
8. **RUX rendered-structure baseline still matches** (16 page-render tests). Channel isolation and one chat_input per mode hold. Layout not reopened.
9. **Provider modules are isolated** except the documented PTT bridge. Sidecar is localhost-only; `fp`/`newurl` are a stdlib override, not dead code. urlopen targets hardcoded HTTPS (QI-12-06 owns the CI scanner gap).
10. **vulture 100% on sidecar** is the redirect-handler signature (plus `headers`/`msg` on this radon/vulture pair). Not a defect.

---

## 7. Handoffs to other slices

| To | Observation (not a finding here) |
|---|---|
| QI-6 | H8 parked default remains in `_bounded_spec` (QI-09-08). Zip size cap on assistant `BUNDLE.import` is QI-06-09. Three integrity bars: page 12 vs assistant labels (QI-06-06 / QI-09-10) |
| QI-7 | `STUDY.*` handlers exist; tools stay default-off. `load_study_tools_settings` lives in `thesistester/study/tools.py` (QI-7-owned) |
| QI-10 | Page 14’s 138 session-state lines and `THESIS_SCOPED_STAGING_KEYS` already in QI-10 graph. 9 page-level `except Exception` classified here |
| QI-11 | handlers 46% / sidecar 48% / xai 63% / grounding 66% already QI-11-01. QI-09-04 is the capability-ID behavioral gap. AppTest proto/`set_value` sensitivity is QI-11-03 |
| QI-12 | B310 urlopen ×4 and lazy Streamlit imports already in QI-12-06 / QI-12-07. No new CVE work |
| QI-13 | AIA-0 “Streamlit-free / does not execute” sentence is stale (QI-09-05). Help rule 2 matches code — do not move allowlisted paths. `VOICE_SIDECAR_OPS.md` omits ephemeral-vs-full-key sidecar detail |
| QI-3 | AO1 `min_valid=0` cannot be authored on the Draft form (QI-09-11). Do not reopen AO math |

---

## 8. Docs that would need amending in QR

List only. **Not amended** in this slice.

| Doc | Why it might change in QR |
|---|---|
| `docs/ARCHITECTURE.md` | AIA-0 “does not execute / import Streamlit” sentence (QI-09-05); session-key / presentation-only paragraph if secrets helper is extracted |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | L10 audit-payload residual; L9 `require_tool_for_numbers`; H8 omit=on on assistant `_bounded_spec` if disclosure is added |
| `docs/USER_GUIDE.md` | Open-exact vs page-12 schema-only labels (QI-09-10); AO1 `min_valid=0` cannot be set on the Draft form (QI-09-11); fail-closed-without-key copy if QR changes wording |
| `docs/AGENT_GUIDE.md` | Secret-resolution asymmetry (OpenAI vs xAI); audit-payload scrub rule; capability test-completeness expectation |
| `docs/VOICE_SIDECAR_OPS.md` | Sidecar uses full server-side Bearer key, not `mint_ephemeral_token` |
| `docs/METRICS_GLOSSARY.md` | Only if Discuss claim labels change during a QR extract of `_format_scalar_for_claim` (not expected) |

---

## 9. Research-only sentence

No tracked file outside `docs/quality/` changed; `pytest -q` unchanged (3966 passed, 5 skipped). Probe scripts stay under `/tmp`.

---

## 10. Probe script (pasted; not committed)

Full script: `/tmp/qi09_probes.py`. It (1) AST-walks `thesistester/assistant` for Streamlit imports / `st.*`, (2) diffs `HELP_CORPUS_MANIFEST` vs `docs/README.md` rule 2, (3) audits registry × `HANDLER_REGISTRY` × test-file ID mentions, (4) runs secret negatives on `_usable_openai_api_key` / `_usable_xai_api_key` / sanitizer / missing-key, (5) persists a malicious `payload.api_key` through `_record_audit` into a throwaway `LocalThesisRepository`, (6) probes `_bounded_spec` H8 omit, (7) AST-maps `results_overview.py`, (8) loads default-off flags.

```python
# excerpt — audit-payload + xAI quote/BOM (see /tmp/qi09_probes.py)
req = AssistantRequest(
    capability_id="HOME.workflow_guide",
    payload={"action": "inspect", "api_key": "sk-injected-should-not-persist"},
)
orch._record_audit(result, request=req, thesis_id=thesis.thesis_id,
                   conversation_id=conv.conversation_id)
# → secret_in_transcript True; secret on disk under /tmp/qi09-audit-*/theses/.../conversations/*.json

assert _usable_openai_api_key('"sk-qi09-stub-not-a-real-key-XXXX"') == FAKE_OPENAI
assert _usable_xai_api_key('"xai-qi09-stub-not-a-real-key-YYYY"') != FAKE_XAI  # quotes kept
```
