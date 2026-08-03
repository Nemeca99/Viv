# RID — Resource Integrity Dynamics

**Pillar entry:** `rid_main.py` — everything AIOS needs for RID.  
**Autonomous consumer:** `auto_main.py` reads RID artifacts; it does not implement RID.  
**See also:** `FOUNDATION_ROADMAP.md` for the three-pillar split.

---

## What RID Is

RID models a machine as a **dual-sensor plant**. Two temperature readings (A °C, B °C) define a geometric stress state:

| Symbol | Sensor formula | Meaning |
|--------|----------------|---------|
| **LTP** | `(A + B) / 2` | Thermal midpoint |
| **RSR** | `A × B` | Coupled thermal product |
| **RLE** | `A×B − ((A+B)/2)²` | Spread / gap energy between sensors |
| **RLE_rate** | `dRLE/dt` | Rate of gap change — early warning |

From load, temperature, and RAM, RID derives **runtime channels** normalized to **0–1** (what the control loop uses):

| Channel | Meaning |
|---------|---------|
| **RSR** | Load stability |
| **LTP** | Thermal headroom |
| **RLE** | RAM headroom |

**Composite stability:**

```
S_n = (RSR × LTP × RLE)^(1/3)
```

**Equation set (canonical vs proposed electrical/routing):** `RID_EQUATIONS.md`  
— Part A is implemented plant law; Part B electrical is **observe-only** until meters complete.

**Electrical observe gate (no Master authority):**
```powershell
L:\Continue\.venv\Scripts\python.exe scripts\test_rid_electrical.py
L:\Continue\.venv\Scripts\python.exe scripts\test_rid_electrical_adversarial.py
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_meter_inventory.py
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_observe.py --once
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_shadow_ab.py
```
Code: `lib/rid_electrical.py`. Artifacts: `artifacts/auto/rid_electrical/`.  
State: **`rejected_operational_use`** for Master/prediction/routing; rails **`observe_only_diagnostics`**.  
Lifecycle: unimplemented → implemented-unavailable → measured-in-shadow → **rejected operational use** (`RID_EQUATIONS.md` §B.15).  
Closed result: decisive 15-session corpus, \(\Delta_{\text{info}}<0\) → no \(A(t)\), no Master weight, no advisory routing, canary fail-closed. Diagnostics retained (power/voltage/derived I/stale sensors). Reopen only under material-change conditions — not more of the same meters. Next plant focus: thermal, coolant, load, VRAM, transitions, existing RID subsystems.  
Shadow A/B with incomplete triad is labeled **INCONCLUSIVE** (honest), not a Master admit.

**Dormancy threshold:** `S_n < 0.45` → DORMANT. Privileged automation, speech, and irreversible actions are blocked until stability returns. (Law-5 host security may use ~0.37 — see `RID_EQUATIONS.md`.)

---

## Architect monitor (PRT companion)

`rid_main.py monitor` — remade from Steel_Brain live_stream / hardware_monitor patterns onto Viv plant:

| Pane | Source |
|------|--------|
| Per-core load % | `psutil` via `piston_engine.read_loads` |
| Per-core + package + coolant °C | Corsair iCUE CSV (`corsair_telemetry`) |
| GPU temp/util/VRAM/power | NVML (`gpu_plant`) |
| Master RSR/LTP/RLE/S_n + subsystems | `master_rid` |

JSONL default: `artifacts/rid/architect_monitor.jsonl`. Run beside PRT when thermals look “interesting.”

---

## PC Sensor Pairs

| Pair | A | B | Use |
|------|---|---|-----|
| `cpu_gpu` | CPU package (iCUE) | GPU die (NVML) | Default live telemetry |
| `cpu_coolant` | CPU package | H100i coolant | Liquid-loop stability proof |
| `core_spread` | Hottest core | Coolest core | Intra-die thermal spread |

Poll cadence: **1 Hz** (matches Corsair iCUE CSV logging).

---

## Hierarchical Master S_n

Every subsystem has its own normalized channels and **master S_n** (0–1). The whole system rolls up to one **Master S_n**.

| Subsystem | Source | Role |
|-----------|--------|------|
| `cpu_automaton` | `rid_triad` runtime channels | Package-level automaton |
| `piston` | `piston_state.json` per-core aggregate | Per-core thermal firing / governor |
| `gpu` | NVML util / temp / VRAM | Air-cooled GPU plant |
| `coolant_loop` | CPU package + coolant temps | H100i liquid loop health |

**Per subsystem:** `S_n = (RSR × LTP × RLE)^(1/3)` (all channels clamped 0–1)

**System Master S_n:** geometric mean of all available subsystem S_n values (same for master RSR/LTP/RLE).

Under full stress, the weakest subsystem dominates — geometric mean is intentionally harsh.

**Authority chain:** sensors → subsystem S_n → Master S_n → heartbeat / supervisor / autonomy gate → agentic runtime tick.

---

## Plant Captures

120-second stress captures at 1 Hz produce machine-readable evidence. Verdicts:

| Verdict | Meaning |
|---------|---------|
| **PASS** | Stress confirmed, cadence met, workers alive |
| **PASS_FLAT** | 100% load held; iCUE temps flat (liquid loop stable, no sensor steps logged) |
| **FAIL** | Cadence shortfall, workers died, or load insufficient |
| **INCONCLUSIVE** | Idle or low-signal sample |

Canonical captures require **≥90% of target polls** (e.g. 108/120 minimum).

---

## Autonomous Operator

`auto_main.py autonomous --interval 1` runs the always-on loop:

1. Foundation gate
2. Pulse (live sample + Master S_n)
3. RID journal → supervisor heartbeat
4. Piston snapshot (background thread ticks independently)
5. Plant snapshot
6. Tiered gate (halted / degraded / nominal)
7. Agentic runtime tick when nominal (Master S_n ≥ 0.45, ACTIVE)

**Piston runs in a background daemon thread** — it does not block the 1 Hz autonomy beat.

---

## Measured Results (2026-07-04)

### Hardware

- CPU: Intel i7-11700F (16 logical cores)
- GPU: RTX 3060 Ti (air)
- Cooler: Corsair H100i (liquid)
- OS: Windows 11
- Python: `L:\Continue\.venv` (3.12)

### Canonical plant proofs

| Capture | Artifact | Polls | Cadence | Load | Verdict |
|---------|----------|-------|---------|------|---------|
| CPU + coolant blast | `artifacts/rid/stability_pc_120s_v5.csv` | 120/120 | 1.0 Hz | CPU 100%, 16/16 workers | **PASS_FLAT** |
| Coupled CPU+GPU | `artifacts/rid/coupled_master_120s_v2.csv` | 120/120 | 1.00 Hz | CPU 100%, GPU 99% util | **PASS** |
| Core spread | `artifacts/rid/core_spread_master_120s_v1.csv` | 120/120 | 1.00 Hz | CPU 100%, 16/16 workers | **PASS** |

**PASS_FLAT (v5 coolant proof):** iCUE held CPU package and coolant constant for all 120 polls under 100% CPU blast. H100i liquid loop demonstrated flat thermal hold.

**Coupled v2 (canonical):** Master S_n mean 0.0023 under full CPU+GPU stress — system correctly reports DORMANT when all plants are saturated. Subsystem means: cpu_automaton 0.099, piston 0.013, gpu 0.373, coolant_loop 0.0.

**Core spread v1:** Master S_n mean 0.0014 under CPU-only stress. GPU idle headroom high (mean 0.823).

*Note:* `coupled_master_120s_v1.csv` (55 polls) is pre-cadence-fix — superseded by v2.

### Autonomous loop (idle / light load)

Observed live with `auto_main autonomous --interval 1`:

| Signal | Result |
|--------|--------|
| Foundation gate | OK |
| Piston background | Running — `pis` climbed ~0.01 → ~0.47 over first minute |
| Master S_n | Settled **0.45–0.62 ACTIVE** after warm-up |
| Plant verdict | PASS |
| Runtime | `rt=0` when nominal, `rt=skip` when DORMANT |
| Mode | nominal (majority of beats after warm-up) |

---

## Key Paths

| Purpose | Path |
|---------|------|
| Foundation root | `L:\Continue\Viv\foundation\` |
| Live sample | `artifacts/rid/live_sample.json` |
| Master S_n | `artifacts/auto/master_rid.json` |
| Pulse / autonomy state | `artifacts/auto/pulse.json`, `autonomous_state.json` |
| Piston state | `artifacts/auto/piston/piston_state.json` |
| Plant verdict | `artifacts/auto/plant/last_stability_capture.json` |
| Phone reference | `L:\Phone\` |
| RID implementation | `lib/rid_triad.py`, `lib/master_rid.py` |

---

## Commands

```powershell
# Live Master S_n
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\auto_main.py master --live

# Always-on autonomous loop
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\auto_main.py autonomous --interval 1

# 120s coolant stability proof (blast)
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\rid_main.py stability --stress --seconds 120 --csv L:\Continue\Viv\foundation\artifacts\rid\stability_pc_120s_v5.csv

# 120s coupled CPU+GPU Master S_n capture
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\rid_main.py coupled-capture --seconds 120

# 120s core spread Master S_n capture
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\rid_main.py core-spread-capture --seconds 120

# Foundation health
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\scripts\foundation_health.py
```

---

## Summary

RID is a **stability governor**, not a workload scheduler. It measures whether the machine's thermal, load, and memory plants are in a state where autonomous action is safe. On this PC, that measurement chain is implemented, stress-tested at 120 seconds and 1 Hz, and running in a continuous autonomous loop with background piston control.

**Pillar boundary:** All RID capability belongs in `rid_main.py`. `auto_main.py` only consumes the output.
