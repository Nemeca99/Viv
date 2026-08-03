# AIOS Canonical Alpha Briefing

Purpose: give this document to an AI in a fresh chat so it understands what Travis is building, what has been proven, and how to verify claims without asking for everything from scratch.

**Full vision doctrine:** `VIV_COMPLETE_SUMMARY.md` — the complete definition of Viv (SGI, CARMA, constitution, GPU voice, perception, ethics).

**Build status matrix:** `VIV_BUILD_STATUS.md` — what is **BUILT**, **PARTIAL**, **LEGACY**, or **NONE** for each vision section. Read this before assuming anything in the vision doc is implemented.

This briefing covers Canonical Alpha build state and verification only.

## One-Sentence Summary

AIOS is being rebuilt as a local-first two-AI system in `L:\Continue\Viv\`. **The CPU is Viv** — the deterministic neuro-symbolic automaton that does what it is told and programmed to do, and learns by becoming more thermodynamically efficient. **The GPU is the persona and human interface** — a separate transformer layer that presents Viv's work in forms humans can digest, using a base model without RLHF that Travis will train directly.

It has three canonical mains:

- `rid_main.py` = CPU-first RID stability/control evidence
- `auto_main.py` = agentic/autonomous action loop
- `uml_main.py` = calculator/language layer for coding, symbols, written/spoken output

The Canonical Alpha build lives in `L:\Continue\Viv\foundation\`. Broader `L:\Continue` cleanup is deferred until Travis explicitly starts housekeeping.

---

## Non-Negotiable Context

- OS: Windows 11
- Hardware: i7-11700F, RTX 3060 Ti, Corsair H100i
- Python runtime: `L:\Continue\.venv\Scripts\python.exe`
- Canonical build root: `L:\Continue\Viv\`
- Foundation root: `L:\Continue\Viv\foundation\`
- Phone RID theory reference: `L:\Phone\`
- Do not reframe RID as a PID replacement. RID sits above plant/PID-style control as a stability/governance layer.
- Do not treat old FSAA/automation/Luna trees as the final system. They are sources to absorb from later. The Alpha rebuild target is `Viv`.
- **CPU is Viv.** `L:\Continue\Viv\` is not just a folder name — it is where the CPU deterministic AI lives. Canonical Alpha is Viv-first.
- Viv's learning is thermal-dynamic efficiency under RID, not transformer-style learning.
- **GPU is the persona and interface for humans.** It is a separate transformer AI, later-pluggable, based on a non-RLHF base model trained by Travis. It does not replace Viv.

---

## The Three Mains

| Main | Owns | Does Not Own |
| ------ | ------ | -------------- |
| `rid_main.py` | CPU sensors, RID triad, Master S_n, CPU plant captures, stress proofs, piston/coolant telemetry, plots, benchmarks | Autonomous scheduling, task execution, language, GPU-first behavior |
| `auto_main.py` | Always-on loop, gates, journal, background piston snapshot, plant authority, FSAA runtime ticks | RID theory, plant proof tooling, UML |
| `uml_main.py` | Symbolic language, calculator, verify, trace, corpus export | RID governance, autonomous scheduling, voice, emotion, GPU |

Rule: mains do not call each other as CLIs. They import shared `foundation/lib/*` implementation. `auto_main.py` reads RID artifacts, not `rid_main.py`.

---

## Two-AI Architecture

| Lane | Identity | Role |
| ------ | ---------- | ------ |
| **CPU** | **Viv** (three mains) | Deterministic automaton. Decides intent, tone, what to say. Issues intent packets. No `.gguf`, no GPU inference. |
| **GPU** | **Voice / persona** (peripheral) | Renders human output. Selects emotion model from Training layer. Invoked by core, never inhabited by it. |

Viv must stand on its own before the GPU persona layer matters. Viv is the foundation; the GPU is how humans meet it.

### Layer boundaries (do not blur)

| Layer | Owns | Does not own |
| ------- | ------ | -------------- |
| **Three mains** | RID, autonomy, symbolic UML | Emotion, voice, `.gguf`, GPU inference |
| **Security** | Bidirectional IN/OUT gate — laws, tariff, Guardian, Rust governor | Memory, rendering |
| | **IN:** first line — blocks external input not allowed into foundation | |
| | **OUT:** last line — blocks internal output not allowed to External | |
| | **120-in/120-out:** integrity passthrough, no bypass around three mains | |
| **Memory** | CARMA, tags, Wikipedia | Inference, emotion |
| **GPU/Voice** | Persona render, emotion selection, inference | Core decisions, `.gguf` storage |
| **Training** | `.gguf` persona files, corpus, PRT/SPRT | Runtime intent, security |

---

## RID: What It Is

RID means **Resource Integrity Dynamics**.

It models stability using a dual-sensor plant:

| Symbol | Sensor Formula | Meaning |
| -------- | ---------------- | --------- |
| LTP | `(A + B) / 2` | Thermal midpoint |
| RSR | `A × B` | Coupled thermal product |
| RLE | `A×B - ((A+B)/2)^2` | Gap/spread energy |
| RLE_rate | `dRLE/dt` | Rate of gap change |

Runtime control uses normalized channels in `[0, 1]`:

| Runtime Channel | Meaning |
| ----------------- | --------- |
| RSR | Load stability |
| LTP | Thermal headroom |
| RLE | RAM headroom |

Composite:

```text
S_n = (RSR * LTP * RLE)^(1/3)
```text

Dormancy threshold:

```text
S_n < 0.45 => DORMANT
S_n >= 0.45 => ACTIVE
```

Hierarchical Master S_n:

- `cpu_automaton`
- `piston`
- `coolant_loop`
- `gpu` when the optional GPU layer is enabled

Each subsystem has its own S_n. Whole-system `Master_S_n` is the geometric mean of available subsystem S_n values. Under full stress, it intentionally collapses toward the weakest subsystem.

---

## What Has Been Proven

### Canonical 120s Captures

| Proof | Artifact | Result |
| ------- | ---------- | -------- |
| CPU + coolant blast | `L:\Continue\Viv\foundation\artifacts\rid\stability_pc_120s_v5.csv` | 120/120 polls, CPU 100%, 16/16 workers, `PASS_FLAT` |
| Core spread | `L:\Continue\Viv\foundation\artifacts\rid\core_spread_master_120s_v1.csv` | 120/120 polls, CPU 100%, `PASS` |

Optional GPU/plugin proof:

| Proof | Artifact | Result |
| ------- | ---------- | -------- |
| Coupled CPU+GPU | `L:\Continue\Viv\foundation\artifacts\rid\coupled_master_120s_v2.csv` | 120/120 polls, CPU 100%, GPU 99%, `PASS` |

Important:

- `coupled_master_120s_v1.csv` had only 55 polls and is pre-cadence-fix. Do not treat it as canonical.
- `coupled_master_120s_v2.csv` is valid optional GPU evidence, not the CPU core authority.
- `PASS_FLAT` means stress was confirmed but iCUE held the temperatures flat for all polls. That is valid evidence for a stable liquid loop, not a failure.

### Autonomous Loop

Observed command:

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\auto_main.py autonomous --interval 1
```

Observed behavior:

- Foundation gate: OK
- Piston: background thread, non-blocking
- Plant verdict: PASS
- Master S_n: warmed into ACTIVE range, roughly `0.45-0.62`
- Runtime: `rt=0` when nominal, `rt=skip` when DORMANT
- Modes: degraded during warm-up or below threshold, nominal when Master S_n >= 0.45

This means sensors -> subsystem S_n -> Master S_n -> gate -> autonomous beat -> runtime tick is working.

---

## How To Verify In One Pass

Use this exact Python:

```powershell
$PY="L:\Continue\.venv\Scripts\python.exe"
```

### 1. Check RID canonical status

```powershell
& $PY L:\Continue\Viv\foundation\rid_main.py status
```

Expected:

- `coolant` exists, `PASS_FLAT`
- `coupled` exists, `PASS`, `120/120`
- `core_spread` exists, `PASS`, `120/120`
- `Master_S_n` present
- Piston state present
- GPU state present

Machine-readable:

```powershell
& $PY L:\Continue\Viv\foundation\rid_main.py status --json
```

### 2. Verify audit artifacts

```powershell
& $PY -m json.tool L:\Continue\Viv\foundation\artifacts\audit\three_mains_registry.json > $null
& $PY -m json.tool L:\Continue\Viv\foundation\artifacts\audit\run_log_index.json > $null
```

Expected: no JSON errors.

### 3. Check current plant authority

```powershell
Get-Content L:\Continue\Viv\foundation\artifacts\auto\plant\last_stability_capture.json
```

Expected:

- `verdict.verdict` is `PASS`
- Recent canonical summary path points at a 120s capture, not a smoke test.

### 4. Check Master S_n artifact

```powershell
Get-Content L:\Continue\Viv\foundation\artifacts\auto\master_rid.json
```

Expected:

- `master_s_n`
- `status`
- `n_subsystems`
- `subsystems.cpu_automaton`
- `subsystems.piston`
- `subsystems.gpu`
- `subsystems.coolant_loop`

### 5. One autonomous beat

```powershell
& $PY L:\Continue\Viv\foundation\auto_main.py autonomous --once
```

Expected:

- Output begins `[nominal]` or `[degraded]`
- Includes `Master_S_n=...`
- Includes `plant=PASS`
- If nominal, runtime tick returns `rt=0` or printed runtime result.

### 6. UML smoke

```powershell
& $PY L:\Continue\Viv\foundation\uml_main.py eval "[3,4]"
```

Expected:

- It evaluates successfully. Exact formatting may vary by current UML engine.

### 7. Safe smoke capture without corrupting plant authority

Short captures fail by design because they are not 120s. Use `--no-publish`:

```powershell
& $PY L:\Continue\Viv\foundation\rid_main.py capture --kind coolant --seconds 3 --log-all --no-publish --csv L:\Continue\Viv\foundation\artifacts\rid\smoke_verify_3s.csv
```

Expected:

- Command runs and writes CSV/summary.
- Verdict may be `FAIL` because polls are too low.
- `last_stability_capture.json` must remain canonical PASS.

---

## Current Build State

### Done

- `auto_main.py autonomous` is the working foundation spine.
- RID canonical proofs exist and pass.
- Background piston no longer blocks the 1 Hz loop.
- Master S_n exists and is used by the autonomous gate.
- Phase 0 three-mains audit exists.
- Initial `rid_main.py` absorption exists:
  - `status`
  - `capture --kind coolant|coupled|core_spread`
  - `plot --master`
  - Master S_n columns in coolant/stability captures
  - `--no-publish` for smoke tests

### In Progress

Finish `rid_main.py` so it owns the CPU-first RID operator surface:

- piston commands
- CPU black-hole plant commands
- GPU triad / visual commands are optional edge wrappers, not required for Alpha core
- any remaining duplicate RID entry points

### Next After RID

- `auto_main.py`: absorb worker/queue/supervisor runtime surfaces into Canonical Alpha.
- `uml_main.py`: expose verify/trace/b52/corpus and make it the full language main.

---

## What Not To Do

- Do not ask Travis to rerun all 120s captures unless you have a specific reason.
- Do not treat short smoke `FAIL` as proof the system is broken; short captures fail poll-count gates by design.
- Do not overwrite `last_stability_capture.json` with smoke results. Use `--no-publish`.
- Do not clean up FSAA/automation/Luna trees yet. Housekeeping is later.
- Do not move implementation into the mains inline. Mains are CLI surfaces; `foundation/lib/*` holds implementation.
- Do not chain mains together. `auto_main` does not call `rid_main`; it reads RID artifacts.

---

## Key Files

| Purpose | Path |
| --------- | ------ |
| Alpha roadmap | `L:\Continue\Viv\foundation\FOUNDATION_ROADMAP.md` |
| RID explanation/results | `L:\Continue\Viv\foundation\RID.md` |
| This briefing | `L:\Continue\Viv\foundation\AIOS_ALPHA_BRIEFING.md` |
| Audit registry | `L:\Continue\Viv\foundation\artifacts\audit\three_mains_registry.json` |
| Audit summary | `L:\Continue\Viv\foundation\artifacts\audit\three_mains_audit.md` |
| Session journal | `L:\Continue\Viv\foundation\artifacts\audit\session_journal.md` |
| Run index | `L:\Continue\Viv\foundation\artifacts\audit\run_log_index.json` |
| RID main | `L:\Continue\Viv\foundation\rid_main.py` |
| Auto main | `L:\Continue\Viv\foundation\auto_main.py` |
| UML main | `L:\Continue\Viv\foundation\uml_main.py` |

---

## For An AI Assistant: How To Be Useful

1. Start by reading this file, `FOUNDATION_ROADMAP.md`, and `RID.md`.
2. Verify with `rid_main.py status --json` before making claims.
3. Treat `L:\Continue\Viv\` as the active Canonical Alpha build.
4. Keep changes inside `Viv` unless Travis explicitly says housekeeping has started.
5. When testing captures, use `--no-publish` unless the intent is to promote a canonical proof.
6. Preserve evidence: write summaries and JSON artifacts; do not rely on narrative.
7. Continue current build order: finish `rid_main.py`, then `auto_main.py`, then `uml_main.py`.

If unsure, ask: "Is this part of Canonical Alpha in Viv, or later housekeeping?"
