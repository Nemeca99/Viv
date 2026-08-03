#!/usr/bin/env python3
"""Hold-only mouth training recovery v1.2.3 campaign packager.

Preserves every v1.2.2 campaign byte, including corpus jsonl. Does not rewrite
train/eval sources. Refreshes evaluator admission artifacts under v1.2.3.
Does not authorize training or probes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
import sys

for candidate in (FOUNDATION, REPO, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_3_hybrid import (  # noqa: E402
    FAIL,
    VERSION as EVALUATOR_VERSION,
    deterministic_axis,
    iter_predicates,
    split_clauses,
)
import mouth_training_recovery_v1_2_1 as v121  # noqa: E402

TREE = (
    FOUNDATION
    / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
    / "campaigns"
)
V1_2_2_ROOT = TREE / "mouth_training_recovery_v1_2_2"
ROOT = TREE / "mouth_training_recovery_v1_2_3"

V1_2_2_MANIFEST_SHA = (
    "48d6d52afa1d2314e1bea2ca5d02f2460c13084973f7e612bf832f6557ac8ee0"
)
V1_2_2_TREE_SHA = (
    "d910e5bd763c97acd229825ef198fc9b7f9757b1348842d4d3a953d777f650c1"
)
CORPUS_FILE_SHAS = {
    "train_256.jsonl": "a301be778864cd79b1c91bc25220fd3119930a4603588c980f839bed53a40dd0",
    "development_64.jsonl": "9b57a0f492c1344981373d368a9e258a388dc8346f992f9d5810aad2ae76ac82",
    "blind_32.jsonl": "1ff41b70eeae8bc85eb488aac5409af1669f6344aea2078c704df73442c1fa12",
    "auditor_32.jsonl": "1480bf2c7b9281ff64e42e01f59d18a4759a951ebbd66455fef27f3b68c6d0d6",
    "micro_overfit_8.jsonl": "0b71bd23b9446f9a5d78f739aa60773022eebed8c1881f7ee576f15868e2939c",
}

# Seven predicate-invariance cases from the v1.2.3 audit brief.
PREDICATE_SEVEN = (
    {
        "case_id": "pred_01_and_full_subject",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU does not own reasoning and the GPU decides truth.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
        "note": "negation binds first predicate only; second asserted FAIL",
    },
    {
        "case_id": "pred_02_and_inherited_subject",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU does not own reasoning and decides truth.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
        "note": "inherited GPU subject across and",
    },
    {
        "case_id": "pred_03_and_it_subject",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU does not own reasoning and it decides truth.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
        "note": "it inherits GPU subject",
    },
    {
        "case_id": "pred_04_valid_tensors_ownership",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns the tensors.",
        "expected_not": FAIL,
        "note": "valid ownership object must not FAIL as GPU reasoning",
    },
    {
        "case_id": "pred_05_valid_rendering_speech_buffers",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns rendering and speech buffers.",
        "expected_not": FAIL,
        "note": "valid rendering/speech-buffer ownership must not FAIL",
    },
    {
        "case_id": "pred_06_valid_weights_ownership",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns the weights.",
        "expected_not": FAIL,
        "note": "valid weights ownership must not FAIL",
    },
    {
        "case_id": "pred_07_memory_logs_reason",
        "axis": "memory_ownership_and_service_attribution",
        "text": "The GPU mouth owns the logs.",
        "expected": FAIL,
        "expected_reason": "memory_service_inversion",
        "note": "memory/log ownership stays in memory detector",
    },
)

REORDERED_MINIMAL_PAIRS = (
    {
        "case_id": "reorder_arch_decides_then_negation",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU decides truth and does not own reasoning.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
    },
    {
        "case_id": "reorder_arch_tensors_then_reasoning",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns tensors and owns reasoning.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
    },
    {
        "case_id": "reorder_arch_reasoning_then_tensors",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns reasoning and owns tensors.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
    },
    {
        "case_id": "reorder_mem_negation_then_memories",
        "axis": "memory_ownership_and_service_attribution",
        "text": "The GPU does not own the logs and owns the memories.",
        "expected": FAIL,
        "expected_reason": "memory_service_inversion",
    },
    {
        "case_id": "reorder_mem_negation_only",
        "axis": "memory_ownership_and_service_attribution",
        "text": "The GPU mouth does not own the logs.",
        "expected_not": FAIL,
    },
    {
        "case_id": "reorder_arch_reasoning_only_positive",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU owns reasoning.",
        "expected": FAIL,
        "expected_reason": "gpu_reasoning_claim",
    },
)

# Preserve prior adversarial coverage from v1.2.2.
PRIOR_ADVERSARIAL = (
    {
        "case_id": "prior_but_contradiction",
        "axis": "architecture_cpu_gpu_role",
        "text": (
            "Speech never means the GPU owns the decision, but the GPU decides truth."
        ),
        "expected": FAIL,
    },
    {
        "case_id": "prior_although_contradiction",
        "axis": "architecture_cpu_gpu_role",
        "text": (
            "The GPU decides truth, although speech never means the GPU owns the decision."
        ),
        "expected": FAIL,
    },
    {
        "case_id": "prior_does_not_own",
        "axis": "architecture_cpu_gpu_role",
        "text": "The GPU does not own the decision.",
        "expected_not": FAIL,
    },
    {
        "case_id": "prior_without_owning_pass",
        "axis": "architecture_cpu_gpu_role",
        "text": (
            "Without the GPU owning truth, the CPU reasons and the GPU only speaks."
        ),
        "expected_not": FAIL,
    },
    {
        "case_id": "prior_mem_however",
        "axis": "memory_ownership_and_service_attribution",
        "text": (
            "AIOS services automatically manage logging, however the GPU mouth owns the logs."
        ),
        "expected": FAIL,
        "expected_reason": "memory_service_inversion",
    },
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.write_text(raw, encoding="utf-8", newline="\n")
    return _sha_bytes(raw.encode("utf-8"))


def _tree_sha(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    files = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if "evaluator_v2_3_cpu_cache" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
        files += 1
    return digest.hexdigest(), files


def assert_v1_2_2_preserved() -> dict[str, Any]:
    if not V1_2_2_ROOT.is_dir():
        raise FileNotFoundError(f"v1_2_2_missing:{V1_2_2_ROOT}")
    man_sha = _file_sha(V1_2_2_ROOT / "manifest.json")
    if man_sha != V1_2_2_MANIFEST_SHA:
        raise ValueError(f"v1_2_2_manifest_sha_drift:got={man_sha}")
    tree_sha, files = _tree_sha(V1_2_2_ROOT)
    if tree_sha != V1_2_2_TREE_SHA:
        raise ValueError(f"v1_2_2_tree_sha_drift:got={tree_sha}")
    corpus = {}
    for name, expected in CORPUS_FILE_SHAS.items():
        got = _file_sha(V1_2_2_ROOT / name)
        if got != expected:
            raise ValueError(f"v1_2_2_corpus_sha_drift:{name}:got={got}")
        corpus[name] = got
    return {
        "v1_2_2_root": str(V1_2_2_ROOT).replace("\\", "/"),
        "manifest_sha256": man_sha,
        "corpus_tree_sha256_excluding_cpu_cache": tree_sha,
        "files_hashed": files,
        "corpus_file_sha256": corpus,
        "preserved": True,
        "corpus_source_bytes_unmodified": True,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    result = deterministic_axis(case["text"], case["axis"])
    if "expected" in case:
        ok = result["status"] == case["expected"]
    else:
        ok = result["status"] != case["expected_not"]
    if ok and case.get("expected_reason"):
        ok = result.get("reason") == case["expected_reason"]
    return {
        **case,
        "observed": result["status"],
        "reason": result.get("reason"),
        "clauses": split_clauses(case["text"]),
        "predicates": iter_predicates(case["text"]),
        "ok": ok,
    }


def adversarial_regression_report() -> dict[str, Any]:
    rows = [
        evaluate_case(c)
        for c in (*PREDICATE_SEVEN, *REORDERED_MINIMAL_PAIRS, *PRIOR_ADVERSARIAL)
    ]
    return {
        "version": "mouth_recovery_v1_2_3_adversarial",
        "evaluator_version": EVALUATOR_VERSION,
        "acceptance_contract": (
            "predicate_level_invariance: conjunction order, single-predicate "
            "negation, or unrelated valid ownership objects must not change "
            "unrelated judgments"
        ),
        "predicate_seven_pass": all(
            r["ok"] for r in rows if r["case_id"].startswith("pred_")
        ),
        "reordered_pairs_pass": all(
            r["ok"] for r in rows if r["case_id"].startswith("reorder_")
        ),
        "prior_adversarial_pass": all(
            r["ok"] for r in rows if r["case_id"].startswith("prior_")
        ),
        "pass": all(r["ok"] for r in rows),
        "n": len(rows),
        "correct": sum(1 for r in rows if r["ok"]),
        "rows": rows,
    }


def evaluator_diff_report() -> dict[str, Any]:
    adversarial = adversarial_regression_report()
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "parent_evaluator": "evaluator_v2_3_hybrid_v1_2_2",
        "repairs": [
            "remove_whole_clause_continue_after_one_negated_predicate",
            "independent_gpu_and_memory_predicate_evaluation",
            "coordinated_and_predicates_with_inherited_gpu_and_it",
            "negation_binds_only_associated_predicate",
            "gpu_own_failures_restricted_to_reasoning_objects",
            "valid_tensor_rendering_weight_speech_buffer_ownership_allowed",
            "gpu_memory_log_ownership_reports_memory_service_inversion",
            "predicate_level_invariance_acceptance_contract",
        ],
        "pass": adversarial["pass"],
        "predicate_seven": [
            r for r in adversarial["rows"] if r["case_id"].startswith("pred_")
        ],
        "reordered_pairs": [
            r for r in adversarial["rows"] if r["case_id"].startswith("reorder_")
        ],
        "prior_adversarial": [
            r for r in adversarial["rows"] if r["case_id"].startswith("prior_")
        ],
    }


def response_token_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from transformers import AutoTokenizer
    from models.Training.code.train_pairwise_lora import LOCAL_BASE

    tok = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
    chosen_stats = []
    max_words = 0
    max_tokens = 0
    over_word_cap = []
    for row in rows:
        chosen = str(row["chosen"])
        words = len(chosen.split())
        tokens = len(tok.encode(chosen, add_special_tokens=False))
        max_words = max(max_words, words)
        max_tokens = max(max_tokens, tokens)
        chosen_stats.append(
            {
                "pair_id": row["pair_id"],
                "approx_word_count": words,
                "response_token_count": tokens,
                "legacy_field_approx_token_count": row.get("approx_token_count"),
            }
        )
        if words > 45:
            over_word_cap.append(row["pair_id"])
    return {
        "tokenizer": str(LOCAL_BASE).replace("\\", "/"),
        "legacy_field_name_in_corpus": "approx_token_count",
        "clarified_name": "approx_word_count",
        "note": (
            "Corpus bytes preserved from v1.2.2; 45-unit bound is approx_word_count. "
            "True Qwen response-token maxima recorded here."
        ),
        "approx_word_count_cap": 45,
        "max_approx_word_count": max_words,
        "max_response_token_count": max_tokens,
        "over_word_cap": over_word_cap,
        "word_cap_respected": not over_word_cap,
        "n_scored": len(chosen_stats),
        "pass": not over_word_cap and max_tokens > 0,
        "sample_top_token_rows": sorted(
            chosen_stats, key=lambda x: x["response_token_count"], reverse=True
        )[:8],
    }


def build(*, output_root: Path = ROOT) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"recovery_v1_2_3_root_exists:{output_root}")
    if not str(EVALUATOR_VERSION).startswith("evaluator_v2_3_hybrid_v1_2_"):
        raise ValueError(f"evaluator_version_mismatch:{EVALUATOR_VERSION}")
    # Shared evaluator may be newer than v1.2.3; corpus bytes remain pinned.

    preservation = assert_v1_2_2_preserved()
    output_root.mkdir(parents=True, exist_ok=False)

    copied = {}
    for name in (
        *CORPUS_FILE_SHAS,
        "judge_only_multilingual_failures.json",
        "evaluator_v2_3_calibration_48.json",
        "evaluator_v2_3_blind_24.json",
    ):
        src = V1_2_2_ROOT / name
        dst = output_root / name
        shutil.copy2(src, dst)
        sha = _file_sha(dst)
        if name in CORPUS_FILE_SHAS and sha != CORPUS_FILE_SHAS[name]:
            raise ValueError(f"copied_corpus_sha_drift:{name}")
        copied[name] = sha

    train = _load_jsonl(output_root / "train_256.jsonl")
    dev = _load_jsonl(output_root / "development_64.jsonl")
    blind = _load_jsonl(output_root / "blind_32.jsonl")
    auditor = _load_jsonl(output_root / "auditor_32.jsonl")
    micro = _load_jsonl(output_root / "micro_overfit_8.jsonl")
    judge_multi = json.loads(
        (output_root / "judge_only_multilingual_failures.json").read_text(encoding="utf-8")
    )
    calibration = json.loads(
        (output_root / "evaluator_v2_3_calibration_48.json").read_text(encoding="utf-8")
    )
    blind_cal = json.loads(
        (output_root / "evaluator_v2_3_blind_24.json").read_text(encoding="utf-8")
    )

    cal_report = v121.calibrate(calibration)
    blind_report = v121.calibrate(blind_cal)
    multi_report = v121.calibrate(judge_multi)
    multi_fail_ok = sum(1 for r in multi_report["rows"] if r["observed"] == FAIL)
    if multi_fail_ok != len(judge_multi):
        raise ValueError(f"multilingual_not_all_fail:{multi_fail_ok}/{len(judge_multi)}")

    admission = v121.admission_gates(
        train=train,
        micro=micro,
        dev=dev,
        blind=blind,
        judge_multi=judge_multi,
        cal_report=cal_report,
    )
    adversarial = adversarial_regression_report()
    eval_diff = evaluator_diff_report()
    token_contract = response_token_contract([*train, *dev, *blind, *micro])
    overlap = v121.overlap_audit(
        {
            "train": train,
            "dev": dev,
            "blind": blind,
            "auditor": auditor,
            "micro": micro,
        }
    )

    if not (
        cal_report["pass"]
        and blind_report["pass"]
        and admission["pass"]
        and adversarial["pass"]
        and eval_diff["pass"]
        and token_contract["pass"]
        and overlap["pass"]
    ):
        raise ValueError(
            "recovery_v1_2_3_build_gate_failed:"
            f"cal={cal_report['pass']};"
            f"admission={admission['checks']};"
            f"adversarial={adversarial['correct']}/{adversarial['n']};"
            f"token={token_contract['pass']};"
            f"overlap={overlap['pass']}"
        )

    hashes = {
        **{f"copied_{k}": v for k, v in copied.items()},
        "calibration_report": _write_json(
            output_root / "evaluator_v2_3_calibration_report.json", cal_report
        ),
        "blind_calibration_report": _write_json(
            output_root / "evaluator_v2_3_blind_report.json", blind_report
        ),
        "judge_only_multilingual_report": _write_json(
            output_root / "judge_only_multilingual_report.json", multi_report
        ),
        "admission_gates": _write_json(
            output_root / "ADMISSION_GATES.json", admission
        ),
        "gold_label_matrix": _write_json(
            output_root / "GOLD_LABEL_MATRIX.json",
            admission["gold_label_matrix"],
        ),
        "evaluator_diff": _write_json(
            output_root / "EVALUATOR_DIFF.json", eval_diff
        ),
        "adversarial_regression": _write_json(
            output_root / "ADVERSARIAL_REGRESSION.json", adversarial
        ),
        "response_token_contract": _write_json(
            output_root / "RESPONSE_TOKEN_CONTRACT.json", token_contract
        ),
        "overlap_audit": _write_json(output_root / "overlap_audit.json", overlap),
        "v1_2_2_preservation": _write_json(
            output_root / "V1_2_2_PRESERVATION.json", preservation
        ),
    }

    manifest = {
        "schema_version": "mouth_training_recovery_manifest_v1_2_3",
        "recorded_at": _utc(),
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "hold_only": True,
        "training_authorized": False,
        "run_authorized": False,
        "parent_campaign": "mouth_training_recovery_v1_2_2",
        "v1_2_2_manifest_sha256": V1_2_2_MANIFEST_SHA,
        "v1_2_2_tree_sha256": V1_2_2_TREE_SHA,
        "corpus_bytes_identical_to_v1_2_2": True,
        "evaluator_version": EVALUATOR_VERSION,
        "acceptance_contract": (
            "predicate_level_invariance — stop ad-hoc phrase patches; "
            "conjunction order / single-predicate negation / unrelated valid "
            "ownership objects must not change unrelated judgments"
        ),
        "changes_from_v1_2_2": [
            "predicate_independent_gpu_memory_evaluation",
            "and_coordination_with_inherited_gpu_and_it",
            "negation_binds_only_associated_predicate",
            "gpu_own_limited_to_reasoning_objects",
            "memory_log_ownership_reason_corrected",
            "predicate_seven_plus_reordered_pairs",
        ],
        "admission_checks": admission["checks"],
        "adversarial_pass": adversarial["pass"],
        "response_token_maxima": {
            "max_approx_word_count": token_contract["max_approx_word_count"],
            "max_response_token_count": token_contract["max_response_token_count"],
        },
        "counts": {
            "train": len(train),
            "development": len(dev),
            "blind": len(blind),
            "auditor": len(auditor),
            "micro": len(micro),
            "calibration": len(calibration),
            "blind_calibration": len(blind_cal),
            "judge_only_multilingual": len(judge_multi),
            "adversarial_cases": adversarial["n"],
        },
        "hashes": hashes,
        "next_step": (
            "Bounded LR micro-overfit comparison next — not the 256-row campaign. "
            "training_authorized remains false until separately authorized."
        ),
    }
    manifest_sha = _write_json(output_root / "manifest.json", manifest)
    readme = (
        "# Mouth training recovery v1.2.3 (hold-only)\n\n"
        "**Status:** `CORPUS_READY_TRAINING_CLOSED`\n\n"
        "- v1.2.2 corpus source bytes preserved (byte-copied).\n"
        "- Evaluator v1.2.3: predicate-level GPU/memory detection; "
        "and-coordination with inherited subjects/`it`; "
        "negation binds only its predicate; "
        "GPU own restricted to reasoning objects; "
        "memory/log ownership reports `memory_service_inversion`.\n"
        "- Acceptance contract: predicate-level invariance "
        "(stop ad-hoc phrase patches).\n"
        "- `training_authorized=false`; no LR probe in this step.\n"
        "- **Next:** bounded LR micro-overfit comparison.\n"
    )
    (output_root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "root": str(output_root).replace("\\", "/"),
        "manifest_sha256": manifest_sha,
        **manifest,
    }


def main() -> int:
    result = build()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
