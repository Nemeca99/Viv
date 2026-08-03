"""Test the CPU semantic runtime authority boundary without loading a model."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_semantic_runtime import semantic_compare_verified  # noqa: E402


def main() -> int:
    verified = {"state": "VERIFIED", "errors": []}
    with patch("lib.cpu_semantic_runtime.verify_catalog", return_value=verified), patch(
        "lib.knowledge_semantic_backend.semantic_compare",
        return_value={"ok": True, "state": "SEMANTIC_SCORE", "score": 0.8123, "backend": "ollama_viv_embed"},
    ):
        result = semantic_compare_verified("retrieval", "semantic retrieval")
    assert result["ok"] is True, result
    assert result["specialist_id"] == "semantic_geometry", result
    assert result["specialist_output_is_authority"] is False, result
    assert result["authority"] == "deterministic_cpu_aios_and_rust_security", result

    with patch("lib.cpu_semantic_runtime.verify_catalog", return_value={"state": "ABSTAIN", "errors": ["hash_mismatch"]}):
        denied = semantic_compare_verified("a", "b")
    assert denied["state"] == "INCONCLUSIVE" and denied["ok"] is False, denied
    assert denied["reason"] == "cpu_catalog_not_verified", denied
    print("CPU_SEMANTIC_RUNTIME_PASS verified_observation=true fail_closed=true authority_cpu=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
