"""Rust security gate for CARMA writes."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1] / "foundation"
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.master_rid import load_master_rid  # noqa: E402
from lib.triad_kernel import (  # noqa: E402
    TriadDenied,
    TriadEnvelope,
    dispatch,
    open_context,
)


def current_s_n() -> float:
    try:
        return float(load_master_rid().master_s_n)
    except Exception:
        return 0.0


def gated_write(path: str, content: str, s_n: float | None = None) -> tuple[bool, str, dict[str, Any]]:
    sn = float(s_n if s_n is not None else current_s_n())
    target = Path(path)
    params = {"path": path, "content": content}
    try:
        context = open_context(
            TriadEnvelope.build(
                actor="semantic_memory",
                source="memory_core",
                target="carma",
                action="MEMORY_WRITE",
                payload=params,
                s_n=sn,
            )
        )

        def _write() -> str:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return str(target)

        _, receipt = dispatch(
            context,
            operation="memory.write",
            params=params,
            handler=_write,
            tool_name="write_file",
        )
        return True, "write_ok", receipt.to_dict()
    except TriadDenied as exc:
        verdict = {
            "allowed": False,
            "reason": exc.reason,
            "evidence": exc.evidence,
        }
        return False, exc.reason, verdict
