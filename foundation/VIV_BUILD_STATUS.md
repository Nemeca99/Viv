# Viv (AIOS) — Build Status Matrix

Maps `VIV_COMPLETE_SUMMARY.md` vision to what exists **today** on this machine.

**Canonical Alpha root:** `L:\Continue\Viv\foundation\`  
**Legacy absorption sources (not Alpha):** `L:\Continue\FSAA\`, `L:\Continue\automation\`, Steel_Brain, Luna/AIOS_V2

## Status Legend

| Status | Meaning |
| ------ | ------- |
| **BUILT** | Runnable in Viv foundation with real artifacts or verified commands |
| **PARTIAL** | Some Viv code or legacy code; spec incomplete or not wired end-to-end |
| **LEGACY** | Real code exists outside Viv; not absorbed into Canonical Alpha |
| **NONE** | Doctrine/vision only; no implementation found |

**Build order (roadmap):** `auto_main` done → `rid_main` in progress → `uml_main` next. Everything below that stack is future absorption unless marked BUILT.

**Rebuild doctrine:** Partial builds already exist in legacy trees. Canonical Alpha does not try to finish everything at once. Finish **one layer and one system at a time**, with the **three foundation mains solid first**. Layers above the mains (CARMA, constitution, GPU voice, vision, hearing, knowledge, hive) wait until `rid_main.py`, `auto_main.py`, and `uml_main.py` each meet their “solid” bar in `FOUNDATION_ROADMAP.md`.

**2026-08-03 reconciliation:** The three mains and foundation preflight are now green, and a bounded knowledge seam has been added beneath the CPU-controlled mouth path. This changes knowledge from `NONE` to `PARTIAL`, not to complete Wikipedia/CARMA absorption: local dataset sampling, explicit Wikipedia REST lookup, runtime-authority records, provenance hashes, CPU retrieval ranking, and grounded-response containment are wired and read-only. The full 80 GB corpus is not yet inventoried, imported, or promoted into CARMA. `viv-embed` remains unavailable as a semantic embedding backend, so claim alignment remains `INCONCLUSIVE`.

---

## Summary at a Glance

| Status | Count | Sections |
| ------ | ----- | -------- |
| **BUILT** | 6 | §2 RID, §3 piston/heartbeat, §6 CARMA phase 1, §7 voice Phase 1b (LoRA+auto), parts of §5/§8/§13 |
| **PARTIAL** | 9 | §1, §3–§5, §8–§9, §11–§13, §15–§17 |
| **LEGACY** | 6 | CARMA, dream, vision, Rust cores, wiki batches, full constitution |
| **NONE** | 3 | §10 hearing, §14 symbiotic ethics loop, §18 (aspirational) |

### Skeleton spine (2026-08-07) — **SKELETON / PARTIAL**

| | |
| --- | --- |
| **Status** | Structural spine landed; not a claim every core is fleshed |
| **Map** | 39 systems · structural coverage **100%** · PARTIAL **23.1%** · SKELETON **76.9%** |
| **Bus** | 13 slots · filled **92.3%** (12/13) · vacant for compute-core: `uml_invoke` only (`subagent_spawn` BOUND → `aios_subagent_v1`) |
| **Overnight gaps** | `perception_core` / `ethics_core` / `federation_core` stubs + bus slots `perception_plan` / `ethics_plan` / `federation_plan` / `hardware_plan` |
| **Smoke** | System skeleton smoke **PASS 12/12** (already done; do not rebuild) |
| **Latest map** | `artifacts/auto/aios_skeleton/LATEST.json` + `skeleton_map_latest.json` |
| **Latest smoke** | `artifacts/auto/system_smoke/LATEST.json` (stamp `20260807T092608Z`) |
| **Runner** | `scripts/run_aios_skeleton_v1.py --plan-only` |
| **Bus / map libs** | `lib/aios_skeleton_bus.py`, `lib/aios_skeleton_map.py`, `lib/aios_skeleton_stub.py`, `lib/aios_skeleton_subagent_profiles.py` |
| **Vacant (honest)** | `uml_invoke` only — reserved for compute-core wire-in; `subagent_spawn` bound to skeleton worker bus |
| **Overnight notes** | `artifacts/auto/wake_finish/skeleton_gaps_overnight.md` |

---

## 2026-07-23 OpenAster training status

| Component | Status | Evidence |
| --- | --- | --- |
| Prompt/runtime parity | **BUILT** | `openaster_prompt_v4`, ChatML, response-only EOS supervision |
| Expanded MoE LoRA | **BUILT** | 25.98M trainable parameters; peak reserved VRAM 5.965 GB |
| v3 curriculum | **BUILT** | 720 balanced/disjoint rows; concise ingest replacement audit |
| v3 candidate | **REJECTED** | Deploy mind 0.80 but valid speech 0.7167, 4 collapses, multi-turn 0/12 |
| Layered curriculum tree v2 | **SKELETON BUILT** | Eight cumulative stages; 96 frozen balanced seed pairs; 57 calibrated / 39 HOLD; zero frozen overlap |
| Generalization data split | **BUILT** | 612 train / 108 validation; zero ask-cluster overlap |
| Preference optimization | **PREFLIGHT PASS** | Hybrid response-only SFT + reference-free pairwise margin completed one optimizer step at 5.121 GiB peak; no production stage activated |
| Closed-net training security | **BUILT + ACTIVE** | Verified Viv-local Rust `security_core` 0.2.9; 15/15 Rust tests, 11 negative training contracts, hash-chained ledgers |
| AIOS backup core | **BUILT + ACTIVE** | 959-file verified bootstrap, 38 immutable model hashes, staged restore drill, training mutation hooks; off-disk replication unconfigured |
| AIOS Triad membrane | **BUILT + ACTIVE** | `viv_triad_contract_v1`; Security IN → RID/AUTO/UML → Security OUT; package coverage and boundary-registry drift are preflight gates |
| Engineering Governor | **BUILT + ACTIVE** | Discover → backup → authorize → verify → reconcile → journal; protected-source self-modification remains blocked |
| Stage 1 truth corpus | **BUILT; CPU JUDGE WAITING; NOT FROZEN** | Secured construction wrote 360 unique pairs, 240/48/48/24 splits, 60/domain, three aligned drafts plus three hard negatives per row, and zero frozen overlap; resumable judging is waiting at the unchanged Master S_n 0.3700 floor |
| Stage 1 candidate | **NOT RUN** | Bounded 80-step BF16 response-only/pairwise trainer is implemented; training, evaluation, candidate validation, and deployment did not run |
| Live mouth | **QWEN** | OpenAster `validated_candidate=null`; no runtime switch |

### 2026-07-23 Triad membrane integration

- RID, AUTO, and UML expose versioned pillar contracts through the
  dependency-light `lib/triad_kernel.py` facade.
- Architect inbox, CARMA mutation, agentic mutation, training records, and
  voice generation/egress now open authenticated Triad contexts.
- Static architecture coverage is 100% across governed Python packages.
  Existing raw boundary sites are frozen in `triad_boundary_registry.json`;
  new or changed sites fail unified preflight.
- The known `SensorReading.runtime_rsr` integration defect was repaired:
  training security now supplies `compute_master_rid` a real `TriadSample`.
- No training, candidate validation, canary, deployment, or live-mouth switch
  occurred. Evidence: `artifacts/auto/triad/milestone_report_v1.json`.

CPU-resident judging is allowed concurrently with the single GPU mouth. GPU
exclusivity applies between Qwen/OpenAster mouth processes.

### Closed-net Stage 1 implementation evidence

- Installed Viv-local security is verified as `security_core==0.2.9` through `foundation/lib/security_bridge.py`; the bridge selects `security_core/runtime/security_core.pyd` and checks its SHA-256 sidecar before loading.
- Rust contracts: 15/15 pass, including DPAPI current-user binding, lease
  replay denial, action/role/artifact capability matching, root/path/extension
  containment, immutable registry freeze, hardlink/reparse denial, and
  malformed/non-finite safetensors rejection.
- Unified preflight: 250 Python files parse; 14 Python contract suites and the
  Rust security suite pass. It also rejects duplicate definitions, duplicate
  literal dictionary keys, mutable defaults, malformed/duplicate-key critical
  JSON, test timeouts, and launch failures.
- Secured Stage 1 construction wrote 360 balanced rows with zero frozen
  overlap. The resumable CPU judge is waiting because Master S_n 0.3620 is
  below the unchanged 0.3700 Law 5 floor; no row is admitted or frozen.
- No general writable-root exception was added. Training artifacts use typed
  authorization or a Rust lease; the eight detected direct writes are all
  explicitly inside lease staging.
- Live Qwen, historical deploy pointers, frozen packs, and model configuration
  are unchanged.

---

## Section-by-Section

### §1 Core Philosophy — PARTIAL

| | |
| --- | --- |
| **Vision** | SGI, shield-not-sword, CPU mind / GPU voice |
| **Viv** | Doctrine in `VIV_COMPLETE_SUMMARY.md`, `AIOS_ALPHA_BRIEFING.md`, `model_config.json` |
| **Gap** | No single runtime module enforces “shield not sword”; philosophy is architectural intent |

---

### §2 RID Physics Engine — **BUILT**

| | |
| --- | --- |
| **Vision** | S_n, RSR/LTP/RLE, dormancy at 0.45, self-referential gate |
| **Viv** | `rid_main.py`, `lib/master_rid.py`, `lib/rid_triad.py`, `lib/rid_feed.py` |
| **Artifacts** | `artifacts/auto/master_rid.json`, 120s captures (`stability_pc_120s_v5`, `core_spread_master_120s_v1`) |
| **Verify** | `rid_main.py status`, `auto_main.py master`, `RID.md` |
| **Note** | Plant RID (thermal/load) is proven on this machine. Semantic/identity RSR from the full vision doc is not the same channel yet — that is future UML/Guardian integration. |

---

### §3 Hardware Architecture — PARTIAL

| Subsystem | Status | Evidence |
| --------- | ------ | -------- |
| CPU = Viv mind | **BUILT** | `auto_main.py autonomous`, `lib/autonomous_operator.py` |
| GPU = voice | **Phase 1b** | `voice_core/` + HF LoRA speak + gated autonomous speak — `VOICE.md` |
| Piston thermal scheduler | **BUILT** | `lib/piston_engine.py`, `lib/piston_background.py`, `rid_main.py piston` |
| 1 Hz heartbeat | **BUILT** | `lib/auto_rid_journal.py`, `artifacts/auto/pulse.json`, `artifacts/auto/beat.json` |
| Hardware-agnostic scaling | PARTIAL | `piston_engine.detect_hardware()`, `make_pairs()` |
| Mycelial hive mind | **NONE** | No multi-node S_n distribution in Viv |

---

### §4 Three Tuning Knobs — PARTIAL

| Knob | Status | Evidence |
| ---- | ------ | -------- |
| master_S_n_threshold | **BUILT** | `cpu_config.json` (`dormancy_threshold` 0.45), `lib/master_rid.py` |
| Tariff dictionary | **BUILT** | `artifacts/auto/guardian_tariff.json`, `lib/guardian_v2.py` |
| Tariff thesaurus | **NONE** | Synonym expansion not implemented in Viv Guardian |
| Hardware + environment | PARTIAL | Corsair/iCUE telemetry, piston params; no room-temp knob |

---

### §5 Software Architecture — PARTIAL

| Language / surface | Status | Evidence |
| ------------------ | ------ | -------- |
| Python three mains | **BUILT** | `rid_main.py`, `auto_main.py`, `uml_main.py` |
| Python lib spine | **BUILT** | `foundation/lib/*` (50+ modules) |
| UML calculator | **BUILT** | `uml_main.py`, `lib/uml_engine.py` |
| Identity→UML bridge (Aug 7) | **CANARY_PASS (default OFF)** | Shadow `FIELD_SCOPED_WINS`; canary `CANARY_PASS` with `--enable-canary` only; ingress `uml_request`; evidence `Training/evidence/snapshots/20260807T085000Z` + `artifacts/auto/field_scoped_bridge_canary/20260807T092040Z` — see `COLD_START.md` Part 3.2 / Part 5 |
| UML full spec (verify/trace/b52/corpus) | PARTIAL | Engine exists; CLI surface incomplete per roadmap |
| Rust `security_core` (Viv) | **BUILT** v0.2.2 | `L:\Continue\Viv\security_core\` — gate, 8 Laws, tariff, PyO3; red-team 64/64 |
| Viv agentic queue | **BUILT** | `lib/agentic_runtime.py`, `agentic_main.py` — Rust `tool_gate` on all writes |
| Rust moral governor (Luna legacy) | LEGACY | `nox_forge_core/src/governor.rs` — port into Viv security_core |
| Mod-folder language isolation | **NONE** | Policy only |

---

### §6 Memory System (CARMA) — **BUILT** (Phase 1)

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Plain-text .txt / .jsonl / .json stack | **BUILT** | `memory_core/`, `artifacts/carma/` |
| SemanticMemory API + `memory_main.py` | **BUILT** | Rust-gated via `tool_gate`; Law 2 path deny |
| Master tag file | **BUILT** | `artifacts/carma/master_tags.json` |
| Provenance tags [live]/[dream]/[simulation] | **BUILT** | Line prefix + folder layout |
| 1 MB split mechanism | **BUILT** | `memory_core/split.py` |
| Autonomous live-note append | **BUILT** | `lib/autonomous_operator.py` + flight-recorder Law 5 (0.2.3) |
| Bounded CPU retrieve (no vectors/embeddings) | **BUILT, provisional ranking** | `memory_core/retrieve.py`; keyword admission plus deterministic CPU cosine re-ranking with explicit provisional metadata |
| Heartbeat log (append-only) | **BUILT** | `artifacts/carma/heartbeat.jsonl` + auto journal |
| Dream cycle | **BUILT** | `lib/aios_dream.py` — REM consolidate live→dream, archive raw, CARMA `[dream]` |
| Wikipedia absorb | LEGACY | Steel_Brain batches — Phase 2 |
| Legacy vector CARMA | LEGACY | Luna `carma_core/carma.py` — not ported |

---

### §7 Stateless Voice (GPU) — **PARTIAL** (Qwen live; OpenAster parity candidate rejected)

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Hemispheres doctrine | **BUILT** | CPU judge/mind is authoritative; Qwen is temporary live mouth/teacher; OpenAster HF+LoRA remains the sovereign trainable target |
| `voice_core` intent packet (CPU → GPU) | **BUILT** | `Viv/voice_core/intent_packet.py` — canonical `openaster_prompt_v4` shared by HF training and runtime |
| Soft-fail client (silent OK offline) | **BUILT** | `voice_core/client.py`, `speak.py` — `{ok:true, silent:true}` when no server |
| Security OUT on spoken text | **BUILT** | `filter_egress` + `artifacts/auto/voice_events.jsonl` |
| Stub server (offline pipeline proof) | **BUILT** | `voice_core/stub_server.py` — no GPU / no weights |
| Operator CLI | **BUILT** | `voice_core/voice_main.py` (`status` \| `speak` \| `stub` \| `packet`) |
| Foundation bridge + `model_main speak` | **BUILT** | `lib/voice_bridge.py`, `model_main.py speak` |
| **HF + LoRA backend** | **BUILT, not live** | `voice_core/hf_lora.py`; runtime renderer uses the canonical prompt, but `model_config` keeps Qwen live |
| **LoRA SFT trainer** | **BUILT** | BF16 response-only trainer; 384-token preflight; GPU-singleton, non-finite gradient, overlap, and boundary aborts |
| **Internal RLHF (shadow judge)** | **PARTIAL** | `lib/viv_shadow_judge.py` + `INTERNAL_RLHF_SHADOW_JUDGE_CONTRACT.md`; useful×honest×understanding AND; wired into talk compose; preference pairs → `artifacts/auto/shadow_judge/` |
| **Layered contrastive training tree** | **SKELETON BUILT** | Eight cumulative stages, 96 balanced calibration pairs, frozen seed registry, deterministic admission, CPU-only double semantic observation, and hybrid response-only/pairwise preflight under `artifacts/auto/openaster_training_tree/`; no stage activated or deployed |
| Qwen GGUF path | **LIVE TEMPORARY** | `viv-voice-qwen` is the live baseline; isolated `viv-qwen-teacher` has the correct ChatML template for bounded curriculum collection |
| **Autonomous gated speak** | **HALTED** | Wired earlier for smoke; `voice_speak=false` until PRT cycle exists (fluency ≠ PRT) |
| Operator guide | **BUILT** | `foundation/VOICE.md` (**PRT vs fluency** section mandatory read) |
| vLLM / AWQ launcher | PARTIAL | `model_main.py voice-serve` — AWQ path not on disk |
| OpenAster parity corpus | **BUILT** | `artifacts/models/viv_judge_sft_v2.jsonl`: 720 disjoint rows, 120/category, all examples fit sequence cap 384 |
| OpenAster parity candidate | **REJECTED** | Candidate B deploy: mind 0.2667, valid speech 0.2167, 13 collapses, multi-turn 0/12; `validated_candidate=null` |
| Phase 1 smoke | **PASS** | `artifacts/audit/voice_smoke_phase1.{md,json}` |
| Left-brain embed retrieve | PARTIAL | `viv-embed` is present but Ollama exposes completion only; bounded embedding adapter fails closed and claim alignment remains `INCONCLUSIVE` |
| PRT / SPRT trainer | **PARTIAL** (collect+train applied) | `prt_main.py apply/train`; physics JSONL; continue LoRA; speak scored; auto-speak still halted |
| Emotional GGUF models | **NONE** (out of scope) | |
| Multilingual voice | **NONE** | |

Decision evidence: `artifacts/auto/openaster_parity/candidate_decision_v1.json`.
Training-tree skeleton evidence:
`artifacts/auto/openaster_training_tree/milestone_report_v2.json`. No runtime
adapter, deploy pointer, or canary was changed during either milestone.

---

### §8 Constitutional Framework — PARTIAL

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Guardian gate (UML + tariff + S_n interlock) | **BUILT** | `guardian_main.py`, `lib/guardian_v2.py` |
| 3 Prime Directives + 8 Immutable Laws | **BUILT** | Viv `security_core` v0.2.2 + membrane on Guardian + agentic ticks |
| Rust moral governor | **BUILT** (Viv) | `L:\Continue\Viv\security_core\` — Luna legacy remains as reference |
| Full fail-closed constitution on hot path | **BUILT** | `lib/security_membrane.py` — Integrity sidecar fail-closed |
| Tariff thesaurus | **NONE** | |

---

### §9 Vision System — LEGACY

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Stereoscopic mouse-tied capture | LEGACY | `FSAA/Luna/AIOS_V2/vision_core/stereoscopic_vision.py` (150×150, not 100×100) |
| GIF → text → memory | LEGACY | `consciousness_core/aria_memory.py`, `vision_core/effector.py` |
| In Viv foundation | **NONE** | Not absorbed |

---

### §10 Hearing System — **NONE**

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Real-time audio capture | **NONE** | No wav/mp3 pipeline under `L:\Continue\Viv\` |
| Audio → text → CARMA | **NONE** | |

---

### §11 Security & Identity — PARTIAL

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Three-key quorum gate | PARTIAL | `L:\Continue\automation\aios_quorum_gate.py`, `lib/auto_gate.py` |
| S_identity biometrics formula | **NONE** | Not implemented in code |
| Continuous face/voice/linguistic match | **NONE** | |

---

### §12 Knowledge & Open Source — LEGACY

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Wikipedia plain-text batches | LEGACY | `FSAA/Steel_Brain/Encoding/UML_Import/D/Dataset/wikipedia_deduplicated/` |
| Semantic search (~3s, no vector DB) | LEGACY/PARTIAL | `FSAA/Luna/AIOS_V2/dataset_core/read_global_index.py` |
| Wired into Viv | **PARTIAL** | `foundation/lib/knowledge_source_contract.py`, external adapters, CPU retrieval ranker, and `voice_core/knowledge_grounding.py`; read-only/provenance-preserving seam, not full CARMA absorption |
| 80 GB dump on this machine | UNVERIFIED | Batches exist; full size not audited here |

---

### §13 Sovereignty & Transparency — PARTIAL

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Append-only RID/journal logs | **BUILT** | `auto_rid_journal`, `events.jsonl`, RID CSVs |
| Plain-text artifacts | **BUILT** | `artifacts/rid/*.csv`, `artifacts/auto/*.json` |
| User-only delete / full flight recorder | PARTIAL | Policy in vision; CARMA delete rules not built in Viv |
| Trace every decision | PARTIAL | Guardian verdicts logged; not universal |

---

### §14 Symbiotic Ethics — **NONE**

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Lie/apology → S_n pattern learning | **NONE** | Physics gate exists; ethics-as-relationship loop not coded |
| “Loyal to physics not person” | PARTIAL | Architectural intent via RID dormancy |

---

### §15 Dream Cycle — **BUILT** (Viv plain-text)

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Self-summarize + archive raw | **BUILT** | `lib/aios_dream.py` → `artifacts/carma/dream/` + `dream/archive/` |
| In Viv plain-text CARMA | **BUILT** | `remember(..., provenance="dream")`; organism beat cadence |
| Legacy Luna dream_core | LEGACY | Not imported — Viv path owns REM now |

---

### §16 Perception (Sight / Sound / Text) — PARTIAL

| Sense | Status | Evidence |
| ----- | ------ | -------- |
| Text → UML | **BUILT** | `uml_main.py`, `guardian_v2.py` |
| Sight | LEGACY | Luna vision_core only |
| Sound | **NONE** | |
| Redundancy fallback chain | **NONE** | |

---

### §17 Hardware Agnosticism — PARTIAL

| Feature | Status | Evidence |
| ------- | ------ | -------- |
| Core/pair detection | **BUILT** | `piston_engine.detect_hardware()` |
| Adaptive heartbeat interval | PARTIAL | Configurable `--interval`; not auto-scaled to hardware class |
| 50/50 burden split policy | **NONE** | Doctrine only |
| Knowledge downsizing when hardware small | **NONE** | |

---

### §18 Final Goal — NONE (aspirational)

End-state vision. Canonical Alpha is mid-rebuild toward it. See `FOUNDATION_ROADMAP.md`.

---

## Canonical Alpha — What Is Proven Today

### 2026-07-23 hardening milestone

The integrated CPU preflight passes across 199 Python sources plus UML structure, tariff registry, semantic choice, AIFL preference contracts, and token economics. Three sequential live voice checks completed through the Qwen path or deterministic fallback with 3/3 judge-aligned drafts. Training/deployment remains validation-only while the frozen holdout and deploy baseline remain authoritative.

These are the items a new AI can verify without rerunning 120s captures:

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"

# Viv spine
& $PY L:\Continue\Viv\foundation\auto_main.py autonomous --interval 1   # 1 Hz loop (Ctrl+C to stop)

# RID / Master S_n
& $PY L:\Continue\Viv\foundation\rid_main.py status
& $PY L:\Continue\Viv\foundation\auto_main.py master

# Piston
& $PY L:\Continue\Viv\foundation\rid_main.py piston status

# Guardian
& $PY L:\Continue\Viv\foundation\guardian_main.py eval "hello" --json

# UML
& $PY L:\Continue\Viv\foundation\uml_main.py eval "2+2"

# CARMA (plain-text memory)
& $PY L:\Continue\Viv\memory_core\memory_main.py status
& $PY L:\Continue\Viv\foundation\scripts\memory_smoke_30s.py
```

---

## What To Build Next (Viv-first)

**Gate:** three mains solid → then one layer at a time.

| Phase | Target | Status |
| ----- | ------ | ------ |
| 0 | `auto_main.py` solid | **Done** |
| 1 | `rid_main.py` solid | **Done** |
| 2 | `uml_main.py` solid | **Done** |
| 3 | Security system — `L:\Continue\Viv\security_core\` (Rust IN/OUT gate) | **0.2.9 Viv-local active** — CLI and foundation bridge use the verified local runtime; training + backup membranes pass 15 Rust tests; shared `.venv` 0.2.5 retained untouched |
| 4 | Memory / Knowledge (CARMA, tags, Wikipedia) | **Phase 1 DONE; read-only knowledge seam PARTIAL** — local/runtime/Wikipedia packets and grounding gate wired; corpus inventory, CARMA promotion, and semantic embedding remain Phase 2 |
| 5 | GPU / Voice (persona render, emotion selection, inference) | Not started |
| 6 | Training (`.gguf` persona files, PRT/SPRT, corpus) | Not started |
| 7+ | Rest of AIOS (vision, hearing, hive, services) | Not started |

**Intent packet flow:** External → Security IN → three mains → … → Security OUT → External.

**Security doctrine:** first and last line of defense. 120-in/120-out integrity. No bypass around foundation.

| Layer (after mains solid) | Source | Absorb into |
| ------------------------- | ------ | ----------- |
| CARMA plain-text memory | Luna `carma_core` | `lib/` + `uml_main` / `auto_main` as appropriate |
| Constitution (8 Laws + Rust governor) | Luna `security_core`, `nox_forge_core` | `lib/` + `guardian_main` / gates |
| GPU voice PRT/SPRT | `model_main`, FSAA UML docs | `model_main` → absorbed into pillar when GPU phase starts |
| Vision / hearing | Luna `vision_core`, new audio pipeline | `lib/` — later phase |
| Wikipedia / knowledge | Steel_Brain batches | `lib/` — later phase |
| Hive mind, S_identity, symbiotic ethics | None / vision | Last — none blocking CPU spine |

---

## Related Docs

| Doc | Role |
| ------ | ---- |
| `../COLD_START.md` | Living operator manual (v1-manual shape; Phases 0–8 + core automation cookbook) |
| `VIV_COMPLETE_SUMMARY.md` | Full vision (what Viv is) |
| `VIV_BUILD_STATUS.md` | This file (what exists) |
| `AIOS_ALPHA_BRIEFING.md` | Verification commands + proven artifacts |
| `FOUNDATION_ROADMAP.md` | Three-mains build order |
| `BACKUP_CORE.md` | AIOS snapshot, restore, security, and recovery contract |
| `scripts/run_aios_core_automation_v1.py` | Integrated core automation (preflight + training + backup); see `COLD_START.md` Part 5 |
