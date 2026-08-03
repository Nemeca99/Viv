# GPU Voice Phase 1 — stub smoke

**When:** 2026-07-15 ~01:03 CDT  
**Python:** `L:/Continue/.venv/Scripts/python.exe`  
**Verdict:** **PASS**

## Commands + results

### 1. Status offline → silent OK

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\voice_core\voice_main.py status
```

- `ok: true`, `silent: true`, `reachable: false`, exit 0

### 2. Stub + speak round-trip

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\voice_core\stub_server.py --port 8000
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\voice_core\voice_main.py speak "state summary"
```

- Stub rendered facts + CARMA cue
- Security OUT `allowed: true` (security_core 0.2.3)
- Logged `artifacts/auto/voice_events.jsonl`
- `model_main.py speak` alias also OK

### 3. Packet JSON (CARMA + S_n)

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\voice_core\voice_main.py packet --json "state summary"
```

- `s_n` from Master RID, `memory` top-k from CARMA live fallback

### 4. Status after stub stop → silent OK again

- `ok: true`, `silent: true` (not an error)

## Out of scope (unchanged)

- AWQ download / vLLM install
- PRT/SPRT, emotion GGUFs
- GPU deciding or remembering
