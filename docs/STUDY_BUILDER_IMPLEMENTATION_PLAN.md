# Study Builder — Implementation Plan (SB)

**Document type:** Focused implementation plan (fully scoped PRs)  
**Date:** 2026-08-14 (amended: mode_rules emit-exactly-listed-modes; levels TF omit ≠ bare `SMA_N`; RS D8/D9 out-of-scope labels)  
**Status:** **SB0 plan-locked.** SB1–SB3 not started.  
**Series code:** **SB** (Study Builder)  
**Regression framework:** Mandatory compliance with `docs/ENGINEERING_PROPOSAL.md` §4, including §4.1 golden-master operational spec and §4.2 per-milestone PR acceptance checklist  
**Depends on (already shipped):** Research Study Runner RS1–RS5 + RS-D8 + RS-D9 (`docs/STUDY_RUNNER.md`, `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md`)  
**Related living docs:** `docs/STUDY_RUNNER.md`, `docs/USER_GUIDE.md` (H2 `Studies viewer (read-only)`), `docs/ARCHITECTURE.md`, `docs/AGENT_GUIDE.md`, `docs/ENGINEERING_ROADMAP.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`  
**Related but separate:** Setup Builder (`pages/3_Setup_Builder.py`) — one closed setup, not a factorial study. Do not clone that page.  
**Does not reopen:** parked RS-D1 (NL compiler), RS-D3 (`run_batch` continue), RS-D6 (new factor types)  
**Related follow-on (do not implement here):** Study Ingest Alignment — `docs/STUDY_INGEST_ALIGNMENT_IMPLEMENTATION_PLAN.md` (SIA). Authoring/defaults only; does not reopen SB execute/preview/launch contracts. Study Viewer — `docs/STUDY_VIEWER_IMPLEMENTATION_PLAN.md` (SV). Inspect catalog/quality/charts/peek only; does not reopen SB emit/Apply/Preview.

**Completeness posture:** SB1–SB3 is one shippable product update: a researcher can assemble a valid `schema_version: 1` StudySpec from closed catalogs, see cell count / confirm, hand the YAML to the **existing** Preview pane, and run via the **existing** CLI spawn. Inspect, Preview, launch, expand, execute, promote, and report stay behavior-identical.

---

## 1. Purpose

YAML-as-contract stays. The Studies page already inspects artifacts, previews pasted YAML, and spawns `python -m thesistester study run`. Authoring is still a textarea. Operators omit required keys, invent illegal tokens, and explode cartesian size.

Ship a **Study Builder** that compiles a closed `StudyDraft` into canonical StudySpec YAML and applies it to the existing Preview textarea. No second runner. No new study language. No new factor axes.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Study Builder |
| Package home | `thesistester/study/builder.py` (new; pages import this module directly) |
| UI home | Third tab on existing `pages/15_Studies.py` — **Build StudySpec** |
| Contract | Emit / hydrate `schema_version: 1` only. `validate_study_spec(normalize_study_spec(emit(draft)))` is the gate |
| Preview / launch | Unchanged. Builder **writes** `STUDIES_PREVIEW_YAML_KEY` then the operator uses existing Validate / Preview / Run via CLI |
| Engine / golden impact | **None** |
| Schema / expand / execute / launch / promote | **No behavior edits** |
| Assistant / MCP | Unchanged (`assistant.study_tools` stays default-off; no `STUDY.*` from the builder) |
| Setup Builder | Catalog reuse only (enums). No shared editor state, no setup library, no `levels` dataframe requirement |
| Marketplace / NL / shorthand | **Non-goals** |
| Series complete when | SB3 acceptance checklist is green (end-to-end: build → apply → preview 40 → existing launch controls still present) |

**Feasibility:** High. `closed_level_token_set`, `preview_study_spec`, and CLI launch already exist. The builder is a constrained compiler plus widgets.

### 2.1 In-scope vs out

| In SB1–SB3 | Explicitly out (entire series) |
|---|---|
| Pure `StudyDraft` → canonical StudySpec | New StudySpec keys / factor axes / `schema_version` bump |
| Closed token / enum pickers | NL compiler (RS-D1); shorthand dialect |
| Auto `mode_rules` (canonical templates) | Custom `mode_rules` authoring |
| Forced `enabled: true\|false` on batteries | Auto-enabling grid / validation / walk_forward |
| Live strip via existing `preview_study_spec` | Reimplementing expand / cartesian / confirm math |
| Apply YAML to existing Preview textarea | In-process `run_study` / `STUDY.run` / new launch path |
| Stage filter + hydrate + promote-draft row delete | Templates marketplace; local study library / store schema |
| Download emitted YAML | New nav page; Inspect/Preview behavior change |
| | Promote-from-page; job queue; kill/retry UI |
| | Classic session mutation; Setup Builder / Data / Levels edits |
| | `engine/` edits; golden regeneration; `run_batch` semantics |

---

## 3. Why this is not Setup Builder

| Setup Builder | Study Builder |
|---|---|
| One closed setup | Factorial generator → N cells |
| `selected_levels` **or** one anchor + rules | `core_level` × `partner_levels` sets × modes × triggers × TFs × optional OTF |
| User-set min/max confluences | Expand **overrides** those for `global_cluster` (`min=max=len(core+partners)`) |
| Level columns from session `levels` frame | Closed catalog + `study.levels` implications (`closed_level_token_set`) |
| Saves `setup_config` to local store | Emits StudySpec YAML; identity hash is the study identity |
| Classic research session keys | Studies-scoped keys only |

Reuse: `VALID_TRIGGERS`, `VALID_TRIGGER_TIMEFRAMES`, `VALID_CONFLUENCE_MODES`, `VALID_DIRECTIONS`, `normalize_otf_filter_config`, `INSTRUMENTS`, `SUPPORTED_INDICATOR_TIMEFRAMES`.

Do not reuse: Setup Builder widget keys, `_setup_builder_editor_config`, `save_setup` / `list_saved_setups`, min/max confluence sliders as if they were study factors, dependence on `st.session_state["levels"]`.

---

## 4. Architecture (locked)

```text
StudyDraft  --emit_study_spec-->  dict  --normalize/validate-->  StudySpec
     ^                              |
     |                              +-- yaml.safe_dump --> Preview textarea
     +-- hydrate_study_draft(spec)

page Build tab  --preview_study_spec(emitted)-->  live strip (count / confirm / batteries)
page Build tab  --Apply to Preview-->  STUDIES_PREVIEW_YAML_KEY  (existing Preview / launch unchanged)
```

| Module | Role | Must not |
|---|---|---|
| `thesistester/study/builder.py` | Draft dataclass, defaults, emit, hydrate, canonical `mode_rules`, OTF presets, widget-key helpers | Import `execute`, `launch`, `promote`, `tools`, `viewer`, `cli`, `run_batch`, `preview` |
| `pages/15_Studies.py` | Third tab; widgets; call emit + `preview_study_spec`; Apply to Preview | Call `run_study`, dispatch `STUDY.*`, write classic keys, change Inspect/Preview/launch semantics |
| `thesistester/study/preview.py` | Unchanged consumer | New builder logic |
| `thesistester/study/schema.py` / `expand.py` / `launch.py` / `execute.py` | Unchanged | Any SB edit |

`thesistester/study/__init__.py` stays unchanged (package init already imports `execute`). Pages import `thesistester.study.builder` directly, same pattern as `launch.py`.

### 4.1 `StudyDraft` (locked fields)

Plain dataclass (or TypedDict + helpers). Source of truth for the Build tab. Not a second schema: emit is the only path into `validate_study_spec`.

| Field | Type | Default (SB1 `default_study_draft`) | Notes |
|---|---|---|---|
| `name` | `str` | `untitled_study` | Must match `RUN_NAME_RE` on emit |
| `description` | `str` | `""` | |
| `output_dir` | `str \| None` | `None` | `None` → omit; normalize fills `results/studies/<name>` |
| `workers` | `int` | `1` | ≥ 1 |
| `confirm_above_runs` | `int` | `200` | ≥ 1 |
| `dataset_path` | `str` | `data/es_1m.csv` | Required string; file need not exist until launch |
| `instrument` | `str` | `ES` | Required |
| `source_timezone` | `str` | `America/New_York` | |
| `format_profile` | `str` | `canonical` | Always emit. Omitted / blank → `canonical` (runner default). Unknown non-blank tokens fail emit — do not rewrite them to `canonical` |
| `subtimeframe_path` | `str \| None` | `None` | Omit when `None` |
| `dataset_extra` | `dict` | `{}` | Pass-through unknown-to-builder dataset keys present on hydrate (lossless round-trip). Emit copies them after known keys. Must not invent keys |
| `levels` | `dict` | `{sma_lengths: [50], ema_lengths: [21], sma_timeframes: [1min], ema_timeframes: [1min]}` | Keys ⊆ `DEFAULT_LEVELS_SETTINGS` |
| `core_level` | `list[str]` | `["pdPOC"]` | Required factor axis. `default_study_draft()` now uses `pRTH_Open`; this row is the `StudyDraft()` field default |
| `partner_levels` | `list[list[str]]` | `[["SMA_50_1min"]]` | List of non-empty sets |
| `confluence_mode` | `list[str]` | `["global_cluster", "anchor_rules"]` | Required cell axis — always emit |
| `trigger` | `list[str]` | `["touch"]` | Required cell axis — always emit |
| `trigger_timeframe` | `list[str]` | `["base"]` | Required cell axis — always emit (`30min` illegal) |
| `otf` | `list[dict] \| None` | `None` | `None` → omit factor (expand → OTF off). Never emit alias duplicates |
| `direction_as_factor` | `bool` | `False` | |
| `direction_values` | `list[str]` | `["long", "short"]` | Used only when `direction_as_factor` |
| `direction_constant` | `str` | `"both"` | Used when not a factor |
| `tolerance_ticks` | `float` | `0` | Constant |
| `naked_only` | `bool` | `False` | |
| `naked_requirement` | `str` | `"any"` | `any` \| `all` |
| `min_confluences` | `int` | `2` | Emitted for schema completeness; expand overrides for `global_cluster` |
| `max_confluences` | `int` | `2` | Must be ≤ 5 |
| `min_valid_confluences` | `int` | `1` | Anchor emission uses this |
| `trigger_params` | `dict` | `{}` | |
| `entry_window` | `dict \| None` | `None` | |
| `backtest` | `dict` | `{stop_loss_ticks: 8, take_profit_ticks: 16, exposure_policy: single_position, commission_per_side: 0.0, slippage_ticks: 0.0, flat_by_session_close: false, intrabar_model: sl_first}` | `stop_loss_ticks` and `take_profit_ticks` required on emit |
| `grid` | `dict` | `{enabled: false}` | Always include `enabled: bool` |
| `validation` | `dict` | `{enabled: false}` | Always include `enabled: bool` |
| `walk_forward` | `dict` | `{enabled: false}` | Always include `enabled: bool` |
| `from_partners` | `str` | `"required"` | `required` \| `optional` → `mode_rules.anchor_rules.confluence_rules` |
| `primary_metric` | `str` | `"expectancy_r"` | ⊆ index primary metrics |
| `secondary_metrics` | `list[str]` | `[profit_factor, max_drawdown_r, trade_count, total_r]` | |
| `min_trades` | `int` | `30` | ≥ 0 |
| `group_by` | `list[str] \| None` | `None` | `None` → omit; normalize intersects defaults with declared factors |
| `otf_baseline` | `dict` | `{enabled: false}` | Must include `enabled` |
| `multiple_testing` | `str` | `"warn"` | `warn` \| `error` |
| `stage_mode` | `None \| "filter" \| "explicit_cells"` | `None` | `None` → omit `stage` (full cartesian) |
| `stage_include` | `dict[str, list]` | `{}` | Used when `stage_mode=="filter"`; must be non-empty and ⊆ factor domains |
| `stage_cells` | `list[dict]` | `[]` | Used when `stage_mode=="explicit_cells"`; each cell has every factor axis |

Default draft expands to **2** cells (`1×1×2×1×1`). Valid without a dataset CSV on disk.
`default_study_draft()` (not the `StudyDraft()` field defaults in the table)
uses MNQ, UTC, `data/mnq_15s.csv`, Quantower HE, `15s_primary_derive_1m`,
`pRTH_Open`, tolerance 15, SL 40 / TP 80, costs 0.5 / 1.0 tick. The 16-cell
operator cartesian is `examples/studies/pRTH_open_ma.yaml`.

### 4.2 Emit (locked)

`emit_study_spec(draft) -> dict` builds a mapping, then returns `validate_study_spec(normalize_study_spec(payload))`.

`emit_study_yaml(draft) -> str` is `yaml.safe_dump` of that validated mapping (`sort_keys=False`, insertion order as below, `allow_unicode=True`). Comments from source files are **not** preserved.

**Required factor axes — always present as lists, even when singleton:**

`core_level`, `partner_levels`, `confluence_mode`, `trigger`, `trigger_timeframe`

Expand refuses cells missing `confluence_mode` / `trigger` / `trigger_timeframe`. The builder must not treat those as constants.

**Optional factor axes:**

- `otf` — omit entirely when `draft.otf is None` (do not emit `[{enabled: false}]` unless the operator selected the Off preset as an explicit factor value)
- `direction` — emit as a factor list only when `direction_as_factor`; otherwise emit `constants.direction`

**Canonical `mode_rules` — always present** (required cell axis `confluence_mode` is always a factor). Emit **exactly** the modes in `draft.confluence_mode`. Extra unused entries (`global_cluster` when the factor is only `anchor_rules`, or the reverse) change `study_identity_hash` and break hydrate → emit round-trip on singleton-mode / promote drafts. Schema requires an entry for each listed mode; it does not require the other allow-listed key.

Templates (use only for modes that are present):

```yaml
mode_rules:
  global_cluster:
    selected_levels: ["${core_level}", "${partner_levels...}"]
  anchor_rules:
    selected_levels: []
    anchor_level: "${core_level}"
    confluence_rules:
      from_partners: required   # or optional from draft.from_partners
```

Do not expose template strings in the main UI. Advanced: `from_partners` radio only (ignored on emit when `anchor_rules` is not in `confluence_mode`).

**Batteries:** if `grid` / `validation` / `walk_forward` are present on the draft (they always are), emit the mapping with an explicit boolean `enabled`. Never emit `{}`. Extra keys on those mappings survive hydrate → emit (grid value lists, etc.).

**Levels:** emit `draft.levels` as-is after dropping `None` values. Do **not** emit JSON `null` for `sma_timeframes` / `ema_timeframes` — `expand_study` → `validate_run_spec` requires a list when the key is present, so `null` fails the live strip. Tokens in factors must be in `closed_level_token_set(levels)` or emit raises `StudySpecError` with the existing schema wording.

Timeframe-key semantics after `{**DEFAULT_LEVELS_SETTINGS, **levels}` (this is what `closed_level_token_set` uses):

| Emit | Catalog / implied tokens |
|---|---|
| Key omitted | Product default TFs `1min`, `5min`, `30min` — **not** bare `SMA_N` |
| `[]` | No MA tokens for that family |
| Explicit list | Those suffixes only (`SMA_50_1min`, …) |

**Partner-set vs core:** emit may warn via a helper `draft_warnings(draft) -> tuple[str, ...]` when any partner set intersects `core_level` (expand fails that cell). Emit still validates; do not silently drop tokens.

### 4.3 Hydrate (locked)

`hydrate_study_draft(spec: Mapping) -> StudyDraft` accepts raw or normalized YAML mappings.

Invariant (load-bearing):

```text
loaded = load_study_spec(path)          # already normalized + validated
roundtrip = emit_study_spec(hydrate_study_draft(loaded))
study_identity_hash(roundtrip) == study_identity_hash(loaded)
```

Applies to:

- `examples/studies/dopen_ma_3c_mnq.yaml` (declares `format_profile`)

YAML **text** may differ (comments, key order). Identity hash is on the normalized mapping.

**Exception — omitted `dataset.format_profile`:** hydrate treats omitted / blank as `canonical` and emit always writes the key. That matches `run_experiment`'s existing default (`dataset_config.get("format_profile", "canonical")`) — explicit YAML, not a runner change. Unknown non-blank tokens are preserved on hydrate and fail emit (same fail-closed path as `load_ohlcv`). First hydrate→emit of `tests/fixtures/study/golden_study.yaml` and `examples/studies/pdPOC_ma_confluence_battery.yaml` therefore differs in identity hash; a second hydrate→emit is stable. Do not rewrite those fixtures (expand golden-masters stay byte-identical).

Rules:

1. Unknown StudySpec / study keys still fail in `validate_study_spec` — hydrate is not a second validator. Callers validate first or hydrate then emit (emit validates).
2. `dataset_extra` captures dataset keys other than `path`, `instrument`, `source_timezone`, `format_profile`, `subtimeframe_path`.
3. `otf` factor present → `draft.otf` is the list of **normalized** OTF dicts. Absent → `None`.
4. `direction` in factors → `direction_as_factor=True`. Else `direction_constant` from constants (default `both`).
5. `stage` absent → `stage_mode=None`. `filter` / `explicit_cells` copy include/cells.
6. `group_by` present → preserve list. Absent → `None` (emit omits; normalize fills).
7. `mode_rules.anchor_rules.confluence_rules.from_partners` → `from_partners` when `anchor_rules` is present. Emit **replaces** `mode_rules` with the canonical templates **for listed modes only**. Examples and the golden fixture already use those templates. Non-canonical `selected_levels` strings are not preserved (document; no test requires preserving invented templates).
8. `output_dir` equal to the normalize default may be stored as `None` or as the string; emit+normalize must hash-equal either way.
9. Copy report fields as present (`primary_metric`, `secondary_metrics`, `min_trades`, `group_by`, `otf_baseline`, `multiple_testing`). Do not replace a shorter `secondary_metrics` list (golden fixture) with the draft default list — that breaks identity-hash round-trip.

`hydrate_study_yaml(text) -> StudyDraft`: `yaml.safe_load` → mapping → `hydrate_study_draft`. Invalid YAML / non-mapping → `StudySpecError` (same class as schema).

### 4.4 OTF presets (locked)

Used by SB2 chips. Values are passed through `normalize_otf_filter_config` before emit.

| Id | Label | Config |
|---|---|---|
| `off` | Off | `{enabled: false}` |
| `5m` | 5m | `{enabled: true, timeframes: [5m], alignment_mode: all, minimum_consecutive_bars: 3}` |
| `15m` | 15m | same with `[15m]` |
| `30m` | 30m | same with `[30m]` |
| `combo` | 5m+15m+30m | `{enabled: true, timeframes: [5m, 15m, 30m], alignment_mode: all, minimum_consecutive_bars: 3}` |

Selecting **no** OTF chips → `draft.otf = None` (axis omitted).  
Selecting one or more chips → `draft.otf` is that list (order: off, 5m, 15m, 30m, combo).  
Custom OTF: Advanced expander only; must normalize; alias duplicates fail closed (existing schema).

The pdPOC example’s five OTF rows **are** these five presets. Hydrate of that example must map onto the five chips.

### 4.5 Token catalog (locked)

```python
def builder_token_catalog(levels: Mapping) -> tuple[str, ...]
```

Returns `tuple(sorted(closed_level_token_set(levels)))`. Factor pickers use this list. Do not read session `levels` / `levels_settings`. Do not invent tokens.

Static names come from `STUDY_STATIC_LEVEL_NAMES`. MA / rolling / prev30m / pivot tokens appear only when `draft.levels` **after DEFAULT merge** implies them (existing `closed_level_token_set` rules: omitted TF keys inherit `DEFAULT_LEVELS_SETTINGS` `1min`/`5min`/`30min`, not bare `SMA_N`; explicit `[]` → no MA tokens; prev30m/pivots inherit DEFAULT enable flags — both **on** unless the draft sets them false). Do not advertise a “bare `SMA_N`” emit path: study schema treats map-`None` as bare, but expand rejects `null` list fields.

### 4.6 Live strip (locked)

The **page** (not `builder.py`) calls `preview_study_spec(emit_study_spec(draft))` and renders:

- study name
- axis sizes
- `cartesian_product`
- `effective_run_count_estimate` / exact `run_count` when `expanded`
- `needs_confirm`, `confirm_above_runs`, `workers`
- battery flags + existing hint lines
- identity hash of the **emitted** (unpinned) spec — caption that launch will re-hash after dataset pin
- existing honesty sentence (screening size ≠ independent tests; ranking ≠ validated edge)

Reuse `StudyPreview` fields. Do not recompute cartesian in the page. Over `PREVIEW_EXPAND_CAP` (2_000): show the existing cap warning; Apply to Preview still allowed; launch remains the Preview-tab gate (`expanded=False` refuses launch — unchanged).

Builder emit failures (`StudySpecError`) show on the Build tab; they do not clear a previously cached Preview result unless the operator hits Apply (Apply always clears preview cache + launch approval via existing `reset_launch_session_for_preview`).

### 4.7 Apply to Preview (locked)

Button **Apply to Preview**:

1. `yaml_text = emit_study_yaml(draft)`
2. Capture `prev_cached_yaml = session_state.get(STUDIES_PREVIEW_CACHED_YAML_KEY)` (string or `None`) **before** popping cache
3. `st.session_state[STUDIES_PREVIEW_YAML_KEY] = yaml_text`
4. Pop `STUDIES_PREVIEW_CACHED_KEY` and `STUDIES_PREVIEW_CACHED_YAML_KEY`
5. `reset_launch_session_for_preview(session_state, prev_cached_yaml=prev_cached_yaml, new_yaml=yaml_text)` — existing helper; both kwargs are required. Always drops armed confirm; reseeds CLI `output_dir` when YAML changed
6. Success caption: YAML is on the Preview tab — use **Validate / Preview**, then existing Run via CLI / Bind confirm

Do **not** auto-call `preview_study_yaml`. Do **not** spawn CLI. Do **not** write `study.launch.yaml`. Do **not** switch Streamlit tabs programmatically (not reliable); the operator changes tab.

### 4.8 Session keys (locked allow-list)

Additive Studies-scoped keys only. Do not write `CLASSIC_RESEARCH_SESSION_KEYS` (`thesistester/study/viewer.py`).

| Key constant | String | Purpose |
|---|---|---|
| `STUDIES_BUILDER_DRAFT_KEY` | `studies_builder_draft` | Serialized draft dict (source of truth) |
| `STUDIES_BUILDER_PENDING_SYNC_KEY` | `studies_builder_pending_sync` | One-shot widget overwrite after hydrate (Setup Builder pattern) |

Widget keys live in `builder.py` as `WIDGET_KEY_*` constants with prefix `_study_builder_`. Partner-set rows use `_partner_set_widget_key(index)` → `_study_builder_partner_set_{index}`. AST tests allow-list the two Studies keys above plus existing RS-D2/D8/D9 keys. A separate test asserts the page source does not assign `CLASSIC_RESEARCH_SESSION_KEYS`.

Do not read Data / Levels / Setup Builder session keys to populate the draft (Studies stay independent of the classic mutate path). Dataset path is typed. **Start from example** and **Load from Inspect spec** are the convenience paths.

### 4.9 Import allow-list (`builder.py`)

Allowed:

- `thesistester.study.schema` — `StudySpecError`, `normalize_study_spec`, `validate_study_spec`, `closed_level_token_set`, `RUN_NAME_RE`, `STUDY_SCHEMA_VERSION`
- `thesistester.setup` — `VALID_*`, `normalize_otf_filter_config`
- `thesistester.levels.defaults.DEFAULT_LEVELS_SETTINGS`
- `thesistester.levels.indicators.SUPPORTED_INDICATOR_TIMEFRAMES`
- `thesistester.config.INSTRUMENTS` (or equivalent instrument catalog) only if needed for a helper; prefer the page to import `INSTRUMENTS`
- `yaml`, stdlib, `dataclasses`

Forbidden: `execute`, `launch`, `promote`, `tools`, `viewer`, `preview`, `cli`, `run_batch`, `run_experiment`, `pages.*`.

AST-guard `builder.py` the same way `preview.py` / `launch.py` are guarded.

---

## 5. UI contract (Build tab)

Same page, new tab label **Build StudySpec**. Tab order: Inspect output dir | Preview StudySpec | Build StudySpec.

Inspect and Preview bodies stay as they are (same functions, same buttons, same captions). Build is additive.

### 5.1 SB2 widgets (P0 — cannot omit structure)

Render from `STUDIES_BUILDER_DRAFT_KEY`. On hydrate, set `STUDIES_BUILDER_PENDING_SYNC_KEY` and `st.rerun()` so widgets pick up values (do not fight Streamlit key state).

**Identity**

- Name, description, workers, `confirm_above_runs`
- Output dir optional text (placeholder `results/studies/<name>`)

**Dataset**

- Path, instrument (`INSTRUMENTS`), timezone (`TIMEZONE_OPTIONS` or the string used on Data)
- Optional format profile text (empty → omit)
- Caption: launch still refuses a missing CSV; preview does not require the file

**Levels → tokens**

- SMA / EMA lengths: comma-separated positive ints or small multiselect of common lengths `{9, 21, 50, 200}` plus a free “add length” number input
- SMA / EMA timeframes: multiselect from `SUPPORTED_INDICATOR_TIMEFRAMES`. UI radio **Product default TFs** / **No MA tokens** / **Explicit TFs**. Map: Product default → omit the key (catalog uses DEFAULT `1min`/`5min`/`30min`, not bare `SMA_N`); No MA tokens → `[]`; Explicit → selected list. Do not store or emit JSON `null` for these keys.
- Optional expander: `vwap_windows`, `poc_windows`, `prev30m_vwap_enabled`, `pivots_enabled` + `pivot_timeframes`
- Read-only caption: **Closed tokens (N):** first ~20 names + count. This is the picker domain

**Factors**

- `core_level`: multiselect from token catalog (require ≥ 1)
- `partner_levels`: list editor — Add partner set / Remove. Each row is a multiselect from the catalog (require ≥ 1 token per set; reject duplicate tokens inside a set in the widget). Warn when a set shares a token with `core_level`
- `confluence_mode`: checkboxes `global_cluster`, `anchor_rules` (require ≥ 1)
- `trigger`: multiselect `touch, reject, break, reclaim, 3c`
- `trigger_timeframe`: multiselect `base, 1min, 5min, 15min` (no `30min`)
- OTF: the five preset chips (see §4.4)
- Direction: radio **Constant** / **Factor**. Constant → selectbox long/short/both. Factor → multiselect of those three

**Constants (main)**

- `tolerance_ticks`, naked toggle + requirement
- **Backtest (required):** `stop_loss_ticks`, `take_profit_ticks`, `commission_per_side`, `slippage_ticks`, `exposure_policy`, `intrabar_model`, `flat_by_session_close`
- Batteries: three checkboxes, default off, always emit `enabled`

**Constants (Advanced expander)**

- `min_confluences` / `max_confluences` / `min_valid_confluences` with caption: expand overrides min/max for `global_cluster`; do not present them as factor axes
- `from_partners`
- `entry_window` / `trigger_params`: pass-through JSON-ish or “leave null / {}” for SB2. Full entry-window widgets are **out of SB2**; hydrate preserves mappings. SB3 may add a one-line caption only unless entry-window reuse is trivial — do not clone Setup Builder’s entry-window block in this series
- Grid when enabled: `stop_loss_ticks_values` and `take_profit_ticks_values` as comma-separated ints (required if `grid.enabled`). Other grid keys hydrate-pass-through

**Live strip** — §4.6, always visible when emit succeeds.

**Actions (SB2)**

- **Start from example** — hydrate the selected template via `preview.py` path helpers in the **page** only (do not duplicate path constants). Default: `prth_open_ma_example_spec_path()` → `examples/studies/pRTH_open_ma.yaml`. pdPOC teaching example stays on the picker via `example_study_spec_path()`
- **Apply to Preview** — §4.7
- Emit `StudySpecError` → `st.error`, no Apply

### 5.2 SB3 widgets (complete product)

Additive on the same tab. Do not new-page.

**Stage**

- Radio: **Full cartesian** (`stage_mode=None`) / **Filter** / **Explicit cells**
- Filter: for each declared factor axis, optional multiselect of **currently selected** domain values. Only axes with a non-empty include subset (proper subset or explicit include) are written. At least one include key is required when mode is filter (schema). Default when starting from the pdPOC example: `trigger=[touch]`, `trigger_timeframe=[base]`
- Live strip already shows staged vs cartesian (reuse `StudyPreview`)
- Explicit cells: dataframe of `stage_cells` (one row per cell; partner_levels shown as `A+B`; OTF as a short canonical label). **Delete selected rows** only. No add-cell constructor (promote draft / YAML hydrate is the add path). Empty cells → `StudySpecError` on emit (existing schema)

**Report**

- `primary_metric` selectbox
- `min_trades`, `multiple_testing`
- `group_by` multiselect defaulting to intersection of preferred axes with declared factors; empty → emit `None` (normalize default)
- `otf_baseline` enabled checkbox (default off)

**Hydrate**

- **Load YAML from Preview tab** — hydrate `STUDIES_PREVIEW_YAML_KEY` if non-empty
- **Copy spec from loaded dir** — read Inspect `study.spec.yaml` via existing `resolve_study_dir` / sandbox; hydrate draft (Preview tab already has a copy-to-textarea button; Build hydrates the draft instead of only filling the textarea)
- Start from example already in SB2

**Download**

- `st.download_button` of `emit_study_yaml` as `<name>.yaml`. Not a store write. Never default a save path to the Inspect dir’s `study.spec.yaml`

**Honesty** (required on Build whenever the live strip is shown): same screening / multiple-testing sentence as Preview. Combinatorial count is not a validated edge.

### 5.3 Forbidden UI

- Run / Bind confirm / Promote / Kill / Retry on the Build tab
- Enable-batteries-by-default
- New sidebar page
- Saving to the setup library
- Editing `mode_rules` template strings
- Picking tokens not in the closed catalog
- Reading or writing classic research session keys

---

## 6. Regression-safety binding

Every SB PR must satisfy `ENGINEERING_PROPOSAL.md` §4.2.

| Gate | SB0–SB3 |
|---|---|
| Golden masters | Untouched; **no** regeneration |
| Engine | No edits under `thesistester/engine/` |
| StudySpec / expand / execute / launch / promote / rollup / tools | **No behavior edits.** SB1–SB3 must not change golden `experiment.yaml` / `study.expansion.json` bytes |
| Preview semantics | Unchanged (`PREVIEW_EXPAND_CAP`, import guard, no execute import) |
| Launch semantics | Unchanged (pin both dataset keys, pinned-hash confirm, exclusive pid, no in-process `run_study`) |
| Inspect | Unchanged (read-only; `write_artifacts=False`) |
| `run` / `run_batch` | Identical |
| `assistant.study_tools` | Default-off; no handler edits required |
| Pages | **Only** `pages/15_Studies.py` (third tab). No Setup Builder / Data / Levels / Backtest edits |
| Session | Studies-scoped keys only; record new keys in `ARCHITECTURE.md` in the PR that introduces them (SB2) |
| Docs | Same PR as the behavior; prefer **extend** USER_GUIDE H2 `Studies viewer (read-only)`. New H2 ⇒ amend RQ §7.1.4 + `_USER_GUIDE_SECTIONS` + freeze tests **in the same PR** |
| PIT | No new causality claims |
| Honesty | Live strip + Apply path repeat the screening caveat |

**Forbidden (entire series):** `engine/` edits; golden-master regeneration; new factor types; NL/shorthand compiler; in-process execute; job queue; templates marketplace; local study-library schema; cloning Setup Builder; mutating `CLASSIC_RESEARCH_SESSION_KEYS`; rewriting the RS-D5 Grok pack (optional one-liner only, in SB3).

**Allowed additive touches:**

| PR | Allowed paths |
|---|---|
| SB0 | Docs listed in §7 SB0 |
| SB1 | `thesistester/study/builder.py` (new); `tests/study/test_study_builder.py` (new); docs pointer in `STUDY_RUNNER.md` §SB stub if needed |
| SB2 | `pages/15_Studies.py` (additive tab); `tests/study/test_study_builder.py` (extend); `tests/study/test_study_preview.py` + `test_study_viewer.py` (AST allow-list only); `ARCHITECTURE.md` session-key sentence; USER_GUIDE extend (may wait for SB3 if SB2 UI is incomplete — prefer a short “Build tab (partial)” sentence in SB2 so Help is not silent) |
| SB3 | Same page + builder helpers for stage/report/hydrate already in SB1; USER_GUIDE complete how-to; `STUDY_RUNNER.md` §SB; `AGENT_GUIDE.md` pointer; roadmap ✅; optional one-liner in Grok pack |

---

## 7. PR sequence (fully scoped)

Do not merge SB2 before SB1. Do not merge SB3 before SB2. Do not start SB1 in the SB0 PR.

### SB0 — Plan lock (this document)

| | |
|---|---|
| **Scope** | Add `docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md`. Index in `docs/README.md`, `docs/ENGINEERING_ROADMAP.md`. Pointer from `docs/STUDY_RUNNER.md`, `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` (parked “UI factor builder” → this series; do not reopen D1/D3/D6), `docs/AGENT_GUIDE.md` |
| **Code** | None |
| **Tests** | None |
| **USER_GUIDE / HC** | No H2 change |
| **Acceptance** | Plan reviewed; SB1–SB3 scopes unambiguous; non-goals locked; existing RS flow described as unchanged |
| **Risk** | None |

---

### SB1 — Pure StudyDraft compiler (no UI)

| | |
|---|---|
| **Depends on** | SB0; shipped RS1–RS5 + D8 |
| **Scope** | `thesistester/study/builder.py`; `tests/study/test_study_builder.py`; `docs/STUDY_RUNNER.md` short **SB (compiler)** note that the helper exists and the UI does not |
| **Behavior** | `default_study_draft`, `emit_study_spec`, `emit_study_yaml`, `hydrate_study_draft`, `hydrate_study_yaml`, `builder_token_catalog`, `draft_warnings`, `OTF_PRESETS`, canonical `mode_rules`, widget-key constants (unused by UI yet) |
| **Out of scope** | `pages/15_Studies.py`; preview/launch/schema/expand edits; Streamlit |
| **Regression** | No existing module behavior change. `pytest tests/study/` stays green without touching goldens |
| **Acceptance checklist** | |
| | ☑ Default draft emit validates; `expand_study` run_count **2** |
| | ☑ Identity-hash round-trip on golden fixture + both `examples/studies/*.yaml` (exclude `agents/`) |
| | ☑ pdPOC hydrate: `stage_mode=="filter"`, include touch/base; emit preview estimate 40 vs cartesian 800 (call `preview_study_spec` **from the test**, not from `builder.py`) |
| | ☑ dopen hydrate: `format_profile` + grid value lists survive; `otf is None`; trigger `[3c]` |
| | ☑ Missing `mode_rules` on a hand-built draft: emit inserts canonical templates **for listed `confluence_mode` values only** (singleton mode → one `mode_rules` key) |
| | ☑ `grid: {}` cannot be produced by emit; batteries always have `enabled` |
| | ☑ Unknown token / `trigger_timeframe=30min` / empty partner set → `StudySpecError` |
| | ☑ Emit never writes `sma_timeframes` / `ema_timeframes` as JSON `null` |
| | ☑ `direction_as_factor` vs constant: only one of `factors.direction` / `constants.direction` as specified |
| | ☑ OTF presets normalize; selecting off+5m aliases that collapse to the same canonical config fail closed |
| | ☑ AST/import guard: `builder.py` does not import execute/launch/promote/preview/tools/viewer/cli |
| | ☑ `__init__.py` unchanged |
| | ☑ No `engine/` / pages / golden edits |

**Copy-ready agent prompt:**

```text
Implement SB1 only from docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md §7 SB1
and §4 (StudyDraft / emit / hydrate / OTF presets / token catalog).
Add thesistester/study/builder.py and tests/study/test_study_builder.py.
No Streamlit. Do not edit schema.py, expand.py, preview.py, launch.py,
execute.py, pages/, or study/__init__.py. builder.py must not import
execute/launch/promote/preview/tools/viewer/cli. Emit always validates
via normalize_study_spec + validate_study_spec. Always emit required
factor axes core_level, partner_levels, confluence_mode, trigger,
trigger_timeframe. Auto-insert canonical mode_rules for listed
confluence_mode values only (do not emit the unused mode). Batteries
always have explicit enabled. Do not emit sma_timeframes/ema_timeframes
null. Identity-hash round-trip must hold for
tests/fixtures/study/golden_study.yaml and both examples/studies/*.yaml.
Default draft expands to 2 cells. ENGINEERING_PROPOSAL.md §4.2: no
engine/golden drift. Update docs/STUDY_RUNNER.md with a short SB
compiler note only.
```

---

### SB2 — Build tab (authoring that cannot omit structure)

| | |
|---|---|
| **Depends on** | SB1 |
| **Scope** | Third tab on `pages/15_Studies.py`; wire widgets §5.1; live strip §4.6; Apply to Preview §4.7; Start from example; session keys §4.8; extend page AST allow-lists; `ARCHITECTURE.md` session-key sentence; USER_GUIDE: one short paragraph under existing H2 `Studies viewer (read-only)` that a Build tab exists and Apply sends YAML to Preview (full how-to in SB3 if needed) |
| **Behavior** | Operator can produce a valid StudySpec without typing YAML. Inspect + Preview + launch controls remain byte-equivalent in behavior (same buttons, same helpers, same captions). Build tab does not launch |
| **Out of scope** | Stage filter UI; report editor; explicit_cells table; download button; hydrate-from-Preview (SB3); entry-window widget clone; Data-page session coupling |
| **Regression** | |
| | Existing `tests/study/test_study_viewer.py` / `test_study_preview.py` / `test_study_launch.py` green after AST allow-list extension |
| | Page still has no in-process `run_study`; Preview still the only launch surface |
| | Classic research keys untouched |
| | `preview.py` import guard unchanged |
| **Acceptance checklist** | |
| | ☑ Tabs: Inspect \| Preview \| Build |
| | ☑ Default draft loads; live strip shows 2 cells, `needs_confirm` false |
| | ☑ Start from example hydrates pdPOC; live strip 40 vs 800; `needs_confirm` false at 200 |
| | ☑ Token picker: `EMA_21_5min` appears only after levels imply 21 × 5min |
| | ☑ Partner-set editor cannot submit a flat list (always list-of-lists) |
| | ☑ Apply to Preview writes `STUDIES_PREVIEW_YAML_KEY`, clears preview cache + launch approval, does not spawn |
| | ☑ After Apply, Preview textarea equals emitted YAML; Validate / Preview still required |
| | ☑ Batteries default off in emitted YAML (`enabled: false`) |
| | ☑ `mode_rules` present in emitted YAML without the operator typing templates |
| | ☑ AST allow-list includes `STUDIES_BUILDER_DRAFT_KEY` / `PENDING_SYNC`; no classic keys |
| | ☑ `builder.py` still has no preview/execute import (page imports both) |
| | ☑ Honesty visible on Build when emit succeeds |
| | ☑ Full `tests/study/` green; no golden regen |

**Copy-ready agent prompt:**

```text
Implement SB2 only from docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md §7 SB2
and §5.1 / §4.6–4.8. Add a third tab Build StudySpec on
pages/15_Studies.py. Do not change Inspect or Preview behavior except
AST allow-lists for new Studies-scoped keys. Widgets cover identity,
dataset, levels→closed tokens, factors (including partner-set list
editor and OTF presets), constants/backtest, batteries default off.
Live strip calls preview_study_spec(emit_study_spec(draft)) — do not
reimplement cartesian math. Apply to Preview writes
STUDIES_PREVIEW_YAML_KEY and reset_launch_session_for_preview; do not
auto-preview or spawn CLI. Start from example uses
example_study_spec_path() from preview.py in the page only.
Studies-scoped keys only (STUDIES_BUILDER_DRAFT_KEY,
STUDIES_BUILDER_PENDING_SYNC_KEY). No engine/golden/schema/expand/
launch/execute edits. Extend USER_GUIDE H2 Studies viewer (read-only)
with a short Build/Apply sentence; no new H2. ARCHITECTURE session-key
sentence. Extend test_study_preview / test_study_viewer AST allow-lists.
ENGINEERING_PROPOSAL.md §4.2.
```

---

### SB3 — Stage, report, hydrate, download (series complete)

| | |
|---|---|
| **Depends on** | SB2 |
| **Scope** | §5.2 widgets; hydrate from Preview / Inspect spec; download YAML; USER_GUIDE complete Build how-to **under the same H2**; `STUDY_RUNNER.md` §SB operator contract; `AGENT_GUIDE.md` SB pointer; `ENGINEERING_ROADMAP.md` SB1–SB3 ✅; optional one-liner in `STUDY_RUNNER_GROK_ROUTINE_PACK.md` (do not rewrite the pack) |
| **Behavior** | Stage-first authoring without YAML. Promote drafts hydrate into an explicit-cells table (delete rows). Round-trip: Preview YAML → Build → Apply → same identity hash. Product loop closed: Build → Apply → Validate / Preview → Run via CLI (existing) |
| **Out of scope** | New H2 unless HC amended same PR (prefer no new H2); study library; add-cell constructor; entry-window clone; promote CLI; in-process run |
| **Regression** | Same as SB2 plus USER_GUIDE H2 title unchanged (HC allowlist untouched) |
| **Acceptance checklist** | |
| | ☑ Filter UI can reproduce pdPOC stage (touch + base) → live strip 40 vs 800 |
| | ☑ Full cartesian radio omits `stage`; pdPOC domains → 800 estimate; confirm true at 200 |
| | ☑ Filter include values are ⊆ current factor widgets (cannot type a token not in the domain) |
| | ☑ Hydrate Preview YAML after Apply → draft fields match (identity hash equal) |
| | ☑ Copy spec from loaded dir hydrates a completed study’s `study.spec.yaml` |
| | ☑ Hydrate dopen example: grid lists + format_profile visible; 8 cells |
| | ☑ Explicit-cells table: delete one row → emit `len(cells)` decreases; cannot emit empty cells |
| | ☑ Download button serves `emit_study_yaml` |
| | ☑ Report `group_by` cannot include axes not in `factors` |
| | ☑ Inspect / Preview / launch tests still green; no launch controls on Build |
| | ☑ USER_GUIDE how-to: Build → Apply → Validate / Preview → Run via CLI; honesty; no new H2 |
| | ☑ `STUDY_RUNNER.md` §SB documents emit/hydrate/Apply and states execute is still CLI |
| | ☑ Roadmap SB1–SB3 ✅; AGENT_GUIDE pointer |
| | ☑ Full suite green; no golden regen |

**Copy-ready agent prompt:**

```text
Implement SB3 only from docs/STUDY_BUILDER_IMPLEMENTATION_PLAN.md §7 SB3
and §5.2. Complete the Build tab: stage radio (none/filter/explicit_cells),
filter include pickers ⊆ current factor domains, explicit-cells table with
delete-only, report fields, hydrate from Preview YAML and from Inspect
study.spec.yaml, download emitted YAML. Live strip remains preview_study_spec.
Do not add launch/promote/run controls to Build. Do not change Inspect,
Preview, launch, schema, expand, execute, or engine. Prefer extend USER_GUIDE
H2 Studies viewer (read-only) with the full Build how-to — no new H2, no HC
allowlist change. Add docs/STUDY_RUNNER.md §SB, AGENT_GUIDE pointer, roadmap
SB1–SB3 complete. Optional one-liner in the Grok pack; do not rewrite it.
Identity-hash round-trip: Preview YAML → hydrate → emit → same hash.
ENGINEERING_PROPOSAL.md §4.2.
```

---

## 8. End-to-end product acceptance (after SB3)

A researcher who never writes YAML can:

1. Open **Studies → Build StudySpec**.
2. Start from example (or pick core/partners/modes/triggers/OTF from catalogs).
3. See **40 vs 800** (or the live cartesian / staged counts) and battery flags.
4. **Apply to Preview**.
5. On Preview, **Validate / Preview** (existing) → same 40 / confirm gate.
6. **Run via CLI** or Bind confirm / Confirm and run (existing RS-D9).
7. Inspect the output dir (existing RS-D2) while the child runs.

A researcher with a promote draft can paste or copy YAML into Preview, **Load YAML from Preview** on Build, delete loser rows, Apply, and run the narrowed `explicit_cells` study.

CLI `study expand|run|report|promote|rollup` remains the academic path and does not depend on Streamlit.

---

## 9. Documentation rules

| Doc | When | What |
|---|---|---|
| This plan | SB0 | Lock |
| `docs/README.md` | SB0 | Index row |
| `docs/ENGINEERING_ROADMAP.md` | SB0 planned; SB3 ✅ | Status table + SB section |
| `docs/STUDY_RUNNER_IMPLEMENTATION_PLAN.md` | SB0 | Point parked UI factor builder at SB; do not reopen D1/D3/D6 |
| `docs/STUDY_RUNNER.md` | SB1 stub; SB3 §SB | Operator contract for emit/Apply; execute still CLI |
| `docs/USER_GUIDE.md` H2 `Studies viewer (read-only)` | SB2 short; SB3 complete | How-to. **No new H2** |
| RQ §7.1.4 / `_USER_GUIDE_SECTIONS` | Only if a new H2 is added | Same PR |
| `docs/ARCHITECTURE.md` | SB2 | Boundary + session keys |
| `docs/AGENT_GUIDE.md` | SB0 planned; SB3 shipped | Pointer |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | SB3 only if a new claim appears | Builder does not create an edge; combinatorial N is screening |
| Grok pack | SB3 optional one-liner | Humans may author via Build; coworkers still CLI |

Help corpus: extending the existing Studies H2 does **not** require an HC allowlist PR.

---

## 10. Test plan (series)

| Layer | Tests | PR |
|---|---|---|
| Compiler | `tests/study/test_study_builder.py` — emit/hydrate/presets/warnings/import guard | SB1, extend SB3 |
| Preview reuse | Builder tests may call `preview_study_spec` on emitted dicts; do not edit `preview.py` | SB1 |
| Page AST | Extend `test_study_preview.py` / `test_study_viewer.py` allow-lists; assert no `run_study(` on the page; assert no classic key writes | SB2 |
| Launch | Existing `test_study_launch.py` unchanged expectations | SB2–SB3 |
| Goldens | `tests/fixtures/study/golden/*` byte-stable | all |
| Suite | `pytest -q tests/study/` per PR; full suite before SB3 merge | all |

No Streamlit AppTest required if AST + pure helpers cover the contract (same posture as RS-D8/D9). If an AppTest is added, it must not call execute.

---

## 11. Risk register

| Risk | Mitigation |
|---|---|
| Streamlit widget state fights hydrate | Pending-sync key + draft as source of truth (Setup Builder pattern); tests cover hydrate → emit hash |
| Builder silently diverges from schema | Emit always `validate_study_spec`; no second validator |
| Cartesian blow-up | Live strip + existing confirm gate; stage-first example is the Start-from-example default |
| Page becomes a second runner | Launch stays on Preview; Build AST-forbidden from `run_study` / `spawn_launch` |
| Classic session contamination | Frozen `CLASSIC_RESEARCH_SESSION_KEYS` test |
| Mode-rules drift | Canonical templates only; examples already match |
| Entry-window / trigger_params underspecified | Hydrate pass-through; no Setup Builder clone in this series |
| HC allowlist break | Do not add a USER_GUIDE H2 |

---

## 12. Status

| Milestone | Intent | Status |
|---|---|---|
| SB0 | Plan lock + index | ✅ |
| SB1 | Pure StudyDraft compiler | ✅ |
| SB2 | Build tab P0 + Apply to Preview | ✅ |
| SB3 | Stage / report / hydrate / download + docs closeout | This PR |

Parked (not in SB): RS-D1 NL compiler; RS-D6 new factor axes; templates marketplace; study library; in-process execute; promote UI; entry-window widget clone.
