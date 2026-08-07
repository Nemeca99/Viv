"""Selftest for privacy/support/dream service-cores automation (plan-only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.service_cores_automation import (  # noqa: E402
    RECEIPTS_ROOT,
    SERVICE_CORE_IDS,
    get_spec,
    inventory,
    run_all_plans,
    run_plan,
    write_receipt,
)


def main() -> int:
    inv = inventory()
    assert inv.get("ok") is True, inv
    assert inv.get("cores") == list(SERVICE_CORE_IDS), inv
    assert len(inv.get("rows") or []) == 3, inv
    for row in inv["rows"]:
        assert row.get("all_artifacts_present") is True, row
        assert row.get("adapter_present") is True, row
        assert row.get("cpu_module_present") is True, row
        assert row.get("docs_present") is True, row

    assert get_spec("privacy") is not None
    assert get_spec("privacy_core") is not None
    assert get_spec("support") is not None
    assert get_spec("dream_core") is not None
    assert get_spec("missing") is None

    for core_key in SERVICE_CORE_IDS:
        result = run_plan(core_key)
        assert result.get("ok") is True, (core_key, result)
        assert result.get("mode") == "plan_only", (core_key, result)
        assert result.get("aios_runtime_started") is False, (core_key, result)
        assert result.get("deny_weight_packs") is True, (core_key, result)
        assert result.get("federation_activation") is False, (core_key, result)
        assert result.get("bridge_promotion") is False, (core_key, result)

    privacy = run_plan("privacy")
    assert (privacy.get("plan") or {}).get("writes_performed") is False, privacy

    support = run_plan("support")
    plan = support.get("plan") or {}
    assert plan.get("writes_performed") is False, support
    assert plan.get("live_probe_performed") is False, support

    dream = run_plan("dream")
    assert dream.get("dream_cycle_executed") is False, dream
    assert dream.get("archive_deleted") is False, dream
    consolidation = (dream.get("plan") or {}).get("consolidation") or {}
    assert consolidation.get("writes_performed") is False, dream

    bundle = run_all_plans()
    assert bundle.get("ok") is True, bundle
    assert set(bundle.get("results") or {}) == set(SERVICE_CORE_IDS), bundle

    receipt = write_receipt(bundle, stamp="selftest_service_cores_automation")
    assert receipt.is_file(), receipt
    assert RECEIPTS_ROOT.name == "service_cores_automation"
    assert receipt.parent.parent == RECEIPTS_ROOT or RECEIPTS_ROOT in receipt.parents

    report = {
        "ok": True,
        "cores": list(SERVICE_CORE_IDS),
        "inventory_ok": True,
        "receipt": str(receipt).replace("\\", "/"),
        "receipt_md": str(receipt.with_name("RECEIPT.md")).replace("\\", "/"),
        "receipts_root": str(RECEIPTS_ROOT).replace("\\", "/"),
        "aios_runtime_started": False,
        "deny_weight_packs": True,
        "planned": list(SERVICE_CORE_IDS),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
