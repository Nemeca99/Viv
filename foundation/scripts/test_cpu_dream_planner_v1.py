"""Regression for deterministic dream planning."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.cpu_dream_planner import plan_dream_cycle  # noqa: E402


def main() -> int:
    cold = plan_dream_cycle(s_n=0.8, live_chars=100, pulse_bpm=0.2)
    hot = plan_dream_cycle(s_n=0.8, live_chars=100, pulse_bpm=0.9)
    assert cold["allowed"] and cold["mode"] == "cold_path"
    assert hot["allowed"] and hot["mode"] == "hot_path"
    assert plan_dream_cycle(s_n=0.2, live_chars=100)["reason"] == "s_n_dormancy"
    assert plan_dream_cycle(s_n=0.8, live_chars=10)["reason"] == "thin_live_memory"
    forced = plan_dream_cycle(s_n=0.2, live_chars=10, force=True)
    assert forced["allowed"] and forced["reason"] == "forced"
    assert forced["writes_performed"] is False and forced["llm_authority"] is False
    print(json.dumps({"ok": True, "cold": cold["mode"], "hot": hot["mode"], "forced": forced["allowed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
