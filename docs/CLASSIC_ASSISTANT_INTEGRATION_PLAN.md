# Classic Workspace and Research Assistant Integration Plan

## Status

**Status:** proposed implementation contract; `CAI-0` through `CAI-5` implemented.

**Owner model:** one trusted local user, local datasets, local execution.

**Implementation rule:** each numbered milestone is a separately reviewable PR.

**Baseline record:** `docs/CAI_BASELINE.md`.

## Purpose

ThesisTester currently provides two useful but disconnected workflows:

1. **Classic workspace:** Data → Levels → Setup Builder → Signals → Backtest.
   It is fast for iterative work because page state retains computed data and
   levels during a browser session.
2. **Research Assistant:** thesis → explicit RunSpec → validate → confirm →
   execute → bundle-backed explanation. It is reproducible and evidence-backed,
   but presently re-enters the headless pipeline from `dataset.path` and does
   not understand a completed classic-page run as a thesis experiment.

The target is not to replace the classic workspace with chat. The target is one
research graph with two interfaces:

```text
immutable data asset
  → immutable derived-level artifact
    → optional active research context (thesis)
      → immutable experiment records (classic / assistant / CLI origin)
        → hash-verified research bundle
          → compare, explain, discuss, restore, and inspect
```

The classic workspace remains the best interface for visual configuration and
fast exploration. The Assistant remains the best interface for thesis
definition, evidence-backed discussion, comparison, and reproducible revision.

## Evidence-backed current state

### What already works

- Classic pages use a shared Streamlit session contract. Data and Levels are
  retained in `st.session_state`; later pages consume those values.
- The Levels page can manually persist and reload a saved levels snapshot using
  `dataset_id` plus `compute_levels_settings_hash()`.
- Assistant and CLI runs use the public `thesistester.api.run_experiment()`
  pipeline and write hash-verified research bundles.
- A completed Assistant bundle can restore managed research keys into classic
  pages through `AssistantOrchestrator.restore_run_bundle_to_session()`.
- A research bundle contains the data, levels, setup/signal state, trades, and
  analyses required to reconstruct a completed research state.

### Current gaps

1. `run_experiment()` always calls `load_dataset()` and `compute_levels()`.
   It does not use the classic Levels snapshot store.
2. The existing saved-level snapshot format is user-facing and manually
   managed. It must not become an implicit, unbounded execution cache.
3. There is no common canonical-levels-config normalizer. The API merges
   defaults, sets instrument, and sorts list fields before computation; the
   classic snapshot lookup hashes the settings supplied to it. A cache bridge
   must normalize once before deriving any identity.
4. A classic backtest/bundle cannot become a thesis run. The Assistant can
   inspect imported evidence but cannot attach a classic completed experiment
   to thesis lineage.
5. Classic page edits after an Assistant restore do not fork a new immutable
   specification. The bridge is one-way.

## Product contract

### User-visible behavior after the roadmap

1. A user can optionally create or link a thesis while configuring a setup in
   the classic workspace.
2. The user can keep using Data, Levels, Setup Builder, Signals, and Backtest
   normally.
3. A completed classic run can be recorded as an immutable, bundle-backed run
   under the active thesis without recomputing it.
4. The Assistant can explain, compare, and discuss any recorded classic or
   Assistant-origin run from its verified bundle evidence.
5. A confirmed Assistant run reuses verified canonical data and levels
   artifacts when their identities exactly match; otherwise it performs a cold
   run and creates fresh artifacts.
6. A user can restore any recorded run into the classic pages, revise it, and
   explicitly record the revision as a new thesis run.

### Non-goals

- No direct Assistant execution from `st.session_state["data"]`,
  `st.session_state["levels"]`, or any other mutable page object.
- No implicit conversion of every exploratory page click into a thesis run.
- No silent mutation of an immutable confirmed specification.
- No LLM access to arbitrary files, DataFrames, shell commands, or engine
  internals.
- No change to level, signal, backtest, validation, or point-in-time semantics.
- No requirement to use a thesis for ordinary page-based exploration.

## Architectural decisions

### D1 — Immutable artifacts, never live session objects

The Assistant must never consume a live Streamlit DataFrame as its execution
input. Session state may be stale, partially updated, or manually modified. It
does not carry sufficient immutable provenance.

Instead, classic and Assistant execution share content-addressed persisted
artifacts. A page can publish an artifact; an Assistant run can consume it only
when every identity component matches.

### D2 — Separate execution cache from user snapshots

The existing local “Saved levels” UX remains a user-managed snapshot feature.
Automatic reuse belongs in a new internal execution-artifact namespace, hidden
from that UI. This prevents normal Assistant use from filling the user's saved
snapshot selector and permits independent retention/eviction policies.

### D3 — Canonical identity before cache lookup

All cache keys must use shared pure normalizers:

```text
DataIdentity
  = schema version
  + canonical data content hash
  + instrument
  + source timezone
  + exchange timezone
  + format profile

LevelsIdentity
  = DataIdentity
  + canonical normalized levels settings hash
  + level-engine version
  + artifact schema version

ExperimentIdentity
  = LevelsIdentity
  + canonical executable RunSpec hash
```

The normalizer must be the only location that merges level defaults, records
instrument, validates supported keys, and canonicalizes unordered list values.
Classic pages, API, CLI, bundle import, and the Assistant all call it.

### D4 — Cache correctness is more important than hit rate

- The raw source file is fingerprinted by content, not only by path or mtime.
- A changed source file, input profile, timezone contract, engine version,
  artifact schema, or canonical levels config produces a cache miss.
- Missing, corrupt, partially written, or unknown-version artifacts fail cold;
  they never cause a failed or stale cache hit.
- Cache use is reported in run provenance (`cold`, `data_hit`,
  `levels_hit`, or `bypassed`) but cannot change numerical results.

### D5 — Research mode is explicit

Classic exploration stays untracked by default. A user explicitly starts or
links a thesis to enter **research mode**. Within research mode, the interface
must make the recording policy conspicuous:

- Initial rollout: the user clicks **Record and discuss this run** after a
  completed Backtest.
- Follow-up rollout: an opt-in **record every execution in this thesis** policy
  captures successful, failed, and cancelled attempts, preventing selective
  recording of only favorable outcomes.

### D6 — A bundle is the interchange contract

Classic-to-Assistant attachment works by verifying and registering a completed
research bundle. It must not reconstruct metrics from screen widgets or rerun
the experiment merely to attach it. A bundle attached to a thesis retains its
canonical bundle hash, source origin, immutable evidence, and original run
timestamp.

## Invariants

These rules are non-negotiable for every milestone.

1. Existing engine outputs retain their semantics.
2. Cache-hit and cold executions produce equal canonical bundle hashes for an
   equivalent fixed RunSpec and fixture.
3. A recorded run is immutable. Classic revisions create a new run and, when
   execution choices change, a new specification version.
4. The Assistant only explains bundle-backed evidence. It never reads transient
   classic page state as evidence.
5. Data/levels identity comparisons are exact; a partial match is displayed as
   non-comparable, never as equivalent.
6. Old bundles and run records remain readable. New persisted fields are
   additive and schema-versioned.
7. Cache loading is bounded to the configured local store and validates
   artifact schema/engine version before deserialization.
8. Every user-facing compute action keeps the existing confirmation boundary:
   assistant compute starts only from a confirmed immutable RunSpec.
9. All documentation, registry entries, schemas, and tests change in the same
   PR as the behavior they describe.

## Milestone roadmap

### CAI-0 — Baseline characterization and decision record ✅ Implemented

**Goal:** freeze the current behavior before connecting execution paths.

**Scope**

- Add this plan and an implementation record section in
  `docs/ENGINEERING_ROADMAP.md`.
- Measure the current cold-path timing for:
  - canonical CSV loading;
  - level computation, including rolling POC;
  - signals/backtest; and
  - bundle construction.
- Capture representative fixed fixtures: one small fixture for exhaustive CI
  and one realistic-size fixture for non-blocking benchmark reporting.
- Document the chosen initial recording policy: manual record-after-run.

**Implemented contract**

- Fixtures live in `tests/fixtures/cai_baseline.py`:
  - `small` = 60 RTH bars, no rolling POC (CI smoke);
  - `realistic` = 780 bars / two RTH sessions with `poc_windows=["30min"]`
    (informational only).
- Harness: `python3 -m tests.benchmarks.cai_cold_path --fixture both --repeats 5`
- Baseline record, stage shares, and recording-policy decision:
  `docs/CAI_BASELINE.md`
- Initial recording policy is **manual record-after-run**; automatic
  `all_executions` remains deferred/opt-in for CAI-7.
- On the realistic fixture, `compute_levels` accounted for ~71% of end-to-end
  cold median time, confirming levels artifact reuse as the first performance
  target for CAI-2/CAI-3.

**Tests and acceptance**

- Existing API/CLI/Assistant canonical bundle parity fixture remains green.
- Benchmark harness is reproducible and does not become a CI pass/fail
  performance threshold.
- The plan identifies the exact fixtures, commands, and baseline results.

**Non-goals:** no production cache or UI behavior.

### CAI-1 — Shared canonical configuration and identity module ✅ Implemented

**Goal:** create one pure source of truth for identity derivation.

**Scope**

- Add a Streamlit-free module, for example
  `thesistester/research_identity.py`.
- Extract API levels normalization into
  `normalize_levels_config(config, *, instrument)`.
- Define serializable, frozen `DataIdentity`, `LevelsIdentity`, and
  `ExperimentIdentity` contracts.
- Provide constructors from:
  - canonical loaded data;
  - normalized RunSpec;
  - classic canonical page state; and
  - bundle manifest/provenance.
- Add only additive bundle/run metadata fields:
  `data_identity`, `levels_identity`, and `execution_origin`.

**Implemented contract**

- Module: `thesistester/research_identity.py`.
- `api.compute_levels` and identity derivation call
  `normalize_levels_config` (product defaults + instrument + sorted unordered
  lists; unknown keys rejected). Classic page sparse
  `_normalize_levels_settings` remains a legacy UX stale-check path only.
- `DataIdentity.dataset_id()` matches `compute_dataset_id` and **excludes**
  `format_profile` (carried as additive metadata until an explicit dataset-id
  version bump).
- `LevelsIdentity` includes `LEVEL_ENGINE_VERSION` and
  `LEVELS_ARTIFACT_SCHEMA_VERSION` (artifact schema, not UX snapshot schema).
- `run_experiment(..., execution_origin=...)` stamps additive state fields.
  Optional bundle member `research_identity.json` carries `data_identity` and
  `levels_identity` only when present. `execution_origin` is run provenance
  and is excluded from that member so origin cannot change canonical bundle
  hashes. `experiment_identity` remains on run state/provenance until
  path-canonical RunSpec hashing lands (relative vs absolute dataset paths).
- Bundle restore also manages `format_profile` (via `dataset_meta.json`, with
  fallback from `data_identity`) and clears stale `experiment_identity` /
  `execution_origin` so a prior session cannot leak provenance into an import.
- `normalize_levels_config` ignores inbound `instrument` keys (classic
  page/bundle settings carry them) and binds from the explicit parameter.
- Identity write/load promotes nested `levels_identity.data_identity` to a
  top-level `data_identity` when the top-level key is absent.
- Tests: `tests/test_research_identity.py`.

**Regression gates**

- Normalization parity tests prove API and classic levels configuration yield
  the same normalized config and hash for equivalent inputs.
- Run existing level/API/CLI/Assistant parity tests.
- Old bundle and run metadata load with `None`/unknown optional identity fields.

**Acceptance**

- No production cache lookup occurs yet.
- The same normalized levels settings always hash identically regardless of
  input key order or list ordering where order is not semantically meaningful.

### CAI-2 — Durable execution-artifact store ✅ Implemented

**Goal:** establish a safe, internal cache for canonical data and levels.

**Scope**

- Add a schema-versioned artifact namespace separate from datasets and
  user-facing saved level snapshots.
- Persist:
  - canonical data artifact and ingestion metadata;
  - levels and session-level artifacts;
  - `DataIdentity` / `LevelsIdentity`;
  - engine and artifact schema versions; and
  - creation/access timestamps for later retention.
- Implement atomic directory publication:
  write complete artifact files to a temporary sibling directory, fsync where
  supported, then atomically publish the completed directory/manifest.
- Add per-identity locking or single-writer coordination. A concurrent writer
  must either reuse a completed artifact or safely publish an equivalent one.
- Add `read_verified_*`, `write_*`, and `invalidate_*` APIs. They must return a
  miss for corrupt, incomplete, unknown-version, or engine-incompatible data.

**Implemented contract**

- Module: `thesistester/persistence/execution_artifacts.py`.
- Namespace:
  `{store}/execution_artifacts/v1/data/<key>/` and
  `{store}/execution_artifacts/v1/levels/<key>/` (separate from
  `datasets/` and UX `levels/`).
- Data artifact keys include `format_profile` (cache correctness) even though
  legacy `dataset_id` still excludes it.
- Levels artifact keys bind data-artifact key + settings hash + engine +
  artifact schema versions.
- `read_verified_*` returns `ArtifactMiss` (never raises) for missing, corrupt
  (including non-numeric schema/engine version fields), incomplete,
  schema-drift, engine-incompatible, identity/content mismatch, or
  path-escape cases.
- `write_*` publishes under per-identity `fcntl` locks with temp-dir + rename;
  a concurrent writer reuses a verified completed artifact.
- Tests: `tests/test_execution_artifacts.py`.
- No API/page wiring yet (CAI-3).

**Regression gates**

- Unit tests: cold miss, valid hit, corrupt manifest, missing parquet, schema
  drift, engine-version drift, non-numeric version fields, concurrent publish,
  and path containment.
- Existing `save_levels` / `find_matching_levels` UX remains unchanged.

**Acceptance**

- No page or pipeline consumes the artifact store automatically yet.
- Failure to read an artifact never fails a valid cold computation.

### CAI-3 — Cached headless pipeline parity ✅ Implemented

**Goal:** let the public API reuse verified data/levels artifacts without
changing research semantics.

**Scope**

- Add an explicit keyword-only cache policy to `run_experiment()` and
  `compute_levels()`, initially defaulting to legacy cold behavior.
- The Assistant and CLI opt into `read_write` only after all parity tests land.
- Resolve source file content identity, then:
  1. load canonical data artifact on exact hit or ingest/canonicalize and write;
  2. load levels artifact on exact hit or compute and write;
  3. execute signals/backtest/validation exactly as today.
- Include cache outcome and identities in bundle provenance.
- Do not use the classic session DataFrames as a cache source.

**Implemented contract**

- `run_experiment(..., cache_policy="off"|"read"|"read_write", store_root=...)`
  and `compute_levels(..., cache_policy=..., data_identity=..., store_root=...)`.
  Public default remains ``off`` (legacy cold).
- CLI and Assistant pass ``cache_policy="read_write"``.
- Source binding index under
  `execution_artifacts/v1/source_index/<binding_key>.json` maps
  `(source_bytes_hash, instrument, timezones, format_profile)` →
  `DataIdentity` / data artifact key so warm runs skip CSV parsing.
- State/provenance field `cache_provenance` reports
  `{policy, outcome, data, levels}` with outcomes
  `bypassed|cold|data_hit|levels_hit`. It is cleared on bundle import and
  excluded from hashed bundle members so cold/warm hashes match.
- Tests: `tests/test_cai3_cached_pipeline.py`.

**Regression gates**

- For each fixed fixture, cold and warm execution must have:
  - equal canonical bundle hashes;
  - equal canonical data/levels/signals/trades frame values; and
  - equal diagnostics and validation outputs.
- Cache corruption, stale source content, changed timezone/profile, changed
  normalized levels settings, and changed engine version must cold-run.
- Golden-master legacy tests remain unchanged.

**Acceptance**

- A repeated Assistant/CLI run with the same source content and levels config
  skips CSV parsing and level computation after warm-up.
- Cache use is observable in provenance and UI status, never inferred from
  timing alone.

### CAI-4 — Classic-state-to-RunSpec export ✅ Implemented

**Goal:** transform canonical classic workflow state into a reproducible draft,
not a live Assistant execution input.

**Scope**

- Add pure `classic_state_to_run_spec()` and
  `classic_state_export_gaps()` helpers.
- Consume only canonical page-produced state:
  `data` DataFrame, `dataset_id`, data provenance, `levels_settings`,
  `setup_config`, signal settings, and backtest execution policy.
- Reject incomplete, stale, or internally inconsistent state with explicit
  gaps; never invent missing parameters. A stored `data_identity` without the
  in-memory frame is a `missing_data` gap.
- Map page state to the current public RunSpec schema and validate it through
  `validate_run_spec()`.
- Include a stable source reference strategy:
  - preferred: a verified local canonical data artifact reference;
  - fallback: an explicit source CSV path supplied by the user and verified
    against the classic `DataIdentity`.

**Implemented contract**

- Module: `thesistester/classic_export.py` (Streamlit-free).
- `classic_state_export_gaps(state, *, source_path=..., store_root=...,
  include_grid=..., include_validation=..., include_walk_forward=...)`
  — same optional-section flags as `classic_state_to_run_spec` so gap discovery
  and export agree
  returns structured gaps (`missing_*`, `stale_levels`,
  `source_path_identity_mismatch`, etc.). Non-integer
  `levels_data_fingerprint.rows` is a `stale_levels` gap (not an uncaught
  `ValueError`).
- `classic_state_to_run_spec(...)` raises when gaps remain; otherwise returns a
  `validate_run_spec`-validated RunSpec.
- Source resolution: verified data artifact (`dataset.data_artifact_key`) is
  preferred metadata; executable `dataset.path` still required and verified
  against classic `DataIdentity` (from `source_path` kwarg or
  `dataset_source_path` / `source_csv_path` state). Blank/whitespace
  `source_path` kwargs fall through to those state keys. Corrupt/incomplete
  preferred artifacts are omitted so a verified CSV path can still complete
  the export.
- Backtest may come from explicit `backtest_config` or assembled from page
  widget keys (preferred) with post-run policy snapshots as fallback, without
  inventing SL/TP/session fields. Disabled `flat_by_session_close` clears
  session timezone / entry cutoff on both paths to match Backtest page
  persistence. Unpaired trailing fields (or invalid BE/trail values) yield
  `incomplete_exit_management` gaps before `validate_run_spec`.
- Optional grid/validation/walk-forward export only when explicit `*_config`
  mappings are present (`include_grid` / `include_validation` /
  `include_walk_forward`).
- Additive dataset keys `data_artifact_key` / `data_identity` allowed by
  `validate_run_spec`.
- Tests: `tests/test_classic_export.py`.

**Regression gates**

- Determinism tests: the same canonical page state yields the same draft.
- Equivalent classic export and hand-authored RunSpec produce equal canonical
  bundle hashes on a fixture.
- Missing data path/reference, setup, or levels state becomes an explicit
  clarification; no default is injected.

**Acceptance**

- The exporter remains Streamlit-free and is usable by bundle import and
  future non-UI callers.

### CAI-5 — Thesis research context lifecycle ✅ Implemented

**Goal:** allow the classic workspace to enter/leave an explicit thesis context.

**Scope**

- Add a small, additive classic-workspace context contract:
  active thesis ID, recording policy, and optional pending navigation target.
- Add **Create thesis** / **Link existing thesis** to Setup Builder.
- Display a compact thesis breadcrumb and exit/relink action on Setup Builder,
  Signals, Backtest, and Research Bundles.
- Keep thesis prose separate from executable settings. Prose is recorded in the
  thesis conversation; executable settings come only from canonical page state.

**Implemented contract**

- Module: `thesistester/classic_context.py` (helpers are Streamlit-free;
  `render_classic_thesis_chrome` imports Streamlit lazily for page chrome only).
- Additive session keys (`CLASSIC_SESSION_KEYS`):
  `classic_active_thesis_id`, `classic_active_thesis_name`,
  `classic_recording_policy` (default `manual` per CAI-0;
  `all_executions` storable for CAI-7), `classic_pending_navigation`,
  `classic_bound_dataset_id`, `classic_flash`.
- `link_thesis(...)` enters research mode and syncs
  `assistant_selected_thesis_id` via `select_thesis`; it does not create specs,
  start runs, or mutate protected classic producer keys.
- `sync_classic_context_for_dataset(...)` clears thesis-scoped classic keys when
  the active `dataset_id` diverges from `classic_bound_dataset_id`.
- Setup Builder: create/link expander. Signals, Backtest, Research Bundles:
  breadcrumb + exit/relink only.
- Tests: `tests/test_classic_context.py`.

**Regression gates**

- Session-state contract tests verify existing producer/consumer keys retain
  their values and types.
- Thesis switch/dataset switch tests prove context cannot leak across sessions.
- No run is recorded merely by linking a thesis.

**Acceptance**

- A user can create a thesis while building a setup and still run classic pages
  exactly as before.

### CAI-6 — Attach a completed classic run to a thesis

**Goal:** turn a completed classic Backtest into a discussable thesis run
without recomputing it.

**Scope**

- Add a `register_external_bundle_run()` orchestrator facade.
- It verifies:
  - bundle schema and containment;
  - canonical bundle hash;
  - required data/levels/setup/backtest provenance; and
  - compatibility with the exported RunSpec.
- Create an immutable run record with `execution_origin="classic"` and link it
  to a specification version created from CAI-4.
- Add **Record and discuss this run** in the completed Backtest / Research
  Bundles flow. It creates a bundle if one is not already available, verifies
  it, records it, and opens the linked thesis.
- Add a registry capability and structured audit transcript. This action is
  explicit; it must not bypass Assistant confirmation for future recomputation.

**Regression gates**

- A registered external bundle's hash and evidence packet equal the original
  bundle's hash and evidence.
- Tampered, missing, corrupt, or out-of-store bundles fail closed.
- Repeating registration is idempotent or explicitly offers a new record;
  behavior is documented and tested.
- Existing Assistant run lifecycle tests remain green.

**Acceptance**

- The Assistant can explain and compare a classic-origin run immediately after
  registration, with no CSV load or level computation.

### CAI-7 — Research-mode execution ledger

**Goal:** make the history statistically honest once a user intentionally
works under a thesis.

**Scope**

- Add an opt-in recording policy: `manual` (default) or `all_executions`.
- In `all_executions`, record a requested run before classic execution and
  retain terminal statuses for completed, failed, and cancelled attempts.
- Include origin page, effective classic config hash, bundle hash when
  available, timestamps, warnings, and terminal error information.
- Surface a thesis run ledger in Backtest and Assistant, including a clear
  distinction between exploratory/unrecorded runs and thesis-recorded runs.

**Regression gates**

- Failed/cancelled records cannot appear as completed.
- A failed bundle write cannot erase the run request/audit record.
- No existing classic backtest behavior changes while policy is `manual` or no
  thesis context is active.

**Acceptance**

- An opted-in thesis has a complete attempt history suitable for evidence-based
  discussion and avoids selective preservation of only favorable outcomes.

### CAI-8 — Bidirectional navigation and identity-aware UI

**Goal:** make the shared graph visible without duplicating application pages.

**Scope**

- Add:
  - **Discuss this run** from Backtest/Bundles;
  - **Open exact run in Backtest** from Assistant;
  - active thesis/run breadcrumb after bundle restore; and
  - data/levels identity badges (`exact match`, `same data/different levels`,
    `different data`, `identity unavailable`).
- Query run metadata only; do not load full bundles until the user opens,
  explains, restores, or compares a run.
- Add a direct path from Assistant clarification/proposal to the relevant
  classic page. Initial behavior is navigation plus prefilled draft only, not
  automatic page mutation.

**Regression gates**

- Identity badge tests use exact immutable identities, not display labels.
- Navigation context clears after a thesis switch and cannot select a run from
  another thesis.
- Existing bundle restore remains hash-verified.

**Acceptance**

- A user always knows whether the currently visible classic data/levels match
  the run being discussed.

### CAI-9 — Evidence-backed page capability expansion

**Goal:** close the “second application” gap progressively without giving the
Assistant unbounded access.

**Scope**

Implement each capability as its own sub-PR after CAI-6:

1. Read-only levels summary: configuration, identity, families, columns.
2. Read-only signals summary: count, zones, trigger/direction distributions.
3. Read-only backtest summary: KPIs, costs, intrabar policy, caveats.
4. Read-only grid/validation summary: candidate selection and OOS evidence.
5. Controlled proposal actions: Assistant creates a draft change for classic
   review; user explicitly applies it on the owning page.

Each capability must add a registry entry, bounded handler output, evidence
packet paths, grounded explanation templates, limits, documentation, and tests.
Charts remain owned by classic pages; the Assistant links to/restores the exact
recorded run rather than rendering unconstrained DataFrames.

**Regression gates**

- Every numeric Assistant claim is grounded in a bundle evidence path.
- Handlers return bounded JSON, never raw arbitrary DataFrames.
- Unsupported capabilities stay explicitly unsupported until their PR lands.

### CAI-10 — Artifact operations, retention, and performance hardening

**Goal:** make shared artifacts observable and operable over long research use.

**Scope**

- Add cache inspection: identity, size, age, producer, schema/engine version,
  hit/miss count, and safe deletion.
- Add bounded retention/eviction only for internal execution artifacts; never
  delete user-saved snapshots, bundles, thesis records, or source datasets
  without explicit action.
- Add source relocation tooling: rebind a missing source path only after
  content identity verification.
- Measure whether signal artifacts merit a second cache layer after levels
  cache benchmarks are available.
- Document disk growth, data-retention, cache invalidation, and cold/warm
  performance behavior.

**Regression gates**

- Eviction cannot remove an artifact referenced by a retained bundle/run unless
  its bundle independently contains the required data.
- A cache deletion causes a safe cold recomputation, never a failed or stale
  hit.
- Benchmark reports never replace deterministic correctness gates.

## Dependency graph

```text
CAI-0
  └─ CAI-1
       └─ CAI-2
            └─ CAI-3
                 ├─ CAI-4 ─ CAI-5 ─ CAI-6 ─ CAI-7 ─ CAI-8 ─ CAI-9
                 └─ CAI-10
```

## Delivery slices

### First usable slice

`CAI-0` through `CAI-6` delivers:

- shared, verified data/levels reuse;
- thesis creation from the classic setup workflow; and
- no-rerun recording/discussion of a completed classic backtest.

### Research-quality history slice

`CAI-7` and `CAI-8` deliver:

- complete thesis attempt history when explicitly enabled; and
- clear navigation/identity between pages and the Assistant.

### Product-completeness slice

`CAI-9` and `CAI-10` deliver:

- progressive Assistant awareness of the existing page surface; and
- durable artifact operations and measured performance.

## Required test matrix for every milestone

Every PR runs the repository baseline:

```text
ruff check .
ruff format --check .
pytest -q
```

The following gates are additive to the baseline:

| Touched surface | Required evidence |
|---|---|
| Identity/config normalization | Pure deterministic unit tests; API/page/CLI normalization parity |
| Artifact persistence | Schema round-trip, corrupt/unknown version, partial-write, concurrency, containment |
| API/cache path | Cold-versus-warm canonical bundle hash equality and frame equality |
| Bundle/run registration | Hash verification, idempotency, tamper rejection, old-bundle compatibility |
| Assistant contracts/repository | Serialization, invalid-input, lifecycle, registry-audit tests |
| Streamlit pages | Session-state contract tests and manual workflow artifact |
| Levels/signals/engine path | Existing golden-master equality; future-shock tests if any computation changes |
| Evidence/LLM claims | Evidence-packet and grounded-claim tests |

### Golden-master policy

Cache work is an execution-path change, not an excuse to regenerate golden
outputs. The legacy cold path remains golden-gated. A warm-path test must prove
the same canonical bundle hash and frame values. Any proposed output difference
is rejected unless it follows the repository's dedicated golden-regeneration
policy with explicit review and approval.

## PR acceptance checklist

Every implementation PR must state:

1. the exact public/API/session/persistence surface changed;
2. its identity and provenance impact;
3. whether it reads, writes, or bypasses artifacts;
4. why cache or bridge behavior cannot alter numerical results;
5. migration behavior for old bundles/run records;
6. the cold-versus-warm or classic-versus-Assistant parity evidence;
7. all same-PR documentation updates; and
8. the relevant regression-safety gates from
   `docs/ENGINEERING_PROPOSAL.md` §4.

## Deferred decisions

| Decision | Recommended initial choice | Revisit when |
|---|---|---|
| Cache default | Legacy cold default in public API; explicit `read_write` for Assistant/CLI after CAI-3 parity | Cold/warm operational evidence is stable |
| Classic recording | Manual record-after-run (**CAI-0 decision**; see `docs/CAI_BASELINE.md`) | After users accept thesis research mode |
| Automatic all-run ledger | Opt-in only | CAI-7 |
| Signal cache | Defer | CAI-0/CAI-3 benchmarks show levels no longer dominate |
| Assistant page mutation | Proposal + user apply on owning page | Read-only parity is proven |
| Missing source path | Prefer verified internal canonical data artifact; otherwise require user-provided path | Source relocation requirements emerge |
| Retention/eviction | No automatic deletion before CAI-10 | Artifact usage and disk profile measured |

## Explicitly rejected approaches

### Direct use of page session DataFrames

Rejected because page state is mutable, partial, and unversioned. It cannot
prove that levels match current data/configuration and would make Assistant
provenance misleading.

### Merge the classic pages into the Assistant

Rejected because it would discard the fastest visual research workflow and
force a large refactor of stable page state contracts. The product needs shared
identity and handoff, not one interface.

### Auto-record every classic run globally

Rejected because casual exploration should remain lightweight. Complete
recording applies only after a user intentionally enters an explicit thesis
research mode.

### Use the existing “Saved levels” list as the automatic cache

Rejected because it changes user-visible snapshot semantics, creates retention
confusion, and lacks the execution-artifact lifecycle needed for safe reuse.
