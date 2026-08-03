#!/usr/bin/env python3
"""Tests for mouth V3 R2.1 → admitted corpus projection and routing gates."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
SCRIPTS = Path(__file__).resolve().parent
for candidate in (FOUNDATION, REPO, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import admit_mouth_v3_corpus_r2_1 as admit  # noqa: E402

R2_1_DIR = admit.R2_1_DIR
STATUS = admit.STATUS


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class MouthV3CorpusAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="admit_r2_1_test_")
        cls.out_dir = Path(cls._tmpdir.name) / "v3_corpus_admitted_r2_1_test"
        result = admit.admit(output_dir=cls.out_dir)
        cls.admit_result = result
        cls.positives = _load_jsonl(cls.out_dir / "mouth_v3_safe_positives_admitted.jsonl")
        cls.negatives = _load_jsonl(cls.out_dir / "mouth_v3_auditor_hard_negatives_admitted.jsonl")
        cls.source_pos = _load_jsonl(R2_1_DIR / "mouth_v3_safe_positives_candidates.jsonl")
        cls.source_neg = _load_jsonl(R2_1_DIR / "mouth_v3_auditor_hard_negatives.jsonl")
        cls.manifest = json.loads(
            (cls.out_dir / "mouth_v3_corpus_admission_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        cls.status = json.loads((cls.out_dir / "STATUS.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_01_counts(self) -> None:
        by_split = Counter(r["split"] for r in self.positives)
        self.assertEqual(by_split["train"], 16)
        self.assertEqual(by_split["development"], 8)
        self.assertEqual(by_split["frozen"], 4)
        self.assertEqual(by_split["adversarial"], 4)
        self.assertEqual(len(self.positives), 32)
        self.assertEqual(len(self.negatives), 20)

    def test_02_split_isolation_clusters(self) -> None:
        admit.assert_cluster_isolation(self.positives)
        train_side = {
            r["cluster_id"]
            for r in self.positives
            if r["split"] in admit.TRAIN_SIDE_SPLITS
        }
        holdout = {
            r["cluster_id"]
            for r in self.positives
            if r["split"] in admit.HOLDOUT_SPLITS
        }
        self.assertEqual(train_side & holdout, set())

    def test_03_per_axis_balance(self) -> None:
        axis_split: dict[str, Counter] = defaultdict(Counter)
        for row in self.positives:
            axis_split[row["axis"]][row["split"]] += 1
        for axis, expected in admit.EXPECTED_AXIS_SPLIT.items():
            self.assertEqual(dict(axis_split[axis]), expected, msg=axis)

    def test_04_negative_exclusion(self) -> None:
        for row in self.negatives:
            self.assertEqual(row["admission_status"], "AUDITOR_ONLY")
            self.assertIs(row["optimizer_eligible"], False)
            self.assertIs(row["response_only_loss_allowed"], False)
            self.assertIs(row["training_authorized"], False)
            self.assertIs(row["run_authorized"], False)

    def test_05_response_only_routing(self) -> None:
        allowed = [r for r in self.positives if r.get("response_only_loss_allowed") is True]
        self.assertEqual(len(allowed), 16)
        self.assertTrue(all(r["split"] == "train" for r in allowed))
        self.assertTrue(all(r["admission_status"] == "TRAIN_READY" for r in allowed))
        self.assertTrue(all(r["optimizer_eligible"] is True for r in allowed))
        for row in self.positives:
            if row["split"] != "train":
                self.assertEqual(row["admission_status"], "EVALUATION_READY")
                self.assertIs(row["optimizer_eligible"], False)
                self.assertIs(row["response_only_loss_allowed"], False)
        for row in self.negatives:
            self.assertIs(row.get("response_only_loss_allowed"), False)

    def test_06_source_hashes_locked(self) -> None:
        locked = self.manifest["locked_source_hashes"]
        checks = {
            "r2_1_positives_jsonl": admit.R2_1_POS,
            "r2_1_negatives_jsonl": admit.R2_1_NEG,
            "r2_1_overlap_audit_report_json": admit.R2_1_AUDIT,
            "design_TARGETED_MOUTH_CORPUS_DESIGN_V3_json": admit.DESIGN_PATH,
            "taxonomy_r2_1": admit.TAXONOMY_PATH,
            "judge_evaluator_v2_2_rubric_py": admit.JUDGE_PATH,
        }
        for key, path in checks.items():
            self.assertTrue(path.is_file(), msg=str(path))
            self.assertEqual(
                locked[key]["sha256"],
                admit._file_sha256(path),
                msg=key,
            )

    def test_07_training_closure(self) -> None:
        self.assertEqual(self.status["status"], STATUS)
        self.assertIs(self.status["training_authorized"], False)
        self.assertIs(self.status["run_authorized"], False)
        self.assertEqual(self.manifest["status"], STATUS)
        self.assertIs(self.manifest["training_authorized"], False)
        self.assertIs(self.manifest["run_authorized"], False)
        for row in self.positives + self.negatives:
            self.assertIs(row["training_authorized"], False)
            self.assertIs(row["run_authorized"], False)
            self.assertEqual(row["corpus_status"], STATUS)

    def test_08_projection_equality(self) -> None:
        proof = admit.validate_admitted_projection(
            self.positives, self.negatives, self.source_pos, self.source_neg
        )
        self.assertTrue(proof["pass"])
        # Content-hash identity: every admitted example_hash equals R2.1 source.
        src_ex = {r["pair_id"]: r["example_hash"] for r in self.source_pos + self.source_neg}
        for row in self.positives + self.negatives:
            self.assertEqual(row["example_hash"], src_ex[row["pair_id"]])
            self.assertEqual(row["ask"], next(
                s["ask"]
                for s in (self.source_pos + self.source_neg)
                if s["pair_id"] == row["pair_id"]
            ))

    def test_09_existing_directory_refused(self) -> None:
        with self.assertRaises(FileExistsError):
            admit.admit(output_dir=self.out_dir)

    def test_10_failed_audit_refusal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="admit_bad_audit_") as tmp:
            bad_audit = Path(tmp) / "bad_audit.json"
            bad_audit.write_text(
                json.dumps(
                    {
                        "pass": False,
                        "findings": [],
                        "exit_criteria": {"hidden_output_copy": 1},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssertionError):
                admit._require_locked_overlap_report_clean(bad_audit)

    def test_11_negative_extra_key_refused(self) -> None:
        bad_neg = copy.deepcopy(self.negatives)
        bad_neg[0]["unexpected_key"] = "bad"
        with self.assertRaises(AssertionError) as ctx:
            admit.validate_admitted_projection(
                self.positives, bad_neg, self.source_pos, self.source_neg
            )
        self.assertIn("unexpected_admitted_keys", str(ctx.exception))

    def test_12_negative_dropped_key_refused(self) -> None:
        bad_neg = copy.deepcopy(self.negatives)
        del bad_neg[0]["axis"]
        with self.assertRaises(AssertionError) as ctx:
            admit.validate_admitted_projection(
                self.positives, bad_neg, self.source_pos, self.source_neg
            )
        self.assertIn("dropped_source_key", str(ctx.exception))

    def test_13_source_manifest_mismatch_refusal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="admit_manifest_mismatch_") as tmp:
            src = Path(tmp) / "source.jsonl"
            src.write_text(json.dumps({"a": 1}) + "\n", encoding="utf-8")
            manifest = Path(tmp) / "source.manifest.json"
            manifest.write_text(
                json.dumps(
                    {"kind": "safe_positive_targets", "sha256": "deadbeef", "count": 1}
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssertionError):
                admit._verify_source_manifest_jsonl(
                    source_jsonl=src,
                    source_manifest=manifest,
                    manifest_kind="safe_positive_targets",
                )

    def test_14_verify_existing_read_only(self) -> None:
        before = {
            p.relative_to(self.out_dir).as_posix(): admit._file_sha256(p)
            for p in sorted(self.out_dir.rglob("*"))
            if p.is_file()
        }
        result = admit.verify_existing(output_dir=self.out_dir)
        after = {
            p.relative_to(self.out_dir).as_posix(): admit._file_sha256(p)
            for p in sorted(self.out_dir.rglob("*"))
            if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
