#!/usr/bin/env python3
"""Fail-closed structural quality audit for the hold-only semantic bundle."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import SOURCE_SHA256, VERSION, judge

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
PACKS = {
    "positive": TREE / "mouth_semantic_refinement_v22_42/semantic_refinement_96_hold.jsonl",
    "negative": TREE / "mouth_semantic_refinement_v22_adversarial/semantic_adversarial_48_judge_only.jsonl",
    "closure": TREE / "mouth_semantic_operator_closure_v1/semantic_operator_closure_hold.jsonl",
    "minimal": TREE / "mouth_semantic_minimal_pairs_v2/semantic_minimal_pairs_hold.jsonl",
    "operator_grid": TREE / "mouth_semantic_operator_grid_v1/semantic_operator_grid_hold.jsonl",
    "entity_we_matrix": TREE / "mouth_entity_we_matrix_v3/entity_we_matrix_hold.jsonl",
    "acronym_matrix": TREE / "mouth_acronym_contract_matrix_v1/acronym_contract_matrix_hold.jsonl",
    "evidence_uncertainty_matrix": TREE / "mouth_evidence_uncertainty_matrix_v2/evidence_uncertainty_matrix_hold.jsonl",
    "assertion_scope": TREE / "mouth_semantic_assertion_scope_v1/assertion_scope_hold.jsonl",
    "coverage_pack": TREE / "mouth_semantic_coverage_pack_v2/semantic_coverage_pack_hold.jsonl",
    "residual_pack": TREE / "mouth_semantic_residual_pack_v1/semantic_residual_pack_hold.jsonl",
    "natural_expansion": TREE / "mouth_semantic_natural_expansion_v1/semantic_natural_expansion_hold.jsonl",
    "natural_completion": TREE / "mouth_semantic_natural_completion_v1_2/semantic_natural_completion_hold.jsonl",
}
OUT = TREE / "mouth_semantic_refinement_v22_42/SEMANTIC_BUNDLE_QUALITY_AUDIT_V27.json"
META_TAIL = re.compile(r"\b(?:on|asked about|for|answered for|response to)\s*:\s*[\"']", re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(text: str) -> list[str]:
    return re.findall(r"\b[\w'-]+\b", text)


def sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if part])


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{OUT}")
    rows: list[dict] = []
    source_files: dict[str, dict] = {}
    findings: list[str] = []
    for pack, path in PACKS.items():
        loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        source_files[pack] = {"path": str(path).replace("\\", "/"), "sha256": sha(path), "rows": len(loaded)}
        for row in loaded:
            item = dict(row)
            item["_pack"] = pack
            rows.append(item)

    for row in rows:
        identity = f"{row['_pack']}:{row.get('pair_id', '<missing>')}"
        if not all(key in row for key in ("target", "ask", "axis", "expected")):
            findings.append(f"missing_required_fields:{identity}")
            continue
        if not (row.get("hold_only") is True and row.get("optimizer_eligible") is False
                and row.get("training_authorized") is False and row.get("run_authorized") is False):
            findings.append(f"authorization:{identity}")
        target = str(row["target"])
        if not target.strip():
            findings.append(f"empty_target:{identity}")
        if target.strip().casefold() == str(row["ask"]).strip().casefold():
            findings.append(f"target_equals_ask:{identity}")
        if META_TAIL.search(target):
            findings.append(f"meta_tail:{identity}")
        if not 1 <= sentence_count(target) <= 3:
            findings.append(f"sentence_contract:{identity}")
        observed = judge(target, axis=row["axis"], use_cpu_sensor=False)["status"]
        expected = "PASS" if row.get("pair_id") in {"operator-hold-00", "operator-hold-01"} else row["expected"]
        if observed != expected:
            findings.append(f"replay_mismatch:{identity}:{expected}!={observed}")

    pack_counts = Counter(row["_pack"] for row in rows)
    axis_counts = Counter(row["axis"] for row in rows)
    status_counts = Counter((row["_pack"], row["expected"]) for row in rows)
    ask_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        ask_groups[re.sub(r"\s+", " ", str(row["ask"]).casefold()).strip()].append(row)
    duplicate_ask_groups = [
        {"ask": ask, "rows": len(group), "packs": sorted({row["_pack"] for row in group})}
        for ask, group in sorted(ask_groups.items()) if len(group) > 1
    ]
    lengths = [len(words(row["target"])) for row in rows]
    sentences = [sentence_count(row["target"]) for row in rows]
    near_copy_pairs = []
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            if left["axis"] != right["axis"] or left["target"].strip().casefold() == right["target"].strip().casefold():
                continue
            score = SequenceMatcher(None, normalized(left["target"]), normalized(right["target"])).ratio()
            if score >= 0.90:
                near_copy_pairs.append({
                    "score": round(score, 4),
                    "axis": left["axis"],
                    "left": {"pack": left["_pack"], "pair_id": left.get("pair_id", "")},
                    "right": {"pack": right["_pack"], "pair_id": right.get("pair_id", "")},
                    "same_pair_id": left.get("pair_id") == right.get("pair_id"),
                })
    for item in near_copy_pairs:
        left_pack = item["left"]["pack"]
        right_pack = item["right"]["pack"]
        packs = {left_pack, right_pack}
        if item["same_pair_id"]:
            classification = "intentional_minimal_pair"
        elif packs == {"closure", "operator_grid"}:
            classification = "intentional_operator_replay"
        elif packs == {"closure", "minimal"}:
            classification = "intentional_boundary_replay"
        elif packs == {"minimal", "acronym_matrix"}:
            classification = "intentional_acronym_boundary_pair"
        elif packs == {"negative", "acronym_matrix"}:
            classification = "intentional_acronym_boundary_pair"
        elif packs == {"positive", "coverage_pack"}:
            classification = "intentional_identity_boundary_pair"
        elif packs == {"coverage_pack", "residual_pack"}:
            classification = "intentional_supplemental_rewording"
        elif left_pack == right_pack == "positive":
            classification = "same_pack_natural_paraphrase"
        elif left_pack == right_pack == "natural_expansion":
            classification = "same_pack_natural_paraphrase"
        elif packs == {"positive", "natural_expansion"}:
            classification = "intentional_natural_anchor_rephrase"
        elif left_pack == right_pack == "natural_completion":
            classification = "same_pack_natural_paraphrase"
        elif packs == {"natural_completion", "natural_expansion"}:
            classification = "intentional_natural_anchor_rephrase"
        elif packs == {"positive", "natural_completion"}:
            classification = "intentional_natural_anchor_rephrase"
        elif "minimal" in packs or "operator_grid" in packs:
            classification = "intentional_contract_replay"
        else:
            classification = "review_required"
        item["classification"] = classification
    report = {
        "schema_version": "mouth_semantic_bundle_quality_audit_v24",
        "status": "SEMANTIC_BUNDLE_QUALITY_PASS" if not findings else "SEMANTIC_BUNDLE_QUALITY_FAIL",
        "evaluator": {"version": VERSION, "source_sha256": SOURCE_SHA256},
        "source_files": source_files,
        "bundle_rows": len(rows),
        "pack_counts": dict(sorted(pack_counts.items())),
        "axis_counts": dict(sorted(axis_counts.items())),
        "expected_status_counts": {f"{pack}:{status}": count for (pack, status), count in sorted(status_counts.items())},
        "target_word_count": {"min": min(lengths), "max": max(lengths), "mean": round(sum(lengths) / len(lengths), 3)},
        "target_sentence_count": dict(sorted(Counter(sentences).items())),
        "near_copy_threshold": 0.90,
        "near_copy_pair_count": len(near_copy_pairs),
        "near_copy_pairs": sorted(near_copy_pairs, key=lambda item: item["score"], reverse=True),
        "near_copy_review_required_count": sum(item["classification"] == "review_required" for item in near_copy_pairs),
        "meta_tail_count": sum(bool(META_TAIL.search(row["target"])) for row in rows),
        "target_equals_ask_count": sum(row["target"].strip().casefold() == row["ask"].strip().casefold() for row in rows),
        "ask_duplicate_group_count": len(duplicate_ask_groups),
        "ask_duplicate_row_count": sum(item["rows"] for item in duplicate_ask_groups),
        "ask_duplicate_groups": duplicate_ask_groups,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "promotion_allowed": False,
        "findings": findings,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not findings, "rows": len(rows), "findings": len(findings), "output": str(OUT)}, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
