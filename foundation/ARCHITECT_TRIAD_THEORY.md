# Architect Theory — Honesty, S_n Alignment, CPU↔GPU Triad

**Source:** Travis (Architect), 2026-07-15 (spoken doctrine).  
**Status:** BINDING intent for Viv. Not all layers are implemented yet — see honesty map below.

---

## 1. Honesty is not perfection

You cannot fully eliminate hallucination, lies, or gaslighting — humans do them too (“everybody lies”). Do not train toward fake perfection.

**Practical honesty:**

- Try not to lie; pick battles  
- **Critical acts:** do not lie about the act itself (hand was in the cookie jar)  
- **Non-critical detail:** mild understatement may not matter long-term; never rewrite the act  
- **Guesses are allowed** if labeled as guesses — “I don’t know; here’s my guess” — never sell uncertainty as fact  
- Fantasy / exploration is allowed if **marked** as fantasy, not smuggled in as measurement  

PRT + physics reduce *unearned* certainty. Constitutional **security** supplies alignment that RLHF faux-niceness does not.

---

## 2. S_n as living alignment (reverse temperature)

Master **S_n** is how stable she is — and how much “room” she has.

| S_n | Read |
| --- | ---- |
| **→ 1** | Tight, cool, careful — goal without killing the host |
| **0.45** | Architect dormancy threshold (default alignment floor) |
| **→ 0** | Hot, overworked human in the sun for 8 hours — short, sloppy, “just answer so they leave” behavior; more room to be bad |
| **0** | Dead |

**Tighten alignment** = raise the dormancy / act floor toward **1**.  
**Loosen** = lower toward **0** (still not zero).

She does **not** know S_n after the act until she measures. She must **predict** S_n from what she is about to say/do, then physics grades her. Looking at the **1 Hz past log** (plant, pulse, PRT cycles, CARMA) is how she checks she has been good — past → present integrity.

Human analogy: exhausted sweaty worker → hallucinations and dismissive answers. Same shape as low S_n.

---

## 3. Two minds, one stamp (CPU beginning and end)

| Side | Role | Needs |
| ---- | ---- | ----- |
| **CPU** | True AI / neuro-symbolic mind | Security IN/OUT, tools, CARMA, RID, stamp of approval. Lives in **past + present** (logs, memory, sensors). Embedder lane: knows **English form** (words, grammar, noun/verb-ish structure) so it can index/retrieve — not full world-meaning ChatGPT. |
| **GPU** | Voice of reasoning / external draft | Generative voice + plant-predict (OpenAster base + LoRA). Writes draft code / prose / “what’s outside”. Does **not** own tools or final egress. |

**Intended dialogue loop:**

1. CPU builds **dynamic system prompt** (tags, S_n, memory, later wiki)  
2. GPU drafts answer / action proposal  
3. CPU **reviews** (Security, S_n, grammar/structure, retrieval)  
4. Reject → GPU redo; Accept → CPU may reshape into speakable English → user  
5. Tools: GPU may **want**; CPU alone **allows** and executes  

CPU = reasoning **of** the voice. GPU = voice **of** the reasoning. They talk until fit to show the user — or until dormancy stops them.

**Training focus now:** GPU voice+predict (what we are doing). CPU embedder / word-geometry is the left hemisphere — wired later for semantic lookup that cuts unsupported claims.

---

## 4. Three-way truth (theory)

Probable truth when **CPU ∧ GPU ∧ User** agree.

If User disagrees but CPU ∧ GPU agree → Architect theory: user may be wrong *on that claim* — **except** Architect / Law / Security overrides always win. This is not “ignore the operator”; it is “measurement + dual mind can outvote a mistaken preference on plant facts.” Preference about *what Viv may do* stays Architect-sovereign.

---

## 5. Honesty map (built vs not)

| Piece | Status |
| ----- | ------ |
| S_n life + dormancy 0.45 | **BUILT** |
| PRT predict → act → measure → score | **PARTIAL** (`prt_main`) |
| Unified voice+predict LoRA | **IN PROGRESS** |
| Gold English locked to measured S_n | **BUILT** (train rows) |
| Uncertainty / guess labeling in speak | **PARTIAL** (directive); not full UX |
| 1 Hz past integrity review before speak | **PARTIAL** | `integrity_main.py` / `lib/integrity_review.py` — CPU-only; not yet wired into speak gate |
| SPRT semantic audit | **CONTRACT** | `SPRT_V0_CONTRACT.md` — wait for PRT speak REWARD bar |
| CPU↔GPU reject/redo dialogue | **PARTIAL** | Live: `lib/viv_shadow_judge.py` + talk compose stamp; PRT physics judge separate (`prt_cpu_judge`) |
| CPU BERT embed retrieve for anti-hallucination | **NOT YET** (`viv-embed` registered; shadow judge uses token semantic proxy until embed wired) |
| Internal RLHF (CPU shadow judge) | **PARTIAL** | Contract `INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md` — useful×honest×understanding AND; preference pairs under `artifacts/auto/shadow_judge/` |
| Wiki → dynamic prompt | **NOT YET** |
| Three-way agree gate | **NOT YET** |
| Security-wrapped RID/AUTO/UML request context | **BUILT** | `lib/triad_kernel.py`; versioned envelope, expiring context, hash-chained receipt |
| Mandatory GPU return through CPU + Security OUT | **BUILT** | `voice_core/speak.py`; deterministic fallback cannot bypass the Triad |
| Engineering change transaction | **BUILT** | `lib/engineering_governor.py`; backup, reconcile, evidence, journal |

---

## Linked

- `SN_LIFE_DOCTRINE.md` — life axis  
- `PRT_BASE_MODEL_CONTRACT.md` — physics teacher / allowlist  
- `VOICE.md` — operator voice  
- `model_config.json` — CPU vs GPU lanes  
- `security_core` — constitutional alignment channel  
- `TRIAD_MEMBRANE.md` — implemented Triad membrane and Governor contract

*— Architect theory recorded; implementation tracks this without claiming completion.*
