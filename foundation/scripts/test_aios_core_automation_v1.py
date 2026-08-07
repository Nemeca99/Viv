"""Selftest for the unified AIOS core automation surface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_core_automation import (  # noqa: E402
    RECEIPTS_ROOT,
    get_profile,
    inventory_rows,
    list_profiles,
    run_plan,
    write_receipt,
)


def main() -> int:
    profiles = list_profiles()
    assert profiles, "no profiles registered"
    ids = {row["profile_id"] for row in profiles}
    assert "backup_uml_lane" in ids
    assert "infra" in ids
    assert "carma" in ids
    assert get_profile("backup_uml_lane") is not None
    assert get_profile("missing_core") is None

    backup = get_profile("backup_uml_lane")
    assert backup is not None and backup.execute_allowed and backup.execute_kind == "backup_delegate"
    carma = get_profile("carma")
    assert carma is not None and carma.execute_allowed is False

    # Plan-only fixtures for a representative set (no AIOS runtime, no vault write).
    for profile_id in ("infra", "privacy", "fractal", "data", "carma", "utils", "main", "dream"):
        result = run_plan(profile_id)
        assert result.get("aios_runtime_started") is False, (profile_id, result)
        assert result.get("deny_weight_packs") is True, (profile_id, result)
        assert result.get("federation_activation") is False, (profile_id, result)
        assert result.get("bridge_promotion") is False, (profile_id, result)
        assert result.get("ok") is True, (profile_id, result)

    backup_plan = run_plan("backup_uml_lane")
    assert backup_plan.get("ok") is True, backup_plan
    assert backup_plan.get("mode") == "plan_only", backup_plan
    assert backup_plan.get("aios_runtime_started") is False, backup_plan
    assert (backup_plan.get("plan") or {}).get("deny_weight_packs") is True, backup_plan

    receipt = write_receipt(
        {
            "ok": True,
            "profile": "selftest",
            "core_id": "aios_core_automation",
            "mode": "plan_only",
            "aios_runtime_started": False,
            "deny_weight_packs": True,
            "federation_activation": False,
            "bridge_promotion": False,
        },
        stamp="selftest_aios_core_automation",
    )
    assert receipt.is_file(), receipt
    assert RECEIPTS_ROOT in receipt.parents or receipt.parent.parent == RECEIPTS_ROOT or receipt.parent.parent.name == "aios_core_automation"

    rows = inventory_rows()
    assert any(row.get("profile") == "backup_uml_lane" for row in rows)
    assert any(row.get("core") == "federation" and row.get("execute_allowed") is False for row in rows)

    report = {
        "ok": True,
        "profile_count": len(profiles),
        "inventory_rows": len(rows),
        "receipt": str(receipt).replace("\\", "/"),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "planned": ["infra", "privacy", "fractal", "data", "carma", "utils", "main", "dream", "backup_uml_lane"],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
