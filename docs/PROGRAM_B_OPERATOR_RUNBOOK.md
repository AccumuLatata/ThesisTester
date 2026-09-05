# Program B — operator / bot runbook

**Give this file to the bot that will run the studies.**  
**Run 1 YAMLs (historical, long-only):** `examples/studies/program_b/`  
**Run 2 YAMLs (current product):** `examples/studies/program_b_run2/`  
**Inventory / locks:** `docs/LEVEL_VS_MA_VWAP_PIVOT_INVENTORY.md`  
**Concept:** `docs/LEVEL_COMBINATION_RESEARCH_CONCEPT.md`  
**AO1 (solo cells):** `docs/ANCHOR_ONLY_IMPLEMENTATION_PLAN.md` (must be on `main` / a tree that includes AO1)

This is a **new program**. Do **not** write results onto the locked Notion *Process and roadmap* page. Do **not** invent tokens, axes, or a required `dVWAP` partner.

---

## 0. Job

Run the locked Program B grid on MNQ and collect n / `expectancy_r` / PF per cell.

| Stage | What | Cells | StudySpec |
|---|---|---:|---|
| Smoke | `ONH` × `SMA_50_5min` | 1 | `progB_smoke_ONH_SMA50_5min.yaml` |
| Wave 0 (15s) | 41 non-VA anchors **alone** | 41 | `progB_w0_solo.yaml` |
| Waves 1–3, 5–8 | same 41 × 22 confirms | 902 | 21 family YAMLs |
| **15s total** | | **944** | 23 files (`manifest.yaml`) |
| Wave 0 VA | 9 prior-profile anchors alone | 9 | `progB_w0_va.yaml` — **tick-gated** |
| Wave 4 | same 9 × 22 confirms | 198 | 3 family YAMLs — **tick-gated** |
| **Tick total** | | **207** | 4 files (`manifest_va.yaml`) |

Catalog is still 50 anchors. VA and non-VA are different objects (TV3 tick VAP). They must not share a YAML: one named-VA token refuses the **whole** study when `dataset.tick_paths` is empty.

**15s-only (this desk):** run `manifest.yaml` only. Order: **smoke → Wave 0 (`progB_w0_solo`) → Wave 1 MA → rVWAP → pivot → Wave 2 → Wave 3 → Wave 5 … Wave 8.** Skip Wave 4 and `progB_w0_va.yaml` until a Quantower Tick–Tick–Last export is pinned. Do not skip ahead because a cell is green. Do not drop a name because solo E < 0.

---

> **Run 1 is a long-only sample.** Under `touch` + `direction: both` + `single_position`
> the same-bar short candidate is always skipped as `overlapping_position`; only longs
> fill (`docs/ASSUMPTIONS_AND_LIMITATIONS.md` §4b). Read Run 1 cells as
> "buy the touch" only. **Run 2** (`examples/studies/program_b_run2/`) is the
> corrected product (`fade` @ 1min). Do not rerun Run 1 on `touch`.

## 1. Locks (do not edit)

### Run 1 (historical)

| Lock | Value |
|---|---|
| Instrument | MNQ |
| Trigger | `touch` @ `1min` |
| Direction | `both` |
| Mode | `anchor_rules`, `from_partners: required` |
| Pair confluence | `tolerance_ticks: 10` (partner vs anchor) |
| Wave 0 zone | **Point** at live anchor (`min_valid: 0`, `partner_levels: [[]]`). Not ±10 ticks |
| Pair `min_valid` | `1` |
| SL / TP | **80 / 80** ($40 / $40, 1R) |
| Commission | `0.5` per side ($1.00 RT) |
| Slippage | `1.0` tick per side ($1.00 RT) |
| Flatten | `true`, `session_close_time: "16:00"`, `session_timezone: America/New_York` |
| Exposure | `single_position` |
| Ingest | Quantower HE, UTC, `15s_primary_derive_1m`, `subtimeframe_conservative` |
| Grid / validation / WFO | `enabled: false` |
| OTF | omitted (off) |
| ToD | post-hoc after the run; never a factor |
| `min_trades` / interpret | **30**. n=15–29 readable + noisy. Never promote n<30 |
| Coin-flip hold | n≥30 and (`|E|<0.03` or PF ∈ [0.95, 1.05]) |
| +E (descriptive) | n≥30 and E≥0.03 and PF>1.05 |
| Rank | `expectancy_r` only. Never `total_r` |
| Workers | `1` until smoke is ok; POSIX only to raise |

All generated Run 1 YAMLs already stamp these. If a YAML disagrees with this table, **stop** — do not “fix” tokens by hand. Re-run `generate_program_b_yaml.py` with default flags (do not pass `--trigger fade` onto the Run 1 directory).

### Run 2 (current)

Delta vs Run 1 only. Everything else (MNQ, `both`, `single_position`, 80/80, costs, flatten 16:00, 15s ingest, `min_trades` 30) is identical.

| Lock | Run 2 |
|---|---|
| Trigger | **`fade`** @ `1min` (`require_close_confirmation: false`) |
| `same_bar_opposite_direction` | **`raise`** — a collision is a spec error. Valid because each Run 2 cell is **one zone** (`anchor_rules`, one partner or solo point). Do not use `raise` on multi-zone `global_cluster` studies. |
| `report.random_baseline` | `enabled: true`, `n_replicas: 50` |
| Study `name` / `output_dir` | `progB_r2_*` so results do not collide with Run 1 |

```bash
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \
  examples/studies/program_b_run2/manifest.yaml
```

Expect: `ok 23 studies / 944 cells`. Smoke should finish `collision_pairs == 0` and `directional_integrity == mixed` (or a documented reason, e.g. a directional-by-construction core).

---

## 2. Preconditions

1. Code tree includes **AO1** (empty `partner_levels: [[]]` + `min_valid_confluences: 0` expands). `main` at/after PR #423.
2. Dataset file exists. **15s YAMLs already pin** `study.dataset.path` to the
   operator AMP/Rithmic 15s Quantower HE CSV. Change it only if that file moves —
   same path for all 23 files in `manifest.yaml`. Do **not** add `tick_paths` on
   those files. Parked VA YAMLs already list the generate-owned placeholder
   `dataset.tick_paths: [data/mnq_tick_last.csv]` so validate/expand succeed;
   launch still refuses until a real Tick–Tick–Last file is pinned. Do not use
   the session-20 CI tick fixture.
3. Expand-validate the 15s packet once after the path edit:

```bash
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py
```

Expect: `ok 23 studies / 944 cells`. The script expand-checks `manifest.yaml` **and**
the lock table (MNQ, exclusive `anchor_rules`, `from_partners: required`,
Wave 0 `[[]]` + `min_valid: 0`, no VA cores, no `dVWAP` partner, 80/80, costs, flatten
`16:00` `America/New_York`). A file that fails a lock is **not** printed as
`ok`. If this fails, do not run. Do not launch `manifest_va.yaml` on 15s-only.

4. Start from the repo root. `workers: 1` first (Windows-safe).

---

## 3. Per-study CLI

```bash
SPEC=examples/studies/program_b/progB_smoke_ONH_SMA50_5min.yaml
NAME=progB_smoke_ONH_SMA50_5min
OUT=results/studies/$NAME

python -m thesistester study expand "$SPEC" --output-dir "$OUT"
python -m thesistester study run "$SPEC" --output-dir "$OUT"
python -m thesistester study report "$OUT"
```

Every file in `manifest.yaml` has `cells < 200` (`confirm_above_runs: 200`). **Do not pass `--confirm` unless expand reports `run_count >= 200`.** If you merge files and go over 200, `--confirm` is required.

Soft-resume is default. Do not `--force` wipe a finished `output_dir`.

After each `report`, record for every cell: `core_level`, `partner_levels`, `trade_count`, `expectancy_r`, `profit_factor`, `max_drawdown_r`, status (ok / failed). Ranked overview is empty when all cells are n<30 — that is not a bug.

Cross-study UI readout is a **separate** planned series (Study Observatory, `docs/STUDY_OBSERVATORY_IMPLEMENTATION_PLAN.md`). This runbook stays CLI. Do not wait on that page to finish the packet.

---

## 4. Run list (do in this order)

### Run 1 (historical, `examples/studies/program_b/`)

| # | File | Cells | `min_valid` |
|---|---|---:|---:|
| 0 | `progB_smoke_ONH_SMA50_5min.yaml` | 1 | 1 |
| 1 | `progB_w0_solo.yaml` | 41 | 0 |
| 2 | `progB_w1_ext_ma.yaml` | 144 | 1 |
| 3 | `progB_w1_ext_rvwap.yaml` | 24 | 1 |
| 4 | `progB_w1_ext_pivot.yaml` | 96 | 1 |
| 5 | `progB_w2_open_ma.yaml` | 96 | 1 |
| 6 | `progB_w2_open_rvwap.yaml` | 16 | 1 |
| 7 | `progB_w2_open_pivot.yaml` | 64 | 1 |
| 8 | `progB_w3_range_ma.yaml` | 120 | 1 |
| 9 | `progB_w3_range_rvwap.yaml` | 20 | 1 |
| 10 | `progB_w3_range_pivot.yaml` | 80 | 1 |
| 11 | `progB_w5_svwap_ma.yaml` | 48 | 1 |
| 12 | `progB_w5_svwap_rvwap.yaml` | 8 | 1 |
| 13 | `progB_w5_svwap_pivot.yaml` | 32 | 1 |
| 14 | `progB_w6_sp_ma.yaml` | 48 | 1 |
| 15 | `progB_w6_sp_rvwap.yaml` | 8 | 1 |
| 16 | `progB_w6_sp_pivot.yaml` | 32 | 1 |
| 17 | `progB_w7_apoc_ma.yaml` | 24 | 1 |
| 18 | `progB_w7_apoc_rvwap.yaml` | 4 | 1 |
| 19 | `progB_w7_apoc_pivot.yaml` | 16 | 1 |
| 20 | `progB_w8_prev30m_ma.yaml` | 12 | 1 |
| 21 | `progB_w8_prev30m_rvwap.yaml` | 2 | 1 |
| 22 | `progB_w8_prev30m_pivot.yaml` | 8 | 1 |

Parked until ticks (`manifest_va.yaml`; do not launch on 15s-only). Files already
carry placeholder `tick_paths` so TV3 can load/expand; launch still refuses the
missing Tick–Tick–Last file:

| File | Cells | `min_valid` |
|---|---:|---:|
| `progB_w0_va.yaml` | 9 | 0 |
| `progB_w4_profile_ma.yaml` | 108 | 1 |
| `progB_w4_profile_rvwap.yaml` | 18 | 1 |
| `progB_w4_profile_pivot.yaml` | 72 | 1 |

Smoke must finish `status=ok` before Wave 0. Wave 0 (15s) answers “which non-VA levels have +E alone.” Pair waves 1–3 and 5–8 still run for **every** 15s name. Wave 4 / `w0_va` wait for ticks.

### Run 2 (current, `examples/studies/program_b_run2/`)

Same 23 files / 944 cells / same order. Paths are under `examples/studies/program_b_run2/`. Study names are `progB_r2_*`; write `results/studies/progB_r2_*`. Tick-gated VA is **not** in the Run 2 packet (15s only).

| # | File | Cells | `min_valid` |
|---|---|---:|---:|
| 0 | `progB_smoke_ONH_SMA50_5min.yaml` | 1 | 1 |
| 1 | `progB_w0_solo.yaml` | 41 | 0 |
| 2 | `progB_w1_ext_ma.yaml` | 144 | 1 |
| 3 | `progB_w1_ext_rvwap.yaml` | 24 | 1 |
| 4 | `progB_w1_ext_pivot.yaml` | 96 | 1 |
| 5 | `progB_w2_open_ma.yaml` | 96 | 1 |
| 6 | `progB_w2_open_rvwap.yaml` | 16 | 1 |
| 7 | `progB_w2_open_pivot.yaml` | 64 | 1 |
| 8 | `progB_w3_range_ma.yaml` | 120 | 1 |
| 9 | `progB_w3_range_rvwap.yaml` | 20 | 1 |
| 10 | `progB_w3_range_pivot.yaml` | 80 | 1 |
| 11 | `progB_w5_svwap_ma.yaml` | 48 | 1 |
| 12 | `progB_w5_svwap_rvwap.yaml` | 8 | 1 |
| 13 | `progB_w5_svwap_pivot.yaml` | 32 | 1 |
| 14 | `progB_w6_sp_ma.yaml` | 48 | 1 |
| 15 | `progB_w6_sp_rvwap.yaml` | 8 | 1 |
| 16 | `progB_w6_sp_pivot.yaml` | 32 | 1 |
| 17 | `progB_w7_apoc_ma.yaml` | 24 | 1 |
| 18 | `progB_w7_apoc_rvwap.yaml` | 4 | 1 |
| 19 | `progB_w7_apoc_pivot.yaml` | 16 | 1 |
| 20 | `progB_w8_prev30m_ma.yaml` | 12 | 1 |
| 21 | `progB_w8_prev30m_rvwap.yaml` | 2 | 1 |
| 22 | `progB_w8_prev30m_pivot.yaml` | 8 | 1 |

```bash
SPEC=examples/studies/program_b_run2/progB_smoke_ONH_SMA50_5min.yaml
NAME=progB_r2_smoke_ONH_SMA50_5min
OUT=results/studies/$NAME
python -m thesistester study expand "$SPEC" --output-dir "$OUT"
python -m thesistester study run "$SPEC" --output-dir "$OUT"
python -m thesistester study report "$OUT"
```

---

## 5. How to read a cell

| n | What you may say |
|---|---|
| n≥30 and E≥0.03 and PF>1.05 | Descriptive **+E** (not Admit, not live) |
| n≥30 and (`|E|<0.03` or PF ∈ [0.95, 1.05]) | **Hold** (coin-flip) |
| n≥30 and E<0 | Dead under this lock |
| 15≤n<30 | Readable, noisy. Not +E |
| n<15 | Unidentified |

Wave 0 vs a pair on the same core: ΔE mixes confirm value with **zone-shape** (point vs partner box). Report both. Do not call ΔE a pure confluence effect.

**Run 2 readout lock (additive):**

- A cell is **unreadable** if `directional_integrity != "mixed"` **and** the core is not a directional-by-construction level (e.g. `dSP_Above` may legitimately be short-heavy). Record the reason.
- Report `long_expectancy_r` / `short_expectancy_r` with their `n`. A cell is **+E** only if the pooled E qualifies **and** neither side has `n ≥ 30` with `E < −0.03` (a one-sided edge must be named as such, not pooled).
- Report `expectancy_minus_null_r`. A cell whose pooled E qualifies but `random_p_value_ge ≥ 0.05` is **hold**, not +E.
- Run 1 vs Run 2 on the same cell is **not** a paired comparison (different trigger). Report both rows; do not compute ΔE.

Do not `study promote` unless the human names a cell. Promote writes a draft only — never auto-run it. Do not `--admit-tod` from a green 30m pocket.

---

## 6. Never

- Invent tokens (`Pivot_1min_*`, `SMA_50_15min`, `RTH_High`, floor PP/R1).
- Put `dVWAP` in `partner_levels`.
- Put VA tokens (`pd*` / `pw*` / `pm*` VAH/VAL/POC) in a 15s YAML.
- Add `tick_paths` on any `manifest.yaml` file.
- Launch `manifest_va.yaml` on 15s-only, or swap the VA placeholder
  `data/mnq_tick_last.csv` for the session-20 CI tick fixture.
- Put `[]` in a `min_valid: 1` study, or `min_valid: 1` on Wave 0.
- Cartesian 40 vs 80, 10 vs 20, touch vs 3c, cost-on vs cost-off.
- Enable `grid` / `validation` / `walk_forward` / `factors.otf`.
- Lower `min_trades` below 30.
- Mix these YAMLs with Program A desk studies.
- Hand-edit core/partner lists. Change the generator, regenerate, re-validate.

---

## 7. Copy-paste bot prompt

Current product is **Run 2**. Do not give a bot the historical Run 1 directory
(`examples/studies/program_b/`) — that packet is `touch` + `both` +
`single_position` and is a long-only sample.

```text
You run ThesisTester Program B Run 2. Read and follow
docs/PROGRAM_B_OPERATOR_RUNBOOK.md exactly. YAMLs are in
examples/studies/program_b_run2/. Do not invent tokens or axes. Do not
rewrite examples/studies/program_b/ (Run 1, historical).

1. Confirm the tree has AO1 (empty partner_levels + min_valid 0 expands),
   DA4 (fade), DA3 (same_bar_opposite_direction), and DA5 (random_baseline).
2. 15s YAMLs already pin dataset.path to the AMP/Rithmic 15s HE CSV. Change it
   only if that file moves. Same path for all 23 files. Do not add tick_paths.
   Run 2 is 15s only — there is no manifest_va.yaml in this directory.
3. PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py \
     examples/studies/program_b_run2/manifest.yaml
   Must print: ok 23 studies / 944 cells. Stop if it fails.
4. Run the §4 Run 2 list in order. Smoke first.
   Study names / output_dir are progB_r2_*. For each file:
     python -m thesistester study expand <yaml> --output-dir results/studies/<name>
     python -m thesistester study run <yaml> --output-dir results/studies/<name>
     python -m thesistester study report <output-dir>
   workers: 1. No --confirm (every file is < 200 cells). No --force on finished dirs.
5. After each report, log every cell: core, partners, n, expectancy_r, PF,
   max DD, long_n / short_n, long_expectancy_r / short_expectancy_r,
   directional_integrity, collision_pairs, expectancy_minus_null_r,
   random_p_value_ge. Apply the §5 Run 2 readout lock. Interpret only at
   n>=30. Do not compute ΔE vs Run 1.
6. Do not promote, do not Admit ToD, do not touch the Program A desk page.
7. If expand/run fails, stop and report the file + error. Do not patch YAML tokens.
   A same-bar collision under raise is a spec error — stop and report.
```
