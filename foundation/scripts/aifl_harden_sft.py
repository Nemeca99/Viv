#!/usr/bin/env python3
"""Harden judge SFT (dedupe + soft_hold balance) and arm train_ready for a daily cycle."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.viv_judge_train_gate import (  # noqa: E402
    arm_train_ready_from_sft,
    harden_sft_file,
    load_admission_policy,
    save_admission_policy,
)


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-arm", action="store_true", help="Harden only; do not write signal")
    p.add_argument("--no-harden", action="store_true", help="Arm existing SFT without rewriting")
    p.add_argument(
        "--write-policy",
        action="store_true",
        help="Persist default sft_harden block into admission_policy.json",
    )
    args = p.parse_args()

    if args.write_policy:
        policy = load_admission_policy()
        policy["sft_harden"] = {
            "enabled": True,
            "max_text_repeats": 3,
            "soft_hold_min_frac": 0.20,
            "seed": 7,
            "note": "P0 harden 2026-07-22: cap exact-text repeats; downsample REWARD to keep soft_hold share",
        }
        if "sft_harden" not in (policy.get("note") or ""):
            policy["note"] = (
                (policy.get("note") or "")
                + " | sft_harden enabled (max_repeats=3 soft_hold_min_frac=0.20)"
            ).strip(" |")
        save_admission_policy(policy)
        print(json.dumps({"policy_sft_harden": policy["sft_harden"]}, indent=2), flush=True)

    if args.no_arm:
        out = harden_sft_file()
    else:
        out = arm_train_ready_from_sft(harden=not args.no_harden, note="hardened_sft_rearm_p0")
    print(json.dumps(out, indent=2, default=str), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
