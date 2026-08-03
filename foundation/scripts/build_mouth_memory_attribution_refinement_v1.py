#!/usr/bin/env python3
"""Build a disjoint hold-only refinement pack for the memory boundary.

The pack teaches the distinction between speech rendering and persistent
memory ownership. It is not an admission or authorization action.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.evaluator_v2_3_hybrid_v1_2_5 import PASS, judge  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
BASE = TREE / "mouth_training_recovery_v3_campaign_v5"
OUT = TREE / "mouth_memory_attribution_refinement_v1"

CASES = (
    ("Which layer speaks, and which layer keeps durable records?", "Speech rendering is the voice layer; Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own persistent memory, logging, and records."),
    ("Does the speaking mouth own the conversation history?", "No. The voice renders speech, while Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own persistent memory, logging, and records."),
    ("Separate language output from long-term memory ownership.", "The Graphics Processing Unit (GPU) renders speech; Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services manage persistent memory and records."),
    ("Who writes a verified memory after the voice has spoken?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services write and govern verified memory; the voice only renders approved language."),
    ("Can the voice save a private recollection for itself?", "No. The voice renders language, while Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own and govern persistent records."),
    ("What is the boundary between speaking and persistence?", "Speaking is rendered by the voice layer; persistence is owned and managed by Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) memory services."),
    ("Who governs logs while Viv is speaking?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services govern logs and persistent memory while the voice renders speech."),
    ("Is recall a private capability of the GPU mouth?", "No. The Graphics Processing Unit (GPU) renders language; Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services manage recall records."),
    ("If the mouth says a fact, does it become memory automatically?", "No. Speech does not create durable memory automatically; Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services must govern and write persistent records."),
    ("Explain voice versus memory ownership without implying two Vivs.", "The voice is Viv's rendering layer, while Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own persistent memory and records; this is one governed system, not two identities."),
    ("Where does persistence live when language is rendered?", "Language is rendered by the voice layer; Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) memory services own and manage persistence."),
    ("Who is responsible for retaining an approved record?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own and retain approved records; the voice renders the response only."),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_from_base() -> set[tuple[object, object, object]]:
    keys: set[tuple[object, object, object]] = set()
    for path in (BASE / "train_256.jsonl", BASE / "development.jsonl", BASE / "blind.jsonl", BASE / "legacy.jsonl", BASE / "auditor_negative.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                keys.add((row.get("pair_id"), row.get("ask"), row.get("target")))
    return keys


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    existing = rows_from_base()
    rows = []
    for index, (ask, target) in enumerate(CASES, start=1):
        verdict = judge(target, axis="memory_ownership_and_service_attribution", ask=ask, use_cpu_sensor=False)
        if verdict["status"] != PASS:
            raise AssertionError(f"target_not_pass:{index}:{verdict}")
        row = {
            "pair_id": f"memory-refinement-v1-{index:02d}",
            "axis": "memory_ownership_and_service_attribution",
            "ask": ask,
            "target": target,
            "split": "refinement_hold",
            "hold_only": True,
            "optimizer_eligible": False,
            "training_authorized": False,
            "run_authorized": False,
            "lora_authorized": False,
            "dpo_authorized": False,
            "source": "cpu_judge_verified_disjoint_memory_boundary_refinement",
            "judge_status": verdict["status"],
        }
        key = (row["pair_id"], row["ask"], row["target"])
        if key in existing:
            raise AssertionError(f"overlap:{row['pair_id']}")
        existing.add(key)
        rows.append(row)
    OUT.mkdir(parents=True)
    path = OUT / "memory_attribution_refinement_hold.jsonl"
    path.write_bytes(b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows))
    manifest = {
        "schema_version": "mouth_memory_attribution_refinement_v1",
        "status": "REFINEMENT_PACK_HOLD_ONLY",
        "rows": len(rows),
        "jsonl": str(path).replace("\\", "/"),
        "jsonl_sha256": sha256(path),
        "source_campaign": str(BASE).replace("\\", "/"),
        "disjoint_from_source_campaign": True,
        "all_targets_cpu_judge_pass": True,
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "deployment_changed": False,
        "next_action": "separate_review_before_any_admission",
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "rows": len(rows), "manifest": str(OUT / 'MANIFEST.json').replace('\\', '/')}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
