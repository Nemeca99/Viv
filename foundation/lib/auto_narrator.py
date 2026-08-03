"""Template narrator hook for Viv automaton pulses."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from lib.paths import AUTOMATION_ROOT
from lib.security_membrane import filter_egress

RID_BODY = AUTOMATION_ROOT / "3_body"
RID_LOGS = RID_BODY / "rid_logs"
NARRATOR_JSONL = RID_LOGS / "narrator.jsonl"
NARRATOR_TEXT = RID_LOGS / "narrator.txt"
SEEN_PATH = RID_LOGS / "narrator_seen.json"


def _body_on_path() -> None:
    body = str(RID_BODY)
    if body not in sys.path:
        sys.path.insert(0, body)


def narrate_latest(*, print_line: bool = True, s_n: float | None = None) -> dict[str, Any]:
    _body_on_path()
    from rid_event_schema import iter_events
    from rid_narrator import append_lines, load_seen, render_events, save_seen

    events = iter_events(RID_LOGS / "events.jsonl")
    if not events:
        return {"rendered": 0, "line": None}
    tail = events[-1:]
    seen = load_seen(SEEN_PATH)
    lines = render_events(tail, seen=seen, min_severity="info")
    count = append_lines(NARRATOR_JSONL, NARRATOR_TEXT, lines)
    for line in lines:
        seen.add(line.event_id)
    save_seen(SEEN_PATH, seen)
    text = lines[-1].line if lines else None
    if text and s_n is not None:
        filtered, _ev = filter_egress(text, s_n)
        text = filtered
    if print_line and text:
        print(text)
    return {"rendered": count, "line": text, "out_text": str(NARRATOR_TEXT)}
