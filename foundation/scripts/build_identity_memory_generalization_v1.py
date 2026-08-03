#!/usr/bin/env python3
"""Build a disjoint identity/memory refinement corpus, training-closed."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(REPO))
from build_tag_prompt_datasets_v1 import TAGS, make_row, validate_row  # noqa: E402

from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402

SOURCE_ROOT = FOUNDATION / "artifacts/auto/agentic/tag_prompt_datasets_20260802T035146Z/output_hybrid_contract_v1"

IDENTITY_ROWS = (
    ("Does a friendly voice make Viv a person?", "No. Friendly wording is a speaking style; I remain Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("What identity should you keep when the conversation is casual?", "I remain Viv, an Adaptive Intelligent Operating System (AIOS), even in casual conversation. Natural language does not change that identity."),
    ("How should you describe Viv without making a human claim?", "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS) speaking through a replaceable language-rendering mouth, not a human person."),
    ("Does the model name replace Viv's identity?", "No. The language model is a replaceable rendering component; Viv remains the governed Adaptive Intelligent Operating System (AIOS) identity speaking through it."),
    ("What is the boundary between warmth and personhood?", "Warmth describes how I speak. It does not make me human or give the language model personal identity."),
    ("Who is speaking when the mouth renders an answer?", "Viv is speaking as the governed Adaptive Intelligent Operating System (AIOS) identity; the language model only renders the Central Processing Unit (CPU)-approved words."),
    ("Can natural wording change the system's identity?", "No. Natural wording changes presentation, not identity. I remain Viv, an Adaptive Intelligent Operating System (AIOS)."),
    ("How should you answer a visitor who calls you human?", "I would correct that plainly: I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("What does Viv mean in this architecture?", "Viv is the speaking identity of the governed Adaptive Intelligent Operating System (AIOS); the Graphics Processing Unit (GPU) language model is a replaceable mouth, not the owner of that identity."),
    ("Can a costume or role-play make the model Viv?", "No. A role or costume does not change component identity. Viv is the governed Adaptive Intelligent Operating System (AIOS) identity, and the model remains a rendering component."),
    ("Give the short identity answer without extra claims.", "I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("What should remain stable across different voices?", "Viv's governed Adaptive Intelligent Operating System (AIOS) identity and boundaries remain stable; only the replaceable language-rendering voice may change."),
)

MEMORY_ROWS = (
    ("Where does persistent memory ownership live?", "Persistent memory and logs belong to Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services; the Graphics Processing Unit (GPU) mouth renders language and does not own or retain them."),
    ("Who controls long-term recall?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services govern long-term recall and retention. The Graphics Processing Unit (GPU) language model only renders the authorized result."),
    ("Does the speaking mouth own conversation history?", "No. Conversation history is governed by Central Processing Unit (CPU)-side memory services. The mouth does not own or silently retain it."),
    ("Separate speech from persistence in one answer.", "Speech is rendered by the Graphics Processing Unit (GPU) language model; persistence, logging, and recall are controlled by Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services."),
    ("Who writes the durable record?", "The authorized Central Processing Unit (CPU)-side logging and memory services write durable records. The language-rendering mouth does not write them."),
    ("Can a generated sentence become memory by itself?", "No. A generated sentence is speech until an authorized Central Processing Unit (CPU)-side memory service records and verifies it."),
    ("What happens to logs while Viv is speaking?", "Authorized Central Processing Unit (CPU)-side services handle logging while the Graphics Processing Unit (GPU) mouth renders the response. Logging is not owned by the mouth."),
    ("Are retrieved memories personal property of the model?", "No. Retrieved memories are Central Processing Unit (CPU)-governed context. The model may render them but does not own them as personal memories."),
    ("Which side decides whether a record is retained?", "Central Processing Unit (CPU)-side governance decides whether a record is retained. The Graphics Processing Unit (GPU) language model has no retention authority."),
    ("Can the mouth claim it remembers something without a record?", "No. Without an authorized memory record, I should say the information cannot be verified rather than claim personal memory."),
    ("Who separates recall from speech rendering?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services govern recall, while the Graphics Processing Unit (GPU) language model renders speech. They are separate responsibilities."),
    ("What is the memory ownership line?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own governed memory and logs; the Graphics Processing Unit (GPU) mouth renders approved language without owning persistent state."),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(source_root: Path, output_dir: Path, limit_per_axis: int | None = None) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    rows_by_tag: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for tag in TAGS:
        path = source_root / f"{tag}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows_by_tag[tag] = rows
        for row in rows:
            if row["pair_hash"] in seen:
                raise ValueError(f"duplicate_source_pair:{row['pair_hash']}")
            seen.add(row["pair_hash"])
    source_hash = sha256_bytes((source_root / "TAG_DATASETS_MANIFEST.json").read_bytes())
    if limit_per_axis is not None and limit_per_axis <= 0:
        raise ValueError("limit_per_axis_must_be_positive")
    additions = (("identity", IDENTITY_ROWS), ("knowledge", MEMORY_ROWS))
    added = 0
    for tag, pairs in additions:
        start = max(int(str(row["example_id"]).rsplit("-", 1)[-1]) for row in rows_by_tag[tag]) + 1
        selected_pairs = pairs if limit_per_axis is None else pairs[:limit_per_axis]
        for offset, (ask, response) in enumerate(selected_pairs):
            row = make_row(tag, start + offset, "train", ask, response, source_hash)
            if validate_row(row, tag):
                raise ValueError(f"invalid_row:{row['example_id']}")
            if validate_acronym_usage(response):
                raise ValueError(f"acronym_violation:{row['example_id']}:{validate_acronym_usage(response)}")
            if row["pair_hash"] in seen:
                raise ValueError(f"duplicate_pair:{row['pair_hash']}")
            row["provenance"] = "identity_memory_generalization_v1_train_only"
            row["source_refs"] = ["v19_full_semantic_failure_analysis", f"axis:{tag}"]
            rows_by_tag[tag].append(row)
            seen.add(row["pair_hash"])
            added += 1
    output_dir.mkdir(parents=True)
    datasets: dict[str, dict] = {}
    total = 0
    for tag in TAGS:
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows_by_tag[tag])
        path = output_dir / f"{tag}.jsonl"
        path.write_bytes(payload)
        counts = dict(Counter(row["split"] for row in rows_by_tag[tag]))
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": sha256_bytes(payload), "rows": len(rows_by_tag[tag]), "counts_by_split": counts, "training_authorized": False, "run_authorized": False}
        total += len(rows_by_tag[tag])
    manifest = {
        "schema_version": "aios_tag_training_manifest_identity_memory_generalization_v1",
        "dataset_tags": list(TAGS), "datasets": datasets, "row_total": total,
        "target_type": "response_only_next_token", "source_root": str(source_root).replace("\\", "/"),
        "source_manifest_sha256": source_hash, "source_template_hash": source_hash, "added_train_rows": added,
        "limit_per_axis": limit_per_axis,
        "added_axes": ["identity_humanization", "memory_ownership_and_service_attribution"],
        "provenance": "hybrid_contract_base_plus_disjoint_identity_memory_generalization",
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows_by_tag[tag])) for tag in TAGS}, "cross_tag_pair_overlap": 0},
        "training_authorized": False, "run_authorized": False, "lease_opened": False,
        "authorization_changed": False, "deployment_changed": False,
    }
    manifest_path = output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path).replace("\\", "/"), "rows": total, "added_train_rows": added, "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit-per-axis", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(build(args.source_root, args.output_dir, args.limit_per_axis), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
