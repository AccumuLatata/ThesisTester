# ThesisTester documentation

Lean index. Prefer **Primary** docs for day-to-day truth. Completed milestone
plans stay as frozen contracts (amend, do not casually reopen). Historical
build logs and evidence live under [`archive/`](archive/README.md). Point-in-time
research snapshots live under [`research/`](research/README.md).

## Primary (living)

| Doc | Role |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | Feature / how-to (Research Assistant **Help** corpus) |
| [AGENT_GUIDE.md](AGENT_GUIDE.md) | Contributor / agent runbook (not in Help) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Boundaries, `session_state`, page contracts |
| [ASSUMPTIONS_AND_LIMITATIONS.md](ASSUMPTIONS_AND_LIMITATIONS.md) | Honesty surface for research claims |
| [METRICS_GLOSSARY.md](METRICS_GLOSSARY.md) | KPI / metric definitions |
| [POINT_IN_TIME_GUARANTEES.md](POINT_IN_TIME_GUARANTEES.md) | PIT audit surface |
| [ENGINEERING_ROADMAP.md](ENGINEERING_ROADMAP.md) | Milestone + assistant-contract status index |
| [otf-filter.md](otf-filter.md) | OTF v1 behavioral contract |
| [research-methodology.md](research-methodology.md) | OTF OOS evaluation protocol |
| [ANCHOR_CONFLUENCE.md](ANCHOR_CONFLUENCE.md) | Anchor-confluence workflow guide |
| [VOICE_SIDECAR_OPS.md](VOICE_SIDECAR_OPS.md) | Localhost realtime voice sidecar ops |
| [SIMULATE_PERF.md](SIMULATE_PERF.md) · [CAI_BASELINE.md](CAI_BASELINE.md) | Informational performance baselines |

## Normative contracts (complete — amend carefully)

Regression framework: [ENGINEERING_PROPOSAL.md](ENGINEERING_PROPOSAL.md) §4  
(§1–§3 are a **historical** pre-R9 gap snapshot; status SoT is the roadmap.)

Assistant / product contracts (index + status in `ENGINEERING_ROADMAP.md`):

- [RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md](RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md) (RQ)
- [HELP_CORPUS_COVERAGE_IMPLEMENTATION.md](HELP_CORPUS_COVERAGE_IMPLEMENTATION.md) (HC)
- [DISCUSS_INTELLIGENCE_IMPLEMENTATION.md](DISCUSS_INTELLIGENCE_IMPLEMENTATION.md) (DI)
- [RESEARCH_INTELLIGENCE_IMPLEMENTATION.md](RESEARCH_INTELLIGENCE_IMPLEMENTATION.md) (RI)
- [DUPLEX_INTELLIGENCE_IMPLEMENTATION.md](DUPLEX_INTELLIGENCE_IMPLEMENTATION.md) (DX)
- [REALTIME_VOICE_AGENT_IMPLEMENTATION.md](REALTIME_VOICE_AGENT_IMPLEMENTATION.md) (VA)
- [RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md](RESEARCH_ASSISTANT_UX_REFOCUS_PLAN.md) (RUX)
- [CLASSIC_ASSISTANT_INTEGRATION_PLAN.md](CLASSIC_ASSISTANT_INTEGRATION_PLAN.md) (CAI)
- [AI_CHAT_2_ENGINEERING_ROADMAP.md](AI_CHAT_2_ENGINEERING_ROADMAP.md) (C2)
- [AI_RESEARCH_ASSISTANT_ROADMAP.md](AI_RESEARCH_ASSISTANT_ROADMAP.md) (AIA)

Engine / data contracts:

- [SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md](SESSION_ENTRY_WINDOW_IMPLEMENTATION_PLAN.md) (SW C1–C9)
- [15s_primary_derived_1m_implementation_plan.md](15s_primary_derived_1m_implementation_plan.md)
- [PREV30M_VWAP_IMPLEMENTATION_PLAN.md](PREV30M_VWAP_IMPLEMENTATION_PLAN.md)
- [STUDY_RUNNER_IMPLEMENTATION_PLAN.md](STUDY_RUNNER_IMPLEMENTATION_PLAN.md) (RS — MVP RS1–RS5 ✅; §12 through RS-D9 ✅; parked D1/D3/D6)
- [STUDY_RUNNER.md](STUDY_RUNNER.md) (RS operator contract; RS1–RS5 + post-MVP through RS-D9)
- [STUDY_RUNNER_GROK_ROUTINE_PACK.md](STUDY_RUNNER_GROK_ROUTINE_PACK.md) (RS-D5 external Grok coworker routines; copy-ready prompts under `examples/studies/agents/`)
- [STUDY_BUILDER_IMPLEMENTATION_PLAN.md](STUDY_BUILDER_IMPLEMENTATION_PLAN.md) (SB — Study Builder UX; SB1–SB3 complete; does not change RS execute/preview/launch)
- [STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md](STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md) (SIA — Studies authoring aligns to 15s-primary `run_experiment`; SIA0–SIA3 ✅; does not change engine/Data/execute)
- [STUDY_VIEWER_IMPLEMENTATION_PLAN.md](STUDY_VIEWER_IMPLEMENTATION_PLAN.md) (SV — Studies Inspect catalog / quality / charts / cell peek / briefing; SV0–SV5 ✅; does not reopen RS-D2 execute/session boundaries)
- [AUDIT_HONESTY_IMPLEMENTATION_PLAN.md](AUDIT_HONESTY_IMPLEMENTATION_PLAN.md) (AH — research-honesty remediations from the 2026-08-18 audit merge; AH0–AH5 landed; AH6 specified, not implemented)

## Research (demoted snapshots)

- [SOTA backtesting landscape](research/SOTA_BACKTESTING_LANDSCAPE.md)
- [ThesisTester repository analysis (2026-07-29)](research/THESISTESTER_ANALYSIS.md)

## Archive (completed plans / evidence)

See [archive/README.md](archive/README.md). Do not use archive docs as living
status trackers.

## Maintenance rules

1. **One living home per topic.** Status → `ENGINEERING_ROADMAP.md`. Behavior →
   contract or USER_GUIDE / ARCHITECTURE / ASSUMPTIONS.
2. **Help corpus paths are frozen.** Moving Help-allowlisted files
   (`USER_GUIDE`, `ARCHITECTURE`, `ASSUMPTIONS`, `METRICS_GLOSSARY`,
   `otf-filter`, `research-methodology`, root `README`) requires a matching
   HC/RQ allowlist PR.
3. **Completed series stay frozen.** Amend contracts; do not reopen AIA/C2/CAI/RQ/…
   text for unrelated work.
4. **New historical logs go to `archive/`.** New external research → `research/`.
