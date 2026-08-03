# PRT Overnight (DEEP) + daytime quick

## Architect plant monitor (better than iCUE + Task Manager)

During PRT, open a second terminal. One Viv surface: **per-core load + Corsair temps + NVML GPU + Master RID**.

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
# Live (Ctrl+C to stop) — JSONL accumulates every tick
& $PY L:\Continue\Viv\foundation\rid_main.py monitor --interval 1

# Finite capture while something interesting happens
& $PY L:\Continue\Viv\foundation\rid_main.py monitor --seconds 120 --jsonl L:\Continue\Viv\foundation\artifacts\rid\prt_thermal_watch.jsonl
```

Log: `artifacts/rid/architect_monitor.jsonl` (default). Remade from Steel_Brain live_stream / hardware_monitor patterns onto Viv plant sensors (not a new invention).

| Mode | What it does | What it won't do overnight |
| ---- | ------------ | -------------------------- |
| **Quick** (day) | Tiny collect + 40 LoRA steps — GPU free soon | Meaningful fluency leap |
| **Deep** (night) | Heavy collect (20 obs + 10 speak) × up to 8 rounds, **400 steps** each, lower LR | Guarantee LoRA clears stamp alone; auto-speak stays **off** |

Deep overnight **can** grow scored physics rows and push the adapter toward house English + S_n prediction. The CPU stamp still rejects mush. Progress measure = more REWARD speak cycles + less `deterministic_after_lora_fail`, not "she talks like Claude."

The first overnight run used shallow daytime-sized rounds (120 steps). That was a loop demo, not deep training. Config is now **deep**.

## Day — while building

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\prt_main.py quick
# or:
& $PY L:\Continue\Viv\foundation\prt_main.py apply --preset quick
```

## Night — deep

```powershell
# Visible (leave window open)
& $PY L:\Continue\Viv\foundation\prt_main.py night start

# Detached (recommended)
L:\Continue\Viv\foundation\scripts\prt_overnight_start.ps1

# Custom: 50 rounds, 60s pause, 18h cap
L:\Continue\Viv\foundation\scripts\prt_overnight_start.ps1 -MaxRounds 50 -MaxHours 18 -Cooldown 60
```

Deep defaults (~18h budget): **50 rounds** · 6 obs + **12 life** + 4 speak + **8 pulse** · **200 steps** · lr `5e-5` · **60s** cool-down.

Conway task: `PRT_LIFE_TASK.md` — predict live_cells + Master S_n under CPU pressure.

Preset source: `artifacts/models/prt_presets.json`  
Night config: `artifacts/models/prt_overnight_config.json`

## Ship checklist (after ghost baseline completes)

1. `prt_main.py stage ab-piston` — archive ghost window → `ab_piston_ghost_vs_live_v1.{json,md}`
2. Start live overnight (piston_background; epoch already begun — do not reset):

```powershell
# Symbiote nudge — recommended next run (~25 rounds, host-prior bait)
& $PY L:\Continue\Viv\foundation\prt_main.py night start `
  --config L:\Continue\Viv\foundation\artifacts\models\prt_overnight_config_live_symbiote.json

# Full 50-round live pilot
& $PY L:\Continue\Viv\foundation\prt_main.py night start `
  --config L:\Continue\Viv\foundation\artifacts\models\prt_overnight_config_live.json
```

Promotion metrics (`stage check`) exclude cycles before `telemetry_epoch_start` in `prt_stage_state.json`.

| Config | `piston_background` | `begin_telemetry_epoch` | Purpose |
| ------ | ------------------- | ----------------------- | ------- |
| `prt_overnight_config.json` | false | false | Ghost baseline (50-round) |
| `prt_overnight_config_live.json` | true | false | Full 50-round live pilot |
| `prt_overnight_config_live_symbiote.json` | true | false | 25-round live + symbiote host-prior bait |

## Controls

| Command | Effect |
| -------- | ------ |
| `night status` | State / plant / lock |
| `night halt` | Stop between rounds |
| `night resume` | Clear overnight halt |

Auto-speak never enabled by these loops.
