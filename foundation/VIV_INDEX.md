# Viv / AIOS — Documentation Index

**Start here.** One map for everything under `L:/Continue/Viv/foundation/`.

| If you want… | Read this |
|--------------|-----------|
| **L: drive housekeeping (existing tools)** | `HOUSEKEEPING_TOOLS.md` ← use before any cleanup |
| **Operator manual (Alpha)** | **`AIOS_ALPHA_MANUAL.md`** ← day-to-day procedures |
| **What Viv is (vision)** | `VIV_COMPLETE_SUMMARY.md` |
| **What is actually built today** | `VIV_BUILD_STATUS.md` |
| **Run commands / verify Alpha** | `AIOS_ALPHA_BRIEFING.md` |
| **AIFL loop (self-talk → judge → LoRA)** | `AIFL.md` doctrine · `AIFL_STATUS.md` living ops |
| **Build order** | `FOUNDATION_ROADMAP.md` |
| **Runtime config (models, lanes)** | `model_config.json` |
| **Session changelog** | `artifacts/audit/session_journal.md` |
| **Triad membrane / Engineering Governor** | `TRIAD_MEMBRANE.md` |

**Python:** `L:/Continue/.venv/Scripts/python.exe`  
**Bedrock:** `L:/Continue/Viv/foundation/` (everything on `L:` serves AIOS)

---

## Production snapshot (2026-07-22)

Source of truth for deploy: `artifacts/auto/shadow_judge/admission_policy.json`

| Item | Value |
|------|--------|
| **Deploy adapter** | `lora_judge_80_20260722T070710Z` |
| **Deploy pointer** | `models/gpu/viv_voice_lora_judge_deploy` |
| **Train steps** | **160** (`ladder_max_steps: 160`) |
| **Validate oracle** | **60 cases** (`holdout_pack.jsonl`) |
| **Deploy rule** | mind_pass ≥ **0.68** AND ≥ **pinned baseline 0.9333** |
| **Mode** | Adaptive (baseline pinned on 60-case oracle) |
| **Overnight driver** | `scripts/aifl_overnight_loop.py` → `models/Training/code/` |
| **Training home** | `models/Training/` (per-run folders) |

Diagnostic reference (not deployed): `lora_judge_160_20260722T073855Z` — 0.7833 on prior pack.

---

## Quick commands

```powershell
cd L:\Continue\Viv\foundation

# Shell / status
L:\Continue\.venv\Scripts\python.exe viv_shell.py status
L:\Continue\.venv\Scripts\python.exe viv_shell.py gate status
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode mixed --turns 5

# Foundation health
L:\Continue\.venv\Scripts\python.exe scripts\foundation_health.py

# AIFL daily single cycle (stop prt_main apply/autonomous first — they starve the 3060 Ti)
# Guards: GPU preflight, 120s/case validate timeout, 4h train subprocess kill
L:\Continue\.venv\Scripts\python.exe scripts\aifl_overnight_loop.py --once

# RID plant
L:\Continue\.venv\Scripts\python.exe rid_main.py stability --stress --seconds 120
```

---

## Documentation tiers

### Tier 1 — Read first (canonical)

| Doc | Purpose |
|-----|---------|
| `VIV_INDEX.md` | **This file** — navigation |
| `VIV_COMPLETE_SUMMARY.md` | Vision, philosophy, architecture intent |
| `VIV_BUILD_STATUS.md` | BUILT / PARTIAL / LEGACY / NONE matrix |
| `AIOS_ALPHA_BRIEFING.md` | Verification commands for Alpha |
| `FOUNDATION_ROADMAP.md` | Three mains + build order |
| `model_config.json` | Lanes, models, paths (machine-readable) |

### Tier 2 — Contracts (binding behavior)

| Doc | Topic |
|-----|--------|
| `AIFL.md` | **Doctrine** — Autonomous Internal Feedback Learning |
| `AIFL_CONTRACT.md` | Binding control-law and metric formulas |
| `AIFL_STATUS.md` | **Living** AIFL ops, metrics, commands, lessons |
| `INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md` | CPU judge axes (Vidi × Intellexi × Vixi) |
| `ARCHITECT_TRIAD_THEORY.md` | CPU mind / GPU mouth split |
| `TRIAD_MEMBRANE.md` | Security-wrapped RID/AUTO/UML kernel and engineering transaction |
| `RID.md` | Plant telemetry, S_n, captures |
| `RID_EQUATIONS.md` | Canonical RID math vs proposed electrical/routing + observe gate |
| `VOICE.md` | GPU voice lane |
| `PRT_BASE_MODEL_CONTRACT.md` | PRT training on base model |
| `PRT_AUTONOMOUS.md` | Autonomous PRT beats |
| `SN_LIFE_DOCTRINE.md` | S_n life / dormancy |
| `DORMANCY_CALIBRATION.md` | Dormancy thresholds |
| `SPRT_V0_CONTRACT.md` | SPRT stage gate |
| `SUPERCOOLING_GROWTH_CONTRACT.md` | Growth / net2wider (deferred) |

### Tier 3 — Subsystem docs

| Doc | Topic |
|-----|--------|
| `PRT_OVERNIGHT.md` | Overnight PRT runs |
| `PRT_LIFE_TASK.md` | Life-task PRT |
| `PRT_GAMES.md` | PRT game harness |
| `artifacts/auto/systems/AIOS_SYSTEMS_REGISTRY.md` | System registry |
| `models/cpu/README.md` | CPU embedder / judge models |
| `models/gpu/OpenAster1-128k-base-hf/README.md` | GPU base (Qwen3 MoE) |

### Tier 4 — Living artifacts (truth at runtime)

Prefer these over stale markdown when checking *current* state:

| Path | What |
|------|------|
| `artifacts/auto/shadow_judge/admission_policy.json` | LoRA gate, steps, baseline |
| `artifacts/auto/shadow_judge/gate_state.json` | Watermark, frozen, signal |
| `artifacts/auto/shadow_judge/rollback_events.jsonl` | Deploy rejections |
| `artifacts/auto/aifl/auto_train_cycle_latest.json` | Last train cycle |
| `artifacts/audit/aifl_overnight_loop.jsonl` | Overnight cycle log |
| `artifacts/auto/shadow_judge/preference_pairs.jsonl` | Judge stamps |
| `artifacts/models/viv_judge_sft_train.jsonl` | SFT export |

---

## Code map (where logic lives)

```
L:/Continue/Viv/foundation/
├── viv_shell.py              # CLI entry (status, aifl, gate, talk)
├── rid_main.py               # RID plant captures, stability
├── prt_main.py               # PRT autonomous / apply
├── piston_core.py            # Governor / piston
├── model_config.json         # Runtime model paths
├── lib/
│   ├── viv_aifl.py           # Self-talk loop
│   ├── viv_aifl_ingest.py    # Tag-cluster file ingest
│   ├── viv_shadow_judge.py   # CPU judge (static oracle)
│   ├── viv_judge_train_gate.py # LoRA admission gate
│   ├── master_rid.py         # S_n channels
│   └── paths.py              # Artifact roots
└── scripts/   (shims → models/Training/code/ for train/plot/validate/cycle)
    ├── aifl_overnight_loop.py
    ├── aifl_collect_until_ready.py
    ├── aifl_auto_train_cycle.py
    ├── train_judge_lora.py
    ├── validate_judge_adapter.py
    ├── generate_holdout_pack.py
    └── foundation_health.py
└── models/
    ├── gpu/OpenAster1-128k-base-hf/   # base weights
    └── Training/                      # see Training/README.md
        ├── code/
        ├── runs/<run_id>/             # adapter, checkpoints, plots, logs, validate, meta
        └── deploy/current
```

---

## AIFL loop (one paragraph)

Viv generates drafts (identity + L: ingest). The **CPU shadow judge** stamps each reply. Only judge-approved pairs enter `viv_judge_sft_train.jsonl`. When the gate arms (`train_ready/signal.json`), the trainer fine-tunes a **LoRA on OpenAster** (frozen base). Hold-out validate (generate → same judge) must pass floor **and** beat the pinned deploy baseline before the deploy pointer moves. Humans tune **judge criteria only** — `artifacts/auto/shadow_judge/criteria.json`.

Deep dive: `AIFL.md` (doctrine) + `AIFL_CONTRACT.md` + `AIFL_STATUS.md`.

---

## Model stack (GPU mouth)

| Layer | Path / ID |
|-------|-----------|
| Base (frozen) | `binichallein/OpenAster1-128k-base` → `models/gpu/OpenAster1-128k-base-hf` |
| Architecture | Qwen3 MoE, 18L, 128k context |
| LoRA (trainable) | r=16, alpha=32, targets q/k/v/o_proj |
| Deploy adapter | `models/gpu/viv_voice_lora_judge_deploy` → junction |
| Overfit archive | `viv_voice_lora_judge_640_overfit_boundary` — **do not deploy** |

---

## What to ignore (noise)

| Location | Why |
|----------|-----|
| `artifacts/auto/systems/mirrors/*.md` | Stale copies of other docs |
| `models/gpu/**/runs/**/README.md` | HuggingFace checkpoint cards (auto-generated) |
| `L:/Continue/FSAA/`, `AIOS_V2/` | Legacy absorption sources — not canonical Alpha |
| Old adapter dirs | Timestamped; only `*_deploy` junction is live |

When two docs disagree: **artifact JSON > STATUS.md > CONTRACT.md > vision docs**.

---

## Other roots on L:

| Path | Role |
|------|------|
| `L:/Continue/Viv/foundation/` | **Canonical Alpha** (this tree) |
| `L:/Continue/Viv/sandbox/` | Viv workspace / journal |
| `L:/Continue/Viv/security_core/` | Rust security membrane |
| `L:/Phone/` | RID theory source (read-only unless asked) |
| `L:/Continue/FSAA/` | Agentic runtime spine (separate from foundation Alpha) |
| `L:/.cursor/rules/` | Cursor agent policy for this workspace |

---

## Maintaining this index

When production state changes (deploy, ladder, baseline):

1. Update `admission_policy.json` (source of truth).
2. Append to `AIFL_STATUS.md`.
3. Refresh the **Production snapshot** table in this file.
4. Append `artifacts/audit/session_journal.md`.

Do not duplicate long prose here — link to the contract/status doc instead.
