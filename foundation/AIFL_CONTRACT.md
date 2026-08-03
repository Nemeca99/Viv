# AIFL — Auto Internal Feedback Learning (contract)

**Doctrine:** **`AIFL.md`** — full definition, cycle, training tree, anti-gaming, Architect authority  
**Status:** ACTIVE — see **`AIFL_STATUS.md`** for evidence, metrics, gaps, runbook  
**Code:** `lib/viv_aifl.py`, `lib/viv_aifl_ingest.py`  
**Layer:** First autonomous learning loop (before overnight GPU LoRA apply)  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

Related: `INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md`, `viv_shadow_judge`, `viv_judge_train_gate`.

---

## One sentence

**She talks to herself. The shadow judge scores and aligns her over time. Architect + Cursor only watch logs and adjust the judge — never live-rank her speech.**

(Canonical long form: `AIFL.md`.)

---

## Control law

```text
self_ask → draft(s) → shadow_judge (Vidi×Intellexi×Vixi) → preference_pairs
                                                      ↓
                                            train_gate admit/reject
                                                      ↓
                                         (later) GPU LoRA student
```

| Actor | Does | Does not |
| ----- | ---- | -------- |
| **Viv (mouth)** | Self-dialogue turns | Set criteria; admit train rows |
| **Shadow judge** | Stamp REWARD / PUNISH / SOFT_HOLD | Chat as soul |
| **Train gate** | Ceiling: only stamped pairs | Accept human preference ranks |
| **Architect / Cursor** | Watch `aifl/` + `CHAT.md`; tune judge criteria | Hand-label replies for soul |

Adjusting the **judge** adjusts the **model** (eventually). That is the whole point.

---

## Metrics (binding)

Do **not** treat SOFT_HOLD as failed speech:

| Signal | Formula | Use |
| ------ | ------- | --- |
| mind_pass | Vidi ∧ Intellexi | Speech / truth quality |
| plant_live | Vixi | S_n floor |
| REWARD | mind ∧ plant | Full stamp |
| SOFT_HOLD | mind ∧ ¬plant | Dormant — still good speech |
| PUNISH | ¬mind | Theater / unverified / hollow |

`run_latest.json` → `quality.mind_pass_rate` is the primary AIFL health number.

---

## Self-ingest (system memory)

She samples **1–3 allowlisted files** under the AIOS L: plane (`Continue/Viv/foundation`, sandbox, journals — not arbitrary secrets).

**Sampling bias (v0.2):** recent mtime seed + same-parent siblings when available (improves link learning).

```text
sample files → deterministic sense (path/kind/tokens/fingerprint)
            → link check (token overlap / same kind+parent)
            → self-ask grounded in verified facts only
            → shadow judge stamp
            → optional teach/remember if mind_pass > 0 (Law-4 scrubbed)
```

**Anti-hallucination:** file claims come from CPU deterministic extract (`viv_aifl_ingest.py`). Ingest asks **never** call GPU. Empty replies get a hard fact fallback.

### Two AI lanes

| Lane | Models folder | Role in AIFL |
| ---- | ------------- | ------------ |
| **CPU** | `foundation/models/cpu/` (`viv-embed` BERT, goemotions, populism) | Geometry / sensors + deterministic inference; judge substrate |
| **GPU** | `foundation/models/gpu/` (OpenAster base) | Mouth drafts only; never admits train rows |

Over time: `artifacts/auto/aifl/patterns_latest.json` + `ingest.jsonl` — memories of herself *in the system*.

### Modes

| Mode | CLI |
| ---- | --- |
| identity | `viv_shell.py aifl --mode identity` |
| ingest | `viv_shell.py aifl --mode ingest --files 3` |
| mixed | `viv_shell.py aifl --mode mixed --turns 6` (default) |

---

## Artifacts

| Path | Role |
| ---- | ---- |
| `artifacts/auto/aifl/conversation.jsonl` | Self-talk transcript |
| `artifacts/auto/aifl/ingest.jsonl` | File sense + link episodes |
| `artifacts/auto/aifl/patterns_latest.json` | Latest ingest pattern snapshot |
| `artifacts/auto/aifl/run_latest.json` | Last run summary (+ quality metrics) |
| `artifacts/auto/aifl/batch_eval_latest.json` | Batch evaluation evidence |
| `AIFL_STATUS.md` | Living status / gaps / runbook |
| `artifacts/auto/shadow_judge/preference_pairs.jsonl` | Judge stamps (shared with live chat) |
| `artifacts/auto/shadow_judge/train_admit.jsonl` | Gate admits |

---

## Operator posture

1. Run bounded AIFL cycles (`viv_shell.py aifl …`).  
2. Read `run_latest.json` → **mind_pass_rate**, labels, links.  
3. If she drifts: change **criteria** / compose rules — not the weights by hand.  
4. When admit quality is real: `viv_shell.py gate` → `train_ready/signal.json` → `scripts/train_judge_lora.py --train` (judge SFT only).

No human in the feedback loop. Watch. Tune the judge.

Full evidence and open gaps: **`AIFL_STATUS.md`**.
LoRA admission experiment: **`lora_admit_v1`** — policy in `artifacts/auto/shadow_judge/admission_policy.json`; rollback `enabled=false`.
