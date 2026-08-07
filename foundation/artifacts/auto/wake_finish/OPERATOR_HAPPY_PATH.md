# Operator happy path — talk to Viv (text)

**Goal:** real text reply from Viv. No mic. No camera. No full AIOS.  
**Milestone:** `--live --text` → reply in stdout + receipt. MP3 = optional later.

## Do this (3 commands)

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

# 1) Offline contracts (fast; no audio write)
& $py foundation\scripts\run_viv_speak_session_v1.py --dry-run

# 2) Is Ollama / Qwen up?
& $py voice_core\voice_main.py status

# 3) One real text turn
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "hello Viv"
```

Open the receipt: `foundation/artifacts/auto/viv_speak_session/LATEST.json` → `RECEIPT.json`.  
Success = `ok=true` and a non-empty `text_preview` / `speak_result.text`.

## If status says unreachable

1. Start Ollama (user app / service).
2. Ensure a chat model exists (`ollama list`). Config expects `viv-voice-qwen` — rename in `foundation/model_config.json` `voice.served_name` if your tag differs.
3. Re-run command 3.

Offline still returns deterministic CPU text through Security — useful pipeline proof, but label it `ALMOST_OFFLINE`, not GPU live.

## Do not

- Full AIOS start, GPU_LONG, 120s plant, mic/STT, camera, soft-0.99, enable `voice_speak`.
- Leave stub servers running overnight.

## Verdict labels

| Label | Meaning |
|---|---|
| **TEXT_LIVE_READY** | `--live` returned real mouth text (Ollama or honest deterministic) |
| **ALMOST** | Path works; start Ollama for GPU mouth quality |
| **BLOCKED** | Dry-run or live failed — fix receipt `detail` first |
| MP3 | SKIP/TODO — not required for tomorrow |

More detail: `SPEAK_TOMORROW.md` (same folder).
