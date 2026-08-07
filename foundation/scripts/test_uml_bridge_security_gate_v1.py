#!/usr/bin/env python3
"""Contract tests: UML bridge Security IN/OUT gate (packet-scoped)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDATION = REPO / "foundation"
for path in (REPO, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.uml_bridge_security_gate import (  # noqa: E402
    FORBIDDEN_AUTHORITY_KEYS,
    SCHEMA_VERSION,
    WRITE_SCOPE,
    security_in,
    security_out,
)


def _cpu_req(**overrides):
    base = {
        "request_kind": "sealed_destination",
        "target_char": "H",
        "target_value": 42,
        "proposals": ["42", "H"],
        "prefer_policy": "cheapest_valid",
        "source": "cpu",
    }
    base.update(overrides)
    return base


def _resolved(**overrides):
    base = {
        "target_char": "H",
        "target_value": 42,
        "selected_route": "42",
        "bridge_mode": "FIELD_SCOPED_CANARY",
        "canary_only": True,
        "default_path": False,
    }
    base.update(overrides)
    return base


def main() -> int:
    # --- security_in ---------------------------------------------------------
    # 1) Explicitly none / absent → allow, may_invoke=False
    absent = security_in({"facts": ["x=1"]})
    assert absent.allowed is True
    assert absent.may_invoke_uml is False
    assert absent.reason == "explicit_none"
    assert absent.fail_closed is False
    assert absent.security_plane == "external"
    assert absent.authority_minted is False
    assert absent.stage == "security_in"
    assert "schema_version" in absent.to_dict()

    none_pkt = security_in({"uml_request": None, "facts": ["x=1"]})
    assert none_pkt.allowed is True
    assert none_pkt.may_invoke_uml is False
    assert none_pkt.reason == "explicit_none"

    # 2) Sealed CPU uml_request → allow, may_invoke=True
    sealed_pkt = {"uml_request": _cpu_req(), "facts": ["stable=1"]}
    admitted = security_in(sealed_pkt)
    assert admitted.allowed is True
    assert admitted.may_invoke_uml is True
    assert admitted.reason == "sealed_uml_request"
    assert admitted.sealed is True
    assert admitted.uml_request_source == "cpu"
    assert admitted.security_plane == "external"
    assert admitted.authority_minted is False
    d = admitted.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    assert d["allowed"] is True

    # 3) gpu-minted rejected
    gpu = security_in({"uml_request": _cpu_req(source="gpu_mouth")})
    assert gpu.allowed is False
    assert gpu.may_invoke_uml is False
    assert gpu.fail_closed is True
    assert gpu.reason == "gpu_minted_rejected"

    # 4) Ambiguity fail-closed
    bad_type = security_in({"uml_request": "not-a-mapping"})
    assert bad_type.allowed is False
    assert bad_type.reason == "ambiguous_uml_request"
    assert bad_type.fail_closed is True

    no_dest = security_in(
        {
            "uml_request": {
                "request_kind": "sealed_destination",
                "source": "cpu",
            }
        }
    )
    assert no_dest.allowed is False
    assert no_dest.fail_closed is True
    assert "ambiguous" in no_dest.reason or "missing" in no_dest.reason

    invented = security_in(
        {
            "uml_request": {
                "request_kind": "invented_binding",
                "target_char": "H",
                "source": "cpu",
            }
        }
    )
    assert invented.allowed is False
    assert invented.reason == "invented_binding"

    null_packet = security_in(None)  # type: ignore[arg-type]
    assert null_packet.allowed is False
    assert null_packet.reason == "ambiguous_packet"

    # --- security_out --------------------------------------------------------
    packet = {"facts": ["a=1"], "uml_request": _cpu_req()}
    ok_out = security_out(packet, _resolved())
    assert ok_out.allowed is True
    assert ok_out.reason == "uml_resolved_only"
    assert tuple(ok_out.write_scope) == WRITE_SCOPE
    assert ok_out.security_plane == "external"
    assert ok_out.authority_minted is False
    assert ok_out.stage == "security_out"
    assert ok_out.to_dict()["write_scope"] == ["uml_resolved"]

    # Authority tags invented → deny
    for key in ("allowed", "security_plane", "decision_authority", "authority_minted"):
        assert key in FORBIDDEN_AUTHORITY_KEYS
        bad = security_out(packet, _resolved(**{key: True}))
        assert bad.allowed is False, key
        assert bad.reason == "authority_tags_invented"
        assert bad.fail_closed is True
        assert key in bad.forbidden_keys

    # Missing / ambiguous resolved
    missing = security_out(packet, None)
    assert missing.allowed is False
    assert missing.reason == "missing_uml_resolved"

    amb = security_out(packet, ["not", "a", "map"])  # type: ignore[arg-type]
    assert amb.allowed is False
    assert amb.reason == "ambiguous_uml_resolved"

    # gpu source on resolved
    gpu_res = security_out(packet, _resolved(source="gpu_mouth"))
    assert gpu_res.allowed is False
    assert gpu_res.reason == "gpu_minted_resolved_rejected"

    # Opaque fields unchanged when attaching uml_resolved
    before = copy.deepcopy(packet)
    _ = security_out(before, _resolved())
    assert before == packet  # gate must not mutate caller packet

    # Mouth envelope fields rejected when mouth contract present
    mouthish = security_out(packet, _resolved(claims=[{"id": "c1"}], decision_digest="x"))
    if (mouthish.mouth_contract or {}).get("present"):
        assert mouthish.allowed is False
        assert mouthish.reason == "mouth_envelope_invented"

    # Receipt always has required fields
    for receipt in (absent, admitted, gpu, ok_out, bad):
        rd = receipt.to_dict()
        for req in (
            "schema_version",
            "allowed",
            "stage",
            "direction",
            "reason",
            "fail_closed",
            "security_plane",
            "authority_minted",
            "may_invoke_uml",
            "write_scope",
        ):
            assert req in rd, req

    print(
        "UML_BRIDGE_SECURITY_GATE_PASS "
        f"schema={SCHEMA_VERSION} "
        "in_none=1 in_sealed=1 in_gpu_reject=1 in_ambiguous=1 "
        "out_ok=1 out_authority_reject=1 out_ambiguous=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
