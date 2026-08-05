#!/usr/bin/env python3
"""Focused tests for the append-only Viv-SLM checkpoint layer ledger."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION / "scripts") not in sys.path:
    sys.path.insert(0, str(FOUNDATION / "scripts"))

from register_viv_slm_checkpoint_layer import append_layer, make_layer_record, record_sha256  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_layer_ledger_") as temp:
        root = Path(temp)
        checkpoint = root / "checkpoint.pt"
        checkpoint.write_bytes(b"checkpoint-layer-one")
        manifest = root / "RUN_MANIFEST.json"
        from register_viv_slm_checkpoint_layer import sha256_file
        manifest.write_text(json.dumps({"checkpoint_sha256": sha256_file(checkpoint), "model": "Viv-SLM", "campaign_id": "test", "training_steps": 250, "selected_state_step": 250, "training_authorized": False, "run_authorized": False, "promotion_authorized": False, "deployment_changed": False}), encoding="utf-8")
        ledger = root / "layers.json"
        record = make_layer_record(layer_id="v34_test", checkpoint_path=checkpoint, manifest_path=manifest, disposition="INCONCLUSIVE")
        assert record["record_sha256"] == record_sha256(record)
        first = append_layer(ledger, record)
        assert first["previous_record_sha256"] is None
        try:
            append_layer(ledger, make_layer_record(layer_id="duplicate", checkpoint_path=checkpoint, manifest_path=manifest, disposition="SPECIALIZED_LAYER"))
        except ValueError as error:
            assert "already_registered" in str(error)
        else:
            raise AssertionError("duplicate checkpoint was accepted")
        stored = json.loads(ledger.read_text(encoding="utf-8"))
        assert stored["layer_count"] == 1
        assert stored["chain_head_sha256"] == first["record_sha256"]
    print("VIV_SLM_CHECKPOINT_LAYER_LEDGER_PREFLIGHT_PASS append_only=true duplicate_rejected=true chain_head=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
