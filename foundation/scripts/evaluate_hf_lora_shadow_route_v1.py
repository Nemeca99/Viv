#!/usr/bin/env python3
"""Exercise the real HF-LoRA helper with an explicit shadow adapter path."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for path in (FOUNDATION, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.evaluator_v2_3_hybrid import judge  # noqa: E402
from scripts import evaluate_mouth_combined_candidate_v21 as reference  # noqa: E402
from voice_core.hf_lora import generate  # noqa: E402
from voice_core.runtime_contract import finalize_draft  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")
    raw_report = json.loads((FOUNDATION / "artifacts/auto/agentic/runtime_shaped_v64_eval_20260802T135038Z.json").read_text(encoding="utf-8"))
    selected = raw_report["report"]["cases"][:8]
    cases = []
    for source in selected:
        packet = reference.packet({"pair_id": source["pair_id"], "axis": source["axis"], "ask": source["ask"]})
        prompt = reference.generation.render_openaster_prompt(packet, semantic_key=packet.get("semantic_key"))
        completion = generate(prompt, max_new_tokens=64, temperature=0.15, adapter_path=args.adapter)
        raw_text = str(completion.get("text") or "")
        final = finalize_draft(query=source["ask"], packet=packet, raw_text=raw_text, voice_source="hf_lora_shadow")
        verdict = judge(final["text"], axis=source["axis"], ask=source["ask"], use_cpu_sensor=False)
        cases.append({"pair_id": source["pair_id"], "axis": source["axis"], "ask": source["ask"], "completion_ok": bool(completion.get("ok")), "adapter_missing": completion.get("error") == "adapter_missing", "model": completion.get("model"), "raw_text": raw_text, "final_text": final["text"], "final_status": verdict.get("status"), "voice_source": final["voice_source"]})
    report = {"schema_version": "hf_lora_shadow_route_eval_v1", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "adapter": str(args.adapter).replace("\\", "/"), "cases": cases, "all_completion_ok": all(case["completion_ok"] for case in cases), "adapter_missing": sum(case["adapter_missing"] for case in cases), "final_pass": sum(case["final_status"] == "PASS" for case in cases), "final_hold": sum(case["final_status"] == "HOLD" for case in cases), "final_fail": sum(case["final_status"] == "FAIL" for case in cases), "promotion_authorized": False, "deployment_changed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("all_completion_ok", "adapter_missing", "final_pass", "final_hold", "final_fail")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
