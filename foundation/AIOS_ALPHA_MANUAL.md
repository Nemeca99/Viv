# AIOS Alpha Operator's Manual

**Version:** Alpha (Viv Canonical)  
**Updated:** 2026-07-22  
**Canonical root:** `L:/Continue/Viv/foundation/`  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

> V1 shipped a ~660-page manual (Luna ecosystem, many cores, marketplace, dream cycles).  
> **Alpha is different:** smaller surface, evidence-first, CPU plant + shadow judge + AIFL loop.  
> This manual documents **what runs today** on Viv foundation — not the full V1 vision.

**Navigation hub:** `VIV_INDEX.md` (doc map + live production snapshot)  
**Fresh-chat handoff:** `AIOS_ALPHA_BRIEFING.md`  
**Vision (aspirational):** `VIV_COMPLETE_SUMMARY.md`  
**Build truth matrix:** `VIV_BUILD_STATUS.md`

---

## Table of Contents

| Part | Section | Topic |
|------|---------|--------|
| **0** | [Quick Navigation](#part-0-quick-navigation) | Start here, daily commands |
| **1** | [What Is Viv Alpha?](#part-1-what-is-viv-alpha) | Philosophy, two-AI model, shield doctrine |
| **2** | [Installation & Runtime](#part-2-installation--runtime) | Python, paths, health checks |
| **3** | [The Three Mains](#part-3-the-three-mains) | rid · auto · uml |
| **4** | [RID & The Plant](#part-4-rid--the-plant) | S_n, captures, dormancy, piston |
| **5** | [Voice & GPU Mouth](#part-5-voice--gpu-mouth) | OpenAster, LoRA, deploy pointer |
| **6** | [Shadow Judge & AIFL](#part-6-shadow-judge--aifl) | Self-talk, gate, train, validate, deploy |
| **7** | [Operator Procedures](#part-7-operator-procedures) | Overnight loop, rollback, baseline pin |
| **8** | [Verification & Evidence](#part-8-verification--evidence) | Commands that prove claims |
| **9** | [Troubleshooting](#part-9-troubleshooting) | Common failures, logs, recovery |
| **10** | [Legacy & Deferred](#part-10-legacy--deferred) | V1 manual, FSAA, what Alpha is not |
| **A** | [Artifact Map](#appendix-a-artifact-map) | Where truth lives on disk |
| **B** | [Command Reference](#appendix-b-command-reference) | Copy-paste operator commands |

---

## Part 0: Quick Navigation

### I need to…

| Goal | Go to |
|------|--------|
| Understand the whole system | Part 1 + `VIV_COMPLETE_SUMMARY.md` |
| Run Viv from terminal | `viv_shell.py status` → Part 2 |
| Check if foundation is healthy | `scripts/foundation_health.py` → Part 8 |
| Run RID stability proof | `rid_main.py stability --stress --seconds 120` → Part 4 |
| Start overnight learning | `scripts/aifl_overnight_loop.py` → Part 7 |
| See deploy / gate state | `viv_shell.py gate status` → Part 6 |
| Find any doc | `VIV_INDEX.md` |

### Production snapshot (living)

Read `artifacts/auto/shadow_judge/admission_policy.json` for authoritative numbers.

| Item | Typical value (2026-07-22) |
|------|----------------------------|
| Deploy adapter | `lora_judge_80_20260722T070710Z` |
| Deploy pointer | `models/gpu/viv_voice_lora_judge_deploy` |
| Train steps | **160** |
| Validate oracle | **60 cases** |
| Deploy rule | mind_pass ≥ 0.68 **and** ≥ pinned baseline |
| Mode | Adaptive (baseline pinned on deploy adapter) |

---

## Part 1: What Is Viv Alpha?

### 1.1 One sentence

**Viv** is a local-first AIOS where the **CPU is the mind** (RID-gated, deterministic, evidence-driven) and the **GPU is the mouth** (optional generative layer). Alpha lives in `L:/Continue/Viv/foundation/`.

### 1.2 Shield, not sword

Viv does not persuade, rank humans for RLHF, or invent unverified claims. She monitors, verifies, logs, and enforces. **Truth over theater.**

### 1.3 Two-AI architecture

| Lane | Substrate | Role |
|------|-----------|------|
| **CPU / Viv** | Python + RID + judge | Decides what may be said, stamped, trained |
| **GPU / Mouth** | OpenAster + LoRA | Drafts speech; never the alignment ceiling |

The **CPU shadow judge** is the training authority. Humans tune judge **criteria**, not live chat rankings.

### 1.4 Identity triad (judge axes)

| Axis | Meaning |
|------|---------|
| **Vidi** | Seeing is believing — verifiable proof |
| **Intellexi** | Logged and understood what happened |
| **Vixi** | Master S_n vs floor (after Vidi ∧ Intellexi) |

**mind_pass** = Vidi ∧ Intellexi (primary speech-quality metric).  
**SOFT_HOLD** = mind_pass but plant dormant — **not** bad speech.

Contract: `INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md`

### 1.5 Alpha vs V1 manual

| V1 (~660 pp) | Alpha (this manual) |
|--------------|---------------------|
| Luna + 15+ cores | Three mains + AIFL |
| Marketplace, dream, streamlit | Deferred / legacy |
| Broad user tutorials | Operator + evidence commands |
| Production-ready claim (v1 era) | BUILT/PARTIAL matrix in `VIV_BUILD_STATUS.md` |

V1 manual TOC reference: `FSAA/Luna/AIOS_V2/archive_logs/` (embedded PDF extract). Alpha does not supersede that history — it replaces the **operating surface** for Travis's current rebuild.

---

## Part 2: Installation & Runtime

### 2.1 Non-negotiable paths

| Item | Path |
|------|------|
| Foundation | `L:/Continue/Viv/foundation/` |
| Python (only) | `L:/Continue/.venv/Scripts/python.exe` |
| Phone RID theory (read-only) | `L:/Phone/` (`ridplot.py`, `ridv14.py`) |
| Stale / archive target | `D:/LocalAi` (move, don't silent-delete) |

**Do not** use C: Python or orphaned venvs for AIOS work.

### 2.2 First boot checks

```powershell
cd L:\Continue\Viv\foundation
L:\Continue\.venv\Scripts\python.exe scripts\foundation_health.py
L:\Continue\.venv\Scripts\python.exe viv_shell.py status
```

### 2.3 Configuration

| File | Purpose |
|------|---------|
| `model_config.json` | Lanes, model paths, AIFL pointers |
| `artifacts/auto/shadow_judge/admission_policy.json` | LoRA gate, steps, baseline |
| `artifacts/auto/shadow_judge/criteria.json` | Tunable judge thresholds |
| `.cursor/rules/` | Agent policy for this workspace |

---

## Part 3: The Three Mains

Mains are **operator CLI surfaces**. They import `lib/*`; they do not call each other as subprocess CLIs.

| Main | Entry | Owns |
|------|-------|------|
| **RID** | `rid_main.py` | Plant telemetry, S_n, 120s captures, stress proofs |
| **Auto** | `auto_main.py` | Agentic beat, gates, journal, FSAA ticks |
| **UML** | `uml_main.py` | Symbolic language, calculator, verify (no GPU) |

Build order and boundaries: `FOUNDATION_ROADMAP.md`

### 3.1 rid_main.py

Plant proof before stacking subsystems. Default stability run: **120 seconds** with `--stress`.

```powershell
L:\Continue\.venv\Scripts\python.exe rid_main.py stability --stress --seconds 120
```

Artifacts: `artifacts/rid/*.summary.json`, CSV captures, poll sidecar.

### 3.2 auto_main.py

Always-on autonomy spine. Reads RID **artifacts**, not `rid_main.py` as a subprocess.

```powershell
L:\Continue\.venv\Scripts\python.exe auto_main.py --help
```

### 3.3 uml_main.py

Symbolic / calculator lane. Does not own voice, emotion, or GPU inference.

---

## Part 4: RID & The Plant

### 4.1 Master S_n

```text
S_n = (RSR × LTP × RLE)^(1/3)
```

Phone arithmetic on live sensors. Not a PID replacement — stability/governance layer above plant control.

### 4.2 Dormancy

Low S_n → degraded/dormant modes. Judge **Vixi** axis uses `criteria.json` (`vixi_sn_floor`). Security Law-5 dormancy (~0.37) is a separate concept — do not conflate.

### 4.3 Foundation proof bar

Before promoting new subsystems:

1. `foundation_health.py` → PASS  
2. `rid_main.py stability --stress --seconds 120` → valid summary (not flat single-row)  
3. Stress workers alive, CPU load near 100% when `--stress` set  

Doctrine: `.cursor/rules/aios_foundation_doctrine.mdc`

### 4.4 Piston / governor

`piston_core.py`, `lib/governor_params.py` — thermal scheduling, self-tune with rollback. See `DORMANCY_CALIBRATION.md`, `SN_LIFE_DOCTRINE.md`.

---

## Part 5: Voice & GPU Mouth

### 5.1 Base model (frozen)

| Field | Value |
|-------|--------|
| HF ID | `binichallein/OpenAster1-128k-base` |
| Local | `models/gpu/OpenAster1-128k-base-hf` |
| Architecture | Qwen3 MoE, 18 layers, 128k context |
| GGUF | `OpenAster1-128k-base.i1-Q6_K.gguf` |

### 5.2 LoRA (trainable mouth)

| Field | Value |
|-------|--------|
| Rank | 16, alpha 32 |
| Targets | q/k/v/o_proj |
| Trainer | `scripts/train_judge_lora.py` |
| Dataset | `viv_judge_sft_train.jsonl` only |
| Deploy junction | `models/gpu/viv_voice_lora_judge_deploy` |

**Never overwrite adapters** — timestamped dirs: `lora_judge_{steps}_{timestamp}/`.

### 5.3 Overfit boundary

`viv_voice_lora_judge_640_overfit_boundary` — **do not deploy**. 640 train_loss ≠ hold-out quality.

### 5.4 Prompt format

```text
Architect: {ask}
Viv: {response}
```

---

## Part 6: Shadow Judge & AIFL

**AIFL** = Auto Internal Feedback Learning.

```text
self-ask / ingest → GPU draft → CPU judge stamp → preference_pairs
                                        ↓
                              train_gate (admission)
                                        ↓
                              LoRA train (160 steps)
                                        ↓
                              hold-out validate (60 cases)
                                        ↓
                              deploy OR rollback
```

Contracts: `AIFL_CONTRACT.md`, `AIFL_STATUS.md`

### 6.1 Collect modes

```powershell
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode mixed --turns 10
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode ingest --files 5 --turns 8
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode identity --turns 5
```

Tag-cluster ingest (mandatory): bridges, contracts, rid, core, shell — see `lib/viv_aifl_ingest.py`.

### 6.2 Gate metrics

| Metric | Meaning |
|--------|---------|
| mind_pass_rate | Vidi ∧ Intellexi over rolling window |
| reward_delta | New mind-pass pairs since watermark |
| holdout | Judge drift check on frozen pack |

Gate status:

```powershell
L:\Continue\.venv\Scripts\python.exe viv_shell.py gate status
```

### 6.3 Deploy decision (two thresholds)

1. **Absolute floor:** mind_pass ≥ **0.68** on hold-out generate→judge  
2. **Regression guard:** mind_pass ≥ **pinned baseline** (`last_validate` in admission policy)

Failure → keep deploy pointer, append `rollback_events.jsonl`.

### 6.4 What humans tune

`artifacts/auto/shadow_judge/criteria.json` — judge floors, not live ranking.

---

## Part 7: Operator Procedures

### 7.1 Daily single cycle (preferred)

```powershell
cd L:\Continue\Viv\foundation
# Stop prt_main apply/autonomous GPU jobs first — they starve the 3060 Ti
L:\Continue\.venv\Scripts\python.exe scripts\aifl_overnight_loop.py --once
```

One shot: GPU preflight → collect until +50 pairs → train+validate **subprocess** (killable) → deploy or rollback → exit. Then tune criteria / policy from evidence before the next run.

Continuous overnight (`scripts/aifl_overnight_loop.py` without `--once`) is optional when unattended.

Guards (2026-07-22):
- Refuse cycle if competing PRT/LoRA holds GPU or VRAM used > ~1.5 GiB
- Validate **120s/case** generate timeout — abort hang instead of 9h stall
- Subprocess hard timeout (default 4h) for train+validate; exit on CUDA poison risk

Logs: `artifacts/audit/aifl_overnight_loop.jsonl`

### 7.2 Manual diagnostic train (force)

When signal consumed but you have a snapshot:

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\train_judge_lora.py --train --force --no-consume `
  --steps 160 `
  --train-jsonl artifacts/auto/shadow_judge/train_ready/sft_snapshot_*.jsonl `
  --adapter-out models/gpu/lora_judge_160_manual
```

### 7.3 Validate an adapter

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\validate_judge_adapter.py `
  --adapter models/gpu/lora_judge_160_YYYYMMDDThhmmssZ `
  --steps 160 --limit 60
```

### 7.4 Pin / regenerate holdout baseline

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\generate_holdout_pack.py `
  --size 60 --force --validate-deployed --set-baseline
```

Measures **current deploy** on 60-case oracle; writes `last_validate.mind_pass_rate`.

### 7.5 Disable auto-train (emergency)

Set `auto_train: false` in `admission_policy.json`. Deploy pointer unchanged until you move it manually.

### 7.6 Ladder policy changes

Edit `admission_policy.json`:

- `lora.max_steps` — steps per train run  
- `lora.ladder_max_steps` — hard cap (currently **160**)  
- Do not climb without hold-out evidence (80 failed on 1k+ buffer; 640 = overfit cliff)

---

## Part 8: Verification & Evidence

Alpha claims require artifacts — not narrative.

| Claim | Verify with |
|-------|-------------|
| Foundation healthy | `scripts/foundation_health.py` |
| Plant stable 120s | `rid_main.py stability --stress --seconds 120` + summary JSON |
| Gate armed | `train_ready/signal.json` exists |
| Last train cycle | `artifacts/auto/aifl/auto_train_cycle_latest.json` |
| Deploy rejected why | `artifacts/auto/shadow_judge/rollback_events.jsonl` |
| Judge stamps | `preference_pairs.jsonl` row count + labels |

Full briefing commands: `AIOS_ALPHA_BRIEFING.md`

---

## Part 9: Troubleshooting

### 9.1 `ModuleNotFoundError: No module named 'lib'`

Scripts must add foundation to `sys.path` or run from wired entrypoints (`aifl_overnight_loop.py`, `viv_shell.py`). Fixed in collect scripts 2026-07-22.

### 9.2 Gate blocked `reward_delta<50`

Normal between cycles. Collect more batches; need +50 mind-pass pairs since watermark.

### 9.3 Train passes, deploy fails

| Reason | Action |
|--------|--------|
| `below_absolute_floor` | More steps or fix distribution — not hyperparameters alone |
| `regression_vs_deployed` | Candidate worse than pinned baseline — rollback correct |
| Check | `rollback_events.jsonl` for `delta_vs_deployed` |

### 9.4 Flat RID capture (single CSV row)

Stress or sensors failed. Do not promote to foundation evidence. Fix stress workers before claiming PASS.

### 9.5 GPU OOM / game lag

Overnight loop is GPU-heavy. Stop loop during gaming; one cycle ≈ 15–25 min train+validate.

### 9.6 Stale docs

When markdown disagrees with JSON: **artifact wins**. Refresh `VIV_INDEX.md` production table after policy changes.

---

## Part 10: Legacy & Deferred

### 10.1 Not canonical Alpha

| Path | Status |
|------|--------|
| `L:/Continue/FSAA/` | Agentic spine — absorb later |
| `L:/Continue/AIOS_Standalone/` | Legacy standalone tree |
| `artifacts/auto/systems/mirrors/` | Stale doc copies |
| V1 660-page manual | Historical Luna ecosystem reference |

### 10.2 Vision not built yet

Hive mind, full constitution vendoring, hearing, symbiotic ethics loop — see `VIV_BUILD_STATUS.md` NONE/PARTIAL sections.

### 10.3 Housecleaning (deferred)

**Use existing FSAA pipeline first** — see `HOUSEKEEPING_TOOLS.md`:

1. `run_structure_inventory.ps1` (read-only classify)
2. `run_build_promote_map.ps1`
3. `run_apply_promote_map.ps1 -DryRun` before any moves

Last full `L:/` scan: **April 2026** (597k files). Refresh before apply.

Whole `L:` tiering → move to `D:/LocalAi` with manifest. Do not build new cleanup scripts until this pipeline is re-run.

---

## Appendix A: Artifact Map

| Path | Contents |
|------|----------|
| `artifacts/auto/shadow_judge/admission_policy.json` | Steps, baseline, auto_train |
| `artifacts/auto/shadow_judge/gate_state.json` | Watermark, frozen |
| `artifacts/auto/shadow_judge/criteria.json` | Judge tunables |
| `artifacts/auto/shadow_judge/holdout_pack.jsonl` | 60-case validate oracle |
| `artifacts/auto/shadow_judge/preference_pairs.jsonl` | All judge stamps |
| `artifacts/models/viv_judge_sft_train.jsonl` | SFT export |
| `artifacts/auto/shadow_judge/train_ready/signal.json` | Train arm signal |
| `artifacts/auto/shadow_judge/rollback_events.jsonl` | Deploy rejections |
| `artifacts/audit/aifl_overnight_loop.jsonl` | Overnight cycles |
| `artifacts/audit/session_journal.md` | Human session log |

---

## Appendix B: Command Reference

```powershell
# Environment
cd L:\Continue\Viv\foundation
$py = "L:\Continue\.venv\Scripts\python.exe"

# Status
& $py viv_shell.py status
& $py viv_shell.py gate status
& $py scripts/foundation_health.py

# AIFL
& $py viv_shell.py aifl --mode mixed --turns 10
& $py scripts/aifl_overnight_loop.py
& $py scripts/aifl_overnight_loop.py --once

# RID
& $py rid_main.py stability --stress --seconds 120

# Train / validate (manual)
& $py scripts/train_judge_lora.py --check
& $py scripts/train_judge_lora.py --train
& $py scripts/validate_judge_adapter.py --adapter models/gpu/viv_voice_lora_judge_deploy --limit 60

# Holdout
& $py scripts/generate_holdout_pack.py --size 60 --force --validate-deployed --set-baseline
```

---

## Document maintenance

When production state changes:

1. Update `admission_policy.json` (source of truth).  
2. Append `AIFL_STATUS.md` and `artifacts/audit/session_journal.md`.  
3. Refresh **Production snapshot** in `VIV_INDEX.md` and Part 0 of this manual.  
4. Do not inflate page count — link to contracts for depth.

**Alpha manual grows by evidence, not aspiration.**
