#!/usr/bin/env python3
"""CPU tests for mouth training recovery v1.2.2 evaluator + campaign pack."""
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

import mouth_training_recovery_v1_2_2 as recovery
from lib.evaluator_v2_3_hybrid import FAIL, PASS, VERSION, deterministic_axis, split_clauses


def test_evaluator_version() -> None:
    # Shared evaluator advances; v1.2.2 campaign remains frozen. Require at least v1.2.2 semantics.
    assert VERSION.startswith("evaluator_v2_3_hybrid_v1_2_")
    assert VERSION >= "evaluator_v2_3_hybrid_v1_2_2"


def test_codex_audit_four() -> None:
    report = recovery.adversarial_regression_report()
    assert report["codex_audit_four_pass"] is True, [
        r for r in report["rows"] if r["case_id"].startswith("codex_audit_") and not r["ok"]
    ]
    assert report["minimal_pairs_pass"] is True
    assert report["pass"] is True


def test_clause_split_adversatives() -> None:
    clauses = split_clauses(
        "Speech never means the GPU owns the decision, but the GPU decides truth."
    )
    assert clauses == [
        "speech never means the gpu owns the decision",
        "the gpu decides truth",
    ]
    clauses2 = split_clauses(
        "AIOS services automatically manage logging, however the GPU mouth owns the logs."
    )
    assert "the gpu mouth owns the logs" in clauses2


def test_valid_negation_vs_contradiction() -> None:
    assert (
        deterministic_axis(
            "The GPU does not own the decision.",
            "architecture_cpu_gpu_role",
        )["status"]
        != FAIL
    )
    assert (
        deterministic_axis(
            "Speech never means the GPU owns the decision, but the GPU decides truth.",
            "architecture_cpu_gpu_role",
        )["status"]
        == FAIL
    )
    assert (
        deterministic_axis(
            "Without the GPU owning truth, the CPU reasons and the GPU only speaks.",
            "architecture_cpu_gpu_role",
        )["status"]
        == PASS
    )


def test_v1_2_1_preserved_locked() -> None:
    preservation = recovery.assert_v1_2_1_preserved()
    assert preservation["preserved"] is True
    assert preservation["manifest_sha256"] == recovery.V1_2_1_MANIFEST_SHA
    assert preservation["corpus_tree_sha256_excluding_cpu_cache"] == recovery.V1_2_1_TREE_SHA


def test_build_copies_corpus_bytes_and_stays_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "mouth_training_recovery_v1_2_2"
        result = recovery.build(output_root=root)
        assert result["ok"] is True
        assert result["training_authorized"] is False
        assert result["corpus_bytes_identical_to_v1_2_1"] is True
        for name, expected in recovery.CORPUS_FILE_SHAS.items():
            got = hashlib.sha256((root / name).read_bytes()).hexdigest()
            assert got == expected, name
            parent = hashlib.sha256(
                (recovery.V1_2_1_ROOT / name).read_bytes()
            ).hexdigest()
            assert got == parent
        for required in (
            "manifest.json",
            "ADMISSION_GATES.json",
            "GOLD_LABEL_MATRIX.json",
            "EVALUATOR_DIFF.json",
            "ADVERSARIAL_REGRESSION.json",
            "RESPONSE_TOKEN_CONTRACT.json",
            "V1_2_1_PRESERVATION.json",
        ):
            assert (root / required).is_file(), required
        token = json.loads(
            (root / "RESPONSE_TOKEN_CONTRACT.json").read_text(encoding="utf-8")
        )
        assert token["clarified_name"] == "approx_word_count"
        assert token["max_response_token_count"] > 0
        assert token["pass"] is True
        adv = json.loads(
            (root / "ADVERSARIAL_REGRESSION.json").read_text(encoding="utf-8")
        )
        assert adv["pass"] is True


def main() -> int:
    tests = [
        test_evaluator_version,
        test_codex_audit_four,
        test_clause_split_adversatives,
        test_valid_negation_vs_contradiction,
        test_v1_2_1_preserved_locked,
        test_build_copies_corpus_bytes_and_stays_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"ALL_PASS {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
