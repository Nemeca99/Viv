"""Foundation bridge to Viv voice_core (optional GPU translator)."""
from __future__ import annotations

import sys
from pathlib import Path

_VIV = Path(__file__).resolve().parents[2]
if str(_VIV) not in sys.path:
    sys.path.insert(0, str(_VIV))

from voice_core.client import server_reachable, speak_completion, voice_endpoint  # noqa: E402
from voice_core.intent_packet import build_intent_packet, packet_to_messages  # noqa: E402
from voice_core.speak import VOICE_EVENTS_PATH, speak, speak_status  # noqa: E402

__all__ = [
    "VOICE_EVENTS_PATH",
    "build_intent_packet",
    "packet_to_messages",
    "server_reachable",
    "speak",
    "speak_completion",
    "speak_status",
    "voice_endpoint",
]
