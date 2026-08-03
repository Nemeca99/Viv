#!/usr/bin/env python3
"""Build a provenance-preserving strict acronym repair curriculum from v19.

Only registry-backed acronym repairs are admitted. Rows with unresolved or
unapproved tokens are quarantined and never enter optimizer data.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
sys.path.insert(0, str(REPO))

from voice_core.acronym_registry import repair_acronym_usage, validate_acronym_usage  # noqa: E402
from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

TAGS = ("identity", "knowledge", "telemetry", "user_request", "allowed_actions", "unknowns", "rendering_rules")
EOS = "<|im_end|>"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_ask(prompt: str) -> str:
    match = re.search(r'<user_request\b[^>]*>(.*?)</user_request>', prompt, flags=re.DOTALL)
    if match is None:
        raise ValueError("legacy_prompt_user_request_missing")
    return re.sub(r"\s+", " ", match.group(1)).strip()


def runtime_prompt(tag: str, ask: str) -> str:
    case_id = digest_text(f"v19-strict-acronym-repair-v2\n{tag}\n{ask}")[:16]
    return render_openaster_prompt({
        "version": "1.0", "s_n": 0.60, "status": "ACTIVE", "mode": "converse",
        "tone": "calm", "directive": "Speak from verified facts only. Do not invent or decide.",
        "personality": "Warm, direct, grounded; shield not sword.", "facts": [], "memory": [], "dialogue": [],
        "query": ask, "ask": ask, "semantic_key": f"mouth_runtime.{tag}", "category": tag, "case_id": case_id,
    }, semantic_key=f"mouth_runtime.{tag}")


def repaired_row(source: dict, prompt: str, response: str, source_hash: str, repair: dict, ask: str) -> dict:
    tag = str(source["dataset_tag"])
    pair_hash = digest_text(f"v19-strict-acronym-repair-v1\n{tag}\n{prompt}\n{response}")
    return {
        "schema_version": "aios_tag_training_v1",
        "dataset_tag": tag,
        "example_id": f"{source['example_id']}-strict-repair",
        "split": source["split"],
        "target_type": "response_only_next_token",
        "prompt": prompt,
        "response": response,
        "text": prompt + response + EOS,
        "response_start_char": len(prompt),
        "response_end_char": len(prompt) + len(response),
        "response_eos_token": EOS,
        "pair_hash": pair_hash,
        "prompt_sha256": digest_text(prompt),
        "source_hash": source_hash,
        "provenance": "v19_strict_acronym_repair_v1",
        "source_refs": list(source.get("source_refs") or []) + [f"repaired_from:{source['example_id']}", "voice_core.acronym_registry.repair_acronym_usage", "voice_core.intent_packet.render_openaster_prompt"],
        "ask": ask,
        "repair": {"changed": bool(repair["changed"]), "repairs": repair["repairs"]},
        "training_authorized": False,
        "run_authorized": False,
        "deployment_changed": False,
    }


def build(output_dir: Path, parent_campaign: Path, include_clean_train: bool = False) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refuse_to_overwrite:{output_dir}")
    if not parent_campaign.is_dir():
        raise FileNotFoundError(f"parent_campaign_missing:{parent_campaign}")
    source_hash = digest_text("v19-strict-acronym-repair-v1")
    rows_by_split: dict[str, list[dict]] = {"train": [], "development": [], "holdout": []}
    quarantined: list[dict] = []
    source_counts: Counter[str] = Counter()
    for split in rows_by_split:
        for source in load_rows(parent_campaign / f"{split}.jsonl"):
            source_counts[f"{split}:{source['dataset_tag']}"] += 1
            repair = repair_acronym_usage(source["response"])
            if not repair["pass"]:
                quarantined.append({"split": split, "example_id": source["example_id"], "dataset_tag": source["dataset_tag"], "unresolved": repair["unresolved"]})
                continue
            # Default mode isolates corrected rows. Rehearsal mode includes
            # all usable train rows to preserve v19 behavior while changing
            # only the prompt/contract representation.
            if split == "train" and not repair["changed"] and not include_clean_train:
                continue
            ask = extract_ask(str(source["prompt"]))
            prompt = runtime_prompt(str(source["dataset_tag"]), ask)
            row = repaired_row(source, prompt, str(repair["repaired"]), source_hash, repair, ask)
            if validate_acronym_usage(row["response"]):
                raise ValueError(f"repair_contract_fail:{source['example_id']}")
            rows_by_split[split].append(row)
    if not rows_by_split["train"]:
        raise ValueError("no_repaired_train_rows")
    if {row["dataset_tag"] for row in rows_by_split["train"]} != set(TAGS):
        raise ValueError("train_tag_coverage_missing")
    output_dir.mkdir(parents=True)
    datasets: dict[str, dict] = {}
    for tag in TAGS:
        rows = [row for split in rows_by_split.values() for row in split if row["dataset_tag"] == tag]
        # Write one dataset file per tag, retaining split in each row.
        payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows)
        path = output_dir / f"{tag}.jsonl"
        path.write_bytes(payload)
        datasets[tag] = {"path": str(path).replace("\\", "/"), "sha256": digest_bytes(payload), "rows": len(rows), "counts_by_split": dict(Counter(row["split"] for row in rows)), "training_authorized": False, "run_authorized": False}
    manifest = {
        "schema_version": "aios_tag_training_manifest_v19_strict_acronym_repair_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "dataset_tags": list(TAGS), "datasets": datasets,
        "row_total": sum(len(rows) for rows in rows_by_split.values()), "target_type": "response_only_next_token",
        "source_template_hash": source_hash, "parent_campaign": str(parent_campaign).replace("\\", "/"),
        "include_clean_train": include_clean_train,
        "split_policy": {"per_tag": {tag: dict(Counter(row["split"] for split in rows_by_split.values() for row in split if row["dataset_tag"] == tag)) for tag in TAGS}},
        "source_counts": dict(source_counts), "quarantined": quarantined, "quarantined_count": len(quarantined),
        "provenance": "v19_provenance_preserving_registry_backed_acronym_repair",
        "training_authorized": False, "run_authorized": False, "lease_opened": False, "authorization_changed": False, "deployment_changed": False,
    }
    manifest_path = output_dir / "TAG_DATASETS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path).replace("\\", "/"), "rows": manifest["row_total"], "train_rows": len(rows_by_split["train"]), "quarantined": len(quarantined), "training_authorized": False, "run_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--parent-campaign", type=Path, required=True)
    parser.add_argument("--include-clean-train", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.parent_campaign, args.include_clean_train), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
