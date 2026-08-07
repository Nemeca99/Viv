#!/usr/bin/env python3
"""Contract tests: identity-side uml_request ingress on CPU intent packets."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDATION = REPO / "foundation"
for path in (REPO, FOUNDATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.aios_tagged_packet import ALLOWED_TAGS, render_for_gpu  # noqa: E402
from voice_core import intent_packet as ip  # noqa: E402
from voice_core.intent_packet import (  # noqa: E402
    UmlRequestIngressError,
    attach_uml_resolved,
    build_intent_packet,
    seal_uml_request,
)


def _blocks_digest(packet: dict) -> str:
    """Digest tagged blocks only (UML must not appear here)."""
    blocks = packet["tagged_packet"]["blocks"]
    payload = json.dumps(blocks, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_build(**kwargs):
    """Build with frozen plant/memory so digests are comparable."""
    kwargs.setdefault("query", "stable ingress probe")
    kwargs.setdefault("mode", "converse")
    kwargs.setdefault("facts", ["stable_fact=1"])
    kwargs.setdefault("memory_top", 1)

    def _no_memory(*_a, **_k):
        return []

    def _fixed_master():
        class _M:
            master_s_n = 0.61
            status = "ACTIVE"
            n_subsystems = 1

        return _M()

    prev_retrieve = ip.carma_retrieve
    prev_master = ip.load_master_rid
    ip.carma_retrieve = _no_memory  # type: ignore[assignment]
    ip.load_master_rid = _fixed_master  # type: ignore[assignment]
    try:
        return build_intent_packet(**kwargs)
    finally:
        ip.carma_retrieve = prev_retrieve  # type: ignore[assignment]
        ip.load_master_rid = prev_master  # type: ignore[assignment]


def main() -> int:
    # 1) Missing field OK — no UML invocation hints.
    absent = _stable_build()
    none_arg = _stable_build(uml_request=None)
    assert "uml_request" not in absent
    assert "uml_resolved" not in absent
    assert "uml_request" not in none_arg
    assert "uml_resolved" not in none_arg
    assert set(absent["tagged_packet"]["blocks"]) == set(ALLOWED_TAGS)

    # 2) Packet digest stable when uml_request absent (tagged blocks identical).
    d_absent = _blocks_digest(absent)
    d_none = _blocks_digest(none_arg)
    assert d_absent == d_none, "tagged digest must match when uml_request is absent"

    # 3) CPU-sourced request accepted; stays packet-level (not GPU tags).
    cpu_req = {
        "request_kind": "sealed_destination",
        "target_char": "H",
        "target_value": 42,
        "proposals": ["42", "H"],
        "prefer_policy": "cheapest_valid",
        "source": "cpu",
    }
    with_req = _stable_build(uml_request=cpu_req)
    assert with_req["uml_request"]["source"] == "cpu"
    assert with_req["uml_request"]["request_kind"] == "sealed_destination"
    assert with_req["uml_request"]["target_char"] == "H"
    assert with_req["uml_request"]["proposals"] == ["42", "H"]
    assert "uml_request" not in with_req["tagged_packet"]["blocks"]
    assert set(with_req["tagged_packet"]["blocks"]) == set(ALLOWED_TAGS)
    # Tagged digest unchanged vs no-UML packet (UML not in tag markup).
    assert _blocks_digest(with_req) == d_absent
    wire = render_for_gpu(with_req["tagged_packet"])
    assert "uml_request" not in wire
    assert "sealed_destination" not in wire
    assert "cheapest_valid" not in wire

    # Default source=cpu when omitted.
    sealed = seal_uml_request(
        {
            "request_kind": "sealed_destination",
            "target_char": "A",
            "target_value": 1,
        }
    )
    assert sealed["source"] == "cpu"

    # 4) Non-CPU source rejected (gpu_mouth minting).
    try:
        build_intent_packet(
            query="reject",
            mode="converse",
            facts=["x=1"],
            memory_top=1,
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": "H",
                "source": "gpu_mouth",
            },
        )
        raise AssertionError("gpu_mouth uml_request must be rejected")
    except UmlRequestIngressError as exc:
        assert "gpu_mouth" in str(exc)

    # 5) uml_resolved outbound slot — opaque to mouth wire.
    resolved = {
        "target_char": "H",
        "target_value": 42,
        "selected_route": "42",
        "bridge_mode": "FIELD_SCOPED_CANARY",
        "canary_only": True,
    }
    with_resolved = _stable_build(uml_request=cpu_req, uml_resolved=resolved)
    assert with_resolved["uml_resolved"]["selected_route"] == "42"
    assert _blocks_digest(with_resolved) == d_absent
    attach_uml_resolved(with_resolved, {"selected_route": "1", "canary_only": True})
    assert with_resolved["uml_resolved"]["selected_route"] == "1"
    # Mutation of resolved must not rewrite tagged blocks.
    mutated = copy.deepcopy(with_resolved)
    mutated["uml_resolved"] = {"selected_route": "99"}
    assert _blocks_digest(mutated) == d_absent

    print(
        "INTENT_UML_REQUEST_INGRESS_PASS "
        "missing_ok=1 cpu_accept=1 gpu_reject=1 digest_stable=1 uml_resolved=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
