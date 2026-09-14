# ThesisTester Research Report

## Metadata
- Generated at: 2026-06-02T00:00:00+00:00
- App: ThesisTester
- Schema version: 1.0

## Setup Configuration
- Instrument: ES
- Setup name: Phase9 setup
- Selected levels: ONH, ONL
- Trigger: touch
- Direction: both
- Naked only: False
- Confluence settings: min=2, max=4, tolerance_ticks=4.0

## Signal Summary
- Signal count: 2
- Signal table rows exported: 2

## Backtest Summary
- Trade count: 2
- Win rate: 50.0%
- Avg R: 0.2500
- Total R: 0.5000
- Profit factor: 2.0000
- Max drawdown R: 0.5000

### Intrabar Resolution
- Model: path_open_proximity
- Same-bar both-hit exits: 2
- Residual ambiguous resolutions: 1
- Lower-data fallback parent bars: 0
- Lower-data fallback exits: 0
- Deterministic OHLC paths are assumptions, not reconstructed market paths.

### Exit Management
- Break-even after R: 1.0
- Trailing after R: 1.5
- BE exits: 1
- TRAIL exits: 1

## Walk-Forward / OOS Diagnostics
- Fold mode: sessions
- Window mode: rolling
- Valid folds: 1
- Median OOS expectancy R: 0.2000
- Median expectancy retention ratio: 0.5000
- Stitched OOS total R: 1.0000
- Stitched OOS status: ok

## Overfitting-Detection Battery
- PBO: 25.0%
- Deflated Sharpe probability: 40.0%
- Vs-random p-value: 0.1000
- CSCV, DSR, and vs-random are diagnostics on declared historical trials/nulls, not proof of future edge.

### Advanced Risk Metrics
- Sharpe-like R: 0.5000
- Sortino-like R: 0.7500
- Ulcer index R: 0.2500
- Recovery factor: 1.0000
- Tail ratio: 1.2000
- Outlier dependency ratio: 0.8000

## Grid Search Summary
- Grid rows exported: 2
- Best SL ticks: 4.0
- Best TP ticks: 8.0
- Best metric: expectancy_r = 0.2000

## Time Analysis Summary
- Grouped summary rows exported: 2

## Validation Diagnostics
⚠️ Diagnostic only — not a significance test and not proof of edge.

- Bootstrap CI: [-0.1000, 0.6000]
- P(mean R > 0): 77.0%
- Permutation p-value (positive): 0.0800
- Trade-count status: insufficient
- Grid overfit risk: low

## Excursion Analytics
⚠️ Diagnostic only — terminal bar-level MAE/MFE cannot prove intrabar order.

- Trades with excursions: 2
- Mean MAE (R): 0.7500
- Mean MFE (R): 1.5000
- Mean edge ratio: 2.0000
- Median edge ratio: 2.0000
- Calibration both-hit rule: stop_first
- Grouped summary rows exported: 2
- Calibration grid rows exported: 1

## Monte Carlo Path Robustness
⚠️ Diagnostic only — resamples the realized trade sequence and does not prove edge.

- Trades: 2
- Simulations per method: 50
- Methods: reshuffle
- reshuffle: observed final R 0.5000, P95 max DD 0.5000, P95 loss streak 1

## Price-Series Noise Test
⚠️ Diagnostic only — perturbs OHLC input and reruns the full pipeline; it does not prove edge.

- Replicas: 50
- Noise: 0.05 × atr
- P50 expectancy R: 0.2000
- P50 trade persistence: 60.0%

## Parameter Sensitivity (SPP-lite)
⚠️ Diagnostic only — local one-at-a-time execution-parameter changes do not measure interactions or prove edge.

- Parameters profiled: 1
- Fragile parameters: 1
- Baseline expectancy R: 0.2000

## Entry Window (Focus / Admit)
- Status: not available (no Focus/Admit window data in session)

## OTF Filter
- Status: not available (no OTF filter data in session)

## Caveats
- Research output only; not trading advice.
- Backtests are based on historical data and assumptions.
- OHLC bars cannot reveal true intrabar event order; selected deterministic models are assumptions, and lower-timeframe replay retains residual within-sub-bar ambiguity.
- Grid search can overfit; validation diagnostics are descriptive only.
- No guarantee of future performance.
