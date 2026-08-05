# AI Research Assistant Engineering Roadmap

## Status and purpose

**Status:** historical foundations contract (AIA-series). Runtime assistant
integration landed via `docs/AI_CHAT_2_ENGINEERING_ROADMAP.md` (C2,
implemented). **Do not use this document as the active implementation plan for
multi-turn results discussion or product help** — that work is owned exclusively
by `docs/RESULTS_AND_PRODUCT_QA_IMPLEMENTATION.md` (RQ-series). Voice review is
owned by `docs/REALTIME_VOICE_AGENT_IMPLEMENTATION.md` (VA-series, voice-only
after RQ-1).
**Owner model:** one trusted local user, local datasets, and local execution.

**Related integration plan:** `docs/CLASSIC_ASSISTANT_INTEGRATION_PLAN.md`
defines the regression-safe roadmap for joining the classic Streamlit workflow
and this thesis/run model through immutable artifacts and bundle provenance.
`CAI-0` baseline timings and the manual record-after-run policy decision are
recorded in `docs/CAI_BASELINE.md`. `CAI-1` shared identity/normalization lives
in `thesistester/research_identity.py`. `CAI-2`/`CAI-3` execution artifacts and
cached headless reuse live in
`thesistester/persistence/execution_artifacts.py` with explicit
`cache_policy` on `run_experiment` / `compute_levels` (Assistant/CLI use
`read_write`; public default remains `off`). `CAI-4` classic→RunSpec export
lives in `thesistester/classic_export.py`.

This document records the original AIA product/architecture intent for an AI
Research Assistant in ThesisTester. Keep it for invariants and terminology; do
not open new PRs from open-looking AIA milestone text when a newer contract
owns that surface.

The assistant lets the user describe, create, revise, run, compare, and discuss
many independent setup theses. It must convert natural-language ideas into
explicit, reproducible research specifications; invoke the existing deterministic
research pipeline; and explain recorded results and limitations. It is not a
strategy factory, live-trading system, broker integration, or source of
unqualified trading recommendations.

This plan deliberately extends the project's hypothesis-driven position:
**trader thesis in; deterministic research evidence out**. It does not permit
the LLM to silently invent strategy rules, alter engine semantics, or select
parameters on a final sample and present them as unbiased.

## Product contract

### User-visible capabilities

The assistant must support an arbitrary number of distinct theses. A thesis is
not a single conversation: it is an independently versioned research object
that may have many conversations, specifications, runs, and comparisons.

The initial end-to-end product loop is:

1. The user describes a setup in normal language.
2. The assistant produces a draft research plan and identifies unresolved terms.
3. The user confirms or edits a normalized, executable specification.
4. The assistant runs a reproducible experiment through the existing headless
   facade.
5. The assistant explains results, validation evidence, limitations, and the
   next discriminating experiment.
6. The user can fork, revise, re-run, compare, archive, or resume any thesis.

Initial thesis commands must include:

- create, list, select, rename, clone, archive, and restore a thesis;
- show the current and prior specification versions;
- run a baseline, grid, validation battery, or walk-forward experiment;
- compare selected completed runs;
- explain an existing run, bundle, or individual diagnostic;
- save an accepted specification as a reusable setup.

### Non-goals and hard boundaries

- No live order placement, broker connectivity, or execution automation.
- No arbitrary Python, shell, SQL, or unrestricted filesystem tool for the
  model.
- No silent configuration changes, implicit parameter optimization, or
  autonomous bulk generation of trading theories.
- No claim that historical results prove an edge, forecast trade outcomes, or
  establish "best" SL/TP values without stating the selection and validation
  method.
- No change to existing engine, signal, level, or analytics semantics merely to
  support chat.
- No replacement of current Streamlit workflows; the assistant is an additive
  consumer of their shared headless pipeline.

The single-user model removes multi-tenant authentication and account-management
requirements. It does not relax data-root containment, explicit tool schemas,
resource limits, provenance, or confirmation requirements.

## Architecture and ownership

```text
Streamlit Assistant Page
  └── Conversation orchestrator
       ├── Thesis compiler and clarification policy
       ├── Confirmation policy
       ├── Typed tool router
       ├── Grounded result explainer
       └── Thesis/provenance repository
             └── thesistester.api and research bundles
                  └── Existing levels, signals, engine, analytics
```

### Required layering

| Layer | Responsibility | Must not do |
|---|---|---|
| `thesistester/assistant/contracts.py` | Versioned typed schemas for thesis, specification, tool request/result, provenance, and explanation evidence | Import Streamlit or call the engine |
| `thesistester/assistant/repository.py` | Local schema-versioned persistence and atomic reads/writes | Contain model prompts or backtest logic |
| `thesistester/assistant/tools.py` | Narrow JSON-safe wrappers around supported public headless operations | Expose arbitrary code/path execution |
| `thesistester/assistant/thesis_compiler.py` | Compile prose to a draft spec; identify ambiguity | Execute an unconfirmed run |
| `thesistester/assistant/explainer.py` | Build evidence packets and render grounded narratives | Calculate replacement statistics or hide caveats |
| `thesistester/assistant/orchestrator.py` | Conversation state machine, tool sequencing, confirmation | Implement research semantics |
| `pages/14_Research_Assistant.py` | Display and interaction only | Duplicate pipeline, persistence, or analysis logic |

The assistant calls the existing public composition path:

```text
load_dataset → compute_levels → build_setup → generate_signals
             → run_backtest → run_grid → run_validation / run_walk_forward
             → research bundle
```

`thesistester.api` remains the orchestration boundary. The assistant must not
call internal simulation helpers directly and must not replicate page logic.

### Headless feature-parity registry

Before implementation, create a versioned registry that names every visible
ThesisTester capability and records:

- UI producer/consumer and public headless symbol;
- supported assistant action: execute, inspect, explain, import/export, or
  unsupported;
- input schema, output evidence schema, known limitations, and safety class;
- required confirmation level and resource envelope;
- tests proving UI/API parity where applicable.

No roadmap milestone may state that the assistant "controls all features" until
the registry marks every existing feature as supported or explicitly documents a
user-visible exception. Unsupported actions must be reported honestly in chat;
they must never be approximated by model-created behavior.

## Deterministic research and conversation model

### Core objects

All persisted assistant objects are additive and schema-versioned:

| Object | Required fields |
|---|---|
| Thesis | `schema_version`, immutable ID, name, status, created/updated timestamps, tags |
| Spec version | Thesis ID, version, parent version, normalized run spec, unresolved assumptions, user confirmation, compiler version |
| Research run | Spec version, bundle path, canonical bundle hash, dataset fingerprint, result status, tool version, warnings |
| Conversation | Thesis ID, message sequence, selected spec/run IDs, model-independent tool transcript |
| Comparison | Input run IDs/hashes, generated evidence packet, conclusion text, recorded caveats |

Store these under a new namespace:

```text
.thesistester_store/assistant/
  schema_version.json
  theses/<thesis_id>/meta.json
  theses/<thesis_id>/specs/<version>.json
  theses/<thesis_id>/runs/<run_id>.json
  theses/<thesis_id>/conversations/<conversation_id>.json
```

Use atomic writes. Unknown future schema versions fail closed for mutation and
fall back to read-only display where possible. Existing local-store namespaces,
saved setups, research bundles, and session-state keys remain unchanged.

### Thesis state machine

```text
draft → needs_clarification → ready_for_confirmation → confirmed
      → running → completed | failed | cancelled
completed → revised | compared | archived
```

- A run is allowed only from a confirmed immutable specification version.
- Revising a thesis creates a new draft specification; it never mutates the
  specification behind an existing bundle hash.
- A failed or cancelled run retains its request, error class, and no misleading
  partial performance conclusion.
- Conversation context may select a thesis and a spec version, but it must not
  infer an unrecorded parameter change.

### Natural-language compiler policy

The compiler maps language to a `RunSpec` draft plus a structured ambiguity list.
It may suggest defaults only when marked as an assumption and presented for
confirmation.

For a prompt such as “uptrend retraces to dVWAP with 30m 50-SMA confluence in
NY B session,” the compiler must resolve or ask about:

| Phrase | Required executable definition |
|---|---|
| “uptrend” | Chosen measurable condition: SMA slope, price relation, confirmed pivots, OTF state, or another supported filter |
| “retrace” | Trigger (`touch`, `reject`, `reclaim`, or supported alternative), tolerance, and entry rule |
| “dVWAP” | `dVWAP_RTH`, its RTH-only availability, and whether non-RTH bars are excluded |
| “50 SMA on 30m” | Supported level column and confluence tolerance in ticks |
| “B session of NY” | Exact exchange-time interval and session template |
| “likely to work” | Predeclared metrics, minimum trade count, and OOS/robustness requirements |
| “best SL and targets” | Candidate grid, ranking rule, minimum trades, and untouched OOS selection policy |

The compiler must reject or clarify requests that cannot be represented by the
registered public capability set. It must never convert vague prose into an
unshown executable rule.

## Tool contract

### Initial allowed tools

All tool input and output must use typed JSON-safe schemas. DataFrames are
converted to bounded summary/table payloads; full data remains in research
bundles and existing views.

| Tool | Purpose | Confirmation |
|---|---|---|
| `list_theses`, `get_thesis`, `list_runs` | Browse persisted assistant research | No |
| `list_datasets`, `describe_dataset` | Inspect allowed local datasets and metadata | No |
| `get_feature_registry`, `get_available_levels` | Explain current supported capabilities | No |
| `compile_thesis` | Create a draft spec and ambiguity list | No |
| `validate_run_spec` | Validate a draft against the public facade | No |
| `save_spec_version`, `clone_thesis` | Persist explicit user-requested research state | Explicit user request |
| `run_experiment` | Run confirmed deterministic research | Explicit confirmation |
| `load_run_summary`, `load_bundle_summary` | Read structured result evidence | No |
| `compare_runs` | Compare explicit completed run IDs/hashes | Explicit selected inputs |
| `explain_results` | Explain a provided evidence packet | No |

### Tool execution constraints

- Dataset paths must resolve under configured, canonical local data roots.
- Tool schemas allow only documented API keys; unknown keys fail closed.
- Every stochastic operation receives and records an explicit `random_state`.
- Run names are generated safely and cannot control arbitrary output paths.
- Grid cell count, simulation count, WFA fold count, and result-table size are
  capped by documented resource limits.
- The tool router records start/end times, request ID, spec version, bundle
  hash, warning set, and error class.
- A result is never summarized as successful until a completed bundle exists
  and its canonical hash is recorded.
- A model may select only from listed dataset IDs and registry-declared
  features; it may not fabricate a file path or unsupported level/indicator.

### Tool output evidence packet

`explain_results` receives an immutable, structured evidence packet containing
only the output relevant to the question:

- provenance: thesis/spec/run IDs, dataset fingerprint, bundle hash, date range;
- exact setup, costs, exposure, intrabar, session, and random-seed assumptions;
- trade and directional summaries;
- grid cells, ranking rule, and minimum-trade result;
- time/session breakdowns and selected trade diagnostics;
- validation, excursion, Monte Carlo, noise, sensitivity, overfitting, and
  walk-forward outputs when run;
- warning and limitation codes.

Narrative text cannot cite a statistic absent from this packet. The assistant
must distinguish observed results from robustness evidence and unresolved
uncertainty.

## Milestone plan

Each milestone is independently mergeable, additive, tested, documented, and
reviewable. Milestone completion does not authorize adjacent cleanup.

### AIA-0 — Capability audit and contracts

**Goal:** establish the stable assistant surface before any model or UI work.

**Scope**
- Add the feature-parity registry.
- Add JSON-safe Pydantic/dataclass contracts; use the repository's existing
  dependency/style choice unless a new dependency is justified separately.
- Define capability, confirmation, error, warning, and resource-limit enums.
- Document the assistant terminology, state machine, and non-goals.

**Regression controls**
- No Streamlit, engine, analytics, or persistence behavior changes.
- Contract snapshots validate backwards-compatible JSON serialization.
- Tests reject undeclared feature IDs and unknown fields.

**Acceptance**
- Every current user-visible feature has one registry row.
- A spec with unknown keys or unknown capabilities fails with an actionable
  error.
- `docs/ARCHITECTURE.md` documents the new library boundary without changing
  existing session-state contracts.

### AIA-1 — Local thesis and provenance repository

**Goal:** save many independently versioned setup theses and immutable research
history.

**Scope**
- Add the assistant persistence namespace and repository API.
- Implement thesis/spec/run/conversation persistence and state transitions.
- Add migration/read-only handling for unknown schema versions.

**Regression controls**
- New namespace only; do not change existing `local_store` artifact schemas.
- Atomic-write and corrupt-file tests.
- Run metadata references bundle hashes but does not rewrite bundles.

**Acceptance**
- Creating, cloning, revising, archiving, restoring, and listing multiple
  theses round-trips deterministically.
- A historical run keeps its original specification after later revisions.
- Existing store tests and saved setup behavior remain unchanged.

### AIA-2 — Deterministic headless tool adapters

**Goal:** expose the existing research pipeline through constrained assistant
tools.

**Scope**
- Implement data discovery, spec validation, experiment execution, bundle
  summary, and run-comparison tools.
- Serialize bounded API summaries without exposing raw DataFrames to a model.
- Apply data-root checks, resource caps, seeds, and structured errors.

**Regression controls**
- Tools call public `thesistester.api`/bundle APIs only.
- Direct API and tool execution must produce equal logical summaries and equal
  canonical bundle hashes for a fixed fixture/spec.
- Tests cover path traversal, unknown config, excessive resource request, empty
  data, and failed run handling.

**Acceptance**
- A valid confirmed spec runs end-to-end through the adapter.
- A tool result records the exact bundle hash and data fingerprint.
- No tool accepts arbitrary source code, command, or filesystem path.

### AIA-3 — Thesis compiler and confirmation workflow

**Goal:** turn conversational setup ideas into explicit research plans.

**Scope**
- Implement normalized thesis extraction and ambiguity reporting.
- Render a reviewable research-plan card: rules, data scope, assumptions,
  costs, intrabar model, exposure policy, grid, validation, and success criteria.
- Require explicit confirmation before a compute tool call.

**Regression controls**
- Compiler output is a draft only; it cannot call execution tools.
- Fixture tests cover vague, unsupported, contradictory, and complete prompts.
- Identical structured compiler inputs yield identical normalized specs.

**Acceptance**
- Ambiguous terms produce questions or marked assumptions.
- The user can edit every generated rule before confirmation.
- Confirmed input is exactly the immutable spec passed to `run_experiment`.

### AIA-4 — Evidence-grounded explanation

**Goal:** hold a useful conversation about completed research without
overstating results.

**Scope**
- Build evidence packet construction and result explanation templates.
- Add explanations for baseline backtests, trade/time analysis, grid cells,
  costs, exposure, and intrabar assumptions.
- Link conclusions to run IDs/hashes and show material caveats.

**Regression controls**
- Explainer consumes result data only; it neither recomputes trades nor changes
  metrics.
- Fixture tests enforce warning inclusion for low sample size, zero costs,
  overlap-enabled exposure, and intrabar ambiguity.
- Unsupported questions return a bounded response and an available next action.

**Acceptance**
- Every numerical claim in a rendered explanation is traceable to a packet
  field.
- “Best” parameter wording identifies the sample, ranking metric, candidate
  set, and validation status.
- The assistant states that results are research diagnostics, not proof or
  trading advice.

### AIA-5 — Streamlit assistant page

**Goal:** expose the completed single-thesis loop in the product.

**Scope**
- Add `pages/14_Research_Assistant.py`.
- Provide thesis list/selector, transcript, research-plan review, confirmation,
  run progress, result summary, provenance details, and links to existing
  analysis pages.
- Additive session-state keys only, namespaced under `assistant_*`.

**Regression controls**
- The page is a thin consumer of `assistant/orchestrator.py`.
- Existing pages retain their current producers, consumers, and keys.
- Document every new state key in `docs/ARCHITECTURE.md`.

**Acceptance**
- Manual workflow: create thesis → clarify → confirm → run → explain → revise
  → compare two runs.
- Reloading the app restores persisted thesis/run records without changing
  historical results.

### AIA-6 — Advanced research tools

**Goal:** progressively expose the rest of the registered existing research
surface.

**Implementation order**
1. Grid, time/session analysis, costs, exposure, intrabar, and exit management.
2. Excursions, validation, Monte Carlo, noise, sensitivity, and overfitting.
3. Walk-forward and WFA matrix.
4. Portfolio and multi-run analysis.
5. Saved defaults, setup library integration, research import/export, and
   visualization handoff.

Each group requires its own parity-registry update, tool schema, evidence
packet shape, explanation rules, limits, docs, and tests. Portfolio support is
explicitly deferred until multi-run identity/provenance is complete.

## Statistical honesty policy

The assistant must apply these rules in user-facing results:

1. Historical performance is an observed sample, not an outcome forecast.
2. SL/TP grids are parameter searches. A selected cell is in-sample until
   tested through the stated OOS/walk-forward protocol.
3. Low sample size, selection breadth, unstable parameter neighborhoods, costs,
   exposure assumptions, and intrabar ambiguity are first-class findings.
4. The assistant retains all attempted runs and reports comparison selection
   criteria; it does not cherry-pick only favorable outcomes.
5. It does not label a setup “validated” unless the configured validation
   criteria have been met and their limitations are shown.
6. It never implies tick-level ordering from OHLC data. The selected intrabar
   model and any lower-timeframe fallback are part of the result.
7. It must state when a requested conclusion needs unavailable data or an
   unsupported feature.

## Regression-safety and documentation gates

Every assistant PR must state its surface area, deterministic behavior,
provenance impact, and regression evidence. The required baseline is:

- `ruff check .`
- `ruff format --check .`
- `pytest -q`

Additional requirements by touched surface:

| Touched surface | Required gate |
|---|---|
| Assistant contracts/repository/tools | Unit and serialization tests; invalid-input tests; deterministic fixture test |
| API/CLI/bundle integration | Direct API-versus-tool parity and canonical bundle-hash equality |
| Streamlit page | Session-state contract test; manual workflow evidence |
| New persistence | Schema-version, round-trip, corrupt/unknown-version, and atomic-write tests |
| Level/signal/engine change | Existing golden-master equality plus required future-shock tests before implementation |
| Analytics change | Deterministic tests, glossary/caveat updates, and preserved existing result schemas |

No assistant milestone may modify `simulate_trades`, level computation, signal
generation, or existing persistence schemas without satisfying the repository's
golden-master, point-in-time, additive-default, and same-PR documentation
requirements.

## Documentation updates required per milestone

Update the applicable documents in the same PR:

- `docs/ARCHITECTURE.md`: public assistant boundary and additive session-state
  contract;
- `docs/AGENT_GUIDE.md`: supported headless assistant tool schemas and safe
  operation;
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`: material new execution/statistical
  caveats;
- `docs/METRICS_GLOSSARY.md`: any newly exposed or assistant-defined metric;
- `docs/ENGINEERING_ROADMAP.md`: milestone implementation record;
- this roadmap: status, accepted deviation, and final compatibility decision.

## Completion definition

The assistant is ready to be described as a research assistant when a user can
create multiple separate theses, produce explicit confirmed specifications, run
reproducible research through the shared headless pipeline, inspect saved
provenance, compare selected runs, and converse about evidence-backed results
and limitations.

It is ready to be described as controlling all ThesisTester features only when
the feature-parity registry is complete, every declared feature has a typed
tool and evidence/explanation contract, and its documented exceptions are
empty.
