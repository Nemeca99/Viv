#!/usr/bin/env python3
"""Legacy entry — wraps generic validate_judge_adapter for the dedicated 320 path.

Prefer: scripts/validate_judge_adapter.py --adapter <path>
Ladder now auto-validates every rung.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

ADAPTER_320 = FOUNDATION / "models" / "gpu" / "viv_voice_lora_judge_320"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--validate-only", action="store_true", default=True)
    p.add_argument("--adapter", type=str, default=str(ADAPTER_320))
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--max-new", type=int, default=64)
    p.add_argument("--steps", type=int, default=320)
    args = p.parse_args()
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_judge_adapter",
        FOUNDATION / "scripts" / "validate_judge_adapter.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    out = mod.validate_adapter(
        args.adapter, limit=args.limit, max_new=args.max_new, steps=args.steps
    )
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
