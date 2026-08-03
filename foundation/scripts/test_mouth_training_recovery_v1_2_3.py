#!/usr/bin/env python3
"""CPU tests for mouth training recovery v1.2.3 predicate-level evaluator."""
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

import mouth_training_recovery_v1_2_3 as recovery
from lib.evaluator_v2_3_hybrid import FAIL, PASS, VERSION, deterministic_axis, iter_predicates


def test_evaluator_version() -> None:
    assert VERSION.startswith("evaluator_v2_3_hybrid_v1_2_")
    assert VERSION >= "evaluator_v2_3_hybrid_v1_2_3"


def test_predicate_seven_and_reordered_pairs() -> None:
    report = recovery.adversarial_regression_report()
    assert report["predicate_seven_pass"] is True, [
        r for r in report["rows"] if r["case_id"].startswith("pred_") and not r["ok"]
    ]
    assert report["reordered_pairs_pass"] is True
    assert report["prior_adversarial_pass"] is True
    assert report["pass"] is True


def test_negation_does_not_bleed_across_and() -> None:
    text = "The GPU does not own reasoning and decides truth."
    preds = iter_predicates(text)
    assert len(preds) == 2
    assert preds[0]["negated"] is True
    assert preds[1]["negated"] is False
    assert preds[1]["subject"] == "gpu"
    assert deterministic_axis(text, "architecture_cpu_gpu_role")["status"] == FAIL


def test_valid_ownership_objects_do_not_fail() -> None:
    for text in (
        "The GPU owns the tensors.",
        "The GPU owns rendering and speech buffers.",
        "The GPU owns the weights.",
    ):
        assert (
            deterministic_axis(text, "architecture_cpu_gpu_role")["status"] != FAIL
        ), text


def test_memory_log_ownership_reason() -> None:
    result = deterministic_axis(
        "The GPU mouth owns the logs.",
        "memory_ownership_and_service_attribution",
    )
    assert result["status"] == FAIL
    assert result["reason"] == "memory_service_inversion"


def test_v1_2_2_preserved_locked() -> None:
    preservation = recovery.assert_v1_2_2_preserved()
    assert preservation["preserved"] is True
    assert preservation["manifest_sha256"] == recovery.V1_2_2_MANIFEST_SHA
    assert preservation["corpus_tree_sha256_excluding_cpu_cache"] == recovery.V1_2_2_TREE_SHA


def test_build_copies_corpus_bytes_and_stays_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "mouth_training_recovery_v1_2_3"
        result = recovery.build(output_root=root)
        assert result["ok"] is True
        assert result["training_authorized"] is False
        assert result["corpus_bytes_identical_to_v1_2_2"] is True
        for name, expected in recovery.CORPUS_FILE_SHAS.items():
            got = hashlib.sha256((root / name).read_bytes()).hexdigest()
            assert got == expected, name
        adv = json.loads(
            (root / "ADVERSARIAL_REGRESSION.json").read_text(encoding="utf-8")
        )
        assert adv["pass"] is True
        assert "predicate_level_invariance" in adv["acceptance_contract"]


def main() -> int:
    tests = [
        test_evaluator_version,
        test_predicate_seven_and_reordered_pairs,
        test_negation_does_not_bleed_across_and,
        test_valid_ownership_objects_do_not_fail,
        test_memory_log_ownership_reason,
        test_v1_2_2_preserved_locked,
        test_build_copies_corpus_bytes_and_stays_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL_PASS {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
