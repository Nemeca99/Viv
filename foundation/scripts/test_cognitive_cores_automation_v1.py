"""Selftest for CARMA + consciousness plan-only automation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cognitive_cores_automation_v1 import (  # noqa: E402
    RECEIPTS_ROOT,
    list_profiles,
    plan_carma,
    plan_consciousness,
    plan_profile,
    refuse_execute,
    write_receipt,
)
from lib.aios_adapter_consciousness import cpu_plan as consciousness_cpu_plan  # noqa: E402
from lib.aios_adapter_carma import cpu_plan as carma_cpu_plan  # noqa: E402
from lib.carma_core import make_fragment  # noqa: E402


def main() -> int:
    profiles = list_profiles()
    ids = {row["profile_id"] for row in profiles}
    assert ids == {"carma", "consciousness", "both"}, ids
    assert all(row["execute_allowed"] is False for row in profiles)

    carma = plan_carma()
    assert carma["ok"] is True, carma
    assert carma["writes_performed"] is False, carma
    assert carma["durable_commit_performed"] is False, carma
    assert carma["aios_runtime_started"] is False, carma
    assert carma["execution_approved"] is False, carma
    plan = carma["plan"]
    assert plan["writes_performed"] is False, plan
    assert plan["llm_authority"] is False, plan
    assert (plan.get("retrieval") or {}).get("state") == "VERIFIED", plan

    # Direct adapter cpu_plan still effect-closed.
    rows = [make_fragment("fixture provenance", provenance="fixture")]
    direct = carma_cpu_plan(rows, query="provenance", top=1)
    assert direct["ok"] is True and direct["writes_performed"] is False, direct

    consciousness = plan_consciousness()
    assert consciousness["ok"] is True, consciousness
    assert consciousness["writes_performed"] is False, consciousness
    assert consciousness["aios_runtime_started"] is False, consciousness
    cplan = consciousness["plan"]
    assert cplan["writes_performed"] is False, cplan
    assert cplan["durable_commit_performed"] is False, cplan
    assert cplan["llm_authority"] is False, cplan
    assert cplan["viv_executes_v2"] is False, cplan
    assert (cplan.get("cycle") or {}).get("memory_commit", {}).get("state") == "NOT_DUE", cplan

    direct_c = consciousness_cpu_plan(prompt="truthful system documentation", explicit_commit=False)
    assert direct_c["ok"] is True and direct_c["writes_performed"] is False, direct_c

    both = plan_profile("both")
    assert both["ok"] is True, both
    assert both["carma"]["ok"] is True and both["consciousness"]["ok"] is True, both

    refused = refuse_execute("carma")
    assert refused["ok"] is False and refused["error"] == "execute_not_allowed", refused
    assert refused["aios_runtime_started"] is False, refused

    receipt = write_receipt(
        {
            "ok": True,
            "profile": "both",
            "core_id": "cognitive_cores",
            "mode": "plan_only",
            "writes_performed": False,
            "durable_commit_performed": False,
            "execution_approved": False,
            "aios_runtime_started": False,
        },
        stamp="selftest_cognitive_cores_automation",
    )
    assert receipt.is_file(), receipt
    assert RECEIPTS_ROOT.name == "cognitive_cores_automation"
    assert "cognitive_cores_automation" in str(receipt).replace("\\", "/")

    unknown = plan_profile("nope")
    assert unknown["ok"] is False and unknown["error"] == "unknown_profile", unknown

    report = {
        "ok": True,
        "profiles": sorted(ids),
        "carma_retrieval": (plan.get("retrieval") or {}).get("state"),
        "consciousness_commit": (cplan.get("cycle") or {}).get("memory_commit", {}).get("state"),
        "receipt": str(receipt).replace("\\", "/"),
        "aios_runtime_started": False,
        "writes_performed": False,
        "execute_allowed": False,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
