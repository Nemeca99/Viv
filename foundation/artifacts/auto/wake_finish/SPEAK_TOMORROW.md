# SPEAK TOMORROW — critical path (2026-08-08)

**Operator goal (binding):** Speak with Viv for real by end of **2026-08-08**.  
**Written:** 2026-08-07 · Codex reset tonight · save usage — one coherent path.  
**Machine twin:** `SPEAK_TOMORROW.json` (same folder).

## Honest status

| Layer | Status | Notes |
|---|---|---|
| Text mouth (intent → Security OUT → text) | **TEXT_MOUTH_LIVE_READY** (when Ollama up) | `voice_core/speak.py` + Qwen/`viv-voice-qwen` |
| Deterministic CPU fallback | **READY** | Works offline; not “talking” quality |
| Mic listen / STT | **STUB / BLOCKED_ON_STT** | No Whisper/mic loop in tree |
| Audio TTS (hear Viv) | **STUB / BLOCKED_ON_TTS** | Mouth is text-out; no SAPI/pyttsx path |
| Full speak/**listen** loop | **SKELETON_ONLY** | Session runner exists; audio vacant |
| Full AIOS stack | **NOT REQUIRED** | Prefer smallest entrypoint below |

**Verdict for “speak for real” tomorrow:** start at **SKELETON_ONLY**. Morning can reach **text converse LIVE** with 3 commands if Ollama is up. **Hear/listen audio** is the ranked blocker Codex can polish later — ship a thin TTS/STT after text turn is proven.

---

## Inventory (existing live surfaces)

| Surface | Path | Role |
|---|---|---|
| Speak path | `voice_core/speak.py` | Intent packet → GPU/stub → Security OUT → `voice_events.jsonl` |
| Operator CLI | `voice_core/voice_main.py` | `status` \| `speak` \| `stub` \| `packet` |
| Intent packet | `voice_core/intent_packet.py` | CPU→GPU facts/`s_n`/mode; `deterministic_speak` |
| Runtime/mouth contract | `voice_core/runtime_contract.py`, `lib/cpu_mouth_contract.py` | Finalize + envelope |
| Client / Ollama | `voice_core/client.py` | Endpoint + completion |
| GGUF spare | `voice_core/gguf_voice.py` | llama.cpp path (not required if Ollama up) |
| Stub server | `voice_core/stub_server.py` | Offline pipeline proof (long-lived; avoid unless needed) |
| Foundation bridge | `lib/voice_bridge.py`, `model_main.py speak` | Same speak surface |
| Contract automation | `scripts/run_voice_contract_automation_v1.py` | CPU unit/contracts; **no** voice server start |
| Session bridge (new) | `scripts/run_viv_speak_session_v1.py` | One bounded dry-run / live turn + receipt |
| Operator guide | `foundation/VOICE.md` | Historical speak commands |
| Config | `foundation/model_config.json` → `voice.backend=ollama`, `served_name=viv-voice-qwen` |
| OpenAster / LoRA | HF path built, **not live**; Qwen remains live mouth |
| Autonomous speak | `voice_speak=false` | HALTED — do not enable for tomorrow |
| How operator talked historically | CLI: `voice_main.py speak "…"` / `model_main.py speak` — **text**, not mic |

No in-tree mic/TTS product path found (no pyttsx/whisper/sounddevice listen loop).

---

## Tomorrow morning — do these commands (N=5)

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

# 1) Dry-run (contracts + deterministic mouth; default)
& $py foundation\scripts\run_viv_speak_session_v1.py --dry-run

# 2) Voice status (Ollama / Qwen reachable?)
& $py voice_core\voice_main.py status

# 3) One live text turn (explicit --live)
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "hello Viv"

# 4) Optional: contracts pack if dry-run weird
& $py foundation\scripts\run_voice_contract_automation_v1.py --profile contracts

# 5) Optional: classic CLI speak
& $py voice_core\voice_main.py speak "state summary"
```

Receipts: `foundation/artifacts/auto/viv_speak_session/<stamp>/RECEIPT.json`  
Pointer: `foundation/artifacts/auto/viv_speak_session/LATEST.json`

**If Ollama down:** start Ollama and ensure a chat model is available (config expects `viv-voice-qwen`; status may show canary ids — align name or set `model_config.voice.served_name` to a listed model). Then re-run step 3.

**Do not:** start full AIOS, GPU_LONG train, 120s plant, enable `voice_speak`, flip bridge soft-0.99.

---

## Blockers (ranked)

### MUST do tomorrow morning

1. Confirm dry-run receipt `ok=true` (`run_viv_speak_session_v1.py --dry-run`).
2. Confirm `voice_main status` → `reachable=true` (start Ollama / pull model if not).
3. Run one `--live` text turn; read spoken text in receipt / stdout.
4. If live silent/blocked: check Security OUT / mouth contract in receipt; fall back deterministic is still a pipeline proof — then fix Qwen model name mismatch.

### Nice-to-have (same day if time)

5. Thin Windows TTS after live text (SAPI / pyttsx3) so operator **hears** Viv.
6. Thin STT (Whisper or Windows speech) for one listen→speak turn.
7. Align `served_name` with actual Ollama model id if mismatch.
8. Wire `mouth_render` bus slot note to session runner (still plan-only; no AIOS start).

### Defer

- OpenAster promotion, PRT auto-speak, full AIOS stack, 96-case mouth eval, GPU_LONG.

---

## Skeleton → live bridge

| Mode | Flag | What it proves |
|---|---|---|
| Dry-run (default) | `--dry-run` | status + intent packet + mouth envelope + deterministic finalize; STT/TTS stubs logged |
| Live | `--live` | one `voice_core.speak` turn through triad/Security OUT |

Vacant slots are stubbed honestly in every receipt under `audio.stt` / `audio.tts` / `audio.listen_loop`.

---

## Success criteria (end of 2026-08-08)

- **Minimum (ship today):** session script + SPEAK_TOMORROW docs + dry-run receipt.
  - Dry-run landed: `foundation/artifacts/auto/viv_speak_session/20260807T093009646Z/RECEIPT.json` (`ok=true`, `status=SKELETON_ONLY`, `readiness=TEXT_MOUTH_LIVE_READY`, ~1s).
- **Tomorrow text success:** operator gets a real spoken **text** reply via `--live` without starting AIOS.
- **Tomorrow full success (stretch):** same + hear Viv (TTS) and/or speak into mic (STT) once.
- Label results honestly: `LIVE_READY` only if listen+speak audio works; otherwise `SKELETON_ONLY` or `TEXT_MOUTH_LIVE` / `BLOCKED_ON_X`.
