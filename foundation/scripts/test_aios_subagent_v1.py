"""Selftest for AIOS skeleton subagent worker bus v1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_subagent_v1 import (  # noqa: E402
    COMPUTE_CORE_HOOK,
    MAX_FANOUT_CONCURRENCY,
    PROFILES,
    RECEIPTS_ROOT,
    SCHEMA_VERSION,
    fanout_subagents,
    get_profile,
    list_profiles,
    require_profile,
    run_subagent,
)


def main() -> int:
    rows = list_profiles()
    assert len(rows) == len(PROFILES) >= 12, len(rows)
    ids = {r["profile_id"] for r in rows}
    for required in (
        "selftest_ping",
        "preflight",
        "rid_plant",
        "voice_contracts",
        "cognitive_plan",
        "service_plan",
        "training_plan",
        "backup_plan",
        "bridge_canary",
        "security_gate",
        "vision",
        "hearing",
        "federation",
        "soft_099",
        "aios_runtime",
        "compute_core",
        "gpu_train",
    ):
        assert required in ids, required

    # Fail-closed unknown.
    unknown = run_subagent("not_a_real_profile", write=True)
    assert unknown.get("outcome") == "FAIL_CLOSED", unknown
    assert unknown.get("ok") is False
    assert unknown.get("aios_runtime_started") is False

    try:
        require_profile("nope")
        raise AssertionError("require_profile should raise")
    except ValueError as exc:
        assert "unknown_subagent_profile" in str(exc)

    # Tiny selftest profile.
    ping = run_subagent(
        "selftest_ping",
        objective_id="selftest_obj",
        parent_turn_token_id="selftest_turn",
        write=True,
    )
    assert ping.get("ok") is True and ping.get("outcome") == "PASS", ping
    assert ping.get("authority", {}).get("gpu_authority_mint") is False
    assert ping.get("authority", {}).get("plane") == "cpu"
    assert ping.get("soft_0_99") is False
    assert COMPUTE_CORE_HOOK.get("dispatch") is False

    # Stub SKIP.
    vision = run_subagent("vision", write=True)
    assert vision.get("outcome") == "SKIP" and vision.get("ok") is True, vision

    # Forbidden flags refused.
    refused = run_subagent("selftest_ping", enable_soft_099=True, write=True)
    assert refused.get("outcome") == "REFUSED", refused
    refused2 = run_subagent("bridge_canary", enable_bridge_canary=True, write=True)
    assert refused2.get("outcome") == "REFUSED", refused2
    refused3 = run_subagent("aios_runtime", enable_aios_start=True, write=True)
    assert refused3.get("outcome") == "REFUSED", refused3

    # Fanout of 2 plan-only (selftest + stub) — no heavy runners.
    fan = fanout_subagents(
        ["selftest_ping", "vision"],
        concurrency=MAX_FANOUT_CONCURRENCY,
        objective_id="selftest_fanout",
        parent_turn_token_id="selftest_turn_fan",
        plan_only=True,
        write=True,
    )
    assert fan.get("ok") is True, fan
    assert fan.get("concurrency") <= MAX_FANOUT_CONCURRENCY
    assert len(fan.get("jobs") or []) == 2
    assert all(j.get("aios_runtime_started") is False for j in fan["jobs"])

    bridge = get_profile("bridge_canary")
    assert bridge is not None and bridge.allows_bridge_canary_enable is False
    soft = get_profile("soft_099")
    assert soft is not None and soft.allows_soft_099 is False

    assert RECEIPTS_ROOT.is_dir() or (RECEIPTS_ROOT / "LATEST.json").exists() or ping.get("receipt")
    receipt_path = Path(str(ping.get("receipt")).replace("/", "\\")) if ping.get("receipt") else None
    assert receipt_path and receipt_path.is_file(), ping.get("receipt")

    report = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "profile_count": len(rows),
        "fanout_cap": MAX_FANOUT_CONCURRENCY,
        "ping_receipt": ping.get("receipt"),
        "fanout_receipt": fan.get("receipt"),
        "unknown_outcome": unknown.get("outcome"),
        "compute_core_dispatch": COMPUTE_CORE_HOOK.get("dispatch"),
        "aios_runtime_started": False,
        "soft_0_99": False,
        "bridge_canary_enabled": False,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
