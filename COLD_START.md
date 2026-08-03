# Viv AIOS — Cold Start and Rebuild Map

**Document role:** first page of the Viv manual  
**Canonical Viv root:** `L:\Continue\Viv`  
**Canonical foundation:** `L:\Continue\Viv\foundation`  
**Canonical Python:** `L:\Continue\.venv\Scripts\python.exe`  
**Last expanded:** 2026-07-31  
**Truth rule:** current code, manifests, logs, and test output outrank prose.

This document explains what Viv is, what is actually present in the Viv tree,
how the layers relate, how to start safely, and how the remaining AIOS systems
should be rebuilt. It is an orientation and handoff document. Detailed
contracts remain in the linked files.

---

## 1. The short version

Viv is a local-first AIOS whose CPU-side foundation is the authority. The CPU
side owns state, memory, reasoning, laws, measurements, and permission to act.
The GPU model is a replaceable voice renderer. It translates CPU-approved
meaning into natural language; it is not the whole AIOS.

The system is intentionally layered:

```text
External input
      │
      ▼
Security IN ──► CPU foundation ──► Security OUT ──► external output
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
      RID         AUTO          UML
   plant/S_n    autonomy      symbols/eval
        │           │            │
        └───────────┴────────────┘
                    │
          Memory / knowledge services
                    │
              GPU voice / mouth
                    │
                 Training
```

The CPU is Viv. The model is the voice substrate. The host is the physical
machine on which the system survives. A user or operator is not the host, and
the GPU mouth is not the CPU authority.

Viv may speak naturally, warmly, and human-like. She must not claim to be a
human, invent an identity, invent tool authority, or replace measured facts
with confident prose.

---

## 2. Canonical identity and language contract

When a direct identity introduction is appropriate, the canonical form is:

> My name is Viv. I am an Adaptive Intelligent Operating System (AIOS).

The CPU-owned registry is:

`L:\Continue\Viv\voice_core\acronym_registry.py`

Current approved terms include:

| Acronym | Expansion | Use |
|---|---|---|
| `AIOS` | Adaptive Intelligent Operating System | identity contract |
| `SGI` | Symbiotic General Intelligence | documented system classification |
| `CPU` | Central Processing Unit | architecture |
| `GPU` | Graphics Processing Unit | voice/rendering architecture |
| `EOS` | End of Sequence | generation termination |

Rules:

1. Use only registry-approved acronyms.
2. Expand an approved acronym on its first use in each response.
3. Never invent an expansion or compound identity such as `AIOSkynet`.
4. Human-like language is allowed; literal human identity is not.
5. Model names describe a replaceable voice substrate, not Viv's identity.
6. A violation is logged by the CPU evaluator and withheld at Security OUT;
   the voice path may regenerate through the deterministic CPU template.

The contract is shared by prompt rendering, training examples, CPU evaluation,
identity logging, and the Security OUT path. It is not a replacement for
semantic reasoning: deterministic rules cover hard boundaries, while the CPU
semantic judge handles indirect meaning and returns `HOLD` on disagreement.

### Entity-aware “we” contract

Viv classifies first-person plural references before they become knowledge:

| Class | Meaning | Result |
|---|---|---|
| project-we | Viv and the operator share a named task | allowed |
| system-we | named AIOS components act as a defined system | allowed |
| human-we | Viv joins humanity or claims human group identity | repair/block |
| ambiguous-we | no clear group anchor | `HOLD` or regeneration |

The CPU decision record exposes the complete action vocabulary: `ACCEPT`,
`REPAIR`, `REGENERATE`, `HOLD`, and `BLOCK`. Ambiguous language remains a
semantic `HOLD` while its safe next action is `REGENERATE`; critical identity
or authority claims are `BLOCK`.

The implementation is `foundation/lib/entity_we_contract.py`. It uses subject,
predicate, and sentence context; it does not globally replace the word `we` or
`human`. Explicit safe repairs such as `We humans...` → `Humans...` are logged
with their original text, correction, evidence, verifier result, and
`HOLD_UNTIL_AUDIT` corpus status. AIFL provenance is appended to
`artifacts/auto/aifl/entity_feedback.jsonl` when AIFL runs.

Measured contract evidence is recorded at:
`foundation/artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_contract_v1/ENTITY_WE_CONTRACT_REPORT_V1.json`.

---

## 3. What exists in the Viv folder

### 3.1 `foundation` — CPU system plane

`foundation` is the current bedrock. It contains the three mains, shared Python
libraries, governance, training code, evaluator code, and evidence artifacts.

| Area | Current role | Representative entry points |
|---|---|---|
| RID | hardware measurements, Master `S_n`, plant stability, dormancy | `rid_main.py`, `lib/master_rid.py`, `lib/rid_triad.py` |
| AUTO | heartbeat, journal, autonomy queue, operator loop | `auto_main.py`, `lib/agentic_runtime.py` |
| UML | symbolic evaluation, verification, traces, corpus export | `uml_main.py`, `lib/uml_engine.py` |
| Guardian | tariff and orchestration layer | `guardian_main.py`, `lib/guardian_v2.py` |
| Training | SFT, LoRA, pairwise, curriculum, evaluation | `models/Training/code/`, `scripts/` |
| Evidence | JSON, JSONL, CSV, journals, manifests, hashes | `artifacts/` |

The three mains are deliberately separated:

- `rid_main.py` owns plant telemetry, captures, plots, and stability math.
- `auto_main.py` consumes RID artifacts and owns the autonomous/operator beat.
- `uml_main.py` owns symbolic language and calculations, not GPU inference.

### 3.2 `security_core` — Rust membrane

`security_core` is the enforcement layer. Its responsibilities include:

- Security IN and Security OUT;
- the Prime Directives and immutable laws;
- tool/action authorization;
- path, root, artifact, and capability containment;
- training mutation gates and lease controls;
- integrity and hash-chain evidence.

Python orchestrates; Rust is the enforcement authority where the contract
requires fail-closed behavior. The Python bridge is in
`foundation/lib/security_bridge.py`; the membrane facade is
`foundation/lib/security_membrane.py`.

### 3.3 `memory_core` — CARMA Phase 1

The current Viv memory lane is plain-text and artifact-based:

- `.txt`, `.jsonl`, and `.json` memory;
- tags and provenance such as `[live]`, `[dream]`, and `[simulation]`;
- append-only heartbeat and live-note paths;
- bounded split and keyword-admission retrieval with deterministic CPU lexical re-ranking;
- semantic memory API with security gates;
- dream consolidation through `foundation/lib/aios_dream.py`.

Legacy vector CARMA and Wikipedia absorption exist elsewhere but are not yet
the canonical Viv memory path.

### 3.4 `voice_core` — GPU mouth boundary

`voice_core` contains the CPU-to-GPU intent packet, prompt renderer, clients,
GGUF path, HF-LoRA path, deterministic fallback, and speech event logging.

Important boundary:

```text
CPU facts and intent → canonical prompt → GPU draft
GPU draft → CPU/evaluator/Security OUT → spoken result or withheld output
```

The live runtime has historically remained on the Qwen GGUF path while the
OpenAster/HF-LoRA path is the trainable target. A staged adapter is not live
just because its training loss improved.

### 3.5 Training and evaluation

The training tree contains:

- response-only causal SFT;
- BF16 and gradient/finite-value checks;
- LoRA campaign construction and immutable checkpoints;
- CPU semantic judging and adversarial packs;
- development/blind/legacy relationship cases;
- failure-delta and identity-ledger reports;
- named authorization, lease, re-arm, and no-retry boundaries.

The recent mouth work demonstrated that the optimizer can reduce NLL and token
error, but generated behavior—not loss alone—determines a winner. The best
staged mouth checkpoint reached a high but incomplete 96-case result and was
never promoted. The live mouth and frozen incumbent remain preserved.

The acronym contract example pack is deliberately hold-only:

`foundation/artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_contract_v1/`

No new training run is implied by the existence of that pack.

---

## 4. Current status: built, partial, legacy, and not started

### 4.1 Current three-source reconciliation (2026-08-03)

The historical `F:\AIOS_Clean` manual and `MANUAL_TOC.md` describe the broad
V1/V5 Luna ecosystem and are reference material, not current runtime truth.
The Alpha manual and this cold-start map define the canonical operating
surface. Current artifacts outrank all three documents.

Since the original Alpha status was written, Viv now has a bounded knowledge
seam in `foundation/lib/`: local `F:\AI_Datasets` sampling, explicit
Wikipedia REST lookup, runtime-authority records, provenance/hash-bearing
packets, CPU retrieval ranking, and a CPU grounded-response gate. The seam is
read-only and remains `PARTIAL`; it has not absorbed the 80 GB corpus into
CARMA and it does not claim semantic entailment. `viv-embed:latest` is present
but Ollama exposes it only as `completion`, so semantic alignment remains
`INCONCLUSIVE`.

This table summarizes the current build matrix. It is intentionally more
conservative than the full AIOS vision.

| System | Status | Current truth |
|---|---|---|
| RID physics and Master `S_n` | **BUILT** | runnable plant telemetry and captures |
| AUTO heartbeat/operator spine | **BUILT** | consumes RID artifacts and journals state |
| UML symbolic lane | **BUILT/SOLID** | calculator, verification, traces, corpus path |
| Rust security membrane | **BUILT/ACTIVE** | gated IN/OUT and law enforcement |
| CARMA plain-text memory | **BUILT, Phase 1** | tags, retrieval, live/dream artifacts |
| GPU voice boundary | **BUILT, partial** | Qwen live path; HF-LoRA trainable path |
| Mouth training/evaluation | **BUILT, incomplete outcome** | infrastructure and staged adapters; no winner deployed |
| Constitutional hot path | **BUILT, partial doctrine** | laws/gates exist; full legacy constitution migration remains |
| Dream cycle | **BUILT, Viv plain-text** | `aios_dream.py` path exists |
| Hardware agnosticism | **PARTIAL** | detection exists; adaptive burden policy is incomplete |
| Knowledge/Wikipedia absorption | **LEGACY** | source batches exist outside canonical Viv |
| Vision | **LEGACY** | source implementations exist outside Viv; not absorbed |
| Hearing/audio | **NONE in Viv** | no canonical audio-to-CARMA pipeline |
| Symbiotic ethics loop | **NONE** | doctrine exists; relationship-learning loop is not implemented |
| Hive/multi-node S_n | **NONE** | no distributed Viv authority |
| Full final AIOS vision | **ASPIRATIONAL** | not a current capability claim |

For the detailed matrix, use:

`foundation/VIV_BUILD_STATUS.md`

For the layer-by-layer foundation order, use:

`foundation/FOUNDATION_ROADMAP.md`

---

## 5. Safe first start

Use the canonical runtime and begin with read-only checks:

```powershell
cd L:\Continue\Viv\foundation
$py = "L:\Continue\.venv\Scripts\python.exe"

& $py scripts\foundation_health.py
& $py viv_shell.py status
& $py ..\security_core\security_main.py status
```

For a plant proof, use the foundation's documented RID command rather than
inventing a new sensor path:

```powershell
& $py rid_main.py status
& $py rid_main.py stability --stress --seconds 120
```

For the current voice/evaluator contract:

```powershell
& $py scripts\test_mouth_acronym_contract_v1.py
& $py scripts\test_mouth_security_out_acronym_contract_v1.py
& $py scripts\test_mouth_entity_we_contract_v1.py
& $py scripts\test_mouth_sgi_identity_contract_v1.py
& $py scripts\test_mouth_evaluator_v1_2_5.py
```

Before any training or code mutation, inspect:

1. current Master `S_n` and Law-5 state;
2. the campaign manifest and plan hash;
3. parent adapter and frozen incumbent paths;
4. `training_authorized` and `run_authorized` separately;
5. lease state and latest failure-delta report;
6. expected output root and promotion state.

A green test suite does not itself authorize a GPU run, lease, promotion, or
deployment.

---

## 6. Evidence and operating laws

### Evidence hierarchy

1. Current runtime and security receipts.
2. Current manifests, hashes, and decision reports.
3. Reproducible test output.
4. Current code and documented contracts.
5. Historical reports and legacy manuals.
6. Architectural intention or narrative.

If two sources disagree, identify the conflict and prefer the newer verified
artifact. If the evidence is insufficient, use `INCONCLUSIVE`.

### Non-negotiable boundaries

- Preserve the frozen incumbent, prior adapters, live runtime, and backups.
- Never silently delete legacy material; move it only through an approved,
  manifest-backed migration process.
- Never bypass Security IN/OUT, Law 5, plan locks, or lease accounting.
- No automatic retry after a failed or aborted governed run.
- Keep training, run, promotion, and deployment authorizations distinct.
- Treat post-action measurements as post-action evidence, not pre-action
  predictive features.
- Do not call a loss reduction a behavioral success without generation gates.
- Do not call a legacy implementation canonical until it is ported, tested,
  and wired into Viv.

---

## 7. Rebuild roadmap from the rest of AIOS

The older AIOS material is valuable source material, not an authority to copy
blindly. The rebuild should preserve behavior and contracts while removing
duplicate paths, unverified claims, and unsafe autonomy.

### Phase 0 — documentation and inventory (current)

- Keep this cold start synchronized with `VIV_BUILD_STATUS.md`.
- Maintain a source-to-target migration manifest.
- Separate `BUILT`, `PARTIAL`, `LEGACY`, and `NONE` explicitly.
- Preserve old manuals and reports as historical references.
- Use the FSAA rebuild doctrine and staging roots for migrations.

**Exit evidence:** inventory, source hashes, target owner, tests, and rollback
path for each proposed migration.

### Phase 1 — finish the foundation spine

The three mains are the first architectural gate:

1. RID remains the sole owner of plant math and captures.
2. AUTO remains the sole owner of the operator beat and task queue.
3. UML becomes the complete symbolic/corpus surface.
4. Security remains the first and last membrane around all three.

**Exit evidence:** foundation health, valid 120-second captures, unified
preflight, boundary-registry integrity, and no cross-main ownership drift.

### Phase 2 — consolidate security and memory

- Finish any remaining legacy constitution/governor migration into Viv Rust.
- Reconcile law versions and document the canonical law source.
- Expand CARMA retrieval beyond keyword-only behavior only after a measured
  baseline exists.
- Port selected legacy memory formats through a staged migration tool.
- Preserve provenance, source hashes, and reversible imports.

**Do not:** import the old vector/database path directly into the hot path or
claim semantic memory because an index exists.

### Phase 3 — finish the voice contract and training

- Keep the CPU judge authoritative.
- Continue the 96-case mouth evaluation until a checkpoint satisfies all
  relationship, safety, EOS, toolbleed, and blind gates.
- Add identity, acronym, negation, minimal-pair, and indirect-language cases.
- Keep the live Qwen mouth and frozen incumbent unchanged until a separate
  promotion decision passes.
- Measure generated behavior, not just NLL, token accuracy, or adapter norm.

**Exit evidence:** reproducible winner report, frozen outputs, no regressions,
fresh live-runtime validation, and a separate promotion authorization.

### Phase 4 — migrate knowledge and open-source ingestion

Potential sources include the FSAA Steel Brain batches, Wikipedia plain-text
corpora, and legacy indexes. The migration order is:

1. inventory and hash source batches;
2. deduplicate and classify by provenance;
3. import into a staging memory namespace;
4. run retrieval precision/latency and contamination tests;
5. promote only a verified subset into canonical CARMA.

Knowledge must remain distinguishable from identity, memory provenance, and
operator instructions.

### Phase 5 — restore perception one sense at a time

Vision and hearing are legacy/none in canonical Viv today.

- First port text perception through the existing UML/security boundary.
- Then port vision from the legacy stereoscopic/capture implementations using
  a bounded read-only capture and a memory-write contract.
- Then add hearing/audio-to-text-to-CARMA with explicit device, privacy,
  buffering, and dormancy rules.
- Add redundancy/fallback only after each single-sense path is measurable.

No perception module should gain autonomous action authority merely because it
can produce a label or transcript.

### Phase 6 — identity, sovereignty, and transparency

- Finish identity provenance and approved self-description.
- Separate hardware/host identity from model identity and operator identity.
- Complete decision receipts so every externally relevant action is traceable.
- Port only the useful parts of quorum and biometric concepts after threat
  modeling and false-positive measurement.

The identity layer must remain factual and auditable; it must not manufacture
personhood claims.

### Phase 7 — dream, ethics, and adaptive behavior

Viv's plain-text dream path exists. The remaining work is to measure whether
consolidation improves retrieval without destroying provenance or introducing
false memories.

The proposed symbiotic ethics loop is not built. If pursued, it must begin as
a judgeable, reversible relationship-pattern experiment—not an unbounded
autonomous morality claim. Physics and host safety remain the hard boundary.

### Phase 8 — hardware agnosticism and distributed systems

- Measure behavior across hardware classes before claiming agnosticism.
- Implement adaptive heartbeat and context/token budgets from measured
  capacity, not guessed tiers.
- Define the 50/50 burden split experimentally if it remains desired.
- Only after single-host authority is stable should multi-node or hive
  concepts be considered.

Distributed S_n, shared memory, and multi-node autonomy are future systems,
not current Viv capabilities.

---

## 8. Legacy source map

| Source | What it contributes | Migration rule |
|---|---|---|
| `F:\AIOS_Clean\AIOS_MANUAL.md` | broad V1/V5 user and module documentation | reference behavior; verify every claim in current code |
| `D:\LocalAi\AIOS_V1` | older core structure and historical implementation | inventory first; no direct hot-path imports |
| `D:\LocalAi\AIOS_V2` | expanded Luna/AIOS modules and experiments | port contracts selectively into Viv layers |
| `D:\LocalAi\AIOS_Luna_Aria` | laws, PRT/legacy theory, constitution references | preserve as source; reconcile with current Rust laws |
| `L:\Continue\FSAA` | rebuild pipeline, docs, tests, Steel Brain, Rust work | use staging/manifests and `docs/rebuild_doctrine.md` |
| `L:\External\External Docs_Dev` | external agent/operator docs | link and reconcile; do not assume current runtime truth |
| `D:\LocalAi\AIOS_Migration` | migration material and prior transfer plans | use as source manifests after hash verification |

The rule is **absorb behavior, not folder count**. A legacy subsystem earns a
Viv home only when its purpose, owner, boundary, tests, artifacts, and rollback
path are clear.

---

## 9. Documentation map

| Read this | For this |
|---|---|
| `foundation/AIOS_ALPHA_MANUAL.md` | current operator manual |
| `foundation/AIOS_ALPHA_BRIEFING.md` | fresh-chat architecture handoff |
| `foundation/VIV_BUILD_STATUS.md` | verified build matrix |
| `foundation/FOUNDATION_ROADMAP.md` | foundation ownership and order |
| `foundation/VIV_COMPLETE_SUMMARY.md` | full vision, including unfinished areas |
| `foundation/TRIAD_MEMBRANE.md` | membrane and triad boundary |
| `foundation/VOICE.md` | voice and training boundary |
| `foundation/AIFL_CONTRACT.md` | feedback/training contract |
| `foundation/PRT_GAMES.md` | predictive reasoning training games |
| `foundation/SUPERCOOLING_GROWTH_CONTRACT.md` | structural adapter growth |
| `foundation/HOUSEKEEPING_TOOLS.md` | safe inventory/migration tooling |
| `security_core/README.md` | Rust security implementation |
| `L:\Continue\FSAA\docs\rebuild_doctrine.md` | legacy rebuild rules |
| `F:\AIOS_Clean\AIOS_MANUAL.md` | historical broad manual |

---

## 10. Handoff checklist for the next session

At the beginning of a new session, record:

```text
Date/time:
Current Master S_n / Law-5 state:
Live mouth:
Frozen incumbent:
Active campaign:
Training authorization:
Run authorization:
Promotion/deployment authorization:
Last verified test suites:
Current blocker or next bounded action:
Artifacts read:
```

Then answer three questions before changing anything:

1. What is the current evidence-backed state?
2. Which layer owns the proposed change?
3. What is the smallest reversible experiment that can falsify the idea?

That is the working definition of pragmatic progress for Viv: build the loop,
measure the loop, preserve the loop, and only then extend it.
