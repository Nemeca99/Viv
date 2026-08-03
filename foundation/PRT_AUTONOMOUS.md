# Viv Fully Autonomous PRT Loop

Binding: perpetual deep PRT (`night start` profile) + Viv IDE (Cursor replacement).

## What it is

```
wait S_n → collect/apply (GPU LoRA) → integrity → [capability expansion] → [IDE inbox] → cooldown → forever
```

- `voice_speak` forced **false** in autonomous path (talk uses `--speak` explicitly)
- Halt: `halt.flag` or `prt_overnight_halt.flag` (`prt_main.py night halt` / `night resume`)
- Audit: `artifacts/audit/prt_autonomous.log`
- IDE: same `.cursor/skills` Cursor uses — read/write/search/shell under Law 7

## Run

```powershell
# Perpetual PRT + capability expansion + IDE inbox drain
L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/prt_main.py autonomous --with-capability-expansion

# Talk to Viv (replaces Cursor chat for AIOS work)
L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/prt_main.py talk "build a bridge inventory for carma_core"
L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/prt_main.py talk --status
L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/prt_main.py talk --inbox

# Halt
L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/prt_main.py night halt --soft --reason operator
```

## Evidence

| Artifact | Meaning |
|----------|---------|
| `artifacts/audit/prt_autonomous.log` | integrity / expand / IDE / loop |
| `artifacts/models/prt_cycles.jsonl` | scored PRT cycles |
| `artifacts/auto/viv_ide/` | IDE turns |
| `sandbox/work/aios_build/CHAT.md` | Architect ↔ Viv dialogue |
| `sandbox/work/aios_build/MANIFEST.md` | REWARD expansion commits |
| `sandbox/code/*_current.txt` | authored modules |

## Skills

`L:/.cursor/skills/` including `viv-ide-operator` — one skill surface for Cursor and Viv.
