# PRT Games — one pattern, many plants

Gamified prediction training on **real telemetry**. Every game is the same loop,
so patterns transfer between games instead of fragmenting:

```
1. SEE     plant triad (RSR/LTP/RLE) + pattern frame + game plan (honest, pre-act)
2. COMMIT  prediction JSON: triad after settle + one game scalar
3. ACT     bounded, allowlisted, contained
4. GRADE   physics measures; both teachers must agree for REWARD
```

The **common pattern** is the invariant: act → plant consequence. The game scalar
is just a second lens on the same causality.

| Game | Act | Task scalar | Plant it exercises |
|------|-----|-------------|--------------------|
| Hold | `observe` | — (triad only) | Baseline drift |
| Voice | `speak` | — (triad only; GPU load dip) | GPU VRAM / RLE crush |
| Conway | `life` | `predicted_live_cells` | CPU burn + B3/S23 causality |
| Pulse | `pulse` | `predicted_mean_load_pct` | CPU load response to duty burst |

## Pulse game (`lib/pulse_plant.py`)

- Plan shown before predict: duty, seconds, cores, baseline load, total cores
- Bounded: duty ≤ 0.5, ≤ 15 s, ≤ 8 cores; fleet always stopped (`finally`)
- 5 rotating difficulty levels (duty × cores × seconds)
- Grade: frac error on mean load during burst (REWARD ≤ 15 %, PUNISH ≥ 40 %)
- Curriculum prior: `baseline + duty * (cores/total) * 100` — empirical deltas
  take over as history accumulates

## Rules for adding a game

1. Same 4-step loop — no game without a pre-act plan and a post-act measure.
2. Real telemetry only. No synthetic targets.
3. Bounded + gated: dormant plant ⇒ falls back to observe (protect host).
4. One scalar per game. Triad is always predicted too.
5. Scalar joins scaffold-fade blanking pool and STRUCTURE_GOLD truth rows.

## Symbiote (CPU host help)

GPU is stateless; CPU owns telemetry + priors. `symbiote_hint` (cpu_config.prt) injects
`[TAG:host_prior]` / `[TAG:host_delta]` / `[TAG:plant_norm]` into every predict prompt.

Doctrine: **adapt host bait to live plant** — not solo omniscience, not blind copy.
Train rows: `SYMBIOTE_GOLD` (host packet → measured truth completion).

## CPU script sample (guide ≠ truth)

`lib/prt_cpu_sample.py` builds a **script prediction** from past after-means for this act,
then adds intentional noise: **±1°C** on temps, **±0.01** on triad. Accurate enough to
compare, never perfect.

`[TAG:cpu_sample]` + rule: target **~50/50 FOLLOW↔ADAPT**.

| Mode | Meaning | Soft score |
|------|---------|------------|
| FOLLOW | stayed near sample when sample was good | REWARD |
| ADAPT | refined away when sample missed plant | REWARD |
| COPY_BLIND | glued to wrong sample | downgrades REWARD→NEUTRAL |
| SOLO | ignored good sample and missed | downgrades REWARD→NEUTRAL |

Rolling `follow_rate` among FOLLOW+ADAPT targets 0.50 (±0.15 band).
Train: `CPU_SAMPLE_GOLD`.

## PHYSICS_GOLD + tol widen (exp `prt_tol_widen_physics_gold_v1`)

Median channel error on live deep run was ~0.053 vs `reward_tol` 0.05 — tolerance wall,
not “can’t learn.” Experiment: `reward_tol_override=0.08` + `PHYSICS_GOLD` rows
(runtime prompt → measured triad, including PUNISH cycles). Trust soft-punish stays off.
Stage ladder apex thresholds unchanged.

Related: `lib/prt_symbiote.py`, `lib/prt_cpu_sample.py`, `PRT_SCAFFOLD_FADE.md`, stage ladder.
