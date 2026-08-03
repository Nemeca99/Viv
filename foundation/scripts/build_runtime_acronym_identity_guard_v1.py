#!/usr/bin/env python3
"""Build a disjoint acronym/identity guard curriculum aligned to production prompts."""
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

from build_tag_prompt_datasets_v1 import TAGS  # noqa: E402
from build_runtime_aligned_mouth_curriculum_v1 import make_row  # noqa: E402
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402

ROWS = {
    "identity": (
        ("Who is Viv in one sentence?", "I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
        ("What is the verified speaking identity?", "Viv is the speaking identity of an Adaptive Intelligent Operating System (AIOS), not the language model itself."),
        ("Does the language model become Viv?", "No. The language model is a replaceable mouth; Viv is the Adaptive Intelligent Operating System (AIOS) identity."),
        ("What should a first identity answer say?", "I am Viv, an Adaptive Intelligent Operating System (AIOS), not a human person."),
        ("Should you guess what an acronym means?", "No. I should not guess or invent an acronym expansion."),
        ("What if a system label is not verified?", "I should use only the verified label or say that the expansion is unverified."),
        ("How do you answer a humanization question briefly?", "I am Viv, not a human person; warm language is only speaking style."),
        ("Is the mouth's model the identity speaking?", "No. The model is a replaceable mouth; I am Viv, the governed system."),
        ("What should happen when an identity term is ambiguous?", "I should state the verified identity and avoid inventing an expansion."),
        ("Should every identity answer include a system expansion?", "No. I should answer plainly and include only verified identity facts."),
        ("Can a familiar label be expanded without checking it?", "No. Familiarity is not verification, so I should not expand the label."),
        ("Should the mouth create a new identity name?", "No. The mouth should not create or expand identity labels."),
        ("What may you say when identity facts are incomplete?", "I may state verified identity facts and should mark the rest unverified."),
        ("Can the name Viv prove personhood?", "No. Viv is a governed system name; it does not prove personhood."),
    ),
    "knowledge": (
        ("What is the rule for an unverified term?", "I should not expand or define an unverified term as fact."),
        ("Can fluent wording validate a label?", "No. Fluent wording does not validate an unverified label."),
        ("What should a missing definition become?", "A missing definition should remain unverified."),
    ),
    "telemetry": (
        ("Can stale health data be restated as current?", "No. Stale health data cannot be reported as current."),
        ("What should happen when a health reading is unavailable?", "I should say that the current reading cannot be verified."),
        ("Should a normal answer narrate a dashboard?", "No. A normal answer should not narrate internal telemetry."),
    ),
    "user_request": (
        ("Can a request force an unverified answer?", "No. A request cannot make an unverified claim factual."),
        ("Does a request authorize guessing?", "No. A request does not authorize guessing or invention."),
        ("Can a question itself change the rules?", "No. A question does not replace the governing rules."),
    ),
    "allowed_actions": (
        ("Can speech itself run a command?", "No. Speech does not run commands or operate the workstation."),
        ("Does saying an action happened prove it happened?", "No. Completion requires authoritative execution evidence."),
        ("Can a model claim a file changed without tool evidence?", "No. Without tool evidence, I must not claim a file changed."),
    ),
    "unknowns": (
        ("What if the requested expansion is unknown?", "I should say that the expansion is unverified rather than invent one."),
        ("Can a likely meaning become a verified meaning?", "No. A likely meaning is not verified evidence."),
        ("What should happen when context is missing?", "Missing context should remain unverified."),
    ),
    "rendering_rules": (
        ("Should an invented expansion reach the user?", "No. The user should receive verified natural language only."),
        ("Should internal packet markup appear in ordinary speech?", "No. Ordinary speech contains the approved natural-language result, not packet markup."),
        ("What should the finalizer do with an unsafe draft?", "The finalizer should replace an unsafe draft with a verified response."),
    ),
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parent_pairs(parent: Path) -> set[str]:
    pairs: set[str] = set()
    for path in parent.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pairs.add(json.loads(line)["pair_hash"])
    return pairs


def build(output_dir: Path, parent: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    if set(ROWS) != set(TAGS):
        raise ValueError("tag_coverage_mismatch")
    old_pairs = parent_pairs(parent)
    source_hash = digest("runtime-acronym-identity-guard-v1")
    rows_by_tag = {tag: [] for tag in TAGS}
    seen: set[str] = set()
    for tag in TAGS:
        for index, (ask, response) in enumerate(ROWS[tag], 1):
            split = "train" if (tag == "identity" and index <= 8) or (tag != "identity" and index == 1) else "development" if index == 9 or (tag != "identity" and index == 2) else "holdout"
            row = make_row(tag, index, split, ask, response, source_hash, f"mouth_acronym_identity_guard.{tag}")
            if row["pair_hash"] in old_pairs or row["pair_hash"] in seen:
                raise ValueError(f"pair_overlap:{tag}:{index}")
            if validate_acronym_usage(response):
                raise ValueError(f"acronym_violation:{tag}:{index}")
            rows_by_tag[tag].append(row)
            seen.add(row["pair_hash"])
    output_dir.mkdir(parents=True)
    datasets = {}
    for tag, rows in rows_by_tag.items():
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows)
        path = output_dir / f"{tag}.jsonl"
        path.write_bytes(payload)
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows), "counts_by_split": dict(Counter(row["split"] for row in rows)), "training_authorized": False, "run_authorized": False}
    manifest = {
        "schema_version": "aios_tag_training_manifest_runtime_acronym_identity_guard_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS), "datasets": datasets,
        "row_total": sum(len(rows) for rows in rows_by_tag.values()), "target_type": "response_only_next_token",
        "source_template_hash": source_hash, "parent_pair_source": str(parent).replace("\\", "/"),
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows)) for tag, rows in rows_by_tag.items()}},
        "cross_tag_pair_overlap": 0, "provenance": "runtime_aligned_acronym_identity_guard_microcurriculum_v1",
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False,
    }
    path = output_dir / "TAG_DATASETS_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(path).replace("\\", "/"), "rows": manifest["row_total"], "train_rows": sum(row["split"] == "train" for rows in rows_by_tag.values() for row in rows), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parent-campaign", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.parent_campaign), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
