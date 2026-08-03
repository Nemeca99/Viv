#!/usr/bin/env python3
"""P0: freeze fresh deploy-test pack; pin deciding baseline on deployed adapter.

Continuity pack b7b159b442a93139 stays regression-only.
Deploy decisions use deploy_test_pack only.

  L:/Continue/.venv/Scripts/python.exe scripts/aifl_deploy_test_pack_p0.py
  L:/Continue/.venv/Scripts/python.exe scripts/aifl_deploy_test_pack_p0.py --skip-validate
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
    freeze_deploy_test_pack,
    load_deploy_test_registry,
    load_registry,
)
from lib.viv_judge_train_gate import (  # noqa: E402
    ADMISSION_POLICY_PATH,
    VOICE_JUDGE_SFT,
    load_admission_policy,
    load_gate_state,
    save_gate_state,
    _write_json,
)

OUT = FOUNDATION / "artifacts" / "auto" / "shadow_judge" / "deploy_test_pack_p0_latest.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-validate", action="store_true")
    p.add_argument("--force-freeze", action="store_true")
    args = p.parse_args()

    freeze = freeze_deploy_test_pack(force=bool(args.force_freeze))
    check = assert_train_holdout_disjoint(VOICE_JUDGE_SFT) if VOICE_JUDGE_SFT.is_file() else {
        "pass": True,
        "note": "no_sft",
    }
    dt_reg = load_deploy_test_registry()
    cont_reg = load_registry()

    result: dict = {
        "ok": bool(freeze.get("ok") and check.get("pass")),
        "freeze": freeze,
        "disjoint_check": check,
        "deploy_test_registry": {
            "pack_id": dt_reg.get("pack_id"),
            "n": dt_reg.get("n"),
            "frozen": dt_reg.get("frozen"),
            "role": dt_reg.get("role"),
        },
        "continuity_registry": {
            "pack_id": cont_reg.get("pack_id"),
            "role": "regression_only",
        },
    }

    if not freeze.get("ok"):
        OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return 1

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
        result["ok"] = False
        OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return 1

    prev_pin = ((policy.get("lora") or {}).get("last_validate") or {}).get("mind_pass_rate")
    val_mod = _load(
        "validate_judge_adapter",
        FOUNDATION / "models" / "Training" / "code" / "validate_judge_adapter.py",
    )
    print(f"BASELINE deployed={deployed} on fresh deploy_test", flush=True)
    val = val_mod.validate_adapter(
        deployed,
        limit=60,
        max_new=64,
        case_timeout_s=120.0,
        skip_disjoint_preflight=True,  # historical train predates deploy-test quarantine
    )
    mind = float(val.get("mind_pass_rate") or 0.0)
    continuity_mind = float(val.get("continuity_mind_pass_rate") or 0.0)
    pack_id = dt_reg.get("pack_id") or (val.get("deploy_test") or {}).get("pack_id")

    state = load_gate_state()
    # Keep continuity judge-only baseline untouched for drift checks on frozen drafts.
    # New deciding pin lives on admission_policy.lora.last_validate (deploy_test).
    state["deploy_test_baseline_mind_pass"] = mind
    state["deploy_test_baseline_at"] = val.get("at")
    state["deploy_test_baseline_pack_id"] = pack_id
    state["deploy_test_baseline_note"] = (
        "P0 honest deploy baseline on post-quarantine sealed pack; "
        f"continuity_regression={continuity_mind} pack={cont_reg.get('pack_id')}"
    )
    state["continuity_regression_mind_pass"] = continuity_mind
    state["continuity_regression_pack_id"] = cont_reg.get("pack_id")
    save_gate_state(state)

    policy["lora"] = dict(policy.get("lora") or {})
    policy["lora"]["last_validate"] = {
        "steps": (policy.get("lora") or {}).get("last_validate", {}).get("steps"),
        "mind_pass_rate": mind,
        "n": val.get("n"),
        "deploy_candidate": True,
        "at": val.get("at"),
        "adapter": str(deployed).replace("\\", "/"),
        "note": (
            "P0 honest deploy-test baseline — deciding pin. "
            "Continuity pack is regression-only."
        ),
        "pack_id": pack_id,
        "pack_role": "deploy_decision",
        "clean_baseline": True,
        "continuity_mind_pass_rate": continuity_mind,
        "continuity_pack_id": cont_reg.get("pack_id"),
        "previous_continuity_pin": prev_pin,
    }
    policy["note"] = (
        f"P0 deploy-test deciding baseline mind_pass={mind} pack_id={pack_id}; "
        f"continuity_regression={continuity_mind} pack_id={cont_reg.get('pack_id')}"
    )
    _write_json(ADMISSION_POLICY_PATH, policy)

    result["validate"] = {
        "ok": val.get("ok"),
        "mind_pass_rate": mind,
        "continuity_mind_pass_rate": continuity_mind,
        "labels": val.get("labels"),
        "deploy_test": val.get("deploy_test"),
        "continuity": val.get("continuity"),
        "artifact": val.get("artifact"),
        "adapter": str(deployed).replace("\\", "/"),
    }
    result["new_baseline"] = {
        "deploy_test_mind_pass": mind,
        "deploy_test_pack_id": pack_id,
        "continuity_mind_pass": continuity_mind,
        "continuity_pack_id": cont_reg.get("pack_id"),
        "previous_pin_was_continuity": prev_pin,
    }
    result["ok"] = bool(val.get("ok")) and bool(check.get("pass")) and bool(freeze.get("ok"))
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(
        f"P0 DONE deploy_test_pack_id={pack_id} mind={mind} "
        f"continuity={continuity_mind} (regression only)",
        flush=True,
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
