# Chart Visualization Engineering Rollout

## Phase 1 foundation (this PR)

This change set introduces a regression-safe visualization foundation only. Trading, signal, confluence, level-computation, persistence/hash behavior, trades/equity semantics, and KPI logic were not changed.

### Implemented

- Extracted Levels chart construction into `thesistester/visualization/levels_chart.py` via `build_levels_chart(levels_df, selected_levels)`.
- Extracted Signals chart construction into `thesistester/visualization/signals_chart.py` via `build_signals_chart(levels_df, signals, selected_levels)`.
- Updated `pages/5_Levels.py` and `pages/6_Signals.py` to consume the new pure chart builders.
- Exported new chart builders from `thesistester/visualization/__init__.py` while keeping existing exports.
- Added Backtest visual overlay toggles in `pages/7_Backtest.py`:
  - Show session context
  - Show levels
  - Show confluence zones
  - Show SL/TP lines
- Extended `build_backtest_candlestick_chart(...)` in `thesistester/visualization/backtest_chart.py` with backward-compatible defaults for these toggles.
- Batched SL/TP shape construction into one `update_layout(shapes=...)` application to reduce repeated `add_shape()` calls and preserve existing session shapes.
- Added focused visualization tests for Levels, Signals, and Backtest chart toggle behavior.

## Phase 2 visualization readability (this PR)

This change set remains visualization-only. Trading, signal-generation, confluence detection, level computation, backtest simulation, persistence/hash behavior, equity semantics, and KPI logic were not changed.

### Implemented

- `build_levels_chart(...)` now supports candlestick rendering (`OHLC`) when OHLC columns are present, with automatic close-line fallback and an explicit `use_candles=False` fallback mode.
- `build_signals_chart(...)` now supports candlestick rendering (`OHLC`) when OHLC columns are present, with automatic close-line fallback and an explicit `use_candles=False` fallback mode.
- `build_signals_chart(...)` now supports confluence-zone overlay rendering from existing `confluence_zones` as one batched `Confluence zones` trace.
- `build_signals_chart(...)` now validates required confluence-zone columns (`timestamp`, `zone_low`, `zone_high`) when confluence zones are provided.
- `pages/6_Signals.py` now includes a visualization-only toggle to show/hide confluence zones on the signals chart.
- Signal marker traces now expose richer hover text from available signal metadata fields without changing marker semantics or filtering.
- Added focused tests for candlestick/fallback behavior, confluence-zone overlays/toggle behavior, required-column validation, marker hover metadata, and input immutability for both chart builders.

## Phase 3 chart windowing and payload reduction (this PR)

This change set remains visualization-only. Trading, signal-generation, confluence detection, level computation, backtest simulation, persistence/hash behavior, equity semantics, and KPI logic were not changed.

### Implemented

- Added reusable pure chart window helpers in `thesistester/visualization/chart_window.py`:
  - `coerce_timestamp_series`
  - `timestamp_bounds`
  - `clip_by_time_window`
  - `recent_rows_window`
  - `buffered_rows_window`
  - `trade_time_window`
- Added chart range controls to:
  - `pages/5_Levels.py`
  - `pages/6_Signals.py`
  - `pages/7_Backtest.py` execution visualizer
- Updated default chart windows to render clipped data ranges instead of full datasets.
- Kept explicit `Full dataset` options on Levels, Signals, and Backtest charts.
- Applied clipping only to DataFrames passed into chart builders (Plotly inputs), not to session-state artifacts/tables/metrics.
- Added focused helper tests in `tests/visualization/test_chart_window.py`.

## Future work (later phases)

- Trade-review mode.
- Downsampling/performance work (including larger-scale rendering improvements).
- Compute optimization.
