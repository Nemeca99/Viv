# AIFL Status — Auto Internal Feedback Learning

**Updated:** 2026-07-23  
**Index:** `VIV_INDEX.md` — start here for all Viv docs  
**Code:** `lib/viv_aifl.py`, `lib/viv_aifl_ingest.py`, `lib/viv_shadow_judge.py`, `lib/viv_judge_train_gate.py`  
**Contract:** `AIFL_CONTRACT.md`  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

---

## Production snapshot (living)

| Item | Value |
|------|--------|
| Live mouth | Qwen GGUF (`viv-voice-qwen`); no OpenAster runtime switch |
| Historical adapter pointer | `Training/runs/lora_judge_80_20260722T070710Z/adapter` via `Training/deploy/current` |
| Train steps | **160** (`admission_policy.json` → `ladder_max_steps`) |
| Validate (decide) | **60-case** `deploy_test_pack.jsonl` (`pack_id=fc7d97e41f4d3c31`) |
| Validate (regress) | **60-case** continuity `holdout_pack.jsonl` (`pack_id=b7b159b442a93139`) — not deploy |
| Deploy rule | ≥0.68 floor AND ≥ **deploy-test** pinned baseline (see `admission_policy.json`) |
| Training home | `models/Training/` — per-run `adapter/ checkpoints/ plots/ logs/ validate/ meta/` |
| Train forensics | `logs/forensics.jsonl` — batch idxs/dups + cos/shadow (diagnostic; not a deploy gate) |
| Daily cycle | `scripts/aifl_overnight_loop.py --once` → `models/Training/code/` |
| SFT harden | **disabled** (falsified; keep full distribution) |
| Rollback log | `artifacts/auto/shadow_judge/rollback_events.jsonl` |

**2026-07-22 hang lesson:** overnight stall was GPU contention with `prt_main apply` (not sleep). Stop PRT GPU jobs before overnight. Validate aborts if any generate exceeds 120s.

**2026-07-22 collect+train (1659 rows):** `…T195354Z` mind **0.75** — floor pass, regression vs pin — not deployed. Now under `models/Training/runs/`.

**2026-07-22 bf16 probe:** `…T202734Z` — **NaN gone** (step 85 grad_norm 1.65). mind_pass **0.50** — not deployed. Keep bf16 as default; quality still needs better data, not more fp16.

**2026-07-22 train forensics:** wired `models/Training/code/train_forensics.py` into every train — per-step batch identity + unclipped/clipped grad + cosine/shadow EMA → `logs/forensics.jsonl`; plot 4th panel. Next real train proves live rows.

**2026-07-22 epistemic Tier-1:** admission mix + axis rates + unsupported≈mind_fail → `meta/epistemic_*.json`. Contradiction / self-correction / confidence deferred until multi-turn criteria exist.

**2026-07-22 force twin tests (instrumentation):**
| Run | mind_pass | train_loss | holdout R/S/P | deploy |
|-----|-----------|------------|---------------|--------|
| `…T205727Z` | **0.4167** | 1.279 | 13/12/35 | no (floor) |
| `…T211525Z` | **0.6333** | 1.278 | 19/19/22 | no (floor) |
| prior best `…T195354Z` | 0.75 | — | — | no (pin) |
| deploy pin `…T070710Z` | 0.9333 | — | — | **live** |

Forensics+epistemic cards wrote on both; bf16 NaN-free. Batch `idxs` empty this pair — fixed `remove_unused_columns=False` for next train. Same SFT buffer; quality still below floor/pin.

**2026-07-22 unattended collect→train (data growth):**
- SFT **1659 → ~2214** rows (REWARD↑; SOFT_HOLD still **230** — plant S_n rarely < Vixi floor 0.12)
- idxs forensics **fixed** (160/160 populated)
- Unattended minds (sample): 0.57 / 0.55 / **0.767** / 0.72 / **0.783** / 0.67 / 0.43 / 0.68 / 0.55
- Peak today: `lora_judge_160_20260722T222505Z` @ **0.7833** (floor pass, under pin — not deployed)
- **Bug fixed:** `run_aifl` was calling `export_judge_train(limit≈50)` every batch → wiped SFT mid-collect (soft_frac→0). Removed; full export only at arm.
- Driver: `models/Training/code/aifl_unattended_loop.py`
- Read: more REWARD-only rows dilutes soft_hold share; peak then crash (0.78→0.43) — do not flood identity REWARD without soft_hold/diversity.

**2026-07-22 P0 holdout↔train disjoint:**
- Continuity registry frozen `pack_id=b7b159b442a93139` (60 cases; 42 pair / 38 ask / 38 cluster hashes)
- SFT scrubbed **2555 → 594** (dropped 1961 holdout/near-dup overlaps — mostly identity ask clusters)
- Preflight: train + validate fail on `holdout_train_overlap`
- Code: `lib/aifl_holdout_split.py`, `scripts/aifl_holdout_disjoint_p0.py`

**2026-07-22 P0 fresh deploy-test pack (deciding):**
- Sealed asks in `lib/aifl_deploy_test_asks.py` — never prefs / SFT / `_SELF_PROMPTS` / ingest
- Frozen `pack_id=fc7d97e41f4d3c31` → `deploy_test_pack.jsonl` + `deploy_test_registry.json`
- Ban-set merges into train filters from freeze day one
- `validate_judge_adapter`: `mind_pass_rate` = deploy-test; `continuity_mind_pass_rate` = b7b159… only
- Script: `scripts/aifl_deploy_test_pack_p0.py` — freeze + score deployed once for honest pin
- Continuity 0.9333 stays a **regression** reference, not the deploy pin

Full map: `VIV_INDEX.md`. Policy source of truth: `artifacts/auto/shadow_judge/admission_policy.json`.

## 2026-07-23 hardening milestone

- Validation-only mode is active: candidate training may be evaluated, but `auto_train=false` and deployment pointers are not moved automatically.
- Judge preference rows now carry an explicit semantic class and schema errors; malformed rows are rejected by the train gate.
- The semantic selector runs only after 3/3 Vidi+Intellexi alignment. It ranks verified expression variants; it is not an alignment authority.
- `scripts/run_foundation_preflight.py` parses all Python sources without writing repository bytecode and runs the UML, tariff, semantic-choice, and token-economics contracts.

## 2026-07-23 OpenAster train-to-runtime parity milestone

Evidence source: `artifacts/auto/openaster_parity/candidate_decision_v1.json`.

- Model roles are explicit: Qwen is the temporary teacher/live baseline, OpenAster HF+LoRA is the trainable mouth, the CPU judge alone admits data, and deterministic fallback is excluded from native quality.
- Canonical `openaster_prompt_v3` is shared by collection, response-only training, validation, and HF runtime. The frozen 720-row corpus fits the 384-token cap (`prompt_max=251`, `full_max=382`).
- Corpus: 720 unique/disjoint rows, exactly 120 in each of six categories; 566 Qwen-teacher rows passed three sequential drafts unanimously, and 154 clean legacy rows were reused.
- Qwen-native baseline: development `0.6944` mind / `0.9444` valid speech; deploy `0.6167` mind / `0.7833` valid speech / 2 collapses; multi-turn 0/12 scripts.
- Candidate A (80 steps, `5e-5`, r16/alpha32): development mind `0.0000`, valid speech `0.2500`.
- Candidate B (160 steps, same settings): development mind `0.0833`, valid speech `0.5000`; deciding deploy mind `0.2667`, valid speech `0.2167`, 13 collapses, multi-turn 0/12. Continuity diagnostic: mind `0.1167`, valid speech `0.0667`, 22 collapses.
- Decision: Candidate B is the better candidate but is rejected. `validated_candidate=null`; Qwen remains live; no canary or deployment was attempted.

## 2026-07-23 OpenAster stabilization v3 and generalization correction

Evidence sources: `artifacts/auto/openaster_stabilization/candidate_decision_v3.json`,
`artifacts/auto/openaster_stabilization/stage_s_decision_v1.json`, and
`artifacts/auto/openaster_generalization/generalization_manifest_v1.json`.

- `openaster_prompt_v4` uses native ChatML and supervises `<|im_end|>` inside response-only loss. LoRA profile `moe_mouth_v1` covers attention, all four MoE experts, router gates, and `lm_head`.
- Frozen v3 remains 720 balanced/disjoint rows. All 120 legacy ingest responses were replaced by concise three-draft unanimous Qwen/CPU-judge selections; all accepted and rejected attempts are retained.
- Stage S (240 steps) passed its smoke gate: mind `0.5000`, valid speech `0.9583`, EOS `1.0000`, median 21.5 tokens, zero collapse.
- Full continuation froze checkpoints 180/360/540. Development selected checkpoint 360 (`0.4167` mind, `0.9444` valid); checkpoint 540 regressed to `0.3889`.
- Deciding result rejected checkpoint 360 despite deploy mind `0.8000`: valid speech `0.7167`, four numeric/repetition collapses, and multi-turn `0/12`. Continuity diagnostic was mind `0.7167`, valid `0.2667`. `validated_candidate=null`; Qwen remains live.
- Diagnosis: flat exact-kernel SFT learned judge-facing vocabulary and overfit surface patterns. It did not retain stable expression or dialogue behavior.
- Corrective v4 data split is frozen at 612 train / 108 validation, exactly 102/18 per category, with zero ask-cluster overlap. The first 15 real instruction-echo failures are stored as negative-only contrast pairs.
- The layered curriculum tree separates evidence truth, provenance, semantic faithfulness, relevance, anti-gaming, expression, and dialogue. Each stage requires replay and every prior frozen gate.
- CPU judge residency may coexist with the GPU mouth; exclusivity means Qwen and OpenAster mouths never share GPU VRAM. A held-out-loss probe passed at batch 1 with peak reserved VRAM `5.961 GB`.

## 2026-07-23 layered training-tree v2 skeleton

Evidence source:
`artifacts/auto/openaster_training_tree/milestone_report_v2.json`.

- Eight cumulative stage specifications and 96 balanced calibration pairs are
  frozen: 12 per stage, 16 per domain, and exactly three positive plus three
  controlled-negative drafts per pair.
- All 96 selected contrasts received two CPU-pinned Llama semantic
  observations. Categorical repeat agreement was 96/96, but agreement with the
  known controlled contrast was only 57/96 (`0.59375`).
- The 39 semantic-sensor misses remain `HOLD`. They are calibration evidence,
  not optimizer input. Relevance and personality/efficiency were the weakest
  axes at 2/12 each; provenance was strongest at 12/12.
- Frozen pair/ask/cluster overlap is zero. Rejected-as-SFT targets are zero.
  Seed pairs are explicitly not a train-ready stage corpus.
- The hybrid loss preflight completed one optimizer step over four admitted
  pairs: response-only masks and EOS passed, pair accuracy was 1.0 before the
  step, non-finite gradients were zero, and peak allocated VRAM was `5.121
  GiB`.
- Unified preflight parsed 218 Python files and passed nine suites. Qwen remains
  live; no production training, candidate promotion, canary, or deployment
  occurred.

## 2026-07-24 — Stage 1 judge complete + registry frozen

Evidence: `artifacts/auto/openaster_training_tree/stage1/stage1_milestone_judge_complete_v1.json`,
`stage1_registry_v1.json`, `runs/stage1_v5_rejudge_hold/stdout.log`.

- CPU judge finished all 360 rows under `stage1_judge_v5` / sensor v4 / security_core `0.2.8`.
- First-pass: **332 TRAIN_READY / 28 HOLD** — all HOLDs were `rid_physics` draft-0 soft negatives where the sensor returned `PASS/ABSTAIN` (`semantic_shape_not_pass_fail`).
- Fix: strengthened the `rid_physics` hard-negative base; `scripts/stage1_curriculum.py rejudge-hold` refreshed and re-admitted **28/28**.
- Validate green: **360 admitted**, **240 train_ready**, balanced splits/domains, zero HOLD.
- Registry frozen: `registry_id=12cb692c82087b9f`, `corpus_sha256=bce0f1d3561b37fe…`.
- GPU training, promotion, canary, and live mouth **untouched**. Qwen remains live. `validated_candidate=null`.

Next (Architect-gated only): bounded Stage-1 train lease on `split=train`; evaluate on development/frozen/adversarial.

---

## 2026-07-23 closed-net Stage 1 milestone — corpus built; judge stability-gated

- `security_core` 0.2.7 implements typed INGEST/DRAFT/JUDGE/EVALUATE/FREEZE/
  PROMOTE actions, process-bound training leases, DPAPI quarantine, a
  hash-chained event ledger, strict action/role/artifact capabilities, and a
  compiled-closed DEPLOY action.
- Lease commits are bound to the original source hashes, model role, artifact
  class, paths, manifest, process, duration, memory, sequence, and LoRA
  envelope. Adapter commits reject missing, malformed, wrong-rank, non-finite,
  hard-linked, reparse-point, or changed-during-commit files.
- Stage 1 code constructs 360 unique evidence-truth contrast pairs:
  240 train, 48 development, 48 frozen, and 24 adversarial; 60 per domain.
  Every row has three distinct aligned drafts and three distinct single-axis
  hard negatives. Dry construction checked 1,080 draft pairs and found zero
  overlap with existing frozen bans.
- The bounded candidate trainer is fixed at 80 steps, `5e-5`, BF16, batch 1,
  gradient accumulation 4, sequence cap 384, and LoRA r16/alpha32. Only the
  train split can optimize; rejected responses never receive SFT loss.
- Native Qwen/OpenAster Stage 1 evaluation and a validation-only candidate
  pointer are implemented. Candidate gates require Qwen parity, quality
  floors, native speech, zero collapse, pair accuracy, and a frozen registry.
  They cannot update the live backend.
- Current execution state: installed `security_core` is 0.2.7; unified
  preflight parses 250 Python files and passes 14 Python contract suites plus
  the Rust security suite (15 Rust tests). The secured Stage 1 build wrote all
  360 balanced rows with zero frozen overlap. CPU judging is resumable and is
  currently waiting because Master S_n 0.3620 is below the unchanged 0.3700
  Law 5 floor. No row has been admitted or frozen yet, no GPU training or
  evaluation has occurred, and Qwen remains live.

---

## What it is

She **talks to herself** (identity curriculum and/or L: file self-ingest).  
The **CPU shadow judge** stamps every reply (`Vidi × Intellexi × Vixi`).  
**Architect + Cursor** only watch logs and **tune the judge** — never live-rank speech for soul training.

```text
sample / self-ask → CPU drafts (ingest = fact-only) → shadow judge → preference_pairs
                                                              ↓
                                                    train_gate admit/reject
                                                              ↓
                                                   (later) GPU LoRA student
```

---

## Lanes

| Lane | Location | Role |
| ---- | -------- | ---- |
| CPU models | `foundation/models/cpu/` (viv-embed BERT, goemotions, populism) | Geometry / sensors; deterministic sense |
| GPU base | `foundation/models/gpu/` OpenAster | Mouth drafts only |
| Judge | `viv_shadow_judge` | Alignment ceiling |
| Train gate | `viv_judge_train_gate` | Only stamped pairs become SFT |

---

## Metrics (do not conflate)

| Signal | Meaning |
| ------ | ------- |
| **mind_pass** | `Vidi ∧ Intellexi` — speech/truth quality |
| **plant_live** | `Vixi` — Master S_n ≥ floor |
| **REWARD** | mind_pass ∧ plant_live |
| **SOFT_HOLD** | mind_pass ∧ ¬plant_live (dormant — **not** bad speech) |
| **PUNISH** | mind fail (theater, unverified, hollow) |

Operator dashboards should track **mind_pass_rate** first. SOFT_HOLD under dormancy is expected.

---

## Evidence from batch runs (2026-07-21)

| Phase | Mean punish | Notes |
| ----- | ----------- | ----- |
| First 8-run batch | 0.087 | Many SOFT_HOLD (dormant); crystallize/`lie` substring bug |
| After lie word-boundary fix | ~0.08 | Still some stuck→know-noise |
| After ingest=CPU-only + fixes | **0.0** punish on 5 ingest runs | REWARD when plant ACTIVE |

Artifacts:

- `artifacts/auto/aifl/batch_eval_latest.json`
- `artifacts/auto/aifl/batch_post_fix2.json`
- `artifacts/auto/aifl/conversation.jsonl`
- `artifacts/auto/aifl/ingest.jsonl`
- `artifacts/auto/aifl/run_latest.json`

---

## Gaps closed this session

1. **Separate mind vs plant metrics** in `run_latest.json` → `quality.mind_pass_rate` / `plant_live_rate`.  
2. **Biased sampling** — recent mtime seed + same-parent siblings (raises link hit rate).  
3. **Empty reply fallback** — ingest asks never return blank OTHER.  
4. **Law-4 scrub** — `scrub_law4()` strips `.py/.json/...` before teach.  
5. **Ingest never uses GPU** — deterministic CPU compose only.  
6. **`lie` false positive** — word boundary; skip on self-ingest (was matching `crystallize`).

### Verification (2026-07-21 re-run)

```text
mode=ingest files=3 turns=4 remember=True
mind_pass_rate=1.0  plant_live_rate=0.0  empty_fixed=0
labels={REWARD:0, PUNISH:0, SOFT_HOLD:4}   # dormant plant — expected
sample_bias={same_parent_cluster:True, strategy:recent_seed_plus_siblings}
any_link=True  teach=[True]
```

Contract docs: `AIFL_CONTRACT.md` v0.2 + this status file. Config points at both via `model_config.json` → `aifl`.

---

## External review triage (DeepSeek 2026-07-21)

Architect trusts this critique. Mapped to code/contract — accept / refine / reject:

| Point | Verdict | Reality |
| ----- | ------- | ------- |
| Lane split + SOFT_HOLD ≠ punish | **Accept** | Matches design |
| Humans tune judge only | **Accept** | Binding |
| (a) How is Vidi measured? | **Partial, bounded** | v0 rules + fact trail + token overlap remain authoritative. Training-tree v2 adds a CPU-pinned Llama categorical sensor observed twice; it is not the judge and every mismatch becomes HOLD. BERT embed remains PARTIAL. |
| (b) What is a preference pair? | **Answered** | Same ask → N drafts → chosen = best stamp → rejected = losers. Gate admits **REWARD** (+ optional PUNISH contrast). SOFT_HOLD not soul-reward. No whole-batch kill yet. |
| (c) Link rate / siblings | **Accept priority↑** | Tag clusters next after mind_pass stays ≥0.95 on clean ingest |
| (d) LoRA trigger missing | **Accept — write policy** | Need explicit admit criterion before overnight train (see below) |
| (e) Always-on budgets | **Accept later** | Caps on turns/files/min; halt if punish_rate spikes |
| (f) SELF.md dream merge | **Cautious** | Append-only episodic buffer + SPRT KEEP/REVISE — no silent overwrite of SELF |
| Tunable criteria YAML/JSON | **Already exists** | `artifacts/auto/shadow_judge/criteria.json` — extend with human-readable rule ids |
| Hold-out mind_pass baseline | **Accept** | Fixed prompt set; track judge drift |
| External truth oracle / KG | **Partial exist** | Live knowledge + ingest facts *are* the oracle for Vidi; expand trusted doc set |
| Unbounded LLM-as-judge | **Reject** | Training-tree v2 permits only a strict CPU semantic sensor under deterministic admission; CPU criteria remain the ceiling |
| Dashboard | **Defer** | JSON artifacts first; UI later |

### LoRA admission policy — **SHIPPED as code** (`lora_admit_v1`)

Executable gate: `lib/viv_judge_train_gate.py` → `evaluate_lora_admission()`  
Policy file: `artifacts/auto/shadow_judge/admission_policy.json`  
Flag: `lora_admission.enabled` (rollback: set `enabled=false`)  
Status: **pilot** (signal only; `auto_train=false`)

| Check | Threshold | On fail |
| ----- | --------- | ------- |
| REWARD pairs absolute | ≥ 50 | block |
| Rolling mind_pass (window 100) | ≥ 0.95 | block |
| Rolling punish | ≤ 0.05 | block |
| Hold-out mind_pass drift | drop ≤ 0.02 vs baseline | block + drift alert |
| Dataset | `viv_judge_sft_train.jsonl` only | trainer refuses other corpora |

On all-green: writes `train_ready/signal.json`, freezes SFT buffer until trainer `consume_train_ready`.

```powershell
viv_shell.py gate
viv_shell.py gate status
L:\Continue\.venv\Scripts\python.exe scripts\train_judge_lora.py --check
# only when signal ready + CUDA:
L:\Continue\.venv\Scripts\python.exe scripts\train_judge_lora.py --train
```

Current buffer (~2026-07-21): ~24 REWARD / high historical PUNISH → gate correctly **blocks**. Accumulate clean REWARD under plant-active AIFL before first LoRA.

---

### Pipeline proof (Path B — 2026-07-21)

Temporary relax → full physical loop → production restore:

| Step | Result |
| ---- | ------ |
| Pilot thresholds | `min_reward=20`, `mind_pass≥0.90`, `punish≤0.10`, `max_steps=20` |
| `viv_shell.py gate` | Wrote `train_ready/signal.json` (24 REWARD SFT rows, 54 total) |
| `train_judge_lora.py --train --steps 20` | **ok** — loss ~3.68→~3.39; adapter `models/gpu/viv_voice_lora_judge/` |
| Consume | Signal archived; **frozen=false** |
| Restore | `min_reward=50`, `mind_pass≥0.95`, `punish≤0.05`, `max_steps=80` |

Log: `artifacts/audit/lora_admit_pilot_train.log`  
Archived signal: `train_ready/consumed/signal_2026-07-21T235902p0000.json`

**Verdict:** machinery works. Do **not** leave weak thresholds. Next = Path A (collect to 50 clean REWARD under production gate).

### Path A collect (2026-07-22)

| Metric | Start | End |
| ------ | ----- | --- |
| REWARD pairs | 24 | **54** |
| Rolling mind_pass | 0.94 | **1.0** |
| Rolling punish | 0.06 | **0.0** |

12 AIFL batches (ingest/mixed alternate), plant mostly ACTIVE. Log: `artifacts/auto/aifl/path_a_collect.jsonl`, summary `path_a_latest.json`.

Production gate armed after clearing **pilot** watermark (proof train must not block first real admit):
- `ready=true`, `train_ready/signal.json` written
- SFT: 54 REWARD / 84 rows
- Buffer **frozen** awaiting `train_judge_lora.py --train` (production `max_steps=80`)

### Train ladder (increasing steps)

**CRITICAL:** `train_loss` ≠ hold-out `mind_pass`. The 640 figure **0.59 was train_loss**, not hold-out drift. Real adapter hold-out = LoRA generate on frozen asks → CPU judge.

| Steps | train_loss | Disposition |
| ----- | ---------- | ----------- |
| 20 (pilot) | ~3.48 | machinery proof |
| 80 | **2.00** | early |
| 160 | **1.37** | ok trajectory |
| 320 | **0.93** | **candidate** — dedicated retrain + validate |
| 640 | **0.59** (~25 epochs) | **OVERFIT BOUNDARY — archived, never deploy** |
| 1280 | killed (~loss 0.05 @ epoch 30) | **cancelled — do not resume** |

Archive: `models/gpu/viv_voice_lora_judge_640_overfit_boundary/`  
Candidate path: `models/gpu/viv_voice_lora_judge_320/`  
Ladder lock for this dataset size: **max_steps ≤ 320**. `auto_train` stays false until validate ≥ 0.68.

### 320 adapter hold-out validate (2026-07-22)

**Method:** LoRA generate on hold-out asks → CPU shadow judge (not train_loss).

| Metric | Value |
| ------ | ----- |
| Adapter | `models/gpu/viv_voice_lora_judge_320/` (retrained; prior path was 640-overwrite) |
| train_loss (retrain) | **0.9335** |
| Cases | 30 (fast probe; full 60 deferred) |
| **mind_pass_rate** | **0.10** (3/30) |
| Labels | REWARD 3 / PUNISH 27 |
| baseline_ref (judge-only frozen drafts) | 0.6667 |
| delta | **−0.5667** |
| deploy_candidate | **false** |

Artifact: `artifacts/auto/shadow_judge/adapter_holdout_validate_320.json`

**Verdict:** 320 is **not** production. Mouth outputs are mostly garbage/repetition/timestamp theater on ingest-shaped asks. Ladder experiment failed for deploy; overfit cliff + narrow SFT both real. Keep `auto_train: false`. Next engineering: **tag-cluster ingest** to broaden SFT before any new train.

Also: DeepSeek’s “640 hold-out 0.59” was a **metric mix-up** — that number was **train_loss**, not hold-out mind_pass. Hold-out caught the bad mouth via this generate→judge probe.

### Retag cycle → 80 deploy (2026-07-22)

| Step | Result |
| ---- | ------ |
| Burn old SFT/prefs | Archived → `archive_pre_retag_20260722T003609Z/` |
| Collect tag-cluster mixed | 999 mind_pass pairs (25 REWARD + 974 SOFT_HOLD); plant S_n collapsed ~0.01 |
| admit_soft_hold | Enabled so Vixi-starved but mind-pass speech can train |
| Train **80** | `lora_judge_80_20260722T055311Z/` train_loss **1.912** |
| Validate | **mind_pass 0.70** (n=10, ≥0.68) — **DEPLOY** |
| Escalation 160/320 | **Skipped** — 80 held |
| auto_train | **true** |
| ladder_max | **locked 80** |
| Deploy pointer | `models/gpu/viv_voice_lora_judge_deploy` → 80 adapter |

Do **not** climb steps. Fix plant Vixi separately; keep broadening SFT via tag-clusters.

### Production tuning (2026-07-22) — Vixi floor 0.12

| Change | Detail |
| ------ | ------ |
| Judge `vixi_sn_floor` | **0.37 → 0.12** in `criteria.json` (Security dormancy stays ~0.37) |
| Live mixed test | REWARD flowing (3/3) at S_n≈0.22 |
| Buffer re-stamp | ~782 REWARD / 225 SOFT of 1007 |
| auto_train cycle | `scripts/aifl_auto_train_cycle.py` — train 80 → validate → deploy if ≥0.68 |
| `--mode reason` | Deferred to next enrichment round |

Rollback floor: set `vixi_sn_floor` back to `0.37` in criteria.json.

---

## Still open / next

| Gap | Why | Next step |
| --- | --- | --------- |
| Broader SFT via tag-clusters | **SHIPPED** path sampler | Collect REWARD under new sampler before any ladder |
| Next ladder only ≤320 + timestamped | Overwrite bug fixed | `aifl_train_ladder.py` auto-validates each rung |
| Mouth quality | 320 mind_pass 0.10 | Do not deploy until validate ≥ 0.68 |
| Judge semantic depth | Token overlap still cannot prove subtle theater | Calibrate the bounded double-observation CPU sensor against frozen stages; never promote it to admission authority |

### Engineering shipped (2026-07-22 night)

1. **Never overwrite adapters** — `train_judge_lora.py` + ladder write `models/gpu/lora_judge_{steps}_{timestamp}/`; refuse if path exists.  
2. **Auto-validate after each rung** — `validate_judge_adapter.py` (generic); ladder logs `mind_pass_rate` beside `train_loss`.  
3. **Tag-cluster ingest** — `viv_aifl_ingest.sample_files` seeds bridges/contracts/rid/core/shell before siblings.

```powershell
# Re-validate existing 320 (already scored 0.10):
L:\Continue\.venv\Scripts\python.exe scripts\validate_judge_adapter.py --adapter models/gpu/viv_voice_lora_judge_320 --steps 320 --limit 30

# Collect with tag clusters (n_files auto-boosts to ≥3 clusters when ≥2 requested):
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode ingest --files 5 --turns 8
```


---

## Operator runbook

```powershell
cd L:\Continue\Viv\foundation
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode ingest --files 3 --turns 5
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode mixed --turns 6
L:\Continue\.venv\Scripts\python.exe viv_shell.py aifl --mode identity --turns 5
```

Watch:

1. `artifacts/auto/aifl/run_latest.json` → `quality.mind_pass_rate`, `labels`, `ingest.links`  
2. `conversation.jsonl` — self-talk transcript  
3. `shadow_judge/preference_pairs.jsonl` — stamps  
4. If drift: edit judge criteria / compose rules — **not** hand-labeled chat

---

## Bugs fixed (record)

| Bug | Symptom | Fix |
| --- | ------- | --- |
| `"lie" in path` | `crystallize` → false “I don’t lie” overwrite | `\b(lie|lying|liar)\b` + skip self-ingest |
| GPU raw on ingest | Timestamp/digit garbage, Security blocks | Skip Ollama when ask is self-ingest |
| Teach Law 4 | `.py`/`.json` in memory string denied | `scrub_law4` before teach |
| Forced soft recall/know | Slow chat | Removed; wait_plant_s=0 |
| Plant wait 45s | Chat felt stuck | Default 0 |

*— Documented for Architect; AIFL is the first autonomous learning loop.*

---

## 2026-07-23 — AIOS backup prerequisite active

- Viv-local `security_core` 0.2.7 is active with typed backup authorization and
  a separately verified backup-ledger hash chain.
- Stage 1 registry freeze, training-run lease creation, and candidate-pointer
  mutation now create and verify a pre-mutation snapshot or fail closed.
- Bootstrap snapshot `903c052b…b6d4` reconstructed all 959 protected entries;
  all 38 hash-catalogued immutable model files were reverified without drift.
- Backup contract tests staged a real restore and confirmed `live_changed=false`.
- This milestone started no collection, training, evaluation, canary, or
  deployment. `validated_candidate=null`; Qwen remains live.
- Evidence: `artifacts/auto/backup_core/milestone_report_v1.json`.

Residual: the vault is same-volume protection. External/off-disk replication is
not configured.

---

## 2026-07-23 — Security-wrapped Triad active

- Training request and reply records now pass through Security, RID, AUTO, and
  UML before the typed Rust training authority decides admission.
- The fresh Master RID path now uses a `TriadSample`; the prior
  `SensorReading.runtime_rsr` mismatch is fixed and the offline CPU semantic
  judge contract passes.
- `viv_triad_contract_v1` is pinned in CPU and model configuration. Version
  mismatch, forged/expired context, malformed payload hash, low S_n, protected
  source mutation, or unsafe egress fails closed.
- This integration performed no collection, GPU training, evaluation, adapter
  promotion, or deployment.
