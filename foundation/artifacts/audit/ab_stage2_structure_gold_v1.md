# A/B: Stage-2 STRUCTURE_GOLD train (v1)

**Change:** PRT build now emits STRUCTURE_GOLD rows (partial-scaffold prompt + measured-truth completion, 75 cycles ×4) and the r=21 adapter got 120 continue steps (loss 3.44 → ~0.48).

| Window | n | REWARD | self_emit_rate | reward_rate |
|--------|---|--------|----------------|-------------|
| Baseline (batch3, pre-train) | 30 | 0 | 0.000 | 0.000 |
| Pilot (batch4, post-train) | 30 | 1 | **0.133** | 0.033 |

**Deltas:** self_emit +0.133, reward +0.033.

## What the hits look like

All 4 self-emits: `act=life`, blank=`predicted_live_cells`, `parse=json`, `prior_filled=false`, full triad self-emitted. One cycle was **both-reward** (first Phase-2 REWARD ever).

## Honest caveats

- Self-emitted live counts are structurally right but numerically rough (life-loop mean frac_error 1.38 this window).
- n=30 per window → **PROMISING_INCONCLUSIVE**. Apex gates for stage 3: reward ≥ 0.4, self_emit ≥ 0.5 over 30 phase-2 cycles.

## Next

Repeat the loop: batches → build (more STRUCTURE_GOLD from her own phase-2 cycles) → train → measure. Promote via `prt_main.py stage promote` only when `stage check` says apex.
