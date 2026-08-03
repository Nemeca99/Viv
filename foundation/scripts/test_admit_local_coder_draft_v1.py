#!/usr/bin/env python3
"""Pure admission-boundary tests; no source write or security action."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))

from admit_local_coder_draft_v1 import build_admission_plan  # noqa: E402


def main() -> int:
    draft = FOUNDATION / "artifacts" / "auto" / "agentic" / "local_coder_marker_smoke_v1" / "draft_hash_helper_with_contract.txt"
    target = FOUNDATION / "scripts" / "__admission_test_never_written__.py"
    assert draft.is_file()
    assert not target.exists()
    digest = hashlib.sha256(draft.read_bytes()).hexdigest()

    try:
        build_admission_plan(draft, target, digest, False)
    except PermissionError as exc:
        assert "foreman_approval_required" in str(exc)
    else:
        raise AssertionError("approval_gate_not_enforced")

    plan = build_admission_plan(draft, target, digest, True)
    assert plan["foreman_approved"] is True
    assert plan["review"]["syntax_pass"] is True
    assert plan["review"]["risk_findings"] == []

    try:
        build_admission_plan(draft, FOUNDATION / "scripts" / "__admission_hash_test__.py", "0" * 64, True)
    except ValueError as exc:
        assert "draft_hash_mismatch" in str(exc)
    else:
        raise AssertionError("hash_gate_not_enforced")
    assert not target.exists()
    print("ok: draft admission approval, hash, review, and target gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
