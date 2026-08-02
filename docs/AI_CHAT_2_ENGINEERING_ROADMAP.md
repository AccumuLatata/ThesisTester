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
