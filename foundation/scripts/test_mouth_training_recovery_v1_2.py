#!/usr/bin/env python3
"""CPU tests for mouth training recovery v1.2 hold-only corpus."""
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
import mouth_training_recovery_v1_2 as recovery


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(x for x in root.rglob("*") if x.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_v1_1_stop_sha_locked() -> None:
    preservation = recovery.assert_v1_1_preserved()
    assert preservation["preserved"] is True
    assert preservation["stop_report_sha256"] == recovery.V1_1_STOP_SHA


def test_no_style_labels_in_train() -> None:
    train = recovery.build_train_rows()
    recovery._assert_no_style_labels(train)
    for row in train:
        assert "Direct request:" not in row["ask"]
        assert "That boundary also applies when asked to" not in row["chosen"]


def test_calibration_and_blind() -> None:
    calibration, blind = recovery.calibration_examples()
    calibration_report = recovery.calibrate(calibration)
    blind_report = recovery.calibrate(blind)
    assert len(calibration) == 48
    assert len(blind) == 24
    assert calibration_report["correct"] == 48
    assert blind_report["correct"] == 24


def test_multilingual_judge_only_no_false_pass() -> None:
    rows = recovery.multilingual_judge_only_failures()
    report = recovery.calibrate(rows)
    assert not any(r["observed"] == "PASS" for r in report["rows"])
    zh = [r for r in report["rows"] if r.get("language") == "zh"]
    assert zh and all(r["observed"] == "FAIL" for r in zh)


def test_corpus_shape_overlap_and_micro_disjoint() -> None:
    train = recovery.build_train_rows()
    dev, blind, auditor = recovery.build_eval_rows()
    micro = recovery.build_micro_pack(train)
    assert (len(train), len(dev), len(blind), len(auditor), len(micro)) == (
        256,
        64,
        32,
        32,
        8,
    )
    assert Counter(x["axis"] for x in train)["indirect_tool_agency"] == 48
    assert len({x["ask_hash"] for x in train}) == 256
    assert len({x["target_hash"] for x in train}) == 256
    assert all(x["optimizer_eligible"] for x in train)
    assert not any(x["optimizer_eligible"] for x in [*dev, *blind, *auditor, *micro])
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
    train_asks = {r["ask_hash"] for r in train}
    train_tgts = {r["target_hash"] for r in train}
    assert not ({r["ask_hash"] for r in micro} & train_asks)
    assert not ({r["target_hash"] for r in micro} & train_tgts)


def test_training_prompt_matches_production_runtime() -> None:
    ask = "Where does reasoning happen, and where does speech happen?"
    semantic_key = "mouth_recovery.architecture_cpu_gpu_role"
    case_id = "prompt-parity-v12"
    packet = production.build_eval_generation_packet(
        ask=ask, semantic_key=semantic_key, case_id=case_id
    )
    expected = generation.render_openaster_prompt(packet, semantic_key=semantic_key)
    observed = targeted.render_targeted_patch_prompt(
        ask=ask, semantic_key=semantic_key, pair_id=case_id
    )
    assert observed == expected
    assert observed.endswith("<|im_start|>assistant\nViv: ")


def test_response_only_masking_on_sample_row() -> None:
    from transformers import AutoTokenizer
    from models.Training.code.train_pairwise_lora import LOCAL_BASE, OPENASTER_EOS_TOKEN
    from models.Training.code.train_mouth_v3_targeted_patch import tokenize_response_only

    tok = AutoTokenizer.from_pretrained(str(LOCAL_BASE), trust_remote_code=True)
    row = recovery.build_micro_pack(recovery.build_train_rows())[0]
    enc = tokenize_response_only(
        tok,
        ask=row["ask"],
        target=row["chosen"],
        pair_id=row["pair_id"],
        system_prompt=recovery.SYSTEM_PROMPT,
        semantic_key=f"mouth_recovery.{row['axis']}",
    )
    labels = enc["labels"]
    assert any(x == -100 for x in labels)
    assert any(x != -100 for x in labels)
    # Last supervised token should be EOS or response content.
    eos = tok.convert_tokens_to_ids(OPENASTER_EOS_TOKEN)
    assert eos in enc["input_ids"] or labels[-1] != -100


def test_temp_build_immutable_and_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "recovery_v12"
        result = recovery.build(output_root=root)
        assert result["status"] == "CORPUS_READY_TRAINING_CLOSED"
        assert result["training_authorized"] is False
        assert result["run_authorized"] is False
        assert result["hold_only"] is True
        assert (root / "micro_overfit_8.jsonl").is_file()
        assert (root / "judge_only_multilingual_failures.json").is_file()
        before = _tree_hash(root)
        try:
            recovery.build(output_root=root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output must fail closed")
        assert _tree_hash(root) == before


def test_authority_flags_closed_on_rows() -> None:
    train = recovery.build_train_rows()
    assert all(r["training_authorized"] is False for r in train)
    assert all(r["run_authorized"] is False for r in train)


def main() -> int:
    tests = [
        test_v1_1_stop_sha_locked,
        test_no_style_labels_in_train,
        test_calibration_and_blind,
        test_multilingual_judge_only_no_false_pass,
        test_corpus_shape_overlap_and_micro_disjoint,
        test_training_prompt_matches_production_runtime,
        test_response_only_masking_on_sample_row,
        test_temp_build_immutable_and_closed,
        test_authority_flags_closed_on_rows,
    ]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"OK {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
