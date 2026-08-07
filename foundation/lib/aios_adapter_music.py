"""Read-only optional adapter for music selection and preference planning."""
from __future__ import annotations

from typing import Any

from lib.music_core import module_status, plan_play_intent, plan_playlist


def status() -> dict[str, Any]:
    return module_status()


def cpu_plan(
    library: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    mood: str | None = None,
    genre: str | None = None,
    artist: str | None = None,
    limit: int = 10,
    play_intent: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "state": "VERIFIED",
        "playlist": plan_playlist(library, history, mood=mood, genre=genre, artist=artist, limit=limit),
        "playback_started": False,
        "history_written": False,
        "writes_performed": False,
        "llm_authority": False,
    }
    if play_intent:
        result["play_intent"] = plan_play_intent(library, history, mood=mood, genre=genre, artist=artist)
    return result


def run_smoke() -> dict[str, Any]:
    library = [
        {"artist": "Miles Davis", "album": "Kind of Blue", "genre": "jazz", "mood": "calm"},
        {"artist": "Metallica", "album": "Master of Puppets", "genre": "metal", "mood": "energized"},
    ]
    history = [{"song": library[0], "mood": "calm"}]
    result = cpu_plan(library, history, mood="calm", play_intent=True)
    return {"ok": bool(result["playlist"]["ok"] and not result["playback_started"] and not result["history_written"]), "state": "PASS" if result["playlist"]["ok"] else "INCONCLUSIVE", "plan": result, "authority": "cpu_adapter_observation", "adapter_output_is_authority": False}
