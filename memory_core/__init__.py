"""Viv plain-text CARMA — past lives in files, not vectors."""
from memory_core.semantic_memory import SemanticMemory, append_live_note, remember, retrieve, status
from lib.triad_kernel import TRIAD_CONTRACT_VERSION

__all__ = [
    "SemanticMemory",
    "append_live_note",
    "remember",
    "retrieve",
    "status",
    "TRIAD_CONTRACT_VERSION",
]
