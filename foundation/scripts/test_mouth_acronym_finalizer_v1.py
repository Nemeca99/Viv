"""CPU-only integration checks for the spoken acronym boundary."""
from __future__ import annotations

from types import SimpleNamespace
import importlib
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.triad_kernel import TriadEnvelope, open_context


def main() -> int:
    speak = importlib.import_module("voice_core.speak")
    logs: list[dict] = []

    # Keep this test offline and side-effect free. The real finalizer logic is
    # exercised; only event persistence, memory notes, and egress are stubbed.
    original = {
        "log": speak._log_voice_event,
        "note": speak._optional_carma_spoke_note,
        "emit": speak.emit,
        "deterministic": speak.deterministic_speak,
    }
    try:
        speak._log_voice_event = lambda row: logs.append(row)
        speak._optional_carma_spoke_note = lambda chars, silent: None
        speak.emit = lambda context, result: (
            result,
            SimpleNamespace(allowed=True, to_dict=lambda: {"allowed": True}),
        )
        speak.deterministic_speak = lambda packet: (
            "CPU fallback speaks only measured facts."
        )

        packet = {"s_n": 0.6, "status": "ACTIVE", "facts": [], "tone": "calm"}
        context = open_context(
            TriadEnvelope.build(
                actor="test",
                source="acronym_finalizer_test",
                target="gpu_mouth",
                action="SPEAK",
                payload={"test": True},
                s_n=0.6,
            )
        )
        cases = [
            (
                "AIOS speaks through the GPU.",
                "Adaptive Intelligent Operating System (AIOS) speaks through the Graphics Processing Unit (GPU).",
                False,
            ),
            (
                "AIOSkynet is my identity.",
                "Central Processing Unit (CPU) fallback speaks only measured facts.",
                True,
            ),
            (
                "Adaptive Intelligent Operating System (AIOS) speaks through the Graphics Processing Unit (GPU).",
                "Adaptive Intelligent Operating System (AIOS) speaks through the Graphics Processing Unit (GPU).",
                False,
            ),
        ]
        for raw, expected, regenerated in cases:
            result = speak._finalize_spoken(
                query="test",
                packet=packet,
                raw_text=raw,
                voice_source="test",
                model="test",
                s_n=0.6,
                triad_context=context,
            )
            row = logs[-1]
            assert result["text"] == expected
            assert row["acronym_contract"]["pass"] is True
            assert row["acronym_contract"]["regenerated"] is regenerated
        print("CPU_FINALIZER_INTEGRATION_PASS 3/3")
        return 0
    finally:
        speak._log_voice_event = original["log"]
        speak._optional_carma_spoke_note = original["note"]
        speak.emit = original["emit"]
        speak.deterministic_speak = original["deterministic"]


if __name__ == "__main__":
    raise SystemExit(main())
