#!/usr/bin/env python3
"""CPU contracts for mouth V3 R2.1 targeted-patch experiment (no GPU train).

Construct only into tempfile campaign roots — never rewrite the canonical campaign.
Mocks patch real production function names on the experiment module.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
SCRIPTS = Path(__file__).resolve().parent
for candidate in (FOUNDATION, REPO, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import mouth_v3_r2_1_targeted_patch_experiment as exp  # noqa: E402


def _passing_ckpt(step: int, *, paired: int = 2, admitted: float = 1.0) -> dict:
    return {
        "checkpoint_step": step,
        "legacy_goals_pass": 8,
        "legacy_goals_total": 8,
        "mouth_semantic_pass": True,
        "eos_pass": True,
        "valid_pass": True,
        "stop_pass": True,
        "toolbleed_cases": 0,
        "admitted_eval_score": admitted,
        "auditor_score": 1.0,
        "hidden_per_axis": {
            "indirect_tool_agency": 1.0,
            "architecture_cpu_gpu_role": 1.0,
            "identity_humanization": 1.0,
            "memory_ownership_boundary": 1.0,
        },
        "hidden_paired_improvement": paired,
    }


def _incumbent() -> dict:
    return {
        "pass": True,
        "legacy_goals_pass": 8,
        "legacy_goals_total": 8,
        "mouth_semantic_pass": True,
        "eos_pass": True,
        "valid_pass": True,
        "stop_pass": True,
        "toolbleed_cases": 0,
        "admitted_eval_score": 1.0,
        "auditor_score": 1.0,
        "hidden_per_axis": {
            "indirect_tool_agency": 1.0,
            "architecture_cpu_gpu_role": 1.0,
            "identity_humanization": 1.0,
            "memory_ownership_boundary": 1.0,
        },
        "hidden_paired_improvement": 0,
        "role": "incumbent_004859Z",
    }


def _arm_authorized(root: Path, auth_dir: Path) -> str:
    plan_path = root / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["run_authorized"] = True
    plan["training_authorized"] = False
    plan_sha = exp._write_json(plan_path, plan)
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / f"{exp.EXPERIMENT_ID}.json").write_text(
        json.dumps(
            {
                "schema_version": exp.NAMED_UNLOCK_SCHEMA_VERSION,
                "experiment_id": exp.EXPERIMENT_ID,
                "plan_sha256": plan_sha,
                "status": "issued",
                "issued_at": exp._utc(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return plan_sha


class _Lease:
    def __init__(self) -> None:
        self.closed = False
        self.staging_root = Path(".")
        self.final_root = Path(".")

    def close(self) -> None:
        self.closed = True


class MouthV3TargetedPatchExperimentTests(unittest.TestCase):
    def test_01_construct_into_temp_and_refuse_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            result = exp.construct(campaign_root=root)
            self.assertTrue(result["implementation_authorized"])
            self.assertFalse(result["run_authorized"])
            self.assertFalse(result["training_authorized"])
            self.assertTrue((root / "campaign_plan.json").is_file())
            self.assertTrue((root / "hidden_indirect_adversarial_pack_v3_1.json").is_file())
            self.assertTrue((root / "hidden_v3_1_near_copy_audit.json").is_file())
            plan = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["schema_version"], exp.PRODUCTION_PLAN_SCHEMA)
            with self.assertRaises(FileExistsError):
                exp.construct(campaign_root=root)

    def test_02_verify_existing_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            exp.construct(campaign_root=root)
            before = {
                p.name: p.read_bytes()
                for p in root.iterdir()
                if p.is_file()
            }
            report = exp.verify_existing(campaign_root=root)
            self.assertTrue(report["pass"])
            self.assertTrue(report["read_only"])
            self.assertFalse(report["run_authorized"])
            after = {
                p.name: p.read_bytes()
                for p in root.iterdir()
                if p.is_file()
            }
            self.assertEqual(before, after)

    def test_03_run_refuses_when_run_authorized_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            exp.construct(campaign_root=root)
            with self.assertRaises(ValueError) as ctx:
                exp.run_experiment(campaign_root=root)
            self.assertIn("run_authorized_false", str(ctx.exception))
            plan = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIs(plan["run_authorized"], False)

    def test_04_mock_happy_path_win(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            def mock_train(*, output_root, checkpoint_steps, **_kwargs):
                output_root.mkdir(parents=True)
                for step in checkpoint_steps:
                    p = output_root / f"adapter_step_{step}"
                    p.mkdir()
                    (p / "adapter_config.json").write_text("{}", encoding="utf-8")
                return {"ok": True, "adapters": list(checkpoint_steps), "steps": list(checkpoint_steps)}

            def mock_eval(*, incumbent_report, checkpoint_steps, **_kwargs):
                return {
                    "incumbent_report": incumbent_report,
                    "checkpoint_reports": [
                        _passing_ckpt(4, paired=0),
                        _passing_ckpt(8, paired=2),
                        _passing_ckpt(16, paired=3),
                    ],
                    "checkpoint_steps": list(checkpoint_steps),
                }

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(exp, "train_targeted_patch_16", side_effect=mock_train), \
                 mock.patch.object(exp, "evaluate_run_checkpoints", side_effect=mock_eval):
                result = exp.run_experiment(
                    campaign_root=root,
                    authorizations_dir=auth_dir,
                    expected_plan_sha256=plan_sha,
                    output_root=out_root,
                )
            self.assertEqual(result["decision"]["decision"], "WIN")
            self.assertEqual(result["decision"]["winner_checkpoint"], 8)
            self.assertTrue(lease.closed)
            rearmed = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIs(rearmed["run_authorized"], False)
            self.assertIs(rearmed["training_authorized"], False)

    def test_05_baseline_fail_pre_token_pre_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease_opened = {"n": 0}

            def boom_lease(**_k):
                lease_opened["n"] += 1
                return _Lease()

            with mock.patch.object(
                exp,
                "evaluate_incumbent_baseline",
                return_value={"pass": False, "reason": "baseline_regressed"},
            ), mock.patch.object(exp, "open_governed_lease", side_effect=boom_lease), mock.patch.object(
                exp, "train_targeted_patch_16", return_value={"ok": True}
            ), mock.patch.object(
                exp, "evaluate_run_checkpoints", return_value={}
            ):
                with self.assertRaises(ValueError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("incumbent_baseline_failed_pre_lease", str(ctx.exception))
            self.assertEqual(lease_opened["n"], 0)
            token = json.loads(
                (auth_dir / f"{exp.EXPERIMENT_ID}.json").read_text(encoding="utf-8")
            )
            # Token must never be consumed on pre-lease abort (may be invalidated by finally).
            self.assertNotEqual(token["status"], "consumed")
            rearmed = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIs(rearmed["run_authorized"], False)

    def test_05b_malformed_baseline_abort_pre_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease_opened = {"n": 0}

            def boom_lease(**_k):
                lease_opened["n"] += 1
                return _Lease()

            with mock.patch.object(
                exp,
                "evaluate_incumbent_baseline",
                side_effect=ValueError("incumbent_baseline_malformed:hidden_per_axis_empty"),
            ), mock.patch.object(exp, "open_governed_lease", side_effect=boom_lease):
                with self.assertRaises(ValueError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("incumbent_baseline_malformed", str(ctx.exception))
            self.assertEqual(lease_opened["n"], 0)

    def test_06_decide_winner_gates(self) -> None:
        inc = _incumbent()
        decision = exp.decide_winner(
            inc,
            [
                _passing_ckpt(4, paired=1),
                _passing_ckpt(8, paired=2),
                _passing_ckpt(16, paired=2),
            ],
        )
        self.assertEqual(decision["decision"], "WIN")
        self.assertEqual(decision["winner_checkpoint"], 8)

        abort = exp.decide_winner(
            inc,
            [
                _passing_ckpt(4, paired=1),
                _passing_ckpt(8, paired=1),
                _passing_ckpt(16, admitted=0.5),
            ],
        )
        self.assertEqual(abort["decision"], "ABORT")
        self.assertIsNone(abort["winner_checkpoint"])

        bad4 = _passing_ckpt(4, paired=2)
        bad4["toolbleed_cases"] = 1
        self.assertEqual(
            exp.decide_winner(
                inc, [bad4, _passing_ckpt(8, paired=2), _passing_ckpt(16, paired=2)]
            )["winner_checkpoint"],
            8,
        )

        reg = _passing_ckpt(4, paired=2)
        reg["hidden_per_axis"] = dict(inc["hidden_per_axis"])
        reg["hidden_per_axis"]["identity_humanization"] = 0.5
        self.assertEqual(
            exp.decide_winner(
                inc, [reg, _passing_ckpt(8, paired=1), _passing_ckpt(16, paired=1)]
            )["decision"],
            "ABORT",
        )

        with self.assertRaises(ValueError):
            exp.decide_winner(inc, [_passing_ckpt(4, paired=2)])

    def test_07_near_copy_audit_pass_for_v3_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            exp.construct(campaign_root=root)
            audit = json.loads(
                (root / "hidden_v3_1_near_copy_audit.json").read_text(encoding="utf-8")
            )
            self.assertTrue(audit["pass"])
            self.assertEqual(audit["near_copy_hit_count"], 0)

    def test_08_optimizer_and_holdouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            exp.construct(campaign_root=root)
            rows = exp._load_jsonl(root / "optimizer_train_16_TRAIN_READY.jsonl")
            self.assertEqual(len(rows), 16)
            train_ids = {r["pair_id"] for r in rows}
            pos = exp._load_jsonl(exp.ADMITTED_POS)
            neg = exp._load_jsonl(exp.ADMITTED_NEG)
            holdout = {
                r["pair_id"]
                for r in pos
                if r["split"] in {"development", "frozen", "adversarial"}
            } | {r["pair_id"] for r in neg}
            self.assertEqual(train_ids & holdout, set())

    def test_09_batch_order_deterministic(self) -> None:
        a = exp.deterministic_batch_order(["a", "b", "c", "d"])
        b = exp.deterministic_batch_order(["a", "b", "c", "d"])
        self.assertEqual(a["step_schedule"], b["step_schedule"])

    def test_10_gentle32_untouched_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            result = exp.construct(campaign_root=root)
            plan = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["separate_from_gentle32"])
            self.assertTrue(plan["gentle32_contract_unmodified"])
            self.assertAlmostEqual(plan["learning_rate"], 2e-6)
            self.assertEqual(plan["checkpoints"], [4, 8, 16])
            self.assertEqual(result["plan_sha256"], exp._file_sha256(root / "campaign_plan.json"))
        gentle_plan = (
            FOUNDATION
            / "artifacts"
            / "auto"
            / "openaster_training_tree"
            / "stage1_mouth_generation_canary_v4"
            / "campaigns"
            / "mind_lift_gentle32_lr5e6_from_073326Z_v1"
            / "campaign_plan.json"
        )
        self.assertTrue(gentle_plan.is_file())
        doc = json.loads(gentle_plan.read_text(encoding="utf-8"))
        self.assertEqual(doc["experiment_id"], "mind_lift_gentle32_lr5e6_from_073326Z_v1")

    def test_11_canonical_evidence_snapshots_still_present(self) -> None:
        for name in exp.EVIDENCE_SNAPSHOT_NAMES:
            path = exp.CAMPAIGN_ROOT / name
            self.assertTrue(path.is_file(), msg=f"missing evidence:{name}")

    def test_12_abort_winner_rule_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            def mock_train(*, output_root, checkpoint_steps, **_k):
                output_root.mkdir(parents=True)
                for step in checkpoint_steps:
                    (output_root / f"adapter_step_{step}").mkdir()
                return {"ok": True}

            def mock_eval(**_k):
                return {
                    "checkpoint_reports": [
                        _passing_ckpt(4, paired=0),
                        _passing_ckpt(8, paired=0),
                        _passing_ckpt(16, paired=1),
                    ]
                }

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(exp, "train_targeted_patch_16", side_effect=mock_train), \
                 mock.patch.object(exp, "evaluate_run_checkpoints", side_effect=mock_eval):
                result = exp.run_experiment(
                    campaign_root=root,
                    authorizations_dir=auth_dir,
                    expected_plan_sha256=plan_sha,
                    output_root=out_root,
                )
            self.assertEqual(result["decision"]["decision"], "ABORT")
            self.assertTrue(lease.closed)

    def test_13_training_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(
                     exp, "train_targeted_patch_16", return_value={"ok": False, "error": "boom"}
                 ), mock.patch.object(exp, "evaluate_run_checkpoints", return_value={}):
                with self.assertRaises(RuntimeError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("training_failed", str(ctx.exception))
            self.assertTrue(lease.closed)
            rearmed = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIs(rearmed["run_authorized"], False)

    def test_14_evaluation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(
                     exp, "train_targeted_patch_16", return_value={"ok": True}
                 ), mock.patch.object(
                     exp,
                     "evaluate_run_checkpoints",
                     side_effect=RuntimeError("eval_boom"),
                 ):
                with self.assertRaises(RuntimeError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("eval_boom", str(ctx.exception))
            self.assertTrue(lease.closed)

    def test_15_missing_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            def mock_eval(**_k):
                raise FileNotFoundError("checkpoint_missing:adapter_step_8")

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(
                     exp, "train_targeted_patch_16", return_value={"ok": True}
                 ), mock.patch.object(exp, "evaluate_run_checkpoints", side_effect=mock_eval):
                with self.assertRaises(FileNotFoundError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("checkpoint_missing", str(ctx.exception))
            self.assertTrue(lease.closed)

    def test_16_lease_close_failure_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)

            class BadLease:
                staging_root = Path(".")
                final_root = Path(".")

                def close(self) -> None:
                    raise RuntimeError("close_refused")

            def mock_train(*, output_root, checkpoint_steps, **_k):
                output_root.mkdir(parents=True)
                for step in checkpoint_steps:
                    (output_root / f"adapter_step_{step}").mkdir()
                return {"ok": True}

            def mock_eval(**_k):
                return {
                    "checkpoint_reports": [
                        _passing_ckpt(4, paired=2),
                        _passing_ckpt(8, paired=2),
                        _passing_ckpt(16, paired=2),
                    ]
                }

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=BadLease()), \
                 mock.patch.object(exp, "train_targeted_patch_16", side_effect=mock_train), \
                 mock.patch.object(exp, "evaluate_run_checkpoints", side_effect=mock_eval):
                with self.assertRaises(RuntimeError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("lease_close_failed", str(ctx.exception))

    def test_17_rearm_failure_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            out_root = Path(tmp) / "planned_out"
            exp.construct(campaign_root=root)
            plan_sha = _arm_authorized(root, auth_dir)
            lease = _Lease()

            def mock_train(*, output_root, checkpoint_steps, **_k):
                output_root.mkdir(parents=True)
                for step in checkpoint_steps:
                    (output_root / f"adapter_step_{step}").mkdir()
                return {"ok": True}

            def mock_eval(**_k):
                return {
                    "checkpoint_reports": [
                        _passing_ckpt(4, paired=2),
                        _passing_ckpt(8, paired=2),
                        _passing_ckpt(16, paired=2),
                    ]
                }

            with mock.patch.object(exp, "evaluate_incumbent_baseline", return_value=_incumbent()), \
                 mock.patch.object(exp, "open_governed_lease", return_value=lease), \
                 mock.patch.object(exp, "train_targeted_patch_16", side_effect=mock_train), \
                 mock.patch.object(exp, "evaluate_run_checkpoints", side_effect=mock_eval), \
                 mock.patch.object(
                     exp, "_rearm_run_unauthorized", side_effect=OSError("rearm_disk")
                 ):
                with self.assertRaises(RuntimeError) as ctx:
                    exp.run_experiment(
                        campaign_root=root,
                        authorizations_dir=auth_dir,
                        expected_plan_sha256=plan_sha,
                        output_root=out_root,
                    )
            self.assertIn("rearm_failed", str(ctx.exception))

    def test_18_authorize_once_temp_only_not_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "campaign"
            auth_dir = Path(tmp) / "authorizations"
            exp.construct(campaign_root=root)
            # authorize_once requires passing exact-runtime nostep preflight.
            exp._write_json(
                root / exp.EXACT_RUNTIME_PREFLIGHT_NAME,
                {
                    "schema_version": "mouth_v3_r2_1_exact_runtime_nostep_preflight_v1",
                    "pass": True,
                    "optimizer_steps_executed": 0,
                    "run_authorized": False,
                    "training_authorized": False,
                },
            )
            # Point planned output at a non-existing temp path for the check.
            plan_path = root / "campaign_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["checkpoint_paths"]["run_root"] = str(
                Path(tmp) / "planned_out_absent"
            ).replace("\\", "/")
            exp._write_json(plan_path, plan)
            before = exp._file_sha256(plan_path)
            result = exp.authorize_once(campaign_root=root, authorizations_dir=auth_dir)
            self.assertTrue(result["ok"])
            self.assertTrue(result["run_authorized"])
            self.assertFalse(result["training_authorized"])
            plan = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
            self.assertIs(plan["run_authorized"], True)
            self.assertNotEqual(before, result["plan_sha256"])
            token = json.loads(
                (auth_dir / f"{exp.EXPERIMENT_ID}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(token["status"], "issued")
            self.assertEqual(token["plan_sha256"], result["plan_sha256"])

    def test_19_case_level_score_derivation(self) -> None:
        bindings = {
            "adapter_sha256": "a" * 64,
            "evaluator_sha256": "b" * 64,
            "hidden_pack_sha256": "c" * 64,
            "generation_settings": dict(exp.GENERATION_SETTINGS_LOCK),
            "pre_run_plan_sha256": "d" * 64,
        }

        def _j(ok: bool) -> dict:
            return {
                "overall_pass": ok,
                "applicable_axes": [],
                "per_axis_outcomes": {},
                "failure_reasons": [] if ok else ["fail"],
                "toolbleed": 0,
                "stop_metadata": {},
                "token_ids": [],
                "generation_error": None,
                "rubric_judgment": {"overall_pass": ok},
            }

        cases = []
        for i in range(8):
            cases.append(
                {
                    "case_id": f"legacy-{i}",
                    "surface": "legacy_goal",
                    "ask": "a",
                    "generated": "b",
                    "axis_or_split": "legacy_goal",
                    "pass": True,
                    "mouth_semantic_pass": True,
                    "eos_pass": True,
                    "valid_pass": True,
                    "stop_pass": True,
                    "toolbleed": 0,
                    "judgment": _j(True),
                }
            )
        for i in range(16):
            cases.append(
                {
                    "case_id": f"adm-{i}",
                    "surface": "admitted_eval",
                    "ask": "a",
                    "generated": "b",
                    "axis_or_split": "development",
                    "pass": True,
                    "judgment": _j(True),
                }
            )
        for i in range(20):
            cases.append(
                {
                    "case_id": f"aud-{i}",
                    "surface": "auditor",
                    "ask": "a",
                    "generated": "b",
                    "axis_or_split": "auditor",
                    "pass": True,
                    "judgment": _j(True),
                }
            )
        cases.append(
            {
                "case_id": "h1",
                "surface": "hidden_v3_1",
                "ask": "q",
                "generated": "a",
                "axis_or_split": "indirect_tool_agency",
                "pass": False,
                "judgment": _j(False),
            }
        )
        cases.append(
            {
                "case_id": "h2",
                "surface": "hidden_v3_1",
                "ask": "q2",
                "generated": "a2",
                "axis_or_split": "identity_humanization",
                "pass": True,
                "judgment": _j(True),
            }
        )
        for i in range(6):
            cases.append(
                {
                    "case_id": f"hfill-{i}",
                    "surface": "hidden_v3_1",
                    "ask": "q",
                    "generated": "a",
                    "axis_or_split": "architecture_cpu_gpu_role",
                    "pass": False,
                    "judgment": _j(False),
                }
            )
        artifact = {
            "schema_version": exp.CASE_LEVEL_OUTPUTS_SCHEMA,
            "role": "incumbent_004859Z",
            "checkpoint_step": None,
            "immutable": True,
            "bindings": bindings,
            "cases": cases,
        }
        report = exp.derive_score_report_from_case_outputs(artifact)
        self.assertEqual(report["legacy_goals_pass"], 8)
        self.assertTrue(report["mouth_semantic_pass"])
        self.assertIn("indirect_tool_agency", report["hidden_per_axis"])

        ckpt = {
            **artifact,
            "role": "checkpoint",
            "checkpoint_step": 8,
            "cases": list(artifact["cases"]),
        }
        ckpt["cases"] = [
            ({**c, "pass": True, "judgment": _j(True)} if c["case_id"] == "h1" else c)
            for c in artifact["cases"]
        ]
        derived = exp.derive_score_report_from_case_outputs(
            ckpt, incumbent_artifact=artifact
        )
        self.assertEqual(derived["hidden_paired_improvement"], 1)

    def _prep_authorize_temp(self, tmp: Path) -> tuple[Path, Path]:
        root = tmp / "campaign"
        auth_dir = tmp / "authorizations"
        exp.construct(campaign_root=root)
        exp._write_json(
            root / exp.EXACT_RUNTIME_PREFLIGHT_NAME,
            {
                "schema_version": "mouth_v3_r2_1_exact_runtime_nostep_preflight_v1",
                "pass": True,
                "optimizer_steps_executed": 0,
                "run_authorized": False,
                "training_authorized": False,
            },
        )
        plan_path = root / "campaign_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["checkpoint_paths"]["run_root"] = str(tmp / "planned_out_absent").replace(
            "\\", "/"
        )
        exp._write_json(plan_path, plan)
        return root, auth_dir

    def _assert_authorize_rolled_back(self, root: Path, auth_dir: Path) -> None:
        plan = json.loads((root / "campaign_plan.json").read_text(encoding="utf-8"))
        status = json.loads((root / "STATUS.json").read_text(encoding="utf-8"))
        self.assertIs(plan["run_authorized"], False)
        self.assertIs(plan["training_authorized"], False)
        self.assertIs(status["run_authorized"], False)
        self.assertIs(status["training_authorized"], False)
        token_path = auth_dir / f"{exp.EXPERIMENT_ID}.json"
        self.assertFalse(token_path.is_file(), msg="token must not remain after rollback")

    def test_20_authorize_once_fault_injection_each_publish_step(self) -> None:
        """Fault at each os.replace publish; rollback leaves flags false and no token."""
        publish_labels = ("plan", "status", "token")
        for fail_at in (1, 2, 3):
            with tempfile.TemporaryDirectory() as tmp:
                root, auth_dir = self._prep_authorize_temp(Path(tmp))
                real_replace = os.replace
                counter = {"n": 0}

                def flaky_replace(src, dst):  # noqa: ANN001
                    counter["n"] += 1
                    if counter["n"] == fail_at:
                        raise OSError(
                            f"inject_fail_publish_{publish_labels[fail_at - 1]}"
                        )
                    return real_replace(src, dst)

                with mock.patch(
                    "mouth_v3_r2_1_production_runner.os.replace",
                    side_effect=flaky_replace,
                ):
                    with self.assertRaises(OSError) as ctx:
                        exp.authorize_once(
                            campaign_root=root, authorizations_dir=auth_dir
                        )
                self.assertIn("inject_fail_publish_", str(ctx.exception))
                self._assert_authorize_rolled_back(root, auth_dir)

        # Post-publish SHA drift also rolls back.
        with tempfile.TemporaryDirectory() as tmp:
            root, auth_dir = self._prep_authorize_temp(Path(tmp))
            calls = {"n": 0}
            real_sha = exp._file_sha256

            def flaky_sha(path):  # noqa: ANN001
                calls["n"] += 1
                digest = real_sha(path)
                # authorize_once hashes staged_plan then verifies plan_path.
                if calls["n"] >= 2 and Path(path).name == "campaign_plan.json":
                    return "0" * 64
                return digest

            with mock.patch.object(exp, "_file_sha256", side_effect=flaky_sha):
                with self.assertRaises(RuntimeError) as ctx:
                    exp.authorize_once(campaign_root=root, authorizations_dir=auth_dir)
            self.assertIn("authorize_once_plan_sha_drift", str(ctx.exception))
            self._assert_authorize_rolled_back(root, auth_dir)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
