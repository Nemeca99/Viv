"""Hash-verified registry for CPU-resident specialist models."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT


CPU_ROOT = FOUNDATION_ROOT / "models" / "cpu"
CATALOG_PATH = CPU_ROOT / "CPU_MODEL_CATALOG.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def verify_catalog() -> dict[str, Any]:
    """Verify every catalogued weight before a caller loads or uses it."""
    try:
        catalog = load_catalog()
    except (OSError, json.JSONDecodeError) as exc:
        return {"state": "ABSTAIN", "reason": f"catalog_unreadable:{exc}", "specialists": []}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in catalog.get("specialists") or []:
        name = str(item.get("file") or "")
        path = (CPU_ROOT / name).resolve()
        try:
            path.relative_to(CPU_ROOT.resolve())
        except ValueError:
            errors.append(f"outside_cpu_root:{name}")
            continue
        if not path.is_file():
            errors.append(f"missing:{name}")
            continue
        actual = _sha256(path)
        expected = str(item.get("sha256") or "").upper()
        rows.append({"id": item.get("id"), "path": path.as_posix(), "expected": expected, "actual": actual})
        if actual != expected:
            errors.append(f"hash_mismatch:{name}")
    return {
        "state": "VERIFIED" if rows and not errors else "ABSTAIN",
        "authority": catalog.get("policy", {}).get("decision_authority"),
        "specialists": rows,
        "errors": errors,
    }


def resolve_verified_model(specialist_id: str) -> Path:
    """Return a model path only when the catalog and requested role verify."""
    catalog = load_catalog()
    item = next((row for row in catalog.get("specialists") or [] if row.get("id") == specialist_id), None)
    if item is None:
        raise ValueError(f"unknown_cpu_specialist:{specialist_id}")
    result = verify_catalog()
    if result.get("state") != "VERIFIED":
        raise RuntimeError(f"cpu_specialist_catalog_not_verified:{result.get('errors')}")
    return (CPU_ROOT / str(item["file"])).resolve()
