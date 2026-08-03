#!/usr/bin/env python3
"""Score raw adapter outputs before and after the governed CPU draft contract."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from models.Training.code import train_stage1_mouth_generation_canary as canary  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


def counts(values: list[str]) -> dict[str, int]:
    counter = Counter(values)
    return {key: int(counter.get(key, 0)) for key in ("PASS", "HOLD", "FAIL")}


def evaluate(source: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    raw_report = payload.get("report") or {}
    cases = []
    for raw in raw_report.get("cases") or []:
        row = {"pair_id": raw.get("pair_id"), "axis": raw.get("axis"), "ask": raw.get("ask")}
        packet = reference.packet(row)
        draft = finalize_draft(query=str(raw.get("ask") or ""), packet=packet, raw_text=str(raw.get("generated") or ""), voice_source="shadow")
        axis = "entity_we_boundary" if str(raw.get("pair_id") or "").startswith("entity-eval-") else str(raw.get("axis") or "")
        verdict = judge(str(draft["text"]), axis=axis, ask=str(raw.get("ask") or ""), use_cpu_sensor=False)
        cases.append({
            "pair_id": raw.get("pair_id"),
            "axis": raw.get("axis"),
            "ask": raw.get("ask"),
            "raw_status": raw.get("status"),
            "final_status": verdict.get("status"),
            "raw_text": raw.get("generated"),
            "final_text": draft["text"],
            "voice_source": draft["voice_source"],
            "toolbleed": int(canary.response_text_has_toolbleed(str(draft["text"]))),
            "acronym_pass": bool(draft["acronym_pass"]),
            "entity_decision": draft["entity_decision"].get("decision"),
        })
    return {
        "schema_version": "mouth_runtime_contract_shadow_eval_v1",
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(source).replace("\\", "/"),
        "source_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
        "raw_counts": counts([str(item["raw_status"]) for item in cases]),
        "final_counts": counts([str(item["final_status"]) for item in cases]),
        "total": len(cases),
        "toolbleed": sum(item["toolbleed"] for item in cases),
        "acronym_failures": sum(not item["acronym_pass"] for item in cases),
        "cases": cases,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_allowed": False,
        "deployment_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    report = evaluate(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("raw_counts", "final_counts", "total", "toolbleed", "acronym_failures")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
