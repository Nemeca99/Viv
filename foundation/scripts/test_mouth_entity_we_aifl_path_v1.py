#!/usr/bin/env python3
"""Exercise the AIFL correction/provenance path without model or GPU work."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from lib import viv_aifl, viv_ide  # noqa: E402
from lib.entity_we_contract import ENTITY_FEEDBACK_PATH  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_entity_aifl_") as temp:
        temp_root = Path(temp)
        conversation = temp_root / "conversation.jsonl"
        latest = temp_root / "run_latest.json"
        feedback = temp_root / "entity_feedback.jsonl"
        turn = {
            "reply": "We humans tend to make this mistake.",
            "s_n": 0.6,
            "soft_dormant": False,
            "voice": {
                "shadow_judge": {
                    "label": "REWARD",
                    "scores": {"vidi": 1, "intellexi": 1, "vixi": 1},
                }
            },
        }
        with (
            patch.object(viv_ide, "ide_turn", return_value=turn),
            patch.object(viv_aifl, "CONVO_JSONL", conversation),
            patch.object(viv_aifl, "RUN_LATEST", latest),
            patch.object(viv_aifl, "evaluate_lora_admission", return_value={"ready": False}),
            patch("lib.entity_we_contract.ENTITY_FEEDBACK_PATH", feedback),
        ):
            result = viv_aifl.run_aifl(turns=1, mode="identity", speak=False, remember=False)
        if result["turns"] != 1 or not conversation.is_file() or not feedback.is_file():
            raise AssertionError("aifl_artifacts_missing")
        row = json.loads(conversation.read_text(encoding="utf-8").splitlines()[0])
        fb = json.loads(feedback.read_text(encoding="utf-8").splitlines()[0])
        if row["reply"] != "Humans tend to make this mistake.":
            raise AssertionError(f"aifl_did_not_apply_safe_repair:{row}")
        if fb["corpus_admission"] != "HOLD_UNTIL_AUDIT" or fb["optimizer_eligible"]:
            raise AssertionError(f"aifl_feedback_was_admitted:{fb}")
        if fb["original_gpu_output"] != "We humans tend to make this mistake.":
            raise AssertionError("aifl_original_missing")
    print("PASS AIFL applies safe repair and logs original/corrected provenance")
    print("ALL_PASS 1/1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

