#!/usr/bin/env python3
"""Regenerate frozen hold-out pack and optionally re-baseline deployed adapter score.

The hold-out pack is ask-only oracle cases (from preference history). Adapter
validate runs LoRA generate → CPU judge on these asks — not on stored drafts.

Use when the pack is stuck at a small N (e.g. 10) and regression vs deployed
baseline needs a statistically wider oracle.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(FOUNDATION))

from lib.viv_judge_train_gate import (  # noqa: E402
    ADMISSION_POLICY_PATH,
    HOLDOUT_PACK_PATH,
    _utc,
    _write_json,
    ensure_holdout_pack,
    load_admission_policy,
)

DEPLOY_PTR = FOUNDATION / "models" / "gpu" / "viv_voice_lora_judge_deploy"
META_PATH = HOLDOUT_PACK_PATH.parent / "holdout_pack_meta.json"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _archive_existing() -> str | None:
    if not HOLDOUT_PACK_PATH.is_file():
        return None
    archive_dir = HOLDOUT_PACK_PATH.parent / "holdout_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"holdout_pack_{_stamp()}.jsonl"
    shutil.copy2(HOLDOUT_PACK_PATH, dest)
    return str(dest).replace("\\", "/")


def regenerate_pack(*, size: int, force: bool) -> dict:
    archived = _archive_existing() if force and HOLDOUT_PACK_PATH.is_file() else None
    out = ensure_holdout_pack(target_size=size, force=force)
    meta = {
        "at": _utc(),
        "target_size": size,
        "n": out.get("n"),
        "created": out.get("created"),
        "archived_from": archived,
        "path": out.get("path"),
    }
    _write_json(META_PATH, meta)
    return {**out, "archived_from": archived, "meta_path": str(META_PATH).replace("\\", "/")}


def validate_adapter(adapter: Path, *, limit: int | None) -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_judge_adapter",
        FOUNDATION / "scripts" / "validate_judge_adapter.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.validate_adapter(adapter, limit=limit, max_new=64, steps=80)


def set_deployed_baseline(val: dict, *, adapter: Path) -> dict:
    policy = load_admission_policy()
    mind = float(val.get("mind_pass_rate") or 0.0)
    policy["lora"] = dict(policy.get("lora") or {})
    policy["lora"]["last_validate"] = {
        "steps": val.get("steps") or 80,
        "mind_pass_rate": mind,
        "n": val.get("n"),
        "train_loss": val.get("train_loss"),
        "deploy_candidate": True,
        "at": val.get("at") or _utc(),
        "adapter": str(adapter).replace("\\", "/"),
        "holdout_regenerated": True,
        "note": "baseline pinned after holdout pack regeneration",
    }
    policy["note"] = (
        f"holdout rebaseline n={val.get('n')} mind_pass={mind} adapter={adapter.name}"
    )
    _write_json(ADMISSION_POLICY_PATH, policy)
    return {
        "mind_pass_rate": mind,
        "n": val.get("n"),
        "adapter": str(adapter).replace("\\", "/"),
        "policy_path": str(ADMISSION_POLICY_PATH).replace("\\", "/"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Regenerate hold-out pack and optionally re-baseline deploy")
    p.add_argument("--size", type=int, default=60, help="Target hold-out cases (default 60)")
    p.add_argument("--force", action="store_true", help="Replace existing pack (archives prior)")
    p.add_argument(
        "--validate-deployed",
        action="store_true",
        help="Run hold-out validate on viv_voice_lora_judge_deploy after regen",
    )
    p.add_argument("--adapter", type=Path, default=DEPLOY_PTR, help="Adapter for --validate-deployed")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Validate case limit (default: full pack size)",
    )
    p.add_argument(
        "--set-baseline",
        action="store_true",
        help="Pin admission_policy last_validate to validate score (requires --validate-deployed)",
    )
    args = p.parse_args()

    if not args.force and HOLDOUT_PACK_PATH.is_file():
        n = sum(1 for ln in HOLDOUT_PACK_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())
        print(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "n": n,
                    "note": "pack exists; pass --force to regenerate and archive prior",
                },
                indent=2,
            ),
            flush=True,
        )
        return 0

    regen = regenerate_pack(size=max(1, args.size), force=True)
    print(json.dumps({"regenerate": regen}, indent=2), flush=True)

    if not args.validate_deployed:
        return 0 if regen.get("ok") else 1

    adapter = args.adapter.resolve()
    limit = args.limit if args.limit is not None else int(regen.get("n") or args.size)
    print(f"VALIDATE deployed adapter={adapter} limit={limit}", flush=True)
    val = validate_adapter(adapter, limit=limit)
    print(json.dumps({"validate": val}, indent=2), flush=True)
    if not val.get("ok"):
        return 1

    if args.set_baseline:
        pinned = set_deployed_baseline(val, adapter=adapter)
        print(json.dumps({"baseline_pinned": pinned}, indent=2), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
