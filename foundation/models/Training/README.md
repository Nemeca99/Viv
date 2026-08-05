# Training home

This directory is the single self-contained training control plane for Viv.
It contains both the existing AIFL training lane and the custom Viv-SLM
tokenizer/transformer identity lane.  Checkpoints, runs, negative evidence,
and historical code are retained; organization is reversible and no material
is silently deleted.

## Viv-SLM governed continual training

```
Training/
  data/
    identity/                    # first curriculum; canonical V15/V43 inputs
    knowledge/                   # second curriculum; inventoried and locked
  current/
    MASTER_TRAINING_PROGRAM.json   # declarative master entry point
    TRAINING_KNOBS.json             # central training-inference knobs
    viv_slm/
      paths.py                      # canonical root resolution
      train_viv_slm_identity_v1.py  # model adapter and bounded trainer
      run_viv_slm_layer_campaign.py # generic governed engine
      run_viv_slm_layered_training_supervisor.py
      viv_slm_layer_governor.py
      model/                         # custom tokenizer/dataset/transformer
      tests/                         # current-lane focused preflight
  legacy/viv_slm/                    # frozen V1-V59 builders, probes, tests
  checkpoints/                       # indexes and future canonical copies
  evidence/                          # indexes to authoritative receipts
  runs/viv_slm/                      # future V60+ outputs
```

The old `foundation/scripts` and `foundation/lib` VSLM paths are compatibility
entry points only.  Historical contracts keep their original path strings;
the canonical engine resolves moved historical VSLM files under
`legacy/viv_slm` so their evidence remains hash-bound.  New campaigns must use
the paths in `current/MASTER_TRAINING_PROGRAM.json`.

The training-inference profile in `TRAINING_KNOBS.json` controls the prompts,
rendering context, metrics, and bounded variables used while training.  It is
separate from the main AIOS runtime inference contract and cannot authorize a
live model change.

### Canonical VSLM preflight

```powershell
L:\Continue\.venv\Scripts\python.exe -B foundation\models\Training\current\viv_slm\tests\test_viv_slm_layer_governor.py
L:\Continue\.venv\Scripts\python.exe -B foundation\models\Training\current\viv_slm\tests\test_run_viv_slm_layer_campaign.py
L:\Continue\.venv\Scripts\python.exe -B foundation\models\Training\current\viv_slm\tests\test_run_viv_slm_layered_training_supervisor.py
```

# AIFL Training home

All judge-LoRA training lives here. Base weights stay in `models/gpu/OpenAster1-128k-base-hf/`.

## Layout

```
models/Training/
  code/                 # train / plot / validate / auto cycle / ladder / forensics
  runs/<run_id>/        # one folder per train cycle
    RUN.md
    adapter/            # Peft weights (mouth loads this)
    checkpoints/        # HF Trainer checkpoints
    plots/              # train_metrics.png (+ direction panel when forensics exist)
    logs/
      events.jsonl      # labeled timeline: train.* validate.* deploy.* plot.*
      metrics.jsonl     # trainer loss / lr / grad_norm / epoch
      forensics.jsonl   # per-step batch identity + grad direction (diagnostic)
      forensics_summary.json
    validate/           # holdout_validate.json
    meta/               # viv_train_meta.json, cycle_result.json, DEPLOYED.md
  deploy/current        # junction → active adapter/
```

## Holdout ↔ train disjoint (P0)

**Continuity (regression only):** `holdout_registry.json` / `holdout_pack.jsonl` — `pack_id=b7b159b442a93139`.

**Deploy-test (decides deploy):** `deploy_test_registry.json` / `deploy_test_pack.jsonl` — sealed post-quarantine asks; never prefs/SFT/prompts.

- Each case has `pair_hash` / `ask_hash` / `ask_cluster_hash`
- Ban-set unions continuity + deploy-test; SFT exports drop both
- Train + validate preflight fails on `holdout_train_overlap`
- Validate `mind_pass_rate` = deploy-test only; `continuity_mind_pass_rate` is regression
- Re-freeze requires explicit force + archive

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\aifl_holdout_disjoint_p0.py
L:\Continue\.venv\Scripts\python.exe scripts\aifl_deploy_test_pack_p0.py
```

## Epistemic metrics (Tier-1)

Alongside loss/grad forensics, each run writes:

- `meta/epistemic_train_buffer.json` — REWARD / SOFT_HOLD / PUNISH mix on the SFT buffer
- `meta/epistemic_holdout.json` — holdout admission + axis rates + unsupported proxy
- `meta/epistemic_card.json` — both views together

**Wired now:** admission rates, axis on-rates, Intellexi overlap mean, unsupported ≈ mind_fail.
**Deferred (honest):** confidence calibration, contradiction rate, self-correction — need multi-turn memory + new criteria before logging as real metrics.

The card is **descriptive observability**: it explains composition and judge outcomes. It does not overrule deploy. Buffer mix (e.g. 86/14/0) is a **dataset-shape warning**, not automatic proof the judge is soft or that PUNISH is wrongly excluded.

## Forensics (mouth-LoRA only)

Every train logs `logs/forensics.jsonl` with:

- batch: example idxs, REWARD/SOFT_HOLD counts, corpus_dup stats, token/label counts
- `grad_norm_unclipped` / `grad_norm_clipped` / `clipped_at_cap`
- `cos(g_t, g_{t-1})`, `cos(g_t, shadow_EMA)`, `shadow_rel_dev`

This does **not** gate deploy. Deploy stays on **deploy-test** `mind_pass` (continuity pack is regression-only).

### How to read direction (not noise theater)

| Signal | Says |
|--------|------|
| loss | whether tokens are being fit |
| `grad_norm` | how forcefully LoRA params move |
| `cos_prev` | short-range: left/right correction vs last step (`<0` = oscillation) |
| `cos_shadow` | longer-lived: alignment with EMA trajectory |

Observed AIFL pattern (peak runs): `cos_prev` often dips negative while **`cos_shadow` stays positive** — local correction around a **directional spine**, not random wander. Parallel stretches in the direction GIF = magnitude changing while the underlying adaptation direction remains anchored. That is evidence that repeated judge-admitted examples can accumulate into a **consistent** LoRA trajectory, not disconnected updates.

`grad_norm` alone cannot show this; shadow cosine is the directional stability measure.

## Compare runs (GIF)

```powershell
cd L:\Continue\Viv\foundation
L:\Continue\.venv\Scripts\python.exe models\Training\code\make_train_plots_gif.py
# → models/Training/plots_compare/train_metrics_across_runs.gif
# → models/Training/plots_compare/train_forensics_direction_across_runs.gif
```

## Commands

```powershell
cd L:\Continue\Viv\foundation
# shims still work:
L:\Continue\.venv\Scripts\python.exe scripts\aifl_overnight_loop.py --once
L:\Continue\.venv\Scripts\python.exe scripts\aifl_auto_train_cycle.py
L:\Continue\.venv\Scripts\python.exe scripts\plot_train_metrics.py --adapter models\Training\runs\<run_id>

# canonical:
L:\Continue\.venv\Scripts\python.exe models\Training\code\train_judge_lora.py --train
```

## Automation contract

1. Each train creates a **new** `runs/lora_judge_{steps}_{timestamp}/`.
2. Checkpoints, plots, labeled logs, validate, and meta all land **inside that run**.
3. Plot is generated **at end of train** every time (`plots/train_metrics.png`; 4th panel if forensics present).
4. Deploy updates `Training/deploy/current` **and** legacy `models/gpu/viv_voice_lora_judge_deploy`.
