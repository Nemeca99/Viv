# PRT Scaffold Fade

Gradual removal of the prediction **container** so Viv supplies structure herself.

| Phase | Scaffold | prior_fill | Goal |
|------:|----------|------------|------|
| **1** | Full values | Allowed | Content under container (proven) |
| **2** | Partial (null fields rotate) | Only for *shown* fields | She must emit blanked keys |
| **3** | Schema / none | Denied | Self-emit full triad (+ live_cells) |

Config: `cpu_config.json` → `prt.scaffold_phase` (default **2** after Phase-1 proof).

Override per run: `run_cycle(..., scaffold_phase=2)` or batch `--scaffold-phase 2`.

## Phase 2 mechanics

- Pattern frame (norms + act deltas) stays — that is *content*, not the crutch.
- One field blanked per cycle (rotating RSR/LTP/RLE; life odd rounds blank `live_cells`).
- Completion prefix opens JSON through the blank key so decode must supply a number.
- **No REWARD** unless `self_emit_ok` on blanked fields.
- Incomplete blanked triad without self-emit → **PUNISH** (structure failure).

## Evidence metrics

- `self_emit_rate` — fraction of blanked cycles where she filled withheld keys herself
- `reward_rate` under phase 2 (expect drop vs phase 1 until how crystallizes)
- `life_loop_convergence` — still tracks triad + live_cells agreement

Phase 3 is gated: do not enable until Phase 2 `self_emit_rate` is stably useful (operator judgment).
