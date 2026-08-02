# AI Chat 2.0 Engineering Roadmap

## Purpose

This is the implementation contract for evolving ThesisTester from assistant
foundations into a reproducible, single-user conversational research product.
The assistant translates a trader's thesis into an explicit experiment,
requires confirmation, runs the existing deterministic pipeline, records
provenance, and explains only evidence-backed outcomes.

The LLM is a language interface, never a backtest engine, trading system, or
source of uncited performance claims.

## Definition of done

The product is complete only when a user can create multiple theses, convert a
conversation into a validated immutable run specification, confirm it, execute
it through `thesistester.api`, reload its bundle-backed provenance, compare
selected runs, and receive explanations whose numerical claims come only from
an evidence packet.

## Non-negotiable invariants

1. Existing engine, signal, level, and analytics semantics remain unchanged.
2. Every compute action uses `AssistantRequest` → registry validation → bounded
   tool adapter → public headless API.
3. A run starts only from a confirmed immutable spec version.
4. Every completed run records dataset fingerprint, spec version, bundle path,
   canonical bundle hash, tool version, seed/configuration, and warnings.
5. All attempted runs remain visible; no result picker may hide unfavorable
   trials.
6. The assistant must distinguish observed sample results, robustness evidence,
   and unresolved uncertainty.
7. New behavior is additive, schema-versioned, deterministic, and documented
   in the same PR.
8. No LLM receives arbitrary filesystem, shell, SQL, engine, or broker access.

## Current integration gap

The implemented AIA foundations provide contracts, registry, repository, bounded
tools, drafting, evidence helpers, and a thesis workspace. They do not yet form
an end-to-end loop: compiler choices are not executable specs; tools do not
write bundle provenance; the page cannot run/explain/compare; and no
orchestrator or provider layer exists.

The sequence below closes those integration gaps before adding an LLM.

## C2-1 — Orchestrator and registry-gated tool router

**Goal:** introduce `thesistester/assistant/orchestrator.py` as the only
coordinator between UI, repository, compiler, tools, and explainer.

**Scope**
- Implement a typed router from `AssistantRequest` capability IDs to explicit
  handlers.
- Call `validate_capability_request()` before every handler.
- Enforce registry confirmation levels; return an approval-required result
  rather than executing compute immediately.
- Create/append model-independent conversation tool-transcript records.
- Return structured error objects with category, retryability, and remediation.

**Out of scope:** LLM provider calls, Streamlit rendering, engine changes.

**Acceptance**
- Unknown, unsupported, and unconfirmed capability requests fail closed.
- Every successful/failed tool call produces one transcript entry.
- Unit tests cover confirmation bypass, unsupported capability, and idempotent
  read-only operations.

**Implemented contract (typed router)**
- `HANDLER_REGISTRY` maps every non-unsupported registry capability to a typed
  handler. Capabilities without a handler are marked `unsupported` with an
  explicit limitation.
- `dispatch()` records exactly one tool-transcript audit entry for
  `approval_required`, `completed`, `failed`, `unavailable`, and `cancelled`
  when thesis/conversation IDs are supplied.
- Structured errors always include `category`, `retryable`, and `remediation`.
- Capability resource envelopes are projected onto `ToolLimits` before handler
  execution. Confirmed runs persist effective configuration, resolved paths,
  seeds, limits, warnings, fingerprint, canonical hash, and terminal errors.
- Explicit `cancel_run()` transitions a running research run to cancelled and
  audits the outcome. Stale cancel attempts against non-running runs return a
  structured lifecycle failure instead of raising. Cancel-vs-complete races keep
  the cancelled terminal state and attach late bundle provenance when compute
  finished after cancel. UI feedback uses the returned orchestration status so
  cancelled races are not reported as completed. Failed list dispatches are
  shown as errors rather than empty collections.
- Provenance-gated bundle loads require non-empty expected hashes
  (`BUNDLE.import`, export, and `PORTFOLIO.analyze`) and fail closed instead of
  skipping verification. Terminal lifecycle audits are best-effort so a
  transcript race cannot overturn a completed or cancelled run.

## C2-2 — Executable RunSpec compiler

**Goal:** compile a thesis into a version-1 API-valid research specification.

**Scope**
- Add a deterministic mapping from structured choices to `dataset`, `levels`,
  `setup`, `backtest`, optional `grid`, `validation`, and `walk_forward`.
- Preserve the existing prose compiler solely for ambiguity detection.
- Add supported definitions for trend, trigger/tolerance, session window,
  dVWAP/SMA confluence, costs, exposure, intrabar, and SL/TP selection.
- Validate every ready draft with `validate_run_spec()` before confirmation.
- Reject unsupported registry features and incomplete/contradictory choices.

**Acceptance**
- Same choices yield an identical canonical spec.
- Confirmed spec always passes `validate_run_spec()`.
- Example dVWAP/SMA prompt produces questions until all operational fields are
  supplied.
- Fixtures prove no silent defaults for costs, session, selection protocol, or
  random state.

**Implemented contract (compiler v2)**
- `StructuredThesisChoices` is the versioned typed draft boundary. The canonical
  mapper accepts only public executable sections and rejects narrative-only
  fields rather than persisting ignored assumptions.
- Confirmation recompiles and calls `validate_run_spec()` before its immutable
  child record is written. Confirmed content is revalidated before execution.
- Costs, exposure, intrabar behavior, session close/timezone/entry cutoff,
  validation seed, enabled-grid selection, and walk-forward protocol (including
  fold sizes for the selected `fold_mode`) are explicit inputs; the compiler
  supplies none of them.

## C2-3 — Bundle-backed run lifecycle

**Goal:** connect confirmed specs to reproducible execution and provenance.

**Scope**
- Extend the tool execution path to mirror CLI behavior: run API, build bundle,
  write within the thesis assistant namespace, calculate canonical hash.
- Orchestrator sequence: `start_run` → execution → `complete_run` /
  `fail_run` / `cancel_run`.
- Persist compact summary plus source bundle reference; never duplicate engine
  data into conversation state.
- Record data fingerprint, canonical hash, tool version, resolved paths,
  resource limits, warnings, and terminal error details.

**Acceptance**
- A fixed fixture produces equal canonical bundle hashes through CLI and
  assistant execution.
- Interrupted/failing runs retain request and terminal error but no success
  summary.
- Reloading a thesis displays historical completed runs unchanged.

**Implemented contract (execution parity / provenance gate)**
- Fixed fixture `tests/fixtures/assistant_parity.py` drives direct
  `run_experiment`, CLI `run_batch` / `python -m thesistester run`, assistant
  `run_experiment_to_bundle`, and `execute_confirmed_run`; all four surfaces
  must emit the same `canonical_bundle_hash`.
- `execute_confirmed_run` fails closed unless the written bundle is readable
  and its on-disk digest matches the reported hash before `complete_run`.
- Provenance-gated loads reject replaced/corrupt bundles for explanation
  (`BUNDLE.import` evidence), comparison (`compare_bundle_summaries`),
  report/artifact export, and portfolio analysis.
- Completed, failed, interrupted (`KeyboardInterrupt` during compute), and
  cancelled terminal states retain request metadata; only completed runs carry
  a success summary. Historical reload via a fresh repository preserves
  provenance and compact summary bytes.

## C2-4 — Research workspace completion

**Goal:** complete the Streamlit workflow without duplicating business logic.

**Scope**
- Page delegates only to orchestrator APIs.
- Add plan-review card, explicit confirmation, run button/status, run history,
  provenance panel, and deep links/bundle handoff to existing research pages.
- Add conversation transcript and tool transcript views.
- Add compare-run selector and archive/clone/rename thesis actions.
- Replace raw JSON as the default UI with structured clarification controls;
  retain JSON as an advanced audit view.

**Regression safety**
- Existing page session-state producers remain untouched.
- New `assistant_*` keys are additive and documented in `ARCHITECTURE.md`.
- UI tests cover thesis switch, confirmation idempotency, failed run, and
  restored bundle state.

**Implemented contract (orchestrator-only workspace)**
- `pages/14_Research_Assistant.py` is presentation-only: it constructs
  `AssistantOrchestrator.for_local_workspace()` and never calls
  `LocalThesisRepository`, `AssistantTools`, compilers, explainers, or
  bundle I/O directly.
- Workspace façade methods cover thesis/spec lifecycle, validate/confirm,
  execute/cancel, explain/compare, report/artifact export, portfolio analysis,
  and hash-verified bundle handoff into research-page session keys.
- Structured controls cover setup/confluence, levels, execution, grid,
  validation, and walk-forward (including bars mode and optional WFA matrix).
  JSON remains under Advanced and applies only through an explicit audit
  action.
- Plan-review and provenance cards are presentation helpers in
  `thesistester/assistant/workspace.py`. Plan review includes the newest
  `needs_clarification` assumptions. Thesis switches clear scoped staging
  keys (including `assistant_bundle_handoff`) so draft/validation/hydration/
  handoff cannot leak across theses.
- Compare persistence is best-effort: computed evidence remains available when
  `save_comparison` fails. Report and artifact export are independent actions.
  Untouched drafts keep the `allow_all` exposure-policy default.
- Helper/page-contract tests live in `tests/test_assistant_workspace.py`.

## C2-5 — Evidence and comparison expansion

**Goal:** answer useful research questions without hallucinating statistics.

**Scope**
- Expand evidence packets for baseline metrics, grid selection, costs,
  exposure, intrabar, time analysis, excursions, validation, Monte Carlo,
  sensitivity, overfitting, and WFA.
- Add deterministic templates: explain result, explain failure, explain
  candidate SL/TP, explain validation, and compare selected runs.
- Add a schema-versioned comparison object linked to exact input run IDs/hashes.
- Require “best” language to state ranking metric, candidate set, trade count,
  selection sample, and OOS/validation status.

**Acceptance**
- Fixture tests prove every displayed numerical claim exists in the evidence
  packet.
- Mandatory caveats appear for low N, zero costs, overlap, intrabar ambiguity,
  grid selection, and failed robustness checks.

## C2-6 — Optional LLM provider layer

**Goal:** add conversational natural-language assistance only after C2-1–5.

**Scope**
- Provider-neutral `assistant/llm.py` with explicit configuration.
- Provider-native structured outputs for intent, clarification, and tool
  requests; deterministic schema validation at the boundary.
- LLM can propose choices and paraphrase evidence only; it cannot issue engine
  calls, construct unvalidated specs, or override confirmation.
- Use on-demand tool discovery for less common capabilities; keep core
  read-only tools in context.

**Acceptance**
- Prompt injection attempts cannot reach arbitrary tools.
- Tool request/output schemas are evaluated with realistic multi-step fixtures.
- LLM-free deterministic fallback remains usable.

**Implementation status:** C2-6.1 through C2-6.3 provide the provider,
strict intent adapter, and persisted non-executing turns. C2-6.4 adds the
Streamlit transcript/input integration; tool execution remains unavailable from
chat until the explicit confirmation/run lifecycle is wired.

## C2-7 — Feature-parity completion

Implement remaining registry capabilities in this order:

1. Align time analysis with a public API facade; expose costs, exposure,
   intrabar, exits, grids, and session analysis.
2. Surface validation, excursions, Monte Carlo, noise, sensitivity, and
   overfitting in evidence/templates.
3. Add WFA matrix and portfolio comparison.
4. Add saved defaults/setup-library provenance, import/export, and visualization
   handoff.
5. Either implement or explicitly retain user-visible exceptions for resample
   preview, roll metadata, and OTF validation matrix.

Every capability requires registry status, typed schema, resource envelope,
evidence shape, explanation rule, tests, and documentation.

## Research-integrity controls

- Maintain thesis/workstream trial counts and display multiple-testing warnings.
- Preserve all candidate grid/variant attempts.
- Never call an LLM inside historical signal/backtest logic.
- Enforce point-in-time constraints at data/tool boundaries.
- Treat LLM output as untrusted input; validate before persistence or execution.
- Require explicit seeded stochastic diagnostics.

## Testing and release gates

Every PR must run `ruff check .`, `ruff format --check .`, and `pytest -q`.
Changes touching tools also require path-containment, resource-limit,
confirmation, and error-schema tests. Changes touching run lifecycle require
API/tool parity and canonical bundle-hash tests. Engine/level/signal changes
require existing golden-master and point-in-time gates.

Add an agent evaluation suite before enabling an LLM provider: realistic
read-only tasks, deterministic expected outputs, tool-call assertions,
confirmation-gate tests, and adversarial prompt-injection cases.

**C2-6.7 implementation status:** adversarial fixtures cover malformed intent,
tool-request injection, duplicate/blank choices, and unexpected explanation
fields. Extend this suite with provider-failure and UI confirmation scenarios as
each execution path is connected.

## External design inputs

- [Anthropic advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use):
  on-demand tool discovery and bounded context.
- [Anthropic MCP evaluation guidance](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/reference/evaluation.md):
  realistic, verifiable tool-use evaluations.
- [Anthropic tool design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents):
  ergonomic, tested tool contracts.
- [MCP-AgentBench](https://arxiv.org/pdf/2509.09734): outcome-oriented
  evaluation for tool-mediated agents.

These inputs support the roadmap's schema-first, deterministic, auditable
design; they do not replace ThesisTester's point-in-time and research-integrity
requirements.
