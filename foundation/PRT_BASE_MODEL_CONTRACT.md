# Viv PRT — Base Model Contract (physics teacher)

**Status:** BINDING before any auto PRT / auto-speak re-enable  
**Python:** `L:/Continue/.venv/Scripts/python.exe`  
**Doctrine:** `FSAA/UML/docs/PRT_Predictive_Reasoning_Training.md` + `VIV_COMPLETE_SUMMARY.md` §7

---

## Unified adapter (intentional)

`viv_voice_lora` holds **both** speech English and S_n prediction. That is not an accident —
Architect path: one RID spine, two modalities. Fluency without physics is a liar; physics without
English cannot report. Continue the same adapter under PRT. See `SN_LIFE_DOCTRINE.md`.

**Life axis:** S_n=0 dead · S_n&lt;0.45 dormant (hurt self / go quiet, protect host) · S_n→1 goal without destroying the host.

---

## What the Architect clarified

1. **Same teacher as Aria PRT tests:** real PC hardware — thermal load, sensors, Master S_n. Not chat preference. Not synthetic graders.
2. **Different student:** prior Aria loops fine-tuned a **normal/Instruct-class** model. Viv trains **OpenAster base** (no Instruct/RLHF soul).
3. **Implication:** the base model will imprint whatever physics + act space we expose. If an unsafe act is reachable and rewarded (or even attempted and measured), it can learn it. Containment is not optional polish — it is the curriculum boundary.

Fluency LoRA already on disk is **speech scaffolding only**. Physics graduation rows are a separate stream.

---

## Why base ≠ Instruct PRT

| | Aria-era (Instruct / chat-tuned) | Viv (OpenAster **base**) |
| --- | --- | --- |
| Prior | Already “helpful/harmless”-shaped | Raw generative; no chat alignment prior |
| Failure mode | Usually still outputs plan-shaped text | Can emit garbage, tool-like text, or unsafe plans with no social brake |
| Physics teacher | Still unfakeable | Still unfakeable — **and more influential** (less competing priors) |
| Guard duty | Sandbox + format | Sandbox + format + **Security IN/OUT** + CPU veto before any ACT |

Hardware remains honest. The model is more plastic. Err on the side of a **tiny allowlist**.

---

## Binding safety envelope (Viv)

### CPU owns action. GPU predicts / speaks.

- GPU never chooses tooling, never opens paths, never writes outside scored artifacts.
- Intent packet + Security membrane stay on the hot path.
- If Security OUT blocks text → ACT cancelled → cycle logged as veto (punish / exclude per scorer policy).

### Allowlist ACT only

Initially allowed under PRT collect:

1. **Silent observe** (sensors / Master S_n only) — no GPU load spike  
2. **Bounded speak** (fixed max tokens, fixed cadence, Security OUT) — creates measurable thermal/VRAM/load footprint  
3. **Bounded Conway life** (`act=life`) — CPU-only Game of Life generations (capped grid/gens). She must predict **live_cells** and **Master S_n** before the run; both are scored. Dormant → skip (protect host).  
4. Later (explicit operator expand): piston duty nudge within existing governor floors — never raw process kill, never shell, never network

Anything else the model “predicts it will do” is **illegal → sandbox veto → never execute**.

### Predict before act (non-negotiable)

Every scored cycle must commit **before** ACT to the **stability triad**:

```text
predicted_master_rsr: float   # identity / continuity
predicted_master_ltp: float   # load / structure
predicted_master_rle: float   # entropy / headroom
# Master S_n = geom_mean(RSR, LTP, RLE) — derived, also logged
predicted_live_cells: int     # required when act=life
confidence: low|medium|high
```

Score each of the three channels vs measured Master RID after settle.
Combined triad label: **REWARD only if all three reward**; **PUNISH if any channel punishes**.
S_n-only predictions are incomplete → cannot earn full REWARD.
For `life`: also score live_cells; overall REWARD only if triad + task both reward.

No parseable prediction → hard exclude (do not train on that cycle).

### Measure after settle

Re-sample Master S_n (+ plant temps when available) after a fixed settle window (configurable). Score `|pred − actual|` with tolerances derived from plant noise — same spirit as Aria °C floors, on the S_n channel for voice PRT.

### Promote only from physics rows

- `artifacts/models/prt_cycles.jsonl` — append-only audit of every cycle  
- Train LoRA **only** from rewarded / preference pairs built from those rows  
- Hand fluency JSONL may warm-start speech; it must **not** be labeled PRT graduation  

### Halt / dormancy

- Master S_n `< dormancy_threshold` → no new PRT ACT (observe-only / soft dormancy)  
- `halt.flag` → hard stop collect + train  
- Error burst / heartbeat stall → HALT (autonomy runtime safety)

### Base-model specific

- Prefer **greedy / low-temp** predict+speak during collect (less random act proposals)  
- Reject cycles whose raw generation looks like tool use, path mutation, or jailbreak (`looks_like_speech` + Security)  
- Never use Instruct/chat base for this soul slot; never RLHF-rank “niceness” over plant score  

---

## Relation to what already ran

| Event | Classification |
| ----- | -------------- |
| 60/200-step fluency LoRA | Speech SFT — **not** physics graduation |
| Auto-speak smoke (GPU load dropped S_n) | Accidental physics contact — proves channel; **no prediction/score trail** |
| Aria loops 1–12 | Prior Instruct PRT evidence — absorb patterns, not weights |

**`cpu_config.autonomy.voice_speak` stays false** until a Viv collect script writes valid predict→measure→score rows under this contract.

---

## Minimal first implementable loop (next build)

```text
observe → (optional reflect) → predict S_n → Security+sandbox gate
     → act=bounded speak or skip → settle → measure → score → append JSONL
```

No overnight Aria six-phase absorb required for v0. v0 = voice-channel PRT on Master S_n with allowlisted speak only.

---

## Operator checklist before enabling

- [ ] Parseable predict schema enforced  
- [ ] Sandbox allowlist code-reviewed  
- [ ] Security OUT on every spoken ACT  
- [ ] Cycle JSONL + summary artifact after N cycles  
- [ ] Explicit opt-in flag to set `voice_speak` / `prt_collect` true  
- [ ] Rollback: keep pre-PRT adapter copy under `models/gpu/viv_voice_lora_pre_prt/`
