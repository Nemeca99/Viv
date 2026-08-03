"""Foundation bridge to Viv memory_core (CPU past layer)."""
from __future__ import annotations

import sys
from pathlib import Path

_VIV = Path(__file__).resolve().parents[2]
if str(_VIV) not in sys.path:
    sys.path.insert(0, str(_VIV))

from memory_core.semantic_memory import (  # noqa: E402
    SemanticMemory,
    append_live_note,
    remember,
    retrieve,
    status,
)

__all__ = ["SemanticMemory", "append_live_note", "remember", "retrieve", "status"]
