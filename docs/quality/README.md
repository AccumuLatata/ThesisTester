# Quality investigation (QI)

Per-slice reports and the machine-readable finding registry for
[`docs/QUALITY_INVESTIGATION_PLAN.md`](../QUALITY_INVESTIGATION_PLAN.md).
This directory is the only tracked-file destination for QI-1…QI-14.
QI-0 also added the informational harness below. QI-15 may add
`docs/QUALITY_REMEDIATION_PLAN.md` at the docs root.

**Research-only.** Slices do not edit product code, tests, fixtures, or
living docs. Metrics are investigation triggers, not findings
(plan §4.4). No evidence → not a finding.

## Harness (QI-0)

| Path | Role |
|---|---|
| [`scripts/quality_metrics.py`](../../scripts/quality_metrics.py) | Reproduces plan §A.1 counters (`radon` CC/MI, `vulture`, `rg` smells, LOC) plus the exclusive module → slice ownership map. JSON to stdout or `--output`. **Informational; no CI job.** |
| [`findings.csv`](findings.csv) | Registry. Header = plan §3.3 fields. Each slice appends only rows with its own `id` prefix. QI-0 ships the header only (zero findings). |
| [`QI-00_BASELINE.md`](QI-00_BASELINE.md) | Measured baseline on the audited `main` (post-#478). SoT for later slices; do not copy plan §4's `e82c2a9` snapshot blindly. |

```bash
# from repo root; requires radon, vulture, rg on PATH
python scripts/quality_metrics.py --output /tmp/qi-metrics.json
```

Coverage XML, pytest durations, `pip-audit`, `bandit`, and `mypy` stay
under `/tmp` (plan §5 QI-0 / §A.1). They are not produced by this
script.

## Report naming

`QI-<nn>_<SLUG>.md` (two-digit slice id). Follow plan §3.4. Probe
scripts live under `/tmp` and are pasted into the report; do not commit
them.

## Synthetic fixture recipes (throwaway; never commit)

Later slices need deterministic inputs that are **not** desk data and
**not** a committed golden. Generate them under a throwaway
`THESISTESTER_STORE_DIR` (always `/tmp/…`). Do not use real API keys.

These recipes describe how to *regenerate* probes. They are not a
correctness claim about any backtest, metric, or Study.

### Shared isolation

```bash
export THESISTESTER_STORE_DIR=/tmp/qi-store-$$
mkdir -p "$THESISTESTER_STORE_DIR"
unset OPENAI_API_KEY XAI_API_KEY
```

### Canonical 1-minute OHLCV (QI-1 / composer-parity)

Match `sample_data/ES_sample_1m.csv` columns
(`timestamp,open,high,low,close,volume`), exchange-local naive stamps,
strict `H >= max(O,C)` / `L <= min(O,C)`, non-negative volume. Keep the
file tiny (one RTH session is enough for ingest probes).

Deliberate single-defect variants for QI-1 (one defect per file):

- missing bar (gap > 3× inferred interval)
- duplicate timestamp
- `high < low`
- negative volume
- mixed UTC / exchange-local offsets
- 15s stamps not aligned to the parent-minute grid

Vendor-shaped copies (semicolon History Exporter, NinjaTrader,
Sierra, Databento trades) should follow the committed *shape* under
`tests/fixtures/vendor/` without copying those fixtures into
`docs/quality/`.

### 15s-primary (QI-1)

Quantower History Exporter header
(`Time left;Time right;Open;High;Median;Low;Close;Typical;Volume;…`).
Four on-grid 15s rows per parent minute. One file with a single
misaligned `Time left` for the fail-closed path.

### Tick Last×Volume (QI-2 / QI-1 attach)

Minimal Quantower tick-last CSV covering one A-period and one prior
session. Enough for `APOC requires ticks` / `rolling POC requires ticks`
refusals. Do not commit broker exports.

### Drift-VWAP HTF (QI-3 / H14 status)

Two sessions of 1-minute bars where session VWAP trends so a developing
partner at an HTF trigger is *stale* relative to `base_end`. Status
re-verification only; do not re-audit 3c math (`AUDIT_FINAL` S3 locked).

### Two-candidate overlap (QI-4 / H5 status)

Two same-bar opposite-direction candidates under default `allow_all`.
Used to observe disclosure, not to declare P&L correct.

### Journal synthetic (QI-8)

Reuse the *idea* of `tests/fixtures/journal/tradesviz_executions_synthetic.csv`
(UTC executions, no account identifiers). Never copy real AMP PDFs or
TradesViz desk exports into `/tmp` probes that might be pasted into a
report.

### Realistic timing envelope (QI-14 / §3.2 item 8)

Regenerate the CAI `realistic` fixture via
`tests/fixtures/cai_baseline.py` (`write_cai_bars(..., kind="realistic")`)
into `/tmp`. Compare wall time / peak RSS to `docs/SIMULATE_PERF.md` /
`docs/CAI_BASELINE.md`. Informational only.

### Adversarial bundle zips (QI-6)

Build under `/tmp`: path-traversal member, zip-bomb size, foreign
parquet schema, missing manifest, tampered hash. Fail-closed
expectations are application-quality checks, not a security-finding
shortcut — QI-6 records outcomes.

## Finding registry

`findings.csv` columns are the plan §3.3 record fields (UTF-8, quoted as
needed):

`id,axis,classification,severity,confidence,blast_radius,iso25010,files_symbols,repro_or_reasoning,expected,observed,impact,regression_surface,remediation_direction,tests_required_later,docs_required_later,locked_by,handoff_to,prior_id`

QI-15 may add `merge_group,score,qr_workstream,disposition` later. Do
not add those columns in QI-1…QI-14.

ISO 25010 tokens (plan §A.5): `functional_suitability` ·
`performance_efficiency` · `compatibility` · `usability` ·
`reliability` · `security` · `maintainability` · `portability`.
