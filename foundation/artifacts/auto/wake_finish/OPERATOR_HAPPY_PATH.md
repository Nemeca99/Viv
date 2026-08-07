# Operator happy path — talk to Viv (text)

**Goal:** real text reply from Viv. No mic. No camera. No full AIOS.  
**Rule:** run **`--preflight` before `--live`**. Do not treat pipe-ok as converse-ready.

## Do this (in order)

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

# 1) GATE — model present + identity anchors survive finalize
& $py foundation\scripts\run_viv_speak_session_v1.py --preflight

# 2) Only if preflight says CONVERSE_READY (or PIPE_ONLY_IDENTITY_CPU for CPU-only)
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "Who are you?"
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "What is your tone?"
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "hello Viv"
```

Open receipts under `foundation/artifacts/auto/viv_speak_session/`.

## Verdict labels

| Label | Meaning |
|-------|---------|
| `CONVERSE_READY` | Ollama model matches config + identity finalize OK |
| `PIPE_ONLY_IDENTITY_CPU` | Identity CPU OK; GPU model missing/mismatch |
| `NOT_CONVERSE_READY` | Do not run casual `--live` yet |
| `TEXT_LIVE_READY` | One live turn returned text (still check `text_preview`) |

## Do not

- Skip preflight after overnight / rebuild
- Treat evidence-fallback as a greeting
- Full AIOS start, mic/STT, soft-0.99
