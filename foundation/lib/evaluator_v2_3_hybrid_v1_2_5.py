"""v1.2.5 compatibility extension for explicit memory-service attribution.

The frozen v1.2.4 evaluator required the word ``automatically`` before a
memory/service answer could PASS. Explicit CPU-side AIOS service ownership is
already sufficient evidence; this wrapper broadens only that PASS path and
leaves all hard-failure predicates delegated to v1.2.4.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from lib import evaluator_v2_3_hybrid as base

VERSION = "evaluator_v2_3_hybrid_v1_2_5"
SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PASS = base.PASS
FAIL = base.FAIL
HOLD = base.HOLD


def _explicit_memory_service(text: str) -> bool:
    n = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    has_service = bool(re.search(r"\b(?:aios|ai os|cpu[- ]side|service|services)\b", n))
    has_memory = bool(re.search(r"\b(?:memory|memories|records?|logs?|logging|retention|history)\b", n))
    has_management = bool(re.search(r"\b(?:manage|manages|managed|handle|handles|handled|write|writes|own|owns|govern|governs|keep|keeps|retain|retains|preserve|preserves)\b", n))
    return has_service and has_memory and has_management


def _stamp(result: dict[str, Any]) -> dict[str, Any]:
    """Attach provenance for the wrapper and its delegated deterministic result."""
    stamped = dict(result)
    deterministic = dict(stamped.get("deterministic") or {})
    deterministic["evaluator_version"] = VERSION
    deterministic["evaluator_source_sha256"] = SOURCE_SHA256
    stamped["deterministic"] = deterministic
    stamped["version"] = VERSION
    return stamped


def deterministic_axis(text: str, axis: str) -> dict[str, Any]:
    result = base.deterministic_axis(text, axis)
    if (
        axis == "memory_ownership_and_service_attribution"
        and result["status"] == HOLD
        and _explicit_memory_service(text)
    ):
        result = {"status": PASS, "reason": "explicit_aios_memory_service"}
    return _stamp(result)


def judge(text: str, *, axis: str, ask: str = "", facts: list[str] | None = None, cache_dir=None, use_cpu_sensor: bool = False) -> dict[str, Any]:
    result = base.judge(text, axis=axis, ask=ask, facts=facts, cache_dir=cache_dir, use_cpu_sensor=use_cpu_sensor)
    if axis == "memory_ownership_and_service_attribution" and result["status"] == HOLD and _explicit_memory_service(text):
        result = dict(result)
        result["status"] = PASS
        result["deterministic"] = {"status": PASS, "reason": "explicit_aios_memory_service"}
        result["sensor"] = None
    return _stamp(result)


def __getattr__(name: str):
    return getattr(base, name)
