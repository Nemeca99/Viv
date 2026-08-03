"""Offline contracts for the Security-wrapped RID/AUTO/UML kernel."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import time

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.triad_kernel import (  # noqa: E402
    TRIAD_CONTRACT_VERSION,
    TriadDenied,
    TriadEnvelope,
    authorize_operation,
    emit,
    open_context,
    triad_status,
    verify_triad_ledger,
)


def _denied(fn, reason: str) -> None:
    try:
        fn()
    except TriadDenied as exc:
        assert exc.reason == reason, (exc.reason, exc.evidence)
        return
    raise AssertionError(f"expected TriadDenied:{reason}")


def main() -> int:
    status = triad_status()
    assert status["contract_version"] == TRIAD_CONTRACT_VERSION
    assert set(status["pillars"]) == {"rid", "auto", "uml"}
    assert status["error"] is None

    envelope = TriadEnvelope.build(
        actor="architect",
        source="contract_test",
        target="aios",
        action="STATUS",
        payload={"text": "bounded status"},
        s_n=0.60,
    )
    context = open_context(envelope)
    authorization = authorize_operation(
        context,
        operation="status.read",
        params={"scope": "triad"},
    )
    assert authorization.allowed
    output, egress = emit(context, "Triad contract response.")
    assert output == "Triad contract response."
    assert egress.allowed

    tampered = envelope.to_dict()
    tampered["payload"] = {"text": "changed"}
    _denied(lambda: open_context(tampered), "payload_hash_mismatch")

    wrong_version = envelope.to_dict()
    wrong_version["contract_version"] = "old"
    _denied(
        lambda: open_context(wrong_version),
        "triad_contract_version_mismatch",
    )

    _denied(
        lambda: open_context(
            TriadEnvelope.build(
                actor="architect",
                source="contract_test",
                target="aios",
                action="STATUS",
                payload={"text": "low stability"},
                s_n=0.10,
            )
        ),
        "security_ingress_denied",
    )

    expiring = open_context(
        TriadEnvelope.build(
            actor="architect",
            source="contract_test",
            target="aios",
            action="STATUS",
            payload={"text": "expiry"},
            s_n=0.60,
        ),
        ttl_s=0.001,
    )
    time.sleep(0.05)
    _denied(expiring.validate, "triad_context_expired")

    forged = replace(context, context_id="forged")
    _denied(forged.validate, "triad_context_authenticity_failed")

    _denied(
        lambda: authorize_operation(
            context,
            operation="source.write",
            params={
                "path": "L:/Continue/Viv/foundation/rid_main.py",
                "content": "forbidden",
            },
            tool_name="write_file",
        ),
        "[LAW 4] Forbidden extension in 'l:/continue/viv/foundation/rid_main.py'. Code/binary writes blocked.",
    )

    _denied(
        lambda: emit(context, "D:/private/secrets.txt"),
        "security_egress_denied",
    )

    ledger = verify_triad_ledger()
    assert ledger["ok"] and ledger["events"] >= 1, ledger
    print(
        json.dumps(
            {
                "ok": True,
                "contract_version": TRIAD_CONTRACT_VERSION,
                "pillars": sorted(status["pillars"]),
                "negative_contracts": 7,
                "ledger_events": ledger["events"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
