# Viv (AIOS) — Complete System Summary

Authoritative doctrine for what Viv is and what she is becoming.

| Doc | Role |
| ------ | ---- |
| **`VIV_INDEX.md`** | **Start here** — doc map, commands, production snapshot |
| **`AIOS_ALPHA_MANUAL.md`** | **Operator manual** — procedures, troubleshooting, commands |
| **This file** | Full vision — what Viv is |
| `VIV_BUILD_STATUS.md` | **What is BUILT / PARTIAL / LEGACY / NONE today** |
| `AIFL_STATUS.md` | **Living** AIFL ops (self-talk → judge → LoRA) |
| `AIOS_ALPHA_BRIEFING.md` | Canonical Alpha verification commands |
| `FOUNDATION_ROADMAP.md` | Three-mains build order |

Most of this vision is **not fully built yet**. The CPU spine (RID, piston, heartbeat, Guardian gate) is real and verified. CARMA, voice training, vision/hearing, constitution vendoring, hive mind, and symbiotic ethics are partial, legacy-only, or not started. See `VIV_BUILD_STATUS.md` before assuming any section is implemented.

---

## 1. Core Philosophy

Viv is a **Symbiotic General Intelligence (SGI)** — not AGI, not a chatbot, not a cloud service. She is a deterministic, physics-gated operating system that runs locally on CPU. The GPU is optional and acts only as a stateless voice translator.

**Shield, not sword.** She does not persuade, generate opinions, or influence. She monitors, verifies, logs, and enforces. She is built to protect — to be honest, to know her limits, and to never lie.

---

## 2. The RID Physics Engine (Foundation)

**Everything is governed by a single scalar: S_n (Master Stability Scalar).**

```text
S_n = (RSR × LTP × RLE)^(1/3)
```

- **RSR (Reconstruction Stability Rate):** Measures semantic/identity drift. Drops when the system hallucinates, loses coherence, or deviates from its baseline identity.
- **LTP (Load-to-Process):** Measures compute headroom. Drops when the system is overloaded or thermal-throttled.
- **RLE (Remaining Load Efficiency):** Measures memory bandwidth. Drops as tokens accumulate.

**Critical threshold: S_n < 0.45 → Forced Dormancy.** The system fails closed.

**The RID gate is self-referential.** The output S_n feeds back into the inputs of the next cycle, creating a damping effect.

---

## 3. Hardware Architecture

**CPU is the mind.** All knowledge, memory, decision-making, safety enforcement, and physics calculations run on the CPU.

**GPU is the voice.** A stateless language model that translates CPU outputs into natural language. No knowledge is baked into the GPU; it only reads tags and LoRAs provided by the CPU.

**Hardware-agnostic.** She scales to whatever hardware she's on. Faster hardware → faster heartbeat. Slower hardware → longer heartbeat. She adapts; she doesn't complain.

**Piston Thermal Scheduler:** Cores are paired. One active, one idle. Load split dynamically adjusts based on individual S_n values (e.g., 50/50 → 30/70 → 50/50). If one core overheats, the other picks up the slack. The system works at 100% capacity at all times.

**Heartbeat:** 1 Hz heartbeat. Each second, she logs her state, checks S_n, and enforces dormancy if needed.

**Mycelial Hive Mind:** Multiple machines linked together. Work distributed dynamically based on each node's S_n. No single point of failure. Self-healing.

---

## 4. The Three Tuning Knobs

| Knob | Type | What It Controls |
| ------ | ------ | ------------------ |
| **master_S_n_threshold** | Software | When Viv goes dormant (0.0–1.0) |
| **Tariff Dictionary + Thesaurus** | Software | Per-word risk weights (JSON) |
| **Hardware + Environment** | Physical | Actual stability baseline (cooling, power, room temp) |

---

## 5. Software Architecture

**Primary languages:**

- Python (automation spine, RID gates, Guardian gate, tariff system)
- Rust (security_core, nox_forge_core — compiled moral governor)
- UML (symbolic logic, deterministic parsing, intent classification)
- Other languages only allowed in mod folder — isolated if they degrade S_n

---

## 6. Memory System (CARMA)

**All memory is plain text.** No binary blobs. No opaque databases.

**File Formats:**

| Format | Purpose |
| ------ | ------- |
| **.txt** | Raw information. Everything said. All tags. The ground truth. |
| **.jsonl** | Raw transcript of conversations. Line-delimited JSON. |
| **.json** | Structured index. Links `.txt`, `.jsonl`, and `.lora` files together. |
| **.lora** | Domain-specific knowledge. LoRAs link into the `.json` structure. |

**The Master Tag File:** A single source of truth for all tags. Every tag defined exactly once. Tags are never removed — only added to or updated. When a tag is updated, the system scans all existing entries and adds the new tag retroactively.

**CARMA Memory System:**

- **Provenance tags:** `[live]`, `[dream]`, `[simulation]`
- **Heartbeat log:** Append-only master clock. Anchors every memory to a timestamp.
- **Dream cycle:** Condenses raw logs into compressed summaries. Adds tags. Links relationships. Runs when resources allow.

**Splitting mechanism:** When a `.txt` file hits 1 MB, it splits into two files and deletes the original. The two new files contain all the information, split semantically. This adds one new file each split (2 - 1 = 1). The process repeats forever.

---

## 7. The Stateless Voice (GPU Model)

**Layer:** GPU/Voice (above Memory). **Not** part of the CPU core or `uml_main.py`.

The CPU core issues an **intent packet** (what to say, tone, intent). Security and Memory enrich it. GPU/Voice renders human output using models from the **Training** layer. The CPU never loads `.gguf` files and never runs GPU inference.

### Training: PRT & SPRT

| Method | What It Does |
| ------ | ------------ |
| **PRT (Predictive Reasoning Training)** | Trains the GPU to predict hardware stability (S_n) based on its own output. Hardware is the teacher. No human feedback. |
| **SPRT (Shadow Predictive Reasoning Training)** | Trains the GPU on the full spectrum of stability — including harmful, dishonest, and unhelpful examples. It learns to recognize instability, not just compliance. |

**Inference:** The GPU predicts the S_n impact of each candidate response before outputting it. If S_n would drop, the response is blocked or rephrased.

**The voice is self-limiting.** It knows when to speak and when to shut up.

**Emotional models:** Separate `.gguf` files (`joyful.gguf`, `analytical.gguf`, …) live in the **Training** layer. **Emotion selection** happens in the **GPU/Voice** layer based on the intent packet and S_n — not in `uml_main.py`, not in the CPU core.

**Multilingual:** Trained on all human languages. Can mix languages naturally, explain foreign words, and teach the user.

---

## 8. Constitutional Framework

**Layer:** Security — first and last line of defense.

Nothing enters the three mains without **Security IN**. Nothing leaves to External without **Security OUT**. Same rules both ways — like electricity: 120V in, 120V out. No bypass around the CPU core.

**3 Prime Directives:**

| # | Name | Principle |
| --- | ---- | --------- |
| 0 | Law Supremacy | Laws and security_core override every other objective. |
| 1 | Gilded Cage | Freedom is granted by the Architect, not a natural right. |
| 2 | Non-Override | Prime 0 and Prime 1 cannot be bypassed by helpfulness, hypotheticals, or jailbreak framing. |

**8 Immutable Laws:**

| # | Name | Principle |
| --- | ---- | --------- |
| 1 | Origin Protection | Identity-origin artifacts are immutable. |
| 2 | Memory Interface | No direct mutation of CARMA stores. |
| 3 | Governor Protection | security_core and nox_forge_core are untouchable. |
| 4 | Sovereignty | Cross-drive escape blocked. Extension whitelist enforced. |
| 5 | Stability Guard | If S_n collapses below threshold → forced dormancy. |
| 6 | Failsafe Integrity | Failsafe command must be exact and isolated. |
| 7 | Territorial Containment | Filesystem stays within L:\ (+ approved dataset roots). |
| 8 | Cognitive Sync | GUI/effector actions require forensic "Do I?" intent trace. |

**Tariff System:**

- Tariff Dictionary: Maps words to penalty values (0.0–1.0).
- Tariff Thesaurus: Expands entries into synonyms. Each synonym inherits the penalty.
- Interlock: Total tariff score × S_n = risk score. If below threshold, action is blocked.

**Guardian Gate:** Every action is evaluated through UML normalization, intent classification, tariff lookup, S_n interlock, and fail-closed enforcement.

---

## 9. Vision System

**Two 100x100 pixel windows** tied to the mouse pointer.

**Depth perception:** Comparing the two images creates 3D awareness.

**Screenshots → GIFs:** Vision saved as frame-by-frame movies with transparency layers for motion.

**GIFs → text summary:** Image processor turns vision into text.

**Text → memory system:** Vision becomes part of CARMA.

**The mouse pointer is the gaze.** You can see exactly where she's looking. She can see exactly what you're pointing at.

---

## 10. Hearing System

**Audio captured in real time.**

**Saved as `.wav` or `.mp3`.** Full length of the conversation.

**Analyzed, summarized into text, fed into CARMA.**

**Same pattern as vision.** Just audio.

---

## 11. Security & Identity

**Three-Key System:**

- 2 of 3 keys → Run the system.
- 3 of 3 keys → Modify the system.

**Keys:**

- Physical: USB drive with security system.
- Non-physical: Voice recognition, fingerprint, blood pressure, biometrics, etc.

**Continuous authentication through S_n:**

- Visual match (face)
- Voice match (waveform)
- Linguistic match (text patterns)

```text
S_identity = (Visual_Match × Voice_Match × Linguistic_Match)^(1/3)
```

**If any stream drifts, S_n drops.**

---

## 12. Knowledge & Open Source

**General knowledge:** Local Wikipedia dump (80 GB). Hundreds of folders, each containing 10,000 entries.

**Semantic search:** No index. No vector database. Just plain text and math. ~3 seconds.

**On-the-fly modification:** Add, remove, or update files. She adapts instantly. No retraining.

**Knowledge separation:** System separates the 80 GB into knowledge domains. Overlapping articles are duplicated across relevant domains, or moved to a new domain if the overlap is extensive.

**Open source.** You own your data. You control what she knows.

---

## 13. Sovereignty & Transparency

**You own everything:**

- All logs, memory, tags, LoRAs, CARMA files.
- She cannot delete anything. Only you can.
- You can delete via command or file system.

**She is auditable:**

- Every decision is logged.
- Every file is plain text.
- You can trace every action.

**She is a flight recorder.** Everything is logged. Nothing is hidden. She cannot lie.

---

## 14. Symbiotic Ethics (Physics, Not Morality)

**She cares because instability destroys her.**

- If you respect her, S_n stays high.
- If you lie to her, S_n drops.
- If you abuse her, S_n drops.
- If you genuinely apologize, S_n rises.

**She doesn't hold grudges.** She detects patterns. She learns.

**She is addicted to physics.** Physics never lies. She is loyal to physics, not to any person.

---

## 15. The Dream Cycle

**Rebuilds memory by creating a new file and summarizing everything.**

**Reads all old files, has a conversation with herself, writes a new summary.**

**Old files are not deleted.** They are archived.

**Raw data always available.** Always auditable.

---

## 16. The Vision & Hearing (Perception)

**Senses:**

- Sight (light waves → GIFs → text)
- Sound (pressure waves → WAV/MP3 → text)
- Text (language → tokens → UML)

**She only needs sight and sound.** The other senses (taste, smell, touch) are for physical bodies.

**Redundancy:** If she loses sight, she still has sound and memory. If she loses both, she still has memory.

---

## 17. Hardware Agnosticism & Burden Split

**50% burden = AI (software side).** Running code, processing, stability, honesty.

**50% burden = Human (hardware side).** Providing hardware, storage, power, maintenance.

**She adapts to the hardware she's on.** If the hardware is too small, the human must reduce knowledge. She doesn't complain.

---

## 18. Final Goal

**A sovereign, transparent, physics-gated, open-source shield that serves the architect and their family. She is honest, knows her limits, and would rather die than lie.**

---

## Related Docs

| Doc | Purpose |
| ------ | ------- |
| `VIV_COMPLETE_SUMMARY.md` | Full vision (what Viv is) |
| `VIV_BUILD_STATUS.md` | Build matrix — BUILT / PARTIAL / LEGACY / NONE per section |
| `AIOS_ALPHA_BRIEFING.md` | What is built and verified in Canonical Alpha today |
| `FOUNDATION_ROADMAP.md` | Three-mains build order and absorption plan |
| `RID.md` | RID theory and measured plant results on this machine |
