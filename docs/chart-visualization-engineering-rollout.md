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

## Future work (later phases)

- Candlestick Levels/Signals charts.
- Confluence overlays on Signals chart.
- Chart windowing.
- Trade-review mode.
- Downsampling/performance work (including larger-scale rendering improvements).
