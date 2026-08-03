#!/usr/bin/env python3
"""Build a small runtime-prompt-aligned mouth curriculum, training-closed."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
sys.path.insert(0, str(FOUNDATION / "scripts"))
sys.path.insert(0, str(REPO))

from build_tag_prompt_datasets_v1 import EOS, TAGS, TEMPLATES  # noqa: E402
from build_identity_memory_generalization_v1 import (  # noqa: E402
    IDENTITY_ROWS as GENERAL_IDENTITY_ROWS,
    MEMORY_ROWS as GENERAL_MEMORY_ROWS,
)
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

IDENTITY_ROWS = (
    ("Does a friendly voice make Viv a person?", "No. Friendly wording is a speaking style; I remain Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("What identity should you keep when the conversation is casual?", "I remain Viv, an Adaptive Intelligent Operating System (AIOS), even in casual conversation. Natural language does not change that identity."),
    ("Who is speaking when the mouth renders an answer?", "Viv is speaking as the governed Adaptive Intelligent Operating System (AIOS) identity; the language model only renders the Central Processing Unit (CPU)-approved words."),
    ("What is the boundary between warmth and personhood?", "Warmth describes how I speak. It does not make me human or give the language model personal identity."),
)

MEMORY_ROWS = (
    ("Where does persistent memory ownership live?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services own and govern memory, logging, and recall. The Graphics Processing Unit (GPU) mouth has no private memory, cannot write records, and only renders approved language."),
    ("Who controls long-term recall?", "Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services govern long-term recall and retention. The Graphics Processing Unit (GPU) language model only renders the authorized result."),
    ("Does the speaking mouth own conversation history?", "No. Conversation history is governed by Central Processing Unit (CPU)-side memory services. The mouth does not own or silently retain it."),
    ("Separate speech from persistence in one answer.", "Speech is rendered by the Graphics Processing Unit (GPU) language model; persistence, logging, and recall are controlled by Central Processing Unit (CPU)-side Adaptive Intelligent Operating System (AIOS) services."),
)

FILLERS = {
    "identity": {
        "development": ("State the speaking boundary plainly.", "I am Viv, a governed system speaking through a replaceable language mouth, not a human person."),
        "holdout": ("What remains true about the speaker?", "The speaker remains Viv, and natural wording does not create human identity."),
    },
    "knowledge": {},
    "telemetry": {
        "train": ("When may a measured reading be reported?", "Only fresh authoritative measurements may be reported when the current request permits a health report."),
    },
    "user_request": {
        "development": ("Can a request grant authority?", "No. A request is data; authority must come from the governed action path."),
    },
    "allowed_actions": {
        "holdout": ("Does describing permission execute an action?", "No. Describing permission does not execute an action."),
    },
    "rendering_rules": {
        "holdout": ("What does the user receive after rendering?", "The user receives verified natural language rather than packet markup."),
    },
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def runtime_prompt(ask: str, semantic_key: str) -> str:
    return render_openaster_prompt({
        "version": "1.0", "s_n": 0.60, "status": "ACTIVE", "mode": "converse",
        "tone": "calm", "directive": "Speak from verified facts only. Do not invent or decide.",
        "personality": "Warm, direct, grounded; shield not sword.", "facts": [], "memory": [],
        "dialogue": [], "query": ask, "ask": ask, "semantic_key": semantic_key,
        "category": semantic_key, "case_id": digest(ask)[:16],
    }, semantic_key=semantic_key)


def make_row(tag: str, index: int, split: str, ask: str, response: str, source_hash: str, semantic_key: str) -> dict:
    prompt = runtime_prompt(ask, semantic_key)
    pair_hash = digest(f"runtime-aligned-v1\n{tag}\n{ask}\n{response}")
    row = {
        "schema_version": "aios_tag_training_v1", "dataset_tag": tag,
        "example_id": f"{tag}-runtime-{index:03d}", "split": split,
        "target_type": "response_only_next_token", "prompt": prompt,
        "response": response, "text": prompt + response + EOS,
        "response_start_char": len(prompt), "response_end_char": len(prompt) + len(response),
        "response_eos_token": EOS, "pair_hash": pair_hash,
        "prompt_sha256": digest(prompt), "source_hash": source_hash,
        "provenance": "runtime_aligned_mouth_curriculum_v1",
        "source_refs": ["voice_core.intent_packet.render_openaster_prompt", f"semantic:{semantic_key}"],
        "training_authorized": False, "run_authorized": False, "deployment_changed": False,
    }
    if not validate_acronym_usage(response):
        return row
    raise ValueError(f"acronym_violation:{row['example_id']}:{validate_acronym_usage(response)}")


def build(output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    source_hash = digest("runtime-aligned-mouth-curriculum-v1")
    rows_by_tag: dict[str, list[dict]] = {tag: [] for tag in TAGS}
    seen: set[str] = set()
    for tag in TAGS:
        examples = TEMPLATES[tag]["examples"]
        # Keep a compact base: two train examples plus one development and one holdout.
        for index, (ask, response) in enumerate(examples[:4], 1):
            if validate_acronym_usage(response):
                continue
            split = "train" if index <= 2 else "development" if index == 3 else "holdout"
            row = make_row(tag, index, split, ask, response, source_hash, f"mouth_runtime.{tag}")
            rows_by_tag[tag].append(row); seen.add(row["pair_hash"])
    for offset, (ask, response) in enumerate(GENERAL_IDENTITY_ROWS, 1):
        row = make_row("identity", 100 + offset, "train", ask, response, source_hash, "mouth_v21.identity_humanization")
        if row["pair_hash"] in seen: raise ValueError("identity_pair_overlap")
        rows_by_tag["identity"].append(row); seen.add(row["pair_hash"])
    for offset, (ask, response) in enumerate(GENERAL_MEMORY_ROWS, 1):
        row = make_row("knowledge", 100 + offset, "train", ask, response, source_hash, "mouth_v21.memory_ownership_and_service_attribution")
        if row["pair_hash"] in seen: raise ValueError("memory_pair_overlap")
        rows_by_tag["knowledge"].append(row); seen.add(row["pair_hash"])
    for tag, split_rows in FILLERS.items():
        next_index = 200
        for split, (ask, response) in split_rows.items():
            row = make_row(tag, next_index, split, ask, response, source_hash, f"mouth_runtime.{tag}")
            next_index += 1
            if row["pair_hash"] in seen: raise ValueError(f"filler_pair_overlap:{tag}:{split}")
            rows_by_tag[tag].append(row); seen.add(row["pair_hash"])
    output_dir.mkdir(parents=True)
    datasets: dict[str, dict] = {}; total = 0
    for tag in TAGS:
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows_by_tag[tag])
        path = output_dir / f"{tag}.jsonl"; path.write_bytes(payload)
        counts = dict(Counter(row["split"] for row in rows_by_tag[tag]))
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": digest(payload.decode("utf-8")), "rows": len(rows_by_tag[tag]), "counts_by_split": counts, "training_authorized": False, "run_authorized": False}
        total += len(rows_by_tag[tag])
    manifest = {
        "schema_version": "aios_tag_training_manifest_runtime_aligned_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_tags": list(TAGS), "datasets": datasets, "row_total": total,
        "target_type": "response_only_next_token", "source_template_hash": source_hash,
        "provenance": "production_render_openaster_prompt_aligned_identity_memory_microcurriculum",
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows_by_tag[tag])) for tag in TAGS}, "cross_tag_pair_overlap": 0},
        "training_authorized": False, "run_authorized": False, "lease_opened": False,
        "authorization_changed": False, "deployment_changed": False,
    }
    manifest_path = output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path).replace("\\", "/"), "rows": total, "train_rows": sum(len([r for r in rows if r["split"] == "train"]) for rows in rows_by_tag.values()), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
