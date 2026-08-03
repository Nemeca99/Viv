"""Governed CPU semantic-search runtime seam.

The specialist model supplies a similarity observation. The deterministic
AIOS remains the authority for admission, conflict handling, and action.
"""
from __future__ import annotations

from typing import Any

from lib.cpu_model_registry import verify_catalog


def semantic_compare_verified(left: str, right: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """Compare two texts only after CPU specialist identity is verified."""
    catalog = verify_catalog()
    base: dict[str, Any] = {
        "authority": "deterministic_cpu_aios_and_rust_security",
        "specialist_id": "semantic_geometry",
        "specialist_output_is_authority": False,
        "catalog_state": catalog.get("state"),
        "catalog_errors": catalog.get("errors") or [],
    }
    if catalog.get("state") != "VERIFIED":
        return {**base, "ok": False, "state": "INCONCLUSIVE", "reason": "cpu_catalog_not_verified"}
    try:
        from lib.knowledge_semantic_backend import semantic_compare

        result = semantic_compare(left, right, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001 — optional runtime must fail closed
        return {**base, "ok": False, "state": "INCONCLUSIVE", "reason": f"semantic_runtime:{type(exc).__name__}:{exc}"}
    if not result.get("ok"):
        return {**base, **result, "ok": False, "state": "INCONCLUSIVE"}
    return {
        **base,
        **result,
        "state": "SEMANTIC_SCORE",
        "backend": result.get("backend") or "cpu_specialist_runtime",
        "specialist_id": "semantic_geometry",
    }
