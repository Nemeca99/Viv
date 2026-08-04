"""CPU-only integration proof with GPU/API/model availability absent."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_cold_start_replay import canonical_json, replay_fixture  # noqa: E402


def main() -> None:
    first, second = replay_fixture()
    assert first == second
    assert canonical_json(first) == canonical_json(second)
    assert first["decision"]["state"] == "AUTHORIZED_READ_ONLY_CPU_DECISION"
    assert first["decision"]["effect_authorized"] is False
    assert first["model_availability"] == {"gpu": False, "api": False, "model_loaded": False}
    assert first["rendering"] == {"natural_language": False, "mouth_invoked": False, "gpu_invoked": False, "api_invoked": False}
    assert all(value is False for value in first["side_effects"].values())
    assert first["checks"]["rid_shadow"]["ok"] is True
    assert first["checks"]["sandbox_policy"]["state"] == "VERIFIED_PLAN_ONLY"
    assert first["checks"]["infra_policy"]["state"] == "PASS"
    assert first["checks"]["enterprise_read_policy"]["allowed"] is True
    assert first["checks"]["enterprise_external_policy"]["allowed"] is False
    assert len(first["provenance"]["audit_digest"]) == 64
    print(json.dumps({"ok": True, "byte_identical_canonical_replay": True, "decision": first["decision"], "gpu_api_absent": True, "natural_language_rendered": False, "side_effects": first["side_effects"]}, sort_keys=True))


if __name__ == "__main__":
    main()
