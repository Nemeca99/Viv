#!/usr/bin/env python3
"""Train both identity specialists on GPU (same data, different reasoning styles).

GPU trains efficient + deep checkpoints. Speak time: efficient→CPU, deep→GPU.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from sandbox_paths import CAMPAIGNS_DIR, DEEP_CAMPAIGN, EFFICIENT_CAMPAIGN, RUNS_DIR, SCHEMA_CAMPAIGN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-identity",
        choices=("v43", "v62"),
        default="v43",
        help="Read-only Codex identity lane (default v43; has tensor shards on disk).",
    )
    parser.add_argument(
        "--local-dataset",
        action="store_true",
        help="Use tiny sandbox corpus instead of Codex identity.",
    )
    parser.add_argument("--force-dataset", action="store_true", help="Rebuild local dataset only.")
    parser.add_argument("--efficient-steps", type=int, default=None)
    parser.add_argument("--deep-steps", type=int, default=None)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Short smoke (efficient=100, deep=200).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import train_specialist  # noqa: E402

    if args.local_dataset:
        import sandbox_build_dataset as build_dataset  # noqa: E402

        ds_argv = ["--force"] if args.force_dataset else []
        code = build_dataset.main(ds_argv)
        if code != 0:
            return code

    eff_steps = args.efficient_steps
    deep_steps = args.deep_steps
    if args.quick:
        eff_steps = eff_steps or 100
        deep_steps = deep_steps or 200
    elif not args.local_dataset:
        eff_steps = eff_steps or 250
        deep_steps = deep_steps or 250

    common: list[str] = ["--device", "cuda"]
    if args.local_dataset:
        common.append("--local-dataset")
    else:
        common.extend(["--codex-identity", str(args.codex_identity)])

    eff_argv = ["--lane", "efficient", *common]
    if eff_steps is not None:
        eff_argv += ["--steps", str(eff_steps)]
    code = train_specialist.main(eff_argv)
    if code != 0:
        return code

    deep_argv = ["--lane", "deep", *common]
    if deep_steps is not None:
        deep_argv += ["--steps", str(deep_steps)]
    code = train_specialist.main(deep_argv)
    if code != 0:
        return code

    smoke_status = "SKIPPED"
    if not args.skip_smoke:
        import run_sandbox_smoke  # noqa: E402

        code = run_sandbox_smoke.main()
        smoke_status = "PASS" if code == 0 else "FAIL"
        if code != 0:
            return code

    manifest = {
        "schema_version": SCHEMA_CAMPAIGN,
        "sandbox_only": True,
        "originals_untouched": True,
        "status": "PASS",
        "smoke": smoke_status,
        "dataset": "local" if args.local_dataset else f"codex_{args.codex_identity}",
        "train_device": "cuda",
        "deploy_devices": {"efficient": "cpu", "deep": "cuda"},
        "reasoning_styles": {
            "efficient": EFFICIENT_CAMPAIGN.get("reasoning_style"),
            "deep": DEEP_CAMPAIGN.get("reasoning_style"),
        },
        "efficient_steps": eff_steps or EFFICIENT_CAMPAIGN["steps"],
        "deep_steps": deep_steps or DEEP_CAMPAIGN["steps"],
    }
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    with (CAMPAIGNS_DIR / "campaign_latest.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with (RUNS_DIR / "campaign_latest.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"VIV_SANDBOX_CAMPAIGN_PASS dataset={manifest['dataset']} smoke={smoke_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
