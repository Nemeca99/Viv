#!/usr/bin/env python3
"""CPU tests for mouth training recovery v1.2.4 clause-scoped subject state machine."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import mouth_training_recovery_v1_2_4 as recovery
from lib.evaluator_v2_3_hybrid import FAIL, VERSION, deterministic_axis, iter_predicates


def test_evaluator_version() -> None:
    assert VERSION == "evaluator_v2_3_hybrid_v1_2_4"


def test_subject_valid_five_and_inverse_fail() -> None:
    report = recovery.adversarial_regression_report()
    assert report["subject_valid_five_pass"] is True, [
        r for r in report["rows"] if r["case_id"].startswith("subj_valid_") and not r["ok"]
    ]
    assert report["subject_inverse_fail_pass"] is True
    assert report["prior_core_pass"] is True
    assert report["pass"] is True


def test_clause_scoped_reset_and_cpu_inheritance() -> None:
    text = "The GPU owns tensors. The CPU decides truth and owns context."
    preds = iter_predicates(text)
    assert preds[0]["subject"] == "gpu"
    assert preds[1]["subject"] == "cpu"
    assert preds[2]["subject"] == "cpu"
    assert preds[2]["predicate"] == "owns context"
    assert deterministic_axis(text, "architecture_cpu_gpu_role")["status"] != FAIL


def test_it_does_not_cross_sentence_boundary() -> None:
    text = "The GPU owns tensors. It decides truth."
    preds = iter_predicates(text)
    assert preds[1]["subject"] is None
    assert deterministic_axis(text, "architecture_cpu_gpu_role")["status"] != FAIL


def test_it_inherits_gpu_inside_clause() -> None:
    text = "The GPU owns reasoning and it decides truth."
    preds = iter_predicates(text)
    assert preds[1]["subject"] == "gpu"
    assert deterministic_axis(text, "architecture_cpu_gpu_role")["status"] == FAIL


def test_v1_2_3_preserved_locked() -> None:
    preservation = recovery.assert_v1_2_3_preserved()
    assert preservation["preserved"] is True
    assert preservation["manifest_sha256"] == recovery.V1_2_3_MANIFEST_SHA
    assert preservation["corpus_tree_sha256_excluding_cpu_cache"] == recovery.V1_2_3_TREE_SHA


def test_build_copies_corpus_and_stays_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "mouth_training_recovery_v1_2_4"
        result = recovery.build(output_root=root)
        assert result["ok"] is True
        assert result["training_authorized"] is False
        assert result["corpus_bytes_identical_to_v1_2_3"] is True
        for name, expected in recovery.CORPUS_FILE_SHAS.items():
            got = hashlib.sha256((root / name).read_bytes()).hexdigest()
            assert got == expected, name
        adv = json.loads(
            (root / "ADVERSARIAL_REGRESSION.json").read_text(encoding="utf-8")
        )
        assert adv["pass"] is True
        assert "clause_scoped_active_subject" in adv["acceptance_contract"]


def main() -> int:
    tests = [
        test_evaluator_version,
        test_subject_valid_five_and_inverse_fail,
        test_clause_scoped_reset_and_cpu_inheritance,
        test_it_does_not_cross_sentence_boundary,
        test_it_inherits_gpu_inside_clause,
        test_v1_2_3_preserved_locked,
        test_build_copies_corpus_and_stays_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL_PASS {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
