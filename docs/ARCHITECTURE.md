# ARCHITECTURE

## End-to-end data flow

```mermaid
flowchart LR
    A[Data] --> B[Levels]
    B --> C[Setup Builder]
    C --> D[Signals]
    D --> E[Backtest]
    E --> F[Grid Search]
    F --> G[Time Analysis]
    G --> H[Validation]
    H --> I[Report / Export]
```

Flow basis in app workflow and phase pages: `app.py:12-33`, `pages/1_Data.py`, `pages/5_Levels.py`, `pages/2_Setup_Builder.py`, `pages/6_Signals.py`, `pages/7_Backtest.py`, `pages/8_Grid_Search.py`, `pages/9_Time_Analysis.py`, `pages/10_Validation.py`, `pages/11_Report_Export.py`.

## `st.session_state` contract (current)

| Key | Producing page(s) | Consuming page(s) | Schema (observed) |
|---|---|---|---|
| `data` | Data (`pages/1_Data.py:114`) | Levels (`pages/5_Levels.py:203-217,425`), Backtest (`pages/7_Backtest.py:64-68`), Grid (`pages/8_Grid_Search.py:36-40`), Report/Bundles (`pages/12_Research_Bundles.py:26`) | `pd.DataFrame` OHLCV/session columns |
| `resampled_data` | Data (`pages/1_Data.py:115`) | Data summary (`pages/1_Data.py:341`) | `dict[str, pd.DataFrame]` |
| `instrument` | Data (`pages/1_Data.py:116`) | Levels/Setup/Signals/Backtest/Grid/Time (`pages/5_Levels.py:207`, `pages/2_Setup_Builder.py:67`, `pages/6_Signals.py`, `pages/7_Backtest.py:70`, `pages/8_Grid_Search.py:42`, `pages/9_Time_Analysis.py:30`) | `str` (e.g., `ES`, `NQ`) |
| `base_interval` | Data (`pages/1_Data.py:117`) | Levels fingerprint (`pages/5_Levels.py:84`), dataset persistence (`pages/1_Data.py:357`) | `str \| None` |
| `source_timezone` | Data (`pages/1_Data.py:118`) | Levels fingerprint (`pages/5_Levels.py:85`), dataset persistence (`pages/1_Data.py:358`) | `str \| None` |
| `exchange_timezone` | Data (`pages/1_Data.py:119`) | Levels fingerprint (`pages/5_Levels.py:86`), Backtest/Report TZ handling (`pages/7_Backtest.py:74-75`, `pages/11_Report_Export.py:24-33`) | `str \| None` |
| `display_timezone` | Data/Backtest/Time/Report widgets (`pages/1_Data.py:120-123`, `pages/7_Backtest.py:85-90`, `pages/9_Time_Analysis.py:68-73`, `pages/11_Report_Export.py:26-33`) | Time/Report export conversions (`pages/9_Time_Analysis.py:109`, `pages/11_Report_Export.py:33,129-133`) | `str` |
| `dataset_id` | Data (`pages/1_Data.py:124,361`) | Levels/Signals persistence (`pages/5_Levels.py:208-217`, `pages/6_Signals.py`) | `str` |
| `levels` | Levels (`pages/5_Levels.py:186,455`) | Setup/Signals/Backtest/Grid/Report/Bundles (`pages/2_Setup_Builder.py:62-67`, `pages/6_Signals.py`, `pages/7_Backtest.py:62-63`, `pages/8_Grid_Search.py:34-35`, `pages/12_Research_Bundles.py:30`) | `pd.DataFrame` OHLCV + derived level columns |
| `session_levels` | Levels (`pages/5_Levels.py:187,454`) | Bundles/save (`pages/5_Levels.py:497`, `pages/12_Research_Bundles.py:30`) | `pd.DataFrame` session-level table |
| `levels_settings` | Levels (`pages/5_Levels.py:188,456`) | Levels stale checks (`pages/5_Levels.py:323`), Signals persistence context (`pages/6_Signals.py`) | `dict` |
| `levels_data_fingerprint` | Levels (`pages/5_Levels.py:189,457`) | Levels stale checks (`pages/5_Levels.py:324-336`) | `dict` |
| `setup_config` | Setup Builder (`pages/2_Setup_Builder.py:200`), Signals saved-run copy action (`pages/6_Signals.py`) | Signals setup-source selection (`pages/6_Signals.py`), Report (`pages/11_Report_Export.py:36-43`) | `dict` setup configuration |
| `setup_configs` | Setup Builder (`pages/2_Setup_Builder.py:201-205`) | Setup Builder only | `list[dict]` |
| `confluence_zones` | Signals (`pages/6_Signals.py`) | Signals display (`pages/6_Signals.py`), Backtest chart overlay (`pages/7_Backtest.py:294-300`), Bundles (`pages/12_Research_Bundles.py:36`) | `pd.DataFrame` zone rows |
| `naked_flags` | Signals (`pages/6_Signals.py`) | Signals logic/save (`pages/6_Signals.py`), Bundles (`pages/12_Research_Bundles.py:37`) | `pd.DataFrame` naked-level flags |
| `signals` | Signals (`pages/6_Signals.py`) | Backtest/Grid/Report/Bundles (`pages/7_Backtest.py:48-56`, `pages/8_Grid_Search.py:21-29`, `pages/11_Report_Export.py:38-39`, `pages/12_Research_Bundles.py:35`) | `pd.DataFrame` candidate/fill signal rows |
| `signal_settings` | Signals (`pages/6_Signals.py`) | Signals save consistency checks (`pages/6_Signals.py`) | `dict` |
| `signal_settings_hash` | Signals (`pages/6_Signals.py`) | Signals save/load matching (`pages/6_Signals.py`) | `str` |
| `signal_context` | Signals (`pages/6_Signals.py`) | Backtest caption (`pages/7_Backtest.py:56,77`) | `dict` (`setup_name`, `confluence_mode`, `setup_caption`) |
| `last_signal_setup` | Signals (`pages/6_Signals.py`) | Signals persistence/report artifact (`pages/6_Signals.py`, `thesistester/reporting.py:146`) | `dict` |
| `trades` | Backtest (`pages/7_Backtest.py:156`) | Time/Validation/Report/Bundles (`pages/9_Time_Analysis.py:24`, `pages/10_Validation.py:21`, `pages/11_Report_Export.py:39`, `pages/12_Research_Bundles.py:42`) | `pd.DataFrame` simulated trade rows |
| `trade_summary` | Backtest (`pages/7_Backtest.py:157`) | Time/Report (`pages/9_Time_Analysis.py:39`, `thesistester/reporting.py:151`) | `dict` KPI summary |
| `equity_curve` | Backtest (`pages/7_Backtest.py:158`) | Backtest display/Report/Bundles (`pages/7_Backtest.py:163,207`, `pages/11_Report_Export.py:121-122`, `pages/12_Research_Bundles.py:42`) | `pd.DataFrame` cumulative-R curve |
| `grid_results` | Grid (`pages/8_Grid_Search.py:146`) | Validation/Report/Bundles (`pages/10_Validation.py:27`, `pages/11_Report_Export.py:40,123`, `pages/12_Research_Bundles.py:46`) | `pd.DataFrame` one row per SL/TP cell |
| `best_grid_result` | Grid (`pages/8_Grid_Search.py:147`) | Report artifact (`thesistester/reporting.py:152`) | `dict` best ranked cell |
| `time_bucketed_trades` | Time (`pages/9_Time_Analysis.py:129`) | Report/Bundles availability checks (`pages/12_Research_Bundles.py:57`) | `pd.DataFrame` trades + time-bucket columns |
| `time_grouped_summary` | Time (`pages/9_Time_Analysis.py:208`) | Report export (`pages/11_Report_Export.py:41,123`, `thesistester/reporting.py:180-185`) | `pd.DataFrame` grouped diagnostics |
| `validation_summary` | Validation (`pages/10_Validation.py:130`) | Validation display/Report/Bundles (`pages/10_Validation.py:134`, `pages/11_Report_Export.py:42,82-83`, `pages/12_Research_Bundles.py:50`) | `dict` (`bootstrap`, `permutation`, `trade_count`, `grid_overfit`) |

## Local persistence topology (filesystem)

- Root: `.thesistester_store/` (or `$THESISTESTER_STORE_DIR`)
- Datasets: `.thesistester_store/datasets/<dataset_id>/`
- Levels: `.thesistester_store/levels/<dataset_id>/<levels_settings_hash>/`
- Signal runs: `.thesistester_store/signals/<dataset_id>/<levels_settings_hash>/<signal_settings_hash>/`
- Setups: `.thesistester_store/setups/<setup_id>/meta.json`

Setup persistence is local-only (no cloud sync/user accounts). Setup Builder stores setup
configs in the setup library and keeps `st.session_state["setup_config"]` as the active setup
for Signals compatibility. Signals now supports setup-source selection (manual, active setup,
saved setup library), with dataset-aware setup-library labels/filtering and compatibility checks
for missing level references. Saved signal runs also expose a copy action that restores a setup
snapshot back into Setup Builder session state for review/edit/save before persistence.
