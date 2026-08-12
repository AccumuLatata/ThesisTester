# Research Study Runner

**Status:** RS1 landed (schema + validation). Expand / run / report land in RS2–RS5.  
**Plan:** `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`  
**Package:** `thesistester.study`

Headless, additive tooling for closed multi-factor confluence studies. Classic
Streamlit paths and `python -m thesistester run` are unchanged.

This surface answers: *across many closed setups, which factor combinations look
promising?* It is **not** confluence-combo attribution (within-trade membership).

---

## RS1 — StudySpec schema (`schema_version: 1`)

### Load / validate API

```python
from thesistester.study import load_study_spec, normalize_study_spec, validate_study_spec

spec = load_study_spec("path/to/study.yaml")  # load + normalize + validate
```

Fail-closed: unknown StudySpec / study / factors / constants / report / stage keys
raise `StudySpecError`.

### Top-level shape

```yaml
schema_version: 1
study:
  name: pdPOC_mini                    # ^[A-Za-z0-9][A-Za-z0-9_-]*$
  description: optional
  output_dir: results/studies/pdPOC_mini
  workers: 1
  confirm_above_runs: 200
  dataset: { path: data/es_1m.csv, instrument: ES }
  levels: { ... }                     # keys ⊆ DEFAULT_LEVELS_SETTINGS
  constants: { ... }                  # setup + backtest/grid/validation/walk_forward
  factors: { ... }                    # closed axes only
  mode_rules: { ... }                 # required when factors.confluence_mode present
  report: { ... }
  stage: { mode: filter, include: { ... } }   # optional
```

Normalization defaults (when omitted): `workers=1`, `confirm_above_runs=200`,
`description=""`, `output_dir=results/studies/<name>`, and a standard `report`
block (`primary_metric: expectancy_r`, `multiple_testing: warn`, …).

### Supported factor axes

| Axis | Values |
|---|---|
| `core_level` | non-empty list of closed level tokens |
| `partner_levels` | non-empty list of non-empty partner-sets (lists) |
| `confluence_mode` | `global_cluster`, `anchor_rules` |
| `trigger` | `touch`, `reject`, `break`, `reclaim`, `3c` |
| `trigger_timeframe` | `base`, `1min`, `5min`, `15min` (**not** `30min`) |
| `otf` | list of OTF configs (`normalize_otf_filter_config`) |
| `direction` | optional factor; `long` / `short` / `both` |

Unsupported axes (e.g. `sl_ticks`) fail closed.

### Closed level token set

A core/partner token is valid if it is in:

1. **Static catalog** — session/profile names including `pdPOC`, `ONH`, `dOpen`,
   `APOC`, single prints, session VWAPs, etc. (see `STUDY_STATIC_LEVEL_NAMES`
   in `thesistester/study/schema.py`), and
2. **Implied by `study.levels`** — `SMA_{len}_{tf}` / `EMA_{len}_{tf}` from
   lengths×timeframes (`null` timeframes → bare `SMA_{len}` / `EMA_{len}` like
   the levels engine; explicit `[]` → no MA tokens), plus `VWAP_rolling_*` /
   `POC_rolling_*` windows, and `prev30mVWAP*` / `Pivot_*` **only when**
   `prev30m_vwap_enabled` / `pivots_enabled` are true in the merged levels
   settings.

Unknown tokens fail at validate time with an actionable error.

### Constants rules (RS1)

- `direction` in constants allowed (`long` / `short` / `both`).
- When `grid` / `validation` / `walk_forward` mappings are present, they **must**
  include explicit `enabled: true|false`. Bare `{}` is rejected (R18 default-on trap).
- `max_confluences` ≤ 5 when provided.
- `dataset` / `backtest` are structural pass-throughs; deep RunSpec validation
  happens after expansion (RS2).
- `levels` keys ⊆ `DEFAULT_LEVELS_SETTINGS`. List fields (`sma_lengths`,
  `ema_lengths`, `*_timeframes`, `vwap_windows`, `poc_windows`,
  `pivot_timeframes`) must be real lists (not strings); lengths must be
  positive ints (not bools). Invalid shapes fail closed as `StudySpecError`.

### Report rules (RS1)

- `schema_version` must be the integer `1` (reject `true` / `1.0`).
- `group_by` keys must be axes present on **this** study’s `factors` (not merely
  any supported axis name).

### Mode rules

Required when `factors.confluence_mode` is present (and forbidden otherwise).

- `global_cluster.selected_levels` must be a **non-empty** list (template strings
  for RS2).
- `anchor_rules.selected_levels` must be `[]`.
- `anchor_rules.anchor_level` must be a non-empty string.
- `anchor_rules.confluence_rules.from_partners` ∈ `{required, optional}`.

### Stage

| Mode | Requirements |
|---|---|
| `filter` | non-empty `include`; keys ⊆ factor axes; each include value ∈ that factor’s domain; no `cells` |
| `explicit_cells` | non-empty `cells`; each cell supplies **every** factor axis with a value ∈ that factor’s domain; no `include` |

### Out of scope for RS1

Expansion to `experiment.yaml`, CLI `study` commands, execution ledger, and
overview reporting — see RS2–RS5 in the implementation plan.
