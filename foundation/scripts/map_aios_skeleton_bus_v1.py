"""Map AIOS skeleton bus wire status + gap stub plans (one receipt).

CPU-safe. No AIOS start, no GPU, no plant stress, no federation activation.

Usage:
  L:\\Continue\\.venv\\Scripts\\python.exe foundation/scripts/map_aios_skeleton_bus_v1.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.aios_skeleton_bus import BUS_SLOTS, default_bus  # noqa: E402
from lib.aios_skeleton_subagent_profiles import list_profiles  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402

OUT_DIR = AUTO_ARTIFACTS / "aios_skeleton"
SCHEMA_VERSION = "aios_skeleton_map_v1"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _probe_gap_plans() -> dict[str, Any]:
    plans: dict[str, Any] = {}
    for mod_name, key in (
        ("lib.aios_adapter_perception", "perception_core"),
        ("lib.aios_adapter_ethics", "ethics_core"),
        ("lib.aios_adapter_federation", "federation_core"),
    ):
        try:
            import importlib

            mod = importlib.import_module(mod_name)
            plans[key] = mod.cpu_plan()
        except Exception as exc:  # noqa: BLE001
            plans[key] = {"ok": False, "error": str(exc), "build_state": "SKELETON"}
    return plans


def main() -> int:
    bus = default_bus()
    wire = bus.wire_status()
    gap_plans = _probe_gap_plans()
    profiles = list_profiles()
    body: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "at": _utc_iso(),
        "bus_slots": list(BUS_SLOTS),
        "wire_status": wire,
        "gap_stub_plans": {
            k: {
                "ok": v.get("ok"),
                "status": v.get("status"),
                "build_state": v.get("build_state"),
                "cold_start_phase": v.get("cold_start_phase"),
                "bus_slots": v.get("bus_slots"),
                "notes": v.get("notes"),
            }
            for k, v in gap_plans.items()
        },
        "subagent_profile_count": len(profiles),
        "already_present": {
            "vision_core": "lib.aios_adapter_vision (REAL meta; no cpu_plan)",
            "input_core": "lib.aios_adapter_input (REAL text normalize)",
            "infra_core": "lib.aios_adapter_infra (hardware-agnostic plan)",
            "dream_core": "service / aios_adapter_dream",
            "node_federation_modules": "lib/node_federation*.py protocol stack",
            "subagent_skip": "vision/hearing/federation SKIP profiles in aios_subagent_v1",
        },
        "stubbed_this_pass": [
            "perception_core (multi-sense skeleton)",
            "ethics_core (ethics + adaptive_behavior)",
            "federation_core (node/distributed plan-only HOLD)",
            "bus slots: perception_plan, ethics_plan, federation_plan, hardware_plan",
        ],
        "vacant_for_compute_core": wire.get("vacant_for_compute_core"),
        "aios_runtime_started": False,
        "federation_activation": False,
        "gpu_train_started": False,
        "soft_0_99": False,
    }
    # Honest overall ok: bus maps and gap stubs return ok.
    body["ok"] = bool(wire.get("slots_total")) and all(
        bool((gap_plans.get(k) or {}).get("ok")) for k in ("perception_core", "ethics_core", "federation_core")
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    out_json = OUT_DIR / f"skeleton_map_{stamp}.json"
    latest = OUT_DIR / "skeleton_map_latest.json"
    text = json.dumps(body, indent=2, default=str)
    out_json.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": body["ok"], "receipt": str(out_json).replace("\\", "/"), "vacant": body["vacant_for_compute_core"]}, indent=2))
    return 0 if body["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
