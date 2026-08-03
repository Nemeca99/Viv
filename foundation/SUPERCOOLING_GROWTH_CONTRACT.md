# Supercooling Growth Contract (Viv)

**Status:** BINDING for capacity growth  
**Architect:** Travis Miner  
**Source doctrine:** `L:/Continue/docs/supercooling.md` (phone theory/sim)  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

---

## Phone vs PC

| | Phone script in supercooling.md | Viv PC (this contract) |
| --- | --- | --- |
| Role | Theory + simulation of control law | Production AIOS growth spine |
| Telemetry | `/proc`, thermal zones | **Master RID** RSR/LTP/RLE + Master S_n |
| Growth | Virtual experts/params counters | Real actuators (LoRA widen first) behind ceilings |

Phone proved: calibrate idle → accumulate strain when S_n &lt; target → growth event → stabilize.  
PC must **rewrite** that law onto AIOS plant — not copy phone paths.

---

## Continuous identity (no ghost murder)

- Hatchling = current OpenAster HF + `viv_voice_lora` (r=16).
- Growth stages (Hatchling → Drake → Wyrm → Dragon) are **capacity of the same lineage**.
- Forbidden: replace soul with a new Instruct/RLHF base and call it “upgrade.”
- Allowed actuators must be **function-preserving** (Net2Net spirit): zero-pad LoRA widen, later base Net2Wider/Deeper, later MoE chambers with inherited seeds.

---

## Dynamic vs static

| Layer | Language | Role |
| --- | --- | --- |
| Strain, ledger, crystallize (PRT), LoRA widen, overnight | **Python** | Dynamic — Viv may change constantly |
| Security membrane, Law 5, tool_gate, **growth ceilings** | **Rust** (`security_core`) | Static — Architect-immutable bounds |

Python **proposes** growth. Rust **may veto** if over policy ceiling or illegal actuator.

---

## Strain law (PC)

1. Calibrate idle Master S_n for N seconds → `artifacts/auto/growth_baseline.json`
2. `target = baseline − margin` (default margin 0.03)
3. Each tick: sample Master RID; `strain += max(0, target − master_s_n) * dt`
4. If `strain ≥ threshold` and plant not near-dead → emit growth event → reset strain
5. Log triad (rsr/ltp/rle) on every sample/event

**Near-dead / protect host:** if Master S_n below critical / integrity `near_dead`, **do not expand**. Cool and protect. Same priority as Law 5 dormancy over host harm.

---

## Crystallize vs grow

- **Crystallize** = PRT cycle (observe / life / speak) — temporary activation lattice; weights unchanged except training steps.
- **Grow** = bottle expand (LoRA r+, later experts/base) when strain says the container needs more liquid.
- **Breathe** = `growth_main.py breathe` — observe crystallize → strain ticks → optional `--apply-pending`.
- **Chambers** = `growth_chambers.json` ledger (phone experts counter). `real_moe=false` until a real MoE actuator exists.
- Auto-speak remains **false** until separate promote policy.
- Strain **cools** when Master S_n ≥ target (no idle residual fires).

---

## Phase-1 actuator allowlist

1. `lora_widen` — pad LoRA rank (zeros), backup adapter first  
2. (later) `moe_chamber_add`, `base_net2wider` — not enabled until ceiling + tests

Policy file: `artifacts/auto/growth_policy.json` (Rust + Python both read).

---

## Sensors (binding)

- **CPU package + coolant:** Corsair iCUE CSV at `L:/Steel_Brain/RID/RID_Completed/HW-Info/Corsair_Log`
- **GPU die:** NVIDIA NVML directly (not Corsair GPU Temp columns)
- Search `L:/` for prior art before inventing; remake permanently into `Continue/Viv/` when needed

## Plant pressure for strain proofs

Full-core blast collapses Master S_n into **near_dead** → correctly **no grow**.  
Use moderate **GovernedFleet** duty (already in Viv `lib/cpu_governor.py`) via:

```powershell
& $PY L:\Continue\Viv\foundation\growth_main.py run-pressured --seconds 90 --duty 0.30
```

Seeks band `(critical+0.05, target)` then runs strain. Pending grow may fire; auto-widen still off unless `--apply` / `apply_on_overnight`.

## Operator entry

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\growth_main.py calibrate --seconds 30
& $PY L:\Continue\Viv\foundation\growth_main.py run --seconds 120
& $PY L:\Continue\Viv\foundation\growth_main.py run-pressured --seconds 90
& $PY L:\Continue\Viv\foundation\growth_main.py status
& $PY L:\Continue\Viv\foundation\growth_main.py widen --delta-r 4
& $PY L:\Continue\Viv\foundation\growth_main.py widen --pending
```
