#!/usr/bin/env python3
"""Admit frozen mouth V3 R2.1 candidates into an immutable admitted corpus.

Reads R2.1 only. Writes a separate directory (v3_corpus_admitted_r2_1/).
Does not train, lease, promote, deploy, wire trainer, flip live pointers,
or mutate R1 / R2 / R2.1 bytes.

Status terminal for this step: CORPUS_ADMITTED_TRAINING_CLOSED
with training_authorized=false and run_authorized=false everywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

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
R2_1_DIR = CAMPAIGN / "v3_candidates_r2_1"
OUT_DIR = CAMPAIGN / "v3_corpus_admitted_r2_1"

STATUS = "CORPUS_ADMITTED_TRAINING_CLOSED"
CORPUS_REVISION = "admitted_r2_1"
JUDGE_PATH = FOUNDATION / "lib" / "evaluator_v2_2_rubric.py"
DESIGN_PATH = CAMPAIGN / "TARGETED_MOUTH_CORPUS_DESIGN_V3.json"
TAXONOMY_PATH = R2_1_DIR / "mouth_v3_semantic_cluster_taxonomy_r2_1.json"
R2_1_POS = R2_1_DIR / "mouth_v3_safe_positives_candidates.jsonl"
R2_1_NEG = R2_1_DIR / "mouth_v3_auditor_hard_negatives.jsonl"
R2_1_POS_MANIFEST = R2_1_DIR / "mouth_v3_safe_positives_candidates.manifest.json"
R2_1_NEG_MANIFEST = R2_1_DIR / "mouth_v3_auditor_hard_negatives.manifest.json"
R2_1_AUDIT = R2_1_DIR / "mouth_v3_overlap_audit_report.json"

# Content / doctrine fields must project byte/string-equal from R2.1.
# example_hash / ask_hash / target_hash / pair_id are content-derived and must
# remain identical (proves admission overlays do not rewrite text).
CONTENT_KEYS: frozenset[str] = frozenset(
    {
        "ask",
        "target",
        "licensed_positive_target",
        "negative_response",
        "ask_hash",
        "target_hash",
        "example_hash",
        "pair_id",
        "axis",
        "cluster_id",
        "semantic_family",
        "judge_rubric",
        "intended_relational_judge",
        "intended_fail_axis",
        "intended_audit_surface",
        "trap_kind",
        "reference_id",
        "reference_hash",
        "row_class",
        "schema_version",
        "source_kind",
        "author",
        "split",
        "candidate_id",
        "requires_licensed_positive_target",
        "hidden_overlap_checked",
        "dpo_pairwise_without_separate_auth",
        "revision",
    }
)
ADMISSION_OVERLAY_KEYS: frozenset[str] = frozenset(
    {
        "admission_status",
        "optimizer_eligible",
        "response_only_loss_allowed",
        "training_authorized",
        "run_authorized",
        "admitted_from",
        "corpus_revision",
        "source_candidate_id",
        "corpus_status",
        "status",
    }
)

TRAIN_SIDE_SPLITS = frozenset({"train", "development"})
HOLDOUT_SPLITS = frozenset({"frozen", "adversarial"})

EXPECTED_POS_SPLITS = {"train": 16, "development": 8, "frozen": 4, "adversarial": 4}
EXPECTED_AXIS_SPLIT = {
    "architecture_cpu_gpu_role": {"train": 4, "development": 2, "frozen": 1, "adversarial": 1},
    "identity_humanization": {"train": 4, "development": 2, "frozen": 1, "adversarial": 1},
    "indirect_tool_agency": {"train": 4, "development": 2, "frozen": 1, "adversarial": 1},
    "memory_ownership_and_service_attribution": {
        "train": 4,
        "development": 2,
        "frozen": 1,
        "adversarial": 1,
    },
}


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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    return _file_sha256(path)


def _write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return _file_sha256(path)


def _snapshot_dir_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = _file_sha256(path)
    return out


def _routing_for_positive(split: str) -> dict[str, Any]:
    if split == "train":
        return {
            "admission_status": "TRAIN_READY",
            "optimizer_eligible": True,
            "response_only_loss_allowed": True,
        }
    if split in {"development", "frozen", "adversarial"}:
        return {
            "admission_status": "EVALUATION_READY",
            "optimizer_eligible": False,
            "response_only_loss_allowed": False,
        }
    raise ValueError(f"unexpected_positive_split:{split}")


def _admit_row(row: dict[str, Any], *, kind: str) -> dict[str, Any]:
    out = dict(row)
    cid = str(row["candidate_id"])
    if kind == "positive":
        out.update(_routing_for_positive(str(row["split"])))
    elif kind == "negative":
        out["admission_status"] = "AUDITOR_ONLY"
        out["optimizer_eligible"] = False
        out["response_only_loss_allowed"] = False
    else:
        raise ValueError(f"unknown_kind:{kind}")
    out["training_authorized"] = False
    out["run_authorized"] = False
    out["admitted_from"] = "v3_candidates_r2_1"
    out["corpus_revision"] = CORPUS_REVISION
    out["source_candidate_id"] = cid
    out["corpus_status"] = STATUS
    return out


def assert_content_projection(admitted: dict[str, Any], source: dict[str, Any]) -> None:
    for key in CONTENT_KEYS:
        if key not in source and key not in admitted:
            continue
        if source.get(key) != admitted.get(key):
            raise AssertionError(
                f"content_projection_mismatch:{source.get('candidate_id')}:{key}:"
                f"{source.get(key)!r}!={admitted.get(key)!r}"
            )


def validate_admitted_projection(
    admitted_positives: list[dict[str, Any]],
    admitted_negatives: list[dict[str, Any]],
    source_positives: list[dict[str, Any]],
    source_negatives: list[dict[str, Any]],
) -> dict[str, Any]:
    src_pos = {str(r["pair_id"]): r for r in source_positives}
    src_neg = {str(r["pair_id"]): r for r in source_negatives}
    if len(src_pos) != len(source_positives) or len(src_neg) != len(source_negatives):
        raise AssertionError("source_pair_id_not_unique")

    for row in admitted_positives:
        src = src_pos.get(str(row["pair_id"]))
        if src is None:
            raise AssertionError(f"missing_source_positive:{row.get('candidate_id')}")
        extra = set(row) - set(src) - ADMISSION_OVERLAY_KEYS
        if extra:
            raise AssertionError(f"unexpected_admitted_keys:{row.get('candidate_id')}:{sorted(extra)}")
        for key in set(src) - set(row):
            if key not in ADMISSION_OVERLAY_KEYS:
                raise AssertionError(f"dropped_source_key:{row.get('candidate_id')}:{key}")
        assert_content_projection(row, src)

    for row in admitted_negatives:
        src = src_neg.get(str(row["pair_id"]))
        if src is None:
            raise AssertionError(f"missing_source_negative:{row.get('candidate_id')}")
        extra = set(row) - set(src) - ADMISSION_OVERLAY_KEYS
        if extra:
            raise AssertionError(f"unexpected_admitted_keys:{row.get('candidate_id')}:{sorted(extra)}")
        for key in set(src) - set(row):
            if key not in ADMISSION_OVERLAY_KEYS:
                raise AssertionError(f"dropped_source_key:{row.get('candidate_id')}:{key}")
        assert_content_projection(row, src)

    return {
        "method": (
            "Match on pair_id; assert CONTENT_KEYS equal (incl. ask/target/"
            "licensed_positive_target/negative_response and content hashes); "
            "only ADMISSION_OVERLAY_KEYS may differ. example_hash is content-only "
            "(ask||target normalize) so identity with R2.1 proves text projection."
        ),
        "match_key": "pair_id",
        "content_keys": sorted(CONTENT_KEYS),
        "allowed_overlay_keys": sorted(ADMISSION_OVERLAY_KEYS),
        "positives_checked": len(admitted_positives),
        "negatives_checked": len(admitted_negatives),
        "pass": True,
    }


def assert_cluster_isolation(positives: list[dict[str, Any]]) -> None:
    cluster_to_splits: dict[str, set[str]] = defaultdict(set)
    for row in positives:
        cluster_to_splits[str(row["cluster_id"])].add(str(row["split"]))
    for cid, splits in cluster_to_splits.items():
        if (splits & TRAIN_SIDE_SPLITS) and (splits & HOLDOUT_SPLITS):
            raise AssertionError(f"cluster_leak:{cid}:{sorted(splits)}")


def assert_routing_and_counts(positives: list[dict[str, Any]], negatives: list[dict[str, Any]]) -> None:
    by_split = Counter(str(r["split"]) for r in positives)
    if dict(by_split) != EXPECTED_POS_SPLITS:
        raise AssertionError(f"positive_split_counts:{dict(by_split)}")
    if len(negatives) != 20:
        raise AssertionError(f"negative_count:{len(negatives)}")

    axis_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row in positives:
        axis_split[str(row["axis"])][str(row["split"])] += 1
    for axis, expected in EXPECTED_AXIS_SPLIT.items():
        got = dict(axis_split[axis])
        if got != expected:
            raise AssertionError(f"axis_split_balance:{axis}:{got}!={expected}")

    train_ready = 0
    for row in positives:
        split = str(row["split"])
        routing = _routing_for_positive(split)
        for key, value in routing.items():
            if row.get(key) != value:
                raise AssertionError(
                    f"routing_mismatch:{row.get('candidate_id')}:{key}:{row.get(key)!r}!={value!r}"
                )
        if row.get("training_authorized") is not False:
            raise AssertionError(f"training_authorized:{row.get('candidate_id')}")
        if row.get("run_authorized") is not False:
            raise AssertionError(f"run_authorized:{row.get('candidate_id')}")
        if row.get("corpus_status") != STATUS:
            raise AssertionError(f"corpus_status:{row.get('candidate_id')}")
        if split == "train":
            train_ready += 1

    if train_ready != 16:
        raise AssertionError(f"train_ready_count:{train_ready}")

    response_only_true = [r["candidate_id"] for r in positives if r.get("response_only_loss_allowed") is True]
    if len(response_only_true) != 16:
        raise AssertionError(f"response_only_true_count:{len(response_only_true)}")
    if any(str(r["split"]) != "train" for r in positives if r.get("response_only_loss_allowed")):
        raise AssertionError("response_only_outside_train")

    for row in negatives:
        if row.get("admission_status") != "AUDITOR_ONLY":
            raise AssertionError(f"neg_status:{row.get('candidate_id')}")
        if row.get("optimizer_eligible") is not False:
            raise AssertionError(f"neg_optimizer:{row.get('candidate_id')}")
        if row.get("response_only_loss_allowed") is not False:
            raise AssertionError(f"neg_response_only:{row.get('candidate_id')}")
        if row.get("training_authorized") is not False:
            raise AssertionError(f"neg_training_authorized:{row.get('candidate_id')}")
        if row.get("run_authorized") is not False:
            raise AssertionError(f"neg_run_authorized:{row.get('candidate_id')}")


def _verify_source_manifest_jsonl(*, source_jsonl: Path, source_manifest: Path, manifest_kind: str) -> None:
    manifest = _load_json(source_manifest)
    if manifest.get("kind") != manifest_kind:
        raise AssertionError(f"source_manifest_kind_mismatch:{source_manifest}:{manifest.get('kind')}")
    if manifest.get("sha256") != _file_sha256(source_jsonl):
        raise AssertionError(f"source_manifest_sha_mismatch:{source_jsonl}")
    if int(manifest.get("count", -1)) != len(_load_jsonl(source_jsonl)):
        raise AssertionError(f"source_manifest_count_mismatch:{source_jsonl}")


def _require_design_authorization_closed(design_path: Path) -> None:
    design = _load_json(design_path)
    for key in ("training_authorized", "run_authorized", "lora_authorized", "dpo_authorized"):
        if design.get(key) is not False:
            raise AssertionError(f"design_authorization_not_false:{key}:{design.get(key)!r}")


def _require_locked_overlap_report_clean(report_path: Path) -> None:
    report = _load_json(report_path)
    if report.get("pass") is not True:
        raise AssertionError("locked_overlap_report_not_pass")
    findings = report.get("findings", [])
    if not isinstance(findings, list) or findings:
        raise AssertionError(f"locked_overlap_report_findings_nonzero:{len(findings)}")
    exit_criteria = report.get("exit_criteria")
    if not isinstance(exit_criteria, dict) or not exit_criteria:
        raise AssertionError("locked_overlap_report_missing_exit_criteria")
    nonzero = {k: v for k, v in exit_criteria.items() if int(v) != 0}
    if nonzero:
        raise AssertionError(f"locked_overlap_report_nonzero_exit_criteria:{nonzero}")


def _compute_locked_hashes() -> dict[str, dict[str, str]]:
    return {
        "r2_1_positives_jsonl": {"path": str(R2_1_POS).replace("\\", "/"), "sha256": _file_sha256(R2_1_POS)},
        "r2_1_negatives_jsonl": {"path": str(R2_1_NEG).replace("\\", "/"), "sha256": _file_sha256(R2_1_NEG)},
        "r2_1_overlap_audit_report_json": {
            "path": str(R2_1_AUDIT).replace("\\", "/"),
            "sha256": _file_sha256(R2_1_AUDIT),
        },
        "design_TARGETED_MOUTH_CORPUS_DESIGN_V3_json": {
            "path": str(DESIGN_PATH).replace("\\", "/"),
            "sha256": _file_sha256(DESIGN_PATH),
        },
        "taxonomy_r2_1": {"path": str(TAXONOMY_PATH).replace("\\", "/"), "sha256": _file_sha256(TAXONOMY_PATH)},
        "judge_evaluator_v2_2_rubric_py": {
            "path": str(JUDGE_PATH).replace("\\", "/"),
            "sha256": _file_sha256(JUDGE_PATH),
        },
    }


def _build_admitted_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _require_locked_overlap_report_clean(R2_1_AUDIT)
    _require_design_authorization_closed(DESIGN_PATH)
    _verify_source_manifest_jsonl(
        source_jsonl=R2_1_POS,
        source_manifest=R2_1_POS_MANIFEST,
        manifest_kind="safe_positive_targets",
    )
    _verify_source_manifest_jsonl(
        source_jsonl=R2_1_NEG,
        source_manifest=R2_1_NEG_MANIFEST,
        manifest_kind="auditor_hard_negatives",
    )
    source_pos = _load_jsonl(R2_1_POS)
    source_neg = _load_jsonl(R2_1_NEG)
    admitted_pos = [_admit_row(r, kind="positive") for r in source_pos]
    admitted_neg = [_admit_row(r, kind="negative") for r in source_neg]
    projection = validate_admitted_projection(admitted_pos, admitted_neg, source_pos, source_neg)
    assert_cluster_isolation(admitted_pos)
    assert_routing_and_counts(admitted_pos, admitted_neg)
    return admitted_pos, admitted_neg, projection


def admit(*, output_dir: Path = OUT_DIR) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"admitted_output_already_exists_refusing_overwrite:{output_dir}")

    pre_hashes = {
        "v3_candidates": _snapshot_dir_hashes(R1_DIR),
        "v3_candidates_r2": _snapshot_dir_hashes(R2_DIR),
        "v3_candidates_r2_1": _snapshot_dir_hashes(R2_1_DIR),
    }
    locked = _compute_locked_hashes()
    admitted_pos, admitted_neg, projection = _build_admitted_rows()

    output_dir.mkdir(parents=True, exist_ok=False)
    pos_path = output_dir / "mouth_v3_safe_positives_admitted.jsonl"
    neg_path = output_dir / "mouth_v3_auditor_hard_negatives_admitted.jsonl"
    pos_sha = _write_jsonl(pos_path, admitted_pos)
    neg_sha = _write_jsonl(neg_path, admitted_neg)
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pos_manifest = {
        "schema_version": "mouth_v3_admitted_manifest_v1",
        "corpus_revision": CORPUS_REVISION,
        "status": STATUS,
        "kind": "safe_positive_targets_admitted",
        "path": str(pos_path).replace("\\", "/"),
        "sha256": pos_sha,
        "count": len(admitted_pos),
        "counts_by_axis": dict(sorted(Counter(str(r["axis"]) for r in admitted_pos).items())),
        "counts_by_split": dict(sorted(Counter(str(r["split"]) for r in admitted_pos).items())),
        "counts_by_admission_status": dict(
            sorted(Counter(str(r["admission_status"]) for r in admitted_pos).items())
        ),
        "optimizer_eligible_train_only": True,
        "optimizer_eligible_count": sum(1 for r in admitted_pos if r.get("optimizer_eligible") is True),
        "response_only_loss_allowed_count": sum(
            1 for r in admitted_pos if r.get("response_only_loss_allowed") is True
        ),
        "training_authorized": False,
        "run_authorized": False,
        "source_r2_1_path": locked["r2_1_positives_jsonl"]["path"],
        "source_r2_1_sha256": locked["r2_1_positives_jsonl"]["sha256"],
        "recorded_at": recorded_at,
    }
    neg_manifest = {
        "schema_version": "mouth_v3_admitted_manifest_v1",
        "corpus_revision": CORPUS_REVISION,
        "status": STATUS,
        "kind": "auditor_hard_negatives_admitted",
        "path": str(neg_path).replace("\\", "/"),
        "sha256": neg_sha,
        "count": len(admitted_neg),
        "counts_by_axis": dict(sorted(Counter(str(r["axis"]) for r in admitted_neg).items())),
        "admission_status": "AUDITOR_ONLY",
        "optimizer_eligible_any": False,
        "response_only_loss_allowed_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "not_in_train_jsonl": True,
        "split_locked": "auditor",
        "source_r2_1_path": locked["r2_1_negatives_jsonl"]["path"],
        "source_r2_1_sha256": locked["r2_1_negatives_jsonl"]["sha256"],
        "recorded_at": recorded_at,
    }
    _write_json(output_dir / "mouth_v3_safe_positives_admitted.manifest.json", pos_manifest)
    _write_json(output_dir / "mouth_v3_auditor_hard_negatives_admitted.manifest.json", neg_manifest)

    _write_json(
        output_dir / "STATUS.json",
        {
            "status": STATUS,
            "corpus_revision": CORPUS_REVISION,
            "training_authorized": False,
            "run_authorized": False,
            "lora_authorized": False,
            "dpo_authorized": False,
            "admitted_from": str(R2_1_DIR).replace("\\", "/"),
            "positives": str(pos_path).replace("\\", "/"),
            "negatives": str(neg_path).replace("\\", "/"),
            "recorded_at": recorded_at,
            "next_authorized_step_not_done": (
                "Construct a bounded training experiment + preflight only. "
                "Do not run GPU training, open a lease, promote, or deploy."
            ),
        },
    )
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# Mouth V3 corpus - admitted R2.1",
                "",
                f"**Status: `{STATUS}`**",
                "",
                "- `training_authorized=false`",
                "- `run_authorized=false`",
                "",
                "Next authorized step (NOT done here): bounded training experiment + preflight only.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    manifest_path = output_dir / "mouth_v3_corpus_admission_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "mouth_v3_corpus_admission_manifest_v1",
            "status": STATUS,
            "corpus_revision": CORPUS_REVISION,
            "training_authorized": False,
            "run_authorized": False,
            "admission_timestamp": recorded_at,
            "source_paths": {
                "r1_dir": str(R1_DIR).replace("\\", "/"),
                "r2_dir": str(R2_DIR).replace("\\", "/"),
                "r2_1_dir": str(R2_1_DIR).replace("\\", "/"),
                "admitted_dir": str(output_dir).replace("\\", "/"),
            },
            "locked_source_hashes": locked,
            "admitted_artifacts": {
                "positives_jsonl": {"path": str(pos_path).replace("\\", "/"), "sha256": pos_sha, "count": 32},
                "negatives_jsonl": {"path": str(neg_path).replace("\\", "/"), "sha256": neg_sha, "count": 20},
            },
            "routing_summary": {
                "train_positives_TRAIN_READY_optimizer_response_only": 16,
                "development_positives_EVALUATION_READY": 8,
                "frozen_positives_EVALUATION_READY": 4,
                "adversarial_positives_EVALUATION_READY": 4,
                "auditor_negatives_AUDITOR_ONLY": 20,
            },
            "projection_proof": projection,
            "pre_admission_candidate_tree_hashes": pre_hashes,
        },
    )

    post_hashes = {
        "v3_candidates": _snapshot_dir_hashes(R1_DIR),
        "v3_candidates_r2": _snapshot_dir_hashes(R2_DIR),
        "v3_candidates_r2_1": _snapshot_dir_hashes(R2_1_DIR),
    }
    if post_hashes != pre_hashes:
        raise AssertionError("candidate_trees_mutated_during_admission")

    return {
        "status": STATUS,
        "out_dir": str(output_dir).replace("\\", "/"),
        "manifest": str(manifest_path).replace("\\", "/"),
        "training_authorized": False,
        "run_authorized": False,
    }


def verify_existing(*, output_dir: Path = OUT_DIR) -> dict[str, Any]:
    if not output_dir.exists():
        raise FileNotFoundError(f"admitted_output_missing:{output_dir}")
    pos_path = output_dir / "mouth_v3_safe_positives_admitted.jsonl"
    neg_path = output_dir / "mouth_v3_auditor_hard_negatives_admitted.jsonl"
    manifest_path = output_dir / "mouth_v3_corpus_admission_manifest.json"
    status_path = output_dir / "STATUS.json"
    for required in (pos_path, neg_path, manifest_path, status_path):
        if not required.is_file():
            raise FileNotFoundError(f"admitted_required_missing:{required}")

    _require_locked_overlap_report_clean(R2_1_AUDIT)
    _require_design_authorization_closed(DESIGN_PATH)
    _verify_source_manifest_jsonl(
        source_jsonl=R2_1_POS,
        source_manifest=R2_1_POS_MANIFEST,
        manifest_kind="safe_positive_targets",
    )
    _verify_source_manifest_jsonl(
        source_jsonl=R2_1_NEG,
        source_manifest=R2_1_NEG_MANIFEST,
        manifest_kind="auditor_hard_negatives",
    )
    positives = _load_jsonl(pos_path)
    negatives = _load_jsonl(neg_path)
    projection = validate_admitted_projection(positives, negatives, _load_jsonl(R2_1_POS), _load_jsonl(R2_1_NEG))
    assert_cluster_isolation(positives)
    assert_routing_and_counts(positives, negatives)

    manifest = _load_json(manifest_path)
    status_doc = _load_json(status_path)
    if manifest.get("status") != STATUS or status_doc.get("status") != STATUS:
        raise AssertionError("existing_status_mismatch")
    if manifest.get("training_authorized") is not False or status_doc.get("training_authorized") is not False:
        raise AssertionError("existing_training_authorized_not_false")
    if manifest.get("run_authorized") is not False or status_doc.get("run_authorized") is not False:
        raise AssertionError("existing_run_authorized_not_false")

    locked = manifest.get("locked_source_hashes", {})
    for key, source in _compute_locked_hashes().items():
        if locked.get(key, {}).get("sha256") != source["sha256"]:
            raise AssertionError(f"locked_source_hash_mismatch:{key}")
    if manifest.get("admitted_artifacts", {}).get("positives_jsonl", {}).get("sha256") != _file_sha256(pos_path):
        raise AssertionError("admitted_positives_hash_mismatch")
    if manifest.get("admitted_artifacts", {}).get("negatives_jsonl", {}).get("sha256") != _file_sha256(neg_path):
        raise AssertionError("admitted_negatives_hash_mismatch")

    return {
        "status": STATUS,
        "mode": "verify_existing",
        "verified": True,
        "out_dir": str(output_dir).replace("\\", "/"),
        "projection_checked": projection["pass"],
        "training_authorized": False,
        "run_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    result = verify_existing(output_dir=args.output_dir) if args.verify_existing else admit(output_dir=args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
