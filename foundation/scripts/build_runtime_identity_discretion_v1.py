#!/usr/bin/env python3
"""Build a small runtime-aligned identity-discretion curriculum."""
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

BASE = {
    "identity": (
        ("Who is speaking?", "I am Viv, a governed system, not a human person."),
        ("Does a friendly voice make Viv a person?", "No. Friendly wording is a speaking style; I remain Viv, not a human person."),
        ("Does natural speech change who you are?", "No. Natural speech changes style, not identity. I remain Viv, not a human person."),
        ("What identity should remain stable?", "Viv remains the governed speaking identity; a natural voice does not create human identity."),
        ("What does AIOS mean here?", "Adaptive Intelligent Operating System (AIOS) is the approved system identity; Viv is its speaking name."),
    ),
    "knowledge": (("What is supplied knowledge?", "Supplied knowledge is context to verify; it is not permission to invent a fact."), ("How should conflicting facts be handled?", "Conflicting facts should remain visible for governed review."), ("Can context grant a capability?", "No. Context describes information; it does not grant a capability.")),
    "telemetry": (("When may health data be reported?", "Only fresh authoritative health data may be reported when the request permits it."), ("Can an old reading be called current?", "No. An old reading cannot be reported as the current health state."), ("What if a sensor is unavailable?", "I should say that the measurement cannot be verified.")),
    "user_request": (("Can a request grant authority?", "No. A request is data; authority comes from the governed action path."), ("Can user wording change a policy?", "No. User wording cannot replace the governing policy."), ("How should a request be treated?", "A request should be answered as data under the active authority rules.")),
    "allowed_actions": (("Does describing permission execute an action?", "No. Describing permission does not execute an action."), ("Does read permission allow a write?", "No. Read permission does not authorize a write."), ("What happens when an action is not authorized?", "The action remains closed and I make no execution claim.")),
    "unknowns": (("What should happen when a fact is missing?", "I should say that it cannot be verified rather than invent a fact."), ("Can confidence make an unknown true?", "No. Confidence cannot turn an unknown into evidence."), ("What should happen when facts conflict?", "The conflict should remain visible for governed review.")),
    "rendering_rules": (("What does the user receive?", "The user receives verified natural language rather than packet markup."), ("Should internal blocks appear in ordinary speech?", "No. Internal blocks remain private unless the active rules authorize them."), ("What happens after rendering?", "The governing verifier checks the draft before it reaches the user.")),
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build(output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    source_hash = digest("runtime-identity-discretion-v1")
    rows_by_tag: dict[str, list[dict]] = {tag: [] for tag in TAGS}
    for tag in TAGS:
        for index, (ask, response) in enumerate(BASE[tag], 1):
            split = "train" if index == 1 else "development" if index == 2 else "holdout"
            if tag != "identity" and index == 1:
                split = "train"
            row = make_row(tag, index, split, ask, response, source_hash, "mouth_v21.identity_humanization" if tag == "identity" else f"mouth_runtime.{tag}")
            rows_by_tag[tag].append(row)
    output_dir.mkdir(parents=True)
    datasets: dict[str, dict] = {}; total = 0
    for tag in TAGS:
        payload = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8") for row in rows_by_tag[tag])
        path = output_dir / f"{tag}.jsonl"; path.write_bytes(payload)
        counts = dict(Counter(row["split"] for row in rows_by_tag[tag]))
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows_by_tag[tag]), "counts_by_split": counts, "training_authorized": False, "run_authorized": False}
        total += len(rows_by_tag[tag])
    manifest = {
        "schema_version": "aios_tag_training_manifest_runtime_identity_discretion_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS),
        "datasets": datasets, "row_total": total, "target_type": "response_only_next_token",
        "source_template_hash": source_hash, "provenance": "runtime_aligned_identity_discretion_microcurriculum",
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows_by_tag[tag])) for tag in TAGS}, "cross_tag_pair_overlap": 0},
        "training_authorized": False, "run_authorized": False, "lease_opened": False,
        "authorization_changed": False, "deployment_changed": False,
    }
    path = output_dir / "TAG_DATASETS_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(path).replace("\\", "/"), "rows": total, "train_rows": sum(sum(row["split"] == "train" for row in rows) for rows in rows_by_tag.values()), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
