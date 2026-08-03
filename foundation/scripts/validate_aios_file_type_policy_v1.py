#!/usr/bin/env python3
"""Validate the AIOS implementation source-extension boundary."""
from __future__ import annotations

import json
import sys
from fnmatch import fnmatch
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
POLICY_PATH = FOUNDATION / "artifacts/auto/agentic/AIOS_FILE_TYPE_POLICY.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate(policy: dict | None = None) -> dict:
    policy = policy or load_policy()
    allowed = {str(ext).lower() for ext in policy["primary_implementation_extensions"]}
    excluded = tuple(str(item) for item in policy.get("non_implementation_globs", ()))
    findings: list[str] = []
    checked: list[str] = []
    extension_counts: dict[str, int] = {}
    for relative_root in policy["implementation_roots"]:
        root = REPO / relative_root
        if not root.is_dir():
            findings.append(f"missing_implementation_root:{relative_root}")
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name == "__pycache__":
                continue
            if any(part == "__pycache__" for part in path.parts):
                continue
            suffix = path.suffix.lower()
            extension_counts[suffix or "<none>"] = extension_counts.get(suffix or "<none>", 0) + 1
            checked.append(str(path.relative_to(REPO)).replace("\\", "/"))
            relative = str(path.relative_to(REPO)).replace("\\", "/")
            if any(fnmatch(relative, pattern) for pattern in excluded):
                continue
            if suffix not in allowed:
                findings.append(f"non_primary_source_extension:{relative}")
    return {
        "schema_version": "aios_file_type_policy_validation_v1",
        "status": "PASS" if not findings else "FAIL",
        "checked_files": len(checked),
        "primary_extensions": sorted(allowed),
        "non_implementation_globs": list(excluded),
        "extension_counts": dict(sorted(extension_counts.items())),
        "findings": findings,
        "policy": str(POLICY_PATH.relative_to(REPO)).replace("\\", "/"),
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_authorized": False,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
