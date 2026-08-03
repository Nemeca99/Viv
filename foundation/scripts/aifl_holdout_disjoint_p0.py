#!/usr/bin/env python3
"""P0: freeze holdout hashes, rebuild SFT without overlap, revalidate deployed adapter.

  L:/Continue/.venv/Scripts/python.exe scripts/aifl_holdout_disjoint_p0.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aifl_holdout_split import (  # noqa: E402
    assert_train_holdout_disjoint,
    freeze_holdout_registry_from_pack,
    load_registry,
    rebuild_sft_excluding_holdout,
)
from lib.viv_judge_train_gate import (  # noqa: E402
    ADMISSION_POLICY_PATH,
    HOLDOUT_PACK_PATH,
    VOICE_JUDGE_SFT,
    ensure_holdout_pack,
    load_admission_policy,
    load_gate_state,
    save_gate_state,
    _write_json,
)

OUT = FOUNDATION / "artifacts" / "auto" / "shadow_judge" / "holdout_disjoint_p0_latest.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-validate", action="store_true")
    p.add_argument("--force-registry", action="store_true")
    args = p.parse_args()

    ensure = ensure_holdout_pack(target_size=60, force=False)
    freeze = freeze_holdout_registry_from_pack(force=bool(args.force_registry))
    rebuild = rebuild_sft_excluding_holdout(sft_path=VOICE_JUDGE_SFT, backup=True)
    check = assert_train_holdout_disjoint(VOICE_JUDGE_SFT)

    result: dict = {
        "ok": bool(check.get("pass") and rebuild.get("ok")),
        "ensure_holdout": ensure,
        "freeze": freeze,
        "rebuild_sft": rebuild,
        "disjoint_check": check,
        "registry": load_registry(),
    }

    if not check.get("pass"):
        OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return 1

    if args.skip_validate:
        OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return 0

    policy = load_admission_policy()
    deployed = (policy.get("lora") or {}).get("deployed_adapter")
    if not deployed or not Path(str(deployed)).is_dir():
        result["validate"] = {"ok": False, "error": "deployed_adapter_missing", "path": deployed}
        OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return 1

    val_mod = _load(
        "validate_judge_adapter",
        FOUNDATION / "models" / "Training" / "code" / "validate_judge_adapter.py",
    )
    print(f"REVALIDATE deployed={deployed}", flush=True)
    val = val_mod.validate_adapter(
        deployed,
        limit=60,
        max_new=64,
        case_timeout_s=120.0,
        skip_disjoint_preflight=True,  # measuring deployed mouth on clean holdout only
    )
    mind = float(val.get("mind_pass_rate") or 0.0)

    # New clean baselines on untouched holdout
    state = load_gate_state()
    state["holdout_baseline_mind_pass"] = mind
    state["holdout_baseline_at"] = val.get("at")
    state["holdout_baseline_note"] = (
        f"P0 clean baseline after disjoint freeze pack_id={load_registry().get('pack_id')}"
    )
    save_gate_state(state)

    policy["lora"] = dict(policy.get("lora") or {})
    policy["lora"]["last_validate"] = {
        "steps": (policy.get("lora") or {}).get("last_validate", {}).get("steps"),
        "mind_pass_rate": mind,
        "n": val.get("n"),
        "deploy_candidate": True,
        "at": val.get("at"),
        "adapter": str(deployed).replace("\\", "/"),
        "note": "P0 clean revalidate on frozen disjoint holdout — replaces prior pin",
        "pack_id": load_registry().get("pack_id"),
        "clean_baseline": True,
    }
    policy["note"] = (
        f"P0 disjoint holdout frozen; clean deploy baseline mind_pass={mind} "
        f"pack_id={load_registry().get('pack_id')}"
    )
    _write_json(ADMISSION_POLICY_PATH, policy)

    result["validate"] = {
        "ok": val.get("ok"),
        "mind_pass_rate": mind,
        "labels": val.get("labels"),
        "axis_rates": val.get("axis_rates"),
        "artifact": val.get("artifact"),
        "adapter": str(deployed).replace("\\", "/"),
    }
    result["new_baseline"] = {
        "holdout_baseline_mind_pass": mind,
        "deploy_pin_mind_pass": mind,
        "pack_id": load_registry().get("pack_id"),
        "previous_pin": 0.9333,
    }
    result["ok"] = bool(val.get("ok")) and bool(check.get("pass"))
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(
        f"P0 DONE pack_id={load_registry().get('pack_id')} "
        f"sft {rebuild.get('before')}->{rebuild.get('after')} "
        f"clean_baseline_mind={mind}",
        flush=True,
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
