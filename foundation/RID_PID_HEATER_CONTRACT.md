# RID-on-PID Heater Control Software — Contract

**Binding:** RID **layers on top of PID**. RID does **not** replace PID.

This is industrial control software for quartz / process heaters. It must **work as software** before hardware arrives, then plug into real PID + heater IO without changing the contract.

---

## Architecture

```
Setpoint ──► [ PID inner loop ] ──► duty% ──► [ RID envelope ] ──► final duty% ──► Heater
                  ▲                         │
                  │                         ▼
                  └──────── SP, PV, duty → RSR / LTP / RLE / S_n
```

| Layer | Owns | Does not own |
|-------|------|--------------|
| **PID** | Tracking law (error → duty) | Safety envelope |
| **RID** | Observe triad, gain schedule, duty clamp, interlock | Tracking law |

Adaptive gain (Phone theory): `Kp_dyn = Kp_static × S_n` (floor applied).

---

## Prove / Disprove

| Mode | Meaning |
|------|---------|
| **Baseline** | PID alone (`mode=pid`) |
| **Pilot** | RID on PID (`mode=rid_pid`) |

Same plant, same base gains, same setpoint + disturbance profile.

**PROVED** — pilot tracking OK/better **and** safety improved (less overshoot and/or higher min RLE).  
**DISPROVED** — pilot tracking worse with no safety gain.  
**INCONCLUSIVE** — sample thin or no clear delta.

Command:

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\rid_pid_main.py ab
```

Artifacts: `artifacts/audit/ab_rid_pid_heater_v1.{json,md}`

---

## Modules

| File | Role |
|------|------|
| `lib/pid_controller.py` | Inner PID |
| `lib/rid_heater_channels.py` | Heater RSR/LTP/RLE from SP/PV/duty |
| `lib/rid_pid_supervisor.py` | RID envelope on PID output |
| `lib/quartz_heater_plant.py` | Software plant (until hardware) |
| `lib/rid_pid_loop.py` | Closed loop + A/B metrics |
| `rid_pid_main.py` | CLI |

---

## Hardware handoff (when heater + PID arrive)

Replace `QuartzHeaterPlant.step(duty, dt)` with a driver that:

1. Writes duty to SSR / Eurotherm OP / real PID remote setpoint interface
2. Reads PV from thermocouple / controller
3. Keeps the same `RIDOnPIDController.step(setpoint, pv, dt)` call

Software stack does not change. Plant adapter does.

---

## Non-negotiables

1. Never reframe RID as a PID replacement.
2. Never claim industrial proof from AIOS PC thermals alone.
3. A/B reports must be machine-readable; INCONCLUSIVE is valid.
4. Fail-safe: RID interlock may cut duty; it may not invent a new controller.
