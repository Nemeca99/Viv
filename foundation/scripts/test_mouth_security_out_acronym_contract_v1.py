#!/usr/bin/env python3
"""Security OUT tests for the registry-governed acronym contract."""
from __future__ import annotations

from unittest.mock import patch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from lib import security_membrane  # noqa: E402
from voice_core.acronym_registry import CANONICAL_IDENTITY_INTRO  # noqa: E402


def main() -> int:
    with patch.object(
        security_membrane,
        "egress_gate",
        return_value={"allowed": True, "stage": "security_out", "reason": "test_allow"},
    ):
        valid, valid_verdict = security_membrane.filter_egress(CANONICAL_IDENTITY_INTRO, 0.6)
        if valid != CANONICAL_IDENTITY_INTRO or not valid_verdict["allowed"]:
            raise AssertionError(f"valid_output_blocked:{valid_verdict}")
        print("PASS approved first-use expansion reaches Security OUT")

        invalid, invalid_verdict = security_membrane.filter_egress(
            "AIOS speaks through the GPU.", 0.6
        )
        if invalid != security_membrane.BLOCKED_EGRESS:
            raise AssertionError("invalid_output_not_withheld")
        if invalid_verdict.get("reason") != "acronym_contract_violation":
            raise AssertionError(f"wrong_block_reason:{invalid_verdict}")
        if invalid_verdict["acronym_contract"]["pass"]:
            raise AssertionError("invalid_output_marked_pass")
        print("PASS unexpanded approved acronyms are withheld")

        invented, invented_verdict = security_membrane.filter_egress(
            "Adaptive Intelligent Operating System (AIOS) uses XYZ.", 0.6
        )
        if invented != security_membrane.BLOCKED_EGRESS:
            raise AssertionError("unapproved_acronym_not_withheld")
        if not any(v.get("token") == "XYZ" for v in invented_verdict["acronym_contract"]["violations"]):
            raise AssertionError("unapproved_token_not_logged")
        print("PASS unapproved acronym is withheld and logged")

    print("ALL_PASS 3/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
