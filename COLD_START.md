# Viv AIOS Operator Manual (Cold Start)

**Document role:** living operator manual for Canonical Viv (successor shape to the
historical `F:\AIOS_Clean\AIOS_MANUAL.md` user manual — not a copy of its claims)  
**Canonical Viv root:** `L:\Continue\Viv`  
**Canonical foundation:** `L:\Continue\Viv\foundation`  
**Canonical Python:** `L:\Continue\.venv\Scripts\python.exe`  
**Merged AIOS runtime surface (sibling):** `L:\Continue\FSAA`  
**Last expanded:** 2026-08-07  
**Truth rule:** current code, manifests, logs, and test output outrank prose.

---

## Document purpose

This is the first page of the Viv manual: orientation, safe ops, module map,
rebuild phases, and the automation cookbook. It is meant to be kept current the
way the v1 AIOS manual was used as the operator’s single entry document — but
scoped to what Viv actually runs today.

| Audience | What this page gives you |
|---|---|
| Operator / session handoff | What Viv is, safe first commands, evidence hierarchy |
| Rebuild / automation | Phase map 0–8, integrated core orchestrator, receipts |
| Architecture | CPU foundation authority, GPU as voice substrate, security membrane |
| Migration | Legacy source map (`F:\AIOS_Clean`, FSAA, LocalAi trees) — absorb behavior, not folder count |

Detailed contracts remain in linked foundation docs. Historical V1/V5 Luna
material on `F:\AIOS_Clean` is reference only.

---

## Quick navigation

| Go to | For |
|---|---|
| [Part 1 — Getting started](#part-1-getting-started) | Short version, identity contract, computer-not-brain |
| [Part 2 — Architecture and modules](#part-2-architecture-and-modules) | Layer diagram, foundation / security / memory / voice |
| [Part 3 — Status and evidence](#part-3-status-and-evidence) | Build matrix, Aug 7 bridge canary, laws |
| [Part 4 — Safe start and validation](#part-4-safe-start-and-validation) | Health, RID, mouth contracts |
| [Part 5 — Deployment and operations cookbook](#part-5-deployment-and-operations-cookbook) | **Core orchestrator**, **subagent bus**, skeleton smoke, backup |
| [Part 6 — Rebuild roadmap (Phases 0–8)](#part-6-rebuild-roadmap-phases-0-8) | Migration order from the rest of AIOS |
| [Part 7 — Legacy sources, docs map, handoff](#part-7-legacy-sources-docs-map-handoff) | Where old manuals live; session checklist |

Companion status matrix: `foundation/VIV_BUILD_STATUS.md`  
Historical v1 manual: `F:\AIOS_Clean\AIOS_MANUAL.md` (+ `MANUAL_TOC.md`)

---

# Part 1 — Getting started

## 1.1 The short version

Viv is a local-first Adaptive Intelligent Operating System (AIOS) whose CPU-side
foundation is the authority. The CPU owns state, memory, reasoning, laws,
measurements, and permission to act. The GPU model is a replaceable voice
renderer. It translates CPU-approved meaning into natural language; it is not
the whole AIOS.

**Viv/AIOS is a COMPUTER**, not a language-generator brain and not a human
analogue. It computes with indexed math (UML), deterministic structure (Nested
PEMDAS), and control (PID internal / RID outer stability). Words are a
deterministic render surface of computation — not the primary mode of thought.

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

## 1.2 Canonical identity and language contract

When a direct identity introduction is appropriate, the canonical form is:

> My name is Viv. I am an Adaptive Intelligent Operating System (AIOS).

The CPU-owned registry is:

`L:\Continue\Viv\voice_core\acronym_registry.py`

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
identity logging, and the Security OUT path. Deterministic rules cover hard
boundaries; the CPU semantic judge handles indirect meaning and returns `HOLD`
on disagreement.

### Entity-aware “we” contract

| Class | Meaning | Result |
|---|---|---|
| project-we | Viv and the operator share a named task | allowed |
| system-we | named AIOS components act as a defined system | allowed |
| human-we | Viv joins humanity or claims human group identity | repair/block |
| ambiguous-we | no clear group anchor | `HOLD` or regeneration |

The CPU decision record exposes: `ACCEPT`, `REPAIR`, `REGENERATE`, `HOLD`, and
`BLOCK`. Ambiguous language remains a semantic `HOLD` while its safe next
action is `REGENERATE`; critical identity or authority claims are `BLOCK`.

Implementation: `foundation/lib/entity_we_contract.py`. Explicit safe repairs
such as `We humans...` → `Humans...` are logged with original text, correction,
evidence, verifier result, and `HOLD_UNTIL_AUDIT` corpus status. AIFL
provenance appends to `artifacts/auto/aifl/entity_feedback.jsonl` when AIFL runs.

Measured contract evidence:
`foundation/artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_entity_we_contract_v1/ENTITY_WE_CONTRACT_REPORT_V1.json`.

## 1.3 Foundation doctrine (non-negotiables)

`L:\Continue\Viv\foundation\` is bedrock. If foundation telemetry, math, or
runtime lies, layers above are built on a sinkhole.

1. **Evidence over narrative** — plant captures need validated artifacts
   (summary JSON, poll sidecar, verdict). Never treat a single CSV row as a
   120s stability proof.
2. **Phone RID math, PC plants** — LTP/RSR/RLE/`S_n` from `L:\Phone\` arithmetic
   on live sensors. RID is stability (nestable 3→1 fold of continuous [0,1]
   channels), not an accuracy engine or PID replacement fiction.
3. **Full runs for foundation proof** — 120s stressed captures default; smoke
   tests do not promote to foundation evidence.
4. **Stress must be proven** — CPU load near 100%, stress workers alive, poll
   sidecar confirms. Flat iCUE temps with proven load = `PASS_FLAT`, not failure.
5. **One Python runtime** — `L:\Continue\.venv` only. No C: Python for AIOS.
6. **Piston sits on plant** — stability captures feed `artifacts/auto/plant/`
   before piston/governor layers consume them.

Health check:

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\scripts\foundation_health.py
```

---

# Part 2 — Architecture and modules

## 2.1 `foundation` — CPU system plane

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
| Core automation | integrated preflight + training + backup orchestrator | `lib/aios_core_automation.py`, `scripts/run_aios_core_automation_v1.py` |
| Subagent worker bus | skeleton local jobs + fanout + receipts (not IDE fanout) | `lib/aios_subagent_v1.py`, `scripts/run_aios_subagent_v1.py` |
| Skeleton spine | structural map + bus for later compute-core wire-in | `lib/aios_skeleton_bus.py`, `scripts/run_aios_skeleton_v1.py` |

### 2.1.1 Skeleton mode (scaffold-first)

Entire AIOS is **scaffold-first**: importable adapters / catalog rows / plan-only
hooks first; flesh later. The compute core (operator may say “brain” —
UML Nested-PEMDAS + RID/PID plant + mouth/security surfaces) plugs into
`foundation/lib/aios_skeleton_bus.py` slots:

`security_in`, `security_out`, `uml_invoke`, `rid_sample`, `mouth_render`,
`memory_plan`, `dream_plan`, `subagent_spawn`, `plant_health`.

Vacant slots are honest emptiness for wire-in (today: `uml_invoke`,
`subagent_spawn`). One-command map:

```powershell
L:\Continue\.venv\Scripts\python.exe foundation\scripts\run_aios_skeleton_v1.py --plan-only
```

Receipts: `foundation/artifacts/auto/aios_skeleton/` (`LATEST.json`).
Do not treat `SKELETON` / `PARTIAL` map rows as `BUILT`.

The three mains are deliberately separated:

- `rid_main.py` owns plant telemetry, captures, plots, and stability math.
- `auto_main.py` consumes RID artifacts and owns the autonomous/operator beat.
- `uml_main.py` owns symbolic language and calculations, not GPU inference.

## 2.2 `security_core` — Rust membrane

Responsibilities include Security IN/OUT, Prime Directives and immutable laws,
tool/action authorization, path/root/artifact/capability containment, training
mutation gates and leases, integrity and hash-chain evidence.

Python orchestrates; Rust is the enforcement authority where the contract
requires fail-closed behavior. Bridge: `foundation/lib/security_bridge.py`.
Membrane facade: `foundation/lib/security_membrane.py`.

## 2.3 `memory_core` — CARMA Phase 1

Current Viv memory lane is plain-text and artifact-based:

- `.txt`, `.jsonl`, and `.json` memory;
- tags and provenance such as `[live]`, `[dream]`, and `[simulation]`;
- append-only heartbeat and live-note paths;
- bounded split and keyword-admission retrieval with deterministic CPU lexical re-ranking;
- semantic memory API with security gates;
- dream consolidation through `foundation/lib/aios_dream.py`.

Legacy vector CARMA and Wikipedia absorption exist elsewhere but are not yet
the canonical Viv memory path.

## 2.4 `voice_core` — GPU mouth boundary

Contains the CPU-to-GPU intent packet, prompt renderer, clients, GGUF path,
HF-LoRA path, deterministic fallback, and speech event logging.

```text
CPU facts and intent → canonical prompt → GPU draft
GPU draft → CPU/evaluator/Security OUT → spoken result or withheld output
```

The live runtime has historically remained on the Qwen GGUF path while the
OpenAster/HF-LoRA path is the trainable target. A staged adapter is not live
just because its training loss improved.

## 2.5 Training and evaluation

The training tree contains response-only causal SFT; BF16 and gradient checks;
LoRA campaigns and immutable checkpoints; CPU semantic judging and adversarial
packs; development/blind/legacy relationship cases; failure-delta and identity
ledger reports; named authorization, lease, re-arm, and no-retry boundaries.

Optimizer NLL/token error reduction is not a behavioral win by itself. The best
staged mouth checkpoint reached a high but incomplete 96-case result and was
never promoted. The live mouth and frozen incumbent remain preserved.

Acronym contract pack (hold-only):
`foundation/artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_contract_v1/`

No new training run is implied by the existence of that pack.

---

# Part 3 — Status and evidence

## 3.1 Three-source reconciliation (2026-08-03)

The historical `F:\AIOS_Clean` manual and `MANUAL_TOC.md` describe the broad
V1/V5 Luna ecosystem and are **reference material, not current runtime truth**.
This cold-start manual and the Alpha docs define the canonical operating
surface. Current artifacts outrank all three documents.

Since the original Alpha status was written, Viv has a bounded knowledge seam
in `foundation/lib/`: local `F:\AI_Datasets` sampling, explicit Wikipedia REST
lookup, runtime-authority records, provenance/hash-bearing packets, CPU
retrieval ranking, and a CPU grounded-response gate. The seam is read-only and
remains `PARTIAL`; it has not absorbed the 80 GB corpus into CARMA and does not
claim semantic entailment. `viv-embed:latest` is present but Ollama exposes it
only as `completion`, so semantic alignment remains `INCONCLUSIVE`.

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
| AIOS core automation orchestrator | **BUILT** | plan-only + execute-safe bundles; phases 0–8 tagged |
| AIOS subagent worker bus | **BUILT (skeleton)** | profiles + fanout + receipts; compute-core hook RESERVED |
| Hardware agnosticism | **PARTIAL** | detection exists; adaptive burden policy incomplete |
| Knowledge/Wikipedia absorption | **LEGACY / PARTIAL seam** | bounded seam in Viv; full corpus not absorbed |
| Vision | **LEGACY** | outside Viv; not absorbed |
| Hearing/audio | **NONE in Viv** | no canonical audio-to-CARMA pipeline |
| Symbiotic ethics loop | **NONE** | doctrine exists; loop not implemented |
| Hive/multi-node S_n | **NONE** | no distributed Viv authority |
| Full final AIOS vision | **ASPIRATIONAL** | not a current capability claim |

Detailed matrix: `foundation/VIV_BUILD_STATUS.md`  
Layer order: `foundation/FOUNDATION_ROADMAP.md`

## 3.2 Aug 7 — identity→UML bridge (current truth)

| Stage | Verdict | Default runtime posture |
|---|---|---|
| Shadow pilot (`IDENTITY_UML_BRIDGE_SHADOW_V1`) | `FIELD_SCOPED_WINS` | `SCAN_SURFACE` is not authority |
| Bounded canary (`FIELD_SCOPED_BRIDGE_CANARY_V1`) | **`CANARY_PASS`** | **default OFF** — operator gate `--enable-canary` required |

Facts:

- Ingress is explicit `uml_request` on CPU intent packets (not prose scan).
- Path: `build_intent_packet.uml_request` → Security/gate → UML `decide_route` → attach `uml_resolved`.
- Lib: `foundation/lib/uml_field_scoped_bridge.py` (`BRIDGE_MODE = FIELD_SCOPED_CANARY`).
- Runner: `foundation/scripts/run_field_scoped_bridge_canary_v1.py`.
- **No default promotion**, no tag architecture, no soft-0.99, no `SCAN_SURFACE` authority.
- Tag architecture remains deferred (`TIE_WITH_CONSTRAINTS`).
- Evidence snapshot: `foundation/models/Training/evidence/snapshots/20260807T085000Z`
- Thesis: `UML_TRAINING_THESIS.md` items 78–79.
- Canary receipt:
  `foundation/artifacts/auto/field_scoped_bridge_canary/20260807T092040Z/`

## 3.3 Evidence hierarchy

1. Current runtime and security receipts.
2. Current manifests, hashes, and decision reports.
3. Reproducible test output.
4. Current code and documented contracts.
5. Historical reports and legacy manuals.
6. Architectural intention or narrative.

If two sources disagree, identify the conflict and prefer the newer verified
artifact. If evidence is insufficient, use `INCONCLUSIVE`.

## 3.4 Non-negotiable operating laws

- Preserve the frozen incumbent, prior adapters, live runtime, and backups.
- Never silently delete legacy material; move only through approved,
  manifest-backed migration.
- Never bypass Security IN/OUT, Law 5, plan locks, or lease accounting.
- No automatic retry after a failed or aborted governed run.
- Keep training, run, promotion, and deployment authorizations distinct.
- Treat post-action measurements as post-action evidence, not pre-action
  predictive features.
- Do not call a loss reduction a behavioral success without generation gates.
- Do not call a legacy implementation canonical until it is ported, tested,
  and wired into Viv.
- Do not start AIOS runtime, launch `GPU_LONG`, promote bridges, or copy
  weight packs from automation unless the operator explicitly authorizes that
  surface.

---

# Part 4 — Safe start and validation

Use the canonical runtime and begin with read-only checks:

```powershell
cd L:\Continue\Viv\foundation
$py = "L:\Continue\.venv\Scripts\python.exe"

& $py scripts\foundation_health.py
& $py viv_shell.py status
& $py ..\security_core\security_main.py status
```

Plant proof (documented RID path; full 120s stressed capture when proving):

```powershell
& $py rid_main.py status
& $py rid_main.py stability --stress --seconds 120
```

Voice / evaluator contracts:

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

# Part 5 — Deployment and operations cookbook

This part mirrors the v1 manual’s “operations / daily workflows” role: concrete
commands, receipts, and what is *not* started. Prefer these surfaces over ad-hoc
scripts when checking the integrated AIOS core.

## 5.1 AIOS core automation orchestrator (primary cookbook)

**Purpose:** one local, plan-first surface that bundles systems preflight,
training automation (catalog / `uml_status`), and backup (`uml_lane`) without
duplicating those runners. Profiles and bundles are tagged to
[COLD_START Phases 0–8](#part-6-rebuild-roadmap-phases-0-8) — this is **not** a
parallel roadmap.

| Piece | Path |
|---|---|
| Runner | `foundation/scripts/run_aios_core_automation_v1.py` |
| Library / registry | `foundation/lib/aios_core_automation.py` |
| Receipts root | `foundation/artifacts/auto/aios_core_automation/` |
| Latest pointer | `foundation/artifacts/auto/aios_core_automation/LATEST.json` |

### Commands (from `foundation`)

```powershell
cd L:\Continue\Viv\foundation
$py = "L:\Continue\.venv\Scripts\python.exe"

# Integrated plan-only (default): preflight + training catalog + backup plan
& $py scripts\run_aios_core_automation_v1.py --plan-only

# Integrated safe execute: preflight + training uml_status + backup uml_lane
& $py scripts\run_aios_core_automation_v1.py --execute-safe

# Inventory / phase map (no sibling execute)
& $py scripts\run_aios_core_automation_v1.py --list
& $py scripts\run_aios_core_automation_v1.py --phase-map
```

Equivalent from Viv root:

```powershell
L:\Continue\.venv\Scripts\python.exe foundation/scripts/run_aios_core_automation_v1.py --plan-only
L:\Continue\.venv\Scripts\python.exe foundation/scripts/run_aios_core_automation_v1.py --execute-safe
```

### What each integrated bundle does

| Mode | Siblings | Phase tags | FS / runtime effects |
|---|---|---|---|
| `--plan-only` (`integrated_plan_only`) | systems preflight, training catalog, backup `uml_lane` plan | 0, 1, 2, 3 | plan/catalog only; no AIOS start; no `GPU_LONG` |
| `--execute-safe` (`integrated_execute_safe`) | systems preflight, training `uml_status`, backup `uml_lane` execute | 0, 1, 2, 3 | backup `uml_lane` is the only FS-effect sibling; **still** no AIOS start; no `GPU_LONG` |

Hard denials for both bundles (encoded in receipts):

- `aios_runtime_started: false`
- `gpu_long_launched: false`
- `deny_weight_packs: true`
- `federation_activation: false`
- `bridge_promotion: false`
- `soft_0_99: false`

### Verified receipts (2026-08-07)

| Stamp | Mode | `ok` | Notes |
|---|---|---|---|
| `20260807T092111Z_plan_only` | `plan_only` | **true** | siblings preflight / training_catalog / backup_uml_lane all ok; AIOS not started |
| `20260807T092120Z_execute_safe` | `execute_safe` | **true** | siblings preflight / training_uml_status / backup_uml_lane all ok; AIOS not started; no GPU_LONG |

Read: `foundation/artifacts/auto/aios_core_automation/<stamp>/RECEIPT.json`  
(`LATEST.json` tracks the most recent write and may point at a later per-profile
plan; prefer the stamped bundle folders above for those two results.)

### Per-core profiles (secondary)

`--profile <id> --plan-only` (or closed-smoke / backup delegate where allowed)
covers cores tagged across Phases 0–8 (`main`, `utils`, `rid`, `support`,
`fractal`, `backup_*`, `carma`, `consciousness`, `dream`, voice-adjacent,
`music`, `game`, etc.). Gaps such as federation, full knowledge absorption,
vision, and `GPU_LONG` training remain operator-gated and are listed in
`--inventory` — not auto-executed by this orchestrator.

```powershell
& $py scripts\run_aios_core_automation_v1.py --profile fractal --plan-only
& $py scripts\run_aios_core_automation_v1.py --inventory
```

### Sibling runners (still valid; orchestrator prefers not to duplicate)

| Surface | Runner |
|---|---|
| Systems preflight | `scripts/run_aios_systems_preflight_v1.py` |
| Training automation | `scripts/run_training_automation_v1.py` |
| Backup core | `scripts/run_backup_core_automation_v1.py` |
| Continue automation check | `L:\Continue\automation\check_automation.ps1` (before/after automation spine edits) |

## 5.2 AIOS subagent worker bus (skeleton)

**Purpose:** thin local **worker bus** for the AIOS skeleton — named profiles map
to existing plan-only runners or SKIP stubs, with receipts and bounded fanout.
Not Cursor IDE Task fanout. Not deep cognition; `compute_core` is a **RESERVED**
hook (`dispatch: false`) for later compute-core integration.

| Piece | Path |
|---|---|
| Runner | `foundation/scripts/run_aios_subagent_v1.py` |
| Library | `foundation/lib/aios_subagent_v1.py` |
| Selftest | `foundation/scripts/test_aios_subagent_v1.py` |
| Receipts root | `foundation/artifacts/auto/aios_subagents/` |
| Latest pointer | `foundation/artifacts/auto/aios_subagents/LATEST.json` |

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

& $py foundation\scripts\run_aios_subagent_v1.py --list
& $py foundation\scripts\run_aios_subagent_v1.py --run selftest_ping
& $py foundation\scripts\run_aios_subagent_v1.py --run preflight --plan-only --timeout-s 60
& $py foundation\scripts\run_aios_subagent_v1.py --fanout selftest_ping,vision --timeout-s 30
& $py foundation\scripts\test_aios_subagent_v1.py
```

**Authority (fail-closed):** CPU-owned tags only; unknown profile → `FAIL_CLOSED`;
`--enable-aios-start` / `--enable-soft-099` / `--enable-bridge-canary` → `REFUSED`
in v1. Bridge profile uses `--rollback-check` only (canary stays default OFF).
Fanout concurrency capped at 3. Wired into system skeleton smoke as
`aios_subagent_list` + `aios_subagent_selftest`.

## 5.3 System skeleton smoke (walk check)

**Purpose:** one command that proves the **skeleton walks** — orchestration plus
safe surfaces (plan-only / catalog / contracts / canary / security gate) respond
and emit receipts. This is **not** a claim that every core is finished. Vacant
or missing slots are `SKIP` with note labeled `SKELETON` and do not fail the
aggregate by themselves. Any hard fail on a present surface → overall `FAIL`.

| Piece | Path |
|---|---|
| Runner | `foundation/scripts/run_aios_system_smoke_v1.py` |
| Library | `foundation/lib/aios_system_smoke_v1.py` |
| Selftest (catalog only) | `foundation/scripts/test_aios_system_smoke_v1.py` |
| Receipts root | `foundation/artifacts/auto/system_smoke/` |
| Latest pointer | `foundation/artifacts/auto/system_smoke/LATEST.json` |

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

# Full skeleton smoke (one receipt; includes bounded canary)
& $py foundation\scripts\run_aios_system_smoke_v1.py

# Catalog only / selftest (no child execute)
& $py foundation\scripts\run_aios_system_smoke_v1.py --plan-only
& $py foundation\scripts\test_aios_system_smoke_v1.py
```

Included surfaces (prefer plan-only / measurement / contracts):

- systems preflight `--profile quick --plan-only`
- core automation `--plan-only` (not `--execute-safe` — avoids vault copy)
- training `--profile uml_status`
- RID plant `--plan-only` + optional `health_quick --execute` (<10s, non-stress)
- voice `--profile contracts`
- cognitive cores `--profile both --plan-only`
- service cores `--core all --plan-only`
- backup `--profile uml_lane --plan-only`
- UML bridge security gate selftest
- field-scoped bridge canary with `--enable-canary --no-append-thesis` (default
  OFF; bounded; reference restore `CANARY_PASS` 64/64 at
  `foundation/artifacts/auto/field_scoped_bridge_canary/20260807T092420Z/`)
- intent UML request ingress selftest
- AIOS subagent bus `--list` + selftest (skeleton worker bus)

Hard denials: no AIOS start/stop, no `GPU_LONG`, no 120s plant stress, no
soft-0.99, no bridge default promotion, no large vault copy.

## 5.4 Daily operator loop (minimal)

1. Foundation health + `viv_shell.py status` (Part 4).
2. System skeleton smoke (optional quick walk) or core automation `--plan-only`
   (or `--execute-safe` when backup lane is intended).
3. Inspect receipts under `artifacts/auto/system_smoke/`,
   `artifacts/auto/aios_core_automation/`, and/or `artifacts/auto/aios_subagents/`.
4. Only then consider RID 120s captures, mouth tests, or governed training —
   each with its own authorization.

## 5.5 What this cookbook never does by default

- Start or stop the AIOS runtime.
- Launch `GPU_LONG` training.
- Promote the field-scoped bridge (canary remains **default OFF**; skeleton
  smoke may enable it only under `--enable-canary` for a bounded check).
- Activate federation against real endpoints.
- Copy weight packs / GPU trees.
- Invent a second rebuild roadmap beside Phases 0–8.

---

# Part 6 — Rebuild roadmap (Phases 0–8)

The older AIOS material is valuable source material, not an authority to copy
blindly. Rebuild preserves behavior and contracts while removing duplicate
paths, unverified claims, and unsafe autonomy.

Core automation profiles are tagged to these same phase numbers
(`COLD_START_PHASES` in `aios_core_automation.py`).

### Phase 0 — documentation and inventory (current)

- Keep this manual synchronized with `VIV_BUILD_STATUS.md`.
- Maintain a source-to-target migration manifest.
- Separate `BUILT`, `PARTIAL`, `LEGACY`, and `NONE` explicitly.
- Preserve old manuals and reports as historical references.
- Use the FSAA rebuild doctrine and staging roots for migrations.
- Orchestrator: systems preflight / inventory profiles.

**Exit evidence:** inventory, source hashes, target owner, tests, and rollback
path for each proposed migration.

### Phase 1 — finish the foundation spine

1. RID remains the sole owner of plant math and captures.
2. AUTO remains the sole owner of the operator beat and task queue.
3. UML becomes the complete symbolic/corpus surface.
4. Security remains the first and last membrane around all three.

**Exit evidence:** foundation health, valid 120-second captures, unified
preflight, boundary-registry integrity, and no cross-main ownership drift.

### Phase 2 — consolidate security and memory

- Finish remaining legacy constitution/governor migration into Viv Rust.
- Reconcile law versions and document the canonical law source.
- Expand CARMA retrieval beyond keyword-only behavior only after a measured baseline.
- Port selected legacy memory formats through staged migration tools.
- Preserve provenance, source hashes, and reversible imports.
- Orchestrator: backup `uml_lane` / `safe` profiles land here.

**Do not:** import the old vector/database path directly into the hot path or
claim semantic memory because an index exists.

### Phase 3 — finish the voice contract and training

- Keep the CPU judge authoritative.
- Continue the 96-case mouth evaluation until a checkpoint satisfies all
  relationship, safety, EOS, toolbleed, and blind gates.
- Keep live Qwen mouth and frozen incumbent unchanged until a separate
  promotion decision passes.
- Measure generated behavior, not just NLL or adapter norm.
- Orchestrator: training catalog / `uml_status` (never silent `GPU_LONG`).

**Exit evidence:** reproducible winner report, frozen outputs, no regressions,
fresh live-runtime validation, and a separate promotion authorization.

### Phase 4 — migrate knowledge and open-source ingestion

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
- Then vision from legacy stereoscopic/capture with bounded read-only capture
  and a memory-write contract.
- Then hearing/audio-to-text-to-CARMA with explicit device, privacy, buffering,
  and dormancy rules.

No perception module gains autonomous action authority merely because it can
produce a label or transcript.

### Phase 6 — identity, sovereignty, and transparency

- Finish identity provenance and approved self-description.
- Separate hardware/host identity from model identity and operator identity.
- Complete decision receipts so every externally relevant action is traceable.
- Field-scoped bridge canary (`CANARY_PASS`, default OFF) lives here as an
  operator-gated experiment — not a default hot path.

### Phase 7 — dream, ethics, and adaptive behavior

Viv's plain-text dream path exists. Remaining work: measure whether
consolidation improves retrieval without destroying provenance or introducing
false memories. Symbiotic ethics loop is not built; if pursued, begin as a
judgeable, reversible relationship-pattern experiment. Physics and host safety
remain the hard boundary.

### Phase 8 — hardware agnosticism and distributed systems

- Measure across hardware classes before claiming agnosticism.
- Adaptive heartbeat and context/token budgets from measured capacity.
- Multi-node / hive only after single-host authority is stable.

Distributed S_n, shared memory, and multi-node autonomy are future systems,
not current Viv capabilities.

---

# Part 7 — Legacy sources, docs map, handoff

## 7.1 Legacy source map

| Source | What it contributes | Migration rule |
|---|---|---|
| `F:\AIOS_Clean\AIOS_MANUAL.md` | broad V1/V5 user and module documentation (**v1 operator manual**) | reference structure/behavior; verify every claim in current code |
| `F:\AIOS_Clean\MANUAL_TOC.md` | line-indexed TOC for the v1 manual | navigation aid for historical research |
| `D:\LocalAi\AIOS_V1` | older core structure and historical implementation | inventory first; no direct hot-path imports |
| `D:\LocalAi\AIOS_V2` | expanded Luna/AIOS modules and experiments | port contracts selectively into Viv layers |
| `D:\LocalAi\AIOS_Luna_Aria` | laws, PRT/legacy theory, constitution references | preserve as source; reconcile with current Rust laws |
| `L:\Continue\FSAA` | rebuild pipeline, docs, tests, Steel Brain, Rust work | use staging/manifests and `docs/rebuild_doctrine.md` |
| `L:\External\External Docs_Dev` | external agent/operator docs | link and reconcile; do not assume current runtime truth |
| `D:\LocalAi\AIOS_Migration` | migration material and prior transfer plans | use as source manifests after hash verification |

**Absorb behavior, not folder count.** A legacy subsystem earns a Viv home only
when its purpose, owner, boundary, tests, artifacts, and rollback path are clear.

### Historical context only (obsolete vs current Viv)

| v1 / AIOS_Clean assumption | Current Viv truth |
|---|---|
| Luna personality as primary identity | Viv AIOS identity contract; GPU is mouth substrate |
| CARMA as “AI’s brain” framing | Computer/control language; CARMA Phase 1 plain-text memory |
| LM Studio / Streamlit-first install story | L: venv + foundation mains; no C: Python |
| Consciousness / biological-memory marketing layers | Not canonical Viv runtime claims |
| Broad “whatever you want” OS narrative | Bounded autonomy with Security IN/OUT and Law 5 |
| Docker / K8s / cloud deployment chapters | Local-first L: / FSAA staging; not those deploy targets |

## 7.2 Documentation map

| Read this | For this |
|---|---|
| `COLD_START.md` (this file) | living operator manual + rebuild map |
| `foundation/AIOS_ALPHA_MANUAL.md` | Alpha operator detail |
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
| `foundation/scripts/run_aios_core_automation_v1.py` | integrated core automation (Part 5.1) |
| `foundation/scripts/run_aios_subagent_v1.py` | skeleton subagent worker bus (Part 5.2) |
| `security_core/README.md` | Rust security implementation |
| `L:\Continue\FSAA\docs\rebuild_doctrine.md` | legacy rebuild rules |
| `F:\AIOS_Clean\AIOS_MANUAL.md` | historical broad manual (structure reference) |

## 7.3 Handoff checklist for the next session

### WAKE_FINISH (Codex reset tonight)

Machine-readable twin: `foundation/artifacts/auto/wake_finish/LATEST.json`  
Stamp: `20260807T092807Z` · Written for Codex reset handoff (no git commit in this pack).

#### Done

- **Skeleton system smoke PASS** — 12/12 in ~8.4s (`verdict=PASS`, `smoke_kind=skeleton`). Already done; do not rebuild.
  - Receipt: `foundation/artifacts/auto/system_smoke/20260807T092608Z/system_smoke_v1_20260807T092608Z.json`
  - LATEST: `foundation/artifacts/auto/system_smoke/LATEST.json`
  - Scripts (commit paths): `foundation/scripts/run_aios_system_smoke_v1.py`, `foundation/lib/aios_system_smoke_v1.py`, `foundation/scripts/test_aios_system_smoke_v1.py`
  - Manual: this file §5.3
- **AIOS subagent worker bus v1 LANDED** — 20 profiles; `--list`/`--run`/`--fanout`; fail-closed; compute-core hook RESERVED.
  - Receipts: `foundation/artifacts/auto/aios_subagents/` (`LATEST.json`)
  - Scripts (commit paths): `foundation/lib/aios_subagent_v1.py`, `foundation/scripts/run_aios_subagent_v1.py`, `foundation/scripts/test_aios_subagent_v1.py`
  - Manual: this file §5.2
- **Skeleton map + bus LANDED** — 35 systems structural coverage 100%; bus filled 77.8%; vacant for compute-core: `uml_invoke`, `subagent_spawn`.
  - Receipt: `foundation/artifacts/auto/aios_skeleton/20260807T092807Z/SKELETON_MAP.json`
  - LATEST: `foundation/artifacts/auto/aios_skeleton/LATEST.json`
  - Runner: `foundation/scripts/run_aios_skeleton_v1.py`
  - Libs: `aios_skeleton_bus.py`, `aios_skeleton_map.py`, `aios_skeleton_stub.py`, `aios_skeleton_subagent_profiles.py`, `aios_adapter_security.py`
- **Field-scoped bridge canary CANARY_PASS** — 64/64 (bounded; **default OFF**).
  - Receipt: `foundation/artifacts/auto/field_scoped_bridge_canary/20260807T092616Z/field_scoped_bridge_canary_v1_20260807T092616Z.json`
- Status matrix: `foundation/VIV_BUILD_STATUS.md` (Skeleton spine row).
- Core automation same-day stamps — §5.1 `20260807T092111Z_plan_only` / `20260807T092120Z_execute_safe`.

#### Must-do on wake (ordered)

**GOAL: Speak with Viv for real by end of 2026-08-08.**  
Pointer: `foundation/artifacts/auto/wake_finish/SPEAK_TOMORROW.md` (may still be writing — if missing, say "pending from speak critical-path agent").

0. Read `SPEAK_TOMORROW.md` (or note pending) — first commands there lead the speak path.
1. Confirm vacant bus slots still `uml_invoke` + `subagent_spawn` via map/`wire_status` (CLI subagent bus is landed; bus-slot wire-in may still be vacant).
2. **Wire compute core** (UML Nested-PEMDAS + RID/PID plant + mouth/security) into vacant slots — plan-only bind; no AIOS start. Bind `subagent_spawn` to `run_aios_subagent_v1.py` if still vacant.
3. Re-run skeleton map after wire-in; then re-run system smoke; require PASS.
4. Re-check canary under `--enable-canary` only; keep **default OFF**.
5. Read this WAKE_FINISH + `wake_finish/LATEST.json` + skeleton map + smoke receipts (Done above) for evidence context.
6. **Commit/push** (operator git): smoke trio + **subagent trio** (`aios_subagent_v1.py`, `run_aios_subagent_v1.py`, `test_aios_subagent_v1.py`) + skeleton bus/map/stub/security adapter + `run_aios_skeleton_v1.py` + `COLD_START.md` + `VIV_BUILD_STATUS.md` + `artifacts/auto/system_smoke/` + `artifacts/auto/aios_subagents/` + `artifacts/auto/aios_skeleton/` (exact list in wake_finish JSON).
7. Optional soft-0.99 ask only if canary still PASS + default OFF — do not enable.
8. Update `VIV_BUILD_STATUS.md` fill counts if wire-in changes them.
9. Record next blocker in the blank session form below; stop on smoke fail / policy conflict.

#### Do-not

- Do **not** start/stop AIOS runtime unless the operator explicitly asks.
- Do **not** launch `GPU_LONG` or any training mutation.
- Do **not** auto-run 120s stressed plant captures.
- Do **not** grant `SCAN_SURFACE` authority (ingress stays explicit `uml_request` only).
- Do **not** enable soft-0.99 by default (or at all without explicit operator ask after canary re-check).
- Do **not** promote the field-scoped bridge off canary / default OFF.
- Do **not** wipe manual Parts 1–7 when editing this file — merge handoff only.

#### Exact re-run commands

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

# Skeleton map (ALL systems + bus; plan-only)
& $py foundation\scripts\run_aios_skeleton_v1.py --plan-only

# Skeleton system smoke (already PASS 12/12; re-run after wire-in)
& $py foundation\scripts\run_aios_system_smoke_v1.py

# Catalog / selftest only (no child execute)
& $py foundation\scripts\run_aios_system_smoke_v1.py --plan-only
& $py foundation\scripts\test_aios_system_smoke_v1.py

# Field-scoped bridge canary (operator gate; default OFF — omit flag = off)
& $py foundation\scripts\run_field_scoped_bridge_canary_v1.py --enable-canary --no-append-thesis

# Foundation health (read-only)
& $py foundation\scripts\foundation_health.py
```

---

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
Field-scoped bridge canary (default OFF):
Last core-automation receipt (plan-only / execute-safe):
Last system skeleton smoke (stamp / verdict):
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
