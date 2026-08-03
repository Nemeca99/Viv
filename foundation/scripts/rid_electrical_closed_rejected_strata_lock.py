#!/usr/bin/env python3
"""Write CLOSED_REJECTED_STRATA_V1 lock artifact.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_closed_rejected_strata_lock.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_accounting_registry_release import RELEASE_ID  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
PATH = OUT / "CLOSED_REJECTED_STRATA_V1.json"
PATH_MD = OUT / "CLOSED_REJECTED_STRATA_V1.md"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    payload = {
        "ok": True,
        "at": _utc(),
        "lock_id": "CLOSED_REJECTED_STRATA_V1",
        "release_id": RELEASE_ID,
        "strata": {
            "tail_5": {
                "status": "closed_negative",
                "release_id": RELEASE_ID,
                "nearby_fallback_forbidden": True,
                "substitute_horizons_forbidden": ["tail_10", "tail_20"],
            },
            "warm_prompt_eval": {
                "status": "closed_negative",
                "release_id": RELEASE_ID,
                "nearby_fallback_forbidden": True,
                "warm_generic_fallback_forbidden": True,
            },
        },
        "reopen_policy": {
            "requires_named_separate_campaign": True,
            "predeclared_measurement_control_changes_required": True,
            "repeated_sampling_alone_insufficient": True,
            "mirror": "electrical_reopen_doctrine",
        },
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
        "policy": policy_stamp(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    PATH_MD.write_text(
        "\n".join(
            [
                "# CLOSED_REJECTED_STRATA_V1",
                "",
                f"- release_id: `{RELEASE_ID}`",
                "- closed: `tail_5`, `warm_prompt_eval`",
                "- reopen: named separate campaign + predeclared measurement/control changes",
                "- repeated sampling alone is insufficient",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "artifact": str(PATH).replace("\\", "/")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
