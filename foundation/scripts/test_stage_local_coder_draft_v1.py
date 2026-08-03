#!/usr/bin/env python3
"""Pure staging-boundary tests; no sandbox write or execution."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))

from stage_local_coder_draft_v1 import SANDBOX_CODE, build_stage_plan  # noqa: E402


def main() -> int:
    draft = FOUNDATION / "artifacts" / "auto" / "agentic" / "local_coder_marker_smoke_v1" / "draft_hash_helper_with_contract.txt"
    target = SANDBOX_CODE / "__stage_test_never_written__.txt"
    assert draft.is_file()
    assert SANDBOX_CODE.is_dir()
    assert not target.exists()
    digest = hashlib.sha256(draft.read_bytes()).hexdigest()
    try:
        build_stage_plan(draft, target, digest, False, True)
    except PermissionError as exc:
        assert "foreman_approval_required" in str(exc)
    else:
        raise AssertionError("approval_gate_not_enforced")
    try:
        build_stage_plan(draft, target, digest, True, False)
    except PermissionError as exc:
        assert "semantic_review_confirmation_required" in str(exc)
    else:
        raise AssertionError("semantic_review_gate_not_enforced")
    plan = build_stage_plan(draft, target, digest, True, True)
    assert plan["foreman_approved"] is True
    assert plan["semantic_reviewed"] is True
    assert plan["execution_performed"] is False
    assert plan["foundation_source_mutated"] is False
    assert plan["security_membrane_required"] is True
    assert len(plan["staged_sha256"]) == 64
    assert "source_as_txt" in plan["staged_content"]
    assert plan["review"]["risk_findings"] == []
    try:
        build_stage_plan(draft, SANDBOX_CODE / "bad.py", digest, True, True)
    except ValueError as exc:
        assert "must_be_txt" in str(exc)
    else:
        raise AssertionError("sandbox_extension_gate_not_enforced")
    assert not target.exists()
    print("ok: sandbox staging approval, hash, review, extension, and no-execution gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
