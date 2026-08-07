# SPEAK TOMORROW — text-first critical path (2026-08-08)

**Operator goal:** Speak with Viv for real by end of **2026-08-08**.  
**Primary success = text round-trip.** Mic/camera exist but are **out of scope** for tomorrow.  
**MP3 file = optional SKIP** — do not block on TTS deps.  
**Machine twin:** `SPEAK_TOMORROW.json` · **Happy path:** `OPERATOR_HAPPY_PATH.md`

## Verdict (tonight)

| Layer | Status |
|---|---|
| Text mouth (`--live --text`) | **PRIMARY** — TEXT_LIVE_READY when turn returns reply |
| Deterministic CPU fallback | READY offline |
| MP3 / TTS-to-file | **SKIP / TODO** (nice later; not a wake blocker) |
| Mic STT / camera | **OUT OF SCOPE** — do not build |
| Full AIOS | **NOT REQUIRED** |
| Bus vacant | `uml_invoke` only — HOLD, do not fake UML |

**Operator labels:** **TEXT_LIVE_READY** (text works) · audio MP3 = SKIP · full listen+speak audio = not tomorrow.

---

## Morning — 3 commands only

```powershell
cd L:\Continue\Viv
$py = "L:\Continue\.venv\Scripts\python.exe"

& $py foundation\scripts\run_viv_speak_session_v1.py --dry-run
& $py voice_core\voice_main.py status
& $py foundation\scripts\run_viv_speak_session_v1.py --live --text "hello Viv"
```

Receipts: `foundation/artifacts/auto/viv_speak_session/<stamp>/RECEIPT.json`  
Pointer: `foundation/artifacts/auto/viv_speak_session/LATEST.json`

**Pass:** `ok=true` + non-empty spoken text in summary/`speak_result.text`.  
**If Ollama down:** start it, align `voice.served_name`, re-run live. Deterministic text still proves the path.

**Do not:** full AIOS, GPU_LONG, 120s plant, mic/camera work, soft-0.99, leftover stub servers.

---

## Surfaces used (smallest)

- `voice_core/speak.py` — intent → mouth → Security OUT → text
- `voice_core/voice_main.py status` — Ollama reachability
- `foundation/scripts/run_viv_speak_session_v1.py` — dry-run / one-turn live + receipt
- `uml_invoke` — vacant HOLD (no fake Nested-PEMDAS)

## Success by end of 2026-08-08

1. **Ship:** operator gets a real **text** reply via `--live --text` without AIOS boot.
2. **Stretch (optional):** write `viv_speak.mp3` under the session stamp — only if deps already easy.
3. Never label `LIVE_READY` for mic/listen until STT exists; tomorrow = **TEXT_LIVE_READY**.
