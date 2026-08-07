"""Focused tests for the optional effect-closed music boundary."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.music_core import module_status, plan_play_intent, plan_playlist, select_tracks, summarize_preferences, validate_track


def _library() -> list[dict[str, str]]:
    return [{"artist": "Miles Davis", "album": "Kind of Blue", "genre": "jazz", "mood": "calm"}, {"artist": "Metallica", "album": "Master of Puppets", "genre": "metal", "mood": "energized"}]


def test_track_validation_and_mood_selection() -> None:
    assert validate_track(_library()[0])["ok"] is True
    result = select_tracks(_library(), mood="calm")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["track"]["artist"] == "Miles Davis"
    assert result["filesystem_read_performed"] is False


def test_preferences_are_from_supplied_history_only() -> None:
    history = [{"song": _library()[0], "mood": "calm"}, {"song": _library()[0], "mood": "calm"}]
    result = summarize_preferences(history)
    assert result["favorite_genres"] == ["jazz"]
    assert result["learning_persisted"] is False
    assert result["source_scope"] == "caller_supplied_history_only"


def test_playlist_and_play_intent_are_non_mutating() -> None:
    result = plan_playlist(_library(), [], mood="calm")
    intent = plan_play_intent(_library(), [], mood="calm")
    assert result["ok"] is True
    assert result["playback_started"] is False
    assert result["history_written"] is False
    assert intent["playback_authorized"] is False


def test_invalid_track_abstains() -> None:
    assert validate_track({"artist": "", "album": "", "genre": ""})["ok"] is False


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "music_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib", "random", "urllib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["optional"] is True
    assert result["playback_authorized"] is False
