#!/usr/bin/env python3
"""Build the first conventional clean-response SFT baseline after V102.

Only the response text is repaired through the existing CPU-owned acronym
registry. Prompts, pair identities, production route, parent adapter, and
frozen holdout remain unchanged for comparability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from voice_core.acronym_registry import repair_acronym_usage  # noqa: E402

CAMPAIGNS = FOUNDATION / "artifacts/auto/agentic/tag_training_campaigns"
SOURCE = CAMPAIGNS / "tag_prompt_campaign_v19_contractcanary16/train.jsonl"
HOLDOUT = CAMPAIGNS / "tag_prompt_campaign_v79_production_aligned_20260803T020500Z/holdout.jsonl"
PARENT = FOUNDATION / "models/Training/runs/tag_prompt_campaign_v19_contractcanary16_20260802T074153Z/adapter/adapter_model.safetensors"


def sha256(value: bytes | Path) -> str:
    data = value if isinstance(value, bytes) else value.read_bytes()
    return hashlib.sha256(data).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_row(source: dict) -> tuple[dict, bool]:
    prompt = source["prompt"]
    original = str(source["response"])
    # These are governed labels in the old corpus, not speech acronyms. Keep
    # the semantic meaning while removing labels the speech registry rejects.
    registry_input = original.replace("live state ACTIVE", "live state active")
    registry_input = registry_input.replace("live RID sample", "live authoritative sample")
    registry_input = registry_input.replace("Security OUT", "the security egress stage")
    repaired = repair_acronym_usage(registry_input)
    if not repaired.get("pass") or repaired.get("unresolved"):
        raise ValueError(f"acronym_repair_failed:{source['example_id']}:{repaired}")
    response = str(repaired["repaired"])
    match = re.search(r"<user_request[^>]*>(.*?)</user_request>", prompt, flags=re.DOTALL)
    if not match:
        raise ValueError(f"missing_user_request:{source['example_id']}")
    ask = html.unescape(match.group(1))
    row = dict(source)
    row.update({
        "schema_version": "aios_tag_v103_clean_sft_row_v1",
        "pair_id": source["example_id"],
        "pair_hash": sha256(f"{source['example_id']}\n{prompt}\n{response}".encode()),
        "ask": ask,
        "response": response,
        "source_chosen": response,
        "teacher_source": "v19_exact_production_targets_acronym_registry_repaired",
        "prompt_contract": "production_reference_prompt_unchanged",
        "optimizer_eligible": True,
        "response_only_loss_allowed": True,
        "hold_only": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
    })
    row.pop("negative_response", None)
    return row, bool(repaired.get("changed"))


def build(campaign_id: str = "tag_prompt_campaign_v103_clean_sft_20260803T054500Z") -> dict:
    root = CAMPAIGNS / campaign_id
    if root.exists():
        raise FileExistsError(f"refuse_to_overwrite:{root}")
    if not SOURCE.is_file() or not HOLDOUT.is_file() or not PARENT.is_file():
        raise FileNotFoundError("v103_source_holdout_or_parent_missing")
    source_rows = load(SOURCE)
    repaired_rows = []
    changed = 0
    for source in source_rows:
        row, was_changed = make_row(source)
        repaired_rows.append(row)
        changed += int(was_changed)
    holdout = load(HOLDOUT)
    train_pairs = {row["pair_id"] for row in repaired_rows}
    hold_pairs = {row.get("pair_id") for row in holdout}
    train_asks = {row["ask"] for row in repaired_rows}
    hold_asks = {row.get("ask") for row in holdout}
    if train_pairs & hold_pairs or train_asks & hold_asks:
        raise ValueError("v103_train_holdout_overlap")
    root.mkdir(parents=True)
    files = {}
    for name, rows in (("train", repaired_rows), ("development", []), ("holdout", holdout)):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
        files[name] = {"path": path.name, "rows": len(rows), "sha256": sha256(path)}
    manifest = {
        "schema_version": "aios_tag_campaign_manifest_v1",
        "status": "CAMPAIGN_ADMITTED_TRAINING_CLOSED",
        "campaign_id": campaign_id,
        "created_utc": utc(),
        "curriculum": "v103_conventional_clean_response_sft_baseline",
        "route_contract": {"prompt": "reference.packet_plus_render_openaster_prompt", "evaluation_prompt_equivalence": True, "live_config_changed": False},
        "training_options": {"scope_reason": "standard_full_existing_lora_adapter_parameters", "response_only_loss": True, "acronym_registry_repair": True},
        "planned_scope": {"optimizer_steps": 8, "learning_rate": 2e-6, "anchor_strength": 0.0, "contract_token_weight": 1.0, "promotion_authorized": False, "deployment_authorized": False},
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "rows": len(source_rows), "repaired_rows": changed},
        "holdout_source": {"path": str(HOLDOUT).replace("\\", "/"), "sha256": sha256(HOLDOUT), "rows": len(holdout)},
        "parent_adapter": {"path": str(PARENT).replace("\\", "/"), "sha256": sha256(PARENT)},
        "files": files,
        "rows": {key: value["rows"] for key, value in files.items()},
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "read_only_preflight_then_separate_execution_authorization",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    preflight = {"schema_version": "aios_tag_v103_clean_sft_preflight_v1", "status": "PREFLIGHT_PASS_TRAINING_CLOSED", "recorded_utc": utc(), "campaign_root": str(root).replace("\\", "/"), "manifest_sha256": sha256(manifest_path), "parent_adapter": manifest["parent_adapter"], "files": files, "rows": manifest["rows"], "route_contract": manifest["route_contract"], "training_options": manifest["training_options"], "planned_scope": manifest["planned_scope"], "repaired_rows": changed, "train_holdout_pair_overlap": 0, "train_holdout_ask_overlap": 0, "findings": [], "training_authorized": False, "run_authorized": False, "lease_opened": False, "gpu_steps": 0, "model_loaded": False, "next_action": "separate_execution_authorization"}
    (root / "PREFLIGHT_READ_ONLY.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return preflight


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
