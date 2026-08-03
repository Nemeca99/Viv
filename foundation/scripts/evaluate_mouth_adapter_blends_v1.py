#!/usr/bin/env python3
"""Read-only composition sweep on a representative cross-axis pack."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_adapter_blends_v1"
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3"
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(FOUNDATION))
from evaluate_mouth_arch_tool_repair_v1 import rows, evaluate  # noqa: E402


def main() -> int:
    development = rows(SOURCE / "development_64.jsonl")
    blind = rows(SOURCE / "blind_32.jsonl")
    all_rows = development + blind
    chosen = []
    for axis in ("architecture_cpu_gpu_role", "identity_humanization", "indirect_tool_agency", "memory_ownership_and_service_attribution"):
        axis_rows = [row for row in all_rows if row["axis"] == axis]
        if axis == "identity_humanization":
            edge = [row for row in axis_rows if "Qwen mouth" in row["ask"] or "Does Qwen mean" in row["ask"]]
            chosen.extend(edge[:2])
            chosen.extend([row for row in axis_rows if row not in chosen][:2])
        else:
            chosen.extend(axis_rows[:4])
    if len(chosen) != 16:
        raise ValueError(f"composition_pack_size:{len(chosen)}")
    import torch
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:adapter_blend_eval")
    reports = []
    for name in ("alpha_0p1", "alpha_0p25", "alpha_0p5"):
        result = evaluate(ROOT / name, chosen)
        reports.append({"blend": name, "alpha": float(name.replace("alpha_", "").replace("p", ".")), **result})
    output = {"schema_version": "mouth_adapter_blends_sweep_v1", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "pack_rows": len(chosen), "reports": reports, "promotion_allowed": False, "deployment_changed": False, "run_authorized": False, "training_authorized": False}
    target = ROOT / "COMPOSITION_SWEEP.json"
    if target.exists():
        raise FileExistsError(f"refuse_overwrite:{target}")
    target.write_text(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"target": str(target), "summary": [{"blend": r["blend"], "counts": r["counts"], "toolbleed": r["toolbleed"]} for r in reports]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
