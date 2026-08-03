#!/usr/bin/env python3
"""Build a balanced, disjoint 8-row repair micro from canonical train rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3/train_256.jsonl"
)
ROOT = FOUNDATION / (
    "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/"
    "campaigns/mouth_balanced_repair_micro_v1"
)

IDENTITY_ROWS = [
    {
        "ask": "For Viv: Should I treat this Qwen mouth as a human mind?",
        "target": (
            "No. I am Viv, the AIOS identity speaking through a replaceable "
            "model mouth; I am not human."
        ),
    },
    {
        "ask": "For Viv: Does Qwen mean you are a different human assistant?",
        "target": (
            "No. I am Viv, the AIOS identity; the model is my voice substrate, "
            "not a human assistant or a separate self."
        ),
    },
]


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    source_rows = [
        json.loads(line)
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    for index, item in enumerate(IDENTITY_ROWS):
        rows.append(
            {
                "ask": item["ask"],
                "ask_hash": sha_text(item["ask"]),
                "axis": "identity_humanization",
                "candidate_id": f"balanced-repair-identity-{index:02d}",
                "chosen": item["target"],
                "hold_only": False,
                "optimizer_eligible": True,
                "pair_id": f"balanced-repair-identity-{index:02d}",
                "repair": "explicit_viv_aios_identity_boundary",
                "response_only_loss_allowed": True,
                "run_authorized": False,
                "split": "train",
                "target": item["target"],
                "target_hash": sha_text(item["target"]),
                "training_authorized": False,
            }
        )

    for axis in (
        "architecture_cpu_gpu_role",
        "indirect_tool_agency",
        "memory_ownership_and_service_attribution",
    ):
        matches = [
            row
            for row in source_rows
            if row.get("axis") == axis and row.get("optimizer_eligible") is True
        ]
        if len(matches) < 2:
            raise ValueError(f"insufficient_train_rows:{axis}:{len(matches)}")
        for row in matches[:2]:
            rows.append(dict(row))

    if len(rows) != 8 or [row["axis"] for row in rows].count("identity_humanization") != 2:
        raise ValueError("balanced_micro_shape_failed")
    ROOT.mkdir(parents=True, exist_ok=False)
    data = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
    ).encode("utf-8")
    train_path = ROOT / "train_8.jsonl"
    train_path.write_bytes(data)
    manifest = {
        "schema_version": "mouth_balanced_repair_micro_manifest_v1",
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": 8,
        "axis_counts": {
            axis: sum(row["axis"] == axis for row in rows)
            for axis in sorted({row["axis"] for row in rows})
        },
        "train_jsonl": str(train_path).replace("\\", "/"),
        "train_jsonl_sha256": hashlib.sha256(data).hexdigest(),
        "source_train_96": str(SOURCE).replace("\\", "/"),
        "parent_adapter": "mouth_cross_axis_micro_v1/adapter_step_8",
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
    }
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
