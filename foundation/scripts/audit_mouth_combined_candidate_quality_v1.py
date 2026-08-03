"""Measure exact and contract-token-normalized target diversity without mutation."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
CAMPAIGN = ROOT / "campaigns/mouth_combined_candidate_v13"
SOURCE = CAMPAIGN / "train_308_candidate_hold.jsonl"
REPORT = CAMPAIGN / "CORPUS_QUALITY_AUDIT_V1.json"

CONTRACT_WORDS = set(
    "adaptive intelligent operating system aios central processing unit cpu "
    "graphics processing unit gpu viv mouth model ai human human like service "
    "services memory memories logging logs speech voice reasoning decisions "
    "decision context rendering render operator tools tool evidence record "
    "records verified verification uncertain uncertainty claim claims".split()
)


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(text: str, *, strip_contract: bool = False) -> set[str]:
    values = set(re.findall(r"[a-z]+", text.lower()))
    return values - CONTRACT_WORDS if strip_contract else values


def main() -> int:
    if REPORT.exists():
        raise FileExistsError("refuse_overwrite:mouth_combined_candidate_v13_quality_audit")
    rows = load(SOURCE)
    target_counts = Counter(row["target_hash"] for row in rows)
    exact_duplicates = sum(count > 1 for count in target_counts.values())
    near_pairs: list[dict] = []
    normalized = [words(row["target"], strip_contract=True) for row in rows]
    for i, j in combinations(range(len(rows)), 2):
        if rows[i]["axis"] != rows[j]["axis"]:
            continue
        union = normalized[i] | normalized[j]
        score = len(normalized[i] & normalized[j]) / len(union) if union else 1.0
        if score >= 0.90:
            near_pairs.append({"score": round(score, 4), "axis": rows[i]["axis"], "a": rows[i]["candidate_id"], "b": rows[j]["candidate_id"]})
    report = {
        "schema_version": "mouth_combined_candidate_quality_audit_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sha256": digest(SOURCE),
        "rows": len(rows),
        "unique_asks": len({row["ask_hash"] for row in rows}),
        "unique_targets": len(target_counts),
        "exact_target_duplicate_groups": exact_duplicates,
        "normalized_same_axis_pairs_at_or_above_0_90": len(near_pairs),
        "normalized_near_copy_pairs": near_pairs,
        "status": "QUALITY_REVIEW_REQUIRED" if near_pairs else "QUALITY_PASS",
        "finding": "Inherited parent responses still contain template-level near copies after required contract vocabulary is removed." if near_pairs else "No normalized near-copy pairs at threshold.",
        "candidate_mutated": False,
        "admission_allowed": False,
        "training_authorized": False,
        "run_authorized": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("status", "rows", "unique_asks", "unique_targets", "exact_target_duplicate_groups", "normalized_same_axis_pairs_at_or_above_0_90", "training_authorized")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
