#!/usr/bin/env python3
"""Start a new admission epoch after the permanent disjoint split.

This resets only the historical reward watermark. It refuses to proceed if
the deploy-test registry is not frozen or the current SFT overlaps a ban set.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.aifl_holdout_split import assert_train_holdout_disjoint, load_deploy_test_registry, load_registry
from lib.paths import AUTO_ARTIFACTS
from lib.viv_judge_train_gate import VOICE_JUDGE_SFT, load_gate_state, save_gate_state


OUT = AUTO_ARTIFACTS / "shadow_judge" / "post_quarantine_rearm.json"
JOURNAL = ROOT / "artifacts" / "audit" / "session_journal.md"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    at = utc()
    continuity = load_registry()
    deploy = load_deploy_test_registry()
    check = assert_train_holdout_disjoint(VOICE_JUDGE_SFT)
    result = {
        "ok": False,
        "at": at,
        "continuity_pack_id": continuity.get("pack_id"),
        "deploy_test_pack_id": deploy.get("pack_id"),
        "sft_path": str(VOICE_JUDGE_SFT).replace("\\", "/"),
        "disjoint_check": check,
    }
    if not continuity.get("frozen") or not deploy.get("frozen"):
        result["error"] = "both_quarantine_registries_must_be_frozen"
    elif not check.get("pass"):
        result["error"] = "sft_not_disjoint"
    else:
        state_path = AUTO_ARTIFACTS / "shadow_judge" / "gate_state.json"
        backup = state_path.with_suffix(f".pre_rearm_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak")
        if state_path.is_file():
            shutil.copy2(state_path, backup)
        state = load_gate_state()
        previous = int(state.get("reward_watermark") or 0)
        state["reward_watermark"] = 0
        state["post_quarantine_rearmed_at"] = at
        state["post_quarantine_rearm_note"] = (
            "New admission epoch after frozen continuity + deploy-test quarantine; "
            "current SFT passed disjoint preflight."
        )
        save_gate_state(state)
        result.update({"ok": True, "previous_reward_watermark": previous, "new_reward_watermark": 0, "backup": str(backup).replace("\\", "/")})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n- [{at}] **ENGINEERING** — post-quarantine admission epoch: "
            f"ok={result['ok']} previous_watermark={result.get('previous_reward_watermark')} "
            f"new_watermark={result.get('new_reward_watermark')} report={OUT.as_posix()}\n"
        )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
