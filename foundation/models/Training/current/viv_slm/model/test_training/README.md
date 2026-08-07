# Viv-SLM test_training sandbox

**Sandbox only — originals untouched.**

This folder is an isolated plant for our own train / test / short campaigns.
It sits under `model/` next to `transformer.py`, but it does **not** write into
Codex/operator campaign trees, live checkpoints, or production training runners.

## Authorization

Operator authorized: train, test, short campaigns, and speak/load smokes **here**.
Python: `L:/Continue/.venv/Scripts/python.exe` only.

## Isolation doctrine

| Allowed | Forbidden |
|---------|-----------|
| Writes under `model/test_training/` | Mutating Codex/operator checkpoints outside this sandbox |
| Sealed receipts under `model/artifacts_local/experiments/` for this sandbox | Editing production runners (`train.py`, campaign configs, etc.) |
| `import` of parent plant modules (`transformer`, `speak_lanes`, …) | Treating sandbox weights as production identity |

## Layout

```
test_training/
  README.md                 # this file
  sandbox_paths.py          # path constants (sandbox-only)
  data/
    identity_corpus.txt     # edit this to grow identity training text
  sandbox_build_dataset.py  # corpus → vocab + tensor shards
  train_specialist.py       # train one lane (--lane efficient|deep)
  run_campaign.py           # full pipeline: build → train both → smoke
  run_sandbox_smoke.py      # load + fingerprint + speak sandwich
  run_uml_mix_layer.py      # active UML mix metabolism layers
  uml_mix_recipe.json       # active mix recipe
  UML_TRAINING_THESIS.md    # active thesis / evidence ladder
  mint_specialists.py       # shim → legacy/ (tiny 8/40-step mint)
  legacy/                   # retired RID/acc99 + mint implementations
    README.md
    MOVE_MANIFEST.json
  shared/
    vocab_manifest.json     # shared tokenizer identity
  dataset/                  # built tensor shards (build_dataset.py)
  checkpoints/
    efficient/specialist.pt
    deep/specialist.pt
  runs/                     # per-lane checkpoints, metrics, samples (leave in place)
  campaigns/                # campaign manifests
```

Retired pre-UML RID/acc99 runners live under `legacy/` with thin shims at the old
top-level names. See `legacy/MOVE_MANIFEST.json`. Do not relocate `runs/` or live
checkpoints while mix training is active.

## Codex identity dataset (read-only)

Codex prepared the canonical identity curriculum under:

`L:/Continue/Viv/foundation/models/Training/data/identity/`

| Lane | Role | Shards on disk |
|------|------|----------------|
| **v43_conversation_focus** | Base conversation identity (55k train) | **yes** — default for sandbox |
| v62_dialogue_visibility_preservation | Latest declared lane (67k train) | manifest only (needs build) |
| v16_response_only | Retention source | manifest only |

Index: `foundation/models/Training/data/identity/INDEX.json`  
Dialogue source jsonl: `foundation/artifacts/auto/agentic/viv_slm_identity_dialogue_v43/`  
Vocab: **96 characters**, response-only loss, context **128**.

Sandbox training **reads** Codex tensors; writes checkpoints only under `test_training/checkpoints/`.

## Doctrine: one identity, two reasoning styles

| Specialist | Trained on | Deploy at speak | Reasoning style |
|------------|------------|-----------------|-----------------|
| **efficient** | GPU | CPU (mind / verify) | speculative, short, greedy |
| **deep** | GPU | GPU (mouth / reason) | explore-then-lock, longer |

Same Codex identity data + vocab for both. Different seed, LR, and sample policy → distinct weights.

## Training workflow (with operator)

```powershell
cd L:\Continue\Viv\foundation\models\Training\current\viv_slm\model

# Train both specialists on GPU (250 steps each, Codex v43)
L:\Continue\.venv\Scripts\python.exe -B test_training\run_campaign.py

# Quick iteration (100 + 200 steps)
L:\Continue\.venv\Scripts\python.exe -B test_training\run_campaign.py --quick

# One checkpoint only
L:\Continue\.venv\Scripts\python.exe -B test_training\train_specialist.py --lane efficient --codex-identity v43 --steps 250 --device cuda
L:\Continue\.venv\Scripts\python.exe -B test_training\train_specialist.py --lane deep --codex-identity v43 --steps 250 --device cuda

# Smoke after training (efficient speaks on CPU, deep on GPU)
L:\Continue\.venv\Scripts\python.exe -B test_training\run_sandbox_smoke.py
```

## Legacy smoke (tiny 8/40-step mint)

Implementation: `legacy/mint_specialists.py`. Top-level path is a shim.
**Overwrites** `checkpoints/efficient|deep` — require `--execute`:

```powershell
L:\Continue\.venv\Scripts\python.exe -B test_training\mint_specialists.py --execute
L:\Continue\.venv\Scripts\python.exe -B test_training\run_sandbox_smoke.py
```

Receipt: `../artifacts_local/experiments/H_sandbox_test_training.json`
