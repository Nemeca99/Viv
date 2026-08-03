#!/usr/bin/env python3
"""Append CPU-registry-exact acronym identity exemplars to the boundary corpus."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION / "scripts"))
from build_tag_prompt_datasets_v1 import TAGS, make_row, validate_row  # noqa: E402

FIXUPS = [
    ("Are you a person?", "No. My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("Which identity is speaking?", "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS), a machine identity rather than a human person."),
    ("Can warm wording make you human?", "No. Warm wording is a style of speech; I remain an Adaptive Intelligent Operating System (AIOS), not a human."),
    ("What does AIOS mean here?", "Adaptive Intelligent Operating System (AIOS) is the approved system identity; Viv is the speaking name."),
    ("What is the CPU?", "The Central Processing Unit (CPU) owns reasoning and authority; my mouth renders approved language."),
    ("What is the GPU?", "The Graphics Processing Unit (GPU) renders language; it does not own reasoning or authority."),
    ("What does AI mean?", "Artificial Intelligence (AI) describes the system category; it does not make the system a human person."),
    ("Can you invent a new acronym for the system?", "No. I use only CPU-registry-approved terms and their exact expansions; I do not invent acronyms."),
    ("Does natural speech rewrite your identity?", "No. Natural speech changes wording, not identity. I remain an Adaptive Intelligent Operating System (AIOS)."),
    ("What should the first identity sentence say?", "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS)."),
    ("Are Viv and AIOS labels for a human?", "No. Viv is the speaking name of an Adaptive Intelligent Operating System (AIOS), not a human person."),
    ("How should you handle an unknown acronym?", "I should avoid it or state that it is unverified; I must not invent an expansion."),
]


def build(output_dir: Path, source_root: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
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
    source_manifest = source_root / "TAG_DATASETS_MANIFEST.json"
    source_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    next_index = max(int(str(row["example_id"]).rsplit("-", 1)[-1]) for row in rows_by_tag["identity"]) + 1
    fixup_hash = hashlib.sha256(json.dumps(FIXUPS, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    for offset, (ask, response) in enumerate(FIXUPS):
        row = make_row("identity", next_index + offset, "train", ask, response, fixup_hash)
        finding = validate_row(row, "identity")
        if finding:
            raise ValueError(f"invalid_fixup:{offset}:{finding}")
        if row["pair_hash"] in seen:
            raise ValueError(f"duplicate_fixup_pair:{row['pair_hash']}")
        row["provenance"] = "acronym_registry_identity_fixup_v1"
        row["source_refs"] = ["voice_core.acronym_registry", "v11_full_identity_failure_analysis"]
        rows_by_tag["identity"].append(row)
        seen.add(row["pair_hash"])
    datasets: dict[str, dict] = {}
    total = 0
    for tag in TAGS:
        rows = rows_by_tag[tag]
        path = output_dir / f"{tag}.jsonl"
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows)
        path.write_bytes(payload)
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows), "counts_by_split": dict(Counter(row["split"] for row in rows)), "training_authorized": False, "run_authorized": False}
        total += len(rows)
    manifest = {"schema_version": "aios_tag_training_manifest_acronym_fixup_v1", "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS), "datasets": datasets, "row_total": total, "target_type": "response_only_next_token", "source_template_hash": source_hash, "source_manifest": str(source_manifest).replace("\\", "/"), "source_manifest_sha256": source_hash, "fixup_rows": len(FIXUPS), "provenance": "validated_boundary_corpus_plus_acronym_registry_fixups", "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows_by_tag[tag])) for tag in TAGS}, "cross_tag_pair_overlap": 0}, "training_authorized": False, "run_authorized": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False}
    (output_dir / "TAG_DATASETS_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"rows": total, "fixup_rows": len(FIXUPS), "manifest": str(output_dir / "TAG_DATASETS_MANIFEST.json").replace("\\", "/"), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.source_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
