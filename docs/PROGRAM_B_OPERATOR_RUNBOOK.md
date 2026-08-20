# Program B — operator / bot runbook

**Give this file to the bot that will run the studies.**  
**YAMLs:** `examples/studies/program_b/`  
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
| Wave 0 | 50 anchors **alone** | 50 | `progB_w0_solo.yaml` |
| Waves 1–8 | same 50 × 22 confirms | 1,100 | 24 family YAMLs |
| **Total** | | **1,151** | 26 files (`manifest.yaml`) |

Order: **smoke → Wave 0 → Wave 1 MA → rVWAP → pivot → Wave 2 … Wave 8.** Do not skip ahead because a cell is green. Do not drop a name because solo E < 0.

---

## 1. Locks (do not edit)

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

All 26 YAMLs already stamp these. If a YAML disagrees with this table, **stop** — do not “fix” tokens by hand. Re-run `generate_program_b_yaml.py`.

---

## 2. Preconditions

1. Code tree includes **AO1** (empty `partner_levels: [[]]` + `min_valid_confluences: 0` expands). `main` at/after PR #423.
2. Dataset file exists. Default path in YAML is `data/mnq_15s.csv`. **Replace** `study.dataset.path` in every file with the same 15s Quantower History Exporter CSV used on Data. Same path for all 26 studies.
3. Expand-validate once after the path edit:

```bash
PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py
```

Expect: `ok 26 studies / 1151 cells`. If this fails, do not run.

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

---

## 4. Run list (do in this order)

| # | File | Cells | `min_valid` |
|---|---|---:|---:|
| 0 | `progB_smoke_ONH_SMA50_5min.yaml` | 1 | 1 |
| 1 | `progB_w0_solo.yaml` | 50 | 0 |
| 2 | `progB_w1_ext_ma.yaml` | 144 | 1 |
| 3 | `progB_w1_ext_rvwap.yaml` | 24 | 1 |
| 4 | `progB_w1_ext_pivot.yaml` | 96 | 1 |
| 5 | `progB_w2_open_ma.yaml` | 96 | 1 |
| 6 | `progB_w2_open_rvwap.yaml` | 16 | 1 |
| 7 | `progB_w2_open_pivot.yaml` | 64 | 1 |
| 8 | `progB_w3_range_ma.yaml` | 120 | 1 |
| 9 | `progB_w3_range_rvwap.yaml` | 20 | 1 |
| 10 | `progB_w3_range_pivot.yaml` | 80 | 1 |
| 11 | `progB_w4_profile_ma.yaml` | 108 | 1 |
| 12 | `progB_w4_profile_rvwap.yaml` | 18 | 1 |
| 13 | `progB_w4_profile_pivot.yaml` | 72 | 1 |
| 14 | `progB_w5_svwap_ma.yaml` | 48 | 1 |
| 15 | `progB_w5_svwap_rvwap.yaml` | 8 | 1 |
| 16 | `progB_w5_svwap_pivot.yaml` | 32 | 1 |
| 17 | `progB_w6_sp_ma.yaml` | 48 | 1 |
| 18 | `progB_w6_sp_rvwap.yaml` | 8 | 1 |
| 19 | `progB_w6_sp_pivot.yaml` | 32 | 1 |
| 20 | `progB_w7_apoc_ma.yaml` | 24 | 1 |
| 21 | `progB_w7_apoc_rvwap.yaml` | 4 | 1 |
| 22 | `progB_w7_apoc_pivot.yaml` | 16 | 1 |
| 23 | `progB_w8_prev30m_ma.yaml` | 12 | 1 |
| 24 | `progB_w8_prev30m_rvwap.yaml` | 2 | 1 |
| 25 | `progB_w8_prev30m_pivot.yaml` | 8 | 1 |

Smoke must finish `status=ok` before Wave 0. Wave 0 answers “which levels have +E alone.” Pair waves still run for **every** name.

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

Do not `study promote` unless the human names a cell. Promote writes a draft only — never auto-run it. Do not `--admit-tod` from a green 30m pocket.

---

## 6. Never

- Invent tokens (`Pivot_1min_*`, `SMA_50_15min`, `RTH_High`, floor PP/R1).
- Put `dVWAP` in `partner_levels`.
- Put `[]` in a `min_valid: 1` study, or `min_valid: 1` on Wave 0.
- Cartesian 40 vs 80, 10 vs 20, touch vs 3c, cost-on vs cost-off.
- Enable `grid` / `validation` / `walk_forward` / `factors.otf`.
- Lower `min_trades` below 30.
- Mix these YAMLs with Program A desk studies.
- Hand-edit core/partner lists. Change the generator, regenerate, re-validate.

---

## 7. Copy-paste bot prompt

```text
You run ThesisTester Program B. Read and follow docs/PROGRAM_B_OPERATOR_RUNBOOK.md
exactly. YAMLs are in examples/studies/program_b/. Do not invent tokens or axes.

1. Confirm the tree has AO1 (empty partner_levels + min_valid 0 expands).
2. Set study.dataset.path in every YAML to the operator’s MNQ 15s Quantower HE CSV.
   Same path for all 26 files.
3. PYTHONPATH=. python3 examples/studies/program_b/validate_program_b_yaml.py
   Must print: ok 26 studies / 1151 cells. Stop if it fails.
4. Run the manifest in listed order. Smoke first.
   For each file:
     python -m thesistester study expand <yaml> --output-dir results/studies/<name>
     python -m thesistester study run <yaml> --output-dir results/studies/<name>
     python -m thesistester study report <output-dir>
   workers: 1. No --confirm (every file is < 200 cells). No --force on finished dirs.
5. After each report, log every cell: core, partners, n, expectancy_r, PF, max DD.
   Interpret only at n>=30. Coin-flip hold if |E|<0.03 or PF in [0.95, 1.05].
   +E only if n>=30 and E>=0.03 and PF>1.05. Descriptive, not Admit.
6. Do not promote, do not Admit ToD, do not touch the Program A desk page.
7. If expand/run fails, stop and report the file + error. Do not patch YAML tokens.
```
