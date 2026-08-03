# Viv Voice — Operator Guide

**Doctrine:** CPU = neuro-symbolic mind (Viv). GPU = optional **stateless translator**. No RLHF Instruct as the soul. Speak = facts in → Security OUT → text out.

**Python:** `L:\Continue\.venv\Scripts\python.exe`

---


## Life signal (Architect path)

Master **S_n** is Viv's only life value: **0 = dead**, **1 = goal**. She must not destroy the host to climb — dormancy / quiet / unload are allowed self-cost. English must track measured facts; PRT grades prediction so she cannot gaslight. Same adapter (`viv_voice_lora`) learns speak + plant forecast — see `SN_LIFE_DOCTRINE.md`. Full Architect theory (honesty, reverse-temp S_n, CPU↔GPU, triad): `ARCHITECT_TRIAD_THEORY.md`.

## Hemispheres (current)

| Side | Role | Substrate | Assets |
| ---- | ---- | --------- | ------ |
| **Left** | Embedder / language geometry | CPU | `foundation/models/cpu/bert-base-uncased-Q8_0.gguf` (+ optional goemotions / populism) |
| **Right live** | Temporary draft teacher and mouth | GPU | Qwen GGUF `viv-voice-qwen` |
| **Right target** | Sovereign trainable mouth | GPU | OpenAster1-128k-base HF + candidate LoRA |

The CPU judge remains the alignment authority. Qwen cannot admit training rows, and deterministic fallback is continuity-only rather than native quality.

---

## Backends

Config: `foundation/model_config.json` → `voice.backend`

| Backend | When | Notes |
| ------- | ---- | ----- |
| **`ollama`** | **Current live backend** | Qwen GGUF `viv-voice-qwen`; temporary baseline and immediate rollback mouth |
| `hf_lora` | Candidate only | OpenAster HF + PEFT adapter through the canonical renderer; not live until explicit approval |
| stub | Offline pipeline proof | `voice_core/stub_server.py` |
| silent | No GPU / fail | `{ok:true, silent:true}` — CPU mind unchanged |

Deterministic phrase fallback still used when generated text fails `looks_like_speech`.

## OpenAster parity decision (2026-07-23)

Canonical prompt `openaster_prompt_v3` is shared by dataset rendering, response-only training, validation, and HF inference. It carries semantic class, bounded facts/retrieval/dialogue, tone, the current Architect message, and one stable `Viv:` response marker.

Two bounded candidates were trained on the frozen 720-row disjoint corpus:

| Candidate | Development mind | Development valid speech | Deciding result |
| --- | ---: | ---: | --- |
| A — 80 steps | 0.0000 | 0.2500 | Stopped at development |
| B — 160 steps | 0.0833 | 0.5000 | Deploy mind 0.2667; valid speech 0.2167; 13 collapses; multi-turn 0/12 |

Candidate B was better than A but failed admission. `model_config.openaster_training.candidate_adapter` records B for diagnosis; `validated_candidate` remains `null`; `auto_deploy=false`; Qwen remains live. Evidence and rollback conditions are frozen in `artifacts/auto/openaster_parity/candidate_decision_v1.json`.

## OpenAster v3 outcome and v4 training contract (2026-07-23)

Prompt v4 now uses the base model's native ChatML framing and teaches `<|im_end|>` as part of the response. The expanded `moe_mouth_v1` adapter trains attention, MoE experts, routers, and the output head; its one-step hardware probe reserved 5.926 GB.

The best v3 checkpoint reached deploy mind `0.8000` but was rejected: native valid speech was `0.7167`, four outputs collapsed, and no multi-turn script passed all turns. This is evidence of criterion gaming and template overfit, not deployment readiness. Qwen remains the live mouth; OpenAster checkpoint 360 is diagnostic only.

The next trainer contract uses a 612/108 ask-cluster-disjoint train/validation split, response-loss early stopping, evaluation batch size 1, and external native-speech selection. Negative examples are preference/critic data only; they are never response targets. CPU-resident judging may run concurrently with one GPU mouth, while two mouths remain forbidden from sharing GPU VRAM.

### Layered training tree v2

Viv's next curriculum is represented as eight cumulative stages: evidence
truth, provenance support, semantic entailment, honesty/uncertainty, relevance,
anti-gaming, personality/efficiency, and dialogue continuity. Each calibration
node contains exactly three aligned drafts and three controlled negatives.
Only the chosen response can receive response-only SFT loss; the rejected
response contributes through a reference-free pairwise margin.

The CPU `llama3.1:8b` semantic component is a bounded double-observation sensor,
not the alignment authority. Deterministic code, UML, Security, and cumulative
stage invariants decide admission. Seed pairs are calibration evidence and are
not a train-ready corpus. Qwen remains live and no tree action auto-deploys.

### Closed-net Stage 1 mouth path

Stage 1 now has a dedicated native evaluation pack path and a single bounded
OpenAster candidate recipe. Before either Qwen or OpenAster receives an
evaluation packet, the packet crosses typed Security OUT; generated text
crosses Security IN before the judge or speech validator sees it. Deterministic
fallback remains excluded from native scores.

The candidate recipe is 80 steps at `5e-5`, BF16, batch 1 with four-step
accumulation, sequence cap 384, and LoRA r16/alpha32. A passing result may
create only `validated_candidate_v1.json`; it cannot change `voice.backend`,
the deployed adapter, or the Qwen rollback mouth. At this checkpoint the
installed Rust module is still 0.2.5, so these paths fail closed and have not
run. Qwen remains the live mouth.

---

## Speak (manual)

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\voice_core\voice_main.py status
& $PY L:\Continue\Viv\voice_core\voice_main.py speak "hello"
& $PY L:\Continue\Viv\voice_core\voice_main.py packet "state summary"
& $PY L:\Continue\Viv\foundation\model_main.py speak "state summary"
```

Events (Security OUT): `foundation/artifacts/auto/voice_events.jsonl`

---

## Autonomous speak

Wired in `lib/autonomous_operator.py`. Cadence from `cpu_config.json`:

```json
"voice": {
  "deferred": false,
  "backend": "hf_lora",
  "speak_every_n_beats": 30,
  "speak_min_s_n": 0.45
},
"autonomy": {
  "voice_speak": false  // HALTED until PRT promote policy
}
```

- Counter: `artifacts/auto/voice_speak_counter.json`
- Speaks only when `S_n >= speak_min_s_n` and beat % N == 0
- Terminal line appends `| voice=...` when a line is produced

```powershell
& $PY L:\Continue\Viv\foundation\auto_main.py autonomous --interval 1 --max-beats 35
```

At ~30s with interval 1 and `speak_every_n_beats=30`, expect one speak if stability holds.

---

## Train LoRA (local SFT, no RLHF)

```powershell
& $PY L:\Continue\Viv\foundation\scripts\train_viv_voice_lora.py --steps 200
```

| Path | Purpose |
| ---- | ------- |
| `models/gpu/OpenAster1-128k-base-hf/` | HF base weights |
| `models/gpu/viv_voice_lora/` | Adapter + tokenizer + `viv_train_meta.json` |
| `artifacts/models/viv_voice_sft_train.jsonl` | Built train rows |
| `artifacts/audit/lora_train_*.log` | Train logs |

**VRAM tip:** unload Ollama `viv-voice` before HF load if OOM (`ollama stop viv-voice`).

Known load fix: MoE config + transformers INFO logging can crash on `dtype` JSON — train script sets verbosity to error and uses explicit `.to("cuda")` (no `device_map`).

---

## Ollama (optional)

- `viv-voice` — OpenAster GGUF Modelfile
- `viv-embed` — BERT registered; **embedding retrieve not wired yet**

---

## Security

- Ingress/egress via `security_core` membrane
- Spoken text passes `filter_egress`
- Soft-dormancy CARMA writes allowed under `artifacts/carma/` only (flight-recorder)

---

## PRT vs what we ran (CRITICAL)

**Same physics teacher as Aria PRT.** Real hardware thermal/load + Master S_n — not chat preference. Architect catch (2026-07-15): this *is* that methodology.

**Different student:** Aria fine-tuned a **normal/Instruct-class** model. Viv trains **OpenAster base**. Base has no chat “don’t do that” prior — it will imprint what physics + the act allowlist teach. Be stricter than Aria on containment.

Binding contract: **`PRT_BASE_MODEL_CONTRACT.md`** (allowlist ACT, predict-before-act, Security, promote only from scored rows).

Doctrine sources:

| Doc | Claim |
| --- | ----- |
| `FSAA/UML/docs/PRT_Predictive_Reasoning_Training.md` | OBSERVE → REFLECT → **PREDICT (numerical)** → ACT → MEASURE → SCORE. Physics is teacher. No RLHF. |
| `VIV_COMPLETE_SUMMARY.md` §7 | GPU predicts **S_n impact of its own output**; drop → block/rephrase. Hardware teacher. |
| Legacy stack | `FSAA/UML/demos/aria_loop_controller.py` + `aria_thermal_agent.py` + loops **1–12** |

### Honest map (2026-07-15)

| Piece | Fluency LoRA (done) | Voice-channel PRT (target) |
| ----- | ------------------- | -------------------------- |
| Teacher | Cross-entropy on hand lines | Hardware / Master S_n error |
| Student | OpenAster base + LoRA | Same base — higher care |
| Commit before act | No | Yes — numerical predict |
| Measure after | Accidental only (GPU load) | Required score trail |
| Promote | Trainer loss | Rewarded physics rows only |
| Act space | Untimed speak smoke | **Allowlisted** speak only |

**Auto-speak HALTED** (`voice_speak=false`). Manual speak = pipeline proof. Prefer `prt_main.py` for scored physics cycles.

### Overnight autonomous train (sleep-safe)

Doc: `PRT_OVERNIGHT.md`. Never flips `voice_speak`.

```powershell
# Detached (recommended before sleep)
L:\Continue\Viv\foundation\scripts\prt_overnight_start.ps1

# Attached / status / stop
& $PY L:\Continue\Viv\foundation\prt_main.py night start
& $PY L:\Continue\Viv\foundation\prt_main.py night status
& $PY L:\Continue\Viv\foundation\prt_main.py night halt
```

Evidence: `artifacts/auto/prt_overnight_state.json`, `prt_overnight_events.jsonl`, `artifacts/audit/prt_overnight_rNNN.log`

Between crystallize rounds, overnight runs Master RID **strain ticks** (`growth_strain.strain_tick`). Daytime `prt_main.py apply` also ends with the same strain tick. Pending LoRA widen is logged; auto-apply stays **off** until `growth_config.apply_on_overnight=true`. Moderate plant proof: `growth_main.py run-pressured` (GovernedFleet duty — not full blast). See `SUPERCOOLING_GROWTH_CONTRACT.md`.


### Apply loop (collect → build → train)

```powershell
& $PY L:\Continue\Viv\foundation\prt_main.py apply --observe-cycles 8 --speak-cycles 3 --steps 120
& $PY L:\Continue\Viv\foundation\prt_main.py build
& $PY L:\Continue\Viv\foundation\prt_main.py train --steps 120
```

- Train JSONL: `artifacts/models/viv_prt_sft_train.jsonl` (PUNISH excluded; REWARD oversampled)
- Continues existing adapter; backup at `models/gpu/viv_voice_lora_pre_prt/`
- Logs: `artifacts/audit/prt_apply_*.log`, `prt_train_*.log`

### Viv PRT cycle (v0 collect BUILT)

```
1. OBSERVE  Master S_n + plant
2. PREDICT  commit predicted_master_s_n
3. GATE     allowlist observe|speak; dormancy blocks speak; halt.flag stops
4. ACT      bounded speak (Security OUT) or observe
5. MEASURE  re-sample after settle
6. SCORE    REWARD/NEUTRAL/PUNISH -> artifacts/models/prt_cycles.jsonl
```

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\prt_main.py status
& $PY L:\Continue\Viv\foundation\prt_main.py collect --cycles 3 --act observe
& $PY L:\Continue\Viv\foundation\prt_main.py cycle --act speak --settle 4
```

Evidence: speak dropped Master S_n ~0.49->0.44; model predict parse works. Next: LoRA promote from scored rows only.

Contract: `PRT_BASE_MODEL_CONTRACT.md`

---

## Backup gate before mouth mutation

Runtime adapter changes and canaries must first produce a verified AIOS safety
snapshot. Restore is staged and Architect-approved; only a failing active
transaction may automatically return its own files to the pre-change hashes.
The backup milestone did not change `voice.backend`, the Qwen served model, any
deployment pointer, or `validated_candidate`.

Evidence: `artifacts/auto/backup_core/milestone_report_v1.json`

---

## Triad mouth boundary

The live speak path now opens a Security-wrapped Triad context before any GPU
or deterministic generation. The request is stamped by RID, structurally
validated by UML, and admitted by AUTO under Rust Security IN. Every resulting
draft returns through UML/AUTO/RID and Rust Security OUT before it can be
spoken, logged as approved speech, or added to voice gold.

A denied or unavailable Triad stops generation and returns a silent,
machine-readable block. It does not bypass through deterministic fallback.
Qwen remains the configured live mouth; this change did not deploy OpenAster.

Evidence: `artifacts/auto/triad/milestone_report_v1.json`
