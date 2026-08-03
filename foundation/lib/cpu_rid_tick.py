"""CPU RID tick for autonomous beats — no GPU, plant-graded hold observe."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.prt_cycle import run_cycle

CPU_RID_TICKS = AUTO_ARTIFACTS / "cpu_rid_ticks.jsonl"
CPU_RID_LATEST = AUTO_ARTIFACTS / "cpu_rid_tick_latest.json"


def rid_cpu_tick(*, settle_s: float = 1.5) -> dict[str, Any]:
    """One observe cycle using pure CPU hold prediction."""
    row = run_cycle(act="observe", settle_s=settle_s, cpu_hold=True, wait_active=False)
    score = row.get("score") or {}
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": bool(row.get("ok")),
        "label": score.get("label"),
        "error": score.get("error"),
        "reason": (row.get("predict") or {}).get("reason") or row.get("reason"),
        "master_s_n_before": (row.get("observe_before") or {}).get("master_s_n"),
        "master_s_n_after": (row.get("observe_after") or {}).get("master_s_n"),
        "excluded": bool(row.get("excluded")),
    }
    AUTO_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with CPU_RID_TICKS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    CPU_RID_LATEST.write_text(json.dumps(out, indent=2), encoding="utf-8")
    if out.get("label") == "REWARD":
        try:
            from lib.prt_cpu_teacher import append_cpu_teach_gold, hold_triad_from_before

            before = row.get("observe_before") or {}
            append_cpu_teach_gold(
                {
                    "timestamp": out["timestamp"],
                    "kind": "cpu_hold_reward",
                    "hold": hold_triad_from_before(before),
                    "error": out.get("error"),
                    "s_n_before": out.get("master_s_n_before"),
                    "s_n_after": out.get("master_s_n_after"),
                }
            )
        except Exception:  # noqa: BLE001
            pass
    return out
