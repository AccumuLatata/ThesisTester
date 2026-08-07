# 15-Second Primary Data → Derived 1-Minute Canonical Plan

**Status:** Delivered (PRs 1–3); PR4 recommend-only UX/docs complete
**Scope:** Explicit 15-second-primary ingestion for Quantower-style OHLCV exports
**Decision:** Build 1-minute canonical bars internally from uploaded 15-second
bars, and retain the uploaded 15-second bars as the only R12 intrabar source.

## 1. Problem and decision

The current R12 workflow accepts a separately exported one-minute primary CSV and
a lower-timeframe CSV. The lower data is accepted only when every one-minute
parent has exactly four timestamp-aligned 15-second bars whose first open, maximum
high, minimum low, and last close reconcile to the uploaded one-minute OHLC.

That is the correct safety rule for two independently exported files, but is
operationally fragile: two valid vendor exports can still differ in bar
boundaries, omissions, or aggregation. Parser success does not prove that the
two exports reconcile.

This plan establishes a different, explicit research contract:

1. The uploaded 15-second export is the source of truth.
2. ThesisTester derives complete one-minute canonical bars from it.
3. The original validated 15-second bars are retained as R12 lower-timeframe
   data.
4. Levels, signals, and decision-timeframe execution continue to use one-minute
   canonical bars. R12 continues to use 15-second bars only to order events
   inside a parent bar.

The resulting parent/lower OHLC relationship is deterministic by construction.
It does **not** make a vendor-native one-minute export equivalent to the derived
one-minute dataset; they are separate research datasets and may have different
volume, VWAP, profile, levels, signals, and trades.

## 2. Goals and non-goals

### Goals

- One explicit Data-page upload path for a supported 15-second vendor export.
- Complete, aligned 15-second coverage is required before a one-minute bar is
  emitted.
- The derived parent is valid for strict R12 `subtimeframe` replay without
  weakening `prepare_subtimeframe_context()`.
- Local saved datasets, research bundles, API runs, and CLI runs preserve the
  same source/derived relationship and provenance.
- Existing one-minute upload, optional separate lower-upload, engine defaults,
  and golden-master outputs remain unchanged.

### Non-goals

- Do not infer this mode merely because a file happens to have a 15-second
  cadence. The user selects an explicit ingestion mode and explicit vendor
  profile.
- Do not change R12 event ordering, `simulate_trades`, `sim_core`, levels,
  signal generation, or the legacy `sl_first` default.
- Do not synthesize, interpolate, forward-fill, or repair missing 15-second
  bars.
- Do not invent off-grid timestamps or silently floor misaligned stamps into
  valid opens. Sparse on-grid minutes are retained (v2); misaligned minutes
  are still dropped. Conservative R12 fallback covers sparse parents at
  simulation time without fabricating empty 15s bars.
- Do not claim tick-level ordering: a residual SL/TP tie inside a single
  15-second bar remains pessimistic SL-first under the existing R12 contract.

## 3. Locked data contract

### 3.1 Eligibility

The new mode accepts a parsed, validated OHLCV source only if all conditions
hold:

| Condition | Required behavior |
|---|---|
| Explicit mode and profile | User chooses `15s_primary_derive_1m`; no interval or header auto-detection. |
| Source cadence | On-grid opens among `:00`/`:15`/`:30`/`:45` with consecutive gaps that are exact multiples of 15 seconds (sparse 30s/60s gaps allowed). |
| Timestamp basis | Timestamps represent bar opens and are exchange-timezone aware after normal loader conversion. |
| Source validity | Existing fatal OHLCV failures remain fatal: duplicates, missing values, invalid OHLC ranges, and negative volume. |
| Bucket alignment | A source bar belongs to the exchange-local wall-clock minute containing its open timestamp. Valid expected opens are `:00`, `:15`, `:30`, and `:45`. |
| Observed coverage (v2) | A derived parent exists when the bucket contains one or more unique on-grid opens. Sparse trade-only minutes are retained; off-grid stamps drop the minute. |

**Amendment (v2):** Historical policy `complete_aligned_15s_to_1m_v1` required
exactly four sub-bars and dropped sparse minutes. That rejected normal
Quantower/Rithmic History Exporter trade-only files (empty 15s slots omitted).
Current policy `observed_aligned_15s_to_1m_v2` retains sparse on-grid minutes
and drops only misaligned buckets. Empty bars are still never synthesized.

The helper must reject duplicate source timestamps before grouping. A source
timestamp at an offset such as `:00:05` is not silently floored into a valid
bucket; that bucket is misaligned and yields no parent.

### 3.2 Derived OHLCV semantics

For each eligible minute `m` with observed on-grid opens `S` (a non-empty
subset of `{0s, 15s, 30s, 45s}`), derive:

```text
timestamp = m
open      = source.open at first observed stamp in S
high      = max(source.high over S)
low       = min(source.low  over S)
close     = source.close at last observed stamp in S
volume    = sum(source.volume over S)
```

When `|S|=4`, this is identical to the original complete-coverage aggregation.
The output is sorted and session-tagged through the existing `tag_session()`
path. Misaligned minutes produce no parent. Sparse minutes are retained for
levels/signals research; R12 strict replay still requires `|S|=4`, while
`subtimeframe_conservative` falls back to SL-first on sparse parents.

### 3.3 Coverage diagnostics and provenance

The derivation returns a typed result rather than a bare parent frame:

```python
@dataclass(frozen=True)
class DerivedParentResult:
    parent_data: pd.DataFrame
    source_data: pd.DataFrame
    source_interval: pd.Timedelta
    parent_interval: pd.Timedelta
    dropped_buckets: pd.DataFrame
    sparse_buckets: pd.DataFrame
    derivation_policy: str  # "observed_aligned_15s_to_1m_v2"
```

`sparse_buckets` / `dropped_buckets` are read-only diagnostics with at least:

- `timestamp`
- `reason` (`incomplete_coverage` in sparse; `timestamp_misalignment` in dropped)
- `expected_sub_bars`
- `observed_sub_bars`
- `observed_timestamps`

They are not used to patch source data. The UI reports counts and offers CSVs
for download. A derived dataset with zero retained parent rows fails clearly.

The following additive provenance mapping must follow all durable paths:

```json
{
  "ingestion_mode": "15s_primary_derive_1m",
  "source_interval": "15s",
  "derived_parent_interval": "1min",
  "derivation_policy": "observed_aligned_15s_to_1m_v2",
  "source_format_profile": "quantower_history_exporter",
  "source_content_hash": "<sha256>",
  "dropped_parent_bucket_count": 0,
  "sparse_parent_bucket_count": 0
}
```

`source_content_hash` is a hash of the normalized retained 15-second source
frame, not of original CSV bytes, so it can be reproduced after local save,
bundle import, or API ingestion.

### 3.4 Identity and comparability

The canonical derived one-minute frame remains the engine data identity and
therefore determines the existing `dataset_id`. This is correct because levels
and signals consume it. The source hash and derivation policy are additive
provenance and cache-binding fields; they must not silently alter legacy
one-minute IDs.

Comparison UIs and reports must state that runs are comparable only when both
canonical data identity **and** ingestion provenance match. In particular,
vendor-native 1m and derived 1m should never be described as equivalent merely
because their timestamps overlap.

## 4. Architecture changes

### 4.1 New pure derivation boundary

Add `thesistester/data/derive.py`:

- `DERIVATION_POLICY_COMPLETE_ALIGNED_15S_TO_1M_V1`
- `derive_complete_parent_ohlcv(source, *, parent_interval="1min")`
- `DerivedParentResult`

The function receives already parsed canonical OHLCV and has no Streamlit,
filesystem, persistence, or instrument dependency. It validates cadence,
ordering, duplicates, expected timestamp alignment, complete coverage, and
financial aggregation deterministically.

`resample_ohlcv()` is reused only where its aggregation semantics are shared,
not as the derivation implementation unless it gains an explicit
complete-coverage mode that leaves existing callers byte-for-byte unchanged.
The recommended first implementation keeps the complete-coverage gate in the
new module to avoid changing preview semantics.

### 4.2 Data page mode

Add an explicit mode selector displayed only for CSV uploads:

- `One-minute primary (existing)`
- `15-second primary — derive one-minute canonical (new)`

The latter is enabled initially only for `quantower_history_exporter`; adding
other vendor profiles later is a separate contract decision. On success:

| Session key | Value |
|---|---|
| `data` | Derived, session-tagged one-minute parent |
| `base_interval` | `"1min"` |
| `subtimeframe_data` | Original validated, session-tagged 15-second source |
| `subtimeframe_interval` | `"15s"` |
| `subtimeframe_format_profile` | Selected source profile |
| `ingestion_provenance` | JSON-safe mapping from §3.3 |
| `derived_parent_diagnostics` | Mapping of sparse + dropped diagnostic frames |

The mode invokes `prepare_subtimeframe_conservative_context()` as a
postcondition. Complete minutes must still reconcile under the strict R12
contract; sparse minutes record fallback reasons. Failure is a
programming/data-contract error and must fail closed rather than silently
load the parent without R12 data.

The legacy lower-timeframe expander is hidden whenever this mode is selected
in the ingestion-mode radio — including before a 15-second CSV installs
`ingestion_provenance` — because dual upload must not appear while the
selector says derive-from-15s. After a successful upload its source is already
attached. The expander remains unchanged for legacy one-minute primary mode.
Changing modes or replacing the upload clears all dependent dataset state,
including intrabar provenance and execution results.

### 4.3 Persistence and restore

Local persistence schema advances from v1 to v2:

```text
datasets/<dataset_id>/
  canonical.parquet                 # derived 1m or legacy primary
  subtimeframe.parquet              # only when attached
  meta.json                         # schema v2, source/derivation metadata
  raw.parquet                       # existing independent R17 capture sidecar
```

Requirements:

- v1 datasets load exactly as they do today, without a subtimeframe sidecar.
- v2 loads verify that a declared `subtimeframe.parquet` exists and can be
  parsed; missing/corrupt declared sidecars fail closed with a clear message.
- Save refuses to overwrite a different existing subtimeframe sidecar for the
  same canonical dataset ID, mirroring the raw-sidecar provenance guard.
- Save refuses `ingestion_mode=15s_primary_derive_1m` provenance without a
  subtimeframe sidecar (`has_subtimeframe` must be true after preserve logic).
- Restore repopulates `subtimeframe_data`, its interval/profile, and
  `ingestion_provenance` before dependent pages render — and never latches
  derive provenance when the lower frame is absent or unreadable.
- Legacy saves without a lower frame stay valid v2 records or remain readable
  v1 according to the narrowest migration that preserves existing data.

### 4.4 Headless API, CLI, cache, and bundles

Extend RunSpec dataset configuration additively:

```yaml
dataset:
  path: nq_15s.csv
  instrument: NQ
  source_timezone: America/New_York
  format_profile: quantower_history_exporter
  ingestion_mode: 15s_primary_derive_1m
```

`subtimeframe_path` remains supported for legacy dual-file runs. Validation
rules:

- `ingestion_mode` is absent or `"primary"` for legacy behavior.
- `"15s_primary_derive_1m"` requires source interval 15 seconds.
- It supplies `subtimeframe_data` internally; pairing it with
  `subtimeframe_path` is rejected as ambiguous.
- R12 models work with the generated source; `sl_first` remains valid and does
  not require its use.

Execution-artifact source-index bindings must include a normalized
`ingestion_mode`/derivation-policy component so a warm hit cannot reuse a
legacy or differently derived data artifact for the same source bytes.

Research bundles already support subtimeframe members. Extend their metadata
with the derivation provenance and restore all new managed keys. Bundle schema
remains backward-compatible: absent fields mean legacy primary ingestion.

## 5. Regression-safety controls

This is an ingestion and persistence change, not an engine change. Apply the
project regression framework nevertheless:

1. **Additive and default-off:** no existing profile, mode, API call, YAML, or
   default behavior changes.
2. **Golden preservation:** run the full legacy golden suite in every PR. Do
   not regenerate golden files.
3. **Stable session contract:** add keys only; document each producer,
   consumer, and schema in `docs/ARCHITECTURE.md`.
4. **Schema versioning:** read v1 datasets/bundles safely; v2 writers include
   explicit derivation metadata.
5. **Fail closed:** no interpolation or lower-data fallback in the new
   complete-minute mode; malformed source cannot produce a partial canonical
   bar.
6. **Determinism:** derivation output, diagnostics ordering, hashes, and
   metadata are stable for equal normalized input.
7. **Same-PR honesty documentation:** update `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
   with volume/profile divergence, discarded incomplete minutes, and the fact
   that 15-second bars still do not recover tick ordering.
8. **Cache correctness:** exercise cold/read/read_write paths so ingestion mode
   and derivation policy cannot cross-contaminate data artifacts.

There is no new point-in-time computation: each derived parent uses only four
source bars within its own closed minute. A future-shock test is still required
to prove appending later 15-second bars cannot change already emitted parent
bars or their diagnostics.

## 6. Implementation PR plan

The minimum usable release is three focused PRs. Each is intentionally
comprehensive within one boundary, and small enough for a capable coding agent
to implement and verify without mixing engine changes.

### PR 1 — Complete 15s→1m derivation foundation

**Status:** Implemented (`thesistester/data/derive.py`, `tests/test_derive.py`)

**Title:** `Data: derive complete one-minute parents from 15-second OHLCV`

**Purpose:** Establish the tested, Streamlit-free source/parent contract before
any UI or persistence integration.

**Production scope**

- Add `thesistester/data/derive.py` and public exports as appropriate.
- Implement the typed result and complete/aligned derivation policy in §3.
- Reuse canonical validation helpers where appropriate; do not alter
  `resample_ohlcv()` semantics.
- Add a minimal provenance-builder helper only if it remains pure and is reused
  by later PRs.

**Test scope**

- Four correctly aligned 15-second bars produce one exact one-minute OHLCV bar,
  including summed volume.
- **v2 amendment:** Missing any one of the four bars retains the parent,
  reports `incomplete_coverage` in `sparse_buckets`, and leaves
  `dropped_buckets` empty.
- Offset / off-grid timestamps drop the minute with `timestamp_misalignment`.
- Duplicate timestamps and invalid source cadence fail closed.
- Multi-minute source with a middle sparse minute retains all on-grid minutes.
- Exchange-local bucketing remains correct across DST transition fixtures.
- Derived parent plus retained source passes
  `prepare_subtimeframe_conservative_context()`; fully complete fixtures still
  pass strict `prepare_subtimeframe_context()`.
- Future-shock: append future complete 15-second buckets and assert prior
  parent rows and diagnostics are unchanged.
- Existing `resample_ohlcv`, vendor loader, intrabar, and golden tests remain
  green.

**Documentation**

- Add the foundational derivation contract and incomplete-bucket caveat to
  `docs/ASSUMPTIONS_AND_LIMITATIONS.md`.
- Add a short planned boundary note to `docs/ARCHITECTURE.md`.

**Acceptance criteria**

- No UI, local-store, API, CLI, or engine behavior changes.
- Existing default test fixtures are byte-identical.
- A reviewer can verify every retained parent has exactly four aligned source
  rows from the result/diagnostic contract.

### PR 2 — Data-page single-upload workflow

**Status:** Implemented (`pages/1_Data.py` helpers + session contract)

**Title:** `Data: add explicit 15-second primary upload mode`

**Purpose:** Make the coherent one-file workflow usable in Streamlit while
keeping legacy uploads intact.

**Production scope**

- Add the explicit mode selector and mode-specific user copy to `pages/1_Data.py`.
- Parse through the selected explicit vendor profile, validate, derive, tag
  sessions, and install the session contract in §4.2 atomically.
- Render retained/dropped source counts and downloadable dropped-bucket CSV.
- Run strict R12 compatibility as an internal postcondition before state commit.
- Suppress the separate lower-timeframe uploader only for the new mode.
- Extend dataset-state clearing so no stale lower frame, provenance, diagnostics,
  backtest, grid, validation, or bundle state can survive a mode/source change.

**Test scope**

- Data-page helper tests for successful atomic parent/sub installation.
- Mode switching clears the correct dependent state.
- A partial source minute is absent from `data` and reported, while the source
  remains available only according to the locked policy.
- Legacy primary upload and legacy lower upload helpers remain unchanged.
- UI copy/selector guard tests if the project’s page tests assert labels.
- Smoke-test strict R12 context using the state produced by the new path.
- Full suite plus legacy golden master.

**Documentation**

- Update `docs/ARCHITECTURE.md` session-state table for
  `ingestion_provenance` and `derived_parent_diagnostics`.
- Update user-facing limitations and `docs/AGENT_GUIDE.md` interactive workflow
  guidance.

**Acceptance criteria**

- A user uploads one Quantower 15-second export and can immediately calculate
  1m levels/signals and select strict R12 replay.
- The prior one-minute + optional lower-file flow remains available and
  unchanged.
- No partial parent bar can appear in the new mode.

### PR 3 — Durable and headless reproducibility

**Status:** Implemented (local-store schema v2 sidecar, `app_state` restore,
RunSpec `ingestion_mode`, execution-artifact binding separation, research-bundle
provenance)

**Title:** `Data: persist and reproduce 15-second-derived datasets`

**Purpose:** Ensure the one-upload workflow remains reproducible after a local
save/restore, bundle export/import, API execution, CLI execution, and cache
reuse.

**Production scope**

- Add local-store schema v2 subtimeframe sidecar and derivation provenance.
- Add v1-compatible reads and sidecar conflict protection.
- Restore the lower source and ingestion provenance in `app_state.py`.
- Add `ingestion_mode` validation and orchestration to the R18 API/RunSpec/CLI.
- Extend execution-artifact source binding and ingestion metadata for cache
  separation.
- Extend research-bundle metadata and managed-key restoration; do not break
  pre-feature bundles or legacy `subtimeframe_path`.

**Test scope**

- Local v2 save → load → bootstrap restores exact canonical parent, source
  frame, intervals, format profile, and provenance.
- Existing v1 datasets load with no lower frame and unchanged metadata behavior.
- Saving a conflicting lower sidecar for equal canonical data fails closed.
- API/CLI one-file run reaches a strict R12 backtest without
  `subtimeframe_path`.
- Legacy API/CLI dual-file RunSpec remains valid and has unchanged results.
- Research bundle round-trip restores derived provenance and source data.
- Cache read/write tests prove mode/policy cannot share an artifact with a
  legacy or different derivation policy.
- API/CLI/Streamlit-equivalent bundle canonical projections agree on the
  derived fixture.
- Full suite, lint, and legacy golden master pass.

**Documentation**

- Update `docs/ARCHITECTURE.md` persistence topology, headless composition
  boundary, cache key contract, and session-state table.
- Update `docs/AGENT_GUIDE.md` with one-file YAML.
- Update `docs/ASSUMPTIONS_AND_LIMITATIONS.md` and, if necessary,
  `docs/ENGINEERING_ROADMAP.md` with the delivered capability and caveats.

**Acceptance criteria**

- A saved or bundled derived dataset restores with R12-ready 15-second source
  data; no re-upload is needed.
- A one-file YAML run is reproducible and exports derivation provenance.
- Legacy datasets, bundles, and RunSpecs remain readable/executable.

### PR 4 — Recommend 15s-primary (regression-safe)

**Status:** Implemented (`pages/1_Data.py` presentation + docs; no API/engine
removal)

**Title:** `Data: recommend 15-second-primary without removing legacy paths`

Focused product-surface promotion only. Engine, loaders, derive policy,
persistence schema, RunSpec semantics, cache bindings, and goldens stay
untouched.

**In scope**

- Streamlit Upload-CSV radio: 15s-primary labeled/ordered first as
  **Recommended**; one-minute primary labeled **Legacy / advanced**.
- Upload-CSV widget default selects `15s_primary_derive_1m` on first visit;
  Sample data remains the legacy one-minute fixture path.
- Upload-CSV entry realigns `data_ingestion_mode_selector` for legacy
  one-minute sessions (Sample/saved) so dual-upload stays reachable, without
  writing the selector from the Sample render branch (which would clobber the
  recommended default). Explicit radio choices are preserved. Post-radio CSV
  install sync skips rewriting the selector key when the value already
  matches (Streamlit forbids mutating a bound widget key on the same run).
- Dual-upload expander retitled **Legacy dual-upload (optional)** with
  prefer-15s-primary copy; hide rules unchanged.
- Docs mark 15s-primary as the recommended Streamlit Quantower path; legacy
  dual-file / `subtimeframe_path` remain supported.

**Out of scope (intentionally deferred)**

- Removing or disabling dual-upload / `subtimeframe_path`
- Changing API/CLI default (`ingestion_mode` absent ⇒ still `primary`)
- Auto-detecting interval/profile or expanding beyond
  `quantower_history_exporter`
- Sample-data path, engine, R12 resolvers, derive policy, dataset schema,
  cache keys, research-bundle schema, golden regeneration

## 7. Verification matrix

| Layer | Required evidence |
|---|---|
| Pure data | Deterministic 4→1 aggregation, complete coverage gate, gap/DST/future-shock tests |
| R12 integration | `prepare_subtimeframe_context(derived_parent, source_15s)` passes |
| Streamlit | Helper/page tests prove atomic state installation and legacy-path preservation |
| Persistence | v1 read compatibility, v2 sidecar round trip, sidecar conflict refusal |
| Headless | One-file API/CLI parity with an equivalent explicit parent/sub run |
| Cache | Distinct derivation mode/policy cannot warm-hit an incompatible artifact |
| Regression | Full pytest, Ruff, and legacy golden-master test green on every PR |

No golden regeneration is authorized by this plan. If any legacy golden output
changes, treat it as a regression and stop the implementation until the cause
is resolved.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| User expects vendor 1m volumes/profiles to remain unchanged | Label derived 1m as a new research contract; record source/derivation provenance and document non-comparability. |
| Data gaps silently create distorted parent bars | Emit parents only from exactly four expected source opens; report and drop all other buckets. |
| Source boundaries include a partial first/last minute | Drop them deterministically; never fall back to a partial canonical parent. |
| State loses R12 data after local restore | Schema v2 sidecar + bootstrap restoration is part of PR 3, not deferred. |
| Cache returns a legacy artifact | Bind ingestion mode and derivation policy into source-index/cache metadata and test it. |
| Scope expands into engine behavior | Keep `simulate_trades`, R12 resolver logic, and golden fixtures untouched; the parent/sub contract is prepared before calling them. |
| User asks to remove dual upload too early | Keep removal optional until the one-file path has durable persistence and validated product usage. |

## 9. Definition of done

The project is complete when a supported 15-second export can be uploaded once,
derive only fully covered one-minute canonical bars, run strict R12 replay using
the same retained source, survive local save/restore and bundle import/export,
and execute headlessly from a one-file RunSpec. All legacy workflows and
golden-master outputs must remain unchanged.
