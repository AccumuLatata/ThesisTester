# Anchor-Only (`min_valid_confluences: 0`) — Implementation Plan

**Document type:** Focused, regression-safe implementation contract  
**Date:** 2026-08-20  
**Status:** AO1 implemented  
**Series:** **AO** (Anchor-Only). **AO0** = this plan lock. **AO1** = the one implementation PR in §4.
**Regression framework:** `docs/ENGINEERING_PROPOSAL.md` §4, §4.1, §4.2  
**Related:** `docs/ANCHOR_CONFLUENCE.md`, `docs/STUDY_RUNNER.md`, `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/AGENT_GUIDE.md`

This file is the **normative contract** for the implementation PR. Do not widen it.

---

## 0. Intent (locked)

The research question is:

> Does a **named location by itself** have positive expected value when traded
> with the existing trigger / SL / TP / cost machinery?

Today `anchor_rules` cannot answer that. A zone emits only when
`valid_count >= min_valid_confluences` and the product floor is **1**, and
empty partner lists are rejected before the detector runs. Every current
anchor cell is therefore “location **and** at least one confluence mark.”

That is a different thesis. L1 `{dVWAP}` already conditions on developing
session VWAP. It cannot be used as a location-only control.

**Wanted capability:** run `anchor_rules` with the **anchor alone** — no
partner rule, `min_valid_confluences: 0` — on both **saved setups** and
**StudySpec cells**. Global cluster, the trade engine, and the
levels → signals → backtest composition stay frozen.

---

## 1. What this is / is not

| This is | This is not |
|---|---|
| Allow **zero** valid confluence rules in `anchor_rules` only | A new factor axis, trigger, or level family |
| Opt-in: default `min_valid` stays **1**; empty rules + default still emit **no** zones | Changing `global_cluster` `min_confluences` (stays ≥ 1) |
| Point zone at the live anchor price (existing bounding-box math) | A new “anchor ± tolerance_ticks band” zone model |
| Same Setup Builder + Study Runner surfaces | A desk-sequence rewrite or a new L1 kill list |
| One narrow PR | Touching `detect_confluence_zones`, `simulate_trades`, `generate_signals` composition, OTF, Admit, combo attribution, goldens |

---

## 2. Design notes (read before coding)

### 2.1 Why the floor is 1 today

Three independent gates, all currently “≥ 1 / non-empty”:

| Gate | File | Current behavior |
|---|---|---|
| Detector | `thesistester/engine/anchor_confluence.py` | Empty `confluence_rules` → empty frame. `min_valid = max(..., 1)` |
| Setup validator | `thesistester/setup.py` | Empty rules error. `min_valid < 1` error |
| Headless setup schema | `thesistester/api.py` | `_validate_range(..., "min_valid_confluences", minimum=1)` |
| Study schema | `thesistester/study/schema.py` | Every partner-set must be non-empty |
| Study expand | `thesistester/study/expand.py` | `1 <= min_valid <= len(rules)` or fail |
| Signals UI | `pages/6_Signals.py` | Hard-stop: “Anchor mode requires at least one confluence rule.” |
| Setup Builder UI | `pages/3_Setup_Builder.py` | Info: “Select at least one confluence level.” (save then fails validator) |
| Study Builder UI | `pages/15_Studies.py` | `min_valid` widget `min_value=1`; empty partner set fails RS1 |

Lowering only the UI widget does nothing. Lowering only the validator still
hits the detector’s empty-rules early return. The surgical change is
**paired**: validator + detector + study emit, default-preserving.

### 2.2 “Do not touch the engine / pipeline” — precise freeze

The request is: do not change fills, global clustering, or pipeline
composition. It cannot mean “never open `anchor_confluence.py`.” Without
that one function, empty rules cannot emit zones.

**Frozen (do not edit):**

- `thesistester/engine/confluence.py` (`detect_confluence_zones`)
- `thesistester/engine/backtest.py` / `simulate_trades`
- `thesistester/engine/signals.py` / `signals_3c.py`
- `thesistester/engine/levels*` / catalog / defaults / `LEVEL_ENGINE_VERSION`
- `api.generate_signals` **composition** (mode branch, zone → `_generate_signals` → backtest). Allowed: the existing `min_valid` range check so a legal setup is not rejected before the detector.
- OTF, Admit / `entry_window`, combo attribution, WFA, grid, validation batteries
- Golden fixtures (`tests/fixtures/golden/**`)
- Notion desk contract / running studies (`swing_3c_20_anchor`, …)

**Allowed surface (this PR only):**

- `detect_anchor_confluence_zones` empty-rules / `min_valid` floor
- `validate_setup_config` / `build_setup_config` defaults unchanged
- `api.py` setup-field range for `min_valid_confluences` (0 legal)
- Study schema + expand pairing
- Setup Builder / Signals / Study Builder gates that currently refuse empty partners
- Same-PR docs listed in §8

### 2.3 Zone geometry (locked — do not invent a band)

Current emit math (keep):

```text
included_prices = [anchor_price] + valid_partner_prices
zone_low  = min(included_prices)
zone_high = max(included_prices)
```

Anchor-only therefore emits a **degenerate interval** `[P, P]` at the live
anchor price. `valid_confluence_count = 0`. `rule_results = "[]"`
(`json.dumps([])`). `level_names` is the **anchor token** (the existing
`"|".join([anchor_level])` of a one-name list — e.g. `"ONH"`, not a
literal `"<anchor>"` and not a trailing `|`). `level_count = 1`.

Triggers already use zone overlap (`signals.py`: bar range vs
`zone_low`/`zone_high`). Touch of a point zone means “bar high/low contains
the exact level.” `3c` / reject / break / reclaim keep their existing
definitions against that interval.

`constants.tolerance_ticks` / per-rule `tolerance_ticks` are **unused** when
there are no partners. Do **not** apply them as a halo around the anchor.
That would be a new engine semantic and would make location-only cells
incomparable to today’s L1 zones (where 10 ticks is *partner-to-anchor
distance*, not an entry band).

Honesty (must land in `ASSUMPTIONS_AND_LIMITATIONS.md`):

- Location-only zones are typically **narrower** than L1 `{dVWAP}` zones
  (L1 zone width ∈ [0, tolerance] ticks).
- Δ vs L1 is “value of requiring a second mark” **plus** a zone-width
  change. Rank on `expectancy_r`, not `total_r`. n will be larger.

If a later PR wants “location ± N ticks,” that is a new opt-in model. Out
of scope here.

### 2.4 Pairing rule (fail closed)

| `confluence_rules` / partner-set | `min_valid_confluences` | Result |
|---|---|---|
| non-empty | default `1` … `len(rules)` | **Legacy** — unchanged |
| non-empty | `0` | Legal. Count floor is off; **required** flags still gate. All-required + `0` ≡ all-required + `1` |
| empty | `≥ 1` or omitted (default 1) | **Legacy** — no zones (detector) / setup invalid (validator) |
| empty | `0` | **New** — point zone on every bar with a finite anchor price |
| empty or not | `< 0` | Invalid |

This pairing is the regression gate: existing callers that pass `[]` with
default `min_valid=1` still get an empty frame
(`tests/test_anchor_confluence.py::test_empty_rules_returns_empty_schema`
must keep passing).

### 2.5 Global cluster stays illegal as a single-level study

Study expand for `global_cluster` still sets
`min_confluences = max_confluences = len([core] + partners)`. An empty
partner-set would emit a 1-level global cell. **Forbidden.**

Schema lock: a partner-set `[]` is legal **only** when every value in
`factors.confluence_mode` is `anchor_rules` (the study does not include
`global_cluster`) **and** `constants.min_valid_confluences == 0`.

Expand lock: `global_cluster` cells with `partners == []` fail closed even
if schema were bypassed.

`global_cluster.min_confluences >= 1` in `setup.py` / `api.py` does not
change.

### 2.6 Desk protocol vs product capability

`docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` L1/L2 stay
`from_partners: required` and `min_valid_confluences: 1` with partner
`{dVWAP}`. This PR does **not** rewrite the desk sequence, does **not**
amend Notion *Process and roadmap*, and does **not** invent a study.

Optional later (not this PR): an L0 location-only screen as its own
StudySpec (`partner_levels: [[]]`, `min_valid: 0`). Capability first;
protocol amendment only if the desk asks.

A single StudySpec **may** mix `[[]]` with `[[dVWAP]]` / `[[dVWAP, X]]`
because `min_valid: 0` + `from_partners: required` keeps required partners
as a hard AND. That is the honest location-only vs L1 vs L2 comparison.
Do not force authors to split files.

---

## 3. Semantics after the change

`detect_anchor_confluence_zones` (unchanged except the two gates in §4.1):

1. Anchor column must exist; missing / non-finite anchor price skips the bar.
2. Each partner rule is evaluated as today (tolerance, required/optional,
   missing column / missing price).
3. Zone emits iff **every required rule is valid** and
   `valid_count >= min_valid`.
4. `valid_count` counts valid rules only (not the anchor).
5. **New:** zero rules and `min_valid == 0` → step 3 is true whenever the
   anchor price exists. Emit the point zone.

`generate_signals` / `run_backtest` consume that zone table as they already
do. No new signal path.

---

## 4. Implementation (AO1 — one PR)

Suggested title: `AO1: allow anchor-only zones (min_valid=0, regression-safe)`.

### 4.1 Detector — `thesistester/engine/anchor_confluence.py`

Default stays `min_valid_confluences: int = 1`.

Replace the two gates:

```text
# TODAY
if not isinstance(confluence_rules, list) or not confluence_rules: return empty
min_valid = max(int(min_valid_confluences), 1)

# AFTER
if not isinstance(confluence_rules, list): return empty
min_valid = int(min_valid_confluences)
if min_valid < 0: raise ValueError("min_valid_confluences must be >= 0")
if not confluence_rules and min_valid >= 1: return empty   # legacy
# KEEP the existing missing / blank / unknown-column anchor_level
# early-return HERE (before the bar loop). empty+0 + missing anchor
# must still return the empty schema — do not fall into the loop.
# empty rules + min_valid == 0 + finite anchor: for-loop is a no-op;
# required_valid stays True; valid_count == 0; emit point zone
```

Do not restructure the bar loop. Do not add a tolerance halo. Do not
change `ANCHOR_ZONE_COLUMNS`. Missing / blank / unknown `anchor_level`
still returns the empty schema (existing tests). Today that check runs
**after** the empty-rules return; keep it, just do not skip it on the
new empty+0 path.

`tick_size <= 0` still raises.

### 4.2 Setup validator — `thesistester/setup.py`

`anchor_rules` branch only (`global_cluster` untouched):

- Resolve `min_valid` **before** the empty-rules check.
- Omitted / null `min_valid_confluences` resolves to **1** (same default as
  `build_setup_config`, `generate_signals`, and the detector). Today the
  validator uses `config.get("min_valid_confluences", 0)` and then errors
  on `< 1`. After the floor becomes `>= 0`, keeping that `0` default would
  make empty+**omitted** look like empty+0 and silently enable the new
  path. **Forbidden.**
- `confluence_rules` may be `[]` **iff** the **resolved** `min_valid == 0`.
  Otherwise keep: “Confluence rules must be a non-empty list.”
- Floor: resolved `min_valid_confluences >= 0` (was `>= 1`). Still an integer.
- Ceiling: `min_valid <= len(rules)` still (0 ≤ 0 holds).
- Anchor-level / diagnostic / base-column / duplicate / self-as-partner
  checks unchanged.
- `build_setup_config` default `min_valid_confluences=1` unchanged.
- `generate_signals` already uses `.get("min_valid_confluences", 1)` — keep
  that default **1**.

`test_anchor_rules_empty_confluence_rules_invalid` stays: default
`_anchor_config(confluence_rules=[])` still has `min_valid=1` → invalid.

Add: empty rules + `min_valid=0` → `[]` errors. Add: empty rules +
**omitted** `min_valid` → invalid (legacy). Add: `min_valid=-1` →
error. Add: non-empty rules + `min_valid=0` → valid.

### 4.3 Headless experiment setup schema — `thesistester/api.py`

One line: `_validate_range(setup, "min_valid_confluences", …, minimum=0)`
(was `minimum=1`).

Do **not** change `_validate_range` for `min_confluences` / `max_confluences`.
Do **not** rewrite `generate_signals` composition. Today empty
`confluence_rules` **never** reach the detector: `generate_signals` calls
`validate_setup_config` first. After §4.2 they pass through. LC4
`_require_level_columns` on `[anchor] + rule levels` still works when the
rule list is empty (referenced is just the anchor). `_validate_range`
skips omitted keys; the omitted-as-1 rule lives in the setup validator.

### 4.4 Study schema — `thesistester/study/schema.py`

`factors.partner_levels` remains a non-empty **list of sets**. A **set**
may be `[]` only when:

1. `factors.confluence_mode` is present and every mode is `anchor_rules`, and
2. `study.constants.min_valid_confluences == 0` (explicit; omit still
   defaults to 1 at expand and must fail).

Otherwise keep today’s wording:
`factors.partner_levels[{i}] must be a non-empty list`.

Dual-mode studies (`[global_cluster, anchor_rules]`) still reject `[]`.
Unknown tokens / duplicates / core-in-partners / core+partners > 5
unchanged. `[]` has length 0; `0 + 1 <= 5` is fine.

No new factor axis. `from_partners` unchanged (`required` / `optional`);
irrelevant when the set is empty.

### 4.5 Study expand — `thesistester/study/expand.py`

`anchor_rules` cell:

```text
# TODAY
if min_valid < 1 or min_valid > len(confluence_rules): fail

# AFTER
if min_valid < 0 or min_valid > len(confluence_rules): fail
if min_valid >= 1 and len(confluence_rules) == 0: fail   # same incompatibility
```

`min_valid == 0` and `rules == []` is compatible. `min_valid == 0` and
non-empty rules is compatible (required flags still apply).

`global_cluster` branch: if `partners == []`, raise
`StudySpecError` (do not emit `selected_levels=[core]`, `min=max=1`).

Emitted setup for anchor-only:

```text
confluence_mode: anchor_rules
anchor_level: <core>
selected_levels: []          # already honest for anchor
confluence_rules: []
min_valid_confluences: 0
min_confluences: 1           # unused placeholder; do not change
max_confluences: 1
tolerance_ticks: <constants> # unused for zone width; keep for identity
```

`build_setup` must accept that dict after §4.2.

### 4.6 Setup Builder — `pages/3_Setup_Builder.py`

Anchor branch:

- Confluence-level multiselect may be empty.
- When empty: **assign** `min_valid_confluences = 0` (today the else
  branch only shows info and leaves the module default `1`, so save
  still fails the validator). Show `min_valid` locked to `0` (or a
  number input with `min_value=0`, `max_value=0`, value `0`) and a
  one-line caption: “Anchor only — no confluence required. Zone is the
  live anchor price.”
- Remove the blocker-only info “Select at least one confluence level.”
  (replace with the caption above).
- When one or more confluence levels are selected: keep today’s widget;
  allow `min_value=0` (optional count floor off) up to `len(rules)`.
  Default remains 1. Also change the existing
  `_safe_int_fallback(..., min_value=1)` clamp to `min_value=0` or a
  loaded `min_valid=0` setup will be forced back to 1.

Save still goes through `validate_setup_config`. No new `session_state` keys
unless a widget key already exists (`WIDGET_KEY_MIN_VALID_CONFLUENCES`).
Do not add a second mode enum.

### 4.7 Signals page — `pages/6_Signals.py`

Remove the hard-stop that refuses empty `confluence_rules` **when**
`min_valid_confluences == 0` and an `anchor_level` is set. Keep the
hard-stop when `min_valid >= 1` (legacy). This hard-stop is **not**
validator-driven (`pages/6_Signals.py` generate path); changing only
`validate_setup_config` leaves Generate dead.

`_saved_setup_generation_blockers` is already validator-driven: empty rules
+ `min_valid=1` stays a blocker; empty + `0` does not.

`_no_zones_message` (anchor): add that a missing finite anchor price, not
only missing partners, can yield no zones.

Manual Signals editor mirrors Setup Builder (`min_value=1` today; empty
branch leaves `min_valid=1` and shows “Select at least one confluence
level.”). Allow empty rules the same way: assign `min_valid=0` when the
multiselect is empty. Do not special-case global.

### 4.8 Study Builder — `pages/15_Studies.py` + `thesistester/study/builder.py`

- `min_valid_confluences` number input: `min_value=0` (default still 1).
- Partner-set multiselect may be empty. `coerce_partner_levels` already
  preserves `[]` (`out.append(tokens)` even when `tokens` is empty). Do
  not “helpfully” drop empty sets.
- `draft_warnings`: if any partner-set is `[]` and (`global_cluster` is
  selected or `min_valid != 0`), warn before emit. Emit still fail-closes
  via RS1.
- Default draft stays `partner_levels=[["SMA_50_1min"]]`,
  `min_valid=1`, both modes. **Do not** change `default_study_draft()`.

YAML-only authors do not need the Builder. Builder must not make
`[[]]` + `min_valid: 0` + `confluence_mode: [anchor_rules]` unsavable.

### 4.9 Persistence / identity

No new setup keys. No schema version bump. Existing library setups keep
`min_valid=1` and non-empty rules → byte-identical zones.

Signal-settings hash already includes `confluence_rules` and
`min_valid_confluences`. Anchor-only is a new identity, not a collision
with L1.

`local_store` rule sort on empty list is a no-op.

---

## 5. Authoring shapes (must work)

### 5.1 Setup (library / `build_setup` / R18 run)

```python
build_setup({
    "name": "ONH_anchor_only",
    "instrument": "MNQ",
    "confluence_mode": "anchor_rules",
    "anchor_level": "ONH",
    "confluence_rules": [],
    "min_valid_confluences": 0,
    "selected_levels": [],
    "tolerance_ticks": 10,          # unused for zone width
    "min_confluences": 1,           # unused placeholder
    "max_confluences": 1,
    "trigger": "touch",
    "trigger_timeframe": "1min",
    "direction": "both",
    # backtest locks unchanged
})
```

Headless: `generate_signals` → `run_backtest` with that setup must produce
zones/signals/trades without `ValueError`.

### 5.2 StudySpec (expand + run + report)

```yaml
schema_version: 1
study:
  name: scalp_touch_10_anchor_only
  constants:
    min_valid_confluences: 0          # required for [[]]
    tolerance_ticks: 10               # unused on [] cells; used if you also list [dVWAP]
    # … same product locks as L1 (trigger, flatten, costs, ingest)
  factors:
    core_level: [ONH]                 # or the kill-list
    partner_levels:
      - []                            # location-only cell
      # optional same-study controls:
      # - [dVWAP]
    confluence_mode: [anchor_rules]   # must NOT include global_cluster
    trigger: [touch]
    trigger_timeframe: [1min]
  mode_rules:
    anchor_rules:
      selected_levels: []
      anchor_level: "${core_level}"
      confluence_rules:
        from_partners: required
```

`python -m thesistester study expand SPEC --output-dir OUT` must succeed.
`study run` / `study report` use the existing execute path (no execute
edits).

Fail-closed examples (must raise `StudySpecError`):

- `partner_levels: [[]]` + omitted / `min_valid: 1`
- `partner_levels: [[]]` + `confluence_mode: [global_cluster]` or both modes
- `min_valid: 2` + `partner_levels: [[]]` or `[[dVWAP]]` (ceiling)

---

## 6. Tests (same PR)

No golden regen. No new fixture dataset. Deterministic unit tests only.

### 6.1 Detector (`tests/test_anchor_confluence.py`)

Keep:

- `test_empty_rules_returns_empty_schema` (default `min_valid=1`)
- All existing required / optional / tolerance / missing-price cases

Add:

| Test | Assert |
|---|---|
| Empty rules + `min_valid=0` + finite anchor | 1 zone; `zone_low=zone_high=zone_mid=P`; `valid_confluence_count=0`; `required_valid` true; `level_names==anchor`; `rule_results=="[]"` |
| Empty rules + `min_valid=0` + NaN anchor | empty frame |
| Empty rules + `min_valid=0` + missing anchor column | empty schema (legacy) |
| Empty rules + `min_valid=2` | empty frame (legacy pairing) |
| `min_valid=-1` | `ValueError` |
| Non-empty optional rules + `min_valid=0` + all invalid | zone still emits (count floor off; no required failed) |
| Non-empty **required** rule invalid + `min_valid=0` | empty (required still gates) |
| Existing exact-match fixture + `min_valid=1` | unchanged row |

Point-in-time: appending a future bar must not change past
anchor-only zone rows (follow `tests/test_r3_point_in_time.py` style on
this detector only — do not reopen the levels engine).

### 6.2 Setup (`tests/test_setup_config.py`)

Keep `test_anchor_rules_empty_confluence_rules_invalid`.

Add empty+0 valid; empty+**omitted** `min_valid` invalid; empty+0 then
`generate_signals` smoke (or API test); `min_valid=-1` invalid;
non-empty+0 valid; global `min_confluences=0` still invalid.

### 6.3 API (`tests/test_api.py` or LC4 neighbor)

`validate_run_spec` / `build_setup` accepts the §5.1 dict.
`generate_signals` on a 1-row levels frame with `ONH` present emits one
zone. Global setup with `min_confluences=1` unchanged.

Do **not** add a vs-random / noise / WFA case.

### 6.4 Study schema + expand

`tests/study/test_study_schema.py`:

- `[[]]` + `min_valid=0` + `confluence_mode: [anchor_rules]` validates
- `[[]]` + default/1 fails
- `[[]]` + both modes fails

`tests/study/test_study_expand.py`:

- Expand §5.2 → one run, `confluence_rules=[]`, `min_valid=0`,
  `anchor_level=ONH`
- Expand `[[]]` under `global_cluster` fails
- Existing 800/40 example fixture still expands (no partner-set is `[]`)

### 6.5 UI helpers

`tests/test_signals_page_helpers.py`:

- Keep `test_generation_blockers_anchor_empty_confluence_rules` (`min_valid=1`)
- Add: empty rules + `min_valid=0` + available anchor → no confluence-rule
  blocker

Setup Builder helpers: empty confluence selection + `min_valid=0` builds a
config that `validate_setup_config` accepts.

### 6.6 Frozen suite (must stay green, no edits unless a test encodes the old floor as the *product* contract you are extending)

Do not rewrite global confluence tests, golden-master, backtest, 3c, OTF,
Admit, combo attribution, or study execute. If a helper test asserts
“empty rules always block” **without** `min_valid=1` in the fixture, fix
the fixture to state `min_valid=1` rather than weakening the assertion.

CI: full `pytest -q` + ruff. No `GOLDEN_REGEN`.

---

## 7. Documentation (same PR)

| Doc | Change |
|---|---|
| `docs/ANCHOR_CONFLUENCE.md` | Anchor-only: empty rules + `min_valid=0`; point zone; `tolerance_ticks` unused |
| `docs/STUDY_RUNNER.md` | Partner-set `[]` legal only for exclusive `anchor_rules` + `min_valid=0` |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Location-only is a different thesis than L1; zone-width caveat; not proof of edge |
| `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` | **Capability footnote only.** Do not change L1/L2 locks (`min_valid: 1`, `{dVWAP}`). One short “product now allows L0 `[[]]`” pointer. Do not insert L0 into the desk sequence in this PR |
| `docs/AGENT_GUIDE.md` | One setup snippet with `min_valid: 0` / empty rules (plan index already landed in AO0) |
| `docs/USER_GUIDE.md` | One how-to sentence: Setup Builder can save an anchor with no confluence levels when minimum valid is 0 |
| `docs/ENGINEERING_ROADMAP.md` | AO1 status → implemented |
| This file | Status → AO1 implemented |

`thesistester/study/report.py` `format_partner_levels([])` is `""`. Do
**not** edit report.py. Location-only cells show a blank partner column;
identify them via emitted `confluence_rules: []` / `min_valid=0`.
`_slug_token([])` already returns `"empty"` — run names stay unique.

Do **not** edit `docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md` (Notion handoff).
Do **not** dump this plan onto Notion.

---

## 8. Full PR file list (budget)

**Edit**

- `thesistester/engine/anchor_confluence.py`
- `thesistester/setup.py`
- `thesistester/api.py` (range minimum only)
- `thesistester/study/schema.py`
- `thesistester/study/expand.py`
- `thesistester/study/builder.py` (`draft_warnings` only; defaults untouched)
- `pages/3_Setup_Builder.py`
- `pages/6_Signals.py`
- `pages/15_Studies.py` (`min_value=0` + empty partner set allowed)
- Tests listed in §6
- Docs listed in §7

**Do not touch**

- `thesistester/engine/confluence.py`, `backtest.py`, `signals*.py`, levels modules
- `thesistester/study/execute.py`, `report.py`, `promote.py`, `preview.py`, `launch.py`
- `thesistester/analytics/**` (combo attribution included)
- `tests/fixtures/golden/**`
- Example StudySpecs under `examples/studies/` (do not convert L1 examples to `[[]]`)
- Assistant / classic compiler / OTF / Admit

---

## 9. Per-milestone PR checklist (`ENGINEERING_PROPOSAL.md` §4.2)

- [ ] Unit tests for the new pairing (empty+0 emits; empty+1 empty; required still gates)
- [ ] Golden-master untouched; legacy detector tests still pass
- [ ] No new randomness
- [ ] Docs in the same PR (§7)
- [ ] CI green
- [ ] Small surface; PR body includes the regression-safety paragraph below

**Regression-safety paragraph (paste into the PR body):**

```text
Defaults unchanged: min_valid_confluences still defaults to 1; empty
confluence_rules with that default still return an empty zone frame and
still fail setup validation. Global-cluster min_confluences / max
caps / study emission (min=max=N) are not edited. detect_confluence_zones,
simulate_trades, and generate_signals composition are not edited.
Study [[]] is legal only for exclusive anchor_rules + min_valid=0.
No golden fixtures are regenerated.
```

---

## 10. Acceptance

1. Setup Builder can save an `anchor_rules` setup with no confluence levels
   and `min_valid=0`. Signals can generate from it. Backtest runs.
2. Headless `build_setup` → `generate_signals` → `run_backtest` with §5.1
   succeeds on a fixture that has a finite anchor column.
3. `study expand` / `study run` / `study report` of §5.2 succeeds
   (`run` needs a real dataset; expand+validate_run_spec is the CI gate).
4. Existing L1 StudySpec (`partner_levels: [[dVWAP]]`, `min_valid: 1`)
   expands and validates unchanged.
5. Dual-mode study with `[[]]` fails closed.
6. `pytest -q` green; goldens untouched.
7. A 1-partner all-required cell with `min_valid=0` matches `min_valid=1`
   zone-for-zone on a fixture (equivalence).

---

## 11. Non-goals (explicit)

- Applying `tolerance_ticks` as an anchor halo
- `global_cluster` singles (`min_confluences=1` with one selected level is
  already mechanically possible in the detector; Study emit must not start
  producing it)
- Mixed required/optional StudySpec emission (`from_partners` stays
  all-or-nothing)
- Rewriting the combination protocol sequence or Notion desk page
- New factor axis, new trigger, new combo-attribution model
- Changing `LEVEL_ENGINE_VERSION` or level math
- Auto-running or promoting any study
- Treating omitted `min_valid_confluences` as 0 in `validate_setup_config`
- Editing `study/report.py` to pretty-print empty partner sets

---

## 12. Copy-ready implementation prompt

```text
You are implementing docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md AO1 on
ThesisTester. Work regression-safe. Do not widen scope.

Intent: allow anchor_rules with no confluence partners so a location can
be traded by itself. Setups and studies. Default behavior unchanged.

Hard freeze:
- Do not edit detect_confluence_zones, simulate_trades, signals.py,
  signals_3c.py, levels modules, study execute/report/promote, analytics,
  or tests/fixtures/golden/**
- Do not apply tolerance_ticks as a band around the anchor. Point zone
  [P,P] only. level_names is the anchor token (join of a one-name list).
- Do not allow Study partner-set [] unless confluence_mode is exclusively
  anchor_rules AND constants.min_valid_confluences is an explicit 0
  (omit is not 0).
- Do not change default min_valid (1) or default_study_draft().
- validate_setup_config must resolve omitted min_valid as 1, not 0.
  Empty+omitted stays invalid.
- Keep the detector missing-anchor early-return before the bar loop.
- Setup Builder / Signals empty-partner branch must assign min_valid=0
  (today it leaves 1). Change _safe_int_fallback min_value 1 → 0 when
  partners are selected. Remove the Signals Generate hard-stop only when
  min_valid==0.
- Empty rules + min_valid>=1 must keep returning an empty zone frame
  (test_empty_rules_returns_empty_schema).
- Do not amend the desk L1/L2 locks (min_valid: 1, {dVWAP}).

Implement §4.1–§4.8, tests §6, docs §7. One PR (AO1). Follow §9 checklist.
```
