"""Viv voice_core — optional GPU translator; CPU owns intent; soft-fail silent."""
from voice_core.client import server_reachable, speak_completion, voice_endpoint
from voice_core.intent_packet import build_intent_packet, packet_to_messages
from voice_core.speak import speak, speak_status
from lib.triad_kernel import TRIAD_CONTRACT_VERSION

__all__ = [
    "build_intent_packet",
    "packet_to_messages",
    "server_reachable",
    "speak",
    "speak_completion",
    "speak_status",
    "voice_endpoint",
    "TRIAD_CONTRACT_VERSION",
]
