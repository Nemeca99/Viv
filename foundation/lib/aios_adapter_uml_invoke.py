"""UML invoke adapter — bind skeleton bus ``uml_invoke`` to real Nested-PEMDAS eval.

Bounded: evaluate + verify one expression, return replayable evidence.
Does not start AIOS, does not invent bindings, does not claim plant health.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADAPTER_ID = "aios_adapter_uml_invoke_v1"
_LAST_INVOKE: dict[str, Any] | None = None
_LAST_INVOKE_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "auto"
    / "uml_invoke"
    / "LAST_INVOKE.json"
)

_SOLVE_PREFIX = re.compile(
    r"^\s*(?:viv[,:]?\s*)?(?:please\s+)?(?:solve|compute|evaluate|calc(?:ulate)?)\s*[:=]?\s*",
    flags=re.I,
)
_EXPR_ONLY = re.compile(
    r"^\s*[\d\(\)\[\]\{\}\+\-\*/\^\.\s,πpiφphi]+(?:[\d\(\)\[\]\{\}\+\-\*/\^\.\s,πpiφphi]+)*\s*$",
    flags=re.I,
)


def _persist_last(out: dict[str, Any]) -> None:
    global _LAST_INVOKE
    _LAST_INVOKE = out
    try:
        _LAST_INVOKE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAST_INVOKE_PATH.write_text(
            json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 — persistence must not break invoke
        pass


def last_invoke() -> dict[str, Any] | None:
    global _LAST_INVOKE
    if isinstance(_LAST_INVOKE, dict):
        return dict(_LAST_INVOKE)
    try:
        if _LAST_INVOKE_PATH.is_file():
            data = json.loads(_LAST_INVOKE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _LAST_INVOKE = data
                return dict(data)
    except Exception:  # noqa: BLE001
        return None
    return None


def extract_expression(query: str) -> str | None:
    """Pull a bounded arithmetic / UML expression from operator text."""
    text = str(query or "").strip()
    if not text:
        return None
    stripped = _SOLVE_PREFIX.sub("", text).strip().rstrip("?.!")
    if not stripped:
        return None
    # Prefer explicit solve/compute forms; also allow bare expr turns.
    if _SOLVE_PREFIX.search(text) or _EXPR_ONLY.match(stripped):
        # Reject prose leftovers.
        if re.search(r"[A-Za-z]{4,}", stripped) and not re.search(
            r"\b(?:pi|phi|tau)\b", stripped, flags=re.I
        ):
            return None
        return stripped
    return None


def invoke_uml(
    expr: str,
    *,
    source: str = "cpu",
    query: str | None = None,
) -> dict[str, Any]:
    """Evaluate + verify ``expr`` via uml_engine; return evidence receipt."""
    global _LAST_INVOKE
    t0 = time.perf_counter()
    expression = str(expr or "").strip()
    if not expression:
        out = {
            "ok": False,
            "adapter": ADAPTER_ID,
            "uml_invoked": False,
            "reason": "empty_expression",
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        _persist_last(out)
        return out

    try:
        from lib import uml_engine as uml
    except Exception as exc:  # noqa: BLE001
        out = {
            "ok": False,
            "adapter": ADAPTER_ID,
            "uml_invoked": False,
            "reason": f"uml_engine_import:{type(exc).__name__}",
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        _persist_last(out)
        return out

    try:
        value, node, notation, trace = uml.evaluate(expression)
        ok_v, report = uml.verify(expression)
        uml_form = uml.to_uml(node)
        std_form = uml.to_std(node)
        value_s = uml.fmt(value)
    except Exception as exc:  # noqa: BLE001 — fail closed with evidence
        out = {
            "ok": False,
            "adapter": ADAPTER_ID,
            "uml_invoked": True,
            "expression": expression,
            "reason": f"eval_error:{type(exc).__name__}:{exc}",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source": source,
            "query": query,
        }
        _persist_last(out)
        return out

    digest = hashlib.sha256(
        f"{expression}|{notation}|{value_s}|{uml_form}|{std_form}|{ok_v}".encode("utf-8")
    ).hexdigest()
    out = {
        "ok": bool(ok_v),
        "adapter": ADAPTER_ID,
        "uml_invoked": True,
        "expression": expression,
        "notation": notation,
        "value": value_s,
        "verify_ok": bool(ok_v),
        "verify_report": str(report)[:800],
        "uml_form": str(uml_form)[:400],
        "std_form": str(std_form)[:400],
        "trace_steps": len(trace) if isinstance(trace, list) else 0,
        "evidence_sha256": digest,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": source,
        "query": query,
        "authority": "cpu_uml_engine",
    }
    _persist_last(out)
    return out


def cpu_plan(**_kwargs: Any) -> dict[str, Any]:
    """Skeleton/plan surface for bus inventory."""
    last = last_invoke()
    return {
        "status": "partial",
        "build_state": "PARTIAL",
        "adapter": ADAPTER_ID,
        "plan_only": True,
        "uml_invoke_bound": True,
        "last_invoke_ok": None if last is None else bool(last.get("ok")),
        "last_evidence_sha256": None if last is None else last.get("evidence_sha256"),
        "note": "uml_invoke bound to uml_engine.evaluate+verify; speak can request solve turns.",
    }


def uml_invoke_slot(
    expr: str | None = None,
    *,
    query: str | None = None,
    source: str = "cpu",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Bus callable for ``uml_invoke``."""
    expression = expr
    if not expression and query:
        expression = extract_expression(query)
    if not expression:
        return {
            "ok": False,
            "adapter": ADAPTER_ID,
            "uml_invoked": False,
            "reason": "no_expression",
            "query": query,
        }
    return invoke_uml(expression, source=source, query=query)


__all__ = [
    "ADAPTER_ID",
    "cpu_plan",
    "extract_expression",
    "invoke_uml",
    "last_invoke",
    "uml_invoke_slot",
]
