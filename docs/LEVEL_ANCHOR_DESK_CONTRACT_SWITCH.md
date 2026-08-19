# Switch brief: Notion desk contract ← new combination protocol

**Who this is for:** an agent that will rewrite Notion *Process and roadmap* so the desk uses the new protocol **without** losing the old page’s contract, logging, or live roadmap.

**Give the agent both files:**

1. This brief
2. `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` (realization SoT)

**Target page:** Notion *Process and roadmap* (parent: *ThesisTester - Backtesting:*). Locked 2026-08-19. Change it **on purpose**, then log the change.

**Do not touch:** `swing_3c_20_anchor` while it is running. This is a **page** switch, not a new study.

---

## 1. Job of the switch

The old Notion page is the **daily contract** (locks, sequence, never-do, logging, live roadmap).

The new repo plan is the **realization protocol** (token inventory, expand/`min_valid`, Admit path, L2 power stop, L6 vs L6b).

**Success:** Notion stays a short page you can scan at 20:00 Vienna. It absorbs the new *locks*. It links the repo plan for YAML / expand / Admit. It does **not** become a paste of the 600-line protocol.

If you dump the full protocol onto Notion and delete logging / Runs+Results / “how we decide the next run,” the switch has failed.

---

## 2. Two sources of truth (do not invert)

| Surface | Role after the switch |
|---|---|
| Notion *Process and roadmap* | **Desk contract.** Job, two products, lock table, sequence, map, never-do, logging, **live roadmap**, current scalp map, next-run gate |
| Notion *ThesisTester Runs* + *ThesisTester Results* | **The record.** Still write both after every study / add-on / ToD / audit / Admit |
| `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` | **How to emit and interpret a StudySpec.** Inventory, family catalog, expand semantics, YAML shape, coworker study prompt |

The repo plan already says it does not replace the desk page. This switch **updates** the desk page. It does not move the contract into git and abandon Notion.

---

## 3. Hard rules

1. **Do not invent a study** because you are rewriting the page. No new kill list. No L1b on killed names. No swing ToD until swing L1 finishes.
2. **Do not change widths, products, or `dVWAP` required.** Distance-audit 10 / 20 stays. Do not cartesian 10 vs 20.
3. **Do not put a killed scalp name back** because a 30m slice was green.
4. **Do not rewrite history.** Scalp ToD already ran *before* pairwise. That was an L1 diagnostic. It is not L4 for ONH pairs that do not exist yet. Keep the finding; do not Admit from it.
5. **Do not mix L6 language.** Old “rush check measures the reentry leak” is **wrong**. New: L6 = product compare; L6b = same-width leak isolate.
6. **Do not list `otf` as a normal first-screen factor.** The axis exists in StudySpec. This desk does not cartesian it. OTF = Validation matrix on a promoted single setup (`docs/research-methodology.md`).
7. **Do not use `from_partners: optional`** in StudySpec. That drops the `dVWAP` lock. Mixed required/optional is Setup Builder only.
8. **Do not write under Xai ThesisTester.** Log real metrics only. If a cell is still running, the run row says running and Results cells stay empty.
9. Keep: **Focus ≠ Admit** (the 4-day 18:00 test is not a live schedule).
10. Keep: partner set required; singles illegal; core + partners ≤ 5; partner ≠ core; never invent tokens / triggers / axes.

---

## 4. Keep / absorb / drop

### Keep verbatim (old page — operational)

- Callout: locked date; change on purpose; log the change; do not invent a study because a ToD pocket looked green
- “These two databases are the record. This page is the contract.” + links to **ThesisTester Runs** and **ThesisTester Results**
- **Job** paragraph (money, discretionary NQ/MNQ + ES/MES, ThesisTester is the lab, rankings are descriptive)
- **Two products, never one cartesian** (scalp = fade the touch; swing = wait for 3c, enter once)
- Distance-audit sentence (p25/p50/p75 = 0/0/2). Do not pick width by backtest R
- Kill-list **map** (cores, swing-only `wVWAP`/`mVWAP`, `dVWAP` is not a core, stay-off list)
- **Never do this** list, except replace the rush-check implication via the new L6/L6b lines (see absorb)
- **Logging** (one Runs row + one Results row per cell; dedupe Study + Run id + Core; same day, not next morning; 20:00 Vienna is catch-up only)
- “Write under Xai ThesisTester” ban
- **How we decide the next run:** *Ask: which step is this, and which lock does it keep? If the answer is a new factor or just this one window, it is drift. Do not run it.*
- Live **roadmap table** (statuses as of the switch). Do not reset “done” rows. Do not mark swing L1 done while it is running
- **Current scalp map:** Stay ONH; coin-flip `pwEQ`; off-map list

### Absorb from the new plan (make these desk locks — short)

Put these on the Notion page as bullets or extra lock-table rows. Do **not** paste the full protocol sections.

| New lock | One-line desk wording |
|---|---|
| Coin-flip first | If `n≥30` and (`|E|<0.03` or PF ∈ [0.95, 1.05]) → **hold**. Then promote only if `n≥30` and `E≥0.03` and `PF>1.05`. Test: `ONH` promotes; `pwEQ` holds |
| `min_valid_confluences: 1` | Required L1/L2 studies. Do not set `min_valid` to partner-set length (`min_valid: 2` fails expand on the `{dVWAP}` baseline) |
| `from_partners: required` | Study expand is all-or-nothing. Optional StudySpec partners drop the `dVWAP` lock |
| L1b | **Named coin-flips only (`pwEQ`)**. Not a replay of killed cores |
| L2 shape | Survivors only. Partner sets `[dVWAP]` (baseline) and `[dVWAP, X]`. One extra information source. No MA/pivot in first pairwise (those are later, “MA partners on survivors”) |
| L2 power | If **every** pair is `n<30`: **STOP**. Do not open all-optional discovery on the same slice |
| Admit | Only `study promote --admit-tod auto`. Engine path is `backtest.entry_window` (+ `grid.entry_window`). Setup-only `constants.entry_window` does not constrain fills. `n<30` never Admitted |
| OTF | Not a StudySpec factor on this desk. Optional Validation matrix on a **promoted single setup** |
| Exposure / flatten / costs | `exposure_policy: single_position`. Flatten: copy finished L1; new screens `true` and log it. Costs `0.5` / `1.0`. Engine omit-defaults are `allow_all` / flatten off / zero cost — those are not desk defaults |
| L6 / L6b | L6 (roadmap “rush check”) = same survivor, **two locked products**, separate studies (touch/10/40 vs 3c/20/80). That is a **product compare**. L6b (later, optional) = same width + SL/TP, touch vs 3c — that isolates the reentry leak |
| Complementary | Means **different information**. Family letters in the repo plan are a catalog, not a license to stack siblings |
| Repo link | One line: realization / YAML / expand → `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md` |

### Drop or do not carry forward as-is

| Old wording | Why |
|---|---|
| Full paste of the repo protocol onto Notion | Destroys the contract page |
| “Rush check … measures the reentry leak” as the only description | Width and trigger both change; that is L6, not L6b |
| Treating `otf` / `direction` as first-screen cartesians | Axes exist; first screen is `both` + no `factors.otf` |
| L1b / completeness retry on killed cores (`RTH_Open`, …) | Desk Type II hole, accepted. Amending it requires amending this page **on purpose** |
| “Promote if E>0 and PF≥1.0” | Would promote `pwEQ` |
| Admit via setup `constants.entry_window` alone | No-op on fills |
| Inventing a ToD factor or re-Admitting L1 ToD pockets | Already decided: thin, not Admitted |
| New factor, new width, or “just this one window” as the next run | Drift |

`global_cluster` after survivors, 2–3 marks only, may stay. It is **not** L2. First pairwise stays `anchor_rules`.

---

## 5. Sequence (desk order vs already-done work)

Keep this order on the page:

1. Kill list
2. Pairwise among survivors (2–3 marks; not a 9-way AND)
3. ToD — post-hoc 30m NY; `n≥15` readable / “solid”; **`n<30` never Admitted**; never a factor
4. Stop / target grid — survivors only; MNQ SL ≤ 80 ticks ($40)
5. Rush check — **product compare** (L6). Leak isolate is L6b, later, same width

**History (do not “fix” by re-running):**

- Scalp L1 + RTH add-on + scalp ToD are **done**. Findings stay on the roadmap.
- That ToD was on the **kill-list** sample. After L2, ToD is a **new** pass (pairs change the clock). Do not Admit from the old L1 ToD.
- Swing L1 is **running**. Next swing step is still “wait,” then swing ToD, then pairwise on swing survivors **plus** ONH.

---

## 6. Target Notion page shape

Keep it short. Suggested H2s, in order:

1. Locked callout
2. Contract + two databases
3. Job + two products
4. Locked constants (old table **plus** `min_valid: 1`, `from_partners: required`, exposure, flatten, costs)
5. Decision rules (coin-flip → promote → kill; L2 low-N stop) — five lines max
6. Sequence (five steps, L6 wording fixed)
7. Closed StudySpec (axes list may still name `otf` / `direction` as *allowed by the engine*; add: **this desk does not cartesian them on a first screen**)
8. Map (unchanged cores / stay-off)
9. Never do this (keep old bullets; add: no `from_partners: optional`; no `min_valid: 2` on a study that includes `{dVWAP}`; no optional discovery because L2 was thin)
10. Logging (unchanged)
11. Roadmap (statuses unchanged except you may add a “Realization SoT” note / repo link; do not invent new done rows)
12. Current scalp map (unchanged)
13. How we decide the next run (verbatim)
14. One link to `docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md`

Do **not** add: token inventory, family taxonomy tables, Bailey/PBO essay, YAML tutorial, 73-token list. Those stay in the repo plan.

---

## 7. Roadmap rows after the switch

Copy status/findings. Only tighten language where the old finding contradicts a new lock:

| Step | Status | Finding (keep) |
|---|---|---|
| Distance audit | done | Lock 10 / 20 |
| Scalp kill list (`scalp_touch_10_anchor`, 24) | done | Only **ONH** survives (+0.07R, n=47, PF 1.16). Descriptive. Coin-flip **`pwEQ`** holds — do not pairwise it |
| Scalp RTH add-on | done | Both killed. Do not L1b these |
| Scalp ToD | done | Thin pockets. ONH no solid green. RTH_Open 13:00 n=25 **not Admitted**. Not L4 for future pairs |
| Swing kill list | **running** | Do not edit this run |
| Swing ToD | next | After swing L1. Same n≥15 / no Admit |
| Pairwise | waiting | **ONH** + any swing survivors. `[dVWAP]` baseline + `[dVWAP, X]`. No MA in first pass. Stop if all n<30 |
| MA partners | later | L2m. Survivors only. ONH first if still the only scalp name |
| $40 grid | later | Survivors. MNQ SL ≤ 80 ticks |
| Rush check | later | L6 product compare. L6b same-width leak isolate is not this row |

Next run if the human asks for one after the page lands: **L2 ONH**, not a new kill list.

---

## 8. After you edit Notion

1. Log the **page change** (the old callout requires it): one Runs row that this contract was amended, plus what changed (coin-flip, `min_valid`, Admit path, L6/L6b, L2 stop).
2. Do **not** open a Results row for a study you did not run.
3. Do not `study expand` / `study run` unless the human names L2 and confirms dataset path.

---

## 9. Acceptance checklist

- [ ] Notion page is still a **short contract**, not a protocol dump
- [ ] Runs + Results still named as the record
- [ ] Job, two products, 10/20 widths, `dVWAP` required, `anchor_rules`, MNQ first — unchanged
- [ ] Coin-flip-first + ONH/pwEQ test cases on the page
- [ ] `min_valid: 1` and `from_partners: required` on the page
- [ ] L1b = `pwEQ` only
- [ ] L2 baseline + low-N stop on the page
- [ ] Admit = `--admit-tod auto` / `backtest.entry_window`
- [ ] OTF not a first-screen factor
- [ ] L6 vs L6b wording (old leak sentence gone as the only rush-check meaning)
- [ ] Logging, Xai ban, Focus ≠ Admit, next-run gate — still present
- [ ] Roadmap statuses not reset; swing still **running**
- [ ] Scalp map unchanged (ONH stay, pwEQ coin-flip, killed names off)
- [ ] One link to the repo plan
- [ ] Page-change logged; no new study invented
- [ ] Known hole stated once: killed cores will not get an alternate-confirm retry unless this page is amended on purpose

---

## 10. Copy-ready agent prompt

Paste this with the two files attached or checked out:

```text
You are switching the ThesisTester desk contract.

Read, in this order:
1. docs/LEVEL_ANCHOR_DESK_CONTRACT_SWITCH.md  (this brief — follow it)
2. docs/LEVEL_ANCHOR_CONFLUENCE_RESEARCH_PLAN.md  (realization SoT)
3. The live Notion page "Process and roadmap" (fetch it; do not rely on memory)

Task: rewrite that Notion page in place so it absorbs the new protocol locks
and keeps the old contract. Follow the switch brief §3–§9 exactly.

Hard rules:
- Notion stays a short daily contract. Do NOT paste the full repo protocol.
- Keep job, two products, width locks, kill-list map, logging, Runs+Results,
  Xai ban, Focus ≠ Admit, and the next-run gate verbatim in spirit.
- Absorb: coin-flip first (ONH promote, pwEQ hold), min_valid=1,
  from_partners=required, L1b=pwEQ only, L2 baseline + all-n<30 stop,
  Admit via study promote --admit-tod auto (backtest.entry_window),
  OTF = Validation matrix not a factor, L6 product compare vs L6b leak isolate,
  exposure/flatten/costs named, one link to the repo plan.
- Do not invent a study. Do not touch the running swing_3c_20_anchor run.
- Do not revive killed scalp names. Do not Admit from the already-done L1 ToD.
- Do not reset roadmap "done" rows. Swing L1 stays running.
- Change the page on purpose, then log that page change on ThesisTester Runs.
- Do not write under Xai ThesisTester.

When done, return:
- What you kept / absorbed / dropped (short table)
- Confirmation swing was not re-run
- The next-run sentence still on the page
- A link to the updated Notion page
```
