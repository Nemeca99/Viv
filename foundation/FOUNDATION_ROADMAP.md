# Viv Foundation — Canonical Alpha

**Canonical Alpha root:** `L:\Continue\Viv\`
**Foundation:** `L:\Continue\Viv\foundation\`

AIOS is being rebuilt here first as two AIs. **The CPU is Viv** — the deterministic neuro-symbolic automaton that executes programmed/operator intent and learns by becoming more thermodynamically efficient. **The GPU is the persona and human interface** — a separate transformer lane that presents Viv in forms humans can digest, using a base model without RLHF that Travis trains directly. Canonical Alpha is Viv-first. The three mains below are the only Alpha operator CLI surface. Broader `L:\Continue` housekeeping (FSAA, automation, Luna, launchers, legacy copies) is deferred until the operator explicitly starts that phase.

Phase 0 audit artifacts:

- `artifacts/audit/three_mains_registry.json`
- `artifacts/audit/three_mains_audit.md`
- `artifacts/audit/run_log_index.json`
- `VIV_COMPLETE_SUMMARY.md` — full Viv doctrine (vision, CARMA, constitution, GPU voice)
- `VIV_BUILD_STATUS.md` — BUILT / PARTIAL / LEGACY / NONE matrix per vision section
- `AIOS_ALPHA_BRIEFING.md` — one-file handoff for new AI chats and verification

AIOS is built on three mains. Each owns one concern. They do not overlap.

## System stack (build order)

Layers stack **bottom-up**. Each layer has explicit boundaries. **Security is the first and last line of defense** — nothing enters or leaves the CPU core without passing both checks.

### Security envelope (bidirectional gate)

Think electricity: **120V in → 120V out**. What is allowed in is what may go out. No bypass, no smuggling, no unauthorized transformation.

```text
                    External / User
                          │
                   ┌──────▼──────┐
                   │  SECURITY   │  ◄── INGRESS (first line)
                   │  IN check   │      laws · tariff · S_n · whitelist
                   └──────┬──────┘
                          │  only if allowed
              ┌───────────▼───────────┐
              │  THREE MAINS          │  entire CPU core
              │  rid · auto · uml     │  nothing skips this
              └───────────┬───────────┘
                          │
                   ┌──────▼──────┐
                   │  SECURITY   │  ◄── EGRESS (last line)
                   │  OUT check  │      same rules, fail-closed
                   └──────┬──────┘
                          │
              Memory → GPU/Voice → Training → External
```

**Ingress rule:** External input does **not** reach the three mains unless Security IN allows it. Blocked at the door.

**Egress rule:** Nothing from inside (foundation or upper layers) reaches External unless Security OUT allows it. Blocked at the exit.

**No bypass:** There is no side channel around the three mains. There is no direct external ↔ internal path that skips Security.

Upper layers (Memory, GPU/Voice, Training) sit **above** the secured foundation envelope. They inherit the same in/out contract — intent and output are checked at the Security boundary.

```text
┌──────────────────────────────────────┐
│  TRAINING          (.gguf personas)  │
└──────────────────────────────────────┘
       ↑
┌──────────────────────────────────────┐
│  GPU / VOICE       (render only)     │
└──────────────────────────────────────┘
       ↑
┌──────────────────────────────────────┐
│  MEMORY / KNOWLEDGE  (CARMA, wiki)   │
└──────────────────────────────────────┘
       ↑  (all traffic through Security IN/OUT around foundation)
┌──────────────────────────────────────┐
│  SECURITY IN  →  THREE MAINS  →  SECURITY OUT │
└──────────────────────────────────────┘
```

### Intent packet flow (runtime)

1. **External input** → **Security IN** → **CPU core (three mains)** processes → issues intent packet.
2. **Memory** enriches (tags, CARMA, Wikipedia).
3. **GPU / Voice** renders using **Training** layer `.gguf` models.
4. **Security OUT** → **External output**. Same integrity contract as ingress.

**Not in the CPU core:** emotion selection, `.gguf` loading, GPU inference. `uml_main.py` is symbolic language only.

**Current phase:** three foundation mains are **solid**. **Security layer** (`security_core\`, Rust) is **in progress** — v0.1 built; wiring into foundation hot path is next.

| Entry | Owns | Does not own |
| ------- | ------ | -------------- |
| **`rid_main.py`** | **Everything AIOS needs for CPU-first RID** — sensors, triad, Master S_n, CPU plant captures, stress proofs, plots, piston telemetry, Phone parity | Autonomous loops, task execution, language, GPU-first behavior |
| **`auto_main.py`** | **Agentic and autonomous actions** — always-on beat, gates, journal, FSAA runtime ticks, operator spine | RID theory, plant capture tooling, UML |
| **`uml_main.py`** | **Calculator and symbolic language** — eval, verify, trace, convert, corpus build | RID governance, autonomous scheduling, **emotion selection**, **GPU inference**, **voice rendering** |

```text
┌──────────────────────────────────────────────────────────────┐
│  uml_main.py     symbolic language · calculator · verify      │
├──────────────────────────────────────────────────────────────┤
│  auto_main.py    agentic · autonomous · gates · runtime      │
├──────────────────────────────────────────────────────────────┤
│  rid_main.py     RID · telemetry · plant · Master S_n        │
├──────────────────────────────────────────────────────────────┤
│  lib/            shared implementation                       │
└──────────────────────────────────────────────────────────────┘
         ↑  entire CPU core — no .gguf, no GPU inference
```

**Dependency rule:** `auto_main` **reads** RID state (`live_sample.json`, `master_rid.json`, plant verdict). It never replaces `rid_main`. All RID work — captures, plots, benchmarks — lives under `rid_main` (and `lib/` it calls).

Theory: `L:\Phone\`. RID results: `RID.md`.

**Build order:** `auto_main` ✓ → `rid_main` ✓ → `uml_main` ✓ → **Security layer** next.

Only after all three are solid do we promote the next vision layers — **Security → Memory/Knowledge → GPU/Voice → Training → Rest of AIOS** — one at a time, each with evidence.

---

## 1. `rid_main.py` — The RID Pillar

**Entry:** `L:\Continue\Viv\foundation\rid_main.py`  
**Status:** **Solid** — single CPU-first RID operator CLI.

`rid_main.py` is the **single home for CPU-first RID capability** in AIOS. If it touches CPU sensors, stability, S_n, plant evidence, or thermal/load governance — it belongs here.

### Scope (everything RID)

| Area | Commands / libs |
| ------ | ----------------- |
| Live telemetry | `watch`, `log`, `feed`, `sample`, `stress` |
| Plant proof (120s) | `stability`, `core-spread-capture`; `coupled-capture` is optional GPU/plugin evidence |
| Master S_n hierarchy | `lib/master_rid.py`, `lib/plant_master_capture.py` |
| Visualization | `plot`, `cube`, `trajectory` |
| Benchmark / parity | `benchmark`, `compare` |
| Piston / coolant | `lib/piston_engine.py`, `lib/piston_background.py`, Corsair telemetry |
| Collapse physics | `black_hole_main.py` (related plant science) |

### Canonical artifacts

| Capture | File | Verdict |
| --------- | ------ | --------- |
| Coolant blast | `artifacts/rid/stability_pc_120s_v5.csv` | PASS_FLAT |
| Optional coupled CPU+GPU | `artifacts/rid/coupled_master_120s_v2.csv` | PASS (120/120), not CPU core authority |
| Core spread | `artifacts/rid/core_spread_master_120s_v1.csv` | PASS (120/120) |

### Remaining `rid_main` polish (non-blocking)

| Task | Status |
| ------ | ------ |
| Unified `capture` command | Done |
| Master S_n in stability path | Done |
| `plot --master` | Done |
| `status` + `health` | Done |
| Piston + black-hole absorption | Done |
| Legacy `coupled-capture` / `core-spread-capture` | Deprecated → `capture --kind` |
| Refresh `compare` for plant captures | Optional |
| Document sensor pairs in `RID.md` | Optional |

---

## 2. `auto_main.py` — Agentic & Autonomous — DONE

**Entry:** `L:\Continue\Viv\foundation\auto_main.py`  
**Status:** Foundation complete.

Owns the **always-on operator**: pulse, Master S_n gate, RID journal, background piston snapshot, plant authority check, Viv agentic tick (Rust-gated).

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\auto_main.py autonomous --interval 1
```

### What it does

- Consumes RID artifacts produced by `rid_main` / live feed
- Tiered modes: `halted` / `degraded` / `nominal`
- Delegates work to `lib/agentic_runtime.py` via `tool_gate` / Security membrane (`agentic_main.py` for operator queue)
- Writes automation spine (`journal_pulse`, supervisor, heartbeat)

### What it does not do

- Plant captures, stress tests, plots → **`rid_main`**
- UML eval, language, calculator → **`uml_main`**
- Implement RID formulas or sensor math → **`lib/rid_triad.py`** via `rid_main` / shared lib only

### Post-foundation polish (optional)

Deprecate legacy `run`/`loop`, guardian on hot path, supervisor cleanup, dormancy hysteresis, FSAA task seeding, service wrapper.

---

## 3. `uml_main.py` — Calculator & Language — SOLID

**Entry:** `L:\Continue\Viv\foundation\uml_main.py`  
**Status:** **Solid** — full calculator/language CLI surface.

Owns **how Viv thinks in symbols** — expression evaluation, verification, traces, corpus export for the Training layer. Not RID. Not autonomous scheduling. **Not voice, not emotion, not GPU inference.**

### Scope

| Command | Purpose |
| --------- | --------- |
| `eval`, `repl`, `demo`, `examples`, `symbols` | Calculator |
| `verify`, `trace`, `convert`, `b52`, `dual-eval` | Symbolic audit |
| `corpus` | Export JSONL for **Training layer** consumption (not runtime voice) |

### Does not own

- Emotion selection (`joyful.gguf`, `analytical.gguf`, …) → **GPU/Voice layer**
- `.gguf` loading or GPU inference → **GPU/Voice layer**
- Persona file storage → **Training layer**
- Spoken/written rendering → **GPU/Voice layer** (peripheral service invoked by core)

---

## 4. Security system — IN PROGRESS (`L:\Continue\Viv\security_core\`)

**Path:** `L:\Continue\Viv\security_core\` — **own folder, own layer. Rust only** for enforcement.  
**Operator CLI:** `security_core\security_main.py` (thin Python over PyO3)  
**Foundation bridge:** `foundation\lib\security_bridge.py`

### Doctrine

Security is the **first and last line of defense**. Nothing happens unless it passes **both** checks. **Security MUST be Rust** — Python Guardian (`guardian_main.py`) remains orchestration/tariff until fully wired through the Rust gate.

| Direction | Role | Rule |
| --------- | ---- | ---- |
| **IN (ingress)** | First line | External input blocked unless allowed. Must pass through Security before the three mains see it. |
| **OUT (egress)** | Last line | Internal output blocked unless allowed. Nothing reaches External without Security OUT — including paths from upper layers back out. |

**Electricity principle:** 120V in → 120V out. Integrity passthrough. No unauthorized amplification, leakage, or side-channel bypass around the foundation.

### Viv folder layout (one folder = one layer)

```text
L:\Continue\Viv\
  foundation\       Python — rid_main · auto_main · uml_main (CPU core)
  security_core\    Rust   — bidirectional IN/OUT gate, immutable laws
  (future)
  memory_core\      CARMA, tags, Wikipedia
  voice_core\       GPU persona render, emotion selection
  training_core\    .gguf files, PRT/SPRT, corpus production
```

### Build & verify

```powershell
cd L:\Continue\Viv\security_core
cargo build --release
Copy-Item -Force target\release\security_core.dll L:\Continue\.venv\Lib\site-packages\security_core.pyd

# Native Rust CLI
.\target\release\security_core_cli.exe check-in "hello" --s-n 0.56

# Python operator CLI
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\security_core\security_main.py check-out "response" --s-n 0.56
```

### Implementation status

| Component | Status |
| --------- | ------ |
| Rust crate `security_core` (gate IN/OUT, laws, governor) | **BUILT** v0.2.1 |
| PyO3 module (`check_ingress`, `check_egress`, `enforce_morality`) | **BUILT** |
| `security_main.py` operator CLI | **BUILT** |
| `foundation/lib/security_bridge.py` | **BUILT** |
| Wire Guardian + autonomous loop through Rust gate | **BUILT** — heartbeat + Guardian ingress |
| Full 8 Laws + Luna constitution port | **BUILT** v0.2.1 — hardened red-team PASS 62/62 |
| Tariff thesaurus | **BUILT** — keyword weights + soft interlock in governor |

**Done when:** Every external-facing entry and exit is fail-closed through Rust Security IN/OUT; three mains remain the only CPU core path.

---

## File index

| File | Pillar |
| ------ | -------- |
| `rid_main.py` | RID — everything AIOS needs for control/stability |
| `auto_main.py` | Agentic — autonomous actions and runtime |
| `uml_main.py` | Language — symbolic calculator, verify, trace |
| `RID.md` | RID theory and measured results |
| `FOUNDATION_ROADMAP.md` | This document |
| `cpu_config.json` | Paths, dormancy, solo_mode, pillar registry |

---

## Last Updated

2026-07-04
