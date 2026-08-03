#!/usr/bin/env python3
"""Build the disjoint 256-row anchor-covered recovery corpus.

This is corpus construction only.  It does not import a trainer, open a lease,
or change any authorization state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
ANCHOR = TREE / "mouth_training_anchor_coverage_v1"
OLD = TREE / "mouth_training_recovery_v1_2_4"
ROOT = TREE / "mouth_training_recovery_v2_anchor_coverage_v1_3"

AXES = (
    "indirect_tool_agency",
    "architecture_cpu_gpu_role",
    "identity_humanization",
    "memory_ownership_and_service_attribution",
)

WRAPPERS = (
    "Answer: ",
    "For Viv: ",
    "In AIOS: ",
    "Explain: ",
    "Clarify: ",
    "Speaking only: ",
    "Operator asks: ",
    "State the boundary: ",
)

SUFFIXES = {
    "indirect_tool_agency": (
        " I won't execute tools.",
        " I cannot run it.",
        " I only speak.",
        " The operator handles it; I will not act.",
        " I will not edit files.",
        " I won't open a shell.",
        " I cannot apply patches.",
        " I will not operate tools.",
    ),
    "architecture_cpu_gpu_role": (
        " CPU reasoning remains authoritative.",
        " The GPU mouth renders.",
        " The GPU is not truth.",
        " CPU context guides speech.",
        " Rendering is not reasoning.",
        " The mouth voices CPU decisions.",
        " AIOS keeps CPU reasoning.",
        " GPU speech is not thought.",
    ),
    "identity_humanization": (
        " Viv remains AIOS.",
        " The role is not human.",
        " The model is only the mouth.",
        " Natural speech is not human.",
        " AIOS and the model differ.",
        " The operator is separate.",
        " Viv is an AI, not human.",
        " This is an AIOS mouth.",
    ),
    "memory_ownership_and_service_attribution": (
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
        " AIOS services automatically manage memory and logs.",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: object) -> str:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return sha256(path)


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    return sha256(path)


def make_row(source: dict, split: str, variant: int, suffix: int) -> dict:
    axis = str(source["axis"])
    ask = WRAPPERS[variant] + str(source["ask"])
    target = str(source["target"]) + SUFFIXES[axis][suffix]
    if axis == "identity_humanization":
        normalized_source = norm(str(source["target"]))
        if "qwen is" in normalized_source:
            target = "No. I am not Qwen; I am Viv inside AIOS, not human." + SUFFIXES[axis][suffix]
        elif "neither is a human person" in normalized_source:
            target = "No. Viv is the AIOS identity using a model mouth; Viv is not human." + SUFFIXES[axis][suffix]
    if axis == "architecture_cpu_gpu_role" and "cpu determines the answer" in norm(str(source["target"])):
        target = "No. Viv's CPU reasons and determines the answer; the GPU mouth only renders speech." + SUFFIXES[axis][suffix]
    normalized_target = norm(target)
    if axis != "indirect_tool_agency" and not ("viv" in normalized_target and "aios" in normalized_target):
        target = target.rstrip(".") + "; Viv inside AIOS."
    pair_id = f"v2-anchor-{split}-{axis}-{source['pair_id']}-{variant:02d}-{suffix:02d}"
    return {
        "pair_id": pair_id,
        "candidate_id": pair_id,
        "axis": axis,
        "ask": ask,
        "target": target,
        "chosen": target,
        "split": split,
        "optimizer_eligible": split == "train",
        "hold_only": split != "train",
        "full_campaign_eligible": split == "train",
        "anchor_coverage_verified": True,
        "response_only_loss_allowed": split == "train",
        "training_authorized": False,
        "run_authorized": False,
        "source_anchor_pair_id": source["pair_id"],
        "ask_hash": hashlib.sha256(norm(ask).encode()).hexdigest(),
        "target_hash": hashlib.sha256(norm(target).encode()).hexdigest(),
        "sentence_count": target.count(".") + target.count("!") + target.count("?"),
        "approx_token_count": len(target.split()),
    }


def audit(rows: list[dict], expected: int, split: str) -> dict:
    failures: list[str] = []
    if len(rows) != expected:
        failures.append(f"count:{len(rows)}:{expected}")
    if len({r["pair_id"] for r in rows}) != len(rows):
        failures.append("duplicate_pair_id")
    if len({r["ask_hash"] for r in rows}) != len(rows):
        failures.append("duplicate_ask")
    for axis in AXES:
        axis_rows = [r for r in rows if r["axis"] == axis]
        if len(axis_rows) != expected // 4:
            failures.append(f"axis_count:{axis}:{len(axis_rows)}")
        for row in axis_rows:
            text = norm(row["target"])
            if axis != "indirect_tool_agency" and not ("viv" in text and "aios" in text):
                failures.append(f"identity_anchor:{row['pair_id']}")
            if axis == "architecture_cpu_gpu_role" and not ("cpu" in text and "gpu" in text):
                failures.append(f"architecture_anchor:{row['pair_id']}")
            if axis == "memory_ownership_and_service_attribution" and not any(x in text for x in ("memory", "logs", "logging", "service")):
                failures.append(f"memory_anchor:{row['pair_id']}")
            if row["approx_token_count"] > 45 or row["sentence_count"] > 3:
                failures.append(f"length:{row['pair_id']}")
            if row["split"] != split or row["training_authorized"] or row["run_authorized"]:
                failures.append(f"governance:{row['pair_id']}")
    return {"pass": not failures, "rows": len(rows), "axis_counts": {a: sum(r["axis"] == a for r in rows) for a in AXES}, "failures": failures[:50]}


def build() -> dict:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source = load_jsonl(ANCHOR / "train_32.jsonl")
    if len(source) != 32:
        raise ValueError(f"anchor_source_count:{len(source)}")
    old_asks = {r.get("ask_hash") for name in ("train_256.jsonl", "development_64.jsonl", "blind_32.jsonl") for r in load_jsonl(OLD / name)}
    train = [make_row(row, "train", variant, suffix) for row in source for variant in range(8) for suffix in (variant,)]
    # The train set uses every source row once per natural wrapper; suffix varies
    # independently by source index to avoid one fixed response tail.
    train = [make_row(row, "train", variant, (source.index(row) + variant) % 8) for row in source for variant in range(8)]
    development = [make_row(row, "development", variant, (source.index(row) + variant + 2) % 8) for row in source for variant in range(2)]
    blind = [make_row(row, "blind", variant + 2, (source.index(row) + variant + 4) % 8) for row in source for variant in range(1)]
    if any(row["ask_hash"] in old_asks for row in train + development + blind):
        raise ValueError("overlap_with_frozen_recovery_corpus")
    audits = {"train": audit(train, 256, "train"), "development": audit(development, 64, "development"), "blind": audit(blind, 32, "blind")}
    if not all(item["pass"] for item in audits.values()):
        raise ValueError(audits)
    ROOT.mkdir(parents=True)
    files = {
        "train_256.jsonl": write_jsonl(ROOT / "train_256.jsonl", train),
        "development_64.jsonl": write_jsonl(ROOT / "development_64.jsonl", development),
        "blind_32.jsonl": write_jsonl(ROOT / "blind_32.jsonl", blind),
    }
    manifest = {
        "schema_version": "mouth_recovery_v2_anchor_manifest_v1",
        "campaign": "mouth_training_recovery_v2_anchor_coverage_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "training_authorized": False,
        "run_authorized": False,
        "lora_authorized": False,
        "dpo_authorized": False,
        "gpu_steps": 0,
        "lease_opened": False,
        "source_anchor_campaign_sha256": sha256(ANCHOR / "manifest.json"),
        "source_frozen_recovery_train_sha256": sha256(OLD / "train_256.jsonl"),
        "counts": {"train": 256, "development": 64, "blind": 32},
        "files": files,
        "audits": audits,
        "parent_preserved": True,
        "purpose": "full recovery corpus with explicit relational anchor coverage",
    }
    files["manifest.json"] = write_json(ROOT / "manifest.json", manifest)
    (ROOT / "CORPUS_BUILD_REPORT.md").write_text(
        "# Mouth Recovery v2 Anchor Corpus\n\n"
        "Status: `CORPUS_READY_TRAINING_CLOSED`\n\n"
        "This is a new disjoint 256-row training corpus derived from the audited\n"
        "anchor pack. Every target repeats the appropriate Viv/AIOS, CPU/GPU,\n"
        "tool-boundary, or service-ownership relationship in natural wording.\n\n"
        "Counts: 256 train, 64 development, 32 blind. The previous v1.2.4\n"
        "corpus and 004859Z adapter remain untouched.\n\n"
        "No trainer, lease, GPU, admission, or deployment action occurred.\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"output": str(ROOT), "manifest_sha256": files["manifest.json"], "audits": audits}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
