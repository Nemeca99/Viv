#!/usr/bin/env python3
"""Collect AIFL under tag-clusters until LoRA admission writes train_ready/signal.json.

By default, wakes a dormant plant so turns can stamp REWARD.
When SFT soft_hold share is below soft_hold_target_frac, skips pulse on odd
batches so SOFT_HOLD (mind-pass + Vixi=0) can grow — dataset-shape fix, not a
gate change.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.viv_aifl import run_aifl
from lib.viv_ide import observe_state
from lib.viv_judge_train_gate import (
    TRAIN_READY_SIGNAL,
    VOICE_JUDGE_SFT,
    count_reward_pairs,
    evaluate_lora_admission,
    load_admission_policy,
    load_gate_state,
)

LOG = Path("L:/Continue/Viv/foundation/artifacts/auto/aifl/collect_until_ready.jsonl")
LATEST = Path("L:/Continue/Viv/foundation/artifacts/auto/aifl/collect_until_ready_latest.json")
MAX_BATCHES = 60
VIXI_FLOOR = 0.37
DEFAULT_SOFT_HOLD_TARGET = 0.18


def _sft_soft_hold_frac(path: Path = VOICE_JUDGE_SFT) -> dict:
    n = soft = reward = 0
    if not path.is_file():
        return {"n": 0, "soft_hold": 0, "reward": 0, "soft_hold_frac": 0.0}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        n += 1
        lab = str(obj.get("label") or (obj.get("scores") or {}).get("label") or "").upper()
        if lab == "SOFT_HOLD":
            soft += 1
        elif lab == "REWARD":
            reward += 1
    return {
        "n": n,
        "soft_hold": soft,
        "reward": reward,
        "soft_hold_frac": (soft / n) if n else 0.0,
    }


def _ensure_plant_live(*, round_i: int = 0) -> dict:
    """If S_n below Vixi floor, run a bounded pulse so turns can stamp REWARD."""
    from lib.pulse_plant import pick_pulse_level, run_pulse

    st = observe_state()
    sn = float(st.get("master_s_n") or 0.0)
    if sn >= VIXI_FLOOR:
        return {"pulsed": False, "sn": sn, "status": st.get("status")}
    cfg = pick_pulse_level(round_i)
    print(f"plant dormant sn={sn:.4f} — pulsing duty={cfg.get('duty')} s={cfg.get('seconds')}", flush=True)
    out = run_pulse(cfg)
    st2 = observe_state()
    return {
        "pulsed": True,
        "pulse": out,
        "sn_before": sn,
        "sn_after": st2.get("master_s_n"),
        "status": st2.get("status"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--allow-dormant",
        action="store_true",
        help="Never pulse plant (favor SOFT_HOLD growth when S_n is low)",
    )
    p.add_argument(
        "--soft-hold-target",
        type=float,
        default=DEFAULT_SOFT_HOLD_TARGET,
        help="If SFT soft_hold_frac below this, skip pulse on odd batches (default 0.18)",
    )
    p.add_argument("--max-batches", type=int, default=MAX_BATCHES)
    p.add_argument("--turns", type=int, default=10)
    p.add_argument("--n-files", type=int, default=5)
    args = p.parse_args(argv)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    start_r = count_reward_pairs()
    mix0 = _sft_soft_hold_frac()
    print(
        f"START rewards={start_r} signal={TRAIN_READY_SIGNAL.is_file()} "
        f"frozen={load_gate_state().get('frozen')} "
        f"sft_soft_hold_frac={mix0.get('soft_hold_frac'):.3f} "
        f"({mix0.get('soft_hold')}/{mix0.get('n')})",
        flush=True,
    )
    batches = []
    for i in range(1, max(1, int(args.max_batches)) + 1):
        if TRAIN_READY_SIGNAL.is_file():
            print(f"SIGNAL already present before batch {i}", flush=True)
            break
        mix = _sft_soft_hold_frac()
        soft_frac = float(mix.get("soft_hold_frac") or 0.0)
        need_soft = soft_frac < float(args.soft_hold_target)
        skip_pulse = bool(args.allow_dormant) or (need_soft and (i % 2 == 1))
        if skip_pulse:
            st = observe_state()
            wake = {
                "pulsed": False,
                "skipped_for_soft_hold": True,
                "soft_hold_frac": soft_frac,
                "soft_hold_target": float(args.soft_hold_target),
                "sn": st.get("master_s_n"),
                "status": st.get("status"),
            }
            print(
                f"batch={i} skip_pulse soft_frac={soft_frac:.3f}<{args.soft_hold_target} "
                f"sn={wake.get('sn')}",
                flush=True,
            )
        else:
            wake = _ensure_plant_live(round_i=i)
        before = count_reward_pairs()
        out = run_aifl(
            mode="mixed",
            n_files=max(1, int(args.n_files)),
            turns=max(1, int(args.turns)),
            remember=True,
        )
        after = count_reward_pairs()
        adm = out.get("lora_admission") or {}
        if not TRAIN_READY_SIGNAL.is_file():
            adm = evaluate_lora_admission(write_signal=True)
        row = {
            "batch": i,
            "reward_before": before,
            "reward_after": after,
            "delta": after - before,
            "labels": out.get("labels"),
            "quality": out.get("quality"),
            "clusters": ((out.get("ingest") or {}).get("sample_bias") or {}).get("clusters_unique"),
            "wake": wake,
            "sn": (observe_state() or {}).get("master_s_n"),
            "sft_mix": _sft_soft_hold_frac(),
            "ready": bool(adm.get("ready") or TRAIN_READY_SIGNAL.is_file()),
            "blocked_by": adm.get("blocked_by"),
        }
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        batches.append(row)
        print(
            f"batch={i} reward {before}->{after} (+{after-before}) "
            f"labels={row['labels']} clusters={row['clusters']} "
            f"ready={row['ready']} blocked={row['blocked_by']} sn={row['sn']} "
            f"soft_frac={(row['sft_mix'] or {}).get('soft_hold_frac')}",
            flush=True,
        )
        if TRAIN_READY_SIGNAL.is_file() or adm.get("ready"):
            print("SIGNAL WRITTEN", flush=True)
            break
        time.sleep(0.2)

    summary = {
        "ok": TRAIN_READY_SIGNAL.is_file(),
        "start_rewards": start_r,
        "final_rewards": count_reward_pairs(),
        "batches": len(batches),
        "sft_mix_start": mix0,
        "sft_mix_end": _sft_soft_hold_frac(),
        "signal": str(TRAIN_READY_SIGNAL).replace("\\", "/") if TRAIN_READY_SIGNAL.is_file() else None,
        "gate": load_gate_state(),
        "policy_ingest": (load_admission_policy().get("ingest") or {}),
    }
    LATEST.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
