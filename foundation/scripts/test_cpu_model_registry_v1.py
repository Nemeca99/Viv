"""Verify CPU specialist catalog integrity and authority boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

VIV = Path(__file__).resolve().parents[2]
FOUNDATION = VIV / "foundation"
for path in (VIV, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_model_registry import resolve_verified_model, verify_catalog  # noqa: E402


def main() -> int:
    result = verify_catalog()
    assert result["state"] == "VERIFIED", result
    assert len(result["specialists"]) == 3, result
    assert result["authority"] == "deterministic_cpu_aios_and_rust_security", result
    assert all(row["expected"] == row["actual"] for row in result["specialists"]), result
    semantic = resolve_verified_model("semantic_geometry")
    assert semantic.name == "bert-base-uncased-Q8_0.gguf", semantic
    print("CPU_MODEL_REGISTRY_PASS specialists=3 hashes=verified authority=deterministic_cpu_aios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
