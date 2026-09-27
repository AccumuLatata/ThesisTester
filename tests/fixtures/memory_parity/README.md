# MW0 memory-parity suite

New golden suite for the worker-memory (MW) series. **The legacy golden set
under `tests/fixtures/golden/` is not rewritten.** Do not edit
`tests/fixtures/golden/README.md` (byte-locked by
`test_existing_golden_files_byte_identical`). Regeneration of
`trades_legacy.*` / `legacy_bundle_hash.txt` is out of scope here.

Plan: `docs/WORKER_MEMORY_IMPLEMENTATION_PLAN.md` §9. Pointer:
`docs/ENGINEERING_PROPOSAL.md` §4.1.

## What this directory holds

| Path | Role |
|---|---|
| `capture_operator.py` | §9.3 operator script: UTC-slice the farm Quantower 15s MNQ CSV, run the six short cells and/or the full reference cell, write a §9.1 capture |
| `compare.py` | Bit-identical compare of two capture dirs (full MW equality or `--pre-step`) |
| `stage_trace.py` | §8 Linux-only stage-trace harness (flag off, one process, no 50 replicas) |
| `record_memory_parity.py` | Synthetic-fixture recorder. Compare-only unless `--regenerate` |
| `synthetic_mnq_15s.csv` | Committed multi-day 15s CI fixture |
| `synthetic_golden/` | Recorded CI captures (prepare + one replica, plus cell-6 shape) |
| `farm_reference/full/` | Official Linux-farm full reference cell (`cells/` + `manifest.json`) |
| `farm_reference/short/` | Official Linux-farm six short cells (`cells/` + `manifest.json`) |
| `farm_reference.sha256` | SHA-256 lock of official `farm_reference/` bytes (outside that tree) |

## Official farm captures (`farm_reference/`)

Linux-farm only. Captured with `capture_operator` (tooling `898beccf`,
the #601 tip; squash-merged to `main` as `a1ea25b2`) against `main`
`ddf9fcbe`, flag off, one process, full MNQ 15s Quantower CSV. Layout is
the compare root (`cells/` + `manifest.json`) so `compare.py` can take
these directories directly. `*.parquet` is `binary` in `.gitattributes`
so Git does not apply text/CRLF conversion to the official frames.

| Tree | When | Result |
|---|---|---|
| `full/` | 2026-09-26 | 59 trades, E=`0.0805084745762712`, portable hash `b8ff7982…`. Bit-identical to an independent `59a4652` rerun |
| `short/` | 2026-09-27 | trade_count `17 / 75 / 21 / 16 / 0 / 0`. Cell 6 is zero, as required |

These bytes are the Linux baseline. macOS must record and compare against
**its own** baseline. Last-bit `EMA_*` splits in `levels.parquet` /
`naked_flags.parquet` fail the portable hash across machines.

Verify the committed tree (does not rewrite fixtures):

```bash
( cd tests/fixtures/memory_parity/farm_reference && sha256sum -c ../farm_reference.sha256 )
```

Slice CSVs are **not** committed (~29 MB). The `--cells short`
invocation in the next section writes them under
`<output-dir>/slices/` (`slice_csv.py` is the helper; it is not a
standalone CLI).

Do not rewrite the legacy golden set under `tests/fixtures/golden/`.
Do not edit `tests/fixtures/golden/README.md`.

### Re-capture and compare (farm, Linux)

```bash
# full reference
python -m tests.fixtures.memory_parity.capture_operator \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-dir /path/to/mw0_capture_full \
  --cells full \
  --run-label farm-main-full

python -m tests.fixtures.memory_parity.compare \
  tests/fixtures/memory_parity/farm_reference/full \
  /path/to/mw0_capture_full

# six short cells
python -m tests.fixtures.memory_parity.capture_operator \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-dir /path/to/mw0_capture_short \
  --cells short \
  --run-label farm-main-short

python -m tests.fixtures.memory_parity.compare \
  tests/fixtures/memory_parity/farm_reference/short \
  /path/to/mw0_capture_short
```

One process. Do not set `THESISTESTER_MEMORY_PATH` when recording the
flag-off reference. Do not touch the farm production checkout
`~/thesistester` at `59a4652`. If any field differs: **stop and report**.
Do not loosen a tolerance or regenerate these fixtures to make a check
pass.

## Capture contents (§9.1)

For every cell the operator / recorder writes:

- `trades.parquet` — every column; numeric dtypes and timezone preserved.
  Datetime columns are stored as `datetime64[ns, tz]` (pandas 2 ns /
  pandas 3 us are normalized; conversion that loses an instant aborts)
- `trades_dtypes.json` — column dtype/unit/tz sidecar (after ns canonicalize)
- `replica_expectancies.json` — ordered in-memory list from
  `vs_random_benchmark`, float64 bits as hex. **Not persisted in product
  bundles.** Captured by an import-time wrap of `vs_random_benchmark`
  (no product-code edit). Required on `59a4652`, whose bundles also omit
  this list.
- `summary.json` — `trade_count`, `expectancy_r`, `total_r`,
  `max_drawdown_r`, `profit_factor`, `win_rate` (floats as hex bits)
- `da5.json` — `random_null_expectancy_r`, `random_null_std_r`,
  `random_p_value_ge`, `expectancy_minus_null_r`
- `ledger.json` — `status`, `error`, `bundle_path`, plus wall-clock
  `started_at` / `finished_at` (stored; **not** part of equality)
- `canonical_bundle_hash.txt` — portable digest: the product zip walk
  after parquet datetime units are normalized to ns (`str`/`object`
  labels collapsed when every non-null value is a Python `str`; 0-row
  frames hash column names only). Product identity strings that
  `hash_dataframe` / `hash_source_frame` embed in JSON
  (`data_content_hash`, `dataset_id`, `source_content_hash`) are
  rewritten from those portable parquet digests — they are the same
  pandas-major leak, not a second source of truth. The raw product
  `canonical_bundle_hash` is stored on `meta.json` as
  `product_canonical_bundle_hash` (pandas-major-specific; not the gate).

Equality is bit-identical. Float64 compared as bits. `NaN` equals `NaN`.
Datetime instants and tz must match after ns canonicalize. No tolerance.
References are not regenerated to make a check pass.

## Short cells (§9.2)

UTC slice of the farm file, inclusive start `2024-08-01 00:00:00+00:00`,
exclusive end `2024-10-01 00:00:00+00:00`. Saved once. Cell 6 is a further
cut `[2024-08-01, 2024-08-04)`. Do not cut on `America/New_York` midnight.

All six: MNQ, `15s_primary_derive_1m`, `subtimeframe_conservative`,
`tolerance_ticks: 10`, `min_valid_confluences: 1`, `naked_only: false`,
commission 0.5 / slippage 1 tick, flatten 16:00 `America/New_York`,
grid / validation / walk-forward off, `n_replicas=50`, `random_state=42`,
`anchor_rules`, `direction: both`, `single_position`.

| # | Policy | Notes |
|---|---|---|
| 1, 3, 4, 6 | `raise` | If one of these raises, stop and report. Do not switch the policy |
| 2, 5 | `legacy` | Engine default; both can emit a same-bar opposite pair |

Cell 6 must produce 0 trades. If it does not, the slice is wrong; do not
record it.

## CI git gates (fail-closed)

`tests/test_memory_parity.py` audits hook names at `59a4652` and asserts
`thesistester/` plus `tests/fixtures/golden/` are untouched versus
`origin/main`. Shallow CI clones often lack those objects. The helpers in
`gitref.py` fetch `origin/main` and the full farm SHA
(`59a4652cdb96ac86da6675633fd57f3e31f803e0`). If a fetch cannot run, the
test **fails** with `STOP AND REPORT`. It does not skip. A stale local
`main` is never used for the untouched-package gate.

## Hook points (current main and `59a4652`)

Verified by reading `59a4652` (farm production, ~255 commits behind main).
Every hook used by these scripts exists there under the same name:

- `thesistester.analytics.overfitting.vs_random_benchmark`
- `thesistester.study.execute.execute_study_cell` / `run_study` /
  `prepare_study_expansion` / `random_baseline_fields`
- `thesistester.api._load_15s_primary_experiment_data` (load-time
  `prepare_subtimeframe_conservative_context` call)
- `thesistester.api.generate_signals` / `run_experiment`
- `thesistester.engine.intrabar.prepare_subtimeframe_conservative_context`
- `thesistester.engine.backtest.simulate_trades`
- `thesistester.research_bundle.build_research_bundle` /
  `canonical_bundle_hash`

Import-time feature detection fails closed if a name is missing.

## Farm invocations

Run from the **MW0 checkout** (this PR). One process. Do not set
`THESISTESTER_MEMORY_PATH` (the flag does not exist yet). Do not touch the
farm production checkout `~/thesistester` at `59a4652`. Use a **separate
worktree** and a **separate output directory**. Wait until the running
study batch finishes.

### 1. Current-main full reference cell

```bash
python -m tests.fixtures.memory_parity.capture_operator \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-dir /path/to/mw0_capture_main \
  --cells full \
  --run-label farm-main-full
```

### 2. `59a4652` full reference cell (separate worktree)

```bash
git -C /path/to/thesistester fetch origin
git -C /path/to/thesistester worktree add /path/to/thesistester-59a4652 59a4652

PYTHONPATH=/path/to/thesistester-59a4652:/path/to/mw0-checkout \
  python -m tests.fixtures.memory_parity.capture_operator \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-dir /path/to/mw0_capture_59a4652 \
  --cells full \
  --run-label farm-59a4652-full
```

`PYTHONPATH` puts `59a4652` first so `import thesistester` is that commit,
then the MW0 checkout so `tests.fixtures.memory_parity` is this tooling.

`python -m` from this checkout would otherwise put cwd at `sys.path[0]`
and shadow that worktree (silent main-vs-main capture). The operator
lifts the first `PYTHONPATH` tree that contains `thesistester/` ahead of
cwd, records the imported root on `meta.json`, and **stops** if the
imported package is not that tree.

### 3. Compare (pre-step subset)

```bash
python -m tests.fixtures.memory_parity.compare \
  /path/to/mw0_capture_59a4652 \
  /path/to/mw0_capture_main \
  --pre-step
```

`--pre-step` **gates** trades (every column including
`exit_subbar_timestamp`, dtypes, tz, datetime unit after ns
canonicalize), `replica_expectancies` bits (order, `NaN==NaN`),
`trade_count`, and `expectancy_r`. Known result: 59 trades, E=0.0805.
DA5 and `canonical_bundle_hash` are printed as `INFO` and do not fail
the pre-step.

Full MW equality (later MW0 record, same commit, both sides current-main):

```bash
python -m tests.fixtures.memory_parity.compare \
  /path/to/mw0_capture_a \
  /path/to/mw0_capture_b
```

That gates trades, replica bits, summary, DA5 (non-null where the
reference is non-null), ledger `status`/`error`/`bundle_path`, and the
portable `canonical_bundle_hash`. Ledger wall-clock timestamps are
excluded. The hash gate stays bit-strict on values; only the pandas
major datetime-unit (and all-string `str` vs `object`) label is
canonicalized before hashing. Last-bit float differences (the farm
Mac/Linux `EMA_*` split in `levels.parquet` / `naked_flags.parquet`)
**fail** the hash. Comparisons are same-machine against that machine's
own baseline. Identity JSON strings
(`data_content_hash` / `dataset_id` / `source_content_hash`) are
rewritten only inside `research_identity.json`, `dataset_meta.json`,
and `subtimeframe_meta.json`; the same key in any other member is a
real field and still fails.

### 4. §8 stage trace (Linux, after the pre-step passes)

Reset is **after the load-time prepare returns**, not after `R_load`
(owner addition). The wrapper drops the discarded map and `gc.collect()`s
**before** writing `5` to `/proc/self/clear_refs`, so VmHWM excludes that
map. `R_pre_prepare.hwm` is taken immediately before that prepare call.
`R_load.hwm` and every later `hwm` start from the reset.

```bash
python -m tests.fixtures.memory_parity.stage_trace \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-json /path/to/mw0_stage_trace.json \
  --run-label farm-main-stage-trace
```

Stops after `R_done`. Does not run the 50 replicas. JSON includes GiB
values, `map_step`, the §8.1 rule, and §8.2 `B`.

### 5. Six short cells (current main)

```bash
python -m tests.fixtures.memory_parity.capture_operator \
  --csv /path/to/MNQ_15s_quantower.csv \
  --output-dir /path/to/mw0_capture_short \
  --cells short \
  --run-label farm-main-short
```

The script writes the two-month UTC slice once under
`<output-dir>/slices/`, then the cell-6 three-day slice from that file.

## Synthetic recorder (CI)

```bash
# compare-only (default)
python -m tests.fixtures.memory_parity.record_memory_parity

# write the committed synthetic golden (this PR's base commit only)
python -m tests.fixtures.memory_parity.record_memory_parity --regenerate
```

If any check cannot be run or any parity differs: **stop and report**.
Do not loosen a tolerance, regenerate a reference, or switch a policy.
