# Quality investigation (QI)

Per-slice reports and the machine-readable finding registry for
[`docs/QUALITY_INVESTIGATION_PLAN.md`](../QUALITY_INVESTIGATION_PLAN.md).
This directory is the only tracked-file destination for QI-1…QI-15
reports. QI-0 also added the informational harness below. QI-15 added
[`QUALITY_REMEDIATION_PLAN.md`](../QUALITY_REMEDIATION_PLAN.md) at the docs root.

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

## Reports (QI-0…QI-15)

Landed slice reports. Investigation is **Completed**; living status SoT is
[`ENGINEERING_ROADMAP.md`](../ENGINEERING_ROADMAP.md). Remediation is
[`QUALITY_REMEDIATION_PLAN.md`](../QUALITY_REMEDIATION_PLAN.md) (QR).

| Report | Slice |
|---|---|
| [`QI-00_BASELINE.md`](QI-00_BASELINE.md) | QI-0 harness + measured baseline |
| [`QI-01_DATA_INGESTION.md`](QI-01_DATA_INGESTION.md) | QI-1 data ingestion |
| [`QI-02_LEVELS_ENGINE_PIT.md`](QI-02_LEVELS_ENGINE_PIT.md) | QI-2 levels / engine PIT |
| [`QI-03_SETUP_SIGNALS_OTF.md`](QI-03_SETUP_SIGNALS_OTF.md) | QI-3 setup / signals / OTF |
| [`QI-04_EXECUTION_ENGINE.md`](QI-04_EXECUTION_ENGINE.md) | QI-4 execution engine |
| [`QI-05_ANALYTICS_VALIDATION_BATTERIES.md`](QI-05_ANALYTICS_VALIDATION_BATTERIES.md) | QI-5 analytics / validation / batteries |
| [`QI-06_HEADLESS_FACADE.md`](QI-06_HEADLESS_FACADE.md) | QI-6 headless facade |
| [`QI-07_STUDY_SYSTEM.md`](QI-07_STUDY_SYSTEM.md) | QI-7 Study system |
| [`QI-08_TRADE_JOURNAL.md`](QI-08_TRADE_JOURNAL.md) | QI-8 trade journal |
| [`QI-09_RESEARCH_ASSISTANT_VOICE.md`](QI-09_RESEARCH_ASSISTANT_VOICE.md) | QI-9 Research Assistant / voice |
| [`QI-10_UI_SESSION_STATE.md`](QI-10_UI_SESSION_STATE.md) | QI-10 UI / session state |
| [`QI-11_TEST_SUITE_QUALITY.md`](QI-11_TEST_SUITE_QUALITY.md) | QI-11 test-suite quality |
| [`QI-12_TOOLING_CI_SECURITY.md`](QI-12_TOOLING_CI_SECURITY.md) | QI-12 tooling / CI / security |
| [`QI-13_DOCS_CONTRACTS_DRIFT.md`](QI-13_DOCS_CONTRACTS_DRIFT.md) | QI-13 docs / contracts drift (includes QI-13-05) |
| [`QI-14_PERFORMANCE_ENVELOPE.md`](QI-14_PERFORMANCE_ENVELOPE.md) | QI-14 performance envelope |
| [`QI-15_SYNTHESIS.md`](QI-15_SYNTHESIS.md) | QI-15 synthesis (historical; QR Rev 2 is the remediation SoT) |
| [`findings.csv`](findings.csv) | Finding registry (plan §3.3 fields + QR disposition columns) |

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

QI-15 added `merge_group,score,qr_workstream,disposition` (see Reports
table). Slice reports do not invent further columns; QR owns disposition
updates.

ISO 25010 tokens (plan §A.5): `functional_suitability` ·
`performance_efficiency` · `compatibility` · `usability` ·
`reliability` · `security` · `maintainability` · `portability`.
