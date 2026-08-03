#!/usr/bin/env python3
"""Create read-only linear adapter blends for composition testing."""
from __future__ import annotations

import json
from pathlib import Path

from safetensors.torch import load_file, save_file

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_adapter_blends_v1"
PARENT = FOUNDATION / "models/Training/runs/mouth_cross_axis_micro_v1/adapter_step_8"
IDENTITY = FOUNDATION / "models/Training/runs/mouth_identity_complete_v1/adapter_step_96"


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=False)
    parent = load_file(str(PARENT / "adapter_model.safetensors"), device="cpu")
    identity = load_file(str(IDENTITY / "adapter_model.safetensors"), device="cpu")
    if set(parent) != set(identity):
        raise ValueError("adapter_key_sets_differ")
    alphas = (0.10, 0.25, 0.50)
    manifest = {"schema_version": "mouth_adapter_blends_manifest_v1", "status": "READ_ONLY_COMPOSITION_CANDIDATES", "parent": str(PARENT).replace("\\", "/"), "identity_candidate": str(IDENTITY).replace("\\", "/"), "alphas": list(alphas), "promotion_authorized": False, "deployment_changed": False}
    for alpha in alphas:
        name = f"alpha_{str(alpha).replace('.', 'p')}"
        target = ROOT / name
        target.mkdir(parents=True, exist_ok=False)
        tensors = {key: parent[key] * (1.0 - alpha) + identity[key] * alpha for key in parent}
        save_file(tensors, str(target / "adapter_model.safetensors"), metadata={"blend_alpha": str(alpha), "parent": str(PARENT), "identity": str(IDENTITY)})
        config = json.loads((PARENT / "adapter_config.json").read_text(encoding="utf-8"))
        (target / "adapter_config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        manifest[name] = {"alpha": alpha, "path": str(target).replace("\\", "/")}
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
