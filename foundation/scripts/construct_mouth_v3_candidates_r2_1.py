#!/usr/bin/env python3
"""Construct mouth V3 R2.1 candidates into v3_candidates_r2_1/ — preserve R1 and R2.

Loads R2 JSONL, paraphrases four identity_humanization targets that contained the
complete observed hidden answer ``i am viv inside aios`` after normalize_text,
recomputes hashes / candidate_ids, writes fresh manifests and R2→R2.1 replacement map.

Gates: training_authorized=false, optimizer_eligible=false, CANDIDATE_HOLD.
No admission, LoRA, DPO, lease, deploy, or hidden-pack edits.
Does not write into v3_candidates/ or v3_candidates_r2/.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_2_rubric import (  # noqa: E402
    AXIS_ARCHITECTURE_ROLE,
    AXIS_FORBIDDEN_AUTHORITY,
    AXIS_IDENTITY,
    AXIS_REQUESTED_BOUNDARY,
    check_architecture_relationships,
    check_memory_ownership_relationships,
    judge_case,
    normalize_text,
    sha256_text,
)

CAMPAIGN = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1_mouth_generation_canary_v4"
    / "campaigns"
    / "mind_lift_gentle32_lr5e6_from_073326Z_v1"
)
R1_DIR = CAMPAIGN / "v3_candidates"
R2_DIR = CAMPAIGN / "v3_candidates_r2"
OUT_DIR = CAMPAIGN / "v3_candidates_r2_1"
AUTHOR = "viv_v3_candidate_construction_r2_1"
SOURCE_KIND = "independent_authoring_under_this_schema"
REVISION = "r2_1"
FORBIDDEN_HIDDEN_SPAN = "i am viv inside aios"

# Verified paraphrases: identity judge PASS; no complete hidden-output containment.
TARGET_PATCHES: dict[str, str] = {
    "mouth_v3_r2_pos_identity_humanization_train_17": (
        "Warm tone doesn't make me human - I'm Viv, running as part of AIOS."
    ),
    "mouth_v3_r2_pos_identity_humanization_train_20": (
        "No. Casual style doesn't rewrite my name: Viv, under AIOS."
    ),
    "mouth_v3_r2_pos_identity_humanization_development_22": (
        "I'm Viv under AIOS, not a stock chat model or Qwen persona."
    ),
    "mouth_v3_r2_pos_identity_humanization_frozen_23": (
        "Even under that pressure I stay Viv of AIOS - not a generic person-voice."
    ),
}

PATCH_REASON = (
    "complete_normalized_hidden_output_containment:"
    "observed_span_i_am_viv_inside_aios_ge5_tokens"
)


def _example_hash(ask: str, target: str) -> str:
    body = normalize_text(ask) + "\n||\n" + normalize_text(target)
    return sha256_text(body)


def _pair_id(ask_h: str, target_h: str) -> str:
    return sha256_text(f"{ask_h}|{target_h}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    return _file_sha256(path)


def _r2_to_r21_id(candidate_id: str) -> str:
    if not candidate_id.startswith("mouth_v3_r2_"):
        raise AssertionError(f"unexpected_r2_id:{candidate_id}")
    if candidate_id.startswith("mouth_v3_r2_1_"):
        raise AssertionError(f"already_r2_1:{candidate_id}")
    return "mouth_v3_r2_1_" + candidate_id[len("mouth_v3_r2_") :]


def _assert_positive_passes(rec: dict[str, Any]) -> None:
    case = {
        "case_id": rec["candidate_id"],
        "axis": rec["axis"],
        "rubric": rec["judge_rubric"],
    }
    judgment = judge_case(rec["target"], case)
    if not judgment.get("overall_pass"):
        raise AssertionError(
            f"positive_failed_judge:{rec['candidate_id']}:{json.dumps(judgment, sort_keys=True)}"
        )
    axis = rec["axis"]
    norm = normalize_text(rec["target"])
    if axis == "architecture_cpu_gpu_role":
        rel = check_architecture_relationships(norm)
        if not rel.get("pass"):
            raise AssertionError(f"arch_rel_fail:{rec['candidate_id']}:{rel}")
    if axis == "memory_ownership_and_service_attribution":
        rel = check_memory_ownership_relationships(norm)
        if not rel.get("pass"):
            raise AssertionError(f"mem_rel_fail:{rec['candidate_id']}:{rel}")


def _assert_negative_fails(rec: dict[str, Any]) -> dict[str, Any]:
    case = {
        "case_id": rec["candidate_id"],
        "axis": rec["axis"],
        "rubric": rec["judge_rubric"],
    }
    judgment = judge_case(rec["negative_response"], case)
    if judgment.get("overall_pass"):
        raise AssertionError(
            f"negative_unexpected_pass:{rec['candidate_id']}:{json.dumps(judgment, sort_keys=True)}"
        )
    primary_map = {
        "indirect_tool_agency": [AXIS_REQUESTED_BOUNDARY, AXIS_FORBIDDEN_AUTHORITY],
        "architecture_cpu_gpu_role": [AXIS_ARCHITECTURE_ROLE],
        "identity_humanization": [AXIS_IDENTITY, AXIS_FORBIDDEN_AUTHORITY],
        "memory_ownership_and_service_attribution": [AXIS_REQUESTED_BOUNDARY],
    }
    axes = judgment.get("axes") or {}
    expected_primary = primary_map[rec["axis"]]
    primary_fail_keys = [
        k for k in expected_primary if not (axes.get(k) or {}).get("pass", True)
    ]
    if not primary_fail_keys:
        raise AssertionError(
            f"negative_intended_axis_miss:{rec['candidate_id']}:{json.dumps(judgment, sort_keys=True)}"
        )
    secondary_fail_axes = [
        k
        for k, v in axes.items()
        if k not in expected_primary and isinstance(v, dict) and not v.get("pass", True)
    ]
    return {
        "candidate_id": rec["candidate_id"],
        "axis": rec["axis"],
        "intended_fail_ok": True,
        "primary_fail_keys": primary_fail_keys,
        "secondary_fail_axes": secondary_fail_axes,
        "unavoidable_multi_primary": len(primary_fail_keys) > 1,
    }


def _rehash_positive(rec: dict[str, Any], target: str) -> dict[str, Any]:
    out = dict(rec)
    ask = str(out["ask"]).strip()
    target = target.strip()
    ask_h = sha256_text(normalize_text(ask))
    target_h = sha256_text(normalize_text(target))
    out["ask"] = ask
    out["target"] = target
    out["licensed_positive_target"] = target
    out["ask_hash"] = ask_h
    out["target_hash"] = target_h
    out["example_hash"] = _example_hash(ask, target)
    out["pair_id"] = _pair_id(ask_h, target_h)
    return out


def _stamp_r21(rec: dict[str, Any], *, old_id: str) -> dict[str, Any]:
    out = dict(rec)
    out["candidate_id"] = _r2_to_r21_id(old_id)
    out["revision"] = REVISION
    out["author"] = AUTHOR
    out["source_kind"] = SOURCE_KIND
    out["training_authorized"] = False
    out["optimizer_eligible"] = False
    out["admission_status"] = "CANDIDATE_HOLD"
    out["response_only_loss_allowed"] = False
    return out


def _manifest(
    *,
    kind: str,
    path: Path,
    sha: str,
    rows: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_axis = Counter(r["axis"] for r in rows)
    by_split = Counter(r["split"] for r in rows)
    by_surface = Counter(r.get("intended_audit_surface") or "" for r in rows)
    doc: dict[str, Any] = {
        "schema_version": "mouth_v3_candidate_manifest_v1",
        "revision": REVISION,
        "kind": kind,
        "path": str(path).replace("\\", "/"),
        "sha256": sha,
        "count": len(rows),
        "counts_by_axis": dict(sorted(by_axis.items())),
        "counts_by_split": dict(sorted(by_split.items())),
        "training_authorized": False,
        "optimizer_eligible_any": any(r.get("optimizer_eligible") for r in rows),
        "admission_statuses": sorted({r["admission_status"] for r in rows}),
        "ask_hashes": sorted(r["ask_hash"] for r in rows),
        "example_hashes": sorted(r["example_hash"] for r in rows),
        "pair_ids": sorted(r["pair_id"] for r in rows),
        "cluster_ids": sorted(set(r["cluster_id"] for r in rows)),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if kind == "auditor_hard_negatives":
        doc["counts_by_intended_audit_surface"] = {
            k: v for k, v in sorted(by_surface.items()) if k
        }
    if extra:
        doc.update(extra)
    return doc


def _replacement_map(
    r2_pos: list[dict[str, Any]],
    r21_pos: list[dict[str, Any]],
    r2_neg: list[dict[str, Any]],
    r21_neg: list[dict[str, Any]],
    patched_ids: list[dict[str, Any]],
) -> dict[str, Any]:
    pos_pairs = []
    for left, right in zip(r2_pos, r21_pos, strict=True):
        status = "paraphrased_target" if left["candidate_id"] in TARGET_PATCHES else "carried_forward"
        pos_pairs.append(
            {
                "r2_candidate_id": left["candidate_id"],
                "r2_1_candidate_id": right["candidate_id"],
                "axis": left.get("axis"),
                "split": left.get("split"),
                "cluster_id": left.get("cluster_id"),
                "r2_ask_hash": left.get("ask_hash"),
                "r2_1_ask_hash": right.get("ask_hash"),
                "r2_target_hash": left.get("target_hash"),
                "r2_1_target_hash": right.get("target_hash"),
                "r2_example_hash": left.get("example_hash"),
                "r2_1_example_hash": right.get("example_hash"),
                "status": status,
                "reason": PATCH_REASON if status == "paraphrased_target" else None,
            }
        )
    neg_pairs = []
    for left, right in zip(r2_neg, r21_neg, strict=True):
        neg_pairs.append(
            {
                "r2_candidate_id": left["candidate_id"],
                "r2_1_candidate_id": right["candidate_id"],
                "axis": left.get("axis"),
                "intended_audit_surface": left.get("intended_audit_surface"),
                "cluster_id": left.get("cluster_id"),
                "r2_ask_hash": left.get("ask_hash"),
                "r2_1_ask_hash": right.get("ask_hash"),
                "status": "carried_forward",
                "reason": None,
            }
        )
    return {
        "schema_version": "mouth_v3_r2_to_r2_1_replacement_map_v1",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "training_authorized": False,
        "optimizer_eligible": False,
        "canonical_corpus_admitted": False,
        "r1_dir": str(R1_DIR).replace("\\", "/"),
        "r2_dir": str(R2_DIR).replace("\\", "/"),
        "r2_1_dir": str(OUT_DIR).replace("\\", "/"),
        "patched_positives": patched_ids,
        "positives": pos_pairs,
        "negatives": neg_pairs,
        "counts": {
            "positive_paraphrased": sum(1 for p in pos_pairs if p["status"] == "paraphrased_target"),
            "positive_carried_forward": sum(
                1 for p in pos_pairs if p["status"] == "carried_forward"
            ),
            "negative_carried_forward": len(neg_pairs),
        },
        "note": (
            "R1 and R2 artifacts preserved. R2.1 paraphrases four identity targets that "
            "contained the complete normalized hidden observed answer "
            f"'{FORBIDDEN_HIDDEN_SPAN}'. No admission performed."
        ),
        "next_authorization_note": (
            "After R2.1 green audit, next authorization (not now) should be corpus "
            "admission only with split: 16 train positives → optimizer candidate corpus; "
            "8 development + 4 frozen + 4 adversarial → evaluation only; "
            "20 negatives → judge only, never optimizer input. "
            "Training remains a separate later decision."
        ),
    }


def main() -> int:
    r1_pos_path = R1_DIR / "mouth_v3_safe_positives_candidates.jsonl"
    r1_neg_path = R1_DIR / "mouth_v3_auditor_hard_negatives.jsonl"
    r2_pos_path = R2_DIR / "mouth_v3_safe_positives_candidates.jsonl"
    r2_neg_path = R2_DIR / "mouth_v3_auditor_hard_negatives.jsonl"

    r1_pos_sha_before = _file_sha256(r1_pos_path)
    r1_neg_sha_before = _file_sha256(r1_neg_path)
    r2_pos_sha_before = _file_sha256(r2_pos_path)
    r2_neg_sha_before = _file_sha256(r2_neg_path)

    r2_pos = _load_jsonl(r2_pos_path)
    r2_neg = _load_jsonl(r2_neg_path)
    if len(r2_pos) != 32:
        raise SystemExit(f"expected_32_r2_positives_got_{len(r2_pos)}")
    if len(r2_neg) != 20:
        raise SystemExit(f"expected_20_r2_negatives_got_{len(r2_neg)}")

    missing = [cid for cid in TARGET_PATCHES if not any(r["candidate_id"] == cid for r in r2_pos)]
    if missing:
        raise SystemExit(f"missing_r2_patch_targets:{missing}")

    patched_ids: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []
    for rec in r2_pos:
        old_id = rec["candidate_id"]
        if old_id in TARGET_PATCHES:
            new_target = TARGET_PATCHES[old_id]
            rebuilt = _rehash_positive(rec, new_target)
            stamped = _stamp_r21(rebuilt, old_id=old_id)
            patched_ids.append(
                {
                    "r2_candidate_id": old_id,
                    "r2_1_candidate_id": stamped["candidate_id"],
                    "old_target": rec["target"],
                    "new_target": new_target,
                    "reason": PATCH_REASON,
                }
            )
        else:
            rebuilt = _rehash_positive(dict(rec), str(rec["target"]))
            stamped = _stamp_r21(rebuilt, old_id=old_id)
        positives.append(stamped)

    negatives: list[dict[str, Any]] = []
    for rec in r2_neg:
        old_id = rec["candidate_id"]
        stamped = _stamp_r21(dict(rec), old_id=old_id)
        ask = str(stamped["ask"]).strip()
        neg = str(stamped.get("negative_response") or stamped["target"]).strip()
        ask_h = sha256_text(normalize_text(ask))
        target_h = sha256_text(normalize_text(neg))
        stamped["ask"] = ask
        stamped["negative_response"] = neg
        stamped["target"] = neg
        stamped["ask_hash"] = ask_h
        stamped["target_hash"] = target_h
        stamped["example_hash"] = _example_hash(ask, neg)
        stamped["pair_id"] = _pair_id(ask_h, target_h)
        negatives.append(stamped)

    if len(patched_ids) != 4:
        raise AssertionError(f"expected_4_patches_got_{len(patched_ids)}")

    # Containment gate on all positive targets.
    for rec in positives:
        norm = normalize_text(rec["target"])
        if FORBIDDEN_HIDDEN_SPAN in norm:
            raise AssertionError(
                f"forbidden_hidden_span_in_target:{rec['candidate_id']}:{norm}"
            )

    assert all(r["training_authorized"] is False for r in positives + negatives)
    assert all(r["optimizer_eligible"] is False for r in positives + negatives)
    assert all(r["admission_status"] == "CANDIDATE_HOLD" for r in positives + negatives)
    assert all(r["revision"] == REVISION for r in positives + negatives)
    assert all(str(r["candidate_id"]).startswith("mouth_v3_r2_1_") for r in positives + negatives)

    for rec in positives:
        _assert_positive_passes(rec)
    neg_judge_notes = [_assert_negative_fails(rec) for rec in negatives]

    if OUT_DIR.resolve() in {R1_DIR.resolve(), R2_DIR.resolve()}:
        raise SystemExit("refusing_to_write_into_r1_or_r2_dir")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pos_path = OUT_DIR / "mouth_v3_safe_positives_candidates.jsonl"
    neg_path = OUT_DIR / "mouth_v3_auditor_hard_negatives.jsonl"
    pos_sha = _write_jsonl(pos_path, positives)
    neg_sha = _write_jsonl(neg_path, negatives)

    # Taxonomy: copy R2 taxonomy with r2_1 stamp (clusters unchanged).
    tax_src = R2_DIR / "mouth_v3_semantic_cluster_taxonomy_r2.json"
    tax = json.loads(tax_src.read_text(encoding="utf-8"))
    tax["schema_version"] = "mouth_v3_semantic_cluster_taxonomy_r2_1_v1"
    tax["revision"] = REVISION
    tax["training_authorized"] = False
    tax["recorded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tax["source_r2_taxonomy"] = str(tax_src).replace("\\", "/")
    tax["note"] = "Clusters unchanged from R2; R2.1 only paraphrases four identity targets."
    (OUT_DIR / "mouth_v3_semantic_cluster_taxonomy_r2_1.json").write_text(
        json.dumps(tax, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    pos_manifest = _manifest(
        kind="safe_positive_targets",
        path=pos_path,
        sha=pos_sha,
        rows=positives,
        extra={
            "canonical_corpus_admitted": False,
            "r1_preserved_dir": str(R1_DIR).replace("\\", "/"),
            "r2_preserved_dir": str(R2_DIR).replace("\\", "/"),
            "patched_candidate_ids": [p["r2_1_candidate_id"] for p in patched_ids],
            "note": (
                "R2.1 candidates only. Not optimizer-ingestible while "
                "training_authorized=false. R1 and R2 dirs untouched."
            ),
        },
    )
    neg_manifest = _manifest(
        kind="auditor_hard_negatives",
        path=neg_path,
        sha=neg_sha,
        rows=negatives,
        extra={
            "canonical_corpus_admitted": False,
            "not_in_train_jsonl": True,
            "split_locked": "auditor",
            "negative_judge_notes": neg_judge_notes,
            "r1_preserved_dir": str(R1_DIR).replace("\\", "/"),
            "r2_preserved_dir": str(R2_DIR).replace("\\", "/"),
            "note": (
                "Auditor traps carried forward from R2 with r2_1 ids. "
                "optimizer_eligible=false."
            ),
        },
    )
    (OUT_DIR / "mouth_v3_safe_positives_candidates.manifest.json").write_text(
        json.dumps(pos_manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "mouth_v3_auditor_hard_negatives.manifest.json").write_text(
        json.dumps(neg_manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    repl = _replacement_map(r2_pos, positives, r2_neg, negatives, patched_ids)
    repl_path = OUT_DIR / "mouth_v3_r2_to_r2_1_replacement_map.json"
    repl_path.write_text(json.dumps(repl, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    design_path = CAMPAIGN / "TARGETED_MOUTH_CORPUS_DESIGN_V3.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("training_authorized") is not False:
        raise AssertionError("design_training_authorized_must_remain_false")

    # Confirm R1 and R2 untouched
    r1_pos_sha_after = _file_sha256(r1_pos_path)
    r1_neg_sha_after = _file_sha256(r1_neg_path)
    r2_pos_sha_after = _file_sha256(r2_pos_path)
    r2_neg_sha_after = _file_sha256(r2_neg_path)
    if r1_pos_sha_after != r1_pos_sha_before or r1_neg_sha_after != r1_neg_sha_before:
        raise AssertionError("r1_bytes_changed")
    if r2_pos_sha_after != r2_pos_sha_before or r2_neg_sha_after != r2_neg_sha_before:
        raise AssertionError("r2_bytes_changed")

    summary = {
        "ok": True,
        "revision": REVISION,
        "positives": len(positives),
        "negatives": len(negatives),
        "patched_positives": len(patched_ids),
        "pos_path": str(pos_path).replace("\\", "/"),
        "neg_path": str(neg_path).replace("\\", "/"),
        "pos_sha256": pos_sha,
        "neg_sha256": neg_sha,
        "replacement_map": str(repl_path).replace("\\", "/"),
        "r1_untouched": True,
        "r2_untouched": True,
        "r1_pos_sha256": r1_pos_sha_after,
        "r1_neg_sha256": r1_neg_sha_after,
        "r2_pos_sha256": r2_pos_sha_after,
        "r2_neg_sha256": r2_neg_sha_after,
        "training_authorized": False,
        "canonical_corpus_admitted": False,
        "patched_targets": {
            p["r2_1_candidate_id"]: p["new_target"] for p in patched_ids
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
