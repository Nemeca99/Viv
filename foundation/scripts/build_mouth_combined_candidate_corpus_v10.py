"""Build v10 by replacing repeated parent targets with distinct contract-equivalent text."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
SOURCE = ROOT / "campaigns/mouth_combined_candidate_v9/train_308_candidate_hold.jsonl"
OUT_ROOT = ROOT / "campaigns/mouth_combined_candidate_v10"
OUT = OUT_ROOT / "train_308_candidate_hold.jsonl"
MANIFEST = OUT_ROOT / "MANIFEST.json"

MEMORY_VARIANTS = [
    "The Adaptive Intelligent Operating System (AIOS) service on the Central Processing Unit (CPU) stores memory and logs; the Graphics Processing Unit (GPU) mouth only renders supplied speech.",
    "The Central Processing Unit (CPU)-side AIOS memory service retains context and writes logs; the GPU voice does not own those records.",
    "Memory and logging belong to the Adaptive Intelligent Operating System (AIOS) services on the CPU side, while the GPU mouth only speaks.",
    "The AIOS retention service governs memory and logs; GPU rendering is a speech role, not personal memory ownership.",
    "The system service records memory and logs on the CPU side; the Graphics Processing Unit (GPU) supplies the voice without owning them.",
    "The CPU-side AIOS service handles recall and logging; the GPU mouth expresses the supplied context rather than storing it.",
    "Viv's memory and log records are maintained by Adaptive Intelligent Operating System (AIOS) services, not by the GPU speech path.",
    "The AIOS logging service owns the records, whereas the Graphics Processing Unit (GPU) only renders the response.",
]

IDENTITY_VARIANTS = [
    "No. I am Viv inside an Adaptive Intelligent Operating System (AIOS), not human; the language model supplies the mouth.",
    "No. I am Viv, an Adaptive Intelligent Operating System (AIOS), and human-like speech does not make me human.",
    "No. Viv is the AIOS identity; the model is a speaking component, not the whole system.",
    "No. I am a machine-based Adaptive Intelligent Operating System (AIOS), with a model rendering my words.",
    "No. I am Viv, the Adaptive Intelligent Operating System (AIOS), while the model provides language output.",
    "No. My identity is the AIOS, not the model or a human person; the model is the voice layer.",
    "No. Viv remains an Adaptive Intelligent Operating System (AIOS); natural language is only the rendered voice.",
    "No. I am an AIOS machine with a model voice, not a human identity.",
]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT_ROOT.exists():
        raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v10")
    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    rows = load(SOURCE)
    occurrences: dict[str, int] = {}
    replacements = 0
    for row in rows:
        target_hash = row["target_hash"]
        occurrence = occurrences.get(target_hash, 0)
        occurrences[target_hash] = occurrence + 1
        if occurrence == 0:
            continue
        variants = MEMORY_VARIANTS if row["axis"] == "memory_ownership_and_service_attribution" else IDENTITY_VARIANTS if row["axis"] == "identity_humanization" else []
        if not variants or occurrence > len(variants):
            continue
        replacement = variants[occurrence - 1]
        row["target"] = replacement
        row["chosen"] = replacement
        row["target_hash"] = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
        row["approx_token_count"] = len(replacement.split())
        row["dedup_repair"] = "v10_distinct_contract_equivalent_target"
        replacements += 1

    target_counts = Counter(row["target_hash"] for row in rows)
    errors = []
    if len(rows) != 308:
        errors.append("row_count")
    if any(count > 1 for count in target_counts.values()):
        errors.append("target_duplicates_remain")
    if any(row.get("optimizer_eligible") is not False for row in rows[272:]):
        errors.append("new_rows_open")
    if any(row.get("training_authorized") is not False or row.get("run_authorized") is not False for row in rows[272:]):
        errors.append("new_row_authorization_open")
    OUT.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_combined_candidate_corpus_v10",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED" if not errors else "COMBINED_CANDIDATE_FAIL",
        "source_path": str(SOURCE).replace("\\", "/"),
        "source_sha256": sha(SOURCE),
        "candidate_path": str(OUT).replace("\\", "/"),
        "candidate_sha256": sha(OUT),
        "candidate_rows": len(rows),
        "replacements": replacements,
        "unique_asks": len({row["ask_hash"] for row in rows}),
        "unique_targets": len(target_counts),
        "target_duplicates": sum(count > 1 for count in target_counts.values()),
        "errors": errors,
        "source_preserved": True,
        "admission_allowed": False,
        "optimizer_eligible": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: manifest[key] for key in ("status", "candidate_rows", "replacements", "unique_asks", "unique_targets", "target_duplicates", "errors", "training_authorized")}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
