#!/usr/bin/env python3
"""Review and intentionally freeze triad boundary registry after drift."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.triad_architecture import (  # noqa: E402
    BOUNDARY_REGISTRY,
    freeze_boundary_registry,
    scan_architecture,
    _boundary_signature,
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    allow_changed = "--allow-changed" in sys.argv
    out_dir = AUTO_ARTIFACTS / "triad"
    out_dir.mkdir(parents=True, exist_ok=True)
    old_hash = _sha256(BOUNDARY_REGISTRY) if BOUNDARY_REGISTRY.exists() else None
    old_reg = json.loads(BOUNDARY_REGISTRY.read_text(encoding="utf-8")) if BOUNDARY_REGISTRY.exists() else {}
    old_bounds = old_reg.get("boundaries") or {}

    live = scan_architecture(compare_registry=False)
    new_bounds = _boundary_signature(live["boundary_inventory"])

    old_paths = set(old_bounds.keys())
    new_paths = set(new_bounds.keys())
    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed = sorted(
        p for p in (old_paths & new_paths) if old_bounds.get(p) != new_bounds.get(p)
    )

    review = {
        "ok": len(removed) == 0 and (len(changed) == 0 or allow_changed),
        "at": _utc(),
        "old_registry_sha256": old_hash,
        "n_added": len(added),
        "n_removed": len(removed),
        "n_changed": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
        "allow_changed": allow_changed,
        "note": (
            "Intentional freeze of current inventory after review. "
            "Unexplained removals block freeze; changed signatures require --allow-changed."
        ),
    }
    review_path = out_dir / "boundary_registry_review_latest.json"
    review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    (out_dir / "boundary_registry_review_latest.md").write_text(
        "\n".join(
            [
                "# Boundary registry review",
                "",
                f"- ok: {review['ok']}",
                f"- added: {review['n_added']}",
                f"- removed: {review['n_removed']}",
                f"- changed: {review['n_changed']}",
                f"- old_sha256: {old_hash}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if not review["ok"]:
        print(json.dumps(review, indent=2))
        return 1

    backup = BOUNDARY_REGISTRY.with_suffix(
        f".bak_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    if BOUNDARY_REGISTRY.exists():
        shutil.copy2(BOUNDARY_REGISTRY, backup)
    frozen = freeze_boundary_registry()
    new_hash = _sha256(BOUNDARY_REGISTRY)
    # verify clean
    check = scan_architecture(compare_registry=True)
    result = {
        **review,
        "backup": str(backup).replace("\\", "/"),
        "new_registry_sha256": new_hash,
        "freeze_ok": check.get("boundary_registry_error") is None,
        "frozen_modules": len(frozen.get("boundaries") or {}),
        "review_artifact": str(review_path).replace("\\", "/"),
    }
    review_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["freeze_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
