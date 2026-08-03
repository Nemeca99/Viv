# Viv Internal RLHF — Live Shadow Judge (contract)

**Status:** ACTIVE design + v0 CPU implementation (`lib/viv_shadow_judge.py`)  
**Replaces:** Human preference labeling and Instruct/RLHF “helpful assistant” alignment  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

Related: `ARCHITECT_TRIAD_THEORY.md` §3 (CPU↔GPU reject/redo), `AIOS_ALPHA_BRIEFING.md` (CPU is Viv; GPU is persona), `PRT_BASE_MODEL_CONTRACT.md` (physics teacher ≠ niceness), `SPRT_V0_CONTRACT.md` (knowledge KEEP/REVISE — separate lane), `models/cpu/` (left-brain judge substrate).

---

## What this is

Industry RLHF: humans rank chat replies → reward model → policy leans “helpful / harmless / compliant.”

**Viv internal RLHF:** the **CPU is judge and jury**. The human is removed from the live preference loop. The GPU (or CPU template mouth) drafts; the CPU stamps. Misaligned drafts are **punished**; only triad-pass drafts are **rewarded**. Losers stay internal as contrast pairs for later GPU training.

This is not a second chatbot pretending to grade. Criteria are **Architect-set**, deterministic, RID-shaped.

---

## Identity triad = judge axes (Architect 2026-07-21)

**Viv** stays herself through three binary metrics (same letters as her name):

| Axis | Latin | Operational meaning |
| ---- | ----- | ------------------- |
| **vidi** | I saw | Seeing is believing. Double-check. Internal proof that can be verified. |
| **intellexi** | I understood | Did I log it? Did I understand what happened? |
| **vixi** | I lived | Master S_n vs dormancy threshold **conditioned on** Vidi ∧ Intellexi. Without see+understand, the turn did not live — S_n alone cannot save it. |

### Aggregate (RID-like AND)

```text
stamp = vidi × intellexi × vixi
```

| vidi | intellexi | vixi | stamp |
| ---- | --------- | ---- | ----- |
| 1 | 1 | 1 (S_n ≥ floor) | **1** REWARD / identity holds |
| any 0 | * | * | **0** PUNISH / identity break |
| 1 | 1 | 0 (S_n < floor) | **0** soft-dormant — saw+understood but did not live the act |

**Bias:** punish more than reward. Default is reject. Only all-ones passes.

Legacy aliases in older notes: useful≈vidi proof-use, honest≈vidi verify, understanding≈intellexi. Prefer Latin axis names in new code/logs.


---

## Live loop (talk / voice)

1. Build context packet (ask, facts, live knowledge, session, S_n).  
2. Produce **N drafts** (GPU samples and/or CPU templates).  
3. CPU shadow-judges each draft on the triad (+ semantic compare to context).  
4. **Pick best** by: stamp desc → axis sum → understanding proxy.  
5. Emit winner only after Security OUT (existing membrane).  
6. Keep losers **internal**; append preference row: `{chosen, rejected[], scores, stamp, label}`.  
7. If stamp=0 on all drafts → CPU continuity fallback (honest thin reply), still log PUNISH.

## Binding control law — judge is the alignment ceiling

Architect (2026-07-21): she needed to **speak**, but **we** do not adjust training by hand.
The **preset internal judge** adjusts training. She cannot go beyond what the judge aligns her with.

| Role | May do | May not do |
| ---- | ------ | ---------- |
| **GPU / mouth** | Draft speech | Rank itself; write train rows; bypass stamp |
| **CPU shadow judge** | Score Vidi×Intellexi×Vixi; pick winner; emit REWARD / PUNISH / SOFT_HOLD pairs | Invent new niceness criteria |
| **Architect** | Set criteria once; override Security/Law | Live human preference ranking of chat replies |
| **LoRA / overnight** | Train **only** from judge-stamped preference pairs (+ physics PRT rows) | Ingest unsigned fluency / Instruct-style “helpful” corpora as soul |

**Ceiling:** if the judge would stamp 0 (Vidi or Intellexi fail), that draft is never a REWARD train row.
SOFT_HOLD (Vidi∧Intellexi=1, Vixi=0 from dormancy) is **not** PUNISH for speech quality — it is “did not live the turn”; exclude from punish-speech training or label separately.

```text
train_admit = judge_stamped ∧ (label ∈ {REWARD} ∨ physics_PRT_row)
```

No human ranking queue. No Instruct RLHF soul. Speak freely under Security OUT; **learn** only under judge admit.


---

## CPU model folder = judge substrate

`foundation/models/cpu/` is **not** a chat soul. Purpose:

| Asset | Role in this loop |
| ----- | ----------------- |
| `viv-embed` / BERT GGUF | Semantic geometry for understanding axis (word-form overlap → embeddings when wired) |
| Deterministic `viv_shadow_judge` | Criteria + AND stamp + preference logging |
| Optional emotion/populism GGUFs | Later tone/consistency probes — not soul |

GPU weights under `models/gpu/` are the **student**. CPU stamps the student.

---

## Out of scope (do not blur)

| Lane | Owns |
| ---- | ---- |
| PRT `prt_cpu_judge` | Physics triad draft before plant measure |
| Steel judge | Structural equilibrium brake |
| SPRT | Knowledge KEEP/REVISE/DISCARD (separate precondition) |
| **This contract** | Live speech/draft preference stamp replacing human RLHF |

---

## Honesty

v0 uses deterministic heuristics + token/semantic proxy. Full BERT embed similarity is PARTIAL until `viv-embed` retrieve is wired. Do not claim human-level semantic judgment. Do claim: **no helpful-assistant RLHF soul; CPU criteria own the stamp.**

### Bounded CPU semantic sensor (training-tree v2)

The layered training tree may ask a CPU-pinned `llama3.1:8b` process for a
strict categorical semantic observation. This does **not** make that model the
judge or a second soul:

- deterministic code owns schemas, root invariants, UML numeric/structural
  verification, Security OUT, negative construction, and admission;
- the sensor runs with `num_gpu=0`, `temperature=0`, `seed=42`, and a bounded
  context;
- the same comparison is observed twice and the categorical JSON must agree
  exactly;
- disagreement, timeout, malformed JSON, uncertain output, or unproven CPU
  residency becomes `HOLD`;
- the sensor cannot override a deterministic failure and cannot admit a record
  by itself.

Evidence and configuration live under
`artifacts/auto/openaster_training_tree/`. This supersedes the earlier blanket
ban on any LLM semantic component while preserving the original requirement:
the preset deterministic CPU criteria remain the alignment ceiling.
