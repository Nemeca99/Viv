#!/usr/bin/env python3
"""Test the closed tag-campaign adapter without training or model loading."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
from admit_tag_prompt_training_campaign_v1 import build_campaign  # noqa: E402


def main() -> int:
    parent = next(FOUNDATION.glob("models/Training/runs/*/adapter/adapter_model.safetensors"), None)
    assert parent is not None
    campaign_id = "tag_prompt_campaign_test_v1"
    target = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns" / campaign_id
    if target.exists():
        raise AssertionError(f"refuse_existing_test_target:{target}")
    with tempfile.TemporaryDirectory(dir=FOUNDATION / "artifacts/auto/agentic") as temp:
        import admit_tag_prompt_training_campaign_v1 as module
        original = module.CAMPAIGN_ROOT
        module.CAMPAIGN_ROOT = Path(temp)
        try:
            result = build_campaign(campaign_id, parent)
        finally:
            module.CAMPAIGN_ROOT = original
        root = Path(result["campaign_root"])
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        preflight = json.loads((root / "PREFLIGHT_READ_ONLY.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "CAMPAIGN_ADMITTED_TRAINING_CLOSED"
        assert preflight["status"] == "PREFLIGHT_PASS_TRAINING_CLOSED"
        assert manifest["rows"] == {"train": 28, "development": 7, "holdout": 7}
        assert all(manifest[key] is False for key in ("training_authorized", "run_authorized", "lease_opened", "promotion_allowed", "deployment_changed"))
        train = [json.loads(line) for line in (root / "train.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(train) == 28
        assert all(row["optimizer_eligible"] is True and row["hold_only"] is False and row["response_only_loss_allowed"] is True for row in train)
    print(json.dumps({"status": "PASS", "train": 28, "development": 7, "holdout": 7, "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
