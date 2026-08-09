# Regression-Safe Implementation Plan: Confluence Combo Attribution (Backtest)

**Status:** Phase 1 + Phase 2 implemented (analytics helpers + Backtest expander UI + honesty docs)  
**Document type:** Focused analytics / Backtest UX implementation plan  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related docs:**  
`docs/anchor_confluence_regression_safe_plan.md`,  
`docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md`,  
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`,  
`docs/METRICS_GLOSSARY.md`,  
`docs/ARCHITECTURE.md`

**Date:** 2026-08-09

**Plan review (2026-08-09):** Core seam and PR split are sound. Normative
amendments below lock View C grain, `available`, expander UI, lean metrics,
partition tests, default sample filters, anchor display keys, and elevates soft
pairwise (PR 4) as the main post-MVP research unlock.

**Plan polish (2026-08-09, follow-up):** Clarified observed-only cardinality,
UI-vs-analytics filter ownership (so partition identity stays valid), example-raw
fallback when timestamps are missing, empty-name membership behavior, optional
`__init__` export, and pure display helpers for anchor `display_combo`. Do
**not** start PR 1 until §5 / §7 / §12 locks in this revision are followed.

---

## 1. Purpose

Add a **post-trade confluence attribution** layer so researchers can answer:

> Which level combinations produced which R?

This is especially motivated by Anchor mode with `min_valid_confluences = 1`
(anchor + any one of N supports can fire), but it is equally valuable for
Global cluster mode, where unsupervised clusters mix many combinations into one
overall expectancy number.

The feature must be:

1. **Focused** — analytics + Backtest display only; no confluence/signal/fill
   behavior changes.
2. **Regression-safe** — additive, on-the-fly, default UI-off or expandable;
   legacy Backtest outputs unchanged when the new section is collapsed/unused.
3. **Mode-agnostic** — same machinery for `global_cluster` and `anchor_rules`,
   with mode-aware captions/honesty text.
4. **Honest** — membership views double-count; exact-combo keys must be
   canonicalized; empty/`3c` semantics documented.

---

## 2. Executive summary

| Item | Decision |
|---|---|
| Feature name | Confluence combo attribution |
| Primary surface | Backtest page → collapsed expander near Breakdown (not a 4th tab) |
| Compute model | Pure post-trade analytics from `_display_trades` |
| Persistence (MVP) | None — recompute on the fly (like Time Analysis / prev30m hit R) |
| Engine changes (MVP) | **None** |
| Signal / zone changes (MVP) | **None** |
| Required trade columns | `level_names`, `r_multiple` (optional: `direction`, `trigger`, `level_source_mode`, `entry_timestamp`) |
| Core views (MVP) | Exact combo · Level membership · Level count (parsed token count) |
| Optional polish (PR 3) | Direction × combo cross-tab / CSV / top-N |
| Post-MVP research unlock (PR 4) | Soft pairwise attribution (analytics-only) |
| Closest precedent | `thesistester/analytics/prev30m_vwap_hit.py` (expander + availability dict) |
| Golden-master impact | None (no engine touch) |

**Feasibility:** High. Trades already carry `|`-joined `level_names` (and
`level_count`) from zones → signals → `simulate_trades`. No schema migration is
required for MVP. Prefer `_display_trades` over raw `trades` so Focus overlays
stay honest (improvement vs current prev30m wiring).

**Cardinality note (locked):** tables enumerate **observed traded combinations**,
not the theoretical power set of selected levels. With 5 levels, theory allows
up to 31 non-empty subsets, but rows are bounded by combinations that actually
became trades in the run. Engine load is unchanged; UX cardinality is managed by
default sample hiding (and optional later top-N).

---

## 3. Problem statement / user motivation

### 3.1 Observed user model

When creating setups:

- **Global cluster:** N selected levels, shared tolerance, `min_confluences`.
- **Anchor rules:** 1 anchor + M confluence rules, `min_valid_confluences`.

With Anchor `min_valid_confluences = 1`, the user correctly expects:

> Anchor + any 1 of the M supports can create a zone / signal.

They then want Backtest to show **which combination** drove outcomes:

| Combo | Trades | Win rate | Avg R | Total R |
|---|---:|---:|---:|---:|
| `pdHigh\|VWAP_rolling_1h` | 42 | 55% | +0.21 | +8.8 |
| `pdHigh\|pdPOC` | 31 | 48% | -0.05 | -1.6 |
| `pdHigh\|VWAP_rolling_1h\|pdPOC` | 18 | 61% | +0.40 | +7.2 |

### 3.2 Current gap

Today:

- Trades retain `level_names` / `level_count` and show them in the trade table.
- Backtest Breakdown tabs group by `trigger` / `direction` / `exit_reason` only.
- No first-class combo / membership / count attribution summary exists.
- Overall expectancy mixes strong and weak combinations.

### 3.3 Why global mode benefits too

Global cluster with low `min_confluences` emits many unsupervised clusters.
Overall avg R can hide that one recurring pair carries the edge while others
drag. Combo attribution separates discovery from noise for both modes.

---

## 4. Current behavior (locked baseline)

### 4.1 Propagation path (already implemented)

```text
detect_confluence_zones / detect_anchor_confluence_zones
  → generate_signals (_make_signal copies zone level_names / level_count)
  → simulate_trades (sig.get("level_names") / sig.get("level_count"))
  → st.session_state["trades"]
```

| Stage | File | Format notes |
|---|---|---|
| Global zones | `thesistester/engine/confluence.py` | `"\|".join(...)` in **price-sorted** order |
| Anchor zones | `thesistester/engine/anchor_confluence.py` | `anchor \| valid_rules_in_rule_order` |
| Signals | `thesistester/engine/signals.py` | Direct copy for simple triggers; 3c may emit tested-level-only / empty |
| Trades | `thesistester/engine/backtest.py` | Always present in trade schema |

### 4.2 What is NOT on trades today

| Field | Where it lives | MVP implication |
|---|---|---|
| `rule_results` / per-rule distances | Anchor zones / Signals diagnostics | Stay Signals-only |
| `anchor_level`, `valid_confluence_count` | Zones | Do **not** infer from `level_names` token order; use session `setup_config` for captions / display only |
| `setup_name` | Signals (often), not reliably on trades | Out of MVP cross-setup grouping |
| `confluence_mode` | Setup / zones | Caption / display from session `setup_config` when available; not required for core metric tables |

### 4.3 Existing grouping precedents

| Precedent | Location | Reuse |
|---|---|---|
| Rich group metrics + `sample_warning` | `analytics/time_analysis.py::summarize_by_group` | **Do not reuse** — too heavy (`max_drawdown_r` etc.) and sorts by group key |
| Minimal group metrics | `analytics/metrics.py::summarize_by_group` | Avoid dual-API confusion; do not extend for this feature |
| Lean hit-R group metrics | `analytics/prev30m_vwap_hit.py::summarize_r_by_hit_flag` | Closest metric shape; mirror with private `_summarize_r` + `sample_warning` |
| Backtest Breakdown tabs | `pages/7_Backtest.py` | Leave the three tabs untouched; insert expander nearby |
| prev30m diagnostic expander | `pages/7_Backtest.py` | UI pattern precedent (collapsed `st.expander`) |
| Focused subset display | `_display_trades` on Backtest | Combo analytics **must** use `_display_trades` |
| Delimiter-tolerant parse | `analytics/prev30m_vwap_hit.py` (`|` and `,`) | Reuse pattern |
| Chart parse (`|` only) | `visualization/backtest_chart.py::_parse_level_names` | Keep chart as-is; analytics gets shared robust parser |

---

## 5. Locked product definition

### 5.1 Views (MVP)

#### View A — Exact combo

Group trades by a **canonical combo key** derived from `level_names`.

Canonicalization rules (locked):

1. Accept `|` or `,` delimiters.
2. Strip whitespace; drop empty tokens.
3. Deduplicate tokens while preserving first-seen order for parsing helpers.
4. Build **exact_combo_key** = tokens sorted lexicographically, joined by `|`.
5. Empty / null / `pd.NA` / `pd.NaT` / `"nan"` → bucket `__empty__`
   (display label: `(no level names)`). Never invent a literal `"<NA>"` token.

Why sort: global price-order can emit `A|B` and `B|A` for the same set across
bars; unsorted grouping would falsely split identical sets.

**Display vs group key (locked):**

- Metrics always group on the canonical sorted `exact_combo_key`.
- Optional secondary **example raw** column: choose the raw `level_names` from
  the earliest trade in the group by `entry_timestamp` (then `trade_id`) —
  never “first row seen” (order-dependent).
  Fallback when `entry_timestamp` is missing/unsortable: `trade_id` only; if
  that is also missing, use a stable `reset_index()` position as last resort.
- Optional **display_combo** column for UI: when
  `setup_config.confluence_mode == "anchor_rules"` and session `anchor_level`
  is known and present in the token set, render
  `anchor|sorted(remaining tokens)`; otherwise render the canonical sorted key.
  Never infer anchor from token order in global/unknown mode.
  Implement as a pure helper (`format_display_combo(...)`) so the page stays thin.

**Partition identity (locked):** exact-combo rows form a partition of the
analyzable trade universe **before any UI sample filter**. Tests must assert:

```text
sum(by_exact_combo.trade_count) == analyzable_trade_count
sum(by_exact_combo.total_r) == sum(analyzable r_multiple)
```

Membership deliberately does **not** partition (double-counts).

#### View B — Level membership

Explode each trade into one row per distinct level token, then group by level.
Trades with empty parsed names contribute **no** membership rows (they only
appear in Exact combo as `__empty__` and Level count as `(unknown)`).

Honesty caveat (must appear in UI + docs):

> Membership attribution **double-counts** trades across levels. A trade with
> `pdHigh|VWAP` contributes to both `pdHigh` and `VWAP` rows. Use this to find
> useful participants, not as an additive PnL decomposition.

#### View C — Level count (parsed token count)

Group by **parsed distinct token count** from `level_names` (same grain as
Views A/B). Empty / null names → `(unknown)` (or equivalently token count `0`
mapped to that label).

**Do not** prefer stored trade `level_count` for MVP grouping. On `3c` signals,
`level_names` is often the tested level only while zone `level_count` remains
the fuller zone size — mixing those grains would make View C disagree with
Exact/Membership. Stored `level_count` may be exposed later as a secondary
diagnostic column; it is out of MVP View C.

This answers: do denser *recorded name sets* outperform thinner ones?

**Nested-set caveat (MVP limitation):** exact combo treats `A|B` and `A|B|C`
as unrelated. If the true edge is pair `A|B` but a third tag often accompanies
it, MVP understates that pair. Membership only partially helps. Soft pairwise
(PR 4) is the dedicated unlock for this.

### 5.2 Metrics (locked)

Implement via a private lean `_summarize_r(trades, group_col, min_trades)`
inside `confluence_attribution.py`. Do **not** call
`time_analysis.summarize_by_group` or extend `metrics.summarize_by_group`.

Each summary table includes:

| Column | Definition |
|---|---|
| view-specific key | Combo key / display key, level name, or level-count bucket |
| `trade_count` | Rows in group with non-null `r_multiple` |
| `win_rate` | Share of `r_multiple > 0` among non-null `r_multiple` |
| `avg_r` | Mean `r_multiple` |
| `median_r` | Median `r_multiple` |
| `total_r` | Sum `r_multiple` |
| `sample_warning` | True when `trade_count < min_trades` |

Defaults (locked):

- `min_trades = 10` for warning flag (configurable in UI; clamp ≥ 1).
- Sort default: `total_r` descending, then `trade_count` descending.
- **Hide below `min_trades` = ON by default** in the UI (honesty / anti-cherry-pick).
- Optional UI toggle: sort by `avg_r`; optional “show all samples”.

**Filter ownership (locked):**

- Analytics `summarize_*` / `confluence_attribution_summary` return **all**
  groups and set `sample_warning`; they do **not** drop thin samples.
- The Backtest UI applies the hide-below-`min_trades` filter as a presentation
  step. This keeps exact-combo partition identity testable and avoids baking
  selection into the analytics API.
- Breakeven trades (`r_multiple == 0`) count in `trade_count` and are **not**
  wins (`win_rate` uses `> 0` only).

Null `r_multiple` rows are **excluded** from denominators (same convention as
`summarize_trades` / prev30m hit R). Note intentionally differs from the
existing Breakdown tabs’ inline `(x > 0).mean()`, which treats nulls as
non-wins in the denominator — do **not** change those sibling tabs in MVP;
document the difference in `METRICS_GLOSSARY.md`.

Do **not** invent new expectancy definitions; reuse existing R conventions from
`METRICS_GLOSSARY.md`.

### 5.3 Trade universe (locked)

| Context | Universe |
|---|---|
| Standard Backtest | `_display_trades` (respects Focus window when active) |
| Admit constrained re-sim | Session trades after Admit (already constrained) |
| Walk-forward OOS (future) | Same helpers on OOS trades DF; not MVP UI |
| Missing `level_names` column | `available=False`; calm info; no crash |
| Column present but only empty names | `available=False`; report `empty_level_names_count`; calm info |

### 5.4 Mode-aware copy (locked)

| Mode | Caption emphasis |
|---|---|
| Anchor / `anchor_rules` | “Combinations are anchor + currently valid confluence rules on the signal bar. Min valid confluences controls threshold, not pairwise splitting.” |
| Global / `global_cluster` | “Combinations are unsupervised peer clusters within tolerance. Order is canonicalized; raw price-order strings may differ.” |
| Unknown / mixed | Neutral caption; still compute from `level_names`. |
| Any run with `trigger == "3c"` trades in the displayed set | Extra honesty: “For 3c, `level_names` may be the tested level only, not full zone membership.” |

Mode detection for captions (best-effort, non-blocking):

1. `st.session_state["setup_config"]["confluence_mode"]` when present.
2. Else `level_source_mode` dominance on displayed trades if present.
3. Else neutral.

Diagnostic framing (mandatory in UI caption):

> Diagnostic only — rows are combinations that actually traded in this run,
> not all possible subsets. Sorting many combinations by total R invites
> selection effects; thin samples are hidden by default. Not proof of future
> edge.

### 5.5 What this feature is not

| Non-goal (MVP) | Reason |
|---|---|
| Pairwise zone splitting in the engine (`anchor+A`, `anchor+B` as separate zones) | Changes signal multiplicity / backtest economics; high regression risk |
| Joining `rule_results` onto trades | Signals-only diagnostics; different grain |
| Persisted combo summary artifacts | Not needed; on-the-fly is enough |
| Changing `min_confluences` / `min_valid_confluences` semantics | Product confusion already exists; do not “fix” by changing engines |
| Auto-promoting winning combos into Setup Builder | Workflow automation later; keep research-read-only |
| Portfolio / multi-setup combo tables | Requires reliable setup tagging on trades |
| Mutating chart parsers or naked-count parsers | Avoid unrelated regressions |

---

## 6. Design principles (regression safety)

1. **Analytics-only.** No changes to
   `detect_confluence_zones`, `detect_anchor_confluence_zones`,
   `generate_signals`, or `simulate_trades` in MVP PRs.
2. **Additive UI.** Collapsed expander near Breakdown; **do not** add/reorder/
   rename the existing three Breakdown tabs.
3. **Fail closed in display, never crash.** Missing columns or no non-empty
   combos → calm info + `available=False`.
4. **Focused-subset honesty.** Use `_display_trades`; keep Focus caveat visible.
5. **No golden regeneration.** Engine goldens untouched (§4.1 N/A because no
   engine touch).
6. **Docs in the same PR** that introduces user-visible behavior
   (`ASSUMPTIONS_AND_LIMITATIONS`, `METRICS_GLOSSARY`, this plan’s status).
7. **Small surface area per PR.** Pure helpers land before UI wiring.
8. **Lean private metrics.** One `_summarize_r` helper; no third public
   `summarize_by_group` API.

---

## 7. Architecture / file plan

### 7.1 New module

```text
thesistester/analytics/confluence_attribution.py
```

Suggested public API:

```python
EMPTY_LEVEL_NAMES_KEY = "__empty__"
EMPTY_LEVEL_NAMES_LABEL = "(no level names)"
UNKNOWN_LEVEL_COUNT_LABEL = "(unknown)"

def parse_level_names(raw: Any) -> list[str]:
    """Normalize |/, strip, drop empties, de-dupe preserving order."""

def exact_combo_key(raw: Any) -> str:
    """Canonical sorted key; EMPTY_LEVEL_NAMES_KEY when none."""

def format_display_combo(
    tokens_or_key: Any,
    *,
    anchor_level: str | None = None,
) -> str:
    """UI display helper. If anchor_level is in the token set, render
    ``anchor|sorted(rest)``; else canonical sorted key. Never guesses anchor.
    """

def attach_combo_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """Return copy with exact_combo_key, level_token_count, parsed helper cols.

    ``level_token_count`` is the distinct parsed-token count from
    ``level_names`` (View C grain). Do not copy/prefer stored ``level_count``.
    """

def summarize_by_exact_combo(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Return all groups + sample_warning. Do not drop thin samples here."""

def summarize_by_level_membership(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Return all groups + sample_warning. Empty-name trades contribute no rows."""

def summarize_by_level_count(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame:
    """Group by parsed distinct token count (not stored level_count)."""

def confluence_attribution_summary(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> dict[str, Any]:
    """Bundle availability + the three unfiltered frames + honesty flags."""
```

Availability contract (mirror prev30m style; tightened):

```python
{
  "available": bool,          # True iff level_names present AND ≥1 analyzable
                              # trade with a non-empty parsed combo
  "trade_count": int,         # analyzable trades (non-null r_multiple)
  "nonempty_combo_trade_count": int,  # analyzable + non-empty combo
  "empty_level_names_count": int,
  "by_exact_combo": DataFrame,
  "by_membership": DataFrame,
  "by_level_count": DataFrame,
  "warnings": list[str],      # membership double-count when available;
                              # 3c note whenever any *displayed* trade has
                              # trigger=="3c" (independent of available / R)
}
```

`__empty__` rows may still appear inside `by_exact_combo` when summarizing a
frame that mixes empty and non-empty names, but **`available` stays False**
when every analyzable trade is empty-named (UI shows calm info, not tables).

When `available=True`, UI may still render the `__empty__` exact-combo row if
it survives the presentation filter; membership will simply omit those trades.

### 7.2 Package export

**PR 1 default:** do **not** modify `thesistester/analytics/__init__.py`.
Pages/tests import the submodule directly:

```python
from thesistester.analytics.confluence_attribution import (
    confluence_attribution_summary,
)
```

Optional later: re-export from `__init__.py` only if another consumer needs it.
Avoid package-init churn in the foundation PR.

### 7.3 UI wiring (locked)

Update `pages/7_Backtest.py`:

- **Do not** add a fourth Breakdown tab or change the existing
  `["By trigger", "By direction", "By exit reason"]` tab args/order/labels.
- Add a collapsed expander **“Confluence combo attribution”** immediately
  under/near the Breakdown block (same pattern as the prev30m hit-R expander).
- Inside:
  - Mode-aware caption + diagnostic / selection-effects / observed-only caption
  - Membership double-count honesty caption
  - Conditional 3c tested-level-only caption when any displayed trade has
    `trigger == "3c"`
  - `min_trades` number input (default 10)
  - “Hide samples below min_trades” checkbox (**default ON**)
  - Presentation filter applied in the page after summary returns
  - Three sub-tabs or stacked tables: Exact combo / Membership / Level count
  - Exact combo display may use `format_display_combo(..., anchor_level=...)`
    when session setup is anchor_rules
- Compute from `_display_trades`, not raw `trades`, when Focus is active.

MVP recommendation: **keep logic in analytics module**; page only renders and
applies the sample-size presentation filter.

### 7.4 Tests

```text
tests/test_confluence_attribution.py
```

Template: `tests/test_prev30m_vwap_hit_analytics.py` (empty-safe, delimiter,
missing columns, availability).

### 7.5 Docs touched by user-visible PR

| Doc | Update |
|---|---|
| This plan | Status → phased progress |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Membership double-count; canonicalization; 3c tested-level-only; nested-set / selection-effects caveats |
| `docs/METRICS_GLOSSARY.md` | Exact combo / membership / parsed level-count metrics; null-R exclusion vs sibling Breakdown tabs; partition vs double-count |
| `docs/ARCHITECTURE.md` | One bullet under analytics surfaces if session keys remain unchanged |

No `ENGINEERING_PROPOSAL` milestone bump required unless product owners want it
tracked as a named research UX milestone; this plan is sufficient.

---

## 8. Semantic edge cases (normative)

| Case | Required behavior |
|---|---|
| `level_names` missing column | `available=False`; no exception |
| `level_names` null / `pd.NA` / `pd.NaT` / `""` / `"nan"` | Bucket `__empty__`; does **not** alone make `available=True` |
| Only empty names (all analyzable trades) | `available=False`; report `empty_level_names_count` |
| Delimiters `,` and `\|` mixed | Normalize both |
| Duplicate tokens `A\|A\|B` | Treat as `{A,B}` for combo key / membership / token count |
| Global price-order flip `A\|B` vs `B\|A` | Same exact_combo_key |
| Anchor order `anchor\|B\|A` | Canonical sort groups same set; UI display may use `anchor\|sorted(rest)` when session anchor known |
| Stored `level_count` ≠ parsed token count (`3c`) | View C uses **parsed** count only |
| Single-level global (`min_confluences=1`) | Valid 1-token combos; expected and useful |
| Multi-level zone (up to 5 / anchor+N) | Exact combo uses full set; membership explodes all tokens |
| Nested sets `A\|B` vs `A\|B\|C` | Separate exact-combo rows; soft pairwise (PR 4) attributes shared pairs |
| 3c tested-level-only names | Combo reflects signal `level_names` (often tested level); UI caption when any `trigger=="3c"` |
| Focus subset empty | Info message; no tables |
| Huge combo cardinality | Observed-only rows + default UI hide below `min_trades`; no hard truncation in MVP (optional top-N in PR 3) |
| `r_multiple` null | Exclude from metric denominators |
| `r_multiple == 0` | Included in `trade_count`; not a win |
| Empty-name trade in membership | No membership rows emitted for that trade |
| Direction filter | Not auto-applied; optional PR-3 cross-tab |

---

## 9. Value framing by mode (for UI/docs)

### Anchor mode

Research questions unlocked:

1. Which supports are productive partners for this anchor?
2. Is `anchor+1` enough, or do richer confirmations improve R?
3. Are a few weak optional rules polluting a good anchor thesis?

Interpretation: exact combo ≈ “what evidence set fired”; membership ≈ “is this
rule useful around the anchor?”

### Global mode

Research questions unlocked:

1. Which unsupervised clusters carry the edge?
2. Which selected levels are passengers vs drivers?
3. Does raising `min_confluences` align with level-count R curves?

Interpretation: exact combo ≈ “which peer cluster”; membership ≈ “should this
level remain in the selected set?”

---

## 10. Explicit non-goals / deferred work

### Deferred (post-MVP)

| Idea | Priority after MVP | Why deferred |
|---|---|---|
| Soft pairwise **attribution** view | **High — ship soon after PR 2** | Main nested-set / “anchor partner quality” unlock; still analytics-only |
| Direction × combo / CSV / top-N polish | Medium — if cardinality or export pain appears | UX convenience, not research-critical |
| Pairwise **engine** emission (one zone per valid rule when min=1) | Low / likely never default | Changes trade counts / overlap / exposure; needs own golden-gated plan |
| Stamping `setup_name` / `confluence_mode` onto trades | Low for single-run Backtest | Additive schema; captions already read session `setup_config` |
| Research-bundle parquet export of combo summaries | Later | Follow prev30m/excursion pattern |
| Time Analysis primary dimension = `exact_combo_key` | Later | Natural follow-on after Backtest proves usefulness |
| Assistant narrative over combo tables | Later | Depends on stable analytics API |
| Auto-suggested setup tightening from winning combos | Explicitly out | High product risk / overfitting temptation |
| Secondary View C by stored zone `level_count` | Later | Only after 3c name/zone grain is clarified in UI |

### Soft pairwise attribution (recommended Phase 4, still analytics-only)

**Why elevated:** Exact combo alone understates a productive pair when a third
level often tags along (`A|B` vs `A|B|C`). Soft pairwise answers anchor
“which support partners earned R?” without multiplying fills.

For Anchor-like reading without changing the engine:

- For each trade with tokens `[anchor?, L1, L2, ...]`, emit pair keys
  `(sorted_pair)` for every unordered pair, **or**
  for anchor mode specifically emit `anchor|Li` for each non-anchor Li present.
- Metrics grouped by those pair keys.
- Honesty: still double-counts; caption required.
  A single trade with three tokens contributes to **three** generic pairs
  (`AB`, `AC`, `BC`), so pair-view `total_r` can exceed book `total_r`.

**Anchor source (locked):** prefer explicit session
`setup_config.anchor_level` when `confluence_mode == "anchor_rules"`.
Otherwise show generic unordered pairs only — **do not guess** anchor from
token order (global price-sort puts cheapest level first, not an anchor).

---

## 11. Fully scoped PRs

### PR 1 — Pure analytics foundation (no UI)

**Title:** `feat(analytics): confluence combo attribution helpers (no UI)`

**Scope:**

- Add `thesistester/analytics/confluence_attribution.py`
- Add `tests/test_confluence_attribution.py`
- Update this plan status (Phase 1 complete)
- Do **not** modify `analytics/__init__.py` unless a concrete import need appears

**Must include tests for:**

1. Empty trades / None / missing `level_names`
2. Delimiter normalization (`|` and `,`)
3. Canonicalization (`B|A` == `A|B`)
4. Dedup tokens
5. Empty bucket
6. Exact combo metrics correctness on a tiny fixture
7. **Exact-combo partition identity** on the **unfiltered** summary
   (`sum(trade_count)` / `sum(total_r)`)
8. Membership double-count (one trade → two membership rows)
9. Empty-name trades emit no membership rows
10. Level count uses **parsed** token count even when stored `level_count` differs
11. `min_trades` → `sample_warning` (thin groups still returned)
12. `available=False` when column missing **or** only empty names
13. `available=True` only with ≥1 non-empty analyzable combo
14. Null `r_multiple` excluded; `r_multiple == 0` counted but not a win
15. `format_display_combo` uses explicit anchor only when present in tokens

**Out of scope:**

- Any page changes
- Any engine/signal changes
- `analytics/__init__.py` re-exports (optional later)
- Docs beyond this plan status (glossary waits for UI PR)
- Presentation filtering / hide-below-min logic (UI owns that in PR 2)

**Regression safety:**

- Pure additive module
- Full suite green; no golden updates
- PR body includes regression-safety paragraph

**Acceptance:**

- Unit tests pass (including unfiltered partition identity)
- Helpers importable from
  `thesistester.analytics.confluence_attribution`
- No Streamlit / session_state / `__init__.py` changes

**Forbidden paths in PR 1 diff:**

```text
thesistester/engine/**
pages/**
tests/fixtures/golden/**
```

---

### PR 2 — Backtest UI wiring + honesty docs

**Title:** `feat(backtest): confluence combo attribution breakdown`

**Depends on:** PR 1

**Scope:**

- Wire `confluence_attribution_summary(_display_trades, ...)` into
  `pages/7_Backtest.py` as a **collapsed expander** near Breakdown
- Mode-aware caption + membership double-count warning + diagnostic /
  observed-only caption
- Conditional 3c tested-level-only caption
- Controls: `min_trades` (default 10), hide-small-samples (**default ON**)
- Page-level presentation filter for hide-below-min (analytics remains unfiltered)
- Anchor-aware `display_combo` via `format_display_combo` + session `setup_config`
- Docs:
  - `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
  - `docs/METRICS_GLOSSARY.md`
  - `docs/ARCHITECTURE.md` (brief)
  - this plan → Phase 2 complete

**UI acceptance criteria:**

1. Existing Breakdown tab labels/order/behavior unchanged (diff must not alter
   the three-tab `st.tabs([...])` call).
2. New UI is a collapsed expander; unused/collapsed leaves legacy outputs alone.
3. With Focus active, combo tables use focused trades.
4. With no trades / missing columns / only empty names → calm info, no exceptions.
5. Anchor and global runs both produce tables from `level_names`.
6. Captions state diagnostic nature + observed-only + selection-effects
   (not proof of edge).
7. With hide-below default ON, thin `sample_warning` rows are not shown; turning
   it off reveals them without recomputing analytics semantics.

**Out of scope:**

- Soft pairwise view (PR 4 — next research priority)
- Time Analysis integration
- Persistence / report export sections
- Setup Builder changes
- Engine changes
- Refactors of existing Breakdown tab metric logic

**Regression safety:**

- No engine/golden touch
- Expander only; do not reorder/rename existing tabs
- Avoid large page refactors in the same PR

**Forbidden paths in PR 2 diff:**

```text
thesistester/engine/**
tests/fixtures/golden/**
```

**Suggested manual check matrix:**

| Run | Expect |
|---|---|
| Global, 5 levels, min=2 | Multi-token combos; parsed token count ≥ 2 |
| Global, min=1 | Includes 1-token combos |
| Anchor, 1+4, min_valid=1 | Combos of size ≥ 2 when names include anchor+supports |
| 3c trigger run | Caption notes tested-level-only name semantics |
| Focus window with trades | Counts shrink vs unfocused |
| Focus empty | Info only |

---

### PR 3 — Direction cross-tab + polish (optional; ship if pain appears)

**Title:** `feat(backtest): confluence combo × direction summary`

**Depends on:** PR 2

**Scope:**

- Add optional table: exact combo × direction metrics
- Add download CSV buttons for the three MVP frames (optional)
- Cap/display helpers: top N combos by `|total_r|` with “show all” toggle if
  cardinality is high
- Extra unit tests for cross-tab helper
- Docs: glossary note for cross-tab

**Out of scope:**

- Soft pairwise view (PR 4)
- Report export markdown section (can be PR 3b if desired)

**Regression safety:** Additive only; default view remains the three MVP tables.
**Priority note:** Prefer PR 4 over PR 3 if research bandwidth is limited.

---

### PR 4 — Soft pairwise attribution (analytics-only; recommended soon after MVP)

**Title:** `feat(analytics): soft pairwise confluence attribution view`

**Depends on:** PR 2 (UI) or PR 1 (helpers-only first)

**Recommended split:**

- **PR 4a:** helpers + tests for pair explosion
  (`summarize_by_level_pairs`, optional `anchor_partner` mode)
- **PR 4b:** Backtest UI sub-tab/expander section + honesty captions + docs

**Product lock for pair mode:**

| Input | Pair definition |
|---|---|
| Generic / global / unknown | All unordered pairs among distinct tokens |
| Anchor-aware | Only when session `setup_config.confluence_mode == "anchor_rules"` **and** `anchor_level` is known; emit `anchor\|Li` for each non-anchor token present. Otherwise fall back to generic pairs — **never** guess anchor from first token |

**Why reject first-token heuristic:** global price-sort puts cheapest level
first, not an anchor. Guessing would mislead.

**Regression safety:** Still no engine changes; pure attribution.

---

### PR 5 — Downstream consumers (explicitly later)

Only after PR 2 proves usefulness:

| PR | Scope |
|---|---|
| 5a | Time Analysis: optional primary/secondary group = combo key / level count |
| 5b | Report export markdown section (diagnostic) |
| 5c | Research bundle optional artifact `confluence_combo_summary.parquet` |
| 5d | Assistant read-only summarization over combo tables |

Each is independently shippable; none should block MVP.

---

## 12. Test plan (normative)

### 12.1 Unit tests (PR 1)

File: `tests/test_confluence_attribution.py`

Minimum cases:

```text
parse_level_names:
  - None / NaN / "" / "nan" → []
  - "A|B" → ["A","B"]
  - "A, B" → ["A","B"]
  - " A|A|B " → ["A","B"]

exact_combo_key:
  - "B|A" == "A|B"
  - empty → __empty__

summarize_by_exact_combo:
  - two trades same set different raw order merge
  - metrics match hand-computed avg/total/win_rate
  - unfiltered partition identity: sum(trade_count)/sum(total_r) == analyzable universe
  - thin groups remain present with sample_warning=True

summarize_by_level_membership:
  - one trade A|B increments both A and B trade_count
  - membership total_r may exceed overall total_r (double-count)
  - empty-name trade contributes zero membership rows

summarize_by_level_count:
  - uses parsed distinct token count
  - when stored level_count disagrees (e.g. 3 vs parsed 1), group by parsed

format_display_combo:
  - anchor present → anchor|sorted(rest)
  - anchor absent / None → canonical sorted key
  - never invents an anchor from first token

confluence_attribution_summary:
  - missing column → available False
  - only empty names → available False (empty_level_names_count reported)
  - ≥1 non-empty analyzable combo → available True
  - mixed null r_multiple excluded from counts
  - r_multiple == 0 counted, not a win
```

### 12.2 UI / integration (PR 2)

Prefer pure rendering decisions tested if helpers are extracted; otherwise
manual checklist in PR body + full pytest suite.

Do **not** add brittle Streamlit runtime tests.

### 12.3 Regression suite gates

Every PR:

```bash
python -m pytest tests/test_confluence_attribution.py -q
python -m pytest tests/ -q
```

No golden regeneration expected. If a PR accidentally touches engine files,
stop and re-scope.

---

## 13. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Exact string grouping splits same sets (`A\|B` vs `B\|A`) | High (correctness) | Canonical sorted key (locked) |
| View C uses stored `level_count` and disagrees with A/B on `3c` | High (correctness) | View C = parsed token count only (locked) |
| Users treat membership rows as additive PnL | High (honesty) | Mandatory caption + ASSUMPTIONS entry |
| Cherry-picking best `total_r` across many combos | High (honesty) | Hide below `min_trades` default ON + observed-only/diagnostic caption |
| Nested sets hide pair edge (`A\|B` vs `A\|B\|C`) | Medium (research gap) | Elevate soft pairwise PR 4 after MVP |
| Combo table explosion with min=1 global | Medium (UX) | Observed-only rows + default UI sample filter + optional top-N in PR 3 |
| Analytics drops thin samples and breaks partition tests | Medium (correctness) | Filter is UI-only; summarize_* returns all groups |
| 3c `level_names` semantics differ from full zone | Medium (interpretation) | Conditional UI caption + glossary |
| Accidental engine “fix” for pairwise zones | High (regression) | Explicit non-goal; PR checklist forbids engine files |
| Focus confusion (post-hoc subset) | Medium | Use `_display_trades`; keep Focus caveat |
| Dual / third `summarize_by_group` APIs | Medium (drift) | Private lean `_summarize_r` only; do not reuse time_analysis |
| Adding a 4th Breakdown tab alters legacy chrome | Medium (UI regression) | Collapsed expander only (locked) |
| Performance on large trade frames | Low | Vectorized pandas explode; MVP datasets are research-scale |

---

## 14. Implementation sequence (developer guide)

### Build order

```text
PR 1 analytics helpers + tests
  → PR 2 Backtest expander UI + docs   (= MVP)
    → PR 4 soft pairwise attribution   (recommended next)
      → PR 3 direction / CSV / top-N    (only if UX pain)
        → PR 5a/b/c/d downstream consumers (optional)
```

### Suggested implementation steps inside PR 1

1. Create module skeleton with empty-frame helpers and constants.
2. Implement `parse_level_names` + `exact_combo_key` + `format_display_combo`
   + unit tests first.
3. Implement `attach_combo_columns` (`level_token_count` = parsed distinct count).
4. Implement private lean `_summarize_r` (prev30m-shaped metrics + `sample_warning`).
5. Implement the three summarize functions on top of `_summarize_r`
   (**return all groups**; do not drop thin samples).
6. Implement `confluence_attribution_summary` with tightened `available` contract.
7. Add unfiltered partition-identity + stored-`level_count`-disagreement +
   empty-membership tests.
8. Leave `analytics/__init__.py` unchanged; import submodule directly.
9. Run focused then full tests.

### Suggested implementation steps inside PR 2

1. Import summary / display helpers in `pages/7_Backtest.py` (submodule import).
2. Add **collapsed expander** near Breakdown; do not touch the three-tab call.
3. Compute only when `_display_has_trades`; pass `_display_trades`.
4. Controls: `min_trades=10`, hide-small **default ON**.
5. Apply presentation filter in the page after summary returns.
6. Render three tables; mode / membership / diagnostic / observed-only /
   conditional 3c captions.
7. Use `format_display_combo` with session `setup_config.anchor_level` when
   `confluence_mode == "anchor_rules"`.
8. Update honesty docs (incl. null-R vs sibling Breakdown note; observed-only).
9. Manual matrix check (global + anchor + 3c if available).
10. Full pytest.

### Definition of done (MVP = PR 1 + PR 2)

- [ ] Researchers can open Backtest expander and see exact combo / membership /
  parsed level-count R breakdowns
- [ ] Works for both global cluster and anchor setups without mode-specific
      engine paths
- [ ] Existing Breakdown tabs untouched; no engine/signal/fill changes
- [ ] Honesty caveats visible in UI and docs (membership, 3c, selection effects)
- [ ] Exact-combo partition tests green; full suite green; no golden diffs

---

## 15. Acceptance checklist (copy into PR bodies)

### PR 1

- [ ] New analytics module + tests + plan status only
- [ ] No page/engine/persistence/`analytics/__init__.py` changes
- [ ] Empty/missing/delimiter/canonicalization tests included
- [ ] View C groups by parsed token count (disagreement fixture included)
- [ ] Exact-combo **unfiltered** partition identity asserted
- [ ] Thin groups returned with `sample_warning` (not dropped in analytics)
- [ ] `available` requires ≥1 non-empty analyzable combo
- [ ] Membership double-count + empty-name non-emission asserted
- [ ] `format_display_combo` tested (explicit anchor only)
- [ ] Full suite green
- [ ] Regression-safety paragraph in PR body

### PR 2

- [ ] Uses `_display_trades`
- [ ] Collapsed expander only; three Breakdown tabs untouched in diff
- [ ] Hide-below-`min_trades` defaults ON as a **page presentation filter**
- [ ] Calm empty/missing/only-empty-names states
- [ ] Mode-aware or neutral caption present
- [ ] Membership + diagnostic/observed-only/selection-effects captions present
- [ ] Conditional 3c tested-level-only caption when applicable
- [ ] ASSUMPTIONS + METRICS_GLOSSARY updated (incl. null-R note)
- [ ] No engine / golden files in diff
- [ ] Full suite green

### PR 3 / PR 4

- [ ] Additive views only
- [ ] No anchor-guessing heuristic from token order
- [ ] Anchor-aware pairs only via session `setup_config.anchor_level`
- [ ] Pair/membership double-count honesty captions present
- [ ] Docs/captions updated for any new double-count view
- [ ] Full suite green

---

## 16. Open questions (resolved for MVP)

| Question | Resolution |
|---|---|
| Persist summaries? | No for MVP |
| Change engines to emit pairwise zones? | No — deferred / likely never for default path |
| Put view in Time Analysis first? | No — Backtest first (closest to R outcome review) |
| Require `setup_name` on trades? | No for MVP |
| Sort combo key or keep raw engine order? | Canonical sort for grouping (locked) |
| Include soft pairwise in MVP? | No — PR 4 soon after |
| 4th Breakdown tab vs expander? | **Expander only** (locked) |
| View C: stored `level_count` or parsed names? | **Parsed distinct token count** (locked) |
| Reuse `time_analysis.summarize_by_group`? | **No** — private lean `_summarize_r` |
| When is `available=True`? | Column present **and** ≥1 non-empty analyzable combo |
| Default hide thin samples? | **ON** (UI presentation filter; analytics unfiltered) |
| Modify `analytics/__init__.py` in PR 1? | **No** — submodule import |
| Rows = theoretical subsets? | **No** — observed traded combos only |

No blocking open questions remain for PR 1–2.

---

## 17. Future (explicitly out of this proposal’s MVP)

1. Engine option: “emit separate zones per valid confluence” (major behavior
   change; needs its own regression-safe plan and golden gates).
2. Setup Builder assistant that proposes dropping weak confluence rules based
   on membership stats (overfit risk; needs validation workflow).
3. Cross-run meta-analysis across saved research bundles.

---

## 18. Status tracker

| Phase | PR | Status |
|---|---|---|
| Phase 0 | This proposal (+ 2026-08-09 review locks + polish) | Complete |
| Phase 1 | PR 1 analytics helpers | **Implemented** (`thesistester/analytics/confluence_attribution.py`, `tests/test_confluence_attribution.py`) |
| Phase 2 | PR 2 Backtest expander UI + docs | **Implemented** (`pages/7_Backtest.py` expander; ASSUMPTIONS / METRICS_GLOSSARY / ARCHITECTURE) |
| Phase 4 | PR 4 soft pairwise attribution (recommended next) | Not started |
| Phase 3 | PR 3 cross-tab / polish (if UX pain) | Not started |
| Phase 5 | Downstream consumers | Not started |

---

## 19. Appendix A — Example fixtures for tests

```python
trades = pd.DataFrame(
    {
        "trade_id": [1, 2, 3, 4, 5],
        "entry_timestamp": pd.to_datetime(
            [
                "2024-01-02 09:31",
                "2024-01-02 09:40",
                "2024-01-02 10:05",
                "2024-01-02 10:20",
                "2024-01-02 11:00",
            ]
        ),
        "r_multiple": [1.0, -1.0, 0.5, None, 0.25],
        "level_count": [2, 2, 3, 1, 3],  # trade 5: stored count disagrees on purpose
        "level_names": [
            "pdHigh|VWAP_rolling_1h",
            "VWAP_rolling_1h|pdHigh",  # same set, flipped
            "pdHigh|VWAP_rolling_1h|pdPOC",
            "",
            "pdHigh",  # 3c-like: names thinner than stored level_count
        ],
        "direction": ["long", "long", "short", "long", "long"],
        "trigger": ["touch", "touch", "touch", "touch", "3c"],
    }
)
```

Expectations:

- Exact combo rows merge trades 1 and 2 under `VWAP_rolling_1h|pdHigh`
  (sorted key).
- Partition: analyzable trades are ids 1,2,3,5 (id 4 null R excluded);
  `sum(trade_count)` / `sum(total_r)` over exact-combo rows matches that universe.
- Membership: `pdHigh` appears in trades 1–3 and 5; `pdPOC` only in trade 3.
- Empty bucket would include trade 4 only if `r_multiple` non-null — here excluded.
- Level-count view: parsed counts → `2` has trades 1–2; `3` has trade 3; `1`
  has trade 5 — **not** stored `level_count=3` for trade 5.
- `available=True` because nonempty combos exist; a frame of only `""` names
  with non-null R would be `available=False`.

---

## 20. Appendix B — Why this is the right seam

The user’s desired research loop is:

```text
configure confluence thesis
  → generate zones/signals/trades
  → inspect which combinations earned R
  → tighten selected levels / rules / min thresholds
  → re-run
```

ThesisTester already stores the combination on each trade. The missing piece is
**attribution analytics**, not more confluence machinery.

Building at the analytics seam:

- preserves reproducibility of historical backtests,
- avoids golden/engine risk,
- serves both confluence modes,
- and leaves the door open for a soft pairwise view (PR 4) that matches the
  “anchor + any one level” / nested-pair mental model without multiplying fills.

---

## 21. Appendix C — Review locks checklist (copy into implementation PRs)

Before coding PR 1 / PR 2, confirm these locks:

1. [ ] View C = parsed distinct token count from `level_names` (not stored `level_count`)
2. [ ] `available=True` only with ≥1 non-empty analyzable combo
3. [ ] UI = collapsed expander; three Breakdown tabs untouched
4. [ ] Private lean `_summarize_r`; no `time_analysis.summarize_by_group`
5. [ ] Exact-combo **unfiltered** partition identity unit test
6. [ ] Hide below `min_trades` defaults ON in UI; analytics does not drop rows
7. [ ] Example raw by earliest `entry_timestamp` / `trade_id` (with fallbacks)
8. [ ] Anchor display key only from session `setup_config.anchor_level`
9. [ ] No first-token-as-anchor heuristic
10. [ ] Soft pairwise is the preferred post-MVP research follow-on
11. [ ] Rows are observed traded combos, not theoretical subsets
12. [ ] PR 1 leaves `analytics/__init__.py` unchanged (submodule import)
