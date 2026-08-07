"""Optional, read-only music selection and preference planner."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MODULE_ID = "music_core"
VERSION = "v1"
MANUAL_SECTION = "3.14"
MANUAL_SOURCE = "F:/AIOS_Clean/music_core"
MAX_TRACKS = 512
MAX_HISTORY = 512
MAX_TEXT = 200
DEFAULT_MOOD_MAPPINGS = {
    "sad": ("blues", "jazz", "acoustic"),
    "happy": ("pop", "dance", "upbeat"),
    "stressed": ("ambient", "classical", "nature"),
    "focused": ("instrumental", "lo-fi", "classical"),
    "energized": ("rock", "metal", "electronic"),
    "calm": ("jazz", "acoustic", "ambient"),
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_TEXT]


def _hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def validate_track(track: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(track, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "track_not_mapping"}
    artist = _clean(track.get("artist"))
    album = _clean(track.get("album"))
    genre = _clean(track.get("genre")).casefold()
    mood = _clean(track.get("mood")).casefold()
    issues = [name for name, value in (("artist", artist), ("album", album), ("genre", genre)) if not value]
    return {"ok": not issues, "state": "VERIFIED" if not issues else "ABSTAIN", "artist": artist, "album": album, "genre": genre, "mood": mood, "issues": issues, "track_hash": _hash(dict(track)), "filesystem_read_performed": False, "filesystem_write_performed": False, "llm_authority": False}


def select_tracks(library: Sequence[Mapping[str, Any]], *, genre: str | None = None, mood: str | None = None, artist: str | None = None, mood_mappings: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    """Filter and deterministically order caller-supplied library metadata."""
    target_genre = _clean(genre).casefold()
    target_mood = _clean(mood).casefold()
    target_artist = _clean(artist).casefold()
    mappings = {key.casefold(): tuple(str(value).casefold() for value in values) for key, values in (mood_mappings or DEFAULT_MOOD_MAPPINGS).items()}
    allowed_genres = set(mappings.get(target_mood, ())) if target_mood else set()
    tracks: list[dict[str, Any]] = []
    rejected = 0
    for raw in list(library)[:MAX_TRACKS]:
        checked = validate_track(raw)
        if not checked.get("ok"):
            rejected += 1
            continue
        if target_genre and checked["genre"] != target_genre:
            continue
        if target_mood and checked["mood"] != target_mood and checked["genre"] not in allowed_genres:
            continue
        if target_artist and target_artist not in checked["artist"].casefold():
            continue
        tracks.append({"track": checked, "source": "caller_supplied_library"})
    tracks.sort(key=lambda row: (row["track"]["artist"].casefold(), row["track"]["album"].casefold(), row["track"]["genre"]))
    return {"ok": True, "state": "VERIFIED", "matches": tracks, "rejected_tracks": rejected, "filters": {"genre": target_genre, "mood": target_mood, "artist": target_artist}, "filesystem_read_performed": False, "writes_performed": False, "llm_authority": False}


def summarize_preferences(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize only supplied play history; no clock or persistence access."""
    genres: Counter[str] = Counter()
    moods: Counter[str] = Counter()
    artists: Counter[str] = Counter()
    for row in list(history)[:MAX_HISTORY]:
        song = row.get("song") if isinstance(row, Mapping) else None
        song = song if isinstance(song, Mapping) else row
        genre = _clean(song.get("genre")).casefold()
        mood = _clean(song.get("mood")).casefold()
        artist = _clean(song.get("artist"))
        if genre:
            genres[genre] += 1
        if mood:
            moods[mood] += 1
        if artist:
            artists[artist] += 1
    return {"ok": True, "state": "VERIFIED" if genres or moods or artists else "INSUFFICIENT", "plays_observed": min(len(history), MAX_HISTORY), "favorite_genres": [name for name, _count in genres.most_common()], "favorite_moods": [name for name, _count in moods.most_common()], "favorite_artists": [name for name, _count in artists.most_common()], "source_scope": "caller_supplied_history_only", "learning_persisted": False, "filesystem_read_performed": False, "filesystem_write_performed": False, "llm_authority": False}


def plan_playlist(library: Sequence[Mapping[str, Any]], history: Sequence[Mapping[str, Any]], *, mood: str | None = None, genre: str | None = None, artist: str | None = None, limit: int = 10, mood_mappings: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    """Build a stable playlist proposal; never starts playback."""
    selected = select_tracks(library, genre=genre, mood=mood, artist=artist, mood_mappings=mood_mappings)
    preferences = summarize_preferences(history)
    favorite_genres = {name: index for index, name in enumerate(preferences.get("favorite_genres") or [])}
    rows = list(selected.get("matches") or [])
    rows.sort(key=lambda row: (favorite_genres.get(row["track"]["genre"], 999), row["track"]["artist"].casefold(), row["track"]["album"].casefold()))
    bounded_limit = max(1, min(int(limit), 64))
    playlist = rows[:bounded_limit]
    return {"ok": bool(playlist), "state": "PROPOSED" if playlist else "INSUFFICIENT", "playlist": playlist, "requested": {"mood": _clean(mood), "genre": _clean(genre), "artist": _clean(artist)}, "preferences": preferences, "selection": selected, "playback_started": False, "history_written": False, "writes_performed": False, "llm_authority": False}


def plan_play_intent(library: Sequence[Mapping[str, Any]], history: Sequence[Mapping[str, Any]], *, mood: str | None = None, genre: str | None = None, artist: str | None = None) -> dict[str, Any]:
    playlist = plan_playlist(library, history, mood=mood, genre=genre, artist=artist, limit=1)
    return {"ok": playlist["ok"], "state": playlist["state"], "selected": (playlist.get("playlist") or [None])[0], "playlist": playlist, "playback_authorized": False, "playback_started": False, "history_written": False, "writes_performed": False, "llm_authority": False}


def module_status() -> dict[str, Any]:
    return {"ok": True, "state": "READY_OPTIONAL", "module": MODULE_ID, "version": VERSION, "manual_section": MANUAL_SECTION, "optional": True, "read_only": True, "playback_authorized": False, "preference_learning_persisted": False, "llm_authority": False}
