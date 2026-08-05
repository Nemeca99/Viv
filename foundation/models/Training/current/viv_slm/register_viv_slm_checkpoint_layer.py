#!/usr/bin/env python3
"""Append an immutable Viv-SLM checkpoint layer to the current ledger.

This is the canonical current-package registration helper.  The historical
copy under ``legacy/viv_slm`` remains frozen for provenance; current
supervision must not depend on that archive.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

try:
    from paths import FOUNDATION, VIV_ROOT
except ImportError:  # pragma: no cover - direct script fallback
    FOUNDATION = Path(__file__).resolve().parents[4]
    VIV_ROOT = FOUNDATION.parent

DEFAULT_LEDGER = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_checkpoint_layers.json"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def record_sha256(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    return sha256(_canonical(body)).hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"layer_ledger_expected_object:{path}")
    return value


def make_layer_record(
    *,
    layer_id: str,
    checkpoint_path: Path,
    manifest_path: Path,
    disposition: str,
    parent_checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    if not layer_id or not layer_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("layer_id_must_be_simple_identifier")
    if disposition not in {
        "ACCEPTED_PARETO_PROGRESS",
        "REJECTED_AS_WORKING_PARENT_RETAINED_LAYER",
        "SPECIALIZED_LAYER",
        "INCONCLUSIVE",
    }:
        raise ValueError("layer_disposition_invalid")
    if not checkpoint_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("layer_checkpoint_or_manifest_missing")
    manifest = _read_json(manifest_path)
    checkpoint_sha = sha256_file(checkpoint_path)
    if str(manifest.get("checkpoint_sha256") or "").upper() != checkpoint_sha:
        raise ValueError("layer_checkpoint_manifest_hash_mismatch")
    parent = parent_checkpoint_path
    if parent is None:
        warm_start = manifest.get("warm_start_checkpoint")
        if isinstance(warm_start, str) and warm_start:
            parent = VIV_ROOT / Path(warm_start.replace("/", "\\"))
    parent_sha = sha256_file(parent) if parent is not None and parent.is_file() else None
    record = {
        "schema_version": "viv_slm_checkpoint_layer_v1",
        "layer_id": layer_id,
        "checkpoint": str(checkpoint_path).replace("\\", "/"),
        "checkpoint_sha256": checkpoint_sha,
        "manifest": str(manifest_path).replace("\\", "/"),
        "manifest_sha256": sha256_file(manifest_path),
        "parent_checkpoint": str(parent).replace("\\", "/") if parent else None,
        "parent_checkpoint_sha256": parent_sha,
        "vocab_sha256": manifest.get("vocab_sha256"),
        "model": manifest.get("model"),
        "campaign_id": manifest.get("campaign_id"),
        "training_steps": manifest.get("training_steps"),
        "selected_state_step": manifest.get("selected_state_step"),
        "best_validation_nll": manifest.get("best_validation_nll"),
        "best_validation_accuracy": manifest.get("best_validation_accuracy"),
        "halt_reason": manifest.get("halt_reason"),
        "authority": {
            "training_authorized": manifest.get("training_authorized"),
            "run_authorized": manifest.get("run_authorized"),
            "promotion_authorized": manifest.get("promotion_authorized"),
            "deployment_changed": manifest.get("deployment_changed"),
            "live_runtime_mutation": manifest.get("aifl_feedback_live_runtime_mutation", False),
        },
        "disposition": disposition,
        "composition_policy": "compose_as_new_candidate_preserve_all_parents",
    }
    record["record_sha256"] = record_sha256(record)
    return record


def append_layer(ledger_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    ledger = _read_json(ledger_path) if ledger_path.is_file() else {
        "schema_version": "viv_slm_checkpoint_layer_ledger_v1",
        "layers": [],
        "chain_head_sha256": None,
    }
    layers = ledger.get("layers")
    if not isinstance(layers, list):
        raise ValueError("layer_ledger_layers_invalid")
    if any(item.get("checkpoint_sha256") == record["checkpoint_sha256"] for item in layers if isinstance(item, dict)):
        raise ValueError("layer_checkpoint_already_registered")
    record["previous_record_sha256"] = ledger.get("chain_head_sha256")
    record["record_sha256"] = record_sha256(record)
    layers.append(record)
    ledger["chain_head_sha256"] = record["record_sha256"]
    ledger["layer_count"] = len(layers)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--disposition", required=True)
    parser.add_argument("--parent-checkpoint", type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    record = make_layer_record(
        layer_id=args.layer_id,
        checkpoint_path=args.checkpoint,
        manifest_path=args.manifest,
        disposition=args.disposition,
        parent_checkpoint_path=args.parent_checkpoint,
    )
    result = append_layer(args.ledger, record)
    print(json.dumps({"status": "VIV_SLM_CHECKPOINT_LAYER_REGISTERED", "layer_id": result["layer_id"], "record_sha256": result["record_sha256"], "chain_head_sha256": result["record_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
