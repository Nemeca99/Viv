"""CPU tool-authority gate: GPU may request tools; CPU approves and executes.

Doctrine:
  - GPU mouth never executes tools or mints authority.
  - GPU (or operator-via-mouth) may submit a structured tool request.
  - CPU reviews allowlist + inputs; on approve, CPU runs the tool and returns
    the result for mouth render.
  - Example: GPU requests calculator/uml_invoke with expression → CPU checks →
    CPU evaluates → answer returned on the evidence path.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Mapping

AUTHORITY_VERSION = "cpu_tool_authority_v1"
ALLOWED_TOOLS = frozenset({"calculator", "uml_invoke"})
ALLOWED_REQUEST_SOURCES = frozenset(
    {
        "gpu_mouth",
        "gpu_mouth_request",
        "operator",
        "operator_via_mouth",
        "cpu",  # CPU may self-propose for deterministic solve ingress; still reviewed
    }
)
_MAX_EXPR_LEN = 120
_EXPR_OK = re.compile(r"^[\d\s\(\)\[\]\{\}\+\-\*/\^\.,πpiφphiτtau]+$", flags=re.I)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_tool_request(
    *,
    tool: str,
    inputs: Mapping[str, Any],
    source: str = "gpu_mouth_request",
    request_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build a structured tool request (GPU proposes; CPU has not approved yet)."""
    rid = request_id or hashlib.sha256(
        f"{tool}|{json.dumps(dict(inputs), sort_keys=True, default=str)}|{time.time_ns()}".encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return {
        "schema_version": AUTHORITY_VERSION,
        "request_id": rid,
        "source": str(source),
        "tool": str(tool),
        "inputs": dict(inputs),
        "status": "proposed",
        "authority": "gpu_may_request_only",
        "cpu_approved": False,
        "note": note,
        "at": _utc(),
    }


def review_tool_request(request: Mapping[str, Any] | None) -> dict[str, Any]:
    """CPU review — fail closed. Does not execute."""
    if not isinstance(request, Mapping):
        return {
            "allowed": False,
            "status": "denied",
            "reason": "request_not_mapping",
            "authority": "cpu",
            "at": _utc(),
        }
    source = str(request.get("source") or "")
    tool = str(request.get("tool") or "")
    inputs = request.get("inputs")
    if source not in ALLOWED_REQUEST_SOURCES:
        return {
            "allowed": False,
            "status": "denied",
            "reason": f"source_not_allowed:{source}",
            "authority": "cpu",
            "request_id": request.get("request_id"),
            "at": _utc(),
        }
    if tool not in ALLOWED_TOOLS:
        return {
            "allowed": False,
            "status": "denied",
            "reason": f"tool_not_allowlisted:{tool}",
            "authority": "cpu",
            "request_id": request.get("request_id"),
            "at": _utc(),
        }
    if request.get("cpu_approved") is True and source.startswith("gpu"):
        # GPU cannot self-approve.
        return {
            "allowed": False,
            "status": "denied",
            "reason": "gpu_cannot_self_approve",
            "authority": "cpu",
            "request_id": request.get("request_id"),
            "at": _utc(),
        }
    if not isinstance(inputs, Mapping):
        return {
            "allowed": False,
            "status": "denied",
            "reason": "inputs_not_mapping",
            "authority": "cpu",
            "request_id": request.get("request_id"),
            "at": _utc(),
        }
    if tool in {"calculator", "uml_invoke"}:
        expr = str(inputs.get("expression") or inputs.get("expr") or "").strip()
        if not expr:
            return {
                "allowed": False,
                "status": "denied",
                "reason": "missing_expression",
                "authority": "cpu",
                "request_id": request.get("request_id"),
                "at": _utc(),
            }
        if len(expr) > _MAX_EXPR_LEN:
            return {
                "allowed": False,
                "status": "denied",
                "reason": "expression_too_long",
                "authority": "cpu",
                "request_id": request.get("request_id"),
                "at": _utc(),
            }
        if not _EXPR_OK.match(expr):
            return {
                "allowed": False,
                "status": "denied",
                "reason": "expression_charset_denied",
                "authority": "cpu",
                "request_id": request.get("request_id"),
                "at": _utc(),
            }
    return {
        "allowed": True,
        "status": "approved",
        "reason": "cpu_allowlist_and_inputs_ok",
        "authority": "cpu",
        "tool": tool,
        "request_id": request.get("request_id"),
        "approved_expression": str(
            (inputs or {}).get("expression") or (inputs or {}).get("expr") or ""
        ).strip()
        if tool in {"calculator", "uml_invoke"}
        else None,
        "at": _utc(),
    }


def execute_approved_tool(
    request: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """CPU executes only after approval. GPU never enters this function as actor."""
    if not approval.get("allowed"):
        return {
            "ok": False,
            "executed": False,
            "reason": "not_approved",
            "approval": dict(approval),
            "authority": "cpu",
            "at": _utc(),
        }
    tool = str(approval.get("tool") or request.get("tool") or "")
    if tool not in {"calculator", "uml_invoke"}:
        return {
            "ok": False,
            "executed": False,
            "reason": f"execute_unsupported_tool:{tool}",
            "authority": "cpu",
            "at": _utc(),
        }
    expr = str(approval.get("approved_expression") or "").strip()
    from lib.aios_adapter_uml_invoke import invoke_uml

    result = invoke_uml(
        expr,
        source="cpu_after_approval",
        query=str(request.get("note") or request.get("query") or expr),
    )
    # Stamp authority relationship onto the persisted invoke receipt for later asks.
    if isinstance(result, dict):
        result = {
            **result,
            "tool_request_source": str(request.get("source") or ""),
            "cpu_tool_approved": True,
            "cpu_tool_executed": True,
            "gpu_executed_tool": False,
            "request_id": request.get("request_id"),
        }
        try:
            from lib.aios_adapter_uml_invoke import _persist_last

            _persist_last(result)
        except Exception:  # noqa: BLE001
            pass
    return {
        "ok": bool(result.get("ok")),
        "executed": True,
        "tool": tool,
        "request_id": request.get("request_id"),
        "approval": {
            "allowed": True,
            "reason": approval.get("reason"),
            "at": approval.get("at"),
        },
        "result": result,
        "authority": "cpu",
        "gpu_executed": False,
        "at": _utc(),
    }


def handle_tool_request(request: Mapping[str, Any] | None) -> dict[str, Any]:
    """Full CPU path: review → (maybe) execute → evidence bundle."""
    approval = review_tool_request(request)
    if not approval.get("allowed"):
        return {
            "ok": False,
            "executed": False,
            "request": dict(request or {}),
            "approval": approval,
            "authority": "cpu",
            "at": _utc(),
        }
    executed = execute_approved_tool(dict(request or {}), approval)
    return {
        "ok": bool(executed.get("ok")),
        "executed": bool(executed.get("executed")),
        "request": dict(request or {}),
        "approval": approval,
        "execution": executed,
        "authority": "cpu",
        "at": _utc(),
    }


def propose_calculator_from_query(
    query: str,
    *,
    source: str = "operator_via_mouth",
) -> dict[str, Any] | None:
    """Build a calculator/uml_invoke request from operator text if an expression is present."""
    from lib.aios_adapter_uml_invoke import extract_expression

    expr = extract_expression(query)
    if not expr:
        return None
    return build_tool_request(
        tool="uml_invoke",
        inputs={"expression": expr},
        source=source,
        note=str(query),
    )


def parse_gpu_tool_request_from_text(text: str) -> dict[str, Any] | None:
    """Parse an optional GPU-emitted TOOL_REQUEST JSON block from draft text.

    Expected shape (single line or fenced):
      TOOL_REQUEST:{"tool":"uml_invoke","inputs":{"expression":"2+2"}}
    GPU cannot include cpu_approved=true meaningfully — review rejects self-approve.
    """
    raw = str(text or "")
    m = re.search(r"TOOL_REQUEST\s*:\s*(\{)", raw, flags=re.I | re.S)
    if not m:
        return None
    start = m.start(1)
    depth = 0
    end = None
    for i, ch in enumerate(raw[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return None
    try:
        payload = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    tool = str(payload.get("tool") or "uml_invoke")
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    if "expression" not in inputs and payload.get("expression"):
        inputs = {**inputs, "expression": payload.get("expression")}
    return build_tool_request(
        tool=tool,
        inputs=inputs,
        source="gpu_mouth_request",
        note="parsed_from_gpu_draft",
    )


__all__ = [
    "ALLOWED_REQUEST_SOURCES",
    "ALLOWED_TOOLS",
    "AUTHORITY_VERSION",
    "build_tool_request",
    "execute_approved_tool",
    "handle_tool_request",
    "parse_gpu_tool_request_from_text",
    "propose_calculator_from_query",
    "review_tool_request",
]
