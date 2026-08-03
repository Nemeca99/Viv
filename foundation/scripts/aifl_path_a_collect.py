#!/usr/bin/env python3
"""Path A — collect judge REWARD pairs until production gate min (50)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.viv_aifl import run_aifl
from lib.viv_ide import observe_state
from lib.viv_judge_train_gate import count_reward_pairs, evaluate_lora_admission

TARGET = 50
MAX_BATCHES = 12
LOG = Path("L:/Continue/Viv/foundation/artifacts/auto/aifl/path_a_collect.jsonl")
LATEST = Path("L:/Continue/Viv/foundation/artifacts/auto/aifl/path_a_latest.json")


def snap() -> dict:
    st = observe_state()
    return {
        "reward_total": count_reward_pairs(),
        "master_s_n": st.get("master_s_n"),
        "plant_status": st.get("status"),
    }


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    start = snap()
    print(
        f"START reward={start['reward_total']} sn={start['master_s_n']} "
        f"status={start['plant_status']}",
        flush=True,
    )
    batches: list[dict] = []
    for i in range(1, MAX_BATCHES + 1):
        before = count_reward_pairs()
        if before >= TARGET:
            print(f"HIT before batch {i}: {before}", flush=True)
            break
        mode = "ingest" if i % 2 else "mixed"
        turns = 8 if mode == "ingest" else 10
        out = run_aifl(mode=mode, n_files=3, turns=turns, remember=True)
        after = count_reward_pairs()
        row = {
            "batch": i,
            "mode": mode,
            "turns": turns,
            "elapsed_ms": out.get("elapsed_ms"),
            "labels": out.get("labels"),
            "quality": out.get("quality"),
            "reward_before": before,
            "reward_after": after,
            "delta": after - before,
            "sn": (observe_state() or {}).get("master_s_n"),
            "admission_ready": (out.get("lora_admission") or {}).get("ready"),
            "blocked_by": (out.get("lora_admission") or {}).get("blocked_by"),
        }
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        batches.append(row)
        print(
            f"batch={i} mode={mode} labels={row['labels']} "
            f"reward {before}->{after} (+{after - before}) sn={row['sn']}",
            flush=True,
        )
        if after >= TARGET:
            print("TARGET REACHED", after, flush=True)
            break
        time.sleep(0.2)

    final = snap()
    gate = evaluate_lora_admission(write_signal=True)
    summary = {
        "ok": True,
        "start": start,
        "final": final,
        "batches": len(batches),
        "target": TARGET,
        "hit": final["reward_total"] >= TARGET,
        "gate_ready": gate.get("ready"),
        "gate_blocked": gate.get("blocked_by"),
        "gate_quality": gate.get("quality"),
        "log": str(LOG).replace("\\", "/"),
    }
    LATEST.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["hit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
