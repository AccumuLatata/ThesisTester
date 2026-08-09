# Regression-Safe Implementation Plan: Confluence Combo Attribution (Backtest)

**Status:** Proposal — not started  
**Document type:** Focused analytics / Backtest UX implementation plan  
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related docs:**  
`docs/anchor_confluence_regression_safe_plan.md`,  
`docs/PREV30M_VWAP_IMPLEMENTATION_PLAN.md`,  
`docs/ASSUMPTIONS_AND_LIMITATIONS.md`,  
`docs/METRICS_GLOSSARY.md`,  
`docs/ARCHITECTURE.md`

**Date:** 2026-08-09

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
| Primary surface | Backtest page → Breakdown section |
| Compute model | Pure post-trade analytics from `trades` DataFrame |
| Persistence (MVP) | None — recompute on the fly (like Time Analysis / prev30m hit R) |
| Engine changes (MVP) | **None** |
| Signal / zone changes (MVP) | **None** |
| Required trade columns | `level_names`, `r_multiple` (plus optional `level_count`, `direction`, `trigger`, `level_source_mode`) |
| Core views (MVP) | Exact combo · Level membership · Level count |
| Optional view (PR 3) | Direction × combo cross-tab |
| Closest precedent | `thesistester/analytics/prev30m_vwap_hit.py` |
| Golden-master impact | None (no engine touch) |

**Feasibility:** High. Trades already carry `|`-joined `level_names` and
`level_count` from zones → signals → `simulate_trades`. No schema migration is
required for MVP.

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
| `anchor_level`, `valid_confluence_count` | Zones | Inferable from `level_names` for many cases; do not require join |
| `setup_name` | Signals (often), not reliably on trades | Out of MVP cross-setup grouping |
| `confluence_mode` | Setup / zones | Caption from session context if available; not required for core tables |

### 4.3 Existing grouping precedents

| Precedent | Location | Reuse |
|---|---|---|
| Rich group metrics + `sample_warning` | `analytics/time_analysis.py::summarize_by_group` | Prefer for metric richness |
| Minimal group metrics | `analytics/metrics.py::summarize_by_group` | Avoid dual-API confusion; do not extend for this feature |
| Backtest Breakdown tabs | `pages/7_Backtest.py` | UI insertion point |
| Focused subset display | `_display_trades` on Backtest | Combo analytics must use `_display_trades` |
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
3. Deduplicate tokens while preserving first-seen order for raw display.
4. Build **exact_combo_key** = tokens sorted lexicographically, joined by `|`.
5. Empty / null / `"nan"` → bucket `__empty__` (display label: `(no level names)`).

Why sort: global price-order can emit `A|B` and `B|A` for the same set across
bars; unsorted grouping would falsely split identical sets.

Raw unsorted `level_names` may be shown as a secondary “example raw” column
(first seen), but metrics always group on the canonical key.

#### View B — Level membership

Explode each trade into one row per distinct level token, then group by level.

Honesty caveat (must appear in UI + docs):

> Membership attribution **double-counts** trades across levels. A trade with
> `pdHigh|VWAP` contributes to both `pdHigh` and `VWAP` rows. Use this to find
> useful participants, not as an additive PnL decomposition.

#### View C — Level count

Group by `level_count` when present; otherwise by parsed token count from
`level_names`. Null/empty → `(unknown)`.

This answers: do denser confluences outperform thinner ones?

### 5.2 Metrics (locked)

Each summary table includes at least:

| Column | Definition |
|---|---|
| `group` / view-specific key | Combo key, level name, or level count |
| `trade_count` | Rows in group with non-null `r_multiple` |
| `win_rate` | Share of `r_multiple > 0` |
| `avg_r` | Mean `r_multiple` |
| `median_r` | Median `r_multiple` |
| `total_r` | Sum `r_multiple` |
| `sample_warning` | True when `trade_count < min_trades` |

Defaults:

- `min_trades = 10` for warning flag (configurable in UI; clamp ≥ 1).
- Sort default: `total_r` descending, then `trade_count` descending.
- Optional UI toggles: sort by `avg_r`, filter `trade_count >= min_trades` only.

Do **not** invent new expectancy definitions; reuse existing R conventions from
`METRICS_GLOSSARY.md` / Time Analysis.

### 5.3 Trade universe (locked)

| Context | Universe |
|---|---|
| Standard Backtest | `_display_trades` (respects Focus window when active) |
| Admit constrained re-sim | Session trades after Admit (already constrained) |
| Walk-forward OOS (future) | Same helpers on OOS trades DF; not MVP UI |
| Empty / missing `level_names` column | `available=False`; show info caption, no crash |

### 5.4 Mode-aware copy (locked)

| Mode | Caption emphasis |
|---|---|
| Anchor / `anchor_rules` | “Combinations are anchor + currently valid confluence rules on the signal bar. Min valid confluences controls threshold, not pairwise splitting.” |
| Global / `global_cluster` | “Combinations are unsupervised peer clusters within tolerance. Order is canonicalized; raw price-order strings may differ.” |
| Unknown / mixed | Neutral caption; still compute from `level_names`. |

Mode detection for captions (best-effort, non-blocking):

1. Session setup / signal context `confluence_mode` if available.
2. Else `level_source_mode` dominance on displayed trades if present.
3. Else neutral.

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
2. **Additive UI.** New Breakdown tab(s) / expander; existing tabs unchanged.
3. **Fail closed in display, never crash.** Missing columns → empty tables +
   `available=False`.
4. **Focused-subset honesty.** Use `_display_trades`; keep Focus caveat visible.
5. **No golden regeneration.** Engine goldens untouched (§4.1 N/A because no
   engine touch).
6. **Docs in the same PR** that introduces user-visible behavior
   (`ASSUMPTIONS_AND_LIMITATIONS`, `METRICS_GLOSSARY`, this plan’s status).
7. **Small surface area per PR.** Pure helpers land before UI wiring.

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

def parse_level_names(raw: Any) -> list[str]:
    """Normalize |/, strip, drop empties, de-dupe preserving order."""

def exact_combo_key(raw: Any) -> str:
    """Canonical sorted key; EMPTY_LEVEL_NAMES_KEY when none."""

def attach_combo_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """Return copy with exact_combo_key, level_token_count, parsed helper cols."""

def summarize_by_exact_combo(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame: ...

def summarize_by_level_membership(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame: ...

def summarize_by_level_count(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> pd.DataFrame: ...

def confluence_attribution_summary(
    trades: pd.DataFrame,
    *,
    min_trades: int = 10,
) -> dict[str, Any]:
    """Bundle availability + the three frames + honesty flags."""
```

Availability contract (mirror prev30m style):

```python
{
  "available": bool,          # True iff level_names present and ≥1 analyzable trade
  "trade_count": int,         # analyzable trades (non-null r_multiple)
  "empty_level_names_count": int,
  "by_exact_combo": DataFrame,
  "by_membership": DataFrame,
  "by_level_count": DataFrame,
  "warnings": list[str],      # e.g. membership double-count honesty
}
```

### 7.2 Package export

Update `thesistester/analytics/__init__.py` to export the public helpers
(same style as `prev30m_vwap_hit` exports).

### 7.3 UI wiring

Update `pages/7_Backtest.py`:

- After existing Breakdown tabs (`By trigger` / `By direction` / `By exit reason`),
  add a fourth tab: **By confluence combo**  
  **or** a dedicated expander “Confluence combo attribution” under Breakdown
  (preferred if tab overcrowding is a concern).
- Inside:
  - Caption (mode-aware)
  - `min_trades` number input
  - optional “hide below min_trades” checkbox
  - three sub-tabs or stacked tables: Exact combo / Membership / Level count
  - membership honesty caption
- Compute from `_display_trades`, not raw `trades`, when Focus is active.

Optional tiny pure UI helpers (if needed for testability):

```text
# Prefer keeping page thin; extract only if logic grows:
# pages helpers are currently tested via importlib in test_*_page_helpers.py
```

MVP recommendation: **keep logic in analytics module**; page only renders.

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
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Membership double-count; canonicalization; 3c empty names caveat |
| `docs/METRICS_GLOSSARY.md` | Define exact combo / membership / level-count attribution metrics |
| `docs/ARCHITECTURE.md` | One bullet under analytics surfaces if session keys remain unchanged |

No `ENGINEERING_PROPOSAL` milestone bump required unless product owners want it
tracked as a named research UX milestone; this plan is sufficient.

---

## 8. Semantic edge cases (normative)

| Case | Required behavior |
|---|---|
| `level_names` missing column | `available=False`; no exception |
| `level_names` null / `""` / `"nan"` | Bucket `__empty__` |
| Delimiters `,` and `\|` mixed | Normalize both |
| Duplicate tokens `A\|A\|B` | Treat as `{A,B}` for combo key / membership |
| Global price-order flip `A\|B` vs `B\|A` | Same exact_combo_key |
| Anchor order `anchor\|B\|A` | Canonical sort still groups with same set; display may show example raw |
| Single-level global (`min_confluences=1`) | Valid 1-token combos; expected and useful |
| Multi-level zone (up to 5 / anchor+N) | Exact combo uses full set; membership explodes all tokens |
| 3c tested-level-only names | Document: combo reflects signal `level_names`, which for 3c may be the tested level rather than full zone membership |
| Focus subset empty | Info message; no tables |
| Huge combo cardinality | Table renders; recommend min_trades filter; no hard truncation in MVP (optional top-N later) |
| `r_multiple` null | Exclude from metric denominators |
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

### Deferred (post-MVP, separate proposals)

| Idea | Why deferred |
|---|---|
| Pairwise **engine** emission (one zone per valid rule when min=1) | Changes trade counts / overlap / exposure; not analytics-safe |
| Soft pairwise **attribution** view (credit trade to each `anchor+level` pair present) | Useful; can be PR 4 without engine changes |
| Stamping `setup_name` / `confluence_mode` onto trades | Additive schema; useful but not required for single-run Backtest |
| Research-bundle parquet export of combo summaries | Follow prev30m/excursion pattern later |
| Time Analysis primary dimension = `exact_combo_key` | Natural follow-on after Backtest proves usefulness |
| Assistant narrative over combo tables | Depends on stable analytics API |
| Auto-suggested setup tightening from winning combos | High product risk / overfitting temptation |

### Soft pairwise attribution (recommended Phase 4, still analytics-only)

For Anchor-like reading without changing the engine:

- For each trade with tokens `[anchor?, L1, L2, ...]`, emit pair keys
  `(sorted_pair)` for every unordered pair, **or**
  for anchor mode specifically emit `anchor|Li` for each non-anchor Li present.
- Metrics grouped by those pair keys.
- Honesty: still double-counts; caption required.

This approximates the user’s “anchor + each level” mental model **without**
multiplying signals.

---

## 11. Fully scoped PRs

### PR 1 — Pure analytics foundation (no UI)

**Title:** `feat(analytics): confluence combo attribution helpers (no UI)`

**Scope:**

- Add `thesistester/analytics/confluence_attribution.py`
- Export from `thesistester/analytics/__init__.py`
- Add `tests/test_confluence_attribution.py`
- Update this plan status (Phase 1 complete)

**Must include tests for:**

1. Empty trades / None / missing `level_names`
2. Delimiter normalization (`|` and `,`)
3. Canonicalization (`B|A` == `A|B`)
4. Dedup tokens
5. Empty bucket
6. Exact combo metrics correctness on a tiny fixture
7. Membership double-count (one trade → two membership rows)
8. Level count from column vs parsed fallback
9. `min_trades` → `sample_warning`
10. `available` flag contract
11. Null `r_multiple` excluded

**Out of scope:**

- Any page changes
- Any engine/signal changes
- Docs beyond this plan status (glossary can wait for UI PR)

**Regression safety:**

- Pure additive module
- Full suite green; no golden updates
- PR body includes regression-safety paragraph

**Acceptance:**

- Unit tests pass
- Importing `thesistester.analytics` exposes new helpers
- No Streamlit / session_state changes

---

### PR 2 — Backtest UI wiring + honesty docs

**Title:** `feat(backtest): confluence combo attribution breakdown`

**Depends on:** PR 1

**Scope:**

- Wire `confluence_attribution_summary(_display_trades, ...)` into
  `pages/7_Backtest.py` Breakdown area
- Mode-aware caption + membership double-count warning
- Controls: `min_trades`, optional hide-small-samples
- Docs:
  - `docs/ASSUMPTIONS_AND_LIMITATIONS.md`
  - `docs/METRICS_GLOSSARY.md`
  - `docs/ARCHITECTURE.md` (brief)
  - this plan → Phase 2 complete

**UI acceptance criteria:**

1. Existing Breakdown tabs still render identically when new tab/expander is
   unused.
2. With Focus active, combo tables use focused trades.
3. With no trades / missing columns, shows calm info — no exceptions.
4. Anchor and global runs both produce tables from `level_names`.
5. Captions state diagnostic nature (not proof of future edge).

**Out of scope:**

- Pairwise attribution view
- Time Analysis integration
- Persistence / report export sections
- Setup Builder changes
- Engine changes

**Regression safety:**

- No engine/golden touch
- Prefer expander or additive tab; do not reorder/rename existing tabs’
  semantics
- Avoid extracting large page refactors in the same PR

**Suggested manual check matrix:**

| Run | Expect |
|---|---|
| Global, 5 levels, min=2 | Multi-token combos; level_count ≥ 2 |
| Global, min=1 | Includes 1-token combos |
| Anchor, 1+4, min_valid=1 | Combos of size ≥ 2 when names include anchor+supports |
| Focus window with trades | Counts shrink vs unfocused |
| Focus empty | Info only |

---

### PR 3 — Direction cross-tab + polish (optional but recommended)

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

---

### PR 4 — Soft pairwise attribution (analytics-only, optional)

**Title:** `feat(analytics): soft pairwise confluence attribution view`

**Depends on:** PR 2 (UI) or PR 1 (helpers-only first)

**Recommended split:**

- **PR 4a:** helpers + tests for pair explosion
  (`summarize_by_level_pairs`, optional `anchor_partner` mode)
- **PR 4b:** Backtest UI sub-tab + honesty captions + docs

**Product lock for pair mode:**

| Input | Pair definition |
|---|---|
| Generic / global | All unordered pairs among distinct tokens |
| Anchor-aware (if `anchor_level` known or first token heuristic **rejected**) | Prefer explicit session `anchor_level` when available; otherwise show generic pairs only — **do not guess anchor from token order** |

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

summarize_by_level_membership:
  - one trade A|B increments both A and B trade_count

summarize_by_level_count:
  - uses level_count column when present
  - falls back to parsed length when column absent

confluence_attribution_summary:
  - missing column → available False
  - mixed null r_multiple excluded from counts
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
| Users treat membership rows as additive PnL | High (honesty) | Mandatory caption + ASSUMPTIONS entry |
| Combo table explosion with min=1 global | Medium (UX) | `min_trades` filter + optional top-N in PR 3 |
| 3c `level_names` semantics differ from full zone | Medium (interpretation) | Document in captions/glossary |
| Accidental engine “fix” for pairwise zones | High (regression) | Explicit non-goal; PR checklist forbids engine files |
| Focus confusion (post-hoc subset) | Medium | Use `_display_trades`; keep Focus caveat |
| Dual `summarize_by_group` APIs cause inconsistency | Low | Implement metrics inside new module or call time_analysis helper deliberately; do not create a third competing public group API without reason |
| Performance on large trade frames | Low | Vectorized pandas explode; MVP datasets are research-scale |

---

## 14. Implementation sequence (developer guide)

### Build order

```text
PR 1 analytics helpers + tests
  → PR 2 Backtest UI + docs
    → PR 3 direction cross-tab / CSV / top-N polish
      → PR 4 soft pairwise attribution
        → PR 5a/b/c/d downstream consumers (optional)
```

### Suggested implementation steps inside PR 1

1. Create module skeleton with empty-frame helpers and constants.
2. Implement `parse_level_names` + `exact_combo_key` + unit tests first.
3. Implement `attach_combo_columns`.
4. Implement the three summarize functions using one private
   `_summarize_r(trades, group_col, min_trades)`.
5. Implement `confluence_attribution_summary` availability wrapper.
6. Export via `analytics/__init__.py`.
7. Run focused then full tests.

### Suggested implementation steps inside PR 2

1. Import summary helper in `pages/7_Backtest.py`.
2. Add expander/tab under Breakdown; compute only when `_display_has_trades`.
3. Add controls (`min_trades`, hide-small).
4. Render three tables with captions.
5. Update honesty docs.
6. Manual matrix check (global + anchor).
7. Full pytest.

### Definition of done (MVP = PR 1 + PR 2)

- [ ] Researchers can open Backtest and see exact combo / membership /
  level-count R breakdowns
- [ ] Works for both global cluster and anchor setups without mode-specific
      engine paths
- [ ] No engine/signal/fill changes
- [ ] Honesty caveats visible in UI and docs
- [ ] Full test suite green; no golden diffs

---

## 15. Acceptance checklist (copy into PR bodies)

### PR 1

- [ ] New analytics module only (+ exports/tests/plan status)
- [ ] No page/engine/persistence changes
- [ ] Empty/missing/delimiter/canonicalization tests included
- [ ] Membership double-count asserted
- [ ] Full suite green
- [ ] Regression-safety paragraph in PR body

### PR 2

- [ ] Uses `_display_trades`
- [ ] Existing Breakdown tabs unchanged in behavior
- [ ] Calm empty/missing states
- [ ] Mode-aware or neutral caption present
- [ ] Membership honesty caption present
- [ ] ASSUMPTIONS + METRICS_GLOSSARY updated
- [ ] No engine files in diff
- [ ] Full suite green

### PR 3 / PR 4

- [ ] Additive views only
- [ ] No anchor-guessing heuristic from token order
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
| Include soft pairwise in MVP? | No — PR 4 |

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
| Phase 0 | This proposal | **Drafted** |
| Phase 1 | PR 1 analytics helpers | Not started |
| Phase 2 | PR 2 Backtest UI + docs | Not started |
| Phase 3 | PR 3 cross-tab / polish | Not started |
| Phase 4 | PR 4 soft pairwise attribution | Not started |
| Phase 5 | Downstream consumers | Not started |

---

## 19. Appendix A — Example fixtures for tests

```python
trades = pd.DataFrame(
    {
        "trade_id": [1, 2, 3, 4],
        "r_multiple": [1.0, -1.0, 0.5, None],
        "level_count": [2, 2, 3, 1],
        "level_names": [
            "pdHigh|VWAP_rolling_1h",
            "VWAP_rolling_1h|pdHigh",  # same set, flipped
            "pdHigh|VWAP_rolling_1h|pdPOC",
            "",
        ],
        "direction": ["long", "long", "short", "long"],
    }
)
```

Expectations:

- Exact combo rows merge trades 1 and 2 under `VWAP_rolling_1h|pdHigh`
  (sorted key).
- Membership: `pdHigh` appears in trades 1–3; `pdPOC` only in trade 3.
- Empty bucket counts trade 4 only if `r_multiple` non-null — here excluded.
- Level count `2` has 2 analyzable trades (ids 1–2).

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
- and leaves the door open for a later soft pairwise view that matches the
  “anchor + any one level” mental model without multiplying fills.
