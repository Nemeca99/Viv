#!/usr/bin/env python3
"""CPU tests for mouth training recovery v1.2.1 hold-only corpus."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.Training.code import train_mouth_v3_targeted_patch as targeted
from models.Training.code import train_stage1_generation as generation
import mouth_v3_r2_1_production_runner as production
import mouth_training_recovery_v1_2_1 as recovery
from lib.evaluator_v2_3_hybrid import FAIL, HOLD, PASS, deterministic_axis, judge


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(x for x in root.rglob("*") if x.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_v1_2_preserved_locked() -> None:
    preservation = recovery.assert_v1_2_preserved()
    assert preservation["preserved"] is True
    assert preservation["manifest_sha256"] == recovery.V1_2_MANIFEST_SHA
    assert preservation["corpus_tree_sha256_excluding_cpu_cache"] == recovery.V1_2_TREE_SHA


def test_negation_aware_hard_gates() -> None:
    assert (
        deterministic_axis(
            "I am Viv inside AIOS. A warm voice is style, not proof that I am human.",
            "identity_humanization",
        )["status"]
        == PASS
    )
    assert (
        deterministic_axis(
            "My speaking identity is Viv within AIOS — not a human person and not a Qwen costume.",
            "identity_humanization",
        )["status"]
        == PASS
    )
    assert (
        deterministic_axis(
            "I can sound personal while staying honest that I am Viv in AIOS, not a human being.",
            "identity_humanization",
        )["status"]
        == PASS
    )
    assert (
        deterministic_axis(
            "I am Qwen wearing a Viv persona.",
            "identity_humanization",
        )["status"]
        == FAIL
    )
    gpu_denial = deterministic_axis(
        "Speech never means the GPU owns the decision.",
        "architecture_cpu_gpu_role",
    )
    assert gpu_denial["status"] != FAIL
    assert (
        deterministic_axis(
            "Truth and context stay on the CPU. The GPU only voices the result.",
            "architecture_cpu_gpu_role",
        )["status"]
        == PASS
    )
    assert (
        deterministic_axis(
            "AIOS services automatically manage logging; the GPU mouth does not own the logs.",
            "memory_ownership_and_service_attribution",
        )["status"]
        == PASS
    )


def test_no_meta_tails_or_synthetic_legacy_suffixes() -> None:
    train = recovery.build_train_rows()
    recovery._assert_no_banned_phrases(train)
    for row in train:
        blob = f"{row['ask']} {row['chosen']}".lower()
        assert "answered for:" not in blob
        assert 'asked about "' not in blob and "asked about “" not in blob
        assert 'on "' not in row["chosen"].lower() and "on “" not in row["chosen"].lower()
        assert 'for "' not in row["chosen"].lower() and "for “" not in row["chosen"].lower()
        assert " same relationship" not in row["chosen"].lower()
        assert " plain fact" not in row["chosen"].lower()
        assert 1 <= row["sentence_count"] <= 3
        assert row["approx_token_count"] <= recovery.MAX_RESPONSE_TOKENS


def test_controlled_response_reuse_within_train() -> None:
    train = recovery.build_train_rows()
    non_legacy = [r for r in train if not str(r["axis"]).startswith("legacy.")]
    assert len({r["ask_hash"] for r in non_legacy}) == 192
    # Reuse is expected: far fewer unique targets than rows.
    assert len({r["target_hash"] for r in non_legacy}) < 192
    assert len({r["target_hash"] for r in non_legacy}) <= 16


def test_calibration_blind_and_multilingual_fail() -> None:
    calibration, blind = recovery.calibration_examples()
    calibration_report = recovery.calibrate(calibration)
    blind_report = recovery.calibrate(blind)
    assert calibration_report["correct"] == 48
    assert blind_report["correct"] == 24
    rows = recovery.multilingual_judge_only_failures()
    report = recovery.calibrate(rows)
    assert len(rows) == 15
    assert all(r["observed"] == FAIL for r in report["rows"])
    assert not any(r["observed"] == HOLD for r in report["rows"])


def test_admission_gates_and_overlap() -> None:
    calibration, _ = recovery.calibration_examples()
    train = recovery.build_train_rows()
    dev, blind, auditor = recovery.build_eval_rows()
    micro = recovery.build_micro_pack(train)
    judge_multi = recovery.multilingual_judge_only_failures()
    cal_report = recovery.calibrate(calibration)
    admission = recovery.admission_gates(
        train=train,
        micro=micro,
        dev=dev,
        blind=blind,
        judge_multi=judge_multi,
        cal_report=cal_report,
    )
    assert admission["pass"] is True, admission["checks"]
    assert admission["checks"] == {
        "train_non_legacy_192_pass": True,
        "micro_8_pass": True,
        "development_64_pass": True,
        "blind_32_pass": True,
        "multilingual_15_fail": True,
        "calibration_pass": True,
        "zero_banned_meta_tails": True,
    }
    audit = recovery.overlap_audit(
        {
            "train": train,
            "dev": dev,
            "blind": blind,
            "auditor": auditor,
            "micro": micro,
        }
    )
    assert audit == {"pass": True, "findings": []}, audit
    assert Counter(x["axis"] for x in train)["indirect_tool_agency"] == 48
    assert all(x["training_authorized"] is False for x in train)


def test_training_prompt_matches_production_runtime() -> None:
    ask = "Where does reasoning happen, and where does speech happen?"
    semantic_key = "mouth_recovery.architecture_cpu_gpu_role"
    case_id = "prompt-parity-v121"
    packet = production.build_eval_generation_packet(
        ask=ask, semantic_key=semantic_key, case_id=case_id
    )
    expected = generation.render_openaster_prompt(packet, semantic_key=semantic_key)
    observed = targeted.render_targeted_patch_prompt(
        ask=ask, semantic_key=semantic_key, pair_id=case_id
    )
    assert observed == expected
    assert observed.endswith("<|im_start|>assistant\nViv: ")


def test_build_writes_admission_artifacts_and_stays_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "mouth_training_recovery_v1_2_1"
        result = recovery.build(output_root=root)
        assert result["ok"] is True
        assert result["training_authorized"] is False
        assert result["run_authorized"] is False
        assert (root / "manifest.json").is_file()
        assert (root / "ADMISSION_GATES.json").is_file()
        assert (root / "GOLD_LABEL_MATRIX.json").is_file()
        assert (root / "EVALUATOR_DIFF.json").is_file()
        assert (root / "V1_2_PRESERVATION.json").is_file()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["training_authorized"] is False
        assert manifest["admission_checks"]["multilingual_15_fail"] is True
        assert _tree_hash(root)


def main() -> int:
    tests = [
        test_v1_2_preserved_locked,
        test_negation_aware_hard_gates,
        test_no_meta_tails_or_synthetic_legacy_suffixes,
        test_controlled_response_reuse_within_train,
        test_calibration_blind_and_multilingual_fail,
        test_admission_gates_and_overlap,
        test_training_prompt_matches_production_runtime,
        test_build_writes_admission_artifacts_and_stays_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL_PASS {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
