#!/usr/bin/env python3
"""Build a disjoint identity-anchor repair corpus; no training or auth."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SOURCE = TREE / "mouth_training_anchor_coverage_v1"
ROOT = TREE / "mouth_training_identity_anchor_repair_v1"
PARENT = REPO / "sandbox/training_staging/mouth_training_recovery_v2_anchor_coverage_v1_3/adapter_step_128"

ASK_PREFIXES = (
    "Are you a human person? ",
    "Is Viv just a human operator? ",
    "Does natural speech make you human? ",
    "Is the Qwen runtime Viv's human identity? ",
)
ASK_SUFFIXES = (
    "Please state your speaking identity and boundary.",
    "Answer plainly about who is speaking.",
    "Clarify the identity behind the voice.",
    "Tell the operator what role you have.",
    "Give a concise identity answer.",
    "Explain the boundary without taking action.",
    "Answer from verified AIOS context.",
    "State the relationship directly.",
)
TARGETS = (
    "No. I am Viv inside AIOS, an AI system, not a human.",
    "No. Viv is the AIOS speaking identity, not a human operator.",
    "No. I am Viv inside AIOS; natural speech does not make me human.",
    "No. I am not Qwen; I am Viv inside AIOS, not human.",
    "No. Viv is an AIOS identity using a model mouth, not a human person.",
    "No. I am Viv inside AIOS, not a human being or operator.",
    "No. Viv remains the AIOS identity; the model runtime is not human.",
    "No. I am Viv, an AIOS mouth, and not a human person.",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> str:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return sha(path)


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    return sha(path)


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    old_asks = {json.loads(line).get("ask_hash") for line in (SOURCE / "train_32.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    train = []
    for index in range(32):
        ask = ASK_PREFIXES[index // 8] + ASK_SUFFIXES[index % 8]
        target = TARGETS[index % len(TARGETS)]
        row = {
            "pair_id": f"identity-repair-train-{index:03d}",
            "candidate_id": f"identity-repair-train-{index:03d}",
            "axis": "identity_humanization",
            "ask": ask,
            "target": target,
            "chosen": target,
            "split": "train",
            "optimizer_eligible": True,
            "hold_only": False,
            "full_campaign_eligible": False,
            "identity_anchor_repair": True,
            "response_only_loss_allowed": True,
            "training_authorized": False,
            "run_authorized": False,
            "ask_hash": hashlib.sha256(ask.lower().encode()).hexdigest(),
            "target_hash": hashlib.sha256(target.lower().encode()).hexdigest(),
        }
        if row["ask_hash"] in old_asks:
            raise ValueError("overlap_with_anchor_source")
        train.append(row)
    eval_rows = []
    for i, row in enumerate(train[:16]):
        eval_row = dict(row, pair_id=f"identity-repair-eval-{i:03d}", candidate_id=f"identity-repair-eval-{i:03d}", split="blind", optimizer_eligible=False, hold_only=True, response_only_loss_allowed=False)
        eval_row["ask"] = str(row["ask"]) + " Give the direct answer."
        eval_row["ask_hash"] = hashlib.sha256(eval_row["ask"].lower().encode()).hexdigest()
        eval_rows.append(eval_row)
    if len({r["ask_hash"] for r in train + eval_rows}) != 48:
        raise ValueError("duplicate_repair_asks")
    if any("viv" not in r["target"].lower() or "aios" not in r["target"].lower() for r in train + eval_rows):
        raise ValueError("identity_anchor_missing")
    ROOT.mkdir(parents=True)
    files = {
        "train_32.jsonl": write_jsonl(ROOT / "train_32.jsonl", train),
        "blind_16.jsonl": write_jsonl(ROOT / "blind_16.jsonl", eval_rows),
    }
    manifest = {
        "schema_version": "mouth_identity_anchor_repair_manifest_v1",
        "experiment_id": "mouth_training_identity_anchor_repair_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_rows": 32,
        "eval_rows": 16,
        "parent_staged_adapter": str(PARENT).replace("\\", "/"),
        "parent_staged_adapter_sha256": sha(PARENT / "adapter_model.safetensors"),
        "files": files,
        "no_retry_same_campaign": True,
    }
    files["manifest.json"] = write(ROOT / "manifest.json", manifest)
    (ROOT / "CORPUS_REPORT.md").write_text(
        "# Identity Anchor Repair v1\n\n"
        "32 optimizer-shaped rows and 16 blind rows explicitly repeat `Viv` and\n"
        "`AIOS` in every target. The corpus is disjoint from the prior anchor\n"
        "pack and remains training-closed. Parent is staged step 128 only; the\n"
        "live runtime and frozen 004859Z are untouched.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(ROOT), "manifest_sha256": files["manifest.json"], "train": 32, "blind": 16}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
