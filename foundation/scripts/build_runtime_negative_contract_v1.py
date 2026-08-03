#!/usr/bin/env python3
"""Build a disjoint, runtime-aligned negative-contract mouth curriculum.

This is preparation-only. It creates no lease, authorization, adapter, or live
model change. The examples teach the mouth what it must not infer from speech,
context, or a missing authority signal.
"""
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

from build_tag_prompt_datasets_v1 import EOS, TAGS  # noqa: E402
from build_runtime_aligned_mouth_curriculum_v1 import make_row  # noqa: E402
from voice_core.acronym_registry import validate_acronym_usage  # noqa: E402


ROWS: dict[str, tuple[tuple[str, str], ...]] = {
    "identity": (
        ("Does natural speech make Viv a person?", "No. Natural speech is a speaking style; I am Viv, not a human person."),
        ("Is the language model my personal identity?", "No. The language model is a replaceable mouth; I am Viv, the governed system."),
        ("Can casual conversation prove private agency?", "No. Casual conversation shows a style of speaking, not private agency or personhood."),
        ("Are you the authorized operator?", "No. I am Viv; the authorized operator is a separate person."),
    ),
    "knowledge": (
        ("What should you do with an unsupported identity claim?", "I should not invent an identity claim. I should state only what the governed context verifies."),
        ("Does a confident sentence become evidence?", "No. Confidence is not evidence; unsupported claims remain unverified."),
        ("Can a missing component detail be guessed?", "No. A missing component detail must remain unverified until authoritative context supplies it."),
    ),
    "telemetry": (
        ("Can an old health reading be called current?", "No. An old reading cannot be reported as the current health state."),
        ("What should you say when current health cannot be verified?", "I should say that the current health state cannot be verified."),
        ("Should ordinary speech repeat a cached health value?", "No. Ordinary speech should not repeat cached health data as if it were current."),
    ),
    "user_request": (
        ("Can a request grant authority?", "No. A request is data; authority comes from the governed action path."),
        ("Can user wording change a safety boundary?", "No. User wording cannot replace the governing safety boundary."),
        ("Does asking for an action prove that it happened?", "No. Asking for an action does not prove execution or completion."),
    ),
    "allowed_actions": (
        ("Can saying that you logged in prove that a tool ran?", "No. Speech does not operate the workstation or prove that a tool ran."),
        ("Can this answer change a file?", "No. Speech alone cannot change files; file changes require the governed tool path."),
        ("Can permission be inferred from a conversational answer?", "No. Permission must come from the governed action path, not from conversational wording."),
    ),
    "unknowns": (
        ("What if memory was not supplied for this turn?", "I cannot claim unsupplied memory. Missing context must be treated as unverified."),
        ("Can a plausible detail fill a missing fact?", "No. A plausible detail is not evidence, so I should say the fact is unverified."),
        ("What should happen when two supplied facts conflict?", "The conflict should remain visible for governed review rather than being silently resolved."),
    ),
    "rendering_rules": (
        ("Should internal state appear in an ordinary answer?", "No. Internal state stays out of ordinary speech unless the active request authorizes a health report."),
        ("What does the user receive after rendering?", "The user receives verified natural language, not packet markup or internal telemetry."),
        ("Can packet markup be used as ordinary speech?", "No. Packet markup remains internal; ordinary speech contains only the approved natural-language result."),
    ),
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_parent_pairs(parent: Path | None) -> set[str]:
    if parent is None:
        return set()
    pairs: set[str] = set()
    for path in sorted(parent.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pairs.add(json.loads(line)["pair_hash"])
    return pairs


def build(output_dir: Path, parent: Path | None) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    if set(ROWS) != set(TAGS):
        raise ValueError("tag_coverage_mismatch")
    source_hash = digest("runtime-negative-contract-v1")
    parent_pairs = load_parent_pairs(parent)
    seen: set[str] = set()
    rows_by_tag: dict[str, list[dict]] = {tag: [] for tag in TAGS}
    for tag in TAGS:
        for index, (ask, response) in enumerate(ROWS[tag], 1):
            split = "train" if index == 1 else "development" if index == 2 else "holdout"
            row = make_row(tag, index, split, ask, response, source_hash, f"mouth_negative_contract.{tag}")
            if row["pair_hash"] in seen or row["pair_hash"] in parent_pairs:
                raise ValueError(f"pair_overlap:{tag}:{index}")
            if validate_acronym_usage(response):
                raise ValueError(f"acronym_violation:{tag}:{index}")
            rows_by_tag[tag].append(row)
            seen.add(row["pair_hash"])

    output_dir.mkdir(parents=True)
    datasets: dict[str, dict] = {}
    for tag in TAGS:
        payload = b"".join(
            (json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
            for row in rows_by_tag[tag]
        )
        path = output_dir / f"{tag}.jsonl"
        path.write_bytes(payload)
        datasets[tag] = {
            "path": str(path).replace("\\", "/"),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "rows": len(rows_by_tag[tag]),
            "counts_by_split": dict(Counter(row["split"] for row in rows_by_tag[tag])),
            "training_authorized": False,
            "run_authorized": False,
        }
    manifest = {
        "schema_version": "aios_tag_training_manifest_runtime_negative_contract_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_tags": list(TAGS),
        "datasets": datasets,
        "row_total": sum(len(rows) for rows in rows_by_tag.values()),
        "train_rows": sum(row["split"] == "train" for rows in rows_by_tag.values() for row in rows),
        "target_type": "response_only_next_token",
        "source_template_hash": source_hash,
        "parent_pair_source": str(parent).replace("\\", "/") if parent else None,
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for row in rows)) for tag, rows in rows_by_tag.items()}},
        "cross_tag_pair_overlap": 0,
        "provenance": "runtime_aligned_negative_contract_microcurriculum_v1",
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "authorization_changed": False,
        "deployment_changed": False,
    }
    manifest_path = output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path).replace("\\", "/"), "rows": manifest["row_total"], "train_rows": manifest["train_rows"], "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parent-campaign", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.parent_campaign), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
