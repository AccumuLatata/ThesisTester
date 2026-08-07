# Golden-master fixtures

Operational spec for the golden-master mechanism required by
`docs/ENGINEERING_PROPOSAL.md` §4 rule 2 and §4.1. It is the load-bearing regression
control for the invasive engine milestones (R12 look-inside-bar, R13 break-even/trailing
exits) and for the R22 core-surface refactor.

**Status:** active. The deterministic NQ fixture, legacy trades, readable CSV,
manifest, canonical bundle hash, recorder, and verification tests were recorded
from unmodified post-R18 `main` before R12 engine work. Any future output change
must follow the regeneration policy in §4.

---

## 1. Scope

- Goldens cover **legacy mode only**: every new capability ships default-off (§4 rule 3),
  so the recorded outputs are exactly what today's `main` produces with default keyword
  arguments. A milestone that changes behavior *only when its new flag is enabled* leaves
  goldens untouched — that is the whole point of the gate.
- Goldens are deliberately **minimal**: one small synthetic dataset. They prove "legacy
  path unchanged", not "engine is correct" (unit tests do that). Small scope keeps
  legitimate improvements unblocked (§7 brittleness risk).

## 2. Files

### 2.1 Legacy-mode family (default-off / OTF-disabled gate)

| File | Role |
|---|---|
| `dataset_nq_1m_small.parquet` | Input fixture: synthetic NQ 1-minute OHLCV covering a few RTH sessions. Written by the recorder; never edited by hand. |
| `fixture_manifest.json` | Provenance: recorder version, generator parameters (seed, session count, tick size, point value), engine call arguments, recording environment (Python/pandas/numpy/pyarrow versions). |
| `trades_legacy.parquet` | Recorded legacy-mode trade frame for that input (primary comparison artifact). |
| `trades_legacy.csv` | Canonical text projection of the same frame — the readable diff required by the regeneration policy (§4 below) and the hash input (§3). |
| `legacy_bundle_hash.txt` | `sha256` of the canonical research-bundle projection plus the `pandas_major` it was recorded under (see §3.2). |

The deterministic generator in `tests/fixtures/golden/generate.py` produces
the input fixture, and `record_golden.py` runs the frozen pipeline, so every
artifact can be rebuilt from source rather than trusted as an opaque blob.

### 2.2 Enabled-OTF family (hardening PR 3)

Additive drift gate for **enabled** OTF behavior. Isolated from the legacy
family: these files never rewrite legacy artifacts, and `tests/test_otf_golden.py`
asserts legacy trades remain reproducible.

| File | Role |
|---|---|
| `generate_otf_enabled.py` | Overnight 1-minute NQ generator + fixed long/short candidates (up/down/unknown-or-neutral regimes; crosses midnight and 18:00 ET). Candidate `bar_index` is the dataset positional index of `timestamp` so OTF decisions and next-bar entries stay aligned. |
| `pipeline_otf_enabled.py` | Shared enabled-OTF composition (`apply_configured_otf_filter` → `simulate_trades`). |
| `record_otf_enabled_golden.py` | Recorder (`--confirm-regenerate` required). |
| `otf_enabled_dataset.parquet` | Recorded overnight source frame. |
| `otf_enabled_accepted_signals.csv` | Canonical accepted-signal projection. |
| `otf_enabled_rejected_signals.csv` | Canonical rejected-signal projection with reasons. |
| `otf_enabled_trades.csv` | Canonical accepted-trade projection. |
| `otf_enabled_projection.json` | Reviewable identity projection (config, hash, IDs, reasons, counts). |
| `otf_enabled_manifest.json` | Provenance for the enabled-OTF family. |

Regenerate enabled-OTF artifacts with:

```bash
python -m tests.fixtures.golden.record_otf_enabled_golden --confirm-regenerate
```

### 2.3 Enabled entry_window family (SW2)

Additive drift gate for **enabled** `entry_window` admission. Isolated from
legacy and OTF families: these files never rewrite those artifacts.

| File | Role |
|---|---|
| `generate_entry_window_enabled.py` | RTH morning fixture + fixed next-bar candidates straddling `rth_open_30m` |
| `pipeline_entry_window_enabled.py` | `simulate_trades(..., entry_window=..., return_result=True)` |
| `record_entry_window_enabled_golden.py` | Recorder (`--confirm-regenerate` required) |
| `entry_window_enabled_dataset.parquet` | Recorded 1m source frame |
| `entry_window_enabled_trades.csv` | Canonical accepted-trade projection |
| `entry_window_enabled_skipped.csv` | Canonical `outside_entry_window` skips |
| `entry_window_enabled_projection.json` | Reviewable IDs/counts/config |
| `entry_window_enabled_manifest.json` | Provenance |

Regenerate with:

```bash
python -m tests.fixtures.golden.record_entry_window_enabled_golden --confirm-regenerate
```

## 3. Determinism contract (measured, not assumed)

Two properties were verified on this repository before writing this spec. Both shape the
comparison design; ignoring either would make the gate flaky and therefore useless.

### 3.1 Value equality is the primary assertion — not byte equality

`pandas`-level identity of the same logical frame is **not** stable across pandas majors.
Measured with `thesistester.persistence.local_store._hash_dataframe` on one fixed
5-column frame (tz-aware timestamps, ints, floats, strings):

| Environment | Timestamp dtype | String dtype | Frame hash |
|---|---|---|---|
| Python 3.10 / pandas 2.3.3 | `datetime64[ns, America/New_York]` | `object` | `e81ac4a3…8629` |
| Python 3.11 / pandas 3.0.5 | `datetime64[us, America/New_York]` | `str` | `2e7817a4…4649` |
| Python 3.12 / pandas 3.0.5 | `datetime64[us, America/New_York]` | `str` | `2e7817a4…4649` |

Parquet payload bytes differ for the same reason (3712 vs 3697 bytes). Consequences for
the golden tests, which run on the full CI matrix (3.10/3.11/3.12):

1. The trade-frame assertion compares **values**, via
   `pandas.testing.assert_frame_equal(recorded, produced, check_dtype=False, check_exact=True)`
   after a canonicalization step: sort by `(entry_bar_index, signal_id)`, reset index,
   assert identical column *sets and order*, and coerce datetime columns to UTC
   microsecond precision. Floats are compared exactly — R multiples and prices come from
   deterministic arithmetic, so tolerance would hide real drift.
2. Column dtypes are asserted separately against a canonical dtype *family* map
   (integer / float / boolean / string / datetime-with-tz), so a pandas-version dtype
   rename (`object` → `str`) does not fail the gate while a genuine
   `float` → `object` regression does.
3. Never assert on parquet bytes.

### 3.2 The research-bundle hash must be taken over a canonical projection

`thesistester.research_bundle.build_research_bundle` stamps `created_at`
(`datetime.now(timezone.utc)`) into `manifest.json` and writes zip entries with local
timestamps, so raw bundle bytes are not reproducible even within one process — two calls
on identical session state produced `62653c4a…d0fd` and `ee1a0583…10b8`.

`legacy_bundle_hash.txt` therefore records the `sha256` of a **canonical projection**:

- every bundle member is hashed by content, keyed by filename, in sorted filename order;
- JSON members are re-serialized with `sort_keys=True` after dropping `manifest.created_at`;
- DataFrame members are hashed with `local_store._hash_dataframe` (the repo's existing
  deterministic convention) rather than by their parquet bytes.

Because that convention is pandas-major-sensitive (§3.1), the file also records the
recording `pandas_major`. The hash assertion runs only when the executing environment's
`pandas_major` matches the recorded one, and is skipped (not failed) otherwise; frame
value-equality still gates every matrix cell. A pandas major bump thus produces a normal
red-then-regenerate decision rather than an unexplained CI failure.

R18 implements this projection as
`thesistester.research_bundle.canonical_bundle_hash()`. CLI parity and
serial/parallel determinism tests use that shared helper; callers must not
replace it with a raw ZIP hash.

## 4. Regeneration policy (§4.1 rule 3)

Golden outputs are **never** silently re-recorded.

1. Intentional behavior changes land behind a new default-off flag; legacy goldens stay
   byte-for-byte valid, so no regeneration is needed.
2. If a **legacy** golden genuinely must change, that change lands in its **own PR** containing:
   - the reason and the regression justification;
   - the readable `trades_legacy.csv` diff (never only the parquet);
   - the updated `fixture_manifest.json` recording environment;
   - nothing else — no feature work in a regeneration PR.
3. That legacy-regeneration PR must carry the **`GOLDEN_REGEN`** label and reviewer
   approval. The `golden-master regeneration guard` job in `.github/workflows/ci.yml`
   fails any PR that modifies the **legacy** artifact set
   (`dataset_nq_1m_small.parquet`, `trades_legacy.*`, `legacy_bundle_hash.txt`,
   `fixture_manifest.json`) without the label. Additive families such as
   `otf_enabled_*` are not blocked by that label requirement, but still require an
   explicit `--confirm-regenerate` recorder run and a readable projection diff.
4. Regeneration commands:
   - Legacy: `python -m tests.fixtures.golden.record_golden --confirm-regenerate`
   - Enabled OTF: `python -m tests.fixtures.golden.record_otf_enabled_golden --confirm-regenerate`

   Both refuse to write any files without the flag.

## 5. Repository plumbing

`.gitignore` excludes `*.parquet` repo-wide (research exports must never be committed).
Golden parquet fixtures are explicitly re-included via
`!tests/fixtures/golden/*.parquet`, so recording a fixture cannot silently fail to be
committed.

## 6. Recording status

- [x] Deterministic generator committed; fixture rebuildable from it.
- [x] `trades_legacy.parquet` + `trades_legacy.csv` + `fixture_manifest.json` +
      `legacy_bundle_hash.txt` recorded from unmodified `main`.
- [x] `tests/test_golden_master.py` asserts trade-frame value equality on every matrix
      cell and bundle-hash equality on the recorded `pandas_major`.
- [x] Fixture deliberately exercises six same-bar both-hit trades resolved by
      legacy SL-first behavior, so perturbing that rule makes the value gate red.
- [x] `docs/ENGINEERING_ROADMAP.md` and `docs/AGENT_GUIDE.md` reference the active gate.
- [x] Enabled-OTF additive family recorded (`otf_enabled_*`) with overnight ETH
      session coverage, accepted/rejected populations, rejection reasons, trades,
      future-shock tests, and legacy-isolation assertions (`tests/test_otf_golden.py`).
