#!/usr/bin/env python3
"""Explicit foreman admission for a reviewed local-coder draft.

This is deliberately separate from the local-coder queue. It never runs model
output and never overwrites an existing source file. Admission requires an
exact draft hash, an explicit foreman approval flag, a clean static review,
and a Rust security-membrane write verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
ARTIFACTS = FOUNDATION / "artifacts"
ALLOWED_TARGET_ROOTS = (FOUNDATION / "scripts", FOUNDATION / "lib")

if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from review_local_coder_drafts_v1 import extract_python, review_file  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inside(path: Path, roots: tuple[Path, ...]) -> Path:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(f"path_outside_allowed_roots:{path}")


def build_admission_plan(draft: Path, target: Path, expected_sha256: str, foreman_approved: bool) -> dict[str, Any]:
    draft = inside(draft, (ARTIFACTS,))
    target = inside(target, ALLOWED_TARGET_ROOTS)
    if not draft.is_file():
        raise FileNotFoundError(f"draft_missing:{draft}")
    if target.suffix.lower() != ".py":
        raise ValueError(f"target_must_be_python:{target}")
    if target.exists():
        raise FileExistsError(f"refuse_to_overwrite:{target}")
    observed_sha256 = digest(draft)
    if observed_sha256.lower() != expected_sha256.lower():
        raise ValueError(f"draft_hash_mismatch:expected={expected_sha256};observed={observed_sha256}")
    if not foreman_approved:
        raise PermissionError("foreman_approval_required")
    review = review_file(draft)
    if not review["syntax_pass"] or review["risk_findings"]:
        raise ValueError(f"draft_static_review_failed:{json.dumps(review, sort_keys=True)}")
    source = extract_python(draft.read_text(encoding="utf-8"))
    if not source.strip():
        raise ValueError("draft_python_source_empty")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"target_parent_missing:{target.parent}")
    return {
        "schema_version": "local_coder_draft_admission_plan_v1",
        "draft": str(draft).replace("\\", "/"),
        "draft_sha256": observed_sha256,
        "target": str(target).replace("\\", "/"),
        "source_bytes": len(source.encode("utf-8")),
        "review": review,
        "foreman_approved": True,
    }


def security_context() -> tuple[Any, float]:
    from lib.master_rid import load_master_rid
    from lib.security_membrane import require_membrane, tool_gate

    missing = require_membrane()
    if missing is not None:
        raise PermissionError(f"security_membrane:{missing.get('reason')}")
    return tool_gate, float(load_master_rid().master_s_n)


def secure_write(path: Path, content: str, security: tuple[Any, float]) -> None:
    tool_gate, s_n = security
    verdict = tool_gate("write_file", {"path": str(path).replace("\\", "/"), "content": content}, s_n)
    if not verdict.get("allowed"):
        raise PermissionError(f"tool_gate_denied:{verdict}")
    path.write_text(content, encoding="utf-8", newline="\n")


def admit(draft: Path, target: Path, expected_sha256: str, *, foreman_approved: bool) -> dict[str, Any]:
    plan = build_admission_plan(draft, target, expected_sha256, foreman_approved)
    report_path = Path(plan["draft"]).parent / "ADMISSION_REPORT.json"
    if report_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{report_path}")
    source = extract_python(Path(plan["draft"]).read_text(encoding="utf-8"))
    security = security_context()
    secure_write(Path(plan["target"]), source, security)
    report = {
        **plan,
        "status": "DRAFT_ADMITTED_TO_SOURCE",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    secure_write(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n", security)
    return report


def write_failure_report(draft: Path, target: Path, error: Exception) -> None:
    """Best-effort artifact-only failure receipt; never masks the original error."""
    try:
        draft_path = inside(draft, (ARTIFACTS,))
        report_path = draft_path.parent / "ADMISSION_FAILURE.json"
        if report_path.exists():
            return
        security = security_context()
        report = {
            "schema_version": "local_coder_draft_admission_failure_v1",
            "status": "DRAFT_ADMISSION_REFUSED",
            "draft": str(draft_path).replace("\\", "/"),
            "target": str(target).replace("\\", "/"),
            "error": f"{type(error).__name__}:{error}",
            "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        secure_write(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n", security)
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Admit one explicitly approved reviewed coder draft")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--foreman-approved", action="store_true")
    args = parser.parse_args()
    try:
        report = admit(args.draft, args.target, args.expected_sha256, foreman_approved=args.foreman_approved)
    except Exception as exc:
        write_failure_report(args.draft, args.target, exc)
        print(json.dumps({"ok": False, "status": "DRAFT_ADMISSION_REFUSED", "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "status": report["status"], "draft_sha256": report["draft_sha256"], "target": report["target"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
